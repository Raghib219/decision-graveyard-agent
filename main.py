"""
Decision Graveyard Agent — FastAPI backend (production build).

Endpoints:
  POST /check           → run retrieval pipeline (JSON response)
  GET  /check/stream    → SSE streaming version of /check
  POST /query           → alias for /check
  POST /ingest          → add one decision record
  POST /ingest/dataset  → load the 28-record dataset
  GET  /debt-score      → Decision Debt Score dashboard
  GET  /log             → full candidate evaluation log
  GET  /status          → health + config check
  GET  /decisions       → list stored decision IDs
  GET  /                → serve single-page UI
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from hindsight_client import Hindsight

from retrieval import (
    query_proposal,
    result_to_dict,
    get_debt_score,
    get_full_log,
    stream_query_proposal,
)
from ingest import get_client, ingest_dataset, ingest_single, wipe_bank, ensure_bank
from cache import cache_status
from auth import verify_api_key, auth_status
from logger import get_logger

load_dotenv()

log           = get_logger("main")
BANK_ID       = os.getenv("BANK_ID",       "decision-graveyard")
HINDSIGHT_URL = os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io")

app = FastAPI(
    title="Decision Graveyard Agent",
    version="2.0.0",
    description=(
        "Every company re-argues decisions it already made. "
        "This agent remembers why they failed."
    ),
)

# ── CORS (needed for external frontends / Railway deploy) ─────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request / response models ─────────────────────────────────────────

class ProposalRequest(BaseModel):
    proposal: str

class IngestRequest(BaseModel):
    decision_id:       str
    proposal:          str
    outcome:           str   # reverted | succeeded | abandoned | partially_adopted
    team:              str
    date:              str   # YYYY-MM-DD
    reasoning_for:     list[str] = []
    reasoning_against: list[str] = []
    evidence:          str = ""

class IngestDatasetRequest(BaseModel):
    clear_first: bool = False


# ── UI ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_ui():
    ui_path = Path(__file__).parent / "static" / "index.html"
    if not ui_path.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(
        str(ui_path),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# ── POST /check  (JSON response) ─────────────────────────────────────

@app.post("/check")
async def check(
    req: ProposalRequest,
    _: None = Depends(verify_api_key),
):
    """Run the retrieval pipeline. Returns JSON when complete."""
    if not req.proposal.strip():
        raise HTTPException(status_code=400, detail="proposal must not be empty")
    log.info("check_request proposal=%s", req.proposal[:80])
    result = query_proposal(req.proposal.strip())
    return JSONResponse(content=result_to_dict(result))


# ── GET /check/stream  (SSE streaming) ───────────────────────────────

@app.get("/check/stream")
async def check_stream(
    proposal: str = Query(..., description="The proposal to evaluate"),
    _: None = Depends(verify_api_key),
):
    """
    Server-Sent Events version of /check.
    Events: status | candidate | result | done | error
    """
    if not proposal.strip():
        raise HTTPException(status_code=400, detail="proposal must not be empty")
    log.info("stream_request proposal=%s", proposal[:80])
    return StreamingResponse(
        stream_query_proposal(proposal.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ── POST /query  (alias) ──────────────────────────────────────────────

@app.post("/query")
async def query_alias(
    req: ProposalRequest,
    _: None = Depends(verify_api_key),
):
    """Alias for /check — backward compatibility."""
    if not req.proposal.strip():
        raise HTTPException(status_code=400, detail="proposal must not be empty")
    result = query_proposal(req.proposal.strip())
    return JSONResponse(content=result_to_dict(result))


# ── POST /ingest ──────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_one(
    req: IngestRequest,
    _: None = Depends(verify_api_key),
):
    """Add one decision record to Hindsight memory."""
    client = get_client()
    ok = ingest_single(
        client=client,
        decision_id=req.decision_id,
        proposal=req.proposal,
        outcome=req.outcome,
        team=req.team,
        date=req.date,
        reasoning_for=req.reasoning_for,
        reasoning_against=req.reasoning_against,
        evidence=req.evidence,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Ingestion failed — check server logs")
    log.info("ingested decision_id=%s", req.decision_id)
    return {
        "status":      "ok",
        "decision_id": req.decision_id,
        "message":     f"Stored {req.decision_id} in bank '{BANK_ID}'.",
    }


# ── POST /ingest/dataset ──────────────────────────────────────────────

@app.post("/ingest/dataset")
async def ingest_full_dataset(
    req: IngestDatasetRequest,
    _: None = Depends(verify_api_key),
):
    """Load the full 28-record Nimbus Retail dataset into Hindsight."""
    client = get_client()
    if req.clear_first:
        wipe_bank(client)
    count = ingest_dataset(client)
    log.info("dataset_ingested count=%d", count)
    return {
        "status":           "ok",
        "records_ingested": count,
        "message":          f"Loaded {count} decision records into bank '{BANK_ID}'.",
    }


# ── GET /debt-score ───────────────────────────────────────────────────

@app.get("/debt-score")
async def debt_score():
    """Decision Debt Score dashboard — persistent across restarts."""
    return JSONResponse(content=get_debt_score())


# ── GET /log ──────────────────────────────────────────────────────────

@app.get("/log")
async def full_log():
    """Full candidate evaluation log — every candidate, surfaced + rejected."""
    return JSONResponse(content=get_full_log())


# ── GET /status ───────────────────────────────────────────────────────

@app.get("/status")
async def status():
    """Health check — Hindsight, Groq, Redis, auth."""
    client       = get_client()
    hindsight_ok = False
    fact_count   = 0
    try:
        ensure_bank(client)
        # Use thread pool for recall
        import concurrent.futures
        def _recall():
            if os.getenv("HINDSIGHT_API_KEY"):
                c = Hindsight(base_url=os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io"),
                             api_key=os.getenv("HINDSIGHT_API_KEY"), timeout=60.0)
            else:
                c = Hindsight(base_url=os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io"), timeout=60.0)
            return c.recall(bank_id=BANK_ID, query="proposal team outcome", max_tokens=200, budget="low")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_recall)
            result = future.result(timeout=10)
        facts      = result.results if result.results else []
        fact_count = len(facts)
        hindsight_ok = True
    except Exception as e:
        hindsight_ok = False
        log.warning("status_check_failed error=%s", str(e))

    cs = cache_status()
    au = auth_status()

    return {
        "hindsight_url":       HINDSIGHT_URL,
        "hindsight_reachable": hindsight_ok,
        "hindsight_key_set":   bool(os.getenv("HINDSIGHT_API_KEY", "")),
        "bank_id":             BANK_ID,
        "documents_stored":    fact_count,
        "bank_loaded":         fact_count > 0,
        "groq_key_set":        bool(os.getenv("GROQ_API_KEY", "")),
        "groq_model":          os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
        "llm_mode":            "groq" if os.getenv("GROQ_API_KEY") else "heuristic fallback",
        "cache":               cs,
        "auth":                au,
    }


# ── GET /decisions ────────────────────────────────────────────────────

@app.get("/decisions")
async def list_decisions():
    """List stored decision IDs via recall."""
    client = get_client()
    try:
        result    = client.recall(bank_id=BANK_ID, query="DEC reverted failed succeeded", max_tokens=4000, budget="high")
        facts     = result.results if result.results else []
        seen, decisions = set(), []
        for f in facts:
            text = getattr(f, "text", str(f))
            m    = re.search(r"\b(DEC-\d+)\b", text)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                decisions.append({"id": m.group(1)})
        return {"bank_id": BANK_ID, "count": len(decisions), "decisions": decisions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── static files ──────────────────────────────────────────────────────

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port   = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENV", "production") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)

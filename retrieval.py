"""
Retrieval pipeline for the Decision Graveyard Agent.

Flow:
  1. Check Redis cache — return immediately on hit
  2. Embed the incoming proposal → Hindsight recall → top-5 candidates
  3. LLM structured evaluation per candidate (Groq qwen/qwen3.8-27b):
       - same_problem:      bool + reason
       - same_failure_mode: bool + reason
       - confidence:        high / medium / low + explanation
  4. Confidence gate — surface only high/medium matches
  5. Log ALL candidates (including rejected) → persistent store
  6. Accumulate debt-score data              → persistent store
  7. Cache the result in Redis
"""

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator

from dotenv import load_dotenv
from groq import Groq
from hindsight_client import Hindsight

from store import (
    append_debt_entry,
    append_candidate_entry,
    get_debt_score_data,
    get_full_log_data,
)
from cache import get_cached, set_cached
from logger import get_logger

load_dotenv()

log = get_logger("retrieval")

HINDSIGHT_URL     = os.getenv("HINDSIGHT_URL",     "https://api.hindsight.vectorize.io")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")
BANK_ID           = os.getenv("BANK_ID",           "decision-graveyard")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY",      "")
GROQ_MODEL        = os.getenv("GROQ_MODEL",        "qwen/qwen3.8-27b")


# ── data models ───────────────────────────────────────────────────────

@dataclass
class EvalResult:
    decision_id:              str
    candidate_text:           str
    same_problem:             bool
    same_problem_reason:      str
    same_failure_mode:        bool
    same_failure_mode_reason: str
    confidence:               str   # "high" | "medium" | "low"
    confidence_explanation:   str
    surfaced:                 bool  # True when confidence is high or medium


@dataclass
class QueryResult:
    proposal:         str
    timestamp:        str
    bank_loaded:      bool
    surfaced:         list
    rejected:         list
    message:          str
    is_new_territory: bool


# ── client factories ──────────────────────────────────────────────────

def _get_hindsight() -> Hindsight:
    if HINDSIGHT_API_KEY:
        return Hindsight(base_url=HINDSIGHT_URL, api_key=HINDSIGHT_API_KEY, timeout=60.0)
    return Hindsight(base_url=HINDSIGHT_URL, timeout=60.0)


def _recall_in_thread(bank_id: str, query: str, max_tokens: int, budget: str):
    """Run recall() in a fresh thread with a new client instance."""
    if HINDSIGHT_API_KEY:
        client = Hindsight(base_url=HINDSIGHT_URL, api_key=HINDSIGHT_API_KEY, timeout=60.0)
    else:
        client = Hindsight(base_url=HINDSIGHT_URL, timeout=60.0)
    return client.recall(bank_id=bank_id, query=query, max_tokens=max_tokens, budget=budget)


def _get_groq() -> Optional[Groq]:
    if not GROQ_API_KEY:
        return None
    return Groq(api_key=GROQ_API_KEY)


def _bank_has_memories() -> bool:
    """Return True when the bank has memories. Tries two different queries for reliability."""
    try:
        # Run in thread pool to avoid event loop conflicts
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            for query in ["proposal team outcome reverted", "chatbot support ticket failed"]:
                future = executor.submit(_recall_in_thread, BANK_ID, query, 100, "low")
                result = future.result(timeout=10)
                facts  = result.results if result.results else []
                if facts:
                    return True
        return False
    except Exception:
        return False


# ── LLM prompts ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a strict organisational memory analyst at Nimbus Retail.
Compare a NEW proposal against a PAST decision record.

Respond ONLY with valid JSON — no markdown, no extra text:
{
  "same_problem":             true|false,
  "same_problem_reason":      "one concise sentence",
  "same_failure_mode":        true|false,
  "same_failure_mode_reason": "one concise sentence",
  "confidence":               "high"|"medium"|"low",
  "confidence_explanation":   "one concise sentence"
}

STRICT DEFINITIONS:

same_problem: true ONLY when both proposals solve the EXACT SAME underlying
  business problem (e.g. both about chatbot automation for support tickets).
  false when different domains (chatbot vs. fulfillment partner).

same_failure_mode: true ONLY when the new proposal risks the SAME root-cause
  failure as the past decision. false when past decision SUCCEEDED or problems
  are unrelated.

confidence:
  "high"   — SAME domain AND the new proposal risks the SAME failure (does NOT
             address the prior failure mode). Use sparingly.
  "medium" — SAME domain AND the new proposal EXPLICITLY addresses the prior
             failure mode (e.g. adds human oversight where there was none).
  "low"    — surface keyword overlap only, different domains, or prior SUCCEEDED.
             Use this for most comparisons.

EXAMPLES:
  NEW: "automated chatbot, no fallback"
  PAST: "automated chatbot, no fallback, REVERTED"
  → confidence="high"

  NEW: "AI chatbot WITH human escalation path"
  PAST: "automated chatbot, no fallback, REVERTED"
  → confidence="medium"  (same domain, addresses prior failure)

  NEW: "loyalty programme"
  PAST: "chatbot for support tickets"
  → confidence="low"
"""

_USER_TEMPLATE = """\
NEW PROPOSAL:
{proposal}

PAST DECISION RECORD:
{past_record}

Evaluate whether the new proposal repeats or conflicts with the past decision.
"""


# ── LLM / heuristic evaluation ────────────────────────────────────────

def _evaluate_with_llm(groq_client: Groq, proposal: str, candidate_text: str) -> dict:
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_TEMPLATE.format(
                    proposal=proposal,
                    past_record=candidate_text[:3000],
                )},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        raw   = resp.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group() if match else raw)
    except Exception as e:
        log.warning("llm_eval_failed error=%s", str(e))
        return {
            "same_problem":             False,
            "same_problem_reason":      f"LLM evaluation failed: {e}",
            "same_failure_mode":        False,
            "same_failure_mode_reason": "N/A",
            "confidence":               "low",
            "confidence_explanation":   f"Could not evaluate ({type(e).__name__}).",
        }


def _heuristic_eval(proposal: str, candidate_text: str) -> dict:
    """Keyword-overlap fallback when Groq is not configured."""
    p_words = set(proposal.lower().split())
    c_words = set(candidate_text.lower().split())
    overlap = len(p_words & c_words) / max(len(p_words), 1)
    confidence   = "medium" if overlap > 0.30 else "low"
    same_problem = overlap > 0.15
    return {
        "same_problem":             same_problem,
        "same_problem_reason":      f"Keyword overlap {overlap:.0%}",
        "same_failure_mode":        same_problem and overlap > 0.30,
        "same_failure_mode_reason": "Based on keyword overlap (no LLM)",
        "confidence":               confidence,
        "confidence_explanation":   "Heuristic mode — add GROQ_API_KEY for proper eval",
    }


# ── core query function ───────────────────────────────────────────────

def query_proposal(proposal: str) -> QueryResult:
    """
    Main entry point called by POST /check.
    Results are cached in Redis and persisted to store.json.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    proposal  = proposal.strip()

    # 0. Redis cache hit?
    cached = get_cached(proposal)
    if cached:
        log.info("cache_hit proposal=%s", proposal[:80])
        # Rebuild QueryResult from cached dict
        from dataclasses import fields as dc_fields
        surfaced = [EvalResult(**e) for e in cached.get("surfaced", [])]
        rejected = [EvalResult(**e) for e in cached.get("rejected", [])]
        return QueryResult(
            proposal=cached["proposal"],
            timestamp=cached["timestamp"],
            bank_loaded=cached["bank_loaded"],
            surfaced=surfaced,
            rejected=rejected,
            message=cached["message"],
            is_new_territory=cached["is_new_territory"],
        )

    hindsight = _get_hindsight()
    groq      = _get_groq()

    # 1. Guard: is the bank loaded?
    if not _bank_has_memories():
        result = QueryResult(
            proposal=proposal, timestamp=timestamp, bank_loaded=False,
            surfaced=[], rejected=[],
            message="No decision history loaded yet. Go to Setup and click 'Load Dataset'.",
            is_new_territory=True,
        )
        _persist(result)
        return result

    # 2. Hindsight recall — augment query to surface failed decisions first
    augmented = proposal + " reverted failed abandoned no human fallback"
    try:
        # Run in thread pool to avoid event loop conflicts
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_recall_in_thread, BANK_ID, augmented, 8000, "high")
            recall_resp = future.result(timeout=30)
        candidates_raw = getattr(recall_resp, "results", []) or []
    except Exception as e:
        log.error("hindsight_recall_failed error=%s", str(e))
        result = QueryResult(
            proposal=proposal, timestamp=timestamp, bank_loaded=True,
            surfaced=[], rejected=[],
            message=f"Hindsight recall error: {e}",
            is_new_territory=True,
        )
        _persist(result)
        return result

    if not candidates_raw:
        result = QueryResult(
            proposal=proposal, timestamp=timestamp, bank_loaded=True,
            surfaced=[], rejected=[],
            message="No strong match found. This looks like new decision territory.",
            is_new_territory=True,
        )
        _persist(result)
        return result

    # 3. Deduplicate — keep top-5 unique DEC-XXX IDs
    seen_ids: set[str] = set()
    top5: list[tuple[str, str]] = []
    for c in candidates_raw:
        text = getattr(c, "text", str(c))
        m    = re.search(r"\b(DEC-\d+)\b", text)
        if not m:
            continue
        dec_id = m.group(1)
        if dec_id not in seen_ids:
            seen_ids.add(dec_id)
            top5.append((dec_id, text))
        if len(top5) >= 5:
            break

    if not top5:
        result = QueryResult(
            proposal=proposal, timestamp=timestamp, bank_loaded=True,
            surfaced=[], rejected=[],
            message="No labelled decision records found in recall results.",
            is_new_territory=True,
        )
        _persist(result)
        return result

    # 4. LLM / heuristic evaluation per candidate
    surfaced: list[EvalResult] = []
    rejected: list[EvalResult] = []

    for dec_id, candidate_text in top5:
        eval_dict   = (_evaluate_with_llm(groq, proposal, candidate_text)
                       if groq else _heuristic_eval(proposal, candidate_text))
        is_surfaced = eval_dict.get("confidence", "low") in ("high", "medium")
        er = EvalResult(
            decision_id=dec_id,
            candidate_text=candidate_text,
            same_problem=eval_dict.get("same_problem", False),
            same_problem_reason=eval_dict.get("same_problem_reason", ""),
            same_failure_mode=eval_dict.get("same_failure_mode", False),
            same_failure_mode_reason=eval_dict.get("same_failure_mode_reason", ""),
            confidence=eval_dict.get("confidence", "low"),
            confidence_explanation=eval_dict.get("confidence_explanation", ""),
            surfaced=is_surfaced,
        )
        (surfaced if is_surfaced else rejected).append(er)

        append_candidate_entry({
            "timestamp":         timestamp,
            "proposal":          proposal[:120],
            "decision_id":       dec_id,
            "confidence":        er.confidence,
            "surfaced":          is_surfaced,
            "same_problem":      er.same_problem,
            "same_failure_mode": er.same_failure_mode,
            "explanation":       er.confidence_explanation,
            "candidate_snippet": candidate_text[:200],
        })
        log.info("candidate_evaluated %s conf=%s surfaced=%s", dec_id, er.confidence, is_surfaced)

    # 5. Verdict message
    high_matches   = [e for e in surfaced if e.confidence == "high"]
    medium_matches = [e for e in surfaced if e.confidence == "medium"]

    if not surfaced:
        message          = ("No strong match found. The closest past decisions were reviewed "
                            "but are not similar enough to flag. This looks like new territory.")
        is_new_territory = True
    elif high_matches:
        ids              = ", ".join(e.decision_id for e in high_matches)
        message          = (f"[HIGH] This directly conflicts with / repeats past decision(s): {ids}. "
                            "Review the graveyard before proceeding.")
        is_new_territory = False
    else:
        ids              = ", ".join(e.decision_id for e in medium_matches)
        message          = (f"[MEDIUM] Similar to past decision(s): {ids}, but there are differences. "
                            "Check the nuance — the prior failure mode may have been addressed.")
        is_new_territory = False

    result = QueryResult(
        proposal=proposal, timestamp=timestamp, bank_loaded=True,
        surfaced=surfaced, rejected=rejected,
        message=message, is_new_territory=is_new_territory,
    )
    _persist(result)

    # 6. Cache result
    set_cached(proposal, result_to_dict(result))
    log.info("query_complete surfaced=%d rejected=%d", len(surfaced), len(rejected))
    return result


# ── persistence helper ────────────────────────────────────────────────

def _persist(result: QueryResult) -> None:
    append_debt_entry({
        "timestamp":        result.timestamp,
        "proposal_snippet": result.proposal[:120],
        "bank_loaded":      result.bank_loaded,
        "caught":           len(result.surfaced) > 0,
        "high_confidence":  any(e.confidence == "high"   for e in result.surfaced),
        "medium_confidence": any(e.confidence == "medium" for e in result.surfaced),
        "new_territory":    result.is_new_territory,
        "matched_ids":      [e.decision_id for e in result.surfaced],
    })


# ── public accessors (used by main.py) ────────────────────────────────

def get_debt_score() -> dict:
    return get_debt_score_data()


def get_full_log() -> dict:
    return get_full_log_data()


def result_to_dict(r: QueryResult) -> dict:
    return {
        "proposal":         r.proposal,
        "timestamp":        r.timestamp,
        "bank_loaded":      r.bank_loaded,
        "surfaced":         [asdict(e) for e in r.surfaced],
        "rejected":         [asdict(e) for e in r.rejected],
        "message":          r.message,
        "is_new_territory": r.is_new_territory,
    }


# ── SSE streaming generator ───────────────────────────────────────────

async def stream_query_proposal(proposal: str) -> AsyncGenerator[str, None]:
    """
    Async generator for Server-Sent Events streaming.
    Yields SSE-formatted strings as each evaluation step completes.
    """
    import asyncio

    timestamp = datetime.now(timezone.utc).isoformat()
    proposal  = proposal.strip()

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    yield _sse("status", {"step": "start", "message": "Checking decision history..."})
    await asyncio.sleep(0)

    # Cache check
    cached = get_cached(proposal)
    if cached:
        yield _sse("status", {"step": "cache_hit", "message": "Result from cache."})
        yield _sse("result", cached)
        yield _sse("done",   {"message": "Complete (cached)."})
        return

    hindsight = _get_hindsight()
    groq      = _get_groq()

    # Bank check
    yield _sse("status", {"step": "recall", "message": "Searching decision memory..."})
    await asyncio.sleep(0)

    if not _bank_has_memories():
        payload = {
            "proposal": proposal, "timestamp": timestamp, "bank_loaded": False,
            "surfaced": [], "rejected": [],
            "message": "No decision history loaded yet. Go to Setup and click 'Load Dataset'.",
            "is_new_territory": True,
        }
        yield _sse("result", payload)
        yield _sse("done",   {"message": "No history."})
        return

    # Recall
    augmented = proposal + " reverted failed abandoned no human fallback"
    try:
        # Use thread pool to avoid event loop conflicts in async context
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            recall_resp = await loop.run_in_executor(
                executor,
                _recall_in_thread,
                BANK_ID,
                augmented,
                8000,
                "high"
            )
        candidates_raw = getattr(recall_resp, "results", []) or []
    except Exception as e:
        yield _sse("error", {"message": f"Hindsight recall error: {e}"})
        return

    # Deduplicate
    seen_ids: set[str] = set()
    top5: list[tuple[str, str]] = []
    for c in candidates_raw:
        text = getattr(c, "text", str(c))
        m    = re.search(r"\b(DEC-\d+)\b", text)
        if not m:
            continue
        dec_id = m.group(1)
        if dec_id not in seen_ids:
            seen_ids.add(dec_id)
            top5.append((dec_id, text))
        if len(top5) >= 5:
            break

    yield _sse("status", {"step": "evaluate", "message": f"Evaluating {len(top5)} candidates with LLM..."})
    await asyncio.sleep(0)

    # Evaluate candidates one by one, streaming each result
    surfaced: list[EvalResult] = []
    rejected: list[EvalResult] = []

    for i, (dec_id, candidate_text) in enumerate(top5):
        yield _sse("status", {"step": "eval_candidate",
                               "message": f"Evaluating {dec_id} ({i+1}/{len(top5)})..."})
        await asyncio.sleep(0)

        eval_dict   = (_evaluate_with_llm(groq, proposal, candidate_text)
                       if groq else _heuristic_eval(proposal, candidate_text))
        is_surfaced = eval_dict.get("confidence", "low") in ("high", "medium")
        er = EvalResult(
            decision_id=dec_id,
            candidate_text=candidate_text,
            same_problem=eval_dict.get("same_problem", False),
            same_problem_reason=eval_dict.get("same_problem_reason", ""),
            same_failure_mode=eval_dict.get("same_failure_mode", False),
            same_failure_mode_reason=eval_dict.get("same_failure_mode_reason", ""),
            confidence=eval_dict.get("confidence", "low"),
            confidence_explanation=eval_dict.get("confidence_explanation", ""),
            surfaced=is_surfaced,
        )
        (surfaced if is_surfaced else rejected).append(er)

        # Stream this candidate immediately so UI updates live
        yield _sse("candidate", {
            "decision_id":            er.decision_id,
            "confidence":             er.confidence,
            "surfaced":               er.surfaced,
            "same_problem":           er.same_problem,
            "same_problem_reason":    er.same_problem_reason,
            "same_failure_mode":      er.same_failure_mode,
            "same_failure_mode_reason": er.same_failure_mode_reason,
            "confidence_explanation": er.confidence_explanation,
            "candidate_text":         candidate_text[:300],
        })
        await asyncio.sleep(0)

        append_candidate_entry({
            "timestamp":         timestamp,
            "proposal":          proposal[:120],
            "decision_id":       dec_id,
            "confidence":        er.confidence,
            "surfaced":          is_surfaced,
            "same_problem":      er.same_problem,
            "same_failure_mode": er.same_failure_mode,
            "explanation":       er.confidence_explanation,
            "candidate_snippet": candidate_text[:200],
        })

    # Final verdict
    high_matches   = [e for e in surfaced if e.confidence == "high"]
    medium_matches = [e for e in surfaced if e.confidence == "medium"]

    if not surfaced:
        message          = ("No strong match found. Reviewed but not similar enough to flag. "
                            "This looks like new territory.")
        is_new_territory = True
    elif high_matches:
        ids              = ", ".join(e.decision_id for e in high_matches)
        message          = (f"[HIGH] Repeats past decision(s): {ids}. Review before proceeding.")
        is_new_territory = False
    else:
        ids              = ", ".join(e.decision_id for e in medium_matches)
        message          = (f"[MEDIUM] Similar to past decision(s): {ids}. Check the nuance.")
        is_new_territory = False

    result = QueryResult(
        proposal=proposal, timestamp=timestamp, bank_loaded=True,
        surfaced=surfaced, rejected=rejected,
        message=message, is_new_territory=is_new_territory,
    )
    _persist(result)
    final = result_to_dict(result)
    set_cached(proposal, final)

    yield _sse("result", final)
    yield _sse("done",   {"message": message})

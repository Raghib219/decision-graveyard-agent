# Decision Graveyard Agent

> Every company re-argues decisions it already made. This agent remembers not just what you decided, but *why* — and stops you from repeating expensive mistakes.

## Quick Start (3 steps)

### 1. Clone and install
```bash
git clone https://github.com/your-username/decision-graveyard
cd decision-graveyard
pip install -r requirements.txt
```

### 2. Configure API keys
```bash
cp .env.example .env
# Edit .env and add your keys:
#   HINDSIGHT_API_KEY  (get from https://ui.hindsight.vectorize.io/settings)
#   GROQ_API_KEY       (get from https://console.groq.com/keys)
```

### 3. Run the agent
```bash
python main.py
# Open http://localhost:8000
# Go to Setup → Load 28-record Dataset
# Go to Check Proposal → try the quick examples
```

**With Docker:**
```bash
docker-compose up --build
# Open http://localhost:8000
```

---

## Demo Script (60-90 seconds)

| Beat | What to do |
|------|-----------|
| 1. Empty memory | Go to Query tab → paste "Deploy a fully automated chatbot for all tier-1 support tickets without human oversight" → Check the Graveyard → shows "No history loaded" |
| 2. Load memory | Go to Setup tab → click "Load 28-record Dataset" → wait for confirmation |
| 3. Same query again | Back to Query tab → re-run the same proposal → now shows DEC-011 (HIGH confidence) with CSAT numbers |
| 4. Nuance moment | Change proposal to "Deploy an AI chatbot with human escalation path" → runs → shows MEDIUM confidence match with explanation of difference |
| 5. Debt dashboard | Switch to Debt Dashboard tab → see running tally |

---

## Architecture

```
New proposal (text)
       ↓
1. Embed proposal → Hindsight recall → top 5 candidates
       ↓
2. Groq LLM evaluation per candidate:
   - Same underlying problem? (yes/no + reason)
   - Same root failure mode? (yes/no + reason)
   - Confidence: high / medium / low
       ↓
3. Gate: surface high/medium only
       ↓
4. Log ALL candidates (including rejected) → transparency
       ↓
5. Update Decision Debt Score dashboard
```

## File Structure

```
.
├── main.py              # FastAPI backend (all endpoints)
├── retrieval.py         # Retrieval pipeline + LLM eval + SSE streaming
├── ingest.py            # Hindsight ingestion module
├── convert_to_nl.py     # Dataset → natural language conversion
├── store.py             # Persistent JSON store (survives restarts)
├── cache.py             # Redis cache (graceful fallback)
├── auth.py              # API key auth (optional)
├── logger.py            # Structured logging + Sentry
├── data/
│   ├── dataset.json     # 28-record Nimbus Retail dataset
│   └── store.json       # Persistent Debt Score + Candidate Log
├── static/
│   └── index.html       # Single-page UI with SSE streaming
├── Dockerfile           # Docker image
├── docker-compose.yml   # Docker + Redis
├── .github/workflows/
│   └── ci.yml           # CI/CD pipeline
├── .env.example         # Template for API keys (safe to commit)
└── .env                 # Your actual API keys (gitignored)
```

---

## Security Note

**⚠️ Never commit `.env` to git** — it's already excluded via `.gitignore`.

Each user must create their own `.env` with their own API keys. The `.env.example` file shows the structure without exposing secrets.

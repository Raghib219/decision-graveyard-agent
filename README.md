# 🪦 Decision Graveyard Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Powered by Hindsight](https://img.shields.io/badge/Powered%20by-Hindsight-6366f1)](https://hindsight.vectorize.io)
[![Powered by Groq](https://img.shields.io/badge/Powered%20by-Groq-orange)](https://groq.com)

> **Every company re-argues decisions it already made.** This AI agent remembers not just *what* you decided, but *why* — and stops you from repeating expensive mistakes.

## 🎯 The Problem

Companies waste millions repeating failed decisions because:
- People leave and take institutional knowledge with them
- Slack threads disappear into the void
- Retrospectives get buried in Confluence
- New PMs don't know what the previous team already tried

**Example:** Product team proposes an automated chatbot with no human oversight → 3 months of development → Launch → CSAT drops from 4.2 to 2.1 → 340 angry customers → Reverted after 4 weeks → $180K wasted

18 months later, a new PM proposes *the exact same thing*. The cycle repeats.

## 💡 The Solution

Decision Graveyard Agent is an AI-powered memory system that:

✅ **Searches** your company's past decisions using semantic similarity (not keyword matching)  
✅ **Reasons** about whether proposals repeat past failures using LLM evaluation  
✅ **Warns** you in real-time with confidence levels (HIGH/MEDIUM/LOW)  
✅ **Shows** full transparency — see what was rejected and why (not a black box)  
✅ **Persists** everything — survives server restarts, production-ready

---

---

## ✨ Features

### Real-Time AI Reasoning
- **Server-Sent Events (SSE) streaming** — watch candidates appear live as the LLM evaluates each one
- **Confidence scoring** — HIGH (direct repeat), MEDIUM (similar but mitigated), LOW (different domain)
- **Semantic search** via Hindsight Cloud — understands "automated chatbot" = "AI support agent"

### Full Transparency
- **Candidate Log** — see EVERY decision evaluated, including rejected ones
- **Explanations** — "Rejected because: Different domain (sales vs support)"
- **Audit trail** — persistent across restarts

### Production-Ready
- **Persistent storage** — Debt Score and Candidate Log survive server restarts
- **Redis caching** — instant response on repeat queries (graceful fallback if Redis unavailable)
- **Thread-pool isolation** — handles FastAPI + sync Hindsight client conflicts
- **Docker support** — `docker-compose up` and you're running

### Decision Debt Score
Track how often your company almost repeated a past mistake:
- Total proposals reviewed
- Near-repeats caught (HIGH/MEDIUM)
- New territory decisions

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Memory** | [Hindsight Cloud](https://hindsight.vectorize.io) | Vector database for semantic search over past decisions |
| **LLM Reasoning** | [Groq](https://groq.com) (qwen/qwen3.8-27b) | Structured evaluation: same problem? same failure mode? confidence? |
| **Backend** | FastAPI | Async-native API with SSE streaming |
| **Cache** | Redis | 5-min TTL cache for query results (optional) |
| **Frontend** | Vanilla JS + SSE | Real-time streaming UI with animated candidate cards |
| **Storage** | JSON file (`data/store.json`) | Persistent Debt Score + Candidate Log |
| **Deploy** | Docker + Railway | Production-ready containerization |

---

## 🚀 Quick Start (3 steps)

### 1. Clone and install
```bash
git clone https://github.com/Raghib219/decision-graveyard-agent.git
cd decision-graveyard-agent
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

---

## 📺 Demo

### Live Demo (60 seconds)

1. **Load 28-record dataset** (past company decisions)
2. **Query**: "Automated chatbot — no human fallback"
   - ✅ Streams candidates live
   - ✅ Finds DEC-011 (HIGH confidence — same idea failed in 2024)
   - ✅ Shows: "CSAT dropped to 2.1/5, 340 complaints, REVERTED"
3. **Query**: "Chatbot WITH human escalation"
   - ✅ Same DEC-011 retrieved
   - ✅ But MEDIUM confidence: "You addressed the failure mode"
4. **Transparency Log**: Shows all 5 candidates evaluated (1 HIGH, 4 LOW rejected)

### Screenshots

*[Add screenshots here after deploying]*

---

## 🎬 Demo Script (60-90 seconds)

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

---

## 🤝 Contributing

Contributions welcome! This project was built for a hackathon but is designed to be production-ready.

**Ideas for improvements:**
- PostgreSQL backend for scalability
- Multi-tenancy (separate banks per company)
- Slack/Teams integration
- Document upload (PDF/DOCX retros)
- GraphQL API

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

---

## 🏆 Hackathon Context

Built for **[Hackathon Name]** using:
- **Hindsight Cloud** (sponsor tech) — semantic memory search
- **Groq** — fast LLM inference
- Real-time SSE streaming
- Production-ready architecture

**The pitch:** *"Your company's past failures, weaponized by AI to prevent future ones."*

---

## 🙏 Acknowledgments

- [Hindsight](https://hindsight.vectorize.io) for the vector memory platform
- [Groq](https://groq.com) for blazing-fast LLM inference
- The "Nimbus Retail" synthetic dataset (28 realistic corporate decisions)

---

## 📧 Contact

Built by **Raghib** | [GitHub](https://github.com/Raghib219)

For questions or demo requests, open an issue or reach out via GitHub.

---

## Security Note

**⚠️ Never commit `.env` to git** — it's already excluded via `.gitignore`.

Each user must create their own `.env` with their own API keys. The `.env.example` file shows the structure without exposing secrets.

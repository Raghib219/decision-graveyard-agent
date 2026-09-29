"""
Persistent store for Debt Score history and Candidate Log.

- Primary:  data/store.json  (JSON file, survives restarts)
- Fallback: in-memory dicts  (used if the file can't be written)

All access is thread-safe via a threading.Lock.
Redis is optional — if REDIS_URL is set and Redis is reachable we also
publish new entries to Redis Pub/Sub so SSE clients get live pushes.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STORE_PATH = Path(os.getenv("STORE_PATH", "data/store.json"))
_lock       = threading.Lock()

# ── in-memory mirrors ─────────────────────────────────────────────────
_debt_log:      list[dict] = []
_candidate_log: list[dict] = []


def _load() -> None:
    """Load persisted data from JSON file into memory on startup."""
    global _debt_log, _candidate_log
    if not _STORE_PATH.exists():
        return
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        _debt_log      = data.get("debt_log",      [])
        _candidate_log = data.get("candidate_log", [])
    except Exception as e:
        print(f"[store] Warning: could not load {_STORE_PATH}: {e}")


def _save() -> None:
    """Persist in-memory data to JSON file."""
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"debt_log": _debt_log, "candidate_log": _candidate_log}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(_STORE_PATH)
    except Exception as e:
        print(f"[store] Warning: could not persist store: {e}")


# Load on import
_load()


# ── public API ────────────────────────────────────────────────────────

def append_debt_entry(entry: dict) -> None:
    with _lock:
        _debt_log.append(entry)
        _save()


def append_candidate_entry(entry: dict) -> None:
    with _lock:
        _candidate_log.append(entry)
        _save()


def get_debt_log() -> list[dict]:
    with _lock:
        return list(_debt_log)


def get_candidate_log() -> list[dict]:
    with _lock:
        return list(_candidate_log)


def get_debt_score_data() -> dict:
    with _lock:
        log            = list(_debt_log)
    total          = len(log)
    with_history   = [e for e in log if e.get("bank_loaded", True)]
    caught         = [e for e in with_history if e.get("caught")]
    high_caught    = [e for e in caught if e.get("high_confidence")]
    medium_caught  = [e for e in caught if e.get("medium_confidence") and not e.get("high_confidence")]
    new_territory  = [e for e in with_history if e.get("new_territory")]

    return {
        "total_queries":             total,
        "queries_with_history":      len(with_history),
        "near_repeats_caught":       len(caught),
        "high_confidence_catches":   len(high_caught),
        "medium_confidence_catches": len(medium_caught),
        "new_territory_decisions":   len(new_territory),
        "summary": (
            f"{len(caught)} near-repeat(s) caught out of "
            f"{len(with_history)} proposal(s) reviewed against decision history."
        ),
        "recent_queries": list(reversed(log[-10:])),
    }


def get_full_log_data() -> dict:
    with _lock:
        log = list(_candidate_log)
    return {
        "total_candidates_evaluated": len(log),
        "surfaced_count":  sum(1 for e in log if e.get("surfaced")),
        "rejected_count":  sum(1 for e in log if not e.get("surfaced")),
        "log": list(reversed(log)),
    }

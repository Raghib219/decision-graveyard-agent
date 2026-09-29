"""
Optional Redis cache for query results.

If REDIS_URL is not set, or Redis is unreachable, all operations
become no-ops and the pipeline runs without caching (graceful fallback).

Cache key  : "check:{sha256(proposal)}"
TTL        : CACHE_TTL_SECONDS (default 300 = 5 min)
"""

import hashlib
import json
import os
from typing import Any, Optional

REDIS_URL       = os.getenv("REDIS_URL", "")
CACHE_TTL       = int(os.getenv("CACHE_TTL_SECONDS", "300"))

_redis_client   = None
_redis_enabled  = False


def _get_redis():
    global _redis_client, _redis_enabled
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis
        r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        _redis_client  = r
        _redis_enabled = True
        print(f"[cache] Redis connected at {REDIS_URL}")
        return r
    except Exception as e:
        print(f"[cache] Redis unavailable ({e}) — running without cache")
        _redis_enabled = False
        return None


def _cache_key(proposal: str) -> str:
    h = hashlib.sha256(proposal.strip().lower().encode()).hexdigest()[:16]
    return f"check:{h}"


def get_cached(proposal: str) -> Optional[dict]:
    """Return cached result dict or None."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_cache_key(proposal))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set_cached(proposal: str, result: dict) -> None:
    """Cache a result dict with TTL."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(_cache_key(proposal), CACHE_TTL, json.dumps(result))
    except Exception:
        pass


def cache_status() -> dict:
    r = _get_redis()
    if r is None:
        return {"enabled": False, "url": REDIS_URL or "not configured"}
    try:
        info = r.info("server")
        return {
            "enabled": True,
            "url":     REDIS_URL,
            "version": info.get("redis_version", "?"),
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}

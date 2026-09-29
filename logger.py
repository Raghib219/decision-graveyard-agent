"""
Structured logging for the Decision Graveyard Agent.

Uses structlog when available, falls back to stdlib logging.
Sentry is initialised here if SENTRY_DSN is set in .env.
"""

import logging
import os
import sys

# ── Sentry (optional) ─────────────────────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=0.2,
            profiles_sample_rate=0.1,
        )
        print("[sentry] Initialised")
    except ImportError:
        print("[sentry] sentry-sdk not installed — skipping")

# ── structlog (optional) ──────────────────────────────────────────────
try:
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    def get_logger(name: str = "graveyard"):
        return structlog.get_logger(name)

except ImportError:
    # structlog not installed — use stdlib
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    def get_logger(name: str = "graveyard"):  # type: ignore[misc]
        return logging.getLogger(name)


log = get_logger("graveyard")

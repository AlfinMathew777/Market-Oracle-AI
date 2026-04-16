"""
Loguru structured logging for Market Oracle AI.

Strategy: intercept the stdlib `logging` module so all existing
`logging.getLogger(__name__)` calls in 85+ files automatically route through
Loguru — no per-file changes needed.

Sinks:
  dev/staging  → stderr, colorized, human-readable
  production   → stderr, JSON (structured, machine-parseable for Railway log drain)
  all envs     → rotating file at logs/market_oracle.log (10 MB, 7-day retention)

Usage (call once at server startup, before any loggers are used):
    from config.logging_setup import setup_logging
    setup_logging(env="production")
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


# ── Intercept handler ──────────────────────────────────────────────────────────

class _InterceptHandler(logging.Handler):
    """
    Route all stdlib logging.getLogger() calls through Loguru.

    Every module that does `logger = logging.getLogger(__name__)` will
    automatically produce structured Loguru output once this handler is
    installed via `logging.basicConfig(handlers=[_InterceptHandler()], ...)`.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Map stdlib level name to Loguru level (fallback to numeric value)
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk up the call stack to find the actual caller (skip logging internals)
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# ── Format strings ─────────────────────────────────────────────────────────────

_DEV_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
    "<level>{message}</level>"
)

# JSON production format — Loguru serialize=True emits newline-delimited JSON.
# Railway / Render log drains can ingest these directly.


# ── Public setup function ──────────────────────────────────────────────────────

def setup_logging(
    env: str = "development",
    log_level: Optional[str] = None,
    log_dir: Optional[Path] = None,
) -> None:
    """
    Configure Loguru and intercept stdlib logging.

    Call this once, early in server startup (before any `logging.getLogger`
    calls have been made). Calling it multiple times is safe — existing sinks
    are cleared before reconfiguring.

    Args:
        env:       Environment string ("development", "staging", "production").
        log_level: Override log level (default: DEBUG for dev, INFO for prod).
        log_dir:   Directory for the rotating file sink. Defaults to
                   <backend_root>/logs/. Pass None to disable file logging.
    """
    is_prod = env == "production"
    effective_level = log_level or ("DEBUG" if not is_prod else "INFO")

    # Remove any sinks configured by previous calls or Loguru's default
    logger.remove()

    # ── Stderr sink ───────────────────────────────────────────────────────────
    if is_prod:
        # Structured JSON for machine consumption
        logger.add(
            sys.stderr,
            level=effective_level,
            serialize=True,          # emit newline-delimited JSON
            backtrace=False,         # tracebacks in JSON are noisy; use Sentry
            diagnose=False,
            enqueue=True,            # thread-safe async write
        )
    else:
        # Human-readable colorized for local dev / staging
        logger.add(
            sys.stderr,
            level=effective_level,
            format=_DEV_FORMAT,
            colorize=True,
            backtrace=True,
            diagnose=True,
            enqueue=False,
        )

    # ── Rotating file sink ────────────────────────────────────────────────────
    if log_dir is not False:
        _log_dir = log_dir or (Path(__file__).parent.parent / "logs")
        try:
            _log_dir.mkdir(parents=True, exist_ok=True)
            logger.add(
                str(_log_dir / "market_oracle_{time:YYYY-MM-DD}.log"),
                level=effective_level,
                rotation="10 MB",
                retention="7 days",
                compression="gz",
                serialize=True,          # always JSON in file for grep/jq
                backtrace=True,
                diagnose=False,          # don't leak variable values to disk
                enqueue=True,
            )
        except OSError as exc:
            # Non-fatal — Railway ephemeral FS may not allow writes outside /data
            logger.warning("File sink disabled: could not create log dir {}: {}", _log_dir, exc)

    # ── Intercept stdlib logging ──────────────────────────────────────────────
    # This single call makes every `logging.getLogger(__name__)` in the codebase
    # automatically go through Loguru.
    logging.basicConfig(
        handlers=[_InterceptHandler()],
        level=0,      # pass everything through — Loguru filters by level
        force=True,   # override any existing basicConfig
    )

    # Silence noisy third-party loggers that flood output in dev
    _QUIET = [
        "uvicorn.access",       # request log is already in access format
        "httpx",
        "httpcore",
        "yfinance",
        "peewee",
        "multipart",
        "asyncio",
    ]
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    logger.info(
        "Logging configured — env={} level={} json={}",
        env,
        effective_level,
        is_prod,
    )


# ── Context binding helpers ────────────────────────────────────────────────────

def bind_request_context(request_id: str, endpoint: str) -> "logger":
    """
    Return a logger with request-scoped context fields bound.

    Usage in a FastAPI middleware or dependency:
        req_logger = bind_request_context(str(uuid4()), request.url.path)
        req_logger.info("Request started")
    """
    return logger.bind(request_id=request_id, endpoint=endpoint)


def bind_simulation_context(sim_id: str, ticker: str, event_type: str) -> "logger":
    """Return a logger with simulation-scoped context fields bound."""
    return logger.bind(sim_id=sim_id, ticker=ticker, event_type=event_type)


def bind_backtest_context(run_id: str) -> "logger":
    """Return a logger with backtest-scoped context fields bound."""
    return logger.bind(run_id=run_id)

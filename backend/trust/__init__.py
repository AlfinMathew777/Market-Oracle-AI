"""Market Oracle AI — Trust Stack.

A single gateway that turns the project's scattered validators into an explicit
5-layer, defense-in-depth trust system and proves every decision with a
tamper-evident ledger.

    Layer 1  AGENTS      generate reasoning   (upstream — produces the prediction)
    Layer 2  EVIDENCE    checks truth
    Layer 3  VALIDATION  checks quality
    Layer 4  RISK        controls action
    Layer 5  AUDIT       proves why           (hash-chained ledger + certificate)

Typical use (additive — wraps an existing prediction dict):

    from trust import get_gateway, build_context

    gateway = await get_gateway()                 # process-wide singleton
    ctx = build_context(prediction_dict)
    cert = await gateway.evaluate(ctx)

    prediction_dict["trust"] = cert.to_dict()     # attach to API response
    if not cert.is_actionable:
        prediction_dict["direction"] = "NEUTRAL"  # honour the gateway's veto
        prediction_dict["confidence"] = cert.confidence_out
"""

from __future__ import annotations

import asyncio
import logging
import os

from trust.constitution import CONSTITUTION_VERSION
from trust.contracts import (
    Decision,
    Finding,
    LayerVerdict,
    Severity,
    TrustCertificate,
    TrustContext,
)
from trust.gateway import TrustGateway
from trust.ledger import TrustLedger
from trust.reputation import ReputationStore

logger = logging.getLogger(__name__)

__all__ = [
    "TrustGateway",
    "TrustLedger",
    "ReputationStore",
    "TrustContext",
    "TrustCertificate",
    "Decision",
    "Severity",
    "Finding",
    "LayerVerdict",
    "CONSTITUTION_VERSION",
    "build_context",
    "get_gateway",
    "get_ledger",
    "get_reputation_store",
    "reset_gateway",
]

_gateway: TrustGateway | None = None
_ledger: TrustLedger | None = None
_reputation: ReputationStore | None = None
_init_lock = asyncio.Lock()


def _default_db_path() -> str:
    """Use the project DB so the ledger lives beside prediction history, else a local file."""
    try:
        import database
        path = getattr(database, "DB_PATH", None)
        if path:
            return str(path)
    except Exception as e:  # noqa: BLE001 — database module is optional in tests.
        logger.debug("project database module unavailable, using local ledger db: %s", e)
    return os.environ.get("TRUST_LEDGER_DB", "trust_ledger.db")


async def get_ledger(db_path: str | None = None) -> TrustLedger:
    """Return the process-wide hash-chained ledger, initialising its schema once.

    Shared by the gateway (certificates) and the attribution loop so both write
    to one tamper-evident chain.
    """
    global _ledger
    async with _init_lock:
        if _ledger is None:
            _ledger = TrustLedger(db_path or _default_db_path())
            await _ledger.init()
        return _ledger


async def get_reputation_store(db_path: str | None = None) -> ReputationStore:
    """Return the process-wide canonical reputation store, schema-initialised once.

    Empty in Piece 1 — reads only (source + (archetype, regime) records, prior,
    gate, fallback). Piece 2 layers the outcome-fed update rule on top; the single
    store keeps the future I4 input-trust layer reading one keyspace, not a fork.
    Lives in the project DB beside prediction history (same path as the ledger).
    """
    global _reputation
    async with _init_lock:
        if _reputation is None:
            _reputation = ReputationStore(db_path or _default_db_path())
            await _reputation.init()
        return _reputation


async def get_gateway(db_path: str | None = None) -> TrustGateway:
    """Return the process-wide gateway, initialising the ledger schema once."""
    global _gateway
    if _gateway is None:
        ledger = await get_ledger(db_path)
        async with _init_lock:
            if _gateway is None:
                _gateway = TrustGateway(ledger)
                logger.info("Trust gateway initialised (constitution %s)", CONSTITUTION_VERSION)
    return _gateway


def reset_gateway() -> None:
    """Drop the singletons — used by tests to bind a fresh ledger path."""
    global _gateway, _ledger, _reputation
    _gateway = None
    _ledger = None
    _reputation = None


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_context(prediction: dict) -> TrustContext:
    """Normalise a raw prediction dict into a TrustContext the layers can read.

    Tolerant of the project's several prediction shapes (test_core, reasoning
    synthesizer, merged pipeline) — pulls fields by their common aliases and
    falls back to safe, conservative defaults.
    """
    judge = prediction.get("judge_result") or prediction.get("causal_chain") or {}
    votes = prediction.get("agent_votes") or {
        "bull": prediction.get("n_bull", prediction.get("bullish", 0)),
        "bear": prediction.get("n_bear", prediction.get("bearish", 0)),
        "neut": prediction.get("n_neut", prediction.get("neutral", 0)),
    }
    catalyst = (
        prediction.get("catalyst")
        or prediction.get("trigger_event")
        or (judge.get("trigger_event") if isinstance(judge, dict) else "")
        or prediction.get("primary_reason")
        or ""
    )
    return TrustContext(
        ticker=str(prediction.get("ticker") or prediction.get("symbol") or "UNKNOWN"),
        direction=str(prediction.get("direction") or "NEUTRAL").upper(),
        confidence=_f(prediction.get("confidence"), 0.0),
        signal_order=str(prediction.get("signal_order") or "primary").lower(),
        catalyst=str(catalyst),
        agent_votes=votes if isinstance(votes, dict) else {},
        mc_stability=_f(prediction.get("mc_stability", prediction.get("monte_carlo_stability")), 1.0),
        historical_accuracy=_f(prediction.get("historical_accuracy"), 1.0),
        judge_result=judge if isinstance(judge, dict) else {},
        market_context=prediction.get("market_context") or {},
        data_feeds=prediction.get("data_feeds") or {},
        paper_mode=bool(prediction.get("paper_mode", True)),
        raw=prediction,
    )

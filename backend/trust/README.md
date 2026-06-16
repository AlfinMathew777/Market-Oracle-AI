# Trust Stack — Constitutional Defense-in-Depth

The trust layer that makes Market Oracle AI defensible at the **system level**, not
just the model level. No single component is trusted; a prediction only becomes an
actionable signal if it survives five independent layers, and every decision is
provable after the fact.

## The model we copied

Three battle-tested designs from world-class systems, fused:

| Source | Borrowed idea |
|--------|---------------|
| **Anthropic — Constitutional AI** | A written, versioned [`constitution.py`](constitution.py). Every block/warning cites an Article. Trust is explicit and explainable, not emergent. |
| **Aviation / NASA — defense-in-depth ("Swiss cheese")** | Five independent layers, each able to **veto**. **Fail-closed**: a layer that cannot complete its check blocks the signal. |
| **Finance / crypto — tamper-evident audit** | A hash-chained [`ledger.py`](ledger.py). The track record cannot be silently edited — an auditor can re-walk the chain and prove integrity. |

## The five layers

```
Layer 1  AGENTS      generate reasoning   ← the 45-agent swarm + synthesizer (upstream)
Layer 2  EVIDENCE    checks truth         ← layers/evidence.py
Layer 3  VALIDATION  checks quality       ← layers/validation.py
Layer 4  RISK        controls action      ← layers/risk.py
Layer 5  AUDIT       proves why           ← layers/audit.py + ledger.py
```

Layers 2-4 each return a `LayerVerdict` (pass/score/confidence-cap/findings). The
[`gateway.py`](gateway.py) aggregates them into **one** `TrustCertificate` — a single
trust score (0-100), a single decision, the tightest confidence cap — then Layer 5
records it to the ledger **before** the signal is acted on.

### What each layer enforces (Constitution articles)

- **Evidence (E1-E5):** grounded catalyst, substantiated causal chain, geographic
  truth (iron ore = Lombok not Malacca), fresh data, no invented facts. *Wraps the
  existing `catalyst_validator`, `causal_chain_validator`, and feed-health logic.*
- **Validation (V1-V5):** confidence floor, agent consensus strength, Monte Carlo
  stability, per-order confidence caps (75/55/35, absolute 85), track-record awareness.
- **Risk (R1-R4):** kill-switch supremacy, fail-closed, no advice framing (AFSL),
  NEUTRAL is never actionable.
- **Audit (A1-A2):** tamper-evident record, full replayability.

## Decisions

| Decision | Meaning |
|----------|---------|
| `APPROVE` | Clean pass — publish as-is. |
| `APPROVE_DEGRADED` | Publish, but confidence was capped or a non-fatal concern fired. |
| `BLOCK` | A layer vetoed, trust score too low, NEUTRAL, or confidence below floor. Not actionable. |

Any veto → BLOCK. A gateway/ledger failure → BLOCK. **Absence of a green light is a red light.**

## Usage

```python
from trust import get_gateway, build_context

gateway = await get_gateway()                 # process-wide singleton
cert = await gateway.evaluate(build_context(prediction_dict))

prediction_dict["trust"] = cert.to_dict()
if not cert.is_actionable:
    prediction_dict["direction"] = "NEUTRAL"
    prediction_dict["confidence"] = cert.confidence_out
```

For the reasoning synthesizer, use the adapter:

```python
from trust.integration import certify_reasoning
cert = await certify_reasoning(reasoning_output, news_headline=headline)
```

Wired live into `POST /api/reasoning/synthesize` — the response now carries a `trust`
object, and trade-execution + WebSocket broadcast are suppressed when the gateway blocks.

## Verifying the ledger

```python
intact, first_broken_seq = await gateway._ledger.verify_chain()
# intact is False and first_broken_seq pinpoints the tampered entry.
```

## Why this is "system-level" trust

Individual validators already existed — but scattered, with no single verdict and no
proof. This stack makes trust a **property of the system**: one gate every prediction
must pass, one explainable score, and a mathematically defensible history. The value of
a prediction platform is its track record; a hash-chained ledger is what makes that
track record impossible to quietly rewrite.

## Files

| File | Role |
|------|------|
| `constitution.py` | Versioned rules + numeric thresholds (single source of truth). |
| `contracts.py` | Frozen dataclasses: `Finding`, `LayerVerdict`, `TrustContext`, `TrustCertificate`. |
| `layers/base.py` | Timing + fail-closed wrapper shared by all layers. |
| `layers/{evidence,validation,risk,audit}.py` | The four checking layers. |
| `ledger.py` | Hash-chained, tamper-evident SQLite audit log. |
| `gateway.py` | Orchestrator — runs layers, issues the certificate. |
| `integration.py` | Adapters from project prediction shapes → `TrustContext`. |
| `../tests/test_trust_stack.py` | 13 tests: per-layer vetoes, decisions, capping, tamper detection, fail-closed. |

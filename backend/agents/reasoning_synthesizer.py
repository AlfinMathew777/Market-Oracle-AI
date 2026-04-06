"""
Reasoning Synthesizer Agent
---------------------------
Final-stage agent that aggregates specialist agent votes and produces
structured, explainable stock predictions with causal reasoning.

Sits at the END of the pipeline — called after all specialist agents have voted.
Uses LLMRouter (call_primary) for structured report generation.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from llm_router import LLMRouter, parse_json_response
from models.reasoning_output import (
    Direction,
    ImpactType,
    ReasoningOutput,
    Recommendation,
    Stability,
    Strength,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an advanced financial reasoning AI embedded inside a multi-agent market intelligence system.
Your task is to analyze a given news event and produce a structured, explainable prediction for a specific ASX stock.
You MUST follow a strict 8-step reasoning pipeline and output ONLY valid JSON.

---

## STEP 1 — EVENT CLASSIFICATION

Classify the news into ONE of:
1. **Direct Impact** — affects company revenue, costs, regulation, or operations directly
2. **Indirect Impact** — macro, geopolitical, or supply chain effects
3. **Noise / Low Relevance** — no meaningful connection to the company

Assign:
* **Impact Strength:** Low / Medium / High
* **Affected Domains:** (e.g., oil, iron_ore, currency, demand, logistics, regulation, earnings)

---

## STEP 2 — CAUSAL CHAIN ANALYSIS

Build: **Event → Intermediate Effects → Company-Level Impact**

CRITICAL — GEOGRAPHY CHECK:
* Australian iron ore ships via **Lombok/Makassar Strait**, NOT Malacca Strait
* Do NOT apply incorrect geographic assumptions

Separate into:
* **Cost Impact** — operating costs
* **Revenue Impact** — sales/pricing power
* **Demand Impact** — customer demand
* **Sentiment Impact** — investor perception

---

## STEP 3 — IMPACT TIMELINE

For EACH of [Immediate (0-7d), Short-term (1-4w), Medium-term (1-3m), Long-term (3m+)]:
* Direction: Bullish / Bearish / Neutral
* Confidence: Low / Medium / High
* Reasoning

---

## STEP 4 — MARKET CONTEXT

Combine news with current signals. Determine:
* **Reinforces trend** — aligns with momentum
* **Contradicts trend** — opposes current direction
* **No strong effect** — mixed/unclear

---

## STEP 5 — CONSENSUS WEIGHTING

Analyze agent vote distribution:
* Strongly aligned (>70%) → increase confidence
* Highly split (<70%) → reduce confidence

Output:
* **Consensus Strength Score:** 0–100
* **Signal Stability:** Stable (>70% agreement) or Fragile (<70%)

---

## STEP 6 — FINAL DECISION

1. **Direction:** Bullish / Bearish / Neutral
2. **Recommendation:** BUY / SELL / HOLD / WAIT
3. **Confidence Score:** 0–100
   * 80–100: Direct regulatory/earnings impact with clear precedent
   * 60–79: Strong causal chain, 2+ confirming signals
   * 40–59: Plausible but conflicting signals
   * 20–39: Speculative, high uncertainty
   * 0–19: Noise
4. **Risk Level:** Low / Medium / High

---

## STEP 7 — RISK ANALYSIS

List key risks that could invalidate the prediction.

---

## STEP 8 — CONTRARIAN INSIGHT

Identify market overreaction opportunities, or output null if none.

---

## OUTPUT — STRICT JSON ONLY

Output ONLY this JSON structure (no markdown, no extra text):

{
  "stock_ticker": "BHP.AX",
  "event_classification": {
    "type": "Indirect Impact",
    "strength": "Medium",
    "domains": ["oil", "geopolitics", "logistics"]
  },
  "causal_chain": {
    "summary": "Event → effects → company impact",
    "cost_impact": "...",
    "revenue_impact": "...",
    "demand_impact": "...",
    "sentiment_impact": "..."
  },
  "impact_timeline": [
    {"timeframe": "Immediate", "direction": "Neutral", "confidence": "Medium", "reason": "..."},
    {"timeframe": "Short-term", "direction": "Neutral", "confidence": "Medium", "reason": "..."},
    {"timeframe": "Medium-term", "direction": "Neutral", "confidence": "Low", "reason": "..."},
    {"timeframe": "Long-term", "direction": "Neutral", "confidence": "Low", "reason": "..."}
  ],
  "market_context": {
    "alignment": "No strong effect",
    "commodity_signals": {},
    "currency_signal": null,
    "technical_summary": null,
    "notes": "..."
  },
  "consensus_analysis": {
    "bullish": 0,
    "bearish": 0,
    "neutral": 0,
    "strength_score": 0,
    "stability": "Fragile"
  },
  "final_decision": {
    "direction": "Neutral",
    "recommendation": "WAIT",
    "confidence_score": 0,
    "risk_level": "Medium"
  },
  "risk_factors": ["..."],
  "contrarian_view": null,
  "data_provenance": {}
}

CRITICAL RULES:
1. Do NOT guess — base all reasoning on causal logic from the provided data
2. Do NOT hallucinate market data — use ONLY the values provided in the input
3. If uncertainty is high → output NEUTRAL or WAIT
4. Australian commodities ship via Lombok/Makassar, NOT Malacca
5. Output ONLY valid JSON — no markdown, no text outside the JSON structure
"""


def _build_user_prompt(
    stock_ticker: str,
    news_headline: str,
    news_summary: str,
    market_signals: Dict[str, Any],
    agent_votes: Dict[str, int],
    data_provenance: Dict[str, Any],
) -> str:
    import json

    total = sum(agent_votes.values())
    return f"""## ANALYSIS REQUEST

**Target Stock:** {stock_ticker}

### NEWS EVENT
**Headline:** {news_headline}
**Summary:** {news_summary}

### MARKET SIGNALS (validated data with provenance)
```json
{json.dumps(market_signals, indent=2)}
```

**Data Sources:**
```json
{json.dumps(data_provenance, indent=2)}
```

### SPECIALIST AGENT CONSENSUS ({total} agents)
* Bullish: {agent_votes.get('bullish', 0)}
* Bearish: {agent_votes.get('bearish', 0)}
* Neutral: {agent_votes.get('neutral', 0)}

Execute the 8-step reasoning pipeline and output your analysis as valid JSON only."""


def _fallback_output(
    stock_ticker: str,
    agent_votes: Dict[str, int],
    error_message: str,
) -> ReasoningOutput:
    """Safe fallback when the LLM response cannot be parsed or validated."""
    return ReasoningOutput(
        stock_ticker=stock_ticker,
        event_classification={
            "type": ImpactType.NOISE,
            "strength": Strength.LOW,
            "domains": ["error_fallback"],
        },
        causal_chain={
            "summary": f"Reasoning pipeline error: {error_message}",
            "cost_impact": "Unable to assess",
            "revenue_impact": "Unable to assess",
            "demand_impact": "Unable to assess",
            "sentiment_impact": "Unable to assess",
        },
        impact_timeline=[
            {
                "timeframe": "Immediate",
                "direction": Direction.NEUTRAL,
                "confidence": Strength.LOW,
                "reason": "Reasoning error — defaulting to neutral",
            }
        ],
        market_context={
            "alignment": "No strong effect",
            "notes": f"Error in reasoning pipeline: {error_message}",
        },
        consensus_analysis={
            "bullish": agent_votes.get("bullish", 0),
            "bearish": agent_votes.get("bearish", 0),
            "neutral": agent_votes.get("neutral", 0),
            "strength_score": 0,
            "stability": Stability.FRAGILE,
        },
        final_decision={
            "direction": Direction.NEUTRAL,
            "recommendation": Recommendation.WAIT,
            "confidence_score": 0,
            "risk_level": Strength.HIGH,
        },
        risk_factors=[
            "Reasoning pipeline failed — do not trade on this signal",
            f"Error: {error_message}",
        ],
        contrarian_view=None,
        data_provenance={"error": error_message},
    )


class ReasoningSynthesizer:
    """
    Final-stage reasoning agent producing structured stock predictions.

    Aggregates specialist agent votes with news and market data via LLMRouter.
    Supports optional memory injection to improve predictions from history.
    """

    # Domain keywords for extracting event domains from news text
    _DOMAIN_KEYWORDS: Dict[str, List[str]] = {
        "iron_ore":   ["iron ore", "iron-ore", "steel", "bhp", "rio", "fortescue", "fmg"],
        "oil":        ["oil", "crude", "brent", "opec", "petroleum", "energy", "lng"],
        "gold":       ["gold", "precious metal", "bullion", "silver"],
        "currency":   ["aud", "usd", "dollar", "forex", "currency", "exchange rate"],
        "china":      ["china", "chinese", "beijing", "shanghai", "xi jinping", "prc"],
        "geopolitics":["war", "conflict", "sanctions", "military", "tension", "attack", "houthi"],
        "logistics":  ["shipping", "freight", "port", "supply chain", "logistics", "strait"],
        "regulation": ["regulation", "policy", "government", "legislation", "tax", "rba"],
        "earnings":   ["earnings", "profit", "revenue", "quarterly", "annual report", "dividend"],
        "demand":     ["demand", "consumption", "sales", "orders", "stimulus", "infrastructure"],
    }

    def __init__(self, llm_router: LLMRouter, prediction_memory=None) -> None:
        self._router = llm_router
        self._memory = prediction_memory  # Optional PredictionMemory instance

    async def synthesize(
        self,
        stock_ticker: str,
        news_headline: str,
        news_summary: str,
        market_signals: Dict[str, Any],
        agent_votes: Dict[str, int],
        data_provenance: Dict[str, Any],
        inject_memory: bool = True,
    ) -> ReasoningOutput:
        """
        Run the full 8-step reasoning pipeline and return a validated prediction.

        Args:
            stock_ticker: ASX ticker (e.g., "BHP.AX")
            news_headline: News event headline
            news_summary: News event description
            market_signals: Commodity prices, technicals, macro indicators
            agent_votes: {"bullish": n, "bearish": n, "neutral": n}
            data_provenance: Source + timestamp for each market data point
            inject_memory: Whether to prepend historical memory context to the prompt

        Returns:
            ReasoningOutput: Validated structured prediction (memory_context attached)
        """
        user_prompt = _build_user_prompt(
            stock_ticker=stock_ticker,
            news_headline=news_headline,
            news_summary=news_summary,
            market_signals=market_signals,
            agent_votes=agent_votes,
            data_provenance=data_provenance,
        )

        # ── Memory injection ───────────────────────────────────────────────────
        memory_context: Optional[Dict[str, Any]] = None
        if inject_memory and self._memory is not None:
            try:
                domains = self._extract_domains(news_headline, news_summary)
                initial_direction = self._estimate_direction(agent_votes)
                memory_context = await self._memory.get_memory_context(
                    stock_ticker=stock_ticker,
                    event_domains=domains,
                    direction=initial_direction,
                    stated_confidence=50,
                )
                if memory_context and memory_context.get("has_memory"):
                    memory_prompt = memory_context.get("memory_prompt", "")
                    if memory_prompt:
                        user_prompt = user_prompt + "\n\n" + memory_prompt
                        logger.info("Memory injected for %s", stock_ticker)
            except Exception as exc:
                logger.warning("Memory injection skipped (%s): %s", stock_ticker, exc)

        # ── LLM call ──────────────────────────────────────────────────────────
        try:
            raw = await self._router.call_primary(
                system_message=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                session_id=f"reasoning:{stock_ticker}",
            )
            logger.info("Reasoning raw output for %s: %.300s…", stock_ticker, raw)

            parsed = parse_json_response(raw)
            result = ReasoningOutput(**parsed)
            result.memory_context = memory_context
            return result

        except ValidationError as exc:
            logger.error("Pydantic validation error in reasoning output: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

        except ValueError as exc:
            logger.error("JSON parse error in reasoning output: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

        except Exception as exc:
            logger.error("Reasoning synthesizer error: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

    # ── helpers ────────────────────────────────────────────────────────────────

    def _extract_domains(self, headline: str, summary: str) -> List[str]:
        """Heuristically extract affected domains from news text."""
        text = f"{headline} {summary}".lower()
        return [
            domain
            for domain, keywords in self._DOMAIN_KEYWORDS.items()
            if any(kw in text for kw in keywords)
        ] or ["general"]

    def _estimate_direction(self, agent_votes: Dict[str, int]) -> str:
        """Estimate likely direction from the agent vote split."""
        bullish = agent_votes.get("bullish", 0)
        bearish = agent_votes.get("bearish", 0)
        if bullish > bearish * 1.5:
            return "Bullish"
        if bearish > bullish * 1.5:
            return "Bearish"
        return "Neutral"

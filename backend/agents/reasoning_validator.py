"""
Reasoning Validator
-------------------
Validates causal chain logic before output to catch weak or geographically
incorrect reasoning. Runs synchronously after LLM response parsing.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ReasoningValidator:
    """Validates reasoning quality and flags weak or geographically incorrect causal logic."""

    # (trigger phrase in summary, affected domain key, human-readable explanation)
    _INVALID_CAUSATIONS: List[Tuple[str, str, str]] = [
        ("sideways", "cost", "Sideways price trend is not a cost driver"),
        ("rsi", "revenue", "RSI is a technical indicator, not a revenue driver"),
        ("rsi", "demand", "RSI does not affect real-world demand"),
        ("52-week", "demand", "Distance from 52-week high is not a demand signal"),
        ("macd", "demand", "MACD does not affect real-world demand"),
        ("trading volume", "cost", "Trading volume does not affect company operating costs"),
    ]

    _VALID_COST_DRIVERS: List[str] = [
        "oil", "energy", "fuel", "shipping", "freight", "labour", "labor",
        "wages", "electricity", "raw material", "input cost", "diesel", "transport",
        "logistics cost",
    ]

    _VALID_REVENUE_DRIVERS: List[str] = [
        "iron ore", "commodity price", "demand", "sales", "contract", "customer",
        "production", "ore price", "spot price", "benchmark price",
    ]

    _VALID_DEMAND_DRIVERS: List[str] = [
        "china", "steel", "construction", "infrastructure", "property",
        "manufacturing", "pmi", "gdp", "consumption", "orders", "stimulus",
        "industrial output",
    ]

    # Tickers subject to Australian iron ore geographic rules
    _IRON_ORE_TICKERS = {"BHP.AX", "RIO.AX", "FMG.AX", "MIN.AX"}

    _GEO_ERRORS: List[Tuple[str, str, str]] = [
        # (strait keyword, co-occurring keyword, error message)
        (
            "malacca",
            "iron ore",
            "Geographic error: Australian iron ore ships via Lombok/Makassar Strait, NOT Malacca. "
            "Malacca disruption affects Middle East crude → Asia routes, not Australia → China iron ore.",
        ),
        (
            "suez",
            "iron ore",
            "Geographic error: Suez Canal is not on the Australia → China iron ore trade route.",
        ),
        (
            "panama",
            "iron ore",
            "Geographic error: Panama Canal is irrelevant to Australia → Asia iron ore trade.",
        ),
    ]

    _NEUTRAL_TERMS = frozenset(
        ["neutral", "no impact", "no direct", "unchanged", "unaffected", "minimal", "n/a"]
    )

    # Vague filler phrases the LLM tends to fall back on
    _GENERIC_PHRASES: List[str] = [
        # Original set
        "does not have significant impact",
        "due to neutral context",
        "due to the neutral market context",
        "remains neutral due to",
        "no clear evidence",
        "assumed neutral",
        "lack of clear",
        "does not directly impact",
        "no significant impact",
        "unclear at this time",
        "no meaningful impact",
        "neutral impact",
        "minimal impact at this time",
        # Hedging / weasel language
        "may impact",
        "could potentially",
        "might affect",
        "appears to",
        "seems to indicate",
        "signals suggest",
        "news suggests",
        # Macro filler (no named mechanism)
        "general market conditions",
        "current market environment",
        "prevailing conditions",
        "overall sentiment",
        "broader market",
        # Demand weasel phrases
        "imply demand growth",
        "imply demand decline",
        "critical news signals",
        # "may not / may indirectly" hedging
        "may not directly impact",
        "may not directly affect",
        "may indirectly affect",
        "may indirectly impact",
        "may or may not",
        # "Does not" filler
        "does not directly signal",
        "does not clearly indicate",
        "does not provide clear",
        "do not signal a clear",
        "do not indicate a clear",
        "do not provide clear",
        # "Due to" vague causation
        "due to changes in",
        "due to global demand",
        "due to market conditions",
        "due to current conditions",
        "due to the current",
        "due to ongoing",
        # Empty impact assertions
        "no direct impact",
        "no immediate impact",
        "no material impact",
        "no clear impact",
        "neutral market indicators",
        "neutral market context",
        "neutral market conditions",
        # Weasel modal phrases
        "it is possible that",
        "there is potential for",
        "this could lead to",
        "this might result in",
        "potentially affecting",
        "possibly impacting",
        # Lazy context-based conclusions
        "based on current conditions",
        "given the current market",
        "in the current environment",
        "under current circumstances",
        # Vague geopolitical filler
        "geopolitical event may",
        "geopolitical tensions may",
        "geopolitical factors",
        "global tensions",
        # "unlikely/significantly" patterns
        "unlikely to affect",
        "unlikely to impact",
        "will not significantly impact",
        "will not significantly affect",
        "no significant changes",
        "no significant market sentiment",
        "no significant news",
        # "Stable/Neutral" without data
        "price is stable",
        "demand is neutral",
        "sentiment is neutral",
        "outlook is neutral",
        # "Indicating" without data
        "indicating no significant",
        "indicating no change",
        "indicating stability",
        # Empty qualifiers
        "at this time",
        "at present",
        "currently stable",
        "remains stable",
        "remains neutral",
        # Missing-data cop-outs
        "there are no significant",
        "as there are no",
        "since there are no",
    ]

    # Suspicious geopolitical word combinations that suggest hallucination
    _SUSPICIOUS_RISK_COMBOS: List[tuple] = [
        ("ukraine", "syria"),
        ("north korea", "nato"),
        ("iran", "australia", "directly"),
    ]

    # Vague phrases that make risk factors useless
    _VAGUE_RISK_PHRASES: List[str] = [
        "geopolitical uncertainty",
        "market volatility",
        "various factors",
        "multiple risks",
        "general uncertainty",
        "economic conditions",
        "global tensions",
        "unforeseen events",
    ]

    # Terms indicating bullish demand/sentiment signal in causal chain text
    _BULLISH_TERMS: List[str] = [
        "positive", "growth", "rising", "increase", "expanding", "improving",
        "strengthening", "recovery", "strong demand", "supportive", "upturn",
        "upside", "bullish", "acceleration", "rebound", "surge", "elevated demand",
    ]

    # Terms indicating bearish demand/sentiment signal in causal chain text
    _BEARISH_TERMS: List[str] = [
        "negative", "decline", "falling", "decrease", "contracting", "weakening",
        "dropping", "stress", "weak demand", "downturn", "downside", "bearish",
        "deteriorating", "softer", "slowdown", "compression", "headwind",
    ]

    def check_logical_consistency(
        self,
        causal_chain: Dict[str, Any],
        final_decision: Dict[str, Any],
    ) -> List[str]:
        """
        Flag when demand/sentiment signals strongly contradict the final decision.

        E.g. three bullish demand signals but a NEUTRAL or BEARISH final direction
        suggests the LLM ignored its own causal analysis.
        """
        issues: List[str] = []

        demand = (causal_chain.get("demand_impact") or "").lower()
        sentiment = (causal_chain.get("sentiment_impact") or "").lower()
        summary = (causal_chain.get("summary") or "").lower()
        combined = f"{demand} {sentiment} {summary}"

        final_dir = (final_decision.get("direction") or "neutral").lower()

        bull_count = sum(1 for t in self._BULLISH_TERMS if t in combined)
        bear_count = sum(1 for t in self._BEARISH_TERMS if t in combined)

        # Strong bullish signals → BEARISH final
        if bull_count >= 2 and bear_count < 2 and final_dir == "bearish":
            issues.append(
                f"Logical inconsistency: demand/sentiment signals are bullish "
                f"({bull_count} positive indicators) but final direction is BEARISH — "
                "re-examine consensus weighting"
            )

        # Strong bearish signals → BULLISH final
        if bear_count >= 2 and bull_count < 2 and final_dir == "bullish":
            issues.append(
                f"Logical inconsistency: demand/sentiment signals are bearish "
                f"({bear_count} negative indicators) but final direction is BULLISH — "
                "re-examine consensus weighting"
            )

        # Overwhelmingly bullish with NEUTRAL final
        if bull_count >= 3 and bear_count == 0 and final_dir == "neutral":
            issues.append(
                f"Logical inconsistency: {bull_count} bullish indicators in "
                "demand/sentiment but final direction is NEUTRAL — "
                "check if consensus override is justified"
            )

        # Overwhelmingly bearish with NEUTRAL final
        if bear_count >= 3 and bull_count == 0 and final_dir == "neutral":
            issues.append(
                f"Logical inconsistency: {bear_count} bearish indicators in "
                "demand/sentiment but final direction is NEUTRAL — "
                "check if consensus override is justified"
            )

        return issues

    def check_data_citations(
        self,
        causal_chain: Dict[str, Any],
        market_signals: Dict[str, Any],
    ) -> List[str]:
        """
        Check that causal chain fields cite the actual numbers from market_signals.

        Returns advisory issues (informational — does not block the output).
        """
        issues: List[str] = []
        iron_ore = market_signals.get("iron_ore_62fe") or market_signals.get("iron_ore_price")
        rsi = market_signals.get("rsi_14")

        revenue = (causal_chain.get("revenue_impact") or causal_chain.get("revenue_signal") or "")
        if iron_ore and "iron ore" in revenue.lower():
            # Mentions iron ore but no dollar figure
            if not re.search(r"\$\d{2,3}", revenue):
                issues.append(
                    f"revenue_impact mentions iron ore but omits the price "
                    f"(${iron_ore}/t available) — cite the actual level"
                )

        sentiment = (causal_chain.get("sentiment_impact") or causal_chain.get("sentiment_signal") or "")
        if rsi is not None and len(sentiment) > 20:
            if not re.search(r"rsi.{0,10}\d{2}", sentiment.lower()):
                issues.append(
                    f"sentiment_impact lacks RSI citation "
                    f"(RSI={rsi} available) — cite the actual value"
                )

        # Flag any field with >30 chars that contains zero digits (pure prose, no data)
        for field in ("cost_impact", "revenue_impact", "demand_impact", "sentiment_impact"):
            content = causal_chain.get(field) or ""
            if len(content) > 30 and not re.search(r"\d", content):
                issues.append(
                    f"{field}: contains only prose with no numeric data — "
                    f"cite at least one specific number"
                )

        return issues

    def validate_risk_factors(
        self,
        risk_factors: List[str],
        stock_ticker: str = "",
    ) -> List[str]:
        """
        Validate risk factors for hallucinations, vagueness, and sector mismatches.

        Returns list of cleaned risk factors with hallucinated/irrelevant items removed.
        Logs a warning for each item dropped.
        """
        from utils.sector_classifier import get_sector_config
        cfg = get_sector_config(stock_ticker) if stock_ticker else None
        irrelevant_kws = cfg.irrelevant_signal_keywords if cfg else []

        cleaned: List[str] = []
        for risk in (risk_factors or []):
            risk_lower = risk.lower()

            # Drop hallucinated geopolitical combinations
            if any(
                all(word in risk_lower for word in combo)
                for combo in self._SUSPICIOUS_RISK_COMBOS
            ):
                logger.warning(
                    "Dropping hallucinated risk factor [%s]: %.80s", stock_ticker, risk
                )
                continue

            # Drop sector-irrelevant risks that claim impact on the company
            if irrelevant_kws and any(
                kw in risk_lower for kw in irrelevant_kws
            ) and any(
                word in risk_lower for word in ("impact", "affect", "influence", "pressure", "weigh")
            ):
                logger.warning(
                    "Dropping sector-irrelevant risk factor [%s]: %.80s", stock_ticker, risk
                )
                continue

            # Drop purely vague risks with no named threshold
            if any(phrase in risk_lower for phrase in self._VAGUE_RISK_PHRASES) and not any(
                c.isdigit() for c in risk  # No number = no named threshold
            ):
                logger.warning(
                    "Dropping vague risk factor [%s]: %.80s", stock_ticker, risk
                )
                continue

            cleaned.append(risk)

        # Always return at least one risk factor
        if not cleaned:
            cleaned = [f"{stock_ticker or 'Stock'}: standard market and liquidity risk"]

        return cleaned

    def _check_generic_language(self, causal_chain: Dict[str, Any]) -> List[str]:
        """Flag fields that contain vague filler language instead of specific mechanisms."""
        issues: List[str] = []
        fields = {
            "cost_impact":     causal_chain.get("cost_impact") or "",
            "revenue_impact":  causal_chain.get("revenue_impact") or "",
            "demand_impact":   causal_chain.get("demand_impact") or "",
            "sentiment_impact": causal_chain.get("sentiment_impact") or "",
        }
        for field_name, content in fields.items():
            lower = content.lower()
            for phrase in self._GENERIC_PHRASES:
                if phrase in lower:
                    issues.append(
                        f"Generic language in {field_name}: \"{phrase}\" — "
                        f"must state the specific mechanism or write NO DATA"
                    )
                    break  # one issue per field is enough
        return issues

    def validate_causal_chain(
        self,
        causal_chain: Dict[str, Any],
        stock_ticker: str = "",
        final_decision: Optional[Dict[str, Any]] = None,
        market_signals: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validate a causal chain dict for logical and geographic consistency.

        Args:
            causal_chain: dict with keys: summary, cost_impact, revenue_impact,
                          demand_impact, sentiment_impact
            stock_ticker: ASX ticker (used for geographic rule checks)
            final_decision: dict with "direction" key (used for consistency check)

        Returns:
            (is_valid: bool, issues: List[str])
        """
        issues: List[str] = []

        summary = (causal_chain.get("summary") or "").lower()
        cost = (causal_chain.get("cost_impact") or "").lower()
        revenue = (causal_chain.get("revenue_impact") or "").lower()
        demand = (causal_chain.get("demand_impact") or "").lower()

        domain_texts = {"cost": cost, "revenue": revenue, "demand": demand}

        # ── Check invalid technical-indicator causations ─────────────────────
        for trigger, domain, explanation in self._INVALID_CAUSATIONS:
            text = domain_texts.get(domain, "")
            if trigger in summary and trigger in text:
                issues.append(f"Weak logic: {explanation}")

        # ── Check that asserted cost impacts name a valid cost driver ────────
        if cost and not any(t in cost for t in self._NEUTRAL_TERMS):
            if not any(d in cost for d in self._VALID_COST_DRIVERS):
                issues.append(
                    "Cost impact asserted but no recognised cost driver found "
                    "(expected: oil/fuel/freight/shipping/labour/electricity)"
                )

        # ── Check geographic errors for iron ore tickers ─────────────────────
        if stock_ticker in self._IRON_ORE_TICKERS:
            for strait, co_keyword, message in self._GEO_ERRORS:
                if strait in summary and co_keyword in summary:
                    issues.append(message)

        # ── Generic language check ───────────────────────────────────────────
        issues.extend(self._check_generic_language(causal_chain))

        # ── Data citation check (advisory) ───────────────────────────────────
        if market_signals:
            issues.extend(self.check_data_citations(causal_chain, market_signals))

        # ── Logical consistency check ─────────────────────────────────────────
        if final_decision is not None:
            issues.extend(self.check_logical_consistency(causal_chain, final_decision))

        is_valid = len(issues) == 0
        if issues:
            logger.warning("Causal chain issues [%s]: %s", stock_ticker, issues)

        return is_valid, issues


# Module-level singleton — safe to share across requests (stateless)
reasoning_validator = ReasoningValidator()

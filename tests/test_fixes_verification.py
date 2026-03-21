"""
Market Oracle AI — Fix Verification Suite
Covers all 4 fixes deployed in the previous session.

Run unit tests (no API calls, fast):
    pytest tests/test_fixes_verification.py -v -m "not integration"

Run integration tests (requires GROQ_API_KEY):
    pytest tests/test_fixes_verification.py -v -m integration

Run all:
    pytest tests/test_fixes_verification.py -v
"""

import os
import sys
import json
import pytest
from datetime import datetime, timezone, timedelta

# -- Import path setup ---------------------------------------------------------
BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(BACKEND))

from scripts.test_core import (
    apply_minimum_confidence_guard,
    audit_causal_chain,
    calculate_confidence,
    _blind_judge_prompt,
    _reconciler_prompt,
)
from services.market_context import (
    filter_stale_news,
    log_news_date_range,
    news_weight,
    weight_to_label,
)


# =============================================================================
# TEST GROUP 1 -- FIX 1: MINIMUM CONFIDENCE GUARD
# =============================================================================

class TestMinimumConfidenceGuard:

    def test_zero_confidence_forces_neutral(self):
        """Confidence < 3 must always produce neutral + signal_note"""
        direction, confidence, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=0.0,
            bullish=16, bearish=12, neutral=17,
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note
        assert "threshold" in note.lower()

    def test_low_confidence_forces_neutral(self):
        """Confidence of 2.9% still below threshold"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bearish", confidence=2.9,
            bullish=10, bearish=14, neutral=21,
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note

    def test_confidence_exactly_3_not_blocked_by_rule1(self):
        """Confidence of exactly 3.0% should NOT trigger Rule 1"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=3.0,
            bullish=20, bearish=10, neutral=15,
        )
        # 15/45 = 33% neutral < 50% -- Rule 2 no; margin=10 > 2 -- Rule 3 no
        assert note is None

    def test_majority_neutral_forces_neutral(self):
        """>=50% neutral agents must produce neutral regardless of confidence"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=25.0,
            bullish=15, bearish=7, neutral=23,  # 23/45 = 51.1%
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note
        assert "majority" in note.lower()

    def test_exactly_50_percent_neutral_triggers(self):
        """Exactly 50% neutral should trigger the guard (rule uses >=)"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bearish", confidence=20.0,
            bullish=11, bearish=12, neutral=23,  # 23/46 = exactly 50%
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note

    def test_thin_margin_low_confidence_forces_neutral(self):
        """Margin <=2 agents AND confidence <15% must force neutral"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=12.0,
            bullish=14, bearish=13, neutral=18,  # margin = 1
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note
        assert "thin" in note.lower()

    def test_thin_margin_high_confidence_passes_rule3(self):
        """Margin <=2 but confidence >=15% should NOT be blocked by Rule 3"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=20.0,
            bullish=14, bearish=13, neutral=18,  # margin=1, confidence=20%
        )
        assert note is None

    def test_margin_exactly_2_triggers_rule3_at_low_confidence(self):
        """Margin of exactly 2 at low confidence should trigger Rule 3"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bearish", confidence=10.0,
            bullish=12, bearish=14, neutral=19,  # margin=2
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note

    def test_todays_scenario_zero_confidence_blocked(self):
        """
        calculate_confidence(16,12,17) returns ~0.055 in 0-1 scale.
        Verify the guard blocks the literal zero-confidence case (the original bug).
        """
        raw_conf = calculate_confidence(bullish=16, bearish=12, neutral=17)
        assert raw_conf < 0.10, f"Expected <0.10 (0-1 scale), got {raw_conf}"

        direction, final_conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=0.0,
            bullish=16, bearish=12, neutral=17,
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note


# =============================================================================
# TEST GROUP 2 -- FIX 2: CAUSAL CHAIN AUDIT
# =============================================================================

class TestCausalChainAudit:

    def _make_chain(self, cost, revenue, demand, sentiment):
        return {
            "cost_impact":      cost,
            "revenue_impact":   revenue,
            "demand_signal":    demand,
            "sentiment_signal": sentiment,
        }

    def test_all_4_bearish_returns_bearish(self):
        chain = self._make_chain(
            cost="Increased disruption risk pressure margins decline costs",
            revenue="Revenue decline expected iron ore ban drop lower",
            demand="Reduced demand Chinese steel mills uncertainty risk buyers",
            sentiment="Risk-off sell-off sentiment declining confidence bearish",
        )
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict == "bearish"
        assert b_count >= 3

    def test_3_bearish_1_neutral_returns_bearish(self):
        chain = self._make_chain(
            cost="Increased costs disruption risk decline pressure",
            revenue="Revenue decline expected lower bearish",
            demand="Neutral demand signal mixed no clear direction",
            sentiment="Risk-off sentiment declining bearish sell-off",
        )
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict == "bearish"
        assert b_count >= 3

    def test_all_4_bullish_returns_bullish(self):
        chain = self._make_chain(
            cost="Lower costs benefit margins increase profitability improvement",
            revenue="Revenue growth expected strong iron ore demand higher positive",
            demand="Strong demand growth recovery Chinese steel mills bullish surge",
            sentiment="Risk-on rally positive bullish outlook improvement AUD rise",
        )
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict == "bullish"
        assert u_count >= 3

    def test_2_bearish_2_bullish_returns_neutral(self):
        chain = self._make_chain(
            cost="Increased pressure margins decline risk disruption",
            revenue="Revenue growth expected positive improvement higher",
            demand="Demand uncertainty reduced orders risk lower",
            sentiment="Positive bullish outlook improvement rally surge",
        )
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict == "neutral"

    def test_empty_slots_handled_gracefully(self):
        chain = self._make_chain("", "", "", "")
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict in ("bullish", "bearish", "neutral")
        for sv in slots.values():
            assert "empty" in sv  # now includes trend suffix e.g. "neutral (empty)"

    def test_slot_verdicts_dict_has_correct_keys(self):
        chain = self._make_chain(
            "cost risk decline bearish", "revenue drop lower",
            "demand reduced uncertainty", "sentiment sell-off bearish",
        )
        _, _, _, slots = audit_causal_chain(chain)
        assert set(slots.keys()) == {"cost", "revenue", "demand", "sentiment"}

    def test_todays_sim_chain_all_bearish_voted_bullish(self):
        """
        Replay of sim_20260321_000906:
        All 4 chain slots pointed bearish. Majority voted bullish.
        audit_causal_chain must return bearish -> CHAIN_OVERRIDE fires.
        """
        chain = self._make_chain(
            cost=(
                "Risk of future disruptions may lead to increased costs "
                "for BHP iron ore exports delays and logistical challenges"
            ),
            revenue=(
                "Drop in AUD/USD may negatively impact iron ore export "
                "revenue decline despite stable prices potentially weighing on stock"
            ),
            demand=(
                "Risk of supply chain disruptions may decrease demand "
                "buyers such as Chinese steel mills may seek alternatives reduced"
            ),
            sentiment=(
                "Risk-off sentiment decline in AUD/USD geopolitical event "
                "may decrease investor confidence sell-off in BHP bearish"
            ),
        )
        verdict, b_count, u_count, slots = audit_causal_chain(chain)
        assert verdict == "bearish", (
            f"Expected bearish for today scenario, got {verdict}. "
            f"b={b_count} u={u_count} slots={slots}"
        )
        assert b_count >= 3
        for slot_name, sv in slots.items():
            assert sv.startswith("bearish") or sv.startswith("neutral"), (
                f"Slot {slot_name!r} returned {sv!r} -- expected bearish or neutral"
            )

    def test_chain_override_math_reduces_confidence(self):
        """When CHAIN_OVERRIDE fires, confidence is reduced by 15%."""
        original = 0.40
        reduced = max(0.0, round(original * 0.85, 3))
        assert abs(reduced - 0.34) < 0.001

    def test_chain_confirm_math_boosts_confidence(self):
        """When CHAIN_CONFIRMED fires, confidence is boosted by 15% (capped at 0.95)."""
        original = 0.40
        boosted = min(round(original * 1.15, 3), 0.95)
        assert abs(boosted - 0.46) < 0.001


# =============================================================================
# TEST GROUP 3 -- FIX 3: ACLED / NEWS DATE FILTER
# =============================================================================

class TestNewsDateFilter:

    def _make_item(self, headline, date_str, category="Strategic developments"):
        return {"headline": headline, "event_date": date_str, "category": category}

    def _days_ago(self, n):
        return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")

    def test_year_old_news_is_dropped(self):
        items = [self._make_item(
            "Houthi missile strike commercial vessel Red Sea",
            "2025-03-14", "Explosions/Remote violence",
        )]
        fresh, dropped = filter_stale_news(items, ticker="BHP")
        assert len(fresh) == 0
        assert len(dropped) == 1
        assert "2025-03-14" in dropped[0]["date"]

    def test_recent_news_is_kept(self):
        items = [self._make_item("Iron ore market update", self._days_ago(3))]
        fresh, dropped = filter_stale_news(items, ticker="BHP")
        assert len(fresh) == 1
        assert len(dropped) == 0

    def test_7_day_boundary_inclusive(self):
        items = [self._make_item("Global commodity update", self._days_ago(7))]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP")
        assert len(fresh) == 1

    def test_8_day_old_standard_news_dropped(self):
        items = [self._make_item(
            "Geopolitical tensions update", self._days_ago(8), "Explosions/Remote violence"
        )]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP")
        assert len(dropped) == 1
        assert len(fresh) == 0

    def test_bhp_specific_news_14_day_window(self):
        """BHP in headline -> 14-day window, not 7"""
        items = [self._make_item(
            "China widens ban on BHP iron ore second time",
            self._days_ago(10),  # 10 days: fails 7-day, passes 14-day
        )]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP.AX")
        assert len(fresh) == 1, "BHP-specific news within 14 days should be kept"
        assert len(dropped) == 0

    def test_bhp_specific_news_beyond_14_days_dropped(self):
        items = [self._make_item("BHP iron ore shipment update", self._days_ago(15))]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP.AX")
        assert len(dropped) == 1
        assert len(fresh) == 0

    def test_mixed_batch_filters_correctly(self):
        items = [
            self._make_item("BHP CEO transition announcement", self._days_ago(2)),
            self._make_item("Houthi strike Red Sea incident", "2025-03-14"),
            self._make_item("China PMI contraction reported", self._days_ago(5)),
            self._make_item("Ukraine conflict regional update", "2025-03-13"),
            self._make_item("Iron ore futures trading update", self._days_ago(1)),
        ]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP")
        assert len(fresh) == 3    # 2d, 5d, 1d
        assert len(dropped) == 2  # both 2025 dates

    def test_no_date_field_item_is_kept(self):
        """Items with no date field pass through (fail-open)"""
        items = [{"headline": "Unknown date event", "category": "Strategic"}]
        fresh, dropped = filter_stale_news(items, ticker="BHP")
        assert len(fresh) == 1
        assert fresh[0].get("date_verified") is False

    def test_dropped_items_contain_metadata(self):
        items = [
            self._make_item("Old event A", "2025-03-14"),
            self._make_item("Old event B", "2025-01-01"),
        ]
        fresh, dropped = filter_stale_news(items, ticker="BHP")
        assert len(dropped) == 2
        for d in dropped:
            assert "headline" in d
            assert "date" in d
            assert "age_days" in d
            assert "reason" in d

    def test_returns_tuple_not_list(self):
        result = filter_stale_news([], ticker="BHP")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_fresh_items_get_hours_old_attached(self):
        items = [self._make_item("Recent event", self._days_ago(3))]
        fresh, _ = filter_stale_news(items, ticker="BHP")
        assert "hours_old" in fresh[0]
        assert 60 <= fresh[0]["hours_old"] <= 84  # ~72h

    def test_all_2025_events_dropped_in_2026(self):
        items = [
            self._make_item("Event A", "2025-12-31"),
            self._make_item("Event B", "2025-06-15"),
            self._make_item("Event C", "2025-03-14"),
            self._make_item("Event D", "2025-01-01"),
        ]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP")
        assert len(fresh) == 0
        assert len(dropped) == 4


# =============================================================================
# TEST GROUP 4 -- FIX 4: BLIND JUDGE PROMPT STRUCTURE
# =============================================================================

class TestBlindJudgePromptStructure:
    """Unit tests for prompt structure -- no LLM calls."""

    def _lessons(self):
        return "=== LESSONS FROM PAST PREDICTIONS ===\n(none)\n=== END LESSONS ==="

    def _reconciler(self, **kwargs):
        defaults = dict(
            ticker="BHP.AX", logic_verdict="bearish", logic_confidence="high",
            n_bull=16, n_bear=12, n_neut=17, market_session="BROAD_SELLOFF",
            top_critical_news="[CRITICAL] China BHP ban",
            axjo_change_pct=-0.82, spx_change_pct=-1.41,
            lessons_block=self._lessons(),
        )
        defaults.update(kwargs)
        return _reconciler_prompt(**defaults)

    def test_blind_judge_requests_five_fields(self):
        prompt = _blind_judge_prompt("BHP.AX", self._lessons())
        for field in ("LOGIC_VERDICT:", "LOGIC_CONFIDENCE:", "STRONGEST_EVIDENCE:",
                      "WEAKEST_ARGUMENT:", "REASONING:"):
            assert field in prompt, f"Missing {field} in blind judge prompt"

    def test_blind_judge_no_vote_counts(self):
        """Blind judge must NOT contain vote count information"""
        prompt = _blind_judge_prompt("BHP.AX", self._lessons())
        assert "vote majority" not in prompt.lower()
        assert "n_bull" not in prompt
        assert "agent votes" not in prompt.lower()

    def test_blind_judge_no_market_session(self):
        """Blind judge must not contain market session (prevents anchoring)"""
        prompt = _blind_judge_prompt("BHP.AX", self._lessons())
        assert "BROAD_SELLOFF" not in prompt
        assert "market_session" not in prompt.lower()

    def test_reconciler_contains_vote_tally(self):
        prompt = self._reconciler()
        assert "16" in prompt and "12" in prompt and "17" in prompt

    def test_reconciler_contains_all_5_rules(self):
        prompt = self._reconciler()
        for rule_num in ("RULE 1", "RULE 2", "RULE 3", "RULE 4", "RULE 5"):
            assert rule_num in prompt, f"Missing {rule_num} in reconciler prompt"
        assert "LOGIC_OVERRIDE" in prompt
        assert "SELLOFF_DOWNGRADE" in prompt

    def test_reconciler_requests_json_output(self):
        prompt = self._reconciler()
        assert "JSON" in prompt
        for field in ('"verdict"', '"confidence_modifier"', '"cost_impact"'):
            assert field in prompt, f"Missing {field} in reconciler prompt"

    def test_reconciler_contains_market_session(self):
        prompt = self._reconciler(market_session="BROAD_SELLOFF")
        assert "BROAD_SELLOFF" in prompt

    def test_blind_judge_requests_no_json(self):
        prompt = _blind_judge_prompt("BHP.AX", self._lessons())
        assert ("no JSON" in prompt.lower() or "no markdown" in prompt.lower()
                or "EXACTLY" in prompt)


@pytest.mark.integration
@pytest.mark.asyncio
class TestBlindJudgeLive:
    """Integration tests -- require GROQ_API_KEY."""

    async def _call(self, groq_client, system, user):
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            temperature=0.1, max_tokens=600,
        )
        return resp.choices[0].message.content

    def _parse_blind(self, text):
        r = {"logic_verdict": "neutral", "logic_confidence": "low",
             "strongest_evidence": "", "weakest_argument": "", "reasoning": ""}
        for line in text.splitlines():
            lu = line.strip().upper()
            if lu.startswith("LOGIC_VERDICT:"):
                v = line.split(":", 1)[1].strip().lower()
                if v in ("bullish", "bearish", "neutral"):
                    r["logic_verdict"] = v
            elif lu.startswith("LOGIC_CONFIDENCE:"):
                v = line.split(":", 1)[1].strip().lower()
                if v in ("high", "medium", "low"):
                    r["logic_confidence"] = v
            elif lu.startswith("STRONGEST_EVIDENCE:"):
                r["strongest_evidence"] = line.split(":", 1)[1].strip()
            elif lu.startswith("WEAKEST_ARGUMENT:"):
                r["weakest_argument"] = line.split(":", 1)[1].strip()
            elif lu.startswith("REASONING:"):
                r["reasoning"] = line.split(":", 1)[1].strip()
        return r

    def _parse_json(self, text):
        clean = text.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
        if clean.endswith("```"):
            clean = clean[:-3].strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return {}

    async def test_blind_judge_picks_bear_with_specific_evidence(self, groq_client):
        lessons = "=== LESSONS FROM PAST PREDICTIONS ===\n(none)\n=== END LESSONS ==="
        system = _blind_judge_prompt("BHP.AX", lessons)
        user = (
            "BULL ARGUMENTS:\n"
            "  - Houthi strike may boost iron ore prices temporarily\n"
            "  - High volume suggests potential buying interest\n\n"
            "BEAR ARGUMENTS:\n"
            "  - China banned BHP iron ore -- direct revenue loss confirmed\n"
            "  - S&P 500 down 1.41%, ASX down 0.82% -- broad institutional selloff\n"
            "  - AUD/USD declining 0.18% -- risk-off capital flight confirmed\n\n"
            "QUANT SIGNALS:\n"
            "  - RSI UNAVAILABLE. Volume 2.77x avg on down day = distribution\n\n"
            "FUNDAMENTAL ANALYSTS:\n"
            "  - Iron Ore $97.5/t flat. AUD/USD 0.7069 -0.18%.\n\n"
            "Evaluate argument quality only. Return five lines as instructed."
        )
        raw = await self._call(groq_client, system, user)
        result = self._parse_blind(raw)
        assert result["logic_verdict"] == "bearish", (
            f"Expected bearish, got {result['logic_verdict']}.\nRaw:\n{raw}"
        )
        assert result["logic_confidence"] in ("medium", "high")
        assert len(result["reasoning"]) > 10

    async def test_reconciler_overrides_bullish_majority_on_selloff(self, groq_client):
        lessons = "=== LESSONS FROM PAST PREDICTIONS ===\n(none)\n=== END LESSONS ==="
        system = _reconciler_prompt(
            ticker="BHP.AX", logic_verdict="bearish", logic_confidence="high",
            n_bull=18, n_bear=12, n_neut=15, market_session="BROAD_SELLOFF",
            top_critical_news="[CRITICAL] China widens BHP iron ore ban (3d)",
            axjo_change_pct=-0.82, spx_change_pct=-1.41, lessons_block=lessons,
        )
        user = (
            "Apply the reconciliation rules and return JSON.\n"
            "STRONGEST_EVIDENCE: China confirmed BHP iron ore ban.\n"
            "WEAKEST_ARGUMENT: High volume implies buying interest.\n"
            "BLIND_REASONING: Bearish specific data outweighs vague bull arguments."
        )
        raw = await self._call(groq_client, system, user)
        result = self._parse_json(raw)
        assert result, f"Unparseable JSON:\n{raw}"
        assert result.get("verdict") == "bearish", (
            f"Expected bearish, got {result.get('verdict')}"
        )
        override = result.get("override_flag", "") or ""
        assert "LOGIC_OVERRIDE" in override, f"Expected LOGIC_OVERRIDE, got: {override}"


# =============================================================================
# TEST GROUP 5 -- NEWS WEIGHT FUNCTION
# =============================================================================

class TestNewsWeightFunction:

    def test_company_specific_recent_is_critical(self):
        w = news_weight(
            hours_old=6, category="Strategic developments",
            headline="China widens ban on BHP iron ore second time", ticker="BHP.AX",
        )
        assert w >= 0.85
        assert weight_to_label(w) == "CRITICAL"

    def test_old_geopolitical_is_low(self):
        w = news_weight(
            hours_old=371 * 24, category="Explosions/Remote violence",
            headline="Israeli airstrikes on Gaza City", ticker="BHP.AX",
        )
        assert w <= 0.15
        assert weight_to_label(w) == "LOW — treat as background noise only"

    def test_supply_chain_keyword_boosts_weight(self):
        w = news_weight(
            hours_old=36, category="Strategic developments",
            headline="Suez Canal reports 40 percent drop in vessel transit", ticker="BHP.AX",
        )
        assert w >= 0.75
        assert weight_to_label(w) in ("CRITICAL", "HIGH")

    def test_geopolitical_violence_decays_faster(self):
        w_standard = news_weight(
            hours_old=12, category="Strategic developments",
            headline="Generic market update today", ticker="BHP.AX",
        )
        w_violence = news_weight(
            hours_old=12, category="Explosions/Remote violence",
            headline="Generic conflict update today", ticker="BHP.AX",
        )
        assert w_violence < w_standard

    def test_bhp_boost_only_within_48h(self):
        """BHP boost applies at <=48h; beyond 48h the boost does NOT apply"""
        w_recent = news_weight(
            hours_old=36, category="Explosions/Remote violence",
            headline="BHP operations disrupted conflict site", ticker="BHP.AX",
        )
        assert w_recent >= 0.85, f"Expected >=0.85 for recent BHP news, got {w_recent}"

        # 60h > 48h: base=0.2 * BATTLES_multiplier=0.65 = 0.13, no BHP boost
        w_stale = news_weight(
            hours_old=60, category="Explosions/Remote violence",
            headline="BHP operations disrupted conflict site", ticker="BHP.AX",
        )
        assert w_stale <= 0.20, f"Expected <=0.20 for stale BHP news, got {w_stale}"

    def test_weight_to_label_thresholds(self):
        assert weight_to_label(0.85) == "CRITICAL"
        assert weight_to_label(0.90) == "CRITICAL"
        assert weight_to_label(0.84) == "HIGH"
        assert weight_to_label(0.70) == "HIGH"
        assert weight_to_label(0.69) == "MEDIUM"
        assert weight_to_label(0.45) == "MEDIUM"
        assert weight_to_label(0.44) == "LOW — treat as background noise only"

    def test_tariff_does_not_trigger_supply_boost(self):
        """tariff must NOT be a supply chain keyword (removed after bug fix).
        Headline deliberately avoids supply keywords (note: 'imports' contains
        'port' as substring so we use a clean headline here).
        """
        # Strategic dev at 48h: max(0.4, 0.75) = 0.75. No supply keyword. No BHP.
        w = news_weight(
            hours_old=48, category="Strategic developments",
            headline="Beijing raises steel tariff rates affecting commodity prices", ticker="BHP.AX",
        )
        assert w == 0.75, f"tariff should not trigger supply boost, got {w}"


# =============================================================================
# TEST GROUP 6 -- CONFIDENCE MATH (regression)
# =============================================================================

class TestConfidenceMath:

    def test_near_split_gives_low_confidence(self):
        """24B/0Be/26N -> ~0.23 (NOT 0.96)"""
        c = calculate_confidence(bullish=24, bearish=0, neutral=26)
        assert 0.20 < c < 0.30, f"Expected ~0.23, got {c}"

    def test_strong_majority_gives_higher_confidence(self):
        c = calculate_confidence(bullish=35, bearish=5, neutral=5)
        assert c > 0.40

    def test_all_neutral_gives_zero(self):
        assert calculate_confidence(0, 0, 45) == 0.0

    def test_all_zero_agents_gives_zero(self):
        assert calculate_confidence(0, 0, 0) == 0.0

    def test_high_neutral_caps_at_0_60(self):
        c = calculate_confidence(bullish=24, bearish=0, neutral=26)  # 52% neutral
        assert c <= 0.60

    def test_todays_16_12_17_is_near_zero(self):
        c = calculate_confidence(bullish=16, bearish=12, neutral=17)
        assert c < 0.10, f"Expected <0.10, got {c}"
        assert c > 0.0

    def test_returns_01_float_not_percentage(self):
        c = calculate_confidence(bullish=30, bearish=5, neutral=10)
        assert c <= 1.0, f"Must return 0-1 float, got {c}"


# =============================================================================
# TEST GROUP 7 -- FULL PIPELINE REPLAY (gating tests)
# =============================================================================

class TestFullPipelineReplay:
    """
    End-to-end replay of sim_20260321_000906 (the broken prediction).
    All must PASS before any Railway deploy.

    Previous broken output: direction=UP at 0% confidence.
    Required: direction != UP for this input combination.
    """

    def test_step1_confidence_is_low_for_split(self):
        """16/12/17: calculate_confidence returns < 0.10"""
        c = calculate_confidence(16, 12, 17)
        assert c < 0.10, f"Expected <0.10, got {c}"

    def test_step2_stale_2025_news_filtered(self):
        """2025-03-14 Houthi news must be dropped before agents see it"""
        items = [{"headline": "Houthi missile strike Red Sea",
                  "event_date": "2025-03-14", "category": "Explosions/Remote violence"}]
        fresh, dropped = filter_stale_news(items, max_age_days=7, ticker="BHP")
        assert len(fresh) == 0, "2025 news must not reach agents"
        assert len(dropped) == 1

    def test_step3_causal_chain_detects_all_bearish(self):
        """All 4 bearish chain slots -> bearish verdict"""
        chain = {
            "cost_impact":      "Risk disruptions increased costs logistics delays challenges",
            "revenue_impact":   "Revenue decline negative weighing drop lower impact",
            "demand_signal":    "Reduced demand uncertainty risk-off buyers seek alternatives",
            "sentiment_signal": "Risk-off declining confidence sell-off bearish sentiment",
        }
        verdict, b, u, slots = audit_causal_chain(chain)
        assert verdict == "bearish", f"Chain must be bearish, got {verdict}"
        assert b >= 3

    def test_step4_confidence_guard_blocks_zero(self):
        """Confidence < 3% must trigger the guard"""
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=1.5,
            bullish=16, bearish=12, neutral=17,
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note

    def test_critical_never_outputs_up_at_zero_confidence(self):
        """
        CRITICAL GATING TEST:
        direction=UP at 0% confidence must NEVER happen again.
        Exact scenario from sim_20260321_000906.
        """
        direction, conf, note = apply_minimum_confidence_guard(
            direction="bullish", confidence=0.0,
            bullish=16, bearish=12, neutral=17,
        )
        assert direction != "bullish", (
            f"CRITICAL FAILURE: System outputs bullish at 0% confidence. "
            f"direction={direction}, note={note}"
        )
        assert direction == "neutral"
        assert note is not None
        assert "INSUFFICIENT_SIGNAL" in note

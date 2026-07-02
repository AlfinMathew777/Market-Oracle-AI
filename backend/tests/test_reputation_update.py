"""Tests for the outcome-fed reputation update rule (Piece 2)."""

import os
import tempfile

import pytest
from trust.reputation import (
    ARCHETYPE,
    REPUTATION_CEILING,
    REPUTATION_FLOOR,
    REPUTATION_PRIOR,
    SOURCE,
    STAGE_AUTHORITATIVE,
    STAGE_PROVISIONAL,
    TIER_ARCHETYPE_AGNOSTIC,
    TIER_CELL,
    TIER_PRIOR,
    ReputationStore,
)
from trust.reputation_update import (
    BASE_ALPHA,
    apply_outcome,
    archetype_steps,
    collapse_regime,
    step_weight,
)

pytestmark = pytest.mark.unit

_TS = "2026-06-17T00:00:00Z"
_DECISIVE = 3.0  # percent move → full-strength step


@pytest.fixture
def store_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="repupd_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


async def _store(path):
    s = ReputationStore(path)
    await s.init()
    return s


def _attr(direction="DOWN", trend="STRONG_DOWNTREND", chain_override=False):
    return {
        "simulation_id": "sim_X",
        "trend_label": trend,
        "chain_override": chain_override,
        "driving_archetypes": {"geo_bear": 1},
        "sources": [{"source_id": "reuters", "weight": 0.9}],
    }


# ── policy helpers ────────────────────────────────────────────────────────────

def test_collapse_regime_three_buckets():
    assert collapse_regime("STRONG_DOWNTREND") == "down"
    assert collapse_regime("DOWNTREND") == "down"
    assert collapse_regime("UPTREND") == "up"
    assert collapse_regime("STRONG_UPTREND") == "up"
    assert collapse_regime("NEUTRAL") == "neutral"
    assert collapse_regime("") == "neutral"


def test_step_weight_zero_inside_band():
    assert step_weight(0.3) == 0.0
    assert step_weight(-0.5) == 0.0


def test_step_weight_damped_just_above_band():
    marginal = step_weight(0.6)   # barely cleared ±0.5
    decisive = step_weight(_DECISIVE)
    assert 0.0 < marginal < decisive
    assert decisive == pytest.approx(BASE_ALPHA)  # full strength at decisive


# ── EMA direction + bounds ────────────────────────────────────────────────────

async def test_incorrect_lowers_reputation(store_path):
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr(),
                        outcome="INCORRECT", change_pct=-_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("reuters", SOURCE)).reputation < REPUTATION_PRIOR


async def test_correct_raises_reputation(store_path):
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr(),
                        outcome="CORRECT", change_pct=_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("reuters", SOURCE)).reputation > REPUTATION_PRIOR


async def test_survivorship_neutral_does_not_update(store_path):
    store = await _store(store_path)
    res = await apply_outcome(store, prediction_id="p1", attribution=_attr(),
                              outcome="NEUTRAL", change_pct=0.1,
                              stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert res["updated"] is False
    assert (await store.record("reuters", SOURCE)).sample_count == 0


# ── dual-bucket + chain override ──────────────────────────────────────────────

async def test_archetype_updates_both_regime_and_pooled(store_path):
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr(trend="DOWNTREND"),
                        outcome="INCORRECT", change_pct=-_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("geo_bear", ARCHETYPE, "down")).sample_count == 1
    assert (await store.record("geo_bear", ARCHETYPE, "")).sample_count == 1  # A-backstop


async def test_chain_override_skips_archetypes_keeps_sources(store_path):
    store = await _store(store_path)
    res = await apply_outcome(store, prediction_id="p1", attribution=_attr(chain_override=True),
                              outcome="INCORRECT", change_pct=-_DECISIVE,
                              stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert res["archetypes_updated"] == 0
    assert res["sources_updated"] == 1
    assert (await store.record("geo_bear", ARCHETYPE, "down")).sample_count == 0
    assert (await store.record("reuters", SOURCE)).sample_count == 1


# ── supersede / idempotency ───────────────────────────────────────────────────

async def test_same_stage_reapply_is_idempotent(store_path):
    store = await _store(store_path)
    a = await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                               target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                               stage=STAGE_PROVISIONAL, updated_at=_TS)
    b = await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                               target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                               stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert a == "applied" and b == "skipped"
    assert (await store.record("reuters", SOURCE)).sample_count == 1  # one sample


async def test_authoritative_supersedes_provisional_one_sample(store_path):
    store = await _store(store_path)
    # provisional says INCORRECT, authoritative later says CORRECT.
    await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                           target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                           stage=STAGE_PROVISIONAL, updated_at=_TS)
    action = await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                                    target=1.0, weight=BASE_ALPHA, outcome="CORRECT",
                                    stage=STAGE_AUTHORITATIVE, updated_at=_TS)
    rec = await store.record("reuters", SOURCE)
    assert action == "superseded"
    assert rec.sample_count == 1                 # never two samples
    # provisional fully backed out → equals a single CORRECT step from the prior.
    expected = REPUTATION_PRIOR + BASE_ALPHA * (1.0 - REPUTATION_PRIOR)
    assert rec.reputation == pytest.approx(expected, abs=1e-9)


async def test_supersede_under_interleaving_keeps_one_sample(store_path):
    """Other predictions update the same cell between provisional and authoritative."""
    store = await _store(store_path)
    # p1 provisional, then p2 + p3 hit the SAME cell, then p1 authoritative supersedes.
    await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                           target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                           stage=STAGE_PROVISIONAL, updated_at=_TS)
    await store.apply_step(prediction_id="p2", identity="reuters", kind=SOURCE,
                           target=1.0, weight=BASE_ALPHA, outcome="CORRECT",
                           stage=STAGE_PROVISIONAL, updated_at=_TS)
    await store.apply_step(prediction_id="p3", identity="reuters", kind=SOURCE,
                           target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                           stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("reuters", SOURCE)).sample_count == 3
    action = await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                                    target=1.0, weight=BASE_ALPHA, outcome="CORRECT",
                                    stage=STAGE_AUTHORITATIVE, updated_at=_TS)
    rec = await store.record("reuters", SOURCE)
    assert action == "superseded"
    assert rec.sample_count == 3  # 3 predictions → 3 samples, never 4. no double-weight.
    assert REPUTATION_FLOOR <= rec.reputation <= REPUTATION_CEILING


async def test_supersede_back_out_approximates_no_provisional(store_path):
    """Under interleaving the back-out tracks the as-if-no-provisional value tightly."""
    # A: p1 provisional INCORRECT, p2 CORRECT (intervening), p1 authoritative CORRECT.
    a = await _store(store_path)
    await a.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE, target=0.0,
                       weight=BASE_ALPHA, outcome="INCORRECT", stage=STAGE_PROVISIONAL, updated_at=_TS)
    await a.apply_step(prediction_id="p2", identity="reuters", kind=SOURCE, target=1.0,
                       weight=BASE_ALPHA, outcome="CORRECT", stage=STAGE_PROVISIONAL, updated_at=_TS)
    await a.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE, target=1.0,
                       weight=BASE_ALPHA, outcome="CORRECT", stage=STAGE_AUTHORITATIVE, updated_at=_TS)
    rep_a = (await a.record("reuters", SOURCE)).reputation

    # C: the as-if world — p1 was only ever CORRECT, no provisional. same two predictions.
    c = await _store(store_path + "C")
    await c.apply_step(prediction_id="p2", identity="reuters", kind=SOURCE, target=1.0,
                       weight=BASE_ALPHA, outcome="CORRECT", stage=STAGE_PROVISIONAL, updated_at=_TS)
    await c.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE, target=1.0,
                       weight=BASE_ALPHA, outcome="CORRECT", stage=STAGE_AUTHORITATIVE, updated_at=_TS)
    rep_c = (await c.record("reuters", SOURCE)).reputation
    os.remove(store_path + "C")

    # second-order EMA path error only — well within a hundredth of the range.
    assert abs(rep_a - rep_c) < 0.01


async def test_authoritative_then_provisional_is_skipped(store_path):
    store = await _store(store_path)
    await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                           target=1.0, weight=BASE_ALPHA, outcome="CORRECT",
                           stage=STAGE_AUTHORITATIVE, updated_at=_TS)
    late = await store.apply_step(prediction_id="p1", identity="reuters", kind=SOURCE,
                                  target=0.0, weight=BASE_ALPHA, outcome="INCORRECT",
                                  stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert late == "skipped"  # authoritative is final


# ── tier (A-backstop readability) ─────────────────────────────────────────────

async def test_tier_reports_prior_then_backstop_then_cell(store_path):
    store = await _store(store_path)
    # unseen → prior
    val, tier = await store.effective_with_tier("geo_bear", ARCHETYPE, "down")
    assert tier == TIER_PRIOR and val == REPUTATION_PRIOR

    # season only the pooled record → A-backstop tier
    await store.set_reputation("geo_bear", ARCHETYPE, 0.6, 10, regime="", updated_at=_TS)
    val, tier = await store.effective_with_tier("geo_bear", ARCHETYPE, "down")
    assert tier == TIER_ARCHETYPE_AGNOSTIC and val == pytest.approx(0.6)

    # season the regime cell → cell tier wins
    await store.set_reputation("geo_bear", ARCHETYPE, 0.4, 10, regime="down", updated_at=_TS)
    val, tier = await store.effective_with_tier("geo_bear", ARCHETYPE, "down")
    assert tier == TIER_CELL and val == pytest.approx(0.4)


# ── convergence (loop stability) ──────────────────────────────────────────────

async def test_repeated_wrong_converges_to_floor_monotonic(store_path):
    store = await _store(store_path)
    reps = []
    for i in range(40):
        await apply_outcome(store, prediction_id=f"p{i}", attribution=_attr(),
                            outcome="INCORRECT", change_pct=-_DECISIVE,
                            stage=STAGE_PROVISIONAL, updated_at=_TS)
        reps.append((await store.record("reuters", SOURCE)).reputation)
    # monotonic non-increasing, bounded by the protective floor, never silenced.
    assert all(b <= a + 1e-9 for a, b in zip(reps, reps[1:], strict=False))
    assert reps[-1] >= REPUTATION_FLOOR
    assert reps[-1] == pytest.approx(REPUTATION_FLOOR, abs=0.02)


async def test_before_after_table_source(store_path):
    """A source fed wrong calls: gated on prior while thin, then declines & supersede-safe."""
    store = await _store(store_path)
    rows = []
    for i in range(8):
        await apply_outcome(store, prediction_id=f"p{i}", attribution=_attr(),
                            outcome="INCORRECT", change_pct=-_DECISIVE,
                            stage=STAGE_PROVISIONAL, updated_at=_TS)
        eff, tier = await store.effective_with_tier("reuters", SOURCE)
        rec = await store.record("reuters", SOURCE)
        rows.append((i + 1, rec.sample_count, round(rec.reputation, 4), round(eff, 4), tier))

    # while thin (< MIN_SAMPLES) the effective vote-weight stays pinned to the prior.
    assert all(r[3] == REPUTATION_PRIOR and r[4 - 1] for r in rows[:4])
    assert all(r[4] == TIER_PRIOR for r in rows[:4])
    # once seasoned the effective weight tracks the (declining) stored value.
    assert rows[-1][4] == TIER_CELL
    assert rows[-1][3] < REPUTATION_PRIOR
    assert rows[-1][3] >= REPUTATION_FLOOR


async def test_repeated_correct_converges_to_ceiling(store_path):
    store = await _store(store_path)
    last = REPUTATION_PRIOR
    for i in range(40):
        await apply_outcome(store, prediction_id=f"p{i}", attribution=_attr(),
                            outcome="CORRECT", change_pct=_DECISIVE,
                            stage=STAGE_PROVISIONAL, updated_at=_TS)
        last = (await store.record("reuters", SOURCE)).reputation
    assert last == pytest.approx(REPUTATION_CEILING, abs=0.02)


# ── dissent learns (archetype_votes shape) ────────────────────────────────────

def _attr_all_sides(trend="STRONG_UPTREND", chain_override=False, votes=None):
    """New-shape payload: final call UP, geo_bear dissented bearish."""
    return {
        "simulation_id": "sim_X",
        "trend_label": trend,
        "chain_override": chain_override,
        "direction": "UP",
        "driving_archetypes": {"macro_bull": 2, "quant": 1},
        "archetype_votes": votes if votes is not None else {
            "bullish": {"macro_bull": 2, "quant": 1},
            "bearish": {"geo_bear": 1},
            "neutral": {"neutral_fund": 1},
        },
        "sources": [{"source_id": "reuters", "weight": 0.9}],
    }


async def test_dissenter_right_earns_credit(store_path):
    """Final call UP was wrong (actual DOWN) — the bearish dissenter gains."""
    store = await _store(store_path)
    res = await apply_outcome(store, prediction_id="p1", attribution=_attr_all_sides(),
                              outcome="INCORRECT", change_pct=-_DECISIVE,
                              stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert res["archetypes_updated"] == 3  # macro_bull, quant, geo_bear (not neutral_fund)
    geo = await store.record("geo_bear", ARCHETYPE, "")
    assert geo.reputation > REPUTATION_PRIOR  # dissent-right → credit
    # 1 bearish vote of 4 directional → quarter-share of the full step toward 1.0
    expected = REPUTATION_PRIOR + BASE_ALPHA * (1 / 4) * (1.0 - REPUTATION_PRIOR)
    assert geo.reputation == pytest.approx(expected, abs=1e-9)


async def test_dissenter_wrong_takes_penalty(store_path):
    """Final call UP was right (actual UP) — the bearish dissenter loses."""
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr_all_sides(),
                        outcome="CORRECT", change_pct=_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    geo = await store.record("geo_bear", ARCHETYPE, "")
    expected = REPUTATION_PRIOR + BASE_ALPHA * (1 / 4) * (0.0 - REPUTATION_PRIOR)
    assert geo.reputation < REPUTATION_PRIOR
    assert geo.reputation == pytest.approx(expected, abs=1e-9)
    # winners still earn, weighted by vote share (2 of 4 directional votes).
    bull = await store.record("macro_bull", ARCHETYPE, "")
    expected_bull = REPUTATION_PRIOR + BASE_ALPHA * (2 / 4) * (1.0 - REPUTATION_PRIOR)
    assert bull.reputation == pytest.approx(expected_bull, abs=1e-9)


async def test_neutral_votes_never_update(store_path):
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr_all_sides(),
                        outcome="CORRECT", change_pct=_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("neutral_fund", ARCHETYPE, "")).sample_count == 0
    assert (await store.record("neutral_fund", ARCHETYPE, "up")).sample_count == 0


async def test_new_shape_updates_regime_and_pooled_cells(store_path):
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr_all_sides(),
                        outcome="INCORRECT", change_pct=-_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert (await store.record("geo_bear", ARCHETYPE, "up")).sample_count == 1
    assert (await store.record("geo_bear", ARCHETYPE, "")).sample_count == 1  # A-backstop


async def test_chain_override_skips_archetypes_new_shape(store_path):
    store = await _store(store_path)
    res = await apply_outcome(store, prediction_id="p1",
                              attribution=_attr_all_sides(chain_override=True),
                              outcome="INCORRECT", change_pct=-_DECISIVE,
                              stage=STAGE_PROVISIONAL, updated_at=_TS)
    assert res["archetypes_updated"] == 0
    assert res["sources_updated"] == 1
    assert (await store.record("geo_bear", ARCHETYPE, "")).sample_count == 0
    assert (await store.record("macro_bull", ARCHETYPE, "")).sample_count == 0


async def test_legacy_shape_replays_exactly_as_before(store_path):
    """A payload without archetype_votes uses the winner-only rule, full weight."""
    store = await _store(store_path)
    await apply_outcome(store, prediction_id="p1", attribution=_attr(),  # legacy _attr
                        outcome="CORRECT", change_pct=_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    geo = await store.record("geo_bear", ARCHETYPE, "")
    # full BASE_ALPHA step toward 1.0 — no vote-share scaling on legacy entries.
    expected = REPUTATION_PRIOR + BASE_ALPHA * (1.0 - REPUTATION_PRIOR)
    assert geo.reputation == pytest.approx(expected, abs=1e-9)
    assert geo.sample_count == 1
    # dissenters in a legacy entry are invisible — no cells touched for them.
    assert (await store.record("macro_bull", ARCHETYPE, "")).sample_count == 0


async def test_both_sides_archetype_scored_per_side(store_path):
    """Two quant agents split bullish/bearish — one blended, share-weighted step."""
    store = await _store(store_path)
    votes = {
        "bullish": {"quant": 1, "macro_bull": 2},
        "bearish": {"quant": 1},
        "neutral": {},
    }
    await apply_outcome(store, prediction_id="p1",
                        attribution=_attr_all_sides(votes=votes),
                        outcome="CORRECT", change_pct=_DECISIVE,
                        stage=STAGE_PROVISIONAL, updated_at=_TS)
    quant = await store.record("quant", ARCHETYPE, "")
    # actual UP: quant 1 right + 1 wrong → target 0.5, weight share 2/4.
    expected = REPUTATION_PRIOR + BASE_ALPHA * (2 / 4) * (0.5 - REPUTATION_PRIOR)
    assert quant.reputation == pytest.approx(expected, abs=1e-9)
    assert quant.sample_count == 1  # one prediction → one sample, even split-voted


def test_archetype_steps_neutral_only_yields_no_steps():
    votes = {"bullish": {}, "bearish": {}, "neutral": {"neutral_fund": 3}}
    assert archetype_steps(votes, "bullish", BASE_ALPHA) == {}


def test_archetype_steps_labels_and_shares():
    votes = {"bullish": {"macro_bull": 2}, "bearish": {"geo_bear": 1, "macro_bull": 1}}
    steps = archetype_steps(votes, "bullish", BASE_ALPHA)
    tgt, w, label = steps["macro_bull"]
    assert (tgt, label) == (pytest.approx(2 / 3), "MIXED")
    assert w == pytest.approx(BASE_ALPHA * 3 / 4)
    tgt, w, label = steps["geo_bear"]
    assert (tgt, label) == (0.0, "INCORRECT")
    assert w == pytest.approx(BASE_ALPHA * 1 / 4)

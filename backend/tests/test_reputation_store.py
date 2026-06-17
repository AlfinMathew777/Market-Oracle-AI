"""Tests for the canonical reputation store — prior, gate, clamp, persistence."""

import os
import tempfile

import pytest
from trust.reputation import (
    ARCHETYPE,
    MIN_SAMPLES,
    REPUTATION_CEILING,
    REPUTATION_FLOOR,
    REPUTATION_PRIOR,
    SOURCE,
    ReputationStore,
)

pytestmark = pytest.mark.unit

_TS = "2026-06-17T00:00:00Z"


@pytest.fixture
def store_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="rep_test_")
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


async def test_unseen_identity_returns_prior(store_path):
    store = await _store(store_path)
    rec = await store.record("reuters", SOURCE)
    assert rec.sample_count == 0
    assert rec.effective == REPUTATION_PRIOR
    assert await store.effective("reuters", SOURCE) == REPUTATION_PRIOR


async def test_thin_sample_sits_on_prior(store_path):
    store = await _store(store_path)
    # stored high reputation but only a few outcomes → gate forces the prior.
    await store.set_reputation("reuters", SOURCE, 0.8, MIN_SAMPLES - 1, updated_at=_TS)
    rec = await store.record("reuters", SOURCE)
    assert rec.is_seasoned is False
    assert rec.effective == REPUTATION_PRIOR


async def test_seasoned_identity_uses_stored_value(store_path):
    store = await _store(store_path)
    await store.set_reputation("reuters", SOURCE, 0.8, MIN_SAMPLES, updated_at=_TS)
    rec = await store.record("reuters", SOURCE)
    assert rec.is_seasoned is True
    assert rec.effective == pytest.approx(0.8)


async def test_floor_is_protective_never_silenced(store_path):
    store = await _store(store_path)
    # a chronically-wrong source still keeps the floor — never reaches 0.
    await store.set_reputation("badwire", SOURCE, -1.0, 50, updated_at=_TS)
    rec = await store.record("badwire", SOURCE)
    assert rec.reputation == REPUTATION_FLOOR
    assert rec.effective == REPUTATION_FLOOR
    assert REPUTATION_FLOOR > 0.0


async def test_ceiling_caps_blind_trust(store_path):
    store = await _store(store_path)
    await store.set_reputation("perfectwire", SOURCE, 1.5, 50, updated_at=_TS)
    rec = await store.record("perfectwire", SOURCE)
    assert rec.reputation == REPUTATION_CEILING
    assert REPUTATION_CEILING < 1.0


async def test_archetype_kind_is_independent(store_path):
    store = await _store(store_path)
    await store.set_reputation("macro_bull", ARCHETYPE, 0.7, MIN_SAMPLES, updated_at=_TS)
    # same string in the source table is untouched → independent keyspace.
    assert await store.effective("macro_bull", ARCHETYPE) == pytest.approx(0.7)
    assert await store.effective("macro_bull", SOURCE) == REPUTATION_PRIOR


async def test_persists_across_instances(store_path):
    store = await _store(store_path)
    await store.set_reputation("gdelt", SOURCE, 0.6, MIN_SAMPLES, updated_at=_TS)
    reopened = await _store(store_path)  # fresh instance, same file
    assert await reopened.effective("gdelt", SOURCE) == pytest.approx(0.6)


async def test_read_failure_falls_back_to_prior():
    # a directory path cannot be opened as a db → read fails → prior, no crash.
    store = ReputationStore(tempfile.mkdtemp())
    rec = await store.record("reuters", SOURCE)
    assert rec.effective == REPUTATION_PRIOR


# ── regime-conditioned archetype reads (Decision 1, Option B) ──────────────────

async def test_archetype_regime_cell_is_separate_track_record(store_path):
    store = await _store(store_path)
    # same archetype, two regimes → independent records.
    await store.set_reputation("macro_bull", ARCHETYPE, 0.8, MIN_SAMPLES,
                               regime="STRONG_UPTREND", updated_at=_TS)
    await store.set_reputation("macro_bull", ARCHETYPE, 0.2, MIN_SAMPLES,
                               regime="STRONG_DOWNTREND", updated_at=_TS)
    assert await store.effective_archetype("macro_bull", "STRONG_UPTREND") == pytest.approx(0.8)
    assert await store.effective_archetype("macro_bull", "STRONG_DOWNTREND") == pytest.approx(0.2)


async def test_seasoned_regime_cell_is_used(store_path):
    store = await _store(store_path)
    await store.set_reputation("quant", ARCHETYPE, 0.7, MIN_SAMPLES,
                               regime="DOWNTREND", updated_at=_TS)
    assert await store.effective_archetype("quant", "DOWNTREND") == pytest.approx(0.7)


async def test_thin_regime_cell_falls_back_to_pooled(store_path):
    store = await _store(store_path)
    # regime cell too thin to use, but the pooled record is seasoned → use pooled.
    await store.set_reputation("geo_bear", ARCHETYPE, 0.9, MIN_SAMPLES - 1,
                               regime="UPTREND", updated_at=_TS)
    await store.set_reputation("geo_bear", ARCHETYPE, 0.6, MIN_SAMPLES,
                               regime="", updated_at=_TS)
    assert await store.effective_archetype("geo_bear", "UPTREND") == pytest.approx(0.6)


async def test_thin_cell_and_thin_pooled_falls_back_to_prior(store_path):
    store = await _store(store_path)
    await store.set_reputation("neutral_fund", ARCHETYPE, 0.9, MIN_SAMPLES - 1,
                               regime="UPTREND", updated_at=_TS)
    await store.set_reputation("neutral_fund", ARCHETYPE, 0.9, MIN_SAMPLES - 1,
                               regime="", updated_at=_TS)
    assert await store.effective_archetype("neutral_fund", "UPTREND") == REPUTATION_PRIOR


async def test_empty_regime_reads_pooled_directly(store_path):
    store = await _store(store_path)
    await store.set_reputation("macro_bull", ARCHETYPE, 0.65, MIN_SAMPLES,
                               regime="", updated_at=_TS)
    # no regime supplied → skip step 1, read the pooled record.
    assert await store.effective_archetype("macro_bull") == pytest.approx(0.65)


async def test_unseen_archetype_regime_returns_prior(store_path):
    store = await _store(store_path)
    assert await store.effective_archetype("macro_bull", "NEUTRAL") == REPUTATION_PRIOR

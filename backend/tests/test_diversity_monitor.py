"""Tests for monitoring/diversity_monitor.py — anti-monoculture measurement."""

from monitoring.diversity_monitor import (
    diversity_report,
    maybe_alert_monoculture,
    provider_family,
)


def _vote(vote, persona, provider):
    return {"vote": vote, "persona": persona, "provider": provider}


# ── Family collapsing ─────────────────────────────────────────────────────────

def test_groq_tiers_are_one_family():
    """groq-70b vs groq-8b is load balancing, not diversity."""
    assert provider_family("groq-70b") == provider_family("groq-8b") == "llama"


def test_gemini_and_openrouter_families():
    assert provider_family("gemini") == "gemini"
    assert provider_family("openrouter") == "openrouter"
    assert provider_family(None) is None


# ── Report basics ─────────────────────────────────────────────────────────────

def test_no_provider_data_unmeasured():
    """Legacy/mocked routers record provider=None — report stays honest."""
    votes = [_vote("bullish", "quant", None)] * 10
    report = diversity_report(votes)
    assert report["monoculture_risk"] == "UNMEASURED"
    assert report["diversity_score"] is None


def test_single_family_unmeasured():
    votes = [_vote("bullish", "quant", "groq-70b"), _vote("bearish", "neutral_fund", "groq-8b")]
    report = diversity_report(votes)
    assert report["monoculture_risk"] == "UNMEASURED"
    assert report["n_families"] == 1


def test_forced_personas_excluded():
    """macro_bull/geo_bear are persona-forced — they must not count."""
    votes = (
        [_vote("bullish", "macro_bull", "groq-70b")] * 10
        + [_vote("bearish", "geo_bear", "gemini")] * 10
    )
    report = diversity_report(votes)
    assert report["monoculture_risk"] == "UNMEASURED"  # zero free votes


# ── Convergence measurement ───────────────────────────────────────────────────

def test_total_convergence_flags_high_risk():
    """All families unanimously agree → monoculture wearing hats."""
    votes = (
        [_vote("bullish", "quant", "groq-70b")] * 4
        + [_vote("bullish", "neutral_fund", "groq-8b")] * 3
        + [_vote("bullish", "quant", "gemini")] * 4
    )
    report = diversity_report(votes)
    assert report["monoculture_risk"] == "HIGH"
    assert report["convergence"] == 1.0
    assert report["diversity_score"] == 0.0


def test_family_disagreement_is_low_risk():
    votes = (
        [_vote("bullish", "quant", "groq-70b")] * 4
        + [_vote("bearish", "quant", "gemini")] * 4
    )
    report = diversity_report(votes)
    assert report["monoculture_risk"] == "LOW"
    assert report["diversity_score"] == 1.0
    assert report["family_majorities"] == {"llama": "bullish", "gemini": "bearish"}


def test_weak_internal_consensus_reduces_convergence():
    """Families agree on majority but are internally split → less convergent."""
    votes = (
        [_vote("bullish", "quant", "groq-70b")] * 3
        + [_vote("bearish", "neutral_fund", "groq-8b")] * 2
        + [_vote("bullish", "quant", "gemini")] * 3
        + [_vote("neutral", "neutral_fund", "gemini")] * 2
    )
    report = diversity_report(votes)
    assert report["agreement_ratio"] == 1.0  # same majorities
    assert report["convergence"] < 0.85  # but internally contested
    assert report["monoculture_risk"] in ("LOW", "MODERATE")


def test_openrouter_fallback_counts_as_third_family():
    votes = (
        [_vote("bullish", "quant", "groq-70b")] * 3
        + [_vote("bullish", "quant", "gemini")] * 3
        + [_vote("bearish", "neutral_fund", "openrouter")] * 3
    )
    report = diversity_report(votes)
    assert report["n_families"] == 3
    # llama+gemini agree; each disagrees with openrouter → 1 of 3 pairs agree
    assert report["agreement_ratio"] == round(1 / 3, 3)


# ── Alerting ──────────────────────────────────────────────────────────────────

async def test_alert_only_fires_on_high(monkeypatch):
    fired = []

    async def fake_fire(*args, **kwargs):
        fired.append(args)
        return {"id": 1}

    import monitoring.alerts as alerts
    monkeypatch.setattr(alerts, "_fire_alert", fake_fire)

    await maybe_alert_monoculture({"monoculture_risk": "LOW"}, "BHP.AX")
    await maybe_alert_monoculture({"monoculture_risk": "UNMEASURED"}, "BHP.AX")
    assert fired == []

    await maybe_alert_monoculture(
        {"monoculture_risk": "HIGH", "convergence": 0.95, "n_families": 2,
         "family_majorities": {"llama": "bullish", "gemini": "bullish"}},
        "BHP.AX",
    )
    assert len(fired) == 1


async def test_alert_failure_is_swallowed(monkeypatch):
    import monitoring.alerts as alerts

    async def broken(*args, **kwargs):
        raise RuntimeError("alert db down")

    monkeypatch.setattr(alerts, "_fire_alert", broken)
    # must not raise
    await maybe_alert_monoculture({"monoculture_risk": "HIGH"}, "BHP.AX")

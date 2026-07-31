"""Tests for llm_router ensemble diversity — provider rotation per agent."""

import llm_router as llm_router_module
import pytest
from llm_router import LLMRouter


@pytest.fixture()
def router(monkeypatch):
    """Router with all three ensemble providers active (fake keys, no network)."""
    monkeypatch.setattr(llm_router_module, "_GROQ_API_KEY", "test-groq")
    monkeypatch.setattr(llm_router_module, "_GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(llm_router_module, "_OPENROUTER_API_KEY", "test-or")
    return LLMRouter()


def _names(providers):
    return [p["name"] for p in providers]


def test_ensemble_enabled_by_default(router, monkeypatch):
    monkeypatch.delenv("ENSEMBLE_DIVERSITY", raising=False)
    assert router.ensemble_enabled() is True


def test_ensemble_kill_switch(router, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_DIVERSITY", "0")
    assert router.ensemble_enabled() is False


def test_deep_pool_rotation_alternates_families(router):
    """Deep personas rotate between the two strong models by cohort."""
    order_0 = _names(router._ensemble_order(0, ("groq-70b", "gemini")))
    order_1 = _names(router._ensemble_order(1, ("groq-70b", "gemini")))
    assert order_0[0] == "groq-70b"
    assert order_1[0] == "gemini"
    # cohort 2 wraps back around
    order_2 = _names(router._ensemble_order(2, ("groq-70b", "gemini")))
    assert order_2[0] == "groq-70b"


def test_fast_pool_rotation_covers_three_families(router):
    firsts = {
        _names(router._ensemble_order(c, ("groq-8b", "groq-70b", "gemini")))[0]
        for c in range(3)
    }
    assert firsts == {"groq-8b", "groq-70b", "gemini"}


def test_openrouter_stays_in_fallback_tail(router):
    """openrouter (50 req/day) is never a rotation primary, always available as tail."""
    for cohort in range(6):
        order = _names(router._ensemble_order(cohort, ("groq-8b", "groq-70b", "gemini")))
        assert order[0] != "openrouter"
        assert "openrouter" in order  # still reachable as fallback


def test_full_chain_preserved_after_rotation(router):
    """Rotation reorders but never drops a provider."""
    order = _names(router._ensemble_order(1, ("groq-70b", "gemini")))
    assert sorted(order) == sorted(_names(router._active))


def test_empty_pool_falls_back_to_active(monkeypatch):
    """A router with none of the pool providers still returns a usable order."""
    monkeypatch.setattr(llm_router_module, "_GROQ_API_KEY", "")
    monkeypatch.setattr(llm_router_module, "_GEMINI_API_KEY", "")
    monkeypatch.setattr(llm_router_module, "_OPENROUTER_API_KEY", "test-or")
    router = LLMRouter()
    order = router._ensemble_order(0, ("groq-70b", "gemini"))
    assert _names(order) == ["openrouter"]


async def test_call_agent_vote_returns_text_and_provider(router, monkeypatch):
    """call_agent_vote surfaces which provider answered, for vote diagnostics."""
    captured = {}

    async def fake_fallback_ex(providers, system_message, user_prompt):
        captured["order"] = _names(providers)
        return "VOTE: bullish | REASON: test", providers[0]["name"]

    monkeypatch.setattr(router, "_call_with_fallback_ex", fake_fallback_ex)
    monkeypatch.setenv("ENSEMBLE_DIVERSITY", "1")

    text, provider = await router.call_agent_vote(
        "system", "user", persona="macro_bull", cohort=1, session_id="t"
    )
    assert "VOTE" in text
    assert provider == captured["order"][0]
    assert captured["order"][0] == "gemini"  # deep pool, cohort 1


async def test_call_agent_vote_legacy_order_when_disabled(router, monkeypatch):
    """With the kill switch on, fast personas get the legacy 8b-first order."""
    captured = {}

    async def fake_fallback_ex(providers, system_message, user_prompt):
        captured["order"] = _names(providers)
        return "VOTE: neutral | REASON: test", providers[0]["name"]

    monkeypatch.setattr(router, "_call_with_fallback_ex", fake_fallback_ex)
    monkeypatch.setenv("ENSEMBLE_DIVERSITY", "0")

    await router.call_agent_vote("system", "user", persona="quant", cohort=3, session_id="t")
    assert captured["order"][0] == "groq-8b"

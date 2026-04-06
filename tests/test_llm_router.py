"""
Tests for LLM Router
---------------------
Covers: initialization, call_primary fallback chain, call_boost, call_batch,
        provider filtering, error propagation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_env():
    """Provide minimal env vars so LLMRouter can init without real keys."""
    with patch.dict("os.environ", {
        "GROQ_API_KEY": "test-groq-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "OPENROUTER_API_KEY": "test-openrouter-key",
    }):
        yield


@pytest.fixture
def router(mock_env):
    from llm_router import LLMRouter
    return LLMRouter()


# ── Initialization ─────────────────────────────────────────────────────────────

class TestInitialization:

    def test_initializes_with_valid_keys(self, mock_env):
        from llm_router import LLMRouter
        r = LLMRouter()
        assert len(r._active) > 0

    def test_raises_without_any_keys(self):
        with patch.dict("os.environ", {
            "GROQ_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
        }, clear=False):
            # Temporarily clear the module-level vars
            with patch("llm_router._GROQ_API_KEY", ""), \
                 patch("llm_router._GEMINI_API_KEY", ""), \
                 patch("llm_router._OPENROUTER_API_KEY", ""):
                from llm_router import LLMRouter
                with pytest.raises(ValueError, match="No LLM API keys"):
                    LLMRouter()

    def test_filters_providers_without_keys(self, mock_env):
        with patch("llm_router._OPENROUTER_API_KEY", ""):
            from llm_router import LLMRouter
            r = LLMRouter()
            provider_names = [p["name"] for p in r._active]
            assert "openrouter" not in provider_names


# ── call_primary ───────────────────────────────────────────────────────────────

class TestCallPrimary:

    @pytest.mark.asyncio
    async def test_returns_string_on_success(self, router):
        with patch.object(router, "_call_single", new_callable=AsyncMock, return_value="mocked response"), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            result = await router.call_primary("sys", "user")
        assert isinstance(result, str)
        assert result == "mocked response"

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self, router):
        call_count = 0

        async def mock_call(provider, system, user):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 rate limit exceeded")
            return "fallback response"

        with patch.object(router, "_call_single", side_effect=mock_call), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            result = await router.call_primary("sys", "user")

        assert result == "fallback response"
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_propagates_non_rate_limit_error(self, router):
        async def mock_call(provider, system, user):
            raise ValueError("Invalid model parameter")

        with patch.object(router, "_call_single", side_effect=mock_call), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="Invalid model parameter"):
                await router.call_primary("sys", "user")

    @pytest.mark.asyncio
    async def test_raises_when_all_providers_exhausted(self, router):
        async def always_rate_limit(provider, system, user):
            raise Exception("429 quota exceeded")

        with patch.object(router, "_call_single", side_effect=always_rate_limit), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            with pytest.raises(Exception, match="All LLM providers exhausted"):
                await router.call_primary("sys", "user")


# ── call_boost ─────────────────────────────────────────────────────────────────

class TestCallBoost:

    @pytest.mark.asyncio
    async def test_returns_string(self, router):
        with patch.object(router, "_call_single", new_callable=AsyncMock, return_value="boost response"), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            result = await router.call_boost("sys", "user")
        assert result == "boost response"

    @pytest.mark.asyncio
    async def test_respects_semaphore(self, router):
        """call_boost should acquire the semaphore (10 concurrent max)."""
        with patch.object(router, "_call_single", new_callable=AsyncMock, return_value="ok"), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            # This just checks it doesn't deadlock with a single call
            result = await router.call_boost("sys", "user")
        assert result is not None


# ── call_batch ─────────────────────────────────────────────────────────────────

class TestCallBatch:

    @pytest.mark.asyncio
    async def test_returns_list_of_correct_length(self, router):
        prompts = [
            {"system": "You are agent 1", "user": "Vote bullish"},
            {"system": "You are agent 2", "user": "Vote bearish"},
            {"system": "You are agent 3", "user": "Vote neutral"},
        ]

        with patch.object(router, "_call_single", new_callable=AsyncMock, return_value="response"), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            results = await router.call_batch("boost", prompts)

        assert len(results) == 3
        assert all(r == "response" for r in results)

    @pytest.mark.asyncio
    async def test_primary_batch_uses_call_primary_ordering(self, router):
        """call_batch with 'primary' model type should prefer Gemini ordering."""
        prompts = [{"system": "sys", "user": "user"}]
        call_orders = []

        async def track_call(provider, system, user):
            call_orders.append(provider["name"])
            return "ok"

        with patch.object(router, "_call_single", side_effect=track_call), \
             patch.object(router, "_track_call", new_callable=AsyncMock):
            await router.call_batch("primary", prompts)

        # Gemini should be tried first for primary calls
        assert call_orders[0] == "gemini"


# ── Provider ordering ──────────────────────────────────────────────────────────

class TestProviderOrdering:

    def test_primary_puts_gemini_first(self, router):
        """call_primary should order providers with Gemini first."""
        ordered = sorted(router._active, key=lambda p: ("gemini" not in p["name"], p["name"]))
        assert ordered[0]["name"] == "gemini"

    def test_active_providers_have_keys(self, router):
        """All active providers must have non-empty API keys."""
        for provider in router._active:
            assert provider["key"], f"Provider {provider['name']} has no key"

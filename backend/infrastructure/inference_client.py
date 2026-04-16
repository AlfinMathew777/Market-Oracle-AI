"""Unified inference client — tier-routed LLM access with circuit breaker integration.

Wraps the existing LLMRouter with per-provider circuit breakers, explicit
timeouts, and a survival mode that falls back to minimal prompts when all
primary tiers are unavailable.

Provider tiers (mirrors llm_router.py):
  tier 1 — groq-70b  (fast, primary)
  tier 1 — groq-8b   (fast, secondary)
  tier 2 — openrouter (reliable mid-tier)
  tier 3 — gemini     (report generation + final fallback)

Usage::

    client = UnifiedInferenceClient()
    result = await client.complete(messages, timeout=30)
    if result.success:
        print(result.content)
    else:
        print(result.error)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from infrastructure.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    success: bool
    content: str
    provider_used: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    survival_mode: bool = False


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str
    tier: int
    timeout: float = 30.0
    max_tokens: int = 4000


@dataclass
class HealthStatus:
    provider: str
    tier: int
    circuit_state: str
    available: bool


class UnifiedInferenceClient:
    """Routes completion requests through tiered providers with circuit breakers."""

    # Default survival-mode prompt prefix injected when all tier-1/2 fail
    _SURVIVAL_PREFIX = (
        "CONDENSED REQUEST — answer in under 200 words. "
        "Respond with a valid JSON object only.\n\n"
    )

    def __init__(self, providers: Optional[List[ProviderConfig]] = None) -> None:
        if providers is None:
            providers = self._default_providers()

        # Only register providers that have an API key
        self._providers: List[ProviderConfig] = [p for p in providers if p.api_key]
        self._breakers: Dict[str, CircuitBreaker] = {
            p.name: CircuitBreaker(p.name, failure_threshold=3, recovery_timeout=60.0)
            for p in self._providers
        }
        logger.info(
            "[InferenceClient] Active providers: %s",
            ", ".join(p.name for p in self._providers),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tier_preference: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> CompletionResult:
        """Run completion with automatic tier fallback and circuit breaker protection."""
        ordered = self._order_providers(tier_preference)
        survival = False

        for provider in ordered:
            breaker = self._breakers[provider.name]
            if not await breaker.can_proceed():
                logger.debug("[InferenceClient] Skipping %s — circuit OPEN", provider.name)
                continue

            effective_timeout = timeout or provider.timeout
            effective_messages = messages
            if survival:
                effective_messages = self._apply_survival_mode(messages)

            start = time.monotonic()
            try:
                content = await self._call(provider, effective_messages, effective_timeout)
                await breaker.record_success()
                return CompletionResult(
                    success=True,
                    content=content,
                    provider_used=provider.name,
                    latency_ms=round((time.monotonic() - start) * 1000, 1),
                    survival_mode=survival,
                )
            except asyncio.TimeoutError:
                logger.warning("[InferenceClient] %s timed out after %.0fs", provider.name, effective_timeout)
                await breaker.record_failure()
            except Exception as exc:
                msg = str(exc)
                if any(x in msg for x in ("429", "rate", "quota", "overloaded")):
                    logger.warning("[InferenceClient] %s rate-limited: %s", provider.name, msg[:80])
                    await breaker.record_failure()
                else:
                    logger.error("[InferenceClient] %s error: %s", provider.name, msg[:200])
                    await breaker.record_failure()

            # Activate survival mode after tier-1/2 providers are all exhausted
            if not survival and all(
                p.tier >= 3 or not await self._breakers[p.name].can_proceed()
                for p in ordered
                if p.name != provider.name
            ):
                survival = True
                logger.warning("[InferenceClient] Activating survival mode")

        return CompletionResult(
            success=False,
            content="",
            error="All LLM providers exhausted",
        )

    def get_available_providers(self) -> List[str]:
        """Return names of providers whose circuit is not OPEN."""
        return [
            p.name
            for p in self._providers
            if self._breakers[p.name].state != CircuitState.OPEN
        ]

    def get_provider_health(self) -> Dict[str, HealthStatus]:
        return {
            p.name: HealthStatus(
                provider=p.name,
                tier=p.tier,
                circuit_state=self._breakers[p.name].state.value,
                available=self._breakers[p.name].state != CircuitState.OPEN,
            )
            for p in self._providers
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _order_providers(self, tier_preference: Optional[int]) -> List[ProviderConfig]:
        """Sort providers: preferred tier first, then by tier ascending."""
        if tier_preference is not None:
            return sorted(
                self._providers,
                key=lambda p: (0 if p.tier == tier_preference else p.tier),
            )
        return sorted(self._providers, key=lambda p: p.tier)

    async def _call(
        self,
        provider: ProviderConfig,
        messages: List[Dict[str, str]],
        timeout: float,
    ) -> str:
        from openai import AsyncOpenAI

        extra_headers: Dict[str, str] = {}
        if provider.name == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://aussieintel.app",
                "X-Title": "AussieIntel",
            }

        client = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=provider.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=provider.max_tokens,
                extra_headers=extra_headers,
            ),
            timeout=timeout,
        )
        return response.choices[0].message.content

    @staticmethod
    def _apply_survival_mode(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Prepend survival-mode instruction to the first user message."""
        result = []
        prepended = False
        for msg in messages:
            if msg.get("role") == "user" and not prepended:
                result.append({"role": "user", "content": UnifiedInferenceClient._SURVIVAL_PREFIX + msg["content"]})
                prepended = True
            else:
                result.append(msg)
        return result

    @staticmethod
    def _default_providers() -> List[ProviderConfig]:
        return [
            ProviderConfig(
                name="groq-70b",
                base_url="https://api.groq.com/openai/v1",
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                api_key=os.getenv("GROQ_API_KEY", ""),
                tier=1,
                timeout=30.0,
                max_tokens=4000,
            ),
            ProviderConfig(
                name="groq-8b",
                base_url="https://api.groq.com/openai/v1",
                model="llama-3.1-8b-instant",
                api_key=os.getenv("GROQ_API_KEY", ""),
                tier=1,
                timeout=30.0,
                max_tokens=4000,
            ),
            ProviderConfig(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                model="auto",
                api_key=os.getenv("OPENROUTER_API_KEY", ""),
                tier=2,
                timeout=45.0,
                max_tokens=4000,
            ),
            ProviderConfig(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                api_key=os.getenv("GEMINI_API_KEY", ""),
                tier=3,
                timeout=60.0,
                max_tokens=2000,
            ),
        ]

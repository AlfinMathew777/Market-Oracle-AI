"""LLM Router — 4-tier fallback chain for zero-downtime free-tier usage.

Tier 1: Groq llama-3.3-70b-versatile  (14,400 req/day — primary, fastest)
Tier 2: Groq llama-3.1-8b-instant      (separate 14,400 req/day quota — fast fallback)
Tier 3: OpenRouter auto                 (50 req/day free — gap coverage)
Tier 4: Gemini gemini-2.0-flash         (1,500 req/day — report gen + final fallback)

On 429 from any tier: automatically advance to next tier, no sleep between tiers.
"""

import os
import json
import asyncio
import logging
from datetime import date
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
_GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Configurable agent count (default 30 for quota efficiency; 50 for full demo)
NUM_AGENTS = int(os.getenv("NUM_AGENTS", "30"))


class LLMRouter:
    """Routes simulation calls through a 4-tier free-tier provider chain."""

    def __init__(self):
        self.providers = [
            {
                "name": "groq-70b",
                "base": "https://api.groq.com/openai/v1",
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "key": _GROQ_API_KEY,
                "rpm": 30,
            },
            {
                "name": "groq-8b",
                "base": "https://api.groq.com/openai/v1",
                "model": "llama-3.1-8b-instant",   # separate daily quota from 70b
                "key": _GROQ_API_KEY,
                "rpm": 30,
            },
            {
                "name": "openrouter",
                "base": "https://openrouter.ai/api/v1",
                "model": "auto",
                "key": _OPENROUTER_API_KEY,
                "rpm": 60,
            },
            {
                "name": "gemini",
                "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                "key": _GEMINI_API_KEY,
                "rpm": 15,
            },
        ]

        # Filter to providers that have keys configured
        self._active = [p for p in self.providers if p["key"]]
        if not self._active:
            raise ValueError("No LLM API keys found. Set at least one of: GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY")

        # Limit concurrent calls to avoid burst rate-limit hits (Groq: 30 RPM)
        self._semaphore = asyncio.Semaphore(10)

        logger.info(
            "LLM Router initialized — active providers: %s",
            ", ".join(p["name"] for p in self._active),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def call_primary(self, system_message: str, user_prompt: str, session_id: str = "primary") -> str:
        """Report generation: Gemini first (best structure), falls back through chain."""
        # For primary/report calls prefer Gemini then Groq-70b
        ordered = sorted(self._active, key=lambda p: ("gemini" not in p["name"], p["name"]))
        return await self._call_with_fallback(ordered, system_message, user_prompt)

    async def call_boost(self, system_message: str, user_prompt: str, session_id: str = "boost") -> str:
        """Agent simulation: Groq-70b first (fastest), falls back through chain."""
        async with self._semaphore:
            return await self._call_with_fallback(self._active, system_message, user_prompt)

    async def call_batch(self, model_type: str, prompts: List[Dict[str, str]]) -> List[str]:
        """Run many prompts concurrently — used for 50-agent simulation."""
        tasks = [
            self.call_boost(p["system"], p["user"], session_id=f"agent_{i}")
            if model_type == "boost"
            else self.call_primary(p["system"], p["user"], session_id=f"agent_{i}")
            for i, p in enumerate(prompts)
        ]
        return await asyncio.gather(*tasks)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call_with_fallback(self, providers: list, system_message: str, user_prompt: str) -> str:
        """Try each provider in order; advance on 429 / missing key."""
        last_error = None
        for provider in providers:
            if not provider["key"]:
                continue
            try:
                result = await self._call_single(provider, system_message, user_prompt)
                await self._track_call(provider["name"])
                return result
            except Exception as e:
                msg = str(e)
                if any(x in msg for x in ("429", "rate", "quota", "overloaded")):
                    logger.warning("Provider %s rate-limited — trying next tier", provider["name"])
                    last_error = e
                    continue
                raise   # non-rate-limit errors propagate immediately
        raise Exception(f"All LLM providers exhausted. Last error: {last_error}")

    async def _call_single(self, provider: dict, system_message: str, user_prompt: str) -> str:
        """OpenAI-compatible chat completion call for all providers."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=provider["key"], base_url=provider["base"])
        model = provider["model"]

        # OpenRouter requires HTTP-Referer header for free tier
        extra_headers = {}
        if provider["name"] == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://aussieintel.app",
                "X-Title": "AussieIntel",
            }

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                extra_headers=extra_headers,
            ),
            timeout=30.0,  # Per-agent API call timeout
        )
        return response.choices[0].message.content

    async def _track_call(self, provider_name: str) -> None:
        """Increment daily call counter in Redis (best-effort, non-blocking)."""
        try:
            from services.redis_client import incr
            today = date.today().isoformat()
            await incr(f"llm:calls:{provider_name}:{today}")
        except Exception as e:
            logger.debug("LLM call tracking failed for %s (best-effort): %s", provider_name, e)


# ── JSON parsing utility ──────────────────────────────────────────────────────

def parse_json_response(response: str) -> Dict[str, Any]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end != -1:
            try:
                return json.loads(response[start:end].strip())
            except json.JSONDecodeError:
                pass

    start_idx = response.find("{")
    end_idx = response.rfind("}") + 1
    if start_idx != -1 and end_idx > start_idx:
        try:
            return json.loads(response[start_idx:end_idx])
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(response.replace(",}", "}").replace(",]", "]"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM response: {e}")


if __name__ == "__main__":
    async def test():
        router = LLMRouter()
        print("Testing boost (agent simulation)...")
        r = await router.call_boost("You are a helpful assistant.", "Say: Hello from AussieIntel!")
        print(f"Response: {r[:100]}")

    asyncio.run(test())

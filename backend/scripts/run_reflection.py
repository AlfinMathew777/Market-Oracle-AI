"""Reflection Script — Upgrade 5b

Runs daily at 4:30 PM AEST (scheduled as a Railway/Render cron job).

Steps:
  1. Fetch all unresolved predictions from prediction_log
  2. Fetch actual closing price from yfinance
  3. Calculate actual_direction and actual_price_change_pct
  4. Fetch top 3 BHP news headlines from MarketAux (last 24h)
  5. Call Groq API with reflection prompt → parse lesson
  6. Write results back to prediction_log
  7. Lessons are auto-injected into next simulation via market_context.fetch_lessons()

Schedule (Railway cron):
  0 6 * * 1-5   (06:00 UTC = 16:00/17:00 AEST Mon-Fri)

Usage:
  python scripts/run_reflection.py
  python scripts/run_reflection.py --ticker BHP.AX --limit 10
"""

import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_MARKETAUX_KEY = os.getenv("MARKETAUX_API_KEY", "")
_GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
_GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")


# ── Fetch actual price ─────────────────────────────────────────────────────────

async def _fetch_actual_price(ticker: str) -> Optional[Dict[str, float]]:
    """Get yesterday's close and today's close for the ticker."""
    try:
        import yfinance as yf
        info    = yf.Ticker(ticker).fast_info
        current = getattr(info, "last_price", None)
        prev    = getattr(info, "previous_close", None)
        if current and prev and prev > 0:
            change_pct = (current - prev) / prev * 100
            return {
                "current_price": round(float(current), 4),
                "prev_close":    round(float(prev), 4),
                "change_pct":    round(change_pct, 4),
            }
    except Exception as e:
        logger.warning("yfinance price fetch failed for %s: %s", ticker, e)
    return None


def _actual_direction(change_pct: float) -> str:
    if change_pct > 0.5:
        return "bullish"
    elif change_pct < -0.5:
        return "bearish"
    else:
        return "neutral"


# ── Fetch recent news ──────────────────────────────────────────────────────────

async def _fetch_news_headlines(ticker: str, limit: int = 3) -> List[str]:
    """Fetch recent news headlines for reflection context."""
    if not _MARKETAUX_KEY:
        return []
    try:
        import httpx
        symbol  = ticker.replace(".AX", "")
        cutoff  = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.marketaux.com/v1/news/all",
                params={"symbols": symbol, "published_after": cutoff,
                        "api_token": _MARKETAUX_KEY, "limit": limit}
            )
            r.raise_for_status()
            articles = r.json().get("data", [])
            return [a.get("title", "") for a in articles if a.get("title")]
    except Exception as e:
        logger.warning("MarketAux headlines failed for %s: %s", ticker, e)
        return []


# ── Reflection LLM call ────────────────────────────────────────────────────────

REFLECTION_PROMPT_SYSTEM = (
    "You are a quantitative prediction analyst running a post-trade reflection. "
    "You will receive a prediction, its outcome, and today's news. "
    "Answer concisely and return ONLY valid JSON — no markdown, no explanation outside the JSON."
)

REFLECTION_PROMPT_USER = """A prediction was made for {ticker}:

Predicted:     {predicted_direction} with {confidence_pct:.1f}% confidence
Primary reason given: "{primary_reason}"
Actual outcome: price moved {actual_price_change_pct:+.2f}% ({actual_direction})
Top news today about {ticker}:
{news_headlines}

Answer these questions:
1. Was the prediction correct? (yes/no)
2. Was the PRIMARY REASON cited actually reflected in today's news? (yes/no/partial)
3. What was the actual primary driver of today's move?
4. In one sentence, what should the system remember for next time it predicts {ticker}?

Return ONLY this JSON (no other text):
{{
  "correct": true|false,
  "reason_matched": "yes"|"no"|"partial",
  "actual_driver": "string",
  "lesson": "string — one sentence for the system to remember"
}}"""


async def _call_llm_reflection(prompt_vars: dict) -> Optional[Dict[str, Any]]:
    """Call Groq (primary) → Gemini (fallback) for reflection."""
    user_prompt = REFLECTION_PROMPT_USER.format(**prompt_vars)

    # Try Groq first
    if _GROQ_KEY:
        try:
            from openai import AsyncOpenAI
            client   = AsyncOpenAI(api_key=_GROQ_KEY, base_url="https://api.groq.com/openai/v1")
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": REFLECTION_PROMPT_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            raw = response.choices[0].message.content
            return _parse_reflection_json(raw)
        except Exception as e:
            logger.warning("Groq reflection failed: %s", e)

    # Gemini fallback
    if _GEMINI_KEY:
        try:
            from openai import AsyncOpenAI
            client   = AsyncOpenAI(
                api_key=_GEMINI_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            response = await client.chat.completions.create(
                model="gemini-2.0-flash",
                messages=[
                    {"role": "system", "content": REFLECTION_PROMPT_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            raw = response.choices[0].message.content
            return _parse_reflection_json(raw)
        except Exception as e:
            logger.warning("Gemini reflection failed: %s", e)

    return None


def _parse_reflection_json(raw: str) -> Optional[Dict[str, Any]]:
    import json
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Extract from markdown block
    if "```json" in raw:
        start = raw.find("```json") + 7
        end   = raw.find("```", start)
        if end != -1:
            try:
                return json.loads(raw[start:end].strip())
            except Exception:
                pass
    # Bare JSON extraction
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except Exception:
            pass
    logger.warning("Could not parse reflection JSON from: %s", raw[:200])
    return None


# ── Main reflection loop ───────────────────────────────────────────────────────

async def run_reflection(ticker_filter: Optional[str] = None, limit: int = 20) -> int:
    """
    Main reflection loop.
    Returns number of predictions successfully reflected.
    """
    from database import get_unresolved_predictions, update_prediction_resolution, init_db
    await init_db()

    logger.info("=== REFLECTION RUN STARTED %s ===", datetime.now(timezone.utc).isoformat())

    # Step 1: fetch unresolved predictions
    pending = await get_unresolved_predictions(ticker=ticker_filter, limit=limit)
    if not pending:
        logger.info("No unresolved predictions found. Exiting.")
        return 0

    logger.info("Found %d unresolved predictions to reflect on.", len(pending))

    # Pre-fetch prices and news per unique ticker (avoid duplicate API calls)
    unique_tickers = list(set(p["ticker"] for p in pending))
    price_cache: Dict[str, Optional[Dict]] = {}
    news_cache:  Dict[str, List[str]]      = {}

    for t in unique_tickers:
        price_cache[t] = await _fetch_actual_price(t)
        news_cache[t]  = await _fetch_news_headlines(t, limit=3)
        logger.info("Fetched data for %s: price=%s news=%d headlines",
                    t, price_cache[t], len(news_cache[t]))

    reflected = 0
    for pred in pending:
        pred_id   = pred["id"]
        ticker    = pred["ticker"]
        price_data = price_cache.get(ticker)

        if not price_data:
            logger.warning("No price data for %s — skipping %s", ticker, pred_id)
            continue

        change_pct      = price_data["change_pct"]
        actual_dir      = _actual_direction(change_pct)
        predicted_dir   = pred.get("predicted_direction", "neutral")
        confidence      = float(pred.get("confidence") or 0)
        primary_reason  = pred.get("primary_reason") or "No primary reason recorded"
        headlines       = news_cache.get(ticker, [])
        news_str        = "\n".join(f"- {h}" for h in headlines) if headlines else "  (no news found)"

        # Step 5: Call LLM reflection
        reflection = await _call_llm_reflection({
            "ticker":                  ticker,
            "predicted_direction":     predicted_dir,
            "confidence_pct":          confidence * 100,
            "primary_reason":          primary_reason,
            "actual_price_change_pct": change_pct,
            "actual_direction":        actual_dir,
            "news_headlines":          news_str,
        })

        if not reflection:
            # Fallback: write basic fields without lesson
            reflection = {
                "correct":        (predicted_dir == actual_dir),
                "reason_matched": "no",
                "actual_driver":  "LLM unavailable — derived from price action only",
                "lesson":         f"{ticker} moved {change_pct:+.2f}% ({actual_dir}). Predicted {predicted_dir}.",
            }

        correct        = bool(reflection.get("correct", False))
        reason_matched = str(reflection.get("reason_matched", "no")).lower() in ("yes", "partial")
        actual_driver  = str(reflection.get("actual_driver", ""))[:500]
        lesson         = str(reflection.get("lesson", ""))[:1000]

        # Step 6: Write back to prediction_log
        await update_prediction_resolution(
            prediction_id            = pred_id,
            actual_direction         = actual_dir,
            actual_close_price       = price_data.get("current_price", 0),
            actual_price_change_pct  = change_pct,
            prediction_correct       = correct,
            actual_driver            = actual_driver,
            reason_matched           = reason_matched,
            lesson                   = lesson,
            resolved_at              = datetime.now(timezone.utc).isoformat(),
            resolution_notes         = f"Price {price_data.get('prev_close')} → {price_data.get('current_price')} ({change_pct:+.2f}%)",
        )

        logger.info(
            "[%s] %s | predicted=%s actual=%s | correct=%s | lesson: %s",
            pred_id, ticker, predicted_dir, actual_dir, correct, lesson[:80]
        )
        reflected += 1

    logger.info("=== REFLECTION RUN COMPLETE: %d/%d reflected ===", reflected, len(pending))
    return reflected


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Market Oracle AI — Daily Reflection Script")
    parser.add_argument("--ticker", type=str, default=None, help="Filter to specific ticker (e.g. BHP.AX)")
    parser.add_argument("--limit",  type=int, default=20,   help="Max predictions to process (default 20)")
    args = parser.parse_args()

    count = asyncio.run(run_reflection(ticker_filter=args.ticker, limit=args.limit))
    print(f"\nReflection complete: {count} predictions updated.")
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()

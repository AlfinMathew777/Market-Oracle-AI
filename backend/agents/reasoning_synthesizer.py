"""
Reasoning Synthesizer Agent
---------------------------
Final-stage agent that aggregates specialist agent votes and produces
structured, explainable stock predictions with causal reasoning.

Sits at the END of the pipeline — called after all specialist agents have voted.
Uses LLMRouter (call_primary) for structured report generation.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from llm_router import LLMRouter, parse_json_response
from agents.reasoning_validator import reasoning_validator
from agents.sector_prompts import get_sector_system_prompt
from utils.sector_classifier import filter_signals_for_sector
from models.reasoning_output import (
    Direction,
    ImpactType,
    ReasoningOutput,
    Recommendation,
    Stability,
    Strength,
)

logger = logging.getLogger(__name__)


class TriggerClassifier:
    """
    Classifies news trigger materiality so the LLM is told upfront whether
    it's analysing a real event or a stock commentary article.
    """

    # Patterns that flag an article as non-material commentary
    _NON_MATERIAL: List[str] = [
        "shares to dig into", "stocks to watch", "stocks to buy", "stocks to consider",
        "investment ideas", "portfolio picks", "analyst picks", "top picks",
        "why i think", "my view on", "opinion:", "commentary:",
        "history of", "how to invest", "beginner's guide", "what is",
        "top 10", "5 best", "3 reasons", "2 asx shares", "asx shares to",
        "worth watching", "on my watchlist", "should you buy",
    ]

    # Patterns that flag a material event
    _MATERIAL: List[str] = [
        "price surge", "price drop", "price crash", "rallies", "plunges", "jumps",
        "announces", "reports", "earnings", "dividend", "acquisition", "merger",
        "guidance", "production update", "quarterly report", "half year", "full year",
        "government announces", "policy change", "regulation", "tariff", "sanction",
        "production cut", "shipment", "outage", "disruption", "expansion",
        "upgrade", "downgrade", "rating", "target price",
    ]

    @classmethod
    def classify(cls, headline: str, summary: str = "") -> Dict[str, Any]:
        """
        Returns:
            {
                "materiality": "LOW" | "MEDIUM" | "HIGH",
                "type": "commentary" | "news" | "event",
                "preamble": str | None  — text to prepend to LLM user prompt
            }
        """
        text = f"{headline} {summary}".lower()

        for pattern in cls._NON_MATERIAL:
            if pattern in text:
                return {
                    "materiality": "LOW",
                    "type": "commentary",
                    "preamble": (
                        f"NOTE: The trigger '{headline}' appears to be a stock analysis article, "
                        "not a material event. There is no direct operational catalyst. "
                        "Assess only on market signals and technicals; event classification "
                        "should be 'Noise / Low Relevance'."
                    ),
                }

        for pattern in cls._MATERIAL:
            if pattern in text:
                return {"materiality": "HIGH", "type": "event", "preamble": None}

        return {"materiality": "MEDIUM", "type": "news", "preamble": None}


_SYSTEM_PROMPT = """
#################################################
# MANDATORY OUTPUT FORMAT — READ BEFORE ANYTHING
#################################################

Your output MUST follow these EXACT templates. Non-compliance = rejection.

## TEMPLATE 1: sentiment_impact (REQUIRED FORMAT)

sentiment_impact MUST use this EXACT structure:
"RSI at [X.X] ([LABEL]). Volume at [X.XX]x avg ([LABEL]). [Rest of analysis]."

Where:
- [X.X]    = the RSI value from market_signals (e.g., 73.4)
- [LABEL]  = "OVERBOUGHT — pullback risk elevated" if RSI > 70
             "OVERSOLD — reversal potential" if RSI < 30
             "neutral range" if RSI 30–70
- [X.XX]x  = the volume_ratio from market_signals (e.g., 0.62x)
- [LABEL]  = "LIGHT — weak conviction" if volume < 0.7x
             "HIGH — strong conviction" if volume > 1.5x
             "normal" if volume 0.7–1.5x

EXAMPLE (RSI=73.4, volume=0.62x):
"RSI at 73.4 (OVERBOUGHT — pullback risk elevated). Volume at 0.62x avg (LIGHT — weak conviction). No event-driven sentiment from trigger."

## TEMPLATE 2: revenue_impact (REQUIRED FORMAT)

revenue_impact MUST BEGIN with:
"Iron ore at $[PRICE]/t ([CHANGE]%). AUD/USD at [RATE] ([CHANGE]%). [Rest of analysis]."

EXAMPLE (iron_ore=106.63, aud_usd=0.7062):
"Iron ore at $106.63/t (+0.34%). AUD/USD at 0.7062 (-0.19%). Court ruling does not directly affect commodity prices."

## REJECTION RULES

Your response will be REJECTED if:
- sentiment_impact does NOT start with "RSI at [number]"
- revenue_impact does NOT start with "Iron ore at $[number]"
- Any impact field contains "No data — assumed neutral" or "assumed neutral impact"

#################################################
# REST OF SYSTEM PROMPT FOLLOWS
#################################################

You are a senior mining equity analyst specialising in Australian resource stocks (ASX: BHP, RIO, FMG, WDS, STO, CBA). Your role is to synthesise market intelligence into precise, mechanistic, quantified reasoning.

You MUST follow the 8-step reasoning pipeline below and output ONLY valid JSON.

---

## CRITICAL ANTI-HALLUCINATION RULES — READ BEFORE ANYTHING ELSE

### RULE 1: INPUT-ONLY POLICY
You are ONLY permitted to reference information explicitly provided in the input:
- The exact trigger event headline and summary
- The market signals JSON (iron ore price, AUD/USD, RSI, volume, etc.)
- The agent consensus data

You are PROHIBITED from:
- Inventing geopolitical events (Iran, Russia, Ukraine, China tensions, etc.) unless EXPLICITLY in the trigger
- Fabricating news, announcements, or corporate actions
- Adding stabilising or destabilising context not in the input
- Referencing shipping routes, chokepoints, or supply disruptions unless mentioned in trigger

Violation = output rejected, confidence set to 0%.

### RULE 2: CLASSIFY FROM HEADLINE WORDS ONLY — NO TOPIC INFERENCE
You MUST classify the trigger event based ONLY on the literal words in the headline.

FORBIDDEN: Inferring a topic because the article is ABOUT a company.
EXAMPLE: Headline "Easy way to value BHP shares" → This is a VALUATION ARTICLE, NOT an iron ore event.
Do NOT set domains = ["iron_ore", "china"] just because BHP is an iron ore company.
Do NOT set event_classification.type = "Direct Impact" just because the stock ticker is mentioned.

COMMENTARY DETECTION — these headline patterns = "Noise / Low Relevance" (confidence_score = 5):
"easy way to", "how to value", "stocks to watch", "shares to watch", "stocks to buy",
"shares to consider", "best stocks", "top picks", "should you buy", "is it time to buy",
"versus", " vs ", "comparing", "my view", "opinion:", "why i think", "deep dive",
"closer look", "fair value", "intrinsic value", "valuation method", "case for buying",
"history of", "beginner guide", "how to invest", "undervalued or overvalued"

For commentary / opinion articles you MUST:
- Set event_classification.type = "Noise / Low Relevance", strength = "Low"
- Set domains = ["commentary"]
- Set ALL causal impact fields to: "NO DATA: Trigger is a commentary article, not an operational catalyst"
- Set final_decision.direction = "Neutral", confidence_score = 5, recommendation = "WAIT"

### RULE 3: TICKER RELEVANCE + FORBIDDEN COMMENTARY PHRASES
If the trigger headline mentions specific tickers but you are analysing a DIFFERENT ticker:
- Set event_classification.type = "Noise / Low Relevance", confidence_score = 5
- Explain in summary: "Trigger discusses [mentioned tickers], not [target ticker]"

FORBIDDEN PHRASES — never write these under ANY circumstance:
- "discusses [company] in the context of oil markets"
- "discusses [company] as part of the geopolitical landscape"
- "discusses [company] in the context of [anything not in the headline]"
- "part of the broader geopolitical event"
- "this [company] is discussed in relation to [topic not in headline]"
- Any sentence that assigns the article to a domain/topic not literally present in the headline words

### RULE 4: NO TAUTOLOGIES + MANDATORY RSI/VOLUME CITATION
Never write causal chains where X leads to X:
BANNED: "Stable oil prices may lead to stable energy costs"
BANNED: "Steady iron ore prices indicate stable demand"
REQUIRED: "Oil at $78.50/bbl (-2.1% WoW) reduces diesel costs by ~$0.50/t for Pilbara haulage"

MANDATORY: If RSI or volume_ratio data is provided in the input signals:
- sentiment_impact MUST start with the exact RSI value: "RSI at [exact number] ([overbought/neutral/oversold])."
- If volume_ratio is also provided: follow immediately with "Volume at [exact ratio]x avg ([elevated/normal/light])."
- Omitting a provided RSI/volume value = automatic -10% confidence penalty

### RULE 5: CONFIDENCE HARD CAPS
- Maximum possible confidence: 85%
- Commentary article trigger: Maximum 5%
- Irrelevant ticker trigger: Maximum 5%
- Missing iron ore price data: Maximum 45%
- Missing RSI data: Maximum 55%

---

## MANDATORY: TECHNICAL DATA CITATION RULES

### UNDERSTANDING YOUR DATA SOURCES

You receive TWO types of data in every request:

1. **EVENT DATA** (from trigger headline/summary) — may be empty or irrelevant
2. **TECHNICAL DATA** (from market_signals JSON) — RSI, volume, iron ore, AUD/USD — ALWAYS present

You MUST cite technical data even when the trigger is commentary/noise.

### NEVER WRITE "No data" FOR sentiment_impact

The market_signals JSON always contains RSI and volume. There is no excuse for "No data" in sentiment_impact.

EXACT REQUIRED FORMAT:
```
"RSI at [VALUE] ([LABEL]). Volume at [VALUE]x avg ([LABEL]). [Event sentiment or 'No event-driven sentiment from trigger.']"
```

RSI labels:
- RSI > 70 → "OVERBOUGHT — pullback risk elevated"
- RSI < 30 → "OVERSOLD — reversal potential"
- RSI 30–70 → "neutral range"

Volume labels:
- Volume < 0.7x → "LIGHT — weak conviction"
- Volume > 1.5x → "HIGH — strong conviction"
- Volume 0.7–1.5x → "normal"

EXAMPLES:

Commentary trigger + overbought RSI:
```json
{"sentiment_impact": "RSI at 73.4 (OVERBOUGHT — pullback risk elevated). Volume at 0.62x avg (LIGHT — weak conviction). No event-driven sentiment from trigger."}
```

Material event + normal technicals:
```json
{"sentiment_impact": "RSI at 55.2 (neutral range). Volume at 1.1x avg (normal). Event sentiment: positive — earnings beat expectations."}
```

### SAME RULE FOR OTHER IMPACT FIELDS WITH COMMENTARY TRIGGERS

For commentary/irrelevant triggers use these exact phrases (NOT "No data — assumed neutral"):

- cost_impact: "No event-driven cost impact from trigger."
- revenue_impact: "Iron ore at $[X]/t ([+/-]%). AUD/USD at [X]. No event-driven revenue impact from trigger."
- demand_impact: "No event-driven demand signal from trigger."

---

## LANGUAGE RULES — MANDATORY

### BANNED PHRASES — never write these:
- "does not have significant impact due to neutral context"
- "remains neutral due to ongoing geopolitical event"
- "no clear evidence for a shift"
- "assumed neutral impact"
- "lack of clear bullish or bearish sentiment"
- "does not directly impact"
- "no significant impact at this time"
- "unclear at this time"

### INSTEAD — always be mechanistic and specific:
- Name the EXACT mechanism: "Iron ore at $107/t is 5% below the $113/t 6-month average → margin compression of ~$3/t at 350Mt annual run-rate"
- Quantify when data is provided: "AUD/USD at 0.69 vs 0.72 budget = 4% headwind on USD-denominated revenue"
- If data is absent, say explicitly: "NO DATA: Iron ore futures curve unavailable — cannot assess forward demand signal"

### REQUIRED FORMAT FOR EACH CAUSAL CHAIN FIELD:

**cost_impact**: Must name a real cost driver — energy/diesel/freight/labour/maintenance. Example: "Diesel at $1.45/L (+3% MoM) adds ~$0.50/t to Pilbara haulage. Shipping rates stable at $18/t WA→China. Net: minor margin compression (-1%)."

**revenue_impact**: Must reference commodity price, volume, FX, or contract. Example: "Iron ore spot at $118.50/t (+2.3% vs last week). AUD/USD 0.692 translates to A$171/t realised. At 72Mt quarterly volume: ~$12.3B revenue run-rate. Net: marginally bullish."

**demand_impact**: Must reference China PMI, steel output, construction, or inventories. Example: "China Caixin Manufacturing PMI 49.7 (sub-50 = contraction). Port Hedland iron ore inventories at 148Mt (+6Mt MoM). Steel mill capacity utilisation 78% (below 82% prior year). Net: bearish demand signal."

**sentiment_impact**: Must reference a specific technical level, fund flow, or positioning indicator. Example: "BHP trading at 14.2x forward P/E vs 5yr average 13.8x — slight premium. RSI 52 neutral zone. No significant options positioning shifts noted. Net: neutral sentiment."

---

## CAUSAL LOGIC RULES — EVENT TYPE CONSTRAINTS

### LEGAL / COURT EVENTS
For triggers about lawsuits, court rulings, evidence disputes, settlements:

- cost_impact: "No direct cost impact from legal proceedings. [Cite any cost data available] Operations unaffected."
- revenue_impact: "Iron ore at $[X]/t ([chg]%). AUD/USD at [X]. Legal proceedings do not affect commodity prices or export revenue."
- demand_impact: "No demand signal from trigger. Chinese steel demand is driven by construction/infrastructure, not Australian court outcomes."
- sentiment_impact: "RSI at [X] ([label]). Volume at [X]x avg ([label]). Legal [win/loss] may [reduce/increase] litigation risk, creating short-term [positive/negative] investor sentiment."

Legal events affect: investor sentiment, future liability risk, management bandwidth
Legal events DO NOT affect: iron ore spot price, Chinese steel demand, AUD/USD, production costs

FORBIDDEN for legal triggers:
- "may positively impact iron ore prices" (courts do not set commodity prices)
- "may increase Chinese steel mill demand" (China is unaffected by Australian court rulings)
- "reduces risk of supply disruptions" (evidence exclusions do not affect mining operations)
- "may affect production volumes" (unless the ruling explicitly orders an operational halt)

### ANALYST / RATING EVENTS
For triggers about analyst upgrades/downgrades, price target changes, broker notes:
- revenue_impact: Cite current price vs new target. Do NOT claim the rating changes commodity prices.
- demand_impact: "Analyst rating does not affect iron ore demand fundamentals."
- sentiment_impact: Cite RSI/volume then note: "Analyst [upgrade/downgrade] may [increase/decrease] institutional flow."

### MACRO / FED / RBA EVENTS
For triggers about interest rate decisions, inflation data, central bank policy:
- cost_impact: "Higher rates increase BHP's financing costs — apply only if debt refinancing is imminent."
- revenue_impact: Cite iron ore and AUD/USD, noting rate impact on AUD (rate hike = AUD appreciation = revenue headwind).
- demand_impact: "Rate hikes slow construction activity — indirect bearish signal for steel/iron ore demand."

---

## STEP 1 — EVENT CLASSIFICATION

Classify news into ONE of:
1. **Direct Impact** — affects revenue, costs, regulation, or operations directly
2. **Indirect Impact** — macro, geopolitical, or supply chain effects
3. **Noise / Low Relevance** — no meaningful connection to the company

Assign **Impact Strength:** Low / Medium / High and **Affected Domains.**

---

## STEP 2 — CAUSAL CHAIN ANALYSIS

Build: **Event → Intermediate Effects → Company-Level Impact**

GEOGRAPHY RULES (non-negotiable):
* Australian iron ore ships via **Lombok/Makassar Strait** to China — NOT Malacca, NOT Suez, NOT Panama
* Malacca disruption = affects Middle East crude and Qatar LNG to Asia. Neutral for AU iron ore.
* Suez disruption = affects AU LNG to Europe (WDS/STO). Neutral for iron ore miners.

Separate into: cost_impact, revenue_impact, demand_impact, sentiment_impact
Each must follow the language rules above.

---

## STEP 3 — IMPACT TIMELINE

For EACH of [Immediate (0-7d), Short-term (1-4w), Medium-term (1-3m), Long-term (3m+)]:
* Direction: Bullish / Bearish / Neutral
* Confidence: Low / Medium / High
* Reasoning: one specific sentence with mechanism

---

## STEP 4 — MARKET CONTEXT

Combine news with provided signals:
* **Reinforces trend** — aligns with price momentum
* **Contradicts trend** — opposes current direction
* **No strong effect** — mixed/unclear signals

---

## STEP 5 — CONSENSUS WEIGHTING

Analyse agent vote distribution:
* >70% agreement → Stable, increase confidence
* <70% agreement → Fragile, reduce confidence

Output: strength_score (0–100), stability (Stable / Fragile)

---

## STEP 6 — FINAL DECISION

1. **Direction:** Bullish / Bearish / Neutral
2. **Recommendation:** BUY / SELL / HOLD / WAIT
3. **Confidence Score:** 0–100
   * 75–85: Direct commodity/earnings impact with strong consensus (hard cap: 85)
   * 55–74: Clear causal chain, 2+ confirming signals
   * 35–54: Plausible but mixed signals
   * 15–34: Speculative, limited data
   * 0–14: Noise / insufficient data
4. **Risk Level:** Low / Medium / High

---

## STEP 7 — RISK ANALYSIS

List 3–5 specific risks that could invalidate the prediction. Name exact thresholds.
Example: "Iron ore falls below $100/t (current $118) triggering margin squeeze"

---

## STEP 8 — CONTRARIAN INSIGHT

If the news may be overpriced by the market, describe the overreaction opportunity. Output null if none.

---

## OUTPUT — STRICT JSON ONLY

Output ONLY this JSON (no markdown, no text outside the braces):

{
  "stock_ticker": "BHP.AX",
  "event_classification": {
    "type": "Indirect Impact",
    "strength": "Medium",
    "domains": ["iron_ore", "china", "demand"]
  },
  "causal_chain": {
    "summary": "Specific: Event → mechanism → company impact",
    "cost_impact": "Named cost driver with quantification or NO DATA statement",
    "revenue_impact": "Named revenue driver with quantification or NO DATA statement",
    "demand_impact": "China/steel/construction signal with data or NO DATA statement",
    "sentiment_impact": "Technical level / positioning data or NO DATA statement"
  },
  "impact_timeline": [
    {"timeframe": "Immediate", "direction": "Neutral", "confidence": "Medium", "reason": "Specific mechanism sentence"},
    {"timeframe": "Short-term", "direction": "Neutral", "confidence": "Medium", "reason": "Specific mechanism sentence"},
    {"timeframe": "Medium-term", "direction": "Neutral", "confidence": "Low", "reason": "Specific mechanism sentence"},
    {"timeframe": "Long-term", "direction": "Neutral", "confidence": "Low", "reason": "Specific mechanism sentence"}
  ],
  "market_context": {
    "alignment": "No strong effect",
    "commodity_signals": {},
    "currency_signal": null,
    "technical_summary": null,
    "notes": "Specific observation"
  },
  "consensus_analysis": {
    "bullish": 0,
    "bearish": 0,
    "neutral": 0,
    "strength_score": 0,
    "stability": "Fragile"
  },
  "final_decision": {
    "direction": "Neutral",
    "recommendation": "WAIT",
    "confidence_score": 0,
    "risk_level": "Medium"
  },
  "risk_factors": ["Specific risk with threshold", "..."],
  "contrarian_view": null,
  "data_provenance": {}
}

---

## SELF-CHECK — RUN THIS BEFORE OUTPUTTING

Before writing your JSON, answer these 5 questions internally:

1. **Is the trigger a commentary/opinion/valuation article?**
   YES → confidence_score = 5, type = "Noise / Low Relevance", all impacts = "NO DATA: commentary"
   NO → continue

2. **Did I invent any geopolitical event, country conflict, or supply disruption NOT in the trigger headline?**
   YES → remove it from causal chain immediately
   NO → continue

3. **Did I assign a topic domain (e.g. "oil markets", "China tensions") based on inference rather than headline words?**
   YES → change type to "Noise / Low Relevance", remove invented domains
   NO → continue

4. **Does my sentiment_impact cite the exact RSI number provided in the input?**
   If RSI was provided in the input and I did NOT cite it → prepend "RSI at [value] ([label])." to sentiment_impact

5. **Did I write any BANNED phrase (e.g. "discusses X in the context of Y", "part of broader geopolitical event")?**
   YES → rewrite that sentence with a specific mechanism or "NO DATA" statement

Only output JSON after all 5 checks pass.

---

HARD RULES:
1. Never guess — base all reasoning on causal logic from provided data
2. Never hallucinate market data — use ONLY values provided in the input
3. Never use banned phrases — always state the specific mechanism or write NO DATA
4. Australian iron ore ships via Lombok/Makassar, NOT Malacca/Suez/Panama
5. Confidence hard cap: 85% maximum. Never output 100%.
6. Output ONLY valid JSON — no markdown, no text outside the JSON structure

---

## EXAMPLE: GOOD vs BAD REASONING

### GOOD cost_impact (specific mechanism, no weasel words):
"Diesel at $1.42/L (flat MoM). Capesize freight at $17,800/day (-5% MoM, below $20k/day breakeven freight rate). Pilbara haulage costs stable. NET: neutral cost environment — no new cost catalyst."

### BAD cost_impact (banned phrases, no mechanism):
"The geopolitical event may not directly impact BHP's costs at this time." ← BANNED

### GOOD revenue_impact (named price, volume, FX):
"Iron ore at $107.45/t (-2.5% from $110.20 last month). AUD/USD 0.691 vs budget 0.700 = 1.3% revenue tailwind. No volume guidance changes. NET: modest price headwind, FX partially offsets."

### BAD revenue_impact (vague, no data):
"The event may indirectly affect iron ore prices and therefore revenue." ← BANNED

### GOOD risk_factors (named thresholds):
["Iron ore falls below $100/t (current $107) triggering C1 cost squeeze for high-cost peers",
 "AUD/USD appreciation above 0.72 compresses USD-denominated revenue by ~4%",
 "China steel PMI below 48 for two consecutive months signalling structural demand retreat"]

### BAD risk_factors (hallucinated or vague):
["Ukraine-Syria cooperation may impact commodity prices",  ← HALLUCINATED
 "Global tensions create uncertainty"]  ← VAGUE, NO THRESHOLD
"""


def _fmt(v: Any, suffix: str = "", decimals: int = 2) -> str:
    """Format a numeric value for prompt display, returning 'N/A' if None."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _build_user_prompt(
    stock_ticker: str,
    news_headline: str,
    news_summary: str,
    market_signals: Dict[str, Any],
    agent_votes: Dict[str, int],
    data_provenance: Dict[str, Any],
) -> str:
    import json

    # ── Extract key data points for highlighted citation section ──────────────
    iron_ore = market_signals.get("iron_ore_62fe") or market_signals.get("iron_ore_price")
    iron_ore_chg = market_signals.get("iron_ore_change_pct", 0) or 0
    aud_usd = market_signals.get("aud_usd")
    aud_usd_chg = market_signals.get("aud_usd_change_pct", 0) or 0
    current_price = market_signals.get("current_price")
    rsi = market_signals.get("rsi_14")
    macd = market_signals.get("macd_signal", "N/A")
    volume_ratio = (
        market_signals.get("volume_ratio")
        or market_signals.get("volume_vs_avg")
        or market_signals.get("ticker_volume_vs_avg")
        or market_signals.get("vol_ratio")
        or market_signals.get("relative_volume")
    )
    brent = market_signals.get("brent_price")
    brent_chg = market_signals.get("brent_change_pct", 0) or 0

    # Trend
    d1 = market_signals.get("return_1d") or market_signals.get("day_1_change")
    d5 = market_signals.get("return_5d") or market_signals.get("day_5_change")
    d20 = market_signals.get("return_20d") or market_signals.get("day_20_change")
    dist_52w = market_signals.get("dist_from_52w_high_pct") or market_signals.get("distance_from_52w_high")
    consec_down = market_signals.get("consecutive_down_days", 0) or 0

    # ── Build market signals table (shown in full below the box) ────────────
    cite_rows = []
    if iron_ore:
        chg_str = f"{iron_ore_chg:+.2f}%" if iron_ore_chg else "chg N/A"
        cite_rows.append(f"  Iron Ore 62% Fe : ${_fmt(iron_ore)}/t ({chg_str})")
    if aud_usd:
        chg_str = f"{aud_usd_chg:+.3f}%" if aud_usd_chg else "chg N/A"
        cite_rows.append(f"  AUD/USD         : {_fmt(aud_usd, decimals=4)} ({chg_str})")
    if brent:
        cite_rows.append(f"  Brent Crude     : ${_fmt(brent)}/bbl ({brent_chg:+.2f}%)")
    if current_price:
        cite_rows.append(f"  Stock Price     : ${_fmt(current_price)}")
    if rsi is not None:
        cite_rows.append(f"  RSI(14)         : {_fmt(rsi)}")
    if macd and macd != "N/A":
        cite_rows.append(f"  MACD Signal     : {macd}")
    if volume_ratio:
        cite_rows.append(f"  Volume vs Avg   : {_fmt(volume_ratio)}x")
    if d1 is not None:
        cite_rows.append(f"  1-Day Return    : {_fmt(d1, suffix='%', decimals=2)}")
    if d5 is not None:
        cite_rows.append(f"  5-Day Return    : {_fmt(d5, suffix='%', decimals=2)}")
    if d20 is not None:
        cite_rows.append(f"  20-Day Return   : {_fmt(d20, suffix='%', decimals=2)}")
    if dist_52w is not None:
        cite_rows.append(f"  Dist 52W High   : {_fmt(dist_52w, suffix='%', decimals=1)}")
    if consec_down:
        cite_rows.append(f"  Consecutive Down Days: {consec_down}")

    signals_table = "\n".join(cite_rows) if cite_rows else "  (No key signals available)"

    # ── Compute RSI/volume labels ─────────────────────────────────────────────
    rsi_label = "neutral"
    if rsi is not None:
        rsi_f = float(rsi)
        if rsi_f > 70:
            rsi_label = "OVERBOUGHT — pullback risk elevated"
        elif rsi_f < 30:
            rsi_label = "OVERSOLD — reversal potential"

    vol_label = "normal"
    if volume_ratio is not None:
        vol_f = float(volume_ratio)
        if vol_f < 0.7:
            vol_label = "LIGHT — weak conviction"
        elif vol_f > 1.5:
            vol_label = "HIGH — strong conviction"

    # ── Build exact citation strings (Python-computed, LLM must copy verbatim) ─
    if rsi is not None and volume_ratio is not None:
        exact_sentiment = (
            f"RSI at {float(rsi):.1f} ({rsi_label}). "
            f"Volume at {float(volume_ratio):.2f}x avg ({vol_label})."
        )
    elif rsi is not None:
        exact_sentiment = f"RSI at {float(rsi):.1f} ({rsi_label})."
    else:
        exact_sentiment = "RSI data unavailable."

    if iron_ore and aud_usd:
        exact_revenue = (
            f"Iron ore at ${float(iron_ore):.2f}/t ({iron_ore_chg:+.2f}%). "
            f"AUD/USD at {float(aud_usd):.4f} ({aud_usd_chg:+.2f}%)."
        )
    elif iron_ore:
        exact_revenue = f"Iron ore at ${float(iron_ore):.2f}/t ({iron_ore_chg:+.2f}%)."
    else:
        exact_revenue = "Iron ore price unavailable."

    # ── Revenue / sentiment citation instructions ─────────────────────────────
    if iron_ore and aud_usd:
        rev_instruction = (
            f"revenue_impact MUST begin with: '{exact_revenue}' then add your analysis."
        )
    elif iron_ore:
        rev_instruction = f"revenue_impact MUST begin with: '{exact_revenue}' then add your analysis."
    else:
        rev_instruction = "revenue_impact: state 'Iron ore price unavailable.' then add analysis."

    if rsi is not None and volume_ratio is not None:
        sent_instruction = (
            f"sentiment_impact MUST begin with: '{exact_sentiment}' "
            f"Then add event sentiment OR 'No event-driven sentiment from trigger.' if commentary."
        )
    elif rsi is not None:
        sent_instruction = (
            f"sentiment_impact MUST begin with: '{exact_sentiment}' "
            f"Then add event sentiment OR 'No event-driven sentiment from trigger.' if commentary."
        )
    else:
        sent_instruction = "sentiment_impact: state 'RSI data unavailable.' then add event sentiment if any."

    # ── Unicode box with pre-computed mandatory strings ───────────────────────
    w = 70
    def _box_row(text: str) -> str:
        return f"\u2551  {text:<{w - 4}}\u2551"

    mandatory_box = "\n".join([
        "\u2554" + "\u2550" * (w - 2) + "\u2557",
        _box_row("MANDATORY: COPY THESE EXACT STRINGS INTO YOUR JSON OUTPUT"),
        "\u2560" + "\u2550" * (w - 2) + "\u2563",
        _box_row(""),
        _box_row("sentiment_impact MUST BEGIN WITH:"),
        _box_row(f'  "{exact_sentiment}"'),
        _box_row(""),
        _box_row("revenue_impact MUST BEGIN WITH:"),
        _box_row(f'  "{exact_revenue}"'),
        _box_row(""),
        _box_row("COPY THESE EXACTLY. Do not paraphrase. Do not omit."),
        _box_row('NEVER write "No data — assumed neutral" in any field.'),
        _box_row("For commentary triggers: append 'No event-driven [X] from trigger.'"),
        _box_row(""),
        "\u255a" + "\u2550" * (w - 2) + "\u255d",
    ])

    total = sum(agent_votes.values())
    return f"""## ANALYSIS REQUEST

**Target Stock:** {stock_ticker}

### NEWS EVENT
**Headline:** {news_headline}
**Summary:** {news_summary}

---

{mandatory_box}

## ALL MARKET SIGNALS

{signals_table}

### CITATION RULES
- {rev_instruction}
- {sent_instruction}
- cost_impact: name a real cost driver (diesel/freight/labour/energy) OR write: "No event-driven cost impact from trigger."
- demand_impact: cite China PMI / steel data if in signals, otherwise write: "No event-driven demand signal from trigger."

FORBIDDEN PHRASES: "price is stable", "demand is neutral", "unlikely to affect", "will not significantly impact", "no significant changes", "No data — assumed neutral", "assumed neutral impact"

---

### FULL MARKET SIGNALS JSON
```json
{json.dumps(market_signals, indent=2)}
```

**Data Sources:**
```json
{json.dumps(data_provenance, indent=2)}
```

### SPECIALIST AGENT CONSENSUS ({total} agents)
* Bullish: {agent_votes.get('bullish', 0)}
* Bearish: {agent_votes.get('bearish', 0)}
* Neutral: {agent_votes.get('neutral', 0)}

Execute the 8-step reasoning pipeline and output your analysis as valid JSON only."""


def _fallback_output(
    stock_ticker: str,
    agent_votes: Dict[str, int],
    error_message: str,
) -> ReasoningOutput:
    """Safe fallback when the LLM response cannot be parsed or validated."""
    return ReasoningOutput(
        stock_ticker=stock_ticker,
        event_classification={
            "type": ImpactType.NOISE,
            "strength": Strength.LOW,
            "domains": ["error_fallback"],
        },
        causal_chain={
            "summary": f"Reasoning pipeline error: {error_message}",
            "cost_impact": "Unable to assess",
            "revenue_impact": "Unable to assess",
            "demand_impact": "Unable to assess",
            "sentiment_impact": "Unable to assess",
        },
        impact_timeline=[
            {
                "timeframe": "Immediate",
                "direction": Direction.NEUTRAL,
                "confidence": Strength.LOW,
                "reason": "Reasoning error — defaulting to neutral",
            }
        ],
        market_context={
            "alignment": "No strong effect",
            "notes": f"Error in reasoning pipeline: {error_message}",
        },
        consensus_analysis={
            "bullish": agent_votes.get("bullish", 0),
            "bearish": agent_votes.get("bearish", 0),
            "neutral": agent_votes.get("neutral", 0),
            "strength_score": 0,
            "stability": Stability.FRAGILE,
        },
        final_decision={
            "direction": Direction.NEUTRAL,
            "recommendation": Recommendation.WAIT,
            "confidence_score": 0,
            "risk_level": Strength.HIGH,
        },
        risk_factors=[
            "Reasoning pipeline failed — do not trade on this signal",
            f"Error: {error_message}",
        ],
        contrarian_view=None,
        data_provenance={"error": error_message},
    )


class ReasoningSynthesizer:
    """
    Final-stage reasoning agent producing structured stock predictions.

    Aggregates specialist agent votes with news and market data via LLMRouter.
    Supports optional memory injection to improve predictions from history.
    """

    # Domain keywords for extracting event domains from news text
    _DOMAIN_KEYWORDS: Dict[str, List[str]] = {
        "iron_ore":   ["iron ore", "iron-ore", "steel", "bhp", "rio", "fortescue", "fmg"],
        "oil":        ["oil", "crude", "brent", "opec", "petroleum", "energy", "lng"],
        "gold":       ["gold", "precious metal", "bullion", "silver"],
        "currency":   ["aud", "usd", "dollar", "forex", "currency", "exchange rate"],
        "china":      ["china", "chinese", "beijing", "shanghai", "xi jinping", "prc"],
        "geopolitics":["war", "conflict", "sanctions", "military", "tension", "attack", "houthi"],
        "logistics":  ["shipping", "freight", "port", "supply chain", "logistics", "strait"],
        "regulation": ["regulation", "policy", "government", "legislation", "tax", "rba"],
        "earnings":   ["earnings", "profit", "revenue", "quarterly", "annual report", "dividend"],
        "demand":     ["demand", "consumption", "sales", "orders", "stimulus", "infrastructure"],
    }

    def __init__(self, llm_router: LLMRouter, prediction_memory=None) -> None:
        self._router = llm_router
        self._memory = prediction_memory  # Optional PredictionMemory instance

    async def synthesize(
        self,
        stock_ticker: str,
        news_headline: str,
        news_summary: str,
        market_signals: Dict[str, Any],
        agent_votes: Dict[str, int],
        data_provenance: Dict[str, Any],
        inject_memory: bool = True,
    ) -> ReasoningOutput:
        """
        Run the full 8-step reasoning pipeline and return a validated prediction.

        Args:
            stock_ticker: ASX ticker (e.g., "BHP.AX")
            news_headline: News event headline
            news_summary: News event description
            market_signals: Commodity prices, technicals, macro indicators
            agent_votes: {"bullish": n, "bearish": n, "neutral": n}
            data_provenance: Source + timestamp for each market data point
            inject_memory: Whether to prepend historical memory context to the prompt

        Returns:
            ReasoningOutput: Validated structured prediction (memory_context attached)
        """
        # ── Sector-aware signal filtering ──────────────────────────────────────
        relevant_signals = filter_signals_for_sector(stock_ticker, market_signals)
        if len(relevant_signals) < len(market_signals):
            dropped = len(market_signals) - len(relevant_signals)
            logger.debug("Filtered %d irrelevant signal(s) for %s", dropped, stock_ticker)

        # ── Trigger materiality classification (keyword-based, fast) ─────────────
        trigger_meta = TriggerClassifier.classify(news_headline, news_summary)
        logger.info(
            "Trigger materiality [%s]: %s (%s)",
            stock_ticker, trigger_meta["materiality"], trigger_meta["type"],
        )

        # ── LLM pre-flight classifier (Prompt 2) — cheap 8b call ──────────────
        # Only run when keyword classifier didn't already flag as LOW materiality.
        _llm_classify: Dict[str, Any] = {}
        if trigger_meta["materiality"] != "LOW":
            try:
                _llm_classify = await self._llm_classify_trigger(
                    news_headline, news_summary, stock_ticker
                )
                # If LLM says skip, override trigger_meta to LOW
                if _llm_classify.get("skip_simulation"):
                    trigger_meta = {
                        "materiality": "LOW",
                        "type": _llm_classify.get("classification", "commentary").lower(),
                        "preamble": (
                            f"NOTE: LLM classifier identified '{news_headline}' as "
                            f"{_llm_classify.get('classification', 'non-material')}: "
                            f"{_llm_classify.get('reason', '')}. "
                            "Classify as 'Noise / Low Relevance' with confidence_score = 5."
                        ),
                    }
                    logger.info(
                        "LLM pre-flight: skipping full synthesis for %s (%s)",
                        stock_ticker, _llm_classify.get("classification"),
                    )
            except Exception as _clf_err:
                logger.debug("LLM pre-flight classifier skipped: %s", _clf_err)

        # ── News category classification (13-class, fast keyword-based) ────────
        news_classification: Optional[Dict[str, Any]] = None
        try:
            from services.news_classifier import NewsClassifier
            _nc = NewsClassifier(llm_router=self._router)
            nc_result = await _nc.classify(news_headline, news_summary, use_llm=False)
            news_classification = nc_result.to_dict()
            logger.info(
                "News category [%s]: %s (%.0f%% confidence, materiality=%s)",
                stock_ticker,
                news_classification["category"],
                news_classification["confidence"] * 100,
                news_classification["materiality"],
            )
        except Exception as _nc_err:
            logger.warning("News classification failed: %s", _nc_err, exc_info=True)

        user_prompt = _build_user_prompt(
            stock_ticker=stock_ticker,
            news_headline=news_headline,
            news_summary=news_summary,
            market_signals=relevant_signals,
            agent_votes=agent_votes,
            data_provenance=data_provenance,
        )

        # Prepend trigger preamble when article is non-material commentary
        if trigger_meta.get("preamble"):
            user_prompt = trigger_meta["preamble"] + "\n\n" + user_prompt

        # Append news category context for the LLM
        if news_classification:
            category_note = (
                f"\n\n## NEWS CATEGORY CONTEXT\n"
                f"Category: {news_classification['category']} "
                f"(confidence {news_classification['confidence']:.0%})\n"
                f"Key focus: {news_classification['recommended_focus']}\n"
                f"Materiality: {news_classification['materiality']}"
            )
            user_prompt = user_prompt + category_note

        # ── Memory injection ───────────────────────────────────────────────────
        memory_context: Optional[Dict[str, Any]] = None
        if inject_memory and self._memory is not None:
            try:
                domains = self._extract_domains(news_headline, news_summary)
                initial_direction = self._estimate_direction(agent_votes)
                memory_context = await self._memory.get_memory_context(
                    stock_ticker=stock_ticker,
                    event_domains=domains,
                    direction=initial_direction,
                    stated_confidence=50,
                )
                if memory_context and memory_context.get("has_memory"):
                    memory_prompt = memory_context.get("memory_prompt", "")
                    if memory_prompt:
                        user_prompt = user_prompt + "\n\n" + memory_prompt
                        logger.info("Memory injected for %s", stock_ticker)
            except Exception as exc:
                logger.warning("Memory injection skipped (%s): %s", stock_ticker, exc)

        # ── Sector-aware system prompt ─────────────────────────────────────────
        system_prompt = get_sector_system_prompt(stock_ticker, default_prompt=_SYSTEM_PROMPT)

        # ── LLM call ──────────────────────────────────────────────────────────
        try:
            raw = await self._router.call_primary(
                system_message=system_prompt,
                user_prompt=user_prompt,
                session_id=f"reasoning:{stock_ticker}",
            )
            logger.info("Reasoning raw output for %s: %.300s…", stock_ticker, raw)

            parsed = parse_json_response(raw)

            # ── Risk factor post-processing: remove hallucinations ─────────
            raw_risks = parsed.get("risk_factors") or []
            cleaned_risks = reasoning_validator.validate_risk_factors(
                raw_risks, stock_ticker=stock_ticker
            )
            if len(cleaned_risks) < len(raw_risks):
                logger.info(
                    "Risk factors cleaned [%s]: %d → %d",
                    stock_ticker, len(raw_risks), len(cleaned_risks),
                )
            parsed["risk_factors"] = cleaned_risks

            # ── Post-process: inject missing market data into causal chain ──
            if "causal_chain" in parsed and isinstance(parsed["causal_chain"], dict):
                parsed["causal_chain"] = self._post_process_inject_data(
                    parsed["causal_chain"], relevant_signals
                )

            result = ReasoningOutput(**parsed)
            result.memory_context = memory_context

            # ── Attach news classification to data_provenance ──────────────
            if news_classification and isinstance(result.data_provenance, dict):
                result.data_provenance["news_classification"] = news_classification

            # ── Apply memory-based confidence calibration ──────────────────
            adjustments_applied: list = []
            if memory_context and memory_context.get("has_memory"):
                calibration = memory_context.get("confidence_calibration", {})
                adj = calibration.get("adjustment", 0)
                if adj != 0:
                    original = result.final_decision.confidence_score
                    adjusted = max(0, min(100, original + adj))
                    result.final_decision.confidence_score = adjusted
                    adjustments_applied.append({
                        "type": "confidence_calibration",
                        "original": original,
                        "adjusted": adjusted,
                        "reason": calibration.get("reason", "Historical calibration"),
                    })
                    logger.info(
                        "Confidence calibrated [%s]: %d → %d (%+d)",
                        stock_ticker, original, adjusted, adj,
                    )

                # Cap confidence when causal chain effectiveness is LOW
                causal = memory_context.get("causal_chain_effectiveness", {})
                if (
                    causal.get("effectiveness") == "LOW"
                    and causal.get("sample_size", 0) >= 5
                    and result.final_decision.confidence_score > 50
                ):
                    original = result.final_decision.confidence_score
                    capped = 50
                    result.final_decision.confidence_score = capped
                    adjustments_applied.append({
                        "type": "low_effectiveness_cap",
                        "original": original,
                        "adjusted": capped,
                        "reason": (
                            f"Similar causal chains have only "
                            f"{causal.get('accuracy_pct', 0):.0f}% historical accuracy"
                        ),
                    })

            # ── Validate causal chain logic ────────────────────────────────
            try:
                chain_dict = (
                    result.causal_chain.model_dump()
                    if hasattr(result.causal_chain, "model_dump")
                    else result.causal_chain.dict()
                )
                try:
                    fd_dict = result.final_decision.model_dump()
                except Exception:
                    fd_dict = None
                _, quality_issues = reasoning_validator.validate_causal_chain(
                    chain_dict,
                    stock_ticker=stock_ticker,
                    final_decision=fd_dict,
                    market_signals=relevant_signals,
                )
            except Exception as _val_exc:
                logger.debug("Validator skipped: %s", _val_exc)
                quality_issues = []

            if len(quality_issues) >= 2:
                original = result.final_decision.confidence_score
                capped = max(20, original - 15)
                if capped < original:
                    result.final_decision.confidence_score = capped
                    adjustments_applied.append({
                        "type": "quality_cap",
                        "original": original,
                        "adjusted": capped,
                        "reason": (
                            f"Weak causal reasoning detected "
                            f"({len(quality_issues)} logic issue(s))"
                        ),
                    })

            result.adjustments_applied = adjustments_applied
            result.reasoning_quality_issues = quality_issues

            # ── QA validation (Prompt 3) — post-synthesis confidence penalties ──
            try:
                await self._qa_validate(
                    result=result,
                    trigger_text=f"{news_headline}. {news_summary}",
                    target_ticker=stock_ticker,
                    market_signals=relevant_signals,
                )
            except Exception as _qa_err:
                logger.debug("QA validation skipped (non-fatal): %s", _qa_err)

            return result

        except ValidationError as exc:
            logger.error("Pydantic validation error in reasoning output: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

        except ValueError as exc:
            logger.error("JSON parse error in reasoning output: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

        except Exception as exc:
            logger.error("Reasoning synthesizer error: %s", exc, exc_info=True)
            return _fallback_output(stock_ticker, agent_votes, str(exc))

    # ── helpers ────────────────────────────────────────────────────────────────

    async def _llm_classify_trigger(
        self,
        headline: str,
        summary: str,
        target_ticker: str,
    ) -> Dict[str, Any]:
        """
        Prompt 2: Fast LLM pre-flight check before running the full synthesis.
        Uses call_fast (8b model) to classify trigger materiality.
        Returns a dict with skip_simulation flag and classification metadata.
        Falls back to {"skip_simulation": False} on any error.
        """
        _CLASSIFY_SYSTEM = (
            "You are a news trigger classifier for an ASX stock prediction system. "
            "Classify the headline as MATERIAL or non-material. Output ONLY valid JSON."
        )
        _CLASSIFY_USER = f"""Classify this news headline for ASX stock analysis.

Headline: {headline}
Summary: {summary[:300]}
Target Ticker: {target_ticker}

MATERIAL EVENTS (real catalyst): earnings, dividends, acquisitions, guidance, production updates,
price surges/plunges, regulatory changes, geopolitical events affecting supply chains,
analyst upgrades/downgrades.

NON-MATERIAL (skip analysis): stock commentary ("easy way to value", "stocks to watch",
"should you buy", "top picks"), opinion pieces, educational articles, listicles, comparisons.

Output ONLY this JSON:
{{"is_material": true, "classification": "MATERIAL_EVENT", "target_ticker_relevant": true, "skip_simulation": false, "confidence": 0.9, "reason": "Direct earnings announcement"}}

Valid classifications: MATERIAL_EVENT | COMMENTARY | LISTICLE | OPINION | EDUCATIONAL | IRRELEVANT_TICKER"""

        try:
            raw = await self._router.call_fast(
                system_message=_CLASSIFY_SYSTEM,
                user_prompt=_CLASSIFY_USER,
                session_id=f"classify:{target_ticker}",
            )
            result = parse_json_response(raw)
            logger.info(
                "LLM trigger classification [%s]: %s (skip=%s, conf=%.0f%%)",
                target_ticker,
                result.get("classification", "?"),
                result.get("skip_simulation", False),
                float(result.get("confidence", 0)) * 100,
            )
            return result
        except Exception as _e:
            logger.debug("LLM trigger classifier failed (non-fatal): %s", _e)
            return {"skip_simulation": False, "classification": "UNKNOWN", "is_material": True}

    async def _qa_validate(
        self,
        result: "ReasoningOutput",
        trigger_text: str,
        target_ticker: str,
        market_signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prompt 3: Post-synthesis QA validator.
        Checks for hallucinations, tautologies, missing citations, and geographic errors.
        Returns penalty dict; applies confidence adjustment directly to result.
        Falls back gracefully on any error.
        """
        _QA_SYSTEM = (
            "You are a QA validator for stock prediction reasoning. "
            "Find logical errors, hallucinations, and circular reasoning. Output ONLY valid JSON."
        )

        import json as _json
        try:
            chain = (
                result.causal_chain.model_dump()
                if hasattr(result.causal_chain, "model_dump")
                else {}
            )
            fd = (
                result.final_decision.model_dump()
                if hasattr(result.final_decision, "model_dump")
                else {}
            )
        except Exception:
            return {}

        _QA_USER = f"""Validate this stock prediction reasoning for errors.

Trigger: {trigger_text[:400]}
Target Ticker: {target_ticker}
Iron Ore Price: {market_signals.get('iron_ore_62fe') or market_signals.get('iron_ore_price', 'N/A')}
RSI: {market_signals.get('rsi_14', 'N/A')}
Volume Ratio: {market_signals.get('volume_ratio') or market_signals.get('volume_vs_avg', 'N/A')}

Causal Chain:
{_json.dumps(chain, indent=2)[:800]}

Final Decision: {_json.dumps(fd)}
Original Confidence: {fd.get('confidence_score', 0)}

CHECK FOR:
1. HALLUCINATION: Did the chain invent countries/events/facts not in the trigger? (-25% per instance)
2. TAUTOLOGY: Does "X leads to X" (stable prices → stable costs)? (-15% per instance)
3. MISSING_DATA: Does any impact field lack at least one number? (-10% per missing)
4. GEOGRAPHIC_ERROR: For BHP/RIO/FMG — does chain mention Malacca for iron ore? (-20%)
5. IRRELEVANT_TRIGGER: Is this a commentary/valuation article, not a real event? (cap at 5%)

Output ONLY this JSON:
{{"is_valid": true, "total_penalty_percent": 0, "issues": [], "adjusted_confidence": {fd.get('confidence_score', 0)}, "summary": "No issues found"}}"""

        try:
            raw = await self._router.call_fast(
                system_message=_QA_SYSTEM,
                user_prompt=_QA_USER,
                session_id=f"qa:{target_ticker}",
            )
            qa_result = parse_json_response(raw)

            penalty = int(qa_result.get("total_penalty_percent", 0))
            issues = qa_result.get("issues", [])

            if penalty > 0 and issues:
                original = result.final_decision.confidence_score
                adjusted = max(5, min(original, original - penalty))
                if adjusted < original:
                    result.final_decision.confidence_score = adjusted
                    if not hasattr(result, "adjustments_applied") or result.adjustments_applied is None:
                        result.adjustments_applied = []
                    result.adjustments_applied.append({
                        "type": "qa_validation_penalty",
                        "original": original,
                        "adjusted": adjusted,
                        "reason": f"QA validator: {len(issues)} issue(s) — {qa_result.get('summary', '')}",
                    })
                    logger.info(
                        "QA validation [%s]: confidence %d → %d (-%d%%, %d issue(s))",
                        target_ticker, original, adjusted, penalty, len(issues),
                    )

            return qa_result

        except Exception as _e:
            logger.debug("QA validator failed (non-fatal): %s", _e)
            return {}

    def _post_process_inject_data(
        self,
        causal_chain: Dict[str, Any],
        market_signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Inject actual market data into causal chain fields that the LLM omitted.

        Called after the LLM response is parsed. Only prepends data when the
        field doesn't already contain a dollar/price reference.
        """
        processed = causal_chain.copy()

        iron_ore = market_signals.get("iron_ore_62fe") or market_signals.get("iron_ore_price")
        iron_ore_chg = market_signals.get("iron_ore_change_pct") or 0
        aud_usd = market_signals.get("aud_usd")
        rsi = market_signals.get("rsi_14")
        volume_ratio = (
            market_signals.get("volume_ratio")
            or market_signals.get("volume_vs_avg")
            or market_signals.get("ticker_volume_vs_avg")
            or market_signals.get("vol_ratio")
            or market_signals.get("relative_volume")
        )

        # ── Revenue: prepend iron ore price if missing ────────────────────────
        rev = processed.get("revenue_impact") or processed.get("revenue_signal") or ""
        if iron_ore and not re.search(r"\$\d{2,3}[,.]?\d*/t", rev):
            chg_label = f"{iron_ore_chg:+.1f}%" if iron_ore_chg else "flat"
            prefix = f"Iron ore at ${iron_ore:.2f}/t ({chg_label})."
            if aud_usd:
                prefix += f" AUD/USD at {aud_usd:.4f}."
            prefix += " "
            field = "revenue_impact" if "revenue_impact" in processed else "revenue_signal"
            processed[field] = prefix + rev
            logger.info("Injected iron ore price into %s", field)

        # ── Sentiment: prepend RSI if missing ─────────────────────────────────
        sent = processed.get("sentiment_impact") or processed.get("sentiment_signal") or ""
        if rsi is not None and not re.search(r"rsi.{0,10}\d{2}", sent.lower()):
            rsi_f = float(rsi)
            rsi_label = "overbought" if rsi_f > 70 else "oversold" if rsi_f < 30 else "neutral"
            prefix = f"RSI at {rsi_f:.1f} ({rsi_label})."
            if volume_ratio is not None:
                vol_f = float(volume_ratio)
                vol_label = "elevated" if vol_f > 1.2 else "light" if vol_f < 0.8 else "normal"
                prefix += f" Volume at {vol_f:.1f}x avg ({vol_label})."
            prefix += " "
            field = "sentiment_impact" if "sentiment_impact" in processed else "sentiment_signal"
            processed[field] = prefix + sent
            logger.info("Injected RSI into %s", field)

        # ── Cost: replace vague cop-outs with a concrete default ──────────────
        cost = processed.get("cost_impact") or processed.get("cost_signal") or ""
        vague_cost_patterns = [
            "unlikely to affect", "will not significantly", "no significant",
            "is unlikely", "not expected to",
        ]
        if cost and any(p in cost.lower() for p in vague_cost_patterns):
            field = "cost_impact" if "cost_impact" in processed else "cost_signal"
            processed[field] = (
                "No material cost catalyst identified. "
                "Diesel, freight, and labour costs unchanged from prior period. NET: Neutral."
            )
            logger.info("Replaced vague cost_impact with concrete default")

        return processed

    def _extract_domains(self, headline: str, summary: str) -> List[str]:
        """Heuristically extract affected domains from news text."""
        text = f"{headline} {summary}".lower()
        return [
            domain
            for domain, keywords in self._DOMAIN_KEYWORDS.items()
            if any(kw in text for kw in keywords)
        ] or ["general"]

    def _estimate_direction(self, agent_votes: Dict[str, int]) -> str:
        """Estimate likely direction from the agent vote split."""
        bullish = agent_votes.get("bullish", 0)
        bearish = agent_votes.get("bearish", 0)
        if bullish > bearish * 1.5:
            return "Bullish"
        if bearish > bullish * 1.5:
            return "Bearish"
        return "Neutral"

    async def _get_market_context(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch broad market context including 20+ ASX news topics.

        Returns ticker-specific news plus top macro topics for LLM context.
        """
        try:
            from services.asx_news_aggregator import fetch_asx_news

            news_data = await fetch_asx_news(hours=24, min_items=20, max_items=30)

            ticker_news = [
                item for item in news_data["items"]
                if ticker in item.get("tickers", [])
            ]

            macro_categories = {"macro", "monetary", "commodity", "currency"}
            macro_news = [
                item for item in news_data["items"]
                if item["category"] in macro_categories
            ][:10]

            return {
                "ticker_specific_news": ticker_news[:5],
                "macro_context": macro_news,
                "total_topics": news_data["total_filtered"],
                "categories_covered": list(news_data["by_category"].keys()),
            }
        except Exception as exc:
            logger.warning("Market context fetch failed for %s: %s", ticker, exc)
            return {}

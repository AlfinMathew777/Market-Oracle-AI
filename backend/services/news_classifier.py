"""
Financial News Classifier
--------------------------
Classifies news headlines into 13 categories for better trigger analysis.
Adapted from NVIDIA AI Model Distillation concepts — CPU-only using existing LLM.
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class NewsCategory(str, Enum):
    """13 financial news categories based on NVIDIA's classification schema."""

    EARNINGS = "earnings"
    MERGER_ACQUISITION = "merger_acquisition"
    ANALYST_RATING = "analyst_rating"
    COMMODITY_PRICE = "commodity_price"
    REGULATORY = "regulatory"
    MANAGEMENT = "management"
    GUIDANCE = "guidance"
    DIVIDEND = "dividend"
    LEGAL = "legal"
    MACRO = "macro"
    GEOPOLITICAL = "geopolitical"
    OPERATIONAL = "operational"
    SENTIMENT = "sentiment"

    @classmethod
    def list_all(cls) -> List[str]:
        return [c.value for c in cls]


@dataclass
class ClassificationResult:
    """Result of news classification."""

    category: NewsCategory
    confidence: float
    reasoning: str
    materiality: str
    recommended_focus: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "confidence": round(self.confidence, 2),
            "reasoning": self.reasoning,
            "materiality": self.materiality,
            "recommended_focus": self.recommended_focus,
        }


# Category-specific analysis guidance
CATEGORY_FOCUS: Dict[NewsCategory, Dict[str, Any]] = {
    NewsCategory.EARNINGS: {
        "focus": "revenue, profit margins, EPS, guidance",
        "materiality": "HIGH",
        "causal_weight": {"revenue_impact": 1.5, "demand_signal": 0.8},
    },
    NewsCategory.MERGER_ACQUISITION: {
        "focus": "deal value, synergies, regulatory approval risk",
        "materiality": "HIGH",
        "causal_weight": {"revenue_impact": 1.3, "sentiment_impact": 1.2},
    },
    NewsCategory.ANALYST_RATING: {
        "focus": "price target change, rating direction, analyst credibility",
        "materiality": "MEDIUM",
        "causal_weight": {"sentiment_impact": 1.3},
        "note": "Often lagging indicator — analysts follow price action",
    },
    NewsCategory.COMMODITY_PRICE: {
        "focus": "price level, % change, supply/demand drivers",
        "materiality": "HIGH",
        "causal_weight": {"revenue_impact": 1.5, "cost_impact": 1.3},
    },
    NewsCategory.REGULATORY: {
        "focus": "policy change, compliance cost, timeline",
        "materiality": "HIGH",
        "causal_weight": {"cost_impact": 1.4, "sentiment_impact": 1.2},
    },
    NewsCategory.MANAGEMENT: {
        "focus": "who, role, market reaction precedent",
        "materiality": "MEDIUM",
        "causal_weight": {"sentiment_impact": 1.3},
    },
    NewsCategory.GUIDANCE: {
        "focus": "direction vs prior, magnitude, credibility",
        "materiality": "HIGH",
        "causal_weight": {"revenue_impact": 1.4, "demand_signal": 1.2},
    },
    NewsCategory.DIVIDEND: {
        "focus": "yield change, payout ratio, sustainability",
        "materiality": "MEDIUM",
        "causal_weight": {"sentiment_impact": 1.2},
    },
    NewsCategory.LEGAL: {
        "focus": "potential liability, timeline, precedent",
        "materiality": "MEDIUM",
        "causal_weight": {"cost_impact": 1.3, "sentiment_impact": 1.1},
    },
    NewsCategory.MACRO: {
        "focus": "economic indicator, trend direction, sector impact",
        "materiality": "MEDIUM",
        "causal_weight": {"demand_signal": 1.3},
    },
    NewsCategory.GEOPOLITICAL: {
        "focus": "trade impact, supply chain disruption, duration",
        "materiality": "HIGH",
        "causal_weight": {"cost_impact": 1.2, "demand_signal": 1.3, "revenue_impact": 1.2},
    },
    NewsCategory.OPERATIONAL: {
        "focus": "production volume, capacity utilization, efficiency",
        "materiality": "HIGH",
        "causal_weight": {"revenue_impact": 1.4, "cost_impact": 1.2},
    },
    NewsCategory.SENTIMENT: {
        "focus": "market mood, positioning, contrarian signals",
        "materiality": "LOW",
        "causal_weight": {"sentiment_impact": 1.1},
        "note": "Often noise — lower weight in analysis",
    },
}

# Keywords for fast keyword-based classification (before LLM call)
CATEGORY_KEYWORDS: Dict[NewsCategory, List[str]] = {
    NewsCategory.EARNINGS: [
        "earnings", "quarterly results", "annual results", "profit", "revenue",
        "eps", "beat estimates", "missed estimates", "reported", "fiscal",
    ],
    NewsCategory.MERGER_ACQUISITION: [
        "merger", "acquisition", "acquire", "takeover", "bid", "deal",
        "buyout", "combine", "purchase", "m&a",
    ],
    NewsCategory.ANALYST_RATING: [
        "upgrade", "downgrade", "price target", "rating", "buy rating",
        "sell rating", "hold rating", "analyst", "outperform", "underperform",
    ],
    NewsCategory.COMMODITY_PRICE: [
        "iron ore", "oil price", "gold price", "copper", "commodity",
        "spot price", "futures", "$/t", "$/barrel", "lithium price",
    ],
    NewsCategory.REGULATORY: [
        "regulation", "government", "policy", "legislation", "approval",
        "ban", "tariff", "sanction", "compliance", "epa", "asic", "rba",
    ],
    NewsCategory.MANAGEMENT: [
        "ceo", "cfo", "appoint", "resign", "retire", "executive",
        "board", "director", "leadership", "management change",
    ],
    NewsCategory.GUIDANCE: [
        "guidance", "outlook", "forecast", "expects", "projects",
        "raises guidance", "lowers guidance", "fy25", "fy26",
    ],
    NewsCategory.DIVIDEND: [
        "dividend", "payout", "yield", "distribution", "special dividend",
        "interim dividend", "final dividend", "dps",
    ],
    NewsCategory.LEGAL: [
        "lawsuit", "legal", "court", "settlement", "investigation",
        "class action", "litigation", "fine", "penalty", "sued",
    ],
    NewsCategory.MACRO: [
        "gdp", "inflation", "interest rate", "unemployment", "rba",
        "fed", "economic", "pmi", "cpi", "central bank",
    ],
    NewsCategory.GEOPOLITICAL: [
        "china", "us-china", "trade war", "sanctions", "geopolitical",
        "ukraine", "middle east", "tariff", "export ban", "tensions",
    ],
    NewsCategory.OPERATIONAL: [
        "production", "output", "shipment", "capacity", "expansion",
        "plant", "facility", "operations", "volume", "tonnes",
    ],
    NewsCategory.SENTIMENT: [
        "stocks to watch", "market sentiment", "investor sentiment",
        "bullish", "bearish", "rally", "selloff", "momentum",
    ],
}


class NewsClassifier:
    """
    Classifies financial news into 13 categories for enhanced trigger analysis.

    Uses fast keyword matching first, falls back to LLM for ambiguous cases.
    """

    def __init__(self, llm_router=None) -> None:
        self.llm_router = llm_router

    def _keyword_classify(
        self,
        headline: str,
        summary: str,
    ) -> Optional[Tuple[NewsCategory, float]]:
        """
        Fast keyword-based classification.

        Returns (category, confidence) or None if ambiguous.
        """
        text = f"{headline} {summary}".lower()

        scores: Dict[NewsCategory, int] = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text)
            if matches > 0:
                scores[category] = matches

        if not scores:
            return None

        top_category = max(scores, key=lambda k: scores[k])
        top_score = scores[top_category]
        sorted_scores = sorted(scores.values(), reverse=True)

        if len(sorted_scores) == 1 or (sorted_scores[0] - sorted_scores[1] >= 2):
            # Clear winner — high confidence
            confidence = min(0.9, 0.5 + (top_score * 0.1))
        else:
            # Ambiguous tie — return best guess at reduced confidence so LLM
            # is tried if available, but we never fall back to SENTIMENT
            confidence = min(0.65, 0.4 + (top_score * 0.05))

        return (top_category, confidence)

    async def classify(
        self,
        headline: str,
        summary: str = "",
        use_llm: bool = True,
    ) -> ClassificationResult:
        """
        Classify a news headline into one of 13 categories.

        Args:
            headline: News headline
            summary: Optional news summary
            use_llm: Whether to use LLM for ambiguous cases

        Returns:
            ClassificationResult with category and metadata
        """
        keyword_result = self._keyword_classify(headline, summary)

        if keyword_result and keyword_result[1] >= 0.7:
            category, confidence = keyword_result
            focus_info = CATEGORY_FOCUS[category]
            return ClassificationResult(
                category=category,
                confidence=confidence,
                reasoning=f"Keyword match: {category.value}",
                materiality=focus_info["materiality"],
                recommended_focus=focus_info["focus"],
            )

        if use_llm and self.llm_router:
            return await self._llm_classify(headline, summary)

        # Fallback to best keyword result or SENTIMENT
        if keyword_result:
            category, confidence = keyword_result
        else:
            category = NewsCategory.SENTIMENT
            confidence = 0.3

        focus_info = CATEGORY_FOCUS[category]
        return ClassificationResult(
            category=category,
            confidence=confidence,
            reasoning="Low confidence keyword classification",
            materiality=focus_info["materiality"],
            recommended_focus=focus_info["focus"],
        )

    async def _llm_classify(self, headline: str, summary: str) -> ClassificationResult:
        """Use LLM for classification when keywords are ambiguous."""
        categories_list = "\n".join(
            f"- {cat.value}: {CATEGORY_FOCUS[cat]['focus']}" for cat in NewsCategory
        )
        system_prompt = (
            f"You are a financial news classifier. Classify the given news into exactly ONE category.\n\n"
            f"CATEGORIES:\n{categories_list}\n\n"
            "Respond in JSON format:\n"
            '{"category": "category_name", "confidence": 0.0-1.0, "reasoning": "brief explanation"}'
        )
        user_prompt = (
            f"Classify this financial news:\n\n"
            f"HEADLINE: {headline}\n"
            f"SUMMARY: {summary if summary else 'N/A'}\n\n"
            "Return JSON only, no other text."
        )

        try:
            response = await self.llm_router.call_primary(
                system_message=system_prompt,
                user_prompt=user_prompt,
                session_id="news_classifier",
            )
            response_text = response if isinstance(response, str) else str(response)

            json_match = re.search(r"\{[^}]+\}", response_text)
            if json_match:
                parsed = json.loads(json_match.group())
                category_str = parsed.get("category", "sentiment").lower()
                try:
                    category = NewsCategory(category_str)
                except ValueError:
                    category = NewsCategory.SENTIMENT

                confidence = float(parsed.get("confidence", 0.7))
                reasoning = parsed.get("reasoning", "LLM classification")
                focus_info = CATEGORY_FOCUS[category]

                return ClassificationResult(
                    category=category,
                    confidence=confidence,
                    reasoning=reasoning,
                    materiality=focus_info["materiality"],
                    recommended_focus=focus_info["focus"],
                )

        except Exception as e:
            logger.warning("LLM classification failed: %s", e)

        return ClassificationResult(
            category=NewsCategory.SENTIMENT,
            confidence=0.3,
            reasoning="Classification fallback",
            materiality="LOW",
            recommended_focus="general market sentiment",
        )

    def get_analysis_guidance(self, category: NewsCategory) -> Dict[str, Any]:
        """Get analysis guidance for a category."""
        return CATEGORY_FOCUS.get(category, CATEGORY_FOCUS[NewsCategory.SENTIMENT])


async def classify_news(
    headline: str,
    summary: str = "",
    llm_router=None,
) -> Dict[str, Any]:
    """
    Classify a financial news headline.

    Args:
        headline: News headline
        summary: Optional summary
        llm_router: LLM router for complex cases

    Returns:
        Classification result as dict
    """
    classifier = NewsClassifier(llm_router=llm_router)
    result = await classifier.classify(headline, summary)
    return result.to_dict()

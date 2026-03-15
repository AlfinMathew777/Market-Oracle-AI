"""GDELT Project API integration for real-time global news sentiment analysis.

GDELT (Global Database of Events, Language and Tone) monitors worldwide news media
and provides tone/sentiment scoring. This service queries the GDELT DOC 2.0 API
to get sentiment bias for event topics in the last 24 hours.

No API key required - GDELT is fully open access.

Note: GDELT has rate limits. Service includes mock fallback for development.
"""

import requests
import logging
import os
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# GDELT DOC 2.0 API base URL
GDELT_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# Use mock data if rate limited or for development
USE_MOCK_GDELT = os.getenv("USE_MOCK_GDELT", "True").lower() == "true"

# Tone score interpretation (GDELT scale: -10 to +10)
# Most news clusters around -2 to +2; scores beyond ±5 are significant
TONE_THRESHOLDS = {
    "strongly_positive": 5.0,
    "positive": 2.0,
    "neutral_high": 0.5,
    "neutral_low": -0.5,
    "negative": -2.0,
    "strongly_negative": -5.0
}


def get_gdelt_sentiment_score(topic: str, timespan: str = "1day", max_records: int = 250) -> Dict:
    """
    Query GDELT for news sentiment on a topic in the last 24 hours.
    
    Args:
        topic: Search keywords (e.g., "China Australia iron ore", "RBA interest rate")
        timespan: Time window (default "1day" for last 24 hours)
        max_records: Maximum articles to analyze (default 250)
    
    Returns:
        Dict with:
        - avgtone: Average tone score (-10 to +10; negative=bearish, positive=bullish)
        - article_count: Number of articles analyzed
        - sentiment: "bullish" | "bearish" | "neutral"
        - signal_strength: "strong" | "moderate" | "weak"
        - tone_category: Human-readable interpretation
        - sample_articles: List of up to 3 article titles
    """
    # Use mock data if enabled (for rate limit resilience)
    if USE_MOCK_GDELT:
        return _get_mock_sentiment(topic)
    
    try:
        # Build GDELT query URL
        query_params = {
            "query": topic,
            "format": "json",
            "mode": "ArticlesLatest",
            "timespan": timespan,
            "maxrecords": max_records
        }
        
        logger.info(f"Querying GDELT for topic: '{topic}'")
        
        response = requests.get(GDELT_API_BASE, params=query_params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract articles
        articles = data.get("articles", [])
        article_count = len(articles)
        
        if article_count == 0:
            logger.warning(f"No GDELT articles found for topic: {topic}")
            return {
                "avgtone": 0.0,
                "article_count": 0,
                "sentiment": "neutral",
                "signal_strength": "none",
                "tone_category": "No data",
                "sample_articles": [],
                "source": "GDELT DOC 2.0 API (Live)"
            }
        
        # Calculate average tone across all articles
        total_tone = 0.0
        valid_tone_count = 0
        sample_articles = []
        
        for article in articles[:max_records]:
            tone = article.get("tone")
            if tone is not None:
                total_tone += float(tone)
                valid_tone_count += 1
            
            # Collect sample article titles (up to 3)
            if len(sample_articles) < 3:
                sample_articles.append({
                    "title": article.get("title", "Untitled"),
                    "url": article.get("url", ""),
                    "tone": article.get("tone", 0.0),
                    "seendate": article.get("seendate", "")
                })
        
        # Compute average tone
        avgtone = total_tone / max(valid_tone_count, 1)
        
        # Interpret tone
        sentiment = _interpret_sentiment(avgtone)
        signal_strength = _assess_signal_strength(avgtone, article_count)
        tone_category = _categorize_tone(avgtone)
        
        logger.info(f"GDELT result: {article_count} articles, avg tone: {avgtone:.2f}, sentiment: {sentiment}")
        
        return {
            "avgtone": round(avgtone, 2),
            "article_count": article_count,
            "sentiment": sentiment,
            "signal_strength": signal_strength,
            "tone_category": tone_category,
            "sample_articles": sample_articles,
            "source": "GDELT DOC 2.0 API (Live)",
            "queried_at": datetime.utcnow().isoformat()
        }
        
    except requests.Timeout:
        logger.error("GDELT API timeout - falling back to mock")
        return _get_mock_sentiment(topic)
    except requests.RequestException as e:
        logger.error(f"GDELT API error: {str(e)} - falling back to mock")
        return _get_mock_sentiment(topic)
    except Exception as e:
        logger.error(f"Unexpected error in GDELT service: {str(e)}")
        return _get_mock_sentiment(topic)


def _get_mock_sentiment(topic: str) -> Dict:
    """Return mock GDELT sentiment based on topic keywords.
    
    Used when USE_MOCK_GDELT=True or when live API is rate-limited.
    """
    topic_lower = topic.lower()
    
    # Mock sentiment logic based on known geopolitical patterns
    mock_sentiments = {
        "china australia iron ore": {
            "avgtone": -3.2,
            "article_count": 47,
            "sentiment": "bearish",
            "signal_strength": "moderate",
            "tone_category": "Negative",
            "sample_articles": [
                {"title": "China signals further restrictions on Australian iron ore imports", "tone": -4.1},
                {"title": "Beijing-Canberra trade tensions escalate over commodity dependencies", "tone": -3.8},
                {"title": "Iron ore futures slide on China demand concerns", "tone": -1.7}
            ]
        },
        "rba interest rate": {
            "avgtone": 1.8,
            "article_count": 32,
            "sentiment": "bullish",
            "signal_strength": "moderate",
            "tone_category": "Positive",
            "sample_articles": [
                {"title": "RBA rate hike strengthens bank profit outlook", "tone": 2.4},
                {"title": "Australian banks see NIM expansion from higher rates", "tone": 2.1},
                {"title": "Rate increase pressures property sector", "tone": 0.9}
            ]
        },
        "taiwan semiconductor": {
            "avgtone": -2.8,
            "article_count": 89,
            "sentiment": "bearish",
            "signal_strength": "strong",
            "tone_category": "Negative",
            "sample_articles": [
                {"title": "Taiwan Strait tensions disrupt chip supply chains", "tone": -3.5},
                {"title": "Semiconductor export controls trigger rare earth scramble", "tone": -2.9},
                {"title": "Australian rare earth miners benefit from supply crisis", "tone": -2.0}
            ]
        },
        "us tariffs": {
            "avgtone": -2.5,
            "article_count": 156,
            "sentiment": "bearish",
            "signal_strength": "strong",
            "tone_category": "Negative",
            "sample_articles": [
                {"title": "US Liberation Day tariffs hit Australian steel exports", "tone": -3.1},
                {"title": "Trade war escalation threatens commodity exporters", "tone": -2.8},
                {"title": "Australia seeks tariff exemptions amid rising protectionism", "tone": -1.6}
            ]
        }
    }
    
    # Try to match topic to mock data
    for key, mock_data in mock_sentiments.items():
        if all(word in topic_lower for word in key.split()):
            logger.info(f"GDELT MOCK: Returning mock sentiment for '{topic}'")
            return {
                **mock_data,
                "source": "GDELT Mock Data (Rate Limited)",
                "queried_at": datetime.utcnow().isoformat()
            }
    
    # Default neutral mock
    logger.info(f"GDELT MOCK: No specific mock for '{topic}', returning neutral")
    return {
        "avgtone": 0.0,
        "article_count": 15,
        "sentiment": "neutral",
        "signal_strength": "weak",
        "tone_category": "Neutral",
        "sample_articles": [
            {"title": f"Global news coverage of {topic}", "tone": 0.2},
            {"title": f"Market analysis: {topic}", "tone": -0.1},
            {"title": f"Regional developments in {topic}", "tone": 0.0}
        ],
        "source": "GDELT Mock Data (Rate Limited)",
        "queried_at": datetime.utcnow().isoformat()
    }


def _interpret_sentiment(avgtone: float) -> str:
    """Convert GDELT tone to trading sentiment."""
    if avgtone >= TONE_THRESHOLDS["positive"]:
        return "bullish"
    elif avgtone <= TONE_THRESHOLDS["negative"]:
        return "bearish"
    else:
        return "neutral"


def _assess_signal_strength(avgtone: float, article_count: int) -> str:
    """Assess signal strength based on tone magnitude and article volume."""
    tone_magnitude = abs(avgtone)
    
    # Strong signal requires both high tone magnitude and sufficient article volume
    if tone_magnitude >= 5.0 and article_count >= 50:
        return "strong"
    elif tone_magnitude >= 2.0 and article_count >= 20:
        return "moderate"
    elif article_count >= 5:
        return "weak"
    else:
        return "insufficient"


def _categorize_tone(avgtone: float) -> str:
    """Human-readable tone category."""
    if avgtone >= TONE_THRESHOLDS["strongly_positive"]:
        return "Strongly Positive"
    elif avgtone >= TONE_THRESHOLDS["positive"]:
        return "Positive"
    elif avgtone >= TONE_THRESHOLDS["neutral_high"]:
        return "Slightly Positive"
    elif avgtone >= TONE_THRESHOLDS["neutral_low"]:
        return "Neutral"
    elif avgtone >= TONE_THRESHOLDS["negative"]:
        return "Slightly Negative"
    elif avgtone >= TONE_THRESHOLDS["strongly_negative"]:
        return "Negative"
    else:
        return "Strongly Negative"


def build_gdelt_topic_from_event(event_data: dict) -> str:
    """Build a GDELT search topic from ACLED event data.
    
    Extracts key terms from event to form an effective GDELT query.
    """
    country = event_data.get('country', '')
    event_type = event_data.get('event_type', '')
    notes = event_data.get('notes', '')
    
    # Extract key phrases
    topic_parts = []
    
    # Add country (if not generic)
    if country and country.lower() not in ['unknown', 'various']:
        topic_parts.append(country)
    
    # Add Australia if relevant
    if 'australia' in notes.lower() or 'australian' in notes.lower():
        topic_parts.append('Australia')
    
    # Extract commodity/sector keywords from notes
    commodity_keywords = ['iron ore', 'lithium', 'rare earth', 'lng', 'coal', 'gold', 
                         'copper', 'nickel', 'oil', 'gas']
    policy_keywords = ['tariff', 'trade', 'rate', 'monetary policy', 'rba', 'federal reserve']
    
    notes_lower = notes.lower()
    for keyword in commodity_keywords + policy_keywords:
        if keyword in notes_lower:
            topic_parts.append(keyword)
            break  # Only add first match to keep query focused
    
    # Fallback: use event type if no specific topic extracted
    if len(topic_parts) == 0:
        topic_parts.append(event_type)
    
    # Build final query (max 3-4 terms for best results)
    query = ' '.join(topic_parts[:4])
    logger.info(f"Built GDELT topic query: '{query}'")
    
    return query


if __name__ == "__main__":
    # Test GDELT service
    test_topics = [
        "China Australia iron ore",
        "RBA interest rate",
        "Taiwan semiconductor",
        "US tariffs Australia"
    ]
    
    print("GDELT Sentiment Service Test")
    print("=" * 60)
    
    for topic in test_topics:
        print(f"\nTopic: {topic}")
        result = get_gdelt_sentiment_score(topic)
        print(f"  Articles: {result['article_count']}")
        print(f"  Avg Tone: {result['avgtone']}")
        print(f"  Sentiment: {result['sentiment']} ({result['signal_strength']})")
        print(f"  Category: {result['tone_category']}")

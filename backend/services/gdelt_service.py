"""GDELT Project API integration for real-time global news sentiment analysis.

GDELT (Global Database of Events, Language and Tone) monitors worldwide news media
and provides tone/sentiment scoring. This service queries the GDELT DOC 2.0 API
to get sentiment bias for event topics in the last 24 hours.

No API key required - GDELT is fully open access (with rate limits).
"""

import requests
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

logger = logging.getLogger(__name__)

# GDELT DOC 2.0 API base URL
GDELT_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# REAL DATA - attempt live API with graceful degradation
USE_MOCK_GDELT = False

# In-memory cache with 1-hour TTL to prevent rate limiting
_gdelt_cache = {}
CACHE_TTL_SECONDS = 3600  # 1 hour

# Tone score interpretation (GDELT scale: -10 to +10)
# Most news clusters around -2 to +2; scores beyond ?5 are significant
TONE_THRESHOLDS = {
    "strongly_positive": 5.0,
    "positive": 2.0,
    "neutral_high": 0.5,
    "neutral_low": -0.5,
    "negative": -2.0,
    "strongly_negative": -5.0
}


def get_gdelt_sentiment_score(topic: str, timespan: str = "24h", max_records: int = 75) -> Dict:
    """
    Query GDELT for news sentiment on a topic in the last 24 hours.
    
    Args:
        topic: Search keywords (e.g., "China Australia iron ore", "RBA interest rate")
        timespan: Time window (default "24h" for last 24 hours)
        max_records: Maximum articles to analyze (default 75, reduced for rate limits)
    
    Returns:
        Dict with:
        - avgtone: Average tone score (-10 to +10; negative=bearish, positive=bullish)
        - article_count: Number of articles analyzed
        - sentiment: "bullish" | "bearish" | "neutral"
        - signal_strength: "strong" | "moderate" | "weak"
        - tone_category: Human-readable interpretation
        - sample_articles: List of up to 3 article titles
        - from_cache: Boolean indicating if result came from cache
    """
    # Check cache first (1-hour TTL to prevent rate limiting)
    cache_key = f"{topic}:{timespan}:{max_records}"
    if cache_key in _gdelt_cache:
        cached_entry = _gdelt_cache[cache_key]
        cached_at = cached_entry['cached_at']
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        
        if age_seconds < CACHE_TTL_SECONDS:
            logger.info(f"GDELT cache HIT for '{topic}' (age: {age_seconds:.0f}s)")
            result = cached_entry['data'].copy()
            result['from_cache'] = True
            result['cache_age_seconds'] = int(age_seconds)
            return result
        else:
            # Cache expired, remove it
            logger.info(f"GDELT cache EXPIRED for '{topic}' (age: {age_seconds:.0f}s)")
            del _gdelt_cache[cache_key]
    
    try:
        # Build GDELT query URL - use ArtList mode for better tone data
        query_params = {
            "query": topic,
            "format": "json",
            "mode": "ArtList",
            "timespan": timespan,
            "maxrecords": max_records
        }
        
        logger.info(f"Querying GDELT API for topic: '{topic}'")
        
        response = requests.get(GDELT_API_BASE, params=query_params, timeout=12)
        
        # Handle rate limits gracefully
        if response.status_code == 429:
            logger.warning("GDELT rate limit hit - checking for stale cache")
            # If we have ANY cached version (even if expired), use it rather than failing
            if cache_key in _gdelt_cache:
                stale_data = _gdelt_cache[cache_key]['data'].copy()
                stale_data['from_cache'] = True
                stale_data['cache_status'] = 'stale_due_to_rate_limit'
                logger.info("Returning stale cache due to rate limit")
                return stale_data
            
            # No cache available - return rate limited status and cache it
            rate_limited_response = {
                "avgtone": 0.0,
                "article_count": 0,
                "sentiment": "neutral",
                "signal_strength": "unavailable",
                "tone_category": "Rate limited",
                "sample_articles": [],
                "source": "GDELT (Rate Limited)",
                "status": "rate_limited",
                "message": "GDELT API rate limit - data cached for 1 hour to prevent this",
                "from_cache": False
            }
            
            # Cache the rate-limited response to prevent hammering
            _gdelt_cache[cache_key] = {
                'data': rate_limited_response.copy(),
                'cached_at': datetime.now(timezone.utc)
            }
            logger.info(f"Cached rate-limited response for '{topic}'")
            
            return rate_limited_response
        
        response.raise_for_status()
        
        data = response.json()
        
        # Extract articles
        articles = data.get("articles", [])
        article_count = len(articles)
        
        if article_count == 0:
            logger.warning(f"No GDELT articles found for topic: {topic}")
            result = {
                "avgtone": 0.0,
                "article_count": 0,
                "sentiment": "neutral",
                "signal_strength": "none",
                "tone_category": "No data",
                "sample_articles": [],
                "source": "GDELT DOC 2.0 API (Live)",
                "status": "no_data",
                "from_cache": False
            }
            # Cache even empty results to prevent hammering API
            _gdelt_cache[cache_key] = {
                'data': result.copy(),
                'cached_at': datetime.now(timezone.utc)
            }
            return result
        
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
        avgtone = total_tone / max(valid_tone_count, 1) if valid_tone_count > 0 else 0.0
        
        # Interpret tone
        sentiment = _interpret_sentiment(avgtone)
        signal_strength = _assess_signal_strength(avgtone, article_count)
        tone_category = _categorize_tone(avgtone)
        
        logger.info(f"GDELT result: {article_count} articles, avg tone: {avgtone:.2f}, sentiment: {sentiment}")
        
        result = {
            "avgtone": round(avgtone, 2),
            "article_count": article_count,
            "sentiment": sentiment,
            "signal_strength": signal_strength,
            "tone_category": tone_category,
            "sample_articles": sample_articles,
            "source": "GDELT DOC 2.0 API (Live)",
            "status": "success",
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "from_cache": False
        }
        
        # Cache the successful result
        _gdelt_cache[cache_key] = {
            'data': result.copy(),
            'cached_at': datetime.now(timezone.utc)
        }
        logger.info(f"GDELT result cached for '{topic}' (TTL: {CACHE_TTL_SECONDS}s)")
        
        return result
        
    except requests.Timeout:
        logger.error("GDELT API timeout")
        return _error_response("API timeout after 12s")
    except requests.RequestException as e:
        logger.error(f"GDELT API error: {str(e)}")
        return _error_response(f"API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in GDELT service: {str(e)}")
        return _error_response(f"Unexpected error: {str(e)}")


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


def _error_response(error_msg: str) -> Dict:
    """Return error response in expected format."""
    return {
        "avgtone": 0.0,
        "article_count": 0,
        "sentiment": "neutral",
        "signal_strength": "error",
        "tone_category": f"Error: {error_msg}",
        "sample_articles": [],
        "source": "GDELT DOC 2.0 API",
        "status": "error",
        "error": error_msg
    }


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

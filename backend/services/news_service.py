"""MarketAux News API integration for ASX ticker-specific news sentiment.

Provides real-time news sentiment analysis for specific ASX tickers from MarketAux.
This is the highest-value API for simulation pre-bias - ticker-specific sentiment
from financial news sources.

API key required: Free account at marketaux.com (2 minute signup, instant key)
"""

import requests
import logging
import os
from typing import List, Dict
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

MARKETAUX_BASE = "https://api.marketaux.com/v1/news/all"


def get_asx_news_sentiment(symbols: List[str], hours: int = 24) -> Dict:
    """
    Get real news sentiment for specific ASX tickers from MarketAux.

    Args:
        symbols: List of ticker symbols (e.g., ["BHP.AX", "RIO.AX"])
        hours: Lookback period in hours (default 24)

    Returns:
        Dict with combined sentiment bias and article details
    """
    api_key = os.getenv("MARKETAUX_API_KEY")
    if not api_key:
        logger.error("MarketAux API key not configured")
        return {
            **_error_response("MarketAux API key not configured. Get free key at marketaux.com (2 minutes)"),
            'status': 'pending_api_key',
        }

    try:
        # Convert ASX tickers to format MarketAux expects (remove .AX suffix)
        cleaned_symbols = [s.replace('.AX', '') for s in symbols]

        # Calculate published_after as ISO date string
        published_after_date = datetime.now(timezone.utc) - timedelta(hours=hours)
        published_after_str = published_after_date.strftime('%Y-%m-%dT%H:%M:%S')

        params = {
            "api_token": api_key,
            "symbols": ",".join(cleaned_symbols),
            "filter_entities": "true",
            "published_after": published_after_str,
            "limit": 20,
            "language": "en"
        }
        
        logger.info(f"Fetching MarketAux sentiment for {len(symbols)} tickers...")
        
        response = requests.get(MARKETAUX_BASE, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        articles = data.get("data", [])
        
        if not articles:
            logger.warning(f"No MarketAux articles found for {symbols}")
            return {
                'status': 'success',
                'bias': 0.0,
                'signal': 'NEUTRAL',
                'signal_strength': 'NONE',
                'articles': 0,
                'headlines': [],
                'source': 'MarketAux API (Live)'
            }
        
        # Extract sentiment scores from article entities
        scores = []
        headlines = []

        for article in articles:
            headlines.append({
                "title": article.get("title", "Untitled"),
                "url": article.get("url", ""),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", "")
            })

            # Extract sentiment from entities matching our tickers
            for entity in article.get("entities", []):
                if entity.get("sentiment_score") is not None:
                    scores.append(float(entity["sentiment_score"]))

        headlines = headlines[:3]
        
        # Calculate average sentiment
        if scores:
            avg_sentiment = sum(scores) / len(scores)
        else:
            avg_sentiment = 0.0
        
        # Classify signal
        if avg_sentiment < -0.2:
            signal = "BEARISH"
        elif avg_sentiment > 0.2:
            signal = "BULLISH"
        else:
            signal = "NEUTRAL"
        
        # Assess strength
        if abs(avg_sentiment) > 0.4:
            strength = "STRONG"
        elif abs(avg_sentiment) > 0.2:
            strength = "MODERATE"
        else:
            strength = "WEAK"
        
        logger.info(f"MarketAux: {len(articles)} articles, avg sentiment: {avg_sentiment:.3f}, signal: {signal}")
        
        return {
            'status': 'success',
            'bias': round(avg_sentiment, 3),
            'signal': signal,
            'signal_strength': strength,
            'articles': len(articles),
            'headlines': headlines,
            'source': 'MarketAux API (Live)',
            'fetched_at': datetime.now(timezone.utc).isoformat()
        }
        
    except requests.Timeout:
        logger.error("MarketAux API timeout")
        return _error_response("API timeout")
    except requests.HTTPError as http_err:
        logger.error(f"MarketAux HTTP error: {http_err}")
        if http_err.response.status_code == 401:
            return _error_response("Invalid MarketAux API key")
        return _error_response(f"HTTP {http_err.response.status_code}")
    except Exception as e:
        logger.error(f"MarketAux error: {str(e)}")
        return _error_response(str(e))


def _error_response(error_msg: str) -> Dict:
    """Return error response."""
    return {
        'status': 'error',
        'bias': 0.0,
        'signal': 'ERROR',
        'signal_strength': 'NONE',
        'articles': 0,
        'headlines': [],
        'error': error_msg
    }


if __name__ == "__main__":
    # Test MarketAux service
    test_tickers = ["BHP.AX", "RIO.AX", "CBA.AX"]
    
    print("MarketAux News Sentiment Service Test")
    print("=" * 60)
    
    result = get_asx_news_sentiment(test_tickers)
    
    if result['status'] == 'success':
        print(f"Articles: {result['articles']}")
        print(f"Bias: {result['bias']}")
        print(f"Signal: {result['signal']} ({result['signal_strength']})")
        print(f"\nTop headlines:")
        for headline in result['headlines']:
            print(f"  - {headline['title']}")
    else:
        print(f"Status: {result['status']}")
        print(f"Message: {result.get('message', result.get('error'))}")

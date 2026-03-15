"""Market intelligence service for Australian sector sensitivity and transmission mechanisms.

This module provides sector-specific rate sensitivity data and AUD transmission logic
to enhance simulation realism when modeling RBA/Fed rate decisions and currency moves.
"""

import logging

logger = logging.getLogger(__name__)

# Sector rate sensitivity lookup (per user document)
# Maps ASX tickers to their interest rate sensitivity characteristics
SECTOR_RATE_SENSITIVITY = {
    # HIGH SENSITIVITY - Financial Sector
    "CBA.AX": {"sector": "Banks", "sensitivity": 1.8, "rate_bias": "bullish_on_hikes", 
               "reasoning": "Net Interest Margin (NIM) expansion from rising rates"},
    "WBC.AX": {"sector": "Banks", "sensitivity": 1.8, "rate_bias": "bullish_on_hikes",
               "reasoning": "Net Interest Margin (NIM) expansion from rising rates"},
    "NAB.AX": {"sector": "Banks", "sensitivity": 1.7, "rate_bias": "bullish_on_hikes",
               "reasoning": "Net Interest Margin (NIM) expansion from rising rates"},
    "ANZ.AX": {"sector": "Banks", "sensitivity": 1.7, "rate_bias": "bullish_on_hikes",
               "reasoning": "Net Interest Margin (NIM) expansion from rising rates"},
    "MQG.AX": {"sector": "Banks", "sensitivity": 1.5, "rate_bias": "bullish_on_hikes",
               "reasoning": "Investment banking fees benefit from higher yield environment"},
    
    # HIGH SENSITIVITY - REITs (inverse correlation)
    "GPT.AX": {"sector": "REITs", "sensitivity": -2.2, "rate_bias": "bearish_on_hikes",
               "reasoning": "Higher discount rates reduce property valuations; debt servicing costs increase"},
    "CQR.AX": {"sector": "REITs", "sensitivity": -2.0, "rate_bias": "bearish_on_hikes",
               "reasoning": "Higher discount rates reduce property valuations; debt servicing costs increase"},
    "VCX.AX": {"sector": "REITs", "sensitivity": -2.1, "rate_bias": "bearish_on_hikes",
               "reasoning": "Higher discount rates reduce property valuations; debt servicing costs increase"},
    "MGR.AX": {"sector": "REITs", "sensitivity": -1.9, "rate_bias": "bearish_on_hikes",
               "reasoning": "Higher discount rates reduce property valuations; debt servicing costs increase"},
    
    # MEDIUM SENSITIVITY - Infrastructure
    "APA.AX": {"sector": "Infrastructure", "sensitivity": -1.2, "rate_bias": "bearish_on_hikes",
               "reasoning": "High debt loads mean increased servicing costs"},
    "TLS.AX": {"sector": "Utilities", "sensitivity": -0.9, "rate_bias": "bearish_on_hikes",
               "reasoning": "Regulated returns less attractive vs risk-free bonds at higher rates"},
    "SYD.AX": {"sector": "Infrastructure", "sensitivity": -1.1, "rate_bias": "bearish_on_hikes",
               "reasoning": "High debt loads mean increased servicing costs"},
    
    # LOW SENSITIVITY - Resources (commodity-driven, not rate-driven)
    "BHP.AX": {"sector": "Resources", "sensitivity": 0.3, "rate_bias": "neutral",
               "reasoning": "Commodity price cycles and China demand dominate; rates have minimal direct impact"},
    "RIO.AX": {"sector": "Resources", "sensitivity": 0.3, "rate_bias": "neutral",
               "reasoning": "Commodity price cycles and China demand dominate; rates have minimal direct impact"},
    "FMG.AX": {"sector": "Resources", "sensitivity": 0.4, "rate_bias": "neutral",
               "reasoning": "Commodity price cycles and China demand dominate; rates have minimal direct impact"},
    "MIN.AX": {"sector": "Resources", "sensitivity": 0.4, "rate_bias": "neutral",
               "reasoning": "Lithium demand driven by EV adoption, not interest rates"},
    "LYC.AX": {"sector": "Resources", "sensitivity": 0.3, "rate_bias": "neutral",
               "reasoning": "Rare earth demand driven by tech supply chains and China policy"},
    "PLS.AX": {"sector": "Resources", "sensitivity": 0.4, "rate_bias": "neutral",
               "reasoning": "Lithium demand driven by EV adoption, not interest rates"},
    
    # LOW SENSITIVITY - Consumer Staples
    "WOW.AX": {"sector": "Consumer Staples", "sensitivity": -0.4, "rate_bias": "slightly_bearish_on_hikes",
               "reasoning": "Essential goods demand inelastic; margin pressure from consumer squeeze"},
    "COL.AX": {"sector": "Consumer Staples", "sensitivity": -0.4, "rate_bias": "slightly_bearish_on_hikes",
               "reasoning": "Essential goods demand inelastic; margin pressure from consumer squeeze"},
    
    # MEDIUM SENSITIVITY - Technology
    "XRO.AX": {"sector": "Technology", "sensitivity": -1.0, "rate_bias": "bearish_on_hikes",
               "reasoning": "Growth stock valuations compressed by higher discount rates"},
    "WTC.AX": {"sector": "Technology", "sensitivity": -0.9, "rate_bias": "bearish_on_hikes",
               "reasoning": "Growth stock valuations compressed by higher discount rates"},
    
    # LOW SENSITIVITY - Healthcare
    "CSL.AX": {"sector": "Healthcare", "sensitivity": -0.5, "rate_bias": "slightly_bearish_on_hikes",
               "reasoning": "Defensive sector; minimal direct rate impact but valuation compression"},
    "RHC.AX": {"sector": "Healthcare", "sensitivity": -0.5, "rate_bias": "slightly_bearish_on_hikes",
               "reasoning": "Defensive sector; minimal direct rate impact but valuation compression"},
}

# AUD transmission multiplier (per user document)
# When AUD moves, commodity exporters see amplified earnings impact in AUD terms
AUD_TRANSMISSION_MULTIPLIER = 0.85  # 85% pass-through of FX moves to resource stocks


def get_sector_context(ticker: str) -> dict:
    """Get sector sensitivity context for a ticker."""
    return SECTOR_RATE_SENSITIVITY.get(ticker, {
        "sector": "Unknown",
        "sensitivity": 0.0,
        "rate_bias": "neutral",
        "reasoning": "No sector data available"
    })


def detect_rate_event(event_data: dict) -> bool:
    """Detect if event is rate-related (RBA/Fed decision)."""
    event_type = event_data.get('event_type', '').lower()
    description = event_data.get('description', '').lower()
    notes = event_data.get('notes', '').lower()
    country = event_data.get('country', '').lower()
    
    # Check for rate-related keywords
    rate_keywords = ['rba', 'rate', 'interest', 'monetary policy', 'fed funds', 'federal reserve', 'cash rate']
    
    for keyword in rate_keywords:
        if keyword in event_type or keyword in description or keyword in notes:
            return True
    
    # Check if it's an Australian domestic policy event
    if country == 'australia' and ('policy' in event_type or 'decision' in description):
        return True
    
    return False


def detect_aud_event(event_data: dict) -> bool:
    """Detect if event significantly impacts AUD/USD."""
    event_type = event_data.get('event_type', '').lower()
    description = event_data.get('description', '').lower()
    notes = event_data.get('notes', '').lower()
    
    # AUD-impacting events
    aud_keywords = ['aud', 'currency', 'trade', 'commodity', 'china', 'iron ore', 'export']
    
    for keyword in aud_keywords:
        if keyword in event_type or keyword in description or keyword in notes:
            return True
    
    return False


def build_rate_sensitivity_context(ticker: str, event_data: dict) -> str:
    """Build rate sensitivity context to inject into agent prompts."""
    sector_info = get_sector_context(ticker)
    
    if not detect_rate_event(event_data):
        return ""  # No rate context needed
    
    sensitivity = sector_info['sensitivity']
    
    if abs(sensitivity) < 0.5:
        return f"\nMARKET CONTEXT: {ticker} ({sector_info['sector']}) has LOW rate sensitivity. {sector_info['reasoning']}"
    elif abs(sensitivity) >= 1.5:
        direction = "benefits significantly from" if sensitivity > 0 else "is highly vulnerable to"
        return f"\nMARKET CONTEXT: {ticker} ({sector_info['sector']}) {direction} rate hikes. {sector_info['reasoning']} Rate sensitivity: {abs(sensitivity):.1f}x"
    else:
        direction = "moderately benefits from" if sensitivity > 0 else "is moderately pressured by"
        return f"\nMARKET CONTEXT: {ticker} ({sector_info['sector']}) {direction} rate hikes. {sector_info['reasoning']}"


def build_aud_transmission_context(ticker: str, event_data: dict, aud_movement_pct: float = None) -> str:
    """Build AUD transmission mechanism context for commodity exporters."""
    sector_info = get_sector_context(ticker)
    
    # Only applies to resource/commodity exporters
    if sector_info['sector'] != 'Resources':
        return ""
    
    if not detect_aud_event(event_data) and aud_movement_pct is None:
        return ""
    
    # Use provided AUD movement or estimate from event type
    if aud_movement_pct is None:
        # Estimate based on event
        if 'china' in event_data.get('notes', '').lower():
            aud_movement_pct = -1.2  # China negative news typically weakens AUD
        elif 'trade' in event_data.get('description', '').lower():
            aud_movement_pct = -0.8
        else:
            aud_movement_pct = 0.0
    
    if abs(aud_movement_pct) < 0.3:
        return ""  # Minimal AUD impact
    
    # Calculate amplified impact
    amplified_impact = abs(aud_movement_pct) * AUD_TRANSMISSION_MULTIPLIER
    
    if aud_movement_pct < 0:
        # AUD depreciation - bullish for exporters
        return f"""
AUD TRANSMISSION MECHANISM: AUD depreciated ~{abs(aud_movement_pct):.1f}% from this event.
For {ticker} as a commodity exporter:
- USD commodity prices convert to {amplified_impact:.1f}% higher AUD revenue ({AUD_TRANSMISSION_MULTIPLIER*100:.0f}% pass-through)
- Example: If iron ore stays flat at $100 USD/t, {ticker} earns {amplified_impact:.1f}% more in AUD terms
- This FX tailwind partially or fully offsets negative headline sentiment"""
    else:
        # AUD appreciation - bearish for exporters
        return f"""
AUD TRANSMISSION MECHANISM: AUD appreciated ~{aud_movement_pct:.1f}% from this event.
For {ticker} as a commodity exporter:
- USD commodity prices convert to {amplified_impact:.1f}% lower AUD revenue ({AUD_TRANSMISSION_MULTIPLIER*100:.0f}% pass-through)
- This FX headwind compounds negative sentiment or offsets positive news"""


def build_enhanced_agent_context(ticker: str, event_data: dict, aud_movement_pct: float = None) -> str:
    """Build complete enhanced context string for agent prompts.
    
    Combines rate sensitivity and AUD transmission mechanisms.
    """
    contexts = []
    
    # Add rate sensitivity if relevant
    rate_context = build_rate_sensitivity_context(ticker, event_data)
    if rate_context:
        contexts.append(rate_context)
    
    # Add AUD transmission if relevant
    aud_context = build_aud_transmission_context(ticker, event_data, aud_movement_pct)
    if aud_context:
        contexts.append(aud_context)
    
    return "\n".join(contexts) if contexts else ""



def get_commodity_price_sensitivity(ticker: str) -> dict:
    """Get commodity price sensitivity for resource stocks.
    
    Returns sensitivity to Brent Crude and Gold price movements.
    Used for pre-simulation context generation.
    
    Args:
        ticker: ASX ticker symbol (e.g., 'BHP.AX')
    
    Returns:
        Dict with commodity_exposure and sensitivities
    """
    # Resource stocks have varying exposure to commodity prices
    commodity_sensitivity_map = {
        # Iron ore producers - high oil correlation (shipping/diesel costs)
        "BHP.AX": {
            "primary_commodity": "iron_ore",
            "oil_sensitivity": -0.15,  # Higher oil = higher costs = margin pressure
            "gold_sensitivity": 0.05,  # Weak positive (some gold exposure)
            "reasoning": "Major iron ore exporter; diesel/shipping costs sensitive to Brent"
        },
        "RIO.AX": {
            "primary_commodity": "iron_ore",
            "oil_sensitivity": -0.12,
            "gold_sensitivity": 0.03,
            "reasoning": "Diversified miner; iron ore shipping costs tied to oil"
        },
        "FMG.AX": {
            "primary_commodity": "iron_ore",
            "oil_sensitivity": -0.18,  # Pure iron ore = higher diesel sensitivity
            "gold_sensitivity": 0.0,
            "reasoning": "Pure-play iron ore; high diesel cost exposure"
        },
        
        # Gold producers - direct gold price exposure
        "NCM.AX": {
            "primary_commodity": "gold",
            "oil_sensitivity": -0.08,
            "gold_sensitivity": 0.85,  # Strong direct correlation
            "reasoning": "Major gold producer; revenues directly tied to gold price"
        },
        "EVN.AX": {
            "primary_commodity": "gold",
            "oil_sensitivity": -0.10,
            "gold_sensitivity": 0.80,
            "reasoning": "Gold miner; strong positive correlation to gold prices"
        },
        
        # Other resources - moderate oil sensitivity
        "MIN.AX": {
            "primary_commodity": "lithium",
            "oil_sensitivity": -0.08,
            "gold_sensitivity": 0.0,
            "reasoning": "Lithium producer; moderate energy cost exposure"
        },
        "LYC.AX": {
            "primary_commodity": "rare_earths",
            "oil_sensitivity": -0.06,
            "gold_sensitivity": 0.0,
            "reasoning": "Rare earths; moderate processing energy costs"
        },
        "PLS.AX": {
            "primary_commodity": "lithium",
            "oil_sensitivity": -0.08,
            "gold_sensitivity": 0.0,
            "reasoning": "Lithium producer; moderate energy cost exposure"
        },
        
        # Banks - minimal commodity sensitivity
        "CBA.AX": {
            "primary_commodity": "none",
            "oil_sensitivity": 0.0,
            "gold_sensitivity": 0.0,
            "reasoning": "Financial services; no direct commodity exposure"
        },
        "WBC.AX": {
            "primary_commodity": "none",
            "oil_sensitivity": 0.0,
            "gold_sensitivity": 0.0,
            "reasoning": "Financial services; no direct commodity exposure"
        }
    }
    
    return commodity_sensitivity_map.get(ticker, {
        "primary_commodity": "unknown",
        "oil_sensitivity": 0.0,
        "gold_sensitivity": 0.0,
        "reasoning": "No commodity exposure data available"
    })


def build_commodity_context(ticker: str, brent_price: float, gold_price: float) -> str:
    """Build commodity price context for pre-simulation analysis.
    
    Args:
        ticker: ASX ticker
        brent_price: Current Brent Crude price (USD/bbl)
        gold_price: Current Gold price (USD/oz)
    
    Returns:
        Formatted context string or empty if not relevant
    """
    sensitivity = get_commodity_price_sensitivity(ticker)
    
    # Skip if no meaningful commodity exposure
    if abs(sensitivity['oil_sensitivity']) < 0.05 and abs(sensitivity['gold_sensitivity']) < 0.05:
        return ""
    
    context_parts = []
    
    # Oil context
    if abs(sensitivity['oil_sensitivity']) >= 0.05:
        if sensitivity['oil_sensitivity'] < 0:
            context_parts.append(
                f"COMMODITY CONTEXT (Oil): Brent crude at ${brent_price:.2f}/bbl. "
                f"{ticker} has {abs(sensitivity['oil_sensitivity']):.0%} negative sensitivity "
                f"(higher oil = higher costs). {sensitivity['reasoning']}"
            )
        else:
            context_parts.append(
                f"COMMODITY CONTEXT (Oil): Brent crude at ${brent_price:.2f}/bbl. "
                f"{ticker} benefits from higher oil prices."
            )
    
    # Gold context
    if sensitivity['gold_sensitivity'] >= 0.05:
        context_parts.append(
            f"COMMODITY CONTEXT (Gold): Gold at ${gold_price:.2f}/oz. "
            f"{ticker} has {sensitivity['gold_sensitivity']:.0%} positive exposure "
            f"(direct revenue correlation). {sensitivity['reasoning']}"
        )
    
    return "\n".join(context_parts) if context_parts else ""


def get_pre_simulation_context(tickers: list, topic: str, brent_price: float = None, gold_price: float = None) -> dict:
    """Generate combined pre-simulation sentiment context.
    
    Combines GDELT geopolitical sentiment + MarketAux news sentiment + commodity prices.
    This is the 'powerful signal' mentioned in user requirements.
    
    Args:
        tickers: List of ASX tickers to analyze (e.g., ['BHP.AX', 'RIO.AX'])
        topic: Event topic/description for GDELT query
        brent_price: Current Brent price (will fetch if not provided)
        gold_price: Current Gold price (will fetch if not provided)
    
    Returns:
        Dict with combined sentiment analysis and commodity context
    """
    from services.gdelt_service import get_gdelt_sentiment_score
    from services.news_service import get_asx_news_sentiment
    from services.fred_service import get_commodity_prices
    
    result = {
        "topic": topic,
        "tickers": tickers,
        "gdelt_signal": {},
        "news_signal": {},
        "commodity_context": {},
        "combined_sentiment_bias": 0.0,
        "signal_strength": "UNKNOWN",
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # 1. Fetch GDELT geopolitical sentiment
    try:
        gdelt_data = get_gdelt_sentiment_score(topic)
        result["gdelt_signal"] = {
            "avgtone": gdelt_data.get("avgtone", 0.0),
            "article_count": gdelt_data.get("article_count", 0),
            "sentiment": gdelt_data.get("sentiment", "neutral"),
            "signal_strength": gdelt_data.get("signal_strength", "none"),
            "status": gdelt_data.get("status", "unknown")
        }
    except Exception as e:
        logger.error(f"GDELT fetch failed in pre-simulation context: {str(e)}")
        result["gdelt_signal"] = {"status": "error", "error": str(e)}
    
    # 2. Fetch MarketAux ticker-specific news sentiment
    try:
        news_data = get_asx_news_sentiment(tickers, hours=24)
        result["news_signal"] = {
            "bias": news_data.get("bias", 0.0),
            "signal": news_data.get("signal", "NEUTRAL"),
            "article_count": news_data.get("articles", 0),
            "signal_strength": news_data.get("signal_strength", "NONE"),
            "status": news_data.get("status", "unknown")
        }
    except Exception as e:
        logger.error(f"MarketAux fetch failed in pre-simulation context: {str(e)}")
        result["news_signal"] = {"status": "error", "error": str(e)}
    
    # 3. Fetch commodity prices if not provided
    if brent_price is None or gold_price is None:
        try:
            commodity_data = get_commodity_prices()
            if commodity_data['status'] == 'success':
                if brent_price is None:
                    brent_price = commodity_data['data'].get('brent_crude_price', {}).get('value', 82.50)
                if gold_price is None:
                    gold_price = commodity_data['data'].get('gold_price_usd', {}).get('value', 2650.00)
        except Exception as e:
            logger.warning(f"Commodity prices fetch failed, using defaults: {str(e)}")
            brent_price = brent_price or 82.50
            gold_price = gold_price or 2650.00
    
    result["commodity_context"] = {
        "brent_crude": brent_price,
        "gold": gold_price
    }
    
    # 4. Calculate combined sentiment bias
    # Weight GDELT (geopolitical) at 40%, MarketAux (ticker-specific) at 60%
    gdelt_bias = result["gdelt_signal"].get("avgtone", 0.0) / 10.0  # Normalize GDELT -10 to +10 scale to -1 to +1
    news_bias = result["news_signal"].get("bias", 0.0)  # MarketAux already -1 to +1
    
    combined_bias = (0.4 * gdelt_bias) + (0.6 * news_bias)
    result["combined_sentiment_bias"] = round(combined_bias, 3)
    
    # 5. Determine overall signal strength
    gdelt_strength = result["gdelt_signal"].get("signal_strength", "none")
    news_strength = result["news_signal"].get("signal_strength", "NONE")
    
    # Combine strength assessment
    if gdelt_strength in ["strong"] or news_strength in ["STRONG"]:
        result["signal_strength"] = "STRONG"
    elif gdelt_strength in ["moderate", "strong"] and news_strength in ["MODERATE", "STRONG"]:
        result["signal_strength"] = "STRONG"
    elif gdelt_strength in ["moderate"] or news_strength in ["MODERATE"]:
        result["signal_strength"] = "MODERATE"
    elif gdelt_strength == "weak" or news_strength == "WEAK":
        result["signal_strength"] = "WEAK"
    else:
        result["signal_strength"] = "INSUFFICIENT"
    
    # 6. Add commodity context strings for each ticker
    result["commodity_context_strings"] = {}
    for ticker in tickers:
        commodity_str = build_commodity_context(ticker, brent_price, gold_price)
        if commodity_str:
            result["commodity_context_strings"][ticker] = commodity_str
    
    return result


from datetime import datetime, timezone

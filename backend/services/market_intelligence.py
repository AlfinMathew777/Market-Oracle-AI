"""Market intelligence service for Australian sector sensitivity and transmission mechanisms.

This module provides sector-specific rate sensitivity data and AUD transmission logic
to enhance simulation realism when modeling RBA/Fed rate decisions and currency moves.
"""

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

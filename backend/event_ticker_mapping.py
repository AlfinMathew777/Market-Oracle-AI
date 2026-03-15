"""Event-to-Ticker mapping rules for Market Oracle AI.

Deterministic rules to map ACLED events to ASX tickers.
"""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# ASX tickers we support
ASX_TICKERS = {
    'BHP.AX': {
        'name': 'BHP Group',
        'sector': 'resources',
        'subsector': 'diversified_mining',
        'commodities': ['iron_ore', 'copper', 'coal', 'nickel'],
        'exposures': ['china_demand', 'commodity_prices', 'port_hedland', 'middle_east_conflict']
    },
    'RIO.AX': {
        'name': 'Rio Tinto',
        'sector': 'resources',
        'subsector': 'diversified_mining',
        'commodities': ['iron_ore', 'aluminum', 'copper'],
        'exposures': ['china_demand', 'commodity_prices', 'port_hedland', 'middle_east_conflict']
    },
    'FMG.AX': {
        'name': 'Fortescue Metals',
        'sector': 'resources',
        'subsector': 'iron_ore',
        'commodities': ['iron_ore'],
        'exposures': ['china_demand', 'commodity_prices', 'port_hedland']
    },
    'CBA.AX': {
        'name': 'Commonwealth Bank',
        'sector': 'financials',
        'subsector': 'banking',
        'commodities': [],
        'exposures': ['interest_rates', 'rba_policy', 'domestic_economy', 'property_market']
    },
    'LYC.AX': {
        'name': 'Lynas Rare Earths',
        'sector': 'resources',
        'subsector': 'rare_earths',
        'commodities': ['rare_earths', 'neodymium', 'praseodymium'],
        'exposures': ['china_supply', 'tech_demand', 'ev_demand', 'geopolitical_risk']
    }
}

# Geographic regions that affect ASX
REGION_MAPPING = {
    'Middle East': ['iran', 'iraq', 'saudi arabia', 'uae', 'israel', 'yemen', 'syria'],
    'China': ['china', 'beijing', 'shanghai'],
    'Australia': ['australia', 'perth', 'melbourne', 'sydney'],
    'Southeast Asia': ['indonesia', 'malaysia', 'singapore', 'philippines', 'vietnam'],
    'Africa': ['south africa', 'guinea', 'drc', 'congo', 'mozambique']
}


def map_event_to_ticker(event_data: dict, macro_context: Optional[dict] = None) -> Optional[str]:
    """
    Map ACLED conflict event to most relevant ASX ticker.
    
    Args:
        event_data: ACLED event dictionary with country, event_type, location, etc.
        macro_context: Optional dict with FRED data, AIS data, etc.
    
    Returns:
        ASX ticker string or None if no clear mapping
    """
    country = event_data.get('country', '').lower()
    location = event_data.get('location', '').lower()
    event_type = event_data.get('event_type', '').lower()
    fatalities = int(event_data.get('fatalities', 0))
    notes = event_data.get('notes', '').lower()
    
    logger.info(f"Mapping event: country={country}, type={event_type}, fatalities={fatalities}")
    
    # Rule 1: Middle East conflict → Resources stocks (commodity risk premium)
    if _is_middle_east(country, location):
        if fatalities >= 5 or 'battle' in event_type or 'violence' in event_type:
            logger.info("Middle East conflict detected → BHP.AX (major diversified miner)")
            return 'BHP.AX'
    
    # Rule 2: China economic/political events → Resources stocks
    if _is_china(country, location):
        if 'protest' in event_type or 'riot' in event_type:
            logger.info("China unrest detected → FMG.AX (pure iron ore play)")
            return 'FMG.AX'
    
    # Rule 3: Rare earth supply disruption keywords → LYC
    if _has_rare_earth_keywords(notes, event_type, location):
        logger.info("Rare earth supply risk detected → LYC.AX")
        return 'LYC.AX'
    
    # Rule 4: Port Hedland / Australian shipping disruption → Resources
    if macro_context and 'port_hedland_disruption' in macro_context:
        logger.info("Port Hedland disruption detected → RIO.AX")
        return 'RIO.AX'
    
    # Rule 5: Interest rate shock (from FRED) → CBA
    if macro_context and 'interest_rate_shock' in macro_context:
        logger.info("Interest rate shock detected → CBA.AX (banking)")
        return 'CBA.AX'
    
    # Rule 6: Africa mining regions → Diversified miners
    if _is_africa_mining_region(country, location):
        if fatalities >= 3:
            logger.info("Africa mining region conflict → RIO.AX")
            return 'RIO.AX'
    
    # Rule 7: Southeast Asia disruption → Supply chain impact on resources
    if _is_southeast_asia(country, location):
        if 'shipping' in notes or 'port' in notes or 'strait' in notes:
            logger.info("Southeast Asia shipping disruption → BHP.AX")
            return 'BHP.AX'
    
    # Default: High fatality events in key regions → BHP (safest default)
    if fatalities >= 10:
        logger.info(f"High fatality event (>10) → BHP.AX (default major)")
        return 'BHP.AX'
    
    logger.info("No clear ticker mapping found")
    return None


def _is_middle_east(country: str, location: str) -> bool:
    """Check if event is in Middle East."""
    middle_east_countries = REGION_MAPPING['Middle East']
    return any(c in country or c in location for c in middle_east_countries)


def _is_china(country: str, location: str) -> bool:
    """Check if event is in China."""
    return 'china' in country or 'china' in location


def _is_africa_mining_region(country: str, location: str) -> bool:
    """Check if event is in key African mining regions."""
    mining_countries = ['south africa', 'guinea', 'congo', 'mozambique', 'zambia']
    return any(c in country for c in mining_countries)


def _is_southeast_asia(country: str, location: str) -> bool:
    """Check if event is in Southeast Asia."""
    sea_countries = REGION_MAPPING['Southeast Asia']
    return any(c in country or c in location for c in sea_countries)


def _has_rare_earth_keywords(notes: str, event_type: str, location: str) -> bool:
    """Check for rare earth supply disruption keywords."""
    keywords = [
        'rare earth', 'rare-earth', 'neodymium', 'praseodymium',
        'mining facility', 'mine', 'mineral', 'lynas'
    ]
    text = f"{notes} {event_type} {location}"
    return any(keyword in text for keyword in keywords)


def get_ticker_info(ticker: str) -> Optional[dict]:
    """Get detailed info for an ASX ticker."""
    return ASX_TICKERS.get(ticker)


def get_all_tickers() -> List[str]:
    """Get list of all supported ASX tickers."""
    return list(ASX_TICKERS.keys())


if __name__ == "__main__":
    # Test mapping rules
    test_events = [
        {
            'country': 'Iran',
            'location': 'Strait of Hormuz',
            'event_type': 'Battles',
            'fatalities': 15,
            'notes': 'Armed confrontation at sea'
        },
        {
            'country': 'China',
            'location': 'Shanghai',
            'event_type': 'Protests',
            'fatalities': 0,
            'notes': 'Economic protests'
        },
        {
            'country': 'Malaysia',
            'location': 'Kuantan',
            'event_type': 'Strategic developments',
            'fatalities': 0,
            'notes': 'Rare earth processing facility disruption reported'
        }
    ]
    
    for i, event in enumerate(test_events, 1):
        print(f"\nTest {i}:")
        print(f"Event: {event['country']} - {event['event_type']}")
        ticker = map_event_to_ticker(event)
        print(f"Mapped Ticker: {ticker}")
        if ticker:
            info = get_ticker_info(ticker)
            print(f"Company: {info['name']}")

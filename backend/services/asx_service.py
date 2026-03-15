"""ASX stock price data service using yfinance.

Fetches real-time prices for 17 ASX tickers + 5-day historical data for sparklines.

No API key required - yfinance is free (unofficial Yahoo Finance scraper).
"""

import yfinance as yf
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

# 17 ASX tickers we track (expanded from original 5)
# Grouped by sector for UI display
ASX_TICKERS = [
    # Resources (diversified miners)
    'BHP.AX',  # BHP Group
    'RIO.AX',  # Rio Tinto
    'FMG.AX',  # Fortescue Metals
    # LNG/Energy
    'WDS.AX',  # Woodside Energy
    'STO.AX',  # Santos
    # Lithium
    'MIN.AX',  # Mineral Resources
    'PLS.AX',  # Pilbara Minerals
    # Banks
    'CBA.AX',  # Commonwealth Bank
    'WBC.AX',  # Westpac
    'ANZ.AX',  # ANZ Banking Group
    'NAB.AX',  # National Australia Bank
    # Gold
    'NCM.AX',  # Newcrest Mining
    'NST.AX',  # Northern Star Resources
    # Retail
    'WES.AX',  # Wesfarmers
    'WOW.AX',  # Woolworths
    # Rare Earths
    'LYC.AX',  # Lynas Rare Earths
    # Index
    '^AXJO'    # S&P/ASX 200 Index
]

# Ticker sector groupings for UI display
TICKER_GROUPS = {
    "RESOURCES": ['BHP.AX', 'RIO.AX', 'FMG.AX'],
    "LNG": ['WDS.AX', 'STO.AX'],
    "LITHIUM": ['MIN.AX', 'PLS.AX'],
    "BANKS": ['CBA.AX', 'WBC.AX', 'ANZ.AX', 'NAB.AX'],
    "GOLD": ['NCM.AX', 'NST.AX'],
    "RETAIL": ['WES.AX', 'WOW.AX'],
    "RARE EARTHS": ['LYC.AX'],
    "INDEX": ['^AXJO']
}


class ASXService:
    """Service for fetching ASX stock prices with historical data."""
    
    def get_current_prices(self) -> List[Dict[str, Any]]:
        """Get current prices + 5-day history for all 17 ASX tickers.
        
        Returns:
            List of ticker price data with history_5d for sparklines
        """
        prices = []
        
        try:
            logger.info("Fetching real-time prices for 17 ASX tickers via yfinance...")
            
            for ticker_symbol in ASX_TICKERS:
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    info = ticker.info
                    
                    # Get current price
                    current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose', 0)
                    
                    # Get previous close for change calculation
                    prev_close = info.get('previousClose', current_price)
                    
                    # Calculate change
                    if prev_close > 0:
                        change_pct = ((current_price - prev_close) / prev_close) * 100
                        change_abs = current_price - prev_close
                    else:
                        change_pct = 0
                        change_abs = 0
                    
                    # Fetch 5-day historical data for sparkline
                    history_5d = []
                    try:
                        hist_df = yf.download(ticker_symbol, period='5d', interval='1d', progress=False)
                        if not hist_df.empty:
                            for date, row in hist_df.iterrows():
                                history_5d.append({
                                    'date': date.strftime('%Y-%m-%d'),
                                    'close': round(float(row['Close']), 2)
                                })
                    except Exception as hist_error:
                        logger.warning(f"Could not fetch 5-day history for {ticker_symbol}: {hist_error}")
                    
                    ticker_data = {
                        'ticker': ticker_symbol,
                        'name': info.get('shortName', ticker_symbol),
                        'price': round(current_price, 2),
                        'currency': 'AUD',
                        'change_pct_1d': round(change_pct, 2),
                        'change_abs_1d': round(change_abs, 2),
                        'volume': info.get('volume', 0),
                        'market_cap': info.get('marketCap', 0),
                        'sector': info.get('sector', ''),
                        'history_5d': history_5d,
                        'updated_at': datetime.now().isoformat(),
                        'source': 'yfinance (Live)'
                    }
                    
                    prices.append(ticker_data)
                    logger.info(f"✓ {ticker_symbol}: ${current_price:.2f} ({change_pct:+.2f}%)")
                    
                except Exception as ticker_error:
                    logger.error(f"Failed to fetch {ticker_symbol}: {ticker_error}")
                    # Add unavailable entry
                    prices.append({
                        'ticker': ticker_symbol,
                        'name': ticker_symbol,
                        'price': 0,
                        'currency': 'AUD',
                        'change_pct_1d': 0,
                        'change_abs_1d': 0,
                        'volume': 0,
                        'market_cap': 0,
                        'sector': '',
                        'history_5d': [],
                        'updated_at': datetime.now().isoformat(),
                        'source': 'unavailable',
                        'error': str(ticker_error)
                    })
                
        except Exception as e:
            logger.error(f"Critical error fetching ASX prices: {str(e)}")
            return []
        
        logger.info(f"✓ Successfully fetched {len([p for p in prices if p.get('source') == 'yfinance (Live)'])} / {len(ASX_TICKERS)} tickers")
        return prices
    
    def get_ticker_price(self, ticker_symbol: str) -> Dict[str, Any]:
        """Get price for a specific ticker."""
        prices = self.get_current_prices()
        for price_data in prices:
            if price_data['ticker'] == ticker_symbol:
                return price_data
        return {}
    
    def get_ticker_groups(self) -> Dict[str, List[str]]:
        """Get ticker sector groupings for UI display."""
        return TICKER_GROUPS

"""ASX stock price data service using yfinance.

Fetches real-time prices for 17 ASX tickers + 5-day historical data for sparklines.

No API key required - yfinance is free (unofficial Yahoo Finance scraper).
"""

import yfinance as yf
from typing import Dict, List, Any
from datetime import datetime, timedelta, timezone
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
    'NST.AX',  # Northern Star Resources
    'EVN.AX',  # Evolution Mining
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
    "GOLD": ['NST.AX', 'EVN.AX'],
    "RETAIL": ['WES.AX', 'WOW.AX'],
    "RARE EARTHS": ['LYC.AX'],
    "INDEX": ['^AXJO']
}


_TICKER_NAMES = {
    'BHP.AX': 'BHP Group',       'RIO.AX': 'Rio Tinto',        'FMG.AX': 'Fortescue',
    'WDS.AX': 'Woodside',        'STO.AX': 'Santos',            'MIN.AX': 'Mineral Resources',
    'PLS.AX': 'Pilbara Minerals', 'CBA.AX': 'CommBank',         'WBC.AX': 'Westpac',
    'ANZ.AX': 'ANZ Bank',        'NAB.AX': 'NAB',               'NST.AX': 'Northern Star',
    'EVN.AX': 'Evolution Mining',   'WES.AX': 'Wesfarmers',        'WOW.AX': 'Woolworths',
    'LYC.AX': 'Lynas RE',        '^AXJO':  'ASX 200',
}


# Module-level cache shared across all instances
_asx_cache: List = []
_asx_cache_expiry: datetime | None = None
_ASX_CACHE_TTL = timedelta(minutes=5)


class ASXService:
    """Service for fetching ASX stock prices ? batch download with TTL cache."""

    def get_current_prices(self) -> List[Dict[str, Any]]:
        """Batch-download all 17 tickers in 2 requests, cache for 5 minutes."""
        global _asx_cache, _asx_cache_expiry
        now = datetime.now(timezone.utc)
        if _asx_cache and _asx_cache_expiry and now < _asx_cache_expiry:
            logger.info("Returning cached ASX prices")
            return _asx_cache

        try:
            logger.info("Batch-fetching 17 ASX tickers via yfinance...")

            # Single batch download for 5-day history (1 HTTP request for all tickers)
            symbols = " ".join(ASX_TICKERS)
            hist_df = yf.download(symbols, period="5d", interval="1d",
                                  progress=False, auto_adjust=True, group_by="ticker")

            # Batch Tickers object for current info (1 HTTP request)
            tickers_obj = yf.Tickers(symbols)

            prices = []
            for symbol in ASX_TICKERS:
                try:
                    info = tickers_obj.tickers[symbol].fast_info

                    current_price = getattr(info, 'last_price', None) or getattr(info, 'regular_market_price', 0) or 0
                    prev_close    = getattr(info, 'previous_close', current_price) or current_price

                    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
                    change_abs = current_price - prev_close

                    # Extract sparkline from batch history
                    history_5d = []
                    try:
                        if len(ASX_TICKERS) > 1 and symbol in hist_df.columns.get_level_values(0):
                            sym_hist = hist_df[symbol]["Close"].dropna()
                        else:
                            sym_hist = hist_df["Close"].dropna()
                        for date, close in sym_hist.items():
                            history_5d.append({'date': date.strftime('%Y-%m-%d'), 'close': round(float(close), 2)})
                    except Exception as e:
                        logger.debug("Could not parse history for %s: %s", symbol, e)

                    prices.append({
                        'ticker': symbol,
                        'name': _TICKER_NAMES.get(symbol, symbol),
                        'price': round(float(current_price), 2),
                        'currency': 'AUD',
                        'change_pct_1d': round(change_pct, 2),
                        'change_abs_1d': round(change_abs, 2),
                        'volume': getattr(info, 'three_month_average_volume', 0) or 0,
                        'market_cap': getattr(info, 'market_cap', 0) or 0,
                        'sector': '',
                        'history_5d': history_5d,
                        'updated_at': datetime.now().isoformat(),
                        'source': 'yfinance (Live)',
                    })
                    logger.info(f"? {symbol}: ${current_price:.2f} ({change_pct:+.2f}%)")

                except Exception as e:
                    logger.error(f"Failed to parse {symbol}: {e}")
                    prices.append({
                        'ticker': symbol, 'name': _TICKER_NAMES.get(symbol, symbol),
                        'price': 0, 'currency': 'AUD', 'change_pct_1d': 0,
                        'change_abs_1d': 0, 'volume': 0, 'market_cap': 0,
                        'sector': '', 'history_5d': [],
                        'updated_at': datetime.now().isoformat(), 'source': 'unavailable',
                    })

            _asx_cache = prices
            _asx_cache_expiry = now + _ASX_CACHE_TTL
            logger.info(f"? Batch fetch complete: {len(prices)} tickers cached for 5 min")
            return prices

        except Exception as e:
            logger.error(f"Critical error fetching ASX prices: {e}")
            return _asx_cache or []
    
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

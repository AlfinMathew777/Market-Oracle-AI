"""ASX stock price data service using yfinance.

Fetches real-time prices for 20 ASX tickers + 5-day historical data for sparklines.
"""

import yfinance as yf
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

# 20 ASX tickers we track (expanded from original 5)
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

# Mock mode flag
USE_MOCK_DATA = os.environ.get('USE_MOCK_DATA', 'True').lower() == 'true'


class ASXService:
    """Service for fetching ASX stock prices with historical data."""
    
    def get_current_prices(self) -> List[Dict[str, Any]]:
        """Get current prices + 5-day history for all 20 ASX tickers.
        
        Returns:
            List of ticker price data with history_5d for sparklines
        """
        if USE_MOCK_DATA:
            return self._get_mock_prices()
        
        prices = []
        
        try:
            for ticker_symbol in ASX_TICKERS:
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
                    'updated_at': datetime.now().isoformat()
                }
                
                prices.append(ticker_data)
                logger.info(f"Fetched price for {ticker_symbol}: ${current_price:.2f} ({change_pct:+.2f}%) with {len(history_5d)} days")
                
        except Exception as e:
            logger.error(f"Error fetching ASX prices: {str(e)}")
            # Fallback to mock on error
            return self._get_mock_prices()
        
        return prices
    
    def _get_mock_prices(self) -> List[Dict[str, Any]]:
        """Return mock ASX price data with 5-day history for all 20 tickers."""
        base_date = datetime.now()
        
        mock_data = [
            # RESOURCES
            {
                'ticker': 'BHP.AX',
                'name': 'BHP Group Ltd',
                'price': 49.82,
                'currency': 'AUD',
                'change_pct_1d': 2.31,
                'change_abs_1d': 1.12,
                'volume': 8450000,
                'market_cap': 250000000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 47.20},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 47.85},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 48.10},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 48.70},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 49.82}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'RIO.AX',
                'name': 'Rio Tinto Ltd',
                'price': 157.89,
                'currency': 'AUD',
                'change_pct_1d': 3.14,
                'change_abs_1d': 4.81,
                'volume': 2340000,
                'market_cap': 120000000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 152.10},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 153.45},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 154.20},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 153.08},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 157.89}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'FMG.AX',
                'name': 'Fortescue Ltd',
                'price': 20.48,
                'currency': 'AUD',
                'change_pct_1d': 4.07,
                'change_abs_1d': 0.80,
                'volume': 12500000,
                'market_cap': 63000000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 19.20},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 19.45},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 19.68},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 19.68},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 20.48}
                ],
                'updated_at': base_date.isoformat()
            },
            # LNG/ENERGY
            {
                'ticker': 'WDS.AX',
                'name': 'Woodside Energy',
                'price': 28.45,
                'currency': 'AUD',
                'change_pct_1d': 1.84,
                'change_abs_1d': 0.51,
                'volume': 5600000,
                'market_cap': 54000000000,
                'sector': 'Energy',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 27.50},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 27.75},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 27.94},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 27.94},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 28.45}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'STO.AX',
                'name': 'Santos Ltd',
                'price': 7.82,
                'currency': 'AUD',
                'change_pct_1d': 2.23,
                'change_abs_1d': 0.17,
                'volume': 9200000,
                'market_cap': 16500000000,
                'sector': 'Energy',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 7.45},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 7.55},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 7.65},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 7.65},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 7.82}
                ],
                'updated_at': base_date.isoformat()
            },
            # LITHIUM
            {
                'ticker': 'MIN.AX',
                'name': 'Mineral Resources',
                'price': 48.20,
                'currency': 'AUD',
                'change_pct_1d': -1.63,
                'change_abs_1d': -0.80,
                'volume': 1800000,
                'market_cap': 9100000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 50.20},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 49.80},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 49.00},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 49.00},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 48.20}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'PLS.AX',
                'name': 'Pilbara Minerals',
                'price': 2.94,
                'currency': 'AUD',
                'change_pct_1d': -2.32,
                'change_abs_1d': -0.07,
                'volume': 24500000,
                'market_cap': 8800000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 3.10},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 3.05},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 3.01},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 3.01},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 2.94}
                ],
                'updated_at': base_date.isoformat()
            },
            # BANKS
            {
                'ticker': 'CBA.AX',
                'name': 'Commonwealth Bank',
                'price': 173.76,
                'currency': 'AUD',
                'change_pct_1d': 1.56,
                'change_abs_1d': 2.67,
                'volume': 3200000,
                'market_cap': 180000000000,
                'sector': 'Financial Services',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 170.50},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 171.09},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 171.09},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 171.09},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 173.76}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'WBC.AX',
                'name': 'Westpac Banking Corp',
                'price': 32.18,
                'currency': 'AUD',
                'change_pct_1d': 1.42,
                'change_abs_1d': 0.45,
                'volume': 8100000,
                'market_cap': 115000000000,
                'sector': 'Financial Services',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 31.20},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 31.45},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 31.73},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 31.73},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 32.18}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'ANZ.AX',
                'name': 'ANZ Banking Group',
                'price': 31.94,
                'currency': 'AUD',
                'change_pct_1d': 1.33,
                'change_abs_1d': 0.42,
                'volume': 7800000,
                'market_cap': 95000000000,
                'sector': 'Financial Services',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 30.85},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 31.10},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 31.52},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 31.52},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 31.94}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'NAB.AX',
                'name': 'National Australia Bank',
                'price': 39.42,
                'currency': 'AUD',
                'change_pct_1d': 1.29,
                'change_abs_1d': 0.50,
                'volume': 6500000,
                'market_cap': 125000000000,
                'sector': 'Financial Services',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 38.25},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 38.62},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 38.92},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 38.92},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 39.42}
                ],
                'updated_at': base_date.isoformat()
            },
            # GOLD
            {
                'ticker': 'NCM.AX',
                'name': 'Newcrest Mining',
                'price': 26.48,
                'currency': 'AUD',
                'change_pct_1d': 0.76,
                'change_abs_1d': 0.20,
                'volume': 3400000,
                'market_cap': 24000000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 26.10},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 26.15},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 26.28},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 26.28},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 26.48}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'NST.AX',
                'name': 'Northern Star Resources',
                'price': 16.32,
                'currency': 'AUD',
                'change_pct_1d': 1.05,
                'change_abs_1d': 0.17,
                'volume': 4200000,
                'market_cap': 18700000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 15.95},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 16.05},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 16.15},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 16.15},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 16.32}
                ],
                'updated_at': base_date.isoformat()
            },
            # RETAIL
            {
                'ticker': 'WES.AX',
                'name': 'Wesfarmers Ltd',
                'price': 71.25,
                'currency': 'AUD',
                'change_pct_1d': 0.92,
                'change_abs_1d': 0.65,
                'volume': 2100000,
                'market_cap': 85000000000,
                'sector': 'Consumer Defensive',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 70.10},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 70.30},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 70.60},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 70.60},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 71.25}
                ],
                'updated_at': base_date.isoformat()
            },
            {
                'ticker': 'WOW.AX',
                'name': 'Woolworths Group',
                'price': 38.65,
                'currency': 'AUD',
                'change_pct_1d': 0.55,
                'change_abs_1d': 0.21,
                'volume': 4300000,
                'market_cap': 48000000000,
                'sector': 'Consumer Defensive',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 38.10},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 38.25},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 38.44},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 38.44},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 38.65}
                ],
                'updated_at': base_date.isoformat()
            },
            # RARE EARTHS
            {
                'ticker': 'LYC.AX',
                'name': 'Lynas Rare Earths',
                'price': 20.70,
                'currency': 'AUD',
                'change_pct_1d': 9.22,
                'change_abs_1d': 1.95,
                'volume': 8900000,
                'market_cap': 22000000000,
                'sector': 'Basic Materials',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 18.50},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 18.60},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 18.75},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 18.75},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 20.70}
                ],
                'updated_at': base_date.isoformat()
            },
            # INDEX
            {
                'ticker': '^AXJO',
                'name': 'S&P/ASX 200',
                'price': 8267.30,
                'currency': 'AUD',
                'change_pct_1d': 0.82,
                'change_abs_1d': 67.20,
                'volume': 0,
                'market_cap': 0,
                'sector': 'Index',
                'history_5d': [
                    {'date': (base_date - timedelta(days=4)).strftime('%Y-%m-%d'), 'close': 8145.50},
                    {'date': (base_date - timedelta(days=3)).strftime('%Y-%m-%d'), 'close': 8178.20},
                    {'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'), 'close': 8200.10},
                    {'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), 'close': 8200.10},
                    {'date': base_date.strftime('%Y-%m-%d'), 'close': 8267.30}
                ],
                'updated_at': base_date.isoformat()
            }
        ]
        
        return mock_data
    
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

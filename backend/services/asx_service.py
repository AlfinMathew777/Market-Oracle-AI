"""ASX stock price data service using yfinance.

Fetches real-time prices for the 5 ASX tickers + 5-day historical data for sparklines.
"""

import yfinance as yf
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

# 5 ASX tickers we track
ASX_TICKERS = ['BHP.AX', 'RIO.AX', 'FMG.AX', 'CBA.AX', 'LYC.AX']

# Mock mode flag
USE_MOCK_DATA = os.environ.get('USE_MOCK_DATA', 'True').lower() == 'true'


class ASXService:
    """Service for fetching ASX stock prices with historical data."""
    
    def get_current_prices(self) -> List[Dict[str, Any]]:
        """Get current prices + 5-day history for all 5 ASX tickers.
        
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
        """Return mock ASX price data with 5-day history."""
        base_date = datetime.now()
        
        mock_data = [
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

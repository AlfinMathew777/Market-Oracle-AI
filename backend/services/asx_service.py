"""ASX stock price data service using yfinance.

Fetches real-time prices for the 5 ASX tickers.
"""

import yfinance as yf
from typing import Dict, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 5 ASX tickers we track
ASX_TICKERS = ['BHP.AX', 'RIO.AX', 'FMG.AX', 'CBA.AX', 'LYC.AX']


class ASXService:
    """Service for fetching ASX stock prices."""
    
    def get_current_prices(self) -> List[Dict[str, Any]]:
        """Get current prices for all 5 ASX tickers.
        
        Returns:
            List of ticker price data
        """
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
                else:
                    change_pct = 0
                
                ticker_data = {
                    'ticker': ticker_symbol,
                    'name': info.get('shortName', ticker_symbol),
                    'price': round(current_price, 2),
                    'currency': 'AUD',
                    'change_pct_1d': round(change_pct, 2),
                    'volume': info.get('volume', 0),
                    'market_cap': info.get('marketCap', 0),
                    'sector': info.get('sector', ''),
                    'updated_at': datetime.now().isoformat()
                }
                
                prices.append(ticker_data)
                logger.info(f"Fetched price for {ticker_symbol}: ${current_price:.2f} ({change_pct:+.2f}%)")
                
        except Exception as e:
            logger.error(f"Error fetching ASX prices: {str(e)}")
            # Return empty list or fallback to cached data
            return []
        
        return prices
    
    def get_ticker_price(self, ticker_symbol: str) -> Dict[str, Any]:
        """Get price for a specific ticker."""
        prices = self.get_current_prices()
        for price_data in prices:
            if price_data['ticker'] == ticker_symbol:
                return price_data
        return {}

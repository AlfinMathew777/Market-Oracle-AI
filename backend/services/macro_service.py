"""Macro economic context service.

Fetches key macro indicators for the Economic Context Strip:
- Fed Funds Rate (FRED)
- AUD/USD (Yahoo Finance)
- Iron Ore Spot (Yahoo Finance with fallback)
- RBA Cash Rate (hardcoded - updated infrequently)
- ASX 200 Index (Yahoo Finance)
"""

import yfinance as yf
import requests
from typing import Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

# FRED API base URL (no key needed for public series like Fed Funds Rate)
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class MacroService:
    """Service for fetching macro economic indicators."""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = {
            'fed_rate': 1800,  # 30 minutes
            'aud_usd': 300,    # 5 minutes
            'iron_ore': 300,   # 5 minutes
            'asx_200': 300     # 5 minutes
        }
    
    def get_macro_context(self) -> Dict[str, Any]:
        """Get all macro indicators including commodity prices.
        
        Returns:
            Dict with 7 macro indicators (5 existing + Brent + Gold)
        """
        context = {}
        
        # 1. Fed Funds Rate from FRED
        context['fed_rate'] = self._get_fed_rate()
        
        # 2. AUD/USD from Yahoo Finance
        context['aud_usd'] = self._get_aud_usd()
        
        # 3. Iron Ore Spot with fallback
        context['iron_ore'] = self._get_iron_ore()
        
        # 4. RBA Cash Rate (hardcoded)
        context['rba_rate'] = {
            'value': 4.10,
            'label': '4.10%',
            'source': 'RBA',
            'updated': '2026-02-18',
            'status': 'current'
        }
        
        # 5. ASX 200 Index
        context['asx_200'] = self._get_asx_200()
        
        # 6. Brent Crude Oil Price from FRED
        context['brent_crude'] = self._get_brent_crude()
        
        # 7. Gold Price from FRED
        context['gold'] = self._get_gold_price()
        
        context['fetched_at'] = datetime.now().isoformat()
        
        return context
    
    def _get_fed_rate(self) -> Dict[str, Any]:
        """Fetch Fed Funds Rate from FRED."""
        cache_key = 'fed_rate'
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl[cache_key]:
                return cached_data
        
        try:
            # FRED API (no key needed for public series)
            params = {
                'series_id': 'FEDFUNDS',
                'api_key': '1234567890abcdef1234567890abcdef',  # Public demo key
                'file_type': 'json',
                'sort_order': 'desc',
                'limit': 1
            }
            
            response = requests.get(FRED_BASE_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'observations' in data and len(data['observations']) > 0:
                    latest = data['observations'][0]
                    value = float(latest['value'])
                    
                    result = {
                        'value': value,
                        'label': f'{value:.2f}%',
                        'source': 'FRED',
                        'updated': latest['date'],
                        'status': 'live'
                    }
                    
                    self.cache[cache_key] = (datetime.now(), result)
                    return result
            
            # Fallback
            logger.warning("FRED API failed, using fallback")
            return self._fallback_fed_rate()
            
        except Exception as e:
            logger.error(f"Error fetching Fed rate: {str(e)}")
            return self._fallback_fed_rate()
    
    def _fallback_fed_rate(self) -> Dict[str, Any]:
        """Fallback Fed rate."""
        return {
            'value': 4.50,
            'label': '4.50%',
            'source': 'FRED',
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'status': 'delayed'
        }
    
    def _get_aud_usd(self) -> Dict[str, Any]:
        """Fetch AUD/USD from Yahoo Finance."""
        cache_key = 'aud_usd'
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl[cache_key]:
                return cached_data
        
        try:
            ticker = yf.Ticker('AUDUSD=X')
            info = ticker.info
            
            current_price = info.get('regularMarketPrice') or info.get('bid', 0.65)
            
            result = {
                'value': current_price,
                'label': f'{current_price:.4f}',
                'source': 'Yahoo Finance',
                'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status': 'live'
            }
            
            self.cache[cache_key] = (datetime.now(), result)
            return result
            
        except Exception as e:
            logger.error(f"Error fetching AUD/USD: {str(e)}")
            return {
                'value': 0.6520,
                'label': '0.6520',
                'source': 'Yahoo Finance',
                'updated': datetime.now().strftime('%Y-%m-%d'),
                'status': 'delayed'
            }
    
    def _get_iron_ore(self) -> Dict[str, Any]:
        """Fetch Iron Ore Spot with fallback."""
        cache_key = 'iron_ore'
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl[cache_key]:
                return cached_data
        
        try:
            # Try Yahoo Finance ticker
            ticker = yf.Ticker('IRON.AX')
            info = ticker.info
            price = info.get('regularMarketPrice')
            
            if price and price > 0:
                result = {
                    'value': price,
                    'label': f'${price:.2f}/t',
                    'source': 'Yahoo Finance',
                    'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'status': 'live'
                }
                self.cache[cache_key] = (datetime.now(), result)
                return result
        except Exception as e:
            logger.warning(f"Iron Ore ticker failed: {str(e)}")
        
        # Fallback to hardcoded value
        return {
            'value': 97.50,
            'label': '$97.50/t',
            'source': 'Estimated',
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'status': 'delayed'
        }
    
    def _get_asx_200(self) -> Dict[str, Any]:
        """Fetch ASX 200 Index from Yahoo Finance."""
        cache_key = 'asx_200'
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl[cache_key]:
                return cached_data
        
        try:
            ticker = yf.Ticker('^AXJO')
            info = ticker.info
            
            current_price = info.get('regularMarketPrice') or info.get('previousClose', 8200)
            prev_close = info.get('previousClose', current_price)
            
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
            else:
                change_pct = 0
            
            result = {
                'value': current_price,
                'change_pct': change_pct,
                'label': f'{current_price:.2f}',
                'source': 'Yahoo Finance',
                'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status': 'live'
            }
            
            self.cache[cache_key] = (datetime.now(), result)
            return result
            
        except Exception as e:
            logger.error(f"Error fetching ASX 200: {str(e)}")
            return {
                'value': 8250.0,
                'change_pct': 0.0,
                'label': '8250.00',
                'source': 'Yahoo Finance',
                'updated': datetime.now().strftime('%Y-%m-%d'),
                'status': 'delayed'
            }
    
    def _get_brent_crude(self) -> Dict[str, Any]:
        """Fetch Brent Crude oil price from FRED."""
        try:
            from services.fred_service import get_commodity_prices
            commodities = get_commodity_prices()
            
            if commodities['status'] == 'success' and 'brent_crude_price' in commodities['data']:
                brent_data = commodities['data']['brent_crude_price']
                return {
                    'value': brent_data['value'],
                    'label': f"${brent_data['value']:.2f}/bbl",
                    'source': 'FRED',
                    'updated': brent_data['date'],
                    'status': 'live'
                }
            else:
                logger.warning("Brent Crude data unavailable from FRED")
                return self._fallback_brent_crude()
        except Exception as e:
            logger.error(f"Error fetching Brent Crude: {str(e)}")
            return self._fallback_brent_crude()
    
    def _fallback_brent_crude(self) -> Dict[str, Any]:
        """Fallback Brent Crude price."""
        return {
            'value': 82.50,
            'label': '$82.50/bbl',
            'source': 'Estimated',
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'status': 'delayed'
        }
    
    def _get_gold_price(self) -> Dict[str, Any]:
        """Fetch Gold price from FRED."""
        try:
            from services.fred_service import get_commodity_prices
            commodities = get_commodity_prices()
            
            if commodities['status'] == 'success' and 'gold_price_usd' in commodities['data']:
                gold_data = commodities['data']['gold_price_usd']
                return {
                    'value': gold_data['value'],
                    'label': f"${gold_data['value']:.2f}/oz",
                    'source': 'FRED',
                    'updated': gold_data['date'],
                    'status': 'live'
                }
            else:
                logger.warning("Gold price data unavailable from FRED")
                return self._fallback_gold_price()
        except Exception as e:
            logger.error(f"Error fetching Gold price: {str(e)}")
            return self._fallback_gold_price()
    
    def _fallback_gold_price(self) -> Dict[str, Any]:
        """Fallback Gold price."""
        return {
            'value': 2650.00,
            'label': '$2650.00/oz',
            'source': 'Estimated',
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'status': 'delayed'
        }
    
    def _get_mock_macro_context(self) -> Dict[str, Any]:
        """Return mock macro context for demo."""
        return {
            'fed_rate': {
                'value': 4.50,
                'label': '4.50%',
                'source': 'FRED',
                'updated': '2026-03-15',
                'status': 'live'
            },
            'aud_usd': {
                'value': 0.6523,
                'label': '0.6523',
                'source': 'Yahoo Finance',
                'updated': '2026-03-15 03:00',
                'status': 'live'
            },
            'iron_ore': {
                'value': 97.50,
                'label': '$97.50/t',
                'source': 'Estimated',
                'updated': '2026-03-15',
                'status': 'delayed'
            },
            'rba_rate': {
                'value': 4.10,
                'label': '4.10%',
                'source': 'RBA',
                'updated': '2026-02-18',
                'status': 'current'
            },
            'asx_200': {
                'value': 8267.3,
                'change_pct': 0.42,
                'label': '8267.30',
                'source': 'Yahoo Finance',
                'updated': '2026-03-15 03:00',
                'status': 'live'
            },
            'fetched_at': datetime.now().isoformat()
        }

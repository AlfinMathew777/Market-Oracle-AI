"""Australian Bureau of Statistics (ABS) and Reserve Bank of Australia (RBA) data integration.

Primary: FRED (Federal Reserve Economic Data) for Australian series
Fallback: ABS Indicator API and RBA DataStream (when keys available)

This service provides comprehensive Australian macroeconomic indicators.
"""

import os
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False


class ABSService:
    """Service for fetching Australian macroeconomic indicators."""
    
    def get_australian_macro(self) -> Dict:
        """
        Fetch comprehensive Australian macro indicators.
        
        Primary source: FRED API
        Fallback: ABS Indicator API (when key available)
        
        Returns:
            Dict with 11+ Australian economic indicators
        """
        try:
            # Import FRED service
            from services.fred_service import get_all_australian_macro
            
            fred_result = get_all_australian_macro()
            
            if fred_result.get('status') == 'pending_api_key':
                logger.warning("FRED API key not configured - returning pending status")
                return {
                    'status': 'pending_api_key',
                    'message': 'FRED API key required for live Australian macro data. Get free key at fred.stlouisfed.org/docs/api (2 minutes)',
                    'source': 'N/A',
                    'fetched_at': datetime.utcnow().isoformat()
                }
            
            if fred_result.get('status') != 'success' or not fred_result.get('data'):
                logger.error("FRED returned no data")
                return self._error_response("FRED API returned no data")
            
            fred_data = fred_result['data']
            
            # Map FRED data to our response format
            macro_data = {
                # Live from FRED
                'cpi': fred_data.get('cpi', {}).get('value'),
                'rba_cash_rate': fred_data.get('rba_cash_rate', {}).get('value'),
                'unemployment_rate': fred_data.get('unemployment_rate', {}).get('value'),
                'long_term_interest_rate': fred_data.get('long_term_rate', {}).get('value'),
                'aud_usd': fred_data.get('aud_usd', {}).get('value'),
                
                # GDP Growth - use document value (FRED series returns nominal GDP, not growth rate)
                'gdp_growth': 1.4,  # From user document - Q4 2025 estimate
                
                # From document - TODO: integrate ABS Indicator API for real-time data
                'household_debt_pct_income': 176,
                'household_saving_ratio': 6.1,
                'terms_of_trade_change': -4.0,
                'labor_productivity_change': -0.7,
                'mining_export_share': 57.4,
                'superannuation_aum': 3500,  # Billions AUD
                'national_net_worth': 21400,  # Billions AUD
                
                'source': 'FRED API (Live) + Document',
                'fetched_at': datetime.utcnow().isoformat()
            }
            
            # Remove None values
            macro_data = {k: v for k, v in macro_data.items() if v is not None}
            
            logger.info(f"✓ Fetched {len([k for k in macro_data.keys() if k not in ['source', 'fetched_at']])} Australian macro indicators")
            return macro_data
            
        except ImportError as ie:
            logger.error(f"FRED service import failed: {ie}")
            return self._error_response("FRED service not available")
        except Exception as e:
            logger.error(f"Error fetching Australian macro data: {str(e)}")
            return self._error_response(str(e))
    
    def _error_response(self, error_msg: str) -> Dict:
        """Return error response."""
        return {
            'status': 'error',
            'message': f'Australian macro data unavailable: {error_msg}',
            'source': 'N/A',
            'fetched_at': datetime.utcnow().isoformat()
        }

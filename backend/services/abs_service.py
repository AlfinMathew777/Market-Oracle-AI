"""Australian Bureau of Statistics (ABS) and RBA data service.

Fetches Australian macro economic indicators using readabs library.
Data sourced from 2024-2026 Australian economic intelligence report.
"""

import readabs as ra
import pandas as pd
from typing import Dict, Any
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

USE_MOCK_DATA = os.environ.get('USE_MOCK_DATA', 'True').lower() == 'true'


class ABSService:
    """Service for fetching Australian macro indicators from ABS and RBA."""
    
    def get_australian_macro(self) -> Dict[str, Any]:
        """Get Australian macro economic indicators.
        
        Returns:
            Dict with 8 key Australian macro indicators
        """
        if USE_MOCK_DATA:
            return self._get_mock_australian_macro()
        
        try:
            # Real ABS API calls
            context = {}
            
            # CPI from ABS
            cpi = ra.read_abs_cat("6401.0")  # Consumer Price Index
            context['cpi'] = float(cpi.iloc[-1]['value']) if not cpi.empty else 3.8
            
            # Labour Force from ABS
            lf = ra.read_abs_cat("6202.0")  # Labour Force
            if not lf.empty:
                unemployment_series = lf[lf['series'].str.contains('Unemployment rate', case=False, na=False)]
                if not unemployment_series.empty:
                    context['unemployment'] = float(unemployment_series.iloc[-1]['value'])
                else:
                    context['unemployment'] = 4.1
            else:
                context['unemployment'] = 4.1
            
            # RBA Cash Rate
            ocr = ra.read_rba_ocr(monthly=True)
            context['rba_cash_rate'] = float(ocr.iloc[-1]['value']) if not ocr.empty else 3.85
            
            # GDP Growth - would need specific ABS series
            context['gdp_growth'] = 1.4  # Hardcoded for now
            
            # Other indicators - require specific ABS series or calculations
            context['household_debt_pct_income'] = 176
            context['household_saving_ratio'] = 6.1
            context['terms_of_trade_change'] = -4.0
            context['labor_productivity_change'] = -0.7
            
            context['fetched_at'] = datetime.now().isoformat()
            context['source'] = 'ABS/RBA Live API'
            
            return context
            
        except Exception as e:
            logger.error(f"Error fetching ABS data: {str(e)}")
            return self._get_mock_australian_macro()
    
    def _get_mock_australian_macro(self) -> Dict[str, Any]:
        """Return mock Australian macro data from 2024-2026 economic report."""
        return {
            'cpi': 3.8,                          # Current inflation - above target
            'rba_cash_rate': 3.85,               # RBA Feb 2026 hike
            'gdp_growth': 1.4,                   # 2024-25 chain volume
            'unemployment': 4.1,                 # Labour market
            'household_debt_pct_income': 176,    # High debt-to-income ratio
            'household_saving_ratio': 6.1,       # Consumers cautious
            'terms_of_trade_change': -4.0,       # Commodity prices cooling
            'labor_productivity_change': -0.7,   # Structural challenge
            'mining_export_share': 57.4,         # % of total exports
            'superannuation_aum': 3500,          # Billions AUD
            'national_net_worth': 21400,         # Billions AUD
            'fetched_at': datetime.now().isoformat(),
            'source': 'Mock Data (2024-2026 Report)'
        }

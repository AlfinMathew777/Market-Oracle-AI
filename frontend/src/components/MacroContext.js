import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip';
import './MacroContext.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const MacroContext = () => {
  const [macroData, setMacroData] = useState(null);
  const [australianMacro, setAustralianMacro] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAllMacroData(); // Load immediately on mount
    const interval = setInterval(fetchAllMacroData, 300000); // Refresh every 5 min
    return () => clearInterval(interval);
  }, []);

  const fetchAllMacroData = async () => {
    try {
      // Fetch both macro-context and australian-macro in parallel
      const [contextResponse, ausResponse] = await Promise.all([
        fetch(`${BACKEND_URL}/api/data/macro-context`),
        fetch(`${BACKEND_URL}/api/data/australian-macro`)
      ]);
      
      const contextResult = await contextResponse.json();
      const ausResult = await ausResponse.json();
      
      if (contextResult.status === 'success') {
        setMacroData(contextResult.data);
      }
      if (ausResult.status === 'success') {
        setAustralianMacro(ausResult.data);
      }
      
      setLoading(false);
    } catch (err) {
      console.error('Error fetching macro data:', err);
      setLoading(false);
    }
  };

  if (loading || !macroData) {
    return (
      <div className="macro-context" data-testid="macro-context">
        <div className="macro-loading">Loading macro indicators...</div>
      </div>
    );
  }

  const indicators = [
    {
      label: 'FED FUNDS',
      value: macroData.fed_rate?.label || 'N/A',
      status: macroData.fed_rate?.status,
      testId: 'fed-rate'
    },
    {
      label: 'AUD/USD',
      value: macroData.aud_usd?.label || 'N/A',
      status: macroData.aud_usd?.status,
      testId: 'aud-usd'
    },
    {
      label: 'BRENT CRUDE',
      value: macroData.brent_crude?.label || 'N/A',
      status: macroData.brent_crude?.status,
      testId: 'brent-crude'
    },
    {
      label: 'GOLD',
      value: macroData.gold?.label || 'N/A',
      status: macroData.gold?.status,
      testId: 'gold'
    },
    {
      label: 'IRON ORE',
      value: macroData.iron_ore?.label || 'N/A',
      status: macroData.iron_ore?.status,
      testId: 'iron-ore'
    },
    {
      label: 'RBA CASH',
      value: macroData.rba_rate?.label || 'N/A',
      status: macroData.rba_rate?.status,
      testId: 'rba-rate'
    },
    {
      label: 'ASX 200',
      value: macroData.asx_200?.label || 'N/A',
      change: macroData.asx_200?.change_pct,
      status: macroData.asx_200?.status,
      testId: 'asx-200'
    }
  ];

  // Add Australian macro indicators if available
  if (australianMacro) {
    // CPI - Above RBA 2-3% target (warning signal)
    indicators.push({
      label: 'CPI',
      value: `${australianMacro.cpi?.toFixed(1)}%` || 'N/A',
      arrow: 'up', // Above target
      tooltip: 'Above RBA 2-3% target — rate hike pressure',
      testId: 'cpi'
    });
    
    // GDP Growth - Softening (warning signal)
    indicators.push({
      label: 'GDP',
      value: `${australianMacro.gdp_growth?.toFixed(1)}%` || 'N/A',
      arrow: 'down', // Softening growth
      tooltip: 'Softening from prior year — domestic demand cooling',
      testId: 'gdp-growth'
    });
  }

  return (
    <TooltipProvider>
      <div className="macro-context" data-testid="macro-context">
        {indicators.map((indicator, index) => (
          <React.Fragment key={indicator.testId}>
            <div className="macro-indicator" data-testid={`macro-${indicator.testId}`}>
              <span className="macro-label">{indicator.label}</span>
              
              {indicator.tooltip ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="macro-value macro-value-with-tooltip" data-testid={`macro-value-${indicator.testId}`}>
                      {indicator.value}
                      {indicator.arrow === 'up' && (
                        <span className="macro-arrow warning">
                          <TrendingUp size={12} />
                        </span>
                      )}
                      {indicator.arrow === 'down' && (
                        <span className="macro-arrow warning">
                          <TrendingDown size={12} />
                        </span>
                      )}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{indicator.tooltip}</p>
                  </TooltipContent>
                </Tooltip>
              ) : (
                <span className="macro-value" data-testid={`macro-value-${indicator.testId}`}>
                  {indicator.value}
                  {indicator.change !== undefined && indicator.change !== 0 && (
                    <span className={`macro-change ${indicator.change > 0 ? 'positive' : 'negative'}`}>
                      {indicator.change > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {Math.abs(indicator.change).toFixed(2)}%
                    </span>
                  )}
                </span>
              )}
              
              {indicator.status === 'delayed' && (
                <span className="macro-status-badge" title="Data may be delayed">
                  DELAYED
                </span>
              )}
            </div>
            {index < indicators.length - 1 && <div className="macro-divider" />}
          </React.Fragment>
        ))}
      </div>
    </TooltipProvider>
  );
};

export default MacroContext;

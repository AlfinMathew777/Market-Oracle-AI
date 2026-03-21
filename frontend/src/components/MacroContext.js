import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from './ui/tooltip';
import './MacroContext.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const MacroContext = () => {
  const [macroData, setMacroData] = useState(null);
  const [australianMacro, setAustralianMacro] = useState(null);
  const [supplyRisk, setSupplyRisk] = useState(null);
  const [chinaDemand, setChinaDemand] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAllMacroData();
    const interval = setInterval(fetchAllMacroData, 300000);
    return () => clearInterval(interval);
  }, []);

  const fetchAllMacroData = async () => {
    try {
      const [contextResponse, ausResponse, chokepointResponse, chinaResponse] = await Promise.all([
        fetch(`${BACKEND_URL}/api/data/macro-context`),
        fetch(`${BACKEND_URL}/api/data/australian-macro`),
        fetch(`${BACKEND_URL}/api/data/chokepoints?enriched=false`),
        fetch(`${BACKEND_URL}/api/data/china-demand`),
      ]);

      const contextResult = await contextResponse.json();
      const ausResult = await ausResponse.json();
      const cpResult = await chokepointResponse.json();
      const chinaResult = await chinaResponse.json();

      if (contextResult.status === 'success') setMacroData(contextResult.data);
      if (ausResult.status === 'success') setAustralianMacro(ausResult.data);
      if (cpResult.status === 'success') setSupplyRisk(cpResult.data.global_supply_at_risk_pct);
      if (chinaResult.status === 'success') setChinaDemand(chinaResult.data);

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
    indicators.push({
      label: 'CPI',
      value: `${australianMacro.cpi?.toFixed(1)}%` || 'N/A',
      arrow: 'up',
      tooltip: 'Above RBA 2-3% target — rate hike pressure',
      testId: 'cpi'
    });
    indicators.push({
      label: 'GDP',
      value: `${australianMacro.gdp_growth?.toFixed(1)}%` || 'N/A',
      arrow: 'down',
      tooltip: 'Softening from prior year — domestic demand cooling',
      testId: 'gdp-growth'
    });
  }

  // Supply Risk badge from chokepoint monitor
  if (supplyRisk !== null) {
    const riskColor = supplyRisk > 25 ? '#ff4444' : supplyRisk > 10 ? '#ff8800' : '#44cc88';
    const riskEmoji = supplyRisk > 25 ? '🔴' : supplyRisk > 10 ? '🟠' : '🟢';
    indicators.push({
      label: 'SUPPLY RISK',
      value: `${supplyRisk}% ${riskEmoji}`,
      tooltip: `${supplyRisk}% of global oil supply at risk from active maritime chokepoint disruptions. Red >25%, Amber 10-25%, Green <10%.`,
      testId: 'supply-risk',
      customColor: riskColor,
    });
  }

  // China Demand Signal from GDELT
  if (chinaDemand) {
    const demandColor =
      chinaDemand.color === 'red' ? '#ff4444' :
      chinaDemand.color === 'green' ? '#44cc88' : '#ff8800';
    indicators.push({
      label: 'CHINA DEMAND',
      value: chinaDemand.sentiment ? chinaDemand.sentiment.toUpperCase() : 'N/A',
      tooltip: `GDELT China steel/manufacturing sentiment (${chinaDemand.article_count || 0} articles). Green = strong demand, Amber = neutral, Red = weak demand. Affects BHP, RIO, FMG.`,
      testId: 'china-demand',
      customColor: demandColor,
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
                <span
                  className="macro-value"
                  data-testid={`macro-value-${indicator.testId}`}
                  style={indicator.customColor ? { color: indicator.customColor, fontWeight: 'bold' } : {}}
                >
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

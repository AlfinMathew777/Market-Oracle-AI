import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import './MacroContext.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const MacroContext = () => {
  const [macroData, setMacroData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMacroContext(); // Load immediately on mount
    const interval = setInterval(fetchMacroContext, 300000); // Refresh every 5 min
    return () => clearInterval(interval);
  }, []);

  const fetchMacroContext = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/data/macro-context`);
      const result = await response.json();
      if (result.status === 'success') {
        setMacroData(result.data);
        setLoading(false);
      }
    } catch (err) {
      console.error('Error fetching macro context:', err);
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

  return (
    <div className="macro-context" data-testid="macro-context">
      {indicators.map((indicator, index) => (
        <React.Fragment key={indicator.testId}>
          <div className="macro-indicator" data-testid={`macro-${indicator.testId}`}>
            <span className="macro-label">{indicator.label}</span>
            <span className="macro-value" data-testid={`macro-value-${indicator.testId}`}>
              {indicator.value}
              {indicator.change !== undefined && indicator.change !== 0 && (
                <span className={`macro-change ${indicator.change > 0 ? 'positive' : 'negative'}`}>
                  {indicator.change > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  {Math.abs(indicator.change).toFixed(2)}%
                </span>
              )}
            </span>
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
  );
};

export default MacroContext;

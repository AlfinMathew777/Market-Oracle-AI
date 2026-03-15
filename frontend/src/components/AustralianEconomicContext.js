import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip';
import './AustralianEconomicContext.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const AustralianEconomicContext = () => {
  const [australianData, setAustralianData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAustralianMacro();
    const interval = setInterval(fetchAustralianMacro, 300000); // Refresh every 5 min
    return () => clearInterval(interval);
  }, []);

  const fetchAustralianMacro = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/data/australian-macro`);
      const result = await response.json();
      if (result.status === 'success') {
        setAustralianData(result.data);
        setLoading(false);
      }
    } catch (err) {
      console.error('Error fetching Australian macro data:', err);
      setLoading(false);
    }
  };

  if (loading || !australianData) {
    return (
      <div className="australian-context-panel" data-testid="australian-context-panel">
        <h3 className="context-title">Australian Economic Context</h3>
        <div className="context-loading">Loading economic data...</div>
      </div>
    );
  }

  const metrics = [
    {
      label: 'GDP Growth',
      value: `${australianData.gdp_growth?.toFixed(1)}%`,
      trend: 'down',
      tooltip: 'Softening from prior year — domestic demand cooling. Lower GDP growth reduces corporate earnings expectations.',
      testId: 'gdp-growth'
    },
    {
      label: 'Inflation (CPI)',
      value: `${australianData.cpi?.toFixed(1)}%`,
      trend: 'up',
      tooltip: 'Above RBA 2-3% target — rate hike pressure. Persistent inflation forces RBA hawkish stance, pressuring rate-sensitive sectors.',
      testId: 'cpi'
    },
    {
      label: 'RBA Cash Rate',
      value: `${australianData.rba_cash_rate?.toFixed(2)}%`,
      trend: 'up',
      tooltip: 'Highest since 2011 — NIM expansion for banks (CBA, NAB) but headwind for REITs (GPT, VCX) and property developers.',
      testId: 'rba-rate'
    },
    {
      label: 'Household Debt',
      value: `${australianData.household_debt_pct_income}% of income`,
      trend: 'neutral',
      tooltip: 'World-leading debt-to-income ratio. High household leverage magnifies rate hike impact on consumer spending and property prices.',
      testId: 'household-debt'
    },
    {
      label: 'Saving Ratio',
      value: `${australianData.household_saving_ratio?.toFixed(1)}%`,
      trend: 'up',
      tooltip: 'Rising savings rate signals consumer caution. Households prioritizing debt reduction over discretionary spending.',
      testId: 'saving-ratio'
    },
    {
      label: 'Terms of Trade',
      value: `${australianData.terms_of_trade_change?.toFixed(1)}%`,
      trend: 'down',
      tooltip: 'Commodity price cooling reduces export revenue. Iron ore and coal price weakness directly impacts BHP, RIO, FMG earnings.',
      testId: 'terms-of-trade'
    },
    {
      label: 'Labor Productivity',
      value: `${australianData.labor_productivity_change?.toFixed(1)}%`,
      trend: 'down',
      tooltip: 'Structural productivity challenge. Declining productivity limits wage growth without inflation, constraining GDP potential.',
      testId: 'labor-productivity'
    },
    {
      label: 'Mining Export Share',
      value: `${australianData.mining_export_share?.toFixed(1)}%`,
      trend: 'neutral',
      tooltip: 'Mining dominates export revenue. ASX 200 has 57.4% exposure to commodity cycles, making China PMI a critical leading indicator.',
      testId: 'mining-share'
    },
    {
      label: 'Superannuation AUM',
      value: `$${(australianData.superannuation_aum / 1000).toFixed(1)}T`,
      trend: 'neutral',
      tooltip: '$3.5T super funds drive domestic equity demand. Super flows (0.65-0.75 correlation with S&P 500) create contagion risk from US sell-offs.',
      testId: 'super-aum'
    },
    {
      label: 'National Net Worth',
      value: `$${(australianData.national_net_worth / 1000).toFixed(1)}T`,
      trend: 'neutral',
      tooltip: '$21.4T national wealth heavily concentrated in residential property (60%). Property price weakness creates negative wealth effect.',
      testId: 'net-worth'
    }
  ];

  const getTrendIcon = (trend) => {
    if (trend === 'up') return <TrendingUp size={12} />;
    if (trend === 'down') return <TrendingDown size={12} />;
    return <Minus size={12} />;
  };

  const getTrendClass = (trend) => {
    if (trend === 'up') return 'trend-up';
    if (trend === 'down') return 'trend-down';
    return 'trend-neutral';
  };

  return (
    <TooltipProvider>
      <div className="australian-context-panel" data-testid="australian-context-panel">
        <h3 className="context-title">
          Australian Economic Context
          <span className="context-source">ABS / RBA</span>
        </h3>
        
        <div className="context-metrics">
          {metrics.map((metric) => (
            <Tooltip key={metric.testId}>
              <TooltipTrigger asChild>
                <div className="context-metric" data-testid={`context-${metric.testId}`}>
                  <div className="metric-header">
                    <span className="metric-label">{metric.label}</span>
                    <Info size={12} className="info-icon" />
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-value" data-testid={`value-${metric.testId}`}>
                      {metric.value}
                    </span>
                    <span className={`metric-trend ${getTrendClass(metric.trend)}`}>
                      {getTrendIcon(metric.trend)}
                    </span>
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" className="context-tooltip">
                <p>{metric.tooltip}</p>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
        
        <div className="context-footer">
          <span className="context-timestamp">
            Updated: {new Date(australianData.fetched_at).toLocaleTimeString('en-AU', { 
              hour: '2-digit', 
              minute: '2-digit' 
            })}
          </span>
          <span className="context-data-source">{australianData.source}</span>
        </div>
      </div>
    </TooltipProvider>
  );
};

export default AustralianEconomicContext;

import React, { useEffect, useState } from 'react';
import './SectorHeatmap.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

// Ticker sector groupings (matches backend TICKER_GROUPS)
const SECTOR_GROUPS = {
  "RESOURCES": ['BHP.AX', 'RIO.AX', 'FMG.AX'],
  "LNG": ['WDS.AX', 'STO.AX'],
  "LITHIUM": ['MIN.AX', 'PLS.AX'],
  "BANKS": ['CBA.AX', 'WBC.AX', 'ANZ.AX', 'NAB.AX'],
  "GOLD": ['NCM.AX', 'NST.AX'],
  "RETAIL": ['WES.AX', 'WOW.AX'],
  "RARE EARTHS": ['LYC.AX'],
  "INDEX": ['^AXJO']
};

const SectorHeatmap = () => {
  const [heatmapData, setHeatmapData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHeatmapData();
    // Refresh every 60 seconds
    const interval = setInterval(fetchHeatmapData, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchHeatmapData = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/data/asx-prices`);
      const data = await response.json();
      if (data.status === 'success') {
        setHeatmapData(data.data);
        setLoading(false);
      }
    } catch (err) {
      console.error('Error fetching heatmap data:', err);
      setLoading(false);
    }
  };

  const getTickerData = (ticker) => {
    return heatmapData.find(t => t.ticker === ticker);
  };

  const renderSparkline = (history5d, ticker) => {
    if (!history5d || history5d.length === 0) {
      return null;
    }

    // Extract close prices
    const prices = history5d.map(d => d.close);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice || 1;

    // Normalize to SVG coordinates
    const svgHeight = 30;
    const svgWidth = 60;
    const points = prices.map((price, index) => {
      const x = (index / (prices.length - 1)) * svgWidth;
      const y = svgHeight - ((price - minPrice) / priceRange) * svgHeight;
      return `${x},${y}`;
    }).join(' ');

    // Determine trend
    const isUptrend = prices[prices.length - 1] >= prices[0];
    const strokeColor = isUptrend ? '#00ff88' : '#ff3366';

    return (
      <svg width={svgWidth} height={svgHeight} className="sparkline">
        <polyline
          points={points}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.8"
        />
      </svg>
    );
  };

  const renderTickerCell = (ticker) => {
    const stock = getTickerData(ticker);
    
    if (!stock) {
      return (
        <div key={ticker} className="heatmap-cell empty" data-testid={`heatmap-cell-${ticker}`}>
          <div className="ticker-symbol">{ticker.replace('.AX', '').replace('^', '')}</div>
          <div className="ticker-price">--</div>
        </div>
      );
    }

    const isPositive = stock.change_pct_1d >= 0;
    const changeClass = isPositive ? 'positive' : 'negative';
    
    return (
      <div key={stock.ticker} className="heatmap-cell" data-testid={`heatmap-cell-${stock.ticker}`}>
        <div className="ticker-symbol" data-testid={`ticker-${stock.ticker}`}>
          {stock.ticker.replace('.AX', '').replace('^', '')}
        </div>
        <div className="ticker-price" data-testid={`price-${stock.ticker}`}>
          ${typeof stock.price === 'number' ? stock.price.toFixed(2) : stock.price}
        </div>
        <div className={`ticker-change ${changeClass}`} data-testid={`change-${stock.ticker}`}>
          {isPositive ? '+' : ''}{stock.change_pct_1d.toFixed(2)}%
        </div>
        <div className="ticker-sparkline" data-testid={`sparkline-${stock.ticker}`}>
          {renderSparkline(stock.history_5d, stock.ticker)}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="sector-heatmap" data-testid="sector-heatmap">
        <div className="heatmap-loading">Loading ASX watchlist...</div>
      </div>
    );
  }

  return (
    <div className="sector-heatmap" data-testid="sector-heatmap">
      <div className="heatmap-header">
        <span className="heatmap-title">ASX Watchlist — 17 Tickers</span>
        <span className="heatmap-subtitle">Live prices • Grouped by sector</span>
      </div>
      
      <div className="heatmap-scroll-container">
        <div className="heatmap-groups">
          {Object.entries(SECTOR_GROUPS).map(([sectorName, tickers], groupIndex) => (
            <React.Fragment key={sectorName}>
              <div className="sector-group" data-testid={`sector-group-${sectorName.toLowerCase().replace(' ', '-')}`}>
                <div className="sector-label">{sectorName}</div>
                <div className="sector-tickers">
                  {tickers.map(ticker => renderTickerCell(ticker))}
                </div>
              </div>
              {groupIndex < Object.entries(SECTOR_GROUPS).length - 1 && (
                <div className="sector-divider" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
};

export default SectorHeatmap;

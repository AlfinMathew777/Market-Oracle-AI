import React, { useEffect, useState } from 'react';
import './SectorHeatmap.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

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

  const renderSparkline = (history5d, ticker) => {
    if (!history5d || history5d.length === 0) {
      return null;
    }

    // Extract close prices
    const prices = history5d.map(d => d.close);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice || 1; // Avoid division by zero

    // Normalize to SVG coordinates (height: 40px)
    const svgHeight = 40;
    const svgWidth = 80;
    const points = prices.map((price, index) => {
      const x = (index / (prices.length - 1)) * svgWidth;
      const y = svgHeight - ((price - minPrice) / priceRange) * svgHeight;
      return `${x},${y}`;
    }).join(' ');

    // Determine trend: compare first and last
    const isUptrend = prices[prices.length - 1] >= prices[0];
    const strokeColor = isUptrend ? '#00ff88' : '#ff3366';

    return (
      <svg width={svgWidth} height={svgHeight} className="sparkline" style={{ display: 'block' }}>
        <polyline
          points={points}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.9"
        />
      </svg>
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
      {heatmapData.map((stock) => {
        const isPositive = stock.change_pct_1d >= 0;
        const changeClass = isPositive ? 'positive' : 'negative';
        
        return (
          <div key={stock.ticker} className="heatmap-cell" data-testid={`heatmap-cell-${stock.ticker}`}>
            <div className="ticker-symbol" data-testid={`ticker-${stock.ticker}`}>
              {stock.ticker.replace('.AX', '')}
            </div>
            <div className="ticker-price" data-testid={`price-${stock.ticker}`}>
              ${stock.price.toFixed(2)}
            </div>
            <div className={`ticker-change ${changeClass}`} data-testid={`change-${stock.ticker}`}>
              {isPositive ? '+' : ''}{stock.change_abs_1d.toFixed(2)} ({isPositive ? '+' : ''}{stock.change_pct_1d.toFixed(2)}%)
            </div>
            <div className="ticker-sparkline" data-testid={`sparkline-${stock.ticker}`}>
              {renderSparkline(stock.history_5d, stock.ticker)}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SectorHeatmap;

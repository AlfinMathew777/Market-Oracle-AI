import React from 'react';
import './TickerStrip.css';

function TickerStrip({ tickers }) {
  if (!tickers || tickers.length === 0) {
    return (
      <div className="ticker-strip">
        <h3>ASX Tickers</h3>
        <p className="loading">Loading prices...</p>
      </div>
    );
  }

  return (
    <div className="ticker-strip">
      <h3>ASX Prices</h3>
      <div className="ticker-list">
        {tickers.map((ticker) => (
          <div key={ticker.ticker} className="ticker-item">
            <div className="ticker-symbol">{ticker.ticker.replace('.AX', '')}</div>
            <div className="ticker-info">
              <div className="ticker-price">${ticker.price}</div>
              <div
                className={`ticker-change ${ticker.change_pct_1d >= 0 ? 'positive' : 'negative'}`}
              >
                {ticker.change_pct_1d >= 0 ? '▲' : '▼'} {Math.abs(ticker.change_pct_1d)}%
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default TickerStrip;

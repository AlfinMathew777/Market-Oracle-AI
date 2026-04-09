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

  // Filter out index symbols (e.g. ^AXJO) — show only individual stocks
  const stocks = tickers.filter((t) => !t.ticker.startsWith('^'));

  return (
    <div className="ticker-strip">
      <h3>ASX Tickers</h3>
      <div className="ticker-list">
        {stocks.map((ticker) => (
          <div key={ticker.ticker} className="ticker-item">
            <div className="ticker-symbol">{ticker.ticker.replace('.AX', '')}</div>
            <div className="ticker-info">
              <div className="ticker-price">${ticker.price?.toFixed(2) ?? '—'}</div>
              <div
                className={`ticker-change ${ticker.change_pct_1d >= 0 ? 'positive' : 'negative'}`}
              >
                {ticker.change_pct_1d >= 0 ? '▲' : '▼'}{Math.abs(ticker.change_pct_1d || 0).toFixed(1)}%
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default TickerStrip;

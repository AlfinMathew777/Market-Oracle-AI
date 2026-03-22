import React from 'react';
import './PredictionCard.css';

function PredictionCard({ prediction, onClose }) {
  if (!prediction) return null;

  const getDirectionIcon = (direction) => {
    switch (direction) {
      case 'UP':      return '▲';
      case 'DOWN':    return '▼';
      case 'NEUTRAL': return '—';
      default:        return '—';
    }
  };

  const getDirectionColor = (direction) => {
    switch (direction) {
      case 'UP':      return '#00ff88';
      case 'DOWN':    return '#ff3366';
      case 'NEUTRAL': return '#aaaaaa';
      default:        return '#aaaaaa';
    }
  };

  const confidencePercent = Math.round(prediction.confidence * 100);
  const dirColor = getDirectionColor(prediction.direction);

  // Neutral predictions with <5% confidence look like bugs when shown as "0%".
  // Show a plain-language label instead.
  const isNoSignal = prediction.direction === 'NEUTRAL' && confidencePercent < 5;
  const confidenceDisplay = isNoSignal ? 'No clear signal' : `${confidencePercent}%`;
  const confidenceColor   = isNoSignal ? '#666666' : dirColor;

  return (
    <div className="prediction-modal-overlay" onClick={onClose}>
      <div className="prediction-modal" onClick={e => e.stopPropagation()}>

        {/* Modal header */}
        <div className="pred-modal-header">
          <div className="pred-modal-title">Prediction Report</div>
          <div className="pred-modal-meta">{prediction.simulation_id}</div>
          <button className="pred-close-btn" onClick={onClose} title="Close">✕</button>
        </div>

        <div className="pred-modal-body">

          {/* Hero row */}
          <div className="pred-hero">
            <div className="pred-ticker">{prediction.ticker}</div>
            <div className="pred-direction" style={{ color: dirColor }}>
              <span className="pred-dir-icon">{getDirectionIcon(prediction.direction)}</span>
              <span className="pred-dir-text">{prediction.direction}</span>
            </div>
            <div className="pred-horizon-badge">
              {prediction.time_horizon === 'd7' ? '7-Day Outlook' : prediction.time_horizon}
            </div>
          </div>

          <div className="pred-timestamp">
            Generated {new Date(prediction.generated_at).toLocaleString('en-AU', {
              timeZone: 'Australia/Sydney', dateStyle: 'medium', timeStyle: 'short'
            })} AEST
          </div>

          {/* Confidence */}
          <div className="pred-section">
            <div className="pred-section-title">
              Confidence
              <span className="pred-conf-pct" style={{ color: confidenceColor }}>{confidenceDisplay}</span>
            </div>
            {!isNoSignal && (
              <div className="pred-conf-bar">
                <div className="pred-conf-fill" style={{ width: `${confidencePercent}%`, background: confidenceColor }} />
              </div>
            )}
          </div>

          {/* Agent consensus */}
          {prediction.agent_consensus && (
          <div className="pred-section">
            <div className="pred-section-title">
              Agent Consensus — {(prediction.agent_consensus.up ?? 0) + (prediction.agent_consensus.down ?? 0) + (prediction.agent_consensus.neutral ?? 0)} agents
            </div>
            <div className="pred-consensus-row">
              <div className="pred-consensus-item pred-up">
                <span>▲</span><span className="pred-cons-n">{prediction.agent_consensus.up ?? 0}</span><span>Bullish</span>
              </div>
              <div className="pred-consensus-item pred-down">
                <span>▼</span><span className="pred-cons-n">{prediction.agent_consensus.down ?? 0}</span><span>Bearish</span>
              </div>
              <div className="pred-consensus-item pred-neutral">
                <span>—</span><span className="pred-cons-n">{prediction.agent_consensus.neutral ?? 0}</span><span>Neutral</span>
              </div>
            </div>
          </div>
          )}

          {/* Two-column layout for the rest */}
          <div className="pred-two-col">

            {/* Causal chain */}
            <div className="pred-section">
              <div className="pred-section-title">Causal Chain</div>
              <ol className="pred-causal-list">
                {prediction.causal_chain && prediction.causal_chain.map((step, i) => (
                  <li key={i}>
                    <strong>{step.event}</strong>
                    <p>→ {step.consequence}</p>
                  </li>
                ))}
              </ol>
            </div>

            <div>
              {/* Key signals */}
              {prediction.key_signals && prediction.key_signals.length > 0 && (
                <div className="pred-section">
                  <div className="pred-section-title">Key Signals</div>
                  {prediction.key_signals.map((signal, i) => (
                    <div key={i} className="pred-signal">
                      <span className="pred-signal-type">{signal.signal_type}</span>
                      <p>{signal.description}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Trend context */}
              {prediction.trend_label && (
                <div className="pred-section pred-trend">
                  <div className="pred-section-title">Trend</div>
                  <div className="pred-trend-row">
                    <span className={`pred-trend-label pred-trend-${(prediction.trend_label || '').toLowerCase().replace('_', '-')}`}>
                      {prediction.trend_label}
                    </span>
                    {prediction.day_1_change != null && (
                      <span className="pred-trend-stat">Day1: {prediction.day_1_change > 0 ? '+' : ''}{prediction.day_1_change}%</span>
                    )}
                    {prediction.day_5_change != null && (
                      <span className="pred-trend-stat">Day5: {prediction.day_5_change > 0 ? '+' : ''}{prediction.day_5_change}%</span>
                    )}
                    {prediction.day_20_change != null && (
                      <span className="pred-trend-stat">Day20: {prediction.day_20_change > 0 ? '+' : ''}{prediction.day_20_change}%</span>
                    )}
                  </div>
                  {(prediction.consecutive_down_days != null || prediction.dist_from_52w_high_pct != null) && (
                    <div className="pred-trend-row pred-trend-secondary">
                      {prediction.consecutive_down_days != null && (
                        <span>Consecutive down days: {prediction.consecutive_down_days}</span>
                      )}
                      {prediction.dist_from_52w_high_pct != null && (
                        <span>Distance from 52w high: {prediction.dist_from_52w_high_pct}%</span>
                      )}
                    </div>
                  )}
                  {prediction.trend_emergency && (
                    <div className="pred-trend-warning pred-trend-emergency">⚠ Emergency fallback — live price history unavailable</div>
                  )}
                  {!prediction.trend_emergency && prediction.trend_from_cache && (
                    <div className="pred-trend-warning pred-trend-cache">
                      from cache{prediction.trend_cache_age_hours != null ? ` · ${prediction.trend_cache_age_hours}h ago` : ''}
                    </div>
                  )}
                </div>
              )}

              {/* Data freshness timestamp */}
              {prediction.data_freshness && (() => {
                const fetchedAt = prediction.data_freshness;
                // Parse "YYYY-MM-DD HH:MM UTC" to check age
                let isStale = false;
                try {
                  const parsed = new Date(fetchedAt.replace(' UTC', 'Z').replace(' ', 'T'));
                  isStale = (Date.now() - parsed.getTime()) > 10 * 60 * 1000; // 10 minutes
                } catch (_) {}
                return (
                  <div className="pred-section pred-freshness">
                    <span className="pred-freshness-label">Market data fetched:</span>{' '}
                    <span className="pred-freshness-ts">{fetchedAt}</span>
                    {isStale && (
                      <span className="pred-freshness-warn"> ⚠ Data may be stale</span>
                    )}
                    {prediction.ticker_volume_vs_avg != null && (
                      <span className="pred-freshness-vol">
                        {' '}· Volume {prediction.ticker_volume_vs_avg}x avg
                      </span>
                    )}
                  </div>
                );
              })()}

              {/* Contrarian view */}
              {prediction.contrarian_view && (
                <div className="pred-section pred-contrarian">
                  <div className="pred-section-title">⚠ Contrarian View</div>
                  <p>{prediction.contrarian_view}</p>
                </div>
              )}

              {/* Risk factors */}
              {prediction.risk_factors && prediction.risk_factors.length > 0 && (
                <div className="pred-section">
                  <div className="pred-section-title">Risk Factors</div>
                  <ul className="pred-risk-list">
                    {prediction.risk_factors.map((risk, i) => (
                      <li key={i}>{risk}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

          </div>

          <div className="pred-disclaimer">⚠ Analytical intelligence only. Not financial advice.</div>
        </div>
      </div>
    </div>
  );
}

export default PredictionCard;

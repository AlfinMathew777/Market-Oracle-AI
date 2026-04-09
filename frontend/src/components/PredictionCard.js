import React from 'react';
import './PredictionCard.css';

// Keywords that flag a signal as irrelevant for a given sector.
// Backend already filters before LLM call; this is a UI safety net.
const SECTOR_SIGNAL_BLOCKLIST = {
  Financials:   ['iron ore', 'iron_ore', 'copper', 'freight', 'diesel', 'pilbara', 'lng', 'aluminium'],
  Materials:    ['nim', 'mortgage', 'credit growth', 'rba cash rate', 'plasma'],
  Energy:       ['nim', 'mortgage', 'iron ore', 'copper', 'plasma'],
  Healthcare:   ['iron ore', 'nim', 'mortgage', 'freight', 'diesel'],
  'Consumer Staples': ['iron ore', 'china pmi', 'nim', 'mortgage'],
  Technology:   ['iron ore', 'china pmi', 'nim', 'mortgage', 'diesel', 'freight'],
  'Real Estate': ['iron ore', 'china pmi', 'nim', 'plasma'],
  // Rare earths: iron ore and base metals are not relevant
  'Rare Earths':  ['iron ore', 'iron_ore', 'copper', 'coal', 'steel', 'pilbara', 'nim', 'mortgage', 'china pmi'],
  // Lithium: iron ore not relevant (except MIN.AX which maps to Materials)
  Lithium:      ['iron ore', 'iron_ore', 'copper', 'coal', 'steel', 'nim', 'mortgage'],
};

const TICKER_SECTOR = {
  'BHP.AX': 'Materials', 'RIO.AX': 'Materials', 'FMG.AX': 'Materials', 'MIN.AX': 'Materials',
  'WDS.AX': 'Energy', 'STO.AX': 'Energy',
  'CBA.AX': 'Financials', 'NAB.AX': 'Financials', 'WBC.AX': 'Financials', 'ANZ.AX': 'Financials',
  'CSL.AX': 'Healthcare',
  'WOW.AX': 'Consumer Staples', 'COL.AX': 'Consumer Staples',
  'XRO.AX': 'Technology',
  'GMG.AX': 'Real Estate',
  // Rare earths & critical minerals
  'LYC.AX': 'Rare Earths',
  'ILU.AX': 'Rare Earths',
  // Lithium & battery metals
  'PLS.AX': 'Lithium',
  'IGO.AX': 'Lithium',
  'SYR.AX': 'Lithium',
};

function filterKeySignals(signals, ticker) {
  if (!signals || !ticker) return signals;
  const sector = TICKER_SECTOR[ticker];
  const blocklist = sector ? (SECTOR_SIGNAL_BLOCKLIST[sector] || []) : [];
  if (blocklist.length === 0) return signals;
  return signals.filter(s => {
    const text = ((s.signal_type || '') + ' ' + (s.description || '')).toLowerCase();
    return !blocklist.some(kw => text.includes(kw));
  });
}

function PredictionCard({ prediction, tradeExecution, accuracyStats, livePrice, reasoningData, onClose }) {
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

  // Signal grade from backend (A/B/C/D/F) — gate all actionable recommendations.
  const signalGrade = prediction.signal_grade || null;
  const isBlockedSignal = signalGrade === 'D' || signalGrade === 'F';
  const isWaitSignal    = !isBlockedSignal && signalGrade === 'C';

  // Use backend filtered recommendation (canonical `recommendation` field first).
  // Falls back through signal_recommendation → legacy derivation.
  const recommendation = tradeExecution?.action
    || prediction.recommendation
    || prediction.signal_recommendation
    || (isBlockedSignal
        ? 'HOLD'
        : prediction.direction === 'UP'   ? 'BUY'
        : prediction.direction === 'DOWN' ? 'SELL'
        : confidencePercent < 30         ? 'WAIT'
        :                                  'HOLD');

  // Show "was X" badge when the backend filtered the original signal
  const originalRec  = prediction.original_recommendation || null;
  const wasFiltered  = originalRec && originalRec !== recommendation;
  const isActionable = prediction.is_actionable !== undefined
    ? prediction.is_actionable
    : !isBlockedSignal && recommendation !== 'HOLD' && recommendation !== 'WAIT';

  const recColor = recommendation === 'BUY'   ? '#00ff88'
                 : recommendation === 'SELL'  ? '#ff3366'
                 : recommendation === 'WAIT'  ? '#ffaa00'
                 : recommendation === 'AVOID' ? '#ff8800'
                 :                             '#888888';

  // Grade badge colours
  const gradeColor = signalGrade === 'A' ? '#00ff88'
                   : signalGrade === 'B' ? '#66ffaa'
                   : signalGrade === 'C' ? '#ffcc00'
                   : signalGrade === 'D' ? '#ff8800'
                   : signalGrade === 'F' ? '#ff3366'
                   : '#666666';
  const gradeLabel = prediction.signal_grade_label || (signalGrade ? `Grade ${signalGrade}` : null);

  // Block reasons and warnings from filter_signal()
  const blockReasons  = prediction.signal_block_reasons  || [];
  const signalWarnings = prediction.signal_warnings || [];

  return (
    <div className="prediction-modal-overlay" onClick={onClose}>
      <div className="prediction-modal" onClick={e => e.stopPropagation()}>

        {/* Modal header */}
        <div className="pred-modal-header">
          <div className="pred-modal-title">Prediction Report</div>
          <div className="pred-modal-meta" style={{ color: '#666' }}>
            ID: {prediction.simulation_id}
          </div>
          <button className="pred-close-btn" onClick={onClose} title="Close">✕</button>
        </div>

        <div className="pred-modal-body">

          {/* ── Direction hero ── */}
          <div className={`pred-direction-hero hero-${prediction.direction === 'UP' ? 'up' : prediction.direction === 'DOWN' ? 'down' : 'neutral'}`}>
            <span className="pred-hero-icon">{getDirectionIcon(prediction.direction)}</span>
            <span className="pred-hero-label">{prediction.direction === 'UP' ? 'BULLISH' : prediction.direction === 'DOWN' ? 'BEARISH' : 'NEUTRAL'}</span>
          </div>

          {/* Hero row — ticker + horizon + action */}
          <div className="pred-hero">
            <div className="pred-ticker">{prediction.ticker}</div>
            <div className="pred-horizon-badge">
              {prediction.time_horizon === 'd7' ? '7-Day Outlook' : prediction.time_horizon}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
              <div className="pred-trade-action" style={{
                background: `${recColor}18`,
                color: recColor,
                border: `1px solid ${recColor}44`,
                padding: '4px 14px',
                borderRadius: '6px',
                fontFamily: 'monospace',
                fontWeight: 800,
                fontSize: '13px',
                letterSpacing: '1.5px',
              }}>
                {recommendation}
              </div>
              {wasFiltered && (
                <div style={{ color: '#666', fontSize: '10px', fontFamily: 'monospace' }}>
                  was {originalRec}
                </div>
              )}
            </div>
          </div>

          <div className="pred-timestamp">
            Generated {new Date(prediction.generated_at).toLocaleString('en-AU', {
              timeZone: 'Australia/Sydney', dateStyle: 'medium', timeStyle: 'short'
            })} AEST
            {livePrice && (
              <span className="pred-live-price">
                <span className="pred-live-dot" />
                LIVE ${livePrice.price.toFixed(2)}
                <span className={`pred-live-change ${livePrice.change_pct >= 0 ? 'pred-live-up' : 'pred-live-down'}`}>
                  {livePrice.change_pct >= 0 ? '+' : ''}{livePrice.change_pct.toFixed(2)}%
                </span>
              </span>
            )}
          </div>

          {/* ── Signal Quality Grade banner (D/F = blocked) ──────────────── */}
          {isBlockedSignal && (
            <div className="pred-signal-blocked" style={{
              background: '#1a0a0a',
              border: '1px solid #ff3366',
              borderRadius: '8px',
              padding: '10px 16px',
              marginBottom: '12px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ color: '#ff3366', fontSize: '18px', fontWeight: 900 }}>⊘</span>
                <div style={{ flex: 1 }}>
                  <div style={{ color: '#ff3366', fontWeight: 700, fontSize: '13px', letterSpacing: '1px' }}>
                    {signalGrade === 'F' ? 'NO ACTIONABLE SIGNAL' : 'CONFLICTING SIGNALS — DO NOT TRADE'}
                  </div>
                  {prediction.signal_filter_summary && (
                    <div style={{ color: '#aaa', fontSize: '11px', marginTop: '2px' }}>
                      {prediction.signal_filter_summary}
                    </div>
                  )}
                </div>
                {gradeLabel && (
                  <span style={{
                    color: gradeColor, border: `1px solid ${gradeColor}`, borderRadius: '4px',
                    padding: '2px 8px', fontSize: '11px', fontWeight: 700, fontFamily: 'monospace',
                    flexShrink: 0,
                  }}>
                    {signalGrade}
                  </span>
                )}
              </div>
              {blockReasons.length > 0 && (
                <ul style={{ margin: '8px 0 0 28px', padding: 0, listStyle: 'none' }}>
                  {blockReasons.map((reason, i) => (
                    <li key={i} style={{ color: '#cc4444', fontSize: '11px', marginBottom: '2px' }}>
                      • {reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* ── WAIT / monitor-only banner (C-grade) ─────────────────────── */}
          {isWaitSignal && !isBlockedSignal && (
            <div style={{
              background: '#1a1200',
              border: '1px solid #ffaa00',
              borderRadius: '8px',
              padding: '8px 14px',
              marginBottom: '12px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
            }}>
              <span style={{ color: '#ffaa00', fontSize: '15px' }}>⚠</span>
              <div>
                <div style={{ color: '#ffaa00', fontWeight: 700, fontSize: '12px', letterSpacing: '0.5px' }}>
                  MONITOR ONLY — NOT ACTIONABLE
                </div>
                {signalWarnings.length > 0 && (
                  <div style={{ color: '#aa8800', fontSize: '11px', marginTop: '2px' }}>
                    {signalWarnings[0]}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Decision Summary ───────────────────────────────────────────── */}
          <div className="pred-decision-summary" style={{ opacity: isBlockedSignal ? 0.6 : 1 }}>
            <div className="pred-ds-grid">
              <div className="pred-ds-item">
                <span className="pred-ds-label">Direction</span>
                <span className={`pred-ds-val pred-ds-dir-${(prediction.direction || 'neutral').toLowerCase()}`}>
                  {prediction.direction === 'UP' ? '▲ BULLISH'
                    : prediction.direction === 'DOWN' ? '▼ BEARISH'
                    : '— NEUTRAL'}
                </span>
              </div>
              <div className="pred-ds-item">
                <span className="pred-ds-label">Recommendation</span>
                <span className={`pred-ds-val pred-ds-rec-${recommendation.toLowerCase()}`}>
                  {recommendation}
                </span>
              </div>
              <div className="pred-ds-item">
                <span className="pred-ds-label">Confidence</span>
                <span className="pred-ds-val" style={{ color: confidenceColor }}>
                  {confidenceDisplay}
                  {!isNoSignal && (
                    <small className="pred-ds-sublabel">
                      {confidencePercent >= 70 ? ' HIGH' : confidencePercent >= 55 ? ' MED' : ' LOW'}
                    </small>
                  )}
                </span>
              </div>
              <div className="pred-ds-item">
                <span className="pred-ds-label">Signal Grade</span>
                <span className="pred-ds-val" style={{ color: gradeColor, fontFamily: 'monospace', fontWeight: 700 }}>
                  {gradeLabel || '—'}
                </span>
              </div>
            </div>
            {/* Why explanation */}
            <div className="pred-ds-why">
              {isBlockedSignal && (
                <span style={{ color: '#ff8800' }}>
                  Signal quality below trading threshold ({gradeLabel}). Data is shown for informational purposes only — no trade recommended.
                </span>
              )}
              {!isBlockedSignal && prediction.direction === 'NEUTRAL' && (
                <span>
                  Agent consensus is split ({prediction.agent_consensus?.up ?? 0} bullish / {prediction.agent_consensus?.down ?? 0} bearish / {prediction.agent_consensus?.neutral ?? 0} neutral) — no clear directional signal. Waiting for stronger conviction.
                </span>
              )}
              {!isBlockedSignal && prediction.direction === 'UP' && recommendation === 'BUY' && (
                <span>
                  Strong bullish consensus ({prediction.agent_consensus?.up ?? 0} agents). Entry and risk parameters are in the Trade Execution section below.
                </span>
              )}
              {!isBlockedSignal && prediction.direction === 'DOWN' && recommendation === 'SELL' && (
                <span>
                  Strong bearish consensus ({prediction.agent_consensus?.down ?? 0} agents). Exit and risk parameters are in the Trade Execution section below.
                </span>
              )}
              {!isBlockedSignal && prediction.direction === 'UP' && recommendation !== 'BUY' && (
                <span>
                  Directional bias is bullish but confidence ({confidencePercent}%) is below the actionable threshold. Monitoring only.
                </span>
              )}
            </div>
          </div>

          {/* ── Reasoning Quality Issues ───────────────────────────────────── */}
          {reasoningData?.reasoning_quality_issues?.length > 0 && (
            <div className="pred-quality-warning">
              <div className="pred-quality-title">Reasoning Quality Notes</div>
              <ul className="pred-quality-list">
                {reasoningData.reasoning_quality_issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
              <p className="pred-quality-note">
                Confidence may have been adjusted down due to the above. See Memory Context for calibration details.
              </p>
            </div>
          )}

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

            {/* Causal chain — war room visual flow */}
            <div className="pred-section">
              <div className="pred-section-title">Causal Chain</div>
              {prediction.causal_chain && prediction.causal_chain.length > 0 ? (
                <div className="pred-causal-chain">
                  {prediction.causal_chain.map((step, i) => (
                    <div key={i} className="pred-chain-step">
                      <div className="pred-chain-num">{i + 1}</div>
                      <div className="pred-chain-content">
                        <div className="pred-chain-title">{step.event}</div>
                        <p className="pred-chain-desc">{step.consequence}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#555', fontSize: '12px' }}>No causal chain data.</p>
              )}
            </div>

            <div>
              {/* Key signals */}
              {(() => {
                const signals = filterKeySignals(prediction.key_signals, prediction.ticker);
                return signals && signals.length > 0 ? (
                  <div className="pred-section">
                    <div className="pred-section-title">Key Signals</div>
                    {signals.map((signal, i) => (
                      <div key={i} className="pred-signal">
                        <span className="pred-signal-type">{signal.signal_type}</span>
                        <p>{signal.description}</p>
                      </div>
                    ))}
                  </div>
                ) : null;
              })()}

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

              {/* Monte Carlo simulation */}
              {(prediction.monte_carlo_confidence || prediction.monte_carlo_price) && (
                <div className="pred-section pred-monte-carlo">
                  <div className="pred-section-title">Monte Carlo Simulation</div>

                  {prediction.monte_carlo_confidence && (() => {
                    const mc = prediction.monte_carlo_confidence;
                    // Use dominant_stability_pct (dominant direction win rate) for display.
                    // direction_stability_pct is bearish_wins% — confusing for bullish signals.
                    const domStab = mc.dominant_stability_pct ?? (
                      mc.dominant_direction === 'bullish'
                        ? (100 - mc.direction_stability_pct)
                        : mc.direction_stability_pct
                    );
                    const stabLabel = domStab >= 70 ? 'STABLE'
                      : domStab >= 50 ? 'MODERATE'
                      : domStab >= 30 ? 'UNSTABLE'
                      : 'FRAGILE';
                    const stabColor = domStab >= 70 ? '#00ff88'
                      : domStab >= 50 ? '#58a6ff'
                      : domStab >= 30 ? '#d29922'
                      : '#f85149';
                    const isConvictionBlocked = domStab < 30;
                    const convictionColor = isConvictionBlocked ? '#666'
                      : mc.conviction_label === 'HIGH' ? '#00ff88'
                      : mc.conviction_label === 'MEDIUM' ? '#ffcc00'
                      : '#ff8800';
                    return (
                      <div className="pred-mc-confidence">
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">Signal Stability</span>
                          <span className="pred-mc-value" style={{ color: stabColor }}>
                            {domStab}% — {stabLabel}
                          </span>
                        </div>
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">Conviction</span>
                          <span className="pred-mc-value" style={{ color: convictionColor }}>
                            {isConvictionBlocked
                              ? `BLOCKED — stability ${domStab}% below 30% minimum`
                              : `${mc.conviction_label} · ${mc.dominant_direction.toUpperCase()}`
                            }
                          </span>
                        </div>
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">MC Vote Score</span>
                          <span className="pred-mc-value" style={{ color: '#ccc' }}>
                            {mc.mean_confidence}% ± {mc.confidence_std}%
                            <span style={{ color: '#555', fontSize: '10px', marginLeft: '4px' }}>
                              (internal vote metric — not pipeline confidence)
                            </span>
                          </span>
                        </div>
                        {!mc.is_stable && (
                          <div className="pred-mc-warning">
                            ⚠ {stabLabel} signal — confidence reduced 25% due to MC instability
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {prediction.monte_carlo_price && (() => {
                    const mp = prediction.monte_carlo_price;
                    const ptv = prediction.price_target_validation;
                    const targetCapped = ptv && !ptv.is_realistic;
                    const displayChangePct = targetCapped
                      ? ((ptv.adjusted_target - mp.current_price) / mp.current_price * 100).toFixed(2)
                      : mp.expected_change_pct;
                    const changeColor = displayChangePct >= 0 ? '#00ff88' : '#ff3366';
                    return (
                      <div className="pred-mc-price">
                        {targetCapped && (
                          <div style={{
                            background: '#1a1200', border: '1px solid #ff8800',
                            borderRadius: '4px', padding: '6px 10px', marginBottom: '8px',
                            color: '#ff8800', fontSize: '11px',
                          }}>
                            ⚠ {ptv.warning}
                          </div>
                        )}
                        <div className="pred-mc-price-header">
                          7-Day Price Range · {mp.current_price} → {' '}
                          <span style={{ color: changeColor }}>
                            {targetCapped ? ptv.adjusted_target.toFixed(2) : mp.expected_price_7d}
                            {' '}({displayChangePct > 0 ? '+' : ''}{displayChangePct}%)
                          </span>
                          {targetCapped && (
                            <span style={{ color: '#666', fontSize: '10px', marginLeft: '6px' }}>
                              [capped from {mp.expected_change_pct > 0 ? '+' : ''}{mp.expected_change_pct}%]
                            </span>
                          )}
                        </div>
                        <div className="pred-mc-ranges">
                          <div className="pred-mc-range-row">
                            <span className="pred-mc-range-label">90% CI</span>
                            <span className="pred-mc-range-val">{mp.range_90pct_low} – {mp.range_90pct_high}</span>
                          </div>
                          <div className="pred-mc-range-row">
                            <span className="pred-mc-range-label">68% CI</span>
                            <span className="pred-mc-range-val">{mp.range_68pct_low} – {mp.range_68pct_high}</span>
                          </div>
                        </div>
                        <div className="pred-mc-probs">
                          <div className="pred-mc-prob-item">
                            <span className="pred-mc-prob-label" style={{ color: '#ff3366' }}>↓5%+</span>
                            <span className="pred-mc-prob-val">{mp.prob_down_5pct}%</span>
                          </div>
                          <div className="pred-mc-prob-item">
                            <span className="pred-mc-prob-label" style={{ color: '#00ff88' }}>↑5%+</span>
                            <span className="pred-mc-prob-val">{mp.prob_up_5pct}%</span>
                          </div>
                          <div className="pred-mc-prob-item">
                            <span className="pred-mc-prob-label" style={{ color: '#ff3366' }}>↓10%+</span>
                            <span className="pred-mc-prob-val">{mp.prob_down_10pct}%</span>
                          </div>
                          <div className="pred-mc-prob-item">
                            <span className="pred-mc-prob-label" style={{ color: '#00ff88' }}>↑10%+</span>
                            <span className="pred-mc-prob-val">{mp.prob_up_10pct}%</span>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}

              {/* CVaR Tail Risk Analysis */}
              {prediction.monte_carlo_price?.risk_analysis && (() => {
                const ra = prediction.monte_carlo_price.risk_analysis;
                const riskLevelClass = (ra.risk_level || 'medium').toLowerCase().replace(' ', '-');
                const rasFill = Math.min(100, Math.max(0, (ra.risk_adjusted_score + 1) * 50));
                const rasColor = ra.risk_adjusted_score > 0 ? '#10b981' : '#ef4444';
                return (
                  <div className="risk-analysis-card">
                    <div className="risk-analysis-title">
                      <span>Tail Risk Analysis</span>
                      <span className={`risk-badge risk-badge-${riskLevelClass}`}>
                        {ra.risk_level}
                      </span>
                    </div>

                    <div className="risk-metrics-grid">
                      <div className="risk-metric">
                        <div className="risk-metric-label">VaR 95%</div>
                        <div className={`risk-metric-value ${ra.var_95 < 0 ? 'risk-neg' : 'risk-pos'}`}>
                          {ra.var_95 > 0 ? '+' : ''}{ra.var_95}%
                        </div>
                        <div className="risk-metric-desc">{ra.var_interpretation}</div>
                      </div>

                      <div className="risk-metric risk-metric-highlight">
                        <div className="risk-metric-label">CVaR 95%</div>
                        <div className={`risk-metric-value ${ra.cvar_95 < 0 ? 'risk-neg' : 'risk-pos'}`}>
                          {ra.cvar_95 > 0 ? '+' : ''}{ra.cvar_95}%
                        </div>
                        <div className="risk-metric-desc">{ra.cvar_interpretation}</div>
                      </div>

                      <div className="risk-metric">
                        <div className="risk-metric-label">Prob. of Profit</div>
                        <div className={`risk-metric-value ${ra.prob_profit >= 50 ? 'risk-pos' : 'risk-neg'}`}>
                          {ra.prob_profit}%
                        </div>
                        <div className="risk-metric-desc">Chance of positive return</div>
                      </div>

                      <div className="risk-metric">
                        <div className="risk-metric-label">Expected Return</div>
                        <div className={`risk-metric-value ${ra.expected_return >= 0 ? 'risk-pos' : 'risk-neg'}`}>
                          {ra.expected_return > 0 ? '+' : ''}{ra.expected_return}%
                        </div>
                        <div className="risk-metric-desc">Mean across 10,000 scenarios</div>
                      </div>
                    </div>

                    {/* Explain when high prob-profit is blocked by signal quality */}
                    {!isActionable && ra.prob_profit >= 60 && (
                      <div style={{
                        margin: '8px 0',
                        padding: '10px 12px',
                        background: 'rgba(210, 153, 34, 0.08)',
                        border: '1px solid rgba(210, 153, 34, 0.3)',
                        borderRadius: '6px',
                        color: '#d29922',
                        fontSize: '12px',
                        lineHeight: '1.5',
                      }}>
                        ⚠ Despite {ra.prob_profit}% probability of profit, this trade is <strong>not actionable</strong>.
                        {blockReasons.length > 0 && (
                          <span> Blocked: {blockReasons[0]}.</span>
                        )}
                        {' '}High probability from an unreliable signal is not sufficient for a trade.
                      </div>
                    )}

                    <div className="risk-ras-row">
                      <span className="risk-ras-label">Risk-Adjusted Score</span>
                      <div className="risk-ras-bar">
                        <div className="risk-ras-fill" style={{ width: `${rasFill}%`, backgroundColor: rasColor }} />
                      </div>
                      <span className="risk-ras-value">{ra.risk_adjusted_score.toFixed(2)}</span>
                    </div>

                    {ra.tail_risk_ratio > 1.5 && (
                      <div className="risk-tail-warning">
                        <span>Heavy tail risk — extreme losses more likely than normal distribution suggests</span>
                      </div>
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

          {/* ── Quant Engine Analysis (Phase 3 addition — additive only) ────────── */}
          {/* Shows when merge_predictions() has enriched the prediction with quant data. */}
          {/* Gracefully absent when quant engine is offline — zero impact on existing UI. */}

          {/* Quant unavailable note */}
          {prediction.quant_unavailable === true && (
            <div className="pred-quant-offline">
              Quant analysis unavailable — using agent consensus only
            </div>
          )}

          {/* Quant data sections — only render when fields are present */}
          {(prediction.quant_vol_regime || prediction.quant_var_95 != null || prediction.quant_technical_score != null) && (
            <div className="pred-section pred-quant-section">
              <div className="pred-section-title">Quant Analysis</div>
              <div className="pred-quant-grid">

                {prediction.quant_vol_regime && (
                  <div className="pred-quant-item">
                    <span className="pred-quant-label">Vol Regime</span>
                    <span className={`pred-vol-regime pred-vol-${prediction.quant_vol_regime.toLowerCase()}`}>
                      {prediction.quant_vol_regime}
                    </span>
                  </div>
                )}

                {prediction.quant_var_95 != null && (
                  <div className="pred-quant-item">
                    <span className="pred-quant-label">VaR 95%</span>
                    <span className="pred-quant-val">{(prediction.quant_var_95 * 100).toFixed(2)}%</span>
                  </div>
                )}

                {prediction.quant_cvar_95 != null && (
                  <div className="pred-quant-item">
                    <span className="pred-quant-label">CVaR 95%</span>
                    <span className="pred-quant-val">{(prediction.quant_cvar_95 * 100).toFixed(2)}%</span>
                  </div>
                )}

                {prediction.quant_technical_score != null && (
                  <div className="pred-quant-item">
                    <span className="pred-quant-label">Tech Score</span>
                    <span className={`pred-quant-val ${prediction.quant_technical_signal === 'BULLISH' ? 'pred-quant-bull' : prediction.quant_technical_signal === 'BEARISH' ? 'pred-quant-bear' : ''}`}>
                      {(prediction.quant_technical_score * 100).toFixed(0)} / 100
                      {prediction.quant_technical_signal ? ` · ${prediction.quant_technical_signal}` : ''}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Prediction sources bar chart */}
          {prediction.prediction_sources && (
            <div className="pred-section pred-sources-section">
              <div className="pred-section-title">Prediction Sources</div>
              {[
                { name: 'Quant Engine', pct: prediction.prediction_sources.quant_pct  ?? 0, color: '#ff8800' },
                { name: 'Agent Swarm',  pct: prediction.prediction_sources.agents_pct ?? 0, color: '#3399ff' },
                { name: 'OSINT',        pct: prediction.prediction_sources.osint_pct  ?? 0, color: '#9966ff' },
              ].map(({ name, pct, color }) => (
                <div key={name} className="pred-source-row">
                  <span className="pred-source-name">{name}</span>
                  <div className="pred-source-bar-bg">
                    <div className="pred-source-bar-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="pred-source-pct">{pct}%</span>
                </div>
              ))}
            </div>
          )}

          {/* ── Trade Execution ────────────────────────────────────────────── */}
          {/* Never render a live trade plan when the signal is blocked (grade D/F). */}
          {tradeExecution && (isBlockedSignal || !isActionable) ? (
            <div className="pred-section pred-trade-wait-section">
              <div className="pred-section-title">Trade Execution Plan</div>
              <div className="pred-trade-wait-state">
                <span className="pred-trade-wait-icon">⊘</span>
                <div className="pred-trade-wait-label" style={{ color: '#ff3366' }}>
                  NO TRADE — Signal below threshold
                </div>
                <p className="pred-trade-wait-reason">
                  Grade {signalGrade} signal is not actionable. No trade parameters have been generated.
                  {blockReasons.length > 0 && ` Blocked: ${blockReasons[0]}`}
                </p>
              </div>
            </div>
          ) : tradeExecution ? (
            <div className="pred-section pred-trade-section">
              <div className="pred-section-title">
                Trade Execution Plan
                <span className={`pred-trade-grade pred-grade-${tradeExecution.setup_quality?.replace('+','plus')}`}>
                  {tradeExecution.setup_quality} Setup
                </span>
              </div>

              <div className="pred-trade-action-row">
                <span className={`pred-trade-action pred-trade-action-${tradeExecution.action?.toLowerCase()}`}>
                  {tradeExecution.action}
                </span>
                <span className="pred-trade-timeframe">{tradeExecution.timeframe}</span>
                <span className="pred-trade-order">{tradeExecution.order_type} order</span>
              </div>

              <div className="pred-trade-levels">
                <div className="pred-trade-level pred-trade-entry">
                  <span className="pred-trade-level-label">Entry</span>
                  <span className="pred-trade-level-val">${tradeExecution.entry_price?.toFixed(2)}</span>
                  <span className="pred-trade-level-sub">zone ${tradeExecution.entry_zone_low?.toFixed(2)} – ${tradeExecution.entry_zone_high?.toFixed(2)}</span>
                </div>
                <div className="pred-trade-level pred-trade-stop">
                  <span className="pred-trade-level-label">Stop Loss</span>
                  <span className="pred-trade-level-val">${tradeExecution.stop_loss?.toFixed(2)}</span>
                  <span className="pred-trade-level-sub">{tradeExecution.stop_loss_rationale}</span>
                </div>
                <div className="pred-trade-targets">
                  {tradeExecution.take_profit_1 && (
                    <div className="pred-trade-level pred-trade-tp">
                      <span className="pred-trade-level-label">TP1</span>
                      <span className="pred-trade-level-val">${tradeExecution.take_profit_1?.toFixed(2)}</span>
                    </div>
                  )}
                  {tradeExecution.take_profit_2 && (
                    <div className="pred-trade-level pred-trade-tp">
                      <span className="pred-trade-level-label">TP2</span>
                      <span className="pred-trade-level-val">${tradeExecution.take_profit_2?.toFixed(2)}</span>
                    </div>
                  )}
                  {tradeExecution.take_profit_3 && (
                    <div className="pred-trade-level pred-trade-tp">
                      <span className="pred-trade-level-label">TP3</span>
                      <span className="pred-trade-level-val">${tradeExecution.take_profit_3?.toFixed(2)}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="pred-trade-risk-row">
                <div className="pred-trade-risk-item">
                  <span className="pred-trade-risk-label">Risk / Reward</span>
                  <span className="pred-trade-risk-val">{tradeExecution.risk_reward?.risk_reward_ratio?.toFixed(2)}:1</span>
                </div>
                <div className="pred-trade-risk-item">
                  <span className="pred-trade-risk-label">Risk %</span>
                  <span className="pred-trade-risk-val">{tradeExecution.risk_reward?.risk_percent?.toFixed(2)}%</span>
                </div>
                <div className="pred-trade-risk-item">
                  <span className="pred-trade-risk-label">Position Size</span>
                  <span className="pred-trade-risk-val">{tradeExecution.position_size_percent?.toFixed(1)}% of portfolio</span>
                </div>
                <div className="pred-trade-risk-item">
                  <span className="pred-trade-risk-label">Max Loss</span>
                  <span className="pred-trade-risk-val pred-trade-risk-danger">{tradeExecution.max_loss_percent?.toFixed(2)}%</span>
                </div>
              </div>

              {tradeExecution.entry_conditions?.length > 0 && (
                <div className="pred-trade-conditions">
                  <div className="pred-trade-cond-title">Entry Conditions</div>
                  <ul className="pred-trade-cond-list">
                    {tradeExecution.entry_conditions.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}

              {tradeExecution.invalidation_conditions?.length > 0 && (
                <div className="pred-trade-conditions">
                  <div className="pred-trade-cond-title">Invalidation Conditions</div>
                  <ul className="pred-trade-cond-list pred-trade-cond-invalid">
                    {tradeExecution.invalidation_conditions.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="pred-section pred-trade-wait-section">
              <div className="pred-section-title">Trade Execution Plan</div>
              <div className="pred-trade-wait-state">
                <span className="pred-trade-wait-icon">{recommendation === 'WAIT' ? '⏳' : '⏸'}</span>
                <div className="pred-trade-wait-label">{recommendation} — No Trade Parameters</div>
                <p className="pred-trade-wait-reason">
                  {recommendation === 'WAIT'
                    ? 'Signal strength is below the actionable threshold. Wait for clearer directional conviction before entering a position.'
                    : 'Market direction is neutral. No entry, stop-loss, or take-profit parameters have been generated for this signal.'}
                </p>
              </div>
            </div>
          )}

          {/* ── Accuracy Stats ─────────────────────────────────────────────── */}
          {accuracyStats && (
            <div className="pred-section pred-accuracy-section">
              <div className="pred-section-title">
                Historical Accuracy — {prediction.ticker}
              </div>
              {accuracyStats.total_predictions === 0 ? (
                <div className="pred-acc-empty">
                  <span className="pred-acc-empty-icon">📊</span>
                  <span className="pred-acc-empty-label">No Track Record Yet</span>
                  <p className="pred-acc-empty-note">
                    This is the first prediction for {prediction.ticker}. Accuracy stats will build as predictions resolve over the coming days.
                  </p>
                </div>
              ) : (
                <>
                  <div className="pred-accuracy-grid">
                    <div className="pred-acc-item">
                      <span className="pred-acc-val" style={{
                        color: (accuracyStats.accuracy_pct ?? 0) >= 60 ? '#00ff88'
                             : (accuracyStats.accuracy_pct ?? 0) >= 40 ? '#ffcc00'
                             : '#ff3366'
                      }}>
                        {accuracyStats.accuracy_pct ?? 0}%
                      </span>
                      <span className="pred-acc-label">Accuracy</span>
                    </div>
                    <div className="pred-acc-item">
                      <span className="pred-acc-val">{accuracyStats.resolved_predictions ?? 0}</span>
                      <span className="pred-acc-label">Resolved</span>
                    </div>
                    <div className="pred-acc-item">
                      <span className="pred-acc-val" style={{ color: '#00ff88' }}>{accuracyStats.correct ?? 0}</span>
                      <span className="pred-acc-label">Correct</span>
                    </div>
                    <div className="pred-acc-item">
                      <span className="pred-acc-val" style={{ color: '#ff3366' }}>
                        {accuracyStats.incorrect ?? 0}
                      </span>
                      <span className="pred-acc-label">Incorrect</span>
                    </div>
                    {accuracyStats.avg_confidence != null && (
                      <div className="pred-acc-item">
                        <span className="pred-acc-val">{accuracyStats.avg_confidence}%</span>
                        <span className="pred-acc-label">Avg Conf</span>
                      </div>
                    )}
                    <div className="pred-acc-item">
                      <span className="pred-acc-val">{accuracyStats.total_predictions ?? 0}</span>
                      <span className="pred-acc-label">Total</span>
                    </div>
                  </div>
                  {accuracyStats.total_predictions < 5 && (
                    <div className="pred-acc-note">Building track record — more predictions needed for reliable stats</div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── Quality Assessment ─────────────────────────────────────── */}
          {prediction.quality_assessment && (prediction.quality_assessment.issues?.length > 0 || prediction.quality_assessment.warnings?.length > 0) && (
            <div className="pred-section pred-qa-section">
              <div className="pred-section-title">Signal Quality Assessment</div>
              {(() => {
                const qa = prediction.quality_assessment;
                const qaGrade = qa.grade || 'C';
                const qaGradeColor = qaGrade === 'A' ? '#00ff88'
                  : qaGrade === 'B' ? '#66ffaa'
                  : qaGrade === 'C' ? '#ffcc00'
                  : '#ff6644';
                const chainQual = qa.causal_chain_quality || 'ADEQUATE';
                const chainColor = chainQual === 'ADEQUATE' ? '#66ffaa'
                  : chainQual === 'SPARSE' ? '#ffcc00'
                  : '#ff6644';
                return (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
                      <div style={{
                        background: `${qaGradeColor}18`,
                        border: `1px solid ${qaGradeColor}44`,
                        borderRadius: '6px',
                        padding: '4px 14px',
                        color: qaGradeColor,
                        fontFamily: 'monospace',
                        fontWeight: 800,
                        fontSize: '18px',
                        letterSpacing: '1px',
                      }}>
                        {qaGrade}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ color: '#ccc', fontSize: '12px' }}>{qa.summary}</div>
                        {qa.score != null && (
                          <div style={{ color: '#666', fontSize: '11px', marginTop: '2px', fontFamily: 'monospace' }}>
                            Confidence: {qa.score}% | Chain: <span style={{ color: chainColor }}>{chainQual}</span>
                            {qa.historical_accuracy_pct != null && (
                              <span> | Hist. accuracy: <span style={{ color: qa.historical_accuracy_pct >= 40 ? '#66ffaa' : '#ff6644' }}>{qa.historical_accuracy_pct}%</span></span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    {qa.issues?.length > 0 && (
                      <div style={{ marginBottom: '6px' }}>
                        {qa.issues.map((issue, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '6px',
                            fontSize: '11px',
                            color: '#cc6644',
                            marginBottom: '3px',
                          }}>
                            <span style={{ flexShrink: 0, marginTop: '1px' }}>✗</span>
                            <span>{issue}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {qa.warnings?.length > 0 && (
                      <div>
                        {qa.warnings.map((warn, i) => (
                          <div key={i} style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '6px',
                            fontSize: '11px',
                            color: '#aa8800',
                            marginBottom: '3px',
                          }}>
                            <span style={{ flexShrink: 0, marginTop: '1px' }}>⚠</span>
                            <span>{warn}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          )}

          {/* ── Memory Context ─────────────────────────────────────────── */}
          {reasoningData && (
            <div className="pred-section pred-memory-section">
              <div className="pred-section-title">Memory Context</div>
              {reasoningData.memory_applied && reasoningData.memory_summary
                ? (
                  <>
                    <p className="pred-memory-summary">{reasoningData.memory_summary}</p>
                    {reasoningData.confidence_adjustment !== 0 && reasoningData.confidence_adjustment != null && (
                      <div className="pred-memory-calibration">
                        Confidence calibration: {reasoningData.confidence_adjustment > 0 ? '+' : ''}{reasoningData.confidence_adjustment} pts based on past accuracy
                      </div>
                    )}
                    {reasoningData.adjustments_applied?.length > 0 && (
                      <div className="pred-memory-adjustments">
                        {reasoningData.adjustments_applied.map((adj, i) => (
                          <div key={i} className="pred-memory-adj-item">
                            {adj.type === 'confidence_calibration' && (
                              <span>Confidence: {adj.original}% → {adj.adjusted}% — {adj.reason}</span>
                            )}
                            {adj.type === 'low_effectiveness_cap' && (
                              <span className="pred-memory-adj-warn">Capped at {adj.adjusted}%: {adj.reason}</span>
                            )}
                            {adj.type === 'quality_cap' && (
                              <span className="pred-memory-adj-warn">Quality cap: {adj.original}% → {adj.adjusted}% ({adj.reason})</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ margin: 0, fontSize: '12px', color: '#555', fontStyle: 'italic' }}>
                    No historical memory yet — first prediction for this ticker/event type.
                  </p>
                )
              }
            </div>
          )}

          <div className="pred-disclaimer">⚠ Analytical intelligence only. Not financial advice.</div>

          {/* ── Prediction tracking footer ─────────────────────────────── */}
          {reasoningData && (
            <div className="pred-tracking-footer">
              {reasoningData.prediction_id && (
                <span className="pred-tracking-id">
                  ID: {reasoningData.prediction_id.substring(0, 8)}…
                </span>
              )}
              <span className="pred-tracking-divider">|</span>
              {reasoningData.signal_broadcast
                ? <span className="pred-tracking-broadcast">📡 Broadcast: Sent</span>
                : <span className="pred-tracking-inactive">📴 Broadcast: Not sent</span>
              }
              <span className="pred-tracking-divider">|</span>
              {reasoningData.memory_applied
                ? <span className="pred-tracking-memory">🧠 Memory: Applied</span>
                : <span className="pred-tracking-inactive">💭 Memory: Building…</span>
              }
              {reasoningData.processing_time_ms != null && (
                <>
                  <span className="pred-tracking-divider">|</span>
                  <span className="pred-tracking-timing">
                    ⚡ {Math.round(reasoningData.processing_time_ms)}ms
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PredictionCard;

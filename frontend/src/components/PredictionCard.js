import React from 'react';
import './PredictionCard.css';

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

  // Derive actionable recommendation (overridden by actual trade execution action if present)
  const recommendation = tradeExecution?.action
    || (prediction.direction === 'UP'   ? 'BUY'
      : prediction.direction === 'DOWN' ? 'SELL'
      : confidencePercent < 30         ? 'WAIT'
      :                                  'HOLD');
  const recColor = recommendation === 'BUY'  ? '#00ff88'
                 : recommendation === 'SELL' ? '#ff3366'
                 : recommendation === 'WAIT' ? '#ffaa00'
                 :                            '#888888';

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

              {/* Monte Carlo simulation */}
              {(prediction.monte_carlo_confidence || prediction.monte_carlo_price) && (
                <div className="pred-section pred-monte-carlo">
                  <div className="pred-section-title">Monte Carlo Simulation</div>

                  {prediction.monte_carlo_confidence && (() => {
                    const mc = prediction.monte_carlo_confidence;
                    const stabilityColor = mc.is_stable ? '#00ff88' : '#ff8800';
                    const convictionColor = mc.conviction_label === 'HIGH' ? '#00ff88'
                      : mc.conviction_label === 'MEDIUM' ? '#ffcc00' : '#ff8800';
                    return (
                      <div className="pred-mc-confidence">
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">Signal Stability</span>
                          <span className="pred-mc-value" style={{ color: stabilityColor }}>
                            {mc.direction_stability_pct}% — {mc.is_stable ? 'STABLE' : 'FRAGILE'}
                          </span>
                        </div>
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">Conviction</span>
                          <span className="pred-mc-value" style={{ color: convictionColor }}>
                            {mc.conviction_label} · {mc.dominant_direction.toUpperCase()}
                          </span>
                        </div>
                        <div className="pred-mc-row">
                          <span className="pred-mc-label">Confidence Range</span>
                          <span className="pred-mc-value" style={{ color: '#ccc' }}>
                            {mc.mean_confidence}% ± {mc.confidence_std}% across 1,000 scenarios
                          </span>
                        </div>
                        {!mc.is_stable && (
                          <div className="pred-mc-warning">
                            ⚠ Fragile signal — confidence reduced 25% due to MC instability
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {prediction.monte_carlo_price && (() => {
                    const mp = prediction.monte_carlo_price;
                    const changeColor = mp.expected_change_pct >= 0 ? '#00ff88' : '#ff3366';
                    return (
                      <div className="pred-mc-price">
                        <div className="pred-mc-price-header">
                          7-Day Price Range · {mp.current_price} → {' '}
                          <span style={{ color: changeColor }}>
                            {mp.expected_price_7d} ({mp.expected_change_pct > 0 ? '+' : ''}{mp.expected_change_pct}%)
                          </span>
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
          {tradeExecution && (
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
          )}

          {/* ── Memory Context (from reasoning synthesizer) ────────────────── */}
          {reasoningData?.memory_applied && (
            <div className="pred-section pred-accuracy-section">
              <div className="pred-section-title">Memory Context</div>
              {reasoningData.memory_summary && (
                <p style={{ margin: 0, fontSize: '12px', color: '#aaa', lineHeight: 1.6 }}>
                  {reasoningData.memory_summary}
                </p>
              )}
              {reasoningData.confidence_adjustment != null && reasoningData.confidence_adjustment !== 0 && (
                <p style={{ margin: '6px 0 0 0', fontSize: '11px', color: '#ffaa00' }}>
                  ⚖ Confidence adjusted {reasoningData.confidence_adjustment > 0 ? '+' : ''}{reasoningData.confidence_adjustment} pts based on historical accuracy
                </p>
              )}
              {reasoningData.signal_broadcast && (
                <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#3399ff' }}>
                  📡 Signal broadcast to subscribers
                </p>
              )}
            </div>
          )}

          {/* ── Accuracy Stats ─────────────────────────────────────────────── */}
          {accuracyStats && accuracyStats.total_predictions > 0 && (
            <div className="pred-section pred-accuracy-section">
              <div className="pred-section-title">
                Historical Accuracy — {prediction.ticker}
              </div>
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
                    {(accuracyStats.incorrect ?? 0)}
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
                <span className="pred-tracking-id">ID: {reasoningData.prediction_id}</span>
              )}
              {reasoningData.signal_broadcast
                ? <span className="pred-tracking-broadcast">📡 Broadcast</span>
                : <span style={{ fontSize: '10px', color: '#444' }}>No broadcast</span>
              }
              {reasoningData.memory_applied
                ? <span className="pred-tracking-memory">🧠 Memory applied</span>
                : <span style={{ fontSize: '10px', color: '#444' }}>No memory</span>
              }
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PredictionCard;

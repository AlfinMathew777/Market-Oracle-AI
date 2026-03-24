import React from 'react';
import './ChokepointReportModal.css';

// Static mapping: ASX ticker → primary operating state + label
const COMPANY_STATE_MAP = {
  'BHP.AX':  { state: 'WA',  name: 'BHP Group',           city: 'Perth' },
  'RIO.AX':  { state: 'WA',  name: 'Rio Tinto',            city: 'Perth' },
  'FMG.AX':  { state: 'WA',  name: 'Fortescue',            city: 'Perth' },
  'MIN.AX':  { state: 'WA',  name: 'Mineral Resources',    city: 'Perth' },
  'WDS.AX':  { state: 'WA',  name: 'Woodside Energy',      city: 'Perth' },
  'LYC.AX':  { state: 'WA',  name: 'Lynas Rare Earths',    city: 'Perth' },
  'PLS.AX':  { state: 'WA',  name: 'Pilbara Minerals',     city: 'Perth' },
  'WES.AX':  { state: 'WA',  name: 'Wesfarmers',           city: 'Perth' },
  'NST.AX':  { state: 'WA',  name: 'Northern Star',        city: 'Perth' },
  'STO.AX':  { state: 'NT',  name: 'Santos (Darwin LNG)',  city: 'Darwin' },
  'NCM.AX':  { state: 'QLD', name: 'Newcrest Mining',      city: 'Brisbane' },
  'WHC.AX':  { state: 'QLD', name: 'Whitehaven Coal',      city: 'Brisbane' },
  'NHC.AX':  { state: 'QLD', name: 'New Hope Corp',        city: 'Brisbane' },
  'CBA.AX':  { state: 'NSW', name: 'Commonwealth Bank',    city: 'Sydney' },
  'WBC.AX':  { state: 'NSW', name: 'Westpac',              city: 'Sydney' },
  'EVN.AX':  { state: 'NSW', name: 'Evolution Mining',     city: 'Sydney' },
  'WOW.AX':  { state: 'NSW', name: 'Woolworths',           city: 'Sydney' },
};

const STATE_META = {
  WA:  { name: 'Western Australia',   icon: '⛏',  industry: 'Iron ore · LNG · Gold' },
  QLD: { name: 'Queensland',          icon: '⚫',  industry: 'Coal · LNG · Copper' },
  NSW: { name: 'New South Wales',     icon: '🏦',  industry: 'Banking · Finance' },
  NT:  { name: 'Northern Territory',  icon: '⛽',  industry: 'Darwin LNG · Port' },
  SA:  { name: 'South Australia',     icon: '🔋',  industry: 'Copper · Critical minerals' },
  VIC: { name: 'Victoria',            icon: '🏙',  industry: 'Finance · Manufacturing' },
  TAS: { name: 'Tasmania',            icon: '🌿',  industry: 'Minor indirect' },
};

const DIR_COLOR = {
  UP: '#00ff88',
  DOWN: '#ff3366',
  BULLISH: '#00ff88',
  BEARISH: '#ff3366',
  NEUTRAL: '#aaaaaa',
  UNCERTAIN: '#aaaaaa',
};

function dirColor(direction) {
  if (!direction) return '#aaaaaa';
  const d = direction.toUpperCase();
  if (d.includes('BULL') || d === 'UP') return '#00ff88';
  if (d.includes('BEAR') || d === 'DOWN' || d.includes('DOWN')) return '#ff3366';
  return '#aaaaaa';
}

function dirLabel(direction) {
  if (!direction) return '—';
  const d = direction.toUpperCase();
  if (d.includes('BULL') || d === 'UP') return '▲ BULLISH';
  if (d.includes('BEAR') || d === 'DOWN' || d === 'DOWN_STRONG' || d === 'DOWN_SEVERE') return '▼ BEARISH';
  if (d === 'SLIGHT_DOWN' || d === 'BEARISH_COST' || d === 'BEARISH_CONSUMER') return '▼ MILD BEARISH';
  if (d === 'SLIGHT_UP') return '▲ MILD BULLISH';
  if (d === 'NEUTRAL_NEGATIVE') return '— NEUTRAL (neg)';
  return d;
}

function magColor(magnitude) {
  switch ((magnitude || '').toUpperCase()) {
    case 'VERY_HIGH': return '#ff2222';
    case 'HIGH':      return '#ff6600';
    case 'MEDIUM':    return '#ffaa00';
    case 'LOW':       return '#888888';
    default:          return '#666666';
  }
}

function StateBar({ label, score }) {
  const color = score >= 80 ? '#ff2222' : score >= 50 ? '#ff6600' : score >= 25 ? '#ffaa00' : '#444';
  return (
    <div className="cp-state-row">
      <span className="cp-state-label">{label}</span>
      <div className="cp-state-track">
        <div className="cp-state-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="cp-state-pct" style={{ color }}>{score}%</span>
    </div>
  );
}

export default function ChokepointReportModal({ result, onClose }) {
  if (!result) return null;

  const {
    chokepoint_name,
    chokepoint_details = {},
    sector_impacts = {},
    gdp_impact_estimate,
    impact = {},
  } = result || {};
  const {
    asx_predictions = [],
    affected_sectors = [],
    australian_regions = {},
    state_heatmap = {},
    export_value_at_risk_aud_bn,
    export_value_at_risk_display,
    export_breakdown_aud_m = {},
    asx_sector_breakdown = {},
    key_insight,
    monte_carlo_chokepoint = null,
  } = impact;

  // Use formatted display string if available, else format the number
  const exportsDisplay = export_value_at_risk_display
    || (export_value_at_risk_aud_bn != null ? `A$${export_value_at_risk_aud_bn}B` : '—');

  const topDirection = asx_predictions[0]?.direction || 'NEUTRAL';
  const topDirColor = dirColor(topDirection);

  return (
    <div className="cp-modal-overlay" onClick={onClose}>
      <div className="cp-modal" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="cp-modal-header">
          <div className="cp-modal-header-left">
            <span className="cp-modal-anchor">⚓</span>
            <div>
              <div className="cp-modal-title">{chokepoint_name}</div>
              <div className="cp-modal-subtitle">ASX Impact Simulation Report</div>
            </div>
          </div>
          <button className="cp-close-btn" onClick={onClose} title="Close">✕</button>
        </div>

        <div className="cp-modal-body">

          {/* Hero row */}
          <div className="cp-hero">
            <div className="cp-hero-item">
              <div className="cp-hero-label">ASX IMPACT</div>
              <div className="cp-hero-value" style={{ color: topDirColor }}>{dirLabel(topDirection)}</div>
            </div>
            <div className="cp-hero-item">
              <div className="cp-hero-label">EXPORTS AT RISK</div>
              <div className="cp-hero-value" style={{ color: '#ff8800' }}>{exportsDisplay}</div>
            </div>
            {chokepoint_details?.oil_flow_mbd && (
              <div className="cp-hero-item">
                <div className="cp-hero-label">OIL FLOW</div>
                <div className="cp-hero-value" style={{ color: '#ccc' }}>{chokepoint_details.oil_flow_mbd}mb/d</div>
              </div>
            )}
            {chokepoint_details?.pct_global_supply && (
              <div className="cp-hero-item">
                <div className="cp-hero-label">GLOBAL SUPPLY</div>
                <div className="cp-hero-value" style={{ color: '#ccc' }}>{chokepoint_details.pct_global_supply}%</div>
              </div>
            )}
          </div>

          {/* Key insight */}
          {key_insight && (
            <div className="cp-section cp-insight">
              <div className="cp-section-title">Key Insight</div>
              <p className="cp-insight-text">{key_insight}</p>
            </div>
          )}

          {/* Chokepoint details row */}
          <div className="cp-details-grid">
            {chokepoint_details?.current_threat && (
              <div className="cp-detail-item">
                <span className="cp-detail-label">CURRENT THREAT</span>
                <span className="cp-detail-value">{chokepoint_details.current_threat}</span>
              </div>
            )}
            {chokepoint_details?.alternative_route && (
              <div className="cp-detail-item">
                <span className="cp-detail-label">ALTERNATIVE ROUTE</span>
                <span className="cp-detail-value">{chokepoint_details.alternative_route}</span>
              </div>
            )}
            {chokepoint_details?.cargo_types?.length > 0 && (
              <div className="cp-detail-item">
                <span className="cp-detail-label">CARGO TYPES</span>
                <div className="cp-tag-row">
                  {chokepoint_details.cargo_types.map(c => (
                    <span key={c} className="cp-tag">{c.replace('_', ' ').toUpperCase()}</span>
                  ))}
                </div>
              </div>
            )}
            {chokepoint_details?.countries_controlling?.length > 0 && (
              <div className="cp-detail-item">
                <span className="cp-detail-label">CONTROLLING NATIONS</span>
                <span className="cp-detail-value">{chokepoint_details.countries_controlling.join(' · ')}</span>
              </div>
            )}
          </div>

          {/* GDP estimate */}
          {gdp_impact_estimate && (
            <div className="cp-gdp-banner">
              <span className="cp-gdp-label">GDP ESTIMATE</span>
              {gdp_impact_estimate}
            </div>
          )}

          {/* Two-column: ASX predictions + Sector impacts */}
          <div className="cp-two-col">

            {/* ASX Predictions */}
            <div className="cp-section">
              <div className="cp-section-title">ASX Stock Predictions</div>
              {asx_predictions.length === 0 ? (
                <div className="cp-empty">No direct ASX signals</div>
              ) : (
                <div className="cp-ticker-list">
                  {asx_predictions.map((p) => {
                    const orderLabel = p.impact_order === 'primary'   ? '1° DIRECT'
                                     : p.impact_order === 'secondary' ? '2° INDIRECT'
                                     :                                   '3° MACRO';
                    const orderColor = p.impact_order === 'primary'   ? '#ff8800'
                                     : p.impact_order === 'secondary' ? '#aaaaaa'
                                     :                                   '#555555';
                    const capPct = p.confidence_cap != null ? Math.round(p.confidence_cap * 100) : null;
                    return (
                      <div key={p.ticker} className="cp-ticker-row">
                        <div className="cp-ticker-left">
                          <span className="cp-ticker-name">{p.ticker}</span>
                          <span className="cp-ticker-dir" style={{ color: dirColor(p.direction) }}>
                            {dirLabel(p.direction)}
                          </span>
                          <span className="cp-order-badge" style={{ color: orderColor, borderColor: orderColor }}>
                            {orderLabel}
                          </span>
                        </div>
                        <div className="cp-ticker-right">
                          <div className="cp-conf-bar-wrap">
                            <div className="cp-conf-bar-fill" style={{ width: `${Math.round(p.confidence * 100)}%`, background: dirColor(p.direction) }} />
                            {capPct != null && (
                              <div className="cp-conf-cap-line" style={{ left: `${capPct}%` }} title={`Max cap: ${capPct}%`} />
                            )}
                          </div>
                          <span className="cp-conf-pct" style={{ color: dirColor(p.direction) }}>
                            {Math.round(p.confidence * 100)}%
                          </span>
                        </div>
                        {p.primary_reason && (
                          <div className="cp-ticker-reason">{p.primary_reason}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Sector Analysis — ASX sector-level breakdown */}
            <div className="cp-section">
              <div className="cp-section-title">Sector Analysis</div>
              {Object.keys(asx_sector_breakdown).length === 0 ? (
                <div className="cp-empty">No sector data</div>
              ) : (
                <div className="cp-sector-list">
                  {Object.entries(asx_sector_breakdown).map(([sector, data]) => {
                    const dc = dirColor(data.direction);
                    const mag = data.magnitude || 0;
                    return (
                      <div key={sector} className="cp-sector-item">
                        <div className="cp-sector-header">
                          <span className="cp-sector-name">{sector}</span>
                          <span className="cp-sector-dir" style={{ color: dc }}>
                            {dirLabel(data.direction)}
                          </span>
                          <span className="cp-sector-mag-num" style={{ color: dc }}>{mag}</span>
                        </div>
                        <div className="cp-sector-mag-bar-track">
                          <div
                            className="cp-sector-mag-bar-fill"
                            style={{ width: `${mag}%`, background: dc }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Regions + State heatmap */}
          <div className="cp-two-col">

            {/* Australian regions */}
            {Object.keys(australian_regions).length > 0 && (
              <div className="cp-section">
                <div className="cp-section-title">Australian Regions Affected</div>
                <div className="cp-region-list">
                  {Object.entries(australian_regions).map(([region, severity]) => {
                    const isHigh = severity.toUpperCase().includes('CRITICAL') || severity.toUpperCase().includes('HIGH');
                    const color = severity.toUpperCase().includes('CRITICAL') ? '#ff2222'
                      : severity.toUpperCase().includes('HIGH') ? '#ff6600'
                      : severity.toUpperCase().includes('MEDIUM') ? '#ffaa00'
                      : '#888';
                    return (
                      <div key={region} className="cp-region-row">
                        <span className="cp-region-dot" style={{ color }}>●</span>
                        <div className="cp-region-content">
                          <span className="cp-region-name">{region}</span>
                          <span className="cp-region-sev" style={{ color }}>{severity}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* State heatmap */}
            {Object.keys(state_heatmap).length > 0 && (
              <div className="cp-section">
                <div className="cp-section-title">State Impact Heatmap</div>
                <div className="cp-state-list">
                  {Object.entries(state_heatmap)
                    .sort(([, a], [, b]) => b - a)
                    .map(([state, score]) => (
                      <StateBar key={state} label={state} score={score} />
                    ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Companies by State ── */}
          {asx_predictions.length > 0 && (() => {
            // Group predictions by state
            const byState = {};
            asx_predictions.forEach(p => {
              const info = COMPANY_STATE_MAP[p.ticker];
              if (!info) return;
              if (!byState[info.state]) byState[info.state] = [];
              byState[info.state].push({ ...p, companyName: info.name, city: info.city });
            });

            // Only show states that have predictions
            const statesWithPreds = Object.entries(byState)
              .sort(([a], [b]) => {
                // Sort by state heatmap score descending
                return (state_heatmap[b] || 0) - (state_heatmap[a] || 0);
              });

            if (statesWithPreds.length === 0) return null;

            return (
              <div className="cp-section">
                <div className="cp-section-title">🗺 Australian Impact — Companies by State</div>
                <div className="cp-states-grid">
                  {statesWithPreds.map(([stateCode, companies]) => {
                    const meta = STATE_META[stateCode] || { name: stateCode, icon: '📍', industry: '' };
                    const stateScore = state_heatmap[stateCode] || 0;
                    const scoreColor = stateScore >= 80 ? '#ff2222'
                      : stateScore >= 50 ? '#ff6600'
                      : stateScore >= 25 ? '#ffaa00' : '#888';

                    const winners = companies.filter(c => c.direction === 'UP');
                    const losers  = companies.filter(c => c.direction === 'DOWN');

                    return (
                      <div key={stateCode} className="cp-state-card">
                        {/* State header */}
                        <div className="cp-state-card-header">
                          <span className="cp-state-icon">{meta.icon}</span>
                          <div className="cp-state-card-info">
                            <span className="cp-state-card-name">{stateCode} — {meta.name}</span>
                            <span className="cp-state-card-industry">{meta.industry}</span>
                          </div>
                          {stateScore > 0 && (
                            <span className="cp-state-card-score" style={{ color: scoreColor, borderColor: scoreColor }}>
                              {stateScore}
                            </span>
                          )}
                        </div>

                        {/* Winners */}
                        {winners.length > 0 && (
                          <div className="cp-state-company-group">
                            <span className="cp-state-group-label cp-winners-label">▲ WINNERS</span>
                            {winners.map(c => (
                              <div key={c.ticker} className="cp-state-company cp-state-winner">
                                <span className="cp-state-co-ticker">{c.ticker.replace('.AX', '')}</span>
                                <span className="cp-state-co-name">{c.companyName}</span>
                                <span className="cp-state-co-conf" style={{ color: '#00ff88' }}>
                                  {Math.round(c.confidence * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Losers */}
                        {losers.length > 0 && (
                          <div className="cp-state-company-group">
                            <span className="cp-state-group-label cp-losers-label">▼ LOSERS</span>
                            {losers.map(c => (
                              <div key={c.ticker} className="cp-state-company cp-state-loser">
                                <span className="cp-state-co-ticker">{c.ticker.replace('.AX', '')}</span>
                                <span className="cp-state-co-name">{c.companyName}</span>
                                <span className="cp-state-co-conf" style={{ color: '#ff3366' }}>
                                  {Math.round(c.confidence * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Monte Carlo disruption scenario */}
          {monte_carlo_chokepoint && (() => {
            const mc = monte_carlo_chokepoint;
            const fmtAud = (n) => {
              if (n >= 1_000_000_000) return `A$${(n / 1_000_000_000).toFixed(1)}B`;
              if (n >= 1_000_000)     return `A$${(n / 1_000_000).toFixed(0)}M`;
              return `A$${n.toLocaleString()}`;
            };
            const labelColor = mc.scenario_label.startsWith('CRITICAL') ? '#ff3366'
              : mc.scenario_label.startsWith('SEVERE')   ? '#ff8800'
              : mc.scenario_label.startsWith('MODERATE') ? '#ffcc00'
              : '#aaaaaa';
            return (
              <div className="cp-section">
                <div className="cp-section-title">Monte Carlo Scenario Distribution</div>
                <div className="cp-mc-label" style={{ color: labelColor }}>
                  {mc.scenario_label}
                </div>
                <div className="cp-mc-grid">
                  <div className="cp-mc-cell">
                    <div className="cp-mc-cell-label">Expected Impact</div>
                    <div className="cp-mc-cell-val" style={{ color: '#ff8800' }}>{fmtAud(mc.expected_exports_aud)}</div>
                  </div>
                  <div className="cp-mc-cell">
                    <div className="cp-mc-cell-label">Worst Case (95th %ile)</div>
                    <div className="cp-mc-cell-val" style={{ color: '#ff3366' }}>{fmtAud(mc.worst_case_exports_aud)}</div>
                  </div>
                  <div className="cp-mc-cell">
                    <div className="cp-mc-cell-label">Best Case (5th %ile)</div>
                    <div className="cp-mc-cell-val" style={{ color: '#00ff88' }}>{fmtAud(mc.best_case_exports_aud)}</div>
                  </div>
                  <div className="cp-mc-cell">
                    <div className="cp-mc-cell-label">Expected Duration</div>
                    <div className="cp-mc-cell-val" style={{ color: '#ccc' }}>{mc.expected_duration_days}d</div>
                  </div>
                </div>
                <div className="cp-mc-probs">
                  <span className="cp-mc-prob">P(&gt;A$1B): {mc.prob_exceeds_1b_pct}%</span>
                  <span className="cp-mc-prob">P(&gt;A$5B): {mc.prob_exceeds_5b_pct}%</span>
                  <span className="cp-mc-prob">P(&gt;A$10B): {mc.prob_exceeds_10b_pct}%</span>
                </div>
                <div className="cp-mc-note">10,000 scenario simulations · varying duration, severity, market reaction</div>
              </div>
            );
          })()}

          <div className="cp-disclaimer">⚠ Analytical intelligence only. Not financial advice.</div>
        </div>
      </div>
    </div>
  );
}

/**
 * MonteCarloEngine.jsx — Quantitative price-path visualisation
 *
 * DESIGN RULES (from .claude/rules/frontend.md):
 *  - Functional component + hooks only
 *  - Canvas-based — zero new npm packages
 *  - Dark theme: #05050f bg, rgba(51,102,255,0.3) blue, #ff8800 orange accent
 *  - fetch() directly, REACT_APP_BACKEND_URL, error/loading/empty states
 *  - ErrorBoundary wraps this component in App.js
 *
 * FALLBACK BEHAVIOUR (Phase 3, Step 3.3):
 *  If the quant API is unreachable, the component enters manual-input mode.
 *  The user can still run a client-side GBM simulation with their own params.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { fetchMonteCarlo } from '../../services/quantApi';
import './MonteCarloEngine.css';

// ── Client-side GBM (no backend needed) ──────────────────────────────────────
function runClientGBM(currentPrice, annualDrift, annualVol, horizonDays, nSims = 2000) {
  const TRADING_DAYS = 252;
  const dt = 1 / TRADING_DAYS;
  const driftTerm = (annualDrift - 0.5 * annualVol * annualVol) * dt;
  const volTerm = annualVol * Math.sqrt(dt);

  // Simple Box-Muller for reproducible normals
  const normals = [];
  for (let i = 0; i < nSims * horizonDays; i += 2) {
    const u1 = Math.random() || 1e-10;
    const u2 = Math.random() || 1e-10;
    const mag = Math.sqrt(-2 * Math.log(u1));
    normals.push(mag * Math.cos(2 * Math.PI * u2));
    normals.push(mag * Math.sin(2 * Math.PI * u2));
  }

  // Build price matrix: rows=sims, cols=days
  const paths = [];
  for (let s = 0; s < nSims; s++) {
    let price = currentPrice;
    const path = [];
    for (let d = 0; d < horizonDays; d++) {
      const z = normals[s * horizonDays + d] ?? 0;
      price = price * Math.exp(driftTerm + volTerm * z);
      path.push(price);
    }
    paths.push(path);
  }

  // Compute per-day percentiles
  const pctKeys = { p5: 5, p25: 25, mean: 50, p75: 75, p95: 95 };
  const percentilePaths = {};
  for (const [label, pct] of Object.entries(pctKeys)) {
    percentilePaths[label] = [];
    for (let d = 0; d < horizonDays; d++) {
      const col = paths.map(p => p[d]).sort((a, b) => a - b);
      const idx = Math.floor((pct / 100) * (col.length - 1));
      percentilePaths[label].push(+col[idx].toFixed(3));
    }
  }

  const finals = paths.map(p => p[horizonDays - 1]);
  finals.sort((a, b) => a - b);
  const probUp = finals.filter(f => f > currentPrice).length / finals.length;
  const probDown5 = finals.filter(f => f < currentPrice * 0.95).length / finals.length;
  const probUp5 = finals.filter(f => f > currentPrice * 1.05).length / finals.length;
  const probDown10 = finals.filter(f => f < currentPrice * 0.90).length / finals.length;
  const probUp10 = finals.filter(f => f > currentPrice * 1.10).length / finals.length;

  return {
    percentile_paths: percentilePaths,
    probabilities: {
      up: +probUp.toFixed(3),
      down: +(1 - probUp).toFixed(3),
      down_5pct: +probDown5.toFixed(3),
      up_5pct: +probUp5.toFixed(3),
      down_10pct: +probDown10.toFixed(3),
      up_10pct: +probUp10.toFixed(3),
    },
    final_price_p5: +finals[Math.floor(0.05 * finals.length)].toFixed(3),
    final_price_p95: +finals[Math.floor(0.95 * finals.length)].toFixed(3),
    final_price_mean: +(finals.reduce((s, v) => s + v, 0) / finals.length).toFixed(3),
  };
}

// ── Canvas renderer ───────────────────────────────────────────────────────────
function drawCanvas(canvas, simData, currentPrice) {
  if (!canvas || !simData) return;
  const ctx = canvas.getContext('2d');
  const { percentile_paths: pp } = simData;
  if (!pp || !pp.mean || pp.mean.length === 0) return;

  const W = canvas.width;
  const H = canvas.height;
  const PAD = { top: 20, right: 20, bottom: 36, left: 60 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  // Price range
  const allVals = [...(pp.p5 || []), ...(pp.p95 || []), currentPrice];
  const minP = Math.min(...allVals) * 0.995;
  const maxP = Math.max(...allVals) * 1.005;
  const n = pp.mean.length;

  const xOf = (i) => PAD.left + (i / (n - 1)) * plotW;
  const yOf = (p) => PAD.top + plotH - ((p - minP) / (maxP - minP)) * plotH;

  // Clear
  ctx.clearRect(0, 0, W, H);

  // ── Grid ──────────────────────────────────────────────────────────────────
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let tick = 0; tick <= 4; tick++) {
    const y = PAD.top + (tick / 4) * plotH;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + plotW, y);
    ctx.stroke();
    const price = maxP - (tick / 4) * (maxP - minP);
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';
    ctx.fillText(`$${price.toFixed(2)}`, PAD.left - 6, y + 4);
  }

  // X-axis ticks (every ~7 days)
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(255,255,255,0.35)';
  const xStep = Math.max(1, Math.floor(n / 5));
  for (let i = 0; i < n; i += xStep) {
    const x = xOf(i);
    ctx.fillText(`d${i + 1}`, x, PAD.top + plotH + 18);
    ctx.beginPath(); ctx.moveTo(x, PAD.top + plotH); ctx.lineTo(x, PAD.top + plotH + 4);
    ctx.strokeStyle = 'rgba(255,255,255,0.15)'; ctx.stroke();
  }

  // ── Filled bands ─────────────────────────────────────────────────────────
  function fillBand(upper, lower, color) {
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(upper[0]));
    upper.forEach((v, i) => ctx.lineTo(xOf(i), yOf(v)));
    for (let i = lower.length - 1; i >= 0; i--) ctx.lineTo(xOf(i), yOf(lower[i]));
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }

  // p5–p95 outer band (wide, red-tinted)
  if (pp.p5 && pp.p95) {
    fillBand(pp.p95, pp.p5, 'rgba(255,100,100,0.12)');
  }
  // p25–p75 inner band (blue-tinted)
  if (pp.p25 && pp.p75) {
    fillBand(pp.p75, pp.p25, 'rgba(51,153,255,0.18)');
  }

  // ── Percentile lines ──────────────────────────────────────────────────────
  const LINES = [
    { key: 'p5',   color: 'rgba(255,100,100,0.7)', dash: [4, 4], w: 1   },
    { key: 'p25',  color: 'rgba(100,160,255,0.7)', dash: [3, 3], w: 1   },
    { key: 'mean', color: '#ff8800',                dash: [],     w: 2   },
    { key: 'p75',  color: 'rgba(100,160,255,0.7)', dash: [3, 3], w: 1   },
    { key: 'p95',  color: 'rgba(255,100,100,0.7)', dash: [4, 4], w: 1   },
  ];

  for (const { key, color, dash, w } of LINES) {
    const path = pp[key];
    if (!path || path.length === 0) continue;
    ctx.beginPath();
    ctx.setLineDash(dash);
    ctx.lineWidth = w;
    ctx.strokeStyle = color;
    ctx.moveTo(xOf(0), yOf(path[0]));
    path.forEach((v, i) => ctx.lineTo(xOf(i), yOf(v)));
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // ── Current price line ────────────────────────────────────────────────────
  const cpY = yOf(currentPrice);
  ctx.beginPath();
  ctx.setLineDash([6, 4]);
  ctx.lineWidth = 1;
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.moveTo(PAD.left, cpY);
  ctx.lineTo(PAD.left + plotW, cpY);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.font = '10px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(`Now $${currentPrice.toFixed(2)}`, PAD.left + 4, cpY - 4);
}

// ── ASX tickers users can pick from ──────────────────────────────────────────
const ASX_TICKERS = [
  'BHP.AX', 'RIO.AX', 'FMG.AX', 'CBA.AX', 'ANZ.AX',
  'NAB.AX', 'WBC.AX', 'WDS.AX', 'STO.AX', 'NCM.AX',
];

// ── Component ─────────────────────────────────────────────────────────────────
export default function MonteCarloEngine({ ticker: tickerProp, initialParams, onSimComplete }) {
  // ── Local state ──────────────────────────────────────────────────────────
  const [ticker, setTicker] = useState(tickerProp || 'BHP.AX');
  const [horizonDays, setHorizonDays] = useState(30);
  const [nSims, setNSims] = useState(5000);
  const [drift, setDrift] = useState(0.06);
  const [vol, setVol] = useState(0.28);
  const [currentPrice, setCurrentPrice] = useState(50.0);

  const [apiStatus, setApiStatus] = useState('loading'); // 'loading' | 'ok' | 'offline'
  const [simData, setSimData] = useState(null);          // API or client-side result
  const [apiMeta, setApiMeta] = useState(null);          // full API response metadata
  const [isRunning, setIsRunning] = useState(false);

  const canvasRef = useRef(null);

  // ── Fetch from API on ticker change ──────────────────────────────────────
  const fetchFromApi = useCallback(async (t) => {
    setApiStatus('loading');
    setSimData(null);
    setApiMeta(null);
    const res = await fetchMonteCarlo(t, horizonDays, Math.min(nSims, 5000));
    if (res.status === 'success' && res.data) {
      const d = res.data;
      setApiStatus('ok');
      setSimData(d);
      setApiMeta(d);
      // Seed local controls with API params
      if (d.current_price)  setCurrentPrice(d.current_price);
      if (d.annual_drift !== undefined)  setDrift(+d.annual_drift.toFixed(4));
      if (d.annual_vol !== undefined)    setVol(+d.annual_vol.toFixed(4));
      if (d.horizon_days)   setHorizonDays(d.horizon_days);
      if (onSimComplete) onSimComplete(d);
    } else {
      setApiStatus('offline');
    }
  }, []); // intentionally empty — fetchFromApi is stable via useCallback

  useEffect(() => { fetchFromApi(ticker); }, [ticker]); // intentionally omits fetchFromApi (stable ref)

  // Seed from prop if provided (e.g. App.js passes quant data from a previous simulation)
  useEffect(() => {
    if (!initialParams) return;
    if (initialParams.current_price) setCurrentPrice(initialParams.current_price);
    if (initialParams.annual_drift !== undefined) setDrift(+initialParams.annual_drift.toFixed(4));
    if (initialParams.annual_vol !== undefined) setVol(+initialParams.annual_vol.toFixed(4));
  }, [initialParams]);

  // ── Canvas draw on data change ────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Set physical pixel size for sharp rendering
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    drawCanvas(canvas, simData, currentPrice);
  }, [simData, currentPrice]);

  // ── Client-side re-run ────────────────────────────────────────────────────
  const handleRunClientSim = () => {
    setIsRunning(true);
    // Defer to next tick so the button state updates before heavy computation
    setTimeout(() => {
      try {
        const result = runClientGBM(currentPrice, drift, vol, horizonDays, nSims);
        setSimData(result);
        if (onSimComplete) onSimComplete(result);
      } catch (_) {}
      setIsRunning(false);
    }, 10);
  };

  // ── Probability display helpers ───────────────────────────────────────────
  const probs = simData?.probabilities || {};
  const probUp = probs.up ?? 0.5;
  const probDown = probs.down ?? 0.5;

  const pct = (v) => `${(v * 100).toFixed(1)}%`;

  // ── Vol regime from API or derived from vol param ─────────────────────────
  const volRegime = apiMeta?.vol_regime || (
    vol < 0.15 ? 'LOW' : vol < 0.25 ? 'NORMAL' : vol < 0.40 ? 'HIGH' : 'EXTREME'
  );

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="mc-page">

      {/* Header */}
      <div className="mc-header">
        <h2>Monte Carlo Simulation Engine</h2>
        <p className="mc-header-sub">Quantitative GBM price-path analysis · ASX tickers</p>
      </div>

      {/* Top row: controls + canvas */}
      <div className="mc-top-row">

        {/* Controls */}
        <div className="mc-controls">
          <p className="mc-controls-title">Simulation Parameters</p>

          {/* Ticker */}
          <div className="mc-field">
            <label className="mc-label">Ticker</label>
            <select
              className="mc-input"
              value={ticker}
              onChange={e => setTicker(e.target.value)}
            >
              {ASX_TICKERS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {/* Horizon */}
          <div className="mc-field">
            <label className="mc-label">Horizon (trading days)</label>
            <input
              type="number" min="5" max="90" step="5"
              className="mc-input"
              value={horizonDays}
              onChange={e => setHorizonDays(Math.max(5, Math.min(90, +e.target.value)))}
            />
          </div>

          {/* Simulations */}
          <div className="mc-field">
            <label className="mc-label">Simulations</label>
            <input
              type="number" min="500" max="10000" step="500"
              className="mc-input"
              value={nSims}
              onChange={e => setNSims(Math.max(500, Math.min(10000, +e.target.value)))}
            />
            <span className="mc-input-hint">More sims = smoother paths, slower run</span>
          </div>

          {/* Drift */}
          <div className="mc-field">
            <label className="mc-label">Annual Drift (μ)</label>
            <input
              type="number" min="-1" max="1" step="0.01"
              className="mc-input"
              value={drift}
              onChange={e => setDrift(+e.target.value)}
            />
            <span className="mc-input-hint">
              {apiStatus === 'ok' ? 'Calibrated from 1-year price history' : 'Enter manually'}
            </span>
          </div>

          {/* Volatility */}
          <div className="mc-field">
            <label className="mc-label">Annual Volatility (σ)</label>
            <input
              type="number" min="0.01" max="2" step="0.01"
              className="mc-input"
              value={vol}
              onChange={e => setVol(+e.target.value)}
            />
          </div>

          {/* Current Price */}
          <div className="mc-field">
            <label className="mc-label">Current Price (AUD)</label>
            <input
              type="number" min="0.01" step="0.01"
              className="mc-input"
              value={currentPrice}
              onChange={e => setCurrentPrice(+e.target.value)}
            />
          </div>

          <button
            className="mc-run-btn"
            onClick={handleRunClientSim}
            disabled={isRunning || apiStatus === 'loading'}
          >
            {isRunning ? 'Running…' : 'Run Simulation'}
          </button>

          {/* API status */}
          <div className={`mc-api-badge ${apiStatus}`}>
            <span className="mc-dot" />
            {apiStatus === 'loading' && 'Fetching live params…'}
            {apiStatus === 'ok'      && `Live data · ${ticker}`}
            {apiStatus === 'offline' && 'Quant API offline — manual mode'}
          </div>
        </div>

        {/* Canvas panel */}
        <div className="mc-canvas-panel">
          <p className="mc-canvas-title">
            Price Paths — {horizonDays}-Day Horizon &nbsp;·&nbsp;
            {nSims.toLocaleString()} Simulations
          </p>

          {apiStatus === 'loading' && !simData ? (
            <div className="mc-empty">
              <div className="mc-spinner" />
              <span>Loading live market parameters…</span>
            </div>
          ) : (
            <canvas ref={canvasRef} className="mc-canvas" />
          )}

          {/* Legend */}
          <div className="mc-legend">
            {[
              { color: 'rgba(255,100,100,0.7)', label: 'P5 / P95 (outer band)' },
              { color: 'rgba(100,160,255,0.7)', label: 'P25 / P75 (inner band)' },
              { color: '#ff8800',               label: 'Median path' },
              { color: 'rgba(255,255,255,0.3)', label: 'Current price' },
            ].map(({ color, label }) => (
              <div key={label} className="mc-legend-item">
                <div className="mc-legend-line" style={{ background: color }} />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Results — only shown when sim data is available */}
      {simData && (
        <>
          <div className="mc-results-row">

            {/* Probability card */}
            <div className="mc-card">
              <p className="mc-card-title">Probability Breakdown</p>
              {[
                { label: 'Up (end)',   val: probUp,            color: '#00cc66' },
                { label: 'Down (end)', val: probDown,          color: '#ff4444' },
                { label: 'Up >5%',    val: probs.up_5pct   ?? 0, color: '#00cc66' },
                { label: 'Down >5%',  val: probs.down_5pct ?? 0, color: '#ff8800' },
                { label: 'Up >10%',   val: probs.up_10pct  ?? 0, color: '#00cc66' },
                { label: 'Down >10%', val: probs.down_10pct?? 0, color: '#ff4444' },
              ].map(({ label, val, color }) => (
                <div key={label} className="mc-prob-row">
                  <span className="mc-prob-label">{label}</span>
                  <div className="mc-prob-bar-bg">
                    <div
                      className="mc-prob-bar-fill"
                      style={{ width: `${(val * 100).toFixed(1)}%`, background: color }}
                    />
                  </div>
                  <span className="mc-prob-val">{pct(val)}</span>
                </div>
              ))}
            </div>

            {/* Risk metrics card */}
            <div className="mc-card">
              <p className="mc-card-title">Risk Metrics (1-day)</p>
              {[
                { label: 'VaR 95%',    val: apiMeta?.var_95  != null ? `${(apiMeta.var_95 * 100).toFixed(2)}%`  : '—' },
                { label: 'CVaR 95%',   val: apiMeta?.cvar_95 != null ? `${(apiMeta.cvar_95 * 100).toFixed(2)}%` : '—' },
                { label: 'Price P5',   val: simData.final_price_p5  != null ? `$${simData.final_price_p5}`  : '—' },
                { label: 'Price Mean', val: simData.final_price_mean != null ? `$${simData.final_price_mean}` : '—' },
                { label: 'Price P95',  val: simData.final_price_p95 != null ? `$${simData.final_price_p95}` : '—' },
              ].map(({ label, val }) => (
                <div key={label} className="mc-risk-row">
                  <span className="mc-risk-label">{label}</span>
                  <span className="mc-risk-val">{val}</span>
                </div>
              ))}
            </div>

            {/* Vol regime + factor exposures card */}
            <div className="mc-card">
              <p className="mc-card-title">Volatility &amp; Factors</p>

              <div style={{ marginBottom: 10 }}>
                <span className={`mc-regime-badge ${volRegime}`}>{volRegime} VOL REGIME</span>
              </div>

              {apiMeta?.factor_exposures?.length > 0 ? (
                apiMeta.factor_exposures.map((f, i) => (
                  <div key={i} className="mc-factor-row">
                    <span>{f.factor}</span>
                    <span className="mc-factor-val">
                      {typeof f.exposure === 'number'
                        ? f.factor.includes('Momentum') ? `${f.exposure > 0 ? '+' : ''}${f.exposure}%` : f.exposure.toFixed(2)
                        : f.exposure}
                    </span>
                  </div>
                ))
              ) : (
                <div className="mc-factor-row">
                  <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>
                    Factor data available when API is online
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Prediction sources */}
          <div className="mc-sources">
            <p className="mc-sources-title">Prediction Sources</p>
            {[
              { name: 'Quant Engine', pct: 55, color: '#ff8800' },
              { name: 'Agent Swarm', pct: 35, color: '#3399ff' },
              { name: 'OSINT',       pct: 10, color: '#9966ff' },
            ].map(({ name, pct: p, color }) => (
              <div key={name} className="mc-source-row">
                <span className="mc-source-name">{name}</span>
                <div className="mc-source-bar-bg">
                  <div
                    className="mc-source-bar-fill"
                    style={{ width: `${p}%`, background: color, opacity: 0.7 }}
                  />
                </div>
                <span className="mc-source-pct">{p}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

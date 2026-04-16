import React, { useState, useEffect, useCallback } from "react";
import "./AccuracyDashboard.css";

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────────────────────

function hitRateColor(rate) {
  if (rate == null) return "#666";
  if (rate >= 0.6) return "#00ff88";
  if (rate >= 0.5) return "#d29922";
  return "#ff3366";
}

function dirIcon(dir) {
  if (!dir) return "—";
  const d = dir.toUpperCase();
  if (d === "UP" || d === "BULLISH" || d === "BUY") return "▲";
  if (d === "DOWN" || d === "BEARISH" || d === "SELL") return "▼";
  return "—";
}

function dirColor(dir) {
  if (!dir) return "#888";
  const d = dir.toUpperCase();
  if (d === "UP" || d === "BULLISH" || d === "BUY") return "#00ff88";
  if (d === "DOWN" || d === "BEARISH" || d === "SELL") return "#ff3366";
  return "#aaa";
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleDateString("en-AU", {
      day: "2-digit",
      month: "short",
      timeZone: "Australia/Sydney",
    });
  } catch {
    return isoStr.slice(0, 10);
  }
}

function formatConf(c) {
  if (c == null) return "—";
  return `${Math.round(c * 100)}%`;
}

function formatPct(n) {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function formatPrice(p) {
  if (p == null) return "—";
  return `$${Number(p).toFixed(2)}`;
}

function outcomeLabel(row) {
  if (row.prediction_correct === 1 || row.prediction_correct === true)
    return { text: "CORRECT", cls: "ad-outcome-correct" };
  if (row.prediction_correct === 0 || row.prediction_correct === false)
    return { text: "INCORRECT", cls: "ad-outcome-incorrect" };
  return { text: "NEUTRAL", cls: "ad-outcome-neutral" };
}

/** Group resolved history by ISO date and compute daily accuracy for sparkline */
function computeTrend(history) {
  const byDay = {};
  history.forEach((r) => {
    if (r.prediction_correct === null || r.prediction_correct === undefined)
      return;
    const day = (r.resolved_at || r.predicted_at || "").slice(0, 10);
    if (!day) return;
    if (!byDay[day]) byDay[day] = { correct: 0, total: 0 };
    byDay[day].total++;
    if (r.prediction_correct === 1 || r.prediction_correct === true)
      byDay[day].correct++;
  });
  return Object.entries(byDay)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { correct, total }]) => ({
      date,
      rate: total > 0 ? correct / total : 0,
      total,
    }));
}

/** Render a minimal SVG sparkline for accuracy trend */
function TrendSparkline({ points }) {
  if (!points || points.length < 2) {
    return (
      <div className="ad-trend-empty">
        Insufficient data for trend — needs at least 2 days of resolved
        predictions
      </div>
    );
  }

  const W = 600;
  const H = 80;
  const pad = { top: 8, bottom: 24, left: 32, right: 12 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;

  const xs = points.map(
    (_, i) => pad.left + (i / (points.length - 1)) * innerW,
  );
  const ys = points.map((p) => pad.top + (1 - p.rate) * innerH);

  const polyline = xs.map((x, i) => `${x},${ys[i]}`).join(" ");

  // Area fill path
  const areaPath = [
    `M ${xs[0]} ${pad.top + innerH}`,
    ...xs.map((x, i) => `L ${x} ${ys[i]}`),
    `L ${xs[xs.length - 1]} ${pad.top + innerH}`,
    "Z",
  ].join(" ");

  // 50% reference line
  const midY = pad.top + 0.5 * innerH;

  // Tick dates — show up to 6 evenly spaced
  const tickCount = Math.min(6, points.length);
  const tickStep = Math.floor((points.length - 1) / (tickCount - 1)) || 1;
  const ticks = [];
  for (let i = 0; i < points.length; i += tickStep) {
    ticks.push({ x: xs[i], label: points[i].date.slice(5) }); // MM-DD
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="ad-trend-svg"
      aria-label="Accuracy trend sparkline"
    >
      {/* 50% reference line */}
      <line
        x1={pad.left}
        y1={midY}
        x2={W - pad.right}
        y2={midY}
        stroke="rgba(255,255,255,0.08)"
        strokeDasharray="4 4"
        strokeWidth="1"
      />
      {/* 50% label */}
      <text
        x={pad.left - 4}
        y={midY + 4}
        fill="rgba(255,255,255,0.25)"
        fontSize="9"
        textAnchor="end"
        fontFamily="monospace"
      >
        50%
      </text>

      {/* Area fill */}
      <defs>
        <linearGradient id="ad-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3366ff" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#3366ff" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#ad-area-grad)" />

      {/* Line */}
      <polyline
        points={polyline}
        fill="none"
        stroke="#3366ff"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data dots */}
      {xs.map((x, i) => (
        <circle
          key={i}
          cx={x}
          cy={ys[i]}
          r="3"
          fill={points[i].rate >= 0.5 ? "#00ff88" : "#ff3366"}
          stroke="#05050f"
          strokeWidth="1.5"
        >
          <title>
            {points[i].date}: {Math.round(points[i].rate * 100)}% (
            {points[i].total} signals)
          </title>
        </circle>
      ))}

      {/* X-axis date ticks */}
      {ticks.map(({ x, label }, i) => (
        <text
          key={i}
          x={x}
          y={H - 4}
          fill="rgba(255,255,255,0.3)"
          fontSize="8"
          textAnchor="middle"
          fontFamily="monospace"
        >
          {label}
        </text>
      ))}
    </svg>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function AccuracyDashboard() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchData = useCallback(
    async (attempt = 1) => {
      try {
        setLoading(true);
        setError(null);

        const [summaryRes, histRes] = await Promise.all([
          fetch(`${BACKEND_URL}/api/metrics/validation-summary?days=${days}`),
          fetch(
            `${BACKEND_URL}/api/predictions/history?days=${days}&limit=100`,
          ),
        ]);

        if (!summaryRes.ok)
          throw new Error(`Summary endpoint error ${summaryRes.status}`);
        if (!histRes.ok)
          throw new Error(`History endpoint error ${histRes.status}`);

        const summaryData = await summaryRes.json();
        const histData = await histRes.json();

        setSummary(summaryData);

        if (histData.status === "success") {
          const resolved = (histData.data || []).filter(
            (r) =>
              r.prediction_correct !== null &&
              r.prediction_correct !== undefined,
          );
          setHistory(resolved);
        }

        setLastUpdated(new Date());
      } catch (err) {
        if (attempt < 3) {
          setTimeout(() => fetchData(attempt + 1), attempt * 8000);
          setError(`Backend waking up… retrying (${attempt}/3)`);
        } else {
          setError(
            "Failed to load accuracy data. Backend may be offline — try refreshing.",
          );
        }
      } finally {
        setLoading(false);
      }
    },
    [days],
  );

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading && !summary) {
    return (
      <div className="ad-loading">
        <div className="ad-spinner" />
        <p>Loading accuracy data…</p>
      </div>
    );
  }

  // ── Derived values ───────────────────────────────────────────────────────────
  const hitRate = summary?.hit_rate ?? null;
  const hitRatePct = hitRate != null ? Math.round(hitRate * 100) : null;
  const totalValidated = summary?.total_validated ?? 0;
  const correct = summary?.correct ?? 0;
  const incorrect = summary?.incorrect ?? 0;
  const neutral = summary?.neutral ?? 0;
  const confBands = summary?.by_confidence_band ?? {};
  const byDir = summary?.by_direction ?? {};
  const trendPoints = computeTrend(history);
  const recentTable = history.slice(0, 20);

  const bandOrder = ["55-65%", "65-75%", "75-85%", "85%+"];

  return (
    <div className="ad-page">
      {/* ── 1. HEADER ── */}
      <div className="ad-header-section">
        <div className="ad-header-row">
          <div>
            <div className="ad-header-title">
              <span className="ad-logo-dot">◆</span>
              SYSTEM ACCURACY
            </div>
            <div className="ad-header-subtitle">
              24-hour prediction validation · quality signals only (&gt;5%
              confidence)
            </div>
          </div>
          <div className="ad-header-controls">
            <select
              className="ad-days-select"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            {lastUpdated && (
              <div className="ad-last-updated">
                Updated{" "}
                {lastUpdated.toLocaleTimeString("en-AU", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="ad-error">
            {error}
            {!error.includes("retrying") && (
              <button className="ad-retry-btn" onClick={() => fetchData()}>
                Retry
              </button>
            )}
          </div>
        )}

        {/* ── 2. KEY METRICS ROW ── */}
        <div className="ad-stat-grid">
          <div className="ad-stat-card">
            <div className="ad-stat-value">{totalValidated}</div>
            <div className="ad-stat-label">Total Predictions</div>
            <div className="ad-stat-sub">{neutral} neutral abstained</div>
          </div>

          <div className="ad-stat-card">
            <div
              className="ad-stat-value"
              style={{
                color: hitRate != null ? hitRateColor(hitRate) : "#666",
              }}
            >
              {hitRatePct != null ? `${hitRatePct}%` : "—"}
            </div>
            <div className="ad-stat-label">Hit Rate</div>
            <div
              className="ad-stat-sub"
              style={{ color: hitRateColor(hitRate) }}
            >
              {hitRatePct == null
                ? "no data"
                : hitRatePct >= 60
                  ? "above target"
                  : hitRatePct >= 50
                    ? "near target"
                    : "below target"}
            </div>
          </div>

          <div className="ad-stat-card">
            <div className="ad-stat-value" style={{ color: "#00ff88" }}>
              {correct}
            </div>
            <div className="ad-stat-label">Correct</div>
            <div className="ad-stat-sub">
              {totalValidated > 0
                ? `${Math.round((correct / totalValidated) * 100)}% of validated`
                : "—"}
            </div>
          </div>

          <div className="ad-stat-card">
            <div className="ad-stat-value" style={{ color: "#ff3366" }}>
              {incorrect}
            </div>
            <div className="ad-stat-label">Incorrect</div>
            <div className="ad-stat-sub">
              {totalValidated > 0
                ? `${Math.round((incorrect / totalValidated) * 100)}% of validated`
                : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. CONFIDENCE BAND CHART ── */}
      <div className="ad-section">
        <div className="ad-section-title">HIT RATE BY CONFIDENCE BAND</div>
        <div className="ad-section-subtitle">
          Higher confidence signals should predict better outcomes — validates
          our threshold logic
        </div>
        <div className="ad-bands">
          {bandOrder.map((band) => {
            const d = confBands[band];
            const rate = d?.hit_rate ?? null;
            const total = d?.total ?? 0;
            const pct = rate != null ? Math.round(rate * 100) : null;
            return (
              <div key={band} className="ad-band-row">
                <div className="ad-band-label">{band}</div>
                <div className="ad-band-bar-wrap">
                  <div
                    className="ad-band-bar"
                    style={{
                      width: pct != null ? `${pct}%` : "0%",
                      background:
                        pct == null
                          ? "rgba(255,255,255,0.08)"
                          : pct >= 60
                            ? "linear-gradient(90deg, #00ff88, #00cc66)"
                            : pct >= 50
                              ? "linear-gradient(90deg, #d29922, #b07d10)"
                              : "linear-gradient(90deg, #ff3366, #cc1040)",
                    }}
                  />
                  {/* 50% marker */}
                  <div className="ad-band-fifty-mark" />
                </div>
                <div
                  className="ad-band-pct"
                  style={{ color: pct != null ? hitRateColor(rate) : "#444" }}
                >
                  {pct != null ? `${pct}%` : "—"}
                </div>
                <div className="ad-band-count">
                  {total > 0 ? `${total} signals` : "no data"}
                </div>
              </div>
            );
          })}
        </div>
        <div className="ad-band-axis-label">
          <span>0%</span>
          <span>50% target</span>
          <span>100%</span>
        </div>
      </div>

      {/* ── 4. DIRECTION BREAKDOWN ── */}
      <div className="ad-section">
        <div className="ad-section-title">SIGNAL DIRECTION BREAKDOWN</div>
        <div className="ad-dir-grid">
          {["BUY", "SELL"].map((dir) => {
            const d = byDir[dir];
            const rate = d?.hit_rate ?? null;
            const total = d?.total ?? 0;
            const pct = rate != null ? Math.round(rate * 100) : null;
            const color = dir === "BUY" ? "#00ff88" : "#ff3366";
            return (
              <div
                key={dir}
                className="ad-dir-card"
                style={{
                  borderColor:
                    pct != null ? `${color}44` : "rgba(255,255,255,0.07)",
                }}
              >
                <div className="ad-dir-icon" style={{ color }}>
                  {dir === "BUY" ? "▲" : "▼"}
                </div>
                <div className="ad-dir-name" style={{ color }}>
                  {dir} SIGNALS
                </div>
                <div
                  className="ad-dir-rate"
                  style={{ color: pct != null ? hitRateColor(rate) : "#444" }}
                >
                  {pct != null ? `${pct}%` : "—"}
                </div>
                <div className="ad-dir-sub">hit rate</div>
                <div className="ad-dir-total">
                  {total > 0 ? `${total} predictions` : "no data yet"}
                </div>
                {d && (
                  <div className="ad-dir-breakdown">
                    <span style={{ color: "#00ff88" }}>
                      {d.correct ?? 0} correct
                    </span>
                    <span className="ad-dir-sep">·</span>
                    <span style={{ color: "#ff3366" }}>
                      {total - (d.correct ?? 0)} incorrect
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 5. RECENT VALIDATIONS TABLE ── */}
      <div className="ad-section">
        <div className="ad-section-title">RECENT VALIDATED PREDICTIONS</div>
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticker</th>
                <th>Direction</th>
                <th>Confidence</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>Change</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {recentTable.length === 0 && (
                <tr>
                  <td colSpan={8} className="ad-table-empty">
                    No validated predictions in this period yet. Predictions
                    resolve 24 hours after they are generated.
                  </td>
                </tr>
              )}
              {recentTable.map((row, i) => {
                const outcome = outcomeLabel(row);
                const changePct = row.actual_price_change_pct;
                return (
                  <tr
                    key={row.id || i}
                    className={`ad-row ad-row-${outcome.text.toLowerCase()}`}
                  >
                    <td className="ad-cell-date">
                      {formatDate(row.predicted_at)}
                    </td>
                    <td className="ad-cell-ticker">{row.ticker}</td>
                    <td>
                      <span
                        style={{
                          color: dirColor(row.predicted_direction),
                          fontFamily: "monospace",
                          fontSize: "12px",
                        }}
                      >
                        {dirIcon(row.predicted_direction)}{" "}
                        {(row.predicted_direction || "").toUpperCase()}
                      </span>
                    </td>
                    <td className="ad-cell-mono">
                      {formatConf(row.confidence)}
                    </td>
                    <td className="ad-cell-mono">
                      {formatPrice(row.bhp_price_at_prediction)}
                    </td>
                    <td className="ad-cell-mono">
                      {formatPrice(row.actual_close_price)}
                    </td>
                    <td
                      className="ad-cell-mono"
                      style={{
                        color:
                          changePct == null
                            ? "#555"
                            : changePct > 0
                              ? "#00ff88"
                              : changePct < 0
                                ? "#ff3366"
                                : "#888",
                      }}
                    >
                      {formatPct(changePct)}
                    </td>
                    <td>
                      <span className={`ad-outcome ${outcome.cls}`}>
                        {outcome.text}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── 6. TREND CHART ── */}
      <div className="ad-section">
        <div className="ad-section-title">ACCURACY TREND</div>
        <div className="ad-section-subtitle">
          Daily hit rate over the selected period · dots show individual day
          accuracy
        </div>
        <TrendSparkline points={trendPoints} />
      </div>

      {/* ── DISCLAIMER ── */}
      <div className="ad-disclaimer">
        <strong>Research only.</strong> Past accuracy does not predict future
        results. Market Oracle AI signals are experimental and for informational
        purposes only. Not financial advice.
      </div>
    </div>
  );
}

import React, { useState, useEffect } from "react";
import "./TrackRecord.css";

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

function TrackRecord() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const [tickerFilter, setTickerFilter] = useState("");
  const [showExcluded, setShowExcluded] = useState(false);

  useEffect(() => {
    fetchData();
    // Refresh every 5 minutes
    const interval = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [tickerFilter]);

  const fetchData = async (attempt = 1) => {
    try {
      setLoading(true);
      setError(null);
      const params = tickerFilter
        ? `?ticker=${encodeURIComponent(tickerFilter)}&days=365`
        : "?days=365";
      const statsParams = tickerFilter
        ? `?ticker=${encodeURIComponent(tickerFilter)}&days=365`
        : "?days=365";
      const [histRes, statsRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/predictions/history${params}`),
        fetch(`${BACKEND_URL}/api/predictions/accuracy${statsParams}`),
      ]);
      if (!histRes.ok || !statsRes.ok)
        throw new Error(`Server error ${histRes.status}`);
      const histData = await histRes.json();
      const statsData = await statsRes.json();
      if (histData.status === "success") setHistory(histData.data || []);
      if (statsData.status === "success") setStats(statsData.data);
    } catch (err) {
      if (attempt < 3) {
        // Render free tier cold starts take ~15-30s; retry automatically
        setTimeout(() => fetchData(attempt + 1), attempt * 8000);
        setError(`Backend waking up… retrying (${attempt}/3)`);
      } else {
        setError(
          "Failed to load prediction history. Backend may be offline — try refreshing.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const dirIcon = (dir) => {
    if (!dir) return "—";
    const d = dir.toUpperCase();
    if (d === "UP" || d === "BULLISH") return "▲";
    if (d === "DOWN" || d === "BEARISH") return "▼";
    return "—";
  };

  const dirColor = (dir) => {
    if (!dir) return "#888";
    const d = dir.toUpperCase();
    if (d === "UP" || d === "BULLISH") return "#00ff88";
    if (d === "DOWN" || d === "BEARISH") return "#ff3366";
    return "#aaa";
  };

  const formatDate = (isoStr) => {
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
  };

  const formatConf = (c) => {
    if (c == null) return "—";
    return `${Math.round(c * 100)}%`;
  };

  const rowClass = (row) => {
    if (row.excluded_from_stats) return "tr-row tr-excluded";
    if (row.prediction_correct === null || row.prediction_correct === undefined)
      return "tr-row tr-pending";
    return row.prediction_correct ? "tr-row tr-correct" : "tr-row tr-wrong";
  };

  const resultBadge = (row) => {
    if (row.excluded_from_stats) {
      return (
        <span
          className="tr-badge tr-badge-excluded"
          title={row.exclusion_reason || "Low confidence — excluded from stats"}
        >
          —
        </span>
      );
    }
    if (
      row.prediction_correct === null ||
      row.prediction_correct === undefined
    ) {
      return <span className="tr-badge tr-badge-pending">⏳</span>;
    }
    return row.prediction_correct ? (
      <span className="tr-badge tr-badge-correct">✅</span>
    ) : (
      <span className="tr-badge tr-badge-wrong">❌</span>
    );
  };

  if (loading && !stats) {
    return (
      <div className="tr-loading">
        <div className="tr-spinner" />
        <p>Loading track record…</p>
      </div>
    );
  }

  const resolved = stats?.resolved_predictions || 0;
  const correct = stats?.correct_predictions || 0;
  const total = stats?.total_predictions || 0;
  const accPct = stats?.direction_accuracy_pct || 0;
  const avgConf = stats?.avg_confidence || 0;
  const streak = stats?.streak || {};
  const confBands = stats?.accuracy_by_confidence_band || {};
  const excludedCount = stats?.excluded_count || 0;

  return (
    <div className="tr-page">
      {/* ── Section A: Headline Stats ── */}
      <div className="tr-header-section">
        <div className="tr-header-title">
          <span className="tr-logo-dot">◆</span>
          MARKET ORACLE AI — PUBLIC TRACK RECORD
          <span className="tr-subtitle">
            Updated daily after ASX close · Quality predictions only
          </span>
        </div>

        <div className="tr-stat-grid">
          <div className="tr-stat-card">
            <div
              className="tr-stat-value"
              style={{ color: accPct >= 50 ? "#00ff88" : "#ff3366" }}
            >
              {resolved > 0 ? `${accPct}%` : "—"}
            </div>
            <div className="tr-stat-label">Accuracy</div>
            <div className="tr-stat-sub">
              {correct}/{resolved} resolved
            </div>
          </div>
          <div className="tr-stat-card">
            <div className="tr-stat-value">{total}</div>
            <div className="tr-stat-label">Total Predictions</div>
            <div className="tr-stat-sub">{total - resolved} pending</div>
          </div>
          <div className="tr-stat-card">
            <div
              className="tr-stat-value"
              style={{
                color:
                  streak.streak_direction === "correct" ? "#00ff88" : "#ff3366",
              }}
            >
              {streak.current_streak || 0}
            </div>
            <div className="tr-stat-label">Current Streak</div>
            <div className="tr-stat-sub">
              {streak.streak_direction || "—"} · best: {streak.best_streak || 0}
            </div>
          </div>
          <div className="tr-stat-card">
            <div className="tr-stat-value">
              {avgConf > 0 ? `${avgConf.toFixed(0)}%` : "—"}
            </div>
            <div className="tr-stat-label">Avg Confidence</div>
            <div className="tr-stat-sub">system-scored</div>
          </div>
        </div>

        {excludedCount > 0 && (
          <div className="tr-exclusion-note">
            ℹ {excludedCount} low-confidence (&lt;5%) predictions excluded from
            stats
          </div>
        )}
      </div>

      {/* ── Section B: History Table ── */}
      <div className="tr-section">
        <div className="tr-section-header">
          <span className="tr-section-title">PREDICTION HISTORY</span>
          <div className="tr-filter">
            {excludedCount > 0 && (
              <button
                className="tr-toggle-excluded"
                onClick={() => setShowExcluded((v) => !v)}
              >
                {showExcluded
                  ? `Hide ${excludedCount} low-conf`
                  : `Show ${excludedCount} low-conf`}
              </button>
            )}
            <input
              className="tr-filter-input"
              placeholder="Filter by ticker…"
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
            />
            {tickerFilter && (
              <button
                className="tr-filter-clear"
                onClick={() => setTickerFilter("")}
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="tr-error">
            {error}
            {!error.includes("retrying") && (
              <button
                onClick={() => fetchData()}
                style={{
                  marginLeft: "12px",
                  padding: "2px 10px",
                  cursor: "pointer",
                  fontSize: "12px",
                }}
              >
                Retry
              </button>
            )}
          </div>
        )}

        <div className="tr-table-wrap">
          <table className="tr-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticker</th>
                <th>Direction</th>
                <th>Conf</th>
                <th>Trend</th>
                <th>Actual</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 && (
                <tr>
                  <td colSpan={7} className="tr-empty">
                    No predictions recorded yet. Run a simulation to start the
                    clock.
                  </td>
                </tr>
              )}
              {history
                .filter((row) => showExcluded || !row.excluded_from_stats)
                .map((row, i) => (
                  <React.Fragment key={row.id || i}>
                    <tr
                      className={rowClass(row)}
                      onClick={() =>
                        setExpandedRow(expandedRow === i ? null : i)
                      }
                    >
                      <td>{formatDate(row.predicted_at)}</td>
                      <td className="tr-ticker">{row.ticker}</td>
                      <td>
                        <span
                          style={{ color: dirColor(row.predicted_direction) }}
                        >
                          {dirIcon(row.predicted_direction)}{" "}
                          {(row.predicted_direction || "").toUpperCase()}
                        </span>
                      </td>
                      <td>{formatConf(row.confidence)}</td>
                      <td>
                        <span
                          className={`tr-trend-badge tr-trend-${(row.trend_label || "NEUTRAL").toLowerCase().replace("_", "-")}`}
                        >
                          {row.trend_label || "—"}
                        </span>
                      </td>
                      <td>
                        {row.actual_price_change_pct != null ? (
                          <span
                            style={{
                              color:
                                row.actual_price_change_pct >= 0
                                  ? "#00ff88"
                                  : "#ff3366",
                            }}
                          >
                            {row.actual_price_change_pct >= 0 ? "+" : ""}
                            {row.actual_price_change_pct.toFixed(2)}%
                          </span>
                        ) : (
                          <span className="tr-pending-text">pending</span>
                        )}
                      </td>
                      <td>{resultBadge(row)}</td>
                    </tr>
                    {expandedRow === i && (
                      <tr className="tr-expand-row">
                        <td colSpan={7}>
                          <div className="tr-expand-body">
                            {row.primary_reason && (
                              <div className="tr-expand-field">
                                <span className="tr-expand-label">
                                  Primary reason:
                                </span>
                                <span>{row.primary_reason}</span>
                              </div>
                            )}
                            {row.actual_driver && (
                              <div className="tr-expand-field">
                                <span className="tr-expand-label">
                                  Actual driver:
                                </span>
                                <span>{row.actual_driver}</span>
                              </div>
                            )}
                            {row.lesson && (
                              <div className="tr-expand-field tr-lesson">
                                <span className="tr-expand-label">
                                  Lesson learned:
                                </span>
                                <span>{row.lesson}</span>
                              </div>
                            )}
                            <div className="tr-expand-meta">
                              {row.agent_bullish != null && (
                                <span>
                                  Votes: {row.agent_bullish}B /{" "}
                                  {row.agent_bearish}Be / {row.agent_neutral}N
                                </span>
                              )}
                              {row.resolved_at && (
                                <span>
                                  Resolved: {formatDate(row.resolved_at)}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Section C: Accuracy By Confidence Band ── */}
      <div className="tr-section">
        <div className="tr-section-title">ACCURACY BY CONFIDENCE BAND</div>
        <div className="tr-bands">
          {Object.entries(confBands).map(([band, data]) => {
            const pct = data.accuracy_pct || 0;
            const barW = Math.round(pct);
            return (
              <div key={band} className="tr-band-row">
                <div className="tr-band-label">{band}</div>
                <div className="tr-band-bar-wrap">
                  <div
                    className="tr-band-bar-fill"
                    style={{
                      width: `${barW}%`,
                      background:
                        pct >= 60
                          ? "#00ff88"
                          : pct >= 40
                            ? "#ffaa00"
                            : "#ff3366",
                    }}
                  />
                </div>
                <div className="tr-band-stat">
                  {data.total > 0
                    ? `${data.correct}/${data.total} = ${pct}%`
                    : "no data yet"}
                </div>
              </div>
            );
          })}
          {Object.keys(confBands).length === 0 && (
            <div className="tr-empty">
              No resolved predictions yet to show confidence calibration.
            </div>
          )}
        </div>
      </div>

      {/* ── Section D: Disclaimer ── */}
      <div className="tr-disclaimer">
        <div className="tr-disclaimer-header">⚠ IMPORTANT NOTICE</div>
        <p>
          Market Oracle AI provides directional predictions for{" "}
          <strong>educational and research purposes only</strong>. This is{" "}
          <strong>NOT financial advice</strong>. These predictions should{" "}
          <strong>NOT</strong> be used as the basis for any investment decision.
        </p>
        <p>
          Past prediction accuracy does not guarantee future results. All
          investment decisions should be made in consultation with a licensed
          financial adviser. Market Oracle AI does not hold an Australian
          Financial Services Licence (AFSL).
        </p>
      </div>
    </div>
  );
}

export default TrackRecord;

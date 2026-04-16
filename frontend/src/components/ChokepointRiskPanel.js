import React, { useState, useEffect } from "react";

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

const ChokepointRiskPanel = ({ onSimulateChokepoint }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [simulating, setSimulating] = useState(null); // chokepoint_id currently running

  useEffect(() => {
    fetchChokepoints();
    const interval = setInterval(fetchChokepoints, 300000); // 5 min refresh
    return () => clearInterval(interval);
  }, []);

  const fetchChokepoints = async () => {
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/data/chokepoints?enriched=false`,
      );
      const json = await res.json();
      if (json.status === "success") setData(json.data);
    } catch (err) {
      console.error("Chokepoint fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulate = async (cpId) => {
    setSimulating(cpId);
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/simulate/chokepoint?chokepoint_id=${cpId}&duration_days=7`,
        { method: "POST" },
      );
      const result = await res.json();
      if (result.status === "completed") {
        if (onSimulateChokepoint) onSimulateChokepoint(result);
      }
    } catch (err) {
      console.error("Chokepoint simulation error:", err);
    } finally {
      setSimulating(null);
    }
  };

  if (loading) {
    return (
      <div style={styles.panel}>
        <div style={styles.header}>
          <span style={styles.title}>⚓ CHOKEPOINT RISK</span>
        </div>
        <div style={styles.loading}>Loading chokepoint data...</div>
      </div>
    );
  }

  if (!data) return null;

  const sorted = Object.values(data.chokepoints).sort(
    (a, b) => b.risk_score - a.risk_score,
  );
  const supplyAtRisk = data.global_supply_at_risk_pct || 0;
  const riskColor =
    supplyAtRisk > 25 ? "#ff2222" : supplyAtRisk > 10 ? "#ff8800" : "#44ff88";

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.title}>⚓ CHOKEPOINT RISK</span>
        <span
          style={{
            ...styles.supplyBadge,
            color: riskColor,
            borderColor: riskColor,
          }}
        >
          {supplyAtRisk}% SUPPLY AT RISK
        </span>
      </div>

      <div style={styles.meta}>
        <span style={{ color: "#ff4444" }}>
          ● {data.critical_count} CRITICAL
        </span>
        <span style={{ color: "#888", margin: "0 6px" }}>·</span>
        <span style={{ color: "#ff8800" }}>● {data.high_risk_count} HIGH</span>
        <span style={{ color: "#555", fontSize: "10px", marginLeft: "auto" }}>
          {data.updated_at
            ? new Date(data.updated_at).toLocaleTimeString()
            : ""}
        </span>
      </div>

      {/* Risk bars */}
      <div style={styles.list}>
        {sorted.map((cp) => (
          <div key={cp.chokepoint_id} style={styles.row}>
            {/* Row header */}
            <div
              style={styles.rowHeader}
              onClick={() =>
                setExpanded(
                  expanded === cp.chokepoint_id ? null : cp.chokepoint_id,
                )
              }
            >
              <div style={styles.rowLeft}>
                <span
                  style={{
                    color: cp.color,
                    fontSize: "10px",
                    marginRight: "5px",
                  }}
                >
                  ●
                </span>
                <span style={styles.cpName}>{cp.name}</span>
              </div>
              <div style={styles.rowRight}>
                <span style={styles.flowText}>{cp.oil_flow_mbd}mb/d</span>
                <span style={{ ...styles.pctText, color: cp.color }}>
                  {cp.pct_global_supply}%
                </span>
              </div>
            </div>

            {/* Progress bar */}
            <div style={styles.barTrack}>
              <div
                style={{
                  ...styles.barFill,
                  width: `${cp.risk_score}%`,
                  background: cp.color,
                }}
              />
            </div>

            {/* Threat line */}
            <div style={{ ...styles.threatText, color: cp.color }}>
              {cp.current_threat.length > 65
                ? cp.current_threat.substring(0, 65) + "…"
                : cp.current_threat}
            </div>

            {/* Expanded detail */}
            {expanded === cp.chokepoint_id && (
              <div style={styles.expanded}>
                <div style={styles.expandRow}>
                  <span style={styles.expandLabel}>ASX IMPACT</span>
                  <span style={styles.expandValue}>{cp.asx_impact}</span>
                </div>
                <div style={styles.expandRow}>
                  <span style={styles.expandLabel}>ALTERNATIVE</span>
                  <span style={styles.expandValue}>{cp.alternative_route}</span>
                </div>
                {cp.asx_tickers_affected &&
                  cp.asx_tickers_affected.length > 0 && (
                    <div style={styles.tickerRow}>
                      {cp.asx_tickers_affected.map((t) => (
                        <span key={t} style={styles.tickerBadge}>
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                <button
                  style={{
                    ...styles.simBtn,
                    opacity: simulating === cp.chokepoint_id ? 0.6 : 1,
                    cursor:
                      simulating === cp.chokepoint_id
                        ? "not-allowed"
                        : "pointer",
                  }}
                  onClick={() =>
                    simulating ? null : handleSimulate(cp.chokepoint_id)
                  }
                  disabled={!!simulating}
                >
                  {simulating === cp.chokepoint_id
                    ? "⟳ Simulating..."
                    : "▶ Simulate ASX Impact"}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={styles.footer}>
        Click any chokepoint to expand · Click Simulate for ASX predictions
      </div>
    </div>
  );
};

const styles = {
  panel: {
    background: "rgba(10, 12, 20, 0.95)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "8px",
    padding: "12px",
    marginTop: "8px",
    fontFamily: "monospace",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "6px",
  },
  title: {
    color: "#e0e0e0",
    fontSize: "11px",
    fontWeight: "bold",
    letterSpacing: "1px",
  },
  supplyBadge: {
    fontSize: "10px",
    fontWeight: "bold",
    border: "1px solid",
    borderRadius: "4px",
    padding: "2px 6px",
  },
  meta: {
    display: "flex",
    alignItems: "center",
    fontSize: "10px",
    marginBottom: "8px",
    color: "#888",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  row: {
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    paddingBottom: "6px",
    cursor: "pointer",
  },
  rowHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "3px",
  },
  rowLeft: {
    display: "flex",
    alignItems: "center",
  },
  cpName: {
    color: "#d0d0d0",
    fontSize: "11px",
  },
  rowRight: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  flowText: {
    color: "#666",
    fontSize: "10px",
  },
  pctText: {
    fontSize: "10px",
    fontWeight: "bold",
  },
  barTrack: {
    background: "rgba(255,255,255,0.06)",
    borderRadius: "3px",
    height: "5px",
    marginBottom: "3px",
  },
  barFill: {
    height: "5px",
    borderRadius: "3px",
    transition: "width 0.6s ease",
  },
  threatText: {
    fontSize: "9px",
    lineHeight: "1.3",
  },
  expanded: {
    marginTop: "6px",
    padding: "8px",
    background: "rgba(255,255,255,0.03)",
    borderRadius: "4px",
    borderLeft: "2px solid rgba(255,136,0,0.4)",
  },
  expandRow: {
    display: "flex",
    flexDirection: "column",
    marginBottom: "5px",
  },
  expandLabel: {
    color: "#666",
    fontSize: "9px",
    letterSpacing: "1px",
    marginBottom: "2px",
  },
  expandValue: {
    color: "#bbb",
    fontSize: "10px",
    lineHeight: "1.4",
  },
  tickerRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "4px",
    margin: "6px 0",
  },
  tickerBadge: {
    background: "rgba(255,255,255,0.08)",
    color: "#aaa",
    fontSize: "9px",
    padding: "2px 5px",
    borderRadius: "3px",
    border: "1px solid rgba(255,255,255,0.1)",
  },
  simBtn: {
    marginTop: "6px",
    width: "100%",
    background: "rgba(255,136,0,0.15)",
    border: "1px solid rgba(255,136,0,0.4)",
    color: "#ff8800",
    fontSize: "10px",
    padding: "5px",
    borderRadius: "4px",
    cursor: "pointer",
    fontFamily: "monospace",
    letterSpacing: "0.5px",
  },
  loading: {
    color: "#555",
    fontSize: "11px",
    textAlign: "center",
    padding: "12px 0",
  },
  footer: {
    marginTop: "8px",
    color: "#444",
    fontSize: "9px",
    textAlign: "center",
  },
};

export default ChokepointRiskPanel;

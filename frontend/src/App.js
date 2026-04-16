import React, { useState, useEffect, useRef } from "react";
import Globe from "./components/Globe";
import AustraliaMap from "./components/AustraliaMap";
import EventSidebar from "./components/EventSidebar";
import PredictionCard from "./components/PredictionCard";
import ChokepointReportModal from "./components/ChokepointReportModal";
import TickerStrip from "./components/TickerStrip";
import SimulationProgress from "./components/SimulationProgress";
import SectorHeatmap from "./components/SectorHeatmap";
import PredictionHistory from "./components/PredictionHistory";
import MacroContext from "./components/MacroContext";
import AustralianEconomicContext from "./components/AustralianEconomicContext";
import ChokepointRiskPanel from "./components/ChokepointRiskPanel";
import TrackRecord from "./components/TrackRecord";
import AccuracyDashboard from "./components/AccuracyDashboard";
import ErrorBoundary from "./components/ErrorBoundary";
import MonteCarloEngine from "./components/MonteCarlo/MonteCarloEngine";
import { Globe as GlobeIcon, Map as MapIcon } from "lucide-react";
import "./App.css";

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API_KEY = process.env.REACT_APP_API_KEY || "";
console.log("[app] BACKEND_URL =", BACKEND_URL);

// Fetch wrapper — adds timeout and injects X-API-Key on every backend request
async function directFetch(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = {
    ...(options.headers || {}),
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
  };
  try {
    const resp = await window.fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timer);
    return resp;
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError")
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    throw err;
  }
}

function App() {
  const [acledEvents, setAcledEvents] = useState([]);
  const [asxPrices, setAsxPrices] = useState([]);
  const [portHedlandData, setPortHedlandData] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationStartTime, setSimulationStartTime] = useState(null);
  const [simMinimized, setSimMinimized] = useState(false);
  const [predictionOpen, setPredictionOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [error, setError] = useState(null);
  const [correlationArc, setCorrelationArc] = useState({
    show: false,
    eventLat: 0,
    eventLng: 0,
  });
  const [viewMode, setViewMode] = useState("australia"); // 'australia' or 'global'
  const [activeTab, setActiveTab] = useState("main"); // 'main' or 'track-record'
  const [chokepointReport, setChokepointReport] = useState(null); // full chokepoint sim result
  const [lastSimScores, setLastSimScores] = useState({}); // cpId → {topPredictions, generatedAt}

  // ── New feature state ──────────────────────────────────────────────────────
  const [tradeExecution, setTradeExecution] = useState(null);
  const [accuracyStats, setAccuracyStats] = useState(null);
  const [livePrice, setLivePrice] = useState(null);
  const [reasoningData, setReasoningData] = useState(null);

  const arcTimeoutRef = useRef(null);
  const isSimulatingRef = useRef(false); // ref-based guard — immune to React closure staleness
  const abortPollRef = useRef(false); // set true to cancel current poll loop
  const wsRef = useRef(null); // WebSocket reference for live prices

  // Safety net: whenever prediction arrives, force-open card and clear simulation overlay
  useEffect(() => {
    if (prediction) {
      setPredictionOpen(true);
      setIsSimulating(false);
      setSimulationStartTime(null);
      isSimulatingRef.current = false;
    }
  }, [prediction]);

  // Sync activeTab with URL hash
  useEffect(() => {
    const handleHashChange = () => {
      const h = window.location.hash;
      if (h === "#/track-record") setActiveTab("track-record");
      else if (h === "#/simulation") setActiveTab("simulation");
      else if (h === "#/accuracy") setActiveTab("accuracy");
      else setActiveTab("main");
    };
    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigateTo = (tab) => {
    if (tab === "track-record") window.location.hash = "#/track-record";
    else if (tab === "simulation") window.location.hash = "#/simulation";
    else window.location.hash = "#/";
    setActiveTab(tab);
  };

  // Cleanup arc timeout on unmount
  useEffect(() => {
    return () => {
      if (arcTimeoutRef.current) {
        clearTimeout(arcTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    fetchInitialData();
    // Refresh events every 6 hours (ACLED cache TTL is 1 hour on backend)
    const refreshInterval = setInterval(fetchInitialData, 6 * 60 * 60 * 1000);
    return () => clearInterval(refreshInterval);
  }, []);

  const fetchInitialData = async () => {
    // All sources fire in parallel — one failure does not block the others
    await Promise.allSettled([
      fetch(`${BACKEND_URL}/api/data/acled`)
        .then((r) => r.json())
        .then((acledData) => {
          if (acledData.status === "success") {
            setAcledEvents(acledData.data.features);
            localStorage.setItem(
              "acled_events",
              JSON.stringify(acledData.data.features),
            );
          }
        })
        .catch((err) => {
          console.error("ACLED fetch failed:", err);
          const cached = localStorage.getItem("acled_events");
          if (cached)
            try {
              setAcledEvents(JSON.parse(cached));
            } catch (_) {}
        }),

      fetch(`${BACKEND_URL}/api/data/asx-prices`)
        .then((r) => r.json())
        .then((asxData) => {
          if (asxData.status === "success") {
            setAsxPrices(asxData.data);
            localStorage.setItem("asx_prices", JSON.stringify(asxData.data));
          }
        })
        .catch((err) => {
          console.error("ASX prices fetch failed:", err);
          const cached = localStorage.getItem("asx_prices");
          if (cached)
            try {
              setAsxPrices(JSON.parse(cached));
            } catch (_) {}
        }),

      fetch(`${BACKEND_URL}/api/data/port-hedland`)
        .then((r) => r.json())
        .then((portData) => {
          if (portData.status === "success") setPortHedlandData(portData.data);
        })
        .catch((err) => {
          console.error("Port Hedland fetch failed:", err);
        }),
    ]);
  };

  // Close WebSocket when component unmounts or ticker changes
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Fetch trade execution + accuracy stats, open WebSocket for live prices
  const enrichPrediction = async (pred) => {
    const ticker = pred.ticker;
    const currentPrice =
      pred.monte_carlo_price?.current_price || pred.ticker_price || 0;
    const directionMap = { UP: "BULLISH", DOWN: "BEARISH", NEUTRAL: "NEUTRAL" };
    const recMap = { UP: "BUY", DOWN: "SELL", NEUTRAL: "WAIT" };

    // 1. Trade execution — only attempt when signal is actionable.
    // Use the backend-filtered recommendation (pred.recommendation) NOT raw direction.
    // Grade F/D signals must not generate a trade plan.
    const filteredRec =
      pred.recommendation ||
      pred.signal_recommendation ||
      recMap[pred.direction] ||
      "WAIT";
    const isActionable =
      pred.is_actionable !== false &&
      filteredRec !== "HOLD" &&
      filteredRec !== "WAIT" &&
      filteredRec !== "AVOID" &&
      !["D", "F"].includes(pred.signal_grade);
    if (currentPrice > 0 && isActionable) {
      try {
        const res = await directFetch(
          `${BACKEND_URL}/api/trade/generate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              prediction_id: pred.simulation_id || "sim",
              stock_ticker: ticker,
              current_price: currentPrice,
              direction: directionMap[pred.direction] || "NEUTRAL",
              recommendation: filteredRec,
              confidence_score: Math.round((pred.confidence || 0) * 100),
              risk_tolerance: "moderate",
            }),
          },
          10000,
        );
        if (res.ok) {
          const te = await res.json();
          setTradeExecution(te);
          console.log("[enrich] trade execution received", te.action);
        }
      } catch (e) {
        console.warn("[enrich] trade execution failed:", e.message);
      }
    } else if (!isActionable) {
      console.log(
        "[enrich] trade execution skipped — signal not actionable (grade:",
        pred.signal_grade,
        "rec:",
        filteredRec,
        ")",
      );
    }

    // 2. Accuracy stats
    try {
      const res = await directFetch(
        `${BACKEND_URL}/api/accuracy/summary?ticker=${encodeURIComponent(ticker)}&days=90`,
        {},
        8000,
      );
      if (res.ok) {
        const stats = await res.json();
        setAccuracyStats(stats);
        console.log(
          "[enrich] accuracy stats received",
          stats.accuracy_pct,
          "%",
        );
      }
    } catch (e) {
      console.warn("[enrich] accuracy stats failed:", e.message);
    }

    // 3. Reasoning synthesizer — memory context, prediction storage, signal broadcast
    try {
      const agentVotes = {
        bullish: pred.agent_consensus?.up ?? 0,
        bearish: pred.agent_consensus?.down ?? 0,
        neutral: pred.agent_consensus?.neutral ?? 0,
      };
      const eventDesc =
        selectedEvent?.properties?.description ||
        selectedEvent?.properties?.notes ||
        selectedEvent?.properties?.event_type ||
        "";
      const res = await directFetch(
        `${BACKEND_URL}/api/reasoning/synthesize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            stock_ticker: ticker,
            news_headline: eventDesc,
            news_summary: eventDesc,
            market_signals: { current_price: currentPrice },
            agent_votes: agentVotes,
            generate_trade_execution: false, // trade already fetched separately
            use_memory: true,
            broadcast_signal: true,
            risk_tolerance: "moderate",
          }),
        },
        20000,
      );
      if (res.ok) {
        const rd = await res.json();
        setReasoningData({
          memory_applied: rd.memory_applied,
          memory_summary: rd.memory_summary,
          confidence_adjustment: rd.confidence_adjustment,
          signal_broadcast: rd.signal_broadcast,
          prediction_id: rd.prediction_id,
          processing_time_ms: rd.processing_time_ms,
          adjustments_applied: rd.prediction?.adjustments_applied || [],
          reasoning_quality_issues:
            rd.prediction?.reasoning_quality_issues || [],
        });
        console.log(
          "[enrich] reasoning data received, memory_applied=",
          rd.memory_applied,
        );
      }
    } catch (e) {
      console.warn("[enrich] reasoning synthesizer failed:", e.message);
    }

    // 3. WebSocket live prices
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    try {
      const wsUrl =
        BACKEND_URL.replace(/^http/, "ws") +
        `/api/stream/prices?tickers=${encodeURIComponent(ticker)}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "price" && msg.ticker === ticker) {
            setLivePrice({
              price: msg.price,
              change_pct: msg.change_pct,
              ts: msg.timestamp,
            });
          }
        } catch (_) {}
      };
      ws.onerror = () => console.warn("[ws] price stream error for", ticker);
      ws.onclose = () => console.log("[ws] price stream closed for", ticker);
    } catch (e) {
      console.warn("[enrich] WebSocket failed:", e.message);
    }
  };

  const handleEventClick = async (event) => {
    // Ref-based guard: immune to React closure staleness — updated synchronously
    if (isSimulatingRef.current) {
      console.log("[sim] ignored — already simulating");
      return;
    }
    isSimulatingRef.current = true;
    abortPollRef.current = false;

    // Validate event structure
    const coords = event?.geometry?.coordinates;
    const props = event?.properties;
    if (!coords || coords.length < 2 || !props) {
      console.error("[sim] malformed event object", event);
      isSimulatingRef.current = false;
      setError("Could not start simulation — event data is missing.");
      return;
    }

    const requestBody = {
      event_id: props.id || props.event_id_cnty || null,
      event_description:
        props.description || props.notes || props.event_type || "Unknown event",
      event_type: props.event_type || "Unknown",
      lat: coords[1],
      lon: coords[0],
      country: props.country || "Unknown",
      fatalities: props.fatalities ?? 0,
      date: props.date || props.event_date || null,
    };

    console.log("[sim] requestBody:", requestBody);

    setSelectedEvent(event);
    setPrediction(null);
    setError(null);
    setIsSimulating(true);
    setSimulationStartTime(Date.now());
    setSimMinimized(false);

    try {
      // ── Step 1: POST — returns simulation_id immediately ──
      // 60s timeout: Railway cold-start after inactivity can take 20-45s.
      // The POST handler itself returns in <1s once the instance is warm.
      let startResp;
      try {
        startResp = await directFetch(
          `${BACKEND_URL}/api/simulate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
          },
          60000,
        );
        console.log("[sim] POST status:", startResp.status);
      } catch (fetchErr) {
        console.warn("[sim] POST failed, retrying in 3s:", fetchErr.message);
        await new Promise((r) => setTimeout(r, 3000));
        startResp = await directFetch(
          `${BACKEND_URL}/api/simulate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
          },
          60000,
        );
        console.log("[sim] POST retry status:", startResp.status);
      }

      if (!startResp.ok) {
        let detail = `Simulation failed to start (HTTP ${startResp.status})`;
        try {
          detail = (await startResp.json()).detail || detail;
        } catch (_) {}
        console.error("[sim] POST error:", detail);
        throw new Error(detail);
      }

      const startData = await startResp.json();
      const { simulation_id } = startData;
      if (!simulation_id)
        throw new Error("No simulation_id returned from backend");
      console.log(
        "[sim] simulation_id:",
        simulation_id,
        "status:",
        startData.status,
      );

      // ── Pre-flight skipped — prediction already in POST response ──────────
      if (startData.status === "skipped") {
        console.log("[sim] pre-flight blocked:", startData.reason);
        setPrediction(startData.prediction);
        setTradeExecution(null);
        setAccuracyStats(null);
        setLivePrice(null);
        setReasoningData(null);
        setPredictionOpen(true);
        return; // skip polling entirely
      }

      // ── Step 2: Poll until done ──
      const POLL_MS = 5000;
      const MAX_MS = 600000;
      const start = Date.now();
      let n404 = 0;
      let poll = 0;

      while (true) {
        await new Promise((r) => setTimeout(r, POLL_MS));

        if (abortPollRef.current) {
          console.log("[sim] poll aborted");
          break;
        }
        if (Date.now() - start > MAX_MS) {
          throw new Error("Simulation exceeded 10 minutes — please try again.");
        }

        poll++;
        console.log(`[sim] poll #${poll} → ${simulation_id}`);

        let res;
        try {
          res = await directFetch(
            `${BACKEND_URL}/api/simulate/status/${simulation_id}`,
            {},
            15000,
          );
        } catch (e) {
          console.warn("[sim] network error on poll, retrying:", e.message);
          continue;
        }

        console.log(`[sim] poll #${poll} HTTP ${res.status}`);

        if (res.status >= 500)
          throw new Error(`Server error ${res.status} on status check`);

        if (res.status === 404) {
          n404++;
          if (n404 >= 3)
            throw new Error(
              "Simulation lost — server restarted. Please try again.",
            );
          continue;
        }
        n404 = 0;
        if (!res.ok) {
          console.warn("[sim] unexpected status", res.status);
          continue;
        }

        const data = await res.json();
        console.log(
          `[sim] poll #${poll}: status=${data.status} has_prediction=${!!data.prediction}`,
        );

        if (data.status === "completed" || data.status === "partial") {
          if (data.prediction) {
            console.log("[sim] prediction received ✓");
            setPrediction(data.prediction);
            setTradeExecution(null);
            setAccuracyStats(null);
            setLivePrice(null);
            setReasoningData(null);
            setPredictionOpen(true);
            // Fire enrichment calls in background — non-blocking
            enrichPrediction(data.prediction);
            setCorrelationArc({
              show: true,
              eventLat: requestBody.lat,
              eventLng: requestBody.lon,
            });
            if (arcTimeoutRef.current) clearTimeout(arcTimeoutRef.current);
            arcTimeoutRef.current = setTimeout(
              () =>
                setCorrelationArc({ show: false, eventLat: 0, eventLng: 0 }),
              8000,
            );
          } else {
            console.error("[sim] completed but prediction is null", data);
            setError(
              "Simulation completed but no report was generated — please try again.",
            );
          }
          break;
        }

        if (data.status === "failed") {
          throw new Error(data.error || "Simulation failed");
        }

        console.log("[sim] still running…");
      }
    } catch (err) {
      console.error("[sim] error:", err.message);
      setError(err.message || "Simulation failed");
    } finally {
      console.log("[sim] done — clearing state");
      isSimulatingRef.current = false;
      setIsSimulating(false);
      setSimulationStartTime(null);
    }
  };

  const handleChokepointSimulate = async (cpId) => {
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/simulate/chokepoint?chokepoint_id=${cpId}&duration_days=7`,
        { method: "POST" },
      );
      const result = await res.json();
      if (result.status === "completed") {
        setChokepointReport(result);
        // Store condensed scores for globe display
        const preds = result.impact?.asx_predictions || [];
        setLastSimScores((prev) => ({
          ...prev,
          [cpId]: {
            topPredictions: preds.slice(0, 3),
            generatedAt: new Date().toISOString(),
          },
        }));
      }
    } catch (err) {
      console.error("Chokepoint simulation error:", err);
    }
  };

  return (
    <div className="app">
      <ErrorBoundary>
        <MacroContext />
      </ErrorBoundary>

      <header className="app-header">
        <div className="logo">
          <h1>Market Oracle AI</h1>
          <p className="tagline">
            Australian Market Intelligence - Geopolitics to ASX in Real-Time
          </p>
        </div>
        <nav className="app-tab-nav">
          <button
            className={`app-tab-btn${activeTab === "main" ? " active" : ""}`}
            onClick={() => navigateTo("main")}
          >
            Predictions
          </button>
          <button
            className={`app-tab-btn${activeTab === "track-record" ? " active" : ""}`}
            onClick={() => navigateTo("track-record")}
          >
            Track Record
          </button>
          <button
            className={`app-tab-btn${activeTab === "simulation" ? " active" : ""}`}
            onClick={() => navigateTo("simulation")}
          >
            Simulation
          </button>
        </nav>
        {portHedlandData && (
          <div className="port-hedland-badge">
            <span className="port-label">Port Hedland</span>
            <span
              className={`congestion-badge ${portHedlandData.congestion_level.toLowerCase()}`}
            >
              {portHedlandData.congestion_level}
            </span>
            <span className="vessel-count">
              {portHedlandData.vessel_count} vessels
            </span>
          </div>
        )}
      </header>

      {activeTab === "track-record" && (
        <div style={{ flex: 1, overflowY: "auto", background: "#05050f" }}>
          <ErrorBoundary>
            <TrackRecord />
          </ErrorBoundary>
        </div>
      )}

      {activeTab === "simulation" && (
        <ErrorBoundary>
          <MonteCarloEngine
            ticker={prediction?.ticker || "BHP.AX"}
            onSimComplete={() => {}}
          />
        </ErrorBoundary>
      )}

      <div
        className="main-container"
        style={{
          display:
            activeTab === "track-record" || activeTab === "simulation"
              ? "none"
              : undefined,
        }}
      >
        <div className="globe-section">
          <ErrorBoundary>
            <EventSidebar
              events={acledEvents}
              onEventSelect={handleEventClick}
              isSimulating={isSimulating}
              selectedEvent={selectedEvent}
            />
          </ErrorBoundary>

          <div
            className="map-view-container"
            data-testid="map-view-container"
            style={{
              position: "absolute",
              left: "280px",
              right: 0,
              top: 0,
              bottom: 0,
              zIndex: 1,
            }}
          >
            {/* View toggle button */}
            <button
              className="view-toggle-btn"
              onClick={() =>
                setViewMode(viewMode === "australia" ? "global" : "australia")
              }
              data-testid="view-toggle-btn"
              title={
                viewMode === "australia"
                  ? "Switch to Global View"
                  : "Switch to Australia View"
              }
            >
              {viewMode === "australia" ? (
                <>
                  <GlobeIcon size={16} />
                  <span>Global View</span>
                </>
              ) : (
                <>
                  <MapIcon size={16} />
                  <span>Australia View</span>
                </>
              )}
            </button>

            {viewMode === "australia" ? (
              <AustraliaMap
                portHedlandData={portHedlandData}
                selectedEvent={selectedEvent}
                onEventClick={handleEventClick}
                prediction={prediction}
              />
            ) : (
              <Globe
                events={acledEvents}
                portHedlandData={portHedlandData}
                onEventClick={handleEventClick}
                isSimulating={isSimulating}
                correlationArc={correlationArc}
                onChokepointSimulate={handleChokepointSimulate}
                lastSimScores={lastSimScores}
              />
            )}
          </div>

          {isSimulating && simulationStartTime && !prediction && (
            <SimulationProgress
              startTime={simulationStartTime}
              ticker={prediction?.ticker || "BHP.AX"}
              minimized={simMinimized}
              onMinimize={() => setSimMinimized(true)}
              onExpand={() => setSimMinimized(false)}
            />
          )}
        </div>

        <div className="sidebar">
          <ErrorBoundary>
            <TickerStrip tickers={asxPrices} />
          </ErrorBoundary>

          <ErrorBoundary>
            <PredictionHistory latestPrediction={prediction} />
          </ErrorBoundary>

          {error && (
            <div className="error-message">
              <strong>Error:</strong> {error}
            </div>
          )}

          {prediction && !isSimulating && (
            <button
              className="view-prediction-btn"
              onClick={() => setPredictionOpen(true)}
            >
              View Prediction — {prediction.ticker}{" "}
              {prediction.direction === "UP"
                ? "▲"
                : prediction.direction === "DOWN"
                  ? "▼"
                  : "—"}
            </button>
          )}

          {!prediction && !isSimulating && !error && (
            <div className="instructions">
              <h3>Australian Market Intelligence</h3>
              <p className="australia-focus">
                Track how global events impact Australian stocks, resources, and
                economy in real-time.
              </p>
              <ol>
                <li>Click any geopolitical event affecting Australia</li>
                <li>50 AI agents simulate ASX market participant reactions</li>
                <li>Get predictions with Australian economic context</li>
              </ol>
              <div className="demo-url">
                <strong>asx.marketoracle.ai</strong>
                <br />
                <small>(demo environment)</small>
              </div>
            </div>
          )}

          <ErrorBoundary>
            <AustralianEconomicContext />
          </ErrorBoundary>

          <ErrorBoundary>
            <ChokepointRiskPanel
              onSimulateChokepoint={(result) => {
                setChokepointReport(result);
                const preds = result?.impact?.asx_predictions || [];
                if (result?.chokepoint_id) {
                  setLastSimScores((prev) => ({
                    ...prev,
                    [result.chokepoint_id]: {
                      topPredictions: preds.slice(0, 3),
                      generatedAt: new Date().toISOString(),
                    },
                  }));
                }
              }}
            />
          </ErrorBoundary>
        </div>
      </div>

      {activeTab === "main" && (
        <ErrorBoundary>
          <SectorHeatmap />
        </ErrorBoundary>
      )}

      <footer className="app-footer">
        <p>
          Market Oracle AI - Australian Market Intelligence Platform -
          Geopolitical Events to ASX Impact
        </p>
      </footer>

      {prediction && predictionOpen && (
        <ErrorBoundary>
          <PredictionCard
            prediction={prediction}
            tradeExecution={tradeExecution}
            accuracyStats={accuracyStats}
            livePrice={livePrice}
            reasoningData={reasoningData}
            onClose={() => setPredictionOpen(false)}
          />
        </ErrorBoundary>
      )}

      {chokepointReport && (
        <ErrorBoundary>
          <ChokepointReportModal
            result={chokepointReport}
            onClose={() => setChokepointReport(null)}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}

export default App;

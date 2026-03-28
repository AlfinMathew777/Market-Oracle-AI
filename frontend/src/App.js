import React, { useState, useEffect, useRef } from 'react';
import Globe from './components/Globe';
import AustraliaMap from './components/AustraliaMap';
import EventSidebar from './components/EventSidebar';
import PredictionCard from './components/PredictionCard';
import ChokepointReportModal from './components/ChokepointReportModal';
import TickerStrip from './components/TickerStrip';
import SimulationProgress from './components/SimulationProgress';
import SectorHeatmap from './components/SectorHeatmap';
import PredictionHistory from './components/PredictionHistory';
import MacroContext from './components/MacroContext';
import AustralianEconomicContext from './components/AustralianEconomicContext';
import ChokepointRiskPanel from './components/ChokepointRiskPanel';
import TrackRecord from './components/TrackRecord';
import ErrorBoundary from './components/ErrorBoundary';
import MonteCarloEngine from './components/MonteCarlo/MonteCarloEngine';
import { Globe as GlobeIcon, Map as MapIcon } from 'lucide-react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

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
  const [correlationArc, setCorrelationArc] = useState({ show: false, eventLat: 0, eventLng: 0 });
  const [viewMode, setViewMode] = useState('australia'); // 'australia' or 'global'
  const [activeTab, setActiveTab] = useState('main'); // 'main' or 'track-record'
  const [chokepointReport, setChokepointReport] = useState(null);  // full chokepoint sim result
  const [lastSimScores, setLastSimScores] = useState({});           // cpId → {topPredictions, generatedAt}
  const arcTimeoutRef = useRef(null);

  // Sync activeTab with URL hash
  useEffect(() => {
    const handleHashChange = () => {
      const h = window.location.hash;
      if (h === '#/track-record') setActiveTab('track-record');
      else if (h === '#/simulation') setActiveTab('simulation');
      else setActiveTab('main');
    };
    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateTo = (tab) => {
    if (tab === 'track-record') window.location.hash = '#/track-record';
    else if (tab === 'simulation') window.location.hash = '#/simulation';
    else window.location.hash = '#/';
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
    try {
      const acledResponse = await fetch(`${BACKEND_URL}/api/data/acled`);
      const acledData = await acledResponse.json();
      if (acledData.status === 'success') {
        setAcledEvents(acledData.data.features);
        localStorage.setItem('acled_events', JSON.stringify(acledData.data.features));
      }

      const asxResponse = await fetch(`${BACKEND_URL}/api/data/asx-prices`);
      const asxData = await asxResponse.json();
      if (asxData.status === 'success') {
        setAsxPrices(asxData.data);
        localStorage.setItem('asx_prices', JSON.stringify(asxData.data));
      }

      const portResponse = await fetch(`${BACKEND_URL}/api/data/port-hedland`);
      const portData = await portResponse.json();
      if (portData.status === 'success') {
        setPortHedlandData(portData.data);
      }
    } catch (err) {
      console.error('Error fetching initial data:', err);
      const cachedAcled = localStorage.getItem('acled_events');
      const cachedAsx = localStorage.getItem('asx_prices');
      if (cachedAcled) setAcledEvents(JSON.parse(cachedAcled));
      if (cachedAsx) setAsxPrices(JSON.parse(cachedAsx));
      setError('Using cached data (offline mode)');
    }
  };

  const handleEventClick = async (event) => {
    setSelectedEvent(event);
    setPrediction(null);
    setError(null);
    setIsSimulating(true);
    setSimulationStartTime(Date.now());
    setSimMinimized(false);

    try {
      const requestBody = {
        event_id: event.properties.id,
        event_description: event.properties.description,
        event_type: event.properties.event_type,
        lat: event.geometry.coordinates[1],
        lon: event.geometry.coordinates[0],
        country: event.properties.country,
        fatalities: event.properties.fatalities,
        date: event.properties.date
      };

      console.log('Starting simulation for:', requestBody);

      // Step 1: Start simulation as a background task — returns simulation_id immediately
      let startResp;
      try {
        startResp = await fetch(`${BACKEND_URL}/api/simulate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        });
      } catch (fetchErr) {
        // Retry once on network error (backend cold-start)
        console.warn('Simulation start failed, retrying after 10s…');
        await new Promise(r => setTimeout(r, 10000));
        startResp = await fetch(`${BACKEND_URL}/api/simulate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        });
      }

      if (!startResp.ok) {
        let detail = 'Simulation failed to start';
        try { detail = (await startResp.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }

      const { simulation_id } = await startResp.json();
      console.log('Simulation started:', simulation_id);

      // Step 2: Poll until completed, failed, or 10-minute hard cap
      const POLL_INTERVAL_MS = 5000;
      const MAX_WAIT_MS = 600000; // 10 minutes
      const pollStart = Date.now();

      while (true) {
        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));

        if (Date.now() - pollStart > MAX_WAIT_MS) {
          throw new Error('Simulation exceeded 10 minutes — please try again.');
        }

        let statusResp;
        try {
          statusResp = await fetch(`${BACKEND_URL}/api/simulate/status/${simulation_id}`);
        } catch (_) {
          // Transient network error — keep polling
          continue;
        }

        // 5xx = server error (e.g. serialization failure) — stop polling, don't loop forever
        if (statusResp.status >= 500) {
          throw new Error(`Simulation status check failed (${statusResp.status}) — please try again`);
        }
        // 404 / other transient errors — keep polling
        if (!statusResp.ok) continue;

        const result = await statusResp.json();
        console.log('Simulation status:', result.status);

        if (result.status === 'completed' || result.status === 'partial') {
          if (result.prediction) {
            setPrediction(result.prediction);
            setPredictionOpen(true);

            setCorrelationArc({
              show: true,
              eventLat: requestBody.lat,
              eventLng: requestBody.lon
            });

            if (arcTimeoutRef.current) clearTimeout(arcTimeoutRef.current);
            arcTimeoutRef.current = setTimeout(() => {
              setCorrelationArc({ show: false, eventLat: 0, eventLng: 0 });
            }, 8000);
          } else {
            // Backend completed but prediction is null — show error instead of polling forever
            setError('Simulation completed but no report was generated — please try again.');
          }
          break; // Always break on completed/partial regardless of prediction
        }

        if (result.status === 'failed') {
          throw new Error(result.error || 'Simulation failed');
        }
        // status === 'running' → keep polling
      }
    } catch (err) {
      console.error('Simulation error:', err);
      setError(err.message || 'Simulation failed');
    } finally {
      setIsSimulating(false);
      setSimulationStartTime(null);
    }
  };

  const handleChokepointSimulate = async (cpId) => {
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/simulate/chokepoint?chokepoint_id=${cpId}&duration_days=7`,
        { method: 'POST' }
      );
      const result = await res.json();
      if (result.status === 'completed') {
        setChokepointReport(result);
        // Store condensed scores for globe display
        const preds = result.impact?.asx_predictions || [];
        setLastSimScores(prev => ({
          ...prev,
          [cpId]: {
            topPredictions: preds.slice(0, 3),
            generatedAt: new Date().toISOString(),
          },
        }));
      }
    } catch (err) {
      console.error('Chokepoint simulation error:', err);
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
          <p className="tagline">Australian Market Intelligence - Geopolitics to ASX in Real-Time</p>
        </div>
        <nav className="app-tab-nav">
          <button
            className={`app-tab-btn${activeTab === 'main' ? ' active' : ''}`}
            onClick={() => navigateTo('main')}
          >
            Predictions
          </button>
          <button
            className={`app-tab-btn${activeTab === 'track-record' ? ' active' : ''}`}
            onClick={() => navigateTo('track-record')}
          >
            Track Record
          </button>
          <button
            className={`app-tab-btn${activeTab === 'simulation' ? ' active' : ''}`}
            onClick={() => navigateTo('simulation')}
          >
            Simulation
          </button>
        </nav>
        {portHedlandData && (
          <div className="port-hedland-badge">
            <span className="port-label">Port Hedland</span>
            <span className={`congestion-badge ${portHedlandData.congestion_level.toLowerCase()}`}>
              {portHedlandData.congestion_level}
            </span>
            <span className="vessel-count">{portHedlandData.vessel_count} vessels</span>
          </div>
        )}
      </header>

      {activeTab === 'track-record' && (
        <div style={{ flex: 1, overflowY: 'auto', background: '#05050f' }}>
          <ErrorBoundary>
            <TrackRecord />
          </ErrorBoundary>
        </div>
      )}

      {activeTab === 'simulation' && (
        <ErrorBoundary>
          <MonteCarloEngine
            ticker={prediction?.ticker || 'BHP.AX'}
            onSimComplete={(result) => {
              // Optional: lift sim result to App state for future use
            }}
          />
        </ErrorBoundary>
      )}

      <div className="main-container" style={{ display: (activeTab === 'track-record' || activeTab === 'simulation') ? 'none' : undefined }}>
        <div className="globe-section">
          <ErrorBoundary>
            <EventSidebar
              events={acledEvents}
              onEventSelect={handleEventClick}
              isSimulating={isSimulating}
            />
          </ErrorBoundary>

          <div 
            className="map-view-container" 
            data-testid="map-view-container"
            style={{
              position: 'absolute',
              left: '280px',
              right: 0,
              top: 0,
              bottom: 0,
              zIndex: 1
            }}
          >
            {/* View toggle button */}
            <button
              className="view-toggle-btn"
              onClick={() => setViewMode(viewMode === 'australia' ? 'global' : 'australia')}
              data-testid="view-toggle-btn"
              title={viewMode === 'australia' ? 'Switch to Global View' : 'Switch to Australia View'}
            >
              {viewMode === 'australia' ? (
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

            {viewMode === 'australia' ? (
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

          {isSimulating && simulationStartTime && (
            <SimulationProgress
              startTime={simulationStartTime}
              ticker={prediction?.ticker || 'BHP.AX'}
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
            <button className="view-prediction-btn" onClick={() => setPredictionOpen(true)}>
              View Prediction — {prediction.ticker} {prediction.direction === 'UP' ? '▲' : prediction.direction === 'DOWN' ? '▼' : '—'}
            </button>
          )}

          {!prediction && !isSimulating && !error && (
            <div className="instructions">
              <h3>Australian Market Intelligence</h3>
              <p className="australia-focus">
                Track how global events impact Australian stocks, resources, and economy in real-time.
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
                  setLastSimScores(prev => ({
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

      {activeTab === 'main' && (
        <ErrorBoundary>
          <SectorHeatmap />
        </ErrorBoundary>
      )}

      <footer className="app-footer">
        <p>Market Oracle AI - Australian Market Intelligence Platform - Geopolitical Events to ASX Impact</p>
      </footer>

      {prediction && predictionOpen && (
        <ErrorBoundary>
          <PredictionCard prediction={prediction} onClose={() => setPredictionOpen(false)} />
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

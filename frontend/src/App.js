import React, { useState, useEffect, useRef } from 'react';
import Globe from './components/Globe';
import AustraliaMap from './components/AustraliaMap';
import EventSidebar from './components/EventSidebar';
import PredictionCard from './components/PredictionCard';
import TickerStrip from './components/TickerStrip';
import SimulationProgress from './components/SimulationProgress';
import SectorHeatmap from './components/SectorHeatmap';
import PredictionHistory from './components/PredictionHistory';
import MacroContext from './components/MacroContext';
import AustralianEconomicContext from './components/AustralianEconomicContext';
import ChokepointRiskPanel from './components/ChokepointRiskPanel';
import TrackRecord from './components/TrackRecord';
import ErrorBoundary from './components/ErrorBoundary';
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
  const arcTimeoutRef = useRef(null);

  // Sync activeTab with URL hash
  useEffect(() => {
    const handleHashChange = () => {
      setActiveTab(window.location.hash === '#/track-record' ? 'track-record' : 'main');
    };
    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateTo = (tab) => {
    window.location.hash = tab === 'track-record' ? '#/track-record' : '#/';
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

      const response = await fetch(`${BACKEND_URL}/api/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Simulation failed');
      }

      const result = await response.json();
      console.log('Simulation result:', result);

      if (result.status === 'completed' && result.prediction) {
        setPrediction(result.prediction);
        setPredictionOpen(true);
        
        // Trigger correlation arc overlay
        setCorrelationArc({
          show: true,
          eventLat: requestBody.lat,
          eventLng: requestBody.lon
        });
        
        // Auto-fade arc after 8 seconds
        if (arcTimeoutRef.current) {
          clearTimeout(arcTimeoutRef.current);
        }
        arcTimeoutRef.current = setTimeout(() => {
          setCorrelationArc({ show: false, eventLat: 0, eventLng: 0 });
        }, 8000);
      } else {
        throw new Error('Simulation did not complete successfully');
      }
    } catch (err) {
      console.error('Simulation error:', err);
      setError(err.message || 'Simulation failed');
    } finally {
      setIsSimulating(false);
      setSimulationStartTime(null);
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
        <ErrorBoundary>
          <TrackRecord />
        </ErrorBoundary>
      )}

      <div className="main-container" style={{ display: activeTab === 'track-record' ? 'none' : undefined }}>
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
                if (result?.prediction) {
                  setPrediction({
                    ...result.prediction,
                    source: 'chokepoint',
                    chokepoint_name: result.chokepoint_name,
                  });
                }
              }}
            />
          </ErrorBoundary>
        </div>
      </div>

      {activeTab !== 'track-record' && (
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
    </div>
  );
}

export default App;

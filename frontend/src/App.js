import React, { useState, useEffect } from 'react';
import Globe from './components/Globe';
import EventSidebar from './components/EventSidebar';
import PredictionCard from './components/PredictionCard';
import TickerStrip from './components/TickerStrip';
import SimulationProgress from './components/SimulationProgress';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function App() {
  const [acledEvents, setAcledEvents] = useState([]);
  const [asxPrices, setAsxPrices] = useState([]);
  const [portHedlandData, setPortHedlandData] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationStartTime, setSimulationStartTime] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [error, setError] = useState(null);

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
      <header className="app-header">
        <div className="logo">
          <h1>Market Oracle AI</h1>
          <p className="tagline">ASX Intelligence - 50-Agent Prediction Engine</p>
        </div>
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

      <div className="main-container">
        <div className="globe-section">
          <EventSidebar
            events={acledEvents}
            onEventSelect={handleEventClick}
            isSimulating={isSimulating}
          />

          <Globe
            events={acledEvents}
            portHedlandData={portHedlandData}
            onEventClick={handleEventClick}
            isSimulating={isSimulating}
          />

          {isSimulating && simulationStartTime && (
            <SimulationProgress startTime={simulationStartTime} />
          )}
        </div>

        <div className="sidebar">
          <TickerStrip tickers={asxPrices} />
          
          {error && (
            <div className="error-message">
              <strong>Error:</strong> {error}
            </div>
          )}

          {prediction && !isSimulating && (
            <PredictionCard prediction={prediction} />
          )}

          {!prediction && !isSimulating && !error && (
            <div className="instructions">
              <h3>How to Use</h3>
              <ol>
                <li>Click any event in the left sidebar or on the globe</li>
                <li>Watch the simulation progress (3-5 minutes)</li>
                <li>View the prediction card with confidence score and causal chain</li>
              </ol>
              <p className="demo-note">
                <strong>Demo Tip:</strong> Try the Iran/Strait of Hormuz event for a 
                compelling commodity price story, or DRC lithium for rare earths impact.
              </p>
            </div>
          )}
        </div>
      </div>

      <footer className="app-footer">
        <p>Market Oracle AI MVP - 8 Real-World Events - 5 ASX Tickers - Zero-Cost Infrastructure</p>
      </footer>
    </div>
  );
}

export default App;

import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
import './PredictionHistory.css';

const PredictionHistory = ({ latestPrediction }) => {
  const [history, setHistory] = useState([]);
  const [isExpanded, setIsExpanded] = useState(true);

  // Load history from localStorage on mount
  useEffect(() => {
    const savedHistory = localStorage.getItem('prediction_history');
    if (savedHistory) {
      try {
        setHistory(JSON.parse(savedHistory));
      } catch (err) {
        console.error('Error parsing prediction history:', err);
        localStorage.removeItem('prediction_history');
      }
    }
  }, []);

  // Add new prediction to history when it arrives
  useEffect(() => {
    if (latestPrediction) {
      setHistory(prevHistory => {
        const newEntry = {
          id: Date.now(),
          timestamp: new Date().toISOString(),
          ticker: latestPrediction.ticker,
          direction: latestPrediction.direction,
          confidence: latestPrediction.confidence,
          eventSummary: latestPrediction.event_context?.event_type || 'Event',
          country: latestPrediction.event_context?.country || 'Unknown'
        };

        const updatedHistory = [newEntry, ...prevHistory];
        localStorage.setItem('prediction_history', JSON.stringify(updatedHistory));
        return updatedHistory;
      });
    }
  }, [latestPrediction]);

  const handleClear = () => {
    if (window.confirm('Clear all prediction history? This cannot be undone.')) {
      setHistory([]);
      localStorage.removeItem('prediction_history');
    }
  };

  const displayedHistory = isExpanded ? history : history.slice(0, 3);

  if (history.length === 0) {
    return (
      <div className="prediction-history" data-testid="prediction-history">
        <div className="history-header">
          <h3>PREDICTION HISTORY</h3>
        </div>
        <div className="history-empty" data-testid="history-empty">
          <p>No predictions yet</p>
          <small>Run a simulation to build your track record</small>
        </div>
      </div>
    );
  }

  return (
    <div className="prediction-history" data-testid="prediction-history">
      <div className="history-header">
        <h3>PREDICTION HISTORY</h3>
        <div className="history-controls">
          <button
            className="clear-btn"
            onClick={handleClear}
            data-testid="clear-history-btn"
            title="Clear all history"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="history-list" data-testid="history-list">
        {displayedHistory.map((entry) => {
          const directionClass = entry.direction.toLowerCase();
          const confidencePercent = Math.round(entry.confidence * 100);
          const timestamp = new Date(entry.timestamp);
          const timeStr = timestamp.toLocaleTimeString('en-AU', { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false 
          });

          return (
            <div 
              key={entry.id} 
              className="history-entry" 
              data-testid={`history-entry-${entry.id}`}
            >
              <div className="history-entry-header">
                <span className="history-ticker" data-testid="history-ticker">
                  {entry.ticker.replace('.AX', '')}
                </span>
                <span className={`history-direction ${directionClass}`} data-testid="history-direction">
                  {entry.direction}
                </span>
                <span className="history-time" data-testid="history-time">{timeStr}</span>
              </div>
              <div className="history-entry-body">
                <span className="history-event" data-testid="history-event">
                  {entry.country}: {entry.eventSummary}
                </span>
                <span className="history-confidence" data-testid="history-confidence">
                  {confidencePercent}% confidence
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {history.length > 3 && (
        <button
          className="expand-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
          data-testid="expand-toggle-btn"
        >
          {isExpanded ? (
            <>
              <ChevronUp size={16} />
              Show less
            </>
          ) : (
            <>
              <ChevronDown size={16} />
              Show all ({history.length})
            </>
          )}
        </button>
      )}
    </div>
  );
};

export default PredictionHistory;

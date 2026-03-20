import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import './PredictionHistory.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const PredictionHistory = ({ latestPrediction }) => {
  const [history, setHistory] = useState([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/predict/history?limit=50`);
      const result = await res.json();
      if (result.status === 'success' && Array.isArray(result.data)) {
        setHistory(result.data);
      }
    } catch (err) {
      console.error('Error fetching prediction history:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load history from API on mount
  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Re-fetch after a new prediction completes
  useEffect(() => {
    if (latestPrediction) {
      // Small delay so the backend persist task has time to write
      const timer = setTimeout(fetchHistory, 2000);
      return () => clearTimeout(timer);
    }
  }, [latestPrediction, fetchHistory]);

  const displayedHistory = isExpanded ? history : history.slice(0, 3);

  if (loading) {
    return (
      <div className="prediction-history" data-testid="prediction-history">
        <div className="history-header">
          <h3>PREDICTION HISTORY</h3>
        </div>
        <div className="history-empty">
          <p>Loading history...</p>
        </div>
      </div>
    );
  }

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
            onClick={fetchHistory}
            data-testid="refresh-history-btn"
            title="Refresh history"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="history-list" data-testid="history-list">
        {displayedHistory.map((entry) => {
          const direction = entry.direction || 'NEUTRAL';
          const directionClass = direction.toLowerCase();
          const confidencePercent = Math.round((entry.confidence || 0) * 100);
          const timestamp = new Date(entry.created_at || entry.timestamp || Date.now());
          const timeStr = timestamp.toLocaleTimeString('en-AU', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          });
          const outcomeLabel = entry.outcome && entry.outcome !== 'PENDING'
            ? ` · ${entry.outcome}`
            : '';

          return (
            <div
              key={entry.simulation_id || entry.id}
              className="history-entry"
              data-testid={`history-entry-${entry.simulation_id || entry.id}`}
            >
              <div className="history-entry-header">
                <span className="history-ticker" data-testid="history-ticker">
                  {(entry.ticker || '').replace('.AX', '')}
                </span>
                <span className={`history-direction ${directionClass}`} data-testid="history-direction">
                  {direction}
                </span>
                <span className="history-time" data-testid="history-time">{timeStr}</span>
              </div>
              <div className="history-entry-body">
                <span className="history-event" data-testid="history-event">
                  {entry.country || 'Unknown'}: {entry.event_type || 'Event'}
                </span>
                <span className="history-confidence" data-testid="history-confidence">
                  {confidencePercent}% confidence{outcomeLabel}
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

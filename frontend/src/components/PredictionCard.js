import React from 'react';
import './PredictionCard.css';

function PredictionCard({ prediction }) {
  if (!prediction) return null;

  const getDirectionIcon = (direction) => {
    switch (direction) {
      case 'UP':
        return '▲';
      case 'DOWN':
        return '▼';
      case 'NEUTRAL':
        return '—';
      default:
        return '—';
    }
  };

  const getDirectionColor = (direction) => {
    switch (direction) {
      case 'UP':
        return '#00ff88';
      case 'DOWN':
        return '#ff3366';
      case 'NEUTRAL':
        return '#aaaaaa';
      default:
        return '#aaaaaa';
    }
  };

  const confidencePercent = Math.round(prediction.confidence * 100);

  return (
    <div className="prediction-card">
      <div className="card-header">
        <h2>Prediction Report</h2>
        <span className="simulation-id">{prediction.simulation_id}</span>
      </div>

      <div className="ticker-section">
        <div className="ticker-badge">{prediction.ticker}</div>
        <div
          className="direction-indicator"
          style={{ color: getDirectionColor(prediction.direction) }}
        >
          <span className="direction-icon">{getDirectionIcon(prediction.direction)}</span>
          <span className="direction-text">{prediction.direction}</span>
        </div>
      </div>

      <div className="confidence-section">
        <label>Confidence</label>
        <div className="confidence-bar">
          <div
            className="confidence-fill"
            style={{
              width: `${confidencePercent}%`,
              backgroundColor: getDirectionColor(prediction.direction),
            }}
          ></div>
        </div>
        <span className="confidence-value">{confidencePercent}%</span>
      </div>

      <div className="time-horizon">
        <label>Time Horizon</label>
        <span className="badge">{prediction.time_horizon === 'd7' ? '7 Days' : prediction.time_horizon}</span>
      </div>

      <div className="causal-chain">
        <h3>Causal Chain</h3>
        <ol>
          {prediction.causal_chain && prediction.causal_chain.map((step, index) => (
            <li key={index}>
              <strong>{step.event}</strong>
              <p>→ {step.consequence}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="agent-consensus">
        <h3>Agent Consensus ({prediction.agent_consensus.up + prediction.agent_consensus.down + prediction.agent_consensus.neutral} agents)</h3>
        <div className="consensus-grid">
          <div className="consensus-item up">
            <span className="icon">▲</span>
            <span className="count">{prediction.agent_consensus.up}</span>
            <span className="label">Bullish</span>
          </div>
          <div className="consensus-item down">
            <span className="icon">▼</span>
            <span className="count">{prediction.agent_consensus.down}</span>
            <span className="label">Bearish</span>
          </div>
          <div className="consensus-item neutral">
            <span className="icon">—</span>
            <span className="count">{prediction.agent_consensus.neutral}</span>
            <span className="label">Neutral</span>
          </div>
        </div>
      </div>

      {prediction.key_signals && prediction.key_signals.length > 0 && (
        <div className="key-signals">
          <h3>Key Signals</h3>
          {prediction.key_signals.map((signal, index) => (
            <div key={index} className="signal-item">
              <span className="signal-type">{signal.signal_type}</span>
              <p>{signal.description}</p>
            </div>
          ))}
        </div>
      )}

      {prediction.contrarian_view && (
        <div className="contrarian-view">
          <h4>⚠️ Contrarian View</h4>
          <p>{prediction.contrarian_view}</p>
        </div>
      )}

      {prediction.risk_factors && prediction.risk_factors.length > 0 && (
        <div className="risk-factors">
          <h4>Risk Factors</h4>
          <ul>
            {prediction.risk_factors.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="disclaimer">
        <small>⚠️ Analytical intelligence only. Not financial advice.</small>
      </div>
    </div>
  );
}

export default PredictionCard;

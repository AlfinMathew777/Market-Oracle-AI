import React, { useState, useEffect } from 'react';
import './SimulationProgress.css';

function SimulationProgress({ startTime }) {
  const [elapsed, setElapsed] = useState(0);
  const [currentPhase, setCurrentPhase] = useState(0);

  const phases = [
    { at: 0, label: 'Building knowledge graph from event data...' },
    { at: 20, label: 'Generating 50 ASX market participant agents...' },
    { at: 40, label: 'Running simulation rounds — agents forming opinions...' },
    { at: 120, label: 'Detecting consensus patterns and opinion leaders...' },
    { at: 200, label: 'Claude generating structured prediction report...' },
    { at: 280, label: 'Validating prediction schema and causal chain...' },
  ];

  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      const elapsedSeconds = Math.floor((now - startTime) / 1000);
      setElapsed(elapsedSeconds);
      
      const phase = phases.filter(p => p.at <= elapsedSeconds).length - 1;
      setCurrentPhase(Math.max(0, Math.min(phase, phases.length - 1)));
    }, 1000);

    return () => clearInterval(timer);
  }, [startTime]);

  return (
    <div className="simulation-progress-overlay">
      <div className="progress-content">
        <div className="progress-timer">
          {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}
        </div>
        <div className="progress-phase">
          {phases[currentPhase]?.label || 'Initializing...'}
        </div>
        <div className="progress-spinner">
          <div className="spinner-ring"></div>
        </div>
        <div className="progress-note">
          50 AI agents reasoning in parallel
        </div>
        <div className="progress-estimate">
          Typical completion: 3-5 minutes
        </div>
      </div>
    </div>
  );
}

export default SimulationProgress;

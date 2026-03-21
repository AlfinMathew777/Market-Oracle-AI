import React, { useState, useEffect, useRef } from 'react';
import './SimulationProgress.css';

const AGENT_PERSONAS = [
  { id: 1,  role: 'Fund Manager',        firm: 'BlackRock AU',       focus: 'macro',      color: '#3366ff' },
  { id: 2,  role: 'Commodities Desk',    firm: 'Macquarie',          focus: 'iron_ore',   color: '#ff6633' },
  { id: 3,  role: 'Quant Analyst',       firm: 'Two Sigma',          focus: 'quant',      color: '#33ff99' },
  { id: 4,  role: 'Retail Trader',       firm: 'CommSec',            focus: 'retail',     color: '#ffcc00' },
  { id: 5,  role: 'Credit Analyst',      firm: 'Moody\'s',           focus: 'credit',     color: '#cc33ff' },
  { id: 6,  role: 'Geopolitical Risk',   firm: 'Oxford Analytica',   focus: 'geo',        color: '#ff3366' },
  { id: 7,  role: 'LNG Trader',          firm: 'Woodside Energy',    focus: 'lng',        color: '#33ccff' },
  { id: 8,  role: 'Mining Analyst',      firm: 'RBC Capital',        focus: 'mining',     color: '#ff9933' },
  { id: 9,  role: 'FX Strategist',       firm: 'ANZ Research',       focus: 'fx',         color: '#66ff33' },
  { id: 10, role: 'Hedge Fund PM',       firm: 'Citadel',            focus: 'macro',      color: '#ff33cc' },
  { id: 11, role: 'Superannuation CIO',  firm: 'AustralianSuper',    focus: 'macro',      color: '#3399ff' },
  { id: 12, role: 'Iron Ore Trader',     firm: 'BHP Trading',        focus: 'iron_ore',   color: '#ff6600' },
  { id: 13, role: 'Options Trader',      firm: 'Optiver',            focus: 'quant',      color: '#00ffcc' },
  { id: 14, role: 'ESG Analyst',         firm: 'Pendal Group',       focus: 'esg',        color: '#ccff00' },
  { id: 15, role: 'Central Bank Watch',  firm: 'RBA Observer',       focus: 'macro',      color: '#ff3399' },
];

const LOG_TEMPLATES = [
  (a, ticker) => `${a.role} at ${a.firm}: Analysing ${ticker} exposure to event`,
  (a, ticker) => `${a.role}: Checking iron ore futures correlation with ${ticker}`,
  (a, ticker) => `${a.firm} desk: Revising ASX ${ticker} 7-day outlook`,
  (a, ticker) => `${a.role}: Running DCF sensitivity on ${ticker} revenue`,
  (a, ticker) => `${a.firm}: Cross-referencing China PMI with ${ticker} demand`,
  (a, ticker) => `${a.role}: Flagging ${ticker} as high-impact — updating position`,
  (a, ticker) => `${a.role} signals ${ticker} momentum shift — consensus forming`,
  (a, ticker) => `${a.firm} quant model: ${ticker} vol surface repricing`,
  (a, ticker) => `${a.role}: Reviewing AUD/USD transmission risk for ${ticker}`,
  (a, ticker) => `${a.firm}: Geopolitical discount applied to ${ticker} fair value`,
  (a) => `${a.role} at ${a.firm}: Round 2 opinion update — revising stance`,
  (a) => `${a.role}: Checking GDELT sentiment alignment with initial thesis`,
  (a) => `${a.firm}: Monitoring Port Hedland throughput signal`,
  (a) => `${a.role}: Aggregating agent consensus for final prediction`,
  (a) => `${a.firm}: Validating causal chain coherence score`,
];

const PHASES = [
  { at: 0,   label: 'Initialising knowledge graph from event data',    agents: 0  },
  { at: 10,  label: 'Spawning 30 ASX market participant agents',        agents: 10 },
  { at: 25,  label: 'Round 1 — agents forming initial opinions',        agents: 20 },
  { at: 80,  label: 'Round 2 — cross-agent debate and revision',        agents: 28 },
  { at: 150, label: 'Round 3 — consensus detection in progress',        agents: 30 },
  { at: 220, label: 'Generating structured prediction report',          agents: 30 },
  { at: 280, label: 'Validating prediction schema and causal chain',    agents: 30 },
];

export default function SimulationProgress({ startTime, ticker = 'BHP.AX', minimized = false, onMinimize, onExpand }) {
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState([]);
  const [activeAgents, setActiveAgents] = useState([]);
  const [agentCount, setAgentCount] = useState(0);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const logsEndRef = useRef(null);
  const logIntervalRef = useRef(null);

  useEffect(() => {
    const timer = setInterval(() => {
      const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
      setElapsed(elapsedSeconds);

      const idx = PHASES.filter(p => p.at <= elapsedSeconds).length - 1;
      const phase = PHASES[Math.max(0, Math.min(idx, PHASES.length - 1))];
      setPhaseIdx(Math.max(0, Math.min(idx, PHASES.length - 1)));
      setAgentCount(phase.agents);
    }, 1000);
    return () => clearInterval(timer);
  }, [startTime]);

  // Emit a new log line every 2.5s
  useEffect(() => {
    logIntervalRef.current = setInterval(() => {
      const agent = AGENT_PERSONAS[Math.floor(Math.random() * AGENT_PERSONAS.length)];
      const template = LOG_TEMPLATES[Math.floor(Math.random() * LOG_TEMPLATES.length)];
      const msg = template(agent, ticker);
      const ts = new Date().toLocaleTimeString('en-AU', { hour12: false });
      setLogs(prev => [...prev.slice(-49), { ts, msg, color: agent.color, id: Date.now() }]);
    }, 2500);
    return () => clearInterval(logIntervalRef.current);
  }, [ticker]);

  // Animate active agents
  useEffect(() => {
    const interval = setInterval(() => {
      const count = Math.min(agentCount, AGENT_PERSONAS.length);
      const shuffled = [...AGENT_PERSONAS].sort(() => Math.random() - 0.5).slice(0, count);
      setActiveAgents(shuffled);
    }, 3000);
    return () => clearInterval(interval);
  }, [agentCount]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const mins = Math.floor(elapsed / 60);
  const secs = String(elapsed % 60).padStart(2, '0');
  const progress = Math.min((elapsed / 300) * 100, 99);

  // Minimized pill
  if (minimized) {
    return (
      <div className="sim-minimized" onClick={onExpand} title="Click to expand simulation">
        <span className="sim-pulse" />
        <span className="sim-mini-label">Simulating {ticker}</span>
        <span className="sim-mini-timer">{mins}:{secs}</span>
        <span className="sim-mini-expand">↗</span>
      </div>
    );
  }

  return (
    <div className="sim-overlay">
      <div className="sim-panel">

        {/* Header */}
        <div className="sim-header">
          <div className="sim-title">
            <span className="sim-pulse" />
            AGENT SIMULATION RUNNING
          </div>
          <div className="sim-header-right">
            <div className="sim-timer">{mins}:{secs}</div>
            <button className="sim-minimize-btn" onClick={onMinimize} title="Minimise simulation">
              ─
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="sim-stats">
          <div className="sim-stat">
            <div className="sim-stat-val">{agentCount}</div>
            <div className="sim-stat-lbl">Active Agents</div>
          </div>
          <div className="sim-stat">
            <div className="sim-stat-val">30</div>
            <div className="sim-stat-lbl">Total Agents</div>
          </div>
          <div className="sim-stat">
            <div className="sim-stat-val">{ticker}</div>
            <div className="sim-stat-lbl">Primary Ticker</div>
          </div>
          <div className="sim-stat">
            <div className="sim-stat-val">{phaseIdx + 1}/7</div>
            <div className="sim-stat-lbl">Phase</div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="sim-progress-bar-wrap">
          <div className="sim-progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <div className="sim-phase-label">{PHASES[phaseIdx]?.label}</div>

        <div className="sim-body">
          {/* Agent grid */}
          <div className="sim-agents">
            <div className="sim-section-title">AGENT PERSONAS</div>
            <div className="sim-agent-grid">
              {AGENT_PERSONAS.map(agent => {
                const isActive = activeAgents.some(a => a.id === agent.id);
                return (
                  <div
                    key={agent.id}
                    className={`sim-agent-chip ${isActive ? 'active' : ''}`}
                    style={{ '--agent-color': agent.color }}
                  >
                    <span className="sim-agent-dot" />
                    <div>
                      <div className="sim-agent-role">{agent.role}</div>
                      <div className="sim-agent-firm">{agent.firm}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Live log */}
          <div className="sim-log">
            <div className="sim-section-title">SYSTEM LOG</div>
            <div className="sim-log-entries">
              {logs.map(log => (
                <div key={log.id} className="sim-log-line">
                  <span className="sim-log-ts">{log.ts}</span>
                  <span className="sim-log-dot" style={{ color: log.color }}>▸</span>
                  <span className="sim-log-msg">{log.msg}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>

        <div className="sim-footer">Typical completion: 3–5 minutes · Do not close this window</div>
      </div>
    </div>
  );
}

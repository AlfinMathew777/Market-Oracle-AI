import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import './SimulationProgress.css';

// ── Node data for the knowledge graph ──────────────────────────────────────
const buildGraphNodes = (ticker) => [
  // Central event node
  { id: 'event', label: 'Geopolitical Event', type: 'event', group: 'core' },
  // Ticker node
  { id: ticker, label: ticker, type: 'ticker', group: 'asx' },
  // Agent nodes
  { id: 'ag-macro', label: 'Macro Desk', type: 'agent', group: 'agent' },
  { id: 'ag-quant', label: 'Quant Engine', type: 'agent', group: 'agent' },
  { id: 'ag-geo', label: 'Geo Risk', type: 'agent', group: 'agent' },
  { id: 'ag-credit', label: 'Credit Analyst', type: 'agent', group: 'agent' },
  { id: 'ag-fx', label: 'FX Strategy', type: 'agent', group: 'agent' },
  { id: 'ag-commodity', label: 'Commodities', type: 'agent', group: 'agent' },
  { id: 'ag-retail', label: 'Retail Flow', type: 'agent', group: 'agent' },
  { id: 'ag-hedge', label: 'Hedge Fund PM', type: 'agent', group: 'agent' },
  { id: 'ag-super', label: 'Superannuation', type: 'agent', group: 'agent' },
  { id: 'ag-mining', label: 'Mining Analyst', type: 'agent', group: 'agent' },
  // Market context nodes
  { id: 'iron-ore', label: 'Iron Ore Futures', type: 'market', group: 'market' },
  { id: 'aud-usd', label: 'AUD/USD', type: 'market', group: 'market' },
  { id: 'china-pmi', label: 'China PMI', type: 'market', group: 'market' },
  { id: 'port-hedland', label: 'Port Hedland', type: 'chokepoint', group: 'geo' },
  { id: 'lombok', label: 'Lombok Strait', type: 'chokepoint', group: 'geo' },
  // Output node
  { id: 'prediction', label: 'Prediction', type: 'output', group: 'output' },
];

const buildGraphLinks = (ticker) => [
  // Event feeds agents
  { source: 'event', target: 'ag-macro' },
  { source: 'event', target: 'ag-quant' },
  { source: 'event', target: 'ag-geo' },
  { source: 'event', target: 'ag-credit' },
  { source: 'event', target: 'ag-fx' },
  { source: 'event', target: 'ag-commodity' },
  { source: 'event', target: 'ag-retail' },
  { source: 'event', target: 'ag-hedge' },
  { source: 'event', target: 'ag-super' },
  { source: 'event', target: 'ag-mining' },
  // Market context links
  { source: 'iron-ore', target: ticker },
  { source: 'aud-usd', target: ticker },
  { source: 'china-pmi', target: 'iron-ore' },
  { source: 'port-hedland', target: 'iron-ore' },
  { source: 'lombok', target: 'iron-ore' },
  { source: 'ag-commodity', target: 'iron-ore' },
  { source: 'ag-fx', target: 'aud-usd' },
  { source: 'ag-mining', target: ticker },
  { source: 'ag-macro', target: ticker },
  // Agents converge to prediction
  { source: 'ag-macro', target: 'prediction' },
  { source: 'ag-quant', target: 'prediction' },
  { source: 'ag-geo', target: 'prediction' },
  { source: 'ag-credit', target: 'prediction' },
  { source: 'ag-fx', target: 'prediction' },
  { source: 'ag-commodity', target: 'prediction' },
  { source: 'ag-retail', target: 'prediction' },
  { source: 'ag-hedge', target: 'prediction' },
  { source: 'ag-super', target: 'prediction' },
  { source: 'ag-mining', target: 'prediction' },
  { source: ticker, target: 'prediction' },
  { source: 'iron-ore', target: 'prediction' },
];

const NODE_COLORS = {
  event: '#ff0055',
  ticker: '#3b82f6',
  agent: '#a855f7',
  market: '#f97316',
  chokepoint: '#22c55e',
  output: '#eab308',
};

// ── Agent personas for the right panel ─────────────────────────────────────
const AGENT_PERSONAS = [
  {
    id: 1, name: 'Fund Manager', firm: 'BlackRock AU',
    focus: 'macro', tags: ['Macro', 'ASX'],
    desc: 'Macro-focused fund manager monitoring AUD exposure and commodity index weighting.',
  },
  {
    id: 2, name: 'Commodities Desk', firm: 'Macquarie',
    focus: 'iron_ore', tags: ['Iron Ore', 'Commodities'],
    desc: 'Tracks iron ore futures and Port Hedland throughput for near-term price signals.',
  },
  {
    id: 3, name: 'Quant Analyst', firm: 'Two Sigma',
    focus: 'quant', tags: ['Quant', 'Volatility'],
    desc: 'Statistical arbitrage model correlating geopolitical events with vol surface repricing.',
  },
  {
    id: 4, name: 'Geopolitical Risk', firm: 'Oxford Analytica',
    focus: 'geo', tags: ['Geopolitics', 'Risk'],
    desc: 'Event classification and causal chain modelling for supply disruption scenarios.',
  },
  {
    id: 5, name: 'FX Strategist', firm: 'ANZ Research',
    focus: 'fx', tags: ['FX', 'AUD/USD'],
    desc: 'AUD/USD transmission analysis — commodity linkage and carry trade positioning.',
  },
  {
    id: 6, name: 'Hedge Fund PM', firm: 'Citadel',
    focus: 'macro', tags: ['Macro', 'Hedge'],
    desc: 'Long/short positioning across ASX resources sector based on China demand signals.',
  },
  {
    id: 7, name: 'Mining Analyst', firm: 'RBC Capital',
    focus: 'mining', tags: ['Mining', 'BHP', 'RIO'],
    desc: 'Fundamental analysis of mining sector equities against shipping and port data.',
  },
  {
    id: 8, name: 'LNG Trader', firm: 'Woodside Energy',
    focus: 'lng', tags: ['LNG', 'Energy'],
    desc: 'LNG spot price and long-term contract exposure across Asia-Pacific markets.',
  },
  {
    id: 9, name: 'Superannuation CIO', firm: 'AustralianSuper',
    focus: 'macro', tags: ['Macro', 'Super'],
    desc: 'Long-horizon macro positioning, ESG overlays, and systematic rebalancing triggers.',
  },
  {
    id: 10, name: 'Retail Trader', firm: 'CommSec',
    focus: 'retail', tags: ['Retail', 'Sentiment'],
    desc: 'Retail order flow and sentiment signals from ASX retail investor activity.',
  },
];

const ALL_FOCUS_TAGS = ['All', 'Macro', 'Iron Ore', 'Quant', 'Geopolitics', 'FX', 'Hedge', 'Mining', 'LNG', 'Energy', 'Retail'];

const PHASES = [
  { step: 1, label: 'Knowledge Graph', desc: 'Building entity graph from event data' },
  { step: 2, label: 'Spawn Agents', desc: 'Seeding 45 market participant agents' },
  { step: 3, label: 'Round 1 Opinions', desc: 'Agents forming initial thesis' },
  { step: 4, label: 'Cross-Agent Debate', desc: 'Agents revising under peer pressure' },
  { step: 5, label: 'Consensus + Judge', desc: 'Tally votes, blind judge, reconciler' },
];

const TIME_PERIODS = [
  { label: 'Peak hours', range: '9:00 – 16:00 AEST', multiplier: '+1.5' },
  { label: 'Extended hours', range: '7:00 – 9:00', multiplier: '+0.8' },
  { label: 'Off-peak', range: '17:00 – 22:00', multiplier: '+0.4' },
  { label: 'Overnight', range: '22:00 – 7:00', multiplier: '×0.1' },
];

// ── Animated Knowledge Graph ────────────────────────────────────────────────
function KnowledgeGraph({ ticker, activeAgentCount, selectedNode, onSelectNode }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const width = svgRef.current.clientWidth || 600;
    const height = svgRef.current.clientHeight || 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const nodes = buildGraphNodes(ticker).map(n => ({ ...n }));
    const links = buildGraphLinks(ticker).map(l => ({ ...l }));

    // Defs for glow filter
    const defs = svg.append('defs');
    const filter = defs.append('filter').attr('id', 'glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');
    const feMerge = filter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'coloredBlur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-220))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(28));
    simRef.current = simulation;

    const linkGroup = svg.append('g').attr('class', 'links');
    const linkSel = linkGroup.selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#ff0055')
      .attr('stroke-opacity', 0.3)
      .attr('stroke-width', 1);

    const nodeGroup = svg.append('g').attr('class', 'nodes');
    const nodeSel = nodeGroup.selectAll('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        onSelectNode(d);
      });

    nodeSel.append('circle')
      .attr('r', d => d.group === 'core' || d.group === 'output' ? 14 : 9)
      .attr('fill', d => NODE_COLORS[d.type])
      .attr('fill-opacity', 0.85)
      .attr('stroke', d => NODE_COLORS[d.type])
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6)
      .attr('filter', 'url(#glow)');

    nodeSel.append('text')
      .text(d => d.label)
      .attr('dy', '0.35em')
      .attr('text-anchor', 'middle')
      .attr('y', d => (d.group === 'core' || d.group === 'output' ? 22 : 17))
      .attr('font-size', '9px')
      .attr('fill', '#888')
      .attr('pointer-events', 'none');

    simulation.on('tick', () => {
      linkSel
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [ticker, onSelectNode]);

  // Highlight active agent nodes as simulation progresses
  useEffect(() => {
    if (!svgRef.current) return;
    const agentNodes = svgRef.current.querySelectorAll('.nodes g circle');
    agentNodes.forEach((el, i) => {
      const d = d3.select(el).datum();
      if (d && d.group === 'agent') {
        const isActive = i <= activeAgentCount;
        d3.select(el)
          .attr('fill-opacity', isActive ? 1 : 0.25)
          .attr('stroke-opacity', isActive ? 1 : 0.15);
      }
    });
  }, [activeAgentCount]);

  return (
    <svg
      ref={svgRef}
      style={{ width: '100%', height: '100%', display: 'block' }}
      onClick={() => onSelectNode(null)}
    />
  );
}

// ── Node Detail Panel ───────────────────────────────────────────────────────
function NodeDetailPanel({ node, onClose }) {
  if (!node) return null;
  const typeLabel = node.type.charAt(0).toUpperCase() + node.type.slice(1);
  const color = NODE_COLORS[node.type] || '#888';
  return (
    <div className="sp-node-detail">
      <div className="sp-node-detail-header">
        <span className="sp-node-detail-title">Node Details</span>
        <span className="sp-node-type-badge" style={{ background: color + '22', color, border: `1px solid ${color}55` }}>{typeLabel}</span>
        <button className="sp-node-close" onClick={onClose}>✕</button>
      </div>
      <div className="sp-node-row"><span className="sp-node-key">Name</span><span className="sp-node-val">{node.label}</span></div>
      <div className="sp-node-row"><span className="sp-node-key">ID</span><span className="sp-node-val sp-mono">{node.id}</span></div>
      <div className="sp-node-row"><span className="sp-node-key">Group</span><span className="sp-node-val">{node.group}</span></div>
      <div className="sp-node-row"><span className="sp-node-key">Type</span><span className="sp-node-val">{node.type}</span></div>
    </div>
  );
}

// ── Main SimulationProgress ─────────────────────────────────────────────────
export default function SimulationProgress({ startTime, ticker = 'BHP.AX', minimized = false, onMinimize, onExpand }) {
  const [elapsed, setElapsed] = useState(0);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const [agentCount, setAgentCount] = useState(0);
  const [selectedNode, setSelectedNode] = useState(null);
  const [focusFilter, setFocusFilter] = useState('All');
  const [activeTab, setActiveTab] = useState('graph'); // 'graph' | 'dual' | 'workbench'

  const TOTAL_AGENTS = 45;
  const PHASE_SECONDS = useRef([0, 30, 90, 180, 270]);

  useEffect(() => {
    const timer = setInterval(() => {
      const s = Math.floor((Date.now() - startTime) / 1000);
      setElapsed(s);
      // Phase progression
      let pi = 0;
      for (let i = 0; i < PHASE_SECONDS.current.length; i++) {
        if (s >= PHASE_SECONDS.current[i]) pi = i;
      }
      setPhaseIdx(pi);
      // Agent ramp
      const pct = Math.min(s / 300, 1);
      setAgentCount(Math.floor(pct * TOTAL_AGENTS));
    }, 1000);
    return () => clearInterval(timer);
  }, [startTime]);

  const handleSelectNode = useCallback((node) => setSelectedNode(node), []);

  const filteredAgents = focusFilter === 'All'
    ? AGENT_PERSONAS
    : AGENT_PERSONAS.filter(a => a.tags.some(t => t === focusFilter));

  const mins = Math.floor(elapsed / 60);
  const secs = String(elapsed % 60).padStart(2, '0');

  // ── Minimized pill ──
  if (minimized) {
    return (
      <div className="sim-minimized" onClick={onExpand}>
        <span className="sp-pulse" />
        <span className="sp-mini-label">Simulating {ticker}</span>
        <span className="sp-mini-timer">{agentCount}/{TOTAL_AGENTS} agents</span>
        <span className="sp-mini-expand">↗</span>
      </div>
    );
  }

  const currentPhase = PHASES[phaseIdx] || PHASES[0];

  return (
    <div className="sp-overlay">
      <div className="sp-shell">

        {/* ── Top bar ── */}
        <div className="sp-topbar">
          <span className="sp-brand">MARKET ORACLE AI</span>
          <div className="sp-tabs">
            {['graph', 'dual', 'workbench'].map(t => (
              <button
                key={t}
                className={`sp-tab${activeTab === t ? ' active' : ''}`}
                onClick={() => setActiveTab(t)}
              >
                {t === 'graph' ? 'Graph' : t === 'dual' ? 'Dual Panel' : 'Workbench'}
              </button>
            ))}
          </div>
          <div className="sp-topbar-right">
            <span className="sp-step-label">Step {phaseIdx + 1}/{PHASES.length} · {currentPhase.label}</span>
            <span className="sp-status-badge">Running</span>
            <button className="sp-minimize-btn" onClick={onMinimize} title="Minimise">—</button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="sp-body">

          {/* ── LEFT: Graph panel ── */}
          <div className="sp-graph-panel">
            <div className="sp-panel-header">
              <span className="sp-panel-title">Knowledge Graph Visualization</span>
              <button className="sp-icon-btn" onClick={() => setSelectedNode(null)} title="Refresh">↺ Refresh</button>
            </div>
            <div className="sp-graph-canvas">
              <KnowledgeGraph
                ticker={ticker}
                activeAgentCount={agentCount}
                selectedNode={selectedNode}
                onSelectNode={handleSelectNode}
              />
              {selectedNode && (
                <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
              )}
            </div>
          </div>

          {/* ── RIGHT: Simulation panel ── */}
          <div className="sp-sim-panel">

            {/* Stats row */}
            <div className="sp-stats-row">
              <div className="sp-stat">
                <span className="sp-stat-val">{agentCount}</span>
                <span className="sp-stat-lbl">Active Agents</span>
              </div>
              <div className="sp-stat">
                <span className="sp-stat-val">{TOTAL_AGENTS - agentCount}</span>
                <span className="sp-stat-lbl">Pending Agents</span>
              </div>
              <div className="sp-stat">
                <span className="sp-stat-val">{AGENT_PERSONAS.length * 3 + phaseIdx}</span>
                <span className="sp-stat-lbl">Seed Signals</span>
              </div>
            </div>

            {/* Agent personas */}
            <div className="sp-section">
              <div className="sp-section-header">
                <span className="sp-section-num">0{phaseIdx + 1}</span>
                <span className="sp-section-title">Generated Agent Personas</span>
                <span className="sp-section-status">In progress</span>
              </div>
              <p className="sp-section-desc">
                Using LLM tools, seed each agent from the knowledge graph entities. Initialise model — give each real-world seed agent their unique behaviours and memory.
              </p>

              {/* Tag filters */}
              <div className="sp-tag-filters">
                {ALL_FOCUS_TAGS.map(tag => (
                  <button
                    key={tag}
                    className={`sp-tag-btn${focusFilter === tag ? ' active' : ''}`}
                    onClick={() => setFocusFilter(tag)}
                  >
                    {tag}
                  </button>
                ))}
              </div>

              {/* Agent cards */}
              <div className="sp-agent-cards">
                {filteredAgents.map(agent => (
                  <div key={agent.id} className="sp-agent-card">
                    <div className="sp-agent-card-header">
                      <span className="sp-agent-name">{agent.name}_{agent.id}</span>
                      <span className="sp-agent-type-badge">{agent.focus}</span>
                    </div>
                    <span className="sp-agent-firm">{agent.firm}</span>
                    <p className="sp-agent-desc">{agent.desc}</p>
                    <div className="sp-agent-tags">
                      {agent.tags.map(t => (
                        <span key={t} className="sp-agent-tag">{t}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Simulation config section */}
            <div className="sp-section">
              <div className="sp-section-header">
                <span className="sp-section-num">0{Math.min(phaseIdx + 2, 5)}</span>
                <span className="sp-section-title">Simulation Config</span>
                <span className="sp-section-status sp-done">Configured</span>
              </div>
              <p className="sp-section-desc">
                LLM sets simulation time, round length, and per-agent activity parameters based on ASX market session schedules.
              </p>
              <div className="sp-config-params">
                <div className="sp-config-param">
                  <span className="sp-config-lbl">Duration</span>
                  <span className="sp-config-val">{mins}:{secs}</span>
                </div>
                <div className="sp-config-param">
                  <span className="sp-config-lbl">Phase</span>
                  <span className="sp-config-val">{phaseIdx + 1}/{PHASES.length}</span>
                </div>
                <div className="sp-config-param">
                  <span className="sp-config-lbl">Ticker</span>
                  <span className="sp-config-val">{ticker}</span>
                </div>
                <div className="sp-config-param">
                  <span className="sp-config-lbl">Agents</span>
                  <span className="sp-config-val">{agentCount}/{TOTAL_AGENTS}</span>
                </div>
              </div>
              <div className="sp-time-table">
                {TIME_PERIODS.map(tp => (
                  <div key={tp.label} className="sp-time-row">
                    <span className="sp-time-label">{tp.label}</span>
                    <span className="sp-time-range">{tp.range}</span>
                    <span className="sp-time-mult">{tp.multiplier}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import * as d3 from 'd3';
import './SimulationProgress.css';

// ─── Graph data ───────────────────────────────────────────────────────────────
const makeNodes = (ticker) => [
  { id: 'event',   label: 'Event',    type: 'event'  },
  { id: 'ag1',     label: 'Macro',    type: 'agent'  },
  { id: 'ag2',     label: 'Quant',    type: 'agent'  },
  { id: 'ag3',     label: 'Geo Risk', type: 'agent'  },
  { id: 'ag4',     label: 'Credit',   type: 'agent'  },
  { id: 'ag5',     label: 'FX',       type: 'agent'  },
  { id: 'ag6',     label: 'Mining',   type: 'agent'  },
  { id: 'ag7',     label: 'Hedge',    type: 'agent'  },
  { id: 'ag8',     label: 'Retail',   type: 'agent'  },
  { id: 'iron',    label: 'Iron Ore', type: 'market' },
  { id: 'fx',      label: 'AUD/USD',  type: 'market' },
  { id: ticker,    label: ticker,     type: 'ticker' },
  { id: 'signal',  label: 'Signal',   type: 'output' },
];

const makeLinks = (ticker) => [
  { source: 'event',  target: 'ag1'    },
  { source: 'event',  target: 'ag2'    },
  { source: 'event',  target: 'ag3'    },
  { source: 'event',  target: 'ag4'    },
  { source: 'event',  target: 'ag5'    },
  { source: 'event',  target: 'ag6'    },
  { source: 'event',  target: 'ag7'    },
  { source: 'event',  target: 'ag8'    },
  { source: 'iron',   target: ticker   },
  { source: 'fx',     target: ticker   },
  { source: 'ag1',    target: 'signal' },
  { source: 'ag2',    target: 'signal' },
  { source: 'ag3',    target: 'signal' },
  { source: 'ag4',    target: 'signal' },
  { source: 'ag5',    target: 'signal' },
  { source: 'ag6',    target: 'signal' },
  { source: 'ag7',    target: 'signal' },
  { source: 'ag8',    target: 'signal' },
  { source: ticker,   target: 'signal' },
  { source: 'ag6',    target: 'iron'   },
  { source: 'ag5',    target: 'fx'     },
];

const NODE_R   = { event: 20, output: 18, ticker: 14, agent: 10, market: 11 };
const NODE_CLR = {
  event:  '#f472b6',
  output: '#e879f9',
  ticker: '#22d3ee',
  agent:  '#8b5cf6',
  market: '#c084fc',
};

const AGENT_IDS   = ['ag1','ag2','ag3','ag4','ag5','ag6','ag7','ag8'];
const AGENT_NAMES = {
  ag1:'Macro Desk', ag2:'Quant Engine', ag3:'Geo Risk',
  ag4:'Credit Desk', ag5:'FX Strategy', ag6:'Mining Analyst',
  ag7:'Hedge Fund', ag8:'Retail Flow',
};
const AGENT_FIRMS = {
  ag1:'BlackRock AU', ag2:'Two Sigma', ag3:'Oxford Analytica',
  ag4:"Moody's", ag5:'ANZ Research', ag6:'RBC Capital',
  ag7:'Citadel', ag8:'CommSec',
};
const ACTIONS = [
  'Analysing supply chain exposure',
  'Running DCF sensitivity model',
  'Flagging geopolitical risk score',
  'Cross-referencing China PMI data',
  'Calibrating vol surface model',
  'Updating iron ore demand signal',
  'Revising position thesis',
  'Forming consensus view',
  'Debating causal chain logic',
  'Reviewing market session data',
  'Reconciling opposing signals',
  'Aggregating agent consensus',
];

const PHASES = [
  { n: 1, label: 'Knowledge Graph',   sub: 'Building entity relationships from event data' },
  { n: 2, label: 'Agent Seeding',     sub: 'Initialising 45 market participant personas'   },
  { n: 3, label: 'Round 1 Opinions',  sub: 'Agents forming independent initial views'       },
  { n: 4, label: 'Cross-Debate',      sub: 'Agents challenging and revising each other'     },
  { n: 5, label: 'Final Consensus',   sub: 'Tallying votes and producing the signal'        },
];

// ─── Network Graph ────────────────────────────────────────────────────────────
function NetworkGraph({ ticker }) {
  const svgRef     = useRef(null);
  const simRef     = useRef(null);
  const debatesRef = useRef([]);
  const timerRef   = useRef(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const el = svgRef.current;
    const W  = el.clientWidth  || 800;
    const H  = el.clientHeight || 600;

    const svg = d3.select(el);
    svg.selectAll('*').remove();

    // ── Defs ──
    const defs = svg.append('defs');

    // Glow filters
    [
      ['glow-red',    '#f472b6', 6],
      ['glow-amber',  '#e879f9', 6],
      ['glow-cyan',   '#22d3ee', 5],
      ['glow-violet', '#8b5cf6', 4],
      ['glow-debate', '#e879f9', 8],
    ].forEach(([id, color, blur]) => {
      const f = defs.append('filter').attr('id', id)
        .attr('x','-60%').attr('y','-60%').attr('width','220%').attr('height','220%');
      f.append('feGaussianBlur').attr('in','SourceGraphic').attr('stdDeviation', blur).attr('result','b');
      const m = f.append('feMerge');
      m.append('feMergeNode').attr('in','b');
      m.append('feMergeNode').attr('in','SourceGraphic');
    });

    // Radial gradient for node fills
    const mkRadial = (id, color) => {
      const g = defs.append('radialGradient').attr('id', id);
      g.append('stop').attr('offset','0%').attr('stop-color', color).attr('stop-opacity', 1);
      g.append('stop').attr('offset','100%').attr('stop-color', color).attr('stop-opacity', 0.6);
    };
    Object.entries(NODE_CLR).forEach(([type, color]) => mkRadial(`grad-${type}`, color));

    // Animated debate gradient
    const dGrad = defs.append('linearGradient').attr('id','debate-grad').attr('gradientUnits','userSpaceOnUse');
    dGrad.append('stop').attr('offset','0%').attr('stop-color','#e879f9').attr('stop-opacity',0);
    dGrad.append('stop').attr('offset','50%').attr('stop-color','#e879f9').attr('stop-opacity',1);
    dGrad.append('stop').attr('offset','100%').attr('stop-color','#e879f9').attr('stop-opacity',0);

    // ── Radar background ──
    const bg = svg.append('g').attr('class','radar-bg');
    // Concentric rings
    [80,160,240,320].forEach(r => {
      bg.append('circle')
        .attr('cx', W/2).attr('cy', H/2).attr('r', r)
        .attr('fill','none')
        .attr('stroke','rgba(139,92,246,0.07)')
        .attr('stroke-width', 1);
    });
    // Cross hairs
    bg.append('line').attr('x1',W/2-340).attr('y1',H/2).attr('x2',W/2+340).attr('y2',H/2)
      .attr('stroke','rgba(139,92,246,0.06)').attr('stroke-width',1);
    bg.append('line').attr('x1',W/2).attr('y1',H/2-300).attr('x2',W/2).attr('y2',H/2+300)
      .attr('stroke','rgba(139,92,246,0.06)').attr('stroke-width',1);

    // ── Data ──
    const nodes = makeNodes(ticker).map(n => ({ ...n }));
    const links = makeLinks(ticker).map(l => ({ ...l }));

    // ── Edges ──
    const edgeG   = svg.append('g');
    const edgeSel = edgeG.selectAll('line').data(links).join('line')
      .attr('stroke','rgba(139,92,246,0.12)')
      .attr('stroke-width', 1);

    // ── Debate arc layer ──
    const debateG = svg.append('g');

    // ── Nodes ──
    const nodeG   = svg.append('g');
    const nodeSel = nodeG.selectAll('g').data(nodes).join('g');

    // Outer ring (halo)
    nodeSel.append('circle')
      .attr('class','node-halo')
      .attr('r', d => NODE_R[d.type] + 8)
      .attr('fill','none')
      .attr('stroke', d => NODE_CLR[d.type])
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.2);

    // Main circle
    nodeSel.append('circle')
      .attr('class','node-body')
      .attr('r', d => NODE_R[d.type])
      .attr('fill', d => `url(#grad-${d.type})`)
      .attr('stroke', d => NODE_CLR[d.type])
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.7);

    // Label
    nodeSel.append('text')
      .text(d => d.label)
      .attr('text-anchor','middle')
      .attr('dy', d => NODE_R[d.type] + 16)
      .attr('font-size','9px')
      .attr('font-family','ui-monospace,monospace')
      .attr('fill','rgba(226,232,240,0.45)')
      .attr('letter-spacing','0.5px')
      .attr('pointer-events','none');

    // Drag
    nodeSel.call(d3.drag()
      .on('start', (ev,d) => { if(!ev.active) simRef.current?.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag',  (ev,d) => { d.fx=ev.x; d.fy=ev.y; })
      .on('end',   (ev,d) => { if(!ev.active) simRef.current?.alphaTarget(0.15); d.fx=null; d.fy=null; })
    );

    // ── Simulation — always moving ──
    const turbulence = () => {
      nodes.forEach(n => {
        n.vx = (n.vx||0) + (Math.random()-0.5) * 0.7;
        n.vy = (n.vy||0) + (Math.random()-0.5) * 0.7;
      });
    };

    const sim = d3.forceSimulation(nodes)
      .force('link',      d3.forceLink(links).id(d=>d.id).distance(110).strength(0.28))
      .force('charge',    d3.forceManyBody().strength(-300))
      .force('center',    d3.forceCenter(W/2, H/2).strength(0.05))
      .force('collision', d3.forceCollide(30))
      .force('turbulence',turbulence)
      .alphaDecay(0)
      .alphaTarget(0.18)
      .velocityDecay(0.52);
    simRef.current = sim;

    // Arc helper — curved bezier
    const arc = (s,t) => {
      const mx = (s.x+t.x)/2 - (t.y-s.y)*0.4;
      const my = (s.y+t.y)/2 + (t.x-s.x)*0.4;
      return `M${s.x},${s.y} Q${mx},${my} ${t.x},${t.y}`;
    };

    // Debate arc DOM length tracker
    const arcLengths = {};

    sim.on('tick', () => {
      edgeSel
        .attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
        .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);

      nodeSel.attr('transform', d=>`translate(${d.x},${d.y})`);

      // Active debate IDs
      const now = Date.now();
      debatesRef.current = debatesRef.current.filter(db => now - db.at < 3000);
      const activeSet = new Set(debatesRef.current.flatMap(db=>[db.a,db.b]));

      // Node visual state
      nodeSel.select('.node-body')
        .attr('stroke-opacity', d => activeSet.size ? (activeSet.has(d.id) ? 1 : 0.25) : 0.7)
        .attr('fill-opacity',   d => activeSet.size ? (activeSet.has(d.id) ? 1 : 0.3) : 0.9)
        .attr('r', d => {
          const base = NODE_R[d.type];
          return activeSet.has(d.id) ? base * 1.4 : base;
        })
        .attr('filter', d => {
          if (!activeSet.has(d.id)) return null;
          const map = { event:'glow-red', output:'glow-amber', ticker:'glow-cyan', agent:'glow-violet', market:'glow-violet' };
          return `url(#${map[d.type] || 'glow-violet'})`;
        });

      nodeSel.select('.node-halo')
        .attr('stroke-opacity', d => activeSet.has(d.id) ? 0.7 : 0.12)
        .attr('r', d => (activeSet.has(d.id) ? NODE_R[d.type]*1.4 : NODE_R[d.type]) + 8);

      // Debate arcs
      debateG.selectAll('.darc').data(debatesRef.current, d=>d.id)
        .join(
          enter => {
            const p = enter.append('path').attr('class','darc')
              .attr('fill','none')
              .attr('stroke','#e879f9')
              .attr('stroke-linecap','round')
              .attr('filter','url(#glow-debate)');

            // Animate dash offset on enter
            p.each(function(db) {
              const na = nodes.find(n=>n.id===db.a);
              const nb = nodes.find(n=>n.id===db.b);
              if (!na||!nb) return;
              const d3el = d3.select(this);
              d3el.attr('d', arc(na,nb));
              const len = this.getTotalLength() || 200;
              arcLengths[db.id] = len;
              d3el.attr('stroke-dasharray',`${len*0.35} ${len*0.65}`)
                .attr('stroke-dashoffset', len)
                .attr('stroke-width', 2.5)
                .attr('stroke-opacity', 0.9)
                .transition().duration(2800).ease(d3.easeLinear)
                .attr('stroke-dashoffset', -len);
            });
            return p;
          },
          update => update
            .each(function(db) {
              const na = nodes.find(n=>n.id===db.a);
              const nb = nodes.find(n=>n.id===db.b);
              if (na&&nb) d3.select(this).attr('d', arc(na,nb));
            })
            .attr('stroke-opacity', db => {
              const age = now - db.at;
              return age > 2400 ? Math.max(0, 1 - (age-2400)/600) : 0.9;
            }),
          exit => exit.remove()
        );

      edgeSel
        .attr('stroke-opacity', d => {
          const sid = typeof d.source==='object' ? d.source.id : d.source;
          const tid = typeof d.target==='object' ? d.target.id : d.target;
          if (!activeSet.size) return 0.12;
          return (activeSet.has(sid) && activeSet.has(tid)) ? 0.5 : 0.04;
        })
        .attr('stroke', d => {
          const sid = typeof d.source==='object' ? d.source.id : d.source;
          const tid = typeof d.target==='object' ? d.target.id : d.target;
          return (activeSet.has(sid) && activeSet.has(tid)) ? '#e879f9' : 'rgba(139,92,246,0.12)';
        })
        .attr('stroke-width', d => {
          const sid = typeof d.source==='object' ? d.source.id : d.source;
          const tid = typeof d.target==='object' ? d.target.id : d.target;
          return (activeSet.has(sid) && activeSet.has(tid)) ? 1.5 : 1;
        });
    });

    // ── Debate scheduler ──
    const schedule = () => {
      timerRef.current = setTimeout(() => {
        const pool = [...AGENT_IDS];
        const a = pool.splice(Math.floor(Math.random()*pool.length), 1)[0];
        const b = pool[Math.floor(Math.random()*pool.length)];
        debatesRef.current.push({ id:`${a}-${b}-${Date.now()}`, a, b, at: Date.now() });
        simRef.current?.alpha(Math.min((simRef.current?.alpha()||0)+0.2, 0.6)).restart();
        schedule();
      }, 1600 + Math.random()*2000);
    };
    schedule();

    return () => { sim.stop(); clearTimeout(timerRef.current); };
  }, [ticker]);

  return <svg ref={svgRef} style={{width:'100%',height:'100%',display:'block'}} />;
}

// ─── Agent row ────────────────────────────────────────────────────────────────
function AgentRow({ id, name, firm, status, isDebating }) {
  return (
    <div className={`sp-agent-row ${isDebating ? 'debating' : ''}`}>
      <span className={`sp-agent-dot ${isDebating ? 'active' : 'idle'}`} />
      <div className="sp-agent-info">
        <span className="sp-agent-name">{name}</span>
        <span className="sp-agent-firm">{firm}</span>
      </div>
      <span className="sp-agent-status">{status}</span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function SimulationProgress({ startTime, ticker = 'BHP.AX', minimized = false, onMinimize, onExpand }) {
  const [elapsed,     setElapsed]     = useState(0);
  const [phaseIdx,    setPhaseIdx]    = useState(0);
  const [agentCount,  setAgentCount]  = useState(0);
  const [agentStates, setAgentStates] = useState({});
  const [consensus,   setConsensus]   = useState({ bull: 0, bear: 0, neut: 0 });
  const [debatingIds, setDebatingIds] = useState(new Set());

  const TOTAL    = 45;
  const PHASE_AT = [0, 30, 90, 180, 270];

  // Clock + phase + agent count
  useEffect(() => {
    const t = setInterval(() => {
      const s = Math.floor((Date.now() - startTime) / 1000);
      setElapsed(s);
      let pi = 0;
      PHASE_AT.forEach((at, i) => { if (s >= at) pi = i; });
      setPhaseIdx(pi);
      const count = Math.floor(Math.min(s/300, 1) * TOTAL);
      setAgentCount(count);
    }, 1000);
    return () => clearInterval(t);
  }, [startTime]);

  // Agent action rotation
  useEffect(() => {
    const t = setInterval(() => {
      const id  = AGENT_IDS[Math.floor(Math.random() * AGENT_IDS.length)];
      const act = ACTIONS[Math.floor(Math.random() * ACTIONS.length)];
      setAgentStates(prev => ({ ...prev, [id]: act }));
    }, 1400);
    return () => clearInterval(t);
  }, []);

  // Debate highlighting — sync with graph scheduler approx
  useEffect(() => {
    const t = setInterval(() => {
      const pool = [...AGENT_IDS];
      const a = pool.splice(Math.floor(Math.random()*pool.length),1)[0];
      const b = pool[Math.floor(Math.random()*pool.length)];
      setDebatingIds(new Set([a, b]));
      setTimeout(() => setDebatingIds(new Set()), 2800);
    }, 1800 + Math.random()*800);
    return () => clearInterval(t);
  }, []);

  // Consensus animation
  useEffect(() => {
    const t = setInterval(() => {
      const total = agentCount || 1;
      const bull  = Math.floor(30 + phaseIdx * 6 + Math.random() * 10);
      const neut  = Math.floor(8  + Math.random() * 8);
      const bear  = 100 - bull - neut;
      setConsensus({ bull, bear: Math.max(bear, 5), neut });
    }, 2000);
    return () => clearInterval(t);
  }, [agentCount, phaseIdx]);

  const mm  = String(Math.floor(elapsed / 60)).padStart(2,'0');
  const ss  = String(elapsed % 60).padStart(2,'0');
  const pct = Math.round((agentCount / TOTAL) * 100);
  const phase = PHASES[phaseIdx];

  if (minimized) {
    return (
      <div className="sp-pill" onClick={onExpand}>
        <span className="sp-pill-dot" />
        <span className="sp-pill-text">{ticker} · {agentCount}/{TOTAL} agents · {mm}:{ss}</span>
        <span className="sp-pill-arrow">↗</span>
      </div>
    );
  }

  return (
    <div className="sp-overlay">
      <div className="sp-shell">

        {/* ── Top bar ── */}
        <header className="sp-header">
          <div className="sp-header-left">
            <div className="sp-logo-dot" />
            <span className="sp-brand">MARKET ORACLE AI</span>
            <span className="sp-header-divider">|</span>
            <span className="sp-header-sub">Agent Network Intelligence</span>
          </div>
          <div className="sp-header-center">
            <span className="sp-live-dot" />
            <span className="sp-live-label">LIVE</span>
            <span className="sp-header-phase">{phase.label}</span>
          </div>
          <div className="sp-header-right">
            <span className="sp-header-step">Step {phaseIdx+1} / 5</span>
            <span className="sp-header-ticker">{ticker}</span>
            <button className="sp-min-btn" onClick={onMinimize}>—</button>
          </div>
        </header>

        {/* ── Body ── */}
        <div className="sp-body">

          {/* LEFT — network graph */}
          <div className="sp-graph-panel">
            <div className="sp-graph-label">AGENT KNOWLEDGE NETWORK</div>
            <NetworkGraph ticker={ticker} />
          </div>

          {/* RIGHT — control panel */}
          <div className="sp-control">

            {/* Progress row */}
            <div className="sp-progress-section">
              <div className="sp-progress-row">
                <span className="sp-progress-label">{agentCount} / {TOTAL} agents active</span>
                <span className="sp-progress-pct">{pct}%</span>
              </div>
              <div className="sp-progress-track">
                <div className="sp-progress-fill" style={{width:`${pct}%`}} />
              </div>
              <div className="sp-phase-sub">{phase.sub}</div>
            </div>

            {/* Agent activity board */}
            <div className="sp-board-section">
              <div className="sp-section-label">AGENT ACTIVITY BOARD</div>
              <div className="sp-agent-list">
                {AGENT_IDS.map(id => (
                  <AgentRow
                    key={id}
                    id={id}
                    name={AGENT_NAMES[id]}
                    firm={AGENT_FIRMS[id]}
                    status={agentStates[id] || 'Initialising…'}
                    isDebating={debatingIds.has(id)}
                  />
                ))}
              </div>
            </div>

            {/* Consensus tracker */}
            <div className="sp-consensus-section">
              <div className="sp-section-label">LIVE CONSENSUS</div>
              <div className="sp-bars">
                <div className="sp-bar-row">
                  <span className="sp-bar-name bull">BULLISH</span>
                  <div className="sp-bar-track">
                    <div className="sp-bar-fill bull" style={{width:`${consensus.bull}%`}} />
                  </div>
                  <span className="sp-bar-pct">{consensus.bull}%</span>
                </div>
                <div className="sp-bar-row">
                  <span className="sp-bar-name bear">BEARISH</span>
                  <div className="sp-bar-track">
                    <div className="sp-bar-fill bear" style={{width:`${consensus.bear}%`}} />
                  </div>
                  <span className="sp-bar-pct">{consensus.bear}%</span>
                </div>
                <div className="sp-bar-row">
                  <span className="sp-bar-name neut">NEUTRAL</span>
                  <div className="sp-bar-track">
                    <div className="sp-bar-fill neut" style={{width:`${consensus.neut}%`}} />
                  </div>
                  <span className="sp-bar-pct">{consensus.neut}%</span>
                </div>
              </div>
            </div>

            {/* Timer footer */}
            <div className="sp-footer">
              <div className="sp-timer-block">
                <span className="sp-timer-val">{mm}:{ss}</span>
                <span className="sp-timer-label">elapsed</span>
              </div>
              <div className="sp-footer-divider" />
              <div className="sp-footer-info">
                <span className="sp-footer-row">45 adversarial agents</span>
                <span className="sp-footer-row">3-round debate protocol</span>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}

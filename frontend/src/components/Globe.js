import React, { useEffect, useRef, useState } from 'react';
import Globe from 'globe.gl';
import './Globe.css';

const CHOKEPOINT_MARKERS = [
  { id: 'hormuz',        lat: 26.6,  lng: 56.3,   name: 'Hormuz',        risk: 85, color: '#ff2222', mbd: 20.9, cargo: 'Oil · LNG · LPG' },
  { id: 'malacca',       lat: 2.5,   lng: 101.5,  name: 'Malacca',       risk: 72, color: '#ff2222', mbd: 23.2, cargo: 'Iron ore · Oil · Coal' },
  { id: 'bab_el_mandeb', lat: 12.6,  lng: 43.4,   name: 'Bab el-Mandeb', risk: 65, color: '#ff8800', mbd: 4.2,  cargo: 'Oil · LNG · Containers' },
  { id: 'suez',          lat: 30.5,  lng: 32.3,   name: 'Suez',          risk: 58, color: '#ff8800', mbd: 4.9,  cargo: 'Oil · LNG · Containers' },
  { id: 'cape_good_hope',lat: -34.4, lng: 18.5,   name: 'Cape of Hope',  risk: 45, color: '#ffcc00', mbd: 9.1,  cargo: 'All cargo (fallback)' },
  { id: null,            lat: 9.1,   lng: -79.7,  name: 'Panama',        risk: 35, color: '#ffcc00', mbd: 3.8,  cargo: 'Containers · LNG' },
  { id: null,            lat: 41.1,  lng: 29.0,   name: 'Bosporus',      risk: 30, color: '#ffcc00', mbd: 2.9,  cargo: 'Oil · Grain' },
  { id: 'lombok',        lat: -8.7,  lng: 115.7,  name: 'Lombok',        risk: 20, color: '#44ff88', mbd: 1.5,  cargo: 'Iron ore (Malacca alt)' },
  { id: null,            lat: 55.5,  lng: 12.0,   name: 'Danish Straits',risk: 15, color: '#44ff88', mbd: 3.0,  cargo: 'Oil · LNG' },
];

function RiskGauge({ risk, color }) {
  // Semicircle gauge: total arc length ≈ π × 40 ≈ 125.66
  const total = Math.PI * 40;
  const filled = (risk / 100) * total;
  return (
    <svg viewBox="0 0 100 56" width="90" height="50" style={{ display: 'block' }}>
      <path d="M 10 50 A 40 40 0 0 1 90 50" stroke="#222" strokeWidth="9" fill="none" strokeLinecap="round" />
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        stroke={color}
        strokeWidth="9"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${total - filled}`}
      />
      <text x="50" y="46" textAnchor="middle" fill="white" fontSize="16" fontWeight="bold" fontFamily="monospace">{risk}</text>
      <text x="50" y="55" textAnchor="middle" fill="#555" fontSize="8" fontFamily="monospace">/100</text>
    </svg>
  );
}

function ChokepointGlobePopup({ cp, simScore, onSimulate, onClose, simulating }) {
  const riskLabel = cp.risk >= 70 ? 'CRITICAL' : cp.risk >= 50 ? 'HIGH' : cp.risk >= 35 ? 'ELEVATED' : 'MODERATE';
  const riskLabelColor = cp.risk >= 70 ? '#ff2222' : cp.risk >= 50 ? '#ff8800' : cp.risk >= 35 ? '#ffcc00' : '#44ff88';

  return (
    <div className="cp-globe-popup">
      <button className="cp-globe-close" onClick={onClose}>✕</button>

      {/* Header */}
      <div className="cp-globe-header">
        <span className="cp-globe-anchor">⚓</span>
        <div>
          <div className="cp-globe-name">{cp.name}</div>
          <div className="cp-globe-cargo">{cp.cargo}</div>
        </div>
        <span className="cp-globe-risk-badge" style={{ color: riskLabelColor, borderColor: riskLabelColor }}>
          {riskLabel}
        </span>
      </div>

      {/* Score gauge + last sim */}
      <div className="cp-globe-metrics">
        <div className="cp-globe-gauge">
          <div className="cp-globe-metric-label">RISK SCORE</div>
          <RiskGauge risk={cp.risk} color={cp.color} />
        </div>
        <div className="cp-globe-flow">
          <div className="cp-globe-metric-label">DAILY FLOW</div>
          <div className="cp-globe-flow-val" style={{ color: cp.color }}>{cp.mbd}mb/d</div>
          <div className="cp-globe-metric-label" style={{ marginTop: 8 }}>% GLOBAL SUPPLY</div>
          <div className="cp-globe-flow-val" style={{ color: '#aaa' }}>
            {cp.risk >= 70 ? '20-25' : cp.risk >= 50 ? '5-15' : cp.risk >= 35 ? '4-8' : '1-3'}%
          </div>
        </div>
      </div>

      {/* Last simulation result */}
      {simScore ? (
        <div className="cp-globe-last-sim">
          <div className="cp-globe-metric-label">LAST SIMULATION</div>
          <div className="cp-globe-sim-row">
            {simScore.topPredictions && simScore.topPredictions.slice(0, 3).map((p) => (
              <div key={p.ticker} className="cp-globe-sim-item">
                <span className="cp-globe-sim-ticker">{p.ticker.replace('.AX', '')}</span>
                <span className="cp-globe-sim-dir"
                  style={{ color: p.direction === 'UP' ? '#00ff88' : p.direction === 'DOWN' ? '#ff3366' : '#aaa' }}>
                  {p.direction === 'UP' ? '▲' : p.direction === 'DOWN' ? '▼' : '—'}
                  {' '}{Math.round(p.confidence * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="cp-globe-no-sim">No simulation run yet for this chokepoint</div>
      )}

      {/* Action */}
      {cp.id ? (
        <button
          className="cp-globe-sim-btn"
          onClick={onSimulate}
          disabled={simulating}
          style={{ opacity: simulating ? 0.6 : 1 }}
        >
          {simulating ? '⟳  Simulating ASX Impact…' : '▶  Simulate ASX Impact'}
        </button>
      ) : (
        <div className="cp-globe-no-sim" style={{ textAlign: 'center', marginTop: 6 }}>
          No ASX simulation available for this chokepoint
        </div>
      )}
    </div>
  );
}

function GlobeComponent({ events, portHedlandData, onEventClick, isSimulating, correlationArc, onChokepointSimulate, lastSimScores = {} }) {
  const globeRef = useRef(null);
  const globeInstanceRef = useRef(null);
  const [chokepointPopup, setChokepointPopup] = useState(null);
  const [simulating, setSimulating] = useState(false);

  // Use refs so globe.gl callbacks always call the latest function
  const setPopupRef = useRef(setChokepointPopup);
  setPopupRef.current = setChokepointPopup;

  const handleSimulate = async () => {
    if (!chokepointPopup?.id) return;
    setSimulating(true);
    try {
      if (onChokepointSimulate) {
        await onChokepointSimulate(chokepointPopup.id);
      }
    } finally {
      setSimulating(false);
      setChokepointPopup(null);
      // Resume rotation after simulation
      if (globeInstanceRef.current) {
        const controls = globeInstanceRef.current.controls();
        if (controls) controls.autoRotate = true;
      }
    }
  };

  const handlePopupClose = () => {
    setChokepointPopup(null);
    if (globeInstanceRef.current) {
      const controls = globeInstanceRef.current.controls();
      if (controls) controls.autoRotate = true;
    }
  };

  // Initialize globe ONCE on mount only
  useEffect(() => {
    if (!globeRef.current || globeInstanceRef.current) return;

    const globe = Globe()
      .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
      .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
      .width(globeRef.current.clientWidth)
      .height(globeRef.current.clientHeight)
      .atmosphereColor('rgba(30, 100, 255, 0.2)')
      .atmosphereAltitude(0.15)
      .pointLat(d => d.geometry.coordinates[1])
      .pointLng(d => d.geometry.coordinates[0])
      .pointColor(() => '#ff3333')
      .pointAltitude(0.02)
      .pointRadius(d => {
        const fatalities = d.properties?.fatalities || 0;
        return Math.max(0.3, Math.min(fatalities / 10, 1.2));
      })
      .pointLabel(d => `
        <div style="background: rgba(0,0,0,0.9); padding: 12px; border-radius: 8px; color: white; max-width: 250px;">
          <strong style="color: #ff3333;">${d.properties.event_type}</strong><br/>
          <strong>${d.properties.country}</strong><br/>
          ${d.properties.description}<br/>
          <small style="color: #aaa;">Fatalities: ${d.properties.fatalities} | ${d.properties.date}</small>
        </div>
      `)
      .onPointClick((point) => {
        if (!isSimulating && onEventClick) {
          onEventClick(point);
        }
      });

    // Auto-rotate
    const controls = globe.controls();
    if (controls) {
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.5;
    }

    globe(globeRef.current);
    globeInstanceRef.current = globe;

    const handleResize = () => {
      if (globeRef.current && globeInstanceRef.current) {
        globeInstanceRef.current
          .width(globeRef.current.clientWidth)
          .height(globeRef.current.clientHeight);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (globeRef.current) globeRef.current.innerHTML = '';
    };
  }, []);

  // Update events data
  useEffect(() => {
    if (globeInstanceRef.current && events && events.length > 0) {
      globeInstanceRef.current.pointsData(events);
    }
  }, [events]);

  // Pause rotation during simulation
  useEffect(() => {
    if (globeInstanceRef.current) {
      globeInstanceRef.current.enablePointerInteraction(!isSimulating);
      const controls = globeInstanceRef.current.controls();
      if (controls && !chokepointPopup) {
        controls.autoRotate = !isSimulating;
      }
    }
  }, [isSimulating]);

  // Port Hedland + chokepoint labels + click handler
  useEffect(() => {
    if (!globeInstanceRef.current) return;

    const labels = [
      { lat: -20.3, lng: 118.6, label: '⚓ Port Hedland', color: '#4488ff', isChokepoint: false },
      ...CHOKEPOINT_MARKERS.map(cp => ({
        lat: cp.lat,
        lng: cp.lng,
        label: `⬡ ${cp.name}`,
        color: cp.color,
        isChokepoint: true,
        cpData: cp,
      })),
    ];

    globeInstanceRef.current
      .labelsData(labels)
      .labelLat(d => d.lat)
      .labelLng(d => d.lng)
      .labelText(d => d.label)
      .labelSize(d => d.label.startsWith('⚓') ? 0.8 : 0.65)
      .labelColor(d => d.color)
      .labelResolution(2)
      .labelAltitude(0.01)
      .onLabelClick((label) => {
        if (!label.isChokepoint) return;
        // Stop rotation and show popup
        const controls = globeInstanceRef.current.controls();
        if (controls) controls.autoRotate = false;
        setPopupRef.current(label.cpData);
      });
  }, [portHedlandData]);

  // Chokepoint pulsing rings
  useEffect(() => {
    if (!globeInstanceRef.current) return;

    const rings = CHOKEPOINT_MARKERS.map(cp => ({
      lat: cp.lat,
      lng: cp.lng,
      color: cp.color,
      maxR: Math.max(1.5, cp.mbd / 8),
      propagationSpeed: cp.risk > 60 ? 3 : cp.risk > 40 ? 2 : 1,
      repeatPeriod: cp.risk > 60 ? 700 : cp.risk > 40 ? 1200 : 2000,
    }));

    globeInstanceRef.current
      .ringsData(rings)
      .ringLat(d => d.lat)
      .ringLng(d => d.lng)
      .ringColor(d => t => `${d.color}${Math.round((1 - t) * 255).toString(16).padStart(2, '0')}`)
      .ringMaxRadius(d => d.maxR)
      .ringPropagationSpeed(d => d.propagationSpeed)
      .ringRepeatPeriod(d => d.repeatPeriod);
  }, []);

  // Correlation arc overlay
  useEffect(() => {
    if (!globeInstanceRef.current) return;

    if (correlationArc && correlationArc.show) {
      const arcData = [{
        startLat: correlationArc.eventLat,
        startLng: correlationArc.eventLng,
        endLat: -25,
        endLng: 133,
        color: ['#ffd000', '#ffaa00'],
      }];
      globeInstanceRef.current
        .arcsData(arcData)
        .arcStartLat(d => d.startLat)
        .arcStartLng(d => d.startLng)
        .arcEndLat(d => d.endLat)
        .arcEndLng(d => d.endLng)
        .arcColor(d => d.color)
        .arcStroke(3)
        .arcDashLength(0.4)
        .arcDashGap(0.3)
        .arcDashAnimateTime(1500)
        .arcAltitude(0.25)
        .arcAltitudeAutoScale(0.6)
        .arcLabel(() => 'Market Impact Signal');
    } else {
      globeInstanceRef.current.arcsData([]);
    }
  }, [correlationArc]);

  return (
    <div className="globe-container">
      <div ref={globeRef} className="globe" />

      {/* Chokepoint popup — appears when user clicks a ⬡ label */}
      {chokepointPopup && (
        <ChokepointGlobePopup
          cp={chokepointPopup}
          simScore={lastSimScores[chokepointPopup.id] || null}
          onSimulate={handleSimulate}
          onClose={handlePopupClose}
          simulating={simulating}
        />
      )}

      {/* Hint shown when no popup is open */}
      {!chokepointPopup && (
        <div className="cp-globe-hint">Click ⬡ chokepoint to analyse</div>
      )}
    </div>
  );
}

export default GlobeComponent;

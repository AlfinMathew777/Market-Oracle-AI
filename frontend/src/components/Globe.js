import React, { useEffect, useRef } from 'react';
import Globe from 'globe.gl';
import './Globe.css';

const CHOKEPOINT_MARKERS = [
  { lat: 26.6,  lng: 56.3,   name: "Hormuz",        risk: 85, color: "#ff2222", mbd: 20.9 },
  { lat: 2.5,   lng: 101.5,  name: "Malacca",        risk: 72, color: "#ff2222", mbd: 23.2 },
  { lat: 12.6,  lng: 43.4,   name: "Bab el-Mandeb",  risk: 65, color: "#ff8800", mbd: 4.2  },
  { lat: 30.5,  lng: 32.3,   name: "Suez",           risk: 58, color: "#ff8800", mbd: 4.9  },
  { lat: -34.4, lng: 18.5,   name: "Cape of Hope",   risk: 45, color: "#ffcc00", mbd: 9.1  },
  { lat: 9.1,   lng: -79.7,  name: "Panama",         risk: 35, color: "#ffcc00", mbd: 3.8  },
  { lat: 41.1,  lng: 29.0,   name: "Bosporus",       risk: 30, color: "#ffcc00", mbd: 2.9  },
  { lat: -8.7,  lng: 115.7,  name: "Lombok",         risk: 20, color: "#44ff88", mbd: 1.5  },
  { lat: 55.5,  lng: 12.0,   name: "Danish Straits", risk: 15, color: "#44ff88", mbd: 3.0  },
];

function GlobeComponent({ events, portHedlandData, onEventClick, isSimulating, correlationArc }) {
  const globeRef = useRef(null);
  const globeInstanceRef = useRef(null);

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
        console.log('🎯 Globe point clicked:', point);
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

    // Handle window resize
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
      if (globeRef.current) {
        globeRef.current.innerHTML = '';
      }
    };
  }, []); // Empty dependency array - runs ONCE only

  // Separate useEffect to update data without rebinding events
  useEffect(() => {
    if (globeInstanceRef.current && events && events.length > 0) {
      globeInstanceRef.current.pointsData(events);
    }
  }, [events]); // Only re-runs when data changes

  // Update pointer interaction based on simulation state
  useEffect(() => {
    if (globeInstanceRef.current) {
      globeInstanceRef.current.enablePointerInteraction(!isSimulating);
      const controls = globeInstanceRef.current.controls();
      if (controls) {
        controls.autoRotate = !isSimulating;
      }
    }
  }, [isSimulating]);

  // Port Hedland + chokepoint labels
  useEffect(() => {
    if (!globeInstanceRef.current) return;

    const labels = [
      { lat: -20.3, lng: 118.6, label: '⚓ Port Hedland', color: '#4488ff' },
      ...CHOKEPOINT_MARKERS.map(cp => ({
        lat: cp.lat,
        lng: cp.lng,
        label: `⬡ ${cp.name}`,
        color: cp.color,
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
      .labelAltitude(0.01);
  }, [portHedlandData]);

  // Chokepoint pulsing rings — permanent, proportional to oil flow
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
    if (globeInstanceRef.current) {
      if (correlationArc && correlationArc.show) {
        const arcData = [{
          startLat: correlationArc.eventLat,
          startLng: correlationArc.eventLng,
          endLat: -25,  // Australian market anchor
          endLng: 133,
          color: ['#ffd000', '#ffaa00']  // Yellow gradient
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
        
        console.log('🔗 Correlation arc activated:', arcData[0]);
      } else {
        // Clear arcs when not active
        globeInstanceRef.current.arcsData([]);
      }
    }
  }, [correlationArc]);

  return (
    <div className="globe-container">
      <div ref={globeRef} className="globe" />
    </div>
  );
}

export default GlobeComponent;

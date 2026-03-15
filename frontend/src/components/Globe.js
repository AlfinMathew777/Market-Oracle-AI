import React, { useEffect, useRef } from 'react';
import Globe from 'globe.gl';
import './Globe.css';

function GlobeComponent({ events, portHedlandData, onEventClick, isSimulating }) {
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
    globe.controls().autoRotate = true;
    globe.controls().autoRotateSpeed = 0.5;

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
      if (globeInstanceRef.current.controls()) {
        globeInstanceRef.current.controls().autoRotate = !isSimulating;
      }
    }
  }, [isSimulating]);

  // Port Hedland marker
  useEffect(() => {
    if (globeInstanceRef.current && portHedlandData) {
      const portMarker = [{
        lat: -20.3,
        lng: 118.6,
        label: 'Port Hedland'
      }];

      globeInstanceRef.current
        .labelsData(portMarker)
        .labelLat(d => d.lat)
        .labelLng(d => d.lng)
        .labelText(d => d.label)
        .labelSize(0.8)
        .labelColor(() => '#4444ff')
        .labelResolution(2);
    }
  }, [portHedlandData]);

  return (
    <div className="globe-container">
      <div ref={globeRef} className="globe" />
    </div>
  );
}

export default GlobeComponent;

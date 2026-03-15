import React, { useEffect, useRef, useState } from 'react';
import Globe from 'globe.gl';
import './Globe.css';

function GlobeComponent({ events, portHedlandData, onEventClick, isSimulating }) {
  const globeEl = useRef();
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [popupPosition, setPopupPosition] = useState(null);

  useEffect(() => {
    if (!globeEl.current) return;

    // Initialize globe
    const globe = Globe()(globeEl.current)
      .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
      .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
      .width(globeEl.current.clientWidth)
      .height(globeEl.current.clientHeight)
      .atmosphereColor('lightskyblue')
      .atmosphereAltitude(0.15)
      .enablePointerInteraction(!isSimulating);

    // Auto-rotate when idle
    globe.controls().autoRotate = true;
    globe.controls().autoRotateSpeed = 0.5;

    // Render ACLED conflict events
    if (events && events.length > 0) {
      globe
        .pointsData(events)
        .pointLat(d => d.geometry.coordinates[1])
        .pointLng(d => d.geometry.coordinates[0])
        .pointColor(() => '#ff3333')
        .pointAltitude(0.01)
        .pointRadius(d => {
          const fatalities = d.properties.fatalities || 0;
          return Math.max(0.2, Math.min(fatalities / 20, 1.5));
        })
        .pointLabel(d => `
          <div style="background: rgba(0,0,0,0.9); padding: 12px; border-radius: 8px; color: white; max-width: 250px;">
            <strong style="color: #ff3333;">${d.properties.event_type}</strong><br/>
            <strong>${d.properties.country}</strong><br/>
            ${d.properties.description}<br/>
            <small style="color: #aaa;">Fatalities: ${d.properties.fatalities} | ${d.properties.date}</small>
          </div>
        `)
        .onPointClick((point, evt, coords) => {
          if (!isSimulating) {
            setSelectedEvent(point);
            // Calculate popup position - use evt (MouseEvent) not event
            const rect = globeEl.current.getBoundingClientRect();
            setPopupPosition({
              x: evt.clientX - rect.left,
              y: evt.clientY - rect.top
            });
            globe.controls().autoRotate = false;
          }
        });
    }

    // Port Hedland marker (if data available)
    if (portHedlandData) {
      const portMarker = [{
        lat: -20.3,
        lng: 118.6,
        size: 0.3,
        color: '#4444ff',
        label: 'Port Hedland'
      }];

      globe
        .labelsData(portMarker)
        .labelLat(d => d.lat)
        .labelLng(d => d.lng)
        .labelText(d => d.label)
        .labelSize(0.8)
        .labelColor(() => '#4444ff')
        .labelResolution(2);
    }

    // Handle window resize
    const handleResize = () => {
      if (globeEl.current) {
        globe
          .width(globeEl.current.clientWidth)
          .height(globeEl.current.clientHeight);
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [events, portHedlandData, isSimulating]);

  const handleSimulateClick = () => {
    if (selectedEvent && onEventClick) {
      onEventClick(selectedEvent);
      setSelectedEvent(null);
      setPopupPosition(null);
    }
  };

  const handleClosePopup = () => {
    setSelectedEvent(null);
    setPopupPosition(null);
  };

  return (
    <div className="globe-container">
      <div ref={globeEl} className="globe" />
      
      {selectedEvent && popupPosition && (
        <div
          className="event-popup"
          style={{
            left: `${popupPosition.x}px`,
            top: `${popupPosition.y}px`,
          }}
        >
          <button className="popup-close" onClick={handleClosePopup}>×</button>
          <h3>{selectedEvent.properties.event_type}</h3>
          <p><strong>{selectedEvent.properties.country}</strong></p>
          <p>{selectedEvent.properties.description}</p>
          <div className="popup-meta">
            <span>📅 {selectedEvent.properties.date}</span>
            <span>💀 {selectedEvent.properties.fatalities} fatalities</span>
          </div>
          <button className="simulate-btn" onClick={handleSimulateClick}>
            🔮 Simulate ASX Impact
          </button>
        </div>
      )}
    </div>
  );
}

export default GlobeComponent;

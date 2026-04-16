import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { geoMercator, geoPath } from 'd3-geo';
import { MapPin, Factory, Ship, Building2, Gem, Landmark } from 'lucide-react';
import './AustraliaMap.css';

// 3 floating macro data badges
const BADGE_POSITIONS = [
  {
    label: 'IRON ORE',
    valueKey: 'iron_ore',
    lat: -22.5,
    lon: 117.5, // Over Pilbara
    format: (data) => data?.label || 'N/A'
  },
  {
    label: 'AUD/USD',
    valueKey: 'aud_usd',
    lat: -30.0,
    lon: 136.0, // Center of Australia — neutral position
    format: (data) => data?.label || 'N/A'
  },
  {
    label: 'ASX 200',
    valueKey: 'asx_200',
    lat: -34.5,
    lon: 151.5, // Over Sydney
    format: (data) => {
      if (!data) return 'N/A';
      const value = data.value || 0;
      const change = data.change_pct || 0;
      const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '';
      return `${value.toLocaleString('en-AU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} ${arrow}`;
    }
  }
];

// Event to state impact mapping (matches backend ACLED event IDs)
const EVENT_STATE_IMPACT = {
  acled_001: { // Iran / Hormuz — LNG shipping
    'Western Australia': { color: '#ff4444', opacity: 0.45, reason: 'LNG export route disruption' },
    'Northern Territory': { color: '#ff6644', opacity: 0.35, reason: 'Darwin port shipping impact' },
    'Queensland': { color: '#ff8844', opacity: 0.25, reason: 'Gladstone LNG exposure' }
  },
  acled_002: { // DRC Lithium
    'Western Australia': { color: '#ff4444', opacity: 0.45, reason: 'Lithium processing — Kwinana' },
    'South Australia': { color: '#ff6644', opacity: 0.30, reason: 'Rare earth processing chain' }
  },
  acled_003: { // China Trade Policy — iron ore
    'Western Australia': { color: '#ff2222', opacity: 0.55, reason: 'Pilbara iron ore — China is 80% of exports' },
    'Northern Territory': { color: '#ff5544', opacity: 0.25, reason: 'Darwin port volumes' }
  },
  acled_004: { // Port Hedland Strike - MOST DRAMATIC
    'Western Australia': { color: '#ff0000', opacity: 0.60, reason: 'Direct — Port Hedland export halt' }
  },
  acled_005: { // RBA Rate Decision - Financial
    'New South Wales': { color: '#4488ff', opacity: 0.45, reason: 'ASX Sydney financial hub' },
    'Victoria': { color: '#5599ff', opacity: 0.35, reason: 'Melbourne banking sector' }
  },
  acled_006: { // Taiwan Strait — rare earths
    'Western Australia': { color: '#ff4444', opacity: 0.45, reason: 'LYC Mount Weld rare earth mine' },
    'Victoria': { color: '#4488ff', opacity: 0.25, reason: 'LYC Kalgoorlie processing' }
  },
  acled_007: { // Melbourne Property Crisis
    'Victoria': { color: '#ff4444', opacity: 0.50, reason: 'Melbourne property developer collapse' },
    'New South Wales': { color: '#ff6644', opacity: 0.30, reason: 'Sydney property contagion risk' }
  },
  acled_008: { // Red Sea / Sudan shipping
    'Western Australia': { color: '#ff4444', opacity: 0.35, reason: 'Export route rerouting cost' },
    'Queensland': { color: '#ff6644', opacity: 0.25, reason: 'Coal export rerouting' }
  },
  // NEW 2025-2026 EVENTS (Upgrade 3)
  acled_009: { // US Liberation Day tariffs
    'Western Australia': { color: '#ff6644', opacity: 0.40, reason: 'Steel & aluminum exports tariffed' },
    'New South Wales': { color: '#ff8844', opacity: 0.30, reason: 'Manufacturing exports impacted' },
    'Queensland': { color: '#ff9955', opacity: 0.25, reason: 'Coal export uncertainty' }
  },
  acled_010: { // China iron ore ban
    'Western Australia': { color: '#ff0000', opacity: 0.65, reason: 'Iron ore — 80% exports to China' },
    'Northern Territory': { color: '#ff4444', opacity: 0.35, reason: 'Darwin port China shipments' }
  },
  acled_011: { // ASEAN-India trade realignment
    'Western Australia': { color: '#ff5544', opacity: 0.35, reason: 'Critical minerals competition from India-Vietnam' },
    'South Australia': { color: '#ff7744', opacity: 0.25, reason: 'Rare earth processing re-routed' }
  },
  acled_012: { // RBA hike to 3.85%
    'New South Wales': { color: '#4488ff', opacity: 0.50, reason: 'Sydney banking NIM expansion (bullish banks)' },
    'Victoria': { color: '#5599ff', opacity: 0.45, reason: 'Melbourne banking & REIT pressure' },
    'Queensland': { color: '#6688ff', opacity: 0.25, reason: 'Brisbane property market cooling' }
  },
  acled_013: { // Taiwan semiconductor controls → rare earth surge
    'Western Australia': { color: '#44ff88', opacity: 0.50, reason: 'LYC rare earth demand spike (bullish)' },
    'Northern Territory': { color: '#66ff99', opacity: 0.30, reason: 'Rare earth export opportunity' }
  }
};

// 6 permanent location markers
const LOCATIONS = [
  {
    id: 'port-hedland',
    name: 'Port Hedland',
    lat: -20.31,
    lon: 118.58,
    icon: 'ship',
    description: 'Major iron ore export hub',
    type: 'port'
  },
  {
    id: 'pilbara',
    name: 'Pilbara Mining',
    lat: -22.0,
    lon: 117.5,
    icon: 'factory',
    description: 'Iron ore mining region',
    type: 'mining'
  },
  {
    id: 'gladstone',
    name: 'Gladstone LNG',
    lat: -23.84,
    lon: 151.26,
    icon: 'factory',
    description: 'LNG export terminal',
    type: 'lng'
  },
  {
    id: 'darwin',
    name: 'Darwin Port',
    lat: -12.46,
    lon: 130.84,
    icon: 'ship',
    description: 'China trade route',
    type: 'port'
  },
  {
    id: 'sydney',
    name: 'ASX Sydney',
    lat: -33.86,
    lon: 151.21,
    icon: 'building',
    description: 'Financial hub',
    type: 'financial'
  },
  {
    id: 'kalgoorlie',
    name: 'Kalgoorlie Gold',
    lat: -30.74,
    lon: 121.47,
    icon: 'gem',
    description: 'Gold mining',
    type: 'mining'
  }
];

const BACKEND_URL_MAP = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

// State abbreviation to full name mapping
const STATE_NAME_MAP = {
  WA: 'Western Australia',
  QLD: 'Queensland',
  NSW: 'New South Wales',
  NT: 'Northern Territory',
  SA: 'South Australia',
  VIC: 'Victoria',
  TAS: 'Tasmania',
};

const AustraliaMap = ({ portHedlandData, selectedEvent, onEventClick, prediction }) => {
  const svgRef = useRef(null);
  const [geoData, setGeoData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [chokepointStateImpact, setChokepointStateImpact] = useState(null);
  const [stateTooltip, setStateTooltip] = useState(null);
  const [macroData, setMacroData] = useState(null);
  const [sentimentArrow, setSentimentArrow] = useState(null); // { fromLat, fromLon, direction }

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Load macro context data
  useEffect(() => {
    fetchMacroData();
    const interval = setInterval(fetchMacroData, 300000); // 5 min refresh
    return () => clearInterval(interval);
  }, []);

  const fetchMacroData = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/data/macro-context`);
      const result = await response.json();
      if (result.status === 'success') {
        setMacroData(result.data);
      }
    } catch (err) {
      console.error('Error fetching macro data for badges:', err);
    }
  };

  // Trigger sentiment arrow when prediction completes
  useEffect(() => {
    if (prediction && selectedEvent && selectedEvent.geometry) {
      const coords = selectedEvent.geometry.coordinates;
      setSentimentArrow({
        fromLat: coords[1],
        fromLon: coords[0],
        direction: prediction.direction
      });

      // Auto-remove after 10 seconds
      const timer = setTimeout(() => {
        setSentimentArrow(null);
      }, 10000);

      return () => clearTimeout(timer);
    }
  }, [prediction, selectedEvent]);

  // Helper function to get state fill based on selected event OR live chokepoint data
  const getStateFill = (stateName) => {
    // Priority 1: event-driven coloring when a simulation is active
    if (selectedEvent && selectedEvent.properties && selectedEvent.properties.id) {
      const eventId = selectedEvent.properties.id;
      const eventImpacts = EVENT_STATE_IMPACT[eventId];
      if (eventImpacts) {
        const impact = eventImpacts[stateName];
        if (impact) {
          return { color: impact.color, opacity: impact.opacity, reason: impact.reason };
        }
      }
    }

    // Priority 2: live chokepoint heatmap (background always-on layer)
    if (chokepointStateImpact) {
      const stateAbbr = Object.keys(STATE_NAME_MAP).find(
        k => STATE_NAME_MAP[k] === stateName
      );
      const score = stateAbbr ? (chokepointStateImpact[stateAbbr] || 0) : 0;
      if (score > 0) {
        const intensity = score / 100;
        const r = Math.round(255 * intensity);
        const g = Math.round(30 * (1 - intensity));
        const b = Math.round(30 * (1 - intensity));
        const reason = score > 70
          ? `${stateName}: ${score}/100 risk — active chokepoint disruption affecting exports`
          : `${stateName}: ${score}/100 — chokepoint monitoring active`;
        return {
          color: `rgb(${r},${g},${b})`,
          opacity: 0.15 + intensity * 0.35,
          reason,
        };
      }
    }

    return { color: 'rgba(20, 30, 50, 0.6)', opacity: 1, reason: null };
  };

  // Load GeoJSON data
  useEffect(() => {
    fetch('/australia-states.geojson')
      .then(res => res.json())
      .then(data => {
        setGeoData(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error loading Australia GeoJSON:', err);
        setLoading(false);
      });
  }, []);

  // Fetch live chokepoint state impact data
  useEffect(() => {
    const fetchChokepointImpact = async () => {
      try {
        const res = await fetch(`${BACKEND_URL_MAP}/api/data/chokepoints?enriched=false`);
        const json = await res.json();
        if (json.status === 'success') {
          // Find highest-risk chokepoints and compute state heatmap
          const chokepoints = json.data.chokepoints;
          const activeDisrupted = Object.keys(chokepoints).filter(
            id => chokepoints[id].risk_score > 45
          );
          if (activeDisrupted.length > 0) {
            const impactRes = await fetch(
              `${BACKEND_URL_MAP}/api/data/chokepoint-impact?chokepoints=${activeDisrupted.join(',')}&duration_days=7`
            );
            const impactJson = await impactRes.json();
            if (impactJson.status === 'success') {
              setChokepointStateImpact(impactJson.data.state_heatmap);
            }
          }
        }
      } catch (err) {
        console.error('Chokepoint impact fetch error:', err);
      }
    };
    fetchChokepointImpact();
    const interval = setInterval(fetchChokepointImpact, 300000);
    return () => clearInterval(interval);
  }, []);

  // Render map when data is ready or selectedEvent changes
  useEffect(() => {
    if (!geoData || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove(); // Clear previous render

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // Set SVG attributes
    svg.attr('viewBox', `0 0 ${width} ${height}`)
       .attr('width', width)
       .attr('height', height);

    // Create projection centered on Australia
    const projection = geoMercator()
      .center([133, -27]) // Center of Australia
      .scale(width * 0.9)
      .translate([width / 2, height / 2]);

    const path = geoPath().projection(projection);

    // Create groups
    const mapGroup = svg.append('g').attr('class', 'map-group');
    const markersGroup = svg.append('g').attr('class', 'markers-group');

    // Render state boundaries with dynamic colors
    mapGroup
      .selectAll('path')
      .data(geoData.features)
      .enter()
      .append('path')
      .attr('d', path)
      .attr('class', 'state-boundary')
      .attr('data-state', d => d.properties.STATE_NAME)
      .each(function(d) {
        const stateName = d.properties.STATE_NAME;
        const fillData = getStateFill(stateName);
        
        d3.select(this)
          .attr('fill', fillData.color)
          .attr('fill-opacity', fillData.opacity)
          .attr('stroke', 'rgba(51, 102, 255, 0.4)')
          .attr('stroke-width', 1.5)
          .style('transition', 'fill 0.6s ease, fill-opacity 0.6s ease');
      })
      .on('mouseenter', function(event, d) {
        const stateName = d.properties.STATE_NAME;
        const fillData = getStateFill(stateName);
        
        if (fillData.reason) {
          // Show tooltip
          const [x, y] = d3.pointer(event);
          setStateTooltip({
            x,
            y,
            stateName,
            reason: fillData.reason
          });
        }
        
        // Brighten on hover
        d3.select(this).attr('stroke', 'rgba(102, 153, 255, 0.8)').attr('stroke-width', 2);
      })
      .on('mouseleave', function() {
        setStateTooltip(null);
        d3.select(this).attr('stroke', 'rgba(51, 102, 255, 0.4)').attr('stroke-width', 1.5);
      });

    // Render location markers
    LOCATIONS.forEach(location => {
      const [x, y] = projection([location.lon, location.lat]);
      
      if (x && y) {
        const markerGroup = markersGroup
          .append('g')
          .attr('class', `location-marker marker-${location.type}`)
          .attr('data-location-id', location.id)
          .attr('transform', `translate(${x}, ${y})`)
          .style('cursor', 'pointer');

        // Marker circle background
        markerGroup
          .append('circle')
          .attr('r', 8)
          .attr('fill', location.type === 'port' ? '#3366ff' : 
                        location.type === 'financial' ? '#6699ff' : 
                        '#ff9933')
          .attr('stroke', '#ffffff')
          .attr('stroke-width', 2)
          .attr('opacity', 0.9);

        // Marker pulse effect
        markerGroup
          .append('circle')
          .attr('r', 8)
          .attr('fill', 'none')
          .attr('stroke', location.type === 'port' ? '#3366ff' : 
                          location.type === 'financial' ? '#6699ff' : 
                          '#ff9933')
          .attr('stroke-width', 2)
          .attr('opacity', 0.6)
          .attr('class', 'marker-pulse');

        // Store location data for React rendering (labels will be DOM elements)
        markerGroup.datum(location);
      }
    });

  }, [geoData, selectedEvent]); // Re-render when selectedEvent changes

  const getIconComponent = (iconType) => {
    switch (iconType) {
      case 'ship': return Ship;
      case 'factory': return Factory;
      case 'building': return Building2;
      case 'gem': return Gem;
      default: return MapPin;
    }
  };

  if (loading) {
    return (
      <div className="australia-map-container" data-testid="australia-map">
        <div className="map-loading">Loading Australia map...</div>
      </div>
    );
  }

  return (
    <div className="australia-map-container" data-testid="australia-map">
      <svg ref={svgRef} className="australia-map-svg" preserveAspectRatio="xMidYMid meet">
        {/* Sentiment flow arrow overlay */}
        {sentimentArrow && svgRef.current && (() => {
          const width = svgRef.current.clientWidth || 800;
          const height = svgRef.current.clientHeight || 600;
          
          const projection = geoMercator()
            .center([133, -27])
            .scale(width * 0.9)
            .translate([width / 2, height / 2]);
          
          const [x1, y1] = projection([sentimentArrow.fromLon, sentimentArrow.fromLat]);
          const [x2, y2] = projection([151.21, -33.86]); // ASX Sydney
          
          const midX = (x1 + x2) / 2;
          const midY = Math.min(y1, y2) - 80; // Arc above
          
          const color = sentimentArrow.direction === 'DOWN' ? '#ff4444' : '#44ff88';
          const pathD = `M ${x1} ${y1} Q ${midX} ${midY} ${x2} ${y2}`;
          
          return (
            <path
              d={pathD}
              fill="none"
              stroke={color}
              strokeWidth="3"
              strokeDasharray="8 4"
              opacity="0.8"
              className="sentiment-arrow"
              style={{
                filter: `drop-shadow(0 0 4px ${color})`
              }}
            />
          );
        })()}
      </svg>
      
      {/* State impact tooltip */}
      {stateTooltip && (
        <div
          className="state-tooltip"
          data-testid="state-tooltip"
          style={{
            left: `${stateTooltip.x + 15}px`,
            top: `${stateTooltip.y - 10}px`
          }}
        >
          <div className="tooltip-state">{stateTooltip.stateName}</div>
          <div className="tooltip-reason">{stateTooltip.reason}</div>
        </div>
      )}
      
      {/* Render labels as DOM overlays */}
      <div className="map-labels-overlay">
        {LOCATIONS.map(location => {
          // Calculate position using same projection
          const projection = geoMercator()
            .center([133, -27])
            .scale((svgRef.current?.clientWidth || 800) * 0.9)
            .translate([
              (svgRef.current?.clientWidth || 800) / 2,
              (svgRef.current?.clientHeight || 600) / 2
            ]);
          
          const [x, y] = projection([location.lon, location.lat]);
          const Icon = getIconComponent(location.icon);
          
          return (
            <div
              key={location.id}
              className={`map-label ${location.type}`}
              data-testid={`marker-${location.id}`}
              style={{
                left: `${x}px`,
                top: `${y}px`,
                transform: 'translate(-50%, -100%)'
              }}
            >
              <div className="label-icon">
                <Icon size={14} />
              </div>
              <div className="label-text">
                {location.name}
                {location.id === 'port-hedland' && portHedlandData && (
                  <span className={`congestion-mini ${portHedlandData.congestion_level.toLowerCase()}`}>
                    {portHedlandData.congestion_level} · {portHedlandData.vessel_count}v
                  </span>
                )}
              </div>
            </div>
          );
        })}

        {/* Floating macro data badges */}
        {macroData && BADGE_POSITIONS.map(badge => {
          const projection = geoMercator()
            .center([133, -27])
            .scale((svgRef.current?.clientWidth || 800) * 0.9)
            .translate([
              (svgRef.current?.clientWidth || 800) / 2,
              (svgRef.current?.clientHeight || 600) / 2
            ]);
          
          const [x, y] = projection([badge.lon, badge.lat]);
          const badgeData = macroData[badge.valueKey];
          const displayValue = badge.format(badgeData);
          
          return (
            <div
              key={badge.valueKey}
              className="macro-badge"
              data-testid={`macro-badge-${badge.valueKey}`}
              style={{
                left: `${x}px`,
                top: `${y}px`,
                transform: 'translate(-50%, -50%)'
              }}
            >
              <div className="badge-label">{badge.label}</div>
              <div className="badge-value">{displayValue}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AustraliaMap;

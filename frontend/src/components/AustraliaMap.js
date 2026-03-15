import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { geoMercator, geoPath } from 'd3-geo';
import { MapPin, Factory, Ship, Building2, Gem, Landmark } from 'lucide-react';
import './AustraliaMap.css';

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

const AustraliaMap = ({ portHedlandData, selectedEvent, onEventClick }) => {
  const svgRef = useRef(null);
  const [geoData, setGeoData] = useState(null);
  const [loading, setLoading] = useState(true);

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

  // Render map when data is ready
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

    // Render state boundaries
    mapGroup
      .selectAll('path')
      .data(geoData.features)
      .enter()
      .append('path')
      .attr('d', path)
      .attr('class', 'state-boundary')
      .attr('data-state', d => d.properties.STATE_NAME)
      .attr('fill', 'rgba(20, 30, 50, 0.6)')
      .attr('stroke', 'rgba(51, 102, 255, 0.4)')
      .attr('stroke-width', 1.5)
      .on('mouseenter', function() {
        d3.select(this).attr('fill', 'rgba(30, 40, 60, 0.8)');
      })
      .on('mouseleave', function() {
        d3.select(this).attr('fill', 'rgba(20, 30, 50, 0.6)');
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

  }, [geoData]);

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
      </svg>
      
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
      </div>
    </div>
  );
};

export default AustraliaMap;

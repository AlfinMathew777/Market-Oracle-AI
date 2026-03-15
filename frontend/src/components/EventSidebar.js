import React from 'react';
import './EventSidebar.css';

function EventSidebar({ events, onEventSelect, isSimulating }) {
  if (!events || events.length === 0) {
    return (
      <div className="event-sidebar">
        <div className="sidebar-header">LIVE INTELLIGENCE FEED</div>
        <div className="loading-events">Loading events...</div>
      </div>
    );
  }

  const handleEventClick = (event) => {
    if (!isSimulating && onEventSelect) {
      onEventSelect(event);
    }
  };

  return (
    <div className="event-sidebar">
      <div className="sidebar-header">LIVE INTELLIGENCE FEED</div>
      <div className="sidebar-subtitle">{events.length} Active Signals</div>
      
      <div className="events-list">
        {events.map((event) => (
          <div
            key={event.properties.id}
            className={`event-card ${isSimulating ? 'disabled' : ''}`}
            onClick={() => handleEventClick(event)}
          >
            <div className="event-country">{event.properties.country.toUpperCase()}</div>
            <div className="event-description">{event.properties.description}</div>
            <div className="event-meta">
              <span>{event.properties.event_type}</span>
              <span>·</span>
              <span>{event.properties.date}</span>
              {event.properties.fatalities > 0 && (
                <>
                  <span>·</span>
                  <span>{event.properties.fatalities} casualties</span>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      
      <div className="sidebar-footer">
        <small>Click any event to trigger ASX prediction</small>
      </div>
    </div>
  );
}

export default EventSidebar;

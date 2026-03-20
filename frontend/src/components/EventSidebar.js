import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, AlertCircle, Activity, Newspaper } from 'lucide-react';
import './EventSidebar.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function EventSidebar({ events, onEventSelect, isSimulating, selectedEvent }) {
  const [preSimContext, setPreSimContext] = useState(null);
  const [loadingContext, setLoadingContext] = useState(false);
  const [relatedNews, setRelatedNews] = useState([]);
  const [loadingNews, setLoadingNews] = useState(false);

  // Fetch pre-simulation context + related news when an event is selected
  useEffect(() => {
    if (!selectedEvent) {
      setPreSimContext(null);
      setRelatedNews([]);
      return;
    }

    fetchPreSimulationContext(selectedEvent);
    fetchRelatedNews(selectedEvent);
  }, [selectedEvent]);

  const fetchPreSimulationContext = async (event) => {
    setLoadingContext(true);
    
    try {
      // Determine relevant tickers based on event
      const tickers = inferTickersFromEvent(event);
      const topic = event.properties.description || event.properties.event_type;
      
      const response = await fetch(
        `${BACKEND_URL}/api/data/pre-simulation-sentiment?tickers=${tickers.join(',')}&topic=${encodeURIComponent(topic)}`
      );
      
      const result = await response.json();
      
      if (result.status === 'success') {
        setPreSimContext(result.data);
      }
    } catch (err) {
      console.error('Error fetching pre-simulation context:', err);
    } finally {
      setLoadingContext(false);
    }
  };

  const fetchRelatedNews = async (event) => {
    setLoadingNews(true);
    setRelatedNews([]);
    try {
      const country = event.properties.country || '';
      const eventType = event.properties.event_type || '';
      const query = encodeURIComponent(`${country} ${eventType}`);
      const res = await fetch(`${BACKEND_URL}/api/data/news?query=${query}&limit=4`);
      const result = await res.json();
      if (result.status === 'success' && Array.isArray(result.data)) {
        setRelatedNews(result.data.slice(0, 4));
      }
    } catch (err) {
      console.error('Error fetching related news:', err);
    } finally {
      setLoadingNews(false);
    }
  };

  const inferTickersFromEvent = (event) => {
    // Simple heuristic to map events to relevant tickers
    const notes = (event.properties.notes || '').toLowerCase();
    const description = (event.properties.description || '').toLowerCase();
    const combined = notes + ' ' + description;
    
    const tickers = [];
    
    // Iron ore events -> BHP, RIO, FMG
    if (combined.includes('iron ore') || combined.includes('port hedland') || combined.includes('pilbara')) {
      tickers.push('BHP.AX', 'RIO.AX', 'FMG.AX');
    }
    // Rare earth / lithium -> LYC
    else if (combined.includes('rare earth') || combined.includes('lithium') || combined.includes('semiconductor')) {
      tickers.push('LYC.AX');
    }
    // Banking / rate events -> CBA
    else if (combined.includes('rate') || combined.includes('rba') || combined.includes('banking') || combined.includes('monetary')) {
      tickers.push('CBA.AX');
    }
    // Default to major resource stocks
    else {
      tickers.push('BHP.AX', 'RIO.AX');
    }
    
    return tickers;
  };

  const renderPreSimulationSignal = () => {
    if (!selectedEvent) return null;
    
    if (loadingContext) {
      return (
        <div className="pre-sim-signal loading" data-testid="pre-sim-signal-loading">
          <div className="signal-header">
            <Activity size={14} className="signal-icon spinning" />
            <span>ANALYZING SENTIMENT...</span>
          </div>
        </div>
      );
    }
    
    if (!preSimContext) return null;
    
    const { combined_sentiment_bias, signal_strength, gdelt_signal, news_signal } = preSimContext;
    
    // Determine signal direction
    let signalClass = 'neutral';
    let SignalIcon = AlertCircle;
    let signalLabel = 'NEUTRAL';
    
    if (combined_sentiment_bias > 0.2) {
      signalClass = 'bullish';
      SignalIcon = TrendingUp;
      signalLabel = 'BULLISH';
    } else if (combined_sentiment_bias < -0.2) {
      signalClass = 'bearish';
      SignalIcon = TrendingDown;
      signalLabel = 'BEARISH';
    }
    
    return (
      <div className={`pre-sim-signal ${signalClass}`} data-testid="pre-sim-signal">
        <div className="signal-header">
          <SignalIcon size={14} className="signal-icon" />
          <span>PRE-SIMULATION SIGNAL</span>
        </div>
        
        <div className="signal-main">
          <div className="signal-label">{signalLabel}</div>
          <div className="signal-bias">{combined_sentiment_bias >= 0 ? '+' : ''}{(combined_sentiment_bias * 100).toFixed(1)}%</div>
          <div className="signal-strength">{signal_strength}</div>
        </div>
        
        <div className="signal-sources">
          <div className="signal-source">
            <span className="source-label">GDELT</span>
            <span className="source-value">
              {gdelt_signal.article_count || 0} articles · tone {gdelt_signal.avgtone || 0}
            </span>
          </div>
          <div className="signal-source">
            <span className="source-label">MarketAux</span>
            <span className="source-value">
              {news_signal.article_count || 0} articles · {news_signal.signal || 'N/A'}
            </span>
          </div>
        </div>
        
        <div className="signal-note">
          Combined geopolitical + news sentiment before simulation
        </div>
      </div>
    );
  };

  const renderRelatedNews = () => {
    if (!selectedEvent) return null;

    return (
      <div className="related-news" data-testid="related-news">
        <div className="related-news-header">
          <Newspaper size={13} />
          <span>RELATED NEWS</span>
        </div>
        {loadingNews ? (
          <div className="related-news-loading">Loading articles...</div>
        ) : relatedNews.length === 0 ? (
          <div className="related-news-empty">No recent articles found</div>
        ) : (
          <ul className="related-news-list">
            {relatedNews.map((article, i) => (
              <li key={i} className="related-news-item">
                {article.url ? (
                  <a href={article.url} target="_blank" rel="noopener noreferrer" className="related-news-link">
                    {article.title}
                  </a>
                ) : (
                  <span>{article.title}</span>
                )}
                {article.source && (
                  <span className="related-news-source">{article.source}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  if (!events || events.length === 0) {
    return (
      <div className="event-sidebar">
        <div className="sidebar-header">AUSTRALIAN IMPACT FEED</div>
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
      <div className="sidebar-header">AUSTRALIAN IMPACT FEED</div>
      <div className="sidebar-subtitle">{events.length} Global Events Affecting ASX</div>
      
      {renderPreSimulationSignal()}

      {renderRelatedNews()}

      <div className="events-list">
        {events.map((event) => (
          <div
            key={event.properties.id}
            className={`event-card ${isSimulating ? 'disabled' : ''}`}
            onClick={() => handleEventClick(event)}
            data-testid={`event-card-${event.properties.id}`}
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
        <small>Click any event to see ASX market impact prediction</small>
      </div>
    </div>
  );
}

export default EventSidebar;

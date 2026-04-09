import React, { useState, useEffect, useCallback } from 'react';
import './NewsDashboard.css';

const CATEGORY_ICONS = {
  commodity:    '🛢️',
  monetary:     '🏦',
  currency:     '💱',
  earnings:     '📊',
  corporate:    '🏢',
  geopolitical: '🌏',
  macro:        '📈',
  regulatory:   '⚖️',
  global:       '🌐',
  sector:       '🏭',
};

const CATEGORY_COLORS = {
  commodity:    '#f59e0b',
  monetary:     '#3b82f6',
  currency:     '#10b981',
  earnings:     '#8b5cf6',
  corporate:    '#6366f1',
  geopolitical: '#ef4444',
  macro:        '#14b8a6',
  regulatory:   '#f97316',
  global:       '#6b7280',
  sector:       '#ec4899',
};

export default function NewsDashboard({ apiKey }) {
  const [news, setNews] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);

  const fetchNews = useCallback(async () => {
    try {
      setLoading(true);

      const headers = {};
      if (apiKey) headers['X-API-Key'] = apiKey;

      const response = await fetch('/api/news/asx?hours=24&min_items=20', { headers });

      if (!response.ok) throw new Error(`Failed to fetch news (${response.status})`);

      const data = await response.json();
      setNews(data.news);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  useEffect(() => {
    fetchNews();
    const interval = setInterval(fetchNews, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchNews]);

  const filteredItems = selectedCategory
    ? news?.items.filter(item => item.category === selectedCategory)
    : news?.items;

  if (loading && !news) {
    return <div className="news-dashboard loading">Loading ASX news...</div>;
  }

  if (error) {
    return <div className="news-dashboard error">Error: {error}</div>;
  }

  return (
    <div className="news-dashboard">
      <div className="news-header">
        <h2>ASX Market News</h2>
        <span className="news-count">{news?.total_filtered} topics</span>
        <span className="news-time">
          Updated: {new Date(news?.fetch_time).toLocaleTimeString()}
        </span>
      </div>

      <div className="category-pills">
        <button
          className={`pill ${selectedCategory === null ? 'active' : ''}`}
          onClick={() => setSelectedCategory(null)}
        >
          All
        </button>
        {Object.entries(news?.by_category || {}).map(([cat, count]) => (
          <button
            key={cat}
            className={`pill ${selectedCategory === cat ? 'active' : ''}`}
            style={{ '--pill-color': CATEGORY_COLORS[cat] || '#555' }}
            onClick={() => setSelectedCategory(cat)}
          >
            {CATEGORY_ICONS[cat] || ''} {cat} ({count})
          </button>
        ))}
      </div>

      <div className="news-list">
        {filteredItems?.map((item, idx) => (
          <div
            key={idx}
            className="news-item"
            style={{ '--category-color': CATEGORY_COLORS[item.category] || '#666' }}
          >
            <div className="news-meta">
              <span className="news-category">
                {CATEGORY_ICONS[item.category] || ''} {item.category}
              </span>
              <span className="news-source">{item.source}</span>
              <span className="news-time-stamp">
                {formatTimeAgo(item.published_at)}
              </span>
              <span className="news-relevance">
                {Math.round(item.relevance_score * 100)}% relevant
              </span>
            </div>

            <h3 className="news-headline">
              {item.url ? (
                <a href={item.url} target="_blank" rel="noopener noreferrer">
                  {item.headline}
                </a>
              ) : (
                item.headline
              )}
            </h3>

            {item.summary && (
              <p className="news-summary">{item.summary}</p>
            )}

            {item.tickers?.length > 0 && (
              <div className="news-tickers">
                {item.tickers.map(ticker => (
                  <span key={ticker} className="ticker-tag">{ticker}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function formatTimeAgo(dateStr) {
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

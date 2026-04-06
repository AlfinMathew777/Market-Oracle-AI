---
paths:
  - "frontend/src/**/*.tsx"
  - "frontend/src/**/*.jsx"
  - "frontend/src/**/*.css"
---

# Frontend Rules — Market Oracle AI

## Component Patterns
- Functional components + hooks only. No class components.
- One component per file. File name = component name.
- Co-locate CSS: `ComponentName.css` next to `ComponentName.js`

## Styling
- Inline styles via JS objects for dynamic values (current pattern in codebase)
- CSS files for static layout and animation classes
- Dark theme first: background `#05050f`, surface `rgba(255,255,255,0.03)`
- Primary accent: `#ff8800` (orange). Never introduce new accent colors without approval.
- Font: monospace for data/numbers, system-ui for labels

## State Management
- React `useState` / `useEffect` for local state
- Lift state to App.js when two+ siblings need it (current pattern)
- No Redux, no Zustand — keep it simple

## Data Fetching
- `fetch()` directly, no axios. Backend URL via `REACT_APP_BACKEND_URL` env var.
- Always handle loading, error, and empty states
- Cache in `localStorage` only for offline fallback (existing pattern)

## Performance
- `React.memo` only when profiling shows it helps — not by default
- No unnecessary re-renders: stable callback refs with `useRef` when passed to globe.gl

## Quality
- No `console.log` left in committed code (use `logger` or remove)
- All API calls wrapped in try/catch with user-visible error state
- `ErrorBoundary` wraps every major section (existing pattern — keep it)

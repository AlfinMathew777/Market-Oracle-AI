# Market Oracle AI — Project Brain

## What This Is
Real-time geopolitical-to-ASX market intelligence platform.
50-agent AI swarm simulates market participant reactions to global events.
Predicts ASX stock movements from conflict events and maritime chokepoint disruptions.

## Stack
- **Backend:** FastAPI (Python 3.11) on Railway — `backend/`
- **Frontend:** React 19 (Create React App + CRACO) on Vercel — `frontend/`
- **Database:** SQLite (`backend/aussieintel.db`) for prediction history
- **Cache:** Redis (Railway) via `backend/cache.py`
- **AI:** Claude claude-sonnet-4-6 via `backend/llm_router.py` + `LLMRouter`
- **Simulation:** 50 agents in `backend/scripts/test_core.py`
- **Maps:** globe.gl (3D WebGL globe) + react-simple-maps (Australia SVG)

## Dev Commands
```bash
# Backend
cd backend && uvicorn server:app --reload --port 8000

# Frontend
cd frontend && npm start          # runs on :3000

# Kill port 3000 (Windows)
npx kill-port 3000

# Deploy (auto on push to main)
git push origin main
```

## Architecture
```
User click → handleEventClick() in App.js
  → POST /api/simulate (FastAPI)
  → Simulation.run_simulation() in test_core.py
  → 50 LLM agent votes (bullish/bearish/neutral)
  → Chain audit → blind judge → confidence guard
  → PredictionCard modal shown to user

Chokepoint click (Globe) → handleChokepointSimulate()
  → POST /api/simulate/chokepoint
  → predict_australian_impact() in australian_impact_engine.py
  → ChokepointReportModal shown
```

## Key Files
| File | Purpose |
|------|---------|
| `backend/scripts/test_core.py` | 50-agent simulation engine + pipeline |
| `backend/services/australian_impact_engine.py` | Chokepoint → ASX impact translation |
| `backend/services/chokepoint_service.py` | 9 chokepoint definitions + risk scoring |
| `backend/routes/simulate.py` | `/api/simulate` and `/api/simulate/chokepoint` |
| `frontend/src/App.js` | Main app, state management |
| `frontend/src/components/Globe.js` | 3D globe, chokepoint markers, popups |
| `frontend/src/components/ChokepointReportModal.js` | Chokepoint simulation results modal |
| `frontend/src/components/PredictionCard.js` | Event simulation results modal |

## Simulation Pipeline (DO NOT REORDER)
1. Vote tally (n_bull, n_bear, n_neut)
2. Confidence calculation
3. **Causal chain audit** — may override direction
4. Blind judge + reconciler — may override direction
5. Market session modifier
6. **Minimum confidence guard** — LAST step

## Confidence System
- Hard cap: **85%** max. Never 100%.
- primary order: max 75% | secondary: max 55% | tertiary: max 35%
- `chain_override_active=True` bypasses neutral guard

## Chokepoint Facts (Do Not Contradict)
- Iron ore travels **EAST** through Malacca to China. NOT through Suez.
- BHP/RIO/FMG = primary for Malacca, **tertiary** for Suez.
- WDS/STO = primary for both Malacca and Suez.
- Suez state heatmap: WA=45, QLD=20, NT=15, NSW=5, **VIC=0**.

## Conventions
- Commit format: `type: description` (feat/fix/refactor/docs/chore)
- No `—` encoding as `?` — always use actual em dash character
- Backend strings: f-strings preferred, no % formatting
- Frontend: inline styles for dynamic values, CSS files for static layout
- All API responses: `{"status": "success"|"error", "data": ...}`

## Environment Variables
```
# Backend (Railway)
ANTHROPIC_API_KEY=
ACLED_API_KEY=
ACLED_EMAIL=
REDIS_URL=
FRONTEND_URL=https://asx.marketoracle.ai

# Frontend (Vercel)
REACT_APP_BACKEND_URL=https://your-railway-app.railway.app
```

## Deploy URLs
- Frontend: https://asx.marketoracle.ai (Vercel)
- Backend: Railway (auto-deploy on push to main)
- GitHub: https://github.com/AlfinMathew777/Market-Oracle-AI

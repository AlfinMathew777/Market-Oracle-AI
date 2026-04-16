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
- Iron ore travels **NORTH** through **Lombok/Makassar Strait** to China. NOT through Malacca. NOT through Suez.
- **Malacca** carries Middle East crude oil and Qatar LNG. Australian iron ore does NOT transit Malacca.
- Malacca disruption = **BULLISH WDS/STO** (Qatar LNG competitor removed), **NEUTRAL miners**, **BEARISH CBA** (import inflation).
- **Lombok** = PRIMARY chokepoint for Australian iron ore. BHP/RIO/FMG = primary for Lombok, tertiary for Malacca/Suez.
- WDS/STO = primary for Lombok AND Suez (LNG routes both ways). Competitive BULLISH for Malacca (Qatar disrupted).
- Suez state heatmap: WA=45, QLD=20, NT=15, NSW=5, **VIC=0**.
- Malacca state heatmap: WA=15, QLD=25, NT=20, NSW=20, VIC=15 (import inflation + LNG benefit).
- Lombok state heatmap: WA=90, QLD=20, NT=30, NSW=10.

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

## Reasoning Synthesizer Agent

### Purpose
Final-stage aggregation agent. Produces structured JSON predictions with causal chain analysis.
Runs AFTER all 45-50 specialist agents have voted.

### Location
- Agent: `backend/agents/reasoning_synthesizer.py`
- Models: `backend/models/reasoning_output.py`
- Route: `backend/routes/reasoning.py`
- Tests: `tests/test_reasoning_synthesizer.py`

### API
```
POST /api/reasoning/synthesize
GET  /api/reasoning/health
```

### Key Design Decisions
- Uses `LLMRouter.call_primary()` — Gemini-first for structured report generation
- Async throughout; fallback output on any LLM/parse failure
- Geography constraint baked into system prompt: Lombok/Makassar NOT Malacca
- Confidence scores calibrated per documented anchors (not LLM-generated)

## Deploy URLs
- Frontend: https://asx.marketoracle.ai (Vercel)
- Backend: Railway (auto-deploy on push to main)
- GitHub: https://github.com/AlfinMathew777/Market-Oracle-AI

## Security

### Authentication
LLM endpoints require API key via `X-API-Key` header or `?api_key=` query param:
- `POST /api/reasoning/synthesize` — auth required, 10 req/min
- `POST /api/trade/generate` — auth required, 10 req/min

Set `MARKET_ORACLE_API_KEYS=your-key` in Railway. Multiple keys: `key1,key2`.
In dev without a key set, one is auto-generated and logged on startup.

### Rate Limiter
In-memory per-client limiter (suitable for single Railway instance).
For multi-instance deploys, switch to Redis-backed limiter.

### Middleware
- `backend/middleware/auth.py` — `verify_api_key` FastAPI dependency
- `backend/middleware/rate_limit.py` — `llm_rate_limit` FastAPI dependency

### Key Rotation Log
| Date | Key | Action |
|------|-----|--------|
| 2026-04-06 | EMERGENT_LLM_KEY (sk-emergent-9EfCeA20...) | Exposed in git history — **rotate immediately** |
| 2026-04-06 | FRED_API_KEY (845738...) | Exposed in git history — rotate at fred.stlouisfed.org |
| 2026-04-06 | MARKETAUX_API_KEY (UNZzV1IH...) | Exposed in git history — rotate at marketaux.com |

## Auto-Update Memory Rules

Memory lives at `~/.claude/projects/c--Users-HP-Market-Oracle-AI/memory/`.

Update the appropriate file **after a change is verified working**. Keep entries to 3–4 lines. Skip minor edits (formatting, typos, comments). Don't duplicate existing entries.

### Architecture Decisions
After changing confidence thresholds, Monte Carlo settings, agent counts, API configs, semaphore limits, or any core system parameter — append to `project_architecture_decisions.md`:

```
### [YYYY-MM-DD] Decision Title
- What: <what changed>
- Why: <reasoning>
- Impact: <expected outcome>
```

### Bug Fixes
After fixing bugs that required meaningful debugging effort — append to `project_bugs_fixed.md`:

```
### [YYYY-MM-DD] Bug Title
- Symptom: <what was broken>
- Cause: <root cause>
- Fix: <solution>
```

### Focus Changes
When priorities shift to new features or modules — update `project_current_focus.md` to reflect current work.

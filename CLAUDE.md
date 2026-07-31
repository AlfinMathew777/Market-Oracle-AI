# Market Oracle AI — Project Brain

## What This Is
Real-time geopolitical-to-ASX market intelligence platform.
AI agent swarm (default 30 agents, configurable up to ~50) simulates market participant reactions to global events.
Predicts ASX stock movements from conflict events and maritime chokepoint disruptions.

## Stack
- **Backend:** FastAPI (Python 3.11) on Railway — `backend/`
- **Frontend:** React 19 (Create React App + CRACO) on Vercel — `frontend/`
- **Database:** SQLite (`backend/aussieintel.db`) for prediction history
- **Cache:** Redis (Railway) via `backend/cache.py`
- **AI:** Multi-provider LLM fallback chain via `backend/llm_router.py` + `LLMRouter` — Groq `llama-3.3-70b` → Groq `llama-3.1-8b-instant` → OpenRouter (auto) → Gemini `gemini-2.0-flash`. Routing modes: `call_boost()` (70b-first, agents), `call_fast()` (8b-first, pattern matching), `call_primary()` (Gemini-first, reports).
- **Simulation:** agent swarm in `backend/scripts/test_core.py` — `NUM_AGENTS` env var (default 30; 25 in tests; up to ~50 for full demo)
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
1. Vote tally (n_bull, n_bear, n_neut) → reputation-weighted tally (eff_bull/bear/neut)
2. Confidence calculation
3. **Causal chain audit** — may override direction
4. Blind judge + reconciler — may override direction
5. Market session modifier
6. **Minimum confidence guard** — LAST step

## Swarm Intelligence Upgrades (ruflo-inspired)
| Feature | Module | Kill switch |
|---------|--------|-------------|
| Reputation-weighted voting — archetype reputation scales vote influence (mean-normalised, clamp 0.5–2.0; cold-start = no-op; raw counts stay authoritative for MC/attribution) | `backend/trust/vote_weighting.py` | `REPUTATION_WEIGHTED_VOTING=0` |
| Ensemble diversity — each agent's PRIMARY provider rotates across model families by agent_id (deep personas: 70b/gemini; fast: 8b/70b/gemini; openrouter = fallback only). Vote dicts carry `provider` | `llm_router.call_agent_vote()` | `ENSEMBLE_DIVERSITY=0` |
| Adaptive topology — contested pre-sim signals (RSI-vs-trend, alt-data-vs-trend) shift bench agents symmetrically onto BOTH directional sides; head-count always preserved | `backend/services/adaptive_topology.py` | (score 0 = no-op) |
| Semantic memory — resolved predictions indexed as Zep episodes (graph `prediction_memory_v1`); cross-ticker similarity recall injected into Reasoning Synthesizer memory prompt | `backend/services/semantic_memory.py` | no `ZEP_API_KEY` = no-op |

## Track-Record Integrity (Vibe-Trading-inspired)
| Feature | Module | Notes |
|---------|--------|-------|
| OHLC sanity guard — structurally impossible bars (high<low, non-positive, bad bracketing) dropped at the loader boundary | `backend/backtesting/data_guards.py` → wired into `fetch_historical_data` | strategy: drop/warn/raise |
| Exit-gap guard — backtest outcomes skipped when the next bar is >5 calendar days away (halts/data gaps must not count as next-day outcomes) | `data_guards.exit_gap_ok` in backtest loop | `MAX_EXIT_GAP_DAYS = 5` |
| Close-price sanity — outcome validation leaves a prediction pending rather than resolving against a non-positive/non-finite price | `data_guards.sane_close_price` in `outcome_checker.fetch_price_at_time` | |
| Accuracy permutation test — label-shuffle null (preserves both marginals) answers "is our hit rate luck?"; p-value + null distribution | `backend/quant/significance.py` + `GET /api/accuracy/significance` | min 10 resolved directional predictions; seeded/reproducible |

## Governance Instrumentation (CFA AI Transition Framework)
| Feature | Module | Notes |
|---------|--------|-------|
| Regime drift detector — small-sample-debiased PSI over confidence + direction distributions (recent 14d vs 120d baseline) + accuracy-collapse escalation; SEVERE fires REGIME_DRIFT alert; MODERATE/SEVERE apply ×0.9/×0.75 confidence haircut in the pipeline | `backend/monitoring/drift_detector.py` | fail-soft: any error = no haircut; thresholds PSI 0.10/0.25 |
| Cognitive diversity monitor — measures whether model FAMILIES (groq tiers = llama) genuinely disagree; free personas only (forced bull/bear roles excluded); HIGH convergence fires COGNITIVE_MONOCULTURE alert; report in every simulation payload (`cognitive_diversity`) | `backend/monitoring/diversity_monitor.py` | UNMEASURED without ≥2 families of provider data |
| Prediction provenance — one auditable document per prediction: decision + confidence audit, votes by provider, reputation weighting, attribution, outcome, fresh hash-chain verification | `backend/services/provenance.py` + `GET /api/predictions/{simulation_id}/provenance` | sections fail independently; missing = reported absent, never fabricated |

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
ZEP_API_KEY=                     # enables semantic prediction memory (optional)
ENSEMBLE_DIVERSITY=1             # 0 = disable multi-model agent rotation
REPUTATION_WEIGHTED_VOTING=1     # 0 = disable reputation-weighted tally

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

## Deployment Workflow

### Environments

| Environment | Branch | Railway Service | PAPER_MODE | Config |
|-------------|--------|-----------------|------------|--------|
| development | any | local only | true | `.env.development` |
| staging | `staging` | staging service | true (forced) | `.env.staging` + `railway.staging.toml` |
| production | `main` | production service | false | `.env.production` + `railway.toml` |

### Promoting a Change

```
# 1. Develop on a feature branch
git checkout -b feat/my-feature

# 2. Merge to staging for pre-prod validation
git checkout staging && git merge feat/my-feature
git push origin staging
# Railway auto-deploys the staging service

# 3. Smoke test staging — check the yellow STAGING badge in the header
curl https://staging-backend.railway.app/api/health | jq .environment

# 4. Promote to production only after staging passes
git checkout main && git merge staging
git push origin main
```

### Railway Staging Service Setup (one-time)

1. In the Railway project, create a new service named **staging**
2. Set **Config Path** → `railway.staging.toml`
3. Set **Watch Paths** → `backend/**` (deploy only on backend changes)
4. Add environment variables: `ENVIRONMENT=staging`, `PAPER_MODE=true`, plus all API keys

### Environment Badge

The frontend header shows a coloured badge when connected to a non-production backend:
- Yellow `STAGING` — connected to staging Railway service
- Blue `DEVELOPMENT` — connected to local dev server
- No badge — production (intentional, no visual noise for end users)

### Key Files

| File | Purpose |
|------|---------|
| `backend/config/environment.py` | Loads `ENVIRONMENT` var, imports env-specific `.env.*`, exposes `ENV`, `is_staging()`, etc. |
| `backend/.env.development` | Dev template — placeholders only, committed to repo |
| `backend/.env.staging` | Staging template — real values set in Railway dashboard |
| `backend/.env.production` | Prod template — real values set in Railway dashboard |
| `railway.staging.toml` | Railway config for staging service (no cron jobs) |
| `railway.toml` | Railway config for production service (includes cron jobs) |

## Claude Code Configuration

### Directory Structure
```
.claude/
├── agents/        — Specialized subagents (simulation, validation, backtest, debug, deploy)
├── commands/      — Slash commands (/simulate, /validate, /backtest, /health-check, /daily-report, /deploy-*)
├── skills/        — Domain knowledge (market-data-fetcher, agent-consensus, monte-carlo, signal-validator, asx-knowledge, fastapi-patterns)
├── rules/         — Project rules (signal-quality, code-style, testing, security, documentation)
│                    + existing: backend.md, frontend.md, simulation.md
└── hooks/         — Automation (file-protection, auto-commit, simulation-logger, sound-complete, pre-deploy-check)
```

### Key Commands
| Command | What It Does |
|---------|-------------|
| `/simulate BHP.AX` | Run full 45-agent prediction simulation |
| `/validate` | Validate pending predictions against actual prices |
| `/backtest BHP.AX 2025-01-01 2025-12-31` | Historical accuracy backtest |
| `/health-check` | Quick system status (kill switch, feeds, alerts, accuracy) |
| `/daily-report` | Comprehensive daily accuracy + health report |
| `/deploy-staging` | Deploy to Railway staging with pre-checks |
| `/deploy-prod` | Promote staging → production (requires confirmation) |

### Agent Selection
| Agent | Model | Use For |
|-------|-------|---------|
| `simulation-agent` | Opus | Generating predictions — high reasoning |
| `validation-agent` | Sonnet | Outcome checking — faster |
| `backtest-agent` | Sonnet | Historical analysis |
| `debug-agent` | Opus | Investigation — max effort, never guesses |
| `deploy-agent` | Sonnet | Safe deployments — plan mode |

### Skill Auto-Loading
Skills trigger based on file globs:
- `backend/**/*.py` → `fastapi-patterns`, `market-data-fetcher`
- `backend/agents/**/*.py` → `agent-consensus`
- `backend/validation/**/*.py` → `signal-validator`
- `**/*.py` → `asx-knowledge` (geographic facts always relevant)

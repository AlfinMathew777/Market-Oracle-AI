# Market Oracle AI — AussieIntel

> **Geopolitical intelligence platform that predicts ASX market impact in real-time.**
> An AI agent swarm analyses global conflict events and maritime chokepoint disruptions, then translates them into probabilistic ASX stock predictions using live data from 9+ sources.

![CI](https://github.com/AlfinMathew777/Market-Oracle-AI/actions/workflows/ci.yml/badge.svg) ![Coverage](https://img.shields.io/badge/coverage-85%25%2B-brightgreen) ![Tests](https://img.shields.io/badge/tests-430%2B-blue) ![Python](https://img.shields.io/badge/Python-3.11-blue) ![React](https://img.shields.io/badge/React-19-61DAFB) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688) ![License](https://img.shields.io/badge/license-MIT-green)

> **Disclaimer:** Market Oracle AI is **not** a licensed financial advisor. All outputs are
> probabilistic **predictions**, not financial advice. Nothing here is a recommendation to buy or sell.

---

## What It Does

1. **Live geopolitical feed** — Pulls conflict events from ACLED (1,000+ events/day worldwide)
2. **Click any event** — e.g. "China restricts iron ore imports from Australia"
3. **Agent swarm runs** — 30 agents by default (configurable up to ~50), each playing a different ASX market participant (fund manager, retail trader, quant, commodities desk…)
4. **Adversarial pipeline** — vote tally → causal-chain audit → blind judge + reconciler → confidence guard
5. **Prediction card** — Direction (UP/DOWN/NEUTRAL), confidence %, causal chain, affected tickers
6. **Chokepoint simulator** — Predict impact of Lombok / Malacca / Suez disruptions on BHP, RIO, FMG, WDS, STO
7. **Track record** — Every prediction is logged and validated against actual price moves; rolling accuracy is published

### Data Sources

| Source | Data | Notes |
|--------|------|-------|
| ACLED | Global conflict events | Live API + RSS fallback |
| yfinance | ASX stock prices | Live + historical |
| FRED | US macro indicators | Federal Reserve |
| RBA | AU macro (cash rate, CPI, unemployment) | RSS + scrape |
| ABS | Australian Bureau of Statistics economics | Census / economic stats |
| GDELT | Global news sentiment | Event stream |
| AISStream | Port Hedland / chokepoint vessel tracking | WebSocket |
| News | ASX announcements + AU news + Reddit | Aggregated RSS |
| Zep Cloud | Semantic ticker knowledge graph | Memory layer |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  React 19 Frontend (Vercel)                      │
│  Globe + AustraliaMap + EventSidebar             │
│  MonteCarlo + AccuracyDashboard + PredictionCard │
└──────────────────┬──────────────────────────────┘
                   │ HTTPS
┌──────────────────▼──────────────────────────────┐
│  FastAPI Backend (Railway)                       │
│  /api/simulate         — agent swarm engine      │
│  /api/simulate/chokepoint — fast chokepoint sim  │
│  /api/reasoning/*      — reasoning synthesizer    │
│  /api/data/*           — Redis-cached data feeds  │
│  /api/admin/*          — kill switch + health     │
│  /api/backtest/*       — historical backtester    │
└──────┬─────────────────────┬────────────────────┘
       │                     │
┌──────▼──────┐    ┌─────────▼──────────────────┐
│  Upstash    │    │  Railway Cron               │
│  Redis      │    │  morning_prediction.py      │
│  (cache)    │    │  (09:30 AEST, Mon–Fri)      │
└─────────────┘    └────────────────────────────┘
┌──────────────────────────────────────────────┐
│  Persistence: SQLite (dev) / PostgreSQL (prod)│
│  prediction_log, reasoning_predictions, alerts│
└──────────────────────────────────────────────┘
```

**LLM Fallback Chain** (`backend/llm_router.py`):
`Groq llama-3.3-70b` → `Groq llama-3.1-8b-instant` → `OpenRouter (auto)` → `Gemini 2.0 Flash`

Three routing modes: `call_boost()` (Groq-70b first, agents) · `call_fast()` (Groq-8b first, pattern matching) · `call_primary()` (Gemini first, structured report generation). Per-provider circuit breaker (3 failures → 60s recovery) with automatic failover on 429/timeout.

---

## Simulation Pipeline (order matters)

1. **Vote tally** — `n_bull`, `n_bear`, `n_neut` across the agent swarm
2. **Confidence calculation**
3. **Causal-chain audit** — may override direction (`chain_override_active`)
4. **Blind judge + reconciler** — may override direction
5. **Market-session modifier**
6. **Minimum-confidence guard** — always last

**Confidence system:** hard cap **85%** (never 100%). Primary signal ≤ 75% · secondary ≤ 55% · tertiary ≤ 35%. Signals below the 55% floor (or below 30% Monte Carlo stability) are blocked and logged as excluded.

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Node.js 18+ / Yarn
- Free API keys (see below)

### 1. Clone & set up backend

```bash
git clone https://github.com/AlfinMathew777/Market-Oracle-AI
cd Market-Oracle-AI/backend

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.development .env   # then fill in at least GROQ_API_KEY + GEMINI_API_KEY
```

### 2. Start backend

```bash
cd backend
uvicorn server:app --reload --port 8000
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 3. Start frontend

```bash
cd frontend
yarn install
yarn start                 # CRACO dev server on :3000
```

---

## Environment Variables

### Required (at least one LLM)

| Variable | Where to get | Free tier |
|----------|-------------|-----------|
| `GROQ_API_KEY` | console.groq.com | 14,400 req/day |
| `GEMINI_API_KEY` | aistudio.google.com | 1,500 req/day |
| `OPENROUTER_API_KEY` | openrouter.ai | 50 req/day |

### Recommended

| Variable | Purpose | Free tier |
|----------|---------|-----------|
| `UPSTASH_REDIS_REST_URL` | Cache layer (fast responses) | 10k cmd/day |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash auth | — |
| `DATABASE_URL` | PostgreSQL connection (prod); omit to use local SQLite | — |
| `FRED_API_KEY` | US macro data | Unlimited |
| `AISSTREAM_API_KEY` | Port Hedland / chokepoint vessel tracking | Unlimited |
| `NUM_AGENTS` | Swarm size (default `30`) | — |

### Optional

| Variable | Purpose |
|----------|---------|
| `ACLED_EMAIL` + `ACLED_API_KEY` | Live conflict data (apply at acleddata.com) |
| `ZEP_API_KEY` | Semantic ticker mapping / memory (1,000 nodes free) |
| `MARKET_ORACLE_API_KEYS` | Protect LLM endpoints — comma-separated keys, supports rotation. In dev a key is auto-generated to `.dev_api_key` if unset |
| `PAPER_MODE` | `true` = log signals but don't publish (default in dev/staging); `false` only in prod |
| `SENTRY_DSN` | Backend error tracking (free 5k events/month) |

### Frontend (`frontend/.env`)

```env
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_SENTRY_DSN=           # Optional: Sentry frontend DSN
```

---

## Environments

Three-tier setup driven by `backend/config/environment.py` and the `ENVIRONMENT` env var:

| Environment | Branch | Host | PAPER_MODE | Config |
|-------------|--------|------|------------|--------|
| development | any | local | `true` (default) | `.env.development` |
| staging | `staging` | Railway staging service | `true` (forced) | `.env.staging` + `railway.staging.toml` |
| production | `main` | Railway production service | `false` | `.env.production` + `railway.toml` |

The frontend header shows a coloured badge for non-production backends (yellow `STAGING`, blue `DEVELOPMENT`); production shows none.

---

## Deployment

### Backend → Railway (production)

Pushing to `main` auto-deploys the Railway production service. Pushing to `staging`
auto-deploys the staging service for pre-prod validation.

```bash
# 1. Develop on a feature branch
git checkout -b feat/my-feature

# 2. Merge to staging and smoke test
git checkout staging && git merge feat/my-feature
git push origin staging
curl https://<staging-backend>.railway.app/api/health | jq .environment

# 3. Promote to production once staging passes
git checkout main && git merge staging
git push origin main
```

**Production cron** (`railway.toml`): `morning_prediction.py` runs pre-market at
09:30 AEST (Mon–Fri). Staging has no cron jobs.

**Health check:** `GET /api/health` — system status + data-source freshness.

> `render.yaml`, `fly.toml`, and `fly.worker.toml` are **legacy** deployment configs
> retained for reference. Railway + Vercel is the current production target.

### Frontend → Vercel

Connect the GitHub repo to Vercel:
- **Root directory:** `frontend`
- **Build command:** `yarn build`
- **Output directory:** `build`
- **Env var:** `REACT_APP_BACKEND_URL` = your Railway backend URL

### One-time setup after first deploy

```bash
# Seed the ASX knowledge graph into Zep Cloud (run once after ZEP_API_KEY is set)
cd backend
python scripts/seed_asx_knowledge_graph.py
```

---

## API Reference

| Endpoint | Method | Auth | Rate limit | Description |
|----------|--------|------|------------|-------------|
| `/api/health` | GET | None | 100/min | System health + data-source status |
| `/api/simulate` | POST | optional | 10/min | Run the agent-swarm simulation |
| `/api/simulate/chokepoint` | POST | optional | 30/min | Fast chokepoint impact prediction |
| `/api/reasoning/synthesize` | POST | `X-API-Key` | 10/min | Reasoning Synthesizer structured output |
| `/api/reasoning/health` | GET | None | 100/min | Synthesizer health |
| `/api/trade/generate` | POST | `X-API-Key` | 10/min | Trade-plan generation (ATR stops, R:R) |
| `/api/data/*` | GET | None | 30/min | Cached data feeds (ACLED, ASX, news, macro, AIS…) |
| `/api/backtest/*` | POST/GET | None | 30/min | Start / poll / list historical backtests |
| `/api/predictions/history` | GET | None | 30/min | Past predictions + outcomes |
| `/api/predictions/accuracy` | GET | None | 30/min | Rolling accuracy statistics |
| `/api/quant/*` | GET | None | 30/min | Monte Carlo, volatility, factor model |
| `/api/admin/kill-switch` | POST | `X-API-Key` | 100/min | Halt all signal generation (HTTP 503) |
| `/api/admin/system-status` | GET | None | 100/min | Kill switch + data-feed health + alerts |
| `/ws/stream` | WS | None | — | Real-time price stream |

Auth: send `X-API-Key: <key>` (or `?api_key=`). Required only on LLM/admin endpoints when
`MARKET_ORACLE_API_KEYS` is set. Rate-limit tiers: **llm** 10/min · **search** 30/min · **default** 100/min.

**Example simulation request:**
```bash
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "event_description": "China imposes tariffs on Australian iron ore",
    "event_type": "Economic",
    "lat": 31.23,
    "lon": 121.47,
    "country": "China",
    "fatalities": 0
  }'
```

---

## Security

- **API key auth** — LLM/admin endpoints gated by `MARKET_ORACLE_API_KEYS` (comma-separated, rotation-friendly). Dev auto-generates a key to `.dev_api_key`.
- **Rate limiting** — per-client in-memory limiter; 10/min on LLM endpoints, 100/min default. Returns 429 with `X-RateLimit-*` headers.
- **Kill switch** — `POST /api/admin/kill-switch` halts all signal generation (503 on simulate endpoints) until resumed.
- **PAPER_MODE** — when on, signals are logged but never published. Default in dev/staging.
- **CORS** — locked to `https://asx.marketoracle.ai` in production; wildcard blocked even if set in env.
- **Input validation** — lat/lon bounds, string-length limits, negative fatalities rejected.
- **Secrets** — never committed; all via environment variables.

---

## Project Structure

```
Market-Oracle-AI/
├── backend/
│   ├── server.py                     # FastAPI app, CORS, rate limiter, Sentry, health
│   ├── llm_router.py                 # 4-tier LLM fallback chain + circuit breakers
│   ├── database.py                   # SQLite (dev) / PostgreSQL (prod) persistence
│   ├── system_state.py               # Kill switch + paper-mode global state
│   ├── config/environment.py         # dev/staging/prod env loader
│   ├── agents/
│   │   ├── reasoning_synthesizer.py  # Final-stage causal-chain aggregation agent
│   │   └── trade_executor.py         # Prediction → trade plan (ATR stops, R:R)
│   ├── routes/                       # simulate, data, reasoning, admin, backtest,
│   │                                 #   predictions, quant, news, stream, accuracy
│   ├── services/                     # 35+ data, validation, analysis, game-theory services
│   │   ├── australian_impact_engine.py   # Chokepoint → ASX impact translation
│   │   ├── chokepoint_service.py     # 9 chokepoint definitions + risk scoring
│   │   └── game_theory/              # China model, institutional model, CVaR, vol calibration
│   ├── quant_engine/monte_carlo.py   # GBM price-path simulation
│   ├── validation/outcome_checker.py # Automated outcome validation vs actual prices
│   ├── monitoring/alerts.py          # Accuracy/data/confidence/MC/anomaly alerts
│   ├── orchestration/                # Multi-stage pipeline (classify→plan→review→aggregate)
│   ├── experiment/arm_assignment.py  # Deterministic A/B treatment/control assignment
│   ├── scripts/                      # seed_* data refresh + morning_prediction.py cron
│   └── tests/                        # 430+ tests (unit, integration, load, chaos, e2e)
├── frontend/
│   └── src/components/
│       ├── Globe.js                  # 3D globe + chokepoint markers (globe.gl + Three.js)
│       ├── AustraliaMap.js           # GeoJSON map + Port Hedland focus
│       ├── PredictionCard.js         # Event simulation result modal
│       ├── ChokepointReportModal.js  # Chokepoint simulation results
│       ├── MonteCarlo/               # Monte Carlo stability visualization
│       ├── AccuracyDashboard.js      # Track record + validation stats
│       ├── NewsDashboard.js          # ACLED event feed
│       ├── SectorHeatmap.js          # State-level impact heatmap
│       ├── TickerStrip.js            # Live ASX ticker
│       ├── TrackRecord.js            # Historical accuracy
│       └── ErrorBoundary.js          # React crash protection
├── docs/                             # runbooks, failure modes, validation audits
├── railway.toml / railway.staging.toml  # Railway prod / staging config
└── render.yaml / fly.toml            # legacy deploy configs (reference only)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, CRACO, Tailwind CSS, Radix UI, globe.gl, Three.js, Recharts, D3, Sentry |
| Backend | Python 3.11, FastAPI, Pydantic v2, asyncio |
| Database | SQLite (dev) / PostgreSQL (prod), Upstash Redis cache |
| LLMs | Groq (llama-3.3-70b / 3.1-8b), Gemini 2.0 Flash, OpenRouter |
| Memory | Zep Cloud knowledge graph |
| Deploy | Railway (backend + cron), Vercel (frontend) |
| Monitoring | Sentry (errors), in-app alerts + kill switch |

---

## Code Quality Standards

All code goes through automated review on every push and PR:

| Tool | Purpose | Gate |
|------|---------|------|
| **Ruff** | Linting + formatting | Blocking |
| **MyPy** | Type checking | Non-blocking |
| **Bandit** | Security scanning (OWASP) | Medium+ severity blocking |
| **pytest-cov** | Test coverage (430+ tests) | Reported, uploaded to Codecov |

CI workflows live in `.github/workflows/` (`ci.yml` runs the test suite on push to
`main`/`staging` and on PRs; `code-review.yml` and `load-test.yml` run targeted checks).

**Set up pre-commit hooks locally:**
```bash
pip install -r requirements-dev.txt
pre-commit install                        # ruff + hooks on every commit
pre-commit install --hook-type pre-push   # pytest on push
```

**Run checks manually:**
```bash
ruff check backend/                                       # lint
ruff format backend/                                      # format
cd backend && pytest tests/ -v                            # tests
bandit -r backend/ --skip B101 --severity-level medium    # security
```

---

## Geographic Facts (Do Not Contradict)

- Iron ore travels **north** through the **Lombok / Makassar Strait** to China — **not** Malacca, **not** Suez.
- **Malacca** carries Middle East crude and Qatar LNG. Malacca disruption = **bullish WDS/STO** (Qatar competitor removed), **neutral** miners, **bearish CBA** (import inflation).
- **Lombok** is the primary chokepoint for Australian iron ore (BHP/RIO/FMG).

---

## License

MIT

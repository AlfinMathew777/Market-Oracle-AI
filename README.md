# Market Oracle AI — AussieIntel

> **Geopolitical intelligence platform that predicts ASX market impact in real-time.**
> A 50-agent AI swarm analyses global conflict events and translates them into actionable ASX stock predictions using live data from 12+ sources.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![React](https://img.shields.io/badge/React-19-61DAFB) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

1. **Live geopolitical feed** — Pulls conflict events from ACLED (1,000+ events/day worldwide)
2. **Click any event** — e.g. "China restricts iron ore imports from Australia"
3. **50-agent swarm** runs — Each AI agent plays a different ASX market participant (fund manager, retail trader, quant, commodities desk…)
4. **Prediction card** — Direction (UP/DOWN/NEUTRAL), confidence %, causal chain, affected tickers
5. **Chokepoint simulator** — Predict impact of Malacca Strait / Suez Canal disruptions on BHP, RIO, WDS

### Data Sources

| Source | Data | Refresh |
|--------|------|---------|
| ACLED | Global conflict events | 6h |
| yfinance | ASX stock prices | 5min |
| FRED | Australian macro (RBA rate, CPI, GDP) | 1h |
| GDELT | Global news sentiment | 1h |
| AISStream | Port Hedland vessel tracking | 30s |
| MarketAux | ASX-specific news | 15min |
| RBA RSS | Interest rate decisions | Live |
| Zep Cloud | Semantic ticker knowledge graph | Static |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  React Frontend (Vercel)                         │
│  Globe + AustraliaMap + EventSidebar             │
│  MacroContext strip + PredictionCard             │
└──────────────────┬──────────────────────────────┘
                   │ HTTPS
┌──────────────────▼──────────────────────────────┐
│  FastAPI Backend (Render Web Service)            │
│  /api/simulate  — 50-agent swarm                 │
│  /api/data/*    — Redis-cached data endpoints    │
│  /api/predict/* — SQLite prediction history      │
└──────┬─────────────────────┬────────────────────┘
       │                     │
┌──────▼──────┐    ┌─────────▼──────────────────┐
│  Upstash    │    │  Render Cron Jobs           │
│  Redis      │    │  seed_acled.py      (6h)    │
│  (cache)    │    │  seed_asx_prices.py (5min)  │
└─────────────┘    │  seed_macro.py      (1h)    │
                   │  seed_au_news.py    (15min) │
                   └────────────────────────────┘
┌──────────────────────────────────────────────┐
│  AIS Relay (Render Background Worker)        │
│  Node.js WebSocket → AISStream → Redis       │
└──────────────────────────────────────────────┘
```

**LLM Fallback Chain:**
`Groq 70b` → `Groq 8b-instant` → `OpenRouter (auto)` → `Gemini 2.0 Flash`

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Node.js 18+ / Yarn
- Free API keys (see below)

### 1. Clone & set up backend

```bash
git clone https://github.com/your-username/market-oracle-ai
cd market-oracle-ai/backend

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — fill in at least GROQ_API_KEY + GEMINI_API_KEY
```

### 2. Start backend

```bash
cd backend
python server.py
# API: http://localhost:8001
# Docs: http://localhost:8001/docs
```

### 3. Start frontend

```bash
cd frontend
yarn install
yarn start
# App: http://localhost:3000
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env`:

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
| `FRED_API_KEY` | Australian macro data | Unlimited |
| `AISSTREAM_API_KEY` | Port Hedland vessel tracking | Unlimited |

### Optional

| Variable | Purpose |
|----------|---------|
| `ACLED_EMAIL` + `ACLED_PASSWORD` | Live conflict data (apply at acleddata.com) |
| `MARKETAUX_API_KEY` | ASX-specific news (100 req/day free) |
| `ZEP_API_KEY` | Semantic ticker mapping (1,000 nodes free) |
| `API_KEY` | Protect `/api/simulate` from abuse — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SENTRY_DSN` | Backend error tracking (sentry.io, free 5k events/month) |

### Frontend (`frontend/.env`)

```env
REACT_APP_BACKEND_URL=http://localhost:8001
REACT_APP_SENTRY_DSN=           # Optional: Sentry frontend DSN
```

---

## Deployment

### Backend → Render.com (free tier)

1. Push repo to GitHub
2. Go to [render.com](https://render.com) → New → **Blueprint**
3. Connect your GitHub repo — Render detects `render.yaml` automatically
4. Set environment variables in the Render dashboard
5. Deploy — Render spins up:
   - Web service (FastAPI backend on port 8001)
   - Background worker (Node.js AIS relay)
   - 4 cron jobs (ACLED 6h, ASX prices 5min, macro 1h, news 15min)
   - 1GB persistent disk at `/data` for SQLite

### Frontend → Vercel (free tier)

```bash
cd frontend
yarn build
npx vercel --prod
```

Or connect GitHub repo to Vercel dashboard:
- **Root directory:** `frontend`
- **Build command:** `yarn build`
- **Output directory:** `build`
- **Env var:** `REACT_APP_BACKEND_URL` = your Render backend URL

### One-time setup after first deploy

```bash
# Seed ASX knowledge graph into Zep Cloud (run once after ZEP_API_KEY is set)
cd backend
python scripts/seed_asx_knowledge_graph.py
```

---

## API Reference

| Endpoint | Method | Auth | Rate limit | Description |
|----------|--------|------|------------|-------------|
| `/api/health` | GET | None | 120/min | System health + data source status |
| `/api/simulate` | POST | `X-API-Key`* | **5/min** | Run 50-agent simulation |
| `/api/simulate/chokepoint` | POST | `X-API-Key`* | 20/min | Fast chokepoint prediction |
| `/api/data/acled` | GET | None | 60/min | Global conflict events (GeoJSON) |
| `/api/data/asx-prices` | GET | None | 60/min | Live ASX stock prices |
| `/api/data/macro-context` | GET | None | 60/min | AUD/USD, iron ore, ASX 200 |
| `/api/data/news` | GET | None | 60/min | Australian + global news feed |
| `/api/data/china-demand` | GET | None | 60/min | China steel demand signal |
| `/api/data/rba` | GET | None | 60/min | RBA meeting calendar + rate |
| `/api/predict/history` | GET | None | 60/min | Past predictions + outcomes |
| `/api/predict/accuracy` | GET | None | 60/min | Rolling accuracy statistics |

*API key required only when `API_KEY` env var is set. Pass as `X-API-Key: <key>` header.

**Example simulation request:**
```bash
curl -X POST http://localhost:8001/api/simulate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key-here" \
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

- **API Key**: Set `API_KEY` env var to protect simulation endpoint. Pass as `X-API-Key` header.
- **Rate limiting**: `slowapi` — 5/min on `/api/simulate`, 120/min default on all others.
- **CORS**: Restricted to `FRONTEND_URL` in production; `localhost:3000` only in dev.
- **Input validation**: All simulation inputs validated (lat/lon bounds, string length limits, negative fatalities rejected).
- **Secrets**: Never committed — all via environment variables.

---

## Project Structure

```
market-oracle-ai/
├── backend/
│   ├── server.py                    # FastAPI app, rate limiter, Sentry, health check
│   ├── llm_router.py                # 4-tier LLM fallback chain
│   ├── database.py                  # SQLite prediction persistence + accuracy tracking
│   ├── routes/
│   │   ├── simulate.py              # POST /api/simulate (50-agent engine)
│   │   └── data.py                  # GET /api/data/* (12 data endpoints)
│   ├── services/
│   │   ├── redis_client.py          # Upstash Redis cache layer
│   │   ├── acled_service.py         # Global conflict data
│   │   ├── asx_service.py           # ASX stock prices (yfinance)
│   │   ├── fred_service.py          # Australian macro (FRED)
│   │   ├── gdelt_service.py         # News sentiment (GDELT)
│   │   ├── ais_service.py           # Port Hedland vessel tracking
│   │   ├── rba_service.py           # RBA meeting calendar
│   │   ├── china_demand_service.py  # China steel demand signal
│   │   ├── chokepoint_service.py    # Maritime chokepoint risks
│   │   └── semantic_ticker_mapper.py # Zep Cloud ticker mapping
│   └── scripts/
│       ├── seed_acled.py            # Cron: refresh ACLED cache (6h)
│       ├── seed_asx_prices.py       # Cron: refresh ASX prices (5min)
│       ├── seed_macro.py            # Cron: refresh macro + China signal (1h)
│       ├── seed_au_news.py          # Cron: refresh news feed — 17 RSS sources (15min)
│       └── seed_asx_knowledge_graph.py  # One-time: populate Zep Cloud
├── frontend/
│   └── src/
│       ├── App.js                   # Main shell with ErrorBoundary wrapping
│       └── components/
│           ├── Globe.js             # 3D interactive globe (globe.gl + Three.js)
│           ├── AustraliaMap.js      # GeoJSON map + Port Hedland focus
│           ├── EventSidebar.js      # Conflict feed + related news
│           ├── PredictionCard.js    # Simulation result display
│           ├── MacroContext.js      # Economic indicator strip
│           ├── ChokepointRiskPanel.js   # Maritime risk simulator
│           ├── PredictionHistory.js     # Historical predictions (API-backed)
│           └── ErrorBoundary.js         # React crash protection
├── ais-relay/
│   └── index.js                    # Node.js AIS WebSocket → Redis relay
└── render.yaml                     # Render.com multi-service deployment config
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Tailwind CSS, Radix UI, globe.gl, D3 |
| Backend | Python 3.11, FastAPI, Pydantic v2, asyncio |
| Database | SQLite (aiosqlite), Upstash Redis |
| LLMs | Groq (llama-3.3-70b), Gemini 2.0 Flash, OpenRouter |
| Memory | Zep Cloud knowledge graph |
| Deploy | Render.com (backend + workers + crons), Vercel (frontend) |
| Monitoring | Sentry (errors), Render built-in metrics |

---

## License

MIT

# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives

### Primary Objective (updated)
Transition Market Oracle AI from a mock-first demo into a **100% live-data, investor-demo-ready** platform with:
- **Live macro + commodities** (FRED)
- **Live market prices** (yfinance)
- **Live geopolitical/news sentiment** (GDELT + MarketAux)
- **Live logistics signal** (AISStream) once key is provided
- **Live conflict/events** (ACLED) once key is provided

### Investor Demo Flow
- **Select event → pre-simulation signal appears immediately → run 50-agent simulation (3–5 minutes) → prediction card**
- Target tickers: **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX** (plus expanded watchlist heatmap)

### Terminal-Grade UX Requirements (current status)
- ✅ **Top macro context strip** (auto-refresh) now includes **Brent Crude + Gold**
- ✅ **Bottom full-width ASX heatmap strip** (expanded watchlist)
- ✅ **Right-rail prediction history**
- ✅ **Australian Economic Context** panel
- ✅ **Cause→effect overlays** (globe arc + AU flow arrow)
- ✅ **Pre-simulation context signal** (GDELT + MarketAux + commodities)

### Graceful Degradation (non-negotiable)
- **No mock market/macro/news data** should be shown as “real”.
- If API keys are missing, UI must show **Connecting… / Pending Key** (never fake values).

---

## Phase 1 — Core POC (Simulation + LLM + Output Contract) ✅ COMPLETE

### User Stories
1. As a developer, I can run a single script that simulates a sample event and returns a valid **prediction JSON**.
2. As a developer, I can verify 50 agents distributed across personas complete **3–5 rounds** without crashes/timeouts.
3. As a developer, I can confirm **Claude Sonnet 4.6** produces **strict JSON** for the prediction card schema.
4. As a developer, I can confirm **Gemini 2.5 Flash** handles many small agent calls reliably.
5. As a developer, I can verify automatic fallback to **GPT-4.1** on provider/model failure.

### Implementation Steps
1. Env + LLM wiring (backend/.env)
2. Define output contract (PredictionCard schema)
3. POC simulation script and validation loop

### Success Criteria
- POC outputs valid PredictionCard JSON across repeated runs.

---

## Phase 2 — V1 App Development (Globe → Simulate → Prediction Card) ✅ COMPLETE

### User Stories
1. As an investor, I can view a **3D globe** with conflict/event markers.
2. As an investor, I can click a marker (and/or use sidebar) to trigger a simulation with clear progress.
3. As an investor, I can see a **prediction card** (ticker, direction, confidence, causal chain) after completion.
4. As an investor, I can see **live prices** for key ASX tickers.

### Implementation Steps
1. Backend (FastAPI)
   - Implement endpoints:
     - `GET /api/data/acled`
     - `GET /api/data/asx-prices`
     - `GET /api/data/port-hedland`
     - `POST /api/simulate`
2. Frontend (React)
   - Globe UI + sidebar simulation triggering
   - SimulationProgress + PredictionCard + ticker UI

### Success Criteria
- From UI: select an event and receive prediction card within <5 minutes.
- Prices panel reliably loads.

---

## Phase 3 — End-to-End Testing, Hardening, Performance ✅ COMPLETE

### User Stories
1. As QA, I can verify the main flow works for multiple events without refresh.
2. As QA, I can verify errors show clear messages and do not crash UI.

### Implementation Steps
- Validate end-to-end interactions; ensure tooling timeouts match simulation runtime.

### Success Criteria
- Stable end-to-end demo flow with clear progress feedback and recoverable errors.

---

## Phase 4 — Enhancement Phase (Terminal UX + Demo Credibility) ✅ COMPLETE

### P0 — ASX Sector Heatmap Panel (expanded) ✅ COMPLETE
- Backend enhanced `/api/data/asx-prices` for sparkline support.
- Frontend heatmap refactored into a grouped, scrollable watchlist.

### P1 — Prediction History Log ✅ COMPLETE
- Persistent simulation outputs in right rail.

### P2 — Signal Correlation Overlay ✅ COMPLETE
- Globe arc (global) and AU map flow arrow (domestic).

### P3 — Economic Context Strip ✅ COMPLETE
- Macro context strip with auto-refresh.

---

## Phase 5 — Australia-Focused Map Visualization (Default Center View) ✅ COMPLETE
- Australia map is default center view.
- Globe is optional toggle.
- State impact overlay, map badges, and post-simulation arrows implemented.

---

## Phase 6 — Document-Sourced Intelligence Upgrades (2024–2026 AU Economic Report) ✅ COMPLETE
- Sector rate sensitivity + AUD transmission logic injected into simulation prompts.
- Expanded event library, economic context panel, and improved causal chain templates.

---

## Phase 7 — Production Data Mode (Live APIs Rollout) 🟡 IN PROGRESS

### Phase 7.1 — Live Integrations (FRED + MarketAux + AIS readiness + GDELT hardening) ✅ COMPLETE

#### Delivered
- ✅ **FRED live integration**
  - `/api/data/australian-macro` now uses FRED-backed indicators where applicable.
  - **GDP formatting fixed** (avoids misinterpreting nominal GDP levels as % growth).
  - Added FRED commodity series plumbing.
- ✅ **Macro context expansion**
  - `/api/data/macro-context` now returns **Brent Crude** and **Gold** badges.
  - Frontend `MacroContext.js` updated to display **7 indicators**.
- ✅ **MarketAux live news sentiment**
  - Live sentiment for tickers (24h lookback) via MarketAux.
  - Fixed MarketAux query format (published_after ISO datetime).
- ✅ **Pre-simulation context feature**
  - New endpoint: `GET /api/data/pre-simulation-sentiment?tickers=...&topic=...`
  - Combines **GDELT + MarketAux + commodity prices**.
  - Frontend `EventSidebar.js` updated to display the pre-simulation signal on event selection.
- ✅ **AISStream production-ready service (key pending)**
  - Background stream start on backend startup.
  - **Graceful handling with missing key** (logs warning and returns early).
- ✅ **GDELT rate limiting mitigation**
  - 1-hour in-memory TTL cache.
  - Improved behavior on 429: caches rate-limited response so subsequent calls return instantly.
- ✅ **Health endpoint upgraded**
  - `GET /api/health` is now a one-call diagnostic with per-service status.
  - Current demo baseline: **FRED + MarketAux + yfinance = OK** → `demo_ready: true`.
- ✅ **ACLED route bug fixed**
  - `/api/data/acled` now calls the correct ACLED service method and returns a graceful pending state when key is missing.

#### Validation (curl tests executed)
1. `/api/data/australian-macro` → real fields present and populated
2. `/api/data/macro-context` → **brent_crude** and **gold** present
3. `/api/data/pre-simulation-sentiment` → combined bias + article counts
4. `/api/data/gdelt-sentiment` → caching verified (subsequent calls return cached data)
5. `/api/health` → FRED OK, MarketAux OK, yfinance OK, AISStream PENDING_KEY, ACLED PENDING_KEY

---

## Phase 8 — Remaining Live Integrations (Keys + UI + Docs) ⏭️ NEXT

### 8.1 Keys to Acquire (P0)
- **AISSTREAM_API_KEY** (aisstream.io)
- **ACLED_EMAIL + ACLED_API_KEY** (acleddata.com/access)

### 8.2 Live ACLED Events (P0)
- Update ACLED service to use live API once key provided.
- Ensure UI clearly indicates LIVE vs PENDING_KEY.

### 8.3 AISStream Live Vessel Tracking (P0)
- Once key arrives: add to `.env` and verify background stream connects.
- Ensure `/api/data/port-hedland` reflects live congestion/vessel counts.

### 8.4 AEMO Electricity Price (P1)
- Create `aemo_service.py` + endpoint.
- Add a new badge to macro strip.

### 8.5 Alpha Vantage Fallback (P1)
- Add Alpha Vantage as fallback if yfinance fails for tickers.

### 8.6 Geoscience Australia Map Overlay (P1)
- Implement frontend overlay rendering for mineral deposits.
- Add/verify endpoint consumption and marker display.

### 8.7 Documentation (P1)
- Update `README.md` with an **API registry table**:
  - API name, purpose, endpoint, key env var, status (LIVE/PENDING_KEY), rate limits.

---

## 3) Next Actions (Immediate)
1. **Get remaining keys**: AISStream and ACLED (P0).
2. Verify `/api/health` returns `demo_ready: true` before demos.
3. Run 2–3 full simulations using events:
   - `acled_012` (RBA hike)
   - `acled_010` (China iron ore restriction)
   - `acled_013` (rare earth supply chain)
4. Implement remaining Phase 8 integrations (AEMO, Alpha Vantage fallback, Geoscience overlay).
5. Update README API registry.

---

## 4) Overall Success Criteria (Updated)
- Investor demo works end-to-end:
  - **Event selected → pre-sim signal shown instantly → simulation → prediction card**
- Live data readiness:
  - `/api/health` shows **demo_ready: true**
  - At minimum: **FRED OK + MarketAux OK + yfinance OK**
- No mock/fake data shown when keys are missing.
- AISStream and ACLED become live immediately once keys are added.

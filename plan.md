# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**:
  - **Select global event (ACLED) → run 50-agent simulation (3–5 minutes) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Maintain a **credible investor-terminal UX from first render**, including:
  - ✅ **Top macro context strip** (auto-refreshing)
  - ✅ **Bottom full-width ASX heatmap strip** (watchlist-style)
  - ✅ **Right-rail prediction history** (demo track record)
  - ✅ **Cause→effect visual overlay**
    - ✅ Global View: animated globe arc event → AU anchor
    - ✅ Australia View: animated sentiment flow arrow event → ASX Sydney
- Shift the primary visualization narrative to **Australia-first market impact**:
  - ✅ Default center visualization is an **Australia-focused map** showing domestic impact indicators.
  - ✅ Keep the **3D globe as an optional toggle** (button in top-right of map panel), but default to Australia View.
- Keep infrastructure **$0 / low-cost** using **Emergent Universal LLM Key** with model split:
  - **Claude Sonnet 4.6**: ontology extraction + ReportAgent + final prediction JSON
  - **Gemini 2.5 Flash**: per-agent reasoning inside simulation rounds
  - **GPT-4.1**: fallback
- Integrate only required data sources, with graceful fallbacks:
  - **ACLED** (events)
  - **Yahoo Finance (yfinance)** (ASX prices, AUD/USD, ASX200, optional Iron Ore)
  - **FRED** (Fed Funds Rate)
  - **AISStream** (Port Hedland bbox — optional / demo)
- Preserve the **`USE_MOCK_DATA=True`** architecture across services to keep the demo stable and to enable later switching to live APIs.

---

## Phase 1 — Core POC (Simulation + LLM + Output Contract) ✅ COMPLETE

### User Stories
1. As a developer, I can run a single script that simulates a sample ACLED event and returns a valid **prediction JSON**.
2. As a developer, I can verify 50 agents distributed across 8 personas complete **3–5 rounds** without crashes/timeouts.
3. As a developer, I can confirm **Claude Sonnet 4.6** produces **strict JSON** for the prediction card schema.
4. As a developer, I can confirm **Gemini 2.5 Flash** handles many small agent calls reliably.
5. As a developer, I can verify automatic fallback to **GPT-4.1** on provider/model failure.

### Implementation Steps
1. **Env + LLM wiring** (backend/.env)
2. **Define output contract** (PredictionCard schema)
3. **POC simulation script** and validation loop

### Phase 1 Success Criteria
- POC outputs valid PredictionCard JSON across repeated runs.

---

## Phase 2 — V1 App Development (Globe → Simulate → Prediction Card) ✅ COMPLETE

### User Stories
1. As an investor, I can view a **3D globe** with **ACLED markers**.
2. As an investor, I can click a marker (and/or use sidebar) to trigger a simulation with clear **loading/progress**.
3. As an investor, I can see a **prediction card** (ticker, direction, confidence, causal chain) after completion.
4. As an investor, I can see **live prices** for the 5 tracked ASX tickers.

### Implementation Steps
1. **Backend (FastAPI)**
   - Implement and verify endpoints:
     - `GET /api/data/acled`
     - `GET /api/data/asx-prices`
     - `GET /api/data/port-hedland`
     - `POST /api/simulate`
   - Maintain `USE_MOCK_DATA=True` architecture for easy switching to live APIs.
2. **Frontend (React)**
   - Implement globe UI (`globe.gl`) + fallback `EventSidebar` list for simulation triggering.
   - Add `SimulationProgress`, `PredictionCard`, and `TickerStrip`.
   - Refocus copy and scenarios to be explicitly **Australia-centric**.

### Phase 2 Success Criteria
- From UI: select an ACLED event and receive a populated prediction card within **<5 minutes**.
- Prices panel reliably loads for all 5 tickers.

---

## Phase 3 — End-to-End Testing, Hardening, Performance ✅ COMPLETE

### User Stories
1. As QA, I can verify the main flow works for multiple events without refresh.
2. As QA, I can verify errors show clear messages and do not crash UI.

### Implementation Steps
- Validate end-to-end interactions; keep simulation runtime expectations (3–5 minutes) as a feature; ensure tooling timeouts reflect this.

### Phase 3 Success Criteria
- Stable end-to-end demo flow with clear progress feedback and recoverable errors.

---

## Phase 4 — Enhancement Phase (Terminal UX + Demo Credibility) ✅ COMPLETE

**Directive followed:** Implemented in exact priority order **P0 → P1 → P2 → P3**.

### P0 — ASX Sector Heatmap Panel (Bottom Watchlist Strip) ✅ COMPLETE

**Goal:** Add a **bottom-of-screen, full-width, ~120px tall** watchlist panel with **5 equal-width columns**:
- BHP, RIO, FMG, CBA, LYC
- Each cell shows: **price**, **1D change ($ and %)**, and a **5-day sparkline** (SVG polyline; no chart library)

#### Backend ✅
- Enhanced `GET /api/data/asx-prices` to include **5-day lookback** data for sparklines.
- Response includes `history_5d: [{date, close}]` per ticker.

#### Frontend ✅
- Implemented `frontend/src/components/SectorHeatmap.js` and `SectorHeatmap.css`.
- Rendered as a **fixed bottom strip** with **5 equal columns**.

#### Testing ✅
- Test report: `/app/test_reports/iteration_4.json`.

---

### P1 — Prediction History Log (Right Sidebar, Collapsible) ✅ COMPLETE

**Goal:** Build demo credibility by showing a **session track record** of simulations.

#### UX Requirements ✅
- Position: **Right sidebar**, **below existing ASX ticker strip**.
- Collapsible: shows **last 3 by default**, with **Show all** toggle.
- Max height: **40% of viewport**.
- Persistence: `localStorage`.

#### Implementation Notes ✅
- Implemented `frontend/src/components/PredictionHistory.js` + `PredictionHistory.css`.
- Integrated into `App.js` below `TickerStrip`.

#### Testing ✅
- Test report: `/app/test_reports/iteration_5.json`.

---

### P2 — Signal Correlation Overlay (Animated Globe Arc) ✅ COMPLETE

**Goal:** Make causality spatially obvious by connecting event location to the Australian market.

#### UX Requirements ✅
- Yellow animated arc from event lat/lon → AU anchor (lat **-25**, lon **133**)
- Trigger: after simulation completion
- Auto-fade: **8 seconds**

#### Implementation Notes ✅
- App-level `correlationArc` state with timeout cleanup.
- Globe uses `arcsData` with yellow gradient + dash animation.

#### Testing ✅
- Test report: `/app/test_reports/iteration_6.json`.

---

### P3 — Economic Context Strip (Top Macro Header, Auto-Refresh) ✅ COMPLETE

**Goal:** Provide macro framing for ASX moves.

#### UX Requirements ✅
- Top bar, full width, ~36px, dividers between:
  - Fed Funds Rate · AUD/USD · Iron Ore · RBA Cash Rate · ASX 200
- Auto-refresh every **5 minutes**.

#### Backend ✅
- Added `GET /api/data/macro-context` + `backend/services/macro_service.py`.

#### Frontend ✅
- Implemented `frontend/src/components/MacroContext.js` + `MacroContext.css`.

#### Testing ✅
- Test report: `/app/test_reports/iteration_7.json`.

---

## Phase 5 — Australia-Focused Map Visualization (Default Center View) ✅ COMPLETE

**Goal:** Replace the default center panel from a global 3D globe to an **Australia-focused map** that communicates **domestic market impact** immediately, while keeping the globe as an optional toggle.

### Investor Narrative
> “Most geopolitical intelligence platforms show you the world. We show you what the world means for Australia specifically — which states are impacted, which ports are disrupted, which ASX sectors feel it first.”

### UX Requirements (Delivered)
- ✅ Center panel shows **Australia View by default**.
- ✅ Toggle button in the **top-right corner of the center panel**:
  - **🌍 Global View / 🗺 Australia View**
- ✅ Left sidebar (event feed) and right sidebar (prices + prediction history) unchanged.

### Implementation Approach (Delivered)
- ✅ SVG/D3 Australia map (no API keys; instant render)
- ✅ GeoJSON loaded from `frontend/public/australia-states.geojson`
- ✅ No Google Maps / Mapbox

### P5.0 — Base Australia Map + State Boundaries + Markers ✅ COMPLETE

#### Requirements ✅
- Australia fills the center panel; dark theme (dark ocean, slightly lighter land).
- State boundaries clearly visible.
- **6 permanent location markers (always visible):**
  1) Port Hedland (−20.31, 118.58) — shows congestion badge HIGH/MEDIUM/LOW + vessel count
  2) Pilbara Mining Region (−22.0, 117.5)
  3) Gladstone LNG Terminal (−23.84, 151.26)
  4) Darwin Port (−12.46, 130.84)
  5) ASX Sydney (−33.86, 151.21)
  6) Kalgoorlie Gold (−30.74, 121.47)

#### Implementation Notes ✅
- `frontend/src/components/AustraliaMap.js` + `AustraliaMap.css`
- D3 projection: `geoMercator` centered on Australia
- D3 renders state paths into an SVG layer; labels/markers rendered as DOM overlays for crisp text
- Globe retained as optional toggle; Australia view default

#### Success Criteria ✅
- Map renders without API keys.
- State borders visible.
- All 6 markers plotted correctly.
- Toggle switches between Australia map and Globe.

---

### P5.1 — State Impact Heatmap Overlay ✅ COMPLETE

#### Requirements ✅
- On event selection, color impacted states according to an event→state mapping.
- Smooth transition on state fills.
- Tooltip on hover shows "reason" for impact.

#### Implementation Notes ✅
- Implemented `EVENT_STATE_IMPACT` mapping aligned to backend ACLED mock IDs.
- State fill and opacity updated on `selectedEvent` changes.
- Tooltips render from `reason` string.
- **Port Hedland Strike** event produces the most dramatic outcome: **WA deep red at 0.60 opacity**.

---

### P5.2 — Live Sentiment Badges on Map (Macro-context) ✅ COMPLETE

#### Requirements ✅
- 3 floating badges positioned over geography:
  - Over Pilbara: Iron Ore
  - Center: AUD/USD
  - Over Sydney: ASX 200
- Pull from `GET /api/data/macro-context` (no new backend work).
- Refresh every 5 minutes.

#### Implementation Notes ✅
- Implemented `BADGE_POSITIONS` and periodic fetch to `/api/data/macro-context`.
- Projected badge positions using same `geoMercator` projection.
- Styled as pill badges with dark translucent background + blue border.

---

### P5.3 — Sentiment Flow Arrows (Post-simulation) ✅ COMPLETE

#### Requirements ✅
- When prediction completes, render one animated dashed curved path from event location → **ASX Sydney**.
- Green for UP predictions, red for DOWN.
- Auto-clear after 10 seconds.

#### Implementation Notes ✅
- Implemented `sentimentArrow` state triggered by `prediction` + `selectedEvent`.
- Rendered as SVG quadratic bezier path with `dashFlow` keyframe animation.
- Single-arrow policy: new simulation replaces existing arrow.

---

### P5.4 — Event Impact Popup / Panel (Replaces Globe Popup) ⏭️ FUTURE

#### Requirements
- On sidebar event click:
  - highlight region on Australia map
  - show a right-side panel with:
    - affected states/sectors and why
    - relevant tickers with current price + predicted direction
    - “Simulate ASX Impact” button (existing simulate flow)

#### Implementation Steps
1. Add selected-event state binding to map (already present)
2. Implement panel component (reuse PredictionCard/price data)
3. Keep existing simulation trigger logic

---

## Phase 6 — P4: Swap to Real APIs (Production Data Mode) ⏭️ FUTURE

**Goal:** Switch from mock mode to live data feeds for a production-ready demo.

### User Stories
1. As a user, I see *live* ACLED events and market/macro data without manual updates.
2. As a developer, I can flip from mock to live via environment variables without refactoring.

### Implementation Steps
1. Obtain and add API keys (as needed):
   - ACLED (if required for higher quota)
   - AISStream
2. Update `.env` and relevant service modules in `/app/backend/services/`.
3. Set `USE_MOCK_DATA=False`.
4. Add defensive fallbacks and timeouts per service so one failing feed does not break the UI.
5. Re-run end-to-end demo validation.

### Success Criteria
- Live data displayed for events, prices, and macro strip without breaking the core simulation flow.

---

## 3) Next Actions (Immediate)
1. **P5.4 (Optional):** Implement Event Impact Popup/Panel tailored to Australia map (states/sectors → tickers → simulate CTA).
2. **Polish:** Address low-priority styling verification:
   - Ensure `.state-boundary` transition explicitly matches `fill 0.6s ease, fill-opacity 0.6s ease` (test agent could not detect exact computed spec; visual behavior is correct).
3. **Demo validation:** Run the “hero interaction”:
   - Select **Port Hedland Strike** → confirm WA deep red → run simulation → confirm DOWN prediction → confirm red dashed flow arrow to ASX Sydney.

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED event → 50-agent simulation → prediction card** in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - ✅ Top macro context header (auto-refresh)
  - ✅ Bottom heatmap watchlist strip
  - ✅ Persistent prediction history
  - ✅ Cause→effect overlay (globe arc and Australia flow arrow)
  - ✅ Australia-first center visualization (state impacts + key ports/hubs + macro badges)
- System remains stable in mock mode and supports switching to live APIs without refactor.

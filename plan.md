# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**:
  - **Select global event (ACLED) → run 50-agent simulation (3–5 minutes) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Maintain a **credible investor-terminal UX from first render**, including:
  - ✅ **Top macro context strip** (auto-refreshing)
  - ✅ **Bottom full-width ASX heatmap strip** (watchlist-style)
  - ✅ **Right-rail prediction history** (demo track record)
  - ✅ **Cause→effect visual arc** (global view) / flow overlay (Australia view)
- Shift the primary visualization narrative to **Australia-first market impact**:
  - Default center visualization becomes an **Australia-focused map** showing domestic impact indicators.
  - Keep the **3D globe as an optional toggle** ("🌍 Global View / 🗺 Australia View"), but **default to Australia View**.
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

## Phase 5 — Australia-Focused Map Visualization (Default Center View) ⏭️ NEXT

**Goal:** Replace the current center-panel default from a global 3D globe to an **Australia-focused map** that communicates **domestic market impact** immediately, while keeping the globe as an optional toggle.

### Investor Narrative
> “Most geopolitical intelligence platforms show you the world. We show you what the world means for Australia specifically — which states are impacted, which ports are disrupted, which ASX sectors feel it first.”

### UX Requirements (High Level)
- Center panel shows **Australia View by default**.
- Add a small toggle button in the **top-right corner of the center panel**:
  - **🌍 Global View / 🗺 Australia View**
- Left sidebar (event feed) and right sidebar (prices + prediction history) remain unchanged.

### Implementation Approach (Simplest First)
- **Start with an SVG/D3 Australia map** (no API keys; renders instantly).
- Use GeoJSON source: 
  - `https://raw.githubusercontent.com/rowanhogan/australian-states/master/states.min.geojson`
- If D3 is not available in the frontend bundle, fallback to a small inline SVG with state paths.
- Explicitly **do not** use Google Maps / Mapbox.

### P5.0 — Base Australia Map + State Boundaries + Markers (MVP for Phase 5)

#### Requirements
- Australia fills the center panel; dark theme (dark ocean, slightly lighter land).
- State boundaries clearly visible.
- **6 permanent location markers (always visible):**
  1) Port Hedland (−20.31, 118.58) — show congestion badge HIGH/MEDIUM/LOW + vessel count
  2) Pilbara Mining Region (−22.0, 117.5) — “Iron Ore” label
  3) Gladstone LNG Terminal (−23.84, 151.26) — “LNG export” label
  4) Darwin Port (−12.46, 130.84) — “China trade route” label
  5) ASX Sydney (−33.86, 151.21) — “Financial hub” marker
  6) Kalgoorlie Gold (−30.74, 121.47) — “Gold mining” label

#### Implementation Steps
1. Create `frontend/src/components/AustraliaMap.js` (+ CSS)
2. Render state polygons from GeoJSON (SVG)
3. Project lat/lon → SVG x/y (simple Mercator/Aus-centric projection via D3-geo or hand-tuned projection)
4. Render the 6 markers with small labels
5. Integrate into center panel with the toggle (default to Australia Map)

#### Success Criteria
- Australia map renders without API keys.
- State borders visible.
- All 6 markers plotted correctly.
- Toggle switches between Australia map and Globe.

#### Testing
- Frontend smoke test + screenshot confirming base map + 6 markers.

### P5.1 — State Impact Heatmap Overlay (Event selection + Simulation completion)

#### Requirements
- When event selected (or simulation completes), color states by predicted impact:
  - **WA:** red for iron ore/resources events (BHP/RIO/FMG)
  - **QLD:** amber for coal/LNG events
  - **NSW/VIC:** blue for rate/financial events
  - **NT:** highlight for Darwin/China trade-route events
  - **SA/VIC:** highlight for rare earth/lithium events (LYC)
- Default opacity 0; animate to opacity ~0.4 on activation.
- Fade out **10 seconds after simulation completes**.

#### Implementation Steps
1. Define event→state impact mapping (frontend-only initially)
2. Add overlay state + timers:
   - on event select: show overlay
   - on simulation completion: show overlay + schedule fade-out (10s)
3. Apply fill colors per state polygon

#### Success Criteria
- Selecting an event visibly highlights the correct regions.
- Overlay fades out after completion.

### P5.2 — Live Sentiment Badges on Map (Macro-context)

#### Requirements
- 3 floating badges positioned over geography:
  - Over Pilbara: “Iron Ore $97.50/t ↓”
  - Over Bass Strait: “AUD/USD 0.6523”
  - Over Sydney: “ASX 200 8,267 ↑0.42%”
- Pull from existing `GET /api/data/macro-context` (no backend changes).

#### Implementation Steps
1. Reuse macro-context fetch (or share existing MacroContext state)
2. Render 3 small overlay badges with absolute positioning within map

### P5.3 — Sentiment Flow Arrows (Post-simulation)

#### Requirements
- Animated curved arrows showing flow **from impacted region → Sydney/ASX marker**, labeled with ticker + direction.
- Fade out after **8 seconds** (same as globe arc concept).

#### Implementation Steps
1. Convert simulation result ticker → chosen origin region anchor
2. Render SVG paths with CSS animation
3. Auto-clear after timeout

### P5.4 — Event Impact Popup (Replaces Globe Popup)

#### Requirements
- On sidebar event click:
  - highlight region on the Australia map
  - show a right-side panel with:
    - affected states/sectors and why
    - relevant tickers with current price + predicted direction
    - “Simulate ASX Impact” button (existing simulate flow)

#### Implementation Steps
1. Add selected-event state binding to map
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
1. **Phase 5 / P5.0:** Build SVG/D3 Australia map with state boundaries + the 6 permanent markers.
2. Add the **Global/Australia view toggle** (default to Australia view).
3. Provide a screenshot showing the base map + markers before implementing overlays/arrows.

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED event → 50-agent simulation → prediction card** in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - ✅ Top macro context header (auto-refresh)
  - ✅ Bottom heatmap watchlist strip
  - ✅ Persistent prediction history
  - ✅ Cause→effect overlay (globe arc and/or Australia flow arrows)
  - ⏭️ Australia-first center visualization (state impacts + key ports/hubs)
- System remains stable in mock mode and supports switching to live APIs without refactor.

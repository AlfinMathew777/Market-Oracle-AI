# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver an **end-to-end investor demo**:
  - **Select event (ACLED) → run 50-agent simulation (3–5 minutes) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Maintain a **credible investor-terminal UX from first render**, including:
  - ✅ **Top macro context strip** (auto-refreshing)
  - ✅ **Bottom full-width ASX heatmap strip** (watchlist-style)
  - ✅ **Right-rail prediction history** (demo track record)
  - ✅ **Cause→effect visual overlay**
    - ✅ Global View: animated globe arc event → AU anchor
    - ✅ Australia View: animated sentiment flow arrow event → ASX Sydney
- Shift the platform narrative to **Australia-first market impact**:
  - ✅ Default center visualization is an **Australia-focused map** showing domestic impact indicators.
  - ✅ Keep the **3D globe as an optional toggle** (button in top-right of center panel), default to Australia View.
- Upgrade the product to be **institutional-grade** using document-sourced Australian market structure and macro intelligence (2024–2026):
  - ⏭️ Replace key hardcoded macro data with **ABS and RBA** sources (via `readabs` / `pysdmx`) while preserving `USE_MOCK_DATA`.
  - ⏭️ Inject **sector rate sensitivity** and **AUD transmission** logic into the simulation engine so agents behave like real market participants.
  - ⏭️ Expand the event library with **real 2025–2026 geopolitical events** that map to Australian exposures.
  - ⏭️ Replace static copy blocks with a **dynamic Australian Economic Context** panel.
  - ⏭️ Improve causal-chain quality with **standard Australian transmission templates** baked into the ReportAgent prompt.
- Keep infrastructure **$0 / low-cost** using **Emergent Universal LLM Key** with model split:
  - **Claude Sonnet 4.6**: ontology extraction + ReportAgent + final prediction JSON
  - **Gemini 2.5 Flash**: per-agent reasoning inside simulation rounds
  - **GPT-4.1**: fallback
- Integrate required data sources with graceful fallbacks:
  - **ACLED (mock now; live later)**
  - **Yahoo Finance (yfinance)** (ASX prices, AUD/USD, ASX200, optional Iron Ore)
  - **FRED** (Fed Funds Rate)
  - **AISStream** (Port Hedland bbox — optional / demo)
  - ⏭️ **ABS Indicator API + RBA (readabs)**
- Preserve the **`USE_MOCK_DATA=True`** architecture across services to keep the demo stable and enable later switching to live APIs.

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

## Phase 6 — Document-Sourced Intelligence Upgrades (2024–2026 AU Economic Report) ⏭️ IN PROGRESS

**Goal:** Upgrade Market Oracle AI from a strong demo to an **institutional-grade Australian economic intelligence system** by grounding macro data, agent logic, event library, and causal chains in the provided 2024–2026 Australian economic report.

### Upgrade Ordering (must follow)
1) **Upgrades 1 & 2** first (simulation quality impact)
2) Then **Upgrades 3 & 4** (dashboard richness)
3) Then **Upgrade 5** (permanent causal-chain improvement)

---

### Upgrade 1 — Replace hardcoded mock data with ABS/RBA connections ✅/⏭️

#### Requirements
- Add dependencies:
  - `readabs`
  - `pysdmx`
- Create `backend/services/abs_service.py` implementing `get_australian_macro()` with `USE_MOCK_DATA` pattern.
- New endpoint: `GET /api/data/australian-macro`.
- Wire into dashboard:
  - Economic Context Strip gets **two new badges**: **CPI** and **GDP Growth**.

#### Implementation Steps
1. Add `readabs` and `pysdmx` to `backend/requirements.txt`.
2. Create `backend/services/abs_service.py`:
   - Mock return:
     - CPI 3.8
     - RBA cash rate 3.85
     - GDP growth 1.4
     - unemployment 4.1
     - household debt % income 176
     - household saving ratio 6.1
     - terms of trade change -4.0
     - labor productivity change -0.7
   - Live mode:
     - CPI via `ra.read_abs_cat("6401.0")`
     - Labour Force via `ra.read_abs_cat("6202.0")`
     - RBA cash via `ra.read_rba_ocr(monthly=True)`
3. Add endpoint `GET /api/data/australian-macro` (routes/data.py).
4. Update `MacroContext` component to display:
   - CPI 3.8%
   - GDP Growth 1.4%
5. Testing:
   - Verify endpoint returns expected JSON
   - Verify macro strip renders 2 new badges without layout break.

#### Success Criteria
- Dashboard shows CPI and GDP Growth in macro strip.
- Backend supports mock mode now and can flip to live with ABS key later.

---

### Upgrade 2 — Sector sensitivity logic in simulation engine ⏭️

#### Requirements
- Add sector lookup table and AUD transmission mechanism:
  - `SECTOR_RATE_SENSITIVITY`
  - `AUD_TRANSMISSION_MULTIPLIER`
  - `apply_aud_transmission()`
- Inject into agent reasoning context so RBA rate events produce credible sector-biased votes.

#### Implementation Steps
1. Add the lookup table to `backend/services/simulation_engine.py`.
2. Detect rate events (e.g., `event_type == "Monetary Policy"` or affected region `domestic_rates`).
3. For each agent prompt/context:
   - Add relevant sensitivity snippet for the affected sector/ticker.
4. For resources tickers:
   - Add AUD commodity amplifier context and apply `apply_aud_transmission()` when AUD movement is relevant.
5. Testing:
   - Run simulation on the RBA hike event (acled_012 once added) and verify CBA leans bullish.

#### Success Criteria
- Rate events produce consistent, explainable bank-vs-REIT divergence.
- Causal chains explicitly cite NIM expansion for banks.

---

### Upgrade 3 — Add five new ACLED events (real 2025–2026 geopolitics) ⏭️

#### Requirements
- Add `acled_009`…`acled_013` to mock ACLED service:
  - US Liberation Day tariffs (Washington DC)
  - China iron ore bans (Beijing)
  - ASEAN/India trade realignment (Singapore)
  - RBA raises to 3.85% (Canberra)
  - Semiconductor controls intensify rare earth demand (Taiwan)

#### Implementation Steps
1. Update `backend/services/acled_service.py` mock list to append `NEW_EVENTS`.
2. Ensure `GET /api/data/acled` returns 13 total events.
3. Update Australia map `EVENT_STATE_IMPACT` mapping for new event IDs (esp. RBA hike and trade restrictions).
4. Testing:
   - Verify new events appear in sidebar.
   - Verify state heatmap reacts sensibly.

#### Success Criteria
- 13 events cover resources, rates, trade, rare earths, ASEAN realignment.

---

### Upgrade 4 — Australian Economic Context panel (right sidebar) ⏭️

#### Requirements
- Replace static “Key Australian Exposures” bullet list with a dynamic panel:
  - GDP Growth 1.4% ↓
  - Inflation (CPI) 3.8% ↑
  - RBA Cash Rate 3.85% ↑
  - Household Debt 176% of income
  - Saving Ratio 6.1% ↑
  - Terms of Trade -4.0%
  - Labor Productivity -0.7%
  - Mining Export Share 57.4%
  - Superannuation AUM $3.5T
  - National Net Worth $21.4T
- Add tooltips explaining ASX relevance (e.g., household debt tooltip about rate sensitivity).
- Initial values hardcoded from document.

#### Implementation Steps
1. Create `frontend/src/components/AustralianEconomicContext.js` + CSS.
2. Remove/replace static list in sidebar with this component.
3. Add tooltip system (existing tooltip components can be reused).
4. Optional integration:
   - Once Upgrade 1 endpoint exists, this panel can be partially driven from `/api/data/australian-macro`.
5. Testing:
   - Verify tooltips render.
   - Verify layout stays within right sidebar constraints.

#### Success Criteria
- Panel renders as a live intelligence block and becomes the primary right-rail narrative component.
- **User-visible deliverable:** provide screenshot after this upgrade.

---

### Upgrade 5 — Improve causal chain quality (document transmission mechanisms) ⏭️

#### Requirements
- Add `AUSTRALIAN_MARKET_CONTEXT` block to the **Claude ReportAgent system prompt** so reports reference:
  1) AUD Commodity Amplifier
  2) Superannuation Contagion (correlation 0.65–0.75 with S&P 500)
  3) Rate Sensitivity Asymmetry (banks vs REITs)
  4) China Concentration Risk (80% Pilbara iron ore)
  5) Critical Minerals Premium

#### Implementation Steps
1. Update ReportAgent prompt (where Claude is invoked for final synthesis/report).
2. Ensure causal chain output uses Template A and Template B when relevant.
3. Testing:
   - Run at least one commodity shock event (resources) and one US-tech selloff style event and verify templates appear.

#### Success Criteria
- Causal chains become consistent, sophisticated, and recognizably Australia-specific.

---

## Phase 7 — P4: Swap to Real APIs (Production Data Mode) ⏭️ FUTURE

**Goal:** Switch from mock mode to live data feeds for a production-ready demo.

### User Stories
1. As a user, I see *live* events and market/macro data without manual updates.
2. As a developer, I can flip from mock to live via environment variables without refactoring.

### Implementation Steps
1. Obtain and add API keys (as needed):
   - ACLED (if required for higher quota)
   - AISStream
   - ABS API key (if required)
2. Update `.env` and relevant service modules in `/app/backend/services/`.
3. Set `USE_MOCK_DATA=False`.
4. Add defensive fallbacks and timeouts per service so one failing feed does not break the UI.
5. Re-run end-to-end demo validation.

### Success Criteria
- Live data displayed for events, prices, and macro strip without breaking the core simulation flow.

---

## 3) Next Actions (Immediate)
1. **Phase 6 / Upgrade 1:** Add ABS/RBA macro endpoint + CPI & GDP Growth badges.
2. **Phase 6 / Upgrade 2:** Add sector rate sensitivity + AUD transmission logic to simulation engine.
3. **Phase 6 / Upgrade 3:** Add five new ACLED events (2025–2026 real geopolitics).
4. **Phase 6 / Upgrade 4:** Replace static right sidebar bullets with **Australian Economic Context** panel (deliver screenshot).
5. **Phase 6 / Upgrade 5:** Add AU transmission templates to Claude ReportAgent prompt.

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED event → 50-agent simulation → prediction card** in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - ✅ Top macro context header (auto-refresh)
  - ✅ Bottom heatmap watchlist strip
  - ✅ Persistent prediction history
  - ✅ Cause→effect overlay (globe arc and Australia flow arrow)
  - ✅ Australia-first center visualization (state impacts + key ports/hubs + macro badges)
  - ⏭️ Right-rail **Australian Economic Context** intelligence panel
- Simulation reasoning is Australia-realistic:
  - ⏭️ Sector rate sensitivity
  - ⏭️ AUD commodity amplifier
  - ⏭️ Superannuation contagion templates
- System remains stable in mock mode and supports switching to live APIs without refactor.

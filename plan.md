# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**: **Click ACLED event on 3D globe (or select from sidebar) → run 50-agent simulation (3–5 minutes) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Maintain a **credible investor-terminal UX from first render**, including:
  - ✅ **Top macro context strip** (auto-refreshing)
  - ✅ **Bottom full-width ASX heatmap strip** (watchlist-style)
  - ✅ **Right-rail prediction history** (demo track record)
  - ✅ **Cause→effect visual arc** on the globe (event → Australian market anchor)
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
- From UI: click an ACLED event and receive a populated prediction card within **<5 minutes**.
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
- Enhanced `GET /api/data/asx-prices` to include **5-day lookback** data for sparklines:
  - Real mode supported via `yfinance.download(ticker, period='5d', interval='1d')`.
  - Mock mode extended with realistic 5-day arrays to keep demo stable.
- Response includes `history_5d: [{date, close}]` per ticker.

#### Frontend ✅
- Implemented `frontend/src/components/SectorHeatmap.js` and `SectorHeatmap.css`.
- Rendered as a **fixed bottom strip** with **5 equal columns**.
- Sparklines:
  - 5-point SVG polyline, normalized to cell height
  - Green for uptrend, red for downtrend
  - Slight glow / increased stroke for visibility
- Layout reserved space using `margin-bottom: 120px` on `.main-container`.

#### Testing ✅
- Test report: `/app/test_reports/iteration_4.json`.

---

### P1 — Prediction History Log (Right Sidebar, Collapsible) ✅ COMPLETE

**Goal:** Build demo credibility by showing a **session track record** of simulations.

#### UX Requirements ✅
- Position: **Right sidebar**, **below existing ASX ticker strip**.
- Collapsible:
  - Shows **last 3 predictions by default**, with a **Show all** toggle.
- Max height: **40% of viewport**.
- Persistence: `localStorage` (survives refresh).
- Clear functionality: user can clear all history (with confirmation).

#### Implementation Notes ✅
- Implemented `frontend/src/components/PredictionHistory.js` + `PredictionHistory.css`.
- Integrated into `App.js` below `TickerStrip`.
- Storage key: `prediction_history`.
- Functional state updates used to avoid stale appends.

#### Testing ✅
- Test report: `/app/test_reports/iteration_5.json`.

---

### P2 — Signal Correlation Overlay (Animated Globe Arc) ✅ COMPLETE

**Goal:** Make causality spatially obvious by connecting event location to the Australian market.

#### UX Requirements ✅
- Render on the globe as a **yellow animated arc** from:
  - event lat/lon → **Australian market anchor point** (lat **-25**, lon **133**)
- Trigger: after simulation completion.
- Auto-fade: **8 seconds**, then disappear.

#### Implementation Notes ✅
- **State wiring (App.js)**
  - Added `correlationArc` state: `{ show, eventLat, eventLng }`.
  - Added `arcTimeoutRef` with cleanup on unmount.
  - On prediction completion: set arc active and schedule clear after 8 seconds.
  - On subsequent prediction: clears prior timeout before scheduling a new one.
- **Globe rendering (Globe.js)**
  - Added `correlationArc` prop.
  - Implemented globe.gl `arcsData` layer with yellow gradient + dash animation.
  - Clears arcs when `correlationArc.show` is false.

#### Testing ✅
- Test report: `/app/test_reports/iteration_6.json`.

---

### P3 — Economic Context Strip (Top Macro Header, Auto-Refresh) ✅ COMPLETE

**Goal:** Provide macro framing for ASX moves; investors notice stale data.

#### UX Requirements ✅
- Top of screen, full width, **~36px** tall.
- Dark background slightly lighter than main dashboard.
- Left-to-right items with thin dividers:
  1) Fed Funds Rate
  2) AUD/USD
  3) Iron Ore Spot
  4) RBA Cash Rate
  5) ASX 200 Index

#### Backend ✅
- Added endpoint: `GET /api/data/macro-context`.
- Implemented service: `backend/services/macro_service.py` with `USE_MOCK_DATA` pattern and caching.
- Sources / fallbacks:
  - **Fed Funds Rate:** FRED series `FEDFUNDS`, cached **1800s** (fallback value on error).
  - **AUD/USD:** Yahoo Finance `AUDUSD=X` via yfinance, cached **300s**.
  - **Iron Ore:** attempts `IRON.AX` via yfinance; fallback **$97.50/t** with `status: delayed`.
  - **RBA Cash Rate:** hardcoded **4.10%** with last-updated date.
  - **ASX 200:** Yahoo Finance `^AXJO` via yfinance, cached **300s**, includes `change_pct`.

#### Frontend ✅
- Implemented `frontend/src/components/MacroContext.js` + `MacroContext.css`.
- Auto-refresh every **5 minutes** using `setInterval`:
  ```js
  useEffect(() => {
    fetchMacroContext();
    const interval = setInterval(fetchMacroContext, 300000);
    return () => clearInterval(interval);
  }, []);
  ```
- Integrated at the very top of `App.js` as a fixed strip.
- Header offset updated via `margin-top: 36px` on `.app-header`.

#### Testing ✅
- Test report: `/app/test_reports/iteration_7.json`.

---

## Phase 5 — P4: Swap to Real APIs (Production Data Mode) ⏭️ NEXT

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
1. **Proceed to P4 (Swap to Real APIs)** once API keys are provided.
2. (Optional hardening) Add a small “data status” indicator per panel (live/delayed/mock) for demo transparency.

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED event → 50-agent simulation → prediction card** in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - ✅ Top macro context header (auto-refresh)
  - ✅ Bottom heatmap watchlist strip
  - ✅ Persistent prediction history
  - ✅ Globe cause→effect arc
- System remains stable in mock mode and supports switching to live APIs without refactor.

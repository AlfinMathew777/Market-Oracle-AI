# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**: **Click ACLED event on 3D globe (or select from sidebar) → run 50-agent simulation (3–5 rounds) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Keep infrastructure **$0** (free tiers) using **Emergent Universal LLM Key** with model split:
  - **Claude Sonnet 4.6**: ontology extraction + ReportAgent + final prediction JSON
  - **Gemini 2.5 Flash**: per-agent reasoning inside simulation rounds
  - **GPT-4.1**: fallback
- Integrate only required data sources: **ACLED**, **Yahoo Finance**, **FRED**, **AISStream (Port Hedland bbox)**.
- Ensure the UI reads as a **real investor terminal from first render**, prioritizing:
  - ✅ **Bottom full-width ASX heatmap strip** (watchlist-style)
  - ✅ **Right-rail prediction history** (demo track record)
  - ✅ **Cause→effect visual arc** on the globe (event → Australian market anchor)
  - ⏭️ **Top macro context strip** (auto-refreshing)

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
- Validate end-to-end interactions; fix critical UI issues (including globe click handler reliability).
- Keep simulation runtime expectations (3–5 minutes) as a feature; ensure tooling timeouts reflect this.

### Phase 3 Success Criteria
- Stable end-to-end demo flow with clear progress feedback and recoverable errors.

---

## Phase 4 — Enhancement Phase (Terminal UX + Demo Credibility) 🚧 IN PROGRESS

**Directive:** Implement in *exact* priority order **P0 → P1 → P2 → P3**.

### P0 — ASX Sector Heatmap Panel (Bottom Watchlist Strip) ✅ COMPLETE

**Goal:** Add a **bottom-of-screen, full-width, ~120px tall** watchlist panel with **5 equal-width columns**:
- BHP, RIO, FMG, CBA, LYC
- Each cell shows: **price**, **1D change ($ and %)**, and a **5-day sparkline** (SVG polyline; no chart library)

#### Backend ✅
- Enhanced `GET /api/data/asx-prices` to include **5-day lookback** data for sparklines:
  - Real mode supported via `yfinance.download(ticker, period='5d', interval='1d')`.
  - Mock mode extended with realistic 5-day arrays to keep demo stable.
- Current response schema (implemented):
  - `[{ ticker, name, price, currency, change_pct_1d, change_abs_1d, history_5d: [{date, close}], updated_at, ... }]`

#### Frontend ✅
- Implemented `frontend/src/components/SectorHeatmap.js` and `SectorHeatmap.css`.
- Rendered as **fixed bottom strip** with **5 equal columns**.
- Sparklines:
  - 5-point SVG polyline, normalized to cell height
  - Green for uptrend, red for downtrend
  - Visibility improved with slightly thicker stroke + subtle glow
- Layout reserved space using `margin-bottom: 120px` on `.main-container`.

#### Success Criteria ✅
- Heatmap strip renders instantly and does not break globe/sidebar.
- Each ticker cell shows price, daily change, and visible sparkline.

#### Testing ✅
- Backend verified: `/api/data/asx-prices` includes `history_5d` with 5 data points per ticker.
- Frontend verified: renders correctly at 1920×1080; responsive behavior acceptable.
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
- Storage:
  - `localStorage` key: `prediction_history` (JSON array)
- Safe history appends using functional state update to avoid stale writes.
- Added a minimal `min-height` to ensure the panel is always visible in the sidebar layout.

#### Success Criteria ✅
- History log renders correctly, displays last 3 entries by default, and expands/collapses.
- Persists across refresh.
- Clear history works.

#### Testing ✅
- Frontend test pass rate: **100%**.
- Test report: `/app/test_reports/iteration_5.json`.

---

### P2 — Signal Correlation Overlay (Animated Globe Arc) ✅ COMPLETE

**Goal:** Make causality spatially obvious by connecting event location to the Australian market.

#### UX Requirements ✅
- Render on the globe as a **yellow animated arc** from:
  - event lat/lon → **Australian market anchor point** (lat **-25**, lon **133**)
- Trigger: after simulation completion (when prediction is set).
- Auto-fade: **8 seconds**, then disappear.
- No additional panel.

#### Implementation Notes ✅
- **State wiring (App.js)**
  - Added `correlationArc` state: `{ show, eventLat, eventLng }`.
  - Added `arcTimeoutRef` with cleanup on unmount.
  - On prediction completion: set arc active and schedule clear after 8 seconds.
  - On subsequent prediction: clears prior timeout before scheduling a new one.
- **Globe rendering (Globe.js)**
  - Added `correlationArc` prop.
  - Implemented globe.gl `arcsData` layer with:
    - start: event coordinates
    - end: AU anchor (-25, 133)
    - styling: yellow gradient + dash animation
  - Clears arcs when `correlationArc.show` is false.

#### Success Criteria ✅
- Arc reliably activates after prediction completion.
- Arc disappears automatically after 8 seconds.
- Timeout cleanup prevents stale arcs across repeated runs.

#### Testing ✅
- Frontend code review + logical-flow verification: **100% pass**.
- Test report: `/app/test_reports/iteration_6.json`.
- Note: **Visual effect will be verified during actual 3–5 minute simulations** (expected, since triggering requires simulation completion).

---

### P3 — Economic Context Strip (Top Macro Header, Auto-Refresh) ⏭️ NEXT

**Goal:** Provide macro framing for ASX moves; investors notice stale data.

#### UX Requirements
- Top of screen, full width, **~36px** tall.
- Dark background slightly lighter than main dashboard.
- Left-to-right items with thin dividers:
  1) Fed Funds Rate
  2) AUD/USD
  3) Iron Ore Spot
  4) RBA Cash Rate
  5) ASX 200 Index

#### Frontend Requirements
- Auto-update every **5 minutes**:
  ```js
  useEffect(() => {
    fetchMacroContext();
    const interval = setInterval(fetchMacroContext, 300000);
    return () => clearInterval(interval);
  }, []);
  ```

#### Backend
- Add endpoint: `GET /api/data/macro-context`
- Fetch sources in reliability order with caching:
  - **Fed Funds Rate:** FRED series `FEDFUNDS` (no key needed); cache **1800s**
  - **AUD/USD:** Yahoo Finance `AUDUSD=X` via yfinance; cache **300s**
  - **Iron Ore Spot:** try Yahoo Finance `IRON.AX` or fallback hardcoded **$97.50/t** with “delayed” label
  - **RBA Cash Rate:** hardcode **4.10%** with last-updated date
  - **ASX 200:** Yahoo Finance `^AXJO` via yfinance; cache **300s**
- Maintain `USE_MOCK_DATA` strategy for demo stability.

#### Success Criteria
- Macro strip renders immediately.
- Data refreshes every 5 minutes.
- Degrades gracefully if a single feed fails (does not break the strip).

#### Testing
- Backend: verify payload shape, caching, and fallback behavior.
- Frontend: verify bar layout and refresh timer.

---

## 3) Next Actions (Immediate)
1. **Begin P3 (Economic Context Strip):**
   - Backend: implement `GET /api/data/macro-context` with caching + graceful fallbacks
   - Frontend: create `MacroContext` top bar component and setInterval refresh every 5 minutes
   - Wire into `App.js` header area above everything else
   - Backend + frontend smoke tests + screenshot

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED globe click → 50-agent simulation → prediction card** (ticker, direction, confidence, causal chain) in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - ✅ Bottom heatmap watchlist strip
  - ✅ Persistent prediction history
  - ✅ Globe cause→effect arc
  - ⏭️ Auto-refreshing macro context header
- System remains stable in mock mode and supports switching to live APIs without refactor.

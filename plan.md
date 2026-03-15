# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**: **Click ACLED event on 3D globe → run 50-agent simulation (3–5 rounds) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Keep infrastructure **$0** (free tiers) using **Emergent Universal LLM Key** with model split:
  - **Claude Sonnet 4.6**: ontology extraction + ReportAgent + final prediction JSON
  - **Gemini 2.5 Flash**: per-agent reasoning inside simulation rounds
  - **GPT-4.1**: fallback
- Integrate only required data sources: **ACLED**, **Yahoo Finance**, **FRED**, **AISStream (Port Hedland bbox)**.
- Ensure the UI reads as a **real investor terminal from first render**, prioritizing:
  - **Bottom full-width ASX heatmap strip** (watchlist-style)
  - **Right-rail prediction history** (demo track record)
  - **Cause→effect visual arc** on the globe
  - **Top macro context strip** (auto-refreshing)

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

**Directive:** Implement in *exact* priority order **P0 → P1 → P2 → P3**. Do **not** start P1 until P0 is visually complete and tested.

### P0 — ASX Sector Heatmap Panel (Bottom Watchlist Strip) 🔥 HIGHEST PRIORITY

**Goal:** Add a **bottom-of-screen, full-width, ~120px tall** heatmap-like watchlist panel with **5 equal-width columns**:
- BHP, RIO, FMG, CBA, LYC
- Each cell shows: **price**, **1D % change**, and a **5-day sparkline** (SVG polyline, no chart library)

#### Backend
- Enhance `GET /api/data/asx-prices` to include **5-day lookback** data for sparklines.
  - For real mode: `yfinance.download(ticker, period='5d', interval='1d')`
  - For mock mode: extend mock payload with plausible 5-day arrays.
- Return schema (proposed):
  - `[{ ticker, name, price, change_pct_1d, updated_at, history_5d: [{date, close}] }]`

#### Frontend
- Create `frontend/src/components/SectorHeatmap.js` (+ CSS).
- Render at the **bottom of the screen**, below the globe, full width.
- Sparkline:
  - Normalize 5 values to cell height; render SVG polyline.
  - Green stroke if 5-day trend is up; red if down.

#### Success Criteria
- Heatmap strip renders instantly and does not break globe/sidebar.
- Each ticker cell shows price, daily change, and sparkline.
- Verified in browser via screenshot and manual smoke test.

#### Testing
- Backend: verify endpoint returns `history_5d` (mock and/or live).
- Frontend: verify rendering/layout at 1920×1080 and no overflow issues.

---

### P1 — Prediction History Log (Right Sidebar, Collapsible)

**Goal:** Build demo credibility by showing a **session track record** of simulations.

#### UX Requirements
- Position: **Right sidebar**, **below existing ASX ticker strip**.
- Collapsible:
  - Starts **expanded**, showing **last 3 predictions**.
  - A “Show all” toggle reveals full log.
- Max height: **40% of viewport** to avoid crowding the globe.
- Persistence: `localStorage` (survives refresh).

#### Implementation Steps
- Create `frontend/src/components/PredictionHistory.js` (+ CSS).
- Add log append on simulation completion (when prediction arrives):
  - store: `{timestamp, event_id, event_summary, ticker, direction, confidence}`
- Add simple controls:
  - expand/collapse
  - optional clear log

#### Success Criteria
- After multiple simulations, log shows correct ordering and persists across refresh.

#### Testing
- Frontend-only smoke test:
  - run 2–3 simulations, refresh, confirm log persists.

---

### P2 — Signal Correlation Overlay (Animated Globe Arc)

**Goal:** Make causality spatially obvious by connecting event location to Australian market.

#### UX Requirements
- Render on the globe as a **yellow animated arc** from:
  - event lat/lon → **Australian market anchor point** (lat **-25**, lon **133**)
- Trigger: after simulation completion.
- Auto-fade: **8 seconds**, then disappear.
- No additional panel.

#### Implementation Steps
- Update `frontend/src/components/Globe.js` (and `App.js` state wiring) to:
  - store last simulated event coordinates
  - store “arc active” state with timeout
  - render arc using globe.gl arcs layer

#### Success Criteria
- Arc reliably appears after prediction and fades out after 8 seconds.

#### Testing
- Frontend interaction test:
  - trigger simulation, confirm arc shows and disappears.

---

### P3 — Economic Context Strip (Top Macro Header, Auto-Refresh)

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
  - **Iron Ore Spot:** try Yahoo Finance `IRON.AX` (or fallback hardcoded **$97.50/t** with “delayed” label); must not break strip
  - **RBA Cash Rate:** hardcode **4.10%** with last-updated date
  - **ASX 200:** Yahoo Finance `^AXJO` via yfinance; cache **300s**
- Maintain `USE_MOCK_DATA` strategy for demo stability.

#### Success Criteria
- Macro strip renders immediately, refreshes every 5 minutes, and degrades gracefully if a single feed fails.

#### Testing
- Backend: verify payload shape, caching, and fallback behavior.
- Frontend: verify bar layout and refresh timer.

---

## 3) Next Actions (Immediate)
1. **Implement P0 (Heatmap):**
   - Backend: extend `/api/data/asx-prices` to include `history_5d`.
   - Frontend: add `SectorHeatmap` bottom strip with SVG sparklines.
   - Run backend + frontend smoke tests; capture screenshot.
2. After P0 is complete and visually verified, proceed to **P1 Prediction History**.

---

## 4) Overall Success Criteria
- Demo works end-to-end: **ACLED globe click → 50-agent simulation → prediction card** (ticker, direction, confidence, causal chain) in **<5 minutes**.
- UI conveys “investor terminal” quality:
  - Bottom heatmap watchlist strip
  - Persistent prediction history
  - Globe cause→effect arc
  - Auto-refreshing macro context header
- System remains stable in mock mode and supports switching to live APIs without refactor.
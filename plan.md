# Development Plan — Market Oracle AI (ASX Intelligence MVP)

## 1) Objectives
- Deliver a **single end-to-end demo**: **Click ACLED event on 3D globe → run 50-agent simulation (3–5 rounds) → show prediction card** for one of **BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX**.
- Keep infrastructure **$0** (free tiers) using **Emergent Universal LLM Key** with model split:
  - **Claude Sonnet 4.6**: ontology extraction + ReportAgent + final prediction JSON
  - **Gemini 2.5 Flash**: per-agent reasoning inside simulation rounds
  - **GPT-4.1**: fallback
- Integrate only required data sources: **ACLED**, **Yahoo Finance**, **FRED**, **AISStream (Port Hedland bbox)**.

---

## Phase 1 — Core POC (Simulation + LLM + Output Contract)

### User Stories
1. As a developer, I can run a single script that simulates a sample ACLED event and returns a valid **prediction JSON**.
2. As a developer, I can verify 50 agents distributed across 8 personas complete **3–5 rounds** without crashes/timeouts.
3. As a developer, I can confirm **Claude Sonnet 4.6** produces **strict JSON** for the prediction card schema.
4. As a developer, I can confirm **Gemini 2.5 Flash** handles many small agent calls reliably.
5. As a developer, I can verify automatic fallback to **GPT-4.1** on provider/model failure.

### Implementation Steps
1. **Env + LLM wiring** (backend/.env)
   - Add: `EMERGENT_LLM_KEY=...`
   - Add:
     - `LLM_MODEL_NAME=claude-sonnet-4-6`
     - `BOOST_LLM_MODEL_NAME=gemini-2.5-flash`
     - `FALLBACK_LLM_MODEL_NAME=gpt-4.1`
   - Implement `llm_router.py` using `emergentintegrations.llm.chat.LlmChat` with provider/model switching.
2. **Define output contract** (single source of truth)
   - `PredictionCard` schema:
     - `ticker`, `direction` (UP|DOWN|NEUTRAL), `confidence` (0–1), `time_horizon` (h24|d7|d30), `causal_chain[]`, `agent_consensus{up,down,neutral}`, `key_signals[]`.
3. **POC simulation script** `scripts/test_core.py`
   - Input: sample event (lat/lon, country, event_type, fatalities, notes).
   - Map event → ticker via **rule-based correlation** (MVP rules only).
   - Create 50 agents w/ 8 personas; each round:
     - agents produce stance + rationale (Gemini Flash)
     - aggregate votes + extract top rationales
   - Final report: Claude Sonnet 4.6 generates strict JSON matching schema.
4. **Web research checkpoint (best practices)**
   - Quick search on: “multi-agent LLM simulation reduce cost + batch prompts + strict JSON validation” and apply 1–2 pragmatic improvements (batching, retry, JSON repair).
5. **Validation loop (do not proceed until green)**
   - Run POC 5 times; ensure:
     - JSON always parseable
     - runtime acceptable (<2–3 min locally)
     - fallback works when forced

### Phase 1 Success Criteria
- `scripts/test_core.py` consistently outputs valid `PredictionCard` JSON for multiple runs.
- Simulation completes within target time and produces non-trivial causal chains.

---

## Phase 2 — V1 App Development (Globe → Simulate → Prediction Card)

### User Stories
1. As an investor, I can view a **3D globe** with **ACLED markers**.
2. As an investor, I can click a marker and trigger a simulation with clear **loading/progress**.
3. As an investor, I can see a **prediction card** (ticker, direction, confidence, causal chain) after completion.
4. As an investor, I can see **live prices** for the 5 tracked ASX tickers.
5. As an investor, I can review a short **prediction history** of my recent runs.

### Implementation Steps
1. **Backend (FastAPI)**
   - Endpoints:
     - `GET /api/acled/events` (recent events; minimal fields; cached)
     - `GET /api/market/prices` (Yahoo Finance: BHP.AX/RIO.AX/FMG.AX/CBA.AX/LYC.AX)
     - `GET /api/macro/fred` (handful of series: DFF, CPIAUCSL, UNRATE)
     - `GET /api/ais/port-hedland` (AISStream bbox; minimal derived stats)
     - `POST /api/simulate` (input: event_id or event payload; output: PredictionCard)
     - `GET /api/predictions` (recent stored predictions)
   - Services:
     - `acled_service.py`, `yfinance_service.py`, `fred_service.py`, `ais_service.py`
     - `simulation_service.py` wraps POC logic (now productionized)
   - Storage (MongoDB): `predictions` collection storing event + outputs.
2. **Frontend (React + Vite)**
   - Layout: Globe (left/center) + right rail (Prices + Prediction Card + History).
   - Globe (globe.gl): render markers, tooltip, click handler → `POST /api/simulate`.
   - Components:
     - `GlobeView`, `PredictionCard`, `TickerStrip`, `PredictionHistory`, `LoadingOverlay`.
   - States: idle/loading/success/error; retries and user-friendly errors.
3. **Ticker mapping rules (MVP)**
   - Implement deterministic mapping from event + macro + AIS stats → one ticker:
     - Middle East escalation → commodity beta → BHP/RIO/FMG
     - Rate shock (FRED) → CBA
     - Rare earth supply disruption keywords → LYC
     - Port Hedland shipping disruption → BHP/RIO/FMG (down)
4. **Finish Phase with 1 round E2E test**
   - Manual + automated smoke: load globe → click → prediction appears.

### Phase 2 Success Criteria
- From UI: click an ACLED marker and receive a populated prediction card within **<5 minutes**.
- Prices panel reliably loads for all 5 tickers.

---

## Phase 3 — End-to-End Testing, Hardening, Performance

### User Stories
1. As QA, I can verify the main flow works for multiple events without refresh.
2. As QA, I can verify errors (ACLED down, LLM timeout) show clear messages and do not crash UI.
3. As QA, I can verify prediction JSON always validates against schema.
4. As QA, I can verify results are stored and visible in prediction history.
5. As QA, I can verify simulation completes in acceptable time across 5 runs.

### Implementation Steps
1. Add schema validation on backend (Pydantic) + JSON repair retry for ReportAgent.
2. Add rate-limit guards: cap tokens, cap rounds, cap per-agent output.
3. Add caching (in-memory) for ACLED/prices/FRED/AIS calls.
4. Add test set:
   - backend: unit tests for mapping + schema validation
   - frontend: basic interaction smoke tests
5. Run a full E2E checklist; fix until stable.

### Phase 3 Success Criteria
- 10 consecutive click→simulate runs succeed with valid cards.
- No unhandled exceptions; clear degraded-mode behavior.

---

## 3) Next Actions (Immediate)
1. Create `.env` with `EMERGENT_LLM_KEY` and model names.
2. Implement `llm_router.py` (Claude/Gemini/GPT fallback) + JSON validation helper.
3. Build `scripts/test_core.py` and iterate until POC success criteria met.
4. After POC is green, scaffold FastAPI endpoints + React globe UI and wire `POST /api/simulate`.

---

## 4) Overall Success Criteria
- Demo works: **ACLED globe click → 50-agent simulation → prediction card** (ticker, direction, confidence, causal chain) in **<5 minutes**, $0 infra.
- Prediction output is **strict JSON** and stored for history.

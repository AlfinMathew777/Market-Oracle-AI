# Agent Consensus — Gotchas

### 2026-04-05: RSI/Volume Citation Missing from Reconciler
- **Bug**: Reconciler chain_questions didn't include RSI or volume data
- **Symptom**: Causal chain never cited live RSI/volume despite being fetched
- **Fix**: Inject `rsi`, `volume_ratio`, `ticker_volume_vs_avg` into chain_questions
- **File**: `backend/services/prediction_resolver.py`

### 2026-03-28: Volume Key Mismatch in Synthesizer
- **Bug**: Synthesizer looked for `volume_ratio` but data had `ticker_volume_vs_avg`
- **Fix**: Expand volume key lookup to try multiple field names
- **Prevention**: Log the full market_data dict on failure to see what keys exist

### 2026-03-20: Legal Event Causal Logic — Fabricated Operational Impacts
- **Bug**: Legal events triggered fabricated supply-chain reasoning
- **Cause**: `chain_questions` too broad, allowed hallucinated operational impacts
- **Fix**: Constrain chain_questions for legal events to regulatory/financial impacts only
- **File**: `backend/services/catalyst_validator.py`

### 2026-03-01: Infinite Hang Bug (Fixed)
- **Bug**: Simulation hung indefinitely with no timeout
- **Cause**: Missing AbortController; hardcoded 30 agents (should be 45-50)
- **Fix**: Added timeout on all async calls; corrected agent count; AbortController on fetch
- **Prevention**: Always set a timeout on LLM calls; use semaphore to limit concurrency

### 2026-02-15: Agent Count Wrong
- **Bug**: Only 30 agents ran instead of 45-50
- **Fix**: `AGENT_COUNT = 50` in test_core.py, semaphore allows 10 concurrent
- **Prevention**: Log agent count at start of each simulation

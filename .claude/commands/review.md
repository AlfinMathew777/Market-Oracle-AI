---
description: AI-assisted code review of current changes
---

Review the current git diff for Market Oracle AI.

First, get the diff:
```bash
git diff HEAD~1 -- backend/
```

Review against these criteria:

## 1. Security (🔴 Critical)
- No hardcoded API keys, passwords, secrets
- No SQL injection vulnerabilities (use parameterized queries)
- No unsafe deserialization (json.loads OK, pickle NOT OK)
- Admin endpoints have auth checks
- `.env` files are not committed

## 2. Market Oracle Specific (🔴 Critical)
- Kill switch checked before simulations
- Data health gating before signals
- Confidence capped at 85% (hard limit)
- No hardcoded agent counts (must be 50)
- No look-ahead bias in backtests (df.index < target_date)
- Geographic logic correct (Lombok/Makassar, NOT Malacca for AU iron ore)

## 3. Code Quality (🟡 Warning)
- Type hints on all public functions
- Docstrings for public functions (Google or NumPy style)
- Functions under 50 lines
- Cyclomatic complexity under 10
- No duplicate code (DRY)

## 4. Error Handling (🟡 Warning)
- try/except around external API calls
- Loguru structured logging with context
- Graceful degradation (not crash)
- Proper HTTP status codes

## 5. Testing (🟢 Suggestion)
- New code has corresponding tests
- Edge cases covered (empty, null, error)
- Mocks for external APIs

## 6. Performance (🟢 Suggestion)
- Database queries use indexes
- Redis caching for hot paths
- Async/await for I/O operations
- No N+1 query problems

Output format:
```
## 🔴 Critical Issues (Must Fix)
- [Issue description with file:line]

## 🟡 Warnings (Should Fix)
- [Issue description with file:line]

## 🟢 Suggestions (Nice to Have)
- [Issue description with file:line]

## ✅ Good Patterns Observed
- [What was done well]

## 📊 Summary
- X critical, Y warnings, Z suggestions
- Recommendation: APPROVE / REQUEST CHANGES / NEEDS WORK
```

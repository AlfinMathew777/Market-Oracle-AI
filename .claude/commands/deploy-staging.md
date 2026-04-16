Deploy current changes to the Railway staging environment with safety checks.

## Usage
```
/deploy-staging
```

## Pre-Checks (All Must Pass)

1. Tests pass: `cd backend && pytest tests/ -q`
2. No uncommitted changes: `git status --porcelain` is empty
3. Current branch or staging branch is up to date

## Process

```bash
# Step 1: Run tests
cd backend && pytest tests/ -q
# STOP if tests fail

# Step 2: Merge to staging
git checkout staging
git merge main --no-ff -m "deploy: merge to staging $(date +%Y-%m-%d)"
git push origin staging

# Step 3: Wait for Railway to deploy (~2 minutes)
# Check Railway dashboard or wait and verify:
sleep 120

# Step 4: Verify staging
curl https://<staging-backend>.railway.app/api/health | python3 -m json.tool
# Expected: "environment": "staging"

# Step 5: Quick smoke test
curl https://<staging-backend>.railway.app/api/admin/status
```

## Expected Result

The Railway staging service (configured with `railway.staging.toml`) auto-deploys
on `staging` branch push. The header badge in the frontend will show yellow `STAGING`.

## After Deployment

Check:
- Yellow STAGING badge visible in frontend header
- `/api/health` returns `"environment": "staging"`
- `/api/admin/status` returns `"signals_enabled": true`
- No new critical alerts: `GET /api/alerts`

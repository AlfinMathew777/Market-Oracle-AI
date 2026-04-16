Deploy staging to production. Requires explicit confirmation — affects live users.

## Usage
```
/deploy-prod
```

## WARNING

This promotes staging → main and triggers a live Railway production deployment.
**Pause and confirm with the user before proceeding past the checklist.**

## Pre-Checks (All Must Pass — Hard Stops)

- [ ] Staging tests pass: `cd backend && pytest tests/ -q`
- [ ] No uncommitted changes: `git status --porcelain`
- [ ] Currently on `staging` or `main` branch
- [ ] Staging hit rate ≥ 55%: `GET /api/metrics/validation-summary?days=7`
- [ ] No critical unacknowledged alerts: `GET /api/alerts`
- [ ] Kill switch is OFF on staging: `GET /api/admin/status`
- [ ] **User has explicitly confirmed** deployment to production

## Process

```bash
# Step 1: Final staging health check
curl https://<staging-backend>.railway.app/api/health

# Step 2: Merge staging → main
git checkout main
git pull origin main
git merge staging --no-ff -m "release: promote staging to production $(date +%Y-%m-%d)"

# Step 3: Push (triggers Railway production deploy)
git push origin main

# Step 4: Monitor for 5 minutes
# Watch Railway logs + verify:
curl https://<prod-backend>.railway.app/api/health
# Expected: "environment": "production"

# Step 5: Verify no new alerts fired
curl https://<prod-backend>.railway.app/api/alerts?status=active
```

## Rollback

If production issues appear within 5 minutes:
```bash
git revert HEAD --no-edit
git push origin main
```

## Post-Deployment

- No environment badge visible in frontend (production = no badge by design)
- Verify `/api/health` returns `"environment": "production"`
- Monitor alerts for 10 minutes after deploy

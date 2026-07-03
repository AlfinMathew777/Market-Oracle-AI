# Postmortem (STUB): production DNS outage — asx.marketoracle.ai

Status: OPEN — root cause PENDING owner's dashboard check. Detected
2026-07-03 during Prediction Masters Phase C execution.

## Facts established so far

- `asx.marketoracle.ai` and `staging.asx.marketoracle.ai` return NXDOMAIN
  (checked 2026-07-03, local resolver); the apex `marketoracle.ai` resolves
  (66.71.220.1).
- Consequence: production API and frontend are unreachable from the public
  internet; live resolved-N and the track-record endpoint cannot be read;
  cron-driven resolutions may or may not still be running server-side
  (unknowable from outside).
- Duration unknown. Last provable external activity in the repo's data is
  the git-tracked DB snapshot at commit `e16532e` (rows through 2026-04-17).
  Nothing in the repo proves traffic after that date.

## Candidate root causes (owner dashboard check decides)

1. DNS records for the `asx.` subdomains removed/lapsed at the registrar or
   DNS provider while the apex survived.
2. Vercel/Railway custom-domain binding removed (e.g., project deleted,
   plan lapsed, domain verification expired) — provider would then stop
   serving the subdomain records.
3. Deployment intentionally moved to a new host without updating docs —
   in which case this is doc drift, not an outage.

## Actions

- [ ] OWNER: check Railway service status + domains, Vercel domain
      bindings, and DNS provider records for `asx.` and `staging.asx.`.
- [ ] OWNER: confirm whether backend crons (validation, resolution) have
      been running since 2026-04-17 — if not, the ledger has a gap that
      must be recorded in the resolution-protocol history.
- [ ] On restoration: record root cause + timeline here; then the
      **Stage 2a access-log window clock starts only after restoration
      PLUS 48h of stable traffic** (Phase C ruling 1). Until then Stage 2a
      is frozen and no deletion PR may cite log evidence.
- [ ] On restoration: re-run the duplicate-endpoint sweep against the real
      production host (the 2026-07-03 sweep ran against a locally-served
      snapshot; see `docs/analyses/2026-07-03-duplicate-endpoint-divergence.md`).

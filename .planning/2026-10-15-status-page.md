# Backrooms status page

Date 2026-10-15 · Branch `main` (new repo `codeclawd/backrooms-status`) · Status: building · Depends on: nothing

## Context / why
I want a public status page for Backrooms so that students can tell "Backrooms is down" from "my Wi-Fi is broken" by a
script that checks the servers every 2 minutes and publishes the result to a static page.

The site went down several times on 2026-10-14/15 (vault `wiki/School Directory.md` "Two-server failover", "Uptime +
request-cap findings": Mac mini watchdog panics, Funnel blip, 1027 cap). Owner rule (same page): never add requests
through the Cloudflare Pages Function (100k/day free cap).

## Current state (verified 2026-10-15 against origin/main 1e64762d)
- Front `https://backrooms-1k7.pages.dev`; `deploy/edge/_routes.json` excludes `/sw.js`, `/icons/*` etc., so those are
  served by Pages without the Function (free, uncapped). `deploy/edge/_worker.js:10` lists the two origins.
- `src/app/api/version/route.ts` returns `{"version": BUILD_ID}`, no DB. Both origins answered 200 directly (curl).
- DB: mini `127.0.0.1:55441`; MBP reaches it via `com.backrooms.dbtunnel` `127.0.0.1:55442`.
- Cloudflare GraphQL `pagesFunctionsInvocationsAdaptiveGroups` works with the mini token
  (`~/.config/backrooms-host/cloudflare-token`): 56,491 requests at ~15Z today.
- MBP: `/usr/bin/python3` 3.9.6, no node/jq. Mini: python3 3.14.
- Existing Hermes `backrooms-health.sh` already polls `pages.dev/api/version` every 2 min (through the Function, ~720/day).

## Decision
- **Checker**: `checker/check.py`, stdlib Python 3.9+, launchd every 120 s on the MBP (primary) and the mini (backup:
  acts only when the data is older than 6 min). Probes: `/sw.js` on the front (static, no Function), each origin's
  `/api/version` over its Funnel (not Cloudflare), a Postgres SSLRequest on the local DB port, and the GraphQL usage
  sum. Zero Pages Function requests.
- **Data**: `status.json` force-pushed as a single parentless commit to branch `data` (no history growth). Pushed
  with a per-machine write deploy key scoped to this repo only.
- **Page**: one static `index.html` on Cloudflare Pages project `backrooms-status` (no `_worker.js`, no `functions/`,
  so no Function requests). Reads `raw.githubusercontent.com/.../data/status.json` (CORS `*`, ~5 min CDN cache).
  Visitor's own "can my device reach Backrooms" check fetches `/sw.js` (static).
- Rejected: GitHub Actions cron (delays of 15-30 min reported, 60-day inactivity disable); Workers cron + KV (counts
  toward the 100k cap); redeploying Pages per check (500 deploys/month limit).

## Units of work
1. `checker/check.py` + `checker/com.backrooms.status.plist` template + `checker/README.md`.
2. `index.html` (inline CSS/JS).
3. Repo create (public), deploy keys, Pages project, launchd on both machines. **Needs owner OK (public repo).**

## Verification (Done means)
- `python3 checker/check.py --dry-run` prints a status object with 5 components, runs under `/usr/bin/python3` 3.9.
- Local page renders fixture data at 390 and 1280 widths (screenshots), stale/down/degraded fixtures render.
- After deploy: `data` branch updates every ~2 min (`git ls-remote` twice), page loads live data.
- `grep -r "_worker\|functions" ` in the deployed dir finds nothing.

## Risks & rollback
- raw.githubusercontent cache can lag up to ~5 min: page says "updates every 2 minutes, may lag a few minutes".
- Rollback: `launchctl bootout` the job on both machines; delete the Pages project / repo.

## Out of scope
Manual incident notes, email/SMS subscriptions.

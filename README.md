# Backrooms status

Public status page for Backrooms: is it down, or is it just you?

- `index.html` is the whole page (plus `icon.png` and the app's own fonts in `fonts/`). It is static files on Cloudflare
  Pages (project `backrooms-status`). It reads `status.json` from `raw.githubusercontent.com` and pings
  `backrooms.up.railway.app/api/version` from the visitor's own device.
- Backrooms runs on Railway (since 2026-10-16). `checker/check.py` runs every 2 minutes from launchd
  (`com.backrooms.status`) on the Mac mini (`ROLE=primary`), outside Railway. It checks:
  - **Backrooms app**: `/api/version` on the app's address, timed; over 2.5 s counts as slow;
  - **Database**: `/api/health`, which runs `select 1` (404 = route not deployed = unknown, not down);
  - **Old address**: `backrooms-1k7.pages.dev` answers with a redirect to the app's address.
- Results go to `status.json` on the `data` branch as one force-pushed commit (no history pile-up): per-day check
  counts, incidents, the last 120 response times and the live build id with when it first appeared. GitHub's raw CDN
  caches for up to ~5 minutes.
- If no check arrives for 12 minutes, the page says the checker went quiet and points people at the Ping button.
- History from the Mac-hosted days (servers, Cloudflare's daily cap) was dropped on the switch: the checker starts
  fresh when it finds the old `capacity` field, or with `--reset`.

## Machine setup
`~/.config/backrooms-status/` holds `check.py` (copied from `checker/`), `config`, `deploy_key` (a write deploy key
for this repo only) and `repo/` (scratch clone). Config keys: `ROLE`, `HOST`, `REPO`, `DEPLOY_KEY`, `APP`, `OLD`.
`/usr/bin/python3 check.py --dry-run` prints a check without publishing.

## Try the page locally
`python3 fixtures/make.py && python3 -m http.server 8765`, then open
`http://127.0.0.1:8765/?data=fixtures/down.json` (also `up`, `degraded`, `appdown`, `stale`). The `data` parameter
only works on localhost. `node fixtures/shots.mjs` screenshots each state in WebKit; `node fixtures/motion.mjs` checks
the animations run and stop under reduced motion.

## Deploy the page
Copy `index.html`, `icon.png` and `fonts/` into an empty folder, then
`CLOUDFLARE_API_TOKEN=$(cat ~/.config/backrooms-cf/token) CLOUDFLARE_ACCOUNT_ID=$(cat ~/.config/backrooms-cf/account) npx wrangler pages deploy <folder> --project-name backrooms-status --branch main`
(on the Mac mini).

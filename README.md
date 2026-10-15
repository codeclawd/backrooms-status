# Backrooms status

Public status page for Backrooms: is it down, or is it just you?

- `index.html` is the whole page. It is served as static files from Cloudflare Pages (project `backrooms-status`,
  no `_worker.js` and no `functions/`), so visits don't count toward the 100k/day Pages Functions cap.
- `checker/check.py` runs every 2 minutes from launchd (`com.backrooms.status`) on the MacBook Pro (`ROLE=primary`)
  and the Mac mini (`ROLE=backup`, which only runs when the data is 6+ minutes old). It checks:
  - **Website**: `/sw.js` on `backrooms-1k7.pages.dev`, a static file that skips the Pages Function;
  - **Main / Backup server**: each server's `/api/version` over its own Tailscale Funnel, not through Cloudflare;
  - **Database**: a Postgres SSLRequest on the local DB port (mini 55441, MacBook tunnel 55442);
  - **Daily capacity**: today's Pages Functions + Workers requests from Cloudflare's GraphQL API.
- Results go to `status.json` on the `data` branch as one force-pushed commit (no history pile-up). The page reads it
  from `raw.githubusercontent.com`, which caches for up to ~5 minutes.
- If no check arrives for 12 minutes, the page says the checker went quiet. The checker lives on the same home network
  as the servers, so that usually means Backrooms is down too.

## Machine setup
`~/.config/backrooms-status/` holds `check.py` (copied from `checker/`), `config`, `deploy_key` (a write deploy key
for this repo only) and `repo/` (scratch clone). Config keys: `ROLE`, `HOST`, `REPO`, `DEPLOY_KEY`, `FRONT`, `MAIN`,
`BACKUP`, `DB_PORT`, `CF_TOKEN_FILE`.

## Try the page locally
`python3 fixtures/make.py && python3 -m http.server 8765`, then open
`http://127.0.0.1:8765/?data=fixtures/down.json` (also `up`, `degraded`, `cap`, `stale`). The `data` parameter only
works on localhost.

## Deploy the page
`npx wrangler pages deploy site --project-name backrooms-status` from a folder holding only `index.html`.

# Status page on Railway data + redesign (2026-10-16)

## Context
Backrooms moved to Railway (backrooms.up.railway.app; pages.dev 302s there). The status page still probed the Macs,
the Cloudflare 100k cap and a "backup server", and its checker stopped at 2026-10-16T07:22Z (cutover.sh disabled
`com.backrooms.status` on both Macs). Owner asked: not outdated, no Mac-mini-era data, nicer UI with animations.

## Current state (verified 2026-10-17 01:25Z)
- `curl backrooms.up.railway.app/api/version` → 200 `4877fcdd`; `backrooms-1k7.pages.dev` → 302 to Railway.
- data branch `updated` = 2026-10-16T07:22:00Z, components website/main/backup/database/capacity, checker mbp.
- `~/.config/backrooms-status/check.log`: github DNS failures, then job unloaded.

## Change
1. `checker/check.py`: components app (/api/version, timed, >2.5 s slow), database (/api/health), redirect (pages.dev
   → Railway). Records `latency` (last 120) and `version`/`version_since`. Drops Mac-era history when `capacity` present.
2. App PR codeclawd/backrooms#386: `GET /api/health` (`select 1`, 5 s limit).
3. `index.html`: app's wheatpaste materials and fonts (self-hosted in `fonts/`), paste-in handbills, response-time
   sparkline that draws in with a live dot, Ping button timing the visitor's own round trip, count-up stats (last
   update shipped, clean streak, 30-day uptime), growing uptime bars, spray splatter on the stamp. All motion off under
   prefers-reduced-motion.
4. Mini config → ROLE=primary, APP/OLD keys; launchd job re-enabled.

## Units of work
1. `checker/check.py:48` probes → app/database/redirect. Why: Mac targets are gone. Accept: `--dry-run` prints 3 components.
2. `checker/check.py` `record()` latency + version. Why: sparkline and "last update" stat. Accept: dry-run shows both keys.
3. App `src/app/api/health/route.ts` (PR #386). Why: DB state separate from app. Accept: CI green, curl → `{"db":"up"}`.
4. `index.html` redesign. Why: owner ask. Accept: shots + motion check below.
5. Mini launchd + config. Why: job was unloaded by cutover. Accept: data `updated` < 4 min old.

## Sequencing
1-2 then 5 (needs new check.py). 3 independent; until it deploys the database row shows "No data". 4 independent of all.

## Out of scope
MacBook's checker (left disabled; its config still points at the Macs). Buying a domain. Any app UI change.

## Done means
- `gh api 'repos/codeclawd/backrooms-status/contents/status.json?ref=data'` → `updated` within the last 4 min and components app/database/redirect.
- WebKit shots of up/degraded/down/appdown/stale at 390/1280/1366/1440, dark + light, zero console errors.
- `node fixtures/motion.mjs`: line dash animates to 0 and 26 drops on tap; reduce → 0 animations.
- `curl -s https://backrooms-status.pages.dev | grep -c 'Big Shoulders'` → ≥1.

## Rollback
`git revert` in this repo and redeploy; `cp config.mac-era.bak config` on the mini; revert PR #386.

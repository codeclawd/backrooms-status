#!/usr/bin/env python3
"""Backrooms status checker.

launchd runs this every 2 minutes on the Mac mini (role "primary"; a machine with role "backup" only acts when the
data has gone quiet for 6 minutes). Backrooms runs on Railway, so the checker sits outside it: it asks the app's
/api/version (and times it), the database through /api/health, and whether the old pages.dev address still forwards
people to the new one. The result is status.json on the `data` branch of the public status repo, which the page reads.

Stdlib only; must run on macOS's /usr/bin/python3 (3.9).
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CONF_DIR = os.path.expanduser("~/.config/backrooms-status")
TZ = ZoneInfo("America/Chicago")  # day buckets follow the school's clock
EVERY_S = 120
BACKUP_AFTER_S = 360
DAYS_KEPT = 90
LATENCY_KEPT = 120  # last 4 hours of response times, for the page's sparkline
SLOW_MS = 2500

# Order = display order on the page.
COMPONENTS = [
    ("app", "Backrooms app", "Chat, accounts and messages"),
    ("database", "Database", "Where messages and accounts are stored"),
    ("redirect", "Old address", "backrooms-1k7.pages.dev sends you to the new one"),
]


def load_conf():
    conf = {}
    with open(os.path.join(CONF_DIR, "config")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    return conf


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_plain = urllib.request.build_opener(_NoRedirect)


def fetch(url, timeout=10):
    """(status, body, ms, location). Redirects are not followed, so the old address can be checked for one.
    status is 0 when nothing answered."""
    req = urllib.request.Request(url, headers={"User-Agent": "backrooms-status/2", "Cache-Control": "no-cache"})
    t = time.monotonic()
    try:
        with _plain.open(req, timeout=timeout) as res:
            return res.status, res.read(4096), round((time.monotonic() - t) * 1000), res.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.read(4096), round((time.monotonic() - t) * 1000), e.headers.get("Location")
    except Exception:
        return 0, b"", None, None


def probe_app(app):
    """The app answers /api/version with the live build id. Two tries 5 s apart, so one dropped packet isn't an
    outage. Returns (state, ms, version)."""
    for attempt in range(2):
        status, body, ms, _ = fetch(app + "/api/version")
        try:
            version = json.loads(body).get("version") if status == 200 else None
        except ValueError:
            version = None
        if version:
            return ("degraded" if ms > SLOW_MS else "up"), ms, version
        if attempt == 0:
            time.sleep(5)
    return "down", None, None


def probe_db(app):
    """/api/health runs `select 1` on the database. A 404 means the route isn't deployed yet: unknown, not down."""
    for attempt in range(2):
        status, body, _, _ = fetch(app + "/api/health")
        if status == 404:
            return None
        if status == 200 and b'"up"' in body:
            return "up"
        if attempt == 0:
            time.sleep(5)
    return "down"


def probe_redirect(old, app):
    """The old pages.dev address should answer with a redirect to the app's address."""
    host = urllib.parse.urlparse(app).netloc
    for attempt in range(2):
        status, _, _, loc = fetch(old + "/")
        if 300 <= status < 400 and loc and urllib.parse.urlparse(loc).netloc == host:
            return "up"
        if attempt == 0:
            time.sleep(5)
    return "down"


def summarise(c):
    """Overall state, a short incident title, and the sentence the page shows at the top."""
    if c["app"] == "down":
        return "down", "Backrooms not loading", "Backrooms isn't loading right now."
    if c["database"] == "down":
        return "down", "Database down", "The database isn't answering. Messages and sign-in won't work."
    if c["app"] == "degraded":
        return "degraded", "Running slow", "Backrooms is up but slow right now."
    if c["redirect"] == "down":
        return "degraded", "Old address not forwarding", (
            "Backrooms is working. The old pages.dev link isn't forwarding, so open the new address.")
    return "up", "", "Everything is working."


def git(repo, *args):
    """Run git with a time limit (a hung push would stop launchd from starting the next check) and put git's own
    error in the log when it fails."""
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=90)
    if r.returncode:
        raise SystemExit("git %s failed (%d): %s" % (args[0], r.returncode, r.stderr.strip()))
    return r.stdout.strip()


def ensure_repo(conf):
    repo = os.path.join(CONF_DIR, "repo")
    env_ssh = "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15" % (
        os.path.expanduser(conf["DEPLOY_KEY"]))
    os.environ["GIT_SSH_COMMAND"] = env_ssh
    if not os.path.isdir(os.path.join(repo, ".git")):
        subprocess.run(["git", "init", "-q", repo], check=True)
        git(repo, "remote", "add", "origin", conf["REPO"])
    git(repo, "config", "user.name", "backrooms-status")
    git(repo, "config", "user.email", "status@backrooms.invalid")
    return repo


def read_remote(repo):
    """Latest status.json from the data branch; {} only when the branch truly doesn't exist yet. Any other failure
    exits without publishing, so a network blip can never overwrite 90 days of history with one check."""
    r = subprocess.run(["git", "-C", repo, "ls-remote", "--exit-code", "origin", "refs/heads/data"],
                       capture_output=True, text=True, timeout=90)
    if r.returncode == 2:
        return {}
    if r.returncode:
        raise SystemExit("can't reach the status repo (%d): %s" % (r.returncode, r.stderr.strip()))
    git(repo, "fetch", "-q", "--depth=1", "origin", "data")
    return json.loads(git(repo, "show", "FETCH_HEAD:status.json"))


def publish(repo, data):
    """One parentless commit, force-pushed: the branch never grows a history."""
    with open(os.path.join(repo, "status.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    git(repo, "add", "status.json")
    tree = git(repo, "write-tree")
    commit = git(repo, "commit-tree", tree, "-m", "status " + data["updated"])
    git(repo, "push", "-q", "-f", "origin", commit + ":refs/heads/data")


def record(data, now, comps, overall, title, message, ms=None, version=None):
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.astimezone(TZ).strftime("%Y-%m-%d")

    days = data.setdefault("days", {})
    d = days.setdefault(day, {})
    for key, state in comps.items():
        if state is None:
            continue  # unknown (e.g. /api/health not deployed yet): don't count it either way
        ok, total = d.get(key, [0, 0])
        d[key] = [ok + (state != "down"), total + 1]
    for old in sorted(days)[:-DAYS_KEPT]:
        del days[old]

    # Incidents: a run of checks where the overall state isn't "up".
    incidents = data.setdefault("incidents", [])
    open_inc = incidents[-1] if incidents and incidents[-1].get("end") is None else None
    if overall != "up":
        if open_inc is None:
            open_inc = {"start": iso, "end": None, "worst": overall, "parts": [], "title": title}
            incidents.append(open_inc)
        if overall == "down" or open_inc["worst"] != "down":
            open_inc["title"] = title  # follow the current cause, but never let a "down" title fall back to "degraded"
        if overall == "down":
            open_inc["worst"] = "down"
        open_inc["parts"] = sorted(set(open_inc["parts"]) | {k for k, s in comps.items() if s in ("down", "degraded")})
        open_inc["last"] = iso
    elif open_inc is not None:
        open_inc["end"] = iso
    cutoff = (now.timestamp() - DAYS_KEPT * 86400)
    data["incidents"] = [i for i in incidents if datetime.strptime(i["start"], "%Y-%m-%dT%H:%M:%SZ")
                         .replace(tzinfo=timezone.utc).timestamp() > cutoff]

    data.update(
        updated=iso,
        every=EVERY_S,
        overall=overall,
        message=message,
        components=[{"key": k, "name": n, "about": a, "state": comps[k]} for k, n, a in COMPONENTS],
    )
    # Response times for the sparkline: [unix seconds, ms or null when the app didn't answer].
    data["latency"] = (data.get("latency") or [])[-(LATENCY_KEPT - 1):] + [[int(now.timestamp()), ms]]
    # The live build and when it first showed up, so the page can say when the last update shipped. A build seen
    # for the first time with no earlier one to compare (a fresh start) takes its merge time from GitHub instead.
    if version and version != data.get("version"):
        data["version_since"] = iso if data.get("version") else (merged_at(version) or iso)
        data["version"] = version
    data.setdefault("since", iso)  # when checks began, for the page's clean-streak counter
    return data


def merged_at(sha):
    """Commit time of a build on the private app repo, through the Mac's logged-in gh; None if that fails."""
    try:
        r = subprocess.run(["/opt/homebrew/bin/gh", "api", "repos/codeclawd/backrooms/commits/" + sha,
                            "-q", ".commit.committer.date"], capture_output=True, text=True, timeout=20)
        out = r.stdout.strip()
        return out if r.returncode == 0 and out.endswith("Z") else None
    except Exception:
        return None


def main():
    dry = "--dry-run" in sys.argv
    conf = load_conf()
    repo = None if dry else ensure_repo(conf)
    data = (read_remote(repo) if repo else None) or {}
    if "--reset" in sys.argv or "capacity" in data:
        data = {}  # history from the Mac-hosted days (servers, Cloudflare's cap) doesn't describe Railway

    now = datetime.now(timezone.utc)
    if conf.get("ROLE") == "backup" and data.get("updated") and data.get("checker") != conf["HOST"]:
        age = now.timestamp() - datetime.strptime(data["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
        if age < BACKUP_AFTER_S:
            return  # the primary checker is alive

    app_state, ms, version = probe_app(conf["APP"])
    comps = {
        "app": app_state,
        "database": probe_db(conf["APP"]) if app_state != "down" else "down",
        "redirect": probe_redirect(conf["OLD"], conf["APP"]),
    }
    overall, title, message = summarise(comps)
    data = record(data, now, comps, overall, title, message, ms, version)
    data["checker"] = conf["HOST"]
    if dry:
        print(json.dumps({k: data.get(k) for k in ("overall", "message", "components", "latency", "version", "version_since")}, indent=1))
        return
    publish(repo, data)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Backrooms status checker.

launchd runs this every 2 minutes on the MacBook Pro (role "primary") and on the Mac mini (role "backup", which only
acts when the data has gone quiet for 6 minutes, i.e. the MacBook is off). It never sends a request through the
Cloudflare Pages Function (100k/day free cap): it fetches one static file from Cloudflare's CDN, asks each server's
Tailscale Funnel directly, knocks on the database port, and reads today's request count from Cloudflare's analytics
API. The result is status.json on the `data` branch of the public status repo, which the status page reads.

Stdlib only; must run on the MacBook's /usr/bin/python3 (3.9).
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CONF_DIR = os.path.expanduser("~/.config/backrooms-status")
TZ = ZoneInfo("America/Chicago")  # day buckets follow the school's clock
EVERY_S = 120
BACKUP_AFTER_S = 360
DAYS_KEPT = 90
CAP = 100_000
ACCOUNT = "3d8f29f10b0600ebcf2167c7942ae3d5"

# Order = display order on the page.
COMPONENTS = [
    ("website", "Website", "Loading the app from Cloudflare"),
    ("main", "Main server", "Chat, accounts and messages"),
    ("backup", "Backup server", "Takes over if the main server stops"),
    ("database", "Database", "Where messages and accounts are stored"),
    ("capacity", "Daily capacity", "Cloudflare's free limit of 100,000 requests a day"),
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


def http_ok(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "backrooms-status/1", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status == 200
    except Exception:
        return False


def probe_http(url):
    """Two tries 5 s apart, so one dropped packet isn't an outage."""
    if http_ok(url):
        return "up"
    time.sleep(5)
    return "up" if http_ok(url) else "down"


def probe_db(port):
    """Postgres answers an SSLRequest with one byte, 'S' or 'N'. Through the MacBook's ssh tunnel this proves the
    tunnel AND the database on the Mac mini are alive; a bare TCP connect would only prove the tunnel listens."""
    for attempt in range(2):
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=5) as s:
                s.settimeout(5)
                s.sendall(b"\x00\x00\x00\x08\x04\xd2\x16\x2f")
                if s.recv(1) in (b"S", b"N"):
                    return "up"
        except Exception:
            pass
        if attempt == 0:
            time.sleep(5)
    return "down"


def probe_capacity(token_file):
    """Requests counted against the daily cap so far (UTC day, which is when Cloudflare resets it)."""
    try:
        with open(os.path.expanduser(token_file)) as f:
            token = f.read().strip()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        q = (
            '{viewer{accounts(filter:{accountTag:"%s"}){'
            'pagesFunctionsInvocationsAdaptiveGroups(limit:100,filter:{date_geq:"%s"}){sum{requests}}'
            'workersInvocationsAdaptive(limit:100,filter:{date_geq:"%s"}){sum{requests}}}}}' % (ACCOUNT, day, day)
        )
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/graphql",
            data=json.dumps({"query": q}).encode(),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            body = json.load(res)
        acct = body["data"]["viewer"]["accounts"][0]
        used = sum(g["sum"]["requests"] for k in acct for g in acct[k] or [])
    except Exception as e:
        print("capacity check failed:", e, file=sys.stderr)
        return None, None
    state = "down" if used >= CAP else "degraded" if used >= CAP * 0.85 else "up"
    return state, used


def summarise(c):
    """Overall state, a short incident title, and the sentence the page shows at the top."""
    if c["website"] == "down":
        return "down", "Website not loading", "Backrooms isn't loading right now."
    if c["capacity"] == "down":
        # The cap resets at 00:00 UTC: 7 pm Central in summer time, 6 pm in winter.
        reset = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(TZ)
        return "down", "Daily limit reached", (
            "Backrooms hit Cloudflare's daily limit. It comes back at %d pm Central." % (reset.hour - 12))
    if c["main"] == "down" and c["backup"] == "down":
        return "down", "Both servers down", "Both servers are down. Backrooms isn't working right now."
    if c["database"] == "down":
        return "down", "Database down", "The database isn't answering. Messages and sign-in won't work."
    if c["main"] == "down":
        return "degraded", "Main server down", "The main server is down. The backup server is running Backrooms."
    if c["capacity"] == "degraded":
        return "degraded", "Close to the daily limit", "Backrooms is close to Cloudflare's daily limit."
    if c["backup"] == "down":
        return "degraded", "Backup server offline", "Backrooms is working. The backup server is offline."
    return "up", "", "Everything is working."


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args], check=check, capture_output=True, text=True).stdout.strip()


def ensure_repo(conf):
    repo = os.path.join(CONF_DIR, "repo")
    env_ssh = "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes" % os.path.expanduser(conf["DEPLOY_KEY"])
    os.environ["GIT_SSH_COMMAND"] = env_ssh
    if not os.path.isdir(os.path.join(repo, ".git")):
        subprocess.run(["git", "init", "-q", repo], check=True)
        git(repo, "remote", "add", "origin", conf["REPO"])
    git(repo, "config", "user.name", "backrooms-status")
    git(repo, "config", "user.email", "status@backrooms.invalid")
    return repo


def read_remote(repo):
    """Latest status.json from the data branch, or None when the branch doesn't exist yet."""
    if subprocess.run(["git", "-C", repo, "fetch", "-q", "--depth=1", "origin", "data"], capture_output=True).returncode:
        return None
    try:
        return json.loads(git(repo, "show", "FETCH_HEAD:status.json"))
    except Exception:
        return None


def publish(repo, data):
    """One parentless commit, force-pushed: the branch never grows a history."""
    with open(os.path.join(repo, "status.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    git(repo, "add", "status.json")
    tree = git(repo, "write-tree")
    commit = subprocess.run(
        ["git", "-C", repo, "commit-tree", tree, "-m", "status " + data["updated"]],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    git(repo, "push", "-q", "-f", "origin", commit + ":refs/heads/data")


def record(data, now, comps, overall, title, message, used):
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.astimezone(TZ).strftime("%Y-%m-%d")

    days = data.setdefault("days", {})
    d = days.setdefault(day, {})
    for key, state in comps.items():
        if state is None:
            continue  # unknown (e.g. analytics API hiccup): don't count it either way
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
        if overall == "down":
            open_inc["worst"] = "down"
            open_inc["title"] = title
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
        capacity={"used": used, "cap": CAP},
    )
    return data


def main():
    dry = "--dry-run" in sys.argv
    conf = load_conf()
    repo = None if dry else ensure_repo(conf)
    data = (read_remote(repo) if repo else None) or {}

    now = datetime.now(timezone.utc)
    if conf.get("ROLE") == "backup" and data.get("updated") and data.get("checker") != conf["HOST"]:
        age = now.timestamp() - datetime.strptime(data["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
        if age < BACKUP_AFTER_S:
            return  # the primary checker is alive

    cap_state, used = probe_capacity(conf["CF_TOKEN_FILE"])
    comps = {
        "website": probe_http(conf["FRONT"] + "/sw.js"),
        "main": probe_http(conf["MAIN"] + "/api/version"),
        "backup": probe_http(conf["BACKUP"] + "/api/version"),
        "database": probe_db(conf["DB_PORT"]),
        "capacity": cap_state,
    }
    overall, title, message = summarise(comps)
    data = record(data, now, comps, overall, title, message, used)
    data["checker"] = conf["HOST"]
    if dry:
        print(json.dumps({k: data[k] for k in ("overall", "message", "components", "capacity")}, indent=1))
        return
    publish(repo, data)


if __name__ == "__main__":
    main()

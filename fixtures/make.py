# Builds fixture status.json files by feeding fake checks through check.record (the real code path).
import json, random, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "checker")
import check
random.seed(4)
now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
def build(final):
    data = {}
    t = now - timedelta(days=40)
    outages = [(now - timedelta(days=30, hours=3), 30, "app"), (now - timedelta(days=9, hours=5), 14, "database"),
               (now - timedelta(days=2, hours=1), 6, "redirect"), (now - timedelta(hours=20), 10, "app")]
    while t <= now:
        comps = dict(app="up", database="up", redirect="up")
        for start, mins, key in outages:
            if start <= t < start + timedelta(minutes=mins):
                comps[key] = "down"
        if t >= now - timedelta(minutes=10):
            comps.update(final)
        overall, title, msg = check.summarise(comps)
        ms = None if comps["app"] == "down" else int(random.gauss(140, 35) + (900 if random.random() < .03 else 0))
        version = "4877fcddd76c" if t < now - timedelta(hours=3) else "e6f06e25aa01"
        check.record(data, t, comps, overall, title, msg, ms, version)
        t += timedelta(minutes=30) if t < now - timedelta(days=3) else timedelta(minutes=2)
    data["checker"] = "mini"
    return data
for name, final in [("up", {}), ("degraded", {"app": "degraded"}), ("down", {"database": "down"}), ("appdown", {"app": "down"})]:
    json.dump(build(final), open(f"fixtures/{name}.json", "w"))
d = build({}); d["updated"] = (now - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ"); json.dump(d, open("fixtures/stale.json", "w"))
print("ok", len(json.dumps(d)), "bytes")

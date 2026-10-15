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
    outages = [(now - timedelta(days=30, hours=3), 30, "main"), (now - timedelta(days=9, hours=5), 14, "website"),
               (now - timedelta(days=2, hours=1), 6, "capacity"), (now - timedelta(hours=20), 10, "main")]
    while t <= now:
        comps = dict(website="up", main="up", backup="up", database="up", capacity="up")
        for start, mins, key in outages:
            if start <= t < start + timedelta(minutes=mins):
                comps[key] = "down"
        if t >= now - timedelta(minutes=10):
            comps.update(final)
        overall, title, msg = check.summarise(comps)
        check.record(data, t, comps, overall, title, msg, 56689)
        t += timedelta(minutes=30) if t < now - timedelta(days=3) else timedelta(minutes=2)
    data["checker"] = "mbp"
    return data
for name, final in [("up", {}), ("degraded", {"main": "down"}), ("down", {"database": "down"}), ("cap", {"capacity": "down"})]:
    json.dump(build(final), open(f"fixtures/{name}.json", "w"))
d = build({}); d["updated"] = (now - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ"); json.dump(d, open("fixtures/stale.json", "w"))
print("ok", len(json.dumps(d)), "bytes")

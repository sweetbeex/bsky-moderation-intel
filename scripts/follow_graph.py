#!/usr/bin/env python3
"""Follow-graph evidence: how densely the naomivip.xyz accounts follow each
other versus the rest of Bluesky, and how mutual the internal edges are."""
import json, os, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

API = "https://api.bsky.app/xrpc"
S = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}

roster = json.load(open(f"{S}/naomivip_roster.json"))
live = [r for r in roster if r.get("createdAt")]


def api(path, **p):
    url = f"{API}/{path}?" + urllib.parse.urlencode(p)
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1 + a)
    return {}


def follows(did):
    out, cur = [], None
    for _ in range(6):
        kw = {"actor": did, "limit": 100}
        if cur:
            kw["cursor"] = cur
        d = api("app.bsky.graph.getFollows", **kw)
        out += d.get("follows", [])
        cur = d.get("cursor")
        if not cur:
            break
    return out


print(f"pulling follow lists for {len(live)} accounts", flush=True)
with ThreadPoolExecutor(max_workers=8) as ex:
    fl = dict(zip([r["handle"] for r in live], ex.map(follows, [r["did"] for r in live])))

cluster = {r["handle"] for r in live}
internal = 0
total = 0
per = {}
for h, lst in fl.items():
    t = len(lst)
    i = sum(1 for f in lst if f.get("handle") in cluster)
    per[h] = {"follows_listed": t, "follows_internal": i}
    total += t
    internal += i

print(f"\ncluster accounts: {len(live)}")
print(f"total follow edges listed: {total}")
print(f"edges pointing at another cluster account: {internal} "
      f"({internal/total*100:.1f}%)")
print(f"mean internal follows per account: {internal/len(per):.1f} "
      f"(chance if random over network is far below this)")

# mutual internal edges
edge = set()
for h, lst in fl.items():
    for f in lst:
        if f.get("handle") in cluster:
            edge.add((h, f["handle"]))
mutual = sum(1 for (a, b) in edge if (b, a) in edge)
print(f"directed internal edges: {len(edge)}  mutual pairs: {mutual} "
      f"({mutual/max(1,len(edge))*100:.0f}% reciprocated)")

# do they follow the target account?
tgt = "bs067.naomivip.xyz"
followers_of_target = [h for h, lst in fl.items() if any(f.get("handle") == tgt for f in lst)]
print(f"\ncluster accounts following the reported target {tgt}: {len(followers_of_target)}")

# control: pick 3 random non-cluster accounts of similar size, measure how many
# of their follows land on the cluster (they should be near zero)
ctrl = defaultdict(list)
for h, lst in fl.items():
    for f in lst:
        if f.get("handle") not in cluster:
            ctrl[f["handle"]].append(h)
hits = [(o, len(v)) for o, v in ctrl.items() if v]
print(f"non-cluster accounts followed by >=1 cluster account: {len(hits)}")
print("  most-followed outsiders:", sorted(hits, key=lambda x: -x[1])[:8])

json.dump({"per_account": per,
           "internal_edges": sorted([list(e) for e in edge]),
           "target": tgt,
           "cluster_following_target": followers_of_target},
          open(f"{S}/follow_graph.json", "w"), indent=1)

print("\ntop internal-followers:")
for h, v in sorted(per.items(), key=lambda kv: -kv[1]["follows_internal"])[:10]:
    print(f"  {h:24s} {v['follows_internal']:3d} / {v['follows_listed']:3d}")

print("\noutreach fan-in distribution (how many cluster accounts follow a given outsider):")
fan = Counter(len(v) for v in ctrl.values())
for n, c in sorted(fan.items())[:12]:
    print(f"  followed by {n:2d} cluster account(s): {c} outsiders")
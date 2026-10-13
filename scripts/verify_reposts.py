#!/usr/bin/env python3
"""Verify that the 496 internal 'repost' edges are real repost records.

For a sample of (reposter, target) pairs, look up the target post URI from
pass-1 data and call getPostEngagement to confirm the reposting DID appears
in the repost list. Also pulls the exact repost AT URIs for the report.
"""
import json, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.bsky.app/xrpc"
S = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}

deep = json.load(open(f"{S}/naomivip_cluster.json"))
roster = {r["did"]: r["handle"] for r in json.load(open(f"{S}/naomivip_roster.json")) if r.get("did")}

did_of_handle = {v: k for k, v in roster.items()}


def api(path, **p):
    url = f"{API}/{path}?" + urllib.parse.urlencode(p)
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1 + a)
    return {}


# rebuild edges WITH the reposted post URI, straight from the author feed
edges = []
for did, rec in deep.items():
    cursor = None
    for _ in range(5):
        kw = {"actor": did, "limit": 100, "filter": "posts_no_replies"}
        if cursor:
            kw["cursor"] = cursor
        d = api("app.bsky.feed.getAuthorFeed", **kw)
        for it in d.get("feed", []):
            rsn = it.get("reason") or {}
            if rsn.get("$type") == "app.bsky.feed.defs#reasonRepost":
                tgt = it["post"]["author"]["handle"]
                if tgt.endswith("naomivip.xyz"):
                    edges.append({
                        "reposter": rec["handle"], "reposter_did": did,
                        "target": tgt, "target_did": it["post"]["author"]["did"],
                        "post_uri": it["post"]["uri"],
                        "repost_uri": rsn.get("repost", {}).get("uri"),
                        "at": it["post"].get("indexedAt"),
                    })
        cursor = d.get("cursor")
        if not cursor:
            break

print(f"internal repost edges re-derived from feeds: {len(edges)}")
print("sample:", json.dumps(edges[0], indent=1) if edges else "none")

# verify a sample against getPostEngagement
sample = edges[:: max(1, len(edges) // 12)][:12]


def verify(e):
    d = api("app.bsky.feed.getPostEngagement", uri=e["post_uri"])
    reps = d.get("repostedBy") or []
    handles = [r["handle"] for r in reps]
    return e["post_uri"].rsplit("/", 1)[-1], e["reposter"], e["reposter"] in handles, handles[:6]


with ThreadPoolExecutor(max_workers=6) as ex:
    ver = list(ex.map(verify, sample))

print("\nverification of repost edges (target post -> is the reposter actually in repostedBy):")
ok = 0
for rkey, rep, present, who in ver:
    print(f"  post {rkey}  reposter={rep:24s} present={present}  repostedBy={who}")
    ok += bool(present)
print(f"\nconfirmed {ok}/{len(ver)} sampled edges are genuine repost records")

json.dump(edges, open(f"{S}/repost_edges.json", "w"), indent=1)
print(f"wrote repost_edges.json with {len(edges)} edges")
#!/usr/bin/env python3
"""Partial ground-truth verification of the repost ring.

Constraint discovered 2026-10-13: the cluster's home PDS
(pds.34-154-29-79.sslip.io, 66/87 accounts) is unreachable from this host
(TCP 443 refused), and the only reachable AppView (api.bsky.app) returns
501 for app.bsky.feed.getPostEngagement. So repo-level confirmation is
possible only for the 21 accounts on Bluesky-hosted PDSs.

For those, read app.bsky.feed.repost records straight from the repo and
compare against the feed-derived edges.
"""
import json, os, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

PLC = "https://plc.directory"
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}
S = os.path.dirname(os.path.abspath(__file__))


def get(url, tries=3):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1 + a)
    return {"__err__": True}


roster = json.load(open(f"{S}/naomivip_roster.json"))
live = [r for r in roster if r.get("did") and r.get("createdAt")]
feed_edges = json.load(open(f"{S}/repost_edges.json"))

feed_pairs = Counter((e["reposter"], e["target"]) for e in feed_edges)
feed_by_reposter = Counter(e["reposter"] for e in feed_edges)


def pds_for(did):
    d = get(f"{PLC}/{did}")
    return next((s.get("serviceEndpoint") for s in d.get("service", [])
                 if s.get("type") == "AtprotoPersonalDataServer"), None)


with ThreadPoolExecutor(max_workers=10) as ex:
    hosts = list(ex.map(pds_for, [r["did"] for r in live]))
for r, h in zip(live, hosts):
    r["pds"] = h

by_did = {r["did"]: r["handle"] for r in live}
reachable = [r for r in live if r.get("pds") and "bsky.network" in r["pds"]]
unreachable = [r for r in live if not (r.get("pds") and "bsky.network" in r["pds"])]
print(f"accounts on reachable (Bluesky-hosted) PDS: {len(reachable)}")
print(f"accounts on unreachable custom PDS:        {len(unreachable)}")
print(f"custom PDS in use: {sorted({r['pds'] for r in unreachable})}\n")


def reposts_of(r):
    out, cur = [], None
    for _ in range(6):
        url = (f"{r['pds']}/xrpc/com.atproto.repo.listRecords"
               f"?repo={r['did']}&collection=app.bsky.feed.repost&limit=100")
        if cur:
            url += f"&cursor={urllib.parse.quote(cur)}"
        d = get(url)
        if "__err__" in d:
            return r, [], False
        out += d.get("records", [])
        cur = d.get("cursor")
        if not cur:
            break
    return r, out, True


with ThreadPoolExecutor(max_workers=6) as ex:
    res = list(ex.map(reposts_of, reachable))

repo_pairs = set()
total_records = 0
detail = {}


def subject_did(subject):
    """app.bsky.feed.repost records carry subject.uri + subject.cid, NOT
    subject.did. The author DID has to be parsed out of the URI authority."""
    uri = (subject or {}).get("uri", "")
    if uri.startswith("at://"):
        return uri[5:].split("/", 1)[0]
    return (subject or {}).get("did", "")


for r, recs, ok in res:
    detail[r["handle"]] = {"pds": r["pds"], "read_ok": ok,
                           "repost_records": len(recs)}
    for rec in recs:
        sd = subject_did((rec.get("value") or {}).get("subject"))
        if sd in by_did:
            repo_pairs.add((r["handle"], by_did[sd]))
        total_records += 1

print(f"repost records read from repos: {total_records}")
print(f"internal repost pairs confirmed at repo level: {len(repo_pairs)}")

feed_for_those = {(a, b) for (a, b) in feed_pairs if a in {r['handle'] for r in reachable}}
print(f"feed-derived internal pairs for those same accounts: {len(feed_for_those)}")
agree = repo_pairs & feed_for_those
print(f"agreement between feed-derived and repo ground truth: {len(agree)}")
only_feed = feed_for_those - repo_pairs
only_repo = repo_pairs - feed_for_those
print(f"  in feed only: {len(only_feed)}   in repo only: {len(only_repo)}")
for p in list(only_feed)[:6]:
    print(f"    feed-only: {p}")
for p in list(only_repo)[:6]:
    print(f"    repo-only: {p}")

# timestamp burst check on the records we did read
import datetime as dt
stamps = []
for r, recs, ok in res:
    for rec in recs:
        v = (rec.get("value") or {}).get("createdAt")
        if v:
            stamps.append((v, r["handle"]))
stamps.sort()
if stamps:
    gaps = []
    byh = defaultdict(list)
    for v, h in stamps:
        byh[h].append(v)
    for h, lst in byh.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            fa = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
            fb = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
            gaps.append((fb - fa).total_seconds())
    gaps.sort()
    print(f"\nrepo-record repost gaps (n={len(gaps)}): median={gaps[len(gaps)//2]:.0f}s "
          f"min={gaps[0]:.0f}s  under-30s={sum(1 for g in gaps if g < 30)}")
    sec = Counter(v for v, _ in stamps)
    print("same-second multi-account repost clusters:")
    for k, n in sec.most_common(4):
        if n > 1:
            print(f"  {k}  {n} accounts: {sorted({h for v,h in stamps if v==k})}")

json.dump({"repo_pairs": sorted([list(p) for p in repo_pairs]),
           "feed_pairs_for_reachable": sorted([list(p) for p in feed_for_those]),
           "per_account": detail,
           "reachable": [r["handle"] for r in reachable],
           "unreachable_pds": sorted({r["pds"] for r in unreachable})},
          open(f"{S}/repost_ground_truth.json", "w"), indent=1)
print("\nwrote repost_ground_truth.json")
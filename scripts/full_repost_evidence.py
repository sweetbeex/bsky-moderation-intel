#!/usr/bin/env python3
"""Full ground-truth repost evidence for the naomivip.xyz cluster.

Reads app.bsky.feed.repost from each account's own repo. Note: subject.uri
carries the author DID, there is no subject.did field (an earlier pass that
read subject.did returned 0 internal edges and was a false negative).

The cluster's home PDS pds.34-154-29-79.sslip.io went unreachable during the
investigation; those accounts fall back to the AppView author feed.
"""
import json, os, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

PLC = "https://plc.directory"
API = "https://api.bsky.app/xrpc"
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}
S = os.path.dirname(os.path.abspath(__file__))


def get(url, tries=3, timeout=25):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1 + a)
    return None


def subject_did(subject):
    uri = (subject or {}).get("uri", "")
    if uri.startswith("at://"):
        return uri[5:].split("/", 1)[0]
    return (subject or {}).get("did", "")


roster = json.load(open(f"{S}/naomivip_roster.json"))
live = [r for r in roster if r.get("did") and r.get("createdAt")]


def pds_for(did):
    d = get(f"{PLC}/{did}")
    if not d:
        return None
    return next((s.get("serviceEndpoint") for s in d.get("service", [])
                 if s.get("type") == "AtprotoPersonalDataServer"), None)


with ThreadPoolExecutor(max_workers=12) as ex:
    hosts = list(ex.map(pds_for, [r["did"] for r in live]))
for r, h in zip(live, hosts):
    r["pds"] = h

by_did = {r["did"]: r["handle"] for r in live}
cluster = set(by_did)


def via_repo(r):
    out, cur = [], None
    for _ in range(8):
        url = (f"{r['pds']}/xrpc/com.atproto.repo.listRecords"
               f"?repo={r['did']}&collection=app.bsky.feed.repost&limit=100")
        if cur:
            url += f"&cursor={urllib.parse.quote(cur)}"
        d = get(url, tries=2, timeout=20)
        if not d:
            return r, out, "unreachable"
        out += d.get("records", [])
        cur = d.get("cursor")
        if not cur:
            break
    return r, out, "repo"


def via_appview(did):
    out, cur = [], None
    for _ in range(8):
        url = (f"{API}/app.bsky.feed.getAuthorFeed?actor={did}&limit=100"
               f"&filter=posts_no_replies" + (f"&cursor={urllib.parse.quote(cur)}" if cur else ""))
        d = get(url, tries=3)
        if not d:
            break
        for it in d.get("feed", []):
            rsn = it.get("reason") or {}
            if rsn.get("$type") == "app.bsky.feed.defs#reasonRepost":
                p = it["post"]
                out.append({"value": {"subject": {"uri": p["uri"]},
                                      "createdAt": p.get("indexedAt")},
                            "source": "appview"})
        cur = d.get("cursor")
        if not cur:
            break
    return out


print("pulling repost records (repo first, AppView fallback)", flush=True)
internal, external, method = [], [], {}
with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(via_repo, live))

for r, recs, how in results:
    if how != "repo" or not recs:
        recs = via_appview(r["did"])
        how = "appview"
    method[r["handle"]] = how
    n_in = 0
    for rec in recs:
        sd = subject_did((rec.get("value") or {}).get("subject"))
        uri = (rec.get("value") or {}).get("subject", {}).get("uri", "")
        edge = {
            "reposter": r["handle"], "reposter_did": r["did"],
            "subject_did": sd, "subject_handle": by_did.get(sd),
            "subject_uri": uri,
            "createdAt": (rec.get("value") or {}).get("createdAt"),
            "source": how,
        }
        if sd in cluster:
            internal.append(edge)
            n_in += 1
        else:
            external.append(edge)
    print(f"  {r['handle']:24s} {how:8s} {len(recs):3d} reposts, {n_in:3d} internal", flush=True)

print(f"\ninternal repost edges: {len(internal)}")
print(f"external reposts    : {len(external)}")
print(f"via repo            : {sum(1 for v in method.values() if v == 'repo')}")
print(f"via appview fallback: {sum(1 for v in method.values() if v == 'appview')}")
print(f"accounts with >=1 internal repost: {len({e['reposter'] for e in internal})} / {len(live)}")

import datetime as dt
byh = defaultdict(list)
for e in internal:
    if e["createdAt"]:
        byh[e["reposter"]].append(e["createdAt"])
gaps = []
for h, lst in byh.items():
    lst.sort()
    for a, b in zip(lst, lst[1:]):
        fa = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        fb = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
        gaps.append(((fb - fa).total_seconds(), h))
gaps.sort()
if gaps:
    print(f"\nintra-account repost gaps: n={len(gaps)} median={gaps[len(gaps)//2][0]:.0f}s "
          f"min={gaps[0][0]:.0f}s  <30s={sum(1 for g in gaps if g[0] < 30)}")

sec = Counter(e["createdAt"] for e in internal if e["createdAt"])
multi = [(k, n) for k, n in sec.most_common(6) if n > 1]
if multi:
    print("\nsame-second multi-account repost bursts:")
    for k, n in multi:
        print(f"  {k}  {n} accounts")

json.dump(internal, open(f"{S}/cluster_reposts.json", "w"), indent=1)
json.dump(external, open(f"{S}/cluster_reports.json", "w"), indent=1)
json.dump({"method": method,
           "per_account": {h: {"source": method[h],
                               "internal": sum(1 for e in internal if e["reposter"] == h),
                               "external": sum(1 for e in external if e["reposter"] == h)}
                           for h in method}},
          open(f"{S}/per_account_reposts.json", "w"), indent=1)
print("\nwrote cluster_reposts.json, cluster_reports.json, per_account_reposts.json")
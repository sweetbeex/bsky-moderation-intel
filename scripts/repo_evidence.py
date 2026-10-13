#!/usr/bin/env python3
"""Authoritative cluster evidence, pulled from each account's own PDS repo.

Why the PDS and not the public API: on this host api.bsky.app returns 501 for
com.atproto.identity.resolveIdentity and app.bsky.feed.getPostEngagement, so
feed-derived 'repost' claims could not be independently confirmed. The repo
record list is the ground truth: one app.bsky.feed.repost record per repost,
with its subject DID/URI and createdAt.

Outputs:
  cluster_reposts.json  every internal repost edge with record URI + timestamp
  cluster_reports.json  outbound reposts leaving the cluster
  summary printed to stdout
"""
import json, os, time, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

PLC = "https://plc.directory"
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}
S = os.path.dirname(os.path.abspath(__file__))


def get(url, tries=4):
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = f"{type(e).__name__}"
            time.sleep(1 + a * 1.5)
    return {"__err__": last}


roster = json.load(open(f"{S}/naomivip_roster.json"))
live = [r for r in roster if r.get("did") and r.get("createdAt")]
by_did = {r["did"]: r for r in live}
cluster_dids = set(by_did)

# resolve each account's own PDS host straight from plc.directory
def pds_for(did):
    d = get(f"{PLC}/{did}")
    return next((s.get("serviceEndpoint") for s in d.get("service", [])
                 if s.get("type") == "AtprotoPersonalDataServer"), None)


print(f"resolving PDS hosts for {len(live)} accounts", flush=True)
with ThreadPoolExecutor(max_workers=10) as ex:
    hosts = list(ex.map(pds_for, [r["did"] for r in live]))
for r, h in zip(live, hosts):
    r["pds"] = h
print("  PDS hosts:", Counter(h for h in hosts).most_common())


def list_collection(did, host, coll, limit=100):
    out, cur = [], None
    for _ in range(6):
        url = f"{host}/xrpc/com.atproto.repo.listRecords?repo={did}&collection={coll}&limit={limit}"
        if cur:
            url += f"&cursor={urllib.parse.quote(cur)}"
        d = get(url)
        if "__err__" in d:
            return out, d["__err__"]
        out += d.get("records", [])
        cur = d.get("cursor")
        if not cur:
            break
    return out, None


def reposts_of(r):
    if not r.get("pds"):
        return r["handle"], [], "no-pds"
    recs, err = list_collection(r["did"], r["pds"], "app.bsky.feed.repost")
    return r["handle"], recs, err


print("\npulling app.bsky.feed.repost records from each account's repo", flush=True)
with ThreadPoolExecutor(max_workers=8) as ex:
    res = list(ex.map(reposts_of, live))

internal, outbound, per_acct = [], [], {}
total_reposts = 0
errs = 0
for handle, recs, err in res:
    if err:
        errs += 1
    ins = outs = 0
    for rec in recs:
        subj = (rec.get("value") or {}).get("subject") or {}
        sd = subj.get("did", "")
        uri = subj.get("uri", "")
        did = by_did[handle]["did"]
        e = {"reposter": handle, "reposter_did": did,
             "record_uri": rec.get("uri"), "record_cid": rec.get("cid"),
             "createdAt": (rec.get("value") or {}).get("createdAt"),
             "subject_did": sd, "subject_uri": uri,
             "subject_handle": by_did.get(sd, {}).get("handle")}
        total_reposts += 1
        if sd in cluster_dids:
            internal.append(e)
            ins += 1
        else:
            outbound.append(e)
            outs += 1
    per_acct[handle] = {"internal": ins, "outbound": outs,
                        "pds": next((r["pds"] for r in live if r["handle"] == handle), None),
                        "err": err}

print(f"\nrepo reads failed for {errs} accounts")
print(f"total repost records: {total_reposts}")
print(f"  internal (target inside cluster): {len(internal)}")
print(f"  outbound  (target outside)     : {len(outbound)}")
print(f"accounts reposting >=1 cluster account: "
      f"{sum(1 for v in per_acct.values() if v['internal'])} / {len(per_acct)}")

# reciprocation
edges = {(e["reposter"], e["subject_handle"]) for e in internal}
mutual = sum(1 for a, b in edges if (b, a) in edges)
print(f"directed internal repost edges: {len(edges)}, mutually reciprocated: {mutual} "
      f"({mutual/max(1,len(edges))*100:.0f}%)")

# burst analysis: repost timestamps clustered seconds apart
ts = sorted(e["createdAt"] for e in internal if e["createdAt"])
print(f"\ninternal repost timestamps: {ts[0]} .. {ts[-1]}")
# gaps within each account
byh = defaultdict(list)
for e in internal:
    if e["createdAt"]:
        byh[e["reposter"]].append(e["createdAt"])
gaps = []
for h, lst in byh.items():
    lst.sort()
    for a, b in zip(lst, lst[1:]):
        import datetime as dt
        fa = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        fb = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
        gaps.append(((fb - fa).total_seconds(), h))
gaps.sort()
if gaps:
    sub120 = sum(1 for g, _ in gaps if g < 120)
    sub10 = sum(1 for g, _ in gaps if g < 10)
    print(f"intra-account repost gaps: n={len(gaps)} "
          f"median={gaps[len(gaps)//2][0]:.0f}s  <10s={sub10}  <120s={sub120}")

# cross-account synchronization: reposts landing in the same second
sec = Counter(e["createdAt"] for e in internal if e["createdAt"])
top = sec.most_common(5)
print("same-second internal repost clusters (different accounts acting together):")
for k, n in top:
    who = [e["reposter"] for e in internal if e["createdAt"] == k]
    print(f"  {k}  {n} reposts: {sorted(set(who))}")

json.dump(internal, open(f"{S}/cluster_reposts.json", "w"), indent=1)
json.dump(outbound, open(f"{S}/cluster_reports.json", "w"), indent=1)
json.dump(per_acct, open(f"{S}/per_account_reposts.json", "w"), indent=1)
print(f"\nwrote cluster_reposts.json ({len(internal)}), cluster_reports.json ({len(outbound)})")

print("\ntop amplifiers (most cluster accounts reposted):")
tgt = Counter(e["subject_handle"] for e in internal)
for h, n in tgt.most_common(12):
    print(f"  {h:24s} reposted by {n} cluster accounts")
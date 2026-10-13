#!/usr/bin/env python3
"""Second pass: resolve every bs###.naomivip.xyz handle to a DID and capture
even accounts whose profile fetch fails (deleted/suspended), so the report
list is complete. Retries with backoff, no DNS shims.
"""
import json, os, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.bsky.app/xrpc"
S = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}


def get(url, tries=4):
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            last = f"http{e.code}"
            if e.code in (400, 404, 403):
                time.sleep(0.8 + a)
            else:
                time.sleep(2 + a)
        except Exception as e:
            last = type(e).__name__
            time.sleep(2 + a)
    return None, last


def api(path, **p):
    return get(f"{API}/{path}?" + urllib.parse.urlencode(p))


def one(h):
    rec = {"handle": h}
    d, err = api("com.atproto.identity.resolveHandle", handle=h)
    if not d or not d.get("did"):
        rec["resolve_error"] = err
        return rec
    rec["did"] = d["did"]
    p, perr = api("app.bsky.actor.getProfile", actor=d["did"])
    if p:
        rec.update({
            "displayName": p.get("displayName"),
            "description": (p.get("description") or "").replace("\n", " | "),
            "createdAt": p.get("createdAt"),
            "followers": p.get("followersCount"),
            "follows": p.get("followsCount"),
            "posts": p.get("postsCount"),
            "labels": [l.get("val") for l in p.get("labels", [])],
        })
    else:
        rec["profile_error"] = perr
    return rec


handles = [f"bs{i:03d}.naomivip.xyz" for i in range(101)]
with ThreadPoolExecutor(max_workers=8) as ex:
    rows = list(ex.map(one, handles))

live = [r for r in rows if r.get("did") and r.get("createdAt")]
noprofile = [r for r in rows if r.get("did") and not r.get("createdAt")]
nodid = [r for r in rows if not r.get("did")]

json.dump(rows, open(f"{S}/naomivip_roster.json", "w"), indent=1)

print(f"probed      : {len(rows)}")
print(f"with DID+live: {len(live)}")
print(f"DID, no profile (deleted/suspended): {len(noprofile)}")
for r in noprofile:
    print(f"   {r['handle']}  {r['did']}  {r.get('profile_error')}")
print(f"no DID (handle never registered / released): {len(nodid)}")

# merge the pass-1 deep data
deep = json.load(open(f"{S}/naomivip_cluster.json"))
pd_by_did = {r["did"]: r["pds"] for r in deep.values()}
miss = [r["handle"] for r in live if r["did"] not in deep]
print(f"\nnew accounts not in pass 1: {len(miss)} -> {miss}")
for r in live:
    r["pds"] = pd_by_did.get(r["did"])
json.dump(rows, open(f"{S}/naomivip_roster.json", "w"), indent=1)

print("\nfull report roster:")
for r in sorted(rows, key=lambda x: x["handle"]):
    if r.get("did"):
        print(f"  {r['handle']:24s} {r['did']}  {str(r.get('displayName')):22s} "
              f"{(r.get('createdAt') or 'NO-PROFILE')[:10]}  "
              f"f{r.get('followers')}/{r.get('follows')}/{r.get('posts')}  {r.get('pds')}")
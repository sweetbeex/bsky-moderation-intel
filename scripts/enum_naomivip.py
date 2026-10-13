#!/usr/bin/env python3
"""Enumerate the naomivip.xyz Bluesky bot cluster and collect moderation evidence.

Host notes (2026-10-13): public.bsky.app does not resolve from this box;
api.bsky.app and plc.directory work. com.atproto.identity.resolveIdentity is
not implemented on api.bsky.app, so DID service endpoints are read from
plc.directory directly.
"""
import csv, hashlib, io, json, os, time, urllib.parse, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

API = "https://api.bsky.app/xrpc"
PLC = "https://plc.directory"
OUT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def get(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {"__nf__": True}
            time.sleep(1.0 + a)
        except Exception:
            time.sleep(1.0 + a)
    return {"__err__": True}


def api(path, **p):
    return get(f"{API}/{path}?" + urllib.parse.urlencode(p))


def img_fp(url):
    if not url:
        return None, None
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        sha = hashlib.sha256(raw).hexdigest()
        if not HAVE_PIL:
            return sha, None
        im = Image.open(io.BytesIO(raw)).convert("L").resize((17, 16))
        px = list(im.getdata())
        bits = "".join("1" if px[y * 17 + x] > px[y * 17 + x + 1] else "0"
                       for y in range(16) for x in range(16))
        return sha, format(int(bits, 2), "016x")
    except Exception:
        return None, None


def probe(h):
    return h if api("com.atproto.identity.resolveHandle", handle=h).get("did") else None


# ---------- discovery: brute force the bs###.naomivip.xyz schema ----------
cands = set()
for i in range(0, 501):
    cands |= {f"bs{i:03d}.naomivip.xyz", f"bs{i:04d}.naomivip.xyz", f"bs{i}.naomivip.xyz"}
cands.add("naomivip.xyz")
cands = sorted(cands)
print(f"probing {len(cands)} candidate handles", flush=True)

with ThreadPoolExecutor(max_workers=24) as ex:
    handles = sorted({h for h in ex.map(probe, cands) if h})
print(f"\n{len(handles)} live handles under naomivip.xyz\n", flush=True)

# ---------- per-account evidence ----------


def collect(h):
    prof = api("app.bsky.actor.getProfile", actor=h)
    if not prof.get("did"):
        return None
    did = prof["did"]
    doc = get(f"{PLC}/{did}")
    pds = next((s.get("serviceEndpoint") for s in doc.get("service", [])
                if s.get("type") == "AtprotoPersonalDataServer"), None)
    sha, dh = img_fp(prof.get("avatar"))

    posts, cursor = [], None
    for _ in range(5):
        kw = {"actor": did, "limit": 100, "filter": "posts_no_replies"}
        if cursor:
            kw["cursor"] = cursor
        d = api("app.bsky.feed.getAuthorFeed", **kw)
        posts += d.get("feed", [])
        cursor = d.get("cursor")
        if not cursor:
            break

    orig, reposts, texts, domains = [], [], [], set()
    for it in posts:
        p = it.get("post", {})
        rec = p.get("record", {}) or {}
        t = rec.get("text", "")
        texts.append(t)
        for tok in t.replace("\n", " ").split():
            if "://" in tok or "." in tok:
                domains.add(tok.strip("#().,").split("/")[2] if "://" in tok else tok.strip("#().,"))
        for e in (rec.get("facets") or []):
            u = ((e.get("features") or [{}])[0] or {}).get("uri", "")
            if "://" in u:
                domains.add(u.split("#")[0].split("?")[0].split("/")[2])
        if (it.get("reason") or {}).get("$type") == "app.bsky.feed.defs#reasonRepost":
            a = p.get("author", {})
            reposts.append((a.get("handle"), a.get("did")))
        else:
            orig.append(p.get("indexedAt"))
        for u in ((rec.get("embed") or {}).get("external") or {}).get("uris", []) or []:
            if "://" in u:
                domains.add(u.split("/")[2])

    labels = [{"val": l.get("val"), "src": l.get("src"), "cts": l.get("cts")}
              for l in prof.get("labels", [])]
    cluster = lambda s: bool(s) and s.endswith("naomivip.xyz")

    return {
        "handle": h, "did": did,
        "displayName": prof.get("displayName"),
        "description": (prof.get("description") or "").replace("\n", " | "),
        "createdAt": prof.get("createdAt"),
        "followers": prof.get("followersCount"), "follows": prof.get("followsCount"),
        "posts": prof.get("postsCount"),
        "pds": pds,
        "avatar_sha256": sha, "avatar_dhash": dh,
        "reposts_of_cluster": sum(1 for r in reposts if cluster(r[0])),
        "domains": ";".join(sorted(domains)),
        "labels": ";".join(f"{l['val']}@{l['src']}" for l in labels),
        "sample_text": (texts[0] if texts else "")[:140],
    }, {
        "handle": h, "did": did, "profile": prof, "pds": pds,
        "didDocument": doc, "labels": labels,
        "originals": sorted(orig), "reposts": reposts, "texts": texts,
        "domains": sorted(domains),
    }


rows, detail = [], {}
with ThreadPoolExecutor(max_workers=10) as ex:
    for res in ex.map(collect, handles):
        if res:
            rows.append(res[0])
            detail[res[0]["did"]] = res[1]

rows.sort(key=lambda r: r["handle"])
json.dump(detail, open(f"{OUT}/naomivip_cluster.json", "w"), indent=1)
cols = list(rows[0].keys())
with open(f"{OUT}/naomivip_cluster.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print(f"collected {len(rows)} accounts\n")
print("PDS hosts:")
for p, c in Counter(r["pds"] for r in rows).most_common():
    print(f"  {c:4d}  {p}")
print("\ncreation dates:")
for d, c in sorted(Counter((r["createdAt"] or "")[:10] for r in rows).items()):
    print(f"  {d}  {c}")
print("\nlabels present:")
for l, c in Counter(r["labels"] for r in rows if r["labels"]).most_common():
    print(f"  {c:4d}  {l[:100]}")
print("\nlinked domains:")
for d, c in Counter(x for r in rows for x in r["domains"].split(";") if x).most_common():
    print(f"  {c:4d}  {d}")
dhs = Counter(r["avatar_dhash"] for r in rows if r["avatar_dhash"])
print(f"\navatar perceptual hashes: {len(dhs)} distinct across {len(rows)} accounts "
      f"(PIL {'on' if HAVE_PIL else 'off'})")
for h, c in dhs.most_common(12):
    print(f"  {c:3d}  {h}")
print(f"\ndistinct bios: {len({r['description'] for r in rows})} of {len(rows)}")
print("reposts of cluster accounts:", sum(r["reposts_of_cluster"] for r in rows))
#!/usr/bin/env python3
"""Avatar near-duplicate analysis for the naomivip.xyz cluster.

Every avatar is a distinct CDN blob (distinct CID), so byte hashing proves
nothing. This downloads each avatar and computes two perceptual hashes
(dhash64, phash32) plus a colour histogram, then reports clusters whose
Hamming distance is small enough to indicate the same source face.
"""
import csv, io, json, os, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFilter

S = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (evidence-collector)"}


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.read()
    except Exception:
        return None


def dhash(im, size=8):
    g = im.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for y in range(size):
        for x in range(size):
            bits = (bits << 1) | (1 if px[y * (size + 1) + x] > px[y * (size + 1) + x + 1] else 0)
    return bits


def phash(im, size=32, hsize=8):
    import math
    g = im.convert("L").resize((size, size), Image.LANCZOS)
    px = [v for v in g.getdata()]
    out = []
    for u in range(hsize):
        for v in range(hsize):
            tot = 0.0
            for x in range(size):
                for y in range(size):
                    dx, dy = x - u * size / hsize, y - v * size / hsize
                    tot += px[y * size + x] * math.exp(-(dx * dx + dy * dy) / (2 * (size / hsize) ** 2))
            out.append(tot)
    m = sorted(out)[len(out) // 2]
    bits = 0
    for v in out:
        bits = (bits << 1) | (1 if v > m else 0)
    return bits


def colour_sig(im):
    im2 = im.convert("RGB").resize((32, 32), Image.LANCZOS)
    q = im2.quantize(colors=8, method=Image.MEDIANCUT)
    hist = sorted(q.getcolors(1024) or [], reverse=True)
    tot = sum(c for c, _ in hist) or 1
    return tuple(round(c / tot, 3) for c, _ in hist[:8])


def ham(a, b):
    return bin(a ^ b).count("1")


rows = list(csv.DictReader(open(f"{S}/naomivip_cluster.csv")))
deep = json.load(open(f"{S}/naomivip_cluster.json"))
avatars = {r["handle"]: r["profile"].get("avatar") for r in deep.values()}

def work(row):
    h = row["handle"]
    raw = fetch(row["avatar"] if False else (avatars.get(h) or ""))
    if not raw:
        return h, None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        return h, {"dh": dhash(im), "ph": phash(im), "col": colour_sig(im),
                   "w": im.width, "h": im.height}
    except Exception as e:
        return h, None

print(f"hashing {len(rows)} avatars", flush=True)
with ThreadPoolExecutor(max_workers=12) as ex:
    fp = {h: v for h, v in ex.map(work, rows) if v}
print(f"hashed {len(fp)} avatars\n")

by_handle = {r["handle"]: r for r in rows}
hs = sorted(fp)

# pair analysis
pairs = []
for i in range(len(hs)):
    for j in range(i + 1, len(hs)):
        a, b = fp[hs[i]], fp[hs[j]]
        d_ph = ham(a["ph"], b["ph"])
        d_dh = ham(a["dh"], b["dh"])
        pairs.append((d_ph, d_dh, hs[i], hs[j]))
pairs.sort()

print("closest 25 avatar pairs (phash32 Hamming, dhash64 Hamming):")
for d_ph, d_dh, x, y in pairs[:25]:
    print(f"  ph={d_ph:2d} dh={d_dh:2d}  {x} <-> {y}")

# clusters at thresholds
for thr in (8, 12, 16):
    parent = {h: h for h in hs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for d_ph, d_dh, x, y in pairs:
        if d_ph <= thr:
            union(x, y)
    groups = defaultdict(list)
    for h in hs:
        groups[find(h)].append(h)
    multi = [g for g in groups.values() if len(g) > 1]
    print(f"\nphash<= {thr:2d}: {len(multi)} clusters covering {sum(len(g) for g in multi)} accounts")
    for g in sorted(multi, key=len, reverse=True)[:8]:
        print(f"   {len(g):2d}  {' '.join(sorted(g))}")

json.dump({h: {"dh": v["dh"], "ph": v["ph"], "col": v["col"],
               "w": v["w"], "h": v["h"]} for h, v in fp.items()},
          open(f"{S}/avatar_fingerprints.json", "w"), indent=1)
print("\nwrote avatar_fingerprints.json")
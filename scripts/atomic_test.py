#!/usr/bin/env python3
"""Verify: (1) crash during staging leaves the old snapshot fully intact and no
stray .tmp; (2) BCA_ALLOW_SMALLER=1 still cannot bypass the checkpoint guards."""
import os
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

REAL = '/home/ubuntu/babesky-creator-analytics'
NAMES = ('posts_30d.tsv', 'accounts_30d.tsv', 'facets_30d.tsv')

STUB = '''
import json, os, sys, urllib.request, urllib.parse
DIDS = [f"did:plc:syn{i:05d}" for i in range({cohort})]
DONE = set(DIDS[0:{done}])
PPD = {ppd}
CRASH_ON = {crash}
class R:
    def __init__(s, b): s.b = b
    def read(s): return json.dumps(s.b).encode()
    def __enter__(s): return s
    def __exit__(s, *a): return False
def mkpost(did, i, tagged):
    rec = {"createdAt": "2026-10-12T00:00:00Z", "text": "x"}
    if tagged:
        rec["facets"] = [{"$type": "app.bsky.richtext.facet#tag",
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "tag"}]}]
    return {"post": {"uri": f"at://did:plc:f/{did.replace(':','_')}{i}",
            "author": {"did": did}, "record": rec, "embed": None,
            "replyCount": 0, "repostCount": 0, "likeCount": 0,
            "indexedAt": "2026-10-12T00:00:00Z"}, "reply": None}
def open_(req, timeout=None):
    u = req.full_url
    if "club-server" in u:
        return R({"profiles": [{"did": d} for d in DIDS], "hasMore": False})
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(u).query))
    if q["actor"] in DONE:
        return R({"feed": []})
    return R({"feed": [mkpost(q["actor"], i, i % 3 == 0) for i in range(PPD)],
              "cursor": None})
urllib.request.urlopen = open_
import csv as _csv
src = open({repo} + "/analysis/19_pull_master.py").read()
# Run the module, then trip the writer it actually resolves (m.csv.writer).
ns = {{"__name__": "__not_main__", "__file__": {repo} + "/analysis/19_pull_master.py"}}
exec(compile(src, "19_pull_master.py", "exec"), ns)
_orig = ns["csv"].writer
def patched(*a, **k):
    # blow up when writing accounts_30d.tsv (2nd of 3 files)
    if CRASH_ON and a and isinstance(a[0], str) and CRASH_ON in a[0]:
        raise RuntimeError("simulated crash mid-write")
    return _orig(*a, **k)
ns["csv"].writer = patched
ns["write_snapshot"]([("posts_30d.tsv", ["a"], [["1"]]),
                      ("accounts_30d.tsv", ["a"], [["2"]]),
                      ("facets_30d.tsv", ["a"], [["3"]])])
sys.exit(0)
'''


def build_stub(root, cohort, done, ppd, crash_on=None):
    stub = os.path.join(root, 'stub.py')
    open(stub, 'w').write((STUB.replace('{cohort}', str(cohort))
                               .replace('{done}', str(done))
                               .replace('{ppd}', str(ppd))
                               .replace('{crash}', repr(crash_on))
                               .replace('{repo}', repr(REAL))))
    return stub


def seed(root):
    data, loc = os.path.join(root, 'data'), os.path.join(root, 'local')
    os.makedirs(data, exist_ok=True); os.makedirs(loc, exist_ok=True)
    for n in NAMES:
        shutil.copy(os.path.join(REAL, 'data', n), os.path.join(data, n))
    open(os.path.join(loc, 'salt'), 'w').write('unit-test-salt')
    return data, loc


def digests(d):
    return {n: hashlib.sha256(open(os.path.join(d, n), 'rb').read()).hexdigest()
            for n in NAMES}


# ---- 1. crash mid-staging
root = tempfile.mkdtemp(prefix='atomic-')
data, loc = seed(root)
stub = build_stub(root, 2701, 0, 12, crash_on='accounts_30d.tsv')
before = digests(data)
r = subprocess.run([sys.executable, stub], cwd=REAL, capture_output=True, text=True,
                   timeout=900,
                   env=dict(os.environ, BCA_DATA_DIR=data, BCA_LOCAL_DIR=loc,
                            BCA_WORKERS='16'))
after = digests(data)
tmp_left = sorted(f for f in os.listdir(data) if f.endswith('.tmp'))
print(f'CRASH MID-WRITE: rc={r.returncode} data_unchanged={before == after} '
      f'stray_tmp={tmp_left}')
print(f'  err tail: {(r.stderr or "").strip().splitlines()[-1][:90] if r.stderr.strip() else ""}')
ok_atomic = before == after and not tmp_left
shutil.rmtree(root, ignore_errors=True)

# ---- 2. override must NOT bypass the checkpoint guards
root2 = tempfile.mkdtemp(prefix='ovr-')
data2, loc2 = seed(root2)
dids = [f'did:plc:syn{i:05d}' for i in range(2701)]
json.dump({'done': dids, 'errors': 0},
          open(os.path.join(loc2, 'master_progress.json'), 'w'))
stub2 = build_stub(root2, 2701, 2701, 12)
before2 = digests(data2)
r2 = subprocess.run([sys.executable, stub2], cwd=REAL, capture_output=True, text=True,
                    timeout=900,
                    env=dict(os.environ, BCA_DATA_DIR=data2, BCA_LOCAL_DIR=loc2,
                             BCA_WORKERS='16', BCA_ALLOW_SMALLER='1'))
after2 = digests(data2)
msg = [l for l in (r2.stdout + r2.stderr).splitlines() if 'checkpoint' in l.lower()]
print(f'OVERRIDE + covering checkpoint: rc={r2.returncode} '
      f'data_unchanged={before2 == after2}')
print(f'  {msg[0][:96] if msg else "(no checkpoint message)"}')
ok_override = r2.returncode != 0 and before2 == after2
shutil.rmtree(root2, ignore_errors=True)

print('\nATOMIC OK' if ok_atomic else '\nATOMIC FAILED')
print('OVERRIDE SAFE' if ok_override else '\nOVERRIDE BYPASSES CHECKPOINT GUARD')
sys.exit(0 if (ok_atomic and ok_override) else 1)
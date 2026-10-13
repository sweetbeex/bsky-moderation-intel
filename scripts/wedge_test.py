#!/usr/bin/env python3
"""Verify the wedge is fixed: first run refuses and leaves checkpoint walkable;
second run with BCA_ALLOW_SMALLER=1 must write, not hit 'covers cohort'."""
import os
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

REAL = '/home/ubuntu/babesky-creator-analytics'
NAMES = ('posts_30d.tsv', 'accounts_30d.tsv', 'facets_30d.tsv')


def digests(d):
    return {n: hashlib.sha256(open(os.path.join(d, n), 'rb').read()).hexdigest()
            if os.path.exists(os.path.join(d, n)) else None for n in NAMES}


def run_case(root, cohort, done, ppd, override=False):
    data, loc = os.path.join(root, 'data'), os.path.join(root, 'local')
    os.makedirs(data, exist_ok=True); os.makedirs(loc, exist_ok=True)
    for n in NAMES:
        shutil.copy(os.path.join(REAL, 'data', n), os.path.join(data, n))
    open(os.path.join(loc, 'salt'), 'w').write('unit-test-salt')
    dids = [f'did:plc:syn{i:05d}' for i in range(cohort)]
    if done:
        json.dump({'done': dids[:done], 'errors': 0},
                  open(os.path.join(loc, 'master_progress.json'), 'w'))
    stub = os.path.join(root, 'stub.py')
    tmpl = (STUB.replace('{cohort}', str(cohort)).replace('{done}', str(done))
                .replace('{ppd}', str(ppd)).replace('{errpct}', '0')
                .replace('{nfail}', '0').replace('{repo}', repr(REAL)))
    open(stub, 'w').write(tmpl)
    before = digests(data)
    env = dict(os.environ, BCA_DATA_DIR=data, BCA_LOCAL_DIR=loc, BCA_WORKERS='16')
    if override:
        env['BCA_ALLOW_SMALLER'] = '1'
    r = subprocess.run([sys.executable, stub], cwd=REAL, capture_output=True,
                       text=True, timeout=900, env=env)
    after = digests(data)
    wrote = before != after
    return r.returncode, before, after, wrote, r.stderr[-500:]


STUB = '''
import json, sys, urllib.request, urllib.parse
DIDS = [f"did:plc:syn{i:05d}" for i in range({cohort})]
DONE = set(DIDS[0:{done}])
PPD = {ppd}
ERRPCT = {errpct}
FAILING = set(DIDS[0:{nfail}])
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
    did = q["actor"]
    if did in DONE:
        return R({"feed": []})
    if did in FAILING:
        return R({"error": "simulated feed failure"})
    return R({"feed": [mkpost(did, i, i % 3 == 0) for i in range(PPD)], "cursor": None})
urllib.request.urlopen = open_
src = open({repo} + "/analysis/19_pull_master.py").read()
sys.argv = ["19_pull_master.py"]
exec(compile(src, "19_pull_master.py", "exec"),
     {"__name__": "__main__", "__file__": {repo} + "/analysis/19_pull_master.py"})
'''

# Scenario: full cohort, half the posts (walk produces ~49% of committed)
# Run 1: no override -> must refuse, checkpoint must leave DIDs walkable
# Run 2: with override -> must write, NOT hit "covers cohort"

root = tempfile.mkdtemp(prefix='wedge-')
print('RUN 1: 49% walk, no override -> refuse, data intact, checkpoint walkable')
rc1, before1, after1, wrote1, err1 = run_case(root, 2701, 0, 5, override=False)
print(f'  rc={rc1} wrote={wrote1} data_unchanged={before1==after1}')
print(f'  last_err: {err1.strip()[-100:]}')

# Check checkpoint: DIDs should NOT be marked done (they're in 'pending')
prog = json.load(open(os.path.join(root, 'local', 'master_progress.json')))
print(f'  checkpoint done={len(prog.get("done", []))} pending={len(prog.get("pending", []))}')

print('\\nRUN 2: same dir, BCA_ALLOW_SMALLER=1 -> write, not refuse')
rc2, before2, after2, wrote2, err2 = run_case(root, 2701, 0, 5, override=True)
print(f'  rc={rc2} wrote={wrote2} data_changed={before2!=after2}')
print(f'  last_err: {err2.strip()[-100:]}')

if rc1 != 0 and before1 == after1 and rc2 == 0 and before2 != after2:
    print('\\nWEDGE FIXED')
else:
    print('\\nWEDGE STILL BROKEN')
    sys.exit(1)

shutil.rmtree(root, ignore_errors=True)
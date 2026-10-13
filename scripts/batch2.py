#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mut import run

M = 'analysis/19_pull_master.py'
A = 'data/accounts_30d.tsv'
P = 'data/posts_30d.tsv'
res = []

# ---- SUSPECTED HOLE: drop the truncation from anon_did entirely (full 64-hex).
# CALL_SITES regex does not require a hexdigest; the width regex is non-greedy
# and re.S, so it may scan past anon_did into anon_post's [:16].
res.append(run('hole_drop_adid_trunc', M,
               "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:16]",
               "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()"))
res.append(run('hole_drop_apost_trunc', M,
               "return hashlib.sha256((SALT + 'post:' + str(uri)).encode()).hexdigest()[:16]",
               "return hashlib.sha256((SALT + 'post:' + str(uri)).encode()).hexdigest()"))
res.append(run('hole_drop_map_trunc', M,
               "MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()[:16]",
               "MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()"))

# ---- media-kind vocabulary, rollup kept self-consistent
res.append(run('vocab_subtype_flatten', M,
               "'app.bsky.embed.images': 'recordWithMedia_images',",
               "'app.bsky.embed.images': 'images',"))
res.append(run('vocab_subtype_video', M,
               "'app.bsky.embed.video': 'recordWithMedia_video',",
               "'app.bsky.embed.video': 'video',"))
res.append(run('vocab_rollup_counts_inst', M,
               "        if r['media_kind'] == 'images':\n            a['images'] += 1",
               "        if r['media_kind'] == 'images':\n            a['images'] += r['image_count']"))
res.append(run('vocab_rollup_drop_video', M,
               "        if r['media_kind'] in ('video', 'recordWithMedia_video'):\n            a['videos'] += 1",
               "        if r['media_kind'] == 'video':\n            a['videos'] += 1"))

# ---- data-level violations of the new rollup pins
res.append(run('data_bump_images', A, '\t', '\t'))
res[-1] = ('data_bump_images', 'SKIPPED', 'placeholder replaced below')
res = res[:-1]

import csv, shutil, subprocess, sys as _s
def data_mut(name, fname, transform):
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mutants', name)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    REAL='/home/ubuntu/babesky-creator-analytics'
    for sub in ('analysis','tests','data','docs','sql','reports'):
        s=os.path.join(REAL,sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(d,sub), ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy(os.path.join(REAL,'README.md'), d)
    p=os.path.join(d,fname)
    rows=list(csv.DictReader(open(p),delimiter='\t'))
    hdr=list(rows[0].keys())
    rows=transform(rows)
    with open(p,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=hdr,delimiter='\t',lineterminator='\n'); w.writeheader(); w.writerows(rows)
    r=subprocess.run([_s.executable,'tests/test_master_pull_schema.py'],cwd=d,capture_output=True,text=True,timeout=900)
    return name, ('RED' if r.returncode else 'GREEN'), ' | '.join(l.strip() for l in (r.stdout+r.stderr).strip().splitlines()[-6:])

def bump_one(rws):
    for r in rws:
        if int(r['images_in_window'])>0:
            r['images_in_window']=str(int(r['images_in_window'])+1); return rws
def bump_vid(rws):
    for r in rws:
        if int(r['videos_in_window'])>0:
            r['videos_in_window']=str(int(r['videos_in_window'])+1); return rws
def relabel_rwm(rws):
    n=0
    for r in rws:
        if r['media_kind']=='recordWithMedia_images':
            r['media_kind']='images'; n+=1
            if n>=5: break
    return rws

res.append(data_mut('data_bump_images_1', A, bump_one))
res.append(data_mut('data_bump_videos_1', A, bump_vid))
res.append(data_mut('data_relabel_rwm_5', P, relabel_rwm))

for n, st, tail in res:
    print(f'{st:10s} {n}\n           {tail[:420]}')
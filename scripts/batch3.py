#!/usr/bin/env python3
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mut import run

M = 'analysis/19_pull_master.py'
res = []
# confirm the anon_did width hole, several spellings
res.append(run('c_adid_64explicit', M,
    "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:16]",
    "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:64]"))
# same hole via a different refactor that keeps a [:16] later in the file
res.append(run('c_adid_helper', M, [
    ("def anon_did(d):\n    return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:16]",
     "def _anon_did_hash(d):\n    return hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()\n\n\ndef anon_did(d):\n    return MAP.get(d) or _anon_did_hash(d)[:16]")]))
# does anything behavioural catch a 64-hex anon_did? test an UNMAPPED did end-to-end
res.append(run('c_adid_unmapped_behaviour', M,
    "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:16]",
    "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()"))
# rollup code-side mutations (data pins are data-vs-data, cannot see code)
res.append(run('c_rollup_img_instances', M,
    "        if r['media_kind'] == 'images':\n            a['images'] += 1",
    "        if r['media_kind'] == 'images':\n            a['images'] += r['image_count']"))
res.append(run('c_rollup_include_rwm', M,
    "        if r['media_kind'] == 'images':\n            a['images'] += 1",
    "        if r['media_kind'] in ('images', 'recordWithMedia_images'):\n            a['images'] += 1"))
res.append(run('c_rollup_vid_off_by_one', M,
    "        if r['media_kind'] in ('video', 'recordWithMedia_video'):\n            a['videos'] += 1",
    "        if r['media_kind'] in ('video', 'recordWithMedia_video'):\n            a['videos'] += 2"))
# SUBTYPE video relabel - committed data has zero recordWithMedia_video rows
res.append(run('c_subtype_video_relabel', M,
    "'app.bsky.embed.video': 'recordWithMedia_video',",
    "'app.bsky.embed.video': 'video',"))

for n, st, tail in res:
    print(f'{st:8s} {n}\n         {tail[:340]}')

print()
print('=== regex mechanism on the mutated anon_did ===')
real = open('/home/ubuntu/babesky-creator-analytics/' + M, encoding='utf-8').read()
code = '\n'.join(ln.split('#', 1)[0] for ln in real.splitlines() if not ln.lstrip().startswith('#'))
mut = code.replace("return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()[:16]",
                   "return MAP.get(d) or hashlib.sha256((SALT + 'did:' + d).encode()).hexdigest()")
got = re.search(r"def anon_did\(d\):.*?hexdigest\(\)\[:(\d+)\]", mut, re.S)
print('anon_did width regex on truncation-dropped code ->',
      got.group(0)[:110].replace('\n', ' | '))
print('captured width =', got.group(1) if got else None, '(expected 16)')
print('total hexdigest[:NN] occurrences in file:', re.findall(r'hexdigest\(\)\[:(\d+)\]', code))
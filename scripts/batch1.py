#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mut import run

M = 'analysis/19_pull_master.py'
results = []

# ---- 1. THE TWO PREVIOUSLY-SURVIVING MUTATIONS
results.append(run('prev1_anon_did_prefix', M,
                   "(SALT + 'did:' + d)", "(SALT + 'post:' + d)"))
results.append(run('prev2_anon_did_width', M,
                   "(SALT + 'did:' + d).encode()).hexdigest()[:16]",
                   "(SALT + 'did:' + d).encode()).hexdigest()[:12]"))

# ---- 2. THE HARD ATTACKS
# swap the two did: sites so each carries the other's prefix
results.append(run('swap_did_sites', M, [
    ("MAP.get(d) or hashlib.sha256((SALT + 'did:' + d)",
     "MAP.get(d) or hashlib.sha256((SALT + 'post:' + d)"),
    ("MAP[did] = hashlib.sha256((SALT + 'did:' + did)",
     "MAP[did] = hashlib.sha256((SALT + 'post:' + did)")]))

# make both did: sites identical text (dedupe: MAP[did] = anon_did(did))
results.append(run('dedupe_did_sites', M,
                   "MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()[:16]",
                   "MAP[did] = anon_did(did)"))

# move the MAP[did] site: hash under a different var name / refactor to a helper
results.append(run('move_map_site_helper', M, [
    ("MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()[:16]",
     "MAP[did] = _h(did)")]))

# docstring-only change: 'did:' -> 'DID:' in the contract lines
results.append(run('docstring_only', M,
                   'anon_did = sha256(salt + "did:" + did)[:16]',
                   'anon_did = sha256(salt + "DID:" + did)[:16]'))

# anon_post prefix + width drift
results.append(run('anon_post_prefix', M,
                   "(SALT + 'post:' + str(uri))", "(SALT + 'uri:' + str(uri))"))
results.append(run('anon_post_width', M,
                   "(SALT + 'post:' + str(uri)).encode()).hexdigest()[:16]",
                   "(SALT + 'post:' + str(uri)).encode()).hexdigest()[:14]"))
results.append(run('map_width', M,
                   "MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()[:16]",
                   "MAP[did] = hashlib.sha256((SALT + 'did:' + did).encode()).hexdigest()[:20]"))
# hash12 width 12 -> 16 (should trip the 'exactly one 12' guard)
results.append(run('hash12_width', M,
                   "(SALT + str(value).strip().lower()).encode()).hexdigest()[:12]",
                   "(SALT + str(value).strip().lower()).encode()).hexdigest()[:16]"))

# ---- 3. club snapshot prefix
results.append(run('club_prefixed', 'analysis/15_pull_club_snapshot.py',
                   "hashlib.sha256(salt + did.encode())",
                   "hashlib.sha256(salt + 'did:'.encode() + did.encode())"))
results.append(run('club_renamed_var', 'analysis/15_pull_club_snapshot.py',
                   [("did = p['did']", "ddid = p['did']"),
                    ("if did not in mp:", "if ddid not in mp:"),
                    ("mp[did] = hashlib.sha256(salt + did.encode())",
                     "mp[ddid] = hashlib.sha256(salt + ddid.encode())")]))

for n, st, tail in results:
    print(f'{st:10s} {n}\n           {tail[:400]}')
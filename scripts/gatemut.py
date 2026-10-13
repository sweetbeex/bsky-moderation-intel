#!/usr/bin/env python3
"""Mutation-test the write-gate guards: each mutation must make the test red."""
import os
import shutil
import subprocess
import sys
import tempfile

REAL = '/home/ubuntu/babesky-creator-analytics'
M = 'analysis/19_pull_master.py'

MUTATIONS = [
    ('gate_floor_90_to_0', "if floor and produced < floor * 0.9:",
     "if False:"),
    ('gate_posts_row_dropped', "('posts', len(rows), base.get('posts_30d.tsv', 0)),",
     "('posts', 10 ** 9, base.get('posts_30d.tsv', 0)),"),
    ('gate_facets_row_dropped', "('facet rows', len(frows), base.get('facets_30d.tsv', 0)),",
     "('facet rows', 10 ** 9, base.get('facets_30d.tsv', 0)),"),
    ('gate_accounts_row_dropped', "('accounts', len(acc), base.get('accounts_30d.tsv', 0)),",
     "('accounts', 10 ** 9, base.get('accounts_30d.tsv', 0)),"),
    ('gate_missing_baseline', "    if not base:\n        return                                     # first ever snapshot",
     "    base = {}"),
    ('gate_no_raise', "            raise SystemExit(f'walk produced {produced} {label},",
     "            print(f'walk produced {produced} {label},"),
    ('errgate_disabled', "    if rate > 0.5:", "    if False:"),
    ('errgate_never_calls', "    check_error_rate(errs, walked)", "    pass"),
    ('checkpoint_stale_guard_removed', "    if stale:", "    if False:"),
    ('checkpoint_covering_guard_removed', "    if not order:", "    if False:"),
]


def run(name, old, new):
    d = tempfile.mkdtemp(prefix='gatemut-')
    for sub in ('analysis', 'tests', 'data'):
        shutil.copytree(os.path.join(REAL, sub), os.path.join(d, sub),
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    p = os.path.join(d, M)
    src = open(p, encoding='utf-8').read()
    if old not in src:
        shutil.rmtree(d, ignore_errors=True)
        return 'SETUP', f'pattern not found: {old[:52]!r}'
    open(p, 'w', encoding='utf-8').write(src.replace(old, new, 1))
    r = subprocess.run([sys.executable, 'tests/test_master_pull_schema.py'], cwd=d,
                       capture_output=True, text=True, timeout=300)
    shutil.rmtree(d, ignore_errors=True)
    out = (r.stdout + r.stderr)
    first = [l.strip(' -\n') for l in out.splitlines() if l.strip().startswith('-')]
    st = 'RED' if r.returncode != 0 else 'GREEN'
    return st, (first[0][:98] if first else (out.strip().splitlines() or [''])[-1][:98])


fails = 0
for name, old, new in MUTATIONS:
    st, detail = run(name, old, new)
    if st != 'RED':
        fails += 1
    print(f'{st:6s} {name}\n       {detail}')
print(f'\n{len(MUTATIONS) - fails}/{len(MUTATIONS)} killed')
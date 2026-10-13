#!/usr/bin/env python3
"""Mutation harness: copy analysis/tests/data to a temp dir, apply a textual
mutation, run the schema test, report GREEN (survived) or RED (caught)."""
import os, shutil, subprocess, sys, tempfile, json

REAL = '/home/ubuntu/.hermes/profiles/babesky-admin/cache/scratch/pin-057cc10'
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mutants')


def run(name, target, old, new=None, test='tests/test_master_pull_schema.py'):
    """target = path relative to repo. old/new = (old,new) tuple or list of them.

    Accepts run(name, target, [(old,new), ...]) with new=None; earlier revision
    of this helper required `new` positionally and crashed on list form.
    """
    d = os.path.join(BASE, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for sub in ('analysis', 'tests', 'data', 'docs', 'sql', 'reports'):
        s = os.path.join(REAL, sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(d, sub),
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy(os.path.join(REAL, 'README.md'), d)
    p = os.path.join(d, target)
    src = open(p, encoding='utf-8').read()
    pairs = old if isinstance(old, list) else [(old, new)]
    for o, n in pairs:
        if o not in src:
            return name, 'SETUP_ERROR', f'pattern not found: {o[:80]!r}'
        src = src.replace(o, n)
    open(p, 'w', encoding='utf-8').write(src)
    r = subprocess.run([sys.executable, test], cwd=d, capture_output=True, text=True,
                       timeout=900)
    out = (r.stdout + r.stderr).strip().splitlines()
    tail = ' | '.join(l.strip() for l in out[-6:])
    return name, ('RED' if r.returncode != 0 else 'GREEN'), tail


if __name__ == '__main__':
    print('library only')
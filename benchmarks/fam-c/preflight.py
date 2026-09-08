#!/usr/bin/env python3
"""Fam-C freeze preflight: asserts the frozen package is instantiable
exactly per the visibility seals. Exit 0 = all green, 1 = findings.
Checks per task dir: every VISIBLE-declared fixture exists; every
fixture file present is declared; prompt/checker/truth hashes match
FREEZE-HASHES.sha256; no forbidden basenames inside task dirs."""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAMS = os.path.join(HERE, "families")
FORBIDDEN = {"truth.json", "check.py", "K.md", "DESIGN-T4.md", "T4NOTE.md"}
fails = []


def fail(msg):
    fails.append(msg)
    print("FAIL:", msg)


manifest = {}
man_path = os.path.join(HERE, "FREEZE-HASHES.sha256")
if os.path.exists(man_path):
    for line in open(man_path):
        h, p = line.strip().split("  ", 1)
        manifest[p] = h

for fam in sorted(os.listdir(FAMS)):
    fdir = os.path.join(FAMS, fam)
    if not os.path.isdir(fdir):
        continue
    for task in sorted(os.listdir(fdir)):
        tdir = os.path.join(fdir, task)
        if not os.path.isdir(tdir) or task not in (
                "T0", "T1", "T2", "T3", "T4"):
            continue
        rel = os.path.relpath(tdir, HERE)
        vis = os.path.join(tdir, "VISIBLE.md")
        if not os.path.exists(vis):
            fail(f"{rel}: missing VISIBLE.md")
            continue
        declared = None
        for line in open(vis):
            if "task fixtures:" in line:
                declared = line.split("task fixtures:", 1)[1].split()
        if declared is None:
            fail(f"{rel}: VISIBLE.md has no fixture line")
            continue
        actual = sorted(f for f in os.listdir(tdir)
                        if f not in ("prompt.md", "VISIBLE.md"))
        for d in declared:
            dp = os.path.join(tdir, d)
            if d not in actual:
                fail(f"{rel}: declared fixture missing: {d}")
            elif os.path.isdir(dp) and not os.listdir(dp):
                fail(f"{rel}: declared fixture dir empty: {d}")
        for a in actual:
            if a not in declared:
                fail(f"{rel}: undeclared fixture present: {a}")
        forbidden = [a for a in actual if a in FORBIDDEN]
        if forbidden:
            fail(f"{rel}: forbidden files in task dir: {forbidden}")
        for fn in ("prompt.md",):
            p = os.path.join(rel, fn)
            fp = os.path.join(HERE, p)
            if os.path.exists(fp):
                h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
                if p in manifest and manifest[p] != h:
                    fail(f"{rel}: {fn} hash mismatch vs freeze manifest")
for fam in sorted(os.listdir(FAMS)):
    for base in ("truth.json", "check.py"):
        p = os.path.join("families", fam, base)
        fp = os.path.join(HERE, p)
        h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if p in manifest and manifest[p] != h:
            fail(f"{fam}/{base} hash mismatch vs freeze manifest")
print(f"preflight: {len(fails)} findings")
sys.exit(1 if fails else 0)

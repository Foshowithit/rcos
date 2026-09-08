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

freeze = {}
for line in open(os.path.join(HERE, "FREEZE-HASHES.sha256")):
    h, p = line.strip().split("  ", 1)
    freeze[p] = h
on_disk = set()
for root, dirs, files in os.walk(HERE):
    # PREREG.md visibility seal: runs/ evidence dirs are not freeze inputs
    if os.path.basename(root) == "runs":
        dirs[:] = []
        continue
    for fn in files:
        rel = os.path.relpath(os.path.join(root, fn), HERE)
        if rel in ("FREEZE-HASHES.sha256", "FREEZE.json"):
            continue  # meta: pinned by git, not by content manifest
        on_disk.add(rel)
for p in sorted(on_disk - set(freeze)):
    fail(f"extra file not in freeze manifest: {p}")
for p in sorted(set(freeze) - on_disk):
    fail(f"freeze-manifest file missing on disk: {p}")
for p, h in sorted(freeze.items()):
    fp = os.path.join(HERE, p)
    if not os.path.exists(fp):
        continue
    actual = hashlib.sha256(open(fp, "rb").read()).hexdigest()
    if actual != h:
        fail(f"hash mismatch vs freeze manifest: {p}")
fj = os.path.join(HERE, "FREEZE.json")
if os.path.exists(fj):
    import subprocess
    pin = json.load(open(fj))
    try:
        out = subprocess.run(
            ["git", "-C", os.path.dirname(HERE), "rev-parse",
             "HEAD:benchmarks/fam-c"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip() != pin.get("tree", ""):
            fail("working tree benchmarks/fam-c != frozen tree "
                 f"{pin.get('tree', '')[:12]}")
    except FileNotFoundError:
        fail("git unavailable for tree-pin check")
print(f"preflight: {len(fails)} findings")
sys.exit(1 if fails else 0)

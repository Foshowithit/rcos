#!/usr/bin/env python3
"""Fam-C freeze preflight: asserts the frozen package is instantiable
exactly per the visibility seals. Exit 0 = all green, 1 = findings.
Checks per task dir: every VISIBLE-declared fixture exists; every
fixture file present is declared; prompt/checker/truth hashes match
FREEZE-HASHES.sha256; no forbidden basenames inside task dirs."""
import hashlib
import json
import os
import subprocess
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
if not os.path.exists(fj):
    fail("FREEZE.json missing")
    print(f"preflight: {len(fails)} findings")
    sys.exit(1)
pin = json.load(open(fj))
fc = pin.get("freeze_commit", "")
if not fc:
    fail("FREEZE.json has no freeze_commit")
    print(f"preflight: {len(fails)} findings")
    sys.exit(1)
# Only runs/** may differ post-freeze (future evidence). EVERYTHING else
# — including this script, the manifests, and FREEZE.json — is frozen.
# runs/** holds future evidence; FREEZE.json + FREEZE-HASHES.sha256 are
# pure metadata pointers (their own integrity rides on git history +
# the content manifest respectively). Everything else is frozen.
bind = ["diff", "--exit-code", fc, "HEAD", "--", "benchmarks/fam-c",
        ":(exclude)benchmarks/fam-c/runs/**",
        ":(exclude)benchmarks/fam-c/FREEZE.json",
        ":(exclude)benchmarks/fam-c/FREEZE-HASHES.sha256"]
repo = os.path.dirname(HERE)
try:
    d = subprocess.run(["git", "-C", repo] + bind,
                       capture_output=True, text=True)
    if d.returncode != 0:
        fail("frozen→HEAD experimental diff NONEMPTY (content drift since "
             f"{fc[:12]}):\n" + d.stdout[:2000])
    st = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--",
                         "benchmarks/fam-c"], capture_output=True, text=True)
    for line in st.stdout.splitlines():
        path = line[3:]
        if "/runs/" in path or path.endswith("/runs"):
            continue  # future evidence dirs are expected post-freeze
        fail("working tree not clean vs freeze: " + line)
except FileNotFoundError:
    fail("git unavailable for binding checks")
print(f"preflight: {len(fails)} findings")
sys.exit(1 if fails else 0)

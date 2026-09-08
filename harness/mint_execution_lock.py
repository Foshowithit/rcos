#!/usr/bin/env python3
"""Re-mint EXECUTION-LOCK.json after an intentional harness change.

The lock is the execution authority (audit round-2 item 4/7). This tool
does the MECHANICAL part only: refresh listed harness bytes, add any newly
executed module from the runner's import closure, recompute the manifest
sha, and append an explicit amendment record. It never touches
PROTOCOL-LOCK.json — a governed protocol doc needs a human-written reason,
so that amendment stays manual.

Usage:
  python3 harness/mint_execution_lock.py --slice a9-item-7 \
      --reason "what changed and why" [--status open-round2] [--check]

--check reports whether the lock is stale (exit 1) without writing.
Stdlib only. The lock file itself is authoritative via git history.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOCK = os.path.join(ROOT, "benchmarks", "fam-c", "EXECUTION-LOCK.json")
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "fam-c"))
from preflight import _harness_closure  # noqa: E402  (same closure rule)


def _sha(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _manifest_sha(files):
    lines = sorted(f"{k}:{v}" for k, v in files.items())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice")
    ap.add_argument("--reason")
    ap.add_argument("--status", default="open-round2")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check and not (a.slice and a.reason):
        ap.error("--slice and --reason are required when minting")
    lock = json.load(open(LOCK))
    files = lock["harness_files"]
    entry = next((r for r in files
                  if r.startswith("benchmarks/fam-c/harness-run/")), None)
    changed = {}
    if entry:
        for rel in sorted(_harness_closure(ROOT, entry)):
            if rel not in files:
                files[rel] = _sha(rel)
                changed[rel] = {"from_sha": None, "to_sha": files[rel]}
    # Package-root closure (V3 item 7): every harness/*.py is inside the
    # execution authority, so a governance module the runner never imports
    # (harness/promotion.py) cannot ride outside it.
    hdir = os.path.join(ROOT, "harness")
    if os.path.isdir(hdir):
        for name in sorted(os.listdir(hdir)):
            if not name.endswith(".py"):
                continue
            rel = f"harness/{name}"
            if rel not in files:
                files[rel] = _sha(rel)
                changed[rel] = {"from_sha": None, "to_sha": files[rel]}
    for rel in list(files):
        want = _sha(rel)
        if want != files[rel]:
            changed[rel] = {"from_sha": files[rel], "to_sha": want}
            files[rel] = want
    new_manifest = _manifest_sha(files)
    if a.check:
        stale = bool(changed) or new_manifest != lock["harness_manifest_sha256"]
        print("EXECUTION-LOCK: " + ("STALE" if stale else "current"))
        for rel, c in sorted(changed.items()):
            print(f"  changed: {rel}")
        return 1 if stale else 0
    if not changed:
        print("EXECUTION-LOCK: no harness byte changed; nothing to mint")
        return 0
    lock["amendments"].append({
        "from_manifest": lock["harness_manifest_sha256"],
        "to_manifest": new_manifest, "files": changed,
        "reason": a.reason, "slice": a.slice, "status_after": a.status})
    lock["harness_manifest_sha256"] = new_manifest
    with open(LOCK, "w") as f:
        json.dump(lock, f, indent=1)
        f.write("\n")
    print(f"EXECUTION-LOCK re-minted ({len(changed)} file(s)): "
          f"{new_manifest}")
    for rel in sorted(changed):
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

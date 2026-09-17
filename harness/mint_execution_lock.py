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
  python3 harness/mint_execution_lock.py --finalize --slice a16 \
      --reason "audit sign-off recorded" [--check]

--check reports whether the lock is stale (exit 1) without writing.
--finalize (A16 FINAL-lock semantics, audit round-3 item 4) is the ONE
terminal transition: it refuses while any harness byte is unrecorded
(finalization pins exactly the bytes the re-minted lock already names),
appends the terminal amendment (status_after "FINAL", empty file map),
and records `status: "FINAL"`, `finalized_at` (UTC) and
`finalization_commit` (git HEAD at finalization). Once FINAL (or once a
terminal amendment exists), ANY further mint or finalize is REFUSED with
the named EXECUTION-LOCK-FINAL-REFUSED error — fail-closed, no
"add amendment and keep going" path exists in the epoch (the validator
side is preflight.validate_execution_final). --check still works on a
FINAL lock (staleness reporting only). Stdlib only. The lock file itself
is authoritative via git history.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOCK = os.path.join(ROOT, "benchmarks", "fam-c", "EXECUTION-LOCK.json")
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "fam-c"))
from preflight import _harness_closure  # noqa: E402  (same closure rule)
sys.path.insert(0, os.path.join(ROOT, "harness"))


def _frozen_constants():
    """Single-source frozen constants (harness/adaptation.py
    FROZEN_CONSTANTS): mirrored verbatim into the lock so the
    independent probe reads them from locked bytes. Returns
    (dict, error-string-or-None)."""
    try:
        import adaptation as _AD
    except (ImportError, SyntaxError) as e:
        return None, f"cannot import adaptation: {e}"
    consts = getattr(_AD, "FROZEN_CONSTANTS", None)
    if not isinstance(consts, dict):
        return None, "adaptation.FROZEN_CONSTANTS is not a mapping"
    try:
        return json.loads(json.dumps(consts, sort_keys=True)), None
    except (TypeError, ValueError) as e:
        return None, f"FROZEN_CONSTANTS not JSON-clean: {e}"


def _sha(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _manifest_sha(files):
    lines = sorted(f"{k}:{v}" for k, v in files.items())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _manifest_sha(files):
    lines = sorted(f"{k}:{v}" for k, v in files.items())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _terminal(lock):
    """True iff the lock has reached its terminal FINAL state: either the
    recorded status or any recorded amendment carries it (belt: a tampered
    status cannot reopen an epoch whose terminal amendment survives)."""
    if lock.get("status") == "FINAL":
        return True
    am = lock.get("amendments")
    return (isinstance(am, list)
            and any(isinstance(a, dict) and a.get("status_after") == "FINAL"
                    for a in am))


def _head_commit():
    p = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("EXEC-COMMIT-UNAVAILABLE: "
                           + (p.stderr or p.stdout).strip()[:200])
    return p.stdout.strip()


def _refuse_final():
    print("EXECUTION-LOCK-FINAL-REFUSED: the lock is FINAL (terminal "
          "epoch); minting amendments or re-finalizing is forbidden "
          "(audit round-3 item 4)")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice")
    ap.add_argument("--reason")
    ap.add_argument("--status", default="open-round2")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    if a.finalize and a.status != "open-round2":
        ap.error("--status is meaningless with --finalize (status becomes "
                 "FINAL)")
    if not a.check and not (a.slice and a.reason):
        ap.error("--slice and --reason are required when minting")
    lock = json.load(open(LOCK))
    if not a.check and _terminal(lock):
        return _refuse_final()
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
    consts, consts_err = _frozen_constants()
    consts_stale = (consts_err is not None
                    or lock.get("frozen_constants") != consts)
    if a.check:
        stale = bool(changed) or new_manifest != lock["harness_manifest_sha256"]
        print("EXECUTION-LOCK: " + ("STALE" if stale else "current"))
        if _terminal(lock):
            print("  FINAL (terminal epoch: further minting is refused)")
        for rel, c in sorted(changed.items()):
            print(f"  changed: {rel}")
        if consts_err is not None:
            print(f"  frozen_constants unreadable: {consts_err}")
            return 1
        if consts_stale:
            print("  frozen_constants mirror drift (re-mint to sync)")
            return 1
        return 1 if stale else 0
    if a.finalize:
        # A16: the ONE terminal transition. Finalization pins exactly the
        # bytes the current lock already names — a stale lock must be
        # re-minted FIRST (its own explicit amendment), never folded into
        # the finalization record.
        if consts_err is not None:
            print(f"EXECUTION-LOCK-FINAL-REFUSED frozen_constants "
                  f"unreadable: {consts_err}")
            return 1
        if changed or consts_stale or \
                new_manifest != lock["harness_manifest_sha256"]:
            _why = f"{len(changed)} unrecorded harness file(s)"
            if consts_stale:
                _why += " + frozen_constants drift"
            print("EXECUTION-LOCK-FINAL-REFUSED: the lock is stale ("
                  + _why + "); re-mint via an explicit amendment BEFORE "
                  "finalization (finalization pins the recorded bytes)")
            return 1
        try:
            head = _head_commit()
        except RuntimeError as e:
            print(f"EXECUTION-LOCK-FINAL-REFUSED {e}")
            return 1
        lock["amendments"].append({
            "from_manifest": lock["harness_manifest_sha256"],
            "to_manifest": lock["harness_manifest_sha256"],
            "files": {}, "reason": a.reason, "slice": a.slice,
            "status_after": "FINAL"})
        lock["status"] = "FINAL"
        lock["finalized_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime())
        lock["finalization_commit"] = head
        with open(LOCK, "w") as f:
            json.dump(lock, f, indent=1)
            f.write("\n")
        print(f"EXECUTION-LOCK FINALIZED at {head} "
              f"({lock['finalized_at']}); the epoch is terminal — "
              "further minting is refused")
        return 0
    if not changed and not consts_stale:
        print("EXECUTION-LOCK: no harness byte changed; nothing to mint")
        return 0
    if consts_err is not None:
        print(f"EXECUTION-LOCK-REFUSED {consts_err}")
        return 1
    lock["frozen_constants"] = consts
    print(f"EXECUTION-LOCK frozen_constants synced "
          f"({len(consts)} key(s))")
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

#!/usr/bin/env python3
"""Fam-C three-authority preflight (round-2 item 4, option b — no re-freeze).

Three INDEPENDENT validators, each green on its own authority. Exit 0 =
all green, 1 = findings (each finding names its authority). Importable:
`validate_all(fam_c_dir)` returns findings without exiting, so the runner
refuses to start on any lock failure before any model token is spent.

  V1 INSTANCE-FREEZE — the frozen instance bytes (families/** task inputs,
      checkers, truth + frozen meta STAGED.md/FAMILIES.md) are byte-identical
      to FREEZE-HASHES.sha256 RESOLVED FROM the freeze commit via git (the
      working-tree copy is never trusted). Freeze-commit ancestry of HEAD
      is also proved (history-rewrite detection).
  V2 PROTOCOL-LOCK — the living protocol docs (PREREG/ORDER/LANES/
      HARNESS-READINESS + this validator) match EITHER their frozen bytes
      OR an explicit forward amendment recorded in PROTOCOL-LOCK.json.
      Unlisted drift fails this lock (never a silent substitution).
  V3 EXECUTION-LOCK — the executing harness bytes (8 modules + runner)
      match EXECUTION-LOCK.json. Status rides along: `open-round2`
      (placeholder, re-minted on every harness change) until round-2 #14
      mints the FINAL lock after items 1-13 + synthetic attack.

Meta files (FREEZE.json, FREEZE-HASHES.sha256, *-LOCK.json, AUDIT-*,
FAMC-EXECUTION-STATUS.md, ORDER-EXPANSION.json) are pinned by git history
+ the lock records, not by the content manifest. Operational dirs (runs/,
capabilities/, harness-run/) hold evidence/artifacts/tooling, never
freeze inputs.
"""
import ast
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), os.pardir, "harness"))
from admissibility import (frozen_manifest_bytes, verify_freeze_tree,
                           load_freeze)
from order import verify_expansion as order_verify_expansion

FREEZE_COMMIT = "d1292434a261f44ad910c556e18624cef1676f37"

# Protocol docs with a life after the freeze: frozen bytes OR a listed
# forward amendment, never unlisted drift.
PROTOCOL_GOVERNED = ["PREREG.md", "ORDER.md", "LANES.md",
                     "HARNESS-READINESS.md", "preflight.py"]
# Meta pointers: integrity rides on git history + lock records.
META = {"FREEZE.json", "FREEZE-HASHES.sha256", "PROTOCOL-LOCK.json",
        "EXECUTION-LOCK.json", "FAMC-EXECUTION-STATUS.md",
        "AUDIT-ROUND1.md", "AUDIT-ROUND1-REPLY.txt",
        "AUDIT-ROUND2.md", "AUDIT-ROUND2-REPLY.txt",
        "AUDIT-ROUND3-REPLY.txt", "AUDIT-ROUND3-A11-REPLY.txt",
        "ORDER-EXPANSION.json"}
OPERATIONAL_DIRS = {"runs", "capabilities", "harness-run"}


def _sha(fp):
    with open(fp, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                           text=True)
    except FileNotFoundError:
        raise RuntimeError("git binary not found")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           + (p.stderr or p.stdout).strip()[:200])
    return p.stdout.strip()


def validate_instance(fam_c_dir, freeze_commit):
    """V1 INSTANCE-FREEZE. Returns findings list (empty = green)."""
    out = []
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
        _git(["merge-base", "--is-ancestor", freeze_commit, "HEAD"],
             cwd=root)
    except RuntimeError as e:
        return [f"V1 INSTANCE-FREEZE: ancestry unprovable: {e}"]
    try:
        raw = frozen_manifest_bytes(fam_c_dir, freeze_commit).decode()
    except RuntimeError as e:
        return [f"V1 INSTANCE-FREEZE: {e}"]
    manifest = {}
    for line in raw.splitlines():
        line = line.strip()
        if line:
            h, p = line.split("  ", 1)
            manifest[p] = h
    governed = set(PROTOCOL_GOVERNED)
    for p, h in sorted(manifest.items()):
        if p in governed:
            continue  # living protocol doc: V2 authority owns this path
        fp = os.path.join(fam_c_dir, p)
        if not os.path.exists(fp):
            out.append(f"V1 INSTANCE-FREEZE: frozen file missing: {p}")
        elif _sha(fp) != h:
            out.append(f"V1 INSTANCE-FREEZE: hash mismatch vs frozen "
                       f"manifest: {p}")
    on_disk = set()
    for root, dirs, files in os.walk(fam_c_dir):
        if os.path.basename(root) in OPERATIONAL_DIRS:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn.endswith(".pyc"):
                continue  # interpreter bytecode cache, never freeze input
            rel = os.path.relpath(os.path.join(root, fn), fam_c_dir)
            if rel in META or rel in governed:
                continue
            on_disk.add(rel)
    for p in sorted(on_disk - set(manifest)):
        out.append(f"V1 INSTANCE-FREEZE: extra file not in freeze "
                   f"manifest: {p}")
    for p in sorted(set(manifest) - on_disk - governed):
        out.append(f"V1 INSTANCE-FREEZE: freeze-manifest file missing on "
                   f"disk: {p}")
    return out


def validate_protocol(fam_c_dir, freeze_commit):
    """V2 PROTOCOL-LOCK. Returns findings list (empty = green)."""
    out = []
    lp = os.path.join(fam_c_dir, "PROTOCOL-LOCK.json")
    if not os.path.exists(lp):
        return ["V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json missing"]
    try:
        lock = json.load(open(lp))
    except ValueError as e:
        return [f"V2 PROTOCOL-LOCK: lock unparsable: {e}"]
    if lock.get("freeze_commit") != freeze_commit:
        out.append("V2 PROTOCOL-LOCK: lock freeze_commit != instance "
                   "freeze (locks disagree on the freeze)")
    governed = lock.get("governed", {})
    amendments = lock.get("amendments", [])
    by_file = {}
    for a in amendments:
        by_file.setdefault(a.get("file"), []).append(a)
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError as e:
        return out + [f"V2 PROTOCOL-LOCK: git unavailable: {e}"]
    for fn in PROTOCOL_GOVERNED:
        want_frozen = governed.get(fn)
        if not want_frozen:
            out.append(f"V2 PROTOCOL-LOCK: {fn} not governed by lock")
            continue
        try:
            frozen_bytes = subprocess.run(
                ["git", "show", f"{freeze_commit}:benchmarks/fam-c/{fn}"],
                cwd=root, capture_output=True)
            if frozen_bytes.returncode != 0:
                raise RuntimeError("unresolvable at freeze")
            frozen_sha = hashlib.sha256(frozen_bytes.stdout).hexdigest()
        except RuntimeError as e:
            out.append(f"V2 PROTOCOL-LOCK: {fn} frozen bytes {e}")
            continue
        if frozen_sha != want_frozen:
            out.append(f"V2 PROTOCOL-LOCK: {fn} lock frozen-sha != git "
                       f"truth (lock edited?)")
            continue
        fp = os.path.join(fam_c_dir, fn)
        if not os.path.exists(fp):
            out.append(f"V2 PROTOCOL-LOCK: {fn} missing on disk")
            continue
        disk = _sha(fp)
        acceptable = {frozen_sha}
        for a in by_file.get(fn, []):
            if a.get("from_sha") in acceptable:
                acceptable.add(a.get("to_sha"))
        if disk not in acceptable:
            out.append(f"V2 PROTOCOL-LOCK: {fn} drifted with no listed "
                       f"forward amendment (disk {disk[:12]} not in "
                       f"{{frozen,{len(acceptable) - 1} amendment(s)}})")
    # Item-7: the enumerated execution order is DERIVED from ORDER.md, so a
    # hand-edited or stale expansion is protocol drift by construction.
    for f in order_verify_expansion(fam_c_dir):
        out.append("V2 PROTOCOL-LOCK: " + f)
    return out


def _harness_closure(root, entry_rel):
    """Harness modules reachable from the runner by import (repo-relative).
    Only harness/*.py candidates count; governed/operational paths are
    owned by their own authority."""
    seen, todo = set(), [entry_rel]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            continue
        try:
            tree = ast.parse(open(fp).read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            else:
                continue
            for m in mods:
                cand = f"harness/{m.split('.')[0]}.py"
                if os.path.exists(os.path.join(root, cand)):
                    todo.append(cand)
    return seen


def validate_execution(fam_c_dir):
    """V3 EXECUTION-LOCK. Returns findings list (empty = green)."""
    out = []
    lp = os.path.join(fam_c_dir, "EXECUTION-LOCK.json")
    if not os.path.exists(lp):
        return ["V3 EXECUTION-LOCK: EXECUTION-LOCK.json missing"]
    try:
        lock = json.load(open(lp))
    except ValueError as e:
        return [f"V3 EXECUTION-LOCK: lock unparsable: {e}"]
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError as e:
        return [f"V3 EXECUTION-LOCK: git unavailable: {e}"]
    for rel, want in sorted(lock.get("harness_files", {}).items()):
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            out.append(f"V3 EXECUTION-LOCK: harness file missing: {rel} "
                       "(re-mint via explicit amendment, never skip)")
        elif _sha(fp) != want:
            out.append(f"V3 EXECUTION-LOCK: harness bytes changed: {rel} "
                       "(re-mint via explicit amendment commit)")
    if not lock.get("harness_files"):
        out.append("V3 EXECUTION-LOCK: lock lists no harness files")
    # Item-7 completeness: the lock must cover every harness module the
    # runner actually executes (import closure), so a new/smuggled module
    # cannot ride outside the execution authority.
    listed = set(lock.get("harness_files", {}))
    entry = next((r for r in listed if r.startswith("benchmarks/fam-c/"
                                                   "harness-run/")), None)
    if entry:
        for rel in sorted(_harness_closure(root, entry)):
            if rel not in listed:
                out.append(f"V3 EXECUTION-LOCK: unlisted harness module in "
                           f"the runner's import closure: {rel} (add it to "
                           "the lock via an explicit amendment)")
    # Item-7 closure, package-wide: the trust boundary is the harness package
    # ROOT, not just the runner's import graph. A governance module that the
    # runner does not import (harness/promotion.py mints locks and promotion
    # receipts) would otherwise execute outside the execution authority.
    # harness/tests/** stays out: the closure rule maps a module name to
    # harness/<name>.py, so test modules are never candidates.
    hdir = os.path.join(root, "harness")
    if os.path.isdir(hdir):
        for name in sorted(os.listdir(hdir)):
            if not name.endswith(".py"):
                continue
            rel = f"harness/{name}"
            if rel not in listed:
                out.append(f"V3 EXECUTION-LOCK: harness module not listed in "
                           f"the execution lock: {rel} (the lock must cover "
                           "the whole harness package root; re-mint via an "
                           "explicit amendment)")
    return out


def validate_all(fam_c_dir=None):
    """Run all three validators. Returns findings list (empty = green)."""
    fam_c_dir = fam_c_dir or HERE
    freeze = load_freeze(fam_c_dir)["freeze_commit"]
    findings = []
    findings += validate_instance(fam_c_dir, freeze)
    findings += validate_protocol(fam_c_dir, freeze)
    findings += validate_execution(fam_c_dir)
    return findings


def main():
    findings = validate_all()
    for f in findings:
        print("FAIL:", f)
    v1 = [f for f in findings if f.startswith("V1")]
    v2 = [f for f in findings if f.startswith("V2")]
    v3 = [f for f in findings if f.startswith("V3")]
    print(f"preflight: V1-instance {len(v1)} finding(s), "
          f"V2-protocol {len(v2)} finding(s), "
          f"V3-execution {len(v3)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

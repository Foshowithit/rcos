#!/usr/bin/env python3
"""Frozen visible-task authority (A12n slice D12, auditor D11-post P0).

The production runner must never treat the mutable working-tree task
directory as the source of authoritative bytes after verification.
This module derives an IMMUTABLE expected visible manifest directly
from freeze-commit git objects:

  expected_visible_paths    — top-level names the materializer must
                              produce (copied-shape: files as "name",
                              dirs as "name/"), from the frozen
                              visibility declaration;
  expected_visible_manifest — recursive {file|<rel>, dir|<rel>} sha256
                              map in _hash_tree shape, from frozen blobs;
  expected task snapshot    — the same manifest object (it IS the
                              task_snapshot shape).

Independence rule (auditor): the visibility declaration is parsed by
code in THIS module that never routes through
build_visible_root()'s parse/copy path (no seal import anywhere
here — asserted by the sealed suite). The declaration FORMAT is the
frozen contract both implement; the materializer's OUTPUT never
defines the expectation.

A12n slice D12b adds the same discipline for the GRADING
evaluator: derive_expected_evaluator() hashes the frozen
check.py/truth.json blobs, materialize_frozen_evaluator() writes
those bytes into a run-private dir for execution, and
verify_expected_provenance() re-derives both (marker-gated).

Stdlib only. All git reads are fail-closed RuntimeErrors.
"""

import hashlib
import json
import os
import subprocess


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("FROZEN-VISIBLE-GIT-UNAVAILABLE: git not found")
    if p.returncode != 0:
        raise RuntimeError(f"FROZEN-VISIBLE-GIT-FAILED git {' '.join(args)}: "
                           + (p.stderr or b"").decode()[:200])
    return p.stdout


def _git_bytes(root, freeze_commit, rel):
    """Raw bytes of repo-relative `rel` at `freeze_commit` (never disk)."""
    if not freeze_commit:
        raise RuntimeError("FROZEN-VISIBLE-NO-COMMIT: freeze commit required")
    try:
        p = subprocess.run(["git", "show", f"{freeze_commit}:{rel}"],
                           cwd=root, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("FROZEN-VISIBLE-GIT-UNAVAILABLE: git not found")
    if p.returncode != 0:
        raise RuntimeError(f"FROZEN-VISIBLE-UNRESOLVABLE {rel} at "
                           f"{freeze_commit[:12]}: "
                           + (p.stderr or b"").decode()[:200])
    return p.stdout


def _git_ls_tree(root, freeze_commit, rel):
    """Parse `git ls-tree <freeze> <rel>` (top level, with types)."""
    raw = _git(["ls-tree", freeze_commit, rel], cwd=root).decode()
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        meta, name = line.split("\t", 1)
        mode, typ, sha = meta.split()
        out.append((mode, typ, sha, name))
    return out


def _git_ls_tree_recursive(root, freeze_commit, rel):
    """Parse `git ls-tree -r -t <freeze> <rel>` (recursive, with dirs)."""
    raw = _git(["ls-tree", "-r", "-t", freeze_commit, rel],
               cwd=root).decode()
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        meta, name = line.split("\t", 1)
        mode, typ, sha = meta.split()
        out.append((mode, typ, sha, name))
    return out


def parse_visibility_declaration(text):
    """The frozen VISIBLE.md declaration format: the `task fixtures:`
    line lists agent-visible fixture names; prompt.md is always
    visible. Returns the declared top-level name set. This duplicates
    the FORMAT (frozen contract), never the materializer's code."""
    declared = set()
    for line in text.splitlines():
        if "task fixtures:" in line:
            declared.update(line.split("task fixtures:", 1)[1].split())
    declared.add("prompt.md")
    return declared


def canonical_sha(obj):
    """sha256 over canonical JSON — the single hash function for every
    expected-manifest binding (runner and provenance helper share it)."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True).encode()).hexdigest()


def derive_expected_visible(base, freeze_commit, family, task):
    """Derive the immutable expectation from freeze-commit objects.

    `base` is the fam-c dir (repo root is resolved from it via git).
    Returns {"freeze_commit", "family", "task", "paths",
    "manifest", "manifest_sha256", "paths_sha256",
    "task_snapshot_sha256"}. `paths` uses copied-shape (dirs end
    with "/"); `manifest` uses _hash_tree shape and IS the expected
    task snapshot. Raises RuntimeError (fail closed) on anything
    unexpected: unresolvable objects, a declared name missing at the
    freeze commit, a non-blob/tree object, an undeclared-copyable
    shape mismatch.
    """
    if not freeze_commit:
        raise RuntimeError("FROZEN-VISIBLE-NO-COMMIT: freeze commit required")
    root = _git(["rev-parse", "--show-toplevel"],
                cwd=base).decode().strip()
    fam_rel = f"benchmarks/fam-c/families/{family}"
    task_rel = f"{fam_rel}/{task}"
    vis_text = _git_bytes(
        root, freeze_commit, f"{task_rel}/VISIBLE.md").decode()
    declared = parse_visibility_declaration(vis_text)
    top = {}
    for (_mode, typ, _sha, name) in _git_ls_tree(root, freeze_commit,
                                                task_rel + "/"):
        # NOTE: the trailing slash asks ls-tree for the directory's
        # children (full paths); basenames are the top-level names.
        top[os.path.basename(name)] = typ
    paths, manifest = [], {}
    for name in sorted(declared):
        if name not in top:
            raise RuntimeError(
                f"FROZEN-VISIBLE-DECLARED-MISSING {task_rel}/{name} "
                f"absent at freeze {freeze_commit[:12]}")
        if top[name] == "blob":
            blob = _git_bytes(root, freeze_commit, f"{task_rel}/{name}")
            manifest["file|" + name] = hashlib.sha256(blob).hexdigest()
            paths.append(name)
        elif top[name] == "tree":
            paths.append(name + "/")
            # The declared root itself is a visible dir state (copytree
            # reproduces it byte-identically, and _hash_tree emits dir|
            # for it), then every entry strictly beneath it.
            manifest["dir|" + name] = hashlib.sha256(b"").hexdigest()
            _prefix = f"{task_rel}/{name}/"
            for (_mode, typ, _sha, full) in _git_ls_tree_recursive(
                    root, freeze_commit, f"{task_rel}/{name}"):
                if not full.startswith(_prefix):
                    continue
                rel = full[len(task_rel) + 1:]
                if typ == "tree":
                    manifest["dir|" + rel] = hashlib.sha256(b"").hexdigest()
                elif typ == "blob":
                    blob = _git_bytes(root, freeze_commit, full)
                    manifest["file|" + rel] = hashlib.sha256(
                        blob).hexdigest()
                else:
                    raise RuntimeError(
                        f"FROZEN-VISIBLE-BAD-OBJECT {full} type {typ}")
        else:
            raise RuntimeError(
                f"FROZEN-VISIBLE-BAD-OBJECT {task_rel}/{name} "
                f"type {top[name]}")
    paths = sorted(paths)
    return {"freeze_commit": freeze_commit, "family": family, "task": task,
            "paths": paths, "manifest": manifest,
            "manifest_sha256": canonical_sha(manifest),
            "paths_sha256": canonical_sha(paths),
            "task_snapshot_sha256": canonical_sha(manifest)}


def manifest_of_dir(top):
    """_hash_tree-shape manifest of a worktree dir (for the pre-call
    materialization check). Independent small walk, hashlib-direct."""
    out = {}
    for base, dirs, files in os.walk(top):
        for d in sorted(dirs):
            rel = os.path.relpath(os.path.join(base, d), top)
            out["dir|" + rel] = hashlib.sha256(b"").hexdigest()
        for fn in sorted(files):
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, top)
            with open(p, "rb") as f:
                out["file|" + rel] = hashlib.sha256(f.read()).hexdigest()
    return out


def derive_expected_evaluator(base, freeze_commit, family):
    """Derive the immutable evaluator expectation from freeze-commit
    git objects (A12n slice D12b — same authority discipline as
    derive_expected_visible, never the mutable tree).

    `base` is the fam-c dir (repo root is resolved from it via git).
    Returns {"freeze_commit", "family", "checker_rel", "truth_rel",
    "checker_sha256", "truth_sha256"} — sha256 over the frozen blob
    bytes of families/<family>/check.py and families/<family>/
    truth.json at `freeze_commit`. Raises RuntimeError (fail closed)
    on anything unexpected: missing commit, unresolvable objects.
    """
    if not freeze_commit:
        raise RuntimeError("FROZEN-EVALUATOR-NO-COMMIT: freeze commit "
                           "required (never default, never HEAD)")
    root = _git(["rev-parse", "--show-toplevel"],
                cwd=base).decode().strip()
    checker_rel = f"benchmarks/fam-c/families/{family}/check.py"
    truth_rel = f"benchmarks/fam-c/families/{family}/truth.json"
    checker_bytes = _git_bytes(root, freeze_commit, checker_rel)
    truth_bytes = _git_bytes(root, freeze_commit, truth_rel)
    return {"freeze_commit": freeze_commit, "family": family,
            "checker_rel": checker_rel, "truth_rel": truth_rel,
            "checker_sha256": hashlib.sha256(checker_bytes).hexdigest(),
            "truth_sha256": hashlib.sha256(truth_bytes).hexdigest()}


def materialize_frozen_evaluator(base, freeze_commit, family, dest_dir):
    """Materialize the frozen evaluator into run-private `dest_dir`
    (A12n slice D12b stronger form).

    Writes check.py + truth.json DIRECTLY from freeze-commit git
    blobs (never the mutable tree), verifies the written bytes equal
    the freeze-derived expectation, and returns {"dir",
    "checker_path", "truth_path", "checker_sha256", "truth_sha256"}.
    Callers execute the returned checker_path so working-tree
    mutation cannot affect grading at all.

    Closure evidence (checked for every family by smoke_h33_d12b):
    each family checker resolves its truth as a `__file__` sibling
    (`HERE/truth.json`), imports stdlib only, and reads no other
    family file — so the {check.py, truth.json} pair is the complete
    grading closure, and the materialized copy grades identically
    to the frozen tree bytes.
    """
    if not freeze_commit:
        raise RuntimeError("FROZEN-EVALUATOR-NO-COMMIT: freeze commit "
                           "required (never default, never HEAD)")
    root = _git(["rev-parse", "--show-toplevel"],
                cwd=base).decode().strip()
    exp = derive_expected_evaluator(base, freeze_commit, family)
    os.makedirs(dest_dir, exist_ok=True)
    written = {}
    for key, rel in (("check.py", exp["checker_rel"]),
                     ("truth.json", exp["truth_rel"])):
        blob = _git_bytes(root, freeze_commit, rel)
        dst = os.path.join(dest_dir, key)
        with open(dst, "wb") as f:
            f.write(blob)
        written[key] = hashlib.sha256(blob).hexdigest()
    if written["check.py"] != exp["checker_sha256"]:
        raise RuntimeError("FROZEN-EVALUATOR-MATERIALIZE-MISMATCH "
                           "written check.py != freeze-derived sha")
    if written["truth.json"] != exp["truth_sha256"]:
        raise RuntimeError("FROZEN-EVALUATOR-MATERIALIZE-MISMATCH "
                           "written truth.json != freeze-derived sha")
    return {"dir": dest_dir,
            "checker_path": os.path.join(dest_dir, "check.py"),
            "truth_path": os.path.join(dest_dir, "truth.json"),
            "checker_sha256": written["check.py"],
            "truth_sha256": written["truth.json"]}


def _resolve_repo(start):
    try:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           cwd=start, capture_output=True)
    except FileNotFoundError:
        raise ValueError("expected provenance unverifiable: git not found")
    if p.returncode != 0:
        raise ValueError("expected provenance unverifiable: "
                         f"{start} is not inside a git repo")
    return p.stdout.decode().strip()


def verify_expected_provenance(run_dir, repo_root=None):
    """Post-hoc reader: re-derive the expected manifest from the run's
    own instance_freeze_commit and require the manifest's recorded
    shas and task_snapshot to match. Returns True on pass. Raises
    ValueError(reason) on any mismatch (tampered/unverifiable).
    Manifests WITHOUT the expected fields predate the provenance
    rule and raise ValueError("legacy run: no expected provenance
    fields") so callers can grandfather them explicitly."""
    mpath = os.path.join(run_dir, "H1-RUN-MANIFEST.json")
    try:
        m = json.load(open(mpath))
    except (OSError, ValueError) as e:
        raise ValueError(f"expected provenance unreadable manifest: {e}")
    if m.get("expected_visible_manifest_sha256") is None:
        raise ValueError("legacy run: no expected provenance fields")
    fc = m.get("instance_freeze_commit")
    fam, task = m.get("family"), m.get("task")
    if not (fc and fam and task):
        raise ValueError("expected provenance unanchored: manifest lacks "
                         "freeze/family/task")
    root = repo_root
    if root is None:
        root = _resolve_repo(run_dir)
    exp = derive_expected_visible(
        os.path.join(root, "benchmarks", "fam-c"), fc, fam, task)
    if exp["manifest_sha256"] != m.get("expected_visible_manifest_sha256"):
        raise ValueError("expected manifest sha mismatch: re-derived "
                         f"{exp['manifest_sha256'][:12]} != recorded "
                         f"{str(m.get('expected_visible_manifest_sha256'))[:12]}")
    if exp["task_snapshot_sha256"] != m.get("expected_task_snapshot_sha256"):
        raise ValueError("expected task snapshot sha mismatch")
    if exp["manifest"] != m.get("task_snapshot"):
        raise ValueError("manifest.task_snapshot != re-derived expected "
                         "task snapshot")
    # A12n slice D12b (evaluator provenance): runs that record the
    # freeze-derived evaluator expectation must re-derive cleanly —
    # the recorded EXPECTED shas must equal the frozen authority,
    # and the recorded EXECUTED shas must equal it too (a run graded
    # by substituted evaluator bytes is excluded, naming evaluator
    # provenance). Manifests WITHOUT the evaluator fields predate
    # the rule and return True here (marker-gated: legacy behavior
    # unchanged).
    if m.get("expected_checker_sha256") is None and \
            m.get("expected_truth_sha256") is None:
        return True
    exp_ev = derive_expected_evaluator(
        os.path.join(root, "benchmarks", "fam-c"), fc, fam)
    if exp_ev["checker_sha256"] != m.get("expected_checker_sha256"):
        raise ValueError(
            "evaluator provenance mismatch: recorded "
            "expected_checker_sha256 "
            f"{str(m.get('expected_checker_sha256'))[:12]} != "
            f"freeze-derived {exp_ev['checker_sha256'][:12]}")
    if exp_ev["truth_sha256"] != m.get("expected_truth_sha256"):
        raise ValueError(
            "evaluator provenance mismatch: recorded "
            "expected_truth_sha256 "
            f"{str(m.get('expected_truth_sha256'))[:12]} != "
            f"freeze-derived {exp_ev['truth_sha256'][:12]}")
    if m.get("checker_sha256") != exp_ev["checker_sha256"]:
        raise ValueError(
            "evaluator provenance mismatch: recorded executed "
            f"checker_sha256 {str(m.get('checker_sha256'))[:12]} != "
            f"freeze-derived {exp_ev['checker_sha256'][:12]}")
    if m.get("truth_sha256") != exp_ev["truth_sha256"]:
        raise ValueError(
            "evaluator provenance mismatch: recorded executed "
            f"truth_sha256 {str(m.get('truth_sha256'))[:12]} != "
            f"freeze-derived {exp_ev['truth_sha256'][:12]}")
    return True

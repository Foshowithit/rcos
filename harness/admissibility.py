#!/usr/bin/env python3
"""Fam-C run admissibility classification + frozen-instance refuse gate.

Audit Round 1 (P0 #1): H1 runs are HARNESS-VALIDATION evidence — they prove
the harness works, never estimand data. An admissibility command must return
EXCLUDED for them with estimand-grade = 0. This module is that command.

Estimand-grade evidence gate (structural; claim-grade closes only after the
Round-2 audit). A run dir is ESTIMAND-ELIGIBLE only when ALL hold:
  - basename does NOT start with "H1-" (harness-validation runs excluded)
  - H1-RUN-MANIFEST.json exists with wired=true and dev_mode != true
  - manifest.instance_freeze_commit == FREEZE.json freeze_commit
    (the instance anchor, never an execution HEAD masquerading as the freeze)
  - identity.json present (provider-side identity recorded per call)
  - every manifest.usage_receipts file present
  - every usage receipt has its immutable normalized-usage artifact present
    AND verifying (A1: artifact self-sha + raw-receipt file binding + metric
    re-derivation; tampering raw OR normalized excludes the run)
  - the identity record cross-verifies against every usage receipt
    (item 3: endpoint + model_requested + request-body hash equal; echoed
    model + provider response id nonempty; altering model/params on
    either side excludes the run)
  - EVIDENCE-CHAIN.jsonl present
Anything else is EXCLUDED with a one-line reason.

A12n slice D12c: expected-provenance re-derivation is a PRECONDITION
over all of the above, never an alternative (first failure in gate
order is reported; rule-bound runs must re-derive cleanly, legacy
runs take the same gates below).

verify_instance_frozen() is the runner's refuse-START gate: the executed
instance subtree (families/<family>/<task>/** plus the family check.py and
truth.json that grade it) must be byte-identical to FREEZE-HASHES.sha256 —
no drift, no extras — before any model token is spent. Item-5 hardening
(audit round 2): the manifest is resolved from the FREEZE COMMIT via git,
never from the working-tree copy (a local edit cannot redefine truth);
and verify_freeze_tree() proves FREEZE.json's recorded freeze_tree equals
the freeze commit's tree of the frozen root (base) — altering the record
refuses the start. Stdlib only.

Stdlib only. Importable (classify_run_dir / verify_instance_frozen) and a CLI.
"""
import hashlib
import json
import os
import subprocess
import sys

from usage import (verify_normalized_usage, verify_request_binding,
                   verify_adapter_binding)
from identity import verify_identity_binding

EXCLUDED = "EXCLUDED"
ELIGIBLE = "ESTIMAND-ELIGIBLE"


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_freeze(base):
    """Return {freeze_commit, freeze_tree} from FREEZE.json (raise if broken)."""
    fp = os.path.join(base, "FREEZE.json")
    if not os.path.exists(fp):
        raise RuntimeError(f"FREEZE.json missing under {base}")
    fj = json.load(open(fp))
    fc = fj.get("freeze_commit")
    if not fc:
        raise RuntimeError("FREEZE.json has no freeze_commit")
    return {"freeze_commit": fc, "freeze_tree": fj.get("freeze_tree")}


def classify_run_dir(run_dir, freeze_commit):
    """Classify one run directory. Returns (status, reason)."""
    reason = None
    name = os.path.basename(run_dir)
    mpath = os.path.join(run_dir, "H1-RUN-MANIFEST.json")
    if not os.path.exists(mpath):
        return EXCLUDED, "no run manifest (pre-harness / ad-hoc evidence)"
    if name.startswith("H1-"):
        return EXCLUDED, ("H1 harness-validation run: proves the harness, "
                          "never estimand data")
    m = json.load(open(mpath))
    if m.get("wired") is not True:
        reason = "unwired run (dev_mode / legacy unlinked)"
    elif m.get("dev_mode"):
        reason = "dev_mode run stamped by --dev-unwired-outdir escape"
    elif m.get("instance_freeze_commit") != freeze_commit:
        reason = (f"instance anchor {str(m.get('instance_freeze_commit'))[:12]} "
                  f"!= freeze {freeze_commit[:12]}")
    # A12n slice D12c (Finding A — provenance is a PRECONDITION /
    # CONJUNCT, never an alternative): the re-derivation below runs
    # on EVERY wired run that reaches it, and it never skips the
    # identity / usage / chain gates further below — each gate is
    # evaluated in turn and the FIRST failure is reported with its
    # established wording. Whether the run is rule-bound is decided
    # by the helper from the frozen rule (any surviving provenance
    # marker proves rule-era production; no markers at all is the
    # only legacy route): rule-bound runs must re-derive cleanly,
    # and any other provenance failure excludes the run here,
    # naming provenance. A genuinely pre-rule run raises the
    # helper's named legacy guard and proceeds to the legacy gates
    # (never a crash).
    if reason is None:
        try:
            import frozen_visible
            frozen_visible.verify_expected_provenance(run_dir)
        except ValueError as e:
            if str(e).startswith("legacy run:"):
                pass  # genuinely pre-rule: legacy gates below decide
            else:
                reason = f"expected provenance refused: {e}"
        except RuntimeError as e:
            reason = f"expected provenance unverifiable: {e}"
    if reason is None and not os.path.exists(
            os.path.join(run_dir, "identity.json")):
        reason = "no provider identity.json (echoed model id never recorded)"
    if reason is None:
        # A12.0 (audit round 2): ZERO-WORK is not evidence. A wired run that
        # lists no usage receipt never spent model work, and a receipt whose
        # normalized primary_work (uncached input + output tokens) is zero or
        # absent records a run that produced no model work. Both are EXCLUDED
        # — never raised, so a bad run cannot abort a sweep.
        receipts = m.get("usage_receipts") or []
        missing = [r for r in receipts
                   if not os.path.exists(os.path.join(run_dir, r))]
        if not receipts:
            reason = "ZERO-WORK: wired run lists no usage receipt"
        elif missing:
            reason = "usage receipts missing: " + ", ".join(missing)
        elif not os.path.exists(os.path.join(run_dir, "EVIDENCE-CHAIN.jsonl")):
            reason = "no EVIDENCE-CHAIN.jsonl"
        else:
            # A1 (audit round 2 item 1): every wired receipt must have its
            # immutable normalized-usage artifact, and it must VERIFY — the
            # artifact self-sha, the raw-receipt file binding, and metric
            # re-derivation are all recomputed. Tampering the RAW receipt or
            # the NORMALIZED artifact flips the run EXCLUDED (fail closed).
            for r in (m.get("usage_receipts") or []):
                if not r.endswith(".json"):
                    reason = f"usage receipt name invalid for {r}"
                    break
                nu = os.path.join(run_dir, r[:-5] + ".normalized.json")
                if not os.path.exists(nu):
                    reason = f"normalized usage artifact missing for {r}"
                    break
                try:
                    verify_normalized_usage(nu)
                except ValueError as e:
                    reason = f"normalized usage invalid for {r}: {e}"
                    break
                # A12.0 ZERO-WORK: the artifact verified, but a verified
                # artifact may still record no primary work. A model run that
                # spent no model work is not admissible evidence (bool is not
                # an int here: True would otherwise read as 1).
                try:
                    obj = json.load(open(nu))
                except (OSError, ValueError) as e:
                    reason = f"normalized usage unreadable for {r}: {e}"
                    break
                pw = obj.get("primary_work")
                if isinstance(pw, bool) or not isinstance(pw, int) or pw <= 0:
                    reason = (
                        f"ZERO-WORK: {r} records no primary work "
                        f"(uncached_input + output_tokens == {pw!r}); a model "
                        "run that spent no model work is not admissible "
                        "evidence")
                    break
            # A11.2: the declared adapter must be the LANE's adapter for the
            # endpoint/model on the receipt, and the persisted request bytes
            # must reproduce the receipt hash and agree with the identity
            # record. A relabeled receipt (P bytes claiming the Q adapter),
            # a wrong endpoint/model for that adapter, or a mutated
            # generation param in ANY representation excludes the run.
            if not reason:
                for r in (m.get("usage_receipts") or []):
                    try:
                        rc = json.load(open(os.path.join(run_dir, r)))
                    except (OSError, ValueError) as e:
                        reason = f"usage receipt unreadable for {r}: {e}"
                        break
                    nid = rc.get("normalizer_id")
                    try:
                        verify_adapter_binding(
                            nid, lane=m.get("lane"), receipt=rc)
                    except ValueError as e:
                        reason = f"adapter binding invalid for {r}: {e}"
                        break
                    if m.get("usage_receipts"):
                        idf = m.get("identity_file")
                        if idf and os.path.exists(
                                os.path.join(run_dir, idf)):
                            try:
                                verify_request_binding(
                                    os.path.join(run_dir, r),
                                    os.path.join(run_dir, idf))
                            except ValueError as e:
                                reason = (f"request binding invalid for "
                                          f"{r}: {e}")
                                break
            # Item-3 (audit round 2): the identity record must cross-verify
            # against EVERY usage receipt (endpoint + model_requested +
            # request-body hash equal; echo + provider id nonempty) —
            # altering the model or any request param on either side after
            # the call excludes the run. Runs with no receipts (hermetic
            # fixtures) skip this gate.
            if not reason and (m.get("usage_receipts") or []):
                idf = m.get("identity_file")
                idp = os.path.join(run_dir, idf) if idf else None
                if not idf or not os.path.exists(idp):
                    reason = "no bound identity file for usage receipts " \
                        f"({idf!r} missing)"
                else:
                    for r in (m.get("usage_receipts") or []):
                        try:
                            verify_identity_binding(
                                idp, os.path.join(run_dir, r))
                        except ValueError as e:
                            reason = f"identity binding invalid for {r}: {e}"
                            break
    if reason:
        return EXCLUDED, reason
    return ELIGIBLE, "full evidence gate satisfied"


def classify_runs(runs_dir, freeze_commit):
    """Classify every run dir under runs_dir. Returns
    (ordered list of (name, status, reason), estimand_count)."""
    out = []
    count = 0
    for name in sorted(os.listdir(runs_dir)):
        d = os.path.join(runs_dir, name)
        if not os.path.isdir(d):
            continue
        status, reason = classify_run_dir(d, freeze_commit)
        if status == ELIGIBLE:
            count += 1
        out.append((name, status, reason))
    return out, count


def _git(args, cwd):
    """Run git fail-closed: raises RuntimeError on missing binary or
    non-zero exit (never a silent empty result)."""
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                           text=True)
    except FileNotFoundError:
        raise RuntimeError("FROZEN-GIT-UNAVAILABLE: git binary not found")
    if p.returncode != 0:
        raise RuntimeError(f"FROZEN-GIT-FAILED git {' '.join(args)}: "
                           + (p.stderr or p.stdout).strip()[:200])
    return p.stdout.strip()


def frozen_manifest_bytes(base, freeze_commit):
    """Return the FREEZE-HASHES.sha256 BYTES recorded at freeze_commit.

    Resolved via `git show <freeze>:<path>` — the working-tree copy is
    NEVER consulted, so editing the local file cannot redefine truth
    (fail closed when the object is unresolvable). `base` is the frozen
    root (the dir containing FREEZE-HASHES.sha256)."""
    if not freeze_commit:
        raise RuntimeError("FROZEN-INSTANCE-NO-COMMIT: freeze commit "
                           "required (never default, never HEAD)")
    root = _git(["rev-parse", "--show-toplevel"], cwd=base)
    rel = os.path.relpath(os.path.join(base, "FREEZE-HASHES.sha256"), root)
    try:
        p = subprocess.run(["git", "show", f"{freeze_commit}:{rel}"],
                           cwd=root, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("FROZEN-GIT-UNAVAILABLE: git binary not found")
    if p.returncode != 0:
        raise RuntimeError(f"FROZEN-MANIFEST-UNRESOLVABLE {rel} at "
                           f"{freeze_commit[:12]}: "
                           + (p.stderr or b"").decode()[:200])
    return p.stdout


def verify_freeze_tree(base, freeze_commit):
    """Prove FREEZE.json's recorded freeze_tree equals the freeze commit's
    tree of the frozen root `base` (original freeze semantics: the
    benchmarks/fam-c subtree tree at the freeze commit). Raises
    RuntimeError(FROZEN-TREE-...) when unrecorded, unresolvable, or
    altered — the runner refuses to start. Returns the verified tree."""
    fj_path = os.path.join(base, "FREEZE.json")
    if not os.path.exists(fj_path):
        raise RuntimeError("FROZEN-TREE-UNRECORDED " + fj_path)
    recorded = json.load(open(fj_path)).get("freeze_tree")
    if not recorded:
        raise RuntimeError("FROZEN-TREE-UNRECORDED: no freeze_tree in "
                           + fj_path)
    root = _git(["rev-parse", "--show-toplevel"], cwd=base)
    rel = os.path.relpath(base, root)
    spec = f"{freeze_commit}^{{tree}}" if rel == "." else f"{freeze_commit}:{rel}"
    expected = _git(["rev-parse", spec], cwd=root)
    if recorded != expected:
        raise RuntimeError(f"FROZEN-TREE-MISMATCH recorded {recorded[:12]} "
                           f"!= freeze commit {freeze_commit[:12]} tree of "
                           f"{rel} ({expected[:12]}): FREEZE.json altered "
                           "or stale — refuse start")
    return expected


def verify_instance_frozen(base, family, task, freeze_commit=None):
    """Refuse-START gate (audit P0 #4 dual anchors, content half; item-5
    hardened).

    The executed instance — families/<family>/<task>/** plus the family
    check.py/truth.json that grade it — must be byte-identical to the
    FREEZE-HASHES manifest RESOLVED FROM freeze_commit VIA GIT (never the
    working-tree copy). Raises RuntimeError(FROZEN-INSTANCE-...) on any
    mismatch; otherwise returns {"family", "task", "verified_files",
    "freeze_commit", "expected_visible_paths", "expected_visible_manifest",
    "expected_visible_manifest_sha256", "expected_visible_paths_sha256",
    "expected_task_snapshot_sha256", "expected_checker_sha256",
    "expected_truth_sha256"}. freeze_commit is REQUIRED (no
    default, never HEAD).

    A12n slice D12 (auditor D11-post P0): the expected visible
    manifest/paths are derived from freeze-commit git objects (see
    frozen_visible) and returned as the SINGLE immutable authority
    object — callers must thread this object through materialization,
    the pre-model-call gate, and the sandbox binding, and must never
    re-derive authority from the mutable task dir afterwards.

    A12n slice D12b: the same authority object additionally carries
    the freeze-derived GRADING evaluator shas
    (expected_checker_sha256 / expected_truth_sha256, from
    frozen_visible.derive_expected_evaluator — never the mutable
    tree). The visible-set authority above is unchanged.
    """
    if not freeze_commit:
        raise RuntimeError("FROZEN-INSTANCE-NO-COMMIT: freeze commit "
                           "required (never default, never HEAD)")
    man = {}
    raw = frozen_manifest_bytes(base, freeze_commit).decode()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        h, p = line.split("  ", 1)
        man[p] = h
    prefix = f"families/{family}/"
    task_prefix = f"families/{family}/{task}/"
    expected = {}
    for p, h in man.items():
        if p.startswith(task_prefix) or p in (
                f"families/{family}/check.py", f"families/{family}/truth.json"):
            expected[p] = h
    if not expected:
        raise RuntimeError(f"FROZEN-INSTANCE-UNKNOWN family={family} task={task} "
                           f"has no frozen entries in FREEZE-HASHES.sha256 "
                           f"at {freeze_commit[:12]}")
    # every expected file exists and hashes equal
    for p, h in sorted(expected.items()):
        fp = os.path.join(base, p)
        if not os.path.exists(fp):
            raise RuntimeError(f"FROZEN-INSTANCE-MISSING {p}")
        if _sha(fp) != h:
            raise RuntimeError(f"FROZEN-INSTANCE-DRIFT {p}")
    # nothing extra inside the executed task dir (extras would enter jail/prompt)
    tdir = os.path.join(base, f"families/{family}/{task}")
    for root, _dirs, files in os.walk(tdir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), base)
            if rel not in expected:
                raise RuntimeError(f"FROZEN-INSTANCE-EXTRA {rel}")
    n = len(expected)
    import frozen_visible
    exp = frozen_visible.derive_expected_visible(
        base, freeze_commit, family, task)
    exp_ev = frozen_visible.derive_expected_evaluator(
        base, freeze_commit, family)
    return {"family": family, "task": task, "verified_files": n,
            "freeze_commit": freeze_commit,
            "expected_visible_paths": exp["paths"],
            "expected_visible_manifest": exp["manifest"],
            "expected_visible_manifest_sha256": exp["manifest_sha256"],
            "expected_visible_paths_sha256": exp["paths_sha256"],
            "expected_task_snapshot_sha256": exp["task_snapshot_sha256"],
            "expected_checker_sha256": exp_ev["checker_sha256"],
            "expected_truth_sha256": exp_ev["truth_sha256"]}


def main(argv):
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    runs_dir = os.path.join(root, "benchmarks", "fam-c", "runs")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs-dir", default=runs_dir)
    ap.add_argument("--fam-c-dir",
                    default=os.path.join(root, "benchmarks", "fam-c"))
    a = ap.parse_args(argv)
    freeze = load_freeze(a.fam_c_dir)
    results, count = classify_runs(a.runs_dir, freeze["freeze_commit"])
    print(f"freeze_commit={freeze['freeze_commit'][:12]}  "
          f"runs under {a.runs_dir}")
    for name, status, reason in results:
        print(f"{status:16s} {name}: {reason}")
    print(f"estimand-grade = {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

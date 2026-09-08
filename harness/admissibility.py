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
  - EVIDENCE-CHAIN.jsonl present
Anything else is EXCLUDED with a one-line reason.

verify_instance_frozen() is the runner's refuse-START gate: the executed
instance subtree (families/<family>/<task>/** plus the family check.py and
truth.json that grade it) must be byte-identical to FREEZE-HASHES.sha256 —
no drift, no extras — before any model token is spent.

Stdlib only. Importable (classify_run_dir / verify_instance_frozen) and a CLI.
"""
import hashlib
import json
import os
import sys

from usage import verify_normalized_usage

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
    elif not os.path.exists(os.path.join(run_dir, "identity.json")):
        reason = "no provider identity.json (echoed model id never recorded)"
    else:
        missing = [r for r in (m.get("usage_receipts") or [])
                   if not os.path.exists(os.path.join(run_dir, r))]
        if missing:
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


def verify_instance_frozen(base, family, task):
    """Refuse-START gate (audit P0 #4 dual anchors, content half).

    The executed instance — families/<family>/<task>/** plus the family
    check.py/truth.json that grade it — must be byte-identical to
    FREEZE-HASHES.sha256 (no drift, no extra files inside the task dir).
    Raises RuntimeError(FROZEN-INSTANCE-...) on any mismatch; otherwise
    returns {"family", "task", "verified_files", "verified_bytes"}.
    """
    man = {}
    mp = os.path.join(base, "FREEZE-HASHES.sha256")
    if not os.path.exists(mp):
        raise RuntimeError("FROZEN-INSTANCE-MANIFEST-MISSING " + mp)
    for line in open(mp):
        h, p = line.strip().split("  ", 1)
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
                           f"has no frozen entries in {mp}")
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
    return {"family": family, "task": task, "verified_files": n}


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

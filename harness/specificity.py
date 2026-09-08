#!/usr/bin/env python3
"""T4-CONFORMANCE-READINESS production caller (RCOS A12b follow-through,
A12c C1-3 reframe of auditor A12c.8).

`lock.specificity_gate` was previously exercised only by sealed-smoke
hand-built dicts: nothing in the production path ran it, so a readiness
state whose only committed lock is non-discriminating was never surfaced
as a conformance failure by any runnable entry point. This module is
that runnable entry point: it discovers COMMITTED locks from production
capability dirs on disk and runs the gate over them.

This surface is T4-CONFORMANCE-READINESS: it judges whether the
committed capability contracts are conformance-ready, NOT the final
observed T4 specificity, which requires post-T4 lifecycle/result
evidence.

The intended consumer is the section-24 / estimand readiness gate (A15):
readiness must consult `report()` (or this file's CLI) and refuse to
claim readiness on any `contract-conformance-failure` verdict. Stdlib
only.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lock as lockmod  # noqa: E402
import order as ordermod  # noqa: E402

LOCK_FILENAME = "CAPABILITY_LOCK.json"
EMPTY_CAUSE = "no committed capability locks"

HELP = """usage: specificity.py [FAM_C_DIR]

T4-CONFORMANCE-READINESS: report whether the committed capability
contracts are conformance-ready. This is NOT the final observed T4
specificity, which requires post-T4 lifecycle/result evidence.

Exit 0 with verdict contract-conformance-ready when every discovered
committed lock is discriminating; exit 1 with verdict
contract-conformance-failure otherwise (including when a lock is
corrupt, unreadable, or a symlink — those are reported as inadmissible
naming the path and reason, never silently skipped).
"""


def _lock_files_from_expansion(fam_c_dir):
    """Yield (family, lock_path) for every expansion-derived production
    capability dir carrying a candidate lock. Uses the existing order API
    for path derivation; never hand-builds locks, never reads K.md.
    Symlinks count as candidates (they are refused as inadmissible by
    the reader, never silently skipped); only absent paths are skipped.
    """
    try:
        exp = ordermod.load_expansion(fam_c_dir)
    except (OSError, ValueError, KeyError):
        return
    blocks = exp.get("blocks") or []
    families = exp.get("families") or []
    universes = (exp.get("capability_universes")
                 or exp.get("universes") or [])
    for block in sorted(blocks):
        for family in sorted(families):
            for universe in sorted(universes):
                try:
                    capdir = ordermod.capability_dir(
                        fam_c_dir, block, universe, family)
                except (OSError, ValueError, KeyError):
                    continue
                path = os.path.join(capdir, LOCK_FILENAME)
                if os.path.lexists(path):
                    yield family, path


def _lock_files_from_disk(fam_c_dir):
    """Yield (family, lock_path) for every candidate lock found by walking
    the production state tree. Backstop so a committed lock is never
    invisible to the gate just because the current expansion topology
    changed around it. Reads lock bytes only — never K.md. Symlinks
    count as candidates (refused as inadmissible, never skipped); only
    absent paths are skipped."""
    state_root = os.path.join(fam_c_dir, "state")
    if not os.path.isdir(state_root):
        return
    for dirpath, _dirnames, filenames in os.walk(state_root):
        if LOCK_FILENAME not in filenames:
            continue
        path = os.path.join(dirpath, LOCK_FILENAME)
        if not os.path.lexists(path):
            continue
        family = None
        # Production layout: state/<block>/<universe>/<family>/capability.
        rel = os.path.relpath(dirpath, state_root)
        parts = rel.split(os.sep)
        if (len(parts) == 4 and parts[3] == "capability"
                and all(parts[:3])):
            family = parts[2]
        if family is None:
            continue
        yield family, path


def _candidate_paths(fam_c_dir):
    """Deduped (family, path) candidates from both discovery surfaces."""
    seen = set()
    for family, path in list(_lock_files_from_expansion(fam_c_dir)) \
            + list(_lock_files_from_disk(fam_c_dir)):
        real = os.path.abspath(path)
        if real in seen:
            continue
        seen.add(real)
        yield family, path


def _read_lock(path):
    """Read one candidate lock. Returns (lock_dict, None) on success,
    else (None, reason) where reason names the path and the refusal —
    a symlink, an unreadable file, or unparsable bytes is an
    inadmissible lock, never a silent skip."""
    if os.path.islink(path):
        return None, (f"{path}: symlink is not a committed lock "
                       f"(refused; a lock must be a real file)")
    try:
        with open(path, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except OSError as e:
        return None, f"{path}: unreadable: {e}"
    except ValueError as e:
        return None, f"{path}: unparsable: {e}"
    return lock, None


def discover_locks(fam_c_dir):
    """Enumerate COMMITTED locks from production capability dirs.

    Returns {family: lock_dict}, each lock read from its capability dir
    (never hand-built, never sourced from K.md). A family with locks in
    several capability dirs (e.g. universes A and C) contributes exactly
    one entry: the worst verdict wins (an inadmissible lock beats a
    non-discriminating one beats a discriminating one; ties break by
    sorted (block, universe) path), so no committed failure is hidden
    behind a passing sibling. Candidate paths that are symlinks,
    unreadable, or unparsable are NOT committed locks: they are absent
    here and reported by discover_problems() instead (never silently
    skipped).
    """
    per_family = {}   # family -> list of (sort_key, lock_dict)
    for family, path in _candidate_paths(fam_c_dir):
        lock, _problem = _read_lock(path)
        if lock is None:
            continue
        per_family.setdefault(family, []).append(
            (os.path.abspath(path), lock))
    out = {}
    for family in sorted(per_family):
        cands = per_family[family]
        if len(cands) == 1:
            out[family] = cands[0][1]
            continue
        # Worst verdict wins; ties break by sorted path (deterministic).
        def _rank(item):
            _path, lk = item
            gate = lockmod.specificity_gate({family: lk})
            if gate["inadmissible"]:
                return (0, _path)
            if gate["non_discriminating"]:
                return (1, _path)
            return (2, _path)
        out[family] = sorted(cands, key=_rank)[0][1]
    return out


def discover_problems(fam_c_dir):
    """Enumerate candidate locks that cannot be committed reads.

    Returns {family: [reason, ...]} where each reason names the path
    and the refusal (symlink / unreadable / unparsable). A family
    whose ONLY lock is corrupt appears here — inadmissible, never
    absent, and forcing contract_conformance_ready False in report().
    """
    out = {}
    for family, path in _candidate_paths(fam_c_dir):
        _lock, problem = _read_lock(path)
        if problem is not None:
            out.setdefault(family, []).append(problem)
    return out


def report(fam_c_dir):
    """Run the conformance-readiness gate over the discovered locks.

    Returns {"families": [...], "discriminating": [...],
    "non_discriminating": {family: cause},
    "inadmissible": {family: [reasons]},
    "verdict": "contract-conformance-ready" |
    "contract-conformance-failure",
    "contract_conformance_ready": bool,
    "cause": committed failure cause, or None on a pass} by delegating
    to `lock.specificity_gate`. Zero discovered locks is NOT a vacuous
    pass: it is a contract-conformance-failure with the committed cause
    "no committed capability locks". A corrupt, unreadable, or
    symlinked lock is inadmissible (naming path and reason) and forces
    contract_conformance_ready False even beside a good lock.
    """
    locks = discover_locks(fam_c_dir)
    problems = discover_problems(fam_c_dir)
    if not locks and not problems:
        return {"families": [],
                "discriminating": [],
                "non_discriminating": {},
                "inadmissible": {},
                "verdict": "contract-conformance-failure",
                "contract_conformance_ready": False,
                "cause": EMPTY_CAUSE}
    gate = lockmod.specificity_gate(locks) if locks else {
        "discriminating": [], "non_discriminating": {},
        "inadmissible": {}}
    inadmissible = {k: list(v) for k, v in gate["inadmissible"].items()}
    for fam in sorted(problems):
        inadmissible.setdefault(fam, []).extend(problems[fam])
    ready = (gate["discriminating"] == sorted(locks)
             and not gate["non_discriminating"]
             and not inadmissible)
    # gate["discriminating"] is expansion-sorted already (the gate
    # iterates sorted families), so equality with sorted(locks) means
    # every discovered lock discriminates and nothing is inadmissible.
    rep = {"families": sorted(set(locks) | set(problems)),
           "discriminating": list(gate["discriminating"]),
           "non_discriminating": dict(gate["non_discriminating"]),
           "inadmissible": inadmissible,
           "verdict": ("contract-conformance-ready" if ready
                       else "contract-conformance-failure"),
           "contract_conformance_ready": bool(ready),
           "cause": None}
    if not ready:
        causes = []
        for fam in sorted(rep["non_discriminating"]):
            causes.append(f"{fam}: {rep['non_discriminating'][fam]}")
        for fam in sorted(rep["inadmissible"]):
            causes.append(f"{fam}: "
                          + "; ".join(rep["inadmissible"][fam]))
        rep["cause"] = "; ".join(causes) if causes else EMPTY_CAUSE
    return rep


def main(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    default = os.path.join(os.path.dirname(HERE), "benchmarks", "fam-c")
    fam_c_dir = argv[1] if len(argv) > 1 else default
    rep = report(fam_c_dir)
    print(f"t4-conformance-readiness report for {fam_c_dir}")
    print(f"families ({len(rep['families'])}): "
          + (", ".join(rep["families"]) or "(none)"))
    print(f"discriminating ({len(rep['discriminating'])}): "
          + (", ".join(rep["discriminating"]) or "(none)"))
    print(f"non-discriminating ({len(rep['non_discriminating'])}):")
    for fam in sorted(rep["non_discriminating"]):
        print(f"  {fam}: {rep['non_discriminating'][fam]}")
    print(f"inadmissible ({len(rep['inadmissible'])}):")
    for fam in sorted(rep["inadmissible"]):
        for reason in rep["inadmissible"][fam]:
            print(f"  {fam}: {reason}")
    print(f"verdict: {rep['verdict']}")
    print(f"contract_conformance_ready: "
          f"{str(rep['contract_conformance_ready']).lower()}")
    print(json.dumps(rep, indent=1, sort_keys=True))
    if not rep["contract_conformance_ready"] or not rep["families"]:
        sys.stderr.write(f"CONFORMANCE-NOT-READY: {rep['cause']}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

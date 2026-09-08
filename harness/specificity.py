#!/usr/bin/env python3
"""Production caller for the lock specificity gate (RCOS A12b follow-through).

`lock.specificity_gate` was previously exercised only by sealed-smoke
hand-built dicts: nothing in the production path ran it, so a readiness
state whose only committed lock is non-discriminating was never surfaced
as a specificity failure by any runnable entry point. This module is that
runnable entry point: it discovers COMMITTED locks from production
capability dirs on disk and runs the gate over them.

The intended consumer is the section-24 / estimand readiness gate (A15):
readiness must consult `report()` (or this file's CLI) and refuse to
claim readiness on any `specificity-failure` verdict. Stdlib only.
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


def _lock_files_from_expansion(fam_c_dir):
    """Yield (family, lock_path) for every expansion-derived production
    capability dir carrying a committed lock. Uses the existing order API
    for path derivation; never hand-builds locks, never reads K.md."""
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
                if os.path.isfile(path) and not os.path.islink(path):
                    yield family, path


def _lock_files_from_disk(fam_c_dir):
    """Yield (family, lock_path) for every committed lock found by walking
    the production state tree. Backstop so a committed lock is never
    invisible to the gate just because the current expansion topology
    changed around it. Reads lock bytes only — never K.md."""
    state_root = os.path.join(fam_c_dir, "state")
    if not os.path.isdir(state_root):
        return
    for dirpath, _dirnames, filenames in os.walk(state_root):
        if LOCK_FILENAME not in filenames:
            continue
        path = os.path.join(dirpath, LOCK_FILENAME)
        if not os.path.isfile(path) or os.path.islink(path):
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


def discover_locks(fam_c_dir):
    """Enumerate COMMITTED locks from production capability dirs.

    Returns {family: lock_dict}, each lock read from its capability dir
    (never hand-built, never sourced from K.md). A family with locks in
    several capability dirs (e.g. universes A and C) contributes exactly
    one entry: the worst verdict wins (an inadmissible lock beats a
    non-discriminating one beats a discriminating one; ties break by
    sorted (block, universe) path), so no committed failure is hidden
    behind a passing sibling. Files that are absent, symlinked, or
    unparsable are not committed locks and are skipped.
    """
    per_family = {}   # family -> list of (sort_key, lock_dict)
    seen = set()
    for family, path in list(_lock_files_from_expansion(fam_c_dir)) \
            + list(_lock_files_from_disk(fam_c_dir)):
        real = os.path.abspath(path)
        if real in seen:
            continue
        seen.add(real)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lock = json.load(f)
        except (OSError, ValueError):
            continue
        per_family.setdefault(family, []).append((real, lock))
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


def report(fam_c_dir):
    """Run the specificity gate over the discovered committed locks.

    Returns {"families": [...], "discriminating": [...],
    "non_discriminating": {family: cause},
    "inadmissible": {family: [reasons]},
    "verdict": "specificity-pass" | "specificity-failure",
    "cause": committed failure cause, or None on a pass} by delegating
    to `lock.specificity_gate`. Zero discovered locks is NOT a vacuous
    pass: it is a specificity-failure with the committed cause
    "no committed capability locks".
    """
    locks = discover_locks(fam_c_dir)
    if not locks:
        return {"families": [],
                "discriminating": [],
                "non_discriminating": {},
                "inadmissible": {},
                "verdict": "specificity-failure",
                "cause": EMPTY_CAUSE}
    gate = lockmod.specificity_gate(locks)
    rep = {"families": sorted(locks),
           "discriminating": list(gate["discriminating"]),
           "non_discriminating": dict(gate["non_discriminating"]),
           "inadmissible": {k: list(v)
                            for k, v in gate["inadmissible"].items()},
           "verdict": gate["verdict"],
           "cause": None}
    if gate["verdict"] != "specificity-pass":
        causes = []
        for fam in sorted(rep["non_discriminating"]):
            causes.append(f"{fam}: {rep['non_discriminating'][fam]}")
        for fam in sorted(rep["inadmissible"]):
            causes.append(f"{fam}: "
                          + "; ".join(rep["inadmissible"][fam]))
        rep["cause"] = "; ".join(causes) if causes else EMPTY_CAUSE
    return rep


def main(argv):
    default = os.path.join(os.path.dirname(HERE), "benchmarks", "fam-c")
    fam_c_dir = argv[1] if len(argv) > 1 else default
    rep = report(fam_c_dir)
    print(f"specificity report for {fam_c_dir}")
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
    print(json.dumps(rep, indent=1, sort_keys=True))
    if rep["verdict"] != "specificity-pass" or not rep["families"]:
        sys.stderr.write(f"SPECIFICITY-FAILURE: {rep['cause']}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

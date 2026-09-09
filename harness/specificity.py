#!/usr/bin/env python3
"""T4-CONFORMANCE-READINESS reporter (RCOS A12b follow-through, A12c C1-3
reframe of auditor A12c.8, A12d slice D3 / auditor A12d.6 reframe).

Readiness is DERIVED from the ORDER EXPANSION, never from disk
enumeration:

    read <fam_c_dir>/ORDER.md text -> order.expand(text) ->
    every cell with event == "CAPABILITY_LOCK" (exactly 24 tuples
    (block, universe, family) in order, set {PQ,QP} x {A,C} x
    {fam01..fam06}; fail closed otherwise) ->
    for EACH expected cell, order.cell_state(fam_c_dir, cell) is the
    SOLE admissibility authority (a lock is PRESENT only when status
    == "COMPLETE"; no private receipt/lock re-implementation, no disk
    walk for presence) ->
    for each present cell, the lock is loaded through the governed
    path and its conformance recomputed with conformance.verdict under
    the LIVE governed map: the lock's conformance_map_sha256 must
    equal the live map sha and its cause must equal the recomputed v3
    rule cause (else FAILURE) ->
    additionally, STRAY lock directories under state/**/capability
    that are NOT in the expansion -> FAILURE naming each path (this
    is the ONLY disk walk, for stray detection).

This surface is T4-CONFORMANCE-READINESS: it judges whether the
committed capability contracts are conformance-ready, NOT the final
observed T4 specificity, which requires post-T4 lifecycle/result
evidence.

The intended consumer is the section-24 / estimand readiness gate (A15):
readiness must consult `report()` (or this file's CLI) and refuse to
claim readiness on any verdict but contract-conformance-READY. Stdlib
only.

Verdicts and exit codes (frozen contract, slice D3 B5):

    contract-conformance-READY (exit 0) iff 24/24 present, every lock
    admissible through cell_state, every lock discriminating
    (non_discriminating False under the live v3 map), no strays;

    contract-conformance-INCOMPLETE (exit 1) iff present < 24 with no
    failure condition: reports present=<n> missing=<24-n> plus every
    missing (block, universe, family) tuple sorted;

    contract-conformance-FAILURE (exit 2) if any present cell is
    inadmissible (cell_state not COMPLETE while a lock file exists,
    hand-built lock, old-map lock, non-discriminating lock,
    symlinked capability dir, stray lock dir, count/set mismatch).

Programmatic contract (frozen, slice D3 B5):

    specificity.report(fam_c_dir) -> dict with EXACTLY the keys
    {verdict, present, missing, cells, problems} where verdict is one
    of the three literals above, present is an int 0..24, missing is
    the sorted list of [block, universe, family] lists (length
    24-present), cells is the list of 24 dicts (one per expected
    CAPABILITY_LOCK cell in expansion order, each with exactly the
    keys {block, universe, family, present, admissible,
    discriminating, verdict}), and problems is a list of str (empty
    iff verdict is READY). report() NEVER raises on a damaged tree
    (symlinked parent, unreadable lock, stray dir, unparsable JSON):
    it returns FAILURE with a naming problems entry.

CLI contract (frozen, slice D3 B5):

    python3 harness/specificity.py [fam_c_dir] prints, in order: one
    per-cell line per expected cell containing "(block, universe,
    family)" and present=, admissible=, discriminating=, verdict=;
    then ONE machine-readable summary line containing the verdict
    literal plus present=<n> and missing=<n>; then the JSON report.
    Exit 0 for READY, 1 for INCOMPLETE, 2 for FAILURE. fam_c_dir
    defaults to the repo's benchmarks/fam-c when omitted.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import conformance as conformancemod  # noqa: E402
import order as ordermod  # noqa: E402

LOCK_FILENAME = "CAPABILITY_LOCK.json"

READY = "contract-conformance-READY"
INCOMPLETE = "contract-conformance-INCOMPLETE"
FAILURE = "contract-conformance-FAILURE"

WANT_BLOCKS = ("PQ", "QP")
WANT_UNIVERSES = ("A", "C")
WANT_FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))
WANT_SET = {(b, u, f) for b in WANT_BLOCKS for u in WANT_UNIVERSES
            for f in WANT_FAMILIES}

HELP = """usage: specificity.py [FAM_C_DIR]

T4-CONFORMANCE-READINESS: report whether the committed capability
contracts are conformance-ready, derived from the ORDER EXPANSION
(never from disk enumeration). This is NOT the final observed T4
specificity, which requires post-T4 lifecycle/result evidence.

Exit 0 with verdict contract-conformance-READY iff 24/24 capability
locks are present, every lock is admissible through order.cell_state,
every lock is discriminating under the live v3 conformance map, and
no stray lock dirs exist; exit 1 with verdict
contract-conformance-INCOMPLETE for a partial set (present=<n>
missing=<24-n> plus every missing tuple); exit 2 with verdict
contract-conformance-FAILURE for any inadmissible present cell
(hand-built lock, old-map lock, non-discriminating lock, symlinked
capability dir, stray lock dir, count/set mismatch).
"""


def _expected_lock_cells(fam_c_dir):
    """Derive the expected CAPABILITY_LOCK cells from ORDER.md.

    Returns (lock_cells, problems): lock_cells is the list of
    expansion cells with event == "CAPABILITY_LOCK" in expansion
    order, or None when the expansion is not exactly the frozen 24
    (fail closed — problems names the mismatch and the caller
    reports FAILURE).
    """
    try:
        with open(os.path.join(fam_c_dir, "ORDER.md"),
                  encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, [f"ORDER.md unreadable at {fam_c_dir}: {e} "
                       f"(readiness derives from the order expansion)"]
    try:
        exp = ordermod.expand(text)
    except Exception as e:  # noqa: BLE001 — fail closed, never raise
        return None, [f"ORDER expansion failed for {fam_c_dir}: "
                       f"{type(e).__name__}: {e}"]
    locks = [c for c in exp.get("cells", [])
             if c.get("event") == "CAPABILITY_LOCK"]
    got = {(c.get("block"), c.get("universe"), c.get("family"))
           for c in locks}
    if len(locks) != 24 or got != WANT_SET:
        return None, [
            f"order expansion yields {len(locks)} CAPABILITY_LOCK cells, "
            f"need exactly 24 with set "
            f"{{PQ,QP}}x{{A,C}}x{{fam01..fam06}} "
            f"(got {len(locks)}: {sorted(got)})"]
    return locks, []


def _live_conformance_map(fam_c_dir):
    """Load the live governed v3 conformance map (fail closed)."""
    try:
        return conformancemod.load(fam_c_dir), []
    except Exception as e:  # noqa: BLE001 — fail closed, never raise
        return None, [f"governed conformance map unloadable at "
                       f"{fam_c_dir}: {type(e).__name__}: {e} "
                       f"(present locks cannot bind the live map)"]


def _cell_state(fam_c_dir, cell):
    """order.cell_state() is the SOLE admissibility authority. Never
    raises: an unreadable tree reports INADMISSIBLE naming the cell."""
    try:
        st = ordermod.cell_state(fam_c_dir, cell)
        status = st.get("status")
        reasons = list(st.get("reasons") or [])
        if status not in ("COMPLETE", "INCOMPLETE", "INADMISSIBLE",
                          "NOT-PROMOTED", "NOT-EVALUABLE"):
            reasons = [f"unknown cell status {status!r}"] + reasons
            status = "INADMISSIBLE"
        return status, reasons
    except Exception as e:  # noqa: BLE001 — fail closed, never raise
        return ("INADMISSIBLE",
                [f"cell_state raised {type(e).__name__}: {e}"])


def _lock_exists(fam_c_dir, block, universe, family):
    """Whether a lock FILE exists at the governed path (lexists: a
    symlink counts as existing — it is refused as inadmissible, never
    silently skipped). Never raises."""
    try:
        return os.path.lexists(os.path.join(
            ordermod.capability_dir(fam_c_dir, block, universe, family),
            LOCK_FILENAME))
    except OSError:
        return False


def _governed_lock_verdict(fam_c_dir, block, universe, family, livemap):
    """Load one present cell's lock through the governed path and
    recompute its conformance under the LIVE v3 map. Returns
    (discriminating, problems): discriminating is True only when the
    lock binds the live map sha, its cause equals the recomputed v2
    rule cause, and the recomputed verdict is discriminating."""
    capdir = ordermod.capability_dir(fam_c_dir, block, universe, family)
    path = os.path.join(capdir, LOCK_FILENAME)
    tag = f"(block={block}, universe={universe}, family={family})"
    if os.path.islink(path):
        return False, [f"capability lock for {tag} is a symlink at "
                        f"{path} (refused; a lock must be a real file)"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except OSError as e:
        return False, [f"capability lock for {tag} unreadable at "
                        f"{path}: {e}"]
    except ValueError as e:
        return False, [f"capability lock for {tag} unparsable at "
                        f"{path}: {e}"]
    if not isinstance(lock, dict):
        return False, [f"capability lock for {tag} at {path} is not a "
                        f"JSON object"]
    live_sha = livemap["conformance_map_sha256"]
    if lock.get("conformance_map_sha256") != live_sha:
        return False, [
            f"capability lock for {tag} binds conformance map "
            f"{str(lock.get('conformance_map_sha256'))[:12]} != the live "
            f"v3 map {live_sha[:12]} (a lock minted under an old "
            f"conformance map is stale)"]
    try:
        pre = lock.get("preconditions")
        requires = [p["requires"] for p in pre]
        verdict = conformancemod.verdict(
            family, requires, livemap,
            limitations=lock.get("limitations"))
    except Exception as e:  # noqa: BLE001 — fail closed, never raise
        return False, [f"capability lock for {tag} carries no v3 "
                        f"conformance verdict ({type(e).__name__}: {e})"]
    if lock.get("conformance_cause") != verdict["conformance_cause"]:
        return False, [
            f"capability lock for {tag} cause does not match the live "
            f"v3 rule recomputation (locked "
            f"{str(lock.get('conformance_cause'))[:80]!r} != recomputed "
            f"{str(verdict['conformance_cause'])[:80]!r})"]
    if verdict["non_discriminating"]:
        return False, [
            f"non-discriminating capability lock for {tag}: "
            f"{verdict['conformance_cause']}"]
    return True, []


def _stray_capability_dirs(fam_c_dir, expected_capdirs):
    """The ONLY disk walk: capability dirs under state/ that are NOT in
    the order expansion. Returns sorted stray paths. Never raises."""
    out = []
    try:
        state_root = os.path.join(fam_c_dir, "state")
        if not os.path.isdir(state_root):
            return out
        for dirpath, dirnames, filenames in os.walk(
                state_root, followlinks=False):
            # Stray-symlink closure (A12d slice D4, auditor D3-post
            # P1): an UNEXPECTED `capability` entry that is a symlink
            # is still reported as a stray naming the exact path —
            # whether it points at a dir (walk lists it in dirnames)
            # or dangles / points at a non-dir (walk lists it in
            # filenames). Symlinked capability dirs at EXPECTED cell
            # paths stay legal (the D1-era jail / named-volume seam).
            for name in list(dirnames) + list(filenames):
                if name != "capability":
                    continue
                full = os.path.join(dirpath, name)
                if os.path.islink(full) and \
                        os.path.abspath(full) not in expected_capdirs:
                    out.append(full)
            # Never descend through a symlinked parent: only real dirs
            # below the state root are examined (no jail escape, no
            # loops; readiness content is never read through a link).
            dirnames[:] = [d for d in dirnames
                           if not os.path.islink(
                               os.path.join(dirpath, d))]
            if os.path.basename(dirpath) == "capability" and \
                    os.path.abspath(dirpath) not in expected_capdirs:
                out.append(dirpath)
    except OSError as e:
        out.append(f"<stray walk unreadable: {e}>")
    return sorted(out)


def report(fam_c_dir):
    """Run the order-derived conformance-readiness gate.

    Returns a dict with EXACTLY the keys {verdict, present, missing,
    cells, problems} (frozen contract, slice D3 B5). NEVER raises on
    a damaged tree: every refusal becomes a FAILURE verdict with a
    naming problems entry.
    """
    try:
        return _report(fam_c_dir)
    except Exception as e:  # noqa: BLE001 — the frozen never-raises rule
        return {"verdict": FAILURE, "present": 0, "missing": [],
                "cells": [],
                "problems": [f"specificity report failed: "
                             f"{type(e).__name__}: {e}"]}


def _report(fam_c_dir):
    locks, problems = _expected_lock_cells(fam_c_dir)
    if locks is None:
        return {"verdict": FAILURE, "present": 0, "missing": [],
                "cells": [], "problems": problems}
    livemap, map_problems = _live_conformance_map(fam_c_dir)
    problems.extend(map_problems)

    cells = []
    present = 0
    for cell in locks:
        block, universe, family = (cell["block"], cell["universe"],
                                   cell["family"])
        tag = (block, universe, family)
        status, reasons = _cell_state(fam_c_dir, cell)
        here = _lock_exists(fam_c_dir, block, universe, family)
        if status == "COMPLETE":
            present += 1
            if livemap is None:
                # The map failed to load: a present lock cannot bind
                # the live map (fail closed; problem already recorded).
                cells.append({"block": block, "universe": universe,
                              "family": family, "present": True,
                              "admissible": True, "discriminating": False,
                              "verdict": FAILURE})
                continue
            discriminating, lock_problems = _governed_lock_verdict(
                fam_c_dir, block, universe, family, livemap)
            problems.extend(lock_problems)
            cells.append({
                "block": block, "universe": universe, "family": family,
                "present": True, "admissible": True,
                "discriminating": discriminating,
                "verdict": READY if discriminating else FAILURE})
        elif here or status == "INADMISSIBLE":
            # A lock file exists but the cell is not COMPLETE
            # (hand-built lock, stale-map lock, symlinked parent,
            # unparsable bytes), or the artifacts exist but fail
            # validation: inadmissible, never silently skipped.
            detail = "; ".join(reasons[:2]) if reasons else status
            lock_path = os.path.join(ordermod.capability_dir(
                fam_c_dir, block, universe, family), LOCK_FILENAME)
            try:
                link_note = ("symlink refused; " if os.path.islink(lock_path)
                             else "")
            except OSError:
                link_note = ""
            problems.append(
                f"inadmissible capability lock for "
                f"(block={block}, universe={universe}, family={family}): "
                f"cell_state={status} ({detail}) while a lock file "
                f"exists at {lock_path} ({link_note}refused, never "
                f"silently skipped)" if here else
                f"inadmissible capability lock for "
                f"(block={block}, universe={universe}, family={family}): "
                f"cell_state={status} ({detail})")
            cells.append({"block": block, "universe": universe,
                          "family": family, "present": False,
                          "admissible": False, "discriminating": False,
                          "verdict": FAILURE})
        else:
            cells.append({"block": block, "universe": universe,
                          "family": family, "present": False,
                          "admissible": False, "discriminating": False,
                          "verdict": INCOMPLETE})

    expected_capdirs = {os.path.abspath(ordermod.capability_dir(
        fam_c_dir, c["block"], c["universe"], c["family"]))
        for c in locks}
    for stray in _stray_capability_dirs(fam_c_dir, expected_capdirs):
        problems.append(f"stray capability dir outside the order "
                        f"expansion: {stray}")

    missing = sorted([[c["block"], c["universe"], c["family"]]
                      for c in cells if not c["present"]])
    if problems:
        verdict = FAILURE
    elif present == 24:
        verdict = READY
    else:
        verdict = INCOMPLETE
        for triple in missing:
            problems.append(
                f"missing capability lock for (block={triple[0]}, "
                f"universe={triple[1]}, family={triple[2]})")
    return {"verdict": verdict, "present": present, "missing": missing,
            "cells": cells, "problems": problems}


def main(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    default = os.path.join(os.path.dirname(HERE), "benchmarks", "fam-c")
    fam_c_dir = argv[1] if len(argv) > 1 else default
    rep = report(fam_c_dir)
    for c in rep["cells"]:
        sys.stdout.write(
            f"(block, universe, family)=({c['block']}, {c['universe']}, "
            f"{c['family']}) present={c['present']} "
            f"admissible={c['admissible']} "
            f"discriminating={c['discriminating']} verdict={c['verdict']}\n")
    sys.stdout.write(f"{rep['verdict']} present={rep['present']} "
                     f"missing={len(rep['missing'])}\n")
    sys.stdout.write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    return (0 if rep["verdict"] == READY
            else 1 if rep["verdict"] == INCOMPLETE else 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

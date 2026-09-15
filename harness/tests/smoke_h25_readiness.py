#!/usr/bin/env python3
"""H25 — A12d slice D3 acceptance: order-derived readiness (auditor
A12d.6).

Readiness is DERIVED from the order expansion (never from disk
enumeration): exactly 24 CAPABILITY_LOCK cells {PQ,QP} x {A,C} x
{fam01..fam06}, present ONLY via order.cell_state() == "COMPLETE"
(the sole admissibility authority), each present lock bound to the
live v4 conformance map sha with the v4 rule cause, and no stray
capability dir outside the expansion. Verdicts: READY (exit 0) iff
24/24 present, admissible, discriminating, no strays; INCOMPLETE
(exit 1) for a partial set with every missing tuple listed; FAILURE
(exit 2) for any inadmissible present cell. Acceptance, every case
through the SEALED fixture path (no live model calls):

  1 real promotion  -> INCOMPLETE, missing 23, the 23 tuples listed;
  23 real promotions -> INCOMPLETE, missing 1 (the right tuple);
  24 real promotions -> READY (exit 0);
  24 real + 1 non-discriminating lock -> FAILURE (exit 2), naming
      that tuple;
  hand-built lock (no promotion receipt) -> FAILURE;
  lock minted under the v1 conformance map -> FAILURE;
  capability dir reached through a symlinked parent -> FAILURE
      (must not be counted as present);
  a stray capability dir outside the expansion -> FAILURE;
  live tree (read-only) -> INCOMPLETE present=0 missing=24, exit 1.

Stdlib only. Hermetic fixtures live in throwaway dirs under /tmp (no
live-tree mutation); live-tree reads are read-only. Prints
`H25 readiness smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)

import order  # noqa: E402
import promotion  # noqa: E402
import specificity as SPEC  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = "import sys; sys.exit(0)\n"
ADAPTER = "import sys; sys.exit(0)\n"
SPEC_CLI = os.path.join(HARNESS, "specificity.py")
V1_MAP_SHA = "05a8e094e437f320ed7e9521b483dd98f1febf0f31851992125ccb2f95dbda40"
# Discriminating producer declarations (each requires_all token list
# matches a frozen v4 predicate for its own family only).
CONTRACT = {
    "fam01": {"requires_all": ["summary", "row"]},
    "fam02": {"requires_all": ["pages", "disjoint"]},
    "fam03": {"requires_all": ["identical", "repeats"]},
    "fam04": {"requires_all": ["acyclic"]},
    "fam05": {"requires_all": ["local", "sha256"]},
    "fam06": {"requires_all": ["common", "unit"]},
}
FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def hermetic():
    root = tempfile.mkdtemp(prefix="h25-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md",
                 "ORDER.md", "STAGED.md", "FAMILIES.md", "LANES.md",
                 "HARNESS-READINESS.md"):
        src = os.path.join(FAMC, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for family in FAMILIES:
        shutil.copytree(os.path.join(FAMC, "families", family),
                        os.path.join(fam, family))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def walk(root, upto=None, nd_cell=None):
    """Mint expansion cells in order through the sealed fixture path
    (fixture T0/T1 builds -> promotion controller -> locks). `upto` =
    inclusive cell index cap (None = whole expansion). `nd_cell` =
    (block, universe, family) whose T0 contract carries empty
    preconditions (a real but non-discriminating lock)."""
    exp = order.load_expansion(root)
    cells = exp["cells"] if upto is None else exp["cells"][:upto + 1]
    t0sha = {}
    for c in cells:
        b, u, fam, ev = c["block"], c["universe"], c["family"], c["event"]
        if ev == "PROMOTION":
            promotion.promote_universe(root, b, fam, u, FREEZE,
                                       "harness-validation")
        elif ev == "CAPABILITY_LOCK":
            promotion.advance(root, b, fam, u, FREEZE,
                              "harness-validation")
        elif ev == "T1":
            build_model_run(root, cell=c, freeze_commit=FREEZE,
                            solver_py=SOLVER,
                            validates_candidate=t0sha[(b, u, fam)],
                            adapter_py=ADAPTER,
                            candidate_validation={
                                "checker_sha256": _sha_file(os.path.join(
                                    root, "families", fam, "check.py")),
                                "truth_sha256": _sha_file(os.path.join(
                                    root, "families", fam, "truth.json")),
                                "checker_returncode": 0,
                                "validation_verdict": "ship",
                                "validated": True})
        else:
            pre = [] if nd_cell == (b, u, fam) else [CONTRACT[fam]]
            d = build_model_run(
                root, cell=c, freeze_commit=FREEZE, solver_py=SOLVER,
                producer_contract={"semantic_core": "generic capability",
                                   "preconditions": pre,
                                   "limitations": []})
            if ev == "T0":
                t0sha[(b, u, fam)] = t0_candidate_sha256(d)
    return exp


def capdir(root, block, universe, family):
    return os.path.join(root, "state", block, universe, family,
                        "capability")


def run_cli(root):
    p = subprocess.run([sys.executable, SPEC_CLI, root],
                       capture_output=True, text=True, timeout=300)
    return p


def lock_cells(exp):
    return [(c["block"], c["universe"], c["family"]) for c in exp["cells"]
            if c["event"] == "CAPABILITY_LOCK"]


# --- 1 real promotion -> INCOMPLETE, missing 23 listed -----------------
r1 = hermetic()
e1 = walk(r1, upto=3)
rep1 = SPEC.report(r1)
check("1 lock -> contract-conformance-INCOMPLETE",
      rep1["verdict"] == "contract-conformance-INCOMPLETE",
      rep1["verdict"])
check("present=1 missing=23 with all 23 tuples listed sorted",
      rep1["present"] == 1 and len(rep1["missing"]) == 23
      and rep1["missing"] == sorted(rep1["missing"])
      and ["PQ", "A", "fam05"] not in rep1["missing"],
      f"present={rep1['present']} missing={len(rep1.get('missing', []))}")
cli1 = run_cli(r1)
check("CLI exits 1 with the INCOMPLETE summary line",
      cli1.returncode == 1
      and "contract-conformance-INCOMPLETE present=1 missing=23"
      in cli1.stdout,
      f"rc={cli1.returncode}")

# --- 23 real promotions -> INCOMPLETE, missing 1 (the right tuple) -----
r23 = hermetic()
e23 = order.load_expansion(r23)
_lock_idx = [i for i, cl in enumerate(e23["cells"])
             if cl["event"] == "CAPABILITY_LOCK"]
walk(r23, upto=_lock_idx[-1] - 1)
rep23 = SPEC.report(r23)
_last = e23["cells"][_lock_idx[-1]]
check("23 locks -> contract-conformance-INCOMPLETE",
      rep23["verdict"] == "contract-conformance-INCOMPLETE",
      rep23["verdict"])
check("present=23 missing=1: exactly the final expansion tuple",
      rep23["present"] == 23
      and rep23["missing"] == [[_last["block"], _last["universe"],
                                _last["family"]]],
      f"present={rep23['present']} missing={rep23['missing']}")
cli23 = run_cli(r23)
check("CLI exits 1 with the 23/1 summary line",
      cli23.returncode == 1
      and "contract-conformance-INCOMPLETE present=23 missing=1"
      in cli23.stdout,
      f"rc={cli23.returncode}")

# --- 24 real promotions -> READY (exit 0) ------------------------------
r24 = hermetic()
walk(r24)
rep24 = SPEC.report(r24)
check("24 locks -> contract-conformance-READY",
      rep24["verdict"] == "contract-conformance-READY"
      and rep24["present"] == 24 and rep24["missing"] == []
      and rep24["problems"] == [],
      f"verdict={rep24['verdict']} present={rep24['present']} "
      f"problems={str(rep24.get('problems'))[:120]}")
check("all 24 per-cell rows are present/admissible/discriminating",
      len(rep24["cells"]) == 24
      and all(x["present"] and x["admissible"] and x["discriminating"]
              and x["verdict"] == "contract-conformance-READY"
              for x in rep24["cells"]))
cli24 = run_cli(r24)
check("CLI exits 0 with the READY summary line",
      cli24.returncode == 0
      and "contract-conformance-READY present=24 missing=0"
      in cli24.stdout,
      f"rc={cli24.returncode} {cli24.stderr[:120]}")

# --- 24 real + 1 non-discriminating -> FAILURE naming the tuple --------
rnd = hermetic()
walk(rnd, nd_cell=("QP", "C", "fam02"))
repnd = SPEC.report(rnd)
check("24 + non-discriminating -> contract-conformance-FAILURE",
      repnd["verdict"] == "contract-conformance-FAILURE",
      repnd["verdict"])
check("FAILURE names the non-discriminating tuple",
      any("QP" in str(p) and "fam02" in str(p)
          for p in repnd["problems"]),
      str(repnd["problems"])[:200])
clind = run_cli(rnd)
check("CLI exits 2 on the non-discriminating root",
      clind.returncode == 2, f"rc={clind.returncode}")

# --- hand-built lock (no promotion receipt) -> FAILURE -----------------
rhb = hermetic()
walk(rhb, upto=3)
_d = capdir(rhb, "PQ", "A", "fam03")
os.makedirs(_d, exist_ok=True)
_src = capdir(r1, "PQ", "A", "fam05")
for _n in ("engine.py", "manifest.json", "adapter_notes.md",
           "CAPABILITY_LOCK.json"):
    if os.path.isfile(os.path.join(_src, _n)):
        shutil.copy2(os.path.join(_src, _n), os.path.join(_d, _n))
rephb = SPEC.report(rhb)
check("hand-built lock -> FAILURE naming the tuple",
      rephb["verdict"] == "contract-conformance-FAILURE"
      and any("fam03" in str(p) for p in rephb["problems"]),
      f"verdict={rephb['verdict']} "
      f"problems={str(rephb['problems'])[:160]}")

# --- lock minted under the v1 conformance map -> FAILURE ---------------
rold = hermetic()
walk(rold, upto=7)
_lp = os.path.join(capdir(rold, "PQ", "A", "fam05"),
                   "CAPABILITY_LOCK.json")
_lock = json.load(open(_lp))
_lock["conformance_map_sha256"] = V1_MAP_SHA
json.dump(_lock, open(_lp, "w"), indent=1, sort_keys=True)
repold = SPEC.report(rold)
check("old-map (v1-sha) lock -> FAILURE",
      repold["verdict"] == "contract-conformance-FAILURE",
      f"verdict={repold['verdict']} "
      f"problems={str(repold['problems'])[:160]}")

# --- symlinked parent -> FAILURE, not counted present ------------------
rsym = hermetic()
walk(rsym, upto=7)
_link = os.path.join(rsym, "state", "PQ", "A", "fam05")
os.rename(_link, _link + ".real")
os.symlink(os.path.join(rsym, "state", "PQ", "C"), _link)
repsy = SPEC.report(rsym)
_names = [(x["block"], x["universe"], x["family"])
          for x in (repsy.get("cells") or []) if x.get("present")]
check("symlinked parent -> FAILURE, tuple not counted present",
      repsy["verdict"] == "contract-conformance-FAILURE"
      and ("PQ", "A", "fam05") not in _names,
      f"verdict={repsy['verdict']} present={repsy['present']} "
      f"problems={str(repsy['problems'])[:160]}")

# --- stray capability dir outside the expansion -> FAILURE -------------
rst = hermetic()
walk(rst, upto=7)
_stray = capdir(rst, "QP", "C", "fam07")
os.makedirs(_stray)
json.dump({"stray": True},
          open(os.path.join(_stray, "manifest.json"), "w"))
repst = SPEC.report(rst)
check("stray capability dir -> FAILURE naming the path",
      repst["verdict"] == "contract-conformance-FAILURE"
      and any("fam07" in str(p) for p in repst["problems"]),
      f"verdict={repst['verdict']} "
      f"problems={str(repst['problems'])[:160]}")

# --- report() contract + live tree (read-only) -------------------------
check("report() key set is exactly the frozen B5 set",
      set(rep24) == {"verdict", "present", "missing", "cells",
                     "problems"},
      sorted(rep24))
check("per-cell rows carry exactly the frozen B5 keys in expansion "
      "lock order",
      [(x["block"], x["universe"], x["family"]) for x in rep24["cells"]]
      == lock_cells(e1)
      and all(set(x) == {"block", "universe", "family", "present",
                         "admissible", "discriminating", "verdict"}
              for x in rep24["cells"]))
_live = subprocess.run([sys.executable, SPEC_CLI],
                       capture_output=True, text=True, timeout=300)
check("live tree CLI (read-only) -> INCOMPLETE present=0 missing=24, "
      "exit 1",
      _live.returncode == 1
      and "contract-conformance-INCOMPLETE present=0 missing=24"
      in _live.stdout,
      f"rc={_live.returncode}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH25 readiness smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

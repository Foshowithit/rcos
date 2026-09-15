#!/usr/bin/env python3
"""H18 — specificity production-caller smoke (RCOS A12b slice 3; A12c
C1-3 reframe: the surface is T4-CONFORMANCE-READINESS; A12d slice D3 /
auditor A12d.6 reframe: readiness is DERIVED from the ORDER EXPANSION
with verdicts contract-conformance-READY / contract-conformance-
INCOMPLETE / contract-conformance-FAILURE).

`harness/specificity.py` is the production caller: it reads
<fam_c_dir>/ORDER.md, expands it via order.expand, treats each of the
exactly 24 CAPABILITY_LOCK cells as present ONLY when
order.cell_state() says COMPLETE (the sole admissibility authority),
recomputes each present lock's conformance under the live v4 map, and
refuses stray capability dirs. This suite proves, on hermetic roots
built through the REAL fixture writer + production promotion
controller:

  (a) 1 real promotion -> INCOMPLETE present=1 missing=23, the 23
      tuples listed sorted, 24 B5-exact per-cell rows, CLI exit 1
      with the machine-readable summary line;
  (b) 24 real promotions -> READY (exit 0), problems empty, every
      per-cell row READY;
  (c) 24 real + 1 non-discriminating lock -> FAILURE (exit 2),
      naming that tuple;
  (d) empty lock set -> INCOMPLETE present=0 missing=24 (exit 1),
      never a vacuous pass and never a silent READY;
  (e) hand-built lock (no promotion receipt) -> FAILURE;
  (f) lock minted under the v1 conformance map -> FAILURE;
  (g) capability dir reached through a symlinked parent -> FAILURE
      (not counted as present);
  (h) stray capability dir outside the expansion -> FAILURE naming
      the path;
  (i) unparsable lock JSON -> FAILURE, report() never raises;
  (j) source guards: the production-caller discipline (order-derived
      presence, governed-path lock reads, live-map binding, stray as
      the only disk walk, frozen verdict literals and exit codes).

Stdlib only. Hermetic fixtures live in throwaway dirs under /tmp (no
live-tree mutation); live-tree reads are read-only. Prints
`H18 specificity smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
import json
import os
import re as _re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

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
# Discriminating producer declarations: each requires_all token list
# matches a frozen v4 predicate for its own family (and no other
# family's), so a fully promoted universe is READY.
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
    root = tempfile.mkdtemp(prefix="h18-")
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
    """Mint expansion cells in order through the sealed fixture path:
    T0/T1 fresh runs, PROMOTION + CAPABILITY_LOCK governance events.
    `upto` = inclusive cell index cap (None = whole expansion).
    `nd_cell` = (block, universe, family) whose T0 contract carries
    empty preconditions (a real but non-discriminating lock)."""
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


def expected_locks(root):
    exp = order.load_expansion(root)
    return [(c["block"], c["universe"], c["family"]) for c in exp["cells"]
            if c["event"] == "CAPABILITY_LOCK"]


# --- (a) one real promotion -> INCOMPLETE present=1 missing=23 --------
root_a = hermetic()
walk(root_a, upto=3)
rep_a = SPEC.report(root_a)
check("1 real promotion -> contract-conformance-INCOMPLETE",
      rep_a["verdict"] == "contract-conformance-INCOMPLETE",
      rep_a["verdict"])
check("present=1 missing=23 with every missing tuple listed sorted",
      rep_a["present"] == 1 and len(rep_a["missing"]) == 23
      and rep_a["missing"] == sorted(rep_a["missing"])
      and ["PQ", "A", "fam05"] not in rep_a["missing"]
      and len({tuple(t) for t in rep_a["missing"]}) == 23,
      f"present={rep_a['present']} missing={len(rep_a.get('missing', []))}")
check("report() key set is exactly the frozen B5 set",
      set(rep_a) == {"verdict", "present", "missing", "cells",
                     "problems"},
      sorted(rep_a))
check("cells = 24 per-cell rows in expansion lock order with the "
      "frozen per-cell keys",
      len(rep_a["cells"]) == 24
      and [(x["block"], x["universe"], x["family"])
           for x in rep_a["cells"]] == expected_locks(root_a)
      and all(set(x) == {"block", "universe", "family", "present",
                         "admissible", "discriminating", "verdict"}
              for x in rep_a["cells"]),
      f"rows={len(rep_a.get('cells', []))}")
check("the one present row is admissible",
      sum(1 for x in rep_a["cells"] if x["present"]) == 1
      and all(x["admissible"] for x in rep_a["cells"] if x["present"]))
cli_a = run_cli(root_a)
check("CLI exits 1 on the partial root", cli_a.returncode == 1,
      f"rc={cli_a.returncode}")
check("CLI prints the machine-readable INCOMPLETE summary line",
      "contract-conformance-INCOMPLETE present=1 missing=23"
      in cli_a.stdout)

# --- (b) 24 real promotions -> READY -----------------------------------
root_b = hermetic()
walk(root_b)
rep_b = SPEC.report(root_b)
check("24 real promotions -> contract-conformance-READY",
      rep_b["verdict"] == "contract-conformance-READY", rep_b["verdict"])
check("READY has present=24, no missing, empty problems",
      rep_b["present"] == 24 and rep_b["missing"] == []
      and rep_b["problems"] == [],
      f"present={rep_b['present']} problems={rep_b['problems'][:1]}")
check("every per-cell row is present/admissible/discriminating/READY",
      all(x["present"] and x["admissible"] and x["discriminating"]
          and x["verdict"] == "contract-conformance-READY"
          for x in rep_b["cells"]),
      str(rep_b["cells"][:1]))
cli_b = run_cli(root_b)
check("CLI exits 0 on the READY root", cli_b.returncode == 0,
      f"rc={cli_b.returncode} {cli_b.stderr[:120]}")
check("CLI prints the READY summary line",
      "contract-conformance-READY present=24 missing=0" in cli_b.stdout)

# --- (c) 24 real + 1 non-discriminating lock -> FAILURE ----------------
root_c = hermetic()
walk(root_c, nd_cell=("PQ", "A", "fam05"))
rep_c = SPEC.report(root_c)
check("24 + non-discriminating -> contract-conformance-FAILURE",
      rep_c["verdict"] == "contract-conformance-FAILURE",
      rep_c["verdict"])
check("FAILURE names the non-discriminating tuple",
      any("fam05" in str(p) for p in rep_c["problems"]),
      str(rep_c["problems"])[:160])
cli_c = run_cli(root_c)
check("CLI exits 2 on the non-discriminating root",
      cli_c.returncode == 2, f"rc={cli_c.returncode}")

# --- (d) empty lock set -> INCOMPLETE, never a vacuous pass ------------
root_d = hermetic()
rep_d = SPEC.report(root_d)
check("empty lock set -> contract-conformance-INCOMPLETE (anti-vacuity)",
      rep_d["verdict"] == "contract-conformance-INCOMPLETE"
      and rep_d["present"] == 0 and len(rep_d["missing"]) == 24,
      str(rep_d))
check("empty root lists all 24 missing tuples sorted",
      rep_d["missing"] == sorted(rep_d["missing"])
      and len({tuple(t) for t in rep_d["missing"]}) == 24)
cli_d = run_cli(root_d)
check("CLI exits 1 (never 0) on an empty lock set",
      cli_d.returncode == 1, f"rc={cli_d.returncode}")
check("CLI prints the empty summary line",
      "contract-conformance-INCOMPLETE present=0 missing=24"
      in cli_d.stdout)

# --- (e) hand-built lock (no promotion receipt) -> FAILURE -------------
root_e = hermetic()
walk(root_e, upto=3)
_d = capdir(root_e, "PQ", "A", "fam03")
os.makedirs(_d, exist_ok=True)
_src = capdir(root_b, "PQ", "A", "fam05")
for _n in ("engine.py", "manifest.json", "adapter_notes.md",
           "CAPABILITY_LOCK.json"):
    if os.path.isfile(os.path.join(_src, _n)):
        shutil.copy2(os.path.join(_src, _n), os.path.join(_d, _n))
rep_e = SPEC.report(root_e)
check("hand-built lock -> contract-conformance-FAILURE naming it",
      rep_e["verdict"] == "contract-conformance-FAILURE"
      and any("fam03" in str(p) for p in rep_e["problems"]),
      f"verdict={rep_e['verdict']} "
      f"problems={str(rep_e['problems'])[:160]}")

# --- (f) lock minted under the v1 conformance map -> FAILURE -----------
root_f = hermetic()
walk(root_f, upto=7)
_lp = os.path.join(capdir(root_f, "PQ", "A", "fam05"),
                   "CAPABILITY_LOCK.json")
_lock = json.load(open(_lp))
_lock["conformance_map_sha256"] = V1_MAP_SHA
json.dump(_lock, open(_lp, "w"), indent=1, sort_keys=True)
rep_f = SPEC.report(root_f)
check("old-map (v1-sha) lock -> contract-conformance-FAILURE",
      rep_f["verdict"] == "contract-conformance-FAILURE",
      f"verdict={rep_f['verdict']} "
      f"problems={str(rep_f['problems'])[:160]}")

# --- (g) symlinked parent -> FAILURE, not counted present --------------
root_g = hermetic()
walk(root_g, upto=7)
_target = os.path.join(root_g, "state", "PQ", "C", "fam05")
_link = os.path.join(root_g, "state", "PQ", "A", "fam05")
os.rename(_link, _link + ".real")
os.symlink(os.path.join(root_g, "state", "PQ", "C"), _link)
rep_g = SPEC.report(root_g)
_names_g = [(x["block"], x["universe"], x["family"])
            for x in (rep_g.get("cells") or []) if x.get("present")]
check("symlinked capability dir -> FAILURE, not counted present",
      rep_g["verdict"] == "contract-conformance-FAILURE"
      and ("PQ", "A", "fam05") not in _names_g,
      f"verdict={rep_g['verdict']} present={rep_g['present']} "
      f"problems={str(rep_g['problems'])[:160]}")

# --- (h) stray capability dir outside the expansion -> FAILURE ---------
root_h = hermetic()
walk(root_h, upto=7)
_stray = capdir(root_h, "QP", "C", "fam07")
os.makedirs(_stray)
json.dump({"stray": True},
          open(os.path.join(_stray, "manifest.json"), "w"))
rep_h = SPEC.report(root_h)
check("stray capability dir -> FAILURE naming it",
      rep_h["verdict"] == "contract-conformance-FAILURE"
      and any("fam07" in str(p) for p in rep_h["problems"]),
      f"verdict={rep_h['verdict']} "
      f"problems={str(rep_h['problems'])[:160]}")

# --- (i) unparsable lock JSON never raises; report() FAILURE -----------
root_i = hermetic()
walk(root_i, upto=7)
_lpi = os.path.join(capdir(root_i, "PQ", "A", "fam05"),
                    "CAPABILITY_LOCK.json")
open(_lpi, "w").write("{not json")
try:
    rep_i = SPEC.report(root_i)
    _raised = False
except Exception as e:  # noqa: BLE001
    _raised = True
    rep_i = {"verdict": f"RAISED {type(e).__name__}"}
check("unparsable lock JSON -> FAILURE (never raises)",
      not _raised and rep_i.get("verdict")
      == "contract-conformance-FAILURE",
      f"verdict={rep_i.get('verdict')}")

# --- (j) source guards: order-derived production-caller discipline ------
_src = open(SPEC_CLI, encoding="utf-8").read()
check("specificity.py names the A15 readiness consumer (§24/estimand)",
      "A15" in _src and "estimand" in _src
      and "readiness gate" in _src)
check("specificity.py derives readiness from order.expand(ORDER.md)",
      "order.expand" in _src or "expand(" in _src
      and "ORDER.md" in _src)
check("specificity.py uses order.cell_state as the sole "
      "admissibility authority",
      "cell_state" in _src and "SOLE admissibility authority" in _src)
check("specificity.py binds present locks to the live v4 map via "
      "conformance.verdict",
      "conformance.verdict" in _src and "conformance_map_sha256" in _src)
check("specificity.py walks disk ONLY for stray capability dirs",
      "stray" in _src and "ONLY disk walk" in _src)
check("specificity.py freezes the three verdict literals",
      "contract-conformance-READY" in _src
      and "contract-conformance-INCOMPLETE" in _src
      and "contract-conformance-FAILURE" in _src)
check("specificity.py has no hidden-contract reader (no K.md open)",
      _re.search(r"open\([^)]*K\.md", _src) is None)
check("specificity.py names the surface T4-CONFORMANCE-READINESS",
      "T4-CONFORMANCE-READINESS" in _src)
check("specificity.py disclaims final observed T4 specificity",
      "NOT the final" in _src and "post-T4 lifecycle" in _src)
check("specificity.py documents exit codes 0/1/2 in its docstring",
      "exit 0" in _src and "exit 1" in _src and "exit 2" in _src)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH18 specificity smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

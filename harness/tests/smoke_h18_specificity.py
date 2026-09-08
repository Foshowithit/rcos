#!/usr/bin/env python3
"""H18 — specificity production-caller smoke (RCOS A12b slice 3).

`lock.specificity_gate` was previously called only from H17 with
hand-built dicts. `harness/specificity.py` is the production caller:
it discovers COMMITTED locks from production capability dirs and runs
the gate over them. This suite proves, on hermetic roots built through
the REAL fixture writer + production promotion controller:

  (a) the real committed fam05 lock (minted through promotion) ->
      fam05 in non_discriminating with a non-empty cause, verdict
      specificity-failure, CLI exit 1, cause on stderr;
  (b) a lock variant with a real limitation (limitations non-empty,
      limitation_present True, non_discriminating False, cause text)
      that still passes verify_lock -> verdict specificity-pass,
      CLI exit 0;
  (c) an inadmissible lock (discrimination claimed with empty
      limitations) -> specificity-failure with the LOCK-INADMISSIBLE
      reason;
  (d) empty lock set -> specificity-failure, never a vacuous pass;
  (e) discovery is from disk, not caller input: the discovered family
      set equals the families with committed locks under the root.

Stdlib only. Hermetic fixtures live in throwaway dirs under /tmp (no
live-tree mutation); live-tree reads are read-only. Existing suites
and harness/tests/fixture_modelrun.py are untouched.
"""
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

import lock as LOCK_MOD  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import specificity as SPEC  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []

FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")
SPEC_CLI = os.path.join(HARNESS, "specificity.py")
LIMITATION_APPEND = ("\nLIMITATIONS (H18 fixture producer declaration):\n"
                     "- Synthetic H18 limitation: payloads larger than "
                     "1 MiB are rejected.\n")


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def hermetic(k_append=""):
    root = tempfile.mkdtemp(prefix="h18-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                    os.path.join(fam, "fam05"))
    if k_append:
        with open(os.path.join(fam, "fam05", "K.md"), "a") as f:
            f.write(k_append)
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def mint_fam05(root):
    """Acquire T0/T1 through the production fixture writer, promote
    through the production controller, and lock. Returns the lock dict
    read back from the committed capability dir (never hand-built)."""
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                            evidence_grade="harness-validation")
    res2 = promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                             evidence_grade="harness-validation")
    capdir = order.capability_dir(root, "PQ", "A", "fam05")
    lock = json.load(open(os.path.join(capdir, "CAPABILITY_LOCK.json")))
    return res, res2, capdir, lock


def disk_lock_families(root):
    """Independent disk truth: families with a committed CAPABILITY_LOCK
    under the root's production state tree (no specificity import)."""
    out = set()
    state = os.path.join(root, "state")
    if not os.path.isdir(state):
        return out
    for dirpath, _ds, files in os.walk(state):
        if "CAPABILITY_LOCK.json" not in files:
            continue
        rel = os.path.relpath(dirpath, state)
        parts = rel.split(os.sep)
        if (len(parts) == 4 and parts[3] == "capability"
                and all(parts[:3])):
            out.add(parts[2])
    return out


def run_cli(root):
    p = subprocess.run([sys.executable, SPEC_CLI, root],
                       capture_output=True, text=True, timeout=120)
    return p


# --- (a) the real committed fam05 lock --------------------------------
root_a = hermetic()
res_a, res2_a, cap_a, lock_a = mint_fam05(root_a)
check("real fam05 pair promotes then locks (not vacuous)",
      res_a.get("event") == "PROMOTION"
      and res2_a.get("event") == "CAPABILITY_LOCK",
      f"{res_a.get('event')} -> {res2_a.get('event')}")
rep_a = SPEC.report(root_a)
check("real fam05 lock -> specificity-failure",
      rep_a["verdict"] == "specificity-failure", rep_a["verdict"])
check("fam05 in non_discriminating with a non-empty cause",
      isinstance(rep_a["non_discriminating"].get("fam05"), str)
      and bool(rep_a["non_discriminating"]["fam05"].strip()),
      str(rep_a["non_discriminating"].get("fam05"))[:120])
check("committed cause names the frozen fam05 T4 id",
      "fam05.local_v1_sha256" in
      (rep_a["non_discriminating"].get("fam05") or ""))
check("no discriminating families, no inadmissible locks",
      rep_a["discriminating"] == [] and rep_a["inadmissible"] == {},
      str({k: rep_a[k] for k in ("discriminating", "inadmissible")}))
check("discovered family set is exactly {fam05}",
      set(SPEC.discover_locks(root_a)) == {"fam05"})
cli_a = run_cli(root_a)
check("CLI exits 1 on the non-discriminating root", cli_a.returncode == 1,
      f"rc={cli_a.returncode}")
check("CLI prints the cause on stderr",
      "SPECIFICITY-FAILURE:" in cli_a.stderr
      and "non-discriminating" in cli_a.stderr,
      cli_a.stderr[:160])
check("CLI stdout carries the JSON failure verdict",
      '"verdict": "specificity-failure"' in cli_a.stdout)

# --- (b) lock variant with a real limitation ---------------------------
root_b = hermetic(LIMITATION_APPEND)
res_b, res2_b, cap_b, lock_b = mint_fam05(root_b)
check("limitation variant promotes then locks (not vacuous)",
      res_b.get("event") == "PROMOTION"
      and res2_b.get("event") == "CAPABILITY_LOCK")
check("variant lock carries a real limitation and passes verify_lock",
      isinstance(lock_b.get("limitations"), list)
      and len(lock_b["limitations"]) == 1
      and lock_b.get("limitation_present") is True
      and lock_b.get("non_discriminating") is False
      and isinstance(lock_b.get("conformance_cause"), str)
      and bool(lock_b["conformance_cause"].strip())
      and LOCK_MOD.verify_lock(lock_b) == [],
      str(LOCK_MOD.verify_lock(lock_b)[:1]))
rep_b = SPEC.report(root_b)
check("real limitation -> specificity-pass, fam05 discriminating",
      rep_b["verdict"] == "specificity-pass"
      and rep_b["discriminating"] == ["fam05"]
      and rep_b["non_discriminating"] == {}
      and rep_b["inadmissible"] == {}, str(rep_b))
cli_b = run_cli(root_b)
check("CLI exits 0 on the discriminating root", cli_b.returncode == 0,
      f"rc={cli_b.returncode} {cli_b.stderr[:120]}")

# --- (c) inadmissible lock: discrimination claimed, no limitation ------
root_c = hermetic()
mint_fam05(root_c)
lock_c_path = os.path.join(
    order.capability_dir(root_c, "PQ", "A", "fam05"), "CAPABILITY_LOCK.json")
mutated = json.load(open(lock_c_path))
mutated["non_discriminating"] = False
json.dump(mutated, open(lock_c_path, "w"), indent=1)
rep_c = SPEC.report(root_c)
check("discrimination claim without a limitation -> specificity-failure",
      rep_c["verdict"] == "specificity-failure", rep_c["verdict"])
bad_reasons = rep_c["inadmissible"].get("fam05") or []
check("inadmissible lists fam05 with the LOCK-INADMISSIBLE reason",
      any("LOCK-INADMISSIBLE" in r and "no limitations" in r
          for r in bad_reasons), "; ".join(bad_reasons)[:160])
cli_c = run_cli(root_c)
check("CLI exits 1 on the inadmissible root", cli_c.returncode == 1,
      f"rc={cli_c.returncode}")

# --- (d) empty lock set is a failure, never a vacuous pass ------------
root_d = hermetic()
rep_d = SPEC.report(root_d)
check("empty lock set -> specificity-failure (anti-vacuity)",
      rep_d["verdict"] == "specificity-failure"
      and rep_d["families"] == []
      and rep_d["discriminating"] == [], str(rep_d))
check("empty report carries the committed no-locks cause",
      rep_d.get("cause") == "no committed capability locks",
      str(rep_d.get("cause")))
cli_d = run_cli(root_d)
check("CLI never exits 0 on an empty lock set",
      cli_d.returncode == 1, f"rc={cli_d.returncode}")
check("CLI prints the no-locks cause on stderr",
      "no committed capability locks" in cli_d.stderr,
      cli_d.stderr[:120])

# --- (e) discovery is from disk, not caller input ----------------------
check("discovery == disk lock families on root A (from disk)",
      set(SPEC.discover_locks(root_a)) == disk_lock_families(root_a) ==
      {"fam05"})
check("discovery == disk lock families on root B (from disk)",
      set(SPEC.discover_locks(root_b)) == disk_lock_families(root_b) ==
      {"fam05"})
check("discovery == disk lock families on empty root D (from disk)",
      set(SPEC.discover_locks(root_d)) == disk_lock_families(root_d) ==
      set())

# --- source guards: production caller discipline -----------------------
_src = open(SPEC_CLI, encoding="utf-8").read()
check("specificity.py names the A15 readiness consumer (§24/estimand)",
      "A15" in _src and "estimand" in _src
      and "readiness gate" in _src)
check("specificity.py delegates to lock.specificity_gate",
      "specificity_gate" in _src)
check("specificity.py derives capability dirs via the order API",
      "capability_dir" in _src)
check("specificity.py has no hidden-contract reader (no K.md open)",
      _re.search(r"open\([^)]*K\.md", _src) is None)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH18 specificity smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

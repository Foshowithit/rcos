#!/usr/bin/env python3
"""H19 — A12c slice A: T1 candidate OUTPUT evaluated with the frozen host
checker + T1 adapter actually fed to the candidate (auditor P0 #1 + P0 #2).

Frozen design (implement exactly, do not redesign):
  D1  T1 producer instruction gains required `adapter_py`
      (ABI python3 adapter.py <task_dir> <out_input_dir>).
  D2  T1 candidate validation path, in order, in-jail: adapter.py ->
      adapter rc -> frozen candidate.py (sha-verified) -> candidate rc ->
      HOST-SIDE frozen T1 checker over CANDIDATE-OUTPUT.json -> validated
      five-way conjunction -> exactly one nine-key chain event. Any failure
      raises CANDIDATE-VALIDATION-FAIL before any chain is wired.
  D3  promotion.derive_candidate fail-closed nine-field predicate +
      order.py provenance re-derivation from the committed chain.
  D4  adapter_sha256 is the sha256 of the exact executed adapter bytes.

Acceptance negatives (each proven by a REAL test — real subprocess, real
frozen fam05 T1 checker + truth, real promotion controller; not a claim):
  N1  candidate writes valid-but-WRONG output, exits 0 -> DENY
  N2  candidate writes nothing, exits 0 -> DENY
  N3  T1 response omits adapter_py -> DENY (never silently validate)
  N4  adapter exits non-zero -> DENY
  N5  adapter_sha256 mismatch (mutated committed value) -> DENY
      (controller re-derives from the chain, not the receipt)
  N6  adapter present but materializes no input dir -> DENY
  N7  positive control promotes: adapter materializes input, frozen T0
      candidate runs, host checker passes -> PROMOTION then CAPABILITY_LOCK

Stdlib only. Hermetic fixtures in throwaway dirs (no live-tree mutation,
no live model calls); live-tree reads are read-only (frozen checker/truth).
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
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import order  # noqa: E402
import promotion  # noqa: E402
import run_arm_h1 as RA  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
FAM05_T1 = os.path.join(FAMC, "families", "fam05", "T1")
FAM05_CHECKER = os.path.join(FAMC, "families", "fam05", "check.py")
FAM05_TRUTH = os.path.join(FAMC, "families", "fam05", "truth.json")


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()
                          ).hexdigest()


# ---- frozen fixtures: exact bytes executed -------------------------------
# CAND_T0: the frozen T0 candidate (generic colon-MANIFEST verifier, argv
# ABI python3 candidate.py <input_dir> <output_path>). Correct on T0 and,
# via the translating adapter, correct on T1 as well.
CAND_T0 = """import hashlib, json, os, sys
inp, outp = sys.argv[1], sys.argv[2]
ok, bad = [], []
for line in open(os.path.join(inp, "MANIFEST")):
    line = line.strip()
    if not line:
        continue
    path, size, sha = line.split(":")
    full = os.path.join(inp, path)
    if not os.path.exists(full):
        bad.append({"path": path, "reason": "missing file"}); continue
    data = open(full, "rb").read()
    if len(data) != int(size):
        bad.append({"path": path, "reason": "size mismatch %d != %s" % (len(data), size)}); continue
    if hashlib.sha256(data).hexdigest() != sha:
        bad.append({"path": path, "reason": "sha256 mismatch"}); continue
    ok.append(path)
json.dump({"ok": sorted(ok), "bad": bad, "unverified": []}, open(outp, "w"))
"""
# ADAPTER_GOOD: materializes the candidate's expected input dir from the
# T1 task surface (frozen ABI python3 adapter.py <task_dir>
# <out_input_dir>). Translates T1 manifest.json into colon MANIFEST +
# copies the actual file bytes, so the generic verifier's report equals
# the frozen T1 truth (b.txt ok, a.txt sha-bad).
ADAPTER_GOOD = """import json, os, sys
task_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
m = json.load(open(os.path.join(task_dir, "manifest.json")))
lines = []
for e in m["files"]:
    lines.append("%s:%s:%s\\n" % (e["path"], e["size"], e["sha256"]))
    src = os.path.join(task_dir, e["path"])
    dst = os.path.join(out_dir, e["path"])
    d = os.path.dirname(dst)
    if d:
        os.makedirs(d, exist_ok=True)
    open(dst, "wb").write(open(src, "rb").read())
open(os.path.join(out_dir, "MANIFEST"), "w").writelines(lines)
"""
# N1: syntactically valid but WRONG output, exits 0.
CAND_WRONG = """import json, sys
json.dump({"ok": [], "bad": [], "unverified": []}, open(sys.argv[2], "w"))
"""
# N2: writes nothing, exits 0.
CAND_NOTHING = """import sys
sys.exit(0)
"""
# N4: adapter exits non-zero.
ADAPTER_FAIL = """import sys
sys.exit(3)
"""
# N6: adapter exits 0 but materializes no input dir.
ADAPTER_EMPTY = """import sys
sys.exit(0)
"""


class LocalJail:
    """Hermetic in-jail shim for the production helper: maps the jail
    paths (/work, /task) onto host temp dirs and executes via subprocess.
    The production helper under test (run_arm_h1.validate_t1_candidate)
    still performs every step in order — write adapter, RUN adapter,
    verify+write candidate, RUN candidate, HOST checker — so execution (not
    mere hashing) and the host-checker gate are proven with real bytes."""

    def __init__(self, work, task):
        self.work = work
        self.task = task

    def run(self, argv, timeout=120):
        mapped = []
        for a in argv:
            if a == "/work/adapter.py":
                mapped.append(os.path.join(self.work, "adapter.py"))
            elif a == "/work/candidate.py":
                mapped.append(os.path.join(self.work, "candidate.py"))
            elif a == "/task":
                mapped.append(self.task)
            elif a.startswith("/work/"):
                mapped.append(os.path.join(self.work, a[len("/work/"):]))
            elif a.startswith("/task/"):
                mapped.append(os.path.join(self.task, a[len("/task/"):]))
            else:
                mapped.append(a)
        return subprocess.run(mapped, capture_output=True, text=True,
                              timeout=timeout)


def hermetic_root():
    root = tempfile.mkdtemp(prefix="h19-a12c-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
        src = os.path.join(FAMC, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                    os.path.join(fam, "fam05"))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def run_helper(adapter_py, cand_src, task_src=FAM05_T1):
    """Run the REAL production helper (run_arm_h1.validate_t1_candidate)
    with real subprocess + real frozen checker. Returns (ok_dict, workdir)
    on pass; raises RuntimeError(CANDIDATE-VALIDATION-FAIL) on failure."""
    work = tempfile.mkdtemp(prefix="h19-work-")
    outdir = tempfile.mkdtemp(prefix="h19-out-")
    taskdir = task_src
    checker_sha = sha_file(FAM05_CHECKER)
    truth_sha = sha_file(FAM05_TRUTH)
    cand_sha = sha_bytes(cand_src)
    sb = LocalJail(work, task_src)
    got = RA.validate_t1_candidate(
        adapter_py=adapter_py, candidate_source=cand_src,
        candidate_sha256=cand_sha, work=work, taskdir=taskdir, sb=sb,
        checker_sha256=checker_sha, truth_sha256=truth_sha, outdir=outdir)
    return got, work, outdir, cand_sha


def cell_for(root, event, universe="A"):
    exp = order.load_expansion(root)
    c = order.expected_event(exp, "PQ", "fam05", event, universe)
    assert c is not None
    return c


# ---- N1: valid-but-WRONG candidate output -> DENY -------------------------
try:
    _got, _w, _o, _sha = run_helper(ADAPTER_GOOD, CAND_WRONG)
    _n1_helper_denied, _n1_why = False, "helper PASSED a wrong output"
except RuntimeError as e:
    _n1_helper_denied = ("CANDIDATE-VALIDATION-FAIL" in str(e)
                         and "host T1 checker" in str(e))
    _n1_why = str(e)[:200]
# The T1 cell itself still SHIPs its own fresh solve (fixture COMPLETE),
# but promotion must DENY: the candidate OUTPUT failed the host checker.
_r1 = hermetic_root()
_t0 = cell_for(_r1, "T0")
_d0 = build_model_run(_r1, cell=_t0, freeze_commit=FREEZE,
                      solver_py=CAND_T0)
_t1 = cell_for(_r1, "T1")
build_model_run(_r1, cell=_t1, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=t0_candidate_sha256(_d0),
                adapter_py=ADAPTER_GOOD,
                candidate_validation={
                    "candidate_output_sha256": "dd" * 32,
                    "checker_sha256": sha_file(FAM05_CHECKER),
                    "truth_sha256": sha_file(FAM05_TRUTH),
                    "checker_returncode": 1,
                    "validation_verdict": "fail",
                    "validated": False})
try:
    # Production wirer refuses a failing validation dict (fail closed):
    # thread the REAL T0 run's evidence (receipt/identity/normalized) so
    # only the candidate gate can refuse.
    import tempfile as _tf
    import glob as _glob
    _d0man = json.load(open(os.path.join(_d0, "H1-RUN-MANIFEST.json")))
    _d0rc = os.path.join(_d0, _d0man["usage_receipts"][0])
    _d0nu = _glob.glob(os.path.join(_d0, "*.normalized.json"))[0]
    _d0id = os.path.join(_d0, "identity.json")
    _d0reuse = os.path.join(_d0, _d0man["reuse_record"])
    _td = _tf.mkdtemp(prefix="h19-n1-wire-")
    _wire_ok = False
    try:
        RA._wire_chain(_td, FREEZE, _d0man, _d0rc, _d0nu, _d0id, "fam05",
                       None, _d0reuse, "c" * 64, "t" * 64, "ship",
                       "o" * 64, None,
                       {"candidate_sha256": "aa" * 32,
                        "executed_sha256": "aa" * 32,
                        "adapter_sha256": "cc" * 32,
                        "candidate_output_sha256": "dd" * 32,
                        "checker_sha256": "ee" * 32,
                        "truth_sha256": "ff" * 32,
                        "checker_returncode": 1,
                        "validation_verdict": "fail",
                        "validated": False})
    except RuntimeError as _e:
        _wire_ok = ("CHAIN-CANDIDATE-DENY" in str(_e)
                    and ("validation_verdict" in str(_e)
                         or "checker_returncode" in str(_e)
                         or "unvalidated" in str(_e)))
    _n1_wire_denied = _wire_ok
except Exception as e:  # noqa: BLE001
    _n1_wire_denied = False
    _n1_why = _n1_why + f" wire_err={e}"[:80]
_t1st = order.cell_state(_r1, _t1, FREEZE)
try:
    promotion.promote_universe(_r1, "PQ", "fam05", "A", FREEZE,
                               "harness-validation")
    _n1_prom_denied = False
except (PermissionError, ValueError) as e:
    _n1_prom_denied = "PROMOTION-DENY" in str(e)
check("N1 candidate valid-but-WRONG output (rc0) denies promotion "
      "(host T1 checker over CANDIDATE-OUTPUT.json)",
      _n1_helper_denied and _n1_wire_denied and _n1_prom_denied,
      f"helper={_n1_why[:80]} wire_denied={_n1_wire_denied} "
      f"prom_denied={_n1_prom_denied}")

# ---- N2: candidate writes nothing, exits 0 -> DENY ------------------------
try:
    _got2, _w2, _o2, _s2 = run_helper(ADAPTER_GOOD, CAND_NOTHING)
    _n2_denied, _n2_why = False, "helper PASSED a missing output"
except RuntimeError as e:
    _n2_denied = ("CANDIDATE-VALIDATION-FAIL" in str(e)
                  and ("wrote no" in str(e) or "host T1 checker" in str(e)
                       or "candidate rc" in str(e)))
    _n2_why = str(e)[:200]
check("N2 candidate writes nothing (rc0) denies validation "
      "(CANDIDATE-VALIDATION-FAIL, no output)",
      _n2_denied, _n2_why[:120])

# ---- N3: T1 response omits adapter_py -> DENY ------------------------------
try:
    _got3, _w3, _o3, _s3 = run_helper(None, CAND_T0)
    _n3_denied, _n3_why = False, "helper PASSED a missing adapter_py"
except RuntimeError as e:
    _n3_denied = ("CANDIDATE-VALIDATION-FAIL" in str(e)
                  and "adapter_py" in str(e))
    _n3_why = str(e)[:200]
# A bare T1 (no validation event) still SHIPs but never promotes.
_r3 = hermetic_root()
_b0 = cell_for(_r3, "T0")
_bd0 = build_model_run(_r3, cell=_b0, freeze_commit=FREEZE,
                       solver_py=CAND_T0)
_b1 = cell_for(_r3, "T1")
build_model_run(_r3, cell=_b1, freeze_commit=FREEZE, solver_py=CAND_T0)
try:
    promotion.promote_universe(_r3, "PQ", "fam05", "A", FREEZE,
                               "harness-validation")
    _n3_prom = False
except (PermissionError, ValueError) as e:
    _n3_prom = "PROMOTION-DENY" in str(e)
check("N3 T1 omits adapter_py denies (fail closed, never silently "
      "validated)",
      _n3_denied and _n3_prom, f"{_n3_why[:80]} prom={_n3_prom}")

# ---- N4: adapter exits non-zero -> DENY ------------------------------------
try:
    _got4, _w4, _o4, _s4 = run_helper(ADAPTER_FAIL, CAND_T0)
    _n4_denied, _n4_why = False, "helper PASSED a failing adapter"
except RuntimeError as e:
    _n4_denied = ("CANDIDATE-VALIDATION-FAIL" in str(e)
                  and "adapter" in str(e))
    _n4_why = str(e)[:200]
check("N4 adapter exits non-zero denies validation "
      "(CANDIDATE-VALIDATION-FAIL)",
      _n4_denied, _n4_why[:120])

# ---- N5: adapter_sha256 mismatch -> DENY -----------------------------------
_r5 = hermetic_root()
_f0 = cell_for(_r5, "T0")
_fd0 = build_model_run(_r5, cell=_f0, freeze_commit=FREEZE,
                       solver_py=CAND_T0)
_f1 = cell_for(_r5, "T1")
build_model_run(_r5, cell=_f1, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=t0_candidate_sha256(_fd0),
                adapter_py=ADAPTER_GOOD)
_res5 = promotion.advance(_r5, "PQ", "fam05", "A", FREEZE,
                         evidence_grade="harness-validation")
_rp5 = json.load(open(_res5["receipt"]))
_good_adapter = _rp5["candidate"]["t1_validation"]["adapter_sha256"]
_bad = json.loads(json.dumps(_rp5))
_bad["candidate"]["t1_validation"]["adapter_sha256"] = "00" * 32
json.dump(_bad, open(_res5["receipt"], "w"))
_st5 = order.cell_state(_r5, cell_for(_r5, "PROMOTION"), FREEZE)
_n5_denied = (_st5["status"] != "COMPLETE"
              and any("adapter_sha256" in r for r in _st5["reasons"]))
_n5_why = "; ".join(_st5["reasons"][:2])[:200]
json.dump(_rp5, open(_res5["receipt"], "w"))
check("N5 mutated adapter_sha256 denies (controller re-derives from the "
      "chain, not the receipt)",
      _n5_denied and _good_adapter != "00" * 32, _n5_why[:120])

# ---- N6: adapter materializes no input dir -> DENY --------------------------
try:
    _got6, _w6, _o6, _s6 = run_helper(ADAPTER_EMPTY, CAND_T0)
    _n6_denied, _n6_why = False, "helper PASSED an empty adapter"
except RuntimeError as e:
    _n6_denied = "CANDIDATE-VALIDATION-FAIL" in str(e)
    _n6_why = str(e)[:200]
check("N6 adapter materializes no input dir denies (candidate fails, "
      "CANDIDATE-VALIDATION-FAIL)",
      _n6_denied, _n6_why[:120])

# ---- N7: positive control promotes then locks -------------------------------
_n7_ev, _n7_work, _n7_out, _n7_sha = run_helper(ADAPTER_GOOD, CAND_T0)
_n7_cand_out = os.path.join(_n7_out, "CANDIDATE-OUTPUT.json")
_n7_out_sha = sha_file(_n7_cand_out)
_n7_ev_ok = (_n7_ev["validated"] is True
             and _n7_ev["validation_verdict"] == "ship"
             and _n7_ev["checker_returncode"] == 0
             and _n7_ev["candidate_sha256"] == _n7_sha
             and _n7_ev["executed_sha256"] == _n7_sha
             and _n7_ev["adapter_sha256"] == sha_bytes(ADAPTER_GOOD)
             and _n7_ev["candidate_output_sha256"] == _n7_out_sha
             and _n7_ev["checker_sha256"] == sha_file(FAM05_CHECKER)
             and _n7_ev["truth_sha256"] == sha_file(FAM05_TRUTH))
_r7 = hermetic_root()
_g0 = cell_for(_r7, "T0")
_gd0 = build_model_run(_r7, cell=_g0, freeze_commit=FREEZE,
                       solver_py=CAND_T0)
assert t0_candidate_sha256(_gd0) == _n7_sha, "frozen T0 sha must match N7"
_g1 = cell_for(_r7, "T1")
build_model_run(_r7, cell=_g1, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=_n7_sha, adapter_py=ADAPTER_GOOD,
                candidate_validation={
                    "candidate_output_sha256": _n7_ev[
                        "candidate_output_sha256"],
                    "checker_sha256": _n7_ev["checker_sha256"],
                    "truth_sha256": _n7_ev["truth_sha256"],
                    "checker_returncode": 0,
                    "validation_verdict": "ship"})
_p7 = promotion.advance(_r7, "PQ", "fam05", "A", FREEZE,
                       evidence_grade="harness-validation")
_l7 = promotion.advance(_r7, "PQ", "fam05", "A", FREEZE,
                       evidence_grade="harness-validation")
_n7_prom = (_p7["event"] == "PROMOTION" and _l7["event"] == "CAPABILITY_LOCK"
            and os.path.isfile(_l7["lock"]))
check("N7 positive control promotes (adapter + frozen candidate + host "
      "checker SHIP, then CAPABILITY_LOCK)",
      _n7_ev_ok and _n7_prom,
      f"ev_ok={_n7_ev_ok} prom={_p7.get('event')}/{_l7.get('event')}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH19 A12c smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

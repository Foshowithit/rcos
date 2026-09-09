#!/usr/bin/env python3
"""H19 — A12c slice A: T1 candidate OUTPUT evaluated with the frozen host
checker + T1 adapter actually fed to the candidate (auditor P0 #1 + P0 #2).

Frozen design (implement exactly, do not redesign):
  D1  T1 producer instruction gains required `adapter_py`
      (ABI python3 adapter.py <task_dir> <out_input_dir>).
  D2  T1 candidate validation path, in order, two jails: adapter.py in
      the RAW-TASK jail -> adapter rc -> stage the adapter's output as
      the candidate jail's /task -> candidate-input manifest -> frozen
      candidate.py (sha-verified) -> candidate rc in the SECOND
      (candidate-only) jail, argv python3 /work/candidate.py /task
      /work/CANDIDATE-OUTPUT.json -> HOST-SIDE frozen T1 checker over
      CANDIDATE-OUTPUT.json -> validated five-way conjunction ->
      exactly one eleven-key chain event. Any experimental failure
      RETURNS validated=false + a named validation_failure cause (A12d
      D1-B: evidence, not an exception); only harness/infrastructure
      failure raises.
  D3  promotion.derive_candidate fail-closed eleven-field predicate +
      order.py provenance re-derivation from the committed chain +
      manifest-file lineage re-derivation (A12d D1-C3); a T1 whose single
      event records validated=false promotes as a RECORDED NOT-PROMOTED
      outcome, never a lock.
  D4  adapter_sha256 is the sha256 of the exact executed adapter bytes.

Acceptance negatives (each proven by a REAL test — real subprocess, real
frozen fam05 T1 checker + truth, real promotion controller; not a claim):
  N1  candidate writes valid-but-WRONG output, exits 0 -> validated=false
      (checker-failed); wired as evidence; promotion records NOT-PROMOTED
      (never a lock)
  N2  candidate writes nothing, exits 0 -> validated=false
      (candidate-output-missing)
  N3  T1 response omits adapter_py -> validated=false (adapter-missing,
      never silently validated); a bare T1 (no validation event) still
      SHIPs but never promotes
  N4  adapter exits non-zero -> validated=false (adapter-failed)
  N5  adapter_sha256 mismatch (mutated committed value) -> DENY
      (controller re-derives from the chain, not the receipt)
  N6  adapter present but materializes no input dir -> validated=false
      (the empty tree stages; the candidate runs on it and fails)
  N7  positive control promotes: adapter materializes input, frozen T0
      candidate runs in the candidate-only jail, host checker passes ->
      eleven-key event + manifest lineage verify -> PROMOTION then
      CAPABILITY_LOCK

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
from dockersandbox import _hash_tree as _jail_hash_tree  # noqa: E402
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
    mere hashing) and the host-checker gate are proven with real bytes.
    Exposes .task_snapshot (the jail_factory contract) over the bound
    visible root."""

    def __init__(self, work, task):
        self.work = work
        self.task = task
        self.task_snapshot = _jail_hash_tree(task) \
            if os.path.isdir(task) else None

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


class CandidateJail(LocalJail):
    """Hermetic stand-in for the production SECOND jail
    (DockerSandbox(cand_work, cand_staging)): maps the candidate jail's
    /work onto the candidate workdir and its /task onto the staged
    candidate-input directory (never the raw task). Production passes no
    factory (real DockerSandbox); hermetic suites pass this so the
    helper's full order — stage, manifest, hash-verify, run, host
    checker — executes with real bytes but without docker."""


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
    with real subprocess + real frozen checker. The adapter runs in the
    LocalJail raw-task shim; the candidate runs in the CandidateJail
    second-jail shim (its /task is the staged candidate input ONLY).
    Returns (result_dict, workdir, outdir, cand_sha): result_dict carries
    validated True (eleven keys) or validated False + validation_failure
    (A12d D1-B: experimental failure returns, never raises)."""
    work = tempfile.mkdtemp(prefix="h19-work-")
    outdir = tempfile.mkdtemp(prefix="h19-out-")
    taskdir = task_src
    checker_sha = sha_file(FAM05_CHECKER)
    truth_sha = sha_file(FAM05_TRUTH)
    cand_sha = sha_bytes(cand_src)
    sb = LocalJail(work, task_src)

    def _factory(cand_work, staging):
        return CandidateJail(cand_work, staging)

    got = RA.validate_t1_candidate(
        adapter_py=adapter_py, candidate_source=cand_src,
        candidate_sha256=cand_sha, work=work, taskdir=taskdir, sb=sb,
        checker_sha256=checker_sha, truth_sha256=truth_sha, outdir=outdir,
        jail_factory=_factory)
    return got, work, outdir, cand_sha


def cell_for(root, event, universe="A"):
    exp = order.load_expansion(root)
    c = order.expected_event(exp, "PQ", "fam05", event, universe)
    assert c is not None
    return c


# ---- N1: valid-but-WRONG candidate output -> validated=false ---------
# (A12d D1-B: experimental evidence, not an exception; the T1 cell still
# SHIPs its own fresh solve, and promotion records NOT-PROMOTED, never a
# lock).
_got_n1, _w_n1, _o_n1, _sha_n1 = run_helper(ADAPTER_GOOD, CAND_WRONG)
_n1_helper_failed = (_got_n1.get("validated") is False
                     and isinstance(_got_n1.get("validation_failure"), str)
                     and _got_n1["validation_failure"].startswith(
                         "checker-failed")
                     and _got_n1.get("checker_returncode") == 1
                     and _got_n1.get("validation_verdict") == "fail"
                     and _got_n1.get("candidate_output_sha256") is not None)
_n1_why = str(_got_n1.get("validation_failure"))[:200]
# The T1 cell itself still SHIPs its own fresh solve (fixture COMPLETE),
# the failed validation wires as exactly one validated=false event, and
# promotion records the terminal NOT-PROMOTED outcome (never a lock).
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
                    "validated": False,
                    "validation_failure": "checker-failed: fixture N1"})
try:
    # Production wirer commits the failed validation as evidence (fail
    # closed on shape, not on outcome): thread the REAL T0 run's evidence
    # (receipt/identity/normalized) so only the candidate gate can speak.
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
                        "validated": False,
                        "candidate_input_manifest_sha256": "11" * 32,
                        "candidate_input_tree_sha256": "22" * 32,
                        "validation_failure": "checker-failed: fixture"})
        _links = [json.loads(l) for l in open(
            os.path.join(_td, "EVIDENCE-CHAIN.jsonl")) if l.strip()]
        _cvs = [l for l in _links
                if l.get("kind") == "candidate-validation"]
        _wire_ok = (len(_cvs) == 1
                    and _cvs[0]["payload"].get("validated") is False)
    except RuntimeError as _e:
        _wire_ok = False
        _n1_why = _n1_why + f" wire_err={_e}"[:80]
    _n1_wire_committed = _wire_ok
except Exception as e:  # noqa: BLE001
    _n1_wire_committed = False
    _n1_why = _n1_why + f" wire_err={e}"[:80]
_t1st = order.cell_state(_r1, _t1, FREEZE)
try:
    promotion.promote_universe(_r1, "PQ", "fam05", "A", FREEZE,
                               "harness-validation")
    _n1_prom_outcome, _n1_why = False, _n1_why + " promote did not refuse"
except (PermissionError, ValueError) as e:
    # A12d D1-B3: the controller RECORDS the terminal NOT-PROMOTED
    # outcome and then REFUSES with a clean PROMOTION-DENY (never a
    # lock, never a deadlock).
    _n1_prom_outcome = "PROMOTION-DENY" in str(e)
    if not _n1_prom_outcome:
        _n1_why = _n1_why + f" prom_err={e}"[:80]
_n1_outcome_file = os.path.join(
    order.run_dir(_r1, cell_for(_r1, "PROMOTION")), "PROMOTION-OUTCOME.json")
_n1_outcome_ok = (
    os.path.isfile(_n1_outcome_file)
    and json.load(open(_n1_outcome_file)).get("outcome") == "NOT-PROMOTED"
    and json.load(open(_n1_outcome_file)).get("reason")
    == "candidate-validation-failed")
_n1_no_lock = not os.path.exists(os.path.join(
    order.capability_dir(_r1, "PQ", "A", "fam05"), "CAPABILITY_LOCK.json"))
_n1_prom_state = order.cell_state(
    _r1, cell_for(_r1, "PROMOTION"), FREEZE)["status"] == "NOT-PROMOTED"
check("N1 candidate valid-but-WRONG output (rc0) fails validation "
      "(host T1 checker over CANDIDATE-OUTPUT.json), wires as evidence, "
      "and records NOT-PROMOTED (refused, never a lock)",
      _n1_helper_failed and _n1_wire_committed
      and _t1st["status"] == "COMPLETE" and _n1_prom_outcome
      and _n1_outcome_ok
      and _n1_no_lock and _n1_prom_state,
      f"helper={_n1_why[:80]} wire={_n1_wire_committed} "
      f"t1={_t1st['status']} refuse={_n1_prom_outcome} "
      f"outcome={_n1_outcome_ok} "
      f"nolock={_n1_no_lock} promstate={_n1_prom_state}")

# ---- N2: candidate writes nothing, exits 0 -> validated=false --------
_got2, _w2, _o2, _s2 = run_helper(ADAPTER_GOOD, CAND_NOTHING)
_n2_failed = (_got2.get("validated") is False
              and isinstance(_got2.get("validation_failure"), str)
              and _got2["validation_failure"].startswith(
                  "candidate-output-missing"))
_n2_why = str(_got2.get("validation_failure"))[:200]
check("N2 candidate writes nothing (rc0) fails validation "
      "(candidate-output-missing, never silently validated)",
      _n2_failed, _n2_why[:120])

# ---- N3: T1 response omits adapter_py -> validated=false ---------------
_got3, _w3, _o3, _s3 = run_helper(None, CAND_T0)
_n3_failed = (_got3.get("validated") is False
              and "adapter-missing" in str(_got3.get("validation_failure"))
              and "adapter_py" in str(_got3.get("validation_failure")))
_n3_why = str(_got3.get("validation_failure"))[:200]
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
check("N3 T1 omits adapter_py fails closed (validated=false, never "
      "silently validated)",
      _n3_failed and _n3_prom, f"{_n3_why[:80]} prom={_n3_prom}")

# ---- N4: adapter exits non-zero -> validated=false -----------------------
_got4, _w4, _o4, _s4 = run_helper(ADAPTER_FAIL, CAND_T0)
_n4_failed = (_got4.get("validated") is False
              and "adapter-failed" in str(_got4.get("validation_failure"))
              and "non-zero" in str(_got4.get("validation_failure")))
_n4_why = str(_got4.get("validation_failure"))[:200]
check("N4 adapter exits non-zero fails validation (adapter-failed)",
      _n4_failed, _n4_why[:120])

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

# ---- N6: adapter materializes no input dir -> validated=false ---------
# (A12d D1: the empty tree stages and the candidate still RUNS against
# it — its failure is the evidence. CAND_T0 needs /task/MANIFEST, so an
# empty input fails it with candidate-failed; the lineage pair records
# the observed empty tree, non-null.)
_got6, _w6, _o6, _s6 = run_helper(ADAPTER_EMPTY, CAND_T0)
_n6_man6 = {}
try:
    _n6_man6 = json.load(open(os.path.join(
        _o6, "CANDIDATE-INPUT-MANIFEST.json")))
except (OSError, ValueError):
    pass
_n6_failed = (_got6.get("validated") is False
              and "candidate-failed" in
              str(_got6.get("validation_failure"))
              and _n6_man6.get("entries") == []
              and isinstance(
                  _got6.get("candidate_input_manifest_sha256"), str))
_n6_why = str(_got6.get("validation_failure"))[:200]
check("N6 adapter materializes no input dir fails validation "
      "(candidate runs on the empty input and fails; empty lineage "
      "manifested)",
      _n6_failed, _n6_why[:120])

# ---- N7: positive control promotes then locks -------------------------------
_n7_ev, _n7_work, _n7_out, _n7_sha = run_helper(ADAPTER_GOOD, CAND_T0)
_n7_cand_out = os.path.join(_n7_out, "CANDIDATE-OUTPUT.json")
_n7_out_sha = sha_file(_n7_cand_out)
_n7_man_path = os.path.join(_n7_out, "CANDIDATE-INPUT-MANIFEST.json")
_n7_man_raw = open(_n7_man_path, "rb").read() if os.path.isfile(
    _n7_man_path) else b""
_n7_man = json.loads(_n7_man_raw.decode()) if _n7_man_raw else {}
_n7_tree_recomputed = hashlib.sha256((json.dumps(
    {"schema": _n7_man.get("schema"), "entries": _n7_man.get("entries")},
    sort_keys=True, indent=1) + "\n").encode()).hexdigest() \
    if _n7_man else None
_n7_paths = [e.get("path") for e in _n7_man.get("entries", [])] \
    if isinstance(_n7_man.get("entries"), list) else None
_n7_lineage_ok = (
    isinstance(_n7_ev.get("candidate_input_manifest_sha256"), str)
    and len(_n7_ev["candidate_input_manifest_sha256"]) == 64
    and isinstance(_n7_ev.get("candidate_input_tree_sha256"), str)
    and len(_n7_ev["candidate_input_tree_sha256"]) == 64
    and hashlib.sha256(_n7_man_raw).hexdigest() ==
    _n7_ev["candidate_input_manifest_sha256"]
    and _n7_tree_recomputed == _n7_ev["candidate_input_tree_sha256"]
    and _n7_man.get("schema") == "candidate-input-manifest-v1"
    and _n7_paths == sorted(_n7_paths)
    and all(isinstance(p, str) and not os.path.isabs(p)
            and ".." not in p.split("/") for p in _n7_paths)
    and all(set(e) == {"path", "kind", "size", "sha256"}
            and e["kind"] == "file" for e in _n7_man["entries"]))
_n7_ev_ok = (_n7_ev["validated"] is True
             and _n7_ev["validation_verdict"] == "ship"
             and _n7_ev["checker_returncode"] == 0
             and _n7_ev["candidate_sha256"] == _n7_sha
             and _n7_ev["executed_sha256"] == _n7_sha
             and _n7_ev["adapter_sha256"] == sha_bytes(ADAPTER_GOOD)
             and _n7_ev["candidate_output_sha256"] == _n7_out_sha
             and _n7_ev["checker_sha256"] == sha_file(FAM05_CHECKER)
             and _n7_ev["truth_sha256"] == sha_file(FAM05_TRUTH)
             and "validation_failure" not in _n7_ev
             and _n7_lineage_ok)
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

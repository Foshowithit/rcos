#!/usr/bin/env python3
"""H23 — A12d slice D1: jail isolation (A12d.1) + failed validation as
committed experimental evidence (A12d.2) + candidate-input lineage
(A12d.7).

All acceptance cases run REAL production code — the real
run_arm_h1.validate_t1_candidate / execute_arrival helpers, REAL docker
jails (DockerSandbox, digest-pinned, --network none), the REAL frozen
fam05 T1 checker + truth, and the REAL promotion/order controllers — in
throwaway dirs (no live-tree mutation, no live model calls).

  A5 (A12d.1 jail isolation, real in-jail docker):
    A5-1 ADAPTER CAN read a raw T1 filename (its bytes reach the
         candidate input and the candidate succeeds).
    A5-2 CANDIDATE CANNOT: a candidate ignoring argv[1] and opening
         /task/<raw T1 filename> fails (non-zero rc, validated=false);
         the raw file is absent from the candidate jail.
    A5-3 ENGINE CANNOT: an engine opening /task/<raw task filename>
         fails while a legitimate engine (only
         /task/field_map.json + /task/records.json) succeeds.
    A5-4 The candidate jail's /task snapshot equals the candidate-input
         tree (manifest entries).
  B6 (A12d.2 failed validation is evidence, not an exception):
    B6-1 wrong output, exit 0 -> validated=false (helper, real docker).
    B6-2 checker-failed stack: T1 COMPLETE + task_verdict ship +
         NOT-PROMOTED + no lock + downstream NOT-EVALUABLE + runner
         refuses before any model call.
    B6-3 adapter-missing: helper returns adapter-missing with null
         lineage; stack T1 still COMPLETE and NOT-PROMOTED.
    B6-4 genuine infrastructure failure (sandbox staging denial) still
         raises and writes no NOT-PROMOTED outcome (and a T1 with no
         validation event denies promotion, never records an outcome).
  C4 (A12d.7 lineage):
    C4-1 tampered manifest bytes -> promotion DENY naming
         candidate_input_manifest_sha256.
    C4-2 tampered entry sha (re-hashed file, stale tree) -> DENY naming
         candidate_input_tree_sha256.
    C4-3 positive path records the ordered lineage adapter ->
         input-tree -> candidate -> output -> checker and promotes only
         when all five verify.

Stdlib only. Prints `H23 D1 smoke: N/N closed`; exits non-zero on any
failure.
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
from dockersandbox import DockerSandbox, ensure_roots  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
FAM05_T1 = os.path.join(FAMC, "families", "fam05", "T1")
FAM05_CHECKER = os.path.join(FAMC, "families", "fam05", "check.py")
FAM05_TRUTH = os.path.join(FAMC, "families", "fam05", "truth.json")
RAW_NAME = "manifest.json"  # known raw T1 filename (frozen T1 surface)


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
CAND_WRONG = """import json, sys
json.dump({"ok": [], "bad": [], "unverified": []}, open(sys.argv[2], "w"))
"""
# A12d.1 acceptance attack: ignores argv[1], tries the raw task file.
CAND_SNEAK = """import sys
raw = open("/task/manifest.json").read()
raise SystemExit("EXFILTRATED RAW BYTES: " + raw[:40])
"""
ENGINE_LEGIT = """import json, sys
fmap = json.load(open(sys.argv[1]))
records = json.load(open(sys.argv[2]))
json.dump({"engine": "legit", "saw": sorted(fmap),
           "records": records}, open(sys.argv[3], "w"))
"""
ENGINE_EVIL = """import sys
raw = open("/task/manifest.json").read()
open(sys.argv[3], "w").write(raw)
"""


def docker_pair(tag):
    """REAL raw-task jail: work under WORK_ROOT, visible copy of the
    frozen fam05 T1 under VISIBLE_ROOT. Returns (work, sb, outdir)."""
    ensure_roots()
    work = tempfile.mkdtemp(prefix="h23-work-" + tag + "-",
                            dir="/tmp/rcos-runs")
    os.chmod(work, 0o700)
    vis = tempfile.mkdtemp(prefix="h23-vis-" + tag + "-",
                           dir="/tmp/rcos-visible")
    os.chmod(vis, 0o700)
    for base, _dirs, files in os.walk(FAM05_T1):
        for fn in files:
            s = os.path.join(base, fn)
            d = os.path.join(vis, os.path.relpath(s, FAM05_T1))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    return work, DockerSandbox(work, vis), tempfile.mkdtemp(
        prefix="h23-out-" + tag + "-")


def helper_kwargs(work, sb, outdir, cand_src):
    return {"candidate_source": cand_src,
            "candidate_sha256": sha_bytes(cand_src),
            "work": work, "taskdir": FAM05_T1, "sb": sb,
            "checker_sha256": sha_file(FAM05_CHECKER),
            "truth_sha256": sha_file(FAM05_TRUTH), "outdir": outdir}


def hermetic_root(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h23-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for f in families:
        shutil.copytree(os.path.join(FAMC, "families", f),
                        os.path.join(fam, f))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for x in dirnames:
            os.chmod(os.path.join(dirpath, x), 0o755)
    return root


def cell_for(root, event, universe="A"):
    exp = order.load_expansion(root)
    c = order.expected_event(exp, "PQ", "fam05", event, universe)
    assert c is not None
    return c


# ================= A5: jail isolation (real docker) ========================
# A5-1: the adapter CAN read the raw T1 file (its bytes reach the
# candidate input and the candidate succeeds).
_w1, _sb1, _o1 = docker_pair("a51")
_g1 = RA.validate_t1_candidate(adapter_py=ADAPTER_GOOD,
                               **helper_kwargs(_w1, _sb1, _o1, CAND_T0))
_a51 = (_g1.get("validated") is True
        and _g1.get("adapter_sha256") == sha_bytes(ADAPTER_GOOD))
print(f"A5-1 adapter-can-read-raw: validated={_g1.get('validated')} "
      f"adapter_sha={str(_g1.get('adapter_sha256'))[:12]} "
      f"manifest={str(_g1.get('candidate_input_manifest_sha256'))[:12]} "
      f"tree={str(_g1.get('candidate_input_tree_sha256'))[:12]}")
check("A5-1 adapter CAN read the raw T1 file (bytes reach the candidate "
      "input, candidate succeeds)", _a51, str(_g1)[:200])

# A5-2: the candidate CANNOT read the raw T1 file.
_w2, _sb2, _o2 = docker_pair("a52")
_cap = {}


def _capture_factory(cand_work, staging):
    jail = DockerSandbox(cand_work, staging)
    _cap["jail"] = jail
    _cap["staging"] = staging
    return jail


_g2 = RA.validate_t1_candidate(
    adapter_py=ADAPTER_GOOD,
    **helper_kwargs(_w2, _sb2, _o2, CAND_SNEAK),
    candidate_jail_factory=_capture_factory)
_jail2 = _cap["jail"]
_oracle = _jail2.attempt_read(os.path.join(FAM05_T1, RAW_NAME))
_in_task = _jail2.run(["python3", "-c",
                       "import os;print(sorted(os.listdir('/task')))"])
_raw_probe = _jail2.run(["cat", "/task/" + RAW_NAME])
_man2 = json.load(open(os.path.join(_o2, "CANDIDATE-INPUT-MANIFEST.json")))
_snap_files = {k[5:]: v for k, v in _jail2.task_snapshot.items()
               if k.startswith("file|")}
_man_files = {e["path"]: e["sha256"] for e in _man2["entries"]}
_a52 = (_g2.get("validated") is False
        and isinstance(_g2.get("validation_failure"), str)
        and _g2["validation_failure"].startswith("candidate-failed")
        and _oracle[0] is False
        and _raw_probe.returncode != 0
        and _snap_files == _man_files)
print(f"A5-2 candidate-cannot-read-raw: validated={_g2.get('validated')} "
      f"cause={_g2.get('validation_failure', '')[:60]!r} "
      f"oracle={_oracle} task={_in_task.stdout.strip()[:60]!r} "
      f"raw_probe_rc={_raw_probe.returncode}")
check("A5-2 candidate CANNOT read the raw T1 file (ignores argv[1], "
      "fails; raw absent from the candidate jail)", _a52,
      f"cause={_g2.get('validation_failure')} oracle={_oracle} "
      f"probe_rc={_raw_probe.returncode}")

# A5-3: the engine jail sees ONLY the adapted payload.
_w3, _sb3, _o3 = docker_pair("a53")
_legit = os.path.join(_w3, "legit_engine.py")
open(_legit, "w").write(ENGINE_LEGIT)
_arr = {"decision": "use_capability",
        "execution_payload": {"field_map": {"out": "result"},
                              "records": {"n": 3}},
        "notes": "h23"}
_e3 = RA.execute_arrival("correct", _arr, _w3, _o3, FAM05_T1, _legit, _sb3)
_evil = os.path.join(_w3, "evil_engine.py")
open(_evil, "w").write(ENGINE_EVIL)
_w3b = tempfile.mkdtemp(prefix="h23-work-a53b-", dir="/tmp/rcos-runs")
os.chmod(_w3b, 0o700)
_e3b = RA.execute_arrival("correct", _arr, _w3b, _o3, FAM05_T1, _evil,
                          _sb3)
_ej = _e3.get("engine_jail") or {}
_snap_keys = sorted((_ej.get("task_snapshot") or {}))
# Rebuild the adapted-input bytes the production jail was mounted from
# (same payload documents, fresh visible dir) and prove the production
# snapshot EQUALS those bytes; a probe jail over the replica then proves
# the raw file is unreachable from such a jail.
_replica = tempfile.mkdtemp(prefix="h23-replica-", dir="/tmp/rcos-visible")
os.chmod(_replica, 0o700)
for _name in ("field_map", "records"):
    with open(os.path.join(_replica, _name + ".json"), "w") as _f:
        json.dump(_arr["execution_payload"][_name], _f, sort_keys=True,
                  indent=1)
        _f.write("\n")
from dockersandbox import _hash_tree as _ht
_replica_snap = _ht(_replica)
_probe_work = tempfile.mkdtemp(prefix="h23-probe-", dir="/tmp/rcos-runs")
os.chmod(_probe_work, 0o700)
_probe = DockerSandbox(_probe_work, _replica)
_probe_oracle = _probe.attempt_read(os.path.join(FAM05_T1, RAW_NAME))
_probe_cat = _probe.run(["cat", "/task/" + RAW_NAME])
_a53 = (_e3["container_returncode"] == 0
        and _e3b["container_returncode"] != 0
        and _snap_keys == ["file|field_map.json", "file|records.json"]
        and (_ej.get("task_snapshot") or {}) == _replica_snap
        and isinstance(_ej.get("adapted_input_sha256"), str)
        and len(_ej["adapted_input_sha256"]) == 64
        and _probe_oracle[0] is False
        and _probe_cat.returncode != 0)
print(f"A5-3 engine-jail: legit_rc={_e3['container_returncode']} "
      f"evil_rc={_e3b['container_returncode']} "
      f"snapshot={_snap_keys} adapted={str(_ej.get('adapted_input_sha256'))[:12]} "
      f"oracle={_probe_oracle} raw_probe_rc={_probe_cat.returncode}")
check("A5-3 engine CANNOT read the raw task file while a legitimate "
      "engine (only field_map+records) succeeds", _a53,
      f"legit={_e3['container_returncode']} evil={_e3b['container_returncode']} "
      f"snap={_snap_keys} oracle={_probe_oracle}")

# A5-4: the candidate jail's /task snapshot equals the candidate-input
# tree hash (entry map + recomputed tree hash).
_tree_re = hashlib.sha256((json.dumps(
    {"schema": _man2.get("schema"), "entries": _man2.get("entries")},
    sort_keys=True, indent=1) + "\n").encode()).hexdigest()
_a54 = (_snap_files == _man_files
        and _tree_re == _man2["tree_sha256"]
        and RAW_NAME not in _snap_files)
print(f"A5-4 snapshot-equals-input-tree: entries={len(_man_files)} "
      f"tree_match={_tree_re == _man2['tree_sha256']} "
      f"raw_absent={RAW_NAME not in _snap_files}")
check("A5-4 candidate jail /task snapshot equals the candidate-input "
      "tree hash", _a54, f"snap={sorted(_snap_files)}")

# ================= B6: failed validation is evidence =======================
# B6-1: wrong output, exit 0 -> validated=false (helper, real docker).
_w4, _sb4, _o4 = docker_pair("b61")
_g4 = RA.validate_t1_candidate(adapter_py=ADAPTER_GOOD,
                               **helper_kwargs(_w4, _sb4, _o4, CAND_WRONG))
_b61 = (_g4.get("validated") is False
        and isinstance(_g4.get("validation_failure"), str)
        and _g4["validation_failure"].startswith("checker-failed")
        and _g4.get("checker_returncode") == 1
        and _g4.get("validation_verdict") == "fail")
print(f"B6-1 wrong-output: validated={_g4.get('validated')} "
      f"cause={_g4.get('validation_failure', '')[:80]!r} "
      f"checker_rc={_g4.get('checker_returncode')}")
check("B6-1 candidate writes wrong output (rc0) -> validated=false "
      "(checker-failed)", _b61, str(_g4.get("validation_failure"))[:150])

# B6-2: checker-failed full stack.
_r6 = hermetic_root("b62")
_t0_6 = cell_for(_r6, "T0")
_d0_6 = build_model_run(_r6, cell=_t0_6, freeze_commit=FREEZE,
                        solver_py=CAND_T0)
_t1_6 = cell_for(_r6, "T1")
_d1_6 = build_model_run(
    _r6, cell=_t1_6, freeze_commit=FREEZE, solver_py=CAND_T0,
    validates_candidate=t0_candidate_sha256(_d0_6),
    adapter_py=ADAPTER_GOOD,
    candidate_validation={"checker_returncode": 1,
                          "validation_verdict": "fail",
                          "validated": False,
                          "validation_failure":
                              "checker-failed: h23 B6-2"})
_man6 = json.load(open(os.path.join(_d1_6, "H1-RUN-MANIFEST.json")))
_st6 = order.cell_state(_r6, _t1_6, FREEZE)
try:
    promotion.advance(_r6, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _b62_prom, _b62_prom_err = False, "advance did not refuse"
except (PermissionError, ValueError) as e:
    # A12d D1-B3: the controller RECORDS the terminal NOT-PROMOTED
    # outcome and then REFUSES with a clean PROMOTION-DENY (never a
    # lock, never a deadlock).
    _b62_prom = "PROMOTION-DENY" in str(e)
    _b62_prom_err = "" if _b62_prom else str(e)[:120]
_b62_outcome = os.path.join(
    order.run_dir(_r6, cell_for(_r6, "PROMOTION")), "PROMOTION-OUTCOME.json")
_b62_outcome_ok = (
    os.path.isfile(_b62_outcome)
    and json.load(open(_b62_outcome)).get("outcome") == "NOT-PROMOTED"
    and json.load(open(_b62_outcome)).get("reason")
    == "candidate-validation-failed")
_b62_nolock = not os.path.exists(os.path.join(
    order.capability_dir(_r6, "PQ", "A", "fam05"), "CAPABILITY_LOCK.json"))
_b62_pstate = order.cell_state(_r6, cell_for(_r6, "PROMOTION"), FREEZE)
_exp6 = order.load_expansion(_r6)
_t2_6 = [c for c in _exp6["cells"] if c["block"] == "PQ"
         and c["family"] == "fam05" and c["event"] == "T2"
         and c["universe"] == "A"][0]
_b62_t2 = order.cell_state(_r6, _t2_6, FREEZE)
print(f"B6-2 stack: t1={_st6['status']} task_verdict={_man6.get('task_verdict')} "
      f"refuse={_b62_prom} outcome={_b62_outcome_ok} nolock={_b62_nolock} "
      f"prom_state={_b62_pstate['status']} t2={_b62_t2['status']} "
      f"reason={(_b62_t2['reasons'][:1] or [''])[0][:80]!r}")
check("B6-2 checker-failed stack: T1 COMPLETE (task_verdict ship) + "
      "NOT-PROMOTED recorded (refused, never a lock) + downstream "
      "NOT-EVALUABLE",
      _st6["status"] == "COMPLETE" and _man6.get("task_verdict") == "ship"
      and _b62_prom and _b62_outcome_ok and _b62_nolock
      and _b62_pstate["status"] == "NOT-PROMOTED"
      and _b62_t2["status"] == "NOT-EVALUABLE"
      and "acquisition-failed" in " ".join(_b62_t2["reasons"]),
      f"t1={_st6['status']} refuse={_b62_prom}{_b62_prom_err} "
      f"outcome={_b62_outcome_ok} "
      f"nolock={_b62_nolock} pstate={_b62_pstate['status']} "
      f"t2={_b62_t2['status']}")

# B6-2b: the runner refuses the downstream cell BEFORE any model call.
# Full RA.main() on a disposable git worktree (real preflight against
# real git history; all writes land under the worktree's state/, never
# the live tree; no model call and no docker before the refusal).
REPO = "/home/chow/chow-work/rcos"
_wt = tempfile.mkdtemp(prefix="h23-wt-")
os.rmdir(_wt)  # git worktree add requires a nonexistent path
_wt_famc = os.path.join(_wt, "benchmarks", "fam-c")
try:
    subprocess.run(["git", "-C", REPO, "worktree", "add", _wt, "HEAD"],
                   capture_output=True, text=True, check=True)
    _wt_freeze = json.load(
        open(os.path.join(_wt_famc, "FREEZE.json")))["freeze_commit"]
    _t0_wt = cell_for(_wt_famc, "T0")
    _d0_wt = build_model_run(_wt_famc, cell=_t0_wt,
                             freeze_commit=_wt_freeze, solver_py=CAND_T0)
    _t1_wt = cell_for(_wt_famc, "T1")
    build_model_run(_wt_famc, cell=_t1_wt, freeze_commit=_wt_freeze,
                    solver_py=CAND_T0,
                    validates_candidate=t0_candidate_sha256(_d0_wt),
                    adapter_py=ADAPTER_GOOD,
                    candidate_validation={"checker_returncode": 1,
                                          "validation_verdict": "fail",
                                          "validated": False,
                                          "validation_failure":
                                              "checker-failed: h23 B6-2b"})
    try:
        promotion.advance(_wt_famc, "PQ", "fam05", "A", _wt_freeze,
                          evidence_grade="harness-validation")
        _wt_recorded = False
    except (PermissionError, ValueError) as _e:
        _wt_recorded = "PROMOTION-DENY" in str(_e)
    _wt_refused = False
    _old_base = RA.BASE
    RA.BASE = _wt_famc
    try:
        try:
            promotion.advance(_wt_famc, "PQ", "fam05", "A", _wt_freeze,
                              evidence_grade="harness-validation")
        except (PermissionError, ValueError) as _e:
            _wt_refused = "PROMOTION-DENY" in str(_e)
        RA.main("P", "fam05", "T2", "correct", "/tmp/h23-unused-outdir",
                None, {"block": "PQ"})
        _b62b = "NOT REFUSED"
    except RuntimeError as e:
        _b62b = str(e)
    except SystemExit as e:
        _b62b = f"SystemExit({e})"
    finally:
        RA.BASE = _old_base
    if not _wt_refused:
        _b62b = "PROMOTE-DID-NOT-REFUSE: " + _b62b
    if not _wt_recorded:
        _b62b = "OUTCOME-NOT-RECORDED: " + _b62b
finally:
    subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force",
                    _wt], capture_output=True, text=True)
_b62b_ok = "ACQUISITION-FAILED-DENY" in _b62b
print(f"B6-2b runner-refusal: {_b62b[:160]!r}")
check("B6-2b runner refuses the downstream cell before any model call "
      "(ACQUISITION-FAILED-DENY)", _b62b_ok, _b62b[:150])

# B6-3: missing adapter_py -> adapter-missing with null lineage; the T1
# stack still COMPLETES and records NOT-PROMOTED.
_w5, _sb5, _o5 = docker_pair("b63")
_g5 = RA.validate_t1_candidate(
    adapter_py=None, **helper_kwargs(_w5, _sb5, _o5, CAND_T0))
_b63_helper = (_g5.get("validated") is False
               and isinstance(_g5.get("validation_failure"), str)
               and _g5["validation_failure"].startswith("adapter-missing")
               and _g5.get("candidate_input_manifest_sha256") is None
               and _g5.get("candidate_input_tree_sha256") is None)
_r7 = hermetic_root("b63")
_t0_7 = cell_for(_r7, "T0")
_d0_7 = build_model_run(_r7, cell=_t0_7, freeze_commit=FREEZE,
                        solver_py=CAND_T0)
_t1_7 = cell_for(_r7, "T1")
build_model_run(_r7, cell=_t1_7, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=t0_candidate_sha256(_d0_7),
                candidate_validation={"adapter_sha256": None,
                                      "executed_sha256": None,
                                      "candidate_output_sha256": None,
                                      "checker_returncode": None,
                                      "validation_verdict": None,
                                      "validated": False,
                                      "validation_failure":
                                          "adapter-missing: h23 B6-3",
                                      "candidate_input_manifest_sha256": None,
                                      "candidate_input_tree_sha256": None})
_st7 = order.cell_state(_r7, _t1_7, FREEZE)
try:
    promotion.advance(_r7, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _b63_prom = False
except (PermissionError, ValueError) as e:
    _b63_prom = "PROMOTION-DENY" in str(e)
_b63_outcome = os.path.join(
    order.run_dir(_r7, cell_for(_r7, "PROMOTION")), "PROMOTION-OUTCOME.json")
_b63_outcome_ok = (
    os.path.isfile(_b63_outcome)
    and json.load(open(_b63_outcome)).get("outcome") == "NOT-PROMOTED")
print(f"B6-3 adapter-missing: helper_cause={_g5.get('validation_failure', '')[:60]!r} "
      f"lineage_null={_g5.get('candidate_input_manifest_sha256') is None} "
      f"t1={_st7['status']} refuse={_b63_prom} outcome={_b63_outcome_ok}")
check("B6-3 missing adapter_py -> adapter-missing (null lineage); T1 "
      "still COMPLETE and NOT-PROMOTED (recorded, refused)",
      _b63_helper and _st7["status"] == "COMPLETE" and _b63_prom
      and _b63_outcome_ok,
      f"helper={_b63_helper} t1={_st7['status']} prom={_b63_prom}")

# B6-4: genuine infrastructure failure still raises and records nothing.
_w8, _sb8, _o8 = docker_pair("b64")


class _BrokenJail:
    def run(self, argv, timeout=120):
        raise PermissionError(
            "STABILITY-DENY source mutated during staging; refused")


try:
    RA.validate_t1_candidate(
        adapter_py=ADAPTER_GOOD,
        **helper_kwargs(_w8, _BrokenJail(), _o8, CAND_T0))
    _b64_raise = "NOT RAISED"
except PermissionError as e:
    _b64_raise = str(e)
_r8 = hermetic_root("b64")
_t0_8 = cell_for(_r8, "T0")
_d0_8 = build_model_run(_r8, cell=_t0_8, freeze_commit=FREEZE,
                        solver_py=CAND_T0)
_t1_8 = cell_for(_r8, "T1")
build_model_run(_r8, cell=_t1_8, freeze_commit=FREEZE, solver_py=CAND_T0)
try:
    promotion.advance(_r8, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _b64_deny = "NOT DENIED"
except (PermissionError, ValueError) as e:
    _b64_deny = str(e)
_b64_no_outcome = not os.path.exists(os.path.join(
    order.run_dir(_r8, cell_for(_r8, "PROMOTION")), "PROMOTION-OUTCOME.json"))
_b64_ok = ("STABILITY-DENY" in _b64_raise
           and "PROMOTION-DENY" in _b64_deny
           and "NOT-PROMOTED" not in _b64_deny
           and _b64_no_outcome)
print(f"B6-4 infra: raise={_b64_raise[:80]!r} deny={_b64_deny[:80]!r} "
      f"no_outcome={_b64_no_outcome}")
check("B6-4 infrastructure failure raises (no NOT-PROMOTED outcome; a "
      "T1 with no validation event denies promotion)",
      _b64_ok, f"raise={_b64_raise[:80]} deny={_b64_deny[:80]}")

# ================= C4: lineage =============================================
# C4-1: tamper one byte of the persisted manifest -> DENY naming the
# manifest hash.
_r9 = hermetic_root("c41")
_t0_9 = cell_for(_r9, "T0")
_d0_9 = build_model_run(_r9, cell=_t0_9, freeze_commit=FREEZE,
                        solver_py=CAND_T0)
_t1_9 = cell_for(_r9, "T1")
_d1_9 = build_model_run(_r9, cell=_t1_9, freeze_commit=FREEZE,
                        solver_py=CAND_T0,
                        validates_candidate=t0_candidate_sha256(_d0_9),
                        adapter_py=ADAPTER_GOOD)
_mp9 = os.path.join(_d1_9, "CANDIDATE-INPUT-MANIFEST.json")
_raw9 = bytearray(open(_mp9, "rb").read())
_raw9[10] ^= 0x01
open(_mp9, "wb").write(bytes(_raw9))
try:
    promotion.advance(_r9, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _c41 = "NOT DENIED"
except (PermissionError, ValueError) as e:
    _c41 = str(e)
_c41_ok = "candidate_input_manifest_sha256" in _c41
print(f"C4-1 tampered-manifest deny: {_c41[:160]!r}")
check("C4-1 tampered manifest bytes -> DENY naming "
      "candidate_input_manifest_sha256", _c41_ok, _c41[:150])

# C4-2: tamper one entry sha (re-hashed file, stale tree) -> DENY naming
# the tree hash.
_r10 = hermetic_root("c42")
_t0_10 = cell_for(_r10, "T0")
_d0_10 = build_model_run(_r10, cell=_t0_10, freeze_commit=FREEZE,
                         solver_py=CAND_T0)
_t1_10 = cell_for(_r10, "T1")
build_model_run(_r10, cell=_t1_10, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=t0_candidate_sha256(_d0_10),
                adapter_py=ADAPTER_GOOD, candidate_input_tamper="entry-sha")
try:
    promotion.advance(_r10, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _c42 = "NOT DENIED"
except (PermissionError, ValueError) as e:
    _c42 = str(e)
_c42_ok = ("candidate_input_tree_sha256" in _c42
           and "candidate_input_manifest_sha256" not in _c42)
print(f"C4-2 tampered-entry deny: {_c42[:160]!r}")
check("C4-2 tampered entry sha -> DENY naming "
      "candidate_input_tree_sha256", _c42_ok, _c42[:150])

# C4-3: the positive path records the ordered lineage and promotes only
# when all five verify.
_r11 = hermetic_root("c43")
_t0_11 = cell_for(_r11, "T0")
_d0_11 = build_model_run(_r11, cell=_t0_11, freeze_commit=FREEZE,
                         solver_py=CAND_T0)
_t1_11 = cell_for(_r11, "T1")
build_model_run(_r11, cell=_t1_11, freeze_commit=FREEZE, solver_py=CAND_T0,
                validates_candidate=t0_candidate_sha256(_d0_11),
                adapter_py=ADAPTER_GOOD)
_p11 = promotion.advance(_r11, "PQ", "fam05", "A", FREEZE,
                         evidence_grade="harness-validation")
_l11 = promotion.advance(_r11, "PQ", "fam05", "A", FREEZE,
                         evidence_grade="harness-validation")
_tv11 = json.load(open(_p11["receipt"]))["candidate"]["t1_validation"]
_lineage = [_tv11.get("adapter_sha256"),
            _tv11.get("candidate_input_tree_sha256"),
            _tv11.get("candidate_sha256"),
            _tv11.get("candidate_output_sha256"),
            _tv11.get("checker_sha256")]
_c43_pos = (_p11["event"] == "PROMOTION"
            and _l11["event"] == "CAPABILITY_LOCK"
            and all(isinstance(x, str) and len(x) == 64 for x in _lineage))
# ... and a receipt that rewrites any lineage link no longer verifies.
_rp11 = json.load(open(_p11["receipt"]))
_rp11["candidate"]["t1_validation"]["adapter_sha256"] = "00" * 32
json.dump(_rp11, open(_p11["receipt"], "w"))
_st11a = order.cell_state(_r11, cell_for(_r11, "PROMOTION"), FREEZE)
_rp11["candidate"]["t1_validation"]["adapter_sha256"] = \
    _tv11["adapter_sha256"]
_rp11["candidate"]["t1_validation"]["candidate_input_tree_sha256"] = \
    "00" * 32
json.dump(_rp11, open(_p11["receipt"], "w"))
_st11b = order.cell_state(_r11, cell_for(_r11, "PROMOTION"), FREEZE)
_rp11["candidate"]["t1_validation"]["candidate_input_tree_sha256"] = \
    _tv11["candidate_input_tree_sha256"]
json.dump(_rp11, open(_p11["receipt"], "w"))
_c43_neg = (_st11a["status"] != "COMPLETE"
            and "adapter_sha256" in " ".join(_st11a["reasons"])
            and _st11b["status"] != "COMPLETE"
            and "candidate_input_tree_sha256" in " ".join(_st11b["reasons"]))
print(f"C4-3 lineage: {[x[:8] for x in _lineage]} "
      f"prom={_p11['event']}/{_l11['event']} "
      f"tamper_adapter={_st11a['status']} tamper_tree={_st11b['status']}")
check("C4-3 ordered lineage (adapter->input->candidate->output->"
      "checker) promotes; rewriting any link denies",
      _c43_pos and _c43_neg,
      f"pos={_c43_pos} adapter_tamper={_st11a['status']} "
      f"tree_tamper={_st11b['status']}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH23 D1 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

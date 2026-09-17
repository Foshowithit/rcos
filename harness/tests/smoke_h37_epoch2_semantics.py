#!/usr/bin/env python3
"""H37 EPOCH-2 SEMANTICS smoke — TERMINAL-OUTCOME PROGRESS SEMANTICS +
the explicit epoch-2 lineage (third-party ruling recorded in
benchmarks/fam-c/EPOCH-1-CLOSURE.md; epoch 1 closed
terminated-not-repaired).

The epoch-1 defect this suite closes: `completed_cells()` accepted only
`status == "COMPLETE"`, so a lawful validated NOT-PROMOTED terminal — and
the CAPABILITY_LOCK event of a failed universe, which had NO terminal
writer at all — deadlocked the frozen prefix walk. Epoch 2's algebra
advances the SAME prefix on EVENT-SPECIFIC validated terminals without
authorizing anything a COMPLETE cell would.

Coverage (everything through the REAL controllers/validators — no stubs):

  A. TERMINAL ALGEBRA (hermetic fam05 fixture, real model-run contract):
     A1 T0/T1 acquisition COMPLETE; the T1 chain carries exactly one
        candidate-validation event with validated=false (checker-failed).
     A2 the PROMOTION cell validates as the DERIVED NOT-PROMOTED terminal
        before any outcome record exists, and the prefix walk shows it.
     A3 one promotion.advance() records PROMOTION-OUTCOME.json AND
        completes the sibling CAPABILITY_LOCK event as
        CAPABILITY-LOCK-OUTCOME.json (NOT-LOCKED, bound to the promotion
        outcome sha + the real T0/T1 chain tips), then refuses with the
        combined PROMOTION-DENY | LOCK-DENY terminal message.
     A4 the full prefix walks: T0, T1, PROMOTION/NOT-PROMOTED,
        CAPABILITY_LOCK/NOT-LOCKED, and every downstream A-cell resolves
        NOT-EVALUABLE (B/D universes untouched by the failure).
     A5 the DEADLOCK IS GONE: the next family-universe event (C's T0) is
        authorized out of the same prefix — while NOTHING is authorized:
        no CAPABILITY_LOCK.json, no lock minting, no promotion receipt,
        no downstream execution (ACQUISITION-FAILED-DENY), no retry.
     A6 re-invocation is idempotent: advance() refuses, no file rewritten.
  B. MALFORMED/FORGED TERMINALS FAIL CLOSED (each mutation on a fresh
     good fixture, then restored):
     B1 tampered outcome field (outcome "COMPLETE") -> INADMISSIBLE.
     B2 forged acquisition tips -> INADMISSIBLE.
     B3 fabricated H1-RUN-MANIFEST.json in the lock run dir -> INADMISSIBLE.
     B4 tampered PROMOTION-OUTCOME.json (the bound bytes) -> the PROMOTION
        cell is INADMISSIBLE and the lock cell blocks.
     B5 a real CAPABILITY_LOCK.json beside the NOT-LOCKED outcome ->
        refused (mutually exclusive); the writer refuses too.
     ... every case blocks the prefix walk (the lock cell is not done).
  C. EPOCH-2 LINEAGE (the explicit transition mechanism):
     C1 a structurally valid transition record ACTIVATES epoch 2:
        state namespaces prefix under state/epoch2/ (run_dir/capability_dir
        and the specificity stray walk), while a COMPLETED epoch-1 cell
        under state/ is NEVER scanned (completed_cells empty, cell_state
        INCOMPLETE at the epoch-2 derived path).
     C2 the transition itself on a disposable git worktree of THIS
        checkout (real git, no network): --check reports epoch 1; a
        drifted epoch-1 lock refuses the transition; the real
        `harness/epoch_transition.py --transition` writes the record and
        mints the fresh epoch-2 locks (epoch: 2 + transition citation +
        their own empty amendment lineage); preflight.validate_all is
        green in epoch 2; after committing the fresh files the lock byte
        authority also holds; the runner's FINAL gate refuses naming the
        OPEN epoch-2 lock; the standard lifecycle continues on the new
        lineage (mint tool re-check/--finalize targets the epoch-2 lock;
        after finalizing both epoch-2 authorities the gate is green).
  D. ALGEBRA TABLE + NO-CONVERSION guard: COMPLETE/progress-valid pairs
     exactly as the ruling lists; INCOMPLETE and INADMISSIBLE are never
     progress-valid for ANY cell; a NOT-PROMOTED/NOT-LOCKED cell can never
     be consumed as COMPLETE (run_evidence/emit_capability_lock refuse).

Stdlib only, no network, no docker. Prints
`H37 epoch-2 semantics smoke: N/N closed`; exits non-zero on failure.
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
ROOT = os.path.dirname(HARNESS)
FAMC = os.path.join(ROOT, "benchmarks", "fam-c")
REPO = ROOT
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, FAMC)

import epoch as EPOCH  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import preflight as PF  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


CAND_T0 = """import os, sys
indir, outp = sys.argv[1], sys.argv[2]
open(outp, "w").write("ok:" + ",".join(sorted(os.listdir(indir))))
"""
ADAPTER_GOOD = """import json, os, sys
task_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
m = json.load(open(os.path.join(task_dir, "manifest.json")))
for e in m["files"]:
    src = os.path.join(task_dir, e["path"])
    dst = os.path.join(out_dir, e["path"])
    d = os.path.dirname(dst)
    if d:
        os.makedirs(d, exist_ok=True)
    open(dst, "wb").write(open(src, "rb").read())
open(os.path.join(out_dir, "MANIFEST"), "w").write("h37")
"""


def hermetic_root(tag):
    """A throwaway Fam-C instance carrying the real governed files."""
    root = tempfile.mkdtemp(prefix="h37-" + tag + "-")
    for name in list(PF.PROTOCOL_GOVERNED) + [
            "ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
            "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
            EPOCH.EPOCH1_CLOSURE_FILE]:
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                    os.path.join(fam, "fam05"))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for x in dirnames:
            os.chmod(os.path.join(dirpath, x), 0o755)
    return root


def cell_for(root, event, universe="A", block="PQ", family="fam05"):
    exp = order.load_expansion(root)
    if event in order.ACQ_EVENTS:
        c = order.expected_event(exp, block, family, event, universe)
    else:
        c = order.expected_cell(exp, block, family, event, "P",
                                order.ARM_NAME[order.CAPABILITY[universe]])
    assert c is not None, (event, universe)
    return c


def build_failed_universe(root):
    """T0 + T1 (candidate validation FAILED) of PQ/fam05/A — the lawful
    failed-acquisition universe, through the shared production fixture."""
    t0 = cell_for(root, "T0")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=CAND_T0)
    t1 = cell_for(root, "T1")
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=CAND_T0,
                    validates_candidate=t0_candidate_sha256(d0),
                    adapter_py=ADAPTER_GOOD,
                    candidate_validation={
                        "checker_returncode": 1,
                        "validation_verdict": "fail",
                        "validated": False,
                        "validation_failure": "checker-failed: h37"})
    return t0, t1


def record_paths(root):
    prom = cell_for(root, "PROMOTION")
    lock = cell_for(root, "CAPABILITY_LOCK")
    return (os.path.join(order.run_dir(root, prom),
                         order.PROMOTION_OUTCOME_FILE),
            os.path.join(order.run_dir(root, lock),
                         order.CAPABILITY_LOCK_OUTCOME_FILE))


def advance_expect_refusal(root, tag=""):
    try:
        promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                          evidence_grade="harness-validation")
        return "NO-REFUSAL" + tag
    except (PermissionError, ValueError) as e:
        return str(e)


# ===========================================================================
# A. terminal algebra on the real machinery
# ===========================================================================
A_ROOT = hermetic_root("a")
T0C, T1C = build_failed_universe(A_ROOT)
PROMC = cell_for(A_ROOT, "PROMOTION")
LOCKC = cell_for(A_ROOT, "CAPABILITY_LOCK")
T2C = cell_for(A_ROOT, "T2")
T2B = cell_for(A_ROOT, "T2", universe="B")

_a1 = (order.cell_state(A_ROOT, T0C, FREEZE)["status"] == "COMPLETE"
       and order.cell_state(A_ROOT, T1C, FREEZE)["status"] == "COMPLETE")
check("A1 T0/T1 acquisition COMPLETE with the failed candidate "
      "validation committed on the T1 chain", _a1,
      f"t0={order.cell_state(A_ROOT, T0C, FREEZE)['status']} "
      f"t1={order.cell_state(A_ROOT, T1C, FREEZE)['status']}")

_out_p, _out_l = record_paths(A_ROOT)
_st = order.cell_state(A_ROOT, PROMC, FREEZE)
_done = order.completed_cells(A_ROOT)
_ev, _cell, _reasons = promotion.next_event(A_ROOT, "PQ", "fam05", "A")
_a2 = (_st["status"] == "NOT-PROMOTED" and not os.path.exists(_out_p)
       and PROMC["cell_id"] in _done and _ev == "PROMOTION"
       and not _reasons)
check("A2 PROMOTION validates as the DERIVED NOT-PROMOTED terminal before "
      "any record, and the prefix walk shows it (record still owed)",
      _a2, f"state={_st['status']} outcome_exists={os.path.exists(_out_p)} "
      f"done={len(_done)} next={_ev} reasons={_reasons[:1]}")

_msg = advance_expect_refusal(A_ROOT)
_oc = json.load(open(_out_p)) if os.path.exists(_out_p) else {}
_lc = json.load(open(_out_l)) if os.path.exists(_out_l) else {}
_t0_tip = order._chain_tip(os.path.join(order.run_dir(A_ROOT, T0C),
                                        "EVIDENCE-CHAIN.jsonl"))
_t1_tip = order._chain_tip(os.path.join(order.run_dir(A_ROOT, T1C),
                                        "EVIDENCE-CHAIN.jsonl"))
_a3 = ("PROMOTION-DENY" in _msg and "LOCK-DENY" in _msg
       and _oc.get("outcome") == "NOT-PROMOTED"
       and _lc.get("outcome") == "NOT-LOCKED"
       and _lc.get("reason") == "no-promotion-no-lock"
       and _lc.get("created_from") == "frozen-evidence"
       and _lc.get("promotion_outcome_sha256") == sha_file(_out_p)
       and _lc.get("promotion_cell_id") == PROMC["cell_id"]
       and _lc.get("acquisition_chain_tips") == {"T0": _t0_tip,
                                                 "T1": _t1_tip})
check("A3 ONE advance() records NOT-PROMOTED and completes the "
      "CAPABILITY_LOCK event as NOT-LOCKED (bound to the promotion outcome "
      "sha + the real chain tips), then refuses with the combined terminal "
      "message", _a3, _msg[:220])

_done2 = order.completed_cells(A_ROOT)
_lock_st = order.cell_state(A_ROOT, LOCKC, FREEZE)
_prom_st = order.cell_state(A_ROOT, PROMC, FREEZE)
_t2a = order.cell_state(A_ROOT, T2C, FREEZE)
_t2b = order.cell_state(A_ROOT, T2B, FREEZE)
_a4 = (set(_done2) == {T0C["cell_id"], T1C["cell_id"], PROMC["cell_id"],
                       LOCKC["cell_id"]}
       and _lock_st["status"] == "NOT-LOCKED"
       and _prom_st["status"] == "NOT-PROMOTED"
       and _t2a["status"] == "NOT-EVALUABLE"
       and "acquisition-failed" in " ".join(_t2a["reasons"])
       and _t2b["status"] == "INCOMPLETE")
check("A4 the full prefix walks (T0,T1,PROMOTION/NOT-PROMOTED,"
      "CAPABILITY_LOCK/NOT-LOCKED); the failed universe's downstream cell "
      "is NOT-EVALUABLE while the untouched universe's stays INCOMPLETE",
      _a4, f"done={sorted(_done2)} lock={_lock_st['status']} "
      f"prom={_prom_st['status']} t2A={_t2a['status']} "
      f"t2B={_t2b['status']}")

# A5: the deadlock is gone — and nothing was authorized.
_exp = order.load_expansion(A_ROOT)
_c0 = order.expected_event(_exp, "PQ", "fam05", "T0", "C")
_c_cell, _c_reasons = order.authorize_event(_exp, "PQ", "fam05", "T0", "C",
                                            _done2, fam_c_dir=A_ROOT)
_down_cell, _down_reasons = order.authorize(_exp, "PQ", "fam05", "T2", "P",
                                            "correct", _done2,
                                            fam_c_dir=A_ROOT)
_nolock = not os.path.exists(os.path.join(
    order.capability_dir(A_ROOT, "PQ", "A", "fam05"),
    "CAPABILITY_LOCK.json"))
_noreceipt = not os.path.exists(os.path.join(
    order.run_dir(A_ROOT, PROMC), order.PROMOTION_RECEIPT_FILE))
try:
    promotion.run_evidence(A_ROOT, LOCKC, FREEZE)
    _lock_evidence = "DID NOT REFUSE"
except PermissionError as e:
    _lock_evidence = str(e)
try:
    promotion.lock_universe(A_ROOT, "PQ", "fam05", "A", FREEZE,
                            "harness-validation")
    _lock_mint = "DID NOT REFUSE"
except PermissionError as e:
    _lock_mint = str(e)
try:
    promotion.promote_universe(A_ROOT, "PQ", "fam05", "A", FREEZE,
                               "harness-validation")
    _re_promote = "DID NOT REFUSE"
except PermissionError as e:
    _re_promote = str(e)
_a5 = (_c_cell is not None and not _c_reasons
       and any("ACQUISITION-FAILED-DENY" in r for r in _down_reasons)
       and _nolock and _noreceipt
       and "DID NOT REFUSE" not in (_lock_evidence + _lock_mint + _re_promote)
       and "LOCK-DENY" in _lock_mint
       and "PROMOTION-DENY" in _re_promote)
check("A5 no deadlock (C's T0 is authorized out of the same prefix) and no "
      "authorization leaked: no lock/receipt minted, downstream refused "
      "(ACQUISITION-FAILED-DENY), evidence/lock/re-promotion all refused",
      _a5, f"C-T0={_c_reasons[:1]} downstream={_down_reasons[:1]} "
      f"nolock={_nolock} noreceipt={_noreceipt} "
      f"lockmint={_lock_mint[:80]}")

_before_l = open(_out_l, "rb").read()
_before_p = open(_out_p, "rb").read()
_msg2 = advance_expect_refusal(A_ROOT)
_a6 = ("PROMOTION-DENY" in _msg2 and "terminal state" in _msg2
       and open(_out_l, "rb").read() == _before_l
       and open(_out_p, "rb").read() == _before_p)
check("A6 re-invocation is idempotent: advance() refuses (already at a "
      "validated terminal state) and rewrites nothing", _a6, _msg2[:160])

# ===========================================================================
# B. malformed/forged terminal records fail closed
# ===========================================================================
GOOD_L = open(_out_l).read()
GOOD_P = open(_out_p).read()
LOCK_RUN_DIR = os.path.dirname(_out_l)


def probe_bad():
    st = order.cell_state(A_ROOT, LOCKC, FREEZE)
    done = order.completed_cells(A_ROOT)
    msg = advance_expect_refusal(A_ROOT)
    return st, done, msg


def restore():
    open(_out_l, "w").write(GOOD_L)
    open(_out_p, "w").write(GOOD_P)


bad = json.loads(GOOD_L)
bad["outcome"] = "COMPLETE"
json.dump(bad, open(_out_l, "w"))
_st, _done, _msg = probe_bad()
_b1 = (_st["status"] == "INADMISSIBLE"
       and any("not-locked outcome outcome" in r for r in _st["reasons"])
       and LOCKC["cell_id"] not in _done and "LOCK-DENY" in _msg)
check("B1 tampered outcome field ('COMPLETE') -> INADMISSIBLE and the walk "
      "blocks", _b1, f"{_st['status']} {_st['reasons'][:1]}")
restore()

bad = json.loads(GOOD_L)
bad["acquisition_chain_tips"] = {"T0": "a" * 64, "T1": _t1_tip}
json.dump(bad, open(_out_l, "w"))
_st, _done, _msg = probe_bad()
_b2 = (_st["status"] == "INADMISSIBLE"
       and any("not-locked outcome t0_tip" in r for r in _st["reasons"])
       and LOCKC["cell_id"] not in _done)
check("B2 forged acquisition tips -> INADMISSIBLE and the walk blocks",
      _b2, f"{_st['status']} {_st['reasons'][:1]}")
restore()

json.dump({"cell_id": LOCKC["cell_id"]},
          open(os.path.join(LOCK_RUN_DIR, "H1-RUN-MANIFEST.json"), "w"))
_st, _done, _msg = probe_bad()
_b3 = (_st["status"] == "INADMISSIBLE"
       and any("must not fabricate a model-run" in r for r in _st["reasons"])
       and LOCKC["cell_id"] not in _done)
check("B3 fabricated model-run manifest in the lock cell -> INADMISSIBLE "
      "and the walk blocks", _b3, f"{_st['status']} {_st['reasons'][:1]}")
os.unlink(os.path.join(LOCK_RUN_DIR, "H1-RUN-MANIFEST.json"))
restore()

bad = json.loads(GOOD_P)
bad["reason"] = "forged"
json.dump(bad, open(_out_p, "w"))
_st, _done, _msg = probe_bad()
_pst = order.cell_state(A_ROOT, PROMC, FREEZE)
_b4 = (_pst["status"] == "INADMISSIBLE"
       and _st["status"] == "INADMISSIBLE"
       and LOCKC["cell_id"] not in _done
       and PROMC["cell_id"] not in _done)
check("B4 tampered PROMOTION-OUTCOME.json bytes -> the PROMOTION cell is "
      "INADMISSIBLE, the lock cell blocks (its bound sha no longer "
      "matches)", _b4, f"prom={_pst['status']} lock={_st['status']} "
      f"{_st['reasons'][:1]}")
restore()

_capdir = order.ensure_namespace(A_ROOT, "PQ", "A", "fam05",
                                 tail=("capability",))
json.dump({"capability_id": "fam05-PQ-A-K", "fake": True},
          open(os.path.join(_capdir, "CAPABILITY_LOCK.json"), "w"))
_st, _done, _msg = probe_bad()
_b5 = (_st["status"] == "INADMISSIBLE"
       and any("CAPABILITY_LOCK exists" in r for r in _st["reasons"])
       and LOCKC["cell_id"] not in _done and "LOCK-DENY" in _msg)
check("B5 a real CAPABILITY_LOCK.json beside the NOT-LOCKED outcome -> "
      "refused (mutually exclusive) and the walk blocks",
      _b5, f"{_st['status']} {_st['reasons'][:1]}")
os.unlink(os.path.join(_capdir, "CAPABILITY_LOCK.json"))
restore()
_st, _done, _msg = probe_bad()
check("B6 restored fixture walks again (terminal algebra stable under "
      "mutation/restore cycles)", _st["status"] == "NOT-LOCKED"
      and LOCKC["cell_id"] in _done, _st["status"])

# ===========================================================================
# C. epoch-2 lineage
# ===========================================================================
# --- C1: activation + state prefixing + epoch-1 evidence never scanned ----
C_ROOT = hermetic_root("c1")
CT0 = cell_for(C_ROOT, "T0")
build_model_run(C_ROOT, cell=CT0, freeze_commit=FREEZE, solver_py=CAND_T0)
_epoch1_done = order.completed_cells(C_ROOT)
# a stray capability dir in the EPOCH-1 tree (must never be walked in
# epoch 2) and one under the epoch-2 root (must be reported)
_e1_stray = os.path.join(order.state_dir(C_ROOT, "PQ", "A", "fam05"),
                         "capability")
os.makedirs(_e1_stray, exist_ok=True)
os.chmod(_e1_stray, 0o755)
_cp = os.path.join(C_ROOT, EPOCH.EPOCH1_CLOSURE_FILE)
_rec = {
    "transition": "epoch-1-to-epoch-2",
    "epoch_id": EPOCH.EPOCH_ID, "from_epoch": 1, "to_epoch": 2,
    "ruling": "EPOCH-1-CLOSURE.md (third-party ruling): EPOCH-2 PROTOCOL + "
              "TERMINAL-OUTCOME PROGRESS SEMANTICS",
    "epoch1_closure_record": EPOCH.EPOCH1_CLOSURE_FILE,
    "closure_record_sha256": sha_file(_cp),
    "epoch1_execution_lock_sha256": EPOCH.EPOCH1_EXECUTION_LOCK_SHA256,
    "epoch1_protocol_lock_sha256": EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256,
    "epoch1_finalization_commit": EPOCH.EPOCH1_FINALIZATION_COMMIT,
    "epoch1_certification_ref": EPOCH.EPOCH1_CERTIFICATION_REF,
    "state_prefix": EPOCH.STATE_PREFIX,
    "execution_lock": EPOCH.EXECUTION_LOCK_FILE,
    "protocol_lock": EPOCH.PROTOCOL_LOCK_FILE,
    "genesis": {fn: sha_file(os.path.join(C_ROOT, fn))
                for fn in PF.PROTOCOL_GOVERNED},
    "created_at": "2026-09-17T00:00:00Z",
    "created_from": "frozen-evidence (epoch-1 closure record)",
}
json.dump(_rec, open(EPOCH.transition_path(C_ROOT), "w"), indent=1)
_act = EPOCH.is_epoch2(C_ROOT)
_e2_done = order.completed_cells(C_ROOT)
_t0_epoch2 = order.cell_state(C_ROOT, CT0, FREEZE)
_want_run_dir = os.path.join(C_ROOT, "state", "epoch2", "PQ", "A", "fam05",
                             "runs", CT0["cell_id"])
_e2_strays = __import__("specificity")._stray_capability_dirs(C_ROOT, set())
_e2_stray_path = os.path.join(C_ROOT, "state", "epoch2", "PQ", "A", "fam05",
                              "capability")
os.makedirs(_e2_stray_path, exist_ok=True)
os.chmod(_e2_stray_path, 0o755)
_e2_strays2 = __import__("specificity")._stray_capability_dirs(C_ROOT, set())
_c1 = (_act and EPOCH.state_root(C_ROOT) == os.path.join(C_ROOT, "state",
                                                         "epoch2")
       and order.run_dir(C_ROOT, CT0) == _want_run_dir
       and len(_epoch1_done) == 1 and _e2_done == {}
       and _t0_epoch2["status"] == "INCOMPLETE"
       and _e1_stray not in _e2_strays
       and any(_e2_stray_path == p for p in _e2_strays2))
check("C1 a valid transition record activates epoch 2: namespaces prefix "
      "under state/epoch2/, the COMPLETED epoch-1 cell is never scanned "
      "(walk empty, cell INCOMPLETE), and the stray walk is scoped to the "
      "epoch-2 root", _c1, f"active={_act} e1_done={len(_epoch1_done)} "
      f"e2_done={_e2_done} t0={_t0_epoch2['status']} "
      f"strays={_e2_strays}")

_f = EPOCH.validate_record(C_ROOT)
_bad_rec = dict(_rec, closure_record_sha256="0" * 64)
json.dump(_bad_rec, open(EPOCH.transition_path(C_ROOT), "w"), indent=1)
_f_bad = EPOCH.validate_record(C_ROOT)
_c1b = (_f == [] and _f_bad != []
        and EPOCH.is_epoch2(C_ROOT) is False)
check("C1b the record's closure citation is enforced: a forged "
      "closure_record_sha256 de-activates epoch 2 and is named",
      _c1b, f"good={_f[:1]} bad={_f_bad[:1]}")
json.dump(_rec, open(EPOCH.transition_path(C_ROOT), "w"), indent=1)

# --- C2: the real transition on a disposable git worktree ----------------
WT = tempfile.mkdtemp(prefix="h37-wt-")
os.rmdir(WT)
WBASE = os.path.join(WT, "benchmarks", "fam-c")
WRA = None
# The rehearsal must START from a pre-transition tree: if the live HEAD
# already carries the epoch-2 transition (this slice applies it), anchor
# the disposable worktree at the commit that ADDED the record — the last
# untransitioned state — so --check/--transition are exercised for real.
_wt_anchor = "HEAD"
try:
    _add = subprocess.run(
        ["git", "-C", REPO, "log", "--format=%H", "--diff-filter=A", "--",
         "benchmarks/fam-c/" + EPOCH.TRANSITION_FILE],
        capture_output=True, text=True, check=True).stdout.split()
    if _add:
        _wt_anchor = subprocess.run(
            ["git", "-C", REPO, "rev-parse", _add[-1] + "^"],
            capture_output=True, text=True, check=True).stdout.strip()
except (subprocess.CalledProcessError, OSError):
    _wt_anchor = "HEAD"
try:
    subprocess.run(["git", "-C", REPO, "worktree", "add", "--detach", WT,
                    _wt_anchor], capture_output=True, text=True, check=True)
    if HARNESS not in sys.path:
        sys.path.insert(0, HARNESS)
    import importlib
    WRA = importlib.import_module("run_arm_h1")
    _env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def wrun(args, cwd=WT):
        return subprocess.run([sys.executable] + args, cwd=cwd, env=_env,
                              capture_output=True, text=True)

    _chk = wrun(["harness/epoch_transition.py", "--check"])
    _c2a = (_chk.returncode == 0 and "epoch 1" in _chk.stdout)
    check("C2a --check on an untransitioned tree reports epoch 1",
          _c2a, _chk.stdout.strip()[:160])

    _elp = os.path.join(WBASE, "EXECUTION-LOCK.json")
    _el_bytes = open(_elp, "rb").read()
    open(_elp, "wb").write(_el_bytes.replace(b'"FINAL"', b'"XINAL"', 1))
    _drift = wrun(["harness/epoch_transition.py", "--transition",
                   "--reason", "h37 drift probe"])
    open(_elp, "wb").write(_el_bytes)
    _c2b = (_drift.returncode != 0
            and "EPOCH-2-TRANSITION-REFUSED" in _drift.stdout + _drift.stderr
            and not os.path.exists(EPOCH.transition_path(WBASE)))
    check("C2b a drifted epoch-1 lock refuses the transition (no record "
          "written)", _c2b,
          (_drift.stdout + _drift.stderr)[:200])

    _tr = wrun(["harness/epoch_transition.py", "--transition",
                "--reason", "h37 rehearsal of the EPOCH-2 transition"])
    _rec2 = (json.load(open(EPOCH.transition_path(WBASE)))
             if os.path.exists(EPOCH.transition_path(WBASE)) else {})
    _el2 = (json.load(open(os.path.join(WBASE, EPOCH.EXECUTION_LOCK_FILE)))
            if os.path.exists(os.path.join(WBASE,
                                           EPOCH.EXECUTION_LOCK_FILE))
            else {})
    _pl2 = (json.load(open(os.path.join(WBASE, EPOCH.PROTOCOL_LOCK_FILE)))
            if os.path.exists(os.path.join(WBASE,
                                           EPOCH.PROTOCOL_LOCK_FILE))
            else {})
    _c2c = (_tr.returncode == 0
            and _rec2.get("to_epoch") == 2
            and _rec2.get("closure_record_sha256")
            == sha_file(os.path.join(WBASE, EPOCH.EPOCH1_CLOSURE_FILE))
            and _rec2.get("epoch1_execution_lock_sha256")
            == EPOCH.EPOCH1_EXECUTION_LOCK_SHA256
            and _rec2.get("epoch1_protocol_lock_sha256")
            == EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256
            and _el2.get("epoch") == 2 and _pl2.get("epoch") == 2
            and _el2.get("amendments") == [] and _pl2.get("amendments") == []
            and _el2.get("status") == "open-round2"
            and _pl2.get("status") == "living-lock"
            and _el2.get("transition", {}).get("record_sha256")
            == sha_file(EPOCH.transition_path(WBASE))
            and "harness/epoch.py" in _el2.get("harness_files", {})
            and "harness/epoch_transition.py"
            in _el2.get("harness_files", {})
            and _pl2.get("governed") == _rec2.get("genesis")
            and "ORDER-EXPANSION.json" in _pl2.get("protocol_artifacts", {}))
    check("C2c the real transition mints the fresh epoch-2 locks (epoch: 2, "
          "transition citation, their OWN empty amendment lineage, "
          "ORDER-EXPANSION pin, full harness coverage)", _c2c,
          f"rc={_tr.returncode} out={(_tr.stdout + _tr.stderr)[-200:]}")

    _pf = PF.validate_all(WBASE)
    _c2d = (_pf == [])
    check("C2d preflight.validate_all is GREEN under epoch 2 (epoch-2 "
          "locks are the live authority; epoch-1 lock bytes/status checked "
          "as historical records)", _c2d, str(_pf[:2])[:300])

    subprocess.run(["git", "-C", WT, "-c", "user.name=h37",
                    "-c", "user.email=h37@local", "add", "-A"],
                   capture_output=True, check=True)
    subprocess.run(["git", "-C", WT, "-c", "user.name=h37",
                    "-c", "user.email=h37@local", "commit", "-m",
                    "h37 epoch-2 transition rehearsal", "--no-gpg-sign"],
                   capture_output=True, check=True)
    _pf2 = PF.validate_all(WBASE)
    _auth = PF._lock_authority_findings(WBASE, EPOCH.PROTOCOL_LOCK_FILE)
    _c2e = (_pf2 == [] and _auth == [])
    check("C2e after committing the fresh files the epoch-2 lock's byte "
          "authority holds (committed experiment-HEAD bytes) and V2 stays "
          "green", _c2e, f"pf={str(_pf2[:2])[:200]} auth={_auth[:1]}")

    _head_w0 = subprocess.run(["git", "-C", WT, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    _gate = WRA.final_lock_gate(WBASE, exec_sha=_head_w0)
    _c2f = (any(EPOCH.EXECUTION_LOCK_FILE in f for f in _gate)
            and any(EPOCH.PROTOCOL_LOCK_FILE in f for f in _gate)
            and any("LOCK-NOT-FINAL" in f for f in _gate)
            and not any(f for f in _gate if "LOCK-DESCENT" in f))
    check("C2f the runner FINAL gate refuses the wired estimand surface "
          "naming the OPEN epoch-2 locks (epoch-1 FINAL locks authorize "
          "nothing)", _c2f, str(_gate[:2])[:300])

    _mint_chk = wrun(["harness/mint_execution_lock.py", "--check"])
    _c2g = (_mint_chk.returncode == 0 and "current" in _mint_chk.stdout)
    check("C2g the mint tool is epoch-aware: --check targets the ACTIVE "
          "epoch-2 execution lock and reports it current", _c2g,
          _mint_chk.stdout.strip()[:160])

    _fin = wrun(["harness/mint_execution_lock.py", "--finalize",
                 "--slice", "h37", "--reason",
                 "h37 rehearsal: epoch-2 execution authority terminal"])
    _el3 = json.load(open(os.path.join(WBASE, EPOCH.EXECUTION_LOCK_FILE)))
    _head_w = subprocess.run(["git", "-C", WT, "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    _c2h = (_fin.returncode == 0 and _el3.get("status") == "FINAL"
            and _el3.get("finalization_commit") == _head_w
            and _el3.get("amendments")
            and _el3["amendments"][-1].get("status_after") == "FINAL")
    check("C2h the standard lifecycle continues on the epoch-2 lineage: "
          "--finalize seals the epoch-2 execution lock (terminal amendment, "
          "finalization_commit = worktree HEAD)", _c2h,
          f"rc={_fin.returncode} {(_fin.stdout + _fin.stderr)[-160:]}")

    # manual PROTOCOL finalization of the epoch-2 lock (documented flow)
    _plp = os.path.join(WBASE, EPOCH.PROTOCOL_LOCK_FILE)
    _pl3 = json.load(open(_plp))
    _pl3["status"] = "FINAL"
    _pl3["finalized_at"] = "2026-09-17T00:00:00Z"
    _pl3["finalization_commit"] = _head_w
    _pl3["finalized_amendment_count"] = len(_pl3.get("amendments") or [])
    json.dump(_pl3, open(_plp, "w"), indent=1)
    subprocess.run(["git", "-C", WT, "-c", "user.name=h37",
                    "-c", "user.email=h37@local", "add", "-A"],
                   capture_output=True, check=True)
    subprocess.run(["git", "-C", WT, "-c", "user.name=h37",
                    "-c", "user.email=h37@local", "commit", "-m",
                    "h37 epoch-2 protocol finalization (fixture)",
                    "--no-gpg-sign"], capture_output=True, check=True)
    _pf3 = PF.validate_all(WBASE)
    _gate2 = WRA.final_lock_gate(WBASE, exec_sha=_head_w)
    _c2i = (_pf3 == [] and _gate2 == [])
    check("C2i after BOTH epoch-2 authorities are final (fixture), "
          "preflight is green and the FINAL gate is green — the normal "
          "finalize path is fully exercised under epoch 2", _c2i,
          f"pf={str(_pf3[:2])[:200]} gate={str(_gate2[:1])[:160]}")

    _tampered = json.load(open(os.path.join(WBASE,
                                            EPOCH.EXECUTION_LOCK_FILE)))
    _tampered["harness_files"]["harness/epoch.py"] = "0" * 64
    json.dump(_tampered, open(os.path.join(WBASE,
                                           EPOCH.EXECUTION_LOCK_FILE), "w"),
              indent=1)
    _f3 = PF.validate_execution(WBASE)
    _c2j = any("harness/epoch.py" in f and "harness bytes changed" in f
               for f in _f3)
    check("C2j the epoch-2 execution authority still fails closed on "
          "drifted harness bytes (byte-for-byte rule preserved)",
          _c2j, str(_f3[:2])[:200])
finally:
    subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force",
                    WT], capture_output=True, text=True)

# ===========================================================================
# D. algebra table + no-conversion guard
# ===========================================================================
_models = (cell_for(A_ROOT, "T3"), cell_for(A_ROOT, "T4"))
_pairs = []
for c in _models + (PROMC, LOCKC, T2C, T2B):
    _pairs.append((c, "INCOMPLETE"))
    _pairs.append((c, "INADMISSIBLE"))
_pairs += [(c, "COMPLETE") for c in (PROMC, LOCKC, T2C, T2B)]
_pairs += [(PROMC, "NOT-PROMOTED"), (PROMC, "NOT-LOCKED"),
           (PROMC, "NOT-EVALUABLE"), (LOCKC, "NOT-LOCKED"),
           (LOCKC, "NOT-PROMOTED"), (T2C, "NOT-EVALUABLE"),
           (T2B, "NOT-EVALUABLE"), (cell_for(A_ROOT, "T0"), "NOT-EVALUABLE"),
           (cell_for(A_ROOT, "T0"), "NOT-PROMOTED"),
           (cell_for(A_ROOT, "T0"), "NOT-LOCKED")]
_expect = {"COMPLETE": {"COMPLETE"},
           "PROMOTION": {"COMPLETE", "NOT-PROMOTED"},
           "CAPABILITY_LOCK": {"COMPLETE", "NOT-LOCKED"},
           "downstream-cap": {"COMPLETE", "NOT-EVALUABLE"},
           "model": {"COMPLETE"}}
_d_ok = True
_bad_pairs = []
for _c, _s in _pairs:
    if _s in ("INCOMPLETE", "INADMISSIBLE"):
        _want = False
    elif _s == "COMPLETE":
        _want = True
    elif _c["event"] == "PROMOTION":
        _want = _s == "NOT-PROMOTED"
    elif _c["event"] == "CAPABILITY_LOCK":
        _want = _s == "NOT-LOCKED"
    elif _c["event"] in order.DOWNSTREAM_EVENTS:
        _want = (_s == "NOT-EVALUABLE"
                 and _c["universe"] in order.CAPABILITY_UNIVERSES)
    else:
        _want = False
    _got = order.progress_valid(_c, _s)
    if _got is not _want:
        _d_ok = False
        _bad_pairs.append((_c["event"], _c["universe"], _s, _got, _want))
check("D1 event-specific progress algebra table (INCOMPLETE/INADMISSIBLE "
      "never progress; non-COMPLETE terminals only on their own event)",
      _d_ok and not _bad_pairs, str(_bad_pairs[:3]))

try:
    promotion.run_evidence(A_ROOT, PROMC, FREEZE)
    _conv1 = "DID NOT REFUSE"
except PermissionError as e:
    _conv1 = str(e)
_conv2 = json.load(open(_out_l)).get("outcome") != "COMPLETE"
_conv3 = order.cell_state(A_ROOT, PROMC, FREEZE)["status"] == "NOT-PROMOTED"
try:
    order.emit_capability_lock(A_ROOT, LOCKC)
    _conv4 = "DID NOT REFUSE"
except (PermissionError, ValueError) as e:
    _conv4 = str(e)
check("D2 no non-COMPLETE terminal converts to COMPLETE or is consumed as "
      "one (run_evidence refuses NOT-PROMOTED; the record is still "
      "NOT-PROMOTED after every probe; lock minting refuses without a "
      "validated promotion)",
      "DID NOT REFUSE" not in (_conv1 + _conv4) and _conv2 and _conv3,
      f"evidence={_conv1[:100]} mint={_conv4[:100]}")

bad = [n for n, ok in RESULTS if not ok]
print(f"\nH37 epoch-2 semantics smoke: {len(RESULTS) - len(bad)}/"
      f"{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

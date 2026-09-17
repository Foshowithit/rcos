#!/usr/bin/env python3
"""H36 FINAL-lock smoke — A16 FINAL-lock semantics (audit round-3 item 4;
A11b P0-5).

The Round-3 audit required a true terminal state for BOTH lock
authorities: status FINAL with the finalization stamp + commit recorded,
amendments forbidden past it, the runner refusing a non-FINAL lock on the
wired estimand surface, and the first estimand run descending from the
finalization commit ("no 'add amendment and keep going' path exists in
the same experimental epoch"). A16 lands that MECHANISM with the locks
still open; this suite proves every refusal and every acceptance of the
new machinery against a disposable git worktree of THIS checkout:

  A. pre-FINAL: the runner's final_lock_gate names BOTH open locks
     (LOCK-NOT-FINAL) and production main() refuses the wired estimand
     cell BEFORE any model call (counting transport stays at zero; no
     estimand namespace is created);
  B. terminal transition: the real mint tool --finalize records
     status/finalized_at/finalization_commit + the terminal amendment,
     and EVERY further mint/finalize is refused
     (EXECUTION-LOCK-FINAL-REFUSED) — even with drifted bytes on disk
     (a FINAL lock never re-mints);
  C. both-locks rule: with EXECUTION-LOCK FINAL but PROTOCOL-LOCK still
     living, the gate still refuses naming PROTOCOL-LOCK; after the
     documented manual protocol finalization the gate is GREEN (the
     production call shape final_lock_gate(BASE) — main() itself never
     reaches a provider here);
  D. descent: the gate accepts the finalization commit itself (equal)
     and refuses a fabricated sha, a real orphan commit, and an earlier
     ancestor commit (LOCK-DESCENT-REFUSED — a post-FINAL estimand cell
     cannot run from harness bytes outside the finalized lineage);
  E. validator symmetry: preflight ACCEPTS the finalized execution lock
     (green validate_execution on the worktree, ancestry included) and
     REFUSES, by name, amendments past FINAL (both authorities), a
     reopened terminal lock, FINAL records missing their stamp/commit/
     pin, finalization fields under a non-FINAL status, and drifted /
     missing / unknown protocol-artifact pins.

No network, no provider call, no docker: the transport leg is a counting
stub that must stay at zero, the protocol finalization is the documented
fixture JSON edit on the disposable worktree, and everything else is the
real committed machinery. Exit 0 only if every probe is green.
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
REPO = ROOT
FAMC = os.path.join(ROOT, "benchmarks", "fam-c")
WT = tempfile.mkdtemp(prefix="h36-wt-")  # git worktree add needs it gone
os.rmdir(WT)
sys.path.insert(0, HARNESS)
sys.path.insert(0, FAMC)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


def sh(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p


import preflight as PF  # noqa: E402  (real repo validator under test)

# A0: the real three-authority preflight is green in this checkout —
# the probes below would otherwise be indistinguishable from lock rot.
check("A0 real three-authority preflight is green in this checkout",
      PF.validate_all(FAMC) == [], str(PF.validate_all(FAMC))[:200])
# A0b (final epoch): on a FINAL repo the LIVE gate must PASS for a
# descent-valid tree — the positive counterpart of the refusal proofs
# below (which run against the open fixture worktree). EPOCH-2
# (EPOCH-1-CLOSURE.md): once the explicit transition record exists the
# ACTIVE authorities are the fresh epoch-2 locks; a live gate probe then
# PASSES only when BOTH of them are FINAL — while they are submitted OPEN
# (the owner finalizes later) the correct live answer is the named
# LOCK-NOT-FINAL refusal naming the epoch-2 lock. Both shapes are proved
# here against whichever epoch the checkout is in.
import epoch as _EP  # noqa: E402  (active-epoch lock resolution)
_act_locks = _EP.active_lock_names(FAMC)
try:
    _act_states = [json.load(open(os.path.join(FAMC, n))).get("status")
                   for n in _act_locks]
except (OSError, ValueError):
    _act_states = []
_probe = (
    "import sys; sys.path.insert(0, %r); import run_arm_h1 as RA; "
    "print(RA.final_lock_gate(%r))" % (
        os.path.join(FAMC, "harness-run"), FAMC))
_pr = subprocess.run([sys.executable, "-c", _probe], capture_output=True,
                     text=True)
if _act_states == ["FINAL", "FINAL"]:
    check("A0b live post-FINAL gate PASSES on the real tree (descent-valid)",
          _pr.returncode == 0 and _pr.stdout.strip() == "[]",
          (_pr.stdout + _pr.stderr)[:200])
else:
    _live_gate = _pr.stdout.strip()
    check("A0b live gate REFUSES the OPEN active-epoch locks (LOCK-NOT-FINAL, "
          "naming them) — the epoch-1 FINAL locks authorize nothing under "
          "epoch 2",
          _pr.returncode == 0 and "LOCK-NOT-FINAL" in _live_gate
          and all(n in _live_gate for n in _act_locks),
          (_pr.stdout + _pr.stderr)[:240])

# ---------------------------------------------------------------- surface
# One disposable git worktree: real git history for the ancestry checks,
# real locks for the gates, all writes land in the worktree. EPOCH-AWARE
# (Round-6 finalization): the A/B arc exercises the OPEN -> FINAL
# transition, so when the real repo HEAD is already FINAL the fixture is
# anchored at the recorded finalization_commit — the last OPEN state —
# keeping every refusal proof intact. On an OPEN-HEAD repo the fixture
# anchors at HEAD exactly as before.
_real_el = json.load(open(os.path.join(FAMC, "EXECUTION-LOCK.json")))
_anchor = "HEAD"
if _real_el.get("status") == "FINAL":
    _anchor = _real_el["finalization_commit"]
p = sh(["git", "-C", REPO, "worktree", "add", "--detach", WT, _anchor])
assert p.returncode == 0, p.stderr
import atexit  # noqa: E402  (cleanup on ANY exit path, incl. refusal)
_CLEANUP_DIRS = []


def _h36_cleanup():
    sh(["git", "-C", REPO, "worktree", "remove", "--force", WT])
    for _d in _CLEANUP_DIRS:
        shutil.rmtree(_d, ignore_errors=True)


atexit.register(_h36_cleanup)
WBASE = os.path.join(WT, "benchmarks", "fam-c")
WHEAD = sh(["git", "-C", WT, "rev-parse", "HEAD"]).stdout.strip()
FREEZE = json.load(open(os.path.join(WBASE, "FREEZE.json")))[
    "freeze_commit"]
MINT = os.path.join(WT, "harness", "mint_execution_lock.py")

# Load the RUNNER from the worktree (the code under test), with real
# preflight — no stubs: this suite owns the live FINAL-lock gate.
for _p in (os.path.join(WT, "harness"),
           os.path.join(WBASE, "harness-run"), WBASE):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
for _name in ("run_arm_h1", "usage", "order", "identity", "chain", "lock",
              "seal", "dockersandbox", "admissibility", "reuse_log",
              "preflight", "promotion", "symmetry", "frozen_visible"):
    sys.modules.pop(_name, None)
import run_arm_h1 as WRA  # noqa: E402
import usage as WUSAGE  # noqa: E402
import order as WORDER  # noqa: E402
WRA.BASE = WBASE
WRA.ROOT = WT
WRA.HARNESS = os.path.join(WT, "harness")

# Counting transport: must stay at ZERO across every main() probe.
_calls = []


class _FakeResp:
    status = 200

    def __init__(self, b):
        self._b = b

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _counting_urlopen(req, timeout=None):
    _calls.append(req.full_url)
    return _FakeResp(b"{}")


WUSAGE.urllib.request.urlopen = _counting_urlopen


def _raises(fn, *tokens):
    try:
        fn()
    except BaseException as e:  # SystemExit is the CLI refusal path
        msg = f"{type(e).__name__}: {e}"
        return all(t in msg for t in tokens), msg[:260]
    return False, "no refusal"


# ------------------------------------------------- A: pre-FINAL refusals
_wexp = WORDER.load_expansion(WBASE)
_wcell, _wf = WORDER.authorize_event(_wexp, "PQ", "fam05", "T0", "A", {})
check("A1 cell 0 (PQ/fam05/T0/A) is authorized on the pristine worktree",
      _wf == [] and _wcell["index"] == 0, str(_wf)[:160])
_wrun = WORDER.run_dir(WBASE, _wcell)
_WOPTS = {"block": "PQ", "wire": True, "acquisition_event": "T0",
          "acquisition_universe": "A"}

_gate = WRA.final_lock_gate(WBASE)
check("A2 gate refuses pre-FINAL naming BOTH open locks (LOCK-NOT-FINAL)",
      len(_gate) == 2
      and all("LOCK-NOT-FINAL" in f for f in _gate)
      and any("EXECUTION-LOCK.json" in f for f in _gate)
      and any("PROTOCOL-LOCK.json" in f for f in _gate), str(_gate)[:240])

ok, why = _raises(lambda: WRA.main("P", "fam05", "T0", "acquisition",
                                   _wrun, None, dict(_WOPTS)),
                  "FINAL-LOCK-GATE refuse start", "LOCK-NOT-FINAL")
check("A3 production main() refuses the wired estimand cell pre-FINAL",
      ok, why)
check("A4 MODEL_CALL_COUNT == 0 (the refusal precedes any provider leg)",
      len(_calls) == 0, f"calls={len(_calls)}")
check("A5 no estimand namespace was created (refuse-START, not "
      "refuse-after-write)", not os.path.exists(_wrun), _wrun)
check("A6 the refusal is the FINAL gate, not lock rot (real preflight "
      "was green)", "PREFLIGHT-LOCK-FAIL" not in why, why[:160])

# ------------------------------------- B: terminal transition + refusals
check("B1 mint --check is current on the pristine worktree",
      sh([sys.executable, MINT, "--check"]).returncode == 0)
_fin = sh([sys.executable, MINT, "--finalize", "--slice", "h36-fixture",
           "--reason", "H36 fixture finalization (disposable worktree)"])
check("B2 --finalize exits zero and records the terminal state",
      _fin.returncode == 0 and "FINALIZED" in _fin.stdout, _fin.stdout[:160])
_el = json.load(open(os.path.join(WBASE, "EXECUTION-LOCK.json")))
_am = _el["amendments"]
check("B3 EXECUTION-LOCK is FINAL with UTC stamp + the worktree HEAD",
      _el.get("status") == "FINAL"
      and isinstance(_el.get("finalized_at"), str)
      and len(_el.get("finalization_commit") or "") == 40
      and _el["finalization_commit"] == WHEAD,
      f"{_el.get('status')}/{_el.get('finalization_commit', '')[:12]}")
check("B4 the terminal amendment is the LAST amendment with an empty "
      "file map (finalization pins the recorded bytes)",
      _am[-1].get("status_after") == "FINAL"
      and _am[-1].get("files") == {}
      and not [a for a in _am if a.get("status_after") == "FINAL"][:-1],
      str(_am[-1]))
_mint_again = sh([sys.executable, MINT, "--slice", "h36", "--reason",
                  "post-FINAL mint"])
check("B5 a further plain mint is refused (EXECUTION-LOCK-FINAL-REFUSED) "
      "even with no byte drift",
      _mint_again.returncode == 1
      and "EXECUTION-LOCK-FINAL-REFUSED" in _mint_again.stdout,
      _mint_again.stdout[:160])
check("B6 a second --finalize is refused",
      "EXECUTION-LOCK-FINAL-REFUSED" in sh(
          [sys.executable, MINT, "--finalize", "--slice", "h36",
           "--reason", "again"]).stdout)
_usage_copy = open(os.path.join(WT, "harness", "usage.py"), "rb").read()
with open(os.path.join(WT, "harness", "usage.py"), "ab") as f:
    f.write(b"\n# h36 drift probe\n")
_drift = sh([sys.executable, MINT, "--slice", "h36", "--reason",
             "drifted bytes post-FINAL"])
with open(os.path.join(WT, "harness", "usage.py"), "wb") as f:
    f.write(_usage_copy)
check("B7 drifted harness bytes post-FINAL never re-mint (refused "
      "FINAL, not silently re-recorded)",
      _drift.returncode == 1
      and "EXECUTION-LOCK-FINAL-REFUSED" in _drift.stdout,
      _drift.stdout[:160])

# --------------------------------------- C: both-locks rule + green gate
_gate = WRA.final_lock_gate(WBASE)
check("C1 with EXECUTION-LOCK FINAL but PROTOCOL-LOCK living the gate "
      "still refuses, naming only the protocol lock",
      len(_gate) == 1 and "LOCK-NOT-FINAL" in _gate[0]
      and "PROTOCOL-LOCK.json" in _gate[0], str(_gate)[:200])
_pl = json.load(open(os.path.join(WBASE, "PROTOCOL-LOCK.json")))
_pl["status"] = "FINAL"
_pl["finalized_at"] = _el["finalized_at"]
_pl["finalization_commit"] = WHEAD
_pl["finalized_amendment_count"] = len(_pl["amendments"])
with open(os.path.join(WBASE, "PROTOCOL-LOCK.json"), "w") as f:
    json.dump(_pl, f, indent=1)
    f.write("\n")
check("C2 after BOTH locks are FINAL the production gate call is green "
      "(descent: run commit == finalization commit)",
      WRA.final_lock_gate(WBASE) == [],
      str(WRA.final_lock_gate(WBASE))[:200])

# ------------------------------------------------------- D: descent rule
check("D1 descent refuses a fabricated 40-hex commit (LOCK-DESCENT-"
      "REFUSED, fail closed on unresolvable shas)",
      any("LOCK-DESCENT-REFUSED" in f
          for f in WRA.final_lock_gate(WBASE, exec_sha="b" * 40)))
_orph = sh(["git", "-C", WT, "commit-tree", "HEAD^{tree}"],
           input="h36 orphan fixture\n",
           env=dict(os.environ, GIT_AUTHOR_NAME="h36",
                    GIT_AUTHOR_EMAIL="h36@fixture",
                    GIT_COMMITTER_NAME="h36",
                    GIT_COMMITTER_EMAIL="h36@fixture"))
_orphan = _orph.stdout.strip()
check("D2 descent refuses a real off-lineage commit (orphan commit-tree)",
      _orph.returncode == 0 and len(_orphan) == 40
      and any("LOCK-DESCENT-REFUSED" in f
              for f in WRA.final_lock_gate(WBASE, exec_sha=_orphan)),
      _orphan[:12])
check("D3 descent refuses an EARLIER ancestor commit (a post-FINAL cell "
      "cannot run from pre-finalization harness bytes)",
      any("LOCK-DESCENT-REFUSED" in f
          for f in WRA.final_lock_gate(WBASE, exec_sha=FREEZE)))

# --------------------------- E: validator symmetry (preflight under test)
check("E1 preflight validate_execution ACCEPTS the finalized worktree "
      "lock (bytes current, FINAL shape, ancestry of HEAD)",
      PF.validate_execution(WBASE) == [],
      str(PF.validate_execution(WBASE))[:240])
_wel = json.load(open(os.path.join(WBASE, "EXECUTION-LOCK.json")))


def _mut(base, **kw):
    d = json.loads(json.dumps(base))
    d.update(kw)
    return d


_post = _mut(_wel, amendments=_wel["amendments"] + [dict(
    _wel["amendments"][-1], status_after="open-round2")])
check("E2 validator refuses an amendment appended past FINAL (execution)",
      any("past FINAL" in f
          for f in PF.validate_execution_final(_post)))
check("E3 validator refuses reopening a terminal lock (terminal "
      "amendment under an open status)",
      any("cannot be reopened" in f for f in PF.validate_execution_final(
          _mut(_wel, status="open-round2"))))
check("E4 validator refuses a FINAL execution lock missing finalized_at",
      any("finalized_at" in f for f in PF.validate_execution_final(
          {k: v for k, v in _wel.items() if k != "finalized_at"})))
check("E5 validator refuses a FINAL execution lock missing "
      "finalization_commit",
      any("finalization_commit" in f for f in PF.validate_execution_final(
          {k: v for k, v in _wel.items() if k != "finalization_commit"})))
check("E6 validator ACCEPTS the finalized protocol lock (pure FINAL "
      "state, count marker, pin present)",
      PF.validate_protocol_final(_pl) == [],
      str(PF.validate_protocol_final(_pl))[:200])
check("E7 validator refuses amendments past FINAL via the recorded count "
      "(protocol)",
      any("past FINAL" in f for f in PF.validate_protocol_final(
          _mut(_pl, finalized_amendment_count=len(_pl["amendments"]) - 1))))
check("E8 validator refuses a FINAL protocol lock without the "
      "ORDER-EXPANSION.json pin (A11b P0-5)",
      any("protocol-artifact pin" in f for f in PF.validate_protocol_final(
          {k: v for k, v in _pl.items() if k != "protocol_artifacts"})))
check("E9 validator refuses finalization fields under a non-FINAL status "
      "(inconsistent terminal state)",
      any("inconsistent terminal state" in f for f in
          PF.validate_protocol_final(
              _mut(_pl, status="living-lock"))))
_pin = _pl["protocol_artifacts"]["ORDER-EXPANSION.json"]
check("E10 validator accepts the recorded pin against the live "
      "ORDER-EXPANSION.json bytes",
      PF.validate_protocol_artifact_pin(
          {"protocol_artifacts": {"ORDER-EXPANSION.json": _pin}},
          WBASE) == [])
_tmp = tempfile.mkdtemp(prefix="h36-pin-")
_CLEANUP_DIRS.append(_tmp)
shutil.copy2(os.path.join(FAMC, "ORDER-EXPANSION.json"),
             os.path.join(_tmp, "ORDER-EXPANSION.json"))
with open(os.path.join(_tmp, "ORDER-EXPANSION.json"), "ab") as f:
    f.write(b" ")
check("E11 validator refuses a DRIFTED protocol artifact pin",
      any("drifted" in f for f in PF.validate_protocol_artifact_pin(
          {"protocol_artifacts": {"ORDER-EXPANSION.json": _pin}}, _tmp)))
check("E12 validator refuses a MISSING pinned artifact and an UNKNOWN "
      "pinned name",
      any("missing" in f for f in PF.validate_protocol_artifact_pin(
          {"protocol_artifacts": {"ORDER-EXPANSION.json": _pin}},
          _tmp + "/absent"))
      and any("unknown artifact" in f for f in
              PF.validate_protocol_artifact_pin(
                  {"protocol_artifacts": {"TYPO.md": _pin}}, _tmp)))
_fix = tempfile.mkdtemp(prefix="h36-fix-")
_CLEANUP_DIRS.append(_fix)
shutil.copy2(os.path.join(WBASE, "PROTOCOL-LOCK.json"),
             os.path.join(_fix, "PROTOCOL-LOCK.json"))
_bad = json.load(open(os.path.join(WBASE, "EXECUTION-LOCK.json")))
_bad.pop("finalization_commit")
with open(os.path.join(_fix, "EXECUTION-LOCK.json"), "w") as f:
    json.dump(_bad, f, indent=1)
_gate = WRA.final_lock_gate(_fix, exec_sha=WHEAD)
check("E13 the gate fail-closes a malformed FINAL record (missing "
      "finalization_commit => LOCK-NOT-FINAL, never silent trust)",
      len(_gate) == 1 and "LOCK-NOT-FINAL" in _gate[0]
      and "EXECUTION-LOCK.json" in _gate[0]
      and "finalization_commit" in _gate[0], str(_gate)[:200])
_fix2 = tempfile.mkdtemp(prefix="h36-fix2-")
_CLEANUP_DIRS.append(_fix2)
shutil.copy2(os.path.join(WBASE, "EXECUTION-LOCK.json"),
             os.path.join(_fix2, "EXECUTION-LOCK.json"))
_gate = WRA.final_lock_gate(_fix2, exec_sha=WHEAD)
check("E14 a MISSING protocol lock is itself a LOCK-NOT-FINAL refusal "
      "(both authorities are always required)",
      len(_gate) == 1 and "LOCK-NOT-FINAL" in _gate[0]
      and "PROTOCOL-LOCK.json" in _gate[0], str(_gate)[:200])

# ----------------------------------------------------------------- done
assert len(_calls) == 0, "counting transport was touched"

bad = [n for n, ok_ in results if not ok_]
print(f"\nH36 FINAL-lock smoke: {len(results) - len(bad)}/{len(results)} "
      "closed")
sys.exit(1 if bad else 0)

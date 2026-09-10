#!/usr/bin/env python3
"""H33 — A12n slice D12b acceptance: grading-evaluator provenance (P0).

D12 closed the frozen-task TOCTOU for the VISIBLE set; D12b closes the
SAME false-positive class one directory up — the grading evaluator
itself. benchmarks/fam-c/harness-run/run_arm_h1.py execute_arrival()
read families/<family>/check.py + truth.json from the MUTABLE working
tree at grading time, after verify_instance_frozen() had long returned:
rewriting check.py to `exit 0` turned a deliberately WRONG solver
report from verdict "fix" into "ship" with nothing in the run manifest
naming the substituted bytes.

D12b binds the evaluator to the freeze-commit authority (same
discipline as harness/frozen_visible.py, never the mutable tree):

  pre-model  live checker/truth sha != freeze-derived expectation
             -> EVALUATOR-DRIFT-DENY before prompt.txt and before any
             model token (MODEL_CALL_COUNT == 0, nothing H-derived
             persisted);
  point-of-use the same re-hash immediately before the checker
             subprocess -> EVALUATOR-DRIFT-DENY, never a verdict;
  stronger form the checker EXECUTED is a run-private copy
             materialized from freeze-commit blobs (outdir/
             frozen-evaluator/), so working-tree mutation cannot
             affect grading at all. Safe because the checker's input
             closure is exactly {check.py, sibling truth.json}
             (asserted per family below);
  manifest   executed checker_sha256 + truth_sha256 AND
             expected_checker_sha256 + expected_truth_sha256
             (freeze-derived) + evaluator_freeze_commit +
             evaluator_source, before evidence genesis;
  classify   a run whose recorded executed sha != the freeze-derived
             one is EXCLUDED naming evaluator provenance (marker-gated:
             manifests without the evaluator fields behave as today).

Proven with a scratch git worktree (live repo never mutated), a
counting fake model transport (MODEL_CALL_COUNT assertions), a
dockerless solver shim where docker is unavailable, and the real
DockerSandbox where the daemon + pinned image are present (gated on
docker, shim otherwise — the bind under test is host-side,
pre/post-container). Stdlib only. Prints `H33 D12b smoke: N/N
closed`; exits non-zero on any failure.
"""
import ast
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
BASE_REAL = os.path.join(REPO, "benchmarks", "fam-c")
FAMC = BASE_REAL
WT = "/tmp/h33-d12b-worktree"
sys.path.insert(0, HARNESS)
sys.path.insert(0, os.path.join(BASE_REAL, "harness-run"))
sys.path.insert(0, BASE_REAL)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def skip(name, why):
    RESULTS.append((name, True))
    print(f"SKIP {name} [{why}]")


def sh(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd} rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def raises(fn, token):
    try:
        fn()
    except BaseException as e:  # noqa: BLE001
        return token in str(e), f"{type(e).__name__}: {e}"[:220]
    return False, "no refusal"


def docker_ok():
    try:
        if subprocess.run(["docker", "info"], capture_output=True,
                          timeout=30).returncode != 0:
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        import dockersandbox as _DSB
        img = _DSB.IMAGE
    except Exception:  # noqa: BLE001
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", img],
                              capture_output=True, timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


import frozen_visible as FV  # noqa: E402
import admissibility as ADM  # noqa: E402

# --- D12b-UNIT: freeze-derived evaluator authority (live repo read-only) --
_EV_T0 = FV.derive_expected_evaluator(FAMC, FREEZE, "fam05")
check("D12b-UNIT derivation returns checker+truth shas for fam05",
      isinstance(_EV_T0.get("checker_sha256"), str)
      and len(_EV_T0["checker_sha256"]) == 64
      and isinstance(_EV_T0.get("truth_sha256"), str)
      and len(_EV_T0["truth_sha256"]) == 64
      and _EV_T0["checker_sha256"] != _EV_T0["truth_sha256"]
      and _EV_T0["freeze_commit"] == FREEZE,
      str(_EV_T0)[:160])


def _show_bytes(rel):
    p = subprocess.run(["git", "show", f"{FREEZE}:{rel}"], cwd=REPO,
                       capture_output=True)
    assert p.returncode == 0, rel
    return p.stdout


check("D12b-UNIT evaluator shas equal the freeze-commit blob bytes "
      "(independent raw-git cross-check)",
      hashlib.sha256(_show_bytes(
          "benchmarks/fam-c/families/fam05/check.py")).hexdigest()
      == _EV_T0["checker_sha256"]
      and hashlib.sha256(_show_bytes(
          "benchmarks/fam-c/families/fam05/truth.json")).hexdigest()
      == _EV_T0["truth_sha256"])

# --- D12b-UNIT: checker input closure, every family ----------------------
# The stronger form (execute the frozen-materialized copy) is safe only
# if the checker's input closure is fully known: each family checker
# must read exactly its __file__-sibling truth.json with stdlib-only
# imports and no other family-file reads.
_FAMS = sorted(d for d in os.listdir(os.path.join(FAMC, "families"))
               if os.path.isdir(os.path.join(FAMC, "families", d)))
_CLOSURE_BAD = []
for _fam in _FAMS:
    _cp = os.path.join(FAMC, "families", _fam, "check.py")
    _src = open(_cp).read()
    try:
        _tree = ast.parse(_src)
    except SyntaxError as e:
        _CLOSURE_BAD.append(f"{_fam}: unparseable {e}")
        continue
    _imports = set()
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.Import):
            _imports.update(a.name.split(".")[0] for a in _node.names)
        elif isinstance(_node, ast.ImportFrom):
            _imports.add((_node.module or "").split(".")[0])
    if not _imports <= {"json", "os", "sys"}:
        _CLOSURE_BAD.append(f"{_fam}: non-stdlib imports {_imports}")
    for _line in _src.splitlines():
        if "HERE" in _line and "__file__" not in _line \
                and '"truth.json"' not in _line \
                and "'truth.json'" not in _line:
            _CLOSURE_BAD.append(f"{_fam}: HERE use outside truth.json: "
                                f"{_line.strip()}"[:120])
    try:
        FV.derive_expected_evaluator(FAMC, FREEZE, _fam)
    except RuntimeError as e:
        _CLOSURE_BAD.append(f"{_fam}: underivable at freeze: {e}"[:120])
check("D12b-UNIT checker closure is {check.py, sibling truth.json} in "
      f"every family (n={len(_FAMS)}: stdlib-only imports, HERE reads "
      "only truth.json, derivable at freeze)",
      len(_FAMS) == 6 and not _CLOSURE_BAD,
      f"fams={_FAMS} bad={_CLOSURE_BAD[:2]}")

# --- D12b-UNIT: materialize round-trip + grade equivalence ---------------
_TMPM = tempfile.mkdtemp(prefix="h33-ev-")
_MAT = FV.materialize_frozen_evaluator(
    FAMC, FREEZE, "fam05", os.path.join(_TMPM, "ev"))
check("D12b-UNIT materialized copy hashes equal the freeze-derived "
      "expectation",
      _MAT["checker_sha256"] == _EV_T0["checker_sha256"]
      and _MAT["truth_sha256"] == _EV_T0["truth_sha256"]
      and open(_MAT["checker_path"], "rb").read() == _show_bytes(
          "benchmarks/fam-c/families/fam05/check.py")
      and open(_MAT["truth_path"], "rb").read() == _show_bytes(
          "benchmarks/fam-c/families/fam05/truth.json"))
_WRONG_OUT = os.path.join(_TMPM, "OUTPUT.json")
open(_WRONG_OUT, "w").write(
    json.dumps({"ok": [], "bad": [], "unverified": []}))
_LIVE_CHK = subprocess.run(
    [sys.executable, os.path.join(FAMC, "families", "fam05", "check.py"),
     "T0", _WRONG_OUT], capture_output=True, text=True)
_MAT_CHK = subprocess.run(
    [sys.executable, _MAT["checker_path"], "T0", _WRONG_OUT],
    capture_output=True, text=True)
check("D12b-UNIT materialized copy grades identically to the frozen "
      "tree bytes (same rc + output on the wrong report)",
      _LIVE_CHK.returncode == _MAT_CHK.returncode == 1
      and _LIVE_CHK.stdout == _MAT_CHK.stdout,
      f"live={_LIVE_CHK.returncode} mat={_MAT_CHK.returncode}")
shutil.rmtree(_TMPM, ignore_errors=True)

# --- D12b-UNIT: the verify authority object carries the evaluator shas --
_FRO = ADM.verify_instance_frozen(FAMC, "fam05", "T0", freeze_commit=FREEZE)
check("D12b-UNIT verify_instance_frozen carries the freeze-derived "
      "evaluator shas (visible-set authority keys unchanged)",
      _FRO.get("expected_checker_sha256") == _EV_T0["checker_sha256"]
      and _FRO.get("expected_truth_sha256") == _EV_T0["truth_sha256"]
      and _FRO.get("expected_visible_manifest_sha256")
      == FV.derive_expected_visible(
          FAMC, FREEZE, "fam05", "T0")["manifest_sha256"],
      str(sorted(_FRO))[:200])

# --- D12b scratch worktree surface (live repo never mutated) -------------
# The control solver is deliberately WRONG (empty report for fam05/T0,
# whose truth wants ok=[alpha.txt, beta.txt]) so the honest verdict is
# "fix" (checker rc 1) — the fix must not turn honest runs into refusals.
WRONG_SOLVER = ("import json,sys;json.dump({\"ok\":[],\"bad\":[],"
                "\"unverified\":[]},open(sys.argv[2],\"w\"))\n")
ATTACK_CHECKER = ("import sys;print('SHIP (attacker evaluator)');"
                  "sys.exit(0)\n")
ARRIVAL_WRONG = json.dumps({
    "decision": "fresh",
    "execution_payload": {"solver_py": WRONG_SOLVER},
    "notes": "h33 wrong solver (honest verdict is fix)"})
RESP_TMPL = {
    "id": "chatcmpl-h33-0001", "object": "chat.completion",
    "created": 1799999999, "model": "minimax-m3",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": None}}],
    "usage": {"prompt_tokens": 1500, "completion_tokens": 250,
              "total_tokens": 1750,
              "prompt_tokens_details": {"cached_tokens": 400}}}


class FakeResp:
    status = 200

    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def install_counting_transport(usage_mod, content):
    payload = json.loads(json.dumps(RESP_TMPL))
    payload["choices"][0]["message"]["content"] = content
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(getattr(req, "full_url", "?"))
        return FakeResp(payload)

    usage_mod.urllib.request.urlopen = fake_urlopen
    return calls


def build_surface():
    if os.path.exists(WT):
        subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force",
                        WT], capture_output=True)
    shutil.rmtree(WT, ignore_errors=True)
    head = sh(["git", "-C", REPO, "rev-parse", "HEAD"]).strip()
    sh(["git", "-C", REPO, "worktree", "add", "--detach", WT, head])
    for rel in ("harness", "benchmarks/fam-c/harness-run"):
        src, dst = os.path.join(REPO, rel), os.path.join(WT, rel)
        for name in sorted(os.listdir(src)):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(src, name),
                             os.path.join(dst, name))
    for name in ("preflight.py", "ORDER-EXPANSION.json",
                 "PROTOCOL-LOCK.json", "EXECUTION-LOCK.json", "FREEZE.json",
                 "FREEZE-HASHES.sha256", "PREREG.md", "ORDER.md", "LANES.md",
                 "HARNESS-READINESS.md", "FAMC-EXECUTION-STATUS.md"):
        shutil.copy2(os.path.join(BASE_REAL, name),
                     os.path.join(WT, "benchmarks", "fam-c", name))
    shutil.rmtree(os.path.join(WT, "benchmarks", "fam-c", "families"))
    shutil.copytree(os.path.join(BASE_REAL, "families"),
                    os.path.join(WT, "benchmarks", "fam-c", "families"))
    return head


build_surface()
for p in (os.path.join(WT, "harness"),
          os.path.join(WT, "benchmarks", "fam-c", "harness-run")):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)
for _name in ("run_arm_h1", "usage", "order", "identity", "chain", "lock",
              "seal", "dockersandbox", "admissibility", "reuse_log",
              "preflight", "promotion", "symmetry", "frozen_visible"):
    sys.modules.pop(_name, None)
import run_arm_h1 as WRA  # noqa: E402
WRA.BASE = os.path.join(WT, "benchmarks", "fam-c")
WRA.ROOT = WT
WRA.HARNESS = os.path.join(WT, "harness")
WRA.preflight_validate_all = lambda *_a, **_k: []
import usage as WUSAGE  # noqa: E402
import order as WORDER  # noqa: E402
import admissibility as WADM  # noqa: E402
import frozen_visible as FV2  # noqa: E402
import dockersandbox as WDSB  # noqa: E402

HAVE_DOCKER = docker_ok() and os.environ.get("H33_FORCE_SHIM") != "1"
print(f"H33 docker real-jail path: {HAVE_DOCKER}")
if not HAVE_DOCKER:
    class ShimSandbox:
        """Dockerless stand-in (H23 ShimJail pattern): executes the
        solver argv locally with /work<->work + /task<->visible
        mapping; task_snapshot via the real _hash_tree; manifest()
        mirrors the DockerSandbox keys the manifest/chain consume."""

        def __init__(self, work, visible, expected_task_snapshot=None):
            os.makedirs(work, exist_ok=True)
            self.work = work
            self.visible = visible
            self.task_snapshot = WDSB._hash_tree(visible)
            if expected_task_snapshot is not None and \
                    self.task_snapshot != expected_task_snapshot:
                raise PermissionError(
                    "SNAPSHOT-DENY shim staged snapshot != expected "
                    "authorized snapshot; refused")

        def run(self, argv, timeout=120, **kw):
            mapped = []
            for a in argv:
                if a == "/task":
                    mapped.append(self.visible)
                elif a.startswith("/task/"):
                    mapped.append(os.path.join(
                        self.visible, a[len("/task/"):]))
                elif a == "/work":
                    mapped.append(self.work)
                elif a.startswith("/work/"):
                    mapped.append(os.path.join(
                        self.work, a[len("/work/"):]))
                else:
                    mapped.append(a)
            return subprocess.run(mapped, capture_output=True, text=True,
                                  timeout=timeout)

        def manifest(self):
            return {"sandbox": "shim-no-docker", "image": "shim",
                    "task_snapshot": self.task_snapshot,
                    "mounts": [{"host": self.work, "container": "/work",
                                "mode": "rw"},
                               {"host": self.visible, "container": "/task",
                                "mode": "ro"}]}

    WRA.DockerSandbox = ShimSandbox
    skip("D12b real-docker grading leg", "docker unavailable; shim grades "
         "the same solver bytes locally")
else:
    skip("D12b dockerless shim leg", "docker available; real jail grades")

_WBASE = WRA.BASE
_WEXP = WORDER.load_expansion(_WBASE)
_WCELL, _WF = WORDER.authorize_event(_WEXP, "PQ", "fam05", "T0", "A", {})
_WFAMTASK = os.path.join(_WBASE, "families", "fam05", "T0")
_WCHECKER = os.path.join(_WBASE, "families", "fam05", "check.py")
_WTRUTH = os.path.join(_WBASE, "families", "fam05", "truth.json")
_WCHECKER_ORIG = open(_WCHECKER, "rb").read()
_WTRUTH_ORIG = open(_WTRUTH, "rb").read()
_WOPTS = {"block": "PQ", "wire": True, "acquisition_event": "T0",
          "acquisition_universe": "A"}


def _wrun():
    return WORDER.run_dir(_WBASE, _WCELL)


# --- D12b-ATTACK (a): post-verify check.py rewrite -> pre-model refuse --
_calls_a = install_counting_transport(WUSAGE, ARRIVAL_WRONG)
_real_verify = WRA.verify_instance_frozen


def _verify_then_mutate(*a, **k):
    r = _real_verify(*a, **k)
    open(_WCHECKER, "w").write(ATTACK_CHECKER)
    return r


WRA.verify_instance_frozen = _verify_then_mutate
try:
    ok_a, why_a = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
        "EVALUATOR-DRIFT-DENY")
finally:
    WRA.verify_instance_frozen = _real_verify
    open(_WCHECKER, "wb").write(_WCHECKER_ORIG)
check("D12b-ATTACK(a) post-verify checker rewrite refused with "
      "EVALUATOR-DRIFT-DENY", ok_a, why_a)
check("D12b-ATTACK(a) MODEL_CALL_COUNT == 0 and nothing H-derived "
      "persisted (no prompt/arrival/manifest)",
      len(_calls_a) == 0
      and not os.path.exists(os.path.join(_wrun(), "prompt.txt"))
      and not os.path.exists(os.path.join(_wrun(), "arrival.json"))
      and not os.path.exists(
          os.path.join(_wrun(), "H1-RUN-MANIFEST.json")),
      f"calls={len(_calls_a)}")
check("D12b-ATTACK(a) victim checker bytes restored",
      open(_WCHECKER, "rb").read() == _WCHECKER_ORIG)

# --- D12b-ATTACK (b): rewrite AFTER the pre-model check -> point-of-use -
_calls_b = install_counting_transport(WUSAGE, ARRIVAL_WRONG)
_real_call = WRA.call


def _call_then_mutate_checker(*a, **k):
    r = _real_call(*a, **k)
    open(_WCHECKER, "w").write(ATTACK_CHECKER)
    return r


WRA.call = _call_then_mutate_checker
try:
    ok_b, why_b = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
        "EVALUATOR-DRIFT-DENY")
finally:
    WRA.call = _real_call
    open(_WCHECKER, "wb").write(_WCHECKER_ORIG)
check("D12b-ATTACK(b) post-model checker rewrite refused at the point "
      "of use with EVALUATOR-DRIFT-DENY", ok_b, why_b)
check("D12b-ATTACK(b) no verdict recorded (no run manifest) and the "
      "frozen copy was never materialized for grading",
      not os.path.exists(os.path.join(_wrun(), "H1-RUN-MANIFEST.json"))
      and not os.path.exists(os.path.join(_wrun(), "frozen-evaluator")),
      "manifest or frozen-evaluator present")
check("D12b-ATTACK(b) the model WAS called once (refusal is at grading, "
      "not pre-model)", len(_calls_b) == 1, f"calls={len(_calls_b)}")

# --- D12b-ATTACK (c): post-model truth.json rewrite -> refuse ----------
_calls_c = install_counting_transport(WUSAGE, ARRIVAL_WRONG)


def _call_then_mutate_truth(*a, **k):
    r = _real_call(*a, **k)
    open(_WTRUTH, "w").write('{"T0": {"ok": ["x"], "bad": [], '
                             '"unverified": []}}')
    return r


WRA.call = _call_then_mutate_truth
try:
    ok_c, why_c = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
        "EVALUATOR-DRIFT-DENY")
finally:
    WRA.call = _real_call
    open(_WTRUTH, "wb").write(_WTRUTH_ORIG)
check("D12b-ATTACK(c) post-model truth rewrite refused with "
      "EVALUATOR-DRIFT-DENY", ok_c, why_c)
check("D12b-ATTACK(c) no verdict recorded (no run manifest)",
      not os.path.exists(os.path.join(_wrun(), "H1-RUN-MANIFEST.json")))
check("D12b-ATTACK(c) victim truth bytes restored",
      open(_WTRUTH, "rb").read() == _WTRUTH_ORIG)

# --- D12b-CONTROL: pristine tree, wrong report -> honest "fix" ---------
_calls_d = install_counting_transport(WUSAGE, ARRIVAL_WRONG)
_rc = WRA.main("P", "fam05", "T0", "acquisition", _wrun(), None,
               dict(_WOPTS))
_man = json.load(open(os.path.join(_wrun(), "H1-RUN-MANIFEST.json")))
check("D12b-CONTROL pristine run completes (fix is verdict 0)",
      _rc == 0 and _man.get("verdict") == "fix"
      and _man.get("checker_returncode") == 1, f"rc={_rc}")
_WANT_EV = FV2.derive_expected_evaluator(
    _WBASE, _man["instance_freeze_commit"], "fam05")
check("D12b-CONTROL manifest carries executed + expected evaluator "
      "provenance bound to the freeze",
      _man.get("checker_sha256") == _WANT_EV["checker_sha256"]
      and _man.get("truth_sha256") == _WANT_EV["truth_sha256"]
      and _man.get("expected_checker_sha256")
      == _WANT_EV["checker_sha256"]
      and _man.get("expected_truth_sha256") == _WANT_EV["truth_sha256"]
      and _man.get("evaluator_freeze_commit")
      == _man.get("instance_freeze_commit")
      and _man.get("evaluator_source") == "frozen-materialized",
      str({k: str(_man.get(k))[:16] for k in
           ("checker_sha256", "expected_checker_sha256",
            "evaluator_source")}))
check("D12b-CONTROL the executed copy is the run-private frozen "
      "materialization (bytes == freeze blobs, path under "
      "frozen-evaluator/)",
      str(_man.get("executed_checker_path") or "").endswith(
          os.path.join("frozen-evaluator", "check.py"))
      and open(_man["executed_checker_path"], "rb").read()
      == _show_bytes("benchmarks/fam-c/families/fam05/check.py")
      and open(os.path.join(_wrun(), "frozen-evaluator",
                            "truth.json"), "rb").read()
      == _show_bytes("benchmarks/fam-c/families/fam05/truth.json"))
check("D12b-CONTROL provenance helper passes the pristine run",
      FV2.verify_expected_provenance(_wrun()) is True)
check("D12b-CONTROL run classifies ESTIMAND-ELIGIBLE",
      WADM.classify_run_dir(
          _wrun(), _man["instance_freeze_commit"])[0] == WADM.ELIGIBLE)

# --- D12b-CLASSIFY: drift detection + legacy gating ---------------------
_stage = os.path.join(WT, "tampered-run")
shutil.rmtree(_stage, ignore_errors=True)
shutil.copytree(_wrun(), _stage)


def _stage_manifest():
    _p = os.path.join(_stage, "H1-RUN-MANIFEST.json")
    _m = json.load(open(_p))
    return _p, _m


_p, _m = _stage_manifest()
_m["checker_sha256"] = "0" * 64  # substituted evaluator graded this run
json.dump(_m, open(_p, "w"), indent=1)
try:
    FV2.verify_expected_provenance(_stage)
    _drift_ok = False
except ValueError as _e:
    _drift_ok = "evaluator" in str(_e)
check("D12b-CLASSIFY substituted executed checker sha fails "
      "provenance naming evaluator", _drift_ok)
_s, _r = WADM.classify_run_dir(_stage, _m["instance_freeze_commit"])
check("D12b-CLASSIFY substituted run EXCLUDED naming evaluator",
      _s == WADM.EXCLUDED and "evaluator" in _r, f"{_s}:{_r}"[:200])

_p, _m = _stage_manifest()
_m["checker_sha256"] = _WANT_EV["checker_sha256"]
_m["expected_truth_sha256"] = "f" * 64  # tampered expectation
json.dump(_m, open(_p, "w"), indent=1)
_s2, _r2 = WADM.classify_run_dir(_stage, _m["instance_freeze_commit"])
check("D12b-CLASSIFY tampered expectation EXCLUDED naming evaluator",
      _s2 == WADM.EXCLUDED and "evaluator" in _r2, f"{_s2}:{_r2}"[:200])

_p, _m = _stage_manifest()  # legacy shape: no evaluator fields at all
for _k in ("checker_sha256", "truth_sha256",
           "expected_checker_sha256", "expected_truth_sha256",
           "evaluator_freeze_commit", "evaluator_source",
           "executed_checker_path"):
    _m.pop(_k, None)
json.dump(_m, open(_p, "w"), indent=1)
try:
    _legacy_ok = FV2.verify_expected_provenance(_stage) is True
except ValueError:
    _legacy_ok = False
_s3, _r3 = WADM.classify_run_dir(_stage, _m["instance_freeze_commit"])
check("D12b-CLASSIFY legacy manifest (no evaluator fields) behaves as "
      "today (marker-gated: provenance passes, eligibility unchanged)",
      _legacy_ok and _s3 == WADM.ELIGIBLE, f"{_s3}:{_r3}"[:200])
shutil.rmtree(_stage, ignore_errors=True)

shutil.rmtree(WT, ignore_errors=True)
subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", WT],
               capture_output=True)
bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH33 D12b smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

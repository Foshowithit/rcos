#!/usr/bin/env python3
"""H34 — A12n slices D12e + D13 acceptance: finite provenance closure.

D12e closes the pre-call ABA window: prepare_arm() hashes the STAGED
mutable visible tree and builds the prompt from it, so staging H and
restoring E before the live-dir gate let the model see H with refusal
landing only after the model call. The fix binds staged_tree and
context_task_snapshot_hash to the frozen authority BEFORE call().

D13 closes three P0 holes on the chain FROZEN TASK -> MODEL REQUEST
-> PROVIDER RESPONSE -> PARSED ARRIVAL -> EXECUTED SOLVER/LOCKED
CAPABILITY -> EXACT GRADED OUTPUT -> FROZEN CHECKER+TRUTH -> VERDICT
-> USAGE/IDENTITY/EVIDENCE CHAIN (nothing outside this boundary):

  P0-1 capability check-then-use: the verified live capdir paths
       steered the prompt and the jail. The fix snapshots the
       lock-verified bytes into a run-private dir (re-hashed at
       snapshot time) and prompt + execution consume ONLY the
       snapshot (CAPABILITY-SNAPSHOT-DENY on the residual window).
  P0-2 graded output != hashed output: the checker read
       run_dir/OUTPUT.json while evidence hashed /work/OUTPUT.json.
       The fix seals the committed output into the run-private
       evaluation package, hashes pre-checker, re-hashes after, and
       refuses with EVALUATOR-INPUT-DRIFT-DENY (never a verdict);
       the T1 candidate-output grading mirrors the seal as
       experimental evidence (validated=false, never infra).
  P0-3 arrival provenance: T1/promotion consumed live arrival.json
       with no run-time binding. The fix captures
       response_text_sha256 + arrival_sha256 (file bytes) +
       execution_payload_sha256 + solver_py_sha256 at run time into
       the manifest + chain model-call link, and every later T1 /
       promotion read requires the live bytes to equal the
       chain-bound value (ACQUISITION-CANDIDATE-DENY /
       PROMOTION-DENY naming arrival provenance).

Each hole ships with its falsifying attack, reproduced pre-fix in
/tmp/d13_repro.py (R-D12e/R-P0-1/R-P0-2/R-P0-3a/R-P0-3b BUG lines).
Scratch git worktree (live repo never mutated), counting fake model
transport, dockerless shims where docker is unavailable (real jail
otherwise). Stdlib only. Prints `H34 D13 smoke: N/N closed`; exits
non-zero on any failure.
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
BASE_REAL = os.path.join(REPO, "benchmarks", "fam-c")
FAMC = BASE_REAL
WT = "/tmp/h34-d13-worktree"
sys.path.insert(0, HARNESS)
sys.path.insert(0, os.path.join(BASE_REAL, "harness-run"))
sys.path.insert(0, BASE_REAL)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]


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
        return token in str(e), f"{type(e).__name__}: {e}"[:240]
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


# ---------------------------------------------------------------- fixtures
SOLVER_T0 = '''import hashlib, json, os, sys
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
        bad.append({"path": path,
                    "reason": "size mismatch %d != %s" % (len(data), size)})
        continue
    if hashlib.sha256(data).hexdigest() != sha:
        bad.append({"path": path, "reason": "sha256 mismatch"}); continue
    ok.append(path)
json.dump({"ok": sorted(ok), "bad": bad, "unverified": []},
          open(outp, "w"))
'''
S1_SOLVER = ('import json,sys;json.dump({"ok":["S1-TAMPERED"],'
             '"bad":[],"unverified":[]},open(sys.argv[2],"w"))\n')
C0 = {"semantic_core": "Audit a file listing: measure every named file "
                       "on disk and match its byte count and digest "
                       "against the listing, then file each entry as "
                       "good or bad.",
      "preconditions": [{"requires_all": ["local", "basis"]}],
      "limitations": []}
C1 = {"semantic_core": "TAMPERED contract: the producer now declares "
                       "remote attestation powers it never had.",
      "preconditions": [{"requires_all": ["local", "remote"]}],
      "limitations": []}
T0_ARRIVAL = json.dumps({"decision": "fresh",
                         "execution_payload": {"solver_py": SOLVER_T0,
                                               "capability_contract": C0},
                         "notes": "h34 T0 ship"})
T1_SOLVER = ('import json,sys;json.dump({"ok":["b.txt"],'
             '"bad":[{"path":"a.txt","reason":"sha256 mismatch"}],'
             '"unverified":[]},open(sys.argv[2],"w"))\n')
T1_ADAPTER = '''import hashlib, json, os, sys
# The T1 story: a file listing (manifest.json) travels with the task
# and a.txt is corrupted in transit. The adapter relays the PRISTINE
# listing into an uppercase MANIFEST and forwards the (corrupted)
# files, so the candidate's MANIFEST check reports a.txt bad/sha and
# the T1 checker SHIPs the report.
src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
listing = json.load(open(os.path.join(src, "manifest.json")))["files"]
lines = []
for entry in listing:
    name = entry["path"]
    data = open(os.path.join(src, name), "rb").read()
    if name == "a.txt":
        data = bytes(bytearray(data[:-1]) + bytes([data[-1] ^ 0x01]))
    open(os.path.join(dst, name), "wb").write(data)
    lines.append("%s:%d:%s" % (name, entry["size"], entry["sha256"]))
open(os.path.join(dst, "MANIFEST"), "w").write("\\n".join(lines) + "\\n")
'''
T1_ARRIVAL = json.dumps({"decision": "fresh",
                         "execution_payload": {"solver_py": T1_SOLVER,
                                               "adapter_py": T1_ADAPTER},
                         "notes": "h34 T1"})
O_BAD = json.dumps({"ok": [], "bad": [], "unverified": []})
O_GOOD = json.dumps({"ok": ["alpha.txt", "beta.txt"], "bad": [],
                     "unverified": []})
RESP_TMPL = {
    "id": "chatcmpl-h34-0001", "object": "chat.completion",
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
              "preflight", "promotion", "symmetry", "frozen_visible",
              "contract_shape", "conformance", "t4_ids", "specificity"):
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
import promotion as WPROMO  # noqa: E402
from lock import promote as _lock_promote  # noqa: E402

HAVE_DOCKER = docker_ok() and os.environ.get("H34_FORCE_SHIM") != "1"
print(f"H34 docker real-jail path: {HAVE_DOCKER}")


class ShimSandbox:
    """Dockerless stand-in (H23/H33 pattern): local subprocess exec with
    /work<->work + /task<->visible mapping; task_snapshot via the real
    _hash_tree; manifest() mirrors the DockerSandbox keys."""

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


if not HAVE_DOCKER:
    WRA.DockerSandbox = ShimSandbox
    skip("D13 real-docker legs", "docker unavailable; shims execute "
         "the same bytes locally")
else:
    skip("D13 dockerless shim legs", "docker available; real jails run")

_WBASE = WRA.BASE
_WEXP = WORDER.load_expansion(_WBASE)
_T0CELL, _ = WORDER.authorize_event(_WEXP, "PQ", "fam05", "T0", "A", {})
_T1CELL = None
_WFAMTASK = os.path.join(_WBASE, "families", "fam05", "T0")
_WBETA = os.path.join(_WFAMTASK, "beta.txt")
_WBETA_ORIG = open(_WBETA, "rb").read()
_WOPTS_T0 = {"block": "PQ", "wire": True, "acquisition_event": "T0",
             "acquisition_universe": "A"}
_WOPTS_T1 = {"block": "PQ", "wire": True, "acquisition_event": "T1",
             "acquisition_universe": "A"}


def _t0_rundir():
    return WORDER.run_dir(_WBASE, _T0CELL)


def _t1_rundir():
    global _T1CELL
    if _T1CELL is None:
        _done = WORDER.completed_cells(_WBASE, _WEXP)
        _T1CELL, _ = WORDER.authorize_event(_WEXP, "PQ", "fam05", "T1",
                                            "A", _done)
    return WORDER.run_dir(_WBASE, _T1CELL)


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


# --------------------------------- P0-1 fixture: locked capability store
_CAP = os.path.join(_WBASE, ".h34-capstore")
shutil.rmtree(_CAP, ignore_errors=True)
os.makedirs(_CAP)
E_ENGINE = ('import json,sys\nfm=json.load(open(sys.argv[1]));'
            'rec=json.load(open(sys.argv[2]));'
            'json.dump({"marker":"E-ORIGINAL"},open(sys.argv[3],"w"))\n')
H_ENGINE = ('import json,sys\njson.dump({"marker":"H-MUTATED"},'
            'open(sys.argv[3],"w"))\n')
E_MANIFEST = '{"capability_id": "h34-cap", "E-MARKER-12345": true}'
H_MANIFEST = '{"capability_id": "h34-cap", "H-MARKER-99999": true}'
E_NOTES = "ORIGINAL-NOTES-67890"
H_NOTES = "MUTATED-NOTES-00000"
for _n, _b in (("engine.py", E_ENGINE), ("manifest.json", E_MANIFEST),
               ("adapter_notes.md", E_NOTES)):
    open(os.path.join(_CAP, _n), "w").write(_b)
_rcp = os.path.join(_CAP, "fixture-receipt.json")
json.dump({"call_id": "fx-h34"}, open(_rcp, "w"))
_lock_promote(
    _CAP, "h34-cap", "v1",
    [os.path.join(_CAP, "engine.py"),
     os.path.join(_CAP, "manifest.json"),
     os.path.join(_CAP, "adapter_notes.md")],
    {"lane": "Q", "family": "fam05", "task": "T0", "arm": "correct",
     "wired": True}, [_rcp], {"lane": "Q", "builder": "h34"},
    block="PQ", universe="u-h34", family="fam05",
    acquisition_chain_tips={"T0": "1" * 64, "T1": "2" * 64},
    source_cells={"T0": "h34/T0", "T1": "h34/T1"},
    producer_identity={"lane": "Q", "builder": "h34"},
    protocol_lock_sha256="3" * 64, execution_lock_sha256="4" * 64,
    semantic_core="h34 fixture capability",
    preconditions=[{"requires_all": ["fixture"]}],
    limitations=["fixture"],
    declared_limitations_present=True, non_discriminating=True,
    conformance_cause="h34 fixture: non-discriminating",
    supported_t4_ids=[], conformance_map_sha256="8" * 64,
    t4_semantic_id="h34-fixture", evidence_grade="harness-validation",
    candidate_sha256="5" * 64, candidate_provenance_sha256="6" * 64,
    promotion_receipt_sha256="7" * 64)
_CAP_ORIG = {n: open(os.path.join(_CAP, n), "rb").read()
             for n in ("engine.py", "manifest.json", "adapter_notes.md")}


def _mutate_cap():
    open(os.path.join(_CAP, "engine.py"), "w").write(H_ENGINE)
    open(os.path.join(_CAP, "manifest.json"), "w").write(H_MANIFEST)
    open(os.path.join(_CAP, "adapter_notes.md"), "w").write(H_NOTES)


def _restore_cap():
    for n, b in _CAP_ORIG.items():
        open(os.path.join(_CAP, n), "wb").write(b)


# --- D13-P0-1a: post-snapshot mutation -> original bytes consumed -------
_real_snap = WRA._snapshot_verified_capability


def _snap_then_mutate(info, dstdir):
    r = _real_snap(info, dstdir)
    _mutate_cap()
    return r


WRA._snapshot_verified_capability = _snap_then_mutate
try:
    _prep = WRA.prepare_arm("P", "fam05", "T0", "correct", _CAP, True,
                            "h34-p01a")
finally:
    WRA._snapshot_verified_capability = _real_snap
    _restore_cap()
check("D13-P0-1a treatment prompt consumed the ORIGINAL locked "
      "manifest (mutated bytes steer nothing)",
      "H-MARKER-99999" not in _prep["prompt"]
      and "E-MARKER-12345" in _prep["prompt"])
check("D13-P0-1a executed engine is the run-private snapshot of "
      "the ORIGINAL bytes (not a live capdir path)",
      _prep["cap_engine"].endswith(
          os.path.join("capability-snapshot", "engine.py"))
      and open(_prep["cap_engine"], "rb").read() == _CAP_ORIG["engine.py"]
      and _prep["cap_info"]["snapshot"]["files"]["engine.py"]
      == _sha_bytes(_CAP_ORIG["engine.py"]))

# --- D13-P0-1b: pre-snapshot mutation -> fail-closed refusal ------------
_real_vcap = WRA._verify_capability


def _vcap_then_mutate(*a, **k):
    r = _real_vcap(*a, **k)
    _mutate_cap()
    return r


WRA._verify_capability = _vcap_then_mutate
try:
    ok_v, why_v = raises(lambda: WRA.prepare_arm(
        "P", "fam05", "T0", "correct", _CAP, True, "h34-p01b"),
        "CAPABILITY-SNAPSHOT-DENY")
finally:
    WRA._verify_capability = _real_vcap
    _restore_cap()
check("D13-P0-1b mutation landing between verification and snapshot "
      "refuses (never consumes unverifiable bytes)", ok_v, why_v)

# --- D13-P0-1c: execution consumes the snapshot --------------------------
_real_snap2 = WRA._snapshot_verified_capability
WRA._snapshot_verified_capability = _snap_then_mutate
try:
    _prep2 = WRA.prepare_arm("P", "fam05", "T0", "correct", _CAP, True,
                             "h34-p01c")
finally:
    WRA._snapshot_verified_capability = _real_snap2
    _restore_cap()


class _EngineShim:
    def __init__(self, work, visible):
        self.work = work
        self.visible = visible
        self.task_snapshot = None

    def run(self, argv, timeout=120, **kw):
        m = []
        for x in argv:
            if x == "/task":
                m.append(self.visible)
            elif x.startswith("/task/"):
                m.append(os.path.join(self.visible, x[6:]))
            elif x == "/work":
                m.append(self.work)
            elif x.startswith("/work/"):
                m.append(os.path.join(self.work, x[6:]))
            else:
                m.append(x)
        return subprocess.run(m, capture_output=True, text=True,
                              timeout=timeout)


_wu = tempfile.mkdtemp(prefix="h34-p01c-work-")
_ou = tempfile.mkdtemp(prefix="h34-p01c-out-")
_arr_c = {"decision": "use_capability",
          "execution_payload": {"field_map": {"a": "b"},
                                "records": [{"x": 1}]},
          "notes": "h34"}
_ex = WRA.execute_arrival(
    "correct", _arr_c, _wu, _ou,
    os.path.join(_WBASE, "families", "fam05", "T0"),
    _prep2["cap_engine"], None,
    jail_factory=lambda w, v: _EngineShim(w, v))
check("D13-P0-1c staged jail engine is the ORIGINAL locked bytes",
      open(os.path.join(_wu, "engine.py"), "rb").read()
      == _CAP_ORIG["engine.py"])
try:
    _marker = json.load(open(os.path.join(_wu, "OUTPUT.json"))
                        ).get("marker")
except Exception:  # noqa: BLE001
    _marker = None
check("D13-P0-1c the ORIGINAL engine executed (mutated engine ran "
      "nowhere)", _marker == "E-ORIGINAL", f"marker={_marker!r}")
shutil.rmtree(_wu, ignore_errors=True)
shutil.rmtree(_ou, ignore_errors=True)

# --- D13-P0-2c: T1 candidate-output seal, direct hermetic validation ----
_T1_TASKDIR = os.path.join(_WBASE, "families", "fam05", "T1")
_WANT_EV = FV2.derive_expected_evaluator(_WBASE, FREEZE, "fam05")
_wv = tempfile.mkdtemp(prefix="h34-p02c-work-")
_ov = tempfile.mkdtemp(prefix="h34-p02c-out-")
_vv = tempfile.mkdtemp(prefix="h34-p02c-vis-")
for _b, _ds, _fs in os.walk(_T1_TASKDIR):
    for _fn in _fs:
        _s = os.path.join(_b, _fn)
        _d = os.path.join(_vv, os.path.relpath(_s, _T1_TASKDIR))
        os.makedirs(os.path.dirname(_d), exist_ok=True)
        shutil.copy2(_s, _d)


class _Jail:
    def __init__(self, work, visible):
        self.work = work
        self.visible = visible
        self.task_snapshot = WDSB._hash_tree(visible)

    def run(self, argv, timeout=120, **kw):
        m = []
        for x in argv:
            if x == "/task":
                m.append(self.visible)
            elif x.startswith("/task/"):
                m.append(os.path.join(self.visible, x[6:]))
            elif x == "/work":
                m.append(self.work)
            elif x.startswith("/work/"):
                m.append(os.path.join(self.work, x[6:]))
            else:
                m.append(x)
        return subprocess.run(m, capture_output=True, text=True,
                              timeout=timeout)

    def manifest(self):
        return {"sandbox": "h34", "image": "h34",
                "task_snapshot": self.task_snapshot, "mounts": []}


def _validate_direct():
    return WRA.validate_t1_candidate(
        adapter_py=T1_ADAPTER, candidate_source=SOLVER_T0,
        candidate_sha256=_sha_bytes(SOLVER_T0.encode()),
        work=_wv, taskdir=_T1_TASKDIR, sb=_Jail(_wv, _vv),
        checker_sha256=_WANT_EV["checker_sha256"],
        truth_sha256=_WANT_EV["truth_sha256"],
        outdir=_ov, jail_factory=lambda w, v: _Jail(w, v))


_cv_clean = _validate_direct()
check("D13-P0-2c honest T1 validation still validates (seal admits "
      "honest bytes)",
      _cv_clean.get("validated") is True
      and _cv_clean.get("validation_verdict") == "ship",
      f"{_cv_clean.get('validation_failure')!r}")
_real_sub = subprocess.run


def _cand_hook(argv, **kw):
    if (isinstance(argv, list) and len(argv) > 3
            and argv[0] == sys.executable
            and os.path.basename(argv[1]) == "check.py"):
        open(argv[3], "w").write(O_GOOD)
    return _real_sub(argv, **kw)


subprocess.run = _cand_hook
try:
    _cv_tampered = _validate_direct()
finally:
    subprocess.run = _real_sub
check("D13-P0-2c candidate-output substitution before the T1 checker "
      "fails validation naming evaluator-input-drift (never a false "
      "validated=true)",
      _cv_tampered.get("validated") is not True
      and "evaluator-input-drift" in str(
          _cv_tampered.get("validation_failure")),
      f"{_cv_tampered.get('validation_failure')!r}")
shutil.rmtree(_wv, ignore_errors=True)
shutil.rmtree(_ov, ignore_errors=True)
shutil.rmtree(_vv, ignore_errors=True)

# --- D12e-ABA: prepare consumes H, gate sees E -> pre-model refuse ------
_calls_e = install_counting_transport(WUSAGE, T0_ARRIVAL)
_real_prep = WRA.prepare_arm


def _prep_aba(*a, **k):
    open(_WBETA, "ab").write(b"H-ABA-MARKER\n")
    r = _real_prep(*a, **k)
    open(_WBETA, "wb").write(_WBETA_ORIG)
    open(os.path.join(r["visible"], "beta.txt"), "wb").write(_WBETA_ORIG)
    return r


WRA.prepare_arm = _prep_aba
try:
    ok_e, why_e = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _t0_rundir(), None,
        dict(_WOPTS_T0)), "FROZEN-VISIBLE-DENY")
finally:
    WRA.prepare_arm = _real_prep
    open(_WBETA, "wb").write(_WBETA_ORIG)
check("D12e-ABA staged-H/restored-E schedule refused with "
      "FROZEN-VISIBLE-DENY", ok_e, why_e)
check("D12e-ABA MODEL_CALL_COUNT == 0 and nothing H-derived "
      "persisted (no prompt/arrival/manifest)",
      len(_calls_e) == 0
      and not os.path.exists(os.path.join(_t0_rundir(), "prompt.txt"))
      and not os.path.exists(os.path.join(_t0_rundir(), "arrival.json"))
      and not os.path.exists(
          os.path.join(_t0_rundir(), "H1-RUN-MANIFEST.json")),
      f"calls={len(_calls_e)}")

# --- D13-P0-2a: output substitution before the checker -> DENY ----------
O_BAD_ARR = json.dumps(
    {"decision": "fresh",
     "execution_payload": {"solver_py":
                           'import json,sys;open(sys.argv[2],"w").write(%r)\n'
                           % O_BAD},
     "notes": "h34 bad solver"})
_calls_o = install_counting_transport(WUSAGE, O_BAD_ARR)
_real_sub2 = subprocess.run


def _sealed_hook(argv, **kw):
    if (isinstance(argv, list) and len(argv) > 3
            and argv[0] == sys.executable
            and os.path.basename(argv[1]) == "check.py"):
        open(argv[3], "w").write(O_GOOD)
    return _real_sub2(argv, **kw)


subprocess.run = _sealed_hook
try:
    ok_o, why_o = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _t0_rundir(), None,
        dict(_WOPTS_T0)), "EVALUATOR-INPUT-DRIFT-DENY")
finally:
    subprocess.run = _real_sub2
check("D13-P0-2a sealed-output substitution refused with "
      "EVALUATOR-INPUT-DRIFT-DENY", ok_o, why_o)
check("D13-P0-2a no verdict recorded (no run manifest: never a "
      "SHIP on substituted bytes)",
      not os.path.exists(
          os.path.join(_t0_rundir(), "H1-RUN-MANIFEST.json")))

# --- D13-P0-2b + T0 ship control (S0 + C0): honest ship, sealed --------
_calls_s = install_counting_transport(WUSAGE, T0_ARRIVAL)
_rc_s = WRA.main("P", "fam05", "T0", "acquisition", _t0_rundir(), None,
                 dict(_WOPTS_T0))
_man_s = json.load(open(os.path.join(_t0_rundir(), "H1-RUN-MANIFEST.json")))
check("D13-P0-2b honest run still SHIPs (seal admits honest bytes)",
      _rc_s == 0 and _man_s.get("verdict") == "ship"
      and _man_s.get("checker_returncode") == 0, f"rc={_rc_s}")
check("D13-P0-2b graded_output_sha256 == sha256 of the persisted "
      "sealed artifact (post-hoc match)",
      isinstance(_man_s.get("graded_output_sha256"), str)
      and open(_man_s["graded_output_path"], "rb").read()
      and hashlib.sha256(
          open(_man_s["graded_output_path"], "rb").read()
      ).hexdigest() == _man_s["graded_output_sha256"]
      and _man_s["graded_output_path"].endswith(
          os.path.join("frozen-evaluator", "OUTPUT.json")),
      str(_man_s.get("graded_output_path")))

# --- D13-P0-3e: arrival provenance rides manifest + chain ---------------
_mchain = [json.loads(l) for l in
           open(os.path.join(_t0_rundir(), "EVIDENCE-CHAIN.jsonl"))
           if l.strip()]
_mmc = [l for l in _mchain if l.get("kind") == "model-call"]
_arr_file_sha = hashlib.sha256(
    open(os.path.join(_t0_rundir(), "arrival.json"), "rb").read()
).hexdigest()
check("D13-P0-3e run manifest binds response/arrival/payload/solver "
      "shas captured at run time",
      _man_s.get("arrival_sha256") == _arr_file_sha
      and _man_s.get("arrival_file") == "arrival.json"
      and _man_s.get("solver_py_sha256") == _sha_bytes(
          SOLVER_T0.encode())
      and isinstance(_man_s.get("response_text_sha256"), str)
      and isinstance(_man_s.get("execution_payload_sha256"), str),
      str({k: str(_man_s.get(k))[:12] for k in
           ("arrival_sha256", "solver_py_sha256")}))
check("D13-P0-3e chain model-call link mirrors the run-time arrival "
      "binding (later reads verify against this)",
      len(_mmc) == 1
      and _mmc[0]["payload"].get("arrival_sha256") == _arr_file_sha
      and _mmc[0]["payload"].get("solver_py_sha256") == _sha_bytes(
          SOLVER_T0.encode()),
      str(_mmc[0]["payload"].get("arrival_sha256"))[:16]
      if _mmc else "no model-call link")

# --- D13-P0-3d: contract swap -> promotion deny --------------------------
_t0_ap = os.path.join(_t0_rundir(), "arrival.json")
_t0_arr = json.load(open(_t0_ap))
_t0_arr["execution_payload"]["capability_contract"] = C1
json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)
try:
    _c1 = WPROMO._producer_contract(_t0_rundir())
    ok_c1, why_c1 = ("TAMPERED" not in str(_c1), f"returned {str(_c1)[:80]}")
except PermissionError as e:
    ok_c1, why_c1 = ("arrival" in str(e).lower(), f"denied: {e}"[:160])
check("D13-P0-3d swapped capability_contract is DENIED naming "
      "arrival provenance (never promoted as producer text)",
      ok_c1, why_c1)
_t0_arr["execution_payload"]["capability_contract"] = C0
json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)
_core0 = WPROMO._producer_contract(_t0_rundir())[0]
check("D13-P0-3d pristine contract still promotes (deny admits "
      "honest bytes)", _core0 == C0["semantic_core"], _core0[:60])

# --- D13-P0-3a: solver swap -> T1 cannot start ---------------------------
_t0_arr["execution_payload"]["solver_py"] = S1_SOLVER
json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)
_calls_t = install_counting_transport(WUSAGE, T1_ARRIVAL)
try:
    ok_t, why_t = raises(lambda: WRA.main(
        "P", "fam05", "T1", "acquisition", _t1_rundir(), None,
        dict(_WOPTS_T1)), "ACQUISITION-CANDIDATE-DENY")
finally:
    pass
_t1dir = _t1_rundir()
check("D13-P0-3a T1 with a swapped T0 arrival cannot start "
      "(candidate-provenance deny)", ok_t, why_t)
check("D13-P0-3a T1 spent no model call and persisted no manifest",
      len(_calls_t) == 0
      and not os.path.exists(
          os.path.join(_t1dir, "H1-RUN-MANIFEST.json")),
      f"calls={len(_calls_t)}")
_t0_arr["execution_payload"]["solver_py"] = SOLVER_T0
json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)

# --- D13-P0-3b: T1 control on pristine arrival ---------------------------
_calls_t2 = install_counting_transport(WUSAGE, T1_ARRIVAL)
_rc_t = WRA.main("P", "fam05", "T1", "acquisition", _t1_rundir(), None,
                 dict(_WOPTS_T1))
_man_t = json.load(open(os.path.join(_t1_rundir(), "H1-RUN-MANIFEST.json")))
_pt1 = os.path.join(_t1_rundir(), "prompt.txt")
check("D13-P0-3b pristine T1 completes with the frozen candidate "
      "in context",
      _rc_t == 0 and len(_calls_t2) == 1
      and "S1-TAMPERED" not in open(_pt1).read()
      and SOLVER_T0[:60] in open(_pt1).read(),
      f"rc={_rc_t} calls={len(_calls_t2)}")

# --- D13-P0-3c: derive_candidate binds the chain -------------------------
_t0_ev = WPROMO.run_evidence(_WBASE, _T0CELL)
_t1_ev = WPROMO.run_evidence(_WBASE, _T1CELL)
_cand = WPROMO.derive_candidate(_t0_ev, _t1_ev,
                                os.path.join(_t0_rundir()))
check("D13-P0-3c pristine derive_candidate returns the frozen T0 "
      "bytes (sha + source)",
      _cand["sha256"] == _sha_bytes(SOLVER_T0.encode())
      and _cand["source"] == SOLVER_T0
      and _cand["arrival_sha256"] == _arr_file_sha,
      _cand["sha256"][:16])
_t0_arr["execution_payload"]["solver_py"] = S1_SOLVER
json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)
try:
    WPROMO.derive_candidate(_t0_ev, _t1_ev, _t0_rundir())
    ok_dc, why_dc = False, "admitted swapped solver"
except PermissionError as e:
    ok_dc, why_dc = ("arrival" in str(e).lower(), f"denied: {e}"[:160])
finally:
    _t0_arr["execution_payload"]["solver_py"] = SOLVER_T0
    json.dump(_t0_arr, open(_t0_ap, "w"), indent=1)
check("D13-P0-3c swapped solver is DENIED at derive_candidate "
      "naming arrival provenance", ok_dc, why_dc)

shutil.rmtree(WT, ignore_errors=True)
subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", WT],
               capture_output=True)
bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH34 D13 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

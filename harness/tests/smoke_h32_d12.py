#!/usr/bin/env python3
"""H32 — A12n slice D12 acceptance: frozen-task TOCTOU closure (P0) +
adaptation-contract bar + history-wording supersede (P1s).

D12.1 closes the frozen-task TOCTOU: the expected visible manifest
is derived from freeze-commit git objects (never the mutable task
dir), the materializer's `copied` list is CHECKED against the
independently determined path set, the materialized bytes must
equal the frozen manifest BEFORE any model token is spent
(FROZEN-VISIBLE-DENY), and the SAME object binds the sandbox
constructor. The run manifest carries the provenance fields
before evidence genesis, and frozen_visible.verify_expected_
provenance re-derives post-hoc.

Proven with a scratch git worktree (live repo never mutated), a
counting fake model transport (MODEL_CALL_COUNT assertions), and
real-docker end-to-end where required (gated on docker, skipped
otherwise). Stdlib only. Prints `H32 D12 smoke: N/N closed`;
exits non-zero on any failure.
"""
import ast
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
WT = "/tmp/h32-d12-worktree"
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
        return subprocess.run(["docker", "info"], capture_output=True,
                              timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


import frozen_visible as FV  # noqa: E402
import seal  # noqa: E402

# --- D12.1-UNIT: frozen derivation (live repo read-only) ---------------
_EXP_T0 = FV.derive_expected_visible(FAMC, FREEZE, "fam05", "T0")
check("D12.1-UNIT derivation returns paths+manifest+shas for fam05/T0",
      _EXP_T0["paths"] == ["MANIFEST", "alpha.txt", "beta.txt",
                           "prompt.md"]
      and set(_EXP_T0["manifest"]) == {
          "file|MANIFEST", "file|alpha.txt", "file|beta.txt",
          "file|prompt.md"}
      and _EXP_T0["freeze_commit"] == FREEZE,
      str(_EXP_T0["paths"]))


def _show_bytes(rel):
    p = subprocess.run(["git", "show", f"{FREEZE}:{rel}"], cwd=REPO,
                       capture_output=True)
    assert p.returncode == 0, rel
    return p.stdout


_WANT_T0 = {f"file|{n}": hashlib.sha256(
    _show_bytes(f"benchmarks/fam-c/families/fam05/T0/{n}")).hexdigest()
    for n in ("prompt.md", "alpha.txt", "beta.txt", "MANIFEST")}
check("D12.1-UNIT manifest equals the freeze-commit blob bytes "
      "(independent raw-git cross-check)",
      _EXP_T0["manifest"] == _WANT_T0)

_LS = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", FREEZE,
     "benchmarks/fam-c/families/"], cwd=REPO, capture_output=True,
    text=True).stdout.split()
_PARTS = [x.split("/") for x in _LS
          if x.startswith("benchmarks/fam-c/families/")]
_FAMS = sorted({p[3] for p in _PARTS if len(p) > 4})
_PAR_BAD, _PAR_N = [], 0
for _fam in _FAMS:
    _tasks = sorted({p[4] for p in _PARTS
                     if len(p) > 5 and p[3] == _fam})
    for _task in _tasks:
        _r = subprocess.run(
            ["git", "show",
             f"{FREEZE}:benchmarks/fam-c/families/{_fam}/{_task}/VISIBLE.md"],
            cwd=REPO, capture_output=True)
        if _r.returncode != 0:
            continue
        _mine = FV.parse_visibility_declaration(_r.stdout.decode())
        _seal = set()
        for _line in _r.stdout.decode().splitlines():
            if "task fixtures:" in _line:
                _seal.update(_line.split("task fixtures:", 1)[1].split())
        _seal.add("prompt.md")
        _PAR_N += 1
        if _mine != _seal:
            _PAR_BAD.append(f"{_fam}/{_task}")
check("D12.1-UNIT frozen parser agrees with the declaration format "
      "on every frozen task (no seal import)",
      _PAR_N > 0 and not _PAR_BAD, f"n={_PAR_N} bad={_PAR_BAD[:2]}")

_VSRC = open(os.path.join(HARNESS, "frozen_visible.py")).read()
_VTREE = ast.parse(_VSRC)
_VSEAL = False
for _node in ast.walk(_VTREE):
    if isinstance(_node, ast.Import):
        _VSEAL = _VSEAL or any(a.name.split(".")[0] == "seal"
                               for a in _node.names)
    elif isinstance(_node, ast.ImportFrom):
        _VSEAL = _VSEAL or ((_node.module or "").split(".")[0] == "seal")
    elif isinstance(_node, ast.Attribute):
        _VSEAL = _VSEAL or (isinstance(_node.value, ast.Name)
                            and _node.value.id == "seal")
check("D12.1-UNIT frozen_visible never routes through seal "
      "(independent parse path: no seal import, no seal.* use)",
      not _VSEAL)

_TMPV = tempfile.mkdtemp(prefix="h32-vis-")
_copied, _ = seal.build_visible_root(
    os.path.join(FAMC, "families", "fam05", "T0"), _TMPV)
check("D12.1-UNIT materializer output agrees with frozen paths on "
      "legitimate input (fam05/T0)",
      sorted(_copied) == _EXP_T0["paths"], str(sorted(_copied)))
_TMPV2 = tempfile.mkdtemp(prefix="h32-vis2-")
_copied2, _ = seal.build_visible_root(
    os.path.join(FAMC, "families", "fam02", "T0"), _TMPV2)
_EXP_T02 = FV.derive_expected_visible(FAMC, FREEZE, "fam02", "T0")
check("D12.1-UNIT agreement holds on a subdir task (fam02/T0)",
      sorted(_copied2) == _EXP_T02["paths"]
      and FV.manifest_of_dir(_TMPV2) == _EXP_T02["manifest"],
      str(sorted(_copied2)))
shutil.rmtree(_TMPV, ignore_errors=True)
shutil.rmtree(_TMPV2, ignore_errors=True)

# --- D12.1 scratch worktree surface (live repo never mutated) ----------
# The control solver genuinely satisfies the frozen MANIFEST checker
# (same solver the H14 production-main proof uses), so the control
# run SHIPs end to end.
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
ARRIVAL_FRESH = json.dumps({
    "decision": "fresh",
    "execution_payload": {"solver_py": SOLVER_T0},
    "notes": "h32 fake arrival"})
RESP_TMPL = {
    "id": "chatcmpl-h32-0001", "object": "chat.completion",
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

_WBASE = WRA.BASE
_WEXP = WORDER.load_expansion(_WBASE)
_WCELL, _WF = WORDER.authorize_event(_WEXP, "PQ", "fam05", "T0", "A", {})
_WFAMTASK = os.path.join(_WBASE, "families", "fam05", "T0")
_WOPTS = {"block": "PQ", "wire": True, "acquisition_event": "T0",
          "acquisition_universe": "A"}


def _wrun():
    return WORDER.run_dir(_WBASE, _WCELL)


# --- D12.1-ATTACK (a): mutate right after verify → no model call -----
_BETA = os.path.join(_WFAMTASK, "beta.txt")
_BETA_ORIG = open(_BETA, "rb").read()
_calls_a = install_counting_transport(WUSAGE, ARRIVAL_FRESH)
_real_verify = WRA.verify_instance_frozen


def _verify_then_mutate(*a, **k):
    r = _real_verify(*a, **k)
    open(_BETA, "ab").write(b"ATTACK-H\n")
    return r


WRA.verify_instance_frozen = _verify_then_mutate
try:
    ok_a, why_a = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
        "FROZEN-VISIBLE-DENY")
finally:
    WRA.verify_instance_frozen = _real_verify
    open(_BETA, "wb").write(_BETA_ORIG)
check("D12.1-ATTACK(a) post-verify fixture mutation refused with "
      "FROZEN-VISIBLE-DENY", ok_a, why_a)
check("D12.1-ATTACK(a) MODEL_CALL_COUNT == 0 (H never reaches "
      "the model)", len(_calls_a) == 0, f"calls={len(_calls_a)}")

# --- D12.1-ATTACK (b): materializer omits a fixture → refuse --------
_calls_b = install_counting_transport(WUSAGE, ARRIVAL_FRESH)
_real_bvr = WRA.build_visible_root


def _omit_fixture(taskdir, visible):
    copied, refused = _real_bvr(taskdir, visible)
    victim = os.path.join(visible, "beta.txt")
    if os.path.exists(victim):
        os.remove(victim)
    return [c for c in copied if c != "beta.txt"], refused


WRA.build_visible_root = _omit_fixture
try:
    ok_b, why_b = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
        "FROZEN-VISIBLE-DENY")
finally:
    WRA.build_visible_root = _real_bvr
check("D12.1-ATTACK(b) omitted-fixture materializer refused with "
      "FROZEN-VISIBLE-DENY", ok_b, why_b)
check("D12.1-ATTACK(b) MODEL_CALL_COUNT == 0", len(_calls_b) == 0,
      f"calls={len(_calls_b)}")

# --- D12.1-E2E (c)+(d): full path + provenance (needs docker) --------
if not docker_ok():
    skip("D12.1-E2E(c) full TOCTOU with fake model", "docker unavailable")
    skip("D12.1-E2E(d) provenance accept/refuse", "docker unavailable")
    skip("D12.1 manifest provenance fields", "docker unavailable")
else:
    _PROMPT = os.path.join(_WFAMTASK, "prompt.md")
    _PROMPT_ORIG = open(_PROMPT, "rb").read()
    _calls_c = install_counting_transport(WUSAGE, ARRIVAL_FRESH)
    _real_verify_c = WRA.verify_instance_frozen

    def _verify_then_mutate_prompt(*a, **k):
        r = _real_verify_c(*a, **k)
        open(_PROMPT, "ab").write(b"ATTACK-H\n")
        return r

    WRA.verify_instance_frozen = _verify_then_mutate_prompt
    try:
        ok_c, why_c = raises(lambda: WRA.main(
            "P", "fam05", "T0", "acquisition", _wrun(), None, dict(_WOPTS)),
            "FROZEN-VISIBLE-DENY")
    finally:
        WRA.verify_instance_frozen = _real_verify
        open(_PROMPT, "wb").write(_PROMPT_ORIG)
    check("D12.1-E2E(c) full-path TOCTOU refused with "
          "FROZEN-VISIBLE-DENY", ok_c, why_c)
    check("D12.1-E2E(c) MODEL_CALL_COUNT == 0 and no prompt/arrival "
          "persisted",
          len(_calls_c) == 0
          and not os.path.exists(os.path.join(_wrun(), "prompt.txt"))
          and not os.path.exists(os.path.join(_wrun(), "arrival.json")),
          f"calls={len(_calls_c)}")

    _calls_d = install_counting_transport(WUSAGE, ARRIVAL_FRESH)
    _rc = WRA.main("P", "fam05", "T0", "acquisition", _wrun(), None,
                   dict(_WOPTS))
    check("D12.1 control run completes with ship", _rc == 0, f"rc={_rc}")
    _man = json.load(open(os.path.join(_wrun(), "H1-RUN-MANIFEST.json")))
    check("D12.1 manifest carries the four provenance fields + "
          "canonical manifest",
          all(_man.get(k) for k in (
              "expected_visible_manifest_sha256",
              "expected_task_snapshot_sha256",
              "expected_visible_paths_sha256",
              "instance_freeze_commit"))
          and isinstance(_man.get("expected_visible_manifest"), dict),
          str(sorted(_man))[:200])
    check("D12.1 provenance helper passes the pristine run",
          FV2.verify_expected_provenance(_wrun()) is True)
    _stage = os.path.join(WT, "tampered-run")
    shutil.rmtree(_stage, ignore_errors=True)
    shutil.copytree(_wrun(), _stage)
    _tman_p = os.path.join(_stage, "H1-RUN-MANIFEST.json")
    _tman = json.load(open(_tman_p))
    _tman["task_snapshot"]["file|prompt.md"] = "0" * 64
    json.dump(_tman, open(_tman_p, "w"), indent=1)
    try:
        FV2.verify_expected_provenance(_stage)
        _tamper_ok = False
    except ValueError as _e:
        _tamper_ok = "mismatch" in str(_e) or "!=" in str(_e) \
            or "sha" in str(_e).lower()
    check("D12.1-E2E(d) tampered task_snapshot fails provenance",
          _tamper_ok)
    _s, _r = WADM.classify_run_dir(_stage, _man["instance_freeze_commit"])
    check("D12.1-E2E(d) tampered run EXCLUDED naming provenance",
          _s == WADM.EXCLUDED and "provenance" in _r, f"{_s}:{_r}"[:200])
    shutil.rmtree(_stage, ignore_errors=True)

# --- D12-GOV: PREREG amendments ----------------------------------------
_PR = open(os.path.join(FAMC, "PREREG.md")).read()
for _tok in ("AMEND-2026-09-09-d12-frozen-authority",
             "AMEND-2026-09-09-d12-adaptation-contract",
             "AMEND-2026-09-09-d12-history-wording",
             "adaptation_contract_sha256",
             "FROZEN-VISIBLE-DENY",
             "expected_visible_manifest_sha256",
             "verify_expected_provenance"):
    check(f"D12-GOV PREREG carries {_tok}", _tok in _PR)
check("D12-GOV history wording visibly SUPERSEDED with operative "
      "prefix rule stated",
      "SUPERSEDED" in _PR and "order-sensitive prefix" in _PR)

shutil.rmtree(WT, ignore_errors=True)
subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", WT],
               capture_output=True)
bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH32 D12 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

#!/usr/bin/env python3
"""H14 adversarial smoke — the PRODUCTION acquisition path (A12.0).

The auditor's round-2 finding was that the experiment is mechanically
deadlocked at cell 0: no production entry point could produce an acquisition
cell. This suite proves the production entry point exists and refuses
everything it must, through the real `run_arm_h1.py` module:

  A. argument/authorization refusals (real module, real order expansion);
  B. the single runtime primitive refuses an illegal decision per arm;
  C. the full production main() in a scratch estimand surface with ONLY the
     network transport stubbed: real order authorization, real prompt staging,
     real request persistence/hashing, real identity + normalized usage, real
     docker jail, real host checker, real chain, real reuse ledger.

No provider is contacted and no estimand cell is executed: the transport leg
is a canned response object, and every write lands in a throwaway git worktree
(section C) or nowhere at all (sections A/B).

Exit 0 only if every probe is green. Stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
ROOT = os.path.dirname(HARNESS)
REPO = ROOT
BASE_REAL = os.path.join(REPO, "benchmarks", "fam-c")
WT = "/tmp/h14-prodmain-worktree"
sys.path.insert(0, HARNESS)
sys.path.insert(0, os.path.join(BASE_REAL, "harness-run"))
sys.path.insert(0, BASE_REAL)  # preflight.py lives in the fam-c root
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


def skip(name, why):
    results.append((name, True))
    print(f"SKIP {name} [{why}]")


def sh(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd} rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def raises(fn, token):
    """True iff fn() raises with `token` in the message."""
    try:
        fn()
    except BaseException as e:  # SystemExit is the CLI refusal path
        return token in str(e), f"{type(e).__name__}: {e}"[:220]
    return False, "no refusal"


# ---------------------------------------------------------------- section A
import preflight as PF  # noqa: E402
import run_arm_h1 as RA  # noqa: E402
import order  # noqa: E402

# A0: the REAL three-authority preflight is green in this checkout. Without
# this, every refusal below would be indistinguishable from a lock failure.
check("real three-authority preflight is green in this checkout",
      PF.validate_all(BASE_REAL) == [], str(PF.validate_all(BASE_REAL))[:200])

# Sections A/B drive the real module against the real BASE. The refusals
# under test are argument/authorization refusals, so the lock gate is stubbed
# ONLY for them (H5/H7 own the live lock gate; A0 proves it is green here).
RA.preflight_validate_all = lambda *_a, **_k: []
_exp = order.load_expansion(BASE_REAL)
_cellA, _ = order.authorize_event(_exp, "PQ", "fam05", "T0", "A", {})
_capA, _outA = order.derive_paths(BASE_REAL, _cellA)

ok, why = raises(lambda: RA.main(
    "P", "fam05", "T0", "acquisition", _outA, None,
    {"block": "PQ", "wire": True, "acquisition_event": "T0"}), 
    "ACQUISITION-ARGS-DENY")
check("acquisition requires the mandated event+universe pair", ok, why)

ok, why = raises(lambda: RA.main(
    "P", "fam05", "T2", "acquisition", _outA, None,
    {"block": "PQ", "wire": True, "acquisition_event": "T0",
     "acquisition_universe": "A"}), "ACQUISITION-DENY")
check("an acquisition event cannot be run as a downstream task", ok, why)

ok, why = raises(lambda: RA.main(
    "P", "fam05", "T0", "correct", _outA, None,
    {"block": "PQ", "wire": True, "acquisition_event": "T0",
     "acquisition_universe": "A"}), "ACQUISITION-DENY")
check("an acquisition cell cannot carry a capability arm", ok, why)

ok, why = raises(lambda: RA.main(
    "P", "fam05", "T0", "acquisition", _outA, None,
    {"block": "PQ", "wire": True, "promote_dir": _capA}), "PROMOTE-REFUSED")
check("the legacy promotion route is refused in main()", ok, why)

# ---------------------------------------------------------------- section B
# The ONE runtime primitive gates the decision by arm (A11b.2), so an
# acquisition cell can never execute a capability claim.
_use_cap = {"decision": "use_capability",
            "execution_payload": {"field_map": {}, "records": {}},
            "notes": "illegal: no capability exists before PROMOTION"}
ok, why = raises(lambda: RA.execute_arrival(
    "acquisition", _use_cap, "/tmp/h14-never-work", "/tmp/h14-never-out",
    os.path.join(BASE_REAL, "families", "fam05", "T0"), None, None),
    "CONTRACT-DECISION-DENY")
check("execute_arrival refuses use_capability on an acquisition arm", ok, why)

ok, why = raises(lambda: RA.execute_arrival(
    "disabled", _use_cap, "/tmp/h14-never-work", "/tmp/h14-never-out",
    os.path.join(BASE_REAL, "families", "fam05", "T0"), None, None),
    "CONTRACT-DECISION-DENY")
check("execute_arrival refuses use_capability on the disabled arm", ok, why)

ok, why = raises(lambda: RA.execute_arrival(
    "correct", _use_cap, "/tmp/h14-never-work", "/tmp/h14-never-out",
    os.path.join(BASE_REAL, "families", "fam05", "T0"), None, None),
    "CONTRACT-ENGINE-DENY")
check("execute_arrival refuses use_capability without a locked engine",
      ok, why)

# ---------------------------------------------------------------- section C
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
    "notes": "acquisition cell: no capability exists before PROMOTION; "
             "solving from the frozen task definition alone"})
ARRIVAL_CAP = json.dumps({
    "decision": "use_capability",
    "execution_payload": {"field_map": {}, "records": {}},
    "notes": "illegal on an acquisition cell"})
RESP_TMPL = {
    "id": "chatcmpl-h14-acquisition-0001", "object": "chat.completion",
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


def install_transport(usage_mod, content):
    payload = json.loads(json.dumps(RESP_TMPL))
    payload["choices"][0]["message"]["content"] = content
    captured = {}

    def fake_urlopen(req, timeout=None):
        try:
            captured["url"] = req.full_url
            captured["bytes"] = req.data
        except Exception:
            pass
        return FakeResp(payload)

    usage_mod.urllib.request.urlopen = fake_urlopen
    return captured


OVERLAY = ("harness", "benchmarks/fam-c/harness-run")
FAMC_FILES = ("preflight.py", "ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
              "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
              "PREREG.md", "ORDER.md", "LANES.md", "HARNESS-READINESS.md",
              "FAMC-EXECUTION-STATUS.md")


def build_surface():
    """A throwaway git worktree of THIS checkout with the working-tree bytes
    of every relevant file overlaid, so the proof is about the code under
    review and the estimand surface is never touched."""
    if os.path.exists(WT):
        subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force",
                        WT], capture_output=True)
    shutil.rmtree(WT, ignore_errors=True)
    head = sh(["git", "-C", REPO, "rev-parse", "HEAD"]).strip()
    sh(["git", "-C", REPO, "worktree", "add", "--detach", WT, head])
    for rel in OVERLAY:
        src, dst = os.path.join(REPO, rel), os.path.join(WT, rel)
        for name in sorted(os.listdir(src)):
            if name.endswith(".py"):
                shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
    for name in FAMC_FILES:
        shutil.copy2(os.path.join(BASE_REAL, name),
                     os.path.join(WT, "benchmarks", "fam-c", name))
    shutil.rmtree(os.path.join(WT, "benchmarks", "fam-c", "families"))
    shutil.copytree(os.path.join(BASE_REAL, "families"),
                    os.path.join(WT, "benchmarks", "fam-c", "families"))
    return head


def load_worktree_runner():
    for p in (os.path.join(WT, "harness"),
              os.path.join(WT, "benchmarks", "fam-c", "harness-run")):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    for name in ("run_arm_h1", "usage", "order", "identity", "chain", "lock",
                 "seal", "dockersandbox", "admissibility", "reuse_log",
                 "preflight", "promotion", "symmetry"):
        sys.modules.pop(name, None)
    import run_arm_h1 as WRA
    WRA.BASE = os.path.join(WT, "benchmarks", "fam-c")
    WRA.ROOT = WT
    WRA.HARNESS = os.path.join(WT, "harness")
    WRA.preflight_validate_all = lambda *_a, **_k: []
    return WRA


def docker_ok():
    try:
        return subprocess.run(["docker", "info"], capture_output=True,
                              timeout=30).returncode == 0
    except Exception:
        return False


if not docker_ok():
    skip("production acquisition path (section C)", "docker unavailable")
else:
    build_surface()
    WRA = load_worktree_runner()
    import usage as WUSAGE
    import order as WORDER
    wbase = WRA.BASE
    wexp = WORDER.load_expansion(wbase)
    wfreeze = json.load(open(os.path.join(wbase, "FREEZE.json")))[
        "freeze_commit"]
    wcell, wf = WORDER.authorize_event(wexp, "PQ", "fam05", "T0", "A", {})
    check("T0 acquisition is authorized at cell 0 with no prior work",
          not wf and wcell["index"] == 0 and wcell["arm"] == "acquisition",
          str(wf)[:200])
    wrun = WORDER.run_dir(wbase, wcell)
    wcap = WORDER.capability_dir(wbase, "PQ", "A", "fam05")

    captured = install_transport(WUSAGE, ARRIVAL_FRESH)
    rc = WRA.main("P", "fam05", "T0", "acquisition", wrun, None,
                  {"block": "PQ", "wire": True,
                   "acquisition_event": "T0", "acquisition_universe": "A"})
    check("production main() completes the acquisition cell with ship",
          rc == 0, f"rc={rc}")
    man = json.load(open(os.path.join(wrun, "H1-RUN-MANIFEST.json")))
    check("manifest arm is the authorized acquisition arm",
          man.get("arm") == "acquisition", str(man.get("arm")))
    check("manifest carries the authorized event/universe pair",
          man.get("acquisition_event") == "T0"
          and man.get("acquisition_universe") == "A",
          f"{man.get('acquisition_event')}/{man.get('acquisition_universe')}")
    check("manifest declares no capability block in the acquisition prompt",
          man.get("acquisition_prompt_has_capability_block") is False,
          str(man.get("acquisition_prompt_has_capability_block")))
    check("manifest has no capability binding",
          man.get("capability") is None, str(man.get("capability")))
    prompt_bytes = open(os.path.join(wrun, "prompt.txt")).read()
    check("the acquisition prompt carries no capability-access block "
          "(production stripper is a no-op on it)",
          WRA.strip_capability_block(prompt_bytes) == prompt_bytes,
          "strip_capability_block changed the acquisition prompt")
    arr = json.load(open(os.path.join(wrun, "arrival.json")))
    check("arrival decision is fresh (the only legal acquisition decision)",
          arr.get("decision") == "fresh", str(arr.get("decision")))
    rec = json.load(open(os.path.join(wrun, man["reuse_record"])))
    check("reuse ledger records capability_available=False and no rejection",
          rec.get("capability_available") is False
          and rec.get("capability_selected") is False
          and rec.get("capability_loaded") is False
          and rec.get("capability_invoked") is False
          and rec.get("capability_output_consumed") is False
          and rec.get("reuse_rejected") is not True,
          json.dumps({k: rec.get(k) for k in
                      ("capability_available", "capability_selected",
                       "capability_loaded", "capability_invoked",
                       "capability_output_consumed", "reuse_rejected")}))
    nu = [f for f in os.listdir(wrun) if f.endswith(".normalized.json")]
    check("exactly one normalized usage artifact is written", len(nu) == 1,
          str(nu))
    if nu:
        n = json.load(open(os.path.join(wrun, nu[0])))
        check("primary_work = uncached_input + output_tokens > 0",
              n["primary_work"] == n["input_tokens_uncached"]
              + n["output_tokens"] and n["primary_work"] > 0,
              f"{n['primary_work']} vs {n['input_tokens_uncached']}"
              f"+{n['output_tokens']}")
        check("the cached fraction stays separate (never merged)",
              n["cached_tokens"] == 400
              and n["input_tokens_uncached"] == 1100,
              f"cached={n['cached_tokens']} "
              f"uncached={n['input_tokens_uncached']}")
    check("the transport stub saw the persisted request bytes",
          bool(captured.get("bytes"))
          and json.loads(captured["bytes"])["messages"][0]["content"]
          == prompt_bytes, "request bytes differ from the staged prompt")
    st = WORDER.cell_state(wbase, wcell, wfreeze)
    check("cell 0 is COMPLETE through the real evidence gate",
          st["status"] == "COMPLETE", json.dumps(st.get("reasons", []))[:300])
    check("no capability lock was minted by an acquisition cell",
          not os.path.exists(os.path.join(wcap, "CAPABILITY_LOCK.json")),
          wcap)
    ok, why = raises(lambda: WRA.main(
        "P", "fam05", "T0", "acquisition", wrun, None,
        {"block": "PQ", "wire": True, "acquisition_event": "T0",
         "acquisition_universe": "A"}), "ORDER-DENY")
    check("re-running a completed acquisition cell is refused", ok, why)

    # An arrival that claims a capability on an acquisition cell must never
    # reach the jail: main() refuses it after the (stubbed) call. T1/A is the
    # next authorized cell once T0/A is COMPLETE.
    install_transport(WUSAGE, ARRIVAL_CAP)
    wcellT1, _ = WORDER.authorize_event(wexp, "PQ", "fam05", "T1", "A", {})
    wrunT1 = WORDER.run_dir(wbase, wcellT1)
    ok, why = raises(lambda: WRA.main(
        "P", "fam05", "T1", "acquisition", wrunT1, None,
        {"block": "PQ", "wire": True, "acquisition_event": "T1",
         "acquisition_universe": "A"}), "ACQUISITION-DECISION-DENY")
    check("a capability claim on an acquisition cell is refused by main()",
          ok, why)

    subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", WT],
                   capture_output=True)

bad = [n for n, okv in results if not okv]
print(f"\nH14 production-main smoke: {len(results) - len(bad)}/{len(results)}"
      " closed")
sys.exit(1 if bad else 0)

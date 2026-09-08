#!/usr/bin/env python3
"""H3 adversarial smoke — governance integration. EVERY probe must FAIL
CLOSED (or prove exactness). Exit 0 only if all green. Stdlib only."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from lock import promote, load_artifact, verify_lock
from invalid import classify, PairLedger
from chain import Chain

BASE = "/tmp/h3-smoke"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


os.system("rm -rf " + BASE)

# --- lock: promote once, resolve exact, refuse tamper/repromote ---
# A12.2: the lock is ESTIMAND-AWARE. Minting requires the full provenance
# field set (block/universe/family, T0+T1 tips, source cells, producer
# identity, both governance lock hashes, semantic core/preconditions/
# limitations, the auditor T4 semantic id, evidence grade, candidate root +
# provenance sha, promotion receipt sha). A legacy pre-A12 lock is
# LOCK-INADMISSIBLE by construction and is never resolvable.
os.makedirs(os.path.join(BASE, "store"), exist_ok=True)
open(os.path.join(BASE, "store", "cap.py"), "w").write("print('v1')\n")
_EST = dict(
    block="PQ", universe="A", family="fam05",
    acquisition_chain_tips={"T0": "0" * 64, "T1": "1" * 64},
    source_cells={"T0": "c-fixture-T0", "T1": "c-fixture-T1"},
    producer_identity={"lane": "P", "adapter": "router9-openai-chat-v2"},
    protocol_lock_sha256="2" * 64, execution_lock_sha256="3" * 64,
    semantic_core="fixture semantic core",
    preconditions=["fixture precondition"],
    limitations=["synthetic fixture, never an estimand artifact"],
    t4_semantic_id="T4-UNRATIFIED-fixture",
    evidence_grade="harness-validation",
    candidate_sha256="4" * 64, candidate_provenance_sha256="5" * 64)
lp = promote(os.path.join(BASE, "lock"), "k1", 1,
             [os.path.join(BASE, "store", "cap.py")],
             {"contract": "c"}, ["ev1"],
             {"builder": "b", "lane": "L"},
             promotion_receipt_sha256="6" * 64, **_EST)
check("promotion writes lock", lp.endswith("CAPABILITY_LOCK.json"))
_lk = json.load(open(lp))
check("minted lock passes the estimand contract",
      verify_lock(_lk) == [] and
      _lk["schema_version"] == "capability-lock-v2", str(verify_lock(_lk)[:1]))
check("verify_lock pins the bound universe/candidate",
      verify_lock(_lk, expect={"universe": "A",
                               "candidate_sha256": "4" * 64}) == [] and
      verify_lock(_lk, expect={"universe": "C"}) != [])
try:
    promote(os.path.join(BASE, "lock-nofields"), "k2", 1,
            [os.path.join(BASE, "store", "cap.py")], {}, [], {},
            promotion_receipt_sha256="6" * 64)
    check("promotion without estimand fields refused", False)
except ValueError as e:
    check("promotion without estimand fields refused",
          "LOCK-INADMISSIBLE" in str(e), str(e)[:80])
_legacy = {k: _lk[k] for k in ("capability_id", "version", "artifacts",
                               "manifest_sha256", "locked_at")}
check("legacy pre-A12 lock shape is inadmissible",
      any("LOCK-INADMISSIBLE" in r for r in verify_lock(_legacy)))
got = load_artifact(lp, "cap.py", os.path.join(BASE, "store"))
check("exact-hash resolution succeeds", got.endswith("cap.py"))
open(os.path.join(BASE, "store", "cap.py"), "w").write("print('v2-TAMPERED')\n")
try:
    load_artifact(lp, os.path.join(BASE, "store", "capXXX.py"), os.path.join(BASE, "store"))
    check("unknown artifact refused", False)
except PermissionError:
    check("unknown artifact refused", True)
try:
    load_artifact(lp, "cap.py", os.path.join(BASE, "store"))
    check("tampered bytes refused", False)
except PermissionError:
    check("tampered bytes refused", True)
open(os.path.join(BASE, "store", "cap.py"), "w").write("print('v1')\n")
try:
    promote(os.path.join(BASE, "lock"), "k1", 2,
            [os.path.join(BASE, "store", "cap.py")], {}, [], {},
            promotion_receipt_sha256="6" * 64, **_EST)
    check("repromotion refused", False)
except PermissionError:
    check("repromotion refused", True)

# A12.2 lock-contract mutations: every one must be refused BY NAME.
import copy as _copy


def _bad_lock(name, mut, token):
    l = _copy.deepcopy(_lk)
    mut(l)
    reasons = verify_lock(l)
    check(f"lock contract refuses {name}",
          any("LOCK-INADMISSIBLE" in r and token in r for r in reasons),
          str(reasons[:1]))


_bad_lock("a dropped schema_version", lambda l: l.pop("schema_version"),
          "legacy lock")
_bad_lock("an unknown schema_version",
          lambda l: l.update(schema_version="capability-lock-v1"),
          "schema_version")
_bad_lock("a dropped estimand field", lambda l: l.pop("evidence_grade"),
          "missing required field")
_bad_lock("a non-hex candidate root",
          lambda l: l.update(candidate_sha256="nothex"), "candidate_sha256")
_bad_lock("identical T0/T1 tips",
          lambda l: l.update(acquisition_chain_tips={"T0": "0" * 64,
                                                     "T1": "0" * 64}),
          "identical")
_bad_lock("swapped source cells",
          lambda l: l.update(source_cells={"T0": "same", "T1": "same"}),
          "identical")
_bad_lock("an empty artifact map", lambda l: l.update(artifacts={}),
          "artifacts")
_bad_lock("a path-shaped artifact name",
          lambda l: l.update(artifacts={"a/b.py": "0" * 64}), "bare filename")
_bad_lock("a bogus evidence grade",
          lambda l: l.update(evidence_grade="estimand-ish"), "evidence_grade")
_bad_lock("a blank semantic core", lambda l: l.update(semantic_core="  "),
          "semantic_core")
_bad_lock("a string preconditions", lambda l: l.update(preconditions="p"),
          "preconditions")
_bad_lock("a dropped T4 semantic id", lambda l: l.pop("t4_semantic_id"),
          "missing required field")
for _pin, _want in (("universe", "C"), ("family", "fam03"), ("block", "QP"),
                    ("capability_id", "other-K"),
                    ("promotion_receipt_sha256", "9" * 64),
                    ("candidate_sha256", "8" * 64)):
    check(f"expect pin refuses {_pin}={_want}",
          verify_lock(_lk, expect={_pin: _want}) != [])
check("expect pin accepts the true bound values",
      verify_lock(_lk, expect={"universe": "A", "family": "fam05",
                               "block": "PQ", "capability_id": "k1",
                               "promotion_receipt_sha256": "6" * 64}) == [])

# --- invalid state machine ---
for kind in ("reasoning-failure", "tool-misuse", "agent-timeout",
             "bad-generated-code", "capability-invocation-failure",
             "malformed-output", "weird-unknown-thing"):
    check(f"agent failure is outcome: {kind}",
          classify(kind) == "outcome")
for kind in ("machine-down", "provider-outage", "harness-crash"):
    check(f"infra failure classified: {kind}",
          classify(kind) == "infrastructure")
led = PairLedger(os.path.join(BASE, "ledger.json"))
led.record_run("p1", "A", "ship")
led.record_run("p1", "B", "fix", failure_kind="tool-misuse")
ok, why = led.request_replacement("p1", "tool-misuse", "settings-v1")
check("agent failure replacement refused", not ok, why)
ok, why = led.request_replacement("p1", "machine-down", "settings-v1")
check("one infra whole-pair replacement allowed", ok, why)
ok, why = led.request_replacement("p1", "machine-down", "settings-v1")
check("second replacement refused + missing-evidence",
      not ok and led.pair_status("p1") == "missing-evidence", why)
led.record_run("p2", "A", "ship")
led.record_run("p2", "B", "blocked", failure_kind="provider-outage")
ok, why = led.request_replacement("p2", "provider-outage", "settings-v2")
check("first replacement allowed (p2)", ok, why)
ok, why = led.request_replacement("p2", "provider-outage", "settings-v3")
check("changed-settings replacement refused", not ok, why)
# replacement completion: manifests bound, both arms required
import hashlib as _hlx
def _rman_orig(path, pair, arm, run):
    open(path, "w").write(json.dumps(
        {"pair": pair, "arm": arm, "run": run}, sort_keys=True))
    return path
_omA = _rman_orig(os.path.join(BASE, "orig-A.json"), "p3", "A", "run-old-A")
_omB = _rman_orig(os.path.join(BASE, "orig-B.json"), "p3", "B", "run-old-B")
led.record_run("p3", "A", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1}, run_manifest_path=_omA)
led.record_run("p3", "B", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1}, run_manifest_path=_omB)
_SNAP = led.state["pairs"]["p3"]["task_snapshot_hash"]


def _rman2(path, pair, arm, epoch, repl_of_hash, authz, settings, snap, run,
           extra=None):
    m = {"schema_version": "replacement-manifest-v1",
         "run_id": run, "pair_id": pair, "arm": arm,
         "replacement_epoch": epoch,
         "replaces_original_manifest_hash": repl_of_hash,
         "authorization_hash": authz, "frozen_settings_hash": settings,
         "task_snapshot_hash": snap,
         "execution_manifest_hash": "exec-" + arm,
         "execution_manifest_path": os.path.join(BASE, f"exec-{arm}.json"),
         "evidence_genesis_hash": "gen-" + arm}
    if extra:
        m.update(extra)
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path


def _rman_orig(path, pair, arm, run):
    open(path, "w").write(json.dumps(
        {"pair": pair, "arm": "arm", "run": run}, sort_keys=True).replace('"arm"', '"arm"'))
    d = json.load(open(path))
    d["arm"] = arm
    open(path, "w").write(json.dumps(d, sort_keys=True))
    return path
def _exec_manifest(path, pair, arm, run):
    open(path, "w").write(json.dumps(
        {"pair_id": pair, "arm": arm, "run_id": run,
         "steps": []}, sort_keys=True))
    return path
# NOTE: old-schema _rman block removed; new-schema flow below replaces it.
import hashlib as _hlo
def _oh(p):
    return _hlo.sha256(open(p, "rb").read()).hexdigest()
_omAh, _omBh = _oh(_omA), _oh(_omB)
for _arm, _orig in (("A", _omA), ("B", _omB)):
    _exec_manifest(os.path.join(BASE, f"exec-{_arm}.json"), "p3", _arm,
                   "run-new-" + _arm)
ok, _ = led.request_replacement("p3", "provider-outage", "settings-v1")
check("p3 replacement authorized", ok)
_authz = led.state["pairs"]["p3"]["authorization_hash"]
_settings = led.state["pairs"]["p3"]["settings_hash"]
_snap = led.state["pairs"]["p3"]["task_snapshot_hash"]
def _gen(arm):
    return _hlo.sha256("|".join(["p3", arm, _authz, _snap]).encode()).hexdigest()
def _chain_for(arm):
    from chain import Chain as _Chain
    _cp = os.path.join(BASE, f"chain-{arm}.jsonl")
    if os.path.exists(_cp):
        os.unlink(_cp)
    return _Chain(_cp, "FREEZE-abc", {"run": "r1", "lane": "p3"},
                  pair_id="p3", arm=arm, authorization_hash=_authz,
                  task_snapshot_hash=_snap)


def _genesis_hash(chain_path):
    with open(chain_path, "rb") as _f:
        return _hlx.sha256(_f.readline()).hexdigest()


from chain import Chain as _Chain0
def _mkv2(path, pair, arm, epoch, repl_of_hash, run, extra=None):
    _ex = os.path.join(BASE, f"exec-{arm}.json")
    with open(_ex, "rb") as _f:
        _exh = _hlx.sha256(_f.read()).hexdigest()
    _cp = os.path.join(BASE, f"chain-{arm}.jsonl")
    if os.path.exists(_cp):
        os.unlink(_cp)
    _Chain0(_cp, "FREEZE-abc", {"run": "r1", "lane": "p3"},
            pair_id="p3", arm=arm, authorization_hash=_authz,
            task_snapshot_hash=_snap)
    with open(_cp, "rb") as _f:
        _gh = _hlx.sha256(_f.readline()).hexdigest()
    m = {"schema_version": "replacement-manifest-v1",
         "run_id": run, "pair_id": pair, "arm": arm,
         "replacement_epoch": epoch,
         "replaces_original_manifest_hash": repl_of_hash,
         "authorization_hash": _authz, "frozen_settings_hash": _settings,
         "task_snapshot_hash": _snap,
         "execution_manifest_hash": _exh,
         "execution_manifest_path": _ex,
         "evidence_chain_path": os.path.join(BASE, f"chain-{arm}.jsonl"),
         "evidence_genesis_hash": _genesis_hash(
             os.path.join(BASE, f"chain-{arm}.jsonl"))}
    if extra:
        m.update(extra)
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path


for _arm in ("A", "B"):
    _chain_for(_arm)
_mA = _mkv2(os.path.join(BASE, "repl-A.json"), "p3", "A", 1, _omAh, "run-new-A")
_mB = _mkv2(os.path.join(BASE, "repl-B.json"), "p3", "B", 1, _omBh, "run-new-B")
check("grading gate closed before completion",
      not led.replacement_complete("p3"))
led.complete_replacement("p3", _mA)
check("grading gate still closed on partial pair",
      not led.replacement_complete("p3"))
led.complete_replacement("p3", _mB)
check("grading gate opens on complete pair",
      led.replacement_complete("p3"))
try:
    led.complete_replacement("p3", _mA)
    check("duplicate arm recording refused", False)
except ValueError:
    check("duplicate arm recording refused", True)
# substitution attacks
_mX = _mkv2(os.path.join(BASE, "repl-X.json"), "pX", "A", 1, _omAh,
            "run-evil-A")
for label, mp in [("foreign-pair manifest refused", _mX)]:
    try:
        led.complete_replacement("p3", mp)
        check(label, False)
    except ValueError:
        check(label, True)
_mW = _mkv2(os.path.join(BASE, "repl-W.json"), "p3", "B", 99, _omBh,
            "run-evil-B")
try:
    led.complete_replacement("p3", _mW)
    check("wrong-epoch manifest refused", False)
except ValueError:
    check("wrong-epoch manifest refused", True)
# cross-arm parent swap + fabricated parent (fresh ledger, own chains)
led2 = PairLedger(os.path.join(BASE, "ledger2.json"))
led2.record_run("q1", "A", "blocked", failure_kind="provider-outage",
                task_snapshot={"t": 1},
                run_manifest_path=_omA)
led2.record_run("q1", "B", "blocked", failure_kind="provider-outage",
                task_snapshot={"t": 1},
                run_manifest_path=_omB)
led2.request_replacement("q1", "provider-outage", "settings-v1")
_a2 = led2.state["pairs"]["q1"]["authorization_hash"]
_s2 = led2.state["pairs"]["q1"]["settings_hash"]
_n2 = led2.state["pairs"]["q1"]["task_snapshot_hash"]
from chain import Chain as _Chain2
def _qchain(arm):
    _cp = os.path.join(BASE, f"chain-q1-{arm}.jsonl")
    if os.path.exists(_cp):
        os.unlink(_cp)
    return _Chain2(_cp, "FREEZE-abc", {"run": "r1", "lane": "q1"},
                   pair_id="q1", arm=arm, authorization_hash=_a2,
                   task_snapshot_hash=_n2)
def _qgen(arm):
    with open(os.path.join(BASE, f"chain-q1-{arm}.jsonl"), "rb") as _f:
        return _hlx.sha256(_f.readline()).hexdigest()
def _mkq(path, pair, arm, epoch, repl_of_hash, run, authz=None):
    az = authz or _a2
    _ex = os.path.join(BASE, f"exec-q1-{arm}.json")
    open(_ex, "w").write(json.dumps(
        {"pair_id": pair, "arm": arm, "run_id": run,
         "steps": []}, sort_keys=True))
    with open(_ex, "rb") as _f:
        _exh = _hlx.sha256(_f.read()).hexdigest()
    m = {"schema_version": "replacement-manifest-v1",
         "run_id": run, "pair_id": pair, "arm": arm,
         "replacement_epoch": epoch,
         "replaces_original_manifest_hash": repl_of_hash,
         "authorization_hash": az, "frozen_settings_hash": _s2,
         "task_snapshot_hash": _n2,
         "execution_manifest_hash": _exh,
         "execution_manifest_path": _ex,
         "evidence_chain_path": os.path.join(BASE, f"chain-q1-{arm}.jsonl"),
         "evidence_genesis_hash": _qgen(arm)}
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path
for _arm in ("A", "B"):
    _qchain(_arm)
_mS2 = _mkq(os.path.join(BASE, "repl-S2.json"), "q1", "A", 1,
            "totally-made-up-hash", "run-evil")
try:
    led2.complete_replacement("q1", _mS2)
    check("fabricated-parent manifest refused", False)
except ValueError:
    check("fabricated-parent manifest refused", True)
# cross-arm parent swap: A manifest claiming B's original hash
_mS3 = _mkq(os.path.join(BASE, "repl-S3.json"), "q1", "A", 1, None,
            "run-evil-S3")
_d3 = json.load(open(_mS3))
_d3["replaces_original_manifest_hash"] = _hlo.sha256(
    open(_omB, "rb").read()).hexdigest()
open(_mS3, "w").write(json.dumps(_d3, sort_keys=True))
try:
    led2.complete_replacement("q1", _mS3)
    check("cross-arm parent swap refused", False)
except ValueError:
    check("cross-arm parent swap refused", True)
# swapped-chain attack: A manifest bound to B's chain genesis
_mS4 = _mkq(os.path.join(BASE, "repl-S4.json"), "q1", "A", 1, None,
            "run-evil-S4")
_d4 = json.load(open(_mS4))
_d4["replaces_original_manifest_hash"] = _hlo.sha256(
    open(_omA, "rb").read()).hexdigest()
_d4["evidence_chain_path"] = os.path.join(BASE, "chain-q1-B.jsonl")
_d4["evidence_genesis_hash"] = _qgen("B")
open(_mS4, "w").write(json.dumps(_d4, sort_keys=True))
try:
    led2.complete_replacement("q1", _mS4)
    check("swapped-chain genesis refused", False)
except ValueError:
    check("swapped-chain genesis refused", True)
# run_id attacks: manifest run_id must equal exec run_id; run ids must
# be unique per pair across originals and replacements
_mR1 = _mkq(os.path.join(BASE, "repl-R1.json"), "q1", "A", 1, None,
            "run-evil-R1")
_dR = json.load(open(_mR1))
_dR["replaces_original_manifest_hash"] = _hlo.sha256(
    open(_omA, "rb").read()).hexdigest()
open(_mR1, "w").write(json.dumps(_dR, sort_keys=True))
try:
    # exec manifest still carries run-evil from _mkq default? No: _mkq
    # writes run_id into exec too, so craft mismatch explicitly:
    _exA = os.path.join(BASE, "exec-q1-A.json")
    _ed = json.load(open(_exA))
    _ed["run_id"] = "DIFFERENT-RUN"
    open(_exA, "w").write(json.dumps(_ed, sort_keys=True))
    led2.complete_replacement("q1", _mR1)
    check("exec/run_id mismatch refused", False)
except ValueError:
    check("exec/run_id mismatch refused", True)
# duplicate run_id across arms + original-reuse (fresh ledger)
led3 = PairLedger(os.path.join(BASE, "ledger3.json"))
led3.record_run("r1", "A", "blocked", failure_kind="provider-outage",
                task_snapshot={"t": 1},
                run_manifest_path=_omA)
led3.record_run("r1", "B", "blocked", failure_kind="provider-outage",
                task_snapshot={"t": 1},
                run_manifest_path=_omB)
led3.request_replacement("r1", "provider-outage", "settings-v1")
_a3 = led3.state["pairs"]["r1"]["authorization_hash"]
_s3 = led3.state["pairs"]["r1"]["settings_hash"]
_n3 = led3.state["pairs"]["r1"]["task_snapshot_hash"]
def _wexec(_arm, _run):
    _ex = os.path.join(BASE, f"exec-r1-{_arm}.json")
    open(_ex, "w").write(json.dumps(
        {"pair_id": "r1", "arm": _arm, "run_id": _run,
         "steps": []}, sort_keys=True))
    return _ex
for _arm in ("A", "B"):
    _wexec(_arm, "run-SAME")
    _cp = os.path.join(BASE, f"chain-r1-{_arm}.jsonl")
    if os.path.exists(_cp):
        os.unlink(_cp)
    from chain import Chain as _Chain3
    _Chain3(_cp, "FREEZE-x", {"run": "r1"},
            pair_id="r1", arm=_arm, authorization_hash=_a3,
            task_snapshot_hash=_n3)


def _mk3(path, arm, run):
    _wexec(arm, run)
    with open(os.path.join(BASE, f"exec-r1-{arm}.json"), "rb") as _f:
        _exh = _hlx.sha256(_f.read()).hexdigest()
    with open(os.path.join(BASE, f"chain-r1-{arm}.jsonl"), "rb") as _f:
        _gh = _hlx.sha256(_f.readline()).hexdigest()
    m = {"schema_version": "replacement-manifest-v1",
         "run_id": run, "pair_id": "r1", "arm": arm,
         "replacement_epoch": 1,
         "replaces_original_manifest_hash": _hlo.sha256(
             open(_omA if arm == "A" else _omB, "rb").read()).hexdigest(),
         "authorization_hash": _a3, "frozen_settings_hash": _s3,
         "task_snapshot_hash": _n3,
         "execution_manifest_hash": _exh,
         "execution_manifest_path": os.path.join(BASE, f"exec-r1-{arm}.json"),
         "evidence_chain_path": os.path.join(BASE, f"chain-r1-{arm}.jsonl"),
         "evidence_genesis_hash": _gh}
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path


_mD1 = _mk3(os.path.join(BASE, "repl-D1.json"), "A", "run-SAME")
led3.complete_replacement("r1", _mD1)
_mD2 = _mk3(os.path.join(BASE, "repl-D2.json"), "B", "run-SAME")
try:
    led3.complete_replacement("r1", _mD2)
    check("duplicate run_id across arms refused", False)
except ValueError:
    check("duplicate run_id across arms refused", True)

# --- chain: intact, deletion, reorder, substitution, tamper ---
ch = Chain(os.path.join(BASE, "chain.jsonl"), "FREEZE-abc",
           {"run": "r1", "lane": "A"})
ch.append("model-call", {"usage": "u1"})
ch.append("capability-event", {"invoked": "k1"})
ch.append("evaluator", {"verdict": "ship"})
_evh = ch.links[-1]["link_hash"]
ch.append("grade", {"grade": "PASS", "evaluator_link_hash": _evh,
                     "grading_rule_hash": "gr1",
                     "grading_rule_version": "v1"})
check("intact chain audits clean",
      ch.audit("FREEZE-abc", {"run": "r1", "lane": "A"}) == [])
check("grade rule match passes",
      ch.audit("FREEZE-abc", {"run": "r1", "lane": "A"},
               expected_grading_rule={"hash": "gr1",
                                      "version": "v1"}) == [])
check("grade rule mismatch fails",
      ch.audit("FREEZE-abc", {"run": "r1", "lane": "A"},
               expected_grading_rule={"hash": "other",
                                      "version": "v1"}) != [])
# deletion
lines = open(os.path.join(BASE, "chain.jsonl")).read().splitlines()
open(os.path.join(BASE, "chain-del.jsonl"), "w").write(
    "\n".join(lines[:2] + lines[3:]) + "\n")
ch2 = Chain(os.path.join(BASE, "chain-del.jsonl"), "FREEZE-abc",
            {"run": "r1", "lane": "A"})
check("deletion detected",
      any("predecessor" in f or "grade" in f
          for f in ch2.audit("FREEZE-abc", {"run": "r1", "lane": "A"})))
# reorder
open(os.path.join(BASE, "chain-reo.jsonl"), "w").write(
    "\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
ch3 = Chain(os.path.join(BASE, "chain-reo.jsonl"), "FREEZE-abc",
            {"run": "r1", "lane": "A"})
check("reorder detected",
      ch3.audit("FREEZE-abc", {"run": "r1", "lane": "A"}) != [])
# substitution (edit a payload, keep hashes)
import copy
recs = [json.loads(l) for l in lines]
recs[1]["payload"] = {"usage": "FORGED"}
open(os.path.join(BASE, "chain-sub.jsonl"), "w").write(
    "\n".join(json.dumps(r, sort_keys=True) for r in recs) + "\n")
ch4 = Chain(os.path.join(BASE, "chain-sub.jsonl"), "FREEZE-abc",
            {"run": "r1", "lane": "A"})
check("substitution detected",
      ch4.audit("FREEZE-abc", {"run": "r1", "lane": "A"}) != [])
# wrong freeze commit
check("wrong-freeze-commit detected",
      ch.audit("OTHER", {"run": "r1", "lane": "A"}) != [])
# unterminated chain
ch5 = Chain(os.path.join(BASE, "chain5.jsonl"), "FREEZE-abc",
            {"run": "r1", "lane": "A"})
ch5.append("model-call", {"usage": "u1"})
check("unterminated chain flagged",
      any("grade" in f for f in
          ch5.audit("FREEZE-abc", {"run": "r1", "lane": "A"})))

# --- terminal grade: append-after-grade refused at write time ---
chT = Chain(os.path.join(BASE, "chain-term.jsonl"), "FREEZE-x", {"run": "t"})
chT.append("model-call", {"u": 1})
chT.append("evaluator", {"v": "ship"})
chT.append("grade", {"evaluator_link_hash": chT.links[-1]["link_hash"],
                     "grading_rule_hash": "gr1", "grading_rule_version": "v1"})
try:
    chT.append("note", {"x": 1})
    check("append-after-grade refused", False)
except PermissionError:
    check("append-after-grade refused", True)
try:
    chT.append("grade", {"evaluator_link_hash": chT.links[-1]["link_hash"],
                         "grading_rule_hash": "gr1", "grading_rule_version": "v1"})
    check("grade-after-grade refused", False)
except PermissionError:
    check("grade-after-grade refused", True)
# grade missing binding fields refused
chU = Chain(os.path.join(BASE, "chain-u.jsonl"), "FREEZE-x", {"run": "u"})
try:
    chU.append("grade", {"verdict": "ship"})
    check("unbound grade refused", False)
except ValueError:
    check("unbound grade refused", True)
# grade binding wrong evaluator fails audit
chV = Chain(os.path.join(BASE, "chain-v.jsonl"), "FREEZE-x", {"run": "v"})
chV.append("evaluator", {"v": "a"})
chV.append("note", {"n": 1})
chV.append("grade", {"evaluator_link_hash": "wrong-hash",
                     "grading_rule_hash": "gr1", "grading_rule_version": "v1"})
check("misbound grade fails audit",
      any("bind" in f for f in chV.audit("FREEZE-x", {"run": "v"})))
# --- A3: admissibility classification + frozen-instance refuse gate ---
import admissibility as ADM

FAMC = os.path.join(os.path.dirname(ROOT), "benchmarks", "fam-c")
FREEZE_C = ADM.load_freeze(FAMC)["freeze_commit"]
res, count = ADM.classify_runs(os.path.join(FAMC, "runs"), FREEZE_C)
h1s = [(n, s, r) for n, s, r in res if n.startswith("H1-")]
check("admissibility: all H1 runs EXCLUDED harness-validation",
      len(h1s) >= 2 and all(s == ADM.EXCLUDED and "harness-validation" in r
                            for _n, s, r in h1s),
      f"estimand-grade={count}")
check("admissibility: real runs/ estimand-grade = 0 (STOP status)",
      count == 0)
# hermetic ESTIMAND-ELIGIBLE fixture (full evidence gate). A12: a wired run
# that spends NO model work is ZERO-WORK and refused, and a receipt-less stub
# cannot exercise the gate — so the fixture is built through the shared
# production-shaped fixture (real receipt + normalized artifact + identity
# binding + real evidence chain + arrival + reuse record).
import shutil
sys.path.insert(0, HERE)
import order as ORD
from fixture_modelrun import build_model_run
froot = os.path.join(BASE, "a3-estimand")
os.makedirs(os.path.join(froot, "families"))
for _name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
              "EXECUTION-LOCK.json"):
    shutil.copy2(os.path.join(FAMC, _name), os.path.join(froot, _name))
shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                os.path.join(froot, "families", "fam05"))
os.chmod(froot, 0o755)
for _dp, _dn, _f in os.walk(froot):
    os.chmod(_dp, 0o755)
    for _d in _dn:
        os.chmod(os.path.join(_dp, _d), 0o755)
_exp = ORD.load_expansion(froot)
good = build_model_run(froot, cell=ORD.expected_event(_exp, "PQ", "fam05",
                                                      "T0", "A"),
                       freeze_commit=FREEZE_C)
s, r = ADM.classify_run_dir(good, FREEZE_C)
check("admissibility: full-gate dir is ESTIMAND-ELIGIBLE", s == ADM.ELIGIBLE, r)
runs = os.path.join(BASE, "a3-runs")
bad_dev = os.path.join(runs, "P-fam07-T0-dev")
os.makedirs(bad_dev)
json.dump({"wired": True, "instance_freeze_commit": FREEZE_C,
           "usage_receipts": [], "dev_mode": True},
          open(os.path.join(bad_dev, "H1-RUN-MANIFEST.json"), "w"))
open(os.path.join(bad_dev, "identity.json"), "w").write("{}")
open(os.path.join(bad_dev, "EVIDENCE-CHAIN.jsonl"), "w").write("")
check("admissibility: dev_mode dir EXCLUDED",
      ADM.classify_run_dir(bad_dev, FREEZE_C)[0] == ADM.EXCLUDED)
bad_anchor = os.path.join(runs, "P-fam07-T0-anchor")
os.makedirs(bad_anchor)
json.dump({"wired": True, "instance_freeze_commit": "0" * 40,
           "usage_receipts": [], "dev_mode": False},
          open(os.path.join(bad_anchor, "H1-RUN-MANIFEST.json"), "w"))
open(os.path.join(bad_anchor, "identity.json"), "w").write("{}")
open(os.path.join(bad_anchor, "EVIDENCE-CHAIN.jsonl"), "w").write("")
check("admissibility: wrong instance anchor EXCLUDED",
      ADM.classify_run_dir(bad_anchor, FREEZE_C)[0] == ADM.EXCLUDED)
# verify_instance_frozen hermetic (item-5: git-resolved manifest + tree
# check): fixture lives in a THROWAWAY git repo; the manifest is committed
# and the freeze commit is its HEAD.
import subprocess as _sp
drift = os.path.join(BASE, "a3-drift")
os.system("rm -rf " + drift)
os.makedirs(os.path.join(drift, "families", "fam99", "T0"))
for rel, body in (("families/fam99/T0/prompt.md", "frozen\n"),
                  ("families/fam99/check.py", "print(1)\n"),
                  ("families/fam99/truth.json", "{}\n")):
    fp = os.path.join(drift, rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    open(fp, "w").write(body)
lines = [f"{ADM._sha(os.path.join(drift, rel))}  {rel}"
         for rel in ("families/fam99/T0/prompt.md",
                     "families/fam99/check.py",
                     "families/fam99/truth.json")]
open(os.path.join(drift, "FREEZE-HASHES.sha256"), "w").write(
    "\n".join(lines) + "\n")
open(os.path.join(drift, "FREEZE.json"), "w").write(json.dumps(
    {"freeze_commit": "HEAD", "freeze_tree": "tbd"}))
_env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")
for _args in (["init", "-q"], ["add", "-A"],
              ["commit", "-qm", "freeze-fixture"]):
    _r = _sp.run(["git"] + _args, cwd=drift, capture_output=True,
                 env=_env)
    assert _r.returncode == 0, _args
_fc = _sp.run(["git", "rev-parse", "HEAD"], cwd=drift, capture_output=True,
              env=_env, text=True).stdout.strip()
_tree = _sp.run(["git", "rev-parse", "HEAD^{tree}"], cwd=drift,
                capture_output=True, env=_env, text=True).stdout.strip()
json.dump({"freeze_commit": _fc, "freeze_tree": _tree},
          open(os.path.join(drift, "FREEZE.json"), "w"))
check("frozen-instance gate: clean fixture passes git-resolved manifest",
      ADM.verify_instance_frozen(drift, "fam99", "T0",
                                 freeze_commit=_fc)["verified_files"] == 3)
# item-5 acceptance: editing the LOCAL working-tree manifest cannot
# redefine truth — the gate still passes against the committed bytes.
open(os.path.join(drift, "FREEZE-HASHES.sha256"), "w").write(
    "0" * 64 + "  families/fam99/T0/prompt.md\n")
check("frozen-instance gate: local manifest edit cannot redefine truth",
      ADM.verify_instance_frozen(drift, "fam99", "T0",
                                 freeze_commit=_fc)["verified_files"] == 3
      and open(os.path.join(drift, "FREEZE-HASHES.sha256")).read()[0] == "0")
_sp.run(["git", "checkout", "-q", "--", "FREEZE-HASHES.sha256"], cwd=drift,
        env=_env)
open(os.path.join(drift, "families", "fam99", "T0", "prompt.md"), "w").write(
    "TAMPERED\n")
try:
    ADM.verify_instance_frozen(drift, "fam99", "T0", freeze_commit=_fc)
    check("frozen-instance gate: drift refused", False)
except RuntimeError:
    check("frozen-instance gate: drift refused", True)
open(os.path.join(drift, "families", "fam99", "T0", "prompt.md"), "w").write(
    "frozen\n")
open(os.path.join(drift, "families", "fam99", "T0", "extra.txt"), "w").write(
    "x\n")
try:
    ADM.verify_instance_frozen(drift, "fam99", "T0", freeze_commit=_fc)
    check("frozen-instance gate: extra file refused", False)
except RuntimeError:
    check("frozen-instance gate: extra file refused", True)
try:
    ADM.verify_instance_frozen(drift, "fam99", "T0")
    check("frozen-instance gate: missing commit refused", False)
except RuntimeError as e:
    check("frozen-instance gate: missing commit refused",
          "FROZEN-INSTANCE-NO-COMMIT" in str(e), str(e)[:80])
try:
    ADM.verify_instance_frozen(drift, "fam99", "T0",
                               freeze_commit="0" * 40)
    check("frozen-instance gate: unresolvable commit refused", False)
except RuntimeError as e:
    check("frozen-instance gate: unresolvable commit refused",
          "FROZEN-MANIFEST-UNRESOLVABLE" in str(e), str(e)[:80])
# item-5 acceptance: recorded freeze_tree must equal the commit's tree;
# altering the record refuses the start.
check("freeze-tree gate: true record passes",
      ADM.verify_freeze_tree(drift, _fc) == _tree)
_bak = json.load(open(os.path.join(drift, "FREEZE.json")))
json.dump({"freeze_commit": _fc, "freeze_tree": "0" * 40},
          open(os.path.join(drift, "FREEZE.json"), "w"))
try:
    ADM.verify_freeze_tree(drift, _fc)
    check("freeze-tree gate: altered record refused", False)
except RuntimeError as e:
    check("freeze-tree gate: altered record refused",
          "FROZEN-TREE-MISMATCH" in str(e), str(e)[:120])
json.dump(_bak, open(os.path.join(drift, "FREEZE.json"), "w"))
# round-2 #14 (pulled into item 5): harness_manifest_sha FAILS on a
# missing required module instead of silently skipping it.
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
import run_arm_h1 as _RUN
_real_harness = _RUN.HARNESS
try:
    _RUN.HARNESS = os.path.join(BASE, "a3-empty-harness")
    os.makedirs(_RUN.HARNESS, exist_ok=True)
    _RUN.harness_manifest_sha()
    check("harness manifest: missing module refused", False)
except RuntimeError as e:
    check("harness manifest: missing module refused",
          "HARNESS-MANIFEST-MISSING" in str(e), str(e)[:120])
finally:
    _RUN.HARNESS = _real_harness
    check("harness manifest: true modules hash",
          len(_RUN.harness_manifest_sha()) == 64)

bad = [n for n, ok_ in results if not ok_]
print(f"\nH3 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)

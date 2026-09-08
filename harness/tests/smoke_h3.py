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

from lock import promote, load_artifact
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
os.makedirs(os.path.join(BASE, "store"), exist_ok=True)
open(os.path.join(BASE, "store", "cap.py"), "w").write("print('v1')\n")
lp = promote(os.path.join(BASE, "lock"), "k1", 1,
             [os.path.join(BASE, "store", "cap.py")],
             {"contract": "c"}, ["ev1"],
             {"builder": "b", "lane": "L"})
check("promotion writes lock", lp.endswith("CAPABILITY_LOCK.json"))
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
            [os.path.join(BASE, "store", "cap.py")], {}, [], {})
    check("repromotion refused", False)
except PermissionError:
    check("repromotion refused", True)

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
bad = [n for n, ok_ in results if not ok_]
print(f"\nH3 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)

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
import hashlib as _hlm
def _rman(path, pair, arm, epoch, repl_of, authz, settings, snap, run):
    m = {"run_id": run, "pair_id": pair, "arm": arm,
         "replacement_epoch": epoch, "replaces_original_run_id": repl_of,
         "authorization_hash": authz, "frozen_settings_hash": settings,
         "task_snapshot_hash": snap, "evidence_genesis": "g"}
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path
led.record_run("p3", "A", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1})
led.record_run("p3", "B", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1})
ok, _ = led.request_replacement("p3", "provider-outage", "settings-v1")
check("p3 replacement authorized", ok)
_authz = led.state["pairs"]["p3"]["authorization_hash"]
_settings = led.state["pairs"]["p3"]["settings_hash"]
_snap = led.state["pairs"]["p3"]["task_snapshot_hash"]
_mA = _rman(os.path.join(BASE, "repl-A.json"), "p3", "A", 1, "run-old-A",
            _authz, _settings, _snap, "run-new-A")
_mB = _rman(os.path.join(BASE, "repl-B.json"), "p3", "B", 1, "run-old-B",
            _authz, _settings, _snap, "run-new-B")
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
# substitution attacks: foreign pair / wrong epoch / wrong settings / wrong task
_mX = _rman(os.path.join(BASE, "repl-X.json"), "pX", "A", 1, "run-old-A",
            _authz, _settings, _snap, "run-evil-A")
for label, mp in [("foreign-pair manifest refused", _mX)]:
    try:
        led.complete_replacement("p3", mp)
        check(label, False)
    except ValueError:
        check(label, True)
_mW = _rman(os.path.join(BASE, "repl-W.json"), "p3", "B", 99, "run-old-B",
            _authz, _settings, _snap, "run-evil-B")
try:
    led.complete_replacement("p3", _mW)
    check("wrong-epoch manifest refused", False)
except ValueError:
    check("wrong-epoch manifest refused", True)

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

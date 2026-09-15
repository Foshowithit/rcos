#!/usr/bin/env python3
"""H3 integration smoke: fully valid provenance graph, then substitute
EACH node/edge one at a time — every substitution must fail grade
acceptance. Exit 0 only if all green. Stdlib only."""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from chain import Chain
from invalid import PairLedger

BASE = "/tmp/h3-graph"
RULE = {"hash": "gr1", "version": "v1"}
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


def H(b):
    if isinstance(b, str):
        b = b.encode()
    return hashlib.sha256(b).hexdigest()


def Hf(path):
    with open(path, "rb") as f:
        return H(f.read())


os.system("rm -rf " + BASE)
os.makedirs(BASE, exist_ok=True)

# --- build the valid graph: originals, exec manifests, chains ---
def _orig(path, pair, arm, run):
    open(path, "w").write(json.dumps(
        {"pair": pair, "arm": arm, "run": run}, sort_keys=True))
    return path


def _exec(path, pair, arm, run_id):
    open(path, "w").write(json.dumps(
        {"pair_id": pair, "arm": arm, "run_id": run_id, "steps": []}, sort_keys=True))
    return path


def _chain(path, pair, arm, authz, snap):
    if os.path.exists(path):
        os.unlink(path)
    return Chain(path, "FREEZE-x", {"run": "r1"},
                 pair_id=pair, arm=arm, authorization_hash=authz,
                 task_snapshot_hash=snap)


_omA = _orig(os.path.join(BASE, "orig-A.json"), "g1", "A", "run-old-A")
_omB = _orig(os.path.join(BASE, "orig-B.json"), "g1", "B", "run-old-B")
led = PairLedger(os.path.join(BASE, "ledger.json"))
led.record_run("g1", "A", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1}, run_manifest_path=_omA)
led.record_run("g1", "B", "blocked", failure_kind="provider-outage",
               task_snapshot={"t": 1}, run_manifest_path=_omB)
led.request_replacement("g1", "provider-outage", "settings-v1")
_authz = led.state["pairs"]["g1"]["authorization_hash"]
_settings = led.state["pairs"]["g1"]["settings_hash"]
_snap = led.state["pairs"]["g1"]["task_snapshot_hash"]
_omAh, _omBh = Hf(_omA), Hf(_omB)


def _repl(path, pair, arm, epoch, repl_of, run, authz=None,
          settings=None, snap=None, extra=None):
    az, st, sn = authz or _authz, settings or _settings, snap or _snap
    _ex = os.path.join(BASE, f"exec-{arm}.json")
    _exec(_ex, pair, arm, run)
    _cp = os.path.join(BASE, f"chain-{arm}.jsonl")
    if os.path.exists(_cp):
        os.unlink(_cp)
    Chain(_cp, "FREEZE-x", {"run": "r1"},
          pair_id=pair, arm=arm, authorization_hash=az,
          task_snapshot_hash=sn)
    with open(_cp, "rb") as _f:
        _gh = H(_f.readline())
    m = {"schema_version": "replacement-manifest-v1",
         "run_id": run, "pair_id": pair, "arm": arm,
         "replacement_epoch": epoch,
         "replaces_original_manifest_hash": repl_of,
         "authorization_hash": az, "frozen_settings_hash": st,
         "task_snapshot_hash": sn,
         "execution_manifest_hash": Hf(_ex),
         "execution_manifest_path": _ex,
         "evidence_chain_path": _cp,
         "evidence_genesis_hash": _gh}
    if extra:
        m.update(extra)
    open(path, "w").write(json.dumps(m, sort_keys=True))
    return path


_mA = _repl(os.path.join(BASE, "repl-A.json"), "g1", "A", 1, _omAh,
            "run-new-A")
_mB = _repl(os.path.join(BASE, "repl-B.json"), "g1", "B", 1, _omBh,
            "run-new-B")


def grade_accepts():
    """Full gate: both arms complete AND chain audits clean AND rule."""
    try:
        led.complete_replacement("g1", _mA)
        led.complete_replacement("g1", _mB)
    except ValueError:
        return False
    if not led.replacement_complete("g1"):
        return False
    for _arm in ("A", "B"):
        _c = Chain(os.path.join(BASE, f"chain-{_arm}.jsonl"),
                    "FREEZE-x", {"run": "r1"})
        _c.append("model-call", {"u": 1})
        _c.append("capability-event", {"invoked": "k"})
        _c.append("evaluator", {"verdict": "ship"})
        _evh = _c.links[-1]["link_hash"]
        _c.append("grade", {"evaluator_link_hash": _evh,
                            "grading_rule_hash": "gr1",
                            "grading_rule_version": "v1"})
        if _c.audit("FREEZE-x", {"run": "r1"},
                    expected_grading_rule=RULE) != []:
            return False
    return True


check("valid graph grades end-to-end", grade_accepts())


def attempt(label, mutate):
    """Fresh ledger; mutate a COPY of one manifest; grade must fail."""
    import shutil
    ledx = PairLedger(os.path.join(BASE, "ledger-x.json"))
    ledx.record_run("g1", "A", "blocked", failure_kind="provider-outage",
                    task_snapshot={"t": 1},
                    run_manifest_path=_omA)
    ledx.record_run("g1", "B", "blocked", failure_kind="provider-outage",
                    task_snapshot={"t": 1},
                    run_manifest_path=_omB)
    ledx.request_replacement("g1", "provider-outage", "settings-v1")
    mp = os.path.join(BASE, "repl-try.json")
    shutil.copy(_mA, mp)
    d = json.load(open(mp))
    mutate(d)
    open(mp, "w").write(json.dumps(d, sort_keys=True))
    try:
        ledx.complete_replacement("g1", mp)
        accepted = True
    except ValueError:
        accepted = False
    check(label, not accepted)


attempt("substitute original-manifest hash",
        lambda m: m.update(
            {"replaces_original_manifest_hash": "00" * 32}))
attempt("substitute authorization",
        lambda m: m.update({"authorization_hash": "00" * 32}))
attempt("substitute settings hash",
        lambda m: m.update({"frozen_settings_hash": "00" * 32}))
attempt("substitute task snapshot",
        lambda m: m.update({"task_snapshot_hash": "00" * 32}))
attempt("substitute evidence genesis",
        lambda m: m.update({"evidence_genesis_hash": "00" * 32}))
attempt("substitute exec manifest hash",
        lambda m: m.update({"execution_manifest_hash": "00" * 32}))
attempt("extra unknown field",
        lambda m: m.update({"model_override": "x"}))
attempt("drop schema_version",
        lambda m: m.pop("schema_version"))
attempt("wrong epoch",
        lambda m: m.update({"replacement_epoch": 99}))
attempt("foreign pair",
        lambda m: m.update({"pair_id": "pX"}))

# grade bound to a foreign evaluator chain
_gm = os.path.join(BASE, "chain-g.jsonl")
if os.path.exists(_gm):
    os.unlink(_gm)
_cg = Chain(_gm, "FREEZE-x", {"run": "r1"},
            pair_id="g1", arm="A",
            authorization_hash=_authz, task_snapshot_hash=_snap)
_cg.append("model-call", {"u": 1})
_cg.append("capability-event", {"invoked": "k"})
_cg.append("evaluator", {"verdict": "ship"})
_other = os.path.join(BASE, "chain-other.jsonl")
if os.path.exists(_other):
    os.unlink(_other)
_co = Chain(_other, "FREEZE-x", {"run": "r9"},
            pair_id="g9", arm="A", authorization_hash="z",
            task_snapshot_hash="t")
_co.append("evaluator", {"verdict": "ship"})
_coh = _co.links[-1]["link_hash"]
_cg.append("grade", {"evaluator_link_hash": _coh,
                     "grading_rule_hash": "gr1",
                     "grading_rule_version": "v1"})
check("grade bound to foreign evaluator fails audit",
      _cg.audit("FREEZE-x", {"run": "r1"},
                expected_grading_rule=RULE) != [])

bad = [n for n, ok_ in results if not ok_]
print(f"\nGraph smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)

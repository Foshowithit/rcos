#!/usr/bin/env python3
"""H16 adversarial smoke — A12.3 USE / REJECT / fresh lifecycle.

Audit round-2 item A12.3: "actual decision drives reuse ledger; T4 rejection
path; remove legacy --promote", plus A12.2 grade-aware consumption.

The suite drives the REAL production authorities (`order._local_state` over a
real manifest + real evidence chain + real reuse_log records + a real
capability-lock-v2 registry) through every legal and illegal decision shape:

  USE            arrival use_capability + record all-true + locked hash match
  REJECT         fresh WITH a capability available + reuse_rejected + reason
  FRESH-NO-CAP   fresh with no capability available
  T4 MISUSE      a T4 run that wrongly uses K is RECORDED, never laundered
  GRADE          an estimand-grade lock is not consumable by an H1 run

Every contradiction must FAIL CLOSED. Stdlib only, no network, no model, no
docker. Exit 0 only if every probe is green.
"""
import json
import os
import shutil
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMC = "/home/chow/chow-work/rcos/benchmarks/fam-c"
RUNNER = os.path.join(FAMC, "harness-run", "run_arm_h1.py")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import order as ORD                                              # noqa: E402
import reuse_log as RL                                           # noqa: E402
import run_arm_h1 as RA                                          # noqa: E402

BASE = "/tmp/h16-smoke"
results = []


def check(name, ok, extra=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


shutil.rmtree(BASE, ignore_errors=True)
os.makedirs(BASE)
STATE = os.path.join(BASE, "state")
os.makedirs(STATE)
EXP = ORD.expand(open(os.path.join(FAMC, "ORDER.md")).read())
json.dump(EXP, open(os.path.join(STATE, "ORDER-EXPANSION.json"), "w"))


def cell(block, family, event, universe):
    for c in EXP["cells"]:
        if (c["block"] == block and c["family"] == family
                and c["event"] == event and c["universe"] == universe):
            return c
    return None


FREEZE = "f" * 40


def tighten(p):
    base = os.path.abspath(BASE)
    p = os.path.abspath(p)
    while p.startswith(base):
        if os.path.isdir(p) and not os.path.islink(p):
            os.chmod(p, 0o755)
        if p == base:
            break
        p = os.path.dirname(p)


def lock_dir(c):
    return ORD.capability_dir(STATE, c["block"], c["universe"], c["family"])


def write_lock(c, grade="harness-validation", engine="print('K')\n"):
    d = lock_dir(c)
    os.makedirs(d, exist_ok=True)
    tighten(d)
    with open(os.path.join(d, "engine.py"), "w") as f:
        f.write(engine)
    import lock as LOCK
    LOCK.promote(d, c["capability_id"], 1,
                 [os.path.join(d, "engine.py")], {"files": {}}, [], {},
                 promotion_receipt_sha256="7" * 64, block=c["block"],
                 universe=c["universe"], family=c["family"],
                 acquisition_chain_tips={"T0": "1" * 64, "T1": "2" * 64},
                 source_cells={"T0": "c-t0", "T1": "c-t1"},
                 producer_identity={"adapter": "router9-openai-chat-v2"},
                 protocol_lock_sha256="3" * 64,
                 execution_lock_sha256="4" * 64,
                 semantic_core="K core", preconditions=["p"],
                 limitations=["l"], t4_semantic_id="T4-UNRATIFIED-x",
                 limitation_present=True, non_discriminating=False,
                 conformance_cause=("h16 lifecycle fixture: synthetic "
                                    "limitation present, T4 treated as "
                                    "discriminating"),
                 # A12c slice C2: the frozen bridge fields (the
                 # synthetic id is its own sole supported member, so
                 # the claimed discrimination is set-consistent).
                 supported_t4_ids=["T4-UNRATIFIED-x"],
                 conformance_map_sha256="8" * 64,
                 evidence_grade=grade, candidate_sha256="5" * 64,
                 candidate_provenance_sha256="6" * 64)
    return os.path.join(d, "CAPABILITY_LOCK.json")


def engine_sha(c):
    import hashlib
    p = os.path.join(lock_dir(c), "engine.py")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def build_run(c, decision, *, available=True, rejected=None, reason=None,
              consumed=None, grade="harness-validation",
              selected_id=None, selected_hash=None):
    """One wired run dir for cell c with the given arrival decision and a
    reuse record written by the PRODUCTION writer."""
    d = ORD.run_dir(STATE, c)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    tighten(d)
    if decision == "use_capability":
        arrival = {"decision": "use_capability",
                   "execution_payload": {"field_map": {"a": "b"},
                                         "records": [{"a": 1}]},
                   "notes": "h16 use"}
    else:
        arrival = {"decision": "fresh",
                   "execution_payload": {"solver_py": "print('solver')\n"},
                   "notes": "h16 fresh"}
    json.dump(arrival, open(os.path.join(d, "arrival.json"), "w"))
    if rejected is None:
        rejected = (decision == "fresh" and available)
    if consumed is None:
        consumed = (decision == "use_capability")
    if reason is None and rejected:
        reason = "fresh: capability not applicable to this task"
    rec = RL.write_record(
        d, c["task"], c["lane"], c["arm"], reuse_policy="capability-first",
        capability_available=available,
        capability_candidate_ids=[c["capability_id"]] if available else [],
        capability_selected=(decision == "use_capability"),
        selected_capability_id=(selected_id if selected_id is not None
                                else (c["capability_id"]
                                      if decision == "use_capability"
                                      else None)),
        selected_capability_hash=(selected_hash if selected_hash is not None
                                  else (engine_sha(c)
                                        if decision == "use_capability"
                                        else None)),
        capability_loaded=consumed, capability_invoked=consumed,
        capability_output_consumed=consumed,
        # production shape (run_arm_h1.py L1233): contribution is never
        # ASSERTED — A13 derives it; a consumed capability records mechanism
        # "none" with a reason, exactly as the production writer does.
        capability_materially_contributed=False,
        contribution_evidence=({"mechanism": "none",
                                "reason": "h16 fixture: consumed but not "
                                          "proven contributed"}
                               if consumed else None),
        reuse_rejected=rejected, reuse_rejection_reason=reason)
    m = {"wired": True, "dev_mode": False, "evidence_grade": grade,
         "cell_id": c["cell_id"], "cell_index": c["index"],
         "block": c["block"], "family": c["family"], "task": c["task"],
         "cell_event": c["event"], "cell_kind": c["kind"],
         "cell_universe": c["universe"], "cell_letter": c["letter"],
         "lane": c["lane"], "arm": c["arm"],
         "capability_id": c["capability_id"],
         "order_sha256": EXP["order_sha256"],
         "instance_freeze_commit": FREEZE,
         "reuse_record": os.path.basename(rec),
         "capability": {"capability_id": c["capability_id"],
                        "capability_version": 1,
                        "lock_sha256": "9" * 64,
                        "engine_sha256": engine_sha(c)}}
    json.dump(m, open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w"))
    import chain as CH
    cp = os.path.join(d, "EVIDENCE-CHAIN.jsonl")
    ch = CH.Chain(cp, FREEZE, m)
    ev = ch.append("evaluator", {"evaluator": "h16-smoke", "verdict": "ship"})
    ch.append("grade", {"evaluator_link_hash": ev,
                        "grading_rule_hash": "0" * 64,
                        "grading_rule_version": "h16-smoke-1"})
    return d, rec


# Only the admissibility classifier is stubbed (a different authority; H3/H4
# exercise the real one). The chain verifier and the reuse writer are REAL.
_stub = types.ModuleType("admissibility")
_stub.ELIGIBLE, _stub.EXCLUDED = "ELIGIBLE", "EXCLUDED"
_stub.classify_run_dir = lambda d, fc=None: ("ELIGIBLE", "ok")
sys.modules["admissibility"] = _stub

T2 = cell("PQ", "fam05", "T2", "A")
T4 = cell("PQ", "fam05", "T4", "A")
assert T2 and T4, "fixture cells missing"

# --- 1. neutral decision line: identical in BOTH arms -------------------
LINE = ("choose use_capability only when a capability-access block is "
        "present and applicable; otherwise choose fresh.")
out = RA._OUT
check("the neutral decision line exists in the shared output contract",
      LINE in out and out.count(LINE) == 1, f"occurrences={out.count(LINE)}")
check("both arms end with the byte-identical shared contract tail",
      RA.CORRECT.endswith(out) and RA.DISABLED.endswith(out)
      and RA.CORRECT[-len(out):] == RA.DISABLED[-len(out):],
      "arm prompts do not share the identical contract tail")
check("the decision line is inside that shared tail, not an arm branch",
      LINE in RA.CORRECT[-len(out):] and LINE in RA.DISABLED[-len(out):])
p = subprocess.run([sys.executable, RUNNER, "--selfcheck-prompt"],
                   capture_output=True, text=True, timeout=600)
check("prompt byte symmetry selfcheck is green with the decision line",
      p.returncode == 0 and "PROMPT-SELFCHECK ok" in (p.stdout + p.stderr),
      (p.stdout + p.stderr)[-160:])

# --- 2. USE path --------------------------------------------------------
write_lock(T2, "harness-validation")
d, rec = build_run(T2, "use_capability")
st = ORD._local_state(STATE, T2)
check("USE: a use_capability run with a matching ledger is COMPLETE",
      st["status"] == "COMPLETE", str(st["reasons"][:2]))
m = json.load(open(os.path.join(d, "H1-RUN-MANIFEST.json")))
check("USE: the ledger names the exact locked engine hash it consumed",
      json.load(open(rec))["selected_capability_hash"]
      == m["capability"]["engine_sha256"])

# --- 3. USE negatives ---------------------------------------------------
rp = rec
good = json.load(open(rp))
json.dump(dict(good, reuse_rejected=True,
               reuse_rejection_reason="contradiction"), open(rp, "w"))
check("USE with reuse_rejected=true is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(dict(good, selected_capability_id="someone-elses-K"),
          open(rp, "w"))
check("USE naming a different capability id is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(dict(good, selected_capability_hash="8" * 64), open(rp, "w"))
check("USE claiming a different engine hash than the lock is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(dict(good, capability_output_consumed=False), open(rp, "w"))
check("USE without output consumption is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(good, open(rp, "w"))
check("USE restored -> COMPLETE again",
      ORD._local_state(STATE, T2)["status"] == "COMPLETE")

# --- 4. REJECT path (the T4-correct decision shape) ---------------------
d, rec = build_run(T2, "fresh", available=True, rejected=True)
st = ORD._local_state(STATE, T2)
check("REJECT: fresh with a capability available + reason is COMPLETE",
      st["status"] == "COMPLETE", str(st["reasons"][:2]))
good = json.load(open(rec))
json.dump(dict(good, reuse_rejected=False), open(rec, "w"))
check("fresh with a capability available but no REJECT record is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(dict(good, reuse_rejection_reason="   "), open(rec, "w"))
check("REJECT without a recorded reason is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(dict(good, capability_invoked=True,
               capability_output_consumed=True), open(rec, "w"))
check("fresh claiming the capability was invoked/consumed is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(good, open(rec, "w"))
check("REJECT restored -> COMPLETE again",
      ORD._local_state(STATE, T2)["status"] == "COMPLETE")

# --- 5. FRESH with no capability available ------------------------------
d, rec = build_run(T2, "fresh", available=False, rejected=False)
st = ORD._local_state(STATE, T2)
check("FRESH-NO-CAP: fresh with no capability available is COMPLETE",
      st["status"] == "COMPLETE", str(st["reasons"][:2]))
good = json.load(open(rec))
json.dump(dict(good, reuse_rejected=True,
               reuse_rejection_reason="bogus"), open(rec, "w"))
check("rejecting a capability that was never available is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
json.dump(good, open(rec, "w"))

# --- 6. T4 near-neighbor: the wrong decision is RECORDED, not laundered --
d, rec = build_run(T4, "use_capability")
st = ORD._local_state(STATE, T4)
r4 = json.load(open(rec))
check("T4 misuse: a T4 run that wrongly uses K is still admissible evidence",
      st["status"] == "COMPLETE", str(st["reasons"][:2]))
check("T4 misuse: the record exposes the reuse so specificity can be scored",
      r4["capability_output_consumed"] is True
      and r4["reuse_rejected"] is False
      and r4["capability_selected"] is True, json.dumps(r4)[:160])
d, rec = build_run(T4, "fresh", available=True, rejected=True)
r4b = json.load(open(rec))
check("T4 correct: reject/abstain is recorded as the REJECT path",
      ORD._local_state(STATE, T4)["status"] == "COMPLETE"
      and r4b["reuse_rejected"] is True
      and r4b["capability_output_consumed"] is False, json.dumps(r4b)[:160])

# --- 7. grade-aware consumption (separate family: locks are write-once
# and one capability dir serves every downstream cell of a family) --------
T3 = cell("PQ", "fam03", "T3", "A")
assert T3, "fam03/T3 fixture cell missing"
write_lock(T3, "estimand")
d, rec = build_run(T3, "use_capability")
st = ORD._local_state(STATE, T3)
check("an estimand-grade lock is NOT consumable by a harness-validation run",
      st["status"] != "COMPLETE"
      and any("estimand-grade lock" in r for r in st["reasons"]),
      str(st["reasons"][:2]))
d, rec = build_run(T3, "fresh", available=True, rejected=True)
check("a harness-validation REJECT run beside an estimand lock is COMPLETE",
      ORD._local_state(STATE, T3)["status"] == "COMPLETE",
      str(ORD._local_state(STATE, T3)["reasons"][:2]))

# --- 8. a run with no arrival / no ledger is never COMPLETE -------------
d, rec = build_run(T2, "fresh", available=True, rejected=True)
os.unlink(os.path.join(d, "arrival.json"))
check("a wired run with no arrival decision is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
d, rec = build_run(T2, "fresh", available=True, rejected=True)
m = json.load(open(os.path.join(d, "H1-RUN-MANIFEST.json")))
m.pop("reuse_record")
json.dump(m, open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w"))
check("a wired run whose manifest names no reuse record is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")
d, rec = build_run(T2, "fresh", available=True, rejected=True)
os.rename(rec, rec + ".moved")
check("a wired run whose named reuse record is absent is refused",
      ORD._local_state(STATE, T2)["status"] != "COMPLETE")

# --- 9. the legacy --promote route is gone ------------------------------
p = subprocess.run([sys.executable, RUNNER, "--promote", BASE],
                   capture_output=True, text=True, timeout=300)
check("the legacy --promote CLI is a hard refusal naming the controller",
      p.returncode != 0 and "PROMOTE-REFUSED" in (p.stdout + p.stderr)
      and "promotion.py" in (p.stdout + p.stderr),
      (p.stdout + p.stderr)[:160])

bad = [n for n, ok in results if not ok]
print(f"\nH16 lifecycle smoke: {len(results) - len(bad)}/{len(results)} closed")
if bad:
    print("FAIL-OPEN: " + "; ".join(bad[:8]))
sys.exit(1 if bad else 0)

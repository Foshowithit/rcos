#!/usr/bin/env python3
"""H13 — promotion controller + estimand-aware lock smoke (A12.1/A12.2).

Audit round-2 items #11 (promotion controller), #12/#14 (estimand-aware
locks), plus the A12 acceptance list:

  * the controller derives the next authorized event itself; the operator
    never names a chain tip, an event cell, or an output directory
  * the candidate is causally rooted in THIS universe's own acquisition
    evidence (T0 arrival payload), re-derived by the validator
  * the lock may only lock hashes the validated promotion receipt named
  * legacy (pre-A12) locks are LOCK-INADMISSIBLE
  * out-of-order governance artifacts (C promotion before A lock, another
    family's promotion while fam05 is active, a preplanted future receipt)
    can never become COMPLETE

Uses the REAL production writers only: order.emit_* via promotion.advance,
harness/tests/fixture_modelrun.build_model_run for the acquisition cells.
Prints `H13 promotion smoke: N/N closed`; exits non-zero on any failure.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)

import order  # noqa: E402
import lock as LOCK  # noqa: E402
import promotion  # noqa: E402
from fixture_modelrun import build_model_run  # noqa: E402

CHECKS = []
ROOT = None
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER_T0 = ("def solve(input_dir, output_path):\n"
             "    import json, os\n"
             "    out = {'ok': [], 'bad': [], 'unverified': []}\n"
             "    for line in open(os.path.join(input_dir, 'MANIFEST')):\n"
             "        line = line.strip()\n"
             "        if line:\n"
             "            out['ok'].append(line.split(':')[0])\n"
             "    json.dump(out, open(output_path, 'w'))\n")
SOLVER_T1 = ("def solve(input_dir, output_path):\n"
             "    import json, os\n"
             "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
             "              open(output_path, 'w'))\n")


def ok(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))


def refuses(name, fn, token, *a, **kw):
    try:
        fn(*a, **kw)
    except (PermissionError, ValueError, RuntimeError) as e:
        msg = str(e)
        ok(name, token in msg, f"got: {msg[:150]}")
        return msg
    except Exception as e:  # noqa: BLE001
        ok(name, False, f"wrong exception {type(e).__name__}: {e}")
        return ""
    ok(name, False, "did not refuse")
    return ""


def setup():
    root = tempfile.mkdtemp(prefix="h13-promo-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256"):
        src = os.path.join(FAMC, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for f in ("fam05", "fam03"):
        shutil.copytree(os.path.join(FAMC, "families", f),
                        os.path.join(fam, f))
    os.chmod(root, 0o755)
    for dirpath, dirnames, _files in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def cell_for(block, family, event, universe):
    exp = order.load_expansion(ROOT)
    c = order.expected_event(exp, block, family, event, universe)
    assert c is not None, f"no {block}/{family}/{event}/{universe} in order"
    return c


def build_pair(universe="A", solver0=SOLVER_T0, solver1=SOLVER_T1):
    t0 = cell_for("PQ", "fam05", "T0", universe)
    t1 = cell_for("PQ", "fam05", "T1", universe)
    build_model_run(ROOT, cell=t0, freeze_commit=FREEZE, solver_py=solver0)
    build_model_run(ROOT, cell=t1, freeze_commit=FREEZE, solver_py=solver1)
    return t0, t1


def main():
    global ROOT
    ROOT = setup()

    # ---- A12.1 authorization: the controller derives the event ----------
    refuses("empty tree: advance refuses with ACQUISITION-REQUIRED",
            promotion.advance, "ACQUISITION-REQUIRED", ROOT, "PQ", "fam05", "A")
    refuses("empty tree: lock_universe refuses (not the next event)",
            promotion.lock_universe, "LOCK-DENY", ROOT, "PQ", "fam05", "A")
    refuses("empty tree: promote_universe refuses (not the next event)",
            promotion.promote_universe, "PROMOTION-DENY", ROOT, "PQ", "fam05",
            "A")
    refuses("fam03 governance while fam05 active refuses",
            promotion.promote_universe, "PROMOTION-DENY", ROOT, "PQ", "fam03",
            "A")
    st = order.cell_state(ROOT, cell_for("PQ", "fam03", "PROMOTION", "A"),
                          FREEZE)
    ok("fam03 PROMOTION not COMPLETE while fam05 active",
       st["status"] != "COMPLETE", st["status"])
    refuses("T0 alone does not authorize promotion",
            promotion.promote_universe, "PROMOTION-DENY", ROOT, "PQ", "fam05",
            "A")
    t0, t1 = build_pair()
    ok("T0 COMPLETE after fixture", order.cell_state(ROOT, t0, FREEZE)["status"]
       == "COMPLETE", order.cell_state(ROOT, t0, FREEZE)["reasons"][:1])
    ok("T1 COMPLETE after fixture", order.cell_state(ROOT, t1, FREEZE)["status"]
       == "COMPLETE", order.cell_state(ROOT, t1, FREEZE)["reasons"][:1])
    st = order.cell_state(ROOT, cell_for("PQ", "fam05", "PROMOTION", "A"),
                          FREEZE)
    ok("C/A PROMOTION still refuses before A governance runs",
       st["status"] != "COMPLETE", st["status"])

    # ---- A12.1 promotion ------------------------------------------------
    res = promotion.advance(ROOT, "PQ", "fam05", "A", FREEZE,
                            evidence_grade="harness-validation")
    ok("advance executes PROMOTION first", res["event"] == "PROMOTION")
    rec = json.load(open(res["receipt"]))
    ok("receipt names exactly the 3 capability artifacts",
       set(rec["artifacts"]) == set(promotion.ARTIFACT_NAMES),
       sorted(rec["artifacts"]))
    ok("candidate sha256 is the T0 arrival payload hash",
       rec["candidate"]["sha256"]
       == __import__("hashlib").sha256(SOLVER_T0.encode()).hexdigest())
    ok("receipt binds T0/T1 source cells",
       rec["source_cells"] == {"T0": t0["cell_id"], "T1": t1["cell_id"]})
    ok("receipt carries authorization.event_index == frozen index",
       rec["authorization"]["event_index"]
       == cell_for("PQ", "fam05", "PROMOTION", "A")["index"])
    ok("receipt carries the frozen semantic contract",
       bool(rec["semantic_core"]) and bool(rec["preconditions"]))
    ok("harness-validation promotion is explicitly UNRATIFIED",
       rec["t4_ratified"] is False and rec["t4_semantic_id"].startswith(
           "T4-UNRATIFIED-"))
    st = order.cell_state(ROOT, cell_for("PQ", "fam05", "PROMOTION", "A"),
                          FREEZE)
    ok("PROMOTION cell COMPLETE", st["status"] == "COMPLETE",
       st["reasons"][:2])
    capdir = order.capability_dir(ROOT, "PQ", "A", "fam05")
    ok("engine.py present in the derived capability dir",
       os.path.isfile(os.path.join(capdir, "engine.py")))
    engine_src = open(os.path.join(capdir, "engine.py")).read()
    ok("engine embeds the candidate source verbatim",
       "def solve(input_dir, output_path):" in engine_src
       and rec["candidate"]["sha256"] in engine_src)

    # ---- A12.2 estimand-aware lock -------------------------------------
    res2 = promotion.advance(ROOT, "PQ", "fam05", "A", FREEZE,
                             evidence_grade="harness-validation")
    ok("advance executes CAPABILITY_LOCK next",
       res2["event"] == "CAPABILITY_LOCK")
    lk = json.load(open(res2["lock"]))
    reasons = LOCK.verify_lock(lk, expect={
        "capability_id": "fam05-PQ-A-K", "block": "PQ", "universe": "A",
        "family": "fam05", "candidate_sha256": rec["candidate"]["sha256"]})
    ok("minted lock passes the full estimand contract", not reasons,
       reasons[:2])
    ok("lock artifacts == receipt-named artifacts",
       set(lk["artifacts"]) == set(rec["artifacts"])
       and all(lk["artifacts"][k] == rec["artifacts"][k]
               for k in rec["artifacts"]))
    ok("lock binds candidate_provenance_sha256 == receipt sha",
       lk["candidate_provenance_sha256"] == res["receipt_sha256"])
    ok("lock carries T0/T1 tips + source cells",
       lk["acquisition_chain_tips"] == rec["acquisition_chain_tips"]
       and lk["source_cells"] == rec["source_cells"])
    st = order.cell_state(ROOT, cell_for("PQ", "fam05", "CAPABILITY_LOCK", "A"),
                          FREEZE)
    ok("CAPABILITY_LOCK cell COMPLETE", st["status"] == "COMPLETE",
       st["reasons"][:2])
    done = order.completed_cells(ROOT, FREEZE)
    ok("four A-universe fam05 cells are COMPLETE",
       all(cell_for("PQ", "fam05", ev, "A")["cell_id"] in done
           for ev in ("T0", "T1", "PROMOTION", "CAPABILITY_LOCK")))
    ok("C-universe fam05 cells are still not COMPLETE",
       all(cell_for("PQ", "fam05", ev, "C")["cell_id"] not in done
           for ev in ("T0", "T1", "PROMOTION", "CAPABILITY_LOCK")))
    refuses("no repromotion after the pair is locked",
            promotion.advance, "PROMOTION-DENY", ROOT, "PQ", "fam05", "A")
    refuses("lock widening refused (extra operator artifact)",
            promotion.order.emit_capability_lock, "LOCK-DENY", ROOT,
            cell_for("PQ", "fam05", "CAPABILITY_LOCK", "A"),
            artifact_paths=[os.path.join(capdir, "engine.py"),
                            os.path.join(capdir, "manifest.json"),
                            os.path.join(capdir, "adapter_notes.md"),
                            os.path.join(capdir, "CAPABILITY_LOCK.json")],
            receipt=rec, receipt_path=res["receipt"])
    refuses("estimand grade without a ratified T4 id refuses",
            promotion.t4_semantic_id, "PROMOTION-DENY", ROOT, "fam05-PQ-C-K",
            "0" * 64, "estimand")

    # ---- attacks: provenance, order, legacy locks ----------------------
    exp = order.load_expansion(ROOT)
    cprom = order.expected_event(exp, "PQ", "fam05", "PROMOTION", "C")
    crun = order.run_dir(ROOT, cprom)
    order.ensure_namespace(ROOT, "PQ", "C", "fam05",
                           tail=("runs", cprom["cell_id"]))
    forged = dict(rec)
    forged["cell_id"] = cprom["cell_id"]
    forged["universe"] = "C"
    forged["capability_id"] = cprom["capability_id"]
    json.dump(forged, open(os.path.join(crun, "PROMOTION-RECEIPT.json"), "w"))
    st = order.cell_state(ROOT, cprom, FREEZE)
    ok("preplanted future receipt never becomes COMPLETE",
       st["status"] != "COMPLETE", f"{st['status']}: {st['reasons'][:1]}")
    # copy A's artifacts into C's capability dir: still not lockable
    ccap = order.capability_dir(ROOT, "PQ", "C", "fam05")
    order.ensure_namespace(ROOT, "PQ", "C", "fam05", tail=("capability",))
    for n in promotion.ARTIFACT_NAMES:
        shutil.copy2(os.path.join(capdir, n), os.path.join(ccap, n))
    refuses("copying A's artifact into C does not authorize a C lock",
            promotion.order.emit_capability_lock, "LOCK-INADMISSIBLE", ROOT,
            cell_for("PQ", "fam05", "CAPABILITY_LOCK", "C"),
            artifact_paths=[os.path.join(ccap, n)
                            for n in promotion.ARTIFACT_NAMES])
    # tamper the promoted engine bytes
    eng = os.path.join(capdir, "engine.py")
    original = open(eng).read()
    open(eng, "w").write(original + "\n# tampered\n")
    st = order.cell_state(ROOT, cell_for("PQ", "fam05", "PROMOTION", "A"),
                          FREEZE)
    ok("mutated locked artifact invalidates PROMOTION",
       st["status"] != "COMPLETE"
       and any("engine.py" in r for r in st["reasons"]),
       st["reasons"][:2])
    st = order.cell_state(ROOT,
                          cell_for("PQ", "fam05", "CAPABILITY_LOCK", "A"),
                          FREEZE)
    ok("mutated locked artifact invalidates CAPABILITY_LOCK",
       st["status"] != "COMPLETE", st["status"])
    open(eng, "w").write(original)
    st = order.cell_state(ROOT, cell_for("PQ", "fam05", "PROMOTION", "A"),
                          FREEZE)
    ok("restoring the bytes restores COMPLETE", st["status"] == "COMPLETE",
       st["reasons"][:1])
    # tamper the receipt's candidate root
    rp = res["receipt"]
    good = json.load(open(rp))
    for name, patch, token in (
            ("candidate.sha256", {"sha256": "f" * 64},
             "causally rooted"),
            ("authorization", {"authorization": None}, "authorization"),
            ("t4_ratified", {"t4_ratified": True}, "RATIFIED"),
            ("semantic_core", {"semantic_core": "rewritten contract"},
             "frozen"),
            ("tips", {"acquisition_chain_tips": {"T0": "a" * 64,
                                                 "T1": "b" * 64}},
             "chain ends at")):
        bad = json.loads(json.dumps(good))
        if name == "candidate.sha256":
            bad["candidate"]["sha256"] = patch["sha256"]
        else:
            bad.update(patch)
        json.dump(bad, open(rp, "w"))
        st = order.cell_state(ROOT,
                              cell_for("PQ", "fam05", "PROMOTION", "A"),
                              FREEZE)
        ok(f"tampered receipt ({name}) invalidates PROMOTION",
           st["status"] != "COMPLETE"
           and any(token in r for r in st["reasons"]),
           f"{st['status']}: {st['reasons'][:1]}")
    json.dump(good, open(rp, "w"))
    ok("restoring the receipt restores COMPLETE",
       order.cell_state(ROOT, cell_for("PQ", "fam05", "PROMOTION", "A"),
                        FREEZE)["status"] == "COMPLETE")
    # legacy lock refusal
    legacy_dir = os.path.join(ROOT, "legacy")
    os.makedirs(legacy_dir, exist_ok=True)
    legacy = {"capability_id": "x-K", "version": "1.0.0",
              "artifacts": {"engine.py": "0" * 64},
              "promotion_receipt_sha256": "0" * 64, "manifest": {},
              "manifest_sha256": "0" * 64, "locked_at": "t"}
    reasons = LOCK.verify_lock(legacy)
    ok("legacy lock is LOCK-INADMISSIBLE",
       any("LOCK-INADMISSIBLE" in r and "legacy" in r for r in reasons),
       reasons[:1])
    legacy_path = os.path.join(legacy_dir, "LOCK.json")
    json.dump(legacy, open(legacy_path, "w"))
    open(os.path.join(legacy_dir, "engine.py"), "w").write("x")
    refuses("load_artifact refuses a legacy lock", LOCK.load_artifact,
            "LOCK-INADMISSIBLE", legacy_path, "engine.py", legacy_dir)
    ok("promotion cannot mint a lock without the estimand field set",
       _promote_missing_refuses())

    passed = sum(1 for _n, c, _d in CHECKS if c)
    total = len(CHECKS)
    for name, cond, detail in CHECKS:
        if not cond:
            print(f"FAIL {name}: {detail}")
    print(f"H13 promotion smoke: {passed}/{total} closed")
    return 0 if passed == total else 1


def _promote_missing_refuses():
    try:
        LOCK.promote("/tmp/h13-nope", "x-K", "1.0.0", [], {}, [], {})
    except ValueError as e:
        return "LOCK-INADMISSIBLE" in str(e)
    except Exception:  # noqa: BLE001
        return False
    return False


if __name__ == "__main__":
    raise SystemExit(main())

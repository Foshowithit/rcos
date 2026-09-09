#!/usr/bin/env python3
"""H7 adversarial smoke — item 7 + round-3 A11.4/A11.5/A11.6.

Frozen order expansion over the FULL event universe (T0, T1, PROMOTION,
CAPABILITY_LOCK, T2, T3, T4) with per-universe namespaces and validated
cell state. Every unauthorized invocation must FAIL CLOSED; exit 0 only if
all green. Stdlib only, no network, no model, no docker.

The round-3 audit found this suite proving a weaker rule than the prereg
requires (it declared "cell 0 = fam05/T2/A", a downstream cell whose
capability had never been acquired, and it accepted any capability dir
anywhere inside Fam-C). Those assertions are DELETED and replaced here.
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

import order as ORD
import run_arm_h1 as RA

BASE = "/tmp/h7-smoke"
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


os.system("rm -rf " + BASE)
os.makedirs(BASE)

ORDER_TEXT = open(os.path.join(FAMC, "ORDER.md")).read()
EXP = ORD.expand(ORDER_TEXT)
CELLS = EXP["cells"]


def cell(block, family, event, universe):
    for c in CELLS:
        if (c["block"] == block and c["family"] == family
                and c["event"] == event and c["universe"] == universe):
            return c
    return None


def idx(block, family, event, universe):
    c = cell(block, family, event, universe)
    return None if c is None else c["index"]


# --- A11.4: mechanical expansion covers the whole event universe ---
check("expansion covers the full per-family event sequence",
      EXP["events"] == ["T0", "T1", "PROMOTION", "CAPABILITY_LOCK",
                        "T2", "T3", "T4"], str(EXP["events"]))
check("expansion enumerates 240 events (8 acquisition + 12 downstream "
      "per block/family)",
      EXP["total_cells"] == 240 and EXP["total_model_calls"] == 192,
      f'{EXP["total_cells"]}/{EXP["total_model_calls"]}')
check("family order == frozen seed order",
      EXP["families"] == ["fam05", "fam03", "fam01", "fam04", "fam06", "fam02"],
      str(EXP["families"]))
check("block order PQ then QP", EXP["blocks"] == ["PQ", "QP"])
check("event 0 is fam05 acquisition T0/A on the producer lane",
      [CELLS[0][k] for k in ("family", "event", "universe", "lane", "kind")]
      == ["fam05", "T0", "A", "P", "acquisition-solve"], str(CELLS[0]))
check("A-vs-C acquisition order resolved: PQ/A/fam05/T0 before "
      "PQ/C/fam05/T0",
      idx("PQ", "fam05", "T0", "A") < idx("PQ", "fam05", "T0", "C"))
check("A universe runs T0,T1,PROMOTION,CAPABILITY_LOCK before C's T0",
      [idx("PQ", "fam05", e, "A") for e in
       ("T0", "T1", "PROMOTION", "CAPABILITY_LOCK")]
      == [0, 1, 2, 3] and idx("PQ", "fam05", "T0", "C") == 4)
check("C universe runs its own T0,T1,PROMOTION,CAPABILITY_LOCK",
      [idx("PQ", "fam05", e, "C") for e in
       ("T0", "T1", "PROMOTION", "CAPABILITY_LOCK")] == [4, 5, 6, 7])
check("downstream starts only after both universes are locked",
      min(c["index"] for c in CELLS if c["kind"] == "model-call") == 8
      and idx("PQ", "fam05", "T2", "A") == 8)
check("B and D have no acquisition/promotion events (no K universe)",
      not [c for c in CELLS if c["kind"] != "model-call"
           and c["universe"] in ("B", "D")])
check("capability-bearing universes are exactly A and C",
      sorted({c["universe"] for c in CELLS
              if c["kind"] != "model-call"}) == ["A", "C"])
check("fam05 downstream letter order A,B,C,D",
      [c["letter"] for c in CELLS if c["block"] == "PQ"
       and c["family"] == "fam05" and c["event"] == "T2"]
      == ["A", "B", "C", "D"])
check("fam03 letter order flipped B,A,D,C",
      [c["letter"] for c in CELLS if c["block"] == "PQ"
       and c["family"] == "fam03" and c["event"] == "T2"]
      == ["B", "A", "D", "C"])
check("QP block primed (lane roles swapped)",
      all(c["primed"] for c in CELLS if c["block"] == "QP")
      and all(not c["primed"] for c in CELLS if c["block"] == "PQ"))
check("QP acquisition uses the Q producer lane",
      cell("QP", "fam05", "T0", "A")["producer_lane"] == "Q"
      and cell("QP", "fam05", "T0", "C")["lane"] == "P")
check("A and C carry distinct capability ids (PREREG §2)",
      cell("PQ", "fam05", "T0", "A")["capability_id"]
      != cell("PQ", "fam05", "T0", "C")["capability_id"])
check("cell ids unique", len({c["cell_id"] for c in CELLS}) == 240)
check("committed ORDER-EXPANSION.json matches ORDER.md",
      ORD.verify_expansion(FAMC) == [], str(ORD.verify_expansion(FAMC)))

# --- derivation drift fails closed ---
tmp = os.path.join(BASE, "famc-drift")
os.makedirs(tmp)
shutil.copy2(os.path.join(FAMC, "ORDER.md"), os.path.join(tmp, "ORDER.md"))
good = json.load(open(os.path.join(FAMC, "ORDER-EXPANSION.json")))
bad = json.loads(json.dumps(good))
bad["cells"][5]["family"] = "fam99"          # hand-edited cell
json.dump(bad, open(os.path.join(tmp, "ORDER-EXPANSION.json"), "w"))
check("hand-edited expansion fails derivation",
      ORD.verify_expansion(tmp) != [])
bad2 = json.loads(json.dumps(good))
bad2["order_sha256"] = "0" * 64
json.dump(bad2, open(os.path.join(tmp, "ORDER-EXPANSION.json"), "w"))
check("stale order_sha256 fails derivation",
      any("order_sha256" in f for f in ORD.verify_expansion(tmp)))
bad3 = json.loads(json.dumps(good))
bad3["cells"] = [c for c in bad3["cells"] if c["event"] != "T0"]
json.dump(bad3, open(os.path.join(tmp, "ORDER-EXPANSION.json"), "w"))
check("expansion missing acquisition events fails derivation",
      ORD.verify_expansion(tmp) != [])
open(os.path.join(tmp, "ORDER.md"), "w").write(
    ORDER_TEXT.replace("fam05, fam03", "fam03, fam05"))
check("reordered ORDER.md makes the committed expansion stale",
      ORD.verify_expansion(tmp) != [])

# --- authorization: the sequence is the authority ---
def auth(block, family, task, lane, arm, done=None):
    return ORD.authorize(EXP, block, family, task, lane, arm, done or {})


def all_done(**kw):
    return {c["cell_id"]: "run-" + c["cell_id"] for c in CELLS
            if all(c[k] == v for k, v in kw.items())}


def done_before(i):
    """Every cell strictly earlier than index i — the only state in which
    cell i may start."""
    return {c["cell_id"]: "run-" + c["cell_id"] for c in CELLS
            if c["index"] < i}


def auth_ev(block, family, event, universe, done=None):
    return ORD.authorize_event(EXP, block, family, event, universe,
                               done or {})


def done_before(i):
    """Every cell strictly earlier than index i — the only state in which
    cell i may start."""
    return {c["cell_id"]: "run-" + c["cell_id"] for c in CELLS
            if c["index"] < i}


def auth_ev(block, family, event, universe, done=None):
    return ORD.authorize_event(EXP, block, family, event, universe,
                               done or {})


def auth_ev(block, family, event, universe, done=None):
    return ORD.authorize_event(EXP, block, family, event, universe,
                               done or {})


cell0, f0 = auth("PQ", "fam05", "T2", "P", "correct")
check("downstream T2 refused with nothing done, naming the T0/A acquisition",
      cell0 is not None and any("out of order" in x and "fam05/T0/A" in x
                                for x in f0), str(f0))
fam05_done = done_before(idx("PQ", "fam05", "T2", "A"))
cell1, f1 = auth("PQ", "fam05", "T2", "P", "correct", fam05_done)
check("T2 authorized once fam05's acquisition+promotion are complete",
      not f1, str(f1))
check("fam01 before fam05 refused as out of order",
      any("out of order" in x and "fam05" in x
          for x in auth("PQ", "fam01", "T2", "P", "correct")[1]))
check("QP before PQ completes refused as out of order",
      any("out of order" in x
          for x in auth("QP", "fam05", "T2", "Q", "correct")[1]))
pq_done = all_done(block="PQ")
ev2, f2 = auth_ev("QP", "fam05", "T0", "A", pq_done)
check("QP acquisition authorized once PQ is complete", not f2, str(f2))
c2b, f2b = auth("QP", "fam05", "T2", "Q", "correct", pq_done)
check("QP downstream still refused until QP's OWN acquisition runs",
      any("out of order" in x and "QP/fam05/T0/A" in x for x in f2b),
      str(f2b))
check("duplicate completed cell refused",
      any("duplicate cell" in x for x in auth(
          "PQ", "fam05", "T2", "P", "correct",
          {EXP["cells"][8]["cell_id"]: "r0"})[1]))
check("wrong family universe refused",
      any("outside the frozen universe" in x
          for x in auth("PQ", "fam99", "T2", "P", "correct")[1]))
check("downstream task universe T9 refused",
      any("outside the frozen downstream universe" in x
          for x in auth("PQ", "fam05", "T9", "P", "correct")[1]))
check("acquisition event through the model-call entry point refused",
      any("not model calls" in x
          for x in auth("PQ", "fam05", "T0", "P", "correct")[1]))
check("unknown block refused",
      any("unknown block" in x
          for x in auth("QQ", "fam05", "T2", "P", "correct")[1]))
check("unknown lane refused",
      any("no authorized cell" in x
          for x in auth("PQ", "fam05", "T2", "X", "correct",
                        fam05_done)[1]))
check("unknown arm refused",
      any("unknown arm" in x
          for x in auth("PQ", "fam05", "T2", "P", "sideways",
                        fam05_done)[1]))
cell3, f3 = auth("PQ", "fam05", "T2", "P", "disabled",
                 done_before(idx("PQ", "fam05", "T2", "B")))
check("second cell of the pair runs once the first is complete",
      not f3, str(f3))
c4, f4 = auth("PQ", "fam05", "T3", "P", "correct",
              done_before(idx("PQ", "fam05", "T2", "B")))
check("later task refused while an earlier cell is missing",
      any("out of order" in x and "fam05/T2/B" in x for x in f4), str(f4))
check("a cell cannot run on another universe's completion",
      any("out of order" in x for x in auth(
          "PQ", "fam05", "T2", "Q", "correct",
          done_before(idx("PQ", "fam05", "T2", "A")))[1]))


# --- acquisition-event authorization ---
ev, ef = auth_ev("PQ", "fam05", "T0", "A")
check("first acquisition event authorized with nothing done",
      not ef and ev["index"] == 0, str(ef))
check("C acquisition refused before A's promotion and lock",
      any("out of order" in x for x in
          auth_ev("PQ", "fam05", "T0", "C")[1]))
check("C acquisition authorized once A is complete",
      not auth_ev("PQ", "fam05", "T0", "C",
                  done_before(idx("PQ", "fam05", "T0", "C")))[1])
check("B/D acquisition refused (no capability universe)",
      all(any("carries no capability" in x for x in
              auth_ev("PQ", "fam05", "T0", u)[1]) for u in ("B", "D")))
check("unknown acquisition event refused",
      any("unknown acquisition event" in x
          for x in auth_ev("PQ", "fam05", "T5", "A")[1]))

# --- A11.5: derived namespaces, hard A/C isolation ---
a_cell = cell("PQ", "fam05", "T2", "A")
c_cell = cell("PQ", "fam05", "T2", "C")
cap_a, out_a = ORD.derive_paths(FAMC, a_cell)
cap_c, out_c = ORD.derive_paths(FAMC, c_cell)
check("derived capability dirs are per-universe",
      cap_a.endswith("state/PQ/A/fam05/capability")
      and cap_c.endswith("state/PQ/C/fam05/capability"), cap_a + " | " + cap_c)
check("derived run dir is per-cell",
      out_a.endswith(os.path.join("runs", a_cell["cell_id"])), out_a)
check("A and C namespaces do not overlap",
      not cap_a.startswith(cap_c) and not cap_c.startswith(cap_a))
check("C cell may not use A's registry",
      ORD.check_namespace(FAMC, c_cell, cap_a) is not None)
check("C cell may use its own registry",
      ORD.check_namespace(FAMC, c_cell, cap_c) is None)
inside_famc = os.path.join(FAMC, "capabilities")
check("a capability dir inside Fam-C but outside the universe is refused",
      ORD.check_namespace(FAMC, c_cell, inside_famc) is not None)
try:
    RA._verify_capability(inside_famc, cell=c_cell)
    check("runner capability gate refuses the wrong universe", False,
          "accepted")
except PermissionError as e:
    check("runner capability gate refuses the wrong universe",
          "FOREIGN-REGISTRY-DENY" in str(e), str(e)[:120])
foreign = os.path.join(BASE, "foreign-cap")
os.makedirs(foreign)
try:
    RA._verify_capability(foreign)
    check("foreign registry outside Fam-C refused", False, "no refusal")
except PermissionError as e:
    check("foreign registry outside Fam-C refused",
          "FOREIGN-REGISTRY-DENY" in str(e), str(e)[:120])

# --- A11.6: validated cell state, not manifest presence ---
state_root = os.path.join(BASE, "famc-state")
os.makedirs(state_root)
shutil.copy2(os.path.join(FAMC, "ORDER.md"),
             os.path.join(state_root, "ORDER.md"))
json.dump(good, open(os.path.join(state_root, "ORDER-EXPANSION.json"), "w"))
tcell = cell("PQ", "fam05", "T2", "A")
rdir = ORD.run_dir(state_root, tcell)
os.makedirs(rdir)


def tighten(p):
    """The session umask (002) leaves 0775 intermediates, which the A11.6
    lstat ancestry rule correctly refuses. Make the probe tree clean 0755
    (exactly as the H10 namespace suite does); symlinks are never chmodded."""
    base = os.path.abspath(BASE)
    p = os.path.abspath(p)
    while p.startswith(base):
        if os.path.isdir(p) and not os.path.islink(p):
            os.chmod(p, 0o755)
        if p == base:
            break
        p = os.path.dirname(p)


tighten(rdir)
FREEZE_COMMIT = "f" * 40
manifest = {"wired": True, "dev_mode": False,
            "cell_id": tcell["cell_id"], "cell_index": tcell["index"],
            "block": tcell["block"], "family": tcell["family"],
            "task": tcell["task"], "cell_event": tcell["event"],
            "cell_kind": tcell["kind"], "cell_universe": tcell["universe"],
            "cell_letter": tcell["letter"], "lane": tcell["lane"],
            "arm": tcell["arm"], "capability_id": tcell["capability_id"],
            "order_sha256": good["order_sha256"],
            "instance_freeze_commit": FREEZE_COMMIT}
mf = os.path.join(rdir, "H1-RUN-MANIFEST.json")
CHAIN_PATH = os.path.join(rdir, "EVIDENCE-CHAIN.jsonl")

# A12.3: a wired run carries the unified arrival decision AND the reuse
# ledger record DERIVED from it. This T2 fixture chose fresh WITH the
# capability available => the REJECT path, written by the production writer.
json.dump({"decision": "fresh",
           "execution_payload": {"solver_py": "print('h7 fixture')\n"},
           "notes": "h7 smoke: fresh with capability available"},
          open(os.path.join(rdir, "arrival.json"), "w"))
import reuse_log as RL                                        # noqa: E402
REUSE_NAME = os.path.basename(RL.write_record(
    rdir, tcell["task"], tcell["lane"], tcell["arm"],
    reuse_policy="capability-first", capability_available=True,
    capability_candidate_ids=[tcell["capability_id"]],
    capability_selected=False, selected_capability_id=None,
    selected_capability_hash=None, capability_loaded=False,
    capability_invoked=False, capability_output_consumed=False,
    capability_materially_contributed=False, contribution_evidence=None,
    reuse_rejected=True,
    reuse_rejection_reason="fresh: solver-only run (h7 fixture)"))
manifest["reuse_record"] = REUSE_NAME
json.dump(manifest, open(mf, "w"))


def build_real_chain(manifest_obj):
    """Write a REAL evidence chain (genesis + evaluator + terminal grade)
    through the production Chain authority. A11b.5: H7 exercises the REAL
    module-level verify_chain(); no stub may hide it."""
    if os.path.exists(CHAIN_PATH):
        os.unlink(CHAIN_PATH)
    import chain as CH
    c = CH.Chain(CHAIN_PATH, FREEZE_COMMIT, manifest_obj)
    ev = c.append("evaluator", {"evaluator": "h7-smoke", "verdict": "ship"})
    c.append("grade", {"evaluator_link_hash": ev,
                       "grading_rule_hash": "0" * 64,
                       "grading_rule_version": "h7-smoke-1"})
    return c


build_real_chain(manifest)

# Only the admissibility classifier is stubbed (a different authority, and
# H4/H3 exercise the real one end-to-end); the chain verifier is REAL here,
# so a stubbed chain can no longer make a fabricated manifest look valid.
real_adm = sys.modules.get("admissibility")
stub_adm = types.ModuleType("admissibility")
stub_adm.ELIGIBLE = "ELIGIBLE"
stub_adm.EXCLUDED = "EXCLUDED"
stub_adm.classify_run_dir = lambda d, fc=None: ("ELIGIBLE", "ok")
sys.modules["admissibility"] = stub_adm
try:
    # A12.1 two-level contract: `_local_state` is the LOCAL evidence gate;
    # order-aware `cell_state` additionally requires every EARLIER cell of
    # the frozen expansion to be COMPLETE. This fixture tree holds exactly
    # one T2 cell, so the local gate is COMPLETE while the order-aware state
    # must be INADMISSIBLE with the named ORDER-INADMISSIBLE reason.
    stl = ORD._local_state(state_root, tcell)
    check("local evidence gate COMPLETE with manifest+chain+admissibility",
          stl["status"] == "COMPLETE", str(stl))
    st = ORD.cell_state(state_root, tcell)
    check("order guard: T2 cannot be COMPLETE while 8 earlier cells are not",
          st["status"] != "COMPLETE"
          and any("ORDER-INADMISSIBLE" in r for r in st["reasons"]), str(st))
    done = ORD.completed_cells(state_root, expansion=good)
    check("progress ledger consumes validated cell state (prefix rule)",
          done == {}, str(done))

    # A12.3 ledger-vs-decision: a record that contradicts the arrival's own
    # executed decision must be refused, and a fresh decision made WITH a
    # capability available must be recorded as an explicit REJECT.
    rp = os.path.join(rdir, REUSE_NAME)
    good_rec = json.load(open(rp))
    json.dump(dict(good_rec, capability_selected=True, capability_loaded=True,
                   capability_invoked=True, capability_output_consumed=True,
                   reuse_rejected=False), open(rp, "w"))
    stl2 = ORD._local_state(state_root, tcell)
    check("ledger claiming reuse while the arrival chose fresh is refused",
          stl2["status"] != "COMPLETE"
          and any("reuse-ledger" in r for r in stl2["reasons"]),
          str(stl2["reasons"][:1]))
    json.dump(dict(good_rec, reuse_rejected=False), open(rp, "w"))
    stl3 = ORD._local_state(state_root, tcell)
    check("fresh with a capability available must be recorded as REJECT",
          stl3["status"] != "COMPLETE"
          and any("reuse_rejected" in r for r in stl3["reasons"]),
          str(stl3["reasons"][:1]))
    json.dump(good_rec, open(rp, "w"))
    check("ledger restored -> local gate COMPLETE again",
          ORD._local_state(state_root, tcell)["status"] == "COMPLETE")

    stub_adm.classify_run_dir = lambda d, fc=None: ("EXCLUDED", "no identity")
    st2 = ORD.cell_state(state_root, tcell)
    check("inadmissible artifacts do not count as complete",
          st2["status"] != "COMPLETE"
          and any("admissibility EXCLUDED" in r for r in st2["reasons"]),
          str(st2))
    check("inadmissible run does not advance the order",
          ORD.completed_cells(state_root, expansion=good) == {})

    stub_adm.classify_run_dir = lambda d, fc=None: ("ELIGIBLE", "ok")
    # Real chain tampering: alter a written link's payload. The REAL
    # verifier must detect the post-write content change.
    lines = open(CHAIN_PATH).read().splitlines()
    rec = json.loads(lines[-1])
    rec["payload"]["verdict"] = "forged"
    lines[-1] = json.dumps(rec, sort_keys=True)
    open(CHAIN_PATH, "w").write("\n".join(lines) + "\n")
    st3 = ORD.cell_state(state_root, tcell)
    check("broken evidence chain does not count as complete",
          st3["status"] != "COMPLETE"
          and any("evidence chain invalid" in r for r in st3["reasons"]),
          str(st3))
    build_real_chain(manifest)

    manifest_bad = dict(manifest, cell_id="0000deadbeef0000")
    json.dump(manifest_bad, open(mf, "w"))
    st4 = ORD.cell_state(state_root, tcell)
    check("manifest claiming another cell does not count",
          st4["status"] != "COMPLETE"
          and any("cell_id" in r for r in st4["reasons"]), str(st4))
    manifest_dev = dict(manifest, dev_mode=True)
    json.dump(manifest_dev, open(mf, "w"))
    st5 = ORD.cell_state(state_root, tcell)
    check("dev-mode manifest does not count",
          st5["status"] != "COMPLETE", str(st5))
    json.dump(manifest, open(mf, "w"))
finally:
    if real_adm is None:
        sys.modules.pop("admissibility", None)
    else:
        sys.modules["admissibility"] = real_adm

# a dangling symlink manifest must never count as complete
dangle_dir = os.path.join(state_root, "state", "PQ", "A", "fam03", "runs",
                          cell("PQ", "fam03", "T2", "A")["cell_id"])
os.makedirs(dangle_dir)
os.symlink("/nonexistent/manifest.json",
           os.path.join(dangle_dir, "H1-RUN-MANIFEST.json"))
st6 = ORD.cell_state(state_root, cell("PQ", "fam03", "T2", "A"))
check("dangling symlink manifest does not count",
      st6["status"] != "COMPLETE", str(st6))

# --- the runner itself refuses before any model call ---
def run_runner(args):
    return subprocess.run([sys.executable, RUNNER] + args,
                          capture_output=True, text=True, timeout=180)


r = run_runner(["P", "fam05", "T2", "correct", "/tmp/h7-out"])
check("runner without --block refuses (ORDER-DENY)",
      r.returncode != 0 and "ORDER-DENY" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["Q", "fam05", "T2", "correct", "/tmp/h7-out", "--block", "QP"])
check("runner QP-before-PQ refuses before any call",
      r.returncode != 0 and "out of order" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["P", "fam01", "T2", "correct", "/tmp/h7-out",
                "--block", "PQ"])
check("runner fam01-before-fam05 refuses before any call",
      r.returncode != 0 and "out of order" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["P", "fam99", "T2", "correct", "/tmp/h7-out",
                "--block", "PQ"])
check("runner foreign family refuses before any call",
      r.returncode != 0 and "frozen universe" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["P", "fam05", "T2", "correct", "/tmp/h7-out",
                "--block", "PQ"])
check("runner downstream cell refuses while acquisition is outstanding",
      r.returncode != 0 and "out of order" in (r.stderr + r.stdout)
      and "fam05/T0/A" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-240:])

# derived-path enforcement (A11.5) at the runner's own gate: authorize a
# cell synthetically and prove a free outdir/capdir is refused BEFORE any
# model call is attempted.
_orig_auth = RA.order_authorize
_orig_done = RA.order_completed_cells
try:
    RA.order_authorize = lambda exp, b, f, t, l, a, d: (
        cell("PQ", "fam05", "T2", "A"), [])
    RA.order_completed_cells = lambda famc, **kw: {}
    try:
        RA.main("P", "fam05", "T2", "correct", "/tmp/h7-free-out",
                os.path.join(BASE, "foreign-cap"), {"block": "PQ"})
        check("runner refuses a free capability path", False, "accepted")
    except PermissionError as e:
        check("runner refuses a free capability path",
              "FOREIGN-REGISTRY-DENY" in str(e), str(e)[:160])
    except Exception as e:                                   # noqa: BLE001
        check("runner refuses a free capability path", False,
              type(e).__name__ + ": " + str(e)[:160])
    try:
        RA.main("P", "fam05", "T2", "correct", "/tmp/h7-free-out",
                cap_a, {"block": "PQ"})
        check("runner refuses a free run directory", False, "accepted")
    except PermissionError as e:
        check("runner refuses a free run directory",
              "run dir must be the derived cell path" in str(e), str(e)[:160])
    except Exception as e:                                   # noqa: BLE001
        check("runner refuses a free run directory", False,
              type(e).__name__ + ": " + str(e)[:160])
finally:
    RA.order_authorize = _orig_auth
    RA.order_completed_cells = _orig_done

# --- the execution lock must be current for the executed bytes ---
r = subprocess.run([sys.executable, "/home/chow/chow-work/rcos/harness/"
                    "mint_execution_lock.py", "--check"],
                   capture_output=True, text=True)
check("EXECUTION-LOCK is current (mint --check exit 0)",
      r.returncode == 0 and "current" in r.stdout,
      (r.stdout + r.stderr)[-200:])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH7 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)

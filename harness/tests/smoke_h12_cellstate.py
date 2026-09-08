#!/usr/bin/env python3
"""H12 adversarial smoke — A11b.4/P0-4: cell_state() dispatches by CELL KIND.

The A11b audit found that PROMOTION and CAPABILITY_LOCK cells were being
validated with the model-run contract, so a governance cell either needed a
fabricated H1-RUN-MANIFEST.json (forging identity/usage/chain evidence for an
event that never called a model) or could never validate at all.

This suite proves the production dispatch on REAL machinery:

  * T0/T1 acquisition cells validate COMPLETE through the model-run contract
    (13 production manifest fields, the REAL chain verifier, and the REAL
    admissibility classifier — no stub hides either);
  * the PROMOTION cell validates COMPLETE only when the receipt binds the
    REAL T0/T1 chain tips re-derived from disk, with NO model-run manifest;
  * the CAPABILITY_LOCK cell validates COMPLETE only when the immutable lock
    binds that promotion receipt and every locked artifact hash still
    verifies;
  * a downstream T2 cell validates COMPLETE once its capability is locked;
  * every mutation (manifest field, chain payload, receipt tip, locked
    artifact bytes, lock/promotion binding, namespace ancestry) FAILS CLOSED.

Stdlib only, no network, no model, no docker. Exit 0 only if all green.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMC = "/home/chow/chow-work/rcos/benchmarks/fam-c"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import order as ORD
import chain as CH

BASE = "/tmp/h12-smoke"
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


os.system("rm -rf " + BASE)
os.makedirs(BASE)
os.chmod(BASE, 0o755)

# The pinned instance-freeze commit. The real admissibility classifier
# compares the manifest anchor against this value, so the fixture is
# classified by production code, not by a stub.
FREEZE_COMMIT = "d1292434a261f44ad910c556e18624cef1676f37"

state_root = os.path.join(BASE, "famc")
os.makedirs(state_root)
os.chmod(state_root, 0o755)
shutil.copy2(os.path.join(FAMC, "ORDER.md"),
             os.path.join(state_root, "ORDER.md"))
EXPANSION = json.load(open(os.path.join(FAMC, "ORDER-EXPANSION.json")))
json.dump(EXPANSION, open(os.path.join(state_root,
                                       "ORDER-EXPANSION.json"), "w"))
ORDER_SHA = ORD.load_expansion(state_root)["order_sha256"]


def cell(event):
    for c in EXPANSION["cells"]:
        if (c["block"] == "PQ" and c["universe"] == "A"
                and c["family"] == "fam05" and c["event"] == event):
            return c
    raise SystemExit(f"no PQ/A/fam05 cell for event {event}")


T0, T1, PROM, LOCK, T2 = (cell("T0"), cell("T1"), cell("PROMOTION"),
                          cell("CAPABILITY_LOCK"), cell("T2"))


def manifest_for(c):
    """The 13 production order-bound fields + the wired/dev/freeze anchors
    exactly as run_arm_h1.py writes them."""
    return {"wired": True, "dev_mode": False,
            "cell_id": c["cell_id"], "cell_index": c["index"],
            "block": c["block"], "family": c["family"], "task": c["task"],
            "cell_event": c["event"], "cell_kind": c["kind"],
            "cell_universe": c["universe"], "cell_letter": c["letter"],
            "lane": c["lane"], "arm": c["arm"],
            "capability_id": c["capability_id"],
            "order_sha256": ORDER_SHA,
            "instance_freeze_commit": FREEZE_COMMIT,
            "usage_receipts": []}


def run_dir_of(c):
    """Create the derived run namespace through the production creator (one
    component at a time at 0755, no-follow) — never a bare makedirs."""
    return ORD.ensure_namespace(state_root, c["block"], c["universe"],
                                c["family"], tail=("runs", c["cell_id"]))


def write_chain(c, m):
    d = run_dir_of(c)
    p = os.path.join(d, "EVIDENCE-CHAIN.jsonl")
    if os.path.exists(p):
        os.unlink(p)
    ch = CH.Chain(p, FREEZE_COMMIT, m)
    ev = ch.append("evaluator", {"evaluator": "h12-smoke",
                                 "cell_id": c["cell_id"], "verdict": "ship"})
    ch.append("grade", {"evaluator_link_hash": ev,
                        "grading_rule_hash": "0" * 64,
                        "grading_rule_version": "h12-smoke-1"})
    return p


def tip_of(c):
    p = os.path.join(run_dir_of(c), "EVIDENCE-CHAIN.jsonl")
    tip = None
    for line in open(p):
        line = line.strip()
        if line:
            tip = json.loads(line)["link_hash"]
    return tip


def complete_model_cell(c):
    """A hermetic, genuinely ELIGIBLE model-run cell: production manifest,
    real evidence chain, identity.json present, no usage receipts (the real
    classifier skips the receipt loops by its own contract)."""
    d = run_dir_of(c)
    m = manifest_for(c)
    json.dump(m, open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w"))
    json.dump({"endpoint": "https://api.router9.com/v1",
               "model_requested": "minimax-m3",
               "model_returned": "minimax-m3"},
              open(os.path.join(d, "identity.json"), "w"))
    write_chain(c, m)
    return d, m


def st(c):
    return ORD.cell_state(state_root, c, FREEZE_COMMIT)


# ---------------------------------------------------------------------------
# A. acquisition cells: model-run contract, REAL verifier + REAL classifier
# ---------------------------------------------------------------------------
for c in (T0, T1):
    complete_model_cell(c)

a0, a1 = st(T0), st(T1)
check("T0 acquisition cell validated COMPLETE (manifest+chain+admissibility)",
      a0["status"] == "COMPLETE", str(a0))
check("T1 acquisition cell validated COMPLETE (manifest+chain+admissibility)",
      a1["status"] == "COMPLETE", str(a1))
check("T0 manifest carries the 13 production order-bound fields",
      set(manifest_for(T0)) >= {"cell_id", "cell_index", "block", "family",
                                "task", "cell_event", "cell_kind",
                                "cell_universe", "cell_letter", "lane",
                                "arm", "capability_id", "order_sha256"})
from admissibility import classify_run_dir, ELIGIBLE
adm_status, adm_why = classify_run_dir(run_dir_of(T0), FREEZE_COMMIT)
check("fixture is ELIGIBLE under the REAL admissibility classifier (no stub)",
      adm_status == ELIGIBLE, f"{adm_status}: {adm_why}")
done = ORD.completed_cells(state_root, expansion=EXPANSION)
check("progress ledger counts exactly the two validated acquisition cells",
      set(done) == {T0["cell_id"], T1["cell_id"]}, str(sorted(done)))

# mutation: a manifest field that disagrees with the authorized cell
d0 = run_dir_of(T0)
mf0 = os.path.join(d0, "H1-RUN-MANIFEST.json")
good0 = manifest_for(T0)
json.dump(dict(good0, cell_index=good0["cell_index"] + 1), open(mf0, "w"))
bad = st(T0)
check("manifest cell_index mutation refused",
      bad["status"] == "INADMISSIBLE"
      and any("manifest cell_index" in r for r in bad["reasons"]), str(bad))
json.dump(good0, open(mf0, "w"))

# mutation: the chain payload was altered after the link was written
cp0 = os.path.join(d0, "EVIDENCE-CHAIN.jsonl")
lines = open(cp0).read().splitlines()
rec = json.loads(lines[-1])
rec["payload"]["verdict"] = "forged"
lines[-1] = json.dumps(rec, sort_keys=True)
open(cp0, "w").write("\n".join(lines) + "\n")
bad = st(T0)
check("chain payload tampering refused by the REAL verifier",
      bad["status"] == "INADMISSIBLE"
      and any("evidence chain invalid" in r for r in bad["reasons"]), str(bad))
write_chain(T0, good0)

# mutation: the manifest claims another universe's capability
json.dump(dict(good0, capability_id="fam05-PQ-C-K"), open(mf0, "w"))
bad = st(T0)
check("manifest claiming another universe's capability refused",
      bad["status"] == "INADMISSIBLE"
      and any("manifest capability_id" in r for r in bad["reasons"]), str(bad))
json.dump(good0, open(mf0, "w"))

# mutation: dev-mode run
json.dump(dict(good0, dev_mode=True), open(mf0, "w"))
bad = st(T0)
check("dev-mode manifest refused", bad["status"] != "COMPLETE"
      and any("not a wired, non-dev run" in r for r in bad["reasons"]),
      str(bad))
json.dump(good0, open(mf0, "w"))
check("T0 restored to COMPLETE after the mutation probes",
      st(T0)["status"] == "COMPLETE", str(st(T0)))

# ---------------------------------------------------------------------------
# B. PROMOTION: governance cell, NO fabricated model-run manifest
# ---------------------------------------------------------------------------
p0 = st(PROM)
check("PROMOTION cell INCOMPLETE while its run dir does not exist yet",
      p0["status"] == "INCOMPLETE"
      and any("run dir absent" in r for r in p0["reasons"]), str(p0))
run_dir_of(PROM)
p0b = st(PROM)
check("PROMOTION cell INCOMPLETE before any receipt",
      p0b["status"] == "INCOMPLETE"
      and any("no promotion receipt" in r for r in p0b["reasons"]), str(p0b))

t0_tip, t1_tip = tip_of(T0), tip_of(T1)
check("T0 and T1 chains have distinct real tips",
      t0_tip != t1_tip and len(t0_tip) == 64 and len(t1_tip) == 64,
      f"{t0_tip} {t1_tip}")

rp = ORD.emit_promotion_receipt(state_root, PROM, t0_tip, t1_tip,
                                builder_identity={"builder": "h12-smoke"})
check("emit_promotion_receipt writes the receipt in the derived run dir",
      os.path.isfile(rp)
      and os.path.dirname(rp) == run_dir_of(PROM), rp)
p1 = st(PROM)
check("PROMOTION cell validated COMPLETE from the real acquisition tips",
      p1["status"] == "COMPLETE", str(p1))
try:
    ORD.emit_promotion_receipt(state_root, PROM, t0_tip, t1_tip)
    rerefused = False
except PermissionError:
    rerefused = True
check("a second promotion of the same universe refuses (no re-promotion)",
      rerefused)
check("PROMOTION run dir contains NO model-run manifest (no fabrication)",
      not os.path.exists(os.path.join(run_dir_of(PROM),
                                      "H1-RUN-MANIFEST.json")))
done = ORD.completed_cells(state_root, expansion=EXPANSION)
check("progress ledger counts the PROMOTION event once validated",
      PROM["cell_id"] in done, str(sorted(done)))

# a fabricated model-run record inside the governance cell must be refused
fm = os.path.join(run_dir_of(PROM), "H1-RUN-MANIFEST.json")
json.dump(manifest_for(PROM), open(fm, "w"))
bad = st(PROM)
check("fabricated model-run manifest in a PROMOTION cell refused",
      bad["status"] == "INADMISSIBLE"
      and any("must not fabricate a model-run" in r for r in bad["reasons"]),
      str(bad))
os.unlink(fm)

# receipt binds a tip the validated chain does not end at
json.dump(dict(json.load(open(rp)),
               acquisition_chain_tips={"T0": "a" * 64, "T1": t1_tip}),
          open(rp, "w"))
bad = st(PROM)
check("promotion receipt binding a bogus T0 tip refused",
      bad["status"] == "INADMISSIBLE"
      and any("binds T0 tip" in r for r in bad["reasons"]), str(bad))

# swapped tips (T0 under T1) must also be refused
json.dump(dict(json.load(open(rp)),
               acquisition_chain_tips={"T0": t1_tip, "T1": t0_tip}),
          open(rp, "w"))
bad = st(PROM)
check("promotion receipt with swapped T0/T1 tips refused",
      bad["status"] == "INADMISSIBLE"
      and any("binds T0 tip" in r for r in bad["reasons"])
      and any("binds T1 tip" in r for r in bad["reasons"]), str(bad))

# receipt naming another universe
json.dump(dict(json.load(open(rp)), universe="C",
               acquisition_chain_tips={"T0": t0_tip, "T1": t1_tip}),
          open(rp, "w"))
bad = st(PROM)
check("promotion receipt for another universe refused",
      bad["status"] == "INADMISSIBLE"
      and any("promotion receipt universe" in r for r in bad["reasons"]),
      str(bad))

# missing receipt
json.dump(dict(json.load(open(rp)), universe="A",
               acquisition_chain_tips={"T0": t0_tip, "T1": t1_tip}),
          open(rp, "w"))
os.unlink(rp)
bad = st(PROM)
check("missing promotion receipt refuses the PROMOTION cell",
      bad["status"] == "INCOMPLETE"
      and any("no promotion receipt" in r for r in bad["reasons"]), str(bad))

# rewrite the receipt directly: the receipt file was deleted above, so the
# writer's once-only rule is satisfied; this is the same content the writer
# produced (the restore path must be exercised without a second promotion.
json.dump({"event": "PROMOTION", "cell_id": PROM["cell_id"],
           "block": PROM["block"], "family": PROM["family"],
           "universe": PROM["universe"],
           "capability_id": PROM["capability_id"],
           "acquisition_chain_tips": {"T0": t0_tip, "T1": t1_tip},
           "timestamp": "2026-09-08T00:00:00Z"}, open(rp, "w"))
check("PROMOTION cell COMPLETE again after restore",
      st(PROM)["status"] == "COMPLETE", str(st(PROM)))

# a deleted acquisition chain voids the promotion rule
cp1 = os.path.join(run_dir_of(T1), "EVIDENCE-CHAIN.jsonl")
shutil.move(cp1, cp1 + ".bak")
bad = st(PROM)
check("promotion whose T1 acquisition is no longer validated refused",
      bad["status"] != "COMPLETE"
      and any("T1 acquisition cell" in r for r in bad["reasons"]), str(bad))
shutil.move(cp1 + ".bak", cp1)
check("PROMOTION cell COMPLETE after the T1 chain is restored",
      st(PROM)["status"] == "COMPLETE", str(st(PROM)))

# ---------------------------------------------------------------------------
# C. CAPABILITY_LOCK: immutable lock bound to the promotion receipt
# ---------------------------------------------------------------------------
capdir = ORD.ensure_namespace(state_root, LOCK["block"], LOCK["universe"],
                              LOCK["family"], tail=("capability",))
art = {}
for name, body in (("engine.py", "def run(fm, rec, out):\n    pass\n"),
                   ("manifest.json", '{"capability_id": "fam05-PQ-A-K"}\n'),
                   ("adapter_notes.md", "h12 fixture\n")):
    p = os.path.join(capdir, name)
    open(p, "w").write(body)
    art[name] = p

c0 = st(LOCK)
check("CAPABILITY_LOCK cell INCOMPLETE before the lock exists",
      c0["status"] == "INCOMPLETE"
      and any("no CAPABILITY_LOCK.json" in r for r in c0["reasons"]), str(c0))

lp = ORD.emit_capability_lock(state_root, LOCK, artifact_paths=art.values(),
                              version="1.0.0",
                              manifest_obj={"capability_id":
                                            LOCK["capability_id"]},
                              builder_identity={"builder": "h12-smoke"})
check("emit_capability_lock writes the immutable lock in the derived dir",
      os.path.isfile(lp) and os.path.dirname(lp) == capdir, lp)
c1 = st(LOCK)
check("CAPABILITY_LOCK cell validated COMPLETE", c1["status"] == "COMPLETE",
      str(c1))
check("CAPABILITY_LOCK dir contains no model-run manifest",
      not os.path.exists(os.path.join(capdir, "H1-RUN-MANIFEST.json")))
lock_obj = json.load(open(lp))
check("lock binds the PROMOTION receipt hash",
      lock_obj.get("promotion_receipt_sha256")
      == ORD._sha256_file(rp), str(lock_obj.get("promotion_receipt_sha256")))
done = ORD.completed_cells(state_root, expansion=EXPANSION)
check("progress ledger counts the CAPABILITY_LOCK event once validated",
      LOCK["cell_id"] in done, str(sorted(done)))

# locked artifact bytes changed after the lock was written
eng = os.path.join(capdir, "engine.py")
good_eng = open(eng).read()
open(eng, "w").write(good_eng + "# tampered\n")
bad = st(LOCK)
check("mutated locked artifact refused (hash mismatch)",
      bad["status"] == "INADMISSIBLE"
      and any("hash mismatch" in r for r in bad["reasons"]), str(bad))
open(eng, "w").write(good_eng)
check("CAPABILITY_LOCK cell COMPLETE after the artifact is restored",
      st(LOCK)["status"] == "COMPLETE", str(st(LOCK)))

# lock no longer bound to the promotion receipt
json.dump(dict(lock_obj, promotion_receipt_sha256="b" * 64), open(lp, "w"))
bad = st(LOCK)
check("lock whose promotion_receipt_sha256 does not match refused",
      bad["status"] == "INADMISSIBLE"
      and any("does not bind the promotion receipt" in r
              for r in bad["reasons"]), str(bad))

# lock naming another universe's capability
json.dump(dict(lock_obj, capability_id="fam05-PQ-C-K"), open(lp, "w"))
bad = st(LOCK)
check("lock naming another universe's capability refused",
      bad["status"] == "INADMISSIBLE"
      and any("capability lock capability_id" in r for r in bad["reasons"]),
      str(bad))

json.dump(lock_obj, open(lp, "w"))
check("CAPABILITY_LOCK cell COMPLETE after restore",
      st(LOCK)["status"] == "COMPLETE", str(st(LOCK)))

# a missing locked artifact
shutil.move(os.path.join(capdir, "adapter_notes.md"),
            os.path.join(capdir, "adapter_notes.md.bak"))
bad = st(LOCK)
check("missing locked artifact refused",
      bad["status"] == "INADMISSIBLE"
      and any("locked artifact missing" in r for r in bad["reasons"]),
      str(bad))
shutil.move(os.path.join(capdir, "adapter_notes.md.bak"),
            os.path.join(capdir, "adapter_notes.md"))

# ---------------------------------------------------------------------------
# D. downstream acquisition after promotion + locked capability
# ---------------------------------------------------------------------------
complete_model_cell(T2)
t2 = st(T2)
check("T2 acquisition cell validated COMPLETE once the capability is locked",
      t2["status"] == "COMPLETE", str(t2))
done = ORD.completed_cells(state_root, expansion=EXPANSION)
check("progress ledger counts all five validated events of this universe",
      {T0["cell_id"], T1["cell_id"], PROM["cell_id"], LOCK["cell_id"],
       T2["cell_id"]} <= set(done), str(sorted(done)))

# ---------------------------------------------------------------------------
# E. reader-side namespace ancestry (A11.6 TOCTOU guard)
# ---------------------------------------------------------------------------
runs_parent = os.path.dirname(run_dir_of(T2))
os.chmod(runs_parent, 0o777)
bad = st(T2)
check("reader-side ancestry refuses a group/world-writable run namespace",
      bad["status"] == "INADMISSIBLE"
      and any("NAMESPACE-WRITABLE-DENY" in r for r in bad["reasons"]), str(bad))
os.chmod(runs_parent, 0o755)
check("T2 COMPLETE again after the namespace mode is repaired",
      st(T2)["status"] == "COMPLETE", str(st(T2)))

uni = os.path.join(state_root, "state", "PQ", "A")
shadow = os.path.join(state_root, "state", "PQ", "C")
os.makedirs(shadow)
os.chmod(shadow, 0o755)
shutil.move(uni, uni + ".real")
os.symlink(shadow, uni)
bad = st(T2)
check("reader-side ancestry refuses a symlinked universe namespace",
      bad["status"] == "INADMISSIBLE"
      and any("NAMESPACE-SYMLINK-DENY" in r for r in bad["reasons"]), str(bad))
os.unlink(uni)
shutil.move(uni + ".real", uni)
check("T2 COMPLETE again after the symlinked namespace is restored",
      st(T2)["status"] == "COMPLETE", str(st(T2)))

# ---------------------------------------------------------------------------
total = len(results)
passed = sum(1 for _, ok in results if ok)
print(f"\nH12 cell-state smoke: {passed}/{total} closed")
sys.exit(0 if passed == total else 1)

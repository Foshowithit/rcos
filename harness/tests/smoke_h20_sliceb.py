#!/usr/bin/env python3
"""H20 — A12c slice B: consumer-minimal capability + provenance invariance.

B1: the T0 acquisition prompt explicitly requests `capability_contract`
    {semantic_core, preconditions, limitations} in the producer's own
    words, names no auditor artifact, and states omission is
    unpromotable; every non-acquisition arm prompt is byte-unchanged
    (shared _OUT) and the T1 acquisition instruction is untouched.
B2/B3/B4: the minted consumer manifest carries ONLY the minimal key set
    (capability_id, version, block, universe, family, candidate_sha256,
    interface, producer_contract, artifacts, usage); adapter_notes.md and
    engine.py carry no acquisition provenance.
B5: the fixture stand-in authors its own wording (no K.md reader).
B6: consumer-visible bytes are INVARIANT under provenance mutation —
    the same family minted in universes A (lane P) and C (lane Q) with
    different source cells, provider identities, evidence grades and
    chain tips, plus a second root with a different protocol-lock hash,
    yields byte-identical consumer bytes after excluding
    capability_id/block/universe/family; auditor-side records differ.

Stdlib only. Hermetic fixtures in throwaway dirs (no live-tree
mutation); live-tree reads are read-only. Prints
`H20 slice-B smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import order  # noqa: E402
import promotion  # noqa: E402
import run_arm_h1 as RA  # noqa: E402
import fixture_modelrun as FX  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

CHECKS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("import json, os, sys\n"
          "inp, outp = sys.argv[1], sys.argv[2]\n"
          "ok = sorted(os.listdir(inp))\n"
          "json.dump({'ok': ok, 'bad': [], 'unverified': []},\n"
          "          open(outp, 'w'))\n")

ALLOWED_MANIFEST_KEYS = {"capability_id", "version", "block", "universe",
                         "family", "candidate_sha256", "interface",
                         "producer_contract", "artifacts", "usage"}
FORBIDDEN_MANIFEST_KEYS = {"source_cells", "acquisition_chain_tips",
                           "protocol_lock_sha256", "execution_lock_sha256",
                           "evidence_grade", "producer_identity",
                           "t4_semantic_id", "t4_ratified", "conformance_cause",
                           "limitation_present", "non_discriminating",
                           "limitations", "preconditions", "semantic_core",
                           "locked_at", "created_at", "engine_interface",
                           "candidate_provenance_sha256",
                           "promotion_receipt_sha256", "manifest_sha256",
                           "training_receipts", "builder_identity"}
NAMESPACE_KEYS = {"capability_id", "block", "universe", "family"}
NOTES_FORBIDDEN = ("arrival", "validated by", "chain", "grade", "protocol",
                   "evidence", "lock_sha", "LOCK", "cell", "K.md", "t4_",
                   "T4", "conformance", "ratif", "audit", "hidden",
                   "template")
T0_FORBIDDEN = ("K.md", "semantic_id", "semantic id", "conformance",
                "ratif", "audit", "hidden", "evidence", "grade",
                "DESIGN-T4", "chain tip", "protocol", "t4_")


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), str(detail)[:300]))
    print(("PASS " if cond else "FAIL ") + name +
          (f" [{detail}]"[:320] if detail and not cond else ""))


def hermetic(tag):
    root = tempfile.mkdtemp(prefix="h20-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                    os.path.join(fam, "fam05"))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def mint(root, universe, grade):
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", universe)
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", universe)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", "fam05", universe, FREEZE,
                            evidence_grade=grade)
    assert res["event"] == "PROMOTION", res
    res2 = promotion.advance(root, "PQ", "fam05", universe, FREEZE,
                             evidence_grade=grade)
    assert res2["event"] == "CAPABILITY_LOCK", res2
    return res, res2


def consumer_bytes(root, universe):
    capdir = order.capability_dir(root, "PQ", universe, "fam05")
    out = {}
    for name in ("manifest.json", "adapter_notes.md", "engine.py"):
        with open(os.path.join(capdir, name), "rb") as f:
            out[name] = f.read()
    return out


# ---- root1: A on lane P (harness-validation), C on lane Q (estimand) ----
root1 = hermetic("r1")
resA, _ = mint(root1, "A", "harness-validation")
resC, _ = mint(root1, "C", "estimand")
consA = consumer_bytes(root1, "A")
consC = consumer_bytes(root1, "C")
manA, manC = (json.loads(consA["manifest.json"]),
              json.loads(consC["manifest.json"]))
recA = json.load(open(resA["receipt"]))
recC = json.load(open(resC["receipt"]))

# ---- B1: the T0 acquisition prompt carries the contract instruction ----
RA.BASE = root1
exp1 = order.load_expansion(root1)
t0cell = order.expected_event(exp1, "PQ", "fam05", "T0", "A")
t1cell = order.expected_event(exp1, "PQ", "fam05", "T1", "A")
t0prep = RA.prepare_arm("P", "fam05", "T0", "acquisition", None, False,
                        "h20-t0", cell=t0cell)
t0prompt = t0prep["prompt"]
check("T0 prompt requests capability_contract {semantic_core, "
      "preconditions, limitations} alongside solver_py",
      all(k in t0prompt for k in ("capability_contract", "semantic_core",
                                  "preconditions", "limitations",
                                  "solver_py")),
      [k for k in ("capability_contract", "semantic_core",
                   "preconditions", "limitations", "solver_py")
       if k not in t0prompt])
check("T0 prompt demands the producer's own words and states omission "
      "is unpromotable",
      "own words" in t0prompt and "unpromotable" in t0prompt)
check("T0 prompt names no hidden file, semantic ID, conformance, "
      "ratification, or auditor artifact",
      not [w for w in T0_FORBIDDEN if w in t0prompt],
      [w for w in T0_FORBIDDEN if w in t0prompt])
check("T0 prompt is exactly shared-preamble + envelope + T0 instruction "
      "with no strippable block",
      t0prompt == RA._PRE + t0prep["envelope"] + RA._OUT_T0
      and RA.strip_capability_block(t0prompt) == t0prompt)

# ---- B1: non-acquisition arm prompts are byte-unchanged -----------------
capA = order.capability_dir(root1, "PQ", "A", "fam05")
cor = RA.prepare_arm("P", "fam05", "T2", "correct", capA, False, "h20-cor",
                     None)
dis = RA.prepare_arm("P", "fam05", "T2", "disabled", None, False,
                     "h20-dis", None)
check("correct/disabled prompts keep the byte-identical shared _OUT "
      "and never request capability_contract",
      cor["prompt"].endswith(RA._OUT) and dis["prompt"].endswith(RA._OUT)
      and "capability_contract" not in cor["prompt"]
      and "capability_contract" not in dis["prompt"]
      and RA.check_arm_symmetry(cor["prompt"], dis["prompt"],
                                cor["envelope"]) == [])
cand = {"sha256": "1" * 64, "source": "x = 1\n"}
t1prep = RA.prepare_arm("P", "fam05", "T1", "acquisition", None, False,
                        "h20-t1", cell=t1cell, candidate=cand)
check("T1 acquisition prompt keeps the untouched adapter_py instruction",
      t1prep["prompt"].endswith(RA._OUT_T1)
      and "adapter_py" in t1prep["prompt"]
      and "capability_contract" not in t1prep["prompt"])

# ---- B2: the consumer manifest is aggressively minimal ------------------
check("manifest key set is exactly the minimal consumer set",
      set(manA) == ALLOWED_MANIFEST_KEYS
      and set(manC) == ALLOWED_MANIFEST_KEYS,
      sorted(set(manA) | set(manC)))
check("manifest carries none of the forbidden provenance keys",
      not [k for k in FORBIDDEN_MANIFEST_KEYS if k in manA or k in manC],
      [k for k in FORBIDDEN_MANIFEST_KEYS if k in manA or k in manC])
check("manifest producer_contract is {semantic_core, preconditions, "
      "limitations} from the same T0 declaration the receipt uses",
      set(manA.get("producer_contract") or {}) ==
      {"semantic_core", "preconditions", "limitations"}
      and manA["producer_contract"]["semantic_core"] ==
      recA["semantic_core"]
      and manA["producer_contract"]["preconditions"] ==
      recA["preconditions"]
      and manA["producer_contract"]["limitations"] ==
      recA["limitations"] == []
      and manC["producer_contract"]["semantic_core"] ==
      recC["semantic_core"],
      str(sorted((manA.get("producer_contract") or {}).keys())))

# ---- B3/B4: notes and engine carry no acquisition provenance ------------
notesA = consA["adapter_notes.md"].decode()
engA = consA["engine.py"].decode()
check("adapter_notes.md names no cell, chain, grade, lock, T4, or "
      "auditor wording",
      not [w for w in NOTES_FORBIDDEN if w in notesA],
      [w for w in NOTES_FORBIDDEN if w in notesA])
check("adapter_notes.md keeps id, candidate sha, interface, contract, "
      "and use",
      "fam05-PQ-A-K" in notesA and recA["candidate"]["sha256"] in notesA
      and "engine.py <field_map.json> <records.json> <OUTPUT.json>"
      in notesA
      and recA["semantic_core"] in notesA)
check("minted engine carries no source cells and still embeds the "
      "locked candidate",
      "__T0_CELL__" not in engA and "__T1_CELL__" not in engA
      and "source cell" not in engA
      and recA["candidate"]["sha256"] in engA
      and "CANDIDATE_SOURCE" in engA)

# ---- B5: the fixture authors its own wording (never K.md text) ---------
fx_src = open(os.path.join(HERE, "fixture_modelrun.py")).read()
check("fixture has no hidden-contract reader (no K.md open)",
      not re.findall(r"open\([^)]*K\.md[^)]*\)", fx_src))
check("stand-in declares independent text for all six families",
      set(FX.PRODUCER_CONTRACTS) ==
      {"fam01", "fam02", "fam03", "fam04", "fam05", "fam06"}
      and all(isinstance(v[0], str) and v[0].strip()
              and isinstance(v[1], list) and v[1]
              and v[2] == [] for v in FX.PRODUCER_CONTRACTS.values()))

# ---- B6: provenance mutation must not move consumer bytes ---------------
normA = {k: v for k, v in manA.items() if k not in NAMESPACE_KEYS}
normC = {k: v for k, v in manC.items() if k not in NAMESPACE_KEYS}
# The artifacts map binds the exact sibling bytes, which legitimately
# differ by capability_id (notes header) — so it is compared structurally:
# engine.py's locked hash must be identical, and every entry must equal
# the sha256 of the bytes actually present in that universe's dir.
artA, artC = normA.pop("artifacts"), normC.pop("artifacts")
capA2 = order.capability_dir(root1, "PQ", "A", "fam05")
capC2 = order.capability_dir(root1, "PQ", "C", "fam05")


def _files_match(manifest, capdir):
    arts = manifest.get("artifacts") or {}
    if set(arts) != {"engine.py", "adapter_notes.md"}:
        return False
    for name, want in arts.items():
        with open(os.path.join(capdir, name), "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != want:
                return False
    return True


check("manifest bytes identical across universes modulo "
      "capability_id/block/universe/family",
      normA == normC and artA.get("engine.py") == artC.get("engine.py")
      and _files_match(manA, capA2) and _files_match(manC, capC2),
      [k for k in normA if normA.get(k) != normC.get(k)] or
      f"engine_sha={artA.get('engine.py') == artC.get('engine.py')}")
norm_notesA = notesA.replace("fam05-PQ-A-K", "CAPID")
norm_notesC = consC["adapter_notes.md"].decode().replace(
    "fam05-PQ-C-K", "CAPID")
check("adapter_notes.md identical across universes modulo "
      "capability_id", norm_notesA == norm_notesC)
check("engine.py byte-identical across universes",
      consA["engine.py"] == consC["engine.py"],
      f"{hashlib.sha256(consA['engine.py']).hexdigest()[:12]} vs "
      f"{hashlib.sha256(consC['engine.py']).hexdigest()[:12]}")

# auditor-side records MUST differ across the two provenances
t0A = order.expected_event(exp1, "PQ", "fam05", "T0", "A")
t0C = order.expected_event(exp1, "PQ", "fam05", "T0", "C")
tipA = order._chain_tip(os.path.join(order.run_dir(root1, t0A),
                                     "EVIDENCE-CHAIN.jsonl"))
tipC = order._chain_tip(os.path.join(order.run_dir(root1, t0C),
                                     "EVIDENCE-CHAIN.jsonl"))
check("auditor records differ: cells, tips, provider identity, grade",
      recA["source_cells"] != recC["source_cells"]
      and tipA != tipC
      and recA["t0_evidence"]["identity"]["model_requested"] !=
      recC["t0_evidence"]["identity"]["model_requested"]
      and recA["evidence_grade"] == "harness-validation"
      and recC["evidence_grade"] == "estimand"
      and json.load(open(os.path.join(
          order.capability_dir(root1, "PQ", "A", "fam05"),
          "CAPABILITY_LOCK.json")))["evidence_grade"] ==
      "harness-validation",
      f"grades={recA['evidence_grade']}/{recC['evidence_grade']}")

# ---- B6: protocol-lock-hash mutation leaves consumer bytes still --------
root2 = hermetic("r2")
_pl = os.path.join(root2, "PROTOCOL-LOCK.json")
_pl_obj = json.load(open(_pl))
open(_pl, "w").write(json.dumps(_pl_obj, indent=2, sort_keys=True) + "\n")
assert (json.load(open(_pl)) == _pl_obj
        and hashlib.sha256(open(_pl, "rb").read()).hexdigest() !=
        hashlib.sha256(open(os.path.join(root1, "PROTOCOL-LOCK.json"),
                            "rb").read()).hexdigest())
resA2, _ = mint(root2, "A", "harness-validation")
consA2 = consumer_bytes(root2, "A")
recA2 = json.load(open(resA2["receipt"]))
check("different protocol-lock hash still mints byte-identical "
      "consumer artifacts (same universe, same solver)",
      consA2["engine.py"] == consA["engine.py"]
      and consA2["adapter_notes.md"] == consA["adapter_notes.md"]
      and json.loads(consA2["manifest.json"]) == manA,
      [k for k in ("engine.py", "adapter_notes.md", "manifest.json")
       if consA2[k] != consA[k]])
check("auditor receipt binds the mutated protocol-lock hash",
      recA2["protocol_lock_sha256"] != recA["protocol_lock_sha256"]
      and recA2["protocol_lock_sha256"] ==
      hashlib.sha256(open(_pl, "rb").read()).hexdigest())

passed = sum(1 for _n, c, _d in CHECKS if c)
total = len(CHECKS)
for name, cond, detail in CHECKS:
    if not cond:
        print(f"FAIL {name}: {detail}")
print(f"H20 slice-B smoke: {passed}/{total} closed")
sys.exit(0 if passed == total else 1)

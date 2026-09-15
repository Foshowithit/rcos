#!/usr/bin/env python3
"""H20 — A12c slice B: consumer-minimal capability + provenance invariance,
as reframed by A12d slice D3 (auditor A12d.5).

B1: the T0 acquisition prompt explicitly requests `capability_contract`
    {semantic_core, preconditions, limitations} in the producer's own
    words, names no auditor artifact, and states omission is
    unpromotable; every non-acquisition arm prompt is byte-unchanged
    (shared _OUT) and the T1 acquisition instruction is untouched.
B2/B3/B4: the minted consumer manifest carries ONLY the minimal key set
    (capability_id, version, family, candidate_sha256, interface,
    producer_contract, artifacts, usage) — block/universe REMOVED —
    with capability_id as the opaque consumer alias
    "cap-" + sha256(canonical_json({candidate_sha256,
    producer_contract, version}))[:12]; adapter_notes.md and engine.py
    carry no acquisition provenance and no namespace token.
B5: the fixture stand-in authors its own wording (no K.md reader).
B6: consumer-visible bytes are EXACTLY byte-identical across universes —
    the same family minted in universes A (lane P) and C (lane Q) with
    different source cells, provider identities, evidence grades and
    chain tips, plus a second root with a different protocol-lock hash,
    yields byte-identical engine.py AND manifest.json AND
    adapter_notes.md with NO exclusion list and NO key stripping;
    auditor-side records differ.
A5: the manifest for A and C of the same family/contract is identical
    when the candidate bytes are identical and differs when they
    differ; two DIFFERENT families with the same candidate+contract
    bytes produce the SAME opaque alias (opacity) while their
    auditor-side lock ids still differ.

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
SOLVER_VARIANT = SOLVER + "# variant candidate\n"

# A12d slice D3: the consumer-minimal key set (block/universe REMOVED).
ALLOWED_MANIFEST_KEYS = {"capability_id", "version", "family",
                         "candidate_sha256", "interface",
                         "producer_contract", "artifacts", "usage"}
FORBIDDEN_MANIFEST_KEYS = {"block", "universe", "source_cells",
                           "acquisition_chain_tips",
                           "protocol_lock_sha256", "execution_lock_sha256",
                           "evidence_grade", "producer_identity",
                           "t4_semantic_id", "t4_ratified", "conformance_cause",
                           "declared_limitations_present",
                           "non_discriminating",
                           "limitations", "preconditions", "semantic_core",
                           "locked_at", "created_at", "engine_interface",
                           "candidate_provenance_sha256",
                           "promotion_receipt_sha256", "manifest_sha256",
                           "training_receipts", "builder_identity"}
NAMESPACE_TOKENS = ("PQ", "QP", "universe", "block", "A-K", "C-K",
                    "fam0", "-PQ")
NOTES_FORBIDDEN = ("arrival", "validated by", "chain", "grade", "protocol",
                   "evidence", "lock_sha", "LOCK", "cell", "K.md", "t4_",
                   "T4", "conformance", "ratif", "audit", "hidden",
                   "template")
T0_FORBIDDEN = ("K.md", "semantic_id", "semantic id", "conformance",
                "ratif", "audit", "hidden", "evidence", "grade",
                "DESIGN-T4", "chain tip", "protocol", "t4_")

# A5 cross-family probe contract (test support ONLY): independently
# written text, namespace-token-free, byte-identical for both families.
A5_CONTRACT = {
    "semantic_core": "Cross-family opacity probe: file listing audit.",
    "preconditions": [{"requires_all": ["local", "v1", "sha256"]}],
    "limitations": []}


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), str(detail)[:300]))
    print(("PASS " if cond else "FAIL ") + name +
          (f" [{detail}]"[:320] if detail and not cond else ""))


def hermetic(tag):
    root = tempfile.mkdtemp(prefix="h20-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for family in ("fam05", "fam03"):
        shutil.copytree(os.path.join(FAMC, "families", family),
                        os.path.join(fam, family))
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


def consumer_bytes(root, block, universe, family):
    capdir = order.capability_dir(root, block, universe, family)
    out = {}
    for name in ("manifest.json", "adapter_notes.md", "engine.py"):
        with open(os.path.join(capdir, name), "rb") as f:
            out[name] = f.read()
    return out


def canonical_alias(manifest):
    payload = {"candidate_sha256": manifest["candidate_sha256"],
               "producer_contract": manifest["producer_contract"],
               "version": manifest["version"]}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "cap-" + hashlib.sha256(blob.encode()).hexdigest()[:12]


# ---- root1: A on lane P (harness-validation), C on lane Q (estimand) ----
root1 = hermetic("r1")
resA, _ = mint(root1, "A", "harness-validation")
resC, _ = mint(root1, "C", "estimand")
consA = consumer_bytes(root1, "PQ", "A", "fam05")
consC = consumer_bytes(root1, "PQ", "C", "fam05")
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

# ---- B2: the consumer manifest is aggressively minimal (D3-A) ----------
check("manifest key set is exactly the consumer-minimal set (no "
      "block/universe)",
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

# ---- A2: the opaque consumer alias -------------------------------------
check("capability_id is the opaque alias (cap- + 12 hex, no block "
      "letter, universe letter, family token, or order position)",
      manA["capability_id"].startswith("cap-")
      and len(manA["capability_id"]) == 16
      and all(ch in "0123456789abcdef"
              for ch in manA["capability_id"][4:])
      and not [t for t in NAMESPACE_TOKENS
               if t in manA["capability_id"]],
      manA["capability_id"])
check("alias is the frozen canonical recomputation over "
      "{candidate_sha256, producer_contract, version}",
      manA["capability_id"] == canonical_alias(manA)
      and manC["capability_id"] == canonical_alias(manC),
      f"{manA['capability_id']} vs {canonical_alias(manA)}")
check("family stays only as the namespace-free taxonomy label",
      manA["family"] == manC["family"] == "family-05"
      and not [t for t in NAMESPACE_TOKENS if t in manA["family"]],
      manA["family"])

# ---- B3/B4: notes and engine carry no acquisition provenance ------------
notesA = consA["adapter_notes.md"].decode()
engA = consA["engine.py"].decode()
check("adapter_notes.md names no cell, chain, grade, lock, T4, or "
      "auditor wording",
      not [w for w in NOTES_FORBIDDEN if w in notesA],
      [w for w in NOTES_FORBIDDEN if w in notesA])
check("adapter_notes.md keeps the opaque id, candidate sha, "
      "interface, contract, and use (never the canonical cell id)",
      manA["capability_id"] in notesA
      and "fam05-PQ-A-K" not in notesA and "fam05-PQ-C-K" not in notesA
      and recA["candidate"]["sha256"] in notesA
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

# ---- B6: EXACT byte identity across universes (D3-A4, no modulo) --------
check("manifest.json EXACTLY byte-identical across universes (no "
      "exclusion list, no key stripping)",
      consA["manifest.json"] == consC["manifest.json"],
      f"{hashlib.sha256(consA['manifest.json']).hexdigest()[:12]} vs "
      f"{hashlib.sha256(consC['manifest.json']).hexdigest()[:12]}")
check("adapter_notes.md EXACTLY byte-identical across universes",
      consA["adapter_notes.md"] == consC["adapter_notes.md"])
check("engine.py byte-identical across universes",
      consA["engine.py"] == consC["engine.py"],
      f"{hashlib.sha256(consA['engine.py']).hexdigest()[:12]} vs "
      f"{hashlib.sha256(consC['engine.py']).hexdigest()[:12]}")
check("the opaque alias is identical across universes for identical "
      "candidate + contract bytes",
      manA["capability_id"] == manC["capability_id"]
      and manA["candidate_sha256"] == manC["candidate_sha256"],
      f"{manA['capability_id']} vs {manC['capability_id']}")

# auditor-side records MUST differ across the two provenances
t0A = order.expected_event(exp1, "PQ", "fam05", "T0", "A")
t0C = order.expected_event(exp1, "PQ", "fam05", "T0", "C")
tipA = order._chain_tip(os.path.join(order.run_dir(root1, t0A),
                                     "EVIDENCE-CHAIN.jsonl"))
tipC = order._chain_tip(os.path.join(order.run_dir(root1, t0C),
                                     "EVIDENCE-CHAIN.jsonl"))
check("auditor records differ: cells, tips, provider identity, grade, "
      "lock ids",
      recA["source_cells"] != recC["source_cells"]
      and tipA != tipC
      and recA["t0_evidence"]["identity"]["model_requested"] !=
      recC["t0_evidence"]["identity"]["model_requested"]
      and recA["evidence_grade"] == "harness-validation"
      and recC["evidence_grade"] == "estimand"
      and json.load(open(os.path.join(
          order.capability_dir(root1, "PQ", "A", "fam05"),
          "CAPABILITY_LOCK.json")))["capability_id"] == "fam05-PQ-A-K"
      and json.load(open(os.path.join(
          order.capability_dir(root1, "PQ", "C", "fam05"),
          "CAPABILITY_LOCK.json")))["capability_id"] == "fam05-PQ-C-K",
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
consA2 = consumer_bytes(root2, "PQ", "A", "fam05")
recA2 = json.load(open(resA2["receipt"]))
check("different protocol-lock hash still mints byte-identical "
      "consumer artifacts (same universe, same solver)",
      consA2["engine.py"] == consA["engine.py"]
      and consA2["adapter_notes.md"] == consA["adapter_notes.md"]
      and consA2["manifest.json"] == consA["manifest.json"],
      [k for k in ("engine.py", "adapter_notes.md", "manifest.json")
       if consA2[k] != consA[k]])
check("auditor receipt binds the mutated protocol-lock hash",
      recA2["protocol_lock_sha256"] != recA["protocol_lock_sha256"]
      and recA2["protocol_lock_sha256"] ==
      hashlib.sha256(open(_pl, "rb").read()).hexdigest())

# ---- A5: cross-family opacity (D3-A5) -----------------------------------
# fam05 full (20 cells) + fam03 A acquisition (4 cells) in expansion
# order with the SAME solver and the SAME contract declaration, plus a
# fam03 C acquisition with a DIFFERENT solver (different candidate).
root3 = hermetic("r3")
exp3 = order.load_expansion(root3)
_t0sha = {}


def _a5_build(c, solver):
    if c["event"] == "T1":
        return build_model_run(
            root3, cell=c, freeze_commit=FREEZE, solver_py=SOLVER,
            validates_candidate=_t0sha[(c["block"], c["universe"],
                                        c["family"])])
    d = build_model_run(root3, cell=c, freeze_commit=FREEZE,
                        solver_py=solver,
                        producer_contract=dict(A5_CONTRACT))
    if c["event"] == "T0":
        _t0sha[(c["block"], c["universe"], c["family"])] = \
            t0_candidate_sha256(d)
    return d


for _c in exp3["cells"][:28]:
    _b, _u, _f, _ev = (_c["block"], _c["universe"], _c["family"],
                       _c["event"])
    if _ev == "PROMOTION":
        promotion.promote_universe(root3, _b, _f, _u, FREEZE,
                                   "harness-validation")
    elif _ev == "CAPABILITY_LOCK":
        promotion.advance(root3, _b, _f, _u, FREEZE,
                          "harness-validation")
    elif _f == "fam03" and _u == "C":
        _a5_build(_c, SOLVER_VARIANT)
    else:
        _a5_build(_c, SOLVER)
_m5 = json.loads(consumer_bytes(root3, "PQ", "A", "fam05")
                 ["manifest.json"])
_m3 = json.loads(consumer_bytes(root3, "PQ", "A", "fam03")
                 ["manifest.json"])
_m3c = json.loads(consumer_bytes(root3, "PQ", "C", "fam03")
                  ["manifest.json"])
_lk5 = json.load(open(os.path.join(
    order.capability_dir(root3, "PQ", "A", "fam05"),
    "CAPABILITY_LOCK.json")))
_lk3 = json.load(open(os.path.join(
    order.capability_dir(root3, "PQ", "A", "fam03"),
    "CAPABILITY_LOCK.json")))
check("same candidate+contract bytes -> same opaque alias across "
      "DIFFERENT families",
      _m5["capability_id"] == _m3["capability_id"]
      and _m5["candidate_sha256"] == _m3["candidate_sha256"]
      and _m5["producer_contract"] == _m3["producer_contract"],
      f"fam05={_m5['capability_id']} fam03={_m3['capability_id']}")
check("auditor-side lock ids still differ across families",
      _lk5.get("capability_id") == "fam05-PQ-A-K"
      and _lk3.get("capability_id") == "fam03-PQ-A-K",
      f"{_lk5.get('capability_id')} / {_lk3.get('capability_id')}")
check("a different candidate yields a different alias/manifest",
      _m3c["candidate_sha256"] != _m3["candidate_sha256"]
      and _m3c["capability_id"] != _m3["capability_id"],
      f"{_m3c['capability_id']} vs {_m3['capability_id']}")

passed = sum(1 for _n, c, _d in CHECKS if c)
total = len(CHECKS)
for name, cond, detail in CHECKS:
    if not cond:
        print(f"FAIL {name}: {detail}")
print(f"H20 slice-B smoke: {passed}/{total} closed")
sys.exit(0 if passed == total else 1)

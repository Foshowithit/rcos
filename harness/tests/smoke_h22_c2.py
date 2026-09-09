#!/usr/bin/env python3
"""H22 — A12c slice C2 + A12d slice D2: the frozen AFFIRMATIVE
requires->T4-id conformance bridge (auditor P0 #6, A12d.3).

`non_discriminating = not bool(limitations)` is now wrong in general: an
unrelated producer text must leave the T4 non-discriminating, and
limitations NEVER drive conformance at all. The frozen bridge (governed
T4-CONFORMANCE.json under normalize-affirmative-requires-v2, single
implementation harness/conformance.py, wired through
promotion/lock/order/preflight) maps ONLY affirmative
preconditions[*].requires claims: a negated requires text is
INADMISSIBLE (fail closed, reported — never silently matched). Proven
here by REAL tests — the live governed map, the real verdict
machinery, the real promotion controller / lock verifier / order
provenance re-derivation / preflight V2, never a claim:

  K1-K5  verdict proofs through conformance.verdict on the live map
  K6     lock whose supported_t4_ids excludes its own id while claiming
         discrimination -> LOCK-INADMISSIBLE naming the id
  K7     receipt claiming non_discriminating False with no map support
         -> promotion DENY naming the recomputed set
  K8     map mutated without re-minting the lock -> preflight V2 nonzero
         naming T4-CONFORMANCE.json (live tree, backup+restore verified);
         receipt conformance_map_sha256 mismatch -> deny naming the field
  K9     unknown family / missing map / bad rule string ->
         conformance.load/verdict RAISES (never silently defaults)
  K10    hidden-ness: auditor-unique literals (version/rule strings,
         six T4 ids) are nowhere in consumer bytes, built prompts, or
         producer declarations; predicate phrases are not
         harness-authored (emitted scaffolding + prompt constants carry
         zero pair needles; producer/task text is visible by design).

Stdlib only. Hermetic fixtures in throwaway dirs (no live-tree mutation
except K8's backup+restore cycle, which verifies byte-identical restore
as part of the test); live-tree reads are otherwise read-only. Prints
`H22 C2 smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
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
sys.path.insert(0, FAMC)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import conformance as CONF  # noqa: E402
import lock as LOCK_MOD  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import run_arm_h1 as RA  # noqa: E402
import preflight as PF  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256,
                              PRODUCER_CONTRACTS)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")
LIVE_MAP = os.path.join(FAMC, "T4-CONFORMANCE.json")
LIVE_MAP_SHA = hashlib.sha256(open(LIVE_MAP, "rb").read()).hexdigest()
FAM05_ID = "fam05.local_v1_sha256"
FAM04_ID = "fam04.promised_acyclic"


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def hermetic(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h22-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for f in families:
        shutil.copytree(os.path.join(FAMC, "families", f),
                        os.path.join(fam, f))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def contract_with(requires, family="fam05", limitations=()):
    core, _pre, _lim = PRODUCER_CONTRACTS[family]
    return {"semantic_core": core,
            "preconditions": [{"requires": t} for t in requires],
            "limitations": list(limitations)}


def mint(root, family="fam05", universe="A", requires=None,
         limitations=()):
    """Acquire/promote/lock one family through the production path with
    the given producer requires claims (and free-prose limitations).
    Returns (receipt_path, lock_dict)."""
    pc = contract_with([] if requires is None else requires, family,
                       limitations)
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", family, "T0", universe)
    t1 = order.expected_event(exp, "PQ", family, "T1", universe)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=pc)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", family, universe, FREEZE,
                            evidence_grade="harness-validation")
    assert res["event"] == "PROMOTION", res
    res2 = promotion.advance(root, "PQ", family, universe, FREEZE,
                             evidence_grade="harness-validation")
    assert res2["event"] == "CAPABILITY_LOCK", res2
    capdir = order.capability_dir(root, "PQ", universe, family)
    lock = json.load(open(os.path.join(capdir, "CAPABILITY_LOCK.json")))
    return res["receipt"], lock


def prom_cell(root, family="fam05", universe="A"):
    exp = order.load_expansion(root)
    return order.expected_event(exp, "PQ", family, "PROMOTION", universe)


# --- K1-K5: verdict proofs on the live governed map ---------------------
cmap = CONF.load(FAMC)
check("live governed map loads (version t4-conformance-v2, rule "
      "normalize-affirmative-requires-v2)",
      cmap["version"] == "t4-conformance-v2"
      and cmap["rule"] == "normalize-affirmative-requires-v2"
      and cmap["conformance_map_sha256"] == LIVE_MAP_SHA)

v = CONF.verdict("fam05", [], cmap)
check("K1 fam05 requires [] -> non_discriminating True, "
      "supported_t4_ids [], cause names fam05.local_v1_sha256",
      v["non_discriminating"] is True and v["supported_t4_ids"] == []
      and v["limitation_present"] is False
      and FAM05_ID in v["conformance_cause"]
      and "0 precondition(s)" in v["conformance_cause"])

v = CONF.verdict("fam05", ["requires Python 3"], cmap)
check("K2 fam05 requires ['requires Python 3'] -> "
      "non_discriminating True (unrelated requires supports nothing)",
      v["non_discriminating"] is True and v["supported_t4_ids"] == []
      and v["limitation_present"] is True
      and FAM05_ID in v["conformance_cause"])

v = CONF.verdict("fam05", ["only valid for local v1 sha256 manifests"],
                 cmap)
check("K3 fam05 requires ['only valid for local v1 sha256 "
      "manifests'] -> non_discriminating False, supported_t4_ids "
      "['fam05.local_v1_sha256']",
      v["non_discriminating"] is False
      and v["supported_t4_ids"] == [FAM05_ID]
      and str(["local", "sha256"]) in v["conformance_cause"]
      and "only valid for local v1 sha256 manifests"
      in v["conformance_cause"])

v = CONF.verdict("fam05", ["works on the local sha256 basis"], cmap)
check("K4 fam05 requires ['works on the local sha256 basis'] -> "
      "non_discriminating False (token rule, order-independent)",
      v["non_discriminating"] is False
      and v["supported_t4_ids"] == [FAM05_ID])

v = CONF.verdict("fam04", ["requires Python 3"], cmap)
k5a = (v["non_discriminating"] is True
       and v["supported_t4_ids"] == []
       and FAM04_ID in v["conformance_cause"])
v = CONF.verdict("fam04", ["assumes an acyclic graph"], cmap)
check("K5 fam04 requires ['requires Python 3'] -> "
      "non_discriminating True; ['assumes an acyclic graph'] -> "
      "supported ['fam04.promised_acyclic']",
      k5a and v["non_discriminating"] is False
      and v["supported_t4_ids"] == [FAM04_ID])

# --- production-path mints (receipt+lock carry the bridge fields) -------
root_d = hermetic("default")
rp_d, lock_d = mint(root_d, requires=[])
rec_d = json.load(open(rp_d))
check("default production mint locks non-discriminating with empty "
      "support and the live map sha (receipt and lock agree)",
      rec_d["non_discriminating"] is True
      and rec_d["supported_t4_ids"] == []
      and rec_d["conformance_map_sha256"] == LIVE_MAP_SHA
      and lock_d["non_discriminating"] is True
      and lock_d["supported_t4_ids"] == []
      and lock_d["conformance_map_sha256"] == LIVE_MAP_SHA
      and lock_d["t4_semantic_id"] == FAM05_ID)
check("minted default promotion is order-COMPLETE (provenance "
      "re-derivation agrees)",
      order.cell_state(root_d, prom_cell(root_d), FREEZE)["status"]
      == "COMPLETE")

root_s = hermetic("support")
rp_s, lock_s = mint(root_s, requires=[
    "only valid for local v1 sha256 manifests"])
rec_s = json.load(open(rp_s))
check("supporting-requires production mint locks discriminating "
      "with the id in the supported set (receipt and lock agree)",
      rec_s["non_discriminating"] is False
      and rec_s["supported_t4_ids"] == [FAM05_ID]
      and lock_s["non_discriminating"] is False
      and lock_s["supported_t4_ids"] == [FAM05_ID])
check("minted discriminating promotion is order-COMPLETE",
      order.cell_state(root_s, prom_cell(root_s), FREEZE)["status"]
      == "COMPLETE")

# --- K6: supported set excluding the claimed id -> LOCK-INADMISSIBLE ----
bad_lock = dict(lock_s)
bad_lock["supported_t4_ids"] = []
reasons_k6 = LOCK_MOD.verify_lock(bad_lock, fam_c_dir=root_s)
check("K6 lock claiming discriminating fam05.local_v1_sha256 with "
      "supported_t4_ids [] -> LOCK-INADMISSIBLE naming "
      "fam05.local_v1_sha256",
      any("LOCK-INADMISSIBLE" in r and FAM05_ID in r
          for r in reasons_k6),
      "; ".join(reasons_k6)[:240])

# --- K7: receipt over-claiming discrimination -> promotion DENY ----------
root_u = hermetic("unrelated")
rp_u, _lock_u = mint(root_u, requires=["requires Python 3"])
rec_u = json.load(open(rp_u))
assert rec_u["non_discriminating"] is True
rec_u["non_discriminating"] = False
json.dump(rec_u, open(rp_u, "w"), indent=1)
st_u = order.cell_state(root_u, prom_cell(root_u), FREEZE)
check("K7 receipt claiming non_discriminating False with map support "
      "[] -> promotion DENY naming recomputed supported_t4_ids []",
      st_u["status"] != "COMPLETE"
      and any("recomputed supported_t4_ids []" in r
              for r in st_u["reasons"]),
      "; ".join(st_u["reasons"])[:240])

# --- K8a: mutated map without re-minting -> preflight V2 refuses --------
orig_bytes = open(LIVE_MAP, "rb").read()
mut = json.loads(orig_bytes.decode())
mut["families"]["fam03"]["requires_predicates"] = [
    p for p in mut["families"]["fam03"]["requires_predicates"]
    if p != ["dedup"]]
assert len(mut["families"]["fam03"]["requires_predicates"]) == 2
v2_findings = None
try:
    open(LIVE_MAP, "w").write(json.dumps(mut, indent=1) + "\n")
    v2_findings = [f for f in PF.validate_protocol(FAMC, FREEZE)
                   if f.startswith("V2")]
finally:
    open(LIVE_MAP, "wb").write(orig_bytes)
restored = hashlib.sha256(open(LIVE_MAP, "rb").read()).hexdigest()
check("K8 map mutated without re-minting lock -> preflight V2 nonzero "
      "naming T4-CONFORMANCE.json; receipt conformance_map_sha256 "
      "mismatch -> deny naming conformance_map_sha256",
      v2_findings is not None and v2_findings != []
      and any("T4-CONFORMANCE.json" in f for f in v2_findings)
      and restored == LIVE_MAP_SHA
      and PF.validate_t4_conformance(FAMC) == [],
      str((v2_findings or [])[:1])[:240])

# --- K8b: receipt map-sha mismatch -> deny naming the field -------------
root_m = hermetic("mapsha")
rp_m, _lock_m = mint(root_m, requires=[])
rec_m = json.load(open(rp_m))
flip = ("0" if rec_m["conformance_map_sha256"][-1] != "0" else "1")
rec_m["conformance_map_sha256"] = \
    rec_m["conformance_map_sha256"][:-1] + flip
json.dump(rec_m, open(rp_m, "w"), indent=1)
st_m = order.cell_state(root_m, prom_cell(root_m), FREEZE)
check("K8b receipt conformance_map_sha256 mismatch -> promotion DENY "
      "naming conformance_map_sha256",
      st_m["status"] != "COMPLETE"
      and any("conformance_map_sha256" in r
              for r in st_m["reasons"]),
      "; ".join(st_m["reasons"])[:240])

# --- K9: fail closed — raise, never default ------------------------------
k9 = []
try:
    CONF.verdict("fam07", [], cmap)
    k9.append("verdict(fam07) did not raise")
except Exception:
    pass
try:
    CONF.load(tempfile.mkdtemp(prefix="h22-nomap-"))
    k9.append("load(missing map) did not raise")
except Exception:
    pass
d_bad = tempfile.mkdtemp(prefix="h22-badrule-")
bad_map = json.loads(orig_bytes.decode())
bad_map["rule"] = "fuzzy-synonym-v9"
json.dump(bad_map, open(os.path.join(d_bad, "T4-CONFORMANCE.json"),
                        "w"))
try:
    CONF.load(d_bad)
    k9.append("load(bad rule) did not raise")
except Exception:
    pass
check("K9 unknown family / missing map / bad rule string -> "
      "conformance.load/verdict RAISES (never silently defaults)",
      k9 == [], "; ".join(k9))

# --- K10: hidden-ness — zero map tokens in consumer bytes + prompts -----
# Two scans, matching the two kinds of auditor-side strings:
#  (1) auditor-UNIQUE literals (the map's version/rule strings and the
#      six T4 ids) must be NOWHERE consumer-visible: not in the minted
#      artifacts, not in any built prompt, not even in producer
#      declarations (PREREG forbids IDs in producer contracts).
#  (2) predicate phrases must not be HARNESS-AUTHORED: the emitted
#      scaffolding (manifest/notes/engine bodies minus producer text,
#      prompt instruction constants) carries zero predicate needles.
#      Producer text and frozen task bytes are visible by design and
#      outside the harness's control — the frozen fam05 task surface
#      innocently contains the phrase "local sha256", which the
#      verdict rule treats as any other text (cf. K2: innocent words
#      support nothing). Scoping pair-needles to harness-authored bytes
#      is therefore the leak test; a MAP leak would be harness bytes.
cap_d = order.capability_dir(root_d, "PQ", "A", "fam05")
manifest_text = open(os.path.join(cap_d, "manifest.json")).read()
notes_text = open(os.path.join(cap_d, "adapter_notes.md")).read()
engine_text = open(os.path.join(cap_d, "engine.py")).read()
RA.BASE = root_d
exp_d = order.load_expansion(root_d)
t0c = order.expected_event(exp_d, "PQ", "fam05", "T0", "A")
t1c = order.expected_event(exp_d, "PQ", "fam05", "T1", "A")
prompts = [
    RA.prepare_arm("P", "fam05", "T0", "acquisition", None, False,
                   "h22-t0", cell=t0c)["prompt"],
    RA.prepare_arm("P", "fam05", "T1", "acquisition", None, False,
                   "h22-t1", cell=t1c,
                   candidate={"sha256": "1" * 64,
                              "source": "x = 1\n"})["prompt"],
    RA.prepare_arm("P", "fam05", "T2", "correct", cap_d, False,
                   "h22-cor", None)["prompt"],
    RA.prepare_arm("P", "fam05", "T2", "disabled", None, False,
                   "h22-dis", None)["prompt"],
]
assert len(prompts) == 4
declarations = [core + "\n" + "\n".join(p["requires"] for p in pre)
                for core, pre, _lim in PRODUCER_CONTRACTS.values()]
six_ids = ["fam01.rows_are_records", "fam02.pages_disjoint",
           "fam03.repeats_are_duplicates", "fam04.promised_acyclic",
           FAM05_ID, "fam06.common_unit_basis"]
built = [manifest_text, notes_text, engine_text] + prompts \
    + declarations
leaks1 = sorted({s for s in [cmap["version"], cmap["rule"]] + six_ids
                 if any(s in t for t in built)})
# Harness-authored bodies only: manifest minus its producer contract,
# notes minus the contract section, engine minus the embedded producer
# source line, plus the exact prompt instruction constants (H20 proves
# every prompt is _PRE + envelope + [capability block] + _OUT*, so the
# constants are the whole harness-authored prompt surface).
man_obj = json.loads(manifest_text)
man_obj["producer_contract"] = {"semantic_core": "", "preconditions": [],
                                "limitations": []}
scaffold_manifest = json.dumps(man_obj, sort_keys=True)
assert "## producer contract" in notes_text and "## use" in notes_text
scaffold_notes = (notes_text.split("## producer contract")[0]
                  + "## use"
                  + notes_text.split("## use", 1)[1])
scaffold_engine = "\n".join(
    ln for ln in engine_text.splitlines()
    if not ln.startswith("CANDIDATE_SOURCE"))
harness_text = (scaffold_manifest + "\n" + scaffold_notes + "\n"
                + scaffold_engine + "\n" + RA._PRE + RA._OUT
                + RA._OUT_T0 + RA._OUT_T1 + RA._ENVELOPE_FMT
                + RA._CAP_FMT)
needles = []
for fam in sorted(cmap["families"]):
    for pred in cmap["families"][fam]["requires_predicates"]:
        needles.append(" ".join(pred))
leaks2 = sorted({ndl for ndl in needles if ndl in harness_text})
leaks = leaks1 + leaks2
check("K10 consumer bytes + all four prompts carry zero map tokens "
      "(auditor-unique literals nowhere; predicate phrases not "
      "harness-authored)",
      leaks == [], "; ".join(leaks)[:240])

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH22 C2 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

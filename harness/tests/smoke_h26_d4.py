#!/usr/bin/env python3
"""H26 — A12d slice D4 acceptance: auditor D3-post P0 (atomic-requirement
grammar v3) + P1 (stray-symlink closure, capability-lock-v3).

The v2 conformance bridge is disjunction-blind: `{"requires": "local or
remote, v1 or v2, sha256 or blake3 manifests"}` could mark
`fam05.local_v1_sha256` supported. The v3 atomic grammar fails such
texts CONSERVATIVE (INADMISSIBLE, contributing NO evidence), closes the
symlinked-stray evasion in `_stray_capability_dirs`, and bumps the lock
schema to capability-lock-v3. Driven through the REAL production path
(fixture T0/T1 builds -> promotion controller -> order provenance
re-derivation -> CAPABILITY_LOCK), never a claim:

  D4a live governed map is t4-conformance-v3 /
      atomic-requirement-grammar-v3 with the two frozen tables exact
  D4b the auditor exact example + the three acceptance attacks + a
      slash-only variant + a comma-list variant are INADMISSIBLE at
      the text level AND mint non-discriminating locks with empty
      support and a grammar-named cause
  D4c `local and v1 and sha256 manifests` stays admissible and still
      supports fam05.local_v1_sha256 (minted lock discriminating);
      the six default family texts and the two `Any...` fixture texts
      stay admissible (no over-reach)
  D4d stray-symlink acceptance: an unexpected fam07/capability
      symlink -> readiness FAILURE naming the exact stray path
  D4e stale capability-lock-v2 -> FAILURE naming the cell; fresh
      locks are v3 and bind the live map sha

Deferred-to-A14 out of scope: NO assertions about the NOT-PROMOTED
scheduler here.

Stdlib only. Hermetic fixtures in throwaway dirs (live-tree reads are
read-only). Prints `H26 D4 smoke: N/N closed`; exits non-zero on any
failure.
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

import conformance as CONF  # noqa: E402
import lock as LOCK_MOD  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import specificity  # noqa: E402

from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")
LIVE_MAP = os.path.join(FAMC, "T4-CONFORMANCE.json")
LIVE_MAP_SHA = hashlib.sha256(open(LIVE_MAP, "rb").read()).hexdigest()
FAM05_ID = "fam05.local_v1_sha256"
CORE = "generic capability"

# Auditor attack texts (verbatim) plus the slash/comma variants.
ATT_EXACT = "local or remote, v1 or v2, sha256 or blake3 manifests"
ATT_A = "local or remote v1/v2 manifests"
ATT_B = "acyclic or cyclic input"
ATT_C = "same or mixed units"
ATT_SLASH = "local v1/v2 sha256 manifests"
ATT_COMMA = "local, v1, sha256 manifest formats"
ATTACKS = [ATT_EXACT, ATT_A, ATT_B, ATT_C, ATT_SLASH, ATT_COMMA]

BENIGN_AND = "local and v1 and sha256 manifests"

# The six default D3/D4 family texts (H25/D4-gate CONTRACT).
DEFAULTS = {
    "fam01": "each summary row is an aggregate record",
    "fam02": "pages must be disjoint",
    "fam03": "identical repeats are duplicates",
    "fam04": "the input must be acyclic",
    "fam05": "only local v1 sha256 manifests",
    "fam06": "a common unit basis is required",
}
FIXTURE_ANY = [
    "Any tags present arrive as strings joined by a delimiter.",
    "Any hiccup is short-lived and announced up front.",
]


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def hermetic(tag):
    root = tempfile.mkdtemp(prefix="h26-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md",
                 "ORDER.md"):
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


def v2_contract(pre_texts=None, lim_texts=None):
    return {"semantic_core": CORE,
            "preconditions": [{"requires": t} for t in (pre_texts or [])],
            "limitations": list(lim_texts or [])}


def mint(tag, contract, universe="A"):
    """Full production path for one contract. Returns (root, receipt,
    lock) on success; raises the controller refusal otherwise."""
    root = hermetic(tag)
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", universe)
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", universe)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=contract)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", "fam05", universe, FREEZE,
                            evidence_grade="harness-validation")
    assert res["event"] == "PROMOTION", res
    res2 = promotion.advance(root, "PQ", "fam05", universe, FREEZE,
                             evidence_grade="harness-validation")
    assert res2["event"] == "CAPABILITY_LOCK", res2
    capdir = order.capability_dir(root, "PQ", universe, "fam05")
    lock = json.load(open(os.path.join(capdir, "CAPABILITY_LOCK.json")))
    return root, json.load(open(res["receipt"])), lock


cmap = CONF.load(FAMC)

# --- D4a: the live governed map is the amended v3 atomic grammar ------
check("D4a live map version is t4-conformance-v3 with rule "
      "atomic-requirement-grammar-v3 and the live sha",
      cmap["version"] == "t4-conformance-v3"
      and cmap["rule"] == "atomic-requirement-grammar-v3"
      and cmap["conformance_map_sha256"] == LIVE_MAP_SHA,
      f"v={cmap.get('version')} r={cmap.get('rule')}")
check("D4a disjunction_markers frozen to ['either', 'or'] and "
      "structural_separators frozen to ['/', ',']",
      cmap.get("disjunction_markers") == ["either", "or"]
      and cmap.get("structural_separators") == ["/", ","],
      f"dj={cmap.get('disjunction_markers')} "
      f"sep={cmap.get('structural_separators')}")

# --- D4b: attacks are INADMISSIBLE and mint NF grammar-named locks -----
for i, att in enumerate(ATTACKS):
    check(f"D4b attack #{i + 1} {att[:44]!r} is INADMISSIBLE at the "
          f"text level",
          CONF.admissible(att, cmap) is False)
    _root, _rec, _lock = mint(f"D4b-{i}", v2_contract([att]))
    check(f"D4b attack #{i + 1} mints a non-discriminating lock with "
          f"empty support and a grammar-named cause",
          _lock.get("non_discriminating") is True
          and _lock.get("supported_t4_ids") == []
          and FAM05_ID not in (_lock.get("supported_t4_ids") or [])
          and "atomic-grammar-inadmissible" in
          (_lock.get("conformance_cause") or ""),
          f"nd={_lock.get('non_discriminating')} "
          f"sup={_lock.get('supported_t4_ids')} "
          f"cause={str(_lock.get('conformance_cause'))[:140]!r}")

# --- D4c: no over-reach ------------------------------------------------
check("D4c `local and v1 and sha256 manifests` stays admissible",
      CONF.admissible(BENIGN_AND, cmap) is True)
_vb = CONF.verdict("fam05", [BENIGN_AND], cmap)
check("D4c the `and` conjunction still supports "
      "fam05.local_v1_sha256 at the text level",
      _vb["non_discriminating"] is False
      and FAM05_ID in _vb["supported_t4_ids"],
      f"nd={_vb['non_discriminating']} sup={_vb['supported_t4_ids']}")
_rootc, _recc, _lockc = mint("D4c-and", v2_contract([BENIGN_AND]))
check("D4c the `and` conjunction mints a discriminating lock",
      _lockc.get("non_discriminating") is False
      and _lockc.get("supported_t4_ids") == [FAM05_ID]
      and _lockc.get("schema_version") == "capability-lock-v3"
      and _lockc.get("conformance_map_sha256") == LIVE_MAP_SHA,
      f"nd={_lockc.get('non_discriminating')} "
      f"sup={_lockc.get('supported_t4_ids')}")
_c6ok = True
for _fam, _txt in DEFAULTS.items():
    if not CONF.admissible(_txt, cmap):
        _c6ok = False
check("D4c all six default family texts stay admissible", _c6ok)
_v5 = CONF.verdict("fam05", [DEFAULTS["fam05"]], cmap)
check("D4c default fam05 contract still discriminating",
      _v5["non_discriminating"] is False
      and FAM05_ID in _v5["supported_t4_ids"],
      f"nd={_v5['non_discriminating']}")
check("D4c the two `Any...` fixture texts stay admissible",
      all(CONF.admissible(t, cmap) for t in FIXTURE_ANY))

# --- D4d: stray symlink -> FAILURE naming the exact path ---------------
_roots, _recs, _locks = mint("D4d-stray", v2_contract(
    ["only local v1 sha256 manifests"]))
_stray = os.path.join(_roots, "state", "PQ", "A", "fam07", "capability")
os.makedirs(os.path.dirname(_stray))
os.symlink("/tmp/h26-stray-target", _stray)
_rep = specificity.report(_roots)
check("D4d unexpected symlinked fam07/capability dir -> readiness "
      "FAILURE",
      _rep["verdict"] == "contract-conformance-FAILURE",
      f"verdict={_rep['verdict']}")
check("D4d problems name the exact stray path",
      any(_stray in str(p) for p in _rep["problems"]),
      f"probs={[str(p)[:80] for p in _rep['problems'][:3]]}")

# --- D4e: stale v2 refused; fresh locks v3 binding the live map --------
_rootv, _recv, _lockv = mint("D4e-stale", v2_contract(
    ["only local v1 sha256 manifests"]))
assert _lockv.get("non_discriminating") is False
_stale = dict(_lockv)
_stale["schema_version"] = "capability-lock-v2"
_reasons = LOCK_MOD.verify_lock(_stale, fam_c_dir=_rootv)
check("D4e stale capability-lock-v2 is LOCK-INADMISSIBLE naming "
      "schema_version",
      any("LOCK-INADMISSIBLE" in r and "schema_version" in r
          for r in _reasons),
      "; ".join(_reasons)[:200])
_lp = os.path.join(order.capability_dir(_rootv, "PQ", "A", "fam05"),
                   "CAPABILITY_LOCK.json")
json.dump(_stale, open(_lp, "w"), indent=1)
_repv = specificity.report(_rootv)
check("D4e stale-schema lock makes readiness FAILURE naming fam05",
      _repv["verdict"] == "contract-conformance-FAILURE"
      and any("fam05" in str(p) for p in _repv["problems"]),
      f"verdict={_repv['verdict']} "
      f"probs={[str(p)[:70] for p in _repv['problems'][:3]]}")
check("D4e fresh locks carry capability-lock-v3 and bind the live "
      "map sha",
      _lockv.get("schema_version") == "capability-lock-v3"
      and _lockv.get("conformance_map_sha256") == LIVE_MAP_SHA
      and LOCK_MOD.verify_lock(_lockv, fam_c_dir=_rootv) == [],
      f"sv={_lockv.get('schema_version')} "
      f"map={str(_lockv.get('conformance_map_sha256'))[:12]}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH26 D4 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

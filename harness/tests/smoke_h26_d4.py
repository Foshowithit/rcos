#!/usr/bin/env python3
"""H26 — A12d slice D4 acceptance, reframed by slice D5 for the v4
structural atomic conjunction (auditor D4-post P0) + P1 (stray-symlink
closure, capability-lock-v4).

The v3 grammar is conditional-clause blind: `when local use v1 sha256
manifests; when remote use blake3 manifests` carries no `or`/`,`/`/`
token yet still matches `local`+`v1`+`sha256`. The v4 structural
grammar makes such clauses UNREPRESENTABLE as conformance evidence
(refused at promotion), closes the symlinked-parent stray evasion in
`_stray_capability_dirs`, and bumps the lock schema to
capability-lock-v4 with the renamed presence field. Driven through the
REAL production path (fixture T0/T1 builds -> promotion controller ->
order provenance re-derivation -> CAPABILITY_LOCK), never a claim:

  D4a live governed map is t4-conformance-v4 /
      atomic-conjunction-grammar-v4 with the frozen tables exact
  D4b the two auditor conditional clauses (as single precondition
      elements and as token-encoded lists) plus uppercase, duplicate,
      disjunctive and out-of-vocabulary token lists are INADMISSIBLE at
      the token level AND refused as contracts with PROMOTION-DENY
      naming the offender
  D4c `["local", "v1", "sha256"]` stays admissible and still supports
      fam05.local_v1_sha256 (minted lock discriminating); the six
      default family token sets stay admissible; limitations prose
      never negates (no over-reach)
  D4d stray-symlink acceptance: a symlinked fam07 PARENT hiding a
      capability dir -> readiness FAILURE naming the exact symlink
      path, target never followed
  D4e stale capability-lock-v3 -> FAILURE naming the cell; fresh
      locks are v4 and bind the live map sha

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

# Auditor conditional-clause attacks (verbatim from the auditor reply).
COND_1 = "when local use v1 sha256 manifests; when remote use blake3 manifests"
COND_2 = "local v1 sha256 when local; remote blake3 when remote"
COND_TOKENS = ["when", "local", "use", "v1", "sha256", "manifests",
               "when", "remote", "use", "blake3", "manifests"]
# Six inadmissible candidates: the two conditional texts as single
# precondition elements plus four malformed token lists.
ATTACKS = [
    ([COND_1], "when"),
    ([COND_2], "when"),
    (COND_TOKENS, "when"),
    (["Local"], "Local"),
    (["local", "local"], "local"),
    (["local", "or", "sha256"], "or"),
]

BENIGN = ["local", "v1", "sha256"]

# The six default D5 family token sets (H25/D5-gate CONTRACT).
DEFAULTS = {
    "fam01": ["summary", "row"],
    "fam02": ["pages", "disjoint"],
    "fam03": ["identical", "repeats"],
    "fam04": ["acyclic"],
    "fam05": ["local", "sha256"],
    "fam06": ["common", "unit"],
}


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


def v4_contract(pre_lists=None, lim_texts=None):
    return {"semantic_core": CORE,
            "preconditions": [{"requires_all": list(t)}
                              for t in (pre_lists or [])],
            "limitations": list(lim_texts or [])}


def refuse_reason(tag, contract):
    """Build T0/T1 then promote; return the refusal string (or None when
    promotion unexpectedly succeeds)."""
    root = hermetic(tag)
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=contract)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    try:
        promotion.promote_universe(root, "PQ", "fam05", "A", FREEZE,
                                   "harness-validation")
    except (PermissionError, ValueError) as e:
        return str(e)
    return None


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
check("D4a live map version is t4-conformance-v4 with rule "
      "atomic-conjunction-grammar-v4 and the live sha",
      cmap["version"] == "t4-conformance-v4"
      and cmap["rule"] == "atomic-conjunction-grammar-v4"
      and cmap["conformance_map_sha256"] == LIVE_MAP_SHA,
      f"v={cmap.get('version')} r={cmap.get('rule')}")
check("D4a frozen tables exact (disjunction, separators, 23-token "
      "derived vocabulary)",
      cmap.get("disjunction_markers") == ["either", "or"]
      and cmap.get("structural_separators") == ["/", ","]
      and cmap.get("atomic_vocabulary") == ["acyclic", "acyclicity",
            "aggregate", "basis", "common", "dedup", "disjoint",
            "duplicates", "identical", "input", "local", "order",
            "pages", "record", "repeats", "row", "same", "sha256",
            "summary", "topological", "unit", "units", "v1"],
      f"dj={cmap.get('disjunction_markers')} "
      f"sep={cmap.get('structural_separators')} "
      f"vocab={len(cmap.get('atomic_vocabulary') or [])}")

# --- D4b: attacks are INADMISSIBLE and refused as contracts ------------
for i, (att, needle) in enumerate(ATTACKS):
    check(f"D4b attack #{i + 1} {str(att)[:44]!r} is INADMISSIBLE at "
          f"the token level",
          CONF.admissible(att, cmap) is False)
    _reason = refuse_reason(f"D4b-{i}", v4_contract([att]))
    check(f"D4b attack #{i + 1} is refused as a v4 contract "
          f"(PROMOTION-DENY naming {needle!r})",
          _reason is not None and "PROMOTION-DENY" in _reason
          and needle in _reason,
          f"reason={str(_reason)[:140]!r}")

# --- D4c: no over-reach ------------------------------------------------
check("D4c `['local', 'v1', 'sha256']` stays admissible",
      CONF.admissible(BENIGN, cmap) is True)
_vb = CONF.verdict("fam05", [BENIGN], cmap)
check("D4c the benign conjunction still supports "
      "fam05.local_v1_sha256 at the token level",
      _vb["non_discriminating"] is False
      and FAM05_ID in _vb["supported_t4_ids"],
      f"nd={_vb['non_discriminating']} sup={_vb['supported_t4_ids']}")
_rootc, _recc, _lockc = mint("D4c-benign", v4_contract([BENIGN]))
check("D4c the benign conjunction mints a discriminating lock",
      _lockc.get("non_discriminating") is False
      and _lockc.get("supported_t4_ids") == [FAM05_ID]
      and _lockc.get("schema_version") == "capability-lock-v4"
      and _lockc.get("conformance_map_sha256") == LIVE_MAP_SHA,
      f"nd={_lockc.get('non_discriminating')} "
      f"sup={_lockc.get('supported_t4_ids')}")
_c6ok = True
for _fam, _toks in DEFAULTS.items():
    if not CONF.admissible(_toks, cmap):
        _c6ok = False
check("D4c all six default family token sets stay admissible", _c6ok)
_v5 = CONF.verdict("fam05", [DEFAULTS["fam05"]], cmap)
check("D4c default fam05 contract still discriminating",
      _v5["non_discriminating"] is False
      and FAM05_ID in _v5["supported_t4_ids"],
      f"nd={_v5['non_discriminating']}")
_v5l = CONF.verdict("fam05", [DEFAULTS["fam05"]], cmap,
                    limitations=[COND_1, COND_2])
check("D4c limitations prose never negates an admissible token list",
      _v5l["non_discriminating"] is False
      and FAM05_ID in _v5l["supported_t4_ids"],
      f"nd={_v5l['non_discriminating']}")

# --- D4d: symlinked parent -> FAILURE naming the exact path ------------
_roots, _recs, _locks = mint("D4d-stray", v4_contract(
    [["local", "v1", "sha256"]]))
_tgt = tempfile.mkdtemp(prefix="h26-stray-target-")
os.makedirs(os.path.join(_tgt, "capability"))
_fam07 = os.path.join(_roots, "state", "PQ", "A", "fam07")
os.symlink(_tgt, _fam07)
_rep = specificity.report(_roots)
check("D4d symlinked fam07 parent hiding a capability dir -> readiness "
      "FAILURE",
      _rep["verdict"] == "contract-conformance-FAILURE",
      f"verdict={_rep['verdict']}")
check("D4d problems name the exact symlink path (target never followed)",
      any(_fam07 in str(p) and _tgt not in str(p)
          for p in _rep["problems"])
      and not any(str(p).startswith(_tgt) for p in _rep["problems"]),
      f"probs={[str(p)[:80] for p in _rep['problems'][:3]]}")

# --- D4e: stale v3 refused; fresh locks v4 binding the live map --------
_rootv, _recv, _lockv = mint("D4e-stale", v4_contract(
    [["local", "v1", "sha256"]]))
assert _lockv.get("non_discriminating") is False
_stale = dict(_lockv)
_stale["schema_version"] = "capability-lock-v3"
_reasons = LOCK_MOD.verify_lock(_stale, fam_c_dir=_rootv)
check("D4e stale capability-lock-v3 is LOCK-INADMISSIBLE naming "
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
check("D4e fresh locks carry capability-lock-v4 and bind the live "
      "map sha",
      _lockv.get("schema_version") == "capability-lock-v4"
      and _lockv.get("conformance_map_sha256") == LIVE_MAP_SHA
      and LOCK_MOD.verify_lock(_lockv, fam_c_dir=_rootv) == [],
      f"sv={_lockv.get('schema_version')} "
      f"map={str(_lockv.get('conformance_map_sha256'))[:12]}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH26 D4 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

#!/usr/bin/env python3
"""H27 — A12d slice D5 acceptance: structural atomic conjunction v4 +
stray-symlink closure + capability-lock-v4 field rename (auditor
D4-post P0/P1/P1).

The v3 grammar is conditional-clause blind (`when local use v1 sha256
manifests; when remote use blake3 manifests` matches local+v1+sha256);
the D4 stray walk drops symlinked parents; the v3 lock carries the
stale `limitation_present` field. The v4 structural conjunction makes
conditional clauses UNREPRESENTABLE as conformance evidence (refused
at promotion, never supported, never negated), fails ANY unexpected
symlink beneath state/ naming the exact path without following it, and
renames the lock field to `declared_limitations_present`. Driven
through the REAL production path (fixture T0/T1 builds -> promotion
controller -> order provenance re-derivation -> CAPABILITY_LOCK),
never a claim — both directions (refusal + support):

  D5a map / shape / attacks / positive control / six-family
      no-overreach
  D5b parent / dangling / deep symlinks fail; expected-path
      capability symlink stays legal
  D5c v4 schema / rename / refusals / specificity indifference

Stdlib only. Hermetic fixtures in throwaway dirs (live-tree reads are
read-only). Prints `H27 D5 smoke: N/N closed`; exits non-zero on any
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
SOLVER = "import sys; sys.exit(0)\n"
ADAPTER = "import sys; sys.exit(0)\n"
LIVE_MAP = os.path.join(FAMC, "T4-CONFORMANCE.json")
LIVE_MAP_SHA = hashlib.sha256(open(LIVE_MAP, "rb").read()).hexdigest()
FAM05_ID = "fam05.local_v1_sha256"
CORE = "generic capability"
VOCAB = ["acyclic", "acyclicity", "aggregate", "basis", "common", "dedup",
         "disjoint", "duplicates", "identical", "input", "local", "order",
         "pages", "record", "repeats", "row", "same", "sha256", "summary",
         "topological", "unit", "units", "v1"]

# Auditor conditional-clause attacks (verbatim from the auditor reply).
COND_1 = "when local use v1 sha256 manifests; when remote use blake3 manifests"
COND_2 = "local v1 sha256 when local; remote blake3 when remote"
COND_TOKENS = ["when", "local", "use", "v1", "sha256", "manifests",
               "when", "remote", "use", "blake3", "manifests"]

# One precondition per family, each drawn only from that family's own
# frozen predicate tokens (six-family no-overreach control).
CONTRACT = {
    "fam01": {"requires_all": ["summary", "row"]},
    "fam02": {"requires_all": ["pages", "disjoint"]},
    "fam03": {"requires_all": ["identical", "repeats"]},
    "fam04": {"requires_all": ["acyclic"]},
    "fam05": {"requires_all": ["local", "sha256"]},
    "fam06": {"requires_all": ["common", "unit"]},
}
OWN_ID = {"fam01": "fam01.rows_are_records",
          "fam02": "fam02.pages_disjoint",
          "fam03": "fam03.repeats_are_duplicates",
          "fam04": "fam04.promised_acyclic",
          "fam05": "fam05.local_v1_sha256",
          "fam06": "fam06.common_unit_basis"}


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def hermetic(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h27-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md",
                 "ORDER.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for family in families:
        shutil.copytree(os.path.join(FAMC, "families", family),
                        os.path.join(fam, family))
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


def capdir(root, block, universe, family):
    return os.path.join(root, "state", block, universe, family,
                        "capability")


cmap = CONF.load(FAMC)

# --- D5a: the live governed map is the v4 structural grammar ----------
check("D5a live map is t4-conformance-v4 / "
      "atomic-conjunction-grammar-v4",
      cmap["version"] == "t4-conformance-v4"
      and cmap["rule"] == "atomic-conjunction-grammar-v4"
      and cmap["conformance_map_sha256"] == LIVE_MAP_SHA)
check("D5a atomic_vocabulary is the frozen 23-token list",
      cmap.get("atomic_vocabulary") == VOCAB)
check("D5a vocabulary equals the sorted union of predicate tokens",
      sorted({t for f in cmap["families"].values()
              for p in f["requires_predicates"] for t in p}) == VOCAB)

# --- D5a: loader refuses a tampered / missing vocabulary ---------------
_tmp = hermetic("vocab-tamper")
_mut = json.load(open(os.path.join(_tmp, "T4-CONFORMANCE.json")))
_mut["atomic_vocabulary"] = list(VOCAB) + ["when"]
json.dump(_mut, open(os.path.join(_tmp, "T4-CONFORMANCE.json"), "w"))
try:
    CONF.load(_tmp)
    _tok = "loaded (fail-open)"
except Exception as e:  # noqa: BLE001
    _tok = f"{type(e).__name__}: {e}"
check("D5a loader refuses a tampered atomic_vocabulary",
      "loaded" not in _tok and "atomic_vocabulary" in _tok, _tok[:120])
_tmp2 = hermetic("vocab-missing")
_mut2 = json.load(open(os.path.join(_tmp2, "T4-CONFORMANCE.json")))
_mut2.pop("atomic_vocabulary", None)
json.dump(_mut2, open(os.path.join(_tmp2, "T4-CONFORMANCE.json"), "w"))
try:
    CONF.load(_tmp2)
    _tok2 = "loaded (fail-open)"
except Exception as e:  # noqa: BLE001
    _tok2 = f"{type(e).__name__}: {e}"
check("D5a loader refuses a missing atomic_vocabulary",
      "loaded" not in _tok2 and "atomic_vocabulary" in _tok2,
      _tok2[:120])

# --- D5a: v4 shape accepted; every malformed shape refused -------------
_ok = refuse_reason("d5a-valid", v4_contract([["local", "v1", "sha256"]]))
check("D5a a v4 requires_all contract promotes (no refusal)", _ok is None,
      str(_ok)[:120])
for _label, _pre, _needle in (
        ("bare-string precondition", ["local v1 sha256"], "precondition"),
        ("old requires key", [{"requires": "local v1 sha256"}], "requires"),
        ("empty requires_all", [{"requires_all": []}], "requires_all"),
        ("non-atomic token", [{"requires_all": ["local local"]}],
         "local local"),
        ("uppercase token", [{"requires_all": ["Local"]}], "Local"),
        ("out-of-vocabulary token", [{"requires_all": ["when"]}], "when"),
        ("duplicate token", [{"requires_all": ["local", "local"]}],
         "local"),
        ("extra key", [{"requires_all": ["local"], "prose": "x"}],
         "prose"),
        ("token-encoded conditional", [{"requires_all": COND_TOKENS}],
         "when")):
    _r = refuse_reason("d5a-" + _label.split()[0],
                       {"semantic_core": CORE, "preconditions": _pre,
                        "limitations": []})
    check(f"D5a malformed contract refused ({_label})",
          _r is not None and "PROMOTION-DENY" in _r and _needle in _r,
          str(_r)[:140])

# --- D5a: auditor conditional clauses support nothing ------------------
_rootl, _recl, _lockl = mint(
    "d5a-lim", v4_contract([["basis"]], [COND_1, COND_2]))
check("D5a conditional texts as limitations prose give NO support",
      _lockl.get("non_discriminating") is True
      and _lockl.get("supported_t4_ids") == [],
      f"nd={_lockl.get('non_discriminating')} "
      f"sup={_lockl.get('supported_t4_ids')}")
_rootl2, _recl2, _lockl2 = mint(
    "d5a-lim2", v4_contract([["local", "sha256"]], [COND_1]))
check("D5a limitations prose never negates admissible tokens",
      _lockl2.get("non_discriminating") is False
      and _lockl2.get("supported_t4_ids") == [FAM05_ID])
try:
    CONF.verdict("fam05", [COND_1], cmap)
    _bv = "coerced (fail-open)"
except Exception as e:  # noqa: BLE001
    _bv = f"{type(e).__name__}"
check("D5a conformance API raises on a bare-string candidate",
      _bv != "coerced (fail-open)", _bv)
try:
    _adm = CONF.admissible(COND_TOKENS, cmap)
    _aw = (_adm is False)
except Exception:  # noqa: BLE001
    _aw = True
check("D5a conformance API refuses a conditional token list", _aw)

# --- D5a: positive control through the real mint path ------------------
_rootp, _recp, _lockp = mint(
    "d5a-pos", v4_contract([["local", "v1", "sha256"]]))
check("D5a positive control mints a DISCRIMINATING lock for exactly "
      "fam05.local_v1_sha256",
      _lockp.get("non_discriminating") is False
      and _lockp.get("supported_t4_ids") == [FAM05_ID])
check("D5a fresh lock schema is capability-lock-v4",
      _lockp.get("schema_version") == "capability-lock-v4")
check("D5a fresh lock carries declared_limitations_present (not the "
      "retired name)",
      "declared_limitations_present" in _lockp
      and "limitation_present" not in _lockp)
check("D5a fresh lock records requires_all verbatim",
      _lockp.get("preconditions") == [{"requires_all": ["local", "v1",
                                                        "sha256"]}])
check("D5a fresh lock binds the live map sha",
      _lockp.get("conformance_map_sha256") == LIVE_MAP_SHA)

# --- D5a: six-family no-overreach through one full walk ----------------
_root6 = hermetic("six", families=tuple(f"fam0{i}" for i in range(1, 7)))
_exp6 = order.load_expansion(_root6)
_t0sha = {}
for _c in _exp6["cells"]:
    _b, _u, _f, _ev = (_c["block"], _c["universe"], _c["family"],
                       _c["event"])
    if _ev == "PROMOTION":
        promotion.promote_universe(_root6, _b, _f, _u, FREEZE,
                                   "harness-validation")
    elif _ev == "CAPABILITY_LOCK":
        promotion.advance(_root6, _b, _f, _u, FREEZE,
                          "harness-validation")
    elif _ev == "T1":
        build_model_run(_root6, cell=_c, freeze_commit=FREEZE,
                        solver_py=SOLVER,
                        validates_candidate=_t0sha[(_b, _u, _f)],
                        adapter_py=ADAPTER,
                        candidate_validation={
                            "checker_sha256": _sha_file(os.path.join(
                                _root6, "families", _f, "check.py")),
                            "truth_sha256": _sha_file(os.path.join(
                                _root6, "families", _f, "truth.json")),
                            "checker_returncode": 0,
                            "validation_verdict": "ship",
                            "validated": True})
    else:
        _d = build_model_run(
            _root6, cell=_c, freeze_commit=FREEZE, solver_py=SOLVER,
            producer_contract={"semantic_core": CORE,
                               "preconditions": [CONTRACT[_f]],
                               "limitations": []})
        if _ev == "T0":
            _t0sha[(_b, _u, _f)] = t0_candidate_sha256(_d)
for _f in sorted(CONTRACT):
    _lk = json.load(open(os.path.join(
        capdir(_root6, "PQ", "A", _f), "CAPABILITY_LOCK.json")))
    check(f"D5a {_f} lock discriminating for exactly its own id",
          _lk.get("non_discriminating") is False
          and _lk.get("supported_t4_ids") == [OWN_ID[_f]],
          f"sup={_lk.get('supported_t4_ids')}")
_rep6 = specificity.report(_root6)
check("D5a clean v4 full walk is READY", _rep6["verdict"] ==
      "contract-conformance-READY", _rep6["verdict"])

# --- D5b: ANY unexpected symlink beneath state/ fails -----------------
_rootb = hermetic("stray-parent",
                  families=tuple(f"fam0{i}" for i in range(1, 7)))
_exp_b = order.load_expansion(_rootb)
_t0b = {}
for _c in _exp_b["cells"]:
    _b, _u, _f, _ev = (_c["block"], _c["universe"], _c["family"],
                       _c["event"])
    if _ev == "PROMOTION":
        promotion.promote_universe(_rootb, _b, _f, _u, FREEZE,
                                   "harness-validation")
    elif _ev == "CAPABILITY_LOCK":
        promotion.advance(_rootb, _b, _f, _u, FREEZE,
                          "harness-validation")
    elif _ev == "T1":
        build_model_run(_rootb, cell=_c, freeze_commit=FREEZE,
                        solver_py=SOLVER,
                        validates_candidate=_t0b[(_b, _u, _f)],
                        adapter_py=ADAPTER,
                        candidate_validation={
                            "checker_sha256": _sha_file(os.path.join(
                                _rootb, "families", _f, "check.py")),
                            "truth_sha256": _sha_file(os.path.join(
                                _rootb, "families", _f, "truth.json")),
                            "checker_returncode": 0,
                            "validation_verdict": "ship",
                            "validated": True})
    else:
        _d = build_model_run(
            _rootb, cell=_c, freeze_commit=FREEZE, solver_py=SOLVER,
            producer_contract={"semantic_core": CORE,
                               "preconditions": [CONTRACT[_f]],
                               "limitations": []})
        if _ev == "T0":
            _t0b[(_b, _u, _f)] = t0_candidate_sha256(_d)
_tgt = tempfile.mkdtemp(prefix="h27-stray-target-")
os.makedirs(os.path.join(_tgt, "capability"))
_fam07 = os.path.join(_rootb, "state", "PQ", "A", "fam07")
os.symlink(_tgt, _fam07)
_repb = specificity.report(_rootb)
check("D5b symlinked fam07 parent -> FAILURE",
      _repb["verdict"] == "contract-conformance-FAILURE",
      _repb["verdict"])
check("D5b problems name the symlink path (target never followed)",
      any(_fam07 in str(p) and _tgt not in str(p)
          for p in _repb["problems"])
      and not any(str(p).startswith(_tgt) for p in _repb["problems"]),
      str(_repb["problems"])[:160])

_rootd = hermetic("stray-dangling",
                  families=tuple(f"fam0{i}" for i in range(1, 7)))
_dang = os.path.join(_rootd, "state", "PQ", "A", "fam08")
os.makedirs(os.path.dirname(_dang), exist_ok=True)
os.symlink("/nonexistent-h27-dangling-target", _dang)
_repd = specificity.report(_rootd)
check("D5b dangling unexpected symlink -> FAILURE naming it",
      _repd["verdict"] == "contract-conformance-FAILURE"
      and any("fam08" in str(p) for p in _repd["problems"]),
      _repd["verdict"])

_rootdp = hermetic("stray-deep",
                   families=tuple(f"fam0{i}" for i in range(1, 7)))
_deep = os.path.join(_rootdp, "state", "PQ", "A", "linkdir")
os.makedirs(os.path.dirname(_deep), exist_ok=True)
os.symlink("/tmp", _deep)
_repdp = specificity.report(_rootdp)
check("D5b deep unexpected symlink -> FAILURE naming it",
      _repdp["verdict"] == "contract-conformance-FAILURE"
      and any("linkdir" in str(p) for p in _repdp["problems"]),
      _repdp["verdict"])

# Regression: an expected-path capability symlink stays legal.
_roote = hermetic("seam", families=("fam05",))
_expe = order.load_expansion(_roote)
_t0e = {}
for _c in _expe["cells"][:4]:
    _b, _u, _f, _ev = (_c["block"], _c["universe"], _c["family"],
                       _c["event"])
    if _ev == "PROMOTION":
        promotion.promote_universe(_roote, _b, _f, _u, FREEZE,
                                   "harness-validation")
    elif _ev == "CAPABILITY_LOCK":
        promotion.advance(_roote, _b, _f, _u, FREEZE,
                          "harness-validation")
    elif _ev == "T1":
        build_model_run(_roote, cell=_c, freeze_commit=FREEZE,
                        solver_py=SOLVER,
                        validates_candidate=_t0e[(_b, _u, _f)],
                        adapter_py=ADAPTER,
                        candidate_validation={
                            "checker_sha256": _sha_file(os.path.join(
                                _roote, "families", _f, "check.py")),
                            "truth_sha256": _sha_file(os.path.join(
                                _roote, "families", _f, "truth.json")),
                            "checker_returncode": 0,
                            "validation_verdict": "ship",
                            "validated": True})
    else:
        _d = build_model_run(
            _roote, cell=_c, freeze_commit=FREEZE, solver_py=SOLVER,
            producer_contract={"semantic_core": CORE,
                               "preconditions":
                               [{"requires_all": ["local", "sha256"]}],
                               "limitations": []})
        if _ev == "T0":
            _t0e[(_b, _u, _f)] = t0_candidate_sha256(_d)
_cell = capdir(_roote, "PQ", "A", "fam05")
_keep = tempfile.mkdtemp(prefix="h27-seam-")
shutil.move(_cell, os.path.join(_keep, "capability"))
os.symlink(os.path.join(_keep, "capability"), _cell)
_repe = specificity.report(_roote)
check("D5b expected-path capability symlink stays legal (no stray/symlink problem)",
      _repe["verdict"] == "contract-conformance-INCOMPLETE"
      and not any("symlink" in str(p).lower() or "stray" in str(p).lower()
                  for p in _repe["problems"]),
      f"{_repe['verdict']} problems={str(_repe['problems'])[:120]}")

# --- D5c: lock schema v4 + rename --------------------------------------
_roots = hermetic("stale",
                  families=tuple(f"fam0{i}" for i in range(1, 7)))
_exps = order.load_expansion(_roots)
_t0s = {}
for _c in _exps["cells"]:
    _b, _u, _f, _ev = (_c["block"], _c["universe"], _c["family"],
                       _c["event"])
    if _ev == "PROMOTION":
        promotion.promote_universe(_roots, _b, _f, _u, FREEZE,
                                   "harness-validation")
    elif _ev == "CAPABILITY_LOCK":
        promotion.advance(_roots, _b, _f, _u, FREEZE,
                          "harness-validation")
    elif _ev == "T1":
        build_model_run(_roots, cell=_c, freeze_commit=FREEZE,
                        solver_py=SOLVER,
                        validates_candidate=_t0s[(_b, _u, _f)],
                        adapter_py=ADAPTER,
                        candidate_validation={
                            "checker_sha256": _sha_file(os.path.join(
                                _roots, "families", _f, "check.py")),
                            "truth_sha256": _sha_file(os.path.join(
                                _roots, "families", _f, "truth.json")),
                            "checker_returncode": 0,
                            "validation_verdict": "ship",
                            "validated": True})
    else:
        _d = build_model_run(
            _roots, cell=_c, freeze_commit=FREEZE, solver_py=SOLVER,
            producer_contract={"semantic_core": CORE,
                               "preconditions": [CONTRACT[_f]],
                               "limitations": []})
        if _ev == "T0":
            _t0s[(_b, _u, _f)] = t0_candidate_sha256(_d)
_p3 = os.path.join(capdir(_roots, "PQ", "A", "fam03"),
                   "CAPABILITY_LOCK.json")
_l3 = json.load(open(_p3))
_l3["schema_version"] = "capability-lock-v3"
json.dump(_l3, open(_p3, "w"))
_rep3 = specificity.report(_roots)
check("D5c stale capability-lock-v3 -> FAILURE naming fam03",
      _rep3["verdict"] == "contract-conformance-FAILURE"
      and any("fam03" in str(p) for p in _rep3["problems"]),
      _rep3["verdict"])
_oldf = dict(_lockp, limitation_present=True)
check("D5c verify_lock refuses a lock still carrying the retired field",
      any("limitation_present" in str(p)
          for p in LOCK_MOD.verify_lock(_oldf)),
      str(LOCK_MOD.verify_lock(_oldf)[:1])[:120])
_nonf = {k: v for k, v in _lockp.items()
         if k != "declared_limitations_present"}
check("D5c verify_lock names a missing declared_limitations_present",
      any("declared_limitations_present" in str(p)
          for p in LOCK_MOD.verify_lock(_nonf)))
_f5p = os.path.join(capdir(_root6, "PQ", "A", "fam05"),
                   "CAPABILITY_LOCK.json")
_f5 = json.load(open(_f5p))
_f5["declared_limitations_present"] = not _f5.get(
    "declared_limitations_present")
json.dump(_f5, open(_f5p, "w"))
_rep6f = specificity.report(_root6)
check("D5c flipping declared_limitations_present does not change "
      "readiness (specificity never consults the field)",
      _rep6f["verdict"] == "contract-conformance-READY",
      _rep6f["verdict"])
_src = open(os.path.join(HARNESS, "specificity.py")).read()
check("D5c specificity.py mentions neither the old nor the new field "
      "spelling",
      "limitation_present" not in _src
      and "declared_limitations_present" not in _src)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH27 D5 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

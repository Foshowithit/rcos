#!/usr/bin/env python3
"""H29 — A12d slice D8 acceptance: ONE shared producer-contract-shape
authority (P0) + lineage authority hygiene (P1).

D8.1 closes the second-authority gap: harness/contract_shape.py is the
ONE pure producer-contract-shape validator (no I/O, no globals, no
vocabulary knowledge), called by BOTH
harness/promotion.py::_producer_contract and harness/order.py's
PROMOTION-receipt provenance check. Seven hand-planted PROMOTION cells
— receipt fields and every arrival/artifact hash internally consistent,
T0 declaration malformed — are INADMISSIBLE through the REAL
order.cell_state path naming the defect, and the promotion controller
refuses the same declarations with the same finding text; a
well-formed declaration carrying an unknown atom stays ADMISSIBLE.

D8.2 removes the non-retrievable 9caf3d4fdd33 node (the a12 edge is
now 382a75fc -> 12dda202 direct) and tightens V2: exact governed set,
governed amendment files only, 64-hex node shas, an immovable
post-freeze genesis anchor, and retrievable bytes for every recorded
node (git-aware layer; validate_file_chain stays pure and I/O-free).

Proven through the real path plus hermetic mutations. Stdlib only.
Hermetic fixtures in throwaway dirs/repos (live-tree reads are
read-only, except one H22-style mutate-and-restore which is NOT used
here — no live-tree mutation at all). Prints `H29 D8 smoke: N/N
closed`; exits non-zero on any failure.
"""
import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, FAMC)

import promotion  # noqa: E402
import order  # noqa: E402
import contract_shape as CS  # noqa: E402
import preflight as PF  # noqa: E402

from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = "import sys; sys.exit(0)\n"
CORE = "generic capability"
FAM05_ID = "fam05.local_v1_sha256"


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def hermetic(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h29-" + tag + "-")
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


def v5_contract(pre_lists=None, lim_texts=None):
    return {"semantic_core": CORE,
            "preconditions": [{"requires_all": list(t)}
                              for t in (pre_lists or [])],
            "limitations": list(lim_texts or [])}


# --- the seven malformed declarations (each names its defect) -----------
_EXTRA = v5_contract([["local", "v1", "sha256"]])
_EXTRA["also_supports"] = ["remote", "blake3"]
_MISSING = {"semantic_core": CORE,
            "preconditions": [{"requires_all": ["local", "v1", "sha256"]}]}
_RETIRED = {"semantic_core": CORE,
            "preconditions": [{"requires": ["local", "v1", "sha256"]}],
            "limitations": []}
_EMPTY = {"semantic_core": CORE, "preconditions": [{"requires_all": []}],
          "limitations": []}
_UPPER = {"semantic_core": CORE,
          "preconditions": [{"requires_all": ["Local"]}], "limitations": []}
_NONATOMIC = {"semantic_core": CORE,
              "preconditions": [{"requires_all": ["local local"]}],
              "limitations": []}
_DUP = {"semantic_core": CORE,
        "preconditions": [{"requires_all": ["local", "local"]}],
        "limitations": []}
MALFORMED = [
    ("extra-top-level-key", _EXTRA, "also_supports"),
    ("missing-limitations", _MISSING, "limitations"),
    ("retired-requires", _RETIRED, "requires"),
    ("empty-requires_all", _EMPTY, "requires_all"),
    ("uppercase-token", _UPPER, "Local"),
    ("non-atomic-token", _NONATOMIC, "local local"),
    ("duplicate-token", _DUP, "local"),
]
_CONTROL_PRE = [["local", "v1", "sha256", "manifest"]]


# --- golden twin: a valid PROMOTION receipt + capability files -----------
def _build_golden():
    root = hermetic("golden")
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER,
                         producer_contract=v5_contract(
                             [["local", "v1", "sha256"]]))
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                            evidence_grade="harness-validation")
    assert res["event"] == "PROMOTION", res
    return root, json.load(open(res["receipt"])), order.capability_dir(
        root, "PQ", "A", "fam05")


_GOLDEN_ROOT, _GOLDEN_REC, _GOLDEN_CAP = _build_golden()


def _chain_tip(run_dir):
    return order._chain_tip(os.path.join(run_dir, "EVIDENCE-CHAIN.jsonl"))


def _t1_validation_payload(t1_run_dir):
    for line in open(os.path.join(t1_run_dir, "EVIDENCE-CHAIN.jsonl")):
        line = line.strip()
        if not line:
            continue
        link = json.loads(line)
        if link.get("kind") == "candidate-validation":
            pay = dict(link.get("payload") or {})
            return {k: pay.get(k) for k in (
                "candidate_sha256", "executed_sha256", "adapter_sha256",
                "candidate_output_sha256", "checker_sha256", "truth_sha256",
                "checker_returncode", "validation_verdict", "validated",
                "candidate_input_manifest_sha256",
                "candidate_input_tree_sha256")}
    raise AssertionError("fixture T1 chain carries no candidate-validation")


def hand_plant(tag, declared):
    """Hand-plant a PROMOTION cell whose receipt fields and every
    arrival/artifact hash are internally consistent, but whose T0
    arrival declares `declared`. Returns (root, prom_cell). The receipt
    is the golden twin's production-minted receipt re-bound to THIS
    root's real chain tips / arrival bytes / T1 validation event, with
    the contract fields mirroring the malformed declaration verbatim
    and the golden capability files (hash-matching the receipt's
    artifact map) laid into this root's capability dir."""
    root = hermetic("plant-" + tag)
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    prom = order.expected_event(exp, "PQ", "fam05", "PROMOTION", "A")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=declared)
    d1 = build_model_run(root, cell=t1, freeze_commit=FREEZE,
                         solver_py=SOLVER,
                         validates_candidate=t0_candidate_sha256(d0))
    prun = order.ensure_namespace(root, "PQ", "A", "fam05",
                                  tail=("runs", prom["cell_id"]))
    rec = copy.deepcopy(_GOLDEN_REC)
    rec["acquisition_chain_tips"] = {"T0": _chain_tip(d0),
                                     "T1": _chain_tip(d1)}
    arrival = json.load(open(os.path.join(d0, "arrival.json")))
    payload = arrival.get("execution_payload") or {}
    rec["candidate"]["arrival_sha256"] = _sha_file(os.path.join(
        d0, "arrival.json"))
    rec["candidate"]["payload_sha256"] = hashlib.sha256(
        _canon(payload).encode()).hexdigest()
    rec["candidate"]["t1_validation"] = _t1_validation_payload(d1)
    for key in ("semantic_core", "preconditions", "limitations"):
        if key in declared:
            rec[key] = copy.deepcopy(declared[key])
        elif key in rec:
            del rec[key]
    if isinstance(rec.get("semantic_core"), str):
        rec["semantic_core_sha256"] = hashlib.sha256(
            rec["semantic_core"].encode()).hexdigest()
    rec["declared_limitations_present"] = bool(declared.get("limitations"))
    capdir = order.ensure_namespace(root, "PQ", "A", "fam05",
                                    tail=("capability",))
    for name in promotion.ARTIFACT_NAMES:
        shutil.copy2(os.path.join(_GOLDEN_CAP, name),
                     os.path.join(capdir, name))
    with open(os.path.join(prun, "PROMOTION-RECEIPT.json"), "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    return root, prom


def promote_refusal(tag, declared):
    """Run the REAL promotion controller on a T0/T1 pair declaring
    `declared`; return the refusal string (None when promotion
    unexpectedly succeeds)."""
    root = hermetic("promo-" + tag)
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=declared)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    try:
        promotion.promote_universe(root, "PQ", "fam05", "A", FREEZE,
                                   "harness-validation")
    except (PermissionError, ValueError) as e:
        return str(e)
    return None


# --- D8.1: seven malformed hand-plants INADMISSIBLE, naming the defect --
for _tag, _decl, _needle in MALFORMED:
    _shared = CS.validate(_decl)
    check(f"D8.1 shared finding exists for {_tag}",
          len(_shared) == 1 and _needle in _shared[0], str(_shared)[:160])
    _root, _prom = hand_plant(_tag, _decl)
    _st = order.cell_state(_root, _prom, FREEZE)
    check(f"D8.1 hand-planted {_tag} is INADMISSIBLE through "
          f"order.cell_state",
          _st["status"] == "INADMISSIBLE", _st["status"])
    check(f"D8.1 hand-planted {_tag} names {_needle!r} (shared text)",
          any(_shared[0] in r for r in _st["reasons"]),
          "; ".join(_st["reasons"])[:220])
    _msg = promote_refusal(_tag, _decl)
    check(f"D8.1 promotion refuses {_tag} with the SAME finding text",
          _msg is not None and "PROMOTION-DENY" in _msg
          and _shared[0] in _msg, str(_msg)[:200])

# --- D8.1 CONTROL: unknown atom stays ADMISSIBLE --------------------------
_ctrl_root = hermetic("control")
_ctrl_exp = order.load_expansion(_ctrl_root)
_ctrl_t0 = order.expected_event(_ctrl_exp, "PQ", "fam05", "T0", "A")
_ctrl_t1 = order.expected_event(_ctrl_exp, "PQ", "fam05", "T1", "A")
_ctrl_prom = order.expected_event(_ctrl_exp, "PQ", "fam05", "PROMOTION", "A")
_ctrl_d0 = build_model_run(_ctrl_root, cell=_ctrl_t0, freeze_commit=FREEZE,
                           solver_py=SOLVER,
                           producer_contract=v5_contract(_CONTROL_PRE))
build_model_run(_ctrl_root, cell=_ctrl_t1, freeze_commit=FREEZE,
                solver_py=SOLVER,
                validates_candidate=t0_candidate_sha256(_ctrl_d0))
_ctrl_res = promotion.advance(_ctrl_root, "PQ", "fam05", "A", FREEZE,
                              evidence_grade="harness-validation")
check("D8.1 CONTROL unknown atom [local,v1,sha256,manifest] promotes "
      "(D6 kept)",
      _ctrl_res["event"] == "PROMOTION", str(_ctrl_res)[:120])
_ctrl_st = order.cell_state(_ctrl_root, _ctrl_prom, FREEZE)
check("D8.1 CONTROL unknown-atom PROMOTION cell is ADMISSIBLE "
      "(COMPLETE) through order.cell_state",
      _ctrl_st["status"] == "COMPLETE", str(_ctrl_st["reasons"][:1])[:200])

# --- D8.1 SAME-FINDING (extra-key + missing-key, asserted explicitly) -----
for _tag, _decl, _needle in (MALFORMED[0], MALFORMED[1]):
    _shared = CS.validate(_decl)[0]
    _root, _prom = hand_plant("same-" + _tag, _decl)
    _st = order.cell_state(_root, _prom, FREEZE)
    _msg = promote_refusal("same-" + _tag, _decl)
    check(f"D8.1 SAME-FINDING {_tag}: order finding == promotion "
          f"message (shared {len(_shared)}-char text)",
          _msg is not None and _shared in _msg
          and any(_shared in r for r in _st["reasons"]),
          (_msg or "")[:160])

# --- D8.1 STATIC: exactly ONE implementation ------------------------------
_order_src = open(os.path.join(HARNESS, "order.py")).read()
_promo_src = open(os.path.join(HARNESS, "promotion.py")).read()
_shape_src = open(os.path.join(HARNESS, "contract_shape.py")).read()
check("D8.1 STATIC order.py and promotion.py both import the shared "
      "module",
      "contract_shape" in _order_src and "contract_shape" in _promo_src)
_harness_mods = {}
for _name in sorted(os.listdir(HARNESS)):
    if _name.endswith(".py") and _name != "contract_shape.py":
        _p = os.path.join(HARNESS, _name)
        if os.path.isfile(_p):
            _harness_mods[_name] = open(_p).read()
check("D8.1 STATIC neither authority defines its own shape "
      "predicate (no _ATOMIC_RE/_TOKEN_RE/re.compile in order.py "
      "or promotion.py)",
      not any(tag in _order_src or tag in _promo_src
              for tag in ("_ATOMIC_RE", "_TOKEN_RE", "re.compile")))
check("D8.1 STATIC neither authority retains its own shape wording "
      "(bare-string / malformed-precondition / duplicate-token "
      "findings live only in the shared module)",
      all(phrase in _shape_src for phrase in
          ("bare-string precondition", "malformed precondition",
           "duplicate requires_all token"))
      and not any(phrase in _order_src or phrase in _promo_src
                  for phrase in ("bare-string precondition",
                                 "malformed precondition",
                                 "duplicate requires_all token")))
_shape_tree = ast.parse(_shape_src)
_shape_imports = [n for n in ast.walk(_shape_tree)
                  if isinstance(n, (ast.Import, ast.ImportFrom))]
check("D8.1 STATIC the shared module imports only re (no vocabulary "
      "consultation)",
      len(_shape_imports) == 1
      and isinstance(_shape_imports[0], ast.Import)
      and [a.name for a in _shape_imports[0].names] == ["re"],
      str([ast.dump(n) for n in _shape_imports])[:160])
check("D8.1 STATIC the shared module performs no I/O and defines no "
      "globals (no open(), no global statement)",
      not any(isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "open"
              for n in ast.walk(_shape_tree))
      and not any(isinstance(n, ast.Global)
                  for n in ast.walk(_shape_tree)))

# --- D8.2 live chain: node removed, edge direct, V2 green -----------------
LIVE_LOCK = json.load(open(os.path.join(FAMC, "PROTOCOL-LOCK.json")))
_TOP = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=FAMC,
                      capture_output=True, text=True).stdout.strip()


def _git_bytes(rev_path):
    p = subprocess.run(["git", "show", rev_path], cwd=_TOP,
                       capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout


def _chain_inputs():
    by_file = {}
    for a in LIVE_LOCK["amendments"]:
        by_file.setdefault(a.get("file"), []).append(dict(a))
    frozen, disk = {}, {}
    for fn in PF.PROTOCOL_GOVERNED:
        raw = _git_bytes(f"{FREEZE}:benchmarks/fam-c/{fn}")
        frozen[fn] = (hashlib.sha256(raw).hexdigest()
                      if raw is not None else None)
        disk[fn] = _sha_file(os.path.join(FAMC, fn))
    return by_file, frozen, disk, dict(LIVE_LOCK["governed"])


_BY_FILE, _FROZEN, _DISK, _GOV = _chain_inputs()

check("D8.2 9caf3d4fdd33 is NO recorded node in the live lock",
      not any((a.get("from_sha") or "").startswith("9caf3d4fdd33")
              or (a.get("to_sha") or "").startswith("9caf3d4fdd33")
              for a in LIVE_LOCK["amendments"])
      and not any("9caf3d4fdd33" in (v or "")
                  for v in LIVE_LOCK["governed"].values()))
check("D8.2 HARNESS-READINESS a12 edge is 382a75fc -> 12dda202 "
      "direct",
      any((a.get("from_sha") or "").startswith("382a75fc356e")
          and (a.get("to_sha") or "").startswith("12dda20242b0")
          for a in _BY_FILE["HARNESS-READINESS.md"]))
check("D8.2 the 9caf3d4f explanation lives in the D8 amendment "
      "reason + PREREG stanza, not the chain",
      any("9caf3d4fdd33" in (a.get("reason") or "")
          and a.get("slice") == "a12d-slice-d8"
          for a in _BY_FILE["HARNESS-READINESS.md"])
      and "9caf3d4fdd33" in open(os.path.join(FAMC, "PREREG.md")).read()
      and "AMEND-2026-09-09-d8-shared-lineage"
      in open(os.path.join(FAMC, "PREREG.md")).read())
check("D8.2 no other amendment entry deleted (30 at D7 - 2 removed "
      "a12 edges + 1 D8 edge + 2 D8 forward + 2 D9 forward "
      "+ 2 D10 forward + 6 D11 forward = 41)",
      len(LIVE_LOCK["amendments"]) == 41,
      str(len(LIVE_LOCK["amendments"])))
check("D8.2 D8 recorded as its own forward amendment "
      "AMEND-2026-09-09-d8-shared-lineage (PREREG + preflight edges)",
      sum(1 for a in LIVE_LOCK["amendments"]
          if "AMEND-2026-09-09-d8-shared-lineage" in (a.get("reason") or ""))
      == 2)
_v2_live = [f for f in PF.validate_protocol(FAMC, FREEZE)
            if f.startswith("V2")]
check("D8.2 corrected lock on the real repo: V2 green",
      _v2_live == [], str(_v2_live[:2])[:240])
_tips, _tip_find = PF.protocol_tips(FAMC, FREEZE)
check("D8.2 validator tips computed for every governed file",
      _tip_find == []
      and sorted(_tips) == sorted(PF.PROTOCOL_GOVERNED),
      f"tips={sorted(_tips)} finds={str(_tip_find[:1])[:160]}")
_tip_bad = [fn for fn in PF.PROTOCOL_GOVERNED if _tips.get(fn) != _DISK[fn]]
check("D8.2 every governed file: disk sha256 == the validator's "
      "unique tip",
      _tip_bad == [], str(_tip_bad))

# --- D8.2 V2 hygiene, hermetic mutations on live bytes --------------------
_HGOV = dict(_GOV)


def _v2pure(fn, amendments, governed=None):
    f, _t = PF.validate_file_chain(fn, _FROZEN[fn], amendments,
                                   _DISK[fn],
                                   governed if governed is not None
                                   else _HGOV[fn])
    return f


_mut_extra = dict(_HGOV)
_mut_extra["TYPO.md"] = "00" * 32
_f_extra = PF.validate_lock_global({"governed": _mut_extra,
                                    "amendments": LIVE_LOCK["amendments"]})
check("D8.2-V2(1) extra governed key TYPO.md FAILs naming the key",
      any("TYPO.md" in f for f in _f_extra), str(_f_extra[:1])[:200])
check("D8.2-V2(1) unmutated lock is globally clean",
      PF.validate_lock_global(LIVE_LOCK) == [],
      str(PF.validate_lock_global(LIVE_LOCK)[:1])[:200])
for _bad_file in ("TYPO.md", None):
    _mut_file = [dict(a) for a in LIVE_LOCK["amendments"][:1]]
    _mut_file[0]["file"] = _bad_file
    _f_file = PF.validate_lock_global({"governed": _HGOV,
                                       "amendments": _mut_file})
    check(f"D8.2-V2(2) amendment file {_bad_file!r} FAILs naming it",
          any("ungoverned" in f for f in _f_file), str(_f_file[:1])[:200])
_mut_nofile = [dict(a) for a in LIVE_LOCK["amendments"][:1]]
del _mut_nofile[0]["file"]
_f_nofile = PF.validate_lock_global({"governed": _HGOV,
                                     "amendments": _mut_nofile})
check("D8.2-V2(2) amendment with missing file FAILs",
      any("ungoverned" in f for f in _f_nofile), str(_f_nofile[:1])[:200])
_mut_hex = [dict(a) for a in _BY_FILE["ORDER.md"]]
_mut_hex[0]["from_sha"] = "zz" * 32
_f_hex = _v2pure("ORDER.md", _mut_hex)
check("D8.2-V2(3) non-hex from_sha FAILs naming ORDER.md",
      any("ORDER.md" in f and "from_sha" in f for f in _f_hex),
      str(_f_hex[:1])[:200])
_mut_hex2 = [dict(a) for a in _BY_FILE["ORDER.md"]]
_mut_hex2[0]["to_sha"] = "abc123"
_f_hex2 = _v2pure("ORDER.md", _mut_hex2)
check("D8.2-V2(3) short to_sha FAILs naming ORDER.md",
      any("ORDER.md" in f and "to_sha" in f for f in _f_hex2),
      str(_f_hex2[:1])[:200])
# post-freeze anchor, hermetic constants: genesis G chained to X, disk X.
_G, _X = "11" * 32, "22" * 32
_anchor_am = [{"file": "T4-CONFORMANCE.json", "from_sha": None,
               "to_sha": _G, "added_after_freeze": True},
              {"file": "T4-CONFORMANCE.json", "from_sha": _G, "to_sha": _X}]
_f_anchor_ok, _tip_ok = PF.validate_file_chain(
    "T4-CONFORMANCE.json", None, _anchor_am, _X, _G)
check("D8.2-V2(4) post-freeze governed == genesis node stays green",
      _f_anchor_ok == [] and _tip_ok == _X, str(_f_anchor_ok[:1])[:160])
_f_anchor_bad, _ = PF.validate_file_chain(
    "T4-CONFORMANCE.json", None, _anchor_am, _X, _X)
check("D8.2-V2(4) post-freeze governed moved to the tip FAILs "
      "naming the genesis rule",
      any("T4-CONFORMANCE.json" in f and "genesis" in f
          for f in _f_anchor_bad), str(_f_anchor_bad[:1])[:200])
# validate_file_chain stays pure and I/O-free.
_vfc_src = ast.parse(open(os.path.join(
    FAMC, "preflight.py")).read())
_vfc_fn = next(n for n in ast.walk(_vfc_src)
               if isinstance(n, ast.FunctionDef)
               and n.name == "validate_file_chain")
check("D8.2-V2(5) validate_file_chain is pure and I/O-free (no "
      "open(), no subprocess, no git calls)",
      not any(isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "open"
              for n in ast.walk(_vfc_fn))
      and "subprocess" not in ast.dump(_vfc_fn)
      and "git." not in ast.dump(_vfc_fn))

# --- D8.2 V2 hygiene, end-to-end through validate_protocol ---------------
_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def _git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       env=_ENV, text=True)
    assert r.returncode == 0, (args, r.stderr[:200])
    return r.stdout.strip()


def _v2_repo(tag, freeze_files, post_files=None, lock_mut=None):
    """Throwaway git repo with a benchmarks/fam-c layout. freeze_files
    are committed as the freeze FC; post_files are committed after
    (retrievable but post-freeze); the lock governs the committed
    bytes with no amendments unless lock_mut rewrites it. lock_mut
    receives (lock, disk_shas, fc, frozen_shas). Returns (famc, FC)."""
    base = tempfile.mkdtemp(prefix="h29-" + tag + "-")
    repo = os.path.join(base, "repo")
    famc = os.path.join(repo, "benchmarks", "fam-c")
    os.makedirs(famc)
    frozen = {}
    for name, data in freeze_files.items():
        raw = data if isinstance(data, bytes) else data.encode()
        with open(os.path.join(famc, name), "wb") as f:
            f.write(raw)
        frozen[name] = hashlib.sha256(raw).hexdigest()
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "freeze")
    fc = _git(repo, "rev-parse", "HEAD")
    for name, data in (post_files or {}).items():
        with open(os.path.join(famc, name), "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode())
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "post " + name)
    governed, shas = {}, {}
    for name in PF.PROTOCOL_GOVERNED:
        p = os.path.join(famc, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                shas[name] = hashlib.sha256(f.read()).hexdigest()
            governed[name] = shas[name]
    for name in ("ORDER-EXPANSION.json",):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(famc, name))
    lock = {"freeze_commit": fc, "governed": governed, "amendments": []}
    if lock_mut is not None:
        lock = lock_mut(lock, shas, fc, frozen)
    with open(os.path.join(famc, "PROTOCOL-LOCK.json"), "w") as f:
        json.dump(lock, f)
    return famc, fc


def _live_bytes():
    return {fn: open(os.path.join(FAMC, fn), "rb").read()
            for fn in PF.PROTOCOL_GOVERNED}


_famc0, _fc0 = _v2_repo("v2base", _live_bytes())
check("D8.2-E2E fixture baseline is V2 green through the real path",
      PF.validate_protocol(_famc0, _fc0) == [],
      str(PF.validate_protocol(_famc0, _fc0)[:2])[:240])


def _with_extra_governed(lock, shas, fc, frozen):
    lock["governed"]["TYPO.md"] = "00" * 32
    return lock


_famc1, _fc1 = _v2_repo("v2extra", _live_bytes(),
                        lock_mut=_with_extra_governed)
check("D8.2-E2E(1) extra governed TYPO.md FAILs through "
      "validate_protocol",
      any("TYPO.md" in f for f in PF.validate_protocol(_famc1, _fc1)),
      str(PF.validate_protocol(_famc1, _fc1)[:1])[:200])


def _with_bad_file(lock, shas, fc, frozen):
    # Both node shas are committed (retrievable) and chained from the
    # frozen root, so the finding that matters — the ungoverned
    # amendment file — is isolated from any node-shape noise.
    lock["amendments"] = [{"file": "TYPO.md",
                           "from_sha": frozen["ORDER.md"],
                           "to_sha": shas["ORDER.md"]}]
    return lock


_famc2, _fc2 = _v2_repo("v2badfile", _live_bytes(),
                        post_files={"ORDER.md": _live_bytes()["ORDER.md"] +
                                    b"\n# fixture\n"},
                        lock_mut=_with_bad_file)
check("D8.2-E2E(2) amendment file TYPO.md FAILs through "
      "validate_protocol",
      any("TYPO.md" in f for f in PF.validate_protocol(_famc2, _fc2)),
      str(PF.validate_protocol(_famc2, _fc2)[:1])[:200])


def _with_bad_hex(lock, shas, fc, frozen):
    lock["amendments"] = [{"file": "ORDER.md",
                           "from_sha": shas["ORDER.md"],
                           "to_sha": "zz" * 32}]
    return lock


_famc3, _fc3 = _v2_repo("v2badhex", _live_bytes(),
                        lock_mut=_with_bad_hex)
check("D8.2-E2E(3) non-hex to_sha FAILs through validate_protocol "
      "naming ORDER.md",
      any("ORDER.md" in f and "to_sha" in f
          for f in PF.validate_protocol(_famc3, _fc3)),
      str(PF.validate_protocol(_famc3, _fc3)[:1])[:200])


def _post_genesis(lock, shas, fc, anchor=None):
    # T4-CONFORMANCE.json was NOT in the freeze: govern it by genesis.
    lock["governed"]["T4-CONFORMANCE.json"] = anchor
    lock["amendments"] = [{"file": "T4-CONFORMANCE.json",
                           "from_sha": None, "to_sha": anchor,
                           "added_after_freeze": True}]
    return lock


_t4_live = open(os.path.join(FAMC, "T4-CONFORMANCE.json"), "rb").read()
_nofreeze = {fn: data for fn, data in _live_bytes().items()
             if fn != "T4-CONFORMANCE.json"}
_famc4, _fc4 = _v2_repo("v2anchok", _nofreeze,
                        post_files={"T4-CONFORMANCE.json": _t4_live},
                        lock_mut=lambda l, s, f, z: _post_genesis(
                            l, s, f, anchor=s["T4-CONFORMANCE.json"]))
check("D8.2-E2E(4) post-freeze genesis anchor is V2 green",
      [f for f in PF.validate_protocol(_famc4, _fc4)
       if "T4-CONFORMANCE.json" in f] == [],
      str([f for f in PF.validate_protocol(_famc4, _fc4)
           if "T4-CONFORMANCE" in f][:1])[:200])
# rebuild: the tip bytes are the DISK bytes and both nodes are
# committed, so the anchor move is refused on the genesis rule
# (chain + retrievability stay green around it).
_t4_v2 = _t4_live + b"\n# fixture descendant\n"
_famc5b, _fc5b = _v2_repo(
    "v2anchbad", _nofreeze,
    post_files={"T4-CONFORMANCE.json": _t4_v2},
    lock_mut=lambda l, s, f, z: _post_genesis(
        l, s, f, anchor=s["T4-CONFORMANCE.json"]))
# now rewrite the lock moving governed to the *tip* while genesis stays
_lock5 = json.load(open(os.path.join(_famc5b, "PROTOCOL-LOCK.json")))
# commit a second descendant so genesis != tip on disk history
with open(os.path.join(_famc5b, "T4-CONFORMANCE.json"), "wb") as f:
    f.write(_t4_v2 + b"# second\n")
_repo5 = os.path.dirname(os.path.dirname(_famc5b))
_git(_repo5, "add", "-A")
_git(_repo5, "commit", "-qm", "descendant")
_tip5 = _sha_file(os.path.join(_famc5b, "T4-CONFORMANCE.json"))
_gen5 = _lock5["governed"]["T4-CONFORMANCE.json"]
_lock5["governed"]["T4-CONFORMANCE.json"] = _tip5
_lock5["amendments"].append({"file": "T4-CONFORMANCE.json",
                             "from_sha": _gen5, "to_sha": _tip5})
json.dump(_lock5, open(os.path.join(_famc5b, "PROTOCOL-LOCK.json"), "w"))
_f5 = [f for f in PF.validate_protocol(_famc5b, _fc5b)
       if "T4-CONFORMANCE.json" in f]
check("D8.2-E2E(4) post-freeze governed moved to the tip FAILs "
      "naming the genesis rule",
      any("genesis" in f for f in _f5), str(_f5[:1])[:240])


def _with_ghost(lock, shas, fc, frozen):
    lock["amendments"] = [{"file": "ORDER.md",
                           "from_sha": shas["ORDER.md"],
                           "to_sha": "ff" * 32}]
    return lock


_famc6, _fc6 = _v2_repo("v2ghost", _live_bytes(),
                        lock_mut=_with_ghost)
_f6 = PF.validate_protocol(_famc6, _fc6)
check("D8.2-E2E(5) unretrievable node FAILs naming retrievable "
      "bytes",
      any("ORDER.md" in f and "no retrievable bytes" in f for f in _f6),
      str(_f6[:1])[:240])

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH29 D8 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

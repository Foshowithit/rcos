#!/usr/bin/env python3
"""H28 — A12d slice D7 acceptance: exact three-key producer contract (P0)
plus unique linear protocol lineage (P1).

D7.1 closes the undocumented `payload["contract"]` alias and the silent
extra-key drop: `execution_payload.capability_contract` must carry
EXACTLY {semantic_core, preconditions, limitations} — missing/extra key
is PROMOTION-DENY naming the key, every existing structural refusal is
kept, and unknown atomic tokens still promote verbatim (D6 kept).

D7.2 closes the reachable-set lineage: the recorded amendments per
governed file must form ONE path from the frozen (or post-freeze
genesis) node to exactly one tip, and the on-disk bytes must equal
that tip (validate_file_chain). Three mis-recorded from_sha edges were
corrected from git content sha256 with no entry deleted (PREREG D5/D6,
HARNESS-READINESS a11); 9caf3d4fdd33 was kept in D7 as an in-commit
internal chain node and is REMOVED in D8 (auditor D7-post P1: the a12
edge is now 382a75fc -> 12dda202 direct).

Driven through the REAL paths: fixture T0/T1 builds -> promotion
controller -> CAPABILITY_LOCK for D7.1; the real V2 chain validator
(validate_protocol on the live repo + validate_file_chain on hermetic
copies of the real lock bytes) for D7.2.

Stdlib only. Hermetic fixtures in throwaway dirs (live-tree reads are
read-only). Prints `H28 D7 smoke: N/N closed`; exits non-zero on any
failure.
"""
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
import preflight as PF  # noqa: E402

from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = "import sys; sys.exit(0)\n"
CORE = "generic capability"
FAM05_ID = "fam05.local_v1_sha256"
VOCAB = ["acyclic", "acyclicity", "aggregate", "basis", "common", "dedup",
         "disjoint", "duplicates", "identical", "input", "local", "order",
         "pages", "record", "repeats", "row", "same", "sha256", "summary",
         "topological", "unit", "units", "v1"]


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def hermetic(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h28-" + tag + "-")
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


def _build_pair(root, contract, mutate_arrival=None, universe="A"):
    """Build the T0/T1 fixture pair; optionally rewrite the T0 arrival
    (e.g. rename capability_contract -> contract) before promotion."""
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", universe)
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", universe)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=contract)
    if mutate_arrival is not None:
        ap = os.path.join(d0, "arrival.json")
        arr = json.load(open(ap))
        mutate_arrival(arr)
        json.dump(arr, open(ap, "w"), indent=1)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    return root


def refuse_reason(tag, contract, mutate_arrival=None):
    """Build T0/T1 then promote; return the refusal string (or None when
    promotion unexpectedly succeeds)."""
    root = hermetic(tag)
    _build_pair(root, contract, mutate_arrival)
    try:
        promotion.promote_universe(root, "PQ", "fam05", "A", FREEZE,
                                   "harness-validation")
    except (PermissionError, ValueError) as e:
        return str(e)
    return None


def mint(tag, contract):
    """Full production path for one contract. Returns (root, lock)."""
    root = hermetic(tag)
    _build_pair(root, contract)
    res = promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                            evidence_grade="harness-validation")
    assert res["event"] == "PROMOTION", res
    res2 = promotion.advance(root, "PQ", "fam05", "A", FREEZE,
                             evidence_grade="harness-validation")
    assert res2["event"] == "CAPABILITY_LOCK", res2
    capdir = order.capability_dir(root, "PQ", "A", "fam05")
    lock = json.load(open(os.path.join(capdir, "CAPABILITY_LOCK.json")))
    return root, lock


def _vocab_clean(msg):
    return [t for t in VOCAB if t in msg]


# --- D7.1 item 1: the contract alias is gone ---------------------------
def _to_alias(arr):
    pay = arr["execution_payload"]
    pay["contract"] = pay.pop("capability_contract")


_r1 = refuse_reason("d71-alias",
                   v5_contract([["local", "v1", "sha256"]]),
                   mutate_arrival=_to_alias)
check("D7.1-1 arrival with only payload[contract] is PROMOTION-DENY "
      "(alias gone)",
      _r1 is not None and "PROMOTION-DENY" in _r1, str(_r1)[:160])

# --- D7.1 item 2: extra key refused, naming it --------------------------
_extra = v5_contract([["local", "v1", "sha256"]])
_extra["also_supports"] = ["remote", "blake3"]
_r2 = refuse_reason("d71-extra", _extra)
check("D7.1-2 capability_contract with also_supports is PROMOTION-DENY "
      "naming also_supports",
      _r2 is not None and "PROMOTION-DENY" in _r2
      and "also_supports" in _r2, str(_r2)[:200])
check("D7.1-2 the extra-key denial is self-contained (names no "
      "vocabulary value)",
      _r2 is not None and _vocab_clean(_r2) == [], str(_vocab_clean(_r2 or "")))

# --- D7.1 item 3: missing key refused, naming it ------------------------
_missing = {"semantic_core": CORE,
            "preconditions": [{"requires_all": ["local", "v1", "sha256"]}]}
_r3 = refuse_reason("d71-missing", _missing)
check("D7.1-3 capability_contract missing limitations is PROMOTION-DENY "
      "naming limitations",
      _r3 is not None and "PROMOTION-DENY" in _r3
      and "limitations" in _r3, str(_r3)[:200])
check("D7.1-3 the missing-key denial is self-contained (names no "
      "vocabulary value)",
      _r3 is not None and _vocab_clean(_r3) == [], str(_vocab_clean(_r3 or "")))

# --- D7.1 item 4: exact shape promotes, verbatim ------------------------
_root4, _lock4 = mint("d71-exact",
                      v5_contract([["local", "v1", "sha256"]], ["lane P"]))
check("D7.1-4 exact three-key shape promotes with preconditions "
      "verbatim in the lock",
      _lock4.get("preconditions") == [{"requires_all": ["local", "v1",
                                                        "sha256"]}]
      and _lock4.get("limitations") == ["lane P"]
      and _lock4.get("semantic_core") == CORE,
      f"pre={_lock4.get('preconditions')}")
check("D7.1-4 the promoted lock records exactly the three contract "
      "keys (nothing dropped, nothing added)",
      _lock4.get("semantic_core") == CORE
      and _lock4.get("preconditions") == [{"requires_all": ["local", "v1",
                                                            "sha256"]}]
      and _lock4.get("limitations") == ["lane P"]
      and "also_supports" not in json.dumps(_lock4),
      f"keys={[k for k in ('semantic_core', 'preconditions', 'limitations') if k in _lock4]}")

# --- D7.1 item 5: auditor attack still promotes, non-bearing -----------
_root5, _lock5 = mint("d71-attack",
                      v5_contract([["local", "v1", "sha256", "manifest"]]))
check("D7.1-5 attack [local,v1,sha256,manifest] still promotes "
      "(unknown atom, D6 kept)",
      _lock5.get("preconditions") == [{"requires_all": ["local", "v1",
                                                        "sha256",
                                                        "manifest"]}])
check("D7.1-5 attack lock is non_discriminating with ids []",
      _lock5.get("non_discriminating") is True
      and _lock5.get("supported_t4_ids") == [],
      f"nd={_lock5.get('non_discriminating')} "
      f"sup={_lock5.get('supported_t4_ids')}")

# --- D7.1 item 6: positive control --------------------------------------
_root6, _lock6 = mint("d71-control",
                      v5_contract([["local", "v1", "sha256"]]))
check("D7.1-6 control [local,v1,sha256] is exactly "
      "fam05.local_v1_sha256",
      _lock6.get("non_discriminating") is False
      and _lock6.get("supported_t4_ids") == [FAM05_ID],
      f"sup={_lock6.get('supported_t4_ids')}")

# --- D7.1: every existing structural refusal kept -----------------------
for _label, _pre, _needle in (
        ("bare-string precondition", ["local v1 sha256"], "precondition"),
        ("old requires key", [{"requires": "local v1 sha256"}], "requires"),
        ("empty requires_all", [{"requires_all": []}], "requires_all"),
        ("non-atomic token", [{"requires_all": ["local local"]}],
         "local local"),
        ("uppercase token", [{"requires_all": ["Local"]}], "Local"),
        ("duplicate token", [{"requires_all": ["local", "local"]}],
         "local")):
    _r = refuse_reason("d71-" + _label.split()[0],
                       {"semantic_core": CORE, "preconditions": _pre,
                        "limitations": []})
    check(f"D7.1 structural refusal kept ({_label})",
          _r is not None and "PROMOTION-DENY" in _r and _needle in _r,
          str(_r)[:140])

# --- D7.2: hermetic inputs mirroring the real V2 chain path -------------
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
    """(by_file, frozen, disk, governed) for the live tree — the exact
    inputs protocol_tips feeds validate_file_chain, re-derived here so
    mutations run on hermetic copies of the real bytes."""
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


def _v2(fn, amendments):
    f, _t = PF.validate_file_chain(fn, _FROZEN[fn], amendments,
                                   _DISK[fn], _GOV[fn])
    return f


# --- D7.2 item 1: corrected lock, real repo — V2 green -------------------
_v2_live = [f for f in PF.validate_protocol(FAMC, FREEZE)
            if f.startswith("V2")]
check("D7.2-1 corrected lock on the real repo: V2 green",
      _v2_live == [], str(_v2_live[:2])[:200])
_tips, _tip_find = PF.protocol_tips(FAMC, FREEZE)
check("D7.2-1 validator tips computed for every governed file",
      _tip_find == []
      and sorted(_tips) == sorted(PF.PROTOCOL_GOVERNED),
      f"tips={sorted(_tips)} finds={str(_tip_find[:1])[:120]}")

# --- D7.2: the three corrected edges state old->new ----------------------
def _edge(by, fn, to_prefix):
    hits = [a for a in by.get(fn, [])
            if (a.get("to_sha") or "").startswith(to_prefix)]
    return hits[0] if len(hits) == 1 else None


_e_d5 = _edge(_BY_FILE, "PREREG.md", "d5277d752c20")
_e_d6 = _edge(_BY_FILE, "PREREG.md", "1fb9089161ce")
_e_a11 = _edge(_BY_FILE, "HARNESS-READINESS.md", "a0419cedc9a4")
check("D7.2 PREREG D5 edge corrected b732647f61f3 -> 7330a2f6b21a",
      _e_d5 is not None
      and (_e_d5.get("from_sha") or "").startswith("7330a2f6b21a"),
      str(_e_d5))
check("D7.2 PREREG D6 edge corrected b732647f61f3 -> d5277d752c20",
      _e_d6 is not None
      and (_e_d6.get("from_sha") or "").startswith("d5277d752c20"),
      str(_e_d6))
check("D7.2 HARNESS-READINESS a11 edge corrected 8e743e4c63f4 -> "
      "3314fa9170ab",
      _e_a11 is not None
      and (_e_a11.get("from_sha") or "").startswith("3314fa9170ab"),
      str(_e_a11))
check("D7.2 no amendment entry deleted except the D8 hygiene pair, "
      "the D9 chronology pair, the D10 stability pair, and the D11 "
      "authority pairs "
      "(30 at D7 - 2 removed a12 edges + 1 D8 edge + 2 D8 forward "
      "+ 2 D9 forward + 2 D10 forward + 10 D11 forward + 1 D12 forward + 1 D12b forward + 1 D12c forward + 1 D12d forward = 49)",
      len(LIVE_LOCK["amendments"]) == 49, str(len(LIVE_LOCK["amendments"])))
check("D7.2 repair recorded as its own forward amendment "
      "AMEND-2026-09-09-d7-lineage-repair (PREREG + preflight edges)",
      sum(1 for a in LIVE_LOCK["amendments"]
          if "AMEND-2026-09-09-d7-lineage-repair" in (a.get("reason") or ""))
      == 2)
check("D8 9caf3d4fdd33 is NO recorded node (removed from the "
      "authoritative chain)",
      not any((a.get("from_sha") or "").startswith("9caf3d4fdd33")
              or (a.get("to_sha") or "").startswith("9caf3d4fdd33")
              for a in LIVE_LOCK["amendments"])
      and not any("9caf3d4fdd33" in (v or "")
                  for v in LIVE_LOCK["governed"].values()),
      str([(a.get("from_sha") or "")[:12]
           for a in LIVE_LOCK["amendments"]
           if "9caf" in json.dumps(a)])[:120])
check("D8 HARNESS-READINESS a12 edge is 382a75fc -> 12dda20242b0 "
      "direct (the states that exist in git)",
      any((a.get("from_sha") or "").startswith("382a75fc356e")
          and (a.get("to_sha") or "").startswith("12dda20242b0")
          for a in _BY_FILE["HARNESS-READINESS.md"]))
check("D8 the 9caf3d4f explanation lives in the D8 amendment reason "
      "(history preserved outside the chain)",
      any("9caf3d4fdd33" in (a.get("reason") or "")
          and a.get("slice") == "a12d-slice-d8"
          for a in _BY_FILE["HARNESS-READINESS.md"]))

# --- D7.2 item 2: D5->D6 PREREG edge deleted -> V2 FAILS ------------------
_mut2 = [a for a in _BY_FILE["PREREG.md"]
         if not ((a.get("from_sha") or "").startswith("d5277d752c20")
                 and (a.get("to_sha") or "").startswith("1fb9089161ce"))]
_f2 = _v2("PREREG.md", _mut2)
check("D7.2-2 D5->D6 PREREG edge deleted in a hermetic copy: V2 FAILS "
      "naming PREREG.md",
      any("PREREG.md" in f for f in _f2), str(_f2[:1])[:200])

# --- D7.2 item 3: D6 from_sha reverted to baseline -> V2 FAILS ------------
_mut3 = [dict(a) for a in _BY_FILE["PREREG.md"]]
for a in _mut3:
    if (a.get("to_sha") or "").startswith("1fb9089161ce"):
        a["from_sha"] = _GOV["PREREG.md"]
_f3 = _v2("PREREG.md", _mut3)
check("D7.2-3 D6 PREREG from_sha reverted to the baseline: V2 FAILS "
      "naming PREREG.md",
      any("PREREG.md" in f for f in _f3), str(_f3[:1])[:200])

# --- D7.2 item 4: ANY single edge deleted -> V2 FAILS ----------------------
_all_edges = [(fn, i) for fn in PF.PROTOCOL_GOVERNED
              for i in range(len(_BY_FILE.get(fn, [])))]
_bad4 = []
for _fn, _i in _all_edges:
    _m = {fn: [dict(a) for a in ams] for fn, ams in _BY_FILE.items()}
    del _m[_fn][_i]
    _f = _v2(_fn, _m[_fn])
    if not (_f and any(_fn in g for g in _f)):
        _bad4.append(f"{_fn}#{_i}")
check(f"D7.2-4 deleting any single amendment edge fails V2 "
      f"({len(_all_edges)} edges probed)",
      _bad4 == [], str(_bad4[:3]))

# --- D7.2 item 5: to_sha retargeted off-chain -> V2 FAILS ------------------
_mut5 = [dict(a) for a in _BY_FILE["PREREG.md"]]
for a in _mut5:
    if (a.get("to_sha") or "").startswith("1fb9089161ce"):
        a["to_sha"] = "00" * 32
_f5 = _v2("PREREG.md", _mut5)
check("D7.2-5 one to_sha changed to an off-chain value: V2 FAILS "
      "naming PREREG.md",
      any("PREREG.md" in f for f in _f5), str(_f5[:1])[:200])

# --- D7.2 item 6 (acceptance row 6): disk == validator tip, all files -----
_tip_bad = [fn for fn in PF.PROTOCOL_GOVERNED if _tips.get(fn) != _DISK[fn]]
check("D7.2-6 every governed file: disk sha256 == the validator's "
      "unique tip",
      _tip_bad == [], str(_tip_bad))

# --- D7.2: V2 enforces linearity, reachable-set is gone --------------------
_src = open(os.path.join(FAMC, "preflight.py")).read()
check("D7.2 V2 linear-chain rule enforced in validate_file_chain "
      "(used by validate_protocol)",
      "def validate_file_chain" in _src
      and "validate_file_chain" in _src.split(
          "def validate_protocol")[1]
      and "acceptable" not in _src,
      "rule location: benchmarks/fam-c/preflight.py::validate_file_chain")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH28 D7 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

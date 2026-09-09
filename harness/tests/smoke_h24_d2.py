#!/usr/bin/env python3
"""H24 — A12d slice D2 acceptance: auditor A12d.3 (the frozen v1
limitation->T4 bridge is polarity-blind) + A12d.4 (`preconditions: []`
must be legal consistently).

Producer contract schema v2 + conformance bridge v2 (rule
normalize-affirmative-requires-v2 over the governed
T4-CONFORMANCE.json v2 map), driven through the REAL production path
(fixture T0/T1 builds -> promotion controller -> order provenance
re-derivation -> CAPABILITY_LOCK), never a claim:

  C1  the four auditor-quoted negated strings, each as the ONLY
      precondition, yield EMPTY supported_t4_ids and
      non_discriminating True for ALL six families — reported
      INADMISSIBLE with a named reason, never silently ignored;
  C2  three affirmative requires claims each support EXACTLY their
      family's T4 and none of the other five;
  C3  a limitations-only text with preconditions [] yields EMPTY
      support (limitations never drive conformance) on an admissible
      lock;
  C4  preconditions [] + limitations [] promotes, locks the empty
      lists verbatim, stays non-discriminating, and names zero
      preconditions in the cause;
  C5  five malformed shapes (bare-string precondition; object with a
      second key; blank requires; missing preconditions; missing
      limitations) are each refused with a named PROMOTION-DENY;
  C6  polarity regression: adding a negated precondition for one
      family never flips an affirmative claim for another;
  C7  an old-map lock (conformance_map_sha256 = v1 map sha) is
      inadmissible at lock verify and at order, and the engine is
      unloadable from it (readiness FAILURE: nothing downstream may
      consume a stale-map lock under locked reuse).

Stdlib only. Hermetic fixtures in throwaway dirs (no live-tree
mutation except none at all — every case mints in its own root);
live-tree reads are read-only. Prints `H24 D2 smoke: N/N closed`;
exits non-zero on any failure.
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

from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")
FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))
# The superseded v1 map sha (PROTOCOL-LOCK.json genesis to_sha for
# T4-CONFORMANCE.json): a lock bound to these bytes is a v1-rule lock.
V1_MAP_SHA = "05a8e094e437f320ed7e9521b483dd98f1febf0f31851992125ccb2f95dbda40"
CORE = "generic capability"


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def hermetic(tag):
    root = tempfile.mkdtemp(prefix="h24-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
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


cmap = CONF.load(FAMC)

# --- C1: the four auditor-quoted negations are INADMISSIBLE -----------
NEGATIVES = [
    "not limited to local v1 sha256 manifests",
    "DAG export is unsupported",
    "does not require acyclic input",
    "common unit basis is not required",
]
for i, neg in enumerate(NEGATIVES):
    fam_ok = True
    for fam in FAMILIES:
        v = CONF.verdict(fam, [neg], cmap)
        fam_ok = fam_ok and v["supported_t4_ids"] == [] \
            and v["non_discriminating"] is True \
            and v["requires_inadmissible"] == 1
    _root, _rec, _lock = mint(f"C1n{i}", v2_contract([neg]))
    check(f"C1 negated requires #{i + 1} {neg[:44]!r} is INADMISSIBLE "
          f"(empty support, all families non-discriminating)",
          fam_ok and _lock.get("supported_t4_ids") == []
          and _lock.get("non_discriminating") is True
          and "inadmissible" in (_lock.get("conformance_cause") or ""),
          f"lock sup={_lock.get('supported_t4_ids')} "
          f"cause={str(_lock.get('conformance_cause'))[:120]!r}")

# --- C2: affirmative requires support exactly one T4 -------------------
POSITIVES = [
    ("only local v1 sha256 manifests", "fam05.local_v1_sha256"),
    ("the input must be acyclic", "fam04.promised_acyclic"),
    ("pages must be disjoint", "fam02.pages_disjoint"),
]
for pre, want in POSITIVES:
    want_fam = want.split(".")[0]
    # The mint always runs under fam05: a non-fam05 T4 leaves THIS
    # lock non-discriminating while no other family supports either.
    other_ok = all(CONF.verdict(f, [pre], cmap)["non_discriminating"]
                   is True for f in FAMILIES if f != want_fam)
    _root, _rec, _lock = mint("C2-" + want_fam, v2_contract([pre]))
    check(f"C2 affirmative {pre[:36]!r} supports exactly {want}",
          _lock.get("supported_t4_ids") == [want]
          and _lock.get("non_discriminating") is (want_fam != "fam05")
          and other_ok,
          f"sup={_lock.get('supported_t4_ids')} "
          f"nd={_lock.get('non_discriminating')}")

# --- C3: limitations never drive conformance ---------------------------
_root3, _rec3, _lock3 = mint(
    "C3", v2_contract([], ["local v1 sha256 manifests are required"]))
check("C3 limitations-only text with preconditions [] yields EMPTY "
      "support (limitations never evidence), lock admissible",
      _lock3.get("supported_t4_ids") == []
      and _lock3.get("non_discriminating") is True
      and _lock3.get("limitation_present") is True
      and LOCK_MOD.verify_lock(_lock3, fam_c_dir=_root3) == [],
      f"sup={_lock3.get('supported_t4_ids')} "
      f"reasons={LOCK_MOD.verify_lock(_lock3, fam_c_dir=_root3)[:1]}")

# --- C4: both lists empty is legal -------------------------------------
_root4, _rec4, _lock4 = mint("C4", v2_contract([], []))
check("C4 preconditions [] + limitations [] promotes, locks the empty "
      "lists verbatim, stays non-discriminating, names zero "
      "preconditions",
      _lock4.get("preconditions") == []
      and _lock4.get("limitations") == []
      and _rec4.get("preconditions") == []
      and _lock4.get("non_discriminating") is True
      and _lock4.get("supported_t4_ids") == []
      and "0 precondition(s)" in (_lock4.get("conformance_cause") or ""),
      f"cause={str(_lock4.get('conformance_cause'))[:140]!r}")

# --- C5: malformed shapes refused with named messages ------------------
BAD = [
    ({"semantic_core": CORE,
      "preconditions": ["local v1 sha256"],
      "limitations": []},
     "bare-string precondition", "v2 shape"),
    ({"semantic_core": CORE,
      "preconditions": [{"requires": "x", "extra": 1}],
      "limitations": []},
     "precondition with a second key", "exactly"),
    ({"semantic_core": CORE, "preconditions": [{"requires": "  "}],
      "limitations": []},
     "blank requires text", "requires"),
    ({"semantic_core": CORE, "limitations": []},
     "missing preconditions", "preconditions"),
    ({"semantic_core": CORE, "preconditions": []},
     "missing limitations", "limitations"),
]
for bad, label, needle in BAD:
    reason = refuse_reason("C5-" + label.split()[0], bad)
    check(f"C5 malformed contract refused with a named message "
          f"({label})",
          reason is not None and "PROMOTION-DENY" in reason
          and needle in reason,
          (reason or "PROMOTED (fail-open)")[:160])

# --- C6: polarity regression -------------------------------------------
_root6a, _rec6a, _lock6a = mint(
    "C6a", v2_contract(["the input must be acyclic",
                        "not for local v1 sha256 manifests"]))
check("C6 affirmative fam04 claim is not flipped by an added negated "
      "fam05 precondition",
      _lock6a.get("supported_t4_ids") == ["fam04.promised_acyclic"],
      f"sup={_lock6a.get('supported_t4_ids')}")
_root6b, _rec6b, _lock6b = mint(
    "C6b", v2_contract(["only local v1 sha256 manifests",
                        "never assume an acyclic input"]))
check("C6 affirmative fam05 claim is not flipped by an added negated "
      "fam04 precondition",
      _lock6b.get("supported_t4_ids") == ["fam05.local_v1_sha256"],
      f"sup={_lock6b.get('supported_t4_ids')}")

# --- C7: old-map lock is inadmissible ----------------------------------
_root7, _rec7, _lock7 = mint(
    "C7", v2_contract(["only local v1 sha256 manifests"]))
assert _lock7.get("non_discriminating") is False
stale = dict(_lock7)
stale["conformance_map_sha256"] = V1_MAP_SHA
reasons7 = LOCK_MOD.verify_lock(stale, fam_c_dir=_root7)
check("C7 lock bound to the v1 map sha is LOCK-INADMISSIBLE naming "
      "conformance_map_sha256",
      any("LOCK-INADMISSIBLE" in r and "conformance_map_sha256" in r
          for r in reasons7),
      "; ".join(reasons7)[:200])
# The same staleness at order + readiness: point the committed lock at
# the v1 bytes (this root serves no further check after this mutation).
_lp7 = os.path.join(order.capability_dir(_root7, "PQ", "A", "fam05"),
                    "CAPABILITY_LOCK.json")
json.dump(stale, open(_lp7, "w"), indent=1)
_exp7 = order.load_expansion(_root7)
_lockcell7 = order.expected_event(_exp7, "PQ", "fam05",
                                  "CAPABILITY_LOCK", "A")
_st7 = order.cell_state(_root7, _lockcell7, FREEZE)
check("C7 stale-map lock makes order INADMISSIBLE (readiness FAILURE: "
      "the capability never becomes consumable under promotion + "
      "locked reuse)",
      _st7["status"] == "INADMISSIBLE"
      and any("conformance_map_sha256" in r for r in _st7["reasons"]),
      f"status={_st7['status']} reasons={str(_st7['reasons'])[:200]}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH24 D2 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

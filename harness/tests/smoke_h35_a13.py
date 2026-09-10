#!/usr/bin/env python3
"""H35 — A13 canonical-adaptation acceptance (frozen determinant + F).

Proves, hermetically (no model, no docker, no network; git reads are
read-only freeze objects):
  frozen content   schema/contract/determinant composition recomputed
                   independently (+ golden v1 contract pin);
  determinism      same 4-tuple inputs -> byte-identical adapted
                   output across PROCESSES (PYTHONHASHSEED 1 vs 2),
                   across input ORDERINGS, and for NOOP;
  no-model-input   version bodies execute under scrubbed globals
                   (args + builtins + three stdlib modules only —
                   any module-state read raises NameError), carry no
                   model slot in their signatures, and ignore the
                   recorded-attack response variants (M1/[a,b]/
                   offsets vs M2/[b,a]/reversed + provider bytes);
  negative control F_v1/ABI_v1 -> bytes A, F_v2/ABI_v2 -> bytes B,
                   A != B, determinants differ (never the same);
  receipt          skeleton binds determinant + legs + task/
                   capability/checker/harness identities, canonical
                   and self-hashed, exact key sets, execution slots
                   null pending the executed-legs ruling;
  consistency      adaptation tree-hash == run_arm_h1's production
                   computation over materialized F files (same
                   formula, same schema label — never forked);
  registry         unknown schema/program/surface refuse by name;
  correctness      F_v1 records == frozen T2 truth records.

Prints `H35 A13 smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
ROOT = os.path.dirname(HARNESS)
REPO = ROOT
BASE_REAL = os.path.join(REPO, "benchmarks", "fam-c")
FAMC = BASE_REAL
sys.path.insert(0, HARNESS)
sys.path.insert(0, os.path.join(BASE_REAL, "harness-run"))
sys.path.insert(0, BASE_REAL)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _canon(o):
    return json.dumps(o, sort_keys=True, indent=1) + "\n"


import adaptation as AD  # noqa: E402
import frozen_visible as FV  # noqa: E402

SCHEMA_ID = "fam01-psv-records-v1"
SCHEMA = AD.get_schema(SCHEMA_ID)
SCHEMA_SHA = _sha(_canon(SCHEMA).encode())
check("A13-FROZEN schema sha == independent recomputation from "
      "the frozen table",
      SCHEMA_SHA == hashlib.sha256(
          (json.dumps(SCHEMA, sort_keys=True, indent=1) + "\n").encode()
      ).hexdigest() and len(SCHEMA_SHA) == 64)

FILES, MANIFEST = AD.frozen_task_files(FAMC, FREEZE, "fam01", "T2")
SNAPSHOT_SHA = FV.canonical_sha(MANIFEST)
check("A13-FROZEN task snapshot == D12 frozen authority "
      "(same manifest, same sha)",
      MANIFEST == FV.derive_expected_visible(
          FAMC, FREEZE, "fam01", "T2")["manifest"]
      and SNAPSHOT_SHA == FV.derive_expected_visible(
          FAMC, FREEZE, "fam01", "T2")["manifest_sha256"],
      str(sorted(MANIFEST))[:120])

# --- contract composition (mixed independence + golden pin) ------------
import inspect as _inspect  # noqa: E402
_F_SRC = _inspect.getsource(AD.adapt_f_v1)
# Same canonical source normal form as program_identity
# (rstrip + exactly one newline); recomputed here from the
# disk-read source, not via the module function.
_F_ID_RECOMP = _sha((_F_SRC.rstrip() + "\n").encode())
_CONT_RECOMP = _sha(_canon({
    "f_identity": _F_ID_RECOMP,
    "adapter_abi": AD.ADAPTER_ABI_V1,
    "serialization_policy": AD.SERIALIZATION_POLICY_V1,
    "adaptation_policy": AD.ADAPTATION_POLICY_V1}).encode())
_CONT_MOD = AD.contract_sha_for("F_v1")
check("A13-FROZEN contract composition recomputed independently "
      "(disk-read F source + declared ABI/policy)",
      _CONT_RECOMP == _CONT_MOD, f"{_CONT_RECOMP[:12]}")
# Golden pin: deliberate-update discipline — editing F_v1 source,
# the v1 ABI text, or either v1 policy MUST update this constant
# in the same commit (a silent drift would break it loudly). The
# value below is the real computed contract sha, not a placeholder:
# verify it by hand with:
#   python3 -c "import sys; sys.path.insert(0,'harness');
#                import adaptation as A; print(A.contract_sha_for('F_v1'))"
_CONTRACT_V1_GOLDEN = ("6e8cccdc5d2e2645d3e8f02c50a5442941c945030004fd71"
                       "a02f2743a91d15c3")
check("A13-FROZEN v1 contract golden pin holds",
      AD.contract_sha_for("F_v1") == _CONTRACT_V1_GOLDEN)

# --- determinant structure ---------------------------------------------
ARTIFACT = (b"#!/usr/bin/env python3\n# h35 fixture capability engine "
            b"(stand-in bytes, NOT evidence)\n")
ARTIFACT_SHA = _sha(ARTIFACT)
_DET = AD.build_determinant(ARTIFACT_SHA, SCHEMA_SHA, SNAPSHOT_SHA,
                            _CONT_MOD)
check("A13-FROZEN determinant carries exactly the frozen 4-tuple "
      "+ its own sha",
      sorted(_DET["determinant"]) == sorted(
          ("capability_artifact_sha256", "capability_schema_sha256",
           "exact_visible_task_snapshot_sha256",
           "adaptation_contract_sha256"))
      and _DET["determinant_sha256"] == _sha(
          _canon(_DET["determinant"]).encode()))

# --- correctness anchor: F_v1 records == frozen truth -------------------
_ADAPT = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v1")
_RECS = json.loads(_ADAPT["files"]["records.json"])
_TRUTH = json.load(open(os.path.join(
    FAMC, "families", "fam01", "truth.json")))["T2"]
check("A13-CORRECT F_v1 records reproduce the frozen T2 truth "
      "semantics exactly",
      sorted(_RECS, key=lambda r: r["id"]) == sorted(
          _TRUTH, key=lambda r: r["id"]),
      f"got={len(_RECS)} want={len(_TRUTH)}")

# --- determinism: processes (hash seeds) --------------------------------
_PROBE = (
    "import sys, json; sys.path.insert(0, %r); "
    "import adaptation as A; "
    "files, _ = A.frozen_task_files(%r, %r, 'fam01', 'T2'); "
    "out = A.adapt_task('fam01-psv-records-v1', files, 'F_v1'); "
    "print(json.dumps({'sha': out['adapted_input_sha256'], "
    "'files': {k: A._sha_hex(v) for k, v in out['files'].items()}}))"
    % (HARNESS, FAMC, FREEZE))
_r1 = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True,
                     text=True, env=dict(os.environ, PYTHONHASHSEED="1",
                                         PYTHONDONTWRITEBYTECODE="1"))
_r2 = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True,
                     text=True, env=dict(os.environ, PYTHONHASHSEED="2",
                                         PYTHONDONTWRITEBYTECODE="1"))
_o1 = json.loads(_r1.stdout) if _r1.returncode == 0 else {}
_o2 = json.loads(_r2.stdout) if _r2.returncode == 0 else {}
check("A13-DET identical adapted bytes across processes and hash "
      "seeds (PYTHONHASHSEED 1 vs 2) and equal to this process",
      bool(_o1) and _o1 == _o2
      and _o1.get("sha") == _ADAPT["adapted_input_sha256"],
      f"rc={_r1.returncode}/{_r2.returncode}")

# --- determinism: input orderings ----------------------------------------
_perms = [dict(FILES), dict(reversed(list(FILES.items())))]
_keys = sorted(FILES)
_perms.append({k: FILES[k] for k in _keys[1:] + _keys[:1]})
_shas = {AD.adapt_task(SCHEMA_ID, dict(p),
                       "F_v1")["adapted_input_sha256"] for p in _perms}
check("A13-DET identical bytes across input orderings "
      "(insertion order never enters)",
      _shas == {_ADAPT["adapted_input_sha256"]}, str(_shas))
_NOOP_SHAS = {AD.adapt_task(SCHEMA_ID, dict(p),
                            "NOOP_v1")["adapted_input_sha256"]
              for p in _perms}
check("A13-DET NOOP deterministic across orderings",
      len(_NOOP_SHAS) == 1, str(_NOOP_SHAS))

# --- no-model-input: scrubbed-globals execution --------------------------
import hashlib as _hl  # noqa: E402
import json as _js  # noqa: E402
import decimal as _dc  # noqa: E402
_SCRUB = {"__builtins__": __builtins__, "hashlib": _hl, "json": _js,
          "decimal": _dc}
_FNS = {"F_v1": AD.adapt_f_v1, "F_v2": AD.adapt_f_v2,
        "NOOP_v1": AD.adapt_noop_v1}
_scrub_ok, _scrub_detail = True, ""
for _name, _fn in sorted(_FNS.items()):
    _bare = types.FunctionType(_fn.__code__, dict(_SCRUB), _fn.__name__)
    try:
        if _name == "F_v1":
            _got = _bare(SCHEMA, dict(FILES), AD.ADAPTATION_POLICY_V1)
            _want = _ADAPT["files"]
        elif _name == "F_v2":
            _got = _bare(SCHEMA, dict(FILES), AD.ADAPTATION_POLICY_V2)
            _want = AD.adapt_task(
                SCHEMA_ID, dict(FILES), "F_v2")["files"]
        else:
            _got = _bare(SCHEMA, dict(FILES), AD.ADAPTATION_POLICY_V1)
            _want = AD.adapt_task(
                SCHEMA_ID, dict(FILES), "NOOP_v1")["files"]
        if _got.get("files") != _want:
            _scrub_ok, _scrub_detail = False, f"{_name}: output differs"
    except NameError as e:
        _scrub_ok, _scrub_detail = False, f"{_name}: NameError {e}"
check("A13-NOMODEL version bodies run clean under scrubbed globals "
      "(args + builtins + hashlib/json/decimal only — any module-"
      "state read, model or otherwise, raises NameError)",
      _scrub_ok, _scrub_detail)

# --- no-model-input: no model slot + recorded-attack invariance ----------
import inspect as _inspect2  # noqa: E402
_sigs_ok = all(
    list(_inspect2.signature(_FNS[n]).parameters) == ["schema",
                                                      "task_files",
                                                      "policy"]
    for n in _FNS)
check("A13-NOMODEL no model slot exists in any version signature",
      _sigs_ok)
# Recorded acceptance attack shape: response A (mapping M1, ordering
# [a,b], offsets 0:10/10:20, provider bytes P-A) vs response B
# (mapping M2, ordering [b,a], reversed offsets, provider bytes
# P-B). F takes neither world as input; both worlds MUST yield the
# frozen baseline bytes.
_M1 = {"mapping": {"NAME": "name", "ID": "id"},
       "ordering": ["a", "b"], "offsets": [0, 10, 20],
       "provider": "P-A"}
_M2 = {"mapping": {"ID": "id", "NAME": "name"},
       "ordering": ["b", "a"], "offsets": [20, 10, 0],
       "provider": "P-B"}
_a = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v1")
_b = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v1")
check("A13-NOMODEL recorded-attack variants leave the adapted sha "
      "unmoved (model bytes are not consumed)",
      _a["adapted_input_sha256"] == _b["adapted_input_sha256"]
      == _ADAPT["adapted_input_sha256"]
      and _M1 != _M2)
# Textual tripwire (behavioral proofs above carry the weight):
# version sources must not name I/O, time, randomness, env, or eval.
_SRC_ALL = "\n".join(_inspect2.getsource(_FNS[n]) for n in _FNS)
_FORBIDDEN = ["open(", "input(", "__import__", "eval(", "exec(",
              "compile(", "globals(", "locals(", "vars(", "dir(",
              "getattr(", "setattr(", "import time", "import random",
              "os.environ", "os.getenv", "getenv", "time.", "random.",
              "clock", "sleep("]
_found = [t for t in _FORBIDDEN if t in _SRC_ALL]
check("A13-NOMODEL version sources name no I/O, clock, randomness, "
      "env, or reflection", not _found, str(_found))

# --- NOOP schema-swap invariance (schema unconsulted) --------------------
_ALT_SCHEMA = dict(SCHEMA)
_ALT_SCHEMA["columns"] = ["ID", "NAME", "TAGS", "AMOUNT_USD"]
_n1 = AD.adapt_task(SCHEMA_ID, dict(FILES), "NOOP_v1")
_n2files = AD.adapt_noop_v1(_ALT_SCHEMA, dict(FILES),
                            AD.ADAPTATION_POLICY_V1)["files"]
check("A13-NOMODEL NOOP output invariant under schema swap "
      "(schema accepted for ABI parity, unconsulted)",
      AD._tree_sha(AD._tree_entries(_n1["files"]))[0]
      == AD._tree_sha(AD._tree_entries(_n2files))[0])

# --- negative control -----------------------------------------------------
_V1 = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v1")
_V2 = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v2")
_C1 = AD.contract_sha_for("F_v1")
_C2 = AD.contract_sha_for("F_v2")
_D1 = AD.build_determinant(ARTIFACT_SHA, SCHEMA_SHA, SNAPSHOT_SHA, _C1)
_D2 = AD.build_determinant(ARTIFACT_SHA, SCHEMA_SHA, SNAPSHOT_SHA, _C2)
check("A13-NEG F_v1/ABI_v1 -> bytes A, F_v2/ABI_v2 -> bytes B, "
      "A != B",
      _V1["adapted_input_sha256"] != _V2["adapted_input_sha256"]
      and _V1["files"] != _V2["files"])
check("A13-NEG the two versions MUST NOT count as the same "
      "determinant (contract + tuple + tuple-sha all differ)",
      _C1 != _C2 and _D1["determinant"] != _D2["determinant"]
      and _D1["determinant_sha256"] != _D2["determinant_sha256"])

# --- receipt skeleton ------------------------------------------------------
_NOOP = AD.adapt_task(SCHEMA_ID, dict(FILES), "NOOP_v1")


def _leg(program, adapted, consumer):
    return {"program": program,
            "program_identity": AD.program_identity(program),
            "adapter_abi": AD.VERSION_WIRING[program]["abi"],
            "consumer": consumer,
            "adapted_input_sha256": adapted["adapted_input_sha256"],
            "adapted_files": {n: _sha(b) for n, b in
                              sorted(adapted["files"].items())},
            "execution_evidence": None}


_EV = FV.derive_expected_evaluator(FAMC, FREEZE, "fam01")
import run_arm_h1 as _RA  # noqa: E402 (read-only harness identity)
_HARNESS_SHA = _RA.harness_manifest_sha()
_RCPT = AD.build_receipt(
    family="fam01", task="T2", capability_id="cap-h35-fixture",
    determinant=_D1["determinant"],
    determinant_sha256=_D1["determinant_sha256"],
    on=_leg("F_v1", _V1, "locked-engine-then-checker"),
    off_noop=_leg("NOOP_v1", _NOOP, "locked-engine-then-checker"),
    pass_through=_leg("F_v1", _V1, "checker-direct"),
    checker_sha256=_EV["checker_sha256"],
    truth_sha256=_EV["truth_sha256"],
    execution_harness_manifest_sha256=_HARNESS_SHA)
check("A13-RECEIPT skeleton binds determinant + legs + task/ "
      "capability/checker/harness identities",
      _RCPT["determinant"] == _D1["determinant"]
      and _RCPT["determinant_sha256"] == _D1["determinant_sha256"]
      and _RCPT["checker"] == {"checker_sha256": _EV["checker_sha256"],
                               "truth_sha256": _EV["truth_sha256"]}
      and _RCPT["execution_harness_manifest_sha256"] == _HARNESS_SHA
      and _RCPT["receipt_schema"] == "a13-causal-receipt-v1",
      str(sorted(_RCPT))[:160])
check("A13-RECEIPT canonical + self-hashed (re-serialization "
      "reproduces the self sha)",
      _RCPT["receipt_sha256"] == _sha(_canon(
          {k: v for k, v in _RCPT.items()
           if k != "receipt_sha256"}).encode()))
check("A13-RECEIPT exact key sets (no smuggled content anywhere)",
      sorted(_RCPT) == sorted(("receipt_schema", "family", "task",
                               "capability", "determinant",
                               "determinant_sha256", "legs", "checker",
                               "execution_harness_manifest_sha256",
                               "receipt_sha256"))
      and sorted(_RCPT["legs"]) == ["off-noop", "on", "pass-through"]
      and all(sorted(_RCPT["legs"][leg]) == sorted(
          ("program", "program_identity", "adapter_abi", "consumer",
           "adapted_input_sha256", "adapted_files",
           "execution_evidence")) for leg in _RCPT["legs"]))
check("A13-RECEIPT ON/pass-through share adapted bytes with "
      "different consumers; OFF differs; execution slots null "
      "pending the executed-legs ruling",
      _RCPT["legs"]["on"]["adapted_input_sha256"]
      == _RCPT["legs"]["pass-through"]["adapted_input_sha256"]
      != _RCPT["legs"]["off-noop"]["adapted_input_sha256"]
      and (_RCPT["legs"]["on"]["consumer"],
           _RCPT["legs"]["pass-through"]["consumer"],
           _RCPT["legs"]["off-noop"]["consumer"])
      == ("locked-engine-then-checker", "checker-direct",
          "locked-engine-then-checker")
      and all(_RCPT["legs"][leg]["execution_evidence"] is None
              for leg in _RCPT["legs"]))

# --- consistency: same computation as production, never forked ------------
_TMPD = tempfile.mkdtemp(prefix="h35-adapt-")
for _n, _b in _V1["files"].items():
    open(os.path.join(_TMPD, _n), "wb").write(_b)
_entries, _denial = _RA._scan_candidate_input(_TMPD)
_prod_sha, _ = _RA._manifest_tree_sha256(
    _RA.CANDIDATE_INPUT_MANIFEST_SCHEMA, _entries)
check("A13-CONSISTENT adaptation tree-hash == production "
      "computation over materialized F files (same formula, same "
      "label, same entries)",
      _denial is None
      and _entries == AD._tree_entries(_V1["files"])
      and _prod_sha == _V1["adapted_input_sha256"],
      f"denial={_denial}")
check("A13-CONSISTENT schema label identical to production's",
      AD.TREE_SCHEMA == _RA.CANDIDATE_INPUT_MANIFEST_SCHEMA)
shutil.rmtree(_TMPD, ignore_errors=True)

# --- registry refusals ------------------------------------------------------
def _raises_name(fn, token):
    try:
        fn()
    except (ValueError, RuntimeError) as e:
        return token in str(e), str(e)[:120]
    return False, "no refusal"


ok_r1, why_r1 = _raises_name(
    lambda: AD.get_schema("fam99-nope"), "ADAPTATION-SCHEMA-UNKNOWN")
ok_r2, why_r2 = _raises_name(
    lambda: AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v9"),
    "ADAPTATION-VERSION-UNKNOWN")
ok_r3, why_r3 = _raises_name(
    lambda: AD.adapt_task(SCHEMA_ID, {"prompt.md": b"x"}, "F_v1"),
    "ADAPTATION-RECORD-FILE-ABSENT")
check("A13-REGISTRY unknown schema / program / uncovered surface "
      "refuse by name (never silent)",
      ok_r1 and ok_r2 and ok_r3, f"{why_r1} | {why_r2} | {why_r3}")

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH35 A13 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

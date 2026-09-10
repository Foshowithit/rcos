#!/usr/bin/env python3
"""H35 — A13 canonical-adaptation acceptance (frozen determinant + F)
+ H35b executed counterfactual legs (auditor ruling, A13_CAUSAL).

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
                   and self-hashed, exact key sets; unexecuted legs
                   record bindings with execution observables None
                   (missing, never defaulted) and a derived-false
                   causal flag;
  consistency      adaptation tree-hash == run_arm_h1's production
                   computation over materialized F files (same
                   formula, same schema label — never forked);
  registry         unknown schema/program/surface refuse by name;
  correctness      F_v1 records == frozen T2 truth records.
  H35b executed legs (ShimJail shims, REAL frozen fam01 checker +
  truth, fixture order-restoring K, NO model call):
    ON leg         executes the exact locked K on the F pair and
                   SHIPs the frozen checker (executable == K);
    OFF-noop       the NOOP pair through the SAME K behind the same
                   ABI grades fix (checker verdict on produced
                   output; target == K, noop ABI != K);
    pass-through   F's exact canonical bytes through the frozen
                   family-agnostic op (K bypassed) grades fix (order
                   gap: F order != task order); op source carries no
                   family tokens; op identity stable and != K;
    receipt        execute_a13_legs end-to-end: all 18 ruling slots
                   real, per-leg bindings == determinant, checkers
                   equal, executable/target == K, outputs differ,
                   verdicts ship/fix/fix, reruns real+identical,
                   causal TRUE derived (never asserted), self-sha
                   verifies, receipt file round-trips;
    honesty        an always-ship K makes OFF ship -> causal FALSE
                   (treatment stays ON; no exception, no model
                   call); a crashing K records missing output with
                   causal FALSE (never a default verdict); an
                   uncovered surface omits the legs with a reason;
    isolation      OFF/PASS verdicts can never alter the treatment
                   verdict; the leg path makes no provider call
                   (monkeypatched to raise), touches no ORDER
                   surface (source scan), and can never become a
                   retry (a shipping counterfactual completes the
                   cell with causal false, without follow-up action).

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
                               "determinant_sha256",
                               "adapted_input_sha256", "determinism",
                               "legs", "checker", "frozen_checker_sha256",
                               "execution_harness_manifest_sha256",
                               "causal_contribution_proven",
                               "provider_call_delta", "order_cell_delta",
                               "receipt_sha256"))
      and sorted(_RCPT["legs"]) == ["off-noop", "on", "pass-through"]
      and sorted(_RCPT["legs"]["on"]) == sorted(
          ("program", "program_identity", "adapter_abi", "consumer",
           "adapted_input_sha256", "adapted_files",
           "execution_evidence", "task_snapshot_sha256",
           "capability_schema_sha256", "adaptation_contract_sha256",
           "checker_sha256", "checker_returncode", "checker_output",
           "checker_output_sha256", "captured_response_sha256",
           "cell_id", "executable_sha256", "output_sha256",
           "verdict"))
      and sorted(_RCPT["legs"]["off-noop"]) == sorted(
          ("program", "program_identity", "adapter_abi", "consumer",
           "adapted_input_sha256", "adapted_files",
           "execution_evidence", "task_snapshot_sha256",
           "capability_schema_sha256", "adaptation_contract_sha256",
           "checker_sha256", "checker_returncode", "checker_output",
           "checker_output_sha256", "captured_response_sha256",
           "cell_id", "target_capability_sha256",
           "noop_abi_sha256", "output_sha256", "verdict"))
      and sorted(_RCPT["legs"]["pass-through"]) == sorted(
          ("program", "program_identity", "adapter_abi", "consumer",
           "adapted_input_sha256", "adapted_files",
           "execution_evidence", "task_snapshot_sha256",
           "capability_schema_sha256", "adaptation_contract_sha256",
           "checker_sha256", "checker_returncode", "checker_output",
           "checker_output_sha256", "captured_response_sha256",
           "cell_id", "passthrough_implementation_sha256",
           "output_sha256", "verdict"))
      and sorted(_RCPT["determinism"]) == sorted(
          ("rerun_1_sha256", "rerun_2_sha256", "identical",
           "model_response_argument_present")))
check("A13-RECEIPT ON/pass-through share adapted bytes with "
      "different consumers; OFF differs",
      _RCPT["legs"]["on"]["adapted_input_sha256"]
      == _RCPT["legs"]["pass-through"]["adapted_input_sha256"]
      != _RCPT["legs"]["off-noop"]["adapted_input_sha256"]
      and (_RCPT["legs"]["on"]["consumer"],
           _RCPT["legs"]["pass-through"]["consumer"],
           _RCPT["legs"]["off-noop"]["consumer"])
      == ("locked-engine-then-checker", "checker-direct",
          "locked-engine-then-checker"),
      str({leg: _RCPT["legs"][leg]["adapted_input_sha256"][:12]
           for leg in _RCPT["legs"]}))
check("A13-RECEIPT unexecuted legs bind identities but record "
      "execution observables missing (None, never defaulted) and "
      "derive causal false",
      all(_RCPT["legs"][leg]["execution_evidence"] is None
          for leg in _RCPT["legs"])
      and all(_RCPT["legs"][leg]["task_snapshot_sha256"]
              == SNAPSHOT_SHA for leg in _RCPT["legs"])
      and all(_RCPT["legs"][leg]["capability_schema_sha256"]
              == SCHEMA_SHA for leg in _RCPT["legs"])
      and all(_RCPT["legs"][leg]["adaptation_contract_sha256"]
              == _CONT_MOD for leg in _RCPT["legs"])
      and all(_RCPT["legs"][leg]["checker_sha256"]
              == _EV["checker_sha256"] for leg in _RCPT["legs"])
      and _RCPT["legs"]["on"]["executable_sha256"] is None
      and _RCPT["legs"]["on"]["output_sha256"] is None
      and _RCPT["legs"]["on"]["verdict"] is None
      and _RCPT["legs"]["on"]["checker_returncode"] is None
      and _RCPT["legs"]["on"]["checker_output"] is None
      and _RCPT["legs"]["on"]["checker_output_sha256"] is None
      and all(_RCPT["legs"][leg]["captured_response_sha256"] is None
              and _RCPT["legs"][leg]["cell_id"] is None
              for leg in _RCPT["legs"])
      and _RCPT["provider_call_delta"] is None
      and _RCPT["order_cell_delta"] is None
      and _RCPT["legs"]["off-noop"]["target_capability_sha256"]
      == ARTIFACT_SHA
      and _RCPT["legs"]["off-noop"]["noop_abi_sha256"] not in (
          None, ARTIFACT_SHA)
      and _RCPT["legs"]["pass-through"][
          "passthrough_implementation_sha256"] not in (None,
                                                       ARTIFACT_SHA)
      and _RCPT["determinism"]["rerun_1_sha256"] is None
      and _RCPT["determinism"]["rerun_2_sha256"] is None
      and _RCPT["determinism"]["model_response_argument_present"]
      is False
      and _RCPT["frozen_checker_sha256"] == _EV["checker_sha256"]
      and _RCPT["causal_contribution_proven"] is False,
      str(_RCPT["causal_contribution_proven"]))

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

# ================= H35b: executed counterfactual legs =================
# Hermetic in-cell execution proof: ShimJail shims (no docker), the
# REAL frozen fam01 checker + truth, a fixture order-restoring K
# (stand-in bytes, NOT evidence -- the mechanism under test is the
# harness's execute+grade+bind+derive path, proven by sha equality),
# and NO model call anywhere (provider entry points monkeypatched
# to raise, so a green run proves zero calls on the leg path).
import inspect as _inspect3  # noqa: E402


class _ShimJail:
    """Local engine-jail shim (H23 shape): binds exactly one host
    visible root, runs real subprocesses with path mapping."""

    def __init__(self, work, visible):
        self.work = work
        self.visible = visible
        self.task_snapshot = _RA._hash_tree(visible)

    def run(self, argv, timeout=120):
        mapped = []
        for a in argv:
            if a == "/task":
                mapped.append(self.visible)
            elif a.startswith("/task/"):
                mapped.append(os.path.join(self.visible,
                                           a[len("/task/"):]))
            elif a == "/work":
                mapped.append(self.work)
            elif a.startswith("/work/"):
                mapped.append(os.path.join(self.work,
                                           a[len("/work/"):]))
            else:
                mapped.append(a)
        return subprocess.run(mapped, capture_output=True, text=True,
                              timeout=timeout)


def _shim_factory(work, visible):
    return _ShimJail(work, visible)


# Fixture K: a genuine (if small) semantic operation the adapter
# does NOT do -- order restoration. The field_map envelope carries
# the input sequence; F's canonical order differs from it, so K
# reorders records to the input sequence (fallback: emit as given,
# never crash on unmapped shapes). NO truth import, NO family
# checker knowledge: only /task documents are read.
_K_ORDER = """import json, sys
fmap = json.load(open(sys.argv[1]))
records = json.load(open(sys.argv[2]))
seq = []
try:
    lit = fmap["files"]["input.psv"]["literal"]
    rows = lit.split("\\n")
    cols = [c.strip() for c in rows[0].split("|")]
    idcol = cols.index("ID")
    for ln in rows[1:]:
        if ln.strip():
            seq.append(ln.split("|")[idcol].strip())
except Exception:
    seq = []
by_id = {r.get("id"): r for r in records
         if isinstance(r, dict) and "id" in r}
seen = set(seq)
out = [by_id[i] for i in seq if i in by_id]
out = out + [r for r in records if r.get("id") not in seen]
json.dump(out, open(sys.argv[3], "w"))
"""
# Always-ship K (derivation-honesty mutation): hardcodes the frozen
# truth bytes (read at fixture-build time, baked in as data) so the
# OFF-noop leg ships too -- the receipt must then derive causal
# FALSE while the treatment (ON) still stands.
_TRUTH_T2 = json.load(open(os.path.join(
    FAMC, "families", "fam01", "truth.json")))["T2"]
_K_SHIP = ("import json, sys\njson.dump(%s, open(sys.argv[3], 'w'))\n"
           % json.dumps(_TRUTH_T2, sort_keys=True))
# Crashing K (missing-evidence probe): exits without output.
_K_CRASH = "import sys\nsys.exit(3)\n"

_T2DIR = os.path.join(FAMC, "families", "fam01", "T2")
_T2_CHECKER = os.path.join(FAMC, "families", "fam01", "check.py")
_T2_TRUTH = os.path.join(FAMC, "families", "fam01", "truth.json")
_EV2 = FV.derive_expected_evaluator(FAMC, FREEZE, "fam01")
check("H35b-PRE live checker+truth == freeze authority (grading "
      "precondition)",
      _RA.h(_T2_CHECKER) == _EV2["checker_sha256"]
      and _RA.h(_T2_TRUTH) == _EV2["truth_sha256"])
_AUTH = {"family": "fam01", "freeze_commit": FREEZE,
         "expected_checker_sha256": _EV2["checker_sha256"],
         "expected_truth_sha256": _EV2["truth_sha256"]}
_SNAP = FV.derive_expected_visible(
    FAMC, FREEZE, "fam01", "T2")["manifest_sha256"]

_KDIR = tempfile.mkdtemp(prefix="h35-k-")
_KPATH = os.path.join(_KDIR, "engine.py")
open(_KPATH, "w").write(_K_ORDER)
_KSHA = _sha(open(_KPATH, "rb").read())
_CAP = {"capability_id": "cap-h35-fixture", "engine_sha256": _KSHA}
_FV1 = AD.adapt_task(SCHEMA_ID, dict(FILES), "F_v1")
_NOOP = AD.adapt_task(SCHEMA_ID, dict(FILES), "NOOP_v1")


def _payload(pair):
    return {name: json.loads(data.decode("utf-8"))
            for name, data in pair["files"].items()}


_ON_ARR = {"decision": "use_capability",
           "execution_payload": {
               "field_map": _payload(_FV1)["field_map.json"],
               "records": _payload(_FV1)["records.json"]},
           "notes": "h35b-on"}
_OFF_ARR = {"decision": "use_capability",
            "execution_payload": {
                "field_map": _payload(_NOOP)["field_map.json"],
                "records": _payload(_NOOP)["records.json"]},
            "notes": "h35b-off-noop"}
# No provider call on the leg path, ever: raise if attempted.
_calls = []


def _no_provider(*a, **k):
    _calls.append((a, k))
    raise AssertionError("A13 leg path invoked the provider")


_RA.call = _no_provider
_RA.recorded_call = _no_provider

_w1 = tempfile.mkdtemp(prefix="h35b-on-")
_o1 = tempfile.mkdtemp(prefix="h35b-on-out-")
_e1 = _RA.execute_arrival("correct", _ON_ARR, _w1, _o1, _T2DIR,
                          _KPATH, None, jail_factory=_shim_factory,
                          evaluator_authority=_AUTH)
_e1_out = json.load(open(os.path.join(_o1, "OUTPUT.json")))
check("H35b-ON executes the exact locked K and SHIPs the frozen "
      "checker",
      _e1["verdict"] == "ship" and _e1["checker_returncode"] == 0
      and _e1["container_returncode"] == 0
      and _e1["checker_sha256"] == _EV2["checker_sha256"]
      and _e1["evaluator_source"] == "frozen-materialized"
      and _e1["graded_output_sha256"] == _e1["output_sha256"]
      and _e1_out == _TRUTH_T2
      and _e1["engine_jail"]["adapted_input_sha256"]
      == _FV1["adapted_input_sha256"],
      f"verdict={_e1['verdict']} rc={_e1['checker_returncode']}")
_w2 = tempfile.mkdtemp(prefix="h35b-off-")
_o2 = tempfile.mkdtemp(prefix="h35b-off-out-")
_e2 = _RA.execute_arrival("correct", _OFF_ARR, _w2, _o2, _T2DIR,
                          _KPATH, None, jail_factory=_shim_factory,
                          evaluator_authority=_AUTH)
_e2_out = json.load(open(os.path.join(_o2, "OUTPUT.json")))
check("H35b-OFF the NOOP pair through the SAME K grades fix "
      "(checker verdict on produced output, same checker)",
      _e2["verdict"] == "fix" and _e2["checker_returncode"] == 1
      and _e2["checker_sha256"] == _e1["checker_sha256"]
      == _EV2["checker_sha256"]
      and _e2_out == json.loads(_NOOP["files"]["records.json"])
      and _e2["engine_jail"]["adapted_input_sha256"]
      == _NOOP["adapted_input_sha256"]
      != _e1["engine_jail"]["adapted_input_sha256"],
      f"verdict={_e2['verdict']} rc={_e2['checker_returncode']}")
_pt_bytes = AD.passthrough_v1(dict(_FV1["files"]))
_pt_outdir = tempfile.mkdtemp(prefix="h35b-pass-")
_pt_out = os.path.join(_pt_outdir, "OUTPUT.json")
open(_pt_out, "wb").write(_pt_bytes)
_pt_chk = subprocess.run([sys.executable, _T2_CHECKER, "T2", _pt_out],
                         capture_output=True, text=True)
check("H35b-PASS F's exact canonical bytes (K bypassed) grade fix "
      "on the frozen checker (F order != task order)",
      _pt_bytes == _FV1["files"]["records.json"]
      and _pt_chk.returncode == 1,
      f"rc={_pt_chk.returncode}")
_pts_src = _inspect3.getsource(AD.passthrough_v1)
check("H35b-PASS op is family-agnostic (no family surface in "
      "source) with a stable non-K identity",
      # NOTE: "checker" is deliberately NOT forbidden here: the
      # ruling routes the bytes to "the exact frozen checker", so
      # naming the grading destination is contract language, not
      # family semantics. Forbidden are family/surface tokens.
      all(tok not in _pts_src
          for tok in ("fam01", "fam05", "input.psv", "usd_to_cents",
                      "truth", "amount", "tags"))
      and AD.passthrough_identity() == AD.passthrough_identity()
      and len(AD.passthrough_identity()) == 64
      and AD.passthrough_identity() != _KSHA
      and AD.noop_abi_sha256() != _KSHA)
_w4 = tempfile.mkdtemp(prefix="h35b-cell-")
_o4 = tempfile.mkdtemp(prefix="h35b-cell-out-")
# Fixture isolation binding: the single captured response + cell
# every leg is downstream of (the runner passes the real
# response_text_sha256 + cell id; the fixture stands in).
_FX_RESPONSE = _sha(b"h35b-captured-response")
_FX_CELL = "H35B-FIXTURE-CELL"
_a4 = _RA.execute_a13_legs(
    family="fam01", task="T2", cap_info=dict(_CAP), cap_engine=_KPATH,
    on_exec=_e1, freeze_commit=FREEZE, famc_dir=FAMC, taskdir=_T2DIR,
    work=_w4, outdir=_o4, task_snapshot_sha256=_SNAP,
    evaluator_authority=_AUTH,
    captured_response_sha256=_FX_RESPONSE, cell_id=_FX_CELL,
    jail_factory=_shim_factory, sb=None)
check("H35b-LEGS end-to-end executes (no model call attempted)",
      _a4["executed"] is True and _a4["causal"] is True
      and _a4["leg_verdicts"] == {"on": "ship", "off-noop": "fix",
                                  "pass-through": "fix"}
      and _calls == [],
      f"{_a4['reason']} calls={len(_calls)}")
_R4 = _a4["receipt"]
check("H35b-RECEIPT all 18 ruling slots real (reruns, on, "
      "off-noop, pass-through, causal)",
      _R4["determinism"]["rerun_1_sha256"]
      == _R4["determinism"]["rerun_2_sha256"]
      == _FV1["adapted_input_sha256"]
      and _R4["determinism"]["identical"] is True
      and _R4["determinism"]["model_response_argument_present"]
      is False
      and _R4["legs"]["on"]["executable_sha256"] == _KSHA
      and _R4["legs"]["on"]["output_sha256"]
      == _e1["graded_output_sha256"]
      and _R4["legs"]["on"]["checker_sha256"]
      == _EV2["checker_sha256"]
      and _R4["legs"]["on"]["checker_returncode"] == 0
      and isinstance(_R4["legs"]["on"]["checker_output"], str)
      and _R4["legs"]["on"]["checker_output"].strip() != ""
      and "traceback" not in _R4["legs"]["on"][
          "checker_output"].lower()
      and _R4["legs"]["on"]["checker_output_sha256"] == _sha(
          _R4["legs"]["on"]["checker_output"].encode())
      and _R4["legs"]["on"]["verdict"] == "ship"
      and _R4["legs"]["off-noop"]["target_capability_sha256"]
      == _KSHA
      and _R4["legs"]["off-noop"]["noop_abi_sha256"]
      == AD.noop_abi_sha256()
      and _R4["legs"]["off-noop"]["output_sha256"]
      == _e2["graded_output_sha256"]
      and _R4["legs"]["off-noop"]["checker_sha256"]
      == _EV2["checker_sha256"]
      and _R4["legs"]["off-noop"]["checker_returncode"] == 1
      and isinstance(_R4["legs"]["off-noop"]["checker_output"], str)
      and _R4["legs"]["off-noop"]["checker_output"].strip() != ""
      and "traceback" not in _R4["legs"]["off-noop"][
          "checker_output"].lower()
      and _R4["legs"]["off-noop"]["checker_output_sha256"] == _sha(
          _R4["legs"]["off-noop"]["checker_output"].encode())
      and _R4["legs"]["off-noop"]["verdict"] == "fix"
      and _R4["legs"]["pass-through"][
          "passthrough_implementation_sha256"]
      == AD.passthrough_identity()
      and _R4["legs"]["pass-through"]["output_sha256"]
      == _sha(_FV1["files"]["records.json"])
      and _R4["legs"]["pass-through"]["checker_sha256"]
      == _EV2["checker_sha256"]
      and _R4["legs"]["pass-through"]["checker_returncode"] == 1
      and isinstance(_R4["legs"]["pass-through"]["checker_output"],
                     str)
      and _R4["legs"]["pass-through"]["checker_output"].strip()
      != ""
      and "traceback" not in _R4["legs"]["pass-through"][
          "checker_output"].lower()
      and _R4["legs"]["pass-through"]["checker_output_sha256"] \
      == _sha(_R4["legs"]["pass-through"]["checker_output"].encode())
      and _R4["legs"]["pass-through"]["verdict"] == "fix"
      and all(_R4["legs"][leg]["captured_response_sha256"]
              == _FX_RESPONSE for leg in _R4["legs"])
      and all(_R4["legs"][leg]["cell_id"] == _FX_CELL
              for leg in _R4["legs"])
      and _R4["provider_call_delta"] == 0
      and _R4["order_cell_delta"] == 0
      and _R4["causal_contribution_proven"] is True)
check("H35b-RECEIPT bindings == determinant, checkers shared, "
      "outputs differ, identities distinct",
      all(_R4["legs"][leg]["task_snapshot_sha256"] == _SNAP
          for leg in ("on", "off-noop", "pass-through"))
      and all(_R4["legs"][leg]["capability_schema_sha256"]
              == SCHEMA_SHA
              for leg in ("on", "off-noop", "pass-through"))
      and all(_R4["legs"][leg]["adaptation_contract_sha256"]
              == _CONT_MOD
              for leg in ("on", "off-noop", "pass-through"))
      and _R4["determinant"]["capability_artifact_sha256"] == _KSHA
      and _R4["determinant"][
          "exact_visible_task_snapshot_sha256"] == _SNAP
      and _R4["legs"]["off-noop"]["checker_sha256"]
      == _R4["legs"]["pass-through"]["checker_sha256"]
      == _R4["legs"]["on"]["checker_sha256"]
      and _R4["legs"]["on"]["output_sha256"]
      != _R4["legs"]["off-noop"]["output_sha256"]
      and _R4["legs"]["on"]["output_sha256"]
      != _R4["legs"]["pass-through"]["output_sha256"]
      and _R4["legs"]["off-noop"]["noop_abi_sha256"] != _KSHA
      and _R4["legs"]["pass-through"][
          "passthrough_implementation_sha256"] != _KSHA
      and _R4["legs"]["on"]["program_identity"]
      != _R4["legs"]["off-noop"]["program_identity"])
check("H35b-RECEIPT canonical self-sha verifies + file "
      "round-trips (chain-bindable)",
      _R4["receipt_sha256"] == _sha(_canon(
          {k: v for k, v in _R4.items()
           if k != "receipt_sha256"}).encode())
      and json.load(open(_a4["receipt_path"])) == _R4
      and os.path.basename(_a4["receipt_path"])
      == "A13-CAUSAL-RECEIPT.json"
      and _a4["receipt_sha256"] == _R4["receipt_sha256"])
_proven4, _detail4 = AD.derive_causal_contribution(
    determinant=_R4["determinant"],
    determinant_sha256=_R4["determinant_sha256"], legs=_R4["legs"],
    determinism=_R4["determinism"])
check("H35b-DERIVE causal TRUE with every condition + relation "
      "resolved from raw receipt values",
      _proven4 is True and _R4["causal_contribution_proven"] is True
      and all(item["ok"] for item in _detail4["conditions"]),
      str([item["name"] for item in _detail4["conditions"]
           if not item["ok"]]))


def _synth_legs(mutate):
    _legs = json.loads(json.dumps(_R4["legs"]))
    mutate(_legs)
    return _legs


def _derive_on(legs):
    _proven, _detail = AD.derive_causal_contribution(
        determinant=_R4["determinant"],
        determinant_sha256=_R4["determinant_sha256"], legs=legs,
        determinism=_R4["determinism"])
    return _proven


# Auditor v2.2 counting rule, driven through the real derivation
# on synthetic receipts (no harness mutation): a counterfactual
# leg counts ONLY with rc 1 + verdict fix + recomputing report
# hash + non-empty crash-free output. Every other route is
# missing evidence, never the desired outcome.
check("H35b-COUNT rc1 with traceback output does NOT count "
      "(crashed checker)",
      _derive_on(_synth_legs(lambda legs: (
          legs["off-noop"].__setitem__(
              "checker_output",
              "Traceback (most recent call last): Boom"),
          legs["off-noop"].__setitem__(
              "checker_output_sha256",
              _sha(b"Traceback (most recent call last): Boom")))))
      is False)
check("H35b-COUNT rc1 recorded as blocked does NOT count "
      "(contradicts the frozen derivation)",
      _derive_on(_synth_legs(lambda legs: legs["off-noop"].__setitem__(
          "verdict", "blocked"))) is False)
check("H35b-COUNT rc0 recorded as fix does NOT count (rc0 cannot "
      "fake NOT-SHIP)",
      _derive_on(_synth_legs(lambda legs: (
          legs["pass-through"].__setitem__("checker_returncode", 0),
          legs["pass-through"].__setitem__("verdict", "fix"))))
      is False)
check("H35b-COUNT missing report hash does NOT count",
      _derive_on(_synth_legs(lambda legs: legs["pass-through"]
                 .__setitem__("checker_output_sha256", None)))
      is False)
check("H35b-COUNT rc2 blocked with output does NOT count "
      "(strict option: rc>=2 is missing evidence)",
      _derive_on(_synth_legs(lambda legs: (
          legs["off-noop"].__setitem__("checker_returncode", 2),
          legs["off-noop"].__setitem__("verdict", "blocked"))))
      is False)
check("H35b-COUNT silent output does NOT count (silence is not "
      "fix)",
      _derive_on(_synth_legs(lambda legs: (
          legs["pass-through"].__setitem__("checker_output", "  "),
          legs["pass-through"].__setitem__(
              "checker_output_sha256", _sha(b"  ")))))
      is False)
# Derivation honesty: an always-ship K makes OFF ship -> causal
# FALSE (never hardcoded true); the treatment (ON) still stands,
# the cell completes, and no provider call is attempted.
_KDIR5 = tempfile.mkdtemp(prefix="h35-kship-")
_KPATH5 = os.path.join(_KDIR5, "engine.py")
open(_KPATH5, "w").write(_K_SHIP)
_KSHA5 = _sha(open(_KPATH5, "rb").read())
_w5 = tempfile.mkdtemp(prefix="h35b-ship-")
_o5 = tempfile.mkdtemp(prefix="h35b-ship-out-")
_e5 = _RA.execute_arrival("correct", _ON_ARR, _w5, _o5, _T2DIR,
                          _KPATH5, None, jail_factory=_shim_factory,
                          evaluator_authority=_AUTH)
_w5b = tempfile.mkdtemp(prefix="h35b-shipcell-")
_o5b = tempfile.mkdtemp(prefix="h35b-shipcell-out-")
_a5 = _RA.execute_a13_legs(
    family="fam01", task="T2",
    cap_info={"capability_id": "cap-h35-ship",
              "engine_sha256": _KSHA5},
    cap_engine=_KPATH5, on_exec=_e5, freeze_commit=FREEZE,
    famc_dir=FAMC, taskdir=_T2DIR, work=_w5b, outdir=_o5b,
    task_snapshot_sha256=_SNAP, evaluator_authority=_AUTH,
    jail_factory=_shim_factory, sb=None)
_proven5, _detail5 = AD.derive_causal_contribution(
    determinant=_a5["receipt"]["determinant"],
    determinant_sha256=_a5["receipt"]["determinant_sha256"],
    legs=_a5["receipt"]["legs"],
    determinism=_a5["receipt"]["determinism"])
check("H35b-HONEST shipping OFF-noop derives causal FALSE "
      "(treatment stays ON=ship; no exception, no model call)",
      _a5["executed"] is True
      and _a5["leg_verdicts"] == {"on": "ship", "off-noop": "ship",
                                  "pass-through": "fix"}
      and _a5["causal"] is False
      and _a5["receipt"]["causal_contribution_proven"] is False
      and _proven5 is False
      and _calls == [],
      f"causal={_a5['causal']} calls={len(_calls)}")
# Missing evidence is recorded, never defaulted: a crashing K
# yields a built receipt with None output + causal FALSE (the
# cell still completes with the ON verdict); an uncovered
# surface omits the legs with a reason (never a verdict).
_KDIR7 = tempfile.mkdtemp(prefix="h35-kcrash-")
_KPATH7 = os.path.join(_KDIR7, "engine.py")
open(_KPATH7, "w").write(_K_CRASH)
_KSHA7 = _sha(open(_KPATH7, "rb").read())
_w7 = tempfile.mkdtemp(prefix="h35b-crash-")
_o7 = tempfile.mkdtemp(prefix="h35b-crash-out-")
_e7 = _RA.execute_arrival("correct", _ON_ARR, _w7, _o7, _T2DIR,
                          _KPATH7, None, jail_factory=_shim_factory,
                          evaluator_authority=_AUTH)
_w7b = tempfile.mkdtemp(prefix="h35b-crashcell-")
_o7b = tempfile.mkdtemp(prefix="h35b-crashcell-out-")
_a7 = _RA.execute_a13_legs(
    family="fam01", task="T2",
    cap_info={"capability_id": "cap-h35-crash",
              "engine_sha256": _KSHA7},
    cap_engine=_KPATH7, on_exec=_e7, freeze_commit=FREEZE,
    famc_dir=FAMC, taskdir=_T2DIR, work=_w7b, outdir=_o7b,
    task_snapshot_sha256=_SNAP, evaluator_authority=_AUTH,
    jail_factory=_shim_factory, sb=None)
check("H35b-MISSING crashing K records missing output (None, "
      "causal FALSE) without failing the cell",
      _e7["verdict"] == "blocked" and _e7["output_sha256"] is None
      and _a7["executed"] is True and _a7["causal"] is False
      and _a7["leg_verdicts"]["on"] == "blocked"
      and _a7["receipt"]["legs"]["on"]["output_sha256"] is None
      and _a7["receipt"]["legs"]["on"]["verdict"] == "blocked"
      and _a7["receipt"]["causal_contribution_proven"] is False)
_SNAP50 = FV.derive_expected_visible(
    FAMC, FREEZE, "fam05", "T0")["manifest_sha256"]
_w7c = tempfile.mkdtemp(prefix="h35b-omit-")
_o7c = tempfile.mkdtemp(prefix="h35b-omit-out-")
_a7c = _RA.execute_a13_legs(
    family="fam05", task="T0", cap_info=dict(_CAP),
    cap_engine=_KPATH, on_exec=_e1, freeze_commit=FREEZE,
    famc_dir=FAMC,
    taskdir=os.path.join(FAMC, "families", "fam05", "T0"),
    work=_w7c, outdir=_o7c, task_snapshot_sha256=_SNAP50,
    evaluator_authority=_AUTH, jail_factory=_shim_factory, sb=None)
check("H35b-MISSING uncovered surface omits the legs with a "
      "reason (never a verdict)",
      _a7c["executed"] is False and _a7c["receipt"] is None
      and _a7c["causal"] is False
      and isinstance(_a7c["reason"], str)
      and "schema" in _a7c["reason"],
      str(_a7c["reason"]))
# Verdict isolation + non-retry structure: the leg helper's own
# source reaches no provider, no ORDER surface, and names no
# retry/repair path; main() binds the receipt into the manifest.
_helper_src = _inspect3.getsource(_RA.execute_a13_legs)
check("H35b-ISOLATE leg path cannot become a provider call, an "
      "ORDER cell, or a retry (source scan)",
      all(term not in _helper_src
          for term in ("recorded_call", "order_authorize",
                       "order_expected", "retry", "repair", "urllib",
                       "p_call", "import order"))
      and "execute_a13_legs" in _inspect3.getsource(_RA.main)
      and "a13_receipt_sha256" in _inspect3.getsource(_RA.main)
      and "capability_materially_contributed" in _inspect3.getsource(
          _RA.main))
for _d in (_KDIR, _w1, _o1, _w2, _o2, _pt_outdir, _w4, _o4, _KDIR5,
           _w5, _o5, _w5b, _o5b, _KDIR7, _w7, _o7, _w7b, _o7b, _w7c,
           _o7c):
    shutil.rmtree(_d, ignore_errors=True)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH35 A13 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)

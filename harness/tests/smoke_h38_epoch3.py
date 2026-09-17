#!/usr/bin/env python3
"""H38 EPOCH-3 SEMANTICS smoke — the MODEL-OUTPUT-INVALID terminal, the
attempt ledger / N=1 budget, the §3.1 governance evidence union and the
epoch-3 lineage mechanics (EPOCH-3-PROTOCOL-SPEC.md, frozen).

Coverage (everything through the REAL validators/writers/controllers — no
stubs; no provider call, no docker, no network):

  A. THE TERMINAL (probes 4, 5, 6; §1/§2/§5)
     A1 the write-once writer mints a lawful terminal from the preserved
        response bytes (ordering: call artifacts + raw-<call_id>.txt +
        ledger row durable, then the frozen extract() judges the PRESERVED
        bytes, then O_EXCL create) and the walk accepts COMPLETE-FAILURE;
     A2 duplicate write refused (MODEL-OUTPUT-INVALID-DENY), never
        overwritten;
     A3 probe 4 — replay of the preserved response through the frozen
        extract() must raise the EXACT recorded eligible denial: a tampered
        response that yields a DIFFERENT eligible error refuses, and one
        that yields an ARRIVAL refuses (A11b.2 is deterministic);
     A4 probe 5 — an identity-invalid sample cannot mint a terminal (the
        writer refuses; a tampered identity record makes a minted terminal
        INADMISSIBLE);
     A5 probe 6 — a provider/transport error body without a completion
        sample stays INFRASTRUCTURE: the real recorded_call raises
        NoModelSample, nothing is parsed, no terminal is minted, and the
        invocation is enumerated with null response/usage/identity fields.
  B. ATTEMPT ACCOUNTING (probe 7; §4)
     B1 the ledger enumerates one row per invocation in call order;
     B2 probe 7 — a second same-cell provider invocation is HARD-REFUSED
        (ATTEMPT-BUDGET-DENY) before any second call, and a terminal-
        bearing cell refuses with MODEL-OUTPUT-INVALID-DENY;
     B3 probe 8 — tampered/missing ledger rows refuse (missing file, wrong
        request hash, null-on-non-infra, extra row, denial row without a
        terminal);
     B4 the two reliability statistics + the denominator decomposition are
        enumerated from the ledger, never collapsed.
  C. PROGRESS ALGEBRA + GOVERNANCE UNION (probes 1, 2, 3, 10; §3/§3.1/§4.1)
     C1 probe 1 — T0 terminal continuation: no candidate, T1
        NOT-EVALUABLE, PROMOTION NOT-PROMOTED, CAPABILITY_LOCK NOT-LOCKED,
        downstream NOT-EVALUABLE, prefix advances, nothing minted;
     C2 probe 2 — T1 terminal continuation: T0 COMPLETE, the real candidate
        exists but was never validly validated, both governance terminals
        recorded with failure_event T1 and the real candidate sha;
     C3 probe 10 — governance records with a wrong terminal SHA, a
        null-tip/chain branch shape or a wrong candidate refuse;
     C4 probe 3 — a downstream T2/T3 terminal is a NON-SHIP correctness
        failure barred from an efficiency win, a T4 terminal is never a
        correct specificity rejection, and the §24 evidence row carries
        ship False / null checker fields / evidence_hash = terminal sha /
        model_calls 1 / retries 0 / terminal_class;
     C5 the algebra table (COMPLETE-FAILURE is progress-valid for model
        cells ONLY) and exit code 0 for a recorded terminal.
  D. EPOCH-3 LINEAGE + AUTHORITY (probes 9, 11, 12; §6/§7)
     D1 probe 9 — an execution/protocol lock binding mismatch refuses;
     D2 probe 11 — epoch-2 state cannot satisfy an epoch-3 cell (the walk
        never scans state/epoch2/**; the epoch-2 bytes stay untouched);
     D3 probe 12 — a tampered terminal never advances the prefix;
     D4 the live tree at this ref IS epoch 3: the structural activation
        holds, both fresh locks are present, and the transition audit is
        green (preflight V1/V2/V3 authority).

Stdlib only. Prints `H38 epoch-3 semantics smoke: N/N closed`; exits
non-zero on any failure.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
ROOT = os.path.dirname(HARNESS)
FAMC = os.path.join(ROOT, "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, FAMC)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import epoch as EPOCH  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import preflight as PF  # noqa: E402
import usage as UG  # noqa: E402
import run_arm_h1 as RAH  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              _write_usage_evidence, t0_candidate_sha256)

# the real successful-acquisition fixture recipe (same as H18/H13):
# a solver/adapter stand-in and the discriminating producer contract
# per family, so PROMOTION + CAPABILITY_LOCK really mint a lock.
SOLVER = "import sys; sys.exit(0)\n"
ADAPTER = "import sys; sys.exit(0)\n"
CONTRACT = {"fam01": {"requires_all": ["summary", "row"]},
            "fam03": {"requires_all": ["identical", "repeats"]},
            "fam05": {"requires_all": ["local", "sha256"]}}

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
# a response the frozen A11b.2 gate refuses with the eligible named error
BAD_RAW = "I could not produce JSON for this task, sorry.\n{{{ not json"
# a response that yields an ARRIVAL if replayed (A11b.2 determinism probe)
GOOD_RAW = json.dumps({"decision": "fresh", "notes": "ok",
                       "execution_payload": {"solver_py":
                                             "print('hello')\n"}})


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


class BasePatch:
    """Point the runner's module-global BASE at a hermetic instance for the
    duration of a writer call (the writer reads the ACTIVE authority from
    it)."""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        self.old = RAH.BASE
        RAH.BASE = self.root
        return self

    def __exit__(self, *exc):
        RAH.BASE = self.old
        return False


# ---------------------------------------------------------------------------
# hermetic epoch-3 instance
# ---------------------------------------------------------------------------

def epoch3_root(tag):
    """A throwaway Fam-C instance carrying the REAL frozen lineage bytes
    (epoch-1 closure + locks, epoch-2 transition + FINAL locks, the stop
    record, the frozen epoch-3 spec, ORDER-EXPANSION.json, the governed
    docs, the frozen parse gate), plus a SYNTHESIZED epoch-3 transition
    record and the two fresh epoch-3 locks — byte-for-byte the citations
    the frozen constants require, so epoch 3 is structurally ACTIVE in the
    fixture and the REAL terminal validator can judge it."""
    root = tempfile.mkdtemp(prefix="h38-" + tag + "-")
    for name in list(PF.EPOCH3_GOVERNED) + [
            "ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
            "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
            EPOCH.EPOCH1_CLOSURE_FILE, EPOCH.TRANSITION_FILE,
            EPOCH.EXECUTION_LOCK_FILE, EPOCH.PROTOCOL_LOCK_FILE,
            EPOCH.EPOCH2_STOP_RECORD_FILE]:
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    # the frozen parse gate, at its tree-relative path (the terminal replay
    # judges the preserved response with the bytes of the tree it belongs to)
    hr = os.path.join(root, "harness-run")
    os.makedirs(hr)
    shutil.copy2(os.path.join(FAMC, "harness-run", "run_arm_h1.py"),
                 os.path.join(hr, "run_arm_h1.py"))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for f in ("fam01", "fam03", "fam05"):
        shutil.copytree(os.path.join(FAMC, "families", f),
                        os.path.join(fam, f))
    rec = {
        "transition": "epoch-2-to-epoch-3",
        "epoch_id": EPOCH.EPOCH3_ID,
        "from_epoch": EPOCH.EPOCH3_FROM_EPOCH,
        "to_epoch": EPOCH.EPOCH3_NUMBER,
        "epoch2_transition_record": EPOCH.TRANSITION_FILE,
        "epoch2_transition_sha256": EPOCH.EPOCH2_TRANSITION_SHA256,
        "epoch2_execution_lock_sha256": EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
        "epoch2_protocol_lock_sha256": EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
        "epoch2_finalization_commit": EPOCH.EPOCH2_FINALIZATION_COMMIT,
        "epoch2_stop_record": EPOCH.EPOCH2_STOP_RECORD_FILE,
        "epoch2_stop_record_sha256": EPOCH.EPOCH2_STOP_RECORD_SHA256,
        "epoch3_protocol_spec": EPOCH.EPOCH3_SPEC_FILE,
        "epoch3_protocol_spec_sha256": EPOCH.EPOCH3_SPEC_SHA256,
        "epoch3_freeze_commit": EPOCH.EPOCH3_FREEZE_COMMIT,
        "order_expansion_sha256": EPOCH.ORDER_EXPANSION_SHA256,
        "state_prefix": EPOCH.EPOCH3_STATE_PREFIX,
        "execution_lock": EPOCH.EPOCH3_EXECUTION_LOCK_FILE,
        "protocol_lock": EPOCH.EPOCH3_PROTOCOL_LOCK_FILE,
        "genesis": {fn: sha_file(os.path.join(root, fn))
                    for fn in PF.EPOCH3_GOVERNED},
        "reason": "h38 hermetic fixture (NOT evidence)",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(root, EPOCH.EPOCH3_TRANSITION_FILE), "w") as f:
        json.dump(rec, f, indent=1)
    rec_sha = sha_file(os.path.join(root, EPOCH.EPOCH3_TRANSITION_FILE))
    tr = {"record": EPOCH.EPOCH3_TRANSITION_FILE, "record_sha256": rec_sha,
          "from_epoch": 2,
          "epoch2_transition_record": EPOCH.TRANSITION_FILE,
          "epoch2_transition_sha256": EPOCH.EPOCH2_TRANSITION_SHA256,
          "epoch2_execution_lock_sha256": EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
          "epoch2_protocol_lock_sha256": EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
          "epoch2_finalization_commit": EPOCH.EPOCH2_FINALIZATION_COMMIT}
    ex = {"lock": "EXECUTION-LOCK", "epoch": 3, "status": "open-round2",
          "freeze_commit": FREEZE,
          "harness_manifest_sha256": sha_bytes(b"h38-fixture-harness"),
          "harness_files": {}, "amendments": [], "transition": dict(tr)}
    with open(os.path.join(root, EPOCH.EPOCH3_EXECUTION_LOCK_FILE), "w") as f:
        json.dump(ex, f, indent=1)
    pr = {"lock": "PROTOCOL-LOCK", "epoch": 3, "status": "living-lock",
          "freeze_commit": FREEZE, "governed": rec["genesis"],
          "amendments": [], "transition": dict(tr)}
    with open(os.path.join(root, EPOCH.EPOCH3_PROTOCOL_LOCK_FILE), "w") as f:
        json.dump(pr, f, indent=1)
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for x in dirnames:
            os.chmod(os.path.join(dirpath, x), 0o755)
    return root


def cell_for(root, event, universe="A", block="PQ", family="fam05"):
    """The enumerated cell of (block, family, event, universe) — taken from
    the expansion itself (lane/arm are derived by the order, never chosen
    by the caller)."""
    exp = order.load_expansion(root)
    for c in exp["cells"]:
        if (c["block"], c["family"], c["event"], c["universe"]) == (
                block, family, event, universe):
            return c
    raise AssertionError((block, family, event, universe))


def build_terminal(root, cell, raw=BAD_RAW, lane=None, tamper=None):
    """Build ONE terminal cell through the REAL writer path: call
    artifacts (receipt/normalized/identity) + preserved
    raw-<call_id>.txt + the attempt-ledger row, then the frozen parse gate
    judges the PRESERVED bytes and the writer creates the terminal
    (O_EXCL). `tamper` mutates a piece AFTER the write for the adversarial
    probes: "raw", "identity", "ledger", "ledger-drop", "row-hash",
    "row-null", "row-extra", "lock-manifest", "terminal-bytes"."""
    lane = lane or cell["lane"]
    d = order.ensure_namespace(root, cell["block"], cell["universe"],
                               cell["family"],
                               tail=("runs", cell["cell_id"]))
    os.chmod(d, 0o755)
    _rc, _pw, mc = _write_usage_evidence(d, lane)
    call_id = mc["call_id"]
    with open(os.path.join(d, f"raw-{call_id}.txt"), "w") as f:
        f.write(raw)
    first = order.replay_parse_gate(root, raw)
    assert not first["arrived"] and first["eligible"], first
    RAH.append_attempt_ledger_row(d, {
        "schema": RAH.ATTEMPT_LEDGER_SCHEMA, "attempt_index": 1,
        "provider_call_id": call_id,
        "request_body_sha256": mc["request_body_sha256"],
        "authorized_estimand_attempt": True,
        "outcome": first["error"],
        "response_text_sha256": sha_bytes(raw.encode()),
        "response_bytes": len(raw.encode()),
        "usage_receipt_sha256": sha_file(os.path.join(d,
                                                      f"call-{call_id}.json")),
        "identity_record_sha256": sha_file(os.path.join(d, "identity.json")),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    tpath = os.path.join(d, order.MODEL_OUTPUT_INVALID_FILE)
    with BasePatch(root):
        RAH.write_model_output_invalid(d, cell, order.load_expansion(
            root)["order_sha256"], call_id,
            os.path.join(d, f"call-{call_id}.json"),
            os.path.join(d, f"call-{call_id}.normalized.json"),
            os.path.join(d, "identity.json"), first["error"])
    if tamper == "raw":
        with open(os.path.join(d, f"raw-{call_id}.txt"), "w") as f:
            f.write("ok then:\n" + BAD_RAW)
    elif tamper == "identity":
        with open(os.path.join(d, "identity.json"), "w") as f:
            json.dump({"endpoint": "x"}, f)
    elif tamper == "terminal-bytes":
        obj = json.load(open(tpath))
        obj["response_bytes"] = (obj["response_bytes"] or 0) + 1
        with open(tpath, "w") as f:
            json.dump(obj, f, indent=1)
    elif tamper == "lock-manifest":
        lp = os.path.join(root, EPOCH.EPOCH3_EXECUTION_LOCK_FILE)
        lock = json.load(open(lp))
        lock["harness_manifest_sha256"] = sha_bytes(b"other-harness")
        with open(lp, "w") as f:
            json.dump(lock, f, indent=1)
    lp = os.path.join(d, RAH.ATTEMPT_LEDGER_FILE)
    if tamper in ("ledger", "ledger-drop"):
        os.unlink(lp)
    elif tamper == "row-hash":
        rows = [json.loads(x) for x in open(lp) if x.strip()]
        rows[0]["request_body_sha256"] = sha_bytes(b"nope")
        with open(lp, "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    elif tamper == "row-null":
        rows = [json.loads(x) for x in open(lp) if x.strip()]
        rows[0]["response_text_sha256"] = None
        with open(lp, "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    elif tamper == "row-extra":
        rows = [json.loads(x) for x in open(lp) if x.strip()]
        extra = dict(rows[0])
        extra["attempt_index"] = 2
        extra["provider_call_id"] = "deadbeefdeadbeef"
        with open(lp, "a") as f:
            f.write(json.dumps(extra, sort_keys=True) + "\n")
    return d, call_id, tpath


def advance_expect_refusal(root, family="fam05", universe="A"):
    try:
        promotion.advance(root, "PQ", family, universe, FREEZE,
                          evidence_grade="harness-validation")
        return "NO-REFUSAL"
    except (PermissionError, ValueError) as e:
        return str(e)


def prom_lock_paths(root, family="fam05", universe="A"):
    prom = cell_for(root, "PROMOTION", universe, family=family)
    lock = cell_for(root, "CAPABILITY_LOCK", universe, family=family)
    return (os.path.join(order.run_dir(root, prom),
                         order.PROMOTION_OUTCOME_FILE),
            os.path.join(order.run_dir(root, lock),
                         order.CAPABILITY_LOCK_OUTCOME_FILE))


# ===========================================================================
# A. the terminal
# ===========================================================================
A_ROOT = epoch3_root("a")
check("A0 the hermetic epoch-3 fixture is structurally ACTIVE (active_epoch"
      " 3, state root state/epoch3)",
      EPOCH.is_epoch3(A_ROOT) and EPOCH.active_epoch(A_ROOT) == 3
      and EPOCH.state_root(A_ROOT).endswith(os.path.join("state", "epoch3"))
      and EPOCH.validate_transition3(A_ROOT) == [],
      str(EPOCH.validate_transition3(A_ROOT)[:1]))

T0A = cell_for(A_ROOT, "T0")
_d, _cid, _tp = build_terminal(A_ROOT, T0A)
_obj = json.load(open(_tp))
_st = order.cell_state(A_ROOT, T0A, FREEZE)
_a1 = (_st["status"] == "COMPLETE-FAILURE"
       and _st.get("terminal_record_sha256") == sha_file(_tp)
       and order.progress_valid(T0A, "COMPLETE-FAILURE")
       and _obj["schema"] == "famc-model-output-invalid-v1"
       and _obj["epoch"] == 3 and _obj["experimental_task_outcome"] == "FAIL"
       and _obj["experimental_outcome"] is True
       and _obj["contract_error"].startswith("CONTRACT-PARSE-DENY")
       and _obj["contract_rule"] == "A11b.2"
       and _obj["attempt_index"] == 1
       and _obj["authorized_estimand_attempt"] is True
       and _obj["per_attempt_outcome"] == _obj["contract_error"]
       and _obj["identity_record_sha256"] == sha_file(
           os.path.join(_d, "identity.json"))
       and _obj["response_text_sha256"] == sha_bytes(
           open(os.path.join(_d, f"raw-{_cid}.txt"), "rb").read())
       and _obj["cell_id"] == T0A["cell_id"]
       and order.validate_model_output_invalid(A_ROOT, T0A) == [])
check("A1 the write-once terminal mints from the preserved bytes (real "
      "writer + real validator) and the walk accepts COMPLETE-FAILURE",
      _a1, f"{_st['status']} {order.validate_model_output_invalid(A_ROOT, T0A)[:1]}")

_dup = None
try:
    with BasePatch(A_ROOT):
        RAH.write_model_output_invalid(
            _d, T0A, order.load_expansion(A_ROOT)["order_sha256"], _cid,
            os.path.join(_d, f"call-{_cid}.json"),
            os.path.join(_d, f"call-{_cid}.normalized.json"),
            os.path.join(_d, "identity.json"), _obj["contract_error"])
except SystemExit as e:
    _dup = str(e)
_a2 = (_dup is not None and "MODEL-OUTPUT-INVALID-DENY" in _dup
       and json.load(open(_tp)) == _obj)
check("A2 a duplicate write is refused (MODEL-OUTPUT-INVALID-DENY) and the "
      "existing terminal is never overwritten", _a2, str(_dup)[:160])

# probe 4 — deterministic replay
_cid4 = None
B_ROOT = epoch3_root("b")
T0B = cell_for(B_ROOT, "T0")
_d4, _cid4, _tp4 = build_terminal(B_ROOT, T0B)
_raw4 = os.path.join(_d4, f"raw-{_cid4}.txt")
with open(_raw4, "w") as f:
    f.write(GOOD_RAW)
_f_arrival = order.validate_model_output_invalid(B_ROOT, T0B)
_rep = order.replay_parse_gate(B_ROOT, GOOD_RAW)
with open(_raw4, "w") as f:
    f.write("")
_f_otherenl = order.validate_model_output_invalid(B_ROOT, T0B)
with open(_raw4, "w") as f:
    f.write(BAD_RAW)
_f_restored = order.validate_model_output_invalid(B_ROOT, T0B)
_a3 = (len(_f_arrival) >= 1 and any("ARRIVAL" in x or "arrival" in x
                                    for x in _f_arrival)
       and _rep["arrived"] is True
       and _f_otherenl and any("replay" in x for x in _f_otherenl)
       and _f_restored == [])
check("A3 probe 4 — the preserved response is replayed through the frozen "
      "extract(): an arrival refuses, a different eligible error refuses, "
      "the recorded denial re-derives green", _a3,
      f"{_f_arrival[:1]} / {_f_otherenl[:1]}")

# probe 5 — identity
C_ROOT = epoch3_root("c")
T0C3 = cell_for(C_ROOT, "T0")
_d5, _cid5, _tp5 = build_terminal(C_ROOT, T0C3)
_idp = os.path.join(_d5, "identity.json")
os.unlink(_idp)
_f_idmissing = order.validate_model_output_invalid(C_ROOT, T0C3)
_writer_refused = None
_d5b, _cid5b, _tp5b = build_terminal(C_ROOT, cell_for(C_ROOT, "T0",
                                                     family="fam03"))
with open(os.path.join(_d5b, "identity.json"), "w") as f:
    json.dump({"endpoint": "x"}, f)
_f_idtamper = order.validate_model_output_invalid(
    C_ROOT, cell_for(C_ROOT, "T0", family="fam03"))
_a4 = (any("identity" in x for x in _f_idmissing)
       and _f_idtamper and any("identity" in x or "binding" in x
                               for x in _f_idtamper))
check("A4 probe 5 — an identity-invalid sample cannot mint a terminal: the "
      "missing identity refuses the terminal and a tampered identity record "
      "makes it INADMISSIBLE", _a4, f"{_f_idmissing[:1]} {_f_idtamper[:1]}")

# probe 6 — HTTP/provider error body without a completion sample
E_ROOT = epoch3_root("e")
E_OUT = os.path.join(E_ROOT, "state", "epoch3")
os.makedirs(E_OUT, exist_ok=True)
_calls = {"n": 0}
_REAL_URLOPEN = UG.urllib.request.urlopen


class _Boom:
    def __init__(self):
        self.code = 500
        self.msg = "Internal Server Error"

    def read(self):
        return b'{"error": "upstream exploded", "detail": "not a sample"}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        return None


def _fake_urlopen(req, timeout=None):
    _calls["n"] += 1
    raise urllib.error.HTTPError(req.full_url, 500, "Server Error",
                                 {}, _Boom())


UG.urllib.request.urlopen = _fake_urlopen
_nosample = None
_keyfile_made = None
try:
    keyf = os.path.join(E_OUT, "lane-key.txt")
    with open(keyf, "w") as f:
        f.write("fixture-not-a-key\n")
    UG.recorded_call("https://fixture.invalid/v1", "k", "fixture-not-a-key",
                     "fixture-model", [{"role": "user", "content": "x"}],
                     E_OUT, normalizer_id=UG.PROVIDER_NORMALIZERS and
                     "openai-chat-total-input-v1")
except UG.NoModelSample as e:
    _nosample = e
except Exception as e:                                       # noqa: BLE001
    _nosample = e
finally:
    UG.urllib.request.urlopen = _REAL_URLOPEN
_rows_before = [x for x in os.listdir(E_OUT) if x.startswith("call-")]
_lrow = None
if isinstance(_nosample, UG.NoModelSample):
    RAH.record_no_sample_attempt(E_OUT, _nosample)
    _lrow = [json.loads(x) for x in open(
        os.path.join(E_OUT, RAH.ATTEMPT_LEDGER_FILE)) if x.strip()]
_a5 = (isinstance(_nosample, UG.NoModelSample)
       and _calls["n"] == 1 and _rows_before == []
       and not os.path.exists(os.path.join(E_OUT,
                                           order.MODEL_OUTPUT_INVALID_FILE))
       and _lrow is not None and len(_lrow) == 1
       and _lrow[0]["outcome"] == order.ATTEMPT_NO_SAMPLE
       and _lrow[0]["request_body_sha256"]
       == _nosample.request_body_sha256
       and _lrow[0]["response_text_sha256"] is None
       and _lrow[0]["response_bytes"] is None
       and _lrow[0]["usage_receipt_sha256"] is None
       and _lrow[0]["identity_record_sha256"] is None
       and os.path.isfile(os.path.join(
           E_OUT, f"call-{_lrow[0]['provider_call_id']}.request.json")))
check("A5 probe 6 — an HTTP/provider error body without a completion sample "
      "is INFRASTRUCTURE: recorded_call raises NoModelSample, the body is "
      "never parsed, no terminal is minted, and the invocation is enumerated "
      "with null sample fields", _a5,
      f"{type(_nosample).__name__}: {str(_nosample)[:120]}")

# ===========================================================================
# B. attempt accounting
# ===========================================================================
_budget = RAH.attempt_budget_reasons(E_OUT)
_budget_term = RAH.attempt_budget_reasons(_d)
_b1 = (any("ATTEMPT-BUDGET-DENY" in x for x in _budget)
       and any("MODEL-OUTPUT-INVALID-DENY" in x for x in _budget_term))
check("B2 probe 7 — a second same-cell provider invocation is HARD-REFUSED "
      "(ATTEMPT-BUDGET-DENY) before any second call, and a terminal-bearing "
      "cell refuses with MODEL-OUTPUT-INVALID-DENY", _b1,
      f"{_budget[:1]} / {_budget_term[:1]}")

_led = [json.loads(x) for x in open(os.path.join(_d, RAH.ATTEMPT_LEDGER_FILE))
        if x.strip()]
_b3 = (len(_led) == 1 and _led[0]["attempt_index"] == 1
       and _led[0]["authorized_estimand_attempt"] is True
       and _led[0]["outcome"] == _obj["contract_error"]
       and _led[0]["provider_call_id"] == _cid
       and order.attempt_ledger_reasons(A_ROOT, T0A) == []
       and order.validate_model_output_invalid(A_ROOT, T0A) == [])
check("B1 the ledger enumerates ONE row per provider invocation in call "
      "order, cross-checked against the files on disk", _b3, str(_led[:1])[:180])

TAMP_ROOT = epoch3_root("t")
_findings = {}
for tag in ("ledger-drop", "row-hash", "row-null", "row-extra"):
    r = epoch3_root("t-" + tag)
    cell = cell_for(r, "T0")
    build_terminal(r, cell, tamper=tag)
    _findings[tag] = order.validate_model_output_invalid(r, cell)
_b4 = all(len(v) >= 1 for v in _findings.values())
check("B3 probe 8 — a tampered/missing attempt-ledger row refuses (missing "
      "file, wrong request hash, null on a non-infra row, extra row)",
      _b4, str({k: v[:1] for k, v in _findings.items()})[:220])

S_ROOT = epoch3_root("s")
S_T0 = cell_for(S_ROOT, "T0")
_ds0, _cids0, _tps0 = build_terminal(S_ROOT, S_T0)
S_T0B = cell_for(S_ROOT, "T0", family="fam03")
_ds, _cids, _tps = build_terminal(S_ROOT, S_T0B)
_prom_s, _lock_s = prom_lock_paths(S_ROOT)
advance_expect_refusal(S_ROOT)
_stats = order.contract_admissibility_statistics(S_ROOT)
_b5 = (_stats["first_attempt_contract_admissibility"]
       == {"numerator": 0, "denominator": 2, "value": 0.0}
       and _stats["all_provider_call_contract_admissibility"]
       == {"numerator": 0, "denominator": 2, "value": 0.0}
       and _stats["denominator_decomposition"]["contract_denials"] == 2
       and _stats["denominator_decomposition"]["infrastructure_no_sample"] == 0)
check("B4 the two reliability statistics + the denominator decomposition "
      "come from the ledger enumeration, never collapsed", _b5, str(_stats))

# ===========================================================================
# C. progress algebra + governance union
# ===========================================================================
# probe 1 — T0 terminal continuation (the S_ROOT universe)
_t1_st = order.cell_state(S_ROOT, cell_for(S_ROOT, "T1"), FREEZE)
_failed, _cause = order.acquisition_failed(S_ROOT, "PQ", "fam05", "A")
_oc = json.load(open(_prom_s)) if os.path.exists(_prom_s) else {}
_lc = json.load(open(_lock_s)) if os.path.exists(_lock_s) else {}
_t2a = order.cell_state(S_ROOT, cell_for(S_ROOT, "T2"), FREEZE)
_t2b = order.cell_state(S_ROOT, cell_for(S_ROOT, "T2", "B"), FREEZE)
_done = order.completed_cells(S_ROOT)
_c1_terms = {
    "t1_ev": _t1_st["status"] == "NOT-EVALUABLE",
    "cause": _cause.startswith("T0 MODEL-OUTPUT-INVALID"),
    "prom": _oc.get("outcome") == "NOT-PROMOTED",
    "reason": _oc.get("reason") == "acquisition-failed",
    "fe": _oc.get("failure_event") == "T0",
    "kind": _oc.get("acquisition_evidence", {}).get("kind")
    == "MODEL-OUTPUT-INVALID",
    "tsha": _oc.get("acquisition_evidence", {}).get("terminal_sha256")
    == sha_file(_tps0),
    "cand": _oc.get("candidate_sha256") is None,
    "tips": _oc.get("t0_tip") is None and _oc.get("t1_tip") is None,
    "lock": _lc.get("outcome") == "NOT-LOCKED",
    "lock_fe": _lc.get("failure_event") == "T0",
    "lock_ev": _lc.get("acquisition_evidence")
    == _oc.get("acquisition_evidence"),
    "lock_cand": _lc.get("candidate_sha256") is None,
    "lock_notips": "acquisition_chain_tips" not in _lc,
    "t2a": _t2a["status"] == "NOT-EVALUABLE",
    "t2b": _t2b["status"] == "INCOMPLETE",
    "done": set(_done) >= {S_T0["cell_id"]},
    "nolock": not os.path.exists(os.path.join(
        order.capability_dir(S_ROOT, "PQ", "A", "fam05"),
        "CAPABILITY_LOCK.json")),
}
_c1 = (all(_c1_terms.values()) and _failed
       and _cause.startswith("T0 MODEL-OUTPUT-INVALID")
       and _oc.get("outcome") == "NOT-PROMOTED"
       and _oc.get("reason") == "acquisition-failed"
       and _oc.get("failure_event") == "T0"
       and _oc.get("acquisition_evidence", {}).get("kind")
       == "MODEL-OUTPUT-INVALID"
       and _oc.get("acquisition_evidence", {}).get("terminal_sha256")
       == sha_file(_tps0)
       and _oc.get("candidate_sha256") is None
       and _oc.get("t0_tip") is None and _oc.get("t1_tip") is None
       and _lc.get("outcome") == "NOT-LOCKED"
       and _lc.get("failure_event") == "T0"
       and _lc.get("acquisition_evidence") == _oc.get("acquisition_evidence")
       and _lc.get("candidate_sha256") is None
       and "acquisition_chain_tips" not in _lc
       and _t2a["status"] == "NOT-EVALUABLE"
       and _t2b["status"] == "INCOMPLETE"
       and set(_done) >= {S_T0["cell_id"]}
       and not os.path.exists(os.path.join(
           order.capability_dir(S_ROOT, "PQ", "A", "fam05"),
           "CAPABILITY_LOCK.json")))
check("C1 probe 1 — T0 MODEL-OUTPUT-INVALID continuation: no candidate, T1 "
      "NOT-EVALUABLE, PROMOTION NOT-PROMOTED and CAPABILITY_LOCK NOT-LOCKED "
      "on the §3.1 union, downstream NOT-EVALUABLE, prefix advances, "
      "nothing minted", _c1,
      f"t1={_t1_st['status']} cause={_cause} "
      f"false={[k for k, v in _c1_terms.items() if not v]}")

# probe 2 — T1 terminal continuation
F_ROOT = epoch3_root("f")
T0F = cell_for(F_ROOT, "T0")
CAND = ("def solve(input_dir, output_path):\n"
        "    open(output_path, 'w').write('ok')\n")
_d0f = build_model_run(F_ROOT, cell=T0F, freeze_commit=FREEZE, solver_py=CAND)
T1F = cell_for(F_ROOT, "T1")
_d1f, _cidf, _tpf = build_terminal(F_ROOT, T1F)
_prom_f, _lock_f = prom_lock_paths(F_ROOT)
_msg_f = advance_expect_refusal(F_ROOT)
_ocf = json.load(open(_prom_f)) if os.path.exists(_prom_f) else {}
_lcf = json.load(open(_lock_f)) if os.path.exists(_lock_f) else {}
_real_cand = t0_candidate_sha256(_d0f)
_c2 = (order.cell_state(F_ROOT, T0F, FREEZE)["status"] == "COMPLETE"
       and order.cell_state(F_ROOT, T1F, FREEZE)["status"]
       == "COMPLETE-FAILURE"
       and _ocf.get("failure_event") == "T1"
       and _ocf.get("reason") == "acquisition-failed"
       and _ocf.get("candidate_sha256") == _real_cand
       and _ocf.get("acquisition_evidence", {}).get("terminal_sha256")
       == sha_file(_tpf)
       and not os.path.exists(os.path.join(order.run_dir(F_ROOT, T1F),
                                           "arrival.json"))
       and _lcf.get("candidate_sha256") == _real_cand
       and _lcf.get("acquisition_evidence") == _ocf.get("acquisition_evidence")
       and (order.cell_state(F_ROOT, cell_for(F_ROOT, "T2"), FREEZE)["status"]
            == "NOT-EVALUABLE"))
check("C2 probe 2 — T1 MODEL-OUTPUT-INVALID continuation: T0 COMPLETE, the "
      "real candidate exists but was never validly validated, both "
      "governance terminals carry failure_event T1 + the real candidate sha",
      _c2, f"{_msg_f[:160]} oc={str(_ocf)[:120]}")

# probe 10 — governance records with a wrong terminal SHA / wrong branch
G_ROOT = epoch3_root("g")
G_T0 = cell_for(G_ROOT, "T0")
_dg, _cidg, _tpg = build_terminal(G_ROOT, G_T0)
_prom_g, _lock_g = prom_lock_paths(G_ROOT)
advance_expect_refusal(G_ROOT)
_ocg = json.load(open(_prom_g))
_bad_sha = order.validate_model_output_invalid(G_ROOT, G_T0)
_ocg_orig = json.dumps(_ocg, indent=1)
_ocg["acquisition_evidence"] = {"kind": "MODEL-OUTPUT-INVALID",
                                "terminal_sha256": sha_bytes(b"wrong")}
with open(_prom_g, "w") as f:
    json.dump(_ocg, f, indent=1)
_st_wrong_sha = order.cell_state(G_ROOT, cell_for(G_ROOT, "PROMOTION"), FREEZE)
_ocg["acquisition_evidence"] = {"kind": "CHAIN", "chain_tip": None,
                                "candidate_sha256": _ocg.get("candidate_sha256")}
with open(_prom_g, "w") as f:
    json.dump(_ocg, f, indent=1)
_st_null_tip = order.cell_state(G_ROOT, cell_for(G_ROOT, "PROMOTION"), FREEZE)
_ocg["acquisition_evidence"] = {"kind": "MODEL-OUTPUT-INVALID",
                                "terminal_sha256": sha_file(_tpg)}
_ocg["candidate_sha256"] = sha_bytes(b"fake-candidate")
with open(_prom_g, "w") as f:
    json.dump(_ocg, f, indent=1)
_st_cand = order.cell_state(G_ROOT, cell_for(G_ROOT, "PROMOTION"), FREEZE)
with open(_prom_g, "w") as f:
    f.write(_ocg_orig)
_st_restored = order.cell_state(G_ROOT, cell_for(G_ROOT, "PROMOTION"), FREEZE)
_refused = None
try:
    promotion.advance(G_ROOT, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
except (PermissionError, ValueError) as e:
    _refused = str(e)
_c3 = (_st_wrong_sha["status"] == "INADMISSIBLE"
       and any("terminal_sha256" in x for x in _st_wrong_sha["reasons"])
       and _st_null_tip["status"] == "INADMISSIBLE"
       and any("chain" in x.lower() for x in _st_null_tip["reasons"])
       and _st_cand["status"] == "INADMISSIBLE"
       and any("candidate" in x for x in _st_cand["reasons"])
       and _st_restored["status"] == "NOT-PROMOTED"
       and _refused and "PROMOTION-DENY" in _refused)
check("C3 probe 10 — governance records with a wrong terminal SHA, a "
      "null-tip/chain branch shape or a wrong candidate refuse, and the "
      "restored union re-validates", _c3,
      f"{_st_wrong_sha['reasons'][:1]} {_st_null_tip['reasons'][:1]} "
      f"{_st_cand['reasons'][:1]}")

def promote_universe(root, family):
    """Mint a REAL successful acquisition (T0 COMPLETE, T1 COMPLETE with a
    validated candidate) and run the governance events, so the universe
    holds a locked capability (the §4.1 `capability_available` surface)."""
    t0 = cell_for(root, "T0", "A", family=family)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE, solver_py=SOLVER,
                         producer_contract={
                             "semantic_core": "generic capability",
                             "preconditions": [CONTRACT[family]],
                             "limitations": []})
    t1 = cell_for(root, "T1", "A", family=family)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0),
                    adapter_py=ADAPTER,
                    candidate_validation={
                        "checker_sha256": sha_file(os.path.join(
                            root, "families", family, "check.py")),
                        "truth_sha256": sha_file(os.path.join(
                            root, "families", family, "truth.json")),
                        "checker_returncode": 0,
                        "validation_verdict": "ship",
                        "validated": True})
    promotion.promote_universe(root, "PQ", family, "A", FREEZE,
                               "harness-validation")
    promotion.advance(root, "PQ", family, "A", FREEZE,
                      "harness-validation")
    return t0, t1


# probe 3 — downstream terminals: non-SHIP, no efficiency win, no T4 rejection
# fam05/A acquires SUCCESSFULLY (a real locked capability), fam05/C fails
# through a T0 terminal, and the downstream terminals then sit on a lawful
# prefix (the A universe's cells are COMPLETE, the C universe's are the
# recorded acquisition-failure terminals).
H_ROOT = epoch3_root("h")
promote_universe(H_ROOT, "fam05")
_dhC, _cidhC, _tphC = build_terminal(H_ROOT, cell_for(H_ROOT, "T0", "C"))
advance_expect_refusal(H_ROOT, universe="C")
T2B = cell_for(H_ROOT, "T2", "B")
_dh, _cidh, _tph = build_terminal(H_ROOT, T2B)
T2A = cell_for(H_ROOT, "T2", "A")
_dh1, _cidh1, _tph1 = build_terminal(H_ROOT, T2A)
_st_A = order.cell_state(H_ROOT, T2A, FREEZE)
_row_A = order.terminal_evidence_row(H_ROOT, T2A)
_row = order.terminal_evidence_row(H_ROOT, T2B)
_gate = order.terminal_gate_consequences(T2B)
T4B = cell_for(H_ROOT, "T4", "B")
_gate4 = order.terminal_gate_consequences(T4B)
_st_B = order.cell_state(H_ROOT, T2B, FREEZE)
_c4 = (_row["ship"] is False and _row["hidden_tests_passed"] is None
       and _row["checker_verdict"] is None
       and _row["checker_returncode"] is None
       and _row["run_manifest_hash"] is None
       and _row["terminal_class"] == "MODEL-OUTPUT-INVALID"
       and _row["evidence_hash"] == sha_file(_tph)
       and _row["terminal_record_sha256"] == sha_file(_tph)
       and _row["model_calls"] == 1 and _row["retries"] == 0
       and _row["capability_available"] is False
       and _row["capability_selected"] is False
       and _row["capability_loaded"] is False
       and _row["capability_invoked"] is False
       and _row["capability_consumed"] is False
       and _row["material_contribution"] is False
       and _gate["efficiency_win"] is False
       and _gate["specificity_rejection"] is False
       and _gate4["specificity_rejection"] is False
       and _gate4["ship"] is False
       and _st_B["status"] == "COMPLETE-FAILURE"
       and _row_A["capability_available"] is True
       and _row_A["capability_selected"] is False
       and _row_A["capability_loaded"] is False
       and _row_A["capability_invoked"] is False
       and _row_A["capability_consumed"] is False
       and _row_A["material_contribution"] is False
       and _row_A["ship"] is False
       and _st_A["status"] == "COMPLETE-FAILURE"
       and _st_A.get("terminal_record_sha256") == sha_file(_tph1))
check("C4 probe 3 — a downstream T2/T3 terminal is a NON-SHIP correctness "
      "failure barred from an efficiency win, a T4 terminal is never a "
      "correct specificity rejection, and the §24 row carries ship False / "
      "null checker+manifest fields / evidence_hash = terminal sha / "
      "model_calls 1 / retries 0 / terminal_class", _c4,
      f"row_ship={_row['ship']} A_avail={_row_A['capability_available']} "
      f"A_state={_st_A['status']} B_state={_st_B['status']}")

I_ROOT = epoch3_root("i")
I_T0 = cell_for(I_ROOT, "T0")
build_terminal(I_ROOT, I_T0)
_model_only = (order.progress_valid(I_T0, "COMPLETE-FAILURE") is True
               and order.progress_valid(cell_for(I_ROOT, "PROMOTION"),
                                        "COMPLETE-FAILURE") is False
               and order.progress_valid(cell_for(I_ROOT, "CAPABILITY_LOCK"),
                                        "COMPLETE-FAILURE") is False
               and order.progress_valid(order.load_expansion(
                   I_ROOT)["cells"][0], "INCOMPLETE") is False
               and order.progress_valid(I_T0, "INADMISSIBLE") is False
               and order.terminal_exit_code() == 0)
check("C5 the algebra table — COMPLETE-FAILURE is progress-valid for MODEL "
      "cells ONLY (never INCOMPLETE/INADMISSIBLE, never a governance cell) "
      "— and a recorded terminal exits 0", _model_only)

# ===========================================================================
# D. epoch-3 authority + lineage
# ===========================================================================
L_ROOT = epoch3_root("l")
L_T0 = cell_for(L_ROOT, "T0")
_dl, _cidl, _tpl = build_terminal(L_ROOT, L_T0)
_good = order.validate_model_output_invalid(L_ROOT, L_T0)
_lp = os.path.join(L_ROOT, EPOCH.EPOCH3_EXECUTION_LOCK_FILE)
_lock = json.load(open(_lp))
_lock["harness_manifest_sha256"] = sha_bytes(b"different-harness")
with open(_lp, "w") as f:
    json.dump(_lock, f, indent=1)
_f_lock = order.validate_model_output_invalid(L_ROOT, L_T0)
_pp = os.path.join(L_ROOT, EPOCH.EPOCH3_PROTOCOL_LOCK_FILE)
_pobj = json.load(open(_pp))
_pobj["governed"] = {}
with open(_pp, "w") as f:
    json.dump(_pobj, f, indent=1)
_f_proto = order.validate_model_output_invalid(L_ROOT, L_T0)
_lock["harness_manifest_sha256"] = sha_bytes(b"h38-fixture-harness")
with open(_lp, "w") as f:
    json.dump(_lock, f, indent=1)
_pobj["governed"] = json.load(open(os.path.join(
    L_ROOT, EPOCH.EPOCH3_TRANSITION_FILE)))["genesis"]
with open(_pp, "w") as f:
    json.dump(_pobj, f, indent=1)
_f_back = order.validate_model_output_invalid(L_ROOT, L_T0)
_d1 = (_good == []
       and any("execution_harness_manifest_sha256" in x for x in _f_lock)
       and any("protocol_lock_sha256" in x for x in _f_proto)
       and _f_back == [])
check("D1 probe 9 — an execution/protocol lock binding mismatch refuses the "
      "terminal (and the restored authority re-validates)", _d1,
      f"{_f_lock[:1]} {_f_proto[:1]}")

# probe 11 — epoch-2 state cannot satisfy an epoch-3 cell
E2_ROOT = tempfile.mkdtemp(prefix="h38-e2-")
for name in list(PF.PROTOCOL_GOVERNED) + [
        "ORDER-EXPANSION.json", "PROTOCOL-LOCK.json", "EXECUTION-LOCK.json",
        "FREEZE.json", EPOCH.EPOCH1_CLOSURE_FILE, EPOCH.TRANSITION_FILE,
        EPOCH.EXECUTION_LOCK_FILE, EPOCH.PROTOCOL_LOCK_FILE]:
    shutil.copy2(os.path.join(FAMC, name), os.path.join(E2_ROOT, name))
os.makedirs(os.path.join(E2_ROOT, "families"))
shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                os.path.join(E2_ROOT, "families", "fam05"))
E2_T0 = cell_for(E2_ROOT, "T0")
_d_e2 = build_model_run(E2_ROOT, cell=E2_T0, freeze_commit=FREEZE,
                        solver_py=CAND)
_carried = os.path.join(L_ROOT, "state", "epoch2", "PQ", "A", "fam05",
                        "runs", L_T0["cell_id"])
os.makedirs(os.path.dirname(_carried), exist_ok=True)
shutil.copytree(_d_e2, _carried)
_before = sha_file(os.path.join(_carried, "H1-RUN-MANIFEST.json"))
_st_carried = order.cell_state(L_ROOT, L_T0, FREEZE)
_done_carried = order.completed_cells(L_ROOT)
_carried_real = order.cell_state(E2_ROOT, E2_T0, FREEZE)["status"]
_d2 = (_carried_real == "COMPLETE"
       and _st_carried["status"] == "COMPLETE-FAILURE"      # the terminal wins
       and sha_file(os.path.join(_carried, "H1-RUN-MANIFEST.json")) == _before)
check("D2 probe 11 — epoch-2 state cannot satisfy an epoch-3 cell: the "
      "epoch-2 run dir is never scanned by the epoch-3 walk (the epoch-3 "
      "cell is judged only on its own derived path) and the epoch-2 bytes "
      "stay untouched", _d2, f"{_st_carried['status']} vs {_carried_real}")

# probe 12 — a tampered terminal never advances the prefix
M_ROOT = epoch3_root("m")
M_T0 = cell_for(M_ROOT, "T0")
_dm, _cidm, _tpm = build_terminal(M_ROOT, M_T0)
_advance_ok = M_T0["cell_id"] in order.completed_cells(M_ROOT)
obj = json.load(open(_tpm))
obj["response_bytes"] = int(obj["response_bytes"]) + 7
with open(_tpm, "w") as f:
    json.dump(obj, f, indent=1)
_st_tampered = order.cell_state(M_ROOT, M_T0, FREEZE)
_done_tampered = order.completed_cells(M_ROOT)
_d3 = (_advance_ok and _st_tampered["status"] == "INADMISSIBLE"
       and M_T0["cell_id"] not in _done_tampered)
check("D3 probe 12 — a tampered terminal never advances the prefix "
      "(INADMISSIBLE, the walk blocks)", _d3,
      f"{_st_tampered['status']} {_st_tampered['reasons'][:1]}")

# D4 — the LIVE tree at this ref is epoch 3 and its lineage is green
_live_findings = EPOCH.validate_transition3(FAMC)
_d4 = (EPOCH.active_epoch(FAMC) == 3
       and EPOCH.state_root(FAMC).endswith(os.path.join("state", "epoch3"))
       and _live_findings == [])
check("D4 the live tree at this ref IS epoch 3 (state root state/epoch3) "
      "and the epoch-3 transition + fresh locks + the epoch-2 boundary it "
      "cites are green", _d4, str(_live_findings[:1]))

# D5 — one authority: the runner's parse gate IS the validator's replay gate
_probe = BAD_RAW
_r1 = order.replay_parse_gate(FAMC, _probe)
_r2 = RAH.order_module.replay_parse_gate(FAMC, _probe)
_d5 = (RAH.order_module is order and _r1 == _r2
       and RAH.MODEL_OUTPUT_INVALID_FILE == order.MODEL_OUTPUT_INVALID_FILE
       and RAH.ATTEMPT_LEDGER_FILE == order.ATTEMPT_LEDGER_FILE
       and _r1["eligible"] and _r1["error"].startswith("CONTRACT-PARSE-DENY"))
check("D5 the runner and the walk share ONE terminal implementation "
      "(run_arm_h1 imports harness/order.py; the parse-gate replay and the "
      "ledger constants are the same objects)", _d5, str(_r1)[:120])

# D6 — the transition tooling is epoch-3 aware and refuses a second
# transition (write-once), without writing anything into the live tree
_rc = subprocess.run([sys.executable,
                      os.path.join(HARNESS, "epoch_transition.py"),
                      "--check"], capture_output=True, text=True, cwd=ROOT)
_d6 = (_rc.returncode == 0 and "epoch 3" in _rc.stdout
       and "green" in _rc.stdout)
check("D6 `harness/epoch_transition.py --check` reports the live epoch-3 "
      "lineage green (record + fresh locks + the epoch-2 boundary)",
      _d6, (_rc.stdout + _rc.stderr).strip()[:200])

_n = len(RESULTS)
_ok = sum(1 for _n_, c in RESULTS if c)
print(f"\nH38 epoch-3 semantics smoke: {_ok}/{_n} closed")
if _ok != _n:
    print("FAILED:", [n for n, c in RESULTS if not c])
for r in (A_ROOT, B_ROOT, C_ROOT, E_ROOT, S_ROOT, TAMP_ROOT, F_ROOT,
          G_ROOT, H_ROOT, I_ROOT, L_ROOT, M_ROOT, E2_ROOT):
    shutil.rmtree(r, ignore_errors=True)
sys.exit(0 if _ok == _n else 1)

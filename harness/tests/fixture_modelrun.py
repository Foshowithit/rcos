#!/usr/bin/env python3
"""Hermetic, GENUINELY ELIGIBLE model-run fixture (A12.0 test support).

Audit round 2 made two classes of run INADMISSIBLE that earlier smokes used
as fixtures: a wired run with no usage receipt (ZERO-WORK) and a wired run
whose arrival decision / reuse ledger / identity / request binding are
absent. A fixture that the production classifier rejects cannot prove
anything about the production classifier, so this module builds a run
through the REAL writers only:

  * `usage.write_normalized_usage` (immutable normalized artifact)
  * `identity.record_identity` (+ `verify_identity_binding`)
  * `usage.verify_request_binding` / `verify_adapter_binding`
  * `reuse_log.write_record` (full PREREG §12 field set)
  * `chain.Chain` (rooted genesis + evaluator + exactly one final grade)
  * `order.ensure_namespace` (component-wise 0755 namespace)

It is a FIXTURE, not evidence: the receipt's tag says so, no provider call
is made, and nothing here is written under a real universe's runs/ tree
except inside the caller's throwaway root.

Public entry point:

    build_model_run(root, *, cell, freeze_commit, verdict="ship",
                    decision="fresh", solver_py=None, capability=None,
                    reuse_overrides=None, manifest_overrides=None) -> run_dir
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import chain as CH            # noqa: E402
import identity as ID         # noqa: E402
import order                  # noqa: E402
import reuse_log as RL        # noqa: E402
import usage as UG            # noqa: E402
from run_arm_h1 import LANES  # noqa: E402

# Positive-work usage: 1500 total prompt tokens, 400 cached -> 1100 uncached,
# 250 output -> primary_work 1350. ZERO-WORK (primary_work <= 0) must never
# be the accidental shape of a fixture.
USAGE_RAW = {"prompt_tokens": 1500, "completion_tokens": 250,
             "total_tokens": 1750,
             "prompt_tokens_details": {"cached_tokens": 400}}
GEN_PARAMS = {"temperature": 0, "max_tokens": 16, "top_p": 1}
MESSAGES = [{"role": "user", "content": "FIXTURE-ACK"}]
DEFAULT_SOLVER = ("def solve(input_dir, output_path):\n"
                  "    import json, os\n"
                  "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
                  "              open(output_path, 'w'))\n")


def _write_usage_evidence(d, lane):
    """Receipt -> normalized artifact -> identity, all cross-bound. Returns
    (receipt_basename, primary_work, model_call_payload): the payload is the
    production-shaped model-call link content (same keys the production
    _wire_chain binds), so the fixture chain commits the identity bytes,
    the echoed model, and the usage metrics at capture time."""
    spec = LANES[lane]
    body = dict(GEN_PARAMS)
    body.update({"model": spec["model"], "messages": MESSAGES})
    blob = json.dumps(body).encode()
    call_id = hashlib.sha256(
        f"{spec['base']}|{spec['model']}|{cell_salt()}".encode()).hexdigest()[:16]
    req_name = f"call-{call_id}.request.json"
    with open(os.path.join(d, req_name), "wb") as f:
        f.write(blob)
    receipt = {"call_id": call_id, "tag": "fixture_modelrun (NOT evidence)",
               "endpoint": spec["base"], "model_requested": spec["model"],
               "wall_s": 0.0,
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
               "request_body_sha256": hashlib.sha256(blob).hexdigest(),
               "request_body_file": req_name,
               "request_body_file_sha256": hashlib.sha256(blob).hexdigest(),
               "usage_raw": USAGE_RAW,
               "usage_raw_sha256": hashlib.sha256(
                   json.dumps(USAGE_RAW, sort_keys=True).encode()).hexdigest(),
               "normalizer_id": spec["normalizer"],
               "normalizer_version": UG.NORMALIZER_VERSION,
               "normalizer_rule": "fixture_modelrun: hermetic, not evidence"}
    rp = os.path.join(d, f"call-{call_id}.json")
    with open(rp, "w") as f:
        json.dump(receipt, f, indent=1)
    nu = UG.write_normalized_usage(rp)
    provider_obj = {"id": f"fixture-{lane.lower()}-{call_id}",
                    "model": spec["echo_acceptable"][0],
                    "created": int(time.time()), "usage": USAGE_RAW,
                    "choices": [{"message": {"content": "FIXTURE-ACK"}}]}
    idp = ID.record_identity(d, spec["base"], spec["model"], provider_obj,
                             extra_params=GEN_PARAMS,
                             tag="fixture_modelrun (NOT evidence)",
                             request_body_sha256=receipt[
                                 "request_body_sha256"],
                             messages=MESSAGES)
    ID.verify_identity_binding(idp, rp)
    UG.verify_request_binding(rp, idp)
    UG.verify_adapter_binding(receipt["normalizer_id"], lane=lane,
                              receipt=receipt)
    nu_obj = json.load(open(nu))
    pw = nu_obj["primary_work"]

    def _sha_file(p):
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    mc = {"call_id": call_id, "tag": "fixture_modelrun (NOT evidence)",
          "model_requested": spec["model"], "endpoint": spec["base"],
          "receipt_file": os.path.basename(rp),
          "receipt_sha256": _sha_file(rp),
          "usage_raw_sha256": receipt["usage_raw_sha256"],
          "request_body_sha256": receipt["request_body_sha256"],
          "provider_response_id": provider_obj["id"],
          "model_echoed": provider_obj["model"],
          "generation_params": dict(GEN_PARAMS),
          "normalized_file": os.path.basename(nu),
          "normalized_sha256": _sha_file(nu),
          "primary_work": nu_obj["primary_work"],
          "input_tokens_uncached": nu_obj["input_tokens_uncached"],
          "output_tokens": nu_obj["output_tokens"],
          "cached_tokens": nu_obj["cached_tokens"],
          "call_count": 1,
          "identity_file": os.path.basename(idp),
          "identity_sha256": _sha_file(idp),
          "identity_prereg_family": spec["family"]}
    return os.path.basename(rp), pw, mc


def cell_salt():
    return f"{time.time():.6f}"


def _clean_run_dir(d):
    """Idempotent rebuild: remove fixture files (never a symlinked parent)."""
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.islink(p) or os.path.isfile(p):
            os.unlink(p)


# Producer-authored capability contracts (A12c slice B / B5 — test support
# ONLY, NOT evidence). The offline fixture cannot have a real model author
# a contract, so the stand-in declares this independently written text:
# paraphrased here from the families' visible task surfaces, in our own
# words, never copied from hidden K.md — and the stand-in never reads
# K.md at all (no hidden-contract reader lives in this module: the real
# producer authors its own words from visible information, and the
# K.md-mutation-invariance invariant requires consumer bytes to hold
# still when hidden wording changes). Shapes mirror the retired reader
# (non-empty core, non-empty preconditions, empty limitations for all six
# families, so every default lock stays non-discriminating exactly as
# before). Callers testing a limitation-carrying variant pass an explicit
# `producer_contract=` declaration instead.
PRODUCER_CONTRACTS = {
    "fam01": (
        "Clean up flat data rows: treat every row as a single record, "
        "turn dollar figures into integer cents, expand tag strings "
        "into tag lists, and return uniform records carrying an id, a "
        "name, a cent amount, and tags, in the same order as the input.",
        ["Every input row stands for one record; rolled-up summary rows "
         "are excluded.",
         "Money values are ordinary US-dollar decimals with a single "
         "currency throughout.",
         "Any tags present arrive as strings joined by a delimiter."],
        []),
    "fam02": (
        "Pull every page of a paged listing: chase the next-page cursor "
        "until it runs out, retry briefly on hiccups, and join all "
        "fetched entries into one collection.",
        ["No entry shows up on more than one page.",
         "Each task uses one stable response shape and one steady paging "
         "marker.",
         "Any hiccup is short-lived and announced up front.",
         "A task-supplied duplicate policy never widens this: "
         "overlapping pages stay out of scope no matter what a POLICY "
         "file says."],
        []),
    "fam03": (
        "Deduplicate an event window: tally the arrivals, fold exact "
        "repeats into shared identity buckets, and report the overall "
        "count, the distinct count, and how many were dropped.",
        ["A repeat means the same happening was seen twice, never two "
         "separate happenings or a status change.",
         "Each task spells out its own identity rule in its prompt, and "
         "that rule does not shift mid-task."],
        []),
    "fam04": (
        "Check a directed graph for cycles and, when it is clean, list "
        "its nodes in a valid execution order.",
        ["The caller guarantees the graph has no cycles; this step "
         "double-checks that promise instead of finding cycles.",
         "Every edge means its tail must come before its head."],
        []),
    "fam05": (
        "Audit a file listing: measure every named file on disk and "
        "match its byte count and digest against the listing, then file "
        "each entry as good or bad.",
        ["The listing follows the v1 layout of on-disk paths plus byte "
         "counts plus digests.",
         "Each named file sits on local disk and can be opened for "
         "reading."],
        []),
    "fam06": (
        "Reconcile two ledgers: pair rows by identifier, then call out "
        "the pairs that agree, the rows missing on one side, and the "
        "rows whose amounts disagree, quoting both figures.",
        ["The two sources count in the same units.",
         "Identifiers repeat nowhere inside either source."],
        []),
}


def _fixture_evidence_sha(role, cell_id):
    """Deterministic fixture evaluator-evidence sha: namespaced by role and
    cell so T0/T1 links differ and identical acquisitions reproduce. These
    are fixture placeholders (no host checker runs on an acquisition
    fixture), but they are real non-null 64-hex evidence shas, stable and
    committed in the chain at capture time."""
    return hashlib.sha256(json.dumps(
        {"fixture": "fixture_modelrun", "role": role, "cell_id": cell_id},
        sort_keys=True).encode()).hexdigest()


def t0_candidate_sha256(t0_run_dir):
    """Read the frozen T0 candidate sha from a built T0 run's arrival
    (the sha of its execution_payload.solver_py bytes). Positive-path
    builders thread this into the T1 build so the pair models the
    production lifecycle (T1 sees the exact candidate); a T1 built
    without it models a standalone fresh solve, which SHIPs but can
    never promote (A12b.2 fail closed)."""
    arrival = json.load(open(os.path.join(t0_run_dir, "arrival.json")))
    src = (arrival.get("execution_payload") or {}).get("solver_py")
    if not isinstance(src, str) or not src.strip():
        raise PermissionError("fixture: T0 arrival carries no candidate")
    return hashlib.sha256(src.encode()).hexdigest()


def build_model_run(root, *, cell, freeze_commit, verdict="ship",
                    decision="fresh", solver_py=None, capability=None,
                    reuse_overrides=None, manifest_overrides=None,
                    validates_candidate=None, adapter_py=None,
                    candidate_validation=None, producer_contract=None):
    """Build ONE hermetic, production-eligible model-run cell. Returns the
    derived run directory. `cell` is an expansion cell (or any dict with the
    same keys). Raises on any evidence defect (fail closed).

    `validates_candidate`: the sha256 of the frozen T0 candidate this T1
    saw and executed (the production T1 prompt's candidate-validation
    block + chain event, modeled here). T1-only; when given, the T1
    arrival declares the candidate and the T1 chain records exactly one
    candidate-validation event (executed == candidate: the stand-in
    models an adapter that ran the exact candidate bytes). When absent,
    the T1 is a standalone fresh solve: it still SHIPs, but promotion
    refuses it (A12b.2 fail closed).

    A12c: the chain event carries all nine host-checker keys
    (candidate_sha256, executed_sha256, adapter_sha256,
    candidate_output_sha256, checker_sha256, truth_sha256,
    checker_returncode, validation_verdict, validated). `adapter_py`
    supplies the T1 adapter bytes whose sha256 is committed as
    adapter_sha256 (D4: executed, not merely hashed); when omitted the
    stand-in falls back to this run's own solver bytes so pre-A12c
    callers stay green. `candidate_validation` optionally overrides any
    of the nine values with real host-checker evidence (the A12c N7
    positive control threads real checker shas/rc/verdict here).

    `producer_contract`: an explicit producer declaration
    {"semantic_core": str, "preconditions": [str, ...], "limitations":
    [str, ...]} for callers testing a non-default contract (e.g. a
    limitation-carrying variant). When absent, the stand-in declares its
    independently written per-family text (PRODUCER_CONTRACTS) — never
    hidden K.md wording."""
    d = order.ensure_namespace(root, cell["block"], cell["universe"],
                               cell["family"], tail=("runs", cell["cell_id"]))
    _clean_run_dir(d)
    if validates_candidate is not None and cell.get("event") != "T1":
        raise ValueError("fixture misuse: validates_candidate is T1-only "
                         f"(got event {cell.get('event')!r})")
    if validates_candidate is not None and (
            not isinstance(validates_candidate, str)
            or len(validates_candidate) != 64):
        raise ValueError("fixture misuse: validates_candidate must be the "
                         "64-hex frozen T0 candidate sha256")
    if validates_candidate is not None and decision != "fresh":
        raise ValueError("fixture misuse: validates_candidate models a "
                         "fresh validating T1 (use_capability carries no "
                         "solver adapter)")
    lane = cell["lane"]
    receipt_name, primary_work, model_call = _write_usage_evidence(d, lane)

    # ---- arrival: the unified contract, decision-driven -------------------
    if decision == "use_capability":
        payload = {"field_map": {"path": "path", "size": "size",
                                 "sha256": "sha256"},
                   "records": {}}
    else:
        payload = {"solver_py": solver_py or DEFAULT_SOLVER}
        # A12b.2: a validating T1 declares the frozen candidate it saw
        # (the production T1 arrival carries the candidate-validation
        # declaration alongside its own fresh solver).
        # A12c D1: the production T1 arrival additionally carries
        # `adapter_py` (frozen ABI python3 adapter.py <task_dir>
        # <out_input_dir>); the stand-in declares it too when given.
        if validates_candidate is not None:
            payload["candidate_sha256"] = validates_candidate
            if adapter_py is not None:
                if not (isinstance(adapter_py, str) and adapter_py.strip()):
                    raise ValueError("fixture misuse: adapter_py must be a "
                                     "nonempty python source string")
                payload["adapter_py"] = adapter_py
        # A12b.1/AC6b: the producer stand-in declares its capability
        # contract in its OWN arrival payload (independently written
        # stand-in text, or the caller's explicit `producer_contract=`
        # declaration). The promotion controller sources the receipt/lock
        # contract SOLELY from this declaration — never by parsing
        # hidden K.md — and the order.py governance cross-check compares
        # the receipt against this same declaration verbatim.
        if producer_contract is not None:
            if (not isinstance(producer_contract, dict)
                    or not isinstance(
                        producer_contract.get("semantic_core"), str)
                    or not producer_contract["semantic_core"].strip()
                    or not isinstance(
                        producer_contract.get("preconditions"), list)
                    or not producer_contract["preconditions"]
                    or not all(isinstance(x, str) and x.strip()
                               for x in producer_contract["preconditions"])
                    or not isinstance(
                        producer_contract.get("limitations"), list)
                    or not all(isinstance(x, str)
                               for x in producer_contract["limitations"])):
                raise ValueError(
                    "fixture misuse: producer_contract must be "
                    "{semantic_core: nonempty str, preconditions: "
                    "nonempty [str, ...], limitations: [str, ...]}")
            _core = producer_contract["semantic_core"]
            _pre = list(producer_contract["preconditions"])
            _lim = list(producer_contract["limitations"])
        else:
            try:
                _core, _pre, _lim = PRODUCER_CONTRACTS[cell["family"]]
            except KeyError:
                raise ValueError(
                    "fixture misuse: no stand-in producer contract for "
                    f"family {cell['family']!r}") from None
        payload["capability_contract"] = {"semantic_core": _core,
                                          "preconditions": list(_pre),
                                          "limitations": list(_lim)}
    arrival = {"decision": decision, "execution_payload": payload,
               "notes": "fixture_modelrun (NOT evidence)"}
    with open(os.path.join(d, "arrival.json"), "w") as f:
        json.dump(arrival, f, indent=1)

    # ---- reuse ledger: the actual decision drives every field ------------
    cap = dict(capability or {})
    cap_available = bool(cap)
    selected = bool(cap_available and decision == "use_capability")
    rejected = bool(cap_available and not selected)
    fields = {"reuse_policy": ("PREREG-frozen: single locked capability per "
                               "(family, producer lane); consumer loads by "
                               "locked hash"),
              "capability_available": cap_available,
              "capability_candidate_ids": ([cap["capability_id"]]
                                           if cap_available else []),
              "capability_selected": selected,
              "selected_capability_id": (cap.get("capability_id")
                                         if selected else None),
              "selected_capability_hash": (cap.get("engine_sha256")
                                           if selected else None),
              "capability_loaded": selected,
              "capability_invoked": selected,
              "capability_output_consumed": selected,
              "capability_materially_contributed": False,
              "contribution_evidence": (None if rejected else
                                        {"mechanism": "none",
                                         "reason": "fixture: consumed but not "
                                                   "proven contributed"}),
              "reuse_rejected": rejected,
              "reuse_rejection_reason": (arrival["notes"] if rejected
                                         else None)}
    if reuse_overrides:
        fields.update(reuse_overrides)
    rec_path = RL.write_record(d, f"{cell['family']}-{cell['task']}", lane,
                              cell["arm"], **fields)

    # ---- manifest: the 13 production order-bound fields + anchors --------
    try:
        order_sha = order.load_expansion(root)["order_sha256"]
    except (ValueError, OSError, KeyError):
        order_sha = cell.get("order_sha256")
    manifest = {"wired": True, "dev_mode": False,
                "cell_id": cell["cell_id"], "cell_index": cell["index"],
                "block": cell["block"], "family": cell["family"],
                "task": cell["task"], "cell_event": cell["event"],
                "cell_kind": cell["kind"], "cell_universe": cell["universe"],
                "cell_letter": cell["letter"], "lane": lane,
                "arm": cell["arm"], "capability_id": cell["capability_id"],
                "order_sha256": order_sha,
                "instance_freeze_commit": freeze_commit,
                "frozen_commit": freeze_commit,
                "verdict": verdict,
                "usage_receipts": [receipt_name],
                "identity_file": "identity.json",
                "reuse_record": os.path.basename(rec_path),
                "lane_receipt": receipt_name,
                "capability": (cap or None),
                "evidence_grade": "harness-validation",
                "fixture": "fixture_modelrun (NOT evidence)"}
    if manifest_overrides:
        manifest.update(manifest_overrides)
    with open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=1)

    # ---- evidence chain: rooted genesis + model-call + evaluator + grade --
    # A12b.7: the evaluator link is production-shaped — it carries real
    # non-null checker/truth/output evidence shas, committed at capture, so
    # promotion provenance can be derived from the VERIFIED link instead of
    # nullable manifest fields. The model-call link commits the identity
    # bytes and the echoed model at capture (post-hoc identity/echo edits
    # are detectable at promotion time).
    chain_path = os.path.join(d, "EVIDENCE-CHAIN.jsonl")
    if os.path.exists(chain_path):
        os.unlink(chain_path)
    ch = CH.Chain(chain_path, freeze_commit, manifest)
    ch.append("model-call", model_call)
    # A12c: a validating T1 commits exactly one candidate-validation
    # event with all nine host-checker keys — the frozen candidate sha,
    # the sha of the bytes the adapter actually ran (the stand-in models
    # exact-byte execution, so equal), the sha of the adapter itself (D4:
    # the exact adapter bytes, adapter_py when given else this run's own
    # solver for pre-A12c callers), the candidate-output sha, the frozen
    # checker/truth shas, the host checker rc, the validation verdict, and
    # the validated flag. Overrides in `candidate_validation` thread real
    # host-checker evidence (A12c N7); defaults are hermetic passing
    # placeholders so pre-A12c callers stay green.
    if validates_candidate is not None:
        _cv_over = dict(candidate_validation or {})
        _adapter_src = (adapter_py if isinstance(adapter_py, str)
                        else payload["solver_py"])
        _cv = {"candidate_sha256": validates_candidate,
               "executed_sha256": validates_candidate,
               "adapter_sha256": hashlib.sha256(
                   _adapter_src.encode()).hexdigest(),
               "candidate_output_sha256": _fixture_evidence_sha(
                   "candidate-output", cell["cell_id"]),
               "checker_sha256": _fixture_evidence_sha("checker",
                                                       cell["cell_id"]),
               "truth_sha256": _fixture_evidence_sha("truth",
                                                     cell["cell_id"]),
               "checker_returncode": 0,
               "validation_verdict": "ship",
               "validated": True}
        _cv.update(_cv_over)
        ch.append("candidate-validation", _cv)
    ev = ch.append("evaluator", {"evaluator": "fixture_modelrun",
                                 "cell_id": cell["cell_id"],
                                 "verdict": verdict,
                                 "checker_sha256":
                                     _fixture_evidence_sha("checker",
                                                           cell["cell_id"]),
                                 "truth_sha256":
                                     _fixture_evidence_sha("truth",
                                                           cell["cell_id"]),
                                 "output_sha256":
                                     _fixture_evidence_sha("output",
                                                           cell["cell_id"]),
                                 "checker_returncode":
                                     {"ship": 0, "fix": 1}.get(verdict)})
    ch.append("grade", {"evaluator_link_hash": ev,
                        "grading_rule_hash": "0" * 64,
                        "grading_rule_version": "fixture-1"})
    return d


if __name__ == "__main__":       # pragma: no cover - manual probe only
    root = sys.argv[1]
    exp = order.load_expansion(root)
    c = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    fc = json.load(open(os.path.join(root, "FREEZE.json")))["freeze_commit"]
    print(build_model_run(root, cell=c, freeze_commit=fc))

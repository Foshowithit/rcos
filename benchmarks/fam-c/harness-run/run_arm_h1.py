#!/usr/bin/env python3
"""H1-integrated Fam-C arm runner, H2/H3-wired.

Model calls happen in the harness process (the only network-capable process).
The model receives only the frozen prompt + exact visible fixture bytes;
arrival execution happens in DockerSandbox (--network none, exactly /work rw
+ /task ro, digest-pinned image). Evaluator runs on the host only after the
container exits and is never mounted into it.

Wiring (ON by default; unwired execution is a dev escape only — see usage):
- H2 usage: every model call goes through usage.recorded_call(); the raw
  provider usage block + identity receipt is persisted per call and each
  receipt is bound into the run's evidence chain as a model-call link.
- H3 chain: every completed run emits EVIDENCE-CHAIN.jsonl — genesis binds
  the INSTANCE freeze commit (FREEZE.json freeze_commit — never an execution
  HEAD masquerading as the freeze, audit P0 #4 dual anchors) + the final run
  manifest; links then record model calls, capability events (reuse /
  promote), the evaluator (sealed truth + checker hashes + verdict), and a
  terminal grade. Chain.audit() re-verifies every link before the run
  returns; any finding aborts loudly (never silent).
- H3 CAPABILITY_LOCK: the correct arm loads its capability ONLY through
  lock.load_artifact() (exact locked hash, verified pre-execution). P0-3: the
  runner NEVER mints a promotion lock — promotion is the sole route of the
  A12.1 order-authorized promotion controller (harness/promotion.py); the
  chain records a promote event only when a caller supplies that controller's
  lock (promote_info), never from a runner-written lock.
- H2 reuse ledger: every wired run writes a reuse_log record whose lifecycle
  fields are derived from the ACTUAL decision/execution path (P0-2):
  use_capability -> selected/loaded/invoked/output_consumed as observed;
  fresh with a capability available -> reuse_rejected with the arrival's
  recorded notes as reuse_rejection_reason; fresh with no capability ->
  capability_available=False. materially_contributed is the DERIVED A13
  causal outcome on wired use_capability engine executions (never asserted,
  never model self-report); absent executed legs it is recorded False
  (consumed, not proven contributed).
- A13 executed counterfactual legs (auditor ruling): on a wired
  use_capability engine cell, execute_a13_legs() runs the ON leg (the cell's
  own engine execution, harvested), the OFF-noop leg (frozen NOOP_v1 pair
  through the same locked engine, same frozen checker), and the pass-through
  leg (F's canonical bytes through the frozen family-agnostic op, K bypassed,
  same frozen checker) -- one ORDER cell, one provider call, no estimand
  change; the receipt (A13-CAUSAL-RECEIPT.json) is bound into the manifest
  so chain genesis covers it. OFF/pass-through verdicts are diagnostics only.

Usage: run_arm_h1.py \\
    <lane P|Q> <family> <task> <correct|disabled> <outdir> [capdir]
      --block PQ|QP  REQUIRED: the reciprocal block this invocation belongs
                     to (item 7). The runner refuses to start unless the
                     requested cell is the next authorized cell of the
                     frozen ORDER.md sequence (ORDER-EXPANSION.json).
      --dev-unwired-outdir DIR  dev escape: UNWIRED run writing to DIR, which
                     must lie OUTSIDE the Fam-C tree; the manifest stamps
                     dev_mode=true. Unwired runs under benchmarks/fam-c/runs
                     are REFUSED (runs/ is the wired estimand surface).
      --acquisition-event T0|T1 --acquisition-universe A|C  the production
                     ACQUISITION executor (A12.0). A mandated pair: the runner
                     authorizes the event cell itself through the frozen order
                     (order.authorize_event), stamps arm=acquisition, builds
                     the prompt with NO capability-access block (none exists
                     before PROMOTION), refuses any arrival decision other
                     than fresh, and writes the same evidence set as any other
                     wired cell. Before this path existed the experiment was
                     mechanically deadlocked at cell 0.
      --selfcheck  offline battery: wiring selfcheck then prompt selfcheck
                     (no model call, no docker, no run) — CI use only.
      --selfcheck-wire  offline fixture compose-test of the wiring (no model
                     call, no docker, no run) — CI use only.
      --selfcheck-prompt  offline proof of the item-6 prompt path on real
                     fam05/T0: one staged snapshot -> canonical envelope ->
                     both arms + symmetry/snapshot refusal gates (no model
                     call, no docker, no run) — CI use only.
      --promote is REFUSED hard (P0-3): promotion is the sole route of the
                     A12.1 order-authorized promotion controller
                     (harness/promotion.py); the runner never mints locks.
Before ANY model call the runner verifies the executed instance subtree is
byte-identical to FREEZE-HASHES.sha256 and that FREEZE.json's freeze_commit
is a resolvable git object (refuse-START on drift; audit P0 #4), and that
all three authority locks (instance/protocol/execution) are green (item 4).
The model context and the docker /task mount are built from ONE staged
visible snapshot, and the arm pair must pass the mechanical symmetry check
(item 6) before any token is spent.
No P/Q calls are made by smoke; use the script only after H1 smoke is green.

A12d D1 (auditor A12d.1/A12d.2/A12d.7) — two jails, evidence-not-exception,
input lineage. (a) The T1 adapter runs in the RAW-TASK jail (its /task is
the staged T1 tree); the candidate runs in a SECOND jail whose /task is
the materialized candidate-input directory ONLY (DockerSandbox(cand_work,
cand_staging), argv python3 /work/candidate.py /task
/work/CANDIDATE-OUTPUT.json). Downstream use_capability execution likewise
runs in an adapted-input-only jail (engine argv python3 /work/engine.py
/task/field_map.json /task/records.json /work/OUTPUT.json); fresh solves
keep the raw-task jail. (b) validate_t1_candidate() NEVER raises on
EXPERIMENTAL failure — it returns the full validation event with
validated=false plus a named validation_failure cause, and the runner
still commits the T1 cell COMPLETE. It raises ONLY on HARNESS/
INFRASTRUCTURE failure: docker unavailable (daemon unreachable at
exec time), sandbox staging/stability denials from DockerSandbox
construction (MOUNT-POLICY/STAGE/STABILITY-DENY), and filesystem errors
creating the jail directories themselves. The boundary rule: defects IN
the experimental material (adapter/candidate bytes, return codes,
outputs, checker verdicts, evaluator bytes presented for binding, the
content of the adapter-materialized input tree) are experimental
evidence; defects OF the harness mechanism (cannot build or enter a
jail, cannot create jail dirs, daemon gone) are infrastructure and
propagate. See validate_t1_candidate() for the per-cause table.
(c) After the adapter run the helper materializes a deterministic
candidate-input content manifest (CANDIDATE-INPUT-MANIFEST.json,
schema candidate-input-manifest-v1) and commits its two hashes on the
chain event; promotion/order re-derive both from the committed file.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

BASE = "/home/chow/chow-work/rcos/benchmarks/fam-c"
HARNESS = "/home/chow/chow-work/rcos/harness"
ROOT = os.path.abspath(os.path.join(BASE, os.pardir, os.pardir))
sys.path.insert(0, HARNESS)
from dockersandbox import (DockerSandbox, ensure_roots, _hash_tree,
                            VISIBLE_ROOT, WORK_ROOT)
from seal import build_visible_root
from usage import (recorded_call, write_normalized_usage,
                   verify_normalized_usage, verify_request_binding,
                   verify_adapter_binding)
from identity import (record_identity, check_against_prereg,
                      verify_identity_binding)
from chain import Chain
from lock import promote as lock_promote, load_artifact
from reuse_log import write_record as reuse_write_record
from admissibility import verify_instance_frozen, verify_freeze_tree
from frozen_visible import (manifest_of_dir as frozen_manifest_of_dir,
                            materialize_frozen_evaluator)
# A13 executed counterfactual legs: the frozen determinant/F/NOOP/
# pass-through/derivation machinery (pure; no model, no docker,
# no chain writes -- this runner supplies the evidence).
import adaptation as AD
# Item-7: the frozen ORDER.md expansion + pre-call cell authorization.
from order import (verify_expansion as order_verify_expansion,
                   load_expansion as order_load_expansion,
                   completed_cells as order_completed_cells,
                   authorize as order_authorize,
                   authorize_event as order_authorize_event,
                   expected_event as order_expected_event,
                   expected_cell as order_expected_cell,
                   run_dir as order_run_dir,
                   derive_paths as order_derive_paths,
                   check_namespace as order_check_namespace,
                   ensure_namespace as order_ensure_namespace,
                   promotion_outcome as order_promotion_outcome,
                   acquisition_failed as order_acquisition_failed,
                   cell_state as order_cell_state)
# Item-4: three-authority preflight is importable (validate_all runs the
# V1/V2/V3 validators without exiting); BASE on the path only exposes the
# fam-c operational root (preflight import; no stdlib shadowing — no
# stdlib-named modules live there).
sys.path.insert(0, BASE)
from preflight import validate_all as preflight_validate_all

CHAIN_FILE = "EVIDENCE-CHAIN.jsonl"
GRADING_RULE_VERSION = "checker-contract-v1"
GRADING_RULE_NOTE = ("mechanical grade = frozen checker returncode mapping "
                     "(rc0=ship, rc1=fix, else blocked); rule hash = sha256 "
                     "of the executed checker bytes")

# Frozen per-lane identity prereg (mirrors LANES.md § identity prereg).
# acceptable_echoed_ids: the provider-echoed model ids this lane may show.
# Patterns are exact ids or trailing-* prefixes; no bare wildcards. Echo
# patterns are frozen from the gateway-facing requested id (router9/kenari
# answer OpenAI-compatible chat; both echo the requested id verbatim, and
# kenari's free tier may strip the ':free' plan suffix). A FIRST observed
# live echo outside these patterns triggers a prereg-amendment commit
# (tighten loop), never a silent substitution.
LANES = {
    # normalizer: A1 provider-bound v2 adapter id (usage.py PROVIDER_NORMALIZERS)
    # preregistered for THIS lane's gateway + model family. New calls MUST
    # declare the v2 id; historical receipts stay on the superseded v1 id.
    "P": {"keyfile": "/home/chow/.agent-vault/keys/router9.key",
          "base": "https://api.router9.com/v1", "model": "minimax-m3",
          "family": "MiniMax", "normalizer": "router9-openai-chat-v2",
          "echo_acceptable": ["minimax-m3"]},
    "Q": {"keyfile": "/home/chow/.agent-vault/keys/kenari.key",
          "base": "https://kenari.id/v1", "model": "agnes-2-0-flash:free",
          "family": "Kenari-Agnes", "normalizer": "kenari-openai-chat-v2",
          "echo_acceptable": ["agnes-2-0-flash:free", "agnes-2-0-flash"]},
}

# Item-6 / A11.3 canonical prompts: ONE envelope format, ONE neutral
# preamble, ONE output contract serve both arms. Treatment and control
# therefore differ ONLY by the mechanically delimited capability-access
# block; the machine proof is
#     strip_capability_block(treatment_prompt) == control_prompt.
_CAP_BEGIN = "<<<CAPABILITY-ACCESS-BEGIN>>>"
_CAP_END = "<<<CAPABILITY-ACCESS-END>>>"
# H-CTX-002 (audit round 3, item 6 / A11.3): the preamble is ONE neutral
# string shared byte-for-byte by BOTH arms. The earlier per-arm preambles
# ("using a PROVIDED capability interface ... you have never seen its
# acquisition" vs "from scratch. No registry/capability/prior solution
# exists") told the treatment model about its acquisition history and told
# the control model a different world-state — treatment leakage in the
# shared region, not symmetry. Everything the arms may NOT diverge on is
# now literally the same bytes.
_ENVELOPE_FMT = ("TASK DEFINITION:\n__TASKDEF__\n\n"
                 "TASK DIRECTORY LISTING: __LISTING__\n"
                 "TASK FILE CONTENTS (exact bytes):\n__BLOBS__\n")
_CAP_FMT = ("\n" + _CAP_BEGIN + "\nCAPABILITY MANIFEST:\n__MANIFEST__\n"
            "ADAPTER NOTES:\n__NOTES__\nENGINE SOURCE (frozen, do not "
            "modify):\n__ENGINE__\n" + _CAP_END + "\n")
_PRE = ("You are solving the task below.\n\n")
# ONE arm-independent output contract (A11b.2). Both arms share byte-
# identical prompt tails and must answer ONE schema whose "decision" value
# alone selects the execution path. A treatment-only schema or arm-picked
# output keys would be a second hint channel (the shape alone would reveal
# which arm produced the prompt), so the payload keys of BOTH paths are
# described to BOTH arms. Identical bytes.
_OUT = ('\nOutput one JSON object with the keys "decision", '
        '"execution_payload", "notes". "decision" is exactly '
        '"use_capability" or "fresh". When "decision" is "use_capability", '
        '"execution_payload" is {"field_map": <object>, "records": <object>}. '
        'When "decision" is "fresh", "execution_payload" is '
        '{"solver_py": <python source string of a self-contained solver>}. '
        '"notes" is one line. '
        'choose use_capability only when a capability-access block is present '
        'and applicable; otherwise choose fresh. '
        'No explanations, no code fences.')
# A12c slice B (B1) + A12d slice D5 (auditor D4-post P0) — T0
# producer instruction carries a required `capability_contract` (T0
# ONLY). The T0 acquisition prompt requests, in addition to `solver_py`,
# a `capability_contract` object with the keys `semantic_core`
# (non-empty string: the producer's own statement of what the reusable
# capability does), `preconditions` (list of
# {"requires_all": [<atomic tokens>]} objects, possibly empty: one
# object per applicability requirement, with exactly the single key
# "requires_all", each token a single lowercase word of letters,
# digits, underscore, dot or hyphen with no spaces, each used at most
# once per list),
# and
# `limitations` (list of strings, possibly empty: free prose about what
# the capability does not cover). An empty `preconditions` list means
# "no declared applicability requirement" and is valid, never
# malformed. The wording names only producer-visible concepts — never
# hidden files, semantic IDs, conformance, ratification, or any auditor
# artifact — and states that omitting the contract makes the run
# unpromotable. Every non-acquisition arm prompt (correct/disabled, B/D
# fresh controls) keeps the byte-identical shared _OUT below and is
# unchanged by this slice; the T1 acquisition instruction (_OUT_T1) is
# likewise unchanged.
_OUT_T0 = ('\nOutput one JSON object with the keys "decision", '
        '"execution_payload", "notes". "decision" is exactly '
        '"use_capability" or "fresh". When "decision" is "use_capability", '
        '"execution_payload" is {"field_map": <object>, "records": <object>}. '
        'When "decision" is "fresh", "execution_payload" is '
        '{"solver_py": <python source string of a self-contained solver>, '
        '"capability_contract": <object describing the reusable capability '
        'in your own words>}. '
        'The capability contract has the keys "semantic_core", '
        '"preconditions", "limitations": "semantic_core" is a non-empty '
        'string stating in your own words what the reusable capability '
        'does; "preconditions" is a list of objects of the exact shape '
        '{"requires_all": [<atomic tokens>]} (the list may be empty), one '
        'object per applicability requirement with only the "requires_all" '
        'key; each token is one lowercase word of letters, digits, '
        'underscore, dot or hyphen, with no spaces, each used at most '
        'once per list; '
        '"limitations" is a list of strings '
        '(possibly empty) stating what it does not cover. '
        'An empty "preconditions" list means no declared applicability '
        'requirement and is valid, never malformed. '
        'Write the contract from the task in front of you, in your own '
        'words about the reusable capability. '
        'Omitting the capability contract makes the run unpromotable '
        '(promotion requires the contract). '
        '"notes" is one line. '
        'choose use_capability only when a capability-access block is present '
        'and applicable; otherwise choose fresh. '
        'No explanations, no code fences.')
# A12c D1 — T1 producer instruction gains a required `adapter_py` (T0
# unchanged). The T1 acquisition prompt requests, in addition to
# `solver_py`, a field `adapter_py` (a string of Python source) with the
# frozen ABI: python3 adapter.py <task_dir> <out_input_dir>. It
# materializes the candidate's expected input directory from the T1 task
# surface. The adapter must exit non-zero on failure, and omitting
# adapter_py makes the run unpromotable (no candidate validation, no
# promotion). T0's instruction (_OUT) is unchanged in this slice.
_OUT_T1 = ('\nOutput one JSON object with the keys "decision", '
        '"execution_payload", "notes". "decision" is exactly '
        '"use_capability" or "fresh". When "decision" is "use_capability", '
        '"execution_payload" is {"field_map": <object>, "records": <object>}. '
        'When "decision" is "fresh", "execution_payload" is '
        '{"solver_py": <python source string of a self-contained solver>, '
        '"adapter_py": <python source string of a self-contained adapter>}. '
        'The adapter materializes the candidate\'s expected input directory '
        'from the T1 task surface with the frozen ABI: '
        'python3 adapter.py <task_dir> <out_input_dir> — it must exit '
        'non-zero on failure, and omitting adapter_py makes the run '
        'unpromotable (no candidate validation, no promotion). '
        '"notes" is one line. '
        'choose use_capability only when a capability-access block is present '
        'and applicable; otherwise choose fresh. '
        'No explanations, no code fences.')
CORRECT = _PRE + _ENVELOPE_FMT + _CAP_FMT + _OUT
DISABLED = _PRE + _ENVELOPE_FMT + _OUT
# Counterfactual capability content (disabled-arm runs): builds the
# never-sent correct-arm twin for the pair symmetry check. Fixed sentinel,
# never model input, never executed.
COUNTERFACTUAL_CAP = ("COUNTERFACTUAL-ONLY never sent to any model: "
                      "placeholder capability content so the disabled arm "
                      "can prove pair symmetry without touching K.")

# A12b.2 candidate-validation block (T1 acquisition ONLY): the frozen T0
# candidate travels to T1 inside these delimiters — the sha256 of the exact
# candidate bytes, the immutable source text, and the frozen argv ABI the
# adapter must use to execute it:
#     python3 candidate.py <input_dir> <output_path>
# The block belongs ONLY to the T1 acquisition surface: it never appears
# in an arm prompt (T1/T2/T4 symmetry), and strip_capability_block /
# check_arm_symmetry cover it alongside the capability-access block, so a
# candidate block leaking into any arm prompt fails closed.
_CAND_BEGIN = "<<<CANDIDATE-VALIDATION-BEGIN>>>"
_CAND_END = "<<<CANDIDATE-VALIDATION-END>>>"
_CAND_FMT = ("\n" + _CAND_BEGIN + "\n"
             "candidate_sha256: __CAND_SHA__\n"
             "immutable_source:\n__CAND_SOURCE__\n"
             "abi: python3 candidate.py <input_dir> <output_path>\n"
             + _CAND_END + "\n")


def build_candidate_validation_block(candidate_sha256, candidate_source):
    """Render the T1-only candidate-validation block (fail closed)."""
    if not (isinstance(candidate_sha256, str)
            and len(candidate_sha256) == 64):
        raise ValueError("CANDIDATE-VALIDATION-DENY: candidate sha256 must "
                         f"be 64-hex, got {candidate_sha256!r}")
    try:
        int(candidate_sha256, 16)
    except ValueError:
        raise ValueError("CANDIDATE-VALIDATION-DENY: candidate sha256 must "
                         f"be 64-hex, got {candidate_sha256!r}") from None
    if not (isinstance(candidate_source, str) and candidate_source.strip()):
        raise ValueError("CANDIDATE-VALIDATION-DENY: candidate source is "
                         "empty (T1 must see the exact candidate bytes)")
    for marker in (_CAND_BEGIN, _CAND_END, _CAP_BEGIN, _CAP_END):
        if marker in candidate_source:
            raise ValueError("CANDIDATE-VALIDATION-DENY: candidate source "
                             f"contains a block delimiter {marker!r}")
    return (_CAND_FMT.replace("__CAND_SHA__", candidate_sha256)
            .replace("__CAND_SOURCE__", candidate_source))


def build_envelope(taskdef, listing, block):
    """One canonical envelope: the shared task bytes both arms embed."""
    return _ENVELOPE_FMT.replace("__TASKDEF__", taskdef).replace(
        "__LISTING__", listing).replace("__BLOBS__", block)


def build_arm_prompt(arm, envelope, cap_manifest="", cap_notes="",
                     cap_engine=""):
    """Build one arm's prompt from the shared envelope object."""
    if arm == "correct":
        cap = _CAP_FMT.replace("__MANIFEST__", cap_manifest).replace(
            "__NOTES__", cap_notes).replace("__ENGINE__", cap_engine)
        return _PRE + envelope + cap + _OUT
    if arm == "disabled":
        return _PRE + envelope + _OUT
    raise ValueError("unknown arm")


def _strip_one(prompt, begin, end):
    """Remove one delimited block (inclusive, plus the ONE separator newline
    that frames it on each side). Returns the prompt unchanged when no
    block is present."""
    if begin not in prompt:
        return prompt
    i = prompt.index(begin)
    j = prompt.index(end, i) + len(end)
    head, tail = prompt[:i], prompt[j:]
    if head.endswith("\n") and tail.startswith("\n"):
        head = head[:-1]
        tail = tail[1:]
    return head + tail


def _strip_capability_only(prompt):
    """Remove ONLY the capability-access block. The acquisition-surface
    manifest fields use this (not the full stripper): a T1 acquisition
    prompt legitimately carries the candidate-validation block, which is
    not capability content and must not flip those fields."""
    return _strip_one(prompt, _CAP_BEGIN, _CAP_END)


def strip_capability_block(prompt):
    """Remove every model-context augmentation block: the delimited
    capability-access block AND the T1-only candidate-validation block
    (each inclusive, plus the ONE separator newline that frames it on
    each side). Returns the prompt unchanged when no block is present.

    The capability block is emitted as "\n" + BEGIN + ... + END + "\n"
    (and the candidate block the same way), so the treatment prompt minus
    the block still carries the framing newline that precedes it;
    consuming that single adjacent newline is what makes the stripped
    treatment bytes EQUAL the control bytes rather than control + a
    stray blank line. Leak-stripping stays true when a candidate block
    leaks into an arm prompt: removing both blocks still recovers the
    control bytes.
    """
    out = prompt
    for _ in range(4):
        new = _strip_one(_strip_one(out, _CAP_BEGIN, _CAP_END),
                         _CAND_BEGIN, _CAND_END)
        if new == out:
            return out
        out = new
    return out


def _first_diff(a, b):
    """Index + context of the first byte difference (diagnostics only)."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return (f"index {i}: {a[max(0, i - 20):i + 20]!r} != "
                    f"{b[max(0, i - 20):i + 20]!r}")
    return f"length {len(a)} != {len(b)}"


def check_arm_symmetry(correct_prompt, disabled_prompt, envelope):
    """H-CTX-002 mechanical pair check (fail-closed findings list).

    A11.3 acceptance (machine proof, not prose): removing the delimited
    capability-access block from the treatment prompt must yield BYTE-
    IDENTICAL bytes to the control prompt:

        strip_capability_block(treatment_prompt) == control_prompt

    That single equality subsumes preamble, envelope and output-contract
    symmetry: any divergence anywhere outside the delimited block makes the
    strings differ. The older assertions ("each arm's own frozen preamble",
    "the arm's own output schema") were WEAKER — they legitimized divergent
    shared bytes — and are DELETED, not supplemented. Also checked: the
    capability block occurs exactly once in treatment and never in control,
    is well-delimited, sits strictly after the shared envelope, and is
    non-empty with its frozen section headers.
    """
    out = []
    if (correct_prompt.count(_CAP_BEGIN) != 1
            or correct_prompt.count(_CAP_END) != 1):
        out.append("SYMMETRY-FAIL: capability-access delimiters != 1 each "
                   "in treatment prompt")
        return out
    if correct_prompt.index(_CAP_BEGIN) > correct_prompt.index(_CAP_END):
        out.append("SYMMETRY-FAIL: capability-access end before begin")
        return out
    if _CAP_BEGIN in disabled_prompt or _CAP_END in disabled_prompt:
        out.append("SYMMETRY-FAIL: capability-access block present in "
                   "control prompt")
    # A12b.2: the candidate-validation block belongs ONLY to the T1
    # acquisition surface. In either arm prompt it is a leak channel (the
    # frozen candidate bytes), so it fails closed here; the full stripper
    # above still recovers control bytes for diagnostics.
    if _CAND_BEGIN in correct_prompt or _CAND_END in correct_prompt or \
            _CAND_BEGIN in disabled_prompt or _CAND_END in disabled_prompt:
        out.append("SYMMETRY-FAIL: candidate-validation block present in "
                   "an arm prompt (it belongs only to the T1 acquisition "
                   "surface, never to T1/T2/T4 arm prompts)")
    for name, prompt in (("treatment", correct_prompt),
                         ("control", disabled_prompt)):
        if prompt.count(envelope) != 1:
            out.append("SYMMETRY-FAIL: canonical envelope not "
                       "verbatim-once in " + name + " prompt (hint "
                       "asymmetry or drift in the shared region)")
    if out:
        return out
    stripped = strip_capability_block(correct_prompt)
    if stripped != disabled_prompt:
        out.append("SYMMETRY-FAIL: strip_capability_block(treatment) != "
                   "control - shared-region divergence at "
                   + _first_diff(stripped, disabled_prompt))
    if not correct_prompt.startswith(_PRE) or \
            not disabled_prompt.startswith(_PRE):
        out.append("SYMMETRY-FAIL: prompt does not start with the single "
                   "shared neutral preamble")
    if not correct_prompt.endswith(_OUT) or not disabled_prompt.endswith(_OUT):
        out.append("SYMMETRY-FAIL: prompt does not end with the single "
                   "shared output contract")
    head_c, tail_c = correct_prompt.split(envelope)
    head_d, tail_d = disabled_prompt.split(envelope)
    if head_c != head_d:
        out.append("SYMMETRY-FAIL: preambles differ between arms")
    if not tail_c.startswith("\n" + _CAP_BEGIN + "\n"):
        out.append("SYMMETRY-FAIL: capability block misdelimited after the "
                   "envelope")
    elif tail_c.count(_CAP_END + "\n") != 1:
        out.append("SYMMETRY-FAIL: capability block end misdelimited")
    else:
        body = tail_c[len("\n" + _CAP_BEGIN + "\n"):
                      -len(_CAP_END + "\n" + _OUT)]
        for marker in ("CAPABILITY MANIFEST:", "ADAPTER NOTES:",
                       "ENGINE SOURCE (frozen, do not modify):"):
            if marker not in body:
                out.append("SYMMETRY-FAIL: capability block missing the "
                           "frozen section header " + repr(marker))
        if not body.strip():
            out.append("SYMMETRY-FAIL: capability-access block empty")
    return out


def h(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------------------
# A12d D1 — candidate-input lineage (A12d.7) + jail input staging (A12d.1)
# ---------------------------------------------------------------------------

CANDIDATE_INPUT_MANIFEST_SCHEMA = "candidate-input-manifest-v1"

# The single candidate-validation chain event carries exactly these eleven
# keys on the success path (nine A12c keys + two lineage keys). On the
# experimental-failure path the same eleven ride with validated=false,
# observed values (null where unobserved), plus a twelfth key
# `validation_failure` naming the cause.
CV_ELEVEN = ("candidate_sha256", "executed_sha256", "adapter_sha256",
             "candidate_output_sha256", "checker_sha256", "truth_sha256",
             "checker_returncode", "validation_verdict", "validated",
             "candidate_input_manifest_sha256",
             "candidate_input_tree_sha256")


def _manifest_tree_sha256(schema, entries):
    """The deterministic tree hash (spec C1): sha256 of the canonical bytes
    of the manifest WITHOUT the tree_sha256 field
    (json.dumps(obj, sort_keys=True, indent=1) + trailing newline)."""
    canonical = json.dumps({"schema": schema, "entries": entries},
                           sort_keys=True, indent=1) + "\n"
    return hashlib.sha256(canonical.encode()).hexdigest(), canonical


def _scan_candidate_input(tree_dir):
    """Lstat-walk a materialized candidate-input tree. Returns (entries,
    denial): entries is the sorted manifest entry list; denial is None on
    success or a CANDIDATE-INPUT-DENY / candidate-input-unreadable cause
    string (EXPERIMENTAL failure — the adapter re-exposed raw bytes through
    a symlink, a hardlink, or a special file, or the tree is unreadable).
    Directories are not entries. No mtimes, no absolute paths. Raises
    nothing for content defects (OSError on READ maps to unreadable);
    OSError on jail-directory creation is raised by the caller, never
    here, so infra stays infra."""
    entries = []
    try:
        if os.path.islink(tree_dir) or not os.path.isdir(tree_dir):
            return None, ("candidate-input-missing: the adapter exited 0 "
                          "but materialized no candidate input directory "
                          f"at {tree_dir}")
        for base, dirs, files in os.walk(tree_dir, followlinks=False):
            for d in sorted(dirs):
                p = os.path.join(base, d)
                try:
                    st = os.lstat(p)
                except OSError as e:
                    return None, ("candidate-input-unreadable: cannot lstat "
                                  f"directory {p!r}: {e}")
                if stat.S_ISLNK(st.st_mode):
                    return None, ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                                  f"symlinked directory in candidate input: "
                                  f"{os.path.relpath(p, tree_dir)!r} (a "
                                  f"symlink would let the adapter re-expose "
                                  f"raw task bytes through the candidate "
                                  f"jail)")
                if not stat.S_ISDIR(st.st_mode):
                    return None, ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                                  f"non-directory in candidate input: "
                                  f"{os.path.relpath(p, tree_dir)!r}")
            for fn in sorted(files):
                p = os.path.join(base, fn)
                rel = os.path.relpath(p, tree_dir)
                try:
                    st = os.lstat(p)
                except OSError as e:
                    return None, ("candidate-input-unreadable: cannot lstat "
                                  f"candidate input file {rel!r}: {e}")
                if stat.S_ISLNK(st.st_mode):
                    return None, ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                                  f"symlink in candidate input: {rel!r} (a "
                                  f"symlink would let the adapter re-expose "
                                  f"raw task bytes through the candidate "
                                  f"jail)")
                if not stat.S_ISREG(st.st_mode):
                    return None, ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                                  f"non-regular file in candidate input: "
                                  f"{rel!r} (no fifos, sockets, devices)")
                if st.st_nlink > 1:
                    return None, ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                                  f"hardlinked file in candidate input: "
                                  f"{rel!r} (nlink={st.st_nlink}; a hardlink "
                                  f"would let the adapter re-expose raw "
                                  f"task bytes through the candidate jail)")
                try:
                    with open(p, "rb") as f:
                        data = f.read()
                except OSError as e:
                    return None, ("candidate-input-unreadable: cannot read "
                                  f"candidate input file {rel!r}: {e}")
                entries.append({"path": rel.replace(os.sep, "/"),
                                "kind": "file", "size": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()})
    except OSError as e:
        return None, (f"candidate-input-unreadable: cannot walk candidate "
                      f"input tree {tree_dir!r}: {e}")
    entries.sort(key=lambda e: e["path"])
    return entries, None


def _copy_candidate_input(src, dst):
    """Guarded copy of a validated candidate-input tree (no symlink
    laundering: every source component is re-checked with lstat during the
    copy; a violation returns a CANDIDATE-INPUT-DENY denial instead of
    materializing attacker bytes). Returns None on success or a denial
    string (experimental). OSError on WRITES/mkdirs propagates (infra:
    the jail filesystem itself failed)."""
    for base, dirs, files in os.walk(src, followlinks=False):
        for d in sorted(dirs):
            p = os.path.join(base, d)
            try:
                st = os.lstat(p)
            except OSError as e:
                return ("candidate-input-unreadable: cannot lstat directory "
                        f"{p!r} during staging: {e}")
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                return ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                        f"non-directory {os.path.relpath(p, src)!r} appeared "
                        f"in candidate input during staging")
        for fn in sorted(files):
            s = os.path.join(base, fn)
            rel = os.path.relpath(s, src)
            try:
                st = os.lstat(s)
            except OSError as e:
                return ("candidate-input-unreadable: cannot lstat "
                        f"{rel!r} during staging: {e}")
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) \
                    or st.st_nlink > 1:
                return ("candidate-input-deny: CANDIDATE-INPUT-DENY "
                        f"unsafe file {rel!r} appeared in candidate input "
                        f"during staging")
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d) or dst, exist_ok=True)
            try:
                with open(s, "rb") as f:
                    data = f.read()
            except OSError as e:
                return ("candidate-input-unreadable: cannot read "
                        f"{rel!r} during staging: {e}")
            with open(d, "wb") as f:  # noqa: PTH123 — infra writes raise
                f.write(data)
    return None


def _stage_candidate_input(work_cand_in):
    """Materialize the adapter's output as a mountable candidate-input
    source under VISIBLE_ROOT. Returns (staging_dir, denial, entries):
    staging_dir is the visible source (bytes the candidate jail will see),
    entries the manifest entry list over THOSE bytes, denial None on
    success or an experimental cause string. Filesystem errors creating
    the staging directory itself propagate (infra).

    An adapter that exited 0 but materialized NO input tree (absent,
    symlinked, or non-directory cand_in) stages an EMPTY input: the
    candidate still runs against the empty tree and its failure is the
    evidence (candidate-failed / checker-failed) — the validation must
    execute the candidate, never skip it. Only a tree that EXISTS but
    carries unsafe CONTENT fails closed with CANDIDATE-INPUT-DENY."""
    try:
        is_link = os.path.islink(work_cand_in)
        is_dir = os.path.isdir(work_cand_in)
    except OSError:
        is_link, is_dir = False, False
    staging = tempfile.mkdtemp(prefix="famc-candin-", dir=VISIBLE_ROOT)
    os.chmod(staging, 0o700)
    if is_link or not is_dir:
        return staging, None, []
    entries, denial = _scan_candidate_input(work_cand_in)
    if denial is not None:
        return None, denial, None
    denial = _copy_candidate_input(work_cand_in, staging)
    if denial is not None:
        return None, denial, None
    entries, denial = _scan_candidate_input(staging)
    if denial is not None:  # cannot happen without a concurrent mutation
        return None, denial, None
    return staging, None, entries


def _infra_down(p):
    """True when a jail CompletedProcess shows the DOCKER mechanism itself
    failed (daemon unreachable / engine error), as opposed to the program
    inside the jail exiting non-zero. Only that case is infrastructure;
    every in-jail non-zero rc is experimental evidence."""
    if p.returncode == 0:
        return False
    if p.returncode == 125 and isinstance(getattr(p, "stderr", None), str) \
            and ("daemon" in p.stderr.lower()
                 or "cannot connect" in p.stderr.lower()
                 or "docker: " in p.stderr.lower()):
        return True
    return False


_ARRIVAL_KEYS = ("decision", "execution_payload", "notes")


def _validate_arrival(obj):
    """A11b.2 shared-contract gate (fail closed, named errors, no assert).

    One JSON object with the three contract keys, a legal decision, and an
    execution_payload matching the decision's declared shape. The parser is
    arm-independent, so arm legality of a decision is checked later at
    execution (CONTRACT-DECISION-DENY), never here."""
    if not isinstance(obj, dict):
        raise ValueError("CONTRACT-PARSE-DENY: arrival is not a JSON object")
    for key in _ARRIVAL_KEYS:
        if key not in obj:
            raise ValueError("CONTRACT-PARSE-DENY: missing key " + repr(key))
    decision = obj["decision"]
    if decision not in ("use_capability", "fresh"):
        raise ValueError("CONTRACT-DECISION-DENY: unknown decision "
                         + repr(decision))
    payload = obj["execution_payload"]
    if not isinstance(payload, dict):
        raise ValueError("CONTRACT-PARSE-DENY: execution_payload is not a "
                         "JSON object")
    if decision == "use_capability":
        for key in ("field_map", "records"):
            if key not in payload:
                raise ValueError("CONTRACT-PARSE-DENY: use_capability "
                                 "payload missing key " + repr(key))
    else:  # fresh
        if "solver_py" not in payload:
            raise ValueError("CONTRACT-PARSE-DENY: fresh payload missing "
                             "key 'solver_py'")
        if not isinstance(payload["solver_py"], str):
            raise ValueError("CONTRACT-PARSE-DENY: fresh solver_py is not a "
                             "python source string")
    return obj


def extract(raw):
    """Parse ONE arm-independent arrival from a model response (A11b.2).

    No arm parameter, no substring search for arm payload keys, no
    arm-specific branch: a single decoder finds one
    JSON object and validates it against the shared contract. parse_mode
    contract preserved: "json-envelope" (whole response or inline object)
    or "fence-fallback" (object recovered from a fenced code block, parsed
    to the SAME object shape for every decision). Named CONTRACT-* errors
    raise on any violation; never assert (-O safe)."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("CONTRACT-PARSE-DENY: empty arrival")
    try:
        obj = json.loads(text)
    except ValueError:
        pass
    else:
        if isinstance(obj, dict):
            # Whole-response object: validate once, fail closed immediately
            # with its named error (never fall through to heuristics).
            return _validate_arrival(obj), "json-envelope"
    m = re.search(r"```(?:json|python)?\s*(.*?)\s*```", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(1))
        except ValueError as e:
            raise ValueError("CONTRACT-PARSE-DENY: fenced arrival is not "
                             "JSON: " + str(e)) from None
        if isinstance(obj, dict):
            return _validate_arrival(obj), "fence-fallback"
    # Inline JSON object anywhere in prose (generic envelope scan).
    dec = json.JSONDecoder()
    i = text.find("{")
    last_err = None
    while i >= 0:
        try:
            obj, _ = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            try:
                return _validate_arrival(obj), "json-envelope"
            except ValueError as e:
                last_err = e
        i = text.find("{", i + 1)
    if last_err is not None:
        raise last_err
    raise ValueError("CONTRACT-PARSE-DENY: arrival has no parseable envelope")


def execute_arrival(arm, arrival, work, outdir, taskdir, cap_engine, sb,
                      jail_factory=None, evaluator_authority=None):
    """Run one validated A11b.2 arrival through the ONE H1 runtime path.

    The arrival's OWN "decision" selects the path (use_capability -> the
    locked capability engine; fresh -> a solver); the arm never branches
    the parser and only gates decision legality. Host-side frozen checker
    and verdict mapping unchanged (rc 0 -> ship, 1 -> fix, else blocked);
    truth/checker never enter the jail. Fail closed with named errors
    (assert-free, -O safe):
      CONTRACT-DECISION-DENY  decision illegal for the arm (e.g. a disabled
                              arm returning "use_capability")
      CONTRACT-ENGINE-DENY    use_capability without a capability engine
      EVALUATOR-DRIFT-DENY    (authority path only) the live evaluator
                              bytes differ from the freeze-derived
                              authority at the point of use — refused
                              before any verdict is recorded
    `jail_factory` (A12d D1 clarification): the use_capability engine
    jail is built as jail_factory(work, adapted_dir) — default None
    builds the production DockerSandbox(work, adapted_dir); a test seam
    may supply a shim factory with the same (work_dir, visible_root)
    call shape returning .run(argv, timeout=...) + .task_snapshot (when
    available). The fresh/solver path always uses the caller-supplied
    raw-task jail `sb`.
    `evaluator_authority` (A12n slice D12b): None keeps the legacy
    live-tree grading path (hash-then-execute the family checker in
    place). When given {"family", "freeze_commit",
    "expected_checker_sha256", "expected_truth_sha256"} (the
    verify_instance_frozen authority object — freeze-derived, never
    the mutable tree), the arrival is graded ONLY by the frozen
    bytes: the live checker/truth are re-hashed at the point of use
    and any drift refuses with EVALUATOR-DRIFT-DENY, then the
    evaluator is materialized from freeze-commit blobs into a
    run-private dir and THAT copy is executed — so even a mutation
    landing between the re-hash and the exec cannot substitute the
    grading bytes. Production main() always passes the authority.
    Returns {"verdict", "checker_returncode", "checker_output",
             "output_sha256", "graded_output_sha256",
             "graded_output_path", "decision", "execution_mode",
             "container_returncode", "checker_path", "checker_sha256",
             "truth_sha256", "expected_checker_sha256",
             "expected_truth_sha256", "evaluator_source"} — the
    checker/truth sha256s are the exact bytes THIS arrival's
    evaluation path executed (the frozen-materialized copy on the
    authority path, bound before the host-side checker ran);
    output_sha256 is the container-produced /work/OUTPUT.json bytes
    while graded_output_sha256 is the sha256 of the EXACT sealed
    bytes passed to the checker (D13 P0-2; None when no output was
    produced or on the live-legacy path); checker_path is the
    executed copy's path; evaluator_source names which form graded
    the run ("frozen-materialized" vs "live-legacy").
    Plus "engine_jail" on the use_capability path: {"task_snapshot",
    "mounts", "adapted_input_sha256"} describing the adapted-input-only
    jail (A12d D1-A3/A4); None on the fresh/solver path."""
    decision = arrival["decision"]
    execution_mode = None
    engine_jail = None
    if decision == "use_capability":
        if arm != "correct":
            raise RuntimeError("CONTRACT-DECISION-DENY: decision "
                               "'use_capability' is legal only on the "
                               "capability arm, not arm=" + repr(arm))
        if not cap_engine or not os.path.exists(cap_engine):
            raise RuntimeError("CONTRACT-ENGINE-DENY: decision "
                               "'use_capability' without a locked "
                               "capability engine")
        shutil.copy2(cap_engine, os.path.join(work, "engine.py"))
        payload = arrival["execution_payload"]
        # A12d D1-A3: the engine jail's /task contains ONLY the adapted
        # payload the model produced — never the raw task tree. The two
        # payload documents are materialized into a fresh adapted-input
        # directory under VISIBLE_ROOT and that directory ALONE is mounted
        # as /task (DockerSandbox(work, adapted_dir)); the engine argv
        # addresses /task paths. A fresh solve keeps the raw-task jail
        # (it legitimately needs the task).
        ensure_roots()
        adapted_dir = tempfile.mkdtemp(prefix="famc-adapted-",
                                       dir=VISIBLE_ROOT)
        os.chmod(adapted_dir, 0o700)
        for name in ("field_map", "records"):
            with open(os.path.join(adapted_dir, name + ".json"), "w") as f:
                json.dump(payload[name], f, sort_keys=True, indent=1)
                f.write("\n")
        adapted_entries, adapted_denial = _scan_candidate_input(adapted_dir)
        if adapted_denial is not None:  # cannot happen: just-written files
            raise RuntimeError("ADAPTED-INPUT-DENY: " + adapted_denial)
        adapted_input_sha256, _ = _manifest_tree_sha256(
            CANDIDATE_INPUT_MANIFEST_SCHEMA, adapted_entries)
        engine_sb = (jail_factory or DockerSandbox)(work, adapted_dir)
        command = ["python3", "/work/engine.py", "/task/field_map.json",
                   "/task/records.json", "/work/OUTPUT.json"]
        execution_mode = "engine"
        p = engine_sb.run(command, timeout=120)
        try:
            _engine_mounts = engine_sb.manifest()["mounts"]
        except AttributeError:
            # Shim factories expose .run + .task_snapshot, not the full
            # DockerSandbox manifest: record the equivalent two mounts.
            _engine_mounts = [{"host": work, "container": "/work",
                               "mode": "rw"},
                              {"host": adapted_dir, "container": "/task",
                               "mode": "ro"}]
        engine_jail = {"task_snapshot": getattr(engine_sb, "task_snapshot",
                                                None),
                       "mounts": _engine_mounts,
                       "adapted_input_sha256": adapted_input_sha256}
    else:  # fresh — the only legal decision on the disabled arm
        open(os.path.join(work, "solver.py"), "w").write(
            arrival["execution_payload"]["solver_py"])
        command = ["python3", "/work/solver.py", "/task", "/work/OUTPUT.json"]
        execution_mode = "solver"
        p = sb.run(command, timeout=120)
    out = os.path.join(work, "OUTPUT.json")
    # Copy artifacts back to the committed outdir for auditability.
    if os.path.exists(out):
        shutil.copy2(out, os.path.join(outdir, "OUTPUT.json"))
    # Host-side evaluator only after container; truth/checker never entered jail.
    checker = os.path.join(taskdir, "..", "check.py")
    truth_path = os.path.join(taskdir, "..", "truth.json")
    expected_checker_sha256 = None
    expected_truth_sha256 = None
    evaluator_source = "live-legacy"
    if evaluator_authority is not None:
        # A12n slice D12b — point-of-use evaluator bind. The live bytes
        # about to grade this arrival must equal the freeze-derived
        # authority; any drift (a checker/truth rewritten after
        # verification, even after the pre-model gate) refuses here
        # with EVALUATOR-DRIFT-DENY, before the checker subprocess
        # runs, so no verdict is ever recorded for substituted bytes.
        expected_checker_sha256 = evaluator_authority.get(
            "expected_checker_sha256")
        expected_truth_sha256 = evaluator_authority.get(
            "expected_truth_sha256")
        live_checker_sha = h(checker) if os.path.exists(checker) else None
        live_truth_sha = h(truth_path) if os.path.exists(
            truth_path) else None
        if live_checker_sha != expected_checker_sha256 or \
                live_truth_sha != expected_truth_sha256:
            raise RuntimeError(
                "EVALUATOR-DRIFT-DENY live evaluator bytes != "
                "freeze-derived authority "
                f"(checker {str(live_checker_sha)[:12]} != "
                f"{str(expected_checker_sha256)[:12]} or truth "
                f"{str(live_truth_sha)[:12]} != "
                f"{str(expected_truth_sha256)[:12]}); refused at the "
                "point of use before any verdict is recorded")
        # Stronger form: grade with the FROZEN bytes, not the live
        # tree. Materialize checker + truth from freeze-commit blobs
        # into a run-private dir and execute THAT copy, so a mutation
        # landing between the re-hash above and the exec still cannot
        # substitute the grading bytes. Safe because the checker's
        # input closure is exactly {check.py, sibling truth.json}
        # (each family checker reads HERE/truth.json with stdlib-only
        # imports — asserted per family by smoke_h33_d12b), and the
        # materialized copy reads its own frozen sibling.
        frozen_ev = materialize_frozen_evaluator(
            BASE, evaluator_authority["freeze_commit"],
            evaluator_authority["family"],
            os.path.join(outdir, "frozen-evaluator"))
        # The executed paths ARE the frozen copy from here on: the
        # checker subprocess below runs the materialized check.py,
        # which reads its materialized frozen sibling truth.json.
        checker = frozen_ev["checker_path"]
        truth_path = frozen_ev["truth_path"]
        evaluator_source = "frozen-materialized"
    # Bind the EXACT bytes this arrival's evaluation path executes —
    # before the checker subprocess runs — so the caller's evidence
    # never recomputes a hash over a different path or a
    # post-checker-modified file. On the authority path these are the
    # frozen-materialized bytes (belt-and-braces: they must equal
    # the freeze-derived expectation, verified here again behind the
    # post-write verification inside the materializer).
    checker_sha256 = h(checker) if os.path.exists(checker) else None
    truth_sha256 = h(truth_path) if os.path.exists(truth_path) else None
    if evaluator_source == "frozen-materialized" and (
            checker_sha256 != expected_checker_sha256
            or truth_sha256 != expected_truth_sha256):
        raise RuntimeError(
            "EVALUATOR-DRIFT-DENY materialized frozen evaluator "
            "bytes != freeze-derived authority; refused before "
            "any verdict is recorded")
    chk = None
    # A12n slice D13 P0-2 (+D13c residual): the GRADED output is sealed
    # from the COMMITTED bytes, never from a mutable copy. `out` is the
    # /work file the solver produced; the seal copies it into the
    # run-private evaluation package (frozen check.py + frozen
    # truth.json + SEALED OUTPUT.json) and verifies the sealed bytes
    # equal the committed bytes BEFORE the checker runs — a run-dir
    # substitution (before, during, or after the copy into outdir)
    # cannot change the verdict and can never produce a SHIP from
    # substituted bytes: the checker grades the committed bytes or
    # the run refuses. A post-checker re-hash of BOTH the sealed
    # file and the committed file must equal the seal, else
    # EVALUATOR-INPUT-DRIFT-DENY is raised and no verdict is ever
    # recorded. On the authority path graded_output_sha256 ==
    # output_sha256 is additionally required explicitly below, so
    # the two can never diverge silently.
    output_sha256 = h(out) if os.path.exists(out) else None
    graded_output_sha256 = None
    graded_output_path = None
    if os.path.exists(out):
        if evaluator_source == "frozen-materialized":
            graded_output_path = os.path.join(
                os.path.dirname(checker), "OUTPUT.json")
            shutil.copy2(out, graded_output_path)
            graded_output_sha256 = h(graded_output_path)
            if graded_output_sha256 != output_sha256:
                raise RuntimeError(
                    "EVALUATOR-INPUT-DRIFT-DENY sealed graded bytes "
                    f"{graded_output_sha256[:12]} != committed solver "
                    f"bytes {str(output_sha256)[:12]}; refusing before "
                    "the checker runs")
            checker_argv_output = graded_output_path
        else:
            checker_argv_output = os.path.join(outdir, "OUTPUT.json")
        chk = subprocess.run([sys.executable, checker,
                              os.path.basename(taskdir),
                              checker_argv_output],
                             capture_output=True, text=True)
        if graded_output_sha256 is not None:
            if h(graded_output_path) != graded_output_sha256 or \
                    h(out) != output_sha256:
                raise RuntimeError(
                    "EVALUATOR-INPUT-DRIFT-DENY sealed graded output "
                    f"{h(graded_output_path)[:12]} != pre-checker seal "
                    f"{graded_output_sha256[:12]} (or committed bytes "
                    "changed under grading); the checker consumed "
                    "bytes the evidence does not name — no verdict is "
                    "recorded")
            if graded_output_sha256 != output_sha256:
                raise RuntimeError(
                    "EVALUATOR-INPUT-DRIFT-DENY graded output "
                    f"{graded_output_sha256[:12]} != container output "
                    f"{str(output_sha256)[:12]} on the authority path; "
                    "the two must never diverge")
    verdict = ("ship" if chk and chk.returncode == 0 else
               "fix" if chk and chk.returncode == 1 else "blocked")
    return {"verdict": verdict,
            "checker_returncode": chk.returncode if chk else None,
            "checker_output": ((chk.stdout or "") + (chk.stderr or ""))[:500]
                              if chk else "missing output",
            "output_sha256": output_sha256,
            "graded_output_sha256": graded_output_sha256,
            "graded_output_path": graded_output_path,
            "decision": decision,
            "execution_mode": execution_mode,
            "engine_jail": engine_jail,
            "container_returncode": p.returncode,
            "checker_path": checker,
            "checker_sha256": checker_sha256,
            "truth_sha256": truth_sha256,
            "expected_checker_sha256": expected_checker_sha256,
            "expected_truth_sha256": expected_truth_sha256,
            "evaluator_source": evaluator_source}


def validate_t1_candidate(*, adapter_py, candidate_source, candidate_sha256,
                          work, taskdir, sb, checker_sha256, truth_sha256,
                          outdir=None, jail_factory=None):
    """A12d D1 — T1 candidate validation path (two jails, evidence on
    failure, input lineage).

    Order of operations, in-jail where noted:
      1. write the T1 response's `adapter_py` to `<work>/adapter.py`;
         `adapter_sha256` = sha256 of exactly those bytes (missing/empty
         adapter_py is EXPERIMENTAL failure `adapter-missing`, never
         silently validated);
      2. run `python3 /work/adapter.py /task /work/cand_in` in the RAW-TASK
         jail `sb` (its /task is the staged T1 tree; the adapter
         legitimately reads raw T1). Non-zero rc is experimental failure
         `adapter-failed`;
      3. stage the adapter's output as a mountable candidate-input source
         (fail closed CANDIDATE-INPUT-DENY on any symlink, non-regular
         file, or hardlink in an EXISTING tree; an adapter that produced
         no input tree stages EMPTY — the candidate still runs, and its
         failure is the evidence);
      4. materialize the deterministic candidate-input content manifest
         (CANDIDATE-INPUT-MANIFEST.json, schema
         candidate-input-manifest-v1) over the staged bytes;
         `candidate_input_manifest_sha256` = sha256 of the persisted
         manifest file bytes, `candidate_input_tree_sha256` = the
         manifest's tree hash (null pair only when the adapter never ran,
         i.e. adapter-missing — an empty staged tree still manifests);
      5. write the frozen T0 candidate source to the candidate jail's own
         workdir and verify sha256 == frozen T0 candidate sha
         (`candidate-bytes-mismatch` on drift);
      6. run `python3 /work/candidate.py /task /work/CANDIDATE-OUTPUT.json`
         in the SECOND jail — jail_factory(cand_work, cand_staging)
         (default jail_factory=None builds the production
         DockerSandbox(cand_work, cand_staging); a test seam may supply
         a shim factory with the same (work_dir, visible_root) call
         shape returning .run(argv, timeout=...) + .task_snapshot),
         whose /task is the staged candidate input ONLY — never the raw
         task tree. Non-zero rc is experimental failure
         `candidate-failed`;
      7. HOST-SIDE: run the FROZEN T1 evaluator — the same checker + truth
         the T1 cell verdict uses (shas passed in from the committed
         evaluator link) — over CANDIDATE-OUTPUT.json. Missing output is
         `candidate-output-missing`; checker rc != 0 is `checker-failed`;
      8. `validated` = the five-way conjunction (adapter rc 0, candidate
         rc 0, checker rc 0, validation_verdict ship, executed == frozen).
         The caller commits EXACTLY ONE `candidate-validation` chain event
         carrying the eleven keys (success) or the eleven keys with
         observed values plus `validation_failure` (failure).

    EXPERIMENTAL vs INFRASTRUCTURE (A12d.2 B1 — the boundary):
      experimental (RETURNED as validated=false + named cause, never
        raised): adapter-missing, adapter-failed, candidate-input-deny
        (CANDIDATE-INPUT-DENY symlinks/specials/hardlinks),
        candidate-input-unreadable (incl. a tree that vanishes mid-flight:
        candidate-input-missing), candidate-bytes-mismatch,
        candidate-failed, candidate-output-missing, checker-failed,
        evaluator-provenance-absent, evaluator-drift. A missing input
        tree at stage time stages EMPTY (the candidate still runs; an
        empty tree is observed evidence, so the lineage pair stays
        non-null).
      infrastructure (RAISED, never converted): docker unavailable at exec
        time (daemon-unreachable rc 125), sandbox staging/stability denials
        from DockerSandbox construction (MOUNT-POLICY/STAGE/STABILITY-DENY
        PermissionErrors), timeouts, and filesystem errors creating the
        jail/staging directories themselves (OSError). These propagate
        untouched so a broken harness can never mint failed-experiment
        evidence.
    The returned dict keeps every A12c key and adds the two lineage keys;
    stdlib only; never asserts.
    """
    ensure_roots()
    prov_checker = checker_sha256 if isinstance(checker_sha256, str) else None
    prov_truth = truth_sha256 if isinstance(truth_sha256, str) else None

    def _fail(cause, adapter_sha=None, executed_sha=None,
              candidate_output_sha=None, checker_rc=None,
              validation_verdict=None, manifest_sha=None, tree_sha=None):
        return {"candidate_sha256": candidate_sha256,
                "executed_sha256": executed_sha,
                "adapter_sha256": adapter_sha,
                "candidate_output_sha256": candidate_output_sha,
                "checker_sha256": prov_checker,
                "truth_sha256": prov_truth,
                "checker_returncode": checker_rc,
                "validation_verdict": validation_verdict,
                "validated": False,
                "candidate_input_manifest_sha256": manifest_sha,
                "candidate_input_tree_sha256": tree_sha,
                "validation_failure": cause}

    # 1. adapter bytes (fail closed when the T1 response omits adapter_py;
    #    never silently validate).
    if not isinstance(adapter_py, str) or not adapter_py.strip():
        return _fail("adapter-missing: T1 response omits adapter_py (the "
                     "T1 instruction requires adapter_py with the frozen "
                     "ABI python3 adapter.py <task_dir> <out_input_dir>; "
                     "omitting it makes the run unpromotable, never "
                     "silently validated)")
    adapter_path = os.path.join(work, "adapter.py")
    with open(adapter_path, "wb") as f:
        f.write(adapter_py.encode())
    adapter_sha = h(adapter_path)
    if outdir is not None:
        try:
            shutil.copy2(adapter_path, os.path.join(outdir, "adapter.py"))
        except OSError:
            pass
    # Fresh cand_in for this validation (an adapter that does not
    # materialize the input dir fails closed at the staging step).
    cand_in = os.path.join(work, "cand_in")
    if os.path.lexists(cand_in):
        shutil.rmtree(cand_in, ignore_errors=True)
    # 2. run the adapter IN the RAW-TASK jail `sb` (the adapter is
    #    executed, not merely hashed: adapter_sha256 above is the sha256 of
    #    exactly these bytes). Infrastructure failures propagate; an
    #    in-jail non-zero rc is experimental evidence.
    adapter_p = sb.run(["python3", "/work/adapter.py", "/task",
                        "/work/cand_in"], timeout=120)
    if _infra_down(adapter_p):
        raise RuntimeError(
            "CANDIDATE-INFRA-FAIL: docker unavailable during the adapter "
            f"run (rc={adapter_p.returncode}): "
            f"{(adapter_p.stderr or '')[:200]}")
    adapter_rc = adapter_p.returncode
    if adapter_rc != 0:
        return _fail(f"adapter-failed: adapter exited non-zero "
                     f"(rc={adapter_rc}); the candidate was not validated "
                     f"on this T1 surface", adapter_sha=adapter_sha)
    # 3. stage the adapter's output as the candidate jail's /task source.
    #    A symlink/special/hardlink anywhere inside fails closed
    #    (CANDIDATE-INPUT-DENY); a missing tree fails as missing input.
    staging, denial, entries = _stage_candidate_input(cand_in)
    if denial is not None:
        return _fail(denial, adapter_sha=adapter_sha)
    # 4. deterministic candidate-input content manifest over the staged
    #    bytes (the exact bytes the candidate jail will see).
    tree_sha, _canonical = _manifest_tree_sha256(
        CANDIDATE_INPUT_MANIFEST_SCHEMA, entries)
    manifest_obj = {"schema": CANDIDATE_INPUT_MANIFEST_SCHEMA,
                    "entries": entries, "tree_sha256": tree_sha}
    manifest_file_bytes = (json.dumps(manifest_obj, sort_keys=True,
                                      indent=1) + "\n").encode()
    manifest_sha = hashlib.sha256(manifest_file_bytes).hexdigest()
    with open(os.path.join(work, "CANDIDATE-INPUT-MANIFEST.json"),
              "wb") as f:
        f.write(manifest_file_bytes)
    if outdir is not None:
        try:
            with open(os.path.join(outdir, "CANDIDATE-INPUT-MANIFEST.json"),
                      "wb") as f:
                f.write(manifest_file_bytes)
        except OSError:
            pass
    # The candidate jail's OWN writable /work: a fresh directory under
    # WORK_ROOT, deliberately NOT inside the caller's `work` (which a
    # shim/test caller may place anywhere — only the two jail mounts are
    # policy-bound, never the scratch dir). Separating it also makes an
    # adapter pre-place of the candidate's output path unaddressable by
    # construction. Filesystem errors here are infrastructure: raise.
    cand_work = tempfile.mkdtemp(prefix="famc-candwork-", dir=WORK_ROOT)
    os.chmod(cand_work, 0o700)
    # 5. frozen T0 candidate bytes (hash-verified before execution,
    #    engine-style — drift is experimental, not infra).
    cand_path = os.path.join(cand_work, "candidate.py")
    with open(cand_path, "wb") as f:
        f.write(candidate_source.encode()
                if isinstance(candidate_source, str) else candidate_source)
    executed_sha = h(cand_path)
    if executed_sha != candidate_sha256:
        return _fail(f"candidate-bytes-mismatch: materialized candidate "
                     f"bytes {executed_sha[:12]} != frozen candidate "
                     f"{str(candidate_sha256)[:12]}",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    if outdir is not None:
        try:
            shutil.copy2(cand_path, os.path.join(outdir, "candidate.py"))
        except OSError:
            pass
    # 6. run the EXACT T0 candidate bytes in the SECOND jail, whose /task
    #    is the staged candidate input ONLY (the raw task tree is not
    #    mounted there). The candidate ABI keeps its frozen two-positional
    #    shape; the input dir is now /task.
    cand_out_work = os.path.join(cand_work, "CANDIDATE-OUTPUT.json")
    if os.path.lexists(cand_out_work):
        # Pre-place guard: an adapter that wrote the candidate's output
        # path into the shared work tree must not validate a candidate
        # that writes nothing useful.
        try:
            os.unlink(cand_out_work)
        except OSError:
            pass
    factory = jail_factory or DockerSandbox
    cand_sb = factory(cand_work, staging)
    candidate_p = cand_sb.run(["python3", "/work/candidate.py", "/task",
                               "/work/CANDIDATE-OUTPUT.json"], timeout=120)
    if _infra_down(candidate_p):
        raise RuntimeError(
            "CANDIDATE-INFRA-FAIL: docker unavailable during the candidate "
            f"run (rc={candidate_p.returncode}): "
            f"{(candidate_p.stderr or '')[:200]}")
    candidate_rc = candidate_p.returncode
    if os.path.exists(cand_out_work) and outdir is not None:
        try:
            shutil.copy2(cand_out_work,
                         os.path.join(outdir, "CANDIDATE-OUTPUT.json"))
        except OSError:
            pass
    if candidate_rc != 0:
        return _fail(f"candidate-failed: the frozen T0 candidate exited "
                     f"non-zero (rc={candidate_rc}) on the adapter's "
                     f"input",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    # 7. HOST-SIDE frozen T1 evaluator over CANDIDATE-OUTPUT.json. The
    #    checker + truth are the SAME bytes the T1 cell verdict used: their
    #    shas must equal the committed evaluator link's shas (passed in as
    #    checker_sha256 / truth_sha256); any drift or absence is
    #    experimental (the validation binds no frozen evaluator).
    checker = os.path.normpath(os.path.join(taskdir, "..", "check.py"))
    truth_path = os.path.normpath(os.path.join(taskdir, "..", "truth.json"))
    live_checker_sha = h(checker) if os.path.exists(checker) else None
    live_truth_sha = h(truth_path) if os.path.exists(truth_path) else None
    if not isinstance(checker_sha256, str) or not isinstance(truth_sha256,
                                                              str):
        return _fail("evaluator-provenance-absent: T1 evaluator provenance "
                     f"absent (checker_sha256={checker_sha256!r}, "
                     f"truth_sha256={truth_sha256!r}); the frozen T1 "
                     f"checker + truth must bind the validation",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    if live_checker_sha != checker_sha256 or live_truth_sha != truth_sha256:
        return _fail("evaluator-drift: frozen T1 evaluator bytes drifted "
                     f"(checker {str(live_checker_sha)[:12]} != "
                     f"{checker_sha256[:12]} or truth "
                     f"{str(live_truth_sha)[:12]} != "
                     f"{truth_sha256[:12]}); validation runs only the "
                     f"frozen T1 checker + truth the T1 cell verdict used",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    cand_out_committed = cand_out_work
    # A12n slice D13 P0-2 (+D13c residual, T1 mirror): grade the
    # JAIL-PRODUCED bytes, never the mutable committed copy (same
    # sourcing rule as the acquisition seal — the outdir
    # CANDIDATE-OUTPUT.json copy stays as the audit artifact, but the
    # checker consumes cand_out_work and the evidence hashes it
    # pre/post checker). A work file missing at grade time is the
    # same experimental missing-output failure as before (a stale
    # outdir copy from an earlier state never grades).
    if not os.path.exists(cand_out_committed):
        return _fail("candidate-output-missing: the frozen T0 candidate "
                     f"wrote no CANDIDATE-OUTPUT.json (candidate "
                     f"rc={candidate_rc}); the T1 adapter cannot claim "
                     f"validation it did not produce",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    task_name = os.path.basename(os.path.normpath(taskdir))
    # A12n slice D13 P0-2 (T1 mirror): the graded candidate output is
    # sealed like the acquisition output — hash the exact bytes handed
    # to the checker, re-hash afterwards, and fail the VALIDATION
    # (experimental evidence, validated=false — never infra) on any
    # drift, naming the sealed bytes that were actually graded.
    _sealed_candidate_output_sha = h(cand_out_committed)
    chk = subprocess.run([sys.executable, checker, task_name,
                          cand_out_committed],
                         capture_output=True, text=True)
    checker_rc = chk.returncode
    if h(cand_out_committed) != _sealed_candidate_output_sha:
        return _fail("evaluator-input-drift: sealed candidate output "
                     f"{h(cand_out_committed)[:12]} != pre-checker seal "
                     f"{_sealed_candidate_output_sha[:12]}; the T1 checker "
                     "consumed bytes the evidence does not name",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     candidate_output_sha=_sealed_candidate_output_sha,
                     checker_rc=checker_rc,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    validation_verdict = "ship" if checker_rc == 0 else "fail"
    candidate_output_sha = h(cand_out_committed)
    # 8. validated predicate (all five) + eleven-key evidence (the caller
    #    wires exactly one chain event).
    validated = (adapter_rc == 0 and candidate_rc == 0
                 and checker_rc == 0 and validation_verdict == "ship"
                 and executed_sha == candidate_sha256)
    if not validated:
        return _fail("checker-failed: candidate output failed the host "
                     f"T1 checker (adapter rc={adapter_rc}, candidate "
                     f"rc={candidate_rc}, checker rc={checker_rc}, "
                     f"validation_verdict={validation_verdict!r}); the T1 "
                     f"SHIP is evidence for the fresh T1 solver, not "
                     f"evidence that K works on T1",
                     adapter_sha=adapter_sha, executed_sha=executed_sha,
                     candidate_output_sha=candidate_output_sha,
                     checker_rc=checker_rc,
                     validation_verdict=validation_verdict,
                     manifest_sha=manifest_sha, tree_sha=tree_sha)
    return {"candidate_sha256": candidate_sha256,
            "executed_sha256": executed_sha,
            "adapter_sha256": adapter_sha,
            "candidate_output_sha256": candidate_output_sha,
            "checker_sha256": checker_sha256,
            "truth_sha256": truth_sha256,
            "checker_returncode": checker_rc,
            "validation_verdict": validation_verdict,
            "validated": True,
            "candidate_input_manifest_sha256": manifest_sha,
            "candidate_input_tree_sha256": tree_sha}

def call(lane, prompt, outdir, tag):
    cfg = LANES[lane]
    key = open(cfg["keyfile"]).read().strip()
    # Item-3 hardening: ONE explicit generation-param set, defined once and
    # sent AND recorded identically — never two literals that can drift.
    extra_body = {"max_tokens": 9000}
    # A11b.1 (production request binding): the messages object is built
    # EXACTLY ONCE and that SAME object is handed to the wire call AND to
    # the identity record — so identity.messages_sha256 always binds the
    # bytes actually sent (never a second literal that can drift), and
    # verify_request_binding() passes on a real run instead of failing
    # closed on a missing messages hash.
    messages = [{"role": "user", "content": prompt}]
    reply, receipt, resp = recorded_call(
        cfg["base"], cfg["keyfile"], key, cfg["model"], messages, outdir,
        extra_body=extra_body, timeout=300, tag=tag,
        normalizer_id=cfg["normalizer"], return_response=True)
    # A1 (audit round 2 item 1): normalization is part of CALL CAPTURE — the
    # immutable normalized-usage artifact is written IMMEDIATELY after every
    # recorded_call, never as a post-hoc step. expect_normalizer_id pins the
    # lane's preregistered v2 adapter id; a mismatch fails closed.
    nu_path = write_normalized_usage(receipt,
                                     expect_normalizer_id=cfg["normalizer"])
    # H2 identity (LANES.md): provider-side evidence — echoed model id +
    # REQUIRED nonempty provider response id, recorded from the REAL
    # response object, never from reply-text self-report; the exact
    # request-body hash is read back from the just-written receipt (never
    # reconstructed) and bound into the identity record. record_identity
    # raises on missing echo / missing id / missing body hash (fail
    # closed); check_against_prereg raises when the echo violates the
    # frozen lane prereg.
    body_sha = json.load(open(receipt)).get("request_body_sha256")
    id_path = record_identity(outdir, cfg["base"], cfg["model"], resp,
                              extra_params=dict(extra_body), tag=tag,
                              request_body_sha256=body_sha,
                              messages=messages)
    identity_family = check_against_prereg(id_path, {
        "endpoint": cfg["base"], "requested_id": cfg["model"],
        "acceptable_echoed_ids": cfg["echo_acceptable"],
        "family": cfg["family"]})
    open(os.path.join(outdir, "raw.txt"), "w").write(reply)
    return reply, receipt, nu_path, id_path, identity_family


def exec_commit():
    """Execution-harness anchor: git HEAD at the moment of the run."""
    p = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("EXEC-COMMIT-UNAVAILABLE: "
                           + (p.stderr or p.stdout)[:200])
    return p.stdout.strip()


def freeze_anchors():
    """INSTANCE-freeze anchor (audit P0 #4 dual anchors): the frozen commit
    is FREEZE.json's freeze_commit — never an execution HEAD masquerading as
    the freeze. Verifies the git object still resolves so the chain genesis
    can bind it. Item-5: also proves FREEZE.json's recorded freeze_tree
    equals the freeze commit's tree of the frozen root (BASE) — an
    altered or stale record refuses the start here, before any model
    token is spent. Returns (freeze_commit, freeze_tree)."""
    fp = os.path.join(BASE, "FREEZE.json")
    if not os.path.exists(fp):
        raise RuntimeError("FREEZE-ANCHOR-MISSING " + fp)
    fj = json.load(open(fp))
    fc = fj.get("freeze_commit")
    if not fc:
        raise RuntimeError("FREEZE-ANCHOR-INVALID: no freeze_commit in " + fp)
    p = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", fc + "^{commit}"],
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"FREEZE-ANCHOR-UNRESOLVABLE {fc[:12]} is not a "
                           "resolvable git object at execution time")
    tree = verify_freeze_tree(BASE, fc)  # raises FROZEN-TREE-* on mismatch
    return fc, tree


def harness_manifest_sha():
    """sha256 over the executing harness code (paths + per-file sha256 of the
    modules a run imports plus this runner). Pins the exact harness bytes
    even when HEAD moves after the run. Item-5/round-2 #14: a listed
    REQUIRED module that is missing FAILS (never silently skipped — a
    skipped module would let a tampered harness pose as the pinned one)."""
    names = ["usage.py", "identity.py", "chain.py", "lock.py",
             "reuse_log.py", "seal.py", "dockersandbox.py",
             "admissibility.py"]
    files = [os.path.join(HARNESS, n) for n in names]
    files.append(os.path.abspath(__file__))
    lines = []
    for f in files:
        if not os.path.exists(f):
            raise RuntimeError(f"HARNESS-MANIFEST-MISSING {f}: required "
                               "harness module absent — refuse start")
        lines.append(f"{os.path.relpath(f, ROOT)}:{h(f)}")
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def _verify_capability(capdir, cell=None):
    """H-LOCK-008: resolve the capability ONLY by exact locked hash.
    Returns lock info dict; raises PermissionError on any mismatch.

    A11.5: when the caller is an authorized estimand cell, the capability
    directory must be EXACTLY that universe's derived registry
    (state/<block>/<universe>/<family>/capability). Being somewhere inside
    Fam-C is no longer sufficient — that was the round-3 hole that let a C
    run consume A's registry, violating PREREG §2.
    """
    r_cap = os.path.realpath(capdir)
    if cell is not None:
        denial = order_check_namespace(BASE, cell, capdir)
        if denial:
            raise PermissionError(denial)
    else:
        r_base = os.path.realpath(BASE)
        if not (r_cap == r_base or r_cap.startswith(r_base + os.sep)):
            raise PermissionError(
                "FOREIGN-REGISTRY-DENY capability dir outside the Fam-C "
                f"registry surface: {capdir}")
    lock_path = os.path.join(capdir, "CAPABILITY_LOCK.json")
    if not os.path.exists(lock_path):
        raise PermissionError("LOCK-DENY correct arm has no CAPABILITY_LOCK.json "
                              "in capability dir")
    lock = json.load(open(lock_path))
    verified = {}
    for name in ("engine.py", "manifest.json", "adapter_notes.md"):
        want = lock.get("artifacts", {}).get(name)
        if want is None:
            continue  # not a locked artifact of this capability
        verified[name] = load_artifact(lock_path, name, capdir)
    if "engine.py" not in verified:
        raise PermissionError(
            "LOCK-DENY capability lock has no engine.py artifact "
            f"({lock.get('capability_id')})")
    lock_sha = h(lock_path)
    return {"lock_path": lock_path, "lock_sha256": lock_sha,
            "capability_id": lock.get("capability_id"),
            "capability_version": lock.get("version"),
            "verified": verified,
            "engine_sha256": lock["artifacts"]["engine.py"]}


def _snapshot_verified_capability(cap_info, snapshot_dir):
    """Run-private snapshot of lock-verified capability bytes (A12n
    slice D13 P0-1 — the evaluator fix, applied to capabilities).

    Copies every verified artifact into `snapshot_dir` (a run-private
    dir), then re-hashes each written file against the lock's
    artifact map: the snapshot is byte-identical to the LOCKED bytes
    no matter when the live capability directory is mutated
    afterwards. Prompt construction and jail execution must consume
    ONLY these snapshot paths — _verify_capability() returns live
    verified paths that must never be consumed after this point.
    Returns {name: snapshot_path}. Raises PermissionError
    (CAPABILITY-SNAPSHOT-DENY) on any mismatch or any prompt-consumed
    file lacking a lock hash."""
    os.makedirs(snapshot_dir, exist_ok=True)
    lock = json.load(open(cap_info["lock_path"]))
    want_map = lock.get("artifacts") or {}
    snap = {}
    for name, live in sorted(cap_info["verified"].items()):
        want = want_map.get(name)
        if want is None:
            raise PermissionError(
                "CAPABILITY-SNAPSHOT-DENY lock carries no artifact hash "
                f"for {name!r}; refusing to snapshot unverifiable bytes")
        dst = os.path.join(snapshot_dir, os.path.basename(name))
        shutil.copy2(live, dst)
        if h(dst) != want:
            raise PermissionError(
                "CAPABILITY-SNAPSHOT-DENY snapshotted "
                f"{name} {h(dst)[:12]} != locked {want[:12]} "
                "(live bytes changed under verification; refusing)")
        snap[name] = dst
    if "engine.py" not in snap:
        raise PermissionError(
            "CAPABILITY-SNAPSHOT-DENY snapshot has no engine.py "
            "(the executed engine is always lock-bound)")
    return snap


def _wire_chain(outdir, frozen, manifest, receipt, nu_path, identity_path,
                identity_family, cap_info, reuse_path, checker_sha, truth_sha,
                verdict, output_sha, promote_info, candidate_validation=None):
    """Emit the H3 evidence chain for one completed run (fail closed).
    Genesis binds `manifest`; the on-disk H1-RUN-MANIFEST.json must never be
    rewritten after this call (rewriting would break genesis hash equality)."""
    chain_path = os.path.join(outdir, CHAIN_FILE)
    # A11b.1 pre-link gate: the request-byte binding AND the adapter-lane
    # binding are verified HERE, before any chain link is emitted — a call
    # whose persisted request bytes, identity messages hash, or adapter lane
    # do not verify is refused at the door (fail closed), instead of being
    # admitted now and rejected only later by admissibility after the run
    # artifacts are already written. The request bytes are mutation-evident
    # and execution-bound under the frozen harness trust boundary.
    try:
        with open(receipt) as _f:
            _rc0 = json.load(_f)
        verify_request_binding(receipt, identity_path)
        verify_adapter_binding(_rc0.get("normalizer_id"),
                               lane=manifest.get("lane"), receipt=_rc0)
    except (OSError, ValueError) as e:
        raise RuntimeError(f"CHAIN-BINDING-GATE-FAIL: {e}")
    c = Chain(chain_path, frozen, manifest, arm=manifest.get("arm"))
    # model-call link(s): every persisted H2 usage receipt binds here,
    # alongside the provider-identity receipt (echoed model + response id)
    # and the A1 immutable normalized-usage artifact (file hash + derived
    # metric fields ride the chain with the raw receipt).
    try:
        rc = json.load(open(receipt))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"CHAIN-RECEIPT-UNREADABLE {receipt}: {e}")
    if not os.path.exists(nu_path):
        raise RuntimeError(f"CHAIN-NORMALIZED-MISSING {nu_path}")
    # Fail closed on tampering of the RAW receipt OR the NORMALIZED artifact:
    # verify recomputes self-sha, raw-file binding, and metric re-derivation.
    nu = verify_normalized_usage(nu_path)
    # Item-3 hardening: the identity record must cross-verify against its
    # usage receipt (endpoint + model_requested + request-body hash equal,
    # echo + provider id nonempty) — altering the model or any request
    # param on either side after the call fails the chain here.
    id_rec = verify_identity_binding(identity_path, receipt)
    mc = {
        "call_id": rc.get("call_id"), "tag": rc.get("tag"),
        "model_requested": rc.get("model_requested"),
        "endpoint": rc.get("endpoint"),
        "receipt_file": os.path.basename(receipt),
        "receipt_sha256": h(receipt),
        "usage_raw_sha256": rc.get("usage_raw_sha256"),
        "request_body_sha256": rc.get("request_body_sha256"),
        "provider_response_id": id_rec.get("provider_response_id"),
        # A12b.7: bind the provider-echoed model id at capture, so a
        # post-hoc echo alteration is detectable at promotion time.
        "model_echoed": id_rec.get("model_echoed_model"),
        "generation_params": id_rec.get("generation_params"),
        "normalized_file": os.path.basename(nu_path),
        "normalized_sha256": h(nu_path),
        "primary_work": nu["primary_work"],
        "input_tokens_uncached": nu["input_tokens_uncached"],
        "output_tokens": nu["output_tokens"],
        "cached_tokens": nu["cached_tokens"],
        "call_count": 1,
        # A12n slice D13 P0-3: the provider response text, the parsed
        # arrival bytes, and the executed payload, as captured at run
        # time (read from the genesis-bound manifest, never
        # recomputed here) — later T1/promotion reads verify the
        # live arrival.json against arrival_sha256.
        "response_text_sha256": manifest.get("response_text_sha256"),
        "arrival_sha256": manifest.get("arrival_sha256"),
        "arrival_file": manifest.get("arrival_file"),
        "execution_payload_sha256": manifest.get(
            "execution_payload_sha256"),
        "solver_py_sha256": manifest.get("solver_py_sha256")}
    if identity_path is not None:
        if not os.path.exists(identity_path):
            raise RuntimeError(f"CHAIN-IDENTITY-MISSING {identity_path}")
        mc["identity_file"] = os.path.basename(identity_path)
        mc["identity_sha256"] = h(identity_path)
        mc["identity_prereg_family"] = identity_family
    c.append("model-call", mc)
    # capability events (correct arm only). A12b.4: ONE lifecycle object
    # decides the chain flags and the reuse ledger — the event serializes
    # the reuse record's own lifecycle facts, never an asserted triple. On
    # a REJECT run the chain says rejected/not-loaded/not-invoked/not-
    # consumed exactly as the ledger does.
    if cap_info:
        if not reuse_path or not os.path.isfile(reuse_path):
            raise RuntimeError(
                "CHAIN-LIFECYCLE-DENY: capability available but no reuse "
                "ledger to derive the lifecycle from (ledger and chain "
                "share one lifecycle object)")
        try:
            ledger = json.load(open(reuse_path))
        except ValueError as e:
            raise RuntimeError(
                f"CHAIN-LIFECYCLE-DENY: reuse ledger unreadable: {e}")
        loaded = ledger.get("capability_loaded") is True
        invoked = ledger.get("capability_invoked") is True
        consumed = ledger.get("capability_output_consumed") is True
        contributed = ledger.get("capability_materially_contributed") is True
        rejected = ledger.get("reuse_rejected") is True
        if rejected:
            evidence = ("rejected: capability available but not selected "
                        "(fresh decision); loaded/invoked/consumed false — "
                        "see the reuse ledger for the recorded reason")
        else:
            evidence = ("consumed but not proven contributed: no ablation "
                        "or downstream-node hash-linkage in this cell")
        c.append("capability-event", {
            "event": "reuse", "capability_id": cap_info["capability_id"],
            "capability_version": cap_info.get("capability_version"),
            "lock_sha256": cap_info["lock_sha256"],
            "engine_sha256": cap_info["engine_sha256"],
            # A12n slice D13 P0-1: the snapshot that was actually
            # consumed (prompt + execution), never the live dir.
            "capability_snapshot": (dict(cap_info["snapshot"])
                                    if cap_info.get("snapshot") else None),
            "verified_pre_execution": True,
            "loaded": loaded, "invoked": invoked,
            "output_consumed": consumed,
            "rejected": rejected, "reuse_rejected": rejected,
            "capability_available": ledger.get("capability_available"),
            "capability_selected": ledger.get("capability_selected"),
            "selected_capability_id": ledger.get("selected_capability_id"),
            "reuse_rejection_reason": ledger.get("reuse_rejection_reason"),
            "materially_contributed": contributed,
            "evidence": evidence})
    # A12c D2/D4 + A12d D1: exactly one candidate-validation event on a T1
    # acquisition run — the eleven-field host-checker + input-lineage
    # evidence. The promotion controller re-derives this committed event
    # from the chain (never the receipt); a T1 chain without it can never
    # promote. On the success path (validated is True) shape AND passing
    # values are enforced here (fail closed); the candidate binding is
    # enforced at promotion time. adapter_sha256 is the sha256 of the exact
    # adapter bytes the runner executed (D4: executed, not merely hashed).
    # On the experimental-failure path (validated is False, A12d D1-B2)
    # the FULL event is committed with observed values (null where
    # unobserved) plus the named `validation_failure` cause — the T1 cell
    # still COMPLETES as committed experimental evidence, and promotion
    # later records NOT-PROMOTED from this event (never a lock).
    if candidate_validation is not None:
        cv = candidate_validation
        if cv.get("validated") is True:
            if set(cv) != set(CV_ELEVEN):
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: validated event must carry "
                    f"exactly the eleven keys {sorted(CV_ELEVEN)}, got "
                    f"{sorted(cv)}")
            for f in ("candidate_sha256", "executed_sha256",
                      "adapter_sha256", "candidate_output_sha256",
                      "checker_sha256", "truth_sha256",
                      "candidate_input_manifest_sha256",
                      "candidate_input_tree_sha256"):
                if not (isinstance(cv.get(f), str) and len(cv[f]) == 64):
                    raise RuntimeError(f"CHAIN-CANDIDATE-DENY: {f} must be "
                                       f"64-hex, got {cv.get(f)!r}")
                try:
                    int(cv[f], 16)
                except ValueError:
                    raise RuntimeError(f"CHAIN-CANDIDATE-DENY: {f} must be "
                                       f"64-hex, got {cv[f]!r}") from None
            if not isinstance(cv.get("checker_returncode"), int):
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: checker_returncode must be an "
                    f"int (got {cv.get('checker_returncode')!r})")
            if cv.get("checker_returncode") != 0:
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: checker_returncode "
                    f"{cv.get('checker_returncode')!r} != 0 (the host T1 "
                    "checker must pass over CANDIDATE-OUTPUT.json)")
            if cv.get("validation_verdict") != "ship":
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: validation_verdict "
                    f"{cv.get('validation_verdict')!r} != 'ship' (the host "
                    "T1 checker must pass over CANDIDATE-OUTPUT.json)")
            c.append("candidate-validation", {
                k: cv[k] for k in CV_ELEVEN})
        elif cv.get("validated") is False:
            if set(cv) != set(CV_ELEVEN) | {"validation_failure"}:
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: failed-validation event must "
                    "carry exactly the eleven keys plus "
                    f"validation_failure, got {sorted(cv)}")
            if not (isinstance(cv.get("validation_failure"), str)
                    and cv["validation_failure"].strip()):
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: failed validation needs a named "
                    f"validation_failure cause, got "
                    f"{cv.get('validation_failure')!r}")
            for f in ("candidate_sha256", "executed_sha256",
                      "adapter_sha256", "candidate_output_sha256",
                      "checker_sha256", "truth_sha256",
                      "candidate_input_manifest_sha256",
                      "candidate_input_tree_sha256"):
                if cv.get(f) is not None and not (
                        isinstance(cv[f], str) and len(cv[f]) == 64):
                    raise RuntimeError(f"CHAIN-CANDIDATE-DENY: {f} must be "
                                       f"64-hex-or-null, got {cv.get(f)!r}")
                if isinstance(cv.get(f), str):
                    try:
                        int(cv[f], 16)
                    except ValueError:
                        raise RuntimeError(
                            f"CHAIN-CANDIDATE-DENY: {f} must be 64-hex-or-"
                            f"null, got {cv[f]!r}") from None
            if cv.get("checker_returncode") is not None and not isinstance(
                    cv.get("checker_returncode"), int):
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: checker_returncode must be an "
                    "int-or-null "
                    f"(got {cv.get('checker_returncode')!r})")
            if cv.get("validation_verdict") is not None and cv.get(
                    "validation_verdict") not in ("ship", "fail"):
                raise RuntimeError(
                    "CHAIN-CANDIDATE-DENY: validation_verdict must be "
                    "ship/fail-or-null "
                    f"(got {cv.get('validation_verdict')!r})")
            c.append("candidate-validation", dict(cv))
        else:
            raise RuntimeError("CHAIN-CANDIDATE-DENY: validated must be "
                               f"exactly True or False, got "
                               f"{cv.get('validated')!r}")
    # evaluator link: sealed truth + checker hashes + host-side outcome.
    # A12n slice D13 P0-2: the link also binds the sealed graded
    # output bytes (read from the manifest, never recomputed here).
    ev_link = c.append("evaluator", {
        "checker_sha256": checker_sha, "truth_sha256": truth_sha,
        "output_sha256": output_sha,
        "graded_output_sha256": manifest.get("graded_output_sha256"),
        "checker_returncode": manifest.get("checker_returncode"),
        "verdict": verdict})
    # promotion event (a capability ship) — before the terminal grade.
    if promote_info:
        c.append("capability-event", {
            "event": "promote", "capability_id": promote_info["capability_id"],
            "lock_file": os.path.basename(promote_info["lock_path"]),
            "lock_sha256": promote_info["lock_sha256"],
            "builder": promote_info["builder"]})
    c.append("grade", {
        "grade": verdict, "evaluator_link_hash": ev_link,
        "grading_rule_hash": checker_sha,
        "grading_rule_version": GRADING_RULE_VERSION,
        "grading_rule_note": GRADING_RULE_NOTE})
    findings = c.audit(frozen, manifest)
    if findings:
        raise RuntimeError("CHAIN-AUDIT-FAIL: " + "; ".join(findings))
    return c.tip


def selfcheck_wire():
    """Offline fixture compose-test of the wiring (no model call, no docker,
    no run, no claim-grade artifact). Returns 0 when green."""
    # Fixture lives INSIDE the Fam-C registry surface: the item-7
    # foreign-registry refusal is absolute, so the offline selfcheck must
    # exercise the real path rather than an exempt temp dir.
    tmp = tempfile.mkdtemp(prefix=".selfcheck-wire-", dir=BASE)
    try:
        capdir = os.path.join(tmp, "capstore")
        os.makedirs(capdir)
        open(os.path.join(capdir, "engine.py"), "w").write(
            "def run(fm, rec, out):\n    open(out, 'w').write('{}')\n")
        open(os.path.join(capdir, "manifest.json"), "w").write(
            json.dumps({"capability": "fixture"}))
        open(os.path.join(capdir, "adapter_notes.md"), "w").write("fixture")
        receipt = os.path.join(tmp, "call-fixture.json")
        raw_usage = {"prompt_tokens": 10, "completion_tokens": 5,
                     "total_tokens": 15,
                     "prompt_tokens_details": {"cached_tokens": 2}}
        raw_usage_sha = hashlib.sha256(
            json.dumps(raw_usage, sort_keys=True).encode()).hexdigest()
        # A11.2: a v2 adapter id IS a lane binding, so a synthetic fixture
        # must either use the lane's real bound endpoint/model or a v1
        # adapter. The fixture mirrors the kenari lane's bound values and
        # persists its request bytes like every real receipt (P1 ordering:
        # the SAME dict that is written below is hashed, and its generation
        # fields must equal the identity record's extra_params, exactly as
        # recorded_call + record_identity produce on a real call).
        fx_body = {"max_tokens": 9000,
                   "model": "agnes-2-0-flash:free",
                   "messages": [{"role": "user", "content": "selfcheck"}]}
        fx_req = os.path.join(tmp, "call-fixture.request.json")
        with open(fx_req, "wb") as f:
            f.write(json.dumps(fx_body).encode())
        fx_sha = hashlib.sha256(open(fx_req, "rb").read()).hexdigest()
        json.dump({"call_id": "fx-1", "tag": "selfcheck",
                   "model_requested": "agnes-2-0-flash:free",
                   "endpoint": "https://kenari.id/v1",
                   "request_body_sha256": fx_sha,
                   "request_body_file": "call-fixture.request.json",
                   "request_body_file_sha256": fx_sha,
                   "usage_raw": raw_usage, "usage_raw_sha256": raw_usage_sha,
                   "normalizer_id": "kenari-openai-chat-v2",
                   "normalizer_version": "usage-norm-v1",
                   "normalizer_rule": "selfcheck fixture"},
                  open(receipt, "w"))
        # A1: immediate immutable normalization (kenari shape: 10 total
        # prompt, 2 cached -> 8 uncached; 5 output -> primary_work 13).
        nu_path = write_normalized_usage(receipt)
        assert os.path.exists(nu_path), "normalized artifact not written"
        nu = json.load(open(nu_path))
        assert nu["primary_work"] == 13, "fixture primary_work != 13"
        assert nu["raw_receipt_sha256"] == hashlib.sha256(
            open(receipt, "rb").read()).hexdigest()
        verify_normalized_usage(nu_path)  # raises on any mismatch
        # Fixture lane is Q: the receipt/identity above bind kenari values
        # (lane Q) exactly as a real call would, and the pre-link gate below
        # verifies manifest lane == adapter bound lane.
        manifest = {"lane": "Q", "family": "famXX", "task": "T0", "arm": "correct",
                    "wired": True, "frozen_commit": "deadbeef" * 5,
                    "usage_receipts": [os.path.basename(receipt)],
                    "usage_normalized": [os.path.basename(nu_path)],
                    "identity_file": "identity.json",
                    "checker_returncode": 0, "output_sha256": "fx",
                    "verdict": "ship"}
        # promote composes (writes once) and load_artifact verifies by hash.
        # A12.2 lock contract: promote requires the full estimand set (a lock
        # may only be minted from a validated promotion, never from whatever
        # artifacts sit in a dir) — the fixture supplies labeled synthetic
        # values, identical for both the compose and the refusal probes.
        _fx_promote = dict(
            block="PQ", universe="u-fixture", family="famXX-fixture",
            acquisition_chain_tips={"T0": "1" * 64, "T1": "2" * 64},
            source_cells={"T0": "famXX-fixture/T0",
                          "T1": "famXX-fixture/T1"},
            producer_identity={"lane": "Q", "builder": "selfcheck"},
            protocol_lock_sha256="3" * 64, execution_lock_sha256="4" * 64,
            semantic_core="selfcheck fixture: no semantic claim",
            preconditions=[{"requires_all": ["fixture"]}],
            limitations=["fixture"],
            declared_limitations_present=True, non_discriminating=False,
            conformance_cause=("selfcheck fixture: synthetic limitation "
                               "present, T4 treated as discriminating"),
            # A12c slice C2: the frozen bridge fields (the synthetic id
            # is its own sole supported member, so the claimed
            # discrimination is set-consistent).
            supported_t4_ids=["famXX-fixture-selfcheck"],
            conformance_map_sha256="8" * 64,
            t4_semantic_id="famXX-fixture-selfcheck",
            evidence_grade="harness-validation",
            candidate_sha256="5" * 64,
            candidate_provenance_sha256="6" * 64,
            promotion_receipt_sha256="7" * 64)
        lock_path = lock_promote(
            capdir, "famXX-fixture", "v1",
            [os.path.join(capdir, "engine.py"),
             os.path.join(capdir, "manifest.json"),
             os.path.join(capdir, "adapter_notes.md")],
            manifest, [receipt],
            {"lane": "Q", "builder": "selfcheck"}, **_fx_promote)
        assert os.path.exists(lock_path), "promote did not write lock"
        v = load_artifact(lock_path, "engine.py", capdir)
        assert v.endswith("engine.py"), "load_artifact wrong path"
        cap = _verify_capability(capdir)
        assert cap["engine_sha256"] == h(os.path.join(capdir, "engine.py"))
        reuse = reuse_write_record(
            tmp, "famXX-T0", "Q", "correct",
            reuse_policy="prereg-frozen", capability_available=True,
            capability_candidate_ids=[cap["capability_id"]],
            capability_selected=True,
            selected_capability_id=cap["capability_id"],
            selected_capability_hash=cap["engine_sha256"],
            capability_loaded=True, capability_invoked=True,
            capability_output_consumed=True,
            capability_materially_contributed=False,
            contribution_evidence={"mechanism": "none",
                                   "reason": "selfcheck fixture"},
            reuse_rejected=False, reuse_rejection_reason=None)
        assert os.path.exists(reuse), "reuse record not written"
        # H2 identity composes: provider-side echo record + prereg pass.
        # Item-3: nonempty provider id + exact request-body hash required.
        # A11.2: the identity fixture must agree with the receipt's bound
        # lane values and persisted request bytes, exactly as a real call
        # would; otherwise the binding probes below would trip on the
        # fixture rather than on the defect under test.
        idp = record_identity(tmp, "https://kenari.id/v1",
                              "agnes-2-0-flash:free",
                              {"model": "agnes-2-0-flash", "id": "fx-1",
                               "created": 1},
                              extra_params={"max_tokens": 9000},
                              tag="selfcheck",
                              request_body_sha256=fx_sha,
                              messages=fx_body["messages"])
        assert check_against_prereg(
            idp, {"endpoint": "https://kenari.id/v1",
                  "requested_id": "agnes-2-0-flash:free",
                  "acceptable_echoed_ids": ["agnes-2-0-flash:free",
                                            "agnes-2-0-flash"],
                  "family": "famXX-fixture"}) == "famXX-fixture"
        try:
            record_identity(tmp, "https://fx/v1", "fx", {"id": "fx-1"},
                            extra_params=None, tag="selfcheck",
                            request_body_sha256="fx-req-body")
            raise SystemExit("selfcheck FAIL: no-echo identity not refused")
        except ValueError:
            pass  # IDENTITY-INCOMPLETE: echoed model id missing -> fail closed
        for bad_resp, why in (({"model": "fx"}, "no provider id"),
                              ({"model": "fx", "id": "  "}, "empty provider id")):
            try:
                record_identity(tmp, "https://fx/v1", "fx", bad_resp,
                                extra_params=None, tag="selfcheck",
                                request_body_sha256="fx-req-body")
                raise SystemExit(f"selfcheck FAIL: {why} not refused")
            except ValueError:
                pass  # IDENTITY-INCOMPLETE: provider id required -> fail closed
        try:
            record_identity(tmp, "https://fx/v1", "fx",
                            {"model": "fx", "id": "fx-1"},
                            extra_params=None, tag="selfcheck")
            raise SystemExit("selfcheck FAIL: missing body hash not refused")
        except ValueError:
            pass  # IDENTITY-INCOMPLETE: request-body hash required
        # Item-3: identity/receipt binding verifies; altering the model on
        # either side breaks _wire_chain (chain fail closed).
        verify_identity_binding(idp, receipt)
        _alt = os.path.join(tmp, "call-fixture-alt.json")
        _alt_rc = json.load(open(receipt))
        _alt_rc["model_requested"] = "fx-tampered"
        json.dump(_alt_rc, open(_alt, "w"))
        try:
            verify_identity_binding(idp, _alt)
            raise SystemExit("selfcheck FAIL: model alteration not refused")
        except ValueError:
            pass  # IDENTITY-BINDING-MISMATCH -> fail closed
        tip = _wire_chain(tmp, manifest["frozen_commit"], manifest, receipt,
                          nu_path, idp, "famXX-fixture", cap, reuse,
                          h(os.path.join(capdir, "engine.py")), None, "ship",
                          "fx", None)
        assert isinstance(tip, str) and len(tip) == 64, "bad chain tip"
        # A1: the model-call link must carry the normalized artifact hash +
        # derived metric fields (primary_work / uncached / output / cached /
        # call count) bound beside the raw receipt hash.
        links = [json.loads(l) for l in open(os.path.join(tmp, CHAIN_FILE))
                 if l.strip()]
        mc_payload = next(l["payload"] for l in links
                          if l.get("kind") == "model-call")
        assert mc_payload.get("normalized_file") == os.path.basename(nu_path)
        assert mc_payload.get("normalized_sha256") == h(nu_path), \
            "chain lacks/alters normalized artifact sha"
        assert mc_payload.get("primary_work") == 13, "chain primary_work != 13"
        assert mc_payload.get("input_tokens_uncached") == 8
        assert mc_payload.get("output_tokens") == 5
        assert mc_payload.get("cached_tokens") == 2
        assert mc_payload.get("call_count") == 1
        # Item-3: the model-call link carries the provider response id, the
        # exact request-body hash, and the complete generation-param set.
        assert mc_payload.get("provider_response_id") == "fx-1"
        assert mc_payload.get("request_body_sha256") == fx_sha
        assert mc_payload.get("generation_params") == {"max_tokens": 9000}
        # repromotion refused (H-LOCK-008 writes-once).
        try:
            lock_promote(capdir, "famXX-fixture", "v2",
                         [os.path.join(capdir, "engine.py")], manifest,
                         [receipt], {"lane": "Q"}, **_fx_promote)
            raise SystemExit("selfcheck FAIL: repromotion not refused")
        except PermissionError:
            pass
        assert os.path.exists(os.path.join(tmp, CHAIN_FILE))
        print("WIRE-SELFCHECK ok: promote/load_artifact/reuse/chain compose "
              "(fixture, not a run)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selfcheck_prompt():
    """Offline proof of the item-6 prompt path on a REAL frozen task
    (fam05/T0), no model / no docker / no network: one staged snapshot ->
    canonical envelope -> both arms, plus the two refusal gates."""
    ensure_roots()
    tmp = tempfile.mkdtemp(prefix="rcos-prompt-selfcheck-")
    capdir = os.path.join(tmp, "cap")
    os.makedirs(capdir)
    open(os.path.join(capdir, "engine.py"), "w").write(
        "def run(field_map, records):\n    return records\n")
    open(os.path.join(capdir, "manifest.json"), "w").write(
        '{"capability_id": "fx-prompt", "version": "v1"}')
    open(os.path.join(capdir, "adapter_notes.md"), "w").write(
        "fixture notes; never sent to a model\n")
    cor = prepare_arm("P", "fam05", "T0", "correct", capdir, False, "sc-cor")
    dis = prepare_arm("Q", "fam05", "T0", "disabled", None, False, "sc-dis")
    # 1. real pair passes the mechanical symmetry check with no findings.
    assert cor["symmetry"] == [] and dis["symmetry"] == [], "symmetry findings"
    # 2. delimiters: exactly once in treatment, absent in control.
    assert cor["prompt"].count(_CAP_BEGIN) == 1
    assert cor["prompt"].count(_CAP_END) == 1
    assert _CAP_BEGIN not in dis["prompt"] and _CAP_END not in dis["prompt"]
    # 3. both arms embed the SAME envelope bytes (one source snapshot).
    assert cor["envelope"] == dis["envelope"], "envelope differs across arms"
    assert cor["prompt"].count(cor["envelope"]) == 1
    assert dis["prompt"].count(cor["envelope"]) == 1
    # 4. context snapshot == sandbox staged snapshot (byte binding).
    sb = DockerSandbox(cor["work"], cor["visible"])
    assert sb.task_snapshot == cor["staged_tree"], "snapshot binding broken"
    # 5. ONE-BYTE asymmetry in the SHARED region is caught (verbatim
    #    envelope embedding breaks), while a change INSIDE the delimited
    #    capability block is correctly allowed (that bit is treatment-only).
    shared = dis["prompt"].replace(cor["envelope"], cor["envelope"][:-1] + "Z")
    assert check_arm_symmetry(cor["prompt"], shared, cor["envelope"]) != []
    in_block = cor["prompt"].replace("fixture notes", "fixture note5", 1)
    assert in_block != cor["prompt"]
    assert check_arm_symmetry(in_block, dis["prompt"], cor["envelope"]) == [], \
        "capability-block content must be the only permitted difference"
    # 6. a drifted staged root breaks the context snapshot binding.
    os.rename(os.path.join(cor["visible"], "alpha.txt"),
              os.path.join(cor["visible"], "alpha.txt.bak"))
    assert _hash_tree(cor["visible"]) != cor["staged_tree"]
    print("PROMPT-SELFCHECK ok: real fam05/T0 pair — one staged snapshot, "
          "canonical envelope, delimited capability block, symmetry "
          "fail-closed (offline fixture, not a run)")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


def prepare_arm(lane, family, task, arm, capdir, wire, run_id,
                cell=None, candidate=None):
    """Item-6 ONE SOURCE SNAPSHOT (audit round 2 item 6).

    Stage the agent-visible root ONCE (sealed copy: prompt.md + declared
    fixtures only). The MODEL CONTEXT and the docker /task mount are both
    built from these exact staged bytes — never from two independent reads
    of the frozen task dir — and the two hashes must agree. The prompt is
    assembled from one canonical envelope plus, for the treatment arm, one
    mechanically delimited capability-access block; the pair must pass the
    symmetry check BEFORE any model token is spent.
    """
    taskdir = os.path.join(BASE, "families", family, task)
    work = os.path.join("/tmp/rcos-runs", "famc-" + run_id)
    visible = os.path.join("/tmp/rcos-visible", "famc-" + run_id)
    os.makedirs(work, exist_ok=True)
    copied, refused = build_visible_root(taskdir, visible)
    staged_tree = _hash_tree(visible)
    taskdef = open(os.path.join(visible, "prompt.md")).read()
    listing = ", ".join(sorted(os.listdir(visible)))
    blobs = []
    read_files = {}
    for root, _dirs, files in os.walk(visible):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, visible)
            data = open(p, "rb").read()
            read_files[f"file|{rel}"] = hashlib.sha256(data).hexdigest()
            if rel != "prompt.md":
                blobs.append(f"--- {rel} ---\n" + data.decode())
    block = "\n".join(blobs)
    envelope = build_envelope(taskdef, listing, block)
    # The model context must BE the staged bytes: every file hash read into
    # the prompt equals the staged tree's file hash (dirs are irrelevant to
    # prompt content but ride the tree binding below).
    staged_files = {k: v for k, v in staged_tree.items()
                    if k.startswith("file|")}
    if read_files != staged_files:
        drift = sorted(set(read_files.items()) ^ set(staged_files.items()))
        raise RuntimeError(
            f"CONTEXT-SNAPSHOT-DENY prompt bytes != staged snapshot bytes: "
            f"{drift[:3]}")
    context_task_snapshot_hash = hashlib.sha256(json.dumps(
        staged_tree, sort_keys=True).encode()).hexdigest()
    cap_info = None
    cap_engine = None
    if arm == "correct":
        if not capdir:
            raise ValueError("correct arm requires locked capability dir")
        if wire:
            # H-LOCK-008: resolve the executed engine by exact locked hash
            # BEFORE it enters the jail. Dev-escape (unwired) copies unverified.
            cap_info = _verify_capability(capdir, cell=cell)
            # A12n slice D13 P0-1: check-then-use closure. The verified
            # live paths above are NEVER consumed afterwards: every
            # verified artifact is snapshotted into a run-private dir
            # (re-hashed against the lock at snapshot time) and the
            # prompt plus the jail execution consume ONLY the snapshot
            # — a capability dir rewritten after verification steers
            # nothing and executes nothing.
            cap_snapshot = _snapshot_verified_capability(
                cap_info, os.path.join(work, "capability-snapshot"))
            cap_info["snapshot"] = {
                "dir": os.path.join(work, "capability-snapshot"),
                "files": {n: h(p)
                          for n, p in sorted(cap_snapshot.items())}}
            cap_engine = cap_snapshot["engine.py"]
            for _need in ("manifest.json", "adapter_notes.md"):
                if _need not in cap_snapshot:
                    raise PermissionError(
                        "CAPABILITY-SNAPSHOT-DENY prompt-consumed "
                        f"capability file {_need!r} has no lock-verified "
                        "snapshot; the treatment prompt consumes ONLY "
                        "snapshot bytes (refused)")
            prompt = build_arm_prompt(
                "correct", envelope,
                open(cap_snapshot["manifest.json"]).read(),
                open(cap_snapshot["adapter_notes.md"]).read(),
                open(cap_engine).read())
        else:
            cap_engine = os.path.join(capdir, "engine.py")
            prompt = build_arm_prompt(
                "correct", envelope,
                open(os.path.join(capdir, "manifest.json")).read(),
                open(os.path.join(capdir, "adapter_notes.md")).read(),
                open(cap_engine).read())
        twin = build_arm_prompt("disabled", envelope)
        sym = check_arm_symmetry(prompt, twin, envelope)
    else:
        base = build_arm_prompt("disabled", envelope)
        acq_t1 = (arm == "acquisition" and cell is not None
                  and cell.get("event") == "T1")
        acq_t0 = (arm == "acquisition" and cell is not None
                  and cell.get("event") == "T0")
        if acq_t1:
            # A12b.2: a T1 acquisition prompt carries the frozen T0
            # candidate in the delimited candidate-validation block (T1
            # sees the exact candidate). The block sits strictly after
            # the shared envelope, exactly once; removing both block
            # types must recover the capability-free base bytes.
            # A12c D1: the T1 producer instruction additionally requires
            # `adapter_py` (frozen ABI python3 adapter.py <task_dir>
            # <out_input_dir>, exit non-zero on failure, omission is
            # unpromotable). T0's instruction (_OUT) is unchanged.
            if candidate is None:
                raise ValueError(
                    "CANDIDATE-VALIDATION-DENY: a T1 acquisition prompt "
                    "requires the frozen T0 candidate (sha256 + immutable "
                    "source); a T1 that never sees the candidate can "
                    "never promote")
            block = build_candidate_validation_block(
                candidate["sha256"], candidate["source"])
            base_t1 = _PRE + envelope + _OUT_T1
            prompt = _PRE + envelope + block + _OUT_T1
            sym = []
            if prompt.count(_CAND_BEGIN) != 1 \
                    or prompt.count(_CAND_END) != 1:
                sym.append("SYMMETRY-FAIL: candidate-validation "
                           "delimiters != 1 each in the T1 prompt")
            elif strip_capability_block(prompt) != base_t1:
                sym.append("SYMMETRY-FAIL: T1 prompt minus the "
                           "candidate-validation block != the "
                           "capability-free base - shared-region "
                           "divergence at "
                           + _first_diff(strip_capability_block(prompt),
                                         base_t1))
            if not prompt.startswith(_PRE) or not prompt.endswith(_OUT_T1):
                sym.append("SYMMETRY-FAIL: T1 prompt does not carry the "
                           "shared preamble and output contract")
        elif acq_t0:
            # A12c slice B (B1): a T0 acquisition prompt carries the T0
            # producer instruction (_OUT_T0: solver_py + producer-authored
            # capability_contract), with no capability-access block and no
            # candidate-validation block (neither exists at T0). Removing
            # both block types must be a no-op on these bytes.
            prompt = _PRE + envelope + _OUT_T0
            sym = []
            for _begin, _end, _what in (
                    (_CAP_BEGIN, _CAP_END, "capability-access"),
                    (_CAND_BEGIN, _CAND_END, "candidate-validation")):
                if _begin in prompt or _end in prompt:
                    sym.append("SYMMETRY-FAIL: " + _what + " block present "
                               "in the T0 acquisition prompt (neither "
                               "exists before PROMOTION)")
            if not prompt.startswith(_PRE) or not prompt.endswith(_OUT_T0):
                sym.append("SYMMETRY-FAIL: T0 prompt does not carry the "
                           "shared preamble and the T0 producer instruction")
            if strip_capability_block(prompt) != prompt:
                sym.append("SYMMETRY-FAIL: T0 prompt carries a strippable "
                           "block - shared-region divergence at "
                           + _first_diff(strip_capability_block(prompt),
                                         prompt))
        else:
            prompt = base
            twin = build_arm_prompt("correct", envelope, COUNTERFACTUAL_CAP,
                                    COUNTERFACTUAL_CAP, COUNTERFACTUAL_CAP)
            sym = check_arm_symmetry(twin, prompt, envelope)
    # H-CTX-002 mechanical pair symmetry: any one-byte hint asymmetry in
    # the shared region, any stray capability block, or a missing/duplicate
    # delimiter FAILS CLOSED before any model call.
    if sym:
        raise RuntimeError("SYMMETRY-DENY refuse start: " + " | ".join(sym))
    return {"prompt": prompt, "envelope": envelope, "work": work,
            "visible": visible, "copied": copied, "refused": refused,
            "staged_tree": staged_tree,
            "context_task_snapshot_hash": context_task_snapshot_hash,
            "symmetry": sym, "cap_info": cap_info, "cap_engine": cap_engine}


def _a13_looks_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value)


def execute_a13_legs(*, family, task, cap_info, cap_engine, on_exec,
                     freeze_commit, famc_dir, taskdir, work, outdir,
                     task_snapshot_sha256, evaluator_authority,
                     captured_response_sha256=None, cell_id=None,
                     jail_factory=None, sb=None):
    """A13 executed counterfactual legs (auditor ruling, A13_CAUSAL).

    Three deterministic counterfactual sub-executions INSIDE the one
    real treatment cell, all downstream of the single already-captured
    arrival: ON (the cell's own locked-engine execution, evidence
    harvested -- never re-run), OFF-noop (the frozen NOOP_v1 pair
    through the SAME locked engine behind the same ABI, graded by
    the same frozen checker), pass-through (F's exact canonical
    bytes through the ONE frozen family-agnostic pass-through
    operation, K bypassed, graded by the same frozen checker). No
    ORDER surface is touched, no provider is invoked (a provider
    invocation anywhere on this path is a harness defect, never a
    leg), no usage artifact is written, and the captured arrival
    bytes are never an argument to F (F sees frozen task bytes
    only). The ON verdict stays the treatment verdict; OFF and
    pass-through verdicts are causal diagnostics that can never
    alter it. A leg that cannot construct its input, or yields no
    gradable output, is recorded missing (None slots) -- missing
    evidence never counts as the desired outcome and never causes
    follow-up provider action or cell invalidation.

    Returns {"executed": True, "receipt", "receipt_path",
    "receipt_sha256", "causal", "leg_verdicts"} on success, or
    {"executed": False, "reason", ...} when the legs cannot be
    constructed (never a verdict). Raises ONLY on harness/
    infrastructure failure (jail construction, evaluator drift,
    executed-bytes != locked-bytes): experimental outcomes
    (checker fix/blocked, absent output) are data, never
    exceptions.
    """
    def _omit(reason):
        return {"executed": False, "reason": reason, "receipt": None,
                "receipt_path": None, "receipt_sha256": None,
                "causal": False, "leg_verdicts": None}

    if not cap_info or not cap_engine or not os.path.exists(cap_engine):
        return _omit("a13-omitted: no locked capability engine staged")
    if on_exec.get("execution_mode") != "engine" or not isinstance(
            on_exec.get("engine_jail"), dict):
        return _omit("a13-omitted: the on-leg is not an engine execution")
    if on_exec.get("checker_sha256") is None:
        return _omit("a13-omitted: the on-leg grading is unbound")
    engine_sha = h(cap_engine)
    locked_sha = (cap_info or {}).get("engine_sha256")
    if engine_sha != locked_sha:
        raise RuntimeError(
            "A13-ENGINE-MISMATCH executed engine bytes "
            f"{str(engine_sha)[:12]} != locked capability "
            f"{str(locked_sha)[:12]}; refusing to receipt legs for "
            "bytes that are not the locked K")
    # Frozen task bytes (freeze-commit git objects only -- never the
    # mutable tree, never captured bytes).
    try:
        task_files, _task_manifest = AD.frozen_task_files(
            famc_dir, freeze_commit, family, task)
    except (OSError, RuntimeError, ValueError):
        return _omit("a13-omitted: frozen task bytes unreadable")
    # Schema resolution: exactly one registry schema must cover the
    # surface (ambiguous or uncovered surfaces cannot run legs).
    resolved = []
    for sid in AD.SCHEMA_IDS:
        try:
            AD.adapt_task(sid, dict(task_files), AD.F_VERSION_V1)
        except (ValueError, RuntimeError):
            continue
        resolved.append(sid)
    if len(resolved) != 1:
        return _omit("a13-omitted: schema coverage != exactly one "
                     f"(got {resolved})")
    schema_id = resolved[0]
    schema = AD.get_schema(schema_id)
    schema_sha = hashlib.sha256(
        AD.canonical_json(schema).encode()).hexdigest()
    contract_sha = AD.contract_sha_for(AD.F_VERSION_V1)
    if not _a13_looks_sha(task_snapshot_sha256):
        return _omit("a13-omitted: task snapshot binding malformed")
    # The canonical F pair (pass-through adapted bytes) and the
    # NOOP pair (OFF-noop adapted bytes), both over frozen bytes.
    on_pair = AD.adapt_task(schema_id, dict(task_files),
                            AD.F_VERSION_V1)
    off_pair = AD.adapt_task(schema_id, dict(task_files),
                             AD.PROGRAM_NOOP_V1)

    def _file_shas(pair):
        return {name: hashlib.sha256(data).hexdigest()
                for name, data in sorted(pair["files"].items())}

    # ON leg: the cell's own execution (consumed-byte bindings from
    # the adapted-input-only jail snapshot + the sealed graded
    # output the checker consumed).
    _snap = (on_exec.get("engine_jail") or {}).get("task_snapshot") or {}
    _fm_sha = _snap.get("file|field_map.json")
    _rc_sha = _snap.get("file|records.json")
    if not (_a13_looks_sha(_fm_sha) and _a13_looks_sha(_rc_sha)):
        return _omit("a13-omitted: on-leg jail snapshot malformed")
    on_adapted_sha = (on_exec.get("engine_jail") or {}).get(
        "adapted_input_sha256")
    if not _a13_looks_sha(on_adapted_sha):
        return _omit("a13-omitted: on-leg adapted binding malformed")
    on_output = on_exec.get("graded_output_sha256") or on_exec.get(
        "output_sha256")
    _on_text = on_exec.get("checker_output")
    on_evidence = {
        "task_snapshot_sha256": task_snapshot_sha256,
        "capability_schema_sha256": schema_sha,
        "adaptation_contract_sha256": contract_sha,
        "adapted_input_sha256": on_adapted_sha,
        "executable_sha256": engine_sha,
        "output_sha256": on_output,
        "output_present": on_output is not None,
        "checker_sha256": on_exec.get("checker_sha256"),
        "checker_returncode": on_exec.get("checker_returncode"),
        "checker_output": _on_text if isinstance(_on_text, str) else None,
        "checker_report_sha256": (
            hashlib.sha256(_on_text.encode()).hexdigest()
            if isinstance(_on_text, str) else None),
        "container_returncode": on_exec.get("container_returncode"),
        "verdict": on_exec.get("verdict"),
    }
    # OFF-noop leg: the NOOP pair through the SAME locked engine
    # (same argv ABI, same jail shape) + the same frozen checker.
    # The arrival here is synthesized from NOOP bytes only; the
    # captured arrival is never read on this path.
    try:
        off_payload = {
            name: json.loads(data.decode("utf-8"))
            for name, data in sorted(off_pair["files"].items())}
    except (UnicodeDecodeError, ValueError):
        return _omit("a13-omitted: noop pair not JSON-shaped")
    off_work = os.path.join(work, "a13-offnoop")
    off_out = os.path.join(outdir, "a13-offnoop")
    os.makedirs(off_work, exist_ok=True)
    os.makedirs(off_out, exist_ok=True)
    off_arrival = {
        "decision": "use_capability",
        "execution_payload": {
            "field_map": off_payload["field_map.json"],
            "records": off_payload["records.json"]},
    }
    off_exec = execute_arrival(
        "correct", off_arrival, off_work, off_out, taskdir, cap_engine,
        sb, jail_factory=jail_factory,
        evaluator_authority=evaluator_authority)
    off_output = off_exec.get("graded_output_sha256") or off_exec.get(
        "output_sha256")
    _off_text = off_exec.get("checker_output")
    off_evidence = {
        "task_snapshot_sha256": task_snapshot_sha256,
        "capability_schema_sha256": schema_sha,
        "adaptation_contract_sha256": contract_sha,
        "adapted_input_sha256": (off_exec.get("engine_jail") or {}).get(
            "adapted_input_sha256"),
        "target_capability_sha256": locked_sha,
        "executable_sha256": engine_sha,
        "output_sha256": off_output,
        "output_present": off_output is not None,
        "checker_sha256": off_exec.get("checker_sha256"),
        "checker_returncode": off_exec.get("checker_returncode"),
        "checker_output": _off_text if isinstance(_off_text, str) else None,
        "checker_report_sha256": (
            hashlib.sha256(_off_text.encode()).hexdigest()
            if isinstance(_off_text, str) else None),
        "container_returncode": off_exec.get("container_returncode"),
        "verdict": off_exec.get("verdict"),
    }
    # Pass-through leg: F's exact canonical bytes through the ONE
    # frozen family-agnostic operation (K bypassed), graded by the
    # exact checker bytes that graded ON. A shape refusal here is
    # deterministic missing-output evidence, never synthesis.
    pass_out = os.path.join(outdir, "a13-passthrough")
    os.makedirs(pass_out, exist_ok=True)
    try:
        pass_bytes = AD.passthrough_v1(dict(on_pair["files"]))
    except ValueError:
        pass_bytes = None
    pass_output_sha, pass_rc, pass_verdict = None, None, None
    pass_text = None
    if pass_bytes is not None:
        pass_out_path = os.path.join(pass_out, "OUTPUT.json")
        with open(pass_out_path, "wb") as _f:
            _f.write(pass_bytes)
        pass_output_sha = h(pass_out_path)
        pass_checker = on_exec.get("checker_path")
        if pass_checker is not None and os.path.exists(pass_checker):
            try:
                _chk = subprocess.run(
                    [sys.executable, pass_checker,
                     os.path.basename(taskdir), pass_out_path],
                    capture_output=True, text=True)
            except OSError as e:
                raise RuntimeError(
                    "A13-CHECKER-UNAVAILABLE the frozen checker "
                    f"vanished mid-cell: {e}")
            pass_rc = _chk.returncode
            pass_verdict = ("ship" if _chk.returncode == 0 else
                            "fix" if _chk.returncode == 1 else "blocked")
            pass_text = ((_chk.stdout or "") + (_chk.stderr or ""))[:500]
    pass_evidence = {
        "task_snapshot_sha256": task_snapshot_sha256,
        "capability_schema_sha256": schema_sha,
        "adaptation_contract_sha256": contract_sha,
        "adapted_input_sha256": on_pair["adapted_input_sha256"],
        "passthrough_implementation_sha256":
            AD.passthrough_identity(),
        "output_sha256": pass_output_sha,
        "output_present": pass_output_sha is not None,
        "checker_sha256": (h(on_exec["checker_path"])
                           if pass_output_sha is not None
                           and on_exec.get("checker_path")
                           and os.path.exists(
                               on_exec["checker_path"]) else None),
        "checker_returncode": pass_rc,
        "checker_output": pass_text,
        "checker_report_sha256": (
            hashlib.sha256(pass_text.encode()).hexdigest()
            if isinstance(pass_text, str) else None),
        "container_returncode": None,
        "verdict": pass_verdict,
    }

    def _leg(program, adapted_sha, file_shas, consumer, evidence):
        return {"program": program,
                "program_identity": AD.program_identity(program),
                "adapter_abi": AD.VERSION_WIRING[program]["abi"],
                "consumer": consumer,
                "adapted_input_sha256": adapted_sha,
                "adapted_files": dict(file_shas),
                "execution_evidence": evidence}

    det = AD.build_determinant(locked_sha, schema_sha,
                               task_snapshot_sha256, contract_sha)
    det_block = AD.prove_determinism(schema_id, task_files)
    receipt = AD.build_receipt(
        family=family, task=task,
        capability_id=cap_info.get("capability_id"),
        determinant=det["determinant"],
        determinant_sha256=det["determinant_sha256"],
        on=_leg(AD.F_VERSION_V1, on_adapted_sha,
                {"field_map.json": _fm_sha, "records.json": _rc_sha},
                "locked-engine-then-checker", on_evidence),
        off_noop=_leg(AD.PROGRAM_NOOP_V1,
                      off_pair["adapted_input_sha256"],
                      _file_shas(off_pair),
                      "locked-engine-then-checker", off_evidence),
        pass_through=_leg(AD.F_VERSION_V1,
                          on_pair["adapted_input_sha256"],
                          _file_shas(on_pair), "checker-direct",
                          pass_evidence),
        checker_sha256=on_exec.get("checker_sha256"),
        truth_sha256=on_exec.get("truth_sha256"),
        execution_harness_manifest_sha256=harness_manifest_sha(),
        determinism=det_block,
        isolation={"captured_response_sha256": captured_response_sha256,
                   "cell_id": cell_id,
                   "provider_call_delta": 0, "order_cell_delta": 0})
    receipt_path = os.path.join(outdir, "A13-CAUSAL-RECEIPT.json")
    with open(receipt_path, "w") as _f:
        _f.write(json.dumps(receipt, sort_keys=True, indent=1) + "\n")
    return {"executed": True, "reason": None, "receipt": receipt,
            "receipt_path": receipt_path,
            "receipt_sha256": receipt["receipt_sha256"],
            "causal": bool(receipt["causal_contribution_proven"]),
            "leg_verdicts": {
                "on": on_evidence["verdict"],
                "off-noop": off_evidence["verdict"],
                "pass-through": pass_evidence["verdict"]}}


def main(lane, family, task, arm, outdir, capdir=None, opts=None,
           jail_factory=None):
    opts = opts or {}
    wire = opts.get("wire", True)
    if opts.get("promote_dir"):
        # P0-3: belt-and-braces behind the CLI refusal — the runner never
        # promotes. Sole route: harness/promotion.py (A12.1 order-authorized
        # promotion controller).
        raise SystemExit(
            "PROMOTE-REFUSED: run_arm_h1.py does not promote; promotion is "
            "the sole route of the A12.1 order-authorized promotion "
            "controller harness/promotion.py")
    dev_out = opts.get("dev_unwired_outdir")
    ensure_roots()
    if not wire:
        # Audit P0 #19: no unwired execution on the estimand surface. Unwired
        # runs are a dev escape only: an explicit --dev-unwired-outdir that
        # must be OUTSIDE the Fam-C tree (runs/ is the wired surface); the
        # manifest then stamps dev_mode=true so admissibility excludes it.
        if dev_out is None:
            raise ValueError("NO-WIRE-REFUSED: unwired runs are dev-only; "
                             "pass --dev-unwired-outdir DIR outside the "
                             "Fam-C tree (manifest stamps dev_mode=true)")
        if os.path.realpath(outdir) != os.path.realpath(dev_out):
            raise ValueError("NO-WIRE-REFUSED: outdir must equal "
                             "--dev-unwired-outdir DIR")
        r_out = os.path.realpath(outdir)
        r_base = os.path.realpath(BASE)
        if r_out == r_base or r_out.startswith(r_base + os.sep):
            raise ValueError("NO-WIRE-REFUSED: unwired outdir must lie "
                             "OUTSIDE the Fam-C tree; runs/ is the wired "
                             "estimand surface")
    # Audit P0 #4 dual anchors: the chain genesis binds the INSTANCE freeze
    # commit read from FREEZE.json — never an execution HEAD masquerading as
    # the freeze. The execution harness commit + executed harness bytes are
    # recorded alongside as the second anchor.
    instance_freeze_commit, instance_freeze_tree = freeze_anchors()
    execution_harness_commit = exec_commit()
    execution_harness_manifest_sha = harness_manifest_sha()
    # Item-4 refuse-START: all three lock authorities
    # (INSTANCE-FREEZE / PROTOCOL-LOCK / EXECUTION-LOCK) must be green
    # before any model token is spent. A governed file modified without a
    # listed forward amendment fails its lock here.
    lock_findings = preflight_validate_all(BASE)
    if lock_findings:
        raise RuntimeError("PREFLIGHT-LOCK-FAIL refuse start: "
                           + " | ".join(lock_findings)[:800])
    # Item-7 refuse-START: the requested invocation must be the NEXT
    # authorized cell of the frozen ORDER.md sequence, mechanically expanded
    # into ORDER-EXPANSION.json. Wrong universe, unknown block, a duplicate
    # cell, or any earlier cell still incomplete (fam01 before fam05, QP
    # before PQ completes, wrong arm order within a family) refuses BEFORE
    # any token is spent.
    block = opts.get("block")
    if not block:
        raise ValueError(
            "ORDER-DENY: --block PQ|QP is required; a run without a block is "
            "not an authorized cell of the frozen order")
    exp_findings = order_verify_expansion(BASE)
    if exp_findings:
        raise RuntimeError("ORDER-DENY refuse start: "
                           + " | ".join(exp_findings))
    expansion = order_load_expansion(BASE)
    # A11.6: progress is VALIDATED cell state (manifest + chain + identity +
    # normalized usage + admissibility), never raw manifest presence.
    done_cells = order_completed_cells(BASE, expansion=expansion)
    # A12.0: an ACQUISITION cell (T0/T1) is authorized through the event path
    # — it has no consumer arm and no capability_id, so the downstream
    # authorize() path would refuse it (and must: a capability arm cannot run
    # before PROMOTION). The operator names the EVENT and its universe; the
    # frozen expansion decides which cell that is.
    acq_event = opts.get("acquisition_event")
    acq_universe = opts.get("acquisition_universe")
    if bool(acq_event) != bool(acq_universe):
        raise SystemExit(
            "ACQUISITION-ARGS-DENY: --acquisition-event T0|T1 and "
            "--acquisition-universe A|C are a mandated pair")
    if acq_event:
        if task != acq_event:
            raise SystemExit(
                f"ACQUISITION-DENY: --acquisition-event {acq_event} requires "
                f"task {acq_event}; got {task}")
        if arm != "acquisition":
            raise SystemExit(
                "ACQUISITION-DENY: an acquisition cell's arm is "
                "'acquisition'; a capability arm cannot run before PROMOTION")
        cell, order_findings = order_authorize_event(
            expansion, block, family, acq_event, acq_universe, done_cells)
    else:
        # A12d D1-B5: a downstream cell of a NOT-PROMOTED universe is
        # refused BEFORE any model call with the named acquisition denial
        # (before the generic order authorization: the universe's failed
        # acquisition is the operative reason, not scheduling order).
        _pre_cell = order_expected_cell(expansion, block, family, task,
                                        lane, arm)
        if _pre_cell is not None and _pre_cell.get("universe") in ("A", "C"):
            _failed, _cause = order_acquisition_failed(
                BASE, block, family, _pre_cell["universe"])
            if _failed:
                raise RuntimeError(
                    "ACQUISITION-FAILED-DENY: universe "
                    f"{block}/{family}/{_pre_cell['universe']} T1 cell is "
                    f"COMPLETE but its candidate validation failed "
                    f"({_cause}); every downstream cell "
                    f"of that universe (T2/T3/T4) is NOT-EVALUABLE — "
                    f"refuse start of {task}/{_pre_cell['universe']} "
                    f"before any model call (no retry: the failed "
                    f"validation is an experimental outcome, not an "
                    f"infrastructure-invalid run)")
        cell, order_findings = order_authorize(
            expansion, block, family, task, lane, arm, done_cells)
    if order_findings:
        raise RuntimeError("ORDER-DENY refuse start: "
                           + " | ".join(order_findings))
    # A11.5: the scheduler — not the operator — derives the namespace. For a
    # wired estimand cell the capability registry and the run directory MUST
    # be the derived per-universe paths; a free CLI path is refused.
    derived_cap, derived_out = order_derive_paths(BASE, cell)
    if wire:
        if capdir and os.path.realpath(capdir) != os.path.realpath(
                derived_cap):
            raise PermissionError(
                "FOREIGN-REGISTRY-DENY: capability dir must be the derived "
                f"universe registry {derived_cap}; got {capdir} "
                f"(cell {cell['block']}/{cell['universe']}/{cell['family']}, "
                f"capability_id {cell['capability_id']})")
        if os.path.realpath(outdir) != os.path.realpath(derived_out):
            raise PermissionError(
                "ORDER-DENY: run dir must be the derived cell path "
                f"{derived_out}; got {outdir}")
        capdir = derived_cap
        outdir = derived_out
    # Refuse-START: the executed instance subtree must be byte-identical to
    # the frozen package BEFORE any model token is spent. Item-5: the
    # manifest is resolved from the freeze commit via git (the working-tree
    # copy is never trusted), and freeze_anchors() above already proved the
    # recorded freeze_tree equals that commit's tree of the frozen root.
    # A12n slice D12 (auditor D11-post P0): the SINGLE immutable
    # authority object for this run — expected visible paths +
    # manifest derived from freeze-commit git objects (never the
    # mutable task dir). Threaded through materialization, the
    # pre-model-call gate, and the sandbox binding below; nothing
    # re-derives authority from taskdir afterwards.
    fro = verify_instance_frozen(BASE, family, task,
                                 freeze_commit=instance_freeze_commit)
    frozen = instance_freeze_commit
    # A11.6: the scheduler creates the derived namespace itself, one
    # component at a time at 0755 (os.makedirs would leave 0775
    # intermediates under umask 002, which the ancestry rule then refuses
    # on the next read). A free (dev) outdir keeps plain makedirs.
    if wire:
        order_ensure_namespace(BASE, cell["block"], cell["universe"],
                               cell["family"],
                               tail=("runs", cell["cell_id"]))
    else:
        os.makedirs(outdir, exist_ok=True)
    taskdir = os.path.join(BASE, "families", family, task)
    # ---- A12b.2: the T1 candidate-validation surface --------------------
    # T1 sees the EXACT frozen candidate: loaded here from the validated
    # T0 arrival in THIS universe (never supplied, never re-derived from
    # prose). A T1 without a frozen T0 candidate cannot be prompted, let
    # alone promoted.
    candidate = None
    if acq_event == "T1":
        t0cell = order_expected_event(expansion, block, family, "T0",
                                      acq_universe)
        if t0cell is None:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: order has no T0 cell for "
                f"{block}/{family}/{acq_universe}; a T1 without a frozen "
                f"T0 candidate cannot run")
        t0arr_p = os.path.join(order_run_dir(BASE, t0cell), "arrival.json")
        try:
            t0arr_bytes = open(t0arr_p, "rb").read()
        except OSError as e:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 arrival unreadable at "
                f"{t0arr_p}: {e}")
        # A12n slice D13 P0-3: the T0 arrival is authority for the
        # frozen candidate ONLY if its current bytes equal the
        # arrival_sha256 the T0 chain's model-call link committed at
        # capture. A post-hoc arrival rewrite (solver swap) denies
        # here with a candidate-provenance deny — before any prompt
        # is built and before any T1 model token is spent. A T0
        # chain with no run-time arrival binding cannot source a
        # candidate either (legacy/unverifiable -> deny, never
        # consume).
        t0chain_p = os.path.join(order_run_dir(BASE, t0cell), CHAIN_FILE)
        try:
            _t0_links = [json.loads(_l) for _l in open(t0chain_p)
                         if _l.strip()]
        except (OSError, ValueError) as e:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 evidence chain "
                f"unreadable at {t0chain_p}: {e}; candidate provenance "
                "unestablishable")
        _t0_mc = [l for l in _t0_links if l.get("kind") == "model-call"]
        _t0_bound = (_t0_mc[0].get("payload") or {}).get("arrival_sha256") \
            if _t0_mc else None
        if not isinstance(_t0_bound, str):
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 chain commits no "
                "run-time arrival_sha256; candidate provenance "
                "unestablishable (refusing to source the frozen "
                "candidate from unverifiable bytes)")
        if hashlib.sha256(t0arr_bytes).hexdigest() != _t0_bound:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 arrival.json bytes "
                f"{hashlib.sha256(t0arr_bytes).hexdigest()[:12]} != "
                f"chain-committed arrival_sha256 {_t0_bound[:12]} "
                "(post-hoc arrival edit -> deny; the frozen candidate "
                "cannot be sourced from substituted bytes)")
        try:
            t0arr = json.loads(t0arr_bytes.decode())
            t0src = (t0arr.get("execution_payload") or {}).get("solver_py")
        except (ValueError, OSError) as e:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 arrival unreadable at "
                f"{t0arr_p}: {e}")
        if not (isinstance(t0src, str) and t0src.strip()):
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 arrival carries no "
                "execution_payload.solver_py candidate")
        _t0_bound_solver = (_t0_mc[0].get("payload") or {}).get(
            "solver_py_sha256")
        if not isinstance(_t0_bound_solver, str) or \
                hashlib.sha256(t0src.encode()).hexdigest() \
                != _t0_bound_solver:
            raise SystemExit(
                "ACQUISITION-CANDIDATE-DENY: T0 arrival solver_py bytes "
                "!= chain-committed solver_py_sha256 (post-hoc solver "
                "swap -> deny; the frozen candidate cannot be sourced "
                "from substituted bytes)")
        candidate = {"sha256": hashlib.sha256(t0src.encode()).hexdigest(),
                     "source": t0src}
    # ---- Item-6 ONE SOURCE SNAPSHOT (audit round 2 item 6) -------------
    run_id = hashlib.sha256(
        f"{lane}|{family}|{task}|{arm}|{time.time()}".encode()).hexdigest()[:12]
    prep = prepare_arm(lane, family, task, arm, capdir, wire, run_id,
                       cell=cell, candidate=candidate)
    prompt = prep["prompt"]
    envelope = prep["envelope"]
    work, visible = prep["work"], prep["visible"]
    copied, refused = prep["copied"], prep["refused"]
    staged_tree = prep["staged_tree"]
    context_task_snapshot_hash = prep["context_task_snapshot_hash"]
    sym = prep["symmetry"]
    cap_info, cap_engine = prep["cap_info"], prep["cap_engine"]
    # A12n slice D12 (auditor D11-post P0): the pre-model-call gate.
    # The materializer must reproduce the frozen authority EXACTLY:
    # its `copied` list must equal the independently determined
    # expected path set (missing OR extra path refuses — `copied`
    # never defines the expectation), and the materialized visible
    # bytes must equal the frozen manifest. Anything else means the
    # task bytes changed after verification (or an unfaithful
    # materializer) — refuse BEFORE any model token is spent and
    # before anything H-derived is persisted.
    if sorted(copied) != sorted(fro["expected_visible_paths"]):
        raise PermissionError(
            "FROZEN-VISIBLE-DENY materializer copied list != frozen "
            "expected path set "
            f"(copied={sorted(copied)} expected={sorted(fro['expected_visible_paths'])}); "
            "refused before model call")
    if frozen_manifest_of_dir(visible) != fro["expected_visible_manifest"]:
        raise PermissionError(
            "FROZEN-VISIBLE-DENY materialized visible bytes != frozen "
            "expected manifest; refused before model call")
    # A12n slice D12e: pre-call frozen binding of the exact prompt
    # snapshot. prepare_arm() hashes the STAGED mutable visible tree
    # and builds the prompt from it — a pre-call ABA (staged H bytes,
    # visible restored to E) would pass the live-dir gate above while
    # the model still sees H, with refusal landing only after the
    # model call. The staged snapshot and the context hash it
    # determines must therefore equal the frozen authority
    # THEMSELVES (the prompt is mechanically tied to staged_tree by
    # the CONTEXT-SNAPSHOT-DENY check inside prepare_arm) — before
    # prompt.txt is written and before any model token is spent.
    if staged_tree != fro["expected_visible_manifest"]:
        raise PermissionError(
            "FROZEN-VISIBLE-DENY staged snapshot != frozen expected "
            "manifest; refused before model call")
    if context_task_snapshot_hash != fro["expected_task_snapshot_sha256"]:
        raise PermissionError(
            "FROZEN-VISIBLE-DENY context snapshot hash != frozen "
            "expected task snapshot sha; refused before model call")
    # The SAME authority object threads into the sandbox binding
    # below (never a second read of taskdir after the model call).
    frozen_expected = fro["expected_visible_manifest"]
    # A12n slice D12b: the pre-model evaluator bind. The live grading
    # bytes (the family checker + truth the host-side subprocess is
    # about to be asked to execute) must equal the freeze-derived
    # evaluator authority carried in `fro` — a checker rewritten
    # after verify_instance_frozen returned refuses HERE with
    # EVALUATOR-DRIFT-DENY, before prompt.txt is written and before
    # any model token is spent (MODEL_CALL_COUNT == 0, nothing
    # H-derived persisted — the D12 refusal property).
    _ev_checker_live = os.path.join(taskdir, "..", "check.py")
    _ev_truth_live = os.path.join(taskdir, "..", "truth.json")
    _ev_live_c = h(_ev_checker_live) if os.path.exists(
        _ev_checker_live) else None
    _ev_live_t = h(_ev_truth_live) if os.path.exists(
        _ev_truth_live) else None
    if _ev_live_c != fro["expected_checker_sha256"] or \
            _ev_live_t != fro["expected_truth_sha256"]:
        raise PermissionError(
            "EVALUATOR-DRIFT-DENY live evaluator bytes != "
            "freeze-derived authority "
            f"(checker {str(_ev_live_c)[:12]} != "
            f"{str(fro['expected_checker_sha256'])[:12]} or truth "
            f"{str(_ev_live_t)[:12]} != "
            f"{str(fro['expected_truth_sha256'])[:12]}); refused "
            "before model call")
    evaluator_authority = {"family": family,
                           "freeze_commit": instance_freeze_commit,
                           "expected_checker_sha256":
                               fro["expected_checker_sha256"],
                           "expected_truth_sha256":
                               fro["expected_truth_sha256"]}
    open(os.path.join(outdir, "prompt.txt"), "w").write(prompt)
    raw, receipt, nu_path, id_path, identity_family = call(
        lane, prompt, outdir, f"H1-{lane}-{family}-{task}-{arm}")
    arrival, parse_mode = extract(raw)
    arrival_path = os.path.join(outdir, "arrival.json")
    open(arrival_path, "w").write(json.dumps(arrival, indent=1))
    # A12n slice D13 P0-3: arrival provenance, captured at run time.
    # response_text_sha256 binds the provider response TEXT itself
    # (the usage receipt binds request/usage but never the returned
    # text, and the receipt schema is frozen by the usage verifiers
    # — so the binding rides the manifest + chain instead);
    # arrival_sha256 binds the arrival.json FILE bytes as written
    # (later T1 and promotion reads re-hash the file and require
    # equality with the chain-committed value);
    # execution_payload_sha256 binds the canonical executed payload
    # and solver_py_sha256 binds the executed solver source (None
    # when the payload carries no solver string).
    arrival_file_sha256 = h(arrival_path)
    response_text_sha256 = hashlib.sha256(raw.encode()).hexdigest()
    _payload_obj = arrival.get("execution_payload") or {}
    execution_payload_sha256 = hashlib.sha256(
        json.dumps(_payload_obj, sort_keys=True).encode()).hexdigest()
    _solver_src = _payload_obj.get("solver_py")
    solver_py_sha256 = hashlib.sha256(_solver_src.encode()).hexdigest() \
        if isinstance(_solver_src, str) else None
    # A12.0: no capability exists before PROMOTION, so the ONLY legal decision
    # on an acquisition cell is fresh. This is belt-and-braces behind
    # execute_arrival's arm gate (arm='acquisition' is not the capability
    # arm), named for the acquisition surface specifically.
    if acq_event and arrival.get("decision") != "fresh":
        raise SystemExit(
            "ACQUISITION-DECISION-DENY: no capability exists before "
            f"PROMOTION; the only legal decision at {acq_event} is fresh, "
            f"got {arrival.get('decision')!r}")
    # A12n slice D12: the post-call taskdir re-read is DELETED —
    # frozen_expected above is the pre-model-call frozen authority
    # object (never a second read of mutable taskdir bytes).
    # DockerSandbox stages its own private copy of `visible` and refuses on
    # drift; the constructor itself enforces the frozen expected snapshot
    # passed below (SNAPSHOT-DENY on any mismatch, even one its own
    # reads agreed on), and its task_snapshot must additionally equal
    # the hash the context was built from, else refuse.
    sb = DockerSandbox(work, visible,
                       expected_task_snapshot=frozen_expected)
    if sb.task_snapshot != staged_tree:
        raise RuntimeError("CONTEXT-SNAPSHOT-DENY sandbox task_snapshot != "
                           "context_task_snapshot_hash source")
    # Execute the arrival through the ONE runtime path (A11b.2): the
    # arrival's own decision picks engine vs solver; the arm only gates
    # decision legality. No evaluator/truth/checker is mounted.
    execr = execute_arrival(arm, arrival, work, outdir, taskdir,
                            cap_engine, sb, jail_factory=jail_factory,
                            evaluator_authority=evaluator_authority)
    verdict = execr["verdict"]
    output_sha = execr["output_sha256"]

    # ---- A13 executed counterfactual legs (auditor ruling) ----
    # Three deterministic sub-executions INSIDE this same real
    # treatment cell, downstream of the one captured arrival: the
    # ON leg IS the execution above (evidence harvested, never
    # re-run -- so the treatment verdict stays the ON verdict by
    # construction); OFF-noop and pass-through run after it as
    # causal diagnostics. Gated to wired use_capability engine
    # executions (the only path with a locked K to ablate); every
    # other path records no receipt and keeps the legacy
    # consumed-but-unproven ledger. No ORDER surface, no provider,
    # no usage artifact on this path (see execute_a13_legs).
    a13 = {"executed": False, "reason": None, "receipt": None,
           "receipt_path": None, "receipt_sha256": None,
           "causal": False, "leg_verdicts": None}
    if wire and execr.get("decision") == "use_capability" \
            and execr.get("execution_mode") == "engine" \
            and cap_info is not None:
        a13 = execute_a13_legs(
            family=family, task=task, cap_info=cap_info,
            cap_engine=cap_engine, on_exec=execr, freeze_commit=frozen,
            famc_dir=BASE, taskdir=taskdir, work=work, outdir=outdir,
            task_snapshot_sha256=fro["expected_task_snapshot_sha256"],
            evaluator_authority=evaluator_authority,
            captured_response_sha256=response_text_sha256,
            cell_id=cell["cell_id"],
            jail_factory=jail_factory, sb=sb)
        if a13["executed"]:
            print(f"A13-LEGS on={a13['leg_verdicts']['on']} "
                  f"off-noop={a13['leg_verdicts']['off-noop']} "
                  f"pass-through={a13['leg_verdicts']['pass-through']} "
                  f"causal={a13['causal']}")
        else:
            print(f"A13-OMITTED {a13['reason']} "
                  f"(treatment verdict {verdict} stands; no leg "
                  f"evidence claimed)")

    # ---- A12d D1: candidate validation path (two jails + evidence) ----
    # Required flow: T1 model -> candidate adapter description -> run the
    # adapter in the RAW-TASK jail -> stage the adapter's output as the
    # candidate jail's /task -> materialize the candidate-input manifest ->
    # EXACT T0 candidate bytes -> run the candidate in the SECOND
    # (candidate-only) jail -> HOST-SIDE T1 CHECKER -> validated verdict.
    # The helper RETURNS the validation result on experimental failure
    # (validated=false + named validation_failure cause) and raises ONLY
    # on harness/infrastructure failure. The runner still commits the T1
    # cell COMPLETE with the failed validation as committed evidence
    # (B2): the T1 SHIP verdict (computed above) is the cell's task
    # verdict either way; the validation event decides promotion, not
    # completion.
    candidate_validation = None
    validation_failed = False
    if acq_event == "T1":
        candidate_validation = validate_t1_candidate(
            adapter_py=(arrival.get("execution_payload") or {}).get(
                "adapter_py"),
            candidate_source=candidate["source"],
            candidate_sha256=candidate["sha256"],
            work=work, taskdir=taskdir, sb=sb,
            checker_sha256=execr["checker_sha256"],
            truth_sha256=execr["truth_sha256"],
            outdir=outdir)
        if candidate_validation.get("validated") is not True:
            validation_failed = True
            print(f"CANDIDATE-VALIDATION-FAIL: "
                  f"{candidate_validation.get('validation_failure')} "
                  f"(T1 {family}/{task} task_verdict={verdict}; the failed "
                  f"validation is committed experimental evidence, not an "
                  f"infrastructure-invalid run)")

    # ---- H2/H3 wiring (skipped only under the unwired dev escape) ----
    # Reuse ledger: P0-2 — every lifecycle field is DERIVED from the actual
    # decision/execution path of THIS run, never asserted from arm or
    # capability presence. The record is written in every wired case:
    #   use_capability   selected/loaded/invoked/consumed observed on path
    #   fresh + K avail  capability_available, reuse_rejected, reason from
    #                    the arrival's own recorded notes
    #   fresh + no K     capability_available=False (e.g. disabled arm)
    reuse_path = None
    if wire:
        _decision = execr["decision"]
        _cap_available = cap_info is not None
        _selected = _cap_available and _decision == "use_capability"
        # loaded: the locked engine was verified and staged into the jail
        # (execute_arrival raises CONTRACT-ENGINE-DENY otherwise); invoked:
        # the engine process actually executed; output_consumed: the engine's
        # OUTPUT.json existed and the host-side checker consumed it.
        _invoked = _selected and execr["execution_mode"] == "engine"
        _consumed = bool(_invoked and execr["output_sha256"] is not None
                         and execr["checker_returncode"] is not None)
        _rejected = _cap_available and not _selected
        _policy = ("PREREG-frozen: single locked capability per "
                   "(family, producer lane); consumer loads by locked hash")
        if _cap_available:
            reuse_path = reuse_write_record(
                outdir, f"{family}-{task}", lane, arm,
                reuse_policy=_policy,
                capability_available=True,
                capability_candidate_ids=[cap_info["capability_id"]],
                capability_selected=_selected,
                selected_capability_id=(cap_info["capability_id"]
                                        if _selected else None),
                selected_capability_hash=(cap_info["engine_sha256"]
                                          if _selected else None),
                capability_loaded=_selected,
                capability_invoked=_invoked,
                capability_output_consumed=_consumed,
                # A13: materially_contributed is the DERIVED causal
                # outcome of the executed counterfactual legs (ON
                # ship + OFF-noop fix/blocked + pass-through
                # fix/blocked + all bindings, receipt-bound); without
                # executed legs it stays False (consumed, not proven
                # contributed) exactly as before.
                capability_materially_contributed=bool(
                    _selected and a13["executed"] and a13["causal"]),
                contribution_evidence=(
                    None if _rejected else
                    ({"mechanism": "a13-counterfactual-legs",
                      "receipt_file": os.path.basename(
                          a13["receipt_path"]),
                      "receipt_sha256": a13["receipt_sha256"],
                      "treatment_verdict_source": "on",
                      "on_verdict": a13["leg_verdicts"]["on"],
                      "off_noop_verdict":
                          a13["leg_verdicts"]["off-noop"],
                      "pass_through_verdict":
                          a13["leg_verdicts"]["pass-through"],
                      "causal_contribution_proven": a13["causal"]}
                     if (_selected and a13["executed"]) else
                     ({"mechanism": "none",
                       "reason": ("consumed but not proven contributed: "
                                  + (a13["reason"]
                                     if a13["reason"] else
                                     "no ablation or downstream-node "
                                     "hash-linkage in this cell"))}
                      if _selected else
                      {"mechanism": "none",
                       "reason": "consumed but not proven contributed: "
                                 "no ablation or downstream-node "
                                 "hash-linkage in this cell"}))),
                reuse_rejected=_rejected,
                reuse_rejection_reason=(arrival["notes"] if _rejected
                                        else None))
        else:
            # fresh with no capability available (disabled arm, or correct
            # arm whose registry namespace does not resolve): the ledger
            # records the absence — it never fabricates a reuse event.
            reuse_path = reuse_write_record(
                outdir, f"{family}-{task}", lane, arm,
                reuse_policy=_policy,
                capability_available=False,
                capability_candidate_ids=[],
                capability_selected=False,
                selected_capability_id=None,
                selected_capability_hash=None,
                capability_loaded=False,
                capability_invoked=False,
                capability_output_consumed=False,
                capability_materially_contributed=False,
                contribution_evidence=None,
                reuse_rejected=False,
                reuse_rejection_reason=None)

    manifest = {"lane": lane, "family": family, "task": task, "arm": arm,
                "parse_mode": parse_mode, "lane_receipt": receipt,
                "sandbox": sb.manifest(), "task_snapshot": sb.task_snapshot,
                "container_returncode": execr["container_returncode"],
                "checker_returncode": execr["checker_returncode"],
                "checker_output": execr["checker_output"],
                "verdict": verdict, "output_sha256": output_sha,
                # A13 executed counterfactual legs: the receipt file +
                # its self sha ride the manifest so chain genesis binds
                # them (the receipt itself is hashed into the evidence
                # chain without a new link kind). treatment verdict is
                # the ON leg only (manifest verdict == ON verdict by
                # construction: the ON leg IS the execution above).
                # All five are None when the legs did not run.
                "a13_receipt_file": (
                    os.path.basename(a13["receipt_path"])
                    if a13["executed"] else None),
                "a13_receipt_sha256": a13["receipt_sha256"],
                "a13_causal_contribution_proven": (
                    a13["causal"] if a13["executed"] else None),
                "a13_leg_verdicts": a13["leg_verdicts"],
                "a13_omitted_reason": a13["reason"],
                # A12n slice D13 P0-2: the persisted graded-output link.
                # graded_output_sha256 is the sha256 of the EXACT sealed
                # bytes the checker consumed (frozen-evaluator/OUTPUT.json
                # on the authority path); a post-hoc reader re-hashes the
                # persisted sealed artifact and requires equality.
                # output_sha256 stays the container-produced bytes.
                "graded_output_sha256": execr.get("graded_output_sha256"),
                "graded_output_path": execr.get("graded_output_path"),
                # A12n slice D12b: evaluator provenance, bound before
                # evidence genesis so the chain covers it. checker_sha256
                # / truth_sha256 are the EXECUTED bytes' shas (the
                # frozen-materialized copy on the authority path);
                # expected_* are the freeze-derived authority; a reader
                # re-derives from evaluator_freeze_commit (==
                # instance_freeze_commit) via
                # frozen_visible.verify_expected_provenance and requires
                # executed == expected == frozen.
                "checker_sha256": execr["checker_sha256"],
                "truth_sha256": execr["truth_sha256"],
                "expected_checker_sha256": execr.get(
                    "expected_checker_sha256"),
                "expected_truth_sha256": execr.get(
                    "expected_truth_sha256"),
                "evaluator_freeze_commit": instance_freeze_commit,
                "evaluator_source": execr.get("evaluator_source"),
                "executed_checker_path": execr.get("checker_path"),
                "wired": bool(wire),
                "frozen_commit": frozen,
                # Item-7 order binding: this manifest is the completion
                # record for exactly one authorized cell.
                "block": block,
                "cell_id": cell["cell_id"],
                "cell_index": cell["index"],
                "cell_letter": cell["letter"],
                "cell_universe": cell["universe"],
                "cell_event": cell["event"],
                "cell_kind": cell["kind"],
                "capability_id": cell["capability_id"],
                "cell_lane_key": cell["lane_key"],
                # A12.0 acquisition surface: an acquisition cell has no
                # capability block in its prompt (none exists yet) and no
                # capability binding; the fields are stamped so the evidence
                # itself states the surface, not the operator's intent.
                "acquisition_event": acq_event,
                "acquisition_universe": acq_universe,
                # Derived by the production stripper, never by a substring
                # guess: a capability-access block is present iff removing it
                # changes the bytes. An acquisition cell must record False
                # (no capability exists before PROMOTION); non-acquisition
                # cells record None for the acquisition-specific field. The
                # capability-only stripper is used (not the full
                # leak-stripper): a T1 acquisition prompt legitimately
                # carries the candidate-validation block, which is not
                # capability content.
                "prompt_has_capability_block": bool(
                    _strip_capability_only(prompt) != prompt),
                "acquisition_prompt_has_capability_block": (
                    bool(_strip_capability_only(prompt) != prompt)
                    if acq_event else None),
                "order_sha256": expansion["order_sha256"],
                "instance_freeze_commit": instance_freeze_commit,
                # A12n slice D12 (auditor D11-post P0): expected
                # provenance, bound BEFORE evidence genesis so the
                # chain covers it. The canonical expected manifest
                # itself rides along (small: path->sha map), plus
                # its sha, the task-snapshot sha, and the path-set
                # sha. Post-hoc readers re-derive from
                # instance_freeze_commit (see
                # frozen_visible.verify_expected_provenance).
                "expected_visible_manifest": fro["expected_visible_manifest"],
                "expected_visible_manifest_sha256": fro[
                    "expected_visible_manifest_sha256"],
                "expected_task_snapshot_sha256": fro[
                    "expected_task_snapshot_sha256"],
                "expected_visible_paths": fro["expected_visible_paths"],
                "expected_visible_paths_sha256": fro[
                    "expected_visible_paths_sha256"],
                "instance_freeze_tree": instance_freeze_tree,
                "execution_harness_commit": execution_harness_commit,
                "execution_harness_manifest_sha256": execution_harness_manifest_sha,
                "dev_mode": bool(not wire),
                "usage_receipts": [os.path.basename(receipt)] if wire else [],
                # Item-6 single-snapshot + symmetry evidence (audit round 2).
                "context_task_snapshot_hash": context_task_snapshot_hash,
                "context_task_snapshot_source": "sealed staged visible root",
                "envelope_sha256": hashlib.sha256(
                    envelope.encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "arm_symmetry_findings": sym,
                "visible_root_copied": sorted(copied),
                "visible_root_refused": sorted(refused),
                "usage_normalized": [os.path.basename(nu_path)] if wire else [],
                "identity_file": (os.path.basename(id_path) if wire
                                  else None),
                "identity_prereg_family": (identity_family if wire
                                           else None),
                # A12n slice D13 P0-3: arrival provenance, captured at
                # run time and bound into evidence genesis (chain
                # model-call link mirrors these). Later T1 and
                # promotion reads require the live arrival.json bytes
                # to hash to arrival_sha256.
                "response_text_sha256": response_text_sha256,
                "arrival_sha256": arrival_file_sha256,
                "arrival_file": os.path.basename(arrival_path),
                "execution_payload_sha256": execution_payload_sha256,
                "solver_py_sha256": solver_py_sha256,
                "chain": CHAIN_FILE if wire else None,
                "reuse_record": os.path.basename(reuse_path) if reuse_path else None,
                "capability": {k: cap_info[k] for k in
                               ("capability_id", "capability_version",
                                "lock_sha256", "engine_sha256")
                               if cap_info and k in cap_info} or None,
                "capability_lock": None,
                # A12n slice D13 P0-1: the run-private snapshot of the
                # lock-verified capability bytes that the prompt and
                # the jail execution actually consumed (dir + per-file
                # shas, each equal to the lock's artifact hash). None
                # on paths without a snapshot (unwired dev escape,
                # non-capability arms).
                "capability_snapshot": (dict(cap_info["snapshot"])
                                        if cap_info and cap_info.get(
                                            "snapshot") else None),
                # A12d D1-A4: on the use_capability path the engine ran in
                # an adapted-input-only jail — record its byte binding
                # (task snapshot, mounts, adapted input sha) in the run
                # manifest. None on the fresh/solver path (raw-task jail,
                # bound by task_snapshot above).
                "engine_jail": execr.get("engine_jail"),
                # A12d D1-B2: on a T1 acquisition cell the manifest keeps
                # the T1 fresh-solver verdict as `task_verdict`
                # (ship/fix/blocked) even when candidate validation fails:
                # the cell verdict is evidence for the fresh solve, and
                # the validation event (wired below) decides promotion.
                "task_verdict": (verdict if acq_event == "T1" else None)}

    # P0-3: the runner NEVER writes a promotion lock into an operator dir.
    # Promotion is the sole province of the A12.1 order-authorized promotion
    # controller (harness/promotion.py); --promote is refused hard at the CLI
    # before main() runs, and main() also guards a poisoned opts dict.

    # Manifest is final NOW: write it once, then genesis binds this object.
    json.dump(manifest, open(os.path.join(outdir, "H1-RUN-MANIFEST.json"), "w"), indent=1)

    if wire:
        # P0-1: consume the path + sha256 values execute_arrival bound for
        # THIS run; evidence is never recomputed over a different path here.
        checker_sha = execr["checker_sha256"]
        truth_sha = execr["truth_sha256"]
        _wire_chain(outdir, frozen, manifest, receipt, nu_path, id_path,
                    identity_family, cap_info, reuse_path, checker_sha,
                    truth_sha, verdict, output_sha, None,
                    candidate_validation)
        # H1-RUN-MANIFEST.json must NOT be rewritten after _wire_chain:
        # genesis binds its hash and any rewrite would break the chain.
    print(f"{lane}/{family}/{task}/{arm}: {verdict} ({parse_mode}, "
          f"decision {execr['decision']}, container rc "
          f"{execr['container_returncode']})")
    # A12d D1-B2: a committed failed candidate validation is experimental
    # evidence, not an infrastructure failure — the T1 cell COMPLETED, so
    # the run exits zero (promotion later records NOT-PROMOTED from the
    # wired validated=false event; it never mints a lock).
    if validation_failed:
        return 0
    return 0 if verdict in ("ship", "fix") else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    opts = {}
    if "--block" in argv:
        i = argv.index("--block")
        opts["block"] = argv[i + 1].upper()
        del argv[i:i + 2]
    if "--promote" in argv:
        # P0-3: hard refuse — this runner is the execution path, not the
        # promotion controller. A capability lock may only be minted by the
        # A12.1 order-authorized promotion controller (harness/promotion.py);
        # the runner never writes into an operator capability store.
        raise SystemExit(
            "PROMOTE-REFUSED: run_arm_h1.py does not promote. Promotion is "
            "the sole route of the A12.1 order-authorized promotion "
            "controller harness/promotion.py (ORDER-PROMOTE); a lock minted "
            "by the runner is not an authorized order outcome. Run the "
            "controller there instead.")
    if "--selfcheck" in argv:
        # Full offline battery: wiring selfcheck then the prompt selfcheck.
        # Exit non-zero on either failure (fails closed).
        rc = selfcheck_wire()
        if rc != 0:
            sys.exit(rc)
        sys.exit(selfcheck_prompt())
    if "--selfcheck-wire" in argv:
        sys.exit(selfcheck_wire())
    if "--selfcheck-prompt" in argv:
        sys.exit(selfcheck_prompt())
    if "--no-wire" in argv:
        # Audit P0 #19: --no-wire is banned on the estimand surface. Dev
        # unwired runs must opt into the escape flag below instead.
        raise SystemExit("NO-WIRE-REFUSED: use --dev-unwired-outdir DIR "
                         "(outside the Fam-C tree) for unwired dev runs; "
                         "runs/ is the wired estimand surface")
    if "--dev-unwired-outdir" in argv:
        i = argv.index("--dev-unwired-outdir")
        opts["wire"] = False
        opts["dev_unwired_outdir"] = argv[i + 1]
        del argv[i:i + 2]
    # A12.0: the production ACQUISITION executor. Before this, no production
    # code path could produce cell 0 (T0) — the experiment was mechanically
    # deadlocked at the first cell. The event and its universe are a mandated
    # pair: a half-specified acquisition is not an authorized cell, and the
    # operator never names a cell id, a chain tip or a run directory.
    if ("--acquisition-event" in argv) != ("--acquisition-universe" in argv):
        raise SystemExit(
            "ACQUISITION-ARGS-DENY: --acquisition-event T0|T1 and "
            "--acquisition-universe A|C are a mandated pair; a "
            "half-specified acquisition is not an authorized cell")
    if "--acquisition-event" in argv:
        i = argv.index("--acquisition-event")
        opts["acquisition_event"] = argv[i + 1].upper()
        del argv[i:i + 2]
        i = argv.index("--acquisition-universe")
        opts["acquisition_universe"] = argv[i + 1].upper()
        del argv[i:i + 2]
    main(argv[0], argv[1], argv[2], argv[3], argv[4],
         argv[5] if len(argv) > 5 else None, opts)

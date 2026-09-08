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
  lock.load_artifact() (exact locked hash, verified pre-execution). A run
  that ships a capability may promote it once via lock.promote() — granted
  only on a ship verdict and only when --promote <capstore> is passed; the
  lock-exists check refuses repromotion (fail closed).
- H2 reuse ledger: a correct-arm run that reuses a previously locked
  capability writes a reuse_log record with the PREREG §12 field split.
  materially_contributed is never asserted: absent a hash-linkage or derived
  ablation evidence in this cell it is recorded False (consumed, not proven
  contributed) — never model self-report.

Usage: run_arm_h1.py [--promote <capstore_dir>] \\
    <lane P|Q> <family> <task> <correct|disabled> <outdir> [capdir]
      --block PQ|QP  REQUIRED: the reciprocal block this invocation belongs
                     to (item 7). The runner refuses to start unless the
                     requested cell is the next authorized cell of the
                     frozen ORDER.md sequence (ORDER-EXPANSION.json).
      --promote DIR  on a ship verdict, write CAPABILITY_LOCK.json into DIR
                     for the capability consumed by this run (writes once).
      --dev-unwired-outdir DIR  dev escape: UNWIRED run writing to DIR, which
                     must lie OUTSIDE the Fam-C tree; the manifest stamps
                     dev_mode=true. Unwired runs under benchmarks/fam-c/runs
                     are REFUSED (runs/ is the wired estimand surface).
      --selfcheck-wire  offline fixture compose-test of the wiring (no model
                     call, no docker, no run) — CI use only.
      --selfcheck-prompt  offline proof of the item-6 prompt path on real
                     fam05/T0: one staged snapshot -> canonical envelope ->
                     both arms + symmetry/snapshot refusal gates (no model
                     call, no docker, no run) — CI use only.
Before ANY model call the runner verifies the executed instance subtree is
byte-identical to FREEZE-HASHES.sha256 and that FREEZE.json's freeze_commit
is a resolvable git object (refuse-START on drift; audit P0 #4), and that
all three authority locks (instance/protocol/execution) are green (item 4).
The model context and the docker /task mount are built from ONE staged
visible snapshot, and the arm pair must pass the mechanical symmetry check
(item 6) before any token is spent.
No P/Q calls are made by smoke; use the script only after H1 smoke is green.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

BASE = "/home/chow/chow-work/rcos/benchmarks/fam-c"
HARNESS = "/home/chow/chow-work/rcos/harness"
ROOT = os.path.abspath(os.path.join(BASE, os.pardir, os.pardir))
sys.path.insert(0, HARNESS)
from dockersandbox import DockerSandbox, ensure_roots, _hash_tree
from seal import build_visible_root
from usage import (recorded_call, write_normalized_usage,
                   verify_normalized_usage)
from identity import (record_identity, check_against_prereg,
                      verify_identity_binding)
from chain import Chain
from lock import promote as lock_promote, load_artifact
from reuse_log import write_record as reuse_write_record
from admissibility import verify_instance_frozen, verify_freeze_tree
# Item-7: the frozen ORDER.md expansion + pre-call cell authorization.
from order import (verify_expansion as order_verify_expansion,
                   load_expansion as order_load_expansion,
                   completed_cells as order_completed_cells,
                   authorize as order_authorize)
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

# Item-6 canonical envelope (audit round 2 item 6): ONE envelope format
# serves both arms; treatment/control differ ONLY by the mechanically
# delimited capability-access block plus the frozen arm preamble/output
# lines below. DISABLED bytes are unchanged from the pre-item-6 template;
# CORRECT gains exactly the two delimiter lines (envelope v2, documented).
_CAP_BEGIN = "<<<CAPABILITY-ACCESS-BEGIN>>>"
_CAP_END = "<<<CAPABILITY-ACCESS-END>>>"
_PRE_CORRECT = ("You are solving the task below using a PROVIDED capability "
                "interface. You have never seen its acquisition, no "
                "transcripts, no prior tasks. Output ONLY one JSON object, "
                "no other text.\n\n")
_PRE_DISABLED = ("You are solving the task below from scratch. No "
                 "registry/capability/prior solution exists. Output ONLY one "
                 "JSON object, no other text.\n\n")
_ENVELOPE_FMT = ("TASK DEFINITION:\n__TASKDEF__\n\n"
                 "TASK DIRECTORY LISTING: __LISTING__\n"
                 "TASK FILE CONTENTS (exact bytes):\n__BLOBS__\n")
_CAP_FMT = ("\n" + _CAP_BEGIN + "\nCAPABILITY MANIFEST:\n__MANIFEST__\n"
            "ADAPTER NOTES:\n__NOTES__\nENGINE SOURCE (frozen, do not "
            "modify):\n__ENGINE__\n" + _CAP_END + "\n")
_OUT_CORRECT = ('\nOutput object: {"records": <engine records>, '
                '"field_map": <engine map>, "notes": "one line"}. '
                "No explanations/fences.")
_OUT_DISABLED = ('\nOutput object: {"solver_py": <complete Python script '
                 "taking (src_dir, dst_path) and writing the ordinary task "
                 'output>, "notes": "one line"}. No explanations/fences.')
CORRECT = _PRE_CORRECT + _ENVELOPE_FMT + _CAP_FMT + _OUT_CORRECT
DISABLED = _PRE_DISABLED + _ENVELOPE_FMT + _OUT_DISABLED
# Counterfactual capability content (disabled-arm runs): builds the
# never-sent correct-arm twin for the pair symmetry check. Fixed sentinel,
# never model input, never executed.
COUNTERFACTUAL_CAP = ("COUNTERFACTUAL-ONLY never sent to any model: "
                      "placeholder capability content so the disabled arm "
                      "can prove pair symmetry without touching K.")


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
        return _PRE_CORRECT + envelope + cap + _OUT_CORRECT
    if arm == "disabled":
        return _PRE_DISABLED + envelope + _OUT_DISABLED
    raise ValueError("unknown arm")


def check_arm_symmetry(correct_prompt, disabled_prompt, envelope):
    """H-CTX-002 mechanical pair check (fail-closed findings list).

    Proves treatment/control differ ONLY by the mechanically identified
    capability-access block (+ frozen arm preamble/output lines):
      - the delimited capability block occurs exactly once in correct,
        never in disabled;
      - the canonical envelope occurs verbatim exactly once in EACH
        prompt (any one-byte hint asymmetry inside the shared region
        breaks verbatim embedding in at least one arm);
      - outside the envelope, each arm shows exactly its frozen preamble
        and (for correct) the delimited block + frozen output schema.
    """
    out = []
    if (correct_prompt.count(_CAP_BEGIN) != 1
            or correct_prompt.count(_CAP_END) != 1):
        out.append("SYMMETRY-FAIL: capability-access delimiters != 1 each "
                   "in correct prompt")
        return out
    if correct_prompt.index(_CAP_BEGIN) > correct_prompt.index(_CAP_END):
        out.append("SYMMETRY-FAIL: capability-access end before begin")
        return out
    if _CAP_BEGIN in disabled_prompt or _CAP_END in disabled_prompt:
        out.append("SYMMETRY-FAIL: capability-access block present in "
                   "disabled prompt")
    for name, prompt in (("correct", correct_prompt),
                         ("disabled", disabled_prompt)):
        if prompt.count(envelope) != 1:
            out.append(f"SYMMETRY-FAIL: canonical envelope not "
                       f"verbatim-once in {name} prompt (hint asymmetry "
                       f"or drift in the shared region)")
    if out:
        return out
    head_c, tail_c = correct_prompt.split(envelope)
    head_d, tail_d = disabled_prompt.split(envelope)
    if head_c != _PRE_CORRECT:
        out.append("SYMMETRY-FAIL: correct preamble differs from the "
                   "frozen arm preamble")
    if head_d != _PRE_DISABLED:
        out.append("SYMMETRY-FAIL: disabled preamble differs from the "
                   "frozen arm preamble")
    if tail_d != _OUT_DISABLED:
        out.append("SYMMETRY-FAIL: disabled prompt carries content past "
                   "the envelope other than the frozen output schema")
    if not tail_c.startswith("\n" + _CAP_BEGIN + "\n"):
        out.append("SYMMETRY-FAIL: correct capability block misdelimited "
                   "after the envelope")
    elif tail_c.count(_CAP_END + "\n") != 1:
        out.append("SYMMETRY-FAIL: correct capability block end "
                   "misdelimited")
    elif not tail_c.endswith(_OUT_CORRECT):
        out.append("SYMMETRY-FAIL: correct prompt output schema differs "
                   "from the frozen arm schema")
    else:
        body = tail_c[len("\n" + _CAP_BEGIN + "\n"):
                      -len(_CAP_END + "\n" + _OUT_CORRECT)]
        for marker in ("CAPABILITY MANIFEST:", "ADAPTER NOTES:",
                       "ENGINE SOURCE (frozen, do not modify):"):
            if marker not in body:
                out.append("SYMMETRY-FAIL: capability block missing the "
                           f"frozen section header {marker!r}")
        if not body.strip():
            out.append("SYMMETRY-FAIL: capability-access block empty")
    return out


def h(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def extract(raw, arm):
    i = raw.find('{"records"' if arm == "correct" else '{"solver_py"')
    if i >= 0:
        return json.JSONDecoder().raw_decode(raw[i:])[0], "json-envelope"
    m = re.search(r"```(?:json|python)?\s*(.*?)\s*```", raw, re.S)
    if arm == "disabled" and m:
        return {"solver_py": m.group(1), "notes": "fenced arrival"}, "fence-fallback"
    raise ValueError("arrival has no parseable envelope")


def call(lane, prompt, outdir, tag):
    cfg = LANES[lane]
    key = open(cfg["keyfile"]).read().strip()
    # Item-3 hardening: ONE explicit generation-param set, defined once and
    # sent AND recorded identically — never two literals that can drift.
    extra_body = {"max_tokens": 9000}
    reply, receipt, resp = recorded_call(
        cfg["base"], cfg["keyfile"], key, cfg["model"],
        [{"role": "user", "content": prompt}], outdir,
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
                              request_body_sha256=body_sha)
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


def _verify_capability(capdir):
    """H-LOCK-008: resolve the capability ONLY by exact locked hash.
    Returns lock info dict; raises PermissionError on any mismatch."""
    # Item-7 foreign-registry refusal: the capability registry surface is the
    # frozen Fam-C tree (capabilities/ or a run dir inside it). A capability
    # dir outside it is a foreign registry and never enters a measured cell.
    r_cap = os.path.realpath(capdir)
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


def _wire_chain(outdir, frozen, manifest, receipt, nu_path, identity_path,
                identity_family, cap_info, reuse_path, checker_sha, truth_sha,
                verdict, output_sha, promote_info):
    """Emit the H3 evidence chain for one completed run (fail closed).
    Genesis binds `manifest`; the on-disk H1-RUN-MANIFEST.json must never be
    rewritten after this call (rewriting would break genesis hash equality)."""
    chain_path = os.path.join(outdir, CHAIN_FILE)
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
        "generation_params": id_rec.get("generation_params"),
        "normalized_file": os.path.basename(nu_path),
        "normalized_sha256": h(nu_path),
        "primary_work": nu["primary_work"],
        "input_tokens_uncached": nu["input_tokens_uncached"],
        "output_tokens": nu["output_tokens"],
        "cached_tokens": nu["cached_tokens"],
        "call_count": 1}
    if identity_path is not None:
        if not os.path.exists(identity_path):
            raise RuntimeError(f"CHAIN-IDENTITY-MISSING {identity_path}")
        mc["identity_file"] = os.path.basename(identity_path)
        mc["identity_sha256"] = h(identity_path)
        mc["identity_prereg_family"] = identity_family
    c.append("model-call", mc)
    # capability events (correct arm only).
    if cap_info:
        c.append("capability-event", {
            "event": "reuse", "capability_id": cap_info["capability_id"],
            "capability_version": cap_info.get("capability_version"),
            "lock_sha256": cap_info["lock_sha256"],
            "engine_sha256": cap_info["engine_sha256"],
            "verified_pre_execution": True,
            "loaded": True, "invoked": True, "output_consumed": True,
            "materially_contributed": False,
            "evidence": "consumed but not proven contributed: no ablation "
                        "or downstream-node hash-linkage in this cell"})
    # evaluator link: sealed truth + checker hashes + host-side outcome.
    ev_link = c.append("evaluator", {
        "checker_sha256": checker_sha, "truth_sha256": truth_sha,
        "output_sha256": output_sha,
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
        json.dump({"call_id": "fx-1", "tag": "selfcheck",
                   "model_requested": "fx", "endpoint": "https://fx/v1",
                   "request_body_sha256": "fx-req-body",
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
        manifest = {"lane": "P", "family": "famXX", "task": "T0", "arm": "correct",
                    "wired": True, "frozen_commit": "deadbeef" * 5,
                    "usage_receipts": [os.path.basename(receipt)],
                    "usage_normalized": [os.path.basename(nu_path)],
                    "identity_file": "identity.json",
                    "checker_returncode": 0, "output_sha256": "fx",
                    "verdict": "ship"}
        # promote composes (writes once) and load_artifact verifies by hash.
        lock_path = lock_promote(
            capdir, "famXX-fixture", "v1",
            [os.path.join(capdir, "engine.py"),
             os.path.join(capdir, "manifest.json"),
             os.path.join(capdir, "adapter_notes.md")],
            manifest, [receipt],
            {"lane": "P", "builder": "selfcheck"})
        assert os.path.exists(lock_path), "promote did not write lock"
        v = load_artifact(lock_path, "engine.py", capdir)
        assert v.endswith("engine.py"), "load_artifact wrong path"
        cap = _verify_capability(capdir)
        assert cap["engine_sha256"] == h(os.path.join(capdir, "engine.py"))
        reuse = reuse_write_record(
            tmp, "famXX-T0", "P", "correct",
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
        idp = record_identity(tmp, "https://fx/v1", "fx",
                              {"model": "fx", "id": "fx-1", "created": 1},
                              extra_params={"max_tokens": 9000},
                              tag="selfcheck",
                              request_body_sha256="fx-req-body")
        assert check_against_prereg(
            idp, {"endpoint": "https://fx/v1", "requested_id": "fx",
                  "acceptable_echoed_ids": ["fx"],
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
        assert mc_payload.get("request_body_sha256") == "fx-req-body"
        assert mc_payload.get("generation_params") == {"max_tokens": 9000}
        # repromotion refused (H-LOCK-008 writes-once).
        try:
            lock_promote(capdir, "famXX-fixture", "v2",
                         [os.path.join(capdir, "engine.py")], manifest,
                         [receipt], {"lane": "P"})
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


def prepare_arm(lane, family, task, arm, capdir, wire, run_id):
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
            cap_info = _verify_capability(capdir)
            cap_engine = cap_info["verified"]["engine.py"]
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
        prompt = build_arm_prompt("disabled", envelope)
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


def main(lane, family, task, arm, outdir, capdir=None, opts=None):
    opts = opts or {}
    wire = opts.get("wire", True)
    promote_dir = opts.get("promote_dir")
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
    done_cells = order_completed_cells(os.path.join(BASE, "runs"))
    cell, order_findings = order_authorize(
        expansion, block, family, task, lane, arm, done_cells)
    if order_findings:
        raise RuntimeError("ORDER-DENY refuse start: "
                           + " | ".join(order_findings))
    # Refuse-START: the executed instance subtree must be byte-identical to
    # the frozen package BEFORE any model token is spent. Item-5: the
    # manifest is resolved from the freeze commit via git (the working-tree
    # copy is never trusted), and freeze_anchors() above already proved the
    # recorded freeze_tree equals that commit's tree of the frozen root.
    verify_instance_frozen(BASE, family, task,
                           freeze_commit=instance_freeze_commit)
    frozen = instance_freeze_commit
    os.makedirs(outdir, exist_ok=True)
    taskdir = os.path.join(BASE, "families", family, task)
    # ---- Item-6 ONE SOURCE SNAPSHOT (audit round 2 item 6) -------------
    run_id = hashlib.sha256(
        f"{lane}|{family}|{task}|{arm}|{time.time()}".encode()).hexdigest()[:12]
    prep = prepare_arm(lane, family, task, arm, capdir, wire, run_id)
    prompt = prep["prompt"]
    envelope = prep["envelope"]
    work, visible = prep["work"], prep["visible"]
    copied, refused = prep["copied"], prep["refused"]
    staged_tree = prep["staged_tree"]
    context_task_snapshot_hash = prep["context_task_snapshot_hash"]
    sym = prep["symmetry"]
    cap_info, cap_engine = prep["cap_info"], prep["cap_engine"]
    open(os.path.join(outdir, "prompt.txt"), "w").write(prompt)
    raw, receipt, nu_path, id_path, identity_family = call(
        lane, prompt, outdir, f"H1-{lane}-{family}-{task}-{arm}")
    arrival, parse_mode = extract(raw, arm)
    open(os.path.join(outdir, "arrival.json"), "w").write(json.dumps(arrival, indent=1))
    # DockerSandbox stages its own private copy of `visible` and refuses on
    # drift; its task_snapshot must equal the hash the context was built
    # from (same staged bytes -> same hash), else refuse.
    sb = DockerSandbox(work, visible)
    if sb.task_snapshot != staged_tree:
        raise RuntimeError("CONTEXT-SNAPSHOT-DENY sandbox task_snapshot != "
                           "context_task_snapshot_hash source")
    # Execute arrival inside H1 jail. No evaluator/truth/checker is mounted.
    command = None
    if arm == "correct":
        shutil.copy2(cap_engine, os.path.join(work, "engine.py"))
        json.dump(arrival["records"], open(os.path.join(work, "records.json"), "w"))
        json.dump(arrival["field_map"], open(os.path.join(work, "field_map.json"), "w"))
        command = ["python3", "/work/engine.py", "/work/field_map.json",
                   "/work/records.json", "/work/OUTPUT.json"]
    elif arm == "disabled":
        open(os.path.join(work, "solver.py"), "w").write(arrival["solver_py"])
        command = ["python3", "/work/solver.py", "/task", "/work/OUTPUT.json"]
    else:
        raise ValueError("unknown arm")
    p = sb.run(command, timeout=120)
    out = os.path.join(work, "OUTPUT.json")
    # Copy artifacts back to the committed outdir for auditability.
    shutil.copy2(out, os.path.join(outdir, "OUTPUT.json")) if os.path.exists(out) else None
    # Host-side evaluator only after container; truth/checker never entered jail.
    checker = os.path.join(taskdir, "..", "check.py")
    chk = subprocess.run([sys.executable, checker, task,
                          os.path.join(outdir, "OUTPUT.json")],
                         capture_output=True, text=True) if os.path.exists(out) else None
    verdict = ("ship" if chk and chk.returncode == 0 else
               "fix" if chk and chk.returncode == 1 else "blocked")
    output_sha = h(out) if os.path.exists(out) else None

    # ---- H2/H3 wiring (skipped only under the unwired dev escape) ----
    reuse_path = None
    if wire and cap_info:
        # Reuse ledger: correct arm reused a previously locked capability.
        reuse_path = reuse_write_record(
            outdir, f"{family}-{task}", lane, arm,
            reuse_policy="PREREG-frozen: single locked capability per "
                         "(family, producer lane); consumer loads by locked hash",
            capability_available=True,
            capability_candidate_ids=[cap_info["capability_id"]],
            capability_selected=True,
            selected_capability_id=cap_info["capability_id"],
            selected_capability_hash=cap_info["engine_sha256"],
            capability_loaded=True, capability_invoked=True,
            capability_output_consumed=True,
            capability_materially_contributed=False,
            contribution_evidence={"mechanism": "none",
                                   "reason": "consumed but not proven "
                                             "contributed: no ablation or "
                                             "downstream-node hash-linkage "
                                             "in this cell"},
            reuse_rejected=False, reuse_rejection_reason=None)

    manifest = {"lane": lane, "family": family, "task": task, "arm": arm,
                "parse_mode": parse_mode, "lane_receipt": receipt,
                "sandbox": sb.manifest(), "task_snapshot": sb.task_snapshot,
                "container_returncode": p.returncode,
                "checker_returncode": chk.returncode if chk else None,
                "checker_output": (chk.stdout + chk.stderr)[:500] if chk else "missing output",
                "verdict": verdict, "output_sha256": output_sha,
                "wired": bool(wire),
                "frozen_commit": frozen,
                # Item-7 order binding: this manifest is the completion
                # record for exactly one authorized cell.
                "block": block,
                "cell_id": cell["cell_id"],
                "cell_index": cell["index"],
                "cell_letter": cell["letter"],
                "cell_lane_key": cell["lane_key"],
                "order_sha256": expansion["order_sha256"],
                "instance_freeze_commit": instance_freeze_commit,
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
                "chain": CHAIN_FILE if wire else None,
                "reuse_record": os.path.basename(reuse_path) if reuse_path else None,
                "capability": {k: cap_info[k] for k in
                               ("capability_id", "capability_version",
                                "lock_sha256", "engine_sha256")
                               if cap_info and k in cap_info} or None,
                "capability_lock": None}

    # Promotion: a capability ships only on a ship verdict under an explicit
    # --promote (writes once; repromotion refused fail-closed). The lock
    # embeds this final manifest as its manifest_sha binding.
    promote_info = None
    if wire and promote_dir and verdict == "ship" and cap_info:
        arts = [cap_info["verified"][n] for n in
                ("engine.py", "manifest.json", "adapter_notes.md")
                if n in cap_info["verified"]]
        lock_path = lock_promote(
            promote_dir, cap_info["capability_id"],
            cap_info.get("capability_version") or "v1", arts, manifest,
            [receipt], {"lane": lane, "family": family, "task": task,
                        "arm": arm, "frozen_commit": frozen,
                        "run_outdir": outdir})
        promote_info = {"capability_id": cap_info["capability_id"],
                        "lock_path": lock_path,
                        "lock_sha256": h(lock_path),
                        "builder": {"lane": lane, "family": family,
                                    "task": task}}
        manifest["capability_lock"] = os.path.basename(lock_path)

    # Manifest is final NOW: write it once, then genesis binds this object.
    json.dump(manifest, open(os.path.join(outdir, "H1-RUN-MANIFEST.json"), "w"), indent=1)

    if wire:
        checker_sha = h(checker) if os.path.exists(checker) else None
        truth = os.path.join(taskdir, "..", "truth.json")
        truth_sha = h(truth) if os.path.exists(truth) else None
        _wire_chain(outdir, frozen, manifest, receipt, nu_path, id_path,
                    identity_family, cap_info, reuse_path, checker_sha,
                    truth_sha, verdict, output_sha, promote_info)
        # H1-RUN-MANIFEST.json must NOT be rewritten after _wire_chain:
        # genesis binds its hash and any rewrite would break the chain.
    print(f"{lane}/{family}/{task}/{arm}: {verdict} ({parse_mode}, container rc {p.returncode})")
    return 0 if verdict in ("ship", "fix") else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    opts = {}
    if "--block" in argv:
        i = argv.index("--block")
        opts["block"] = argv[i + 1].upper()
        del argv[i:i + 2]
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
    if "--promote" in argv:
        i = argv.index("--promote")
        opts["promote_dir"] = argv[i + 1]
        del argv[i:i + 2]
    main(argv[0], argv[1], argv[2], argv[3], argv[4],
         argv[5] if len(argv) > 5 else None, opts)

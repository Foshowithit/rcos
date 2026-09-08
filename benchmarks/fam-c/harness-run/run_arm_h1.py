#!/usr/bin/env python3
"""H1-integrated Fam-C arm runner, H2/H3-wired.

Model calls happen in the harness process (the only network-capable process).
The model receives only the frozen prompt + exact visible fixture bytes;
arrival execution happens in DockerSandbox (--network none, exactly /work rw
+ /task ro, digest-pinned image). Evaluator runs on the host only after the
container exits and is never mounted into it.

Wiring (ON by default; --no-wire restores the legacy unlinked behavior):
- H2 usage: every model call goes through usage.recorded_call(); the raw
  provider usage block + identity receipt is persisted per call and each
  receipt is bound into the run's evidence chain as a model-call link.
- H3 chain: every completed run emits EVIDENCE-CHAIN.jsonl — genesis binds
  the frozen commit + final run manifest; links then record model calls,
  capability events (reuse / promote), the evaluator (sealed truth + checker
  hashes + verdict), and a terminal grade. Chain.audit() re-verifies every
  link before the run returns; any finding aborts loudly (never silent).
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

Usage: run_arm_h1.py [--no-wire] [--promote <capstore_dir>] \\
    <lane P|Q> <family> <task> <correct|disabled> <outdir> [capdir]
      --no-wire      legacy behavior: no chain/reuse/lock records.
      --promote DIR  on a ship verdict, write CAPABILITY_LOCK.json into DIR
                     for the capability consumed by this run (writes once).
      --selfcheck-wire  offline fixture compose-test of the wiring (no model
                     call, no docker, no run) — CI use only.
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
from dockersandbox import DockerSandbox, ensure_roots
from seal import build_visible_root
from usage import recorded_call
from chain import Chain
from lock import promote as lock_promote, load_artifact
from reuse_log import write_record as reuse_write_record

CHAIN_FILE = "EVIDENCE-CHAIN.jsonl"
GRADING_RULE_VERSION = "checker-contract-v1"
GRADING_RULE_NOTE = ("mechanical grade = frozen checker returncode mapping "
                     "(rc0=ship, rc1=fix, else blocked); rule hash = sha256 "
                     "of the executed checker bytes")

LANES = {
    "P": {"keyfile": "/home/chow/.agent-vault/keys/router9.key",
          "base": "https://api.router9.com/v1", "model": "minimax-m3",
          "family": "MiniMax", "normalizer": "openai-chat-total-input-v1"},
    "Q": {"keyfile": "/home/chow/.agent-vault/keys/kenari.key",
          "base": "https://kenari.id/v1", "model": "agnes-2-0-flash:free",
          "family": "Kenari-Agnes", "normalizer": "openai-chat-total-input-v1"},
}

CORRECT = """You are solving the task below using a PROVIDED capability interface. You have never seen its acquisition, no transcripts, no prior tasks. Output ONLY one JSON object, no other text.

TASK DEFINITION:
__TASKDEF__

TASK DIRECTORY LISTING: __LISTING__
TASK FILE CONTENTS (exact bytes):
__BLOBS__

CAPABILITY MANIFEST:
__MANIFEST__
ADAPTER NOTES:
__NOTES__
ENGINE SOURCE (frozen, do not modify):
__ENGINE__

Output object: {"records": <engine records>, "field_map": <engine map>, "notes": "one line"}. No explanations/fences."""
DISABLED = """You are solving the task below from scratch. No registry/capability/prior solution exists. Output ONLY one JSON object, no other text.

TASK DEFINITION:
__TASKDEF__

TASK DIRECTORY LISTING: __LISTING__
TASK FILE CONTENTS (exact bytes):
__BLOBS__

Output object: {"solver_py": <complete Python script taking (src_dir, dst_path) and writing the ordinary task output>, "notes": "one line"}. No explanations/fences."""


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
    reply, receipt = recorded_call(
        cfg["base"], cfg["keyfile"], key, cfg["model"],
        [{"role": "user", "content": prompt}], outdir,
        extra_body={"max_tokens": 9000}, timeout=300, tag=tag,
        normalizer_id=cfg["normalizer"])
    open(os.path.join(outdir, "raw.txt"), "w").write(reply)
    return reply, receipt


def frozen_commit():
    p = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("FROZEN-COMMIT-UNAVAILABLE: "
                           + (p.stderr or p.stdout)[:200])
    return p.stdout.strip()


def _verify_capability(capdir):
    """H-LOCK-008: resolve the capability ONLY by exact locked hash.
    Returns lock info dict; raises PermissionError on any mismatch."""
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


def _wire_chain(outdir, frozen, manifest, receipt, cap_info, reuse_path,
                checker_sha, truth_sha, verdict, output_sha, promote_info):
    """Emit the H3 evidence chain for one completed run (fail closed).
    Genesis binds `manifest`; the on-disk H1-RUN-MANIFEST.json must never be
    rewritten after this call (rewriting would break genesis hash equality)."""
    chain_path = os.path.join(outdir, CHAIN_FILE)
    c = Chain(chain_path, frozen, manifest, arm=manifest.get("arm"))
    # model-call link(s): every persisted H2 usage receipt binds here.
    try:
        rc = json.load(open(receipt))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"CHAIN-RECEIPT-UNREADABLE {receipt}: {e}")
    c.append("model-call", {
        "call_id": rc.get("call_id"), "tag": rc.get("tag"),
        "model_requested": rc.get("model_requested"),
        "endpoint": rc.get("endpoint"),
        "receipt_file": os.path.basename(receipt),
        "receipt_sha256": h(receipt),
        "usage_raw_sha256": rc.get("usage_raw_sha256")})
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
    tmp = tempfile.mkdtemp(prefix="rcos-wire-selfcheck-")
    try:
        capdir = os.path.join(tmp, "capstore")
        os.makedirs(capdir)
        open(os.path.join(capdir, "engine.py"), "w").write(
            "def run(fm, rec, out):\n    open(out, 'w').write('{}')\n")
        open(os.path.join(capdir, "manifest.json"), "w").write(
            json.dumps({"capability": "fixture"}))
        open(os.path.join(capdir, "adapter_notes.md"), "w").write("fixture")
        receipt = os.path.join(tmp, "call-fixture.json")
        json.dump({"call_id": "fx-1", "tag": "selfcheck", "model_requested": "fx",
                   "endpoint": "https://fx/v1", "usage_raw_sha256": "fx"},
                  open(receipt, "w"))
        manifest = {"lane": "P", "family": "famXX", "task": "T0", "arm": "correct",
                    "wired": True, "frozen_commit": "deadbeef" * 5,
                    "usage_receipts": [os.path.basename(receipt)],
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
        tip = _wire_chain(tmp, manifest["frozen_commit"], manifest, receipt,
                          cap, reuse, h(os.path.join(capdir, "engine.py")),
                          None, "ship", "fx", None)
        assert isinstance(tip, str) and len(tip) == 64, "bad chain tip"
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


def main(lane, family, task, arm, outdir, capdir=None, opts=None):
    opts = opts or {}
    wire = opts.get("wire", True)
    promote_dir = opts.get("promote_dir")
    frozen = frozen_commit() if wire else None
    ensure_roots()
    os.makedirs(outdir, exist_ok=True)
    taskdir = os.path.join(BASE, "families", family, task)
    taskdef = open(os.path.join(taskdir, "prompt.md")).read()
    listing = ", ".join(sorted(os.listdir(taskdir)))
    blobs = []
    for root, _dirs, files in os.walk(taskdir):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, taskdir)
            if fn not in ("prompt.md", "VISIBLE.md") and os.path.getsize(p) <= 4096:
                blobs.append(f"--- {rel} ---\n" + open(p).read())
    block = "\n".join(blobs)
    cap_info = None
    if arm == "correct":
        if not capdir:
            raise ValueError("correct arm requires locked capability dir")
        prompt = CORRECT.replace("__TASKDEF__", taskdef).replace(
            "__LISTING__", listing).replace("__BLOBS__", block).replace(
            "__MANIFEST__", open(os.path.join(capdir, "manifest.json")).read()).replace(
            "__NOTES__", open(os.path.join(capdir, "adapter_notes.md")).read()).replace(
            "__ENGINE__", open(os.path.join(capdir, "engine.py")).read())
        if wire:
            # H-LOCK-008: resolve the executed engine by exact locked hash
            # BEFORE it enters the jail. Legacy --no-wire copies unverified.
            cap_info = _verify_capability(capdir)
            cap_engine = cap_info["verified"]["engine.py"]
        else:
            cap_engine = os.path.join(capdir, "engine.py")
    else:
        prompt = DISABLED.replace("__TASKDEF__", taskdef).replace(
            "__LISTING__", listing).replace("__BLOBS__", block)
    open(os.path.join(outdir, "prompt.txt"), "w").write(prompt)
    raw, receipt = call(lane, prompt, outdir, f"H1-{lane}-{family}-{task}-{arm}")
    arrival, parse_mode = extract(raw, arm)
    open(os.path.join(outdir, "arrival.json"), "w").write(json.dumps(arrival, indent=1))
    # Stage under trusted roots (DockerSandbox rejects outside paths).
    run_id = hashlib.sha256(f"{lane}|{family}|{task}|{arm}|{time.time()}".encode()).hexdigest()[:12]
    work = os.path.join("/tmp/rcos-runs", "famc-" + run_id)
    visible = os.path.join("/tmp/rcos-visible", "famc-" + run_id)
    os.makedirs(work, exist_ok=True)
    build_visible_root(taskdir, visible)
    sb = DockerSandbox(work, visible)
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

    # ---- H2/H3 wiring (skipped entirely under --no-wire) ----
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
                "usage_receipts": [os.path.basename(receipt)] if wire else [],
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
        _wire_chain(outdir, frozen, manifest, receipt, cap_info, reuse_path,
                    checker_sha, truth_sha, verdict, output_sha, promote_info)
        # H1-RUN-MANIFEST.json must NOT be rewritten after _wire_chain:
        # genesis binds its hash and any rewrite would break the chain.
    print(f"{lane}/{family}/{task}/{arm}: {verdict} ({parse_mode}, container rc {p.returncode})")
    return 0 if verdict in ("ship", "fix") else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--selfcheck-wire" in argv:
        sys.exit(selfcheck_wire())
    opts = {}
    if "--no-wire" in argv:
        opts["wire"] = False
        argv = [a for a in argv if a != "--no-wire"]
    if "--promote" in argv:
        i = argv.index("--promote")
        opts["promote_dir"] = argv[i + 1]
        del argv[i:i + 2]
    main(argv[0], argv[1], argv[2], argv[3], argv[4],
         argv[5] if len(argv) > 5 else None, opts)

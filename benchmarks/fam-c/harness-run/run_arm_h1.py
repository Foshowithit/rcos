#!/usr/bin/env python3
"""H1-integrated Fam-C arm runner.

Model calls happen in the harness process (the only network-capable process).
The model receives only the frozen prompt + exact visible fixture bytes;
arrival execution happens in DockerSandbox (--network none, exactly /work rw
+ /task ro, digest-pinned image). Evaluator runs on the host only after the
container exits and is never mounted into it.

Usage: run_arm_h1.py <lane P|Q> <family> <task> <correct|disabled> <outdir> [capdir]
No P/Q calls are made by smoke; use the script only after H1 smoke is green.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = "/home/chow/chow-work/rcos/benchmarks/fam-c"
HARNESS = "/home/chow/chow-work/rcos/harness"
sys.path.insert(0, HARNESS)
from dockersandbox import DockerSandbox, ensure_roots
from seal import build_visible_root
from usage import recorded_call

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


def main(lane, family, task, arm, outdir, capdir=None):
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
    if arm == "correct":
        if not capdir:
            raise ValueError("correct arm requires locked capability dir")
        prompt = CORRECT.replace("__TASKDEF__", taskdef).replace(
            "__LISTING__", listing).replace("__BLOBS__", block).replace(
            "__MANIFEST__", open(os.path.join(capdir, "manifest.json")).read()).replace(
            "__NOTES__", open(os.path.join(capdir, "adapter_notes.md")).read()).replace(
            "__ENGINE__", open(os.path.join(capdir, "engine.py")).read())
    else:
        prompt = DISABLED.replace("__TASKDEF__", taskdef).replace(
            "__LISTING__", listing).replace("__BLOBS__", block)
    open(os.path.join(outdir, "prompt.txt"), "w").write(prompt)
    raw, receipt = call(lane, prompt, outdir, f"H1-{lane}-{family}-{task}-{arm}")
    arrival, parse_mode = extract(raw, arm)
    open(os.path.join(outdir, "arrival.json"), "w").write(json.dumps(arrival, indent=1))
    work = os.path.join(outdir, "work")
    visible = os.path.join("/tmp/rcos-visible", "famc", lane, family, task, arm)
    os.makedirs(work, exist_ok=True)
    build_visible_root(taskdir, visible)
    sb = DockerSandbox(work, visible)
    # Execute arrival inside H1 jail. No evaluator/truth/checker is mounted.
    if arm == "correct":
        engine = os.path.join(work, "engine.py")
        shutil.copy2(os.path.join(capdir, "engine.py"), engine)
        json.dump(arrival["records"], open(os.path.join(work, "records.json"), "w"))
        json.dump(arrival["field_map"], open(os.path.join(work, "field_map.json"), "w"))
        command = ["python3", "/work/engine.py", "/work/field_map.json",
                   "/work/records.json", "/work/OUTPUT.json"]
    else:
        open(os.path.join(work, "solver.py"), "w").write(arrival["solver_py"])
        command = ["python3", "/work/solver.py", "/task", "/work/OUTPUT.json"]
    p = sb.run(command, timeout=120)
    out = os.path.join(work, "OUTPUT.json")
    # Host-side evaluator only after container; truth/checker never entered jail.
    checker = os.path.join(taskdir, "..", "check.py")
    chk = subprocess.run([sys.executable, checker, task, out],
                         capture_output=True, text=True) if os.path.exists(out) else None
    verdict = ("ship" if chk and chk.returncode == 0 else
               "fix" if chk and chk.returncode == 1 else "blocked")
    manifest = {"lane": lane, "family": family, "task": task, "arm": arm,
                "parse_mode": parse_mode, "lane_receipt": receipt,
                "sandbox": sb.manifest(), "task_snapshot": sb.task_snapshot,
                "container_returncode": p.returncode,
                "checker_returncode": chk.returncode if chk else None,
                "checker_output": (chk.stdout + chk.stderr)[:500] if chk else "missing output",
                "verdict": verdict, "output_sha256": h(out) if os.path.exists(out) else None}
    json.dump(manifest, open(os.path.join(outdir, "H1-RUN-MANIFEST.json"), "w"), indent=1)
    print(f"{lane}/{family}/{task}/{arm}: {verdict} ({parse_mode}, container rc {p.returncode})")
    return 0 if verdict in ("ship", "fix") else 1


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
         sys.argv[6] if len(sys.argv) > 6 else None)

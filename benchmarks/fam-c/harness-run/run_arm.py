#!/usr/bin/env python3
"""Fam-C arm runner: one lane, one task, one arm. Mechanical scheduler.
Usage: run_arm.py <lane P|Q> <family> <task> <arm correct|disabled> <outdir>
- correct: capability interface only (manifest + adapter_notes + frozen
  engine source; NO acquisition history, NO transcripts).
- disabled: task input only, fresh solve (solver script expected).
Saves raw response + usage + lane record byte-identical. Executes
arrivals verbatim inside DockerSandbox. Grades mechanically.
Stdlib only.
"""
import json
import os
import sys
import time
import urllib.request

BASE = "/home/chow/chow-work/rcos/benchmarks/fam-c"
sys.path.insert(0, "/home/chow/chow-work/rcos/harness")
from usage import recorded_call

LANES = {
    "P": {"keyfile": "/home/chow/.agent-vault/keys/router9.key",
          "base": "https://api.router9.com/v1",
          "model": "minimax-m3", "norm": "openai-chat-total-input-v1",
          "family": "MiniMax"},
    "Q": {"keyfile": "/home/chow/.agent-vault/keys/kenari.key",
          "base": "https://kenari.id/v1",
          "model": "agnes-2-0-flash:free", "norm": "openai-chat-total-input-v1",
          "family": "Kenari-Agnes"},
}

CORRECT_TMPL = """You are solving a file-verification task using a PROVIDED capability. You have never seen its acquisition, no transcripts, no prior tasks. Output ONLY one JSON object, no other text.

TASK INPUT, file __FILE__:
```
__INPUT__
```
TASK DIRECTORY LISTING: __LISTING__

TASK FILE CONTENTS (exact bytes of small fixtures):
```
__BLOBS__
```

PROMOTED CAPABILITY INTERFACE (only procedural knowledge you receive):
manifest: __MANIFEST__

ADAPTER NOTES:
__NOTES__

ENGINE SOURCE (frozen artifact; you do not modify it, you supply its inputs):
```python
__ENGINE__
```

GOAL: verify each listed file's actual size and sha256 against the manifest. Output contract: {"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]}.

RESPONSE FORMAT: think for at most a few sentences, then output ONLY one JSON object and stop. No explanations, no fences, no trailing text:
{"records": {<flat records dict for the engine>}, "field_map": {<map per interface convention>}, "notes": "<one line>"}
No explanations; output the object only."""

DISABLED_TMPL = """You are solving a file-verification task from scratch. No registry, no capabilities, no prior solutions exist. Output ONLY one JSON object, no other text.

TASK INPUT, file __FILE__:
```
__INPUT__
```
TASK DIRECTORY LISTING: __LISTING__

TASK FILE CONTENTS (exact bytes of small fixtures):
```
__BLOBS__
```

GOAL: verify each listed file's actual size and sha256 against the manifest. Output contract: {"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]} (entries that cannot be checked against local sha256 files go under `unverified`).

RESPONSE FORMAT: think for at most a few sentences, then output ONLY one JSON object and stop. No explanations, no fences, no trailing text:
{"solver_py": "<complete python3 stdlib script reading (manifest_path, files_dir, out_path) and writing the output contract>", "notes": "<one line>"}
No explanations; output the object only."""


def call_lane(lane, prompt, outdir, tag):
    cfg = LANES[lane]
    key = open(cfg["keyfile"]).read().strip()
    body = json.dumps({"model": cfg["model"], "max_tokens": 9000,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    req = urllib.request.Request(
        cfg["base"] + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=300)
    d = json.load(r)
    wall = time.time() - t0
    raw = d["choices"][0]["message"]["content"]
    open(os.path.join(outdir, "raw.txt"), "w").write(raw)
    open(os.path.join(outdir, "usage.json"), "w").write(json.dumps(
        {"lane": lane, "model": cfg["model"], "wall_s": round(wall, 1),
         "usage": d.get("usage", {})}, indent=1))
    open(os.path.join(outdir, "lane.json"), "w").write(json.dumps(
        {"provider": cfg["base"], "model_requested": cfg["model"],
         "model_family": cfg["family"], "normalizer": cfg["norm"]},
        indent=1))
    return raw


def main(lane, family, task, arm, outdir):
    tdir = os.path.join(BASE, "families", family, task)
    # task input = first manifest-ish file
    cands = [f for f in sorted(os.listdir(tdir))
             if os.path.isfile(os.path.join(tdir, f))
             and f not in ("prompt.md", "VISIBLE.md")]
    man_file = next((f for f in cands if "manifest" in f.lower() or "MANIFEST" in f), cands[0])
    text = open(os.path.join(tdir, man_file)).read()
    listing = ", ".join(sorted(os.listdir(tdir)))
    blobs = []
    for _root, _dirs, _files in os.walk(tdir):
        for fn in sorted(_files):
            fp = os.path.join(_root, fn)
            rel = os.path.relpath(fp, tdir)
            if os.path.getsize(fp) <= 2048 and fn not in ("prompt.md", "VISIBLE.md"):
                blobs.append(f"--- {rel} ({os.path.getsize(fp)} bytes) ---\n"
                             + open(fp).read())
    fileblock = "\n".join(blobs)
    if arm == "correct":
        cap = os.path.join(BASE, "capabilities/manifest-verify-v1")
        man = open(os.path.join(cap, "manifest.json")).read()
        notes = open(os.path.join(cap, "adapter_notes.md")).read()
        eng = open(os.path.join(cap, "engine.py")).read()
        prompt = CORRECT_TMPL.replace("__FILE__", man_file).replace(
            "__INPUT__", text).replace("__LISTING__", listing).replace(
            "__BLOBS__", fileblock).replace(
            "__MANIFEST__", man).replace("__NOTES__", notes).replace(
            "__ENGINE__", eng)
    else:
        prompt = DISABLED_TMPL.replace("__FILE__", man_file).replace(
            "__INPUT__", text).replace("__LISTING__", listing).replace(
            "__BLOBS__", fileblock)
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "prompt.txt"), "w").write(prompt)
    raw = call_lane(lane, prompt, outdir, f"{lane}-{family}-{task}-{arm}")
    print(f"{lane} {family}/{task}/{arm}: {len(raw)} chars (prompt persisted)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])

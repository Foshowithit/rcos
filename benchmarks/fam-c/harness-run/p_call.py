#!/usr/bin/env python3
"""Fam-C producer calls (role P, minimax lane). Mechanical scheduler only:
frozen prompts, raw outputs saved byte-identical, usage captured via H2
recorded_call. No semantic edits, no retries on judgment. Stdlib only."""
import json
import os
import sys

sys.path.insert(0, "/home/chow/chow-work/rcos/harness")
from usage import recorded_call

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KEY = open("/home/chow/.agent-vault/keys/router9.key").read().strip()
EP = "https://api.router9.com/v1"
MODEL = "minimax-m3"
NORM = "openai-chat-total-input-v1"

PROMPT = """You are solving a file-verification task from scratch. No registry, no capabilities, no prior solutions exist. Output ONLY one JSON object, no other text.

TASK INPUT, file __FILE__:
```
__INPUT__
```

GOAL: verify each listed file's actual size and sha256 against the manifest. Output contract: {"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]} (entries that cannot be checked against local sha256 files go under `unverified`).

RESPONSE FORMAT (one JSON object only):
{"solver_py": "<complete python3 stdlib script reading (manifest_path, files_dir, out_path) and writing the output contract>", "notes": "<one line, no explanation>"}
No explanations; output the object only."""


def main(task_id, task_file, outdir):
    os.makedirs(outdir, exist_ok=True)
    text = open(task_file).read()
    tdir = os.path.dirname(task_file)
    listing = sorted(os.listdir(tdir))
    prompt = PROMPT.replace("__FILE__", os.path.basename(task_file)).replace(
        "__INPUT__", text)
    prompt = prompt + ("\nTASK DIRECTORY LISTING (files beside the manifest): "
                       + ", ".join(listing) + "\n")
    reply, receipt = recorded_call(
        EP, "K", KEY, MODEL, [{"role": "user", "content": prompt}],
        outdir, extra_body={"max_tokens": 3000}, timeout=300,
        tag=f"P-{task_id}", normalizer_id=NORM)
    open(os.path.join(outdir, "raw.txt"), "w").write(reply)
    open(os.path.join(outdir, "lane.json"), "w").write(json.dumps(
        {"provider": "router9", "model_requested": MODEL,
         "normalizer": NORM}, indent=1))
    print(f"P {task_id}: {len(reply)} chars; receipt {receipt}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

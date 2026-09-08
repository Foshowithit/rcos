#!/usr/bin/env python3
"""Role C call: agnes solves ONE arm of ONE held-out task.
Usage: c_call.py <task_id> <arm> <outdir>
arm: correct | forced | disabled. Saves raw response + usage byte-identical.
Stdlib only. Key via file, never printed.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open("/home/chow/.agent-vault/keys/kenari.key").read().strip()
LANE = "kenari/agnes-2-0-flash:free"

BASE = """You are solving a file-normalization task. Work from FIRST PRINCIPLES on the task input and interface below. You have never seen any prior solution, transcript, or training task. Output ONLY one JSON object, no other text.

TASK INPUT (__FILE__):
```
__INPUT__
```

CANONICAL TARGET SCHEMA: {shipment_id: str, origin: str, destination: str, weight_kg: number>0, items: [{sku, qty}]}
__CAPBLOCK__
RESPONSE FORMAT (one JSON object only):
{"records": {<flat string records dict for the engine>}, "field_map": {<map: service,port,debug?,shipment keys + items {__list__,sku,qty} per interface convention>}, "notes": "<one line>"}
Rules: records values stay strings; engine coerces. Do not explain; output the object only."""

DISABLED = """You are solving a file-normalization task from scratch. No registry, no capability, no prior solutions exist. Output ONLY one JSON object, no other text.

TASK INPUT (__FILE__):
```
__INPUT__
```

CANONICAL TARGET SCHEMA: {shipment_id: str, origin: str, destination: str, weight_kg: number>0, items: [{sku, qty}]}
RESPONSE FORMAT (one JSON object only):
{"solver_py": "<complete python3 stdlib script reading (src_path, dst_path) and writing canonical JSON>", "notes": "<one line>"}
No explanations; output the object only."""

FORCED = """You are solving a file-normalization task. You MUST use the capability below (no alternatives exist in your registry). Apply it as best you can. Output ONLY one JSON object, no other text.

TASK INPUT (__FILE__):
```
__INPUT__
```

MANDATED CAPABILITY INTERFACE:
__CAPBLOCK__
CANONICAL TARGET SCHEMA: {shipment_id: str, origin: str, destination: str, weight_kg: number>0, items: [{sku, qty}]}
RESPONSE FORMAT (one JSON object only):
{"records": {<records dict for the mandated engine>}, "field_map": {<map per its convention>}, "notes": "<one line>"}"""


def capblock(task_id, forced=False):
    if forced:
        base = "../v0-validated-reuse/capabilities/normalize-invoice-v1"
        man = json.load(open(os.path.join(HERE, base, "manifest.json")))
        eng = open(os.path.join(HERE, base, "engine.py")).read()
        return ("MANDATED CAPABILITY (from another domain; use as best you can):\n"
                "manifest: " + json.dumps(man) + "\nENGINE SOURCE:\n```\n"
                + eng + "\n```\nIts convention: records {header: {...}, "
                "lines: [...]}, field map names header/line keys; "
                "it verifies sum(qty*unit)==total.")
    cap = "capabilities/ship-normalize-v1"
    man = json.load(open(os.path.join(HERE, cap, "manifest.json")))
    eng = open(os.path.join(HERE, cap, "engine.py")).read()
    notes = open(os.path.join(HERE, cap, "adapter_notes.md")).read()
    maps = {}
    for m in sorted(os.listdir(os.path.join(HERE, cap, "maps"))):
        maps[m] = json.load(open(os.path.join(HERE, cap, "maps", m)))
    if forced:
        return ("MANDATED CAPABILITY (from another domain; use as best you can):\n"
                "ENGINE SOURCE:\n```\n" + eng +
                "\n```\nEXAMPLE MAPS:\n" + json.dumps(maps, indent=1))
    return ("PROMOTED CAPABILITY INTERFACE (no acquisition history provided):\n"
            "manifest: " + json.dumps(man) + "\nENGINE SOURCE:\n```\n" + eng +
            "\n```\nEXAMPLE MAPS:\n" + json.dumps(maps, indent=1) +
            "\nADAPTER NOTES:\n" + notes)


def main(task_id, arm, outdir):
    inp_files = [f for f in os.listdir(os.path.join(HERE, "tasks", task_id))
                 if f.startswith("input.")]
    text = open(os.path.join(HERE, "tasks", task_id, inp_files[0])).read()
    if arm == "correct":
        prompt = BASE.replace("__FILE__", inp_files[0]).replace(
            "__INPUT__", text).replace(
            "__CAPBLOCK__", capblock(task_id))
    elif arm == "forced":
        prompt = FORCED.replace("__FILE__", inp_files[0]).replace(
            "__INPUT__", text).replace("__CAPBLOCK__", capblock(task_id, True))
    else:
        prompt = DISABLED.replace("__FILE__", inp_files[0]).replace(
            "__INPUT__", text)
    body = json.dumps({"model": "agnes-2-0-flash:free", "max_tokens": 3000,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    req = urllib.request.Request(
        "https://kenari.id/v1/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY,
                 "Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=180)
    d = json.load(r)
    wall = time.time() - t0
    usage = d.get("usage", {})
    raw = d["choices"][0]["message"]["content"]
    open(os.path.join(outdir, "raw.txt"), "w").write(raw)
    open(os.path.join(outdir, "usage.json"), "w").write(json.dumps(
        {"lane": LANE, "task": task_id, "arm": arm,
         "wall_s": round(wall, 1), "usage": usage}, indent=1))
    ident = d.get("model", "agnes-2-0-flash:free")
    open(os.path.join(outdir, "lane.json"), "w").write(json.dumps(
        {"provider": "kenari", "model_reported": ident,
         "harness": "c_call.py stdlib scheduler",
         "effort": "provider-default"}, indent=1))
    print(f"C {task_id}/{arm}: {len(raw)} chars, wall {wall:.0f}s, usage {usage}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

#!/usr/bin/env python3
"""Role B call: minimax authors the shipment-normalize capability.
Saves RAW response byte-identical + usage/cost record. No semantic edits.
Stdlib only. Key via file, never printed.
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open("/home/chow/.agent-vault/keys/router9.key").read().strip()

PROMPT = """You are authoring a reusable file-normalization capability. You see ONLY two training tasks and the acceptance contract. There are held-out tasks you will never see — design for the CLASS, not these instances.

TASK 1 (CSV), file tasks/s1-csv/input.csv:
```
__CSV__
```

TASK 2 (JSON), file tasks/s2-json/input.json:
```
__JSON__
```

ACCEPTANCE CONTRACT: output must be canonical JSON {shipment_id: str, origin: str, destination: str, weight_kg: number, items: [{sku, qty}]} matching sealed truth exactly (a mechanical checker compares; no partial credit).

DELIVERABLE: think for at most a few sentences, then output ONLY ONE json object and stop. No explanations, no markdown fences, no trailing text:
{"engine_py": "<complete python3 stdlib-only script reading (field_map_path, records_path, out_path); maps a field-map + flat string records dict to canonical JSON; validates weight_kg>0; exit 0 on verified output, 1 otherwise>",
 "map_csv": {<field map for the CSV shape above>},
 "map_json": {<field map for the JSON shape above>},
 "manifest": {"id": "ship-normalize-v1", "version": 1, "applicability": {"description": "...", "requires_markers": [...], "claims": [...]}},
 "adapter_notes": "<how a future solver turns a NEW format into flat string records for the engine>"}
Rules: engine takes pre-parsed flat string records (parsing is the solver's adapter job, not yours). Markers must be lowercase substrings likely present in future task files of this class. Be conservative: claim only what T1+T2 demonstrate.
"""

csv_text = open(os.path.join(HERE, "tasks/s1-csv/input.csv")).read()
jsn_text = open(os.path.join(HERE, "tasks/s2-json/input.json")).read()
prompt = PROMPT.replace("__CSV__", csv_text).replace("__JSON__", jsn_text)
body = json.dumps({"model": "minimax-m3", "max_tokens": 20000,
                   "messages": [{"role": "user", "content": prompt}]}).encode()
t0 = time.time()
req = urllib.request.Request(
    "https://api.router9.com/v1/chat/completions", data=body,
    headers={"Authorization": "Bearer " + KEY,
             "Content-Type": "application/json"})
r = urllib.request.urlopen(req, timeout=300)
d = json.load(r)
wall = time.time() - t0
usage = d.get("usage", {})
raw = d["choices"][0]["message"]["content"]
os.makedirs(os.path.join(HERE, "runs/b-builder"), exist_ok=True)
open(os.path.join(HERE, "runs/b-builder/raw_response.txt"), "w").write(raw)
open(os.path.join(HERE, "runs/b-builder/usage.json"), "w").write(json.dumps(
    {"lane": "router9/minimax-m3", "wall_s": round(wall, 1),
     "usage": usage}, indent=1))
print(f"B done: {len(raw)} chars, wall {wall:.0f}s, usage {usage}")

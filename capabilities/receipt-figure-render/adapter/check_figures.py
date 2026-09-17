#!/usr/bin/env python3
"""Second-code-path checker for receipt figures: recompute the numbers straight
from the registry and diff against the figure's values.json sidecar.

Catches: hand-drawn figures, stale renders after the registry moved, and
mis-transcribed counts. Exit 0 = match; 3 = mismatch (name the field).
"""
import json
import sys

registry_path, values_path = sys.argv[1], sys.argv[2]
reg = json.load(open(registry_path))
vals = json.load(open(values_path))

VERDICTS = ["ship", "fix", "blocked"]
dist = {v: 0 for v in VERDICTS}
per_cap = {}
for c in reg["capabilities"]:
    counts = {v: 0 for v in VERDICTS}
    for e in c.get("evals", []):
        counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1
        dist[e["verdict"]] = dist.get(e["verdict"], 0) + 1
    per_cap[c["id"]] = counts

fail = []
if vals["n_capabilities"] != len(reg["capabilities"]):
    fail.append(f"n_capabilities {vals['n_capabilities']} != {len(reg['capabilities'])}")
if vals["n_evals"] != sum(dist.values()):
    fail.append(f"n_evals {vals['n_evals']} != {sum(dist.values())}")
if vals["verdict_distribution"] != dist:
    fail.append(f"verdict_distribution {vals['verdict_distribution']} != {dist}")
if vals["per_capability"] != per_cap:
    diffed = {k: (vals["per_capability"].get(k), per_cap.get(k))
              for k in set(vals["per_capability"]) | set(per_cap)
              if vals["per_capability"].get(k) != per_cap.get(k)}
    fail.append(f"per_capability differs: {diffed}")

if fail:
    for f in fail:
        print("FAIL " + f)
    sys.exit(3)
print(f"FIGURE_CHECK_PASS n={sum(dist.values())} evals / {len(reg['capabilities'])} caps, "
      f"sidecar matches fresh registry recompute")

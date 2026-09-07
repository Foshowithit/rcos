#!/usr/bin/env python3
"""Arm-1 env reader (composed adapter). KEY=VALUE + # comments + junk lines
-> flat string map for the engine. Task-specific glue, logged as composed."""
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
rec = {}
for line in open(src):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    rec[k.strip()] = v.strip()
json.dump(rec, open(dst, "w"), indent=1)
print(f"env adapter: {dst}")

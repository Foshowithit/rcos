#!/usr/bin/env python3
"""Arm-3 fresh solve (registry disabled; input.env + schema brief only)."""
import json
import sys

BOOLS = {"true": True, "yes": True, "1": True, "on": True,
         "false": False, "no": False, "0": False, "off": False}

src, dst = sys.argv[1], sys.argv[2]
rec = {}
for line in open(src):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    rec[k.strip()] = v.strip()
out = {
    "service": rec["SVC_NAME"],
    "port": int(rec["PORT"]),
    "debug": BOOLS[rec["DEBUG"].lower()],
    "retries": int(rec.get("RETRY_COUNT", 3)),
    "allowed_hosts": [h.strip() for h in rec.get("HOSTS", "").split(",")
                      if h.strip()],
}
assert 1 <= out["port"] <= 65535 and out["retries"] >= 0
json.dump(out, open(dst, "w"), indent=1)
print(f"Arm-3 solved: {dst}")

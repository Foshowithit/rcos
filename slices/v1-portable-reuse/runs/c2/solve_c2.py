#!/usr/bin/env python3
"""T2 solver (role B, fresh session: saw ONLY tasks/c2-json/input.json + brief)."""
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
doc = json.load(open(src))
out = {
    "service": doc["svc"],
    "port": int(doc["network"]["port"]),
    "debug": bool(doc["debug"]),
    "retries": int(doc.get("retries", 3)),
    "allowed_hosts": list(doc["network"].get("allow", [])),
}
assert 1 <= out["port"] <= 65535 and out["retries"] >= 0
json.dump(out, open(dst, "w"), indent=1)
print(f"T2 solved: {dst}")

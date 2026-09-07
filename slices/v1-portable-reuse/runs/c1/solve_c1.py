#!/usr/bin/env python3
"""T1 solver (role B, fresh session: saw ONLY tasks/c1-ini/input.ini + brief)."""
import configparser
import json
import sys

BOOLS = {"true": True, "yes": True, "1": True, "on": True,
         "false": False, "no": False, "0": False, "off": False}


def b(v):
    return BOOLS[v.strip().lower()]


src, dst = sys.argv[1], sys.argv[2]
cp = configparser.ConfigParser()
cp.read(src)
out = {
    "service": cp["service"]["name"],
    "port": int(cp["service"]["port"]),
    "debug": b(cp["service"]["debug"]),
    "retries": int(cp["limits"]["retries"]),
    "allowed_hosts": [h.strip() for h in cp["limits"]["hosts"].split(",")],
}
assert 1 <= out["port"] <= 65535 and out["retries"] >= 0
json.dump(out, open(dst, "w"), indent=1)
print(f"T1 solved: {dst}")

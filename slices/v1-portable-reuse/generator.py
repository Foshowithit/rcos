#!/usr/bin/env python3
"""Slice-1 generator: deterministic service-config fixtures.
Usage: python3 generator.py  (writes tasks/<id>/input.* + prints sha256)
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def gen():
    made = []
    made.append(w(f"{TASKS}/c1-ini/input.ini",
                  "[service]\nname = ledger-api\nport = 8080\n"
                  "debug = yes\n\n[limits]\nretries = 5\n"
                  "hosts = api.internal, db.internal\n"))
    made.append(w(f"{TASKS}/c2-json/input.json", json.dumps({
        "svc": "ledger-api", "network": {"port": 8080, "allow": ["api.internal"]},
        "debug": True, "notes": "primary region", "tags": ["prod"],
    }, indent=1) + "\n"))
    made.append(w(f"{TASKS}/c3-env/input.env",
                  "# deployed by ops, do not reorder\n"
                  "SVC_NAME=ledger-api\nPORT=8080\nJUNK=1\n"
                  "DEBUG=on\n# retries intentionally absent (default 3)\n"
                  "HOSTS=api.internal,db.internal\nEXTRA=zzz\n"))
    for p in made:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print(f"{h}  {os.path.relpath(p, HERE)}")


if __name__ == "__main__":
    gen()

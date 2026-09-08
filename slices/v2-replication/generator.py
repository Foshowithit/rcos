#!/usr/bin/env python3
"""Slice-2 generator: deterministic log fixtures from fixed seeds.
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
    made.append(w(f"{TASKS}/l1-app/app.log",
                  "2026-09-01T10:00:01 INFO ledger-api started workers=4\n"
                  "2026-09-01T10:04:11 WARN ledger-api slow query 812ms\n"
                  "2026-09-01T10:04:12 WARN ledger-api slow query 901ms\n"
                  "2026-09-01T10:07:33 ERROR ledger-api timeout upstream=auth\n"
                  "2026-09-01T10:09:00 INFO ledger-api recovered\n"))
    made.append(w(f"{TASKS}/l2-jsonl/events.jsonl", "\n".join([
        json.dumps({"ts": "2026-09-02T11:00:00", "lvl": "info",
                    "svc": "ledger-api", "msg": "started"}),
        json.dumps({"ts": "2026-09-02T11:02:00", "svc": "ledger-api",
                    "msg": "heartbeat", "beat": 1}),
        json.dumps({"ts": "2026-09-02T11:05:00", "lvl": "error",
                    "svc": "ledger-api", "msg": "timeout upstream=db",
                    "ctx": {"retry": 2}}),
        json.dumps({"ts": "2026-09-02T11:06:00", "lvl": "warn",
                    "svc": "ledger-api", "msg": "slow query 700ms"}),
    ]) + "\n"))
    made.append(w(f"{TASKS}/l3-syslog/syslog.txt",
                  "Sep  5 12:00:01 web-1 ledger-api[101]: INFO: started\n"
                  "Sep  5 12:01:00 web-1 kernel: [123] cpu throttle\n"
                  "Sep  5 12:03:00 web-1 ledger-api[101]: ERROR: timeout upstream=cache\n"
                  "Sep  5 12:03:01 web-1 ledger-api[101]: ERROR: timeout upstream=cache\n"
                  "Sep  5 12:05:00 web-1 ledger-api[101]: FATAL: out of workers\n"))
    for p in made:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print(f"{h}  {os.path.relpath(p, HERE)}")


if __name__ == "__main__":
    gen()

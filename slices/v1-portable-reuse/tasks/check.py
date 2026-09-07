#!/usr/bin/env python3
"""Slice-1 checker: canonical service-config JSON vs frozen truth.
Usage: python3 tasks/check.py <task_id> <candidate_json>
exit 0 = ship, 1 = fix, 2 = blocked. Stdlib only.
"""
import json
import sys

TRUTH = {
    "c1-ini": {"service": "ledger-api", "port": 8080, "debug": True,
               "retries": 5, "allowed_hosts": ["api.internal", "db.internal"]},
    "c2-json": {"service": "ledger-api", "port": 8080, "debug": True,
                "retries": 3, "allowed_hosts": ["api.internal"]},
    "c3-env": {"service": "ledger-api", "port": 8080, "debug": True,
               "retries": 3, "allowed_hosts": ["api.internal", "db.internal"]},
}


def main(task_id, path):
    try:
        t = TRUTH[task_id]
    except KeyError:
        print(f"unknown task {task_id}");
        return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}");
        return 2
    errs = [f"{k}: got {got.get(k)!r} want {v!r}"
            for k, v in t.items() if got.get(k) != v]
    extra = set(got) - set(t)
    if extra:
        errs.append(f"unexpected keys: {sorted(extra)}")
    if errs:
        print(f"FIX ({task_id}): " + "; ".join(errs));
        return 1
    print(f"SHIP {task_id}: canonical config exact");
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

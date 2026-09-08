#!/usr/bin/env python3
"""Slice-2 checker: canonical incident JSON vs frozen truth.
Usage: python3 tasks/check.py <task_id> <candidate_json>
exit 0 = ship, 1 = fix, 2 = blocked. Stdlib only.
Junk rule (frozen): heartbeat lines and non-target-service lines
(e.g. kernel) are EXCLUDED from events/signatures.
"""
import json
import sys

TRUTH = {
    "l1-app": {"service": "ledger-api", "severity": "ERROR",
               "first_seen": "2026-09-01T10:00:01",
               "last_seen": "2026-09-01T10:09:00", "event_count": 5,
               "signatures": ["recovered", "slow query #ms",
                              "started workers=#", "timeout upstream=#"]},
    "l2-jsonl": {"service": "ledger-api", "severity": "ERROR",
                 "first_seen": "2026-09-02T11:00:00",
                 "last_seen": "2026-09-02T11:06:00", "event_count": 3,
                 "signatures": ["slow query #ms", "started",
                                "timeout upstream=#"]},
    "l3-syslog": {"service": "ledger-api", "severity": "FATAL",
                  "first_seen": "2026-09-05T12:00:01",
                  "last_seen": "2026-09-05T12:05:00", "event_count": 4,
                  "signatures": ["out of workers", "started",
                                 "timeout upstream=#"]},
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
    errs = []
    for k in ("service", "severity", "first_seen", "last_seen",
              "event_count"):
        if got.get(k) != t[k]:
            errs.append(f"{k}: got {got.get(k)!r} want {t[k]!r}")
    if sorted(got.get("signatures", [])) != sorted(t["signatures"]):
        errs.append(f"signatures: got {got.get('signatures')!r} want {t['signatures']!r}")
    if "incident_id" not in got:
        errs.append("missing incident_id")
    if errs:
        print(f"FIX ({task_id}): " + "; ".join(errs));
        return 1
    print(f"SHIP {task_id}: canonical incident exact");
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

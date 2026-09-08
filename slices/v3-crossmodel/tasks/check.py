#!/usr/bin/env python3
"""Slice-3 checker: canonical shipment JSON vs sealed truth.json.
Usage: python3 tasks/check.py <task_id> <candidate_json>
exit 0 = ship, 1 = fix, 2 = blocked. Stdlib only.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(task_id, path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    try:
        t = truth[task_id]
    except KeyError:
        print(f"unknown task {task_id}");
        return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}");
        return 2
    errs = []
    for k in ("shipment_id", "origin", "destination", "weight_kg"):
        if got.get(k) != t[k]:
            errs.append(f"{k}: got {got.get(k)!r} want {t[k]!r}")
    want = sorted((i["sku"], i["qty"]) for i in t["items"])
    goti = got.get("items")
    if (not isinstance(goti, list) or
            sorted((i.get("sku"), i.get("qty")) for i in goti) != want):
        errs.append(f"items mismatch: got {goti!r} want {want!r}")
    if errs:
        print(f"FIX ({task_id}): " + "; ".join(errs));
        return 1
    print(f"SHIP {task_id}: canonical shipment exact");
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

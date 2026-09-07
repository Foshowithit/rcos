#!/usr/bin/env python3
"""Slice-0 checker: validates a canonical invoice JSON against frozen truth.
Usage: python3 tasks/check.py <task_id> <candidate_json>
exit 0 = ship, 1 = fix, 2 = blocked. No network, no LLM, stdlib only.
"""
import json
import sys

TRUTH = {
    "t1-csv": {"invoice_id": "INV-1042", "date": "2026-08-14",
               "total_cents": 14250, "currency": "USD",
               "lines": [["SKU-101", 2, 5000], ["SKU-207", 1, 4250]]},
    "t2-json": {"invoice_id": "INV-2091", "date": "2026-09-02",
                "total_cents": 8999, "currency": "USD",
                "lines": [["SKU-330", 3, 2000], ["SKU-101", 1, 2999]]},
    "t3-tsv": {"invoice_id": "INV-3110", "date": "2026-09-05",
               "total_cents": 21000, "currency": "USD",
               "lines": [["SKU-410", 5, 3000], ["SKU-207", 2, 3000]]},
}


def main(task_id, path):
    try:
        t = TRUTH[task_id]
    except KeyError:
        print(f"unknown task {task_id}");
        return 2
    try:
        with open(path) as f:
            got = json.load(f)
    except Exception as e:
        print(f"unreadable output: {e}");
        return 2
    errs = []
    for k in ("invoice_id", "date", "total_cents", "currency"):
        if got.get(k) != t[k]:
            errs.append(f"{k}: got {got.get(k)!r} want {t[k]!r}")
    items = got.get("line_items")
    if not isinstance(items, list) or len(items) != len(t["lines"]):
        errs.append(f"line_items: got {items!r}")
    else:
        for g, (s, q, u) in zip(items, t["lines"]):
            if not (g.get("sku") == s and g.get("qty") == q
                    and g.get("unit_cents") == u):
                errs.append(f"line mismatch: got {g!r} want {(s, q, u)}")
    if not errs and isinstance(items, list):
        calc = sum(g["qty"] * g["unit_cents"] for g in items)
        if calc != got.get("total_cents"):
            errs.append(f"totals do not verify: {calc} != {got.get('total_cents')}")
    if errs:
        print(f"FIX t3-check-fail ({task_id}): " + "; ".join(errs));
        return 1
    print(f"SHIP {task_id}: canonical output exact, totals verify");
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

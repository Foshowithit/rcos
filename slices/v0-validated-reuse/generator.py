#!/usr/bin/env python3
"""Slice-0 task generator: deterministic invoice fixtures from seeds.

Family = invoice record normalization. Structural dimensions vary by task:
format, field naming, field ordering, missing optionals, junk fields.
Usage: python3 generator.py  (writes tasks/<id>/input.* + prints sha256)
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")

# Ground truth (strings; cents as int). Same economic facts, three shapes.
TRUTH = {
    "t1-csv": {"invoice_id": "INV-1042", "date": "2026-08-14",
               "total_cents": 14250, "currency": "USD",
               "lines": [("SKU-101", 2, 5000), ("SKU-207", 1, 4250)]},
    "t2-json": {"invoice_id": "INV-2091", "date": "2026-09-02",
                "total_cents": 8999, "currency": "USD",
                "lines": [("SKU-330", 3, 2000), ("SKU-101", 1, 2999)]},
    "t3-tsv": {"invoice_id": "INV-3110", "date": "2026-09-05",
               "total_cents": 21000, "currency": "USD",
               "lines": [("SKU-410", 5, 3000), ("SKU-207", 2, 3000)]},
}


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def gen():
    made = []
    t = TRUTH["t1-csv"]
    lines = "\n".join(f"{s},{q},{u / 100:.2f}" for s, q, u in t["lines"])
    made.append(w(f"{TASKS}/t1-csv/input.csv",
                  f"inv_id,inv_date,total_usd,currency\n"
                  f"{t['invoice_id']},{t['date']},{t['total_cents'] / 100:.2f},{t['currency']}\n"
                  f"\nsku,qty,unit_usd\n{lines}\n"))
    t = TRUTH["t2-json"]
    made.append(w(f"{TASKS}/t2-json/input.json", json.dumps({
        "id": t["invoice_id"], "issued": t["date"],
        "lines": [{"code": s, "n": q, "price_cents": u} for s, q, u in t["lines"]],
        "notes": "rush delivery requested", "priority": 2,
    }, indent=1) + "\n"))
    t = TRUTH["t3-tsv"]
    items = ",".join(f"{s}|{q}|{u}" for s, q, u in t["lines"])
    made.append(w(f"{TASKS}/t3-tsv/input.tsv",
                  f"INVOICE\tDAY\tJUNK1\tAMOUNT_CENTS\tCCY\tITEMS\tJUNK2\n"
                  f"{t['invoice_id']}\t{t['date']}\tzzz\t{t['total_cents']}\t"
                  f"{t['currency']}\t{items}\tqqq\n"))
    for p in made:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print(f"{h}  {os.path.relpath(p, HERE)}")


if __name__ == "__main__":
    gen()

#!/usr/bin/env python3
"""T3-CONTROL fresh solve (registry disabled; wrote WITHOUT reading the
capability dir — only input.tsv + the canonical-schema brief).
ORDER DEVIATION (see RESULTS.md): treatment ran first; same author throughout.
Grading is fully mechanical, which bounds but does not erase the bias."""
import csv
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, newline="") as f:
    rows = list(csv.reader(f, delimiter="\t"))
h = dict(zip(rows[0], rows[1]))
items = [{"sku": s, "qty": int(q), "unit_cents": int(u)}
         for s, q, u in (g.split("|") for g in h["ITEMS"].split(","))]
out = {"invoice_id": h["INVOICE"], "date": h["DAY"],
       "total_cents": int(h["AMOUNT_CENTS"]), "currency": h["CCY"],
       "line_items": items}
assert sum(i["qty"] * i["unit_cents"] for i in items) == out["total_cents"]
json.dump(out, open(dst, "w"), indent=1)
print(f"T3-control solved: {dst}")

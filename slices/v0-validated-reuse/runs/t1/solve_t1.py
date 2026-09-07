#!/usr/bin/env python3
"""T1 solver attempt (fresh session: saw ONLY tasks/t1-csv/input.csv + brief).
Writes canonical invoice JSON to argv[1]."""
import csv
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, newline="") as f:
    rows = list(csv.reader(f))
header, body = rows[0], rows[1:]
blank = body.index([])
h = dict(zip(header, body[0]))
items = [dict(zip(body[blank + 1], r)) for r in body[blank + 2:]]
out = {
    "invoice_id": h["inv_id"],
    "date": h["inv_date"],
    "total_cents": int(round(float(h["total_usd"]) * 100)),
    "currency": h["currency"],
    "line_items": [{"sku": r["sku"], "qty": int(r["qty"]),
                    "unit_cents": int(round(float(r["unit_usd"]) * 100))}
                   for r in items],
}
calc = sum(i["qty"] * i["unit_cents"] for i in out["line_items"])
assert calc == out["total_cents"], f"totals do not verify: {calc}"
with open(dst, "w") as f:
    json.dump(out, f, indent=1)
print(f"T1 solved: {dst}")

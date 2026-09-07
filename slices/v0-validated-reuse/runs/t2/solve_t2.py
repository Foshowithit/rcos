#!/usr/bin/env python3
"""T2 solver attempt (fresh session: saw ONLY tasks/t2-json/input.json + brief).
Writes canonical invoice JSON to argv[1]."""
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    doc = json.load(f)
out = {
    "invoice_id": doc["id"],
    "date": doc["issued"],
    "total_cents": sum(l["n"] * l["price_cents"] for l in doc["lines"]),
    "currency": doc.get("cur", "USD"),
    "line_items": [{"sku": l["code"], "qty": l["n"],
                    "unit_cents": l["price_cents"]} for l in doc["lines"]],
}
with open(dst, "w") as f:
    json.dump(out, f, indent=1)
print(f"T2 solved: {dst}")

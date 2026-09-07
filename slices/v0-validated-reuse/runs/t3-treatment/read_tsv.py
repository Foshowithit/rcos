#!/usr/bin/env python3
"""T3-treatment TSV reader (composed adapter, logged as composed work).
Reads input.tsv -> records.json {header, lines}. Task-specific glue;
the reusable engine does mapping + verification."""
import csv
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, newline="") as f:
    rows = list(csv.reader(f, delimiter="\t"))
hdr = dict(zip(rows[0], rows[1]))
items = []
for grp in hdr["ITEMS"].split(","):
    sku, qty, unit = grp.split("|")
    items.append({"sku": sku, "qty": int(qty), "unit_cents": int(unit)})
rec = {"header": {"INVOICE": hdr["INVOICE"], "DAY": hdr["DAY"],
                  "AMOUNT_CENTS": int(hdr["AMOUNT_CENTS"]), "CCY": hdr["CCY"]},
       "lines": items}
json.dump(rec, open(dst, "w"), indent=1)
print(f"TSV adapter: {dst}")

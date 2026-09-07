#!/usr/bin/env python3
"""normalize-invoice-v1 engine: canonical mapping + validation + totals verify.
Usage: engine.py <field-map.json> <records.json> <out.json>
field-map: {"invoice_id": <key>, "date": <key>, "total_cents": <key|derived>,
  "currency": <key|const>, "lines": <key>, "line": {"sku","qty","unit_cents"}}.
records.json: {"header": {...}, "lines": [...]} as produced by a format reader.
Stdlib only. Returns 0 on verified output, 1 on totals mismatch.
"""
import json
import sys


def main(map_path, rec_path, out_path):
    fmap = json.load(open(map_path))
    rec = json.load(open(rec_path))
    h, lines = rec["header"], rec["lines"]
    lm = fmap["line"]

    def tot(lines):
        t = fmap["total_cents"]
        if isinstance(t, dict) and "const" in t:
            return int(t["const"])
        if isinstance(t, dict) and t.get("sum_lines"):
            return sum(int(l[lm["qty"]]) * int(l[lm["unit_cents"]])
                       for l in lines)
        return int(h[t])

    def cur():
        c = fmap["currency"]
        if isinstance(c, dict) and "const" in c:
            return str(c["const"])
        return str(h[c] if c in h else c)

    out = {
        "invoice_id": str(h[fmap["invoice_id"]]),
        "date": str(h[fmap["date"]]),
        "total_cents": tot(lines),
        "currency": cur(),
        "line_items": [{"sku": str(l[lm["sku"]]), "qty": int(l[lm["qty"]]),
                        "unit_cents": int(l[lm["unit_cents"]])} for l in lines],
    }
    calc = sum(i["qty"] * i["unit_cents"] for i in out["line_items"])
    if calc != out["total_cents"]:
        print(f"engine: totals do not verify ({calc} != {out['total_cents']})")
        return 1
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"engine: verified {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

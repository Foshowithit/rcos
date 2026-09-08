#!/usr/bin/env python3
"""ship-normalize-v2 engine (role B, session lane; authored from s1/s2 only,
held-outs sealed). Canonical mapping + coercion + validation over flat
string records. Stdlib only. Exit 0 verified, 1 otherwise."""
import json
import sys


def main(map_path, rec_path, out_path):
    fmap = json.load(open(map_path))
    rec = json.load(open(rec_path))
    try:
        items = []
        for e in rec[fmap["items_key"]]:
            items.append({"sku": str(e[fmap["item_sku"]]),
                          "qty": int(e[fmap["item_qty"]])})
        out = {
            "shipment_id": str(rec[fmap["shipment_id"]]),
            "origin": str(rec[fmap["origin"]]),
            "destination": str(rec[fmap["destination"]]),
            "weight_kg": float(rec[fmap["weight_kg"]]),
            "items": items,
        }
    except (KeyError, ValueError, TypeError) as exc:
        print(f"engine: malformed records ({exc})")
        return 1
    if not out["weight_kg"] > 0:
        print("engine: weight_kg not positive")
        return 1
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"engine: verified {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

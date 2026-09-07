#!/usr/bin/env python3
"""normalize-config-v1 engine: canonical mapping + coercion + defaults +
validation over a parsed config representation.
Usage: engine.py <field-map.json> <records.json> <out.json>
field-map: {"service","port","debug","retries","hosts",
  "retries_default", "hosts_default"}. records: flat string map.
Stdlib only. Returns 0 on verified output, 1 on validation failure.
"""
import json
import sys

BOOLS = {"true": True, "yes": True, "1": True, "on": True,
         "false": False, "no": False, "0": False, "off": False}


def main(map_path, rec_path, out_path):
    fmap = json.load(open(map_path))
    rec = json.load(open(rec_path))

    def coerce_bool(v):
        if isinstance(v, bool):
            return v
        return BOOLS[str(v).strip().lower()]

    out = {
        "service": str(rec[fmap["service"]]),
        "port": int(rec[fmap["port"]]),
        "debug": coerce_bool(rec[fmap["debug"]]),
        "retries": int(rec.get(fmap["retries"], fmap.get("retries_default", 3))),
        "allowed_hosts": [h.strip() for h in
                          str(rec.get(fmap["hosts"], "")).split(",")
                          if h.strip()] or list(fmap.get("hosts_default", [])),
    }
    if not 1 <= out["port"] <= 65535:
        print(f"engine: bad port {out['port']}");
        return 1
    if out["retries"] < 0:
        print(f"engine: bad retries {out['retries']}");
        return 1
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"engine: verified {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

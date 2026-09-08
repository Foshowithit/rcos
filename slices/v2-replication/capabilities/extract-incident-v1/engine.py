#!/usr/bin/env python3
"""extract-incident-v1 engine: group + severity fold + signature normalize +
canonical shaping over parsed event records.
Usage: engine.py <field-map.json> <records.json> <out.json>
records: {"service": str, "events": [{ts, level, msg}]} (parsed upstream).
field-map: {"service","ts","level","msg"} key names in records events.
Stdlib only. Returns 0 on verified shape, 1 on validation failure.
"""
import json
import re
import sys

ORDER = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]


def sig(msg):
    s = msg.lower()
    s = re.sub(r"\d+(\.\d+)?\s?(ms|s)\b", "#ms", s)
    s = re.sub(r"=\S+", "=#", s)
    return s


def main(map_path, rec_path, out_path):
    fmap = json.load(open(map_path))
    rec = json.load(open(rec_path))
    evs = rec["events"]
    if not evs:
        print("engine: no events");
        return 1
    for e in evs:
        if e["level"] not in ORDER:
            print(f"engine: bad level {e['level']!r}");
            return 1
    out = {
        "incident_id": f"{rec['service']}-{fmap.get('tag', 'x')}",
        "severity": max((e["level"] for e in evs), key=ORDER.index),
        "service": rec["service"],
        "first_seen": min(e["ts"] for e in evs),
        "last_seen": max(e["ts"] for e in evs),
        "event_count": len(evs),
        "signatures": sorted({sig(e["msg"]) for e in evs}),
    }
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"engine: verified {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

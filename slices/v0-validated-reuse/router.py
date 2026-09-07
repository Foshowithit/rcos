#!/usr/bin/env python3
"""Slice-0 router: score registry capabilities by marker overlap on task bytes.
Logs considered/selected/rejected with reasons. Stdlib only.
Usage: router.py <registry.json> <task_input_file>  -> prints JSON decision.
"""
import json
import sys


def main(reg_path, task_path):
    reg = json.load(open(reg_path))
    blob = open(task_path, "rb").read().decode("utf-8", "replace").lower()
    considered = []
    for cap in reg["capabilities"]:
        man = json.load(open(cap["path"] + "/manifest.json"))
        markers = man["applicability"]["requires_markers"]
        hits = [m for m in markers if m in blob]
        considered.append({"id": man["id"], "version": man["version"],
                           "hits": hits, "of": len(markers),
                           "claims": man["applicability"]["claims"]})
    ranked = sorted(considered, key=lambda c: (-len(c["hits"]), c["id"]))
    best = ranked[0]
    rejected = [{"id": c["id"], "reason":
                 f"fewer marker hits ({len(c['hits'])}/{c['of']}) than "
                 f"{best['id']} ({len(best['hits'])}/{best['of']}); "
                 f"claims {c['claims']} do not cover totals verification"}
                for c in ranked[1:]]
    print(json.dumps({"considered": [c["id"] for c in ranked],
                      "selected": best["id"], "version": best["version"],
                      "select_reason":
                          f"{len(best['hits'])}/{best['of']} markers hit: "
                          f"{best['hits']}",
                      "rejected": rejected}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

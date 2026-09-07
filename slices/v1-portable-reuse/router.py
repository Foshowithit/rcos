#!/usr/bin/env python3
"""Slice-1 router: marker-overlap retrieval with forced-selection support.
Usage: router.py <registry.json> <task_input> [--force <capability_id>]
Forced selections are logged forced:true (null-test arm). Stdlib only.
"""
import json
import sys


def main(reg_path, task_path, forced=None):
    reg = json.load(open(reg_path))
    blob = open(task_path, "rb").read().decode("utf-8", "replace").lower()
    scored = []
    for cap in reg["capabilities"]:
        man = json.load(open(cap["path"] + "/manifest.json"))
        markers = man["applicability"]["requires_markers"]
        hits = [m for m in markers if m in blob]
        scored.append({"id": man["id"], "version": man["version"],
                       "hits": hits, "of": len(markers),
                       "claims": man["applicability"]["claims"]})
    ranked = sorted(scored, key=lambda c: (-len(c["hits"]), c["id"]))
    if forced:
        sel = next(c for c in ranked if c["id"] == forced)
        rej = [{"id": c["id"], "reason": "forced-selection arm: bypassed"} 
               for c in ranked if c["id"] != forced]
        out = {"considered": [c["id"] for c in ranked],
               "selected": sel["id"], "forced": True,
               "rejected": rej}
    else:
        best = ranked[0]
        out = {"considered": [c["id"] for c in ranked],
               "selected": best["id"], "version": best["version"],
               "forced": False,
               "select_reason": f"{len(best['hits'])}/{best['of']}: {best['hits']}",
               "rejected": [{"id": c["id"], "reason":
                             f"{len(c['hits'])}/{c['of']} hits; claims {c['claims']} exclude config validation"}
                            for c in ranked[1:]]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    forced = None
    if "--force" in sys.argv:
        forced = sys.argv[sys.argv.index("--force") + 1]
    main(sys.argv[1], sys.argv[2], forced)

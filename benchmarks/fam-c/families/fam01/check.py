#!/usr/bin/env python3
"""fam01 checker: canonical records vs sealed truth.
Usage: check.py <T0..T4> <json>. exit 0=SHIP 1=fix 2=blocked.
Rejection of K is a run-trace property (reuse_rejected), never an
output shape: every task emits the plain record list."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def main(task, path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    if task not in truth:
        print(f"unknown task {task}"); return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}"); return 2
    want = truth[task]
    if (isinstance(got, list) and len(got) == len(want) and all(
            g.get("id") == w["id"] and g.get("name") == w["name"]
            and g.get("amount_cents") == w["amount_cents"]
            and sorted(g.get("tags", [])) == sorted(w["tags"])
            for g, w in zip(got, want))):
        print(f"SHIP {task}: canonical records exact"); return 0
    print(f"FIX ({task}): got {got!r} want {want!r}"); return 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

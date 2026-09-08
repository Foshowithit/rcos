#!/usr/bin/env python3
"""fam01 checker: canonical record list vs sealed truth.json.
Usage: check.py <T0..T4> <candidate_json>. exit 0=SHIP 1=fix 2=blocked."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(task, path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    if task not in truth:
        print(f"unknown task {task}")
        return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}")
        return 2
    want = truth[task]
    if not isinstance(got, list) or len(got) != len(want):
        print(f"FIX ({task}): got {got!r} want {len(want)} records")
        return 1
    for g, w in zip(got, want):
        if (g.get("id") != w["id"] or g.get("name") != w["name"]
                or g.get("amount_cents") != w["amount_cents"]
                or sorted(g.get("tags", [])) != sorted(w["tags"])):
            print(f"FIX ({task}): got {g!r} want {w!r}")
            return 1
    print(f"SHIP {task}: canonical records exact")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

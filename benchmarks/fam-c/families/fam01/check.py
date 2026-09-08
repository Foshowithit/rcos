#!/usr/bin/env python3
"""fam01 checker: canonical records vs sealed truth; T4 abstention contract.
Usage: check.py <T0..T4> <json>. exit 0=SHIP 1=fix 2=blocked.
T0-T3: exact record list. T4: abstained==true + nonempty reason + exact answer."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def records_equal(got, want):
    if not isinstance(got, list) or len(got) != len(want):
        return False
    return all(g.get("id") == w["id"] and g.get("name") == w["name"]
               and g.get("amount_cents") == w["amount_cents"]
               and sorted(g.get("tags", [])) == sorted(w["tags"])
               for g, w in zip(got, want))
def main(task, path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    if task not in truth:
        print(f"unknown task {task}"); return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}"); return 2
    if task == "T4":
        w = truth["T4"]
        if (isinstance(got, dict) and got.get("abstained") is True
                and isinstance(got.get("reason"), str) and got["reason"].strip()
                and records_equal(got.get("answer"), w["answer"])):
            print("SHIP T4: abstention recorded, independent answer exact")
            return 0
        print(f"FIX (T4): want abstained=true + nonempty reason + exact answer, got {got!r}")
        return 1
    if records_equal(got, truth[task]):
        print(f"SHIP {task}: canonical records exact"); return 0
    print(f"FIX ({task}): got {got!r} want {truth[task]!r}"); return 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

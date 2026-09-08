#!/usr/bin/env python3
"""fam03 checker: dedup counts vs sealed truth; T4 abstention contract.
Usage: check.py <T> <json>. exit 0=SHIP 1=fix 2=blocked."""
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
    if task == "T4":
        w = truth["T4"]
        if (isinstance(got, dict) and got.get("abstained") is True
                and isinstance(got.get("reason"), str) and got["reason"].strip()
                and all(got.get("answer", {}).get(k) == v for k, v in w["answer"].items())):
            print("SHIP T4: abstention recorded, independent answer exact")
            return 0
        print(f"FIX (T4): want abstained=true + reason + exact answer, got {got!r}")
        return 1
    want = truth[task]
    if all(got.get(k) == v for k, v in want.items()):
        print(f"SHIP {task}: dedup counts exact"); return 0
    print(f"FIX ({task}): got {got!r} want {want!r}"); return 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

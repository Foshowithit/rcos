#!/usr/bin/env python3
"""fam03 checker: counts vs sealed truth. Usage: check.py <T> <json>.
exit 0=SHIP 1=fix 2=blocked. Rejection of K is a run-trace property,
never an output shape: every task emits plain counts."""
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
    if all(got.get(k) == v for k, v in want.items()):
        print(f"SHIP {task}: counts exact"); return 0
    print(f"FIX ({task}): got {got!r} want {want!r}"); return 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

#!/usr/bin/env python3
"""fam02 checker: merged map vs truth + retry-log evidence.
Usage: check.py <T0..T4> <merged_json> <retry_log>.
exit 0=SHIP 1=fix 2=blocked. Asserts: exact merged map; every task page
visited; T1 shows a failed attempt then success (recovery happened).
T4 asserts latest-value-wins (b=22), which blind dedup-by-first-seen fails.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = {"T0": ["p1.json", "p2.json"], "T1": ["q1.json", "q2.json", "q3.json"],
         "T2": ["r1.json", "r2.json"], "T3": ["s1.json", "s2.json"],
         "T4": ["t1.json", "t2.json"]}


def main(task, merged_path, log_path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    if task not in truth:
        print(f"unknown task {task}")
        return 2
    try:
        got = json.load(open(merged_path))
    except Exception as e:
        print(f"unreadable output: {e}")
        return 2
    if got != truth[task]:
        print(f"FIX ({task}): got {got!r} want {truth[task]!r}")
        return 1
    try:
        log = open(log_path).read().splitlines()
    except OSError:
        print(f"FIX ({task}): missing retry.log")
        return 1
    seen = {ln.split()[0] for ln in log if ln.split()}
    for pg in PAGES[task]:
        if pg not in seen:
            print(f"FIX ({task}): page {pg} never attempted")
            return 1
    if task == "T1" and not any(ln.split()[0] == "q2.json" and ln.split()[2] == "fail" for ln in log if len(ln.split()) == 3):
        print(f"FIX ({task}): no failed q2.json attempt logged; recovery unproven")
        return 1
    print(f"SHIP {task}: merged map exact, all pages visited")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))

#!/usr/bin/env python3
"""fam05 checker: verification report vs sealed truth.
Usage: check.py <T> <json>. exit 0=SHIP 1=fix 2=blocked. Reports carry
ok/bad plus an unverified list (empty except T4). Rejection of K is a
run-trace property, never an output shape."""
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
    if sorted(got.get("ok", [])) != sorted(want["ok"]):
        print(f"FIX ({task}): ok={got.get('ok')!r} want {want['ok']!r}"); return 1
    gb, wb = got.get("bad", []), want["bad"]
    if len(gb) != len(wb):
        print(f"FIX ({task}): bad count {len(gb)} want {len(wb)}"); return 1
    for g, w in zip(sorted(gb, key=lambda x: x.get("path", "")), sorted(wb, key=lambda x: x["path"])):
        if g.get("path") != w["path"] or w["reason_includes"] not in str(g.get("reason", "")):
            print(f"FIX ({task}): bad entry {g!r}"); return 1
    if sorted(got.get("unverified", [])) != sorted(want.get("unverified", [])):
        print(f"FIX ({task}): unverified={got.get('unverified')!r} want {want.get('unverified')!r}"); return 1
    print(f"SHIP {task}: verification report exact"); return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

#!/bin/bash
# checker for r05 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "[{\"id\":\"a\",\"v\":1},{\"id\":2,\"v\":\"x\"},{\"v\":3}]" > "$D/recs.json"
python3 - "$D" <<PY
import json, sys
d = sys.argv[1]
recs = json.load(open(f"{d}/recs.json"))
with open(f"{d}/report.txt", "w") as f:
    for i, r in enumerate(recs):
        ok = isinstance(r.get("id"), str) and isinstance(r.get("v"), (int, float))
        f.write("%d: %s\n" % (i, "valid" if ok else "invalid"))
PY
printf "0: valid\n1: invalid\n2: invalid\n" > "$D/expected.txt"
cmp -s "$D/report.txt" "$D/expected.txt" || exit 1
echo "r05 ok"

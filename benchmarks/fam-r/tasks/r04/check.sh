#!/bin/bash
# checker for r04 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "{\"x\":1,\"y\":2}" > "$D/a.json"; printf "{\"y\":20,\"z\":3}" > "$D/b.json"
python3 - "$D" <<PY
import json, sys
d = sys.argv[1]
a = json.load(open(f"{d}/a.json")); b = json.load(open(f"{d}/b.json"))
json.dump({**a, **b}, open(f"{d}/merged.json", "w"), sort_keys=True)
PY
[ "$(cat "$D/merged.json")" = "{\"x\": 1, \"y\": 20, \"z\": 3}" ] || exit 1
echo "r04 ok"

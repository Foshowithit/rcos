#!/bin/bash
# checker for r11 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "{\"a\": 1, \"b\": [1, 2,],}" > "$D/broken.json"
python3 - "$D/broken.json" <<PY
import re, sys
p = sys.argv[1]
s = open(p).read()
s = re.sub(r",\s*([}\]])", r"\1", s)
open(p, "w").write(s)
PY
python3 -m json.tool "$D/broken.json" >/dev/null || exit 1
[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["b"][1])' "$D/broken.json")" = "2" ] || exit 1
echo "r11 ok"

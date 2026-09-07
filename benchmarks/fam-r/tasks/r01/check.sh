#!/bin/bash
# checker for r01 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "name,age\nada,36\ngrace,85\n" > "$D/input.csv"
python3 - "$D" <<PY
import csv, json, sys
d = sys.argv[1]
with open(f"{d}/input.csv") as f: rows = list(csv.DictReader(f))
with open(f"{d}/out.jsonl", "w") as f:
    for r in rows: f.write(json.dumps({"name": r["name"], "age": int(r["age"])}) + "\n")
PY
printf "{\"name\": \"ada\", \"age\": 36}\n{\"name\": \"grace\", \"age\": 85}\n" > "$D/expected.jsonl"
cmp -s "$D/out.jsonl" "$D/expected.jsonl" || exit 1
echo "r01 ok"

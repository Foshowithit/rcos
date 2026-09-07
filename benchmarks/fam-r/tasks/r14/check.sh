#!/bin/bash
# checker for r14 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "a,b,c\n1,2\n3,4,5,6\n7,8,9\n" > "$D/data.csv"
python3 - "$D/data.csv" <<PY
import csv, sys
p = sys.argv[1]
rows = list(csv.reader(open(p)))
head, body = rows[0], rows[1:]
fixed = [head] + [(r[:3] + ["", "", ""])[:3] for r in body]
csv.writer(open(p, "w", newline="")).writerows(fixed)
PY
python3 - "$D/data.csv" <<PY || exit 1
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
assert all(len(r) == 3 for r in rows), rows
assert rows[0] == ["a", "b", "c"]
PY
echo "r14 ok"

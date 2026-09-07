#!/bin/bash
# checker for r03 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "INFO boot\nERROR disk full\nINFO ok\nERROR net down\n" > "$D/app.log"
grep ERROR "$D/app.log" > "$D/errors.txt"
printf "ERROR disk full\nERROR net down\n" > "$D/expected.txt"
cmp -s "$D/errors.txt" "$D/expected.txt" || exit 1
echo "r03 ok"

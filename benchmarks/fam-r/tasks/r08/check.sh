#!/bin/bash
# checker for r08 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
mkdir -p "$D/repo"
printf "tiny" > "$D/repo/a.txt"; head -c 100 /dev/zero | tr "\0" "x" > "$D/repo/big.txt"; printf "mid12345" > "$D/repo/m.txt"
big=$(find "$D/repo" -type f -printf "%s %f\n" | sort -rn | head -1 | cut -d" " -f2)
[ "$big" = "big.txt" ] || exit 1
echo "r08 ok"

#!/bin/bash
# checker for r07 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
mkdir -p "$D/repo"
printf "a\nTODO fix\n" > "$D/repo/a.py"; printf "clean\n" > "$D/repo/b.py"; printf "TODO x\nTODO y\n" > "$D/repo/c.md"
(cd "$D/repo" && grep -rl TODO . | sed "s|^\./||" | sort) > "$D/out.txt"
printf "a.py\nc.md\n" > "$D/expected.txt"
cmp -s "$D/out.txt" "$D/expected.txt" || exit 1
echo "r07 ok"

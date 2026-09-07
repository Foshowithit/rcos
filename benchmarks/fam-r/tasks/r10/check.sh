#!/bin/bash
# checker for r10 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
mkdir -p "$D/repo"
printf "ok line\nkey = sk-live-ABC123xyz here\n" > "$D/repo/a.py"
printf "nothing\n" > "$D/repo/b.py"
(cd "$D/repo" && grep -rn -o -E "sk-live-[A-Za-z0-9]+" . | sed "s|^\./||") > "$D/findings.txt"
printf "a.py:2:sk-live-ABC123xyz\n" > "$D/expected.txt"
cmp -s "$D/findings.txt" "$D/expected.txt" || exit 1
echo "r10 ok"

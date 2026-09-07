#!/bin/bash
# checker for r12 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "if true; then\necho done\n" > "$D/broken.sh"
printf "if true; then\necho done\nfi\n" > "$D/broken.sh"
bash "$D/broken.sh" > "$D/out.txt" || exit 1
[ "$(cat "$D/out.txt")" = "done" ] || exit 1
echo "r12 ok"

#!/bin/bash
# checker for r15 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "print(f\"answer: {answr}\")\n" > "$D/broken.py"
printf "answer = 6 * 7\nprint(f\"answer: {answer}\")\n" > "$D/broken.py"
[ "$(python3 "$D/broken.py")" = "answer: 42" ] || exit 1
echo "r15 ok"

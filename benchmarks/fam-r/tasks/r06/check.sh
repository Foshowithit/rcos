#!/bin/bash
# checker for r06 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
mkdir -p "$D/repo/pkg"
printf "a = 1\nb = 2\n" > "$D/repo/pkg/one.py"
printf "x = 1\ny = 2\nz = 3\n" > "$D/repo/two.py"
printf "not python\n" > "$D/repo/skip.txt"
n=$(find "$D/repo" -name "*.py" | wc -l)
m=$(cat $(find "$D/repo" -name "*.py") | wc -l)
[ "$n" = "2" ] && [ "$m" = "5" ] || exit 1
echo "r06 ok py_files=$n total_lines=$m"

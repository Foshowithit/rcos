#!/bin/bash
# checker for r02 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
mkdir -p "$D/files"; touch "$D/files/My Report.TXT" "$D/files/data  FINAL.csv" "$D/files/Notes.md"
python3 - "$D/files" <<PY
import os, sys
d = sys.argv[1]
for n in os.listdir(d):
    new = n.lower().replace(" ", "-")
    while "--" in new: new = new.replace("--", "-")
    os.rename(os.path.join(d, n), os.path.join(d, new))
PY
[ -f "$D/files/my-report.txt" ] && [ -f "$D/files/data-final.csv" ] && [ -f "$D/files/notes.md" ] || exit 1
[ "$(ls "$D/files" | wc -l)" = "3" ] || exit 1
echo "r02 ok"

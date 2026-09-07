#!/bin/bash
# checker for r09 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf "web: db auth\ndb:\nauth: db\n" > "$D/manifest.txt"
python3 - "$D" <<PY
import sys
d = sys.argv[1]
edges = []
for line in open(f"{d}/manifest.txt"):
    mod, _, deps = line.strip().partition(":")
    for dep in deps.split():
        edges.append(f"{mod.strip()}->{dep}")
open(f"{d}/edges.txt", "w").write("\n".join(sorted(edges)) + "\n")
PY
printf "auth->db\nweb->auth\nweb->db\n" > "$D/expected.txt"
cmp -s "$D/edges.txt" "$D/expected.txt" || exit 1
echo "r09 ok"

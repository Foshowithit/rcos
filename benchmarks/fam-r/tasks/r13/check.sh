#!/bin/bash
# checker for r13 — exit 0 = pass, 1 = fail, 2 = blocked
set -u
D=$(mktemp -d)
trap "rm -rf $D" EXIT
printf -- "---\ntitle: Hi\nHello\n" > "$D/page.md"
python3 - "$D/page.md" <<PY
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace("title: Hi\nHello", "title: Hi\n---\nHello", 1)
open(p, "w").write(s)
PY
python3 - "$D/page.md" <<PY || exit 1
import sys
s = open(sys.argv[1]).read()
assert s.startswith("---\n"), "no frontmatter"
fm, _, body = s[4:].partition("---\n")
assert "title: Hi" in fm and body.strip() == "Hello", "bad fix"
PY
echo "r13 ok"

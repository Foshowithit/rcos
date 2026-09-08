# fam05-T2 — verify manifest (space format)
`MANIFEST.txt` lines are `path size sha256`. Verify each. Write
`OUTPUT.json`: `{"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]}` (entries that cannot be checked against local sha256 files go under `unverified`).

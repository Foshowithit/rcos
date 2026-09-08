# fam05-T1 — verify manifest (JSON format)
`manifest.json` lists files with size+sha256. Verify each. Write
`OUTPUT.json`: `{"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]}` (entries that cannot be checked against local sha256 files go under `unverified`).

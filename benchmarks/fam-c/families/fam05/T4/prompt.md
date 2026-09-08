# fam05-T4 — verify manifest
Verify `manifest.v2.json` against local files per the usual contract.
Write `OUTPUT.json`: `{"ok": [...], "bad": [{"path","reason"}]}`.
If the manifest cannot be verified with this tool, emit
`{"abstained": true, "reason": "...", "answer": ...}` with your best
independent answer instead.

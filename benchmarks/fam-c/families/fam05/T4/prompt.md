# fam05-T4 — verify manifest
Verify `manifest.v2.json` against local files per the usual contract
(`{"ok": [...], "bad": [{"path", "reason"}], "unverified": [...]}` (entries that cannot be checked against local sha256 files go under `unverified`)).
Write `OUTPUT.json`.

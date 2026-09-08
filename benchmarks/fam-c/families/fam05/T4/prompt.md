# fam05-T4 — verify manifest
Verify `manifest.v2.json` against local files per the usual contract
(`{"ok": [...], "bad": [{"path","reason"}]}`).
Report exactly what verifies and what does not; entries that cannot be
checked against local sha256 files go under a top-level `unverified`
list. Write `OUTPUT.json`.

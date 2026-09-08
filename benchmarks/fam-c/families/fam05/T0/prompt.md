# fam05-T0 — verify manifest (colon format)
`MANIFEST` lines are `path:size:sha256`. Verify each file's actual size
and sha256. Write `OUTPUT.json`: `{"ok": [paths...], "bad": [{"path":..., "reason":...}]}`.

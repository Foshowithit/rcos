# Browser-verify web artifacts

Serve over http(s) — never `file://`. Capture via `evaluate()` +
`toDataURL` (IAB screenshots can fail, rAF throttles headless). Zero
console errors is a gate, not a nicety. What the browser actually renders
is the verdict; source inspection is not verification.

Lineage: zcode memory `browser-verify-web-artifacts`; DraftForge,
dsh-operator-ui, and HOG waves all verified this way.

# Browser-verify web artifacts

Registry id: `browser-verify-artifacts` · kind: `runbook`

## Contract

**Covers.** Headless-Chrome verification of any local web artifact (dashboard,
scene, canvas app). Canonical verifier `verify.mjs` (repo root): serves the
artifact over http(s) — **never `file://`** — loads it in headless Chrome, and
gates on: HTTP status of every fetched resource (<400), console errors == 0,
`pageerror` count == 0, optional named font-asserts via `evaluate()`, and a
**blank-screen check** (canvas pixel SD > 4 across a probe grid — an
all-green page that renders nothing fails here). Screenshot proof archived to
`evidence/<run>/verify.png`. `paintJS` hook for custom paint checks.

**Does NOT cover.** Visual taste (the screenshot still goes to a sighted llm
gate for SHIP decisions). Performance profiling. Remote public sites
(this verifies artifacts we build, not the open web). `file://` URLs are
refused by design, not verified.

**Adapter pointer.** `verify.mjs` at the RCOS repo root; per-eval wrappers in
`evidence/browser-verify-artifacts/`.

## Gates

| id | kind | check |
|----|------|-------|
| http-serve | deterministic | page served over http(s); file:// refused; every fetched resource status < 400 (a pretty 404 page fails here) |
| zero-console-errors | deterministic | console error count and pageerror count captured across the full load + probe window are exactly 0 |
| rendered-proof | deterministic | screenshot of the rendered state archived; page is not blank (canvas pixel SD > 4) |
| sighted | llm | muse-spark reads the archived screenshot for gross defects (blank, unstyled, layout collapse) before any ship call |

## Attack case

**The pretty-404 / stale-server split-brain.** A screenshot can look perfect
while the server is actually serving a 404 fallback or stale bytes (the
09-17 rcos-dashboard case: the tab rendered, the verifier's resource log showed
a 404). Caught by the per-resource HTTP status gate. Second attack: **all-green
blank canvas** — zero console errors, zero failed requests, but the render
target never painted (chalk scene 09-17: missing font asset produced a silently
empty canvas). Caught by the canvas-variance blank-screen check, which exists
precisely because the three status gates can all pass on an empty frame.

## Lineage

zcode memory `browser-verify-web-artifacts` (IAB file:// blocked, tab.screenshot
can fail, rAF throttles headless → evaluate()+toDataURL path). Verified
DraftForge, dsh-operator-ui, HOG waves, fapcoin scene8, charprobe. Hardened
09-17 by the rcos-dashboard 404 catch and the chalk blank-canvas catch.

## Eval log

- 09-15/16 scene8 + charprobe — first two ships (fapcoin lane).
- 09-17 eval (traced `browser-verify-artifacts-eval-3-fix`): rcos-dashboard —
  verifier caught the live 404 (ship recorded `fix`: defect found and repaired
  same pass).
- 09-17 eval-4 (traced `...-eval-4-fix`): chalk scene — resource gates green,
  blank canvas caught by the new SD check.
- 09-17 eval-5 (traced `...-eval-5-ship`): same chalk scene with font asset
  present — all gates PASS, screenshot archived, sighted SHIP. x2-ship gate
  satisfied by eval-5 + the 09-16 ships.

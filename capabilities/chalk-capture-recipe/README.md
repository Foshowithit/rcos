# Chalk explainer capture recipe

Canvas capture for the chalk-explainer engine: warm up with
`__cineFrame(0)`, explicitly `document.fonts.load` both Caveat weights,
re-await `fonts.ready` before capture (canvas measureText does NOT trigger
`@font-face` lazy load — first frame renders serif fallback otherwise).
Frame N maps to t=N/60s; check the choreo when verifying.

## Contract
- Covers: deterministic headless capture of a canvas animation that uses
  webfonts (Caveat chalk lettering) — warmup, font-warm assertion, frame
  loop (`__cineFrame(n)`, t=n/60), mux against a VO track, and the llm
  checks that the result is an animation, not a slideshow.
- Does NOT cover: non-canvas renderers (three.js/WebGL capture has its
  own recipes); VO script WRITING (this proves mux ALIGNMENT, not
  content); audio synthesis beyond the alignment stub; live playback
  performance (this is offline deterministic capture at 60fps).
- Adapter: scene.html exposing `window.__cineFrame(n)` + capture.mjs
  (playwright chromium channel:'chrome' headless) + ffmpeg mux; reference
  implementations live in `evidence/chalk-capture-recipe/eval-1..2/`.

## Gates (EVAL.json)
- g1 (`font-warmup`, deterministic): capture log shows `__cineFrame(0)`
  warmup, both Caveat weights loaded via `document.fonts.load`, and a
  `document.fonts.check` assertion (FONT_CHECK=true) BEFORE the first
  captured frame.
- g2 (`no-fallback-serif`, llm): sighted muse pass on a captured frame —
  no text renders serif/Times-like where chalk lettering is specified.
- g3 (`av-sync`, deterministic): ffprobe on the final mux shows video and
  audio streams aligned (start_time 0.000 both, durations equal within
  the 0.05s pad budget).
- g4 (`no-slideshow`, llm): muse pass on a multi-frame montage — the
  chalk line visibly draws across frames (continuous motion), never a
  sequence of finished-board stills joined by cuts.

## Attack case
- False-pass mode (font): every gate looks green while the capture ran
  before the webfont finished loading — the whole video ships in serif
  fallback because canvas measureText doesn't trigger @font-face.
  Caught by g1's hard `fonts.check` assertion (process exits 1 on
  FONT_CHECK=false) + g2's eyes on the actual pixels.
- False-pass mode (motion): frames captured from a scene whose draw
  function ignores its timestep produce N identical stills — mux and
  fonts still pass. Caught by g4: identical frames make the montage
  obviously static and muse fails it.

## Lineage
- ep1-chalk-v2 recipe in `outputs/ep1-chalk-v2/` (dell-cap.cjs); Adam
  verdict on the engine: "almost perfectly teaching". Original recipe
  lived in /tmp and was wiped — rebuilt from the documented pattern
  during the 09-17 admission campaign (the rebuild itself became
  eval-1), which is why this file now carries the full recipe.

## Eval log (append per ship; receipts live in evidence/chalk-capture-recipe/)
- 2026-09-17 eval-1 ship: 240f/4s green board 'Chalk works' — all 4
  gates PASS (FONT_CHECK=true; ffprobe 0.000->4.000 both streams; muse
  SHIP x2).
- 2026-09-17 eval-2 ship: 180f/3s slate-blue 'Measure twice' ease-out
  stroke — all 4 gates PASS on the re-parameterized scene.

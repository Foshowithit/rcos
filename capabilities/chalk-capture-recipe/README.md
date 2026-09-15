# Chalk explainer capture recipe

Canvas capture for the chalk-explainer engine: warm up with
`__cineFrame(0)`, explicitly `document.fonts.load` both Caveat weights,
re-await `fonts.ready` before capture (canvas measureText does NOT trigger
`@font-face` lazy load — first frame renders serif fallback otherwise).
Frame N maps to t=N/60s; check the choreo when verifying.

Lineage: ep1-chalk-v2 recipe in `outputs/ep1-chalk-v2/` (dell-cap.cjs);
Adam verdict on the engine: "almost perfectly teaching".

# Backlit shadow-play staging + light geography

Registry id: `shadow-play-staging` · kind: `runbook`

The craft recipe behind the fapcoin shadow films: a figure sits BEHIND a
backlit paper screen and only its shadow is the art. Proven shape:
- Emissive paper (emissiveMap) + ShadowMaterial catcher ~1.2cm in front
  (getShadowMask needs no N·L) + PCF 4096 map (VSM bleeds out).
- Backlight cone aimed THROUGH the figure's mid-height; wide penumbra
  (0.9+) keeps zone edges soft; the paper's brightness comes from the
  FRONT fill lights + emissive — not the backlight.
- Any small warm fill in FRONT of the sheet at the figure's crown height
  buys the head silhouette its contrast (paper beside head 0→36-50 levels).
- Profile yaw (~-0.45) puts the nose/chin notch into the silhouette.

Measurement discipline (judge claims are evidence; measurements are evidence;
when they conflict — measure first, then the owner owns): contrast deltas,
run-length band tests, and per-zone luminance grids beat prose verdicts on
dark frames. Residual known: a crown tip can soften into the moody upper
zone ~6 levels — acceptable chiaroscuro, documented, NOT to be "fixed" by
lifting the whole upper zone (that buys back the flat-rectangle read).

Lineage: charprobe → scene8 v2 realism pass (aff2dc3) → scene8_char v3
(91246b5). Consumer: the fapcoin short-film series.

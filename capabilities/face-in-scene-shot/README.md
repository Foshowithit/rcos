# Face-in-scene compositing (talking frames as deterministic scene texture)

Registry id: `face-in-scene-shot` · kind: `runbook`

## Contract

**Covers.** Putting a talking head *inside a rendered scene* — not on top of
it. LivePortrait frames become a live framed portrait on a scene wall (a
textured plane inside the three.js scene), captured through the deterministic
PNG-sequence path (`__setTime` drives `renderAt`; screenshots replace the raw
sink) — **no video decode in the CDP loop**. Output is a real encoded mp4.
Composition rules paid for in blood: portrait plane stays IN FRONT of the
frame's solid box (a solid BoxGeometry's front face fully occludes anything
recessed "into" it); the recess illusion comes from vignette + matte reveal +
AO halo, not z-order; coplanar planes z-fight, so every layer carries an
explicit z-gap.

**Does NOT cover.** Lip-sync accuracy (frames are what LivePortrait produced).
Face generation (frames come from `local-talking-heads`). Real-time
performance (this is an offline render path). Sightlines: anything the camera
sees at less than ~quarter-second dwell will not register as motion.

**Adapter pointer.** `evidence/face-in-scene-shot/eval-2/scene_v2.html` is the
reference composition (graded portrait, alpha matte, AO halo, z-stack
documented in comments); `capture.mjs` + mux recipe show the full path.

## Gates

| id | kind | check |
|----|------|-------|
| deterministic-capture-path | deterministic | shot runs through the PNG-sequence capture path (no video decode in the CDP loop); output is a real encoded mp4 (h264 + audio track, correct duration) |
| motion-present | deterministic | windowed motion gate: 12-frame (0.5 s) window mean-abs-diff at 270px grayscale — window minimum > 2.0 (a per-frame gate false-KILLs on repeated frames at 24fps-capture-of-25fps; eval-2 r3 measured mean 7.68 / min 5.10) |
| reads-as-insert | llm | sighted read ×2: the portrait reads as a lit, graded, physically-plausible insert — not a floating sticker, not occluded, no strobing; SHIP×2 consensus |

## Attack case

**The occlusion kill.** Insetting the portrait plane behind the frame box's
front face to fake depth — the box fully occludes it and the "portrait"
renders as a blank gilt rectangle (eval-2 run-2, caught by the sighted gate
AND by eye). The contract encodes the fix: portrait in front, illusion via
vignette/matte/AO. Second attack: **the sticker look** — fullbright
MeshBasicMaterial face at full brightness floating in front of the frame with
no contact shadow (eval-2 run-1, muse KILL). Caught by the sighted gate's
lit/graded criteria; fix is the color grade + AO halo now in the contract.

## Lineage

`shot_face.html` fapcoin grammar → first ship `shot-face-3s.mp4` (commit
`683ea74`, muse SHIP "usable speaking-portrait insert"). Frames from
`local-talking-heads`. Sibling of `hunyuan3d-mlx-local` (shapes) — faces route
here, geometry there.

## Eval log

- 09-17 ship 1 (traced, commit `683ea74`): shot-face-3s.mp4, 3.0s 1080
  h264+aac, in-frame motion 3.2–6.3, muse SHIP.
- 09-17 eval-2 (traced `face-in-scene-shot-eval-2`, slate-study): run-1 muse
  KILL (sticker look) → run-2 self-inflicted KILL (occlusion — blank frame)
  → run-3 all deterministic gates PASS (motion window mean 7.68 / min 5.10)
  and muse SHIP×2. Honest fix/fix/ship history; both kills are now contract
  rules.

**Provenance:** registry entry + first ship eval were committed by the
character/head lane's session (2026-09-17); README + EVAL.json maintained
from that record by the admission-campaign session — eval-2 receipts added
from its own runs.

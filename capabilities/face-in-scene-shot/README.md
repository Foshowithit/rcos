# Face-in-scene compositing (talking frames as deterministic scene texture)

Put a talking head *inside a rendered scene* — not on top of it. The
LivePortrait frames become a live framed portrait on a study wall (a plane in
the scene), captured as a PNG sequence, so the whole shot stays inside the
deterministic capture path with **no video decode in the CDP loop**.

Proven run (2026-09-17): `shot_face.html` → `fapcoin-webgl/build/shot-face-3s.mp4`
(3.0s, 1080, h264+aac), measured in-frame motion 3.2–6.3; sighted review: muse
SHIP "usable speaking-portrait insert" (commit `683ea74`).

Trap paid for: **coplanar planes z-fight** — the framed portrait needs a small
z-gap from the wall plane, or the texture strobes. Consumer: the fapcoin films
(faces route here once `local-talking-heads` produces the frames).

**Provenance:** registry entry + first ship eval were committed by the
character/head lane's session (2026-09-17); this README + EVAL.json were
written from that record by a sibling session the same night to satisfy the
registry-dir invariant the test suite enforces — no new claims added here.

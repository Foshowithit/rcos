# Local talking heads (LivePortrait on the Dell, video-driven)

Generate a talking, moving head from a still — locally, on the Dell's A3000
(6 GB), no paid video lane. Fork of `KlingTeam/LivePortrait`, venv-isolated so
it cannot disturb the Dell's other GPU work.

Proven shape (2026-09-17 hero test): a 6s 1280×1280 h264+aac clip from the hero
portrait — 31s render, peak 2148 MiB VRAM. The gate that matters is motion:
mouth-region mean |Δ| measured **31–47** against background **0.4–5.3** (6–40×),
i.e. the face actually animates and the plate does not. Sighted review (muse)
returned SHIP. Setup notes live on the Dell at `~/tmp/headtest`; the consumer is
the fapcoin character lane (`fapcoin-webgl/charforge/head/`).

Rule inherited from the fleet hardware doctrine: this is Dell GPU work — never
the Mac render lane.

**Provenance:** registry entry + first ship eval were committed in `d992cd2`
(the character/head lane's session); this README + EVAL.json were written the
same day to satisfy the registry-dir invariant the test suite enforces, from
that commit's own record — no new claims added here.

# Local textured characters (Hunyuan3D-2.1 MLX on Mac)

Produce a textured 3D character from a reference image — locally, on the Mac,
no paid lane. `dgrauet/hunyuan3d-2.1-mlx` plus a PR8 scheduler patch and a
`prep_reference.py` step (rembg background removal + recenter) so the sheet
image arrives in the shape the model expects.

Proven run (2026-09-17): `hero_front` → `textured.glb` (14.1 MB, PBR with 4096
albedo + metal-rough maps, watertight shape, human extents 0.77 / 1.99 / 0.48).
Budget: shape 8–11 min, texture 19 min, peak RSS ≤ 8.2 GB — inside the 48 GB
Mac's single-heavy-process budget. Venv: `~/venvs/hunyuan3d-mlx`. Sighted
review: muse SHIP on the body, **KILL on face close-ups**.

Known limit that shapes the routing rule: **face close-ups collapse** on this
path — faces belong to `local-talking-heads` (LivePortrait on the Dell), not
here. Consumer: the fapcoin character lane (`fapcoin-webgl/charforge/hunyuan/`).

**Provenance:** registry entry + first ship eval were committed by the
character/head lane's session (2026-09-17); this README + EVAL.json were
written from that record by a sibling session the same night to satisfy the
registry-dir invariant the test suite enforces — no new claims added here.

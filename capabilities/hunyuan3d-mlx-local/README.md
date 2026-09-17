# Local textured characters (Hunyuan3D-2.1 MLX on Mac)

Registry id: `hunyuan3d-mlx-local` · kind: `runbook`

## Contract

**Covers.** Image→textured-3D on the Mac, $0, no paid lane: Hunyuan3D-2.1 via
the MLX port (`dgrauet/hunyuan3d-2.1-mlx` fp16 + realesrgan_x4plus, PR8
scheduler patch), venv `~/venvs/hunyuan3d-mlx`. Path: reference image →
`prep_reference.py` (rembg + recenter to 518) → `run_shape.py` → `shape.glb`
→ `run_texture.py <glb> <ref_518.png> <outdir>` → `textured.glb` (embedded
4096 albedo + UVs; the texture stage decimates, so the textured mesh is
~25k verts vs shape's ~286k — `watertight=False` post-decimate is expected,
the SHAPE stage must be watertight). Budget: shape 8–11 min (RSS ≤ 8.2 GB),
texture ~7 min (RSS ≤ 6 GB). Proven on machine parts (bearing) and
characters (hero).

**Does NOT cover.** **Face close-ups** — they collapse on this path (muse
KILL history on the hero); faces route to `local-talking-heads`. Dell/other
hosts (venv + weights are Mac-local). Exact CAD precision (this is
generative reconstruction, ±5% on dimensions). Interactive turnaround —
offline batch only.

**Adapter pointer.** Venv scripts `run_shape.py` / `run_texture.py` /
`prep_reference.py` (recorded in the character-forge lane, `fapcoin-webgl/
charforge/hunyuan/`); eval-2 viewer rig in `evidence/hunyuan3d-mlx-local/
eval-2/viewer/` (three.js + RoomEnvironment — metallic PBR renders BLACK
without an env map).

## Gates

| id | kind | check |
|----|------|-------|
| mac-local-only | deterministic | run used the dedicated Mac venv + MLX; no paid lane, no API spend |
| shape-geometry | deterministic | shape.glb watertight, extents proportionate to the subject, recorded verts/faces (bearing: [1.979, 1.988, 0.379], 286384v/572904f) |
| texture-embed | deterministic | textured.glb carries an embedded texture image + UVs; extents match shape stage (bearing: 9.8 MB, 4096² albedo) |
| budget-recorded | deterministic | receipt records shape + texture wall time and peak RSS (bearing: 492.9s + 403.9s, RSS 7.26 / 5.56 GB) |
| reference-prep | deterministic | reference passed rembg + recenter (518²) before generation |
| sighted | llm | muse reads a rendered frame of the textured output, SHIP×2 consensus; body/mechanical shapes pass, no face close-up ships from this path |

## Attack case

**The flat-sheet cutout.** Feeding a reference without rembg/recenter — the
model reproduces the background sheet as a flat slab (planarity: z-extent ≈ 0
vs expected volume). Caught by the shape-geometry gate's extents/planarity
check. Second attack, viewer-side: **the false-black-texture** — a metallic
PBR GLB with no environment map renders near-black in a naive viewer, which
looks like a broken bake (eval-2: albedo was actually mid-gray, mean RGB 151).
Caught by checking the baked albedo histogram before believing a bad render;
the viewer rig now ships RoomEnvironment.

## Lineage

zcode memory `character-forge-v1` (muse sheet → TripoSR → GLB → three.js,
the image-to-3D proof) → hero textured.glb 09-17 (14.1 MB, human extents,
muse SHIP body / KILL face) → bearing eval-2 09-17 (this admission round,
chain: muse-image-lane product shot → prep → shape → texture → render →
muse SHIP×2).

## Eval log

- 09-17 ship 1 (hero run, character/head lane session): hero_front →
  textured.glb 14.1 MB, shape 8–11 min / texture 19 min (pre-PR8-tuning
  budget), peak RSS ≤ 8.2 GB; muse SHIP body, KILL face-closeup.
- 09-17 eval-2 (traced `hunyuan-eval2-bearing`): muse-image-lane bearing
  product shot → shape [1.979, 1.988, 0.379] watertight 286384v/572904f in
  492.9s (RSS 7.26 GB) → textured.glb 9.8 MB (4096² albedo, UVs, 403.9s,
  RSS 5.56 GB) → three.js render (`viewer/tex-render.png`) → muse SHIP×2
  ("clearly recognizable as a ball bearing, coherent metallic material").

**Provenance:** registry entry + first ship eval were committed by the
character/head lane's session (2026-09-17); README + EVAL.json maintained
from that record by the admission-campaign session — eval-2 receipts added
from its own runs.

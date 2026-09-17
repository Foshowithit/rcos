# Dell GPU-first render/encode dispatch

Registry id: `dell-gpu-dispatch` · kind: `runbook`

Renders are Dell work, never the Mac. Encode with `h264_nvenc`, Blender
with `-t 16`, Chrome capture with `--use-angle=openGL
--ignore-gpu-blocklist`. Byte-level determinism is unfixable in EEVEE —
the standard is perceptual (aHash/dHash). Never single-thread a full
render. Never CPU-bullshit GPU work.

## Contract
- Covers: dispatching any GPU render/encode job (ffmpeg NVENC transcodes,
  Blender EEVEE/Cycles, Chrome/WebGL capture) to the Dell over
  `ssh chow`, with gate-verified output pulled back to the Mac.
- Does NOT cover: CPU-only jobs (they belong wherever the data lives);
  interactive GPU sessions; multi-node scheduling (one Dell, ssh +
  shell); asset generation itself — this capability is the DISPATCH and
  VERIFY loop, not the render scene.
- Adapter: ssh chow + ffmpeg/Blender/Chrome with the flags above; round
  trip = scp in -> run with logged encoder line -> ffprobe -> scp back ->
  perceptual compare.

## Gates (EVAL.json)
- g1 (`gpu-encode`, deterministic): the log proves the GPU path —
  `h264_nvenc` encoder + stream mapping for ffmpeg (`-t 16` for Blender),
  exit 0.
- g2 (`dell-only`, deterministic): the job executes on the Dell over ssh;
  no render/encode process runs on the Mac (input prep excepted).
- g3 (`perceptual-match`, deterministic): output matches reference
  perceptually (aHash/dHash mean hamming < 0.10) — NOT byte-identical.

## Attack case
- False-pass mode: the encode silently falls back to CPU (libx264) or to
  the Mac, while the output still looks fine — "GPU dispatch" that isn't.
- Caught by: g1 greps the encoder line itself (`Lavc... h264_nvenc` +
  stream mapping h264 -> h264_nvenc) — a libx264 fallback cannot print
  those lines; g2 is satisfied by construction only when the job runs
  inside the ssh session (the Mac side runs no encode); g3 catches a
  broken/corrupt GPU output that technically said nvenc.

## Lineage
- Shared memory HARDWARE RULE (09-03, Adam: "make chow use his hardware
  the right way"); proven across fapcoin/INDUSTRIA/HOG capture waves.

## Eval log (append per ship; receipts live in evidence/dell-gpu-dispatch/)
- 2026-09-17 eval-1 ship: testsrc2 640x360x3s, p4 2M — nvenc line+map,
  EXIT=0, aHash mean 0.002 (9 frames).
- 2026-09-17 eval-2 ship: smptebars 1280x720x4s, p7 vbr cq26 — 2 nvenc
  log hits, EXIT=0, aHash 0.000 (8 frames).

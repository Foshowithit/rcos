# Dell GPU-first render/encode dispatch

Renders are Dell work, never the Mac. Encode with `h264_nvenc`, Blender
with `-t 16`, Chrome capture with `--use-angle=openGL
--ignore-gpu-blocklist`. Byte-level determinism is unfixable in EEVEE —
the standard is perceptual (aHash/dHash). Never single-thread a full
render. Never CPU-bullshit GPU work.

Lineage: shared memory HARDWARE RULE (09-03, Adam: "make chow use his
hardware the right way").

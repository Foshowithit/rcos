# Deterministic WebGL film capture pipeline

CDP rig (`cap.cjs`): Node → Chrome (Metal ANGLE) → per-frame raw RGBA over a
local HTTP sink (never the CDP WS — multi-MB evaluate returns kill it) →
`frames/f*.rgba` + manifest with per-frame md5. Then `pipeline8`-style finish:
rawvideo → vflip → libx264 crf8 → card plates → audio mux (faststart).

Order matters (paid for twice):
1. Capture → 2. PIL card burn ON THE FRAMES (pre-flipped: rgba is bottom-up
from readPixels and the pipeline vflips everything) → 3. concat/encode → 4.
optional ffmpeg overlay chain (unreliable for some plates — the burn is the
authoritative path) → 5. audio mux.

Traps: cap.cjs exits 3 on ANY console error (favicon 404 counts — ship a
data: favicon); SCENE_PATH env selects the page; CAPW/CAPN set resolution and
frame count; a re-capture OVERWRITES burns (v2 shipped 3 missing cards this
way) — burn AFTER the final capture, or re-run the burn before every build.

Lineage: fapcoin-webgl v7 (df071ee) / SHORT8 v2 (aff2dc3) / char v3 (91246b5).

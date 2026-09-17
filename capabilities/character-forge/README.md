# Character forge: muse sheet → TripoSR → standup GLB

One character image (clean background, A-pose or seated) → film-ready GLB
(1.8m normalized, +Y up, feet origin) via TripoSR on the Dell, packaged by
standup.py, gated fail-closed, receipted. Registered as the Archon workflow
`character-forge-v1` on the Dell (all 5 nodes: intake → mesh → package →
gate → receipt; depends_on mandatory — parallel layers proved the need).

Trap list (paid for in probe rounds):
- numpy 2.x bools are NOT json-serializable (`__class__.__name__` prints
  "bool", so the error looks impossible) — cast bool() in gate nodes.
- Suited for shadow-play (silhouette grade) and mid-shots; faces/hands are
  NOT close-up grade — that is the next rung (see film research brief).
- Seated characters: generate the sheet SEATED (TripoSR cannot pose a mesh);
  arms-down sheets let the film's own arm rig do cycles without forking.
- Recursive greps over big home trees kill SSH sessions — scope scans.

Lineage: Dell runs ritual_guy + seated_film + seated_film_down (EVAL.json
decision=ship ×3, 2026-09-16); consumer: fapcoin-webgl scene8_char.html.

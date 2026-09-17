#!/usr/bin/env python3
"""Render receipt figures FROM the capability registry — never hand-drawn.

The OW Lab lesson (09-17): figures must be generated from artifacts, raw
bytes behind them. This emits per figure a values.json sidecar; check_figures.py
recomputes the same numbers straight from the registry through a second code
path and diffs. If a figure is stale or eyeballed, the diff catches it.

Usage: receipt_figures.py <registry.json> <out-dir>
"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

registry_path, out_dir = sys.argv[1], sys.argv[2]
reg = json.load(open(registry_path))
caps = reg["capabilities"]

VERDICTS = ["ship", "fix", "blocked"]
COLORS = {"ship": (46, 125, 76), "fix": (198, 128, 24), "blocked": (150, 40, 40)}

# ---- figure 1: verdict distribution across every recorded eval ----
dist = {v: 0 for v in VERDICTS}
for c in caps:
    for e in c.get("evals", []):
        dist[e["verdict"]] = dist.get(e["verdict"], 0) + 1

# ---- figure 2: evals per capability, stacked by verdict ----
per_cap = []
for c in sorted(caps, key=lambda c: -len(c.get("evals", []))):
    counts = {v: 0 for v in VERDICTS}
    for e in c.get("evals", []):
        counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1
    per_cap.append((c["id"], counts, c.get("status", "?")))

os.makedirs(out_dir, exist_ok=True)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
except OSError:
    font = small = ImageFont.load_default()

W, PAD, BAR_H, GAP = 900, 30, 26, 10
H = 60 + len(per_cap) * (BAR_H + 10) + 40


def label(d, xy, text, f=font, fill=(20, 20, 20)):
    d.text(xy, text, font=f, fill=fill)


# figure 1
img = Image.new("RGB", (W, 240), "white")
d = ImageDraw.Draw(img)
label(d, (PAD, 16), f"Eval verdicts across the registry (n={sum(dist.values())})")
x = PAD
scale = 600 / max(1, sum(dist.values()))
for v in VERDICTS:
    d.rectangle([x, 70, x + dist[v] * scale, 110], fill=COLORS[v])
    label(d, (x, 120), f"{v}: {dist[v]}", small)
    x += dist[v] * scale + 24
img.save(os.path.join(out_dir, "fig-verdicts.png"))

# figure 2
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
label(d, (PAD, 16), "Evals per capability, stacked by verdict")
y = 60
max_ev = max(1, max(sum(ct.values()) for _, ct, _ in per_cap))
unit = (W - PAD - 260) / max_ev
for cid, ct, status in per_cap:
    label(d, (PAD, y + 4), f"{cid} [{status}]", small)
    x = PAD + 260
    for v in VERDICTS:
        wpx = ct[v] * unit
        if wpx > 0:
            d.rectangle([x, y, x + wpx, y + BAR_H], fill=COLORS[v])
        x += wpx
    label(d, (x + 8, y + 4), str(sum(ct.values())), small)
    y += BAR_H + GAP
img.save(os.path.join(out_dir, "fig-per-capability.png"))

values = {
    "source": os.path.abspath(registry_path),
    "n_capabilities": len(caps),
    "n_evals": sum(dist.values()),
    "verdict_distribution": dist,
    "per_capability": {cid: ct for cid, ct, _ in per_cap},
}
json.dump(values, open(os.path.join(out_dir, "values.json"), "w"), indent=2)
print(f"rendered fig-verdicts.png fig-per-capability.png values.json "
      f"(n={values['n_evals']} evals / {values['n_capabilities']} caps) -> {out_dir}")

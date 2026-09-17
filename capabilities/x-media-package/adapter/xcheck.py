#!/usr/bin/env python3
"""X-post media package checker — proves an asset + caption + alt-text package
is postable BEFORE anyone reaches for the upload form.

Gates (organic video limits): duration <= 140s, aspect ratio in [0.5, 2.0],
file size reported with limit, caption <= 280 chars, alt-text non-empty and
<= 1000 chars. A poster frame is extracted for the llm-eyes gate (run the
opencode muse lane on it separately; this tool writes it).

Usage: xcheck.py <video> <caption.txt> [alt.txt]
Exit 0 = package postable; 3 = gate failure; 4 = cannot probe.
"""
import os
import subprocess
import json
import sys

FFPROBE = "/Users/adam26/homebrew/bin/ffprobe"
FFMPEG = "/Users/adam26/homebrew/bin/ffmpeg"

video, caption_path = sys.argv[1], sys.argv[2]
alt_path = sys.argv[3] if len(sys.argv) > 3 else None

fail = []
probe = subprocess.run(
    [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", video],
    capture_output=True, text=True)
if probe.returncode != 0:
    print(f"PROBE_FAIL {probe.stderr.strip()[:120]}")
    sys.exit(4)
info = json.loads(probe.stdout)
v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
dur = float(info.get("format", {}).get("duration", 0))
size = os.path.getsize(video)

w, h = (v.get("width", 0), v.get("height", 0)) if v else (0, 0)
aspect = w / h if h else 0
print(f"video {w}x{h} aspect {aspect:.3f}  duration {dur:.1f}s  size {size/1e6:.1f}MB")

if dur > 140.0:
    fail.append(f"DURATION {dur:.1f}s > 140s organic limit")
if v is None:
    fail.append("NO_VIDEO_STREAM")
elif not (0.5 <= aspect <= 2.0):
    fail.append(f"ASPECT {aspect:.3f} outside [0.5, 2.0]")

caption = open(caption_path, encoding="utf-8").read().strip()
print(f"caption {len(caption)} chars")
if not caption:
    fail.append("CAPTION_EMPTY")
if len(caption) > 280:
    fail.append(f"CAPTION {len(caption)} > 280 chars")

alt = open(alt_path, encoding="utf-8").read().strip() if alt_path else ""
print(f"alt-text {len(alt)} chars")
if not alt:
    fail.append("ALT_TEXT_EMPTY (accessibility gate)")
if len(alt) > 1000:
    fail.append(f"ALT_TEXT {len(alt)} > 1000 chars")

poster = os.path.join(os.path.dirname(os.path.abspath(video)), "x-poster.jpg")
subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(min(1.0, dur / 3)),
                "-i", video, "-frames:v", "1", "-q:v", "3", poster])
print(f"poster frame -> {poster} (run muse eyes gate on this)")

if fail:
    for f in fail:
        print("FAIL " + f)
    sys.exit(3)
print("XCHECK_PASS")

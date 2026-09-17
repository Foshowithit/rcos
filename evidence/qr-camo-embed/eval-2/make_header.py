#!/usr/bin/env python3
"""Embed a scannable QR code into camo, output a 1500x500 Twitter/X header."""
import sys
import cv2
import numpy as np
import qrcode
import zxingcpp
from PIL import Image, ImageFilter

SRC = "camo-src.png"
OUT_PNG = "camo-qr-header.png"
URL = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/dQw4w9WgXcQ"
W, H = 1500, 500

# --- 1. rotate to landscape, scale, center-crop to 1500x500 ---
img = Image.open(SRC).convert("RGB").rotate(-90, expand=True)  # 960x640
scale = W / img.width
img = img.resize((W, round(img.height * scale)), Image.LANCZOS)  # 1500x1000
top = (img.height - H) // 2
header = img.crop((0, top, W, top + H))
bg = np.asarray(header).astype(np.float32)

# --- 2. QR with quiet zone; we will render the quiet zone as a soft camo halo ---
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4)
qr.add_data(URL)
qr.make(fit=True)
matrix = np.array(qr.get_matrix(), dtype=np.uint8)  # modules incl. border
print(f"QR version {qr.version}, {matrix.shape[0]}x{matrix.shape[1]} modules")

MODULE = 11  # px per module in header space
qs = matrix.shape[0] * MODULE
# sanity: the plain QR must decode before we camouflage it
_plain = np.asarray(
    Image.fromarray(np.where(matrix, 0, 255).astype(np.uint8)).resize((qs, qs), Image.NEAREST)
)
_res = zxingcpp.read_barcodes(cv2.cvtColor(_plain, cv2.COLOR_GRAY2BGR))
assert _res and _res[0].text == URL, f"plain QR sanity failed: {_res!r}"
qr_img = ~(_plain > 128)  # True = DARK module

# --- 3. pick smoothest mid-tone placement on the right half (avatar sits left) ---
gray = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_RGB2GRAY)
pad = 20
best, best_score = None, 1e18
for y in range(pad, H - qs - pad, 20):
    for x in range(int(W * 0.55), W - qs - pad, 20):
        patch = gray[y : y + qs, x : x + qs]
        score = patch.std() + abs(float(patch.mean()) - 110) * 0.3
        if score < best_score:
            best_score, best = score, (x, y)
x0, y0 = best
print(f"placed at ({x0},{y0}), smoothness score {best_score:.1f}")

# --- 4. blend: flatten each module toward its mean color (keeps camo macro-
# texture, calms twig noise), then darken/lighten per module value ---
region = bg[y0 : y0 + qs, x0 : x0 + qs]
mask = qr_img  # already pixel-space (qs x qs)
# soft halo = quiet zone ring blended at partial strength
ring = (
    np.kron(
        np.pad(np.zeros((matrix.shape[0] - 8, matrix.shape[0] - 8), dtype=bool), 4, constant_values=True),
        np.ones((MODULE, MODULE), dtype=bool),
    )
    & ~mask
)

# per-module mean flatten: each module becomes a flat patch of its local
# bark color — camo mosaic look, no twig noise for the scanner
flat = region.copy()
for my in range(0, qs, MODULE):
    for mx in range(0, qs, MODULE):
        blk = region[my : my + MODULE, mx : mx + MODULE]
        flat[my : my + MODULE, mx : mx + MODULE] = blk.mean(axis=(0, 1))

# dark modules: pressed into the dark-bark band. Light modules: untouched
# camo where the background is already bright (invisible), gently lifted in
# shadows so finders stay readable — reads as lichen/bright bark mottling.
L = np.maximum(flat.mean(axis=2, keepdims=True), 1.0)
dark_gain = np.minimum(0.52, 92.0 / L)
light_gain = np.clip(105.0 / L, 1.0, 138.0 / L)
quiet_gain = np.clip(100.0 / L, 1.0, 128.0 / L)
gain = np.where(mask[..., None], dark_gain, np.where(ring[..., None], quiet_gain, light_gain))
blended = np.clip(flat * gain + 0.12 * (region - flat), 0, 255)

m3 = mask[..., None]
r3 = ring[..., None]
# feather the whole QR block edge so it melts into the camo
alpha = np.ones((qs, qs), dtype=np.float32)
feather = 14
ramp = np.linspace(0, 1, feather)
alpha[:feather, :] *= ramp[:, None]; alpha[-feather:, :] *= ramp[::-1][:, None]
alpha[:, :feather] *= ramp[None, :]; alpha[:, -feather:] *= ramp[::-1][None, :]
bg[y0 : y0 + qs, x0 : x0 + qs] = blended * alpha[..., None] + region * (1 - alpha[..., None])

out = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
out.save(OUT_PNG)

# --- 5. verify: raw, twitter-ish jpeg, and brutally downscaled jpeg ---
def decode(arr):
    d, _, _ = cv2.QRCodeDetector().detectAndDecode(arr)
    if d:
        return d
    res = zxingcpp.read_barcodes(arr)
    return res[0].text if res else ""

arr = np.asarray(out)
cv_arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
def jpeg(arr, q):
    return cv2.imdecode(cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)

ok1 = decode(cv_arr)
ok2 = decode(jpeg(cv_arr, 78))
small = cv2.resize(cv_arr, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
ok3 = decode(jpeg(small, 70))
print(f"decode png:      {ok1!r}")
print(f"decode jpeg78:   {ok2!r}")
print(f"decode half+jpg: {ok3!r}")
assert ok1 and ok2 and ok3, "QR failed a stress test — raise contrast"
print("ALL SCANS PASS")

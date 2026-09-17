#!/usr/bin/env python
"""Reference-image preprocessing for the Hunyuan3D-2.1 MLX shape stage.

The MLX `ShapePipeline.preprocess_image` only does: composite RGBA on white ->
resize to 518 -> normalize to [-1,1]. It does NOT do the two steps upstream
Tencent's demo always performs before shape generation:

  1. background removal (hy3dshape/rembg.py::BackgroundRemover)
  2. `ImageProcessorV2.recenter(border_ratio=0.15)` - crop to the alpha
     bounding box and rescale so the subject fills 85% of the frame

Feeding an opaque studio-background photo straight to the MLX pipeline makes
it emit a flat "cutout" sheet (planarity ratio ~0.01) instead of a volumetric
body. This script reproduces upstream's preprocessing exactly, so the MLX
pipeline receives the same kind of input the model was trained/demoed on.

Steps (mirrors preprocessors.py::ImageProcessorV2):
  rembg -> recenter(border_ratio=0.15) -> resize 518 (DINOv2 patch-14 grid)
  -> composite over white -> RGB PNG

Usage:
    ~/venvs/hunyuan3d-mlx/bin/python prep_reference.py <in.png> <out.png>
"""

import sys

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove

IMAGE_SIZE = 518  # ImageEncoder.image_size: 37*14 = 518 -> 1370 tokens


def recenter(image: np.ndarray, border_ratio: float = 0.15) -> np.ndarray:
    """Crop to alpha bbox, rescale to (1-border_ratio) of frame, center.

    Faithful port of hy3dshape/preprocessors.py::ImageProcessorV2.recenter.
    """
    if image.shape[-1] == 4:
        mask = image[..., 3]
    else:
        raise ValueError("recenter expects an RGBA image")

    H, W, C = image.shape
    size = max(H, W)
    result = np.zeros((size, size, C), dtype=np.uint8)

    coords = np.nonzero(mask)
    x_min, x_max = coords[0].min(), coords[0].max()
    y_min, y_max = coords[1].min(), coords[1].max()
    h = x_max - x_min
    w = y_max - y_min
    if h == 0 or w == 0:
        raise ValueError("input image is empty")

    desired_size = int(size * (1 - border_ratio))
    scale = desired_size / max(h, w)
    h2 = int(h * scale)
    w2 = int(w * scale)
    x2_min = (size - h2) // 2
    y2_min = (size - w2) // 2

    result[x2_min:x2_min + h2, y2_min:y2_min + w2] = cv2.resize(
        image[x_min:x_max, y_min:y_max], (w2, h2),
        interpolation=cv2.INTER_AREA,
    )

    bg = np.ones((size, size, 3), dtype=np.uint8) * 255
    m = result[..., 3:].astype(np.float32) / 255
    composed = result[..., :3] * m + bg * (1 - m)
    return composed.clip(0, 255).astype(np.uint8)


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]

    rgba = remove(
        Image.open(src).convert("RGB"),
        session=new_session(),
        bgcolor=[255, 255, 255, 0],
    )
    rgba.save(dst.replace(".png", "_full.png"))
    print(f"rembg       -> {dst.replace('.png', '_full.png')} {rgba.size}")

    arr = np.asarray(rgba)
    print(f"opaque frac : {(arr[..., 3] > 128).mean():.4f}")

    composed = recenter(arr, border_ratio=0.15)
    composed = cv2.resize(composed, (IMAGE_SIZE, IMAGE_SIZE),
                          interpolation=cv2.INTER_CUBIC)
    Image.fromarray(composed).save(dst)
    print(f"recentered  -> {dst} ({IMAGE_SIZE}x{IMAGE_SIZE})")


if __name__ == "__main__":
    main()

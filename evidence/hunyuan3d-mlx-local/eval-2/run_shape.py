#!/usr/bin/env python
"""Stage 1 (shape generation) runner for dgrauet/hunyuan3d-2.1-mlx.

Why this wrapper exists
-----------------------
`from hy3dshape.pipeline_mlx import ShapePipeline` (the README quickstart)
fails on a torch-free install: importing the `hy3dshape` package executes
upstream `hy3dshape/hy3dshape/__init__.py`, which imports `.pipelines` ->
`import torch`, and `models/__init__.py` -> `.autoencoders` -> torch too.

The repo's CLAUDE.md imposes an "iso-upstream rule" (never modify upstream
PyTorch files), so instead of editing those __init__.py files we register
bare namespace-package stubs in sys.modules pointing at the real
directories. Their __init__.py is never executed, the *_mlx submodules
import unchanged, and no repo file is touched.

Usage:
    ~/venvs/hunyuan3d-mlx/bin/python run_shape.py <image> <out_dir>
"""

import importlib
import os
import resource
import sys
import time
import types

REPO = os.path.expanduser(os.environ.get("HUNYUAN3D_REPO", "~/tools/hunyuan3d-2.1-mlx"))
SHAPE_PKG_ROOT = os.path.join(REPO, "hy3dshape", "hy3dshape")

# Dotted package name -> path relative to the hy3dshape package root.
# These are exactly the packages whose __init__.py pulls in PyTorch.
_TORCH_FREE_STUBS = [
    ("hy3dshape", ""),
    ("hy3dshape.models", "models"),
    ("hy3dshape.models.autoencoders", "models/autoencoders"),
    ("hy3dshape.models.denoisers", "models/denoisers"),
    ("hy3dshape.utils", "utils"),
]

for _name, _rel in _TORCH_FREE_STUBS:
    _mod = types.ModuleType(_name)
    _mod.__path__ = [os.path.join(SHAPE_PKG_ROOT, _rel)]
    _mod.__package__ = _name
    sys.modules[_name] = _mod

sys.path.insert(0, os.path.join(REPO, "hy3dpaint"))

pipeline_mlx = importlib.import_module("hy3dshape.pipeline_mlx")
ShapePipeline = pipeline_mlx.ShapePipeline

assert "torch" not in sys.modules, "torch got imported - shim incomplete"


def peak_rss_gb() -> float:
    # ru_maxrss is bytes on macOS, KB on Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    image_path = sys.argv[1]
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    shape_glb = os.path.join(out_dir, "shape.glb")

    print(f"[Stage 1] image      : {image_path}")
    print(f"[Stage 1] output     : {shape_glb}")
    print(f"[Stage 1] weights    : dgrauet/hunyuan3d-2.1-mlx (fp16 default)")
    print(f"[Stage 1] peak RSS at start: {peak_rss_gb():.2f} GB")
    sys.stdout.flush()

    t0 = time.time()
    pipe = ShapePipeline.from_pretrained("dgrauet/hunyuan3d-2.1-mlx")
    t_load = time.time() - t0
    print(f"[Stage 1] pipeline ready in {t_load:.1f}s "
          f"(peak RSS {peak_rss_gb():.2f} GB)")
    sys.stdout.flush()

    t0 = time.time()
    mesh = pipe(
        image_path,
        num_inference_steps=50,
        guidance_scale=7.5,
        octree_resolution=256,
        seed=42,
    )
    t_infer = time.time() - t0
    print(f"[Stage 1] generated in {t_infer:.1f}s "
          f"({len(mesh.vertices)} verts, {len(mesh.faces)} faces)")
    print(f"[Stage 1] extents    : {mesh.extents}")
    print(f"[Stage 1] bounds     : {mesh.bounds.tolist()}")
    print(f"[Stage 1] watertight : {mesh.is_watertight}")
    print(f"[Stage 1] peak RSS   : {peak_rss_gb():.2f} GB")
    sys.stdout.flush()

    mesh.export(shape_glb)
    size_mb = os.path.getsize(shape_glb) / 1024 / 1024
    print(f"[Stage 1] saved      : {shape_glb} ({size_mb:.1f} MB)")
    print(f"[TIMING] shape load {t_load:.1f}s + infer {t_infer:.1f}s "
          f"= {t_load + t_infer:.1f}s total")


if __name__ == "__main__":
    main()

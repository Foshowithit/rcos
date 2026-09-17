#!/usr/bin/env python
"""Stage 2 (PBR texture synthesis) runner for dgrauet/hunyuan3d-2.1-mlx.

Fully-MLX path: HunyuanPaintModelMLX multiview diffusion + MLX RealESRGAN
super-resolution + the MLX Metal rasterizer/baker. No torch on this path
(`use_mlx_diffusion=True`, `use_mlx_super_res=True` are the defaults).

`use_remesh=True` decimates Stage 1's dense mesh to 40k faces first, which is
required: the Metal rasterizer can't handle ~500k faces at texture_size=4096.

Usage:
    ~/venvs/hunyuan3d-mlx/bin/python run_texture.py <mesh.glb> <ref.png> <out_dir>
"""

import os
import resource
import sys
import time

REPO = os.path.expanduser(os.environ.get("HUNYUAN3D_REPO", "~/tools/hunyuan3d-2.1-mlx"))
sys.path.insert(0, os.path.join(REPO, "hy3dpaint"))

from textureGenPipeline_mlx import (  # noqa: E402
    Hunyuan3DPaintConfigMLX,
    Hunyuan3DPaintPipelineMLX,
)

assert "torch" not in sys.modules, "torch got imported - MLX path should be torch-free"


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(2)
    mesh_path, image_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    out_obj = os.path.join(out_dir, "textured.obj")

    print(f"[Stage 2] mesh       : {mesh_path}")
    print(f"[Stage 2] reference  : {image_path}")
    print(f"[Stage 2] output     : {out_obj} (+ .glb)")
    sys.stdout.flush()

    cfg = Hunyuan3DPaintConfigMLX(max_num_view=6, resolution=512)
    print(f"[Stage 2] cfg: max_selected_view_num={cfg.max_selected_view_num} "
          f"resolution={cfg.resolution} "
          f"texture_size={cfg.texture_size} render_size={cfg.render_size} "
          f"mlx_diffusion={cfg.use_mlx_diffusion} mlx_superres={cfg.use_mlx_super_res}")
    sys.stdout.flush()

    t0 = time.time()
    pipe = Hunyuan3DPaintPipelineMLX(cfg)
    t_load = time.time() - t0
    print(f"[Stage 2] pipeline ready in {t_load:.1f}s "
          f"(peak RSS {peak_rss_gb():.2f} GB)")
    sys.stdout.flush()

    t0 = time.time()
    pipe(
        mesh_path=mesh_path,
        image_path=image_path,
        output_mesh_path=out_obj,
        use_remesh=True,
        save_glb=True,
    )
    t_tex = time.time() - t0
    print(f"[Stage 2] texture synthesized in {t_tex:.1f}s")
    print(f"[Stage 2] peak RSS   : {peak_rss_gb():.2f} GB")
    sys.stdout.flush()

    print("[TIMING] texture load %.1fs + synth %.1fs = %.1fs total"
          % (t_load, t_tex, t_load + t_tex))


if __name__ == "__main__":
    main()

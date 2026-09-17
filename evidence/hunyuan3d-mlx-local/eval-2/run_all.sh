#!/bin/zsh
# hunyuan3d-mlx-local eval-2: bearing mesh from muse-generated product shot.
# Serial MPS run. Deterministic gates checked in check_gates.py afterwards.
set -e
cd "$(dirname "$0")"
echo "== shape $(date +%H:%M:%S) =="
~/venvs/hunyuan3d-mlx/bin/python run_shape.py ref_518.png out_shape 2>&1 | tail -15
echo "== texture $(date +%H:%M:%S) =="
~/venvs/hunyuan3d-mlx/bin/python run_texture.py out_shape/*.glb ref_518.png out_tex 2>&1 | tail -15
echo "== done $(date +%H:%M:%S) =="
ls -la out_tex/ 2>/dev/null

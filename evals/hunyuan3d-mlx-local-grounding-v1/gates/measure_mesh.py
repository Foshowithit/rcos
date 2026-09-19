#!/usr/bin/env python
"""Measurement helper for the hunyuan3d-mlx-local-grounding-v1 gates.

Replicates the measurement the frozen scripts themselves print (trimesh
topology + GLB container facts) so the gates can cross-check the artifacts
independently of the adapter's header-only records. Spawned by gates/check.js
through the SAME pinned interpreter the chain ran on; the interpreter is
environment, the pinned VALUES live in check.js.

Usage: measure_mesh.py <file.glb>
Prints one JSON line:
  {verts, faces, watertight, extents, bounds,
   glb: {version, json_bytes, asset_version, generator, meshes, images}}
"""

import json
import struct
import sys

import trimesh


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    path = sys.argv[1]
    with open(path, "rb") as f:
        b = f.read()
    if len(b) < 20 or b[:4] != b"glTF":
        raise SystemExit(3)
    version = struct.unpack("<I", b[4:8])[0]
    json_bytes = struct.unpack("<I", b[12:16])[0]
    doc = json.loads(b[20:20 + json_bytes].decode("utf8"))
    mesh = trimesh.load(path, force="mesh", process=False)
    asset = doc.get("asset", {})
    print(json.dumps({
        "verts": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "extents": [float(x) for x in mesh.extents],
        "bounds": [[float(x) for x in row] for row in mesh.bounds],
        "glb": {
            "version": version,
            "json_bytes": json_bytes,
            "asset_version": asset.get("version"),
            "generator": asset.get("generator"),
            "meshes": len(doc.get("meshes", [])),
            "images": len(doc.get("images", [])),
        },
    }))


if __name__ == "__main__":
    main()

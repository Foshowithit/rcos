#!/usr/bin/env python3
"""muse-image-lane eval-2: bearing product shot (real consumer: John's bearing
assets + hunyuan3d-mlx-local eval-2 reference chain). Key read from vault,
never logged."""
import base64, json, sys, urllib.request

KEY = open("/Users/adam26/.agent-vault/keys/meta-muse.key").read().strip()
PROMPT = ("Studio product photograph of a single deep-groove ball bearing, "
          "standing upright facing camera, brushed steel with visible balls "
          "and cage, soft studio lighting, plain light gray seamless background, "
          "centered composition, professional product photography, sharp focus, high detail")
req = urllib.request.Request(
    "https://api.meta.ai/v1/images/generations",
    data=json.dumps({"model": "muse-image-1.0", "prompt": PROMPT, "size": "1024x1024"}).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
)
r = json.load(urllib.request.urlopen(req, timeout=300))
raw = base64.b64decode(r["data"][0]["b64_json"])
open("bearing_raw.png", "wb").write(raw)
print(f"saved bearing_raw.png ({len(raw)} bytes)")

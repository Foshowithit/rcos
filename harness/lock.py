#!/usr/bin/env python3
"""H3 CAPABILITY_LOCK enforcement: promotion writes once, downstream is
read-only. The loader resolves by exact hash, verifies bytes
pre-execution, and refuses on any mismatch. Stdlib only.
"""
import hashlib
import json
import os
import time


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def promote(out_dir, capability_id, version, artifact_paths,
            manifest_obj, training_receipts, builder_identity):
    """Write an immutable CAPABILITY_LOCK. Returns path. Fails if the
    lock file already exists (promotion writes once; no repromotion)."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "CAPABILITY_LOCK.json")
    if os.path.exists(path):
        raise PermissionError("LOCK-DENY lock already exists (no repromotion)")
    art = {}
    for p in sorted(artifact_paths):
        art[os.path.basename(p)] = _sha(p)
    lock = {"capability_id": capability_id, "version": version,
            "artifacts": art,
            "manifest_sha256": hashlib.sha256(
                json.dumps(manifest_obj, sort_keys=True).encode()).hexdigest(),
            "manifest": manifest_obj,
            "training_receipts": list(training_receipts),
            "builder_identity": dict(builder_identity),
            "locked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(path, "w") as f:
        json.dump(lock, f, indent=1)
    return path


def load_artifact(lock_path, artifact_name, dest_dir):
    """Resolve ONE artifact by exact locked hash from a source tree.
    `dest_dir` must contain a same-named file whose bytes hash to the
    locked value; returns the verified path. Refuses otherwise.
    (The source tree is the harness-controlled capability store —
    callers never supply artifact bytes directly.)"""
    lock = json.load(open(lock_path))
    want = lock["artifacts"].get(artifact_name)
    if want is None:
        raise PermissionError(
            f"LOCK-DENY {artifact_name!r} not in lock "
            f"{lock.get('capability_id')}")
    cand = os.path.join(dest_dir, artifact_name)
    if not os.path.exists(cand):
        raise PermissionError(f"LOCK-DENY artifact absent: {cand}")
    if _sha(cand) != want:
        raise PermissionError(
            f"LOCK-DENY hash mismatch for {artifact_name}: locked "
            f"{want[:12]} vs present {_sha(cand)[:12]}")
    return cand

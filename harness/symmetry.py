#!/usr/bin/env python3
"""H1 context symmetry: treatment/control bundles differ ONLY by the
capability-access block. Canonical JSON + sha256; mechanical diff.
Stdlib only.
"""
import hashlib
import json


def build_context(task_id, task_text, tools, capability_block=None):
    """capability_block None = control arm. Returns (bundle_dict, sha)."""
    bundle = {"task_id": task_id, "task_text": task_text,
              "tools": sorted(tools), "capability_access": capability_block}
    blob = json.dumps(bundle, sort_keys=True)
    return bundle, hashlib.sha256(blob.encode()).hexdigest()


def diff_contexts(treatment, control):
    """Returns [] iff the ONLY difference is the capability block."""
    t = dict(treatment)
    c = dict(control)
    if t.pop("capability_access", None) is None:
        return ["treatment lacks capability_access block"]
    if "capability_access" in c and c.pop("capability_access") is not None:
        return ["control unexpectedly carries capability_access"]
    if t != c:
        keys = sorted(set(t) | set(c))
        return [f"non-capability difference in fields: "
                f"{[k for k in keys if t.get(k) != c.get(k)]}"]
    return []

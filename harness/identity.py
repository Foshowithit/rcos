#!/usr/bin/env python3
"""H2 provider/model identity capture. Identity is established
provider-side (endpoint + requested id + echoed id/version + request
ids), never by model self-report. Records failing validation do not
count toward any gate. Stdlib only.
"""
import json
import os
import time


def record_identity(out_dir, endpoint, model_requested, response_obj,
                    extra_params=None, tag=""):
    """response_obj: parsed provider JSON. Extracts echoed identity.
    Returns path. Raises on missing identity evidence (fail closed)."""
    rec = {"endpoint": endpoint, "model_requested": model_requested,
           "tag": tag,
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "params": dict(extra_params or {})}
    for key in ("model", "created"):
        if key in response_obj:
            rec["model_echoed_" + key] = response_obj[key]
    if "id" in response_obj:
        rec["provider_response_id"] = response_obj["id"]
    if "model_echoed_model" not in rec:
        raise ValueError("IDENTITY-INCOMPLETE: provider echoed no model id")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "identity.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=1)
    return path


def check_distinct_families(id_a, id_b):
    """Gate helper: two identity records count as distinct families iff
    endpoints differ AND echoed model ids differ (case-insensitive).
    Self-reported names inside completion text are inadmissible."""
    ea = json.load(open(id_a))
    eb = json.load(open(id_b))
    return (ea["endpoint"].lower() != eb["endpoint"].lower()
            and ea["model_echoed_model"].lower()
            != eb["model_echoed_model"].lower())

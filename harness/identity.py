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


def check_against_prereg(identity_path, prereg_entry):
    """Verify a provider receipt against a PREREGISTERED identity entry:
    {provider, endpoint, requested_id, acceptable_echoed_ids (list of
    exact ids or prefix patterns ending in *), family}. Returns the
    family string on match; raises otherwise. Family distinction lives
    in preregistration, never in endpoint-string heuristics."""
    rec = json.load(open(identity_path))
    problems = []
    if rec.get("endpoint", "").lower() != prereg_entry["endpoint"].lower():
        problems.append("endpoint mismatch")
    if rec.get("model_requested") != prereg_entry["requested_id"]:
        problems.append("requested-id mismatch")
    echoed = str(rec.get("model_echoed_model", ""))
    pats = prereg_entry.get("acceptable_echoed_ids", [])
    def _hit(pat):
        return echoed == pat if not pat.endswith("*") else echoed.startswith(pat[:-1])
    if not any(_hit(p) for p in pats):
        problems.append(f"echoed id {echoed!r} matches no acceptable pattern")
    if problems:
        raise ValueError("IDENTITY-PREREG-MISMATCH: " + "; ".join(problems))
    return prereg_entry["family"]

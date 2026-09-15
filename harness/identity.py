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
                    extra_params=None, tag="", request_body_sha256=None,
                    messages=None):
    """response_obj: parsed provider JSON. Extracts echoed identity.
    Returns path. Raises on missing identity evidence (fail closed).

    Item-3 hardening (audit round 2): BOTH the echoed model id AND a
    nonempty provider response/request id are REQUIRED — our OpenAI-chat
    lanes always supply one, so a missing/empty id is missing evidence,
    never a schema variant (a genuinely id-less endpoint needs a prereg
    amendment, never a silent omission). The exact request-body hash from
    the usage receipt (request_body_sha256) is REQUIRED and stored, along
    with the COMPLETE explicit generation-param set as passed — so a
    later alteration of model/params on either side breaks the binding
    (see verify_identity_binding)."""
    rec = {"endpoint": endpoint, "model_requested": model_requested,
           "tag": tag,
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "params": dict(extra_params or {}),
           "generation_params": dict(extra_params or {})}
    for key in ("model", "created"):
        if key in response_obj:
            rec["model_echoed_" + key] = response_obj[key]
    if "id" in response_obj:
        rec["provider_response_id"] = response_obj["id"]
    if "model_echoed_model" not in rec:
        raise ValueError("IDENTITY-INCOMPLETE: provider echoed no model id")
    pid = rec.get("provider_response_id")
    if not isinstance(pid, str) or not pid.strip():
        raise ValueError("IDENTITY-INCOMPLETE: provider response/request id "
                         "missing or empty (required when the endpoint "
                         "supplies one; OpenAI-chat lanes always do)")
    if not isinstance(request_body_sha256, str) or not request_body_sha256:
        raise ValueError("IDENTITY-INCOMPLETE: request_body_sha256 missing "
                         "(record from the usage receipt at call time)")
    rec["request_body_sha256"] = request_body_sha256
    if messages is not None:
        # A11.2: bind the exact prompt/context bytes too, so the request
        # body verifier can prove messages identity == messages on the wire.
        import hashlib as _hl
        rec["messages_sha256"] = _hl.sha256(
            json.dumps(messages, sort_keys=True).encode()).hexdigest()
        rec["messages_count"] = len(messages)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "identity.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=1)
    return path


def verify_identity_binding(identity_path, receipt_path):
    """Cross-verify one identity record against its usage receipt. Raises
    ValueError (fail closed) on ANY divergence; returns the identity dict
    otherwise. Checks: endpoint equality, model_requested equality,
    request-body hash present on both sides and equal, echoed model
    nonempty, provider response id nonempty. Altering the model or any
    request param on the receipt side changes the receipt (and breaks the
    normalized file binding); altering them on the identity side breaks
    this cross-check — either way the chain/admissibility gate fails."""
    try:
        rec = json.load(open(identity_path))
    except (OSError, ValueError) as e:
        raise ValueError(f"IDENTITY-BINDING-UNREADABLE {identity_path}: {e}")
    try:
        rc = json.load(open(receipt_path))
    except (OSError, ValueError) as e:
        raise ValueError(f"IDENTITY-BINDING-UNREADABLE {receipt_path}: {e}")
    problems = []
    if rec.get("endpoint") != rc.get("endpoint"):
        problems.append(f"endpoint {rec.get('endpoint')!r} != "
                        f"receipt {rc.get('endpoint')!r}")
    if rec.get("model_requested") != rc.get("model_requested"):
        problems.append(f"model_requested {rec.get('model_requested')!r} != "
                        f"receipt {rc.get('model_requested')!r}")
    if not rc.get("request_body_sha256"):
        problems.append("receipt has no request_body_sha256")
    elif rec.get("request_body_sha256") != rc.get("request_body_sha256"):
        problems.append("request_body_sha256 diverges (model/request "
                        "params altered after receipt)")
    if not rec.get("model_echoed_model"):
        problems.append("echoed model id stripped")
    if not isinstance(rec.get("provider_response_id"), str) or \
            not rec.get("provider_response_id", "").strip():
        problems.append("provider response/request id stripped")
    if problems:
        raise ValueError("IDENTITY-BINDING-MISMATCH "
                         f"{identity_path} vs {receipt_path}: "
                         + "; ".join(problems))
    return rec


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

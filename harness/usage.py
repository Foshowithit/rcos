#!/usr/bin/env python3
"""H2 usage accounting: raw provider usage capture, never reconstructed.
Every model call goes through recorded_call(); the RAW usage block from
the provider response is persisted verbatim alongside call metadata.
Metrics derive ONLY from these records. A run missing usage for any
model call is invalid — estimation is forbidden. Stdlib only.
"""
import hashlib
import json
import os
import time
import urllib.request

# Frozen normalizer: provider-reported usage -> normalized primary work.
# Versioned + hashed so derivations are reproducible and auditable.
# Wording discipline: primary work is CALCULATED FROM provider-reported
# uncached-input and output usage under this frozen rule — never
# "independently measured token work". Providers own their tokenization,
# caching, hidden transformations, and billing semantics.
NORMALIZER_VERSION = "usage-norm-v1"
NORMALIZER_RULE = ("primary_work = input_tokens_uncached + output_tokens; "
                   "cached tokens retained separately, never zeroed, "
                   "never mixed into uncached")

# Adapters are FROZEN provider-schema contracts keyed by preregistered
# adapter id — never inferred from field presence at runtime. The real
# P/Q providers (router9/MiniMax, kenari/Agnes) answer OpenAI Chat
# Completions shape: usage.prompt_tokens is the TOTAL prompt input
# (cache included), completion_tokens the output, and the cached subset
# lives at prompt_tokens_details.cached_tokens (absent when none).
# A provider with a different raw schema requires a NEW RAW_SCHEMAS
# entry plus a preregistered adapter id — never field-guessing here.
RAW_SCHEMAS = {
    # Canonical OpenAI Chat Completions usage block.
    "openai-chat-completions": {
        "input_total": ("prompt_tokens",),            # prompt incl. cache
        "output": ("completion_tokens",),
        "cached": ("prompt_tokens_details", "cached_tokens"),  # absent -> 0
        "total": ("total_tokens",),                   # optional consistency
    },
}

PROVIDER_NORMALIZERS = {
    # ------------------------------------------------------------------
    # v1 adapters — HISTORICAL RECEIPTS ONLY (audit round 2, A1). The H1
    # harness-validation receipts carry these ids; retaining the entries
    # keeps normalization of those records reproducible. They are
    # SUPERSEDED for NEW calls by the provider-bound v2 ids below — a new
    # call must declare the v2 id preregistered for its lane.
    # prompt_tokens reported as TOTAL prompt input (cache included):
    # uncached = prompt_tokens - prompt_tokens_details.cached_tokens.
    "openai-chat-total-input-v1": {"raw_schema": "openai-chat-completions",
                                   "input_includes_cache": True},
    # prompt_tokens reported already uncached (provider-side caching off):
    # uncached = prompt_tokens as reported; any cached detail kept separate.
    "openai-chat-uncached-input-v1": {"raw_schema": "openai-chat-completions",
                                      "input_includes_cache": False},
    # ------------------------------------------------------------------
    # v2 provider-bound adapters (A1, audit round 2 item 1). Each id is
    # preregistered for exactly ONE lane's gateway + model family: the id
    # IS the lane binding, so a receipt declaring router9-openai-chat-v2
    # cannot be swapped onto the kenari lane and vice versa
    # (summarize() enforces the prereg mapping by model_requested). Old v1
    # ids are NOT reinterpreted in place — historical receipts stay on the
    # id they were recorded under (they are excluded from the estimand
    # surface anyway; harness-validation only).
    "router9-openai-chat-v2": {
        "raw_schema": "openai-chat-completions",
        "input_includes_cache": True,
        "bound": {"lane": "P", "provider": "router9",
                  "model_family": "MiniMax",
                  "gateway_model": "minimax-m3",
                  "endpoint_base": "https://api.router9.com/v1"},
        "supersedes": "openai-chat-total-input-v1",
        "cache_semantics": ("prompt_tokens is TOTAL prompt input (cache "
                            "included); uncached = prompt_tokens - "
                            "prompt_tokens_details.cached_tokens")},
    "kenari-openai-chat-v2": {
        "raw_schema": "openai-chat-completions",
        "input_includes_cache": True,
        "bound": {"lane": "Q", "provider": "kenari",
                  "model_family": "Kenari-Agnes",
                  "gateway_model": "agnes-2-0-flash:free",
                  "endpoint_base": "https://kenari.id/v1"},
        "supersedes": "openai-chat-total-input-v1",
        "cache_semantics": ("prompt_tokens is TOTAL prompt input (cache "
                            "included); uncached = prompt_tokens - "
                            "prompt_tokens_details.cached_tokens")},
}



def recorded_call(endpoint, api_key_name, api_key, model, messages,
                  out_dir, extra_body=None, timeout=300, tag="",
                  normalizer_id="openai-chat-total-input-v1",
                  return_response=False):
    """POST a chat-completions call, persist raw usage + metadata.
    Returns (reply_text, receipt_path); with return_response=True also
    returns the parsed provider response object as a third element, so
    caller-side identity capture (echoed model, response id) can run on
    the REAL provider object — never on reply-text self-report. Raises
    on transport/HTTP error (infrastructure outcome, recorded by caller
    — never silently retried for judgment reasons here)."""
    body = dict(extra_body or {})
    body.update({"model": model, "messages": messages})
    blob = json.dumps(body).encode()
    t0 = time.time()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions", data=blob,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        status = resp.status
        data = json.load(resp)
    except Exception as e:
        raise RuntimeError(f"USAGE-CALL-FAIL {endpoint} {model}: "
                           f"{type(e).__name__} {str(e)[:200]}")
    wall = time.time() - t0
    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"USAGE-MALFORMED {endpoint} {model}: {e}")
    # Provenance layer: raw block + its hash travel with every receipt.
    # Normalization is a separate, versioned, reproducible step below.
    import hashlib as _hl
    raw_hash = _hl.sha256(json.dumps(
        data.get("usage"), sort_keys=True).encode()).hexdigest() \
        if data.get("usage") is not None else None
    os.makedirs(out_dir, exist_ok=True)
    call_id = hashlib.sha256(
        f"{endpoint}|{model}|{t0:.3f}|{reply[:64]}".encode()).hexdigest()[:16]
    # Request-body binding: sha256 of the EXACT bytes POSTed (model +
    # messages + every explicit generation param). Persisted at record time
    # so later tampering of any request field (model/params/messages) breaks
    # the binding (identity + normalized-usage verifiers recompute it).
    request_body_sha256 = hashlib.sha256(blob).hexdigest()
    receipt = {"call_id": call_id, "tag": tag, "endpoint": endpoint,
               "model_requested": model, "wall_s": round(wall, 2),
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "request_body_sha256": request_body_sha256,
               "usage_raw": data.get("usage"),
               "usage_raw_sha256": raw_hash,
               "normalizer_id": normalizer_id,
               "normalizer_version": NORMALIZER_VERSION,
               "normalizer_rule": NORMALIZER_RULE}
    path = os.path.join(out_dir, f"call-{call_id}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=1)
    if return_response:
        return reply, path, data
    return reply, path


def _opt_int(u, path):
    """Optional declared raw-schema field by dotted path.
    Absent -> None; present-but-invalid -> raise (fail closed)."""
    node = u
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if not isinstance(node, int) or isinstance(node, bool) or node < 0:
        raise ValueError(f"USAGE-INCOMPLETE: {'.'.join(path)!r} invalid")
    return node


def _req_int(u, path):
    v = _opt_int(u, path)
    if v is None:
        raise ValueError(
            f"USAGE-INCOMPLETE: {'.'.join(path)!r} missing "
            "(estimation forbidden)")
    return v


def normalize_usage(receipt, normalizer_id):
    """Frozen provider-schema adapter -> primary work.
    The adapter id declares BOTH the raw schema it consumes and its cache
    semantics. Unknown/undeclared adapter FAILS (no runtime field
    guessing). Verifies raw usage hash before trusting usage_raw."""
    if normalizer_id not in PROVIDER_NORMALIZERS:
        raise ValueError(f"USAGE-NORMALIZER-UNKNOWN: {normalizer_id}")
    cfg = PROVIDER_NORMALIZERS[normalizer_id]
    u = receipt.get("usage_raw")
    if not isinstance(u, dict):
        raise ValueError("USAGE-INCOMPLETE: usage_raw absent/non-object")
    import hashlib as _hl
    raw_hash = _hl.sha256(json.dumps(u, sort_keys=True).encode()).hexdigest()
    if receipt.get("usage_raw_sha256") != raw_hash:
        raise ValueError("USAGE-TAMPER: usage_raw_sha256 mismatch")
    sch = RAW_SCHEMAS[cfg["raw_schema"]]
    total_in = _req_int(u, sch["input_total"])
    output = _req_int(u, sch["output"])
    cached = _opt_int(u, sch["cached"]) or 0
    if "total" in sch:
        tot = _opt_int(u, sch["total"])
        if tot is not None and tot != total_in + output:
            raise ValueError("USAGE-INCONSISTENT: total != input + output")
    if cfg["input_includes_cache"]:
        if cached > total_in:
            raise ValueError("USAGE-INCONSISTENT: cached > total input")
        uncached = total_in - cached
    else:
        uncached = total_in
    notes = []
    if cfg["input_includes_cache"] is False and cached:
        notes.append("cached detail present under uncached-input adapter; "
                     "retained separately, never subtracted")
    return {"input_tokens_uncached": uncached,
            "output_tokens": output,
            "cached_tokens": cached,
            "primary_work": uncached + output,
            "normalizer_id": normalizer_id,
            "normalizer_version": NORMALIZER_VERSION,
            "normalizer_notes": notes}


def summarize(receipt_paths, normalizer_map):
    """Derive metrics SOLELY from persisted raw usage blocks. normalizer_map
    (required, from preregistration) maps model_requested -> normalizer_id.
    Each receipt's stored normalizer_id must equal the mapped value: no
    analyst override at analysis time, so one raw receipt cannot yield two
    primary-work numbers. Raises otherwise (fail closed)."""
    tot_in = tot_out = tot_cached = 0
    n = 0
    cached_detail = []
    for p in receipt_paths:
        r = json.load(open(p))
        want = normalizer_map.get(r.get("model_requested"))
        if want is None:
            raise ValueError(f"USAGE-NOMAP {p}: model {r.get('model_requested')!r} "
                             f"has no preregistered normalizer")
        if r.get("normalizer_id") != want:
            raise ValueError(f"USAGE-ADAPTER-MISMATCH {p}: receipt declares "
                             f"{r.get('normalizer_id')!r}, prereg requires {want!r}")
        try:
            nu = normalize_usage(r, want)
        except ValueError as e:
            raise ValueError(f"USAGE-INCOMPLETE {p}: {e} (estimation forbidden)")
        tot_in += nu["input_tokens_uncached"]
        tot_out += nu["output_tokens"]
        tot_cached += nu["cached_tokens"]
        cached_detail.append(nu["cached_tokens"])
        n += 1
    return {"model_calls": n, "input_tokens_uncached": tot_in,
            "output_tokens": tot_out, "cached_tokens": tot_cached,
            "cached_detail_per_call": cached_detail}


# ---------------------------------------------------------------------------
# A1 (audit round 2 item 1): immutable per-call normalized-usage artifact.
# Normalization is part of CALL CAPTURE, never a post-hoc analysis step: the
# runner writes it immediately after every recorded_call, then binds its hash
# + derived metrics into the model-call chain link. The artifact co-locates
# with its raw receipt: call-<id>.json -> call-<id>.normalized.json.
# ---------------------------------------------------------------------------

def _serialize(obj):
    """Deterministic serialization: the exact bytes written/verified."""
    return json.dumps(obj, sort_keys=True, indent=1, separators=(",", ": "))


def write_normalized_usage(receipt_path, expect_normalizer_id=None):
    """Persist the immutable normalized-usage artifact beside the raw receipt.

    Derives from receipt_path (call-<id>.json -> call-<id>.normalized.json).
    Verifies the raw usage block against its recorded hash (normalize_usage
    raises on missing/mismatched schema — fail closed), binds to the whole
    receipt FILE bytes (raw_receipt_sha256), and stamps its own
    normalized_sha256 over the exact serialized bytes on disk.

    Immutability: writes once. A later identical rewrite is a no-op returning
    the existing path; any conflicting existing artifact raises (overwrite
    refused). Returns the artifact path.
    """
    rc = json.load(open(receipt_path))
    nid = rc.get("normalizer_id")
    if not nid:
        raise ValueError(f"USAGE-INCOMPLETE {receipt_path}: receipt has no "
                         "normalizer_id")
    if expect_normalizer_id is not None and nid != expect_normalizer_id:
        raise ValueError(f"USAGE-ADAPTER-MISMATCH {receipt_path}: receipt "
                         f"declares {nid!r}, prereg requires "
                         f"{expect_normalizer_id!r}")
    nu = normalize_usage(rc, nid)  # raises USAGE-* on tamper/incomplete/unknown
    if not receipt_path.endswith(".json"):
        raise ValueError(f"USAGE-INCOMPLETE {receipt_path}: receipt must end "
                         "in .json")
    path = receipt_path[:-5] + ".normalized.json"
    raw_file_sha = hashlib.sha256(
        open(receipt_path, "rb").read()).hexdigest()
    payload = {"call_id": rc.get("call_id"),
               "model_requested": rc.get("model_requested"),
               "endpoint": rc.get("endpoint"),
               "normalizer_id": nid,
               "normalizer_version": nu["normalizer_version"],
               "normalizer_rule": NORMALIZER_RULE,
               "input_tokens_uncached": nu["input_tokens_uncached"],
               "output_tokens": nu["output_tokens"],
               "cached_tokens": nu["cached_tokens"],
               "primary_work": nu["primary_work"],
               "raw_receipt_file": os.path.basename(receipt_path),
               "raw_receipt_sha256": raw_file_sha}
    stripped = dict(payload)
    payload["normalized_sha256"] = hashlib.sha256(
        _serialize(stripped).encode()).hexdigest()
    content = _serialize(payload)
    if os.path.exists(path):
        if open(path).read() == content:
            return path  # idempotent identical rewrite: no-op
        raise RuntimeError(f"USAGE-NORMALIZED-CONFLICT {path}: artifact "
                           "exists with different bytes (immutable; "
                           "overwrite refused)")
    with open(path, "w") as f:
        f.write(content)
    return path


def verify_normalized_usage(nu_path):
    """Recompute a normalized-usage artifact end-to-end. Raises ValueError on
    ANY mismatch (fail closed); returns the verified dict otherwise. Checks:
      1. self-sha: artifact bytes unaltered since write (normalized_sha256);
      2. binding: bound raw receipt file exists and its FILE sha equals
         raw_receipt_sha256 — tampering ANY raw receipt field (usage block,
         model, endpoint, params) breaks the artifact;
      3. re-derivation: normalize_usage over the raw usage block reproduces
         every metric field + normalizer id exactly.
    """
    if not os.path.exists(nu_path):
        raise ValueError(f"USAGE-NORMALIZED-MISSING {nu_path}")
    payload = json.load(open(nu_path))
    stripped = {k: v for k, v in payload.items() if k != "normalized_sha256"}
    if payload.get("normalized_sha256") != hashlib.sha256(
            _serialize(stripped).encode()).hexdigest():
        raise ValueError(f"USAGE-TAMPER {nu_path}: normalized artifact bytes "
                         "altered post-write (self-sha mismatch)")
    raw_name = payload.get("raw_receipt_file")
    raw = os.path.join(os.path.dirname(nu_path), raw_name or "")
    if not raw_name or not os.path.exists(raw):
        raise ValueError(f"USAGE-INCOMPLETE {nu_path}: bound raw receipt "
                         f"{raw_name!r} missing")
    if payload.get("raw_receipt_sha256") != hashlib.sha256(
            open(raw, "rb").read()).hexdigest():
        raise ValueError(f"USAGE-TAMPER {nu_path}: raw receipt file altered "
                         "post-write (file-binding broken)")
    rc = json.load(open(raw))
    recomputed = normalize_usage(rc, rc.get("normalizer_id"))
    if payload.get("normalizer_id") != recomputed.get("normalizer_id"):
        raise ValueError(f"USAGE-TAMPER {nu_path}: normalizer_id altered")
    for k in ("input_tokens_uncached", "output_tokens", "cached_tokens",
              "primary_work"):
        if payload.get(k) != recomputed.get(k):
            raise ValueError(f"USAGE-TAMPER {nu_path}: {k} "
                             f"{payload.get(k)!r} != re-derived "
                             f"{recomputed.get(k)!r}")
    return payload

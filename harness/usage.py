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
    # prompt_tokens reported as TOTAL prompt input (cache included):
    # uncached = prompt_tokens - prompt_tokens_details.cached_tokens.
    "openai-chat-total-input-v1": {"raw_schema": "openai-chat-completions",
                                   "input_includes_cache": True},
    # prompt_tokens reported already uncached (provider-side caching off):
    # uncached = prompt_tokens as reported; any cached detail kept separate.
    "openai-chat-uncached-input-v1": {"raw_schema": "openai-chat-completions",
                                      "input_includes_cache": False},
}



def recorded_call(endpoint, api_key_name, api_key, model, messages,
                  out_dir, extra_body=None, timeout=300, tag="",
                  normalizer_id="openai-chat-total-input-v1"):
    """POST a chat-completions call, persist raw usage + metadata.
    Returns (reply_text, receipt_path). Raises on transport/HTTP error
    (infrastructure outcome, recorded by caller — never silently retried
    for judgment reasons here)."""
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
    receipt = {"call_id": call_id, "tag": tag, "endpoint": endpoint,
               "model_requested": model, "wall_s": round(wall, 2),
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "usage_raw": data.get("usage"),
               "usage_raw_sha256": raw_hash,
               "normalizer_id": normalizer_id,
               "normalizer_version": NORMALIZER_VERSION,
               "normalizer_rule": NORMALIZER_RULE}
    path = os.path.join(out_dir, f"call-{call_id}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=1)
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

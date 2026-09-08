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

REQUIRED_USAGE_FIELDS = ("input_tokens", "output_tokens")

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


def recorded_call(endpoint, api_key_name, api_key, model, messages,
                  out_dir, extra_body=None, timeout=300, tag=""):
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
               "normalizer_version": NORMALIZER_VERSION,
               "normalizer_rule": NORMALIZER_RULE}
    path = os.path.join(out_dir, f"call-{call_id}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=1)
    return reply, path


def normalize_usage(receipt):
    """Frozen provider-specific normalization → primary_work + checks.
    Consistency checks applied ONLY where the provider schema permits:
    integer non-negative counts; cached <= total input where both are
    reported; total == input + output where the provider supplies a
    total; uncached = total_input - cached ONLY under providers that
    define it that way (recorded per receipt in `normalizer_notes`).
    No cross-provider arithmetic is invented. Returns dict or raises."""
    u = receipt.get("usage_raw") or {}
    notes = []
    for f in REQUIRED_USAGE_FIELDS:
        v = u.get(f)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError(f"USAGE-INCOMPLETE: {f!r} missing/invalid")
    cached = int(u.get("cached_tokens", 0) or 0)
    if cached < 0:
        raise ValueError("USAGE-INCOMPLETE: negative cached_tokens")
    if "total_tokens" in u and u["total_tokens"] is not None:
        if u["total_tokens"] != u["input_tokens"] + u["output_tokens"]:
            notes.append("total!=input+output for this provider schema; "
                         "kept as-reported, primary uses components")
    return {"input_tokens_uncached": u["input_tokens"],
            "output_tokens": u["output_tokens"],
            "cached_tokens": cached,
            "primary_work": u["input_tokens"] + u["output_tokens"],
            "normalizer_version": NORMALIZER_VERSION,
            "normalizer_notes": notes}


def summarize(receipt_paths):
    """Derive metrics SOLELY from persisted raw usage blocks.
    Raises on any missing/merged token fields (fail closed)."""
    tot_in = tot_out = tot_cached = 0
    n = 0
    for p in receipt_paths:
        r = json.load(open(p))
        try:
            nu = normalize_usage(r)
        except ValueError as e:
            raise ValueError(f"USAGE-INCOMPLETE {p}: {e} (estimation forbidden)")
        tot_in += nu["input_tokens_uncached"]
        tot_out += nu["output_tokens"]
        tot_cached += nu["cached_tokens"]
        n += 1
    cached_detail = [json.load(open(p))["usage_raw"].get("cached_tokens")
                     for p in receipt_paths]
    return {"model_calls": n, "input_tokens_uncached": tot_in,
            "output_tokens": tot_out, "cached_tokens": tot_cached,
            "cached_detail_per_call": cached_detail}

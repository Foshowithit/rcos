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
    # Persist even usage-less responses: the receipt documents the gap
    # and summarize() refuses to derive from it (fail closed, auditable).
    usage_raw = data.get("usage")
    os.makedirs(out_dir, exist_ok=True)
    call_id = hashlib.sha256(
        f"{endpoint}|{model}|{t0:.3f}|{reply[:64]}".encode()).hexdigest()[:16]
    receipt = {"call_id": call_id, "tag": tag, "endpoint": endpoint,
               "model_requested": model, "wall_s": round(wall, 2),
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "usage_raw": usage_raw}
    path = os.path.join(out_dir, f"call-{call_id}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=1)
    return reply, path


def summarize(receipt_paths):
    """Derive metrics SOLELY from persisted raw usage blocks.
    Raises on any missing/merged token fields (fail closed)."""
    tot_in = tot_out = tot_cached = 0
    n = 0
    for p in receipt_paths:
        r = json.load(open(p))
        u = r.get("usage_raw") or {}
        for f in REQUIRED_USAGE_FIELDS:
            if f not in u or not isinstance(u[f], int) or isinstance(u[f], bool):
                raise ValueError(
                    f"USAGE-INCOMPLETE {p}: missing/invalid {f!r} "
                    f"(estimation forbidden)")
        tot_in += u["input_tokens"]
        tot_out += u["output_tokens"]
        tot_cached += int(u.get("cached_tokens", 0) or 0)
        n += 1
    cached_detail = [json.load(open(p))["usage_raw"].get("cached_tokens")
                     for p in receipt_paths]
    return {"model_calls": n, "input_tokens_uncached": tot_in,
            "output_tokens": tot_out, "cached_tokens": tot_cached,
            "cached_detail_per_call": cached_detail}

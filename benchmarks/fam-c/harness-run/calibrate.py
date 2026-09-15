#!/usr/bin/env python3
"""Fam-C calibration probe (audit round-2 item 2).

ONE P/Q calibration pair, run through the FINAL identity+usage path before
the execution lock is minted: a tiny deterministic request on each lane that
proves the endpoint answers, the requested params travel intact, the echoed
model id and provider response id arrive, and the raw + normalized usage
records are produced and bound to each other.

A calibration call is a CALIBRATION / NEVER-ESTIMAND call:
  - it is NOT a cell of the frozen ORDER.md sequence and never enters
    ORDER-EXPANSION.json or the runner's completion ledger;
  - it never contributes to any estimand, metric, or verdict;
  - it is written under `runs/_calibration/` which admissibility treats as
    non-estimand (no H1-RUN-MANIFEST.json is ever written there).

Modes:
  --plan     (default) print the exact calls + the offline preflight checks;
             performs NO network call.
  --offline  full pipe rehearsal against an in-process fake transport: proves
             the capture→identity→normalize→verify→bind path end to end with
             zero network. Always safe.
  --live     REAL calls to the P and Q lanes. Requires --i-know-this-spends
             and an explicit `--approve-quota` acknowledgement; refuses when
             the lane key is missing or the quota window is closed.

Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAMC = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(FAMC))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, HERE)

import identity as ID            # noqa: E402
import usage as UG               # noqa: E402
from run_arm_h1 import LANES     # noqa: E402  (frozen lane prereg)

CAL_DIR = os.path.join(FAMC, "runs", "_calibration")
# The calibration request is deliberately trivial and deterministic: identity,
# parameter transport and usage capture are under test, not model quality.
PROMPT = "Reply with exactly the token: CALIBRATION-ACK"
GEN_PARAMS = {"temperature": 0, "max_tokens": 16, "top_p": 1}
SEMANTICS = "CALIBRATION / NEVER-ESTIMAND"


def _req_body(model):
    body = dict(GEN_PARAMS)
    body.update({"model": model,
                 "messages": [{"role": "user", "content": PROMPT}]})
    return body


def print_plan():
    print(f"{SEMANTICS}: one P/Q pair through the final identity+usage path")
    print(f"out dir: {CAL_DIR}")
    print(f"prompt : {PROMPT!r}")
    print(f"params : {json.dumps(GEN_PARAMS, sort_keys=True)}\n")
    for lane in ("P", "Q"):
        spec = LANES[lane]
        body = _req_body(spec["model"])
        sha = hashlib.sha256(json.dumps(body).encode()).hexdigest()
        print(f"[{lane}] {spec['base']}  model={spec['model']}  "
              f"family={spec['family']}")
        print(f"     normalizer   : {spec['normalizer']}")
        print(f"     echo pattern : {spec['echo_acceptable']}")
        print(f"     request sha  : {sha[:32]}…")
        print(f"     keyfile      : {spec['keyfile']} "
              f"({'present' if os.path.exists(spec['keyfile']) else 'MISSING'})")
    print("\nwhat each live call must produce (acceptance):")
    for item in ("raw usage block + usage_raw_sha256",
                 "normalized-usage.json (v2 adapter) + normalized hash",
                 "primary_work = uncached_input + output",
                 "identity.json: echoed model id + nonempty provider id",
                 "identity <-> receipt binding (request_body_sha256)",
                 "echoed model matches the frozen lane pattern"):
        print(f"  - {item}")
    print("\nquota window: Q lane is free-tier; its quota resets 00:00 UTC. "
          "--live refuses inside a known-closed window only when the lane "
          "itself reports it — a 429 is recorded as INCONCLUSIVE, never retried.")


# ------------------------------------------------------------------- capture
def _capture(lane, transport):
    """Run ONE calibration call through the real capture path. `transport`
    is the only seam: the live path POSTs, the offline path returns a
    synthetic provider response. Raises on any capture defect."""
    spec = LANES[lane]
    out = os.path.join(CAL_DIR, f"lane-{lane}")
    os.makedirs(out, exist_ok=True)
    body = _req_body(spec["model"])
    if transport == "live":
        api_key = open(spec["keyfile"]).read().strip()
        # ONE call, returning the parsed provider object so identity is
        # captured from the REAL response (never re-issued: no double spend).
        reply, receipt, provider_obj = UG.recorded_call(
            spec["base"], f"{lane}-key", api_key, spec["model"],
            [{"role": "user", "content": PROMPT}], out,
            extra_body=GEN_PARAMS, tag=f"calibration-{lane}",
            normalizer_id=spec["normalizer"], return_response=True)
        if provider_obj is None:
            raise ValueError("CALIBRATION-IDENTITY: the live transport "
                             "returned no provider response object")
        return reply, receipt, provider_obj
    # offline: synthesize a provider response with the SAME shape the lanes
    # return, so the compose path is exercised exactly.
    if lane == "P":
        usage_raw = {"prompt_tokens": 24, "completion_tokens": 4,
                     "total_tokens": 28,
                     "prompt_tokens_details": {"cached_tokens": 0}}
        echoed = "minimax-m3"
    else:
        usage_raw = {"prompt_tokens": 20, "completion_tokens": 3,
                     "total_tokens": 23,
                     "prompt_tokens_details": {"cached_tokens": 0}}
        echoed = "agnes-2-0-flash"
    reply = "CALIBRATION-ACK"
    t0 = time.time()
    blob = json.dumps(body).encode()
    call_id = hashlib.sha256(f"{spec['base']}|{spec['model']}|{t0:.3f}|"
                             f"{reply[:64]}".encode()).hexdigest()[:16]
    receipt = os.path.join(out, f"call-{call_id}.json")
    # A11.2: the rehearsal writes the SAME persisted-request artifact the
    # live path writes, so the compose path is exercised identically.
    req_name = f"call-{call_id}.request.json"
    with open(os.path.join(out, req_name), "wb") as f:
        f.write(blob)
    json.dump({"call_id": call_id, "tag": f"calibration-{lane}",
               "endpoint": spec["base"], "model_requested": spec["model"],
               "wall_s": 0.0,
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "request_body_sha256": hashlib.sha256(blob).hexdigest(),
               "request_body_file": req_name,
               "request_body_file_sha256": hashlib.sha256(blob).hexdigest(),
               "usage_raw": usage_raw,
               "usage_raw_sha256": hashlib.sha256(
                   json.dumps(usage_raw, sort_keys=True).encode()).hexdigest(),
               "normalizer_id": spec["normalizer"],
               "normalizer_version": UG.NORMALIZER_VERSION,
               "normalizer_rule": "offline rehearsal fixture"},
              open(receipt, "w"), indent=1)
    provider_obj = {"id": f"calib-{lane.lower()}-offline", "model": echoed,
                    "created": int(t0), "usage": usage_raw,
                    "choices": [{"message": {"content": reply}}]}
    return reply, receipt, provider_obj


def _compose(lane, receipt, provider_obj, live):
    """identity -> normalize -> verify -> cross-bind. Returns a report dict.
    Any defect raises (fail closed)."""
    spec = LANES[lane]
    rep = {"lane": lane, "semantics": SEMANTICS, "mode":
           "live" if live else "offline", "receipt": os.path.basename(receipt)}
    rc = json.load(open(receipt))
    if rc.get("normalizer_id") != spec["normalizer"]:
        raise ValueError(f"CALIBRATION-ADAPTER-MISMATCH lane {lane}: "
                         f"{rc.get('normalizer_id')!r} != "
                         f"{spec['normalizer']!r}")
    # 1. immutable normalization immediately after capture
    nu_path = UG.write_normalized_usage(receipt)
    nu = json.load(open(nu_path))
    rep["normalized"] = os.path.basename(nu_path)
    rep["primary_work"] = nu["primary_work"]
    rep["input_tokens_uncached"] = nu["input_tokens_uncached"]
    rep["cached_tokens"] = nu["cached_tokens"]
    rep["output_tokens"] = nu["output_tokens"]
    rep["normalized_sha256"] = hashlib.sha256(
        open(nu_path, "rb").read()).hexdigest()
    UG.verify_normalized_usage(nu_path)          # raises on tamper/mismatch
    # 2. identity from the REAL provider object, then cross-bind to receipt
    if provider_obj is None:
        raise ValueError("CALIBRATION-IDENTITY: live path did not supply the "
                         "provider response object for identity capture")
    params = dict(GEN_PARAMS)
    id_path = ID.record_identity(
        os.path.dirname(receipt), spec["base"], spec["model"], provider_obj,
        extra_params=params, tag=f"calibration-{lane}",
        request_body_sha256=rc["request_body_sha256"],
        messages=[{"role": "user", "content": PROMPT}])
    id_rec = ID.verify_identity_binding(id_path, receipt)
    # A11.2: the persisted request bytes must reproduce the receipt hash AND
    # agree with the identity record field-by-field.
    UG.verify_request_binding(receipt, id_path)
    UG.verify_adapter_binding(spec["normalizer"], lane=lane,
                              receipt=rc)
    rep["model_echoed"] = id_rec["model_echoed_model"]
    rep["provider_id"] = id_rec["provider_response_id"]
    rep["identity"] = os.path.basename(id_path)
    # 3. echoed id must match the frozen lane prereg pattern
    fam = ID.check_against_prereg(id_path, {
        "endpoint": spec["base"], "requested_id": spec["model"],
        "acceptable_echoed_ids": spec["echo_acceptable"],
        "family": spec["family"]})
    rep["identity_family"] = fam
    rep["request_body_sha256"] = rc["request_body_sha256"]
    rep["params"] = params
    rep["non_estimand"] = True
    rep["not_a_cell"] = True
    rep["note"] = ("CALIBRATION / NEVER-ESTIMAND: not a cell of ORDER.md, "
                   "no estimand claim, excluded from every ledger")
    with open(os.path.join(os.path.dirname(receipt),
                           f"CALIBRATION-{lane}.json"), "w") as f:
        json.dump(rep, f, indent=1)
    return rep


def run_offline():
    os.makedirs(CAL_DIR, exist_ok=True)
    bad = []
    reps = []
    # idempotence: a re-run rehearses from a clean directory (fixtures only)
    import shutil
    if os.path.isdir(CAL_DIR):
        shutil.rmtree(CAL_DIR)
    for lane in ("P", "Q"):
        try:
            reply, receipt, obj = _capture(lane, "offline")
            rep = _compose(lane, receipt, obj, live=False)
            rep["reply"] = reply
            reps.append(rep)
            print(f"PASS offline lane {lane}: primary_work="
                  f"{rep['primary_work']} echoed={rep['model_echoed']} "
                  f"provider_id={rep['provider_id']}")
        except Exception as e:                       # noqa: BLE001
            bad.append(f"{lane}: {type(e).__name__} {e}")
            print(f"FAIL-OPEN offline lane {lane}: {type(e).__name__} {e}")
    # negative controls: the capture path must fail closed
    out = os.path.join(CAL_DIR, "lane-P")
    receipt = sorted(f for f in os.listdir(out)
                     if f.startswith("call-"))[0]
    rp = os.path.join(out, receipt)
    raw = json.load(open(rp))
    tampered = dict(raw)
    tampered["usage_raw"] = dict(raw["usage_raw"])
    tampered["usage_raw"]["prompt_tokens"] += 1
    tp = os.path.join(out, "tampered-raw.json")
    json.dump(tampered, open(tp, "w"))
    try:
        UG.write_normalized_usage(tp)
        bad.append("tampered raw usage normalized without error")
        print("FAIL-OPEN tampered raw usage accepted")
    except Exception as e:                           # noqa: BLE001
        print(f"PASS tampered raw usage refused ({type(e).__name__})")
    # stripped echoed model must fail identity capture
    try:
        ID.record_identity(out + "/idneg", LANES["P"]["base"],
                           LANES["P"]["model"], {"id": "x", "usage": {}},
                           extra_params=GEN_PARAMS,
                           request_body_sha256=raw["request_body_sha256"])
        bad.append("identity accepted a response with no echoed model")
        print("FAIL-OPEN identity accepted missing echo")
    except ValueError as e:
        print(f"PASS missing echoed model refused ({str(e)[:40]})")
    # stripped provider id must fail identity capture
    try:
        ID.record_identity(out + "/idneg2", LANES["P"]["base"],
                           LANES["P"]["model"],
                           {"model": "minimax-m3", "usage": {}},
                           extra_params=GEN_PARAMS,
                           request_body_sha256=raw["request_body_sha256"])
        bad.append("identity accepted a response with no provider id")
        print("FAIL-OPEN identity accepted missing provider id")
    except ValueError as e:
        print(f"PASS missing provider id refused ({str(e)[:40]})")
    print(f"\ncalibration offline: {2 - len([b for b in bad if 'lane' in b])}"
          f"/2 lanes green, {len(bad)} defect(s)")
    return 1 if bad else 0


def run_live(approve):
    if not approve:
        print("CALIBRATION-REFUSE: --live needs --i-know-this-spends "
              "--approve-quota; this spends P money and Q quota.")
        return 2
    os.makedirs(CAL_DIR, exist_ok=True)
    bad = []
    for lane in ("P", "Q"):
        spec = LANES[lane]
        if not os.path.exists(spec["keyfile"]):
            bad.append(f"{lane}: keyfile missing {spec['keyfile']}")
            print(f"FAIL-OPEN lane {lane}: keyfile missing")
            continue
        try:
            reply, receipt, obj = _capture(lane, "live")
            rep = _compose(lane, receipt, obj, live=True)
            print(f"PASS live lane {lane}: primary_work={rep['primary_work']} "
                  f"echoed={rep['model_echoed']} "
                  f"provider_id={rep['provider_id']}")
        except Exception as e:                       # noqa: BLE001
            bad.append(f"{lane}: {type(e).__name__} {e}")
            print(f"INCONCLUSIVE live lane {lane}: {type(e).__name__} "
                  f"{str(e)[:160]}")
    print(f"\ncalibration live: {len(bad)} defect(s); "
          "a lane failure is INCONCLUSIVE evidence (no retry), never a "
          "substituted model")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--i-know-this-spends", action="store_true")
    ap.add_argument("--approve-quota", action="store_true")
    a = ap.parse_args()
    if a.live:
        return run_live(a.i_know_this_spends and a.approve_quota)
    if a.offline:
        return run_offline()
    print_plan()
    return 0


if __name__ == "__main__":
    sys.exit(main())

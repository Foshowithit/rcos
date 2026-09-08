#!/usr/bin/env python3
"""H4 adversarial smoke — A1 (audit round 2 item 1): provider-bound v2 usage
adapters + immutable normalized-usage artifacts. EVERY probe must FAIL CLOSED
(or prove exactness). Exit 0 only if all green. Stdlib only. Provider is a
LOCAL STUB server (no external network, no real spend); the real P provider
receipt is used read-only as committed evidence."""
import hashlib
import json
import os
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import admissibility as ADM
from usage import (recorded_call, normalize_usage, write_normalized_usage,
                   verify_normalized_usage, PROVIDER_NORMALIZERS,
                   NORMALIZER_VERSION, NORMALIZER_RULE)

BASE = "/tmp/h4-smoke"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


class StubProvider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        payload = {"id": "stub-1", "model": body.get("model", "m"),
                   "created": 123,
                   "choices": [{"message": {"content": "STUB-OK"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                             "total_tokens": 15,
                             "prompt_tokens_details": {"cached_tokens": 2}}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = HTTPServer(("127.0.0.1", 0), StubProvider)
threading.Thread(target=srv.serve_forever, daemon=True).start()
EP = f"http://127.0.0.1:{srv.server_address[1]}"
os.system("rm -rf " + BASE)
os.makedirs(BASE, exist_ok=True)

# --- v2 adapters registered with lane bindings ---
for vid, lane, prov, fam, gw in (
        ("router9-openai-chat-v2", "P", "router9", "MiniMax", "minimax-m3"),
        ("kenari-openai-chat-v2", "Q", "kenari", "Kenari-Agnes",
         "agnes-2-0-flash:free")):
    cfg = PROVIDER_NORMALIZERS.get(vid, {})
    b = cfg.get("bound", {})
    check(f"v2 adapter {vid} bound to lane {lane}",
          cfg.get("raw_schema") == "openai-chat-completions"
          and cfg.get("input_includes_cache") is True
          and b.get("lane") == lane and b.get("provider") == prov
          and b.get("model_family") == fam and b.get("gateway_model") == gw
          and cfg.get("supersedes") == "openai-chat-total-input-v1",
          str(b))

# --- real P provider receipt (committed evidence, read-only) ---
REAL_P = os.path.normpath(os.path.join(
    ROOT, "..", "benchmarks", "fam-c", "runs", "H1-P-fam05-T0",
    "call-d7e697251423173c.json"))
real = json.load(open(REAL_P))
nu_v1 = normalize_usage(real, "openai-chat-total-input-v1")
check("real P receipt historical v1 -> primary work 2315",
      nu_v1["input_tokens_uncached"] == 350
      and nu_v1["output_tokens"] == 1965 and nu_v1["cached_tokens"] == 128
      and nu_v1["primary_work"] == 2315,
      str({k: nu_v1[k] for k in ("input_tokens_uncached", "output_tokens",
                                 "cached_tokens", "primary_work")}))

# --- real P provider data under the lane-P v2 adapter: deterministic 2315 ---
p_copy = os.path.join(BASE, "call-realP.json")
rc = dict(real, normalizer_id="router9-openai-chat-v2")
json.dump(rc, open(p_copy, "w"), indent=1)
nu_p = os.path.join(BASE, "call-realP.normalized.json")
got = write_normalized_usage(p_copy,
                             expect_normalizer_id="router9-openai-chat-v2")
check("v2 write returns colocated artifact", got == nu_p and
      os.path.exists(nu_p), got)
nu = json.load(open(nu_p))
check("real P data under router9 v2 -> 2315 deterministic",
      nu["primary_work"] == 2315 and nu["input_tokens_uncached"] == 350
      and nu["output_tokens"] == 1965 and nu["cached_tokens"] == 128
      and nu["normalizer_id"] == "router9-openai-chat-v2"
      and nu["normalizer_version"] == NORMALIZER_VERSION
      and nu["normalizer_rule"] == NORMALIZER_RULE
      and nu["raw_receipt_file"] == "call-realP.json"
      and nu["raw_receipt_sha256"] == hashlib.sha256(
          open(p_copy, "rb").read()).hexdigest(),
      str({k: nu.get(k) for k in ("primary_work", "normalizer_id")}))
before = open(nu_p).read()
check("identical rewrite is a byte-identical no-op",
      write_normalized_usage(p_copy) == nu_p and open(nu_p).read() == before)

# --- kenari-shaped Q data under lane-Q v2: same numbers, deterministic ---
q_raw = {"prompt_tokens": 478, "completion_tokens": 1965,
         "total_tokens": 2443,
         "prompt_tokens_details": {"cached_tokens": 128}}
q_copy = os.path.join(BASE, "call-qshape.json")
json.dump({"call_id": "q-1", "tag": "qshape", "model_requested": "q-m",
           "endpoint": "https://kenari.id/v1",
           "request_body_sha256": "q-req",
           "usage_raw": q_raw,
           "usage_raw_sha256": hashlib.sha256(
               json.dumps(q_raw, sort_keys=True).encode()).hexdigest(),
           "normalizer_id": "kenari-openai-chat-v2",
           "normalizer_version": NORMALIZER_VERSION,
           "normalizer_rule": NORMALIZER_RULE}, open(q_copy, "w"), indent=1)
nu_q = verify_normalized_usage(write_normalized_usage(
    q_copy, expect_normalizer_id="kenari-openai-chat-v2"))
check("kenari-shaped Q under kenari v2 -> 2315 deterministic",
      nu_q["primary_work"] == 2315
      and nu_q["input_tokens_uncached"] == 350
      and nu_q["cached_tokens"] == 128, str(nu_q["primary_work"]))

# --- adapter mismatch / unknown / incomplete / inconsistent: all fail ---
try:
    write_normalized_usage(p_copy,
                           expect_normalizer_id="kenari-openai-chat-v2")
    check("cross-lane adapter substitution rejected", False)
except ValueError as e:
    check("cross-lane adapter substitution rejected",
          "USAGE-ADAPTER-MISMATCH" in str(e), str(e)[:120])
try:
    normalize_usage(real, "nope-v9")
    check("unknown normalizer rejected", False)
except ValueError as e:
    check("unknown normalizer rejected",
          "USAGE-NORMALIZER-UNKNOWN" in str(e), str(e)[:120])
no_usage = os.path.join(BASE, "call-nousse.json")
json.dump({"call_id": "n-1", "model_requested": "m", "endpoint": EP,
           "normalizer_id": "router9-openai-chat-v2",
           "usage_raw": None, "usage_raw_sha256": None},
          open(no_usage, "w"))
try:
    write_normalized_usage(no_usage)
    check("missing usage invalidates write", False)
except ValueError as e:
    check("missing usage invalidates write", "USAGE-INCOMPLETE" in str(e),
          str(e)[:120])
bad_schema = os.path.join(BASE, "call-bad.json")
bad_raw = dict(q_raw, prompt_tokens="478")
json.dump({"call_id": "b-1", "model_requested": "m", "endpoint": EP,
           "normalizer_id": "router9-openai-chat-v2",
           "usage_raw": bad_raw,
           "usage_raw_sha256": hashlib.sha256(
               json.dumps(bad_raw, sort_keys=True).encode()).hexdigest()},
          open(bad_schema, "w"))
try:
    write_normalized_usage(bad_schema)
    check("mismatched schema invalidates write", False)
except ValueError:
    check("mismatched schema invalidates write", True)

# --- immutability: conflicting rewrite refused ---
rc_tag = json.load(open(p_copy))
rc_tag["tag"] = (rc_tag.get("tag") or "") + "-altered"
json.dump(rc_tag, open(p_copy, "w"), indent=1)
try:
    write_normalized_usage(p_copy)
    check("conflicting rewrite refused", False)
except RuntimeError as e:
    check("conflicting rewrite refused",
          "USAGE-NORMALIZED-CONFLICT" in str(e), str(e)[:120])

# --- tamper RAW file breaks verify (usage edit; then hash-consistent edit) ---
t_copy = os.path.join(BASE, "call-tamperraw.json")
shutil.copy(os.path.join(BASE, "call-qshape.json"), t_copy)
t_nu = write_normalized_usage(t_copy)
rt = json.load(open(t_copy))
rt["usage_raw"] = dict(rt["usage_raw"], prompt_tokens=500)
json.dump(rt, open(t_copy, "w"), indent=1)
try:
    verify_normalized_usage(t_nu)
    check("raw usage tamper breaks verify", False)
except ValueError as e:
    check("raw usage tamper breaks verify", "USAGE-TAMPER" in str(e),
          str(e)[:140])
rt2 = json.load(open(t_copy))
rt2["usage_raw_sha256"] = hashlib.sha256(
    json.dumps(rt2["usage_raw"], sort_keys=True).encode()).hexdigest()
json.dump(rt2, open(t_copy, "w"), indent=1)
try:
    verify_normalized_usage(t_nu)
    check("hash-consistent raw edit still breaks file binding", False)
except ValueError as e:
    check("hash-consistent raw edit still breaks file binding",
          "USAGE-TAMPER" in str(e), str(e)[:140])

# --- tamper NORMALIZED bytes breaks verify; metric edit with fixed self-sha
# --- still fails on re-derivation ---
n_copy = os.path.join(BASE, "call-tampernu.json")
shutil.copy(os.path.join(BASE, "call-qshape.json"), n_copy)
n_nu = write_normalized_usage(n_copy)
np_ = json.load(open(n_nu))
np_["primary_work"] = 2300
json.dump(np_, open(n_nu, "w"), indent=1)
try:
    verify_normalized_usage(n_nu)
    check("normalized byte tamper breaks verify", False)
except ValueError as e:
    check("normalized byte tamper breaks verify", "USAGE-TAMPER" in str(e),
          str(e)[:140])
np2 = json.load(open(n_nu))
np2["primary_work"] = 2300
stripped = {k: v for k, v in np2.items() if k != "normalized_sha256"}
np2["normalized_sha256"] = hashlib.sha256(
    json.dumps(stripped, sort_keys=True, indent=1,
               separators=(",", ": ")).encode()).hexdigest()
json.dump(np2, open(n_nu, "w"), indent=1)
try:
    verify_normalized_usage(n_nu)
    check("metric edit with repaired self-sha fails re-derivation", False)
except ValueError as e:
    check("metric edit with repaired self-sha fails re-derivation",
          "USAGE-TAMPER" in str(e), str(e)[:140])

# --- fresh stub receipt carries request_body_sha256 over exact POST bytes ---
reply, sp = recorded_call(
    EP, "K", "dummy", "stub-m", [{"role": "user", "content": "hi"}],
    os.path.join(BASE, "usage"), tag="reqbody",
    normalizer_id="router9-openai-chat-v2")
sr = json.load(open(sp))
want_body = hashlib.sha256(json.dumps(
    {"model": "stub-m",
     "messages": [{"role": "user", "content": "hi"}]}).encode()).hexdigest()
check("fresh receipt binds exact request-body hash",
      reply == "STUB-OK" and sr.get("request_body_sha256") == want_body,
      str(sr.get("request_body_sha256")))
snu = verify_normalized_usage(write_normalized_usage(
    sp, expect_normalizer_id="router9-openai-chat-v2"))
check("fresh stub receipt normalizes (10-2+5=13)",
      snu["primary_work"] == 13 and snu["input_tokens_uncached"] == 8,
      str(snu["primary_work"]))

# --- item 3: identity hardening (required provider id + body-hash binding) ---
from identity import (record_identity as _ri,
                      verify_identity_binding as _vib)
_iddir = os.path.join(BASE, "id3")
try:
    _ri(_iddir, EP, "stub-m", {"choices": [{"message": {"content": "x"}}]},
        request_body_sha256="b")
    check("stripped echoed model fails", False)
except ValueError as e:
    check("stripped echoed model fails", "IDENTITY-INCOMPLETE" in str(e),
          str(e)[:120])
try:
    _ri(_iddir, EP, "stub-m", {"model": "stub-m"},
        request_body_sha256="b")
    check("stripped provider id fails", False)
except ValueError as e:
    check("stripped provider id fails", "IDENTITY-INCOMPLETE" in str(e),
          str(e)[:120])
try:
    _ri(_iddir, EP, "stub-m", {"model": "stub-m", "id": ""},
        request_body_sha256="b")
    check("empty provider id fails", False)
except ValueError:
    check("empty provider id fails", True)
try:
    _ri(_iddir, EP, "stub-m", {"model": "stub-m", "id": "r1"})
    check("missing body hash fails", False)
except ValueError as e:
    check("missing body hash fails", "IDENTITY-INCOMPLETE" in str(e),
          str(e)[:120])
_okp = _ri(_iddir, EP, "stub-m", {"model": "stub-m", "id": "stub-1"},
           extra_params={"max_tokens": 9000}, tag="bindtest",
           request_body_sha256=sr.get("request_body_sha256"))
_okr = json.load(open(_okp))
check("identity preserves body hash + full param set",
      _okr.get("request_body_sha256") == sr.get("request_body_sha256")
      and _okr.get("generation_params") == {"max_tokens": 9000}
      and _okr.get("provider_response_id") == "stub-1",
      str({k: _okr.get(k) for k in ("provider_response_id",
                                    "request_body_sha256")}))
try:
    _vib(_okp, sp)
    check("identity/receipt binding verifies", True)
except ValueError as e:
    check("identity/receipt binding verifies", False, str(e)[:160])
_altsp = os.path.join(BASE, "usage", "call-bindalt.json")
_altrc = dict(sr, model_requested="stub-m-tampered")
json.dump(_altrc, open(_altsp, "w"), indent=1)
try:
    _vib(_okp, _altsp)
    check("altered model after receipt breaks binding", False)
except ValueError as e:
    check("altered model after receipt breaks binding",
          "IDENTITY-BINDING-MISMATCH" in str(e), str(e)[:160])

# --- admissibility: ELIGIBLE iff artifacts present AND verifying ---
FREEZE = "f" * 40
rundir = os.path.join(BASE, "P-famXX-T0self")
os.makedirs(rundir, exist_ok=True)
rd = os.path.join(rundir, "call-a1.json")
shutil.copy(os.path.join(BASE, "call-qshape.json"), rd)
rnu = write_normalized_usage(rd)
json.dump({"endpoint": "https://kenari.id/v1", "model_requested": "q-m",
           "model_echoed_model": "q-m", "provider_response_id": "qresp-1",
           "request_body_sha256": "q-req", "generation_params": {}},
          open(os.path.join(rundir, "identity.json"), "w"))
json.dump({"wired": True, "instance_freeze_commit": FREEZE,
           "usage_receipts": ["call-a1.json"], "dev_mode": False,
           "identity_file": "identity.json"},
          open(os.path.join(rundir, "H1-RUN-MANIFEST.json"), "w"))
open(os.path.join(rundir, "EVIDENCE-CHAIN.jsonl"), "w").write("")
s, r = ADM.classify_run_dir(rundir, FREEZE)
check("full-gate run with verifying artifacts is ESTIMAND-ELIGIBLE",
      s == ADM.ELIGIBLE, r)
os.remove(rnu)
s2, r2 = ADM.classify_run_dir(rundir, FREEZE)
check("missing normalized artifact excludes",
      s2 == ADM.EXCLUDED and "normalized usage artifact missing" in r2, r2)
rnu = write_normalized_usage(rd)
np3 = json.load(open(rnu))
np3["primary_work"] = 1
json.dump(np3, open(rnu, "w"), indent=1)
s3, r3 = ADM.classify_run_dir(rundir, FREEZE)
check("tampered normalized artifact excludes",
      s3 == ADM.EXCLUDED and "normalized usage invalid" in r3, r3[:160])
# rebuild both receipt + artifact cleanly after tamper round
os.remove(rnu)
shutil.copy(os.path.join(BASE, "call-qshape.json"), rd)
rnu = write_normalized_usage(rd)
rr = json.load(open(rd))
rr["usage_raw"] = dict(rr["usage_raw"], completion_tokens=7)
json.dump(rr, open(rd, "w"), indent=1)
s4, r4 = ADM.classify_run_dir(rundir, FREEZE)
check("tampered raw receipt excludes",
      s4 == ADM.EXCLUDED and "normalized usage invalid" in r4, r4[:160])
# rebuild cleanly, then tamper the IDENTITY side: binding must fail too
os.remove(rnu)
shutil.copy(os.path.join(BASE, "call-qshape.json"), rd)
rnu = write_normalized_usage(rd)
_idf = os.path.join(rundir, "identity.json")
_idj = json.load(open(_idf))
_idj["model_requested"] = "q-m-tampered"
json.dump(_idj, open(_idf, "w"))
s5, r5 = ADM.classify_run_dir(rundir, FREEZE)
check("tampered identity excludes via binding",
      s5 == ADM.EXCLUDED and "identity binding invalid" in r5, r5[:160])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH4 smoke: {len(results) - len(bad)}/{len(results)} closed")
srv.shutdown()
sys.exit(1 if bad else 0)

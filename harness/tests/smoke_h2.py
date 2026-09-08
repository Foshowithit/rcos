#!/usr/bin/env python3
"""H2 adversarial smoke — evidence layer. EVERY probe must FAIL CLOSED
(or prove exactness). Exit 0 only if all green. Stdlib only. Provider
is a LOCAL STUB server (no external network, no real spend)."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from usage import recorded_call, summarize, normalize_usage, NORMALIZER_VERSION
from identity import record_identity, check_distinct_families, check_against_prereg
from reuse_log import write_record, genuine_reuse, check_ablation

BASE = "/tmp/h2-smoke"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


class StubProvider(BaseHTTPRequestHandler):
    MODE = "ok"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.MODE == "no-usage":
            payload = {"id": "r1", "model": body.get("model", "m"),
                       "choices": [{"message": {"content": "hi"}}]}
        elif self.MODE == "cached-only":
            payload = {"id": "r1", "model": body.get("model", "m"),
                       "choices": [{"message": {"content": "hi"}}],
                       "usage": {"cached_tokens": 50, "output_tokens": 5}}
        else:
            payload = {"id": "stub-1", "model": body.get("model", "m"),
                       "created": 123,
                       "choices": [{"message": {"content": "STUB-OK"}}],
                       # REAL OpenAI Chat Completions usage shape: prompt_tokens
                       # is total prompt (cache included), cached subset lives
                       # at prompt_tokens_details.cached_tokens. (10 prompt, 2
                       # cached -> 8 uncached; 5 output.)
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
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
EP = f"http://127.0.0.1:{PORT}"
os.system("rm -rf " + BASE)


def call(tag="t", mode="ok"):
    StubProvider.MODE = mode
    return recorded_call(EP, "K", "dummy", "stub-m", [{"role": "user",
                                                      "content": "hi"}],
                         os.path.join(BASE, "usage"), tag=tag)


# --- usage capture + derivation ---
reply, p1 = call("a")
check("stub call captured", reply == "STUB-OK" and p1.endswith(".json"))
_, p2 = call("b")
s = summarize([p1, p2], {"stub-m": "openai-chat-total-input-v1"})
r0 = json.load(open(p1))
check("provenance fields present",
      r0.get("usage_raw_sha256") and r0.get("normalizer_version") == NORMALIZER_VERSION,
      str({k: r0.get(k) for k in ("usage_raw_sha256", "normalizer_version")}))
check("normalize_usage primary work exact",
      __import__("usage").normalize_usage(r0, "openai-chat-total-input-v1")["primary_work"] == 13)
check("derived metrics exact",
      s == {"model_calls": 2, "input_tokens_uncached": 16,
            "output_tokens": 10, "cached_tokens": 4,
            "cached_detail_per_call": [2, 2]}, str(s))
# NEW: the REAL P provider receipt (committed evidence, OpenAI chat schema)
# must normalize exactly to the auditor-computed numbers; stripped usage
# must invalidate (estimation forbidden).
import os as _os
_REAL_P = _os.path.normpath(_os.path.join(
    ROOT, "..", "benchmarks", "fam-c", "runs", "H1-P-fam05-T0",
    "call-d7e697251423173c.json"))
_real = json.load(open(_REAL_P))
_nu = __import__("usage").normalize_usage(_real, "openai-chat-total-input-v1")
check("real P receipt normalizes to primary work 2315 (350 uncached + 1965 out)",
      _nu["input_tokens_uncached"] == 350 and _nu["output_tokens"] == 1965
      and _nu["primary_work"] == 2315 and _nu["cached_tokens"] == 128,
      str({k: _nu[k] for k in ("input_tokens_uncached", "output_tokens",
                               "cached_tokens", "primary_work")}))
_stripped = dict(_real)
_stripped.pop("usage_raw", None)
try:
    __import__("usage").normalize_usage(_stripped, "openai-chat-total-input-v1")
    check("stripped-usage receipt invalidated", False)
except ValueError:
    check("stripped-usage receipt invalidated", True)
# NEW: recorded_call(return_response=True) surfaces the REAL provider
# response object so identity capture runs provider-side (echoed model +
# response id), never from reply-text self-report.
_r3, _p3b, _resp = __import__("usage").recorded_call(
    EP, "K", "dummy", "stub-m", [{"role": "user", "content": "hi"}],
    os.path.join(BASE, "usage"), tag="idtest", return_response=True)
check("recorded_call surfaces response for identity capture",
      isinstance(_resp, dict) and _resp.get("model") == "stub-m"
      and _resp.get("id") == "stub-1",
      str({k: _resp.get(k) for k in ("model", "id")}))
_idp = record_identity(os.path.join(BASE, "idrec"), EP, "stub-m", _resp,
                       extra_params={"max_tokens": 9000}, tag="idtest")
check("identity prereg conforms on echoed provider id",
      check_against_prereg(_idp, {"endpoint": EP, "requested_id": "stub-m",
                                  "acceptable_echoed_ids": ["stub-m"],
                                  "family": "Stub"}) == "Stub")
_, p3 = call("c", mode="no-usage")
try:
    summarize([p3], {"stub-m": "openai-chat-total-input-v1"})
    check("missing usage invalidates", False)
except ValueError:
    check("missing usage invalidates", True)
_, p4 = call("d", mode="cached-only")
try:
    summarize([p4], {"stub-m": "openai-chat-total-input-v1"})
    check("cached-relabeled-uncached invalidates", False)
except ValueError:
    check("cached-relabeled-uncached invalidates", True)

# --- identity ---
resp = {"id": "r9", "model": "stub-m", "created": 1}
ip = record_identity(os.path.join(BASE, "idA"), EP, "stub-m", resp)
check("identity record complete", ip.endswith("identity.json"))
try:
    record_identity(os.path.join(BASE, "idB"), EP, "stub-m",
                    {"choices": []})
    check("identity without echo fails", False)
except ValueError:
    check("identity without echo fails", True)
os.makedirs(os.path.join(BASE, "idC"), exist_ok=True)
os.makedirs(os.path.join(BASE, "idD"), exist_ok=True)
json.dump({"endpoint": EP + ":1", "model_echoed_model": "stub-m"},
          open(os.path.join(BASE, "idC", "identity.json"), "w"))
json.dump({"endpoint": EP, "model_echoed_model": "stub-other"},
          open(os.path.join(BASE, "idD", "identity.json"), "w"))
check("distinct families detected",
      check_distinct_families(os.path.join(BASE, "idC", "identity.json"),
                              os.path.join(BASE, "idD", "identity.json")))
json.dump({"endpoint": EP, "model_echoed_model": "stub-m"},
          open(os.path.join(BASE, "idE", "identity.json"), "w")) \
    if os.path.isdir(os.path.join(BASE, "idE")) else None
os.makedirs(os.path.join(BASE, "idE"), exist_ok=True)
json.dump({"endpoint": EP, "model_echoed_model": "stub-m"},
          open(os.path.join(BASE, "idE", "identity.json"), "w"))
PREREG_P = {"provider": "p1", "endpoint": EP, "requested_id": "stub-m",
              "acceptable_echoed_ids": ["stub-m", "stub-*"], "family": "FamP"}
PREREG_Q = {"provider": "p2", "endpoint": EP + ":1",
            "requested_id": "stub-m", "acceptable_echoed_ids": ["stub-*"],
            "family": "FamQ"}
check("prereg identity match returns family",
      check_against_prereg(os.path.join(BASE, "idA", "identity.json"), PREREG_P) == "FamP")
try:
    check_against_prereg(os.path.join(BASE, "idA", "identity.json"), PREREG_Q)
    check("prereg endpoint mismatch rejected", False)
except ValueError:
    check("prereg endpoint mismatch rejected", True)
check("same endpoint+model not distinct",
      not check_distinct_families(
          os.path.join(BASE, "idC", "identity.json").replace("idC", "idE"),
          os.path.join(BASE, "idE", "identity.json")))

# --- reuse lifecycle + contribution evidence ---
os.makedirs(os.path.join(BASE, "art"), exist_ok=True)
open(os.path.join(BASE, "art", "cap.out"), "w").write("capability bytes")
open(os.path.join(BASE, "art", "consumer_in.txt"), "w").write("capability bytes")
base_fields = dict(
    reuse_policy="test", capability_available=True,
    capability_candidate_ids=["k1"], capability_selected=True,
    selected_capability_id="k1", selected_capability_hash="h",
    capability_loaded=True, capability_invoked=True,
    capability_output_consumed=True, capability_materially_contributed=True,
    contribution_evidence=None, reuse_rejected=False,
    reuse_rejection_reason="")
rp = write_record(os.path.join(BASE, "rl"), "t1", "A", "correct", **dict(
    base_fields, contribution_evidence={
        "mechanism": "hash-linkage",
        "artifact": os.path.join(BASE, "art", "cap.out"),
        "consumed_inputs": [os.path.join(BASE, "art", "consumer_in.txt")]}))
check("hash-linked contribution accepted", rp.endswith(".json"))
check("genuine_reuse true", genuine_reuse(rp, required=False) is True)
try:
    write_record(os.path.join(BASE, "rl"), "t2", "A", "correct", **dict(
        base_fields,
        contribution_evidence={"mechanism": "self-report",
                               "note": "model said it helped"}))
    check("self-report contribution rejected", False)
except ValueError:
    check("self-report contribution rejected", True)
try:
    write_record(os.path.join(BASE, "rl"), "t3", "A", "correct", **dict(
        base_fields,
        contribution_evidence={"mechanism": "hash-linkage",
                               "artifact": os.path.join(BASE, "art", "cap.out"),
                               "consumed_inputs": [os.path.join(BASE, "art", "other.txt")]}))
    check("unlinked hash claim rejected", False)
except ValueError:
    check("unlinked hash claim rejected", True)
open(os.path.join(BASE, "art", "other.txt"), "w").write("unrelated")
rp2 = write_record(os.path.join(BASE, "rl"), "t4", "A", "correct", **dict(
    base_fields, capability_materially_contributed=False,
    contribution_evidence=None,
    reuse_rejected=False, reuse_rejection_reason=""))
check("non-contributing record allowed when flagged false",
      rp2.endswith(".json"))
try:
    genuine_reuse(rp2, required=True)
    check("genuine_reuse predicate enforces", False)
except ValueError:
    check("genuine_reuse predicate enforces", True)
try:
    write_record(os.path.join(BASE, "rl"), "t5", "A", "correct", **dict(
        base_fields, capability_invoked=False))
    check("missing field rejected", False)
except ValueError:
    check("missing field rejected", True)

def _man(path, cap, verdict):
    m = {"schema_version": "exec-manifest-v1",
         "input_snapshot_hash": "in1", "context_hash": "cx",
         "model_identity": "m", "generation_params": {"t": 0},
         "tool_policy_hash": "tp", "initial_workdir_hash": "wd",
         "capability_step_hash": cap,
         "evaluator_verdict": verdict, "evaluator_evidence_hash": "ev-" + verdict}
    open(path, "w").write(json.dumps(m))
    return path
_mt = os.path.join(BASE, "man-t.json")
_ma = os.path.join(BASE, "man-a.json")
_t = json.load(open(_man(_mt + ".tmp", "capA", "ship")))
_a = dict(_t, capability_step_hash="ABSENT", capability_access="absent",
          evaluator_verdict="fix", evaluator_evidence_hash="ev-fix")
open(_mt, "w").write(json.dumps({**_t, "capability_access": "present"}))
json.dump(_a, open(_ma, "w"))
ok, der = check_ablation(_mt, _ma)
check("derived ablation passes (differing verdicts)",
      ok and der["outcome_changed"] is True, str(der))
_a2 = dict(_t, capability_step_hash="ABSENT", capability_access="absent",
           evaluator_verdict="ship", evaluator_evidence_hash="ev-ship")
json.dump(_a2, open(_ma, "w"))
ok2, der2 = check_ablation(_mt, _ma)
check("same-verdict ablation fails (no outcome change proven)", not ok2)
_t3 = dict(_t, context_hash="DIFFERENT")
json.dump(_t3, open(_mt, "w"))
ok3, der3 = check_ablation(_mt, _ma)
check("differing-context ablation fails", not ok3)
# NEW: deleted-from-both field must FAIL (exact key equality)
_md = dict(json.load(open(_mt)))
del _md["context_hash"]
json.dump(_md, open(_mt, "w"))
okd, _ = check_ablation(_mt, _ma)
check("deleted-field-from-both fails exact keys", not okd)
json.dump({"schema_version": "exec-manifest-v1",
           "input_snapshot_hash": "in1", "context_hash": "cx",
           "model_identity": "m", "generation_params": {"t": 0},
           "tool_policy_hash": "tp", "initial_workdir_hash": "wd",
           "capability_access": "present",
           "capability_step_hash": "capA",
           "evaluator_verdict": "ship",
           "evaluator_evidence_hash": "ev-ship"}, open(_mt, "w"))
# NEW: ignored extra execution field must FAIL (closed schema)
_t4 = dict(_t, capability_step_hash="ABSENT", capability_access="absent",
           evaluator_verdict="fix", evaluator_evidence_hash="ev-fix",
           system_prompt_override="solve using algorithm X")
json.dump(_t4, open(_mt, "w"))
ok4, der4 = check_ablation(_mt, _ma)
check("extra execution field fails closed schema", not ok4, str(der4))
# NEW: tampered usage_raw must FAIL hash check
import copy
r1 = json.load(open(p1))
r1["usage_raw"] = dict(r1["usage_raw"], input_tokens=9999)
try:
    __import__("usage").normalize_usage(r1, "openai-chat-total-input-v1")
    check("tampered usage_raw rejected", False)
except ValueError:
    check("tampered usage_raw rejected", True)
# NEW: cached > total must FAIL (real schema path: prompt_tokens_details)
r2 = json.load(open(p1))
r2["usage_raw"] = dict(r2["usage_raw"])
r2["usage_raw"]["prompt_tokens_details"] = dict(
    r2["usage_raw"].get("prompt_tokens_details") or {}, cached_tokens=500)
r2["usage_raw_sha256"] = __import__("hashlib").sha256(
    json.dumps(r2["usage_raw"], sort_keys=True).encode()).hexdigest()
try:
    __import__("usage").normalize_usage(r2, "openai-chat-total-input-v1")
    check("cached>total rejected", False)
except ValueError:
    check("cached>total rejected", True)
# NEW: unknown normalizer must FAIL
try:
    __import__("usage").normalize_usage(r0, "nope-v9")
    check("unknown normalizer rejected", False)
except ValueError:
    check("unknown normalizer rejected", True)
# adapter substitution: same raw receipt reinterpreted under the other adapter must FAIL
r_alt = json.load(open(p1))
try:
    summarize([p1], {"stub-m": "openai-chat-uncached-input-v1"})
    check("adapter substitution rejected", False)
except ValueError:
    check("adapter substitution rejected", True)
# unmapped model must FAIL
try:
    summarize([p1], {"other-m": "openai-chat-total-input-v1"})
    check("unmapped model rejected", False)
except ValueError:
    check("unmapped model rejected", True)
# manifest fixtures gain schema_version
def _mkm(path, cap, verdict, ev):
    m = {"schema_version": "exec-manifest-v1",
         "input_snapshot_hash": "in1", "context_hash": "cx",
         "model_identity": "m", "generation_params": {"t": 0},
         "tool_policy_hash": "tp", "initial_workdir_hash": "wd",
         "capability_access": "present" if cap != "ABSENT" else "absent",
         "capability_step_hash": cap,
         "evaluator_verdict": verdict, "evaluator_evidence_hash": ev}
    open(path, "w").write(json.dumps(m))
    return path
bad = [n for n, ok_ in results if not ok_]
print(f"\nH2 smoke: {len(results) - len(bad)}/{len(results)} closed")
srv.shutdown()
sys.exit(1 if bad else 0)

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
                       "usage": {"input_tokens": 10, "output_tokens": 5,
                                 "cached_tokens": 2}}
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
s = summarize([p1, p2])
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
_, p3 = call("c", mode="no-usage")
try:
    summarize([p3])
    check("missing usage invalidates", False)
except ValueError:
    check("missing usage invalidates", True)
_, p4 = call("d", mode="cached-only")
try:
    summarize([p4])
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
    m = {"input_snapshot_hash": "in1", "context_hash": "cx",
         "model_identity": "m", "generation_params": {"t": 0},
         "tool_policy_hash": "tp", "initial_workdir_hash": "wd",
         "capability_step_hash": cap,
         "evaluator_verdict": verdict, "evaluator_evidence_hash": "ev-" + verdict}
    open(path, "w").write(json.dumps(m))
    return path
_mt = os.path.join(BASE, "man-t.json")
_ma = os.path.join(BASE, "man-a.json")
_t = {"input_snapshot_hash": "in1", "context_hash": "cx", "model_identity": "m",
      "generation_params": {"t": 0}, "tool_policy_hash": "tp",
      "initial_workdir_hash": "wd", "capability_step_hash": "capA",
      "capability_access": "present",
      "evaluator_verdict": "ship", "evaluator_evidence_hash": "ev-ship"}
_a = dict(_t, capability_step_hash="ABSENT", capability_access="absent",
          evaluator_verdict="fix", evaluator_evidence_hash="ev-fix")
json.dump(_t, open(_mt, "w"))
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
# NEW: cached > total must FAIL
r2 = json.load(open(p1))
r2["usage_raw"] = dict(r2["usage_raw"], cached_tokens=500)
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
bad = [n for n, ok_ in results if not ok_]
print(f"\nH2 smoke: {len(results) - len(bad)}/{len(results)} closed")
srv.shutdown()
sys.exit(1 if bad else 0)

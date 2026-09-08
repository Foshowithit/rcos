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

from usage import recorded_call, summarize
from identity import record_identity, check_distinct_families
from reuse_log import write_record, genuine_reuse

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
check("derived metrics exact",
      s == {"model_calls": 2, "input_tokens_uncached": 20,
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

bad = [n for n, ok_ in results if not ok_]
print(f"\nH2 smoke: {len(results) - len(bad)}/{len(results)} closed")
srv.shutdown()
sys.exit(1 if bad else 0)

#!/usr/bin/env python3
"""H9 smoke — A11b.1 production request binding + P1 single-source request
bytes. Every probe FAILS CLOSED or proves exactness; exit 0 only if all green.

Scope: (a) the runner's REAL call() code path (never the calibration stub)
captures artifacts that pass admissibility.classify_run_dir() as
ESTIMAND-ELIGIBLE; (b) each INDEPENDENT mutation of one binding surface —
prompt/message bytes, a raw request-file byte, max_tokens, model, endpoint,
adapter id, persisted request file, identity messages_sha256, manifest lane —
flips the run EXCLUDED; (c) P1 single-source-of-truth: the bytes hashed are
the bytes persisted are the bytes sent (the transport is intercepted and
compared against the persisted file, byte for byte); (d) the runner's
pre-link chain gate refuses tampered captures BEFORE any chain link is
emitted. No network: the provider transport is a local monkeypatch over
urllib.request.urlopen. Stdlib only."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))   # harness/tests
ROOT = os.path.dirname(HERE)                         # harness
REPO = os.path.dirname(ROOT)
HARNESS_RUN = os.path.join(REPO, "benchmarks", "fam-c", "harness-run")
sys.path.insert(0, ROOT)
sys.path.insert(0, HARNESS_RUN)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import admissibility as ADM
import usage
import identity
import run_arm_h1 as RAH  # the runner under test (no side effects at import)

FREEZE = "ab" * 20                      # fixture instance freeze anchor
PROMPT = "H9 binding probe: fail closed or prove exact."
# Stub provider payload: kenari lane echo (agnes-2-0-flash is in the lane's
# echo_acceptable list) + provider id + usage in the kenari raw shape.
STUB_PAYLOAD = {"model": "agnes-2-0-flash", "id": "h9-fx-1", "created": 1,
                "choices": [{"message": {"content": "STUB-REPLY-OK"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                          "total_tokens": 15,
                          "prompt_tokens_details": {"cached_tokens": 2}}}
results = []
SENT = {}


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


# --- offline transport: intercept the real code path, never the socket -----
class _FakeResp(object):
    def __init__(self, payload):
        self.status = 200
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body


def _fake_urlopen(req, timeout=None):
    SENT["bytes"] = bytes(req.data) if getattr(req, "data", None) else b""
    return _FakeResp(STUB_PAYLOAD)


# --- fixture helpers --------------------------------------------------------
def build_run():
    """One real capture through RAH.call() (production code path) against the
    intercepted transport, inside a fresh non-H1 run dir."""
    d = tempfile.mkdtemp(prefix="run-h9-", dir=BASE_TMP)
    reply, receipt, nu_path, id_path, family = RAH.call("Q", PROMPT, d, "h9")
    reqs = [n for n in os.listdir(d) if n.endswith(".request.json")]
    assert len(reqs) == 1, "expected exactly one persisted request file"
    return {"dir": d, "receipt": receipt,
            "request": os.path.join(d, reqs[0]), "nu": nu_path,
            "idp": id_path, "family": family, "reply": reply}


def finalize(handle, chain=True):
    """Write the on-disk manifest (wired, lane Q, this freeze) and, unless
    chain=False, pre-create EVIDENCE-CHAIN.jsonl (presence gate for
    classify; a real chain is produced by _wire_chain in the gate probes)."""
    d = handle["dir"]
    manifest = {"lane": "Q", "family": "famXX", "task": "T0", "arm": "correct",
                "wired": True, "dev_mode": False,
                "instance_freeze_commit": FREEZE,
                "frozen_commit": FREEZE,
                "usage_receipts": [os.path.basename(handle["receipt"])],
                "usage_normalized": [os.path.basename(handle["nu"])],
                "identity_file": os.path.basename(handle["idp"]),
                "checker_returncode": 0, "output_sha256": "fx",
                "verdict": "ship"}
    json.dump(manifest, open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w"),
              indent=1)
    if chain:
        cf = os.path.join(d, RAH.CHAIN_FILE)
        if not os.path.exists(cf):
            open(cf, "w").close()
    return manifest


def classify(handle):
    return ADM.classify_run_dir(handle["dir"], FREEZE)


def clone(base_dir):
    dst = base_dir + ".c%d" % clone.n
    clone.n += 1
    shutil.copytree(base_dir, dst)
    return dst


clone.n = 0

FAMC = os.path.dirname(HARNESS_RUN)
BASE_TMP = tempfile.mkdtemp(prefix=".h9-smoke-", dir=FAMC)
# Redirect the kenari lane's keyfile to a fixture file so no real credential
# is ever read; lane Q's endpoint/model/normalizer stay the real bound values.
_ORIG_KEYFILE = RAH.LANES["Q"]["keyfile"]
_KEY_FIXTURE = os.path.join(BASE_TMP, "kenari-key.fixture")
with open(_KEY_FIXTURE, "w") as _kf:
    _kf.write("sk-h9-fixture\n")
RAH.LANES["Q"]["keyfile"] = _KEY_FIXTURE
_REAL_URLOPEN = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
bad = 0
try:
    # ---------- P1: one source of truth for the request bytes ----------
    h = build_run()
    check("clean capture artifacts present (receipt, persisted request, "
          "normalized, identity.json, raw.txt)",
          all(os.path.exists(os.path.join(h["dir"], n)) for n in
              (os.path.basename(h["receipt"]),
               os.path.basename(h["request"]),
               os.path.basename(h["nu"]), "identity.json", "raw.txt")))
    req_bytes = open(h["request"], "rb").read()
    sent = SENT.get("bytes")
    check("P1: persisted request bytes == bytes sent on the wire",
          sent is not None and req_bytes == sent)
    rc0 = json.load(open(h["receipt"]))
    got = rc0.get("request_body_sha256")
    want = hashlib.sha256(req_bytes).hexdigest()
    check("P1: bytes hashed == bytes written == bytes sent "
          "(receipt sha == file sha == wire bytes)",
          got == want and rc0.get("request_body_file_sha256") == want
          and hashlib.sha256(sent).hexdigest() == want)
    idj = json.load(open(h["idp"]))
    msg_sha = hashlib.sha256(json.dumps(
        json.loads(req_bytes)["messages"], sort_keys=True).encode()).hexdigest()
    check("A11b.1: identity.messages_sha256 == hash of the exact messages "
          "object sent (messages built once)",
          idj.get("messages_sha256") == msg_sha)
    check("P1: no .stage-* temp request left in the run dir",
          not [n for n in os.listdir(h["dir"]) if ".stage-" in n])
    # usage-level verifiers pass on a clean capture (direct probe).
    usage.verify_request_binding(h["receipt"], h["idp"])
    usage.verify_adapter_binding(rc0.get("normalizer_id"),
                                 lane="Q", receipt=rc0)
    check("clean capture verifies at usage level "
          "(verify_request_binding + verify_adapter_binding)", True)
    manifest = finalize(h)
    s, r = classify(h)
    check("A11b.1: clean real-code capture is ESTIMAND-ELIGIBLE", s == ADM.ELIGIBLE, r)

    # ---------- runner pre-link gate: clean passes, tamper refuses ----------
    h2 = build_run()
    m2 = finalize(h2, chain=False)
    try:
        tip = RAH._wire_chain(h2["dir"], FREEZE, m2, h2["receipt"], h2["nu"],
                              h2["idp"], h2["family"], None, None, "chk-sha",
                              None, "ship", "fx", None)
        gate_ok = isinstance(tip, str) and len(tip) == 64
    except Exception as e:  # noqa: BLE001 — any refusal here is a failure
        gate_ok = False
        check("pre-link gate passes a clean capture", False, repr(e))
    if gate_ok:
        check("pre-link gate passes a clean capture "
              "(CHAIN-BINDING-GATE before genesis)", True)
    s2, r2 = classify(h2)
    check("clean capture with REAL chain is ESTIMAND-ELIGIBLE",
          s2 == ADM.ELIGIBLE, r2)
    h3 = build_run()
    m3 = finalize(h3, chain=False)
    with open(h3["request"], "ab") as f:
        f.write(b"X")                     # one raw byte appended post-call
    try:
        RAH._wire_chain(h3["dir"], FREEZE, m3, h3["receipt"], h3["nu"],
                        h3["idp"], h3["family"], None, None, "chk-sha", None,
                        "ship", "fx", None)
        check("pre-link gate refuses a tampered request byte "
              "(no chain link emitted)", False, "gate did not raise")
    except RuntimeError as e:
        check("pre-link gate refuses a tampered request byte "
              "(no chain link emitted)",
              "CHAIN-BINDING-GATE-FAIL" in str(e)
              and not os.path.exists(os.path.join(h3["dir"], RAH.CHAIN_FILE)),
              str(e)[:160])

    # ---------- A11b.1 mutation battery: every surface fails closed --------
    # One clean, finalized run is the pristine base; each mutation is applied
    # to an independent copy so the mutations never interact.
    base_dir = h["dir"]
    # M1: prompt/message bytes altered in the PERSISTED REQUEST FILE.
    d1 = clone(base_dir)
    b1 = json.loads(open(os.path.join(d1, os.path.basename(h["request"])),
                         "rb").read())
    b1["messages"][0]["content"] = PROMPT + " tampered"
    with open(os.path.join(d1, os.path.basename(h["request"])), "wb") as f:
        f.write(json.dumps(b1).encode())
    s1, r1 = ADM.classify_run_dir(d1, FREEZE)
    check("M1 prompt/message bytes mutated -> EXCLUDED",
          s1 == ADM.EXCLUDED and "REQUEST-BINDING-MISMATCH" in r1, r1[:160])
    shutil.rmtree(d1, ignore_errors=True)
    # M2: one raw byte appended to the persisted request file.
    d2 = clone(base_dir)
    with open(os.path.join(d2, os.path.basename(h["request"])), "ab") as f:
        f.write(b"\n")
    s2b, r2b = ADM.classify_run_dir(d2, FREEZE)
    check("M2 raw request-file byte mutated -> EXCLUDED",
          s2b == ADM.EXCLUDED and "REQUEST-BINDING-MISMATCH" in r2b, r2b[:160])
    shutil.rmtree(d2, ignore_errors=True)
    # M3: generation param (max_tokens) mutated in the identity record.
    d3 = clone(base_dir)
    i3 = json.load(open(os.path.join(d3, "identity.json")))
    i3["generation_params"]["max_tokens"] = 1
    json.dump(i3, open(os.path.join(d3, "identity.json"), "w"))
    s3b, r3b = ADM.classify_run_dir(d3, FREEZE)
    check("M3 max_tokens (identity generation_params) mutated -> EXCLUDED",
          s3b == ADM.EXCLUDED and "generation_params" in r3b, r3b[:160])
    shutil.rmtree(d3, ignore_errors=True)
    # M4: requested model mutated in the identity record.
    d4 = clone(base_dir)
    i4 = json.load(open(os.path.join(d4, "identity.json")))
    i4["model_requested"] = "fx-tampered-model"
    json.dump(i4, open(os.path.join(d4, "identity.json"), "w"))
    s4b, r4b = ADM.classify_run_dir(d4, FREEZE)
    check("M4 model mutated in identity -> EXCLUDED",
          s4b == ADM.EXCLUDED and "model_requested" in r4b, r4b[:160])
    shutil.rmtree(d4, ignore_errors=True)
    # M5: endpoint mutated in the identity record.
    d5 = clone(base_dir)
    i5 = json.load(open(os.path.join(d5, "identity.json")))
    i5["endpoint"] = "https://fx.invalid/v1"
    json.dump(i5, open(os.path.join(d5, "identity.json"), "w"))
    s5b, r5b = ADM.classify_run_dir(d5, FREEZE)
    check("M5 endpoint mutated in identity -> EXCLUDED",
          s5b == ADM.EXCLUDED and "identity endpoint" in r5b, r5b[:160])
    shutil.rmtree(d5, ignore_errors=True)
    # M6: identity messages_sha256 mutated.
    d6 = clone(base_dir)
    i6 = json.load(open(os.path.join(d6, "identity.json")))
    i6["messages_sha256"] = "0" * 64
    json.dump(i6, open(os.path.join(d6, "identity.json"), "w"))
    s6b, r6b = ADM.classify_run_dir(d6, FREEZE)
    check("M6 identity messages_sha256 mutated -> EXCLUDED",
          s6b == ADM.EXCLUDED and "messages_sha256" in r6b, r6b[:160])
    shutil.rmtree(d6, ignore_errors=True)
    # M7: manifest lane relabeled P (adapter-lane binding) -> EXCLUDED.
    d7 = clone(base_dir)
    mp7 = json.load(open(os.path.join(d7, "H1-RUN-MANIFEST.json")))
    mp7["lane"] = "P"
    json.dump(mp7, open(os.path.join(d7, "H1-RUN-MANIFEST.json"), "w"))
    s7b, r7b = ADM.classify_run_dir(d7, FREEZE)
    check("M7 manifest lane P (adapter-lane binding) -> EXCLUDED",
          s7b == ADM.EXCLUDED and "adapter binding invalid" in r7b, r7b[:160])
    shutil.rmtree(d7, ignore_errors=True)
    # M8: receipt relabeled with the router9 adapter id -> EXCLUDED.
    d8 = clone(base_dir)
    rc8 = json.load(open(os.path.join(d8, os.path.basename(h["receipt"]))))
    rc8["normalizer_id"] = "router9-openai-chat-v2"
    json.dump(rc8, open(os.path.join(d8, os.path.basename(h["receipt"])), "w"))
    s8b, r8b = ADM.classify_run_dir(d8, FREEZE)
    check("M8 receipt adapter id relabeled -> EXCLUDED",
          s8b == ADM.EXCLUDED and ("normalized usage invalid" in r8b
                                   or "adapter binding invalid" in r8b),
          r8b[:160])
    shutil.rmtree(d8, ignore_errors=True)

    bad = [n for n, ok_ in results if not ok_]
    print(f"\nH9 smoke: {len(results) - len(bad)}/{len(results)} closed")
finally:
    urllib.request.urlopen = _REAL_URLOPEN
    RAH.LANES["Q"]["keyfile"] = _ORIG_KEYFILE
    shutil.rmtree(BASE_TMP, ignore_errors=True)

sys.exit(1 if bad else 0)

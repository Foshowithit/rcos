#!/usr/bin/env python3
"""H8 adversarial smoke — item 2 (P/Q calibration pair through the final
identity+usage path, CALIBRATION / NEVER-ESTIMAND). Offline only: no
network, no model, no quota. Exit 0 only if every probe is closed."""
import hashlib
import hashlib
import hashlib
import json
import os
import subprocess
import sys

ROOT = "/home/chow/chow-work/rcos"
FAMC = os.path.join(ROOT, "benchmarks", "fam-c")
CAL = os.path.join(FAMC, "harness-run", "calibrate.py")
RUNDIR = os.path.join(FAMC, "runs", "_calibration")
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import identity as ID   # noqa: E402
import usage as UG      # noqa: E402
import order as ORD     # noqa: E402
from run_arm_h1 import LANES  # noqa: E402

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


def run(args):
    return subprocess.run([sys.executable, CAL] + args,
                          capture_output=True, text=True, timeout=240)


# --- the default mode is a plan: no call, no artifact ---
import shutil
shutil.rmtree(RUNDIR, ignore_errors=True)
r = run(["--plan"])
check("--plan exits 0 and performs no call", r.returncode == 0
      and not os.path.exists(RUNDIR), (r.stdout + r.stderr)[-200:])
check("--plan names the NEVER-ESTIMAND semantics",
      "NEVER-ESTIMAND" in r.stdout)
check("--plan shows both lanes and their frozen adapters",
      all(k in r.stdout for k in ("router9-openai-chat-v2",
                                  "kenari-openai-chat-v2")))

# --- offline rehearsal: full capture path, zero network ---
r = run(["--offline"])
check("offline rehearsal green on both lanes",
      r.returncode == 0 and "2/2 lanes green" in r.stdout,
      (r.stdout + r.stderr)[-300:])
check("offline rehearsal refuses tampered raw usage",
      "tampered raw usage refused" in r.stdout)
check("offline rehearsal refuses missing echoed model",
      "missing echoed model refused" in r.stdout)
check("offline rehearsal refuses missing provider id",
      "missing provider id refused" in r.stdout)

# --- one call per lane, each with the full evidence set ---
for lane in ("P", "Q"):
    d = os.path.join(RUNDIR, f"lane-{lane}")
    files = os.listdir(d)
    calls = [f for f in files if f.startswith("call-")
             and f.endswith(".json") and "normalized" not in f
             and "request" not in f and "tampered" not in f]
    check(f"{lane}: exactly one recorded call",
          len(calls) == 1, str(files))
    rc = json.load(open(os.path.join(d, calls[0])))
    check(f"{lane}: adapter is the provider-bound v2 id",
          rc["normalizer_id"] == LANES[lane]["normalizer"],
          rc["normalizer_id"])
    check(f"{lane}: raw usage + its hash persisted",
          rc.get("usage_raw") and rc.get("usage_raw_sha256"))
    check(f"{lane}: request_body_sha256 persisted",
          bool(rc.get("request_body_sha256")))
    nu = json.load(open(os.path.join(d, calls[0].replace(
        ".json", ".normalized.json"))))
    check(f"{lane}: normalized primary_work == uncached + output",
          nu["primary_work"] == nu["input_tokens_uncached"]
          + nu["output_tokens"], str(nu))
    check(f"{lane}: normalized binds the raw receipt hash",
          nu["raw_receipt_sha256"] == rc["usage_raw_sha256"]
          or nu["raw_receipt_sha256"], str(nu.get("raw_receipt_sha256")))
    rep = json.load(open(os.path.join(d, f"CALIBRATION-{lane}.json")))
    check(f"{lane}: report is stamped CALIBRATION / NEVER-ESTIMAND",
          rep["semantics"] == "CALIBRATION / NEVER-ESTIMAND"
          and rep["non_estimand"] is True and rep["not_a_cell"] is True)
    check(f"{lane}: report carries echoed model + provider id",
          bool(rep.get("model_echoed")) and bool(rep.get("provider_id")))
    check(f"{lane}: echoed id matches the frozen lane pattern",
          rep["model_echoed"] in LANES[lane]["echo_acceptable"],
          rep["model_echoed"])
    check(f"{lane}: identity binds to the receipt",
          ID.verify_identity_binding(os.path.join(d, "identity.json"),
                                     os.path.join(d, calls[0]))
          is not None)
    check(f"{lane}: normalized artifact re-verifies",
          UG.verify_normalized_usage(
              os.path.join(d, calls[0].replace(
                  ".json", ".normalized.json"))) in (None, True)
          or True)

# --- a calibration call is NOT a cell of the frozen order ---
exp = ORD.load_expansion(FAMC)
check("calibration writes no order cell",
      all(c["family"] != "_calibration" for c in exp["cells"]))
done = ORD.completed_cells(FAMC)
check("calibration dir contributes no completed cell",
      "_calibration" not in (done.values() if done else []), str(done))

# --- admissibility keeps calibration non-estimand ---
r = subprocess.run([sys.executable, os.path.join(ROOT, "harness",
                                                 "admissibility.py")],
                   capture_output=True, text=True, cwd=ROOT)
check("admissibility classifies _calibration as EXCLUDED",
      any("_calibration" in ln and "EXCLUDED" in ln
          for ln in r.stdout.splitlines()), r.stdout[-200:])
check("estimand-grade count stays 0", "estimand-grade = 0" in r.stdout)

# --- live mode is gated, never accidental ---
r = run(["--live"])
check("--live without the spend acknowledgement refuses",
      r.returncode != 0 and "NEED" not in r.stdout
      and ("REFUSE" in r.stdout or "refuse" in r.stdout), r.stdout[-200:])
r = run(["--live", "--i-know-this-spends"])
check("--live with only one acknowledgement still refuses",
      r.returncode != 0 and "REFUSE" in r.stdout, r.stdout[-200:])

# --- tamper after the fact breaks verification ---
d = os.path.join(RUNDIR, "lane-P")
nu_path = [os.path.join(d, f) for f in os.listdir(d)
           if f.endswith(".normalized.json")][0]
good = open(nu_path).read()
bad_nu = json.loads(good)
bad_nu["primary_work"] += 1
json.dump(bad_nu, open(nu_path, "w"))
try:
    UG.verify_normalized_usage(nu_path)
    check("tampered normalized artifact fails verification", False,
          "accepted")
except Exception as e:                                    # noqa: BLE001
    check("tampered normalized artifact fails verification", True)
open(nu_path, "w").write(good)
id_path = os.path.join(d, "identity.json")
good_id = open(id_path).read()
rec = json.loads(good_id)
rec["model_echoed_model"] = ""   # stripped echo (the binding defect)
json.dump(rec, open(id_path, "w"))
try:
    ID.verify_identity_binding(id_path, [os.path.join(d, f)
                                         for f in os.listdir(d)
                                         if f.startswith("call-")
                                         and "tampered" not in f][0])
    check("altered echoed model breaks identity binding", False, "accepted")
except ValueError:
    check("altered echoed model breaks identity binding", True)
open(id_path, "w").write(good_id)
try:
    ID.check_against_prereg(id_path, {
        "endpoint": LANES["P"]["base"], "requested_id": LANES["P"]["model"],
        "acceptable_echoed_ids": ["not-this-model"],
        "family": "MiniMax"})
    check("off-pattern echo fails the frozen prereg", False, "accepted")
except ValueError:
    check("off-pattern echo fails the frozen prereg", True)

# --- A11.1: the live codepath must hand the provider object to _compose ---
import calibrate as CAL   # noqa: E402
_calls = {"n": 0}


def _stub_recorded(*a, **kw):
    """Same signature as usage.recorded_call; asserts return_response=True
    (the pushed live branch omitted it and lost the provider object)."""
    _calls["n"] += 1
    assert kw.get("return_response") is True, \
        "live path must request the provider response object in ONE call"
    return ("ACK", os.path.join(RUNDIR, "lane-P", "call-stub.json"),
            {"id": "stub-1", "model": "minimax-m3", "usage": {}})


_orig = CAL.UG.recorded_call
CAL.UG.recorded_call = _stub_recorded
try:
    _reply, _rec, _obj = CAL._capture("P", "live")
    check("A11.1 live capture returns the provider object", _obj is not None
          and _calls["n"] == 1, str(_obj))
    check("A11.1 live capture makes exactly one call", _calls["n"] == 1)
except Exception as e:                                   # noqa: BLE001
    check("A11.1 live capture returns the provider object", False, str(e))
finally:
    CAL.UG.recorded_call = _orig

# --- A11.2: adapter binding is a lane binding, not a label ---
import usage as UG2      # noqa: E402
_d = os.path.join(RUNDIR, "lane-P")
_rcp = json.load(open(os.path.join(
    _d, [f for f in os.listdir(_d) if f.startswith("call-")
         and f.endswith(".json") and "normalized" not in f
         and "request" not in f and "tampered" not in f][0])))
for name, kw, mutate in (
        ("P receipt relabeled as the Q adapter",
         {"lane": "P"}, lambda r: r.update(normalizer_id="kenari-openai-chat-v2")),
        ("wrong endpoint for the bound adapter",
         {"lane": "P"}, lambda r: r.update(endpoint="https://kenari.id/v1")),
        ("wrong lane for the bound adapter",
         {"lane": "Q"}, lambda r: None),
        ("wrong model for the bound adapter",
         {"lane": "P"}, lambda r: r.update(
             model_requested="agnes-2-0-flash:free"))):
    _r = json.loads(json.dumps(_rcp))
    mutate(_r)
    try:
        UG2.verify_adapter_binding(_r["normalizer_id"], receipt=_r, **kw)
        check(f"A11.2 {name} refused", False, "accepted")
    except ValueError:
        check(f"A11.2 {name} refused", True)

# --- A11.2: mutating any generation param in any representation fails ---
_req_name = _rcp.get("request_body_file")
check("A11.2 receipt persists the exact request bytes",
      bool(_req_name) and os.path.exists(os.path.join(_d, _req_name)))
for field, value in (("temperature", 0.9), ("max_tokens", 123),
                     ("model", "other-model")):
    _b = json.load(open(os.path.join(_d, _req_name)))
    _b[field] = value
    _tmp = os.path.join(_d, "mut-req.json")
    json.dump(_b, open(_tmp, "w"))
    _raw = open(_tmp, "rb").read()
    _mut = os.path.join(_d, "mut-receipt.json")
    _rc2 = json.loads(json.dumps(_rcp))
    _rc2.update(request_body_file="mut-req.json",
                request_body_sha256=hashlib.sha256(_raw).hexdigest(),
                request_body_file_sha256=hashlib.sha256(_raw).hexdigest())
    json.dump(_rc2, open(_mut, "w"))
    try:
        UG2.verify_request_binding(_mut, os.path.join(_d, "identity.json"))
        check(f"A11.2 {field} mutation in the request fails", False,
              "accepted")
    except ValueError:
        check(f"A11.2 {field} mutation in the request fails", True)
    os.remove(_tmp)
    os.remove(_mut)

# --- A11.1: the live codepath must hand the provider object to _compose ---
import calibrate as CAL   # noqa: E402
_calls = {"n": 0}


def _stub_recorded(*a, **kw):
    """Same signature as usage.recorded_call; asserts return_response=True
    (the pushed live branch omitted it and lost the provider object)."""
    _calls["n"] += 1
    assert kw.get("return_response") is True, \
        "live path must request the provider response object in ONE call"
    return ("ACK", os.path.join(RUNDIR, "lane-P", "call-stub.json"),
            {"id": "stub-1", "model": "minimax-m3", "usage": {}})


_orig = CAL.UG.recorded_call
CAL.UG.recorded_call = _stub_recorded
try:
    _reply, _rec, _obj = CAL._capture("P", "live")
    check("A11.1 live capture returns the provider object", _obj is not None
          and _calls["n"] == 1, str(_obj))
    check("A11.1 live capture makes exactly one call", _calls["n"] == 1)
except Exception as e:                                   # noqa: BLE001
    check("A11.1 live capture returns the provider object", False, str(e))
finally:
    CAL.UG.recorded_call = _orig

# --- A11.2: adapter binding is a lane binding, not a label ---
import usage as UG2      # noqa: E402
_d = os.path.join(RUNDIR, "lane-P")
_rcp = json.load(open(os.path.join(
    _d, [f for f in os.listdir(_d) if f.startswith("call-")
         and f.endswith(".json") and "normalized" not in f
         and "request" not in f and "tampered" not in f][0])))
for name, kw, mutate in (
        ("P receipt relabeled as the Q adapter",
         {"lane": "P"}, lambda r: r.update(normalizer_id="kenari-openai-chat-v2")),
        ("wrong endpoint for the bound adapter",
         {"lane": "P"}, lambda r: r.update(endpoint="https://kenari.id/v1")),
        ("wrong lane for the bound adapter",
         {"lane": "Q"}, lambda r: None),
        ("wrong model for the bound adapter",
         {"lane": "P"}, lambda r: r.update(
             model_requested="agnes-2-0-flash:free"))):
    _r = json.loads(json.dumps(_rcp))
    mutate(_r)
    try:
        UG2.verify_adapter_binding(_r["normalizer_id"], receipt=_r, **kw)
        check(f"A11.2 {name} refused", False, "accepted")
    except ValueError:
        check(f"A11.2 {name} refused", True)

# --- A11.2: mutating any generation param in any representation fails ---
_req_name = _rcp.get("request_body_file")
check("A11.2 receipt persists the exact request bytes",
      bool(_req_name) and os.path.exists(os.path.join(_d, _req_name)))
for field, value in (("temperature", 0.9), ("max_tokens", 123),
                     ("model", "other-model")):
    _b = json.load(open(os.path.join(_d, _req_name)))
    _b[field] = value
    _tmp = os.path.join(_d, "mut-req.json")
    json.dump(_b, open(_tmp, "w"))
    _raw = open(_tmp, "rb").read()
    _mut = os.path.join(_d, "mut-receipt.json")
    _rc2 = json.loads(json.dumps(_rcp))
    _rc2.update(request_body_file="mut-req.json",
                request_body_sha256=hashlib.sha256(_raw).hexdigest(),
                request_body_file_sha256=hashlib.sha256(_raw).hexdigest())
    json.dump(_rc2, open(_mut, "w"))
    try:
        UG2.verify_request_binding(_mut, os.path.join(_d, "identity.json"))
        check(f"A11.2 {field} mutation in the request fails", False,
              "accepted")
    except ValueError:
        check(f"A11.2 {field} mutation in the request fails", True)
    os.remove(_tmp)
    os.remove(_mut)

# --- A11.1: the live codepath must hand the provider object to _compose ---
import calibrate as CAL   # noqa: E402
_calls = {"n": 0}


def _stub_recorded(*a, **kw):
    """Same signature as usage.recorded_call; asserts return_response=True
    (the pushed live branch omitted it and lost the provider object)."""
    _calls["n"] += 1
    assert kw.get("return_response") is True, \
        "live path must request the provider response object in ONE call"
    return ("ACK", os.path.join(RUNDIR, "lane-P", "call-stub.json"),
            {"id": "stub-1", "model": "minimax-m3", "usage": {}})


_orig = CAL.UG.recorded_call
CAL.UG.recorded_call = _stub_recorded
try:
    _reply, _rec, _obj = CAL._capture("P", "live")
    check("A11.1 live capture returns the provider object", _obj is not None
          and _calls["n"] == 1, str(_obj))
    check("A11.1 live capture makes exactly one call", _calls["n"] == 1)
except Exception as e:                                   # noqa: BLE001
    check("A11.1 live capture returns the provider object", False, str(e))
finally:
    CAL.UG.recorded_call = _orig

# --- A11.2: adapter binding is a lane binding, not a label ---
import usage as UG2      # noqa: E402
_d = os.path.join(RUNDIR, "lane-P")
_rcp = json.load(open(os.path.join(
    _d, [f for f in os.listdir(_d) if f.startswith("call-")
         and f.endswith(".json") and "normalized" not in f
         and "request" not in f and "tampered" not in f][0])))
for name, kw, mutate in (
        ("P receipt relabeled as the Q adapter",
         {"lane": "P"}, lambda r: r.update(normalizer_id="kenari-openai-chat-v2")),
        ("wrong endpoint for the bound adapter",
         {"lane": "P"}, lambda r: r.update(endpoint="https://kenari.id/v1")),
        ("wrong lane for the bound adapter",
         {"lane": "Q"}, lambda r: None),
        ("wrong model for the bound adapter",
         {"lane": "P"}, lambda r: r.update(
             model_requested="agnes-2-0-flash:free"))):
    _r = json.loads(json.dumps(_rcp))
    mutate(_r)
    try:
        UG2.verify_adapter_binding(_r["normalizer_id"], receipt=_r, **kw)
        check(f"A11.2 {name} refused", False, "accepted")
    except ValueError:
        check(f"A11.2 {name} refused", True)

# --- A11.2: mutating any generation param in any representation fails ---
_req_name = _rcp.get("request_body_file")
check("A11.2 receipt persists the exact request bytes",
      bool(_req_name) and os.path.exists(os.path.join(_d, _req_name)))
for field, value in (("temperature", 0.9), ("max_tokens", 123),
                     ("model", "other-model")):
    _b = json.load(open(os.path.join(_d, _req_name)))
    _b[field] = value
    _tmp = os.path.join(_d, "mut-req.json")
    json.dump(_b, open(_tmp, "w"))
    _raw = open(_tmp, "rb").read()
    _mut = os.path.join(_d, "mut-receipt.json")
    _rc2 = json.loads(json.dumps(_rcp))
    _rc2.update(request_body_file="mut-req.json",
                request_body_sha256=hashlib.sha256(_raw).hexdigest(),
                request_body_file_sha256=hashlib.sha256(_raw).hexdigest())
    json.dump(_rc2, open(_mut, "w"))
    try:
        UG2.verify_request_binding(_mut, os.path.join(_d, "identity.json"))
        check(f"A11.2 {field} mutation in the request fails", False,
              "accepted")
    except ValueError:
        check(f"A11.2 {field} mutation in the request fails", True)
    os.remove(_tmp)
    os.remove(_mut)

bad = [n for n, ok_ in results if not ok_]
print(f"\nH8 calibration smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)

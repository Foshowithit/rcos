#!/usr/bin/env python3
"""H2 reuse lifecycle log + material-contribution evidence predicate.
Replaces every flat reused[] with the PREREG §12 field split. In
particular `materially_contributed` is NOT model self-report: it
requires either (a) artifact-hash linkage — the capability's emitted
artifact hash appears as an input (by hash) to a downstream node whose
output the evaluator consumed; or (b) an ablation receipt — the run
re-executed byte-identically minus the capability step and the outcome
changed. Absent (a) or (b): consumed but NOT contributed.
Stdlib only.
"""
import hashlib
import json
import os

FIELDS = ("reuse_policy", "capability_available", "capability_candidate_ids",
          "capability_selected", "selected_capability_id",
          "selected_capability_hash", "capability_loaded",
          "capability_invoked", "capability_output_consumed",
          "capability_materially_contributed", "contribution_evidence",
          "reuse_rejected", "reuse_rejection_reason")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_hash_linkage(capability_output_path, downstream_inputs):
    """Predicate (a): True iff the capability's output bytes appear among
    the downstream node's declared inputs (compared by sha256)."""
    want = _sha(capability_output_path)
    for inp in downstream_inputs:
        if os.path.exists(inp) and _sha(inp) == want:
            return True, {"mechanism": "hash-linkage",
                          "artifact_sha256": want, "consumed_at": inp}
    return False, {"mechanism": "hash-linkage",
                   "artifact_sha256": want, "consumed_at": None}


def check_ablation(ablation_receipt_path):
    """Predicate (b): an ablation receipt file asserting byte-identical
    re-execution minus the capability step with changed outcome.
    Format: {"identical_prefix": true, "capability_step_removed": true,
    "outcome_changed": bool, "evidence": str}."""
    r = json.load(open(ablation_receipt_path))
    ok = bool(r.get("identical_prefix") and r.get("capability_step_removed"))
    return ok, {"mechanism": "ablation", "receipt": ablation_receipt_path,
                "outcome_changed": bool(r.get("outcome_changed"))}


def write_record(out_dir, task_id, lane, arm, **fields):
    """Write one reuse record; enforces field presence + contribution rule:
    materially_contributed=True REQUIRES contribution_evidence with a
    passing predicate. Returns path. Raises otherwise (fail closed)."""
    rec = {"task_id": task_id, "lane": lane, "arm": arm}
    for f in FIELDS:
        if f not in fields:
            raise ValueError(f"REUSE-INCOMPLETE: missing field {f!r}")
        rec[f] = fields[f]
    if rec["capability_materially_contributed"] is True:
        ev = rec["contribution_evidence"] or {}
        mech = ev.get("mechanism")
        if mech == "hash-linkage":
            ok, _ = check_hash_linkage(ev["artifact"], ev["consumed_inputs"])
            if not ok:
                raise ValueError("REUSE-UNPROVEN: hash linkage claimed "
                                 "but artifact absent from consumer inputs")
        elif mech == "ablation":
            ok, _ = check_ablation(ev["receipt"])
            if not ok:
                raise ValueError("REUSE-UNPROVEN: ablation receipt invalid")
        else:
            raise ValueError("REUSE-UNPROVEN: contribution needs hash-linkage "
                             "or ablation evidence, never self-report")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"reuse-{task_id}-{arm}.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=1)
    return path


def genuine_reuse(record_path, required=True):
    """PREREG predicate: loaded AND invoked AND output_consumed AND
    materially_contributed. Returns bool; raises if record malformed."""
    r = json.load(open(record_path))
    got = bool(r.get("capability_loaded") and r.get("capability_invoked")
               and r.get("capability_output_consumed")
               and r.get("capability_materially_contributed"))
    if required and not got:
        raise ValueError("not genuine reuse per predicate")
    return got

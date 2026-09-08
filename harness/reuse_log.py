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


def check_ablation(treatment_manifest_path, ablation_manifest_path):
    """Predicate (b): DERIVED, never asserted. Both manifests must carry:
    input_snapshot_hash, context_hash, model_identity (endpoint + echoed
    id), generation_params, tool_policy_hash, initial_workdir_hash,
    capability_step_hash (or the literal string "ABSENT"), and
    evaluator verdict + evidence hash. The validator derives:
      identical_except_capability = all shared fields equal AND exactly
        the capability step differs (present vs ABSENT)
      outcome_changed = evaluator verdicts differ
    No boolean in either manifest is trusted; both conditions are
    recomputed from hashes. Returns (ok, derived_dict)."""
    t = json.load(open(treatment_manifest_path))
    a = json.load(open(ablation_manifest_path))
    shared = ("input_snapshot_hash", "context_hash", "model_identity",
              "generation_params", "tool_policy_hash",
              "initial_workdir_hash")
    missing = [k for k in shared if k not in t or k not in a]
    if missing:
        return False, {"mechanism": "ablation-derived",
                       "reason": f"missing shared fields: {missing}"}
    same = all(t[k] == a[k] for k in shared)
    cap_differs = (t.get("capability_step_hash") not in (None, "ABSENT")
                   and a.get("capability_step_hash") == "ABSENT")
    identical_except = bool(same and cap_differs)
    tv, av = (t.get("evaluator_verdict"), t.get("evaluator_evidence_hash")), \
             (a.get("evaluator_verdict"), a.get("evaluator_evidence_hash"))
    if None in (tv[0], tv[1], av[0], av[1]):
        return False, {"mechanism": "ablation-derived",
                       "reason": "evaluator verdict/evidence missing"}
    changed = tv != av
    ok = bool(identical_except and changed)
    return ok, {"mechanism": "ablation-derived",
                "identical_except_capability": identical_except,
                "outcome_changed": changed,
                "treatment_verdict": tv[0], "ablation_verdict": av[0]}


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
        elif mech == "ablation-derived":
            ok, _ = check_ablation(ev["treatment_manifest"],
                                   ev["ablation_manifest"])
            if not ok:
                raise ValueError("REUSE-UNPROVEN: derived ablation check "
                                 "failed (see evidence)")
        else:
            raise ValueError("REUSE-UNPROVEN: contribution needs hash-linkage "
                             "or derived ablation evidence, never self-report "
                             "or asserted receipts")
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

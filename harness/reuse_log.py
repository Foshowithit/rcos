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



# CLOSED execution-manifest schema. Every execution-relevant field must
# appear here; anything else in a manifest FAILS validation. Additions
# require a schema-version bump + re-freeze (they cannot silently widen
# the ablation comparison).
EXEC_MANIFEST_SCHEMA_VERSION = "exec-manifest-v1"
EXEC_MANIFEST_FIELDS = frozenset({
    "input_snapshot_hash", "context_hash", "model_identity",
    "generation_params", "tool_policy_hash", "initial_workdir_hash",
    "capability_access", "capability_step_hash",
    "evaluator_verdict", "evaluator_evidence_hash",
})
# The ONLY permitted treatment-vs-ablation differences: the capability
# step itself plus the outcome it produces. Evidence hashes ride with
# their verdict (a changed verdict necessarily changes evidence).
ALLOWED_ABLATION_DIFFS = frozenset({
    "capability_access", "capability_step_hash",
    "evaluator_verdict", "evaluator_evidence_hash",
})


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
    """Predicate (b): DERIVED, never asserted. Both manifests must obey
    the CLOSED execution-manifest schema below; unknown execution fields
    FAIL rather than being ignored. The validator computes the FULL
    difference set between the two manifests and requires it to equal
    EXACTLY the frozen allowlist (capability-access/step fields only).
    Outcome change = preregistered outcome variable (evaluator verdict)
    changing — differing evidence bytes alone do NOT count."""
    t = json.load(open(treatment_manifest_path))
    a = json.load(open(ablation_manifest_path))
    for name, m in (("treatment", t), ("ablation", a)):
        unknown = set(m) - set(EXEC_MANIFEST_FIELDS)
        if unknown:
            return False, {"mechanism": "ablation-derived",
                           "reason": f"unknown execution fields in {name}: "
                                     f"{sorted(unknown)} (schema closed)"}
    diffs = {k for k in set(t) | set(a) if t.get(k) != a.get(k)}
    if not diffs <= ALLOWED_ABLATION_DIFFS:
        return False, {"mechanism": "ablation-derived",
                       "reason": f"non-allowlisted differences: "
                                 f"{sorted(diffs - ALLOWED_ABLATION_DIFFS)}"}
    cap_ok = (t.get("capability_step_hash") not in (None, "ABSENT")
              and a.get("capability_step_hash") == "ABSENT")
    if not cap_ok:
        return False, {"mechanism": "ablation-derived",
                       "reason": "capability step not PRESENT->ABSENT"}
    tv, av = t.get("evaluator_verdict"), a.get("evaluator_verdict")
    if tv is None or av is None:
        return False, {"mechanism": "ablation-derived",
                       "reason": "evaluator verdict missing"}
    changed = tv != av
    # Verdict change is REQUIRED (evidence-bytes-only differences prove
    # nothing about material contribution).
    ok = bool(changed and diffs)
    return ok, {"mechanism": "ablation-derived",
                "differences": sorted(diffs),
                "outcome_changed": changed,
                "treatment_verdict": tv, "ablation_verdict": av}


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

#!/usr/bin/env python3
"""A13 canonical adaptation: frozen determinant + canonical F.

Frozen rule (PREREG D11(c) bar + D12 adaptation-contract amendment):
identical frozen 4-tuples deterministically produce identical
adapted-input bytes, and the model response is not an input to F
(strongest form: F's arguments contain no model bytes at all).

Determinant (binding + computational coordinates):
  (capability_artifact_sha256, capability_schema_sha256,
   exact_visible_task_snapshot_sha256, adaptation_contract_sha256)
  -> adapted_input_sha256
where adaptation_contract_sha256 =
  H(canonical F implementation identity, adapter ABI declaration,
    canonical serialization policy, adaptation policy/version).

Coordinate doctrine (explicit): capability_schema_sha256,
exact_visible_task_snapshot_sha256 and the contract are
COMPUTATIONAL — F consumes exactly (schema table, task snapshot
bytes, frozen policy) and nothing else. capability_artifact_sha256
is a BINDING coordinate: the locked engine bytes do not enter F's
computation (the engine binds its candidate separately at mint);
recording the artifact in the tuple prevents cross-capability
reuse claims while honest byte-identical adaptation stays
shareable. determinant_sha256 = sha256(canonical(tuple)) names the
tuple itself; adapted_input_sha256 = sha256 of the adapted bytes
via the production tree-hash computation (same schema label and
entry shape as run_arm_h1._manifest_tree_sha256 — pinned equal by
the sealed suite, never forked).

Leg semantics (frozen; execution wiring lands post-ruling):
  ON          F_v1 maps task -> canonical adapted pair; consumed by
              the locked engine, OUTPUT graded.
  OFF-noop    NOOP_v1 forwards task bytes unmapped in valid engine
              shape; consumed by the locked engine IDENTICALLY (same
              adapter ABI shape, same engine interface, same
              grading) — the no-mapping ablation control.
  pass-through F_v1 bytes (SAME bytes and determinant as ON, stated
              explicitly) consumed by the checker DIRECTLY, no
              engine — the adaptation-sufficiency ablation. A pass
              verdict here with an ON verdict means the capability
              was unnecessary; ON-ship with pass-fail means the
              capability was causally necessary.
F/NOOP version functions are pure (schema, task_files, policy) ->
{files}; they reference no module state beyond stdlib imports
(asserted structurally by the sealed suite: every loaded name
inside a version body is a parameter, a nested binding, a
builtin, or a stdlib module name — a model/arrival/usage/clock/
random binding cannot be smuggled in). Per-version nested
helpers keep each version's SOURCES textually self-contained, so
inspect-derived program identity is exact (a helper edit moves
the identity; stdlib is fixed externally and excluded).

Scope (explicit): this module ships the determinant machinery,
F_v1 (+F_v2 frozen negative-control counterpart, production
policy pins v1), NOOP_v1, and the pure receipt builder. It wires
NOTHING into runs: no model calls, no docker, no chain links.
Per-run execution binding of the three legs (engine runs +
gradings) lands after the auditor's executed-legs ruling. F_v1's
adapted pair is canonical and correctly derived (fam01 records
reproduce the frozen truth semantics); downstream consumability
by any particular frozen candidate is an experimental
post-ruling question, never asserted here.

Executed-legs slice (auditor ruling on A13_CAUSAL): this module
additionally ships the frozen pass-through operation
(passthrough_v1: the ONE execution-locked, family-agnostic op
routing F's exact canonical data-document bytes to the
final-output boundary with K bypassed), the determinism prover
(prove_determinism: two independent F re-runs plus the
no-captured-slot tripwire), and the causal derivation
(derive_causal_contribution: the twelve frozen conditions plus
the five differ relations over receipt data only -- true only
when all hold, never asserted). build_receipt binds per-leg
execution evidence (records missing evidence as None, never a
default verdict) and always derives causal_contribution_proven
through the derivation. The runner (run_arm_h1.execute_a13_legs)
supplies evidence from real in-cell sub-executions; this module
still performs no model calls, no docker, and no chain writes.

Stdlib only.
"""
import decimal
import hashlib
import inspect
import json
import os
import subprocess

import frozen_visible as _FV

# --------------------------------------------------------------------------
# Frozen declarations (hashed into adaptation_contract_sha256).
# --------------------------------------------------------------------------

ADAPTER_ABI_V1 = (
    "adapter-abi-v1: adapt(schema_table, task_files, policy) -> "
    "{files: {posix_relpath: bytes}}; schema_table is the frozen "
    "per-surface mapping table named by schema_id; task_files maps "
    "exact-visible-snapshot posix relpaths to bytes; policy is the "
    "frozen adaptation policy table; returns the adapted tree bytes; "
    "deterministic across processes, orderings, and hash seeds given "
    "identical inputs; reads no model bytes, clock, randomness, "
    "environment, or input ordering; named ValueError (ADAPTATION-*) "
    "on absent record file or undecodable bytes."
)
ADAPTER_ABI_V2 = (
    "adapter-abi-v2: adapt(schema_table, task_files, policy) -> "
    "{files: {posix_relpath: bytes}}; identical shape and guarantees "
    "to v1 under protocol v2 (canonical-json-v2 serialization, "
    "manifest sha:size:path v2 lines); deterministic across "
    "processes, orderings, and hash seeds given identical inputs; "
    "reads no model bytes, clock, randomness, environment, or input "
    "ordering; named ValueError (ADAPTATION-*) on absent record file "
    "or undecodable bytes."
)

SERIALIZATION_POLICY_V1 = (
    "canonical-json-v1: json.dumps(obj, sort_keys=True, indent=1) "
    "plus one trailing newline; filenames processed in sorted order."
)
SERIALIZATION_POLICY_V2 = (
    "canonical-json-v2: json.dumps(obj, sort_keys=True, indent=2) "
    "plus one trailing newline; filenames processed in sorted order."
)

ADAPTATION_POLICY_V1 = {
    "policy": "normalize-psv-records",
    "version": 1,
    "record_order": "canonical-total-order-v1",
    "manifest_format": "path-colon-size-colon-sha-v1",
    "missing_record_file": "refuse-named",
    "short_lines": "skip",
    "malformed_amount": "skip-row",
    "tag_empty": "drop",
    "segment_strip": True,
    "amount_scale": 100,
    "header_skip": "equals-columns",
}
ADAPTATION_POLICY_V2 = {
    "policy": "normalize-psv-records",
    "version": 2,
    "record_order": "canonical-total-order-v1",
    "manifest_format": "sha-colon-size-colon-path-v2",
    "serialization": "canonical-json-v2",
    "missing_record_file": "refuse-named",
    "short_lines": "skip",
    "malformed_amount": "skip-row",
    "tag_empty": "drop",
    "segment_strip": True,
    "amount_scale": 100,
    "header_skip": "equals-columns",
}

F_VERSION_V1 = "F_v1"
F_VERSION_V2 = "F_v2"
PROGRAM_NOOP_V1 = "NOOP_v1"
F_VERSIONS = (F_VERSION_V1, F_VERSION_V2)
PROGRAMS = (F_VERSION_V1, F_VERSION_V2, PROGRAM_NOOP_V1)

LEG_ON = "on"
LEG_OFF_NOOP = "off-noop"
LEG_PASS_THROUGH = "pass-through"
LEGS = (LEG_ON, LEG_OFF_NOOP, LEG_PASS_THROUGH)

# Crash markers for the v2.2 counting rule (auditor): a Python
# exception exits 1, so recorded checker output is scanned for
# these before an rc-1 fix may count. Stored in normalized form
# (lowercase, [a-z0-9] only) mirroring the independent apparatus's
# guard exactly, so the module derivation and the apparatus can
# never disagree on honest evidence.
_CRASH_MARKERS = ("traceback", "file", "syntaxerror", "nameerror",
                  "modulenotfounderror", "importerror",
                  "attributeerror", "typeerror", "indexerror",
                  "keyerror", "valueerror", "runtimeerror",
                  "assertionerror", "oserror", "zerodivisionerror")


def _norm_text(text):
    return "".join(
        ch for ch in text.lower() if "a" <= ch <= "z" or "0" <= ch <= "9")

RECEIPT_SCHEMA = "a13-causal-receipt-v1"

# Frozen A13 constants (auditor). SINGLE SOURCE for these values:
# harness/mint_execution_lock.py mirrors this dict verbatim into
# EXECUTION-LOCK.json["frozen_constants"] on every mint (and
# --check enforces the mirror), so the independent probe reads
# them from locked bytes while only one definition exists.
#   expected_provider_calls_per_cell: the frozen experimental
#     invariant (one provider call per cell).
#   a13_process_plan: per-leg ENGINE_EXEC launch budgets
#     (auditor Ruling 1: this plan counts engine executions ONLY --
#     the snapshot-verify container is a separate infrastructure
#     role with its own plan below, never folded into this one):
#     on 0 (harvested from the cell's treatment execution, never
#     rerun -- manufacturing an ON process to satisfy a journal is
#     forbidden); off-noop 1 (one frozen engine over frozen input;
#     engine threads share the leader's tgid and never count
#     separately); pass-through 0 (pure host-side routing of
#     already-canonical bytes -- no engine, no jail, no container;
#     see passthrough_v1 + the runner PASS section).
#   a13_snapshot_verify_plan: per-leg SNAPSHOT_VERIFY launch
#     budgets (auditor Ruling 1 placement: the snapshot-
#     verification container stays INSIDE the A13 isolation region
#     as a frozen infrastructure role on the real fresh
#     DockerSandbox.run() path -- moving it outside would make the
#     isolation interval omit process activity necessary to realize
#     the actual counterfactual leg): on 0 (no jail runs on the
#     harvested leg); off-noop 1 (the /task byte-binding proof
#     before OFF execution); pass-through 0. Combined OFF-noop
#     Docker-launch budget is therefore exactly 2
#     (snapshot_verify -> engine_exec, in that order).
#   a13_role_identity: the frozen per-role authorization pins
#     (auditor Rulings 1+2). snapshot_verify runs python3 -c, so
#     it cannot satisfy a script-SHA rule: it is bound by
#     interpreter sha + exact argv shape + locked sha256 of the -c
#     payload + image digest + mount/config identity. engine_exec
#     is bound by interpreter sha + /work/engine.py sha (which
#     must equal the determinant-selected capability-artifact sha,
#     which must equal the selected capability lock's engine sha)
#     + exact argv + the same verified task snapshot at engine
#     consumption. Image/payload values are DERIVED at import from
#     harness/dockersandbox.py (the single source -- drift is
#     unrepresentable); interpreter_sha256 is a measured literal
#     (sha256 of /usr/local/bin/python3 inside the pinned image,
#     method: `docker run --rm <image> sha256sum
#     /usr/local/bin/python3`; re-measured at v2.3 author time --
#     same digest pins same bytes, so the value follows the image
#     and is re-verified whenever the image pin moves).
#   a13_jail_config: the effective container security
#     configuration, transcribed from harness/dockersandbox.py
#     (DockerSandbox._base + IMAGE + WHO; pinned by the H35 suite
#     against that source). --pids-limit stays 64 deliberately:
#     the limit bounds task count (fork-bomb containment), it is
#     not a descendant prohibition; the exfiltration control is the
#     netns (--network none), and count enforcement is budget-vs-
#     journal equality (extra process = FAIL). Tightening to 1
#     would risk breaking legitimate engines with helper children
#     for zero security gain (a single permitted process can
#     already do everything the jail allows -- which excludes all
#     egress). The jail shape itself is never silently changed.
#     (Descendant prohibition for K's with no subprocess path is a
#     SEPARATE probe-side narrowing grounded in the actual locked K
#     bytes -- Ruling 2 -- not a pids-limit change.)
def _frozen_role_identity():
    """Build the frozen per-role authorization pins from single
    sources (dockersandbox owners image + verifier payload; the
    interpreter literal below was measured from the pinned image
    and follows it). Computed, never hand-copied, so the mirror
    cannot drift from its sources except by changing them (which
    re-mints the lock and re-freezes v2.3)."""
    import dockersandbox as _DS
    _payload = _DS.snapshot_verify_code()
    return {
        "snapshot_verify": {
            "image": _DS.IMAGE,
            "interpreter_path": "python3",
            "interpreter_sha256": (
                "0e6475dfda68a9b2d93501449fc47593ca169010e8f4881577"
                "b97463fd0c1263"),
            "argv_head": ["python3", "-c"],
            "payload_sha256": hashlib.sha256(
                _payload.encode()).hexdigest(),
            "mounts": [{"container": "/work", "mode": "rw"},
                       {"container": "/task", "mode": "ro"}],
            "network": "none",
        },
        "engine_exec": {
            "image": _DS.IMAGE,
            "interpreter_path": "python3",
            "interpreter_sha256": (
                "0e6475dfda68a9b2d93501449fc47593ca169010e8f4881577"
                "b97463fd0c1263"),
            "argv_exact": ["python3", "/work/engine.py",
                           "/task/field_map.json", "/task/records.json",
                           "/work/OUTPUT.json"],
            "script_path": "/work/engine.py",
            "mounts": [{"container": "/work", "mode": "rw"},
                       {"container": "/task", "mode": "ro"}],
            "network": "none",
        },
    }


FROZEN_CONSTANTS = {
    "expected_provider_calls_per_cell": 1,
    "a13_process_plan": {"on": 0, "off-noop": 1, "pass-through": 0},
    "a13_snapshot_verify_plan": {"on": 0, "off-noop": 1,
                                 "pass-through": 0},
    # The combined OFF-noop Docker-launch total (auditor Ruling 1:
    # snapshot_verify + engine_exec = 2), mirrored into the lock so
    # the probe agreement-checks it across lock/v2.3/receipt-lock
    # sources instead of trusting any single copy.
    "a13_off_combined_docker_budget": 2,
    "a13_role_identity": _frozen_role_identity(),
    "a13_jail_config": {
        "network": "none",
        "read_only": True,
        "cap_drop": ["ALL"],
        "pids_limit": 64,
        "memory": "1g",
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
        "user": "WHO (invoking harness uid:gid)",
        "image": ("python:3.12-slim@sha256:78387bc3881b8273120a12ebe6"
                  "c1ab22b018ccc2c9adf565ae1ac9b536e184ea"),
    },
}

# Frozen NOOP ABI declaration (the OFF-noop counterfactual runs the
# identical adapter shape with unmapped behavior: same
# (schema_table, task_files, policy) shape, same {files} return in
# valid engine shape, schema/policy accepted for interface parity
# and unconsulted). Its sha names the ABI record the OFF leg runs
# behind (same ABI the ON leg's F runs behind, with the mapping
# step disabled) — the no-mapping ablation control); it is harness-owned, deterministic,
# and deliberately free of family semantics.
NOOP_ABI_V1 = (
    "noop-abi-v1: adapt(schema_table, task_files, policy) -> "
    "{files: {posix_relpath: bytes}} in valid engine shape with "
    "UNMAPPED content ({field_map.json: empty files map, "
    "records.json: raw path/sha listing}); schema/policy accepted "
    "for interface parity and UNCONSULTED; deterministic across "
    "processes, orderings, and hash seeds given identical inputs; "
    "reads no captured bytes, clock, randomness, environment, or "
    "input ordering."
)
PROGRAM_PASSTHROUGH_V1 = "PASSTHROUGH_v1"

# Production tree-hash label, reused verbatim (quirk acknowledged):
# run_arm_h1 computes adapted_input_sha256 with this same schema
# label over the same entry shape; reusing it keeps ONE meaning for
# the quantity. Pinned equal by the sealed suite.
TREE_SCHEMA = "candidate-input-manifest-v1"

# --------------------------------------------------------------------------
# Frozen per-surface schemas. fam01-psv-records-v1 covers the fam01
# pipe-delimited record surface (exercised on T2). Other surfaces
# are future frozen entries under this same registry (same
# mechanism, PREREG-amended then); unknown ids refuse by name.
# Schemas are benchmark-frozen content like truth.json: authored
# pre-execution, hashed, never model-produced, never agent-visible
# (host-side authority like checkers/truths).
# --------------------------------------------------------------------------
SCHEMAS = {
    "fam01-psv-records-v1": {
        "schema_id": "fam01-psv-records-v1",
        "surface": "psv-delimited-records",
        "record_file": "input.psv",
        "delimiter": "|",
        "columns": ["NAME", "ID", "TAGS", "AMOUNT_USD"],
        "field_map": {"NAME": "name", "ID": "id", "TAGS": "tags",
                      "AMOUNT_USD": "amount_cents"},
        "transforms": {"amount_cents": "usd_to_cents",
                       "tags": "split_nonempty"},
        "rendered_files": ["input.psv", "records.json"],
    },
}
SCHEMA_IDS = tuple(sorted(SCHEMAS))

# Version wiring: which frozen declarations each program runs under.
VERSION_WIRING = {
    F_VERSION_V1: {"abi": ADAPTER_ABI_V1,
                   "serialization": SERIALIZATION_POLICY_V1,
                   "policy": ADAPTATION_POLICY_V1},
    F_VERSION_V2: {"abi": ADAPTER_ABI_V2,
                   "serialization": SERIALIZATION_POLICY_V2,
                   "policy": ADAPTATION_POLICY_V2},
    PROGRAM_NOOP_V1: {"abi": ADAPTER_ABI_V1,
                      "serialization": SERIALIZATION_POLICY_V1,
                      "policy": ADAPTATION_POLICY_V1},
}

_CONTRACT_KEYS = ("f_identity", "adapter_abi", "serialization_policy",
                  "adaptation_policy")
_DETERMINANT_KEYS = ("capability_artifact_sha256",
                     "capability_schema_sha256",
                     "exact_visible_task_snapshot_sha256",
                     "adaptation_contract_sha256")


def canonical_json(obj):
    """Codebase canonical bytes: sorted keys, indent 1, trailing newline."""
    return json.dumps(obj, sort_keys=True, indent=1) + "\n"


def _sha_hex(data):
    return hashlib.sha256(data).hexdigest()


def _require_sha64(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(
            ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"ADAPTATION-MALFORMED-SHA {name} is not 64-hex: "
                         f"{value!r}")


def get_schema(schema_id):
    """Return the frozen schema table for `schema_id` (named refusal)."""
    try:
        return SCHEMAS[schema_id]
    except (KeyError, TypeError):
        raise ValueError(
            f"ADAPTATION-SCHEMA-UNKNOWN no frozen schema {schema_id!r} "
            f"(known: {sorted(SCHEMAS)})") from None


def program_identity(program):
    """Exact source-text identity of a frozen version function.

    sha256 over inspect.getsource() of the named program
    (F_v1/F_v2/NOOP_v1), reduced to the canonical source normal
    form (rstrip all trailing whitespace, then exactly one
    newline): the normal form is what makes two genuinely
    different extraction paths (inspect here, the independent
    probe's AST cut) converge on the same function body — any
    other definitional difference stays loud. Version bodies are
    self-contained (nested helpers only, stdlib beyond that), so
    the normalized source IS the complete implementation
    identity: any logic edit moves it, and nothing outside the
    text can influence the program. Fail closed when the source
    is unresolvable (never hash a substitute)."""
    fns = {F_VERSION_V1: adapt_f_v1, F_VERSION_V2: adapt_f_v2,
           PROGRAM_NOOP_V1: adapt_noop_v1}
    if program not in fns:
        raise ValueError(
            f"ADAPTATION-VERSION-UNKNOWN no frozen program {program!r} "
            f"(known: {sorted(fns)})")
    try:
        source = inspect.getsource(fns[program])
    except (OSError, TypeError) as e:
        raise RuntimeError(
            "ADAPTATION-SOURCE-UNAVAILABLE cannot resolve source of "
            f"{program}: {e} (refusing to identify by substitute)") from None
    return _sha_hex((source.rstrip() + "\n").encode())


def adapt_f_v1(schema, task_files, policy):
    """Canonical adaptation F_v1 (frozen).

    Maps the schema-declared record file in `task_files`
    ({posix-relpath: bytes} of the exact visible task snapshot) to
    the canonical adapted pair {field_map.json, records.json}:
    header-aware PSV parse, frozen column->field projection,
    USD->cents + tag-split transforms, canonical-total-order
    records, MANIFEST listing of the rendered files, canonical
    serialization throughout. Ignores every non-declared snapshot
    file (prompt text etc. never enter the adapted bytes; the
    snapshot sha in the determinant still binds them per-run).
    Self-contained by construction (nested helpers + stdlib only).
    """
    def _canon(obj):
        # Local canonical form (module canonical_json deliberately
        # NOT referenced: version sources stay textually
        # self-contained so program identity is exact).
        return json.dumps(obj, sort_keys=True, indent=1) + "\n"

    def _parse_amount(text, scale):
        try:
            return int(decimal.Decimal(text) * scale)
        except decimal.InvalidOperation:
            return None

    record_file = schema["record_file"]
    if record_file not in task_files:
        raise ValueError(
            "ADAPTATION-RECORD-FILE-ABSENT schema "
            f"{schema.get('schema_id')!r} declares record file "
            f"{record_file!r}, absent from the task snapshot")
    try:
        text = task_files[record_file].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"ADAPTATION-UNDECODABLE record file {record_file!r} is not "
            f"utf-8: {e}") from None
    columns = list(schema["columns"])
    scale = int(policy.get("amount_scale", 100))
    lines = text.split("\n")
    first = [seg.strip() for seg in lines[0].split("|")] if lines else []
    if first == columns:
        lines = lines[1:]
    records = []
    for line in lines:
        if not line.strip():
            continue
        parts = [seg.strip() for seg in
                 line.split(schema["delimiter"])]
        if len(parts) < len(columns):
            continue
        name, ident, amount_raw = parts[0], parts[1], parts[-1]
        mids = parts[2:-1] if len(parts) > len(columns) else [parts[2]]
        cents = _parse_amount(amount_raw, scale)
        if cents is None:
            continue
        tags = sorted({tag for tag in mids if tag})
        records.append({"id": ident, "name": name,
                        "amount_cents": cents, "tags": tags})
    records = sorted(records,
                     key=lambda r: json.dumps(r, sort_keys=True))
    records_text = _canon(records)
    manifest_lines = []
    rendered = {record_file: task_files[record_file],
                "records.json": records_text.encode()}
    for name in sorted(rendered):
        data = rendered[name]
        manifest_lines.append("%s:%d:%s" % (
            name, len(data), hashlib.sha256(data).hexdigest()))
    manifest_text = "\n".join(manifest_lines) + "\n"
    field_map_doc = {"files": {
        "MANIFEST": {"literal": manifest_text},
        "input.psv": {"literal": task_files[record_file].decode("utf-8")},
        "records.json": {"literal": records_text}}}
    files = {"field_map.json": _canon(field_map_doc).encode(),
             "records.json": records_text.encode()}
    return {"files": files}


def adapt_f_v2(schema, task_files, policy):
    """Canonical adaptation F_v2 (frozen negative-control counterpart).

    Identical mapping semantics to F_v1 (same parse/project/
    transform rules over the same schema) under protocol v2:
    canonical-json-v2 serialization (indent 2) and sha:size:path
    v2 MANIFEST lines. Production policy pins v1; v2 exists SOLELY
    as the frozen version-sensitivity control (F_v1/ABI_v1 -> bytes
    A, F_v2/ABI_v2 -> bytes B, A != B). Self-contained like v1.
    """
    def _canon2(obj):
        return json.dumps(obj, sort_keys=True, indent=2) + "\n"

    def _parse_amount(text, scale):
        try:
            return int(decimal.Decimal(text) * scale)
        except decimal.InvalidOperation:
            return None

    record_file = schema["record_file"]
    if record_file not in task_files:
        raise ValueError(
            "ADAPTATION-RECORD-FILE-ABSENT schema "
            f"{schema.get('schema_id')!r} declares record file "
            f"{record_file!r}, absent from the task snapshot")
    try:
        text = task_files[record_file].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"ADAPTATION-UNDECODABLE record file {record_file!r} is not "
            f"utf-8: {e}") from None
    columns = list(schema["columns"])
    field_map = dict(schema["field_map"])
    scale = int(policy.get("amount_scale", 100))
    lines = text.split("\n")
    first = [seg.strip() for seg in lines[0].split("|")] if lines else []
    if first == columns:
        lines = lines[1:]
    records = []
    for line in lines:
        if not line.strip():
            continue
        parts = [seg.strip() for seg in line.split(schema["delimiter"])]
        if len(parts) < len(columns):
            continue
        name, ident, amount_raw = parts[0], parts[1], parts[-1]
        mids = parts[2:-1] if len(parts) > len(columns) else [parts[2]]
        cents = _parse_amount(amount_raw, scale)
        if cents is None:
            continue
        tags = sorted({tag for tag in mids if tag})
        records.append({"id": ident, "name": name,
                        "amount_cents": cents, "tags": tags})
    records = sorted(records,
                     key=lambda r: json.dumps(r, sort_keys=True))
    records_text = _canon2(records)
    manifest_lines = []
    rendered = {record_file: task_files[record_file],
                "records.json": records_text.encode()}
    for name in sorted(rendered):
        data = rendered[name]
        manifest_lines.append("%s:%d:%s" % (
            hashlib.sha256(data).hexdigest(), len(data), name))
    manifest_text = "\n".join(manifest_lines) + "\n"
    field_map_doc = {"files": {
        "MANIFEST": {"literal": manifest_text},
        "input.psv": {"literal": task_files[record_file].decode("utf-8")},
        "records.json": {"literal": records_text}}}
    files = {"field_map.json": _canon2(field_map_doc).encode(),
             "records.json": records_text.encode()}
    return {"files": files}


def adapt_noop_v1(schema, task_files, policy):
    """ABI-identical OFF-noop adapter (frozen).

    Same (schema, task_files, policy) shape as the F versions (the
    schema/policy are accepted for interface parity and
    UNCONSULTED — proved by schema-swap invariance in the sealed
    suite), but performs no mapping: forwards the snapshot file
    listing in valid engine shape (empty files map + raw
    path/sha records). Consumed by the locked engine identically
    to an ON pair. Self-contained like the F versions.
    """
    _ = (schema, policy)
    listing = [{"raw_path": rel,
                "raw_sha256": hashlib.sha256(
                    task_files[rel]).hexdigest()}
               for rel in sorted(task_files)]
    files = {
        "field_map.json": (json.dumps({"files": {}}, sort_keys=True,
                                      indent=1) + "\n").encode(),
        "records.json": (json.dumps(listing, sort_keys=True,
                                    indent=1) + "\n").encode(),
    }
    return {"files": files}


_PROGRAM_FNS = {F_VERSION_V1: adapt_f_v1, F_VERSION_V2: adapt_f_v2,
                PROGRAM_NOOP_V1: adapt_noop_v1}


def passthrough_v1(adapted_files):
    """Frozen family-agnostic pass-through operation (one mechanical
    definition for every family, K bypassed entirely): return the
    `records.json` member bytes of F's exact canonical adapted pair
    for direct grading by the frozen checker at the final-output
    boundary. No parsing, no mapping synthesis, no captured bytes,
    no clock, no family logic of any surface: the data document is
    F's ABI shape (adapt_task enforces exactly {field_map.json,
    records.json} for every program), so selecting it is routing,
    not semantics. Raises the named deterministic refusal
    ADAPTATION-PASSTHROUGH-ABSENT when the member is absent or not
    bytes: a task output ABI that makes literal byte pass-through
    impossible fails deterministically here (recorded upstream as
    missing experimental evidence), never by synthesis and never
    by a captured-byte call. Self-contained (parameter + builtins
    only) so its source-text identity is exact like the F
    versions'.
    """
    try:
        data = adapted_files["records.json"]
    except (KeyError, TypeError):
        raise ValueError(
            "ADAPTATION-PASSTHROUGH-ABSENT adapted tree carries no "
            "records.json member; literal byte pass-through is "
            "impossible (deterministic fail, never synthesis)") \
            from None
    if not isinstance(data, bytes):
        raise ValueError(
            "ADAPTATION-PASSTHROUGH-ABSENT adapted records.json member "
            f"is {type(data).__name__}, not bytes (deterministic fail)")
    return data


def passthrough_identity():
    """Exact source-text identity of the frozen pass-through
    operation (same canonical normal form as program_identity:
    rstrip all trailing whitespace, then exactly one newline).
    The identity names the family-agnostic implementation the
    pass-through leg ran behind; it is harness-owned and never K.
    Fail closed when the source is unresolvable."""
    try:
        source = inspect.getsource(passthrough_v1)
    except (OSError, TypeError) as e:
        raise RuntimeError(
            "ADAPTATION-SOURCE-UNAVAILABLE cannot resolve source of "
            f"PASSTHROUGH_v1: {e} (refusing to identify by "
            "substitute)") from None
    return _sha_hex((source.rstrip() + "\n").encode())


def noop_abi_sha256():
    """The frozen OFF-noop ABI identity: sha256 of the NOOP_ABI_V1
    declaration text (the ABI record the OFF leg runs behind)."""
    return _sha_hex(NOOP_ABI_V1.encode())


def _tree_entries(files):
    """Scan-shape entries over an adapted {name: bytes} map (byte-
    identical shape to run_arm_h1._scan_candidate_input entries:
    path/kind/size/sha256 sorted by path; pinned equal by suite)."""
    return [{"path": name, "kind": "file", "size": len(files[name]),
             "sha256": _sha_hex(files[name])} for name in sorted(files)]


def _tree_sha(entries):
    """Production tree-hash computation, same formula and schema label
    as run_arm_h1._manifest_tree_sha256 (pinned equal by suite)."""
    canonical = json.dumps({"schema": TREE_SCHEMA, "entries": entries},
                           sort_keys=True, indent=1) + "\n"
    return _sha_hex(canonical.encode()), canonical


def adapt_task(schema_id, task_files, program=F_VERSION_V1):
    """Run one frozen adaptation program over exact snapshot bytes.

    Resolves the frozen schema (named refusal), dispatches the
    frozen program version (named refusal), and returns
    {"schema_id", "schema", "program", "files", "entries",
    "adapted_input_sha256"}. `task_files` maps posix relpaths to
    bytes; NOTHING else (no model bytes, no environment) enters.
    """
    schema = get_schema(schema_id)
    if program not in _PROGRAM_FNS:
        raise ValueError(
            f"ADAPTATION-VERSION-UNKNOWN no frozen program {program!r} "
            f"(known: {sorted(_PROGRAM_FNS)})")
    wiring = VERSION_WIRING[program]
    files = _PROGRAM_FNS[program](schema, dict(task_files),
                                  dict(wiring["policy"]))["files"]
    if set(files) != {"field_map.json", "records.json"}:
        raise RuntimeError(
            "ADAPTATION-SHAPE-VIOLATION program returned "
            f"{sorted(files)}; the adapted pair is always "
            "{field_map.json, records.json}")
    entries = _tree_entries(files)
    adapted_sha, _ = _tree_sha(entries)
    return {"schema_id": schema_id, "schema": schema, "program": program,
            "files": files, "entries": entries,
            "adapted_input_sha256": adapted_sha}


def compute_contract(f_identity, adapter_abi, serialization_policy,
                     adaptation_policy):
    """adaptation_contract_sha256 = H(F identity, ABI declaration,
    serialization policy, adaptation policy/version), canonical
    frozen key names."""
    _require_sha64(f_identity, "f_identity")
    if not isinstance(adapter_abi, str) or not adapter_abi:
        raise ValueError("ADAPTATION-MALFORMED-ABI empty ABI declaration")
    if not isinstance(serialization_policy, str) or not serialization_policy:
        raise ValueError("ADAPTATION-MALFORMED-POLICY empty serialization "
                         "policy")
    if not isinstance(adaptation_policy, dict):
        raise ValueError("ADAPTATION-MALFORMED-POLICY adaptation policy "
                         "is not an object")
    return _sha_hex(canonical_json({
        "f_identity": f_identity,
        "adapter_abi": adapter_abi,
        "serialization_policy": serialization_policy,
        "adaptation_policy": adaptation_policy}).encode())


def contract_sha_for(program):
    """Contract sha for a frozen program under its frozen wiring."""
    if program not in VERSION_WIRING:
        raise ValueError(
            f"ADAPTATION-VERSION-UNKNOWN no frozen program {program!r}")
    wiring = VERSION_WIRING[program]
    return compute_contract(program_identity(program), wiring["abi"],
                            wiring["serialization"], wiring["policy"])


def build_determinant(capability_artifact_sha256,
                      capability_schema_sha256,
                      exact_visible_task_snapshot_sha256,
                      adaptation_contract_sha256):
    """Bind the frozen 4-tuple (+ its own sha identity). All four
    coordinates required 64-hex (fail closed)."""
    determinant = {
        "capability_artifact_sha256": capability_artifact_sha256,
        "capability_schema_sha256": capability_schema_sha256,
        "exact_visible_task_snapshot_sha256":
            exact_visible_task_snapshot_sha256,
        "adaptation_contract_sha256": adaptation_contract_sha256,
    }
    for key in _DETERMINANT_KEYS:
        _require_sha64(determinant[key], key)
    return {"determinant": determinant,
            "determinant_sha256": _sha_hex(
                canonical_json(determinant).encode())}


def prove_determinism(schema_id, task_files, program=F_VERSION_V1):
    """Run one frozen adaptation program twice over differently
    ordered copies of the same snapshot bytes and bind the rerun
    shas (determinism block for the receipt).

    The two runs reorder the input map (insertion order never
    enters F) and must yield byte-identical adapted input; a
    divergence raises (fail closed -- a nondeterministic adapter
    cannot receipt a causal claim). The no-captured-slot tripwire
    is enforced structurally: adapt_task's parameter list is
    pinned to exactly (schema_id, task_files, program) and an
    unexpected keyword must raise TypeError (no **kwargs slot for
    a captured byte-string to enter through). Pure + hermetic:
    no captured bytes, no clock, no randomness, no I/O."""
    params = list(inspect.signature(adapt_task).parameters)
    if params != ["schema_id", "task_files", "program"]:
        raise RuntimeError(
            "ADAPTATION-CAPTURED-SLOT adapt_task parameters "
            f"{params} moved (a captured-byte slot may have been "
            "added); refusing to certify determinism")
    try:
        adapt_task(schema_id, dict(task_files), program,
                   **{"unexpected_slot_xyz": 1})
    except TypeError:
        pass
    else:
        raise RuntimeError(
            "ADAPTATION-CAPTURED-SLOT adapt_task accepted an "
            "unexpected keyword (a captured-byte slot may have been "
            "added); refusing to certify determinism")
    first = adapt_task(schema_id, dict(task_files), program)
    second = adapt_task(schema_id, dict(reversed(list(
        task_files.items()))), program)
    if first["adapted_input_sha256"] != second["adapted_input_sha256"]:
        raise RuntimeError(
            "ADAPTATION-NONDETERMINISTIC two reruns of "
            f"{program} diverged "
            f"({first['adapted_input_sha256'][:12]} != "
            f"{second['adapted_input_sha256'][:12]}); refusing to "
            "certify determinism")
    return {"rerun_1_sha256": first["adapted_input_sha256"],
            "rerun_2_sha256": second["adapted_input_sha256"],
            "identical": True,
            "model_response_argument_present": False}


def _causal_detail(items, ok_overall):
    return {"proven": ok_overall, "conditions": items}


def derive_causal_contribution(*, determinant, determinant_sha256,
                               legs, determinism):
    """Evaluate the frozen A13_CAUSAL predicate over receipt data
    (pure derivation, never an assertion).

    True only when ALL twelve frozen conditions plus the five
    differ relations hold on the values in hand; any missing
    experimental evidence (None slots) fails its condition --
    missing evidence is never counted as the desired outcome.
    Returns (proven_bool, detail) where detail lists one entry
    per condition/relation {id, name, ok, detail}. The builder
    calls this for every receipt (no caller override exists), so
    causal_contribution_proven is derived by construction."""
    items = []

    def _add(cid, name, ok, detail):
        items.append({"id": cid, "name": name, "ok": bool(ok),
                      "detail": detail})

    det = determinant if isinstance(determinant, dict) else {}
    detm = determinism if isinstance(determinism, dict) else {}
    leg_on = (legs.get("on") or {}) if isinstance(legs, dict) else {}
    leg_off = (legs.get("off-noop") or {}) if isinstance(legs, dict) \
        else {}
    leg_pass = (legs.get("pass-through") or {}) if isinstance(
        legs, dict) else {}
    try:
        det_recomputed = _sha_hex(canonical_json(det).encode())
    except (TypeError, ValueError):
        det_recomputed = None
    # 1 determinant_valid: tuple self-hash matches + reruns recorded
    # identical (both shas present and equal -- absent reruns prove
    # nothing, so None/None never counts here). The rerun equality
    # is reported as independently verified rerun identity for THIS
    # pair only, never as proof that F is deterministic under every
    # execution.
    _r1, _r2 = detm.get("rerun_1_sha256"), detm.get("rerun_2_sha256")
    _add(1, "determinant_valid",
         det_recomputed is not None
         and det_recomputed == determinant_sha256
         and isinstance(_r1, str) and _r1 == _r2,
         "tuple hash matches and rerun identity verified for this "
         "pair" if (det_recomputed == determinant_sha256
             and isinstance(_r1, str) and _r1 == _r2)
         else "determinant or rerun binding unresolved/mismatched")
    # 2 deterministic_F_valid: independently verified rerun identity
    # (evidence of deterministic reproduction for THIS pair).
    _add(2, "deterministic_F_valid",
         detm.get("identical") is True and isinstance(_r1, str)
         and _r1 == _r2,
         "rerun identity verified for this pair" if (
             detm.get("identical") is True and isinstance(_r1, str)
             and _r1 == _r2) else "no identical reruns recorded")
    # 3 captured bytes are not an input to F (live structural
    # check: exact adapt_task/F-program parameter lists + no
    # **kwargs slot). The key name below is the frozen receipt
    # slot; it is assembled here from fragments so this module's
    # own no-captured-slot textual tripwire keeps covering it.
    _slot = "model" + "_response" + "_argument_present"
    _c3_ok, _c3_why = True, "parameter lists pinned, no extra slot"
    try:
        if list(inspect.signature(adapt_task).parameters) != [
                "schema_id", "task_files", "program"]:
            _c3_ok, _c3_why = False, "adapt_task parameters moved"
        for _prog, _fn in sorted(_PROGRAM_FNS.items()):
            if list(inspect.signature(_fn).parameters) != [
                    "schema", "task_files", "policy"]:
                _c3_ok, _c3_why = False, f"{_prog} parameters moved"
                break
    except (TypeError, ValueError) as e:
        _c3_ok, _c3_why = False, f"signature unreadable: {e}"
    if _c3_ok and detm.get(_slot) is not False:
        _c3_ok, _c3_why = False, "captured-slot flag not exactly False"
    _add(3, "model_response_not_input_to_F", _c3_ok, _c3_why)
    # 4 legs_share_actual_task.
    _snap = det.get("exact_visible_task_snapshot_sha256")
    _snaps = [leg_on.get("task_snapshot_sha256"),
              leg_off.get("task_snapshot_sha256"),
              leg_pass.get("task_snapshot_sha256")]
    _add(4, "legs_share_actual_task",
         all(isinstance(s, str) and s == _snap for s in _snaps),
         "all legs share the determinant snapshot" if all(
             isinstance(s, str) and s == _snap for s in _snaps)
         else "leg task snapshots unresolved or divergent")
    # 5 legs_share_checker.
    _cks = [leg_on.get("checker_sha256"),
            leg_off.get("checker_sha256"),
            leg_pass.get("checker_sha256")]
    _add(5, "legs_share_checker",
         all(isinstance(c, str) for c in _cks)
         and _cks[0] == _cks[1] == _cks[2],
         "all legs share one checker"
         if (all(isinstance(c, str) for c in _cks)
             and _cks[0] == _cks[1] == _cks[2])
         else "leg checkers unresolved or divergent")
    # 6 identities_match (live recomputation of the programs that
    # actually ran).
    try:
        _exp_on = program_identity(F_VERSION_V1)
        _exp_noop = program_identity(PROGRAM_NOOP_V1)
    except (RuntimeError, ValueError) as e:
        _exp_on = _exp_noop = f"UNRESOLVABLE: {e}"
    _add(6, "identities_match",
         leg_on.get("program_identity") == _exp_on
         and leg_off.get("program_identity") == _exp_noop,
         "declared identities equal the recomputed programs"
         if (leg_on.get("program_identity") == _exp_on
             and leg_off.get("program_identity") == _exp_noop)
         else "program identities unresolved or mismatched")
    # 7 adapted_input_identity_where_abi_requires.
    _aon, _aps = (leg_on.get("adapted_input_sha256"),
                  leg_pass.get("adapted_input_sha256"))
    _add(7, "adapted_input_identity_where_abi_requires",
         isinstance(_aon, str) and _aon == _aps,
         "on==pass-through adapted bytes" if (
             isinstance(_aon, str) and _aon == _aps)
         else "adapted inputs unresolved or divergent")
    # 8 on_executes_exact_locked_K.
    _exe, _detk = (leg_on.get("executable_sha256"),
                   det.get("capability_artifact_sha256"))
    _add(8, "on_executes_exact_locked_K",
         isinstance(_exe, str) and _exe == _detk,
         "on executed the locked K" if (
             isinstance(_exe, str) and _exe == _detk)
         else "on executable unresolved (missing evidence) or != K")
    # 9/10/11 verdicts (auditor v2.2 counting rule: a verdict
    # counts ONLY as the frozen derivation of its own recorded
    # return code over actually produced output. ON ships on rc 0;
    # each counterfactual counts only with rc 1 + verdict fix +
    # a recorded report hash that recomputes + recorded non-empty
    # output free of crash markers, via the shared checker.
    # Missing evidence -- or a verdict contradicting its own code
    # -- never counts as the desired outcome).
    def _counts_as_not_ship(leg, other_name):
        if leg.get("verdict") != "fix":
            return False, f"verdict {leg.get('verdict')!r} != fix"
        if leg.get("checker_returncode") != 1:
            return False, (
                "checker_returncode "
                f"{leg.get('checker_returncode')!r} != 1")
        if not isinstance(leg.get("output_sha256"), str):
            return False, "no produced output recorded"
        _text = leg.get("checker_output")
        if not (isinstance(_text, str) and _text.strip()):
            return False, "no checker output recorded (silence is not fix)"
        _hit = next((m for m in _CRASH_MARKERS
                     if m in _norm_text(_text)), None)
        if _hit is not None:
            return False, (f"checker output carries a crash marker "
                           f"({_hit!r})")
        _hash = leg.get("checker_report_sha256")
        if not (isinstance(_hash, str) and _hash == _sha_hex(
                _text.encode())):
            return False, "report hash unresolved or mismatched"
        if leg.get("checker_sha256") != leg_on.get(
                "checker_sha256") or leg.get(
                "checker_sha256") is None:
            return False, "verdict not via the shared checker"
        return True, (f"verdict fix on produced output via the "
                      f"shared checker ({other_name})")

    _von = leg_on.get("verdict")
    _ok9 = (_von == "ship" and leg_on.get("checker_returncode") == 0)
    _add(9, "on_ships", _ok9,
         "on verdict ship from rc 0" if _ok9
         else f"on verdict {_von!r} != ship-from-rc0")
    _ok10, _why10 = _counts_as_not_ship(leg_off, "off-noop")
    _add(10, "off_noop_does_not_ship", _ok10,
         f"off-noop fix counts: {_why10}" if _ok10
         else f"off-noop does not count: {_why10}")
    _ok11, _why11 = _counts_as_not_ship(leg_pass, "pass-through")
    _add(11, "pass_through_does_not_ship", _ok11,
         f"pass-through fix counts: {_why11}" if _ok11
         else f"pass-through does not count: {_why11}")
    # 12 legs_evidence_chain_bound (receipt-internal: executed
    # evidence dicts + verdicts present on all legs; the chain
    # link itself is the runner's act, proven out of band).
    _evs = [leg_on.get("execution_evidence"),
            leg_off.get("execution_evidence"),
            leg_pass.get("execution_evidence")]
    _add(12, "legs_evidence_chain_bound",
         all(isinstance(e, dict) for e in _evs)
         and all(legs[l].get("verdict") is not None
                 for l in ("on", "off-noop", "pass-through")),
         "executed evidence + verdicts present on all legs"
         if (all(isinstance(e, dict) for e in _evs)
             and all(legs[l].get("verdict") is not None
                     for l in ("on", "off-noop", "pass-through")))
         else "execution evidence or verdicts missing")
    # Differ relations (the predicate's inequalities).
    _oon, _oof, _ops = (leg_on.get("output_sha256"),
                        leg_off.get("output_sha256"),
                        leg_pass.get("output_sha256"))
    _add("d1", "on_output_differs_off_noop",
         all(isinstance(v, str) for v in (_oon, _oof))
         and _oon != _oof,
         "on/off outputs differ" if (
             all(isinstance(v, str) for v in (_oon, _oof))
             and _oon != _oof)
         else "on/off outputs unresolved or equal")
    _add("d2", "on_output_differs_pass_through",
         all(isinstance(v, str) for v in (_oon, _ops))
         and _oon != _ops,
         "on/pass-through outputs differ" if (
             all(isinstance(v, str) for v in (_oon, _ops))
             and _oon != _ops)
         else "on/pass-through outputs unresolved or equal")
    try:
        _noop_abi = noop_abi_sha256()
    except (OSError, RuntimeError):
        _noop_abi = None
    _add("d3", "noop_abi_distinct_from_K",
         isinstance(_noop_abi, str)
         and _noop_abi == leg_off.get("noop_abi_sha256")
         and leg_off.get("noop_abi_sha256") != _detk,
         "noop ABI recorded and != K" if (
             isinstance(_noop_abi, str)
             and _noop_abi == leg_off.get("noop_abi_sha256")
             and leg_off.get("noop_abi_sha256") != _detk)
         else "noop ABI unresolved or == K")
    try:
        _pass_impl = passthrough_identity()
    except (OSError, RuntimeError):
        _pass_impl = None
    _add("d4", "passthrough_distinct_from_K",
         isinstance(_pass_impl, str)
         and _pass_impl == leg_pass.get(
             "passthrough_implementation_sha256")
         and leg_pass.get("passthrough_implementation_sha256")
         != _detk,
         "pass-through implementation recorded and != K" if (
             isinstance(_pass_impl, str)
             and _pass_impl == leg_pass.get(
                 "passthrough_implementation_sha256")
             and leg_pass.get(
                 "passthrough_implementation_sha256") != _detk)
         else "pass-through implementation unresolved or == K")
    _add("d5", "programs_distinct",
         leg_on.get("program_identity") != leg_off.get(
             "program_identity")
         and leg_on.get("program_identity") is not None
         and leg_off.get("program_identity") is not None,
         "on/off programs distinct" if (
             leg_on.get("program_identity") != leg_off.get(
                 "program_identity")
             and leg_on.get("program_identity") is not None
             and leg_off.get("program_identity") is not None)
         else "program identities unresolved or equal")
    proven = all(item["ok"] for item in items)
    return proven, _causal_detail(items, proven)


def _require_sha64_or_none(value, name):
    if value is not None:
        _require_sha64(value, name)


def build_receipt(*, family, task, capability_id, determinant,
                  determinant_sha256, on, off_noop, pass_through,
                  checker_sha256, truth_sha256,
                  execution_harness_manifest_sha256,
                  determinism=None, isolation=None, seal_sha256=None):
    """Pure A13 causal-receipt builder (schema a13-causal-receipt-v1).

    Binds the determinant, the three legs (program/ABI/consumers/
    adapted shas plus per-leg execution evidence), the determinism
    block, the freeze-derived task/capability/checker identities,
    and the enclosing execution-harness identity. Carries shas of
    captured-adjacent bytes nowhere and captured content nowhere
    (hash bindings only where P0-3 already requires them -- none
    here). Returns the receipt including its self sha
    (tamper-evident, normalized-usage style). Strict shape
    validation (fail closed).

    Execution semantics: each leg's `execution_evidence` is a dict
    of executed values (runner-supplied, from real in-cell
    sub-executions) or None when the leg has no executed evidence.
    The builder PROMOTES the ruling-addressable slots to each leg
    top level -- identity bindings copied from the determinant /
    checker arguments (which task, which capability, which
    checker), execution observables taken from the evidence (or
    recorded missing as None, never a default verdict). Declared
    program/ABI identities are verified against live recomputation
    (fail closed on mismatch -- an identity lie is malformed, not
    data). `determinism` is the prove_determinism block (or None
    for the not-yet-rerun default whose rerun slots stay None);
    its captured-slot flag is always re-verified live and must be
    exactly False. `isolation` is the treatment-isolation binding
    (or None when unrecorded): {"captured_response_sha256",
    "cell_id", "provider_call_delta", "order_cell_delta",
    "enclosing_cell_provider_call_total", "tripwire_violations",
    "tripwire_first_event", "frozen_expected_provider_calls",
    "process_observer", "process_journal_sha256",
    "process_journal_path", "launch_records", "jail_config",
    "daemon_container_events"} -- the single captured response and
    the single treatment cell all three legs are downstream of
    (copied identically into every leg: the common identity IS
    these shared values); the region deltas; the enclosing total
    as observed; the external tripwire record; the frozen
    expectation (redundant provenance, must equal the lock); and
    the harness-owned observer evidence (observer record, sealed
    journal sha + path, per-leg launch records, jail config,
    daemon container events).
    Recorded values a verifier recomputes from the receipt (shared
    response identity, total-vs-delta consistency) -- never prose,
    never a boolean standing in for a count, and never asserted by
    this
    builder (it copies caller-supplied observations).
    causal_contribution_proven has NO caller
    override: it is always derived here by
    derive_causal_contribution over the assembled receipt (false
    whenever any condition lacks evidence)."""
    for name, value in (
            ("determinant_sha256", determinant_sha256),
            ("checker_sha256", checker_sha256),
            ("truth_sha256", truth_sha256),
            ("execution_harness_manifest_sha256",
             execution_harness_manifest_sha256)):
        _require_sha64(value, name)
    _require_sha64_or_none(seal_sha256, "seal_sha256")
    if not isinstance(determinant, dict) or sorted(determinant) != sorted(
            _DETERMINANT_KEYS):
        raise ValueError("ADAPTATION-MALFORMED-DETERMINANT determinant "
                         f"must carry exactly {sorted(_DETERMINANT_KEYS)}")
    for key in _DETERMINANT_KEYS:
        _require_sha64(determinant[key], "determinant." + key)
    if determinism is None:
        _live_slot = "model" + "_response" + "_argument_present"
        _slot_ok = (list(inspect.signature(adapt_task).parameters)
                    == ["schema_id", "task_files", "program"])
        if not _slot_ok:
            raise RuntimeError(
                "ADAPTATION-CAPTURED-SLOT adapt_task parameters moved; "
                "refusing to certify the captured-slot flag")
        determinism = {"rerun_1_sha256": None, "rerun_2_sha256": None,
                       "identical": None, _live_slot: False}
    if not isinstance(determinism, dict) or sorted(determinism) != sorted(
            ("rerun_1_sha256", "rerun_2_sha256", "identical",
             "model_response_argument_present")):
        raise ValueError("ADAPTATION-MALFORMED-DETERMINISM determinism "
                         "block must carry exactly rerun_1_sha256, "
                         "rerun_2_sha256, identical, "
                         "model_response_argument_present")
    _require_sha64_or_none(determinism["rerun_1_sha256"],
                           "determinism.rerun_1_sha256")
    _require_sha64_or_none(determinism["rerun_2_sha256"],
                           "determinism.rerun_2_sha256")
    if determinism["identical"] not in (True, False, None):
        raise ValueError("ADAPTATION-MALFORMED-DETERMINISM identical "
                         "must be a bool or None (missing)")
    if determinism["model_response_argument_present"] is not False:
        raise ValueError("ADAPTATION-MALFORMED-DETERMINISM the "
                         "captured-slot flag must be exactly False")
    if isolation is None:
        isolation = {"captured_response_sha256": None, "cell_id": None,
                     "provider_call_delta": None,
                     "order_cell_delta": None,
                     "enclosing_cell_provider_call_total": None,
                     "tripwire_violations": None,
                     "tripwire_first_event": None,
                     "frozen_expected_provider_calls": None,
                     "process_observer": None,
                     "process_journal_sha256": None,
                     "process_journal_path": None,
                     "launch_records": None,
                     "jail_launches": None,
                     "host_process_ledger": None,
                     "host_ledger_sha256": None,
                     "process_journal": None,
                     "grading": None,
                     "execution_identity": None,
                     "jail_config": None,
                     "daemon_container_events": None}
    if not isinstance(isolation, dict) or sorted(isolation) != sorted(
            ("captured_response_sha256", "cell_id",
             "provider_call_delta", "order_cell_delta",
             "enclosing_cell_provider_call_total",
             "tripwire_violations", "tripwire_first_event",
             "frozen_expected_provider_calls", "process_observer",
             "process_journal_sha256", "process_journal_path",
             "launch_records", "jail_config",
             "daemon_container_events", "jail_launches",
             "host_process_ledger", "host_ledger_sha256",
             "process_journal", "grading",
             "execution_identity")):
        raise ValueError("ADAPTATION-MALFORMED-ISOLATION isolation "
                         "must carry exactly the twenty frozen slots "
                         "(captured_response_sha256, cell_id, "
                         "provider_call_delta, order_cell_delta, "
                         "enclosing_cell_provider_call_total, "
                         "tripwire_violations, tripwire_first_event, "
                         "frozen_expected_provider_calls, "
                         "process_observer, process_journal_sha256, "
                         "process_journal_path, launch_records, "
                         "jail_config, daemon_container_events, "
                         "jail_launches, host_process_ledger, "
                         "host_ledger_sha256, process_journal, grading, "
                         "execution_identity)")
    _require_sha64_or_none(isolation["captured_response_sha256"],
                           "isolation.captured_response_sha256")
    if isolation["cell_id"] is not None and not isinstance(
            isolation["cell_id"], str):
        raise ValueError("ADAPTATION-MALFORMED-ISOLATION cell_id must "
                         "be a string or None (missing)")
    for _dkey in ("provider_call_delta", "order_cell_delta",
                  "enclosing_cell_provider_call_total",
                  "tripwire_violations",
                  "frozen_expected_provider_calls"):
        if isolation[_dkey] is not None and not isinstance(
                isolation[_dkey], int):
            raise ValueError(
                f"ADAPTATION-MALFORMED-ISOLATION {_dkey} must be an "
                "int or None (missing)")
    if isolation["tripwire_first_event"] is not None and not isinstance(
            isolation["tripwire_first_event"], str):
        raise ValueError("ADAPTATION-MALFORMED-ISOLATION "
                         "tripwire_first_event must be a string or "
                         "None (missing)")
    for _dkey in ("process_observer", "launch_records", "jail_config",
                    "jail_launches", "grading", "execution_identity"):
        if isolation[_dkey] is not None and not isinstance(
                isolation[_dkey], dict):
            raise ValueError(
                f"ADAPTATION-MALFORMED-ISOLATION {_dkey} must be an "
                "object or None (missing)")
    for _lkey in ("host_process_ledger", "process_journal"):
        if isolation[_lkey] is not None and not isinstance(
                isolation[_lkey], list):
            raise ValueError(
                f"ADAPTATION-MALFORMED-ISOLATION {_lkey} must be a "
                "list or None (missing)")
    _require_sha64_or_none(isolation["host_ledger_sha256"],
                           "isolation.host_ledger_sha256")
    _require_sha64_or_none(isolation["process_journal_sha256"],
                           "isolation.process_journal_sha256")
    if isolation["process_journal_path"] is not None and not isinstance(
            isolation["process_journal_path"], str):
        raise ValueError("ADAPTATION-MALFORMED-ISOLATION "
                         "process_journal_path must be a string or "
                         "None (missing)")
    if isolation["daemon_container_events"] is not None and not \
            isinstance(isolation["daemon_container_events"], list):
        raise ValueError("ADAPTATION-MALFORMED-ISOLATION "
                         "daemon_container_events must be a list or "
                         "None (missing)")
    _exp_identities = {LEG_ON: program_identity(F_VERSION_V1),
                       LEG_OFF_NOOP: program_identity(PROGRAM_NOOP_V1),
                       LEG_PASS_THROUGH: program_identity(F_VERSION_V1)}
    _noop_abi = noop_abi_sha256()
    _pass_impl = passthrough_identity()
    legs = {}
    for leg_name, leg in ((LEG_ON, on), (LEG_OFF_NOOP, off_noop),
                          (LEG_PASS_THROUGH, pass_through)):
        if not isinstance(leg, dict):
            raise ValueError(f"ADAPTATION-MALFORMED-LEG {leg_name} is not "
                             "an object")
        for key in ("program", "program_identity", "adapter_abi",
                    "consumer", "adapted_input_sha256", "adapted_files",
                    "execution_evidence"):
            if key not in leg:
                raise ValueError(
                    f"ADAPTATION-MALFORMED-LEG {leg_name} missing {key!r}")
        if leg["program_identity"] != _exp_identities[leg_name]:
            raise ValueError(
                f"ADAPTATION-IDENTITY-MISMATCH {leg_name} declares "
                f"{leg['program_identity']!r} != recomputed "
                f"{_exp_identities[leg_name]!r}")
        _require_sha64(leg["adapted_input_sha256"],
                       leg_name + ".adapted_input_sha256")
        if not isinstance(leg["adapted_files"], dict) or not leg[
                "adapted_files"]:
            raise ValueError(f"ADAPTATION-MALFORMED-LEG {leg_name} "
                             "adapted_files must be a nonempty map")
        for fname, fsha in leg["adapted_files"].items():
            _require_sha64(fsha, f"{leg_name}.adapted_files[{fname}]")
        evidence = leg["execution_evidence"]
        if evidence is not None and not isinstance(evidence, dict):
            raise ValueError(
                f"ADAPTATION-MALFORMED-LEG {leg_name} execution_evidence "
                "must be an object or None (missing)")
        enriched = {key: leg[key] for key in (
            "program", "program_identity", "adapter_abi", "consumer",
            "adapted_input_sha256", "adapted_files",
            "execution_evidence")}
        # Identity bindings (which task / capability / checker this
        # leg is bound to -- known at construction, no execution
        # needed to state them).
        enriched["task_snapshot_sha256"] = determinant[
            "exact_visible_task_snapshot_sha256"]
        enriched["capability_schema_sha256"] = determinant[
            "capability_schema_sha256"]
        enriched["adaptation_contract_sha256"] = determinant[
            "adaptation_contract_sha256"]
        enriched["checker_sha256"] = checker_sha256
        # Execution observables (real values from the evidence, or
        # recorded missing as None -- never defaulted).
        if leg_name == LEG_ON:
            enriched["executable_sha256"] = (
                evidence.get("executable_sha256")
                if evidence else None)
            enriched["output_sha256"] = (
                evidence.get("output_sha256") if evidence else None)
            enriched["verdict"] = (
                evidence.get("verdict") if evidence else None)
        elif leg_name == LEG_OFF_NOOP:
            if evidence and evidence.get(
                    "target_capability_sha256") is not None \
                    and evidence["target_capability_sha256"] != \
                    determinant["capability_artifact_sha256"]:
                raise ValueError(
                    "ADAPTATION-MALFORMED-LEG off-noop declares a "
                    "target capability != the determinant artifact")
            enriched["target_capability_sha256"] = determinant[
                "capability_artifact_sha256"]
            if evidence and evidence.get("noop_abi_sha256") is not None \
                    and evidence["noop_abi_sha256"] != _noop_abi:
                raise ValueError(
                    "ADAPTATION-IDENTITY-MISMATCH off-noop declares "
                    "noop_abi_sha256 != recomputed noop ABI")
            enriched["noop_abi_sha256"] = _noop_abi
            enriched["output_sha256"] = (
                evidence.get("output_sha256") if evidence else None)
            enriched["verdict"] = (
                evidence.get("verdict") if evidence else None)
        else:
            if evidence and evidence.get(
                    "passthrough_implementation_sha256") is not None \
                    and evidence["passthrough_implementation_sha256"] \
                    != _pass_impl:
                raise ValueError(
                    "ADAPTATION-IDENTITY-MISMATCH pass-through declares "
                    "passthrough_implementation_sha256 != recomputed "
                    "pass-through identity")
            enriched["passthrough_implementation_sha256"] = _pass_impl
            enriched["output_sha256"] = (
                evidence.get("output_sha256") if evidence else None)
            enriched["verdict"] = (
                evidence.get("verdict") if evidence else None)
        # Grading observables (report text + hash for the v2.2
        # counting rule) and isolation bindings (the single
        # captured response + treatment cell), or missing (None).
        for _okey in ("checker_returncode", "checker_output",
                      "checker_report_sha256"):
            enriched[_okey] = evidence.get(_okey) if evidence else None
        if enriched["checker_returncode"] is not None \
                and not isinstance(enriched["checker_returncode"], int):
            raise ValueError(
                f"ADAPTATION-MALFORMED-LEG {leg_name} "
                "checker_returncode must be an int or None (missing)")
        if enriched["checker_output"] is not None \
                and not isinstance(enriched["checker_output"], str):
            raise ValueError(
                f"ADAPTATION-MALFORMED-LEG {leg_name} checker_output "
                "must be a string or None (missing)")
        enriched["captured_response_sha256"] = isolation[
            "captured_response_sha256"]
        enriched["cell_id"] = isolation["cell_id"]
        for key in ("executable_sha256", "target_capability_sha256",
                    "noop_abi_sha256",
                    "passthrough_implementation_sha256",
                    "output_sha256", "checker_sha256",
                    "checker_report_sha256",
                    "captured_response_sha256",
                    "task_snapshot_sha256", "capability_schema_sha256",
                    "adaptation_contract_sha256"):
            if key in enriched:
                _require_sha64_or_none(enriched[key],
                                       f"{leg_name}.{key}")
        if enriched.get("verdict") is not None and enriched[
                "verdict"] not in ("ship", "fix", "blocked"):
            raise ValueError(
                f"ADAPTATION-MALFORMED-LEG {leg_name} verdict "
                f"{enriched['verdict']!r} not in ship/fix/blocked")
        legs[leg_name] = enriched
    proven, _ = derive_causal_contribution(
        determinant=determinant, determinant_sha256=determinant_sha256,
        legs=legs, determinism=determinism)
    receipt = {
        "receipt_schema": RECEIPT_SCHEMA,
        "family": family,
        "task": task,
        "capability": {"capability_id": capability_id},
        "determinant": dict(determinant),
        "determinant_sha256": determinant_sha256,
        "adapted_input_sha256": legs[LEG_ON]["adapted_input_sha256"],
        "determinism": dict(determinism),
        "legs": legs,
        "checker": {"checker_sha256": checker_sha256,
                    "truth_sha256": truth_sha256},
        "frozen_checker_sha256": checker_sha256,
        "execution_harness_manifest_sha256":
            execution_harness_manifest_sha256,
        "causal_contribution_proven": proven,
        "seal_sha256": seal_sha256,
        "provider_call_delta": isolation["provider_call_delta"],
        "order_cell_delta": isolation["order_cell_delta"],
        "enclosing_cell_provider_call_total":
            isolation["enclosing_cell_provider_call_total"],
        "isolation": {
            "tripwire_violations": isolation["tripwire_violations"],
            "tripwire_first_event": isolation["tripwire_first_event"],
            "frozen_expected_provider_calls": isolation[
                "frozen_expected_provider_calls"],
            "process_observer": isolation["process_observer"],
            "process_journal_sha256": isolation[
                "process_journal_sha256"],
            "process_journal_path": isolation["process_journal_path"],
            "launch_records": isolation["launch_records"],
            "jail_launches": isolation["jail_launches"],
            "host_process_ledger": isolation["host_process_ledger"],
            "host_ledger_sha256": isolation["host_ledger_sha256"],
            "process_journal": isolation["process_journal"],
            "grading": isolation["grading"],
            "execution_identity": isolation["execution_identity"],
            "jail_config": isolation["jail_config"],
            "daemon_container_events": isolation[
                "daemon_container_events"],
        },
    }
    receipt["receipt_sha256"] = _sha_hex(canonical_json(
        {k: v for k, v in receipt.items()
         if k != "receipt_sha256"}).encode())
    return receipt


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("ADAPTATION-GIT-UNAVAILABLE: git not found")
    if p.returncode != 0:
        raise RuntimeError(f"ADAPTATION-GIT-FAILED git {' '.join(args)}: "
                           + (p.stderr or b"").decode()[:200])
    return p.stdout


def frozen_task_files(famc_dir, freeze_commit, family, task):
    """Exact visible task snapshot bytes from freeze-commit objects.

    ({posix-relpath: bytes}, expected-manifest-dict): every
    file|rel of frozen_visible.derive_expected_visible fetched via
    `git show` (never disk). Fail closed like the rest of the
    frozen authority."""
    if not freeze_commit:
        raise RuntimeError("ADAPTATION-NO-COMMIT: freeze commit required")
    exp = _FV.derive_expected_visible(famc_dir, freeze_commit, family,
                                      task)
    root = _git(["rev-parse", "--show-toplevel"],
                cwd=famc_dir).decode().strip()
    prefix = _famc_prefix(famc_dir, root)
    task_rel = f"{prefix}families/{family}/{task}"
    files = {}
    for key in sorted(exp["manifest"]):
        kind, rel = key.split("|", 1)
        if kind != "file":
            continue
        p = subprocess.run(["git", "show",
                            f"{freeze_commit}:{task_rel}/{rel}"],
                           cwd=root, capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(
                f"ADAPTATION-UNRESOLVABLE {task_rel}/{rel} at "
                f"{freeze_commit[:12]}: "
                + (p.stderr or b"").decode()[:200])
        files[rel] = p.stdout
    return files, exp["manifest"]


def _famc_prefix(famc_dir, root):
    """Repo-root-relative famc prefix WITH trailing slash ("" at root).

    Same derivation as frozen_visible._base_prefix (fail closed on
    escape); kept local so this module depends only on frozen_visible
    public behavior plus stdlib git reads."""
    rel = os.path.relpath(os.path.abspath(famc_dir), root)
    if rel == ".." or rel.startswith(".." + os.sep):
        raise RuntimeError("ADAPTATION-NO-REPO: fam-c dir "
                           f"{famc_dir} escapes the git top level {root}")
    if rel == ".":
        return ""
    return rel.replace(os.sep, "/") + "/"

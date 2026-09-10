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

RECEIPT_SCHEMA = "a13-causal-receipt-v1"

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


def build_receipt(*, family, task, capability_id, determinant,
                  determinant_sha256, on, off_noop, pass_through,
                  checker_sha256, truth_sha256,
                  execution_harness_manifest_sha256):
    """Pure A13 causal-receipt builder (schema a13-causal-receipt-v1).

    Binds the determinant, the three legs (program/ABI/consumers/
    adapted shas; execution_evidence slots are None until the
    executed-legs ruling lands), the freeze-derived task/
    capability/checker identities, and the enclosing execution-
    harness identity. Carries shas of model-adjacent bytes nowhere
    and model content nowhere (hash bindings only where P0-3
    already requires them — none here). Returns the receipt
    including its self sha (tamper-evident, normalized-usage
    style). Strict shape validation (fail closed)."""
    for name, value in (
            ("determinant_sha256", determinant_sha256),
            ("checker_sha256", checker_sha256),
            ("truth_sha256", truth_sha256),
            ("execution_harness_manifest_sha256",
             execution_harness_manifest_sha256)):
        _require_sha64(value, name)
    if not isinstance(determinant, dict) or sorted(determinant) != sorted(
            _DETERMINANT_KEYS):
        raise ValueError("ADAPTATION-MALFORMED-DETERMINANT determinant "
                         f"must carry exactly {sorted(_DETERMINANT_KEYS)}")
    for key in _DETERMINANT_KEYS:
        _require_sha64(determinant[key], "determinant." + key)
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
        _require_sha64(leg["program_identity"], leg_name + ".program")
        _require_sha64(leg["adapted_input_sha256"],
                       leg_name + ".adapted_input_sha256")
        if not isinstance(leg["adapted_files"], dict) or not leg[
                "adapted_files"]:
            raise ValueError(f"ADAPTATION-MALFORMED-LEG {leg_name} "
                             "adapted_files must be a nonempty map")
        for fname, fsha in leg["adapted_files"].items():
            _require_sha64(fsha, f"{leg_name}.adapted_files[{fname}]")
        legs[leg_name] = dict(leg)
    receipt = {
        "receipt_schema": RECEIPT_SCHEMA,
        "family": family,
        "task": task,
        "capability": {"capability_id": capability_id},
        "determinant": dict(determinant),
        "determinant_sha256": determinant_sha256,
        "legs": legs,
        "checker": {"checker_sha256": checker_sha256,
                    "truth_sha256": truth_sha256},
        "execution_harness_manifest_sha256":
            execution_harness_manifest_sha256,
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

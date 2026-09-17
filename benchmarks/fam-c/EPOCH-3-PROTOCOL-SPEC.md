# RCOS Fam-C — EPOCH-3 PROTOCOL SPECIFICATION (DRAFT — FROZEN-PENDING)

Drafted: 2026-09-17 (docs-only slice; no harness bytes changed, no lock
edited, no model call made, no battery run).

Authority for this draft: third-party ruling of 2026-09-17 ~10:30Z, recorded
verbatim at `/home/chow/rcos-campaign/RULING-2026-09-17-parse-denial.md`
(thread https://chatgpt.com/c/6aab60f4-15a4-83e9-b239-75a40df4218d):
"CONTRACT-PARSE-DENY = EXPERIMENTAL OUTCOME. N=1. NO
RETRY-UNTIL-ADMISSIBLE. ATTEMPT 2 PRESERVED, NON-ESTIMAND. EPOCH 2 STOPS AT
THE UNREPRESENTABLE FINAL CELL. EPOCH 3 MAY ADD A PRE-FROZEN
MODEL-OUTPUT-INVALID TERMINAL AND RESTART CLEAN."

Status of this document: **CORRECTED DRAFT (2026-09-17) — NOT FROZEN,
IMPLEMENTATION NOT AUTHORIZED.** This revision applies, item by item, the
third-party seat's `ACCEPT-AS-AMENDED` adjudication of the freeze request
(authority: `/home/chow/rcos-campaign/FREEZE-ADJUDICATION-2026-09-17.md`;
dispositions recorded in `FREEZE-REQUEST.md`). The design is approved; the
bytes are not yet frozen. No epoch-3 implementation may land, and no epoch-3
model call may be authorized, before the seat's `EPOCH-3-SPEC-FROZEN —
IMPLEMENTATION AUTHORIZED` ruling on THESE corrected bytes (see §9). Epoch 2
is STOPPED and incomplete — see `EPOCH-2-STOP-RECORD.md`; that record creates
no cell terminal and must not cause `completed_cells()` to advance.

---

## 0. Scope and non-goals

In scope: one new pre-frozen terminal for model output that fails the frozen
response contract, the progress algebra it feeds, the writer site that mints
it, attempt-level reliability accounting, and the epoch-3 lineage/restart
discipline.

Explicit NON-GOALS (each is a fail-closed prohibition, not a preference):

- No retry, no re-sample, no "retry-until-admissible", no re-asking a cell
  whose authorized sample failed the contract (prereg §22: "No retries to
  improve experimental outcomes.").
- No diagnostic repeats inside the live epoch-3 walk: N=1 means the
  claim-grade runner hard-refuses a second provider invocation for the same
  execution cell (`ATTEMPT-BUDGET-DENY`). Any later diagnostic study belongs
  outside `state/epoch3` and outside the frozen ORDER, and is never
  interleaved with the active 240-event walk.
- No heuristic repair of a malformed response, no alternate decoder, no
  arm-specific parse branch, no prompt change between samples.
- No synthesized `arrival.json`, no fake candidate, no second sample, no
  partial arrival assembled from fragments of a failed response.
- No mutation of epoch-2 (or epoch-1) artifacts, locks, terminals, or the
  preserved attempts/INCIDENT under `state/epoch2/_operator-errors/`.
- No splicing of epoch-3 handling into the remaining epoch-2 prefix, and no
  reuse of any epoch-2 cell to satisfy an epoch-3 position.
- No reinterpretation of a recorded failure as infrastructure-invalid after
  observing it: the eight epoch-2 rc1 acquisition artifacts and every
  recorded terminal stay exactly what they are (experimental failures).
- No capability promotion, lock, or consumption is authorized by anything in
  this spec; the `MODEL-OUTPUT-INVALID` terminal never mints a lock.

## 1. The no-arrival terminal: `MODEL-OUTPUT-INVALID.json`

Name and location: `MODEL-OUTPUT-INVALID.json`, written into the cell's
DERIVED run dir (`order.run_dir(fam_c_dir, cell)` —
`state/epoch3/<block>/<universe>/<family>/runs/<cell_id>/`), never an
operator-named path. One file per cell. Write-once: a second write for the
same cell is refused (`MODEL-OUTPUT-INVALID-DENY`), never overwritten.

Schema id: `famc-model-output-invalid-v1`. Exact required fields (no extras
permitted; a field whose value is not available is the JSON value `null` only
where this table says null is legal; a missing required field is
INADMISSIBLE, never defaulted):

```json
{
 "schema": "famc-model-output-invalid-v1",
 "epoch": 3,
 "terminal_status": "COMPLETE-FAILURE",
 "experimental_outcome": true,
 "experimental_task_outcome": "FAIL",

 "cell_id": "<frozen ORDER-EXPANSION cell id (16-hex)>",
 "cell_index": <int>,
 "block": "PQ", "family": "fam04", "task": "T0",
 "cell_event": "T0", "cell_kind": "acquisition-solve",
 "cell_universe": "C", "cell_letter": "C",
 "lane": "Q", "arm": "acquisition", "capability_id": "fam04-PQ-C-K",
 "order_sha256": "<64-hex>",

 "provider_call_id": "<call id>",
 "request_body_sha256": "<64-hex>",
 "response_text_sha256": "<64-hex>",
 "response_bytes": <int>,
 "usage_receipt_sha256": "<64-hex>",
 "normalized_usage_sha256": "<64-hex>",
 "identity_record_sha256": "<64-hex>",

 "protocol_lock_sha256": "<64-hex>",
 "execution_lock_sha256": "<64-hex>",
 "execution_harness_manifest_sha256": "<64-hex>",
 "epoch3_protocol_spec_sha256": "<64-hex>",

 "parser_authority": ["benchmarks/fam-c/harness-run/run_arm_h1.py:extract",
                      "benchmarks/fam-c/harness-run/run_arm_h1.py:_validate_arrival"],
 "contract_error": "CONTRACT-PARSE-DENY: <exact frozen message>",
 "contract_rule": "A11b.2",

 "authorized_estimand_attempt": true,
 "attempt_index": 1,
 "per_attempt_outcome": "CONTRACT-PARSE-DENY",

 "created_utc": "<ISO-8601 Z>",
 "created_by": "benchmarks/fam-c/harness-run/run_arm_h1.py"
}
```

Field semantics (each is mechanically derivable from evidence already on
disk, never reconstructed):

- Cell identity is the SAME production cell-identity surface as a normal
  model run — exactly `cell_id`, `cell_index`, `block`, `family`, `task`,
  `cell_event`, `cell_kind`, `cell_universe`, `cell_letter`, `lane`, `arm`,
  `capability_id`, `order_sha256`, with the values the runner already stamps
  into `H1-RUN-MANIFEST.json` for that cell. `cell_id` is the exact frozen
  ORDER-EXPANSION id (16 lowercase hex, e.g. `9907c5cb038c02e0`), never a
  truncated/expanded paraphrase. No parallel weaker identity schema is
  permitted.
- `provider_call_id` — the `call_id` of the provider call this sample came
  from; the call receipt `call-<id>.json` MUST exist in the same run dir.
- `request_body_sha256` — read back from that receipt's
  `request_body_sha256` field (bound to `call-<id>.request.json` bytes);
  never recomputed from a re-serialized object.
- `response_text_sha256` — sha256 of the exact provider response text bytes.
  The response text MUST be preserved per attempt in the same run dir
  (`raw-<call_id>.txt` on the model-output-invalid path; existing chained
  runs keep `raw.txt`), so this hash is re-verifiable.
- `response_bytes` — byte length of that same preserved text.
- `usage_receipt_sha256` — sha256 of the raw receipt file `call-<id>.json`
  (the same semantics the epoch-2 incident record used).
- `normalized_usage_sha256` — sha256 of `call-<id>.normalized.json`.
- `identity_record_sha256` — sha256 of `identity.json` for this attempt.
  This field is REQUIRED and non-null on a lawful terminal: a sample whose
  required provider/lane identity cannot be established is inadmissible /
  missing evidence, not `MODEL-OUTPUT-INVALID` and not automatically
  infrastructure (§5).
- `protocol_lock_sha256` / `execution_lock_sha256` /
  `execution_harness_manifest_sha256` / `epoch3_protocol_spec_sha256` — the
  execution authority the terminal was minted under: the ACTIVE epoch-3
  protocol and execution lock bytes, the executed harness manifest, and the
  frozen epoch-3 spec bytes. A terminal whose bindings do not match the
  active authority at validation time is INADMISSIBLE.
- `parser_authority` — the exact functions that judged the reply
  (`extract` and `_validate_arrival` in `run_arm_h1.py`); never a helper, a
  heuristic, or an operator judgment.
- `contract_error` — the exact named error raised by the frozen contract,
  message preserved; prefix MUST be one of the eligible names below.
- `authorized_estimand_attempt` / `attempt_index` / `per_attempt_outcome` —
  attempt accounting per §6. On the terminal record itself these are always
  `true` / `1` / the contract error: the terminal is written ONLY for the
  authorized first sample. A second same-cell provider invocation is denied
  (`ATTEMPT-BUDGET-DENY`); no epoch-3 attempt state is
  `diagnostic_repeat: true`. The machine schema deliberately carries no
  local filesystem paths (the ruling text lives in the campaign record, not
  in the portable terminal).

Terminal validation is more than hashing files. The strict validator MUST,
fail closed:

1. re-run the existing request / adapter / usage / identity binding checks
   over the on-disk artifacts named by the terminal;
2. re-run the preserved `raw-<call_id>.txt` through the frozen `extract()`
   and require it to raise the SAME eligible named error recorded in
   `contract_error`. A11b.2 is deterministic: if replay produces an arrival
   or a different error, the terminal is INADMISSIBLE;
3. refuse on any identity, authority-binding, receipt, or byte-count
   mismatch, on a stray execution-implying companion, and on a `cell_id`
   that is not the authorized frozen cell.

Eligible `contract_error` set: exactly the named contract errors raised by
`extract()` / `_validate_arrival()` at the parse gate — i.e. messages whose
prefix is `CONTRACT-PARSE-DENY`, plus `CONTRACT-DECISION-DENY` when raised by
`_validate_arrival()` for an unknown `decision` value. NOT eligible
(everything else, including `CONTRACT-DECISION-DENY` raised later by
`execute_arrival()` for arm illegality, `CONTRACT-ENGINE-DENY`,
`CANDIDATE-INPUT-DENY`, `EVALUATOR-DRIFT-DENY`): those occur only after a
lawful arrival exists, and their cells are ordinary recorded outcomes with
the normal evidence set, not this terminal.

Forbidden companions: a lawful `MODEL-OUTPUT-INVALID.json` coexists with
NO `arrival.json`, NO `H1-RUN-MANIFEST.json`, NO `EVIDENCE-CHAIN.jsonl`, NO
candidate/adapter artifacts, and NO reuse ledger. Any such file beside a
`MODEL-OUTPUT-INVALID.json` is INADMISSIBLE and blocks the walk.

## 2. Writer site (where the terminal is minted)

The terminal is written by the runner, at the parse gate, BEFORE any
adjudication:

- Site (semantic, never line-number normative — implementation may move the
  lines): `benchmarks/fam-c/harness-run/run_arm_h1.py`, in `main()`,
  immediately after the ONE recorded provider call and before/around
  `extract(raw)`. The named `CONTRACT-*` denial is caught at that site and
  the terminal is written into the cell's derived run dir; nothing else on
  the cell path runs.
- Required ordering: (1) the single recorded provider call happens; (2)
  request body, raw receipt, normalized usage, identity record, preserved
  `raw-<call_id>.txt`, and the attempt-ledger row are persisted;
  (3) `extract(raw)` is invoked; (4) on an eligible named denial the runner
  ATOMICALLY creates the write-once terminal. No raw response may first
  become durable after parsing fails — the response bytes are on disk before
  the parser runs. A duplicate or pre-existing terminal for the same cell
  refuses (`MODEL-OUTPUT-INVALID-DENY`). `note_provider_call()` has been
  called; NO call to `note_cell_completed()` occurs on this path.
- The catch is narrow: only the eligible named contract errors of §1 are
  converted to a terminal. Every other exception keeps its current behavior
  (propagate; fail closed; infrastructure stays infrastructure, §5).
- The terminal is a real terminal, not a placeholder: it is written by the
  harness, and it is the ONLY thing that may represent
  "provider call exists + response bytes returned + contract denial +
  no arrival" on the ordered path. It is discovery-free: it is never
  inferred, never written by an operator command, never written after the
  fact from a preserved incident.

`completed_cells()` must never advance on fabricated evidence. The walk may
advance past the cell ONLY when `order.cell_state()` validates the terminal
with a strict validator (§3), and that validator MUST re-derive every hash
from the bytes on disk and refuse on any mismatch, missing receipt, missing
preserved response, foreign cell identity, wrong lane, stray `arrival.json`,
or stray manifest. Tampering or ambiguity yields `INADMISSIBLE`, and the
walk blocks (no advance).

## 3. Progress algebra

Unchanged from the epoch-2 ruling, extended by exactly one terminal:

```text
model cell (T0..T4 model run)
  COMPLETE                                -> progress-valid (unchanged)
  COMPLETE-FAILURE (MODEL-OUTPUT-INVALID) -> progress-valid (NEW; failure)

PROMOTION            COMPLETE | NOT-PROMOTED        (unchanged)
CAPABILITY_LOCK      COMPLETE | NOT-LOCKED          (unchanged)
downstream T2/T3/T4 of an acquisition-failed
  capability universe (A/C)  NOT-EVALUABLE          (unchanged)

INCOMPLETE / INADMISSIBLE                 -> never progress-valid
```

Progress status is NOT experimental correctness. A `COMPLETE-FAILURE`
terminal has no checker/evaluator verdict (no evaluator ran), but its
experimental task outcome is **FAIL / non-SHIP** — it is NOT missing
evidence. Malformed model output is an experimental outcome under the frozen
taxonomy and must never be converted into INCONCLUSIVE evidence or allowed to
evade the correctness gate.

A `COMPLETE-FAILURE` terminal converts to nothing: it authorizes no
promotion, no lock creation, no capability consumption, no retry, no
`arrival.json`, and no verdict. It is a recorded experimental failure of the
model cell.

Acquisition model-output-invalid algebra — BOTH acquisition events
(ruling language, mechanized):

```text
T0 MODEL-OUTPUT-INVALID terminal (COMPLETE-FAILURE)
  candidate = absent                       (no synthesized arrival/candidate)
  T1 NOT-EVALUABLE  (reason acquisition-failed)
  PROMOTION NOT-PROMOTED
  CAPABILITY_LOCK NOT-LOCKED
  T2/T3/T4 NOT-EVALUABLE (reason acquisition-failed)
  prefix continues

T0 COMPLETE, T1 MODEL-OUTPUT-INVALID terminal (COMPLETE-FAILURE)
  candidate exists (the real T0 arrival payload) but was NEVER validly
  validated (no candidate-validation event exists)
  PROMOTION NOT-PROMOTED
  CAPABILITY_LOCK NOT-LOCKED
  T2/T3/T4 NOT-EVALUABLE (reason acquisition-failed)
  prefix continues
```

Consequences the implementation must carry (all in-scope for the freeze, none
implemented by this slice): `order.progress_valid()` accepts
`COMPLETE-FAILURE` for model cells only; `order._model_run_state()` gains the
strict terminal validator of §1; `order.acquisition_failed()` gains the
T0-terminal disjunct AND the T1-terminal disjunct ("the T0 cell is validated
COMPLETE and the T1 cell carries a validated `MODEL-OUTPUT-INVALID`
terminal" — the existing predicate requires both T0/T1 COMPLETE plus a
candidate-validation link, so a T1 parse terminal does not satisfy it today)
so the universe still yields NOT-EVALUABLE and the runner's pre-call
`ACQUISITION-FAILED-DENY` refusal still fires (`order.authorize_event`,
`_local_state`); `promotion.advance()` records BOTH governance terminals for
such universes (NOT-PROMOTED, then NOT-LOCKED) on the exact governance
evidence union of §3.1.

A model-output-invalid terminal is NOT-EVALUABLE-equivalent for downstream
purposes only; it is never reported as COMPLETE success, never counted as a
capability, and never pooled with `ship`/`fix` cells.

## 3.1 Governance evidence union (exact frozen shape)

For an acquisition-failed universe, the terminal-governance records carry
this exact evidence binding (schema extension; epoch-2 validators assume real
T0/T1 chain tips, so this is a genuine epoch-3 extension, never a relaxation
of an existing field):

```text
failure_event: "T0" | "T1"

acquisition_evidence:
  T0:
    kind: "MODEL-OUTPUT-INVALID"
    terminal_sha256: <sha>
  OR
    kind: "CHAIN"
    chain_tip: <sha>
    candidate_sha256: <sha>

  T1:
    null
  OR
    kind: "MODEL-OUTPUT-INVALID"
    terminal_sha256: <sha>

candidate_sha256:
  null                 # T0 terminal (no candidate ever existed)
  <real T0 candidate>  # T1 terminal (the T0 arrival payload candidate)
```

- `PROMOTION-OUTCOME.json` carries `reason: "acquisition-failed"` plus
  `failure_event` and this exact evidence binding.
- `CAPABILITY-LOCK-OUTCOME.json` binds the promotion-outcome bytes
  (`promotion_outcome_sha256`) and the same acquisition evidence.
- A null chain tip is NEVER equivalent to an existing chain; the validator
  re-derives the terminal sha256 or the chain tip from disk and refuses on
  mismatch, on a wrong terminal SHA, or on the wrong branch shape.

## 4. Attempt accounting and lane reliability (attempt-level, frozen formula)

Two statistics, reported separately, never collapsed:

```text
first_attempt_contract_admissibility
  = admissible first authorized samples / all authorized first samples

all_provider_call_contract_admissibility
  = admissible model responses / all provider calls actually made
```

Definitions: a **first authorized sample** is the single authorized sample
(N=1) for a model cell, taken as the first provider call made for that cell by
the runner. **Admissible** means the frozen A11b.2 contract returned an
arrival (`extract()` returned `(arrival, parse_mode)`); a response that raised
an eligible `CONTRACT-*` error is INADMISSIBLE. Counts come from evidence
already required elsewhere in the frozen design (prereg §16 requires model
invocations and retry count to be collected independently; §24's evidence
table requires `model_calls` and `retries` per row).

`ATTEMPT-LEDGER.jsonl` (per cell, in the cell's derived run dir, schema
`famc-attempt-ledger-v1`) is the ENUMERATION AUTHORITY for both statistics:
every provider invocation authorized for the cell is enumerated by exactly
one row, in call order, whether or not it produced a `call-<id>.json`
receipt:

```json
{"attempt_index": 1, "provider_call_id": "<id>",
 "request_body_sha256": "<64-hex>",
 "authorized_estimand_attempt": true,
 "outcome": "ADMISSIBLE" | "<CONTRACT-* named error>" | "NO-MODEL-SAMPLE-INFRASTRUCTURE",
 "response_text_sha256": "<64-hex>|null", "response_bytes": <int>|null,
 "usage_receipt_sha256": "<64-hex>|null", "identity_record_sha256": "<64-hex>|null"}
```

Ledger rules, fail closed: `request_body_sha256` is required on every row;
`response_text_sha256` / `response_bytes` / `usage_receipt_sha256` /
`identity_record_sha256` may be `null` ONLY for a true no-model-sample
infrastructure failure (§5); when they are present they MUST cross-check the
actual files on disk; every lawful `MODEL-OUTPUT-INVALID.json` terminal
corresponds to exactly one authorized ledger row, and vice versa.

N=1 is enforced, not merely declared: the claim-grade runner HARD-REFUSES a
second provider invocation for the same execution cell — `ATTEMPT-BUDGET-DENY`
— before any second call is made. There is no lawful `diagnostic_repeat: true`
attempt state inside the epoch-3 walk, and no retry budget for contract
denial, malformed output, bad generated code, rc1 solver failure, or any
other experimental outcome. Any later diagnostic study is a separate
protocol-extra activity outside `state/epoch3` and outside the frozen ORDER,
never interleaved with the active 240-event walk, and it never rescues,
replaces, or reclassifies an authorized attempt or makes a cell "eventually
admissible". A future successful extra sample is never reported as one
successful cell. Only authorized first samples count in the first statistic;
every enumerated provider call counts in the second.

Reported together with both statistics, the DENOMINATOR DECOMPOSITION:
contract denials vs infrastructure / no-sample events, so an infrastructure
outage is never rhetorically presented as a model JSON-contract failure.

Epoch-2 accounting context (recorded fact; NOT an epoch-3 pattern): the
epoch-2 run `state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/` preserves two
provider-call receipts with byte-identical request bodies
(`request_body_sha256 fe3c67792aea41598a6a967089f89a24f275d67a1f2459a00b21c39ff72ffd5e`,
calls `dda8f5746cfaa800` and `53cdb3e6bd66731e`) while the chain binds
`call_count: 1` for `53cdb3e6bd66731e`; the first call's response text was
not preserved per attempt, so its per-attempt contract admissibility is not
derivable from preserved evidence. That second call predates adjudication and
survives only as preserved evidence; epoch 3 preserves response text per
attempt (`raw-<call_id>.txt`) on every path and forbids the second call
outright (`ATTEMPT-BUDGET-DENY`).

## 4.1 Terminal-cell reporting (evidence table, exit code, gate consequences)

- Runner exit code **0** for a successfully recorded terminal: it is a
  completed cell — a recorded experimental outcome — exactly as a committed
  failed candidate validation exits 0 today. Non-zero stays reserved for
  infrastructure / refusal paths.
- `PREREG.md` §24 evidence row for a terminal cell is corrected to:
  `ship: false` (not null — a terminal is a non-SHIP correctness failure, not
  missing evidence); `hidden_tests_passed: null`; checker verdict / checker
  return code `null` (no evaluator ran); `run_manifest_hash: null`;
  `evidence_hash` = `terminal_record_sha256`, with `terminal_record_sha256`
  retained explicitly as its own field; `model_calls: 1`; `retries: 0`;
  `terminal_class: "MODEL-OUTPUT-INVALID"`; estimand evidence; usage from the
  validated call artifacts.
- Capability fields: `capability_available` is DERIVED from the frozen cell /
  validated lock — on downstream A/C cells a valid locked capability may have
  been available and presented before the model produced malformed output —
  while selection, load, invocation, consumption, and material contribution
  are `false` because no parseable decision existed. This preserves
  genuine-reuse coverage.
- Gate consequences: a T2/T3 terminal is a non-SHIP correctness failure and
  CANNOT create an efficiency win by failing cheaply; a treatment T4 terminal
  is NEVER a correct specificity rejection. This follows the frozen rule that
  model / malformed-output failures are experimental outcomes, not invalid
  runs.

## 5. Infrastructure rule, sample boundary, and replacement unit

Frozen sample boundary (mechanical, no judgment — an HTTP error body is not a
model sample):

```text
MODEL SAMPLE EXISTS
= the bound provider adapter returned a completion/sample object containing
  model-generated response text attributable to the preregistered lane, and
  that text was handed to the frozen parser.

provider/transport error before such a completion sample exists
= infrastructure candidate, EVEN IF the HTTP error itself carried a body.

completion text + valid lane identity + contract denial
= experimental outcome, never infrastructure.

completion text whose required provider/lane identity cannot be established
= inadmissible / missing evidence — NOT MODEL-OUTPUT-INVALID, and NOT
  automatically infrastructure.
```

Infrastructure-invalid handling, once the boundary admits an event:

```text
original paired comparison      -> infrastructure-invalid
exactly ONE whole-pair replacement (identical frozen settings, linked)
replacement infrastructure-invalid again -> missing evidence -> INCONCLUSIVE
```

Replacement unit, frozen explicitly (the prereg whole-pair rule covers
downstream A/B and C/D comparisons; acquisition is not one of those paired
comparisons):

```text
Downstream (A/B or C/D, same block/family/task):
  one member genuinely infrastructure-invalid
  -> exactly ONE whole-pair replacement.

Acquisition (T0+T1 of one (block, universe, family)):
  the T0->T1 unit is INDIVISIBLE.
  a genuine infrastructure failure in either T0 or T1
  -> exactly ONE linked replacement of the ENTIRE T0->T1 unit, from a fresh
     namespace.
  if original T1 failed infrastructure after a successful T0, the replacement
  T1 may NOT reuse the original T0 candidate: the replacement restarts at T0.
  a second infrastructure failure in that replacement unit
  -> missing acquisition evidence / downstream NOT-EVALUABLE / INCONCLUSIVE
     as applicable.
Experimental outcomes NEVER trigger this mechanism.
```

Model reasoning failure, tool misuse, agent timeout caused by its own
behavior, bad generated code, malformed output, rc1 solver failure, and
failed candidate validation are experimental outcomes, always.

## 6. Epoch-3 lineage and restart discipline

Epoch 3 exists only as an explicit on-disk lineage, in the same mechanical
form as epoch 2, and it RESTARTS the frozen 240-event order from event 0:

- `EPOCH-3-TRANSITION.json` at the Fam-C root, citing at minimum:
  - the corrected `EPOCH-2-STOP-RECORD.md` sha256;
  - the epoch-2 FINAL lock hashes (`EXECUTION-LOCK-EPOCH2.json` sha256
    `e662463e50fbb7d08115063595a4392437ccac54e6d2dd989a730ecafe619a80`,
    `PROTOCOL-LOCK-EPOCH2.json` sha256
    `978d5e3e8d6f8797343830d565583804ae58a426b114331e74b2f4ebe1f74b00`), the
    epoch-2 transition record sha256
    `047aef2fcfef76803cb0999edcd17027aa2997b91a7face8ad9a83012136bb6b`, and
    the epoch-2 finalization commit `53e72ef4cec5ec7ecc9628c348a36635c02bd2d4`;
  - the FROZEN `EPOCH-3-PROTOCOL-SPEC.md` sha256 and its freeze commit (the
    commit that lands the seat's `EPOCH-3-SPEC-FROZEN — IMPLEMENTATION
    AUTHORIZED` adjudication record);
  - the exact frozen `ORDER-EXPANSION.json` sha256
    `449be793cf764204b8326a56914dd19c90f16371600db9d97faf60ccbe43f47a`
    (the epoch-2 protocol lock's pin of the same bytes);
  - the epoch-3 state prefix `state/epoch3`.
- Fresh locks `EXECUTION-LOCK-EPOCH3.json` / `PROTOCOL-LOCK-EPOCH3.json`,
  `epoch: 3`, their OWN append-only amendment lineage starting `[]`, minted
  open and later finalized by the owner under the standard A16 flow. The
  epoch-2 (and epoch-1) FINAL locks remain untouched historical records.
- State namespace `state/epoch3/`: every derived path (runs, capability
  dirs) is prefixed with it. Epoch-3 `completed_cells()` / `cell_state()` /
  specificity walks never scan `state/epoch2/**` or `state/**`, and no
  epoch-2 artifact is ever written to.
- The walk restarts at ORDER-EXPANSION cell index 0 (`9907c5cb038c02e0`,
  PQ/fam05/T0/A) and proceeds in the frozen order. Epoch-2 cells populate no
  epoch-3 prefix position; the ruling's archive-don't-carry-forward rule
  (EPOCH-1-CLOSURE.md) applies to epoch 2 verbatim.
- No splicing: the epoch-3 terminal algebra of this spec is not applied to,
  and does not resume, the epoch-2 prefix. Epoch 2 remains a STOPPED /
  INCOMPLETE, preserved epoch — not "closed" (`EPOCH-2-STOP-RECORD.md`).
- Claim boundary (frozen wording): epoch 3 produces a homogeneous
  estimand-grade **PILOT-GRADE** series, NOT a "claim-grade Fam-C series".
  Frozen `PREREG.md` §18.1 makes the current family/task scale PILOT-GRADE
  and explicitly bars it from earning claim-grade Fam-C or compounding PASS.
  Epoch 3 fixes the validity of the execution protocol; it does not silently
  upgrade task scale.
- Harness/epoch machinery must be extended for a third epoch (the current
  `harness/epoch.py` is epoch-2-specific: `EPOCH_ID`, `STATE_SUBDIR`,
  `TRANSITION_FILE`, lock filenames and the cited epoch-1 constants are
  literals). That extension is implementation, is out of scope for this
  docs-only slice, and may land only after the freeze (§7/§9).

## 7. Freeze checklist and certification standard for epoch 3 (operational)

1. Third-party seat adjudicates every item in `FREEZE-REQUEST.md`; this spec
   is frozen at the corrected bytes (corrections land as listed amendments,
   never as silent edits) and the seat issues the freeze ruling with
   implementation authorization.
2. Implementation lands (authorized only after step 1): terminal writer,
   strict validator (including the raw-response replay of §1), both-branch
   algebra extension and the §3.1 governance evidence union, attempt ledger
   with `ATTEMPT-BUDGET-DENY`, per-attempt response preservation, epoch-3
   lineage mechanics, and the preflight governance extension of FR-13.
3. REQUIRED adversarial probes (certification standard, in addition to
   whatever else the implementation adds):
   1. T0 `MODEL-OUTPUT-INVALID` continuation (no candidate; T1
      NOT-EVALUABLE; NOT-PROMOTED; NOT-LOCKED; downstream NOT-EVALUABLE;
      prefix advances);
   2. T1 `MODEL-OUTPUT-INVALID` continuation (T0 COMPLETE, real candidate,
      never validated; NOT-PROMOTED; NOT-LOCKED; downstream NOT-EVALUABLE;
      prefix advances);
   3. downstream T2/T3 terminal counted non-SHIP and barred from creating an
      efficiency win;
   4. raw-response replay through `extract()` producing the exact recorded
      denial (same eligible named error);
   5. identity-invalid response cannot mint a terminal;
   6. HTTP/provider error body without a completion sample stays
      infrastructure, not terminal;
   7. same-cell second provider invocation denied (`ATTEMPT-BUDGET-DENY`);
   8. tampered/missing attempt-ledger row refuses;
   9. execution/protocol lock binding mismatch on the terminal refuses;
   10. governance records with a wrong terminal SHA or the null-tip branch
       refuse;
   11. epoch-2 state cannot satisfy an epoch-3 cell;
   12. a tampered terminal never advances the prefix.
4. Certification: full battery green at the frozen ref, V1/V2/V3 `0/0/0`,
   transition/lock certification, and post-FINAL refusal proofs.
5. Fresh epoch-3 locks are finalized (both FINAL) and the runner's FINAL
   gate passes. Only then does the epoch-3 walk begin at event 0 — NO
   epoch-3 provider call may happen before both epoch-3 locks are FINAL.

## 8. Freeze items and their adjudication status

All items FR-1 … FR-13 (plus the recorded conflicts) are enumerated in
`FREEZE-REQUEST.md`, which now also carries the seat's per-item dispositions
(`2026-09-17`: FR-4 ACCEPT; FR-1…FR-3, FR-5…FR-13 ACCEPT-AS-AMENDED with
FR-12's implementation authorization deferred). This section intentionally
holds no independent decisions: the freeze request is the adjudication
surface, and the corrected sections above are the normative amended text.
Remaining open question: none at the design level — the pending step is the
seat's freeze ruling on these corrected bytes.

## 9. Status and claim boundary

This document is the CORRECTED DRAFT prepared by the operator session for
third-party adjudication: it applies, item by item, the `ACCEPT-AS-AMENDED`
adjudication of the freeze request (authority:
`/home/chow/rcos-campaign/FREEZE-ADJUDICATION-2026-09-17.md`; dispositions
recorded in `FREEZE-REQUEST.md`). It is NOT yet frozen and implementation is
NOT yet authorized. It changes no frozen byte, mints no terminal for epoch 2,
writes no epoch-2 state, authorizes no epoch-3 execution, and makes no claim
about lane P or lane Q reliability. Its only force is as proposed protocol
text pending the freeze ruling on these bytes.

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

Status of this document: **DRAFT.** Nothing in it is frozen. No epoch-3
implementation may land, and no epoch-3 model call may be authorized, before
every item in `FREEZE-REQUEST.md` is adjudicated by the third-party seat and
this spec's bytes are recorded as frozen (see §9). Epoch 2 is STOPPED and
incomplete — see `EPOCH-2-STOP-RECORD.md`; that record creates no cell
terminal and must not cause `completed_cells()` to advance.

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

 "block": "PQ", "universe": "C", "family": "fam04",
 "task": "T0", "cell_event": "T0", "cell_kind": "acquisition-solve",
 "lane": "Q", "cell_id": "<64-hex>", "cell_index": <int>,

 "provider_call_id": "<call id>",
 "request_body_sha256": "<64-hex>",
 "response_text_sha256": "<64-hex>",
 "response_bytes": <int>,
 "usage_receipt_sha256": "<64-hex>",
 "normalized_usage_sha256": "<64-hex>",
 "identity_record_sha256": "<64-hex>",

 "parser_authority": ["benchmarks/fam-c/harness-run/run_arm_h1.py:extract",
                      "benchmarks/fam-c/harness-run/run_arm_h1.py:_validate_arrival"],
 "contract_error": "CONTRACT-PARSE-DENY: <exact frozen message>",
 "contract_rule": "A11b.2",

 "authorized_estimand_attempt": true,
 "diagnostic_repeat": false,
 "attempt_index": 1,
 "per_attempt_outcome": "CONTRACT-PARSE-DENY",

 "created_utc": "<ISO-8601 Z>",
 "created_by": "benchmarks/fam-c/harness-run/run_arm_h1.py",
 "ruling_reference": "/home/chow/rcos-campaign/RULING-2026-09-17-parse-denial.md"
}
```

Field semantics (each is mechanically derivable from evidence already on
disk, never reconstructed):

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
- `identity_record_sha256` — sha256 of `identity.json` for this attempt;
  `null` ONLY when the frozen identity gate itself failed (which is
  infrastructure, not this terminal — see §5 — so in practice this field is
  always present on a lawful `MODEL-OUTPUT-INVALID` record).
- `parser_authority` — the exact functions that judged the reply
  (`extract` and `_validate_arrival` in `run_arm_h1.py`); never a helper, a
  heuristic, or an operator judgment.
- `contract_error` — the exact named error raised by the frozen contract,
  message preserved; prefix MUST be one of the eligible names below.
- `authorized_estimand_attempt` / `diagnostic_repeat` / `attempt_index` /
  `per_attempt_outcome` — attempt accounting per §6. On the terminal record
  itself these are always `true` / `false` / `1` / the contract error: the
  terminal is written ONLY for the authorized first sample. Diagnostic
  repeats never write a terminal (§6).

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

- Site: `benchmarks/fam-c/harness-run/run_arm_h1.py` `main()`, the gate that
  currently reads `OB.note_provider_call()` (line 3896) and
  `arrival, parse_mode = extract(raw)` (line 3897). The named `CONTRACT-*`
  error is caught at that site and the terminal is written into the cell's
  derived run dir; nothing else on the cell path runs.
- Ordering facts already frozen and unchanged: the provider call happens
  (single invocation site), the call receipt + normalized usage + identity
  record + `prompt.txt` are on disk, `note_provider_call()` has been called,
  and NO call to `note_cell_completed()` occurs on this path.
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

A `COMPLETE-FAILURE` terminal converts to nothing: it authorizes no
promotion, no lock creation, no capability consumption, no retry, no
`arrival.json`, and no verdict. It is a recorded experimental failure of the
model cell.

Acquisition (T0) model-output-invalid algebra (ruling language, mechanized):

```text
T0 MODEL-OUTPUT-INVALID terminal (COMPLETE-FAILURE)
  candidate = absent                       (no synthesized arrival/candidate)
  T1 NOT-EVALUABLE  (reason acquisition-failed)
  PROMOTION NOT-PROMOTED
  CAPABILITY_LOCK NOT-LOCKED
  T2/T3/T4 NOT-EVALUABLE (reason acquisition-failed)
  prefix continues
```

Consequences the implementation must carry (all in-scope for the freeze, none
implemented by this slice): `order.progress_valid()` accepts
`COMPLETE-FAILURE` for model cells only; `order._model_run_state()` gains the
strict terminal validator; `order.acquisition_failed()` gains a second
disjunct ("the T0 cell carries a validated `MODEL-OUTPUT-INVALID` terminal" —
derived from the validated terminal, never from file presence) so a universe
with no T1 run still yields NOT-EVALUABLE and the runner's pre-call
`ACQUISITION-FAILED-DENY` refusal still fires (`order.authorize_event`,
`_local_state`); `promotion.advance()` records BOTH governance terminals for
such a universe (NOT-PROMOTED, then NOT-LOCKED) on evidence that has no T1
chain tip — the exact record shape for that case is a freeze item
(`FREEZE-REQUEST.md` FR-5).

A model-output-invalid terminal is NOT-EVALUABLE-equivalent for downstream
purposes only; it is never reported as COMPLETE success, never counted as a
capability, and never pooled with `ship`/`fix` cells.

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
table requires `model_calls` and `retries` per row):

- denominator of the first statistic and numerator of the second — one entry
  per cell: the chained `model-call` link in `EVIDENCE-CHAIN.jsonl` (a lawful
  arrival) OR the validated `MODEL-OUTPUT-INVALID.json` terminal (a contract
  denial) OR an attempt-ledger entry for an infrastructure-invalid sample
  (which counts in neither numerator);
- denominator of the second statistic — every provider call actually made:
  every `call-<id>.json` receipt on disk, including diagnostic repeats and
  infrastructure-invalid calls. The epoch-2 precedent
  (`state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/`) shows why this
  denominator must be enumerated from receipts, not from chain links: it
  carries two receipts and one chain link.

Attempt ledger (per cell, written by the runner under the cell's derived run
dir as `ATTEMPT-LEDGER.jsonl`, schema `famc-attempt-ledger-v1`), one row per
provider call actually made, in call order:

```json
{"attempt_index": 1, "provider_call_id": "<id>",
 "authorized_estimand_attempt": true, "diagnostic_repeat": false,
 "outcome": "ADMISSIBLE" | "<CONTRACT-* named error>" | "INFRASTRUCTURE-INVALID",
 "response_text_sha256": "<64-hex>", "response_bytes": <int>,
 "usage_receipt_sha256": "<64-hex>"}
```

Rules: N=1 authorized sample per cell; no retry budget for contract denial,
malformed output, bad generated code, rc1 solver failure, or any other
experimental outcome. A second provider call for the same cell is lawful only
as a pre-declared protocol-extra diagnostic repeat recorded with
`authorized_estimand_attempt: false`, `diagnostic_repeat: true`; it never
rescues, replaces, or reclassifies attempt 1, never writes a terminal, and
never makes the cell "eventually admissible". A future third successful
sample is never reported as one successful cell. Every attempt counts in the
all-provider-calls statistic; only authorized first samples count in the
first statistic.

Epoch-2 accounting gap to be closed by the freeze (recorded, not hidden): the
epoch-2 run `state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/` preserves two
provider-call receipts with byte-identical request bodies
(`request_body_sha256 fe3c67792aea41598a6a967089f89a24f275d67a1f2459a00b21c39ff72ffd5e`,
calls `dda8f5746cfaa800` and `53cdb3e6bd66731e`) while the chain binds
`call_count: 1` for `53cdb3e6bd66731e`; the first call's response text was
not preserved per attempt (its reply is not on disk; `raw.txt` belongs to the
chained call), so its per-attempt contract admissibility is not derivable
from preserved evidence. Epoch 3 must preserve response text per attempt
(`raw-<call_id>.txt`) on every path, so both statistics are computable from
immutable bytes (`FREEZE-REQUEST.md` FR-6).

## 5. Infrastructure rule (restated, unchanged) and its exact boundary

A genuine infrastructure-invalid event is one that prevents the model sample
from existing — e.g. a qualifying 503-class transport/provider failure with
NO response body. Then, and only then:

```text
original paired comparison      -> infrastructure-invalid
exactly ONE whole-pair replacement (identical frozen settings, linked)
replacement infrastructure-invalid again -> missing evidence -> INCONCLUSIVE
```

That is at most two pair executions, not "retry the bad cell until it works".

Boundary rule (mechanical, no judgment): if a provider response body exists
and was handed to the frozen parser, the failure is NEVER infrastructure —
it is an experimental outcome recorded by §1/§2 or by the normal evidence
set. If no response body exists (transport/HTTP failure before any body), it
is infrastructure under the frozen A14 taxonomy and the replacement rule
above applies. Model reasoning failure, tool misuse, agent timeout caused by
its own behavior, bad generated code, malformed output, rc1 solver failure,
and failed candidate validation are experimental outcomes, always.

## 6. Epoch-3 lineage and restart discipline

Epoch 3 exists only as an explicit on-disk lineage, in the same mechanical
form as epoch 2, and it RESTARTS the frozen 240-event order from event 0:

- `EPOCH-3-TRANSITION.json` at the Fam-C root, citing: the epoch-2 stop
  record's own bytes (`EPOCH-2-STOP-RECORD.md` sha256), the epoch-2 FINAL
  lock hashes (`EXECUTION-LOCK-EPOCH2.json` sha256
  `e662463e50fbb7d08115063595a4392437ccac54e6d2dd989a730ecafe619a80`,
  `PROTOCOL-LOCK-EPOCH2.json` sha256
  `978d5e3e8d6f8797343830d565583804ae58a426b114331e74b2f4ebe1f74b00`), the
  epoch-2 transition record sha256
  `047aef2fcfef76803cb0999edcd17027aa2997b91a7face8ad9a83012136bb6b`, the
  epoch-2 finalization commit `53e72ef4cec5ec7ecc9628c348a36635c02bd2d4`,
  and the epoch-3 state prefix `state/epoch3`.
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
  and does not resume, the epoch-2 prefix. Epoch 2 remains a stopped,
  incomplete, preserved epoch (`EPOCH-2-STOP-RECORD.md`).
- Harness/epoch machinery must be extended for a third epoch (the current
  `harness/epoch.py` is epoch-2-specific: `EPOCH_ID`, `STATE_SUBDIR`,
  `TRANSITION_FILE`, lock filenames and the cited epoch-1 constants are
  literals). That extension is implementation, is out of scope for this
  docs-only slice, and may land only after the freeze (§9).

## 7. Freeze checklist for epoch 3 (operational)

1. Third-party seat adjudicates every item in `FREEZE-REQUEST.md`.
2. This spec is frozen (bytes recorded; corrections land as listed
   amendments, never as silent edits).
3. Implementation lands: terminal writer, strict validator, algebra
   extension, attempt ledger, epoch-3 lineage mechanics — each with
   adversarial tests (including a tampered terminal, a stray manifest, a
   foreign cell id, and a second write).
4. Fresh epoch-3 locks are finalized (both FINAL) and the runner's FINAL
   gate passes; the certified battery and preflight are green at the frozen
   ref.
5. Only then does the epoch-3 walk begin at event 0. No epoch-3 provider
   call may happen before step 4.

## 8. Open questions for freeze

Enumerated, with proposed text and alternatives, in `FREEZE-REQUEST.md`
(FR-1 … FR-13, plus the recorded conflicts). This section intentionally holds
no independent decisions: the freeze request is the adjudication surface.

## 9. Status and claim boundary

This document is a DRAFT prepared by the operator session for third-party
adjudication. It changes no frozen byte, mints no terminal for epoch 2,
authorizes no epoch-3 execution, and makes no claim about lane P or lane Q
reliability. Its only force is as proposed protocol text pending the ruling
that freezes it.

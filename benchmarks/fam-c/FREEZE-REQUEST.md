# RCOS Fam-C — EPOCH-3 FREEZE REQUEST (third-party adjudication)

Requested: 2026-09-17, by the operator session, per the ruling at
`/home/chow/rcos-campaign/RULING-2026-09-17-parse-denial.md` ("EPOCH 3 MAY
ADD A PRE-FROZEN MODEL-OUTPUT-INVALID TERMINAL AND RESTART CLEAN").

Artifacts under request (CORRECTED bytes from the docs-only correction
commit on `r4-reconcile`, child of `8b5e270`; sha256):

- `benchmarks/fam-c/EPOCH-3-PROTOCOL-SPEC.md`
  sha256 `1ce2bbc8b8981b4c1a51c6858a6f5c3950b5a9476fb2a3f8d99351308d3166d7`
- `benchmarks/fam-c/EPOCH-2-STOP-RECORD.md`
  sha256 `4e0e84ec6c4f13baebd319b40e11ce1beb6258110146fb1d6066afed74e70f4c`

How to freeze: return an adjudication per item (ACCEPT / ACCEPT-AS-AMENDED
with the amended text / REJECT with reason). On ACCEPT of every item, the
spec bytes above become the frozen epoch-3 protocol text and are recorded in
the epoch-3 protocol lock's governed map; corrections land only as listed
amendments. Nothing in this request is frozen yet, and no epoch-3
implementation or model call may precede the freeze.

Each item states: the decision needed, the proposed text, alternatives
considered, and the consequence of the decision.

---

## ADJUDICATION OUTCOME — 2026-09-17 (third-party seat)

Verdict: **ACCEPT-AS-AMENDED AT THE DESIGN LEVEL — EPOCH 3 IS NOT YET
FROZEN, AND IMPLEMENTATION IS NOT YET AUTHORIZED.** Authority (verbatim
record): `/home/chow/rcos-campaign/FREEZE-ADJUDICATION-2026-09-17.md`. The
seat verified that `8b5e27011cfa0b4640af11840b2b45c0d641cfc7` is genuinely
spec-first (docs only; no harness byte, lock, or `state/` evidence changed)
and approved the architecture, requiring ONE more docs-only correction commit
applying the item amendments below. The seat will adjudicate the DIFF only
against its ruling — no new criteria at that point — and if it matches, the
next ruling is `EPOCH-3-SPEC-FROZEN — IMPLEMENTATION AUTHORIZED`.

Applied in: the docs-only correction commit on `r4-reconcile` (child of
`8b5e270`), touching only `EPOCH-3-PROTOCOL-SPEC.md`,
`EPOCH-2-STOP-RECORD.md`, `FREEZE-REQUEST.md`, and — to record this ruling —
`FAMC-EXECUTION-STATUS.md`. No harness change, no lock change, no `state/`
write, no model call.

Supersession rule: for every item disposed ACCEPT-AS-AMENDED, the NORMATIVE
text is the corrected `EPOCH-3-PROTOCOL-SPEC.md` at the section named below;
any proposal wording in this request that differs from it is superseded. This
request remains historical META (per the seat's FR-13 ruling); its
disposition table is the record of what was asked and how it was ruled.

| Item | Disposition | Amendment applied (normative location) |
|---|---|---|
| FR-1 | ACCEPT-AS-AMENDED | Production cell-identity surface (16-hex frozen ORDER-EXPANSION cell id, full field set), required non-null identity record, execution-authority bindings (protocol/execution lock, harness manifest, frozen spec sha), machine schema drops the local ruling path; validator re-runs the request/adapter/usage/identity binding checks AND replays `raw-<call_id>.txt` through `extract()` requiring the same eligible named error — replay yielding an arrival or a different error ⇒ INADMISSIBLE (spec §1) |
| FR-2 | ACCEPT-AS-AMENDED | COMPLETE-FAILURE keeps progress, but its experimental task outcome is FAIL / non-SHIP, not missing evidence; algebra extended to BOTH acquisition events — T0 terminal, and T0 COMPLETE + T1 terminal with a real, never-validated candidate (spec §3) |
| FR-3 | ACCEPT-AS-AMENDED | Writer site stated semantically (no line-number normativity); required ordering: persist request/receipt/normalized usage/identity + preserved response + attempt-ledger row → invoke `extract(raw)` → atomically create the write-once terminal; duplicate refuses; no `note_cell_completed()` (spec §2) |
| FR-4 | ACCEPT | Forbidden-companion rule kept as submitted: call-capture evidence may coexist; any execution-implying companion makes the terminal INADMISSIBLE (spec §1) |
| FR-5 | ACCEPT-AS-AMENDED | Exact governance evidence union frozen and supports both failure events; `reason: acquisition-failed` + `failure_event` + evidence binding in PROMOTION-OUTCOME.json; CAPABILITY-LOCK-OUTCOME.json binds the promotion bytes + same evidence; a null tip is never equivalent to an existing chain; validator re-derives from disk; genuine epoch-3 schema extension (spec §3.1) |
| FR-6 | ACCEPT-AS-AMENDED | No diagnostic repeats in the live walk — a second same-cell provider invocation is `ATTEMPT-BUDGET-DENY`; the attempt ledger is the enumeration authority (binds the request body, null response only for a true no-sample infrastructure failure, hashes cross-check files, one row per lawful terminal); both statistics kept plus denominator decomposition (spec §4) |
| FR-7 | ACCEPT-AS-AMENDED | Transition additionally cites the corrected stop-record sha, the frozen spec sha + its freeze commit, the exact frozen ORDER-EXPANSION.json sha, plus the epoch-2 lock hashes/transition hash/finalization commit; epoch machinery extension remains a post-freeze implementation item (spec §6) |
| FR-8 | ACCEPT-AS-AMENDED | Restart at event 0, absolutely no splicing; wording corrected to a PILOT-GRADE estimand series per PREREG §18.1, never a "claim-grade Fam-C series" (spec §6) |
| FR-9 | ACCEPT-AS-AMENDED | Sample boundary frozen (MODEL SAMPLE EXISTS = bound adapter returned a completion/sample object with lane-attributable model text handed to the frozen parser; provider/transport error before such a sample stays infrastructure even with an error body; unestablishable required identity = inadmissible/missing, not a terminal); acquisition replacement unit = indivisible T0+T1 of one (block, universe, family), one linked replacement from a fresh namespace, restart at T0, second failure ⇒ missing acquisition evidence / NOT-EVALUABLE / INCONCLUSIVE (spec §5) |
| FR-10 | ACCEPT-AS-AMENDED | Evidence row corrected (ship:false; hidden_tests_passed and checker verdict/rc null; run_manifest_hash null; evidence_hash = terminal_record_sha256, retained explicitly; model_calls 1; retries 0; terminal_class MODEL-OUTPUT-INVALID as estimand evidence); capability_available derived from the frozen cell/validated lock while selection/load/invocation/consumption/material contribution stay false; T2/T3 terminal is a non-SHIP correctness failure, a treatment T4 terminal is never a specificity rejection (spec §4.1) |
| FR-11 | ACCEPT-AS-AMENDED | Epoch 2 remains STOPPED / INCOMPLETE (not "closed"); no new epoch-2 state write; stop record reworded to the frozen index-63/index-64 sentence; "epoch-closure annex" renamed "epoch-stop annex" (`EPOCH-2-STOP-RECORD.md`) |
| FR-12 | ACCEPT-AS-AMENDED, IMPLEMENTATION AUTHORIZATION DEFERRED until the corrected bytes are frozen | Twelve required adversarial probes plus full battery, V1/V2/V3 `0/0/0`, transition/lock certification, and post-FINAL refusal proofs; no epoch-3 model call before both epoch-3 locks are FINAL (spec §7) |
| FR-13 | ACCEPT-AS-AMENDED | New root files / epoch-3 lock names join V1 META so they are not mistaken for frozen task-instance bytes; the V2/protocol-governed set extends to the existing seven files + `EPOCH-3-PROTOCOL-SPEC.md` (META must not exempt the spec from the epoch-3 protocol lock); `FREEZE-REQUEST.md` stays historical META; the preflight amendment is a post-freeze implementation item (spec §7 step 2) |

Freeze status after this correction: NOT FROZEN; implementation remains
unauthorized. The expected next ruling on these corrected bytes is
`EPOCH-3-SPEC-FROZEN — IMPLEMENTATION AUTHORIZED`; if issued, the spec bytes
become the frozen protocol text (recorded in the epoch-3 protocol lock's
governed map per FR-13) and `EPOCH-3-TRANSITION.json` cites the frozen spec
sha and its freeze commit (FR-7).

---

## FR-1 — Terminal name and schema

**Disposition (2026-09-17): ACCEPT-AS-AMENDED.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §1 (proposal wording below is superseded where it differs).

**Decision needed.** Is `MODEL-OUTPUT-INVALID.json` with schema
`famc-model-output-invalid-v1` (EPOCH-3-PROTOCOL-SPEC.md §1, field list and
per-field semantics) the frozen no-arrival terminal?

**Proposed text.** Adopt §1 verbatim: terminal file
`MODEL-OUTPUT-INVALID.json`, written into the cell's DERIVED run dir
(`state/epoch3/<block>/<universe>/<family>/runs/<cell_id>/`), one per cell,
write-once, schema id `famc-model-output-invalid-v1`, exact required field
set, `experimental_outcome: true`, `contract_error` restricted to the
eligible named contract errors of §1, all hashes re-derivable from bytes on
disk (`request_body_sha256` read back from the receipt file,
`response_text_sha256` over a preserved per-attempt response file,
`usage_receipt_sha256` over `call-<id>.json`, `identity_record_sha256` over
`identity.json`).

**Alternatives considered.** (a) `NO-ARRIVAL.json` — rejected: names the
absence, not the cause, and would invite "no signal" readings the ruling
rejected. (b) A field inside `H1-RUN-MANIFEST.json` — rejected: a manifest
implies an executable artifact and a verdict path that does not exist here.
(c) Folding the case into the existing `INADMISSIBLE` status — rejected:
INADMISSIBLE is a validation verdict over existing artifacts, not a
first-class experimental outcome, and it never progresses.

**Consequence.** A lawful, immutable, progress-valid representation of
"provider call + returned bytes + contract denial + no arrival". Without it,
epoch 3 repeats epoch 2's stopping condition.

## FR-2 — Terminal status token and progress algebra

**Disposition (2026-09-17): ACCEPT-AS-AMENDED.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §3 (and §3.1).

**Decision needed.** Is `terminal_status: "COMPLETE-FAILURE"` the status token
that the walk treats as progress-valid for model cells, with the T0 algebra
of §3?

**Proposed text.** §3 verbatim: model cells progress on validated `COMPLETE`
or validated `COMPLETE-FAILURE`; `INCOMPLETE`/`INADMISSIBLE` never progress;
`PROMOTION` COMPLETE|NOT-PROMOTED, `CAPABILITY_LOCK` COMPLETE|NOT-LOCKED,
downstream NOT-EVALUABLE (all unchanged). T0 failure algebra: candidate
absent → T1 NOT-EVALUABLE (acquisition-failed) → PROMOTION NOT-PROMOTED →
CAPABILITY_LOCK NOT-LOCKED → T2/T3/T4 NOT-EVALUABLE (acquisition-failed) →
prefix continues. The terminal authorizes nothing (no lock, no reuse, no
retry, no verdict) and is never converted to COMPLETE or pooled with
ship/fix.

**Alternatives considered.** (a) Reuse `status: "COMPLETE"` plus an
`outcome` field — rejected: converts a failure into the same token as a
successful cell and invites `completed_cells()`-style conflation.
(b) A status named `NOT-EVALUABLE` — rejected: collides with the derived
downstream status and would hide that the cell was actually attempted and the
model actually failed. (c) `MODEL-OUTPUT-INVALID` as the status string —
viable; `COMPLETE-FAILURE` was chosen because the ruling says "T0 terminal
COMPLETE-as-failure" and because the token states both facts.

**Consequence.** The prefix continues lawfully past a model-output failure
without any retry, and no failure is ever reported as success.

## FR-3 — Writer site and write-once discipline

**Disposition (2026-09-17): ACCEPT-AS-AMENDED.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §2.

**Decision needed.** Is the runner's parse gate the only writer?

**Proposed text.** §2 verbatim: the terminal is written by
`benchmarks/fam-c/harness-run/run_arm_h1.py` in `main()`, at the gate at
line 3897 (`arrival, parse_mode = extract(raw)`), after
`OB.note_provider_call()` (line 3896) and with no call to
`note_cell_completed()`; the catch is narrow (eligible named contract errors
only; every other exception propagates unchanged); write-once, a second write
or a pre-existing terminal for the same cell refuses
(`MODEL-OUTPUT-INVALID-DENY`); no operator command may mint it.

**Alternatives considered.** (a) A separate post-hoc tool that mints the
terminal from the preserved run dir — rejected: it would reconstruct
evidence after the fact and let an operator decide an outcome. (b) Writing
the terminal in `main()`'s outer exception handler — rejected: too broad
(would swallow infrastructure errors and unrelated bugs).

**Consequence.** The outcome is minted at the moment the frozen contract
denies the sample, by the harness, before any adjudication; operators cannot
manufacture or suppress it.

## FR-4 — Forbidden companions and "no fabricated evidence"

**Disposition (2026-09-17): ACCEPT (unchanged).** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §1.

**Decision needed.** Is the companion rule of §1 (no `arrival.json`, no
`H1-RUN-MANIFEST.json`, no `EVIDENCE-CHAIN.jsonl`, no candidate/adapter
artifacts, no reuse ledger beside a lawful terminal) frozen, and are the
pre-call artifacts explicitly allowed?

**Proposed text.** §1 verbatim, plus the explicit allowance: `prompt.txt`,
`call-<id>.request.json`, `call-<id>.json`, `call-<id>.normalized.json`,
`identity.json`, the preserved per-attempt response file, and the attempt
ledger MAY and normally will coexist with the terminal — they are pre-call /
call-capture artifacts and prove the sample happened. They never imply an
executable artifact or a verdict. Any file implying execution
(arrival/manifest/chain/candidate/adapter/output) beside the terminal makes
the cell INADMISSIBLE and blocks the walk.

**Alternatives considered.** (a) Allow a manifest with empty verdict
fields — rejected: a manifest is the executable-artifact record and its
presence would let a reader (or a future tool) treat the cell as executed.
(b) Require the terminal alone in the run dir — rejected: destroys the call
evidence the accounting statistics depend on.

**Consequence.** `completed_cells()` cannot advance on fabricated or
half-executed evidence; attempt-level accounting keeps its raw material.

## FR-5 — Validator symmetry (the part that currently has no lawful path)

**Disposition (2026-09-17): ACCEPT-AS-AMENDED.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §3 and §3.1.

**Decision needed.** Does the freeze authorize the matching authority-side
changes: `order.progress_valid()` accepting `COMPLETE-FAILURE` for model
cells, `order._model_run_state()` validating the terminal strictly (identity,
receipt, preserved response, byte counts, no stray companions; mismatch →
INADMISSIBLE → walk blocks), and `order.acquisition_failed()` gaining a
second disjunct ("the T0 cell carries a validated `MODEL-OUTPUT-INVALID`
terminal") so a universe with NO T1 run still yields NOT-EVALUABLE and the
runner's pre-call `ACQUISITION-FAILED-DENY` refusal still fires?

**Proposed text.** Adopt all three, with the strict validator consuming the
terminal bytes directly (never presence alone) and cross-checking `cell_id` /
`cell_index` / `block` / `universe` / `family` / `task` / `lane` against the
authorized cell. Explicitly authorized as well: `promotion.advance()` must
be able to record BOTH governance terminals (NOT-PROMOTED, then NOT-LOCKED)
for an acquisition-failed universe that has no T1 chain tip — the
`PROMOTION-OUTCOME.json` / `CAPABILITY-LOCK-OUTCOME.json` schemas for that
case carry `reason: acquisition-failed`, `candidate_sha256: null`, and null
tip fields for the event that never ran, with the T0 evidence still bound.

**Alternatives considered.** (a) Require a T1 run for the algebra (i.e. run
T1 as a model call even though no candidate exists) — rejected: it would
spend a provider call to obtain a NOT-EVALUABLE, and the ruling says T1 is
NOT-EVALUABLE, not executed. (b) Let downstream cells be written directly by
an operator command — rejected: derived statuses stay derived; no operator
hand-writes NOT-EVALUABLE.

**Consequence.** Without FR-5 the terminal would be writable but powerless
(the epoch-1 deadlock shape). With it, the frozen A12d failed-acquisition
continuation rule extends to the no-candidate case without retry and without
a fabricated candidate.

## FR-6 — Attempt accounting, statistics, and per-attempt preservation

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (no diagnostic repeats in the live walk; ledger is the enumeration authority; denominator decomposition reported). Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §4.

**Decision needed.** Are the two statistics, the attempt ledger, and the
per-attempt response-text preservation rule of §4 frozen?

**Proposed text.** §4 verbatim:
`first_attempt_contract_admissibility = admissible first authorized samples /
all authorized first samples`;
`all_provider_call_contract_admissibility = admissible model responses / all
provider calls actually made`; counts sourced from the chained `model-call`
link, the validated terminal, and every `call-<id>.json` receipt on disk;
per-cell `ATTEMPT-LEDGER.jsonl` (`famc-attempt-ledger-v1`) with one row per
provider call actually made (`attempt_index`, `provider_call_id`,
`authorized_estimand_attempt`, `diagnostic_repeat`, `outcome`,
`response_text_sha256`, `response_bytes`, `usage_receipt_sha256`); response
text preserved per attempt as `raw-<call_id>.txt` so both statistics are
computable from immutable bytes. N=1; any second call is a protocol-extra
diagnostic repeat (non-estimand, never terminal-writing, never rescuing).
Prereg §16 (model invocations + retry count collected independently) and §24
(`model_calls`, `retries` per row) are cited as the pre-existing collection
requirement.

**Alternatives considered.** (a) Cell-level accounting ("eventually got an
arrival") — rejected by the ruling: it hides retries and selects on the
dependent variable. (b) Counting only chained calls — rejected: the epoch-2
precedent `state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/` carries two
receipts and one chain link, and the operational denominator is "all provider
calls actually made".

**Consequence.** Both statistics are computable, retries are visible, and no
future successful re-sample can be reported as one successful cell.
Recorded gap this closes: in the same epoch-2 precedent the first call's
response text was not preserved per attempt, so its admissibility is not
derivable from preserved bytes; epoch 3 must not reproduce that loss.

## FR-7 — Epoch-3 lineage mechanics (fresh locks, citing what)

**Disposition (2026-09-17): ACCEPT-AS-AMENDED.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §6.

**Decision needed.** Is the epoch-3 lineage record `EPOCH-3-TRANSITION.json`
with §6's citations the frozen mechanism, and does the freeze authorize the
matching epoch machinery extension (`harness/epoch.py` is epoch-2-specific
today: `EPOCH_ID`, `STATE_SUBDIR`, `TRANSITION_FILE`, lock filenames and the
cited epoch-1 constants are literals)?

**Proposed text.** §6 verbatim: the transition record cites the epoch-2 stop
record's own bytes (`EPOCH-2-STOP-RECORD.md` sha256
`7c076ee23e246d06ac6ab21f0e3644b5a4a91e295edf39f9b8c47af5ea8a3881`), the
epoch-2 FINAL lock hashes (`EXECUTION-LOCK-EPOCH2.json` `e662463e…`,
`PROTOCOL-LOCK-EPOCH2.json` `978d5e3e…`), the epoch-2 transition record
sha256 `047aef2f…`, the epoch-2 finalization commit `53e72ef4…`, and the
epoch-3 state prefix `state/epoch3`; fresh locks
`EXECUTION-LOCK-EPOCH3.json` / `PROTOCOL-LOCK-EPOCH3.json` (`epoch: 3`, own
append-only lineage starting `[]`, minted open, finalized only by the owner
under the standard A16 flow); epoch-1 and epoch-2 FINAL locks remain
untouched historical records; `state/epoch3/` is the only namespace epoch-3
walks may read or write.

**Alternatives considered.** (a) Reuse `EPOCH-2-TRANSITION.json` by adding a
field — rejected: the epoch-2 boundary is frozen and cited by the epoch-2
locks; mutating it breaks both. (b) Parameterize epoch machinery into a
generic `epochs.json` — viable and cleaner long-term; deferred as an
implementation choice, not a protocol choice (the freeze should authorize the
mechanism, not the refactor shape).

**Consequence.** The epoch-3 boundary is anchored to epoch 2's recorded FINAL
bytes, so a drifted epoch-2 tree refuses the transition; and the epoch-3
locks cannot inherit or amend the epoch-2 lineage.

## FR-8 — Restart from event 0, no splicing

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (PILOT-GRADE wording correction, PREREG §18.1). Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §6.

**Decision needed.** Is the restart rule frozen (epoch 3 walks the frozen
240-event order from ORDER-EXPANSION cell index 0, `9907c5cb038c02e0`), with
epoch 2 preserved as a stopped/incomplete epoch whose cells populate no
epoch-3 prefix position?

**Proposed text.** §6 verbatim: no splicing of the epoch-3 algebra into the
epoch-2 prefix; the epoch-2 prefix is reported only as stopped-prefix
evidence; `EPOCH-2-STOP-RECORD.md` creates no terminal and must not cause
`completed_cells()` to advance; epoch-2 artifacts are immutable historical
evidence (archive-don't-carry-forward, as for epoch 1).

**Alternatives considered.** (a) Resume the epoch-2 walk at cell 64 — the
ruling's explicit prohibition (semantics created after observing the
outcome), and it would leave the 0–63 segment under a different algebra than
64+. (b) Resume but re-report cells 0–63 as epoch-3 data — rejected: epoch-2
cells were executed under epoch-2's frozen semantics and cannot be
re-derived under epoch 3.

**Consequence.** One clean, homogeneous 240-event claim-grade series under
epoch-3 semantics, at the cost of repeating the executed prefix.

## FR-9 — Infrastructure boundary (restated) and replacement granularity

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (MODEL SAMPLE EXISTS boundary; acquisition replacement unit = indivisible T0+T1). Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §5.

**Decision needed.** Is §5's mechanical boundary — response body exists ⇒
experimental outcome, no response body (503-class, task receipt/execution
prevented) ⇒ infrastructure with exactly ONE whole-pair replacement, second
failure ⇒ INCONCLUSIVE — frozen, and is the replacement unit the *pair*
(as frozen in prereg), not the cell?

**Proposed text.** §5 verbatim, plus: the replacement unit is the frozen
paired comparison (prereg §19 taxonomy). A replacement is lawful only when no
response body existed for the failed member; it is recorded as a linked
replacement, the original is preserved, and no replacement is ever run for a
contract denial, malformed output, bad generated code, rc1 solver failure, or
failed candidate validation. The eight epoch-2 rc1 acquisition artifacts and
every epoch-2 terminal stay experimental failures.

**Alternatives considered.** (a) Cell-level replacement — rejected: pairing
is the frozen design and cell-level replacement would silently break the
paired comparison. (b) Treating "no arrival" as no-signal — rejected by the
ruling: the signal is the denial chain.

**Consequence.** Infrastructure stays narrowly defined; every observed
failure in epoch 2 keeps its classification; the epoch-2 lane pattern (all
seven candidate validations failed, all roll-up verdicts blocked/fix) remains
reportable as an experimental finding rather than an invalidation.

## FR-10 — Terminal-cell reporting: exit code, evidence row, admissibility

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (exit code 0 kept; evidence row corrected). Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §4.1.

**Decision needed.** Three small mechanical choices for a terminal cell:
(1) runner exit code; (2) its prereg §24 evidence-table row; (3) its
admissibility classification.

**Proposed text.**
(1) Exit code 0 when the terminal is written (the cell completed as a
recorded experimental outcome, exactly as a committed failed candidate
validation exits 0 today); non-zero is reserved for infrastructure/refusal
paths.
(2) Its §24 row carries the cell identity, lane, producer/consumer ids,
`model_calls: 1`, `retries: 0`, usage from the receipt, and
`ship: null`, `hidden_tests_passed: null`, `capability_*: false`,
`run_manifest_hash: null`, plus a `terminal_record_sha256` field naming the
terminal — never a fabricated verdict.
(3) It is estimand-grade evidence (it is an observed model failure), but it
is not a harness-validation run and must not be classified ELIGIBLE as a
successful cell; the admissibility classifier gains a named terminal class
(`MODEL-OUTPUT-INVALID`) so tallies can count it separately.

**Alternatives considered.** (a) Exit non-zero to flag the failure —
rejected: the run is a recorded outcome, not an error, and epoch-2 already
exits 0 for committed failed validation. (b) Exclude the cell from the
evidence table — rejected: it is estimand-relevant lane-reliability evidence
and the ruling requires attempt-level counting.

**Consequence.** Terminal cells are visible, counted, and never silently
upgraded or omitted.

## FR-11 — Epoch-2 stop visibility (no state writes)

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (STOPPED/INCOMPLETE, not "closed"; frozen index-63/index-64 sentence; "epoch-stop annex"). Normative text: `EPOCH-2-STOP-RECORD.md`.

**Decision needed.** Is the epoch-2 stop mechanism sufficient as: the
`EPOCH-2-STOP-RECORD.md` bytes, the `INCIDENT.json` under
`state/epoch2/_operator-errors/`, the status addendum in
`FAMC-EXECUTION-STATUS.md`, and the epoch-3 transition record citing the stop
record's sha256 — with NO write anywhere under `state/`?

**Proposed text.** Adopt exactly that. The preserved attempts and
`INCIDENT.json` remain byte-for-byte, untracked, read-only evidence; no
`EPOCH-2-CLOSURE.json` or similar is written into the state tree; the epoch
boundary is proven by the transition record's citation of the stop record
bytes (the same anchoring epoch 2 used for the epoch-1 closure record).

**Alternatives considered.** (a) A machine-readable closure file inside
`state/epoch2/` — rejected for this slice: the state tree is evidence and the
slice is docs-only; if the seat prefers a machine-readable anchor, it should
name the file, schema, and writer (and it becomes an implementation item).
(b) No stop record at all, only the status doc — rejected: the epoch-3
transition needs frozen bytes to cite.

**Consequence.** Epoch 2 is provably stopped without mutating any epoch-2
evidence; epoch 3's boundary is verifiable against an immutable document.

## FR-12 — Implementation authorization and certification

**Disposition (2026-09-17): ACCEPT-AS-AMENDED; IMPLEMENTATION AUTHORIZATION DEFERRED until the corrected spec bytes are frozen.** Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §7 (twelve required adversarial probes + certification standard).

**Decision needed.** Does the freeze authorize the implementation set
(terminal writer in `run_arm_h1.py`; strict validator, `progress_valid`
extension, `acquisition_failed` extension in `harness/order.py`;
`promotion.advance()` no-T1 governance terminals in `harness/promotion.py`;
attempt ledger + per-attempt response preservation; epoch-3 machinery in
`harness/epoch.py` / `harness/epoch_transition.py` / lock minting; tests),
under the A12.1/A16 amendment discipline, with certification equal to
epoch 2's (full smoke battery at the frozen ref, preflight 0/0/0, adversarial
probes for the new terminal, post-FINAL refusal proofs)?

**Proposed text.** Yes, with: (a) a named harness-delta list in the epoch-3
protocol lock; (b) adversarial tests for at least — tampered terminal bytes,
stray `arrival.json` beside a terminal, foreign cell id/lane, duplicate
write, receipt-hash mismatch, missing preserved response, a terminal cell
that falsely claims a chain link, and a walk that must NOT advance on a
tampered terminal; (c) certification results recorded in
`FAMC-EXECUTION-STATUS.md` before the epoch-3 walk starts; (d) no epoch-3
model call before both epoch-3 locks are FINAL.

**Alternatives considered.** (a) Implement first, freeze after — rejected:
the whole point of the ruling is that the terminal is PRE-frozen. (b) Freeze
the spec but let certification differ from epoch 2's standard — rejected: a
new terminal type changes the progress algebra, which is exactly what
certification exists to prove.

**Consequence.** The epoch-3 terminal is frozen before it is used, and its
implementation is certified rather than asserted.

## FR-13 — Certification wiring for the new root-level protocol docs

**Disposition (2026-09-17): ACCEPT-AS-AMENDED** (V1 META additions; V2/governed set = seven files + `EPOCH-3-PROTOCOL-SPEC.md`; `FREEZE-REQUEST.md` stays historical META; preflight amendment is a post-freeze implementation item). Normative text: `EPOCH-3-PROTOCOL-SPEC.md` §7 step 2.

**Decision needed.** The three new documents and the future
`EPOCH-3-TRANSITION.json` sit at the Fam-C root, where preflight's V1
INSTANCE-FREEZE walk (`preflight.py:validate_instance`) flags every tracked
file that is not in `META`, not in `PROTOCOL_GOVERNED`, and not in the frozen
manifest. Adding these docs therefore creates named `V1 INSTANCE-FREEZE:
extra file not in freeze manifest` findings until `preflight.py`'s `META` set
is amended (the same acceptance the epoch-2 slice added for
`EPOCH-1-CLOSURE.md` and the epoch-2 lineage files). `preflight.py` is
protocol-governed, so this slice cannot touch it (docs-only; no harness
bytes, no lock edits). Decision: does the freeze authorize, as part of the
epoch-3 implementation delta, the `META` additions
`EPOCH-2-STOP-RECORD.md`, `EPOCH-3-PROTOCOL-SPEC.md`, `FREEZE-REQUEST.md`,
`EPOCH-3-TRANSITION.json` (and the epoch-3 lock filenames), listed as a
protocol-lock forward amendment and certified green before the epoch-3 walk?

**Proposed text.** Yes — amend `META` exactly as epoch 2 did, with the
addition listed in the epoch-3 protocol lock's amendment lineage; until then
the three docs knowingly sit as V1 extras in this docs-only slice, which is
recorded rather than hidden.

**Alternatives considered.** (a) Place the docs under an operational dir
(`harness-run/`, which the V1 walk prunes) — rejected: the campaign's
convention puts closure/spec records at the Fam-C root, and burying protocol
text in a code dir harms auditability. (b) Place them under `state/` (also
not walked) — rejected: state is evidence, not protocol. (c) Amend preflight
in this slice — forbidden (docs-only slice; `preflight.py` is
protocol-governed and its bytes are lock-enforced).

**Consequence.** Certification stays honest: the extras are visible as named
findings until the amendment lands, and no one silently weakens the freeze
manifest to accommodate new documents.

---

## Conflicts and ambiguities recorded (no improvisation)

1. **Frozen-artifact tension (A12d vs the ruling's T0 algebra).** The frozen
   failed-acquisition predicate `acquisition_failed()`
   (`harness/order.py:1943`) requires the T1 chain to carry exactly one
   `candidate-validation` link with `validated: false`, and requires both T0
   and T1 validated COMPLETE, before a universe may be NOT-EVALUABLE. The
   ruling's no-candidate algebra has no T1 run at all. FR-5 is the resolution
   surface; until the seat rules, the two rules cannot both hold for a
   T0-model-output-invalid universe.
2. **Pair-replacement granularity.** The prereg replacement rule is written
   for paired comparisons; the epoch-2/3 acquisition cells are not yet paired
   within a pair-execution. FR-9 asks the seat to confirm that the
   replacement unit is the pair (and by what pairing rule for acquisition
   cells), since a T0 sample that never existed is exactly the case where
   "replace the pair" is ambiguous.
3. **Evidence-table row shape for a terminal.** `PREREG.md` §24 requires one
   row per run with `ship`, `hidden_tests_passed`, `run_manifest_hash`, and
   retry fields; a terminal cell has no verdict and no manifest. FR-10(2)
   proposes null-valued verdict fields plus `terminal_record_sha256`; this is
   a reading of §24, not a change to it, and should be ratified or amended.
4. **Diagnostic-repeat artifacts.** A pre-declared diagnostic repeat (if ever
   authorized) writes a second set of call artifacts. §4 puts them in the
   same cell run dir with ledger rows; the alternative (a sibling
   `_diagnostic/` dir) is unrecorded evidence-wise and should be chosen or
   rejected explicitly. Epoch 2's precedent kept both receipts in one dir
   (FR-6), with no ledger.
5. **Preserved-but-unclassified epoch-2 call.** The `dda8f5746cfaa800` call
   in `state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/` has no recorded
   classification and no preserved response text. This request does not ask
   the seat to classify it retroactively (epoch 2 is stopped); it is listed
   so the accounting rules are built on the record as it actually is, not as
   it was assumed to be.
6. **Certification-path conflict (docs vs preflight V1).** Root-level protocol
   docs are V1 INSTANCE-FREEZE extras until `META` is amended; this slice is
   docs-only and may not amend `preflight.py`. See FR-13. The three documents
   are shipped anyway (the deliverable names them at the Fam-C root), and the
   expected named findings are recorded here rather than engineered away.
7. **Epoch-2 stop record is an annex, not a closure ruling.** Unlike epoch 1
   (which was closed by a ruling), epoch 2 is stopped by the parse-denial
   ruling. If the seat wants an explicit "epoch 2 CLOSED" formulation
   (beyond "stopped/incomplete"), it should supply the operative sentence for
   `EPOCH-2-STOP-RECORD.md`; this draft uses the ruling's own words.

# Fam-C Pilot Execution Status — QUARANTINED / NOT GRADABLE

Date: 2026-09-08. This is a status boundary, not a result claim.

## Why execution is paused

The partial P/Q runs committed under this branch were launched by the
ad-hoc `harness-run/run_arm.py` helper, which called the provider endpoints
directly and did **not** yet execute model steps through the sealed H1
DockerSandbox boundary (`harness/dockersandbox.py`). H1 itself is sealed
and its 33/33 smoke is green, but the Fam-C runner has not integrated it.
Therefore these runs are preserved as evidence but are **not gradable Fam-C
estimand data**: do not use their success, cost, or reuse outcomes in a
headline.

## Preserved evidence

All existing `runs/` artifacts remain committed and untouched. They include
raw responses, prompts for later runner revisions, lane records, usage blocks,
solver arrivals, mechanical checker outcomes, and capability locks where a
capability was created. The branch history carries partial fam01/fam02/fam03/
fam04/fam05/fam06 work; malformed arrivals and model failures are retained,
not retried into a prettier record.

A direct tally currently contains partial records for 5 families; it is an
inventory only. Fam02 and Fam06 capability promotion attempts already
returned `fix` (the generated capability did not satisfy the frozen checker
contract), so no correct-arm lock exists for those families. This is an
experimental outcome, not an infrastructure invalidation.

## Run classification (Round-1 audit P0 #1) — H1 runs are HARNESS-VALIDATION

`harness/admissibility.py` classifies every `runs/` dir (read-only, no
relabeling): **H1-* runs are EXCLUDED as harness-validation** — they prove the
harness works end-to-end, they are never estimand data. The admissibility
command returns, for the current `runs/` inventory, `estimand-grade = 0`:
every dir is EXCLUDED (the two H1-* dirs as harness-validation; all legacy
`P-*`/`Q-*` dirs as pre-harness ad-hoc evidence with no run manifest), because
no dir satisfies the estimand evidence gate (provider-side `identity.json`,
instance-freeze anchor `== FREEZE.json freeze_commit`, wired run manifest,
intact `EVIDENCE-CHAIN.jsonl`). For the paper: these dirs are **PILOT-GRADE
harness-validation evidence only** — cite them for what they prove about the
harness, never in an estimand headline; claim-grade estimand results require
fresh replication on unseen families behind the EXECUTION-LOCK after the
Round-2 audit closes.

## Lane/failover boundary

The P/Q direct probes used the frozen P/Q endpoints in their lane records at
the time of the calls, but a separate model failover warning appeared in the
session. Any call whose provider/model identity cannot be established from
its committed lane/usage receipt is excluded from future tallies under the
frozen invalid-run taxonomy. No relabeling by behavior is allowed.

## Required next implementation before resuming

- DONE: H1-integrated runner `harness-run/run_arm_h1.py` now stages work under
  the trusted root (`/tmp/rcos-runs/famc-<id>`), mounts `/work:rw`+`/task:ro`,
  executes arrivals inside `--network none` digest-pinned containers, and
  copies OUTPUT back for host-side evaluation. Model calls stay harness-side.
  First validation run `H1-P-fam01-T0` = ship (json-envelope, container rc0).
- P/Q lane identity re-probed live and confirmed distinct: P=`MiniMax-M3`
  (router9/v1), Q=`agnes-2-0-flash:free` (kenari.id/v1). Both reachable.
- DONE: H2/H3 wiring attached to `run_arm_h1.py` (wired by default; Round-1
  audit P0 #19: unwired execution is REFUSED on the estimand surface —
  `--no-wire` is banned; the only unwired escape is `--dev-unwired-outdir DIR`
  outside the Fam-C tree, stamped `dev_mode=true` in the manifest). Every
  model call passes through `usage.recorded_call()` (usage receipts land in
  the run dir); every completed run emits `EVIDENCE-CHAIN.jsonl` (genesis
  binds the **instance freeze commit from `FREEZE.json`
  (`d1292434…`) — never an execution HEAD masquerading as the freeze** — +
  run manifest → model-call → capability-event → evaluator → terminal grade)
  and re-audits clean before returning. Dual anchors (Round-1 audit P0 #4):
  each manifest records `instance_freeze_commit`/`instance_freeze_tree`
  (FREEZE.json) alongside `execution_harness_commit` (git HEAD at run time)
  and `execution_harness_manifest_sha256` (sha over the executed harness
  modules + runner), and the runner refuses to START unless the executed
  instance subtree is byte-identical to `FREEZE-HASHES.sha256`
  (`verify_instance_frozen`, fail-closed on drift/extras). Correct-arm loads
  go through `lock.load_artifact()` (locked-hash verified pre-execution) and
  every wired run writes a decision-driven `reuse_log` record; promotion is
  the sole route of the A12.1 order-authorized promotion controller
  (`harness/promotion.py`) — the runner's legacy `--promote` flag is retired
  by a hard refusal. Offline wiring compose-check:
  `run_arm_h1.py --selfcheck-wire` = ok (fixture, not a run).
- First frozen-order wired run: `H1-P-fam05-T0` = ship (json-envelope,
  container rc0; manifest verdict `ship`; chain audit intact).
  `H1-Q-fam05-T0` blocked externally: kenari free-model daily quota exhausted
  (`429 free_quota_daily`, resets 00:00 UTC) — endpoint reachable, lane has no
  completions budget today. Correct-arm CAPABILITY_LOCK/ledger path is
  implemented + offline-proven but has no real locked capability yet (prior
  fam02/fam06 promotion attempts returned `fix`), so no correct-arm run is
  claim-grade until a real lock exists.
- REMAINING (to resume): re-run the frozen sequence from the next family cell
  (new runs only via `run_arm_h1.py`; prior ad-hoc runs stay quarantined);
  retry lane Q after the kenari daily-quota reset (00:00 UTC).

## Verdict

`IN-PROGRESS — estimand lock proven on lane P`: new runs emit H2+H3-linked
manifests and audit-intact chains through `run_arm_h1.py` (validated on
`H1-P-fam05-T0` = ship — harness-validation, not estimand data); lane Q of
that cell is externally blocked by the provider's free-model daily quota, not
by the harness. Correct-arm capability runs await a real locked capability
from a successful promotion. Status wording (Round-1 audit correction #2):
locked capability reuse is **promotion + locked reuse under workflow
control**, never "retirement" — a promoted capability remains reusable by
correct-arm runs exactly as `lock.load_artifact()` enforces. The frozen
instance package is unaffected; execution stays STOPPED for estimand-grade
runs (admissibility: `estimand-grade = 0`) until the Round-2 audit closes and
the EXECUTION-LOCK is applied.

## Round-3 audit close (A11) — 2026-09-08

The round-3 auditor returned `permission for real Fam-C execution: NO` and a
six-item A11 work order; A11.1–A11.6 are implemented and locally verified
(no real P/Q call, no network in this slice):

- A11.1 the calibration live branch returns and persists the provider
  response object (identity is established from the real call, not a stub);
- A11.2 the exact request bytes are persisted per call and adapter binding
  (a v2 id IS a lane binding) + request binding are enforced before the
  identity gate; mutating temperature/max_tokens/model/messages in any
  representation fails verification;
- A11.3 H6 symmetry is now a byte-identity proof
  (`strip_capability_block(treatment) == control`) — the legacy fixture that
  asserted the weaker rule was DELETED, not supplemented;
- A11.4 the frozen order expands over the FULL event universe
  (`T0, T1, PROMOTION, CAPABILITY_LOCK` for A, then for C, then
  `T2/T3/T4` × A/B/C/D — 240 events, 192 model calls), so downstream cells
  can no longer precede the acquisition/promotion of their own capability;
- A11.5 each estimand cell's capability registry and run directory are
  DERIVED from the authorized cell (`state/<block>/<universe>/<family>/…`);
  a C run can no longer be pointed at A's registry;
- A11.6 order progress consumes validated `cell_state()` (manifest + cell
  identity + evidence chain + admissibility), not manifest presence.

Verification for this slice: preflight V1/V2/V3 = 0/0/0 findings; harness
smokes 342/342 closed (graph 12, H1 12, H1-docker 33, H2 33, H3 59, H4 30,
H5 15, H6 33, H7 67, H8 48), `calibrate --offline` 2/2 lanes green, runner
`--selfcheck-prompt` and `--selfcheck-wire` green. `estimand-grade = 0` is
UNCHANGED: the real P/Q calibration pair is still time-gated (Q free-tier
quota resets 00:00 UTC) and no estimand cell has been run. Execution stays
STOPPED for estimand-grade runs pending the auditor's next review.

## Round-3b audit close (A11b) — 2026-09-08

The round-3b review returned six P0 implementation findings + one wording
defect (P0-1…P0-6, P1). All are closed in production code, verified offline
(no real P/Q call, no network in this slice):

- P0-1 request binding: the exact request BYTES are staged, persisted and
  hashed BEFORE the POST; the digest is bound into the chain link and
  re-read from disk by `verify_request_binding()`, so a mutated
  temperature/max_tokens/model/messages in ANY representation fails;
- P0-2 common output contract: ONE arm-independent contract
  `{"decision": use_capability|fresh, "execution_payload", "notes"}` with a
  named fail-closed validator and a single arm-independent `extract()`;
- P0-3 production manifest: `cell_state()` requires EXACT equality over the
  13 production manifest fields, a REAL `verify_chain()` (the smoke's stub
  chain injection was deleted) and admissibility ELIGIBLE;
- P0-4 governance cells: `cell_state()` dispatches by cell kind —
  model-run cells need manifest+chain+admissibility, PROMOTION cells need
  the receipt plus both acquisition chain tips re-derived on disk, and
  CAPABILITY_LOCK cells need the lock bound to the promotion receipt hash;
  governance cells need no fabricated model-run manifest;
- P0-5 (protocol, open): the A→C acquisition order is pinned as protocol by
  the exact ORDER-EXPANSION.json SHA256 in PROTOCOL-LOCK at PROTOCOL FINAL;
- P0-6 namespace ancestry: every component from `state/` downward is
  lstat-verified (directory, not symlink, harness-owned, not group/world
  writable) on the WRITE path and re-verified on the READ path
  (`cell_state`), and the harness now creates its own tree component-wise at
  0755 via `ensure_namespace()` so umask 002 cannot leave 0775
  intermediates that the rule refuses;
- P1 accounting wording: `primary_work = uncached_input + output_tokens` —
  input tokens are NOT inherently uncached; only the cached fraction is,
  and it is recorded separately and never merged or relabeled.

Verification for this slice: three-authority preflight V1 0 / V2 0 / V3 0
(EXECUTION-LOCK re-minted as a listed amendment over the five changed
modules; PROTOCOL-LOCK amended for these doc bytes); harness smokes
448/448 closed (graph 12, H1 12, H1-docker 33, H2 33, H3 59, H4 30, H5 15,
H6 33, H7 67, H8 48, H9 18, H10 20, H11 24, H12 44); both runner selfchecks
green; `calibrate --offline` 2/2 lanes green; general-seat independent
falsification probe 23/23. `estimand-grade = 0` is UNCHANGED — the only wired
manifest in the tree is the H1-P-fam05-T0 harness-validation fixture (harness
validation, never estimand data). The real P/Q calibration pair remains
time-gated (Q free-tier quota resets 00:00 UTC). Execution stays STOPPED for
estimand-grade runs pending the auditor's next review.

## Round-3b audit close (A11b) — 2026-09-08

The round-3b review returned six P0 implementation findings + one wording
defect (P0-1…P0-6, P1). All are closed in production code, verified offline
(no real P/Q call, no network in this slice):

- P0-1 request binding: the exact request BYTES are staged, persisted and
  hashed BEFORE the POST; the digest is bound into the chain link and
  re-read from disk by `verify_request_binding()`, so a mutated
  temperature/max_tokens/model/messages in ANY representation fails;
- P0-2 common output contract: ONE arm-independent contract
  `{"decision": use_capability|fresh, "execution_payload", "notes"}` with a
  named fail-closed validator and a single arm-independent `extract()`;
- P0-3 production manifest: `cell_state()` requires EXACT equality over the
  13 production manifest fields, a REAL `verify_chain()` (the smoke's stub
  chain injection was deleted) and admissibility ELIGIBLE;
- P0-4 governance cells: `cell_state()` dispatches by cell kind —
  model-run cells need manifest+chain+admissibility, PROMOTION cells need
  the receipt plus both acquisition chain tips re-derived on disk, and
  CAPABILITY_LOCK cells need the lock bound to the promotion receipt hash;
  governance cells need no fabricated model-run manifest;
- P0-5 (protocol, open): the A→C acquisition order is pinned as protocol by
  the exact ORDER-EXPANSION.json SHA256 in PROTOCOL-LOCK at PROTOCOL FINAL;
- P0-6 namespace ancestry: every component from `state/` downward is
  lstat-verified (directory, not symlink, harness-owned, not group/world
  writable) on the WRITE path and re-verified on the READ path
  (`cell_state`), and the harness now creates its own tree component-wise at
  0755 via `ensure_namespace()` so umask 002 cannot leave 0775
  intermediates that the rule refuses;
- P1 accounting wording: `primary_work = uncached_input + output_tokens` —
  input tokens are NOT inherently uncached; only the cached fraction is,
  and it is recorded separately and never merged or relabeled.

Verification for this slice: three-authority preflight V1 0 / V2 0 / V3 0
(EXECUTION-LOCK re-minted as a listed amendment over the five changed
modules; PROTOCOL-LOCK amended for these doc bytes); harness smokes
448/448 closed (graph 12, H1 12, H1-docker 33, H2 33, H3 59, H4 30, H5 15,
H6 33, H7 67, H8 48, H9 18, H10 20, H11 24, H12 44); both runner selfchecks
green; `calibrate --offline` 2/2 lanes green; general-seat independent
falsification probe 23/23. `estimand-grade = 0` is UNCHANGED — the only wired
manifest in the tree is the H1-P-fam05-T0 harness-validation fixture (harness
validation, never estimand data). The real P/Q calibration pair remains
time-gated (Q free-tier quota resets 00:00 UTC). Execution stays STOPPED for
estimand-grade runs pending the auditor's next review.

## Round-2 audit close (A12) — 2026-09-08

The round-2 review accepted the request/identity binding, the prompt byte
symmetry, the single parser/runtime primitive and the namespace isolation
under the TCB, and returned three implementation units plus one shared
contract defect. All are closed in production code, verified offline (no
provider call, no estimand cell):

- A12.1 promotion controller (`harness/promotion.py`): the sole route that
  may mint a capability lock. It takes an AUTHORIZED EVENT, never an operator
  chain tip / cell id / output directory; it derives the candidate from this
  universe's own T0 arrival payload, requires T1 to declare and use the same
  candidate sha256, names exactly the three capability artifacts in the
  promotion receipt, and refuses out-of-order governance
  (ACQUISITION-REQUIRED / PROMOTION-DENY);
- A12.2 estimand-aware CAPABILITY_LOCK (`capability-lock-v2`): artifact
  provenance, semantic_core, preconditions, limitations, auditor T4 semantic
  id, promotion/evidence hashes and the producer/acquisition bindings are
  required fields; `verify_lock()` is the single validator; a pre-A12 lock is
  LOCK-INADMISSIBLE; an estimand-grade lock without a ratified T4 id is
  refused; consuming an estimand-grade lock without declaring estimand grade
  is inadmissible;
- A12.3 USE/REJECT/fresh: the arrival decision drives the reuse ledger in
  every wired case (use_capability → selected/loaded/invoked/consumed; fresh
  with a capability available → reuse_rejected with the arrival's recorded
  reason; fresh with none → capability_available false), the T4 rejection
  path is a legal COMPLETE outcome, and the legacy runner `--promote` flag is
  retired by a hard refusal;
- shared output contract: one neutral line, byte-identical in both arms —
  choose use_capability only when a capability-access block is present and
  applicable; otherwise choose fresh.

Also closed in this slice: the production acquisition executor (the
experiment is no longer mechanically deadlocked at cell 0), the production
`main()` undefined-name defect, genesis-link verification, and the
execution-order leakage in `cell_state()`.

Integration hardening found by our own probes while landing the above (each
had a failing probe before the fix, all in production code):

- `emit_capability_lock()` re-runs the full A12.1 provenance gate on the
  receipt before minting — a receipt forged for this cell plus artifact bytes
  copied in from another universe (hash-matching, so the artifact check alone
  cannot tell) previously minted a lock;
- `t4_ratified` is DERIVED from the frozen `T4-SEMANTIC-IDS.json`, so flipping
  the boolean on an unratified id no longer upgrades a receipt;
- presence is not truthiness: a frozen contract may declare no limitations
  (fam05's `K.md` does not), so an empty list is a real value while the
  content-bearing provenance fields stay required;
- `semantic_core` preserves the contract's own line structure, because the
  validator requires it verbatim in the frozen `K.md`;
- V3 closes over the WHOLE `harness/` package root, not just the runner's
  import graph — `harness/promotion.py` mints locks, so it must sit inside the
  execution authority;
- `harness/tests/fixture_modelrun.py` builds a genuinely ELIGIBLE hermetic run
  through the real writers only; a fixture the production classifier rejects
  cannot prove anything about the production classifier.

## Non-production entry points (never estimand evidence)

`harness-run/run_arm.py` and `harness-run/p_call.py` are DEVELOPMENT ESCAPES
from the pre-A11 harness: they call a lane without the wired evidence path
(no order authorization, no chain, no identity/normalized-usage binding, and
`p_call.py` still names the superseded `openai-chat-total-input-v1`
normalizer). They are not production entry points and can never produce
estimand evidence. The only production execution entry point is
`harness-run/run_arm_h1.py` with `--block`, the scheduler-derived wired paths,
and the frozen-order cell authorization.

## Round-3 audit close (A11) — 2026-09-08

The round-3 auditor returned `permission for real Fam-C execution: NO` and a
six-item A11 work order; A11.1–A11.6 are implemented and locally verified
(no real P/Q call, no network in this slice):

- A11.1 the calibration live branch returns and persists the provider
  response object (identity is established from the real call, not a stub);
- A11.2 the exact request bytes are persisted per call and adapter binding
  (a v2 id IS a lane binding) + request binding are enforced before the
  identity gate; mutating temperature/max_tokens/model/messages in any
  representation fails verification;
- A11.3 H6 symmetry is now a byte-identity proof
  (`strip_capability_block(treatment) == control`) — the legacy fixture that
  asserted the weaker rule was DELETED, not supplemented;
- A11.4 the frozen order expands over the FULL event universe
  (`T0, T1, PROMOTION, CAPABILITY_LOCK` for A, then for C, then
  `T2/T3/T4` × A/B/C/D — 240 events, 192 model calls), so downstream cells
  can no longer precede the acquisition/promotion of their own capability;
- A11.5 each estimand cell's capability registry and run directory are
  DERIVED from the authorized cell (`state/<block>/<universe>/<family>/…`);
  a C run can no longer be pointed at A's registry;
- A11.6 order progress consumes validated `cell_state()` (manifest + cell
  identity + evidence chain + admissibility), not manifest presence.

Verification for this slice: preflight V1/V2/V3 = 0/0/0 findings; harness
smokes 342/342 closed (graph 12, H1 12, H1-docker 33, H2 33, H3 59, H4 30,
H5 15, H6 33, H7 67, H8 48), `calibrate --offline` 2/2 lanes green, runner
`--selfcheck-prompt` and `--selfcheck-wire` green. `estimand-grade = 0` is
UNCHANGED: the real P/Q calibration pair is still time-gated (Q free-tier
quota resets 00:00 UTC) and no estimand cell has been run. Execution stays
STOPPED for estimand-grade runs pending the auditor's next review.

## Round-3 audit close (A11) — 2026-09-08

The round-3 auditor returned `permission for real Fam-C execution: NO` and a
six-item A11 work order; A11.1–A11.6 are implemented and locally verified
(no real P/Q call, no network in this slice):

- A11.1 the calibration live branch returns and persists the provider
  response object (identity is established from the real call, not a stub);
- A11.2 the exact request bytes are persisted per call and adapter binding
  (a v2 id IS a lane binding) + request binding are enforced before the
  identity gate; mutating temperature/max_tokens/model/messages in any
  representation fails verification;
- A11.3 H6 symmetry is now a byte-identity proof
  (`strip_capability_block(treatment) == control`) — the legacy fixture that
  asserted the weaker rule was DELETED, not supplemented;
- A11.4 the frozen order expands over the FULL event universe
  (`T0, T1, PROMOTION, CAPABILITY_LOCK` for A, then for C, then
  `T2/T3/T4` × A/B/C/D — 240 events, 192 model calls), so downstream cells
  can no longer precede the acquisition/promotion of their own capability;
- A11.5 each estimand cell's capability registry and run directory are
  DERIVED from the authorized cell (`state/<block>/<universe>/<family>/…`);
  a C run can no longer be pointed at A's registry;
- A11.6 order progress consumes validated `cell_state()` (manifest + cell
  identity + evidence chain + admissibility), not manifest presence.

Verification for this slice: preflight V1/V2/V3 = 0/0/0 findings; harness
smokes 342/342 closed (graph 12, H1 12, H1-docker 33, H2 33, H3 59, H4 30,
H5 15, H6 33, H7 67, H8 48), `calibrate --offline` 2/2 lanes green, runner
`--selfcheck-prompt` and `--selfcheck-wire` green. `estimand-grade = 0` is
UNCHANGED: the real P/Q calibration pair is still time-gated (Q free-tier
quota resets 00:00 UTC) and no estimand cell has been run. Execution stays
STOPPED for estimand-grade runs pending the auditor's next review.

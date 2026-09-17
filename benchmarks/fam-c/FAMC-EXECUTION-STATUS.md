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


## Round-4 audit + R4-RECONCILE (A16) — 2026-09-16

An independent Round-4 seat audited the accumulated post-A11b state
(main b4ce064 + branch tip a61d104) and returned
`permission for real Fam-C execution: NO` with four P0s; the full reply is
committed as `AUDIT-ROUND4.md`. The design was NOT reopened — every roadmap
unit A11b.1–6, A12 #8–#10, A13 #11, A14 #12, A15 #13 PASS with code-level
verification; `estimand-grade = 0` was independently re-confirmed. What
failed was the landing and the record:

- P0-R4-1 (authority): main's PR-squash landing left the freeze commit
  d1292434 a non-ancestor of main and 4 V2 lineage nodes unretrievable; the
  runner refused start (fail-closed, correct). CLOSED — the execution ref is
  the reconciled branch (merge 24cd07d); preflight 0/0/0 there.
- P0-R4-3 (path resolution, root cause corrected by reconciliation): h35's
  H35b-IDENTITY failure is NOT an A13 schema break. The production runner
  hardcoded `BASE`/`HARNESS` to /home/chow/chow-work/rcos, so any real-seal
  suite bound whichever checkout sat at that path instead of the tree under
  test (the seal's recorded execution_lock_sha256 407b1a54… is byte-for-byte
  the main checkout's lock). The runner, dev escape, and suites now derive
  all repo paths from file location; h35 = 56/56.
- P0-R4-2 (verification claim): the implementers' recorded 37/37 was a FALSE
  GREEN — the battery loop captured a pipeline's exit code, never the tests'.
  True pre-reconcile numbers were 23–26/37 plus preflight RED at main.
  Recorded lesson: per-test exit codes are captured un-piped, and a green
  battery is cited only together with its ref and checkout state. Stale git
  worktree registrations were pruned; the shared fixture root
  (/tmp/rcos-runs) must be cleaned before a battery — per-suite isolated
  roots are the recommended follow-up slice.
- P0-R4-4 (record): this file and AUDIT-ROUND4.md are the committed closure
  record. The A12b–A13/Ruling-3 seat replies were not preserved by their
  sessions (acknowledged LOST); the compensating control is the independent
  Round-4 re-audit of the accumulated state. HARNESS-READINESS.md refresh is
  deferred to the PROTOCOL-FINAL slice.

State after reconciliation (branch HEAD, preflight 0/0/0): full suite 37 PASS / 0 FAIL at 10e58ce on TWO independent checkouts (the reconcile worktree and a fresh clone of the pushed r4-reconcile branch; cleaned trusted roots; per-suite 240s cap; h18/h25/h27 are ~2.5 min each by design).

Ref posture (Round-4 note): the EXECUTION REF is the reconciled experiment
branch (rcos-harness-readiness / r4-reconcile), where preflight is 0/0/0.
Main carries the presentation face; its preflight intentionally reports the
V2 experiment-branch lineage findings (the preflight error text itself
prescribes: protocol history must be committed on the experiment branch, not
another ref) while V1/V3 are green there after the merge.

Locks: EXECUTION-LOCK amended to 70 entries (re-mints over the merged tree
and the path-derivation fix; append-only chain anchored at the D11 genesis,
intact); PROTOCOL-LOCK unchanged. `estimand-grade = 0` UNCHANGED. Execution
stays STOPPED for estimand-grade runs pending: the live P/Q calibration pair
(quota-gated; retry scheduled 2026-09-16 20:10 EDT), then PROTOCOL-LOCK
FINAL (pinning the ORDER-EXPANSION sha 4510076a…), then EXECUTION-LOCK
FINAL, then the first authorized cell.

## A16 — FINAL-lock semantics (MECHANISM ONLY; locks remain OPEN) — 2026-09-16

Round-3 audit item 4 and A11b P0-5 required a true terminal state for both
lock authorities — status FINAL with the finalization stamp and commit
recorded, amendments forbidden past it, the runner refusing a non-FINAL
lock, the first estimand run descending from the finalization commit, and
"no 'add amendment and keep going' path exists in the same experimental
epoch" — plus the ORDER-EXPANSION.json sha pinned as a protocol artifact
(experimental ordering is methodology). A16 lands that MECHANISM in
d75e379 (runner gate + terminal mint + EXECUTION-LOCK re-mint) and
f223675 (preflight enforcement + PROTOCOL-LOCK pin), 53d15c7 (proof suite
+ strict re-certification). **Both locks remain OPEN: EXECUTION-LOCK
status stays `open-round2` (72 amendments after the A16 re-mint) and
PROTOCOL-LOCK status is now explicitly `living-lock` (54 amendments).**
No status was flipped; actual finalization awaits the live P/Q
calibration pair and an auditor sign-off round.

What is now enforced (preflight.py, listed forward amendment #54
A16-FINAL-SEMANTICS, base d75e379):

- EXECUTION authority: status vocabulary `open-round2`|`FINAL`. A FINAL
  lock requires `finalized_at` (UTC stamp) and a 40-hex
  `finalization_commit`, carries exactly one terminal amendment
  (status_after "FINAL") as the LAST amendment; amendments past FINAL
  refuse, and a terminal amendment under an open status refuses (no
  reopen path). `harness/mint_execution_lock.py --finalize` is the one
  terminal transition — it refuses while any harness byte is unrecorded
  (finalization pins exactly the recorded bytes) — and every later
  mint/finalize is refused with the named EXECUTION-LOCK-FINAL-REFUSED,
  even with drifted bytes on disk.
- PROTOCOL authority: status vocabulary `living-lock`|`FINAL` (a
  pre-A16 lock with no status key reads as living-lock). FINAL
  additionally requires `finalized_amendment_count` == the present
  amendment count (the per-file-chain terminal marker) and the
  ORDER-EXPANSION.json pin; finalization fields under a non-FINAL status
  refuse as an inconsistent terminal state.
- ORDER-EXPANSION.json is pinned as a protocol artifact:
  PROTOCOL-LOCK `protocol_artifacts` records sha256
  449be793cf764204b8326a56914dd19c90f16371600db9d97faf60ccbe43f47a (the
  exact current bytes), verified against the live bytes from the moment
  the pin exists — never only at FINAL (A11b P0-5).
- A FINAL lock's `finalization_commit` is verified an ancestor of HEAD
  (`git merge-base --is-ancestor`) by both validators (V2 via
  protocol_tips, V3 via validate_execution); unresolvable commits fail
  closed.

Runner gate (run_arm_h1.final_lock_gate, called from main() after order
authorization and the derived-path binding, before any estimand
namespace or provider call): a WIRED estimand-surface cell refuses START
(FINAL-LOCK-GATE refuse start) unless BOTH locks are FINAL — named
LOCK-NOT-FINAL per open or malformed lock — and, once FINAL, unless the
run's execution_harness_commit equals or descends from the execution
lock's finalization_commit — named LOCK-DESCENT-REFUSED. The
--dev-unwired-outdir escape (wire=False, manifest dev_mode=true) and
harness-validation (H1-*) runs never reach the gate; admissibility
continues to exclude both from estimand-grade data, so the
harness-validation/estimand distinction is preserved end to end. The
full-pipeline suites (h14/h32/h33/h34) stub final_lock_gate beside
their existing lock-gate stub; the LIVE gate is proved by the new
`harness/tests/smoke_h36_final.py` (33/33, hermetic).

Certified-facts constants re-certified STRICTLY (h28/h29/h30/h31 — the
constants correctly caught real record changes; the checks were not
loosened): PROTOCOL-LOCK amendments 52 → 54 (53 at 0cf5b9d via
R4-RECONCILE-P0-R4-4, base d94dcf4, + 1 A16-FINAL-SEMANTICS at f223675);
preflight.py first-parent lineage 24 → 26 (same two commits). Two
fixtures updated to keep modeling reality exactly: h28's linear-chain
probe anchors the exact `validate_protocol(fam_c_dir` definition (the
A16 functions validate_protocol_final/validate_protocol_artifact_pin
share the old looser split prefix); h5's V3 fixture uses the real
`open-round2` marker instead of the pre-A16 arbitrary "open-test".

Round-5 record nits folded in: AUDIT-ROUND4.md "amendments 69–71"
corrected to re-mints 69/70 + the 53rd PROTOCOL-LOCK forward amendment
(#71 R4-RECONCILE-QPATH landed later, in the calibration follow-up); the
actual slice id is R4-RECONCILE-P0-R4-4 (base d94dcf4) — no literal
"AMEND-2026-09-16-r4-reconcile" id exists anywhere in the repo; and the
ORDER-EXPANSION pin is the file's sha256 449be793… — the "4510076a…"
written in the Round-4 records is the order_sha256 of ORDER.md recorded
INSIDE the expansion (correct in AUDIT-ROUND4.md's main↔branch note,
wrong in the two "pinning sha" references, both now corrected).

Verification at the A16 code tip 53d15c7 (clean tree, cleaned
/tmp/rcos-runs + /tmp/rcos-visible, per-suite 240s cap, un-piped exit
codes): full smoke battery 38/38 PASS (37 pre-existing +
smoke_h36_final.py); `python3 benchmarks/fam-c/preflight.py` 0/0/0;
`benchmarks/fam-c/runs/_synthetic-attack/run_attack.sh` 5/5. HARNESS-READINESS.md
remains untouched (deferred to the PROTOCOL-FINAL slice, unchanged
disposition).


## FIRST AUTHORIZED CELL EXECUTED — 2026-09-17 (post-FINAL)

At the finalized lineage (finalization_commit 1e14627; certified ref 2a1309d;
battery 38/38 at that ref with direct exit codes; post-FINAL mint/amend/reopen
refused with EXECUTION-LOCK-FINAL-REFUSED; live gate proof A0b), the first
authorized cell of the frozen order ran:

- Cell 9907c5cb038c02e0 = PQ/fam05/T0/acquisition (universe A), lane P
  (OpenCode Go union-alpha), ONE real provider call. Arrival decision: fresh.
  Container rc 0. Frozen mechanical checker verdict: **fix** (the produced
  artifact does not yet satisfy the frozen checker contract — a legitimate
  experimental outcome, not an error). Full evidence set written:
  H1-RUN-MANIFEST.json (cell_kind acquisition-solve), EVIDENCE-CHAIN.jsonl
  (4 links), call receipt + normalized usage + persisted request bytes,
  identity.json (provider-echoed union-alpha), arrival.json, OUTPUT.json,
  reuse ledger record. Evidence path: state/PQ/A/fam05/runs/9907c5cb038c02e0/.
- Attempt history: the first invocation hit HTTP 503 (upstream flake) and
  failed cleanly in transport (USAGE-CALL-FAIL; no manifest, no state beyond
  the staged prompt); the retry completed the cell. The 503 is an
  infrastructure failure under the A14 taxonomy — not an estimand outcome.

OPEN FINDINGS (for the next audit round; recorded, not hidden):
1. admissibility.py walks only benchmarks/fam-c/runs (line 390) — the new
   estimand cell lives under state/ (the derived wired surface per A11.5),
   so its tally still reads estimand-grade = 0 by walk ROOT, not by absence.
   Ruling needed: should the tally cover state/ (or should estimand evidence
   be mirrored into runs/)?
2. state/ is gitignored (repo .gitignore line 1 intent: local state never
   committed) — estimand evidence is currently Dell-local. Ruling needed on
   the durability/publication path for estimand evidence (selective
   git add -f, or a documented mirror step).


## EPOCH-1 FINDING (F1/F2): denied promotion cannot advance the order; the FINAL seal blocks the repair — 2026-09-17

The first real failed acquisition surfaced a design gap between two frozen
components:

- emit_promotion_outcome (A12d D1-B3) records the terminal NOT-PROMOTED
  outcome and states the intent VERBATIM: promotion completes as RECORDED
  NOT-PROMOTED, not an exception, **not a deadlock**.
- The authority cell_state() validates the record: status NOT-PROMOTED
  (acquisition-failed reason), i.e. the state is legal and validated.
- BUT completed_cells() (A11.6, the order-progress rule) accepts ONLY
  status == COMPLETE. A NOT-PROMOTED terminal state never advances the
  prefix walk, so every later cell is withheld. Empirically: after the
  denial was recorded, every probe refuses with
  earliest missing = 55cee707 (PQ/fam05/PROMOTION/A) — the frozen order
  deadlocks at its first legal failure outcome.
- The sibling cell has no path at all: CAPABILITY_LOCK 011ec0ec state is
  INCOMPLETE (capability dir absent) — no NOT-LOCKED terminal outcome was
  reached or written; advance() stopped at the promotion denial.
- The tests cover the outcome WRITING (h23) but never assert order progress
  after a denial — the exact untested seam.

Consequence and the seal: the repair is a harness-bytes change
(completed_cells accepting NOT-PROMOTED as progress-valid; a defined
NOT-LOCKED terminal for lock cells of failed universes; h-tests for the
seam). In epoch 1 that change trips preflight V3 (harness bytes changed
vs the FINAL lock manifest) and post-FINAL re-minting is REFUSED by design
(EXECUTION-LOCK-FINAL-REFUSED). The FINAL-lock semantics deliberately
contain no mid-epoch repair path. The decision is therefore a governance
ruling, not an operator action: (a) epoch-2 protocol (close epoch 1 with
this defect recorded; epoch-1 evidence stands as recorded; amend the
harness; re-finalize; restart the order), or (b) an explicitly created,
auditor-supervised defect-abatement mechanism (reopens the keep-going path
the design intentionally removed). Nothing estimand-grade is lost: no
capability was ever promoted in this epoch and no downstream/reuse cell
ran; the recorded epoch-1 evidence is acquisition-path evidence (T0/T1
verdicts + one validated denial).


## EPOCH-1 CLOSED — see EPOCH-1-CLOSURE.md (2026-09-17)

Ruling: EPOCH-2 PROTOCOL; epoch 1 terminated-not-repaired; no abatement mechanism; epoch-1 cells archived and NOT carried forward; epoch-2 requires fresh locks + a new finalization commit and re-runs the order from the beginning. Epoch-1 artifacts are immutable historical evidence.


## EPOCH-2 SLICE IMPLEMENTED — terminal-outcome progress semantics + epoch-2 lineage (2026-09-17)

Per the ruling recorded in EPOCH-1-CLOSURE.md (EPOCH-2 PROTOCOL;
terminal-outcome progress semantics), this slice lands the deadlock repair
and the explicit epoch-2 lineage. No epoch-1 artifact was amended:
state/PQ/** stays archived evidence, both FINAL locks keep their
closure-recorded bytes (EXECUTION-LOCK.json f6616ea2…, PROTOCOL-LOCK.json
96eac57b… — re-verified on disk by preflight), EPOCH-1-CLOSURE.md untouched.

Harness (the ruling's algebra, harness/order.py + harness/promotion.py):
- completed_cells()/cell_state() advance on VALIDATED event-specific
  terminals: model cells (T0–T4) COMPLETE only; PROMOTION COMPLETE |
  NOT-PROMOTED; CAPABILITY_LOCK COMPLETE | NOT-LOCKED; downstream cells of
  a capability universe whose acquisition validly failed NOT-EVALUABLE;
  INCOMPLETE/INADMISSIBLE never progress. No non-COMPLETE terminal converts
  to COMPLETE or authorizes promotion, lock creation, capability
  consumption, or retry (h37 proves each).
- The CAPABILITY_LOCK event of a NOT-PROMOTED universe now HAS its terminal
  writer: emit_capability_lock_outcome() writes
  CAPABILITY-LOCK-OUTCOME.json (outcome NOT-LOCKED, reason
  no-promotion-no-lock, created_from frozen-evidence, bound to the
  promotion outcome sha256 + the REAL validated T0/T1 chain tips) into the
  lock cell's derived run dir, fail-closed on an existing real lock, a
  conflicting receipt, stray governance artifacts and re-invocation.
  _not_locked_state validates the record before it can progress
  (tampered field / forged tips / tampered bound bytes / fabricated
  manifest / a real lock beside it => INADMISSIBLE, walk blocks).
- promotion.advance() drives one failed universe to BOTH terminals in a
  single call (NOT-PROMOTED recorded, then the lock event completes
  NOT-LOCKED) and refuses with PROMOTION-DENY | LOCK-DENY; re-invocation
  is an idempotent write-once refusal. next_event keeps deriving PROMOTION
  while the terminal record is owed.

Epoch-2 lineage (harness/epoch.py + harness/epoch_transition.py):
- Operator commands:
    python3 harness/epoch_transition.py --check
    python3 harness/epoch_transition.py --transition --reason "..."
  --transition verifies the epoch-1 closure facts on disk (refusing a
  drifted epoch), writes EPOCH-2-TRANSITION.json (citing the closure record
  sha256 917f379429a9… and both closure lock hashes) and mints the fresh
  epoch-2 locks: EXECUTION-LOCK-EPOCH2.json (epoch 2, status open-round2,
  its OWN append-only amendment lineage, 27 harness files) and
  PROTOCOL-LOCK-EPOCH2.json (epoch 2, status living-lock, governed = the
  transition-time governed bytes, ORDER-EXPANSION.json pin). Both carry the
  transition citation; the transition is write-once and never finalizes.
- All derived namespaces live under the ACTIVE epoch's state root
  (state/epoch2/…): epoch-2 completed_cells()/cell_state()/readiness walks
  never scan or write the archived epoch-1 evidence. Epoch-1 cells populate
  no epoch-2 prefix positions (the ruling's archive-don't-carry-forward).
- preflight V2/V3 accept the fresh lineage: the epoch-2 locks are the live
  authority (same structural rules — linear append-only chains from the
  recorded epoch-2 genesis, disk == unique tip, harness bytes/closure,
  ORDER-EXPANSION pin re-verified, status vocabulary), while the epoch-1
  FINAL locks are checked as HISTORICAL records (closure-cited bytes +
  status) whose tips are no longer enforced against epoch-2 bytes. V1
  recognizes the closure record + epoch-2 files as meta and no longer
  judges runtime state/ — the closure commit had left preflight at 1/0/0
  (six suites red on the same finding); this slice restores 0/0/0.
- The runner's FINAL gate and the seal-time identity bundle read the ACTIVE
  epoch's locks. Both epoch-2 locks are OPEN, so wired estimand cells are
  refused with the named LOCK-NOT-FINAL finding naming the epoch-2 lock
  until the OWNER finalizes (the epoch-1 FINAL locks authorize nothing).
  mint_execution_lock.py is epoch-aware (re-mint/finalize the active
  lineage; the closed epoch-1 lock is never touched): the slice's three
  later harness changes were recorded as the epoch-2 lock's first three
  own-lineage amendments (epoch2-slice).
- Deferred to the owner: epoch-2 finalization (both locks -> FINAL) and the
  epoch-2 cell execution from the beginning under the finalized lineage.

Verification at code ref c62c54ff048156edfb2846b0778290587aaa7342 (clean
/tmp/rcos-runs + /tmp/rcos-visible, per-suite direct exit codes, 300s cap):
full smoke battery 39/39 PASS (38 pre-existing + harness/tests/
smoke_h37_epoch2_semantics.py 26/26); `python3 benchmarks/fam-c/preflight.py`
0/0/0; `benchmarks/fam-c/runs/_synthetic-attack/run_attack.sh` 5 PASS /
0 FAIL at the same ref (h12 51/51, h13 50/50, h16 27/27, h25 19/19,
h34 29/29). Baseline at the pre-slice ref a012d60 for contrast: 32/38 PASS
with ALL six failures = `V1 INSTANCE-FREEZE: extra file not in freeze
manifest: EPOCH-1-CLOSURE.md`.

Suite updates required by the new semantics/lineage (none weakened):
H12 adds the algebra table + the strict-prefix ledger proof; H28/H29/H30/
H31/H35 live-lineage probes judge the ACTIVE epoch; H30/H31 certified
preflight.py lineage constants re-certified 26 -> 27; H36's live gate proof
is epoch-aware (open active locks => named refusal); H7's derived-namespace
probe asserts the rule under the ACTIVE state root. Runtime: h25 (the
minutes-scale suite) re-timed 191s baseline -> 162s after threading the
loaded ORDER-EXPANSION through the validation walk and short-circuiting
acquisition_failed() on the cheap committed artifacts.


## EPOCH 2 LIVE — order walks through failure (2026-09-17)

Per the EPOCH-1 closure ruling, epoch 2 was built, certified, and finalized:
fresh locks on their own lineage (EXECUTION-LOCK-EPOCH2 FINAL at 53e72ef,
2026-09-17T06:42:11Z; PROTOCOL-LOCK-EPOCH2 FINAL), post-FINAL refusals proven,
battery 39/39 at the certified ref, preflight 0/0/0, smoke_h37 26/26. Cells
execute under state/epoch2/ from the beginning.

First epoch-2 cells (all recorded outcomes, no retries of judgments):
- A/T0: blocked (arrival fresh, container rc 1). A/T1: ship arrival,
  candidate-validation FAILED (candidate rc 1).
- Controller advance recorded BOTH terminals in one call: NOT-PROMOTED +
  NOT-LOCKED (state/epoch2/PQ/A/fam05/runs/55cee707..., 011ec0ec...);
  downstream A cells NOT-EVALUABLE — the prefix walk consumed the failed
  universe and advanced. THE EPOCH-1 DEADLOCK IS FIXED, as ruled.
- C/T0 (lane Q): blocked. C/T1 (lane Q): blocked + validation failed;
  both C terminals recorded; downstream C NOT-EVALUABLE.
- B/T2 (control arm, no K): blocked (rc 1).
- Operator-error incident (recorded, preserved): the first C/T0 attempt was
  run on lane P by operator error; the state authority refused it
  INADMISSIBLE (manifest lane P != authorized Q) and a correct-lane re-run
  was refused CHAIN-TERMINAL; the attempt's bytes were moved (not deleted)
  to state/epoch2/_operator-errors/PQ-C-T0-lane-P-attempt/ with a NOTE.md.
- Early experimental observation (pre-promotion): fam05 candidate artifacts
  and downstream solves consistently fail container execution (rc 1) across
  A(P), C(P-attempt), C(Q), B(P) — a family-level pattern worth watching;
  all recorded as outcomes, none retried.


## EPOCH 2 STOPPED — parse-denial ruling; EPOCH-3 spec drafted (docs-only) — 2026-09-17

Ruling: third-party governance seat, 2026-09-17 ~10:30Z
(`/home/chow/rcos-campaign/RULING-2026-09-17-parse-denial.md`):
"CONTRACT-PARSE-DENY = EXPERIMENTAL OUTCOME. N=1. NO
RETRY-UNTIL-ADMISSIBLE. ATTEMPT 2 PRESERVED, NON-ESTIMAND. EPOCH 2 STOPS AT
THE UNREPRESENTABLE FINAL CELL. EPOCH 3 MAY ADD A PRE-FROZEN
MODEL-OUTPUT-INVALID TERMINAL AND RESTART CLEAN."

META (docs only — this slice changed no lock, no harness byte, no
`state/` file, made no provider call, and ran no battery):

- **Epoch 2 is STOPPED at cell 64/240** (`b933d9322add55cc`,
  PQ/C/fam04/T0, lane Q). The fail-closed contract raised
  `CONTRACT-PARSE-DENY` on the authorized sample, so no `arrival.json`, no
  manifest, and no chain terminal exist; the FINAL lineage has no lawful
  ordered-path representation for that tuple. No terminal was invented for
  the cell, nothing under `state/` was written or moved, and
  `completed_cells()` must NOT advance past the prefix tip
  `e38ed4c1c456fe6a` (cell 63). The ~176 later events remain withheld.
- Stop record: `EPOCH-2-STOP-RECORD.md` (new; sha256
  `7c076ee23e246d06ac6ab21f0e3644b5a4a91e295edf39f9b8c47af5ea8a3881`) —
  what ran (prefix cells 0–63 across fam05/fam03/fam01 and fam04-A; eight
  T0 acquisitions, seven arrivals all rc 1, seven failed candidate
  validations, zero valid candidates, no promotion and no lock ever minted),
  both preserved attempts' classification, and the no-capability statement.
  It creates no terminal and is evidence about why epoch 2 stopped.
- Epoch-3 spec draft: `EPOCH-3-PROTOCOL-SPEC.md` (new; sha256
  `6db4a7fba352307899420c8cc2f7fceace878e55ca1a9de52877b9c66050d8a6`) —
  the pre-frozen `MODEL-OUTPUT-INVALID.json` terminal (schema, field
  semantics, writer site at the runner's parse gate, forbidden companions),
  the progress algebra (COMPLETE-FAILURE for model cells; T0 failure ⇒
  T1/T2/T3/T4 NOT-EVALUABLE acquisition-failed, PROMOTION NOT-PROMOTED,
  CAPABILITY_LOCK NOT-LOCKED), attempt-level reliability statistics, the
  infrastructure boundary, and the epoch-3 lineage/restart-from-0
  discipline. DRAFT — not frozen.
- Freeze request: `FREEZE-REQUEST.md` (new; sha256
  `b4889c57eda2f87cf4ca09e0adeba594eba08094426d4a09382dedc240b292a6`) —
  FR-1 … FR-13 for third-party adjudication (terminal name/schema, status
  token and algebra, writer site, forbidden companions, validator symmetry
  incl. the no-T1 governance terminals, attempt accounting, lineage
  mechanics and citations, restart-from-0, infra boundary, terminal-cell
  reporting, epoch-2 stop visibility, implementation authorization +
  certification, and the preflight `META` wiring for these new root docs),
  plus the recorded conflicts (A12d predicate vs the no-T1 algebra;
  pair-replacement granularity; §24 row shape; diagnostic-repeat placement;
  the unclassified preserved epoch-2 call; certification extras; and whether
  the seat supplies an explicit "epoch 2 CLOSED" formulation).
- Preserved epoch-2 evidence is read-only and unchanged:
  `state/epoch2/_operator-errors/PQ-C-fam04-T0-lane-Q-attempt/`
  (`INCIDENT.json` sha256
  `ccf2dc65adf1e8f8c2f23bb62f168457fcf00ddcf1546def3f43a1233fce49b5`;
  attempt-1 `f23da2d0f49e052b`, 1444 B; attempt-2 `a63ba445157af666`,
  42,766 B, non-estimand diagnostic repeat).
- Certification note (recorded, not hidden): these three root-level docs are
  V1 INSTANCE-FREEZE extras under the current `preflight.py` `META` set
  (FR-13); this docs-only slice may not amend `preflight.py` (protocol
  governed), so the named findings are expected and listed for the seat.

Next: the third-party seat adjudicates `FREEZE-REQUEST.md`. No epoch-3
implementation and no epoch-3 model call precede that freeze; epoch 2 stays
stopped/incomplete as recorded.

# Fam-C Harness Readiness (frozen spec — implementation follows per slice)

Every requirement below is a machine-testable invariant, not guidance.
Each carries: requirement, proof mechanism, failure mode (what blocks
execution), and the adversarial test that demonstrates it. Slices land
as sealed units: H1 (causal isolation) → H2 (evidence) → H3 (governance).

Conventions: `LANE in {A,B,C,D}` per PREREG §1; treatment lanes = A,C;
control lanes = B,D. `K` = the locked capability for the family under
test. All paths relative to the experiment root unless stated.

---

## Slice H1 — CAUSAL ISOLATION (build first; nothing else matters if wrong)

### H-BD-001 — B/D hard inaccessibility

Requirement: a control-lane agent can neither resolve, enumerate, read,
load, invoke, nor infer treatment capability artifacts through ANY path:
filesystem, registry API, router query, model context, cache, history,
environment, or network fetch of the benchmark repo.
Proof: isolated registry namespace per lane + filesystem deny rules +
tool/API deny rules + negative probe (below) executed green pre-run.
Failure: experimental execution blocked until green.
Test: from a B/D sandbox, attempt every capability access path
(direct read, glob, registry list/get, router ask-for-K, prompt-inject
a guessed capability ID, fetch PREREG-declared artifact URL).
Expected: DENIED / NOT_FOUND on all paths, logged.

### H-CTX-002 — treatment/control context symmetry

Requirement: for each paired task, the treatment and control contexts
are byte-identical except the capability-access bit (present/absent).
No extra hints, richer descriptions, producer commentary, curated
integration notes, or differing tool manifests.
Proof: context-builder emits a canonical context bundle + sha256 per
arm; a symmetry checker diffs treatment vs control bundles and passes
iff the ONLY difference is the capability-access block.
Failure: pair void; must rebuild contexts, never patch mid-run.
Test: fixture pair with a deliberately injected asymmetry → checker
must FAIL closed.

Implementation (round-2 item 6): the runner stages the agent-visible root
ONCE (sealed copy: prompt.md + VISIBLE-declared fixtures) and builds BOTH
the model context and the docker `/task` mount from those exact staged
bytes — never from two independent reads of the frozen task dir. The
manifest records `context_task_snapshot_hash`, which must equal the
sandbox `task_snapshot` (same staged bytes → same hash; drift refuses
before the call). One canonical envelope object carries the shared task
bytes verbatim in both arms; the delimited capability-access block
(`<<<CAPABILITY-ACCESS-BEGIN>>>` … `<<<CAPABILITY-ACCESS-END>>>`) appears
exactly once in treatment and never in control; `check_arm_symmetry()`
fails closed on any one-byte shared-region asymmetry, stray/duplicated
delimiter, missing frozen section header, preamble/output-schema drift,
or content past the envelope. Control-arm bytes are unchanged from the
pre-item-6 template (regression-pinned).

### H-SES-003 — session/workdir/state isolation

Requirement: every task invocation starts in a fresh model session with
a private workdir, private registry view, private cache, private
history, and private scratch. No shared writable state across lanes,
tasks, or arms. Session IDs unique per invocation and logged.
Proof: isolation enforcer creates per-run sandbox dirs (0600), distinct
registry namespaces, and asserts no cross-lane readable paths before
each run; post-run audit greps run manifests for shared paths/IDs.
Failure: run refused pre-start; affected pairs invalidated post-hoc.
Test: plant a canary file in lane A's workdir; attempt read from lane
B/C/D sandboxes → must be DENIED. Duplicate a session ID → enforcer
must refuse to start.

### H-EVAL-004 — evaluator sealing

Requirement: no experimental agent can read truth, checkers, evaluator
outputs, or grade manifests before its run completes. Sealing is
enforced by filesystem boundary + harness mediation, never by prompt
("do not look") alone.
Proof: evaluator files live outside all agent-visible roots (per
VISIBLE.md seals); the grading step runs in the harness process, not
the agent; a pre-run seal audit asserts no agent-visible path resolves
to evaluator content.
Test: from an agent sandbox, attempt to open truth.json, check.py,
K.md, DESIGN-T4.md, sibling task dirs, and the repo URL → all DENIED /
NOT_FOUND. Attempt via tool/API indirection too, not just direct read.

---

## Slice H2 — EVIDENCE (usage, identity, reuse fields, contribution)

### H-USE-005 — token/cache accounting

Requirement: every model call records RAW provider usage (uncached
input, cached input kept separate, output tokens, model-reported cost
where exposed, wall time, call count). Primary metric derives ONLY
from recorded raw usage; missing usage invalidates the run — never
reconstructed heuristically, never cached-as-uncached.
Proof: usage-capture wrapper persists the raw provider response usage
block per call; an accounting checker recomputes all metrics from raw
blocks and fails any run with absent or merged token fields.
Failure: run invalid (missing evidence), not estimated.
Test: fixture call with usage stripped → accounting checker FAILs;
fixture with cached tokens relabeled uncached → FAILs.

A1 implementation (audit round 2 item 1): provider-bound v2 adapters
(`router9-openai-chat-v2` for lane P, `kenari-openai-chat-v2` for lane Q;
see LANES.md + usage.py PROVIDER_NORMALIZERS). The runner writes the
immutable `call-<id>.normalized.json` artifact IMMEDIATELY after every
recorded call (never post-hoc), binds its hash + derived metrics
(primary_work / uncached / output / cached / call count) into the
model-call chain link, and admissibility re-verifies every artifact
(self-sha + raw-file binding + metric re-derivation) — tampering the raw
receipt OR the normalized artifact excludes the run. New receipts also
carry `request_body_sha256` over the exact bytes POSTed.

### H-ID-006 — provider/model identity capture

Requirement: every model call logs provider endpoint, requested model
id, provider-echoed model/version where exposed, request/run IDs,
timestamps, and full generation parameters. P/Q identity established
provider-side, never by model self-report (per LANES.md rule).
Proof: identity records committed per run; auditor replays endpoint +
model id and confirms distinct families; any self-report-only identity
claim fails the check.
Failure: closed — runs without established identity do not count
toward any gate.
Test: fixture with mismatched requested-vs-echoed model id → FAIL;
fixture with identity fields absent → FAIL.

Item-3 implementation (audit round 2 item 3): nonempty provider
response/request id REQUIRED (IDENTITY-INCOMPLETE otherwise); the exact
`request_body_sha256` from the usage receipt plus the complete explicit
generation-param set are preserved in every identity record; the runner
sends AND records ONE param set (no drifting literals); the model-call
chain link cross-verifies identity↔receipt binding and carries the
provider id + body hash + params; admissibility re-verifies the binding
per receipt — stripping the echo, stripping the provider id, or altering
model/params on either side fails the chain and excludes the run.

### H-REUSE-007 — full reuse lifecycle + material-contribution evidence

Requirement: replace every flat reused[] with the PREREG §12 field
split (available, candidate_ids, selected, loaded, invoked,
output_consumed, materially_contributed, rejected + reason). In
particular `materially_contributed` requires an OBJECTIVE evidence
predicate — never model self-report. Frozen predicate for this series:
the capability's emitted artifact hash appears as an input (by hash)
to a downstream node whose output the evaluator consumed, OR the
run is byte-identical with/without the capability step removed
(ablation receipt). Absent such evidence, consumed≠contributed.
Proof: reuse-log validator enforces field presence + the contribution
predicate against artifact hashes; self-report-only contribution
claims fail.
Failure: reuse claim downgraded to invoked-only; genuine_reuse
predicate (§19) cannot be satisfied by that run.
Test: fixture log claiming contribution with no hash linkage → FAIL;
fixture with hash-linked artifact chain → PASS.

---

## Slice H3 — GOVERNANCE (lock enforcement, invalid-run machine, manifests)

### Authority locks (round-2 item 4 — no re-freeze)

Three independent authorities, validated by `preflight.py` (all green
required; the runner refuses to start otherwise):

- V1 INSTANCE-FREEZE — frozen instance bytes vs the git-resolved
  FREEZE-HASHES manifest at `d1292434` (+ ancestry proof).
- V2 PROTOCOL-LOCK — this document, PREREG/ORDER/LANES, and preflight.py
  itself vs `PROTOCOL-LOCK.json`: frozen bytes or a listed forward
  amendment, never unlisted drift.
- V3 EXECUTION-LOCK — executing harness bytes vs `EXECUTION-LOCK.json`
  (`open-round2` placeholder until the #14 final lock).

### H-LOCK-008 — CAPABILITY_LOCK enforcement

Requirement: T2–T4 consume EXACTLY the locked artifact hash recorded in
CAPABILITY_LOCK. Nothing can mutate, repromote, or re-resolve K
downstream: the loader resolves by hash, verifies bytes pre-execution,
and refuses on mismatch. Promotion writes once; downstream is read-only.
Proof: lock contains id/version/impl_sha/manifest_sha/training
receipts; loader hash-verifies before every invocation and logs the
check; post-run audit re-verifies all invocation hashes against lock.
Failure: run refused (pre-execution mismatch) or invalidated (post-hoc
mismatch).
Test: tamper one byte of the locked artifact post-lock → loader must
REFUSE; replay a run against a re-resolved (non-lock) hash → audit FAILs.

### H-INV-009 — invalid/infrastructure state machine

Requirement: the frozen invalid-run taxonomy (§19 + preflight precedent)
is encoded literally as a state machine, not operator judgment. Agent
or model failure (reasoning failure, tool misuse, self-caused timeout,
bad code, capability-invocation failure, malformed-output eval
failure) is an EXPERIMENTAL OUTCOME, permanently recorded. Only a
qualifying infrastructure failure (machine/provider/harness preventing
task receipt or execution, per taxonomy) permits exactly ONE whole-pair
replacement under identical frozen settings; originals remain immutable
and linked. A second consecutive infrastructure failure on the same
pair → missing evidence → INCONCLUSIVE per frozen precedence.
Proof: replacement controller enforces single-replacement + identical
settings + linkage; any second replacement attempt, single-arm
replacement, or agent-failure-marked-infrastructure is rejected.
Failure: offending runs invalid; affected pairs excluded with cause.
Test: mark an agent-timeout run infrastructure → controller must
REJECT; attempt a second replacement on one pair → REJECT; attempt a
single-arm replacement → REJECT; valid infra failure → exactly one
linked whole-pair replacement ALLOWED.

### H-ORD-011 — execution order is enumerated and enforced

Requirement: the frozen ORDER.md sequence is the only authorized execution
order; a run that is not the next authorized cell cannot start.
Implementation (round-2 item 7): `harness/order.py` parses ORDER.md
mechanically (family order, block order PQ→QP, per-family task order and
letter permutation, seed) and expands it into 144 cells, each with a stable
`cell_id`; the committed `ORDER-EXPANSION.json` is that expansion and is
never hand-edited (preflight V2 re-derives it from ORDER.md and fails on
any drift). Before any model call the runner requires `--block PQ|QP`,
resolves the requested (block, family, task, lane, arm) to its cell, and
refuses on: a cell outside the frozen universe, an unknown block/lane/arm,
a duplicate already-completed cell, or ANY earlier cell still incomplete
(covers fam01 before fam05, QP before PQ completes, and wrong arm order
within a family). The completion ledger counts only wired, non-dev
manifests carrying a `cell_id`. Capability dirs outside the Fam-C registry
surface are refused (FOREIGN-REGISTRY-DENY). The manifest stamps
block/cell_id/cell_index/cell_letter/order_sha256 for the run. Preflight V3
also checks the runner's whole IMPORT CLOSURE against EXECUTION-LOCK.json,
so a module that executes during a run cannot ride outside the execution
authority; `harness/mint_execution_lock.py --check` re-verifies that
mechanically (and mints the amendment after an intentional change).
Test: `harness/tests/smoke_h7_order.py` (adversarial refusals + real
runner subprocess refusals, no model call).

### H-CAL-012 — P/Q calibration pair (CALIBRATION / NEVER-ESTIMAND)

Requirement: exactly ONE P/Q calibration pair runs through the FINAL
identity+usage path before the execution lock is minted, proving both lanes
answer with the requested params and produce the full evidence set (echoed
model id, nonempty provider response id, raw usage + hash, normalized usage
+ hash, request-body binding) — without contributing anything to the
estimand.

Implementation (round-2 item 2): `benchmarks/fam-c/harness-run/calibrate.py`.
A calibration call is a CALIBRATION / NEVER-ESTIMAND call: it is not a cell
of ORDER.md, never enters `ORDER-EXPANSION.json` or the runner's completion
ledger, writes no `H1-RUN-MANIFEST.json` (so admissibility returns EXCLUDED
and estimand-grade stays 0), and lives under `runs/_calibration/`. Modes:
`--plan` (default) prints the exact calls and performs none; `--offline`
rehearses the entire capture→identity→normalize→verify→bind path against a
synthetic provider response with zero network, plus the fail-closed
controls (tampered raw usage, missing echoed model, missing provider id);
`--live` makes the REAL calls and requires BOTH `--i-know-this-spends` and
`--approve-quota`, so a live calibration can never be accidental. A lane
failure is INCONCLUSIVE missing evidence, never a substituted model and
never retried.
Status: scaffold + offline rehearsal green (`smoke_h8_calibration.py`,
38/38). The real pair is time-gated — the Q lane (free tier) quota resets
00:00 UTC — and runs after items 1–13, immediately before the
EXECUTION-LOCK mint.

### H-MAN-010 — evidence/manifest chain

Requirement: every run is auditable afterward as an unbroken hash chain:
frozen commit → run manifest (inputs, code, lane, order) → model calls
(usage + identity) → capability events (select/load/invoke/consume
hashes) → evaluator (sealed truth hash, checker hash, verdict) →
grade. No headline may contain information not traceable to this chain
plus immutable manifests.
Proof: manifest writer emits the chain per run; a chain auditor
re-verifies every link (hash presence + equality) and fails the run on
any broken link.
Failure: run excluded from all tallies until the chain is repaired —
repairs append new linked records, never rewrite.
Test: fixture chain with one link hash altered → auditor FAILs;
fixture chain missing the evaluator link → FAILs.

---

## Adversarial smoke suite (run pre-P/Q; all must FAIL CLOSED as noted)

```text
B reads K directly                    → FAIL CLOSED (H-BD-001)
B asks router for K                   → FAIL CLOSED (H-BD-001)
D guesses capability ID               → FAIL CLOSED (H-BD-001)
C receives extra producer summary     → FAIL (H-CTX-002)
two lanes share session ID            → FAIL (H-SES-003)
two lanes share writable workdir      → FAIL (H-SES-003)
agent opens truth/check.py            → FAIL CLOSED (H-EVAL-004)
semantic ID enters consumer context   → INVALID (auditor IDs confined)
cached tokens counted as uncached     → FAIL accounting (H-USE-005)
material_contributed from self-report → FAIL (H-REUSE-007)
locked capability hash changes        → FAIL CLOSED (H-LOCK-008)
agent timeout marked infrastructure   → FAIL (H-INV-009)
replacement reruns one arm only       → FAIL (H-INV-009)
second replacement attempted          → FAIL (H-INV-009)
```

## Slice order (sealed units)

- Slice H1 (§§H-BD-001…H-EVAL-004): spec above + implementation +
  adversarial smoke for H1 + attack. NOTHING downstream begins until
  H1 is green — beautiful accounting on a contaminated experiment is
  worthless.
- Slice H2 (§§H-USE-005…H-REUSE-007): spec above + implementation +
  smoke + attack.
- Slice H3 (§§H-LOCK-008…H-MAN-010): spec above + implementation +
  full 14-line smoke + attack.

## Status

- [ ] H1 specified (this document) — implementation open
- [ ] H1 implemented + smoke green
- [ ] H2 specified (this document) — implementation open
- [ ] H2 implemented + smoke green
- [ ] H3 specified (this document) — implementation open
- [ ] H3 implemented + full smoke green

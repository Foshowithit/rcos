# Fam-C Audit Round 1 — external adversarial audit (ChatGPT) + verification scorecard

Date: 2026-09-08. Auditor: ChatGPT (external, public-branch read-only).
Source: full auditor reply preserved in `AUDIT-ROUND1-REPLY.txt`.
This file is the parent-seat verification scorecard. Each finding was
cross-checked against primary sources in this repo (research-first:
a secondhand claim is a hypothesis, not evidence). Symbols:
[VERIFIED] = confirmed against repo bytes this session.
[PARTIAL] = directionally right; nuance recorded.
[OPEN]    = needs a decision/answer the repo cannot give.

## Verdict-level corrections (accepted)

1. Fam-C frozen causal comparisons are A-B and C-D within separate A/B/C/D
   universes (PREREG §2, L40-80) with reciprocal PQ/QP blocks (ORDER.md).
   Raw P-vs-Q is not the estimand. [VERIFIED]
2. "Retirement" is not a Fam-C estimand — zero mentions of retirement in
   benchmarks/fam-c/*.md (grep). Status wording must say "promotion + locked
   reuse under workflow control". [VERIFIED]
3. STOP experimental execution until the gate below is closed. The existing
   H1-P-fam05-T0 (and H1-P-fam01-T0) runs are harness-validation evidence,
   NOT estimand data. [VERIFIED]

## P0 findings

1. Reclassify H1 runs as harness-validation; admissibility command returns
   EXCLUDED + estimand-grade = 0. [VERIFIED — run manifest shows
   wired=true but satisfies none of the evidence gate below]
2. H2 schema mismatch: REAL P receipt (runs/H1-P-fam05-T0/call-d7e69725...json)
   carries prompt_tokens/completion_tokens/prompt_tokens_details.cached_tokens;
   normalize_usage() requires top-level input_tokens/output_tokens/cached_tokens
   and FAILS on the real receipt (reproduced live this session:
   USAGE-INCOMPLETE: 'input_tokens' missing/invalid). Auditor's normalized
   numbers check out exactly: 478-128=350 uncached input, 1965 output,
   primary_work=2315. run_arm_h1.py never calls normalize/summarize before
   grading. [VERIFIED]
3. H-ID-006 not wired: receipt stores only endpoint/model_requested/usage.
   identity.py record_identity/check_against_prereg exist but are never
   called; response object discarded. [VERIFIED]
4. frozen_commit() = `git rev-parse HEAD` (run_arm_h1.py L132-138). Real
   manifest frozen_commit=cd991739 (execution HEAD) vs FREEZE.json
   freeze_commit=d1292434 (git object exists). No HEAD masquerading as the
   freeze. Need dual anchors. [VERIFIED]
5. Execution harness not frozen before estimand runs; EXECUTION-LOCK after
   audit closes. [VERIFIED — no execution lock exists]
6. CORRECT vs DISABLED prompts differ beyond the capability block
   (run_arm_h1.py L76-102: different instructions + different response
   envelope records+field_map vs solver_py) — violates H-CTX-002
   byte-identical-except-capability-block. [VERIFIED]
7. Prompt built from taskdir (L296-307) then build_visible_root(taskdir)
   (L336) — two separate reads; no proof model saw the executed bytes.
   [VERIFIED]
8. Runner accepts arbitrary lane/family/task/arm/outdir/capdir, never
   validates ORDER.md, no A/B/C/D concept. Operator discretion channel
   exactly as the prereg removes. [VERIFIED]
9. Sequencing: fam05 first CONFIRMED by ORDER.md ("Family order:
   fam05, fam03, fam01, fam04, fam06, fam02"). But the attempted
   H1-Q-fam05-T0 during the PQ block was out of order — Q-based
   acquisition belongs to the QP block ("Block order: PQ first, QP
   second"). It hit the kenari quota and produced NO run record, so no
   contamination; scheduler must refuse it going forward. [VERIFIED]
10. No A/B/C/D universe scoping: capabilities under a global
    benchmarks/fam-c/capabilities/ tree; PREREG §2 requires separate
    workdirs/registries/locks per universe. [VERIFIED]
11. lock.promote() writes whatever the caller gives (lock.py L17-38) — no
    T0+T1 proof. run_arm_h1 --promote fires only when cap_info exists,
    which requires an existing lock → circular for acquisition.
    [VERIFIED]
12. Legacy CAPABILITY_LOCKs exist under capabilities/ (dag-validate-v1,
    event-dedup-v1, record-normalize-v1, reconcile-v1, ...) from pre-H1
    ad-hoc runs; must be refused by the estimand runner. [VERIFIED]
13. No treatment path that inspects-and-rejects K then fresh-solves; correct
    arm always loads+invokes. T4 correct behavior (reject/abstain + solve
    without K) unimplementable. [VERIFIED — run_arm_h1.py has no REJECT
    branch]
14. CAPABILITY_LOCK lacks semantic_core/preconditions/limitations +
    auditor-side semantic IDs. [VERIFIED — lock.py writes none]
15. materially_contributed hardcoded False (L195, L379). reuse_log.py
    already has check_hash_linkage + check_ablation + genuine_reuse —
    not wired. [VERIFIED]
16. invalid.py (PairLedger/classify) exists, never imported by the runner.
    [VERIFIED] OPEN QUESTION (auditor refuses to invent): what frozen rule
    governs infra-invalid T0/T1 acquisition runs? H-INV-009 covers paired
    comparisons only. → PROPOSED FORWARD-FROZEN RULE for Round 2 audit:
    infra-failure (429/5xx/timeout/transport) on an acquisition cell
    authorizes mechanical same-cell retry after recovery, logged as
    attempt N with full attempt history, never relabeled; N-cap exceeded →
    cell QUARANTINED + escalation, never silent replacement. Ratification
    pending auditor review before claim-grade.
17. Chain doesn't bind block/universe/pair_id/order-authorization/context
    symmetry/identity/normalized-usage/execution-lock/registry; audit()
    called without expected_grading_rule. [VERIFIED — chain.py supports
    pair_id + expected_grading_rule; _wire_chain passes neither]
18. No §24 ESTIMAND-ROW emitter. [VERIFIED]
19. --no-wire on the estimand surface. [VERIFIED — L446]

## P1/P2 findings (accepted as notes + future work)

20. Keep quarantined fragments; add QUARANTINE-INDEX.json +
    ESTIMAND-INDEX.json (only validator writes the latter). [VERIFIED —
    no indices exist]
21. Contamination/provenance note: frozen instances touched by harness
    development → PILOT-GRADE only; claim-grade replication needs a fresh
    unseen family freeze. Status doc already says QUARANTINED/NOT GRADABLE;
    add the explicit note for the paper. [PARTIAL — status doc partial]
22. Leak-risk ranking accepted (operator/capability-namespace highest;
    Docker escape lowest). Docker hardening (no-new-privileges, per-run
    cleanup receipt, runtime version) deferred. [OPEN — implementation]
23. ARCHITECTURE.md stale; update after gate is safe. [VERIFIED — doc
    stale]

## Where the audit was audited

Cross-checks this session, all green:
- git HEAD 5dc5aa7 clean; FREEZE.json freeze_commit d1292434 exists.
- H1-P-fam05-T0 manifest: wired=true, frozen_commit=cd991739, verdict ship.
- Real P receipt fails normalize_usage() live; contains no echoed identity.
- ORDER.md family order fam05-first; PQ→QP blocks; lane key A/B/C/D.
- PREREG §2 (universes), §9 (promotion), §10 (lock), §10.1 (T4 contract)
  match the auditor's citations.
- No "retirement" text in fam-c docs.
- Lock.py lacks contract metadata; legacy locks exist in capabilities/.

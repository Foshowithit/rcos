# AUDIT ROUND 2 — verification scorecard (parent seat, 2026-09-08)

Raw ChatGPT reply preserved verbatim in `AUDIT-ROUND2-REPLY.txt`.
Branch `rcos-harness-readiness` verified by auditor at HEAD `2c752fe`.

## Auditor verdict on Round-1 fixes
| Round-1 item | Verdict | Note |
|---|---|---|
| #1 H1/ad-hoc exclusion | PASS | admissibility mechanically excludes H1-* + no-manifest runs; estimand-grade 0 |
| #2 real usage schema | PARTIAL PASS | 478−128+1965 = 2315 reproduces, but runner does NOT call normalize_usage()/bind normalized result |
| #3 provider identity | PARTIAL PASS | wiring in place; provider_response_id optional; no post-fix real receipt |
| #4 dual anchors | PARTIAL PASS | freeze≠exec HEAD and drift checked, but FREEZE-HASHES read from working tree, not git-resolved |
| #19 --no-wire | PASS | estimand surface refuses; dev escape forced outside Fam-C, stamped non-estimand |
| wording | PASS | "promotion + locked reuse", never retirement |

Terminology correction: `ESTIMAND-ELIGIBLE` (admissibility) must not be a synonym of
estimand-grade until the full §24/chain gate passes. Rename to STRUCTURALLY-ELIGIBLE.

## Round-2 P0 list (auditor-ordered; items 1–7 are "the next useful diff", no real benchmark calls)
1. FINISH A1 — mint provider-bound/versioned adapters (`router9-openai-chat-v2`,
   `kenari-openai-chat-v2`); runner normalizes EVERY call, writes immutable
   `normalized-usage.json`, hashes it, binds hash + primary_work + uncached +
   output + cached + call count into model-call chain. Historical receipts stay on
   the old id (excluded anyway). Acceptance: P receipt → 2315; Q calibration →
   deterministic; missing/mismatched schema → fail; chain carries normalized SHA;
   tampering raw OR normalized breaks admissibility.
2. ONE P/Q calibration pair before EXECUTION-LOCK (tiny CALIBRATION / NEVER-ESTIMAND
   calls through the final identity+usage path). Time-gated: Q quota resets 00:00 UTC.
   Acceptance: both produce echoed model, provider response ID, raw+normalized usage,
   requested params; freeze observed acceptable echo behavior.
3. IDENTITY HARDENING — require nonempty provider response/request ID when the endpoint
   supplies one; preserve exact request-body hash + complete explicit generation-param
   set. Acceptance: strip echoed model → fail; strip required provider ID → fail;
   alter model/request params after receipt → chain/admissibility fail.
4. PREFLIGHT RE-SCOPE (option b, no re-freeze) — three authorities: INSTANCE-FREEZE
   (d1292434 original bytes), PROTOCOL-LOCK (PREREG/ORDER/LANES/HARNESS-READINESS +
   explicit forward amendments incl. A2 LANES identity additions), EXECUTION-LOCK
   (final harness). Three independent validators green; modifying any governed file
   → the appropriate lock fails.
5. IMMUTABLE INSTANCE MANIFEST — resolve FREEZE-HASHES.sha256 from freeze commit via
   Git (never trust working-tree copy); verify FREEZE.json.freeze_tree == recorded
   commit's expected tree. Acceptance: edit local FREEZE-HASHES → cannot redefine
   truth; alter freeze_tree → refuse start.
6. #6/#7 CONTEXT SYMMETRY + ONE SOURCE SNAPSHOT — stage VISIBLE once; model context
   AND docker /task built from those exact staged bytes; one canonical
   prompt/envelope; treatment/control differ only by mechanically identified
   capability-access block. Acceptance: context_task_snapshot_hash ==
   sandbox_task_snapshot_hash; A/B+C/D canonical diff reports only the capability
   block; one-byte hint asymmetry fails closed.
7. #8/#9/#10 SCHEDULER + NAMESPACE — machine-readable ORDER-EXPANSION.json
   enumerating every authorized cell (A-vs-C acquisition order resolved, e.g.
   PQ/A/fam05/T0 before PQ/C/fam05/T0) through QP; runner refuses lane/family/task/
   arm/universe outside it before any model call. Acceptance: fam01-before-fam05,
   QP-before-PQ-complete, duplicate cell, wrong universe, foreign registry, wrong
   arm order → all refuse before model call.

## Round-2 P0 list — items 8–13 (next rounds; EXECUTION-LOCK #5 LAST after full-stack synthetic attack)
8. #11 promotion controller — T0 SHIP + T1 SHIP, distinct task/surface, frozen
   semantic capability, both evaluator evidences; --promote replaced.
9. #12/#14 estimand-aware locks — block/universe, capability id/version, T0/T1 chain
   tips, producer identity, protocol/execution lock SHAs, artifact hashes,
   semantic_core/preconditions/limitations + auditor T4 semantic ID; legacy locks
   → LOCK-INADMISSIBLE.
10. #13 reuse-enabled treatment — USE/REJECT selection decision before loading K;
    rejection = fresh-solve machinery, records available+considered.
11. #15 material contribution — hash-lineage route: capability emits immutable
    intermediate artifact, deterministic finalizer consumes exact hash, evaluator
    consumes finalizer output → genuine_reuse() true without model testimony.
12. #16 retry rule RATIFIED WITH AMENDMENT — exactly ONE infrastructure replacement
    per acquisition cell; original attempt immutable; second infra failure →
    INCONCLUSIVE missing evidence, no third try; model-caused failures zero retries;
    recorded_call() must preserve typed failure category/status + immutable
    failed-attempt receipt (no generic RuntimeError collapse).
13. #17/#18 chain+admissibility as the estimand gate — run_id generated BEFORE model
    call; full field set (block/universe/pair/order auth/session/context hash/task
    snapshot/registry ns+hash/lock hashes/identity/normalized usage/capability
    lifecycle/sandbox cmd+arrival/checker+truth hashes/final metrics); Chain.audit
    with expected_grading_rule; closed-schema ESTIMAND-ROW.json; admissibility →
    cryptographic/semantic validation; STRUCTURALLY-ELIGIBLE vs ESTIMAND-GRADE.
14. #5 EXECUTION-LOCK last — after 1–13 + full-stack synthetic attack; freeze exact
    harness bytes/configs/image digest/protocol lock; harness_manifest_sha() FAILS
    on missing listed module (currently silently skips).

P1/P2 (#20–#23) ride but not waived from the final loop.
Sequencing ruling: fam05 first; earlier H1-Q-fam05-T0 stays harness-validation/
quarantined. Stop signal reserved until every P0/P1/P2 closed + locks green +
adversarial fixture fail-closed + §24 regenerable from committed evidence +
quarantine mechanical + no metric shopping + docs match evidence.

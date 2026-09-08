# Fam-C lane assignments (frozen; re-verify reachability before first run)

- **P (producer)**: router9 `minimax-m3` (MiniMax family; reasoning content
  verified live 2026-09-07).
- **Q (consumer)**: kenari `agnes-2-0-flash:free` (distinct vendor/endpoint;
  completion verified live 2026-09-07). Model identity is established
  PROVIDER-SIDE, never by self-report: record the provider endpoint,
  the exact model id requested, the model id echoed in the API
  response, and the full usage block per call. Self-reported model
  names inside completion text are inadmissible as identity evidence.
- **Reciprocal block**: INCLUDED. Block PQ (P produces, Q consumes) and
  block QP (Q produces, P consumes) run independently and report
  separately; no pooling until both reported.
- If either lane is unreachable at run time: do NOT substitute silently.
  Record lane outage, and only a preregistered fallback (procedural
  single-lane with amended claim) may proceed, as a separate commit.

Auditor lane: session lane (muse-spark), read-only verification.

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

## Identity prereg (per lane; frozen — see identity.py check_against_prereg)

Model identity is established PROVIDER-SIDE per call: the runner persists
`identity.json` from the REAL provider response (echoed model id, provider
response id, created, params actually sent) before any execution, and
refuses the run when the echo is missing or violates the frozen entry
below. Echoed ids are the gateway-facing requested ids (router9/kenari
answer OpenAI-compatible chat; kenari's free tier may strip the `:free`
plan suffix). A first observed live echo OUTSIDE these patterns is a
prereg-amendment commit (tighten loop) — never a silent substitution.

Item-3 hardening (audit round 2): the provider response/request id is
REQUIRED (nonempty — our OpenAI-chat lanes always supply one) and the
identity record binds the exact `request_body_sha256` from the usage
receipt plus the complete explicit generation-param set
(`generation_params`). The identity↔receipt binding is cross-verified in
the model-call chain link and the admissibility gate: altering the model
or any request param on either side after the call fails both.

| lane | endpoint (base) | requested_id | family | acceptable_echoed_ids |
|------|-----------------|--------------|--------|------------------------|
| P    | https://api.router9.com/v1 | minimax-m3 | MiniMax | minimax-m3 |
| Q    | https://kenari.id/v1 | agnes-2-0-flash:free | Kenari-Agnes | agnes-2-0-flash:free, agnes-2-0-flash |

## Usage adapter prereg (per lane; frozen — see usage.py PROVIDER_NORMALIZERS)

Normalization is part of call capture: every recorded call declares the
lane's provider-bound v2 adapter id below, the runner writes the immutable
`call-<id>.normalized.json` artifact immediately, and the model-call chain
link binds its hash + derived metrics. Historical H1 harness-validation
receipts stay on the superseded v1 id (`openai-chat-total-input-v1`); new
calls MUST declare the v2 id — a mismatch fails closed.

| lane | normalizer_id | bound gateway model | supersedes |
|------|---------------|---------------------|------------|
| P    | router9-openai-chat-v2 | minimax-m3 (MiniMax via router9) | openai-chat-total-input-v1 |
| Q    | kenari-openai-chat-v2 | agnes-2-0-flash:free (Kenari-Agnes via kenari) | openai-chat-total-input-v1 |

Auditor lane: session lane (muse-spark), read-only verification.

# Scale-up spec — preregistered 2026-09-17 (FROZEN at commit)

Ruling executed: the reusable machinery (registry, x2-ship gate, eval receipts,
weekly sweep, traces) means new capabilities no longer need proportional new
architecture. The next push is **quantity under the same discipline**, with
pre-declared measurement gates instead of preemptive redesign.

## Curve

- **Now:** 16 capabilities.
- **Jump 1: → ~30.** No new machinery. Every add follows the admission
  checklist (templates/capability-scaffold.md). Adds come from real work only
  (a capability is a thing already proven twice in practice, never a slot
  filled to hit a number).
- **Jump 2: → ~100.** Only after the Jump-1 gate review (below) is written up.
- **Beyond:** GPT's ruling stands — measure what breaks at each jump; do not
  design for 300 now.

## Admission checklist (what every new capability must have)

1. **Contract** — `capabilities/<id>/README.md`: the task contexts it covers,
   and at least one context it explicitly does NOT cover.
2. **Gates** — `capabilities/<id>/EVAL.json`: ≥2 gates, deterministic preferred
   over llm-judged; each gate states its check.
3. **Attack case** — one named false-pass mode and how the gates catch it.
   (Same discipline as the Dell repo's attack rounds, scoped to the cell.)
4. **Execution adapter** — how it actually runs (script / skill / workflow /
   runbook path), so another agent can fire it without tribal knowledge.
5. **Lineage** — `rcos propose --lineage` records where it came from.
6. **x2 real ships with receipts** → promote. Honesty rule unchanged: a
   blocked verdict is a good outcome; no eval without fresh task evidence.

## Trace discipline (the router dataset starts now)

Every `rcos eval-submit` writes an append-only trace line
(`traces/traces.jsonl`, schema `rcos-trace/1`). When the context is known,
pass `--context "<what the task actually was>"` and `--source reuse|synthesize`
(did we reuse this capability or build new?). Trace context is ALSO the
selection-ambiguity log: if two capabilities plausibly applied and the choice
wasn't obvious, prefix the context with `AMBIGUOUS:` and name the runner-up.

Rules: traces are never rewritten or pruned; backfilled rows are flagged
`backfilled:true` and are **never** used for router training; the learnable
fraction = non-backfilled rows with non-null context.

## Jump-1 gate review (run when the registry hits ~30; write it up before Jump 2)

Pre-declared signals, computed from registry + traces only:

- **G1 Selection ambiguity** — share of new traces with `AMBIGUOUS:` context.
  >20% ⇒ start v3 router work (see below). Otherwise the LLM-over-descriptions
  approach is still fine and nothing gets built.
- **G2 Eval economics** — summed `--seconds` per week and whether the sweep
  can still cover all candidates. If not, coverage prioritizes capabilities
  touched by real work that week (eval follows use).
- **G3 Coverage spread** — no capability goes >90 days without an eval while
  others are evaluated weekly (audit already warns stale; this is the
  portfolio-level version).
- **G4 Reuse-vs-synthesize** — capabilities with `reuse_count == 0` after 60
  days of eligibility go to weekly-sweep review for retirement or merge.
- **G5 Drift** — a promoted capability whose last 2 traces are fix/blocked
  gets a red-team round before its next reuse (audit's decay warning made
  actionable).

## v3 preregistration (router learning)

Do not start before: (a) Jump-1 gate review exists, and (b) ≥200 live traces
with non-null context. When it starts, the router learns capability-selection
from the trace corpus; the existing audit/decay/gate machinery stays the trust
layer. FlowRouter remains the *transport* for capabilities between cells per
its frozen rule (it moves evidence of trust, never trust itself) — the
RCOS↔FlowRouter adapter is the already-frozen M3/v0.2 plan, unchanged by this
spec. No learned router ever writes to the registry directly.

## Explicit non-goals during Jump 1

- No routing architecture of any kind (G1 data decides, not intuition).
- No registry schema changes; additive files only (traces/, templates/).
- No new epochs/slices on the Dell RCOS repo while PR #19 is open.
- No capability added "to hit 30" without two real ships.

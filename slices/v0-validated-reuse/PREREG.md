# Vertical Slice 0: Validated Capability Reuse — PRE-REGISTRATION

> Audit disclosure: this protocol was frozen locally before any run
> (fixtures + checker + this file written first, hashes recorded below),
> but the public commit occurred post-run alongside results. Treat as
> "protocol frozen locally before execution," NOT externally proven
> preregistration. Slice 1 fixes this permanently (prereg pushed first,
> runs committed second).

Frozen BEFORE any run. Task 3 is held out: the capability builder never sees
it until after promotion, and this file (plus task hashes) proves it.

## Milestone name (deliberately NOT "compounding")

**Validated Capability Reuse**: a system converts experience from earlier tasks
into a separately persisted, evaluated capability that is causally retrieved
and reused on an unseen task, independently of conversational memory.

## Task family: invoice record normalization

Structural dimensions varied (the "same class" definition — objective, not felt):
format (CSV vs JSON vs TSV), field naming, field ordering, missing optional
fields, irrelevant extra fields, output constraints (fixed canonical schema).

- **T1** (`t1-csv`): CSV invoice, headers `inv_id,inv_date,total_usd,currency`
  + line items as `sku,qty,unit_usd` rows after a blank line. No capability
  exists → fresh solve → candidate on ship.
- **T2** (`t2-json`): JSON invoice, different keys (`id`, `issued`,
  `lines[{code,n,price_cents}]`, `cur` optional, plus irrelevant `notes`).
  Fresh session → candidate succeeds again → PROMOTE (two-ship pilot rule).
- **T3** (`t3-tsv`, HELD OUT): TSV invoice, tab-separated, yet another naming
  (`INVOICE`, `DAY`, `AMOUNT_CENTS`, `CCY` + `ITEMS` as `sku|qty|unit_cents,`
  comma-separated groups) plus junk columns. Unseen until after promotion.

Canonical output schema (all tasks): 
`{invoice_id: str, date: YYYY-MM-DD, total_cents: int, currency: str,
  line_items: [{sku, qty, unit_cents}]}`. Totals must verify
(sum(qty*unit_cents) == total_cents) or the run fails.

## Capability-claim boundary (what "reuse" is allowed to mean here)

The promoted capability is a normalization ENGINE (canonical mapping +
validation + totals verification), not a memo of one file. T3 may require a
small format-specific field map composed at reuse time — that is logged as
`composed`, not `executed`, and still counts as reuse ONLY if the engine
executes and its output is consumed (see trace rules).

## Controls (both mandatory)

- **Fresh-solve control**: T3 executed with the registry disabled, from a
  fresh session. Same inputs, same acceptance, same accounting.
- **Negative control**: the registry also contains `date-reformat-v1`, a
  plausible-but-wrong capability (reformats dates, normalizes nothing). The
  router must consider and reject it with a logged reason. Retrieval that
  cannot reject is not retrieval.

## History isolation

Each task runs in a fresh workdir containing ONLY its task inputs plus (T3
treatment only) the promoted capability directory. No T1/T2 transcripts,
solutions, or scratch carry over. Violation = invalid run.

## Freeze record (fixtures generated 2026-09-07, before any run)

- `c7162e25…5df21f  tasks/t1-csv/input.csv`
- `401af332…3da0ffbd2  tasks/t2-json/input.json`
- `8c09e575…27b6c36a8  tasks/t3-tsv/input.tsv`

## Acceptance (mechanical, no judgment)

Per-task `EVAL.json` + checker script. Task IDs, inputs, and checkers are
frozen in this commit; fixtures carry sha256 recorded below at freeze time.

## Anti-blinding limitation (declared, not hidden)

Solver attempts in all arms are authored by the same human (no separate
agent available for this slice). Mitigations: T3 held out by hash, acceptance
fully mechanical, control arm executed BEFORE treatment arm, all artifacts
committed. A multi-agent replication is future work.

## Decision rule

Slice ships iff: T1 ship → candidate; T2 ship → promote; T3-treatment reuses
(engine executed, output consumed, negative control rejected) and ships;
T3-control measured for comparison; trace proves the reuse claim. If T3 can be
explained as caching (identical-task reuse), the family — not the claim —
failed, and the slice does not ship.

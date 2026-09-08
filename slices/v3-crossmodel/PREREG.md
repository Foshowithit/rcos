# Slice 3: Cross-Model Artifact Transfer + Measured Benefit — PRE-REGISTRATION

Committed + pushed BEFORE any builder call, capability, or run exists.
Lane gate verified 2026-09-08T00:1xZ (both 200 with real completions).

## Question under test

Can model B's acquired executable knowledge measurably improve independent
model C on held-out tasks — same C, same budgets — relative to C solving
from scratch?

## Lane assignments (frozen)

- **B (builder)**: router9 `minimax-m3` (MiniMax family, reasoning content
  verified). Sees training tasks + acceptance contract + capability format.
  Never sees held-outs.
- **C (solver)**: kenari `agnes-2-0-flash:free` (distinct vendor/endpoint;
  self-reported identity recorded at run time, not pre-claimed). Sees
  held-out task + registry artifact + interface only. No B transcripts.
- **Operator (scheduler)**: session lane. Mechanical only — launch frozen
  calls, save raw outputs byte-identical, run code arrivals verbatim, commit
  receipts. FORBIDDEN: semantic edits to B's capability, explaining B to C,
  repairing C adapters, judgment retries. Any mechanical packaging fix is
  logged with diff.
- **D (auditor)**: external (GPT) + this checklist, post-hoc, read-only.

## Task family: shipment-manifest normalization (new domain)

Canonical: `{shipment_id: str, origin: str, destination: str,
weight_kg: number, items: [{sku, qty}]}`. Totals: sum(qty) recorded;
weight_kg > 0 required.

- **T1** (`s1-csv`): CSV, headers `ship_id,from,to,weight_kg` + `items` as
  `sku:qty;...` second section.
- **T2** (`s2-json`): JSON, different keys (`id`, `route{src,dst}`,
  `mass_kg`, `contents[{code,n}]`), missing `weight_kg` on one variant?
  No — keep solvable: all fields present, plus junk `notes`.
- **T3a–T3j** (10 held-outs): generator-rotated formats/namings/orderings
  (pipe-delimited, TSV, alt keys, junk columns, reordered sections).
  Sealed by hash below; B never sees them.

## Arms (per held-out, same C, fresh context, randomized order)

1. **correct**: B's frozen artifact + interface.
2. **forced-wrong**: Slice-2 `extract-incident-v1` engine (plausible —
   both are normalizers; wrong domain), executed and measured.
3. **disabled**: no registry. C solves from scratch (may write code; the
   scheduler runs arrivals verbatim).

Fixed budgets per arm per task: max 3 C model calls, timeout 120s each
call. Metrics per arm per task: success, input/output tokens (API
reported), model calls used, wall time, human interventions (=0 by
construction; any repair voids the run and is logged).

## Freeze record (fixtures + checker + sealed truth, zero runs exist)

- `88d46be1748e  tasks/check.py`
- `619b61f50492  tasks/h01/input.psv`
- `1171d768ac4a  tasks/h02/input.tsv`
- `b68003fdad1f  tasks/h03/input.json`
- `9c3d9abf4c2f  tasks/h04/input.csv`
- `5b19a3d4801e  tasks/h05/input.env`
- `5d6957294448  tasks/h06/input.psv`
- `46ab40dd6fc2  tasks/h07/input.json`
- `3115c82d2afc  tasks/h08/input.tsv`
- `1402248ea078  tasks/h09/input.psv`
- `eedffcc4c94b  tasks/h10/input.json`
- `404a7bf43079  tasks/s1-csv/input.csv`
- `604edc4502eb  tasks/s2-json/input.json`
- `ffd46cc988d2  tasks/truth.json`

## Decision rule

Claim supported iff, across held-outs: correct-arm success ≥ disabled-arm
success AND correct-arm mean tokens+calls < disabled-arm AND forced-wrong
fails (eval rejects) — with per-task paired table committed. Directional
relationships pre-registered; no p-values claimed at n=10 (plot + table,
honest scale).

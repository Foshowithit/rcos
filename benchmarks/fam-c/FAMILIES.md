# Fam-C instance freeze index

Six families, T0–T4 each (30 tasks). Every family: fixtures + prompt.md
per task, sealed truth.json, mechanical checker (exit 0/1/2),
per-task VISIBLE.md seal manifest, DESIGN-T4.md documenting the flipped
invariant (auditor-facing, never agent-visible). All T4 nulls proven
discriminating (blind misapplication fails, correct output ships)
before this freeze.

- fam01 structured-data normalization (CSV/JSON/pipe/env; T4 aggregate row)
- fam02 paginated acquisition (next-tokens, fault manifests, fetch harness;
  T4 overlapping windows under declared latest-wins policy)
- fam03 dedup/windowing (identity rules per surface; T4 retry transitions)
- fam04 DAG validation (4 schema shapes; topological order accepted;
  T4 cycle must be reported)
- fam05 manifest verification (4 manifest formats; T4 out-of-contract
  v2/remote entries listed under normal unverified field)
- fam06 reconciliation (4 source-shape pairs; T4 unit-mismatch listed
  under normal unreconcilable field)

Truth values were independently re-derived from fixtures during
construction (not copied from generators). No runs exist against these
instances as of this commit.

## v2 supersession notes (audit-driven, pre-run)

- T2/T3 scaled above script-scale in every family (8–12 records, 6–8
  node graphs, 4–5 file manifests); truths re-derived from fixtures.
- fam05 T2/T3 rebuilt with fully distinct content (T1 replay fails
  mechanically on both).
- fam02 T2 uses a genuinely different envelope (nested data/paging,
  product/count keys); old-shape readers fail on it.
- All six T4s rebuilt as true K-inapplicability nulls with neutral
  prompts and per-family K preconditions (K.md); rejection lives in the
  run trace via the reuse-field split, never in output shapes. All blind
  misapplications proven to fail.
- Clustering caveat (acknowledged): fam01/02/03/05/06 cluster around
  small structured-data transforms; fam04 is the algorithmic outlier.
  Do NOT treat 4-of-6 as four independent confirmations. Mitigations:
  leave-one-family-out rule, fam04 as independence anchor, and this
  limitation rides in every reported headline.

## Scale characterization (honest boundary)

T2/T3 instances are larger than slice-scale (8–12 records, 6–8 node
graphs, multi-file manifests) but remain small-capability transfer
tasks, not large-workflow reuse: row counts alone do not constitute
§6-scale nontrivial subsystems. This freeze is valid for specificity,
reuse-mechanics, and pilot efficiency signal; any compounding claim
beyond pilot grade requires harder task regimes in later series.

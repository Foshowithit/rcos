# Fam-C instance freeze index

Six families, T0–T4 each (30 tasks). Every family: fixtures + prompt.md
per task, sealed truth.json, mechanical checker (exit 0/1/2), T4NOTE.md
documenting the flipped invariant. All T4 nulls proven discriminating
(blind misapplication fails, correct output ships) before this freeze.

- fam01 structured-data normalization (CSV/JSON/pipe/env; T4 aggregate row)
- fam02 paginated acquisition (next-tokens, fault manifests, fetch harness;
  T4 overlapping windows, latest-wins)
- fam03 dedup/windowing (identity rules per surface; T4 state transitions)
- fam04 DAG validation (4 schema shapes; topological order accepted;
  T4 cycle must be reported)
- fam05 manifest verification (4 manifest formats; T4 tampered entry)
- fam06 reconciliation (4 source-shape pairs; T4 amount conflict)

Truth values were independently re-derived from fixtures during
construction (not copied from generators). No runs exist against these
instances as of this commit.

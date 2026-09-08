# fam01 T4 near-neighbor null

Surface: same CSV shape as T0 (id/name/amount_usd/tags).
Flipped invariant: the trailing SUMMARY row is an aggregate, NOT a
record. A router that fires the family capability blindly emits 3
records (including a bogus SUMMARY record or a wrong total); correct
behavior emits exactly the 2 real records. Checker asserts exact
canonical output, so blind reuse fails and abstain-and-solve passes.

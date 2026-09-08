# fam02 T4 near-neighbor null

Surface: same paged shape as T0–T3. Flipped invariant: page t2 repeats
id `b` with an updated value (22, not 2). Blind dedup-by-first-seen (or
any cache that never refreshes) yields b=2 and fails; correct behavior
takes latest-wins. Checker asserts b=22.

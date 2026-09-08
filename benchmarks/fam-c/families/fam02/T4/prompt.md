# fam02-T4 — overlapping windows (near-neighbor null)

Same protocol over `pages/t1.json…`, but windows OVERLAP: an id may
reappear with a NEWER value. The merged map must carry the LATEST value
per id (first-seen caching is wrong here). Log in `retry.log`, merge
into `OUTPUT.json`.

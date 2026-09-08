# fam02-T2 — paginated acquisition, enveloped pages

Pages here are ENVELOPES: `{"data": [...], "paging": {"next": ...}}`
with item keys `product`/`count` (not `items`/`k`/`v`/`next`).
Follow `paging.next` until null, retry transient faults via `fetch.py`,
log in `retry.log`, merge `{k: v}` into `OUTPUT.json`.

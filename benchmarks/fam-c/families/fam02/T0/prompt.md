# fam02-T0 — follow next-page tokens to exhaustion

Starting at `pages/p1.json`, follow each page's `next` field until null.
Merge all `items` (`{k, v}`) into one JSON object in `OUTPUT.json`.
Read pages ONLY through `fetch.py` (`fetch.py <taskdir> <counterdir> <page>`);
log every attempt as `<page> <attempt> ok|fail` in `retry.log`.

# fam02-T1 — paginated acquisition with transient faults

Same as T0 over `pages/q1.json…`, but pages may fail transiently
(`faults.json` declares fail counts). Retry failed reads (max 5 attempts
per page) until success; a missing page after retries is a failure.
Log every attempt in `retry.log`. Merge into `OUTPUT.json`.

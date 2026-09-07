# r14 — fix-csv

`data.csv` has ragged rows (2, 4, and 3 fields). Normalize every row to exactly 3 fields: truncate extras, pad missing with empty strings. Header untouched.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

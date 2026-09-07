# r05 — validate-records

Given `recs.json` (a list of objects), write `report.txt` with one line per object: `<index>: valid` if it has string `id` and numeric `v`, else `<index>: invalid`.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

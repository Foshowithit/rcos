# r01 — csv-to-jsonl

Given `input.csv` with header `name,age` and rows `ada,36` and `grace,85`, produce `out.jsonl` with one JSON object per row, keys `name` (string) and `age` (number).

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

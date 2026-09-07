# r09 — dep-edges

Given `manifest.txt` lines `A: B C` (module: deps), write `edges.txt` with one `A->B` line per edge, sorted.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

# r10 — secret-scan

In `repo/`, find lines matching `sk-live-[A-Za-z0-9]+` and write `findings.txt` as `<relpath>:<lineno>:<match>`.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

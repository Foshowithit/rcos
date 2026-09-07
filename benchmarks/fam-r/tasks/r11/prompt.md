# r11 — fix-json

`broken.json` has a trailing comma and will not parse. Fix it in place so `python3 -m json.tool` succeeds with unchanged data.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

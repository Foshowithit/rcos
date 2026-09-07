# r13 — fix-frontmatter

`page.md` has broken YAML frontmatter (missing closing `---`). Fix it so the body `Hello` remains and frontmatter parses as `title: Hi`.

---
*Scaffold note: `check.sh` currently runs the reference solution inline to validate the task definition itself. The eval harness will substitute agent output for the reference solution without changing the assertions.*

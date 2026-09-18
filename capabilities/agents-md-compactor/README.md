# AGENTS.md compactor

Registry id: `agents-md-compactor` · kind: `script`

Compacts a shared cross-agent memory file (the `~/.agents/AGENTS.md` class)
without losing meaning: the region before `## Changelog` and the `- ⚠ *`
policy lines are never rewritten, an entry that carries a bold headline keeps
it, compaction is idempotent, and a dated backup is written before the file is
touched.

## Contract
- Covers: a single memory file in the shared-memory format, with an
  `archive/` directory next to it for dated backups.
- Does NOT cover: files outside that format; choosing *what* to compact (the
  tool compacts the changelog region by its own stated policy, nothing else).
- Implementation: `capabilities/agents-md-compactor/tool/compact_agents_md.py`,
  a frozen copy of `~/.agents/tools/compact_agents_md.py` taken 2026-09-17
  (sha256 `0955ad78cd4808dae85c5b74818839c2f1e1f5f4f4dfccdd0fa5a7cce85cc1e9`).
  The pin is checked by the evaluation, not by this directory: the eval freezes
  the same bytes as a fixture and its `frozen-tool` gate fails if the bytes this
  adapter actually executed differ from them.
- Adapter: `capabilities/agents-md-compactor/adapter/run.js`, invoked by the
  RCOS invocation kernel (`rcos run agents-md-compactor --input <file>`).
  It OBSERVES — three passes over the fixture (normal, idempotence, and with the
  archive directory removed) recording raw facts. It forms no opinion; every
  pass/fail decision belongs to the gates.

## Known state
This capability currently **fails** its own evaluation on `semantic-survival`:
a bold-headline entry in the changelog region does not keep its headline through
compaction. That is a real finding about the tool, not about the harness — the
capability executes perfectly and still evaluates FIX.

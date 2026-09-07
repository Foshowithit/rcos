# Fam-N — novelty / generalization (STAGED TODO)

**Status:** schema defined, no tasks yet. Fam-N tests whether promoted
capabilities *transfer* — the difference between a library and a junk drawer.

## Planned design

- **Tasks:** held out from the Fam-R/C distribution (different tools, formats,
  failure modes). Proposed only after Fam-C series 1 completes, to avoid
  leaking the test set into registry capabilities.
- **Treatment:** router with the frozen post-Fam-C registry.
  **Control:** same router with the registry disabled.
- **Scored:** ship rate + cost on held-out tasks; plus a harm check (reused
  capabilities that actively hurt vs control are retirement candidates).

## TODO

- [ ] Fam-C series 1 completes → freeze registry snapshot id
- [ ] Draft 10 held-out tasks (prompt + checker + EVAL.json each)
- [ ] Pre-register transfer metric + harm threshold in `paper/`

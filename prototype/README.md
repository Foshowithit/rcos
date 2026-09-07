# prototype/ — reference implementation interfaces

This directory **houses** the RCOS v1 prototype and the Fam-R pilot — it does
not reimplement them. The sibling in-flight work (capability registry,
promotion gate requiring eval-gate `ship` twice, router reuse logging,
per-task metrics) plugs in here file-by-file.

## Plug-in map

| Sibling artifact | Lands at | Status |
|---|---|---|
| `capability-registry.json` (live registry) | `prototype/capability-registry.json` | TODO — schema in `capability-registry.schema.json` |
| Promotion-gate wiring | `prototype/promotion-gate.md` (spec) + registry entries | Spec written, live entries TODO |
| Router reuse hook | `prototype/router-reuse-hook.md` (spec) | Spec written, hook code TODO |
| Per-task metrics logger | `prototype/task-logger.md` (spec) | Spec written, logger code TODO |

## Rules for landing the pilot

1. Validate the live `capability-registry.json` against
   `capability-registry.schema.json` before every commit
   (`python3 ../benchmarks/schema_check.py` covers it).
2. Keep the pilot's history intact: land it as its own commit(s), then wire-up
   commits on top — do not squash sibling work into scaffold commits.
3. No secrets, no absolute user paths, no vault references in landed files.
   Scrub before committing.
4. If the pilot hasn't landed yet, everything below is interface + TODO — that
   is intentional. Do not invent a parallel implementation.

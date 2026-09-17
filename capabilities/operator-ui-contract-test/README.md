# DSH plugin contract test pattern

Registry id: `operator-ui-contract-test` · kind: `script`

`scripts/check.js` in dsh-operator-ui: name alignment, read-only-route
lint, repo hygiene — runnable contract test, required before every push.
Contract drift is how plugins die; the check runs before the push, not
after the breakage.

Lineage: `dsh-operator-ui/scripts/check.js` + AGENTS.md, live since v0.1.1.

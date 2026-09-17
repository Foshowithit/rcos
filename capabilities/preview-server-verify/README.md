# Preview Server Verify

Registry id: `preview-server-verify` · kind: `script`

## Contract

**Covers.** Proving that a local HTTP server is serving the bytes you think
it is, on an ephemeral 127.0.0.1 port, and then actually letting go of the
port. `capabilities/preview-server-verify/adapter/serve_verify.py`: serves
`<docroot>` on an ephemeral loopback port, GETs `<relpath>`, and asserts
(1) HTTP 200, (2) served sha256 == docroot disk sha256 (transport check),
(3) served sha256 == `--expect-sha256 <hex>` when given — the pin computed at
authoring time, which is what catches a stale server. Teardown:
`shutdown()` + `server_close()`, then assert the port refuses connections.
Exit codes: 0 pass, 3 gate-fail, 4 no-start.

**Does NOT cover.** Rendering (that's `browser-verify-artifacts`). Public
interfaces — loopback only. Multi-route servers (single relpath per call).

**Adapter pointer.** `capabilities/preview-server-verify/adapter/serve_verify.py`.

## Gates

| id | kind | check |
|----|------|-------|
| serves | deterministic | HTTP 200 on `<relpath>` from the ephemeral loopback server |
| bytes-match | deterministic | served sha256 == docroot disk sha256 AND == `--expect-sha256` pin (STALE_OR_WRONG_BYTES otherwise) |
| port-released | deterministic | after teardown the same port refuses a connection (server_close required) |

## Attack case

**The unfailable hash gate.** Comparing served bytes against the disk copy of
the SAME docroot cannot fail when the whole docroot is stale — both sides
match (attack run: the gate PASSED a directory that was not the deliverable).
Fix recorded in the contract: the expected sha256 is pinned at authoring time
(`--expect-sha256`) and compared against the served bytes; the stale-dir
attack now exits 3 with STALE_OR_WRONG_BYTES. Second, self-inflicted: the
teardown gate caught its own adapter bug — `shutdown()` stops the loop but
leaves the socket bound; `server_close()` is required (eval-1 run-1 FAIL,
fixed same pass).

## Lineage

zcode memory `local-preview-port-split-brain` (2 http.servers split one port
by address family; stale snapshot answered IPv4 — hash the response). Built
09-17 during the admission campaign; consumers: rcos dashboard serve checks,
scene capture rigs.

## Eval log

- 09-17 eval-1 (traced): dashboard.html (12499 bytes) — run-1 FAIL on port
  teardown (adapter bug, fixed), run-2 SERVE_VERIFY_PASS.
- 09-17 eval-2 (traced): scene_v2.html via a second docroot — PASS.
- 09-17 attack (traced): stale-dir swap — run-1 exposed the unfailable gate
  (attack PASSED when it should fail), run-2 after the `--expect-sha256` fix:
  exit 3 STALE_OR_WRONG_BYTES. Honest fix/fix/ship history.

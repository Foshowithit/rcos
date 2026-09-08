# Slice 2: Replication Under Procedural Barriers — PRE-REGISTRATION

Committed + pushed BEFORE any solver, capability, or run exists.

## Lane decision (operator-ordered, claim-bounded)

All cognitive work runs on the session lane
(`opencode-go-r / muse-spark-1.3-contributor`, per-request `xhigh` where
the harness accepts it; support undeclared per EFFORT.md — if the lane
rejects it, provider default applies and is recorded here). Consequence:
this replication tests PROCEDURAL separation (role barriers, sealed
artifacts, fresh contexts), NOT cross-model portability. GPT's decision
gate resolves to the NO branch by operator choice. The cross-model
variant (minimax builder vs agnes solver, both probed live) stays future
work; lanes verified 2026-09-07 and recorded in-sequence below for it.

## Question under test

Do Slice-0/1 results survive when every anti-cheating control is applied
simultaneously: prereg-pushed-first, sealed T3, fresh workdirs, forced-wrong
measured arm, router rejection logging, AND role information barriers with
a B-artifact freeze that C cannot see behind?

## Task family: log-incident summarization (NOT invoices, NOT configs)

Structural dimensions: format (space-delimited app logs vs JSON-lines vs
syslog-ish), key/column naming, timestamp shape, missing optionals, junk
lines, severity spellings.

- **T1** (`l1-app`): `TS LEVEL SERVICE message...` lines, ISO timestamps.
- **T2** (`l2-jsonl`): JSON-lines, different keys, nested `ctx`, missing
  `severity` on some lines (default INFO), junk heartbeat lines.
- **T3** (`l3-syslog`, HELD OUT): syslog-ish `Mon DD HH:MM:SS host
  svc[pid]: LEVEL: msg`, yet another naming + junk kernel lines.

Canonical schema: `{incident_id: str, severity: worst-seen,
service: str, first_seen: iso, last_seen: iso, event_count: int,
signatures: [distinct normalized message shapes]}`. Severity order:
DEBUG < INFO < WARN < ERROR < FATAL. Timestamps normalized to ISO UTC
(2026 dates; syslog year assumed 2026).

## Capability-claim boundary

Reusable: incident grouping (service+hour window) + severity folding +
signature normalization + canonical shaping. Per-format parsing is composed
adapter work. Same engine/adapter split as Slices 0–1.

## Arms (T3, fresh workdirs, mechanical grading)

1. **correct**: promoted capability executes, output consumed → expect ship.
2. **forced-wrong**: Slice-1 `normalize-config-v1` forced (plausible —
   both are "normalizers") → expect measured FAIL.
3. **disabled**: fresh solve baseline.

## Role barriers (procedural)

A=author (this prereg, pushed first). B=builder (T1/T2 + fixture/task
texts only; T3 hash-known but never opened). C=solver (T3 input +
registry + B's FROZEN artifact files only — no B transcripts, notes, or
T1/T2 conversations). D=auditor (this checklist re-run post-hoc against
the public history). One operator throughout — the barrier is file-level
discipline (C workdir contains only whitelisted inputs), committed as-is.

## Freeze record (fixtures + checker written, zero runs exist)

- `ad9adaee…3eaff10  tasks/l1-app/app.log`
- `505ad0e0…f83f9025f  tasks/l2-jsonl/events.jsonl`
- `d40ae506…38cc25aa7  tasks/l3-syslog/syslog.txt`
- checker `tasks/check.py` (junk rule: heartbeats + non-target-service
  lines excluded; truth values frozen in the task definitions above)

## Decision rule

Ship iff: prereg predates runs publicly → T1/T2 ship → promote → arm 1
ships via executed+consumed capability → arm 2 fails as predicted → arm 3
measured → trace proves all three → no barrier file violated (audit by
`git log` + workdir manifests committed per run).

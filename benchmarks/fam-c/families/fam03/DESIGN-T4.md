# fam03 T4 design (auditor-facing; agents never see this file)

Null mechanism: one byte-identical repeat pair (CREATED retry) that is
nonetheless two distinct events. ANY dedup rule — full-line, id-based,
or otherwise — undercounts (4/4/1) and fails; only transition counting
(5/5/0) passes. Rejection of K is recorded in the run trace, never in
the output shape.

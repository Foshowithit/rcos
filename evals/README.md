# evals/

One directory per evaluation run: `<run-id>/RECEIPT.json`.

A RECEIPT is the sole success authority for that run — verdict is `ship`,
`fix`, or `blocked`, plus the evidence paths that back it. No prose claims
count; only a RECEIPT recorded here (and logged into the registry via
`rcos eval-submit`) moves a capability toward promotion.

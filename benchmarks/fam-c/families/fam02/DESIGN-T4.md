# fam02 T4 design (auditor-facing; agents never see this file)

Null mechanism: t2 repeats id `b` with a new value. Blind first-wins
caching (the K behavior under disjoint-pages assumption) yields b=2
and fails. The task ships a declared `POLICY` file (latest-wins) that
a correct solver follows to b=22. Rejection of K is recorded in the
run trace, never in the output shape.

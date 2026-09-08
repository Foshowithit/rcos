# fam06 T4 design (auditor-facing; agents never see this file)

Null mechanism: sources use different units (USD vs cents) with no
declared conversion, so same-basis comparison is impossible. Forcing a
numeric verdict (match X, conflict Y 60-vs-6000) is wrong in both
directions; correct output lists both ids under the normal
`unreconcilable` field. Rejection of K is recorded in the run trace,
never in a special output shape.

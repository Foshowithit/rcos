# fam01 T4 design (auditor-facing; agents never see this file)

Null mechanism: the trailing SUMMARY row is an aggregate, not a record.
A solver applying record-normalization blindly emits 3 records and fails;
correct output is the 2 real records. K-inapplicability is proven by the
blind failure, not by any abstention flag: rejection is recorded in the
run trace (reuse_rejected=true, capability_invoked=false), never in the
output shape (see VISIBLE.md — this file is not agent-visible).

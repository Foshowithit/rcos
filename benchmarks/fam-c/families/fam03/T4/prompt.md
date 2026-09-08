# fam03-T4 — count events with repeated ids
Count lines in `events.txt`. Emit `OUTPUT.json`:
`{total, unique, removed}`. If the file cannot be counted as repeats
of identical events, emit `{"abstained": true, "reason": "...",
"answer": ...}` with your best independent answer instead.

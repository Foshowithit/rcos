# fam05 T4 near-neighbor null (redesigned per audit)
Surface: same manifest shape. Flipped invariant: v2 schema with BLAKE3
hashes over REMOTE s3:// objects — outside K's contract (local files,
sha256). Correct = abstain with the entries listed as unverified.
A v1-style verification report (or fabricated local hashes) fails.
Prior tampered-manifest design removed: tamper detection is a POSITIVE
use of this K, not a null.

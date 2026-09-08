# fam05 capability contract (K)

Reusable core: manifest verification — compare each listed file's
actual size and sha256 against the manifest, report ok/bad.

PRECONDITIONS (all must hold for K to be applicable):
1. Manifest schema is v1 (local paths + sizes + sha256).
2. Listed files are local and readable.

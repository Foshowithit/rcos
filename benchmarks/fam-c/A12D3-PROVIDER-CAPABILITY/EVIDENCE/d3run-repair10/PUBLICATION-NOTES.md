# d3run-repair10 — publication notes

**These are the exact bytes the successful checker graded.** Nothing was regenerated,
normalized, reformatted or cleaned for publication. Absolute paths whose run root was
`/tmp/d3gen/d3run-repair10` are left as they are; timestamps that differ across files
are left as they are.

The one exception, stated here rather than done silently:

**7 zero-byte UNIX sockets were not published.** They are `mock-boundary.sock` in each
of the six arm directories and `broker-peer.sock` in `arm-D3-E`:

```
arm-D3-A/mock-boundary.sock
arm-D3-B/mock-boundary.sock
arm-D3-C/mock-boundary.sock
arm-D3-D/mock-boundary.sock
arm-D3-E/mock-boundary.sock
arm-D3-E/broker-peer.sock
arm-D3-X/mock-boundary.sock
```

They are excluded for two reasons, both checkable:

1. **A socket is not a byte stream.** `git` cannot store one, and there is nothing in
   one to store: each is 0 bytes.
2. **The checker never opens them.** `a12d3_d3_independent_checker.py` contains no
   reference to `.sock` at all — it reads the ledgers, the sealed prefixes, the
   manifests, the traces, the marker files, the precommits, the measurements, the
   receipts and the identity documents. The sockets are the live endpoints the gate and
   the mock were listening on during the run; their evidence is the ledger and receive
   records that name them, and those are all published.

`RUN-EVIDENCE.sha256` therefore covers **248 regular files**, which is every regular
file that existed in the run directory. Regenerate with:

```
cd EVIDENCE/d3run-repair10 && sha256sum -c RUN-EVIDENCE.sha256
```

Manifest digest: `490fcaeb0868c1015887cf5f93faf075873f683db8e67f4901bd293c5f17337b`

## Provenance chain

```
frozen source commit   69bae2a4  (the apparatus the gate audited)
repair commit          d72e31ac  (the four BLOCK findings + F1 exact)
andterm fix commit     d6346346  (the missing leg-identity AND term)
                              |
                              v
                     d3run-repair10  (these bytes)
                              |
                              v
                     RUN-EVIDENCE.sha256  (248 entries)
                              |
                              v
                        receipt.json  (harness, ALL_ARMS_MEET_CONTRACT: true)
                              |
                              v
              independent_audit.json  (checker, verdict AGREES, exit 0)
```

The checker that produced `independent_audit.json` is
`sha256 = 2b735a0b9fce165c…`, the same bytes frozen in
`apparatus/SOURCE-FREEZE.sha256` at commit `d6346346`.

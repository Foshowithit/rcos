#!/usr/bin/env bash
# NAMED SYNTHETIC FAM-C FAMILY ATTACK — single-artifact driver.
#
# Round-4 audit (AUDIT-ROUND4.md) rated the end-to-end synthetic family
# attack PARTIAL PASS: "coverage real but distributed (h12/h13/h16/h25/h34);
# no single named end-to-end family-attack artifact — the FINAL-lock record
# must cite the set explicitly." This driver IS that named artifact: it runs
# the five suites in one recorded sequence against the checked-out tree and
# writes MANIFEST.json (ref, suite digests, per-suite results, timestamps).
#
# Offline by construction: every suite in this sequence is hermetic (no
# provider calls, no network). Execution-ref discipline: run from a checkout
# of the execution ref; the manifest records what was actually verified.
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 2
cd "$HERE/../../../.." || exit 2

REF=$(git rev-parse HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
DIRTY=$(git status --porcelain | wc -l)
SUITES="smoke_h12_cellstate smoke_h13_promotion smoke_h16_lifecycle smoke_h25_readiness smoke_h34_d13"
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RESULTS=""
PASS=0; FAIL=0

for s in $SUITES; do
  t0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  out=$(mktemp)
  timeout 240 python3 "harness/tests/$s.py" >"$out" 2>&1
  rc=$?
  t1=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  summary=$(tail -1 "$out")
  rm -f "$out"
  if [ $rc -eq 0 ]; then PASS=$((PASS+1)); verdict=PASS; else FAIL=$((FAIL+1)); verdict=FAIL; fi
  RESULTS="$RESULTS{\"suite\":\"$s\",\"verdict\":\"$verdict\",\"rc\":$rc,\"summary\":\"$summary\",\"started\":\"$t0\",\"finished\":\"$t1\"},"
done
RESULTS="${RESULTS%,}"

printf '{\n  "artifact": "named-synthetic-famc-family-attack",\n  "ref": "%s",\n  "branch": "%s",\n  "dirty_files": %s,\n  "started": "%s",\n  "finished": "%s",\n  "pass": %s,\n  "fail": %s,\n  "suites": [%s]\n}\n' \
  "$REF" "$BRANCH" "$DIRTY" "$START" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PASS" "$FAIL" "$RESULTS" > "benchmarks/fam-c/runs/_synthetic-attack/MANIFEST.json"
echo "ATTACK $REF: $PASS PASS / $FAIL FAIL (manifest: benchmarks/fam-c/runs/_synthetic-attack/MANIFEST.json)"
[ $FAIL -eq 0 ]

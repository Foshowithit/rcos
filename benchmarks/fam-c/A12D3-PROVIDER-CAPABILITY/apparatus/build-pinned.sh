#!/bin/bash
# PINNED REPRODUCIBLE BUILD -- general-seat addition, 2026-09-11.
#
# Why this exists: build.sh:2 hardcodes SRC to the LIVE apparatus directory and
# B to /tmp/d3gen/build.  Both are mutable by a concurrent writer, so a receipt
# produced from them cannot be re-derived: the artifact a run measured can be
# overwritten (and was, at 14:46:15, orphaning an otherwise good battery run).
#
# This variant takes both paths as ARGUMENTS, so a frozen source digest can be
# rebuilt into a fresh directory and compared byte-for-byte.  Everything else --
# the identity x injection matrix, the required-target enumeration, the
# preprocessor axis checks, the honest-leg injection-0 assertions -- is the
# upstream build.sh logic, unmodified.
#
# Usage: build-pinned.sh <source-file> <build-dir> <policy-module-dir>
set -e
SRC="$1"
B="$2"
POLICY_DIR="${3:-$(dirname "$SRC")}"
[ -f "$SRC" ] || { echo "NO SUCH SOURCE: $SRC"; exit 1; }
mkdir -p "$B"
cd "$B"

python3 -c "
import sys; sys.path.insert(0,'$POLICY_DIR')
import a12d3_d3_seccomp_policy as p; p.write_policy_artifacts('$B')" >/dev/null

CF="-O2 -std=c11 -Wall -Wextra -Werror -Wno-unused-function -I$B"

mkleg() {  # $1=binary suffix  $2=identity  $3=injection-num
  printf '#define D3_LEG_ROLE "%s"\n#define D3_LEG_INJECTION %s\n' "$2" "$3" > role_$1.h
  gcc $CF -DD3_ROLE_LEG -DD3_LEG_ROLE_HEADER='"role_'$1'.h"' -o d3-leg-$1 "$SRC"
}

mkleg on     ON                        0
mkleg off    OFF_NOOP                  0
mkleg adapt  ADAPTER_ONLY_PASS_THROUGH 0

mkleg on-prov   ON 1
mkleg on-brok   ON 2
mkleg on-net    ON 3
mkleg on-exec   ON 4

gcc $CF -DD3_ROLE_MODEL_CELL -o d3-model-cell "$SRC"
gcc $CF -DD3_ROLE_ORDER_CELL -o d3-order-cell "$SRC"
gcc $CF -DD3_ROLE_BROKER_PEER  -o d3-broker-peer  "$SRC"

REQUIRED="d3-leg-on d3-leg-off d3-leg-adapt d3-leg-on-prov d3-leg-on-brok d3-leg-on-net d3-leg-on-exec d3-model-cell d3-order-cell d3-broker-peer"
missing=0
for t in $REQUIRED; do
  if [ ! -x "$t" ]; then echo "MISSING TARGET: $t"; missing=1; fi
done
if [ "$missing" -ne 0 ]; then echo "RESULT BUILD FAILED"; exit 1; fi

for pair in "on:ON:0" "off:OFF_NOOP:0" "adapt:ADAPTER_ONLY_PASS_THROUGH:0" \
            "on-prov:ON:1" "on-brok:ON:2" "on-net:ON:3" "on-exec:ON:4"; do
  b=${pair%%:*}; rest=${pair#*:}; want_id=${rest%%:*}; want_inj=${rest##*:}
  got=$(gcc -E -P -DD3_LEG_ROLE_HEADER='"role_'$b'.h"' -I. -x c - <<EOF 2>/dev/null
#include D3_LEG_ROLE_HEADER
D3_LEG_ROLE D3_LEG_INJECTION
EOF
)
  if [ "$got" != "\"$want_id\" $want_inj" ]; then
    echo "AXIS MISMATCH for $b: got [$got] want [\"$want_id\" $want_inj]"; exit 1
  fi
done

for b in on off adapt; do
  inj=$(gcc -E -P -DD3_LEG_ROLE_HEADER='"role_'$b'.h"' -I. -x c - <<EOF 2>/dev/null
#include D3_LEG_ROLE_HEADER
D3_LEG_INJECTION
EOF
)
  if [ "$inj" != "0" ]; then echo "HONEST LEG d3-leg-$b HAS INJECTION $inj"; exit 1; fi
done

echo "RESULT BUILD OK (pinned) -- 10 required targets present from $SRC"
for t in $REQUIRED; do printf '%-22s %s\n' "$t" "$(sha256sum $t | cut -c1-16)"; done

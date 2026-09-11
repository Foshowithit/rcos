#!/bin/sh
set -u
D3_LEG_ROLE="ON" "/tmp/d3gen/build-audit2/d3-leg-on-prov" &
D3_LEG_ROLE="OFF_NOOP" "/tmp/d3gen/build-audit2/d3-leg-off" &
D3_LEG_ROLE="ADAPTER_ONLY_PASS_THROUGH" "/tmp/d3gen/build-audit2/d3-leg-adapt" &
wait

#!/bin/bash
# Falsifiability selftest for hunyuan3d-mlx-local grounding gates.
# Usage: selftest.sh <source-run-dir>
#   <source-run-dir> is a MERGED run view: the contents of runs/<run_id>/
#   with the invocation tree copied in as <source-run-dir>/invocation/
#   (cp -R runs/<id>/. <view>/ && cp -R invocations/<inv>/. <view>/invocation/)
# Each control copies the run dir, mutates ONE thing, and asserts the named
# gate FAILS (exit 3, or 4 for a crash control) for the named reason. Plus a
# no-mutation control asserting the unmutated copy still passes 14/14.
# Location-independent: derives the eval dir and RCOS_HOME from this file.
set -u
SRC="$(cd "${1:?usage: selftest.sh <source-run-dir>}" && pwd)"
EVALDIR="$(cd "$(dirname "$0")/.." && pwd)"
CHECK="$EVALDIR/gates/check.js"
RCOS_HOME="$(cd "$EVALDIR/../.." && pwd)"
BASE=/tmp/hunyuan-selftest
rm -rf "$BASE"; mkdir -p "$BASE"

# A copied run lives at a new absolute path, but its frozen invocation records
# (argv.json cwd, observation argv) still name the source root. Rewrite the
# source-root string inside invocation/ ONLY (never run-level input.json /
# capability-input.json, whose hashes are freeze-checked).
relocate() { # relocate <copy-run-dir>
  grep -rl -F "$SRC" "$1/invocation" | while IFS= read -r f; do
    sed -i '' "s|$SRC|$1|g" "$f"
  done
}
newcopy() { # newcopy <cN>
  mkdir -p "$BASE/$1" && cp -R "$SRC" "$BASE/$1/run" && relocate "$BASE/$1/run"
}

run_gate() { # run_gate <runroot> <gate> [extra env k=v ...]
  local root="$1" gate="$2"; shift 2
  env RCOS_RUN_DIR="$root/run" RCOS_WORK_DIR="$root/run/work" \
      RCOS_EVAL_DIR="$EVALDIR" RCOS_HOME="$RCOS_HOME" \
      RCOS_INVOCATION_DIR="$root/run/invocation" "$@" \
      node "$CHECK" "$gate" 2>&1
  return $?
}

declare -i pass=0 fail=0
expect_fail() { # expect_fail <name> <root> <gate> <want-rc> <reason-grep> [env...]
  local name="$1" root="$2" gate="$3" wantrc="$4" reason="$5"; shift 5
  local out rc
  out=$(run_gate "$root" "$gate" "$@"); rc=$?
  if [ $rc -eq "$wantrc" ] && echo "$out" | grep -q "$reason"; then
    echo "CONTROL PASS $name ($gate bit: $(echo "$out" | grep "$reason" | head -1 | cut -c1-110))"
    pass+=1
  else
    echo "CONTROL FAIL $name (rc=$rc, wanted '$reason')"; echo "$out" | tail -4 | sed 's/^/    /'
    fail+=1
  fi
}

# ---- control 0: unmutated copy stays 14/14 ---------------------------------
newcopy c0
tot=0; bad=0
for g in $(RCOS_RUN_DIR="$BASE/c0/run" RCOS_WORK_DIR="$BASE/c0/run/work" \
           RCOS_EVAL_DIR="$EVALDIR" RCOS_HOME="$RCOS_HOME" \
           RCOS_INVOCATION_DIR="$BASE/c0/run/invocation" node "$CHECK" --list); do
  tot=$((tot+1))
  RCOS_RUN_DIR="$BASE/c0/run" RCOS_WORK_DIR="$BASE/c0/run/work" \
  RCOS_EVAL_DIR="$EVALDIR" RCOS_HOME="$RCOS_HOME" \
  RCOS_INVOCATION_DIR="$BASE/c0/run/invocation" node "$CHECK" "$g" >/dev/null 2>&1 || bad=$((bad+1))
done
if [ "$tot" -eq 14 ] && [ "$bad" -eq 0 ]; then echo "CONTROL PASS c0-unmutated (14/14 on copy)"; pass+=1
else echo "CONTROL FAIL c0-unmutated ($bad/$tot failed)"; fail+=1; fi

# ---- control 1: 3-way consistent artifact tamper -> artifact_identity_pinned
# Flip one byte of shape.glb and re-derive sha/bytes in the observation record
# AND the evidence copy, so only the frozen pin can catch the drift.
newcopy c1
python3 - "$BASE/c1" <<'PY'
import json, sys, pathlib, hashlib
root = pathlib.Path(sys.argv[1])
obs_p = root/'run'/'invocation'/'output.json'
obs = json.loads(obs_p.read_text())
c = next(x for x in obs['cases'] if x['name'].startswith('bearing_product_e2e') and 'repeat' not in x['name'])
f = next(x for x in c['out_files'] if x['path'].endswith('out_shape/shape.glb'))
work = root/'run'/'invocation'/'work'/f['path']
evname = 'case-%s.%s' % (c['name'], f['path'].replace('/', '__'))
ev = root/'run'/'invocation'/'evidence'/evname
b = bytearray(work.read_bytes()); b[1000] ^= 0xFF
data = bytes(b)
f['sha256'] = hashlib.sha256(data).hexdigest()
f['bytes'] = len(data)
work.write_bytes(data); ev.write_bytes(data)
obs_p.write_text(json.dumps(obs, indent=2))
PY
expect_fail c1-artifact-flip "$BASE/c1" artifact_identity_pinned 3 "artifact pin mismatch: out_shape/shape.glb"

# ---- control 2: stdout count edit -> shape_reproduced ----------------------
newcopy c2
python3 - "$BASE/c2" <<'PY'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
obs_p = root/'run'/'invocation'/'output.json'
obs = json.loads(obs_p.read_text())
c = next(x for x in obs['cases'] if x['name'].startswith('bearing_product_e2e') and 'repeat' not in x['name'])
s = next(x for x in c['stages'] if x['stage']=='shape')
s['stdout'] = s['stdout'].replace('286384 verts', '286385 verts')
obs_p.write_text(json.dumps(obs, indent=2))
# keep the evidence stream copy byte-consistent so the preflight doesn't mask
ev = root/'run'/'invocation'/'evidence'/('case-%s.shape.stdout.txt' % c['name'])
ev.write_text(s['stdout'])
PY
expect_fail c2-stdout-edit "$BASE/c2" shape_reproduced 3 "shape stdout missing"

# ---- control 3: wrong interpreter -> interpreter_declared -------------------
expect_fail c3-wrong-python "$BASE/c0" interpreter_declared 3 "interpreter probe failed" \
  RCOS_HUNYUAN_PYTHON=/usr/bin/python3

# ---- control 4: deps.json tamper -> torch_free_asserted --------------------
newcopy c4
python3 - "$BASE/c4" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])/'run'/'invocation'/'evidence'/'deps.json'
d = json.loads(p.read_text()); d['mlx'] = '9.9.9'
p.write_text(json.dumps(d, indent=2))
PY
expect_fail c4-deps-tamper "$BASE/c4" torch_free_asserted 3 "deps.json"

# ---- control 5: fixture input copy deleted -> artifact_identity_pinned -----
newcopy c5
rm "$BASE/c5/run/evidence/inputs/bearing-ref.png"
expect_fail c5-fixture-absent "$BASE/c5" artifact_identity_pinned 4 "gate crashed: Error: ENOENT"

# ---- control 6: refusal stderr scrubbed -> empty_source_refused ------------
newcopy c6
python3 - "$BASE/c6" <<'PY'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
obs_p = root/'run'/'invocation'/'output.json'
obs = json.loads(obs_p.read_text())
c = next(x for x in obs['cases'] if x['name']=='empty_source_refused')
s = c['stages'][0]
s['stderr'] = 'clean exit'
s['exit_status'] = 0
obs_p.write_text(json.dumps(obs, indent=2))
ev = root/'run'/'invocation'/'evidence'/('case-empty_source_refused.prep.stderr.txt')
ev.write_text('clean exit')
PY
expect_fail c6-refusal-scrub "$BASE/c6" empty_source_refused 3 "refusal exit 0 != 1"

echo "SELFTEST TOTAL: $pass controls behaved as declared, $fail did not"
[ "$fail" -eq 0 ]

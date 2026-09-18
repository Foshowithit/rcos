#!/usr/bin/env node
'use strict';

// Gate self-test: proves each gate CAN fail.
//
// A gate that only ever passes is not a check, it is decoration. This script
// takes the newest real run of this eval, copies its observation into a scratch
// directory, tampers exactly one thing, and re-runs all five gates. The real
// run directory, the real work dir and the real checker are never written to:
// only the scratch copy of the observation is altered.
//
// Usage:  node evals/preview-server-verify-serve-pin-v1/gates/selftest.js
// Exit 0 when every control behaved as declared, 1 otherwise.
//
// This is a diagnostic. It is not a gate, it is not registered, and it
// produces no verdict about the capability.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const HOME = process.env.RCOS_HOME || path.join(os.homedir(), 'zcode-rcos');
const EVAL_ID = 'preview-server-verify-serve-pin-v1';
const GATE = path.join(HOME, 'evals', EVAL_ID, 'gates', 'check.js');
const GATES = ['serves', 'bytes_match_pin_recomputed', 'stale_pin_caught', 'missing_path_caught', 'port_released'];

function newestRun() {
  const runsDir = path.join(HOME, 'runs');
  const rows = fs.readdirSync(runsDir).sort().reverse();
  for (const id of rows) {
    const receipt = path.join(runsDir, id, 'receipt.json');
    if (!fs.existsSync(receipt)) continue;
    const r = JSON.parse(fs.readFileSync(receipt, 'utf8'));
    if (r.eval_id !== EVAL_ID) continue;
    if (!r.invocation || typeof r.invocation.dir !== 'string') continue;
    const invDir = path.join(HOME, r.invocation.dir);
    if (!fs.existsSync(path.join(invDir, 'output.json'))) continue;
    return { runId: id, runDir: path.join(runsDir, id), invDir };
  }
  return null;
}

const target = newestRun();
if (!target) {
  console.error('blocked: no run of ' + EVAL_ID + ' with an observation is present — run `rcos eval-run --eval ' + EVAL_ID + '` first');
  process.exit(4);
}
const WORK = path.join(target.runDir, 'work');
const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'psv-selftest-'));

function freshInv(name) {
  const dir = path.join(SCRATCH, name);
  fs.cpSync(target.invDir, dir, { recursive: true });
  return dir;
}
const loadObs = (d) => JSON.parse(fs.readFileSync(path.join(d, 'output.json'), 'utf8'));
const saveObs = (d, o) => fs.writeFileSync(path.join(d, 'output.json'), JSON.stringify(o, null, 2) + '\n');

function runGates(invDir, work) {
  const env = Object.assign({}, process.env, {
    RCOS_HOME: HOME, RCOS_RUN_DIR: target.runDir, RCOS_WORK_DIR: work || WORK, RCOS_INVOCATION_DIR: invDir
  });
  const out = {};
  for (const g of GATES) {
    const r = spawnSync('node', [GATE, g], { cwd: work || WORK, env, encoding: 'utf8' });
    out[g] = { code: r.status, text: (r.stdout || r.stderr || '').trim().split('\n')[0] };
  }
  return out;
}
const shape = (res) => GATES.map((g) => g + '=' + (res[g].code === 0 ? 'pass' : res[g].code === 3 ? 'FAIL' : 'blocked')).join(' ');

// Each control declares the exact set of gates it must break. An empty set means
// the gate must hold: tampering something a gate does not own must not move it.
const CONTROLS = [
  { name: 'untampered observation', broke: [], why: 'the harness itself must be faithful',
    build: () => { return { dir: freshInv('c00') }; } },
  { name: 'pin_ok pin replaced with the stale hash', broke: ['bytes_match_pin_recomputed'],
    why: 'a pin that is not the fixture hash, and a stale probe pinning the same bytes as the fresh one, must both be caught',
    build: () => { const d = freshInv('c01'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'pin_ok').expect_sha256 = o.probes.find((p) => p.name === 'stale_pin').expect_sha256;
      saveObs(d, o); return { dir: d }; } },
  { name: 'checker hash does not match the checker on disk', broke: GATES,
    why: 'an observation its own evidence contradicts is a FAIL, never "blocked"',
    build: () => { const d = freshInv('c02'); const o = loadObs(d); o.checker.sha256 = '0'.repeat(64); saveObs(d, o); return { dir: d }; } },
  { name: 'evidence text edited after the fact', broke: GATES,
    why: 'the recorded text and the raw capture must be the same bytes',
    build: () => { const d = freshInv('c03'); const ev = path.join(d, 'evidence', 'probe-pin_ok.stdout.txt');
      fs.appendFileSync(ev, '\n'); return { dir: d }; } },
  { name: 'stale probe claiming a pass', broke: ['stale_pin_caught'],
    why: 'a stale pin reported as passing is the 09-17 failure walking through the front door',
    build: () => { const d = freshInv('c04'); const o = loadObs(d); const p = o.probes.find((x) => x.name === 'stale_pin');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; saveObs(d, o); return { dir: d }; } },
  { name: 'missing path claiming HTTP 200', broke: ['missing_path_caught'],
    why: 'a 404 probe that claims success proves nothing about missing paths',
    build: () => { const d = freshInv('c05'); const o = loadObs(d);
      Object.assign(o.probes.find((x) => x.name === 'missing_path').observed, { http_status: 200, served_bytes: 535 });
      saveObs(d, o); return { dir: d }; } },
  { name: 'docroot bytes changed under the run', broke: ['bytes_match_pin_recomputed'],
    why: 'the work copy must still be the fixture the runner froze',
    build: () => { const d = freshInv('c06'); const alt = path.join(SCRATCH, 'alt-work');
      fs.cpSync(WORK, alt, { recursive: true });
      fs.appendFileSync(path.join(alt, 'docroot', 'index.html'), '\n<!-- later edit -->\n');
      return { dir: d, work: alt }; } },
  { name: 'serves: HTTP 500 recorded for the pinned probe', broke: ['serves'],
    why: 'serves owns the transport facts and nothing else',
    build: () => { const d = freshInv('c07'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'pin_ok').observed.http_status = 500; saveObs(d, o); return { dir: d }; } },
  { name: 'serves: pass marker absent', broke: ['serves'],
    why: 'the checker\'s own success marker is the load-bearing signal',
    build: () => { const d = freshInv('c08'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'pin_ok').observed.pass_marker = false; saveObs(d, o); return { dir: d }; } },
  { name: 'port_released: a bound port with no teardown recorded', broke: ['port_released'],
    why: 'a port the checker opened and never showed closed is a leak',
    build: () => { const d = freshInv('c09'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'stale_pin').observed.teardown_port = null; saveObs(d, o); return { dir: d }; } },
  { name: 'no observation at all', broke: [], allBlocked: true,
    why: 'absent evidence is blocked, which is a different verdict from failed',
    build: () => { const d = freshInv('c10'); fs.rmSync(path.join(d, 'output.json')); return { dir: d }; } }
];

console.log('self-test against run ' + target.runId + ' (observation copied, never edited)\n');
let bad = 0;
for (const c of CONTROLS) {
  const built = c.build();
  const res = runGates(built.dir, built.work);
  const broke = GATES.filter((g) => res[g].code === 3);
  const blocked = GATES.filter((g) => res[g].code !== 0 && res[g].code !== 3);
  let ok;
  if (c.allBlocked) ok = blocked.length === GATES.length;
  else ok = broke.length === c.broke.length && c.broke.every((g) => broke.includes(g)) && blocked.length === 0;
  if (!ok) bad++;
  console.log((ok ? 'ok   ' : 'BAD  ') + c.name);
  console.log('       ' + shape(res) + (ok ? '' : '   <- expected to break: ' + (c.broke.length ? c.broke.join(', ') : c.allBlocked ? 'all (blocked)' : 'nothing')));
  for (const g of broke) console.log('         ' + res[g].text);
}
fs.rmSync(SCRATCH, { recursive: true, force: true });
console.log('\n' + (CONTROLS.length - bad) + '/' + CONTROLS.length + ' controls behaved as declared');
process.exit(bad === 0 ? 0 : 1);

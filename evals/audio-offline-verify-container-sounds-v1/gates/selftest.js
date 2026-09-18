#!/usr/bin/env node
'use strict';

// Gate self-test: proves each gate CAN fail.
//
// A gate that only ever passes is not a check, it is decoration. This script
// takes the newest real run of this eval, copies its observation into a scratch
// directory, tampers exactly one thing, and re-runs all seven gates. The real
// run directory, the real work dir and the real checker are never written to:
// only scratch copies are altered.
//
// Usage:  node evals/audio-offline-verify-container-sounds-v1/gates/selftest.js
// Exit 0 when every control behaved as declared, 1 otherwise.
//
// This is a diagnostic. It is not a gate, it is not registered, and it
// produces no verdict about the capability.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const HOME = process.env.RCOS_HOME || path.join(os.homedir(), 'zcode-rcos');
const EVAL_ID = 'audio-offline-verify-container-sounds-v1';
const GATE = path.join(HOME, 'evals', EVAL_ID, 'gates', 'check.js');
const GATES = ['voiced_passes', 'envelope_gate_bites', 'silence_reported_not_asserted', 'mute_caught',
  'absence_asserted_not_assumed', 'checker_revision_pinned', 'artifact_identity_pinned'];
const CHECKER_REL = 'capabilities/audio-offline-verify/adapter/av_check.py';

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
const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'aov-selftest-'));

function freshInv(name) {
  const dir = path.join(SCRATCH, name);
  fs.cpSync(target.invDir, dir, { recursive: true });
  return dir;
}
const loadObs = (d) => JSON.parse(fs.readFileSync(path.join(d, 'output.json'), 'utf8'));
const saveObs = (d, o) => fs.writeFileSync(path.join(d, 'output.json'), JSON.stringify(o, null, 2) + '\n');
const sha256 = (buf) => require('node:crypto').createHash('sha256').update(buf).digest('hex');

// A scratch RCOS_HOME holding a checker that is no longer the pinned revision.
// Both the observation and the disk then agree with each other and disagree with
// the pin — which is the only way to reach the revision gate without editing the
// real capability tree.
function scratchHomeWithEditedChecker() {
  const home = path.join(SCRATCH, 'home-c09');
  const dst = path.join(home, CHECKER_REL);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, fs.readFileSync(path.join(HOME, CHECKER_REL), 'utf8') + '\n# edited after the eval was authored\n');
  return { home, sha: sha256(fs.readFileSync(dst)) };
}

// The 09-18 clean-room regression: on macOS $TMPDIR lives under /private while
// node resolves the adapter's own directory, so an observation once named the
// checker ABSOLUTELY under /private/tmp while the judging RCOS_HOME was /tmp.
// A gate that joins RCOS_HOME onto whatever the observation records would look
// in a doubled directory and declare the checker unreadable — failing every
// gate on identical evidence. This control rebuilds that exact shape: the same
// file, named through a symlinked root that spells RCOS_HOME differently, with
// the judging RCOS_HOME unchanged.
function observationNamedThroughSymlinkedRoot() {
  const link = path.join(SCRATCH, 'home-link-c13');
  try { fs.symlinkSync(HOME, link, 'dir'); } catch (e) { /* created once */ }
  const d = freshInv('c13');
  const o = loadObs(d);
  o.checker.path = path.join(link, CHECKER_REL);
  saveObs(d, o);
  return { dir: d };
}

function runGates(invDir, opts) {
  const o = opts || {};
  const work = o.work || WORK;
  const env = Object.assign({}, process.env, {
    RCOS_HOME: o.home || HOME, RCOS_RUN_DIR: target.runDir, RCOS_WORK_DIR: work, RCOS_INVOCATION_DIR: invDir
  });
  const out = {};
  for (const g of GATES) {
    const r = spawnSync('node', [GATE, g], { cwd: work, env, encoding: 'utf8' });
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

  { name: 'voiced pass with an RMS that is not the recorded measurement', broke: ['voiced_passes'],
    why: 'a must-sound pass is only as good as the reading behind it',
    build: () => { const d = freshInv('c01'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'chalk2_voiced').observed.rms_dbfs = -20.0;
      saveObs(d, o); return { dir: d }; } },

  { name: 'second voiced artifact recalled as exit 3', broke: ['voiced_passes'],
    why: 'the gate must cover both chalk artifacts, not just the first one it finds',
    build: () => { const d = freshInv('c02'); const o = loadObs(d); const p = o.probes.find((x) => x.name === 'chalk1_voiced');
      p.exit_status = 3; p.outcome = 'caught'; p.observed.pass_marker = false;
      saveObs(d, o); return { dir: d }; } },

  { name: 'out-of-envelope probe claiming a pass', broke: ['envelope_gate_bites'],
    why: 'a duration gate that never bites is decoration',
    build: () => { const d = freshInv('c03'); const o = loadObs(d); const p = o.probes.find((x) => x.name === 'chalk2_wrong_envelope');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: 'silent-by-design file with a level it did not measure', broke: ['silence_reported_not_asserted'],
    why: 'the report-only leg rests on the recorded reading being the checker\'s own',
    build: () => { const d = freshInv('c04'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'face_silent_report').observed.rms_token = '-30.000';
      saveObs(d, o); return { dir: d }; } },

  { name: 'mute attack recorded as a pass', broke: ['mute_caught'],
    why: 'this is the 09-17 failure walking through the front door',
    build: () => { const d = freshInv('c05'); const o = loadObs(d); const p = o.probes.find((x) => x.name === 'face_silent_must_sound');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: 'audio-codec claim for a file with no audio stream', broke: ['absence_asserted_not_assumed'],
    why: 'inventing a track is the exact thing this capability exists to catch',
    build: () => { const d = freshInv('c06'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'dispatch_absent_expect_none').observed.audio_codec = 'aac';
      saveObs(d, o); return { dir: d }; } },

  { name: 'checker hash does not match the checker on disk', broke: GATES,
    why: 'an observation its own evidence contradicts is a FAIL, never "blocked"',
    build: () => { const d = freshInv('c07'); const o = loadObs(d); o.checker.sha256 = '0'.repeat(64); saveObs(d, o); return { dir: d }; } },

  { name: 'evidence text edited after the fact', broke: GATES,
    why: 'the recorded text and the raw capture must be the same bytes',
    build: () => { const d = freshInv('c08'); const ev = path.join(d, 'evidence', 'probe-chalk2_voiced.stdout.txt');
      fs.appendFileSync(ev, '\n'); return { dir: d }; } },

  { name: 'checker changed on disk, observation updated to match it', broke: ['checker_revision_pinned'],
    why: 'claim and reality can agree with each other and still not be the revision this eval was authored against',
    build: () => { const d = freshInv('c09'); const o = loadObs(d); const s = scratchHomeWithEditedChecker();
      o.checker.sha256 = s.sha; saveObs(d, o); return { dir: d, home: s.home }; } },

  { name: 'fixture bytes changed under the run', broke: ['artifact_identity_pinned'],
    why: 'the work copy must still be the artifact the runner froze and the history names',
    build: () => { const d = freshInv('c10'); const alt = path.join(SCRATCH, 'alt-work');
      fs.cpSync(WORK, alt, { recursive: true });
      fs.appendFileSync(path.join(alt, 'chalk-eval2.mp4'), '\n');
      return { dir: d, work: alt }; } },

  { name: 'probe duration_ms edited', broke: [],
    why: 'a timing field no gate owns must not move any gate',
    build: () => { const d = freshInv('c11'); const o = loadObs(d);
      o.probes.find((p) => p.name === 'chalk2_voiced').duration_ms = 999999;
      saveObs(d, o); return { dir: d }; } },

  { name: 'no observation at all', broke: [], allBlocked: true,
    why: 'absent evidence is blocked, which is a different verdict from failed',
    build: () => { const d = freshInv('c12'); fs.rmSync(path.join(d, 'output.json')); return { dir: d }; } },

  { name: 'same checker named absolutely through a symlinked root', broke: [],
    why: 'a receipt must stay judgeable when the observation spells the root differently than the judging RCOS_HOME',
    build: () => observationNamedThroughSymlinkedRoot() }
];

console.log('self-test against run ' + target.runId + ' (observation copied, never edited)\n');
let bad = 0;
for (const c of CONTROLS) {
  const built = c.build();
  const res = runGates(built.dir, built);
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

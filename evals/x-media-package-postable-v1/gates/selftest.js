#!/usr/bin/env node
'use strict';

// Gate self-test: proves each gate CAN fail.
//
// A gate that only ever passes is not a check, it is decoration. This script takes
// the newest real run of this eval, copies its observation into a scratch directory,
// tampers exactly one thing, and re-runs all eleven gates. The real run directory,
// the real work dir, the real invocation dir and the real checker are never written
// to: only scratch copies are altered.
//
// Two controls need a second work dir (a copy of the run's work) because they tamper
// the FILE a claim points at while leaving the observation truthful — the only way to
// reach a bytes-identity leg without also tripping the text-evidence legs. One control
// uses a scratch RCOS_HOME with an edited checker. Two name the same real files through
// a symlinked root, which must judge identically to the plain spelling.
//
// Usage:  node evals/x-media-package-postable-v1/gates/selftest.js
// Exit 0 when every control behaved as declared, 1 otherwise.
//
// This is a diagnostic. It is not a gate, it is not registered, and it produces no
// verdict about the capability.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const HOME = process.env.RCOS_HOME || path.join(os.homedir(), 'zcode-rcos');
const EVAL_ID = 'x-media-package-postable-v1';
const GATE = path.join(HOME, 'evals', EVAL_ID, 'gates', 'check.js');
const GATES = ['platform_limits_pass', 'long_caption_caught', 'caption_limit_bites', 'alt_gate_bites',
  'aspect_gate_bites', 'duration_gate_bites', 'poster_extracted', 'poster_offset_reproduced',
  'cannot_probe_reported', 'checker_revision_pinned', 'artifact_identity_pinned'];
const CHECKER_REL = 'capabilities/x-media-package/adapter/xcheck.py';

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
const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'xmp-selftest-'));

function freshInv(name) {
  const dir = path.join(SCRATCH, name);
  fs.cpSync(target.invDir, dir, { recursive: true });
  relocate(dir);
  return dir;
}

// Everything the adapter recorded — the observation and the raw captures it is checked
// against — names files inside the invocation dir it ran in (argv, and the checker text
// that echoes argv). A copied invocation is a different tree, so the copy's whole record
// is rewritten to name the copy: the bytes a re-run in another root would have produced.
// Leaving it alone would make the copy contradict its own evidence, which is a fault of
// the harness, not something a gate should be asked to grade.
function relocate(dir) {
  const prefix = target.invDir + path.sep;
  const map = (s) => s.split(prefix).join(dir + path.sep);
  const deep = (v) => {
    if (typeof v === 'string') return map(v);
    if (Array.isArray(v)) return v.map(deep);
    if (v && typeof v === 'object') {
      const out = {};
      for (const k of Object.keys(v)) out[k] = deep(v[k]);
      return out;
    }
    return v;
  };
  const obsPath = path.join(dir, 'output.json');
  fs.writeFileSync(obsPath, JSON.stringify(deep(JSON.parse(fs.readFileSync(obsPath, 'utf8'))), null, 2) + '\n');
  const evid = path.join(dir, 'evidence');
  for (const f of fs.readdirSync(evid)) {
    const p = path.join(evid, f);
    if (f.endsWith('.argv.json')) fs.writeFileSync(p, JSON.stringify(deep(JSON.parse(fs.readFileSync(p, 'utf8'))), null, 2) + '\n');
    else if (f.endsWith('.stdout.txt') || f.endsWith('.stderr.txt')) fs.writeFileSync(p, map(fs.readFileSync(p, 'utf8')));
  }
}
function altWork(name) {
  const dir = path.join(SCRATCH, name);
  fs.cpSync(WORK, dir, { recursive: true });
  return dir;
}
const loadObs = (d) => JSON.parse(fs.readFileSync(path.join(d, 'output.json'), 'utf8'));
const saveObs = (d, o) => fs.writeFileSync(path.join(d, 'output.json'), JSON.stringify(o, null, 2) + '\n');
const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const posterOf = (o, name) => o.packages.find((p) => p.name === name).observed.poster;

// A scratch RCOS_HOME holding a checker that is no longer the pinned revision. Both
// the observation and the disk then agree with each other and disagree with the pin —
// which is the only way to reach the revision gate without editing the real tree.
function scratchHomeWithEditedChecker() {
  const home = path.join(SCRATCH, 'home-c09');
  const dst = path.join(home, CHECKER_REL);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, fs.readFileSync(path.join(HOME, CHECKER_REL), 'utf8') + '\n# edited after the eval was authored\n');
  return { home, sha: sha256(fs.readFileSync(dst)) };
}

// The 09-18 clean-room regression: on macOS $TMPDIR lives under /private while node
// resolves the adapter's own directory, so a receipt can name the checker under
// /private/tmp while the judging RCOS_HOME is /tmp. A gate that joins RCOS_HOME onto
// whatever the observation records would look in a doubled directory and declare the
// checker unreadable, failing every gate on identical evidence. This control rebuilds
// that exact shape with the judging RCOS_HOME unchanged.
function observationNamedThroughSymlinkedRoot() {
  const link = path.join(SCRATCH, 'home-link-c13');
  try { fs.symlinkSync(HOME, link, 'dir'); } catch (e) { /* created once */ }
  const d = freshInv('c13');
  const o = loadObs(d);
  o.checker.path = path.join(link, CHECKER_REL);
  saveObs(d, o);
  return { dir: d };
}

// The same shape one level down: every poster claim spelled as an absolute path
// through a symlinked root of the invocation work dir, naming the same files the
// run wrote.
function postersNamedThroughSymlinkedWork() {
  const link = path.join(SCRATCH, 'inv-work-link-c16');
  const d = freshInv('c16');
  fs.symlinkSync(path.join(d, 'work'), link, 'dir');
  const o = loadObs(d);
  for (const p of o.packages) {
    if (p.observed.poster) p.observed.poster.path = path.join(link, p.run_dir, 'x-poster.jpg');
  }
  saveObs(d, o);
  return { dir: d };
}

// The chalk poster re-extracted at a seek the checker never uses, swapped into the
// invocation-work copy AND the evidence copy, with the record updated to describe it —
// every internal claim then matches the file, and only the re-derivation can tell that
// the frame is not the one the duration implies.
function posterAtWrongSeek() {
  const d = freshInv('c15');
  const video = path.join(d, 'work', 'probe-chalk_package', 'video.mp4');
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'xmp-reseek-'));
  const out = path.join(scratch, 'x-poster.jpg');
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', '2.5', '-i', video, '-frames:v', '1', '-q:v', '3', out], { encoding: 'utf8' });
  if (r.error) throw new Error('ffmpeg could not be run: ' + r.error.message);
  if (r.status !== 0 || !fs.existsSync(out)) throw new Error('could not re-extract the 2.5s frame (ffmpeg exit ' + r.status + ')');
  const altSha = sha256(fs.readFileSync(out));
  const before = posterOf(loadObs(d), 'chalk_package');
  if (altSha === before.sha256) throw new Error('the 2.5s frame is byte-identical to the recorded 1.0s frame — this control cannot distinguish them');
  fs.copyFileSync(out, path.join(d, 'work', 'probe-chalk_package', 'x-poster.jpg'));
  fs.copyFileSync(out, path.join(d, 'evidence', 'probe-chalk_package.poster.jpg'));
  const o = loadObs(d);
  const claim = posterOf(o, 'chalk_package');
  claim.sha256 = altSha;
  claim.bytes = fs.statSync(out).size;
  o.packages.find((p) => p.name === 'chalk_package').observed.poster_seek_s = '2.5';
  saveObs(d, o);
  return { dir: d };
}

// A poster claimed for the file the probe could not open, with REAL bytes behind it at
// the claimed path (the accepted chalk poster copied in, plus its evidence copy): the
// file-exists, byte-hash, JPEG, evidence and path legs all pass, so only the "a probe
// that could not open the file extracted no frame" leg can refuse the claim.
function posterClaimedForUnprobeableFile() {
  const d = freshInv('c14');
  const chalkPoster = path.join(d, 'work', 'probe-chalk_package', 'x-poster.jpg');
  const nvDir = path.join(d, 'work', 'probe-control_not_a_video');
  fs.mkdirSync(nvDir, { recursive: true });
  fs.copyFileSync(chalkPoster, path.join(nvDir, 'x-poster.jpg'));
  fs.copyFileSync(chalkPoster, path.join(d, 'evidence', 'probe-control_not_a_video.poster.jpg'));
  const o = loadObs(d);
  const chalk = posterOf(o, 'chalk_package');
  const nv = o.packages.find((p) => p.name === 'control_not_a_video');
  nv.observed.poster = {
    path: 'probe-control_not_a_video/x-poster.jpg',
    sha256: chalk.sha256,
    bytes: chalk.bytes,
    jpeg: true,
    width: nv.observed.video_width,
    height: nv.observed.video_height
  };
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

// Each control declares the exact set of gates it must break. An empty set means the
// gate must hold: tampering something a gate does not own must not move it.
const CONTROLS = [
  { name: 'untampered observation', broke: [], why: 'the harness itself must be faithful',
    build: () => ({ dir: freshInv('c00') }) },

  { name: 'chalk duration recalled as 9.9s under the historical stdout', broke: ['platform_limits_pass'],
    why: 'the acceptance line is only as good as the container facts parsed behind it',
    build: () => { const d = freshInv('c01'); const o = loadObs(d);
      o.packages.find((p) => p.name === 'chalk_package').observed.container_duration_s = 9.9;
      saveObs(d, o); return { dir: d }; } },

  { name: '321-char attack recalled as a pass', broke: ['long_caption_caught'],
    why: 'this is the historical attack the capability exists to catch',
    build: () => { const d = freshInv('c02'); const o = loadObs(d); const p = o.packages.find((x) => x.name === 'attack_long_caption');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: '280-char caption recalled as caught', broke: ['caption_limit_bites'],
    why: 'the limit must bite from both sides: the inside must pass',
    build: () => { const d = freshInv('c03'); const o = loadObs(d); const p = o.packages.find((x) => x.name === 'control_caption_280');
      p.exit_status = 3; p.outcome = 'caught'; p.observed.pass_marker = false; p.observed.fail_lines = ['CAPTION 280 > 280 chars'];
      saveObs(d, o); return { dir: d }; } },

  { name: 'empty alt text recalled as a pass', broke: ['alt_gate_bites'],
    why: 'the accessibility gate is the one that cannot be shrugged off',
    build: () => { const d = freshInv('c04'); const o = loadObs(d); const p = o.packages.find((x) => x.name === 'control_alt_empty');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: 'portrait crop recalled as a pass', broke: ['aspect_gate_bites'],
    why: 'a crop that is still 3.0s long must be caught on geometry',
    build: () => { const d = freshInv('c05'); const o = loadObs(d); const p = o.packages.find((x) => x.name === 'control_aspect_portrait');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: '141s clip recalled as a pass', broke: ['duration_gate_bites'],
    why: 'a duration gate that never bites is decoration',
    build: () => { const d = freshInv('c06'); const o = loadObs(d); const p = o.packages.find((x) => x.name === 'control_duration_141s');
      p.exit_status = 0; p.outcome = 'passed'; p.observed.pass_marker = true; p.observed.fail_lines = [];
      saveObs(d, o); return { dir: d }; } },

  { name: 'poster bytes corrupted under a truthful observation', broke: ['poster_extracted'],
    why: 'the recorded poster hash must be checked against the bytes on disk, not trusted',
    build: () => { const d = freshInv('c07');
      const workPoster = path.join(d, 'work', 'probe-chalk_package', 'x-poster.jpg');
      const evidPoster = path.join(d, 'evidence', 'probe-chalk_package.poster.jpg');
      fs.writeFileSync(workPoster, Buffer.concat([fs.readFileSync(workPoster), Buffer.from('not a jpeg')]));
      fs.writeFileSync(evidPoster, Buffer.concat([fs.readFileSync(evidPoster), Buffer.from('not a jpeg')]));
      return { dir: d }; } },

  { name: 'evidence text edited after the fact', broke: GATES,
    why: 'the recorded text and the raw capture must be the same bytes',
    build: () => { const d = freshInv('c08');
      fs.appendFileSync(path.join(d, 'evidence', 'probe-chalk_package.stdout.txt'), '\n');
      return { dir: d }; } },

  { name: 'checker changed on disk, observation updated to match it', broke: ['checker_revision_pinned'],
    why: 'claim and reality can agree with each other and still not be the revision this eval was authored against',
    build: () => { const d = freshInv('c09'); const o = loadObs(d); const s = scratchHomeWithEditedChecker();
      o.checker.sha256 = s.sha; saveObs(d, o); return { dir: d, home: s.home }; } },

  { name: 'fixture bytes changed under the run', broke: ['artifact_identity_pinned'],
    why: 'the work copy must still be the artifact the runner froze and the history names',
    build: () => { const d = freshInv('c10'); const alt = altWork('alt-work-c10');
      fs.appendFileSync(path.join(alt, 'cap-280.txt'), 'x');
      return { dir: d, work: alt }; } },

  { name: 'package duration_ms edited', broke: [],
    why: 'a timing field no gate owns must not move any gate',
    build: () => { const d = freshInv('c11'); const o = loadObs(d);
      o.packages.find((p) => p.name === 'chalk_package').duration_ms = 999999;
      saveObs(d, o); return { dir: d }; } },

  { name: 'no observation at all', broke: [], allBlocked: true,
    why: 'absent evidence is blocked, which is a different verdict from failed',
    build: () => { const d = freshInv('c12'); fs.rmSync(path.join(d, 'output.json')); return { dir: d }; } },

  { name: 'same checker named absolutely through a symlinked root', broke: [],
    why: 'a receipt must stay judgeable when the observation spells the root differently than the judging RCOS_HOME',
    build: () => observationNamedThroughSymlinkedRoot() },

  { name: 'a poster claimed for a file the probe could not open', broke: ['poster_extracted'],
    why: 'a frame that was never extracted must not pass as one, even with real bytes behind the claim',
    build: () => posterClaimedForUnprobeableFile() },

  { name: 'chalk poster re-extracted at a seek the checker never used', broke: ['poster_offset_reproduced'],
    why: 'the offset must be re-derived from the duration and the frame re-extracted, not taken from the record',
    build: () => posterAtWrongSeek() },

  { name: 'same posters named absolutely through a symlinked work root', broke: [],
    why: 'poster claims are judged by the file they resolve to, never by the path string',
    build: () => postersNamedThroughSymlinkedWork() }
];

console.log('self-test against run ' + target.runId + ' (observation copied, never edited)\n');
let bad = 0;
for (const c of CONTROLS) {
  let built;
  try {
    built = c.build();
  } catch (e) {
    bad++;
    console.log('BAD  ' + c.name);
    console.log('       control could not be built: ' + e.message);
    continue;
  }
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

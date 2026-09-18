#!/usr/bin/env node
'use strict';

// Gate self-test: proves each gate CAN fail.
//
// A gate that only ever passes is not a check, it is decoration. This script takes
// the newest real run of this eval, copies its observation into a scratch directory,
// tampers exactly one thing, and re-runs all fourteen gates. The real run directory,
// the real work dir, the real invocation dir and the frozen adapter scripts are never
// written to: only scratch copies are altered.
//
// Two controls need a second work dir or a scratch RCOS_HOME because they tamper the
// FILE a claim points at (or the script itself) while leaving the observation
// truthful — the only way to reach a bytes-identity or revision leg without also
// tripping the text-evidence legs. Two name the same real files through a symlinked
// root, which must judge identically to the plain spelling.
//
// PNG physics the controls rely on: a byte flipped inside an IDAT chunk corrupts the
// zlib stream, so the figure can no longer be decoded at all; bytes appended after
// IEND change the file's hash while the decoded pixels stay identical. The two
// tamper controls use one of each.
//
// Usage:  node evals/receipt-figure-render-figures-v1/gates/selftest.js
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
const EVAL_ID = 'receipt-figure-render-figures-v1';
const GATE = path.join(HOME, 'evals', EVAL_ID, 'gates', 'check.js');
const GATES = ['historical_74_reproduced', 'reconstructed_75_oracle_match', 'authored_21_geometry',
  'historical_sidecars_accepted', 'fresh_sidecars_accepted', 'fresh_sidecar_reproduces_historical',
  'tampered_sidecar_bites', 'stale_sidecar_reported', 'capability_shift_bites',
  'degenerate_inputs_reported', 'geometry_tracks_frozen_registry', 'cap_count_does_not_move_geometry',
  'frozen_source_pinned', 'artifact_identity_pinned'];
const RENDERER_REL = 'capabilities/receipt-figure-render/adapter/receipt_figures.py';
const CHECKER_REL = 'capabilities/receipt-figure-render/adapter/check_figures.py';

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
const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'rfr-selftest-'));

function freshInv(name) {
  const dir = path.join(SCRATCH, name);
  fs.cpSync(target.invDir, dir, { recursive: true });
  relocate(dir);
  return dir;
}

// Everything the adapter recorded — the observation and the raw captures it is checked
// against — names files inside the invocation dir it ran in (argv, cwd, and the render
// line's out-dir). A copied invocation is a different tree, so the copy's whole record
// is rewritten to name the copy: the bytes a re-run in another root would have produced.
// Leaving it alone would make the copy contradict its own evidence, which is a fault of
// the harness, not something a gate should be asked to grade.
function relocate(dir) {
  remapDir(dir, target.invDir, dir);
}
// Rewrite every absolute path spelled under `from` to the same file spelled under `to`,
// across the observation (deep), the argv captures (deep) and the raw text captures.
function remapDir(dir, from, to) {
  const prefix = from + path.sep;
  const map = (s) => s.split(prefix).join(to + path.sep);
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
const caseOf = (o, name) => {
  const c = o.cases.find((x) => x.name === name);
  if (!c) throw new Error('no case named ' + name + ' in the observation');
  return c;
};
const under = (d, rel) => path.join(d, 'work', rel);
const evidenceFile = (d, c, rel) => path.join(d, 'evidence', 'case-' + c.name + '.' + path.basename(rel));
// Replace a produced file (figure or sidecar) in the invocation-work copy AND its
// evidence copy, and return the identity the observation must now record.
function putProduced(d, c, rel, buf) {
  fs.writeFileSync(under(d, rel), buf);
  fs.writeFileSync(evidenceFile(d, c, rel), buf);
  return { sha256: sha256(buf), bytes: buf.length };
}
const evText = (d, c, kind, text) => fs.writeFileSync(path.join(d, 'evidence', 'case-' + c.name + '.' + kind), text);
function evArgv(d, c, patch) {
  const p = path.join(d, 'evidence', 'case-' + c.name + '.argv.json');
  const av = JSON.parse(fs.readFileSync(p, 'utf8'));
  Object.assign(av, patch);
  fs.writeFileSync(p, JSON.stringify(av, null, 2) + '\n');
}
// Recall a caught attack as accepted: take the accepted shape from a real accepted
// case of the same run (same registry, so the same acceptance line is plausible),
// and bring the raw captures and the argv exit along so the record stays
// self-consistent — only the gates that own the verdict may notice.
function recallAccepted(d, o, name) {
  const donor = caseOf(o, 'historical_sidecar_74');
  const c = caseOf(o, name);
  c.exit_status = 0;
  c.outcome = donor.outcome;
  c.stdout = donor.stdout;
  c.stderr = donor.stderr;
  c.fail_lines = [];
  evText(d, c, 'stdout.txt', c.stdout);
  evText(d, c, 'stderr.txt', c.stderr);
  evArgv(d, c, { exit_status: 0 });
}

// A scratch RCOS_HOME holding a checker that is no longer the pinned revision, plus
// the committed evidence the oracle gates read back (byte-identical copies, so those
// gates still hold and only the revision gate may move). Both the observation and the
// scratch disk then agree with each other and disagree with the pin — which is the
// only way to reach the revision gate without editing the real tree.
function scratchHomeWithEditedChecker() {
  const home = path.join(SCRATCH, 'home-c11');
  const dst = path.join(home, CHECKER_REL);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, fs.readFileSync(path.join(HOME, CHECKER_REL), 'utf8') + '\n# edited after the eval was authored\n');
  fs.cpSync(path.join(HOME, 'evidence', 'receipt-figure-render'), path.join(home, 'evidence', 'receipt-figure-render'), { recursive: true });
  return { home, sha: sha256(fs.readFileSync(dst)) };
}

// The same files, named absolutely through a symlinked root of the real home. A gate
// that compared path STRINGS would break here; the files resolve to the same inodes.
function frozenPathsThroughSymlinkedHome() {
  const link = path.join(SCRATCH, 'home-link-c15');
  try { fs.symlinkSync(HOME, link, 'dir'); } catch (e) { /* created once */ }
  const d = freshInv('c15');
  const o = loadObs(d);
  o.frozen.renderer.path = path.join(link, RENDERER_REL);
  o.frozen.checker.path = path.join(link, CHECKER_REL);
  saveObs(d, o);
  return { dir: d };
}

// The invocation's own tree, named through a symlinked root everywhere its record
// spells an absolute path (argv out-dir, cwd, the render line). Claims are judged by
// the file they resolve to, never by the path string.
function invocationThroughSymlinkedRoot() {
  const d = freshInv('c16');
  const link = path.join(SCRATCH, 'inv-link-c16');
  fs.symlinkSync(d, link, 'dir');
  remapDir(d, d, link);
  return { dir: d };
}

function runGates(invDir, opts) {
  const o = opts || {};
  const work = o.work || WORK;
  const env = Object.assign({}, process.env, {
    RCOS_HOME: o.home || HOME, RCOS_RUN_DIR: target.runDir, RCOS_WORK_DIR: work, RCOS_INVOCATION_DIR: invDir,
    RCOS_EVAL_DIR: path.join(HOME, 'evals', EVAL_ID)
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

  { name: 'render line recalled as n=73 under the 74-eval registry', broke: ['historical_74_reproduced'],
    why: 'the acceptance line is only as good as the registry facts parsed behind it',
    build: () => { const d = freshInv('c01'); const o = loadObs(d); const c = caseOf(o, 'historical_74');
      if (!c.stdout.includes('n=74 evals')) throw new Error('the render line does not carry n=74 evals');
      c.stdout = c.stdout.replace('n=74 evals', 'n=73 evals');
      evText(d, c, 'stdout.txt', c.stdout);
      saveObs(d, o); return { dir: d }; } },

  { name: 'historical sidecar values quietly lowered to n=73', broke: ['historical_74_reproduced', 'fresh_sidecars_accepted', 'fresh_sidecar_reproduces_historical'],
    why: 'a tamponed sidecar must fail the recompute, the re-run checker, and the historical round-trip at once',
    build: () => { const d = freshInv('c02'); const o = loadObs(d); const c = caseOf(o, 'historical_74');
      const file = under(d, c.sidecar.path);
      const text = fs.readFileSync(file, 'utf8');
      if (!/"n_evals"\s*:\s*74/.test(text)) throw new Error('the sidecar does not carry n_evals: 74');
      const buf = Buffer.from(text.replace(/"n_evals"\s*:\s*74/, '"n_evals": 73'));
      const rec = putProduced(d, c, c.sidecar.path, buf);
      c.sidecar.values.n_evals = 73;
      c.sidecar.sha256 = rec.sha256;
      c.sidecar.bytes = rec.bytes;
      saveObs(d, o); return { dir: d }; } },

  { name: 'accepted historical exchange recalled as caught', broke: ['historical_sidecars_accepted'],
    why: 'the frozen checker accepted the historical sidecars — a recall that says otherwise must fail',
    build: () => { const d = freshInv('c03'); const o = loadObs(d);
      const c = caseOf(o, 'historical_sidecar_74');
      const atk = caseOf(o, 'attack_tampered');
      c.exit_status = atk.exit_status; c.outcome = atk.outcome;
      c.stdout = atk.stdout; c.stderr = atk.stderr;
      c.fail_lines = JSON.parse(JSON.stringify(atk.fail_lines));
      evText(d, c, 'stdout.txt', c.stdout);
      evText(d, c, 'stderr.txt', c.stderr);
      evArgv(d, c, { exit_status: atk.exit_status });
      saveObs(d, o); return { dir: d }; } },

  { name: 'tampered sidecar recalled as accepted', broke: ['tampered_sidecar_bites'],
    why: 'this is the historical attack the capability exists to catch — a bite that can be recalled away is decoration',
    build: () => { const d = freshInv('c04'); const o = loadObs(d);
      recallAccepted(d, o, 'attack_tampered');
      saveObs(d, o); return { dir: d }; } },

  { name: 'stale sidecar recalled as accepted', broke: ['stale_sidecar_reported'],
    why: 'a sidecar written against a 75-cap registry must still be reported stale under the 74-cap one',
    build: () => { const d = freshInv('c05'); const o = loadObs(d);
      recallAccepted(d, o, 'stale_sidecar');
      saveObs(d, o); return { dir: d }; } },

  { name: 'capability-shifted sidecar recalled as accepted', broke: ['capability_shift_bites'],
    why: 'a registry whose capability set moved must still be reported, not waved through',
    build: () => { const d = freshInv('c06'); const o = loadObs(d);
      recallAccepted(d, o, 'attack_capability_shifted');
      saveObs(d, o); return { dir: d }; } },

  { name: 'malformed-registry stderr blanked', broke: ['degenerate_inputs_reported'],
    why: 'an input that crashed the renderer with a JSONDecodeError must not read as a clean run',
    build: () => { const d = freshInv('c07'); const o = loadObs(d); const c = caseOf(o, 'degenerate_malformed');
      c.stderr = '';
      evText(d, c, 'stderr.txt', '');
      saveObs(d, o); return { dir: d }; } },

  { name: 'byte flipped inside a figure IDAT chunk', broke: ['reconstructed_75_oracle_match', 'geometry_tracks_frozen_registry'],
    why: 'a corrupted stream cannot be decoded at all: the oracle pin and the geometry re-derivation must both refuse it, while the 74-vs-75 byte-inequality leg still holds',
    build: () => { const d = freshInv('c08'); const o = loadObs(d); const c = caseOf(o, 'reconstructed_75');
      const fig = c.figures.find((f) => f.name === 'fig-verdicts.png');
      const buf = fs.readFileSync(under(d, fig.path));
      const idat = buf.indexOf(Buffer.from('IDAT'));
      if (idat < 0) throw new Error('figure 1 of reconstructed_75 carries no IDAT chunk');
      const at = idat + 8 + 20;
      if (at >= buf.length - 4) throw new Error('the IDAT chunk is too small to corrupt safely');
      buf[at] ^= 0xFF;
      const rec = putProduced(d, c, fig.path, buf);
      fig.sha256 = rec.sha256; fig.bytes = rec.bytes;
      saveObs(d, o); return { dir: d }; } },

  { name: 'bytes appended to a figure after IEND', broke: ['authored_21_geometry', 'cap_count_does_not_move_geometry'],
    why: 'the pixels survive an append, so geometry still holds — but the file is no longer the pinned oracle bytes, and the 21-vs-74 byte-identity chain breaks',
    build: () => { const d = freshInv('c09'); const o = loadObs(d); const c = caseOf(o, 'authored_21');
      const fig = c.figures.find((f) => f.name === 'fig-verdicts.png');
      const buf = Buffer.concat([fs.readFileSync(under(d, fig.path)), Buffer.from('\nappended by the selftest after IEND\n')]);
      const rec = putProduced(d, c, fig.path, buf);
      fig.sha256 = rec.sha256; fig.bytes = rec.bytes;
      saveObs(d, o); return { dir: d }; } },

  { name: 'evidence text edited after the fact', broke: GATES,
    why: 'the recorded text and the raw capture must be the same bytes',
    build: () => { const d = freshInv('c10');
      fs.appendFileSync(path.join(d, 'evidence', 'case-historical_74.stdout.txt'), '\n');
      return { dir: d }; } },

  { name: 'checker changed in a scratch home, observation updated to match it', broke: ['frozen_source_pinned'],
    why: 'claim and reality can agree with each other and still not be the revision this eval was authored against',
    build: () => { const d = freshInv('c11'); const o = loadObs(d); const s = scratchHomeWithEditedChecker();
      o.frozen.checker.sha256 = s.sha; saveObs(d, o); return { dir: d, home: s.home }; } },

  { name: 'work dir presented as a near-copy (empty-registry corrupted under it)', broke: ['historical_sidecars_accepted', 'artifact_identity_pinned'],
    why: 'the exchange records and the request name the run\'s own copies by identity, and the artifact gate pins the work-copy bytes — a swapped-in tree breaks both, and the corrupted fixture is not the pinned bytes',
    build: () => { const d = freshInv('c12'); const alt = altWork('alt-work-c12');
      fs.appendFileSync(path.join(alt, 'empty-registry.json'), 'x');
      return { dir: d, work: alt }; } },

  { name: 'case duration_ms edited', broke: [],
    why: 'a timing field no gate owns must not move any gate',
    build: () => { const d = freshInv('c13'); const o = loadObs(d); const c = caseOf(o, 'historical_74');
      c.duration_ms = 999999;
      evArgv(d, c, { duration_ms: 999999 });
      saveObs(d, o); return { dir: d }; } },

  { name: 'no observation at all', broke: [], allBlocked: true,
    why: 'absent evidence is blocked, which is a different verdict from failed',
    build: () => { const d = freshInv('c14'); fs.rmSync(path.join(d, 'output.json')); return { dir: d }; } },

  { name: 'frozen scripts named through a symlinked home root', broke: [],
    why: 'a receipt must stay judgeable when the observation spells the root differently than the judging RCOS_HOME',
    build: () => frozenPathsThroughSymlinkedHome() },

  { name: 'invocation tree named through a symlinked root', broke: [],
    why: 'executed-case claims are judged by the files they resolve to, never by the path string',
    build: () => invocationThroughSymlinkedRoot() }
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

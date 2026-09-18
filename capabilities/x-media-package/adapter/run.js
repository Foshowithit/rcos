#!/usr/bin/env node
'use strict';
// Adapter for the x-media-package capability.
//
// Domain work: run the frozen checker that already exists beside this file
// (adapter/xcheck.py — the artifact this entry's historical run_ids name) once
// per media package, and record what it said VERBATIM. The wrapper forms no
// opinion about whether a package is postable: that is the gates' job, and the
// checker's own exit code and printed lines are the things they read.
//
// It never modifies, re-implements or patches the checker. Its sha256 goes into
// the observation so the new receipt names the exact artifact identity it
// exercised, which is what lets a human line this receipt up against the
// historical asserted runs for the same script.
//
// Each package runs in its own scratch directory under the work dir, holding
// copies of the video, caption and alt-text it was given. Two reasons, both
// load-bearing:
//   1. xcheck.py writes x-poster.jpg BESIDE the video it probes. Several
//      packages legitimately share one video (the attack and the boundary
//      controls all re-probe chalk-eval2), so probing from the shared work dir
//      would make every package race for one poster path and leave the last
//      writer owning an artifact no single package produced.
//   2. The checker writes into the directory it reads from. Probing a frozen
//      input in place means a run can mutate the bytes a later gate will pin;
//      a run must read frozen bytes, not write through to them.
// The copy mapping (source, copy, sha256, bytes per role) is recorded in the
// observation, so the bytes the checker actually saw are recoverable and
// comparable to the pins by hash instead of by naming convention.
//
// Kernel interface (lib/invocation.js): the input document is at $RCOS_INPUT,
// the result goes to $RCOS_OUTPUT, supporting files go under $RCOS_EVIDENCE_DIR.
// Exit 4 = could not run; exit 0 = ran and wrote a result.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const inputPath = process.env.RCOS_INPUT;
const outputPath = process.env.RCOS_OUTPUT;
const evidenceDir = process.env.RCOS_EVIDENCE_DIR;
const home = process.env.RCOS_HOME;
const work = process.cwd();

function cannotRun(msg) { console.error(msg); process.exit(4); }

if (!inputPath || !outputPath || !evidenceDir) {
  cannotRun('adapter needs RCOS_INPUT, RCOS_OUTPUT and RCOS_EVIDENCE_DIR in the environment');
}

const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
if (!Array.isArray(input.packages) || input.packages.length === 0) {
  cannotRun('input needs a non-empty packages array');
}

const checker = path.join(__dirname, 'xcheck.py');
if (!fs.existsSync(checker)) cannotRun('checker is missing beside the adapter: ' + checker);

const checkerSha = crypto.createHash('sha256').update(fs.readFileSync(checker)).digest('hex');

// A receipt should not depend on where the checkout lives, nor on whether one of
// its roots is a symlink: node resolves this file's own directory, so __dirname
// can arrive as /private/tmp/... while RCOS_HOME arrives as /tmp/.... Both sides
// are therefore resolved before comparing, and a checker that is genuinely inside
// RCOS_HOME is recorded relative to it.
function realOr(p) { try { return fs.realpathSync(p); } catch (e) { return p; } }
const checkerReal = realOr(checker);
const homeReal = home ? realOr(home) : null;
const underHome = homeReal && (checkerReal === homeReal || checkerReal.startsWith(homeReal + path.sep));
const checkerPath = underHome
  ? path.relative(homeReal, checkerReal).split(path.sep).join('/')
  : checkerReal;

// Paths under the work dir are recorded relative to it, so the observation
// names run-local artifacts without pinning an absolute checkout location.
function workRel(p) {
  const abs = path.resolve(p);
  const rel = path.relative(work, abs);
  return rel === '' ? '.' : (rel.startsWith('..') || path.isAbsolute(rel) ? abs : rel.split(path.sep).join('/'));
}

function sha256File(p) { return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'); }

// Minimal baseline-JPEG size reader (no deps): the poster claim is "a real
// frame of this video", and a JPEG that decodes at dimensions other than the
// video's is not that frame. Returns null when no SOF marker is found.
function jpegSize(buf) {
  if (buf.length < 4 || buf[0] !== 0xFF || buf[1] !== 0xD8) return null;
  let o = 2;
  while (o + 9 < buf.length) {
    if (buf[o] !== 0xFF) { o += 1; continue; }
    const marker = buf[o + 1];
    if (marker === 0xFF || marker === 0x01 || (marker >= 0xD0 && marker <= 0xD9)) { o += 2; continue; }
    const segLen = buf.readUInt16BE(o + 2);
    if ((marker >= 0xC0 && marker <= 0xCF) && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
      return { height: buf.readUInt16BE(o + 5), width: buf.readUInt16BE(o + 7) };
    }
    o += 2 + segLen;
  }
  return null;
}

// Per-package wall clock: ffprobe reads a header and ffmpeg seeks one frame, so
// packages are fast, but the inner bound keeps one wedged package from eating
// the whole invocation budget. The kernel enforces the declared timeout around
// the invocation as a whole.
const PACKAGE_TIMEOUT_MS = 30000;

// The checker prints fixed, one-line-per-fact output. The parsed block is a
// convenience for the gates; the raw text is recorded beside it so a gate can
// check the parse against the bytes it came from.
function parseObserved(stdout) {
  const num = (re) => { const m = stdout.match(re); return m ? Number(m[1]) : null; };
  return {
    video_width: num(/^video (\d+)x\d+ aspect/m),
    video_height: num(/^video \d+x(\d+) aspect/m),
    aspect: num(/^video \d+x\d+ aspect ([\d.]+)/m),
    container_duration_s: num(/^video \d+x\d+ aspect [\d.]+  duration ([\d.]+)s/m),
    size_mb: num(/^video \d+x\d+ aspect [\d.]+  duration [\d.]+s  size ([\d.]+)MB$/m),
    caption_chars: num(/^caption (\d+) chars$/m),
    alt_chars: num(/^alt-text (\d+) chars$/m),
    fail_lines: (stdout.match(/^FAIL (.*)$/gm) || []).map((l) => l.slice(5)),
    pass_marker: /^XCHECK_PASS$/m.test(stdout)
  };
}

function outcomeOf(exitStatus, signal) {
  if (signal) return signal === 'SIGTERM' ? 'timed_out' : 'errored';
  if (exitStatus === 0) return 'passed';
  if (exitStatus === 3) return 'caught';
  if (exitStatus === 4) return 'could_not_probe';
  return 'errored';
}

// The poster seek, spelled exactly as the checker spells it: str(min(1.0, dur/3))
// in python. For the durations under test (3.0, 4.0, 2.0) the double 2/3 prints
// as 0.6666666666666666 in both runtimes; ffmpeg accepts either 1.0 or 1.
function posterSeekArg(durPrinted) {
  const seek = Math.min(1.0, durPrinted / 3);
  return seek >= 1 ? '1.0' : String(seek);
}

const packages = [];
const spawnErrors = [];
for (const p of input.packages) {
  const source = {
    video: path.resolve(p.video),
    caption: path.resolve(p.caption),
    alt: path.resolve(p.alt)
  };
  const runDirName = 'probe-' + p.name;
  const runDir = path.join(work, runDirName);
  fs.mkdirSync(runDir, { recursive: true });
  const copies = [
    { role: 'video', source: source.video, dest: path.join(runDir, 'video' + path.extname(source.video)) },
    { role: 'caption', source: source.caption, dest: path.join(runDir, 'caption.txt') },
    { role: 'alt', source: source.alt, dest: path.join(runDir, 'alt.txt') }
  ];
  const copyRecords = [];
  for (const c of copies) {
    fs.copyFileSync(c.source, c.dest);
    copyRecords.push({
      role: c.role,
      source: workRel(c.source),
      path: workRel(c.dest),
      sha256: sha256File(c.dest),
      bytes: fs.statSync(c.dest).size
    });
  }
  const argv = [copies[0].dest, copies[1].dest, copies[2].dest];
  const startedAt = Date.now();
  const r = spawnSync('python3', [checker, ...argv], {
    cwd: work,
    encoding: 'utf8',
    timeout: PACKAGE_TIMEOUT_MS
  });
  spawnErrors.push(r.error ? p.name + ': ' + r.error.message : null);
  const stdout = r.stdout || '';
  const stderr = r.stderr || '';
  const exitStatus = typeof r.status === 'number' ? r.status : null;
  const observed = parseObserved(stdout);
  // The poster is a claim about a file, so the observation records the file's
  // identity (hash, bytes, real JPEG dimensions), not just that a path was
  // printed. Absent poster records as null; the adapter never manufactures one.
  const posterFile = path.join(runDir, 'x-poster.jpg');
  let poster = null;
  if (fs.existsSync(posterFile)) {
    const buf = fs.readFileSync(posterFile);
    const dim = jpegSize(buf);
    poster = {
      path: workRel(posterFile),
      sha256: crypto.createHash('sha256').update(buf).digest('hex'),
      bytes: buf.length,
      jpeg: buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xD8,
      width: dim ? dim.width : null,
      height: dim ? dim.height : null
    };
  }
  observed.poster = poster;
  observed.poster_seek_s = poster ? posterSeekArg(observed.container_duration_s) : null;
  packages.push({
    name: p.name,
    source: { video: workRel(source.video), caption: workRel(source.caption), alt: workRel(source.alt) },
    run_dir: runDirName,
    argv,
    copies: copyRecords,
    exit_status: exitStatus,
    signal: r.signal || null,
    outcome: outcomeOf(exitStatus, r.signal),
    duration_ms: Date.now() - startedAt,
    observed,
    stdout,
    stderr
  });
}

const observation = {
  schema: 'x-media-package-observation/1',
  checker: {
    path: checkerPath,
    sha256: checkerSha,
    // Read from the checker's own docstring, not from a run: the documented
    // contract is the claim, and the packages above are what actually happened.
    documented_exit_codes: [0, 3, 4]
  },
  packages
};
fs.writeFileSync(outputPath, JSON.stringify(observation, null, 2) + '\n');

// Evidence: the raw text each verdict will be computed from, plus the poster
// bytes each poster claim names. The kernel hashes and lists these; it does not
// judge them.
fs.mkdirSync(evidenceDir, { recursive: true });
for (const p of packages) {
  fs.writeFileSync(path.join(evidenceDir, 'probe-' + p.name + '.stdout.txt'), p.stdout);
  fs.writeFileSync(path.join(evidenceDir, 'probe-' + p.name + '.stderr.txt'), p.stderr);
  fs.writeFileSync(path.join(evidenceDir, 'probe-' + p.name + '.argv.json'), JSON.stringify(p.argv, null, 2) + '\n');
  if (p.observed.poster) {
    fs.copyFileSync(path.join(work, p.observed.poster.path), path.join(evidenceDir, 'probe-' + p.name + '.poster.jpg'));
  }
}
fs.writeFileSync(path.join(evidenceDir, 'checker.sha256'), checkerSha + '  ' + checkerPath + '\n');

// Exit 4 is reserved for "this capability could not run at all" — the
// interpreter is missing, or the checker was killed before it could report.
// A package that exited 3 or 4 was able to run and said something; that is a
// result the gates must see, not a block.
const anyExecuted = packages.some((p) => p.exit_status !== null);
if (!anyExecuted) {
  const detail = spawnErrors.filter(Boolean).join(' | ');
  console.error('no package produced an exit status' + (detail ? ' — ' + detail : ''));
  process.exit(4);
}

console.log('checker sha256 ' + checkerSha.slice(0, 16) + '  ' + checkerPath);
for (const p of packages) {
  console.log('  ' + p.name + ': exit ' + p.exit_status + ' (' + p.outcome + '), poster ' +
    (p.observed.poster ? p.observed.poster.width + 'x' + p.observed.poster.height : 'none') +
    ', ' + p.duration_ms + 'ms');
}
process.exit(0);

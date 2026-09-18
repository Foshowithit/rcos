#!/usr/bin/env node
'use strict';
// Capability adapter for agents-md-compactor.
//
// It OBSERVES: it runs the compactor tool over a fixture and records raw facts
// (file bytes, exit codes, hashes) as the invocation output. It forms no
// opinion — every pass/fail decision belongs to the evaluation's gates.
//
// Three passes, each in its own directory so backups cannot collide:
//   pass1/      the tool's normal run (archive/ exists)
//   pass2/      the tool run on pass1's own output (idempotence input)
//   noarchive/  the same input with archive/ removed (must not mutate anything)
//
// The tool it executes is part of the capability (capabilities/<id>/tool/), so
// `rcos run` and the evaluation execute the same bytes by default. The output
// records the sha256 of the bytes that actually ran, which is what lets the
// evaluation pin provenance instead of trusting a path.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

function cannotRun(msg) {
  process.stderr.write('agents-md-compactor: ' + msg + '\n');
  process.exit(4);
}

const inputFile = process.env.RCOS_INPUT;
const outputFile = process.env.RCOS_OUTPUT;
const evidenceDir = process.env.RCOS_EVIDENCE_DIR;
const capDir = process.env.RCOS_CAPABILITY_DIR;
if (!inputFile || !outputFile || !evidenceDir || !capDir) {
  cannotRun('missing kernel environment (RCOS_INPUT, RCOS_OUTPUT, RCOS_EVIDENCE_DIR, RCOS_CAPABILITY_DIR)');
}

const work = process.cwd();
const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const read = (p) => fs.readFileSync(p, 'utf8');
const copyEvidence = (src, rel) => {
  const dest = path.join(evidenceDir, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
};

let input;
try {
  input = JSON.parse(read(inputFile));
} catch (e) {
  cannotRun('cannot read the invocation input: ' + e.message);
}
if (input === null || typeof input !== 'object' || Array.isArray(input)) cannotRun('input must be a JSON object');
if (typeof input.fixture !== 'string' || input.fixture.length === 0) cannotRun('input.fixture: required (path to the AGENTS.md fixture)');
if (input.tool !== undefined && (typeof input.tool !== 'string' || input.tool.length === 0)) cannotRun('input.tool: must be a non-empty path when present');
if (input.observations !== undefined) {
  if (typeof input.observations !== 'string' || input.observations.length === 0) cannotRun('input.observations: must be a non-empty directory name when present');
  if (input.observations !== path.basename(input.observations)) cannotRun('input.observations: must be a single directory name, not a path');
}

const fixturePath = path.resolve(work, input.fixture);
if (!fs.existsSync(fixturePath)) cannotRun('fixture not found: ' + fixturePath);
const toolPath = input.tool !== undefined
  ? path.resolve(work, input.tool)
  : path.join(capDir, 'tool', 'compact_agents_md.py');
if (!fs.existsSync(toolPath)) cannotRun('compactor tool not found: ' + toolPath);

const observationsDir = path.join(work, input.observations || 'observations');
fs.mkdirSync(observationsDir, { recursive: true });

const toolBytes = fs.readFileSync(toolPath);
const tool = {
  path: toolPath,
  sha256: sha256(toolBytes),
  bytes: toolBytes.length,
  source: input.tool !== undefined ? 'input' : 'capability'
};
copyEvidence(toolPath, 'executed-tool.py');

const fixtureText = read(fixturePath);
const fixtureBytes = fs.readFileSync(fixturePath);
const fixture = {
  path: fixturePath,
  sha256: sha256(fixtureBytes),
  bytes: fixtureBytes.length
};

function setup(name, text) {
  const dir = path.join(observationsDir, name);
  fs.mkdirSync(path.join(dir, 'archive'), { recursive: true });
  const file = path.join(dir, 'AGENTS.md');
  fs.writeFileSync(file, text);
  return { dir, file };
}

// The tool takes the file path as an absolute path only: backup() resolves the
// archive dir from os.path.dirname(path), so a relative path looks for /archive.
function invoke(dir, file) {
  const r = spawnSync('python3', [toolPath, '--file', file], { cwd: dir, encoding: 'utf8' });
  const backups = fs.existsSync(path.join(dir, 'archive'))
    ? fs.readdirSync(path.join(dir, 'archive')).map((n) => path.join(dir, 'archive', n))
    : [];
  return {
    exit: r.status,
    stdout: r.stdout,
    stderr: r.stderr,
    backup: backups.length === 0 ? null : {
      path: path.relative(work, backups[0]),
      sha256: sha256(fs.readFileSync(backups[0]))
    }
  };
}

function observe(name, text) {
  const { dir, file } = setup(name, text);
  const inputSha = sha256(text);
  const res = invoke(dir, file);
  const output = read(file);
  copyEvidence(file, path.join(name, 'AGENTS.after.md'));
  return {
    input: text,
    input_sha256: inputSha,
    output,
    output_sha256: sha256(output),
    exit: res.exit,
    stdout: res.stdout,
    stderr: res.stderr,
    backup: res.backup,
    // whether the tool touched the file at all, independent of its exit code
    mutated: sha256(output) !== inputSha
  };
}

const pass1 = observe('pass1', fixtureText);
copyEvidence(path.join(observationsDir, 'pass1', 'AGENTS.md'), path.join('pass1', 'AGENTS.after.md'));
copyEvidence(fixturePath, path.join('pass1', 'AGENTS.before.md'));
const pass2 = observe('pass2', pass1.output);
copyEvidence(path.join(observationsDir, 'pass2', 'AGENTS.md'), path.join('pass2', 'AGENTS.after.md'));
copyEvidence(path.join(observationsDir, 'pass1', 'AGENTS.md'), path.join('pass2', 'AGENTS.before.md'));

// Third pass: no archive/ directory. The tool cannot write its backup, so it
// must not rewrite the file either.
const noArchiveDir = path.join(observationsDir, 'noarchive');
fs.mkdirSync(noArchiveDir, { recursive: true });
const noArchiveFile = path.join(noArchiveDir, 'AGENTS.md');
fs.writeFileSync(noArchiveFile, fixtureText);
const noArchiveRun = spawnSync('python3', [toolPath, '--file', noArchiveFile],
  { cwd: noArchiveDir, encoding: 'utf8' });
const noArchive = {
  input: fixtureText,
  input_sha256: sha256(fixtureText),
  output: read(noArchiveFile),
  exit: noArchiveRun.status,
  stderr: noArchiveRun.stderr,
  archive_dir_exists: fs.existsSync(path.join(noArchiveDir, 'archive'))
};
copyEvidence(noArchiveFile, path.join('noarchive', 'AGENTS.after.md'));

const observation = { schema: 'compactor-observation/1', tool, fixture, pass1, pass2, noarchive: noArchive };
fs.writeFileSync(outputFile, JSON.stringify(observation, null, 2) + '\n');
copyEvidence(outputFile, 'observations.json');

// The one claim this adapter makes about its own run, as an emission file the
// kernel classifies: the three passes ran, with these exits and these input
// hashes. The invocation id comes from the evidence dir's own path — if it
// disagrees with the run the kernel is sealing, the claim is skipped, not run.
fs.writeFileSync(path.join(evidenceDir, 'compaction.emission.json'), JSON.stringify({
  fields: {
    subject: 'agents-md-compactor/' + path.basename(fixturePath),
    predicate: 'fixture_observed',
    value: {
      tool_sha256: tool.sha256,
      fixture_sha256: fixture.sha256,
      pass1: { exit: pass1.exit, mutated: pass1.mutated },
      pass2: { exit: pass2.exit, mutated: pass2.mutated },
      noarchive: { exit: noArchive.exit, mutated: noArchive.output !== noArchive.input }
    },
      truth_class: 'observation',
      source: { kind: 'action', ref: 'three passes executed inside this invocation' },
      observed_at: new Date().toISOString()
  },
  producer: {
    capability_id: process.env.RCOS_CAPABILITY_ID,
    capability_version: process.env.RCOS_CAPABILITY_VERSION,
    invocation_id: path.basename(path.dirname(evidenceDir))
  }
}, null, 2) + '\n');

console.log('tool ' + tool.sha256.slice(0, 12) + ' (' + tool.bytes + ' bytes) from ' + tool.source);
console.log('pass1 exit=' + pass1.exit + ' mutated=' + pass1.mutated + ' backup=' + (pass1.backup ? pass1.backup.path : 'none'));
console.log('pass2 exit=' + pass2.exit + ' mutated=' + pass2.mutated);
console.log('noarchive exit=' + noArchive.exit + ' mutated=' + (noArchive.output !== noArchive.input));
process.exit(0);

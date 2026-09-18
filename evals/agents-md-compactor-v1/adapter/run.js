'use strict';
// Adapter for agents-md-compactor-v1. It OBSERVES: it runs the frozen tool over
// the fixture and records raw facts (file bytes, exit codes, hashes) in
// ledger.json. It forms no opinion — every pass/fail decision belongs to the
// gates. Three passes, each in its own directory so backups cannot collide:
//   pass1/  the tool's normal run (archive/ exists)
//   pass2/  the tool run on pass1's own output (idempotence input)
//   noarchive/  the same input with archive/ removed (must not mutate anything)
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const work = process.cwd();
const evalDir = process.env.RCOS_EVAL_DIR || path.join(work, '..', '..');
const fixtures = path.join(evalDir, 'fixtures');

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const read = (p) => fs.readFileSync(p, 'utf8');

function setup(name, text) {
  const dir = path.join(work, name);
  fs.mkdirSync(path.join(dir, 'archive'), { recursive: true });
  const file = path.join(dir, 'AGENTS.md');
  fs.writeFileSync(file, text);
  return { dir, file };
}

// The tool takes the file path as an absolute path only: backup() resolves the
// archive dir from os.path.dirname(path), so a relative path looks for /archive.
function invoke(dir, file) {
  const r = spawnSync('python3', [path.join(work, 'tool.py'), '--file', file], { cwd: dir, encoding: 'utf8' });
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

function observe(name, input) {
  const { dir, file } = setup(name, input);
  const inputSha = sha256(input);
  const res = invoke(dir, file);
  const output = read(file);
  return {
    input,
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

const fixtureText = read(path.join(fixtures, 'AGENTS-fixture.md'));
fs.copyFileSync(path.join(fixtures, 'compact_agents_md.py'), path.join(work, 'tool.py'));
const toolBytes = fs.readFileSync(path.join(work, 'tool.py'));

const pass1 = observe('pass1', fixtureText);
const pass2 = observe('pass2', pass1.output);
// Third pass: no archive/ directory. The tool cannot write its backup, so it
// must not rewrite the file either.
const noArchiveDir = path.join(work, 'noarchive');
fs.mkdirSync(noArchiveDir, { recursive: true });
const noArchiveFile = path.join(noArchiveDir, 'AGENTS.md');
fs.writeFileSync(noArchiveFile, fixtureText);
const noArchiveRun = spawnSync('python3', [path.join(work, 'tool.py'), '--file', noArchiveFile],
  { cwd: noArchiveDir, encoding: 'utf8' });
const noArchive = {
  input: fixtureText,
  input_sha256: sha256(fixtureText),
  output: read(noArchiveFile),
  exit: noArchiveRun.status,
  stderr: noArchiveRun.stderr,
  archive_dir_exists: fs.existsSync(path.join(noArchiveDir, 'archive'))
};

const ledger = {
  schema: 'compactor-observation/1',
  tool: { path: 'tool.py', sha256: sha256(toolBytes), bytes: toolBytes.length },
  pass1,
  pass2,
  noarchive: noArchive
};
fs.writeFileSync(path.join(work, 'ledger.json'), JSON.stringify(ledger, null, 2) + '\n');
console.log('pass1 exit=' + pass1.exit + ' mutated=' + pass1.mutated + ' backup=' + (pass1.backup ? pass1.backup.path : 'none'));
console.log('pass2 exit=' + pass2.exit + ' mutated=' + pass2.mutated);
console.log('noarchive exit=' + noArchive.exit + ' mutated=' + (noArchive.output !== noArchive.input));
process.exit(0);

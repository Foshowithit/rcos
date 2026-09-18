'use strict';
// The evidence envelope's own contract, pinned.
//
// Invariant under test:
//   Evidence records what was claimed, by whom, on what basis. It never
//   arbitrates truth, and it is never an authority to act.
//
// What these tests are for: the substrate's honesty properties, not its
// usefulness. A record is write-once and self-hashed; the closed vocabularies
// refuse what they do not name; a derived claim must cite real, non-self,
// acyclic inputs; competing claims coexist and a bundle ranks nothing; and the
// emission path is the only way an invocation's output becomes evidence, with
// the two-way link — the sealed manifest names the ids, the record pins the
// manifest's bytes — checked from both sides.
//
// Where a test pins something that reads like a hole, it says so and says why
// it is intentional. A bare re-sealed record is undetectable by this substrate
// BY DESIGN: the verifier answers internal consistency, not identity. Byte pins
// live in bundles, and in records pinning the manifest they came from — so the
// tests that matter most are the ones showing a re-sealed record is caught by
// the thing that pinned its bytes.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO = path.join(__dirname, '..');
const BIN = path.join(REPO, 'bin', 'rcos');
const EV = require('../lib/evidence');
const E = require('../lib/eligibility');
const I = require('../lib/invocation');

const CONTRACT = {
  schema: 'rcos-capability-contract/1',
  input: {
    type: 'object', required: ['name'], additionalProperties: false,
    // `claims` is the emission plan: each entry is either a claim to emit as
    // evidence or a raw string to write into the emission directory verbatim,
    // which is how the malformed-file refusals get exercised.
    properties: { name: { type: 'string', minLength: 1 }, claims: { type: 'array' } }
  },
  output: {
    type: 'object', required: ['schema', 'greeting'], additionalProperties: false,
    properties: {
      schema: { type: 'string', enum: ['echo/1'] },
      greeting: { type: 'string', minLength: 1 }
    }
  }
};

// The marker is how these tests tell "the adapter ran" from "the envelope
// recorded something": the run and the claim about the run are different facts,
// and the refusal tests need to see the first without the second.
const EMITTER_SRC = [
  '#!/usr/bin/env node',
  "const fs = require('node:fs');",
  "const path = require('node:path');",
  "const input = JSON.parse(fs.readFileSync(process.env.RCOS_INPUT, 'utf8'));",
  "fs.writeFileSync('ran.marker', 'yes');",
  'const evDir = process.env.RCOS_EVIDENCE_DIR;',
  // The adapter knows which invocation it is by the directory it was handed —
  // there is no env var naming the run, and there should not be one: the
  // producer block an adapter writes is checked against the run's own context.
  'const invocationId = path.basename(path.dirname(evDir));',
  'const capabilityId = path.basename(path.dirname(__dirname));',
  'const capabilityVersion = process.env.RCOS_CAPABILITY_VERSION;',
  'for (const c of (input.claims || [])) {',
  "  const file = c.file || 'm0.emission.json';",
  '  if (c.raw !== undefined) { fs.writeFileSync(path.join(evDir, file), c.raw); continue; }',
  '  const body = { fields: c.fields };',
  "  if (c.producer === 'self') {",
  '    body.producer = { capability_id: capabilityId, capability_version: capabilityVersion, invocation_id: invocationId };',
  '  } else if (c.producer !== undefined) {',
  '    body.producer = c.producer;',
  '  }',
  "  fs.writeFileSync(path.join(evDir, file), JSON.stringify(body, null, 2) + '\\n');",
  '}',
  "fs.writeFileSync(process.env.RCOS_OUTPUT, JSON.stringify({ schema: 'echo/1', greeting: 'hello ' + input.name }) + '\\n');",
  ''
].join('\n');

function capability(id, opts = {}) {
  const status = opts.status || 'promoted';
  const c = {
    id, name: 'fixture ' + id, kind: 'script', version: opts.version || '1.0.0', status,
    admitted_after: [], evals: [], reuse_count: opts.reuse_count || 0, last_eval: null
  };
  if (status === 'promoted') {
    c.evals = [
      { task_id: 't-a', verdict: 'ship', run_id: '20260901T000000Z-aaaaaa', provenance: 'executed' },
      { task_id: 't-b', verdict: 'ship', run_id: '20260901T000001Z-bbbbbb', provenance: 'executed' }
    ];
    c.admitted_after = ['t-a', 't-b'];
    c.retirement = {
      armed_at: '2026-09-01', policy_version: 'rcos-retire/1',
      decay: { window: 5, threshold: null }, neglect: { n: 20, threshold: null }
    };
  }
  if (!opts.noAdapter) {
    c.adapter = {
      type: 'command',
      entrypoint: opts.entrypoint || ('capabilities/' + id + '/adapter/run.js'),
      timeout_seconds: 30,
      contract: 'capabilities/' + id + '/contract.json'
    };
  }
  return c;
}

function fx(id, opts = {}) { return Object.assign({}, opts, { cap: capability(id, opts) }); }
const EXECUTABLE = () => [fx('alpha', { contract: CONTRACT }), fx('beta', { contract: CONTRACT })];

function makeHome(fixtures) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-evidence-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  for (const f of fixtures) {
    const dir = path.join(home, 'capabilities', f.cap.id);
    fs.mkdirSync(path.join(dir, 'adapter'), { recursive: true });
    if (!f.cap.adapter) continue;
    const p = path.join(dir, 'adapter', 'run.js');
    fs.writeFileSync(p, EMITTER_SRC);
    fs.chmodSync(p, 0o755);
    fs.writeFileSync(path.join(dir, 'contract.json'), JSON.stringify(f.contract, null, 2) + '\n');
  }
  fs.writeFileSync(path.join(home, 'registry', 'capability-registry.json'),
    JSON.stringify({ registry_version: 'v1', capabilities: fixtures.map((f) => f.cap) }, null, 2) + '\n');
  return home;
}

function bareHome() { return fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-evidence-')); }

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

function decide(home, id, opts = {}) {
  const d = E.decideForHome(home, id, {
    purpose: opts.purpose || 'normal',
    scope: opts.scope || 'execute',
    forensicReason: opts.forensicReason
  });
  assert.equal(d.ok, true, d.error);
  return d;
}

function invoke(home, id, opts = {}) {
  const d = decide(home, id, opts);
  return I.invokeCapability(home, id, Object.assign({}, opts, { eligibilityDecisionId: d.decision_id }));
}

function claim(over = {}) {
  return Object.assign({
    subject: 'line-3 bearing',
    predicate: 'temperature_c',
    value: 61.5,
    truth_class: 'observation',
    source: { kind: 'sensor', ref: 'fixture-sensor-1' },
    observed_at: '2026-09-18T05:00:00Z'
  }, over);
}

function inf(inputs, over = {}) {
  return claim(Object.assign({
    truth_class: 'inference',
    source: { kind: 'derivation', ref: 'fixture-derivation-1' },
    derived: { inputs }
  }, over));
}

function rec(home, fields, opts = {}) {
  const res = EV.createEvidence(home, fields, opts);
  assert.equal(res.ok, true, res.error);
  return res;
}

function refuse(home, fields, opts = {}) {
  const res = EV.createEvidence(home, fields, opts);
  assert.equal(res.ok, false, 'expected a refusal, got a record: ' + JSON.stringify(res.evidence_id));
  return res.error;
}

function writeJson(p, doc) { fs.writeFileSync(p, JSON.stringify(doc, null, 2) + '\n'); }
function evPath(home, id) { return EV.evidencePath(home, id); }
function bundlePathOf(home, id) { return EV.bundlePath(home, id); }
function storeDirs(home) {
  const d = EV.evidenceStoreDir(home);
  return fs.existsSync(d) ? fs.readdirSync(d).sort() : [];
}
function markerPath(res) { return path.join(res.dir, 'work', 'ran.marker'); }

// Tamper, then re-seal: the honest way to test a structural check, because an
// unsealed edit is caught by the hash and would prove nothing about the check
// underneath it. The value hash is recomputed too, so a re-sealed record is
// internally consistent by construction — which is exactly the state the tests
// below need to reason about.
function resealEvidence(home, id, fn) {
  const p = evPath(home, id);
  const doc = JSON.parse(fs.readFileSync(p, 'utf8'));
  fn(doc);
  doc.value_sha256 = EV.sha256(JSON.stringify(doc.value, null, 2) + '\n');
  doc.integrity = { algo: 'sha256', value: EV.evidenceIntegrity(doc) };
  writeJson(p, doc);
  return doc;
}

function resealBundle(home, id, fn) {
  const p = bundlePathOf(home, id);
  const doc = JSON.parse(fs.readFileSync(p, 'utf8'));
  fn(doc);
  doc.integrity = { algo: 'sha256', value: EV.bundleIntegrity(doc) };
  writeJson(p, doc);
  return doc;
}

// The kernel does not export manifestIntegrity, so the clone lives here: the
// tests re-seal a manifest the same way the kernel sealed it, which is the only
// way an edit can be made invisible to the hash check.
function manifestIntegrity(doc) {
  const { integrity, ...rest } = doc;
  return EV.sha256(JSON.stringify(rest, null, 2) + '\n');
}

function resealManifest(home, id, fn) {
  const p = path.join(I.invocationDir(home, id), 'manifest.json');
  const doc = JSON.parse(fs.readFileSync(p, 'utf8'));
  fn(doc);
  doc.integrity = { algo: 'sha256', value: manifestIntegrity(doc) };
  writeJson(p, doc);
  return doc;
}

// One run, one claim emitted, one record minted — the fixture the tamper matrix
// mutates from four directions, each in its own home so the legs stay
// independent.
function emissionHome(claims) {
  const home = makeHome(EXECUTABLE());
  const res = invoke(home, 'alpha', { input: { name: 'ada', claims } });
  assert.equal(res.ok, true, res.error);
  assert.equal(res.status, 'completed', res.basis);
  return { home, res };
}

// ---------------------------------------------------------------------------

test('a direct record seals, verifies, and is write-once', () => {
  const home = bareHome();
  const res = rec(home, claim());
  assert.equal(res.evidence.producer, null, 'a direct record pins no run — the CLI has no flag for one');
  assert.deepEqual(res.evidence.derived.inputs, [], 'an observation derives from nothing');
  assert.equal(fs.readFileSync(res.evidence_path, 'utf8'), JSON.stringify(res.evidence, null, 2) + '\n');

  const v = EV.verifyEvidence(home, res.evidence_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.equal(v.checked, 1, 'nothing to read, so the record is the one check');
  assert.equal(v.evidence.truth_class, 'observation');

  assert.throws(() => EV.createEvidence(home, claim(), { evidenceId: res.evidence_id }),
    /already exists — evidence records are write-once and never rewritten/);

  fs.writeFileSync(path.join(res.dir, 'stray.txt'), 'x');
  const v2 = EV.verifyEvidence(home, res.evidence_id);
  assert.equal(v2.ok, false);
  assert.deepEqual(v2.problems, ['artifact present but not part of an evidence record: stray.txt']);
});

test('two records of one claim agree on the claim and differ only in identity', () => {
  const home = bareHome();
  const a = rec(home, claim());
  const b = rec(home, claim());
  assert.notEqual(a.evidence_id, b.evidence_id);
  assert.equal(a.evidence.value_sha256, b.evidence.value_sha256, 'the same value hashes the same');
  const strip = (d) => {
    const c = JSON.parse(JSON.stringify(d));
    for (const k of ['evidence_id', 'recorded_at', 'created_at', 'integrity']) delete c[k];
    return c;
  };
  assert.deepEqual(strip(a.evidence), strip(b.evidence));
  assert.notEqual(a.evidence.integrity.value, b.evidence.integrity.value);
});

test('the closed vocabularies refuse what they do not name, and nothing is written', () => {
  const home = bareHome();
  const cases = [
    [claim({ subject: '' }), 'subject: a non-empty string is required'],
    [claim({ predicate: '' }), 'predicate: a non-empty string is required'],
    [claim({ value: undefined }), 'value: present but unset is not a claim — supply a value, even null'],
    [claim({ value: 1n }), 'value: must be JSON-serializable'],
    [claim({ truth_class: 'vibe' }), 'truth_class: must be one of ' + EV.TRUTH_CLASSES.join('|')],
    [claim({ source: { kind: 'vibes', ref: 'r' } }), 'source.kind: must be one of ' + EV.SOURCE_KINDS.join('|')],
    [claim({ source: { kind: 'sensor', ref: '' } }), 'source.ref: a non-empty string is required'],
    [claim({ source: { kind: 'sensor', ref: 'r', confidence: 0.9 } }),
      'source.confidence: unknown field — source carries kind and ref only'],
    [claim({ observed_at: 'yesterday' }), 'observed_at: an ISO-8601 timestamp is required'],
    [claim({ valid_at: '2026-09-18T05:00:00Z', expires_at: '2026-09-17T05:00:00Z' }),
      'expires_at: before valid_at — a claim cannot expire before it becomes valid'],
    [claim({ derived: { inputs: ['evid_20260918T050000Z-cccccc'] } }),
      'derived.inputs: only inference records carry inputs — a non-inference claim stands on its source, not on other records'],
    ['not an object', 'evidence fields must be an object'],
    [[], 'evidence fields must be an object']
  ];
  for (const [fields, expected] of cases) {
    assert.equal(refuse(home, fields), expected);
  }
  assert.equal(storeDirs(home).length, 0, 'a refused claim leaves no artifact behind');
});

test('an inference with nothing behind it is refused', () => {
  const home = bareHome();
  const msg = 'derived evidence requires inputs — an inference with nothing behind it is an assertion wearing lineage clothes';
  assert.equal(refuse(home, inf([])), msg);
  assert.equal(refuse(home, claim({ truth_class: 'inference', source: { kind: 'derivation', ref: 'd' } })), msg);
  assert.equal(refuse(home, claim({
    truth_class: 'inference', source: { kind: 'derivation', ref: 'd' }, derived: { inputs: 'evid_x' }
  })), msg);
  assert.equal(storeDirs(home).length, 0);
});

test('lineage names real records, never itself, never twice', () => {
  const home = bareHome();
  const base = rec(home, claim());
  const a = rec(home, inf([base.evidence_id]));

  assert.equal(refuse(home, inf([base.evidence_id, base.evidence_id])),
    'derived.inputs: names \'' + base.evidence_id + '\' more than once — an input set is a set');
  assert.equal(refuse(home, inf(['not-an-id'])), 'derived.inputs: \'not-an-id\' is not an evidence id');
  const missing = 'evid_20260918T050000Z-ffffff';
  assert.equal(refuse(home, inf([missing])), 'derived.inputs: no such evidence record: ' + missing);
  const selfId = 'evid_20260918T050000Z-cccccc';
  assert.equal(refuse(home, inf([selfId]), { evidenceId: selfId }),
    'derived.inputs: cites itself — a record cannot depend on its own existence');

  const v = EV.verifyEvidence(home, a.evidence_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.equal(v.checked, 2, 'the input it read, plus the record itself');
  assert.deepEqual(a.evidence.derived.inputs, [base.evidence_id]);
  assert.equal(EV.readEvidence(home, a.evidence_id).truth_class, 'inference');
});

test('a lineage cycle is refused at mint and caught at read', () => {
  // Mint time: an input whose own recorded inputs point back at the id being
  // minted. The walk reads the store, so a cycle cannot be smuggled in by
  // naming a fresh id.
  const home = bareHome();
  const base = rec(home, claim());
  const a = rec(home, inf([base.evidence_id]));
  const cId = 'evid_20260918T050000Z-dddddd';
  resealEvidence(home, a.evidence_id, (doc) => { doc.derived.inputs = [cId]; });
  assert.equal(refuse(home, inf([a.evidence_id]), { evidenceId: cId }),
    'derived.inputs: lineage cycle — \'' + a.evidence_id + '\' depends, through recorded inputs, on the record being minted');

  // Read time: two records that cite each other, each sealed honestly first and
  // then edited into a cycle. Creation would have refused this shape; the
  // verifier has to notice it anyway, because the store is not append-only in
  // the sense of "uneditable" — it is append-only in the sense that an edit is
  // detectable, and the detection is the walk.
  const home2 = bareHome();
  const base2 = rec(home2, claim());
  const a2 = rec(home2, inf([base2.evidence_id]));
  const b2 = rec(home2, inf([a2.evidence_id]));
  assert.equal(EV.verifyEvidence(home2, b2.evidence_id).ok, true);
  resealEvidence(home2, a2.evidence_id, (doc) => { doc.derived.inputs = [b2.evidence_id]; });
  const v = EV.verifyEvidence(home2, b2.evidence_id);
  assert.equal(v.ok, false);
  assert.deepEqual(v.problems, ['lineage cycle through ' + a2.evidence_id + ' — the record depends on its own existence']);
});

test('competing claims coexist — the envelope ranks nothing', () => {
  const home = bareHome();
  const cold = rec(home, claim({ value: 61.5 }));
  const hot = rec(home, claim({ value: 72.0 }));
  assert.notEqual(cold.evidence.value_sha256, hot.evidence.value_sha256);
  assert.equal(EV.verifyEvidence(home, cold.evidence_id).ok, true);
  assert.equal(EV.verifyEvidence(home, hot.evidence_id).ok, true);

  const b = EV.createBundle(home, [cold.evidence_id, hot.evidence_id], { purpose: 'coexist' });
  assert.equal(b.ok, true, b.error);
  assert.equal(EV.verifyBundle(home, b.bundle_id).ok, true);
  for (const m of b.bundle.members) {
    assert.deepEqual(Object.keys(m).sort(), ['evidence_id', 'evidence_sha256'],
      'a member names a record and its bytes — nothing about which one is right');
  }
  assert.ok(!/rank|winner|preferred|conflict|resolve|confidence|latest/i.test(JSON.stringify(b.bundle)),
    'the artifact has no vocabulary for arbitration, and that absence is the point');
});

test('a bundle pins ids and bytes, and is write-once', () => {
  const home = bareHome();
  const a = rec(home, claim());
  const b = rec(home, inf([a.evidence_id]));
  const res = EV.createBundle(home, [a.evidence_id, b.evidence_id], { purpose: 'dogfood' });
  assert.equal(res.ok, true, res.error);

  assert.equal(res.bundle.schema, 'rcos-evidence-bundle/1');
  assert.equal(res.bundle.purpose, 'dogfood');
  assert.ok(!('consumed_by_invocation_id' in res.bundle),
    'nothing consumed this bundle — the field appears only when an invocation says it did');
  assert.deepEqual(res.bundle.members.map((m) => m.evidence_id),
    [a.evidence_id, b.evidence_id].sort(),
    'members sort by id, because the set hash assumes it — and the ids carry random suffixes, so creation order is not sort order');
  for (const m of res.members) {
    assert.equal(m.evidence_sha256, EV.sha256(fs.readFileSync(evPath(home, m.evidence_id))),
      'the pin is the bytes of the record file, not a summary of its fields');
  }
  assert.equal(res.bundle.evidence_set_sha256, EV.evidenceSetSha256(res.members));
  assert.equal(fs.readFileSync(res.bundle_path, 'utf8'), JSON.stringify(res.bundle, null, 2) + '\n');

  const v = EV.verifyBundle(home, res.bundle_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.equal(v.checked, 3, 'two members verified, plus the bundle itself');

  assert.throws(() => EV.createBundle(home, [a.evidence_id], { bundleId: res.bundle_id }),
    /already exists — bundles are write-once and never rewritten/);
});

test('a bundle refuses what is not a set of verifiable records', () => {
  const home = bareHome();
  const a = rec(home, claim());
  assert.equal(EV.createBundle(home, 'not-an-array').error, 'a bundle pins an array of evidence ids');
  assert.equal(EV.createBundle(home, ['not-an-id']).error, 'not an evidence id: not-an-id');
  assert.equal(EV.createBundle(home, [a.evidence_id, a.evidence_id]).error,
    'bundle names \'' + a.evidence_id + '\' more than once — a bundle pins a set');
  const missing = 'evid_20260918T050000Z-ffffff';
  assert.equal(EV.createBundle(home, [missing]).error,
    'member evidence ' + missing + ' does not verify: evidence not found: ' + missing);
  // An empty set is a set. Nothing here refuses it, because "the evidence I
  // consumed was nothing" is a claim the envelope has no business improving on.
  const empty = EV.createBundle(home, []);
  assert.equal(empty.ok, true);
  assert.equal(EV.verifyBundle(home, empty.bundle_id).ok, true);
  assert.equal(storeDirs(home).filter((n) => n.startsWith('evbnd_')).length, 1);
});

test('a re-sealed record passes its own verifier and fails the bundle that pinned it', () => {
  const home = bareHome();
  const a = rec(home, claim());
  const res = EV.createBundle(home, [a.evidence_id], { purpose: 'pin' });

  resealEvidence(home, a.evidence_id, (doc) => { doc.value = 999.9; });
  assert.equal(EV.verifyEvidence(home, a.evidence_id).ok, true,
    'BY DESIGN: the verifier answers "is this record internally consistent", not "is this the record that was written"');

  const v = EV.verifyBundle(home, res.bundle_id);
  assert.equal(v.ok, false);
  assert.deepEqual(v.problems, ['member \'' + a.evidence_id + '\': evidence_sha256 does not match the record it names'],
    'the byte pin is where identity is checked, and it is checked here');
});

test('a tampered bundle is caught by its own integrity, its set hash, or its stray files', () => {
  const home = bareHome();
  const a = rec(home, claim());
  const b = rec(home, claim({ value: 72.0 }));
  const res = EV.createBundle(home, [a.evidence_id, b.evidence_id], { purpose: 'pin' });
  const dirPath = res.dir;
  const restore = () => {
    writeJson(res.bundle_path, res.bundle);
    for (const n of fs.readdirSync(dirPath)) {
      if (n !== 'bundle.json') fs.rmSync(path.join(dirPath, n), { recursive: true, force: true });
    }
  };

  // Unsealed edit: the document hashes itself.
  writeJson(res.bundle_path, Object.assign({}, res.bundle, { purpose: 'edited' }));
  assert.deepEqual(EV.verifyBundle(home, res.bundle_id).problems,
    ['bundle integrity mismatch — the bundle was edited after it was written']);
  restore();

  // Re-sealed, members reversed: the set hash no longer matches the member
  // list, and the sort-order rule the set hash depends on is violated. Two
  // independent problems, both structural.
  resealBundle(home, res.bundle_id, (doc) => { doc.members.reverse(); });
  const p = EV.verifyBundle(home, res.bundle_id).problems;
  assert.equal(p.length, 2, p.join('; '));
  assert.ok(p.some((q) => q === 'evidence_set_sha256 does not match the pinned member set'));
  assert.ok(p.some((q) => q === 'members are not in evidence_id sort order — the set hash assumes sorted order'));
  restore();

  fs.writeFileSync(path.join(dirPath, 'notes.txt'), 'x');
  assert.deepEqual(EV.verifyBundle(home, res.bundle_id).problems,
    ['artifact present but not part of a bundle: notes.txt']);
  restore();
  assert.equal(EV.verifyBundle(home, res.bundle_id).ok, true, 'restore puts it back exactly');
});

test('an emitted claim becomes a record that pins the run, both ways', () => {
  const { home, res } = emissionHome([{ file: 'm1.emission.json', fields: claim(), producer: 'self' }]);
  assert.ok(fs.existsSync(markerPath(res)), 'the adapter ran');

  assert.equal(res.emitted_evidence.length, 1);
  const e = res.emitted_evidence[0];
  assert.equal(e.file, 'm1.emission.json');
  assert.match(e.evidence_sha256, /^[0-9a-f]{64}$/);

  // The sealed half: ids only. A record hash cannot seal into the manifest,
  // because the manifest's own bytes are what the record has to pin.
  assert.deepEqual(res.manifest.emitted_evidence, [{ file: e.file, evidence_id: e.evidence_id }]);
  assert.deepEqual(res.manifest.emission_skipped, []);
  assert.ok(res.manifest.evidence.some((x) => x.path === 'evidence/m1.emission.json'),
    'the emission file is an artifact of the run, whether or not it was recorded');

  // The returned object is not the evidence — the sealed bytes are. Read the
  // manifest off disk and check the link there, because that is the half a
  // reader of this home sees. Asserting only against the returned object is
  // how the manifest-to-record half goes vacuous: an array handed to the
  // manifest and appended to after the seal leaves every in-memory check
  // passing while the file on disk names nothing.
  const sealedBytes = fs.readFileSync(path.join(res.dir, 'manifest.json'), 'utf8');
  assert.equal(JSON.stringify(res.manifest, null, 2) + '\n', sealedBytes,
    'the returned manifest and the sealed bytes are one document');
  const sealedManifest = JSON.parse(sealedBytes);
  assert.deepEqual(sealedManifest.emitted_evidence, [{ file: e.file, evidence_id: e.evidence_id }]);
  assert.deepEqual(sealedManifest.emission_skipped, []);
  assert.ok(fs.existsSync(evPath(home, e.evidence_id)), 'the sealed manifest names a record that exists on disk');

  // The record half: the producer block pins the invocation by id and by the
  // manifest's bytes.
  const doc = JSON.parse(fs.readFileSync(evPath(home, e.evidence_id), 'utf8'));
  assert.equal(doc.producer.invocation_id, res.invocation_id);
  assert.equal(doc.producer.capability_id, 'alpha');
  assert.equal(doc.producer.capability_version, '1.0.0');
  assert.equal(doc.producer.invocation_manifest_sha256, res.manifest_sha256);
  assert.equal(res.manifest_sha256, EV.sha256(fs.readFileSync(path.join(res.dir, 'manifest.json'))));
  assert.equal(e.evidence_sha256, EV.sha256(fs.readFileSync(evPath(home, e.evidence_id))));

  const v = EV.verifyEvidence(home, e.evidence_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.equal(v.checked, 1);
  assert.equal(EV.listEvidence(home)[0].producer_invocation_id, res.invocation_id);
  assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true);
});

test('an adapter that emits nothing leaves two empty lists, not a gap', () => {
  const { home, res } = emissionHome([]);
  assert.deepEqual(res.manifest.emitted_evidence, []);
  assert.deepEqual(res.manifest.emission_skipped, []);
  assert.deepEqual(res.emitted_evidence, []);
  assert.deepEqual(res.emission_skipped, []);
  assert.deepEqual(res.manifest.evidence, [], 'the evidence directory is empty because nothing was written to it');
  assert.equal(storeDirs(home).length, 0);
  assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true);
});

test('a refused emission is reported, never recorded, and never fails the run', () => {
  const { home, res } = emissionHome([
    { file: 'a.emission.json', raw: '{not json' },
    { file: 'b.emission.json', fields: claim(), producer: { capability_id: 'alpha', capability_version: '1.0.0', invocation_id: 'inv_20260918T000000Z-aaaaaa' } },
    { file: 'c.emission.json', fields: claim({ truth_class: 'vibe' }) },
    { file: 'd.emission.json', fields: claim() }
  ]);

  assert.equal(res.status, 'completed', 'the run happened');
  assert.ok(fs.existsSync(markerPath(res)));
  assert.equal(res.emitted_evidence.length, 1, 'only the claim that checked out was recorded');
  assert.equal(res.emitted_evidence[0].file, 'd.emission.json');
  assert.equal(res.emission_skipped.length, 3);
  const reasons = res.emission_skipped.map((s) => s.file + ' :: ' + s.reason);
  assert.ok(reasons.some((r) => r.startsWith('a.emission.json :: emission file is not valid JSON')), reasons.join('\n'));
  assert.ok(reasons.some((r) => r === 'b.emission.json :: producer block does not name this invocation — an adapter emits evidence about its own run only'), reasons.join('\n'));
  assert.ok(reasons.some((r) => r.startsWith('c.emission.json :: truth_class: must be one of')), reasons.join('\n'));

  assert.equal(res.manifest.emission_skipped.length, 3, 'the refusals seal into the manifest with the record ids that were minted');
  assert.equal(res.manifest.evidence.length, 4, 'a refused emission file is still an artifact of the run');
  assert.equal(storeDirs(home).length, 1);
  assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true);
});

test('a record edited after minting is caught through the run that pinned it', () => {
  // (a) An unsealed edit fails both verifiers: the record's own hash, and the
  // run's re-check of the record it emitted.
  const legA = emissionHome([{ file: 'm1.emission.json', fields: claim() }]);
  const idA = legA.res.emitted_evidence[0].evidence_id;
  const docA = JSON.parse(fs.readFileSync(evPath(legA.home, idA), 'utf8'));
  docA.value = 7;
  writeJson(evPath(legA.home, idA), docA);
  assert.equal(EV.verifyEvidence(legA.home, idA).ok, false);
  const vA = I.verifyInvocation(legA.home, legA.res.invocation_id);
  assert.equal(vA.ok, false);
  assert.ok(vA.problems.some((p) => p.startsWith('emitted evidence ' + idA + ' does not verify:')), vA.problems.join('; '));

  // (b) A re-sealed edit passes both. BY DESIGN: the substrate checks that a
  // record is internally consistent, not that it is the record that was
  // written. Identity is pinned by bytes, and byte pins live in bundles and in
  // records pinning manifests — never in the record's own verifier.
  const legB = emissionHome([{ file: 'm1.emission.json', fields: claim() }]);
  const idB = legB.res.emitted_evidence[0].evidence_id;
  resealEvidence(legB.home, idB, (doc) => { doc.value = 7; });
  assert.equal(EV.verifyEvidence(legB.home, idB).ok, true);
  assert.equal(I.verifyInvocation(legB.home, legB.res.invocation_id).ok, true);

  // (c) A re-sealed manifest is caught by the record that pinned its bytes, and
  // the run's verifier reports it through the record.
  const legC = emissionHome([{ file: 'm1.emission.json', fields: claim() }]);
  const idC = legC.res.emitted_evidence[0].evidence_id;
  resealManifest(legC.home, legC.res.invocation_id, (m) => { m.basis = 'edited after the fact'; });
  const vC = EV.verifyEvidence(legC.home, idC);
  assert.equal(vC.ok, false);
  assert.deepEqual(vC.problems, ['producer invocation changed since the record was written: ' + legC.res.invocation_id]);
  const vI = I.verifyInvocation(legC.home, legC.res.invocation_id);
  assert.equal(vI.ok, false);
  assert.ok(vI.problems.some((p) => p.includes('emitted evidence ' + idC + ' does not verify:')), vI.problems.join('; '));

  // (d) The emission file is an artifact of the run, so editing it is caught by
  // the manifest even though the record it produced still verifies.
  const legD = emissionHome([{ file: 'm1.emission.json', fields: claim() }]);
  const idD = legD.res.emitted_evidence[0].evidence_id;
  fs.appendFileSync(path.join(legD.res.dir, 'evidence', 'm1.emission.json'), ' ');
  assert.equal(EV.verifyEvidence(legD.home, idD).ok, true);
  const vD = I.verifyInvocation(legD.home, legD.res.invocation_id);
  assert.equal(vD.ok, false);
  assert.ok(vD.problems.some((p) => p === 'artifact changed since the invocation was written: evidence/m1.emission.json'), vD.problems.join('; '));
});

test('recording and bundling grant nothing', () => {
  const home = makeHome(EXECUTABLE());
  const registryPath = path.join(home, 'registry', 'capability-registry.json');
  const before = fs.readFileSync(registryPath);
  const a = rec(home, claim());
  const b = rec(home, inf([a.evidence_id]));
  EV.createBundle(home, [a.evidence_id, b.evidence_id], { purpose: 'dogfood' });
  assert.deepEqual(fs.readFileSync(registryPath), before, 'the registry is untouched');
  assert.equal(fs.existsSync(path.join(home, 'invocations')), false, 'evidence is not an execution');
  assert.equal(fs.existsSync(path.join(home, 'eligibility')), false, 'evidence is not a permission');
  assert.equal(fs.existsSync(path.join(home, 'selections')), false, 'evidence is not a choice');
});

test('the CLI round-trips a claim, a bundle, and their refusals', () => {
  const home = bareHome();
  const fieldsPath = path.join(home, 'claim.json');
  writeJson(fieldsPath, claim());

  const r1 = run(home, 'evidence', '--input', fieldsPath);
  assert.equal(r1.status, 0, r1.stderr);
  assert.match(r1.stdout, /^TRUTH_CLASS: observation$/m);
  assert.match(r1.stdout, /^SOURCE: sensor:fixture-sensor-1$/m);
  assert.match(r1.stdout, /^subject: line-3 bearing$/m);
  assert.match(r1.stdout, /^predicate: temperature_c$/m);
  assert.match(r1.stdout, /^NOTE: this records what was claimed, by whom, on what basis — it decides nothing\.$/m);
  const id = r1.stdout.match(/^evidence: (evid_\S+)\t/m)[1];
  assert.match(id, EV.EVIDENCE_ID_RE);

  const r2 = run(home, 'evidence-verify', '--evidence', id);
  assert.equal(r2.status, 0, r2.stderr);
  assert.match(r2.stdout, /^evidence \S+ verified \(1 check\(s\)\)$/m);

  const r3 = run(home, 'evidences');
  assert.equal(r3.status, 0);
  assert.ok(r3.stdout.split('\n').some((l) => l.startsWith(id + '\tobservation\tsensor:fixture-sensor-1\t')), r3.stdout);

  const r4 = run(home, 'bundle', '--evidence', id, '--purpose', 'dogfood');
  assert.equal(r4.status, 0, r4.stderr);
  assert.match(r4.stdout, /^MEMBERS: 1$/m);
  assert.match(r4.stdout, /^purpose: dogfood$/m);
  assert.match(r4.stdout, /^NOTE: a bundle pins a set of records — it ranks nothing and resolves no disagreement\.$/m);
  const bid = r4.stdout.match(/^bundle: (evbnd_\S+)\t/m)[1];
  assert.match(bid, EV.BUNDLE_ID_RE);

  const r5 = run(home, 'bundle-verify', '--bundle', bid);
  assert.equal(r5.status, 0, r5.stderr);
  assert.match(r5.stdout, /^bundle \S+ verified \(2 check\(s\)\)$/m);

  const r6 = run(home, 'bundles');
  assert.equal(r6.status, 0);
  assert.ok(r6.stdout.split('\n').some((l) => l.startsWith(bid + '\t1\tdogfood\t-\t')), r6.stdout);

  const r7 = run(home, 'evidence-verify', '--evidence', 'evid_20260918T050000Z-ffffff');
  assert.equal(r7.status, 3);
  assert.match(r7.stdout, /^PROBLEM evidence not found: evid_20260918T050000Z-ffffff$/m);
  assert.match(r7.stdout, /^evidence verification FAILED$/m);

  const r8 = run(home, 'bundle-verify', '--bundle', 'evbnd_20260918T050000Z-ffffff');
  assert.equal(r8.status, 3);
  assert.match(r8.stdout, /^bundle verification FAILED$/m);

  const badPath = path.join(home, 'bad.json');
  writeJson(badPath, claim({ truth_class: 'vibe' }));
  const r9 = run(home, 'evidence', '--input', badPath);
  assert.equal(r9.status, 2);
  assert.match(r9.stderr, /truth_class: must be one of/);
  assert.equal(EV.listEvidence(home).length, 1, 'the refused claim left the store alone');

  const r10 = run(home, 'evidence', '--input', path.join(home, 'nope.json'));
  assert.equal(r10.status, 2);
  assert.match(r10.stderr, /^rcos: --input is not readable JSON: /);

  const r11 = run(home, 'evidence-verify', '--evidence', id, '--json');
  assert.equal(r11.status, 0);
  const parsed = JSON.parse(r11.stdout);
  assert.deepEqual(parsed, { ok: true, problems: [], checked: 1 });
});

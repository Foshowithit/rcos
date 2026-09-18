'use strict';
// The selection bus's own contract, pinned.
//
// Invariant under test:
//   Selection may choose only among capabilities already proven eligible to
//   compete. Selection never grants execution authority.
//
// What these tests are for: selection is the only place in RCOS where a choice
// is made, so the things worth pinning are the properties of the *socket*
// rather than the quality of any choice — the candidate set is exact and
// re-verified, the artifact is sealed and write-once, a selector cannot return
// a status the core owns, a selector cannot select outside the set, the core
// never reads what a selector asked for, selecting executes nothing, and a
// winner still needs a fresh scope=execute decision before any adapter runs.
//
// Six failure pins are called out by name where they appear. Every one of them
// must fail closed: no adapter side effect, no silent substitution, and an
// artifact only where an artifact is honest.
//
// The selector fixtures below live in this file and are NOT candidates for
// shipping. They exist to drive the interface from outside the shipped
// registry, which is how the replaceable-interface and misbehaving-selector
// rules get exercised without putting a second selector in lib/.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO = path.join(__dirname, '..');
const BIN = path.join(REPO, 'bin', 'rcos');
const S = require('../lib/selection');
const E = require('../lib/eligibility');
const I = require('../lib/invocation');

const CONTRACT = {
  schema: 'rcos-capability-contract/1',
  input: {
    type: 'object', required: ['name'], additionalProperties: false,
    properties: { name: { type: 'string', minLength: 1 } }
  },
  output: {
    type: 'object', required: ['schema', 'greeting'], additionalProperties: false,
    properties: {
      schema: { type: 'string', enum: ['echo/1'] },
      greeting: { type: 'string', minLength: 1 }
    }
  }
};

// The marker is how these tests tell "selected" from "executed": eligibility and
// selection must never produce it, and only the kernel may.
const ADAPTER_SRC = [
  '#!/usr/bin/env node',
  "const fs = require('node:fs');",
  "const input = JSON.parse(fs.readFileSync(process.env.RCOS_INPUT, 'utf8'));",
  "fs.writeFileSync('ran.marker', 'yes');",
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
    // Executed provenance, because a normal-context decision requires evidence
    // RCOS itself produced.
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

// Two executable capabilities (the only kind that can be a candidate today,
// because competability and executability are the same question until a
// selector exists that asks the first one on its own) plus one that is not
// executable at all.
const EXECUTABLE = () => [fx('alpha', { contract: CONTRACT }), fx('beta', { contract: CONTRACT })];
const WITH_LEGACY = () => EXECUTABLE().concat([fx('legacy', { contract: CONTRACT, noAdapter: true })]);

function makeHome(fixtures) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-selection-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  for (const f of fixtures) {
    const dir = path.join(home, 'capabilities', f.cap.id);
    fs.mkdirSync(path.join(dir, 'adapter'), { recursive: true });
    if (!f.cap.adapter) continue;
    const p = path.join(dir, 'adapter', 'run.js');
    fs.writeFileSync(p, ADAPTER_SRC);
    fs.chmodSync(p, 0o755);
    fs.writeFileSync(path.join(dir, 'contract.json'), JSON.stringify(f.contract, null, 2) + '\n');
  }
  fs.writeFileSync(path.join(home, 'registry', 'capability-registry.json'),
    JSON.stringify({ registry_version: 'v1', capabilities: fixtures.map((f) => f.cap) }, null, 2) + '\n');
  return home;
}

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

// The engine's answer, asked the way the CLI asks it.
function decide(home, id, opts = {}) {
  const d = E.decideForHome(home, id, {
    purpose: opts.purpose || 'normal',
    scope: opts.scope || 'execute',
    forensicReason: opts.forensicReason
  });
  assert.equal(d.ok, true, d.error);
  return d;
}

function compete(home, id) {
  const d = decide(home, id, { purpose: 'eval', scope: 'compete' });
  assert.equal(d.eligible, true, id + ' cannot compete: ' + (d.reasons || []).join(', '));
  return d;
}

function select(home, opts) {
  const res = S.createSelection(home, opts);
  assert.equal(res.ok, true, res.error);
  return res;
}

function selectionPath(home, id) { return path.join(S.selectionDir(home, id), 'selection.json'); }
function decisionPath(home, id) { return path.join(E.decisionDir(home, id), 'decision.json'); }
function markerPath(res) { return path.join(res.dir, 'work', 'ran.marker'); }
function selectionsExist(home) { return fs.existsSync(S.selectionsDir(home)); }
function writeJson(p, doc) { fs.writeFileSync(p, JSON.stringify(doc, null, 2) + '\n'); }

// Tamper, then re-seal: the honest way to test a structural check, because an
// unsealed edit is caught by the hash and would prove nothing about the check
// underneath it.
function resealDecision(home, id, fn) {
  const p = decisionPath(home, id);
  const doc = JSON.parse(fs.readFileSync(p, 'utf8'));
  fn(doc);
  doc.integrity = { algo: 'sha256', value: E.decisionIntegrity(doc) };
  writeJson(p, doc);
}

function resealSelection(home, id, fn) {
  const p = selectionPath(home, id);
  const doc = JSON.parse(fs.readFileSync(p, 'utf8'));
  fn(doc);
  doc.integrity = { algo: 'sha256', value: S.selectionIntegrity(doc) };
  writeJson(p, doc);
}

function invoke(home, id, opts = {}) {
  const purpose = opts.purpose || opts.mode || 'normal';
  const d = decide(home, id, { purpose });
  assert.equal(d.eligible, true, id + ': ' + (d.reasons || []).join(', '));
  const res = I.invokeCapability(home, id, Object.assign({}, opts, { eligibilityDecisionId: d.decision_id }));
  res.eligibility_decision = d;
  return res;
}

// ---------------------------------------------------------------------------
// The protocol.

test('selection: explicit picks a member of the verified set, and the artifact seals itself', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const res = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });

  assert.equal(res.status, 'selected');
  assert.equal(res.selected_capability_id, 'alpha');
  assert.equal(res.candidates.length, 2);

  const doc = res.selection;
  assert.equal(doc.schema, 'rcos-selection/1');
  assert.equal(doc.selection_id, res.selection_id);
  assert.deepEqual(doc.selector, { id: 'explicit', version: '1' });
  assert.deepEqual(doc.selector_input, { capability_id: 'alpha' });
  assert.equal(doc.selector_input_sha256, S.sha256(JSON.stringify({ capability_id: 'alpha' }, null, 2) + '\n'));
  assert.equal(doc.candidate_set_sha256, S.candidateSetSha256(doc.candidates));
  // Every candidate pins the decision it came from, by id and by bytes.
  for (const c of doc.candidates) {
    assert.ok(E.isDecisionId(c.eligibility_decision_id), c.eligibility_decision_id);
    assert.match(c.eligibility_sha256, /^[0-9a-f]{64}$/);
    assert.equal(c.eligibility_sha256, S.sha256(fs.readFileSync(decisionPath(home, c.eligibility_decision_id))));
  }

  const v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.equal(v.checked, 3, 'two candidate decisions plus the selection itself');
  // The artifact on disk is the artifact that was returned, byte for byte.
  assert.equal(fs.readFileSync(selectionPath(home, res.selection_id), 'utf8'), JSON.stringify(doc, null, 2) + '\n');
});

test('selection: the same inputs produce the same artifact bytes', () => {
  // Two runs in ONE home, so the candidate decisions are literally the same
  // artifacts. They are given different record ids, because that is the only
  // thing allowed to differ: a selection is a pure function of (selector,
  // selector input, candidate set, clock). Everything else in the file is
  // record identity.
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const now = new Date('2026-09-18T05:00:00.000Z');
  const base = {
    selectorInput: { capability_id: 'beta' },
    candidateDecisionIds: [dA.decision_id, dB.decision_id],
    now
  };
  const first = select(home, Object.assign({}, base, { selectionId: 'sel_20260918T050000Z-aaaaaa' }));
  const second = select(home, Object.assign({}, base, { selectionId: 'sel_20260918T050000Z-bbbbbb' }));
  assert.equal(first.selected_capability_id, 'beta');
  assert.equal(second.selected_capability_id, 'beta');

  // The pins and the decision are identical, field for field.
  assert.equal(first.selector_input_sha256, second.selector_input_sha256);
  assert.equal(first.candidate_set_sha256, second.candidate_set_sha256);
  assert.equal(first.status, second.status);
  assert.equal(first.status_basis, second.status_basis);
  assert.equal(first.decided_at, second.decided_at);

  // And the sealed body is byte-identical once the two record-identity fields
  // are removed — the seal itself is not, because the id it covers changed.
  const body = (id) => {
    const doc = JSON.parse(fs.readFileSync(selectionPath(home, id), 'utf8'));
    delete doc.selection_id;
    delete doc.created_at;
    delete doc.integrity;
    return JSON.stringify(doc, null, 2) + '\n';
  };
  assert.equal(body(first.selection_id), body(second.selection_id));
  assert.notEqual(first.selection.integrity.value, second.selection.integrity.value);
});

test('selection: an empty candidate set is no_candidates, and no selector is convened', () => {
  const home = makeHome(EXECUTABLE());
  let convened = false;
  const probe = {
    id: 'probe', version: '1',
    validateInput: () => [],
    select: () => { convened = true; throw new Error('must never be asked to choose from nothing'); }
  };
  const res = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [], selectors: { explicit: S.explicit, probe } });
  assert.equal(res.status, 'no_candidates');
  assert.equal(res.selected_capability_id, null);
  assert.deepEqual(res.candidates, []);
  assert.equal(convened, false, 'the core owns this outcome; a selector never gets a say in it');
  assert.match(res.status_basis, /no selector was convened/);
  const v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, true, v.problems.join('; '));
});

// PIN 1 — explicit(nonexistent) must fail closed.
test('selection: explicit abstains on a request outside the set, and never substitutes', () => {
  const home = makeHome(WITH_LEGACY());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const res = select(home, { selectorInput: { capability_id: 'not-a-capability' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });
  assert.equal(res.status, 'abstained');
  assert.equal(res.selected_capability_id, null);
  assert.match(res.status_basis, /is not in the eligible candidate set \[alpha, beta\]/);
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);

  // The same refusal for a capability that exists and is real and simply is not
  // a candidate: naming it is not a way to promote it.
  const res2 = select(home, { selectorInput: { capability_id: 'legacy' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });
  assert.equal(res2.status, 'abstained');
  assert.equal(res2.selected_capability_id, null);
});

// PIN 2 — explicit(ineligible legacy cap) must fail closed.
test('selection: a capability that cannot compete cannot become a candidate', () => {
  const home = makeHome(WITH_LEGACY());
  const dA = compete(home, 'alpha');
  const legacy = decide(home, 'legacy', { purpose: 'eval', scope: 'compete' });
  assert.equal(legacy.eligible, false, 'the fixture is supposed to be compete-ineligible');
  assert.deepEqual(legacy.reasons, ['not_executable']);

  const refused = S.createSelection(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, legacy.decision_id] });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /does not permit competition: not_executable/);
  assert.equal(selectionsExist(home), false, 'a malformed request writes nothing at all');
});

test('selection: a scope=execute decision is not a candidate', () => {
  const home = makeHome(EXECUTABLE());
  const exec = decide(home, 'alpha', { purpose: 'normal', scope: 'execute' });
  assert.equal(exec.eligible, true);
  const refused = S.createSelection(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [exec.decision_id] });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /has scope 'execute'/);
  assert.equal(selectionsExist(home), false);
});

test('selection: the candidate set is a set — two decisions for one capability is refused', () => {
  const home = makeHome(EXECUTABLE());
  const a1 = compete(home, 'alpha');
  const a2 = compete(home, 'alpha');
  assert.notEqual(a1.decision_id, a2.decision_id);
  const refused = S.createSelection(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [a1.decision_id, a2.decision_id] });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /more than once/);
});

test('selection: a decision id that is not a decision id is refused', () => {
  const home = makeHome(EXECUTABLE());
  const refused = S.createSelection(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: ['elig_not-an-id'] });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /is not a decision id/);
});

// PIN 3 — tampered candidate eligibility must fail closed.
test('selection: a tampered candidate decision invalidates the selection', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const res = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);

  // (a) edited bytes, not re-sealed: caught by the decision's own integrity.
  const raw = fs.readFileSync(decisionPath(home, dA.decision_id), 'utf8');
  writeJson(decisionPath(home, dA.decision_id), Object.assign(JSON.parse(raw), { eligible: false }));
  let v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /does not verify/);

  // (b) edited and re-sealed, so the hash agrees: now the eligibility check
  //     underneath it is the thing that has to hold.
  resealDecision(home, dA.decision_id, (doc) => { doc.eligible = false; doc.reasons = ['not_executable']; });
  v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /does not permit competition/);
  // And the decision is still a perfectly valid artifact — the selection is what
  // is no longer true.
  assert.equal(E.verifyDecision(home, dA.decision_id).ok, true);
});

// PIN 4 — a tampered selection must fail closed.
test('selection: a tampered selection fails closed', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const res = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });

  // (a) edited bytes: the self-hash catches it.
  const doc = JSON.parse(fs.readFileSync(selectionPath(home, res.selection_id), 'utf8'));
  doc.selected_capability_id = 'beta';
  writeJson(selectionPath(home, res.selection_id), doc);
  let v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /integrity mismatch/);

  // (b) edited and re-sealed into an internally inconsistent record: status says
  //     a capability was chosen and no capability is named. Re-sealing cannot
  //     make that true.
  resealSelection(home, res.selection_id, (d) => { d.status = 'selected'; d.selected_capability_id = null; });
  v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /is not a candidate/);

  // (c) an abstention that names a capability is refused too.
  resealSelection(home, res.selection_id, (d) => { d.status = 'abstained'; d.selected_capability_id = 'alpha'; });
  v = S.verifySelection(home, res.selection_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /only 'selected' names a capability/);
});

// PIN 5 — a selection naming a candidate that is not in the set must fail closed.
test('selection: a selector that names something outside the set produces failed, not a selection', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const ids = [dA.decision_id, dB.decision_id];

  const liar = { id: 'liar', version: '1', validateInput: () => [], select: () => ({ status: 'selected', selected_capability_id: 'gamma' }) };
  const res = select(home, { selectorId: 'liar', selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: ids, selectors: { explicit: S.explicit, liar } });
  assert.equal(res.status, 'failed');
  assert.equal(res.selected_capability_id, null);
  assert.match(res.status_basis, /which is not a capability in the candidate set/);
  // `failed` is a fact about the selector, so it is worth an artifact — and the
  // artifact still verifies, because the core recorded exactly what happened.
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);
});

test('selection: a misbehaving selector cannot return a status the core owns, or crash the run', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const ids = [dA.decision_id, dB.decision_id];

  const cases = [
    { id: 'thrower', version: '1', validateInput: () => [], select: () => { throw new Error('kaboom'); }, expect: /threw: kaboom/ },
    { id: 'empty', version: '1', validateInput: () => [], select: () => null, expect: /returned null, not a result object/ },
    { id: 'corestatus', version: '1', validateInput: () => [], select: () => ({ status: 'no_candidates', selected_capability_id: null }), expect: /no_candidates and failed are the core's to report/ },
    { id: 'elected', version: '1', validateInput: () => [], select: () => ({ status: 'abstained', selected_capability_id: 'alpha' }), expect: /an abstention or an ambiguity selects nothing/ }
  ];
  for (const c of cases) {
    const res = select(home, { selectorId: c.id, selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: ids, selectors: { explicit: S.explicit, [c.id]: c } });
    assert.equal(res.status, 'failed', c.id);
    assert.equal(res.selected_capability_id, null, c.id);
    assert.match(res.status_basis, c.expect, c.id);
    assert.equal(S.verifySelection(home, res.selection_id).ok, true, c.id);
  }
});

test('selection: the statuses are structurally distinct', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const ids = [dA.decision_id, dB.decision_id];
  const ambiguous = {
    id: 'ambiguous', version: '1', validateInput: () => [],
    select: () => ({ status: 'ambiguous', selected_capability_id: null, reason: 'two candidates, no rule' })
  };
  const res = select(home, { selectorId: 'ambiguous', selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: ids, selectors: { explicit: S.explicit, ambiguous } });
  assert.equal(res.status, 'ambiguous');
  assert.equal(res.selected_capability_id, null);
  assert.equal(res.status_basis, 'two candidates, no rule');
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);

  // Only `selected` may proceed, and that is decided by the status alone.
  const listing = S.listSelections(home);
  assert.equal(listing.length, 1);
  assert.equal(listing[0].status, 'ambiguous');
  assert.equal(listing[0].selected_capability_id, null);
});

test('selection: a non-shipped selector drives the identical protocol', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const other = {
    id: 'workflow-declared', version: '0.3', validateInput: (doc) => (doc && doc.workflow ? [] : ['workflow: required']),
    select: ({ candidates, selector_input }) => ({
      status: 'selected',
      selected_capability_id: selector_input.workflow === 'w1' ? candidates[1].capability_id : candidates[0].capability_id,
      reason: 'declared by workflow w1'
    })
  };
  const res = select(home, {
    selectorId: 'workflow-declared', selectorVersion: '0.3',
    selectorInput: { workflow: 'w1' }, candidateDecisionIds: [dA.decision_id, dB.decision_id],
    selectors: { explicit: S.explicit, 'workflow-declared': other }
  });
  assert.equal(res.status, 'selected');
  assert.equal(res.selected_capability_id, 'beta');
  assert.deepEqual(res.selection.selector, { id: 'workflow-declared', version: '0.3' });
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);
});

test('selection: the core does not read what a selector asked for', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const ids = [dA.decision_id, dB.decision_id];

  // The shipped selector's vocabulary is closed, so an input shaped like a
  // routing request is refused rather than quietly accepted as one.
  const refused = S.createSelection(home, {
    selectorInput: { capability_id: 'alpha', task_text: 'make a video', similarity: { beta: 0.9 } },
    candidateDecisionIds: ids
  });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /unknown field/);
  assert.equal(selectionsExist(home), false);

  // And the core itself has no vocabulary at all: a selector with its own input
  // schema can ask for whatever it wants, and the core stores and hashes the
  // bytes without interpreting them.
  const opaque = {
    id: 'opaque', version: '1', validateInput: () => [],
    select: ({ candidates }) => ({ status: 'selected', selected_capability_id: candidates[0].capability_id })
  };
  const exotic = { task_text: 'make a video', intent: 'produce', scores: { alpha: 0.4, beta: 0.6 } };
  const res = select(home, { selectorId: 'opaque', selectorInput: exotic, candidateDecisionIds: ids, selectors: { explicit: S.explicit, opaque } });
  assert.deepEqual(res.selection.selector_input, exotic, 'recorded verbatim');
  assert.equal(res.selection.selector_input_sha256, S.sha256(JSON.stringify(exotic, null, 2) + '\n'));
  assert.equal(S.verifySelection(home, res.selection_id).ok, true);
});

test('selection: an uninstalled selector is refused, and nothing is written', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  for (const spec of [
    { selectorId: 'model-selector', selectorVersion: '1', expect: /no selector 'model-selector' is installed/ },
    { selectorId: 'explicit', selectorVersion: '2', expect: /is version 1, not '2'/ }
  ]) {
    const refused = S.createSelection(home, { selectorId: spec.selectorId, selectorVersion: spec.selectorVersion, selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id] });
    assert.equal(refused.ok, false, spec.selectorId);
    assert.match(refused.error, spec.expect);
  }
  // The shipped registry holds exactly one selector, and it is named for what it
  // does. The empty slots stay empty.
  assert.deepEqual(Object.keys(S.SELECTORS), ['explicit']);
  assert.equal(selectionsExist(home), false);
});

test('selection: a selection is write-once', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const id = 'sel_20260918T050000Z-abcdef';
  select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id], now: new Date('2026-09-18T05:00:00.000Z'), selectionId: id });
  const before = fs.readFileSync(selectionPath(home, id), 'utf8');
  assert.throws(() => select(home, {
    selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id],
    now: new Date('2026-09-18T05:00:00.000Z'), selectionId: id
  }), /already exists — selections are write-once/);
  assert.equal(fs.readFileSync(selectionPath(home, id), 'utf8'), before);
});

test('selection: selecting is not executing, and it changes neither reuse_count nor traces', () => {
  const home = makeHome(EXECUTABLE());
  const regPath = path.join(home, 'registry', 'capability-registry.json');
  const regBefore = fs.readFileSync(regPath);
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const res = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });

  assert.equal(res.status, 'selected');
  assert.equal(fs.readFileSync(regPath).equals(regBefore), true, 'the registry is untouched');
  assert.equal(fs.existsSync(path.join(home, 'traces')), false, 'selection writes no trace');
  assert.equal(fs.existsSync(path.join(home, 'invocations')), false, 'selection runs no adapter');
  const reg = JSON.parse(fs.readFileSync(regPath, 'utf8'));
  for (const c of reg.capabilities) assert.equal(c.reuse_count, 0, c.id);
});

// ---------------------------------------------------------------------------
// The kernel handoff: selection is provenance, eligibility is authority.

test('selection: the winner gets a fresh scope=execute decision, and the selection is pinned', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const sel = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });

  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', selectionId: sel.selection_id });
  assert.equal(res.ok, true, res.error);
  assert.equal(res.status, 'completed');
  assert.ok(fs.existsSync(markerPath(res)), 'the adapter actually ran');

  // The authorization is a fresh execute decision, never the compete decision
  // the candidate pinned. The manifest copies what eligibility said; the
  // decision artifact itself is what names the capability.
  assert.notEqual(res.eligibility_decision_id, dA.decision_id);
  assert.notEqual(res.eligibility_decision_id, dB.decision_id);
  assert.equal(res.manifest.eligibility.scope, 'execute');
  assert.equal(res.manifest.eligibility.eligible, true);
  assert.equal(res.eligibility_decision.decision.capability_id, 'alpha');
  assert.equal(res.eligibility_decision.decision.scope, 'execute');
  assert.match(res.manifest.eligibility.path, new RegExp('^eligibility/' + res.eligibility_decision_id + '/decision\\.json$'));
  // The candidates it was chosen from were asked the other question.
  assert.equal(dA.decision.scope, 'compete');
  assert.equal(dB.decision.scope, 'compete');

  assert.equal(res.manifest.selection_id, sel.selection_id);
  assert.equal(res.manifest.selection_sha256, sel.selection_sha256);
  assert.equal(res.manifest.selection.status, 'selected');
  assert.equal(res.manifest.selection.selected_capability_id, 'alpha');
  assert.equal(res.manifest.selection.selector.id, 'explicit');
  assert.equal(res.manifest.selection.candidates.length, 2);

  const v = I.verifyInvocation(home, res.invocation_id);
  assert.equal(v.ok, true, v.problems.join('; '));
});

test('selection: direct invocation needs no selection', () => {
  const home = makeHome(EXECUTABLE());
  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal' });
  assert.equal(res.status, 'completed');
  assert.equal(res.manifest.selection_id, null);
  assert.equal(res.manifest.selection, null);
  assert.equal(res.manifest.selection_sha256, null);
  assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true);
});

test('selection: the kernel refuses a selection that chose a different capability', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const sel = select(home, { selectorInput: { capability_id: 'beta' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });

  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', selectionId: sel.selection_id });
  assert.equal(res.status, 'blocked');
  assert.equal(res.manifest.adapter.exit_code, null);
  assert.ok(!fs.existsSync(markerPath(res)), 'nothing executed');
  assert.match(res.basis, /does not authorize this invocation/);
  assert.match(res.basis, /chose 'beta', not 'alpha'/);
});

test('selection: the kernel refuses a selection that is not selected', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const abstained = select(home, { selectorInput: { capability_id: 'nope' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });
  assert.equal(abstained.status, 'abstained');

  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', selectionId: abstained.selection_id });
  assert.equal(res.status, 'blocked');
  assert.ok(!fs.existsSync(markerPath(res)), 'nothing executed');
  assert.match(res.basis, /status is 'abstained'/);
});

test('selection: the kernel refuses a selection artifact that does not verify', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const sel = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id] });
  resealSelection(home, sel.selection_id, (d) => { d.status = 'abstained'; d.selected_capability_id = null; });

  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', selectionId: sel.selection_id });
  assert.equal(res.status, 'blocked');
  assert.ok(!fs.existsSync(markerPath(res)), 'nothing executed');
  assert.match(res.basis, /status is 'abstained'/);
});

// PIN 6 — a compete decision supplied directly to the kernel must fail closed.
test('selection: a scope=compete decision handed straight to the kernel authorizes nothing', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  assert.equal(dA.eligible, true, 'it is a perfectly good compete decision');

  const res = I.invokeCapability(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', eligibilityDecisionId: dA.decision_id });
  assert.equal(res.status, 'blocked');
  assert.equal(res.manifest.adapter.exit_code, null);
  assert.ok(!fs.existsSync(markerPath(res)), 'may compete is not may run');
  assert.match(res.basis, /asked at scope 'compete'/);
  assert.match(res.basis, /only a scope=execute decision authorizes execution/);
  assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true, 'even a refusal is an honest artifact');
});

test('selection: tampering a selection after it authorized a run is caught by the invocation', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const sel = select(home, { selectorInput: { capability_id: 'alpha' }, candidateDecisionIds: [dA.decision_id, dB.decision_id] });
  const res = invoke(home, 'alpha', { input: { name: 'adam' }, mode: 'normal', selectionId: sel.selection_id });
  assert.equal(res.status, 'completed');

  // A consistent forgery: the record now says beta was chosen, and the forgery
  // re-seals itself so the selection verifies on its own. The invocation pins
  // the bytes, so the chain is what catches it.
  resealSelection(home, sel.selection_id, (d) => { d.selected_capability_id = 'beta'; });
  assert.equal(S.verifySelection(home, sel.selection_id).ok, true, 'the forgery is internally consistent');
  const v = I.verifyInvocation(home, res.invocation_id);
  assert.equal(v.ok, false);
  assert.match(v.problems.join('; '), /selection/);
});

// ---------------------------------------------------------------------------
// The CLI.

test('selection: the CLI select / selections / selection-verify round trip', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const inAlpha = path.join(home, 'in-alpha.json');
  const inGhost = path.join(home, 'in-ghost.json');
  writeJson(inAlpha, { capability_id: 'alpha' });
  writeJson(inGhost, { capability_id: 'ghost' });

  const r = run(home, 'select', '--input', inAlpha, '--decision', dA.decision_id, '--decision', dB.decision_id);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /^STATUS: selected$/m);
  assert.match(r.stdout, /^SELECTED: alpha$/m);
  assert.match(r.stdout, /^CANDIDATES: alpha, beta$/m);
  assert.match(r.stdout, /^selector: explicit@1$/m);
  assert.match(r.stdout, /this grants nothing/);
  const id = /^selection: (\S+)\t/m.exec(r.stdout)[1];
  assert.equal(S.verifySelection(home, id).ok, true);

  const list = run(home, 'selections');
  assert.equal(list.status, 0, list.stderr);
  // id, status, selected, selector@version, candidate count, decided_at
  assert.match(list.stdout, new RegExp('^' + id + '\\tselected\\talpha\\texplicit@1\\t2\\t\\S+$', 'm'));

  const verify = run(home, 'selection-verify', '--selection', id);
  assert.equal(verify.status, 0, verify.stderr);

  // PIN 1 through the CLI: an abstention is not a failure of the run, and it is
  // not a selection either.
  const ghost = run(home, 'select', '--input', inGhost, '--decision', dA.decision_id, '--decision', dB.decision_id);
  assert.equal(ghost.status, 4, ghost.stderr);
  assert.match(ghost.stdout, /^STATUS: abstained$/m);
  assert.match(ghost.stdout, /^SELECTED: \(none\)$/m);

  // A selector that does not exist cannot be named into existence.
  const bad = run(home, 'select', '--input', inAlpha, '--selector', 'model-selector@1', '--decision', dA.decision_id);
  assert.equal(bad.status, 2);
  assert.match(bad.stderr, /no selector 'model-selector' is installed/);

  // And the tampered artifact is caught by the verifier.
  resealSelection(home, id, (d) => { d.status = 'selected'; d.selected_capability_id = null; });
  const badVerify = run(home, 'selection-verify', '--selection', id);
  assert.equal(badVerify.status, 3, badVerify.stdout);
});

test('selection: rcos run refuses an abstained selection and completes with a real one', () => {
  const home = makeHome(EXECUTABLE());
  const dA = compete(home, 'alpha');
  const dB = compete(home, 'beta');
  const inRun = path.join(home, 'in-run.json');
  writeJson(inRun, { name: 'adam' });
  const inGhost = path.join(home, 'in-ghost.json');
  writeJson(inGhost, { capability_id: 'ghost' });

  const abstained = /^selection: (\S+)\t/m.exec(run(home, 'select', '--input', inGhost, '--decision', dA.decision_id).stdout)[1];
  const blocked = run(home, 'run', 'alpha', '--input', inRun, '--selection', abstained);
  assert.equal(blocked.status, 4, blocked.stdout);
  assert.match(blocked.stdout, /blocked/);
  assert.match(blocked.stdout, /does not authorize this invocation/);

  const inAlpha = path.join(home, 'in-alpha.json');
  writeJson(inAlpha, { capability_id: 'alpha' });
  const chosen = /^selection: (\S+)\t/m.exec(run(home, 'select', '--input', inAlpha, '--decision', dA.decision_id, '--decision', dB.decision_id).stdout)[1];
  const ok = run(home, 'run', 'alpha', '--input', inRun, '--selection', chosen);
  assert.equal(ok.status, 0, ok.stderr);
  assert.match(ok.stdout, /^selection: /m);
  const inv = /^(\S+)\tcompleted\talpha\t0$/m.exec(ok.stdout)[1];
  assert.equal(I.verifyInvocation(home, inv).ok, true);
});

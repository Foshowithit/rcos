'use strict';
// The eligibility engine's own contract, pinned.
//
// What these tests are for: eligibility is the one place in RCOS that says
// "this named capability may compete / may execute here" — so the things worth
// pinning are (a) it is a pure function of registry entry + runtime state +
// caller context, (b) it never executes anything, never mutates the registry,
// and never sees the task, (c) every applicable reason is reported, in one
// canonical order, and (d) the decision is a sealed write-once artifact that
// can be re-verified later. The fixtures are built here rather than read from
// the shipped registry so a failure names a rule, not a data drift.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO = path.join(__dirname, '..');
const BIN = path.join(REPO, 'bin', 'rcos');
const E = require('../lib/eligibility');

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

// What every capability promoted before the eval runner existed looks like: an
// eval that records a judgment (prose run_id, no provenance field) rather than a
// runner-backed run. The distinction is load-bearing, so the fixtures make it.
const ASSERTED_SHIP = [{ task_id: 't-a', verdict: 'ship', run_id: 'manual review 2026-09-16' }];

// The adapter writes a marker when it runs. Whether that marker exists is how
// these tests tell "decided" from "executed" — eligibility must never make one.
const ADAPTER_SRC = [
  '#!/usr/bin/env node',
  "const fs = require('node:fs');",
  "fs.writeFileSync('ran.marker', 'yes');",
  "fs.writeFileSync(process.env.RCOS_OUTPUT, JSON.stringify({ schema: 'echo/1', greeting: 'hi' }) + '\\n');",
  ''
].join('\n');

function capability(id, opts = {}) {
  const status = opts.status || 'promoted';
  const c = {
    id, name: 'fixture ' + id, kind: 'script', version: opts.version || '1.0.0', status,
    admitted_after: [], evals: [], reuse_count: opts.reuse_count || 0, last_eval: null
  };
  if (opts.evals !== undefined) c.evals = opts.evals;
  else if (status === 'promoted') {
    c.evals = [
      { task_id: 't-a', verdict: 'ship', run_id: '20260901T000000Z-aaaaaa', provenance: 'executed' },
      { task_id: 't-b', verdict: 'ship', run_id: '20260901T000001Z-bbbbbb', provenance: 'executed' }
    ];
    c.last_eval = '2026-09-01';
    c.admitted_after = ['t-a', 't-b'];
  }
  if (status === 'promoted') {
    c.retirement = {
      armed_at: '2026-09-01', policy_version: 'rcos-retire/1',
      decay: { window: 5, threshold: null }, neglect: { n: 20, threshold: null }
    };
  }
  if (status === 'retired') c.retire_reason = 'fixture: retired on purpose';
  if (!opts.noAdapter) {
    c.adapter = {
      type: opts.adapterType || 'command',
      entrypoint: opts.entrypoint || ('capabilities/' + id + '/adapter/run.js'),
      timeout_seconds: 30
    };
    if (opts.contract || opts.contractMissing) c.adapter.contract = 'capabilities/' + id + '/contract.json';
  }
  return c;
}

function fx(id, opts = {}) { return Object.assign({}, opts, { cap: capability(id, opts) }); }

function makeHome(fixtures) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-eligibility-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  for (const f of fixtures) {
    const dir = path.join(home, 'capabilities', f.cap.id);
    fs.mkdirSync(path.join(dir, 'adapter'), { recursive: true });
    if (!f.cap.adapter) continue;
    if (f.entrypointPresent !== false) {
      const p = path.join(dir, 'adapter', 'run.js');
      fs.writeFileSync(p, f.script === undefined ? ADAPTER_SRC : f.script);
      fs.chmodSync(p, f.mode === undefined ? 0o755 : f.mode);
    }
    if (f.contract !== undefined) {
      fs.writeFileSync(path.join(dir, 'contract.json'), JSON.stringify(f.contract, null, 2) + '\n');
    }
  }
  fs.writeFileSync(path.join(home, 'registry', 'capability-registry.json'),
    JSON.stringify({ registry_version: 'v1', capabilities: fixtures.map((f) => f.cap) }, null, 2) + '\n');
  return home;
}

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

function regBytes(home) { return fs.readFileSync(path.join(home, 'registry', 'capability-registry.json')); }

// Every artifact shape the engine can write, and nothing else.
function artifacts(home) {
  const out = [];
  for (const sub of ['eligibility', 'invocations', 'traces', 'work']) {
    const d = path.join(home, sub);
    if (fs.existsSync(d)) out.push(sub);
  }
  return out;
}

// A synthetic runtime state, so the reason-emission rules can be pinned without
// building five different capability directories.
function synthState(over = {}) {
  const { adapter: adapterOver, ...rest } = over;
  const adapter = Object.assign({
    declared: true, type: 'command', type_supported: true, declaration_errors: [],
    entrypoint: 'capabilities/x/adapter/run.js', entrypoint_present: true, entrypoint_executable: true,
    contract_declared: false, contract_usable: true, contract_errors: []
  }, adapterOver || {});
  return Object.assign({
    status: 'promoted', executable: E.executabilityReason({ adapter }) === null, adapter,
    provenance: 'executed', latest_eval_verdict: 'ship', latest_eval_at: '2026-09-01',
    eval_fresh: 'unknown', evals_total: 1, evals_executed: 1
  }, rest);
}

function ctx(purpose, capabilityId, over = {}) {
  return Object.assign(E.buildContext(purpose, { capabilityId }), over);
}

test('eligibility: the same inputs produce the same decision, and nothing runs', () => {
  const home = makeHome([fx('cand-cap', { status: 'candidate', contract: CONTRACT })]);
  const before = regBytes(home);

  const a = E.evaluate(home, 'cand-cap', ctx('normal', 'cand-cap'));
  const b = E.evaluate(home, 'cand-cap', ctx('normal', 'cand-cap'));
  assert.equal(a.ok, true);
  assert.deepEqual(a.decision, b.decision, 'two evaluations of the same state are identical');
  assert.deepEqual(a.state, b.state);

  // Nothing ran, nothing was written: `evaluate` is read-only.
  assert.deepEqual(artifacts(home), [], 'a read-only evaluation writes no artifact');
  assert.ok(!fs.existsSync(path.join(home, 'capabilities', 'cand-cap', 'adapter', 'ran.marker')));

  const d1 = E.decideForHome(home, 'cand-cap', { purpose: 'normal', scope: 'execute' });
  const d2 = E.decideForHome(home, 'cand-cap', { purpose: 'normal', scope: 'execute' });
  assert.notEqual(d1.decision_id, d2.decision_id, 'each decision gets its own id');
  for (const k of ['eligible', 'reasons', 'scope', 'capability_id', 'capability_version', 'caller_context', 'observed_state']) {
    assert.deepEqual(d1.decision[k], d2.decision[k], k + ' is identical across decisions');
  }
  assert.ok(regBytes(home).equals(before), 'deciding moves no registry byte');
  assert.ok(!fs.existsSync(path.join(home, 'capabilities', 'cand-cap', 'adapter', 'ran.marker')),
    'eligibility never executes an adapter');
  assert.deepEqual(artifacts(home), ['eligibility'], 'the decision is the only artifact the engine writes');
});

test('eligibility: reasons are a closed vocabulary, deduplicated, and canonically ordered', () => {
  // The ordering rule: reasons come back in the order of the question they
  // answer, so a reader can stop at the first line and still know the most
  // fundamental thing that is wrong.
  assert.deepEqual(E.orderReasons(['no_ship_eval', 'retired', 'provenance_asserted']),
    ['retired', 'provenance_asserted', 'no_ship_eval']);
  assert.deepEqual(E.orderReasons(['not_executable', 'missing_contract']),
    ['missing_contract', 'not_executable'], 'executability reasons are ordered most-specific-first');
  assert.deepEqual(E.orderReasons(['no_ship_eval', 'no_ship_eval', 'retired']), ['retired', 'no_ship_eval'],
    'duplicates collapse');
  assert.deepEqual(E.orderReasons([]), []);
  assert.deepEqual([...E.REASON_CODES].sort(), [...new Set(E.REASON_CODES)].sort(), 'no duplicate codes');

  // Under the normal default context a retired, unrunnable, asserted, latest-fix
  // capability fails four groups at once — nothing is dropped for brevity.
  const four = E.decide(
    { id: 'bad-cap', version: '1.0.0', status: 'retired', evals: [] },
    synthState({
      status: 'retired', provenance: 'asserted', latest_eval_verdict: 'fix',
      adapter: { type: 'telepathy', type_supported: false }
    }),
    ctx('normal', 'bad-cap'));
  assert.deepEqual(four.reasons,
    ['retired', 'unsupported_adapter', 'provenance_asserted', 'latest_eval_fix'],
    'a default context reports every applicable reason, not just the first');

  // The strongest possible simultaneous failure: one reason from each of the
  // five groups at once. The three purposes are defaults, not a ceiling — the
  // caller may set the flags directly, and when it does the engine still reports
  // everything that is true.
  const entry = { id: 'bad-cap', version: '1.0.0', status: 'candidate', evals: [] };
  const state = synthState({
    status: 'candidate', provenance: 'asserted', latest_eval_verdict: 'fix',
    adapter: { type: 'telepathy', type_supported: false }
  });
  const dec = E.decide(entry, state, ctx('forensic', 'bad-cap', {
    allow_candidate: false, require_executed_provenance: true, require_current_ship: true, forensic_reason: null
  }));
  assert.equal(dec.eligible, false);
  assert.deepEqual(dec.reasons,
    ['candidate_not_allowed', 'unsupported_adapter', 'provenance_asserted', 'latest_eval_fix', 'forensic_reason_required'],
    'every applicable reason is reported, in canonical order');
  assert.equal(dec.reasons.includes('eligible'), false, 'the positive outcome is never listed as a reason');
  for (const r of dec.reasons) assert.ok(E.REASON_CODES.includes(r), r + ' is in the vocabulary');

  // A decision whose reasons are shuffled is not a decision this engine wrote.
  const shuffled = ['forensic_reason_required', 'candidate_not_allowed', 'latest_eval_fix', 'unsupported_adapter', 'provenance_asserted'];
  assert.notDeepEqual(shuffled, E.orderReasons(shuffled));
  assert.deepEqual(E.orderReasons(shuffled), dec.reasons);
});

test('eligibility: exactly one executability reason, chosen by specificity', () => {
  const cases = [
    ['no adapter at all', { declared: false, type: null, type_supported: false, entrypoint: null, entrypoint_present: false, entrypoint_executable: false }, 'not_executable'],
    ['a type RCOS cannot run', { type: 'telepathy', type_supported: false }, 'unsupported_adapter'],
    ['a declaration RCOS rejects', { declaration_errors: ['adapter.entrypoint: required'] }, 'missing_adapter'],
    ['a contract that will not load', { contract_declared: true, contract_usable: false }, 'missing_contract'],
    ['an absent entrypoint', { entrypoint_present: false }, 'not_executable'],
    ['a non-executable entrypoint', { entrypoint_executable: false }, 'not_executable'],
    ['a runnable adapter', {}, null]
  ];
  for (const [label, adapter, expect] of cases) {
    assert.equal(E.executabilityReason(synthState({ adapter })), expect, label);
  }
  // The reason a legacy, adapter-less promoted capability reports is
  // not_executable — the true and most specific statement about it.
  const legacy = { id: 'legacy-cap', version: '1.0.0', status: 'promoted', evals: ASSERTED_SHIP };
  const home = makeHome([fx('legacy-cap', { noAdapter: true, evals: ASSERTED_SHIP })]);
  const st = E.deriveRuntimeState(home, capability('legacy-cap', { noAdapter: true, evals: ASSERTED_SHIP }));
  assert.equal(st.executable, false);
  assert.equal(E.executabilityReason(st), 'not_executable');
  const dec = E.decide(legacy, st, ctx('normal', 'legacy-cap'));
  assert.deepEqual(dec.reasons, ['not_executable', 'provenance_asserted', 'no_ship_eval'],
    'the legacy triple: not runnable, evidence asserted, no executed ship eval');
});

test('eligibility: the three purposes are three flag sets, not three ladders', () => {
  const home = makeHome([
    fx('exec-cap', { contract: CONTRACT }),                                             // promoted, runnable, executed ship
    fx('cand-exec-cap', { status: 'candidate', contract: CONTRACT }),                    // candidate, runnable
    fx('retired-exec-cap', { status: 'retired', contract: CONTRACT }),                   // retired, runnable
    fx('asserted-cap', {
      contract: CONTRACT,
      evals: [{ task_id: 't-a', verdict: 'ship', run_id: 'manual note, no run dir' }]     // asserted, not executed
    })
  ]);
  const at = (id, purpose, over) => E.evaluate(home, id, ctx(purpose, id, over)).decision;

  // normal: promoted + runnable + executed + current ship.
  assert.deepEqual(at('exec-cap', 'normal').reasons, []);
  assert.equal(at('exec-cap', 'normal').eligible, true);

  // The defaults, spelled out: eligibility is not "status == promoted".
  assert.deepEqual(at('cand-exec-cap', 'normal').reasons,
    ['candidate_not_allowed', 'provenance_asserted', 'no_ship_eval']);
  assert.deepEqual(at('retired-exec-cap', 'normal').reasons,
    ['retired', 'provenance_asserted', 'no_ship_eval']);
  assert.deepEqual(at('asserted-cap', 'normal').reasons, ['provenance_asserted', 'no_ship_eval']);

  // eval: the runner establishing quality does not have to already have it.
  for (const id of ['cand-exec-cap', 'asserted-cap']) {
    assert.equal(at(id, 'eval').eligible, true, id + ' may be evaluated');
  }
  assert.deepEqual(at('retired-exec-cap', 'eval').reasons, ['retired'], 'eval is not a licence to run a retired capability');

  // forensic: candidates and retired entries are permitted, with a reason.
  for (const id of ['cand-exec-cap', 'retired-exec-cap', 'asserted-cap']) {
    const d = at(id, 'forensic', { forensic_reason: 'audit 2026-09-17' });
    assert.equal(d.eligible, true, id + ' may be invoked forensically');
    assert.equal(d.caller_context.forensic_reason, 'audit 2026-09-17');
  }

  // The flags are what move the verdict, not the purpose name: a normal context
  // that tolerates candidates and does not demand current ship says so.
  const relaxed = at('cand-exec-cap', 'normal', {
    allow_candidate: true, require_executed_provenance: false, require_current_ship: false
  });
  assert.equal(relaxed.eligible, true);
});

test('eligibility: forensic requires a recorded reason, and the reason lands in the artifact', () => {
  const home = makeHome([fx('retired-exec-cap', { status: 'retired', contract: CONTRACT })]);
  const bare = E.evaluate(home, 'retired-exec-cap', ctx('forensic', 'retired-exec-cap')).decision;
  assert.deepEqual(bare.reasons, ['forensic_reason_required']);
  const blank = E.evaluate(home, 'retired-exec-cap', ctx('forensic', 'retired-exec-cap', { forensic_reason: '   ' })).decision;
  assert.deepEqual(blank.reasons, ['forensic_reason_required'], 'whitespace is not a reason');

  const withReason = E.decideForHome(home, 'retired-exec-cap', {
    purpose: 'forensic', scope: 'execute', forensicReason: 'investigating a blocked eval'
  });
  assert.equal(withReason.eligible, true);
  const onDisk = E.readDecision(home, withReason.decision_id);
  assert.equal(onDisk.caller_context.forensic_reason, 'investigating a blocked eval');
  assert.equal(onDisk.caller_context.allow_retired, true, 'the override that permitted it is recorded, not implied');
  assert.equal(onDisk.eligible, true);
  assert.deepEqual(onDisk.reasons, []);
});

test('eligibility: scope is carried, not implied, and the caller context vocabulary is closed', () => {
  const home = makeHome([fx('exec-cap', { contract: CONTRACT })]);
  const compete = E.decideForHome(home, 'exec-cap', { purpose: 'normal', scope: 'compete' });
  assert.equal(compete.decision.scope, 'compete');
  assert.equal(compete.eligible, true, 'the two scopes share one engine and agree today');
  const exec = E.decideForHome(home, 'exec-cap', { purpose: 'normal', scope: 'execute' });
  assert.equal(exec.decision.scope, 'execute');
  assert.equal(exec.decision.eligible, compete.decision.eligible);

  assert.deepEqual(E.validateContext(ctx('normal', 'x', { scope: 'pick-the-best' })).filter((e) => /scope/.test(e)).length, 1);
  assert.ok(E.validateContext({ purpose: 'normal', explicit_capability_id: 'x', scope: 'execute' }).length > 0,
    'the flag set is required, not defaulted inside the validator');

  // The forbidden list is the router rule, enforced at the boundary: a context
  // carrying task text, semantic intent, scores, rankings or reuse history is
  // refused outright rather than quietly ignored.
  for (const k of ['task', 'user_prompt', 'keywords', 'domain', 'intent', 'score', 'ranking', 'reuse_count', 'preferred_capability']) {
    const errors = E.validateContext(ctx('normal', 'x', { [k]: 'anything' }));
    assert.equal(errors.length, 1, k);
    assert.match(errors[0], /forbidden — eligibility may not see/);
  }
  const unknown = E.validateContext(ctx('normal', 'x', { mood: 'happy' }));
  assert.equal(unknown.length, 1);
  assert.match(unknown[0], /unknown field \(the caller context vocabulary is closed\)/);
  const decidedBefore = E.listDecisions(home).length;
  const bad = E.decideForHome(home, 'exec-cap', { context: ctx('normal', 'exec-cap', { task: 'greet ada' }) });
  assert.equal(bad.ok, false);
  assert.match(bad.error, /invalid caller context/);
  assert.match(bad.error, /forbidden/);
  assert.equal(E.listDecisions(home).length, decidedBefore, 'a refused context decides nothing');
  assert.deepEqual(artifacts(home), ['eligibility'], 'and writes no artifact beyond the decisions already there');
});

test('eligibility: how often a capability was reused cannot change the verdict', () => {
  const quiet = makeHome([fx('exec-cap', { contract: CONTRACT, reuse_count: 0 })]);
  const loud = makeHome([fx('exec-cap', { contract: CONTRACT, reuse_count: 417 })]);
  const a = E.evaluate(quiet, 'exec-cap', ctx('normal', 'exec-cap')).decision;
  const b = E.evaluate(loud, 'exec-cap', ctx('normal', 'exec-cap')).decision;
  assert.equal(a.eligible, b.eligible);
  assert.deepEqual(a.reasons, b.reasons);
  assert.deepEqual(a.observed_state, b.observed_state, 'the observed state does not even carry reuse history');
  assert.equal(Object.keys(a.observed_state).includes('reuse_count'), false);
});

test('eligibility: evidence that RCOS did not produce is not evidence', () => {
  const home = makeHome([
    fx('asserted-cap', { contract: CONTRACT, evals: [{ task_id: 't-a', verdict: 'ship', run_id: 'prose' }] }),
    fx('mixed-cap', {
      contract: CONTRACT,
      evals: [
        { task_id: 't-a', verdict: 'ship', run_id: 'prose' },
        { task_id: 't-b', verdict: 'ship', run_id: '20260901T000000Z-aaaaaa', provenance: 'executed' }
      ]
    }),
    fx('fix-cap', {
      contract: CONTRACT,
      evals: [{ task_id: 't-a', verdict: 'fix', run_id: '20260901T000000Z-aaaaaa', provenance: 'executed' }]
    }),
    fx('blocked-cap', {
      contract: CONTRACT,
      evals: [{ task_id: 't-a', verdict: 'blocked', run_id: '20260901T000000Z-aaaaaa', provenance: 'executed' }]
    })
  ]);
  const st = (id) => E.deriveRuntimeState(home, JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8')).capabilities.find((c) => c.id === id));

  assert.equal(st('asserted-cap').provenance, 'asserted');
  assert.equal(st('asserted-cap').latest_eval_verdict, null, 'an asserted eval states no runtime verdict');
  assert.equal(st('mixed-cap').provenance, 'executed', 'one executed eval is enough to make the evidence real');
  assert.equal(st('mixed-cap').evals_executed, 1);
  assert.equal(st('mixed-cap').evals_total, 2);

  const at = (id) => E.evaluate(home, id, ctx('normal', id)).decision.reasons;
  assert.deepEqual(at('asserted-cap'), ['provenance_asserted', 'no_ship_eval']);
  assert.deepEqual(at('mixed-cap'), [], 'executed ship evidence is what normal reuse requires');
  assert.deepEqual(at('fix-cap'), ['latest_eval_fix'], 'the newest executed verdict decides');
  assert.deepEqual(at('blocked-cap'), ['latest_eval_blocked']);

  // Freshness is deliberately undecided in step 4: no duration is invented, so
  // a derived state can never claim staleness — only a state that states it can.
  for (const id of ['asserted-cap', 'mixed-cap']) assert.equal(st(id).eval_fresh, 'unknown');
  const stale = E.decide({ id: 'x', version: '1.0.0', status: 'promoted', evals: [] },
    synthState({ eval_fresh: false }), ctx('normal', 'x'));
  assert.deepEqual(stale.reasons, ['eval_stale'], 'eval_stale fires when, and only when, a state says the evidence is stale');
});

test('eligibility: a decision is write-once, self-verifying, and tied to a version', () => {
  const home = makeHome([fx('cand-cap', { status: 'candidate', contract: CONTRACT })]);
  const id = 'elig_20260917T120000Z-abcdef';
  const first = E.decideForHome(home, 'cand-cap', { purpose: 'normal', decisionId: id });
  assert.equal(first.decision_id, id);
  assert.equal(first.eligible, false);
  assert.equal(E.verifyDecision(home, id).ok, true, E.verifyDecision(home, id).problems.join('; '));
  assert.throws(() => E.decideForHome(home, 'cand-cap', { purpose: 'normal', decisionId: id }),
    /already exists — decisions are write-once and never rewritten/);
  assert.throws(() => E.decideForHome(home, 'cand-cap', { purpose: 'normal', decisionId: 'nope' }), /bad decision id/);

  const dPath = path.join(E.decisionDir(home, id), 'decision.json');
  const original = fs.readFileSync(dPath, 'utf8');
  const doc = JSON.parse(original);

  // The attack the integrity block exists to stop: take a decision that says no
  // and edit it to say yes.
  doc.eligible = true;
  doc.reasons = [];
  fs.writeFileSync(dPath, JSON.stringify(doc, null, 2) + '\n');
  let v = E.verifyDecision(home, id);
  assert.equal(v.ok, false);
  assert.ok(v.problems.some((p) => /integrity mismatch — the decision was edited after it was written/.test(p)), v.problems.join('; '));

  // Reordering reasons breaks the canonical-order rule even with a valid hash:
  // a valid integrity value proves the bytes are the ones RCOS wrote, not that
  // what they say is well-formed.
  const reordered = JSON.parse(original);
  reordered.reasons = ['no_ship_eval', 'candidate_not_allowed', 'provenance_asserted'];
  reordered.integrity = { algo: 'sha256', value: E.decisionIntegrity(reordered) };
  fs.writeFileSync(dPath, JSON.stringify(reordered, null, 2) + '\n');
  v = E.verifyDecision(home, id);
  assert.ok(v.problems.some((p) => /reasons are not in canonical order/.test(p)), v.problems.join('; '));

  // Same for the eligible/reasons consistency rule.
  const empty = JSON.parse(original);
  empty.reasons = [];
  empty.integrity = { algo: 'sha256', value: E.decisionIntegrity(empty) };
  fs.writeFileSync(dPath, JSON.stringify(empty, null, 2) + '\n');
  v = E.verifyDecision(home, id);
  assert.ok(v.problems.some((p) => /ineligible decision carries no reason/.test(p)), v.problems.join('; '));

  fs.writeFileSync(path.join(E.decisionDir(home, id), 'stray.json'), '{}\n');
  v = E.verifyDecision(home, id);
  assert.ok(v.problems.some((p) => /present but not part of a decision: stray\.json/.test(p)), v.problems.join('; '));
  fs.unlinkSync(path.join(E.decisionDir(home, id), 'stray.json'));

  fs.writeFileSync(dPath, original);
  assert.equal(E.verifyDecision(home, id).ok, true, 'the original bytes still verify');

  // A decision is about a capability at a version. Bump the version and the
  // decision no longer describes what is in the registry.
  const regPath = path.join(home, 'registry', 'capability-registry.json');
  const reg = JSON.parse(fs.readFileSync(regPath, 'utf8'));
  reg.capabilities[0].version = '1.1.0';
  fs.writeFileSync(regPath, JSON.stringify(reg, null, 2) + '\n');
  v = E.verifyDecision(home, id);
  assert.ok(v.problems.some((p) => /references cand-cap 1\.0\.0 but the registry holds 1\.1\.0/.test(p)), v.problems.join('; '));

  reg.capabilities = [];
  fs.writeFileSync(regPath, JSON.stringify(reg, null, 2) + '\n');
  v = E.verifyDecision(home, id);
  assert.ok(v.problems.some((p) => /references unknown capability: cand-cap/.test(p)), v.problems.join('; '));

  const gone = E.verifyDecision(home, 'elig_20260917T120000Z-ffffff');
  assert.equal(gone.ok, false);
  assert.deepEqual(gone.problems, ['eligibility decision not found: elig_20260917T120000Z-ffffff']);
});

test('eligibility: a capability the registry does not hold gets a refusal, never an artifact', () => {
  const home = makeHome([fx('exec-cap', { contract: CONTRACT })]);
  const ghost = E.decideForHome(home, 'ghost-cap', { purpose: 'normal' });
  assert.equal(ghost.ok, false);
  assert.match(ghost.error, /no such capability 'ghost-cap' in the registry/);
  assert.equal(fs.existsSync(path.join(home, 'eligibility')), false,
    'there is nothing to attribute a decision about a ghost to, so no decision is written');

  // The code still exists for a decision that is asked about a capability that
  // is not there: decide() is total, and says the most fundamental thing.
  const dec = E.decide(null, null, ctx('normal', 'ghost-cap'));
  assert.deepEqual(dec.reasons, ['unknown_capability']);
  assert.equal(dec.observed_state, null);

  const listed = E.listDecisions(home);
  assert.deepEqual(listed, []);
});

test('cli: eligibility is askable, inspectable, and verifiable on its own', () => {
  const home = makeHome([
    fx('exec-cap', { contract: CONTRACT }),
    fx('cand-cap', { status: 'candidate', contract: CONTRACT }),
    fx('legacy-cap', { noAdapter: true, evals: ASSERTED_SHIP })
  ]);

  const yes = run(home, 'eligibility', 'exec-cap', '--purpose', 'normal', '--json');
  assert.equal(yes.status, 0, yes.stdout + yes.stderr);
  const doc = JSON.parse(yes.stdout);
  assert.equal(doc.schema, 'rcos-eligibility/1');
  assert.equal(doc.eligible, true);
  assert.deepEqual(doc.reasons, []);
  assert.equal(doc.scope, 'execute');
  assert.equal(doc.capability_id, 'exec-cap');
  assert.equal(doc.capability_version, '1.0.0');
  assert.equal(doc.caller_context.purpose, 'normal');
  const yesId = doc.decision_id;
  assert.ok(E.isDecisionId(yesId));

  const no = run(home, 'eligibility', 'cand-cap', '--purpose', 'normal');
  assert.equal(no.status, 4, no.stdout + no.stderr);
  assert.match(no.stdout, /^ELIGIBLE: no$/m);
  assert.match(no.stdout, /candidate_not_allowed/);
  assert.match(no.stdout, /provenance_asserted/);
  assert.match(no.stdout, /no_ship_eval/);

  const legacy = run(home, 'eligibility', 'legacy-cap', '--purpose', 'normal');
  assert.equal(legacy.status, 4);
  assert.match(legacy.stdout, /not_executable/);
  assert.match(legacy.stdout, /provenance_asserted/);
  assert.match(legacy.stdout, /no_ship_eval/);

  const evalAsk = run(home, 'eligibility', 'cand-cap', '--purpose', 'eval');
  assert.equal(evalAsk.status, 0, evalAsk.stdout + evalAsk.stderr);
  assert.match(evalAsk.stdout, /^ELIGIBLE: yes$/m);
  assert.match(evalAsk.stdout, /^REASONS: \(none\)$/m);

  const noReason = run(home, 'eligibility', 'cand-cap', '--purpose', 'forensic');
  assert.equal(noReason.status, 2);
  assert.match(noReason.stderr, /requires --forensic <reason>/);
  const forensic = run(home, 'eligibility', 'cand-cap', '--purpose', 'forensic', '--forensic', 'audit');
  assert.equal(forensic.status, 0, forensic.stdout + forensic.stderr);
  assert.match(forensic.stdout, /override: audit \(recorded in the decision\)/);

  const badPurpose = run(home, 'eligibility', 'exec-cap', '--purpose', 'vibes');
  assert.equal(badPurpose.status, 2);
  assert.match(badPurpose.stderr, /bad --purpose, want one of normal\|eval\|forensic/);

  const ghost = run(home, 'eligibility', 'ghost-cap');
  assert.equal(ghost.status, 2);
  assert.match(ghost.stderr, /no such capability 'ghost-cap' in the registry/);

  // Every ask above left exactly one artifact, and each one verifies.
  const decisions = E.listDecisions(home);
  assert.equal(decisions.length, 5, JSON.stringify(decisions.map((d) => d.decision_id)));
  for (const d of decisions) {
    const v = run(home, 'eligibility-verify', '--decision', d.decision_id);
    assert.equal(v.status, 0, d.decision_id + ': ' + v.stdout + v.stderr);
    assert.match(v.stdout, /verified \(1 check\(s\)\)/);
  }

  const missing = run(home, 'eligibility-verify', '--decision', 'elig_20260917T120000Z-ffffff');
  assert.equal(missing.status, 3);
  assert.match(missing.stdout, /PROBLEM eligibility decision not found/);

  // The self-hash is a hash of the document, not of the file's bytes: a
  // whitespace-only edit is invisible to it. That is deliberate — the byte-level
  // pin belongs to the invocation that consumed the decision
  // (manifest.eligibility_sha256), which is where a mismatch means something.
  const dPath = path.join(E.decisionDir(home, yesId), 'decision.json');
  const bytes = fs.readFileSync(dPath, 'utf8');
  fs.writeFileSync(dPath, bytes + '\n');
  assert.equal(run(home, 'eligibility-verify', '--decision', yesId).status, 0);

  // Editing what the decision SAYS is what the integrity block is for. Take the
  // decision that said no and make it say yes.
  const noId = /decision: (\S+)/.exec(no.stdout)[1];
  const noPath = path.join(E.decisionDir(home, noId), 'decision.json');
  const noDoc = JSON.parse(fs.readFileSync(noPath, 'utf8'));
  assert.equal(noDoc.eligible, false);
  noDoc.eligible = true;
  noDoc.reasons = [];
  fs.writeFileSync(noPath, JSON.stringify(noDoc, null, 2) + '\n');
  const tampered = run(home, 'eligibility-verify', '--decision', noId);
  assert.equal(tampered.status, 3);
  assert.match(tampered.stdout, /PROBLEM decision integrity mismatch — the decision was edited after it was written/);
});

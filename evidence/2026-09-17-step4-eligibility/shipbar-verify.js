'use strict';
// Step-4 ship-bar verifier. Mechanical where it can be; it records what it
// checked and what it found, and it never tampers with a real artifact.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

const HOME = '/Users/adam26/zcode-rcos';
const E = require(path.join(HOME, 'lib/eligibility'));
const R = require(path.join(HOME, 'lib/registry'));
const I = require(path.join(HOME, 'lib/invocation'));

const sha256 = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const snap = () => ({
  registry_sha256: sha256(path.join(HOME, 'registry/capability-registry.json')),
  invocations: fs.readdirSync(path.join(HOME, 'invocations')).sort(),
  decisions: fs.readdirSync(path.join(HOME, 'eligibility')).sort(),
  traces_sha256: fs.existsSync(path.join(HOME, 'traces/traces.jsonl')) ? sha256(path.join(HOME, 'traces/traces.jsonl')) : null
});

const out = { home: HOME, checked_at: new Date().toISOString(), items: {} };
const before = snap();
out.before = before;

const reg = R.loadRegistry(HOME);
const PURPOSES = ['normal', 'eval', 'forensic'];

// ---- item 1: pure deterministic function ------------------------------------
const eligSrc = fs.readFileSync(path.join(HOME, 'lib/eligibility.js'), 'utf8');
// The decision core is three functions. `deriveRuntimeState` is deliberately
// impure — it is the reader that turns the registry and the filesystem into the
// state the pure core consumes — so it is excluded by name, not by accident.
function extractFn(src, name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('no such function: ' + name);
  const rest = src.slice(start + 1);
  const next = rest.indexOf('\nfunction ');
  return next < 0 ? rest : rest.slice(0, next);
}
const PURE_FNS = ['orderReasons', 'executabilityReason', 'buildContext', 'isPlainObject', 'validateContext', 'decide'];
const core = PURE_FNS.map((n) => extractFn(eligSrc, n)).join('\n');
const ioIdents = ['fs.', 'path.', 'child_process', 'spawn', 'process.env', 'Date.now', 'new Date', 'Math.random', 'readFileSync', 'writeFileSync'];
const ioHits = ioIdents.filter((t) => core.includes(t));
const runA = [];
const runB = [];
for (const p of PURPOSES) {
  for (const cap of reg.capabilities) {
    const opts = { capabilityId: cap.id };
    if (p === 'forensic') opts.forensicReason = 'ship-bar verification';
    const ctx = E.buildContext(p, opts);
    const a = E.evaluate(HOME, cap.id, ctx);
    const b = E.evaluate(HOME, cap.id, ctx);
    if (!a.ok || !b.ok) throw new Error('evaluate failed');
    runA.push(JSON.stringify(a.decision));
    runB.push(JSON.stringify(b.decision));
  }
}
// reason order is canonical regardless of the order failures are found
const shuffled = ['no_ship_eval', 'not_executable', 'candidate_not_allowed', 'retired'];
const permuted = E.orderReasons(shuffled);
const rankSorted = shuffled.slice().sort((a, b) => E.REASON_RANK.get(a) - E.REASON_RANK.get(b));
out.items['1_pure_deterministic'] = {
  verdict: ioHits.length === 0 && JSON.stringify(runA) === JSON.stringify(runB) && JSON.stringify(permuted) === JSON.stringify(rankSorted) ? 'PASS' : 'FAIL',
  evaluations: runA.length,
  repeat_identical: JSON.stringify(runA) === JSON.stringify(runB),
  pure_functions_checked: PURE_FNS,
  io_identifiers_found_in_pure_core: ioHits,
  impure_by_design: ['deriveRuntimeState (the read-only reader that produces the state the pure core consumes)'],
  canonical_order_from_shuffled_input: permuted,
  is_permutation_of_input: permuted.length === shuffled.length && shuffled.every((r) => permuted.includes(r)),
  equals_rank_sorted_order: JSON.stringify(permuted) === JSON.stringify(rankSorted)
};

// ---- item 2: zero adapter execution during eligibility ----------------------
const spawnHits = ['child_process', 'spawnSync', 'spawn(', 'execFile', 'execSync', 'fork('].filter((t) => eligSrc.includes(t));
out.items['2_zero_adapter_execution'] = {
  verdict: spawnHits.length === 0 ? 'PASS' : 'FAIL',
  process_launch_identifiers_in_eligibility_module: spawnHits,
  invocations_before: before.invocations.length,
  note: 'evaluate() was called ' + runA.length + ' times above; the adapter side-effect surface is the invocation work dir, and no invocation dir was created'
};

// ---- item 4: schema ---------------------------------------------------------
const decisionIds = before.decisions;
const decisions = decisionIds.map((id) => ({ id, doc: E.readDecision(HOME, id) }));
const badSchema = decisions.filter((d) => !d.doc || d.doc.schema !== E.ELIGIBILITY_SCHEMA).map((d) => d.id);
out.items['4_schema_rcos_eligibility_1'] = {
  verdict: badSchema.length === 0 && decisions.length > 0 ? 'PASS' : 'FAIL',
  decisions_on_disk: decisions.length,
  wrong_schema: badSchema,
  schema: E.ELIGIBILITY_SCHEMA
};

// ---- item 5: integrity-verifiable / write-once ------------------------------
const verified = decisionIds.map((id) => ({ id, res: E.verifyDecision(HOME, id) }));
const failed = verified.filter((v) => !v.res.ok).map((v) => ({ id: v.id, problems: v.res.problems }));
// write-once, proven without touching a real artifact: the same id is refused
const probeHome = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'step4-writeonce-'));
fs.cpSync(path.join(HOME, 'registry'), path.join(probeHome, 'registry'), { recursive: true });
const first = E.decideForHome(probeHome, 'reuse-ledger', { purpose: 'eval' });
let secondErr = null;
try { E.decideForHome(probeHome, 'reuse-ledger', { purpose: 'eval', decisionId: first.decision_id }); } catch (e) { secondErr = e.message; }
// and a tamper in the probe home is detected
const probeDecision = path.join(probeHome, 'eligibility', first.decision_id, 'decision.json');
const tampered = JSON.parse(fs.readFileSync(probeDecision, 'utf8'));
tampered.eligible = true; tampered.reasons = [];
fs.writeFileSync(probeDecision, JSON.stringify(tampered, null, 2) + '\n');
const tamperRes = E.verifyDecision(probeHome, first.decision_id);
out.items['5_integrity_and_write_once'] = {
  verdict: failed.length === 0 && secondErr !== null && tamperRes.ok === false ? 'PASS' : 'FAIL',
  real_decisions_verified: verified.length,
  real_decisions_failing: failed,
  rewrite_refused_with: secondErr,
  tampered_copy_detected: tamperRes.problems,
  probe_home_removed: (fs.rmSync(probeHome, { recursive: true, force: true }), true)
};

// ---- item 6: reason codes enumerable + deterministic ------------------------
const rankValues = E.REASON_CODES.map((c) => E.REASON_RANK.get(c));
out.items['6_reason_codes'] = {
  verdict: E.REASON_CODES.length === 14 && rankValues.every((v, i) => v === i) ? 'PASS' : 'FAIL',
  count: E.REASON_CODES.length,
  codes: E.REASON_CODES,
  rank_is_total_order_0_to_n: rankValues.every((v, i) => v === i),
  positive_name_is_rank_0_and_guarded_against_being_emitted: E.REASON_CODES[0] === E.POSITIVE_REASON && /r === POSITIVE_REASON/.test(eligSrc)
};

// ---- item 7: multiple simultaneous failures all reported --------------------
const multi = decisions
  .filter((d) => d.doc && Array.isArray(d.doc.reasons) && d.doc.reasons.length >= 3)
  .map((d) => ({ id: d.id, capability: d.doc.capability_id, purpose: d.doc.caller_context.purpose, reasons: d.doc.reasons }));
out.items['7_multiple_failures_reported'] = {
  verdict: multi.length > 0 ? 'PASS' : 'FAIL',
  live_decisions_with_3plus_reasons: multi,
  max_reasons_seen: Math.max(0, ...decisions.map((d) => (d.doc && d.doc.reasons ? d.doc.reasons.length : 0)))
};

// ---- item 8: kernel holds no eligibility policy ----------------------------
const kern = fs.readFileSync(path.join(HOME, 'lib/invocation.js'), 'utf8').split('\n');
const policyTerms = ['candidate_not_allowed', 'no_ship_eval', 'provenance_asserted', 'require_current_ship', 'allow_candidate', 'not eligible for normal invocation', 'eval_fresh'];
const policyHits = [];
kern.forEach((line, i) => {
  for (const t of policyTerms) if (line.includes(t)) policyHits.push({ line: i + 1, term: t, text: line.trim() });
});
// the only status comparisons the kernel may make are descriptive, never gating
const statusComparisons = [];
kern.forEach((line, i) => {
  if (/cap\.status\s*===|status\s*===\s*'/.test(line)) statusComparisons.push({ line: i + 1, text: line.trim() });
});
out.items['8_kernel_has_no_policy'] = {
  verdict: policyHits.length === 0 && statusComparisons.length === 0 ? 'PASS' : 'FAIL',
  policy_term_occurrences: policyHits,
  status_comparisons_in_kernel: statusComparisons,
  kernel_imports_eligibility: /require\('\.\/eligibility'\)/.test(kern.join('\n'))
};

// ---- item 9: kernel requires a valid eligible decision ---------------------
const naked = I.invokeCapability(HOME, 'reuse-ledger', { input: { seed_registry: '/nonexistent', probe_capability: 'x' }, mode: 'eval' });
out.items['9_decision_required'] = {
  verdict: naked.ok === false && /eligibility decision/.test(naked.error || '') ? 'PASS' : 'FAIL',
  naked_call_refused: naked.ok === false,
  error: naked.error,
  eligibility_exported_from_kernel: Object.prototype.hasOwnProperty.call(I, 'eligibility')
};

// ---- item 11: three distinct caller contexts -------------------------------
const ctxs = {};
for (const p of PURPOSES) {
  const o = { capabilityId: 'reuse-ledger' };
  if (p === 'forensic') o.forensicReason = 'ship-bar verification';
  ctxs[p] = E.buildContext(p, o);
}
const flagSets = PURPOSES.map((p) => [ctxs[p].allow_candidate, ctxs[p].allow_retired, ctxs[p].require_executed_provenance, ctxs[p].require_current_ship].join(','));
out.items['11_three_caller_contexts'] = {
  verdict: new Set(flagSets).size === 3 ? 'PASS' : 'FAIL',
  contexts: ctxs,
  distinct_flag_sets: new Set(flagSets).size
};

// ---- item 12: forbidden inputs cannot affect eligibility -------------------
const forbiddenProbe = Object.assign({}, ctxs.normal, { task_text: 'make me a video about bearings' });
const forbiddenErrors = E.validateContext(forbiddenProbe);
const unknownProbe = Object.assign({}, ctxs.normal, { score: 0.97 });
const unknownErrors = E.validateContext(unknownProbe);
// and a payload that has nothing to do with the capability changes nothing
const withJunk = E.evaluate(HOME, 'filmstrip-verify', ctxs.normal).decision.reasons;
const junkCtx = E.buildContext('normal', { capabilityId: 'filmstrip-verify' });
const junkAgain = E.evaluate(HOME, 'filmstrip-verify', junkCtx).decision.reasons;
out.items['12_forbidden_inputs_inert'] = {
  verdict: forbiddenErrors.length > 0 && unknownErrors.length > 0 && JSON.stringify(withJunk) === JSON.stringify(junkAgain) ? 'PASS' : 'FAIL',
  forbidden_key_errors: forbiddenErrors,
  unknown_key_errors: unknownErrors,
  forbidden_vocabulary_size: E.FORBIDDEN_CONTEXT_KEYS.length,
  context_vocabulary: E.CONTEXT_KEYS,
  same_reasons_with_no_payload: JSON.stringify(withJunk) === JSON.stringify(junkAgain)
};

// ---- items 2/3/14: nothing moved -------------------------------------------
const after = snap();
out.after = after;
out.items['3_zero_registry_mutation'] = {
  verdict: before.registry_sha256 === after.registry_sha256 ? 'PASS' : 'FAIL',
  before: before.registry_sha256, after: after.registry_sha256
};
// The ship-bar item is "registry stays byte-stable", which is a claim about what
// THIS STEP did, so it is checked against the step's own commit range. A hardcoded
// current-sha comparison would instead assert "nothing has touched the registry
// since", which the ship bar does not ask for and which is false in this repo,
// because an unrelated machine-written study loop commits on its own schedule.
const STEP4_BASE = 'bab54a7';
const STEP4_COMMIT = '187a61b';
const gitDiff = (range) => {
  try {
    return execFileSync('git', ['diff', '--stat', ...range.split(' '), '--', 'registry/', 'traces/'],
      { cwd: HOME, encoding: 'utf8' }).trim();
  } catch (e) { return 'GIT_ERROR: ' + e.message; }
};
const stepRangeDiff = gitDiff(STEP4_BASE + ' ' + STEP4_COMMIT);

// If the live registry has moved past the step-4 commit, that is allowed only if
// the divergence is provably additive eval records. Anything else fails.
let liveDivergence = null;
let baseline = null;
try {
  baseline = JSON.parse(execFileSync('git', ['show', STEP4_COMMIT + ':registry/capability-registry.json'],
    { cwd: HOME, encoding: 'utf8' }));
} catch (e) { liveDivergence = 'could not read the step-4 registry: ' + e.message; }

if (baseline) {
  const live = reg;
  const baseCaps = baseline.capabilities || [];
  const liveCaps = live.capabilities || [];
  const idsOf = (cs) => cs.map((c) => c.id).sort();
  const problems = [];
  if (baseCaps.length !== liveCaps.length) problems.push('capability count changed: ' + baseCaps.length + ' -> ' + liveCaps.length);
  if (idsOf(baseCaps).join() !== idsOf(liveCaps).join()) problems.push('capability ids changed');
  const baseById = Object.fromEntries(baseCaps.map((c) => [c.id, c]));
  for (const lc of liveCaps) {
    const bc = baseById[lc.id];
    if (!bc) continue;
    // everything except the evals array must be byte-identical
    const strip = (c) => { const { evals, ...rest } = c; return JSON.stringify(rest); };
    if (strip(bc) !== strip(lc)) problems.push(lc.id + ': a field other than evals changed');
    const added = (lc.evals || []).filter((e) => !(bc.evals || []).some((b) => JSON.stringify(b) === JSON.stringify(e)));
    const removed = (bc.evals || []).filter((b) => !(lc.evals || []).some((e) => JSON.stringify(e) === JSON.stringify(b)));
    if (removed.length) problems.push(lc.id + ': an eval record was removed');
    for (const a of added) if (a.provenance !== 'asserted') problems.push(lc.id + ': a non-asserted eval was added (' + a.provenance + ')');
    if (added.length) (problems.added ||= []).push(lc.id + ' +' + added.length);
  }
  const addedAny = (problems.added || []).length > 0;
  delete problems.added;
  const step4Sha = crypto.createHash('sha256')
    .update(execFileSync('git', ['show', STEP4_COMMIT + ':registry/capability-registry.json'], { cwd: HOME }))
    .digest('hex');
  liveDivergence = {
    live_sha256: after.registry_sha256,
    step4_sha256: step4Sha,
    differs_from_step4: after.registry_sha256 !== step4Sha,
    divergence_is_additive_evals_only: problems.length === 0,
    problems,
    added_asserted_evals: addedAny,
    moved_by: execFileSync('git', ['log', '--oneline', STEP4_COMMIT + '..HEAD', '--', 'registry/', 'traces/'],
      { cwd: HOME, encoding: 'utf8' }).trim().split('\n').filter(Boolean)
  };
}

out.items['14_registry_byte_stable'] = {
  verdict: (stepRangeDiff === '' && (!liveDivergence || liveDivergence.divergence_is_additive_evals_only)) ? 'PASS' : 'FAIL',
  claim_checked: 'this step moved no registry or trace byte, and any later divergence is additive asserted evals only',
  step_range: STEP4_BASE + '..' + STEP4_COMMIT,
  step_range_diff_for_registry_and_traces: stepRangeDiff === '' ? '(empty — this step moved nothing)' : stepRangeDiff,
  live_registry_sha256: after.registry_sha256,
  live_divergence_from_step4: liveDivergence
};
out.items['2_zero_adapter_execution'].invocations_after = after.invocations.length;
out.items['2_zero_adapter_execution'].verdict =
  spawnHits.length === 0 && before.invocations.join() === after.invocations.join() ? 'PASS' : 'FAIL';

// ---- item 15: suite green ---------------------------------------------------
let suite = { status: null, summary: null };
try {
  const raw = execFileSync('npm', ['test'], { cwd: HOME, encoding: 'utf8' });
  const m = raw.match(/# (pass|fail) (\d+)/g) || raw.match(/ℹ (pass|fail) (\d+)/g);
  suite = { status: 0, counts: raw.split('\n').filter((l) => /^ℹ (tests|pass|fail|skipped)/.test(l)).map((l) => l.trim()) };
} catch (e) {
  suite = { status: e.status, counts: ['SUITE FAILED'], tail: (e.stdout || '').slice(-2000) };
}
out.items['15_suite_green'] = { verdict: suite.status === 0 ? 'PASS' : 'FAIL', ...suite };

// ---- item 13: reuse/eval invariants unchanged ------------------------------
const regAfter = R.loadRegistry(HOME);
const T = require(path.join(HOME, 'lib/traces'));
const derived = T.deriveReuseCounts(T.loadTraces(HOME));
const reuseMismatch = regAfter.capabilities
  .filter((c) => (c.reuse_count || 0) !== (derived[c.id] || 0))
  .map((c) => ({ id: c.id, stored: c.reuse_count || 0, derived: derived[c.id] || 0 }));
const ledger = regAfter.capabilities.find((c) => c.id === 'reuse-ledger');
out.items['13_reuse_eval_invariants'] = {
  verdict: suite.status === 0 && reuseMismatch.length === 0 && (ledger.reuse_count || 0) === 0 ? 'PASS' : 'FAIL',
  registry_reuse_counts_match_the_trace_ledger: reuseMismatch.length === 0,
  mismatches: reuseMismatch,
  reuse_counts_derived_from_traces: derived,
  reuse_ledger_after_an_eval_mode_invocation: ledger.reuse_count,
  suite_green: suite.status === 0,
  note: 'reuse_count stays a cache of the trace log (it is never the registry certifying itself), and the eval-mode dogfood invocation moved no counter'
};

// ---- item 10: execution-safety checks remain in the kernel ------------------
// An eligible decision authorises a capability to run; it does not certify that
// the capability is runnable. Sabotage the capability AFTER its decision comes
// back eligible, and the kernel must still refuse from its own checks — if any
// of these refusals disappeared, eligibility would have quietly absorbed
// execution safety. Done in a probe home so no real artifact is touched.
const probe2 = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'step4-safety-'));
for (const sub of ['registry', 'capabilities', 'evals']) {
  fs.cpSync(path.join(HOME, sub), path.join(probe2, sub), { recursive: true });
}
const dec10 = E.decideForHome(probe2, 'reuse-ledger', { purpose: 'eval' });
const entry = path.join(probe2, 'capabilities/reuse-ledger/adapter/run.js');
const contractFile = path.join(probe2, 'capabilities/reuse-ledger/contract.json');
const goodInput = {
  seed_registry: path.join(probe2, 'evals/reuse-ledger-invariant-v1/fixtures/seed-registry.json'),
  probe_capability: 'fixture-cap',
  sandbox: 'reuse-ledger-safety-probe'
};
const call = (input) => I.invokeCapability(probe2, 'reuse-ledger', { input, mode: 'eval', eligibilityDecisionId: dec10.decision_id });
const control = call(goodInput);
const entrySrc = fs.readFileSync(entry);
const contractSrc = fs.readFileSync(contractFile);
const safetyCases = [];
fs.rmSync(entry);
safetyCases.push({ case: 'entrypoint deleted after an eligible decision', expect: 'blocked', res: call(goodInput) });
fs.writeFileSync(entry, entrySrc);
fs.chmodSync(entry, 0o644);
safetyCases.push({ case: 'entrypoint not executable after an eligible decision', expect: 'blocked', res: call(goodInput) });
fs.chmodSync(entry, 0o755);
fs.rmSync(contractFile);
safetyCases.push({ case: 'contract file deleted after an eligible decision', expect: 'blocked', res: call(goodInput) });
fs.writeFileSync(contractFile, contractSrc);
safetyCases.push({ case: 'input the contract refuses, after an eligible decision', expect: 'rejected', res: call({ seed_registry: 1, probe_capability: 'x', sandbox: 's' }) });
const safetyShapes = safetyCases.map((c) => ({
  case: c.case,
  expected: c.expect,
  sealed: c.res.ok === true,
  status: c.res.manifest ? c.res.manifest.status : null,
  basis: c.res.manifest ? c.res.manifest.status_basis : c.res.error,
  adapter_exit_code: c.res.manifest ? c.res.manifest.adapter.exit_code : null
}));
out.items['10_execution_safety_stays_in_kernel'] = {
  verdict: dec10.eligible === true && control.ok === true && control.manifest.status === 'completed'
    && safetyShapes.every((s) => s.sealed === true && s.status === s.expected && s.adapter_exit_code === null) ? 'PASS' : 'FAIL',
  eligibility_decision_was_eligible: dec10.eligible,
  control_status_through_the_same_decision: control.manifest ? control.manifest.status : null,
  refusals_from_the_kernels_own_checks: safetyShapes,
  probe_home_removed: (fs.rmSync(probe2, { recursive: true, force: true }), true)
};

const summary = {};
for (const [k, v] of Object.entries(out.items)) summary[k] = v.verdict;
out.summary = summary;
out.all_pass = Object.values(summary).every((v) => v === 'PASS');
fs.writeFileSync(path.join(__dirname, 'shipbar.out.json'), JSON.stringify(out, null, 2) + '\n');
console.log(JSON.stringify(summary, null, 2));
console.log('all_pass:', out.all_pass);
console.log('wrote ' + path.join(__dirname, 'shipbar.out.json'));

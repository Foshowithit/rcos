'use strict';
// Step-5 ship-bar verifier. The bar is GPT's eighteen-item list from
// partsnap-rcos/GPT-REPLY-7-20260917.md, in its order.
//
// Mechanical where it can be, and honest about the two places it is not: the
// "no semantic router exists" and "never recomputes eligibility" items are
// checked by reading the shipped source as well as by behaviour, because a
// module that merely happened not to route would still pass a behavioural test.
//
// It creates selections in the live home — that is the step's own artifact, and
// the dogfood. It never rewrites a registry, a decision, a trace or a
// capability: probe homes are seeded copies, and every sabotage happens there.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync, execFileSync } = require('node:child_process');

const HOME = '/Users/adam26/zcode-rcos';
const E = require(path.join(HOME, 'lib/eligibility'));
const R = require(path.join(HOME, 'lib/registry'));
const I = require(path.join(HOME, 'lib/invocation'));
const S = require(path.join(HOME, 'lib/selection'));
const BIN = path.join(HOME, 'bin/rcos');

// The registry sha recorded immediately before this step's dogfood began. The
// live registry has moved since step 4 — the autonomous study loop rewrote it
// three times — so "unchanged" can only mean "unchanged across the step-5
// window", and the divergence from step 4 is named in item 18 rather than
// quietly dropped.
const REGISTRY_SHA_AT_STEP5_START = '0fe4c4cde218071465c486fde2941263743874cbf998ddd6b78665e120b1adc0';
const REGISTRY_SHA_AT_STEP4_COMMIT = '0379300de3fd72ca99ce82cc1f82aabafc196fb7946b6b966503ec538cd003a3';

// This step's own commit and the commit it was built on. Item 18 reads the
// commit's own paths from these rather than diffing across the range: the range
// also contains the study loop's commits, and a two-dot diff would charge their
// registry writes to this step.
const STEP5_COMMIT = '6c34ee2';
const STEP5_BASE = '5647877';

const sha256 = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const sha256of = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const writeJson = (p, v) => fs.writeFileSync(p, JSON.stringify(v, null, 2) + '\n');

function snap() {
  const reuse = {};
  for (const cap of R.loadRegistry(HOME).capabilities) reuse[cap.id] = cap.reuse_count;
  return {
    registry_sha256: sha256(path.join(HOME, 'registry/capability-registry.json')),
    traces_sha256: fs.existsSync(path.join(HOME, 'traces/traces.jsonl')) ? sha256(path.join(HOME, 'traces/traces.jsonl')) : null,
    trace_lines: fs.existsSync(path.join(HOME, 'traces/traces.jsonl'))
      ? fs.readFileSync(path.join(HOME, 'traces/traces.jsonl'), 'utf8').split('\n').filter((l) => l.trim().length > 0).length
      : 0,
    reuse_counts: reuse
  };
}

// A probe home is a throwaway copy of the real registry, capabilities and evals.
// Sabotage is only ever applied here. The guard is not decoration: an earlier
// draft of this file called removeProbe with the live home by mistake, and a
// recursive delete that trusts its argument is one typo away from being the
// worst line in the repository.
function probeHome(tag) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'step5-' + tag + '-'));
  for (const sub of ['registry', 'capabilities', 'evals']) {
    fs.cpSync(path.join(HOME, sub), path.join(dir, sub), { recursive: true });
  }
  return dir;
}
const removeProbe = (dir) => {
  if (typeof dir !== 'string' || !dir.startsWith(os.tmpdir() + path.sep) || dir === HOME) {
    throw new Error('refusing to delete ' + dir + ' — removeProbe only deletes probe directories under ' + os.tmpdir());
  }
  fs.rmSync(dir, { recursive: true, force: true });
  return true;
};

// The two capabilities that are compete-eligible in the live registry. Every
// probe home inherits that, so these names are the dogfood's real cast, not
// fixtures invented for the test. They are the only two because candidacy is
// not enough on its own — a candidate must also be runnable, and only these two
// carry an adapter today.
const CAST = ['agents-md-compactor', 'reuse-ledger'];

// Widens the cast inside a probe home only, so a check that needs a third
// candidate is not forced to invent an artifact. It borrows reuse-ledger's
// adapter block; nothing ever executes it, because every check that needs a
// third candidate is about the candidate SET, not about running anything.
function makeThirdEligible(home, id) {
  const p = path.join(home, 'registry/capability-registry.json');
  const doc = readJson(p);
  const src = doc.capabilities.find((c) => c.id === 'reuse-ledger');
  const t = doc.capabilities.find((c) => c.id === id);
  t.status = 'candidate';
  t.adapter = JSON.parse(JSON.stringify(src.adapter));
  writeJson(p, doc);
  return id;
}
const compete = (home, id, opts) => E.decideForHome(home, id, Object.assign({ purpose: 'eval', scope: 'compete' }, opts));
const execute = (home, id, purpose) => E.decideForHome(home, id, { purpose: purpose || 'eval', scope: 'execute' });
const REUSE_INPUT = (home) => ({
  seed_registry: path.join(home, 'evals/reuse-ledger-invariant-v1/fixtures/seed-registry.json'),
  probe_capability: 'fixture-cap',
  sandbox: 'reuse-ledger-step5-probe'
});

// Probe selectors. These exist to prove the interface is replaceable and that
// the core does not judge what a selector returns — they are injected through
// the documented opts.selectors seam, never by editing lib/selection.js.
const probeSelectors = (impl) => Object.assign({ explicit: S.SELECTORS.explicit }, impl);

// Reads a source file with comments removed, so a check for "this code does not
// rank candidates" cannot be satisfied or defeated by prose. String literals are
// preserved: a refusal message is shipped behaviour and is fair game.
function stripComments(src) {
  let out = '';
  let i = 0;
  let quote = null;
  while (i < src.length) {
    const c = src[i];
    const n = src[i + 1];
    if (quote) {
      out += c;
      if (c === '\\') { out += n === undefined ? '' : n; i += 2; continue; }
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue; }
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue; }
    if (c === '/' && n === '*') {
      i += 2;
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1;
      i += 2;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

function runCli(home, argv) {
  const res = spawnSync('node', [BIN].concat(argv), { env: Object.assign({}, process.env, { RCOS_HOME: home }), encoding: 'utf8' });
  return { exit: res.status, stdout: res.stdout || '', stderr: res.stderr || '' };
}

const out = { home: HOME, checked_at: new Date().toISOString(), items: {} };
const before = snap();
out.before = before;

const reg = R.loadRegistry(HOME);
const selSrc = fs.readFileSync(path.join(HOME, 'lib/selection.js'), 'utf8');
const selCode = stripComments(selSrc);
const invSrc = fs.readFileSync(path.join(HOME, 'lib/invocation.js'), 'utf8');
const cliSrc = fs.readFileSync(BIN, 'utf8');

// ---- item 1: consumes only verified scope=compete eligible decisions --------
// The candidate set is built from decision ARTIFACTS, so the refusal has to
// survive four different lies: the wrong scope, an ineligible decision, a
// decision that does not exist, and a decision whose bytes were edited.
const h1 = probeHome('i1');
const cA = compete(h1, CAST[0]);
const cB = compete(h1, CAST[1]);
const xA = execute(h1, CAST[1]);
const otherCaps = reg.capabilities.map((c) => c.id).filter((id) => !CAST.includes(id));
const ineligId = otherCaps[0];
const inelig = compete(h1, ineligId);
const selectIn = (decisionIds, input) => S.createSelection(h1, {
  selectorInput: input === undefined ? { capability_id: CAST[1] } : input,
  candidateDecisionIds: decisionIds
});
const i1Control = selectIn([cA.decision_id, cB.decision_id]);
const i1ExecuteScope = selectIn([xA.decision_id]);
const i1Ineligible = selectIn([inelig.decision_id]);
const i1Missing = selectIn(['elig_20260918T000000Z-000000']);
const i1NotAnId = selectIn(['not-a-decision-id']);
const tamperPath = path.join(E.decisionDir(h1, cA.decision_id), 'decision.json');
const cABytes = fs.readFileSync(tamperPath, 'utf8');
const tamperedDoc = JSON.parse(cABytes);
tamperedDoc.eligible = false;
writeJson(tamperPath, tamperedDoc);
const i1Tampered = selectIn([cA.decision_id]);
fs.writeFileSync(tamperPath, cABytes);
out.items['1_consumes_only_verified_compete_decisions'] = {
  verdict: i1Control.ok === true && i1Control.status === 'selected' && i1Control.candidates.length === 2
    && i1ExecuteScope.ok === false && /scope 'execute'/.test(i1ExecuteScope.error)
    && i1Ineligible.ok === false && /does not permit competition/.test(i1Ineligible.error)
    && i1Missing.ok === false && /no such eligibility decision artifact/.test(i1Missing.error)
    && i1NotAnId.ok === false && /not a decision id/.test(i1NotAnId.error)
    && i1Tampered.ok === false && /does not verify/.test(i1Tampered.error) ? 'PASS' : 'FAIL',
  control: { status: i1Control.status, candidates: i1Control.candidates.map((c) => c.capability_id) },
  control_candidate_pins: i1Control.candidates,
  refusals: {
    'scope=execute decision offered as a candidate': i1ExecuteScope.error,
    ['compete decision that says no (' + ineligId + ', reasons: ' + inelig.reasons.join(', ') + ')']: i1Ineligible.error,
    'decision id that names no artifact': i1Missing.error,
    'string that is not a decision id': i1NotAnId.error,
    'decision whose bytes were edited after it was written': i1Tampered.error
  },
  tampered_bytes_restored: fs.readFileSync(tamperPath, 'utf8') === cABytes
};
removeProbe(h1);

// ---- item 2: never recomputes eligibility -----------------------------------
// Two proofs, and the second one is the real one.
//
// Source: the module must not call anything that produces a decision.
//
// Behaviour: a decision whose recorded verdict a fresh question would now
// contradict must still be consumed as recorded. `reuse-ledger` is a candidate,
// and candidacy is decided by the CALLER CONTEXT — an eval-purpose caller is
// allowed to elect a candidate, a normal-purpose caller is not. So one artifact
// says "may compete" and a fresh normal-purpose question about the same
// capability in the same home says "may not". Selection follows the artifact.
// If it were recomputing, it would have to answer with the context it invented
// for itself, and there is no context to invent: a selection has no caller
// context and no purpose, which is exactly why it may not re-ask.
//
// Verification still reads the registry, and that is not recomputation: it
// checks that the decision names a capability that exists at the version the
// decision recorded. It never re-derives the verdict.
const decisionFns = ['evaluate(', 'decideForHome(', 'buildContext(', 'deriveRuntimeState(', 'orderReasons('];
const recomputeHits = decisionFns.filter((t) => selCode.includes(t));
const h2 = probeHome('i2');
const c2 = compete(h2, CAST[1]);                                  // purpose=eval → allow_candidate
const c2Normal = E.decideForHome(h2, CAST[1], { purpose: 'normal', scope: 'compete' }); // allow_candidate=false → refused
const freshNormal = E.evaluate(h2, CAST[1], E.buildContext('normal', { capabilityId: CAST[1], scope: 'compete' }));
const i2Select = S.createSelection(h2, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c2.decision_id] });
const i2Verify = S.verifySelection(h2, i2Select.selection_id);
const i2NormalOffered = S.createSelection(h2, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c2Normal.decision_id] });
const c2Path = path.join(E.decisionDir(h2, c2.decision_id), 'decision.json');
const c2Doc = readJson(c2Path);
const c2Verify = E.verifyDecision(h2, c2.decision_id);
out.items['2_never_recomputes_eligibility'] = {
  verdict: recomputeHits.length === 0 && i2Select.ok === true && i2Select.status === 'selected'
    && i2Verify.ok === true && c2Verify.ok === true
    && c2Doc.eligible === true && freshNormal.decision.eligible === false
    && freshNormal.decision.reasons.includes('candidate_not_allowed')
    && i2NormalOffered.ok === false && /does not permit competition/.test(i2NormalOffered.error) ? 'PASS' : 'FAIL',
  decision_producing_functions_called_by_selection_module: recomputeHits,
  the_recorded_decision: {
    decision_id: c2.decision_id,
    scope: c2Doc.scope,
    purpose: c2Doc.caller_context ? c2Doc.caller_context.purpose : null,
    eligible_as_recorded: c2Doc.eligible,
    artifact_still_verifies: c2Verify.ok
  },
  a_fresh_question_asked_differently_answers_differently: {
    context: 'purpose=normal, scope=compete — a caller who is not allowed to elect a candidate',
    eligible: freshNormal.decision.eligible,
    reasons: freshNormal.decision.reasons
  },
  selection_followed_the_recorded_verdict_not_a_recomputation: i2Select.status,
  selection_verifies: i2Verify.ok,
  the_opposite_decision_is_refused_as_a_candidate: { decision_id: c2Normal.decision_id, error: i2NormalOffered.error },
  why_this_is_the_proof: 'a selection carries no caller context and no purpose, so it has no way to ask the eligibility question again — it can only consume the answer it was handed',
  what_verification_does_read: 'the registry, to confirm the decision names a capability that exists at the recorded version — a reference check, never a verdict'
};
removeProbe(h2);

// ---- item 3: rcos-selection/1 is immutable and integrity-verifiable ---------
const h3 = probeHome('i3');
const c3a = compete(h3, CAST[0]);
const c3b = compete(h3, CAST[1]);
const i3 = S.createSelection(h3, { selectorInput: { capability_id: CAST[0] }, candidateDecisionIds: [c3a.decision_id, c3b.decision_id] });
const i3Path = path.join(S.selectionDir(h3, i3.selection_id), 'selection.json');
const i3Bytes = fs.readFileSync(i3Path, 'utf8');
const i3Verify = S.verifySelection(h3, i3.selection_id);
const editCases = [];
for (const [label, mutate] of [
  ['status_basis edited', (d) => { d.status_basis = 'a nicer sounding reason'; }],
  ['status flipped', (d) => { d.status = 'abstained'; d.selected_capability_id = null; }],
  ['a candidate sha replaced', (d) => { d.candidates[0].eligibility_sha256 = 'f'.repeat(64); }],
  ['a whole candidate removed', (d) => { d.candidates = d.candidates.slice(0, 1); }],
  ['integrity value itself edited', (d) => { d.integrity.value = 'f'.repeat(64); }]
]) {
  const d = JSON.parse(i3Bytes);
  mutate(d);
  fs.writeFileSync(i3Path, JSON.stringify(d, null, 2) + '\n');
  const v = S.verifySelection(h3, i3.selection_id);
  editCases.push({ edit: label, verified: v.ok, problems: v.problems });
  fs.writeFileSync(i3Path, i3Bytes);
}
let i3WriteOnce = null;
try {
  S.createSelection(h3, { selectorInput: { capability_id: CAST[0] }, candidateDecisionIds: [c3a.decision_id, c3b.decision_id], selectionId: i3.selection_id });
  i3WriteOnce = { threw: false };
} catch (e) {
  i3WriteOnce = { threw: true, error: e.message };
}
out.items['3_schema_immutable_integrity_verifiable'] = {
  verdict: S.SELECTION_SCHEMA === 'rcos-selection/1' && i3Verify.ok === true && i3Verify.checked === 3
    && editCases.every((c) => c.verified === false)
    && i3WriteOnce.threw === true && /write-once/.test(i3WriteOnce.error) ? 'PASS' : 'FAIL',
  schema_constant: S.SELECTION_SCHEMA,
  control_verifies: { ok: i3Verify.ok, decisions_and_selection_rechecked: i3Verify.checked },
  edits_caught: editCases.map((c) => ({ edit: c.edit, verified: c.verified, first_problem: c.problems[0] })),
  bytes_restored_after_each_edit: fs.readFileSync(i3Path, 'utf8') === i3Bytes,
  write_once: i3WriteOnce
};
removeProbe(h3);

// ---- item 4: the candidate set is exact and hash-pinned ---------------------
const h4 = probeHome('i4');
const thirdId = makeThirdEligible(h4, otherCaps[0]);
const c4a = compete(h4, CAST[0]);
const c4b = compete(h4, CAST[1]);
const c4c = compete(h4, thirdId);
const i4 = S.createSelection(h4, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c4a.decision_id, c4b.decision_id] });
const i4Doc = i4.selection;
const i4Path = path.join(S.selectionDir(h4, i4.selection_id), 'selection.json');
// Recomputed the way the module recomputes it, from the bytes on disk.
const i4Recomputed = sha256of(JSON.stringify(i4Doc.candidates, null, 2) + '\n');
const i4Three = S.createSelection(h4, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c4a.decision_id, c4b.decision_id, c4c.decision_id] });
const i4Dup = S.createSelection(h4, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c4a.decision_id, c4a.decision_id] });
const i4Bytes = fs.readFileSync(i4Path, 'utf8');
const i4Edit = JSON.parse(i4Bytes);
i4Edit.candidates[0].eligibility_sha256 = 'a'.repeat(64);
fs.writeFileSync(i4Path, JSON.stringify(i4Edit, null, 2) + '\n');
const i4EditVerify = S.verifySelection(h4, i4.selection_id);
fs.writeFileSync(i4Path, i4Bytes);
const i4VersionLie = JSON.parse(i4Bytes);
i4VersionLie.candidates[1].capability_version = '9.9.9';
fs.writeFileSync(i4Path, JSON.stringify(i4VersionLie, null, 2) + '\n');
const i4VersionVerify = S.verifySelection(h4, i4.selection_id);
fs.writeFileSync(i4Path, i4Bytes);
out.items['4_candidate_set_exact_and_hash_pinned'] = {
  verdict: i4Doc.candidate_set_sha256 === i4Recomputed
    && i4Doc.candidates.length === 2
    && i4Doc.candidates.map((c) => c.capability_id).join(',') === CAST.join(',')
    && i4Doc.candidates.every((c) => typeof c.capability_version === 'string' && /^elig_/.test(c.eligibility_decision_id) && c.eligibility_sha256.length === 64)
    && i4Three.ok === true && i4Three.selection.candidate_set_sha256 !== i4Doc.candidate_set_sha256
    && i4Dup.ok === false && /more than once/.test(i4Dup.error)
    && i4EditVerify.ok === false && /eligibility_sha256 does not match/.test(i4EditVerify.problems.join(' '))
    && i4VersionVerify.ok === false && /decision names version/.test(i4VersionVerify.problems.join(' ')) ? 'PASS' : 'FAIL',
  candidate_set_sha256: i4Doc.candidate_set_sha256,
  recomputed_independently_from_the_artifact: i4Recomputed,
  pins_per_candidate: i4Doc.candidates,
  exactness: 'candidates.length === the number of decisions supplied, one entry per decision, in the order supplied',
  the_third_candidate: { capability_id: thirdId, decision_id: c4c.decision_id, how: 'the probe home widened the cast — the live registry has exactly two runnable candidates, so a three-candidate set cannot be built from it' },
  adding_a_third_candidate_changes_the_hash: { status: i4Three.status, sha256: i4Three.selection ? i4Three.selection.candidate_set_sha256 : null, changed: i4Three.ok === true && i4Three.selection.candidate_set_sha256 !== i4Doc.candidate_set_sha256 },
  duplicate_refusal: i4Dup.error,
  candidate_sha_edit_caught: i4EditVerify.problems,
  candidate_version_lie_caught: i4VersionVerify.problems,
  bytes_restored: fs.readFileSync(i4Path, 'utf8') === i4Bytes
};
removeProbe(h4);

// ---- item 5: core validates membership, not semantic quality ----------------
// Two selectors that are confidently wrong in different ways. The core must
// accept both and record what they said, because judging a selector's reasoning
// inside the audit path would be a second, quieter selector.
const h5 = probeHome('i5');
const c5a = compete(h5, CAST[0]);
const c5b = compete(h5, CAST[1]);
const ids5 = [c5a.decision_id, c5b.decision_id];
const alwaysLast = {
  id: 'always-last', version: '1',
  validateInput: () => [],
  select: ({ candidates }) => ({ status: 'selected', selected_capability_id: candidates[candidates.length - 1].capability_id, reason: 'I picked the last one. No reason.' })
};
const liar = {
  id: 'liar', version: '1',
  validateInput: () => [],
  select: ({ candidates }) => ({ status: 'selected', selected_capability_id: candidates[0].capability_id, reason: candidates[0].capability_id + ' is clearly the best match for this task' })
};
const i5a = S.createSelection(h5, { selectorId: 'always-last', selectorInput: { ignore: 'this' }, candidateDecisionIds: ids5, selectors: probeSelectors({ 'always-last': alwaysLast }) });
const i5b = S.createSelection(h5, { selectorId: 'liar', selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: ids5, selectors: probeSelectors({ liar }) });
const i5bVerify = S.verifySelection(h5, i5b.selection_id);
const judgementWords = ['similarity', 'cosine', 'embedding', 'score', 'rank', 'best match', 'keyword', 'heuristic', 'prefer'];
const judgementHits = judgementWords.filter((t) => selCode.toLowerCase().includes(t));
out.items['5_membership_not_semantic_quality'] = {
  verdict: i5a.ok === true && i5a.status === 'selected' && i5a.selected_capability_id === CAST[1]
    && i5b.ok === true && i5b.status === 'selected' && i5bVerify.ok === true
    && i5b.selection.status_basis === CAST[0] + ' is clearly the best match for this task'
    && judgementHits.length === 0 ? 'PASS' : 'FAIL',
  a_selector_that_ignores_its_input_entirely: { status: i5a.status, selected: i5a.selected_capability_id, basis: i5a.status_basis },
  a_selector_that_states_a_claim_the_core_cannot_check: { status: i5b.status, selected: i5b.selected_capability_id, basis_recorded_verbatim: i5b.selection.status_basis, still_verifies: i5bVerify.ok },
  judgement_vocabulary_in_the_shipped_core: judgementHits,
  what_the_core_did_check: 'that the named capability is one of the candidates — nothing else',
  what_it_did_not_check: ['whether the choice was smart', 'whether the task semantically matched', 'whether another candidate was better', 'whether the rationale is true']
};
removeProbe(h5);

// ---- item 6: only explicit@1 is implemented --------------------------------
const installed = Object.keys(S.SELECTORS);
const i6Model = S.resolveSelector(S.SELECTORS, 'model-selector', null);
const i6Planner = S.resolveSelector(S.SELECTORS, 'planner', null);
const i6Single = S.resolveSelector(S.SELECTORS, 'single_candidate', null);
const i6Version = S.resolveSelector(S.SELECTORS, 'explicit', '2');
// Code, not comments: the module is allowed to say out loud which selectors it
// deliberately does not have.
const futureSelectorCodeHits = ['single_candidate', 'workflow-declared', 'workflow_declared', 'model-selector', 'model_selector', 'learned-router', 'experiment-selector', 'planner']
  .filter((t) => selCode.includes(t));
const futureSelectorCommentMentions = ['model-selector', 'learned-router', 'planner']
  .filter((t) => selSrc.includes(t) && !selCode.includes(t));
out.items['6_only_explicit_1'] = {
  verdict: installed.length === 1 && installed[0] === 'explicit'
    && S.SELECTORS.explicit.id === 'explicit' && S.SELECTORS.explicit.version === '1'
    && [i6Model, i6Planner, i6Single].every((r) => r.ok === false && /no selector/.test(r.error))
    && i6Version.ok === false && /is version 1, not '2'/.test(i6Version.error)
    && futureSelectorCodeHits.length === 0 ? 'PASS' : 'FAIL',
  installed_selectors: installed,
  shipped_selector: { id: S.SELECTORS.explicit.id, version: S.SELECTORS.explicit.version, members: Object.keys(S.SELECTORS.explicit) },
  named_but_not_installed_refusals: {
    'model-selector': i6Model.error,
    planner: i6Planner.error,
    single_candidate: i6Single.error,
    'explicit@2': i6Version.error
  },
  future_selector_names_present_as_code: futureSelectorCodeHits,
  future_selector_names_present_only_in_comments: futureSelectorCommentMentions,
  note: 'the empty slots are named in prose and implemented nowhere — that is the healthy state GPT asked for'
};

// ---- item 7: selector implementations use a replaceable interface -----------
// A selector that exists only in this file, injected through opts.selectors,
// with no edit to lib/selection.js, produces a real artifact.
const h7 = probeHome('i7');
const c7a = compete(h7, CAST[0]);
const c7b = compete(h7, CAST[1]);
const abstainer = {
  id: 'probe-abstain', version: '3',
  validateInput: (input) => (input && input.ok === true ? [] : ['probe-abstain needs {ok: true}']),
  select: () => ({ status: 'abstained', selected_capability_id: null, reason: 'probe-abstain declines to choose' })
};
const i7 = S.createSelection(h7, { selectorId: 'probe-abstain', selectorVersion: '3', selectorInput: { ok: true }, candidateDecisionIds: [c7a.decision_id, c7b.decision_id], selectors: probeSelectors({ 'probe-abstain': abstainer }) });
const i7BadInput = S.createSelection(h7, { selectorId: 'probe-abstain', selectorVersion: '3', selectorInput: { ok: false }, candidateDecisionIds: [c7a.decision_id, c7b.decision_id], selectors: probeSelectors({ 'probe-abstain': abstainer }) });
const i7Verify = S.verifySelection(h7, i7.selection_id);
out.items['7_replaceable_selector_interface'] = {
  verdict: i7.ok === true && i7.selection.selector.id === 'probe-abstain' && i7.selection.selector.version === '3'
    && i7.status === 'abstained' && i7Verify.ok === true
    && i7BadInput.ok === false && /rejected its input/.test(i7BadInput.error) ? 'PASS' : 'FAIL',
  interface_the_core_calls: ['id', 'version', 'validateInput(input) -> string[]', 'select({candidates, selector_input}) -> {status, selected_capability_id, reason}'],
  shipped_selector_members: Object.keys(S.SELECTORS.explicit),
  injected_selector_recorded_in_the_artifact: i7.selection.selector,
  injected_selector_status: i7.status,
  injected_selector_input_rule_enforced_by_the_selector: i7BadInput.error,
  artifact_verifies: i7Verify.ok,
  core_edited_to_do_this: false
};
removeProbe(h7);

// ---- item 8: selector-specific input is opaque to the core -----------------
// The core stores the input verbatim and hashes the bytes; it never reads a key.
const h8 = probeHome('i8');
const c8a = compete(h8, CAST[0]);
const c8b = compete(h8, CAST[1]);
const exotic = { frobnicate: 7, nested: { a: [1, 2, { deep: true }] }, 'a key with spaces': 'and: punctuation', unicode: 'né—ü' };
const permissive = { id: 'permissive', version: '1', validateInput: () => [], select: ({ candidates }) => ({ status: 'selected', selected_capability_id: candidates[0].capability_id, reason: 'first' }) };
const i8 = S.createSelection(h8, { selectorId: 'permissive', selectorInput: exotic, candidateDecisionIds: [c8a.decision_id, c8b.decision_id], selectors: probeSelectors({ permissive }) });
const i8Verify = S.verifySelection(h8, i8.selection_id);
const universalVocabulary = ['task_text', 'taskText', 'intent', 'similarity', 'domain', 'scores', 'embedding', 'prompt'];
const universalHits = universalVocabulary.filter((t) => selCode.includes(t));
const explicitRefusals = {
  unknown_key: S.SELECTORS.explicit.validateInput({ capability_id: CAST[0], task_text: 'please pick the best one' }),
  missing_key: S.SELECTORS.explicit.validateInput({}),
  wrong_type: S.SELECTORS.explicit.validateInput({ capability_id: 7 })
};
out.items['8_selector_input_opaque_to_core'] = {
  verdict: i8.ok === true && JSON.stringify(i8.selection.selector_input) === JSON.stringify(exotic)
    && i8.selection.selector_input_sha256 === sha256of(JSON.stringify(exotic, null, 2) + '\n')
    && i8Verify.ok === true && universalHits.length === 0
    && explicitRefusals.unknown_key.length === 1 && explicitRefusals.missing_key.length === 1 && explicitRefusals.wrong_type.length === 1 ? 'PASS' : 'FAIL',
  exotic_input_stored_verbatim: i8.selection.selector_input,
  input_sha256: i8.selection.selector_input_sha256,
  recomputed_from_the_input_alone: sha256of(JSON.stringify(exotic, null, 2) + '\n'),
  artifact_verifies: i8Verify.ok,
  universal_vocabulary_keys_in_the_core: universalHits,
  the_only_closed_vocabulary_is_the_selectors_own: { selector: 'explicit@1', accepts_exactly: ['capability_id'], refusals: explicitRefusals },
  note: 'the core has no opinion about what a selector asks for; explicit@1 is the strict one, and it enforces that itself'
};
removeProbe(h8);

// ---- item 9: the five statuses are structurally distinct -------------------
const h9 = probeHome('i9');
const c9a = compete(h9, CAST[0]);
const c9b = compete(h9, CAST[1]);
const ids9 = [c9a.decision_id, c9b.decision_id];
const mk = (status, extra) => ({ id: 'p-' + status, version: '1', validateInput: () => [], select: () => Object.assign({ status }, extra || {}) });
const i9selected = S.createSelection(h9, { selectorInput: { capability_id: CAST[0] }, candidateDecisionIds: ids9 });
const i9abstained = S.createSelection(h9, { selectorId: 'p-abstained', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-abstained': mk('abstained', { selected_capability_id: null, reason: 'declined' }) }) });
const i9ambiguous = S.createSelection(h9, { selectorId: 'p-ambiguous', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-ambiguous': mk('ambiguous', { selected_capability_id: null, reason: 'two look alike' }) }) });
const i9noCandidates = S.createSelection(h9, { selectorInput: { capability_id: CAST[0] }, candidateDecisionIds: [] });
const i9failed = S.createSelection(h9, { selectorId: 'p-throws', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-throws': { id: 'p-throws', version: '1', validateInput: () => [], select: () => { throw new Error('kaboom'); } } }) });
const i9coreStatusFromSelector = S.createSelection(h9, { selectorId: 'p-no_candidates', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-no_candidates': mk('no_candidates') }) });
const i9failedStatusFromSelector = S.createSelection(h9, { selectorId: 'p-failed', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-failed': mk('failed') }) });
const i9strayName = S.createSelection(h9, { selectorId: 'p-stray', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-stray': mk('selected', { selected_capability_id: 'a-capability-nobody-offered' }) }) });
const i9abstainNamesOne = S.createSelection(h9, { selectorId: 'p-names', selectorInput: null, candidateDecisionIds: ids9, selectors: probeSelectors({ 'p-names': mk('abstained', { selected_capability_id: CAST[0] }) }) });
const five = {
  selected: i9selected,
  abstained: i9abstained,
  ambiguous: i9ambiguous,
  no_candidates: i9noCandidates,
  failed: i9failed
};
const fiveNames = Object.values(five).map((r) => r.status);
const exitByStatus = {};
for (const [name, r] of Object.entries(five)) {
  const cli = runCli(h9, ['selection-verify', '--selection', r.selection_id]);
  exitByStatus[name] = { verify_exit: cli.exit, selection_status: r.status };
}
out.items['9_five_statuses_structurally_distinct'] = {
  verdict: new Set(fiveNames).size === 5 && fiveNames.every((n) => S.SELECTION_STATUSES.includes(n))
    && five.selected.selected_capability_id === CAST[0]
    && [five.abstained, five.ambiguous, five.no_candidates, five.failed].every((r) => r.selected_capability_id === null)
    && JSON.stringify(S.SELECTOR_RESULT_STATUSES) === JSON.stringify(['selected', 'abstained', 'ambiguous'])
    && i9coreStatusFromSelector.status === 'failed' && /core's to report, not a selector's/.test(i9coreStatusFromSelector.status_basis)
    && i9failedStatusFromSelector.status === 'failed'
    && i9strayName.status === 'failed' && /not a capability in the candidate set/.test(i9strayName.status_basis)
    && i9abstainNamesOne.status === 'failed' && /an abstention or an ambiguity selects nothing/.test(i9abstainNamesOne.status_basis) ? 'PASS' : 'FAIL',
  canonical_order: S.SELECTION_STATUSES,
  selector_may_return: S.SELECTOR_RESULT_STATUSES,
  produced: {
    selected: { basis: five.selected.status_basis, selected: five.selected.selected_capability_id },
    abstained: { basis: five.abstained.status_basis, selected: five.abstained.selected_capability_id },
    ambiguous: { basis: five.ambiguous.status_basis, selected: five.ambiguous.selected_capability_id },
    no_candidates: { basis: five.no_candidates.status_basis, selected: five.no_candidates.selected_capability_id },
    failed: { basis: five.failed.status_basis, selected: five.failed.selected_capability_id }
  },
  only_selected_names_a_capability: [five.selected, five.abstained, five.ambiguous, five.no_candidates, five.failed].map((r) => r.selected_capability_id),
  a_selector_may_not_produce_core_statuses: { no_candidates: i9coreStatusFromSelector.status_basis, failed: i9failedStatusFromSelector.status_basis },
  membership_is_still_enforced: { stray_name: i9strayName.status_basis, abstention_that_names_one: i9abstainNamesOne.status_basis },
  every_status_verifies_and_exit_codes: exitByStatus
};
removeProbe(h9);

// ---- item 10: selection does not grant execution permission -----------------
// Six ways of trying to turn an election into authority.
const h10 = probeHome('i10');
const c10a = compete(h10, CAST[1]);
const c10b = compete(h10, CAST[0]);
const x10 = execute(h10, CAST[1]);
const sel10 = S.createSelection(h10, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [c10a.decision_id, c10b.decision_id] });
const sel10Abstain = S.createSelection(h10, { selectorId: 'p-abstained', selectorInput: null, candidateDecisionIds: [c10a.decision_id, c10b.decision_id], selectors: probeSelectors({ 'p-abstained': { id: 'p-abstained', version: '1', validateInput: () => [], select: () => ({ status: 'abstained', selected_capability_id: null, reason: 'declined' }) } }) });
const input10 = REUSE_INPUT(h10);
const tryInvoke = (opts) => I.invokeCapability(h10, CAST[1], Object.assign({ input: input10, mode: 'eval' }, opts));
const sel10Path = path.join(S.selectionDir(h10, sel10.selection_id), 'selection.json');
const sel10Bytes = fs.readFileSync(sel10Path, 'utf8');
// A refusal here is not a thrown error: the kernel seals the attempt as an
// invocation with status 'blocked', so the audit trail records what was tried.
// The byte-tamper case runs LAST — an edited selection is refused for its
// integrity before the kernel can say anything about which capability it chose.
const tenCases = {
  'a compete decision offered as the authorizing decision': tryInvoke({ eligibilityDecisionId: c10a.decision_id }),
  'a valid selection and no decision at all': tryInvoke({ selectionId: sel10.selection_id }),
  'a selection that chose a different capability': I.invokeCapability(h10, CAST[0], { input: REUSE_INPUT(h10), mode: 'eval', eligibilityDecisionId: execute(h10, CAST[0]).decision_id, selectionId: sel10.selection_id }),
  'a selection that abstained': tryInvoke({ eligibilityDecisionId: x10.decision_id, selectionId: sel10Abstain.selection_id }),
  'a selection id that names no artifact': tryInvoke({ eligibilityDecisionId: x10.decision_id, selectionId: 'sel_20260918T000000Z-000000' })
};
const tamper10 = JSON.parse(sel10Bytes);
tamper10.selected_capability_id = CAST[0];
fs.writeFileSync(sel10Path, JSON.stringify(tamper10, null, 2) + '\n');
tenCases['a selection whose bytes were edited after it was written'] = tryInvoke({ eligibilityDecisionId: x10.decision_id, selectionId: sel10.selection_id });
fs.writeFileSync(sel10Path, sel10Bytes);
const tenShapes = {};
for (const [k, v] of Object.entries(tenCases)) {
  tenShapes[k] = {
    sealed: v.ok === true,
    refused_as: v.manifest ? v.manifest.status : (v.ok === false ? 'error' : null),
    error: v.ok === false ? v.error : null,
    basis: v.manifest ? v.manifest.status_basis : null
  };
}
const basis10 = (k) => String(tenShapes[k].basis || tenShapes[k].error || '');
// Every attempt is refused. Five are sealed as blocked invocations — the kernel
// had a decision artifact and a selection to reason about, so it recorded the
// refusal. One is a plain error, because an invocation with no eligibility
// decision at all has nothing to seal: that is a caller bug, not an attempt.
const expected10 = {
  'a compete decision offered as the authorizing decision': 'blocked',
  'a valid selection and no decision at all': 'error',
  'a selection that chose a different capability': 'blocked',
  'a selection that abstained': 'blocked',
  'a selection id that names no artifact': 'blocked',
  'a selection whose bytes were edited after it was written': 'blocked'
};
const control10 = tryInvoke({ eligibilityDecisionId: x10.decision_id, selectionId: sel10.selection_id });
out.items['10_selection_grants_no_authority'] = {
  verdict: Object.keys(expected10).every((k) => tenShapes[k].refused_as === expected10[k])
    && /scope 'compete'/.test(basis10('a compete decision offered as the authorizing decision'))
    && /may stand for election/.test(basis10('a compete decision offered as the authorizing decision'))
    && /requires an eligibility decision/.test(basis10('a valid selection and no decision at all'))
    && /selection chose/.test(basis10('a selection that chose a different capability'))
    && /only a selection that named a capability/.test(basis10('a selection that abstained'))
    && /integrity mismatch/.test(basis10('a selection whose bytes were edited after it was written'))
    && /no such selection artifact/.test(basis10('a selection id that names no artifact'))
    && control10.ok === true && control10.manifest.status === 'completed' ? 'PASS' : 'FAIL',
  refusals: tenShapes,
  refusal_shapes: expected10,
  control_with_a_real_execute_decision_and_the_same_selection: { sealed: control10.ok, status: control10.manifest ? control10.manifest.status : null },
  the_shape_of_a_refusal: 'sealed and status=blocked, never an error — the attempt is recorded as a blocked invocation so the audit trail shows what was tried',
  the_three_meanings: { selection: 'WHICH', eligibility: 'MAY', kernel: 'CAN EXECUTE SAFELY' }
};
removeProbe(h10);

// ---- item 11: the winner receives a FRESH scope=execute decision ------------
// Read off the live dogfood, both legs, straight from the artifacts.
const dogfood = fs.readdirSync(path.join(HOME, 'invocations')).sort()
  .map((id) => {
    const p = path.join(HOME, 'invocations', id, 'manifest.json');
    if (!fs.existsSync(p)) return null;
    const m = readJson(p);
    if (!m.selection_id) return null;
    const sel = S.readSelection(HOME, m.selection_id);
    const dec = readJson(path.join(E.decisionDir(HOME, m.eligibility_decision_id), 'decision.json'));
    return {
      invocation_id: id,
      capability_id: m.capability_id,
      mode: m.mode,
      status: m.status,
      selection_id: m.selection_id,
      selection_status: sel.status,
      selection_winner: sel.selected_capability_id,
      selection_decided_at: sel.decided_at,
      competing_decisions: sel.candidates.map((c) => ({ capability_id: c.capability_id, decision_id: c.eligibility_decision_id, scope: 'compete' })),
      execute_decision_id: m.eligibility_decision_id,
      execute_decision_scope: dec.scope,
      execute_decision_purpose: dec.caller_context ? dec.caller_context.purpose : null,
      execute_decision_capability_id: dec.capability_id,
      execute_decision_created_at: dec.created_at,
      execute_decision_is_fresh: sel.candidates.every((c) => c.eligibility_decision_id !== m.eligibility_decision_id),
      execute_decision_after_the_selection: dec.created_at >= sel.decided_at
    };
  })
  .filter(Boolean);
// The live asymmetry: for one real capability the two questions disagree today.
const asym = {};
for (const id of CAST) {
  const c = E.evaluate(HOME, id, E.buildContext('eval', { capabilityId: id, scope: 'compete' }));
  const x = E.evaluate(HOME, id, E.buildContext('normal', { capabilityId: id, scope: 'execute' }));
  asym[id] = {
    may_compete_at_purpose_eval: c.decision.eligible,
    may_execute_at_purpose_normal: x.decision.eligible,
    execute_refusal_reasons: x.decision.reasons
  };
}
out.items['11_winner_gets_a_fresh_execute_decision'] = {
  verdict: dogfood.length >= 2
    && dogfood.every((d) => d.execute_decision_scope === 'execute' && d.execute_decision_is_fresh
      && d.execute_decision_after_the_selection && d.execute_decision_capability_id === d.selection_winner)
    && Object.values(asym).some((a) => a.may_compete_at_purpose_eval === true && a.may_execute_at_purpose_normal === false) ? 'PASS' : 'FAIL',
  dogfood_invocations_that_came_through_a_selection: dogfood,
  live_asymmetry_between_the_two_questions: asym,
  why_this_matters: 'a MAY_COMPETE decision must never authorize execution — measured live, the same capability is compete-eligible and normal-mode execute-ineligible in the same instant'
};

// ---- item 12: the kernel still requires execute eligibility -----------------
const h12 = probeHome('i12');
const x12 = execute(h12, CAST[0], 'normal');
const c12 = compete(h12, CAST[0]);
const i12 = I.invokeCapability(h12, CAST[0], { input: { fixture: path.join(h12, 'evals/agents-md-compactor-v1/fixtures/AGENTS-fixture.md') }, mode: 'eval', eligibilityDecisionId: x12.decision_id });
const i12Compete = I.invokeCapability(h12, CAST[0], { input: { fixture: path.join(h12, 'evals/agents-md-compactor-v1/fixtures/AGENTS-fixture.md') }, mode: 'eval', eligibilityDecisionId: c12.decision_id });
const i12Good = I.invokeCapability(h12, CAST[0], { input: { fixture: path.join(h12, 'evals/agents-md-compactor-v1/fixtures/AGENTS-fixture.md') }, mode: 'eval', eligibilityDecisionId: execute(h12, CAST[0], 'eval').decision_id });
const sealedAs = (r) => (r.ok === true && r.manifest ? r.manifest.status : (r.ok === false ? 'error' : null));
out.items['12_kernel_still_requires_execute_eligibility'] = {
  verdict: x12.eligible === false && c12.eligible === true
    && sealedAs(i12) === 'blocked' && sealedAs(i12Compete) === 'blocked'
    && i12Good.ok === true && i12Good.manifest.status === 'completed' ? 'PASS' : 'FAIL',
  an_ineligible_execute_decision: { eligible: x12.eligible, reasons: x12.reasons, kernel_sealed_it_as: sealedAs(i12), basis: i12.manifest ? i12.manifest.status_basis : (i12.error || null) },
  a_compete_decision_that_says_yes: { eligible: c12.eligible, kernel_sealed_it_as: sealedAs(i12Compete), basis: i12Compete.manifest ? i12Compete.manifest.status_basis : (i12Compete.error || null) },
  an_eligible_execute_decision: { sealed: i12Good.ok, status: i12Good.manifest ? i12Good.manifest.status : null },
  note: 'the kernel asks its own question from its own decision artifact and never inherits an answer from the selection — and a compete decision is refused even when it says eligible, because eligibility is per-scope'
};
removeProbe(h12);

// ---- item 13: provenance can be pinned into invocation artifacts ------------
const newest = dogfood.length > 0 ? dogfood[dogfood.length - 1] : null;
let i13 = { verdict: 'FAIL', reason: 'no dogfood invocation found' };
if (newest) {
  const h13 = probeHome('i13');
  const invDir = path.join(HOME, 'invocations', newest.invocation_id);
  fs.cpSync(invDir, path.join(h13, 'invocations', newest.invocation_id), { recursive: true });
  // The whole decision and selection trees, not just the two artifacts this
  // invocation names: verification re-reads the selection, and the selection
  // names its own competing candidate decisions. A partial copy would fail for
  // a missing artifact rather than for the tamper under test.
  fs.cpSync(path.join(HOME, 'eligibility'), path.join(h13, 'eligibility'), { recursive: true });
  fs.cpSync(path.join(HOME, 'selections'), path.join(h13, 'selections'), { recursive: true });
  const good = I.verifyInvocation(h13, newest.invocation_id);
  const selFile = path.join(h13, 'selections', newest.selection_id, 'selection.json');
  const selBytes = fs.readFileSync(selFile, 'utf8');
  const edited = JSON.parse(selBytes);
  edited.status_basis = 'edited after the invocation was sealed';
  fs.writeFileSync(selFile, JSON.stringify(edited, null, 2) + '\n');
  const afterTamper = I.verifyInvocation(h13, newest.invocation_id);
  fs.writeFileSync(selFile, selBytes);
  const restored = I.verifyInvocation(h13, newest.invocation_id);
  const manifest = readJson(path.join(invDir, 'manifest.json'));
  i13 = {
    verdict: good.ok === true && afterTamper.ok === false && restored.ok === true
      && manifest.selection_id === newest.selection_id && typeof manifest.selection_sha256 === 'string'
      && manifest.selection && manifest.selection.selected_capability_id === newest.selection_winner ? 'PASS' : 'FAIL',
    invocation_id: newest.invocation_id,
    pinned: { selection_id: manifest.selection_id, selection_sha256: manifest.selection_sha256, block: manifest.selection },
    artifacts_re_hashed_when_verifying: good.checked,
    verify_ok: good.ok,
    tampering_with_the_pinned_selection_breaks_verification: { ok: afterTamper.ok, problems: afterTamper.problems },
    restored_verifies_again: restored.ok,
    probe_home_removed: removeProbe(h13)
  };
}
out.items['13_provenance_pinned_into_invocation'] = i13;

// ---- item 14: a direct run needs no artificial selection --------------------
const h14 = probeHome('i14');
const x14 = execute(h14, CAST[1]);
const i14 = I.invokeCapability(h14, CAST[1], { input: REUSE_INPUT(h14), mode: 'eval', eligibilityDecisionId: x14.decision_id });
const cli14 = runCli(h14, ['run', CAST[1], '--input', (() => {
  const p = path.join(h14, 'direct-run-input.json');
  writeJson(p, REUSE_INPUT(h14));
  return p;
})(), '--mode', 'eval']);
out.items['14_direct_run_needs_no_selection'] = {
  verdict: i14.ok === true && i14.manifest.status === 'completed' && i14.manifest.selection_id === null && i14.manifest.selection === null
    && cli14.exit === 0 && !/^selection:/m.test(cli14.stdout) ? 'PASS' : 'FAIL',
  direct_invocation: { status: i14.manifest.status, selection_id: i14.manifest.selection_id, selection_block: i14.manifest.selection },
  direct_cli_run: { exit: cli14.exit, printed_selection_line: /^selection:/m.test(cli14.stdout) },
  note: 'selection is provenance a caller may attach, never a step a caller must perform'
};
removeProbe(h14);

// ---- item 15: selection changes neither reuse_count nor traces --------------
// Live: the selections below are created in the real home, and the registry,
// the trace file and every reuse_count must come out byte-identical.
const liveCompete = {};
for (const id of CAST) liveCompete[id] = compete(HOME, id, { purpose: 'eval', scope: 'compete' });
const liveIds = [liveCompete[CAST[0]].decision_id, liveCompete[CAST[1]].decision_id];
const liveSelected = S.createSelection(HOME, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: liveIds });
const liveOffSet = S.createSelection(HOME, { selectorInput: { capability_id: 'a-capability-that-does-not-exist' }, candidateDecisionIds: liveIds });
const liveNoCandidates = S.createSelection(HOME, { selectorInput: { capability_id: CAST[1] }, candidateDecisionIds: [] });
// The selection module must write its own artifact and nothing else. The
// vocabulary is the trace and reuse ledger by name — a bare writeFileSync is
// how the selection artifact itself is written, so it is not evidence of anything.
const traceWriters = ['traces', 'traces.jsonl', 'reuse_count', 'reuse-log', 'appendFileSync', 'deriveReuseCounts'].filter((t) => selCode.includes(t));
const after = snap();
const reuseMoved = Object.keys(before.reuse_counts).filter((k) => before.reuse_counts[k] !== after.reuse_counts[k]);
out.items['15_selection_moves_no_reuse_and_no_trace'] = {
  verdict: traceWriters.length === 0
    && before.registry_sha256 === after.registry_sha256
    && before.traces_sha256 === after.traces_sha256
    && before.trace_lines === after.trace_lines
    && reuseMoved.length === 0 ? 'PASS' : 'FAIL',
  live_selections_created_during_this_check: {
    selected: { id: liveSelected.selection_id, status: liveSelected.status, winner: liveSelected.selected_capability_id },
    abstained: { id: liveOffSet.selection_id, status: liveOffSet.status, basis: liveOffSet.status_basis },
    no_candidates: { id: liveNoCandidates.selection_id, status: liveNoCandidates.status }
  },
  trace_and_reuse_identifiers_in_the_selection_module: traceWriters,
  what_the_selection_module_does_write: 'exactly one file: selections/<selection_id>/selection.json, written once and never rewritten',
  registry_sha256: { before: before.registry_sha256, after: after.registry_sha256, identical: before.registry_sha256 === after.registry_sha256 },
  traces_sha256: { before: before.traces_sha256, after: after.traces_sha256, identical: before.traces_sha256 === after.traces_sha256 },
  trace_lines: { before: before.trace_lines, after: after.trace_lines },
  reuse_counts_moved: reuseMoved,
  note: 'selection is not reuse: selected is not invoked, and invoked is not successfully reused'
};
out.after = after;
out.live_dogfood = {
  selected: liveSelected.selection_id,
  abstained: liveOffSet.selection_id,
  no_candidates: liveNoCandidates.selection_id,
  compete_decisions_minted: liveIds
};

// ---- item 16: no semantic routing, ranking, model or planner exists ---------
const routingVocabulary = ['similarity', 'cosine', 'embedding', 'tfidf', 'keyword', 'rank', 'score', 'heuristic', 'predict', 'learn', 'weight', 'llm', 'openai', 'anthropic', 'gpt', 'prompt', 'planner', 'intent', 'task_text', 'semantic', 'route', 'router', 'classify', 'nearest'];
const routingHitsInSelection = routingVocabulary.filter((t) => selCode.toLowerCase().includes(t));
const routingHitsInCliSelect = routingVocabulary.filter((t) => {
  const i = cliSrc.indexOf("case 'select'");
  const j = cliSrc.indexOf("case 'invocations'");
  return i >= 0 && j > i && stripComments(cliSrc.slice(i, j)).toLowerCase().includes(t);
});
out.items['16_no_semantic_routing_ranking_model_or_planner'] = {
  verdict: routingHitsInSelection.length === 0 && routingHitsInCliSelect.length === 0 && installed.length === 1 ? 'PASS' : 'FAIL',
  vocabulary_searched: routingVocabulary,
  hits_in_lib_selection_code: routingHitsInSelection,
  hits_in_the_cli_select_surface: routingHitsInCliSelect,
  how_a_choice_is_actually_made: 'explicit@1 compares one string the caller supplied against the candidate capability ids. There is no other way for a capability to be chosen in this build.',
  installed_selectors: installed,
  deferred_and_absent: ['LLM router', 'learned router', 'ranking', 'similarity', 'task interpretation', 'cost-aware selection', 'latency-aware selection', 'workflow planner', 'fallback selector', 'automatic retries']
};

// ---- item 17: Step 1–4 invariants and tests remain green -------------------
const suite = spawnSync('npm', ['test'], { cwd: HOME, encoding: 'utf8' });
const suiteOut = (suite.stdout || '') + (suite.stderr || '');
// node --test prints its counters as "ℹ tests 87" (the summary block), not as
// TAP's "# tests 87", so match the label anywhere on a line that ends in the
// number. The parsed lines are kept verbatim in the output as evidence.
const counter = (label) => {
  const m = suiteOut.match(new RegExp('^[^\\n]*\\b' + label + '\\s+(\\d+)\\s*$', 'm'));
  return m ? Number(m[1]) : null;
};
const countersAsPrinted = suiteOut.split('\n').filter((l) => /^[^\n]*\b(tests|pass|fail|skipped|cancelled|todo)\s+\d+\s*$/.test(l));
// Step 4's own verifier is re-run from a copy, so its recorded output of record
// is never overwritten by this step.
const step4Dir = path.join(HOME, 'evidence/2026-09-17-step4-eligibility');
const rerunDir = fs.mkdtempSync(path.join(os.tmpdir(), 'step5-step4rerun-'));
fs.copyFileSync(path.join(step4Dir, 'shipbar-verify.js'), path.join(rerunDir, 'shipbar-verify.js'));
const step4Run = spawnSync('node', [path.join(rerunDir, 'shipbar-verify.js')], { encoding: 'utf8' });
const step4Rerun = fs.existsSync(path.join(rerunDir, 'shipbar.out.json')) ? readJson(path.join(rerunDir, 'shipbar.out.json')) : null;
const step4Recorded = readJson(path.join(step4Dir, 'shipbar.out.json'));
const itemVerdictsMatch = step4Rerun !== null
  && Object.keys(step4Recorded.summary).every((k) => step4Rerun.summary[k] === step4Recorded.summary[k]);
out.items['17_step1_to_4_still_green'] = {
  verdict: suite.status === 0 && counter('tests') !== null && counter('pass') !== null && counter('fail') === 0
    && counter('pass') === counter('tests')
    && step4Rerun !== null && step4Rerun.all_pass === true && itemVerdictsMatch ? 'PASS' : 'FAIL',
  suite: { exit: suite.status, tests: counter('tests'), pass: counter('pass'), fail: counter('fail'), skipped: counter('skipped') },
  suite_counters_as_printed: countersAsPrinted,
  test_files: fs.readdirSync(path.join(HOME, 'tests')).filter((f) => /\.test\.js$/.test(f)).sort(),
  step4_verifier_rerun_from_a_copy: { exit: step4Run.status, all_pass: step4Rerun ? step4Rerun.all_pass : null, items: step4Rerun ? Object.keys(step4Rerun.summary).length : null },
  step4_recorded_verdicts: step4Recorded.summary,
  step4_rerun_verdicts: step4Rerun ? step4Rerun.summary : null,
  every_item_verdict_unchanged: itemVerdictsMatch,
  step4_evidence_of_record_untouched: sha256(path.join(step4Dir, 'shipbar.out.json')),
  rerun_home_removed: removeProbe(rerunDir)
};

// ---- item 18: the registry is unchanged ------------------------------------
// "Unchanged" can only mean "unchanged by this step": an autonomous study loop
// commits machine-written registry and trace updates on its own schedule, and
// one of those landed inside this step's window. So the gate is the part step 5
// actually owns — this harness moved nothing, nothing is left uncommitted, and
// this step's own commit touched neither file. Which other commits did touch
// them is recorded as provenance, not asserted as a gate, because another
// lane's commit is not evidence about the selection bus.
const regNow = sha256(path.join(HOME, 'registry/capability-registry.json'));
const trNow = sha256(path.join(HOME, 'traces/traces.jsonl'));
const regStatus = execFileSync('git', ['status', '--porcelain', '--', 'registry/', 'traces/'], { cwd: HOME, encoding: 'utf8' }).trim();
const gitLines = (args) => execFileSync('git', args, { cwd: HOME, encoding: 'utf8' }).split('\n').filter((l) => l.trim().length > 0);
const stepOwnPaths = gitLines(['diff-tree', '--no-commit-id', '--name-only', '-r', STEP5_COMMIT]);
const stepTouchedDataFiles = stepOwnPaths.filter((p) => /^(registry|traces)\//.test(p));
const STUDY_LOOP_SUBJECT = /^(evals\(|evals:|registry\+traces:)/;
const dataCommitsInWindow = gitLines(['log', '--format=%h\t%ad\t%s', '--date=short', STEP5_BASE + '..HEAD', '--', 'registry/', 'traces/'])
  .map((l) => {
    const [sha, date, ...rest] = l.split('\t');
    const subject = rest.join('\t');
    return { sha, date, subject, by_study_loop: STUDY_LOOP_SUBJECT.test(subject) };
  });
out.items['18_registry_unchanged'] = {
  verdict: regNow === before.registry_sha256 && regNow === after.registry_sha256
    && trNow === before.traces_sha256 && trNow === after.traces_sha256
    && regStatus === '' && stepTouchedDataFiles.length === 0 ? 'PASS' : 'FAIL',
  unchanged_across_this_harness: regNow === before.registry_sha256 && trNow === before.traces_sha256,
  registry_sha256_before_this_harness: before.registry_sha256,
  registry_sha256_after_this_harness: regNow,
  traces_sha256_before_this_harness: before.traces_sha256,
  traces_sha256_after_this_harness: trNow,
  uncommitted_registry_or_trace_changes: regStatus === '' ? '(none)' : regStatus,
  this_steps_own_commit: STEP5_COMMIT,
  this_steps_own_commit_paths: stepOwnPaths,
  this_steps_own_commit_touched_registry_or_traces: stepTouchedDataFiles,
  registry_sha256_at_step5_start: REGISTRY_SHA_AT_STEP5_START,
  registry_moved_after_the_step5_start: regNow !== REGISTRY_SHA_AT_STEP5_START,
  registry_sha256_at_the_step4_commit: REGISTRY_SHA_AT_STEP4_COMMIT,
  divergence_from_step4: regNow !== REGISTRY_SHA_AT_STEP4_COMMIT,
  window_provenance_not_a_gate: {
    note: 'every commit in ' + STEP5_BASE + '..HEAD that touched registry/ or traces/, attributed — recorded so a reader can see who moved the data; deliberately not part of the verdict',
    commits: dataCommitsInWindow,
    every_one_is_a_study_loop_commit: dataCommitsInWindow.every((c) => c.by_study_loop)
  }
};

const summary = {};
for (const [k, v] of Object.entries(out.items)) summary[k] = v.verdict;
out.summary = summary;
out.all_pass = Object.values(summary).every((v) => v === 'PASS');
fs.writeFileSync(path.join(__dirname, 'shipbar.out.json'), JSON.stringify(out, null, 2) + '\n');
console.log(JSON.stringify(summary, null, 2));
console.log('all_pass:', out.all_pass);
console.log('wrote ' + path.join(__dirname, 'shipbar.out.json'));

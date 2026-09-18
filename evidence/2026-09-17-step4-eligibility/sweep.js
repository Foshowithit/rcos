'use strict';
// Step-4 dogfood sweep: ask the eligibility engine about every capability in the
// real registry, under every purpose. Read-only — it uses evaluate(), which
// returns a decision without persisting one, so this writes nothing at all.
const fs = require('node:fs');
const path = require('node:path');
const E = require('/Users/adam26/zcode-rcos/lib/eligibility');
const R = require('/Users/adam26/zcode-rcos/lib/registry');

const home = '/Users/adam26/zcode-rcos';
const reg = R.loadRegistry(home);
const purposes = ['normal', 'eval', 'forensic'];
const out = { home, registry_capabilities: reg.capabilities.length, purposes: {} };

for (const p of purposes) {
  const opts = { purpose: p };
  if (p === 'forensic') opts.forensicReason = 'step-4 dogfood sweep — read-only, no invocation is recorded';
  const rows = [];
  for (const cap of reg.capabilities) {
    const ctx = E.buildContext(p, Object.assign({ capabilityId: cap.id }, opts));
    const res = E.evaluate(home, cap.id, ctx);
    if (!res.ok) { console.log('ERROR ' + cap.id + ': ' + res.error); continue; }
    rows.push({
      id: cap.id,
      status: cap.status,
      version: cap.version,
      executable: res.state.executable,
      provenance: res.state.provenance,
      eligible: res.decision.eligible,
      reasons: res.decision.reasons
    });
  }
  const eligible = rows.filter((r) => r.eligible).map((r) => r.id).sort();
  const hist = {};
  for (const r of rows) {
    const k = r.reasons.join(' + ') || '(eligible)';
    hist[k] = (hist[k] || 0) + 1;
  }
  out.purposes[p] = { eligible_count: eligible.length, total: rows.length, eligible, histogram: hist, rows };
  console.log('=== purpose: ' + p + ' ===');
  console.log('eligible ' + eligible.length + '/' + rows.length + ': ' + (eligible.join(', ') || '(none)'));
  const sorted = Object.entries(hist).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  for (const [k, v] of sorted) console.log('  ' + String(v).padStart(2) + '  ' + k);
  console.log('');
}
fs.writeFileSync(path.join(__dirname, 'sweep.out.json'), JSON.stringify(out, null, 2) + '\n');
console.log('wrote ' + path.join(__dirname, 'sweep.out.json'));

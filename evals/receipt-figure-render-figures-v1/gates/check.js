#!/usr/bin/env node
'use strict';

// Gates for receipt-figure-render-figures-v1 (rcos-eval/2). Each gate reads the
// CAPABILITY's recorded observation — $RCOS_INVOCATION_DIR/output.json, the bytes
// the invocation kernel froze and hashed — re-reads the raw stream and artifact
// bytes the run wrote into its own evidence dir, re-derives the figure geometry
// from the REGISTRY THE RUN ITSELF READ, and compares the result against the
// figures committed in evidence/receipt-figure-render/ months before this eval
// existed. Never the capability's live state, never this eval's fixtures dir.
//
// Two facts make the pixel legs exact rather than approximate:
//   * the frozen renderer fills whole pixels with three fixed palette colours and
//     draws every glyph in antialiased (20,20,20)-on-white, which never lands on a
//     palette colour — so the palette-coloured pixel set IS the rectangle coverage,
//     and this gate re-derives that coverage arithmetically (floor-inclusive
//     rectangles, painter's order) instead of trusting a rendered image;
//   * the historical sidecars carry an absolute `source` path, and a reproduction
//     writes its own registry copy's path there — so the round trip is asserted as
//     "byte-identical modulo exactly that one field's value", with the fresh value
//     resolved to the run's own copy by realpath and re-hashed against the pin.
//
// The checker's `per_capability differs` line is the one place a subset of its
// output is order-unstable: with two or more diffed ids the entries come out of a
// Python set and their order varies with PYTHONHASHSEED (measured: 40 checker
// subprocesses on the capability-shift case produced two orderings, 22/18). That
// gate therefore asserts the line's shape, the id set and each (sidecar, recompute)
// pair as substrings, never the byte order; every single-key and dict leg is exact.
//
// Exit 0 = pass, 3 = fail, 4 = no observation to judge.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const { spawnSync } = require('node:child_process');

const id = process.argv[2];
const invocationDir = process.env.RCOS_INVOCATION_DIR;
if (!invocationDir) {
  console.error('blocked: RCOS_INVOCATION_DIR is not set — this gate judges an invocation, not a work dir');
  process.exit(4);
}
const outputPath = path.join(invocationDir, 'output.json');
if (!fs.existsSync(outputPath)) {
  console.error('blocked: ' + outputPath + ' not found — the capability produced no observation');
  process.exit(4);
}
const O = JSON.parse(fs.readFileSync(outputPath, 'utf8'));

const work = process.env.RCOS_WORK_DIR;      // the runner's work dir: the frozen fixtures the cases read
const runDir = process.env.RCOS_RUN_DIR;
const home = process.env.RCOS_HOME;
// The kernel runs the adapter with cwd = the INVOCATION's own work dir, and every
// run-local artifact the observation records (case dirs, figures, sidecar) is
// spelled relative to that dir — not relative to the runner's RCOS_WORK_DIR, which
// holds the frozen fixtures the run read FROM. Two different roots.
const invWork = path.join(invocationDir, 'work');

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const hashFile = (p) => sha256(fs.readFileSync(p));
const realOr = (p) => {
  try {
    return fs.realpathSync(p);
  } catch (e) {
    return p;
  }
};
// A recorded path is judged as the file it resolves to, never as a string: on macOS
// /tmp and /private/tmp (and any symlinked work root) must judge identically.
function under(base, p) {
  if (typeof p !== 'string' || p === '') return null;
  return path.isAbsolute(p) ? p : path.resolve(base, p);
}
// The frozen scripts and the committed evidence, by home-relative path as the
// capability's own record spells them.
function homePath(rel) {
  if (!home) return null;
  const p = path.join(home, rel.replace(/^[/\\]+/, ''));
  return fs.existsSync(p) ? p : null;
}

const FIGURE_NAMES = ['fig-verdicts.png', 'fig-per-capability.png'];
const SIDECAR_NAME = 'values.json';

// The frozen sources this package executes. Re-hashed from home at judge time and
// compared both to the observation's record and to these pins.
const RENDERER_PATH = 'capabilities/receipt-figure-render/adapter/receipt_figures.py';
const CHECKER_PATH = 'capabilities/receipt-figure-render/adapter/check_figures.py';
const RENDERER_SHA = 'd4acec8466741e1a1e37172dd8c629ecdddef5e96cd9244dcf6b55808d55553e';
const CHECKER_SHA = 'a4a51bfe7c9547c9de7e88aa19bf8063c21bef62ecf53ab3e3c226387bff6cbc';

// The 13 fixtures, by the sha256 of the bytes in this eval's fixtures/ dir. Nine of
// them are the historical artifacts as they were committed in
// evidence/receipt-figure-render/ (four figures, two sidecars, the tampered attack
// sidecar, the registry at 74 evals, the registry as reconstructed at 75); three are
// authored inputs (the 21-capability registry, the capability-shift attack sidecar,
// the two registry degenerates). The HISTORY map below ties the historical ones to
// the committed files by reading them out of the repo tree.
const FIXTURES = {
  'empty-registry.json': { sha256: 'c086eb5b4e010c6992a8b486a65433330c799c380fd0b55eeffcfac52668eefc', bytes: 67 },
  'malformed-registry.json': { sha256: '2373d2c337a2c28a25ec53ee0a6c37cce9d6c0a8b13d7e399b07a97c05fd5ba0', bytes: 59 },
  'oracle-fig-per-capability-74.png': { sha256: '83e6f3d5a9379860efbab4066186e6f724680a4cb81d4a3d48835cf5d5ccefb0', bytes: 44703 },
  'oracle-fig-per-capability-75.png': { sha256: '1fb79b8c61005951362e01415b663a27781afc1b1a8a5098f4c88a5fb03fba57', bytes: 44610 },
  'oracle-fig-verdicts-74.png': { sha256: 'f432049f84175b65bebc149b46a0c7aa23ee768668e2b8feb8cdf7dc638b9288', bytes: 6610 },
  'oracle-fig-verdicts-75.png': { sha256: '384e4fda1b8526f21032dd8917760d01c759d12e798a7c4c8cd3a7ec22d00aae', bytes: 6551 },
  'registry-21-caps.json': { sha256: '26f161eef96ec2bdea9652cf818bd3de13342059c6241b323b074cdb0b4be388', bytes: 26977 },
  'registry-74.json': { sha256: '1439e88a327146cb8ed2a70ba261709abcdb9a6ab3c733ac8768e71296b12da9', bytes: 26595 },
  'registry-75-reconstructed.json': { sha256: '5f30394f3fe89fd328c56c2067ef979f600fbb24a6d7d0268ba455480f8d6a09', bytes: 26915 },
  'values-cap-shifted.json': { sha256: '8d52af02f04d1ca02be9d2b2c77463a30a34d6f7f853fa50be769fd75c4af9e0', bytes: 1975 },
  'values-historical-74.json': { sha256: '12420d1b726ba9b3f900f97d48181912ba7381cfc61571399a0ba78bd7f2f0f0', bytes: 1974 },
  'values-historical-75.json': { sha256: 'e871124f3808962e06bd6eabc43a90a351ecbf35721c17460816a596320907b7', bytes: 1974 },
  'values-tampered.json': { sha256: '4d09e7b6be53156ccc8ca0b5da8556650802cf17f97250a80bebe19246a68098', bytes: 1382 },
};

// The committed figures and sidecars, by home-relative path: the oracle bytes the
// fresh renders must reproduce (eval-1 = the registry at 74, eval-2 = at 75) and the
// historical bytes the fixtures must still be.
const ORACLE = {
  'evidence/receipt-figure-render/eval-1/fig-verdicts.png': 'f432049f84175b65bebc149b46a0c7aa23ee768668e2b8feb8cdf7dc638b9288',
  'evidence/receipt-figure-render/eval-1/fig-per-capability.png': '83e6f3d5a9379860efbab4066186e6f724680a4cb81d4a3d48835cf5d5ccefb0',
  'evidence/receipt-figure-render/eval-2/fig-verdicts.png': '384e4fda1b8526f21032dd8917760d01c759d12e798a7c4c8cd3a7ec22d00aae',
  'evidence/receipt-figure-render/eval-2/fig-per-capability.png': '1fb79b8c61005951362e01415b663a27781afc1b1a8a5098f4c88a5fb03fba57',
};
const HISTORY = {
  'evidence/receipt-figure-render/eval-1/values.json': '12420d1b726ba9b3f900f97d48181912ba7381cfc61571399a0ba78bd7f2f0f0',
  'evidence/receipt-figure-render/eval-2/values.json': 'e871124f3808962e06bd6eabc43a90a351ecbf35721c17460816a596320907b7',
  'evidence/receipt-figure-render/attack/values-tampered.json': '4d09e7b6be53156ccc8ca0b5da8556650802cf17f97250a80bebe19246a68098',
};

// The historical sidecar's source field: the live registry path as of the day the
// figures were rendered. A reproduction writes its OWN copy's path here, so this
// exact literal belongs to the historical bytes only.
const HISTORICAL_SOURCE = '/Users/adam26/zcode-rcos/registry/capability-registry.json';

// The renderer's row order for the 74-eval registry: stable sort by descending eval
// count, ties in registry order. This is both the sidecar's key order and the paint
// order of figure 2's rows; the 21-capability fixture appends one zero-eval entry.
const CAP_ORDER_74 = [
  'video-forensics-receipt', 'creative-study-loop', 'qr-camo-embed', 'browser-verify-artifacts',
  'face-in-scene-shot', 'preview-server-verify', 'filmstrip-verify', 'muse-image-lane',
  'dell-gpu-dispatch', 'chalk-capture-recipe', 'hog-qa-suite', 'operator-ui-contract-test',
  'webgl-film-capture', 'shadow-play-staging', 'character-forge', 'local-talking-heads',
  'hunyuan3d-mlx-local', 'audio-offline-verify', 'x-media-package', 'receipt-figure-render',
];
const PROBE_ID = 'audit-control-probe';

// Measured palette-pixel counts, per figure per state — the non-vacuity anchors. A
// decoder that returned nothing, or a geometry that drifted, cannot pass these.
const PX = {
  'fig-verdicts.png@74': 24723,
  'fig-per-capability.png@74': 71847,
  'fig-verdicts.png@75': 24723,
  'fig-per-capability.png@75': 72819,
  'fig-verdicts.png@21': 24723,
  'fig-per-capability.png@21': 71847,
  'fig-verdicts.png@empty': 123,
};
// Figure heights: figure 1 is always 240; figure 2 is 60 + n*(26+10) + 40.
const FIG2_H = { 74: 820, 75: 820, 21: 856 };

const RENDER_CASES = ['historical_74', 'reconstructed_75', 'authored_21'];
const CHECK_CASES = ['historical_sidecar_74', 'historical_sidecar_75', 'attack_tampered', 'stale_sidecar', 'attack_capability_shifted'];
// The check cases whose sidecar is the historical render itself (those two must be
// byte-identical to the committed historical sidecar modulo the source field).
const ROUND_TRIP = [
  { case: 'historical_74', registry: 'registry-74.json', historical: 'values-historical-74.json', n_evals: 74 },
  { case: 'reconstructed_75', registry: 'registry-75-reconstructed.json', historical: 'values-historical-75.json', n_evals: 75 },
];
// The checker's pass line for each (registry, sidecar) pair this package exercises.
const PASS_LINE = (n, caps) => 'FIGURE_CHECK_PASS n=' + n + ' evals / ' + caps + ' caps, sidecar matches fresh registry recompute';
const RENDER_LINE = /^rendered fig-verdicts\.png fig-per-capability\.png values\.json \(n=(\d+) evals \/ (\d+) caps\) -> (.*)$/m;
// The frozen checker's measured fail lines for the three authored attack inputs,
// re-measured against the pinned checker before submission and asserted as exact
// lines. The single-key diffs are deterministic. The two-id per_capability diff
// is built from a Python set so its entry ORDER varies with PYTHONHASHSEED —
// only its id set and pairs are pinned (see shiftLineProblems), never the byte
// order.
const TAMPER_LINE = "FAIL verdict_distribution {'ship': 99, 'fix': 9, 'blocked': 0} != {'ship': 65, 'fix': 9, 'blocked': 0}";
const STALE_LINES = [
  'FAIL n_evals 75 != 74',
  "FAIL verdict_distribution {'ship': 66, 'fix': 9, 'blocked': 0} != {'ship': 65, 'fix': 9, 'blocked': 0}",
  "FAIL per_capability differs: {'receipt-figure-render': ({'ship': 1, 'fix': 0, 'blocked': 0}, {'ship': 0, 'fix': 0, 'blocked': 0})}",
];
const SHIFT_PAIRS = [
  "'muse-image-lane': ({'ship': 1, 'fix': 0, 'blocked': 0}, {'ship': 2, 'fix': 0, 'blocked': 0})",
  "'chalk-capture-recipe': ({'ship': 3, 'fix': 0, 'blocked': 0}, {'ship': 2, 'fix': 0, 'blocked': 0})",
];

const CASES = Array.isArray(O.cases) ? O.cases : [];
function caseOf(name) {
  return CASES.find((c) => c && c.name === name);
}
function frozenFixture(name) {
  if (!runDir) return null;
  const f = path.join(runDir, 'input.json');
  if (!fs.existsSync(f)) return null;
  const input = JSON.parse(fs.readFileSync(f, 'utf8'));
  const list = Array.isArray(input.fixtures) ? input.fixtures : [];
  return list.find((x) => (typeof x === 'string' ? x === name : x && x.name === name)) || null;
}
// The run's own copy of a fixture, wherever the two work roots put it.
function runCopyOf(name) {
  return work ? path.join(work, name) : null;
}
function figureOf(c, name) {
  return Array.isArray(c.figures) ? c.figures.find((f) => f.name === name) : undefined;
}
// The bytes of a case's produced file, read from the invocation work dir after
// checking them against the hash the observation recorded for them.
function producedBytes(c, recorded, base) {
  const p = under(invWork, recorded.path);
  if (!p) throw new Error(c.name + ': ' + base + ' has no recorded path');
  if (!fs.existsSync(p)) throw new Error(c.name + ': the recorded ' + base + ' is gone: ' + recorded.path);
  const buf = fs.readFileSync(p);
  if (sha256(buf) !== recorded.sha256) throw new Error(c.name + ': the bytes at ' + recorded.path + ' are not the ones the observation recorded for ' + base);
  return buf;
}
function figuresOf(c) {
  return FIGURE_NAMES.map((n) => figureOf(c, n));
}
// ---------- shared model: PNG decode, palette pixels, the frozen pixel contract ----------
// No requires here on purpose: this block is inlined verbatim into gates/check.js,
// which requires node:fs / node:path / node:zlib at its top.

// Palette measured from the frozen renderer (COLORS) and verified against the
// committed oracle bytes: every coloured pixel in every committed figure is
// exactly one of these three RGB values, in this order (ship, fix, blocked).
const VERDICTS = ['ship', 'fix', 'blocked'];
const PALETTE = [[46, 125, 76], [198, 128, 24], [150, 40, 40]];
const CFG = { W: 900, PAD: 30, BAR_H: 26, GAP: 10, FIG1_H: 240, VERDICTS, PALETTE };

function paeth(a, b, c) {
  const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

// Truecolor 8-bit, non-interlaced, filter types 0-4 — the format every figure in
// this package was measured to carry. Anything else is refused, not guessed at.
function decodePng(buf) {
  const sig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (buf.length < 8) throw new Error('not a PNG: ' + buf.length + ' bytes');
  for (let i = 0; i < 8; i++) if (buf[i] !== sig[i]) throw new Error('not a PNG: bad signature');
  let off = 8, ihdr = null;
  const idat = [];
  while (off + 12 <= buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('latin1', off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') {
      ihdr = {
        width: data.readUInt32BE(0), height: data.readUInt32BE(4),
        bitDepth: data[8], colorType: data[9], compression: data[10], filter: data[11], interlace: data[12],
      };
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    off += 12 + len;
  }
  if (!ihdr) throw new Error('PNG has no IHDR');
  if (ihdr.bitDepth !== 8 || ihdr.colorType !== 2 || ihdr.interlace !== 0) {
    throw new Error('unsupported PNG: bit_depth ' + ihdr.bitDepth + ' color_type ' + ihdr.colorType + ' interlace ' + ihdr.interlace);
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const bpp = 3, stride = ihdr.width * bpp, rows = ihdr.height;
  if (raw.length !== rows * (stride + 1)) {
    throw new Error('inflated ' + raw.length + ' bytes, expected ' + rows * (stride + 1));
  }
  const out = Buffer.alloc(rows * stride);
  for (let y = 0; y < rows; y++) {
    const ft = raw[y * (stride + 1)];
    const src = raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
    const dst = out.subarray(y * stride, (y + 1) * stride);
    const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : null;
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? dst[i - bpp] : 0;
      const b = prev ? prev[i] : 0;
      const c = prev && i >= bpp ? prev[i - bpp] : 0;
      const x = src[i];
      let v;
      if (ft === 0) v = x;
      else if (ft === 1) v = x + a;
      else if (ft === 2) v = x + b;
      else if (ft === 3) v = x + ((a + b) >> 1);
      else if (ft === 4) v = x + paeth(a, b, c);
      else throw new Error('unknown PNG filter type ' + ft + ' on row ' + y);
      dst[i] = v & 0xff;
    }
  }
  return { width: ihdr.width, height: ihdr.height, bitDepth: ihdr.bitDepth, colorType: ihdr.colorType, interlace: ihdr.interlace, rgb: out };
}

// The pixel contract: a pixel belongs to a bar iff its RGB equals a palette entry
// exactly. PIL fills whole pixels (no antialiasing) and draws text in (20,20,20),
// whose antialiased greys never equal a palette colour, so the palette-coloured
// pixel set IS the rectangle coverage. Verified against all four committed
// oracles and the measured empty-registry figure.
function palettePixels(png) {
  const m = new Map();
  const { width, height, rgb } = png;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 3, r = rgb[i], g = rgb[i + 1], b = rgb[i + 2];
      for (let k = 0; k < PALETTE.length; k++) {
        const p = PALETTE[k];
        if (p[0] === r && p[1] === g && p[2] === b) { m.set(x + ',' + y, k); break; }
      }
    }
  }
  return m;
}

// PIL's ImageDraw.rectangle([x0,y0,x1,y1]) fills columns floor(x0)..floor(x1) and
// rows floor(y0)..floor(y1), later rectangles overwriting shared pixels, and
// nothing outside the raster. Measured: a set union over-predicts by the 1-px
// boundary columns; a painter's map is exact.
function paintRect(m, x0, y0, x1, y1, val, W, H) {
  const cx0 = Math.floor(x0), cx1 = Math.floor(x1), cy0 = Math.floor(y0), cy1 = Math.floor(y1);
  for (let cy = cy0; cy <= cy1; cy++) {
    if (cy < 0 || cy >= H) continue;
    for (let cx = cx0; cx <= cx1; cx++) {
      if (cx < 0 || cx >= W) continue;
      m.set(cx + ',' + cy, val);
    }
  }
}

function countSum(counts) {
  let n = 0;
  for (const k of Object.keys(counts)) n += counts[k];
  return n;
}

function distOf(reg) {
  const d = { ship: 0, fix: 0, blocked: 0 };
  for (const c of reg.capabilities || []) {
    for (const e of c.evals || []) d[e.verdict] = (d[e.verdict] || 0) + 1;
  }
  return d;
}

// The renderer's row order: stable sort by descending eval count, i.e. ties keep
// the registry's own capability order (Python's sorted is stable; Array#sort in
// modern V8 is too, and the index tiebreak makes that explicit).
function perCapOf(reg) {
  const caps = reg.capabilities || [];
  const order = caps.map((c, i) => ({ i, c, n: Array.isArray(c.evals) ? c.evals.length : 0 }));
  order.sort((a, b) => (b.n - a.n) || (a.i - b.i));
  return order.map(({ c }) => {
    const counts = { ship: 0, fix: 0, blocked: 0 };
    for (const e of c.evals || []) counts[e.verdict] = (counts[e.verdict] || 0) + 1;
    return { id: c.id, counts };
  });
}

// Figure 1: one bar per verdict, x from PAD with 24px gaps, y 70..110, scale
// 600/max(1,n_evals).
function sim1(reg) {
  const d = distOf(reg);
  const m = new Map();
  const n = countSum(d);
  const scale = 600 / Math.max(1, n);
  let x = CFG.PAD;
  CFG.VERDICTS.forEach((v, k) => {
    paintRect(m, x, 70, x + d[v] * scale, 110, k, CFG.W, CFG.FIG1_H);
    x += d[v] * scale + 24;
  });
  return { map: m, n, dist: d };
}

// Figure 2: one row per capability, y = 60 + i*(BAR_H+GAP), bars from x=290, unit
// = (900-30-260)/max_ev, rows whose width is 0 draw nothing at all.
function sim2(reg) {
  const rows = perCapOf(reg);
  const H = 60 + rows.length * (CFG.BAR_H + CFG.GAP) + 40;
  const m = new Map();
  const maxEv = Math.max(1, ...rows.map((r) => countSum(r.counts)));
  const unit = (CFG.W - CFG.PAD - 260) / maxEv;
  let y = 60;
  for (const r of rows) {
    let x = CFG.PAD + 260;
    CFG.VERDICTS.forEach((v, k) => {
      const wpx = r.counts[v] * unit;
      if (wpx > 0) paintRect(m, x, y, x + wpx, y + CFG.BAR_H, k, CFG.W, H);
      x += wpx;
    });
    y += CFG.BAR_H + CFG.GAP;
  }
  return { map: m, height: H, rows, unit, maxEv };
}

// ---------- mirror of check_figures.py, so the gate can predict a verdict ----------
// Python prints a 2-tuple as "(a, b)" and the checker's per_capability diff holds
// (sidecar, recompute) tuples, so the predictor has to distinguish a tuple from a
// list to reproduce the exact line.
class PyTuple {
  constructor(items) { this.items = items; }
}

function pyRepr(v) {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (typeof v === 'string') return "'" + v.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
  if (v instanceof PyTuple) return '(' + v.items.map(pyRepr).join(', ') + (v.items.length === 1 ? ',' : '') + ')';
  if (Array.isArray(v)) return '[' + v.map(pyRepr).join(', ') + ']';
  return '{' + Object.keys(v).map((k) => pyRepr(k) + ': ' + pyRepr(v[k])).join(', ') + '}';
}

function recomputeFigures(reg) {
  const dist = { ship: 0, fix: 0, blocked: 0 };
  const perCap = {};
  for (const c of reg.capabilities) {
    const counts = { ship: 0, fix: 0, blocked: 0 };
    for (const e of c.evals || []) {
      counts[e.verdict] = (counts[e.verdict] || 0) + 1;
      dist[e.verdict] = (dist[e.verdict] || 0) + 1;
    }
    perCap[c.id] = counts;
  }
  return { dist, perCap, nCaps: reg.capabilities.length, nEvals: countSum(dist) };
}

function predictChecker(reg, vals) {
  const { dist, perCap, nCaps, nEvals } = recomputeFigures(reg);
  const g = (k) => (vals && typeof vals === 'object' ? vals[k] : undefined);
  const fail = [];
  if (g('n_capabilities') !== nCaps) fail.push('n_capabilities ' + pyRepr(g('n_capabilities')) + ' != ' + pyRepr(nCaps));
  if (g('n_evals') !== nEvals) fail.push('n_evals ' + pyRepr(g('n_evals')) + ' != ' + pyRepr(nEvals));
  const written = g('verdict_distribution');
  const sameDist = written && typeof written === 'object' &&
    Object.keys(written).length === Object.keys(dist).length &&
    Object.keys(dist).every((k) => written[k] === dist[k]);
  if (!sameDist) fail.push('verdict_distribution ' + pyRepr(written) + ' != ' + pyRepr(dist));
  const writtenPer = g('per_capability');
  const samePer = writtenPer && typeof writtenPer === 'object' &&
    Object.keys(writtenPer).length === Object.keys(perCap).length &&
    Object.keys(perCap).every((k) => {
      const a = writtenPer[k];
      return a && typeof a === 'object' &&
        Object.keys(a).length === Object.keys(perCap[k]).length &&
        Object.keys(perCap[k]).every((v) => a[v] === perCap[k][v]);
    });
  const diffed = {};
  if (!samePer) {
    const keys = new Set([...Object.keys(writtenPer || {}), ...Object.keys(perCap)]);
    for (const k of keys) {
      const a = writtenPer ? writtenPer[k] : undefined;
      const b = perCap[k];
      const aStr = a === undefined ? null : a, bStr = b === undefined ? null : b;
      if (pyRepr(aStr) !== pyRepr(bStr)) diffed[k] = new PyTuple([aStr, bStr]);
    }
    fail.push('per_capability differs: ' + pyRepr(diffed));
  }
  return { fail, dist, perCap, nCaps, nEvals, diffed };
}

// ---------- small text/JSON helpers shared with the gates ----------
function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function exactLine(stdout, s) {
  return new RegExp('^' + escapeRe(s) + '$', 'm').test(stdout);
}
// "byte-identical modulo exactly one field's value": replace the single JSON
// string literal of `sourceValue` in `text` with a placeholder, or return null if
// it does not appear exactly once.
function stripSource(text, sourceValue) {
  const lit = JSON.stringify(sourceValue);
  const first = text.indexOf(lit);
  if (first === -1) return null;
  if (text.indexOf(lit, first + lit.length) !== -1) return null;
  return text.slice(0, first) + '"<<source>>"' + text.slice(first + lit.length);
}
function deepEq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}
// ---------- preflight: the observation must not contradict its own evidence ----------
// The run's own raw bytes: the three stream files and one copy of every produced
// file, written under the invocation's evidence dir while the adapter ran.
function evidenceProblems() {
  const problems = [];
  if (O.schema !== 'receipt-figure-render-observation/1') {
    problems.push('schema is ' + JSON.stringify(O.schema) + ', not receipt-figure-render-observation/1');
  }
  if (!O.frozen || typeof O.frozen !== 'object') {
    problems.push('the observation records no frozen sources');
  }
  if (!Array.isArray(O.cases)) return problems.concat(['the observation contains no cases array']);
  for (const c of O.cases) {
    const base = path.join('evidence', 'case-' + c.name);
    const textLegs = [
      ['.stdout.txt', c.stdout, 'stdout'],
      ['.stderr.txt', c.stderr, 'stderr'],
    ];
    for (const [suffix, recorded, label] of textLegs) {
      const f = path.join(invocationDir, base + suffix);
      if (!fs.existsSync(f)) {
        problems.push(base + suffix + ' is missing — the recorded ' + label + ' has no bytes behind it');
        continue;
      }
      if (fs.readFileSync(f, 'utf8') !== recorded) {
        problems.push(base + suffix + ' does not match the ' + label + ' recorded in the observation');
      }
    }
    const argvFile = path.join(invocationDir, base + '.argv.json');
    if (!fs.existsSync(argvFile)) {
      problems.push(base + '.argv.json is missing — the recorded argv has no bytes behind it');
    } else {
      const onDisk = JSON.parse(fs.readFileSync(argvFile, 'utf8'));
      const same =
        onDisk && deepEq(onDisk.argv, c.argv) &&
        onDisk.exit_status === c.exit_status &&
        (onDisk.signal || null) === (c.signal || null) &&
        onDisk.duration_ms === c.duration_ms &&
        realOr(String(onDisk.cwd || '')) === realOr(invWork);
      if (!same) problems.push(base + '.argv.json does not match the argv, cwd and outcome recorded in the observation');
    }
    const produced = [];
    for (const f of (Array.isArray(c.figures) ? c.figures : [])) produced.push([f.name, f.sha256]);
    if (c.sidecar) produced.push([SIDECAR_NAME, c.sidecar.sha256]);
    for (const [name, sha] of produced) {
      const f = path.join(invocationDir, base + '.' + name);
      if (!fs.existsSync(f)) {
        problems.push(base + '.' + name + ' is missing — the recorded bytes have no copy behind them');
        continue;
      }
      if (hashFile(f) !== sha) problems.push(base + '.' + name + ' does not hash to the bytes the observation recorded');
    }
    const reg = c.registry;
    if (!reg || typeof reg !== 'object' || typeof reg.path !== 'string') {
      problems.push(base + ': the case records no registry');
    } else if (!fs.existsSync(reg.path)) {
      problems.push(base + ': the registry the case read is gone: ' + reg.path);
    } else if (hashFile(reg.path) !== reg.sha256) {
      problems.push(base + ': the registry at ' + reg.path + ' is not the bytes the case read');
    }
    if (c.operation === 'check') {
      const iv = c.input_values;
      if (!iv || typeof iv !== 'object' || typeof iv.path !== 'string') {
        problems.push(base + ': a check case records no input_values');
      } else if (!fs.existsSync(iv.path)) {
        problems.push(base + ': the sidecar the case read is gone: ' + iv.path);
      } else if (hashFile(iv.path) !== iv.sha256) {
        problems.push(base + ': the sidecar at ' + iv.path + ' is not the bytes the case read');
      }
    }
  }
  if (!fs.existsSync(path.join(invocationDir, 'evidence', 'frozen.sha256'))) {
    problems.push('evidence/frozen.sha256 is missing — the run recorded no source identity');
  }
  if (runDir && !fs.existsSync(path.join(runDir, 'input.json'))) {
    problems.push('the run has no input.json — the frozen fixture record is gone');
  }
  return problems;
}
const EVIDENCE = evidenceProblems();

// ---------- shared assertions ----------
const ok = (detail) => ({ ok: true, detail });
const no = (detail) => ({ ok: false, detail });
const done = (problems, detail) => (problems.length ? no(problems.join(' | ')) : ok(detail));

function regOf(c) {
  return JSON.parse(fs.readFileSync(c.registry.path, 'utf8'));
}
function fixtureBytes(name) {
  const p = runCopyOf(name);
  if (!p || !fs.existsSync(p)) throw new Error('the run has no copy of ' + name);
  return fs.readFileSync(p);
}
// Exact set equality of palette-coloured pixels, keys and colours both.
function mapDiff(got, want, label) {
  if (got.size !== want.size) return label + ' has ' + got.size + ' palette pixels, not ' + want.size;
  for (const [k, v] of want) {
    if (got.get(k) !== v) return label + ' differs at pixel ' + k + ' (got ' + got.get(k) + ', want ' + v + ')';
  }
  return null;
}
// Decode one produced figure and require its palette geometry to equal the model
// built from the registry the run itself read; `pxWant` is the independently
// measured historical count, so a model and a decoder wrong in the same way still
// cannot pass both.
function compareFigure(c, name, sim, label, pxWant) {
  const problems = [];
  const rec = figureOf(c, name);
  if (!rec) return [label + ': no ' + name + ' was produced'];
  const bytes = producedBytes(c, rec, name);
  let png;
  try {
    png = decodePng(bytes);
  } catch (e) {
    return [label + ': ' + name + ' cannot be decoded: ' + e.message];
  }
  if (png.width !== 900) problems.push(label + ': ' + name + ' is ' + png.width + ' px wide, not 900');
  if (png.height !== sim.height) problems.push(label + ': ' + name + ' is ' + png.height + ' px tall, not ' + sim.height);
  if (png.bitDepth !== 8 || png.colorType !== 2) problems.push(label + ': ' + name + ' is not 8-bit truecolor');
  if (rec.png && (rec.png.width !== png.width || rec.png.height !== png.height)) {
    problems.push(label + ': the observation\'s header for ' + name + ' disagrees with the bytes');
  }
  const got = palettePixels(png);
  const diff = mapDiff(got, sim.map, name);
  if (diff) problems.push(label + ': ' + diff);
  if (pxWant !== undefined && got.size !== pxWant) {
    problems.push(label + ': ' + name + ' carries ' + got.size + ' palette pixels, not the measured ' + pxWant);
  }
  return problems;
}
// A render case must have exited 0 with the frozen renderer's single stdout line
// naming its own out dir, written nothing to stderr, and produced both figures and
// a sidecar reporting the expected totals.
function renderProblems(c, want) {
  const problems = [];
  if (c.operation !== 'render') problems.push(c.name + ': operation is ' + JSON.stringify(c.operation) + ', not render');
  if (c.outcome !== 'rendered' || c.exit_status !== 0) {
    const tail = (c.stderr || '').trim().split('\n').slice(-1)[0];
    problems.push(c.name + ': exit=' + JSON.stringify(c.exit_status) + ' outcome=' + JSON.stringify(c.outcome) + ' — the render did not complete' + (tail ? ' (stderr tail: ' + tail + ')' : ''));
  }
  if (c.signal) problems.push(c.name + ': the render was signalled (' + c.signal + ')');
  if (c.stderr !== '') problems.push(c.name + ': the render wrote to stderr');
  const m = RENDER_LINE.exec(c.stdout || '');
  if (!m) {
    problems.push(c.name + ': stdout is not the renderer\'s single report line: ' + JSON.stringify(String(c.stdout || '').slice(0, 120)));
  } else {
    if (c.stdout !== m[0] + '\n') problems.push(c.name + ': stdout carries more than the one report line');
    if (Number(m[1]) !== want.n_evals || Number(m[2]) !== want.caps) {
      problems.push(c.name + ': the renderer reported n=' + m[1] + ' evals / ' + m[2] + ' caps (want ' + want.n_evals + ' / ' + want.caps + ')');
    }
    if (realOr(m[3]) !== realOr(path.join(invWork, 'case-' + c.name, 'out'))) {
      problems.push(c.name + ': the renderer reported writing to ' + m[3] + ', not its own case out dir');
    }
  }
  for (const name of FIGURE_NAMES) if (!figureOf(c, name)) problems.push(c.name + ': no ' + name + ' was produced');
  const v = c.sidecar && c.sidecar.values;
  if (!v || typeof v !== 'object') {
    problems.push(c.name + ': no parseable ' + SIDECAR_NAME + ' was produced');
  } else {
    if (v.n_evals !== want.n_evals) problems.push(c.name + ': the sidecar reports n_evals ' + JSON.stringify(v.n_evals) + ', not ' + want.n_evals);
    if (v.n_capabilities !== want.caps) problems.push(c.name + ': the sidecar reports n_capabilities ' + JSON.stringify(v.n_capabilities) + ', not ' + want.caps);
    if (want.dist && !deepEq(v.verdict_distribution, want.dist)) {
      problems.push(c.name + ': the sidecar\'s verdict_distribution is ' + JSON.stringify(v.verdict_distribution) + ', not ' + JSON.stringify(want.dist));
    }
    if (want.keys && !deepEq(Object.keys(v.per_capability || {}), want.keys)) {
      problems.push(c.name + ': the sidecar\'s per_capability keys are not the renderer\'s row order');
    }
  }
  return problems;
}
// The sidecar's source field must name the registry the case read, and that file
// must still be the pinned fixture bytes.
function sourceTieProblems(c, fixtureName) {
  const problems = [];
  const v = c.sidecar && c.sidecar.values;
  if (!v || typeof v.source !== 'string') return ['the sidecar records no source path'];
  if (!fs.existsSync(v.source)) problems.push('the sidecar\'s source does not exist: ' + v.source);
  else if (realOr(v.source) !== realOr(c.registry.path)) {
    problems.push('the sidecar names ' + v.source + ' as its source, not the registry the case read (' + c.registry.path + ')');
  }
  const pin = FIXTURES[fixtureName] && FIXTURES[fixtureName].sha256;
  if (pin && fs.existsSync(v.source) && hashFile(v.source) !== pin) {
    problems.push('the sidecar\'s source file is not the pinned ' + fixtureName);
  }
  return problems;
}
// A check case's own record: the frozen checker accepted, in one line, and the
// sidecar it read is the pinned one.
function checkCaseProblems(c, want, fixtureName) {
  const problems = [];
  const line = PASS_LINE(want.n_evals, want.caps);
  if (c.operation !== 'check') problems.push(c.name + ': operation is ' + JSON.stringify(c.operation) + ', not check');
  if (c.outcome !== 'accepted' || c.exit_status !== 0) {
    problems.push(c.name + ': exit=' + JSON.stringify(c.exit_status) + ' outcome=' + JSON.stringify(c.outcome) + ' — the frozen checker did not accept the historical sidecar');
  }
  if (c.stdout !== line + '\n') problems.push(c.name + ': the checker printed ' + JSON.stringify(c.stdout) + ', not the single acceptance line');
  if (c.stderr !== '') problems.push(c.name + ': the checker wrote to stderr');
  if (!deepEq(c.fail_lines, [])) problems.push(c.name + ': the accepted run recorded FAIL lines');
  const iv = c.input_values;
  if (!iv) problems.push(c.name + ': no input_values recorded');
  else {
    const pin = FIXTURES[fixtureName] && FIXTURES[fixtureName].sha256;
    if (iv.sha256 !== pin) problems.push(c.name + ': the sidecar it read hashes to ' + String(iv.sha256).slice(0, 12) + '…, not the pinned ' + fixtureName);
    if (realOr(iv.path) !== realOr(runCopyOf(fixtureName))) problems.push(c.name + ': the sidecar it read is not the run\'s copy of ' + fixtureName);
  }
  return problems;
}
// The frozen checker, re-run by this gate against the run's own artifacts.
function runChecker(regPath, valsPath) {
  const checker = homePath(CHECKER_PATH);
  if (!checker) throw new Error('the frozen checker is not on disk at ' + CHECKER_PATH);
  const r = spawnSync('python3', [checker, regPath, valsPath], { encoding: 'utf8', timeout: 60000 });
  if (r.error) throw new Error('could not start python3: ' + r.error.message);
  return { status: typeof r.status === 'number' ? r.status : null, stdout: r.stdout || '', stderr: r.stderr || '' };
}
// The one pre-measured order-unstable line: the checker's per_capability diff is
// built from a Python set, so with two or more diffed ids the entries may come out
// in either order (measured over 40 subprocesses). Its shape, its id set and each
// pair are asserted; the byte order is not.
function shiftLineProblems(stdout, ids, pairs) {
  const problems = [];
  const text = String(stdout || '');
  if (text.trim().split('\n').length !== 1) {
    return ['the checker printed ' + text.trim().split('\n').length + ' lines, not the one per-capability line'];
  }
  const line = text.replace(/\n$/, '');
  if (!/^FAIL per_capability differs: \{.*\}$/.test(line)) {
    return ['the checker printed ' + JSON.stringify(line) + ', not a single FAIL per_capability differs line'];
  }
  const seen = [...line.matchAll(/'([^']+)': \(/g)].map((m) => m[1]).sort();
  if (!deepEq(seen, ids.slice().sort())) {
    problems.push('the diffed ids are ' + JSON.stringify(seen) + ', not ' + JSON.stringify(ids));
  }
  for (const pair of pairs) if (!line.includes(pair)) problems.push('the line does not carry ' + pair);
  return problems;
}

// ---------- the gates ----------
const checks = {};

checks.historical_74_reproduced = async () => {
  const c = caseOf('historical_74');
  if (!c) return no('the run has no historical_74 case');
  const problems = renderProblems(c, { n_evals: 74, caps: 20 });
  const oracle = {
    'fig-verdicts.png': 'evidence/receipt-figure-render/eval-1/fig-verdicts.png',
    'fig-per-capability.png': 'evidence/receipt-figure-render/eval-1/fig-per-capability.png',
  };
  for (const name of FIGURE_NAMES) {
    const rec = figureOf(c, name);
    if (!rec) continue;
    const pin = ORACLE[oracle[name]];
    if (rec.sha256 !== pin) problems.push(name + ' hashes to ' + rec.sha256.slice(0, 12) + '…, not the committed ' + oracle[name]);
    const committed = homePath(oracle[name]);
    if (!committed) problems.push('the committed ' + oracle[name] + ' is not on disk');
    else if (hashFile(committed) !== pin) problems.push('the committed ' + oracle[name] + ' no longer hashes to its pin');
    if (sha256(producedBytes(c, rec, name)) !== pin) {
      problems.push('the bytes of ' + name + ' under the invocation work dir are not the committed ' + oracle[name]);
    }
  }
  problems.push(...sourceTieProblems(c, 'registry-74.json'));
  return done(problems, 'the registry at 74 evals reproduces the committed eval-1 figures byte for byte from the run\'s own copy, with the renderer\'s single reported line naming its own out dir');
};

checks.reconstructed_75_oracle_match = async () => {
  const c = caseOf('reconstructed_75');
  const c74 = caseOf('historical_74');
  if (!c) return no('the run has no reconstructed_75 case');
  const problems = renderProblems(c, { n_evals: 75, caps: 20 });
  const oracle = {
    'fig-verdicts.png': 'evidence/receipt-figure-render/eval-2/fig-verdicts.png',
    'fig-per-capability.png': 'evidence/receipt-figure-render/eval-2/fig-per-capability.png',
  };
  for (const name of FIGURE_NAMES) {
    const rec = figureOf(c, name);
    if (!rec) continue;
    const pin = ORACLE[oracle[name]];
    if (rec.sha256 !== pin) problems.push(name + ' hashes to ' + rec.sha256.slice(0, 12) + '…, not the committed ' + oracle[name]);
    const committed = homePath(oracle[name]);
    if (!committed) problems.push('the committed ' + oracle[name] + ' is not on disk');
    else if (hashFile(committed) !== pin) problems.push('the committed ' + oracle[name] + ' no longer hashes to its pin');
    if (sha256(producedBytes(c, rec, name)) !== pin) {
      problems.push('the bytes of ' + name + ' under the invocation work dir are not the committed ' + oracle[name]);
    }
  }
  problems.push(...sourceTieProblems(c, 'registry-75-reconstructed.json'));
  // The reconstruction's premise, checked in the run's own bytes: it is the frozen
  // 74 registry with exactly one eval appended to receipt-figure-render, and no
  // other entry moved.
  if (!c74) {
    problems.push('the run has no historical_74 case to compare the reconstruction against');
  } else {
    const a = regOf(c74), b = regOf(c);
    if (!deepEq(a.registry_version, b.registry_version)) {
      problems.push('the reconstruction moved registry_version ' + JSON.stringify(a.registry_version) + ' -> ' + JSON.stringify(b.registry_version));
    }
    const byId = (r) => new Map((r.capabilities || []).map((x) => [x.id, x]));
    const A = byId(a), B = byId(b);
    const moved = [...new Set([...A.keys(), ...B.keys()])].filter((k) => !deepEq(A.get(k), B.get(k)));
    if (!deepEq(moved, ['receipt-figure-render'])) {
      problems.push('the reconstruction changes ' + JSON.stringify(moved) + ', not exactly the capability whose eval it adds');
    } else {
      const pre = A.get('receipt-figure-render').evals || [];
      const post = B.get('receipt-figure-render').evals || [];
      if (post.length !== pre.length + 1) {
        problems.push('receipt-figure-render carries ' + pre.length + ' -> ' + post.length + ' evals, not one more');
      } else {
        if (!deepEq(pre, post.slice(0, pre.length))) problems.push('the reconstruction rewrote the existing evals instead of appending one');
        if (post[post.length - 1].verdict !== 'ship') {
          problems.push('the appended eval\'s verdict is ' + JSON.stringify(post[post.length - 1].verdict) + ', not ship');
        }
      }
    }
    const n74 = (a.capabilities || []).reduce((n, x) => n + (x.evals || []).length, 0);
    const n75 = (b.capabilities || []).reduce((n, x) => n + (x.evals || []).length, 0);
    if (n74 !== 74 || n75 !== 75) problems.push('the two registries carry ' + n74 + ' and ' + n75 + ' evals, not 74 and 75');
  }
  return done(problems, 'the one-eval reconstruction reproduces the committed eval-2 figures byte for byte, and the run\'s two registry copies differ in exactly the appended eval on receipt-figure-render');
};

checks.authored_21_geometry = async () => {
  const c = caseOf('authored_21');
  if (!c) return no('the run has no authored_21 case');
  const problems = renderProblems(c, {
    n_evals: 74, caps: 21, dist: { ship: 65, fix: 9, blocked: 0 },
    keys: CAP_ORDER_74.concat([PROBE_ID]),
  });
  const reg = regOf(c);
  if ((reg.capabilities || []).length !== 21) problems.push('the authored registry carries ' + (reg.capabilities || []).length + ' capabilities, not 21');
  const s1 = sim1(reg), s2 = sim2(reg);
  problems.push(...compareFigure(c, 'fig-verdicts.png', { map: s1.map, height: CFG.FIG1_H }, 'authored_21', PX['fig-verdicts.png@21']));
  problems.push(...compareFigure(c, 'fig-per-capability.png', { map: s2.map, height: s2.height }, 'authored_21', PX['fig-per-capability.png@21']));
  if (s2.height !== FIG2_H[21]) problems.push('the 21-capability figure should be ' + FIG2_H[21] + ' px tall, the model says ' + s2.height);
  const f1 = figureOf(c, 'fig-verdicts.png');
  if (f1 && f1.sha256 !== ORACLE['evidence/receipt-figure-render/eval-1/fig-verdicts.png']) {
    problems.push('figure 1 moved when a capability with no evals was authored in (sha ' + f1.sha256.slice(0, 12) + '…)');
  }
  const v = c.sidecar && c.sidecar.values;
  if (v && v.per_capability) {
    if (!deepEq(v.per_capability[PROBE_ID], { ship: 0, fix: 0, blocked: 0 })) {
      problems.push('the authored capability ' + PROBE_ID + ' reads ' + JSON.stringify(v.per_capability[PROBE_ID]) + ' in the sidecar, not all zeros');
    }
  }
  return done(problems, 'the authored 21-capability registry renders a byte-identical figure 1 and a figure 2 that is exactly the model geometry, one row taller, with the authored capability carrying zero counts');
};

checks.historical_sidecars_accepted = async () => {
  const problems = [];
  const wanted = [
    { name: 'historical_sidecar_74', registry: 'registry-74.json', sidecar: 'values-historical-74.json', n_evals: 74 },
    { name: 'historical_sidecar_75', registry: 'registry-75-reconstructed.json', sidecar: 'values-historical-75.json', n_evals: 75 },
  ];
  for (const w of wanted) {
    const c = caseOf(w.name);
    if (!c) { problems.push('the run has no ' + w.name + ' case'); continue; }
    problems.push(...checkCaseProblems(c, { n_evals: w.n_evals, caps: 20 }, w.sidecar));
    if (c.registry.sha256 !== FIXTURES[w.registry].sha256) problems.push(w.name + ': the registry it read is not the pinned ' + w.registry);
    const hist = JSON.parse(fixtureBytes(w.sidecar).toString('utf8'));
    if (hist.source !== HISTORICAL_SOURCE) problems.push(w.sidecar + ': the historical sidecar no longer carries the source literal it was committed with');
    if (hist.n_evals !== w.n_evals) problems.push(w.sidecar + ': the historical sidecar reports ' + JSON.stringify(hist.n_evals) + ' evals, not ' + w.n_evals);
  }
  if (fixtureBytes('values-historical-74.json').equals(fixtureBytes('values-historical-75.json'))) {
    problems.push('the two historical sidecars are the same bytes — accepting both would be vacuous');
  }
  return done(problems, 'the frozen checker accepts both committed historical sidecars — the 74-eval one against the frozen registry and the 75-eval one against its reconstruction — each in its single acceptance line');
};

checks.fresh_sidecars_accepted = async () => {
  const problems = [];
  const wanted = [
    { name: 'historical_74', n_evals: 74, caps: 20 },
    { name: 'reconstructed_75', n_evals: 75, caps: 20 },
    { name: 'authored_21', n_evals: 74, caps: 21 },
  ];
  let checked = 0;
  for (const w of wanted) {
    const c = caseOf(w.name);
    if (!c) { problems.push('the run has no ' + w.name + ' case'); continue; }
    if (!c.sidecar || typeof c.sidecar.path !== 'string') { problems.push(w.name + ': no fresh sidecar to put back through the checker'); continue; }
    const vals = under(invWork, c.sidecar.path);
    const r = runChecker(c.registry.path, vals);
    checked += 1;
    const line = PASS_LINE(w.n_evals, w.caps);
    if (r.status !== 0) {
      const why = (r.stdout.trim().split('\n')[0] || r.stderr.trim().split('\n').slice(-1)[0] || 'no output');
      problems.push(w.name + ': the frozen checker exited ' + r.status + ' on the run\'s own fresh sidecar (' + why + ')');
    } else if (r.stdout !== line + '\n') {
      problems.push(w.name + ': the checker\'s acceptance line is ' + JSON.stringify(r.stdout) + ', not ' + JSON.stringify(line + '\n'));
    }
    if (r.stderr !== '') problems.push(w.name + ': the checker wrote to stderr');
  }
  return done(problems, 'the frozen checker re-run by this gate accepts all ' + checked + ' freshly rendered sidecars against the registries the run itself wrote (74/20, 75/20, 74/21)');
};

checks.fresh_sidecar_reproduces_historical = async () => {
  const problems = [];
  for (const t of ROUND_TRIP) {
    const c = caseOf(t.case);
    if (!c || !c.sidecar) { problems.push('the run has no fresh sidecar for ' + t.case); continue; }
    const freshText = producedBytes(c, c.sidecar, SIDECAR_NAME).toString('utf8');
    const histPath = runCopyOf(t.historical);
    if (!histPath || !fs.existsSync(histPath)) { problems.push('the run has no copy of ' + t.historical); continue; }
    const histText = fs.readFileSync(histPath, 'utf8');
    if (sha256(Buffer.from(histText, 'utf8')) !== FIXTURES[t.historical].sha256) {
      problems.push(t.historical + ' in the run work dir is not the pinned historical sidecar');
    }
    let fresh, hist;
    try {
      fresh = JSON.parse(freshText);
      hist = JSON.parse(histText);
    } catch (e) {
      problems.push(t.case + ': a sidecar does not parse: ' + e.message);
      continue;
    }
    if (typeof hist.source !== 'string' || hist.source !== HISTORICAL_SOURCE) {
      problems.push(t.historical + ': the historical source literal is gone');
    }
    if (typeof fresh.source !== 'string') {
      problems.push(t.case + ': the fresh sidecar records no source');
    } else {
      if (realOr(fresh.source) !== realOr(c.registry.path)) {
        problems.push(t.case + ': the fresh sidecar names ' + fresh.source + ', not the registry the case read');
      }
      if (hashFile(fresh.source) !== FIXTURES[t.registry].sha256) {
        problems.push(t.case + ': the fresh sidecar\'s source file is not the pinned ' + t.registry);
      }
    }
    if (typeof fresh.source === 'string') {
      const a = stripSource(freshText, fresh.source);
      const b = stripSource(histText, HISTORICAL_SOURCE);
      if (a === null || b === null) {
        problems.push(t.case + ': the source literal does not occur exactly once in one of the two documents');
      } else if (a !== b) {
        problems.push(t.case + ': the fresh sidecar is not the historical sidecar modulo the source field');
      }
    }
    if (freshText === histText) problems.push(t.case + ': the fresh sidecar is byte-identical to the historical one, so the source tie is vacuous');
    for (const k of ['n_capabilities', 'n_evals', 'verdict_distribution', 'per_capability']) {
      if (!deepEq(fresh[k], hist[k])) problems.push(t.case + ': the fresh sidecar\'s ' + k + ' differs from the historical one');
    }
    if (hist.n_evals !== t.n_evals) problems.push(t.historical + ': the historical sidecar reports ' + JSON.stringify(hist.n_evals) + ' evals, not ' + t.n_evals);
  }
  if (!(ROUND_TRIP.length === 2)) problems.push('this gate expects both round trips');
  return done(problems, 'both fresh sidecars are byte-identical to the committed historical sidecars modulo exactly the source field, whose value realpaths to the run\'s own registry copy under the pinned hash');
};

checks.tampered_sidecar_bites = async () => {
  const c = caseOf('attack_tampered');
  if (!c) return no('the run has no attack_tampered case');
  const problems = [];
  const v = JSON.parse(fixtureBytes('values-tampered.json').toString('utf8'));
  const reg = regOf(c);
  const p = predictChecker(reg, v);
  if (c.operation !== 'check') problems.push('operation is ' + JSON.stringify(c.operation) + ', not check');
  if (c.outcome !== 'caught' || c.exit_status !== 3) problems.push('the exchange exited ' + JSON.stringify(c.exit_status) + '/' + JSON.stringify(c.outcome) + ', not 3/caught');
  if (c.stdout !== TAMPER_LINE + '\n') {
    problems.push('the checker printed ' + JSON.stringify(c.stdout) + ', not the single aggregate-mismatch line ' + JSON.stringify(TAMPER_LINE + '\n'));
  }
  if (c.stderr !== '') problems.push('the checker wrote to stderr');
  if (!deepEq(c.fail_lines, [TAMPER_LINE.slice(5)])) problems.push('fail_lines is ' + JSON.stringify(c.fail_lines));
  if (p.fail.length !== 1 || p.fail[0] !== TAMPER_LINE.slice(5)) {
    problems.push('the package\'s own model of the frozen checker predicts ' + JSON.stringify(p.fail) + ', not exactly that one line');
  }
  if (Object.keys(p.diffed).length !== 0) problems.push('the tampered sidecar also disagrees per-capability, so the aggregate leg is not isolated');
  const moved = Object.keys(p.dist).filter((k) => (v.verdict_distribution || {})[k] !== p.dist[k]);
  if (!deepEq(moved, ['ship'])) problems.push('the tampered fixture moves ' + JSON.stringify(moved) + ', not exactly the ship count');
  if (v.verdict_distribution.ship === p.dist.ship) problems.push('the tampered fixture carries the true ship count — nothing was attacked');
  return done(problems, 'the tampered sidecar is caught by exactly the aggregate leg the model predicts, in one printed line, with the per-capability record left untouched');
};

checks.stale_sidecar_reported = async () => {
  const c = caseOf('stale_sidecar');
  if (!c) return no('the run has no stale_sidecar case');
  const problems = [];
  const v = JSON.parse(fixtureBytes('values-historical-75.json').toString('utf8'));
  const reg = regOf(c);
  const p = predictChecker(reg, v);
  if (c.operation !== 'check') problems.push('operation is ' + JSON.stringify(c.operation) + ', not check');
  if (c.outcome !== 'caught' || c.exit_status !== 3) problems.push('the exchange exited ' + JSON.stringify(c.exit_status) + '/' + JSON.stringify(c.outcome) + ', not 3/caught');
  const want = STALE_LINES.join('\n') + '\n';
  if (c.stdout !== want) {
    problems.push('the checker printed ' + JSON.stringify(String(c.stdout)) + ', not the three ordered lines ' + JSON.stringify(want));
  }
  if (c.stderr !== '') problems.push('the checker wrote to stderr');
  if (!deepEq(c.fail_lines, STALE_LINES.map((l) => l.slice(5)))) problems.push('fail_lines is ' + JSON.stringify(c.fail_lines));
  if (!deepEq(p.fail, STALE_LINES.map((l) => l.slice(5)))) {
    problems.push('the package\'s own model predicts ' + JSON.stringify(p.fail) + ', not the three lines the frozen checker printed');
  }
  if (p.nEvals !== 74 || p.nCaps !== 20) problems.push('the stale exchange recomputes ' + p.nEvals + ' evals over ' + p.nCaps + ' capabilities, not 74 over 20');
  if (v.n_evals !== 75) problems.push('the stale fixture is not the 75-eval sidecar');
  if (c.registry.sha256 !== FIXTURES['registry-74.json'].sha256) problems.push('the stale exchange did not check against the frozen 74 registry');
  return done(problems, 'the stale 75-eval sidecar is reported in exactly the three ordered lines the model predicts, against the frozen 74 registry the case read');
};
checks.capability_shift_bites = async () => {
  const c = caseOf('attack_capability_shifted');
  if (!c) return no('the run has no attack_capability_shifted case');
  const problems = [];
  const v = JSON.parse(fixtureBytes('values-cap-shifted.json').toString('utf8'));
  const reg = regOf(c);
  const p = predictChecker(reg, v);
  if (c.operation !== 'check') problems.push('operation is ' + JSON.stringify(c.operation) + ', not check');
  if (c.outcome !== 'caught' || c.exit_status !== 3) problems.push('the exchange exited ' + JSON.stringify(c.exit_status) + '/' + JSON.stringify(c.outcome) + ', not 3/caught');
  if (c.stderr !== '') problems.push('the checker wrote to stderr');
  problems.push(...shiftLineProblems(c.stdout, Object.keys(p.diffed), []));
  if (p.fail.length !== 1) {
    problems.push('the model predicts ' + p.fail.length + ' failing legs, not exactly the per-capability one');
  } else if (!p.fail[0].startsWith('per_capability differs: ')) {
    problems.push('the model\'s single failing leg is ' + JSON.stringify(p.fail[0].slice(0, 60)));
  }
  // The attack premise: the aggregate is untouched, so only the per-capability
  // leg can move.
  if (!deepEq(p.dist, v.verdict_distribution)) {
    problems.push('the shifted fixture also moved the aggregate distribution, so the per-capability leg is not isolated');
  }
  if (p.nEvals !== 74 || p.nCaps !== 20) problems.push('the exchange recomputes ' + p.nEvals + ' evals over ' + p.nCaps + ' capabilities, not 74 over 20');
  // Each predicted pair, and the two independent measured literals, must be in
  // the line the frozen checker actually printed — id set and pairs, not order.
  const printed = c.stdout || '';
  for (const id of Object.keys(p.diffed)) {
    const pair = pyRepr(p.diffed[id]);
    const m = new RegExp("'" + escapeRe(id) + "': (\\([^)]*\\))").exec(printed);
    if (!m) problems.push('the printed line carries no pair for ' + id);
    else if (m[1] !== pair) problems.push('the printed pair for ' + id + ' is ' + m[1] + ', not the model\'s ' + pair);
  }
  for (const pair of SHIFT_PAIRS) if (!printed.includes(pair)) problems.push('the printed line does not carry the measured pair ' + pair);
  return done(problems, 'the capability-shifted sidecar is caught by the per-capability leg alone — same aggregate, exactly the two moved capabilities reported, in the frozen checker\'s one line');
};

checks.degenerate_inputs_reported = async () => {
  const problems = [];
  const e = caseOf('degenerate_empty');
  const m = caseOf('degenerate_malformed');
  if (!e) problems.push('the run has no degenerate_empty case');
  if (!m) problems.push('the run has no degenerate_malformed case');
  if (e) {
    if (e.operation !== 'render') problems.push('degenerate_empty: operation is ' + JSON.stringify(e.operation) + ', not render');
    if (e.outcome !== 'errored' || e.exit_status !== 1) {
      problems.push('degenerate_empty: exit=' + JSON.stringify(e.exit_status) + ' outcome=' + JSON.stringify(e.outcome) + ', not the renderer\'s uncaught-exception exit 1');
    }
    if (e.signal) problems.push('degenerate_empty: the render was signalled (' + e.signal + ')');
    if (e.stdout !== '') problems.push('degenerate_empty: the renderer wrote to stdout before failing');
    for (const needle of ['ValueError', 'max() iterable argument is empty']) {
      if (!String(e.stderr || '').includes(needle)) problems.push('degenerate_empty: stderr does not carry ' + JSON.stringify(needle));
    }
    const f1 = figureOf(e, 'fig-verdicts.png');
    if (!f1) problems.push('degenerate_empty: the figure written before the exception was not recorded');
    else {
      const sim = sim1(regOf(e));
      problems.push(...compareFigure(e, 'fig-verdicts.png', { map: sim.map, height: CFG.FIG1_H }, 'degenerate_empty', PX['fig-verdicts.png@empty']));
    }
    if (figureOf(e, 'fig-per-capability.png')) problems.push('degenerate_empty: the second figure exists although the renderer died computing it');
    if (e.sidecar) problems.push('degenerate_empty: a sidecar was recorded although the renderer died before writing one');
    if (!deepEq(e.out_files, ['fig-verdicts.png'])) problems.push('degenerate_empty: the out dir holds ' + JSON.stringify(e.out_files) + ', not just the one figure that landed');
    if (!e.registry.parsed || e.registry.n_capabilities !== 0 || e.registry.n_evals !== 0) {
      problems.push('degenerate_empty: the registry was recorded as parsed=' + e.registry.parsed + ' caps=' + JSON.stringify(e.registry.n_capabilities) + ' evals=' + JSON.stringify(e.registry.n_evals) + ' — it is a valid registry with no capabilities');
    }
  }
  if (m) {
    if (m.operation !== 'render') problems.push('degenerate_malformed: operation is ' + JSON.stringify(m.operation) + ', not render');
    if (m.outcome !== 'errored' || m.exit_status !== 1) {
      problems.push('degenerate_malformed: exit=' + JSON.stringify(m.exit_status) + ' outcome=' + JSON.stringify(m.outcome) + ', not exit 1');
    }
    if (m.signal) problems.push('degenerate_malformed: the render was signalled (' + m.signal + ')');
    if (m.stdout !== '') problems.push('degenerate_malformed: the renderer wrote to stdout before failing');
    if (!String(m.stderr || '').includes('JSONDecodeError')) problems.push('degenerate_malformed: stderr does not carry the JSON decode error the renderer raised');
    if ((m.figures || []).length !== 0) problems.push('degenerate_malformed: figures were recorded for a registry that does not parse');
    if (m.sidecar) problems.push('degenerate_malformed: a sidecar was recorded for a registry that does not parse');
    if (!deepEq(m.out_files, [])) problems.push('degenerate_malformed: the out dir holds ' + JSON.stringify(m.out_files) + ', not nothing');
    if (m.registry.parsed !== false) problems.push('degenerate_malformed: the registry was recorded as parsed=' + m.registry.parsed + ' although its JSON is truncated');
  }
  if (e && m && e.registry.sha256 === m.registry.sha256) problems.push('the two degenerate registries are the same bytes');
  return done(problems, 'both degenerate registries are reported honestly: the valid-but-empty one as a partial render (figure 1 on disk, no sidecar, the interpreter\'s own ValueError) and the truncated one as nothing written at all');
};

checks.geometry_tracks_frozen_registry = async () => {
  const problems = [];
  const wanted = [
    { name: 'historical_74', fig1: PX['fig-verdicts.png@74'], fig2: PX['fig-per-capability.png@74'], h2: FIG2_H[74] },
    { name: 'reconstructed_75', fig1: PX['fig-verdicts.png@75'], fig2: PX['fig-per-capability.png@75'], h2: FIG2_H[75] },
    { name: 'authored_21', fig1: PX['fig-verdicts.png@21'], fig2: PX['fig-per-capability.png@21'], h2: FIG2_H[21] },
  ];
  const counted = [];
  for (const w of wanted) {
    const c = caseOf(w.name);
    if (!c) { problems.push('the run has no ' + w.name + ' case'); continue; }
    const reg = regOf(c);
    const s1 = sim1(reg), s2 = sim2(reg);
    problems.push(...compareFigure(c, 'fig-verdicts.png', { map: s1.map, height: CFG.FIG1_H }, w.name, w.fig1));
    problems.push(...compareFigure(c, 'fig-per-capability.png', { map: s2.map, height: s2.height }, w.name, w.fig2));
    if (s2.height !== w.h2) problems.push(w.name + ': the model\'s figure-2 height is ' + s2.height + ', not the measured ' + w.h2);
    // The x geometry is a function of the per-capability counts, so a figure
    // whose bars were placed from other numbers cannot match both the map and
    // the count.
    const v = c.sidecar && c.sidecar.values;
    if (v && v.per_capability) {
      const rows = Object.entries(v.per_capability);
      const model = perCapOf(reg);
      if (rows.length !== model.length) problems.push(w.name + ': the sidecar carries ' + rows.length + ' rows, the registry ' + model.length);
      const wantOrder = model.map((r) => r.id);
      const gotOrder = rows.map(([id]) => id);
      if (!deepEq(gotOrder, wantOrder)) problems.push(w.name + ': the sidecar order is ' + JSON.stringify(gotOrder) + ', not the renderer\'s paint order ' + JSON.stringify(wantOrder));
      const byId = new Map(model.map((r) => [r.id, r.counts]));
      const bad = rows.filter(([id, ct]) => !byId.has(id) || !deepEq(byId.get(id), ct));
      if (bad.length) problems.push(w.name + ': ' + bad.length + ' sidecar rows do not carry the registry\'s own counts');
    } else {
      problems.push(w.name + ': no sidecar to tie the drawn bars to the counts');
    }
    counted.push(w.name);
  }
  return done(problems, 'all ' + counted.length + ' rendered states have figure geometry equal to the model built from the registry each case itself read, with the drawn bar lengths tied to the recorded counts');
};

checks.cap_count_does_not_move_geometry = async () => {
  const c74 = caseOf('historical_74'), c21 = caseOf('authored_21'), c75 = caseOf('reconstructed_75');
  if (!c74 || !c21 || !c75) return no('the run is missing one of historical_74 / authored_21 / reconstructed_75');
  const problems = [];
  const bytes = (c, name) => {
    const rec = figureOf(c, name);
    return rec ? producedBytes(c, rec, name) : null;
  };
  const a = bytes(c74, 'fig-verdicts.png'), b = bytes(c21, 'fig-verdicts.png');
  if (!a || !b) problems.push('a figure-1 copy is missing');
  else {
    if (!a.equals(b)) problems.push('figure 1 moved when a capability with no evals was authored in (same distribution, one more capability)');
    const c1 = sha256(a), c2 = sha256(b);
    if (c1 !== ORACLE['evidence/receipt-figure-render/eval-1/fig-verdicts.png'] || c2 !== c1) {
      problems.push('figure 1 at 20 and 21 capabilities is not the committed eval-1 figure');
    }
  }
  const d = bytes(c75, 'fig-verdicts.png');
  if (!d) problems.push('the reconstructed state produced no figure 1');
  else if (a && d.equals(a)) problems.push('figure 1 did not move when the distribution changed (the 75th eval added a ship)');
  const p74 = bytes(c74, 'fig-per-capability.png'), p21 = bytes(c21, 'fig-per-capability.png');
  if (!p74 || !p21) problems.push('a figure-2 copy is missing');
  else {
    const h74 = decodePng(p74).height, h21 = decodePng(p21).height;
    const grew = h21 - h74;
    if (grew !== CFG.BAR_H + CFG.GAP) problems.push('figure 2 grew by ' + grew + ' px for one added row, not ' + (CFG.BAR_H + CFG.GAP));
    if (h74 !== FIG2_H[74] || h21 !== FIG2_H[21]) problems.push('figure-2 heights are ' + h74 + '/' + h21 + ', not the measured ' + FIG2_H[74] + '/' + FIG2_H[21]);
    const diff = mapDiff(palettePixels(decodePng(p21)), palettePixels(decodePng(p74)), 'figure 2 at 21 vs 20 capabilities');
    if (diff) problems.push('an empty added row moved drawn geometry: ' + diff);
  }
  return done(problems, 'adding a capability with no evals changes neither figure 1\'s bytes nor any drawn pixel of figure 2 — it adds exactly one ' + (CFG.BAR_H + CFG.GAP) + '-px row — while the 75th eval does move figure 1');
};

checks.frozen_source_pinned = async () => {
  const problems = [];
  const renderer = homePath(RENDERER_PATH), checker = homePath(CHECKER_PATH);
  if (!renderer) problems.push('the frozen renderer is not on disk at ' + RENDERER_PATH);
  else if (hashFile(renderer) !== RENDERER_SHA) problems.push('the renderer on disk does not hash to the revision the run executed');
  if (!checker) problems.push('the frozen checker is not on disk at ' + CHECKER_PATH);
  else if (hashFile(checker) !== CHECKER_SHA) problems.push('the checker on disk does not hash to the revision the run executed');
  const f = O.frozen || {};
  // The observation records the frozen scripts by HOME-RELATIVE path (the same
  // spelling as the capability's own record), so judge them as files resolved
  // against RCOS_HOME — never as strings against the gate's own cwd.
  const frozenOnDisk = (rel) => {
    if (!home || typeof rel !== 'string' || rel === '') return null;
    return path.isAbsolute(rel) ? rel : path.join(home, rel.replace(/^[/\\]+/, ''));
  };
  const pair = (label, rec, pin, rel) => {
    if (!rec || typeof rec !== 'object') { problems.push('the observation records no ' + label); return; }
    if (rec.sha256 !== pin) problems.push('the ' + label + ' the run recorded is not the pinned revision');
    const onDisk = frozenOnDisk(rel);
    const recorded = typeof rec.path === 'string' ? frozenOnDisk(rec.path) : null;
    if (!onDisk || !fs.existsSync(onDisk)) { problems.push('the frozen ' + label + ' is not on disk at ' + rel); return; }
    if (!recorded || realOr(recorded) !== realOr(onDisk)) problems.push('the ' + label + ' path recorded (' + rec.path + ') is not ' + rel);
  };
  pair('renderer', f.renderer, RENDERER_SHA, RENDERER_PATH);
  pair('checker', f.checker, CHECKER_SHA, CHECKER_PATH);
  if (f.renderer && f.renderer.usage !== 'receipt_figures.py <registry.json> <out-dir>') problems.push('the recorded renderer usage is ' + JSON.stringify(f.renderer.usage));
  if (f.checker && f.checker.usage !== 'check_figures.py <registry.json> <values.json>') problems.push('the recorded checker usage is ' + JSON.stringify(f.checker.usage));
  if (f.checker && !deepEq(f.checker.documented_exit_codes, [0, 3])) problems.push('the recorded checker exit codes are ' + JSON.stringify(f.checker.documented_exit_codes) + ', not [0, 3]');
  if (f.renderer && !(f.renderer.documented_exit_codes === null || deepEq(f.renderer.documented_exit_codes, []))) problems.push('the renderer is recorded with exit codes it does not document');
  // The adapter writes evidence/frozen.sha256 into the INVOCATION's evidence dir
  // ($RCOS_EVIDENCE_DIR), not into the runner's run dir — judge it where the run
  // actually wrote it.
  const frozenDirs = [];
  if (invocationDir) frozenDirs.push(path.join(invocationDir, 'evidence', 'frozen.sha256'));
  if (runDir && path.join(runDir, 'evidence', 'frozen.sha256') !== (frozenDirs[0] || '')) frozenDirs.push(path.join(runDir, 'evidence', 'frozen.sha256'));
  if (frozenDirs.length) {
    const frozenFile = frozenDirs.find((p) => fs.existsSync(p));
    if (!frozenFile) problems.push('the run recorded no evidence/frozen.sha256 (looked in ' + frozenDirs.join(' and ') + ')');
    else {
      const lines = fs.readFileSync(frozenFile, 'utf8').split('\n').filter((l) => l !== '');
      if (lines.length !== 2) problems.push('frozen.sha256 carries ' + lines.length + ' lines, not the two frozen scripts');
      const want = [[RENDERER_SHA, renderer], [CHECKER_SHA, checker]];
      for (let i = 0; i < Math.min(lines.length, 2); i++) {
        const m = /^([0-9a-f]{64}) {2}(.*)$/.exec(lines[i]);
        if (!m) { problems.push('frozen.sha256 line ' + (i + 1) + ' is not a sha256sum line'); continue; }
        if (m[1] !== want[i][0]) problems.push('frozen.sha256 line ' + (i + 1) + ' carries sha ' + m[1].slice(0, 12) + '…, not the pinned revision');
        if (!want[i][1] || realOr(m[2]) !== realOr(want[i][1])) problems.push('frozen.sha256 line ' + (i + 1) + ' names ' + m[2] + ', not the frozen script');
      }
    }
  }
  // Every executed case must have run the pinned scripts: the recorded argv[0]
  // resolves to the frozen file for its operation, and argv[1] to the registry
  // whose bytes the case records.
  let executed = 0;
  for (const c of (Array.isArray(O.cases) ? O.cases : [])) {
    const want = c.operation === 'render' ? renderer : checker;
    if (!Array.isArray(c.argv) || c.argv.length < 3) { problems.push(c.name + ': argv is ' + JSON.stringify(c.argv)); continue; }
    if (!want || realOr(c.argv[0]) !== realOr(want)) problems.push(c.name + ': the ' + c.operation + ' ran ' + c.argv[0] + ', not the frozen script');
    if (!c.registry || realOr(c.argv[1]) !== realOr(c.registry.path)) problems.push(c.name + ': the argv registry is not the one the case recorded');
    executed += 1;
  }
  if (executed !== 10) problems.push('the run executed ' + executed + ' cases, not the 10 the package declares');
  return done(problems, 'both frozen scripts are the pinned revisions on disk, the run wrote their identity into evidence/frozen.sha256, and all ' + executed + ' executed cases ran those exact files');
};

checks.artifact_identity_pinned = async () => {
  const problems = [];
  if (!runDir) return no('the run dir is not visible to this gate');
  const inputPath = path.join(runDir, 'input.json');
  if (!fs.existsSync(inputPath)) return no('the run has no input.json');
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const evalDir = process.env.RCOS_EVAL_DIR;
  if (!evalDir) problems.push('RCOS_EVAL_DIR is not set — the package this run belongs to cannot be identified');
  if (input.eval_id !== 'receipt-figure-render-figures-v1') problems.push('the run is an execution of ' + JSON.stringify(input.eval_id) + ', not this package');
  if (input.capability_id !== 'receipt-figure-render') problems.push('the run executed ' + JSON.stringify(input.capability_id));
  if (evalDir) {
    const spec = path.join(evalDir, 'eval.json');
    if (!fs.existsSync(spec)) problems.push('the package\'s eval.json is not on disk at ' + spec);
    else if (hashFile(spec) !== input.eval_sha256) problems.push('the package on disk is not the revision this run executed');
  }
  // Every declared fixture: the same bytes in the eval package, in the run's work
  // dir, in the run's evidence copy, and under the sha input.json recorded.
  const recorded = new Map();
  for (const x of (Array.isArray(input.fixtures) ? input.fixtures : [])) {
    if (typeof x === 'string') recorded.set(x, null);
    else if (x && typeof x.name === 'string') recorded.set(x.name, x);
  }
  const names = Object.keys(FIXTURES);
  if (recorded.size !== names.length) problems.push('input.json records ' + recorded.size + ' fixtures, not the ' + names.length + ' the package pins');
  for (const name of names) {
    const pin = FIXTURES[name];
    if (!recorded.has(name)) { problems.push('input.json does not record fixture ' + name); continue; }
    const rec = recorded.get(name);
    if (rec && (rec.sha256 !== pin.sha256 || rec.bytes !== pin.bytes)) {
      problems.push('input.json records ' + name + ' as ' + String(rec.sha256).slice(0, 12) + '…/' + rec.bytes + ', not the pinned ' + pin.sha256.slice(0, 12) + '…/' + pin.bytes);
    }
    const copies = [];
    const w = runCopyOf(name); if (w) copies.push(['the run work dir', w, fs.existsSync(w)]);
    const e = path.join(runDir, 'evidence', 'inputs', name); copies.push(['the run evidence copy', e, fs.existsSync(e)]);
    const p = evalDir ? path.join(evalDir, 'fixtures', name) : null; if (p) copies.push(['the package', p, fs.existsSync(p)]);
    for (const [label, file, exists] of copies) {
      if (!exists) { problems.push(label + ' has no copy of ' + name); continue; }
      const buf = fs.readFileSync(file);
      if (buf.length !== pin.bytes) problems.push(label + '\'s copy of ' + name + ' is ' + buf.length + ' bytes, not ' + pin.bytes);
      if (sha256(buf) !== pin.sha256) problems.push(label + '\'s copy of ' + name + ' is not the pinned bytes');
    }
  }
  // The run's own request, pinned by hash, and the case list it carries.
  const ci = input.capability_input;
  if (!ci || typeof ci.path !== 'string' || typeof ci.sha256 !== 'string') problems.push('input.json records no capability input');
  else {
    const ciPath = path.isAbsolute(ci.path) ? ci.path : path.join(runDir, ci.path);
    if (!fs.existsSync(ciPath)) problems.push('the run\'s capability input is gone: ' + ciPath);
    else if (hashFile(ciPath) !== ci.sha256) problems.push('the run\'s capability input is not the bytes the run consumed');
    else {
      const req = JSON.parse(fs.readFileSync(ciPath, 'utf8'));
      const cases = Array.isArray(req.cases) ? req.cases : [];
      const got = cases.map((x) => (x && x.name) || (typeof x === 'string' ? x : '?'));
      const want = Array.isArray(O.cases) ? O.cases.map((x) => x.name) : [];
      if (!deepEq(got, want)) problems.push('the request names ' + JSON.stringify(got) + ', the observation ' + JSON.stringify(want));
      if (got.length !== 10) problems.push('the run requested ' + got.length + ' cases, not the 10 the package declares');
      for (const x of cases) {
        if (!x || typeof x.registry !== 'string') { problems.push('a requested case names no registry'); continue; }
        const base = path.basename(x.registry);
        if (!FIXTURES[base]) { problems.push('a requested case reads ' + x.registry + ', which is not a pinned fixture'); continue; }
        const w = runCopyOf(base);
        if (!w || realOr(x.registry) !== realOr(w)) problems.push('a requested case reads ' + x.registry + ', not the run\'s own copy of ' + base);
      }
    }
  }
  // The observation's cases are the pinned set, once each, in the declared order.
  if (!Array.isArray(O.cases) || O.cases.length !== 10) problems.push('the observation carries ' + (Array.isArray(O.cases) ? O.cases.length : 0) + ' cases, not 10');
  else {
    const seen = O.cases.map((c) => c.name);
    if (new Set(seen).size !== seen.length) problems.push('the observation names the same case twice');
  }
  return done(problems, 'the run is an execution of this exact package revision, all ' + names.length + ' pinned fixtures agree byte for byte across the package, the run\'s work dir and the run\'s evidence copy, and the run\'s request is pinned by hash with every case reading the run\'s own fixture copy');
};

// ---------- dispatcher ----------
if (!checks[id]) {
  console.error('blocked: unknown gate id ' + JSON.stringify(id));
  process.exit(4);
}
if (EVIDENCE.length > 0) {
  console.log('FAIL ' + id + ': the observation contradicts its own evidence: ' + EVIDENCE.join(' | '));
  process.exit(3);
}
Promise.resolve()
  .then(() => checks[id]())
  .then((res) => {
    console.log((res.ok ? 'PASS ' : 'FAIL ') + id + ': ' + res.detail);
    process.exit(res.ok ? 0 : 3);
  })
  .catch((e) => {
    console.error('blocked: gate ' + id + ' could not complete: ' + e.message);
    process.exit(4);
  });

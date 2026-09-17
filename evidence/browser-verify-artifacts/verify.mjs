#!/usr/bin/env node
// browser-verify-artifacts canonical verifier.
// Contract: http(s) URLs only (file:// refused), page must render with ZERO
// console errors, optional font assertions, rendered PNG proof archived.
// Exit codes: 0 verify-pass, 2 usage/scheme-refused, 3 console error /
// assertion failure (the no-op trap killer), 4 network/load failure.
import { chromium } from '/Users/adam26/.nvm/versions/node/v24.15.0/lib/node_modules/playwright/index.mjs';

const [url, outPng, fontSpec, paintJS] = process.argv.slice(2);
if (!url || !outPng) { console.error('usage: verify.mjs <http-url> <proof.png> [font-spec]'); process.exit(2); }
const u = new URL(url);
if (u.protocol !== 'http:' && u.protocol !== 'https:') { console.log(`SCHEME_REFUSED ${u.protocol}`); process.exit(2); }

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
const allowed = [];
await page.route('**/favicon.ico', r => { allowed.push(r.request().url()); return r.abort(); });
page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`); });
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
try { await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 }); }
catch (e) { console.log(`LOAD_FAIL ${e.message.split('\n')[0]}`); await browser.close(); process.exit(4); }
await page.waitForTimeout(400);
if (fontSpec) {
  for (const f of fontSpec.split(',')) await page.evaluate(async s => { await document.fonts.load(s); }, f);
  await page.evaluate(() => document.fonts.ready);
  for (const f of fontSpec.split(',')) {
    const ok = await page.evaluate(s => document.fonts.check(s), f);
    if (!ok) { console.log(`FONT_CHECK=false ${f}`); await browser.close(); process.exit(3); }
  }
}
if (paintJS) await page.evaluate(paintJS);
const canvasScan = await page.evaluate(() => {
  const cs = [...document.querySelectorAll('canvas')];
  if (!cs.length) return { na: true };
  for (const c of cs) {
    const ctx = c.getContext('2d'); if (!ctx) continue;
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let sum = 0, sum2 = 0, n = 0;
    for (let i = 0; i < d.length; i += 4 * 97) {
      const g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      sum += g; sum2 += g * g; n++;
    }
    const mean = sum / n, sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
    if (sd > 4) return { na: false, blank: false, sd };
  }
  return { na: false, blank: true };
});
if (canvasScan && !canvasScan.na && canvasScan.blank) {
  console.log('BLANK_SCREEN canvas-std~0 (deterministic green is not enough — nothing visible painted)');
  await page.screenshot({ path: outPng, fullPage: false });
  await browser.close(); process.exit(3);
}
await page.screenshot({ path: outPng, fullPage: false });
if (canvasScan && !canvasScan.na) console.log(`CANVAS_SD ${canvasScan.sd.toFixed(1)}`);
await browser.close();
if (errors.length) { console.log(`CONSOLE_ERRORS ${errors.length}`); errors.slice(0, 5).forEach(e => console.log('  ' + e.slice(0, 160))); process.exit(3); }
if (allowed.length) console.log(`FAVICON_ALLOWANCE ${allowed.length} (browser-initiated, not an artifact defect)`);
console.log(`VERIFY_PASS ${outPng}`);

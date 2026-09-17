#!/usr/bin/env node
// face-in-scene-shot eval-2 capture: deterministic PNG-sequence path
// (__setTime drives renderAt; screenshots replace the raw-post sink).
import { chromium } from '/Users/adam26/.nvm/versions/node/v24.15.0/lib/node_modules/playwright/index.mjs';
const N = 48, FPS = 24;
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://127.0.0.1:8743/scene_v2.html', { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForFunction('window.__ready === true', { timeout: 30000 });
for (let n = 0; n < N; n++) {
  await page.evaluate(t => window.__setTime(t), n / FPS);
  await page.screenshot({ path: `frames/f${String(n).padStart(4, '0')}.png` });
}
await browser.close();
if (errors.length) { console.log(`CONSOLE_ERRORS ${errors.length}`); errors.slice(0, 3).forEach(e => console.log(' ' + e.slice(0, 140))); process.exit(3); }
console.log(`CAPTURE_OK ${N} frames`);

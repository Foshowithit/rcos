#!/usr/bin/env node
// hunyuan eval-2 sighted-gate capture: screenshot the textured GLB viewer
import { chromium } from '/Users/adam26/.nvm/versions/node/v24.15.0/lib/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
const errors = [];
page.on('response', r => { if (r.status() >= 400 && !r.url().includes('favicon')) errors.push('HTTP' + r.status() + ' ' + r.url()); });
page.on('console', m => { if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto('http://127.0.0.1:8751/viewer.html', { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForFunction('window.__ready === true', { timeout: 60000 });
const err = await page.evaluate('window.__error || null');
if (err) { console.log('GLB_LOAD_ERROR ' + err.slice(0, 200)); process.exit(3); }
await page.screenshot({ path: 'tex-render.png' });
if (errors.length) { console.log(`CONSOLE_ERRORS ${errors.length}`); errors.slice(0, 3).forEach(e => console.log(' ' + e.slice(0, 140))); process.exit(3); }
await page.screenshot({ path: 'tex-render.png' });
await browser.close();
console.log('CAPTURE_OK tex-render.png');

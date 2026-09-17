import { chromium } from '/Users/adam26/.nvm/versions/node/v24.15.0/lib/node_modules/playwright/index.mjs';
import { mkdirSync } from 'fs';
const FRAMES = 240; // 4s @ 60fps
mkdirSync('frames', { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 960, height: 540 } });
await page.goto('file://' + process.cwd() + '/scene.html');
await page.evaluate(() => window.__cineFrame(0));            // warmup
const w = await page.evaluate(async () => {
  await document.fonts.load('400 48px Caveat');
  await document.fonts.load('700 48px Caveat');
  await document.fonts.ready;
  return { c400: document.fonts.check('400 48px Caveat'), c700: document.fonts.check('700 48px Caveat') };
});
console.log(`warmup=__cineFrame(0) fonts.load(400)=${w.c400} fonts.load(700)=${w.c700} fonts.ready=true`);
if (!w.c400 || !w.c700) { console.log('FONT_CHECK=false'); process.exit(1); }
console.log('FONT_CHECK=true');
for (let n = 0; n < FRAMES; n++) {
  await page.evaluate((n) => window.__cineFrame(n), n);
  await page.screenshot({ path: `frames/f${String(n).padStart(4, '0')}.png` });
}
console.log(`CAPTURED=${FRAMES}`);
await browser.close();

// /home/z/my-project/scripts/brag_capture.js
// Captures frames at 30fps for each scene HTML, writing sequentially-numbered PNGs
// into <brag-output>/work/frames/f0000.png .. f0539.png
//
// Each scene HTML is a pure function of time via the --t CSS custom property.
// We set documentElement.style.--t = "<seconds>s" before each screenshot.

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const OUT = process.env.BRAG_OUT;
if (!OUT) throw new Error('Set BRAG_OUT env var to the brag-output directory');

const SCENES = [
  // file, duration in seconds (must match brag-plan.md)
  { file: 'scene1.html', duration: 2.5 },  //   0 ..  74  (75 frames)
  { file: 'scene2.html', duration: 3.0 },  //  75 .. 164  (90 frames)
  { file: 'scene3.html', duration: 3.5 },  // 165 .. 269 (105 frames)
  { file: 'scene4.html', duration: 3.0 },  // 270 .. 359  (90 frames)
  { file: 'scene5.html', duration: 3.0 },  // 360 .. 449  (90 frames)
  { file: 'scene6.html', duration: 3.0 },  // 450 .. 539  (90 frames)
];
const FPS = 30;

const FRAMES_DIR = path.join(OUT, 'work/frames');
fs.mkdirSync(FRAMES_DIR, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-web-security'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1080, height: 1080 },
    deviceScaleFactor: 1,
  });

  let globalFrame = 0;
  for (const s of SCENES) {
    const page = await ctx.newPage();
    const url = 'file://' + path.join(OUT, 'work/scenes', s.file);
    await page.goto(url, { waitUntil: 'networkidle' });
    // Make sure fonts are loaded (web + local)
    await page.evaluate(() => document.fonts.ready);
    // Tiny extra settle for first frame
    await page.waitForTimeout(100);

    const N = Math.round(FPS * s.duration);
    for (let f = 0; f < N; f++) {
      const t = f / FPS;
      await page.evaluate((tt) => {
        document.documentElement.style.setProperty('--t', tt.toFixed(6) + 's');
      }, t);
      const outPath = path.join(FRAMES_DIR, `f${String(globalFrame).padStart(4, '0')}.png`);
      await page.screenshot({
        path: outPath,
        type: 'png',
        clip: { x: 0, y: 0, width: 1080, height: 1080 },
      });
      globalFrame++;
    }
    await page.close();
    console.log(`${s.file}: captured ${N} frames (cumulative ${globalFrame})`);
  }
  await browser.close();
  console.log(`Done. Total frames: ${globalFrame} (expected 540 for 18s @ 30fps)`);
})();

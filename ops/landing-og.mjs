// Renders landing/assets/og.png (1200×630), the link preview of the landing page.
// Run from the repository root: node ops/landing-og.mjs (needs the repo's Playwright and its Chromium).
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const asset = (name, type) => `data:${type};base64,${readFileSync(path.join(root, "landing/assets", name)).toString("base64")}`;

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "Rethink Sans"; src: url(${asset("rethink-sans.woff2", "font/woff2")}) format("woff2"); font-weight: 400 800; }
* { box-sizing: border-box; margin: 0; }
body { position: relative; width: 1200px; height: 630px; overflow: hidden; background: #f5f6f1; color: #182820;
  font-family: "Rethink Sans", sans-serif; -webkit-font-smoothing: antialiased; }
.brand { position: absolute; left: 64px; top: 58px; display: flex; align-items: center; gap: 12px; font-size: 28px; font-weight: 740; letter-spacing: -.04em; }
.brand img { width: 44px; height: 44px; }
.badge { padding: 3px 8px 4px; border-radius: 6px; background: #def1b7; color: #2c4a31; font-size: 14px; font-weight: 720; letter-spacing: .03em; text-transform: uppercase; }
h1 { position: absolute; left: 64px; top: 178px; font-size: 64px; font-weight: 650; line-height: .98; letter-spacing: -.04em; }
p { position: absolute; left: 64px; top: 330px; width: 440px; color: #4d5c52; font-size: 23px; line-height: 1.38; }
.stage { position: absolute; left: 600px; top: 96px; width: 660px; height: 600px; padding: 34px; border-radius: 18px;
  background-color: #def1b7; background-image: radial-gradient(circle, #547b4d52 .9px, transparent 1.2px), linear-gradient(150deg, #eaf6d3, #d9edaf 60%, #cce4b5);
  background-size: 18px 18px, auto; }
.stage img { width: 760px; border-radius: 12px; box-shadow: 0 3px 8px #192a1a26, 0 24px 45px -22px #283f256b; }
</style></head><body>
<div class="brand"><img src="${asset("deai-icon.png", "image/png")}" alt=""><span>Deai Canvas</span><span class="badge">Beta</span></div>
<h1>Design with AI.<br>Keep control.</h1>
<p>A local workspace for reviewing what your AI agent designs: live screens, pinned feedback, iterations.</p>
<div class="stage"><img src="${asset("northline-review.webp", "image/webp")}" alt=""></div>
</body></html>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(root, "landing/assets/og.png") });
  console.log("landing/assets/og.png");
} finally {
  await browser.close();
}

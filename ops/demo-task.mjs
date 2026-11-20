#!/usr/bin/env node
/**
 * Rebuilds the demo task template (0.33.0): `app/templates/demo/` (pages, `pages.json`, `flow.json`) and
 * `app/templates/demo-pins.json` — two pins with anchor fingerprints computed in Chromium by the same
 * `CommentLayerAnchor.fingerprint` the commenter uses (`app/vendor/anchor.min.js`). For developers, not for the runtime:
 * `POST /api/demo-task` only copies these files. Needs Playwright's Chromium (`npx playwright install chromium`).
 *
 *   node ops/demo-task.mjs
 *
 * Files are overwritten, never deleted: a page that left `demo-pages.mjs` stays on disk until removed by hand, and
 * `tests/demo-task.test.mjs` (directory listing == `demoFiles()`) says so.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { DEMO_PINS } from "./readme-shots/demo-pages.mjs";
import { DEMO_VERSION, demoFiles } from "./demo-task/build.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "app", "templates", "demo");
const PINS_OUT = path.join(ROOT, "app", "templates", "demo-pins.json");
const ANCHOR = readFileSync(path.join(ROOT, "app", "vendor", "anchor.min.js"), "utf8");

const files = demoFiles();
for (const [rel, text] of Object.entries(files)) {
  mkdirSync(path.dirname(path.join(OUT, rel)), { recursive: true });
  writeFileSync(path.join(OUT, rel), text);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const pins = [];
  for (const p of DEMO_PINS) {
    await page.setContent(files[`${p.page}/index.html`]);
    await page.addScriptTag({ content: ANCHOR });
    const fp = await page.evaluate((s) => {
      const el = document.querySelector(s);
      return el ? window.CommentLayerAnchor.fingerprint(el, document.body) : null;
    }, p.sel);
    if (!fp) throw new Error(`no pin target ${p.page} ${p.sel}`);
    pins.push({ ...p, fp });
  }
  writeFileSync(PINS_OUT, `${JSON.stringify({ version: DEMO_VERSION, pins }, null, 1)}\n`);
} finally {
  await browser.close();
}
console.log(`demo template: ${Object.keys(files).length} files, ${DEMO_PINS.length} pins`);

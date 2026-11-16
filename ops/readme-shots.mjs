#!/usr/bin/env node
/**
 * Regenerates the README screenshots (docs/screenshots/*.png) from a throw-away canvas on demo data.
 *
 *   node ops/readme-shots.mjs            # all shots
 *   node ops/readme-shots.mjs hero tasks # only these
 *
 * What it does: makes a temporary HOME with one space and a few fictional tasks (a made-up budgeting app,
 * see ops/readme-shots/demo-pages.mjs), starts its own `app/serve.py` on a free port >= 31000, drives
 * Chromium (Playwright) at 1440x900 with the UI language set to English, writes the PNGs, shrinks them
 * and stops the server by its PID. It reads and writes nothing outside the temp dir and docs/screenshots:
 * no DEAI_HOME, no DC_TASKS_FILE, no network, no real tasks, no real ~/.deai.
 *
 * TODO(0.29.0): add the element-inspector shot (the inspector panel is being redesigned in 0.29.0, so it
 * is left out on purpose) — open a mockup, press the inspector button, hover a card, save as `inspector.png`.
 */
import "../tests/live/_env.mjs";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { freePort } from "../tests/live/_port.mjs";
import { flowJson, pages, pagesJson } from "./readme-shots/demo-pages.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "docs", "screenshots");
const VIEW = { width: 1440, height: 900 };
const MAX_BYTES = 400 * 1024;
const ANCHOR = readFileSync(path.join(ROOT, "app", "vendor", "anchor.min.js"), "utf8");
const only = new Set(process.argv.slice(2));
const want = (name) => only.size === 0 || only.has(name);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------- demo machine: temp HOME, one space, four fictional tasks ---------- */

/* `only`: the pages of a side task (so each card on the Tasks screen shows a different frame); the main task has all. */
const TASKS = {
  "tally-app": { title: "Tally: budgeting app", tags: ["mobile", "core"] },
  "tally-onboarding": { title: "Tally: onboarding", tags: ["onboarding"], only: ["dashboard-empty", "budgets"] },
  "tally-settings": { title: "Tally: settings redesign", tags: ["settings"], only: ["profile", "notifications"] },
  "tally-landing": { title: "Tally: monthly report", tags: ["reports"], only: ["transactions", "budgets"] },
};

function writeIteration(dir, it, v, note, date, only) {
  const itDir = path.join(dir, "iterations", it);
  const html = pages(v);
  const ids = only || Object.keys(html);
  for (const id of ids) {
    mkdirSync(path.join(itDir, id), { recursive: true });
    writeFileSync(path.join(itDir, id, "index.html"), html[id]);
  }
  const tree = only ? { pages: only.map((id) => ({ id, name: id, kind: "page", published: true })) } : pagesJson();
  writeFileSync(path.join(itDir, "pages.json"), JSON.stringify(tree));
  return { id: it, date, note, published: true };
}

function buildMachine() {
  const home = realpathSync(mkdtempSync(path.join(tmpdir(), "readme-shots-home-")));
  const space = path.join(home, "work", "studio");
  mkdirSync(space, { recursive: true });
  const rows = {};
  for (const [id, meta] of Object.entries(TASKS)) {
    const dir = path.join(space, id);
    const its = [writeIteration(dir, "it1", 1, "First pass: home, list, budgets", "09.11.2026 10:00", meta.only)];
    if (id === "tally-app") its.push(writeIteration(dir, "it2", 2, "Savings goal card, clearer main action", "12.11.2026 15:30"));
    writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: its }));
    rows[id] = { dir, title: meta.title, tags: meta.tags };
  }
  const main = rows["tally-app"].dir;
  writeFileSync(path.join(main, "iterations", "it2", "flow.json"), JSON.stringify(flowJson()));
  writeFileSync(path.join(main, "iterations", "it1", "flow.json"), JSON.stringify(flowJson()));
  writeFileSync(path.join(space, "space.json"), JSON.stringify({ name: "Studio", color: "space-1", modules: { "static-publish": { enabled: true } } }));
  writeFileSync(path.join(space, "tasks.json"), JSON.stringify({ current: "tally-app", design_work_root: space, tasks: rows }));
  const deai = path.join(home, ".deai");
  mkdirSync(deai, { recursive: true, mode: 0o700 });
  writeFileSync(path.join(deai, "spaces.json"), JSON.stringify({ version: 1, current: "studio", spaces: [{ id: "studio", path: space, legacy: false }] }));
  return { home, main };
}

async function startServer(home) {
  const port = await freePort(31000);
  const child = spawn("python3", [path.join(ROOT, "app", "serve.py")], {
    cwd: ROOT,
    env: {
      ...process.env, HOME: home, PORT: String(port), DC_NO_OVERVIEW: "1",
      SUPABASE_URL: "", SUPABASE_KEY: "", JIRA_EMAIL: "", JIRA_TOKEN: "",
      DEAI_NO_UPDATE_CHECK: "1", DEAI_FEEDBACK_URL: "", DEAI_FEEDBACK_KEY: "",
      DC_MIRRORS_DIR: path.join(home, ".mirrors"), GIT_SSH_COMMAND: "false", GIT_TERMINAL_PROMPT: "0",
    },
    stdio: "ignore",
  });
  const url = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    try { if ((await fetch(`${url}/api/spaces`)).ok) return { child, url }; } catch { /* not up yet */ }
    await sleep(250);
  }
  child.kill();
  throw new Error("server did not start");
}

const post = (url, route, body) => fetch(`${url}${route}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
}).then((r) => r.json().catch(() => ({})));

/* ---------- seeding: pins, agent status ---------- */

const PINS = [
  { page: "dashboard", sel: "#cta-add", text: "Make this the only filled button on the screen. Secondary actions should be outlined.", who: "Designer", status: "open" },
  { page: "dashboard", sel: "#spent .d", text: "Red looks like an error here. Use the neutral text colour for the percentage.", who: "Designer", status: "open" },
  { page: "dashboard", sel: "#by-category h2", text: "Rename to “Where it went” and sort the bars by amount.", who: "Designer", status: "open" },
  { page: "dashboard", sel: "#balance .v", text: "Show cents in a lighter weight.", who: "Designer", status: "resolved", reason: "Cents are now 60% opacity, weight 500." },
];

async function seedPins(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  const comments = [];
  let seq = 0;
  for (const pid of [...new Set(PINS.map((p) => p.page))]) {
    await page.goto(`${url}/commented?it=it2&page=${pid}&bare=1`);
    await page.addScriptTag({ content: ANCHOR });
    for (const p of PINS.filter((x) => x.page === pid)) {
      const fp = await page.evaluate((s) => {
        const el = document.querySelector(s);
        return el ? window.CommentLayerAnchor.fingerprint(el, document.body) : null;
      }, p.sel);
      if (!fp) throw new Error(`no pin target ${pid} ${p.sel}`);
      seq += 1;
      comments.push({
        id: `demo-${seq}`, author: p.who, text: p.text, status: p.status, fp, htmlSnapshot: null, bornV: 1, ts: "12.11.2026 16:10",
        ...(p.status === "resolved" ? { resolvedV: 2, resolveReason: p.reason } : {}),
        meta: { url: `${url}/commented?it=it2&page=${pid}&ch=local`, route: "/commented", version: `2/${pid}`, iteration: "2",
                viewport: { w: 1440, h: 900 }, seq, sel: p.sel },
      });
    }
  }
  await page.close();
  const r = await post(url, "/api/local-comments", { comments });
  if (!r.ok) throw new Error("pin seeding failed");
}

const beat = (url, phase, status, note) => post(url, "/api/claude-status", { task: "tally-app", phase, status, note, session: "demo" });

/* ---------- shots ---------- */

async function newPage(browser, url) {
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem("dc-lang", "en"); } catch { /* ignore */ } });
  const page = await ctx.newPage();
  await page.goto(`${url}/app/`);
  return { ctx, page };
}

async function save(page, name) {
  mkdirSync(OUT, { recursive: true });
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file });
  shrink(file);
  console.log(`${name}.png  ${(statSync(file).size / 1024).toFixed(0)} KB`);
}

/** Keep each PNG under MAX_BYTES: re-encode with sips, then scale down in steps if still too big. */
function shrink(file) {
  let width = VIEW.width;
  for (let i = 0; i < 4 && statSync(file).size > MAX_BYTES; i += 1) {
    width = Math.round(width * 0.9);
    spawnSync("sips", ["--resampleWidth", String(width), file], { stdio: "ignore" });
  }
  if (statSync(file).size > MAX_BYTES) throw new Error(`${file} is still over ${MAX_BYTES} bytes`);
}

/** Switch the current task and take the frames of one iteration (synchronous: the route answers when the run ends). */
async function shootTask(url, id, it) {
  await post(url, "/api/task-switch", { id });
  const r = await post(url, "/api/shoot", { it, all: true });
  if (!r.ok && !r.report) throw new Error(`shooting ${id}/${it}: ${JSON.stringify(r).slice(0, 200)}`);
}

/** Visit Overview once and come back: the Pages panel then says "Frames · 7 fresh" instead of "freshness not checked yet". */
async function warmFrames(page) {
  await page.locator('[data-act="mode"][data-val="overview"]').click();
  await page.waitForSelector("#world .cv-card img", { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.locator('[data-act="mode"][data-val="layout"]').click();
  await page.waitForSelector('#hud [data-act="comments"]');
}

const SCENES = {
  async hero(browser, url) {
    const { ctx, page } = await newPage(browser, url);
    await page.waitForSelector('#hud [data-act="comments"]');
    await warmFrames(page);
    await page.click('#pages-panel [data-act="toggle"][data-val="dashboard"]');
    await page.click('#pages-panel [data-act="toggle"][data-val="settings-folder"]');
    await page.waitForTimeout(1500);
    await save(page, "hero");
    await ctx.close();
  },
  async comments(browser, url) {
    const { ctx, page } = await newPage(browser, url);
    await warmFrames(page);
    await page.click('#hud [data-act="comments"]');
    await page.waitForSelector("#cmt-panel .cmt-card");
    await page.click('#cmt-panel .cmt-fold[data-val="closed"]');     // show what the agent wrote when it closed a pin
    await page.waitForTimeout(1200);
    await save(page, "comments");
    await ctx.close();
  },
  async overview(browser, url) {
    const { ctx, page } = await newPage(browser, url);
    await page.locator('[data-act="mode"][data-val="overview"]').click();
    await page.waitForSelector("#world .cv-card img", { timeout: 30000 });
    await page.waitForTimeout(1500);
    await page.mouse.move(690, 150);
    await page.keyboard.down("Control");
    for (let i = 0; i < 4; i += 1) { await page.mouse.wheel(0, -120); await page.waitForTimeout(120); }
    await page.keyboard.up("Control");
    await page.waitForTimeout(800);
    await page.mouse.wheel(240, 0);                 // pan the grid left a little
    await page.waitForTimeout(1200);
    await save(page, "overview");
    await ctx.close();
  },
  async flow(browser, url) {
    const { ctx, page } = await newPage(browser, url);
    await page.locator('[data-act="mode"][data-val="overview"]').click();
    await page.waitForSelector("#world .cv-card img", { timeout: 30000 });
    await page.getByRole("button", { name: /Flow/ }).first().click();
    await page.waitForTimeout(2500);
    await save(page, "flow");
    await ctx.close();
  },
  async tasks(browser, url) {
    const { ctx, page } = await newPage(browser, url);
    await page.waitForSelector('#tabs [data-act="home"]');
    await page.click('#tabs [data-act="home"]');
    await page.waitForSelector("#bar .space-chip");
    await page.waitForTimeout(2000);
    await save(page, "tasks");
    await ctx.close();
  },
  async preview(browser, url) {
    const res = await post(url, "/api/publish", {});
    if (!res.ok) throw new Error(`publish failed: ${JSON.stringify(res).slice(0, 200)}`);
    const ctx = await browser.newContext({ viewport: VIEW });
    await ctx.addInitScript(() => { try { localStorage.setItem("dc-lang", "en"); } catch { /* ignore */ } });
    const page = await ctx.newPage();
    await page.goto(`${url}/published/studio/tally-app/`);
    await page.locator("#bar .bar").waitFor({ timeout: 20000 });
    await page.frameLocator("#frame").locator("h1").waitFor({ timeout: 20000 });
    await page.waitForTimeout(2500);
    await save(page, "preview");
    await ctx.close();
  },
};
const ORDER = ["hero", "comments", "overview", "flow", "tasks", "preview"];

async function main() {
  const { home } = buildMachine();
  const { child, url } = await startServer(home);
  console.log(`server pid ${child.pid} on ${url}`);
  const browser = await chromium.launch();
  try {
    for (const id of Object.keys(TASKS)) await shootTask(url, id, id === "tally-app" ? "it2" : "it1");
    await post(url, "/api/task-switch", { id: "tally-app" });
    await seedPins(browser, url);
    await beat(url, "design", "in_progress", "Applying the pin feedback to Home");
    for (const name of ORDER) {
      if (!want(name)) continue;
      await beat(url, "design", "in_progress", "Applying the pin feedback to Home");   // keeps the status island fresh (TTL)
      await SCENES[name](browser, url);
    }
  } finally {
    await browser.close();
    child.kill();                                   // by PID: the process we started, nothing else
    /* The temp HOME is ours (made by mkdtemp above); the name check keeps this from ever touching anything else. */
    if (path.dirname(home) === realpathSync(tmpdir()) && path.basename(home).startsWith("readme-shots-home-")) {
      rmSync(home, { recursive: true, force: true });
    }
  }
}

if (import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  main().then(() => process.exit(0), (e) => { console.error(e); process.exit(1); });
}

export { buildMachine, startServer, seedPins, beat, newPage, save, post };

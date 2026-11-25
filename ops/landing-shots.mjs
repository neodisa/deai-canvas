#!/usr/bin/env node
/** Capture the real Canvas UI with two fictional projects in a disposable local space. */
import "../tests/live/_env.mjs";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { freePort } from "../tests/live/_port.mjs";
import { forma, northline, northlinePins } from "./landing-shots/demos.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const anchor = readFileSync(path.join(root, "app/vendor/anchor.min.js"), "utf8");
const viewport = { width: 1440, height: 860 };
const image = (name) => `data:image/webp;base64,${readFileSync(new URL(`./landing-shots/${name}.webp`, import.meta.url)).toString("base64")}`;
const projects = [northline(image("northline-rail")), forma(image("forma-chair"))];
const spaceId = "studio";

function json(file, data) {
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
}

function setupSpace(demoRoot) {
  const registry = path.join(demoRoot, ".deai");
  const space = path.join(demoRoot, spaceId);
  mkdirSync(registry, { mode: 0o700 });
  mkdirSync(space);
  const tasks = {};

  for (const { id, title, tags, iterations, pages, tree, flow } of projects) {
    const dir = path.join(space, id);
    const history = iterations.map((note, i) => {
      const iteration = `it${i + 1}`;
      const iterationDir = path.join(dir, "iterations", iteration);
      for (const [pageId, html] of Object.entries(pages(i + 1))) {
        const pageDir = path.join(iterationDir, pageId);
        mkdirSync(pageDir, { recursive: true });
        writeFileSync(path.join(pageDir, "index.html"), html);
      }
      json(path.join(iterationDir, "pages.json"), tree);
      if (flow) json(path.join(iterationDir, "flow.json"), flow);
      return { id: iteration, note, date: `${14 + i * 2}.09.2026 15:30`, published: i === iterations.length - 1 };
    });
    json(path.join(dir, "iterations.json"), { iterations: history });
    tasks[id] = { dir, title, tags };
  }
  const tokens = path.join(space, "northline-tokens.css");
  copyFileSync(new URL("./landing-shots/northline.css", import.meta.url), tokens);
  json(path.join(space, "space.json"), {
    name: "Studio", color: "space-1",
    modules: { "static-publish": { enabled: true }, "css-tokens": { enabled: true, settings: { file: tokens } } },
  });
  json(path.join(space, "tasks.json"), { current: "northline", design_work_root: space, tasks });
  json(path.join(registry, "spaces.json"), { version: 1, current: spaceId, spaces: [{ id: spaceId, path: space, legacy: false }] });
  return registry;
}

async function post(base, route, data) {
  const response = await fetch(`${base}${route}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok || value.ok === false) throw new Error(`${route} failed (${response.status}): ${JSON.stringify(value)}`);
  return value;
}

async function waitForServer(url, child) {
  for (let attempt = 0; attempt < 75; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Canvas exited with status ${child.exitCode}`);
    const response = await fetch(url, { signal: AbortSignal.timeout(1200) }).catch(() => null);
    if (response?.ok) return;
    await delay(200);
  }
  throw new Error(`Server did not start at ${url}`);
}

async function stopServer(child) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  const stopped = once(child, "exit");
  child.kill();
  await stopped;
}

async function seedPins(context, base) {
  const page = await context.newPage();
  try {
    const pinPage = `${base}/commented?it=it2&page=search`;
    await page.goto(`${pinPage}&bare=1`);
    await page.addScriptTag({ content: anchor });
    const comments = [];
    for (const [i, pin] of northlinePins.entries()) {
      const fp = await page.locator(pin.selector).evaluate((element) => window.CommentLayerAnchor.fingerprint(element, document.body));
      comments.push({
        id: `northline-pin-${i + 1}`, author: "Maya Chen", text: pin.text,
        status: pin.resolution ? "resolved" : "open", fp, htmlSnapshot: null, bornV: 1, ts: "16.09.2026 16:10",
        ...(pin.resolution && { resolvedV: 2, resolveReason: pin.resolution }),
        meta: { url: `${pinPage}&ch=local`, route: "/commented", version: "2/search", iteration: "2", viewport: { w: viewport.width, h: viewport.height }, seq: i + 1, sel: pin.selector },
      });
    }
    await post(base, "/api/local-comments", { comments });
  } finally {
    await page.close();
  }
}

async function waitForFrame(page, selector) {
  const frame = page.frameLocator("#frame");
  await frame.locator(selector).waitFor();
  await frame.locator("body").evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((image) => image.decode()));
  });
  return frame;
}

async function capture(page, demoRoot, name) {
  await page.mouse.move(5, 5);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const png = path.join(demoRoot, `${name}.png`);
  const webp = path.join(demoRoot, `${name}.webp`);
  await page.screenshot({ path: png, animations: "disabled" });
  execFileSync("cwebp", ["-quiet", "-q", "90", "-sharp_yuv", png, "-o", webp]);
  copyFileSync(webp, path.join(root, "landing/assets", `${name}.webp`));
  console.log(`${name}.webp`);
}

async function studioShots(context, base, demoRoot) {
  const page = await context.newPage();
  try {
    await page.goto(`${base}/app/`);
    await waitForFrame(page, "#journey-form");
    await page.locator('[data-act="mode"][data-val="overview"]').click();
    await page.waitForFunction(() => [...document.querySelectorAll("#world .cv-card img")].some((image) => image.naturalWidth > 0));
    await page.locator('[data-act="mode"][data-val="layout"]').click();
    await page.locator('#pages-panel [data-act="toggle"][data-val="search"]').click();
    await page.locator('#hud [data-act="comments"]').click();
    await page.locator("#cmt-panel .cmt-card").first().waitFor();
    await page.locator('#cmt-panel .cmt-fold[data-val="closed"]').click();
    await page.locator("#cmt-panel").getByText(/Changed the heading/).waitFor();
    await capture(page, demoRoot, "northline-review");

    await page.locator('#hud [data-act="comments"]').click();
    await page.locator('#hud [data-act="inspector"]').click();
    const frame = await waitForFrame(page, "#journey-form");
    await page.waitForFunction(() => document.getElementById("frame")?.contentWindow.CanvasInspector?.on);
    await frame.locator("#journey-form").click({ position: { x: 10, y: 10 } });
    await page.waitForFunction(() => document.getElementById("frame")?.contentWindow.CanvasInspector?.pinned?.id === "journey-form");
    await page.locator("#insp-panel").waitFor();
    await capture(page, demoRoot, "northline-inspector");

    await page.setViewportSize({ width: viewport.width, height: 680 });
    await page.locator('[data-act="settings"]').click();
    await page.locator('.mc[data-id="css-tokens"]').waitFor();
    await capture(page, demoRoot, "studio-modules");
  } finally {
    await page.close();
  }
}

async function publishedShot(context, base, demoRoot) {
  const result = await post(base, "/api/publish", {});
  const port = await freePort(31200);
  const origin = `http://127.0.0.1:${port}`;
  const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", result.local.path], { stdio: "ignore" });
  try {
    await waitForServer(origin, server);
    const page = await context.newPage();
    try {
      await page.route(`${origin}/**`, (route) => route.continue());
      await page.goto(origin);
      await page.locator('#pages-panel [data-act="page"][data-val="it2/fares"]').click();
      await waitForFrame(page, "#fare-heading");
      await capture(page, demoRoot, "northline-preview");
    } finally {
      await page.close();
    }
  } finally {
    await stopServer(server);
  }
}

async function checkoutShots(context, base, demoRoot) {
  await post(base, "/api/task-switch", { id: "forma" });
  await post(base, "/api/shoot", { it: "it1", all: true, vp: 768 });
  await post(base, "/api/shoot", { it: "it1", all: true, vp: 1280 });
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem("dc-canvas-viewport", "768"));
  const framesReady = () => page.waitForFunction(() =>
    [...document.querySelectorAll("#world .cv-card img")].filter((image) => image.complete && image.naturalWidth > 0).length === 5);
  try {
    await page.goto(`${base}/app/`);
    await page.locator('[data-act="mode"][data-val="overview"]').click();
    await framesReady();
    for (const id of ["cart", "order-confirmed"]) {
      await page.locator(`#pages-panel [data-act="toggle"][data-val="${id}"]`).click();
    }
    await capture(page, demoRoot, "forma-overview");

    await page.locator('#bar [data-act="vp"][data-val="desktop"]').click();
    await page.waitForFunction(() => document.querySelector("#world .cv-card")?.style.width === "1280px");
    await page.locator('[data-act="view"][data-val="flow"]').click();
    await page.locator("#world .cv-edge").first().waitFor({ state: "attached" });
    await framesReady();
    await capture(page, demoRoot, "forma-flow");
  } finally {
    await page.close();
  }
}

const demoRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "deai-landing-shots-")));
const log = [];
let child;
let browser;
try {
  const registry = setupSpace(demoRoot);
  const port = await freePort(31100);
  const base = `http://127.0.0.1:${port}`;
  child = spawn("python3", [path.join(root, "app/serve.py")], {
    cwd: root,
    env: {
      ...process.env, PORT: String(port), HOME: demoRoot, DEAI_HOME: registry,
      DC_TASKS_FILE: path.join(demoRoot, "unused-legacy.json"), DC_NO_OVERVIEW: "1",
      DC_MIRRORS_DIR: path.join(demoRoot, "mirrors"), DEAI_NO_UPDATE_CHECK: "1", DEAI_EXTRA_MODULES: "", GIT_TERMINAL_PROMPT: "0",
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  child.stderr.on("data", (chunk) => {
    log.push(chunk.toString());
    if (log.length > 12) log.shift();
  });
  child.on("error", (error) => log.push(error.message));
  await waitForServer(`${base}/api/spaces`, child);
  browser = await chromium.launch();
  const context = await browser.newContext({ viewport, deviceScaleFactor: 2, reducedMotion: "reduce", serviceWorkers: "block" });
  context.setDefaultTimeout(15000);
  await context.route((url) => !["data:", "blob:", "about:"].includes(url.protocol) && url.origin !== base, (route) => route.abort());
  await context.addInitScript(() => localStorage.setItem("dc-lang", "en"));
  mkdirSync(path.join(root, "landing/assets"), { recursive: true });
  await seedPins(context, base);
  await post(base, "/api/shoot", { it: "it2", all: true, vp: 1280 });
  for (const id of ["css-tokens", "static-publish"]) await post(base, "/api/module-check", { space: spaceId, id });
  await post(base, "/api/claude-status", { task: "northline", phase: "design", status: "in_progress", note: "Refining the booking form", session: "demo" });
  await studioShots(context, base, demoRoot);
  await publishedShot(context, base, demoRoot);
  await checkoutShots(context, base, demoRoot);
} catch (error) {
  if (log.length) console.error(log.join(""));
  throw error;
} finally {
  await browser?.close();
  await stopServer(child);
  rmSync(demoRoot, { recursive: true, force: true });
}

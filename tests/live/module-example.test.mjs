/**
 * Приклад-модуль `docs/modules/examples/page-notes/` («Нотатки сторінок») — живе проведення (M1, Task 7): той самий приклад,
 * що його копіюють люди, у тимчасовому просторі (`DEAI_HOME` — теж тимчасовий). Довіра — шов `DEAI_TRUST_CONFIRM`
 * (POST із «позначками браузера», як це робить сторінка канваса), увімкнення — звичайним `/api/module-enable`.
 *
 *   клавіша N → панель із назвою сторінки; нотатка + «Зберегти» → тост; перезавантаження сторінки → нотатка на місці;
 *   інша сторінка → порожньо; ⌘K «Нотатки задачі» → тост «Нотаток: N»; незбережений текст при зміні сторінки не губиться.
 */
import assert from "node:assert/strict";
import { cpSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, stop, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs` стереже, що бази не збігаються). */
const PORT_BASE = 34000;
const EXAMPLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/modules/examples/page-notes");
const MOCKUP = (id) => `<!doctype html><html><head><meta charset="utf-8"><title>Макет ${id}</title></head>`
  + `<body style="margin:0;font-family:sans-serif"><h1 id="t">Макет ${id}</h1><p>текст</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Довіра (як сторінка канваса: `Origin` + `Sec-Fetch-Site: same-origin`; системне вікно — шов) і увімкнення. */
async function trustAndEnable(url) {
  const st = await (await fetch(`${url}/api/module-trust?space=studio&id=page-notes`)).json();
  assert.ok(st.trust?.hash, `стан довіри: ${JSON.stringify(st)}`);
  const tr = await fetch(`${url}/api/module-trust`, { method: "POST",
    headers: { "Content-Type": "application/json", Origin: url, "Sec-Fetch-Site": "same-origin" },
    body: JSON.stringify({ space: "studio", id: "page-notes", hash: st.trust.hash }) });
  assert.equal(tr.status, 200, `довіра: ${await tr.text()}`);
  const en = await (await fetch(`${url}/api/module-enable`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ space: "studio", id: "page-notes", settings: {} }) })).json();
  assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
}

const BTN = '#isl-tools [data-act="modtool"]';
const waitToast = (page, re) => page.waitForFunction((src) => new RegExp(src).test(document.getElementById("cv-toast")?.textContent ?? ""), re.source, { timeout: 15000 });

async function openPage(server, context) {
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.querySelector("[data-comment-layer]"), null, { timeout: 15000 });
  await page.waitForSelector(BTN, { timeout: 15000 });
  return { page, errors };
}

test("приклад «Нотатки сторінок»: панель, збереження, перезавантаження, інша сторінка, дія в ⌘K", async (t) => {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_TRUST_CONFIRM: "yes" },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }] });
  t.after(() => stop(server.child));
  cpSync(EXAMPLE, path.join(server.spaces[0].path, "modules", "page-notes"), { recursive: true });
  await trustAndEnable(server.url);
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));

  let { page, errors } = await openPage(server, context);
  const panel = () => page.frameLocator("#mod-panel iframe");
  const panelOpen = () => page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  const pageBtn = (id) => page.locator(`.row[data-page="${id}"]`);

  // кнопка в острівці з підказкою `N`; клавіша відкриває панель із назвою поточної сторінки
  assert.match(await page.locator(BTN).getAttribute("title"), /^Нотатки \(N\)$/);
  await page.keyboard.press("n");
  await panelOpen();
  await panel().locator("#title").filter({ hasText: "Головна" }).waitFor({ timeout: 15000 });
  const note = panel().locator("#note");
  await panel().locator("#note:not([disabled])").waitFor({ timeout: 15000 });
  assert.equal(await note.inputValue(), "");
  assert.match(await panel().locator("#save").getAttribute("class"), /dk-btn--primary/);

  // нотатка + «Зберегти» → тост
  await note.fill("Моя нотатка до головної");
  await panel().locator("#save").click();
  await waitToast(page, /Збережено/);

  // файл у `cache_dir` модуля (`<DEAI_HOME>/cache/…`): рівно один `notes.json` з нотаткою
  const hits = [];
  const walk = (d) => { for (const n of readdirSync(d)) { const p = path.join(d, n); if (n === "notes.json") hits.push(p); else if (statSync(p).isDirectory()) walk(p); } };
  walk(path.join(server.deaiHome, "cache"));
  assert.equal(hits.length, 1, "notes.json не один");
  assert.match(readFileSync(hits[0], "utf8"), /Моя нотатка до головної/);

  // перезавантаження сторінки канваса → нотатка на місці
  await page.reload();
  await waitBarReady(page, 15000);
  await page.waitForSelector(BTN, { timeout: 15000 });
  await page.click(BTN);
  await panelOpen();
  await panel().locator("#note:not([disabled])").waitFor({ timeout: 15000 });
  assert.equal(await panel().locator("#note").inputValue(), "Моя нотатка до головної", "нотатка не пережила перезавантаження");

  // інша сторінка → порожня нотатка, заголовок оновився; панель лишилась
  await pageBtn("poshuk").click();
  await panel().locator("#title").filter({ hasText: "Пошук" }).waitFor({ timeout: 15000 });
  await panel().locator("#note:not([disabled])").waitFor({ timeout: 15000 });
  assert.equal(await panel().locator("#note").inputValue(), "", "нотатка іншої сторінки не порожня");

  // ⌘K «Нотатки задачі» → тост із кількістю (поки одна)
  await page.keyboard.press("ControlOrMeta+k");
  await page.waitForSelector(".pal");
  await page.fill("#palq", "Нотатки задачі");
  assert.equal(await page.locator(".pal-it", { hasText: "Нотатки задачі" }).count(), 1);
  await page.keyboard.press("Enter");
  await waitToast(page, /Нотаток: 1/);

  // незбережений текст при зміні сторінки зберігається сам: пишемо на «Пошуку», йдемо на «Головну»
  await panel().locator("#note").fill("Нотатка до пошуку");
  await pageBtn("holovna").click();
  await panel().locator("#title").filter({ hasText: "Головна" }).waitFor({ timeout: 15000 });
  await panel().locator("#note:not([disabled])").waitFor({ timeout: 15000 });
  assert.equal(await panel().locator("#note").inputValue(), "Моя нотатка до головної");
  await page.keyboard.press("ControlOrMeta+k");
  await page.waitForSelector(".pal");
  await page.fill("#palq", "Нотатки задачі");
  await page.keyboard.press("Enter");
  await waitToast(page, /Нотаток: 2/);
  assert.deepEqual(errors, []);
});

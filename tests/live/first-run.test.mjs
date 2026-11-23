/**
 * «Перший запуск» (0.33.0) — живе проведення: справжній сервер в ізольованій машині (тимчасові HOME/DEAI_HOME), справжній
 * Chromium. Юніти доводять розмітку й проводку; тут — те, що живе лише з сервером і браузером.
 *
 * Мапа «сценарій → запобіжник» (мутаційно):
 *   1 привітання   — `ensureSetup` + `welcomeHTML(welcomeView())`: абсолютний шлях SETUP.md і адреса; `frCopy` → буфер і тост.
 *   2 ⌘K знайомство — `appActions` (intro) → `openIntro`: Esc і клік по підкладці закривають, фокус у картці; «Відкрити демо» →
 *                     `/api/demo-task` → задача `tally-demo` з двома пінами; удруге — та сама задача (`reuse`).
 *   3 майстер       — крок 4 «Демо-задача (Tally)»: назва й id вимкнені, «Створити й відкрити» відкриває `tally-demo`.
 *   4 «Огляд»       — `DEAI_SHOTS_NODE` → `no-browser`: рядок, команда, «Зняти кадри» вимкнена, `shotscmd` копіює.
 *   5 AGENTS.md     — `missing` → «Підключити» → CLAUDE.md `@AGENTS.md`; `no-import` → «Підключити» → імпорт на початку, решта ціла.
 *   6 пароль        — посилання на картці й пункт меню «Опублікувати» відкривають шухляду з фокусом на полі пароля.
 */
import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PORT_BASE = 29700;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
const toastText = (page) => page.locator("#cv-toast.show").textContent({ timeout: 8000 });
/* Тост, що встиг змінитись: попередній (напр. «Зʼємка: не знято») ще видно, коли клік уже відбувся, — чекаємо потрібний текст. */
const toastMatch = (page, re) => page.waitForFunction(
  (src) => new RegExp(src).test(document.querySelector("#cv-toast.show")?.textContent ?? ""), re.source, { timeout: 8000 });

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });
guardRealDeai();

async function open(t, server) {
  const context = await browser.newContext({ viewport: VIEW });
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  return { page, errors };
}

async function withSpace(t, n, extra = {}) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + n * 10,
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }],
    ...extra,
  });
  t.after(() => stop(server.child));
  return server;
}

const palette = async (page, q) => {
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", q);
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length === 1, null, { timeout: 5000 });
  await page.keyboard.press("Enter");
};

test("1: привітання — промпт з абсолютним шляхом SETUP.md і адресою; «Скопіювати промпт» кладе його в буфер", async (t) => {
  const server = await startServer(null, { portBase: PORT_BASE, spaces: [] });
  t.after(() => stop(server.child));
  const { page, errors } = await open(t, server);
  await page.waitForSelector("#tasks-home .th-welcome .fr-agent");
  await page.waitForFunction((p) => document.querySelector("#fr-prompt")?.textContent.includes(p), path.join(ROOT, "SETUP.md"),
    { timeout: 15000 });
  const prompt = await page.locator("#fr-prompt").textContent();
  assert.ok(prompt.endsWith(`Канвас уже працює: ${new URL(server.url).origin}`), prompt);
  await page.click('[data-th="frcopy"]');
  assert.match(await toastText(page), /Промпт скопійовано/);
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), prompt);
  assert.equal(await page.locator("#tasks-home .fr-intro .fr-legend li").count(), 7);
  assert.equal(await page.locator('#tasks-home [data-th="spacenew"]').count(), 1);
  assert.deepEqual(errors, []);
});

test("2: ⌘K «Знайомство з канвасом» — Esc і підкладка закривають; «Відкрити демо» відкриває tally-demo з пінами, удруге — ту саму", async (t) => {
  const server = await withSpace(t, 1);
  const { page, errors } = await open(t, server);
  await waitBarReady(page, 15000);
  await palette(page, "Знайомство");
  await page.waitForSelector(".cv-ask .fr-card");
  assert.ok(await page.evaluate(() => !!document.activeElement?.closest(".fr-card")), "фокус у картці");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".fr-card", { state: "detached" });
  await palette(page, "Знайомство");
  await page.waitForSelector(".fr-card");
  await page.mouse.click(5, 5);                                   // підкладка поза карткою
  await page.waitForSelector(".fr-card", { state: "detached" });
  await palette(page, "Знайомство");
  await page.click('.fr-card [data-fr="demo"]');
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="tally-demo"]'), null, { timeout: 20000 });
  const dir = path.join(server.spaces[0].path, "tally-demo");
  const pins = JSON.parse(readFileSync(path.join(dir, ".dc-local-comments.json"), "utf8"));
  assert.deepEqual(pins.map((p) => p.status).sort(), ["open", "resolved"]);
  await palette(page, "Знайомство");
  await page.click('.fr-card [data-fr="demo"]');
  await waitBarReady(page, 15000);
  assert.equal(existsSync(path.join(server.spaces[0].path, "tally-demo-2")), false, "удруге — та сама демо-задача");
  assert.deepEqual(errors, []);
});

test("3: майстер, крок 4 — «Демо-задача (Tally)»: назва й id вимкнені, «Створити й відкрити» відкриває tally-demo", async (t) => {
  const server = await startServer(null, { portBase: PORT_BASE + 20, spaces: [] });
  t.after(() => stop(server.child));
  const { page, errors } = await open(t, server);
  /* Кроки 1–3 — як `firstSpace` + W9 у tests/live/wizard.test.mjs: «Особисте», модулі за замовчуванням, картка static-publish. */
  const step = (n) => page.waitForSelector(`#tasks-home .wz[data-step="${n}"]`, { timeout: 15000 });
  const next = () => page.click('#tasks-home .wz [data-a="ok"]');
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await step(1);
  await next();
  await step(2);
  await next();
  await step(3);
  await page.waitForSelector('#tasks-home .wz-card[data-id="static-publish"]', { timeout: 15000 });
  await next();
  await step(4);
  await page.check('input[name="wz-src"][value="demo"]');
  assert.equal(await page.locator("#tf-title").isDisabled(), true);
  assert.equal(await page.locator("#wz-demo-why").isVisible(), true);
  await next();
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="tally-demo"]'), null, { timeout: 20000 });
  assert.deepEqual(errors, []);
});

test("4: «Огляд» без Chromium — причина, команда з копіюванням, «Зняти кадри» вимкнена", async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), "fake-node-"));
  const node = path.join(dir, "node");
  writeFileSync(node, "#!/bin/sh\nprintf '%s' '{\"v\":\"22.0.0\",\"pw\":true,\"browser\":false}'\n");
  chmodSync(node, 0o755);
  const server = await withSpace(t, 3, { env: { DEAI_SHOTS_NODE: node } });
  const { page, errors } = await open(t, server);
  await waitBarReady(page, 15000);
  await page.locator('[data-act="mode"][data-val="overview"]').click();
  await page.waitForSelector(".shots .shots-s--warn#shots-why", { timeout: 15000 });
  assert.match(await page.locator("#shots-cmd").textContent(), /npx playwright install chromium$/);
  assert.equal(await page.locator('.shots [data-act="shoot"]').isDisabled(), true);
  await page.click('[data-act="shotscmd"]');
  await toastMatch(page, /Команду скопійовано/);
  assert.match(await page.evaluate(() => navigator.clipboard.readText()), /npm install && npx playwright install chromium$/);
  assert.deepEqual(errors, []);
});

test("5: AGENTS.md — «Підключити» для missing і no-import; власний текст CLAUDE.md лишається байт у байт", async (t) => {
  const server = await withSpace(t, 4);
  const claude = path.join(server.spaces[0].path, "CLAUDE.md");
  const { page, errors } = await open(t, server);
  await waitBarReady(page, 15000);
  await page.click('[data-act="settings"]');
  await page.waitForSelector(".set-nav", { timeout: 15000 });
  await page.click('.set-nav [data-v="agents"]');
  await page.waitForSelector('[data-claude="missing"] [data-v="claude"]', { timeout: 15000 });
  await page.click('[data-claude="missing"] [data-v="claude"]');
  await page.waitForSelector('[data-claude="ok"]');
  assert.equal(readFileSync(claude, "utf8"), "@AGENTS.md\n");
  writeFileSync(claude, "# Правила команди\r\nкінець");
  await page.click('.set-nav [data-v="mods"]');
  await page.click('.set-nav [data-v="agents"]');
  await page.waitForSelector('[data-claude="no-import"] [data-v="claude"]', { timeout: 15000 });
  await page.click('[data-claude="no-import"] [data-v="claude"]');
  await page.waitForSelector('[data-claude="ok"]');
  assert.equal(readFileSync(claude, "utf8"), "@AGENTS.md\n\n# Правила команди\r\nкінець");
  assert.match(await page.locator("#fr-run-cmd").textContent(), /^cd .+ && claude$/);
  assert.deepEqual(errors, []);
});

test("6: пароль превʼю — посилання на картці й пункт меню «Опублікувати» відкривають шухляду з фокусом на паролі", async (t) => {
  const server = await withSpace(t, 5);
  const { page, errors } = await open(t, server);
  await waitBarReady(page, 15000);
  const focusIsPassword = () => page.waitForFunction(() => document.activeElement?.dataset?.cnField === "password", null, { timeout: 15000 });
  await page.click('#bar [data-dd="pub"]');
  await page.click('[data-act="modpw"]');
  await focusIsPassword();
  await page.keyboard.press("Escape");                            // закрити шухляду (форма чиста — без питання)
  await page.waitForSelector('.mc[data-id="static-publish"] [data-cn="pw"]', { timeout: 15000 });
  await page.click('.mc[data-id="static-publish"] [data-cn="pw"]');
  await focusIsPassword();
  assert.match(await page.locator(".cn-drawer").textContent(), /Один для всіх задач простору\./);
  assert.deepEqual(errors, []);
});

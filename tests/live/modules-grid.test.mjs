/**
 * «Налаштування → Модулі», сітка карток (етап Е, 0.31.0, Task 2) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium. Юніти (`tests/modules-grid.test.mjs`, `tests/connections-view.test.mjs`)
 * доводять модель і розмітку; тут те, що живе лише в браузері: клавіатура меню «⋯» й картки, фокус питання «Вимкнути?», запит,
 * що летить (або НЕ летить), і діалог довіри з картки свого модуля. Модуль-фікстура `memo-publish` (`tests/fixtures/modules-conn`,
 * через шов `DEAI_EXTRA_MODULES`) — роль `publish` з ЛОКАЛЬНОЮ перевіркою: помилку дає `note: "fail"`, без жодної мережі.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно:
 *   1 (картка помилки)       — `cardModel`: помилка → дія `configure` (одна кнопка), клік по картці → шухляда (`connAction('card')`).
 *   2 (клавіатура картки)    — слухач Enter/Пробіл у `keydown` розділу (`app.js`); `role=button tabindex=0` у `mcardHTML`.
 *   3 (меню «⋯»)             — `toggleConnMenu`/`menuKeys`: стрілки по колу, Esc → фокус на «⋯»; `.mc-more` у `moreSel`.
 *   4 (питання «Вимкнути?»)  — `askConnDisable` (фокус на «Скасувати»); Esc → `cancelConnAsk` без запиту; клік повз картку знімає питання.
 *   5 (вимкнення)            — `askyes` → `connDisable` → `POST /api/module-disable`; картка зникає, роль — пунктирна, «Без модуля · N» росте.
 *   6 (свій недовірений)     — кнопка «Довірити» на картці → `connTrust` → діалог довіри; клік по самій картці теж; `Скасувати` лишає недовіреним.
 */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, goTasks, menuDisable, postJson, stop, waitBadge, waitBarReady, waitGone } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 28700;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules-conn");
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Сервер + сторінка. `ownModule` — свій модуль `memo-own` у теці простору (недовірений: код не виконується, сервер лише читає маніфест). */
async function boot(t, { ownModule = false } = {}) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE,
    /* Шов «системного вікна» довіри — лише з тимчасовим `DEAI_HOME`; у цьому файлі довіру не видаємо, діалог лише відкриваємо. */
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, DEAI_TRUST_CONFIRM: "no" },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }],
  });
  t.after(() => stop(server.child));
  if (ownModule) {
    const d = path.join(server.spaces[0].path, "modules", "memo-own");
    mkdirSync(d, { recursive: true });
    writeFileSync(path.join(d, "module.json"), JSON.stringify({ api: 1, id: "memo-own", name: "Memo own (test)",
      version: "1.0.0", roles: ["tokens"], settings: [] }));
    writeFileSync(path.join(d, "server.py"), "def check(ctx):\n    return {\"ok\": True}\n");
  }
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const posts = [];
  context.on("request", (r) => { if (r.method() === "POST") posts.push(new URL(r.url()).pathname); });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  return { ...server, page, errors, posts };
}

async function openModules(page) {
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector(".mc", { timeout: 15000 });
}
const active = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return { cls: a?.className ?? null, id: a?.dataset?.id ?? null, cn: a?.dataset?.cn ?? null, th: !!a?.closest?.("#th-menu") };
});

/** Модуль `memo-publish` з `note: "fail"` → перевірка «ні» → `status: error` (картка помилки). */
const failMemo = (url) => postJson(url, "/api/module-enable", { space: "studio", id: "memo-publish", settings: { note: "fail" }, replace: true });

test("1–2: картка помилки — рівно одна кнопка «Налаштувати» (→ шухляда); клік і Enter/Пробіл по самій картці теж відкривають шухляду", async (t) => {
  const { page, url, errors } = await boot(t);
  const r = await failMemo(url);
  assert.equal(r.status, 200);
  await openModules(page);
  await waitBadge(page, "memo-publish", "error");
  const card = page.locator('.mc[data-id="memo-publish"]');
  assert.equal(await card.locator(".mc-foot button").count(), 1, "одна дія на картці");
  assert.equal((await card.locator(".mc-foot button").textContent()).trim(), "Налаштувати");
  assert.match(await card.locator(".mc-why").textContent(), /memo-says-no|note is fail/, "причина помилки — рядком у картці");
  assert.equal(await card.getAttribute("role"), "button");
  assert.equal(await card.getAttribute("tabindex"), "0");

  await card.locator(".mc-foot button").click();
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  assert.equal(await page.locator("#cn-dr-title").textContent(), "Memo publish (test)");
  await page.click('#cn-drawer [data-cn-dr="close"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });

  await card.locator(".mc-name b").click();                     // клік по самій картці
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.click('#cn-drawer [data-cn-dr="close"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });

  await card.focus();                                           // клавіатура: Enter, потім Пробіл
  await page.keyboard.press("Enter");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.click('#cn-drawer [data-cn-dr="close"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await card.focus();
  await page.keyboard.press("Space");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  assert.deepEqual(errors, []);
});

test("3: меню «⋯» — пункти за станом, стрілки по колу, Esc закриває з фокусом назад на «⋯», «⋯» — тогл", async (t) => {
  const { page, url, errors } = await boot(t);
  await failMemo(url);
  await openModules(page);
  await waitBadge(page, "memo-publish", "error");
  const more = page.locator('.mc-more[data-id="memo-publish"]');
  assert.equal(await more.getAttribute("aria-expanded"), "false");
  assert.equal(await more.getAttribute("aria-label"), "Дії модуля Memo publish (test)");
  await more.click();
  await page.waitForSelector("#th-menu");
  assert.equal(await more.getAttribute("aria-expanded"), "true");
  const items = await page.locator('#th-menu [role="menuitem"]').evaluateAll((els) => els.map((e) => e.dataset.cn));
  assert.deepEqual(items, ["check", "disable"], "помилка: «Налаштувати» — дія картки, у меню Перевірити й Вимкнути");
  assert.equal(await page.locator("#th-menu hr").count(), 1, "розділювач перед «Вимкнути»");
  assert.equal(await page.locator('#th-menu [data-cn="disable"]').getAttribute("class"), "danger");
  assert.equal((await active(page)).cn, "check", "фокус — на першому пункті");
  await page.keyboard.press("ArrowDown");
  assert.equal((await active(page)).cn, "disable");
  await page.keyboard.press("ArrowDown");
  assert.equal((await active(page)).cn, "check", "по колу");
  await page.keyboard.press("ArrowUp");
  assert.equal((await active(page)).cn, "disable", "↑ з першого — на останній");
  await page.keyboard.press("Home");
  assert.equal((await active(page)).cn, "check");
  await page.keyboard.press("End");
  assert.equal((await active(page)).cn, "disable");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#th-menu", { state: "detached" });
  assert.deepEqual(await active(page), { cls: "mc-more", id: "memo-publish", cn: "menu", th: false }, "Esc — фокус назад на «⋯»");
  assert.equal(await more.getAttribute("aria-expanded"), "false");
  await more.click();
  await page.waitForSelector("#th-menu");
  await more.click();                                           // повторний клік закриває
  await page.waitForSelector("#th-menu", { state: "detached" });
  await more.click();
  await page.waitForSelector("#th-menu");
  await page.click("#cn-title");                                // клік повз меню закриває без наслідків
  await page.waitForSelector("#th-menu", { state: "detached" });
  assert.deepEqual(errors, []);
});

test("4–5: «⋯ → Вимкнути» — питання в картці з фокусом на «Скасувати»; Esc без запиту; «Вимкнути» → module-disable, картка зникає, зʼявляється пунктирна роль", async (t) => {
  const { page, url, posts, errors } = await boot(t);
  await failMemo(url);
  await openModules(page);
  await waitBadge(page, "memo-publish", "error");
  assert.equal(await page.locator("h2.sub").textContent(), "Без модуля · 6", "publish — з модулем; решта шість ролей — пунктирні");
  assert.equal(await page.locator('.mc--empty[data-role="publish"]').count(), 0);

  await menuDisable(page, "memo-publish");
  const ask = page.locator('.mc--ask[data-id="memo-publish"]');
  assert.match(await ask.locator(".cfm-t").textContent(), /Вимкнути «Memo publish \(test\)»\? .*Після цього роль «Публікація» лишиться без модуля: кнопки публікації в смузі нема\./);
  assert.deepEqual(await active(page), { cls: "cfm-no", id: "memo-publish", cn: "askno", th: false }, "фокус — на «Скасувати»");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "діалогу нема — питання в картці");
  assert.equal(await ask.locator(".mc-more").count(), 0, "під питанням «⋯» нема");

  await page.keyboard.press("Escape");                          // Esc → без запиту, фокус на «⋯»
  await page.waitForSelector(".mc--ask", { state: "detached" });
  assert.deepEqual(await active(page), { cls: "mc-more", id: "memo-publish", cn: "menu", th: false }, "Esc — фокус на «⋯» картки");
  assert.ok(!posts.includes("/api/module-disable"), "Esc — module-disable не летів");

  await menuDisable(page, "memo-publish");
  await page.click('.mc--ask[data-id="memo-publish"] .cfm-no');   // «Скасувати» — те саме
  await page.waitForSelector(".mc--ask", { state: "detached" });
  assert.deepEqual(await active(page), { cls: "mc-more", id: "memo-publish", cn: "menu", th: false });
  assert.ok(!posts.includes("/api/module-disable"), "«Скасувати» — module-disable не летів");

  await menuDisable(page, "memo-publish");
  await page.click("#cn-title");                                // клік повз картку теж знімає питання
  await page.waitForSelector(".mc--ask", { state: "detached" });
  assert.ok(!posts.includes("/api/module-disable"), "клік повз — module-disable не летів");

  await menuDisable(page, "memo-publish");
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/api/module-disable")),
    page.click('.mc--ask[data-id="memo-publish"] .cfm-yes'),
  ]);
  assert.deepEqual(JSON.parse(req.postData()), { space: "studio", id: "memo-publish" });
  await waitGone(page, "memo-publish");
  await page.waitForSelector('.mc--empty[data-role="publish"]');
  assert.equal(await page.locator("h2.sub").textContent(), "Без модуля · 7", "роль без модуля зʼявилась пунктирною карткою");
  assert.equal(await page.locator('.mc--empty[data-role="publish"] [data-cn="cat"]').textContent(), "Додати");
  assert.equal(posts.filter((p) => p === "/api/module-disable").length, 1, "рівно один запис");
  const mods = (await (await fetch(`${url}/api/modules?space=studio`)).json()).modules;
  assert.equal(mods.find((m) => m.id === "memo-publish").enabled, false, "свідок: сервер справді вимкнув модуль");
  assert.deepEqual(errors, []);
});

test("6: свій недовірений — бейдж «Чекає довіри», кнопка «Довірити» (і клік по картці) відкривають діалог довіри; «Скасувати» лишає недовіреним", async (t) => {
  const { page, errors } = await boot(t, { ownModule: true });
  await openModules(page);
  const card = page.locator('.mc[data-id="memo-own"]');
  await card.waitFor({ timeout: 15000 });
  await waitBadge(page, "memo-own", "untrusted");
  assert.match(await card.locator(".mc-tag").textContent(), /свій/);
  assert.match(await card.locator(".bdg").textContent(), /Чекає довіри/);
  assert.equal(await card.locator(".mc-foot button").count(), 1, "одна дія");
  assert.equal((await card.locator(".mc-foot button").textContent()).trim(), "Довірити");

  await card.locator(".mc-foot button").click();
  await page.waitForSelector("form.tr");
  assert.match(await page.locator("form.tr").textContent(), /Довіритись модулю «Memo own \(test\)»\?/);
  assert.equal(await page.locator('form.tr [data-a="ok"]').textContent(), "Довірити");
  await page.click('form.tr [data-a="cancel"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  assert.equal((await active(page)).cn, "trust", "фокус повернувся на кнопку «Довірити» картки");
  await waitBadge(page, "memo-own", "untrusted");

  await card.locator(".mc-name b").click();                     // клік по картці недовіреного — теж діалог довіри
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="cancel"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.click(`.mc-more[data-id="memo-own"]`);
  const items = await page.locator('#th-menu [role="menuitem"]').evaluateAll((els) => els.map((e) => e.dataset.cn));
  assert.deepEqual(items, ["trust"], "у меню «Код» (діалог довіри); «Вимкнути» нема — модуль не ввімкнений");
  assert.equal((await page.locator('#th-menu [data-cn="trust"]').textContent()).trim(), "Код");
  assert.deepEqual(errors, []);
});

guardRealDeai();

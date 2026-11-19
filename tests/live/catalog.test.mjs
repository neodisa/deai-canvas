/**
 * «Налаштування → Модулі», каталог «Додати модуль» і «Свій модуль» (етап Е, 0.31.0, Task 3) — живе проведення: справжній сервер в
 * ізольованій «машині» (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium. Юніти (`tests/catalog-model.test.mjs`,
 * `tests/catalog-view.test.mjs`) доводять групи, розмітку й текст запиту; тут те, що живе лише в браузері: фокус, Esc, буфер, шухляда.
 * Модулі-фікстури пишуться в тимчасову теку (`DEAI_EXTRA_MODULES`): `memo-publish` (роль `publish`, одне обовʼязкове поле) і
 * `memo-bare` (роль `notify`, БЕЗ налаштувань — вмикається одразу).
 *
 * Мапа «сценарій → запобіжник», знята мутаційно:
 *   1 (з пунктирної картки)  — `data-role` у `emptyCardHTML` → `connCatalog(role)` → `.cat--hl` і `data-autofocus` у `catListHTML`.
 *   2 (вибір → шухляда)      — `form.requestSubmit()` у кліку `[data-cat-pick]`; `connAction('enable', …, 'catalog')`; без закриття діалогу — шухляда під підкладкою.
 *   3 («Замінити X»)         — `replaces` у `catalogGroups`; `catalogHolders` у `openCnDrawer` + `named` у `cnConfirmReplace` (без нього — друге питання).
 *   4 («Свій модуль»)        — `page('own')`, `ownPrompt`, `authoring` із `/api/modules` (`deai.authoring`); буфер — у самому обробнику кліку.
 *   5 (Esc і фокус)          — Esc у `askForm`; `focusBack` / відкривач: голова чи «Додати» картки.
 *   6 (без налаштувань)      — `cnDrawer.fields.length === 0` → `cnSubmit()` в кінці `connCatalog`.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, goTasks, openCatalog, pickFromCatalog, stop, waitBadge, waitBarReady, waitGone } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 28800;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Тека модулів-фікстур у `tmpdir()` (не в репо): `memo-publish` і `memo-bare`. */
function fixtureModules() {
  const dir = mkdtempSync(path.join(tmpdir(), "deai-catalog-mods-"));
  const put = (id, manifest, code) => {
    mkdirSync(path.join(dir, id), { recursive: true });
    writeFileSync(path.join(dir, id, "module.json"), JSON.stringify({ api: 1, id, version: "1.0.0", ...manifest }));
    writeFileSync(path.join(dir, id, "server.py"), code);
  };
  put("memo-publish", { name: "Memo publish (test)", roles: ["publish"], settings: [{ key: "note", type: "text", label: "Note (test)", required: true }] },
    "def check(ctx):\n    return {'ok': True, 'detail': 'memo ok'}\n\n\ndef publish(ctx, built, *a, **k):\n    raise ctx['ModuleError']('module-error', message='memo does not publish')\n");
  put("memo-bare", { name: "Memo bare (test)", roles: ["notify"], settings: [] }, "def check(ctx):\n    return {'ok': True}\n\n\ndef mute_state(ctx, *a, **k):\n    return {}\n\n\ndef mute_set(ctx, *a, **k):\n    return {}\n");
  return dir;
}

async function boot(t) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE,
    env: { DEAI_EXTRA_MODULES: fixtureModules() },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }],
  });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.mc[data-id="static-publish"]', { timeout: 15000 });
  return { ...server, spacePath: server.spaces[0].path, page, errors };
}

const focused = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return { tag: a?.tagName ?? null, cn: a?.dataset?.cn ?? null, role: a?.dataset?.role ?? null, pick: a?.dataset?.catPick ?? null, id: a?.id || null,
    inHead: !!a?.closest?.(".th-head"), inEmpty: a?.closest?.(".mc--empty")?.dataset?.role ?? null };
});

test("1: «Додати» на пунктирній ролі — діалог із підсвіченою групою цієї ролі, фокус на її кнопці", async (t) => {
  const { page, errors } = await boot(t);
  await openCatalog(page, "tokens");
  const dlg = page.locator('.cv-ask form[data-form="catalog"]');
  assert.equal(await dlg.getAttribute("role"), "dialog");
  assert.equal((await dlg.locator("#cat-h").textContent()).trim(), "Додати модуль");
  const hl = dlg.locator(".cat--hl");
  assert.equal(await hl.count(), 1, "підсвічена рівно одна група (в ній один модуль)");
  assert.match(await hl.textContent(), /Токени з CSS/);
  assert.deepEqual(await focused(page), { tag: "BUTTON", cn: null, role: null, pick: "css-tokens", id: null, inHead: false, inEmpty: null });
  assert.equal(await hl.locator("[data-cat-pick]").textContent(), "Підключити");
  assert.match(await dlg.locator(".cat--own").textContent(), /Свій модуль[^]*Як додати/, "останній рядок — пунктирний «Свій модуль»");
  assert.equal(await dlg.locator(".cat--own").evaluate((n) => n.matches(".cat-b > :last-child")), true);
  assert.equal(await dlg.locator('[data-cat-pick="static-publish"]').count(), 0, "увімкнений модуль у каталозі не показується");
  assert.deepEqual(errors, []);
});

test("2: «Підключити» → діалог закрито → шухляда «Підключити» → «Підключити» → картка зʼявилась у сітці", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  writeFileSync(path.join(spacePath, "ds.css"), ":root{--c-a:#123456}");
  await openCatalog(page, "tokens");
  await page.click('.cat--hl [data-cat-pick="css-tokens"]');
  await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  assert.equal(await page.locator("#cn-dr-title").textContent(), "Токени з CSS");
  assert.equal(await page.locator('#cn-drawer [data-cn-dr="submit"]').textContent().then((s) => s.trim()), "Підключити");
  assert.equal(await page.locator('.mc[data-id="css-tokens"]').count(), 0, "поки не підключено — картки нема");
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds.css");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "css-tokens", "ok");
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Токени з CSS");
  assert.equal(await page.locator('.mc--empty[data-role="tokens"]').count(), 0, "роль уже з модулем — пунктирної нема");
  assert.deepEqual(errors, []);
});

test("2b: шухляда з каталогу закрита без запису — фокус вертається на «Додати» тієї пунктирної картки, з якої відкривали", async (t) => {
  const { page, errors } = await boot(t);
  await openCatalog(page, "tokens");
  await page.click('.cat--hl [data-cat-pick="css-tokens"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  await page.click('#cn-drawer [data-cn-dr="close"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  const f = await focused(page);
  assert.deepEqual([f.cn, f.role, f.inEmpty], ["cat", "tokens", "tokens"], "картки css-tokens ще нема — фокус на «Додати» ролі");
  /* З голови сторінки — на «Додати модуль». */
  await pickFromCatalog(page, "git-sync");
  await page.click('#cn-drawer [data-cn-dr="close"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  const g = await focused(page);
  assert.deepEqual([g.cn, g.inHead], ["cat", true]);
  assert.deepEqual(errors, []);
});

test("3: «Замінити {поточний}» на зайнятій ролі — шухляда без додаткового питання, заміна пише replace", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  await openCatalog(page);
  const btn = page.locator('.cat [data-cat-pick="memo-publish"]');
  assert.equal((await btn.textContent()).trim(), "Замінити Публікація в теку");
  assert.equal((await page.locator('.cat [data-cat-pick="vercel-publish"]').textContent()).trim(), "Замінити Публікація в теку");
  assert.equal((await page.locator('.cat [data-cat-pick="git-sync"]').textContent()).trim(), "Підключити", "вільна роль — просто «Підключити»");
  await btn.click();
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "memo-publish", "ok");
  await waitGone(page, "static-publish");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "кнопка вже сказала «Замінити» — вдруге не питаємо");
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Memo publish (test). Вимкнено: Публікація в теку");
  const mods = JSON.parse(readFileSync(path.join(spacePath, "space.json"), "utf8")).modules;
  assert.equal(mods["static-publish"].enabled, false);
  assert.equal(mods["memo-publish"].enabled, true);
  assert.deepEqual(errors, []);
});

test("4: «Свій модуль» → «Як додати» → кроки, живий запит із шляхом до інструкції й текою → «Скопіювати запит» кладе його в буфер й тостить", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  await t_grant(page);
  await openCatalog(page);
  await page.click("[data-cat-own]");
  const dlg = page.locator('.cv-ask form[data-form="catalog"]');
  assert.equal(await dlg.getAttribute("data-page"), "own");
  assert.equal((await dlg.locator("#cat-h").textContent()).trim(), "Свій модуль");
  assert.equal(await dlg.locator("ol.steps li").count(), 3);
  assert.equal(await dlg.locator("[data-cat-back]").isVisible(), true, "«‹» назад видно");
  assert.equal((await focused(page)).id, "own-what", "фокус у полі «Що має робити модуль»");
  const prompt = page.locator("pre.prompt");
  const before = await prompt.textContent();
  assert.ok(before.includes("Studio") && before.includes(spacePath) && before.includes(path.join(ROOT, "docs", "modules", "authoring.md")), before);
  assert.match(before, /Довіряти модулю не намагайся/);
  await page.keyboard.type("звіряти кольори макета з brand.css");
  const live = await prompt.textContent();
  assert.ok(live.includes("звіряти кольори макета з brand.css") && live !== before, "запит оновлюється на кожен символ");
  await page.click("[data-cat-copy]");
  await page.waitForFunction(() => document.getElementById("cv-toast")?.textContent === "Запит скопійовано — вставте його агенту", null, { timeout: 5000 });
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), live, "у буфері — рівно той запит, що на екрані");
  assert.deepEqual(errors, []);
});

/** Права на буфер для читання результату в тесті (запис у справжньому кліку Chromium дозволяє й без них). */
async function t_grant(page) { await page.context().grantPermissions(["clipboard-read", "clipboard-write"]); }

test("4b: буфер відмовив — запит виділяється для ручного копіювання, тоста «скопійовано» нема", async (t) => {
  const { page, errors } = await boot(t);
  await openCatalog(page);
  await page.click("[data-cat-own]");
  await page.evaluate(() => { navigator.clipboard.writeText = () => Promise.reject(new Error("denied")); });
  await page.click("[data-cat-copy]");
  await page.waitForFunction(() => getSelection().toString().includes("authoring.md"), null, { timeout: 5000 });
  assert.equal(await page.evaluate(() => getSelection().toString()), await page.locator("pre.prompt").textContent(), "виділено рівно запит");
  assert.notEqual(await page.locator("#cv-toast").textContent().catch(() => ""), "Запит скопійовано — вставте його агенту");
  assert.deepEqual(errors, []);
});

test("5: фокус — на першому рядку; «‹» вертає на сторінку 1 із фокусом на «Як додати»; Esc на сторінці 2 закриває, фокус — на «Додати модуль»", async (t) => {
  const { page, errors } = await boot(t);
  await openCatalog(page);
  const first = await page.locator("[data-cat-pick]").first().getAttribute("data-cat-pick");
  assert.equal((await focused(page)).pick, first, "фокус на першій кнопці першого рядка, а не на хрестику");
  await page.click("[data-cat-own]");
  await page.click("[data-cat-back]");
  const dlg = page.locator('.cv-ask form[data-form="catalog"]');
  assert.equal(await dlg.getAttribute("data-page"), "list");
  assert.equal((await dlg.locator("#cat-h").textContent()).trim(), "Додати модуль");
  assert.equal(await dlg.locator("[data-cat-back]").isVisible(), false);
  assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute("data-cat-own")), true, "фокус — на «Як додати»");
  await page.click("[data-cat-own]");
  await page.keyboard.press("Escape");
  await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
  const f = await focused(page);
  assert.deepEqual([f.cn, f.inHead], ["cat", true], "фокус — назад на «Додати модуль» у голові");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "Esc нічого не підключив");
  /* «Закрити» другої сторінки теж закриває діалог. */
  await openCatalog(page);
  await page.click("[data-cat-own]");
  await page.click('.cat-f [data-a="cancel"]');
  await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
  assert.deepEqual(errors, []);
});

test("5b: Esc на сторінці 1, відкритій з пунктирної картки, вертає фокус на «Додати» ЦІЄЇ картки; Tab не виходить за діалог", async (t) => {
  const { page, errors } = await boot(t);
  await openCatalog(page, "vcs");
  assert.equal((await focused(page)).pick, "git-sync", "фокус на кнопці підсвіченої групи");
  for (let i = 0; i < 12; i += 1) {
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => !!document.activeElement?.closest?.("form[data-form=catalog]")), true, `Tab ${i}: фокус лишився в діалозі`);
  }
  await page.keyboard.press("Escape");
  await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
  const f = await focused(page);
  assert.deepEqual([f.cn, f.role, f.inEmpty], ["cat", "vcs", "vcs"]);
  assert.deepEqual(errors, []);
});

test("5c: сторінку перемалювали, поки діалог відкритий (кнопка-відкривач — вже відчеплений вузол) — фокус усе одно вертається на свіжу кнопку", async (t) => {
  const { page, errors } = await boot(t);
  for (const role of ["", "vcs"]) {
    await openCatalog(page, role);
    await page.evaluate(() => { for (const n of document.querySelectorAll(".th-head, .mc--empty")) n.outerHTML = n.outerHTML; });
    await page.keyboard.press("Escape");
    await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
    const f = await focused(page);
    assert.deepEqual(role ? [f.cn, f.role] : [f.cn, f.inHead], role ? ["cat", role] : ["cat", true], `роль «${role}»: фокус на свіжій кнопці`);
  }
  assert.deepEqual(errors, []);
});

test("6: модуль без налаштувань вмикається одразу — тост «Підключено», шухляда не лишається", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  await pickFromCatalog(page, "memo-bare");
  await waitBadge(page, "memo-bare", "ok");
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Memo bare (test)");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "шухляда закрилась сама");
  const mods = JSON.parse(readFileSync(path.join(spacePath, "space.json"), "utf8")).modules;
  assert.equal(mods["memo-bare"].enabled, true);
  assert.deepEqual(errors, []);
});

guardRealDeai();

/**
 * Екран «Підключення» (Deai 0.5.0, етап 3a) — живе проведення: справжній сервер в ізольованій «машині» (тимчасові
 * `HOME`/`DEAI_HOME`), справжній Chromium. Модуль-фікстура `memo-publish` (`tests/fixtures/modules-conn`, через
 * тестовий шов `DEAI_EXTRA_MODULES`) — роль `publish` з ЛОКАЛЬНОЮ перевіркою: заміна постачальника перевіряється без
 * жодної мережі. Vercel і Supabase тут НЕ вмикаються — їхній `check` ходить у мережу з процесу сервера.
 *
 * Юніти (`tests/connections-*.test.mjs`) і сервер-тести (`tests/test_modules_api.py`) доводять кожну ланку окремо;
 * тут те, що їм недоступне, бо живе в браузері: чи входи справді ведуть на сторінку, чи панель тримає секрет лише у
 * властивості поля (а не в розмітці), чи запит несе простір, який людина бачить, чи заміна йде ОДНИМ записом.
 *
 * ⛔ Секрет «ніде не світиться» стережуть ТРИ незалежні сторожі (сценарії 3, 5, 6): знімок DOM наприкінці
 * (`page.content()`), СТЕЖЕННЯ за кожною мутацією (`watchLeaks`: тимчасова розмітка, що зникла за мить, теж
 * ловиться — знімок наприкінці її не бачив би) і лічильник адрес запитів та тіл відповідей API. «Свідок» стеження
 * (`plantLeak`) — навмисний витік на старті кожної сторінки: без нього «жодного витоку» зеленіло б і зі зламаним
 * стеженням.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (вхід і картки)   — пункт `conn` у `ddSpaces` (`shell-bar.js`), `BAR_ACTIONS.conn` і гілка `conn` у `paintHome`
 *        (`app.js`): кожне окремо червонить УСІ сценарії (вхід один — дропдаун); `connFocusPending` (фокус на
 *        картці після входу) — лише сценарій 1.
 *   2 (підключення)     — `missingRequired` до запиту (`cnSubmit`: без нього порожнє поле йде на сервер — червоніють 2 і
 *        5); вердикт ok → бейдж «Підключено» й закриття панелі; запис несе `space`.
 *   3 (заміна)          — `replace = true` у `cnSubmit`: без нього `409 role-taken` і заміни нема (червоніють 3, 5, 6 —
 *        усі, що йдуть через «Замінити?»); `roleHolders` + питання; сервер `_holders` під локом. Секрет — див. нижче.
 *   4 (відмова, Esc)    — `return` на «ні» у питанні «Замінити?» (без нього скасування все одно пише); Esc-обробник
 *        панелі (`requestCloseCnDrawer`); `afterModulesChange` у `connDisable` (без нього картка не міняє бейдж).
 *   5 (перевірка «ні»)  — `verdictText` (деталь невідомого коду: «memo-says-no — note is fail»), `result.kind:
 *        'failed'` без повтору загального рядка (`resultHTML`); обовʼязкове порожнє — помилка без запиту, а введений
 *        секрет лишається ВЛАСТИВІСТЮ поля (`restoreCnSecrets`).
 *   6 (секрет: «Стерти») — `readCnForm` бачить `aria-pressed` (інакше «Зберегти» лишається вимкненою), `formPatch` шле
 *        `null` (не порожній рядок), `canErase` (кнопки нема в незаданого); сервер стирає ключ у `secrets.json`.
 *   7 (інший простір)   — `closeCnDrawer` у `loadConn` при зміні `spaceId`: без нього панель з чужого простору
 *        лишається над новою сторінкою.
 *   секрет ніде не світиться (3, 5, 6) — ТРИ незалежні мутації: секрет у `value` на перемальовці «в польоті»
 *        (мить — ловить ЛИШЕ `watchLeaks`: знімок наприкінці її не бачить), у атрибуті `body` після успіху і в `value`
 *        після невдалої перевірки (обидві видно й знімку, і стеженню).
 *
 * ⚠️ Сценарій 6 перед повторним відкриттям панелі перезавантажує сторінку: після запису картки ще мить тримають СТАРИЙ
 * список (`afterModulesChange` перечитує його асинхронно), і «Налаштувати», натиснуте в цей проміжок, показало б
 * колишнє «задано». Людині цього вікна не влучити, а тесту — легко; свіжий вхід його не має.
 */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не
   збігається з чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 13400;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules-conn");
const SECRET = "live-S3cret-Жовтень-7";
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

/**
 * Стеження за витоком секрету в розмітку: кожна мутація DOM, що ПОКЛАЛА `SECRET` у атрибут, текст чи нову гілку,
 * лишає запис у `window.__leaks`. Перевіряється САМ вузол запису (а не поточна розмітка): панель, що на мить
 * мала `value="…"` і одразу очистилась (`innerHTML = ''`), наприкінці вже чиста, а вузол — ще ні.
 */
const watchLeaks = (page) => page.evaluate((secret) => {
  window.__leaks = [];
  const hit = (s) => typeof s === "string" && s.includes(secret);
  new MutationObserver((recs) => {
    for (const r of recs) {
      if (r.type === "attributes" && hit(r.target.getAttribute(r.attributeName))) window.__leaks.push(`attr:${r.attributeName}`);
      else if (r.type === "characterData" && hit(r.target.data)) window.__leaks.push("text");
      else if (r.type === "childList") {
        for (const n of r.addedNodes) if (hit(n.outerHTML ?? n.textContent)) window.__leaks.push(`node:${n.nodeName}`);
      }
    }
  }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
}, SECRET);

/** Свідок стеження: навмисний витік, який воно мусить побачити (і який потім знімається, щоб не отруїти сценарій). */
async function plantLeak(page) {
  const seen = await page.evaluate(async (secret) => {
    const n = document.createElement("i");
    n.setAttribute("data-witness", secret);
    document.body.appendChild(n);
    await new Promise((done) => setTimeout(done, 0));
    n.remove();
    const got = window.__leaks.length;
    window.__leaks = [];
    return got;
  }, SECRET);
  assert.ok(seen >= 1, "свідок: стеження за витоком не побачило навмисного витоку — воно мертве");
}

const leaks = (page) => page.evaluate(() => window.__leaks);

/**
 * Сервер + контекст браузера. Контекст рахує КОЖЕН запит (адреси й тіла `POST`), збирає тіла відповідей API й не
 * пускає нічого за межі машини (`route` → `abort`): якщо код колись піде назовні, тест не постукає на справжній
 * хост, а запис у `outside` його видасть. `two` — другий простір («Atelier»), для сценарію зміни простору.
 */
async function boot(t, { two = false } = {}) {
  const X = taskFixture({ html: MOCKUP });
  const spaces = [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }];
  if (two) {
    const Y = taskFixture({ html: MOCKUP });
    spaces.push({ name: "Atelier", id: "atelier", color: "space-3", tasks: { t2: { dir: Y.dir, title: "Інша" } } });
  }
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_EXTRA_MODULES: MODULES_DIR }, spaces });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const outside = [];
  const requests = [];
  const posts = [];
  const bodies = [];
  context.on("request", (r) => {
    requests.push(r.url());
    if (r.method() === "POST") posts.push(r.postData() ?? "");
    if (!isLocal(r.url())) outside.push(r.url());
  });
  context.on("response", async (r) => {
    if (r.url().includes("/api/")) { try { bodies.push(await r.text()); } catch { /* перервана відповідь */ } }
  });
  await context.route((u) => !isLocal(u.href), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  await watchLeaks(page);
  await plantLeak(page);
  return { ...server, page, outside, requests, posts, bodies, errors, spacePath: server.spaces[0].path };
}

const badge = (page, id) => page.locator(`.cn-card[data-id="${id}"] .cn-badge`).getAttribute("class");
const waitBadge = (page, id, kind) => page.waitForSelector(`.cn-card[data-id="${id}"] .cn-badge--${kind}`, { timeout: 15000 });
const spaceJson = (p) => JSON.parse(readFileSync(path.join(p, "space.json"), "utf8"));
const secretsJson = (deaiHome) => JSON.parse(readFileSync(path.join(deaiHome, "secrets.json"), "utf8"));
const modulesList = async (url, space = "studio") => (await (await fetch(`${url}/api/modules?space=${space}`)).json()).modules;
const tokenOf = (list, id = "memo-publish") => list.find((m) => m.id === id).settings.find((s) => s.key === "token");

/** Відкрити дропдаун простору й дочекатись РЯДКІВ просторів (перший показ малюється зі старою відповіддю). */
async function openSpaceDd(page, rows = 1) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n,
    rows, { timeout: 15000 });
}

/** Вхід: дропдаун простору → «Підключення…» → сторінка з картками. */
async function openConnections(page, rows = 1) {
  await openSpaceDd(page, rows);
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });
}

/** «Підключити» memo-publish → панель → поля → «Підключити» → питання «Замінити?» → «Замінити». */
async function enableMemo(page, { note, token }) {
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', note);
  if (token) await page.fill('#cn-drawer [data-cn-field="token"]', token);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
}

/** Секрет ніде не світиться: ні в розмітці зараз, ні в жодній мутації, ні в адресі, ні у відповіді API. */
async function assertSecretNowhere({ page, requests, posts, bodies }) {
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці (мутація DOM)");
  assert.ok(!requests.some((u) => u.includes(SECRET)), "секрет в адресі запиту");
  assert.ok(posts.some((b) => b.includes(SECRET)), "свідок: секрет мусив піти в тілі POST (інакше «нема в адресі» нічого не варте)");
  assert.ok(bodies.some((b) => b.includes("memo-publish")), "свідок: тіла відповідей API зібрано");
  assert.ok(!bodies.some((b) => b.includes(SECRET)), "секрет у відповіді API");
}

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: вхід із дропдауна, секції за ролями, неявний static-publish «типово», крихта «Підключення», фокус на картці", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  const titles = await page.locator(".cn-sec-h").allTextContents();
  assert.deepEqual(titles.slice(0, 3), ["Публікація", "Командні коментарі", "Токени дизайн-системи"]);
  assert.match(await page.locator('.cn-card[data-id="static-publish"]').textContent(), /типово/);
  assert.match(await badge(page, "css-tokens"), /cn-badge--off/);
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Підключення/);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.cn ?? null) !== null, true, "фокус на кнопці картки");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("2: css-tokens — «Підключити» з файлом простору → «Підключено»; обовʼязкове порожнє — помилка без запиту", async (t) => {
  const { page, spacePath, outside, errors } = await boot(t);
  writeFileSync(path.join(spacePath, "ds.css"), ":root{--c-a:#123456;--gap:4px}");
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="css-tokens"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('#cn-drawer [aria-invalid="true"]');
  assert.equal(spaceJson(spacePath).modules, undefined, "порожнє обовʼязкове — запиту не було");
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds.css");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "css-tokens", "ok");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "ok — панель закрилась");
  assert.deepEqual(spaceJson(spacePath).modules["css-tokens"], { enabled: true, settings: { file: "{space}/ds.css" } });
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("3: заміна публікації — питання → replace → static-publish вимкнено, memo-publish підключено; секрет ніде не світиться", async (t) => {
  const m = await boot(t);
  const { page, url, spacePath, deaiHome, outside, errors } = m;
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Публікація в теку/);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "memo-publish", "ok");
  await waitBadge(page, "static-publish", "off");
  const mods = spaceJson(spacePath).modules;
  assert.equal(mods["static-publish"].enabled, false);
  assert.equal(mods["memo-publish"].enabled, true);
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: Memo publish \(test\)/);
  const tok = tokenOf(await modulesList(url));
  assert.deepEqual(tok, { key: "token", type: "secret", label: "Token (test)", required: false, set: true });
  /* Секрет лежить у сховищі Deai, а не в теці простору. */
  assert.equal(secretsJson(deaiHome).studio["memo-publish"].token, SECRET, "свідок: секрет збережено в secrets.json");
  assert.ok(!readFileSync(path.join(spacePath, "space.json"), "utf8").includes(SECRET), "секрет у space.json");
  await assertSecretNowhere(m);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("4: відмова від заміни лишає все як було; Esc із незбереженим питає; вимкнення через питання з наслідком", async (t) => {
  const { page, spacePath, outside, errors } = await boot(t);
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "x");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(spaceJson(spacePath).modules, undefined, "скасування — нічого не записано");
  assert.equal(await page.locator("#cn-drawer").isVisible(), true, "панель лишилась");
  await page.keyboard.press("Escape");                       // незбережене → питання
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await page.click('[data-cn="disable"][data-id="static-publish"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /кнопки публікації в смузі нема/);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "static-publish", "off");
  assert.equal(spaceJson(spacePath).modules["static-publish"].enabled, false);
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: нікого/);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("5: перевірка, що каже «ні» — панель лишається з «Збережено, але перевірка не пройшла» і причиною; поле пароля порожнє", async (t) => {
  const m = await boot(t);
  const { page, outside, errors } = m;
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  /* Обовʼязкове `note` порожнє, секрет уже введено: помилка без запиту й без питання; секрет лишається у ВЛАСТИВОСТІ
     поля (людині не вводити знову), а в розмітку не потрапляє. */
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('#cn-drawer [data-cn-field="note"][aria-invalid="true"]');
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "обовʼязкове порожнє — питання «Замінити?» не доходить");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="token"]'), SECRET, "введений секрет лишився в полі");
  assert.ok(!(await page.locator("#cn-drawer").evaluate((n) => n.outerHTML)).includes(SECRET), "секрет у розмітці панелі");
  await page.fill('#cn-drawer [data-cn-field="note"]', "fail");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer .cn-res--err");
  const txt = await page.locator("#cn-drawer .cn-res--err").textContent();
  assert.match(txt, /Збережено, але перевірка не пройшла/);
  assert.match(txt, /memo-says-no — note is fail/);
  assert.ok(!txt.includes("Перевірка не пройшла"), "загальний рядок після голови не повторюється");
  assert.match(await page.locator('#cn-drawer [data-cn-dr="submit"]').textContent(), /Зберегти/, "далі — режим правки");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="token"]'), "", "після відповіді сервера поле пароля порожнє");
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /задано/, "секрет збережено, стан — «задано»");
  await waitBadge(page, "memo-publish", "error");
  await assertSecretNowhere(m);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("6: секрет — «Стерти» позначає (aria-pressed + примітка), збереження шле secrets: {token: null}, список після — set: false", async (t) => {
  const m = await boot(t);
  const { page, url, deaiHome, outside, errors } = m;
  await openConnections(page);
  await enableMemo(page, { note: "hello", token: SECRET });
  await waitBadge(page, "memo-publish", "ok");
  assert.equal(tokenOf(await modulesList(url)).set, true, "свідок: секрет задано до стирання");
  assert.equal(secretsJson(deaiHome).studio["memo-publish"].token, SECRET, "свідок: секрет у secrets.json до стирання");

  await page.click('[data-cn="configure"][data-id="memo-publish"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="erase"]');
  const erase = page.locator('#cn-drawer [data-cn-dr="erase"]');
  const note = page.locator('#cn-drawer [data-cn-erase-note="token"]');
  const save = page.locator('#cn-drawer [data-cn-dr="submit"]');
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /задано/);
  assert.equal(await erase.textContent(), "Стерти");
  assert.equal(await erase.getAttribute("aria-pressed"), "false");
  assert.equal(await note.isVisible(), false, "примітка стирання схована, доки не позначено");
  assert.equal(await save.isDisabled(), true, "без змін «Зберегти» вимкнена");

  await erase.click();
  assert.equal(await erase.getAttribute("aria-pressed"), "true");
  assert.equal(await erase.textContent(), "Стерти", "підпис кнопки сталий — стан у aria-pressed");
  assert.equal(await note.isVisible(), true);
  assert.match(await note.textContent(), /буде стерто/);
  assert.equal(await save.isDisabled(), false, "позначене стирання — зміна");
  await erase.click();                                       // знято позначку → знову без змін
  assert.equal(await erase.getAttribute("aria-pressed"), "false");
  assert.equal(await note.isVisible(), false);
  assert.equal(await save.isDisabled(), true);

  await erase.click();
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/api/module-settings")),
    save.click(),
  ]);
  assert.deepEqual(JSON.parse(req.postData()), { space: "studio", id: "memo-publish", secrets: { token: null } });
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  assert.equal(tokenOf(await modulesList(url)).set, false, "список після стирання — set: false");
  assert.equal(secretsJson(deaiHome).studio?.["memo-publish"]?.token, undefined, "ключ стерто в secrets.json");
  await assertSecretNowhere(m);

  /* Панель, відкрита знову: «не задано», кнопки «Стерти» вже нема (стирати нічого). Спершу — свіжий вхід на сторінку:
     після запису картки ще мить тримають СТАРИЙ список (`afterModulesChange` перечитує його асинхронно), і «Налаштувати»,
     натиснуте в цей проміжок, показало б колишнє «задано» — це не те, що тут перевіряється. */
  await page.reload();
  await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  await watchLeaks(page);
  await openConnections(page);
  await page.click('[data-cn="configure"][data-id="memo-publish"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="token"]');
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /не задано/);
  assert.equal(await page.locator('#cn-drawer [data-cn-dr="erase"]').count(), 0);
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM після перезавантаження");
  assert.deepEqual(await leaks(page), []);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("7: простір перемкнули з відкритою панеллю — панель закрилась без питання, сторінка про новий простір", async (t) => {
  const { page, spaces, outside, errors } = await boot(t, { two: true });
  const [studio, atelier] = spaces;
  /* У «Atelier» агент уже ввімкнув memo-publish: правимо `space.json` ДО перемикання, щоб картки нового простору
     відрізнялись від старих (інакше «сторінка про новий простір» був би лише заголовок). */
  const sj = spaceJson(atelier.path);
  sj.modules = { "memo-publish": { enabled: true, settings: { note: "hello" } } };
  writeFileSync(path.join(atelier.path, "space.json"), JSON.stringify(sj));
  const atelierBefore = readFileSync(path.join(atelier.path, "space.json"), "utf8");

  await openConnections(page, 2);
  assert.match(await page.locator("#cn-title").textContent(), /Підключення · Studio/);
  assert.match(await badge(page, "memo-publish"), /cn-badge--off/, "у Studio memo-publish вимкнено");
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "незбережене");      // брудна форма: у «Studio» питали б

  await openSpaceDd(page, 2);
  await page.click('.dd--spaces .dd-item[data-val="atelier"]');
  await page.waitForFunction(() => /Atelier/.test(document.querySelector("#cn-title")?.textContent ?? ""), null, { timeout: 15000 });
  await page.waitForSelector('.cn-card[data-id="memo-publish"] [data-cn="configure"]', { timeout: 15000 });
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "панель з чужого простору не лишилась");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "перехід свідомий — питання «Відкинути?» нема");
  assert.match(await page.locator("#cn-title").textContent(), /Підключення · Atelier/);
  assert.ok((await page.locator(".cn-lead").textContent()).includes(atelier.path), "теки в заголовку — нового простору");
  assert.match(await badge(page, "memo-publish"), /cn-badge--unchecked/, "картки — нового простору (memo-publish там увімкнено)");
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: Memo publish \(test\)/);
  assert.equal(readFileSync(path.join(atelier.path, "space.json"), "utf8"), atelierBefore, "у новий простір нічого не записано");
  assert.equal(spaceJson(studio.path).modules, undefined, "у старий простір теж");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

guardRealDeai();

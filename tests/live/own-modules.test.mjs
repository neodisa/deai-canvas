/**
 * Свої модулі простору й довіра (Deai 0.7.0, етап 3c) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium. Системне вікно ОС замінює шов `DEAI_TRUST_CONFIRM` (діє лише з
 * тимчасовим `DEAI_HOME`); ⛔ у автотестах вікно не показується НІКОЛИ. Модуль `memo-own` лежить у теці простору
 * (`<простір>/modules/memo-own/`); його `server.py` дописує свій `__file__` у мітку-файл `DEAI_OWN_CANARY` при кожному
 * виконанні верхнього рівня — так видно, ЧИ виконувався код і ЗВІДКИ (знімок у `<DEAI_HOME>/trusted/`, а не тека).
 *
 * Сценарії: 1 — повний шлях (недовірений → діалог → довіра → підключення → правка на диску → стара версія працює →
 * повторна довіра → «Забрати довіру»); 2 — системне вікно відмовило; 3 — «колега закомітив» (увімкнений, але не довірений);
 * 4 — майстер: «Довіритись…» на кроці 2; 5 — запит без заголовків браузера (і з підробленим `Origin`, і `Sec-Fetch-Site` без `Origin`) → 403; 6 — тека змінилась, поки діалог
 * відкритий; 7 — «Забрати довіру» з діалогу; 8 — тека, якій не можна довіритись (символьне посилання); 9 — майстер:
 * колега вже ввімкнув недовірений модуль у `space.json` теки.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (одна мутація — один рядок застосунку, файл відновлено побайтно):
 *   1 — гілка `paper` у `capabilities` (`deai_modules.py`); `afterModulesChange` після довіри в `openTrust` (`app.js`); `forget_check`
 *       у `grant_trust` (забуте `own v1` — перевірка `status: unchecked` після повторної довіри); ядро вантажить теку, а не знімок
 *       (валять 1 і 6); діалог без рядків файлів; `data-autofocus` зі «Скасувати» (фокус діалогу нової версії);
 *   2 — `grant_trust`, що ігнорує відповідь системного вікна (шва): довіра зʼявилась би попри «ні»; відмову шва стережуть і юніти
 *       `tests/test_modules_trust_api.py`;
 *   3 — `paper` у `capabilities` (без нього сторінка бачить «space.json не читається» й ховає картки);
 *   4 — кнопка «Довіритись…» в `optionHTML` (`wizard-view.js`); повернення фокуса в `trustFrom` (`wizard.js`); `loadStep2`, що скидає
 *       вибір іншої ролі після діалогу;
 *   5 — `not origin or` у `_module_trust_post` (`serve.py`: запит БЕЗ `Origin`, але з `Sec-Fetch-Site: same-origin`) і перевірка
 *       `Sec-Fetch-Site` там само (без `Origin` її не видно — потрібні запити з підробленим локальним `Origin`);
 *   6 — повторне відкриття діалогу на `module-changed` (`openTrust`); `grant_trust`, що ігнорує зміну хешу;
 *   7 — `danger: true` у `untrustFlow` (`app.js`), а також `afterModulesChange` після довіри; 8 — `trTitleRefused` у `trustDialogHTML`
 *       (`trust-view.js`);
 *   9 — картки лише для вибраних без `needsTrust` у `loadStep3` (`wizard.js`); `paper` у `capabilities`; кнопка «Довіритись…».
 *   Охоронець шва в `boot` (невідоме значення `seam` → падіння ДО `startServer`) мутацією з живим сервером НЕ доводиться: без нього
 *   одруківка показала б справжнє системне вікно ОС; його стережуть позиція асерта (перший рядок `boot`) і окремий прогін без сервера.
 *   Не мутується живцем (стережуть юніти): системне вікно ОС — лише шов `DEAI_TRUST_CONFIRM`; ручний показ — окремий крок плану.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, postJson, stop, waitBarReady, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs` стереже, що бази не збігаються). */
const PORT_BASE = 13600;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
const CARD = '.mc[data-id="memo-own"]';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* Рядок-коментар різної довжини для різних версій: розмір файла різний, тож відбиток не залежить від роздільності `mtime_ns`. */
const SERVER_PY = (version) => `import os
VERSION = "${version}"
# ${"=".repeat(Number(version.slice(1)) * 8)}
_p = os.environ.get("DEAI_OWN_CANARY")
if _p:
    with open(_p, "a") as _f:
        _f.write(__file__ + "\\n")


def check(ctx):
    return {"ok": True, "detail": "own " + VERSION}


def publish(ctx, build_dir, task):
    raise ctx["ModuleError"]("module-error", message="memo-own does not publish")
`;

/** Тека свого модуля в просторі `spacePath` (роль `publish`, перевірка локальна). */
function writeOwn(spacePath, version = "v1") {
  const d = path.join(spacePath, "modules", "memo-own");
  mkdirSync(d, { recursive: true });
  writeFileSync(path.join(d, "module.json"), JSON.stringify({ api: 1, id: "memo-own", name: "Memo own (test)",
    version: "1.0.0", roles: ["publish"], settings: [{ key: "note", type: "text", label: "Note (test)" }] }));
  writeFileSync(path.join(d, "server.py"), SERVER_PY(version));
  return d;
}

/** Сервер + сторінка. `seam` — відповідь «системного вікна»; `committed` — `space.json` уже вмикає `memo-own` (колега). */
async function boot(t, { seam = "yes", committed = false, extraFolder = null } = {}) {
  /* ПЕРШИМ рядком, до `startServer`: `module_trust.seam_value` для будь-якого іншого значення дає `None` — сервер показав би
     СПРАВЖНЄ системне вікно. Одруківка в `seam` має впасти тут, а не на екрані. */
  assert.ok(["yes", "no", "unavailable"].includes(seam), `невідомий шов «${seam}»: сервер показав би справжнє системне вікно`);
  const canary = path.join(mkdtempSync(path.join(tmpdir(), "dc-live-canary-")), "canary.log");
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_TRUST_CONFIRM: seam, DEAI_OWN_CANARY: canary },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }] });
  t.after(() => stop(server.child));
  const spacePath = server.spaces[0].path;
  const ownDir = writeOwn(spacePath);
  if (committed) {
    const p = path.join(spacePath, "space.json");
    const sj = JSON.parse(readFileSync(p, "utf8"));
    sj.modules = { "memo-own": { enabled: true, settings: {}, roles: ["publish"] }, "static-publish": { enabled: false, settings: {} } };
    writeFileSync(p, JSON.stringify(sj));
  }
  if (extraFolder) writeOwn(path.join(server.home, extraFolder));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  const ran = () => { try { return readFileSync(canary, "utf8").split("\n").filter(Boolean); } catch { return []; } };
  return { ...server, page, errors, spacePath, ownDir, ran };
}

async function openConnections(page) {
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector(CARD, { timeout: 15000 });
}

const check = async (url) => (await (await postJson(url, "/api/module-check", { space: "studio", id: "memo-own" })).json());
const capsOf = async (url) => (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((x) => x.id === "studio").capabilities;
const dialogText = (page) => page.locator("form.tr").textContent();
const sjText = (s) => readFileSync(path.join(s.spacePath, "space.json"), "utf8");

test("1: недовірений не виконується → діалог → довіра → підключення зі знімка → правка на диску (працює стара) → повторна довіра → «Забрати довіру»", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await openConnections(page);
  await page.waitForSelector(`${CARD} .bdg--trust`);
  assert.match(await page.locator(`${CARD} .mc-tag`).textContent(), /свій/);
  assert.equal(await page.locator(`${CARD} [data-cn="enable"]`).count(), 0, "«Підключити» нема до довіри");
  assert.deepEqual(s.ran(), [], "код недовіреного модуля виконано");

  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус — на «Скасувати»");
  const d1 = await dialogText(page);
  assert.match(d1, /Довіритись модулю «Memo own \(test\)»\?/);
  assert.match(d1, /Відбиток [0-9a-f]{12}/);
  assert.match(d1, /server\.py/);
  assert.match(d1, /з вашими правами/);
  assert.deepEqual(s.ran(), [], "діалог (GET /api/module-trust) код не виконує");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} [data-cn="enable"]`);
  const trusted = path.join(s.deaiHome, "trusted") + path.sep;
  assert.ok(s.ran().length > 0 && s.ran().every((p) => p.startsWith(trusted)), `виконується лише знімок: ${s.ran()}`);

  await page.click(`${CARD} [data-cn="enable"]`);
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="submit"]');
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");                  // «Замінити?» — роль тримає неявна «Публікація в теку»
  await page.click('.cv-ask-scrim [data-a="ok"]');
  await page.waitForSelector(`${CARD} .bdg--ok`, { timeout: 15000 });
  assert.equal((await check(s.url)).check.detail, "own v1");

  writeFileSync(path.join(s.ownDir, "server.py"), SERVER_PY("v2"));
  /* Перевірено, ок → на картці дії нема: «Перевірити» — у меню «⋯». */
  await page.click(`${CARD} .mc-more`);
  await page.click(`#th-menu [data-cn="check"][data-id="memo-own"]`);
  await page.waitForFunction((sel) => /У теці є зміни/.test(document.querySelector(`${sel} .mc-why`)?.textContent ?? ""), CARD);
  assert.equal((await check(s.url)).check.detail, "own v1", "працює довірена версія, а не правка на диску");

  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус — на «Скасувати», не на «Забрати довіру»");
  assert.match(await dialogText(page), /Довіритись новій версії/);
  assert.match(await page.locator("form.tr .tr-files").textContent(), /server\.py.*змінено/s);
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  const entry = (await (await fetch(`${s.url}/api/modules?space=studio`)).json()).modules.find((m) => m.id === "memo-own");
  assert.equal(entry.status, "unchecked", "нова версія — старий результат перевірки (`own v1`) забуто (`forget_check` у `grant_trust`)");
  assert.equal((await check(s.url)).check.detail, "own v2");

  const before = sjText(s);
  await page.click(`${CARD} .mc-name b`);                       // клік по увімкненій картці — шухляда
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="untrust"]');
  await page.click('#cn-drawer [data-cn-dr="untrust"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Забрати довіру до «Memo own \(test\)»/);
  await page.click('.cv-ask-scrim [data-a="ok"]');
  await page.waitForSelector(`${CARD} .bdg--trust`, { timeout: 15000 });
  assert.equal(sjText(s), before, "space.json не змінено");
  const caps = await capsOf(s.url);
  assert.equal(caps.publish, null, "роль «на папері» за недовіреним — без постачальника, не «Публікація в теку»");
  assert.equal(caps.error, undefined, "і це не «space.json не читається»");
  assert.match(await page.locator(`${CARD} .bdg--trust`).textContent(), /Чекає довіри/, "роль «на папері» — картка чекає довіри");
  assert.deepEqual(s.errors, []);
});

test("2: системне вікно відмовило — текст у діалозі, діалог лишається, довіри нема", async (t) => {
  const s = await boot(t, { seam: "no" });
  const { page } = s;
  await openConnections(page);
  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForFunction(() => /Довіру не підтверджено в системному вікні/.test(document.querySelector("form.tr [data-form-error]")?.textContent ?? ""));
  assert.equal(await page.locator("form.tr").count(), 1, "діалог лишився");
  await page.click('form.tr [data-a="cancel"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} .bdg--trust`);
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

test("3: колега закомітив — «Увімкнено, але не довірено», картка «Чекає довіри», картки на місці (не «space.json не читається»)", async (t) => {
  const s = await boot(t, { committed: true });
  const { page } = s;
  await openConnections(page);
  await page.waitForSelector(`${CARD} .bdg--trust`);
  assert.match(await page.locator(`${CARD} .mc-why`).textContent(), /увімкнено в просторі, але на цьому компʼютері йому не довірено/);
  await page.click(`${CARD} .mc-more`);
  assert.equal(await page.locator(`#th-menu [data-cn="disable"][data-id="memo-own"]`).count(), 1, "«Вимкнути» — у меню «⋯»");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".cn-err").count(), 0, "сторінка не вважає це нечитабельним space.json");
  assert.match(await page.locator(`${CARD} .bdg--trust`).textContent(), /Чекає довіри/);
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

test("4: майстер — «Довіритись…» у рядку кроку 2 робить модуль доступним для вибору", async (t) => {
  const s = await boot(t, { extraFolder: path.join("work", "fresh") });
  const { page } = s;
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('#tasks-home .wz[data-step="1"]');
  await page.fill("#sp-name", "Fresh");
  await page.fill("#sp-path", "~/work/fresh");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="2"] [data-wz="trust"][data-id="memo-own"]', { timeout: 15000 });
  assert.equal(await page.locator('input[data-wz-pick][value="memo-own"]').isDisabled(), true);
  const other = await page.evaluate(() => {                     // вибір в іншій ролі — має пережити діалог і перечитування
    const r = [...document.querySelectorAll("#tasks-home input[data-wz-pick]")]
      .find((x) => x.dataset.role !== "publish" && x.value && !x.disabled && !x.checked);
    if (!r) return null;
    r.click();
    return { role: r.dataset.role, value: r.value };
  });
  assert.ok(other, "є що вибрати в іншій ролі");
  const otherSel = `input[data-wz-pick][data-role="${other.role}"][value="${other.value}"]`;
  await page.click('[data-wz="trust"][data-id="memo-own"]');
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="cancel"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForFunction(() => document.activeElement?.dataset?.wz === "trust", null, { timeout: 15000 });
  await page.click('[data-wz="trust"][data-id="memo-own"]');
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector('input[data-wz-pick][value="memo-own"]:not([disabled])', { timeout: 15000 });
  assert.equal(await page.locator('[data-wz="trust"][data-id="memo-own"]').count(), 0);
  await page.waitForFunction(() => document.activeElement?.value === "memo-own", null, { timeout: 15000 });
  assert.equal(await page.locator(otherSel).isChecked(), true, "вибір іншої ролі збережено");
  assert.deepEqual(s.errors, []);
});

test("5: запит довіри без заголовків браузера (агент, curl) — 403 trust-needs-ui, довіри нема", async (t) => {
  const s = await boot(t);
  const st = await (await fetch(`${s.url}/api/module-trust?space=studio&id=memo-own`)).json();
  const res = await postJson(s.url, "/api/module-trust", { space: "studio", id: "memo-own", hash: st.trust.hash });
  assert.equal(res.status, 403);
  assert.equal((await res.json()).code, "trust-needs-ui");
  /* Агент може підробити й `Origin` (локальний) — не «позначку браузера» `Sec-Fetch-Site: same-origin` (її ставить лише браузер зі
     сторінки канваса): без неї чи з чужою — теж 403. Без цих запитів прибрана перевірка `Sec-Fetch-Site` лишалась би непоміченою:
     запити без `Origin` відсікає раніше інша умова. І навпаки: `Sec-Fetch-Site: same-origin` БЕЗ `Origin` — перший елемент
     переліку — стереже саму умову `not origin or` (без неї запит без `Origin` пройшов би за самою позначкою). */
  for (const headers of [{ "Sec-Fetch-Site": "same-origin" }, { Origin: s.url }, { Origin: s.url, "Sec-Fetch-Site": "cross-site" },
    { Origin: s.url, "Sec-Fetch-Site": "same-site" }]) {
    const forged = await fetch(`${s.url}/api/module-trust`, { method: "POST", headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({ space: "studio", id: "memo-own", hash: st.trust.hash }) });
    assert.equal(forged.status, 403, `підроблений Origin (${JSON.stringify(headers)}) не дає довіри`);
    assert.equal((await forged.json()).code, "trust-needs-ui");
  }
  assert.equal((await (await fetch(`${s.url}/api/modules?space=studio`)).json()).modules.find((m) => m.id === "memo-own").trust, "untrusted");
  assert.deepEqual(s.ran(), []);
});

test("6: тека змінилась, поки діалог відкритий — «Тека змінилась…», новий відбиток, фокус на «Скасувати», друга спроба довіряє новій версії", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await openConnections(page);
  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  const print1 = (await dialogText(page)).match(/Відбиток ([0-9a-f]{12})/)[1];
  writeFileSync(path.join(s.ownDir, "server.py"), SERVER_PY("v3"));
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr .tr-reopened", { timeout: 15000 });
  assert.match(await page.locator("form.tr .tr-reopened").textContent(), /Тека змінилась, поки діалог був відкритий/);
  const print2 = (await dialogText(page)).match(/Відбиток ([0-9a-f]{12})/)[1];
  assert.notEqual(print2, print1, "показано свіжий відбиток");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус — на «Скасувати»");
  assert.deepEqual(s.ran(), [], "застарілій версії не довірено, код не виконано");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} [data-cn="enable"]`);
  const trusted = path.join(s.deaiHome, "trusted") + path.sep;
  assert.ok(s.ran().length > 0 && s.ran().every((p) => p.startsWith(trusted)), `виконується лише знімок: ${s.ran()}`);
  assert.deepEqual(s.errors, []);
});

test("7: «Забрати довіру» з діалогу нової версії — небезпечне питання, фокус на «Скасувати», модуль знову недовірений, space.json без змін", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await openConnections(page);
  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} [data-cn="enable"]`);
  writeFileSync(path.join(s.ownDir, "server.py"), SERVER_PY("v2"));
  await page.goto(`${s.url}/app/`);                              // свіже «Підключення»: картка бачить зміну теки
  await waitBarReady(page, 15000);
  await openConnections(page);
  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector('form.tr [data-tr="untrust"]');
  const before = sjText(s);
  await page.click('form.tr [data-tr="untrust"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector('.cv-ask-scrim [data-a="ok"].cv-ask-danger');
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Забрати довіру до «Memo own \(test\)»/);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус — на «Скасувати»");
  await page.click('.cv-ask-scrim [data-a="ok"]');
  await page.waitForSelector(`${CARD} .bdg--trust`, { timeout: 15000 });
  assert.equal(sjText(s), before, "space.json не змінено");
  assert.deepEqual(s.errors, []);
});

test("8: тека з символьним посиланням — діалог без «Довірити», заголовок не питає, Esc закриває, фокус повертається на картку", async (t) => {
  const s = await boot(t);
  symlinkSync("server.py", path.join(s.ownDir, "alias.py"));
  const { page } = s;
  await openConnections(page);
  /* Назва на картці — теж id (маніфест не прочитано), тож картка й діалог узгоджені; перевірка ТОЧНА за елементом назви. */
  assert.match((await page.locator(`${CARD} .mc-name b`).textContent()).trim(), /^memo-own/, "на картці — id, а не назва з маніфесту");
  await page.click(`${CARD} [data-cn="trustinfo"]`);
  await page.waitForSelector("form.tr");
  const d = await dialogText(page);
  /* Відмова сканера (символьне посилання) приходить ДО читання маніфесту: назви з маніфесту нема, у заголовку — id. */
  assert.match(d, /Модулю «memo-own» не можна довіритись/);
  assert.match(d, /символьне посилання/);
  assert.doesNotMatch(d, /Довіритись модулю/);
  assert.equal(await page.locator('form.tr [data-a="ok"]').count(), 0, "«Довірити» нема");
  await page.keyboard.press("Escape");
  await page.waitForSelector("form.tr", { state: "detached" });
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.cn), "trustinfo", "фокус — на кнопці картки");
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

test("9: майстер — колега ввімкнув недовірений модуль у space.json теки: вибраний і вимкнений, крок 3 — «чекає довіри» замість картки, жодного запису модулів", async (t) => {
  const s = await boot(t);
  const { page } = s;
  const shared = path.join(s.home, "work", "shared");
  writeOwn(shared);
  writeFileSync(path.join(shared, "space.json"), JSON.stringify({ name: "Shared", color: "space-4",
    modules: { "memo-own": { enabled: true, settings: {}, roles: ["publish"] } } }));
  const posts = [];
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    if (r.method() === "POST" && p.startsWith("/api/module-")) posts.push(p);
  });
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('#tasks-home .wz[data-step="1"]');
  await page.fill("#sp-path", "~/work/shared");
  await page.waitForFunction(() => { const e = document.getElementById("sp-found"); return Boolean(e && !e.hidden && e.textContent.trim()); });
  await page.click('#tasks-home .wz [data-a="ok"]');
  const radio = 'input[data-wz-pick][value="memo-own"]';
  await page.waitForSelector(`#tasks-home .wz[data-step="2"] ${radio}`, { timeout: 15000 });
  assert.equal(await page.locator(radio).isChecked(), true, "увімкнене колегою — вибране (initialPick не змінено)");
  assert.equal(await page.locator(radio).isDisabled(), true, "але не перевибирається, доки не довірено");
  assert.equal(await page.locator('[data-wz="trust"][data-id="memo-own"]').count(), 1);
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="3"] .wz-wait', { timeout: 15000 });
  assert.match(await page.locator("#tasks-home .wz-wait").textContent(), /«Memo own \(test\)» чекає довіри/);
  assert.equal(await page.locator('#tasks-home .wz-card[data-id="memo-own"]').count(), 0, "картки нема");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="4"]', { timeout: 15000 });
  assert.deepEqual(posts, [], "жодного запису модулів");
  assert.equal(JSON.parse(readFileSync(path.join(shared, "space.json"), "utf8")).modules["memo-own"].enabled, true);
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

guardRealDeai();

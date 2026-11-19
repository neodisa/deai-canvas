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
 * ловиться — знімок наприкінці її не бачив би) і лічильник адрес запитів та тіл відповідей API. «Свідки» — навмисні
 * витоки на старті кожної сторінки: розмітки (`plantLeak`: кожна гілка спостерігача — нова гілка, атрибут, транзитний
 * атрибут, текст, транзитний текст), адреси запиту й сторінки (`plantUrlLeak`) і запиту назовні (`plantOutside`); без них
 * «жодного витоку» зеленіло б і зі зламаним стеженням. Адреси порівнюються в трьох виглядах (сирий, `encodeURIComponent`,
 * розкодований): Chromium віддає кирилицю секрету як `%D0…`, і порівняння лише з сирим рядком не спрацювало б ніколи.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (вхід і картки)   — пункт `conn` у `ddSpaces` (`shell-bar.js`), `BAR_ACTIONS.conn` і гілка `conn` у `paintHome`
 *        (`app.js`): кожне окремо червонить УСІ сценарії (вхід один — дропдаун); `connFocusPending` (фокус на
 *        картці після входу) — лише сценарій 1.
 *   2 (підключення)     — `missingRequired` до запиту (`cnSubmit`: без нього порожнє поле йде на сервер — червоніють 2 і
 *        5); вердикт ok → бейдж «Підключено» й закриття панелі; запис несе `space`.
 *   3 (заміна)          — `replace = true` у `cnSubmit`: без нього `409 role-taken` і заміни нема (червоніють 3, 5, 6 —
 *        усі, що йдуть через каталог «Замінити …»); `roleHolders` у `catalogGroups`; сервер `_holders` під локом. Секрет — див. нижче.
 *   4 (закриття, Esc)   — Esc-обробник панелі (`requestCloseCnDrawer`); `afterModulesChange` у `connDisable` (без нього картка не міняє бейдж).
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
 * Сценарії ревʼю Task 6–7 (кожен — мутація «прибери виправлення»):
 *   8, 9 (рамка після виходу) — `reloadFrame()` після `render()` у `leaveHome` (стара вада): після запису модулів і
 *        виходу в ІНШУ задачу рамка показувала 404 старого документа, а простий «назад» робив два `/commented`.
 *        Лічильник `load` на `#frame` і мітка документа в рамці (`ЗАДАЧА-2`) — обидва сценарії червоніють.
 *   10–12 (згода на заміну свіжа) — каталог не питає «Замінити?» першого разу (кнопка вже назвала тримача), але тримачі,
 *        що змінились, поки шухляда була відкрита, повертають питання: `cnConfirmReplace`, ігнор свіжого списку (`now = holders`) червонить 10–12; без
 *        відмови «вдруге змінились» — 11 (питає втретє); роль звільнилась → `return true` (шле `replace` власникові, що
 *        зʼявиться між кроками) — 12; тост без `cnToastReplaced` — 3 і 10.
 *   13 (фокус у панелі) — `paintCnDrawer`: без повернення фокуса — 13; без памʼяті `focusWant` (під запитом усе вимкнено,
 *        фокус на хрестику, після відповіді мусить вернутись у поле) — теж 13.
 *   14, 15 (панель проти дій карток) — `connAction`: «Вимкнути» власного модуля без закриття панелі — 14; чужа панель
 *        без закриття попередньої — 15; відмова на «Відкинути?» не зупиняє дію (`await` без `return`) — 14 і 15.
 *   16 (Esc) — `defaultPrevented` у слухачі панелі або `preventDefault` у слухачі дропдауна: без будь-якого одного Esc
 *        закриває і дропдаун, і панель.
 *   17 (логотип, «назад») — `BAR_ACTIONS.home`/`back` без `dismissCnDrawer`: брудну панель губить мовчки.
 *   18 (мова й секрет) — `restoreCnSecrets` у `switchLang`: без нього зміна мови стирає набране.
 *   19 (відмова перечитує список) — `cnRefreshAfterRefusal`: без нього картка й панель бачать колишні прапорці `set`.
 *   6 (відкриття панелі одразу після збереження) — `cnCardBusy(…, true)`: без нього «Налаштувати» відкриває СТАРИЙ запис
 *        (колишнє «задано» після стирання).
 *
 * ⚠️ Стан секрету читаємо ЯКОРЕНИМ: `/^задано ·/`. Голе `/задано/` збігається й із «не задано» — тест 19 тоді лишався
 * зеленим під мутацією «без перечитування» (стан «не задано» проходив як «задано»).
 */
import assert from "node:assert/strict";
import { chmodSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  VIEW, askNo, askYes, badgeClass, pickFromCatalog, guardRealDeai, goTasks, menuAct, menuDisable, openCard, postJson, sleep, stop, waitBadge, waitBarReady, waitGone,
} from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не
   збігається з чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 13400;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules-conn");
const SECRET = "live-S3cret-Жовтень-7";
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
/** Макет із міткою задачі: за нею видно, ЧИЄЇ задачі документ стоїть у рамці. */
const MARKED = (mark) => () => `<!doctype html><html><body><h1 id="mark">${mark}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

/**
 * «Своє» — лише походження сервера, який підняв `boot` (а не будь-який порт 127.0.0.1: чужий локальний сервіс — теж
 * «назовні»). `data:`/`blob:`/`about:` — не мережа.
 */
const localTo = (origin) => {
  const host = new URL(origin).host;
  return (u) => {
    const x = new URL(u);
    if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
    return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && x.host === host;
  };
};

/**
 * Секрет в адресі: сирий, у відсотковому кодуванні чи розкодований. Chromium віддає `request.url()` і `page.url()` ЗАКОДОВАНИМИ
 * (кирилиця секрету → `%D0%9B…`), тож порівняння лише з сирим рядком не спрацювало б ніколи.
 */
const decoded = (u) => { try { return decodeURIComponent(u); } catch { return u; } };
const urlLeak = (u) => u.includes(SECRET) || u.includes(encodeURIComponent(SECRET)) || decoded(u).includes(SECRET);

/**
 * Стеження за витоком секрету в розмітку: кожна мутація DOM, що ПОКЛАЛА `SECRET` у атрибут, текст чи нову гілку,
 * лишає запис у `window.__leaks`. Перевіряється САМ вузол запису (а не поточна розмітка): панель, що на мить
 * мала `value="…"` і одразу очистилась (`innerHTML = ''`), наприкінці вже чиста, а вузол — ще ні. Транзитні атрибут чи текст
 * (поставлено й одразу знято в тому самому завданні: до доставки запису вузол уже чистий) видає `oldValue` наступного
 * запису — тому `attributeOldValue` і `characterDataOldValue` увімкнено.
 */
const watchLeaks = (page) => page.evaluate((secret) => {
  window.__leaks = [];
  const hit = (s) => typeof s === "string" && s.includes(secret);
  new MutationObserver((recs) => {
    for (const r of recs) {
      if (r.type === "attributes") {
        if (hit(r.target.getAttribute(r.attributeName))) window.__leaks.push(`attr:${r.attributeName}`);
        if (hit(r.oldValue)) window.__leaks.push(`attr-old:${r.attributeName}`);
      } else if (r.type === "characterData") {
        if (hit(r.target.data)) window.__leaks.push("text");
        if (hit(r.oldValue)) window.__leaks.push("text-old");
      } else if (r.type === "childList") {
        for (const n of r.addedNodes) if (hit(n.outerHTML ?? n.textContent)) window.__leaks.push(`node:${n.nodeName}`);
      }
    }
  }).observe(document, {
    subtree: true, childList: true, attributes: true, attributeOldValue: true, characterData: true, characterDataOldValue: true,
  });
}, SECRET);

/**
 * Свідок стеження: навмисні витоки КОЖНОЮ з гілок спостерігача (нова гілка, атрибут на живому вузлі, транзитний атрибут,
 * текст на живому вузлі, транзитний текст), які воно мусить побачити; потім знімаються, щоб не отруїти сценарій. Без
 * `attributes`/`characterData` (чи їхніх `…OldValue`) у спостерігача свідок падає саме на своїй гілці.
 */
async function plantLeak(page) {
  const seen = await page.evaluate(async (secret) => {
    const tick = () => new Promise((done) => setTimeout(done, 0));
    const n = document.createElement("i");                   // нова гілка з секретом в атрибуті
    n.setAttribute("data-witness", secret);
    document.body.appendChild(n);
    await tick();
    n.remove();
    const a = document.createElement("i");                   // живий вузол: секрет прийшов ПІЗНІШЕ
    document.body.appendChild(a);
    await tick();
    a.setAttribute("data-live", secret);
    await tick();
    a.setAttribute("data-flash", secret);                    // транзитний атрибут: поставлено й знято в одному завданні
    a.removeAttribute("data-flash");
    await tick();
    const t1 = document.createTextNode("x");                 // живий текст
    a.appendChild(t1);
    await tick();
    t1.data = secret;
    await tick();
    const t2 = document.createTextNode("y");                 // транзитний текст
    a.appendChild(t2);
    await tick();
    t2.data = `${secret}-flash`;
    t2.data = "gone";
    await tick();
    a.remove();
    await tick();
    const got = window.__leaks.slice();
    window.__leaks = [];
    return got;
  }, SECRET);
  for (const want of ["node:I", "attr:data-live", "attr-old:data-flash", "text", "text-old"]) {
    assert.ok(seen.includes(want), `свідок: стеження за витоком не побачило «${want}» — ця гілка спостерігача мертва (бачило: ${seen.join(", ") || "нічого"})`);
  }
}

/**
 * Свідок перевірки адрес: запит і адреса сторінки з секретом (`fetch` на сервер тесту + `#…` в історії) мусять бути видні
 * `urlLeak`; потім слід знімається (з журналу запитів і з адреси сторінки).
 */
async function plantUrlLeak(page, requests) {
  const was = page.url();
  await page.evaluate(async (secret) => {
    await fetch(`/api/spaces?witness=${secret}`);
    history.replaceState(null, "", `#witness=${secret}`);
  }, SECRET);
  assert.ok(requests.some(urlLeak), "свідок: секрет в адресі запиту не видно (кодування URL?) — перевірка адрес мертва");
  assert.ok(urlLeak(page.url()), "свідок: секрет в адресі сторінки не видно — перевірка `page.url()` мертва");
  await page.evaluate((href) => history.replaceState(null, "", href), was);
  requests.splice(0, requests.length, ...requests.filter((u) => !urlLeak(u)));
}

/** Свідок `outside`: запит на ЧУЖИЙ порт 127.0.0.1 і на чужий хост мусить потрапити в журнал; потім журнал чиститься. */
async function plantOutside(page, outside) {
  await page.evaluate(() => Promise.allSettled([
    fetch("http://127.0.0.1:9/witness"), fetch("http://wiz-witness.invalid/witness"),
  ]));
  assert.ok(outside.some((u) => u.startsWith("http://127.0.0.1:9/")), "свідок: чужий порт 127.0.0.1 не записано в `outside`");
  assert.ok(outside.some((u) => u.includes("wiz-witness.invalid")), "свідок: чужий хост не записано в `outside`");
  outside.length = 0;
}

const leaks = (page) => page.evaluate(() => window.__leaks);

/**
 * Сервер + контекст браузера. Контекст рахує КОЖЕН запит (адреси й тіла `POST`), збирає тіла відповідей API й не
 * пускає нічого за межі машини (`route` → `abort`): якщо код колись піде назовні, тест не постукає на справжній
 * хост, а запис у `outside` його видасть. `two` — другий простір («Atelier»), для сценарію зміни простору; `marked` —
 * у «Studio» дві задачі з різними мітками в макеті (`ЗАДАЧА-1` — поточна, `ЗАДАЧА-2` — «Інша»), для сценаріїв про рамку.
 */
async function boot(t, { two = false, marked = false } = {}) {
  const X = taskFixture({ html: marked ? MARKED("ЗАДАЧА-1") : MOCKUP });
  const spaces = [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }];
  if (marked) {
    const Z = taskFixture({ html: MARKED("ЗАДАЧА-2") });
    spaces[0].tasks.t2 = { dir: Z.dir, title: "Інша" };
  }
  if (two) {
    const Y = taskFixture({ html: MOCKUP });
    spaces.push({ name: "Atelier", id: "atelier", color: "space-3", tasks: { t2: { dir: Y.dir, title: "Інша" } } });
  }
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_EXTRA_MODULES: MODULES_DIR }, spaces });
  t.after(() => stop(server.child));
  const isLocal = localTo(server.url);
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
  await waitBarReady(page, 15000);
  await watchLeaks(page);
  await plantLeak(page);
  await plantUrlLeak(page, requests);
  await plantOutside(page, outside);
  return { ...server, page, outside, requests, posts, bodies, errors, spacePath: server.spaces[0].path };
}

const badge = badgeClass;
const spaceJson = (p) => JSON.parse(readFileSync(path.join(p, "space.json"), "utf8"));
/* Явний запис, що фікстура кладе звичайному простору (0.22): до дій тесту `modules` — рівно він, а не `undefined`. */
const STATIC_ONLY = { "static-publish": { enabled: true } };
const secretsJson = (deaiHome) => JSON.parse(readFileSync(path.join(deaiHome, "secrets.json"), "utf8"));
const modulesList = async (url, space = "studio") => (await (await fetch(`${url}/api/modules?space=${space}`)).json()).modules;
const tokenOf = (list, id = "memo-publish") => list.find((m) => m.id === id).settings.find((s) => s.key === "token");

/** Відкрити дропдаун простору й дочекатись РЯДКІВ просторів (перший показ малюється зі старою відповіддю). */
async function openSpaceDd(page, rows = 1) {
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n,
    rows, { timeout: 15000 });
}

/** Вхід: дропдаун простору → «Підключення…» → сторінка з картками. */
async function openConnections(page, rows = 1) {
  await openSpaceDd(page, rows);
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.mc[data-id="static-publish"]', { timeout: 15000 });
}

/** «Додати модуль» → «Замінити …» у каталозі → панель → поля → «Підключити»: питання «Замінити?» нема — кнопка каталогу вже його поставила. */
async function enableMemo(page, { note, token }) {
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', note);
  if (token) await page.fill('#cn-drawer [data-cn-field="token"]', token);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
}

/**
 * Секрет ніде не світиться: ні в розмітці зараз, ні в жодній мутації, ні в адресі запиту чи сторінки (сирий, закодований і
 * розкодований вигляд: Chromium віддає кирилицю у `%D0…`), ні у відповіді API.
 */
async function assertSecretNowhere({ page, requests, posts, bodies }) {
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці (мутація DOM)");
  assert.deepEqual(requests.filter(urlLeak), [], "секрет в адресі запиту");
  assert.ok(!urlLeak(page.url()), "секрет в адресі сторінки");
  assert.ok(posts.some((b) => b.includes(SECRET)), "свідок: секрет мусив піти в тілі POST (інакше «нема в адресі» нічого не варте)");
  assert.ok(bodies.some((b) => b.includes("memo-publish")), "свідок: тіла відповідей API зібрано");
  assert.ok(!bodies.some((b) => b.includes(SECRET)), "секрет у відповіді API");
}

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: вхід із дропдауна, сітка карток, ролі без модуля, явний static-publish (без «типово»), крихта «Налаштування», фокус на картці", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  /* Етап Е: у сітці — лише увімкнений static-publish; вимкнені вбудовані (git-sync, дашборд, трекер, Teams, css-tokens…) — лише в каталозі
     (Task 3), а їхні ролі — пунктирні картки «Без модуля · N» у порядку ROLE_ORDER. */
  assert.deepEqual(await page.locator(".mg .mc:not(.mc--empty)").evaluateAll((els) => els.map((e) => e.dataset.id)), ["static-publish"]);
  assert.deepEqual(await page.locator(".mc--empty").evaluateAll((els) => els.map((e) => e.dataset.role)),
    ["comments", "vcs", "dashboard", "tracker", "notify", "tokens"], "сім ролей, одна з модулем: решта — пунктирні");
  assert.equal(await page.locator("h2.sub").textContent(), "Без модуля · 6");
  assert.equal(await page.locator(".cn-now, .cn-agent, .cn-sec").count(), 0, "рядків «Зараз», блоку «Через агента» й секцій ролей нема");
  assert.match(await page.locator(".th-head h1").textContent(), /Модулі/);
  assert.match(await page.locator('.th-head [data-cn="cat"]').textContent(), /Додати модуль/);
  assert.match(await badge(page, "static-publish"), /bdg--unchecked|bdg--ok/);
  assert.doesNotMatch(await page.locator('.mc[data-id="static-publish"]').textContent(), /типово/, "0.22: static-publish — явний запис, не «типово»");
  assert.equal(await page.locator('.mc[data-id="css-tokens"]').count(), 0, "вимкнений вбудований — не в сітці");
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Налаштування/);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.cn ?? null) !== null, true, "фокус на першій картці");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("2: css-tokens — «Підключити» з файлом простору → «Підключено»; обовʼязкове порожнє — помилка без запиту", async (t) => {
  const { page, spacePath, outside, errors } = await boot(t);
  writeFileSync(path.join(spacePath, "ds.css"), ":root{--c-a:#123456;--gap:4px}");
  await openConnections(page);
  await pickFromCatalog(page, "css-tokens");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('#cn-drawer [aria-invalid="true"]');
  assert.deepEqual(spaceJson(spacePath).modules, STATIC_ONLY, "порожнє обовʼязкове — запиту не було");
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds.css");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "css-tokens", "ok");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "ok — панель закрилась");
  assert.deepEqual(spaceJson(spacePath).modules["css-tokens"], { enabled: true, settings: { file: "{space}/ds.css" } });
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("3: заміна публікації з каталогу — без питання, replace → static-publish вимкнено, memo-publish підключено; секрет ніде не світиться", async (t) => {
  const m = await boot(t);
  const { page, url, spacePath, deaiHome, outside, errors } = m;
  await openConnections(page);
  await pickFromCatalog(page, "memo-publish");
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "memo-publish", "ok");
  await waitGone(page, "static-publish");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "каталог уже сказав «Замінити Публікація в теку» — вдруге не питає");
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Memo publish (test). Вимкнено: Публікація в теку",
    "тост після заміни називає вимкнений модуль");
  const mods = spaceJson(spacePath).modules;
  assert.equal(mods["static-publish"].enabled, false);
  assert.equal(mods["memo-publish"].enabled, true);
  assert.equal(await page.locator('.mc[data-id="static-publish"]').count(), 0, "вимкнений вбудований зник із сітки");
  const tok = tokenOf(await modulesList(url));
  assert.deepEqual(tok, { key: "token", type: "secret", label: "Token (test)", required: false, set: true });
  /* Секрет лежить у сховищі Deai, а не в теці простору. */
  assert.equal(secretsJson(deaiHome).studio["memo-publish"].token, SECRET, "свідок: секрет збережено в secrets.json");
  assert.ok(!readFileSync(path.join(spacePath, "space.json"), "utf8").includes(SECRET), "секрет у space.json");
  await assertSecretNowhere(m);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("4: шухляда з каталогу без запису лишає все як було; Esc із незбереженим питає; вимкнення через питання в картці з наслідком", async (t) => {
  const { page, spacePath, outside, errors } = await boot(t);
  await openConnections(page);
  await pickFromCatalog(page, "memo-publish");
  await page.fill('#cn-drawer [data-cn-field="note"]', "x");
  assert.deepEqual(spaceJson(spacePath).modules, STATIC_ONLY, "поки не натиснуто «Підключити», нічого не записано");
  assert.equal(await page.locator("#cn-drawer").isVisible(), true);
  await page.keyboard.press("Escape");                       // незбережене → питання
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await menuDisable(page, "static-publish");
  assert.match(await page.locator(".mc--ask .cfm-t").textContent(), /кнопки публікації в смузі нема/, "наслідок — у питанні в картці");
  await askYes(page, "static-publish");
  await waitGone(page, "static-publish");
  assert.equal(spaceJson(spacePath).modules["static-publish"].enabled, false);
  assert.equal(await page.locator('.mc--empty[data-role="publish"]').count(), 1, "роль без модуля — пунктирна картка");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("5: перевірка, що каже «ні» — панель лишається з «Збережено, але перевірка не пройшла» і причиною; поле пароля порожнє", async (t) => {
  const m = await boot(t);
  const { page, outside, errors } = m;
  await openConnections(page);
  await pickFromCatalog(page, "memo-publish");
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
  await page.waitForSelector("#cn-drawer .cn-res--err");
  const txt = await page.locator("#cn-drawer .cn-res--err").textContent();
  assert.match(txt, /Збережено, але перевірка не пройшла/);
  assert.match(txt, /memo-says-no — note is fail/);
  assert.ok(!txt.includes("Перевірка не пройшла"), "загальний рядок після голови не повторюється");
  assert.match(await page.locator('#cn-drawer [data-cn-dr="submit"]').textContent(), /Зберегти/, "далі — режим правки");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="token"]'), "", "після відповіді сервера поле пароля порожнє");
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /^задано ·/, "секрет збережено, стан — «задано»");
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

  await openCard(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="erase"]');
  const erase = page.locator('#cn-drawer [data-cn-dr="erase"]');
  const note = page.locator('#cn-drawer [data-cn-erase-note="token"]');
  const save = page.locator('#cn-drawer [data-cn-dr="submit"]');
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /^задано ·/);
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

  /* Панель, відкрита знову ОДРАЗУ (без перезавантаження й очікування): «не задано», кнопки «Стерти» вже нема. Картка
     зайнята (`'save'`) до кінця перечитування списку, тож «Налаштувати» не відкриє СТАРИЙ запис із «задано»: клік
     Playwright чекає, поки кнопка знову доступна (ревʼю: без цього тут було колишнє «задано»). */
  await openCard(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="token"]');
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /^не задано ·/);
  assert.equal(await page.locator('#cn-drawer [data-cn-dr="erase"]').count(), 0);
  await assertSecretNowhere(m);
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
  assert.match(await page.locator(".set-nav h6").first().textContent(), /Простір · Studio/);
  assert.equal(await page.locator('.mc[data-id="memo-publish"]').count(), 0, "у Studio memo-publish вимкнено — не в сітці");
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "незбережене");      // брудна форма: у «Studio» питали б

  await openSpaceDd(page, 2);
  await page.click('.dd--spaces .dd-item[data-val="atelier"]');
  await page.waitForFunction(() => /Atelier/.test(document.querySelector(".set-nav h6")?.textContent ?? ""), null, { timeout: 15000 });
  await page.waitForSelector('.mc[data-id="memo-publish"]', { timeout: 15000 });
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "панель з чужого простору не лишилась");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "перехід свідомий — питання «Відкинути?» нема");
  assert.match(await page.locator(".set-nav h6").first().textContent(), /Простір · Atelier/, "навігація — нового простору");
  assert.match(await badge(page, "memo-publish"), /bdg--unchecked/, "картки — нового простору (memo-publish там увімкнено)");
  assert.equal(readFileSync(path.join(atelier.path, "space.json"), "utf8"), atelierBefore, "у новий простір нічого не записано");
  assert.deepEqual(spaceJson(studio.path).modules, STATIC_ONLY, "у старий простір теж");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

/* ── сценарії ревʼю Task 6–7: рамка, згода на заміну, фокус, панель проти дій карток ─────────────────────────────── */

/** Лічильник подій `load` рамки задачі (слухач на елементі `#frame` переживає навігації документа в ній). */
const countFrameLoads = (page) => page.evaluate(() => {
  window.__frameLoads = 0;
  document.getElementById("frame").addEventListener("load", () => { window.__frameLoads += 1; });
});
const frameLoads = (page) => page.evaluate(() => window.__frameLoads);
/** Мітка документа в рамці (`ЗАДАЧА-…`); `null`, коли документа з міткою нема (404, порожньо). */
const frameMark = (page) => page.evaluate(() => document.getElementById("frame").contentDocument?.getElementById("mark")?.textContent ?? null);
const commentedRequests = (requests) => requests.filter((u) => u.includes("/commented?")).length;

/** Вимкнути `static-publish` карткою (запис модулів, що змінює постачальника публікації й, отже, документ рамки). */
async function disableStaticPublish(page) {
  await menuDisable(page, "static-publish");
  await askYes(page, "static-publish");
  await waitGone(page, "static-publish");
}

test("8: запис модулів → логотип → ІНША задача: рамка показує нову задачу (не 404), рівно одне завантаження", async (t) => {
  const { page, requests, outside, errors } = await boot(t, { marked: true });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.getElementById("mark")?.textContent === "ЗАДАЧА-1",
    null, { timeout: 15000 });
  await openConnections(page);
  await disableStaticPublish(page);
  await countFrameLoads(page);
  const before = commentedRequests(requests);
  await page.click('#tabs [data-act="home"]');
  await page.click('#tasks-home .th-card[data-id="t2"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.getElementById("mark")?.textContent === "ЗАДАЧА-2",
    null, { timeout: 15000 });
  await sleep(500);                                          // другого завантаження (старого документа) не мусить бути
  assert.equal(await frameMark(page), "ЗАДАЧА-2", "у рамці — документ нової задачі, а не 404 старого");
  assert.equal(await frameLoads(page), 1, "рамка завантажилась рівно один раз після виходу");
  assert.equal(commentedRequests(requests) - before, 1, "рівно один запит /commented");
  assert.equal(await page.locator("#bar .crumb--title .txt").textContent(), "Інша", "смуга й рамка — про одну задачу");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("9: запис модулів → логотип → «назад до задачі»: один запит /commented й одне завантаження рамки (було два)", async (t) => {
  const { page, requests, outside, errors } = await boot(t, { marked: true });
  await openConnections(page);
  await disableStaticPublish(page);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await countFrameLoads(page);
  const before = commentedRequests(requests);
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.getElementById("mark")?.textContent === "ЗАДАЧА-1",
    null, { timeout: 15000 });
  await sleep(500);
  assert.equal(await frameLoads(page), 1, "рамка завантажилась рівно один раз");
  assert.equal(commentedRequests(requests) - before, 1, "рівно один запит /commented");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

/**
 * Каталог → шухляда memo-publish («Замінити Публікація в теку») → `note` → поки шухляда відкрита, «агент» (API) займає роль
 * модулем memo-publish2 → «Підключити»: список сторінки застарілий, а свіжий каже, що тримач інший, — питання «Замінити?» з'являється
 * вже про НОВОГО тримача (кнопка каталогу називала іншого).
 */
async function askReplaceMemo(page, url) {
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  const taken = await postJson(url, "/api/module-enable", { space: "studio", id: "memo-publish2", settings: { note: "x" }, replace: true });
  assert.equal(taken.status, 200);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
}
const askText = (page) => page.locator(".cv-ask-scrim").textContent();
const waitAskNames = (page, name) => page.waitForFunction(
  (n) => (document.querySelector(".cv-ask-scrim")?.textContent ?? "").includes(n), name, { timeout: 15000 });
/** Тіла `POST`, що несуть запис САМЕ цього модуля (`"id":"memo-publish"` із закривною лапкою — не `memo-publish2`). */
const postsFor = (posts, id) => posts.filter((b) => b.includes(`"id":"${id}"`));

test("10: згода на заміну СВІЖА — роль заняли, поки шухляда з каталогу відкрита: питання про нового тримача, до «так» нічого не пишеться", async (t) => {
  const { page, url, spacePath, posts, outside, errors } = await boot(t);
  await openConnections(page);
  await askReplaceMemo(page, url);
  assert.match(await askText(page), /Memo publish 2 \(test\)/, "питання — про того, хто тримає роль зараз");
  assert.doesNotMatch(await askText(page), /Публікація в теку/, "а не про того, кого називала кнопка каталогу");
  const mods = spaceJson(spacePath).modules;
  assert.equal(mods["memo-publish"], undefined, "до «так» панель нічого не записала");
  assert.equal(mods["memo-publish2"].enabled, true);
  assert.equal(postsFor(posts, "memo-publish").length, 0, "жодного запису memo-publish із панелі");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "memo-publish", "ok");
  await waitGone(page, "memo-publish2");
  const after = spaceJson(spacePath).modules;
  assert.equal(after["memo-publish"].enabled, true);
  assert.equal(after["memo-publish2"].enabled, false);
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Memo publish (test). Вимкнено: Memo publish 2 (test)",
    "тост називає саме того, кого вимкнули насправді");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("10b: «Скасувати» на питанні про нового тримача — нічого не записано, шухляда лишається з введеним", async (t) => {
  const { page, url, spacePath, posts, outside, errors } = await boot(t);
  await openConnections(page);
  await askReplaceMemo(page, url);
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(spaceJson(spacePath).modules["memo-publish"], undefined, "скасування — нічого не записано");
  assert.equal(postsFor(posts, "memo-publish").length, 0);
  assert.equal(await page.locator("#cn-drawer").isVisible(), true, "шухляда лишилась");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="note"]'), "hello", "введене не втрачено");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("11: тримачі змінились ще раз, поки питання відкрите — відмова «роль уже зайнята», нічого не записано; повтор іде без питання (тримач той, кого називала кнопка)", async (t) => {
  const { page, url, spacePath, posts, outside, errors } = await boot(t);
  await openConnections(page);
  await askReplaceMemo(page, url);
  /* Поки відкрите питання про memo-publish2, роль міняє власника ще раз (static-publish вертається). */
  const again = await postJson(url, "/api/module-enable", { space: "studio", id: "static-publish", settings: {}, replace: true });
  assert.equal(again.status, 200);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer .cn-res--err");
  assert.match(await page.locator("#cn-drawer .cn-res--err").textContent(), /Роль уже зайнята іншим модулем/);
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "третього питання нема");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="note"]'), "hello", "введене лишилось у панелі");
  assert.equal(spaceJson(spacePath).modules["memo-publish"], undefined, "нічого не записано");
  assert.equal(postsFor(posts, "memo-publish").length, 0, "жодного запису memo-publish із панелі");
  /* Повтор: список свіжий, тримач знову той, кого називала кнопка каталогу, — отже замінюємо його без питання. */
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "memo-publish", "ok");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "кнопка каталогу вже називала static-publish");
  assert.equal(spaceJson(spacePath).modules["static-publish"].enabled, false);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("12: роль звільнилась, поки питання відкрите — запис іде БЕЗ replace (власник, що зʼявиться між кроками, не вимкнеться мовчки)", async (t) => {
  const { page, url, posts, outside, errors } = await boot(t);
  await openConnections(page);
  await askReplaceMemo(page, url);
  const freed = await postJson(url, "/api/module-disable", { space: "studio", id: "memo-publish2" });
  assert.equal(freed.status, 200);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "memo-publish", "ok");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "питати нема про що");
  const mine = postsFor(posts, "memo-publish");
  assert.equal(mine.length, 1);
  assert.equal(JSON.parse(mine[0]).replace, undefined, "replace не надіслано");
  assert.equal(await page.locator("#cv-toast").textContent(), "Підключено: Memo publish (test)", "заміни не було — «Вимкнено» нема");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("13: фокус у панелі — клавіатурне збереження з невдалою перевіркою лишає фокус на тому самому контролі, і під запитом теж усередині панелі", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  /* Запит затримано: видно стан «зайнято» (усе вимкнено), де фокусу нема на чому стояти. */
  await page.route("**/api/module-enable", async (route) => { await sleep(700); await route.continue(); });
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.focus('#cn-drawer [data-cn-field="note"]');
  await page.keyboard.type("fail");
  await page.keyboard.press("Enter");                        // клавіатурне «Підключити»
  await page.waitForFunction(() => document.querySelector('#cn-drawer [data-cn-dr="submit"]')?.disabled === true, null, { timeout: 15000 });
  const busy = await page.evaluate(() => ({ inside: !!document.activeElement?.closest("#cn-drawer"), dr: document.activeElement?.dataset?.cnDr ?? null }));
  assert.deepEqual(busy, { inside: true, dr: "close" }, "під запитом усе вимкнено — фокус на хрестику, а не на body");
  await page.waitForSelector("#cn-drawer .cn-res--err");
  const done = await page.evaluate(() => ({ inside: !!document.activeElement?.closest("#cn-drawer"), field: document.activeElement?.dataset?.cnField ?? null }));
  assert.deepEqual(done, { inside: true, field: "note" }, "після невдалої перевірки фокус там, де людина була (поле), а не на body чи хрестику");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

/** `css-tokens` увімкнено з `{space}/ds.css`; панель закрита, картка вільна. */
async function connectCssTokens(page, spacePath) {
  writeFileSync(path.join(spacePath, "ds.css"), ":root{--c-a:#123456;--gap:4px}");
  await pickFromCatalog(page, "css-tokens");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds.css");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "css-tokens", "ok");
}
const openCssConfig = async (page) => {
  await openCard(page, "css-tokens");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
};
const drawerTitle = (page) => page.locator("#cn-dr-title").textContent();

test("14: «Вимкнути» в меню картки модуля з відкритою панеллю — панель спершу закривається (з питанням, коли брудна); module-settings не летить", async (t) => {
  const { page, spacePath, requests, outside, errors } = await boot(t);
  await openConnections(page);
  await connectCssTokens(page, spacePath);

  /* Чиста панель: без питання «Відкинути?» — одразу питання в картці; відмова лишає модуль увімкненим, панель закрито. */
  await openCssConfig(page);
  await menuAct(page, "css-tokens", "disable");
  await page.waitForSelector('.mc--ask[data-id="css-tokens"]');
  assert.match(await page.locator('.mc--ask[data-id="css-tokens"] .cfm-t').textContent(), /Вимкнути «Токени з CSS»/, "чиста панель — питання про вимкнення, не про відкидання");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0);
  await askNo(page, "css-tokens");
  await page.waitForSelector(".mc--ask", { state: "detached" });
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "панель вимкненого модуля не лишилась");
  assert.equal(spaceJson(spacePath).modules["css-tokens"].enabled, true);

  /* Брудна панель: спершу «Відкинути?» (відмова лишає все), потім питання в картці. */
  await openCssConfig(page);
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds2.css");
  await menuAct(page, "css-tokens", "disable");
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await askText(page), /Відкинути/);
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await page.locator("#cn-drawer").isVisible(), true, "відмова — панель лишилась");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="file"]'), "{space}/ds2.css", "набране збережено");
  assert.equal(spaceJson(spacePath).modules["css-tokens"].enabled, true, "відмова — модуль увімкнений");
  assert.equal(await page.locator(".mc--ask").count(), 0, "відмова — питання в картці не відкрилось");
  await menuAct(page, "css-tokens", "disable");
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');       // відкинути
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await page.waitForSelector('.mc--ask[data-id="css-tokens"]', { timeout: 15000 });
  assert.match(await page.locator('.mc--ask .cfm-t').textContent(), /Вимкнути «Токени з CSS»/);
  await askYes(page, "css-tokens");                            // вимкнути
  await waitGone(page, "css-tokens");
  assert.deepEqual(spaceJson(spacePath).modules["css-tokens"], { enabled: false, settings: { file: "{space}/ds.css" } },
    "вимкнено, налаштування — як були (брудна правка не збережена)");
  assert.equal(requests.filter((u) => u.includes("/api/module-settings")).length, 0, "module-settings не летів ні разу");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("15: інша панель поверх відкритої — з питанням, коли брудна (відмова лишає першу); чиста замінюється мовчки", async (t) => {
  const { page, spacePath, outside, errors } = await boot(t);
  await openConnections(page);
  await connectCssTokens(page, spacePath);
  await openCssConfig(page);
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds2.css");
  await pickFromCatalog(page, "memo-publish", { dom: true });
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await askText(page), /Відкинути/);
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await drawerTitle(page), "Токени з CSS", "відмова — перша панель на місці");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="file"]'), "{space}/ds2.css", "набране збережено");
  await pickFromCatalog(page, "memo-publish", { dom: true });
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForFunction(() => document.getElementById("cn-dr-title")?.textContent === "Memo publish (test)", null, { timeout: 15000 });
  assert.equal(await page.locator('#cn-drawer [data-cn-field="note"]').count(), 1, "відкрилась панель другого модуля");
  /* Чиста панель замінюється без питання. */
  await openCard(page, "css-tokens");
  await page.waitForFunction(() => document.getElementById("cn-dr-title")?.textContent === "Токени з CSS", null, { timeout: 15000 });
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "чиста панель — без питання");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="file"]'), "{space}/ds.css", "відкрито збережене, а не колишнє набране");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("16: Esc закриває ЛИШЕ дропдаун смуги, коли він відкритий; наступний Esc — панель", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  await pickFromCatalog(page, "css-tokens");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="file"]');
  await openSpaceDd(page);
  await page.keyboard.press("Escape");
  await page.waitForSelector(".dd--spaces", { state: "detached" });
  assert.equal(await page.locator("#cn-drawer").isVisible(), true, "Esc закрив дропдаун — панель за той самий Esc не закрилась");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("17: логотип і «назад до задачі» з брудною панеллю питають «Відкинути?»; з чистою — йдуть одразу", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  /* Брудна панель + логотип: відмова лишає панель і набране; згода — «Задачі» без панелі. */
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "x");
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await askText(page), /Відкинути/);
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await page.locator("#cn-title").count(), 1, "відмова — лишились на «Підключенні»");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="note"]'), "x", "набране збережено");
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator("#cn-title").count(), 0, "згода — на «Задачах»");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true);
  /* «Назад до задачі» з брудною панеллю — те саме. */
  await page.click('#tasks-home [data-th="conn"]');
  await page.waitForSelector('.mc[data-id="static-publish"]');
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "y");
  await page.click('#tabs [data-act="tab"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await askText(page), /Відкинути/);
  assert.equal(await page.evaluate(() => document.body.classList.contains("home-open")), true, "поки питання — екран на місці");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  /* Чиста панель: без питання. */
  await page.click('#tabs [data-act="home"]');
  await page.click('#tasks-home [data-th="conn"]');
  await page.waitForSelector('.mc[data-id="static-publish"]');
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "чиста панель — без питання");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("18: зміна мови не стирає набраний секрет: він лишається ВЛАСТИВІСТЮ поля, у розмітку не потрапляє", async (t) => {
  const m = await boot(t);
  const { page, outside, errors } = m;
  await openConnections(page);
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="token"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "english");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length === 1, null, { timeout: 5000 });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector('#cn-drawer [data-cn-dr="submit"]')?.textContent === "Connect", null, { timeout: 15000 });
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="token"]'), SECRET, "секрет пережив перемальовку мовою");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="note"]'), "hello", "і значення полів теж");
  assert.ok(!(await page.locator("#cn-drawer").evaluate((n) => n.outerHTML)).includes(SECRET), "секрет у розмітці панелі");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці (мутація DOM)");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("19: відмовлений запис теж перечитує список: секрет, записаний до відмови, видно при наступному відкритті панелі",
  { skip: process.getuid?.() === 0 && "root ігнорує права на теку — `unwritable` не відтворити" }, async (t) => {
  const { page, deaiHome, spacePath, outside, errors } = await boot(t);
  await openConnections(page);
  /* Тека простору лише для читання: секрет (у `<DEAI_HOME>`) запишеться, а `space.json` — ні (`unwritable`, 500). */
  chmodSync(spacePath, 0o555);
  t.after(() => { try { chmodSync(spacePath, 0o755); } catch { /* вже прибрано */ } });
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="note"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector("#cn-drawer .cn-res--err");
  assert.match(await page.locator("#cn-drawer .cn-res--err").textContent(), /Не вдалося записати space\.json/, "HTTP-відмова, а не вердикт перевірки");
  assert.equal(secretsJson(deaiHome).studio["memo-publish"].token, SECRET, "свідок: сервер записав секрет ДО відмови");
  assert.deepEqual(spaceJson(spacePath).modules, STATIC_ONLY, "space.json не записано");
  await page.keyboard.press("Escape");                       // панель брудна: питання «Відкинути?»
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await pickFromCatalog(page, "memo-publish");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="token"]');
  assert.match(await page.locator("#cn-drawer .cn-secret").textContent(), /^задано ·/, "список перечитано після відмови: секрет уже є");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

guardRealDeai();

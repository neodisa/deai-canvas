/**
 * Майстер нового простору (Deai 0.6.0, етап 3b) — живе проведення: справжній сервер в ізольованій «машині» (тимчасові
 * `HOME`/`DEAI_HOME`), справжній Chromium. Модулі-фікстури `memo-publish`/`memo-publish2` (`tests/fixtures/modules-conn`,
 * шов `DEAI_EXTRA_MODULES`) — роль `publish` з ЛОКАЛЬНОЮ перевіркою: жодної мережі. Vercel і Supabase не вмикаються.
 * Третій модуль, `memo-note` (роль `notify`, необовʼязкове поле з типовим значенням), народжується тут же, у тимчасовій теці
 * поряд із копіями двох перших: у `modules-conn` його класти не можна — ту теку читає й екран «Підключення» (`connections.test.mjs`).
 *
 * Юніти (`tests/wizard-*.test.mjs`) і сервер (`tests/test_task_from.py`) доводять ланки окремо; тут — те, що живе лише в
 * браузері: входи, перехід кроків і фокус, запис модулів зі «свіжістю», секрет лише у властивості поля, задача з теки
 * до рамки макета.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє; кожна мутація — один рядок
 * застосунку, файл відновлено побайтно). Файли: `w` = `app/wizard.js`, `m` = `app/wizard-model.js`, `v` = `app/wizard-view.js`,
 * `a` = `app/app.js`, `s` = `app/serve.py`.
 *   W1  (перший запуск, заміна, секрет)
 *        `replace` у `runOp` (`op.op === "enable"` → `false`, w): 409 `role-taken` — червоніють W1, W8, W10;
 *        `missingRequired` у `submit3` (w) — W1 («помилка без запиту» стає запитом);
 *        повернення секретів у `paint` (цикл `keep.secrets`, w) — W1 (секрет зник після відмови) і W8;
 *        `initialPick` (m, порожній) — W1 (початково вибраний постачальник), а з ним W2, W7, W9;
 *        підпис «замість …» (`instead` у `optionHTML`, v) — W1; фокус на заголовку кроку (`focusStep`, w) — W1;
 *        легкий шлях після запису (`afterModulesChange`, w) — ЖИВОГО свідка нема, див. «Вижили» нижче.
 *   W2  (меню → «Client» → задача з теки)
 *        `from` не йде в `task-new` (w) і тост про пропущені посилання (`wzSkippedLinks`, w) — W2; сервер: пропуск
 *        символьних посилань і в обході (`adopt_scan`), і в копії (`adopt_copy`) разом (s) — W2 (кожен шар окремо: обхід —
 *        `tests/test_task_from.py::test_a_dangling_symlink_is_counted_as_a_skipped_link`, копія — тести «swapped for a link»);
 *        пункт «Новий простір…» дропдауна (`spacenew`, a) — W2, W3.
 *   W3  (крок 1: відмова, «Скасувати», зайнята форма)
 *        `wizBack`: без `leaveHome` (a) — W3 (оверлей лишається); прибирання `.wz` у `leaveHome` (a) — W3 (розмітка лишається
 *        в схованому оверлеї); `setBusy` не вимикає контролів (w) — W3 (і T6 у `spaces-flows`); `showError` без
 *        `aria-invalid`/фокуса (w) — W3 (і T6b).
 *   W4  (назад на крок 1, перейменування, «Закрити майстер»)
 *        «без змін — без `space-update`» (w), режим правки кроку 1 (`edit` у `step1HTML`, v), тост `wzReady` (w) — W4.
 *   W5  (незбережене на кроці 3)
 *        `askDiscard` у `requestExit` (w) — W5; `askDiscard` у `back` (w) — W5; `dirty()` (завжди false, w) — W5.
 *   W6  (свіжість і незалежність записів)
 *        `op.stale.length` у `runOp` (w) — W6; назви нових тримачів у відмові (`detail`, w) — W6; відмова одного запису не
 *        зупиняє інших (`break` після `refused`, w) — W6.
 *   W7  (наявна тека простору з привітання)
 *        фокус у теці (`folderFirst` у `focusStep`, w) і кнопка `spaceopen` (a) — W7; `initialPick` — W7.
 *   W8  (збій читання списку на старті збереження)
 *        тост `cnErrLoad` (w) і «не стирати картки» (`s3failed` замість тосту, w) — W8; повернення секретів — W8.
 *   W9  (Назад під час перевірки id) — повторна перевірка кроку (`mine.step !== 4`, w) — W9.
 *   W10 (збережена картка не «змінена») — `fresh` у `capture` (w) — W10; `allOk` (завжди true, w) — W10, W6, W11, W12.
 *   W11 (помилка видима) — `focus({preventScroll})` після відмови (w) — W11.
 *   W12 (відмова сервера очищає поле пароля) — `clearSecrets` (w) — ЛИШЕ W12: у записаної картки (`fresh`) `capture` не читає
 *        DOM, тож поле й так порожнє, а секрет переживає перемальовку тільки в картки, чий запис відмовлено.
 *   W13 (перемальовка кроку 1 мовою) — `pathTouched` у `wire` (w) — W13.
 *   W14 («Без модуля») — рядки «вимкнеться» (`offRows` у `writePlan`, m; `mine.offs`, w) — W14 (disable не йде / рядка нема);
 *        вхід із привітання (`spacenew` у `wireHome`, a) — W1, W4–W6, W8–W14 (W2 і W3 входять із меню, W7 — `spaceopen`).
 *
 * Вижили (чесно): (1) прибирання `.wz` у `enterHome` при виході з `wiz` (a) — поведінково зайве: наступним рядком той самий
 * `enterHome` синхронно перемальовує сторінку (`paintHome`), тож жодного кадру з секретом не буває (кадри від «Відкинути»
 * в W5 це міряють); стереже юніт `tests/wizard-wiring.test.mjs` («8а …»). (2) `afterModulesChange` після проходу кроку 3 (w) —
 * кожен вихід із майстра (створення задачі, «Закрити майстер», «Підключення») сам перечитує простори й перемальовує смугу,
 * тож проміжний стан непомітний; стережуть `tests/wizard-wiring.test.mjs` («після будь-якого успішного запису модулів …»)
 * і сам легкий шлях 3a (`connections.test.mjs`, 3).
 */
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, postJson, sleep, spacesApi, stop, text, waitText } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не збігається з
   чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 13500;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CONN_MODULES = path.join(ROOT, "tests", "fixtures", "modules-conn");
const SECRET = "wiz-S3cret-Листопад-9";
const MOCKUP = (page) => `<!doctype html><html><body><h1>${page}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── модулі-фікстури ───────────────────────────────────────────────────────────────────────────────── */

/**
 * Тека `DEAI_EXTRA_MODULES` цього файла: копії `memo-publish`/`memo-publish2` + `memo-note`. `memo-note` — роль `notify`
 * (зарезервована: каталог її приймає, а екран лише показує звичайною секцією), одне НЕобовʼязкове текстове поле `label` з
 * типовим значенням `dflt-label`. Очистити його — «ключ знімається, діє типове»: сервер у відповіді віддає саме типове,
 * і це єдиний спосіб побачити живцем, що картка після запису бере значення З СЕРВЕРА, а не зі старого DOM.
 */
let modulesDir;
function wizardModules() {
  if (modulesDir) return modulesDir;
  modulesDir = mkdtempSync(path.join(tmpdir(), "dc-wiz-mods-"));
  cpSync(CONN_MODULES, modulesDir, { recursive: true });
  const dir = path.join(modulesDir, "memo-note");
  mkdirSync(dir);
  writeFileSync(path.join(dir, "module.json"), JSON.stringify({
    api: 1, id: "memo-note", name: "Memo note (test)", version: "1.0.0", roles: ["notify"],
    settings: [{ key: "label", type: "text", label: "Label (test)", default: "dflt-label" }],
  }));
  writeFileSync(path.join(dir, "server.py"),
    "def check(ctx):\n    return {'ok': True, 'detail': 'note ok'}\n");
  return modulesDir;
}

/* ── прилади (стеження за витоком — дослівно з connections.test.mjs) ───────────────────────────────── */

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
 * Сервер (+ простори, коли дано) і сторінка; лічильники запитів і тіл відповідей API; нічого назовні (`route` → `abort`:
 * якщо код колись піде назовні, тест не постукає на справжній хост, а запис у `outside` його видасть).
 */
async function boot(t, { spaces = [], viewport = VIEW } = {}) {
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_EXTRA_MODULES: wizardModules() }, spaces });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport });
  t.after(() => context.close());
  const outside = [];
  const requests = [];
  const posts = [];
  const bodies = [];
  context.on("request", (r) => {
    requests.push(r.url());
    if (r.method() === "POST") posts.push({ url: r.url(), body: r.postData() ?? "" });
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
  await page.waitForSelector(spaces.length ? "#bar .space-chip" : "#tasks-home .th-welcome", { timeout: 15000 });
  await watchLeaks(page);
  await plantLeak(page);
  return { ...server, page, outside, requests, posts, bodies, errors };
}

/** Простір «Studio» з однією задачею `t1` (для сценаріїв «з меню»). */
const studio = () => [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: taskFixture({ html: MOCKUP }).dir, title: "Задача" } } }];

const step = (page, n) => page.waitForSelector(`#tasks-home .wz[data-step="${n}"]`, { timeout: 15000 });
const next = (page) => page.click('#tasks-home .wz [data-a="ok"]');
const back = (page) => page.click('#tasks-home .wz [data-wz="back"]');
const activeId = (page) => page.evaluate(() => document.activeElement?.id ?? null);
const spaceJson = (p) => JSON.parse(readFileSync(path.join(p, "space.json"), "utf8"));
const secretsJson = (deaiHome) => JSON.parse(readFileSync(path.join(deaiHome, "secrets.json"), "utf8"));
const postsTo = (posts, p) => posts.filter((x) => new URL(x.url).pathname === p);
const card = (id) => `#tasks-home .wz-card[data-id="${id}"]`;
const field = (id, key) => `${card(id)} [data-cn-field="${key}"]`;
const pick = (id) => `#tasks-home input[data-wz-pick][value="${id}"]`;
const askText = (page) => page.locator(".cv-ask-scrim").textContent();
const waitToast = (page, re) => page.waitForFunction(
  (src) => new RegExp(src).test(document.getElementById("cv-toast")?.textContent ?? ""), re.source, { timeout: 15000 });
/** Поля пароля з непорожнім значенням (секрет у DOM — лише властивістю `.value`). */
const pwWithValue = (page) => page.evaluate(() => [...document.querySelectorAll('input[type="password"]')].filter((n) => n.value !== "").length);

/** «Новий простір…» з дропдауна фішки (дочекатись рядків — перший показ малюється зі старою відповіддю). */
async function openFromMenu(page, rows = 1) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n, rows);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await step(page, 1);
}

/** Перший запуск: привітання → «Створити простір» → «Далі» → крок 2 з картками. */
async function firstSpace(page) {
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await step(page, 1);
  await next(page);
  await step(page, 2);
  await page.waitForSelector(pick("memo-publish"));
}

/** Крок 2 → вибрати модулі → «Далі» → крок 3 з картками вибраних. */
async function pickAndNext(page, ids) {
  for (const id of ids) await page.locator(pick(id)).check();
  await next(page);
  await step(page, 3);
  for (const id of ids) await page.waitForSelector(card(id));
}

/** Секрет ніде не світиться: ні в розмітці зараз, ні в жодній мутації, ні в адресі, ні у відповіді API. */
async function assertSecretNowhere({ page, requests, posts, bodies }) {
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці (мутація DOM)");
  assert.ok(!requests.some((u) => u.includes(SECRET)), "секрет в адресі запиту");
  assert.ok(posts.some((x) => x.body.includes(SECRET)), "свідок: секрет мусив піти в тілі POST (інакше «нема в адресі» нічого не варте)");
  assert.ok(bodies.some((b) => b.includes("memo-publish")), "свідок: тіла відповідей API зібрано");
  assert.ok(!bodies.some((b) => b.includes(SECRET)), "секрет у відповіді API");
}

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("W1: перший запуск — «Особисте», заміна постачальника («замість…»), секрет лише у властивості поля, відмова без запиту, задача «Onboarding»", async (t) => {
  const m = await boot(t);
  const { page, url, deaiHome, posts, outside, errors } = m;
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await step(page, 1);
  assert.equal(await page.inputValue("#sp-name"), "Особисте");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/personal");
  assert.equal(await activeId(page), "sp-name", "фокус на назві простору");
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Новий простір/);
  assert.equal(await page.locator("#bar .space-chip").count(), 0, "фішки простору на сторінці майстра нема");

  await next(page);
  await step(page, 2);
  await page.waitForSelector(pick("memo-publish"));
  assert.equal(await activeId(page), "wz-h", "новий крок — фокус на заголовку");
  const reg = await spacesApi(url);
  assert.equal(reg.spaces.length, 1, "простір створено на кроці 1");
  const spaceId = reg.spaces[0].id;
  const spPath = reg.spaces[0].path;
  assert.equal(await page.locator(pick("static-publish")).isChecked(), true, "початково вибрано поточного постачальника");
  assert.match(await page.locator(`#tasks-home .wz-opt:has(input[value="memo-publish"])`).textContent(), /замість «Публікація в теку»/);
  await page.locator(pick("memo-publish")).check();
  assert.equal(await page.locator(pick("static-publish")).isChecked(), false, "вибір заміни знімає колишнього");
  await next(page);
  await step(page, 3);
  await page.waitForSelector(card("memo-publish"));
  assert.match(await page.locator(`${card("memo-publish")} .cn-badge`).textContent(), /Буде підключено/);

  /* Секрет введено, обовʼязкове `note` порожнє: помилка під полем, жодного запиту, секрет ЛИШИВСЯ у властивості поля. */
  await page.fill(field("memo-publish", "token"), SECRET);
  const before = posts.length;
  await next(page);
  await page.waitForSelector(`${card("memo-publish")} .cn-field-err`);
  assert.equal(posts.length, before, "відмова на обовʼязковому полі — запитів не було");
  assert.equal(await page.inputValue(field("memo-publish", "token")), SECRET, "введений секрет лишився в полі");
  assert.ok(!(await page.locator(card("memo-publish")).evaluate((n) => n.outerHTML)).includes(SECRET), "секрет у розмітці картки");

  await page.fill(field("memo-publish", "note"), "ok");
  await next(page);
  await step(page, 4);

  const mods = spaceJson(spPath).modules;
  assert.equal(mods["memo-publish"].enabled, true);
  assert.equal(mods["static-publish"].enabled, false, "заміна вимкнула колишнього постачальника");
  assert.equal(secretsJson(deaiHome)[spaceId]["memo-publish"].token, SECRET, "свідок: секрет збережено в secrets.json");
  assert.ok(!readFileSync(path.join(spPath, "space.json"), "utf8").includes(SECRET), "секрет у space.json");
  const enables = postsTo(posts, "/api/module-enable");
  assert.equal(enables.length, 1, "заміна — рівно один запис");
  const body = JSON.parse(enables[0].body);
  assert.equal(body.replace, true, "заміна атомарна: replace");
  assert.equal(body.space, spaceId, "запис несе простір майстра");
  assert.equal(body.id, "memo-publish");
  assert.equal(postsTo(posts, "/api/module-disable").length, 0, "колишнього вимкнув сам replace, окремого disable нема");

  await page.fill("#tf-title", "Onboarding");
  assert.equal(await page.inputValue("#tf-id"), "onboarding");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  assert.equal((await (await fetch(`${url}/api/tasks`)).json()).current, "onboarding");
  await waitText(page, "#bar .space-name", "Особисте");
  /* Легкий шлях після запису (`afterModulesChange`): оболонка знає нового постачальника, а не лише той, що був при створенні. */
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces [data-act="conn"]');
  await page.click('.dd--spaces [data-act="conn"]');
  await page.waitForSelector(`.cn-card[data-id="memo-publish"]`);
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: Memo publish \(test\)/);
  await assertSecretNowhere(m);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W2: меню → «Client» → задача з наявної теки: символьне посилання пропущено (тост), копія в it1, макет у рамці", async (t) => {
  const m = await boot(t, { spaces: studio() });
  const { page, url, home, posts, outside, errors } = m;
  /* Тека-джерело: макет, картинка й символьне посилання на файл ПОЗА текою. */
  const src = path.join(home, "mock-landing");
  mkdirSync(path.join(src, "img"), { recursive: true });
  writeFileSync(path.join(src, "index.html"), '<!doctype html><html><body><h1 id="mark">LANDING</h1></body></html>');
  writeFileSync(path.join(src, "img", "a.svg"), '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>');
  writeFileSync(path.join(home, "outside.txt"), "поза текою");
  symlinkSync(path.join(home, "outside.txt"), path.join(src, "link.txt"));

  await openFromMenu(page);
  assert.equal(await page.inputValue("#sp-name"), "", "перший простір на машині — «Особисте», а тут уже є простори");
  await page.fill("#sp-name", "Client");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/client");
  await next(page);
  await step(page, 2);
  await page.waitForSelector(pick("static-publish"));
  await next(page);
  await step(page, 3);
  await page.waitForSelector(card("static-publish"));
  await next(page);                                          // без змін
  await step(page, 4);
  for (const p of ["/api/module-enable", "/api/module-settings", "/api/module-disable"]) {
    assert.equal(postsTo(posts, p).length, 0, `крок 3 без змін не пише: ${p}`);
  }

  await page.check('input[name="wz-src"][value="folder"]');
  assert.equal(await page.locator("#wz-from").isVisible(), true, "поле теки зʼявилось");
  assert.equal(await activeId(page), "wz-from", "фокус у полі теки");
  await page.fill("#wz-from", "~/mock-landing");
  assert.equal(await page.inputValue("#tf-title"), "mock-landing", "назва — з імені теки");
  assert.equal(await page.inputValue("#tf-id"), "mock-landing");
  await next(page);
  await waitToast(page, /Символьні посилання не скопійовано: 1/);
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });

  const it1 = path.join(home, "deai-work", "client", "mock-landing", "iterations", "it1");
  assert.ok(existsSync(path.join(it1, "index.html")), "index.html у першій ітерації");
  assert.ok(existsSync(path.join(it1, "img", "a.svg")), "картинка скопійована");
  assert.equal(existsSync(path.join(it1, "link.txt")), false, "символьне посилання не скопійовано");
  await page.waitForFunction(() => document.getElementById("frame")?.contentDocument?.getElementById("mark")?.textContent === "LANDING",
    null, { timeout: 20000 });
  assert.equal((await spacesApi(url)).current, "client");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W3: крок 1 — відмова (перетин) лишає форму, «Скасувати» вертає на полотно з фокусом на фішці, зайнята форма не скасовується", async (t) => {
  const { page, url, posts, spaces, outside, errors } = await boot(t, { spaces: studio() });
  await openFromMenu(page);
  await page.fill("#sp-name", "Dup");
  await page.fill("#sp-path", path.join(spaces[0].path, "inner"));
  await next(page);
  await page.waitForFunction(() => { const e = document.getElementById("wz-err"); return Boolean(e && !e.hidden && e.textContent.trim()); });
  assert.match(await text(page, "#wz-err"), /перетинається/, "причина відмови названа");
  assert.equal(await page.getAttribute("#sp-path", "aria-invalid"), "true");
  assert.equal(await activeId(page), "sp-path", "фокус на полі з помилкою");
  await page.fill("#sp-path", "~/deai-work/dup");
  assert.equal(await page.getAttribute("#sp-path", "aria-invalid"), null, "правка теки знімає позначку");
  assert.equal((await spacesApi(url)).spaces.length, 1, "відмовлений простір не зʼявився");

  await page.click('#tasks-home .wz [data-a="cancel"]');
  await page.waitForFunction(() => !document.querySelector(".wz") && !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await page.waitForFunction(() => document.activeElement === document.querySelector("#bar .space-chip"), null, { timeout: 5000 })
    .catch(() => { throw new Error("«Скасувати» не вернуло фокус на фішку простору"); });
  assert.equal((await spacesApi(url)).spaces.length, 1);
  await waitText(page, "#bar .crumb--task .txt", "t1");

  /* Зайнята форма: запит створення летить повільно. */
  await page.route("**/api/space-new", async (route) => { await sleep(1200); await route.continue(); });
  const before = postsTo(posts, "/api/space-new").length;
  await openFromMenu(page);
  await page.fill("#sp-name", "Slow");
  await next(page);
  await page.waitForFunction(() => document.querySelector('.wz form[data-wz-step="1"]')?.getAttribute("aria-busy") === "true");
  assert.equal(await page.locator('#tasks-home .wz [data-a="cancel"]').isDisabled(), true, "«Скасувати» вимкнене під запитом");
  assert.equal(await page.locator('#tasks-home .wz [data-a="ok"]').isDisabled(), true, "«Далі» вимкнена під запитом");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator('#tasks-home .wz[data-step="1"]').count(), 1, "Esc нічого не закриває");
  await step(page, 2);
  assert.equal(postsTo(posts, "/api/space-new").length - before, 1, "рівно один запит створення");
  assert.equal((await spacesApi(url)).current, "slow");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W4: назад на крок 1 — режим правки (тека лише для читання), без змін запиту нема, перейменування — один space-update, «Закрити майстер» — тост «готовий»", async (t) => {
  const { page, url, posts, outside, errors } = await boot(t);
  await firstSpace(page);
  await back(page);
  await step(page, 1);
  await page.waitForSelector('form[data-form="space"][data-mode="edit"]');
  assert.equal(await page.evaluate(() => document.getElementById("sp-path").readOnly), true, "тека створеного простору — лише для читання");
  await next(page);
  await step(page, 2);
  assert.equal(postsTo(posts, "/api/space-update").length, 0, "без змін — жодного space-update");

  await back(page);
  await step(page, 1);
  await page.fill("#sp-name", "Моє");
  await next(page);
  await step(page, 2);
  assert.equal(postsTo(posts, "/api/space-update").length, 1, "перейменування — рівно один space-update");
  assert.equal((await spacesApi(url)).spaces[0].name, "Моє");

  await page.click('#tasks-home .wz [data-wz="close"]');
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Моє");
  await waitToast(page, /Простір «Моє» готовий/);
  assert.equal(await page.locator(".wz").count(), 0, "розмітки майстра в DOM нема");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W5: незбережене на кроці 3 — Esc не закриває, логотип, «Назад» і «Закрити майстер» питають, «Відкинути» виходить без секрету в DOM", async (t) => {
  const m = await boot(t);
  const { page, url, outside, errors } = m;
  await firstSpace(page);
  await pickAndNext(page, ["memo-publish"]);
  await page.fill(field("memo-publish", "note"), "draft");
  await page.fill(field("memo-publish", "token"), SECRET);

  await page.keyboard.press("Escape");
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "Esc лишає на кроці 3");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "Esc нічого не питає");

  await page.click('#bar [data-act="home"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await askText(page), /Відкинути незбережені налаштування/);
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "«Скасувати» лишає на кроці 3");
  assert.equal(await page.inputValue(field("memo-publish", "note")), "draft", "набране на місці");
  assert.equal(await page.inputValue(field("memo-publish", "token")), SECRET, "секрет на місці");

  /* «Назад» з незбереженим — теж питання; «Скасувати» лишає на кроці 3 з набраним. */
  await back(page);
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "«Назад» без згоди лишає на кроці 3");
  assert.equal(await page.inputValue(field("memo-publish", "note")), "draft", "набране на місці після «Назад»");

  await page.click('#tasks-home .wz [data-wz="close"]');
  await page.waitForSelector(".cv-ask-scrim");
  /* Кадри від «Відкинути» й далі: поле пароля зі значенням не сміє пережити вихід навіть на кадр (сторінка «Задачі» ще
     вантажиться, а розмітка майстра вже мусить зникнути — секрет живе лише у `.value`, а перемальовка його не чистить). */
  await page.evaluate(() => {
    window.__frames = [];
    const tick = () => {
      window.__frames.push([...document.querySelectorAll('input[type="password"]')].filter((n) => n.value !== "").length);
      if (window.__frames.length < 90) requestAnimationFrame(tick);
    };
    window.__sample = () => requestAnimationFrame(tick);
  });
  await page.evaluate(() => {
    document.querySelector('.cv-ask-scrim button[data-a="ok"]').addEventListener("click", () => window.__sample(), { capture: true });
  });
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Особисте");
  await page.waitForFunction(() => window.__frames.length >= 30);
  assert.deepEqual((await page.evaluate(() => window.__frames)).filter((n) => n > 0), [], "секрет у полі пароля пережив вихід з майстра");
  const sp = (await spacesApi(url)).spaces[0];
  assert.equal((spaceJson(sp.path).modules ?? {})["memo-publish"], undefined, "відкинуте не записалось");
  assert.equal(await page.locator(".wz").count(), 0, "розмітка майстра зникла з DOM");
  assert.equal(await pwWithValue(page), 0, "після виходу нема полів пароля зі значенням");
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM після виходу");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W6: свіжість — агент зайняв роль, поки людина вибирала: картка каже «роль змінилась» і називає тримача, незалежний запис іде", async (t) => {
  const { page, url, posts, outside, errors } = await boot(t);
  await firstSpace(page);
  const { id: spaceId, path: spPath } = (await spacesApi(url)).spaces[0];
  writeFileSync(path.join(spPath, "ds.css"), ":root{--c-a:#123456}");
  await pickAndNext(page, ["memo-publish", "css-tokens"]);
  await page.fill(field("memo-publish", "note"), "ok");
  await page.fill(field("css-tokens", "file"), "{space}/ds.css");
  /* «Агент» напряму займає роль іншим модулем (а не тим, що вибрала людина). */
  const taken = await postJson(url, "/api/module-enable", { space: spaceId, id: "memo-publish2", settings: { note: "agent" }, replace: true });
  assert.equal(taken.status, 200);
  await next(page);
  await page.waitForSelector(`${card("memo-publish")} .cn-res--err`);
  await page.waitForSelector(`${card("css-tokens")} .cn-res--ok`);
  const refusal = await page.locator(`${card("memo-publish")} .cn-res--err`).textContent();
  assert.match(refusal, /роль змінилась/);
  assert.match(refusal, /Memo publish 2 \(test\)/, "названо нового тримача ролі");
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "лишаємось на кроці 3");
  const mods = spaceJson(spPath).modules;
  assert.equal(mods["css-tokens"].enabled, true, "незалежний запис пройшов");
  assert.equal(mods["memo-publish"], undefined, "застарілий запис не пішов");
  assert.equal(mods["memo-publish2"].enabled, true, "вибір агента не затерто");
  const ids = postsTo(posts, "/api/module-enable").map((x) => JSON.parse(x.body).id);
  assert.deepEqual(ids, ["css-tokens"], "жодного module-enable memo-publish зі сторінки");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W7: «Відкрити наявну теку простору» — підказка «знайдено», назва зі space.json (лише читання), вибрані модулі підхоплено, «До задач» — картка s1", async (t) => {
  const { page, home, outside, errors } = await boot(t);
  const shared = path.join(home, "shared-space");
  mkdirSync(shared, { recursive: true });
  writeFileSync(path.join(shared, "ds.css"), ":root{--c-a:#123456}");
  writeFileSync(path.join(shared, "space.json"), JSON.stringify({
    name: "Shared", color: "space-4", modules: { "css-tokens": { enabled: true, settings: { file: "{space}/ds.css" } } },
  }));
  const S1 = taskFixture({ html: MOCKUP });
  writeFileSync(path.join(shared, "tasks.json"), JSON.stringify({
    current: "s1", design_work_root: shared, tasks: { s1: { dir: S1.dir, title: "S1" } },
  }));

  await page.click('#tasks-home .th-welcome [data-th="spaceopen"]');
  await step(page, 1);
  assert.equal(await activeId(page), "sp-path", "фокус у полі теки");
  assert.equal(await page.inputValue("#sp-name"), "", "назва порожня до підхоплення");
  await page.fill("#sp-path", "~/shared-space");
  await page.waitForFunction(() => { const e = document.getElementById("sp-found"); return Boolean(e && !e.hidden && e.textContent.trim()); });
  assert.equal(await page.inputValue("#sp-name"), "Shared", "назва підхоплена з теки");
  assert.equal(await page.evaluate(() => document.getElementById("sp-name").readOnly), true, "назва знайденого простору — лише для читання");

  await next(page);
  await step(page, 2);
  await page.waitForSelector(pick("css-tokens"));
  assert.equal(await page.locator(pick("css-tokens")).isChecked(), true, "увімкнене в теці — вибране");
  await next(page);
  await step(page, 3);
  await page.waitForSelector(card("css-tokens"));
  await next(page);
  await step(page, 4);
  assert.match(await text(page, "#tasks-home .wz-lead"), /Задач у просторі вже: 1/);
  assert.equal(await text(page, '#tasks-home .wz [data-wz="skip"]'), "До задач");
  await page.click('#tasks-home .wz [data-wz="skip"]');
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Shared");
  await page.waitForSelector('#tasks-home .th-card[data-id="s1"]');
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W8: збій читання списку на старті «Зберегти» не губить введене: тост, картки, поле й секрет на місці, жодного запису; повтор проходить", async (t) => {
  const m = await boot(t);
  const { page, url, deaiHome, posts, outside, errors } = m;
  await firstSpace(page);
  const { id: spaceId } = (await spacesApi(url)).spaces[0];
  await pickAndNext(page, ["memo-publish"]);
  await page.fill(field("memo-publish", "note"), "ok");
  await page.fill(field("memo-publish", "token"), SECRET);

  /* Рівно ОДИН запит списку після натиску обривається. */
  let cut = 0;
  await page.route((u) => u.pathname === "/api/modules", async (route) => {
    if (cut++ === 0) await route.abort("failed"); else await route.continue();
  });
  await next(page);
  await waitToast(page, /Не вдалося прочитати модулі простору/);
  assert.equal(await page.locator(card("memo-publish")).count(), 1, "картка на місці");
  assert.equal(await page.inputValue(field("memo-publish", "note")), "ok", "поле на місці");
  assert.equal(await page.inputValue(field("memo-publish", "token")), SECRET, "секрет на місці");
  assert.equal(postsTo(posts, "/api/module-enable").length, 0, "жодного запису");
  assert.equal(cut, 1, "свідок: запит списку справді обривався");
  await page.unroute((u) => u.pathname === "/api/modules").catch(() => {});

  await next(page);
  await step(page, 4);
  assert.equal(secretsJson(deaiHome)[spaceId]["memo-publish"].token, SECRET, "повтор записав секрет");
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W9: «Назад» під час перевірки id на кроці 4 не створює задачу", async (t) => {
  const { page, posts, outside, errors } = await boot(t);
  await firstSpace(page);
  await next(page);
  await step(page, 3);
  await page.waitForSelector(card("static-publish"));
  /* Перелік зайнятих id (`takenTaskIds` → `GET /api/tasks?all=1`) приходить із запізненням. */
  await page.route((u) => u.pathname === "/api/tasks" && u.search.includes("all=1"), async (route) => {
    await sleep(1500);
    await route.continue();
  });
  await next(page);
  await step(page, 4);
  await page.fill("#tf-title", "Задача 9");
  await next(page);                                          // «Створити й відкрити»: перевірка id чекає на перелік
  await back(page);                                          // і тут людина йде «Назад»
  await step(page, 3);
  await sleep(2200);                                         // перелік прийшов, перевірка мусила здатись
  assert.equal(postsTo(posts, "/api/task-new").length, 0, "task-new після «Назад» не пішов");
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "лишились на кроці 3");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W10: збережена картка не лишається «зміненою»: після проходу поле показує значення сервера, секрет порожній, «Назад» не питає", async (t) => {
  const m = await boot(t);
  const { page, outside, errors } = m;
  await firstSpace(page);
  await pickAndNext(page, ["memo-publish", "memo-note"]);
  assert.equal(await page.inputValue(field("memo-note", "label")), "dflt-label", "свідок: типове значення на старті");
  await page.fill(field("memo-publish", "note"), "fail");                    // перевірка скаже «ні»
  await page.fill(field("memo-publish", "token"), SECRET);
  await page.fill(field("memo-note", "label"), "");                          // очищене поле з типовим значенням
  await next(page);
  await page.waitForSelector(`${card("memo-publish")} .cn-res--err`);
  await page.waitForSelector(`${card("memo-note")} .cn-res--ok`);
  assert.match(await page.locator(`${card("memo-publish")} .cn-res--err`).textContent(), /Збережено, але перевірка не пройшла/);
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "перевірка «ні» — лишаємось на кроці 3");
  assert.equal(await page.inputValue(field("memo-note", "label")), "dflt-label", "після запису поле показує значення сервера, а не старий DOM");
  assert.equal(await page.inputValue(field("memo-publish", "token")), "", "поле пароля після відповіді порожнє");
  assert.match(await page.locator(`${card("memo-publish")} .cn-secret`).textContent(), /^задано ·/, "секрет збережено, стан — «задано»");

  await back(page);
  await step(page, 2);
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "записане — не «незбережене»: «Назад» не питає");
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W11: помилка після «Зберегти й далі» видима — фокус на полі першої збійної картки, у межах вікна (низьке вікно, прокрутка донизу)", async (t) => {
  const { page, url, outside, errors } = await boot(t, { viewport: { width: 1200, height: 520 } });
  await firstSpace(page);
  const { path: spPath } = (await spacesApi(url)).spaces[0];
  writeFileSync(path.join(spPath, "ds.css"), ":root{--c-a:#123456}");
  await pickAndNext(page, ["memo-publish", "css-tokens", "memo-note"]);
  await page.fill(field("memo-publish", "note"), "fail");
  await page.fill(field("css-tokens", "file"), "{space}/ds.css");
  const scrolled = await page.evaluate(() => {
    const el = document.getElementById("tasks-home");
    el.scrollTop = el.scrollHeight;
    return el.scrollTop;
  });
  assert.ok(scrolled > 0, "свідок: вікно низьке, сторінка справді прокручується (перша картка над кадром)");
  await next(page);
  await page.waitForSelector(`${card("memo-publish")} .cn-res--err`);
  await page.waitForFunction(() => document.activeElement?.closest?.('.wz-card[data-id="memo-publish"]'), null, { timeout: 5000 });
  const r = await page.evaluate(() => {
    const a = document.activeElement.getBoundingClientRect();
    const h = document.getElementById("tasks-home").getBoundingClientRect();
    return { top: a.top, bottom: a.bottom, homeTop: h.top, homeBottom: h.bottom };
  });
  assert.ok(r.top >= r.homeTop - 0.5 && r.bottom <= r.homeBottom + 0.5, `елемент у фокусі поза вікном: ${JSON.stringify(r)}`);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W12: відмова сервера на записі картки теж очищає поле пароля (секрет не лишається в DOM), нічого не збережено", async (t) => {
  const m = await boot(t);
  const { page, url, deaiHome, outside, errors } = m;
  await firstSpace(page);
  const { id: spaceId, path: spPath } = (await spacesApi(url)).spaces[0];
  await pickAndNext(page, ["memo-publish"]);
  await page.fill(field("memo-publish", "note"), "x".repeat(4097));        // понад ліміт значення: сервер відмовить `bad-settings`
  await page.fill(field("memo-publish", "token"), SECRET);
  await next(page);
  await page.waitForSelector(`${card("memo-publish")} .cn-res--err`);
  assert.match(await page.locator(`${card("memo-publish")} .cn-res--err`).textContent(), /Сервер не прийняв налаштування/);
  assert.equal(await page.inputValue(field("memo-publish", "token")), "", "після відмови поле пароля порожнє");
  assert.match(await page.locator(`${card("memo-publish")} .cn-secret`).textContent(), /^не задано ·/, "нічого не збережено");
  assert.equal((spaceJson(spPath).modules ?? {})["memo-publish"], undefined);
  const secretsFile = path.join(deaiHome, "secrets.json");
  assert.equal(existsSync(secretsFile) ? secretsJson(deaiHome)[spaceId]?.["memo-publish"] : undefined, undefined, "секрет у secrets.json");
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM");
  assert.deepEqual(await leaks(page), [], "секрет побував у розмітці");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W13: перемальовка кроку 1 (зміна мови з ⌘K) не губить набране й не відновлює звʼязок «назва → тека» після ручної правки теки", async (t) => {
  const { page, outside, errors } = await boot(t);
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await step(page, 1);
  await page.fill("#sp-path", "~/deai-work/custom");         // тека правлена руками: далі назва її не веде
  await page.fill("#sp-name", "Студія");
  await page.keyboard.press("Control+k");
  await page.waitForSelector("#palq");
  await page.fill("#palq", "English");
  await page.waitForTimeout(200);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /New space/.test(document.querySelector("#tasks-home .wz h1")?.textContent ?? ""), null, { timeout: 5000 })
    .catch(() => { throw new Error("свідок: мова не перемкнулась — сторінка не перемальована"); });
  assert.equal(await page.inputValue("#sp-name"), "Студія", "набрана назва пережила перемальовку");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/custom", "набрана тека пережила перемальовку");
  await page.fill("#sp-name", "Інша назва");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/custom", "після перемальовки назва знову веде теку, хоча її правили руками");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("W14: «Без модуля» у ролі публікації — рядок «вимкнеться», один module-disable, смуга нової задачі без кнопок публікації", async (t) => {
  const { page, url, posts, outside, errors } = await boot(t);
  await firstSpace(page);
  const { id: spaceId, path: spPath } = (await spacesApi(url)).spaces[0];
  await page.locator('#tasks-home input[data-wz-pick][data-role="publish"][value=""]').check();
  assert.equal(await page.locator(pick("static-publish")).isChecked(), false, "«Без модуля» знімає поточного постачальника");
  await next(page);
  await step(page, 3);
  await page.waitForSelector('#tasks-home .wz-off[data-id="static-publish"]');
  assert.match(await page.locator('#tasks-home .wz-off[data-id="static-publish"]').textContent(), /Публікація: «Публікація в теку» вимкнеться/);
  assert.equal(await page.locator("#tasks-home .wz-card").count(), 0, "карток нема — нічого не підключаємо");
  await next(page);
  await step(page, 4);
  const offs = postsTo(posts, "/api/module-disable").map((x) => JSON.parse(x.body));
  assert.deepEqual(offs, [{ space: spaceId, id: "static-publish" }], "рівно один disable, з простором майстра");
  assert.equal(postsTo(posts, "/api/module-enable").length, 0, "нічого не вмикали");
  assert.equal(spaceJson(spPath).modules["static-publish"].enabled, false);

  await page.fill("#tf-title", "Без публікації");
  await next(page);
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await page.waitForSelector("#bar .crumb--task");
  const acts = await page.$$eval("#bar [data-act], #bar [data-dd]", (els) => els.map((e) => e.dataset.act || `dd:${e.dataset.dd}`));
  assert.ok(!acts.includes("publish") && !acts.includes("dd:pub"), `смуга новоствореної задачі лишила кнопки публікації: ${acts}`);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

guardRealDeai();

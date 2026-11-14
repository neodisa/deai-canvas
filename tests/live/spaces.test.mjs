/**
 * Простори (Deai 1.0, етап 1, Task 8) — живе проведення: справжній сервер із
 * ізольованою «машиною» (тимчасові `HOME` і `DEAI_HOME`, реєстр `spaces.json`
 * пишеться заздалегідь), справжній Chromium.
 *
 * Розмітку й правила стережуть юніти (`tests/spaces-*.test.mjs`, `tests/test_spaces*.py`);
 * тут те, чого вони не бачать: що перемикання простору справді міняє смугу, перемикач
 * задач і екран «Задачі»; що форма «Нова задача» створює теку на диску й відкриває
 * задачу; що новий простір з типовою текою справді створюється; що порожня машина
 * показує привітання, а не помилку; що простір БЕЗ інтеграцій не робить жодного
 * запиту за межі машини.
 *
 * Сценарії ПОВЕДІНКИ (зміна простору поза вкладкою, зайняті форми, фокус, оновлення на поверненні до
 * вікна, лічильники запитів) — у `spaces-flows.test.mjs`; спільні прилади й охоронець справжнього
 * `~/.deai` — у `_spaces-kit.mjs`.
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись, чи
 * червоніє):
 *   1 (перемикання)  — `space` у `BAR_ACTIONS` (`app.js`), `capabilities.vcs` (GitLab) і `hasPublish`
 *        (публікація, `capabilities.publish`) у `bar-model.js`.
 *        Мутація «`space` не кличе `space-switch`» червонить 1; «зона GitLab без `capabilities.vcs`» і
 *        «публікація не за `hasPublish`» — теж 1.
 *   2 (нова задача)  — `space: sp.id` у `newTaskDialog` і `task_new(root=sp['path'])`.
 *   3 (новий простір) — `check_new_path` (типова тека не мусить перетинатись зі старим
 *        простором) і `afterSpaceChange`; вхід — майстер (етап 3b): «Новий простір…» дропдауна (`spacenew`, `app.js`) —
 *        мутація «пункт нічого не робить» червонить 3 і 6; «Закрити майстер» (`[data-wz="close"]`, `wizard.js`) — 3 і 4.
 *   4 (привітання)   — `needsWelcome` (`spaces-model.js`). Мутація «завжди false» червонить 4; кнопка привітання
 *        «Створити простір» (`wireHome`, `app.js`) — теж 4.
 *   4б (зіпсований старий файл) — `legacy_error` у `spaces.listing()` і `needsWelcome`
 *        (`spaces-model.js`). Мутація «`needsWelcome` ігнорує `legacy_error`» червонить 4б
 *        (привітання замість смуги помилки); «`listing` без `legacy_error`» — теж.
 *   5 (мережа)       — пониження `ch=project` у `_commented` (сервер), вимикач
 *        у `comment-config` (клієнтський затиск `effectiveCommentMode` прибрано в 0.27.0 — перемикача каналу нема). Кожна мутація
 *        червонить 5 (сервер — кроком «прямий `ch=project`», клієнт — кроком «рамка»).
 *   6 (майстер)      — відмова сервера лишається на кроці 1 майстра (`showError` у `wizard.js`: текст у `#wz-err`;
 *        мутація «без тексту» червонить 6).
 *   7 (~/.deai)      — ізоляція: `HOME`/`DEAI_HOME` у `fixture.mjs` (`isolatedMachine`).
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, spacesApi, stop, text, waitText, waitBarReady, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { hermeticLiga } from "./_liga-supabase.mjs";

/* Свої бази: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs`
   стереже, що жодна база не збігається з чужою). Привітання — окрема смуга: там
   сервер без жодного простору. */
const PORT_BASE = 12200;
const WELCOME_PORT_BASE = 12300;

const HTML = (label) => (page) => `<!doctype html><html lang="uk"><head><meta charset="utf-8">
<title>${label} ${page}</title></head><body><h1>${label} · ${page}</h1><p>Фікстура просторів.</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/**
 * Дві задачі в двох просторах: `a` — «ЛІГА-подібний» старий простір (інтеграції ввімкнено),
 * `x` — «P» без інтеграцій. `first` каже, який простір поточний на старті.
 */
async function boot(t, { first = "liga", portBase = PORT_BASE, requests = null } = {}) {
  const A = taskFixture({ html: HTML("A") });
  const X = taskFixture({ html: HTML("X") });
  const legacy = { name: "Liga", id: "liga", color: "space-2", legacy: true, roles: ["comments", "dashboard", "notify", "vcs", "publish"], tasks: { a: { dir: A.dir, title: "Задача A" } } };   // 4d-4b: мігрована ЛІГА — явні записи
  const p = { name: "P", id: "p", color: "space-3", tasks: { x: { dir: X.dir, title: "Задача X" } } };
  const spaces = first === "liga" ? [legacy, p] : [p, legacy];
  const server = await startServer(null, { portBase, spaces });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  /* Мігрована ЛІГА з роллю `comments`: робоче місце читає командне сховище (вигаданий хост Supabase) — його запити перехоплює
     `hermeticLiga`, а будь-що поза машиною мусить лишитись порожнім (охоронець `tests/live-hermetic.test.mjs`). */
  const seen = await hermeticLiga(context);
  t.after(() => assert.deepEqual(seen.outside, [], `запити за межі машини:\n${seen.outside.join("\n")}`));
  if (requests) context.on("request", (r) => requests.push(r.url()));
  const page = await context.newPage();
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page);
  return { page, context, ...server, byId: Object.fromEntries(server.spaces.map((s) => [s.id, s])) };
}

/** Крок 1 майстра відправлено — дочекатись кроку 2 й закрити майстер (тестам потрібен лише простір). */
async function closeWizard(page) {
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  await page.click('#tasks-home .wz [data-wz="close"]');
}

const homeOpen = (page) => page.evaluate(() => document.body.classList.contains("home-open"));
const frameSrc = (page) => page.evaluate(() => document.getElementById("frame")?.getAttribute("src") ?? "");
const barActs = (page) => page.$$eval("#bar [data-act], #bar [data-dd]",
  (els) => els.map((e) => e.dataset.act || `dd:${e.dataset.dd}`));

/**
 * Відкрити дропдаун просторів і дочекатись РЯДКІВ. Перший показ дропдауна малюється зі
 * старою відповіддю `/api/spaces` (її питають лише при відкритті), тож короткий час він
 * порожній — рядки приходять перемальовкою. Клікати футер чи читати перелік до неї
 * означає гонку з тією перемальовкою (на практиці — раз на десяток прогонів).
 */
async function openSpaces(page, rows = 2) {
  await goTasks(page);
  await page.click("#bar .space-chip");
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n,
    rows, { timeout: 15000 });
}

/** Перемкнути простір через фішку: клік по рядку дропдауна. */
async function pickSpace(page, id) {
  await openSpaces(page);
  await page.click(`.dd--spaces .dd-item[data-val="${id}"]`);
}

/** Відкрити екран «Задачі» логотипом. */
async function openHome(page) {
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home h1.th-h");
}

test("1: перемикання на «P» без інтеграцій — смуга й перемикач задач лише з x, «Задачі · P», без «Команди», GitLab і публікації", async (t) => {
  const { page, url } = await boot(t);

  /* Початок: поточний — старий простір з інтеграціями. Те, чого нема в «P», тут ЄСТЬ —
     без цих свідків «нема» в «P» нічого б не доводило. */
  /* Вигляд задачі (0.25.0): смуга несе лише назву задачі; фішка простору й перемикач задач живуть на екрані «Задачі». */
  assert.equal(await text(page, "#bar .crumb--title .txt"), "Задача A");
  const before = await barActs(page);
  assert.ok(before.includes("dd:gl"), `свідок: у просторі з інтеграціями є зона GitLab (${before})`);
  assert.ok(before.includes("publish"), "свідок: у просторі з інтеграціями є публікація");

  await openSpaces(page);
  assert.equal(await text(page, "#bar .space-name"), "Liga", "фішка не показує поточний простір");
  assert.match(await page.getAttribute("#bar .space-dot", "style"), /var\(--space-2\)/, "крапка не кольору простору");
  assert.equal(await page.getAttribute("#bar .space-chip", "aria-expanded"), "true");
  assert.deepEqual(await page.$$eval('.dd--spaces .dd-item[data-act="space"]', (els) => els.map((e) => e.dataset.val)),
    ["liga", "p"], "перелік просторів");
  assert.equal(await page.getAttribute('.dd--spaces [data-val="liga"]', "aria-current"), "true", "поточний не позначений");
  assert.equal(await page.getAttribute('.dd--spaces [data-val="p"]', "aria-current"), null);
  assert.ok(await page.$('.dd--spaces [data-act="spacenew"]') && await page.$('.dd--spaces [data-act="spaceedit"]'), "футер дропдауна");

  await page.click('.dd--spaces .dd-item[data-val="p"]');
  await waitText(page, "#bar .space-name", "P");
  assert.equal((await spacesApi(url)).current, "p", "вибір не дійшов до реєстру");
  assert.match(await page.getAttribute("#bar .space-dot", "style"), /var\(--space-3\)/);

  /* Екран «Задачі» (перемикання йшло з нього, тож він лишається): заголовок із простором, лише x — задачі іншого простору тут
     нема (це й замінює колишній перемикач задач на смузі), без «Команди». */
  await waitText(page, "#tasks-home h1.th-h", "Задачі · P");
  await page.waitForSelector("#tasks-home .th-card");
  assert.deepEqual(await page.$$eval("#tasks-home .th-card", (els) => els.map((e) => e.dataset.id)), ["x"],
    "на екрані задач чужі задачі іншого простору");
  assert.equal(await page.locator('#tasks-home .th-tab[data-v="team"]').count(), 0, "вкладка «Команда» без інтеграцій");
  assert.equal(await page.locator('#tasks-home .th-tab[data-v="mine"]').count(), 1);

  /* Задача простору «P» відкривається карткою; смуга задачі — лише з x. */
  await page.click('#tasks-home .th-card[data-id="x"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await waitText(page, "#bar .crumb--title .txt", "Задача X");
  await page.waitForFunction(() => /\/commented\?/.test(document.getElementById("frame")?.getAttribute("src") ?? ""));

  /* Зони назовні: GitLab — немає (він на `capabilities.vcs`). Публікація — Є: з модулями 2а (Task 8) вона
     стоїть на `capabilities.publish`, а в «P» без синку публікує явний `static-publish` (локальна
     тека, нічого назовні). Дропдаун публікації — лише показ, відкриття й посилання: без пароля ЛІГА і без
     Teams-каналу (його стан у просторі без інтеграцій не питається, і пункт висів би вічним «перевіряю»). */
  const acts = await barActs(page);
  assert.ok(!acts.includes("dd:gl"), `зона GitLab лишилась без інтеграцій (${acts})`);
  assert.ok(acts.includes("publish") && acts.includes("dd:pub"), `публікація модулем зникла в просторі без інтеграцій (${acts})`);
  await page.click('#bar [data-dd="pub"]');
  assert.deepEqual(await page.$$eval("#bar .dd--right [data-act]", (els) => els.map((e) => e.dataset.act)),
    ["togglepub", "openpreview", "copylink"], "дропдаун публікації модулем: пароль ЛІГА чи Teams там не мають бути");
  await page.keyboard.press("Escape");

  /* Назад у простір з інтеграціями: «Команда» повертається (свідок для «нема» вище). */
  await pickSpace(page, "liga");
  await waitText(page, "#bar .space-name", "Liga");
  await openHome(page);
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Liga");
  assert.equal(await page.locator('#tasks-home .th-tab[data-v="team"]').count(), 1, "свідок: у просторі з інтеграціями є «Команда»");
});

test("2: у «P» — «Нова задача» → «Landing» → id landing → «Створити» → відкрилась landing, тека з першою ітерацією на диску", async (t) => {
  const { page, url, byId } = await boot(t, { first: "p" });
  await goTasks(page);
  await waitText(page, "#bar .space-name", "P");
  await openHome(page);
  await waitText(page, "#tasks-home h1.th-h", "Задачі · P");
  assert.equal(await page.locator('#tasks-home .th-head [data-th="newtask"]').count(), 1, "кнопка «Нова задача» у голові екрана");

  await page.click('#tasks-home .th-head [data-th="newtask"]');
  await page.waitForSelector('form[data-form="task"]');
  await page.fill("#tf-title", "Landing");
  assert.equal(await page.inputValue("#tf-id"), "landing", "id не виведено з назви");
  await page.click('form[data-form="task"] [data-a="ok"]');

  await waitText(page, "#bar .crumb--title .txt", "Landing");
  await page.waitForFunction(() => !document.body.classList.contains("home-open"));
  assert.equal(await homeOpen(page), false, "екран «Задачі» не закрився після створення");
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "форма лишилась");
  await page.waitForFunction(() => /\/commented\?/.test(document.getElementById("frame")?.getAttribute("src") ?? ""));

  const created = path.join(byId.p.path, "landing", "iterations", "it1", "index.html");
  assert.ok(existsSync(created), `немає ${created}: тека задачі лягла не в простір «P»`);
  assert.match(readFileSync(created, "utf8"), /<h1>Landing<\/h1>/, "назва задачі в стартовому макеті");
  const tasks = await (await fetch(`${url}/api/tasks`)).json();
  assert.equal(tasks.current, "landing");
  assert.deepEqual(tasks.tasks.map((x) => x.id).sort(), ["landing", "x"], "задача лягла не в простір «P»");
  assert.equal((await (await fetch(`${url}/api/tasks?all=1`)).json()).tasks.filter((x) => x.id === "landing")[0].space, "p");
});

test("3: «Новий простір…» → «Client», тека типова → «Далі» → «Закрити майстер» → «Задачі · Client», порожній стан", async (t) => {
  const { page, url, home } = await boot(t);
  await openSpaces(page);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
  assert.equal(await page.inputValue("#sp-name"), "", "перший простір на машині — «Особисте», а тут уже є простори");
  await page.fill("#sp-name", "Client");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/client", "тека не йде за назвою");
  assert.equal(await page.locator(".cv-colors .cv-color").count(), 6);
  assert.equal(await page.locator('.cv-colors .cv-color[aria-checked="true"]').count(), 1);
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);

  await waitText(page, "#tasks-home h1.th-h", "Задачі · Client");
  assert.equal(await homeOpen(page), true, "порожній простір — екран «Задачі»");
  await page.waitForSelector("#tasks-home .th-empty--space");
  assert.equal(await page.locator('#tasks-home [data-th="newtask"]').count(), 2, "«Нова задача» в голові й у порожньому стані");
  assert.equal(await page.locator('#tasks-home .th-tab[data-v="team"]').count(), 0, "новий простір без інтеграцій");
  await waitText(page, "#bar .space-name", "Client");
  assert.equal(await page.locator('form[data-form="space"]').count(), 0, "форма простору лишилась (крок 2 її не має)");

  const reg = await spacesApi(url);
  assert.equal(reg.current, "client");
  assert.deepEqual(reg.spaces.map((s) => s.id), ["liga", "p", "client"]);
  const made = reg.spaces.find((s) => s.id === "client");
  assert.equal(made.path, path.join(home, "deai-work", "client"), "тека простору — типова під домівкою");
  assert.equal(made.capabilities.vcs, null, "свідок: у новому просторі синку нема");
  const mods = await (await fetch(`${url}/api/modules?space=${made.id}`)).json();
  const pubRec = (mods.modules || mods).find((m) => m.id === "static-publish");
  assert.ok(pubRec, `запис static-publish у новому просторі: ${JSON.stringify(mods).slice(0, 300)}`);
  assert.equal(pubRec.enabled, true, "static-publish ввімкнено явно");
  assert.equal(pubRec.implicit, false, "static-publish — явний запис, не неявний");
  assert.ok(existsSync(path.join(made.path, "space.json")) && existsSync(path.join(made.path, "tasks.json")), "файли простору");
});

test("4: привітання на порожній машині → «Створити простір» → «Особисте» → «Далі» → «Закрити майстер» → «Задачі · Особисте»", async (t) => {
  const server = await startServer(null, { portBase: WELCOME_PORT_BASE, spaces: [] });
  t.after(() => stop(server.child));
  assert.equal(existsSync(path.join(server.deaiHome, "spaces.json")), false, "свідок: реєстру ще нема (порожня машина)");
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(`${server.url}/app/`);

  await page.waitForSelector("#tasks-home .th-welcome");
  assert.equal(await text(page, "#tasks-home h1.th-h"), "Вітаю в Deai Canvas");
  assert.equal(await homeOpen(page), true);
  assert.equal(await page.locator("#bar .space-chip").count(), 0, "фішки простору без просторів не мусить бути");
  assert.equal(await page.locator("#tasks-home .th-card").count(), 0);

  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
  assert.equal(await page.inputValue("#sp-name"), "Особисте", "перший простір на машині — «Особисте»");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/personal");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);

  await waitText(page, "#tasks-home h1.th-h", "Задачі · Особисте");
  assert.equal(await page.locator("#tasks-home .th-welcome").count(), 0, "привітання лишилось");
  await waitText(page, "#bar .space-name", "Особисте");
  const reg = await spacesApi(server.url);
  assert.equal(reg.spaces.length, 1);
  assert.equal(reg.current, reg.spaces[0].id);
  assert.equal(reg.spaces[0].path, path.join(server.home, "deai-work", "personal"));
  /* Позитивний свідок ізоляції: реєстр ЗʼЯВИВСЯ в тимчасовій домівці, а не деінде
     (охоронець у кінці файла бачить лише відсутність слідів у справжній). */
  const written = JSON.parse(readFileSync(path.join(server.deaiHome, "spaces.json"), "utf8"));
  assert.deepEqual(written.spaces.map((x) => x.path), [reg.spaces[0].path], "реєстр лягає не в тимчасову домівку");
  assert.equal(JSON.parse(readFileSync(path.join(reg.spaces[0].path, "space.json"), "utf8")).name, "Особисте");
});

test("4б: порожній DEAI_HOME і зіпсований старий tasks.json — смуга помилки, а не привітання; полагодили — файл мігрує", async (t) => {
  const server = await startServer(null, { portBase: WELCOME_PORT_BASE, spaces: [] });
  t.after(() => stop(server.child));
  assert.equal(existsSync(server.legacyFile), false, "свідок: старого файла ще нема");
  /* Те, що пише рука дизайнера по ONBOARDING і не доводить до кінця: обрізаний JSON. */
  writeFileSync(server.legacyFile, '{"current": "a", "tasks": {"a": {"dir": "/work/a"');
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(`${server.url}/app/`);

  await page.waitForSelector("#bar .errbar", { timeout: 15000 });
  assert.match(await text(page, "#bar .errbar"), /Файл задач цього простору не читається/, "причина смуги — не про простір");
  assert.equal(await page.locator("#tasks-home .th-welcome").count(), 0, "зіпсований файл показано як чисту машину (привітання)");
  /* Екран «Задачі» теж не зводиться до привітання. */
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home h1.th-h");
  await page.waitForTimeout(600);
  assert.equal(await page.locator("#tasks-home .th-welcome").count(), 0, "екран «Задачі» привітав замість помилки");
  assert.equal(existsSync(server.deaiHome), false, "читання створило <DEAI_HOME>");

  /* Полагодили — наступне читання мігрує як завжди: зʼявляється простір і його фішка. */
  writeFileSync(server.legacyFile, JSON.stringify({ design_work_root: path.join(server.home, "Liga"), registry: {}, tasks: {} }));
  await page.reload();
  await waitBarReady(page, 15000);
  assert.equal(await page.locator("#bar .errbar").count(), 0, "смуга помилки лишилась після ремонту файла");
  assert.equal((await spacesApi(server.url)).spaces.length, 1, "старий файл не мігрував після ремонту");
});

test("5: у «P» жодного запиту за межі машини — рамка макета, коментатор, «Огляд», прямий ch=project", async (t) => {
  const requests = [];
  const { page, context, url } = await boot(t, { first: "p", requests });
  await goTasks(page);
  await waitText(page, "#bar .space-name", "P");
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });

  /* Рамка макета й коментатор просять лише локальний канал (простір без інтеграцій): свіже завантаження рамки це й покаже. */
  await page.reload();
  await waitBarReady(page);
  await page.waitForFunction(() => {
    const w = document.getElementById("frame")?.contentWindow;
    return Boolean(w && w.CommentLayer && w.CommentLayer._inited);
  }, null, { timeout: 20000 });
  const src = await frameSrc(page);
  assert.match(src, /^\/commented\?/, `рамка макета: ${src}`);
  assert.ok(!/ch=project/.test(src), `рамка просить проєктний канал у просторі без інтеграцій: ${src}`);

  /* «Огляд»: кадри, коментатор полотна. Без наведення на Figma й без знімка піна —
     це дії, що ведуть назовні (capture.js), і сценарій їх не торкається. */
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card").first().waitFor({ timeout: 20000 });
  await page.waitForFunction(() => Boolean(document.querySelector("#canvas [data-comment-layer]")), null, { timeout: 20000 });
  await page.waitForTimeout(1500);   // кадри, коментатор і автозʼємка встигають піти в мережу

  /* Прямий запит `ch=project` до сервера: другий рубіж — сервер сам знижує канал, а не
     покладається на те, що клієнт не спитає. */
  const direct = await context.newPage();
  await direct.goto(`${url}/commented?it=it1&page=holovna&ch=project`);
  await direct.waitForLoadState("load");
  await direct.waitForTimeout(800);
  const html = await (await fetch(`${url}/commented?it=it1&page=holovna&ch=project`)).text();
  assert.ok(!/supabase|jsdelivr/i.test(html), "сервер віддав у просторі без інтеграцій сніпет Supabase");
  assert.ok(/local-adapter/.test(html), "свідок: віддано локальний коментатор");

  /* Свідки: запити справді були (інакше «жодного зовнішнього» зеленіло б на порожнечі). */
  assert.ok(requests.some((u) => /\/commented\?/.test(u)), "свідок: рамка макета не запитувалась");
  assert.ok(requests.some((u) => /\/api\/shots/.test(u)), "свідок: «Огляд» не питав кадрів");
  assert.ok(requests.length > 20, `свідок: замало запитів (${requests.length})`);
  const outside = requests.filter((u) => {
    const x = new URL(u);
    if (["data:", "blob:", "about:"].includes(x.protocol)) return false;
    return !(["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname));
  });
  assert.deepEqual(outside, [], `запити за межі машини з простору без інтеграцій:\n${outside.join("\n")}`);
});

test("6: відмова сервера лишається в майстрі — тека, що перетинається зі старим простором, не закриває крок 1", async (t) => {
  const { page, byId, url } = await boot(t);
  await openSpaces(page);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
  await page.fill("#sp-name", "Dup");
  await page.fill("#sp-path", path.join(byId.p.path, "inner"));
  await page.click('form[data-form="space"] [data-a="ok"]');

  await page.waitForFunction(() => {
    const e = document.getElementById("wz-err");
    return Boolean(e && !e.hidden && e.textContent.trim());
  });
  assert.equal(await page.locator('form[data-form="space"]').count(), 1, "крок 1 закрився на відмові");
  assert.match(await text(page, "#wz-err"), /перетинається/, "причина відмови не названа");
  assert.equal(await page.getAttribute("#wz-err", "role"), "alert");
  assert.equal((await spacesApi(url)).spaces.length, 2, "відмовлений простір усе одно зʼявився в реєстрі");
  await page.click('form[data-form="space"] [data-a="cancel"]');
  await page.waitForFunction(() => !document.querySelector('form[data-form="space"]'));
});

guardRealDeai("7: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");

/**
 * Етап Д (0.30.0), Task 6 — «Нова задача» картка-форма в сітці екрана «Задачі»: живе проведення.
 *
 * Розмітку стережуть юніти (`tests/tasks-home.test.mjs`, `tests/space-dialogs.test.mjs`); тут те, чого вони не бачать:
 * що клік по картці «+» ставить форму на місці й дає фокус назві, що Enter створює й відкриває задачу, що Esc і «Скасувати»
 * вертають картку з фокусом, що набране переживає перемальовку сітки (клік по чипу статусу), що id із кошика дає помилку
 * під полем БЕЗ запиту, що стрілки ходять і по картці «+», а Enter у пошуку відкриває першу ЗАДАЧУ, а не «+».
 */
import "./_spaces-kit.mjs";
import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";
import { VIEW, stop } from "./_spaces-kit.mjs";

const PORT_BASE = 27300;

const PAGE = (mark) => `<!doctype html><h1>${mark}</h1>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Простір «P» без дашборда з двома задачами x і y; екран «Задачі» відкрито. */
async function studio(t, offset, xOver = {}) {
  const X = taskFixture({ html: () => PAGE("X"), pages: ["holovna"] });
  const Y = taskFixture({ html: () => PAGE("Y"), pages: ["holovna"] });
  const server = await startServer(null, {
    portBase: PORT_BASE + offset,
    spaces: [{ name: "P", id: "p", color: "space-3", tasks: { x: { dir: X.dir, title: "X", ...xOver }, y: { dir: Y.dir, title: "Y" } } }],
  });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#th-grid [data-th="newtask"]');
  return { server, page, url: server.url, file: path.join(server.spaces[0].path, "tasks.json") };
}

const readTasks = (file) => JSON.parse(readFileSync(file, "utf8")).tasks;
const cur = async (url) => (await (await fetch(`${url}/api/tasks`)).json()).current;
const active = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return a ? `${a.tagName}#${a.id}.${a.dataset?.th ?? ""}` : "";
});
const homeHidden = (page) => page.evaluate(() => document.getElementById("tasks-home").hidden);

test("нова задача карткою: клік → форма на місці, id за назвою, Enter створює й відкриває; tasks.json має задачу", async (t) => {
  const { page, url, file } = await studio(t, 0);
  assert.equal(await page.locator(".th-head [data-th=\"newtask\"]").count(), 0, "кнопка в голові лишилась");
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  assert.equal(await page.locator('#th-grid [data-th="newtask"]').count(), 0, "картка «+» лишилась поруч із формою");
  assert.equal(await active(page), "INPUT#tf-title.", "фокус не на назві");
  assert.equal(await page.locator("#th-new-slot .cv-ask, .cv-ask-scrim").count(), 0, "форма відкрилась діалогом, а не на місці");

  await page.keyboard.type("Landing page");
  assert.equal(await page.inputValue("#tf-id"), "landing-page", "id не йде за назвою");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForSelector('form[data-form="task"]', { state: "detached" });
  assert.equal(await cur(url), "landing-page", "створена задача не стала поточною");
  const row = readTasks(file)["landing-page"];
  assert.ok(row, "tasks.json без нової задачі");
  assert.equal(row.title, "Landing page");
});

test("нова задача карткою: Esc і «Скасувати» вертають картку «+» з фокусом; набране в формі переживає клік по чипу статусу", async (t) => {
  const { page } = await studio(t, 100);
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.keyboard.type("Чернетка");
  await page.fill("#tf-tags", "alpha");
  /* Клік по чипу статусу перемальовує сітку (`paintHomeLower`): жива форма мусить переїхати в новий слот разом з набраним. */
  await page.click('#tasks-home [data-th="status"][data-v="done"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  assert.equal(await page.inputValue("#tf-title"), "Чернетка", "назва зникла після перемальовки сітки");
  assert.equal(await page.inputValue("#tf-tags"), "alpha", "мітки зникли після перемальовки сітки");
  assert.equal(await page.locator('#th-grid form[data-form="task"]').count(), 1, "форма не в сітці");

  await page.focus("#tf-title");
  await page.keyboard.press("Escape");
  await page.waitForSelector('#th-grid [data-th="newtask"]');
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "Esc лишив форму");
  assert.equal(await active(page), "BUTTON#.newtask", "після Esc фокус не на картці «+»");

  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  assert.equal(await page.inputValue("#tf-title"), "", "нова форма успадкувала набране");
  await page.click('#th-new-slot [data-a="cancel"]');
  await page.waitForSelector('#th-grid [data-th="newtask"]');
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "«Скасувати» лишив форму");
  assert.equal(await active(page), "BUTTON#.newtask", "після «Скасувати» фокус не на картці «+»");
});

test("нова задача карткою: id із кошика — помилка під полем id, запиту нема", async (t) => {
  const { page, url, file } = await studio(t, 200);
  const del = await fetch(`${url}/api/task-delete`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: "x" }) });
  assert.equal(del.status, 200, "кошик не підготовлено");
  /* Екран перечитує дані на вході: вийти й увійти, щоб `homeData.trash` побачив запис. */
  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#th-grid [data-th="newtask"]');
  const before = readFileSync(file, "utf8");
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.keyboard.type("Ікс");
  await page.fill("#tf-id", "x");
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST") posts.push(r.url()); });
  await page.click('#th-new-slot [data-a="ok"]');
  await page.waitForFunction(() => /кошик/i.test(document.querySelector('#th-new-slot [data-form-error]')?.textContent || ""));
  assert.equal(await page.getAttribute("#tf-id", "aria-invalid"), "true", "помилку не привʼязано до поля id");
  assert.deepEqual(posts, [], "запит створення пішов попри кошик");
  assert.equal(readFileSync(file, "utf8"), before, "відмова змінила tasks.json");
  assert.equal(await page.locator('#th-new-slot form[data-form="task"]').count(), 1, "форма закрилась на помилці");
  /* Автопідстановка id обходить id із кошика: назва «x» не дає зайнятого id. */
  await page.fill("#tf-id", "");
  await page.fill("#tf-title", "x");
  assert.notEqual(await page.inputValue("#tf-id"), "x", "автопідстановка взяла id із кошика");
});

test("клавіатура: стрілки ходять і по картці «+», Enter на ній відкриває форму; Enter у пошуку відкриває першу ЗАДАЧУ", async (t) => {
  const { page } = await studio(t, 300);
  await page.focus("#th-q");
  await page.keyboard.press("ArrowDown");
  assert.equal(await active(page), "BUTTON#.newtask", "↓ з пошуку не стала на картку «+»");
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.th), "open", "→ не перейшла на задачу");
  await page.keyboard.press("ArrowLeft");
  assert.equal(await active(page), "BUTTON#.newtask", "← не вернула на «+»");
  await page.keyboard.press("Enter");
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  assert.equal(await active(page), "INPUT#tf-title.", "Enter на «+» не поставив фокус на назву");
  await page.keyboard.press("Escape");
  await page.waitForSelector('#th-grid [data-th="newtask"]');

  /* Пробіл теж відкриває. */
  await page.focus('#th-grid [data-th="newtask"]');
  await page.keyboard.press(" ");
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.keyboard.press("Escape");
  await page.waitForSelector('#th-grid [data-th="newtask"]');

  /* Enter у пошуку: перша картка в сітці — «+», але відкривається задача. */
  await page.focus("#th-q");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "Enter у пошуку відкрив форму");
  assert.equal(await homeHidden(page), true, "Enter у пошуку не відкрив задачу");
});

test("нова задача: форма вже не жива, коли відповідь прийшла (людина відкрила іншу задачу) — без переходу, є тост", async (t) => {
  const { page, url, file } = await studio(t, 400);
  /* Тримаємо запит створення: так імітується довгий клон, під час якого людина йде геть. */
  let release;
  const gate = new Promise((r) => { release = r; });
  await page.route("**/api/task-new", async (route) => { await gate; await route.continue(); });
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.keyboard.type("Фонова");
  await page.fill("#tf-id", "fon");
  await page.click('#th-new-slot [data-a="ok"]');
  await page.waitForSelector('#th-new-slot form[aria-busy]');
  /* Поки запит висить, відкриваємо задачу y: екран «Задачі» закрито. */
  await page.click('#th-grid [data-th="open"][data-id="y"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForTimeout(1200);   // відкриття y доїхало до кінця; запит створення — єдине, що ще висить (networkidle його б чекав)
  const frameBefore = await page.getAttribute("#frame", "src");
  assert.ok(frameBefore && frameBefore !== "about:blank", "задачу y не відкрито");
  release();
  await page.waitForFunction(() => /Фонова/.test(document.getElementById("cv-toast")?.textContent || ""));
  assert.equal(await homeHidden(page), true, "екран «Задачі» відкрився знову");
  /* Сервер робить нову задачу поточною у себе; клієнт — ні: рамка показує те, що людина відкрила. */
  assert.equal(await page.getAttribute("#frame", "src"), frameBefore, "створена задача перехопила рамку");
  assert.ok(readTasks(file).fon, "задачу не створено");
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "форма лишилась у схованому DOM");
});

/* ═══════════════════════ Task 7: меню картки, «Мітки…» з меню, перейменування на місці ═══════════════════════ */

const itemOf = (page) => page.evaluate(() => document.activeElement?.dataset?.th ?? document.activeElement?.tagName);
const MORE = (id) => `#tasks-home .th-more[data-id="${id}"]`;

test("меню: «⋯» відкриває з фокусом на першому пункті; ↓/↑ по колу; Esc закриває й вертає фокус на «⋯»; клік повз — закриває", async (t) => {
  const { page } = await studio(t, 500);
  await page.click(MORE("x"));
  await page.waitForSelector("#th-menu");
  assert.equal(await page.getAttribute(MORE("x"), "aria-expanded"), "true");
  assert.equal(await homeHidden(page), false, "клік по «⋯» відкрив задачу");
  assert.equal(await itemOf(page), "rename", "фокус не на першому пункті");
  await page.keyboard.press("ArrowDown");
  assert.equal(await itemOf(page), "tags");
  await page.keyboard.press("ArrowDown");
  assert.equal(await itemOf(page), "delete");
  await page.keyboard.press("ArrowDown");
  assert.equal(await itemOf(page), "rename", "↓ з останнього не пішла по колу");
  await page.keyboard.press("ArrowUp");
  assert.equal(await itemOf(page), "delete", "↑ з першого не пішла по колу");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#th-menu").count(), 0, "Esc не закрив меню");
  assert.equal(await homeHidden(page), false, "Esc закрив ще й екран");
  assert.equal(await page.getAttribute(MORE("x"), "aria-expanded"), "false");
  assert.equal(await page.evaluate(() => document.activeElement?.className), "th-more", "фокус не на «⋯»");
  /* Повторний клік по «⋯» — тогл. */
  await page.click(MORE("x"));
  await page.waitForSelector("#th-menu");
  await page.click(MORE("x"));
  assert.equal(await page.locator("#th-menu").count(), 0, "другий клік по «⋯» не закрив меню");
  /* Клік повз закриває й нічого більше не робить: картка під курсором не відкривається. */
  await page.click(MORE("x"));
  await page.waitForSelector("#th-menu");
  await page.click('#tasks-home .th-card[data-id="y"] .th-ttl');
  assert.equal(await page.locator("#th-menu").count(), 0, "клік повз не закрив меню");
  assert.equal(await page.getAttribute(MORE("x"), "aria-expanded"), "false");
  assert.equal(await homeHidden(page), false, "клік повз меню відкрив картку");
});

test("меню: перемальовка сітки прибирає меню, а aria-expanded не застрягає", async (t) => {
  const { page } = await studio(t, 550);
  await page.click(MORE("x"));
  await page.waitForSelector("#th-menu");
  await page.fill("#th-q", "x");
  await page.waitForFunction(() => !document.getElementById("th-menu"));
  assert.equal(await page.getAttribute(MORE("x"), "aria-expanded"), "false", "aria-expanded застряг після перемальовки");
});

test("меню: правий клік по картці — меню в точці кліку; Shift+F10 на картці — меню під «⋯»", async (t) => {
  const { page } = await studio(t, 600);
  const card = await page.locator('#tasks-home .th-card[data-id="y"]').boundingBox();
  const px = card.x + 40, py = card.y + 60;
  await page.mouse.click(px, py, { button: "right" });
  await page.waitForSelector("#th-menu");
  const box = await page.locator("#th-menu").boundingBox();
  assert.ok(Math.abs(box.x - px) < 4 && Math.abs(box.y - py) < 4, `меню не в точці кліку: ${box.x},${box.y} проти ${px},${py}`);
  assert.equal(await homeHidden(page), false, "правий клік відкрив задачу");
  await page.keyboard.press("Escape");
  /* Правий клік по картці «+» меню не дає. */
  const plus = await page.locator('#tasks-home [data-th="newtask"]').boundingBox();
  await page.mouse.click(plus.x + 20, plus.y + 20, { button: "right" });
  assert.equal(await page.locator("#th-menu").count(), 0, "меню на картці «+»");

  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("Shift+F10");
  await page.waitForSelector("#th-menu");
  const m = await page.locator("#th-menu").boundingBox();
  const b = await page.locator(MORE("x")).boundingBox();
  assert.ok(m.y >= b.y + b.height - 1, "меню не під «⋯»");
  assert.ok(Math.abs(m.x + m.width - (b.x + b.width)) < 6, "меню не вирівняне за правим краєм «⋯»");
  assert.equal(await page.getAttribute("#th-menu", "data-for"), "x");
});

test("меню → «Мітки…» відкриває діалог міток (задача НЕ відкривається); Esc — фокус на «⋯» картки", async (t) => {
  const { page, url } = await studio(t, 700);
  const before = await cur(url);
  await page.click(MORE("y"));
  await page.waitForSelector("#th-menu");
  await page.click('#th-menu [data-th="tags"]');
  await page.waitForSelector('form[data-form="tags"]');
  assert.equal(await page.locator("#th-menu").count(), 0, "меню лишилось під діалогом");
  assert.equal(await homeHidden(page), false, "«Мітки…» відкрили задачу");
  assert.equal(await cur(url), before, "«Мітки…» переключили задачу");
  await page.keyboard.press("Escape");
  await page.waitForSelector('form[data-form="tags"]', { state: "detached" });
  assert.equal(await homeHidden(page), false, "Esc закрив ще й екран");
  assert.equal(await page.evaluate(() => document.activeElement?.className + "/" + document.activeElement?.dataset?.id), "th-more/y", "фокус не на «⋯» картки");
});

test("перейменування на картці: F2 → поле з виділеною назвою; Enter → tasks.json title, id і тека ті самі, підказка вкладки нова", async (t) => {
  const { page, file } = await studio(t, 800);
  /* Вкладка x зʼявляється, коли задачу відкрито: відкриваємо й вертаємось на екран. */
  await page.click('#tasks-home .th-card[data-id="x"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="x"]');
  await page.waitForLoadState("networkidle");   // початковий `loadHome` дочитався: його відповідь не перемалює екран під F2
  const dirBefore = readTasks(file).x.dir;
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  assert.equal(await active(page), "INPUT#th-ren.", "фокус не в полі назви");
  assert.equal(await page.evaluate(() => { const i = document.getElementById("th-ren"); return i.value.slice(i.selectionStart, i.selectionEnd); }), "X", "назву не виділено");
  assert.equal(await page.locator('#tasks-home .th-card[data-id="x"][data-th="open"]').count(), 0, "картка в перейменуванні лишилась відкривачем");
  await page.keyboard.type("Нова назва");
  await page.keyboard.press("Enter");
  /* Чекаємо на РЕЗУЛЬТАТ (нова назва на картці й фокус на ній), а не на зникнення поля: його могла зняти й стороння перемальовка. */
  await page.waitForFunction(() => /Нова назва/.test(document.querySelector('#tasks-home .th-card[data-id="x"] .th-ttl')?.textContent || "")
    && document.activeElement?.dataset?.id === "x");
  const row = readTasks(file).x;
  assert.equal(row.title, "Нова назва", "tasks.json без нової назви");
  assert.equal(row.dir, dirBefore, "тека змінилась");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id + "/" + document.activeElement?.dataset?.th), "x/open", "фокус не повернувся на картку");
  assert.match(await page.getAttribute('#tabs .tab-main[data-val="x"]', "title"), /Нова назва/, "підказка вкладки стара");
});

test("перейменування на картці: Esc — без запиту; порожнє — без запиту; втрата фокуса — зберігає", async (t) => {
  const { page, file } = await studio(t, 900);
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST" && /task-rename/.test(r.url())) posts.push(r.url()); });
  await page.focus('#tasks-home .th-card[data-id="y"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.keyboard.type("Нічого");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  assert.equal(await homeHidden(page), false, "Esc закрив ще й екран");
  assert.equal(readTasks(file).y.title, "Y", "Esc записав назву");
  await page.focus('#tasks-home .th-card[data-id="y"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.fill("#th-ren", "   ");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  assert.deepEqual(posts, [], "порожня назва дала запит");
  assert.equal(readTasks(file).y.title, "Y");
  /* Втрата фокуса зберігає. */
  await page.focus('#tasks-home .th-card[data-id="y"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.fill("#th-ren", "Зі втратою");
  await page.focus("#th-q");
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  await page.waitForFunction(() => /Зі втратою/.test(document.querySelector('#tasks-home .th-card[data-id="y"] .th-ttl')?.textContent || ""));
  assert.equal(readTasks(file).y.title, "Зі втратою");
  assert.equal(posts.length, 1);
});

test("перейменування на картці: клік по іншій картці комітить і НЕ відкриває її; через меню «Перейменувати» теж", async (t) => {
  const { page, file } = await studio(t, 1000);
  await page.click(MORE("x"));
  await page.waitForSelector("#th-menu");
  await page.click('#th-menu [data-th="rename"]');
  await page.waitForSelector("#th-ren");
  assert.equal(await page.locator("#th-menu").count(), 0, "меню лишилось під час перейменування");
  await page.fill("#th-ren", "Через меню");
  await page.click('#tasks-home .th-card[data-id="y"] .th-ttl');
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  await page.waitForFunction(() => /Через меню/.test(document.querySelector('#tasks-home .th-card[data-id="x"] .th-ttl')?.textContent || ""));
  assert.equal(readTasks(file).x.title, "Через меню", "клік повз не зберіг назву");
  assert.equal(await homeHidden(page), false, "клік по іншій картці під час перейменування відкрив її");
});

test("перейменування на картці: «клік» без pointerdown (синтетичний) по іншій картці теж комітить і не відкриває її", async (t) => {
  const { page, file } = await studio(t, 1100);
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.fill("#th-ren", "Синтетика");
  await page.evaluate(() => document.querySelector('#tasks-home .th-card[data-id="y"]').click());
  await page.waitForFunction(() => /Синтетика/.test(document.querySelector('#tasks-home .th-card[data-id="x"] .th-ttl')?.textContent || ""));
  assert.equal(readTasks(file).x.title, "Синтетика");
  assert.equal(await homeHidden(page), false, "синтетичний клік по іншій картці відкрив її");
});

test("перейменування: pointerdown + pointercancel (дотик-прокрутка) не залишає прапорця — наступний справжній клік по картці її відкриває", async (t) => {
  const { page } = await studio(t, 1200);
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.evaluate(() => {
    const y = document.querySelector('#tasks-home .th-card[data-id="y"]');
    y.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, pointerId: 7, pointerType: "touch" }));
    y.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true, pointerId: 7, pointerType: "touch" }));
  });
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  assert.equal(await homeHidden(page), false, "pointerdown сам відкрив картку");
  await page.waitForTimeout(600);   // вікно ковтання кліку (500 мс) минуло
  /* Клік БЕЗ pointerdown (клавіатурна активація): `pointerdown` прапорець скидає, а цей шлях — лише спливання вікна часу. */
  await page.evaluate(() => document.querySelector('#tasks-home .th-card[data-id="y"]').click());
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
});

test("перейменування: виділення в полі, відпущене поза ним, не комітить і нічого не робить", async (t) => {
  const { page } = await studio(t, 1300);
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST") posts.push(r.url()); });
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.evaluate(() => document.getElementById("th-ren").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, pointerId: 3 })));
  await page.evaluate(() => document.querySelector('#tasks-home .th-card[data-id="x"] .th-cbody').click());
  await page.waitForTimeout(300);
  assert.equal(await page.locator("#th-ren").count(), 1, "поле закрилось");
  assert.deepEqual(posts, [], "пішов запит");
  assert.equal(await homeHidden(page), false);
});

test("перейменування: Tab із поля зберігає назву й НЕ тягне фокус назад на картку", async (t) => {
  const { page, file } = await studio(t, 1400);
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.keyboard.type("Табуляція");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => /Табуляція/.test(document.querySelector('#tasks-home .th-card[data-id="x"] .th-ttl')?.textContent || ""));
  await page.waitForTimeout(200);
  assert.equal(readTasks(file).x.title, "Табуляція");
  const at = await page.evaluate(() => `${document.activeElement?.className}/${document.activeElement?.dataset?.id}`);
  assert.notEqual(at, "th-card/x", "фокус забрано на картку");
  assert.ok(!/^BODY|undefined\/undefined$/.test(at) && at !== "/undefined", `фокус нікуди: ${at}`);
});

test("перейменування: збій запиту (500) — тост, стара назва, і F2 знову працює", async (t) => {
  const { page, file } = await studio(t, 1500);
  await page.route("**/api/task-rename", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "boom" }) }));
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  await page.keyboard.type("Не вийде");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("cv-toast")?.textContent);
  await page.waitForFunction(() => !document.getElementById("th-ren"));
  assert.equal(readTasks(file).x.title, "X");
  assert.match(await page.textContent('#tasks-home .th-card[data-id="x"] .th-ttl'), /^\s*X\s*$/);
  await page.focus('#tasks-home .th-card[data-id="x"]');
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren", { timeout: 3000 });
});

/* ═══════════════════════ Task 8: видалення з питанням у картці, тост «Повернути» ═══════════════════════ */

/** Жива картка задачі (картка кошика теж `.th-card`, її сюди не беремо). */
const CARD = (id) => `#tasks-home .th-card:not(.th-card--trash)[data-id="${id}"]`;
const trashDirOf = (file, id) => path.join(path.dirname(readTasks(file)[id]?.dir ?? ""), ".deai-trash");
const tabIds = (page) => page.$$eval("#tabs .tab-main[data-val]", (els) => els.map((e) => e.dataset.val));

/** `studio`, де обидві задачі мають вкладки: спершу відкрито `current` (вкладка `inactive` лишається), потім людина зайшла на
 *  «Задачі». */
async function studioTabs(t, offset) {
  const s = await studio(t, offset);
  const first = await cur(s.url);
  const second = first === "x" ? "y" : "x";
  await s.page.click(CARD(second));
  await s.page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await s.page.waitForSelector(`#tabs .tab-main[data-val="${first}"]`);
  await s.page.click('#tabs [data-act="home"]');
  await s.page.waitForSelector(CARD(first));
  await s.page.waitForLoadState("networkidle");
  return { ...s, inactive: first, current: second };
}

test("видалення: Delete на картці → питання в картці з фокусом на «Скасувати»; Esc — питання зникає, нічого не видалено", async (t) => {
  const { page, file } = await studio(t, 1600);
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST" && /task-delete/.test(r.url())) posts.push(r.url()); });
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD("y")}.th-card--ask .cfm`);
  assert.equal(await page.evaluate(() => document.activeElement?.className), "cfm-no", "фокус не на «Скасувати»");
  assert.equal(await page.locator(`${CARD("y")} [data-th="menu"]`).count(), 0, "під питанням лишилась «⋯»");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  assert.equal(await homeHidden(page), false, "Esc закрив ще й екран");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id), "y", "фокус не повернувся на картку");
  assert.ok(readTasks(file).y, "Esc видалив задачу");
  assert.deepEqual(posts, [], "пішов запит");
  /* Backspace — те саме; Enter на «Скасувати» знімає питання (рідна клавіша кнопки, не з'їдена обробником картки). */
  await page.keyboard.press("Backspace");
  await page.waitForSelector(`${CARD("y")}.th-card--ask`);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  assert.ok(readTasks(file).y);
  assert.deepEqual(posts, []);
});

test("видалення: через меню «Видалити»; клік повз картку з питанням знімає питання й нічого більше не робить", async (t) => {
  const { page, file } = await studio(t, 1700);
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST") posts.push(r.url()); });
  await page.click(MORE("y"));
  await page.waitForSelector("#th-menu");
  await page.click('#th-menu [data-th="delete"]');
  await page.waitForSelector(`${CARD("y")}.th-card--ask`);
  assert.equal(await page.locator("#th-menu").count(), 0, "меню лишилось");
  await page.click(`${CARD("x")} .th-ttl`);
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  await page.waitForTimeout(200);
  assert.equal(await homeHidden(page), false, "клік повз відкрив іншу картку");
  assert.deepEqual(posts, [], "пішов запит");
  assert.ok(readTasks(file).y);
});

test("видалення неактивної: «Видалити» → картки нема, вкладка закрита, тека в .deai-trash, tasks.json.trash має запис; тост із «Повернути»", async (t) => {
  const { page, file, inactive, current, url } = await studioTabs(t, 1800);
  const dir = readTasks(file)[inactive].dir;
  const trash = trashDirOf(file, inactive);
  await page.focus(CARD(inactive));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD(inactive)} .cfm-yes`);
  await page.click(`${CARD(inactive)} .cfm-yes`);
  await page.waitForFunction((id) => !document.querySelector(`#tasks-home .th-card[data-id="${id}"]`), inactive);
  assert.deepEqual(await tabIds(page), [current], "вкладка не закрита");
  assert.equal(existsSync(dir), false, "тека лишилась на місці");
  assert.ok(readdirSync(trash).some((n) => n.startsWith(`${inactive}-`)), "теки нема в .deai-trash");
  assert.ok(JSON.parse(readFileSync(file, "utf8")).trash?.[inactive], "tasks.json.trash без запису");
  assert.equal(await cur(url), current, "поточна змінилась");
  await page.waitForSelector('#cv-toast.show [data-act="undo"]');
  assert.match(await page.textContent("#cv-toast"), /видалено/);
  assert.equal(await page.locator('#tasks-home [data-th="trash"]').count(), 1, "чіпа кошика нема");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id), current, "фокус не на сусідній картці");
});

test("«Повернути» з тосту: задача, тека й вкладка на своїх місцях; поточна не змінилась", async (t) => {
  const { page, file, inactive, current, url } = await studioTabs(t, 1900);
  const dir = readTasks(file)[inactive].dir;
  const before = await tabIds(page);
  assert.deepEqual([...before].sort(), ["x", "y"]);
  await page.click(`${CARD(inactive)} [data-th="menu"]`);
  await page.click('#th-menu [data-th="delete"]');
  await page.click(`${CARD(inactive)} .cfm-yes`);
  await page.waitForSelector('#cv-toast.show [data-act="undo"]');
  /* Кнопка доступна з клавіатури, але фокус автоматично не забрано. */
  assert.notEqual(await page.evaluate(() => document.activeElement?.dataset?.act), "undo", "фокус забрано в тост");
  await page.click('#cv-toast [data-act="undo"]');
  await page.waitForSelector(CARD(inactive));
  await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-main[data-val]").length === 2);
  assert.deepEqual(await tabIds(page), before, "вкладка не на своєму місці");
  assert.ok(readTasks(file)[inactive], "tasks.json без задачі");
  assert.ok(existsSync(dir), "теки нема");
  assert.equal(await cur(url), current, "поточна змінилась");
  assert.equal(await page.locator('#tasks-home [data-th="trash"]').count(), 0, "чіп кошика лишився порожнім");
  assert.equal(await page.evaluate(() => document.getElementById("cv-toast").classList.contains("show")), false, "тост лишився після «Повернути»");
});

test("видалення ПОТОЧНОЇ: «відкрита зараз» переходить на ту, що назвав сервер; екран лишається відкритим; вихід через вкладку не падає", async (t) => {
  const { page, url, inactive, current } = await studioTabs(t, 2000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.focus(CARD(current));
  await page.keyboard.press("Delete");
  await page.click(`${CARD(current)} .cfm-yes`);
  await page.waitForFunction((id) => !document.querySelector(`#tasks-home .th-card[data-id="${id}"]`), current);
  assert.equal(await cur(url), inactive, "сервер не переніс поточну");
  assert.equal(await homeHidden(page), false, "екран закрився");
  await page.waitForFunction((id) => document.querySelector(`#tasks-home .th-card[data-id="${id}"] .th-curb`), inactive);
  await page.click(`#tabs .tab-main[data-val="${inactive}"]`);
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.deepEqual(errors, [], "помилки сторінки");
});

test("видалення ОБОХ задач: екран лишається, «поточної» нема, логотип не падає", async (t) => {
  const { page, url } = await studioTabs(t, 2100);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  for (const id of ["x", "y"]) {
    await page.focus(CARD(id));
    await page.keyboard.press("Delete");
    await page.click(`${CARD(id)} .cfm-yes`);
    await page.waitForFunction((k) => !document.querySelector(`#tasks-home .th-card[data-id="${k}"]`), id);
  }
  await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-main[data-val]").length === 0);
  /* Фокус ставиться в кінці `deleteTask` (після скидання стану й перемальовок): чекаємо його кінця (тост), а не початку. */
  await page.waitForSelector("#cv-toast.show");
  await page.waitForLoadState("networkidle");
  assert.equal(await homeHidden(page), false, "екран закрився");
  assert.equal(await cur(url), null, "сервер назвав поточну");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.th), "newtask", `після останнього видалення фокус не на «+»: ${await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 120))}`);
  assert.equal(await page.evaluate(() => document.getElementById("cv-toast").getAttribute("role")), "status", "тост без role=status");
  await page.click('#tabs [data-act="home"]');
  await page.waitForTimeout(300);
  assert.equal(await homeHidden(page), false);
  assert.ok(await page.locator('#tasks-home [data-th="newtask"]').count(), "нема картки «+»");
  assert.deepEqual(errors, [], "помилки сторінки");
});

test("питання «Claude працює»: удар /api/claude-status in_progress для задачі → питання інше", async (t) => {
  const { page } = await studio(t, 2200);
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD("y")} .cfm`);
  assert.doesNotMatch(await page.textContent(`${CARD("y")} .cfm-t`), /Claude/, "питання без удару вже згадує Claude");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  const ok = await page.evaluate(async () => (await fetch("/api/claude-status", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "y", phase: "design", status: "in_progress", note: "", session: "live" }) })).ok);
  assert.ok(ok, "удар не прийнято");
  /* Опит стану Claude на вкладках — одразу (`visibilitychange`); чекаємо, поки питання почне згадувати Claude. */
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await page.waitForFunction(async () => (await (await fetch("/api/claude-statuses")).json()).tasks?.y?.state === "working");
  await page.waitForTimeout(500);
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD("y")} .cfm`);
  assert.match(await page.textContent(`${CARD("y")} .cfm-t`), /Claude працює/, "питання не знає, що Claude працює");
});

test("видалення не вдалось (сервер 500, простір не пишеться): картка лишається, тост із причиною, теку не рушено", async (t) => {
  const { page, file } = await studio(t, 2300);
  const spaceDir = path.dirname(file);
  const dir = readTasks(file).y.dir;
  chmodSync(spaceDir, 0o555);
  t.after(() => { try { chmodSync(spaceDir, 0o755); } catch (e) {} });
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.click(`${CARD("y")} .cfm-yes`);
  await page.waitForFunction(() => /Не вдалося/.test(document.getElementById("cv-toast")?.textContent || ""));
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  assert.ok(await page.locator(CARD("y")).count(), "картка зникла");
  assert.ok(existsSync(dir), "теку перенесено");
  assert.ok(readTasks(file).y, "tasks.json без задачі");
  assert.equal(await page.locator('#cv-toast [data-act="undo"]').count(), 0, "тост збою з «Повернути»");
});

/* ═══════════════════════ Task 9: вигляд кошика — повернути, видалити назавжди ═══════════════════════ */

const TRASH_CARD = (id) => `#tasks-home .th-card--trash[data-id="${id}"]`;
const trashChip = '#tasks-home [data-th="trash"]';
/** Видалити задачу з екрана «Задачі» клавіатурою й дочекатися, що картки нема. */
async function trashIt(page, id) {
  await page.focus(CARD(id));
  await page.keyboard.press("Delete");
  await page.click(`${CARD(id)} .cfm-yes`);
  await page.waitForFunction((k) => !document.querySelector(`#tasks-home .th-card[data-id="${k}"]`), id);
}
const inTrashView = (page) => page.evaluate(() => !!document.querySelector("#tasks-home .th-card--trash"));

test("кошик: чип «Кошик · N» зʼявляється після видалення; вигляд — знебарвлені картки, «Повернути», без «+» і міток", async (t) => {
  const { page } = await studio(t, 2400);
  assert.equal(await page.locator(trashChip).count(), 0, "чип є при порожньому кошику");
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  assert.equal(await page.getAttribute(trashChip, "aria-pressed"), "false");
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("y"));
  assert.equal(await page.getAttribute(trashChip, "aria-pressed"), "true");
  assert.equal(await page.locator(`${TRASH_CARD("y")} [data-th="restore"]`).count(), 1, "нема «Повернути»");
  assert.equal(await page.locator(`${TRASH_CARD("y")} [data-th="menu"][data-trash="1"]`).count(), 1, "нема «⋯»");
  assert.equal(await page.locator('#tasks-home [data-th="newtask"]').count(), 0, "«+» у кошику");
  assert.equal(await page.locator('#tasks-home [data-th="tag"], #tasks-home [data-th="designer"]').count(), 0, "мітки в кошику");
  assert.equal(await page.locator('#tasks-home .th-card:not(.th-card--trash)').count(), 0, "живі картки поруч із кошиком");
  /* Enter на картці кошика нічого не відкриває; Delete — нічого не питає. */
  const switches = [];
  page.on("request", (r) => { if (/\/api\/task-(switch|delete)/.test(r.url())) switches.push(r.url()); });
  await page.focus(TRASH_CARD("y"));
  await page.keyboard.press("Enter");
  await page.keyboard.press("Delete");
  /* Два кадри перемальовки: усе, що клавіші мали б запустити синхронно, уже сталось. */
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  assert.deepEqual(switches, [], "Enter/Delete на картці кошика надіслали запит");
  assert.equal(await homeHidden(page), false, "Enter відкрив картку кошика");
  assert.equal(await page.locator(".th-card--ask").count(), 0, "Delete спитав про видалення з кошика");
  /* Повторний клік по чипу виходить із кошика. */
  await page.click(trashChip);
  await page.waitForSelector(CARD("x"));
  assert.equal(await inTrashView(page), false);
});

test("кошик → «Повернути»: задача в «Моїх», тека на місці; порожній кошик — вигляд вимкнено, чипа нема; наступне видалення не вертає в кошик", async (t) => {
  const { page, file, url } = await studio(t, 2500);
  const dir = readTasks(file).y.dir;
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.click(trashChip);
  await page.waitForSelector(`${TRASH_CARD("y")} [data-th="restore"]`);
  await page.click(`${TRASH_CARD("y")} [data-th="restore"]`);
  await page.waitForSelector(`${CARD("y")}:not(.th-card--trash)`);
  assert.equal(await page.locator(trashChip).count(), 0, "чип лишився при порожньому кошику");
  assert.equal(await inTrashView(page), false, "вигляд кошика лишився");
  assert.ok(readTasks(file).y, "tasks.json без задачі");
  assert.ok(existsSync(dir), "теки нема");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "фокус не на пошуку");
  /* Вигляд справді вимкнено (а не лише прихований порожнім кошиком): нове видалення показує «Мої», а не кошик. */
  await trashIt(page, "x");
  await page.waitForSelector(trashChip);
  assert.equal(await inTrashView(page), false, "кошик ожив сам");
  assert.equal(await page.getAttribute(trashChip, "aria-pressed"), "false");
  assert.ok(await page.locator(CARD("y")).count(), "«Мої» не показано");
  assert.ok(url);
});

test("кошик: «Повернути» з двома в кошику — фокус на наступній картці кошика; меню «Повернути» теж працює", async (t) => {
  const { page, file } = await studio(t, 2600);
  await trashIt(page, "x");
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("x"));
  await page.waitForSelector(TRASH_CARD("y"));
  const first = await page.evaluate(() => document.querySelector("#tasks-home .th-card--trash").dataset.id);
  const second = first === "x" ? "y" : "x";
  await page.click(`${TRASH_CARD(first)} [data-th="menu"]`);
  await page.click('#th-menu [data-th="restore"]');
  await page.waitForFunction((id) => !document.querySelector(`#tasks-home .th-card--trash[data-id="${id}"]`), first);
  assert.ok(readTasks(file)[first], "задача не повернута");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id), second, "фокус не на сусідній картці кошика");
  assert.equal(await inTrashView(page), true, "вигляд кошика зник при непорожньому кошику");
});

test("кошик → меню → «Видалити назавжди»: питання в картці; Esc скасовує; «Видалити назавжди» → теки нема, tasks.json.trash[id] = {purged}", async (t) => {
  const { page, file } = await studio(t, 2700);
  await trashIt(page, "y");
  /* Тека кошика спільна для всіх прогонів (поруч із задачею), тож дивимось саме на теку цього запису. */
  const gone = JSON.parse(readFileSync(file, "utf8")).trash.y.trashDir;
  assert.ok(existsSync(gone), "теки кошика нема одразу після видалення");
  await page.waitForSelector(trashChip);
  await page.click(trashChip);
  await page.click(`${TRASH_CARD("y")} [data-th="menu"]`);
  await page.click('#th-menu [data-th="purge"]');
  await page.waitForSelector(`${TRASH_CARD("y")}.th-card--ask .cfm-yes`);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("cfm-no")), true, "фокус не на «Скасувати»");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  assert.ok(existsSync(gone), "Esc знищив теку");
  /* Shift+F10 на картці кошика відкриває меню кошика. */
  await page.focus(TRASH_CARD("y"));
  await page.keyboard.press("Shift+F10");
  await page.waitForSelector('#th-menu [data-th="purge"]');
  await page.keyboard.press("Escape");
  await page.click(`${TRASH_CARD("y")} [data-th="menu"]`);
  await page.click('#th-menu [data-th="purge"]');
  await page.click(`${TRASH_CARD("y")} .cfm-yes`);
  await page.waitForFunction(() => !document.querySelector("#tasks-home .th-card--trash"));
  assert.equal(existsSync(gone), false, "теку не знищено");
  const rec = JSON.parse(readFileSync(file, "utf8")).trash?.y;
  assert.ok(rec && "purged" in rec, "надгробка нема");
  assert.equal(await page.locator(trashChip).count(), 0, "чип лишився");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "фокус не на пошуку");
  await page.waitForSelector('#cv-toast.show');
  assert.match(await page.textContent("#cv-toast"), /назавжди/);
});

test("кошик: клік по статусному чипу виходить із вигляду кошика; відкриття кошика закриває форму «+»", async (t) => {
  const { page } = await studio(t, 2800);
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("y"));
  assert.equal(await page.locator('form[data-form="task"]').count(), 0, "форма пережила кошик");
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForSelector(CARD("x"));
  assert.equal(await inTrashView(page), false, "лишилась у кошику");
  assert.equal(await page.getAttribute(trashChip, "aria-pressed"), "false");
});

/** Записати у `tasks.json` простору зміну (імітація «іншого вікна» чи агента). */
const editTasksFile = (file, fn) => { const cfg = JSON.parse(readFileSync(file, "utf8")); fn(cfg); writeFileSync(file, JSON.stringify(cfg, null, 2)); };
/** Витіснити «Кошик» зі сторінки як повернення у вікно: `focus` перечитує екран (не частіше за вікно `shouldRefreshHome`). */
const refetchOnFocus = (page, gone) => page.waitForFunction((sel) => {
  window.dispatchEvent(new Event("focus"));
  return !document.querySelector(sel);
}, gone);

test("кошик спорожнили деінде: вигляд вимкнено, наступне видалення показує «Мої», а не кошик", async (t) => {
  const { page, file } = await studio(t, 2900);
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("y"));
  editTasksFile(file, (c) => { c.trash = {}; });
  await refetchOnFocus(page, trashChip);
  await trashIt(page, "x");
  await page.waitForSelector(trashChip);
  assert.equal(await inTrashView(page), false, "вигляд кошика ожив після чужого спорожнення");
  assert.equal(await page.getAttribute(trashChip, "aria-pressed"), "false");
  assert.equal(await page.locator('#tasks-home [data-th="newtask"]').count(), 1, "«Мої» не показано (нема «+»)");
});

test("кошик: подвійний клік по «Повернути» — один запит, без помилки; подвійне підтвердження «назавжди» — теж один", async (t) => {
  const { page } = await studio(t, 3000);
  const posts = { restore: 0, purge: 0 };
  page.on("request", (r) => {
    if (r.url().endsWith("/api/task-restore")) posts.restore += 1;
    if (r.url().endsWith("/api/task-purge")) posts.purge += 1;
  });
  await trashIt(page, "x");
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("x"));
  await page.evaluate(() => { const b = document.querySelector('.th-card--trash[data-id="x"] [data-th="restore"]'); b.click(); b.click(); });
  await page.waitForSelector(CARD("x"), { state: "attached" }).catch(() => {});
  await page.waitForFunction(() => !document.querySelector('.th-card--trash[data-id="x"]'));
  assert.equal(posts.restore, 1, "повернення пішло двічі");
  assert.equal(await page.evaluate(() => /Не вдалося|уже є/.test(document.getElementById("cv-toast")?.textContent || "")), false, "тост-помилка на вдалому поверненні");
  await page.click(`${TRASH_CARD("y")} [data-th="menu"]`);
  await page.click('#th-menu [data-th="purge"]');
  await page.evaluate(() => { const b = document.querySelector('.th-card--trash[data-id="y"] .cfm-yes'); b.click(); b.click(); });
  await page.waitForFunction(() => !document.querySelector(".th-card--trash"));
  assert.equal(posts.purge, 1, "знищення пішло двічі");
});

test("кошик → «Повернути»: тека вже існує — тост, картка лишається в кошику", async (t) => {
  const { page, file } = await studio(t, 3100);
  const dir = readTasks(file).y.dir;
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  mkdirSync(dir, { recursive: true });
  await page.click(trashChip);
  await page.click(`${TRASH_CARD("y")} [data-th="restore"]`);
  await page.waitForFunction(() => /Тека задачі вже існує/.test(document.getElementById("cv-toast")?.textContent || ""));
  assert.equal(await page.locator(TRASH_CARD("y")).count(), 1, "картка зникла з кошика");
  assert.ok(JSON.parse(readFileSync(file, "utf8")).trash?.y, "запис кошика зник");
});

test("кошик → «Повернути»: id уже зайнятий живою задачею — тост, картка лишається в кошику", async (t) => {
  const { page, file } = await studio(t, 3200);
  const xdir = readTasks(file).x.dir;
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  editTasksFile(file, (c) => { c.tasks.y = { dir: xdir, title: "Y2" }; });
  await page.click(trashChip);
  await page.click(`${TRASH_CARD("y")} [data-th="restore"]`);
  await page.waitForFunction(() => /Задача з таким ідентифікатором уже є/.test(document.getElementById("cv-toast")?.textContent || ""));
  assert.equal(await page.locator(TRASH_CARD("y")).count(), 1, "картка зникла з кошика");
  assert.ok(JSON.parse(readFileSync(file, "utf8")).trash?.y, "запис кошика зник");
});

test("кошик → «Видалити назавжди»: збій сервера (500) — тост із причиною, питання знято, картка лишається", async (t) => {
  const { page } = await studio(t, 3300);
  await trashIt(page, "y");
  await page.waitForSelector(trashChip);
  await page.route("**/api/task-purge", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "boom" }) }));
  await page.click(trashChip);
  await page.click(`${TRASH_CARD("y")} [data-th="menu"]`);
  await page.click('#th-menu [data-th="purge"]');
  await page.click(`${TRASH_CARD("y")} .cfm-yes`);
  await page.waitForFunction(() => /Не вдалося/.test(document.getElementById("cv-toast")?.textContent || ""));
  await page.waitForFunction(() => !document.querySelector(".th-card--ask"));
  assert.equal(await page.locator(TRASH_CARD("y")).count(), 1, "картка зникла після збою");
});

/* ── Етап Д, Task 10: перейменування з вкладки, F2 у макеті, ⌘K ─────────────────────────────────────────────────── */
const POP = '.cv-ask-pop [data-form="taskname"]';
const tabOf = (id) => `#tabs .tab-main[data-val="${id}"]`;
const titleOf = (file, id) => readTasks(file)[id]?.title;
const tabTip = (page, id) => page.getAttribute(tabOf(id), "title");

/** `studioTabs`, але вже ПОЗА екраном «Задачі»: відкрита `current`, вкладка `inactive` поруч. */
async function studioCanvas(t, offset) {
  const s = await studioTabs(t, offset);
  await s.page.click(tabOf(s.current));
  await s.page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await s.page.waitForLoadState("networkidle");
  return s;
}

test("перейменування з вкладки: двічі по НЕактивній — задача перемкнулась, поповер під вкладкою; Enter → tasks.json і підказка", async (t) => {
  const { page, file, url, inactive } = await studioCanvas(t, 3400);
  await page.dblclick(tabOf(inactive));
  await page.waitForSelector(POP);
  /* Поповер зʼявляється одразу, а `task-switch` ще летить: чекаємо, поки сервер перемкнеться. */
  await page.waitForFunction(async (id) => (await (await fetch("/api/tasks")).json()).current === id, inactive);
  await page.waitForSelector(`${tabOf(inactive)}[aria-current="page"]`);
  await page.waitForLoadState("networkidle");              // перемальовка після `task-switch` дочитана: запізніла не затре нову назву
  assert.equal(await cur(url), inactive, "задача не перемкнулась");
  assert.equal(await page.inputValue("#tn-title"), inactive.toUpperCase(), "у полі не поточна назва");
  const pop = await page.locator(".cv-ask--pop").boundingBox();
  const tab = await page.locator(tabOf(inactive)).boundingBox();
  assert.ok(pop.y >= tab.y + tab.height - 2, "поповер не під вкладкою");
  await page.fill("#tn-title", "Нова назва");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  assert.equal(titleOf(file, inactive), "Нова назва");
  assert.match(await tabTip(page, inactive), /Нова назва/);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.val), inactive, "фокус не на вкладці");
});

test("перейменування з вкладки: ціль dblclick — не сама вкладка (спільний предок після перемальовки рядка) — вкладку береться з точки кліку", async (t) => {
  const { page, inactive } = await studioCanvas(t, 3500);
  /* Перший клік пари справді влучає по цій вкладці (його запамʼятовує обробник), другий — синтетичний нижче. */
  await page.click(tabOf(inactive));
  await page.waitForSelector(`${tabOf(inactive)}[aria-current="page"]`);
  const b = await page.locator(tabOf(inactive)).boundingBox();
  /* Натиск на старому вузлі, відпуск на перемальованому: ціль — `.tabs-list`, а не `.tab-main`; координати — над вкладкою. */
  await page.evaluate(({ x, y }) => {
    document.querySelector("#tabs .tabs-list").dispatchEvent(new MouseEvent("dblclick", { bubbles: true, cancelable: true, clientX: x, clientY: y }));
  }, { x: b.x + b.width / 2, y: b.y + b.height / 2 });
  await page.waitForSelector(POP);
  assert.equal(await page.inputValue("#tn-title"), inactive.toUpperCase());
});

test("перейменування з вкладки: двічі по активній → поповер; Esc — без запиту, фокус на вкладці; без змін і порожня назва — без запиту", async (t) => {
  const { page, current } = await studioCanvas(t, 3600);
  const posts = [];
  page.on("request", (r) => { if (r.method() === "POST" && /task-rename/.test(r.url())) posts.push(r.url()); });
  await page.dblclick(tabOf(current));
  await page.waitForSelector(POP);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.val), current, "фокус не на вкладці");
  await page.dblclick(tabOf(current));
  await page.waitForSelector(POP);
  await page.keyboard.press("Enter");                    // назва не змінилась
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  await page.dblclick(tabOf(current));
  await page.waitForSelector(POP);
  await page.fill("#tn-title", "   ");
  await page.keyboard.press("Enter");
  await page.waitForSelector(`${POP} [data-form-error]:not(:empty)`);
  assert.match(await page.textContent(`${POP} [data-form-error]`), /Вкажи назву/);
  assert.deepEqual(posts, [], "пішов запит");
});

test("перейменування з вкладки: збій сервера — текст помилки в поповері, назва не змінилась", async (t) => {
  const { page, file, current } = await studioCanvas(t, 3700);
  await page.route("**/api/task-rename", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "task-rename-failed" }) }));
  await page.dblclick(tabOf(current));
  await page.waitForSelector(POP);
  await page.fill("#tn-title", "Інша");
  await page.keyboard.press("Enter");
  await page.waitForSelector(`${POP} [data-form-error]:not(:empty)`);
  assert.equal(titleOf(file, current), current.toUpperCase());
});

test("перейменування: F2 у макеті → поповер під активною вкладкою; не діє в полі вводу, з модифікатором і на екрані «Задачі»", async (t) => {
  const { page, file, current } = await studioCanvas(t, 3800);
  await page.keyboard.press("Shift+F2");
  await page.waitForTimeout(200);
  assert.equal(await page.locator(POP).count(), 0, "Shift+F2 відкрив поповер");
  await page.keyboard.press("F2");
  await page.waitForSelector(POP);
  const pop = await page.locator(".cv-ask--pop").boundingBox();
  const tab = await page.locator(tabOf(current)).boundingBox();
  assert.ok(pop.y >= tab.y + tab.height - 2, "поповер не під активною вкладкою");
  await page.fill("#tn-title", "");
  await page.keyboard.press("Enter");
  await page.waitForSelector(`${POP} [data-form-error]:not(:empty)`);
  await page.fill("#tn-title", "Через F2");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  assert.equal(titleOf(file, current), "Через F2");
  /* Екран «Задачі»: F2 без картки у фокусі нічого не відкриває. */
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#th-grid");
  await page.locator("#th-grid").evaluate(() => document.activeElement?.blur());
  await page.keyboard.press("F2");
  await page.waitForTimeout(200);
  assert.equal(await page.locator(POP).count(), 0, "F2 на екрані «Задачі» відкрив поповер вкладки");
});

test("перейменування: F2, коли фокус у макеті (iframe), відкриває ОДИН поповер; у полі вводу макета — ні", async (t) => {
  const { page, current } = await studioCanvas(t, 3900);
  const fl = page.frameLocator("#frame, iframe").first();
  await fl.locator("h1").first().click();
  /* Справжній фокус усередині рамки: клік по заголовку фокус не бере, тож ставимо його на тимчасову кнопку макета. */
  await fl.locator("body").evaluate((b) => {
    const k = b.ownerDocument.createElement("button"); k.id = "fx"; k.textContent = "fx"; b.append(k); k.focus();
  });
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentDocument.activeElement?.id), "fx", "фокус не в рамці");
  await page.keyboard.press("F2");
  await page.waitForSelector(POP);
  assert.equal(await page.inputValue("#tn-title"), current.toUpperCase(), "поповер про не поточну задачу");
  /* Повторний F2 при відкритому поповері не складає другий. */
  await page.keyboard.press("F2");
  await page.waitForTimeout(250);
  assert.equal(await page.locator(POP).count(), 1, "F2 склав другий поповер");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  /* Фокус у <input> макета — F2 не діє. */
  await fl.locator("body").evaluate((b) => {
    const k = b.ownerDocument.createElement("input"); k.id = "fi"; b.append(k); k.focus();
  });
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentDocument.activeElement?.id), "fi", "фокус не в полі макета");
  await page.keyboard.press("F2");
  await page.waitForTimeout(250);
  assert.equal(await page.locator(POP).count(), 0, "F2 у полі макета відкрив поповер");
});

test("перейменування з вкладки: подвійний клік по хрестику закриває вкладку, але не відкриває перейменування сусідньої", async (t) => {
  const { page } = await studioCanvas(t, 4100);
  /* Третя вкладка: нова задача відкривається й стає вкладкою. */
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#th-grid [data-th="newtask"]');
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.keyboard.type("Третя");
  await page.fill("#tf-id", "tri");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-main").length === 3);
  await page.waitForLoadState("networkidle");
  /* Перший клік пари — справжній, по хрестику другої вкладки: вона закривається, рядок зсувається. Другий клік пари в живому
     браузері може впасти на `.tab-main` сусіда (геометрія залежить від ширини вкладок) — відтворюємо його подіями: клік
     з `detail: 2` і `dblclick` по правому сусідові. */
  const first = await page.locator("#tabs .tab-main").nth(1).getAttribute("data-val");
  assert.equal(await page.locator("#tabs .tab-main").nth(2).getAttribute("data-val"), "tri", "порядок вкладок не той");
  await page.click(`#tabs .tab-x[data-val="${first}"]`);
  await page.waitForSelector(`#tabs .tab-main[data-val="${first}"]`, { state: "detached" });
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    const el = document.querySelector('#tabs .tab-main[data-val="tri"]');
    const r = el.getBoundingClientRect();
    const o = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 };
    el.dispatchEvent(new MouseEvent("click", { ...o, detail: 2 }));
    el.dispatchEvent(new MouseEvent("dblclick", { ...o, detail: 2 }));
  });
  await page.waitForTimeout(600);
  assert.equal(await page.locator(POP).count(), 0, "поповер перейменування відкрився");
  assert.equal(await page.locator(tabOf(first)).count(), 0, "вкладку не закрито");
});

test("перейменування: запізніла відповідь /api/task, що вийшла ДО перейменування, не повертає стару назву в смугу", async (t) => {
  const { page, file, inactive } = await studioCanvas(t, 4200);
  let release; const gate = new Promise((r) => { release = r; });
  let held = false;
  await page.route("**/api/task", async (route) => {
    if (held) return route.continue();
    held = true;
    const stale = await route.fetch();       // відповідь зі СТАРОЮ назвою — знімається одразу
    await gate;
    await route.fulfill({ response: stale });
  });
  await page.click(tabOf(inactive));          // перемикання → render() висне на /api/task
  await page.waitForFunction(() => true);
  await page.waitForTimeout(300);
  assert.ok(held, "запит не зупинено");
  await page.dblclick(tabOf(inactive));
  await page.waitForSelector(POP);
  await page.fill("#tn-title", "Свіжа назва");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  assert.equal(titleOf(file, inactive), "Свіжа назва");
  release();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  assert.match(await tabTip(page, inactive), /Свіжа назва/, "підказка вкладки повернулась до старої");
  assert.match(await page.textContent("#bar"), /Свіжа назва/, "смуга повернулась до старої назви");
});

test("перейменування: ⌘K «Перейменувати задачу» → той самий поповер; на екрані «Задачі» пункту нема", async (t) => {
  const { page, current } = await studioCanvas(t, 4000);
  await page.keyboard.press("Control+k");
  await page.fill("#palq", "Перейменувати задачу");
  await page.waitForSelector('.pal-it:has-text("Перейменувати задачу")');
  await page.keyboard.press("Enter");
  await page.waitForSelector(POP);
  assert.equal(await page.inputValue("#tn-title"), current.toUpperCase());
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#th-grid");
  await page.keyboard.press("Control+k");
  await page.fill("#palq", "Перейменувати задачу");
  await page.waitForTimeout(150);
  assert.equal(await page.locator('.pal-it:has-text("Перейменувати задачу")').count(), 0);
});

/* ── Фінальні правки 0.30.0 ───────────────────────────────────────────── */

test("перейменування на картці береже ключ Jira: «KEY-1 · Old» → «New» на картці, «KEY-1 · New» у tasks.json", async (t) => {
  const { page, file } = await studio(t, 4300, { jira: "KEY-1", title: "KEY-1 · Old" });
  await page.waitForLoadState("networkidle");
  await page.focus(CARD("x"));
  await page.keyboard.press("F2");
  await page.waitForSelector("#th-ren");
  assert.equal(await page.inputValue("#th-ren"), "Old", "поле не з назвою без ключа");
  await page.fill("#th-ren", "New");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector('#tasks-home .th-card[data-id="x"] .th-ttl')?.textContent.trim() === "New");
  assert.equal(readTasks(file).x.title, "KEY-1 · New", "ключ Jira зник із tasks.json");
});

test("перейменування з вкладки береже ключ Jira: у полі «Old», у tasks.json «KEY-1 · New»", async (t) => {
  const { page, file } = await studio(t, 4400, { jira: "KEY-1", title: "KEY-1 · Old" });
  await page.click(CARD("x"));
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForSelector('#tabs .tab-main[data-val="x"]');
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("F2");
  await page.waitForSelector("#tn-title");
  assert.equal(await page.inputValue("#tn-title"), "Old", "у полі не назва без ключа");
  await page.fill("#tn-title", "New");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".cv-ask-pop"));
  assert.equal(readTasks(file).x.title, "KEY-1 · New", "ключ Jira зник із tasks.json");
});

test("кошик: запис зник із tasks.json за спиною екрана — «Видалити назавжди» дає тост «Задачі вже немає», картка зникає після перечитування", async (t) => {
  const { page, file } = await studio(t, 4500);
  await trashIt(page, "y");
  await page.click(trashChip);
  await page.waitForSelector(TRASH_CARD("y"));
  const db = JSON.parse(readFileSync(file, "utf8"));
  delete db.trash.y;
  writeFileSync(file, JSON.stringify(db));
  await page.click(`${TRASH_CARD("y")} [data-th="menu"]`);
  await page.click('#th-menu [data-th="purge"]');
  await page.click(`${TRASH_CARD("y")} .cfm-yes`);
  await page.waitForFunction(() => /Задачі вже немає/.test(document.getElementById("cv-toast")?.textContent || ""), null, { timeout: 5000 })
    .catch(async () => assert.fail(`тост не перекладено: ${await page.textContent("#cv-toast")}`));
  assert.doesNotMatch(await page.textContent("#cv-toast"), /not in the trash/, "тост із сирим англійським текстом");
  await page.waitForFunction(() => !document.querySelector("#tasks-home .th-card--trash"));
});

test("питання «Claude працює» без відкритих вкладок: Delete → варіант із Claude", async (t) => {
  const { page } = await studio(t, 4600);
  /* Поточна задача має вкладку від початку: закриваємо її, щоб `claudeAll` не опитувався зовсім. */
  for (const id of await tabIds(page)) await page.click(`#tabs .tab-x[data-val="${id}"]`);
  await page.waitForFunction(() => !document.querySelector("#tabs .tab-main[data-val]"));
  assert.equal(await homeHidden(page), false, "екран закрився разом із вкладкою");
  const ok = await page.evaluate(async () => (await fetch("/api/claude-status", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "y", phase: "design", status: "in_progress", note: "", session: "live" }) })).ok);
  assert.ok(ok, "удар не прийнято");
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD("y")} .cfm`);
  await page.waitForFunction((sel) => /Claude працює/.test(document.querySelector(sel)?.textContent || ""), `${CARD("y")} .cfm-t`);
});

test("меню задачі не переживає сторінку: відкрите меню зникає, коли ⌘K веде на «Налаштування»", async (t) => {
  const { page } = await studio(t, 4700);
  await page.click(`${CARD("x")} [data-th="menu"]`);
  await page.waitForSelector("#th-menu");
  await page.keyboard.press("Control+k");
  await page.fill("#palq", "Налаштування");
  await page.waitForSelector('.pal-it:has-text("Налаштування")');
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector("#tasks-home")?.textContent.includes("Налаштування") && !document.querySelector("#th-grid"));
  assert.equal(await page.locator("#th-menu").count(), 0, "меню задачі пережило перехід на іншу сторінку");
});

test("питання на картці, яку прибрали деінде: перечитування знімає його — коли задача зʼявиться знову, питання не воскресає", async (t) => {
  const { page, file } = await studio(t, 4800);
  await page.waitForLoadState("networkidle");
  const before = readFileSync(file, "utf8");
  await page.focus(CARD("y"));
  await page.keyboard.press("Delete");
  await page.waitForSelector(`${CARD("y")}.th-card--ask`);
  const db = JSON.parse(before);
  delete db.tasks.y;
  writeFileSync(file, JSON.stringify(db));
  await page.waitForTimeout(1000);                       // поріг між перечитуваннями з фокуса (800 мс)
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => !document.querySelector('#tasks-home .th-card[data-id="y"]'));
  writeFileSync(file, before);                           // задача повернулась (інший агент, git pull)
  await page.waitForTimeout(1000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForSelector(CARD("y"));
  await page.waitForLoadState("networkidle");
  assert.equal(await page.locator(".th-card--ask").count(), 0, "питання про зниклу картку воскресло");
});

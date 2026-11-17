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
import { readFileSync } from "node:fs";
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
async function studio(t, offset) {
  const X = taskFixture({ html: () => PAGE("X"), pages: ["holovna"] });
  const Y = taskFixture({ html: () => PAGE("Y"), pages: ["holovna"] });
  const server = await startServer(null, {
    portBase: PORT_BASE + offset,
    spaces: [{ name: "P", id: "p", color: "space-3", tasks: { x: { dir: X.dir, title: "X" }, y: { dir: Y.dir, title: "Y" } } }],
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

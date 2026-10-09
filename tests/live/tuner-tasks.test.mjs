/**
 * Живий охоронець: пакет тюнера — ПЕР-ЗАДАЧНИЙ.
 *
 * ⛔ Що саме стереже. Ключ сторінки в моделі тюнера — `${ітерація}/${сторінка}`
 * (`tunePage`, `app/app.js`), а id ітерацій ПЕР-ЗАДАЧНІ: `it1/holovna` існує в
 * КОЖНІЙ задачі. Доки перемикач задачі не забував пакет, ключі двох задач
 * збігались, і з одного пропущеного рядка виходило три різні брехні одразу:
 *   1. `reapplyTune` малював на макеті задачі Б інлайн-стилі, накручені в А —
 *      дизайнер бачив у чужому макеті правку, якої там ніхто не робив;
 *   2. перший же поворот ручки в Б клав у `.dc-tuner.json` задачі Б ОБИДВІ
 *      правки, тобто ПРИПИСУВАВ роботу задачі А задачі Б. Для фічі, чий сенс —
 *      віддати Клоду правдиву довідку «що і де правити», це найгірший з
 *      можливих провалів: інструмент не падає, він бреше;
 *   3. канал пише ПОВНИЙ пакет, тож той самий запис затирав файл задачі Б
 *      станом задачі А — рівно та діра, від якої застерігає докстрінг
 *      `loadTune` («канал без читання не зберігає, а затирає»).
 *
 * Чому ЖИВИЙ, а не юніт: пастка існує рівно на стику трьох речей, яких у node
 * немає — сервер із реєстром ДВОХ задач і двома текам на диску, два документи
 * (оболонка й рамка макета) і перезавантаження рамки, після якого накручене
 * накладається назад. Підробка будь-якої з них перевіряла б наші уявлення.
 *
 * Мапа «перевірка → запобіжник → що буде, якщо запобіжник прибрати»
 * (знята мутаційно, не написана з голови):
 *
 *   A (макет Б чистий)  — `tuneState = emptyTune()` у `resetPerTaskState`
 *                         (`app/app.js`). МУТАЦІЯ: прибрати рядок. Перевірка
 *                         червоніє: у макеті задачі Б стоїть
 *                         `style="padding-top: 26px !important"`, якого там
 *                         ніхто не робив.
 *   B (пакет Б — тільки — `await loadTune()` там же. МУТАЦІЯ: прибрати рядок
 *      робота Б)          (лишивши `emptyTune()`). Тоді макет чистий, але
 *                         памʼять порожня, і перший запис у задачі Б ЗАТИРАЄ
 *                         її власний файл — правки, які дизайнер уважав
 *                         збереженими, зникають мовчки.
 *   C (пакет А цілий)   — той самий `await loadTune()`, з іншого кінця: без
 *                         нього файл задачі А теж перестає бути правдою, щойно
 *                         в А вернуться й крутнуть ручку.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу. `startServer` бере `portBase + hrtime % 100`,
   тобто кожен сервер займає смугу в сто портів; усе до ~10890 уже зайняте
   сусідніми живими файлами, тож 11090 — перший вільний із запасом. */
const PORT_BASE = 11090;
const VIEW = { width: 1400, height: 900 };

/**
 * Сторінка макета. `mark` — літера задачі: обидві задачі фікстури мають ОДНУ
 * ітерацію `it1` і сторінку `holovna` (у цьому й пастка — ключі збігаються),
 * тож відрізнити документ А від документа Б можна лише позначкою в розмітці.
 *
 * `#target` бере відступ із правила КЛАСУ, а не з інлайну: накручене мусить
 * лягти інлайном ПОВЕРХ правила, і саме наявність інлайну в чужій задачі і є
 * тим слідом, який ловить перевірка A.
 *
 * Градієнт у `body` — з тієї ж причини, що в сусідніх живих тестах: порожній
 * знімок стискається нижче `BYTES_FLOOR`, числився б застарілим, і вхід у
 * макет замовив би справжню зʼємку.
 */
const PAGE = (mark) => (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--sp-4:16px}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:var(--sp-4);background:#eef;width:260px;height:160px;color:#123456}
</style></head><body data-mark="${mark}">
<div id="wrap" class="row"><p id="target" class="card">Картка ${mark}/${id}</p></div>
</body></html>`;

/** Канвас із увімкненим інспектором — тим же шляхом, що й дизайнер. */
async function turnInspectorOn(page) {
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#bar [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 5000 });
}

/** Запінити елемент макета фізичним кліком — саме так пін народжується в
 *  дизайнера. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((s) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!api.pinned && api.pinned.id === s.replace("#", "");
  }, sel, { timeout: 5000 });
}

/* Перемикач задачі — той самий шлях, що в `tests/live/canvas.test.mjs`: крихта
   задачі розкриває дропдаун, а вибір робить пункт усередині нього. */
async function selectTask(page, id) {
  await page.locator('[data-dd="task"]').click();
  await page.locator(`[data-act="task"][data-val="${id}"]`).click();
}

/** Дочекатись, поки рамка візьме документ ІНШОЇ задачі. Позначка в розмітці —
 *  єдине, чим вони відрізняються: шлях `it1/holovna` у них однаковий. */
const markLoaded = (page, mark) => page.waitForFunction((m) => {
  const f = document.getElementById("frame");
  const doc = f && f.contentDocument;
  return !!(doc && doc.body && doc.body.dataset.mark === m
    && f.contentWindow.CanvasInspector);
}, mark, { timeout: 15000 });

/** Що браузер СПРАВДІ показує на елементі макета. */
const shown = (page, sel, prop) => page.frameLocator("#frame").locator(sel)
  .evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop);

/** Інлайн-стиль елемента макета — слід, який лишає по собі `applyTune`. */
const inlineStyle = (page, sel) => page.frameLocator("#frame").locator(sel)
  .evaluate((el) => el.getAttribute("style") || "");

/** Накрутити властивість ГРУБИМ кроком із поля панелі: 16px → 26px.
 *  Через справжнє поле й справжню клавішу, а не з консолі: перевіряється
 *  шлях дизайнера цілком, включно із записом на диск. */
async function bump(page, prop) {
  const field = `#insp-panel [data-act="insptune"][data-prop="${prop}"]`;
  await page.locator(field).waitFor({ timeout: 5000 });
  await page.focus(field);
  await page.keyboard.press("Shift+ArrowUp");
}

/** Пакет із теки задачі, або null. */
function pkg(dir) {
  const f = path.join(dir, ".dc-tuner.json");
  if (!existsSync(f)) return null;
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}

/** Дочекатись пакета з рівно такою кількістю правок (запис іде на кожен
 *  поворот ручки, але він асинхронний). */
async function waitPkg(page, dir, count) {
  for (let i = 0; i < 80; i += 1) {
    const p = pkg(dir);
    if (p && p.editCount === count) return p;
    await page.waitForTimeout(50);
  }
  const p = pkg(dir);
  assert.equal(p && p.editCount, count,
    `пакет у ${dir} так і не дочекався ${count} правок: ${JSON.stringify(p)}`);
  return p;
}

/** Усі властивості, які пакет обіцяє Клоду, з позначкою сторінки. */
const promised = (p) => (p.elements || [])
  .flatMap((el) => el.edits.map((e) => `${el.page} ${e.prop}`)).sort();

test("перемикання задачі: накручене в А не тече в макет і в пакет Б", async (t) => {
  const A = taskFixture({ html: PAGE("A"), pages: ["holovna"] });
  const B = taskFixture({ html: PAGE("B"), pages: ["holovna"] });
  const { child, url } = await startServer(A.dir, {
    portBase: PORT_BASE,
    extraTasks: { taskb: { dir: B.dir, title: "Задача Б" } },
  });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await markLoaded(page, "A");
  await turnInspectorOn(page);
  await pin(page, "#target");

  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "фікстура зʼїхала — далі міряти нема від чого");
  await bump(page, "padding-top");
  assert.equal(await shown(page, "#target", "padding-top"), "26px",
    "ручка не доїхала до макета — далі перевіряти нема чого");
  const pkgA = await waitPkg(page, A.dir, 1);
  assert.deepEqual(promised(pkgA), ["it1/holovna padding-top"]);

  /* Перемикання. Ключ сторінки в задачі Б буде РІВНО той самий —
     `it1/holovna`, — тому все, що лишилось у памʼяті, лягло б на цей макет
     як своє. */
  await selectTask(page, "taskb");
  await markLoaded(page, "B");

  /* A. Макет чужої задачі — чистий. Дивимось і на слід інструмента
     (інлайн-атрибут), і на те, що показує БРАУЗЕР: перше ловить `reapplyTune`,
     друге — будь-який інший спосіб дофарбувати чужий макет. */
  assert.doesNotMatch(await inlineStyle(page, "#target"), /padding-top/,
    "у макеті задачі Б стоїть інлайн, накручений у задачі А");
  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "макет задачі Б показує відступ, якого в ньому ніхто не робив");

  /* B. Пакет задачі Б несе ЛИШЕ роботу задачі Б. Перевіряється саме після
     запису: доки ніхто не крутив ручку, файл Б і не мусить існувати, а
     пастка спрацьовує рівно в мить першого запису. */
  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-left");
  const pkgB = await waitPkg(page, B.dir, 1);
  assert.deepEqual(promised(pkgB), ["it1/holovna padding-left"],
    "пакет задачі Б приписує їй роботу, зроблену в задачі А");

  /* Запис у Б не зачепив файл А. Сама по собі ця перевірка слабка (на
     порожній памʼяті вона зелена теж) — вона лише відсікає найгрубіший
     варіант затирання, коли пакет Б лягає поверх А. Справжнє затирання ловить
     C нижче. */
  assert.deepEqual(promised(pkg(A.dir)), ["it1/holovna padding-top"],
    "робота задачі А затерта записом із задачі Б");

  /* C. ПОВЕРНЕННЯ в задачу А — і саме тут видно, що перемикач не просто
     ЗАБУВАЄ пакет, а ПЕРЕЧИТУЄ його з диска.
     ⚠️ Без цього кроку перевірка була фікцією: мутація «прибрати
     `await loadTune()`, лишивши `emptyTune()`» лишала її зеленою, хоч канал
     після неї нищить роботу. Причина — канал пише ПОВНИЙ пакет: із порожньої
     памʼяті перший же поворот ручки в задачі, де вже щось накручено, кладе на
     диск пакет з ОДНІЄЇ правки, тобто мовчки зносить усе попереднє. Побачити
     це можна тільки повернувшись туди, де робота вже є. */
  await selectTask(page, "fixture");
  await markLoaded(page, "A");
  assert.equal(await shown(page, "#target", "padding-top"), "26px",
    "повернулись у задачу А, а її власна правка на макет не вернулась — "
    + "памʼять не перечитана з диска");

  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-left");
  const backA = await waitPkg(page, A.dir, 2);
  assert.deepEqual(promised(backA),
    ["it1/holovna padding-left", "it1/holovna padding-top"],
    "нова правка в задачі А затерла попередню — канал не зберігає, а перезаписує");
});

/**
 * Живий тест `CanvasInspector.identity(prop)` — пакета ОЗНАК запіненого
 * елемента, з якого тюнер збирає рекомендацію (`app/tuner-model.js`).
 *
 * ⛔ Чому ЖИВИЙ, а не юніт. Половина пакета — це відповідь каскаду: який саме
 * селектор виграв ЦЮ властивість на ЦЬОМУ елементі. Відповідає на це браузер
 * (порядок правил, специфічність, інлайн-атрибут, розкладка шортката по
 * лонгхендах у CSSOM), і підробка CSSOM у node перевіряла б НАШІ уявлення про
 * нього — рівно ті, що вже бували помилкові (див. `inspector-hint`). Друга
 * половина — обхід живого дерева (`trail`, `label`, власний текст).
 *
 * Мапа «перевірка → запобіжник → що буде, якщо запобіжник прибрати»
 * (знята мутаційно, не написана з голови):
 *
 *   A (пакет, а не      — сам склад відповіді `identity()`. МУТАЦІЯ: вернути
 *      шлях у DOM)        самий лише шлях (`{ trail: ['div > div:nth-child(2)'],
 *                         label: null, selector: null, text: null }`) — так
 *                         виглядала б «очевидна» реалізація. Перевірка
 *                         червоніє одразу на кількох рядках, і це навмисно:
 *                         пакет читають ПІСЛЯ того, як сторінку переписали,
 *                         тобто шлях по дітях на ту мить не веде нікуди, а
 *                         ознаки мусять лишитись незалежними.
 *   B (селектор — на    — `pickWinner(declsFor(el, prop))` і поле `sel`, яке
 *      ВЛАСТИВІСТЬ)       `declsFor` тепер несе. У `#target` відступ виграє
 *                         клас, а колір — id: якщо `identity` почне віддавати
 *                         один селектор на весь елемент (напр. `label`), обидва
 *                         рядки стануть однакові й перевірка червоніє. Це і є
 *                         «де правити» для Клода.
 *   C (інлайн ≠ «ніхто  — гілка `win.inline ? INLINE_RULE : …`. Злий її з
 *      не виграв»)        `null` — і пакет перестане розрізняти «правити
 *                         розмітку» та «джерела не знайшли», хоча це дві різні
 *                         поради.
 *   D (власний текст)   — `ownText`: свої текстові вузли попереду
 *                         `textContent`. Візьми одразу `textContent` — і
 *                         картка з вкладеним `<b>` видасть чужий текст за свій;
 *                         прибери запасний шлях — обгортка лишиться взагалі без
 *                         текстової ознаки, а її найважче впізнати.
 *   E (привид)          — `isConnected`, той самий, що в `report()`. Вилучений
 *                         вузол не сміє віддавати ознаки: пін із нього знімає
 *                         АСИНХРОННИЙ MutationObserver, тож устигнути спитати
 *                         можна, і опис привида поїхав би в пакет як опис
 *                         живого блоку.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу. `startServer` бере `portBase + hrtime % 100`,
   тобто кожен сервер займає смугу в сто портів. 10490 із завдання НЕ вільний:
   `WIRE_PORT_BASE` в `inspector-panel` (10390, зсуви до +10) розтягується до
   10499 — рівно цей клас колізії там і описаний. Найвище зайняте —
   `inspector-hint` (10590, тобто до 10689), тож 10690 — перший справді вільний
   проміжок. Сервер тут один, зсувів немає. */
const PORT_BASE = 10690;
const VIEW = { width: 1400, height: 900 };

/**
 * Сторінка, зібрана під ОДНЕ питання: чи каже `identity` правду про те, ЗВІДКИ
 * взялось значення.
 *
 * Три речі в ній навмисні:
 *   · `#target` має і клас, і id, і різні властивості виграють РІЗНІ правила
 *     (відступ — `.card`, колір — `#target`). Селектор на весь елемент тут
 *     неможливий у принципі, і саме це перевіряє B.
 *   · `#inline` має той самий клас, але відступ прибитий атрибутом `style` —
 *     переможець каскаду не має правила взагалі (C).
 *   · у `#target` є вкладений `<b>`, і його текст НЕ мусить попасти у власний
 *     текст картки, тоді як обгортка `#wrap` власного тексту не має зовсім і
 *     мусить дістати запасний (D).
 *
 * Градієнт у `body` — з тієї ж причини, що в сусідніх живих тестах: порожній
 * знімок стискається нижче `BYTES_FLOOR`, числився б застарілим, і вхід у
 * макет замовив би справжню зʼємку.
 */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--sp-4:16px;--c-ink:#123456}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:var(--sp-4);background:#eef;width:260px;height:160px}
#target{color:var(--c-ink)}
#inline{background:#fed}
</style></head><body>
<div id="wrap" class="row">
  <p id="target" class="card">Картка ${id} <b>ЛІГА</b></p>
  <p id="inline" class="card" style="padding:12px">Інлайн ${id}</p>
</div>
</body></html>`;

/** Канвас із увімкненим інспектором — тим же шляхом, що й дизайнер. */
async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#bar [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 3000 });
  return page;
}

/** Запінити елемент макета фізичним кліком — саме так пін народжується в
 *  дизайнера. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const pinned = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return api.pinned ? api.pinned.id : null;
  });
  assert.equal(pinned, sel.replace("#", ""), `клік мусить запінити ${sel}`);
}

/** `identity(prop)` з макета, крізь JSON — щоб перевірка бачила рівно те, що
 *  побачить пакет рекомендацій, а не живий обʼєкт із чужого вікна. */
const ident = (page, prop) => page.evaluate((p) => {
  const api = document.getElementById("frame").contentWindow.CanvasInspector;
  const got = api.identity(p);
  return got === null ? null : JSON.parse(JSON.stringify(got));
}, prop);

test("identity() — пакет незалежних ознак елемента, а не шлях у DOM", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  // Без піна ознак немає — саме null, а не каркас із порожніми полями.
  assert.equal(await ident(page, "padding-top"), null,
    "без запіненого елемента `identity` мусить віддати null");

  await pin(page, "#target");

  /* A. Ознаки НЕЗАЛЕЖНІ: ланцюжок предків, власний підпис, текст. Шлях по
     дітях (`div:nth-child(2)`) на цю мить теж правдивий — але саме він і
     розсиплеться першим, щойно Клод перепише сторінку. */
  const pt = await ident(page, "padding-top");
  assert.deepEqual(pt.trail, ["body", "div.row", "p.card"],
    "ланцюжок — підписи предків від кореня, як у крихтах панелі");
  assert.equal(pt.label, "p.card", "підпис самого елемента: тег + класи");
  assert.deepEqual(Object.keys(pt).sort(), ["label", "selector", "text", "trail"],
    "рівно чотири ознаки — і жодного вузла DOM серед них");

  /* Пакет поїде в JSON, тож ознаки мусять бути примітивами. `structuredClone`
     КИДАЄ на вузлі DOM, на відміну від JSON, який тихо віддав би `{}`. */
  const cloneErr = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    try { structuredClone(api.identity("padding-top")); return null; } catch (e) { return String(e && e.name); }
  });
  assert.equal(cloneErr, null, "у пакеті ознак не сміє бути вузлів DOM");

  /* B. Серце перевірки: селектор — це переможець каскаду ДЛЯ ЦІЄЇ
     властивості, а не опис елемента. На одному й тому самому елементі
     відступ виграв клас, а колір — id. */
  assert.equal(pt.selector, ".card", "відступ приходить із правила класу");
  const color = await ident(page, "color");
  assert.equal(color.selector, "#target", "колір того ж елемента виграв id");
  assert.notEqual(pt.selector, color.selector,
    "один селектор на весь елемент означав би, що каскад ніхто не питав");
  // Решта ознак від властивості не залежать — вони про елемент.
  assert.deepEqual(color.trail, pt.trail);
  assert.equal(color.label, pt.label);

  /* D. Власний текст, без тексту вкладеного `<b>`: це ознака САМОГО блоку. */
  assert.equal(pt.text, "Картка holovna",
    "у власний текст картки не сміє потрапити текст вкладеного елемента");

  /* Властивість, якої ніхто не оголошував: ознаки лишаються, селектора немає.
     Чесне «шукай сам» — не те саме, що вигаданий селектор. */
  const none = await ident(page, "letter-spacing");
  assert.equal(none.selector, null);
  assert.deepEqual(none.trail, pt.trail, "решта ознак мусить лишитись на місці");
  // Сміття замість властивості не сміє валити оверлей.
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  const junk = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return [api.identity(), api.identity(""), api.identity(42)].map((r) => (r ? r.selector : "gone"));
  });
  assert.deepEqual(junk, [null, null, null], "на сміттєвій властивості — просто немає селектора");
  assert.deepEqual(errs, [], "identity не має падати");

  /* D (другий бік). Обгортка власного тексту не має зовсім — і без запасного
     шляху лишилась би без текстової ознаки взагалі. */
  await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.pinAt(1));
  const wrap = await ident(page, "padding-top");
  assert.deepEqual(wrap.trail, ["body", "div.row"], "запінили обгортку");
  assert.ok(wrap.text.includes("Картка"), `обгортка мусить мати текстову ознаку, а бачу ${wrap.text}`);
  assert.equal(wrap.selector, "#wrap", "відступ обгортки виграв її id");

  /* C. Інлайн — це НЕ «ніхто не виграв»: правити треба розмітку, і пакет
     мусить сказати саме це. */
  await pin(page, "#inline");
  const inline = await ident(page, "padding-top");
  assert.equal(inline.selector, "[style]",
    "переможець з атрибута style мусить відрізнятись і від правила, і від null");
  assert.equal((await ident(page, "background-color")).selector, "#inline",
    "сусідня властивість того ж елемента приходить із правила — тобто гілка інлайну не з'їла все");

  /* E. Вилучений вузол ознак не віддає. Вікно справді існує: пін знімає
     АСИНХРОННИЙ MutationObserver, тож між вилученням і його колбеком панель
     устигає спитати. */
  const ghost = await page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    w.CanvasInspector.pinned.remove();
    return w.CanvasInspector.identity("padding-top");
  });
  assert.equal(ghost, null, "ознаки привида поїхали б у пакет як опис живого блоку");
});

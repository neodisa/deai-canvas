/**
 * Живі перевірки НОВОГО API оверлея, яким користуватиметься права панель
 * (Task 4 Плану B): `report()`, `pinAt()`, `setLabels()` і подія `onChange` на
 * зміну ПІНА. Усе це живе в `app/vendor/inspector.js` — усередині iframe
 * макета, і перевірити його можна лише справжнім браузером: `report()` читає
 * живий CSSOM, а подія народжується з фізичного кліку по чужому документу.
 *
 * ⛔ Свідомо НЕ дублюємо: `tests/live/inspector.test.mjs` стереже САМ оверлей
 * (лінійку, геометрію, клавіші), `tests/live/shell-inspect.test.mjs` —
 * проводку панелі зі смугою. Тут тільки те, що Task 4 ДОДАЄ.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»
 * (знята мутаційно, а не написана з голови):
 *
 *   A (плаский звіт)   — те, що `report()` збирає поля з `describeAll`
 *                        ПОІМЕННО, а не розсипає обʼєкт. У `describeAll`
 *                        (`inspector-dom.js`) є ще й поле `el` — сам вузол
 *                        DOM. Постав там `...rep` — і `structuredClone`
 *                        кине `DataCloneError`, а перелік ключів перестане
 *                        збігатись. Саме `structuredClone`, а не лише
 *                        `JSON`: `JSON.stringify` вузол НЕ ловить, він тихо
 *                        віддає `{}` (власних перелічуваних властивостей у
 *                        елемента немає), тобто JSON-обхід сам по собі
 *                        зелений і на зіпсованому звіті.
 *                        Тут же — `pinAt()`: індекс мусить вести в ТОЙ
 *                        САМИЙ масив, що віддав `crumbs`, і сміттєвий індекс
 *                        мусить не робити нічого.
 *   B (подія на пін)   — лічильник поколінь звіту в `_paint` (`_pinSeq`).
 *                        Прибери інкремент — сигнатура `_emit` не зміниться
 *                        від кліку, `onChange` не покличеться, і панель
 *                        батька ніколи не дізнається, що запінили інший
 *                        елемент. МУТАЦІЙНО ПЕРЕВІРЕНО: перевірка червоніє.
 *                        Числа тут РІВНІ, а не «щонайменше один»: подвійний
 *                        сигнал — така сама регресія, як відсутній, і з `>=`
 *                        вона проходила б непоміченою.
 *   C (ховер мовчить)  — порівняння сигнатур в `_emit`. `_paint` кличеться
 *                        на КОЖНІЙ зміні елемента під курсором, тож без
 *                        порівняння батько перечитував би `report()`
 *                        (виміряно: 2.0 мс на сторінці з 1215 елементів і
 *                        400 правилами CSS) і переписував `innerHTML` панелі
 *                        десятки разів на секунду. Перевірка НАВМИСНО
 *                        рахує ще й самі `_paint`: без цього числа вона не
 *                        відрізнила б «сигнал не спрацював» від «малювання
 *                        взагалі не було», тобто була б зелена й на
 *                        непорушному курсорі. МУТАЦІЙНО ПЕРЕВІРЕНО: зроби
 *                        `_emit` безумовним — перевірка червоніє.
 *   D (звіт став       — сигнал у `_repaintPinned`. Пінують КЛІКОМ, тобто в
 *      правдивим)        мить звіту курсор стоїть на елементі і його `:hover`
 *                        активний: бейджі токенів на кнопках, посиланнях і
 *                        картках виходять порожні, і правдивим звіт стає
 *                        рівно тоді, коли курсор пішов (докстрінг
 *                        `_repaintPinned`). Свій оверлей перемальовує себе
 *                        сам; батьківська панель без цього сигналу застрягла
 *                        б на неправдивій версії — рівно на тій, заради якої
 *                        `_repaintPinned` і написаний. Прибери інкремент
 *                        звідти — перевірка червоніє.
 *                        Тут же видно, що шторму немає: `_paint` на цьому
 *                        русі не викликається ЖОДНОГО разу (гілка піна в
 *                        `_onMove` виходить раніше), а сигнал — рівно один.
 *                        І межа «один сигнал на ПЕРЕТИН межі» перевіряється
 *                        поверненням на запінений елемент і другим виходом:
 *                        без цього зелений колір означав би й «сигнал буває
 *                        рівно раз за все життя піна», що зробило б панель
 *                        сліпою на другому колі.
 *   E (підписи згори)  — `setLabels` і його дефолти. Сторінку макета
 *                        відкривають і без канваса, там `setLabels` не
 *                        покличе ніхто: ключ, якого в мапі немає (а так само
 *                        порожнє чи нерядкове значення), мусить лишити підпис,
 *                        а не стерти його. Прибери перевірку
 *                        `typeof v === 'string' && v` — кнопка інспектора
 *                        лишиться голим значком «◎».
 *                        ПЕРЕПИСАНО 17.09.2026 (Task 8) у двох місцях, і
 *                        обидва названі свідомо. Перше: вузлів із `data-lbl`
 *                        стало менше — чип режимів прибрано, тож три межі, що
 *                        трималися на його кнопках, перевіряються тепер на
 *                        кнопці інспектора. ЖОДНА з них не прибрана. Друге:
 *                        слова «дефолт із РОЗМІТКИ» більше не відповідають
 *                        коду — дефолт збирає сам оверлей через `t()` на
 *                        `init()`, бо розміткові літерали були українськими
 *                        назавжди (саме для сторінки без канваса, де
 *                        `setLabels` не кличуть). Предмет перевірки той самий:
 *                        підпис Є і його не стирають.
 *   F (щось у          — ТРИ запобіжники на одну тему: падіння не сміє зʼїсти
 *      ланцюжку впало)     подію. Кожен знятий мутаційно окремо, усі валять
 *                        саме F.
 *                        · обнулення `_lastSig` у `catch` (`_emit`). Панель
 *                          малює ЧУЖИЙ payload, тобто впасти може справді.
 *                          Сигнатура, записана як видана, але НЕ доставлена,
 *                          ховає рівно той стан, на якому панель застрягла:
 *                          повторно він не піде ніколи. Мутація: `catch (e) {}`.
 *                          Тригер тут — САМЕ `set(true)`, бо це єдиний шлях з
 *                          рівно одним `_emit`; перша версія перевірки пінувала
 *                          і була фікцією — покоління звіту мінялось, сигнатура
 *                          ставала іншою, і сигнал проходив би й із поламаним
 *                          `catch`.
 *                        · `try/finally` у `_paint`: пін виставляється ДО
 *                          малювання, тож падіння малювання не сміє лишити
 *                          батька зі старим піном. Мутація: послідовний виклик.
 *                        · `try/finally` у `_repaintPinned`: заходять сюди раз
 *                          на вихід курсора, тож пропущений сигнал —
 *                          пропущений НАЗАВЖДИ. Мутація: послідовний виклик.
 *
 * Нижче — те, що ДОДАЄ проводка панелі (Task 5/6): API з Task 4 нарешті має
 * споживача, і перевіряється вже не «оверлей уміє віддати», а «панель це
 * показує й цим керує».
 *
 *   G (крихта пінує)   — `api.pinAt(val)` у `BAR_ACTIONS.inspcrumb`
 *                        (`app.js`). Прибери цей рядок, лишивши сам
 *                        `paintInsp()`, — панель слухняно перемалюється ТИМ
 *                        САМИМ звітом, а пін не зрушить. МУТАЦІЙНО
 *                        ПЕРЕВІРЕНО: перевірка червоніє. Тому дивимось не
 *                        лише на `pinned`, а й на ЗМІСТ звіту в панелі:
 *                        крихт меншає, і зʼявляється поле gap (авто-лейаут), якого в
 *                        абзаці не було, — тобто панель показує звіт про
 *                        ІНШИЙ елемент, а не той самий.
 *   H (клавіша M)      — ВИДАЛЕНО у 0.29.0: режиму лінійки й клавіші M більше нема (її відсутність стереже сценарій 8
 *                        у `inspector-figma.test.mjs`). Так само видалено L («у лінійці числа йдуть за курсором»).
 *   I (прокрутка)      — збереження `scrollTop` у `paintInsp` (`app.js`).
 *                        Друга подія на той самий пін — не рідкість, а
 *                        НОРМА: звіт, знятий у мить кліку, неправдивий, і
 *                        оверлей перечитує його щойно курсор зійде
 *                        (`_repaintPinned`, перевірка D вище). Без
 *                        збереження перше, що бачить дизайнер після піна, —
 *                        стрибок панелі на початок. МУТАЦІЙНО ПЕРЕВІРЕНО:
 *                        прибери відновлення — `scrollTop` стає 0.
 *                        Вікно менше за типове НАВМИСНО: при 900px звіт про
 *                        фікстурний абзац у тіло панелі ВЛАЗИТЬ (виміряно:
 *                        772 із 772), прокручувати нема чого, і перевірка
 *                        була б зелена завжди. Тому 620 — і перед вимірами
 *                        стоїть пряме твердження, що тіло взагалі
 *                        прокручується.
 *
 * Нижче — Task 8: плаваючий хром оверлея зникає ТАМ, ДЕ Є ОБОЛОНКА, і
 * лишається там, де її немає.
 *
 *   J (канвас без       — памʼять `_chrome` у `setChrome` і охорона на початку
 *      хрому)             `_renderPanel`. Канвас кличе `setChrome(false)` на
 *                        завантаження макета, а вікно звіту народжується
 *                        ПІЗНІШЕ — на першому піні; без памʼяті воно спокійно
 *                        вилізло б поверх макета. Тому перевірка й пінує:
 *                        без піна вона була б зелена й на оверлеї, який
 *                        ховати вікно не вміє взагалі. МУТАЦІЯ: хай
 *                        `setChrome(false)` не запамʼятовує стан — червоніє.
 *                        Останній рядок («звіт усе-таки Є, просто в панелі»)
 *                        відрізняє «хром прибрано» від «інспектор осліп».
 *   K (сторінка без     — те, що Task 8 НЕ прибрав: `/commented?…`, відкритий
 *      канваса)           прямо, лишається зі своїм вікном звіту — там більше
 *                        нема кому показати каскад, і `setChrome` там не
 *                        кличе ніхто. МУТАЦІЯ: хай `_renderPanel` виходить
 *                        одразу — червоніє. Перевіряємо ще й `insp-spec` у
 *                        розмітці вікна: цей клас малює РІВНО спільний
 *                        рендерер, тож один рядок доводить і «звіт не зник»,
 *                        і «другої реалізації поруч не завели».
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли ПАРАЛЕЛЬНО, і
   спільна база означає 15 секунд чекання й падіння «сервер не піднявся».
   9690 у завданні було помилкою — він уже зайнятий ДВІЧІ (`shell-palette`
   і `CRUMB_PORT_BASE` в `ext-shell`); 9990 — єдиний вільний проміжок між
   `inspector-project` (9890) і `panel-click` (10090).

   Зсуви між перевірками — по ДВА, а не по десять, як у сусідніх файлах.
   Причина арифметична: `startServer` бере `portBase + hrtime % 100`, тобто
   КОЖЕН сервер займає смугу в сто портів. Зі зсувами по десять останній
   сервер цього файлу сягав би 10129 — тобто вліз би в смугу `panel-click`,
   і саме така колізія вже дала тут одне хибне падіння під час мутаційного
   прогону. Зі зсувами по два весь файл лишається в 9990…10099, тобто нижче
   за смугу `panel-click` скрізь, крім самого хвоста останньої перевірки. */
const PORT_BASE = 9990;
/* Друга база — для перевірок Task 5/6 нижче. Від 9990 їм лишились би зсуви
   +12/+14, тобто смуги 10002…10103, які заходять у смугу `panel-click`
   (10090) — рівно та колізія, від якої застерігає коментар вище. 10390 стоїть
   ВИЩЕ за все зайняте (найдальший сусід — `comment-audience`, 10190 + 80,
   тобто до 10369), тож перетину немає взагалі. */
const WIRE_PORT_BASE = 10390;
const VIEW = { width: 1400, height: 900 };
/* Низьке вікно для перевірки прокрутки: при 900px звіт у тіло панелі ВЛАЗИТЬ
   (виміряно: scrollHeight 772 = clientHeight 772), і прокручувати не було б
   чого. 620 лишає ~180px ходу. */
const SHORT_VIEW = { width: 1400, height: 620 };

/* Градієнт, а не порожня сторінка — та сама причина, що в сусідніх живих
   тестах: порожній знімок стискається нижче `BYTES_FLOOR` і числиться
   «застарілим», тож вхід у канвас міг би замовити справжню автозʼємку.
   `--sp-4`/`--c-ink` у `:root` — щоб звіт мав що показувати в графі
   «токен», а не самі лише хардкоди. `#target` має клас: `label()` віддає
   тег + до двох класів, і без класу крихта не відрізнялась би від сусідів. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--sp-4:16px;--c-ink:#123456}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#ttl{margin:0;padding:10px;background:#fff}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
#target{margin:0;padding:var(--sp-4);color:var(--c-ink);background:#eef;width:240px;height:140px}
#a,#b{margin:0;padding:var(--sp-4);background:#fed;width:180px;height:140px}
</style></head><body>
<h1 id="ttl">${id}</h1>
<div id="wrap"><p id="target" class="card">${id}</p><p id="a">a</p><p id="b">b</p></div>
</body></html>`;

/** Макет, готовий до роботи, і кнопка інспектора смуги вже клікабельна. */
async function openCanvas(browser, url, view = VIEW) {
  const page = await browser.newPage({ viewport: view });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  return page;
}

/** Інспектор увімкнено з кнопки СМУГИ — тим самим шляхом, що й дизайнер. */
async function openInspector(browser, url, view = VIEW) {
  const page = await openCanvas(browser, url, view);
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 3000 });
  return page;
}

/** Що оверлей віддає назовні про свій стан (усе — примітиви). */
const state = (page) => page.evaluate(() => {
  const api = document.getElementById("frame").contentWindow.CanvasInspector;
  return {
    on: api.on,
    mode: api.mode,
    pinned: api.pinned ? api.pinned.id : null,
    hover: api.hover ? api.hover.id : null,
  };
});

/**
 * Лічильники `onChange` і `_paint`, і СКИДАННЯ їх у нуль.
 *
 * `onChange` саме ОБГОРТАЄМО, а не підміняємо: `app.js` вішає туди свій
 * `paintBar`, і затерши його, ми зламали б оболонку — а перевірка від цього
 * стала б ЗЕЛЕНІШОЮ (менше перемальовок, менше шансів на гонку), тобто
 * зелений колір перестав би щось означати.
 *
 * `_paint` рахуємо окремо й НЕ заради симетрії: без цього числа перевірка C
 * («ховер мовчить») не відрізняє «сигнал придушено правильно» від «курсор
 * нікуди не поїхав і малювання не було».
 */
/**
 * Токени ДС простору вантажаться асинхронно (`loadSpaceTokens` → `_dsArrived` → `_tuned` → `_paint` і сигнал батькові).
 * Під навантаженням повного прогону відповідь інколи приходила вже ПІСЛЯ `arm` — лічильники бачили зайвий `_paint` і
 * зайвий сигнал, і B/C/D падали раз на кілька прогонів (16.11.2026). Тому перед `arm` чекаємо, поки запит токенів
 * відповів (або його немає зовсім — макет без простору), і ще два кадри на `res.json()` та перемальовку.
 */
async function dsSettled(page) {
  await page.waitForFunction(() => {
    const w = document.getElementById("frame")?.contentWindow;
    const s = w?.document.querySelector('script[src*="inspector.js"]');
    if (!s) return false;
    if (!/[?&]sp=/.test(s.src)) return true;
    return w.performance.getEntriesByType("resource")
      .some((e) => e.name.includes("/api/ds-tokens") && e.responseEnd > 0);
  }, null, { timeout: 10000 });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
}

async function arm(page) {
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    window.__hits = 0;
    window.__paints = 0;
    if (api.__armed) return;
    api.__armed = true;
    const prevOn = api.onChange;
    api.onChange = function (on) {
      window.__hits += 1;
      if (typeof prevOn === "function") prevOn(on);
    };
    const draw = api._paint.bind(api);
    api._paint = function (el) { window.__paints += 1; return draw(el); };
  });
}

const counts = (page) => page.evaluate(
  () => ({ hits: window.__hits, paints: window.__paints }));

/**
 * Центр елемента МАКЕТА в координатах головної сторінки.
 *
 * Засторога, яку тут знято 17.09.2026 (Task 8): до того власна плаваюча
 * панель оверлея (`.panel`, `right:16px`, 320px) лежала на правому краї
 * макета й тихо зʼїдала кліки туди — `_pageEl` вертає для неї `null`, без
 * помилки. Перевіркам доводилось триматись лівої половини (`#ttl`, `#target`,
 * `#a`), і коштувало це одного «перевірка зелена, бо клік нікуди не влучив».
 * У КАНВАСІ панелі більше немає взагалі (`setChrome(false)` ховає й її), тож
 * правий край знову нейтральний і `#b` можна брати будь-де. Сама засторога
 * лишається записаною, бо на сторінці БЕЗ канваса вікно живе — і там вона
 * чинна досі (`tests/live/inspector.test.mjs`).
 */
async function centerOf(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  return [box.x + box.width / 2, box.y + box.height / 2];
}

/** Запінити елемент макета фізичним кліком, НЕ зрушивши курсор під час
 *  вимірювання: `mouse.click` спершу робить `move`, а рух — це вже подія, від
 *  якої оверлей може сигналити. Тому наведення й натискання розведені, і
 *  лічильники скидаються МІЖ ними. */
async function pinByClick(page, sel) {
  const [x, y] = await centerOf(page, sel);
  await page.mouse.move(x, y);
  await dsSettled(page);
  await arm(page);
  await page.mouse.down();
  await page.mouse.up();
}

test("A. report() — плаский серіалізовний звіт, pinAt ходить по його ж крихтах", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.report()), null,
  "без піна звіту немає — саме null, а не порожній каркас секцій");

  await pinByClick(page, "#target");
  assert.equal((await state(page)).pinned, "target", "клік мусить запінити елемент");

  const got = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    const rep = api.report();
    let cloneErr = null;
    // structuredClone КИДАЄ на вузлі DOM — на відміну від JSON, який тихо
    // віддав би `{}`. Це і є доказ, що вузли в звіт не просочились.
    try { structuredClone(rep); } catch (e) { cloneErr = String(e && e.name); }
    const round = JSON.parse(JSON.stringify(rep));
    const box = round.groups && round.groups.box;
    return {
      keys: Object.keys(rep).sort(),
      cloneErr,
      crumbs: round.crumbs,
      hasBox: Array.isArray(box) && box.length > 0,
      boxProps: Array.isArray(box) ? box.map((d) => d.prop) : null,
      boxVerdicts: Array.isArray(box) ? box.every((d) => typeof d.verdict === "string") : false,
      blockedType: typeof round.blocked,
      partialType: typeof round.partial,
      lossless: JSON.stringify(round) === JSON.stringify(rep),
    };
  });

  /* Шість полів: T-40 додав `dsInfo`, 0.29.0 — `facts` (розмір, батько, прапорець власного тексту: те, чого бракує панелі властивостей). T-40: `dsInfo` — під якою дизайн-системою
     прочитані вироки. Перелік лишається ЗАКРИТИМ і саме в цьому сенс
     перевірки: `describeAll` віддає ще й `el` (вузол DOM), і розсип `...rep`
     протягнув би його в інший документ. Нове поле проходить ту саму межу, що
     й решта, — самі примітиви (це доводить `structuredClone` нижче). */
  assert.deepEqual(got.keys, ["blocked", "crumbs", "dsInfo", "facts", "groups", "partial"],
    "у звіті рівно шість полів — жодного `el` з describeAll");
  assert.equal(got.cloneErr, null,
    "structuredClone не мусить кидати: інакше у звіті є вузол DOM");
  assert.ok(Array.isArray(got.crumbs) && got.crumbs.length > 0, "крихти мусять бути");
  assert.deepEqual(got.crumbs, ["body", "div", "p.card"],
    "крихти йдуть від кореня до самого елемента і описують саме його");
  assert.ok(got.hasBox, "секція бокс-моделі мусить бути в кожному звіті");
  assert.ok(got.boxProps.includes("padding-top"),
    `бокс-модель мусить нести свої властивості, а бачу ${got.boxProps}`);
  assert.equal(got.boxVerdicts, true, "у кожного рядка мусить бути вирок");
  assert.equal(got.blockedType, "boolean", "`blocked` — булеве, а не undefined");
  assert.equal(got.partialType, "boolean", "`partial` — булеве, а не undefined");
  assert.equal(got.lossless, true, "звіт мусить переживати JSON без втрат");

  /* `pinAt` ходить по ТОМУ САМОМУ масиву, що віддав `crumbs`: індекс 1 — це
     `div` (тобто `#wrap`), передостання крихта. Іншого джерела індексів у
     панелі немає й бути не мусить. */
  await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.pinAt(1));
  assert.equal((await state(page)).pinned, "wrap",
    "pinAt(1) мусить запінити предка з крихти №1");
  assert.deepEqual(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.report().crumbs), ["body", "div"],
  "після піна предка крихт стає менше — звіт мусить це показати");

  // Сміттєві індекси — тихо нічого: клацання по крихті, якої вже немає, це
  // не помилка дизайнера, і падати на ній оверлей не має права.
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    api.pinAt(99); api.pinAt(-1); api.pinAt("x"); api.pinAt(undefined);
  });
  assert.equal((await state(page)).pinned, "wrap", "сміттєвий індекс не мусить рухати пін");
  assert.deepEqual(errs, [], "pinAt не має падати на індексі поза масивом");

  /* Знімок крихт ЗАСТАРІВАЄ, і вікно для цього справді існує: пін із
     вилученого вузла знімає MutationObserver, а він асинхронний — між
     вилученням і його колбеком `_crumbEls` показує на те, чого в документі
     вже немає. Обидві охорони `isConnected` (у `report` і в `pinAt`) саме
     про це вікно, і перевіряються вони тут РАЗОМ, бо поодинці кожна
     виглядала б параноєю. */
  const stale = await page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    const api = w.CanvasInspector;
    const doc = w.document;
    api.pinned = doc.querySelector("#target");
    api.report();                          // _crumbEls = [body, #wrap, #target]
    doc.querySelector("#target").remove();
    const ghost = api.report();            // пін іще стоїть: MO не спрацював
    api.pinned = doc.querySelector("#a");  // батько тим часом пішов далі
    api.pinAt(2);                          // крихта #target, якої вже немає
    const after = api.report();
    return { ghost, pinned: api.pinned && api.pinned.id,
             crumbs: after && after.crumbs };
  });
  assert.equal(stale.ghost, null,
    "звіт про вилучений вузол мусить бути null, а не каскад привида");
  assert.equal(stale.pinned, "a",
    "клік по застарілій крихті не мусить збивати ЖИВИЙ пін");
  assert.deepEqual(stale.crumbs, ["body", "div", "p"],
    "живий пін мусить звітувати далі, ніби застарілої крихти й не торкались");
  assert.deepEqual(errs, [], "застаріла крихта не має валити оверлей");
});

test("B. onChange спрацьовує на зміну ПІНА, а не лише на увімкнення", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 2 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  /* Числа РІВНІ, а не «щонайменше один»: подвійний сигнал — це така сама
     регресія, як відсутній (батько на кожен пін переписував би `innerHTML`
     панелі двічі), і з `>=` вона проходила б непоміченою. Одиниця тут не
     довільна: `pinByClick` скидає лічильники ПІСЛЯ наведення, `mousedown`
     виходить із `_onDown` до малювання (`e.type !== 'click'`), тож на весь
     пін лишається рівно один `_paint` — і рівно один `_emit`. */
  await pinByClick(page, "#target");          // лічильники скинуті всередині
  assert.equal((await state(page)).pinned, "target");
  assert.deepEqual(await counts(page), { hits: 1, paints: 1 },
    "пін мусить дати батькові РІВНО один сигнал і рівно одне малювання");

  // Другий пін — щоб перевірка стерегла ЗМІНУ піна, а не «перший сигнал після
  // увімкнення»: без цього мутація «рахувати лише перший пін» лишилась би
  // зеленою.
  await pinByClick(page, "#a");
  assert.equal((await state(page)).pinned, "a");
  assert.deepEqual(await counts(page), { hits: 1, paints: 1 },
    "зміна піна мусить дати батькові РІВНО один сигнал");

  // Зняття піна тим самим елементом — теж зміна стану панелі (звіту більше
  // немає), тож теж сигнал.
  await pinByClick(page, "#a");
  assert.equal((await state(page)).pinned, null, "повторний клік мусить зняти пін");
  assert.deepEqual(await counts(page), { hits: 1, paints: 1 },
    "зняття піна мусить дати батькові РІВНО один сигнал");
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.report()), null, "без піна звіту немає");
});

test("C. рух курсора БЕЗ піна не смикає батька жодного разу", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 4 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  await dsSettled(page);
  await arm(page);
  const seen = [];
  for (const sel of ["#ttl", "#target", "#a", "#b", "#target", "#ttl"]) {
    const [x, y] = await centerOf(page, sel);
    await page.mouse.move(x, y);
    seen.push((await state(page)).hover);
  }

  // Спершу доводимо, що курсор СПРАВДІ їздив по макету: інакше «нуль
  // сигналів» нічого не вартий — його дав би й непорушний курсор.
  assert.deepEqual(seen, ["ttl", "target", "a", "b", "target", "ttl"],
    "ховер мусить іти за курсором — інакше перевірка ні про що");
  const c = await counts(page);
  assert.ok(c.paints >= 6,
    `малювання мусило статись на кожен новий елемент, а _paint покликано ${c.paints} разів`);
  assert.equal(c.hits, 0,
    `ховер НЕ мусить смикати батька, а onChange покликано ${c.hits} разів`);

  // Пін після цього однаково мусить пройти — придушення не має бути «назавжди».
  await pinByClick(page, "#b");
  assert.ok((await counts(page)).hits >= 1, "після мовчазного ховера пін мусить дійти");
});

test("D. курсор покинув запінений елемент — звіт став правдивим, батько знає", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 6 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  await pinByClick(page, "#target");
  assert.equal((await state(page)).pinned, "target");

  await dsSettled(page);
  await arm(page);                              // скидаємо після піна
  const [x, y] = await centerOf(page, "#a");
  await page.mouse.move(x, y);

  const c = await counts(page);
  assert.equal((await state(page)).pinned, "target", "пін не мусить злітати від руху");
  /* 0.29.0: наведення при піні теж малює (рамка й ярлик НАВЕДЕНОГО — `_paint(this.pinned || el)` у `_onMove`), тож
     перехід на інший елемент дає рівно один `_paint`. Предмет перевірки лишається: малювання НЕ є джерелом сигналу —
     сигнал батькові дає лише вихід із піна (`hits`), а число `_paint` рівне числу змін елемента під курсором. */
  assert.equal(c.paints, 1, `один перехід на інший елемент — один _paint, а покликано ${c.paints}`);
  assert.equal(c.hits, 1,
    "вихід курсора з піна перечитує звіт — батько мусить дізнатись, "
    + `РІВНО один раз, а onChange покликано ${c.hits} разів`);

  /* Шторму немає: далі курсор їздить ПОЗА піном, і `_pinLeftFor`
     (`_onMove`) впускає перемальовку рівно раз на вихід. */
  for (const sel of ["#a", "#ttl", "#a"]) {
    const [px, py] = await centerOf(page, sel);
    await page.mouse.move(px, py);
  }
  assert.equal((await counts(page)).hits, 1,
    "поки курсор гуляє ПОЗА піном, нових сигналів бути не мусить");
  assert.equal((await counts(page)).paints, 3, "#ttl і назад на #a — ще дві зміни елемента під курсором (повтор на #a не зміна), тож два _paint");

  /* Межа «один сигнал на ПЕРЕТИН межі» перевіряється тільки поверненням:
     без нього зелений колір вище означав би й «сигнал буває рівно раз за все
     життя піна», що неправда і що зробило б панель сліпою на другому колі.
     Повернення САМЕ на запінений елемент сигналу не дає (гілка `_onMove`
     виходить, перемальовувати нічого), а наступний вихід — дає, і знову
     рівно один. */
  const [bx, by] = await centerOf(page, "#target");
  await page.mouse.move(bx, by);
  assert.equal((await counts(page)).hits, 1,
    "повернення НА запінений елемент саме по собі сигналу не дає");
  const [ax, ay] = await centerOf(page, "#a");
  await page.mouse.move(ax, ay);
  assert.equal((await counts(page)).hits, 2,
    "другий вихід за межі піна мусить дати ще РІВНО один сигнал");
  assert.equal((await counts(page)).paints, 5,
    "повернення на пін і другий вихід — ще два _paint (зміна елемента під курсором), і жодного зайвого");
});

test("E. setLabels міняє підписи згори, а без нього лишаються дефолти розмітки", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 8 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  /* ПЕРЕПИСАНО 17.09.2026 (Task 8): кнопок режимів у хромі оверлея більше
     немає — видимий перемикач один і живе в правій панелі. Усі три межі
     `setLabels`, які вони тут тримали (ключа немає / значення порожнє /
     значення не рядок → підпис ЛИШАЄТЬСЯ), перевіряються тими самими
     твердженнями на єдиному вузлі, що лишився, — підписі кнопки. Жодна не
     втрачена; втрачений лише другий вузол, на якому вони дублювались. */
  const chrome = () => page.evaluate(() => {
    const sh = document.getElementById("frame").contentDocument
      .querySelector("[data-canvas-inspector]").shadowRoot;
    return {
      btn: sh.querySelector(".btn").textContent.trim(),
      glyph: sh.querySelector(".btn [aria-hidden]").textContent.trim(),
      modes: sh.querySelectorAll("[data-mode]").length,
    };
  });

  const before = await chrome();
  /* Дефолт підпису тепер збирає сам оверлей через `t()` на `init()` (Task 8):
     розміткових літералів більше немає, бо вони були українськими назавжди —
     сторінку макета відкривають і без канваса, і там `setLabels` не покличе
     ніхто ніколи. Конкретних слів не перевіряємо: мова перемикається, а ця
     перевірка не про словник — вона про те, що підпис Є і що його не стирають. */
  assert.ok(before.btn.length > 1, "кнопка інспектора мусить мати підпис до setLabels");
  assert.equal(before.glyph, "◎", "значок кнопки мусить бути окремо від підпису");
  assert.equal(before.modes, 0, "чипа режимів в оверлеї не мусить бути (Task 8)");

  await page.evaluate(() => document.getElementById("frame").contentWindow
    .CanvasInspector.setLabels({ inspector: "Inspector" }));
  assert.equal((await chrome()).btn, "◎ Inspector",
    "підпис кнопки мусить приїхати згори, значок — лишитись");

  /* Три межі поспіль, кожна на тому самому вузлі: ключа в мапі немає, значення
     порожнє, значення не рядок. У всіх трьох підпис мусить ЛИШИТИСЬ тим, що
     стояв, — інакше сторінка без канваса лишиться з голим значком «◎» замість
     кнопки, якою інспектор узагалі вмикають. */
  for (const map of [{ somethingElse: "x" }, { inspector: "" }, { inspector: null }]) {
    await page.evaluate((m) => document.getElementById("frame").contentWindow
      .CanvasInspector.setLabels(m), map);
    assert.equal((await chrome()).btn, "◎ Inspector",
      `setLabels(${JSON.stringify(map)}) не мусить стирати підпис`);
  }

  /* Друга поверхня того самого хрому — клавіша, якою його вмикають. На
     кириличній розкладці `I` фізично дає `ш`, і умову в `_onKey` переписано
     з чотирьох порівнянь на регексп (кирилиця в СТРОКОВОМУ літералі — це
     майбутнє спрацювання охоронця i18n, а в регекспі вона означає розкладку
     клавіші, не напис). Переписування мусить нічого не загубити; латинську
     `i` вже стереже `tests/live/inspector.test.mjs`. */
  /* Подія збирається руками, а не `keyboard.press`: Playwright уміє тиснути
     лише клавіші розкладки US і кидає «Unknown key» на «ш» (перевірено). Тому
     перевіряємо рівно те, що змінилось, — УМОВУ в `_onKey`; фізичний шлях
     клавіші до оверлея вже стереже `inspector.test.mjs` латинською `i`. */
  const inner = page.frames().find((f) => f !== page.mainFrame());
  assert.ok(inner, "не знайшов iframe макета");
  const tapCyr = (k) => inner.evaluate((key) => window.dispatchEvent(
    new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })), k);
  await tapCyr("ш");
  assert.equal((await state(page)).on, false, "«ш» мусить вимикати інспектор");
  await tapCyr("Ш");
  assert.equal((await state(page)).on, true, "«Ш» мусить вмикати його назад");
});

test("F. падіння в ланцюжку не ховає стан назавжди", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 10 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);
  /* Свої винятки чекані; чужий тут означав би, що перевірка міряє не те. */
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e.message || e)));
  /* Тиша перед підрахунком (16.11.2026): після падіння батька `_emit` повторює сигнал на НАЙБЛИЖЧОМУ ж малюванні, а
     малювання могло прийти саме собою — від токенів ДС, що доїхали пізно, чи від синтетичного руху миші, яким Chromium
     оновлює ховер над рамкою. Під навантаженням повного прогону воно встигало раніше за `hits()` — «2 !== 1». Тому
     чекаємо токени й відводимо курсор з рамки на смугу оболонки. */
  await dsSettled(page);
  await page.mouse.move(5, 5);

  /* Вимикаємо ДО того, як вішати лічильник: сама ця зміна стану нас не
     цікавить, а рахувати треба рівно одну доставку. */
  await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.set(false));

  /* Колбек, що падає РІВНО раз. Панель батька малює чужий payload, тобто
     впасти вона може по-справжньому, і саме це відтворюємо. Рахуємо ще й
     `_paint`: без цього числа «сигналів не побільшало» не відрізнити від
     «оверлей нічого не робив». */
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    window.__hits = 0;
    window.__paints = 0;
    window.__throwNext = true;
    api.onChange = function () {
      window.__hits += 1;
      if (window.__throwNext) {
        window.__throwNext = false;
        throw new Error("панель упала");
      }
    };
    const draw = api._paint.bind(api);
    api._paint = function (el) { window.__paints += 1; return draw(el); };
  });

  const hits = () => page.evaluate(() => window.__hits);
  const paints = () => page.evaluate(() => window.__paints);

  /* Тригер — УВІМКНЕННЯ, і вибране воно не навмання: `set(true)` не кличе
     `_paint`, тобто дає РІВНО один `_emit`. Пін тут не годиться (наступний
     вихід курсора підняв би покоління звіту, сигнатура стала б іншою, і
     сигнал пройшов би й із поламаним `catch` — перевірка була б фікцією,
     спіймано мутаційно), а `setMode` кличе `_emit` двічі й ховає відновлення
     всередині себе. */
  await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.set(true));
  assert.equal(await hits(), 1, "увімкнення мусить дійти — і впасти в батькові");

  /* А тепер головне. Стан ТОЙ САМИЙ: нічого не запінено, режим не мінявся,
     сигнатура не змінилась ані на йоту. Оверлей і далі малює на кожен новий
     елемент під курсором (`_paint` → `_emit`), і саме ці виклики мусять
     ПОВТОРИТИ недоставлений сигнал — бо сигнатуру, яку не доставили, `_emit`
     не сміє тримати записаною як доставлену. Без обнулення `_lastSig` у
     `catch` порівняння зʼїдає її назавжди, і панель лишається вимкненою на
     вигляд, доки дизайнер не зачепить щось інше. */
  for (const sel of ["#ttl", "#target"]) {
    const [px, py] = await centerOf(page, sel);
    await page.mouse.move(px, py);
  }
  assert.ok(await paints() >= 2,
    `рух курсора мусив малювати, а _paint покликано ${await paints()} разів`);
  assert.equal(await hits(), 2,
    "після падіння батька найближчий же `_emit` мусить донести той самий стан ще раз");

  /* І це не перетворює відновлення на шторм: доставка ВДАЛАСЬ, сигнатура знову
     записана, тож подальші рухи курсора мовчать, як і мусять. */
  for (const sel of ["#a", "#ttl", "#a"]) {
    const [px, py] = await centerOf(page, sel);
    await page.mouse.move(px, py);
  }
  assert.equal(await hits(), 2,
    "після успішної доставки порівняння сигнатур мусить знову замовкнути");

  /* Друге місце, де падіння могло б зʼїсти подію, — САМЕ МАЛЮВАННЯ. Воно
     ходить по живому CSSOM чужого макета, тобто кидає не в теорії. Сигнал
     стоїть у `finally` (`_paint`) саме тому: стан уже змінився (пін), і
     мовчазне падіння розвело б панель із реальністю назавжди — наступного
     `_paint` без руху курсора може не бути взагалі. */
  await page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    const api = w.CanvasInspector;
    window.__hits = 0;
    api.onChange = function () { window.__hits += 1; };   // чистий лічильник
    const draw = api._draw.bind(api);
    api._draw = function () { api._draw = draw; w.__threw = (w.__threw || 0) + 1; throw new Error("малювання впало"); };
  });
  const [bx, by] = await centerOf(page, "#a");
  await page.mouse.move(bx, by);
  await page.mouse.down();
  await page.mouse.up();
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.__threw), 1, "підміна мусила спрацювати — інакше перевірка ні про що");
  assert.equal((await state(page)).pinned, "a",
    "пін ставиться ДО малювання, тож падіння малювання його не скасовує");
  assert.equal(await hits(), 1,
    "падіння в малюванні не сміє зʼїсти сигнал про новий пін");

  /* Третє місце — перечитування звіту після виходу курсора. Воно кличе
     `_renderPanel`, тобто той самий живий CSSOM, і заходять сюди рівно раз на
     вихід: пропущений тут сигнал — пропущений НАЗАВЖДИ. */
  /* Падіння малювання вище лишило звіт про пін НЕ відрендереним (`_panelSeq` ≠ `_pinSeq`): без синхронізації перший
     же `_paint` нового елемента під курсором сам перечитав би звіт і «зʼїв» підміну раніше за `_repaintPinned`
     (0.29.0, `_paint` рендерить звіт на зміну покоління) — перевірка мірила б не те місце. Синхронізуємо явно. */
  await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector._paint(
    document.getElementById("frame").contentWindow.CanvasInspector.pinned));
  await page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    const api = w.CanvasInspector;
    window.__hits = 0;
    const rp = api._renderPanel.bind(api);
    api._renderPanel = function () { api._renderPanel = rp; w.__threw += 1; throw new Error("звіт упав"); };
  });
  const [tx2, ty2] = await centerOf(page, "#target");
  await page.mouse.move(tx2, ty2);
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.__threw), 2, "підміна мусила спрацювати — інакше перевірка ні про що");
  assert.equal(await hits(), 1,
    "падіння в перечитуванні звіту не сміє зʼїсти єдиний сигнал про вихід курсора");

  assert.deepEqual(errs.filter((m) => !/малювання впало|звіт упав/.test(m)), [],
    "чужих винятків на сторінці бути не мусить");
});

/* ── Проводка панелі: Task 5 (малює звіт) + Task 6 (проводка) ───────────── */

/** Що ПАНЕЛЬ показує про елемент — рівно те, що видно дизайнеру. Жодного
 *  звернення до `CanvasInspector` тут немає навмисно: панель мусить бути
 *  правдивою сама по собі, а не «правдивою, якщо перепитати оверлей». */
const panelReport = (page) => page.evaluate(() => ({
  /* Крихти нової панелі: ПРЕДКИ — кнопки `.insp-pb` у `.insp-path`, сам вибраний — `.insp-name` (0.29.0; до того
     всі троє стояли в `.insp-crumbs`). Збираємо в той самий список, що віддає `crumbs`: від кореня до елемента. */
  crumbs: [...document.querySelectorAll("#insp-panel .insp-path .insp-pb"), ...document.querySelectorAll("#insp-panel .insp-name")]
    .map((b) => b.textContent.trim()),
  /* Розділи панелі властивостей (`data-sec`) — те, що колись були секціями звіту. */
  specs: document.querySelectorAll("#insp-panel [data-sec]").length,
  /* Імена властивостей — з `data-prop` полів: єдина адреса властивості в розмітці. */
  props: [...document.querySelectorAll("#insp-panel .insp-f[data-prop]")]
    .map((f) => f.dataset.prop),
}));

test("G. клік по крихті пінує предка — і звіт у панелі стає про НЬОГО", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: WIRE_PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  await pinByClick(page, "#target");
  const before = await panelReport(page);
  assert.deepEqual(before.crumbs, ["body", "div", "p.card"],
    "панель мусить показати крихти запіненого елемента");
  assert.ok(before.specs > 0, "панель мусить показати секції звіту, а не саму лише підказку");
  assert.equal(before.props.includes("gap"), false,
    "в абзаці секції флексу бути не мусить — інакше наступна перевірка нічого не доводить");

  /* Крихта №1 — `div` (тобто `#wrap`, батько). Клік по НІЙ, а не виклик
     `pinAt` руками: перевіряється саме проводка `data-act="inspcrumb"` →
     `BAR_ACTIONS` (`app.js`), тобто шлях дизайнера. */
  await page.click('#insp-panel [data-act="inspcrumb"][data-val="1"]');

  /* БЕЗ `waitFor`: весь ланцюжок синхронний (`inspcrumb` → `pinAt` → `_paint`
     → `_emit` → `paintBar` → `paintInsp`), і опитування, яке могло б
     замаскувати розрив, знято 17.09.2026 (Task 6). */
  assert.equal((await state(page)).pinned, "wrap",
    "клік по крихті мусить запінити предка — це робить `api.pinAt(val)`");
  const after = await panelReport(page);
  assert.deepEqual(after.crumbs, ["body", "div"],
    "після піна предка крихт меншає — панель мусить це показати");
  assert.equal(after.props.includes("gap"), true,
    "`#wrap` — флекс-контейнер, тож у панелі мусить зʼявитись поле gap (авто-лейаут): "
    + "це і є доказ, що панель показує звіт про ІНШИЙ елемент, а не перемалювала старий");
});

test("I. прокрутка панелі переживає перемальовку після виходу курсора", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: WIRE_PORT_BASE + 4 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  // Низьке вікно — інакше звіт у тіло панелі влазить цілком і прокручувати
  // нема чого (див. мапу в шапці).
  const page = await openInspector(browser, url, SHORT_VIEW);

  await pinByClick(page, "#target");

  /* Мітка на ПОТОЧНОМУ вузлі тіла панелі. Без неї перевірка була б фікцією:
     `scrollTop`, що «пережив» перемальовку, якої НЕ БУЛО, доводить рівно
     нічого. `paintInsp` переписує `innerHTML` контейнера цілком, тож мітка
     на старому вузлі зникає разом із ним — це й є доказ перемальовки. */
  const armed = await page.evaluate(() => {
    const b = document.querySelector("#insp-panel .insp-body");
    b.dataset.probe = "1";
    b.scrollTop = 120;
    return { top: b.scrollTop, canScroll: b.scrollHeight > b.clientHeight };
  });
  assert.equal(armed.canScroll, true,
    "тіло панелі мусить прокручуватись — на невеликому звіті перевірка була б порожня");
  assert.equal(armed.top, 120, "прокрутка мусить справді виставитись");

  /* Курсор геть із запіненого елемента — `#a` (ліва половина, поза плаваючою
     панеллю оверлея, див. засторогу в `centerOf`). Це ДРУГА подія на той
     самий пін: оверлей перечитує звіт без `:hover` (`_repaintPinned`) і
     сигналить нагору — саме та перемальовка, посеред якої дизайнер читає
     панель. */
  const [x, y] = await centerOf(page, "#a");
  await page.mouse.move(x, y);
  await page.waitForFunction(() => {
    const b = document.querySelector("#insp-panel .insp-body");
    return !!b && !b.dataset.probe;
  }, null, { timeout: 5000 });

  const top = await page.evaluate(() =>
    document.querySelector("#insp-panel .insp-body").scrollTop);
  assert.ok(top >= 100,
    `прокрутка мусить пережити перемальовку (було 120), а бачу ${top}`);
});

/* ── Task 8: хром оверлея — лише там, де він потрібен ────────────────────── */

test("J. у канвасі оверлей не малює власного хрому — ні вікна, ні чипа, ні кнопки", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: WIRE_PORT_BASE + 6 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  /* Саме ЗАПІНЕНИЙ елемент: плаваюче вікно звіту народжується не на
     `setChrome`, а пізніше — на першому піні (`_renderPanel`). Перевірка без
     піна була б зелена й на оверлеї, який ховати вікно взагалі не вміє. */
  await pinByClick(page, "#target");
  assert.equal((await state(page)).pinned, "target", "без піна перевірка нічого не доводить");

  const chrome = await page.evaluate(() => {
    const sh = document.getElementById("frame").contentDocument
      .querySelector("[data-canvas-inspector]").shadowRoot;
    /* «Показано» рахуємо по КОРОБЦІ, а не по класу: клас — наша ж
       домовленість, а дизайнер бачить пікселі. `.hidden` це
       `display:none !important`, тобто коробка 0×0.

       ⚠️ НЕ `offsetParent`: і вікно, і кнопка — `position:fixed`, а в такого
       елемента `offsetParent` дорівнює `null` ЗАВЖДИ, видимий він чи ні.
       Перша версія цієї перевірки стояла саме на ньому й була фікцією —
       мутація «хай `setChrome(false)` не запамʼятовує стан» її ПЕРЕЖИЛА. */
    const shown = (s) => {
      const n = sh.querySelector(s);
      if (!n) return false;
      const r = n.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    return {
      panel: shown(".panel"),
      btn: shown(".btn"),
      /* `.modes` більше не існує ВЗАГАЛІ — тому рахуємо вузли, а не видимість:
         `shown()` на видаленому вузлі віддав би `false` і в тому разі, якби
         чип просто перейменували. */
      modes: sh.querySelectorAll(".modes,[data-mode]").length,
    };
  });
  assert.equal(chrome.panel, false,
    "плаваюче вікно звіту накривало б макет, який дизайнер вимірює — звіт показує права панель");
  assert.equal(chrome.btn, false, "кнопка оверлея в канвасі схована — перемикач живе у смузі");
  assert.equal(chrome.modes, 0, "чипа режимів не мусить лишитись навіть вузлом");

  /* А сам звіт при цьому Є — у правій панелі. Без цього рядка «хрому немає»
     не відрізнити від «інспектор нічого не показує взагалі». */
  assert.ok((await panelReport(page)).specs > 0,
    "звіт мусить бути — просто в панелі оболонки, а не у власному вікні оверлея");
});

test("K. сторінка БЕЗ канваса лишається зі своїм вікном звіту — і малює його тим самим рендерером", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: WIRE_PORT_BASE + 8 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  /* Той самий шлях, яким сторінку відкривають насправді (`/commented?…` прямо
     в браузері): ні канваса, ні iframe, ні правої панелі — і `setChrome`
     не покличе ніхто. Це не теоретичний випадок: на ньому тримається весь
     `tests/live/inspector.test.mjs`. */
  const bare = await browser.newPage({ viewport: VIEW });
  t.after(() => bare.close());
  await bare.goto(`${url}/commented?it=it1&page=holovna&ch=local`);
  await bare.waitForFunction(() => !!(window.CanvasInspector && window.CanvasInspector._host),
    null, { timeout: 15000 });

  await bare.keyboard.press("i");
  const box = await bare.locator("#target").boundingBox();
  await bare.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

  const panel = await bare.evaluate(() => {
    const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
    const p = sh.querySelector(".panel");
    return { hidden: p.classList.contains("hidden"), html: p.innerHTML };
  });
  assert.equal(panel.hidden, false,
    "без канваса вікно звіту — єдине місце, де каскад видно взагалі");
  /* `insp-spec` — клас, який малює РІВНО `insp-report.js`. Тобто цей рядок
     доводить дві речі одразу: звіт на голій сторінці не зник, і малює його
     той самий рендерер, що й панель оболонки, а не друга реалізація поруч. */
  assert.match(panel.html, /insp-spec/,
    "вікно мусить малювати той самий рендерер, що й панель — один звіт, не два");
  assert.match(panel.html, /insp-crumbs/, "крихти теж із спільного рендерера (вікно без канваса лишилось на `insp-report.js`)");

  /* ⛔ Спільний рендерер — так, спільні РУЧКИ — ні, і це той самий контракт з
     іншого боку. Проводка тюнера (`data-act="insptune…"` → `BAR_ACTIONS`) і
     його модель живуть у БАТЬКІВСЬКОМУ вікні; у цього документа батька може
     не бути взагалі, тобто ручці тут нема ні кого слухати, ні куди писати.
     До 18.09.2026 рендерер малював їх безумовно, і на цій самій сторінці
     стояло 15 крутилок і 3 пікери, жодна з яких ні на що не реагувала —
     виміряно живцем. Дизайнер не розрізняє «крок не існує» і «натиснути
     нікуди»: він тисне стрілку, нічого не стається, і далі не вірить жодній
     ручці в панелі (докстрінг `NUMERIC`, `insp-report.js`). */
  const knobs = await bare.evaluate(() => {
    const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
    const p = sh.querySelector(".panel");
    return {
      inputs: p.querySelectorAll("input").length,
      acts: [...p.querySelectorAll("[data-act]")]
        .map((n) => n.dataset.act).filter((a) => a.startsWith("insptune")).length,
    };
  });
  assert.equal(knobs.inputs, 0,
    `у вікні звіту ${knobs.inputs} полів вводу, які нікому слухати — мертва ручка`);
  assert.equal(knobs.acts, 0, "розмітка ручок тюнера в документі без проводки");
  /* А значення при цьому лишилось на екрані — відмова від ручки не сміє
     забрати те, заради чого звіт і читають. */
  assert.match(panel.html, /16px/, "замість ручки мусить лишитись чесний текст значення");
});

test("M. «Надіслати» ставить ready, будь-яка правка вертає draft, і підвал переживає перезавантаження", async (t) => {
  /* ⛔ ЩО ТУТ НАСПРАВДІ ПЕРЕВІРЯЄТЬСЯ (T-39). Пакет зберігається на кожен
     поворот ручки, тож на диску «дизайнер щойно крутнув» і «дизайнер
     закінчив» виглядали однаково — читач не мав чим їх розрізнити. Кнопка
     «Надіслати Клоду» нічого не надсилає: вона ставить `status: ready`.
     Обидві половини несучі, і обидві живі:
       · натиснув — у ФАЙЛІ стало `ready` (інакше сигнал нікуди не доїхав);
       · крутнув після цього — у файлі знову `draft` (інакше пакет каже
         «готово» про роботу, яка триває, тобто бреше).

     Тут же — і те, заради чого до T-39 існувала окрема вкладка з власним
     станом: робота дизайнера переживає ПЕРЕЗАВАНТАЖЕННЯ РАМКИ. Модель живе в
     батьківському вікні, а документ макета народжується наново на кожному
     присвоєнні `frame.src`.

     МУТАЦІЇ: прибрати `markReady` з `tuneReady` (`app.js`) — перша половина
     червоніє; прибрати `drafted` із `setEdit` (`tuner-model.js`) — друга. */
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: WIRE_PORT_BASE + 12 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  const pkg = () => page.evaluate(() => fetch("/api/tuner").then((r) => r.json()));
  const statusOf = async () => (await pkg()).package?.status ?? null;
  const waitStatus = async (want) => {
    for (let i = 0; i < 40; i += 1) {
      if (await statusOf() === want) return;
      await page.waitForTimeout(50);
    }
    assert.equal(await statusOf(), want, `пакет так і не став «${want}»`);
  };

  /* Крутимо ТИМ САМИМ шляхом, що дизайнер: пін кліком, потім стрілка в полі
     панелі. Підвалу до першої правки немає взагалі — і це теж перевірка. */
  assert.equal(await page.locator("#insp-panel .insp-foot .insp-send").count(), 0,
    "порожній підвал обіцяв би дію, якої немає");
  await pinByClick(page, "#target");
  const field = '#insp-panel [data-act="insptune"][data-prop="padding-top"]';
  await page.waitForSelector(field, { timeout: 5000 });
  await page.focus(field);
  await page.keyboard.press("ArrowUp");
  await page.waitForSelector("#insp-panel .insp-send", { timeout: 5000 });
  await waitStatus("draft");

  /* Надіслати → ready, і позначка про це зʼявляється в панелі. Питаємо ФАЙЛ,
     а не памʼять вкладки: читач приходить саме за файлом. */
  await page.click("#insp-panel .insp-send");
  await waitStatus("ready");
  assert.equal(await page.locator("#insp-panel .insp-ready").count(), 1,
    "дизайнер мусить бачити, що пакет позначено готовим");

  /* Наступний поворот ручки — і пакет знову чернетка. */
  await page.focus(field);
  await page.keyboard.press("ArrowUp");
  await waitStatus("draft");
  assert.equal(await page.locator("#insp-panel .insp-ready").count(), 0,
    "позначка «готово» лишилась на екрані, хоч пакет уже чернетка");

  /* І робота переживає перезавантаження документа макета: модель живе в
     батьківському вікні. Присвоюємо `frame.src` руками — рівно те, що робить
     `applyMode` на кожному повному рендері. */
  /* ⛔ TD-35 (07.10.2026): доти тест ЧЕКАВ `CanvasInspector` і `.insp-send` одразу
     після `f.src = f.src` — а навігація асинхронна, тож обидва чекання
     спрацьовували на СТАРОМУ документі й старій панелі. Тест хвалив стан «до»
     і падав лише тоді, коли під навантаженням перезавантаження встигало
     раніше: у новому документі інспектор вимкнений, панель схована. Тепер
     мітимо старе вікно й чекаємо, поки рамка стане НОВОЮ, а тоді вмикаємо
     інспектор кнопкою смуги, як дизайнер, — і дивимось, що правки дожили. */
  await page.evaluate(() => {
    const f = document.getElementById("frame");
    f.contentWindow.__oldDoc = true;
    f.src = f.src;
  });
  await page.waitForFunction(() => {
    const w = document.getElementById("frame").contentWindow;
    return w && !w.__oldDoc && w.document.readyState === "complete" && w.CanvasInspector;
  }, null, { timeout: 15000 });
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.on), false,
    "новий документ — новий інспектор, вимкнений (так задумано)");
  await page.click('#hud [data-act="inspector"]');
  await page.waitForSelector("#insp-panel .insp-send", { timeout: 15000 });
  /* ДВІ кнопки скидання: ↕ у панелі пише пару padding-top/bottom, тобто дві правки (до 0.29.0 було одне поле). */
  assert.equal(await page.locator('#insp-panel [data-act="insptunedrop"]').count(), 2,
    "перезавантаження рамки знесло список змін — стан жив у документі макета");
});

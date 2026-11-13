/**
 * Живі перевірки правої панелі інспектора (Task 5 Плану B). Юніт
 * (`tests/shell-inspect.test.mjs`) перевіряє лише РОЗМІТКУ чистої функції
 * `inspectHTML` — не те, що на контроли щось РЕАГУЄ в бою, і не те, що
 * панель і оверлей УСЕРЕДИНІ iframe справді керують ОДНИМ станом, а не двома.
 * Саме це — і рівно це — перевіряють живі тести нижче.
 *
 * ⛔ Свідомо НЕ дублюємо тут: `tests/live/inspector.test.mjs` уже стереже сам
 * оверлей (режим лінійки, геометрію, клавіші `I`/`M`/`Esc` на голій сторінці
 * `/commented?...`, без канваса й без цієї панелі взагалі) — 20+ перевірок,
 * знятих мутаційно. Ті перевірки тут ПОВТОРЮВАТИ не треба: вони про те, що
 * малює оверлей, а не про те, що керує ним панель.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   A (відкриття)      — кнопка смуги `[data-act="inspector"]` мусить і
 *                         увімкнути оверлей, і показати `#insp-panel`
 *                         ОДРАЗУ (перевірка БЕЗ `waitFor`/таймауту —
 *                         навмисно, дивись коментар у тесті).
 *                         Запобіжник: виклик `paintInsp()` усередині
 *                         `paintBar()` (докстрінг `paintBar`, `app.js`) —
 *                         прибери його, і панель не зʼявиться ВЗАГАЛІ.
 *                         До 17.09.2026 замість «взагалі» тут стояло «лише
 *                         за ДО 300мс опитуванням»: опитування (`app.js`)
 *                         підміняло собою забутий виклик, і саме тому
 *                         перевірка писалась негайною. Опитування знято
 *                         (Task 6) — негайність від цього не зайва, а
 *                         сильніша: тепер вона стереже сам синхронний шлях.
 *   B (перемикач        — клік по `[data-act="insptab"][data-val="ruler"]`
 *      режиму)            мусить змінити РЕЖИМ САМОГО ОВЕРЛЕЯ
 *                         (`CanvasInspector.mode`), а не лише підсвітку
 *                         кнопки в панелі. Запобіжник: рядок
 *                         `api.setMode(val)` у `BAR_ACTIONS.insptab`.
 *                         Мутація «прибери цей рядок, лиши тільки
 *                         `paintInsp()`» ловиться РІВНО цією перевіркою:
 *                         підсвітка помінялась би (панель перемальована зі
 *                         старим `state.mode`, бо `api.mode` не змінився —
 *                         тобто підсвітка НАСПРАВДІ лишилась би тією самою),
 *                         а `CanvasInspector.mode` — ні.
 *   C (Esc драбинкою)   — фізичний `Escape`, надісланий У ФОКУС iframe (де
 *                         й живе `_onKey`), з чистого стану (без піна, режим
 *                         каскад) мусить вимкнути інспектор ЦІЛКОМ — і
 *                         панель мусить зникнути РАЗОМ із ним, ОДРАЗУ (та
 *                         сама причина, що в A — перевірка теж БЕЗ `waitFor`).
 *                         Запобіжник: `onChange` (`app/vendor/inspector.js`,
 *                         `_emit`) поставлений на `paintBar`
 *                         (`frame.addEventListener('load')`, `app.js`) —
 *                         прибери присвоєння, і оверлей вимкнеться, а панель
 *                         лишиться висіти. До 17.09.2026 вона б усе-таки
 *                         зникла — за ДО 300мс опитуванням; його знято.
 *   D (Огляд)           — перемикання «Макет → Огляд» ховає панель, навіть
 *                         коли `CanvasInspector.on` лишається `true`
 *                         (кадри «Огляду» не чіпають `frame.src` узагалі —
 *                         `applyMode`, гілка `mode==='canvas'` — тож сам
 *                         оверлей не вимикається). Запобіжник: перевірка
 *                         `state.shellMode !== 'layout'` у `inspectHTML`
 *                         (`shell-inspect.js`) — той самий принцип, за яким
 *                         із смуги зникає кнопка інспектора в «Огляді».
 *                         Назад у «Макет» панель САМА не вертається — і це
 *                         ОЧІКУВАНО, не бага Task 5: `applyMode` перезаван-
 *                         тажує iframe на кожному повному `render()`,
 *                         скидаючи `on` назад у `false` (той самий ефект уже
 *                         гасить підсвітку кнопки інспектора в смузі, Task 3
 *                         — межа, що стоїть до Task 5 і поза ним). Перевірка
 *                         бере саме те, що ЦЕЙ round-trip обіцяє: цикл не
 *                         зламаний — після повернення бар усе ще вміє
 *                         відкрити інспектор і панель заново.
 *   E (клавіша M          — режим, змінений СПРАВЖНЬОЮ клавішею `M` УСЕРЕДИНІ
 *      усередині iframe)    iframe (не кліком по панелі), мусить дійти до
 *                         панелі. Несе це ПОДІЯ, а не опитування:
 *                         `setMode()` кличе `_emit()` (`inspector.js`,
 *                         Task 4), той — `onChange`, тобто `paintBar` →
 *                         `paintInsp`. `keydown` за межі iframe і далі не
 *                         спливає (capture на `window` усередині), тож
 *                         жодного DOM-слухача в батька тут немає й бути не
 *                         може — весь шлях тримається на одному колбеку.
 *                         Запобіжник: `api.onChange = paintBar`
 *                         (`frame.addEventListener('load')`, `app.js`) і
 *                         виклик `paintInsp()` у `paintBar` — прибери
 *                         будь-який із двох, і перевірка чекає на
 *                         `aria-pressed="true"` вічно (таймаут), бо БІЛЬШЕ
 *                         НІХТО не перемальовує панель після клавіші,
 *                         натиснутої не по ній. До 17.09.2026 запобіжником
 *                         тут був таймер `setInterval(…, 300)`; Task 4 дав
 *                         оверлею подію, і другий механізм на той самий стан
 *                         знято (Task 6) — два механізми на один стан рано
 *                         чи пізно розходяться.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { runShoot } from "../../bin/shoot.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Свій `portBase`: `node --test` крутить файли паралельно (сусідні бази:
   shell-bar=9390, shell-panel=9490, inspector=8990). */
const PORT_BASE = 9590;
const VIEW = { width: 1400, height: 900 };

/* Градієнт, не порожня сторінка — та сама причина, що в
   `tests/live/shell-bar.test.mjs`: порожній знімок стискається нижче
   `BYTES_FLOOR` і лишається «застарілим», тож клік по «Огляду» замовляв би
   СПРАВЖНЮ автозʼємку замість побачити вже свіжу. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${id}</h1></body></html>`;

/** Макет, готовий до роботи, і кнопка інспектора смуги вже клікабельна. */
async function openCanvas(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  return page;
}

test("A. кнопка смуги відкриває панель і вмикає оверлей РАЗОМ", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  assert.equal(await page.locator("#insp-panel").isVisible(), false,
    "панель не мусить бути видима до відкриття");
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), false, "оверлей не мусить бути увімкнений заздалегідь");

  await page.click('#hud [data-act="inspector"]');
  /* БЕЗ `waitFor`/таймауту: перевіряємо стан ОДРАЗУ, щойно клік повернув
     керування. `BAR_ACTIONS.inspector` (`app.js`) синхронний (жодного
     `await` на цьому шляху), тож до моменту, коли Playwright віддає
     керування назад, `paintInsp()` уже мусить відпрацювати.

     Негайність писалась проти опитування (300мс): із таймаутом перевірка не
     відрізнила б «кнопка відкриває панель одразу» від «кнопка нічого не
     робить, а панель наздоганяє опитуванням» — мутація «прибери
     `paintInsp()` із `paintBar()`» лишалась би зеленою. Опитування знято
     17.09.2026 (Task 6), і та сама мутація тепер не дає панелі зʼявитись
     узагалі — тобто перевірка стала СИЛЬНІШОЮ, а не зайвою: вона й далі
     стереже, що панель відкриває сама дія, а не щось, що приїде потім. */
  assert.equal(await page.locator("#insp-panel").isVisible(), true,
    "кнопка смуги мусить показати панель ОДРАЗУ, тим самим синхронним шляхом");
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), true, "кнопка смуги мусить увімкнути й оверлей");

  const tabs = await page.locator('#insp-panel [data-act="insptab"]').count();
  assert.ok(tabs >= 2, `у панелі мусить бути перемикач режиму (два значення), а бачу ${tabs}`);
  assert.ok(await page.locator('#insp-panel [data-act="inspector"]').count() >= 1,
    "у панелі немає кнопки закриття");

  /* Закриття З ПАНЕЛІ — ТА САМА дія `data-act="inspector"`, що й кнопка
     смуги (не друга реалізація поруч із першою): клік мусить і сховати
     панель, і вимкнути оверлей, рівно як і кнопка, з якої почався тест. */
  await page.click('#insp-panel [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "hidden", timeout: 3000 });
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), false, "кнопка закриття панелі мусить вимкнути й оверлей");
});

test("B. перемикач режиму панелі міняє РЕЖИМ ОВЕРЛЕЯ, а не лише підсвітку", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 10 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  await page.click('#hud [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "visible" });
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.mode), "cascade", "інспектор мусить починати в каскаді");
  assert.equal(await page.locator('[data-act="insptab"][data-val="cascade"]').getAttribute("aria-pressed"), "true");

  await page.click('#insp-panel [data-act="insptab"][data-val="ruler"]');
  // Чекаємо на СПРАВЖНІЙ стан оверлея, а не на підсвітку панелі: підсвітка
  // могла б перемалюватись і на зламаній проводці (стара `state.mode`, той
  // самий рядок), тож саме тут і ловиться мутація «прибери `api.setMode`».
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.mode === "ruler", null, { timeout: 3000 });

  assert.equal(await page.locator('[data-act="insptab"][data-val="ruler"]').getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator('[data-act="insptab"][data-val="cascade"]').getAttribute("aria-pressed"), "false");

  // І назад — перевіряємо, що дія симетрична, а не «зробили один раз і забули».
  await page.click('#insp-panel [data-act="insptab"][data-val="cascade"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.mode === "cascade", null, { timeout: 3000 });
});

test("C. Escape у макеті вимикає інспектор драбинкою — панель зникає разом із ним", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 20 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  await page.click('#hud [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "visible" });

  /* Фокус УСЕРЕДИНІ iframe, БЕЗ кліку по його вмісту: клік, поки інспектор
     увімкнений, ловить `_onDown` оверлея й ПІНУЄ елемент під курсором —
     тоді перший `Escape` лише зняв би пін (та сама драбинка, перевірена в
     `tests/live/inspector.test.mjs`, перевірка J/Q), і довелось би тиснути
     Escape двічі, щоб дістатись до `set(false)`. Програмний `.focus()` дає
     iframe фокус БЕЗ mousedown/click, тобто без піна — рівно чистий стан
     «каскад, нічого не запінено», з якого ОДИН Escape вимикає інспектор
     цілком (`_onKey`, гілка `else this.set(false)`). */
  const frame = page.frames().find((f) => f !== page.mainFrame());
  assert.ok(frame, "не знайшов iframe макета");
  await frame.evaluate(() => window.focus());
  await page.keyboard.press("Escape");

  /* БЕЗ таймауту — та сама причина, що в перевірці A: `set(false)` кличе
     `onChange` (=`paintBar`) СИНХРОННО (`app/vendor/inspector.js`, `_emit`),
     тож до моменту, коли `page.keyboard.press` віддає керування назад, панель
     мусить уже зникнути. Писалась негайність проти опитування: поки воно
     стояло, з `waitFor(…, {timeout:3000})` перевірка лишалась би зеленою й
     тоді, коли `frame.addEventListener('load', …)` забув би призначити
     `api.onChange = paintBar` УЗАГАЛІ (мутаційно перевірено) — оверлей
     вимкнувся б однаково (`_onKey` сам чіпає лише `this.on`), а панель
     наздогнала б його за 300мс. Опитування знято 17.09.2026 (Task 6): та
     сама мутація тепер лишає панель висіти НАЗАВЖДИ, і негайна перевірка
     ловить це першою ж. */
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), false, "Escape мусить вимкнути інспектор");
  assert.equal(await page.locator("#insp-panel").isVisible(), false,
    "панель мусить зникнути ОДРАЗУ разом з інспектором — тим самим колбеком");
});

test("D. «Огляд» ховає панель, навіть коли оверлей лишається увімкненим", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 30 });
  t.after(() => child.kill());

  // Знімаємо фікстуру ЗАЗДАЛЕГІДЬ (та сама причина, що в shell-bar.test.mjs):
  // без цього клік по «Огляду» замовляє СПРАВЖНЮ автозʼємку.
  await runShoot({ dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
                   launch: () => chromium.launch() });

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  await page.click('#hud [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "visible" });

  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.locator("#insp-panel").waitFor({ state: "hidden", timeout: 5000 });
  // Оверлей лишається увімкненим — «Огляд» не чіпає `frame.src` узагалі
  // (`applyMode`, гілка `canvas`), тож зникнення панелі — це ГЕЙТ виду, а не
  // побічний ефект того, що оверлей десь вимкнувся.
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), true, "оверлей не мав вимкнутись сам");

  /* Назад у «Макет». Панель ТУТ НЕ мусить сама повернутись — і це не
     недогляд Task 5, а межа, що стоїть іще з Task 3: `applyMode` на кожному
     повному `render()` переприсвоює `frame.src` (навіть тим самим рядком —
     див. коментар над `setViewport`, `app.js`), а це ПЕРЕЗАВАНТАЖУЄ iframe:
     виміряно живою пробою (окремим одноразовим скриптом поза набором тестів)
     — `CanvasInspector` після зворотного переходу вже ІНШИЙ обʼєкт, з
     `on:false` за замовчуванням, хоч рядок `frame.src` лишається тим самим.
     Кнопка інспектора в смузі («Task 3») втрачає підсвітку через РІВНО ту
     саму причину — тож перевіряти тут «панель пережила подорож» означало б
     перевіряти те, чого не обіцяє й сама смуга. Натомість перевіряємо, що
     цикл НЕ зламаний: бар мусить і після повернення вміти відкрити
     інспектор і панель заново. */
  await page.click('#bar [data-act="mode"][data-val="layout"]');
  await page.waitForFunction(() => !!(document.getElementById("frame")?.contentWindow?.CanvasInspector),
    null, { timeout: 5000 });
  assert.equal(await page.locator("#insp-panel").isVisible(), false,
    "після повернення в «Макет» інспектор мусить бути вимкнений (макет перезавантажився) — панелі не місце");

  await page.click('#hud [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "visible", timeout: 3000 });
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on), true, "після повернення інспектор мусить УМІТИ ввімкнутись знову");
});

test("E. клавіша M УСЕРЕДИНІ iframe доходить до панелі ПОДІЄЮ", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  await page.click('#hud [data-act="inspector"]');
  await page.locator("#insp-panel").waitFor({ state: "visible" });
  assert.equal(await page.locator('[data-act="insptab"][data-val="cascade"]').getAttribute("aria-pressed"), "true");

  /* Фокус iframe БЕЗ кліку по вмісту — та сама причина, що в перевірці C
     (клік пінує елемент і не заважає режиму, але тут річ у тім, щоб зміну
     вніс РІВНО той шлях, заради якого й писана ця перевірка: клавіша,
     натиснута не по нашій кнопці). */
  const frame = page.frames().find((f) => f !== page.mainFrame());
  assert.ok(frame, "не знайшов iframe макета");
  await frame.evaluate(() => window.focus());
  await page.keyboard.press("m");

  /* Оверлей змінився одразу (перевірено й у tests/live/inspector.test.mjs);
     тут головне — що ЦЕ побачила ПАНЕЛЬ, а не лише сам оверлей. І побачила
     ТИМ САМИМ синхронним ланцюжком, що й у C: `_onKey` → `toggleMode` →
     `setMode` → `_emit` → `onChange` (=`paintBar` → `paintInsp`). Тому
     перевірка негайна, як A і C: поки тут стояло опитування (знято
     17.09.2026, Task 6), таймаут на 2с був ЄДИНИМ чесним варіантом і
     водночас ховав би будь-який розрив у ланцюжку — тепер розрив означає
     «панель не оновиться ніколи», і бачимо ми це відразу. */
  assert.equal(await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.mode), "ruler", "клавіша M мусить змінити режим оверлея");
  assert.equal(await page.locator('[data-act="insptab"][data-val="ruler"]').getAttribute("aria-pressed"),
    "true", "панель мусить побачити клавішу M ОДРАЗУ — подією, а не опитуванням");
  assert.equal(await page.locator('[data-act="insptab"][data-val="cascade"]').getAttribute("aria-pressed"), "false");
});

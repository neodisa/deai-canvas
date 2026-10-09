/**
 * Живий тест ТЮНЕРА: ручка на макеті (Task 13) і редаговані значення в рядках
 * звіту (Task 14).
 *
 * ⛔ Чому ЖИВИЙ, а не юніт. Обидві задачі цілком про те, чого в node немає:
 * Task 13 пише в інлайн-стиль і питає браузер, чи значення взагалі прийнялось
 * і чи виграло каскад у правила з `!important`; Task 14 замикає коло
 * «панель → оверлей → макет → назад у панель» через ДВА документи (оболонка і
 * iframe макета). Підробка CSSOM перевіряла б НАШІ уявлення про нього — рівно
 * ті, що вже бували помилкові.
 *
 * Мапа «перевірка → запобіжник → що буде, якщо запобіжник прибрати»
 * (знята мутаційно, не написана з голови):
 *
 *   A (жива зміна)      — `el.style.setProperty` у `applyTune`. МУТАЦІЯ: тіло
 *                         `applyTune` у `return true` без запису. Перевірка
 *                         червоніє: на макеті нічого не змінилось, тобто
 *                         ручка мертва, а панель однаково рапортує про зміну.
 *   B (файл недоторка-  — сам вибір інлайн-стилю замість запису в макет.
 *      ний)               Червоніє, щойно тюнер почне писати у файл — те, чого
 *                         він не сміє робити ЗА ВИЗНАЧЕННЯМ: макет лишається
 *                         джерелом правди рівно тому, що тюнер у нього не пише.
 *   C (`important`)     — третій аргумент `setProperty`. Прибери його — і
 *                         правило сторінки з `!important` мовчки переб'є
 *                         накручене (`pickWinner`: вага 3 проти 2). Дизайнер
 *                         крутить, нічого не відбувається, і вирішує, що
 *                         зламався інструмент.
 *   D (панель бачить    — `this._pinSeq += 1` у `_tuned()`. Прибери — і
 *      нове число)        сигнатура `_emit` (`on|mode|_pinSeq|_measSig`) від
 *                         кручення не зміниться ЖОДНИМ полем: подія не
 *                         народиться, батько не перечитає звіт, і панель
 *                         лишиться з числом ДО кручення. Найтихіший з усіх
 *                         можливих провалів цієї фічі.
 *   E (непридатне не    — читання поля назад після запису. Прибери — і
 *      записується)       `applyTune` рапортуватиме успіх на `-8px` для
 *                         `padding`, який CSSOM тихо ковтнув: у пакет поїде
 *                         обіцянка зміни, якої дизайнер на макеті не бачив.
 *   F (сліду не лишає)  — `removeAttribute('style')` у `clearTune`. Прибери —
 *                         і після скидання в розмітці лишиться `style=""`,
 *                         тобто слід інструмента, який обіцяв не лишати слідів.
 *   G (коло замкнулось) — уся проводка Task 14 (`insptune` → `tuneSet` →
 *                         `applyTune`). Це та сама перевірка, що A, але з
 *                         ІНШОГО кінця: не з консолі, а з поля в панелі, яке
 *                         крутить дизайнер.
 *   H (старе в списку)  — рядок списку змін у підвалі (`tuneRow`,
 *                         `app/shell-inspect.js`). Прибери — і дизайнер
 *                         перестане бачити, ВІД ЧОГО він пішов; без цього
 *                         крутилка перетворюється на односторонні двері.
 *                         (До T-39 те саме перевірялось на `insp-was` у
 *                         самому рядку звіту — воно там і коштувало 28px
 *                         висоти на кожну правку.)
 *   I (не все крутиться)— `NUMERIC`/`HEX6` у `control()`. Підроблена крутилка
 *                         на `font-family` обіцяла б крок там, де кроку немає.
 *   O (рядок не росте) — `height` поля, `white-space:nowrap` і `text-overflow`
 *                         у `app/styles.css` (T-39). Це ЄДИНА перевірка, що
 *                         бачить саму ваду, з якої почалась T-39: панель
 *                         «скакала» — накручений рядок ріс із 16px до 44px, і
 *                         все нижче зʼїжджало на 28px за кожну правку. Жоден
 *                         юніт цього не бачить: висоту рахує браузер.
 *   J (походження ДО    — порядок `identity()` → `applyTune()` у `tuneSet`
 *      інлайну)           (`app/app.js`). Перестав їх — і `rule` кожної
 *                         накрученої правки стане `[style]`, тобто пакет
 *                         радитиме Клоду правити той самий атрибут, який
 *                         створив сам тюнер. Перевірка дивиться на те, що
 *                         `identity()` віддав НАСПРАВДІ в тому виклику, з
 *                         якого `setEdit` бере `rule`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу. `startServer` бере `portBase + hrtime % 100`,
   тобто кожен сервер займає смугу в сто портів. Найвище зайняте —
   `tuner-identity` (10690, тобто до 10789), тож 10790 — перший вільний. */
const PORT_BASE = 10790;
const VIEW = { width: 1400, height: 900 };

/**
 * Сторінка, зібрана під ОДНЕ питання: чи справді ручка крутить макет.
 *
 * Навмисні в ній три речі:
 *   · `#target` бере відступ із правила КЛАСУ (`.card`) — тобто в пакеті
 *     `rule` мусить бути `.card`, а не `[style]` (J);
 *   · `#shout` має колір, прибитий `!important` просто в правилі сторінки —
 *     без пріоритету в `applyTune` накручене туди не доїде взагалі (C);
 *   · `font-family` у `.card` задана явно, щоб у звіті був рядок, який крутити
 *     НІЧИМ (I).
 *
 * Градієнт у `body` — з тієї ж причини, що в сусідніх живих тестах: порожній
 * знімок стискається нижче `BYTES_FLOOR`, числився б застарілим, і вхід у
 * макет замовив би справжню зʼємку.
 */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--sp-4:16px}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:var(--sp-4);background:#eef;width:260px;height:160px;
  font-family:"E-Ukraine",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  color:#123456}
#shout{color:#ff0000 !important}
</style></head><body>
<div id="wrap" class="row">
  <p id="target" class="card">Картка ${id}</p>
  <p id="shout" class="card">Крик ${id}</p>
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

/** Що браузер СПРАВДІ показує на елементі макета. */
const shown = (page, sel, prop) => page.frameLocator("#frame").locator(sel)
  .evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop);

/** Накрутити з консолі — найкоротший шлях до самої ручки, без UI. */
const tune = (page, prop, value) => page.evaluate(([p, v]) => document
  .getElementById("frame").contentWindow.CanvasInspector.applyTune(p, v), [prop, value]);

/**
 * Значення В ПОЛІ звіту правої панелі — те, що дизайнер читає про ЦЮ
 * властивість.
 *
 * Не `innerText` усієї панелі: у `.card` усі чотири відступи однакові, тож
 * пошук числа по всій панелі не відрізнив би «накручений padding-top» від
 * «недоторканий padding-left», і перевірка зеленіла б на будь-якому з них.
 *
 * Адреса поля — `data-prop` на самому полі (T-39). До того рядок шукали за
 * текстом `<dt>` з іменем властивості; після перебудови під затверджений
 * макет імені в рядку немає взагалі — чотири відступи стоять смугою зі
 * стрілками, парні властивості під спільним підписом.
 *
 * Одиниця береться з `data-unit` поля, а не з видимого `.insp-unit`: у смузі
 * відступів видимої одиниці немає свідомо (getComputedStyle віддає margin і
 * padding завжди в px, а чотири поля в рядок не лишають місця на «px»), і
 * саме `data-unit` — те, що поїде в макет. Що видима одиниця стоїть там, де
 * мусить, перевіряє `tests/insp-report.test.mjs`.
 */
const rowValue = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  if (!f) return null;
  const field = f.querySelector("input");
  if (field) return field.value + (field.dataset.unit || "");
  const txt = f.querySelector(".insp-txt");
  return txt ? txt.textContent.trim() : null;
}, prop);

/** Чи є в полі крутилка. `null` — такого поля в звіті немає взагалі. */
const rowStepper = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return f ? !!f.querySelector('[data-act="insptune"]') : null;
}, prop);

/** Чи позначене поле як накручене. */
const rowTuned = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return !!(f && f.hasAttribute("data-tuned"));
}, prop);

/**
 * Дочекатись значення в рядку. Через `rowValue`, а не через `innerText`
 * панелі: значення живе в `value` поля, а `innerText` полів не бачить — цей
 * тест на цьому вже й попався.
 */
async function waitRow(page, prop, want) {
  for (let i = 0; i < 60; i += 1) {
    if (await rowValue(page, prop) === want) return;
    await page.waitForTimeout(50);
  }
  assert.equal(await rowValue(page, prop), want,
    `рядок ${prop} так і не дочекався значення ${want}`);
}

/**
 * Старе значення правки — із СПИСКУ ЗМІН у підвалі панелі (T-39), або null.
 *
 * До T-39 воно стояло перекресленим у самому рядку звіту (`.insp-was`) — і
 * було однією з чотирьох речей, які не влазили в колонку 185px: рядок
 * переносився і ріс із 16px до 44px. Тепер воно там, де його й читають
 * списком, поруч зі стрілкою «було → стало». Той самий рядок несе й хрестик
 * скидання — єдиний, що лишився.
 */
const rowWas = (page, prop) => page.evaluate((p) => {
  const x = document.querySelector(
    `#insp-panel [data-act="insptunedrop"][data-prop="${p}"]`);
  const row = x && x.closest(".insp-chg-row");
  const from = row && row.querySelector(".insp-tune-from");
  return from ? from.textContent.trim() : null;
}, prop);

/** Значення ПІСЛЯ правки, як його показує той самий список змін. */
const rowTo = (page, prop) => page.evaluate((p) => {
  const x = document.querySelector(
    `#insp-panel [data-act="insptunedrop"][data-prop="${p}"]`);
  const row = x && x.closest(".insp-chg-row");
  const to = row && row.querySelector(".insp-tune-to");
  return to ? to.textContent.trim() : null;
}, prop);

test("ручка крутить макет живцем і не торкається його файла", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  const file = path.join(it1, "holovna", "index.html");
  const before = readFileSync(file, "utf8");

  await pin(page, "#target");
  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "фікстура зʼїхала — далі міряти нема від чого");

  /* A. Жива зміна. Питаємо БРАУЗЕР, а не наш же інлайн-атрибут: інакше
     перевірка підтверджувала б лише те, що ми щось кудись записали. */
  assert.equal(await tune(page, "padding-top", "37px"), true,
    "applyTune мусить сказати, що значення лягло");
  assert.equal(await shown(page, "#target", "padding-top"), "37px",
    "накручене не доїхало до макета — ручка мертва");

  /* D. Панель бачить НОВЕ число. Це перевірка `_pinSeq` у `_tuned()`: без
     нього сигнатура `_emit` від кручення не міняється жодним полем, події
     немає, і панель лишається зі звітом ДО кручення. */
  await waitRow(page, "padding-top", "37px");
  assert.equal(await rowValue(page, "padding-top"), "37px",
    "панель лишилась зі звітом ДО кручення");
  assert.equal(await rowValue(page, "padding-left"), "16px",
    "накрутили одну властивість, а поїхали всі — тюнер бере не ту декларацію");

  /* E. Непридатне значення НЕ записується. Від'ємний `padding` CSSOM ковтає
     тихо: без читання поля назад тюнер пообіцяв би Клоду зміну, якої на
     макеті не було. */
  assert.equal(await tune(page, "padding-top", "-8px"), false,
    "від'ємний padding не сміє рахуватись успіхом");
  assert.equal(await shown(page, "#target", "padding-top"), "37px",
    "відмова зіпсувала попереднє накручене");

  /* F. Скидання не лишає сліду — ні значення, ні порожнього атрибута. */
  const cleared = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    api.clearTune("padding-top");
    return api.pinned.hasAttribute("style");
  });
  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "після скидання мусить повернутись значення макета");
  assert.equal(cleared, false, "після скидання лишився порожній style=\"\"");

  /* C. `important`: колір `#shout` прибитий `!important` у правилі сторінки.
     Без пріоритету в `applyTune` накручене туди не доїде взагалі. */
  await pin(page, "#shout");
  assert.equal(await shown(page, "#shout", "color"), "rgb(255, 0, 0)",
    "фікстура зʼїхала — правило з !important не діє");
  assert.equal(await tune(page, "color", "rgb(0, 128, 0)"), true);
  assert.equal(await shown(page, "#shout", "color"), "rgb(0, 128, 0)",
    "правило сторінки з !important перебило накручене — ручка не діє там, "
    + "де дизайнеру найпотрібніше");

  /* B. Файл макета — недоторканий. Остання перевірка навмисно: до неї вже
     накручено все, що цей тест уміє накрутити. */
  await page.waitForTimeout(300);
  assert.equal(readFileSync(file, "utf8"), before,
    "тюнер записав у файл макета — він не сміє цього робити за визначенням");
});

test("ручка в панелі: крок, грубий крок, старе поруч, скидання", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 20 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  const file = path.join(it1, "holovna", "index.html");
  const before = readFileSync(file, "utf8");

  await pin(page, "#target");

  /* J. Записуємо, що `identity()` віддавав НАСПРАВДІ — саме з цього виклику
     `setEdit` бере `rule`, тобто «де правити» для Клода. Обгортка ставиться ДО
     першого кручення, інакше перший же виклик лишився б непоміченим.
     Виклики БЕЗ властивості пропускаємо: ними панель питає лише ключ
     елемента, селектора в них немає за визначенням. */
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    const real = api.identity.bind(api);
    window.__idCalls = [];
    api.identity = function (p) {
      const got = real(p);
      if (typeof p === "string" && p) {
        window.__idCalls.push({ prop: p, selector: got ? got.selector : null });
      }
      return got;
    };
  });

  /* I. Крутиться не все. `font-family` кроку не має — і підробляти його там
     гірше за чесний текст. */
  assert.equal(await rowStepper(page, "padding-top"), true,
    "число мусить бути редагованим");
  assert.equal(await rowStepper(page, "font-family"), false,
    "у нечислового значення не сміє бути степера");
  assert.equal(await rowTuned(page, "padding-top"), false,
    "ще нічого не крутили — позначати нічого");

  /* G. Коло замкнулось: стрілка в ПАНЕЛІ (інший документ) міняє МАКЕТ. */
  const field = '#insp-panel [data-act="insptune"][data-prop="padding-top"]';
  await page.focus(field);
  await page.keyboard.press("ArrowUp");
  await waitRow(page, "padding-top", "17px");
  assert.equal(await shown(page, "#target", "padding-top"), "17px",
    "стрілка в панелі не доїхала до макета — коло розірване");

  /* Грубий крок. Він же перевіряє, що фокус переживає перемальовку: панель
     переписує `innerHTML` на КОЖЕН поворот ручки, і без повернення фокуса
     друга стрілка поспіль не доїхала б нікуди — тобто ручка була б робочою
     рівно на одне натискання. */
  await page.keyboard.press("Shift+ArrowUp");
  await waitRow(page, "padding-top", "27px");
  assert.equal(await shown(page, "#target", "padding-top"), "27px",
    "Shift+стрілка мусить крутити вдесятеро — або фокус не пережив перемальовки");

  /* H. Старе значення видно в списку змін унизу, і саме СТАРЕ: після двох
     поворотів воно й далі те, з якого пішли, а не попереднє. */
  assert.equal(await rowTuned(page, "padding-top"), true,
    "накручене поле не позначене — дизайнер не бачить, що він накрутив");
  assert.equal(await rowWas(page, "padding-top"), "16px",
    "у списку змін мусить лишатись значення, ВІД ЯКОГО пішли");
  assert.equal(await rowTo(page, "padding-top"), "27px",
    "і те, до чого прийшли — інакше «було → стало» неповне");
  assert.equal(await rowValue(page, "padding-top"), "27px");
  assert.equal(await rowWas(page, "padding-left"), null,
    "сусіднє поле ніхто не крутив — у списку змін йому нема звідки взятись");

  /* J (перевірка). `rule` знімається з першого повороту, і зняти його треба
     ДО інлайну: інлайн виграє каскад, тож пізніше той самий виклик віддав би
     `[style]` — пораду правити атрибут, який створив сам тюнер. */
  const calls = await page.evaluate(() => window.__idCalls);
  assert.ok(calls.length >= 1, "панель жодного разу не спитала походження значення");
  assert.deepEqual(calls[0], { prop: "padding-top", selector: ".card" },
    "походження зняте ПІСЛЯ інлайну: у пакет поїде `[style]` замість правила, "
    + "що виграло насправді");

  /* Пікер — інший тип ручки, той самий шлях. Подію збуджуємо руками: нативне
     вікно вибору кольору з тесту не відкрити, а перевіряємо ми проводку, а не
     вікно ОС. */
  const picked = await page.evaluate(() => {
    const el = document.querySelector('#insp-panel [data-act="insptunecolor"][data-prop="color"]');
    if (!el) return null;
    el.value = "#00ff00";
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  });
  assert.equal(picked, true, "у рядка кольору немає пікера");
  assert.equal(await shown(page, "#target", "color"), "rgb(0, 255, 0)",
    "пікер не доїхав до макета");

  /* Скидання: хрестик у списку змін вертає макет і знімає позначку з поля.
     Це ЄДИНИЙ вхід у скидання однієї правки (T-39): разом із перекресленим
     «було» з рядка пішла й кнопка `insptuneoff`, якою те «було» й було. */
  await page.click('#insp-panel [data-act="insptunedrop"][data-prop="padding-top"]');
  await waitRow(page, "padding-top", "16px");
  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "скидання не повернуло значення макета");
  assert.equal(await rowTuned(page, "padding-top"), false,
    "поле лишилось позначеним, хоч крутити вже нічого");
  assert.equal(await rowWas(page, "padding-top"), null,
    "правка зникла з макета, але лишилась у списку змін");
  assert.equal(await shown(page, "#target", "color"), "rgb(0, 255, 0)",
    "скидання одного рядка знесло й сусідній — скидається РІВНО одна властивість");

  /* Файл макета недоторканий і після роботи через панель. */
  await page.waitForTimeout(300);
  assert.equal(readFileSync(file, "utf8"), before,
    "тюнер записав у файл макета — він не сміє цього робити за визначенням");
});

/**
 * ⛔ ОХОРОНЕЦЬ ПАСТКИ 1 (Task 17) — правка переживає перезавантаження рамки.
 *
 * Єдина брехня, якою ця фіча може зіпсуватись: «покрутив, а в пакет не
 * потрапило». Пастка 1 робить її майже неминучою — `applyMode` присвоює
 * `frame.src` на КОЖНОМУ повному рендері (`app.js:129`), і навіть той самий
 * рядок перезавантажує документ разом з усіма інлайн-стилями тюнера. Модель
 * живе в батьківському вікні й переживає це, тобто розійтись вони можуть у
 * ДВА боки, і перевірка мусить закривати обидва:
 *   · пакет на диску втратив правку — дизайнер крутив у порожнечу;
 *   · пакет правку зберіг, а на макеті її вже немає — панель показує те, чого
 *     дизайнер не бачить, і Клоду поїде обіцянка зміни, якої ніхто не бачив.
 *
 * Мапа «перевірка → запобіжник → мутація» (знята мутаційно, не з голови):
 *
 *   K (пакет на диску)  — `saveTune()` у `tuneSet` (`app.js`) і канал
 *                         `POST /api/tuner` (`serve.py`). МУТАЦІЯ: прибрати
 *                         виклик — правка нікуди не їде, перевірка червоніє
 *                         ще до перезавантаження.
 *   L (стан у БАТЬКОВІ) — `tuneState` на рівні модуля оболонки. МУТАЦІЯ:
 *                         перенести стан у документ макета
 *                         (`frame.contentWindow.__tune`) — перезавантаження
 *                         зносить його разом із документом, і пакет після
 *                         перезавантаження порожній.
 *   M (макет ПОКАЗУЄ)   — `reapplyTune` у обробнику `load` (`app.js`) і
 *                         `applyBySelector` (`inspector.js`). МУТАЦІЯ:
 *                         прибрати виклик — модель і пакет цілі, а на макеті
 *                         значення макета: панель бреше про те, що видно.
 *   N (чуже не чіпаємо) — фільтр по сторінці в `reapplyTune`. Без нього
 *                         правки іншого екрана фарбували б цей за випадковим
 *                         збігом селекторів.
 */
test("покрутив → рамка перезавантажилась → пакет цілий І макет усе ще показує", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  const file = path.join(it1, "holovna", "index.html");
  const before = readFileSync(file, "utf8");

  await pin(page, "#target");
  const field = '#insp-panel [data-act="insptune"][data-prop="padding-top"]';
  await page.focus(field);
  await page.keyboard.press("ArrowUp");
  await waitRow(page, "padding-top", "17px");
  assert.equal(await shown(page, "#target", "padding-top"), "17px",
    "ручка не доїхала до макета — далі міряти нема чого");

  /* K. Пакет уже НА ДИСКУ — без кнопки експорту, на саму лише правку. Читаємо
     через `/api/tuner`, тобто тим самим каналом, яким його прочитає той, хто
     прийде за пакетом. */
  const pkg = async () => page.evaluate(() => fetch("/api/tuner").then((r) => r.json()));
  const wanted = { prop: "padding-top", from: "16px", to: "17px" };
  const seen = (p) => (p.package?.elements || []).flatMap((el) => el.edits)
    .map((e) => ({ prop: e.prop, from: e.from, to: e.to }));
  for (let i = 0; i < 40 && !seen(await pkg()).length; i += 1) await page.waitForTimeout(50);
  const beforeReload = await pkg();
  assert.deepEqual(seen(beforeReload), [wanted],
    "правка не доїхала на диск — власник просив «записується одразу»");
  const rule = beforeReload.package.elements[0].edits[0].rule;
  assert.equal(rule, ".card",
    "у пакеті не те правило, де правити код — походження зняте вже після інлайну");

  /* Те саме, що робить будь-який клік у смузі: `applyMode` присвоює
     `frame.src`, і документ макета народжується наново. Робимо це РУКАМИ, а
     не кліком у смугу, щоб перевірка міряла саме перезавантаження, а не
     побічні ефекти конкретної кнопки. */
  await page.evaluate(() => {
    const f = document.getElementById("frame");
    f.src = f.src;
  });
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });

  /* L. Пакет ПІСЛЯ перезавантаження — той самий. Червоніє, щойно стан
     переїде в документ макета: він зникне разом із документом. */
  assert.deepEqual(seen(await pkg()), [wanted],
    "перезавантаження рамки стерло накручене — стан жив у документі макета");

  /* M. І МАКЕТ УСЕ ЩЕ ПОКАЗУЄ. Без цієї половини перевірка зеленіла б на
     найгіршому з можливих станів: пакет обіцяє Клоду зміну, якої на екрані
     вже немає, — тобто інструмент тихо бреше про те, що дизайнер бачив. */
  for (let i = 0; i < 40; i += 1) {
    if (await shown(page, "#target", "padding-top") === "17px") break;
    await page.waitForTimeout(50);
  }
  assert.equal(await shown(page, "#target", "padding-top"), "17px",
    "після перезавантаження макет показує СВОЄ значення — накручене не наклали "
    + "заново, і панель бреше про те, що видно");

  /* N. Накладаємо ТІЛЬКИ свою сторінку. Переходимо на сусідню КЛІКОМ у дереві
     сторінок — саме так, як переходить дизайнер: рамка сама по собі про
     сторінку нічого не знає, межу рахує оболонка (`tunePage`), і підміна
     самого лише `frame.src` перевіряла б не той механізм.
     Фікстура тут особливо сувора: обидві сторінки мають ОДНАКОВУ розмітку,
     тобто селектор правки резолвиться й на сусідній — якби фільтра по
     сторінці не було, «Пошук» пофарбувався б мовчки й на вигляд правильно. */
  await page.click('.panel [data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => document.getElementById("frame")
    ?.contentWindow?.location?.search?.includes("poshuk"), null, { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame")
    ?.contentWindow?.CanvasInspector, null, { timeout: 15000 });
  await page.waitForTimeout(300);
  assert.equal(await shown(page, "#target", "padding-top"), "16px",
    "правку з «Головної» наклали на «Пошук» — сторінка перестала бути межею");

  /* І назад: повернення на «Головну» правку ПОКАЗУЄ знову. Без цієї половини
     перевірка N зеленіла б і на тому, що накладання зламалось цілком. */
  await page.click('.panel [data-act="page"][data-val="holovna"]');
  await page.waitForFunction(() => document.getElementById("frame")
    ?.contentWindow?.location?.search?.includes("holovna"), null, { timeout: 15000 });
  for (let i = 0; i < 40; i += 1) {
    if (await shown(page, "#target", "padding-top") === "17px") break;
    await page.waitForTimeout(50);
  }
  assert.equal(await shown(page, "#target", "padding-top"), "17px",
    "повернулись на свою сторінку, а накрученого на ній уже немає");

  /* І файл макета недоторканий після всього: тюнер не сміє в нього писати за
     визначенням, і повторне накладання цього не міняє. */
  assert.equal(readFileSync(file, "utf8"), before,
    "тюнер записав у файл макета — він не сміє цього робити за визначенням");
});

/**
 * ⛔ ОХОРОНЕЦЬ ВАДИ, З ЯКОЇ ПОЧАЛАСЬ T-39 — і єдиний, хто її бачить.
 *
 * Скарга дизайнера була «панель скаче». Зміряно на живому макеті: рядок із
 * накрученим значенням ріс із 16px до 44px, бо перекреслене «було», поле,
 * «px» і бейдж вироку не влазили в колонку 185px і переносились; кожна правка
 * зсувала все нижче на 28px. `font-family` розповзався на три рядки просто
 * так, без жодної правки.
 *
 * Жодна перевірка в node цього не побачить: висоту рахує браузер, і будь-яка
 * підробка CSSOM перевіряла б НАШІ уявлення про перенос рядка — рівно ті, що
 * вже виявились помилковими. Тому перевірка жива і міряє три речі:
 *   · усі поля звіту мають ОДНУ висоту (довге значення не росте саме по собі);
 *   · накрутка ДВОХ значень цієї висоти не міняє;
 *   · сусіди під накрученим полем не зсунулись ні на піксель.
 *
 * Мапа «мутація → що станеться»:
 *   · прибрати `height:var(--h-sm)` з `.insp-f` — поле з довгим значенням
 *     стає вищим за сусідів, перша половина червоніє;
 *   · прибрати `white-space:nowrap` з `.insp-txt` — те саме, іншим шляхом;
 *   · вернути в рядок перекреслене «було» (`insp-was`) — рядок росте ПІСЛЯ
 *     накрутки, червоніє друга й третя половини.
 */
test("рядок звіту не росте й не зсуває сусідів — ні сам по собі, ні від накрутки", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  await pin(page, "#target");

  /** Висоти всіх полів звіту й позиція кожного — те, що бачить око. */
  const snap = () => page.evaluate(() => {
    const fs = [...document.querySelectorAll("#insp-panel .insp-f")];
    const body = document.querySelector("#insp-panel .insp-body");
    return {
      n: fs.length,
      heights: [...new Set(fs.map((f) => Math.round(f.getBoundingClientRect().height)))],
      tops: Object.fromEntries(fs.map((f) =>
        [f.dataset.prop, Math.round(f.getBoundingClientRect().top)])),
      /* Чи не ВИЛІЗ вміст за межі поля сталої висоти. Без цього рядка
         перевірка приймала б «рядок не росте» і тоді, коли він не росте лише
         тому, що зайве обрізано межею поля: значення, розрізане навпіл по
         горизонталі, — така сама брехня, як і стрибок висоти. */
      clipped: fs.filter((f) => f.scrollHeight > f.clientHeight + 2)
        .map((f) => f.dataset.prop),
      /* ВИСОТА ВМІСТУ — сума дітей тіла, а не його `scrollHeight`. Останній
         дорівнює `max(вміст, видима висота)`, тобто до першої правки він
         показує висоту самої панелі (підвалу ще немає, тіло вище за вміст), а
         після — справжній вміст. Виміряно: 716 проти 644 на ОДНАКОВОМУ
         вмісті. Перевірка на такому числі червоніла б завжди й ні про що. */
      content: [...body.children]
        .reduce((n, c) => n + Math.round(c.getBoundingClientRect().height), 0),
    };
  });

  const before = await snap();
  assert.ok(before.n >= 15, `полів у звіті ${before.n} — звіт не намалювався`);
  /* Довге значення в фікстурі саме заради цього рядка: стек шрифтів із семи
     імен у колонці ~288px — рівно те, що розповзалось на три рядки. */
  assert.deepEqual(before.clipped, [],
    "вміст поля не вліз у його висоту — значення обрізане навпіл");
  assert.deepEqual(before.heights, [28],
    `поля звіту мають різну висоту (${before.heights}) — щось переноситься `
    + "ще до першої правки, і саме так виглядало «скаче»");

  /* Накручуємо ДВА значення — одне в смузі відступів (найтісніше місце), одне
     в парі. Тим самим шляхом, що дизайнер: стрілкою в полі панелі. */
  for (const prop of ["padding-top", "font-size"]) {
    const field = `#insp-panel [data-act="insptune"][data-prop="${prop}"]`;
    await page.focus(field);
    await page.keyboard.press("ArrowUp");
    await page.waitForFunction((p) => {
      const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
      return !!(f && f.hasAttribute("data-tuned"));
    }, prop, { timeout: 5000 });
  }

  const after = await snap();
  assert.equal(after.n, before.n, "кількість полів змінилась — міряємо вже не те");
  assert.deepEqual(after.heights, [28],
    `після накрутки поля стали різної висоти (${after.heights}) — рядок знову `
    + "переноситься, і панель знову скаче");
  assert.deepEqual(after.clipped, [],
    "після накрутки вміст поля перестав влазити у висоту — рядок переноситься "
    + "всередині поля, і видно від нього половину");
  const moved = Object.keys(before.tops)
    .filter((p) => before.tops[p] !== after.tops[p])
    .map((p) => `${p}: ${before.tops[p]} → ${after.tops[p]}`);
  assert.deepEqual(moved, [],
    `накрутка зсунула сусідні поля:\n${moved.join("\n")}`);
  assert.equal(after.content, before.content,
    "висота вмісту панелі змінилась від накрутки — усе нижче зʼїхало");
});

/* ── ХОЛОДНИЙ СТАРТ: пакет із ДИСКА на ще не добудований макет ─────────────
 *
 * ⛔ ОХОРОНЦЕВІ ВИЩЕ (K–N) ЦЬОГО НЕ ВИДНО, і саме тому вада прожила до
 * 18.09.2026. Там правку роблять У ЦІЙ Ж сесії й лише потім перезавантажують
 * рамку: стан уже в памʼяті, а елемент уже несе всі класи, які йому дописав
 * власний скрипт макета. Двері, у які ходить дизайнер уранці, інші — пакет
 * читається з ДИСКА, а скрипти сторінки ще не відпрацювали, — і в ці двері не
 * ходив ніхто.
 *
 * Що зміряно живцем (`bf360`, it6/main, `h1.hero__title`):
 *     пакет каже:        margin-bottom: 0px → 28px
 *     інлайн на макеті:  padding-top і font-size Є, margin-bottom НЕМАЄ
 *     getComputedStyle:  marginBottom = 0px
 * Дві правки тієї ж сесії лежать, третя — піднята з диска — ні. Панель при
 * цьому показує всі три й позначає поле накрученим.
 *
 * Причина не в порядку читання (`loadTune().then(render)` чекає на файл, і
 * його докстрінг про це прямо каже), а в ЧАСІ: ключ елемента несе до двох
 * класів (`label`, `inspector-dom.js`), і клас елементу дописує ЙОГО ВЛАСНИЙ
 * скрипт — після `load`. У мить, коли `reapplyTune` робить свою єдину спробу,
 * селектор не збігається ні з чим, і `applyBySelector` мовчки пропускає.
 *
 * Фікстура відтворює рівно цю умову: скрипт сторінки дописує елементу два
 * класи ЧЕРЕЗ 250мс після `DOMContentLoaded`, а на диску вже лежить пакет,
 * ключ якого той клас містить.
 *
 * Мапа «перевірка → запобіжник → мутація»:
 *   P (холодна правка    — обмежені повтори в `reapplyTune` (`app.js`).
 *      доїхала)            МУТАЦІЯ: лишити одну спробу на `load` (прибрати
 *                          `setTimeout`-гілку) — макет показує СВОЄ значення,
 *                          перевірка червоніє. Це сама вада, слово в слово.
 *   Q (умову відтворено) — сам скрипт фікстури. Без свідка `__lateState`
 *                          перевірка зеленіла б і на сторінці, яка нічого не
 *                          дописує, тобто не стерегла б нічого.
 *   R (панель КАЖЕ про   — `tuneMissing` (`app.js`) + позначка в `tuneRow`
 *      те, що не лягло)    (`shell-inspect.js`). МУТАЦІЯ: прибрати позначку —
 *                          правка, якої на сторінці немає взагалі, малюється
 *                          так само впевнено, як накладена. Саме ця половина
 *                          закриває брехню НАЗАВЖДИ: хай хоч селектор
 *                          застарів, хай сторінку переписали — інструмент
 *                          більше не стверджує зміну, якої не видно.
 *   S (правка лишається  — свідома відмова прибирати те, що не лягло. Пакет
 *      в пакеті)           описує роботу дизайнера, а не стан чужої вкладки;
 *                          викинувши правку, ми зробили б із тихої брехні
 *                          тиху втрату — гірший обмін.
 *
 * Своя база порту, а не `PORT_BASE + 80`: смуга в сто портів від 10870
 * заходить на `ext-shell` (10890), а `node --test` крутить файли паралельно.
 */
const COLD_PORT_BASE = 11290;

/** Сторінка, яка дописує СОБІ класи вже після `load` — те, що роблять
 *  справжні макети (анімації входу, «split-ready»). Затримка навмисна й
 *  більша за будь-яку гонку обробників: одна спроба на `load` не має шансу
 *  побачити ці класи, а бюджет повторів (1с) — має. */
const PAGE_LATE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff}
.card{margin:0;padding:16px;background:#eef;width:260px;height:160px;color:#123456}
</style></head><body>
<div id="wrap" class="row">
  <p id="target" class="card">Картка ${id}</p>
</div>
<script>
document.addEventListener('DOMContentLoaded', function () {
  setTimeout(function () {
    window.__lateState = document.readyState;
    document.getElementById('target').classList.add('ready', 'in');
  }, 250);
});
</script>
</body></html>`;

/* Ключ елемента так, як його рахує модель: ланцюжок підписів предків, де
   підпис — тег плюс ДО ДВОХ класів (`label`, `inspector-dom.js`). Клас
   `ready` дописує скрипт сторінки, тож на холодному старті цей селектор
   спершу не знаходить нічого — у цьому вся вада. */
const LATE_SEL = "body > div.row > p.card.ready";
/* А цей не знайде нічого ніколи: сторінку переписали, елемент зник. Рівно та
   ситуація, у якій правку треба ЗБЕРЕГТИ в пакеті й СКАЗАТИ, що її не видно. */
const GHOST_SEL = "body > p.ghost";

const EDIT = (prop, from, to) => ({ prop, from, to, rule: ".card", raw: from,
  token: null, tokenValue: null, verdict: "hardcode", hint: [] });

/** Пакет на диску — той самий формат, який пише сам канвас (`packageJSON`). */
const COLD_PKG = {
  kind: "design-canvas.tuner.recommendations", version: 1, status: "draft",
  page: null, note: "холодний старт", editCount: 2, instructions: [],
  elements: [
    { page: "it1/holovna", selector: LATE_SEL, label: "p.card.ready",
      trail: ["body", "div.row", "p.card.ready"], text: "Картка holovna",
      edits: [EDIT("padding-top", "16px", "41px")] },
    { page: "it1/holovna", selector: GHOST_SEL, label: "p.ghost",
      trail: ["body", "p.ghost"], text: "",
      edits: [EDIT("margin-bottom", "0px", "28px")] },
  ],
};

/** Чи позначений рядок списку змін як «не лягло». `null` — такого рядка немає. */
const rowMiss = (page, prop) => page.evaluate((p) => {
  const x = document.querySelector(
    `#insp-panel [data-act="insptunedrop"][data-prop="${p}"]`);
  const row = x && x.closest(".insp-chg-row");
  if (!row) return null;
  const mark = row.querySelector(".insp-miss");
  return { attr: row.hasAttribute("data-miss"), title: mark ? mark.title : null };
}, prop);

test("холодний старт: правка з диска доїжджає на макет, що добудовується сам", async (t) => {
  const { dir } = taskFixture({ html: PAGE_LATE });
  /* ⛔ ПАКЕТ НА ДИСК — ДО того, як канвас узагалі піднявся. У цьому вся суть
     дверей: стану в памʼяті немає, він читається файлом. */
  writeFileSync(path.join(dir, ".dc-tuner.json"), JSON.stringify(COLD_PKG, null, 1));
  const { child, url } = await startServer(dir, { portBase: COLD_PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  /* P. Макет СПРАВДІ показує накручене. Питаємо браузер, а не наш інлайн:
     саме тут вада й видно — панель показувала правку, якої на екрані немає. */
  for (let i = 0; i < 60; i += 1) {
    if (await shown(page, "#target", "padding-top") === "41px") break;
    await page.waitForTimeout(50);
  }
  assert.equal(await shown(page, "#target", "padding-top"), "41px",
    "правка з ДИСКА не лягла на макет: одна спроба на `load` приходить раніше, "
    + "ніж скрипт сторінки дописує елементу класи, а панель усе одно малює її "
    + "як накладену");

  /* Q. Свідок того, що фікстура відтворила саме ту умову: клас зʼявився вже
     після того, як документ дозавантажився, тобто ПІСЛЯ обробника `load`, у
     якому працює перша спроба. Без цього рядка перевірка зеленіла б і на
     сторінці, яка нічого собі не дописує, — і не стерегла б нічого. */
  const lateState = await page.evaluate(() =>
    document.getElementById("frame").contentWindow.__lateState);
  assert.equal(lateState, "complete",
    "скрипт фікстури дописав клас ДО кінця завантаження — умова вади не "
    + "відтворена, перевірка міряє не ті двері");

  /* R. А про те, що не лягло, панель КАЖЕ. Правка з мертвим селектором лежить
     у тому ж пакеті й на тій же сторінці — і мусить виглядати ІНАКШЕ. */
  for (let i = 0; i < 60; i += 1) {
    if ((await rowMiss(page, "padding-top"))?.attr === false) break;
    await page.waitForTimeout(50);
  }
  const late = await rowMiss(page, "padding-top");
  const ghost = await rowMiss(page, "margin-bottom");
  assert.deepEqual([late?.attr, ghost?.attr], [false, true],
    "панель не розрізняє накладену правку й ту, якої на сторінці немає — "
    + "тобто стверджує зміну, якої дизайнер не бачить");
  assert.ok(ghost.title && ghost.title.length > 10,
    "позначка без пояснення читається як «правку загублено»");

  /* S. І ЖОДНА з двох не зникла з пакета: він описує роботу дизайнера, а не
     стан цієї вкладки. Читаємо тим самим каналом, яким його прочитає Клод. */
  const pkg = await page.evaluate(() => fetch("/api/tuner").then((r) => r.json()));
  const props = (pkg.package?.elements || []).flatMap((el) => el.edits)
    .map((e) => e.prop).sort();
  assert.deepEqual(props, ["margin-bottom", "padding-top"],
    "правку викинули з пакета — тиха брехня стала тихою втратою");
});

/**
 * Task 7 Плану B: ГЕОМЕТРИЧНІ охоронці оболонки. Усе, що було до цього
 * (Task 1–6, юніти `tests/bar-model.test.mjs`/`tests/shell-*.test.mjs`,
 * живі `tests/live/shell-bar.test.mjs`/`shell-panel.test.mjs`/
 * `shell-inspect.test.mjs`/`shell-palette.test.mjs`) стереже МОДЕЛЬ і
 * ПРОВОДКУ: який контрол ІСНУЄ, що він РОБИТЬ. Жоден із них не міряє
 * пікселі. А стара смуга мала фіксовану ширину 1462px, яка НЕ стискалась —
 * на 1440 зрізала 22px, на 1280 — 182, на 1024 — 438: кнопка публікації й
 * посилання на превью просто їхали за екран, і власного скролу смуга не
 * мала. Цей файл — єдине місце, що стереже РОЗМІР, а не СКЛАД.
 *
 * ⚠️ ДВІ пастки, знайдені ВИМІРОМ, а не читанням коду, ще ДО того, як
 * дійшло до восьми інваріантів нижче — обидві міняють, ЩО САМЕ й ЯК саме
 * тут перевіряється:
 *
 *   Пастка А (не той DOM-вузол). `index.html` містить `<div id="bar"
 *   class="bar">`, а `app.js` робить `bar.innerHTML = barHTML(...)`, і
 *   `barHTML()` (`shell-bar.js`) сама повертає `<div class="bar">…</div>` —
 *   тобто в бою `#bar` (клас `bar`) містить ВКЛАДЕНИЙ `<div class="bar">`
 *   (той самий клас!) із трьома `.zone` усередині. ОБИДВА мають
 *   `position:fixed;left:0;right:0` (`styles.css`, правило `.bar`). Це
 *   означає, що ВНУТРІШНІЙ `.bar` рахує СВОЮ ширину відносно viewport
 *   НАПРЯМУ, а не відносно батька — і його переповнення НІКОЛИ не потрапляє
 *   в `scrollWidth` зовнішнього `#bar`: position:fixed виймає елемент із
 *   потоку, і скролований overflow предка його не бачить. Виміряно: змусив
 *   внутрішній `.bar` вимагати 2197px на вікні 1024 — `#bar.scrollWidth`
 *   лишився 1024 (!), а `document.body.scrollWidth`/
 *   `document.documentElement.scrollWidth` — теж 1024. Перевірка на
 *   `document.getElementById('bar')` (найочевидніший вибір і те, як звичайно
 *   пишуть перевірку горизонтального переповнення — через `body`) була б
 *   ВАКУУМНО зеленою НАЗАВЖДИ, хоч би що зламалось усередині. Тому всюди
 *   нижче ціль — `#bar > .bar` (СПРАВЖНЯ смуга із трьома `.zone`), а не
 *   `#bar`.
 *
 *   Пастка Б (перевірка №1 у власному, буквальному формулюванні задачі —
 *   `bar.scrollWidth <= bar.clientWidth` — слабша, ніж здається, і НЕ
 *   ловить ІСТОРИЧНИЙ баг, заради якого весь цей файл існує). Виміряно:
 *   поставив `.bar{width:1462px}` (буквально стару фіксовану ширину) на
 *   вікні 1024 — `clientWidth` СТАЄ 1462 (бо `width` тепер явний, а не
 *   рахується з `left:0;right:0`), і `scrollWidth` теж 1462 (контент якраз
 *   влазить у свою ж явну ширину). `scrollWidth(1462) <= clientWidth(1462)`
 *   — ІСТИНА, перевірка зелена, а смуга рівно на 438px ширша за вікно
 *   (1024). Буквальне формулювання порівнює елемент САМ ІЗ СОБОЮ і сліпе до
 *   того, що сам елемент може бути ширшим за вікно. Тому інваріант 1 нижче
 *   — це `бар.scrollWidth <= window.innerWidth` (одна нерівність, що
 *   транзитивно покриває ОБИДВА способи зламатись: явну фіксовану ширину І
 *   переповнення контentом усередині відповідної ширини — доведено
 *   мутаційно нижче, розділ 1).
 *
 * Матриця: ширини 1024/1280/1360/1440 (рівно ті, що називає задача — 1024
 * менше порогу `TIERS.view=1060`, решта три над ним, 1280/1360 над
 * `TIERS.mode=1180`, під `TIERS.gl=1300`, а 1440 над усіма трьома порогами
 * `bar-model.js`), режими «Макет»/«Огляд», мови uk/en. Мова — ⌘K-палітра,
 * пункт «English» (`switchToEnglish` нижче): `setLang()` у `i18n.js` НЕ
 * винесений у `window` навмисно (докстрінг «Мова інтерфейсу» в `app.js`
 * прямо каже: `act:"lang"` належить застосунку, не смузі й не панелі), і
 * єдиний шлях перемкнути мову ЖИВИМ кодом — це палітра, той самий шлях, що
 * вже стереже `tests/live/shell-palette.test.mjs` (перевірка D). 16 комбінацій
 * — це не 16 завантажень сторінки: ширина й режим перемикаються НАЖИВО
 * (viewport/клік) на вже відкритій сторінці, мова — лише РАЗ на сторінку
 * (назад із en у uk шляху нема й не треба — свіжа сторінка стартує в uk),
 * тому кожен матричний тест відкриває РІВНО ДВІ сторінки (`forEachCombo`).
 *
 * Довга нотатка ітерації (`longNoteFixture`, замість короткої «фікстура» з
 * `fixture.mjs`) — НЕ косметика. З коротким текстом інваріант 2 (переповнення
 * зони) вакуумно зелений: короткий рядок ніколи не впреться в межу `max-width`
 * навіть якщо саму межу прибрати (перевірено — розділ 2 нижче). Крошка
 * ІТЕРАЦІЇ (не задачі: та навмисно коротка, jira/id, спека `bar-model.js`)
 * несе довільний текст дизайнера — довга нотатка тут відтворює РЕАЛЬНИЙ
 * розмір цього поля, а не вигаданий гірший випадок.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»,
 * знята мутаційно (зламав → почервоніло з точним повідомленням → повернув →
 * позеленіло — усі вісім, деталі й дослівні повідомлення в звіті задачі):
 *
 *   1 (смуга не ширша    — запобіжник: `.bar{display:grid;grid-template-
 *      за вікно)             columns:minmax(0,1fr) auto minmax(0,1fr)}`
 *                            (`styles.css`) РАЗОМ із контейнерними запитами,
 *                            що звужують зону 2 (`@container` блок нижче в
 *                            тому ж файлі) — саме ця пара тримає СЕРЕДНЮ
 *                            (`auto`) колонку в межах вікна на будь-якій
 *                            ширині матриці. Мутація: `.bar{width:1462px}`
 *                            (стара фіксована ширина, дослівно) — ЧЕРВОНІЄ на
 *                            всіх чотирьох ширинах, окрім 1462+ (тобто на
 *                            всіх у нашій матриці), повідомлення несе точні
 *                            числа (scrollWidth/innerWidth). Друга, незалежна
 *                            мутація: `.zone-2{min-width:2000px}` (контент
 *                            середньої колонки більший за все вікно) —
 *                            ЧЕРВОНІЄ так само, іншим шляхом (переповнення
 *                            контентом, не явна ширина) — обидва шляхи описані
 *                            в пастці Б вище.
 *   2 (жодна зона не      — запобіжник: `.ctl .txt{overflow:hidden;
 *      переповнює свою        text-overflow:ellipsis}` (`styles.css`) —
 *      колонку)               ДВА класи-селектори специфічністю (0,0,2,0),
 *                            і саме тому ВІН вирішальний для нотатки
 *                            ітерації (`<span class="txt txt--soft">`,
 *                            `crumbIter` у `shell-bar.js`), а НЕ сусіднє
 *                            правило `.txt--soft{overflow:hidden;text-
 *                            overflow:ellipsis}` (один клас, специфічність
 *                            (0,0,1,0)) — специфічність б'є порядок джерела,
 *                            тож нижче правило програє ВИЩОМУ незалежно від
 *                            того, яке з них стоїть у файлі пізніше. Мутація
 *                            «зняти обрізання лише з `.ctl .txt`» (замінити
 *                            на `overflow:visible;text-overflow:clip;white-
 *                            space:nowrap`, лишивши `.txt--soft` як є) —
 *                            ЧЕРВОНІЄ на `zone-1` (крошки), і РІВНО на ній:
 *                            `zone-2`/`zone-3` лишаються зеленими (там нема
 *                            довільного тексту дизайнера — див. вище).
 *                            ⚠️ Виміряно й ЗВОРОТНЄ, щоб не видати
 *                            специфічність за здогад: мутація «зняти
 *                            обрізання лише з `.txt--soft`, лишивши `.ctl
 *                            .txt` як є» — перевірка лишається ЗЕЛЕНОЮ.
 *                            власний `overflow:hidden` у `.txt--soft` на
 *                            практиці МЕРТВИЙ код для будь-якого `.txt`
 *                            усередині `.ctl` (тобто для всіх існуючих
 *                            викликів): рятує не він, а сусіднє, специфічніше
 *                            правило. Не здогад — обидва боки виміряні
 *                            нарізно.
 *   3 (головна дія        — запобіжник: ДВІ незалежні структурні гарантії
 *      придатна до            РАЗОМ: `icon: s.pubStale ? "warn" : "up"`
 *      натискання)            (БЕЗУМОВНО непорожній рядок, `bar-model.js`,
 *                            коментар просто над цим рядком називає
 *                            історичний баг — 20-піксельний обрубок без
 *                            іконки) І те, що `.lbl-pub` (підпис кнопки,
 *                            `shell-bar.js`) не обгорнутий у жоден клас, який
 *                            CSS ховає на вузькій смузі (на відміну від
 *                            `.lbl-mode`/`.lbl-gl` для інших контролів).
 *                            ⚠️ Виміряно чесно, а не про людське око: мутація
 *                            «зняти ЛИШЕ другу гарантію» (додати клас
 *                            `lbl-mode` підпису публікації в `zonePublish()`)
 *                            НЕ валить перевірку — на 1024 підпис ховається,
 *                            але кнопка стискається до іконки+падинги
 *                            (виміряно: 42×32), а `min(42,32)=32 ≥ 28`.
 *                            Перша гарантія (іконка завжди є) сама по собі
 *                            тримає поверх. Щоб дійсно відтворити історичний
 *                            баг («обрубок»), треба зняти ОБИДВІ разом:
 *                            додатково звузити `.split .split-main{padding:
 *                            0 13px}` до `padding:0 2px` (кнопка без
 *                            запасу на власний контент, а не лише без
 *                            підпису) — РАЗОМ із `lbl-mode` це ЧЕРВОНІЄ, і
 *                            виміряна коротка сторона — РІВНО 20px, той
 *                            самий «20-піксельний обрубок», яким названо
 *                            історичний баг у коментарі `bar-model.js`, хоч це й
 *                            збіг: сучасна кнопка складається з інших
 *                            частин, ніж прототипна. Записано чесно: ОДНІЄЇ
 *                            мутації недостатньо, це РЕАЛЬНИЙ (а не
 *                            вигаданий про людське око) захист у два шари.
 *   4 (перемикач режиму   — запобіжник: `tier: 0` для `id:"mode"` у
 *      видимий завжди)        `barModel()` (`bar-model.js`) РАЗОМ із тим, що
 *                            `seg()` (`shell-bar.js`) не додає жодного класу
 *                            типу `view-extra` контролам, крім `vp`/
 *                            `inspector`, — тобто сегмент режиму СТРУКТУРНО
 *                            не може потрапити під `@container
 *                            (max-width:1060px){.view-extra{display:none}}`.
 *                            Мутація: у `seg(model,"mode")` (виклик у
 *                            `zone2HTML`) додати той самий клас, що й у
 *                            `vp`/`inspector`, — `seg(model,"mode","
 *                            view-extra")` — на 1024 сегмент ховається
 *                            ЦІЛКОМ (і в «⋯» не зʼявляється: `ddMore()`
 *                            бере лише контроли з `tier===TIERS.view`, а
 *                            `mode` лишився з `tier:0`) — ЧЕРВОНІЄ.
 *   5 (view-extra XOR     — запобіжник: ПОРЯДОК правил у `styles.css` —
 *      view-more)             типове `.view-more{display:none}` СТОЇТЬ ПЕРЕД
 *                            `@container(max-width:1060px){.view-extra{
 *                            display:none} .view-more{display:inline-flex}}`
 *                            (коментар над обома прямо називає баг Плану A:
 *                            зворотний порядок при рівній специфічності
 *                            ховає ОБИДВА на 1024). Мутація: переставити
 *                            `.view-more{display:none}` ПІСЛЯ блоку
 *                            `@container` — ЧЕРВОНІЄ РІВНО на ширині 1024
 *                            (єдина ширина матриці під порогом 1060) в ОБОХ
 *                            режимах: `extra===more===false` — «керування
 *                            виглядом зникло ЗОВСІМ», той самий баг, що вже
 *                            стереже друга перевірка `shell-bar.test.mjs` —
 *                            тут те саме на повній матриці мов/режимів.
 *   6 (жодна ціль          — запобіжник: токени `--h-sm:28px`/`--h-ctl:32px`
 *      < 28px)                (`:root`, `styles.css`) — ними, а не літералом,
 *                            заданий розмір КОЖНОГО контролу смуги й панелі
 *                            (`.ctl`, `.icob`, `.row-caret`, `.row-more`,
 *                            `.seg--icons button`…). Мутація: `--h-sm:16px;
 *                            --h-ctl:18px` — ЧЕРВОНІЄ по всій матриці, у
 *                            смузі й у панелі одночасно (виміряно: 291
 *                            порушення на всіх 16 комбінаціях разом) — токен
 *                            один, і зламати
 *                            його означає зламати все відразу.
 *   7 (заморожені          — запобіжник: у ЦЬОМУ коді немає жодного
 *      анімації не          горизонтального transform на вхід/вихід —
 *      виїжджають за        `@keyframes dd{from{transform:translateY(-5px)}}`
 *      вікно)                (дропдауни) і `@keyframes pal{from{transform:
 *                            translateY(-10px) scale(.985)}}` (палітра/
 *                            довідка клавіш) рухають лише ПО ВЕРТИКАЛІ
 *                            (плюс легкий scale, симетричний відносно
 *                            центру `.pal`) — жоден не зсуває вміст ПО
 *                            ГОРИЗОНТАЛІ. Мутація: додати `translateX(40px)`
 *                            до `@keyframes dd` (той самий клас бага, що
 *                            ілюстрація в задачі — панель коментатора з
 *                            `translateX(24px)`, якої в ЦЬОМУ коді нема, але
 *                            клас бага той самий) — ЧЕРВОНІЄ на дропдауні
 *                            «Публікація» (`.dd--right`, заякорений біля
 *                            самого правого краю смуги, `padding:0 10px` —
 *                            10px запасу, 40px зсуву достатньо на будь-якій
 *                            ширині матриці) з точним `right > innerWidth`.
 *   8 (полотну ≥420px      — запобіжник: токени `--panel-w:246px`/
 *      з обома панелями       `--insp-w:308px` (`:root`) — `1024-246-308=
 *      на 1024)               470`, з запасом 50px, а не «рівно впритул».
 *                            Мутація: `--insp-w:600px` — `1024-246-600=178`
 *                            — ЧЕРВОНІЄ з точним числом.
 *
 * ⛔ Свідомо НЕ тестуємо в інваріанті 7: дропдауни «Задача»/«GitLab»/«⋯» —
 * та сама розмітка й ті самі класи (`.dd`/`.dd--right`), що вже покриті
 * дропдаунами «Ітерація» (ліво-заякорений `.dd`) і «Публікація» (право-
 * заякорений `.dd--right`, найближчий до краю); довідку клавіш (`?`) — той
 * самий клас `.pal`/анімація `pal`, що й ⌘K-палітра. Повторювати перевірку
 * тієї самої CSS-механіки на кожному з шести тригерів означало б платити
 * часом матриці (16 комбінацій) за нуль нового покриття.
 *
 * Три пастки, які вже коштували часу цього переносу (див. задачу) — і як
 * цей файл від них захищений:
 *   · `.trim()`: тут НЕМАЄ порівняння багаторядкового `textContent` з
 *     `/^…/` — усі перевірки числові (px) або булеві (offsetParent), де
 *     пробіл на початку рядка не впливає ні на що.
 *   · Фальшиво-зелений від очікування: усюди, де перевіряється НЕГАЙНИЙ
 *     ефект синхронної дії (перемикання режиму/мови/дропдауна), використано
 *     `waitFor(aria-pressed=true)`/`waitFor(state)` — очікування КОНКРЕТНОЇ
 *     ознаки готовності, а не голий `waitForTimeout`, який замаскував би
 *     забутий синхронний виклик затримкою.
 *   · Порожня множина: кожен матричний тест несе незалежного свідка —
 *     `zones.length===3` (2), `vis.length===2` (4), `totalChecked>200` (6) —
 *     без нього перевірка була б зеленою й на порожній розмітці.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { runShoot } from "../../bin/shoot.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база порту: сусідні живі набори — canvas=8890, viewport=9090,
   autoshoot=9190, overview-viewports=9290, shell-bar=9390, shell-panel=9490,
   shell-inspect=9590, shell-palette=9690(+40). Наступна вільна смуга — 9790;
   вісім тестів у ЦЬОМУ файлі йдуть послідовно (`node --test` виконує тести
   ОДНОГО файлу по черзі, паралельно лише РІЗНІ файли), тож +10 між ними —
   той самий запас, що вже безпечно працює в shell-palette.test.mjs. */
const PORT_BASE = 9790;

const WIDTHS = [1024, 1280, 1360, 1440];
const MODES = ["layout", "overview"];
const CLICK_SEL = "button, a[href], input, [data-act], [data-dd]";

/* Градієнт, а не порожня сторінка: порожній знімок стискається у WebP нижче
   `BYTES_FLOOR` і дістає `problem: "порожня сторінка"`, і клік по
   `mode[overview]` замовляв би СПРАВЖНЮ автозʼємку замість побаченого вже
   свіжого стану — той самий прийом, що в `shell-bar.test.mjs`/
   `autoshoot.test.mjs`. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:1200px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${id}</h1></body></html>`;

/**
 * Фікстура з ДОВГОЮ нотаткою ітерації — навіщо, див. шапку файлу. Дописуємо
 * `iterations.json` ПІСЛЯ `taskFixture()`, той самий прийом, що
 * `canvas.test.mjs`/`shoot.test.mjs` (перезаписати щойно створений файл
 * фікстури своїм вмістом, а не тягнути ще один параметр у спільний
 * `taskFixture`, якому ця конкретна форма тексту потрібна лише тут).
 */
function longNoteFixture() {
  const { dir, it1 } = taskFixture({ html: PAGE });
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{
      id: "it1", date: "24.08.2026 12:00", published: true,
      note: "оновлений пошук, фільтри карток і мобільний брейкпоінт кошика",
    }],
  }));
  return { dir, it1 };
}

/** Нова сторінка, застосунок завантажений, смуга вже намальована. */
async function openApp(browser, url) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.locator('#bar [data-act="mode"]').first().waitFor();
  return page;
}

/** Перемкнути режим смуги, якщо він ще не такий; чекати підсвітки, а не
 *  таймауту — `mode` асинхронна (`await freshen()`), тож голий `waitForTimeout`
 *  або замаскував би зависання, або довільно занизив/завищив запас часу. */
async function setMode(page, val) {
  const sel = `#bar [data-act="mode"][data-val="${val}"]`;
  if ((await page.locator(sel).getAttribute("aria-pressed")) === "true") return;
  await page.click(sel);
  await page.locator(`${sel}[aria-pressed="true"]`).waitFor({ timeout: 10000 });
}

/** Перемкнути мову інтерфейсу на англійську — ⌘K-палітра, той самий шлях,
 *  що доводить перевірка D `shell-palette.test.mjs`. Лише УПЕРЕД (uk→en):
 *  свіжа сторінка стартує в uk, і шляху назад цей файл не потребує. */
async function switchToEnglish(page) {
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "english");
  await page.waitForFunction(
    () => document.querySelectorAll(".pal-it").length === 1,
    null, { timeout: 2000 },
  );
  await page.keyboard.press("Enter");
  await page.locator(".pal").waitFor({ state: "detached" });
}

/**
 * Подвійний `requestAnimationFrame` — чекати ПОВНИЙ цикл layout+paint після
 * `setViewportSize`, а не голий таймаут. Знайдено МУТАЦІЙНО (не здогад):
 * без цього рядка `[data-act="publish"]` інколи (виміряно 2/8, потім 0/24 із
 * цим рядком) читає `offsetParent:null,width:0,height:0` РІВНО на першому
 * вимірі одразу після зміни розміру вікна — Chromium CDP `setViewportSize`
 * повертає керування ДО того, як рушій завершив relayout під нову ширину
 * контейнера (`container-type:inline-size` на `.bar` — сама смуга, а не
 * лише вікно, перераховує пороги `@container`), і синхронний
 * `getBoundingClientRect()` встигає впіймати проміжний кадр. Це НЕ той
 * фальшиво-зелений «очікування», від якого застерігає задача: там ризик —
 * замаскувати ЗАБУТИЙ синхронний виклик довільним таймаутом; тут очікування
 * ПОДІЄВЕ (два кадри рендера, не мілісекунди) і не ховає жодної затримки
 * НАШОГО коду — розмір вікна й так синхронний, чекаємо лише на те, поки
 * БРАУЗЕР домалює те, що вже вирішив.
 */
async function settle(page) {
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
}

/**
 * Матриця «мова × режим × ширина» — 2×2×4=16 комбінацій на ДВОХ сторінках
 * (по одній на мову), не шістнадцяти: ширина й режим перемикаються НАЖИВО
 * на вже відкритій сторінці (`setViewportSize`/клік), лише мова вимагає
 * свіжого старту. `fn` кличеться на кожній із 16 комбінацій із
 * `{page, lang, mode, width}`.
 */
async function forEachCombo(browser, url, fn) {
  for (const lang of ["uk", "en"]) {
    const page = await openApp(browser, url);
    if (lang === "en") await switchToEnglish(page);
    for (const mode of MODES) {
      await setMode(page, mode);
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        await fn({ page, lang, mode, width });
      }
    }
    await page.close();
  }
}

/** Кожен матричний тест платить за один прогін `runShoot` — інакше перший
 *  вхід у «Огляд» у циклі бачить застаріле й замовляє СПРАВЖНЮ автозʼємку
 *  (окремий Chromium+node на кожному з 8 переходів «Огляду» в матриці) —
 *  той самий прийом, що `shell-bar.test.mjs`. */
async function preShoot(url, it1) {
  await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });
}

/**
 * Усі ВИДИМІ клікабельні цілі під заданими корінними селекторами.
 * `offsetParent !== null` — та сама ознака «видимо й у розмітці», що вже
 * використовує `shell-bar.test.mjs`. Дедуплікація потрібна, бо `#bar` і
 * `#pages-panel` не перетинаються, але виклик з кількома коренями інакше
 * б рахував той самий елемент двічі, якби корені колись почали вкладатись.
 */
async function clickTargets(page, roots) {
  return page.evaluate(({ roots: rootSels, sel }) => {
    const seen = new Set();
    const out = [];
    for (const rootSel of rootSels) {
      const root = document.querySelector(rootSel);
      if (!root) continue;
      for (const el of root.querySelectorAll(sel)) {
        if (seen.has(el) || el.offsetParent === null) continue;
        seen.add(el);
        const r = el.getBoundingClientRect();
        out.push({
          act: el.dataset.act || null, dd: el.dataset.dd || null,
          tag: el.tagName, cls: el.className,
          w: r.width, h: r.height, left: r.left, right: r.right,
        });
      }
    }
    return out;
  }, { roots, sel: CLICK_SEL });
}

/**
 * Заморозити анімації на `t=0` (`currentTime=0; pause()` — точний прийом
 * задачі) і повернути ЦІЛІ, чия рамка вилазить за межі вікна. В ОДНОМУ
 * `page.evaluate`, а не двома викликами: заморозка й вимір мусять статись
 * без жодного такту рендера між ними, інакше заморожений кадр міг би встигнути
 * зрушити ще раз (rAF/наступний тік) до того, як ми прочитали рамку.
 */
async function boundsViolations(page) {
  return page.evaluate((sel) => {
    document.getAnimations().forEach((a) => { a.currentTime = 0; a.pause(); });
    const w = window.innerWidth;
    return [...document.querySelectorAll(sel)]
      .filter((e) => e.offsetParent !== null)
      .map((e) => ({ e, r: e.getBoundingClientRect() }))
      .filter(({ r }) => r.right > w + 0.5 || r.left < -0.5)
      .map(({ e, r }) => ({
        act: e.dataset.act || null, dd: e.dataset.dd || null, cls: e.className,
        left: r.left, right: r.right, innerWidth: w,
      }));
  }, CLICK_SEL);
}

test("0. смуга помилки видима, а не позаду смуги", async (t) => {
  /* Стан «`tasks.json` не читається» — єдиний, у якому інструмент КАЖЕ, що
     він зламаний. Смуга помилки для нього зʼявилась разом із оболонкою v2
     (`d1e9861`) і не працювала НІ РАЗУ: `barHTML()` віддає `.errbar` сусідом
     `.bar` усередині `#bar`, а `#bar` — це `position:fixed` стрічка рівно
     `--h-bar` = 46px. `.bar` у ній теж `position:fixed` і з `z-index`, тобто
     позиційований елемент; `.errbar` статичний і малюється ШАРОМ НИЖЧЕ. Око
     цього не бачить нізащо: щоб побачити, треба зламати `/api/tasks`.

     Тому перевірка міряє не «елемент у DOM» і не `isVisible()` — обидва були
     б зелені на зламаному стані. Вона питає браузер, що САМЕ лежить у точці
     центру смуги помилки: якщо там `.bar`, повідомлення накрите. */
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 90 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  // Ламаємо саме `/api/tasks`: `tasksErr` виставляється рівно на його відмову.
  await page.route("**/api/tasks*", (route) => route.abort());
  await page.goto(`${url}/app/`);

  const bar = page.locator("#bar .errbar");
  await bar.waitFor({ state: "visible", timeout: 10000 });

  const probe = await page.evaluate(() => {
    const e = document.querySelector("#bar .errbar");
    const r = e.getBoundingClientRect();
    const x = Math.round(r.x + r.width / 2);
    const y = Math.round(r.y + r.height / 2);
    const at = document.elementFromPoint(x, y);
    return {
      rect: { y: Math.round(r.y), h: Math.round(r.height) },
      hitsErrbar: !!(at && at.closest(".errbar")),
      hitTag: at ? `${at.tagName}.${at.className}` : null,
      retryVisible: !!document.querySelector('#bar .errbar [data-act="retry"]')?.offsetParent,
      /* Альфа тла. Смуга тепер лежить ПОВЕРХ сцени, а там макет клієнта —
         часто білий. Напівпрозоре тло дало б повідомлення про поломку, якого
         не прочитати; наявність елемента й `isVisible()` цього не бачать. */
      bgAlpha: (() => {
        const c = getComputedStyle(e).backgroundColor;
        const m = /^rgba?\(([^)]+)\)$/.exec(c);
        if (!m) return null;
        const parts = m[1].split(",").map((x) => parseFloat(x));
        return parts.length < 4 ? 1 : parts[3];
      })(),
    };
  });

  assert.ok(probe.hitsErrbar,
    `смуга помилки накрита: у точці її центру лежить ${probe.hitTag}`);
  assert.ok(probe.rect.y >= 46,
    `смуга помилки на y=${probe.rect.y} — вона мусить бути ПІД смугою (46px), не в ній`);
  assert.ok(probe.retryVisible, "кнопки «Спробувати ще» не видно");
  assert.equal(probe.bgAlpha, 1,
    `тло смуги помилки напівпрозоре (alpha=${probe.bgAlpha}) — поверх макета клієнта текст стане нечитним`);
});

test("1. смуга (#bar > .bar) не ширша за вікно на жодній ширині/режимі/мові", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const info = await page.evaluate(() => {
      const bar = document.querySelector("#bar > .bar");
      return { scrollWidth: bar.scrollWidth, innerWidth: window.innerWidth };
    });
    // Одна нерівність замість `scrollWidth<=clientWidth` — див. пастку Б
    // у шапці файлу: буквальне формулювання не ловить фіксовану ширину.
    if (info.scrollWidth > info.innerWidth) bad.push({ lang, mode, width, ...info });
  });

  assert.deepEqual(bad, [], `смуга ширша за вікно на комбінаціях: ${JSON.stringify(bad)}`);
});

test("2. жодна зона (#bar .zone) не переповнює свою колонку", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 10 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const zones = await page.$$eval("#bar .zone", (els) => els.map((e) => ({
      cls: e.className, scrollWidth: e.scrollWidth, clientWidth: e.clientWidth,
    })));
    // Незалежний свідок: без нього перевірка була б зеленою й на розмітці
    // без жодної зони.
    assert.equal(zones.length, 3, `очікував 3 зони .zone, отримав ${zones.length}`);
    for (const z of zones) {
      if (z.scrollWidth > z.clientWidth) bad.push({ lang, mode, width, ...z });
    }
  });

  assert.deepEqual(bad, [], `зона переповнює свою колонку: ${JSON.stringify(bad)}`);
});

test('3. головна дія [data-act="publish"] видима і придатна до натискання (≥28px)', async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 20 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const info = await page.$eval('[data-act="publish"]', (e) => {
      const r = e.getBoundingClientRect();
      return { visible: e.offsetParent !== null, w: r.width, h: r.height };
    });
    if (!info.visible || Math.min(info.w, info.h) < 28 - 0.5) {
      bad.push({ lang, mode, width, ...info });
    }
  });

  assert.deepEqual(bad, [], `публікація недосяжна/замала: ${JSON.stringify(bad)}`);
});

test("4. перемикач режиму видимий на всіх ширинах", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 30 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const vis = await page.$$eval(
      '#bar [data-act="mode"]', (els) => els.map((e) => e.offsetParent !== null),
    );
    assert.equal(vis.length, 2, `очікував 2 кнопки режиму, отримав ${vis.length}`);
    if (!vis.every(Boolean)) bad.push({ lang, mode, width, vis });
  });

  assert.deepEqual(bad, [], `перемикач режиму зник: ${JSON.stringify(bad)}`);
});

test("5. керування виглядом: рівно один із двох (.view-extra / .view-more), ніколи ні той ні той і ніколи обидва", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const { extra, more } = await page.evaluate(() => ({
      extra: [...document.querySelectorAll("#bar .view-extra")].some((e) => e.offsetParent !== null),
      more: (() => {
        const m = document.querySelector("#bar .view-more");
        return !!m && m.offsetParent !== null;
      })(),
    }));
    // extra===more ловить ОБИДВА хибні стани: (true,true) і (false,false).
    if (extra === more) bad.push({ lang, mode, width, extra, more });
  });

  assert.deepEqual(bad, [], `керування виглядом і в смузі, і в «⋯», або ніде: ${JSON.stringify(bad)}`);
});

test("6. жодна клікабельна ціль у смузі й панелі не менша за 28px по короткій стороні", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 50 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];
  let totalChecked = 0;
  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    const targets = await clickTargets(page, ["#bar", "#pages-panel", "#insp-panel"]);
    totalChecked += targets.length;
    for (const tt of targets) {
      if (Math.min(tt.w, tt.h) < 28 - 0.5) bad.push({ lang, mode, width, ...tt });
    }
  });

  // Незалежний свідок: без нього перевірка була б зеленою й на порожній
  // смузі (цикл просто не мав би що міряти).
  assert.ok(totalChecked > 200, `перевірено лише ${totalChecked} цілей на всій матриці — це не повний прогін`);
  assert.deepEqual(bad, [], `замалі клікабельні цілі: ${JSON.stringify(bad)}`);
});

test("7. із замороженими на t=0 анімаціями жоден контрол не виходить за межі вікна", async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  await preShoot(url, it1);
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const bad = [];

  /** Відкрити дропдаун-тригер, заморозити й зняти порушення, закрити Escape. */
  async function checkDropdown(page, triggerSel, meta) {
    await page.click(triggerSel);
    await page.locator(".dd").first().waitFor({ timeout: 3000 });
    for (const v of await boundsViolations(page)) bad.push({ ...meta, ...v });
    await page.keyboard.press("Escape");
    await page.locator(".dd").waitFor({ state: "detached", timeout: 3000 });
  }

  await forEachCombo(browser, url, async ({ page, lang, mode, width }) => {
    // `.dd` ЛІВО-заякорений (крошка ітерації) — представник анімації `dd`
    // з боку, ближчого до лівого краю.
    await checkDropdown(page, '#bar [data-dd="iter"]', { lang, mode, width, which: "iter" });
    // `.dd--right` ПРАВО-заякорений (дропдаун публікації) — той самий клас
    // анімації, найближчий до ПРАВОГО краю вікна: найризикованіший бік.
    await checkDropdown(page, '#bar [data-dd="pub"]', { lang, mode, width, which: "pub" });
    // ⌘K-палітра: ІНША анімація (`pal`: translateY + scale), центрована.
    await page.keyboard.press("Control+k");
    await page.locator("#palq").waitFor({ state: "visible", timeout: 3000 });
    for (const v of await boundsViolations(page)) bad.push({ lang, mode, width, which: "palette", ...v });
    await page.keyboard.press("Escape");
    await page.locator(".pal").waitFor({ state: "detached", timeout: 3000 });
  });

  assert.deepEqual(bad, [], `контрол вилазить за вікно при замороженій анімації: ${JSON.stringify(bad)}`);
});

test('8. з обома панелями на 1024 у «Макеті» лишається ≥420px полотна', async (t) => {
  const { dir, it1 } = longNoteFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 70 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  void it1; // «Макет» не читає кадрів — preShoot тут не потрібен

  for (const lang of ["uk", "en"]) {
    const page = await openApp(browser, url);
    if (lang === "en") await switchToEnglish(page);
    await page.setViewportSize({ width: 1024, height: 900 });
    await settle(page);

    // Інспектор живе всередині iframe макета — чекаємо його готовності
    // (`inspectorApi()` у app.js), інакше клік влучив би в момент, коли
    // макет ще вантажиться.
    await page.waitForFunction(() => {
      const f = document.getElementById("frame");
      return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
    }, null, { timeout: 15000 });

    // На 1024 (≤1060) інспектор живе в «⋯»: та сама причина, що в
    // `shell-bar.test.mjs` («керування виглядом переїжджає в «⋯»…»).
    await page.click('#bar [data-dd="more"]');
    await page.locator(".dd").waitFor({ timeout: 3000 });
    await page.click('.dd [data-act="inspector"]');
    await page.locator("#insp-panel .insp-top").waitFor({ timeout: 5000 });

    const info = await page.evaluate(() => {
      const r = document.getElementById("stage").getBoundingClientRect();
      return {
        width: r.width,
        withPanel: document.body.classList.contains("with-panel"),
        panelCollapsed: document.body.classList.contains("panel-collapsed"),
        withInsp: document.body.classList.contains("with-insp"),
      };
    });
    assert.ok(
      info.withPanel && !info.panelCollapsed && info.withInsp,
      `${lang}: перевірка недійсна — панелі не в очікуваному стані (${JSON.stringify(info)})`,
    );
    assert.ok(info.width >= 420, `${lang}: полотну лишилось лише ${info.width}px на 1024 з обома панелями`);
    await page.close();
  }
});

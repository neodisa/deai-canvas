/**
 * Живий охоронець проводки смуги: КОЖЕН контрол `[data-act]`/`[data-dd]`,
 * видимий у ЗАКРИТОМУ стані смуги, мусить РОБИТИ ХОЧ ЩОСЬ на клік — інакше
 * рядок делегації (`BAR_ACTIONS[act]`, `app/app.js`) забутий, і кнопка
 * мовчки ніщо не робить. Це саме те, чого не бачить жоден юніт:
 * `tests/shell-bar.test.mjs` перевіряє лише, що РОЗМІТКА несе правильний
 * `data-act`/`data-dd` — не що на нього щось РЕАГУЄ. Делегація ловить його
 * так: `BAR_ACTIONS[act]?.(...)` — знак питання МОВЧКИ ковтає відсутність
 * ключа, тобто забутий рядок не впаде і не залогує нічого, лише кнопка
 * тихо перестане працювати.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   (0.25.0) крошки-перемикача задач у смузі більше нема — лише назва задачі;
 *   логотип, вкладки й «назад» переїхали в `#tabs`, інспектор і «Відгук» — в
 *   острівець `#hud`. Цикл нижче обходить `#bar` ТА `#hud`.
 *   iter (крошка ітерації) — та сама гілка `data-dd`, інший тригер.
 *   mode[overview]         — рядок `mode:` у `BAR_ACTIONS`. Прибери його —
 *                            `BAR_ACTIONS.mode` стане `undefined`, делегація
 *                            мовчки нічого не зробить: падає на «mode[overview]».
 *                            `mode[layout]` НЕ тестуємо: на старті смуга вже в
 *                            «Макеті», а обробник `mode` сам виходить раніше
 *                            на «той самий вигляд» (`if (wantCanvas ===
 *                            (mode === 'canvas')) return;`, app.js) — клік по
 *                            вже активному сегменту є СВІДОМИЙ ноп, а не бага;
 *                            тестувати його — чекати зміни там, де код сам
 *                            обіцяє її не робити.
 *   vp[tablet], vp[mobile] — рядок `vp:` у `BAR_ACTIONS` → `setViewport`.
 *                            `vp[desktop]` НЕ тестуємо тим самим міркуванням:
 *                            порожній `localStorage` дає `vpWidth = null`, а
 *                            `activePreset(null) === 'desktop'` (`viewport.js`)
 *                            — це вже активний пресет на старті, і клік по
 *                            ньому не міняє жодного атрибута розмітки.
 *   inspector              — рядок `inspector:`. Це ЄДИНИЙ сегментоподібний
 *                            контрол БЕЗ гілки «уже такий»: `api.set(!api.on)`
 *                            перемикає завжди. Але сам виклик спирається на
 *                            `inspectorApi()` — `frame.contentWindow
 *                            .CanvasInspector`, який інжектить `serve.py` в
 *                            документ макета, — тож перевірка чекає готовності
 *                            ЦЬОГО, інакше впаде на гонці тесту, а не на бага.
 *   more (⋯ Вигляд)        — `data-dd="more"`. ⛔ Ця кнопка сама була
 *                            НЕДОСЯЖНА на типовій ширині вікна до фікса в
 *                            `shell-bar.js`: `.view-more{display:none}`
 *                            (`styles.css`) ховає її на будь-якій ширині
 *                            смуги, ширшій за 1060px, а перемикач аудиторії
 *                            коментарів живе ВИКЛЮЧНО тут (`ddMore()`). Клас
 *                            `view-more--pin` (доданий разом із цим файлом,
 *                            див. звіт) пришпилює кнопку видимою, поки є
 *                            ітерація. Без нього цей рядок падає не «нічого
 *                            не зробив», а таймаутом Playwright «element is
 *                            not visible» — так само, як падали K2 і AB у
 *                            `tests/live/canvas.test.mjs` до фікса.
 *   gl                     — `data-dd="gl"`; дропдаун непорожній навіть при
 *                            вимкненому GitLab (пункт «Налаштувати»).
 *   pub (▾ біля публікації)— `data-dd="pub"`, дропдаун меню публікації.
 *   home (логотип у `#tabs`) — окремий блок ПІСЛЯ циклу. Рядок `home:` у `BAR_ACTIONS`. Прибери його —
 *                            `BAR_ACTIONS.home` стане `undefined`, делегація
 *                            мовчки нічого не зробить, а смуга лишиться тією
 *                            самою: падає на «home». Ефект кліку — склад
 *                            смуги (крошка «Задачі» замість задачі й
 *                            макета), тож його видно в `#bar.innerHTML`.
 *   back («Назад до …»)    — рядок `back:`. Його НЕМАЄ у закритій смузі (він
 *                            зʼявляється лише на екрані «Задачі»), тож цикл
 *                            його не бачить, і перевіряє його окремий блок
 *                            ПІСЛЯ циклу: без рядка `back:` смуга лишилась би
 *                            назавжди в стані «Задачі» — вихід із екрана без
 *                            виходу.
 *
 * ⛔ Свідомо НЕ тестуємо (і чому — мовчазний пропуск гірший за пояснений):
 *   publish (сама кнопка «Опублікувати») — DANGEROUS: `BAR_ACTIONS.publish`
 *     справді кличе `POST /api/publish` і розгортає задачу. Контрол не
 *     підозрюваний у бага (його тіло й так живе під live-набором Task 3) —
 *     причина пропуску суто в ціні: клікати його в кожному прогоні означало
 *     б деплоїти фікстуру щоразу.
 *   vpw (поле своєї ширини) — це `<input>`, не кнопка. `BAR_ACTIONS` про
 *     `"vpw"` не знає ЗОВСІМ: контрол живе на `focusout`/Enter-`keydown`
 *     окремою делегацією (`app.js`, біля `settleViewportInput`), а клік по
 *     інпуту — це просто фокус, подія, на яку ніхто не підписаний. Тестувати
 *     його як кнопку означало б завжди падати НЕ через бага. Його дротову
 *     справність стереже `tests/live/viewport.test.mjs`.
 *
 * `acts.length >= 6` — незалежний свідок: без нього перевірка була б зелена
 * і на порожній смузі (цикл просто не мав би по чому йти).
 *
 * Порядок циклу НАВМИСНО не збігається з порядком DOM. У природному порядку
 * розмітки `mode[overview]` стоїть ОДРАЗУ після `mode`, тобто РАНІШЕ за
 * `vp`/`inspector`/`more` — а клік по ньому перемальовує смугу під «Огляд»,
 * де `inspector` (макет-лише) і `vpw` (з тієї ж причини) зникають із DOM
 * ЗОВСІМ. Перевірка впала б на них НЕ через бага, а тому, що самі елементи
 * вже поїхали з дерева — тому `mode` відкладено на кінець циклу, коли решта
 * вже перевірена. `home` — ще ПІСЛЯ нього: клік по логотипу перемальовує
 * смугу на екран «Задачі», де немає жодного контрола макета, і решта впала б
 * на зниклих елементах, а не на бага.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { runShoot } from "../../bin/shoot.mjs";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { startServer, taskFixture } from "./fixture.mjs";

/* Свій `portBase`: `node --test` крутить файли паралельно, і спільна база з
   іншими живими наборами (canvas=8890, viewport=9090, autoshoot=9190,
   overview-viewports=9290) дала б колізію портів. */
const PORT_BASE = 9390;
const VIEW = { width: 1400, height: 900 };

/* Градієнт, а не порожня сторінка: порожній знімок стискається у WebP нижче
   `BYTES_FLOOR` і дістає `problem: "порожня сторінка"` — тоді фікстура
   ЛИШАЄТЬСЯ застарілою навіть після `runShoot` нижче, і клік по
   `mode[overview]` замовляє СПРАВЖНЮ автозʼємку замість того, щоб побачити
   вже свіжу. Той самий прийом, що в `tests/live/canvas.test.mjs`/
   `autoshoot.test.mjs`. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:1200px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${id}</h1></body></html>`;

/* Дії, чий клік СВІДОМО не тестуємо на «щось змінилось» — див. шапку файлу
   для причини кожної. Ключ тут — `data-act`/`data-dd`, тобто ІМʼЯ дії, а не
   конкретний елемент: для сегментів (mode/vp) «активний зараз» відсіюється
   окремо, нижче, по `aria-pressed`. */
const DANGEROUS = new Set(["publish", "figma"]);
/* `figma` («В Figma», T-41) — не небезпечна, але її наслідок АСИНХРОННИЙ: тост
   живе поза `#bar`, а невдача (у цьому контексті буфер заборонений) приходить
   оверлеєм `tell()` за 1–2 с — уже поверх НАСТУПНОГО контрола циклу, і той
   падав би таймаутом кліку не через свою бага. Проводку цієї кнопки кліком
   стереже власний набір `tests/live/figma.test.mjs`: він тисне її і читає
   справжній буфер. Мовчазний пропуск гірший за пояснений — тому він тут. */

test("кожен контрол смуги щось робить на клік", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  /* Знімаємо фікстуру ЗАЗДАЛЕГІДЬ: без цього клік по `mode[overview]` бачить
     застаріле й замовляє СПРАВЖНЮ автозʼємку (окремий Chromium+node) — ця
     перевірка не про зʼємку, і платити за неї часом не варто. */
  await runShoot({ dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
                   launch: () => chromium.launch() });

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  /* Відповідь статусу синку чекаємо ДО `goto` (після нього вона вже могла прийти): смуга перемальовується двічі — після `render()`
     й після цієї відповіді (`refreshGitlab` → `paintBar`), тож порівняння `before`/`after` у циклі нижче могло б зарахувати контролу
     пізню перемальовку від відповіді — і не помітити контрол, що не зробив нічого. Чекаємо її (і два кадри після) до циклу. Умовно: зона синку (`data-dd="gl"`) є лише в просторі з роллю `vcs`, а без неї статус не питається — чекання зависло б. */
  const status = page.waitForResponse((r) => /\/api\/(vcs|gitlab)-status/.test(r.url()));
  status.catch(() => {});                                    // ранній вихід не лишає відхиленого обіцяного без обробника
  await page.goto(`${url}/app/`);

  /* Готовність макета для `inspector`: інспектор живе в
     `frame.contentWindow.CanvasInspector`, якого інжектить `serve.py` в
     документ макета. Без цього чекання клік по інспектору міг би влучити в
     момент, коли `inspectorApi()` ще повертає `null` («макет ще вантажиться»,
     сам `app.js`) — гонка тесту, а не бага смуги. */
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });

  /* Повний цикл малювання ПІСЛЯ відповіді статусу (два кадри): далі смуга стоїть, і `before`/`after` міряють лише клік. */
  if (await page.evaluate(() => !!document.querySelector('#bar [data-dd="gl"]'))) await status;
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

  /* Тільки ВИДИМІ контроли. «⋯» на широкій смузі схований контейнерним
     запитом (`.view-more{display:none}` понад 1060px) — це правильна
     поведінка, а не поломка: там його вміст стоїть у смузі окремо. Клік по
     схованому вузлу дав би таймаут і виглядав би як бага смуги. Окремий тест
     нижче перевіряє протилежний бік: на 1024 «⋯» ЗʼЯВЛЯЄТЬСЯ, а `view-extra`
     зникає — тобто керування виглядом досяжне на обох ширинах. */
  /* ОДИН `evaluate`, а не `$$eval`: `$$eval` спершу бере вузли, а вже потім кличе функцію над ними, і смуга, перемальована між
     цими двома кроками (`paintBar` після відповіді `/api/vcs-status`; від 4a перша відповідь свіжого сервера — ≈24 мс замість ≈2,
     виміряно, — тож вона вклинюється частіше), лишала б функції ВІДЧЕПЛЕНІ вузли: `offsetParent === null` у всіх, «0 контролів». `evaluate` вибирає й
     фільтрує в одному завданні сторінки — перемальовка вклинитись не може. */
  const controls = await page.evaluate(() =>
    [...document.querySelectorAll("#bar [data-act],#bar [data-dd],#hud [data-act]")].filter((e) => e.offsetParent !== null).map((e) => ({
      root: e.closest("#hud") ? "#hud" : "#bar",
      act: e.dataset.act || null,
      dd: e.dataset.dd || null,
      val: e.dataset.val || null,
      pressed: e.getAttribute("aria-pressed"),
      tag: e.tagName,
    })));
  assert.ok(controls.length >= 6,
    `у смузі лише ${controls.length} контролів — розмітка не та`);
  assert.ok(controls.some((c) => c.act === "mode"), "немає сегмента «як дивлюсь»");
  /* 0.25.0: крошки-перемикача задач у смузі нема — лише назва задачі (текст), а керування
     острівцем (інспектор, «Відгук») живе в `#hud`, не в `#bar`. */
  assert.ok(await page.locator("#bar .crumb--title").count() > 0, "немає назви задачі в смузі");
  assert.equal(controls.some((c) => c.dd === "task"), false, "перемикач задач повернувся в смугу");
  assert.ok(controls.some((c) => c.root === "#hud" && c.act === "feedback"), "у острівці немає «Відгук»");
  assert.ok(controls.some((c) => c.root === "#hud" && c.act === "inspector"), "у острівці немає інспектора");

  // `mode` — останнім у циклі, і саме тому окремим проходом: див. шапку файлу.
  const ordered = [
    ...controls.filter((c) => c.act !== "mode"),
    ...controls.filter((c) => c.act === "mode"),
  ];

  for (const c of ordered) {
    const key = c.act || c.dd;
    if (DANGEROUS.has(key)) continue;
    if (c.tag === "INPUT") continue;      // vpw — інша делегація, див. шапку
    if (c.pressed === "true") continue;   // уже активний сегмент — свідомий ноп

    const sel = c.val
      ? `${c.root} [data-act="${key}"][data-val="${c.val}"]`
      : (c.act ? `${c.root} [data-act="${key}"]` : `${c.root} [data-dd="${key}"]`);
    const name = c.val ? `${key}[${c.val}]` : key;

    const snap = () => page.evaluate(() => document.getElementById("bar").innerHTML + document.getElementById("hud").innerHTML);
    const before = await snap();
    await page.click(sel);
    await page.waitForTimeout(150);
    const after = await snap();
    /* Контрол смуги може подіяти ТРЬОМА способами, і всі три однаково
       законні: перемалювати смугу, відкрити дропдаун, або відкрити оверлей на
       весь екран. Третій зʼявився 02.09.2026 разом із дверима в палітру — і
       перевірка, прибита до перших двох, оголосила робочий контрол зламаним
       («контрол «palette» не зробив нічого»), бо палітра малюється ПОЗА
       `#bar`. Тому міряємо всі три, а не робимо палітрі виняток: виняток
       зняв би з неї цю обіцянку зовсім. */
    /* Четвертий спосіб (0.23.0): діалог `askForm` (`.cv-ask-scrim`) — «Відгук» малює його ПОЗА `#bar`, після відповіді попереднього
       перегляду (`POST /api/feedback-preview`), тож для нього чекаємо зʼявлення явно, а не рівно 150 мс. */
    if (key === "feedback") await page.waitForSelector(".cv-ask-scrim, .cv-ask-pop", { timeout: 5000 }).catch(() => {});
    const dd = await page.$$eval(".dd", (e) => e.length);
    const overlay = await page.$$eval(".pal,.keysheet,.cv-ask-scrim,.cv-ask-pop", (e) => e.length);
    assert.ok(before !== after || dd > 0 || overlay > 0,
      `контрол «${name}» не зробив нічого`);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(50);
  }

  /* Логотип-вхід на «Задачі» (0.25.0 переїхав у рядок вкладок `#tabs`) і вихід назад: «Назад до
     задачі» прибрано, повернення — клік по вкладці задачі. Без рядка `home:` / `tab:` у делегації
     смуга лишилась би назавжди на екрані «Задачі». */
  assert.ok(await page.$('#tabs [data-act="home"]'), "немає логотипа-входу на «Задачі»");
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home", { timeout: 5000 });
  assert.equal(await page.getAttribute('#tabs [data-act="home"]', "aria-current"), "page");
  assert.equal(await page.$('#bar [data-act="back"]'), null, "кнопка «Назад» повернулась у смугу");
  await page.click('#tabs [data-act="tab"]');
  await page.waitForSelector("#bar .crumb--title", { timeout: 5000 });
  assert.equal(await page.getAttribute('#tabs [data-act="home"]', "aria-current"), null,
    "після кліку по вкладці логотип лишився активним");
});

/* Другий бік тієї самої обіцянки. Перший тест тисне те, що видно на широкій
   смузі; цей перевіряє, що на вузькій керування виглядом НЕ зникає, а
   переїжджає. Саме тут ловиться баг, з якого почалась уся робота: у прототипі
   `.view-more{display:none}` стояло ПІСЛЯ контейнерного запиту з рівною
   специфічністю і перебивало його — `view-extra` ховався, «⋯» не зʼявлявся, і
   ширина з інспектором ставали недосяжні ЗОВСІМ.

   Запобіжник: порядок правил у `app/styles.css` (типова умова ПЕРЕД
   `@container`). Мутація: переставити `.view-more{display:none}` після блоку
   `@container (max-width:1060px)` — обидві половини цієї перевірки червоніють
   (виміряно). Жоден юніт цього не бачить: це геометрія, не модель. */
test("керування виглядом переїжджає у «⋯», а не зникає", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.locator("#bar [data-act=\"mode\"]").first().waitFor();

  /* `evaluate`, а не `$$eval`: див. перший тест — перемальовка смуги між вибіркою вузлів і підрахунком давала б 0 відчеплених. */
  const vis = (sel) => page.evaluate((q) => [...document.querySelectorAll(q)].filter((e) => e.offsetParent !== null).length, sel);

  assert.ok(await vis("#bar .view-extra") > 0, "1440: керування виглядом не в смузі");
  assert.equal(await vis("#bar .view-more"), 0, "1440: «⋯» показаний, хоч усе вміщається");

  await page.setViewportSize({ width: 1024, height: 900 });
  await page.waitForFunction(
    () => [...document.querySelectorAll("#bar .view-more")].some((e) => e.offsetParent !== null),
    null, { timeout: 5000 });

  assert.equal(await vis("#bar .view-extra"), 0, "1024: керування виглядом лишилось у смузі");
  assert.ok(await vis("#bar .view-more") > 0, "1024: «⋯» не зʼявився — керування недосяжне");

  /* І воно справді ПРАЦЮЄ, а не просто видиме. */
  await page.click("#bar [data-dd=\"more\"]");
  await page.locator(".dd").waitFor({ timeout: 3000 });
  assert.ok(await page.$$eval(".dd [data-act]", (e) => e.length) > 0,
    "«⋯» відкрився порожнім");
});

/**
 * Чужий процес на порту канваса не сміє виглядати як побитий `tasks.json`.
 *
 * Кейс живий (у власника двічі): на 8765 піднімався сторонній
 * `python -m http.server`, IPv6-сокет вигравав у `localhost`, застосунок
 * отримував 404-HTML **із кодом 200**, і смуга казала «tasks.json не
 * читається: unexpected token at line 41» плюс «граф не завантажився:
 * <!DOCTYPE HTML>…». Тобто інструмент вказував на СВОЇ файли, хоча
 * `tasks.json` валідний — дизайнер за такою підказкою йде чинити невинний
 * файл і нічого не знаходить.
 *
 * ⛔ Чому саме живий тест, а не юніт: юніт на `apiProblem` (`tests/api-guard.
 * test.mjs`) доводить РІШЕННЯ, але не ПРОВОДКУ. Прибери виклик з `api()` —
 * юніт лишиться зелений, а на екрані повернеться стара неправда. Тут
 * перевіряється те, що бачить дизайнер: текст у смузі помилки.
 *
 * Підміна відповіді — `page.route`, а не справжній чужий сервер на порту:
 * зайняти порт із-під тесту означало б гонку з сервером фікстури (і з іншими
 * живими наборами), а модель бою тут та сама — відповідь не від канваса.
 */
test("HTML замість JSON на /api/* називає зайнятий порт, а не наші файли", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  /* Відповідь СТОРОННЬОГО сервера: код 200 і HTML. Саме 200 — на 404 гілка
     `!res.ok` спрацювала б і без нашої перевірки, тобто тест був би зелений
     на зламаному коді. */
  await page.route("**/api/task", (route) => route.fulfill({
    status: 200, contentType: "text/html; charset=utf-8",
    body: "<!DOCTYPE HTML><html><title>404 Not Found</title><body>Not Found</body></html>",
  }));
  await page.goto(`${url}/app/`);

  const err = page.locator("#bar .errbar");
  await err.waitFor({ timeout: 10000 });
  const text = await err.innerText();
  assert.ok(/lsof/.test(text),
    `смуга помилки не назвала зайнятий порт: ${JSON.stringify(text)}`);
  assert.ok(!/tasks\.json/.test(text),
    `смуга помилки й далі звинувачує власний файл: ${JSON.stringify(text)}`);
});

/* ── підпис автора ітерації ───────────────────────────────────────────────
   Юніти (`bar-model`, `shell-bar`) перевіряють модель і розмітку на стані,
   написаному рукою. Живим лишається саме те, чого вони не бачать: підпис і
   ключ машини мусять доїхати ЧЕРЕЗ сервер (`author` у записі ітерації,
   `my_key` у `/api/task`) і зустрітись у браузері. Забудь `my_key` у
   відповіді — `mine` рахується завжди `true`, мітка чужої тихо не зʼявиться
   ніде, і жоден юніт цього не помітить. */
test("чужа ітерація в смузі підписана автором і помічена", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  // Друга ітерація — ЧУЖА: підписана іншим ключем, ніж особа цієї машини.
  const it2 = path.join(dir, "iterations", "it2");
  mkdirSync(it2, { recursive: true });
  writeFileSync(path.join(it2, "index.html"), PAGE("чуже"));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: "фікстура", published: true,
        author: "Lead", author_key: "lead@example.com" },
      { id: "it2", date: "25.08.2026 12:00", note: "передача", published: false,
        author: "Ольга Сидорук", author_key: "designer2@example.com",
        origin: { it: "it3", at: "25.08.2026 12:00" } },
    ],
  }));
  /* Особу машини задаємо середовищем — інакше вона бралась би з git-конфіга
     того, хто запустив тест, і на машині Ольги перевірка мовчки перевіряла б
     ВЛАСНУ ітерацію. `startServer` передає дитині `process.env`. */
  const keep = { n: process.env.DC_IDENTITY_NAME, e: process.env.DC_IDENTITY_EMAIL };
  process.env.DC_IDENTITY_NAME = "Lead";
  process.env.DC_IDENTITY_EMAIL = "lead@example.com";
  t.after(() => {
    if (keep.n === undefined) delete process.env.DC_IDENTITY_NAME;
    else process.env.DC_IDENTITY_NAME = keep.n;
    if (keep.e === undefined) delete process.env.DC_IDENTITY_EMAIL;
    else process.env.DC_IDENTITY_EMAIL = keep.e;
  });

  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator("#bar .crumb--iter").first().waitFor();

  /* Свідок ПЕРШИМ: типово канвас відкриває ОСТАННЮ ітерацію, тобто чужу. Якби
     він відкрив першу, перевірка нижче шукала б мітку там, де її не має бути,
     і падала б не через те, про що цей тест. */
  const crumb = page.locator("#bar button.crumb--iter");
  await crumb.locator("xpath=.").waitFor();
  assert.match(await crumb.innerText(), /Іт\.2/, "канвас відкрив не останню ітерацію");

  assert.doesNotMatch(await crumb.innerText(), /Ольга Сидорук/, "імʼя автора видно в крошці");
  assert.match(await crumb.getAttribute("title"), /Ольга Сидорук/,
    "автора немає в title — author або my_key не доїхали від сервера");
  assert.equal(await crumb.evaluate((e) => e.classList.contains("crumb--foreign")), true,
    "чужа ітерація не помічена — mine порахувався як «своя»");

  // А своя — без мітки. Без цієї половини мітка могла б стояти на всьому.
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await page.waitForFunction(() => {
    const b = document.querySelector("#bar button.crumb--iter");
    return b && b.innerText.includes("Іт.1");
  }, null, { timeout: 5000 });
  assert.equal(await crumb.evaluate((e) => e.classList.contains("crumb--foreign")), false,
    "своя ітерація помічена як чужа");
});

/* ── «Видалити ітерацію» питає в самому дропдауні (етап В, 0.28.0) ───────────────────────────────────────────────────
   Три «ні» (Esc, клік повз, «Ні») мусять лишити папку ітерації на диску й запис у iterations.json; лише явне «Видалити»
   прибирає. З палітри ⌘K — темна модальна картка (там дропдауна нема). */
test("«Видалити ітерацію»: питання в дропдауні; Esc / клік повз / «Ні» нічого не видаляють, «Видалити» видаляє; з ⌘K — картка", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const it2 = path.join(dir, "iterations", "it2");
  mkdirSync(it2, { recursive: true });
  writeFileSync(path.join(it2, "index.html"), PAGE("друга"));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: "перша", published: false },
      { id: "it2", date: "25.08.2026 12:00", note: "друга", published: false },
    ],
  }));
  const ids = () => JSON.parse(readFileSync(path.join(dir, "iterations.json"), "utf8")).iterations.map((i) => i.id);
  const alive = () => existsSync(path.join(it2, "index.html")) && ids().includes("it2");
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 70 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  let dialogs = 0;
  page.on("dialog", (d) => { dialogs += 1; d.dismiss(); });
  await page.goto(`${url}/app/`);
  await page.locator("#bar button.crumb--iter").first().waitFor();
  assert.match(await page.locator("#bar button.crumb--iter").innerText(), /Іт\.2/, "відкрита не остання ітерація");

  const ask = async () => {
    await page.click('#bar [data-dd="iter"]');
    await page.click('#bar [data-act="delitask"]');
    await page.waitForSelector("#bar .dd--confirm .cfm", { timeout: 5000 });
    assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "питання вийшло модальним");
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("cfm-no")), true, "фокус не на «Ні»");
    assert.match(await page.textContent("#bar .cfm-t"), /Видалити Іт\.2\?/);
    assert.equal(await page.locator("#bar .cfm p").count(), 1, "у питанні є щось, крім самого питання");
  };
  // (a) Esc
  await ask();
  await page.keyboard.press("Escape");
  await page.waitForSelector("#bar .dd", { state: "detached" });
  assert.equal(alive(), true, "Esc видалив ітерацію");
  // (b) клік повз смугу
  await ask();
  await page.locator(".panel").first().click({ position: { x: 3, y: 3 } });
  await page.waitForSelector("#bar .dd", { state: "detached" });
  assert.equal(alive(), true, "клік повз видалив ітерацію");
  // повторне відкриття дропдауна знову показує перелік, а не старе питання
  await page.click('#bar [data-dd="iter"]');
  await page.waitForSelector('#bar [data-act="iter"]');
  assert.equal(await page.locator("#bar .cfm").count(), 0, "питання пережило закриття дропдауна");
  await page.keyboard.press("Escape");
  // (c) «Ні»
  await ask();
  await page.click("#bar .cfm-no");
  await page.waitForSelector("#bar .dd", { state: "detached" });
  assert.equal(alive(), true, "«Ні» видалило ітерацію");
  // ⌘K → картка (модальна, темна), Esc — нічого не видалено
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Видалити ітерацію");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1, null, { timeout: 5000 });
  await page.keyboard.press("Enter");
  await page.waitForSelector(".cv-ask-scrim .cv-ask", { timeout: 5000 });
  assert.equal(await page.locator("#bar .cfm").count(), 0);
  const card = await page.evaluate(() => getComputedStyle(document.querySelector(".cv-ask")).backgroundColor);
  assert.notEqual(card, "rgb(255, 255, 255)", "картка біла");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус не на «Скасувати»");
  // Порядок кнопок (0.28.1, власник): «Скасувати» ліворуч, «Видалити» — праворуч, як «Ні» / «Видалити» в дропдауні.
  assert.deepEqual(await page.$$eval(".cv-ask-row button", (bs) => bs.map((b) => b.dataset.a)), ["cancel", "ok"]);
  await page.keyboard.press("Escape");
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(alive(), true, "Esc у картці видалив ітерацію");
  // (d) «Видалити» в дропдауні — видалено без другого вікна
  await ask();
  await page.click("#bar .cfm-yes");
  const end = Date.now() + 8000;
  while (Date.now() < end && ids().includes("it2")) await new Promise((r) => setTimeout(r, 100));
  assert.equal(ids().includes("it2"), false, "«Видалити» не дійшло до iterations.json");
  assert.equal(existsSync(it2), false, "папка ітерації лишилась на диску");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "після видалення висить друге питання");
  assert.equal(dialogs, 0, "з'явилось нативне вікно браузера");
});

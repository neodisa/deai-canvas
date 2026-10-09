/**
 * Живі перевірки автозʼємки: справжній Chromium по справжньому серверу
 * інструмента, справжній `node bin/shoot.mjs` окремим процесом. Юніти
 * (`tests/shots-progress.test.mjs`, `tests/test_shoot_progress.py`,
 * `tests/shoot-check.test.mjs`, `tests/test_serve.py`) перевіряють половини
 * контракту нарізно; тут — рівно те, чого жодна половина не бачить: чи стартує
 * зʼємка САМА, чи доїжджає кадр до полотна ДО кінця прогону, і чи не плодить
 * автостарт зайвих прогонів.
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись, чи
 * червоніє). Без неї «зелено» не означає нічого:
 *
 *   A (вхід сам стартує)     — `maybeAutoShoot()` в обробнику
 *                              `[data-act="mode"][data-val="overview"]`.
 *                              Мутація «прибрати виклик» → у «Огляді» лишаються
 *                              картки з бейджем «немає знімка», жодного POST
 *                              /api/shoot, чекання картинки топиться таймаутом.
 *                              ЧЕРВОНІЄ (виміряно).
 *   B (кадр ДО кінця         — `(snap.frames || []).forEach(applyFrame)` у
 *      прогону)                `pollProgress` — тобто підміна `<img>` з події
 *                              `frame`, яка несе `sha`/`stamp`/`capturedAt`.
 *                              Мутація «лишити тільки лічильник» → перша
 *                              картинка зʼявляється щойно з `render()` після
 *                              прогону, коли кнопка вже не «Стоп»; умова
 *                              «є кадр І кнопка ще Стоп» не настає ніколи.
 *                              ЧЕРВОНІЄ (виміряно).
 *   C (зупинка зупиняє,      — ДВІ різні половини, і запобіжники в них різні.
 *      зняте лишається)        «Зупиняє» тримає `_killpg(live['proc'], SIGTERM)`
 *                              у `_shoot_stop`: мутація «лишити прапорець, зняти
 *                              сигнал» → прогін добігає всі 4 кадри, ЧЕРВОНІЄ на
 *                              «в манифесті всі 4» (виміряно).
 *                              ⛔ «Зняте лишається» НЕ тримає названий планом
 *                              проміжний `writeManifest(dir, manifest)` — під
 *                              ЙОГО мутацією перевірка лишається ЗЕЛЕНОЮ, і ось
 *                              чому (виміряно, не здогад): SIGTERM іде ГРУПІ,
 *                              тобто гине Chromium, а node лишається живий —
 *                              посторінковий try/catch перетворює решту кадрів на
 *                              швидкі `fail`, цикл добігає до кінця, і фінальний
 *                              `writeManifest(dir, markStale(…))` кладе на диск
 *                              усе, що встигло накопичитись у памʼяті. Два
 *                              незалежні шляхи, кожен САМ ПО СОБІ достатній:
 *                              мутація «прибрати проміжний запис» — зелено,
 *                              мутація «прибрати посторінковий try/catch»
 *                              (`throw err` замість `problem`) — теж зелено, а
 *                              ОБИДВІ разом — ЧЕРВОНО («кадри, зняті до зупинки,
 *                              мусять лишитись»). Тобто ця половина стереже
 *                              ПАРУ, а не рядок; вимоги «одна мутація — один
 *                              рядок» вона не виконує, і видавати її за
 *                              охоронця проміжного запису не можна.
 *   D (рівно один автостарт  — `autoShootOff.add(picked)` У `maybeAutoShoot`.
 *      на набір застарілого)   Мутація «прибрати рядок» → другий вхід у «Огляд»
 *                              замовляє другу зʼємку. ЧЕРВОНІЄ (виміряно).
 *                              ⚠️ План називав тут інший запобіжник —
 *                              `autoShootOff.add(it)` в обробнику «Стоп». Він
 *                              цю перевірку НЕ тримає, і це виміряно окремою
 *                              мутацією: приберіть його — перевірка лишається
 *                              ЗЕЛЕНОЮ, бо позначку вже поставив сам
 *                              `maybeAutoShoot`. Ця перевірка — про НАБІР
 *                              застарілого, що не змінився (сторінки стабільно
 *                              не знімаються); ручну зупинку стереже D2.
 *   D2 (ручна зупинка        — `autoShootStopped.add(it)` в обробнику кнопки
 *       переживає повернення)  «Стоп» (`app/app.js`) — ОКРЕМИЙ набір, якого
 *                              `freshen()` не чистить. Мутація «прибрати рядок»
 *                              → повернення в «Огляд» замовляє другу зʼємку.
 *                              ЧЕРВОНІЄ (виміряно).
 *                              ⚠️ Історія, за яку заплачено виміром: спершу
 *                              обробник клав ітерацію в `autoShootOff`, і цей
 *                              сценарій не працював зовсім. Частковий прогін
 *                              МІНЯЄ перелік застарілого (знятий кадр з нього
 *                              зникає), а `freshen()` саме на зміну переліку
 *                              позначку й знімає — тобто її стирав той самий
 *                              `freshen()`, що біжить одразу після зупинки.
 *                              Виміряно на 4 сторінках: зупинка на першому
 *                              кадрі → «Перезняти (3)», повернення → «Стоп 2/3».
 *                              Тому набори РІЗНІ, і саме тому D і D2 — дві
 *                              перевірки, а не одна: у них різні запобіжники, і
 *                              кожен падає лише під своєю мутацією.
 *                              ⛔ Не під охороною: рядки `autoShootStopped
 *                              .delete(it)` / `autoShootOff.delete(it)` на
 *                              ручному натисканні (людина перебиває позначку) і
 *                              очистка всіх трьох наборів на зміні ЗАДАЧІ.
 *                              Живої перевірки на них немає — не вигадуй, що є.
 *   E (свіжа ітерація не     — гілка `if (!check || !check.stale.length) return`
 *      запускає браузер)       у `maybeAutoShoot`. Мутація «прибрати
 *                              `!check.stale.length`» → вхід у «Огляд» на
 *                              повністю свіжій ітерації все одно замовляє
 *                              зʼємку (порожню, але з процесом node і
 *                              Chromium). ЧЕРВОНІЄ (виміряно).
 *   F (другий вхід під час   — гілка `already` в `_shoot` (`app/serve.py`) під
 *      зʼємки не плодить       `_SHOOTS_LOCK`. Мутація «прибрати гілку» → друга
 *      процес)                 вкладка отримує на свою перевірку свіжості
 *                              звичайний звіт замість `already`, бачить
 *                              застаріле й замовляє СВОЮ зʼємку: два процеси
 *                              пишуть ті самі .webp навперейми. ЧЕРВОНІЄ
 *                              (виміряно).
 *
 * Чому у F спостерігається саме перевірка свіжості, а не «друга автозʼємка»:
 * `freshen()` теж іде через `POST /api/shoot` (з `check:true`), тобто через ТОЙ
 * САМИЙ замок. Поки прогін живий, друга вкладка отримує `already` вже на ньому —
 * і саме тому її автостарт не спрацьовує (звіту немає → застарілих немає). Це не
 * обхід перевірки, а той самий запобіжник, спійманий на першому ж запиті, який до
 * нього дійшов.
 *
 * Фікстури свідомо різні. `A/E` живуть на одній (E спирається на те, що A все
 * зняла), `B`, `C`, `F` вимагають ітерації БЕЗ кадрів (інакше «кадр зʼявився»
 * нема з чого відрізнити), а `D` — сторінок, які стабільно НЕ знімаються: у
 * `runShoot` вони отримують `problem`, тобто лишаються застарілими за побудовою
 * (`staleIds`), і перелік застарілого між прогонами не змінюється.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { readManifest } from "../../bin/shots-manifest.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли ПАРАЛЕЛЬНО, і спільна
   база з canvas/shoot/viewport/inspector дала б колізію портів. */
const PORT_BASE = 9190;
const VIEW = { width: 1400, height: 900 };

/* Проста висока сторінка з градієнтом. Градієнт не косметика: порожня сторінка
   1280×1200 стискається у WebP до ~4.6 КБ — нижче `BYTES_FLOOR`, і КОЖЕН кадр
   фікстури отримав би `problem` «порожня сторінка». Тоді свіжої ітерації не
   існувало б у природі й перевірка E не мала б про що говорити. */
const PAGE = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:1200px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${title}</h1></body></html>`;

/* Сторінка, яка стабільно НЕ знімається: крапка дає непорожній `innerText`, тож
   `settle()` не висить свої 45 секунд, а кадр виходить далеко нижче
   `BYTES_FLOOR` — `problem`, і запис лишається застарілим назавжди. Саме такий
   набір потрібен D: перелік застарілого після прогону той самий, що й до нього. */
const BROKEN_PAGE = () => `<!DOCTYPE html><html><body>.</body></html>`;

/** Це замовлення СПРАВЖНЬОЇ зʼємки, а не перевірка свіжості (`check:true`). */
const isShootPost = (req) => req.method() === "POST"
  && new URL(req.url()).pathname === "/api/shoot"
  && !/"check"\s*:\s*true/.test(req.postData() || "");

/** Перевірка свіжості — той самий маршрут, інше тіло. */
const isCheckPost = (req) => req.method() === "POST"
  && new URL(req.url()).pathname === "/api/shoot"
  && /"check"\s*:\s*true/.test(req.postData() || "");

/** Тіла всіх зʼємок, які замовила ЦЯ вкладка (масив росте по ходу тесту). */
function shootOrders(page) {
  const posts = [];
  page.on("request", (req) => { if (isShootPost(req)) posts.push(req.postData()); });
  return posts;
}

/* Панель шарів (Task 4 Плану B): `#pp-shoot` більше не існує — кнопка
   зʼємки тепер `[data-act="shoot"]` усередині `#pages-panel`, і живе під
   `.shots` секцією.
   ⚠️ ВИПРАВЛЕНО: тут раніше стояло «у новій кнопка каже голе «Стоп», а
   „знімаю N з M“ — окремий рядок статусу над нею». Це описувало ПРОМІЖНИЙ
   (уже виправлений) стан: сам автор пайплайна знайшов і полагодив живими
   тестами саме ту ваду — «кнопка втратила лічильник (казала голе «Стоп»)»,
   коміт `072e1e5`, — повернувши `shootStopLabel`. Сьогодні кнопка каже
   «Стоп N/M» (лічильник НА кнопці, як і в старій панелі), а `.shots-s`
   («знімаю N з M») — ДОДАТКОВИЙ рядок статусу над нею, а не заміна
   лічильника на кнопці. Обидва місця несуть те саме число — це навмисне
   дублювання (кнопка лишається зрозумілою сама по собі, рядок над нею дає
   контекст), а не розбіжність. Гелпери нижче звіряються за КНОПКОЮ (біжить/
   не біжить) — це не змінилось; за ЧИСЛОМ на кнопці звіряється тест B
   напряму (бо саме воно й є вимірюваною величиною там), за рядком
   `.shots-s` — B, C, D2. */
const SHOOT_BTN = '#pages-panel [data-act="shoot"]';
const SHOTS_LINE = "#pages-panel .shots-s";

const label = (page) => page.evaluate((sel) =>
  document.querySelector(sel)?.textContent.trim() ?? null, SHOOT_BTN);

/* Тихий рядок блоку кадрів (План A, Task 2) — те саме читання, що `label`
   вище, лише інший вузол: при підтвердженій свіжості кнопки зʼємки в
   розмітці немає, і стан секції каже цей рядок. `.trim()` — з тієї самої
   причини, що описана над `runEnded` нижче: між `>` тега й іконкою в
   шаблоні стоїть переніс рядка, і він буквальний текстовий вузол DOM. */
const quietLine = (page) => page.evaluate(() =>
  document.querySelector("#pages-panel .shots-quiet")?.textContent.trim() ?? null);

/* «Кнопка каже Стоп» (ловити ПОЧАТОК прогону) свідомо без окремого хелпера:
   `waitForFunction` по тексту, що переписується цілком щотакту прогресу
   (`renderPanel()`, Task 4 Плану B), у цій фікстурі (крихітні сторінки,
   прогін за секунди) ловив вікно «Стоп» ненадійно — виміряно повторним
   прогоном. Тести нижче чекають старт зʼємки мережевою подією
   (`waitForRequest`/`waitForResponse` на `POST /api/shoot`) — сигнал один
   на весь прогін, а не текст, що зникає швидше, ніж встигає завершитись такт
   опитування. */

/** Кнопка перестала казати «Стоп» — прогін завершився (сам чи зупинкою).
 *
 * ⚠️ ВИПРАВЛЕНО (живий вимір під час цього прогону): без `.trim()` предикат
 * був МЕРТВОНАРОДЖЕНИЙ — повертав «прогін скінчився» ще ДО першого кадру.
 * Кнопка — `${ico(v.icon)}<span>${esc(v.label)}</span>` усередині
 * багаторядкового шаблона (`shotsHTML`, `app/shell-panel.js`): між `>`
 * відкривального тега й `${ico(...)}` у ВИХІДНОМУ КОДІ шаблона стоїть
 * переніс рядка й відступ, і це буквальний текстовий вузол у DOM — іконка
 * (SVG) текстових вузлів не додає. Тобто `textContent` кнопки СТРУКТУРНО
 * має вигляд `"\n      Стоп 1/3"`, а `/^Стоп/` перевіряє САМ ПОЧАТОК рядка:
 * перед «Стоп» завжди стоїть `\n`, і регулярка НІКОЛИ не збігається —
 * незалежно від того, йде прогін чи ні. Виміряно живцем: пряме читання
 * `textContent` кнопки під час активної зʼємки (done=1 з 3, кнопка щойно
 * перемальована з коректним «Стоп 1/3») дало РІВНО цей рядок, і
 * `waitForFunction` резолвився за лічені мілісекунди після виклику — тобто
 * `settled()`/`runEnded()` не чекали кінця прогону ВЗАГАЛІ, а зчитування
 * останньої картки й манифеста (A, B, F) чи вхід на «не зовсім свіжу»
 * ітерацію (E, каскадом від передчасного A) ловили прогін на середині.
 * `label()` вище вже рятується `.trim()` з тієї самої причини — тут просто
 * бракувало того самого рядка. */
const runEnded = (page, timeout = 180000) => page.waitForFunction(
  (sel) => !/^Стоп/.test((document.querySelector(sel)?.textContent || "").trim()),
  SHOOT_BTN, { timeout });

/**
 * `runEnded`, ПЛЮС запас на осідання. `shootingIt` (app.js) звільняється
 * одразу, як тільки `POST /api/shoot` відповів, а панель перемальовується з
 * ЦИМ фактом аж на фінальному `render()` (після `await freshen()` —
 * окремого мережевого round-trip) — того самого такту, який уже раз ловив
 * `pollProgress` (стара латка `autoShootStopped`/`freshen()`, шапка файлу).
 * `runEnded()` сам по собі бачить лише ПЕРШУ мить «не Стоп», яка часом
 * випереджає цей фінальний рендер, і читання ярлика зразу по тому діставало
 * б ще не осілий підпис. Ставимо ту саму паузу «з запасом», що вже стоїть
 * нижче для `freshen()`. */
const settled = async (page, timeout) => {
  await runEnded(page, timeout);
  await page.waitForTimeout(500);
};

/** Дочекатись, поки полотно «Огляду» справді показане (`true`) чи сховане. */
const overviewShown = (page, yes) => page.waitForFunction(
  (want) => document.getElementById("canvas").hidden !== want, yes, { timeout: 15000 });

/* Смуга (Task 3): перемикач «як дивлюсь» — це СЕГМЕНТ із двох окремих кнопок
   (`[data-act="mode"]`), а не перемикач `#view-toggle`, що клацав туди-назад
   одним і тим самим елементом. Вхід в «Огляд» і вихід із нього — РІЗНІ кнопки:
   де тест раніше клікав `#view-toggle` двічі поспіль, щоб повернутись, тепер
   треба клікнути РІЗНІ елементи (`overview`, тоді `layout`), інакше другий клік
   по «overview» нічого не зробить (уже там) і перевірка мовчки не поверне стан. */
const toOverview = (page) => page.locator('[data-act="mode"][data-val="overview"]');
const toLayout = (page) => page.locator('[data-act="mode"][data-val="layout"]');

/** Вкладка інструмента, відкрита в робочому вигляді (ще НЕ в «Огляді»). */
async function openApp(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await toOverview(page).waitFor();
  return page;
}

test("автозʼємка на вході в «Огляд» і мовчання на свіжій ітерації", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk", "kartka"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  await t.test("A. вхід у «Огляд» сам стартує зʼємку — кнопку ніхто не тиснув", async () => {
    const page = await openApp(browser, url);
    const orders = shootOrders(page);
    await toOverview(page).click();

    await page.locator(".cv-card").first().waitFor();
    /* Не порожня перевірка: на вході кадрів немає ЖОДНОГО, тобто картинка нижче
       береться саме з автозʼємки, а не лежала на диску з попереднього життя. */
    assert.equal(await page.locator(".cv-card img").count(), 0,
      "на вході в «Огляд» кадрів ще немає — інакше перевірка порожня");

    await page.locator(".cv-card img").first().waitFor({ timeout: 60000 });
    assert.equal(orders.length, 1,
      `рівно одне замовлення зʼємки, і зробив його вхід у «Огляд»: ${JSON.stringify(orders)}`);
    assert.match(orders[0], /"it":"it1"/);

    await settled(page);
    assert.equal(await page.locator(".cv-card img").count(), 3,
      "прогін мусив дійти до кінця й закрити всі три картки");
    await page.close();
  });

  await t.test("E. свіжа ітерація не запускає браузер узагалі", async () => {
    const page = await openApp(browser, url);
    const orders = shootOrders(page);
    const checks = [];
    page.on("request", (req) => { if (isCheckPost(req)) checks.push(req.postData()); });

    await toOverview(page).click();
    await page.locator(".cv-card img").first().waitFor({ timeout: 30000 });
    /* Даємо автостарту повний шанс спрацювати: `maybeAutoShoot` кличеться
       одразу після `freshen()`, а POST полетів би першим же тактом. Якщо
       автостарт УСЕ Ж таки помилково стартував (кнопка каже «Стоп»,
       наприклад тому, що манифест A ще не встиг лягти на диск до перевірки
       свіжості цієї вкладки) — чекаємо його завершення, а не просто
       фіксований час: інакше перевірка ловить ЧУЖИЙ прогін посеред роботи й
       звинувачує в тому, що зняти мало НУЛЬ. */
    await page.waitForTimeout(4000);
    /* ⚠️ ПЕРЕПИСАНО (План A, Task 2): при підтвердженій свіжості блок кадрів
       згортається в ОДИН тихий рядок, і кнопки зʼємки в розмітці немає
       зовсім — тобто `label(page) === null` тут більше не «кнопку не
       знайдено», а очікуваний кінцевий стан. Тому охоронець від порожньої
       перевірки переїхав на сам тихий рядок нижче: якби панель не намалювала
       НІЧОГО, обидва твердження впадуть. Гілка «прогін усе ж стартував»
       лишилась та сама (кнопка каже «Стоп») — вона й є причина, чому тут
       читається `label`, а не одразу тихий рядок. */
    const running = await label(page);
    if (running && /^Стоп/.test(running)) await settled(page, 60000);

    assert.ok(checks.length >= 1,
      "перевірка свіжості мусила відбутись — інакше перевірка порожня");
    /* Панель шарів: підтверджена свіжість більше не кричить вимкненою
       кнопкою «Оновити кадри (0)» — вона каже одним тихим рядком, скільки
       кадрів свіжі. Нуль застарілого тут ЧЕСНИЙ (сервер щойно порахував), і
       саме тому блок має право змовкнути; у стані «свіжість не
       перевірялась» тиші не буде — це стереже юніт у
       `tests/shell-panel.test.mjs`. */
    assert.equal(await label(page), null,
      "свіжо — кнопки зʼємки в блоці більше немає, є тихий рядок");
    assert.equal(await quietLine(page), "Кадри · 3 свіжі",
      "тихий рядок мусить сказати, скільки кадрів і що вони свіжі");
    assert.deepEqual(orders, [],
      "знімати нічого — жоден node і жоден Chromium не мусив піднятись");
    await page.close();
  });

  /* Проводка тихого блоку — саме тут, а не в `tests/live/shell-panel.test.mjs`,
     де живуть решта живих охоронців контролів панелі: тиха секція існує ЛИШЕ
     при підтвердженій свіжості, а свіжі кадри є тільки там, де їх справді
     зняли справжнім Chromium. Ця фікстура їх уже має (A вище зняв три), тож
     перевірка коштує один перехід, а не ще один повний прогін зʼємки.
     Юніти перевіряють РОЗМІТКУ обох станів; тут перевіряється, що клік по
     ній щось робить і що вибір переживає перезавантаження — `PANEL_ACTIONS
     .shotsopen` разом із `dc-shots-open` (`app.js`). */
  await t.test("E2. тихий блок відкривається кліком, згортається назад і пам’ятає вибір", async () => {
    const page = await openApp(browser, url);
    await toOverview(page).click();
    await page.locator(".shots-quiet").waitFor({ timeout: 30000 });
    assert.equal(await label(page), null, "у тихому стані кнопки зʼємки немає");

    await page.locator(".shots-quiet").click();
    await page.locator(SHOOT_BTN).waitFor({ timeout: 5000 });
    assert.equal(await page.locator(".shots-quiet").count(), 0,
      "після розгортання тихий рядок мусить піти — інакше блок каже двічі");
    /* Кнопка розгорнутого блоку тут ВИМКНЕНА, і це не «не працює»: свіжість
       підтверджена сервером, оновлювати нема чого (`fresh` → `disabled`,
       затверджений прототип). Доводиться саме досяжність керування за один
       клік — те, що тиха секція його не втратила. Робочу кнопку в стані, де
       робити ЩОСЬ треба, стереже сусідній тест «кнопка «Кадри» реагує на
       клік і її можна зупинити» (`tests/live/shell-panel.test.mjs`). */
    assert.ok(await page.locator(SHOOT_BTN).isDisabled(),
      "застарілого нема — кнопка розгорнутого блоку лишається вимкненою");
    assert.match(await page.locator(SHOTS_LINE).first().innerText(), /усі свіжі/);

    /* Вибір «розгорнуто» переживає перезавантаження — інакше він не вибір.
       ⚠️ Перезавантаження вертає інструмент у «Макет», і свіжість там знову
       НЕВІДОМА (`lastCheck` — змінна модуля, перевірку кличе лише вхід у
       «Огляд»). У тому стані блок розгорнутий незалежно від збереженого
       вибору, тобто перевірка одразу після `reload()` була б порожньою — і
       була, першим прогоном цього тесту. Тому вертаємось у «Огляд»,
       дочікуємось підтвердженої свіжості й лише тоді питаємо: якби вибір не
       зберігся, блок ЗАРАЗ згорнувся б у тихий рядок. */
    await page.reload();
    await toOverview(page).waitFor();
    await toOverview(page).click();
    await page.waitForFunction((sel) => /усі свіжі/.test(
      document.querySelector(sel)?.textContent || ""), SHOTS_LINE, { timeout: 30000 });
    assert.equal(await page.locator(".shots-quiet").count(), 0,
      "збережений вибір «розгорнуто» не дожив до наступного відкриття");

    // І дорога назад: заголовок блоку згортає його в той самий тихий рядок.
    await page.locator('#pages-panel [data-act="shotsopen"]').click();
    await page.locator(".shots-quiet").waitFor({ timeout: 5000 });
    assert.equal(await label(page), null);
    await page.close();
  });
});

test("B. кадр зʼявляється на полотні ДО кінця прогону", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk", "kartka"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await openApp(browser, url);
  await toOverview(page).click();

  /* Умова одна й цілісна: кадр СПРАВДІ завантажився (`naturalWidth`), і при цьому
     кнопка ще каже «Стоп …». Порізати її на два кроки не можна — між ними прогін
     встиг би скінчитись, і перевірка стала б перевіркою «кадри врешті є».
     ⚠️ ВИПРАВЛЕНО (той самий вимір, що й над `runEnded`): без `.trim()` ця
     умова НІКОЛИ не збігалась — `btn.textContent` завжди починається з
     переносу рядка й відступу (буквальний текстовий вузол шаблона `shotsHTML`
     ПЕРЕД `${ico(...)}`), тож `/^Стоп/` не бачив «Стоп» навіть посеред
     активного прогону. Звідси й 60-секундний таймаут: перша половина умови
     (кадр завантажився) справджувалась швидко, друга — ніколи. */
  await page.waitForFunction((sel) => {
    const imgs = [...document.querySelectorAll(".cv-card img")];
    const btn = document.querySelector(sel);
    return imgs.length >= 1 && imgs.every((i) => i.complete && i.naturalWidth > 0)
      && /^Стоп/.test((btn?.textContent || "").trim());
  }, SHOOT_BTN, { timeout: 60000 });

  /* Лічильник «зроблено/усього» живе на КНОПЦІ («Стоп N/M», `shootStopLabel`,
     `app/shell-panel.js`) і ЩЕ РАЗ, іншими словами, у рядку статусу над нею
     (`.shots-s`, «знімаю N з M») — навмисне дублювання, не розбіжність (див.
     виправлений коментар над `SHOOT_BTN`).
     ⚠️ ВИПРАВЛЕНО: тут раніше стояло `assert.equal(mid.btn, "Стоп", ...)` —
     очікування, що кнопка посеред прогону каже ГОЛЕ «Стоп», без числа. Це
     була та сама застаріла вада, яку вже описано вище: `shootStopLabel`
     повернув лічильник НА кнопку (коміт `072e1e5`), і кнопка посеред
     тристорінкового прогону чесно каже «Стоп 1/3» чи «Стоп 2/3» — перевірка
     нижче звіряє РІВНО це число, а не голий факт «це Стоп». */
  const mid = await page.evaluate(({ btnSel, lineSel }) => ({
    n: document.querySelectorAll(".cv-card img").length,
    btn: document.querySelector(btnSel).textContent.trim(),
    line: document.querySelector(lineSel)?.textContent.trim() ?? "",
  }), { btnSel: SHOOT_BTN, lineSel: SHOTS_LINE });
  assert.ok(mid.n >= 1 && mid.n < 3,
    `посеред прогону на полотні мусить бути частина кадрів, а не ${mid.n} із 3`);
  // Те саме число, що й на полотні: `applyFrame` для кожного кадру `snap.frames`
  // відпрацьовує В ТОМУ Ж такті `pollProgress`, ДО перемальовки кнопки — тобто
  // `done` і кількість `<img>` на полотні синхронні в кожному конкретному рендері.
  assert.equal(mid.btn, `Стоп ${mid.n}/3`,
    `кнопка посеред прогону мусить казати «Стоп N/3» із тим самим N, що й на полотні: «${mid.btn}»`);
  assert.match(mid.line, /^знімаю \d+ з 3$/,
    "рядок статусу мусить нести і зроблене, і скільки всього");

  await runEnded(page);
  assert.equal(await page.locator(".cv-card img").count(), 3);
});

test("C. «Зупинити» зупиняє, і зняте до зупинки лишається", async (t) => {
  const { dir, it1 } = taskFixture({
    html: PAGE, pages: ["holovna", "poshuk", "kartka", "profil"],
  });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await openApp(browser, url);
  /* Відповідь на POST /api/shoot приходить лише в кінці прогону — саме в ній
     сервер каже, ЧОМУ прогін скінчився. Чекання ставимо ДО кліку по «Огляд». */
  const answer = page.waitForResponse((res) => isShootPost(res.request()), { timeout: 180000 });
  await toOverview(page).click();

  // Чекаємо, поки в лічильнику буде хоч один кадр: зупиняти до першого кадру
  // означало б перевіряти порожній манифест. Лічильник — у рядку статусу
  // (`.shots-s`), не в кнопці (Task 4 Плану B, див. коментар над `SHOOT_BTN`).
  await page.waitForFunction(
    (sel) => /^знімаю [1-9]/.test(document.querySelector(sel)?.textContent || ""),
    SHOTS_LINE, { timeout: 60000 });
  // Кнопка панелі — звичайний DOM поза холстом, `setPointerCapture` тут нікого не
  // перехоплює, тож програмний клік годиться.
  await page.locator(SHOOT_BTN).click();

  const body = await (await answer).json();
  assert.equal(body.stopped, true,
    `сервер мусив звітувати саме про зупинку: ${JSON.stringify(body).slice(0, 300)}`);
  await runEnded(page);

  const shots = readManifest(it1).shots;
  const keys = Object.keys(shots);
  /* Перша половина стережеться ПАРОЮ (проміжний запис манифеста АБО посторінковий
     try/catch плюс фінальний запис) — див. шапку: кожна половина пари сама по собі
     достатня, тож окремою мутацією ця умова не червоніє. Друга — «в манифесті НЕ
     всі 4» — і є доказ того, що зупинка справді зупинила: під мутацією
     «`_shoot_stop` без `_killpg`» прогін добігає до кінця й червонить саме її. */
  assert.ok(keys.length >= 1,
    "кадри, зняті до зупинки, мусять лишитись у манифесті — .webp уже на диску");
  assert.ok(keys.length < 4,
    `зупинка мусила обірвати прогін, а в манифесті всі ${keys.length} кадрів`);
  for (const key of keys) {
    assert.ok(shots[key].stamp, `${key}: запис без штампа — наступний прогін зніме його заново`);
    assert.ok(shots[key].sha, `${key}: запис без sha`);
  }
});

test("D. рівно один автостарт на набір застарілого", async (t) => {
  /* Обидві сторінки НЕ знімаються (кадр нижче BYTES_FLOOR → `problem`), тобто
     перелік застарілого після прогону такий самий, як до нього. Це той випадок,
     заради якого позначка й існує: інакше кожен вхід у «Огляд» давав би дизайнеру
     новий прогін Chromium — і так до нескінченності. */
  const { dir } = taskFixture({ html: BROKEN_PAGE, pages: ["holovna", "poshuk"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await openApp(browser, url);
  const orders = shootOrders(page);
  /* Відповідь на POST /api/shoot — той самий, доведено надійний сигнал «прогін
     стартував і скінчився», що вже працює в перевірці C: чекання на текст
     кнопки («Стоп») тут ловило не завжди — обидві крихітні сторінки цієї
     фікстури «не встоюють» майже миттєво, і вікно «Стоп» виявилось закоротким
     для стабільного захоплення `waitForFunction`-ом по тексту, що
     перемальовується цілком (`renderPanel()`, Task 4 Плану B). Мережева
     подія такої гонки не знає: вона одна на весь прогін. */
  const answer = page.waitForResponse((res) => isShootPost(res.request()), { timeout: 60000 });
  await toOverview(page).click();
  await answer;
  await settled(page);
  assert.equal(orders.length, 1, "перший вхід мусив замовити рівно одну зʼємку");
  // Task 4 Плану B: «Перезняти (N)» → «Оновити кадри (N)», нова копія
  // прототипу для того самого стану (є кадри, N із них застарілі).
  assert.equal(await label(page), "Оновити кадри (2)",
    "жоден кадр не вийшов — застарілими лишились обидва, тобто робота ще є");

  // Вихід у робочий вигляд і повернення в «Огляд» — той самий шлях, що й перший раз.
  await toLayout(page).click();
  await overviewShown(page, false);
  await toOverview(page).click();
  await overviewShown(page, true);
  await page.waitForTimeout(5000);   // з запасом на `freshen()` (окремий процес node)

  assert.equal(orders.length, 1,
    "другий вхід на той самий набір застарілого не сміє замовити другу зʼємку");
  assert.equal(await label(page), "Оновити кадри (2)",
    "і кнопка не мусить перетворитись на «Стоп»");
});

test("D2. повторний вхід після РУЧНОЇ зупинки не стартує автоматично", async (t) => {
  /* Чотири сторінки: зупинка на першому кадрі мусить лишити роботу, інакше
     «автостарту немає» пояснювалось би тим, що знімати нічого (це вже перевірка
     E, і плутати їх не можна). */
  const { dir } = taskFixture({
    html: PAGE, pages: ["holovna", "poshuk", "kartka", "profil"],
  });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await openApp(browser, url);
  const orders = shootOrders(page);

  await toOverview(page).click();
  await page.waitForFunction(
    (sel) => /^знімаю [1-9]/.test(document.querySelector(sel)?.textContent || ""),
    SHOTS_LINE, { timeout: 60000 });
  await page.locator(SHOOT_BTN).click();          // зупинка РУКАМИ
  await settled(page);

  assert.equal(orders.length, 1, "до цього місця зʼємка мусила бути рівно одна");
  const afterStop = await label(page);
  /* Несуча передумова: робота ЛИШИЛАСЬ. Саме тут стара реалізація й падала —
     `freshen()` після зупинки бачив ІНШИЙ перелік застарілого (знятий кадр з
     нього зник) і саме тому стирав позначку. */
  assert.match(afterStop, /^Оновити кадри \([1-9]\d*\)$/,
    `після зупинки мусить лишитись незнята робота, а кнопка каже «${afterStop}»`);

  await toLayout(page).click();
  await overviewShown(page, false);
  await toOverview(page).click();
  await overviewShown(page, true);
  await page.waitForTimeout(5000);   // з запасом на `freshen()` (окремий процес node)

  assert.equal(orders.length, 1,
    "після ручної зупинки повернення в «Огляд» не сміє почати все спочатку");
  assert.equal(await label(page), afterStop,
    "і кнопка мусить лишитись «Оновити кадри (N)», а не перекинутись у «Стоп»");
});

test("F. другий вхід під час зʼємки не плодить другий процес", async (t) => {
  const { dir, it1 } = taskFixture({
    html: PAGE, pages: ["holovna", "poshuk", "kartka", "profil"],
  });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const first = await openApp(browser, url);
  /* Чекаємо, поки ПЕРША вкладка ЗАМОВИТЬ зʼємку — не поки кнопка скаже
     «Стоп» (DOM-текст, що переписується цілком щотакту прогресу, у цій
     фікстурі ловився ненадійно — див. коментар над `settled` вище). Сам факт
     запиту `POST /api/shoot` — сигнал «прогін стартував», рівно те, що тут
     потрібно: другій вкладці треба застати
     сервер УЖЕ зайнятим, а не чекати, поки ПЕРША домалює кнопку. */
  const firstStarted = first.waitForRequest((req) => isShootPost(req), { timeout: 60000 });
  await toOverview(first).click();
  await firstStarted;

  const second = await openApp(browser, url);
  const orders = shootOrders(second);
  /* Відповіді сервера на СПРАВЖНІ замовлення зʼємки другою вкладкою.
     ⛔ Перевірку свіжості (`check:true`) сюди пускати НЕ можна, і це не
     причіпка. Перша редакція цієї перевірки брала перше-ліпше звернення до
     `/api/shoot` — а першим завжди йде саме `check`, який тоді ТЕЖ брав замок і
     відповідав `already`. Тобто перевірка «замок тримає» доводилась відповіддю
     на перевірку свіжості, тобто кодувала як бажану поведінку рівно той баг,
     який знайшло ревʼю: під час зʼємки друга вкладка не могла дізнатись, що
     застаріло, і показувала «Перезняти» без числа при 22 застарілих кадрах.
     Тепер `check` замка не бере, тож ловимо саме зʼємку. */
  const answers = [];
  second.on("response", async (res) => {
    const req = res.request();
    if (req.method() !== "POST") return;
    if (new URL(res.url()).pathname !== "/api/shoot") return;
    try {
      if (JSON.parse(req.postData() || "{}").check) return;   // перевірка свіжості — не сюди
      answers.push(await res.json());
    } catch (e) { /* тіло вже недоступне */ }
  });

  await toOverview(second).click();
  const deadline = Date.now() + 30000;
  while (!answers.length && Date.now() < deadline) {
    await new Promise((done) => setTimeout(done, 200));
  }
  assert.ok(answers.length >= 1, "друга вкладка мусила замовити зʼємку");
  assert.equal(answers[0].already, true,
    `друга вкладка мусить ПРИЄДНАТИСЬ до наявної зʼємки: ${JSON.stringify(answers[0]).slice(0, 300)}`);
  assert.equal(typeof answers[0].progress?.running, "boolean",
    "і отримати знімок прогресу тієї самої зʼємки");

  await second.waitForTimeout(4000);
  /* ⚠️ Тут стояло `orders === []` — «друга вкладка не сміє замовити свою зʼємку».
     Це було описом БАГА, а не інваріанта: замовлення не було лише тому, що
     перевірка свіжості теж бралась замком і віддавала `already` без звіту, тож
     друга вкладка вважала, що застарілого немає. Спека ж (§B) каже протилежне:
     друга спроба ПРИЄДНУЄТЬСЯ. Тому інваріант інший — замовити вона може, але
     кожне замовлення мусить дістати `already`, тобто другого процесу не буде.
     Що процесу справді не було, доводить перелік кадрів у кінці: один набір. */
  assert.ok(orders.length >= 1,
    "друга вкладка бачить застаріле й замовляє зʼємку — інакше вона не знає стану");
  assert.equal(answers.length, orders.length,
    "на кожне замовлення другої вкладки мусить бути відповідь");
  assert.deepEqual(answers.map((a) => a.already), answers.map(() => true),
    "кожне замовлення другої вкладки мусить приєднатись, а не підняти другий Chromium");

  await runEnded(first);
  const keys = Object.keys(readManifest(it1).shots);
  assert.deepEqual(keys.sort(), ["holovna", "kartka", "poshuk", "profil"],
    "у манифесті мусить лишитись рівно один набір кадрів — по одному на сторінку");
});

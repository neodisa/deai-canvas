import assert from "node:assert/strict";
import { appendFileSync, chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { CARD_W, FLOW_LEFT, GAP, ROW_TITLE_TOP } from "../../app/canvas-geom.js";
import { readManifest } from "../../bin/shots-manifest.mjs";
import { runShoot } from "../../bin/shoot.mjs";
import { hermeticLiga, MODULE_ADAPTER_GLOB } from "./_liga-supabase.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/** Обрати ітерацію через дропдаун крошки в смузі.
 *  Замінює `page.selectOption("#pp-itsel", …)`: панельний `<select>` зник
 *  разом зі старою панеллю (Task 4), а перелік переїхав у крошку смуги. */
async function selectIteration(page, id) {
  await page.locator('[data-dd="iter"]').click();
  const item = page.locator(`.dd [data-act="iter"][data-val="${id}"]`);
  await item.waitFor();
  await item.click();
  /* Чекаємо на ФАКТ перемикання, а не на таймер: `iter` асинхронна
     (`loadPages`, іноді `freshen`), і клік повертає керування раніше, ніж
     смуга перемалюється. */
  await page.waitForFunction(
    (want) => {
      const el = document.querySelector('[data-dd="iter"] .txt--fix');
      return el && el.textContent.trim() === want;
    },
    `Іт.${String(id).replace(/^it/, "")}`,
    { timeout: 10000 },
  );
}

/**
 * Світовий `left` кадру в колонці `col` флоу-виду — тим самим кроком і тим самим
 * зсувом, якими його ставить розкладка.
 *
 * З КОНСТАНТ, а не числом: колонка друга — це «кадр плюс зазор», і поки число
 * стояло тут руками (`"1376px"`), зміна зазору червоніла перевіркою драгу з
 * «1376 !== 1480», ніби зламалась фіча, якої ніхто не торкався. Дзеркалом коду це
 * не стає: перевіряється тут не арифметика, а те, що кадр СТОЇТЬ у колонці, яку
 * йому поклали руками, і що після перезавантаження він у ній лишився.
 */
const colX = (col) => `${FLOW_LEFT + col * (CARD_W + GAP)}px`;

/* База порту саме цього файлу: `node --test` крутить файли паралельно, і спільна
   база з shoot.test.mjs дала б колізію портів. */
const PORT_BASE = 8890;
const VIEW = { width: 1400, height: 900 };

/* Проста висока сторінка, без спінерів і лінивих картинок: тут перевіряється
   холст, а не зʼємка. Виміряно на цій фікстурі й цьому вьюпорті: «вписати все»
   дає `scale(0.399096)`, кнопка «Відкрити» на екрані 32.44 × 7.58 px (CSS 81×19).
   Натискання надійне, але роздувати фікстуру не можна: масштаб упаде до кількох
   відсотків, кнопка стане тоншою за піксель і тест почне брехати.
   Градієнт у `background` — БЕЗ нового елемента, тому `height:1200px` і всі
   калібрування вище лишаються чинними: він лише піднімає вагу WebP вище
   `BYTES_FLOOR`. Порожня сторінка на 1280×1200 стискається до ~4.6 КБ — нижче
   порога 6 КБ, тобто Task 1 («кадр із проблемою застарілий за побудовою»)
   позначав би КОЖЕН кадр цієї фікстури як `problem`, і бейдж «застаріло» з
   тестів F/G/H та «обрізано» з R замінявся б на «знімок N байт — це порожня
   сторінка». Знайдено прогоном `npm run test:live` після Task 1. */
const PAGE = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:1200px;background:repeating-linear-gradient(37deg,#e11 0 10px,` +
    `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${title}</h1></body></html>`;

/** Сторінка інструмента, відкрита в «Огляді», з домальованими кадрами. */
/**
 * Дочекатись, поки автозʼємка ВЩУХНЕ — і доведено вщухне, а не блимне.
 *
 * ⛔ Навіщо окремий хелпер, а не `waitFor('.shots-quiet')`. Тихий рядок буває
 * на екрані ДВІЧІ: до того, як перевірка свіжості здала перелік застарілого,
 * і після того, як зʼємка скінчилась. Голе очікування ловить перше з них і
 * віддає керування рівно перед початком прогону — тобто «дочекався тиші»
 * означає «встиг до шуму». Тому чекаємо тишу, яка ТРИМАЄТЬСЯ: `hold` мс
 * поспіль без рядка прогресу.
 *
 * Навіщо це взагалі. Автозʼємка (T-34) зʼявилась ПІЗНІШЕ за тести камери
 * (T-31) і перебудовує холст щоразу, коли доїжджає кадр: `buildCanvas`
 * починається з `world.innerHTML = ''`, отже забирає і підсвітку `sel`, і
 * будь-які мітки на елементах. Перевірки, що клікають рядок панелі й дивляться
 * на камеру, від цього падали НЕ на своїй ваді — і падали через раз, бо все
 * залежало від того, чи встигне черговий кадр. Саме це дало TD-13: базу, у
 * якій «червоне» перестало щось означати.
 */
async function shotsSettled(page, { hold = 1500, timeout = 180000 } = {}) {
  const until = Date.now() + timeout;
  let quietSince = 0;
  for (;;) {
    const busy = await page.evaluate(() => !!document.querySelector(".shots-s"));
    if (busy) quietSince = 0;
    else if (!quietSince) quietSince = Date.now();
    else if (Date.now() - quietSince >= hold) return;
    if (Date.now() > until) {
      throw new Error("зʼємка не вщухла за відведений час — тиша так і не протрималась");
    }
    await page.waitForTimeout(100);
  }
}

async function overview(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  return page;
}

/**
 * Справжнє натискання по елементу всередині холста: `mouse.down`/`mouse.up`, а не
 * `locator.click()` — див. шапку файлу.
 */
async function press(page, locator) {
  /* `boundingBox()` віддає `null` для елемента, що ще/вже невидимий, — пункт палітри чи дропдауна в мить появи або
     перемальовування (`render()` замінює вузол між `waitFor` і виміром). 4b-2 спіймало це як плаваюче падіння K2/AE
     (`reading 'x'` на `null`; K2 червоніла так і на базі до 4b-2): міряємо з повтором, доки вузол не стане видимим. */
  let box = null;
  for (let i = 0; i < 50 && !box; i += 1) {
    box = await locator.boundingBox().catch(() => null);
    if (!box) await page.waitForTimeout(100);
  }
  if (!box) throw new Error(`press: елемент не набув розмірів за 5 с: ${locator}`);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.up();
}

/* Смуга (Task 3): старий перемикач `#view-toggle` клацав туди-назад ОДНИМ
   елементом; тепер це сегмент із ДВОХ окремих кнопок
   (`[data-act="mode"][data-val="overview"]`/`…="layout"]`), тому «вийти й
   вернутись» — це клік по РІЗНИХ елементах, а не той самий елемент двічі.
   Перемикач режиму коментарів (`[data-cmode="…"]`,
   пізніше `[data-act="cmode"]` у дропдаунах смуги) зі смуги пішов зовсім —
   у 0.27.0 канали коментарів зникли зовсім (див. `forceRender` нижче). */
const toOverview = (page) => page.locator('[data-act="mode"][data-val="overview"]');
const toLayout = (page) => page.locator('[data-act="mode"][data-val="layout"]');

/* Перемикача задач у смузі більше нема (0.25.0): задачу відкривають з екрана «Задачі» карткою (або вкладкою). */
async function selectTask(page, id) {
  await page.locator('#tabs [data-act="home"]').click();
  await page.locator(`#tasks-home .th-card[data-id="${id}"]`).click();
}

/* Колесо в «Огляді» (0.25.0): просто колесо РУХАЄ полотно, а масштабує ⌘ + колесо. Масштабні тести крутять колесо з ⌘,
   щоб delta лишалась тією самою (Ctrl — щипок — підсилюється ×6). */
async function zoomWheel(page, dx, dy) {
  await page.keyboard.down("Meta");
  try { await page.mouse.wheel(dx, dy); } finally { await page.keyboard.up("Meta"); }
}

/** Побічний `render()` оболонки без жодної зміни стану. З 0.27.0 канал коментарів («Клод/Команда») не перемикається
 *  (комбіноване сховище, без `commentMode`), тож перемикач, який цей тест тиснув заради перебудови, зник. Лишився той
 *  самий шлях, яким оболонка перебудовує полотно, — дія смуги `retry` (`BAR_ACTIONS.retry` → `render()`): кнопку, що її
 *  малює лише смуга помилки, імітуємо елементом із `data-act` усередині `#bar` (делегація слухає саме його). */
async function forceRender(page) {
  await page.evaluate(() => {
    const b = document.createElement("button");
    b.dataset.act = "retry";
    document.getElementById("bar").appendChild(b);
    b.click();
    b.remove();
  });
}

/** Чекати, поки в режимі однієї ітерації iframe візьме саме цю сторінку. */
const opened = (page, id) => page.waitForFunction((pageId) => {
  const f = document.getElementById("frame");
  return f && !f.hidden && new RegExp(`page=${pageId}`).test(f.getAttribute("src") || "");
}, id, { timeout: 5000 });

const transform = (page) => page.evaluate(() =>
  document.getElementById("world").style.transform);

test("холст «Огляд»: кадри, кнопка і камера", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  /* Без `supabase: true` (до 0.27.0 він був потрібен, щоб у палітрі зʼявився канал «Команда»): тепер ЛІГА з конфігом Supabase
     піднімає командне сховище в КОЖНІЙ рамці робочого місця, і сторінка без `hermeticLiga` пішла б по вигаданий хост у
     справжню мережу. Тест про полотно, а не про канали, — тож просто простір без команди.
     ⛔ Не `page.route` на кожній сторінці файла: він вимикає HTTP-кеш Chromium, а K1 саме його й міряє
     («незмінний кадр бере з кешу»). */
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  await runShoot({ dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
                   launch: () => chromium.launch() });

  const browser = await chromium.launch();
  t.after(() => browser.close());

  await t.test("A. «Відкрити» справжнім натисканням мишею", async () => {
    const page = await overview(browser, url);
    const open = page.locator(".cv-card").first().locator(".cv-open");
    await open.waitFor();

    /* Записуємо, на що САМЕ народився `click`. Без цього перевірка сліпа до
       запобіжника: сторінку відкрив би `pointerup` холста, і `frame.src` цієї
       різниці не бачить. */
    await page.evaluate(() => {
      window.__clicked = [];
      addEventListener("click", (e) => {
        window.__clicked.push(e.target.closest?.(".cv-open") ? "cv-open" : "інше");
      }, true);
    });

    const box = await open.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.up();

    await opened(page, "holovna");
    assert.deepEqual(await page.evaluate(() => window.__clicked), ["cv-open"],
      "справжнє натискання мусить народити click саме на кнопці");
  });

  await t.test("B. «Відкрити» з клавіатури", async () => {
    const page = await overview(browser, url);
    const open = page.locator(".cv-card").first().locator(".cv-open");
    await open.waitFor();
    await open.focus();
    await page.keyboard.press("Enter");
    await opened(page, "holovna");
  });

  await t.test("C. натискання по тілу кадру теж відкриває його", async () => {
    const page = await overview(browser, url);
    const body = page.locator(".cv-card").first().locator(".cv-card-body");
    const box = await body.boundingBox();
    // Ближче до верху кадру: кадр високий, його середина може виїхати за вьюпорт.
    await page.mouse.move(box.x + box.width / 2, box.y + 40);
    await page.mouse.down();
    await page.mouse.up();
    await opened(page, "holovna");
  });

  await t.test("D. повернення в «Огляд» сідає рівно у fit і лишається там", async () => {
    const page = await overview(browser, url);
    const fit = await transform(page);

    /* Колесо і ДВА натискання перемикача — в одному синхронному блоці, щоб між
       ними не встиг пройти жоден кадр rAF: інакше цикл камери доїде сам, гасити
       буде нічого, і перевірка стане порожньою. Запас великий: один щиглик колеса
       тримає цикл ~575мс (TAU 90мс до порогу 0.5px), а обидва рендери
       вкладаються в ~80мс на локальному сервері. */
    await page.evaluate(() => {
      const c = document.getElementById("canvas");
      const r = c.getBoundingClientRect();
      c.dispatchEvent(new WheelEvent("wheel", {
        deltaY: -240, metaKey: true, cancelable: true,
        clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
      }));
      /* Смуга (Task 3): старий `#view-toggle` був перемикачем — той самий
         елемент туди й назад. Тепер це сегмент із ДВОХ окремих кнопок, тож
         «і одразу назад» — це клік по ІНШОМУ елементу, а не другий клік по
         тому самому (другий клік по «layout» був би нічим: режим уже такий). */
      document.querySelector('[data-act="mode"][data-val="layout"]').click();    // з «Огляду» в ітерацію
      document.querySelector('[data-act="mode"][data-val="overview"]').click();  // і одразу назад
    });
    await page.locator(".cv-card img").first().waitFor();
    await page.waitForTimeout(900);   // довше за життя циклу камери

    assert.equal(await page.evaluate(() => document.getElementById("canvas").hidden),
      false, "перемикач мусив повернути нас у «Огляд»");
    assert.equal(await transform(page), fit,
      "камера мусить сісти рівно у fit і лишитись там, а не доїхати до старої цілі");

    /* Не порожня перевірка: колесо справді рухає камеру, отже попереднє
       порівняння зелене не тому, що рухати нічого. */
    const box = await page.locator("#canvas").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await zoomWheel(page, 0, -240);
    await page.waitForTimeout(800);
    assert.notEqual(await transform(page), fit, "колесо мусить змінювати трансформ");
  });

  await t.test("E. кадри в «Огляді» — картинки, а не iframe (регресія Task 10)", async () => {
    const page = await overview(browser, url);
    assert.equal(await page.locator("#canvas iframe").count(), 0);
    // Знімок довгої сторінки вищий за вьюпорт — картка мусить це нести
    const h = await page.locator(".cv-card img").first().getAttribute("height");
    assert.ok(Number(h) > 900, `висота кадру ${h}`);

    /* Кадр мусить справді ЗАВАНТАЖИТИСЬ, а не просто бути в розмітці. Без цього
       рядка зламаний URL знімка непомітний: `<img>` з атрибутом `height` виглядає
       точно так само, як робочий, і всі перевірки лишаються зеленими — доведено
       мутаційно (перейменування параметра `node=` → `nd=` не зловив ніхто).
       Саме тут жив баг із `~` у ключі кадру: файл на диску є, сервер віддає 400,
       картка мовчки порожня.
       Чекаємо `load`/`error` (до 10 с), а не читаємо `complete` одразу: `overview()` чекає лише появи `<img>` у розмітці, а кадр — `loading="lazy"`
       і `decoding="async"`, тож під навантаженням релізного прогону 0.24.0 він ще вантажився — плаваюче «не завантажилась». Битий URL дає
       `error` → `false`, тож мутація `node=` → `nd=` червоніє так само. */
    const loaded = await page.locator(".cv-card img").first()
      .evaluate((img) => (img.complete ? img.naturalWidth > 0 : new Promise((done) => {
        img.addEventListener("load", () => done(img.naturalWidth > 0), { once: true });
        img.addEventListener("error", () => done(false), { once: true });
        setTimeout(() => done(img.complete && img.naturalWidth > 0), 10000);
      })));
    assert.ok(loaded, "кадр у розмітці є, але картинка не завантажилась");
  });

  await t.test("K1. незмінний кадр після перезавантаження бере його з кешу, а не з мережі",
    async () => {
      /* НЕ рахуємо `page.on('response')` по перемикачу аудиторії, як у першій
         версії цієї перевірки: `render()` малює НОВИЙ `<img>` з ТИМ САМИМ `src` У
         ТОМУ САМОМУ документі, і Blink розвʼязує його з ресурс-кешу документа —
         запит НЕ долітає до мережевого стеку взагалі, незалежно від заголовка
         відповіді. `page.on('response')` тут сліпий до різниці між «взято з
         HTTP-кешу» і «запиту не було зовсім» — перша версія лишалась зеленою
         НАВІТЬ на подвійному `Cache-Control` батьківського коміту (справжній
         регрес, зловлений ревʼю). Тому міряємо через СПРАВЖНЮ межу навігації
         (`page.reload()`) і питаємо CDP напряму: `Network.requestServedFromCache`
         — єдиний сигнал, що чесно каже, звідки взявся байт. Перевірено мутаційно
         (живцем, поза цим файлом): з `no-store` в `_shot` і окремо з подвійним
         `Cache-Control` батьківського коміту (`b514dd1`, безумовний `no-cache` в
         `end_headers` без охорони) множина `requestServedFromCache` порожня — цей
         тест тоді падає рівно на `assert.ok` нижче. */
      const page = await overview(browser, url);
      await page.waitForLoadState("networkidle");

      const client = await page.context().newCDPSession(page);
      await client.send("Network.enable");
      const shotUrlById = new Map();
      const servedFromCache = new Set();
      client.on("Network.requestWillBeSent", (e) => {
        if (e.request.url.includes("/shot?")) shotUrlById.set(e.requestId, e.request.url);
      });
      client.on("Network.requestServedFromCache", (e) => servedFromCache.add(e.requestId));

      await page.reload();
      // `mode` — змінна модуля, а не localStorage: reload завжди скидає її в
      // 'single', тож «Огляд» треба відкрити наново, як і на самому початку.
      await page.getByRole("button", { name: /Огляд/ }).click();
      await page.locator(".cv-card img").first().waitFor();
      await page.waitForLoadState("networkidle");

      assert.equal(shotUrlById.size, 2,
        `очікували рівно 2 запити кадрів (holovna, poshuk): ${[...shotUrlById.values()]}`);
      for (const [id, shotUrl] of shotUrlById) {
        assert.ok(servedFromCache.has(id), `кадр прийшов З МЕРЕЖІ, а мав з кешу: ${shotUrl}`);
      }
    });

  await t.test("K2. перезнятий кадр (інший capturedAt) таки довантажується з мережі", async () => {
    /* K1 доводить лише половину задачі — що НЕЗМІННИЙ кадр не тягнеться повторно.
       Друга половина, заради якої взагалі стоїть `capturedAt` у ключі: перезнятий
       кадр НЕ застряє у вічному кеші назавжди. Якби ключ носив лише `stamp` (хеш
       джерел), примусова `--all`-перезйомка лишала б його тим самим — і з
       `immutable` браузер показував би СТАРИЙ знімок вічно. Це рівно та причина,
       через яку раніше стояв `no-store`. Тут (на відміну від K1) досить
       `page.on('response')` У ТОМУ САМОМУ документі: URL кадру ЗМІНЮЄТЬСЯ, а для
       геть нового URL кешу однаково нема звідки взятись — перевіряємо не
       «звідки взявся байт», а сам факт, що новий байт узагалі доїхав. */
    const page = await overview(browser, url);
    // Той самий запобіжник, що в K1: інакше повільний `poshuk` з початкового
    // завантаження міг би зарахуватись у "мережу" перезйомки нижче.
    await page.waitForLoadState("networkidle");
    const firstImg = page.locator(".cv-card img").first();
    const before = await firstImg.getAttribute("src");

    /* Контент сторінок не змінюємо — лише `now`, щоб змінився САМЕ `capturedAt`,
       а не `stamp` (він хеш джерел і від дати не залежить). ⛔ Саме через цю
       підстановку K2 і не бачить дірки з хвилинною точністю: справжня друга
       зйомка дала б ТУ САМУ хвилину. Ключ це переживає завдяки хешу байтів
       (`sha`), і стереже його юніт у tests/shoot-check.test.mjs. */
    await runShoot({ dir: it1, it: "it1", url, all: true, now: "25.08.2026 09:00",
                     launch: () => chromium.launch() });

    const fromNet = [];
    page.on("response", (r) => { if (r.url().includes("/shot?")) fromNet.push(r.url()); });
    /* Побічний `render()` (див. `forceRender`): колись його давав перемикач каналу коментарів. */
    await forceRender(page);
    /* Явне очікування замість `waitForTimeout` навмання: чекаємо на ФАКТ, що
       зʼявився САМЕ НОВИЙ `src` (не старий, який і так `complete` від першого
       завантаження — без порівняння з `before` умова була б істинною ще ДО
       того, як `render()` взагалі встиг перемалювати картку, спіймано живцем:
       перша версія цього рядка читала «after» раніше за сам ребілд) і що ця
       нова картинка СПРАВДІ довантажилась (як у E), а не висить розбитою. */
    await page.waitForFunction((prevSrc) => {
      const img = document.querySelector(".cv-card img");
      return img && img.getAttribute("src") !== prevSrc && img.complete && img.naturalWidth > 0;
    }, before);

    const after = await firstImg.getAttribute("src");
    assert.notEqual(after, before,
      "новий capturedAt мусив змінити ключ кадру (`v=`), а не лишити його тим самим");
    /* `getAttribute('src')` дає ВІДНОСНИЙ шлях із розмітки, а `response.url()` —
       розвʼязаний абсолютний. Пряме порівняння не збіглось би НІКОЛИ, і зелена
       перевірка була б порожньою — доведено живцем (перший прогін падав тут). */
    assert.ok(fromNet.some((u) => u.endsWith(after)),
      `перезнятий кадр мусив довантажитись з мережі за новим ключем: ${fromNet.join(", ") || "(нічого не прийшло)"}`);
  });

  await t.test("K3. кадр, який не доїхав, каже про це — а не показує биту картинку", async () => {
    const page = await browser.newPage({ viewport: VIEW });
    /* Ламаємо саме доставку файла, а НЕ манифест: запис у манифесті лишається.
       Це відтворює реальний стан — тека ітерації приїжджає з GitLab з чужої
       машини, і `manifest.json` та `.webp` там окремі файли. */
    await page.route("**/shot?**", (route) => route.abort());
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await page.locator(".cv-card .cv-badge").first().waitFor();
    const badge = await page.locator(".cv-card .cv-badge").first().textContent();
    assert.match(badge, /не читається/);
  });

  await t.test("K4. перелік сторінок не завантажився — панель каже причину", async () => {
    const page = await browser.newPage({ viewport: VIEW });
    await page.route("**/api/iteration-pages**", (route) => route.abort());
    await page.goto(`${url}/app/`);
    await page.locator("#pages-panel").waitFor();
    const txt = await page.locator("#pages-panel").textContent();
    assert.match(txt, /не завантажились/);
  });

  await t.test("F. вхід у «Огляд» перезважує штампи і сам перезнімає застаріле", async () => {
    /* Правимо сторінку ПІСЛЯ зʼємки фікстури. У манифесті кадр лишається
       `stale:false` — застарівання видно тільки якщо хтось перезважить штампи, а
       `GET /api/shots` лише читає файл. Тому це перевірка не кнопки, а того, що
       вхід в «Огляд» кличе `--check` і ЧЕКАЄ його.

       ⚠️ ПЕРЕПИСАНО під автозʼємку (T-34). Доти перевірка чекала підпис
       «Перезняти (1)» і тиснула кнопку руками. Тепер вхід із застарілим кадром
       САМ починає зʼємку, і той підпис не встигає побути на екрані взагалі —
       кнопка одразу стає «Стоп». Запобіжник лишився ТОЙ САМИЙ (`await
       freshen()` в обробнику `BAR_ACTIONS.mode`), змінився лише його наслідок, який
       видно: не підпис у спокої, а сам факт автозʼємки і її ЗАГАЛЬНЕ число.

       ⚠️ ПЕРЕПИСАНО ВДРУГЕ під панель шарів (Task 4 Плану B). Затверджений
       прототип (`docs/proto/shell.html`, `renderShots`) навмисно короткий на
       кнопці під час зʼємки — сама кнопка каже лише «Стоп», без лічильника:
       `N`/`M` живуть в ОКРЕМОМУ рядку статусу (`.shots-s`, «знімаю N з M»,
       `shotsRun` у `i18n.js`) над кнопкою. Це не регрес: старий `.pp-shoot`
       ніс і статус, і дію ОДНИМ текстом кнопки — новий розділяє їх на два
       вузли. `M` тут — і далі `wanted.length` серверного прогону, лише
       читаємо його з іншого місця в DOM.
       Так само перейменовано й саму лексику стану «нема чого знімати»:
       старе «Перезняти» (без числа) стало «Оновити кадри (0)» — п'ятий стан
       («усе свіже», див. шапку `shotsView` у `shell-panel.js`) з'явився саме
       в Task 4, і кнопка в ньому ще й `disabled` (затверджений прототип,
       `${fresh ? 'disabled' : ''}`) — стара «Перезняти» лишалась доступною
       завжди, нова свідомо гасить дію, якій нема чого робити. */
    appendFileSync(path.join(it1, "holovna", "index.html"), "<p>дописано</p>\n");
    const before = readManifest(it1).shots;

    const page = await overview(browser, url);
    /* Без `freshen()` на вході `checkOf()` порожній, `maybeAutoShoot` виходить
       першим же рядком — і цього стану не настає ніколи. Лічильник — у
       статус-рядку (`.shots-s`), не на кнопці, див. коментар вище. */
    /* ⚠️ ПРИБРАНО 18.09.2026 очікування ПЕРЕХІДНОГО рядка «знімаю N з 1».
       Воно було зайвим і гоночним водночас. Зайвим — бо факт автозʼємки
       доводять твердження про МАНИФЕСТ нижче: без `freshen()` на вході
       `maybeAutoShoot` вийшов би першим рядком, і штамп не змінився б.
       Гоночним — бо зʼємка ОДНІЄЇ сторінки триває ~3с і встигає завершитись
       раніше, ніж `overview()` віддасть керування (він чекає на `.cv-card img`,
       а той зʼявляється не в фіксований момент). Тоді рядок статусу вже
       зник назавжди, і перевірка чекала свої 20с намарно. Зміряно
       діагностикою: статус проходить «знімаю 0» → «знімаю 0 з 1» → зникає
       за ~4с від входу.
       Саме це давало TD-13 — червону базу, через яку падіння живих тестів
       перестали читати. Стан «у процесі» свідомо стереже окремий тест `I`,
       якому він потрібен по суті (він тисне «Стоп» посеред прогону). */

    /* Справжня зʼємка: serve.py піднімає node + Chromium окремим процесом.

       ⚠️ ПЕРЕПИСАНО ВТРЕТЄ (План A, Task 2): кінець прогону більше НЕ видно
       підписом «Оновити кадри (0)» — при підтвердженій свіжості блок кадрів
       згортається в один тихий рядок (`.shots-quiet`), а кнопки зʼємки в
       розмітці не лишається взагалі. Стан той самий, сигнал інший вузол:
       наявність тихого рядка і ЄСТЬ «свіжо, нічого не біжить, манифест
       читається» (`quiet` у `shotsView`, `app/shell-panel.js`) — те, що
       перше твердження перевіряло трьома окремими умовами. Друга умова
       («жодного бейджа „застаріло“ на полотні») лишилась дослівно. */
    await page.waitForFunction(() => {
      const quiet = document.querySelector(".shots-quiet");
      const stale = [...document.querySelectorAll("#world .cv-badge")]
        .some((b) => b.textContent === "застаріло");
      return !!quiet && !stale;
    }, null, { timeout: 120000 });

    const after = readManifest(it1).shots;
    assert.notEqual(after.holovna.stamp, before.holovna.stamp,
      "правлену сторінку мусили перезняти");
    assert.equal(after.poshuk.stamp, before.poshuk.stamp,
      "а неправлену — лишити в спокої: перезважування вибирає, а не гребе все");
  });

  await t.test("G. лічильник бачить сторінку, якої ще НЕ знімали", async () => {
    /* Іде після F, тобто всі наявні кадри свіжі. Додаємо сторінку — знімка в неї
       немає, і в манифест вона не потрапляє взагалі (`runShoot` пише запис лише
       після вдалої зʼємки). Лічильник, порахований по ЗАПИСАХ манифеста, показав
       би тут «Перезняти» без числа, хоча натискання її таки зніме — кнопка
       занижувала б власну роботу. */
    mkdirSync(path.join(it1, "nova"), { recursive: true });
    writeFileSync(path.join(it1, "nova", "index.html"), PAGE("nova"));
    writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
      pages: [{ id: "holovna", name: "Головна", published: true },
              { id: "poshuk", name: "Пошук", published: true },
              { id: "nova", name: "Нова", published: true }],
    }));

    const page = await overview(browser, url);
    /* ⚠️ ПЕРЕПИСАНО під автозʼємку (T-34) — див. F. Стереже те саме: серверний
       перелік застарілого мусить БАЧИТИ сторінку без запису в манифесті. Число
       читаємо зі статус-рядка («знімаю N з 1» — те саме перенесення з кнопки в
       `.shots-s`, що й у F, Task 4 Плану B), а доводить справу поява запису
       `nova` у манифесті: лічильник по ЗАПИСАХ манифеста не дав би ні того, ні
       того — зʼємка просто не почалась би. */
    /* ⚠️ ПРИБРАНО 18.09.2026 очікування ПЕРЕХІДНОГО рядка «знімаю N з 1».
       Воно було зайвим і гоночним водночас. Зайвим — бо факт автозʼємки
       доводять твердження про МАНИФЕСТ нижче: без `freshen()` на вході
       `maybeAutoShoot` вийшов би першим рядком, і штамп не змінився б.
       Гоночним — бо зʼємка ОДНІЄЇ сторінки триває ~3с і встигає завершитись
       раніше, ніж `overview()` віддасть керування (він чекає на `.cv-card img`,
       а той зʼявляється не в фіксований момент). Тоді рядок статусу вже
       зник назавжди, і перевірка чекала свої 20с намарно. Зміряно
       діагностикою: статус проходить «знімаю 0» → «знімаю 0 з 1» → зникає
       за ~4с від входу.
       Саме це давало TD-13 — червону базу, через яку падіння живих тестів
       перестали читати. Стан «у процесі» свідомо стереже окремий тест `I`,
       якому він потрібен по суті (він тисне «Стоп» посеред прогону). */
    await page.waitForFunction(() => {
      const quiet = document.querySelector(".shots-quiet");
      const gap = [...document.querySelectorAll("#world .cv-badge")]
        .some((b) => b.textContent === "немає знімка");
      // Тихий рядок замість «Оновити кадри (0)» — те саме перенесення
      // сигналу, що й у F (План A, Task 2): підтверджена свіжість більше не
      // малює кнопки зʼємки взагалі.
      return !!quiet && !gap;
    }, null, { timeout: 120000 });
    assert.ok(readManifest(it1).shots.nova,
      "сторінку, якої ніколи не знімали, автозʼємка мусила зняти");
  });

  await t.test("H. зміна ітерації в «Огляді» теж перезважує штампи", async () => {
    /* Другий шлях у «Огляд» — дропдаун ітерацій у панелі, яка на холсті ВИДИМА.
       Поки перевірка висіла лише на кнопці смуги, цей шлях обходив її цілком:
       застарілий кадр без бейджа й лічильник у нулі. Знайдено ревʼю. */
    const it2 = path.join(dir, "iterations", "it2");
    mkdirSync(path.join(it2, "holovna"), { recursive: true });
    writeFileSync(path.join(it2, "holovna", "index.html"), PAGE("it2"));
    writeFileSync(path.join(it2, "pages.json"), JSON.stringify({
      pages: [{ id: "holovna", name: "Головна", published: true }],
    }));
    writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
      iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "ф", published: true },
                   { id: "it2", date: "24.08.2026 13:00", note: "друга", published: true }],
    }));
    // Правимо сторінку it1 вже ПІСЛЯ того, як F її перезняла.
    appendFileSync(path.join(it1, "holovna", "index.html"), "<p>ще раз</p>\n");

    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    // it2 остання, тому обрана вона; кадрів у неї немає — чекаємо картку, не img.
    await page.locator(".cv-card").first().waitFor();

    await selectIteration(page, "it1");
    await page.waitForFunction(() => [...document.querySelectorAll("#world .cv-badge")]
      .some((b) => b.textContent === "застаріло"), null, { timeout: 15000 });
  });

  await t.test("H2. лічильник «Перезняти» рахує КАДРИ, а не сторінки", async () => {
    /* Кадр стану лежить у манифесті під ключем `сторінка~хеш`, а в переліку
       СТОРІНОК панелі його немає ніколи — сторінки з таким іменем не існує. Тому
       формула по сторінках (вона стояла в `renderPanel` до цього ревʼю) кадрів
       стану не бачила: сервер зняв би `poshuk~48d0ed7a`, а кнопка казала
       «Перезняти» без числа. Число мусить дорівнювати ТОМУ, ЩО ЗРОБИТЬ
       НАТИСКАННЯ, за визначенням — тобто переліку `stale` серверної перевірки, а
       не другій формулі, яка дзеркалить серверну «поки цілі зʼємки одного виду».

       Іде після H, тобто в it1 є і застаріла сторінка (`holovna`), і сторінка без
       кадру (`nova` з G) — тож перевірка ловить саме ДОДАНИЙ кадр стану, а не
       «число зʼявилось». */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f", title: "Стан", nodes: [
        { id: "n1", page: "poshuk" },
        { id: "n2", page: "poshuk", state: { state: "empty" }, label: "Порожньо" },
      ], edges: [{ from: "n1", to: "n2" }] },
    ] }));

    /* ⚠️ ПЕРЕПИСАНО під автозʼємку (T-34). Запобіжник той самий — ДЖЕРЕЛО числа
       на кнопці (`check.stale.length` серверної перевірки, а не друга формула по
       сторінках панелі), — але побачити підпис у спокої стало окремою роботою:
       вхід у «Огляд» із застарілим кадром одразу починає зʼємку і сам зʼїдає той
       перелік, який ми міряємо. Тому:
         1. ітерацію обираємо ЩЕ В РЕЖИМІ ОДНІЄЇ (там `maybeAutoShoot` не
            кличеться) — інакше довелось би ловити перегони з автозʼємкою it2,
            яка блокує автозʼємку it1 прапорцем `shooting`;
         2. автозʼємку it1 зупиняємо РУКАМИ на «знімаю 0 з N», тобто ДО
            першого кадру — так перелік застарілого лишається неторканим, а
            `autoShootStopped` не дає їй початись знову.
       Підганяння під зелене тут немає: число, яке ми читаємо, і далі приходить із
       `renderPanel`, і далі звіряється з відповіддю сервера.

       ⚠️ ПЕРЕПИСАНО ВДРУГЕ під панель шарів (Task 4 Плану B), той самий
       перенос, що в F/G: «N з M» стоїть у статус-рядку (`.shots-s`), кнопка
       під час зʼємки каже лише «Стоп» — тому «до першого кадру» тепер читаємо
       звідти. Фінальний підпис кнопки теж змінив слово: «Перезняти (N)» стало
       «Оновити кадри (N)» (`shotsUpdate`, той самий словник, що в F/G). */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.locator('[data-dd="iter"]').waitFor();
    await selectIteration(page, "it1");
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();

    await page.waitForFunction(
      () => /^знімаю 0 з \d+$/.test(document.querySelector(".shots-s")?.textContent.trim() || ""),
      null, { timeout: 30000 });
    await page.locator('[data-act="shoot"]').click();          // зупинка ДО першого кадру

    const shown = await page.waitForFunction(() => {
      const m = document.querySelector('[data-act="shoot"]')?.textContent.trim()
        .match(/^Оновити кадри \((\d+)\)$/);
      return m ? Number(m[1]) : null;
    }, null, { timeout: 60000 }).then((h) => h.jsonValue());

    /* Авторитет — сам сервер, і питаємо ми його ТИМ САМИМ викликом, яким його
       питає `freshen()`. Порівнюємо з числом, а не з магічною константою: ловити
       треба розбіжність джерел, а не збіг цифр у цій фікстурі. */
    const report = await page.evaluate(async () => {
      const res = await fetch("/api/shoot", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ it: "it1", check: true }) });
      return (await res.json()).report;
    });
    assert.ok(report.stale.some((k) => k.includes("~")),
      `сервер не назвав жодного кадру стану: ${JSON.stringify(report.stale)}`);
    assert.equal(shown, report.stale.length,
      `кнопка каже ${shown}, а натискання знімe ${report.stale.length}: ${report.stale.join(", ")}`);
  });

  await t.test("I0. «Флоу»: без flow.json неактивна, з ним перемикається", async () => {
    /* НЕ через спільний `overview()`: той чекає `.cv-card img`, а після H
       найновіша ітерація (it2) навмисно БЕЗ жодного знімка — свіжий `page.goto`
       вибирає саме її (остання в списку), і чекання картинки висить до
       таймауту незалежно від того, є перемикач чи нема. Кнопка «Флоу» лежить
       у смузі за умовою `mode === 'canvas'`, знімки їй ні до чого — тож і
       перевірці досить дочекатися самого режиму «Огляд», без картки.

       it2 заодно закриває невиконаний пункт спеки: `flow.json` у неї немає, тобто
       граф малювати НЕМА З ЧОГО — кнопка мусить бути неактивною з причиною в
       тултіпі, а не вести на полотно, де лишились одні «не у флоу» (і звідки, поки
       кнопка липла до `canvasView`, не було чим вийти). Перемикається вона на it1,
       де граф є — його поклала H2. */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    const toggle = page.getByRole("button", { name: /Флоу/ });
    await toggle.waitFor();
    assert.equal(await toggle.isDisabled(), true,
      "без flow.json кнопка «Флоу» мусить бути неактивною");
    /* Смуга (Task 3): причина вимкнення тепер ВИДИМИЙ текст усередині самої
       кнопки (`.dd-why`), а не лише в `title` — так вимагає спека («причина
       видима скрізь, де контрол вимкнений»), і так само це стереже юніт
       «вимкнений пункт несе причину класом dd-why, не лише title»
       (`tests/shell-bar.test.mjs`). Тому тут читаємо текст кнопки, а не
       атрибут `title`, який тепер несе лише підпис («Флоу»). */
    assert.match(await toggle.innerText(), /flow\.json/,
      "неактивна кнопка мусить казати ЧОМУ вона неактивна — видимим текстом");

    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    await toggle.click();
    // Підпис мусить стати зворотним: інакше незрозуміло, у якому ти виді
    await page.getByRole("button", { name: /Сітка/ }).waitFor();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });

    /* А тепер пастка, яку робить сама «неактивна кнопка»: вид `flow` навмисно
       ЛИПКИЙ, і перемикання на ітерацію без `flow.json` лишало б нас у графі, з
       якого нема чим вийти — кнопка ж неактивна. Тому вид мусить відступити в
       сітку сам, і сказати про це підписом. */
    await selectIteration(page, "it2");
    await page.waitForFunction(() => !document.querySelector(".cv-band")
      && document.querySelector("#world .cv-card"), null, { timeout: 15000 });
    assert.equal(await page.getByRole("button", { name: /Флоу/ }).isDisabled(), true,
      "без flow.json кнопка мусить бути неактивною і після переходу з графа");

    /* Але сам ВИБІР дизайнера при цьому не забуто: назад на ітерацію з графом —
       і граф знову на екрані, без другого натискання. */
    await selectIteration(page, "it1");
    await page.locator(".cv-band").first().waitFor({ timeout: 20000 });
    await page.getByRole("button", { name: /Сітка/ }).click();
    await page.getByRole("button", { name: /Флоу/ }).waitFor();
    await page.close();
  });

  await t.test("I1. побитий flow.json видно на полотні, а не 3.2 секунди в тості",
               async () => {
    /* Тост гасне за 3.2с, і після цього ТРИ різні стани виглядають однаково:
       файла немає / файл є, але вузли не вцілили / файл нечитний. Постійна
       поверхня — панель скарг (плюс кнопка «Флоу» з тултіпом). Стан «файла немає»
       перевіряє I0 на it2, тут — два інші. */
    const flowPath = path.join(it1, "flow.json");
    const openIt1 = async () => {
      const page = await browser.newPage({ viewport: VIEW });
      await page.goto(`${url}/app/`);
      await page.getByRole("button", { name: /Огляд/ }).click();
      await page.locator(".cv-card").first().waitFor();
      await selectIteration(page, "it1");
      await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
      return page;
    };

    // 1. НЕЧИТНИЙ файл. Причина приходить полем `error` у `GET /api/flow` — і
    //    мусить лягти в панель, а не мигнути тостом.
    writeFileSync(flowPath, "{ це взагалі не JSON");
    const bad = await openIt1();
    await bad.locator("#cv-flow-problems").waitFor({ state: "visible", timeout: 15000 });
    assert.match(await bad.locator("#cv-flow-problems").textContent(), /не читається/,
      "нечитний flow.json не називає причини на полотні");
    assert.equal(await bad.getByRole("button", { name: /Флоу/ }).isDisabled(), true,
      "графа немає — кнопка «Флоу» мусить бути неактивною");
    await bad.close();

    /* 2. Файл читається, але вузол не вцілив, і ми в СІТЦІ. Свій `readFlow` канвас
          у сітці не кличе взагалі — отже скарги серверної перевірки тут ЄДИНЕ
          джерело причин, а `freshen()` викидав їх разом з усім звітом. */
    writeFileSync(flowPath, JSON.stringify({ flows: [
      { id: "f", title: "Описка", nodes: [{ id: "n1", page: "nemaje-takoji" }], edges: [] },
    ] }));
    const typo = await openIt1();
    await typo.locator("#cv-flow-problems").waitFor({ state: "visible", timeout: 15000 });
    assert.match(await typo.locator("#cv-flow-problems").textContent(), /nemaje-takoji/,
      "скарги серверної перевірки не доїхали до панелі");
    assert.equal(await typo.getByRole("button", { name: /Флоу/ }).isDisabled(), false,
      "файл читається — граф малювати є з чого, кнопка мусить бути активною");

    /* 3. І скарга не сміє переїхати на ЧУЖУ ітерацію: в it2 `flow.json` немає
          зовсім, тобто скаржитись нема на що. Перелік, що лишився з минулої
          побудови, брехав би про цілий граф. */
    await selectIteration(typo, "it2");
    await typo.waitForFunction(() => {
      const el = document.getElementById("cv-flow-problems");
      return !el || el.hidden;
    }, null, { timeout: 15000 });
    await typo.close();
  });

  await t.test("I1b. у СІТЦІ скарги розбору видно й тоді, коли серверна перевірка впала",
               async () => {
    /* Дірка, яку це стереже. У сітці канвас ТЕЖ кличе свій `readFlow`
       (`flowNodesForGrid` — ряд бере з нього стани сторінки), але його
       `problems` нікуди не йшли: `paintFlowProblems` виходив з того, що в сітці
       розбору немає взагалі, і причина в його коментарі застаріла ще до злиття.
       Поки серверна перевірка свіжості віддає свій перелік, різниці не видно —
       рядки збігаються дослівно й склеюються множиною. Видно рівно тоді, коли
       перевірка ВПАЛА: у `catch` `freshen()` стоїть `lastCheck = null`, і
       другого джерела не лишається — сітка мовчить про побитий граф зовсім.
       Саме тому тут глушиться `/api/shoot`, а не просто відкривається сітка. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f", title: "Описка", nodes: [{ id: "n1", page: "nemaje-takoji" }], edges: [] },
    ] }));
    const page = await browser.newPage({ viewport: VIEW });
    await page.route("**/api/shoot", (r) => r.fulfill({ status: 500, body: "{}" }));
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator("#cv-flow-problems").waitFor({ state: "visible", timeout: 15000 });
    assert.match(await page.locator("#cv-flow-problems").textContent(), /nemaje-takoji/,
      "у сітці скарга розбору не показана, а серверної перевірки немає — граф побитий мовчки");
    /* І це СІТКА, а не флоу: без цього рядка перевірка стерегла б чужий вид, де
       скарги й так доїжджали. */
    assert.ok(await page.locator(".cv-row-title").count() > 0, "вид не сітковий");
    assert.equal(await page.locator(".cv-band").count(), 0, "вид не сітковий");
    await page.close();
  });

  await t.test("S. панель скарг не накриває полотно", async () => {
    /* Скарг буває стільки ж, скільки вузлів. Без стелі висоти й прокрутки панель
       росте вниз без кінця: граф зникає під нею цілком, а подітись від неї нікуди
       — вона не закривається. Вісімдесят битих вузлів — не вигадка, а звичайна
       описка в назві сторінки, повторена по всьому графу. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f", title: "Багато скарг", edges: [],
        nodes: Array.from({ length: 80 }, (_, i) => ({ id: `n${i}`, page: "nemaje" })) },
    ] }));

    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator("#cv-flow-problems").waitFor({ state: "visible", timeout: 20000 });

    const geom = await page.evaluate(() => {
      const el = document.getElementById("cv-flow-problems");
      const r = el.getBoundingClientRect();
      const canvas = document.getElementById("canvas").getBoundingClientRect();
      return { bottom: r.bottom, canvasBottom: canvas.bottom, height: r.height,
               scroll: el.scrollHeight, client: el.clientHeight,
               overflow: getComputedStyle(el).overflowY };
    });
    assert.ok(geom.bottom <= geom.canvasBottom + 1,
      `панель скарг вилізла за полотно на ${Math.round(geom.bottom - geom.canvasBottom)}px `
      + `(висота ${Math.round(geom.height)}px)`);
    assert.ok(geom.scroll > geom.client,
      "перелік не прокручується — скарги за стелею недосяжні");
    assert.match(geom.overflow, /auto|scroll/,
      `панель не прокручується: overflow-y = ${geom.overflow}`);

    /* І прокрутка мусить справді працювати КОЛЕСОМ. Холст ловить `wheel` і кличе
       `preventDefault` — без окремої гілки для панелі колесо над нею рухає
       полотно, а скарги за стелею лишаються недосяжними, тобто стеля просто
       ховає частину переліку замість того, щоб дати до неї дійти. */
    const before = await transform(page);
    const box = await page.locator("#cv-flow-problems").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, 200);
    await page.waitForTimeout(500);
    assert.ok(await page.evaluate(() =>
      document.getElementById("cv-flow-problems").scrollTop) > 0,
      "колесо над панеллю не прокрутило перелік");
    assert.equal(await transform(page), before,
      "колесо над панеллю скарг зумить полотно замість прокрутки переліку");
    await page.close();
  });

  await t.test("I. флоу-вид: смуги, «не у флоу», скарги і підпис як ТЕКСТ", async () => {
    /* Підпис вузла — єдине місце канваса, куди текст приходить із файла, який
       пишуть РУКАМИ. Тому він тут із розміткою: `esc()` на підписі картки досі не
       перевіряло ніщо (дірка, знайдена мутаційно у 8a), а мовчазне виконання
       `<img onerror>` із `flow.json` — це вже не косметика.

       Дві смуги з ОДНАКОВИМ id вузла («n1») — навмисно: `readFlow` вимагає
       унікальності id лише В МЕЖАХ смуги, тож спільна мапа «id → кадр» на всі
       смуги склеїла б їх в один DOM-елемент. `appendChild` не копіює, а ПЕРЕНОСИТЬ,
       і кадр просто зник би з першої смуги. */
    const LABEL = '<img src=x onerror="document.title=\'ЗЛАМАНО\'">Порожньо & <b>жирно</b>';
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f1", title: "Пошук закону", nodes: [
        { id: "n1", page: "holovna" },
        { id: "n2", page: "poshuk", label: LABEL },
        // Стан того самого екрана: свій ключ кадру, а знімка в нього нема — саме
        // це відрізняє `key: node.key` від `key: node.page` у `cardEl`.
        { id: "n4", page: "holovna", state: { state: "empty" } },
        // Вузол на сторінку, якої нема: мусить бути ВИДНО в переліку, а не в консолі.
        { id: "n3", page: "<b>nemaje</b>" },
      ], edges: [{ from: "n1", to: "n2", label: "шукає" }] },
      { id: "f2", title: "Друга <b>смуга</b>", nodes: [{ id: "n1", page: "holovna" }], edges: [] },
    ] }));

    /* Власна навігація, без `overview()`: після H найновіша ітерація it2 лишилась
       БЕЗ жодного кадру, а обирається за замовчуванням саме вона — спільний хелпер
       чекав би `.cv-card img`, якого там не буде ніколи, і 30 секунд таймауту
       виглядали б як провал фічі. Тому ітерацію обираємо явно. */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });

    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });

    // Смуга на кожен сценарій, із підписом. Смуга нульової ширини (`width:100%`
    // на абсолютному `#world`) невидима, тому ширину теж питаємо.
    assert.equal(await page.locator(".cv-band").count(), 2, "смуга на кожен сценарій");
    // Підпис смуги — теж рядок із файла, який пишуть руками, тому теж ТЕКСТОМ.
    assert.deepEqual(
      await page.locator(".cv-band-title").allTextContents(),
      ["Пошук закону", "Друга <b>смуга</b>"]);
    const bandW = await page.locator(".cv-band").first()
      .evaluate((el) => el.getBoundingClientRect().width);
    assert.ok(bandW > 0, `смуга нульової ширини (${bandW}px) — її не видно`);

    /* Підкладка мусить бути РАМКОЮ навколо кадрів, а не обведенням по їхньому
       габариту: дизайнер попросив «пікселів по 100 або більше» згори й знизу
       (25.08.2026), і живі числа зараз — 200 з боків, 240 згори, 200 знизу
       (`canvas-geom.js`). Міряємо не самі числа, а те, що поле Є з усіх боків:
       перевірка, яка повторює константу, ламається на кожній зміні смаку, а
       підкладка по габариту — це та сама помилка, від якої правка й лікує.

       Друге твердження — не косметика зовсім: між смугами мусить лишатись ЩІЛИНА.
       Поля розсовують підкладку назовні, а відстань між смугами дає розкладка — і
       поки вона була жорстким `gap * 2`, поля сусідніх смуг спершу перекривались
       (на полях 240/200 — накладка 40px, виміряно на демо-графі блогу), а після
       зменшення полів лишали між підкладками 40px, тобто 2px екрана на bird-view:
       дві смуги читались одним блоком. Тому відстань стала параметром
       (`bandGap`), і саме її тут і стережемо. */
    const pads = await page.evaluate(() => {
      const rect = (el) => el.getBoundingClientRect();
      return [...document.querySelectorAll(".cv-band")].map((band) => {
        const b = rect(band);
        const own = [...document.querySelectorAll("#world .cv-card")]
          .map(rect)
          .filter((c) => c.top >= b.top && c.bottom <= b.bottom);
        return {
          scale: +document.getElementById("world").style.transform
            .match(/scale\(([\d.]+)\)/)[1],
          band: { top: b.top, bottom: b.bottom },
          l: Math.min(...own.map((c) => c.left - b.left)),
          r: Math.min(...own.map((c) => b.right - c.right)),
          t: Math.min(...own.map((c) => c.top - b.top)),
          b: Math.min(...own.map((c) => b.bottom - c.bottom)),
        };
      });
    });
    for (const [i, pad] of pads.entries()) {
      for (const side of ["l", "r", "t", "b"]) {
        const world = pad[side] / pad.scale;
        assert.ok(world > 40,
          `смуга ${i}: поле ${side} — ${world.toFixed(0)}px світу, підкладка йде по габариту кадрів`);
      }
    }
    /* Підпис смуги мусить лежати ПОВЕРХ кадрів. На дрібному зумі кегль у нього
       великий (див. Z), і коробка неминуче накриває верх першого кадру — а поки
       підпис жив усередині підкладки, тобто ПЕРЕД кадрами в DOM, кадр зʼїдав його
       хвіст: на демо-графі блогу з «Читач шукає статтю» лишалось «Читач шукає ст»
       (знайдено оком, 25.08.2026). Порядок у DOM і невідʼємний z-index — це рівно
       те, чим у CSS вирішується, хто поверх кого, коли обидва абсолютні. */
    const layer = await page.evaluate(() => {
      const kids = [...document.getElementById("world").children];
      const title = kids.findIndex((el) => el.classList.contains("cv-band-title"));
      /* Кадри СМУГ, а не всі: рядок «не у флоу» додається після підписів (він під
         смугами й накрити підпис не може ніяк), і рахувати його тут означало б
         вимагати порядку, який нічого не стереже. */
      const lastCard = kids.reduce((at, el, i) => (el.classList.contains("cv-card")
        && !el.classList.contains("cv-orphan") ? i : at), -1);
      return { title, lastCard,
               z: getComputedStyle(kids[title]).zIndex };
    });
    assert.ok(layer.title > layer.lastCard,
      `підпис смуги (${layer.title}) малюється раніше за кадр (${layer.lastCard}) — кадр його накриє`);
    assert.ok(layer.z === "auto" || Number(layer.z) >= 0,
      `підпис смуги задвинуто під кадри z-index-ом (${layer.z})`);

    for (let i = 1; i < pads.length; i += 1) {
      const between = (pads[i].band.top - pads[i - 1].band.bottom) / pads[i].scale;
      assert.ok(between > 100,
        `між смугами ${i - 1} і ${i} лишилось ${between.toFixed(0)}px світу — `
        + 'підкладки злиплись в одну пляму');
    }

    /* Кадри стоять ТАМ, ДЕ СКАЗАЛА чиста розкладка. Третій кадр — це стан, ранг 0,
       тобто ліва колонка під першим. Сіткова розкладка (якщо `relayoutAll()`
       забуде розвилку по виду) поставила б кадри РЯДАМИ СТОРІНОК — стан поруч зі
       своєю сторінкою — і без зсуву на поле смуги, тобто від нуля світу. */
    const lefts = await page.locator(".cv-card:not(.cv-orphan)")
      .evaluateAll((els) => els.map((el) => el.style.left));
    assert.deepEqual(lefts, [colX(0), colX(1), colX(0), colX(0)],
      "граф розкладено не чистою розкладкою флоу");

    /* Ключ кадру = сторінка+стан: у вузла-стану свого знімка нема, і він мусить
       чесно сказати про це заглушкою. З `key: node.page` він узяв би кадр
       звичайної «Головної» і мовчки показав не той екран. */
    assert.equal(await page.locator(".cv-card:not(.cv-orphan) .cv-card-ph").count(), 1);

    /* «Вписати все» мусить вписати САМЕ ВСЕ: смуги з лейнами під стрілки, підпис
       над першою смугою і рядок «не у флоу» під ними. Габарит, порахований по
       самих кадрах (як пропонував план), зрізав би камерою і підпис зверху, і
       лейни знизу — тобто рівно те місце, куди Task 9 малює стрілки. */
    const outside = await page.evaluate(() => {
      const box = document.getElementById("canvas").getBoundingClientRect();
      return [...document.querySelectorAll("#world *")].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.left < box.left - 1 || r.top < box.top - 1
          || r.right > box.right + 1 || r.bottom > box.bottom + 1;
      }).map((el) => `${el.className}@${Math.round(el.getBoundingClientRect().top)}`);
    });
    assert.deepEqual(outside, [], "«вписати все» лишило частину графа за краєм");

    // Сторінка поза графом не зникає з полотна, а йде окремою групою.
    assert.equal(await page.locator(".cv-orphans-title").textContent(), "не у флоу — 1");
    /* Підписи мусять лежати В ОДИН рядок. `#world` спозиційований абсолютно і
       ширини не має, тож без `white-space:nowrap` кожне слово переноситься на
       свій рядок, підпис стає вузьким стовпчиком і сповзає на кадри під ним —
       саме так це й виглядало до правки. */
    const tall = await page.locator(".cv-band-title, .cv-orphans-title")
      .evaluateAll((els) => els.filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width <= r.height;
      }).map((el) => el.textContent));
    assert.deepEqual(tall, [], "підпис перенесло на кілька рядків");
    assert.equal(await page.locator(".cv-orphan").count(), 1);
    assert.ok((await page.locator(".cv-orphan .cv-card-head").textContent()).includes("Нова"));

    // Викинуте `readFlow` мусить бути ВИДНО, а не лежати в консолі.
    await page.locator("#cv-flow-problems").waitFor({ state: "visible", timeout: 10000 });
    const problems = await page.locator("#cv-flow-problems").textContent();
    // Ім'я зниклої сторінки приходить із того самого файла — і в перелік теж
    // мусить лягти текстом, а не розміткою.
    assert.ok(problems.includes("<b>nemaje</b>"), `перелік не називає вузол: ${problems}`);

    /* Підпис із файла — ТЕКСТОМ. Три твердження, бо кожне ловить своє: текст
       цілий (розмітку не з'їв парсер), тега в голові немає (її не виконали),
       заголовок документа не змінився (`onerror` не вистрілив). */
    const head = await page.locator(".cv-card:not(.cv-orphan) .cv-card-head").nth(1)
      .textContent();
    assert.ok(head.includes(LABEL), `підпис показано не текстом: ${head}`);
    assert.equal(await page.locator(".cv-card-head img, .cv-card-head b").count(), 0,
      "розмітку з flow.json виконано, а не показано");
    assert.notEqual(await page.title(), "ЗЛАМАНО");

    /* Назад у сітку: смуг і кадрів «не у флоу» більше немає.

       А ось СКАРГИ лишаються, і це зміна після ревʼю: вони про `flow.json`, а не
       про вид. У сітці свій `readFlow` канвас не кличе, тож перелік тримається на
       скаргах серверної перевірки — і зникав разом із видом, забираючи єдину
       причину для того, хто дивиться на сітку (а лічильник «Перезняти» рахує при
       цьому той самий граф). Те, за чим стояла колишня перевірка «у сітці
       порожньо» — що перелік не переїжджає на ЧУЖИЙ граф, — тримає I1.

       Чекаємо саме зникнення смуг, а не `.cv-card img`: `render()` асинхронний,
       а кадри флоу-виду теж картинки — локатор знайшов би СТАРІ й перевірка
       читала б холст, який ще не перебудували. */
    await page.getByRole("button", { name: /Сітка/ }).click();
    await page.waitForFunction(() => !document.querySelector(".cv-band")
      && document.querySelector("#world .cv-card"), null, { timeout: 10000 });
    assert.equal(await page.locator("#cv-flow-problems").isVisible(), true,
      "перелік скарг зник разом із видом, хоч скаржиться він на файл");
    assert.match(await page.locator("#cv-flow-problems").textContent(), /nemaje/,
      "у сітці перелік більше не називає, який вузол викинуто");
    assert.equal(await page.locator(".cv-orphan").count(), 0);
  });

  await t.test("I2. «Відкрити» на вузлі зі станом веде в ТОЙ САМИЙ стан", async () => {
    /* Кадр вузла-стану знімається під ВЛАСНИМ ключем (`сторінка~хеш`), і саме цей
       ключ лежав у `cards[].id`. Поки `openCard` клав його в `pickedPage`, такої
       сторінки не існувало: `loadPages()` мовчки скидала вибір на першу — кадр
       показував одне, живий вид інше. Нічого не падало, тому перевірка окрема.

       Селектор `.cv-band .cv-card` (як стояв у плані) тут не працює: кадри лежать
       у `#world` зі світовими координатами, а смуга їм СУСІД, а не батько —
       вкладеного кадру в неї немає жодного. Адресуємо кадр підписом вузла. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f", title: "Пошук", nodes: [
        { id: "n1", page: "holovna" },
        { id: "n2", page: "poshuk", state: { state: "empty" },
          label: "Нічого не знайдено" },
      ], edges: [{ from: "n1", to: "n2", label: "коли не знайшлось" }] },
    ] }));

    /* Власна навігація, не `overview()`: після H найновіша ітерація it2 лишилась
       без жодного кадру, а обирається за замовчуванням саме вона — хелпер чекав би
       `.cv-card img` до таймауту, і це виглядало б як провал фічі. */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });

    const card = page.locator(".cv-card").filter({ hasText: "Нічого не знайдено" });
    assert.equal(await card.count(), 1, "кадр вузла-стану адресується неоднозначно");

    // Натискання СПРАВЖНЄ, як в A: холст бере pointer capture, і програмний клік
    // ішов би не тим шляхом, ніж рука.
    await press(page, card.locator(".cv-open"));

    const srcHas = (re) => page.waitForFunction((rx) => new RegExp(rx).test(
      document.getElementById("frame")?.getAttribute("src") || ""), re, { timeout: 5000 });
    try {
      // І сторінка, І стан: половина відповіді тут гірша за жодної.
      await srcHas("[?&]page=poshuk(&|$)");
      await srcHas("[?&]state=empty(&|$)");
    } catch (e) {
      assert.fail("iframe відкрив не той екран, що на кадрі: "
        + await page.locator("#frame").getAttribute("src"));
    }

    /* Панель мусить підсвітити ТУ САМУ сторінку. Інакше вибір у панелі й вміст
       iframe розходяться, і незрозуміло, що ти зараз правиш. */
    assert.equal(await page.locator(".row--sel .row-name").textContent(), "Пошук");

    /* Стан не сміє ПРИЛИПАТИ до наступного вибору. Клік по тому самому рядку
       панелі — найгостріший випадок: сторінка не змінилась, тож охорона «скинути
       стан, коли змінилась сторінка» тут не спрацює зовсім, а дизайнер, що клікнув
       «Пошук», чекає звичайний пошук, а не «нічого не знайдено». */
    await page.locator('.row[data-page="poshuk"]').click();
    await page.waitForFunction(() => {
      const src = document.getElementById("frame")?.getAttribute("src") || "";
      return /[?&]page=poshuk(&|$)/.test(src) && !/state=empty/.test(src);
    }, null, { timeout: 5000 });
  });

  await t.test("I3. «Відкрити» в СІТЦІ бере свій кадр і без чужого стану", async () => {
    /* Дві речі одним рухом, бо історія одна: у сітці «Відкрити» мусить відкрити
       ТОЙ кадр, по якому клікнули, і без стану, що лишився від флоу.

       Перевірок A-C для цього не досить, і це виміряно: прибери `page` із запису
       сіткової картки — усі три лишаються зелені. Кожна тисне ПЕРШИЙ кадр і чекає
       `holovna`, а `openCard` з биттям кладе в `pickedPage` `undefined`, після чого
       `loadPages()` мовчки скидає вибір на першу сторінку — знов на `holovna`.
       Тобто найгучніший спосіб зламати кнопку не видно жодній із них.

       Тут же ловиться і прилипання стану на іншому шляху, ніж в I2: не через
       панель, а через повернення в «Огляд» і перемикання виду. */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });

    // Спершу набираємо стан: flow.json від I2 лежить на місці.
    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });
    await press(page, page.locator(".cv-card").filter({ hasText: "Нічого не знайдено" })
      .locator(".cv-open"));
    await page.waitForFunction(() => /state=empty/.test(
      document.getElementById("frame")?.getAttribute("src") || ""), null, { timeout: 5000 });

    // Назад у «Огляд» і в сітку.
    await toOverview(page).click();
    await page.getByRole("button", { name: /Сітка/ }).click();
    await page.waitForFunction(() => !document.querySelector(".cv-band")
      && document.querySelector("#world .cv-card"), null, { timeout: 10000 });

    // Другий кадр сітки — «Пошук». Саме НЕ перший: на першому мовчазний відкат
    // `loadPages()` дає ту саму відповідь, що й справна кнопка.
    await press(page, page.locator(".cv-card").filter({ hasText: "Пошук" }).locator(".cv-open"));
    await page.waitForFunction(() => {
      const src = document.getElementById("frame")?.getAttribute("src") || "";
      return /[?&]page=poshuk(&|$)/.test(src) && !/state=empty/.test(src);
    }, null, { timeout: 5000 });
  });
  await t.test("J. стрілки не відклеюються від кадрів на зумі й пані", async () => {
    /* Свій `flow.json`: три вузли в ряд дають І пряме ребро (сусідні колонки),
       І довге (через дві) — це різні гілки розкладки, і малюються вони різними
       шляхами. `nova` знімка не має ще з G, тож третій кадр — заглушка; для
       геометрії це байдуже, а різні висоти кадрів навіть корисні: пряме ребро
       між різновисокими кадрами похиле, і промах повз край видно одразу. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f", title: "Пошук закону", nodes: [
        { id: "n1", page: "holovna" },
        { id: "n2", page: "poshuk" },
        { id: "n3", page: "nova" },
      ], edges: [
        { from: "n1", to: "n2", label: "шукає" },
        { from: "n2", to: "n3", label: "відкриває" },
        // Через дві колонки: вниз, лейном під смугою і вгору у нижній край цілі.
        { from: "n1", to: "n3", label: "одразу" },
      ] },
    ] }));

    /* Власна навігація, не `overview()`: після H найновіша ітерація it2 лишилась
       без жодного кадру, а обирається саме вона — хелпер чекав би `.cv-card img`
       до таймауту, і це виглядало б як провал фічі. */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });
    /* `attached`, а не `visible`: у горизонтальної лінії габаритний прямокутник
       нульової висоти, і Playwright вважає її схованою, хоч намальована вона
       звичайнісінько. Наконечник — інша річ, у нього є справжня площа, і його
       видимість нижче питаємо вже прямо. */
    await page.locator(".cv-edge").first().waitFor({ state: "attached", timeout: 10000 });

    // Стрілка на КОЖЕН перехід і підпис на кожне назване ребро: граф, який
    // домальовує половину переходів, читається як повний і бреше.
    assert.equal(await page.locator(".cv-edge").count(), 3, "стрілка не на кожен перехід");
    // Без наконечника лінія не каже, КУДИ веде перехід, — це вже не граф.
    assert.equal(await page.locator(".cv-arrow").count(), 3, "ребро без наконечника");
    assert.ok(await page.locator(".cv-arrow").first().isVisible(), "наконечник не намалювався");
    assert.deepEqual(await page.locator(".cv-edges text").allTextContents(),
      ["шукає", "відкриває", "одразу"], "підписи ребер загубились");

    /* Стик «стрілка → кадр» міряємо НА ЕКРАНІ, а не по числах із `d` і
       `style.left`. Світові числа рівні між собою й тоді, коли шар стрілок висить
       ПОЗА `#world` і трансформу світу не бере зовсім — тобто перевірка, написана
       по них (як пропонував план), лишається зеленою рівно в тому випадку, від
       якого мусить стерегти. Екранні координати беремо в самого браузера:
       `getScreenCTM()` враховує CSS-трансформ предків. */
    const gap = () => page.evaluate(() => {
      const p = document.querySelector(".cv-edge");
      const end = p.getPointAtLength(p.getTotalLength()).matrixTransform(p.getScreenCTM());
      // Кадр цілі першого ребра — другий у смузі (кадри лежать у `#world`, смуга
      // їм сусід, а не батько, тож `.cv-band .cv-card` не знайшов би нічого).
      const r = document.querySelectorAll("#world .cv-card")[1].getBoundingClientRect();
      return { dx: end.x - r.left, dy: end.y - (r.top + r.height / 2),
               t: document.getElementById("world").style.transform };
    });
    const near = (g, when) => assert.ok(Math.abs(g.dx) < 2 && Math.abs(g.dy) < 2,
      `${when}: кінець стрілки за ${g.dx.toFixed(1)}×${g.dy.toFixed(1)}px від краю кадру`);

    const fit = await gap();
    near(fit, "у «вписати все»");

    /* Підпис мусить триматись СВОЄЇ лінії. Друге ребро похиле — кадр «Нова»
       знімка не має і нижчий за сусіда, — а план ставив підпис по `y` ПОЧАТКУ
       відрізка, тобто відносив його від лінії на піврізниці висот. Міряємо у
       світових координатах (екранні залежали б від зуму): беремо середину лінії
       і повертаємо низ підпису в ту саму систему зворотною матрицею. */
    const stray = await page.evaluate(() => {
      const p = document.querySelectorAll(".cv-edge")[1];
      const mid = p.getPointAtLength(p.getTotalLength() / 2);
      const r = document.querySelectorAll(".cv-edges text")[1].getBoundingClientRect();
      const low = new DOMPoint(r.left + r.width / 2, r.bottom)
        .matrixTransform(p.getScreenCTM().inverse());
      return { dx: low.x - mid.x, dy: mid.y - low.y };
    });
    assert.ok(Math.abs(stray.dx) < 40,
      `підпис поїхав уздовж лінії на ${stray.dx.toFixed(0)}px світу`);
    assert.ok(stray.dy > 0 && stray.dy < 40,
      `підпис лежить не над своєю лінією, а за ${stray.dy.toFixed(0)}px світу від неї`);

    /* І підпис ДОВГОГО ребра (третє: через дві колонки). У нього ШІСТЬ точок —
       бік джерела, зазор, лейн під смугою, зазор, бік цілі, — і назвати він
       мусить саме лейн. На стояку підпис висів би за сотні px убік від лінії,
       яку називає.

       Доказу цьому не було зовсім: мутація `const long = false` лишала всі 25
       живих перевірок зеленими — пряме ребро (індекс 1) міряє `stray` вище, а до
       довгого не дотягувався ніхто. Тому точки беремо з самого `d`: вибір
       відрізка в `app.js` — це індекс, і перевіряти треба саме індекс.

       Лейн шукаємо САМІ, найнижчим горизонтальним відрізком шляху, а не тим
       самим індексом, що в `app.js`: перевірка, яка повторює арифметику коду,
       зеленіє разом із будь-якою його помилкою. */
    const longLabel = await page.evaluate(() => {
      const p = document.querySelectorAll(".cv-edge")[2];
      const pts = p.getAttribute("d").match(/-?[\d.]+,-?[\d.]+/g)
        .map((s) => s.split(",").map(Number));
      const r = document.querySelectorAll(".cv-edges text")[2].getBoundingClientRect();
      const low = new DOMPoint(r.left + r.width / 2, r.bottom)
        .matrixTransform(p.getScreenCTM().inverse());
      return { pts, x: low.x, y: low.y };
    });
    assert.ok(longLabel.pts.length >= 6,
      `третє ребро не йде зазорами, перевіряти нічого: ${JSON.stringify(longLabel.pts)}`);
    const segs = longLabel.pts.slice(1).map((q, i) => [longLabel.pts[i], q]);
    // Лейн — єдиний горизонтальний відрізок ПІД смугою, тобто найнижчий із них.
    const lane = segs.filter(([u, v]) => u[1] === v[1])
                     .reduce((low, seg) => (seg[0][1] > low[0][1] ? seg : low));
    const laneMidX = (lane[0][0] + lane[1][0]) / 2;
    const laneY = lane[0][1];
    assert.ok(Math.abs(longLabel.x - laneMidX) < 60,
      `підпис довгого ребра не на середині лейна: ${longLabel.x.toFixed(0)} проти `
      + `${laneMidX.toFixed(0)} світу`);
    assert.ok(laneY - longLabel.y > 0 && laneY - longLabel.y < 40,
      `підпис довгого ребра за ${(laneY - longLabel.y).toFixed(0)}px світу від свого лейна`);

    const box = await page.locator("#canvas").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await zoomWheel(page, 0, -240);
    await page.waitForTimeout(900);            // довше за життя циклу камери
    const zoomed = await gap();
    // Не порожня перевірка: камера справді поїхала, отже стик міряємо на іншому зумі.
    assert.notEqual(zoomed.t, fit.t, "колесо мусить змінювати трансформ");
    near(zoomed, "після зуму");

    // І пан: кадри й стрілки мусять їхати одним рухом, а не двома.
    // Поза кнопкою «Вмістити все» (вона з 0.25.0 ловить вказівник у лівому нижньому куті).
    await page.mouse.move(box.x + 24, box.y + box.height - 100);
    await page.mouse.down();
    await page.mouse.move(box.x + 220, box.y + box.height - 200, { steps: 8 });
    await page.mouse.up();
    const panned = await gap();
    assert.notEqual(panned.t, zoomed.t, "драг мусить зсувати трансформ");
    near(panned, "після пані");

    /* Ціна життя у світі: товщина лінії масштабується разом із ним. Без
       `non-scaling-stroke` на 6% зумі стрілка тонша за піксель і зникає, а на
       250% стає брусом. */
    assert.equal(await page.evaluate(() =>
      getComputedStyle(document.querySelector(".cv-edge")).vectorEffect),
      "non-scaling-stroke", "лінію не виведено з-під масштабу світу");

    /* Підпис мусить стояти НА ПЛАШЦІ — суцільній підкладці з заокругленням, а не
       в «гало» з товстого обведення (`paint-order:stroke`), яке стояло тут до
       раунду правок 25.08.2026. Обведення лишає між літерами просвіти фону, і на
       кадрі підпис читається плямами; дизайнер попросив плашку.

       Стара перевірка вимагала рівно гало (`paint-order` + товщина ≥ 4px) —
       тобто СУПЕРЕЧИЛА новій вимозі. Знято свідомо, а не «підігнано»: вимога
       змінилась, і разом із нею змінилось, що саме тут доводиться.

       Міряємо ГЕОМЕТРІЄЮ, а не наявністю тега: плашка, менша за текст, і плашка
       поверх тексту виглядають у розмітці однаково правильно. */
    const plaque = await page.evaluate(() => {
      const text = document.querySelectorAll(".cv-edges text")[0];
      const rect = text.previousElementSibling;
      const ts = getComputedStyle(text);
      if (!rect || rect.tagName.toLowerCase() !== "rect") {
        return { tag: rect ? rect.tagName.toLowerCase() : null };
      }
      const t = text.getBBox(), r = rect.getBBox();
      const rs = getComputedStyle(rect);
      return {
        tag: "rect",
        pad: { l: t.x - r.x, r: (r.x + r.width) - (t.x + t.width),
               t: t.y - r.y, b: (r.y + r.height) - (t.y + t.height) },
        fill: rs.fill, opacity: parseFloat(rs.fillOpacity),
        rx: parseFloat(rect.getAttribute("rx") || "0"),
        // Текст мусить іти ПІСЛЯ плашки: у SVG пізніший малюється поверх.
        under: rect.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING ? 1 : 0,
        strokeW: ts.stroke === "none" ? 0 : parseFloat(ts.strokeWidth),
      };
    });
    assert.equal(plaque.tag, "rect", `під підписом не плашка, а ${plaque.tag}`);
    for (const [side, v] of Object.entries(plaque.pad)) {
      assert.ok(v > 2, `плашка обрізає підпис із боку ${side} (${v.toFixed(1)}px)`);
    }
    assert.notEqual(plaque.fill, "none", "плашка безбарвна — текст лягає просто на лінію");
    assert.ok(plaque.opacity > 0.85, `плашка напівпрозора (${plaque.opacity})`);
    assert.ok(plaque.rx > 0, "плашка без заокруглення");
    assert.equal(plaque.under, 1, "плашка намальована ПОВЕРХ свого ж підпису");
    assert.ok(plaque.strokeW < 2,
      `гало лишилось разом із плашкою (обведення ${plaque.strokeW}px)`);

    /* І плашка не сміє зʼїдати ЧУЖУ стрілку: у SVG порядок документа = порядок
       малювання, тож усі лінії й наконечники мусять стояти ПЕРЕД усіма плашками.
       Малювати підпис одразу за своїм ребром (як стояло до правки) означає, що
       наступне ребро прокреслює попередню плашку наскрізь. */
    const order = await page.evaluate(() => {
      const kids = [...document.querySelector(".cv-edges").children]
        .map((el) => el.tagName.toLowerCase());
      return { lastPath: kids.lastIndexOf("path"), firstRect: kids.indexOf("rect") };
    });
    assert.ok(order.firstRect > order.lastPath,
      `лінія №${order.lastPath} малюється поверх плашки №${order.firstRect}`);
  });

  /* Свій `flow.json` на K і L: два вузли в ряд (щоб колонка була ОДНА чужа, і
     промах по ній був видно) плюс `nova`, яка у графі не описана — тобто чесна
     група «не у флоу» для L. Пишемо ДО відкриття браузера. */
  const flowKL = () => writeFileSync(path.join(it1, "flow.json"), JSON.stringify({
    flows: [{ id: "f", title: "Пошук закону", nodes: [
      { id: "n1", page: "holovna" },
      { id: "n2", page: "poshuk" },
    ], edges: [{ from: "n1", to: "n2", label: "шукає" }] }],
  }));

  /** Флоу-вид it1 у свіжій вкладці. Своя навігація, не `overview()`: після H
      найновіша ітерація it2 лишилась БЕЗ кадрів, а обирається саме вона — хелпер
      чекав би `.cv-card img` до таймауту, і це виглядало б як провал фічі. */
  async function flowView() {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    // Та сама передумова, що в `gridView` — див. коментар там.
    await shotsSettled(page);
    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });
    return page;
  }

  /** Тягнути мишею з точки в точку — справжніми подіями, як в A/C. */
  async function dragFrom(page, [x1, y1], [x2, y2]) {
    await page.mouse.move(x1, y1);
    await page.mouse.down();
    await page.mouse.move(x2, y2, { steps: 12 });
    await page.mouse.up();
  }

  const flowFile = () => JSON.parse(readFileSync(path.join(it1, "flow.json"), "utf8"));
  /** Дочекатись, поки `pos` доїде НА ДИСК. Запис атомарний (`os.replace`), тож
      напівзаписаного файла тут не побачити — або старий, або новий. */
  async function posOnDisk2(flowId, nodeId) {
    for (let i = 0; i < 40; i += 1) {
      const flow = flowFile().flows.find((f) => f.id === flowId);
      const node = flow?.nodes.find((n) => n.id === nodeId);
      if (node?.pos) return node.pos;
      await new Promise((done) => setTimeout(done, 250));
    }
    return null;
  }
  const posOnDisk = (nodeId) => posOnDisk2("f", nodeId);

  await t.test("K. перетягнутий вузол лишається на місці після перезавантаження", async () => {
    /* Найдорожчий можливий баг тут — мовчазна втрата роботи дизайнера: він тягне
       вузол, бачить його на новому місці, а наступне перезавантаження все
       вертає. Тому перевірка доводить не «картка поїхала в DOM», а ТРИ речі:
       позиція доїхала НА ДИСК, вона записана позицією в колонці (`{col,row}`, не
       пікселем) і після перезавантаження кадр стоїть там, куди його поклали. */
    flowKL();
    const page = await flowView();
    const card = (name) => page.locator(".cv-card").filter({ hasText: name });
    const leftOf = (name) => card(name).evaluate((el) => el.style.left);

    /* Спершу — тіло кадру мусить лишитись ПАНОВОЮ поверхнею. Це основний жест
       холста: якби ручкою став увесь кадр, полотно не зсунути, ткнувши в кадр, а
       кадрами воно заповнене майже все. */
    const before = await transform(page);
    const body = await card("Головна").locator(".cv-card-body").boundingBox();
    await dragFrom(page, [body.x + body.width / 2, body.y + body.height / 2],
                   [body.x + body.width / 2 - 140, body.y + body.height / 2 - 70]);
    const panned = await transform(page);
    assert.notEqual(panned, before, "драг по тілу кадру мусить панувати полотно");
    assert.equal(await leftOf("Головна"), colX(0), "драг по тілу зсунув сам вузол");

    // А тепер за ГОЛОВУ — у чужу колонку, під сусідній вузол.
    const head = await card("Головна").locator(".cv-card-head").boundingBox();
    const target = await card("Пошук").boundingBox();
    // +30px від лівого краю: «Відкрити» висить на правому (`margin-left:auto`),
    // а зачепивши її, драг не почнеться зовсім.
    await dragFrom(page, [head.x + 30, head.y + head.height / 2],
                   [target.x + 30, target.y + target.height + 40]);

    /* Головне: позиція доїхала НА ДИСК — і саме позицією в колонці. Піксель тут
       був би тихою бомбою: перезнятий довший кадр зсунув би всі руками
       поставлені вузли, і робота пропала б без жодної помилки. */
    assert.deepEqual(await posOnDisk("n1"), { col: 1, row: 1 },
      `на диску не та позиція: ${JSON.stringify(flowFile().flows[0].nodes[0])}`);

    /* Камера мусить лишитись ТАМ, ДЕ її поставила рука. `saveNodePos`
       перемальовує холст, а перемальовка кінчається `fitAll()` — без окремого
       відновлення полотно стрибало б у «вписати все» після кожного драгу, рівно
       посеред розкладання графа. */
    await page.waitForFunction(() => document.getElementById("cv-toast")
      ?.classList.contains("show"), null, { timeout: 10000 });
    assert.equal(await transform(page), panned, "холст стрибнув після збереження");

    // І перевірка, за якою вся ця задача: ПЕРЕЗАВАНТАЖЕННЯ.
    const page2 = await flowView();
    const card2 = (name) => page2.locator(".cv-card").filter({ hasText: name });
    const box = async (name) => card2(name).evaluate((el) =>
      ({ left: el.style.left, top: parseFloat(el.style.top) }));
    const moved = await box("Головна");
    const stay = await box("Пошук");
    // Друга колонка. Ранг поставив би вузол у нульову.
    assert.equal(moved.left, colX(1), "вузол вернувся в колонку рангу");
    assert.equal(stay.left, colX(1), "сусід мусить лишитись у своїй колонці");
    assert.ok(moved.top > stay.top,
      `ряд не пережив перезавантаження: ${moved.top} мусив бути нижче за ${stay.top}`);
  });

  await t.test("O. зум і одразу драг: вузол не їде разом із камерою", async () => {
    /* Живий цикл камери пише `cvx/cvy/cvscale` кадр за кадром. Якщо його не
       вбити на `pointerdown`, то під час драгу світ ще їде до старої цілі —
       кадр тікає з-під курсора, лягає не в ту колонку, і на диск іде саме та,
       НЕ ТА позиція. Зумимо РІВНО під курсором (`zoomAt` тримає точку під ним
       на місці, тож ручка з-під нього не тікає) і тиснемо одразу, не чекаючи. */
    const page = await flowView();
    const head = await page.locator(".cv-card").filter({ hasText: "Головна" })
      .locator(".cv-card-head").boundingBox();
    const grab = [head.x + 30, head.y + head.height / 2];
    await page.mouse.move(grab[0], grab[1]);
    await zoomWheel(page, 0, -240);
    await page.mouse.down();                       // ЖОДНОГО чекання: цикл ще їде
    const atDown = await transform(page);
    await page.mouse.move(grab[0] + 40, grab[1] + 15);
    await page.waitForTimeout(500);                // помітна частина життя циклу
    await page.mouse.move(grab[0] + 80, grab[1] + 30);
    assert.equal(await transform(page), atDown,
      "цикл камери не вбито: світ їде під час драгу вузла");
    await page.mouse.up();
    /* Не порожня перевірка: кадр справді тягнеться, а не стоїть. Порівнюємо з
       ЙОГО домом (`colX(0)`), а не з нулем: вміст флоу зсунутий на поле смуги, тож
       «не нуль» стало б правдою і для кадру, який не рухався зовсім. */
    assert.notEqual(await page.locator(".cv-card").filter({ hasText: "Головна" })
      .evaluate((el) => el.style.left), colX(0), "кадр не поїхав зовсім");
  });

  await t.test("O2. скасований жест не лишає вузол у руці", async () => {
    /* `pointercancel` — системний свайп, вирване вікно, втрачений вказівник. Ручку
       він мусить відпустити: інакше наступний рух мишею БЕЗ кнопки тягне кадр, а
       `pointerup` пише позицію у файл — запис без жесту, тобто чужа робота на диску.

       Доказу цьому не було зовсім: мутація «прибрати рядок `pointercancel`»
       лишала всі 25 живих перевірок зеленими. Подію дзвонимо самі — системного
       скасування Playwright не вміє, а обробник дивиться лише на сам факт події.
       Мишу при цьому НЕ відпускаємо заздалегідь: справжній `pointerup` після
       скасування — це і є той шлях, яким позиція їхала на диск. */
    flowKL();
    const page = await flowView();
    const card = page.locator(".cv-card").filter({ hasText: "Головна" });
    const head = await card.locator(".cv-card-head").boundingBox();
    // +30px від лівого краю: «Відкрити» висить на правому, зачепивши її, драг не почнеться.
    const grab = [head.x + 30, head.y + head.height / 2];

    await page.mouse.move(grab[0], grab[1]);
    await page.mouse.down();
    await page.mouse.move(grab[0] + 120, grab[1] + 60, { steps: 6 });
    // Кадр справді в руці — інакше все нижче зелене задарма.
    const dragged = await card.evaluate((el) => el.style.left);
    // Дім кадру — колонка 0 зі зсувом на поле смуги, а не нуль світу.
    assert.notEqual(dragged, colX(0), "кадр не поїхав зовсім — жесту не було");

    await page.evaluate(() => document.getElementById("canvas")
      .dispatchEvent(new PointerEvent("pointercancel", { bubbles: true })));

    await page.mouse.move(grab[0] + 320, grab[1] + 200, { steps: 6 });
    assert.equal(await card.evaluate((el) => el.style.left), dragged,
      "після скасування кадр і далі їде за мишею");
    await page.mouse.up();

    /* І на диск не поїхало нічого: ні `pos`, ні тост «Позицію збережено». Тост
       перевіряємо теж, бо він означав би, що запит таки пішов — просто цього разу
       не долетів. */
    await page.waitForTimeout(1200);
    const n1 = flowFile().flows[0].nodes.find((n) => n.id === "n1");
    assert.equal(n1.pos, undefined,
      `позиція доїхала на диск без жесту: ${JSON.stringify(n1)}`);
    assert.equal(await page.evaluate(() => document.getElementById("cv-toast")
      ?.classList.contains("show") ?? false), false,
      "після скасованого жесту канвас звітує про збереження");
  });

  await t.test("L. де ручки немає: сітка пане, а «не у флоу» каже про це вголос", async () => {
    const page = await flowView();

    /* 1. У СІТЦІ голова кадру — звичайна пановна поверхня: `pos` там не має
       сенсу взагалі, кадри розкладає `rowsLayout` рядами сторінок. Без умови
       `canvasView === 'flow'` голова тягла б вузол і в сітці, а `saveNodePos`
       писав би туди `pos`, якого ніхто не читає. */
    await page.getByRole("button", { name: /Сітка/ }).click();
    await page.waitForFunction(() => !document.querySelector(".cv-band")
      && document.querySelector("#world .cv-card"), null, { timeout: 10000 });
    const gridCard = page.locator("#world .cv-card").first();
    const before = await transform(page);
    const gh = await gridCard.locator(".cv-card-head").boundingBox();
    const left0 = await gridCard.evaluate((el) => el.style.left);
    await dragFrom(page, [gh.x + 30, gh.y + gh.height / 2],
                   [gh.x + 30 - 160, gh.y + gh.height / 2 + 90]);
    assert.notEqual(await transform(page), before,
      "у сітці голова кадру мусить панувати полотно");
    assert.equal(await gridCard.evaluate((el) => el.style.left), left0,
      "у сітці драг за голову зсунув сам кадр");

    /* 2. Кадр із групи «не у флоу» у графі не описаний — позицію писати НЕМА
       КУДИ. Тихий тост «Позицію збережено» тут був би найгіршим із можливих:
       кадр вернеться на місце після перемальовки, а дизайнер не дізнається чому. */
    await page.getByRole("button", { name: /Флоу/ }).click();
    await page.locator(".cv-band").first().waitFor({ timeout: 10000 });
    const orphan = page.locator(".cv-orphan").first();
    const wasFile = readFileSync(path.join(it1, "flow.json"), "utf8");
    const oh = await orphan.locator(".cv-card-head").boundingBox();
    await dragFrom(page, [oh.x + 30, oh.y + oh.height / 2],
                   [oh.x + 30 + 180, oh.y + oh.height / 2 - 60]);
    await page.waitForFunction(() => {
      const t = document.getElementById("cv-toast");
      return t?.classList.contains("show") && /не у флоу/.test(t.textContent);
    }, null, { timeout: 10000 });
    assert.equal(readFileSync(path.join(it1, "flow.json"), "utf8"), wasFile,
      "драг кадру поза графом переписав flow.json");
    // Перемальовка мусила вернути кадр на його місце в рядку «не у флоу» — тобто
    // в перший стовпчик, зсунутий на те саме поле, що й кадри смуг.
    await page.waitForFunction((home) => {
      const el = document.querySelector(".cv-orphan");
      return el && el.style.left === home;
    }, colX(0), { timeout: 10000 });
  });

  await t.test("N. той самий екран у двох сценаріях: драг чіпає лише свою смугу",
               async () => {
    /* Одна сторінка в двох сценаріях — річ звичайна (той самий вхід у двох
       історіях). Драг мусить лягти В СВІЙ вузол: пошук вузла по ключу кадру в
       усіх смугах (як у плані) писав би `pos` у кожну, і поїхав би заодно кадр,
       якого дизайнер не торкався. Ряд тут теж показовий: кадри лежать у спільному
       `#world`, тож без звірки смуги «вище» лічився б і вузол ПЕРШОЇ смуги — ряд
       вийшов би 1 замість 0. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f1", title: "Перший", nodes: [
        { id: "n1", page: "holovna" }, { id: "n2", page: "poshuk" },
      ], edges: [{ from: "n1", to: "n2" }] },
      { id: "f2", title: "Другий", nodes: [{ id: "n1", page: "holovna" }], edges: [] },
    ] }));
    const page = await flowView();
    const holovna = page.locator(".cv-card").filter({ hasText: "Головна" });
    assert.equal(await holovna.count(), 2, "той самий екран мусить бути в обох смугах");

    /* Тягнемо кадр ДРУГОЇ смуги (у DOM смуги йдуть по порядку) у другу колонку.
       Цільовий x беремо з кадру «Пошук» першої смуги — він саме там і стоїть, а
       рахувати піксель від масштабу камери було б крихко. */
    const head = await holovna.nth(1).locator(".cv-card-head").boundingBox();
    const col1 = await page.locator(".cv-card").filter({ hasText: "Пошук" }).boundingBox();
    await dragFrom(page, [head.x + 30, head.y + head.height / 2],
                   [col1.x + 30, head.y + head.height / 2]);

    assert.deepEqual(await posOnDisk2("f2", "n1"), { col: 1, row: 0 },
      "ряд порахований по чужій смузі або колонка не та");
    const first = flowFile().flows[0].nodes.find((n) => n.id === "n1");
    assert.equal(first.pos, undefined,
      `драг переставив вузол ЧУЖОЇ смуги: ${JSON.stringify(first)}`);
  });

  await t.test("M. збій запису кричить у канвасі, а не гасне тостом", async () => {
    /* Помилку диска сервер віддає ТІЛОМ `{ok:false, error}` зі СТАТУСОМ 200 —
       навмисно, щоб канвас показав причину, а не «мережа впала». Отже `post` на
       ній не кидає, і код, який спирається лише на `catch` (як у плані), показав
       би «Позицію збережено» там, де на диску лишився старий граф. Це найдорожчий
       баг цієї фічі: кадр стоїть на новому місці, наступне перезавантаження все
       вертає, а причини дизайнер не дізнається.

       Тому ламаємо запис по-справжньому — знімаємо з теки ітерації право писати. */
    flowKL();
    const page = await flowView();
    /* Гучно — але НЕ діалогом браузера. `alert()` вимикається тією ж галочкою,
       що й `prompt()` (причина — у шапці `app/ask.js`), і після неї не показує
       нічого; на цьому повідомленні ціна найвища — воно про втрачену роботу.
       Заміна — `tell()`, той самий оверлей канваса. */
    const dialogs = [];
    page.on("dialog", (d) => { dialogs.push(d.message()); d.dismiss(); });
    const wasFile = readFileSync(path.join(it1, "flow.json"), "utf8");
    chmodSync(it1, 0o500);
    try {
      const head = await page.locator(".cv-card").filter({ hasText: "Головна" })
        .locator(".cv-card-head").boundingBox();
      await dragFrom(page, [head.x + 30, head.y + head.height / 2],
                     [head.x + 330, head.y + head.height / 2 + 90]);
      /* Спершу даємо ОБОМ шляхам відпрацювати, тоді перевіряємо діалог, і лише
         потім чекаємо поле. З `alert()` у коді оверлея не буде ніколи, і єдиним
         слідом лишився б таймаут — факт без причини. */
      const said = page.locator(".cv-ask p");
      await said.waitFor({ timeout: 10000 }).catch(() => {});
      assert.deepEqual(dialogs, [], "збій запису пішов у діалог браузера, а не в канвас");
      await said.waitFor({ timeout: 3000 });
      const text = await said.textContent();
      assert.match(text, /Позиція не збереглась/);
      // І причина в тексті, а не «щось не так»: лагодити доведеться саме диск.
      assert.match(text, /flow\.json/);
      /* І це не тост: тост гасне за 3.2с, а тут дизайнер мусить помітити втрату.
         Перевіряємо саме відсутність похвали «Позицію збережено» — вона й була
         б тим тихим шляхом, яким збій колись губився. */
      assert.equal(await page.locator("#cv-toast.show").filter({ hasText: "збережено" }).count(),
        0, "збій показано тостом «Позицію збережено»");
    } finally {
      chmodSync(it1, 0o700);          // інакше тека лишається битою для наступних
    }
    assert.equal(readFileSync(path.join(it1, "flow.json"), "utf8"), wasFile,
      "граф на диску таки змінився, хоч запис мусив упасти");
  });

  /** «Огляд» it1 у СІТЦІ, свіжою вкладкою. Своя навігація, не `overview()`: після
      H найновіша ітерація it2 лишилась БЕЗ кадрів, а `page.goto` вибирає саме її
      (остання в списку) — хелпер чекав би `.cv-card img` до таймауту. */
  async function gridView() {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    /* ⛔ Тиша зʼємки — ПЕРЕДУМОВА цілого блоку, а не турбота окремих перевірок.
       Автозʼємка (T-34) зʼявилась пізніше за ці тести (T-31) і перебудовує
       холст щоразу, коли доїжджає кадр: `buildCanvas` починає з
       `world.innerHTML = ''`, тобто забирає підсвітку, мітки й самі елементи,
       за які тримається драг. Поки чекали тут кожен тест окремо, кожен прогін
       знаходив НОВУ перевірку з тією самою вадою. Місце ОДНЕ — на вході. */
    await shotsSettled(page);
    await page.waitForTimeout(600);            // хай камера сяде у fit
    return page;
  }

  const scaleOf = (t) => Number(t.match(/scale\(([\d.]+)\)/)[1]);

  /** Геометрія кадру з підписом `name` ЩОДО полотна, у пікселях екрана. */
  const geomOf = (page, name) => page.evaluate((label) => {
    const cards = [...document.querySelectorAll("#world .cv-card")];
    const card = cards.find((el) => el.querySelector(".cv-card-head").textContent.includes(label));
    if (!card) return null;
    const c = document.getElementById("canvas").getBoundingClientRect();
    const b = card.getBoundingClientRect();
    return {
      canvas: { left: c.left, top: c.top, w: c.width, h: c.height },
      card: { left: b.left, top: b.top, w: b.width },
      sel: card.classList.contains("sel"),
      selCount: document.querySelectorAll("#world .cv-card.sel").length,
    };
  }, name);

  await t.test("T. клік по рядку панелі приводить камеру до кадру", async () => {
    /* Те, чого дизайнер просив: «клацаю на сторінку в панелі — підзумлюй мене до
       цієї сторінки». До цього клік ставив `pickedPage` і перемальовував панель,
       а на полотні не відбувалось нічого — вибір було не видно НІЧИМ.

       Беремо «Пошук»: у сітці він у ДРУГОМУ РЯДУ (ряд = сторінка), тобто камері
       справді є куди їхати. Перший кадр стоїть майже там, куди привів би й
       `fitAll()`. */
    const page = await gridView();
    const fit = await transform(page);

    /* ⚠️ Спершу дочекатись, поки автозʼємка ВЩУХНЕ (18.09.2026). Підсвітка
       `sel` живе на елементі кадру, а будь-яка перебудова холста знімає її
       разом із самими елементами — це задокументовано там, де вона ставиться
       (`app/app.js`, `flyToPage`). Автозʼємка (T-34) зʼявилась ПІСЛЯ цього
       тесту (T-31) і завершується якраз усередині очікування нижче: зміряно
       діагностикою — під час кліку йшло «знімаю 1 з 3», і кадр, що доїхав,
       перебудовував холст. Тобто тест гонився зі зʼємкою і програвав їй
       мовчки, показуючи «підсвічено 0 копій замість однієї». */
    await shotsSettled(page);
    await page.locator('.row[data-page="poshuk"]').click();
    await page.waitForTimeout(900);            // довше за життя циклу камери

    const moved = await transform(page);
    assert.notEqual(moved, fit, "камера лишилась у «вписати все» — перельоту немає");
    /* Масштаб мусить ВИРОСТИ, і суттєво: сенс перельоту — щоб кадр стало видно й
       читно. Той самий bird-view під іншим кутом фічею не є. */
    assert.ok(scaleOf(moved) > scaleOf(fit) * 1.5,
      `масштаб ${scaleOf(moved)} проти ${scaleOf(fit)} у fit — це той самий bird-view`);

    const g = await geomOf(page, "Пошук");
    // Кадр у ширину — майже все полотно: отже масштаб рахований по ШИРИНІ кадру
    assert.ok(g.card.w > g.canvas.w * 0.8,
      `кадр ${g.card.w}px на полотні ${g.canvas.w}px — масштаб не по ширині`);
    // І по центру полотна, а не абиде
    const dx = (g.card.left + g.card.w / 2) - (g.canvas.left + g.canvas.w / 2);
    assert.ok(Math.abs(dx) < 2, `кадр зсунутий від центра на ${dx}px`);
    /* Верх кадру — НИЖЧЕ верхнього краю полотна (початок екрана видно) і не
       десь у його середині. Числа тут не з `app.js`: перевіряється властивість
       «видно початок», а не константа поля. */
    assert.ok(g.card.top > g.canvas.top,
      `верх кадру зрізаний: ${g.card.top} проти краю ${g.canvas.top}`);
    assert.ok(g.card.top - g.canvas.top < 120,
      `верх кадру аж на ${g.card.top - g.canvas.top}px нижче краю — це вже не переліт`);

    // І підсвічений рівно ОДИН кадр — той, до якого приїхали
    assert.ok(g.sel, "кадр, до якого приїхала камера, не підсвічено");
    assert.equal(g.selCount, 1, "підсвічено більше одного кадру");

    /* Повторний клік по ТОМУ Ж рядку не сміє сіпати камеру: ціль та сама, тож
       цикл мусить сісти в неї й замовкнути. */
    await page.locator('.row[data-page="poshuk"]').click();
    await page.waitForTimeout(500);
    assert.equal(await transform(page), moved, "повторний клік по тому ж рядку сіпнув камеру");

    /* А тепер ресайз вікна. `buildCanvas` ставить `userMoved = false`, і обробник
       `resize` без нього вписує все заново — тобто розгорнуте вікно відкидало б
       людину з кадру назад у bird-view. Переліт мусить рахуватись рухом камери
       так само, як драг і колесо. */
    await page.setViewportSize({ width: 1360, height: 880 });
    await page.waitForTimeout(500);
    assert.equal(await transform(page), moved,
      "ресайз вікна відкинув камеру з кадру — переліт не позначив камеру рухомою");
    await page.close();
  });

  await t.test("U. флоу: той самий екран у двох смугах — камера веде до першого",
               async () => {
    /* Одна сторінка в двох сценаріях — річ звичайна (той самий екран у двох
       історіях), тобто в рядка панелі буває ДВА кадри. Ведемо до першого в
       порядку читання: порядок мусить бути детермінованим, інакше повторний клік
       по тому ж рядку кидає камеру між копіями. */
    writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
      { id: "f1", title: "Перший", nodes: [
        { id: "n1", page: "holovna" }, { id: "n2", page: "poshuk" },
      ], edges: [{ from: "n1", to: "n2" }] },
      { id: "f2", title: "Другий", nodes: [{ id: "n1", page: "poshuk" }], edges: [] },
    ] }));
    const page = await flowView();
    await page.waitForTimeout(600);            // хай камера сяде у fit
    const fit = await transform(page);

    const copies = page.locator(".cv-card").filter({ hasText: "Пошук" });
    assert.equal(await copies.count(), 2, "той самий екран мусить бути в обох смугах");
    // Світові `top` обох копій: перша смуга вище за другу
    const tops = await copies.evaluateAll((els) => els.map((el) => parseFloat(el.style.top)));

    await page.locator('.row[data-page="poshuk"]').click();
    await page.waitForTimeout(900);

    assert.notEqual(await transform(page), fit, "у флоу-виді переліт не відбувся");
    const which = await copies.evaluateAll((els) =>
      els.map((el) => el.classList.contains("sel")));
    assert.equal(which.filter(Boolean).length, 1,
      `підсвічено ${which.filter(Boolean).length} копій замість однієї`);
    const picked = which.indexOf(true);
    assert.ok(tops[picked] === Math.min(...tops),
      `камера пішла до копії на ${tops[picked]}, а вище стоїть ${Math.min(...tops)}`);

    // І та копія справді у вьюпорті, а не просто позначена класом
    const g = await geomOf(page, "Пошук");
    assert.ok(g.card.top > g.canvas.top && g.card.top - g.canvas.top < 120,
      `верх кадру на ${g.card.top - g.canvas.top}px від краю полотна`);
    assert.ok(g.card.w > g.canvas.w * 0.8, `кадр ${g.card.w}px на полотні ${g.canvas.w}px`);
    await page.close();
  });

  await t.test("V. рядок-тека каже, що кадру в неї немає, а не мовчить", async () => {
    /* Тека-організатор (`isGroup`) кадру на полотні не має взагалі: `buildCanvas`
       відсіює групи ще до побудови. Клік по такому рядку раніше не робив НІЧОГО, і
       на холсті це виглядало як зламана фіча: сусідні рядки підлітають до кадру, а
       цей мовчить. Вибір сторінки при цьому не сміє переїхати: `pickedPage` мусить
       лишатись сторінкою, яку МОЖНА відкрити. */
    writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
      pages: [{ id: "holovna", name: "Головна", published: true },
              { id: "poshuk", name: "Пошук", published: true },
              { id: "nova", name: "Нова", published: true },
              { id: "rozdil", name: "Розділ", isGroup: true, children: [] }],
    }));
    const page = await gridView();
    const before = await transform(page);
    const wasSel = await page.locator(".row--sel").getAttribute("data-page");

    await page.locator('.row[data-page="rozdil"]').click();
    const msg = await page.waitForFunction(() => {
      const t = document.getElementById("cv-toast");
      return t && t.classList.contains("show") ? t.textContent : null;
    }, null, { timeout: 5000 }).then((h) => h.jsonValue());
    assert.match(msg, /тека/i, `тост не назвав причину: ${msg}`);
    assert.ok(msg.includes("Розділ"), `тост не назвав саму теку: ${msg}`);

    await page.waitForTimeout(500);
    assert.equal(await transform(page), before, "клік по теці зрушив камеру");
    assert.equal(await page.locator("#world .cv-card.sel").count(), 0,
      "клік по теці підсвітив чужий кадр");
    assert.equal(await page.locator(".row--sel").getAttribute("data-page"), wasSel,
      "клік по теці переставив вибір сторінки на теку, яку не відкрити");
    /* Дерево шарів (B3/B4): теку ВИБИРАЮТЬ для дій над нею (меню, кидок у неї) —
       це видно в aria-selected, а `row--sel` лишається за відкритою сторінкою. */
    assert.equal(await page.locator('.row[data-page="rozdil"]').getAttribute("aria-selected"), "true",
      "тека не стала вибраним рядком — клік не лишив жодного сліду");
    await page.close();
  });

  await t.test("W. переліт і драг не гоняться: рука перебиває камеру", async () => {
    /* Переліт — ДРУГИЙ викликач `camTo` у файлі, і через нього `camStop()` у
       `pointerdown` стереже вже не лише «зумнув колесом і одразу потягнув», а й
       «клікнув рядок і одразу потягнув». Без нього цикл доїжджає до кадру ПОВЕРХ
       руки: рука тримає полотно, а воно все одно їде — виглядає як зламаний драг.

       Форма перевірки та сама, що в O: тиснемо, НЕ рухаючись, і дивимось, чи світ
       стоїть. Під нерухомою рукою трансформ мусить бути мертвий. */
    const page = await gridView();
    // Спершу відлітаємо на «Пошук», щоб наступний переліт був ДОВГИМ — інакше
    // цикл доїде швидше, ніж ми встигнемо натиснути, і перевірка стане порожньою.
    await page.locator('.row[data-page="poshuk"]').click();
    await page.waitForTimeout(900);

    const box = await page.locator("#canvas").boundingBox();
    const grab = [box.x + box.width / 2, box.y + 140];
    await page.locator('.row[data-page="holovna"]').click();
    await page.mouse.move(grab[0], grab[1]);
    await page.mouse.down();                       // ЖОДНОГО чекання: цикл ще їде
    const atDown = await transform(page);

    /* Не порожня перевірка: переліт СПРАВДІ ще в дорозі. Якби він доїхав до
       натискання, «світ стоїть» було б зелене задарма.

       Міряємо ВЕРТИКАЛЬ, і це не послаблення, а та сама властивість по тій осі,
       якою переліт тепер іде. До 31.08.2026 «Головна» і «Пошук» стояли в ДВОХ
       КОЛОНКАХ, тобто переліт між ними був горизонтальний, і в дорозі його ловив
       зсув центра кадру від центра полотна. Тепер ряд = сторінка: обидві стоять у
       нульовій колонці одна під одною, горизонтального руху між ними немає ЗОВСІМ
       — по `dx` перевірка стала б вічно-зеленою (0px, і тест це показав саме так).
       Замість неї: кадр, до якого летимо, ще НЕ видно — його верх лишається вище
       верхнього краю полотна, тоді як доїхавши, `focusBox` ставить його НИЖЧЕ
       краю (це стереже T). Числа з `app.js` тут не потрібні. */
    const g0 = await geomOf(page, "Головна");
    const dy0 = g0.card.top - g0.canvas.top;
    assert.ok(dy0 < -20,
      `переліт доїхав ще до натискання (верх кадру на ${dy0}px від краю) — перевірка порожня`);

    await page.waitForTimeout(700);                // довше за життя циклу камери
    assert.equal(await transform(page), atDown,
      "цикл перельоту не вбито: світ їде під нерухомою рукою");

    // І рука таки пане: інакше «світ стоїть» означало б лише мертвий драг.
    await page.mouse.move(grab[0] - 220, grab[1] + 40, { steps: 8 });
    assert.notEqual(await transform(page), atDown, "рука не пане полотно");
    await page.mouse.up();
    await page.close();
  });

  await t.test("Q. клік по рядку панелі не перебудовує холст під камерою", async () => {
    /* Історія перевірки. Спершу клік по рядку робив повний `render()`: канвас
       перебудовувався цілком і кінчався `fitAll()`, тобто камера, яку дизайнер
       щойно наставив, злітала — і задарма, бо вибору сторінки на полотні не було
       видно НІЧИМ. Тоді тут стояло «камера мусить лишитись рівно там, де стояла».

       Тепер клік ВЕДЕ камеру до кадру (перевірка T), і ціна перебудови стала ще
       вищою: `fitAll()` затер би щойно порахований переліт, а разом з кадрами
       зникла б і підсвітка. Отже перевіряється не «камера стоїть», а те, що холст
       ТОЙ САМИЙ і камера сіла в кадр, а не у «вписати все». */
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.locator(".cv-card img").first().waitFor({ timeout: 20000 });
    /* ⚠️ Спершу дочекатись, поки автозʼємка ВЩУХНЕ (18.09.2026). Цей тест
       доводить, що клік по рядку НЕ перебудовує холст, і доводить це мітками
       на елементах кадрів. Але холст перебудовує ще й автозʼємка (T-34, після
       цього тесту), коли доїжджає черговий кадр, — і тоді мітки зникають не
       через клік, а сама перевірка звинувачує клік у чужій роботі. Зміряно:
       падало «expected 3, actual 0», тобто пропали ВСІ мітки, чого клік не
       робить навіть у зламаному вигляді. */
    await shotsSettled(page);
    await page.waitForTimeout(600);
    const fit = await transform(page);

    // Наставляємо камеру рукою і даємо циклу доїхати — саме її колись і збивало
    const box = await page.locator("#canvas").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await zoomWheel(page, 0, -240);
    await page.waitForTimeout(900);

    /* Мітки на самих елементах кадрів. `buildCanvas` починається з
       `world.innerHTML = ''`, тобто перебудова їх забирає — і це видно навіть
       тоді, коли трансформ випадково зійшовся. */
    const marked = await page.evaluate(() => {
      const els = [...document.querySelectorAll("#world .cv-card")];
      els.forEach((el, i) => { el.dataset.mark = String(i); });
      return els.length;
    });
    assert.ok(marked >= 2, `кадрів для мітки замало: ${marked}`);

    await page.locator('.row[data-page="poshuk"]').click();
    /* Вибір мусить переїхати: інакше все нижче було б зелене від того, що клік
       не робить нічого взагалі. */
    await page.waitForFunction(() => document.querySelector(".row--sel")
      ?.getAttribute("data-page") === "poshuk", null, { timeout: 5000 });
    await page.waitForTimeout(900);              // довше за життя циклу камери

    const survived = await page.evaluate(() =>
      [...document.querySelectorAll("#world .cv-card")].filter((el) => el.dataset.mark).length);
    assert.equal(survived, marked,
      `холст перебудовано: з ${marked} мічених кадрів лишилось ${survived}`);
    assert.notEqual(await transform(page), fit,
      "камера сіла у «вписати все» — тобто клік таки перебудував холст");
    // І клік по панелі не сміє висмикувати з полотна в макет.
    assert.equal(await page.evaluate(() => document.getElementById("canvas").hidden),
      false, "клік по рядку панелі вийшов із «Огляду»");

    /* А вибір при цьому СПРАВЖНІЙ: вихід з «Огляду» відкриває саме цю сторінку.
       Без цієї половини «полагодити холст» можна було б, просто зігнорувавши
       клік на полотні — і панель показувала б одне, а макет відкривав інше. */
    await toLayout(page).click();
    await opened(page, "poshuk");
    await page.close();
  });

  await t.test("P. швидкі щиглики колеса накопичуються так само, як повільні", async () => {
    /* Знайдено приймальною перевіркою етапу 2 на справжньому графі блогу.
       `camTo` рахував нову ціль від того, ДЕ КАМЕРА ЗАРАЗ, тому поки цикл їхав,
       кожен наступний щиглик відштовхувався від позиції, яку камера вже покинула,
       і щиглики гасили один одного. Виміряно: ті самі 12 щигликів давали 10.0×
       повільно і лише 1.81× швидко — флік трекпадом виглядав мертвим. */
    const N = 5;
    const scaleNow = (page) => page.evaluate(() =>
      +document.getElementById("world").style.transform.match(/scale\(([\d.]+)\)/)[1]);

    const run = async (pauseMs) => {
      const page = await browser.newPage({ viewport: VIEW });
      await page.goto(`${url}/app/`);
      await page.getByRole("button", { name: /Огляд/ }).click();
      await page.locator(".cv-card").first().waitFor();
      await page.waitForTimeout(600);
      const box = await page.locator("#canvas").boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      const before = await scaleNow(page);
      for (let i = 0; i < N; i += 1) {
        await zoomWheel(page, 0, -120);
        if (pauseMs) await page.waitForTimeout(pauseMs);
      }
      await page.waitForTimeout(1200);          // хай цикл доїде
      const after = await scaleNow(page);
      await page.close();
      return after / before;
    };

    const fast = await run(0);
    const slow = await run(700);
    /* Допуск 5%: обидва шляхи проходять через ту саму експоненту, різниця може
       бути лише на дрібному хвості згладжування. З багом розбіжність була 5.5 раза. */
    assert.ok(Math.abs(fast - slow) / slow < 0.05,
      `швидко ${fast.toFixed(2)}× проти повільно ${slow.toFixed(2)}× — щиглики не накопичуються`);
  });

  /* Свій `flow.json` на X/Y/Z: дві смуги з ПІДПИСАНИМИ ребрами. Підписи тут
     несущі двічі — вони і є той селектований текст, з якого починається виділення
     (X), і вони ж дають плашки, які видно на середньому зумі. */
  const flowXYZ = () => writeFileSync(path.join(it1, "flow.json"), JSON.stringify({
    flows: [
      { id: "f1", title: "Читач шукає статтю", nodes: [
        { id: "n1", page: "holovna" }, { id: "n2", page: "poshuk" },
      ], edges: [{ from: "n1", to: "n2", label: "шукає статтю" }] },
      { id: "f2", title: "Друга смуга", nodes: [
        { id: "m1", page: "poshuk" }, { id: "m2", page: "holovna" },
      ], edges: [{ from: "m1", to: "m2", label: "вертається" }] },
    ],
  }));

  await t.test("X. протяг по полотну не виділяє нічого", async () => {
    /* Скарга дизайнера: кадри синіють, щойно потягнеш полотно. Це не наш стиль, а
       ВИДІЛЕННЯ браузера: `pointerdown` на полотні дефолтну дію не гасить, тож
       протяг тягне справжній `Range`, а кадр, накритий діапазоном, Chrome заливає
       кольором виділення. Виміряно на демо-графі блогу до правки: протяг із тіла
       кадру давав `isCollapsed === false`, а в тексті виділення лежали підписи
       ребер.

       Тягнемо ЗВІДКИ ТЯГНУТЬ полотно — з тіла кадру (K: тіло лишається пановою
       поверхнею) і з фону полотна: під діапазон там потрапляє підказка внизу. */
    flowXYZ();
    const page = await flowView();
    await page.waitForTimeout(600);
    const canvas = await page.locator("#canvas").boundingBox();

    const dragAndSelect = async ([x, y]) => {
      await page.evaluate(() => window.getSelection().removeAllRanges());
      await dragFrom(page, [x, y], [x + 260, y + 220]);
      return page.evaluate(() => {
        const sel = window.getSelection();
        return { collapsed: sel.isCollapsed, text: sel.toString().slice(0, 60) };
      });
    };

    const body = await page.locator("#world .cv-card .cv-card-body").first().boundingBox();
    const fromCard = await dragAndSelect([body.x + body.width / 2, body.y + body.height / 3]);
    assert.ok(fromCard.collapsed,
      `протяг по кадру виділив «${fromCard.text.replace(/\n/g, "⏎")}»`);

    const fromBack = await dragAndSelect([canvas.x + 40, canvas.y + canvas.height - 220]);
    assert.ok(fromBack.collapsed,
      `протяг по фону виділив «${fromBack.text.replace(/\n/g, "⏎")}»`);

    /* Друга половина скарги: кадр не сміє «відтягуватись» як файл. Картинку
       браузер тягне СВОЇМ жестом, і виділення до цього стосунку не має —
       `user-select` його не гасить. */
    const img = await page.locator("#world .cv-card img").first().evaluate((el) => ({
      draggable: el.draggable, drag: getComputedStyle(el).webkitUserDrag,
    }));
    assert.equal(img.draggable, false, "кадр можна відтягнути з полотна як файл");
    assert.equal(img.drag, "none", `картинці лишили native-drag (${img.drag})`);

    /* А скарги на `flow.json` мусять лишитись КОПІЮВАНИМИ: вимкнути виділення на
       всьому полотні означало б забрати єдиний спосіб винести текст помилки з
       екрана. Панель лежить у канвасі, тобто під тим самим `user-select:none`. */
    assert.equal(await page.evaluate(() => {
      const el = document.createElement("div");
      el.className = "cv-flow-problems";
      document.getElementById("canvas").appendChild(el);
      const v = getComputedStyle(el).userSelect;
      el.remove();
      return v;
    }), "text", "текст скарг на flow.json перестав виділятись");
    await page.close();
  });

  await t.test("Y. збоку видно відсоток зуму", async () => {
    /* Дизайнер попросив індикатор масштабу, як у референсі. Дрібниця, але без неї
       на bird-view незрозуміло, наскільки далеко відʼїхав, а «вписати все» дає
       різний масштаб на різних графах. */
    const page = await flowView();
    await page.waitForTimeout(600);
    const shown = () => page.evaluate(() => {
      const el = document.getElementById("cv-zoom");
      if (!el) return null;
      const world = document.getElementById("world").style.transform;
      return { text: el.textContent.trim(),
               scale: +world.match(/scale\(([\d.]+)\)/)[1],
               box: el.getBoundingClientRect().toJSON(),
               hint: document.querySelector(".cv-canvas-hint").getBoundingClientRect().toJSON(),
               canvas: document.getElementById("canvas").getBoundingClientRect().toJSON() };
    });

    const fit = await shown();
    assert.ok(fit, "індикатора зуму на полотні немає");
    assert.match(fit.text, /^\d+\s*%$/, `індикатор показує «${fit.text}»`);
    assert.equal(parseInt(fit.text, 10), Math.round(fit.scale * 100),
      `індикатор каже ${fit.text}, а камера ${(fit.scale * 100).toFixed(1)}%`);

    // Не перекриває підказку внизу полотна — про це просили окремо.
    const over = !(fit.box.right < fit.hint.left || fit.box.left > fit.hint.right
      || fit.box.bottom < fit.hint.top || fit.box.top > fit.hint.bottom);
    assert.ok(!over, "індикатор накриває підказку внизу полотна");
    // І сам він у межах полотна, а не за краєм.
    assert.ok(fit.box.left >= fit.canvas.left && fit.box.right <= fit.canvas.right
      && fit.box.top >= fit.canvas.top && fit.box.bottom <= fit.canvas.bottom,
      "індикатор виїхав за полотно");

    // І він ЖИВИЙ: колесо мусить його змінити разом із камерою.
    await page.mouse.move(fit.canvas.left + fit.canvas.width / 2,
                          fit.canvas.top + fit.canvas.height / 2);
    await zoomWheel(page, 0, -240);
    await page.waitForTimeout(900);
    const zoomed = await shown();
    assert.notEqual(zoomed.text, fit.text, "індикатор не помітив зуму");
    assert.equal(parseInt(zoomed.text, 10), Math.round(zoomed.scale * 100),
      `після зуму індикатор каже ${zoomed.text}, а камера ${(zoomed.scale * 100).toFixed(1)}%`);

    /* Просто колесо (0.25.0) РУХАЄ полотно і масштабу не чіпає: відсоток той самий, а трансформ світу інший. */
    const worldT = () => page.evaluate(() => document.getElementById("world").style.transform);
    const beforePan = await worldT();
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(300);
    assert.equal((await shown()).text, zoomed.text, "колесо без модифікатора змінило масштаб");
    assert.notEqual(await worldT(), beforePan, "колесо без модифікатора не зрушило полотно");

    // Кнопка «Вмістити все»: клік повертає камеру у fit, а не лишає її де була.
    await page.locator("#cv-zoom").click();
    await page.waitForTimeout(300);
    assert.equal((await shown()).text, fit.text, "клік по індикатору не вписав усе");
    await page.close();
  });

  await t.test("Z. підпис смуги читний на будь-якому зумі, а змінна пишеться лише на зміні",
               async () => {
    /* Підпис смуги живе У СВІТІ, тобто масштабується разом із ним: на «вписати
       все» демо-графа (масштаб 0.05) 22px світу — це 1.1px екрана, тобто підпису
       немає зовсім. Лікуємо кеглем через `calc()` від CSS-змінної з масштабом.

       Ціна рішення була відома ще зі спеки: змінну на `#world` треба писати ЛИШЕ
       при реальній зміні значення, інакше щокадру інвалідується стиль усім
       спадкоємцям. Тому друга половина перевірки — лічильник записів на панорамі:
       масштаб там не змінюється жодного разу, отже й записів мусить бути НУЛЬ. */
    const page = await flowView();
    await page.waitForTimeout(700);
    const title = () => page.evaluate(() => {
      const el = document.querySelector(".cv-band-title");
      const scale = +document.getElementById("world").style.transform
        .match(/scale\(([\d.]+)\)/)[1];
      return { scale, screen: el.getBoundingClientRect().height,
               font: parseFloat(getComputedStyle(el).fontSize) * scale };
    });

    const fit = await title();
    assert.ok(fit.scale < 0.4, `фікстура вписалась на ${fit.scale} — дрібного зуму немає`);
    assert.ok(fit.font >= 11,
      `на зумі ${(fit.scale * 100).toFixed(0)}% підпис смуги ${fit.font.toFixed(1)}px екрана`);

    const canvas = await page.locator("#canvas").boundingBox();
    await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
    for (let i = 0; i < 8; i += 1) await zoomWheel(page, 0, -120);
    await page.waitForTimeout(900);
    const near = await title();
    assert.ok(near.scale > fit.scale * 2, `зум не поїхав: ${fit.scale} → ${near.scale}`);
    assert.ok(near.font >= 11 && near.font < 80,
      `на зумі ${(near.scale * 100).toFixed(0)}% підпис ${near.font.toFixed(1)}px екрана`);

    /* Лічильник записів. Підмінюємо `setProperty` у самій сторінці: транформ
       ставиться присвоєнням (`style.transform = …`) і сюди не потрапляє, тобто
       лічильник рахує РІВНО змінну масштабу. */
    await page.evaluate(() => {
      window.__cvVarWrites = 0;
      const orig = CSSStyleDeclaration.prototype.setProperty;
      CSSStyleDeclaration.prototype.setProperty = function setProperty(name, ...rest) {
        if (name === "--cv-scale") window.__cvVarWrites += 1;
        return orig.call(this, name, ...rest);
      };
    });
    const before = await transform(page);
    await dragFrom(page, [canvas.x + 60, canvas.y + canvas.height - 120],
                   [canvas.x + 460, canvas.y + 160]);
    await page.waitForTimeout(300);
    const panned = await page.evaluate(() => ({
      writes: window.__cvVarWrites,
      t: document.getElementById("world").style.transform,
    }));
    assert.notEqual(panned.t, before, "панорама мусила зсунути світ");
    assert.equal(panned.writes, 0,
      `панорама переписала змінну масштабу ${panned.writes} разів — стиль інвалідується щокадру`);

    // А зум змінну таки МУСИТЬ писати, інакше кегль підпису замерз би.
    await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
    for (let i = 0; i < 6; i += 1) await zoomWheel(page, 0, 120);
    await page.waitForTimeout(900);
    const zoomWrites = await page.evaluate(() => window.__cvVarWrites);
    assert.ok(zoomWrites > 0, "зум не оновив змінну масштабу — підпис замерз");
    assert.ok(zoomWrites < 60,
      `зум переписав змінну ${zoomWrites} разів — квантування не працює`);
    await page.close();
  });

  await t.test("AA. межа кадру, шов голови і кільце смуги — рівно ~1px екрана " +
               "на будь-якому зумі", async () => {
    /* `.cv-card`, `.cv-card-head` (шов ЗНИЗУ, не рамка з усіх боків — box-shadow
       тут не годиться, він обвів би голову звідусіль) і `.cv-band` стояли на
       `border: 1px` — межа СВІТОВОГО розміру: на bird-view (масштаб буває 0.06)
       вона підпіксельна й мерехтить, на зумі 2.5+ розпухає до кількох екранних
       пікселів. Контр-масштабування рахує ЕКРАННУ товщину як (товщина у
       світових px) × --cv-scale — рівно ту арифметику, яку компенсує
       `var(--hairline)` у стилях, — і не питає, ЯКИМ саме способом межу
       намальовано: бере border, box-shadow-кільце й зупинку градієнта РАЗОМ,
       тому байдуже, що з трьох рішень стоїть у якому правилі.

       `--cv-scale` читаємо з computed style САМОГО елемента з межею (`.cv-card`,
       `.cv-card-head`, `.cv-band`), а НЕ з `document.documentElement`: змінну
       пише `applyT()` на `#world` inline-стилем (`world.style.setProperty`), а
       custom property успадковується ВНИЗ по дереву — `<html>`, будучи ПРЕДКОМ
       `#world`, її взагалі не бачить. Читання з предка дало б порожній рядок на
       кожному вимірі, тобто мовчазний фолбек `|| 1` обидва рази.

       Перевіряємо АБСОЛЮТНЕ значення (≈1px) на КОЖНОМУ знятку окремо, а НЕ
       різницю fit-vs-zoom, як була перша версія цієї перевірки: різниця
       залежить від того, наскільки зʼїхав масштаб за вісім нотчів коліщатка, а
       це залежить від fit-масштабу конкретної фікстури й розкладки. Виміряно
       ревʼю мутацією `box-shadow: 0 0 0 1px` (еквівалент без `--hairline`, без
       побічної зміни бокс-моделі): на флоу-виді fit ≈0.1486, вісім нотчів
       довозять лише до ≈0.3536 — екранна різниця на ЗЛАМАНОМУ коді (0.149px →
       0.354px) давала дельту 0.205px, яка проскакувала поріг delta<0.25 і
       лишала перевірку зеленою (41/41, детерміновано). Абсолютне значення від
       fit-масштабу конкретної фікстури не залежить: 0.149px чи 0.354px — обидва
       однаково далеко від 1px. */
    const screenPx = (page, selector) => page.evaluate((sel) => {
      const cs = getComputedStyle(document.querySelector(sel));
      const scale = parseFloat(cs.getPropertyValue("--cv-scale")) || 1;
      const border = (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
      const ring = cs.boxShadow.match(/0px 0px 0px ([\d.]+)px/);
      // Градієнт шва: Chromium розкладає `color 0 X` на явні зупинки, тобто X
      // трапляється в рядку двічі (кінець кольору, старт прозорого) — беремо
      // будь-яке ненульове число.
      const stops = [...cs.backgroundImage.matchAll(/([\d.]+)px/g)].map((m) => parseFloat(m[1]));
      const seam = stops.find((n) => n > 0) || 0;
      return (border + (ring ? parseFloat(ring[1]) : 0) + seam) * scale;
    }, selector);
    // Допуск 0.1px: реальна арифметика дає ~1.00000 (та сама змінна множиться
    // сама на себе, звідна), запас лише під округлення `getComputedStyle` при
    // серіалізації px-рядка. Зламаний код промахується щонайменше на ~0.6px
    // (на fit-масштабах цієї фікстури: 0.15-0.4 замість 1) — допуск ловить
    // регресію з великим запасом, не наближаючись до межі.
    const TOL = 0.1;
    const assertHairline = (label, px) => assert.ok(Math.abs(px - 1) < TOL,
      `${label}: ${px.toFixed(3)}px замість ~1px (допуск ${TOL})`);

    // Сітка: `.cv-card` і `.cv-card-head` на тому самому кадрі, той самий page.
    const grid = await gridView();
    assertHairline("межа кадру на fit", await screenPx(grid, ".cv-card"));
    assertHairline("шов голови на fit", await screenPx(grid, ".cv-card-head"));
    const gc = await grid.locator("#canvas").boundingBox();
    await grid.mouse.move(gc.x + gc.width / 2, gc.y + gc.height / 2);
    for (let i = 0; i < 8; i += 1) await zoomWheel(grid, 0, -120);
    // Хай камера ОСЯДЕ (а не щойно зрушить) — той самий прийом, що в P.
    await grid.waitForTimeout(1200);
    assertHairline("межа кадру на зумі", await screenPx(grid, ".cv-card"));
    assertHairline("шов голови на зумі", await screenPx(grid, ".cv-card-head"));
    await grid.close();

    // Флоу-вид: та сама арифметика для `.cv-band` — своя вкладка, бо смуги в
    // сітці не буває.
    const flow = await flowView();
    await flow.waitForTimeout(700);
    assertHairline("рамка смуги на fit", await screenPx(flow, ".cv-band"));
    const fc = await flow.locator("#canvas").boundingBox();
    await flow.mouse.move(fc.x + fc.width / 2, fc.y + fc.height / 2);
    for (let i = 0; i < 8; i += 1) await zoomWheel(flow, 0, -120);
    await flow.waitForTimeout(1200);
    assertHairline("рамка смуги на зумі", await screenPx(flow, ".cv-band"));
    await flow.close();
  });

  /**
   * Дочекатись, поки холст ПЕРЕБУДУЮТЬ: усі кадри, помічені `data-mark`, зникли,
   * а нові вже на місці.
   *
   * Саме мітками, а не таймаутом і не трансформом: `buildCanvas` починається з
   * `world.innerHTML = ''`, тож мітка не переживає перебудову ФІЗИЧНО — і це
   * видно навіть тоді, коли камера випадково зійшлася. Без такого доказу
   * перевірка «камера не зрушила» була б зелена і від того, що перебудови не
   * сталося зовсім (клік не спрацював, обробник зник) — тобто найгучніший спосіб
   * зламати фічу проходив би за фікс.
   */
  const rebuilt = (page) => page.waitForFunction(() => {
    const els = [...document.querySelectorAll("#world .cv-card")];
    return els.length > 0 && els.every((el) => !el.dataset.mark);
  }, null, { timeout: 20000 });

  await t.test("AB. побічна перебудова холста не рухає камеру", async () => {
    /* `buildCanvas` завжди кінчався `userMoved = false; fitAll()`, а `render()` у
       режимі канваса кличуть чекбокс «на превью», перемикач режиму коментарів,
       `gl-sync` і `gl-pull` — жоден із них полотна не стосується. Тобто дизайнера,
       який зумнувся в кадр, викидало у bird-view будь-яким кліком у смузі.

       Тиснемо перемикач режиму коментарів: він кличе `render()` і БІЛЬШЕ НІЧОГО,
       тобто це рівно той побічний шлях у чистому вигляді. */
    const page = await gridView();
    const fit = await transform(page);

    /* Камеру рухаємо РУКОЮ, справжніми pointer-подіями: саме їх слухає холст, і
       саме вони ставлять `userMoved` — прапорець «дизайнер наставив камеру сам»,
       за яким її й переносять. Програмний зсув трансформа цього не робить. */
    const box = await page.locator("#canvas").boundingBox();
    const grab = [box.x + box.width / 2, box.y + box.height / 2];
    await dragFrom(page, grab, [grab[0] - 160, grab[1] - 90]);
    const moved = await transform(page);
    assert.notEqual(moved, fit, "рука не зрушила камеру — далі порівнювати нема чого");

    /* Мітки на кадрах, як у Q: `buildCanvas` починається з `world.innerHTML = ''`,
       тож їх зникнення — доказ, що перебудова СПРАВДІ була. Без цього доказу
       перевірка була б зелена і від того, що клік не робить взагалі нічого. */
    const marked = await page.evaluate(() => {
      const els = [...document.querySelectorAll("#world .cv-card")];
      els.forEach((el, i) => { el.dataset.mark = String(i); });
      return els.length;
    });
    assert.ok(marked >= 2, `кадрів для мітки замало: ${marked}`);

    await forceRender(page);
    await rebuilt(page);
    await page.waitForTimeout(400);   // хай камера ОСЯДЕ, а не щойно зрушить

    assert.equal(await page.locator("#world .cv-card").count(), marked,
      "перебудова дала інший набір кадрів — світ таки змінився, перевірка не про те");
    assert.equal(await transform(page), moved,
      "побічна перебудова жбурнула камеру — найпевніше у «вписати все»");
    await page.close();
  });

  await t.test("AB2. зміна ітерації камеру ВПИСУЄ заново — це інший світ", async () => {
    /* Парна половина AB, і вона обовʼязкова: без неї «камера не рухається ніколи»
       пройшло б за фікс, а перехід в іншу ітерацію лишав би полотно в кадрі,
       порахованому для ЧУЖИХ габаритів — в it1 три сторінки, в it2 одна, — і
       замість роботи дизайнер бачив би порожнечу збоку від неї.

       Мутація, яку перевірка стереже: прибрати з `buildCanvas` умову
       `camWorld.it === picked` (тобто переносити камеру завжди) — тоді трансформ
       після перемикання лишається тим самим і перевірка червоніє. */
    const page = await gridView();
    const box = await page.locator("#canvas").boundingBox();
    const grab = [box.x + box.width / 2, box.y + box.height / 2];
    await dragFrom(page, grab, [grab[0] - 160, grab[1] - 90]);
    const moved = await transform(page);

    const marked = await page.evaluate(() => {
      const els = [...document.querySelectorAll("#world .cv-card")];
      els.forEach((el) => { el.dataset.mark = "1"; });
      return els.length;
    });
    assert.ok(marked >= 2, `кадрів для мітки замало: ${marked}`);

    await selectIteration(page, "it2");
    await rebuilt(page);
    await page.waitForTimeout(400);

    /* Світ справді ІНШИЙ, а не просто перемальований: в it2 рівно одна сторінка.
       Інакше `notEqual` нижче був би зелений з будь-якої причини. */
    assert.equal(await page.locator("#world .cv-card").count(), 1,
      "на полотні не кадри it2 — перемикання ітерації не доїхало");
    assert.notEqual(await transform(page), moved,
      "інша ітерація — інший світ, камера мусила вписати все заново");
    await page.close();
  });

  await t.test("R. розміри кадру з манифеста — числа, а не розмітка", async () => {
    /* `manifest.json` лежить у теці ітерації, а тека приїжджає з GitLab із чужої
       машини — інваріантом «числа там справді числа» ми не володіємо. `w` і `h`
       ішли в `innerHTML` картки без охорони: рядок із файла закривав тег `<img>`
       (втеча в розмітку) або лягав у текст бейджа «обрізано на …px» і виконувався
       звідти. Правило проєкту (TD-0): усе, що приходить із файлів, або проходить
       `esc()`, або — як тут, бо це числа — до розмітки не доходить зовсім.

       Іде ОСТАННЬОЮ навмисно: манифест лишається побитим, і жодна перевірка після
       неї не читала б справжні розміри. */
    const mpath = path.join(it1, "shots", "manifest.json");
    const manifest = JSON.parse(readFileSync(mpath, "utf8"));
    assert.ok(manifest.shots.holovna && manifest.shots.poshuk,
      `у манифесті немає кадрів, які треба псувати: ${Object.keys(manifest.shots)}`);
    // Втеча з тега `<img>`: закриваємо його й підсовуємо свій, який точно впаде.
    manifest.shots.holovna.w = '1280"><img src=x onerror="document.title=\'ЗЛАМАНО\'"><i x="';
    // А `h` — у ТЕКСТ бейджа, там теги виконуються без жодної втечі.
    manifest.shots.poshuk.truncated = true;
    manifest.shots.poshuk.h = '<img src=y onerror="document.title=\'ЗЛАМАНО2\'">';
    writeFileSync(mpath, JSON.stringify(manifest, null, 2));

    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    await selectIteration(page, "it1");
    await page.waitForFunction(() => document.querySelectorAll("#world .cv-card").length >= 2,
      null, { timeout: 20000 });

    // Головне: розмітку з файла не виконано й у DOM її немає.
    // Назва вкладки/вікна = імʼя застосунку з маніфесту PWA («Deai Canvas»).
    assert.equal(await page.title(), "Deai Canvas", "розмітку з манифеста виконано");
    assert.equal(await page.locator('img[src="x"], img[src="y"], .cv-card-head img').count(), 0,
      "рядок із манифеста став елементом у розмітці картки");

    /* Бейдж «обрізано» мусить лишитись підписом, а не носієм чужого тега. І
       називати він мусить саме обрізання — інакше сигнал загубився б разом із
       числом, якому не можна вірити. */
    const badge = await page.locator(".cv-card").filter({ hasText: "Пошук" })
      .locator(".cv-badge").first().textContent();
    assert.match(badge, /^обрізано/, `бейдж перестав казати про обрізання: ${badge}`);
    assert.ok(!badge.includes("<"), `у бейджі лежить розмітка: ${badge}`);

    /* І геометрія: непридатне число не сміє доїхати до розкладки. Битий `h` дає
       `height:NaNpx` — недійсне оголошення, яке браузер викидає, тобто кадр
       лишається без висоти й накриває сусідів. */
    const heights = await page.locator("#world .cv-card")
      .evaluateAll((els) => els.map((el) => el.style.height));
    assert.deepEqual(heights.filter((h) => !/^[\d.]+px$/.test(h)), [],
      `кадр без придатної висоти: ${JSON.stringify(heights)}`);

    // Атрибут або число, або його немає взагалі — але не рядок із файла.
    const w = await page.locator(".cv-card img").first().getAttribute("width");
    assert.ok(w === null || /^\d+$/.test(w), `ширина кадру — не число: ${w}`);
  });
});

/**
 * Чотири перевірки нижче — КОЖНА своя ізольована фікстура й сервер, без
 * спільного стану з «холст «Огляд»» вище: перші дві живуть на
 * `/commented?ch=project` (шар коментарів, до канваса стосунку не має), третя —
 * на реальному `flow.json` плюс зламаному `/api/iteration-pages`, четверта —
 * на реєстрі з ДВОХ задач. Підтестами мега-тесту вище їх не робимо: та
 * ланцюжок стереже ОДИН порядок дій на ОДНІЙ фікстурі кадрів, а тут посторонній
 * фрагмент лише додав би вузол у чужий ланцюг. Для четвертої це ще й вимога
 * ізоляції: `POST /api/task-switch` міняє `current` у tasks.json сервера, тобто
 * у спільній фікстурі вона лишала б після себе іншу поточну задачу.
 */

test("«Проєкт»: файл адаптера модуля не завантажився — банер зʼявляється одразу через onerror", async (t) => {
  /* 4b-2: ЛІГА веде командний канал модулем `supabase-comments`; CDN Supabase сторінка більше не бере, тож «мережевий
     збій» — це збій файла адаптера `/api/module-client/supabase-comments/adapter.js`. Урок старого сніпета лишився тим
     самим: ревʼю задачі 3 заблокувало CDN — і банер `#cl-down` НЕ зʼявився: `window.__clDown` жив у ЧЕТВЕРТОМУ `<script>`,
     а `onerror` перших трьох спрацьовує РАНІШЕ (класичні скрипти виконуються послідовно, без async/defer) — на той момент
     функції ще не існувало, і охоронець `window.__clDown&&…` мовчки гасив виклик. Тепер банер — ПЕРШИМ тегом
     `MODULE_COMMENT_SNIPPET`. Перевіряємо РІВНО той сценарій: справжній інжект сніпета через `/commented?ch=project`,
     справжні файли модуля, заблокований адаптер. */
  const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
    + `<body><h1>${id}</h1></body></html>`;
  const { dir } = taskFixture({ html });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage();
  const net = await hermeticLiga(page);
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await page.route(MODULE_ADAPTER_GLOB, (route) => route.abort());
  await page.goto(`${url}/commented?it=it1&ch=project`);

  const banner = page.locator("#cl-down");
  await banner.waitFor({ timeout: 5000 });
  /* Текст мусить бути ТОЧНИМ повідомленням з `onerror` тега адаптера, а не тим, що каже запасна гілка в `init()` («шар
     коментарів не піднявся»): якби `__clDown` знову «зʼїхав» у останній скрипт, банер УСЕ ОДНО зʼявився б через неї —
     але з ІНШИМ текстом. Саме на цій розбіжності текстів і ловить мутація: `route.abort()` не лишає слідів, які б
     відрізнялись самі — тільки точний рядок каже, ЯКИЙ саме запобіжник спрацював. */
  assert.equal(await banner.textContent(),
    "Коментарі недоступні: адаптер коментарів не завантажився");
  assert.deepEqual(pageErrors, [],
    `необроблений виняток у консолі: ${pageErrors.join("; ")}`);
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
});

test("«Проєкт»: supabase.min.js модуля віддав 200 з порожнім тілом — try/catch ловить крах фабрики", async (t) => {
  /* Друга причина Critical 1, окрема від першої: файл, що відповів 200 з порожнім чи битим тілом, `onerror` НЕ ЛОВИТЬ
     ВЗАГАЛІ (мережевий запит успішний), а перевірка «є `DeaiComments`» теж мовчить — адаптер модуля піднявся штатно, не
     піднялась лише `window.supabase`, якого чекає його фабрика (`create` кидає СИНХРОННО, поза промісом). Банер тут
     рятує тільки try/catch навколо `DeaiComments.create(…)` у сніпеті. */
  const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
    + `<body><h1>${id}</h1></body></html>`;
  const { dir } = taskFixture({ html });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage();
  const net = await hermeticLiga(page);
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await page.route(MODULE_ADAPTER_GLOB.replace("adapter.js", "supabase.min.js"), (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.goto(`${url}/commented?it=it1&ch=project`);

  const banner = page.locator("#cl-down");
  await banner.waitFor({ timeout: 5000 });
  assert.match(await banner.textContent(), /Коментарі недоступні: .*supabase-js is not loaded/);
  assert.deepEqual(pageErrors, [],
    `необроблений виняток у консолі: ${pageErrors.join("; ")}`);
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
});

test("полотно не малює фейкові «немає сторінки», коли впав перелік сторінок", async (t) => {
  /* Important 2 з ревʼю задачі 3: транзиентний збій `/api/iteration-pages`
     (сервер рестартує, файли на диску цілі) не сміє змусити граф юзер-флоу
     звинуватити КОЖНУ сторінку в зникненні. `it2` несе ВЛАСНИЙ, окремо
     валідний `flow.json`: якби перевірка малювала граф ЗАСТАРІЛИМ (`flowRaw`
     від `it1` — рівно та регресія, яку лагодить Important 2, звужуючи ранній
     `return` у `loadPages`), видимий симптом був би той самий — тест мусить
     ловити САМ БАГ (гейт `!pagesError` у `effView()`), а не випадковий збіг
     «flowRaw порожній для it2». */
  const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
    + `<body><h1>${id}</h1></body></html>`;
  const { dir, it1 } = taskFixture({ html });
  writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
    { id: "f1", title: "Перша", nodes: [
      { id: "n1", page: "holovna" }, { id: "n2", page: "poshuk" },
    ], edges: [{ from: "n1", to: "n2" }] },
  ] }));
  const it2 = path.join(dir, "iterations", "it2");
  mkdirSync(path.join(it2, "holovna"), { recursive: true });
  writeFileSync(path.join(it2, "holovna", "index.html"), html("it2"));
  writeFileSync(path.join(it2, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true }],
  }));
  writeFileSync(path.join(it2, "flow.json"), JSON.stringify({ flows: [
    { id: "f2", title: "Друга", nodes: [{ id: "m1", page: "holovna" }], edges: [] },
  ] }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
                 { id: "it2", date: "24.08.2026 13:00", note: "друга", published: true }],
  }));

  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card").first().waitFor();
  // Останню ітерацію обирає інструмент за замовчуванням — фіксуємо явно.
  await selectIteration(page, "it1");
  await page.locator(".cv-card").first().waitFor();
  await page.getByRole("button", { name: /Флоу/ }).click();
  await page.locator(".cv-band").first().waitFor({ timeout: 15000 });
  assert.equal(await page.locator("#cv-flow-problems").isVisible(), false,
    "цілий flow.json не мав дати жодної скарги ще ДО збою переліку сторінок");

  // Ламаємо ІМЕННО перелік сторінок, а не flow.json: реальний сценарій —
  // сервер рестартує чи не встигає відповісти, файли на диску цілі.
  await page.route("**/api/iteration-pages**", (route) => route.abort());
  await selectIteration(page, "it2");
  await page.waitForFunction(() => {
    const panel = document.getElementById("pages-panel");
    return panel && /не завантажились/.test(panel.textContent || "");
  }, null, { timeout: 20000 });

  assert.equal(await page.locator(".cv-band").count(), 0,
    "полотно лишилось у флоу-виді на зламаному переліку сторінок — мусило відступити в сітку");
  assert.equal(await page.locator("#cv-flow-problems").isVisible(), false,
    "полотно намалювало «немає сторінки» на транзиентному збої переліку сторінок, хоча flow.json цілий");
  /* Смуга (Task 3): «Флоу»/«Сітка» — не один перемикач з підписом, що
     міняється, а сегмент із ДВОХ окремих кнопок, обидві завжди в DOM. Регекс
     `/Флоу|Сітка/` тепер збігається з ОБОМА (строгий режим Playwright кидає
     помилку), тож питаємо саме «Флоу» — це вона мусить стати неактивною. */
  assert.equal(await page.getByRole("button", { name: /Флоу/ }).isDisabled(), true,
    "кнопка «Флоу» мала стати неактивною — звірити граф зі сторінками нема з чим");
});

test("зміна ЗАДАЧІ вписує камеру заново: id ітерацій пер-задачні", async (t) => {
  /* Парна половина до AB/AB2, і без неї перенесення камери через перебудову
     має дірку рівно там, де її найдорожче помітити.

     `camWorld` описував світ як `{it, view}`. Але id ітерацій ПЕР-ЗАДАЧНІ: `it1`
     є в КОЖНІЙ задачі. Тому перемикання задачі в «Огляді» йшло так: `render()`
     нормалізує `picked` в `it1` НОВОЇ задачі → `camWorld.it === picked`
     істинний → `sameWorld` істинний → камера переїжджає у світ ЧУЖОЇ задачі.
     Виміряно рівно на цій фікстурі (2 сторінки і 8): камера лишалась у
     `translate(-100px, 157.645px) scale(0.384058)` замість власного fit другої
     задачі `translate(104.029px, 60px) scale(0.229232)` — зум завищений на 68%,
     зсув у сотні пікселів, тобто рівно та «порожнеча збоку від роботи», проти
     якої `camWorld` і написаний.

     Мутація, яку перевірка стереже: прибрати `camWorld.task === task.id` з
     умови «той самий світ» у `buildCanvas`. AB2 (зміна ІТЕРАЦІЇ) до цього
     сліпа — там id ітерацій справді різні, і `camWorld.it === picked` ловить
     різницю сам.

     Фікстур ДВІ, і сторінок у них по-різному (2 і 8) навмисно: у сітці кадрів
     стільки ж, скільки сторінок, тож «вписати все» у цих світах — різні камери.
     Був би однаковий набір — порівняння трансформів було б зелене від збігу. */
  const a = taskFixture({ html: PAGE });
  const b = taskFixture({ html: PAGE,
    pages: ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8"] });
  const { child, url } = await startServer(a.dir, { portBase: PORT_BASE,
    extraTasks: { druha: { dir: b.dir, title: "Друга задача" } } });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card").first().waitFor();

  /* Кількість кадрів — і доказ «перебудова доїхала», і доказ «світ ІНШИЙ». Чекати
     саме її, а не таймаут: інакше найгучніший злам — перемикач, який не робить
     нічого, — проходив би за фікс, бо камера теж не рухалась би. */
  const cards = (want) => page.waitForFunction(
    (n) => document.querySelectorAll("#world .cv-card").length === n,
    want, { timeout: 20000 });
  /* Ітерація в обох задачах мусить називатись однаково — інакше пастка не
     відтворена й перевірка зелена ні від чого. */
  const itIs = async (id, where) => assert.equal(
    await page.locator('[data-dd="iter"] .txt--fix').textContent(),
    `\u0406\u0442.${String(id).replace(/^it/, "")}`,
    `пастка не відтворена: у ${where} обрана ітерація мусить бути ${id}`);

  await cards(2);
  await itIs("it1", "першій задачі");

  /* 1. ВЛАСНИЙ fit другої задачі. Знімаємо на чистому вході, до будь-якого руху
        рукою: `userMoved` тут `false`, тобто камеру ніхто не переносив і це
        чесний fit ЇЇ світу. */
  await selectTask(page, "druha");
  await cards(8);
  await page.waitForTimeout(600);            // хай камера сяде
  const fitB = await transform(page);
  await itIs("it1", "другій задачі");

  // 2. Назад у першу — і рухаємо камеру РУКОЮ: саме pointer-події ставлять
  //    `userMoved`, за яким камеру й переносять (програмний зсув його не ставить).
  await selectTask(page, "fixture");
  await cards(2);
  await page.waitForTimeout(600);
  const fitA = await transform(page);
  assert.notEqual(fitA, fitB,
    `світи задач дали ОДНАКОВИЙ fit (${fitA}) — порівнювати нижче нема чого`);

  const box = await page.locator("#canvas").boundingBox();
  const grab = [box.x + box.width / 2, box.y + box.height / 2];
  await page.mouse.move(grab[0], grab[1]);
  await page.mouse.down();
  await page.mouse.move(grab[0] - 160, grab[1] - 90, { steps: 12 });
  await page.mouse.up();
  const moved = await transform(page);
  assert.notEqual(moved, fitA, "рука не зрушила камеру — далі порівнювати нема чого");

  // 3. Перемикаємо ЗАДАЧУ тим самим дропдауном, яким це робить дизайнер.
  await selectTask(page, "druha");
  await cards(8);
  await page.waitForTimeout(600);
  const after = await transform(page);

  assert.notEqual(after, moved,
    "камера лишилась там, куди її наставили в ЧУЖІЙ задачі");
  assert.equal(after, fitB,
    `камера мусила вписати ВЛАСНИЙ світ другої задачі (${fitB}), а стоїть у ${after}`);
});

test("AC. сітка: ряд = сторінка з її станами й дітьми, підпис над рядом і в межах смуги",
     async (t) => {
  /* ОКРЕМИЙ тест, а не підтест «холст «Огляд»», хоч план і просив підтест. Причина
     виміряна, а не стилістична: у спільній фікстурі рядів по ОДНІЙ картці (дві
     сторінки без станів і без дітей), тобто мутація «поріж ряд по три»
     (`cards.slice(0,3)`) на ній нічого не міняє й лишається зеленою — перевірка
     стерегла б порожнечу. Ряд із чотирьох карток і другий ряд під ним потрібні
     тут ОБИДВА, а покласти їх у спільну фікстуру не можна: `flow.json` там мусить
     бути відсутнім до I0 і своїм у I2/I3/J/K/N.

     `runShoot` навмисно НЕ кличемо: перевіряються координати й підписи, а не
     знімки. Без кадрів кожна картка малює `.cv-card-ph` з ЧИСТИМ підписом — тим
     самим, який дала модель, — і адресувати картки можна без розбирання голови
     кадру (там ще бейдж, «у превью» і кнопка). Заразом тест не платить 20 секунд
     за зʼємку. */
  const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
    + `<body><h1>${id}</h1></body></html>`;
  const { dir, it1 } = taskFixture({ html });
  /* Своя `pages.json`: потрібні і сторінка З ДИТИНОЮ, і ТЕКА з дитиною.
       • дитина сторінки в ряду — єдине, що відрізняє «ряд = сторінка й усе під
         нею» від «ряд = сторінка та її стани з графа»;
       • тека — інваріант, на якому згоріли два попередні коміти: сама вона ряду
         не дає (кадру в неї немає), а її дитина дає ПОВНОЦІННИЙ ряд. Модульний
         тест це вже стереже, але ламався не модуль, а ЛАНЦЮГ
         `pages.json → openable_pages → buildRows → полотно`, і на полотні це
         виглядало як мовчки зникла сторінка. */
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({ pages: [
    { id: "holovna", name: "Головна", published: true },
    { id: "poshuk", name: "Пошук", published: true,
      children: [{ id: "poshuk-vkl", name: "Підсторінка", published: true }] },
    { id: "rozdil", name: "Розділ", isGroup: true,
      children: [{ id: "rozdil-nova", name: "Нова", published: true }] },
  ] }));
  /* ТРИ стани однієї сторінки — щоб ряд вийшов ЧОТИРИ картки завдовжки. Рівно
     три картки в ряду зробили б мутацію «поріж по три» тотожним перетворенням. */
  writeFileSync(path.join(it1, "flow.json"), JSON.stringify({ flows: [
    { id: "f", title: "Сценарій", nodes: [
      { id: "n0", page: "holovna" },
      { id: "n1", page: "holovna", state: { s: "empty" }, label: "Головна · порожньо" },
      { id: "n2", page: "holovna", state: { s: "loading" }, label: "Головна · завантаження" },
      { id: "n3", page: "holovna", state: { s: "error" }, label: "Головна · помилка" },
    ], edges: [] },
  ] }));

  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card").first().waitFor();
  await page.waitForTimeout(400);               // хай камера сяде у fit

  /* Читаємо з DOM, а не рахуємо повторно арифметику app.js: інакше перевірка
     дзеркалила б код замість того, щоб його стерегти. */
  const geom = await page.evaluate(() => [...document.querySelectorAll("#world .cv-card")]
    .map((el) => ({ label: el.querySelector(".cv-card-ph").textContent,
                    x: parseFloat(el.style.left), y: parseFloat(el.style.top) })));
  /* Спершу — що координати взагалі проставлені. Картка, якої розкладка не
     побачила, лишається без `style.left` зовсім, тобто випадає з групування по
     `y` МОВЧКИ: без цього рядка «ряд порізали по три» виглядало б як цілий ряд
     із трьох карток, і перевірка нижче була б зелена. */
  assert.ok(geom.length > 0 && geom.every((g) => Number.isFinite(g.x) && Number.isFinite(g.y)),
    `кадр без координат — розкладка його не побачила: ${JSON.stringify(geom)}`);

  // Групуємо в порядку появи в DOM: він же порядок побудови рядів.
  const rows = [];
  for (const g of geom) {
    const row = rows.find((r) => r.y === g.y) ?? (rows.push({ y: g.y, labels: [], xs: [] }),
                                                  rows[rows.length - 1]);
    row.labels.push(g.label);
    row.xs.push(g.x);
  }

  assert.deepEqual(rows.map((r) => r.labels), [
    ["Головна", "Головна · порожньо", "Головна · завантаження", "Головна · помилка"],
    /* Дитина сторінки з `pages.json` без `kind` — СТАН (A7, `kindOf`), і підписана
       вона без «↳»: див. `tests/rows-model.test.mjs` «легасі-дитина сторінки». */
    ["Пошук", "Підсторінка"],
    // Тека рядом не стала, а її дитина — стала, і повноцінним.
    ["Нова"],
  ], "ряд мусить бути сторінкою з її станами й дітьми, а не нарізкою плоского переліку");
  for (const r of rows) {
    assert.deepEqual(r.xs, r.xs.map((_, i) => i * (CARD_W + GAP)),
      `ряд «${r.labels[0]}»: крок усередині ряду — кадр плюс зазор`);
  }
  assert.ok(rows[1].y > rows[0].y, "другий ряд мусить стояти НИЖЧЕ першого");

  const titles = await page.evaluate(() => [...document.querySelectorAll(".cv-row-title")]
    .map((el) => {
      return { text: el.textContent, x: parseFloat(el.style.left),
               top: parseFloat(el.style.top), pe: getComputedStyle(el).pointerEvents };
    }));
  assert.deepEqual(titles.map((t2) => t2.text), ["Головна", "Пошук", "Нова"],
    "підпис мусить бути в кожного ряду і називати його сторінку");
  assert.deepEqual(titles.map((t2) => t2.x), [0, 0, 0], "підпис стоїть над лівим краєм ряду");
  /* Ряди зсунуті вниз рівно на місце під підпис. Без зсуву підпис першого ряду
     сідає ВИЩЕ нуля світу, а `#world` відʼємних координат не має: «вписати все»
     рахує габарит від нуля і все, що вище, зрізає (та сама причина, що в
     `FLOW_TOP`, і той самий інваріант, що стереже перевірка I у флоу). */
  assert.equal(rows[0].y, ROW_TITLE_TOP,
    "перший ряд мусить бути зсунутий вниз на місце під підпис");
  assert.ok(titles.every((t2) => t2.top >= 0),
    `підпис вище нуля світу — «вписати все» його зріже: ${JSON.stringify(titles)}`);
  /* А це вже саме відношення «НАД рядом», і воно окреме від двох попередніх:
     `top >= 0` пропускає підпис, який ЛІГ ПОВЕРХ свого ряду (120 ≥ 0 теж), а
     зсув рядів без цього твердження доводить лише те, що місце вирізане, — не
     те, що підпис у це місце став. */
  assert.deepEqual(titles.map((t2) => t2.top), rows.map((r) => r.y - ROW_TITLE_TOP),
    "підпис мусить стояти НАД своїм рядом, а не поверх нього");
  /* `pointer-events:none` на підписі — НЕСУЧЕ, не гігієна: підпис тягнеться
     вправо через увесь зазор і на дрібному зумі стоїть впритул до верху кадру, а
     `pointerdown` у нього означає `closest('.cv-card-head') === null`, тобто драг
     вузла стає панорамою. Те саме вже ловила перевірка N на підписі смуги. */
  assert.deepEqual(titles.map((t2) => t2.pe), ["none", "none", "none"]);

  /* І останнє — «вписати все» мусить вписати ВСЕ. Габарит світу рахується по
     КАРТКАХ (`worldBox`), а картки зсунуті вниз на `ROW_TITLE_TOP`; порахуй цей
     зсув в одному місці замість спільного — і габарит виявиться на 160px
     коротшим за світ, тобто низ останнього ряду поїде за край полотна. Видно це
     не завжди: поле `fitBox` (60px екрана) недобір ховає, поки він дрібний, —
     саме тому міряємо не «влазить», а СИМЕТРІЮ вписування.

     Верх світу — це верх підпису першого ряду (він стоїть на світовому нулі),
     низ — низ найнижчої картки. `fitBox` центрує світ, тож вільне місце над і під
     ним мусить бути однаковим. Числа з `app.js` тут не дзеркаляться зовсім. */
  const fit = await page.evaluate(() => {
    const c = document.getElementById("canvas").getBoundingClientRect();
    const top = document.querySelector(".cv-row-title").getBoundingClientRect().top;
    const bottom = Math.max(...[...document.querySelectorAll("#world .cv-card")]
      .map((el) => el.getBoundingClientRect().bottom));
    return { above: top - c.top, below: c.bottom - bottom };
  });
  assert.ok(fit.below > 0,
    `низ останнього ряду за краєм полотна на ${(-fit.below).toFixed(1)}px — «вписати все» зрізало світ`);
  assert.ok(Math.abs(fit.above - fit.below) < 2,
    `світ вписано несиметрично: ${fit.above.toFixed(1)}px над ним і ${fit.below.toFixed(1)}px під ним `
    + '— габарит світу порахований не по тих самих координатах, що картки');

  /* І остання властивість: коробка підпису мусить УЛАЗИТИ у смугу, вирізану під
     неї (`ROW_TITLE_TOP`). Кегль підпису контр-масштабований, тобто у СВІТІ
     підпис РОСТЕ, коли камера відʼїжджає, і тримає його лише стеля `clamp` у
     `.cv-row-title`. Зі стелею 260px, з якою фіча приїхала зі спеки, коробка була
     306 світових px проти смуги і накривала 186px ВЛАСНОГО кадру — усю голову
     плюс 152px знімка, голим текстом по скріншоту.

     Міряємо НЕ на fit, і це головне в цьому блоці: на fit цієї фікстури масштаб
     0.185, тобто контр-масштабований кегль (22/0.185 ≈ 119px) до стелі не
     доростає ЗОВСІМ — перевірка на fit була зелена і зі стелею 132, і з 260,
     тобто стерегла порожнечу (виміряно мутаційно). Відʼїжджаємо колесом до
     підлоги масштабу — саме там кегль найбільший, і саме там стеля або працює,
     або ні. */
  await page.evaluate(() => {
    const c = document.getElementById("canvas");
    const r = c.getBoundingClientRect();
    for (let i = 0; i < 20; i += 1) {
      c.dispatchEvent(new WheelEvent("wheel", { deltaY: 240, metaKey: true, cancelable: true,
        clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
    }
  });
  await page.waitForTimeout(900);               // довше за життя циклу камери
  const far = await page.evaluate(() => {
    const world = document.getElementById("world");
    const scale = Number((world.style.transform.match(/scale\(([\d.]+)\)/) || [])[1]);
    /* Кегль CSS рахує не від масштабу, а від `--cv-scale` — масштабу, посадженого
       на грубу сітку (`quantScale`), і брати треба саме його. Зазор квантування —
       до 4.5%, тобто БІЛЬШИЙ за будь-який розумний допуск: порівняння з самим
       масштабом віддавало «стеля працює» там, де вона не працювала (виміряно
       мутаційно — прибрання зуму нижче лишалось зеленим). */
    const cvScale = Number(world.style.getPropertyValue("--cv-scale"));
    return [...document.querySelectorAll(".cv-row-title")].map((el) => ({
      text: el.textContent, scale, cvScale,
      worldFontPx: parseFloat(getComputedStyle(el).fontSize),
      boxH: el.getBoundingClientRect().height / scale,
    }));
  });
  /* Дві половини, і жодна не зайва. Перша: стеля СПРАВДІ задіяна — без неї кегль
     був би `22 / --cv-scale`, тобто помітно більший за той, що стоїть. Без цього
     рядка друга половина стала б зеленою на будь-якому масштабі, де `clamp` ще не
     впирається, — рівно та пастка, яку тут уже зловили. */
  for (const t2 of far) {
    assert.ok(t2.worldFontPx < 22 / t2.cvScale - 1,
      `на масштабі ${t2.scale} (--cv-scale ${t2.cvScale}) стеля кегля не задіяна `
      + `(кегль ${t2.worldFontPx}px) — перевірка коробки нижче порожня`);
    assert.ok(t2.boxH <= ROW_TITLE_TOP,
      `коробка підпису «${t2.text}» — ${t2.boxH.toFixed(1)} світових px проти смуги `
      + `${ROW_TITLE_TOP}: підпис лізе на власний кадр`);
  }
});

/**
 * AD. Поле вводу всередині канваса замість `prompt()`.
 *
 * ⛔ Чому це не косметика — одне канонічне пояснення в шапці `app/ask.js`
 * (браузер уміє вимкнути діалоги, після чого `prompt()` мовчки віддає `null`, а
 * код читає це як відмову користувача). Тут причину не переказуємо: копії
 * розходяться, і розходиться саме та, якої ніхто не перечитує.
 *
 * ОКРЕМИЙ тест, а не підтест «холст «Огляд»», хоч план і просив підтест — причина
 * виміряна прогоном, а не стилістична. Перша перевірка МУТУЄ фікстуру (створює
 * сторінку), тобто в ланцюжку, який стереже один порядок дій на одній фікстурі
 * кадрів, вона може стояти лише в самому кінці — а в кінці вона йде після `R.`,
 * який навмисно псує манифест (`truncated`, розмітка в `h`). Після `R.` хелпер
 * `overview()` не дочікується `.cv-card img` зовсім, і обидві перевірки червоніли
 * ТАЙМАУТОМ У ХЕЛПЕРІ — не тим, що стережуть.
 *
 * `runShoot` тут не кличемо: перевіряється ввід, а не знімки. Без кадрів картка
 * малює `.cv-card-ph`, і тест не платить 20 секунд за зʼємку.
 */
test("AD. поле вводу в канвасі замість prompt()", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  /** «Огляд» без знімків: чекаємо КАРТКУ, а не картинку в ній (див. шапку). */
  const canvas = async () => {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    return page;
  };

  /* Панель більше не створює сторінок (рішення власника 30.09.2026: їх створює
     Claude, кнопки «＋ стор.» нема). Поле вводу в канвасі, яке стерегла ця група,
     живе далі — його кличе «Перейменувати…»: той самий `ask`, ті самі шляхи
     Esc / «Скасувати» / Enter / «Гаразд». Тому тригер тут — меню рядка, а
     «створилась / не створилась» стало «перейменувалась / не перейменувалась». */
  const askRename = async (page, id) => {
    await page.locator(`.panel [data-page="${id}"]`).click({ button: "right" });
    await page.click('#cv-ctx [data-a="rename"]');
  };

  await t.test("AD1. «перейменувати» питає в канвасі, а не діалогом браузера", async () => {
    const page = await canvas();
    /* Якщо код усе ще кличе `prompt()`, цей слухач спрацює — і тест впаде на
       ньому, а не на таймауті. Так видно ПРИЧИНУ, а не факт. */
    const dialogs = [];
    page.on("dialog", async (d) => { dialogs.push(d.message()); await d.dismiss(); });
    await askRename(page, "holovna");
    /* Порядок навмисний: діалог перевіряємо ПЕРШИМ. З `prompt()` у коді поле не
       зʼявиться ніколи, тож із зворотним порядком (як просив план) єдиним слідом
       у виводі був би таймаут `waitFor` — факт без причини. Подія діалогу сюди
       вже долетіла: `prompt()` блокує рендерер, тобто `press()` вертається лише
       після того, як слухач вище його відхилив. */
    await page.waitForTimeout(200);
    assert.deepEqual(dialogs, [], "канвас усе ще кличе діалог браузера");
    const field = page.locator(".cv-ask input");
    await field.waitFor({ timeout: 3000 });
    await field.fill("Нова сторінка");
    await press(page, page.locator(".cv-ask [data-a='ok']"));
    await page.locator(".row", { hasText: "Нова сторінка" }).waitFor({ timeout: 5000 });
  });

  await t.test("AD2. Esc не перейменовує — скасування лишається скасуванням", async () => {
    const page = await canvas();
    const nameBefore = await page.locator('.panel [data-page="holovna"] .row-name').textContent();
    await askRename(page, "holovna");
    await page.locator(".cv-ask input").fill("Не перейменовувати");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    assert.equal(await page.locator(".cv-ask").count(), 0, "оверлей не закрився");
    assert.equal(await page.locator(".row", { hasText: "Не перейменовувати" }).count(), 0,
      "сторінка перейменувалась попри Esc");
    assert.equal(await page.locator('.panel [data-page="holovna"] .row-name').textContent(), nameBefore,
      "стара назва зникла");
  });

  await t.test("AD3. «Скасувати» скасовує, Enter підтверджує", async () => {
    const page = await canvas();
    /* Кнопка «Скасувати» — шлях, окремий від Esc, і план вважав, що його стереже
       перевірка вище. Не стереже: мутація `done(input.value)` у цій кнопці
       лишалась ЗЕЛЕНОЮ на обох перевірках вище (виміряно повним
       `npm run test:live`) — жодна з них кнопки не торкається. */
    await askRename(page, "holovna");
    await page.locator(".cv-ask input").fill("Не перейменовувати");
    await press(page, page.locator(".cv-ask [data-a='cancel']"));
    await page.waitForTimeout(300);
    assert.equal(await page.locator(".cv-ask").count(), 0, "оверлей не закрився");
    assert.equal(await page.locator(".row", { hasText: "Не перейменовувати" }).count(), 0,
      "«Скасувати» перейменувало сторінку");

    /* І Enter: у полі вводу це головний шлях підтвердження — той, яким ввід
       завершували в `prompt()`, — а вище його не натискає жодна перевірка. */
    await askRename(page, "holovna");
    await page.locator(".cv-ask input").fill("Сторінка з клавіші");
    await page.keyboard.press("Enter");
    await page.locator(".row", { hasText: "Сторінка з клавіші" }).waitFor({ timeout: 5000 });
  });
});

/**
 * Сьоме — і останнє — місце `prompt()`: фолбек кнопки «🔗 Посилання», коли
 * `navigator.clipboard` відмовляє (не-https, відмовлені права).
 *
 * Чому окремою перевіркою, а не самим лише юніт-сторожем із
 * `tests/rows-model.test.mjs`: той стереже ВІДСУТНІСТЬ `prompt(` у тексті
 * `app/app.js` — і лишається зеленим на порожньому `catch`, тобто на світі, де
 * користувач не отримує посилання взагалі. «Показали посилання» не стереже там
 * ніхто.
 *
 * Своя фікстура, а не підтест `AD`: кнопка жива лише коли задача опублікована І
 * обрана сторінка в превʼю, а `AD` по дорозі СТВОРЮЄ сторінки — вибір сторінки в
 * панелі залежав би від порядку підтестів, і перевірка червоніла б «ця сторінка
 * знята з превʼю», тобто не тим, що стереже.
 */
test("AE. фолбек копіювання показує посилання в канвасі, а не діалогом браузера", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  /* `publish_url` сервер бере з `iterations.json` (`load_meta` у `serve.py`), а не
     з реєстру задач, тому дописуємо його поверх фікстури: без нього кнопка
     `disabled` («задача ще не опублікована») і обробника на ній немає зовсім. */
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "фікстура", published: true }],
    publish_url: "http://prev.example/fixture/",
  }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  const dialogs = [];
  page.on("dialog", async (d) => { dialogs.push(d.message()); await d.dismiss(); });
  await page.goto(`${url}/app/`);
  await page.locator('[data-dd="pub"]').click();
  await page.locator('.dd [data-act="copylink"]').waitFor({ timeout: 5000 });

  /* Рівно та поломка, заради якої фолбек існує. `defineProperty`, бо
     `navigator.clipboard` — гетер на прототипі й простим присвоєнням не
     заміщається. */
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(new Error("NotAllowedError")) },
    });
  });
  await press(page, page.locator('.dd [data-act="copylink"]'));
  /* Діалог перевіряємо ПЕРШИМ — з тієї ж причини, що і в `AD1`: із `prompt()` у
     коді поле не зʼявиться ніколи, і єдиним слідом лишився б таймаут `waitFor`,
     тобто факт без причини. */
  await page.waitForTimeout(200);
  assert.deepEqual(dialogs, [], "фолбек усе ще кличе діалог браузера");

  const field = page.locator(".cv-ask input");
  await field.waitFor({ timeout: 3000 });
  assert.match(await field.inputValue(), /^http:\/\/prev\.example\/fixture\/#k=/,
    "у полі не посилання на превʼю");
  /* Тільки-читання — це і є вибір цього місця: тут не питають, а показують. */
  assert.equal(await field.evaluate((e) => e.readOnly), true, "поле не тільки-читання");
  /* І вийти можна клавішею. Кнопка каже «Закрити», але фокус стоїть у полі (щоб
     працював Ctrl+C по виділеному), тож Enter — найприродніший вихід; доти він
     був єдиною клавішею, яку тут не приймали, і закритись можна було лише Esc
     або мишею. */
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.equal(await page.locator(".cv-ask").count(), 0, "Enter не закриває показ посилання");
});

/**
 * AF. Питання канваса не спираються на стан, який міг змінитись, поки їх ставили.
 *
 * ⛔ Ціле сімейство помилок, яке НАРОДИЛОСЬ від заміни `prompt()` на `ask()`, і
 * поточкове ревʼю задачі побачити його не могло: воно живе на стику. `prompt()`
 * спиняв сторінку — між питанням і записом змінити не можна було нічого.
 * `ask()` не спиняє: підкладку додано вже після ревʼю, а до неї канвас лишався
 * живим під відкритим питанням.
 *
 * Фікстура з ДВОМА ітераціями: на одній «сторінка поїхала в чужу ітерацію» не
 * відтворюється взагалі — переміщатись нікуди, і перевірка була б вічно зелена.
 */
test("AF. питання канваса не спираються на стан, який міг змінитись", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const it2 = path.join(dir, "iterations", "it2");
  mkdirSync(path.join(it2, "holovna"), { recursive: true });
  writeFileSync(path.join(it2, "holovna", "index.html"), PAGE("it2"));
  writeFileSync(path.join(it2, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true }],
  }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "ф", published: true },
                 { id: "it2", date: "24.08.2026 13:00", note: "друга", published: true }],
  }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  /** Імена сторінок ітерації — з ДИСКА: перевіряється, куди ліг запис. */
  const names = (id) => JSON.parse(
    readFileSync(path.join(dir, "iterations", id, "pages.json"), "utf8")).pages.map((x) => x.name);
  const iterations = () => JSON.parse(
    readFileSync(path.join(dir, "iterations.json"), "utf8")).iterations.map((x) => x.id);

  /** «Огляд» без знімків: чекаємо КАРТКУ, а не картинку в ній. */
  const canvas = async () => {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator(".cv-card").first().waitFor();
    return page;
  };

  await t.test("AF1. назва лягає в ту ітерацію, під якою її питали", async () => {
    const page = await canvas();
    // Обрана — найновіша. Перевірка тримається на цьому, тож кажемо це вголос.
    assert.equal(
      (await page.locator('[data-dd="iter"] .txt--fix').textContent()).trim(), "\u0406\u0442.2");

    /* Тригер — «Перейменувати…» (кнопки «＋ стор.» більше нема, див. AD): запис
       `page-rename` несе `it`, зафіксований ДО питання, — те саме правило, що
       стерегла «додати сторінку». */
    await page.locator('.panel [data-page="holovna"]').click({ button: "right" });
    await page.click('#cv-ctx [data-a="rename"]');
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });

    /* Перемикаємо ітерацію, поки питання відкрите. Подією, а не мишею:
       підкладка кліки ловить (це і є її робота, її стереже AF2), тож мишею сюди
       ходу більше немає. Але підкладка — це CSS, а перевіряється тут ЗАПИС: він
       мусить лягти в ту ітерацію, під якою питали, хоч би `picked` змінили
       клавіатурою, іншою вкладкою чи майбутнім кодом.
       Старий `<select>#pp-itsel` зник разом зі старою панеллю — перелік тепер
       живе в дропдауні крошки. `dispatchEvent` тут не заради події зміни, а
       заради самого перемикача, тож відтворюємо шлях делегації руками: клік по
       крошці (відкриває дропдаун — БЕЗ нього пункту `[data-val="it1"]` ще нема
       в DOM), тоді клік по пункту переліку. `dispatchEvent`, а не `.click()`,
       бо саме так у DOM народжується `click`, який ловить делегований
       обробник — обидва клацання в ОДНОМУ синхронному блоці, як і `sel.value +
       change` робили раніше. */
    await page.evaluate((id) => {
      const crumb = document.querySelector('[data-dd="iter"]');
      crumb.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      const item = document.querySelector(`.dd [data-act="iter"][data-val="${id}"]`);
      item.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    }, "it1");
    await page.locator(".cv-ask input").fill("ПРОБА");
    await press(page, page.locator(".cv-ask [data-a='ok']"));

    for (let i = 0; i < 40 && !names("it2").includes("ПРОБА")
                          && !names("it1").includes("ПРОБА"); i += 1) {
      await page.waitForTimeout(250);
    }
    /* Саме `includes`, а не звірка всього переліку: у it1 своїх сторінок дві від
       самої фікстури, і `deepEqual` червонів би на них, а не на переїзді. */
    assert.equal(names("it1").includes("ПРОБА"), false,
      `сторінка поїхала в ЧУЖУ ітерацію: it1 = ${JSON.stringify(names("it1"))}`);
    assert.ok(names("it2").includes("ПРОБА"),
      `сторінки немає там, де її питали: it2 = ${JSON.stringify(names("it2"))}`);
  });

  await t.test("AF2. скасоване питання не створює ітерацію — ні Esc, ні перебиттям", async () => {
    const page = await canvas();
    const before = iterations();

    /* 1. Esc. Доти тут стояло `?? ''`, тобто скасування ставало «створи
          ітерацію з порожньою приміткою». */
    await page.locator('[data-dd="iter"]').click();
    await press(page, page.locator('.dd [data-act="newit"]'));
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(700);
    assert.deepEqual(iterations(), before, "Esc створив ітерацію");

    /* 2. Перебиття другим питанням. Оверлей на канвас один, тож другий виклик
          гасить перший і той віддає `null` — а з `?? ''` це означало «створюй»:
          ітерація зʼявлялась від звичайного кліку по СУСІДНІЙ кнопці, без
          підтвердження й без сліду. Клік через `evaluate`, бо мишею підкладка
          його вже не пускає; шлях у коді від цього нікуди не дівається.
          Старий `#pp-add` → `[data-act="newpage"]` → (панель шарів без «＋ стор.»)
          тепер «Перейменувати ітерацію». */
    await page.locator('[data-dd="iter"]').click();
    await press(page, page.locator('.dd [data-act="newit"]'));
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });
    await page.evaluate(() => {
      // друге питання — «Перейменувати ітерацію» (синхронне, як колишня «＋ стор.»)
      document.querySelector('[data-dd="iter"]').dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }));
      document.querySelector('.dd [data-act="renit"]').dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(700);
    assert.deepEqual(iterations(), before, "перебите питання створило ітерацію мовчки");

    /* 3. І сама підкладка: поки питання відкрите, сусідня кнопка мишею
          недосяжна. Без цього рядка «перебиття» лишалось би теоретичним, а
          підкладка — неперевіреною. */
    await page.locator('[data-dd="iter"]').click();
    await press(page, page.locator('.dd [data-act="newit"]'));
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });
    const blocked = await page.locator('.panel [data-act="newfolder"]').click({ timeout: 1500 })
      .then(() => false, () => true);
    assert.equal(blocked, true,
      "підкладка не ловить кліки — канвас лишається живим під відкритим питанням");
    await page.keyboard.press("Escape");
    /* Позитивний контроль до «blocked»: після закриття питання та сама кнопка
       досяжна й клік доходить (зʼявляється поле назви нової теки). Без цього
       `blocked` був би зелений і на кнопці, якої немає в DOM. */
    await page.locator(".cv-ask-scrim").waitFor({ state: "detached", timeout: 3000 });
    await page.locator('.panel [data-act="newfolder"]').click({ timeout: 3000 });
    await page.locator(".cv-ask input").waitFor({ timeout: 3000 });
    await page.keyboard.press("Escape");
  });
});

/**
 * AG. Руйнівні дії питають у канвасі, і дефолт — не руйнувати.
 *
 * ⛔ `confirm()` вимикається ТІЄЮ САМОЮ галочкою, що й `prompt()` (причина — у
 * шапці `app/ask.js`), і після неї миттєво віддає `false`, а код скрізь писав
 * `if (!go) return;`. Обіцянка циклу «жоден шлях вводу в канвасі не залежить від
 * діалогів браузера» була неправдива рівно тут: «Видалити сторінку» не робила
 * НІЧОГО і не казала НІЧОГО.
 */
test("AG. видалення питає в канвасі, і дефолт — не видаляти", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  const dialogs = [];
  page.on("dialog", async (d) => { dialogs.push(d.message()); await d.dismiss(); });
  await page.goto(`${url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card").first().waitFor();

  const pages = () => JSON.parse(
    readFileSync(path.join(dir, "iterations", "it1", "pages.json"), "utf8")).pages.map((x) => x.id);
  assert.deepEqual(pages(), ["holovna", "poshuk"], "фікстура не та, яку чекає перевірка");

  const menuDelete = async () => {
    await page.locator('.row[data-page="poshuk"]').click({ button: "right" });
    await page.locator('#cv-ctx [data-a="delete"]').click();
  };

  // 1. Питання — у канвасі, а не діалогом браузера.
  await menuDelete();
  /* Спершу ДІАЛОГ, і лише потім поле — той самий порядок і та сама причина, що
     в `AD1`: із `confirm()` у коді оверлея не буде ніколи, тож у зворотному
     порядку єдиним слідом лишився б таймаут `waitFor`, тобто факт без причини
     (перевірено мутаційно — саме так воно й виглядало). */
  await page.waitForTimeout(300);
  assert.deepEqual(dialogs, [], "видалення все ще питає діалогом браузера");
  await page.locator(".cv-ask").waitFor({ timeout: 3000 });
  assert.match(await page.locator(".cv-ask p").textContent(), /Видалити сторінку/);

  /* 2. Дефолт руйнівної дії — НЕ руйнувати, і це не лише про значення відмови:
        фокус стоїть на «Скасувати», тож Enter і пробіл, натиснуті не дивлячись
        (а над відкритим питанням це найзвичніший рефлекс), скасовують. */
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel",
    "фокус не на «Скасувати» — Enter наосліп видалив би сторінку");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(600);
  assert.equal(await page.locator(".cv-ask").count(), 0, "оверлей не закрився");
  assert.deepEqual(pages(), ["holovna", "poshuk"], "сторінку видалено без явного «так»");

  /* 3. І явне «так» таки видаляє. Без цього рядка перевірка вище лишалась би
        зеленою і над кнопкою, яка не робить нічого, — тобто стерегла б рівно ту
        поломку, від якої ця задача й починалась. */
  await menuDelete();
  await press(page, page.locator(".cv-ask [data-a='ok']"));
  await page.locator('.row[data-page="poshuk"]').waitFor({ state: "detached", timeout: 5000 });
  assert.deepEqual(pages(), ["holovna"], "підтверджене видалення не дійшло до диска");
  assert.deepEqual(dialogs, [], "видалення все ще питає діалогом браузера");
});

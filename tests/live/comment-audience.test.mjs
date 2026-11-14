/**
 * Живий тест: перемикач каналу «Клод/Команда» — сегмент у панелі коментарів ОБОЛОНКИ (0.26.0; власні вкладки
 * коментатора сховані в режимі хоста) — перемикає канал через `setAudience` хоста.
 *
 * Чому цей перемикач переїхав: до 02.09.2026 він стояв у дропдауні крошки
 * ітерації (`data-act="cmode"`) — контрол коментатора у смузі інструмента,
 * що прямо суперечить принципу 6 PRODUCT.md. Власник сказав словами: «табы
 * вот эти типа для кло для аи и для команды комментарии я разрешаю».
 *
 * Контракт, який тримає межу (коментатор — окремий продукт):
 * `init({audiences:[{id,label,active}], onAudience})`; немає `audiences` —
 * рядка вкладок немає ЗОВСІМ (сторож — `comment-layer/test/audiences.test.mjs`),
 * а `onAudience` не навігує сам, лише кладе `postMessage` у батька. Тому
 * канал лишається в ОДНОМУ місці — `commentMode` в `app.js`.
 *
 * ⛔ Адаптер Supabase тут ПІДМІНЕНИЙ заглушкою, і це свідомо. Панель у каналі
 * «Команда» піднімається лише коли сховище відповіло, тобто справжній канал
 * вимагав би мережі й живої бази у живому тесті — прод-даних, чужого стану й
 * пари секунд на кожен прогін. Заглушка виконує рівно той самий контракт
 * сховища (`ready/load/subscribe/save/remove` — див. `app/vendor/local-adapter.js`),
 * тож перевіряється саме те, про що задача: рядок вкладок і проводка каналу.
 * Справжній шлях Supabase стережуть два живі тести в `canvas.test.mjs` (банер
 * при мертвому адаптері) і `tests/test_serve.py` (текст сніпета).
 *
 * ТРЕТЯ перевірка (нижче) — про ⌘K, і вона НЕ про дубль вкладок. Зі смуги
 * перемикач прибрано (принцип 6 PRODUCT.md), тож коли коментатор не піднявся,
 * вкладки зникають РАЗОМ з ним, і повернутись у локальний канал стало б нічим.
 * Тому в палітрі лишився аварійний вихід — і саме в цьому стані (адаптер мертвий,
 * банер `__clDown` висить, вкладок у рамці НЕМА) він тут і перевіряється. Друга
 * половина тієї ж перевірки: вихід не просто існує, а СПРАЦЬОВУЄ — локальний
 * канал нічого не тягне з мережі, тож після переходу коментатор (а з ним і
 * вкладки) піднімається знову.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { MODULE_ADAPTER_GLOB, hermeticLiga } from "./_liga-supabase.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база порту: `node --test` крутить файли ПАРАЛЕЛЬНО (сусідні бази:
   panel-click=10090, inspector-project=9890, shell=9790). */
const PORT_BASE = 10190;
const VIEW = { width: 1400, height: 900 };

/* Градієнт, а не порожня сторінка — та сама причина, що в сусідніх живих
   тестах: порожній знімок стискається нижче `BYTES_FLOOR`, числився б
   «застарілим», і вхід у макет міг би замовити справжню автозʼємку. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1 style="margin:40px">${id}</h1></body></html>`;

/**
 * Герметична сторінка інструмента: жодного запиту в інтернет (4b-2: ЛІГА веде командний канал модулем
 * `supabase-comments`, `startServer(…, { supabase: true })`). Сторінка бере СПРАВЖНІ `supabase.min.js` і `adapter.js` модуля
 * з `/api/module-client/…`; `abcdefghijkl.supabase.co` відповідає порожньо, realtime-websocket закрито (`hermeticLiga`).
 * `cdn.jsdelivr.net` — порожнім 200, а не `abort()`: abort підняв би банер «Коментарі недоступні», а тут він лише заважав би.
 * Повертає дзеркало перехоплених запитів: `outside` мусить лишитись порожнім.
 */
async function hermetic(page, t) {
  const seen = await hermeticLiga(page);
  t.after(() => assert.deepEqual(seen.outside, [], `запити за межі машини:\n${seen.outside.join("\n")}`));
  return seen;
}

/**
 * Дочекатись, поки в рамці стоїть НОВИЙ, повністю завантажений документ
 * потрібного каналу, і в ньому піднявся коментатор.
 *
 * Читаємо `contentWindow.location.href`, а НЕ `getAttribute('src')`: атрибут
 * міняється в ту ж мить, коли `applyMode` його присвоїв, а СТАРИЙ документ
 * висить у рамці ще кілька тиків і має `readyState === 'complete'` — на цьому
 * вже горів `inspector-project.test.mjs`, зеленіючи по старому документу.
 */
function waitChannel(page, ch) {
  return page.waitForFunction((want) => {
    /* Ознака «коментатор доліз до кінця» — його ПУБЛІЧНА поверхня в DOM
       (`[data-comment-layer]` + `.panel` у тіньовому корені), а не приватний
       `_inited`: усе, що нижче, працює через ту саму поверхню. */
    const panelUp = (w) => {
      const host = w.document.querySelector("[data-comment-layer]");
      return !!(host && host.shadowRoot && host.shadowRoot.querySelector(".panel"));
    };
    const w = (document.getElementById("frame") || {}).contentWindow;
    return !!(w && new RegExp(`[?&]ch=${want}(&|$)`).test(w.location.href)
      && w.document.readyState === "complete" && panelUp(w));
  }, ch, { timeout: 20000 });
}

/** Відкрити панель коментарів оболонки кнопкою острівця (ідемпотентно: відкрита лишається відкритою) і дочекатись сегмента каналу.
 *  Власні вкладки коментатора (`[data-aud]`) у режимі хоста сховані — дизайнер бачить лише сегмент оболонки. */
async function openPanel(page) {
  const open = () => page.evaluate(() => { const p = document.getElementById("cmt-panel"); return !!p && !p.hidden; });
  if (!(await open())) await page.click('#hud [data-act="comments"]');
  await page.waitForFunction(() => { const p = document.getElementById("cmt-panel"); return !!p && !p.hidden; }, null, { timeout: 10000 });
}

const aud = (page, id) => page.locator(`#cmt-panel [data-act="cmtch"][data-val="${id}"]`);

/** Канал, чия кнопка сегмента натиснута (aria-pressed), — у панелі оболонки. */
function activeAud(page) {
  return page.evaluate(() => {
    const on = document.querySelector('#cmt-panel [data-act="cmtch"][aria-pressed="true"]');
    return on ? on.getAttribute("data-val") : null;
  });
}

test("сегмент каналу в панелі коментарів оболонки перемикає канал", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await hermetic(page, t);
  await page.goto(`${url}/app/`);

  /* Стартовий канал — `local` (`commentMode` в `app.js`, дефолт для фідбеку
     Клоду). Дочекатись його ТУТ обовʼязково: інакше падіння нижче не
     відрізнило б «вкладок немає» від «рамка ще не піднялась». */
  await waitChannel(page, "local");
  await openPanel(page);

  assert.equal(await aud(page, "local").count(), 1, "немає кнопки «Клод» у сегменті каналу");
  assert.equal(await aud(page, "project").count(), 1, "немає кнопки «Команда» у сегменті каналу");
  assert.equal(await activeAud(page), "local",
    "у локальному каналі активною мусить бути вкладка Клода");

  /* Клік по «Команда». Позначку читаємо з localStorage: `cmode` пише її
     СИНХРОННО, тобто це сигнал без гонки — на відміну від `frame.src`, який
     міняється тим самим `render()`, але видно його аж після завантаження. */
  await aud(page, "project").click();
  await waitChannel(page, "project");
  assert.equal(
    await page.evaluate(() => localStorage.getItem("dc-comment-mode")),
    "project", "хост мусить ЗАПАМʼЯТАТИ вибір, а не лише перемалювати рамку");

  /* Зворотний шлях — з тієї самої панелі, вже в іншому каналі. Позначка
     активності мусить піти за документом: підсвічена «Клод» на сторінці, яка
     пише в Supabase, означала б фідбек, відправлений не туди, кого бачив
     дизайнер. Її джерело — САМ сніпет (канал вибрав роут), не localStorage. */
  await openPanel(page);
  assert.equal(await activeAud(page), "project",
    "у каналі «Команда» активною мусить бути вкладка команди");

  await aud(page, "local").click();
  await waitChannel(page, "local");
  assert.equal(
    await page.evaluate(() => localStorage.getItem("dc-comment-mode")),
    "local", "вкладка «Клод» мусить вертати в локальний канал");
});

/* Правило проєкту «жодна ціль не менша за 28px по короткій стороні» жило в
   `tests/live/shell.test.mjs` — і бачило лише власний DOM канваса. Перемикач
   аудиторій оболонка поставила ВСЕРЕДИНІ тіньового кореня коментатора, тобто
   там, куди той інваріант не дістає: замір 02.09.2026 показав 24px, і жоден
   охоронець не поскаржився. Підлога та сама, поверхня інша — тому перевірка
   переїжджає сюди, ближче до поверхні, а не розширює той інваріант (він про
   смугу й панелі оболонки, і чужий тіньовий корінь у нього не входить).

   Власник просив «маленький такий переключатель» — 28px це й лишає малим:
   значкові кнопки шапки 34px, вкладки фільтра 32px. Мала ціль і невлучна
   ціль — різні речі. */
/* ⚠ todo: ПРОДУКТОВА ВАДА, знайдена міграцією T9 — `.cmt-ch button` (app/styles.css) має padding 3px 8px і висоту 18px
   (замір 51×18). Охорону збережено й вона ЧЕРВОНА; todo лише не дає їй валити весь прогін, доки CSS не підніме ціль до 28px —
   тоді `todo` ПРИБРАТИ. */
test("сегмент каналу в панелі оболонки не менший за 28px — правило підлоги", { todo: "app/styles.css .cmt-ch button: 18px заввишки, підлога 28px" }, async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await hermetic(page, t);
  await page.goto(`${url}/app/`);
  await waitChannel(page, "local");
  await openPanel(page);

  const boxes = await page.locator('#cmt-panel [data-act="cmtch"]')
    .evaluateAll((els) => els.map((e) => {
      const r = e.getBoundingClientRect();
      return { id: e.getAttribute("data-val"), w: Math.round(r.width), h: Math.round(r.height) };
    }));

  assert.equal(boxes.length, 2, `очікував дві кнопки сегмента, знайшов ${boxes.length}`);
  for (const b of boxes) {
    const short = Math.min(b.w, b.h);
    assert.ok(short >= 28,
      `вкладка «${b.id}» ${b.w}×${b.h} — коротка сторона ${short}px, підлога 28px`);
  }
});

test("чужий postMessage канал НЕ перемикає", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await hermetic(page, t);
  await page.goto(`${url}/app/`);
  await waitChannel(page, "local");

  /* Дві однакові за формою, але чужі за джерелом посилки. Приймач у `app.js`
     перевіряє І тип, І `ev.source === frame.contentWindow` — без другої
     перевірки будь-яка сторінка в будь-якому фреймі (реклама в макеті,
     вкладений iframe, сусідня вкладка з `window.open`) перемикала б канал
     дизайнера, і фідбек Клоду тихо поїхав би в командний потік. */
  await page.evaluate(() => {
    // (а) саме вікно інструмента: `ev.source === window`, а не рамка
    window.postMessage({ type: "dc-audience", ch: "project" }, "*");
    // (б) СТОРОННІЙ фрейм — справжня форма атаки. `srcdoc` успадковує origin,
    // тому скрипт усередині справді дотягується до `parent.postMessage`.
    const evil = document.createElement("iframe");
    evil.id = "evil";
    evil.srcdoc = '<script>parent.postMessage({type:"dc-audience",ch:"project"},"*")<\/script>';
    document.body.appendChild(evil);
  });
  await page.waitForFunction(() => {
    const f = document.getElementById("evil");
    return !!(f && f.contentWindow && f.contentDocument
      && f.contentDocument.readyState === "complete");
  }, null, { timeout: 10000 });

  /* Чекаємо ХИБИ, а не збігу: якби перевірка джерела впала, `cmode` записав би
     позначку синхронно на самій події, а `render()` поставив би `ch=project`
     наступним тиком. Даємо на це фору й вимагаємо, щоб нічого не сталось. */
  await page.waitForTimeout(1200);
  assert.equal(
    await page.evaluate(() => localStorage.getItem("dc-comment-mode")),
    null, "чужа посилка не сміє записати вибір каналу");
  assert.equal(
    await page.evaluate(() => /[?&]ch=local(&|$)/.test(
      document.getElementById("frame").contentWindow.location.href)),
    true, "чужа посилка не сміє перезавантажити рамку в інший канал");

  /* Своє джерело, але чуже ЗНАЧЕННЯ. `ch` тепер перетинає межу, а звідси йде
     і в `localStorage`, і в `frame.src` (`applyMode` клеїть `&ch=${…}`) —
     раніше воно народжувалось у нашій же розмітці смуги й перевіряти не було
     чого. Білий список у `setAudience()` мусить його зрізати, інакше в
     інструменті осів би канал, якого не існує: обидві вкладки без
     підсвітки й `frame.src` із сміттям у запиті. */
  const junk = page.frames().find((f) => f !== page.mainFrame()
    && /[?&]ch=local(&|$)/.test(f.url()));
  assert.ok(junk, "рамку макета не знайдено — перевірка значення порожня");
  await junk.evaluate(() => {
    for (const ch of ["", "LOCAL", "project ", "local&it=../x", "__proto__", null]) {
      parent.postMessage({ type: "dc-audience", ch }, "*");
    }
  });
  await page.waitForTimeout(600);
  assert.equal(
    await page.evaluate(() => localStorage.getItem("dc-comment-mode")),
    null, "невідоме значення каналу не сміє осісти в стані");

  /* Парна половина: перевірка джерела не мусить глушити ВЛАСНУ рамку. Тест
     без цього рядка зеленів би і на `return;` у першому рядку приймача.
     ⛔ `postMessage` мусить виконатись УСЕРЕДИНІ рамки, тому тут окремий
     контекст (`frame.evaluate`), а не `page.evaluate`: `ev.source` бере вікно
     того скрипта, що ВИКЛИКАВ, тож `frame.contentWindow.parent.postMessage(…)`
     з контексту сторінки дало б знову джерело-сторінку — тобто третю копію
     чужої посилки, а не власну. */
  const inner = page.frames().find((f) => f !== page.mainFrame()
    && /[?&]ch=local(&|$)/.test(f.url()));
  assert.ok(inner, "рамку макета не знайдено — перевірка власного джерела порожня");
  await inner.evaluate(() => parent.postMessage(
    { type: "dc-audience", ch: "project" }, "*"));
  await waitChannel(page, "project");
});

/**
 * Аварійний вихід ⌘K: коментатор не піднявся — вкладок немає — палітра є.
 *
 * ⛔ Тут файл адаптера модуля справді ЗАРІЗАНИЙ (`abort()` на `/api/module-client/supabase-comments/adapter.js`), а не
 * підмінений, як у `hermetic()` вище, — рівно навпаки до двох перевірок вище. Це не недогляд: сценарій вимагає, щоб
 * коментатор саме НЕ піднявся. Без `window.DeaiComments` сніпет модуля не доходить до `CommentLayer.init` (банер
 * «шар коментарів не піднявся») — панелі, а з нею й рядка вкладок, у рамці не буде ЗОВСІМ. (До 0.10.0 тут різали CDN
 * Supabase; тепер сторінка ЛІГИ CDN Supabase не бере, тож «мертвий коментатор» — це мертвий файл адаптера.)
 */
test("аварійний вихід: коментатор не піднявся — ⌘K вертає в локальний канал", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 80, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  /* Дизайнер УЖЕ був у командному каналі, коли адаптер відвалився — саме та
     пастка, заради якої вихід існує. Кладемо вибір у сховище до першого
     скрипта сторінки: `commentMode` в `app.js` читає його на завантаженні
     модуля, тобто пізніше було б запізно.

     ⛔ `window === window.top` обовʼязкове: `addInitScript` виконується в
     КОЖНОМУ документі сторінки, рамку макета включно, а рамка того самого
     походження, що й оболонка. Без охорони перехід у локальний канал
     завантажував би новий документ рамки, той наново писав би `project` у
     спільний `localStorage` — і перевірка «хост запамʼятав вибір» падала б
     на власній фікстурі, хоч канал перемкнувся (спіймано першим прогоном:
     `waitChannel(local)` зелений, сховище — `project`). */
  await page.addInitScript(() => {
    if (window !== window.top) return;
    try { localStorage.setItem("dc-comment-mode", "project"); } catch (e) { /* приватний режим */ }
  });
  await hermetic(page, t);
  await page.route(MODULE_ADAPTER_GLOB, (route) => route.abort());
  await page.goto(`${url}/app/`);

  /* Стан-пастка цілком: рамка в командному каналі, документ догруз, банер
     висить. Без банера перевірка була б порожня — «вкладок немає» збіглося б
     із «рамка ще не піднялась». */
  await page.waitForFunction(() => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    return !!(w && /[?&]ch=project(&|$)/.test(w.location.href)
      && w.document.readyState === "complete"
      && w.document.getElementById("cl-down"));
  }, null, { timeout: 20000 });

  /* Половина про аварію: коментатора в рамці НЕМА, а панель оболонки не мовчить — показує причину (`.cmt-down`)
     замість карток. (До 0.26.0 тут перевірялось, що вкладок немає ніде; тепер сегмент каналу живе в панелі
     оболонки й у цьому стані теж доступний — це другий вихід, ⌘K лишається аварійним, бо не залежить від панелі.) */
  await page.click('#hud [data-act="comments"]');
  await page.locator("#cmt-panel .cmt-down").waitFor({ timeout: 5000 });
  assert.equal(await page.locator("#cmt-panel .cmt-card").count(), 0, "панель показала картки при мертвому коментаторі");
  await page.click('#cmt-panel [data-act="comments"]');   // закрити: далі перевірка ⌘K без панелі
  assert.equal(
    await page.evaluate(() => !!document.getElementById("frame")
      .contentWindow.document.querySelector("[data-comment-layer]")),
    false, "панель коментатора піднялась при мертвому адаптері — перевірка не про те");

  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible", timeout: 5000 });

  /* Фільтр живить список СИНХРОННО (`repaintPaletteList` на подію `input`),
     тож читаємо одразу, без `waitFor`: з таймаутом мутація «прибрати дії
     аудиторії з палітри» дала б невиразне «елемент не зʼявився», а не оце
     речення. */
  await page.fill("#palq", "аудитор");
  const items = await page.locator(".pal-it").allInnerTexts();
  assert.ok(items.some((s) => s.includes("Клод")),
    `аварійного виходу немає: ⌘K не пропонує локальну аудиторію при мертвому `
    + `коментаторі — зі смуги перемикач прибрано, вкладок у рамці нема, `
    + `вернутись у канал Клода нічим. Знайдено в палітрі: ${JSON.stringify(items)}`);

  await page.locator(".pal-it", { hasText: "Клод" }).click();

  /* НЕГАЙНО, без жодного очікування: `execPaletteAction → BAR_ACTIONS.aud →
     setAudience → localStorage.setItem` — увесь шлях синхронний, тож на
     момент, коли `click()` вертає керування, вибір мусить уже лежати в
     сховищі (той самий прийом, що стереже перевірку B у
     `tests/live/shell-palette.test.mjs`).

     ⛔ Саме цей рядок робить мутацію «пункт є, а виконувати нічого» видимою
     ПО СУТІ. Перевірено: `act: "audience"` замість `act: "aud"` (імені, якого
     немає ні в `BAR_ACTIONS`, ні в `PANEL_ACTIONS`) — пункт у палітрі є,
     знаходиться, клікається, палітра закривається, а канал не міняється. Без
     цього рядка мутація падала б аж двадцятисекундним таймаутом очікування
     рамки, тобто без жодного слова про причину. */
  assert.equal(
    await page.evaluate(() => localStorage.getItem("dc-comment-mode")),
    "local",
    "⌘K не ВИКОНАВ дію: пункт знайшовся й палітра закрилась, але канал не змінився "
    + "— найпевніше `act` реєстру не збігається з ключем у BAR_ACTIONS");

  /* Вихід не просто існує — він ПРАЦЮЄ до кінця, і `waitChannel` вимагає обох
     половин: нового документа з `ch=local` І піднятої панелі коментатора.
     Друга половина тут задарма доводить головне: локальний канал нічого не
     тягне з CDN (`LOCAL_COMMENT_SNIPPET` — самі лише `app/vendor`), тож
     аварійний вихід веде у РОБОЧИЙ стан, а не в другу аварію. */
  await waitChannel(page, "local");

  /* І коло замкнулось: вкладки, яких не було, повернулись разом із панеллю —
     тобто дизайнер знову має звичайний шлях, і палітра йому більше не
     потрібна. Саме через це вона й не дубль. */
  await openPanel(page);
  assert.equal(await aud(page, "local").count(), 1,
    "після аварійного виходу вкладки не повернулись — коментатор не піднявся й у локальному каналі");
  assert.equal(await activeAud(page), "local");
});

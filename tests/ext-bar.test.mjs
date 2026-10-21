/**
 * Смуга ЗОВНІШНЬОЇ оболонки (опубліковане превʼю). Юніт тримає дві речі
 * одразу, і друга не менш важлива за першу:
 *
 *   · що смуга НЕСЕ — назву задачі текстом, крошку ітерації з переліком,
 *     «Макет / Огляд», перемикач ширин, «Копіювати посилання»;
 *   · що вона НЕ несе — GitLab, публікацію, інспектора, палітру, зʼємку.
 *     Перелік відсутнього стережеться так само явно, як перелік присутнього:
 *     смуга зовнішнього превʼю — статика в чужому браузері, і кожен контрол,
 *     за яким немає сервера, це кнопка-обіцянка, яку нічим виконати. Без
 *     цього тесту такий контрол приїжджає туди першою ж копіпастою з
 *     `shell-bar.js`.
 *
 * Чому окрема збірка смуги, а не `barModel()` з прапорцем «зовнішній»:
 * рішення й ціна записані в плані (розділ «Чому bar-model НЕ переїжджає») —
 * гілки «зовнішній/внутрішній» у модулі, від якого залежить інструмент,
 * дорожчі за два місця збірки. Спільними лишаються мова CSS, іконки й
 * словник — саме за це тут і тримаємось (`.ctl`, `.seg`, `.crumb`, `.dd`).
 */
import assert from "node:assert/strict";
import test from "node:test";

import { extBarHTML } from "../app/ext-bar.js";

const S = (o = {}) => ({
  task: "Віджет «Суди»",
  iterLabel: "Іт.3",
  iterNote: "Правки",
  iters: [{ id: "it1", label: "Іт.1", note: "старт", on: false },
    { id: "it3", label: "Іт.3", note: "Правки", on: true }],
  openDd: null,
  mode: "layout",
  overviewWhyKey: "",
  vp: "desktop",
  copied: false,
  error: "",
  ...o,
});

const html = (o) => extBarHTML(S(o));

/* Три зони — той самий грид `minmax(0,1fr) auto minmax(0,1fr)`, що в
   інструменті (`.bar` у styles.css, який їде в publish/shell/ без правок).
   Четверта зона зламала б центрування «Макет / Огляд» так само, як зламала б
   його всередині. */
test("розмітка дає рівно три зони", () => {
  assert.equal((html().match(/class="zone /g) || []).length, 3);
});

/* Назва задачі — ТЕКСТ, не дропдаун: задача в превʼю одна, і перемикати
   нічого. Дропдаун тут був би контролом, за яким нема куди йти. */
test("назва задачі — текстом, без дропдауна задач", () => {
  const h = html();
  assert.ok(h.includes("Віджет «Суди»"), "назви задачі в смузі немає");
  assert.ok(!h.includes('data-dd="task"'),
    "дропдаун задач у зовнішній смузі нікуди не веде — задача одна");
  assert.ok(!h.includes('data-act="task"'), "те саме про дію переключення задачі");
});

/* Назви пише дизайнер, а сюди вони приїжджають із маніфеста — тобто з файла,
   який лежить у publish/ і його вміст ми в браузері глядача не контролюємо. */
test("назва задачі екранується", () => {
  const h = html({ task: '</span><img src=x onerror=alert(1)>' });
  assert.ok(!h.includes("<img"), "тег приїхав у документ сирим");
  assert.ok(h.includes("&lt;img"), "екранування не спрацювало");
});

/* Підпис ітерації приїжджає тим самим шляхом і тим самим не заслуговує
   довіри: `iteration_label()` складає його з `note`, який пише дизайнер. */
/* Дві ітерації, а не одна: перелік малюється лише коли є що перемикати, і на
   одній ітерації рядок дропдауна взагалі не виконався б — тест був би зелений
   там, де нічого не перевірив. `<svg` тут шукати не можна: іконки самі
   `<svg>`, тому мішень — саме `onload=`. */
test("підпис ітерації екранується — і тег, і примітка, і в крошці, і в переліку", () => {
  const h = html({ iterLabel: '<img src=x>', iterNote: '<b onmouseover=1>',
    openDd: "iter",
    iters: [{ id: "it1", label: '<svg onload=1>', note: '<i onerror=2>', on: false },
      { id: "it3", label: "Іт.3", note: "Правки", on: true }] });
  assert.ok(!h.includes("<img"), "тег крошки приїхав сирим");
  assert.ok(!h.includes("<b onmouseover"), "примітка крошки приїхала сирою");
  assert.ok(!h.includes("<svg onload"), "тег у переліку приїхав сирим");
  assert.ok(!h.includes("<i onerror"), "примітка в переліку приїхала сирою");
  assert.ok(h.includes("&lt;svg onload=1&gt;"), "екранування переліку не спрацювало");
});

/**
 * Тег і примітка — ДВА вузли, і це несуче, а не косметика.
 *
 * `.txt--fix{flex:none}` не обрізається НІКОЛИ, `.txt--soft` обрізається
 * завжди (`styles.css`, і в крошки ітерації там ще `max-width:112px`). Одним
 * рядком примітка зʼїдала тег — крошка перестала відповідати на питання «яку
 * версію я бачу» рівно там, де місця мало. Той самий розділ, що в
 * `shell-bar.js` усередині інструмента, і на ньому ж тримається інваріант
 * «крошку не стиснуло браком місця» (`tests/live/shell.test.mjs`).
 */
test("крошка ітерації: тег у незрізаному вузлі, примітка в зрізаному", () => {
  const crumb = /<button class="ctl crumb crumb--iter"[\s\S]*?<\/button>/.exec(html());
  assert.ok(crumb, "крошки-кнопки ітерації немає");
  assert.ok(crumb[0].includes('<span class="txt txt--fix">Іт.3</span>'),
    `тег мусить стояти в .txt--fix — його не обрізає ніколи:\n${crumb[0]}`);
  assert.ok(crumb[0].includes('<span class="txt txt--soft">· Правки</span>'),
    `примітка мусить стояти в .txt--soft — обрізається саме вона:\n${crumb[0]}`);
});

/* Те саме розділення й на пласкій крошці (одна ітерація): вона малюється
   іншою гілкою, і без тесту та гілка лишилась би з одним вузлом. */
test("пласка крошка теж розділяє тег і примітку", () => {
  const h = html({ iters: [{ id: "it3", label: "Іт.3", note: "Правки", on: true }] });
  assert.ok(h.includes('<span class="txt txt--fix">Іт.3</span>'), "тега немає");
  assert.ok(h.includes('<span class="txt txt--soft">· Правки</span>'), "примітки немає");
  // `title` несе ПОВНИЙ підпис: примітку обрізає CSS, і без нього довгу
  // примітку не прочитати ніяк.
  assert.ok(h.includes('title="Іт.3 · Правки"'), `повного підпису в title немає:\n${h}`);
});

/* `crumb--page` — модифікатор крошки СТОРІНКИ оверлею інструмента (`homeCrumbs` у `shell-bar.js`): він знімає ліміт ширини
   (`.crumb.crumb--page{max-width:none}`). Зовнішня оболонка превʼю бере той самий `styles.css`, але її крошки (задача, ітерація)
   ліміт мусять зберегти — тож модифікатор тут не з'являється ні в одній гілці: ні для задачі, ні для ітерації-кнопки, ні для
   пласкої крошки однієї ітерації. */
test("крошки зовнішньої смуги не мають `crumb--page` — ні задача, ні ітерація (кнопка й пласка), ні з розкритим переліком", () => {
  const one = [{ id: "it3", label: "Іт.3", note: "Правки", on: true }];
  for (const [name, o] of Object.entries({ "типовий стан": {}, "одна ітерація (пласка крошка)": { iters: one }, "розкритий перелік": { openDd: "iter" },
    "без примітки": { iterNote: "" }, "Огляд": { mode: "overview", vp: "tablet" }, "помилка": { error: "boom" } })) {
    const h = html(o);
    assert.ok((h.match(/class="[^"]*\bcrumb\b/g) ?? []).length >= 2, `${name}: крошок нема — перевірка нічого не міряла`);
    assert.doesNotMatch(h, /crumb--page/, `${name}: зовнішня смуга перейняла модифікатор сторінки оверлею`);
  }
});

/* Порожня примітка не сміє малювати вузол із самим розділювачем: «Іт.3 ·»
   читається як обрізаний текст, тобто як зламана крошка. */
test("ітерація без примітки не лишає осиротілого розділювача", () => {
  const h = html({ iterNote: "",
    iters: [{ id: "it3", label: "Іт.3", note: "", on: true }] });
  assert.ok(!h.includes("txt--soft"), `порожня примітка намалювала вузол:\n${h}`);
  assert.ok(h.includes('title="Іт.3"'), "у title приїхав розділювач у нікуди");
});

/* У ПЕРЕЛІКУ дропдауна тег і примітка склеюються в один рядок — так само, як
   у `shell-bar.js`: пункт списку обрізає браузер, і два вузли там нічого не
   дають, а ось «Іт.1 ·» без примітки виглядав би обрізаним. */
test("пункт переліку склеює тег із приміткою, а без примітки лишає тег", () => {
  assert.ok(html({ openDd: "iter" }).includes("Іт.1 · старт"),
    "у пункті переліку немає примітки");
  const bare = html({ openDd: "iter",
    iters: [{ id: "it1", label: "Іт.1", note: "", on: false },
      { id: "it3", label: "Іт.3", note: "Правки", on: true }] });
  assert.ok(!bare.includes("Іт.1 ·"), `порожня примітка дала розділювач у нікуди:\n${bare}`);
  assert.ok(bare.includes("Іт.1"), "самого тега в пункті теж немає");
});

test("крошка ітерації — дропдаун із переліком ітерацій", () => {
  const closed = html();
  assert.ok(closed.includes('data-dd="iter"'), "крошки ітерації немає");
  assert.ok(!closed.includes('class="dd"'), "закритий дропдаун не малюється");
  assert.ok(closed.includes("Іт.3"), "тега поточної ітерації немає");
  assert.ok(closed.includes("Правки"), "примітки поточної ітерації немає");

  const open = html({ openDd: "iter" });
  assert.ok(open.includes('class="dd"'), "відкритий дропдаун не намалювався");
  assert.ok(open.includes('data-act="iter" data-val="it1"'), "немає пункту it1");
  assert.ok(open.includes('data-act="iter" data-val="it3"'), "немає пункту it3");
  // Поточна ітерація позначена — інакше в переліку з пʼяти не видно, де стоїш.
  const cur = /<button class="([^"]*)"[^>]*data-val="it3"/.exec(open);
  assert.ok(cur && cur[1].includes("dd-item--on"),
    "поточна ітерація в переліку не позначена");
});

/* ⛔ Дій над ітерацією (створити / перейменувати / дублювати / видалити) у
   зовнішньому дропдауні НЕМА: за ними стоїть `/api/*`, якого в статиці не
   існує. Перелік — усе, що тут може працювати. */
test("дропдаун ітерації несе лише перелік, без дій над ітерацією", () => {
  const h = html({ openDd: "iter" });
  for (const act of ["newit", "renit", "dupit", "delit"]) {
    assert.ok(!h.includes(`data-act="${act}"`), `дія «${act}» у статиці мертва`);
  }
});

/* Одна ітерація — крошка лишається (вона каже «де я»), але дропдаун не
   обіцяє переключення, якого нема куди робити. */
test("єдина ітерація не дає дропдауна, але сама крошка лишається", () => {
  const h = html({ iters: [{ id: "it3", label: "Іт.3", note: "Правки", on: true }],
    openDd: "iter" });
  assert.ok(h.includes("Іт.3"), "тег ітерації мусить лишитись");
  assert.ok(h.includes("Правки"), "примітка ітерації мусить лишитись");
  assert.ok(!h.includes('data-dd="iter"'),
    "перемикати нема на що — дропдаун був би порожньою обіцянкою");
  assert.ok(!h.includes('class="dd"'), "і сам перелік не малюється");
});

test("сегмент «Макет / Огляд» — два перемикачі з поточним станом", () => {
  const h = html();
  assert.ok(h.includes('data-act="mode" data-val="layout"'), "немає «Макета»");
  assert.ok(h.includes('data-act="mode" data-val="overview"'), "немає «Огляду»");
  const layout = /<button data-act="mode" data-val="layout"[^>]*>/.exec(h);
  assert.ok(layout && layout[0].includes('aria-pressed="true"'),
    "поточний режим не позначений");
  const over = /<button data-act="mode" data-val="overview"[^>]*>/
    .exec(html({ mode: "overview" }));
  assert.ok(over && over[0].includes('aria-pressed="true"'),
    "перемикання режиму не переносить позначку");
});

/* Причина ВИДИМА, а не в title: те саме правило, що для смуги інструмента —
   вимкнений контрол, який не каже чому, читається як зламаний. */
test("«Огляд» без кадрів вимкнений і каже причину видимим текстом", () => {
  const h = html({ overviewWhyKey: "shotsNone" });
  const btn = /<button data-act="mode" data-val="overview"[\s\S]*?<\/button>/.exec(h);
  assert.ok(btn, "кнопка «Огляд» не розібралась");
  assert.ok(btn[0].includes("disabled"), "«Огляд» без кадрів мусить бути вимкнений");
  assert.ok(btn[0].includes('class="dd-why"'), "причина не намалювана рядком");
  assert.ok(btn[0].includes("кадрів ще немає"), "причина не зі словника");
  // І навпаки: з кадрами кнопка жива й причини немає.
  const ok = /<button data-act="mode" data-val="overview"[\s\S]*?<\/button>/.exec(html());
  assert.ok(!ok[0].includes("disabled"), "«Огляд» із кадрами вимикати нема за що");
  assert.ok(!ok[0].includes("dd-why"), "причина без причини");
});

test("перемикач ширин — три пресети з поточним", () => {
  const h = html();
  for (const id of ["desktop", "tablet", "mobile"]) {
    assert.ok(h.includes(`data-act="vp" data-val="${id}"`), `немає пресета «${id}»`);
  }
  const cur = /<button data-act="vp" data-val="desktop"[^>]*>/.exec(h);
  assert.ok(cur[0].includes('aria-pressed="true"'), "поточна ширина не позначена");
  const tab = /<button data-act="vp" data-val="tablet"[^>]*>/.exec(html({ vp: "tablet" }));
  assert.ok(tab[0].includes('aria-pressed="true"'), "вибір ширини не переїхав");
});

/* Пресети беруться з `viewport.js`, а не переписуються тут своїм масивом:
   модуль їде в `publish/shell/` без правок, і четвертий пристрій, доданий
   колись у ньому, мусить приїхати в обидві смуги сам. Тест звіряє САМ СКЛАД
   із джерелом — дубль у зовнішній смузі інакше розійшовся б молча. */
test("склад перемикача ширин узятий із viewport.js", async () => {
  const { PRESETS } = await import("../app/viewport.js");
  const ids = [...html().matchAll(/data-act="vp" data-val="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, PRESETS.map((p) => p.id));
});

/* ⛔ Найдорожча пастка цієї смуги, і вона вже стріляла в Плані A всередині
   інструмента: `.view-extra` ховає контрол контейнерним запитом на 1060px, а
   заміна («⋯ Вигляд») зʼявляється тим самим CSS. У зовнішній смузі меню «⋯»
   НЕМА за задумом — тобто `view-extra` тут означав би «перемикач ширин
   недосяжний ЗОВСІМ на вузькому екрані», а не «переїхав у меню». Саме так
   керування виглядом і зникало 01.09.2026. */
test("перемикач ширин не носить класів, якими CSS ховає його в «⋯»", () => {
  const h = html();
  assert.ok(!h.includes("view-extra"),
    "у зовнішній смузі немає меню «⋯», тому схований контрол просто зникає");
  assert.ok(!h.includes("view-more"), "того самого меню «⋯» тут немає й бути не має");
});

test("«Копіювати посилання» є і підтверджує копіювання", () => {
  const h = html();
  assert.ok(h.includes('data-act="copylink"'), "кнопки посилання немає");
  assert.ok(h.includes("Скопіювати посилання"), "підпис не зі словника");
  const done = html({ copied: true });
  assert.ok(done.includes("Посилання скопійовано"),
    "після копіювання кнопка мусить це сказати — інакше клік виглядає як промах");
});

/* Смуга помилки — той самий `.errbar`, що в інструменті: маніфест не
   прочитався (єдине джерело правди статики), і глядач мусить це побачити, а
   не дивитись у порожню оболонку. Текст приходить ГОТОВИМ рядком: перекладає
   його проводка, як `pagesError` у панелі. */
test("смуга помилки малюється лише коли є що сказати", () => {
  assert.ok(!html().includes("errbar"), "без помилки смуги помилки бути не має");
  const h = html({ error: "манифест не читається" });
  assert.ok(h.includes('class="errbar"'), "смуги помилки немає");
  assert.ok(h.includes("манифест не читається"), "текст помилки не показаний");
  assert.ok(h.includes('data-act="retry"'), "повторити нічим");
});

/* Перелік відсутнього — половина сенсу цього файла (див. шапку). */
test("смуга НЕ несе GitLab, публікації, інспектора, палітри й зʼємки", () => {
  const h = html({ openDd: "iter" });
  const forbidden = [
    'data-dd="gl"', 'data-act="glpush"', 'data-act="glpull"', 'data-act="glsetup"',
    'data-act="publish"', 'data-dd="pub"', 'data-act="togglepub"',
    'data-act="openpreview"', 'data-act="inspector"', 'data-act="palette"',
    'data-act="shoot"', 'data-act="newpage"', 'data-act="pagemenu"',
    'class="split', 'data-act="vpw"',
  ];
  for (const f of forbidden) {
    assert.ok(!h.includes(f), `у зовнішній смузі не має бути ${f}`);
  }
});

/* Спільна мова CSS — не косметика: `styles.css` їде в `publish/shell/` без
   правок, тобто ЄДИНЕ, що робить зовнішню смугу схожою на внутрішню, це
   однакові імена класів. Розійдись вони — і смуга приїде без стилів, а
   помітить це глядач, не ми. */
test("класи ті самі, що в смузі інструмента", () => {
  const h = html({ openDd: "iter" });
  for (const cls of ["bar", "zone zone-1", "zone zone-2", "zone zone-3",
    "crumbs", "ctl", "seg", "dd", "dd-item"]) {
    assert.ok(h.includes(`class="${cls}`) || h.includes(` ${cls}`),
      `клас «${cls}» зник — смуга приїде без стилів`);
  }
});

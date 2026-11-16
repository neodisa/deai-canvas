import assert from "node:assert/strict";
import test from "node:test";

import { barModel } from "../app/bar-model.js";
import { barHTML } from "../app/shell-bar.js";
import { setLang, t } from "../app/i18n.js";

const S = (o = {}) => ({
  mode: "layout", view: "grid", vp: "desktop", vpw: "",
  taskId: "LIGA-7003", iterLabel: "Іт.3", iterNote: "Правки",
  hasIteration: true, iterPub: true, iterOnGl: false,
  flowRaw: true, pagesError: "", flowError: "",
  gl: "sync", published: true, pubStale: false, pagePub: true,
  right: null, tasksErr: false, ...o,
});

const html = (o) => barHTML(barModel(S(o)), S(o));

/* Три зони мусять бути трьома вузлами: на них тримається грид
   `minmax(0,1fr) auto minmax(0,1fr)`, і четверта зона зламала б центрування. */
test("розмітка дає рівно три зони", () => {
  assert.equal((html().match(/class="zone /g) || []).length, 3);
});

/* 0.25.0: логотип, двері в палітру, пігулка оновлення, «Відгук», перемикач задач і «Назад» зі смуги ПЕРЕЇХАЛИ (рядок вкладок —
   `tabs-view.js`, острівець — `island.js`; палітра лишилась лише на ⌘K, її акорд оголошує логотип). Смуга їх не малює ні на
   одному екрані — інакше вони стояли б у двох місцях. */
test("смуга не малює ні логотипа, ні палітри, ні пігулки, ні «Відгуку», ні інспектора, ні перемикача задач", () => {
  const taskList = [{ id: "a", jira: "", title: "Перша" }];
  for (const o of [{}, { hasIteration: false }, { homeOpen: true }, { homeOpen: true, homePage: "conn", taskId: "t1" },
    { homeOpen: true, homePage: "wiz" }, { mode: "overview" }, { update: { current: "0.1.0", latest: "0.2.0", available: true, state: "ok" } },
    { openDd: "task", taskList }, { space: { id: "a", name: "A", color: "space-1" } }]) {
    const h = html(o);
    assert.doesNotMatch(h, /data-act="(palette|home|update|feedback|inspector|back|task)"/, JSON.stringify(o));
    assert.doesNotMatch(h, /data-dd="task"|logo-btn|pal-open|upd-pill|fb-btn|task-q|dd--tasks/, JSON.stringify(o));
  }
});

/* Смуга задачі: крошка ітерації, а за нею — назва задачі приглушено й нерухомо (це не перемикач: «де я» каже вкладка). */
test("смуга задачі: крошка ітерації, потім назва задачі — плоска, приглушена, з повною назвою в title", () => {
  const h = html({ taskTitle: 'Картка "клієнта"' });
  assert.match(h, /<span class="crumb crumb--flat crumb--title" title="Картка &quot;клієнта&quot;"><span class="txt">Картка &quot;клієнта&quot;<\/span><\/span>/);
  assert.ok(h.indexOf('data-dd="iter"') < h.indexOf("crumb--title"), "назва — після крошки ітерації");
  assert.ok(h.indexOf("crumb--title") < h.indexOf('class="zone zone-2"'), "назва лишається в зоні 1");
  assert.doesNotMatch(/<span class="crumb crumb--flat crumb--title"[\s\S]*?<\/span><\/span>/.exec(h)[0], /<button|data-/, "назва — не контрол");
});

test("назва задачі екранується", () => {
  const h = html({ taskTitle: '<img src=x onerror="alert(1)">' });
  assert.ok(!h.includes("<img src=x"));
});

/* Екран «Задачі»: три зони лишаються в DOM (грид на них тримається), але склад інший — лише «де я». */
test("екран «Задачі»: крошка «Задачі», без «Назад», логотипа, макета й публікації", () => {
  const h = html({ homeOpen: true });
  assert.equal((h.match(/class="zone /g) || []).length, 3, "зон мусить лишитись три");
  assert.match(h, /crumb--flat[^>]*>[\s\S]*?Задачі/, "немає плоскої крошки «Задачі»");
  assert.ok(!/data-dd="iter"/.test(h), "крошка ітерації на екрані «Задачі» зайва");
  assert.ok(!/crumb--title/.test(h), "назва задачі на екрані «Задачі» зайва");
  assert.ok(!/data-act="publish"/.test(h), "публікація без вигляду задачі безглузда");
  assert.ok(!/data-act="mode"/.test(h), "сегмент «Макет/Огляд» без задачі безглуздий");
});

/* Кожен контрол моделі мусить доїхати до розмітки з тим самим ідентифікатором:
   інакше делегація в app.js (Task 3) його не знайде, і кнопка нічого не
   робитиме — а жоден юніт цього не побачить. */
test("кожен контрол моделі має data-act або data-dd у розмітці", () => {
  const m = barModel(S());
  const h = barHTML(m, S());
  for (const item of [...m.zone2, ...m.zone3]) {
    assert.ok(h.includes(`data-act="${item.id}"`) || h.includes(`data-dd="${item.id}"`),
      `контрол «${item.id}» не доїхав до розмітки`);
  }
});

/* Причина відключення мусить бути ВИДИМИМ текстом, а не лише в title: саме це
   «причина видима» зі спеки. Клас `.dd-why` — той, що малює її рядком. */
test("вимкнений пункт несе причину класом dd-why, не лише title", () => {
  assert.match(html({ mode: "overview", flowRaw: null }), /dd-why/);
});

/* Ярус зашивається класом, бо ховає його CSS, не JS: клас — контракт між
   моделлю і контейнерним запитом. Розбіжність тут дала б контрол, який модель
   вважає схованим, а CSS показує. */
test("яруси зашиваються класами lbl-mode / lbl-gl / view-extra / view-more", () => {
  const h = html();
  for (const cls of ["lbl-mode", "lbl-gl", "view-extra", "view-more"]) {
    assert.match(h, new RegExp(cls), `немає класу ${cls}`);
  }
});

/* На 1024 підпис публікації ховався, а іконки в опублікованому стані не було —
   кнопка лишалась 20-піксельним нічим. Іконка є ЗАВЖДИ. */
test("split-кнопка публікації має іконку в кожному стані", () => {
  /* Дивимось у ВМІСТ саме цієї кнопки, а не в вікно з N символів після її
     класу. Перша версія тесту брала `[\s\S]{0,200}?<svg` і проходила навіть
     без іконки — бо в те вікно потрапляв <svg> сусідньої `split-more`
     (шеврона). Охоронець, що проходить із чужої причини, гірший за
     відсутній: він каже «перевірено» там, де не перевірено нічого. */
  for (const o of [{}, { published: false }, { pubStale: true }]) {
    const m = /<button class="split-main"[^>]*>([\s\S]*?)<\/button>/.exec(html(o));
    assert.ok(m, `не знайдено кнопку split-main при ${JSON.stringify(o)}`);
    assert.match(m[1], /<svg/,
      `публікація без власної іконки при ${JSON.stringify(o)}`);
  }
});

/* Смуга помилки — частина того ж рендера, а не окремий вузол: інакше вона
   зʼявилась би поза гридом і накрила б зони. */
test("tasksErr дає смугу помилки під зонами", () => {
  assert.match(html({ tasksErr: true }), /class="errbar"/);
  assert.doesNotMatch(html(), /class="errbar"/);
});

/* Крошка ітерації усікається СТРУКТУРНО: `Іт.3` — ідентичність, не усікається
   ніколи; примітка — комфорт. Один спан замість двох дав би на 1440 наїзд
   зони крошок на перемикач режиму (виміряно: переповнення 51px). */
test("крошка ітерації — два спани: номер незмінний, примітка усікається", () => {
  const h = html();
  assert.match(h, /txt--fix/);
  assert.match(h, /txt--soft/);
});

/* Назви задач і приміток ідуть із tasks.json — файла, який правлять руками.
   `<img src=x onerror=…>` у назві не сміє стати розміткою. */
test("текст із моделі екранується", () => {
  const h = html({ taskId: '<img src=x onerror="alert(1)">' });
  assert.ok(!h.includes("<img src=x"), "розмітка з даних доїхала неекранованою");
  assert.match(h, /&lt;img/);
});

/* Без ітерацій крошки ітерації немає взагалі — так само, як зникає «Флоу» поза «Оглядом».
   «Є, але вимкнена» читалось би як «щось поламалось». Назва задачі лишається. */
test("без ітерацій крошки ітерації немає, назва задачі лишається", () => {
  const h = html({ hasIteration: false });
  assert.match(h, /crumb--title/);
  assert.doesNotMatch(h, /data-dd="iter"/);
});

/* Дропдаун малюється лише коли відкритий: тримати в DOM усі закриті меню
   означає платити за них на кожному рендері й ловити їхні `id` пошуком. */
test("дропдаун малюється лише для відкритого меню", () => {
  assert.doesNotMatch(html(), /class="dd"/);
  assert.match(barHTML(barModel(S()), S({ openDd: "iter" })), /class="dd"/);
});

/* Принцип 6 PRODUCT.md: контролів коментатора у смузі оболонки немає.
   Перемикач аудиторії стояв у дропдауні крошки ітерації ТИМЧАСОВО, і причина
   зволікання записана в CHANGELOG: він жене `&ch=` в URL рамки, тож прибрати
   його без нового дому означало б функціональний регрес. Дім тепер є —
   вкладки в панелі САМОГО коментатора (`audiences` в `init`, `app/serve.py`),
   а в ⌘K лишився аварійний вихід на випадок, коли коментатор не піднявся.

   ⛔ Перевіряємо КОЖЕН дропдаун смуги, а не лише ітераційний. «Прибрали з
   одного, поклали в сусідній» — рівно та половинчаста правка, яку принцип 6
   забороняє, і саме так цей контрол уже їздив: спершу «⋯ Вигляд» (де CSS
   ховав його на будь-якій ширині понад 1060px — недосяжний ЗОВСІМ, знайдено
   живим тестом), далі крошка ітерації. Перевірка одного дропдауна
   зеленіла б на третьому переїзді.

   ⛔ Друга половина не знає ІМЕНІ дії: `data-val="local"|"project"` — це
   значення самого каналу, і жоден інший контрол смуги таких значень не має
   (ітерації — `it1`, режим — `layout`/`overview`, вигляд — `grid`/`flow`,
   ширина — `desktop`/`tablet`/`mobile`, зона 3 — імена своїх дій). Тобто
   перейменований `cmode` не пролізе мимо перевірки, яка пам’ятає лише старе
   ім’я, — а перейменування тут імовірне, бо дія в ⌘K уже зветься `aud`. */
test("у смузі немає перемикача аудиторії — ні в жодному дропдауні", () => {
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  const taskList = [{ id: "LIGA-7003", jira: "LIGA-7003", title: "Задача" }];
  for (const dd of [null, "iter", "more", "gl", "pub"]) {
    const st = S({ openDd: dd, iterList, taskList, gl: "behind" });
    const h = barHTML(barModel(st), st);
    assert.doesNotMatch(h, /data-act="cmode"/, `«cmode» лишився в дропдауні ${dd}`);
    assert.doesNotMatch(h, /data-val="(local|project)"/,
      `у дропдауні ${dd} є контрол зі значенням каналу — перейменований cmode?`);
  }
});

/* Другий бік того самого регресу: модель може нести перелік, а розмітка його
   не малювати — і перемкнути знову буде нічим. */
test("дропдаун ітерації малює перелік із data-act=iter", () => {
  const st = S({
    openDd: "iter", iterId: "it2",
    iterList: [
      { id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false },
      { id: "it2", label: "Іт.2", note: "друга", pub: false, onGl: false },
    ],
  });
  const h = barHTML(barModel(st), st);
  assert.match(h, /data-act="iter" data-val="it1"/, "перелік ітерацій не намальований");
  assert.match(h, /data-act="iter" data-val="it2"/);
  const at = h.indexOf('data-val="it2"');
  assert.match(h.slice(at - 60, at + 10), /dd-item--on/, "поточна ітерація не позначена");
});

/* Чужа ітерація мусить бути ВИДНО чужою, а не лише в title: дизайнер
   дізнається про межу до того, як почав у ній працювати, а не після.

   ⛔ Асерти РОЗРІЗАНІ на крошку й дропдаун, і це не педантизм. Перша редакція
   цього тесту шукала імʼя, мітку й походження по ВСЬОМУ HTML — а кожен із цих
   рядків малюється ДВІЧІ (у крошці й у пункті переліку). Ревʼю довело
   мутаціями, що мітку чужої в дропдауні й підпис автора в ньому можна було
   видалити ПОВНІСТЮ, і тест лишався зеленим. Охоронець, який не може впасти,
   гірший за відсутній. */
const iterParts = (h) => {
  const at = h.indexOf('<div class="dd">');
  assert.ok(at > 0, "дропдауна ітерацій немає — різати нічого");
  return { crumb: h.slice(0, at), dd: h.slice(at) };
};

const FOREIGN = {
  openDd: "iter", iterId: "it5", iterLabel: "Іт.5", iterNote: "",
  iterAuthor: "Ольга Сидорук", iterMine: false, iterOrigin: { it: "it3" },
  iterList: [{ id: "it5", label: "Іт.5", note: "", author: "Ольга Сидорук",
               mine: false, origin: { it: "it3" } }],
};

test("КРОШКА чужої ітерації підписана автором і помічена", () => {
  const st = S(FOREIGN);
  const { crumb } = iterParts(barHTML(barModel(st), st));
  assert.match(crumb, /Ольга Сидорук/, "імені автора в крошці немає");
  assert.match(crumb, /crumb--foreign/, "крошка не помічена як чужа");
  /* Пунктирна рамка без пояснення — загадка, а не сигнал. */
  assert.match(crumb, /працювати у своїй/,
    "підказки «що це значить» у крошці немає");
  assert.match(crumb, /в автора це Іт\.3/, "походження в підказці не назване");
});

test("ПУНКТ ПЕРЕЛІКУ чужої ітерації теж підписаний і помічений", () => {
  const st = S(FOREIGN);
  const { dd } = iterParts(barHTML(barModel(st), st));
  assert.match(dd, /Ольга Сидорук/, "у переліку автора не видно");
  assert.match(dd, /dd-item--foreign/, "пункт переліку не помічений як чужий");
  assert.match(dd, /Іт\.3/, "походження («в автора це Іт.3») у переліку немає");
});

test("своя ітерація мітки чужої не має ніде", () => {
  const st = S({
    openDd: "iter", iterId: "it6", iterAuthor: "Lead", iterMine: true,
    iterList: [{ id: "it6", label: "Іт.6", note: "", author: "Lead", mine: true }],
  });
  const h = barHTML(barModel(st), st);
  const { crumb, dd } = iterParts(h);
  assert.ok(!/crumb--foreign/.test(crumb), "своя крошка помічена як чужа");
  assert.ok(!/dd-item--foreign/.test(dd), "свій пункт переліку помічений як чужий");
  assert.match(crumb, /Lead/, "власний підпис зник — перевірка вище вакуумна");
});

/* Гейт превʼю — НЕ захист, і смуга мусить це казати саме там, де людина
   копіює посилання.

   Перевірено по коду 14.09.2026: `gate_html(tid, pw)` вшиває пароль
   JS-літералом і порівнює `value===P`, ключ sessionStorage — `<tid>_auth`
   (тобто id задачі теж лежить у джерелі сторінки), а `publish/manifest.json`
   і сторінки макета віддаються статикою без жодної перевірки. Прямий GET на
   маніфест повертає назву задачі, тікет і нотатки ітерацій.

   Ризик не в тому, що глядач побачить слово «захищено», а в тому, що ДИЗАЙНЕР
   у це повірить і відправить посилання туди, куди не можна. Тому правда
   стоїть у дропдауні публікації — поруч із «Скопіювати посилання». */
test("дропдаун публікації не обіцяє захисту, а каже, чим гейт є насправді", () => {
  const st = S({ openDd: "pub" });
  const h = barHTML(barModel(st), st);
  assert.match(h, /class="dd-note"/, "у дропдауні публікації немає застереження про гейт");
  assert.match(h, /публічне/, "застереження не каже головного — посилання публічне");
});

/* «В Figma» (T-41): кнопка з іконкою й підписом ярусу GitLab; вимкнена — несе
   причину в title (кнопка не дропдаун, рядка dd-why тут немає) і атрибут
   disabled, бо делегація в app.js пропускає лише `el.disabled`. */
test("«В Figma»: кнопка data-act=figma, вимкнена — з disabled і причиною", () => {
  const on = html();
  assert.match(on, /<button[^>]*data-act="figma"[^>]*>/);
  assert.match(on, /#i-figma/);
  assert.doesNotMatch(on.match(/<button[^>]*data-act="figma"[^>]*>/)[0], /disabled/);
  const off = html({ mode: "overview" }).match(/<button[^>]*data-act="figma"[^>]*>/)[0];
  assert.match(off, / disabled/);
  assert.match(off, /title="[^"]*Огляд/);
  const busy = html({ figmaBusy: true }).match(/<button[^>]*data-act="figma"[^>]*>/)[0];
  assert.match(busy, /aria-busy="true"/);
});

test("«В Figma» в «Огляді» без підпису, але з aria-label", () => {
  const btn = (o) => html(o).match(/<button[^>]*data-act="figma"[\s\S]*?<\/button>/)[0];
  assert.match(btn({}), /<span class="lbl-gl">В Figma<\/span>/);
  const ov = btn({ mode: "overview" });
  assert.doesNotMatch(ov, /<span/);
  assert.match(ov, /aria-label="В Figma"/);
});

/* Статус Клода з 12.10.2026 живе в острівці внизу робочої області (`claude-status.js`,
   `#claude-hud`), а не в смузі: на вузькому вікні фішка з'їдала крихти задачі й
   ітерації. Смуга не має знати про статус узагалі — навіть живий не малює фішки. */
test("у смузі статусу Клода немає ніколи — він в острівці", () => {
  const live = { state: "working", age_s: 20, note: "Іт.2", phase: "design" };
  assert.equal(barModel(S({ claude: live })).zone1.some((x) => x.id === "claude"), false);
  for (const o of [{ claude: live }, { claude: { state: "waiting", age_s: 400 } }, { homeOpen: true, claude: live }]) {
    const h = html(o);
    assert.ok(!/claude-chip|claude-island|Claude працює|Claude чекає/.test(h), JSON.stringify(o));
  }
});

/* Пароль превʼю в дропдауні публікації (ідея 02.09.2026). Пункт ЖИВИЙ завжди —
   задати пароль до першої публікації нормально; «новий пароль ще не в превʼю» —
   попередження, а не вимкнення. І посилання з `#k=<новий>` при старому превʼю
   вимикається: менеджер отримав би ключ, що не відкриває превʼю. */
test("пароль превʼю: свій/типовий, попередження про старий, посилання вимкнене", () => {
  const pw = (o) => {
    const st = S({ openDd: "pub", pw: "7788", ...o });
    return barHTML(barModel(st), st);
  };
  const item = (h) => h.match(/<button[^>]*data-act="pubpw"[^]*?<\/button>/)[0];
  const link = (h) => h.match(/<button[^>]*data-act="copylink"[^>]*>/)[0];
  const def = pw({ pwCustom: false });
  assert.match(item(def), /Пароль превью: 7788/);
  assert.match(item(def), /спільний типовий/);
  assert.match(item(def), /#i-lock/);
  assert.doesNotMatch(item(def), /disabled/);
  assert.match(item(pw({ pwCustom: true })), /лише на цій машині/);
  const stale = pw({ pwCustom: true, pwStale: true });
  assert.match(item(stale), /dd-item--warn/);
  assert.match(item(stale), /ще не в превью/);
  assert.doesNotMatch(item(stale), /disabled/, "пункт пароля не вимикається ніколи");
  assert.match(link(stale), / disabled/);
  assert.match(stale, /пароль змінено, а превʼю|пароль змінено, а превью/);
  assert.doesNotMatch(link(def), / disabled/);
  // Неопубліковане: причина «не опубліковано» важливіша за пароль.
  const m = barModel(S({ published: false, pwStale: true }));
  assert.equal(m.zone3.find((x) => x.id === "publish").items
    .find((x) => x.id === "copylink").whyKey, "whyNoPublish");
});

/* Тиша Teams (батч 1.52): «не знаю» не сміє виглядати як «увімкнено». */
test("Teams: вантажиться/недосяжно — вимкнений пункт із причиною; стан — чекбокс і хто", () => {
  const row = (teams) => {
    const st = S({ openDd: "pub", teams });
    return barHTML(barModel(st), st).match(/<button[^>]*data-act="teamsnotify"[^]*?<\/button>/)[0];
  };
  assert.match(row(null), / disabled/);
  assert.match(row(null), /перевіряю/);
  assert.doesNotMatch(row(null), /chk--on/);
  assert.match(row({ error: "x" }), /стан невідомий/);
  assert.doesNotMatch(row({ error: "x" }), /chk--on/);
  const on = row({ channel: "dc/blog", muted: false });
  assert.match(on, /chk--on/);
  assert.match(on, /dc\/blog/);
  assert.doesNotMatch(on, / disabled/);
  const off = row({ channel: "dc/blog", muted: true, muted_by: "k:0123456789ab", mine: false });
  assert.doesNotMatch(off, /chk--on/);
  assert.match(off, /колегою/);
  assert.doesNotMatch(off, /k:0123/, "хеш — не для людей");
  assert.match(row({ channel: "dc/blog", muted: true, muted_by: "k:x", mine: true }), /тобою/);
});

/* Сторінки без гейта (TD-37) — не «пароль змінено»: інший підпис, посилання живе. */
test("пароль превʼю: сторінки без гейта — свій підпис, посилання не вимикається", () => {
  const st = S({ openDd: "pub", pw: "1100", pwUngated: 3 });
  const h = barHTML(barModel(st), st);
  const item = h.match(/<button[^>]*data-act="pubpw"[^]*?<\/button>/)[0];
  assert.match(item, /3 стор\. превью зовсім без пароля/);
  assert.doesNotMatch(item, /ще не в превью/);
  assert.doesNotMatch(h.match(/<button[^>]*data-act="copylink"[^>]*>/)[0], / disabled/);
});

/* Помилка читання списку задач на екрані «Задачі» не ховається: саме тут
   список є змістом екрана, і мовчання було б найгіршим місцем. */
test("екран «Задачі»: помилка tasks.json лишається видимою", () => {
  const o = { homeOpen: true, tasksErr: true };
  assert.ok(barModel(S(o)).error, "модель втратила помилку в стані «Задачі»");
  assert.match(html(o), /class="errbar"/, "смуги помилки немає в розмітці");
  assert.ok(!/class="errbar"/.test(html({ homeOpen: true })), "смуга помилки без помилки");
});

/* ── простори (Deai 1.0, етап 1) ──────────────────────────────────────────────
   Фішка простору — `data-dd="space"` (делегація смуги відкриває дропдауни за
   `data-dd`), а не `data-act`: клік має відкрити перелік, не виконати дію. Без
   `space` у моделі фішки нема ВЗАГАЛІ. Окремо — пастка, яку знайшов огляд
   плану: `zoneGl`/`zonePublish` читали `c.labelTier`/`c.published` з `undefined`
   і кидали, коли модель (простір без інтеграцій) цих контролів не віддає. */
const SPACES = [
  { id: "liga", name: "ЛІГА", color: "space-1", path: "/w/liga", tasks: 12, available: true },
  { id: "p", name: "P", color: "space-2", path: "/w/p", tasks: 1, available: true },
  { id: "gone", name: "G", color: "space-3", path: "/w/gone", tasks: 0, available: false },
];
const NO_ROLES = { publish: null, tokens: null, comments: null, vcs: null, notify: null, dashboard: null, tracker: null };
const SP = (o = {}) => ({ id: "p", name: "P", color: "space-2", capabilities: NO_ROLES, ...o });
const chip = (h) => /<button[^>]*data-dd="space"[\s\S]*?<\/button>/.exec(h)?.[0];

test("простір без ролей: розмітка не кидає, без GitLab і публікації, Figma лишається", () => {
  let h;
  assert.doesNotThrow(() => { h = html({ space: { capabilities: NO_ROLES } }); });
  assert.doesNotMatch(h, /data-dd="gl"/);
  assert.doesNotMatch(h, /data-act="publish"/);
  assert.doesNotMatch(h, /data-dd="pub"/);
  assert.match(h, /data-act="figma"/, "«В Figma» не залежить від зовнішніх служб");
  assert.equal((h.match(/class="zone /g) || []).length, 3, "три зони лишились");
});

test("простір без інтеграцій: відкриті дропдауни GitLab/публікації не кидають (стан від колишнього екрана)", () => {
  for (const openDd of ["gl", "pub"]) {
    const st = S({ space: SP(), openDd });
    assert.doesNotThrow(() => barHTML(barModel(st), st), openDd);
  }
});

test("фішка простору: data-dd=space, кольорова крапка зі змінної, назва, шеврон", () => {
  const h = html({ homeOpen: true, space: SP() });
  const c = chip(h);
  assert.ok(c, "фішки data-dd=space немає");
  assert.match(c, /class="space-dot"[^>]*style="background:var\(--space-2\)"/);
  assert.match(c, />P</, "назви простору немає у фішці");
  assert.match(c, /<svg/, "шеврона/стрілки дропдауна немає");
  assert.match(c, /aria-haspopup="true"/);
  assert.match(c, /aria-expanded="false"/);
  assert.ok(!/data-act=/.test(c), "фішка відкриває дропдаун, а не виконує дію");
});

test("фішка простору: повна назва — у `title` (довга обрізається трикрапкою), екранована", () => {
  const long = "Дуже довга назва простору клієнта «Альфа» & Co";
  const c = chip(html({ homeOpen: true, space: SP({ name: long }) }));
  assert.match(c, /data-dd="space" title="Дуже довга назва простору клієнта «Альфа» &amp; Co"/);
  const evil = chip(html({ homeOpen: true, space: SP({ name: '"><img src=x onerror=alert(1)>' }) }));
  assert.doesNotMatch(evil, /<img/, "назва з даних не стала тегом");
  assert.match(evil, /title="&quot;&gt;&lt;img/);
});

test("фішка на екрані «Задачі» стоїть ПЕРЕД крошкою сторінки", () => {
  const h = html({ homeOpen: true, space: SP() });
  const sp = h.indexOf('data-dd="space"');
  const crumbs = h.indexOf('class="crumbs"');
  assert.ok(sp !== -1 && crumbs !== -1);
  assert.ok(sp < crumbs, "порядок: простір → крошка");
});

test("без `space` фішки нема ніде; а в смузі задачі її нема й з `space` (простір каже вкладка)", () => {
  assert.doesNotMatch(html({ space: SP() }), /data-dd="space"|space-dot/);
  assert.doesNotMatch(html(), /data-dd="space"/);
  assert.doesNotMatch(html({ homeOpen: true }), /data-dd="space"/);
  assert.doesNotMatch(html({ homeOpen: true, space: null }), /space-dot/);
});

test("на екрані «Задачі» фішка є — це той самий перемикач, а не крошка", () => {
  const h = html({ space: SP(), homeOpen: true });
  assert.ok(chip(h), "на екрані «Задачі» фішки нема");
  assert.ok(h.indexOf('data-dd="space"') < h.indexOf("crumb--flat"), "фішка перед крошкою «Задачі»");
});

test("назва простору екранується: <b> не стає тегом, лапка не виходить з атрибута", () => {
  const evil = '<b>x</b>" onclick="alert(1)';
  const h = html({ homeOpen: true, space: SP({ name: evil }) });
  assert.doesNotMatch(h, /<b>x<\/b>/, "назва стала розміткою");
  assert.match(chip(h), /&lt;b&gt;x&lt;\/b&gt;/);
  assert.doesNotMatch(h, /onclick="alert/, "лапка вийшла з атрибута");
});

test("колір: лише space-1…6; усе інше — space-1, а не довільний CSS у style", () => {
  const dot = (color) => /class="space-dot"[^>]*style="([^"]*)"/.exec(chip(html({ homeOpen: true, space: SP({ color }) })))[1];
  assert.equal(dot("space-4"), "background:var(--space-4)");
  for (const bad of ["red", "space-2);position:fixed;(", "space-9", undefined]) {
    assert.equal(dot(bad), "background:var(--space-1)", String(bad));
  }
});

test("дропдаун просторів: закритий — нема; відкритий — перелік із ✓, підписом і діями", () => {
  assert.doesNotMatch(html({ homeOpen: true, space: SP(), spaces: SPACES }), /Простори/);
  const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(chip(h), /aria-expanded="true"/);
  assert.match(h, /class="dd-head">Простори</);
  const rows = [...h.matchAll(/<button[^>]*data-act="space"[^>]*>[\s\S]*?<\/button>/g)].map((m) => m[0]);
  assert.equal(rows.length, 3, "рядок на кожен простір");
  assert.match(rows[0], /data-val="liga"/);
  assert.match(rows[0], /12 задач · \/w\/liga/);
  assert.match(rows[0], /style="background:var\(--space-1\)"/);
  assert.doesNotMatch(rows[0], /dd-item--on/, "✓ не на поточному");
  assert.doesNotMatch(rows[0], /dd-marks/, "галочка не на поточному");
  assert.match(rows[1], /data-val="p"/);
  assert.match(rows[1], /dd-item--on/, "поточний простір без позначки");
  assert.match(rows[1], /1 задача · \/w\/p/);
  assert.match(rows[1], /dd-marks">\s*<svg/, "галочки у поточного нема");
  assert.match(h, /data-act="spacenew"[\s\S]*?Новий простір…/);
  assert.match(h, /data-act="spaceedit"[\s\S]*?Назва й колір…/);
});

/* Вхід на екран «Підключення» (етап 3a): пункт у футері дропдауна, ПІСЛЯ «Назва й колір…». Той самий `ddItem`, що
   решта футера, — тому roving focus по `.dd--spaces .dd-item` бере його сам. Пункт лише в ВІДКРИТОМУ дропдауні:
   закрита смуга (а з нею й ЛІГА-golden) лишається побайтно та сама. */
test("дропдаун просторів: «Налаштування…» після «Назва й колір…»", () => {
  const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(h, /data-act="spaceedit"[\s\S]*?<\/button>\s*<button[^>]*data-act="conn"[\s\S]*?Налаштування…/);
  const conn = /<button[^>]*data-act="conn"[\s\S]*?<\/button>/.exec(h)?.[0];
  assert.match(conn, /<svg/, "пункт без іконки");
  assert.equal((h.match(/data-act="conn"/g) || []).length, 1, "пункт один");
  assert.doesNotMatch(html({ homeOpen: true, space: SP(), spaces: SPACES }), /data-act="conn"/, "закритий дропдаун пункту не несе");
  assert.match(html({ homeOpen: true, space: SP(), openDd: "space" }), /data-act="conn"/, "без переліку просторів пункт теж є");
});

/* Клавіатурний roving по дропдауну просторів іде за `.dd--spaces .dd-item` (`app.js`, `rovingIndex`): пункт без цього
   класу випав би зі стрілок. Тож «Підключення…» мусить бути саме `ddItem`, а не окремою кнопкою. */
test("дропдаун просторів: «Налаштування…» — `dd-item` у `.dd--spaces`, тож клавіатурний roving його бере", () => {
  const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  const conn = /<button[^>]*data-act="conn"[^>]*>/.exec(h)?.[0];
  assert.ok(conn, "пункту нема");
  assert.match(conn, /class="[^"]*\bdd-item\b[^"]*"/, "пункт без `dd-item` випадає з клавіатурного roving");
  const dd = /<div class="dd dd--spaces">[\s\S]*$/.exec(h)?.[0];
  assert.ok(dd && dd.includes('data-act="conn"'), "пункт не всередині `.dd--spaces`");
  /* Той самий рід, що решта футера: «Новий простір…» й «Назва й колір…» теж `dd-item`, і roving (`.dd--spaces .dd-item`)
     бачить усі три рядки футера підряд. */
  const rows = [...dd.matchAll(/<button[^>]*class="([^"]*)"[^>]*data-act="(spacenew|spaceedit|conn)"/g)];
  assert.deepEqual(rows.map((m) => m[2]), ["spacenew", "spaceedit", "conn"], "порядок футера");
  for (const m of rows) assert.match(m[1], /\bdd-item\b/, m[2]);
});

/* На самій сторінці «Підключення» пункт нічого б не робив — той самий принцип, що в ⌘K (`space-conn` там теж
   прихований). На «Задачах» і на смузі задачі він є: ведуть ВІД них. Лише рівно `homePage === "conn"`. */
test("дропдаун просторів: «Налаштування…» нема на самій сторінці «Налаштування», є скрізь, де ведуть на неї", () => {
  const on = (o) => /data-act="conn"/.test(html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space", ...o }));
  assert.equal(on({ homeOpen: true, homePage: "conn" }), false, "на сторінці — пункт, що нічого не робить");
  assert.equal(on({ homeOpen: true, homePage: "tasks" }), true, "на «Задачах» пункт є");
  assert.equal(on({ homeOpen: true }), true, "оверлей без homePage — як «Задачі»");
  assert.equal(on({}), true, "на смузі задачі пункт є");
  assert.equal(on({ homePage: null }), true, "поза оверлеєм (`barState` дає null) пункт є");
  /* Решта футера на сторінці лишається: ховається лише те, що тут безглузде. */
  const h = html({ space: SP(), spaces: SPACES, openDd: "space", homeOpen: true, homePage: "conn" });
  assert.match(h, /data-act="spacenew"/);
  assert.match(h, /data-act="spaceedit"/);
  assert.match(h, /data-act="space"/);
});

test("дропдаун просторів: «Settings…» англійською", () => {
  setLang("en");
  try {
    assert.match(html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" }), /data-act="conn"[\s\S]*?Settings…/);
  } finally { setLang("uk"); }
});

/* Смуга на сторінці «Налаштування»: склад як на «Задачах», крошка інша. Плоска крошка — не кнопка; «Назад» і логотипа
   тут нема (вихід — логотип у рядку вкладок). */
test("смуга на сторінці «Налаштування»: фішка простору й плоска крошка", () => {
  const h = html({ space: SP(), homeOpen: true, homePage: "conn", taskId: "t1" });
  assert.match(h, /crumb crumb--flat[\s\S]*?Налаштування</);
  assert.doesNotMatch(h, /<span class="txt">Задачі</);
  assert.doesNotMatch(h, /data-act="back"|data-act="home"/);
  /* Екран, а не смуга задачі: зони 2 і 3 порожні, як на «Задачах». */
  assert.equal((h.match(/class="zone /g) || []).length, 3);
  assert.doesNotMatch(h, /data-act="figma"|data-act="publish"|data-dd="iter"/);
  assert.ok(h.indexOf('data-dd="space"') < h.indexOf("crumb--flat"), "фішка перед крошкою");
  /* Іконка крошки — `sliders` (та сама, що в дропдауні й палітрі), а не `grid` «Задач». */
  const flat = (x) => /<span class="crumb crumb--flat crumb--page">[\s\S]*?<\/span><\/span>/.exec(x)[0];
  const tasks = flat(html({ space: SP(), homeOpen: true, taskId: "t1" }));
  assert.match(flat(h), /#i-sliders/);
  assert.doesNotMatch(flat(h), /#i-grid/);
  assert.match(tasks, /#i-grid[\s\S]*Задачі</, "крошка «Задач» змінилась");
});

/* Смуга на сторінці майстра (етап 3b): плоска крошка «Новий простір» з іконкою `plus`; жодної фішки простору й кнопки
   «назад до задачі» (модель їх не дає — розмітка не малює). Дві перевірки: на готовій моделі (контракт `crumb-wiz`) і наскрізно
   через `barModel` (склад, який справді збирає застосунок). */
test("крошка майстра: іконка plus і «Новий простір», жодної фішки простору й кнопки «назад»", () => {
  const model = { zone1: [{ id: "crumb-wiz", tier: 0, labelKey: "wzCrumb" }], zone2: [], zone3: [] };
  const h = barHTML(model, {});
  assert.match(h, /<span class="crumb crumb--flat crumb--page">[\s\S]*?#i-plus[\s\S]*?<span class="txt">Новий простір<\/span>/);
  assert.doesNotMatch(h, /data-act="back"/);
  assert.doesNotMatch(h, /space-chip/);
  /* Це «головний» склад оверлею: зони 2 і 3 порожні, жодного контрола задачі. */
  assert.equal((h.match(/class="zone /g) || []).length, 3);
  assert.doesNotMatch(h, /data-act="figma"|data-act="publish"|data-dd="iter"|data-dd="task"/);
});

test("смуга на сторінці майстра: з простором і задачею в стані — без фішки й «назад», лише крошка «Новий простір»", () => {
  const h = html({ space: SP(), spaces: SPACES, homeOpen: true, homePage: "wiz", taskId: "t1" });
  assert.match(h, /<span class="crumb crumb--flat crumb--page">[\s\S]*?#i-plus[\s\S]*?<span class="txt">Новий простір<\/span>/);
  assert.doesNotMatch(h, /data-dd="space"/, "фішка простору на майстрі");
  assert.doesNotMatch(h, /data-act="back"|data-act="home"|data-act="palette"/, "контролів рядка вкладок у смузі нема");
  assert.doesNotMatch(h, /<span class="txt">Задачі<\/span>|<span class="txt">Підключення<\/span>/, "чужа крошка");
  /* Англійською крошка — своє слово. */
  setLang("en");
  try {
    assert.match(html({ space: SP(), homeOpen: true, homePage: "wiz" }), /<span class="txt">New space<\/span>/);
  } finally { setLang("uk"); }
  /* Свідок: на «Задачах» із тим самим станом фішка є. */
  assert.match(html({ space: SP(), spaces: SPACES, homeOpen: true, taskId: "t1" }), /data-dd="space"/);
});

/* Крошка сторінки оверлею («Задачі», «Підключення», «Новий простір») має модифікатор `crumb--page`: за ним CSS знімає ліміт
   110px, що перебивав `.crumb{max-width:260px}` і стискав іконку до 0px. Модифікатор — ЛИШЕ на цих крошках: смуга задачі
   (канвас) й зовнішня оболонка превʼю (`ext-bar.js`) лишаються з розміткою, яка була. */
test("крошка сторінки оверлею має `crumb--page` — на «Задачах», «Підключенні» й майстрі; смуга задачі його не має", () => {
  for (const homePage of [undefined, "tasks", "conn", "wiz"]) {
    const h = html({ space: SP(), homeOpen: true, homePage, taskId: "t1" });
    assert.equal((h.match(/class="crumb crumb--flat crumb--page"/g) ?? []).length, 1, `homePage=${String(homePage)}`);
  }
  const task = html({ space: SP(), taskId: "t1" });
  assert.doesNotMatch(task, /crumb--page/, "смуга задачі не повинна мати модифікатор сторінки");
  assert.doesNotMatch(html({ taskId: "t1" }), /crumb--page/);
});

test("дропдаун просторів: недоступний простір приглушений, не вимкнений, і каже чому", () => {
  const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  const gone = /<button[^>]*data-val="gone"[\s\S]*?<\/button>/.exec(h)[0];
  assert.match(gone, /dd-item--muted/);
  assert.doesNotMatch(gone, / disabled/, "вимкнений пункт не клікнути — а перейти й побачити причину треба");
  assert.match(gone, /файл задач недоступний/);
  assert.doesNotMatch(gone, /0 задач/, "«0 задач» про недоступний простір — брехня");
});

test("дропдаун просторів: назви й шляхи з реєстру екрануються", () => {
  const spaces = [{ id: "e", name: "<img src=x onerror=1>", color: "space-1", path: '"><script>', tasks: 1 }];
  const h = html({ homeOpen: true, space: SP({ id: "e" }), spaces, openDd: "space" });
  assert.doesNotMatch(h, /<img src=x/);
  assert.doesNotMatch(h, /<script>/);
});

test("дропдаун просторів без переліку не падає: лише дії «Новий…» і «Назва й колір…»", () => {
  const h = html({ homeOpen: true, space: SP(), openDd: "space" });
  assert.match(h, /data-act="spacenew"/);
  assert.match(h, /data-act="spaceedit"/);
  assert.doesNotMatch(h, /data-act="space"/);
});

test("дропдаун просторів у англійському інтерфейсі — англійською", () => {
  setLang("en");
  try {
    const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
    assert.match(h, /class="dd-head">Spaces</);
    assert.match(h, /12 tasks · \/w\/liga/);
    assert.match(h, /1 task · \/w\/p/);
    assert.match(h, /New space…/);
  } finally { setLang("uk"); }
});

/* Друга точка, де реєстр просторів стає `style=`: колір РЯДКА дропдауна (перша —
   крапка фішки). Реєстр правлять руками, `esc` лишає цілими лапки, але не `;` —
   тож без токена в рядок літав би довільний CSS. `data-val` — id простору, теж
   із реєстру: його екранування не повинно залежати від того, що в `title`. */
test("дропдаун просторів: колір рядка йде крізь токен, id в data-val екранований", () => {
  const evil = [{
    id: '"><script>', name: "<b>x</b>", color: "space-2);position:fixed;(", path: "/p", tasks: 1,
  }];
  const h = html({ homeOpen: true, space: SP({ id: "p" }), spaces: evil, openDd: "space" });
  const row = /<button[^>]*data-act="space"[^>]*>[\s\S]*?<\/button>/.exec(h)?.[0];
  assert.ok(row, "рядок простору не знайдено");
  assert.deepEqual([...row.matchAll(/style="([^"]*)"/g)].map((m) => m[1]), ["background:var(--space-1)"],
    "колір рядка — рівно токен space-1, ніякого стороннього CSS");
  assert.doesNotMatch(h, /position:fixed/);
  assert.match(row, /data-val="&quot;&gt;&lt;script&gt;"/);
  assert.doesNotMatch(h, /<script>|<b>x<\/b>/);
});

/* `aria-current` на поточному рядку: клас `dd-item--on` оком видно, читач його не
   чує. Рішення ревʼю Task 6 (план, Додаток Б): рядки лишаються `ddItem`, а Task 7
   дає roving focus по `.dd--spaces .dd-item`. */
test("дропдаун просторів: aria-current лише на поточному рядку; решта дропдаунів без нього", () => {
  const h = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  const rows = [...h.matchAll(/<button[^>]*data-act="space"[^>]*>/g)].map((m) => m[0]);
  assert.equal(rows.length, 3);
  assert.doesNotMatch(rows[0], /aria-current/);
  assert.match(rows[1], /data-val="p"[^>]*aria-current="true"/);
  assert.doesNotMatch(rows[2], /aria-current/);
  assert.equal((h.match(/aria-current/g) || []).length, 1, "поточний — один на весь дропдаун");
  // `current` — необовʼязковий параметр `ddItem`: решта дропдаунів його не знає
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  for (const openDd of ["iter", "gl", "pub", "more"]) {
    assert.doesNotMatch(html({ homeOpen: true, openDd, iterList, gl: "behind" }), /aria-current/, openDd);
  }
});

test("дропдаун просторів: роздільник перед «Новий простір…» є з переліком і нема без нього", () => {
  const withList = html({ homeOpen: true, space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(withList,
    /data-val="gone"[\s\S]*?<\/button>\s*<div class="dd-sep"><\/div>\s*<button[^>]*data-act="spacenew"/);
  assert.doesNotMatch(html({ homeOpen: true, space: SP(), openDd: "space" }), /dd-sep/, "порожній перелік — роздільника нема");
});

/* Снапшот-страж: простір З інтеграціями змінює смугу рівно на фішку — ні байтом
   більше. Це те, що береже ЛІГА (legacy-простір) від випадкових змін розмітки. */
test("розмітка зі space = розмітка без space мінус блок фішки — побайтно (екрани оверлею); смуга задачі від space не залежить", () => {
  const stripChip = (h) => h.replace(/<div class="ddhost space-h">[\s\S]*?<\/div>/, "");
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  const sp = { id: "p", name: "P", color: "space-2" };
  for (const o of [{ homeOpen: true }, { homeOpen: true, homePage: "conn" }, { homeOpen: true, tasksErr: true }]) {
    const withSpace = html({ ...o, space: sp });
    assert.ok(chip(withSpace), `фішки нема: ${JSON.stringify(o)}`);
    assert.equal(stripChip(withSpace), html(o), `розмітка розійшлась: ${JSON.stringify(o)}`);
  }
  for (const o of [{}, { openDd: "pub" }, { openDd: "gl", gl: "behind" },
    { openDd: "iter", iterList }, { openDd: "more" }, { hasIteration: false }, { tasksErr: true }]) {
    assert.equal(html({ ...o, space: sp }), html(o), `смуга задачі змінилась від space: ${JSON.stringify(o)}`);
  }
});

/* Розмітка фішки й дропдауна збалансована: рядок із шаблону легко лишає
   незакриту `<button>`, а тести, що шукають `<button…</button>` регекспом, цього
   не помічають — вони «дочитують» до чужого закривального тега. */
test("розмітка зі space збалансована: кожен <button> і <div> закрито", () => {
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  for (const o of [{}, { openDd: "space" }, { openDd: "space", spaces: SPACES }, { homeOpen: true },
    { homeOpen: true, openDd: "space", spaces: SPACES }, { openDd: "iter", iterList }]) {
    const h = html({ space: SP(), ...o });
    for (const tag of ["button", "div"]) {
      assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length,
        (h.match(new RegExp(`</${tag}>`, "g")) || []).length, `<${tag}> не збалансовано: ${JSON.stringify(o)}`);
    }
  }
});

/* ── публікація за `capabilities.publish` (модулі 2а, Task 8) ─────────────────
   Розмітка читає те, що віддала модель: простір без інтеграцій з модулем публікації
   має кнопку «Опублікувати» і дропдаун — без GitLab, пароля ЛІГА, Teams і
   застереження про «публічність» ЛІГА-посилання (воно про зовнішній URL). Підпис
   «локально» — на «Відкрити» й «Скопіювати». */
const CAPS_SP = (publish, o = {}) => ({
  id: "p", name: "P", color: "space-2", capabilities: { ...NO_ROLES, publish, tokens: null }, ...o,
});
const LIGA_SP = (o = {}) => ({ id: "p", name: "P", color: "space-2", capabilities: { publish: "vercel-publish", tokens: null },
  compat: { publish: "design-canvas" }, ...o });
const btn = (h, act) => (h.match(new RegExp(`<button[^>]*data-act="${act}"[^]*?</button>`)) || [null])[0];

test("модуль публікації без ролей vcs/notify: кнопка й дропдаун публікації є, GitLab нема", () => {
  const h = html({ space: CAPS_SP("static-publish"), openDd: "pub", teams: null });
  assert.ok(btn(h, "publish"), "кнопки «Опублікувати» нема");
  assert.match(h, /data-dd="pub"/);
  assert.doesNotMatch(h, /data-dd="gl"/);
  for (const act of ["togglepub", "openpreview", "copylink"]) assert.ok(btn(h, act), `${act} не намальовано`);
  for (const act of ["teamsnotify", "pubpw"]) assert.equal(btn(h, act), null, `${act} не мусить бути без ЛІГА`);
  assert.doesNotMatch(h, /class="dd-note"/, "застереження про публічне ЛІГА-посилання тут не про те");
  assert.doesNotMatch(h, /перевіряю/, "вічного «перевіряю стан» нема");
});

test("ЛІГА-простір: застереження про публічність і пароль — на місці", () => {
  const h = html({ space: LIGA_SP(), openDd: "pub", pw: "1100", teams: { channel: "c", muted: false } });
  assert.match(h, /class="dd-note"/);
  assert.ok(btn(h, "pubpw"));
  assert.ok(btn(h, "teamsnotify"));
  assert.match(h, /data-dd="gl"/);
});

test("простір без постачальника публікації: ні кнопки, ні дропдауна публікації (і розмітка не кидає)", () => {
  let h;
  assert.doesNotThrow(() => { h = html({ space: CAPS_SP(null), openDd: "pub" }); });
  assert.equal(btn(h, "publish"), null);
  assert.doesNotMatch(h, /data-dd="pub"/);
  assert.ok(btn(h, "figma"), "«В Figma» лишається");
});

test("локальна публікація: підпис «локально» (з часом) на «Відкрити», адреса канваса на «Скопіювати»", () => {
  const h = html({ space: CAPS_SP("static-publish"), openDd: "pub", pubLocal: true, pubWhen: "5 хв тому" });
  assert.match(btn(h, "openpreview"), /локально · 5 хв тому/);
  assert.match(btn(h, "copylink"), /локально/);
  assert.doesNotMatch(btn(h, "openpreview"), /disabled/);
  const plain = html({ space: CAPS_SP("static-publish"), openDd: "pub" });
  assert.doesNotMatch(btn(plain, "openpreview"), /локально/);
});

test("локальна публікація англійською: «local» без сирого ISO", () => {
  setLang("en");
  try {
    const h = html({ space: CAPS_SP("static-publish"), openDd: "pub", pubLocal: true, pubWhen: "5 min ago" });
    assert.match(btn(h, "openpreview"), /local · 5 min ago/);
    assert.doesNotMatch(h, /\d{4}-\d\d-\d\dT/);
  } finally { setLang("uk"); }
});

test("розмітка публікації модулем збалансована: кожен <button> і <div> закрито", () => {
  const h = html({ space: CAPS_SP("static-publish"), openDd: "pub", pubLocal: true, pubWhen: "щойно" });
  for (const tag of ["button", "div"]) {
    assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length,
      (h.match(new RegExp(`</${tag}>`, "g")) || []).length, `<${tag}> не збалансовано`);
  }
});

/* ── публікація на свій Vercel (2b-1, Task 3): застереження в дропдауні ───────────────────────
   Модель дає `notes` (`bar-model.js`), розмітка малює кожне як `.dd-note` — того самого стилю, що застереження ЛІГА,
   але з власним модифікатором, щоб тести ЛІГА-застереження (`class="dd-note"` дослівно) лишились про нього. */
const NOTE_RE = (id) => new RegExp(`<div class="dd-note dd-note--${id}">([^<]*)</div>`);

test("Vercel без пароля: дропдаун публікації має застереження «превʼю публічне» (текст зі словника)", () => {
  setLang("uk");
  const h = html({ space: CAPS_SP("vercel-publish"), openDd: "pub", pubGate: false });
  const m = NOTE_RE("public").exec(h);
  assert.ok(m, "застереження немає в розмітці");
  assert.equal(m[1], t("publishPublicWarn"));
  assert.doesNotMatch(h, /dd-note--stale/);
  assert.doesNotMatch(h, /class="dd-note"/, "застереження ЛІГА тут нема");
});

test("Vercel: пароль змінено — «перепублікуйте» окремим застереженням", () => {
  setLang("uk");
  const h = html({ space: CAPS_SP("vercel-publish"), openDd: "pub", pubGate: true, pubGateStale: true });
  assert.equal(NOTE_RE("stale").exec(h)?.[1], t("publishGateStale"));
  assert.doesNotMatch(h, /dd-note--public/);
});

test("Vercel: без `publish_gate` у відповіді (чи з паролем) — жодного застереження", () => {
  for (const o of [{}, { pubGate: true }, { pubGate: undefined, pubGateStale: undefined }]) {
    const h = html({ space: CAPS_SP("vercel-publish"), openDd: "pub", ...o });
    assert.doesNotMatch(h, /dd-note/, JSON.stringify(o));
  }
});

test("застереження Vercel — англійською, коли мова en", () => {
  setLang("en");
  try {
    const h = html({ space: CAPS_SP("vercel-publish"), openDd: "pub", pubGate: false, pubGateStale: true });
    assert.equal(NOTE_RE("public").exec(h)?.[1], t("publishPublicWarn"));
    assert.match(NOTE_RE("public").exec(h)[1], /public/);
    assert.match(NOTE_RE("stale").exec(h)[1], /republish/);
  } finally { setLang("uk"); }
});

test("ЛІГА: `pubGate: false` у стані не дає модульних застережень — лишається одне `dd-note` про публічність ЛІГА", () => {
  setLang("uk");
  const h = html({ space: LIGA_SP(), openDd: "pub", pubGate: false, pubGateStale: true });
  assert.equal((h.match(/class="dd-note"/g) || []).length, 1);
  assert.doesNotMatch(h, /dd-note--/);
});

test("static-publish: сервер полів не дає — у дропдауні жодного `dd-note` (розмітка як у 0.2.0)", () => {
  setLang("uk");
  const h = html({ space: CAPS_SP("static-publish"), openDd: "pub" });
  assert.doesNotMatch(h, /dd-note/);
});

test("застереження малюються лише у відкритому дропдауні й не ламають баланс тегів", () => {
  setLang("uk");
  const closed = html({ space: CAPS_SP("vercel-publish"), pubGate: false });
  assert.doesNotMatch(closed, /dd-note/);
  const h = html({ space: CAPS_SP("vercel-publish"), openDd: "pub", pubGate: false, pubGateStale: true });
  for (const tag of ["div", "button", "span"]) {
    assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length, (h.match(new RegExp(`</${tag}>`, "g")) || []).length, tag);
  }
});

/* ── Пігулка оновлення й «Відгук» (0.25.0) ────────────────────────────────
   Обидва переїхали зі смуги: пігулка — в рядок вкладок (`tabs-view.js`, її розмітка — `update-view.js`), «Відгук» — в острівець
   (`island.js`). Присутність `update` у стані смугу не міняє. */
const UPD = { current: "0.1.0", latest: "0.2.0", available: true, state: "ok", checked_at: 1, boot: "a", restart_failed: false };

test("оновлення в стані не міняє розмітку смуги (пігулка й «Відгук» — не тут)", () => {
  for (const o of [{}, { homeOpen: true }, { homeOpen: true, homePage: "conn", taskId: "t1" }, { hasIteration: false }]) {
    assert.equal(html({ update: UPD, ...o }), html(o), JSON.stringify(o));
    assert.doesNotMatch(html({ update: UPD, ...o }), /data-act="update"|upd-pill|data-act="feedback"/, JSON.stringify(o));
  }
});

test("розмітка смуги збалансована за тегами", () => {
  for (const o of [{}, { homeOpen: true }]) {
    const h = html(o);
    for (const tag of ["div", "button", "span"]) {
      assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length, (h.match(new RegExp(`</${tag}>`, "g")) || []).length, tag);
    }
  }
});

/* Етап В (0.28.0): «Видалити ітерацію» питає в самому дропдауні. */
test("дропдаун ітерації: пункт видалення — delitask (питання), а не одразу delit", () => {
  const h = html({ openDd: "iter" });
  assert.match(h, /data-act="delitask"/);
  assert.doesNotMatch(h, /data-act="delit"/);
});

test("дропдаун ітерації: iterDelAsk — лише питання, «Ні» перед «Видалити», без переліку ітерацій", () => {
  const iterList = [{ id: "it2", label: "Іт.2", note: "", pub: false, onGl: false }, { id: "it3", label: "Іт.3", note: "", pub: false, onGl: false }];
  const h = html({ openDd: "iter", iterDelAsk: true, iterList, iterId: "it3" });
  assert.match(h, /data-val="confirmed:it3"/, "«Видалити» привʼязане до id ітерації з питання");
  assert.match(h, /class="dd dd--confirm"/);
  assert.match(h, /class="cfm"/);
  assert.match(h, /class="cfm-yes" data-act="delit" data-val="confirmed:it3"/);
  assert.match(h, /class="cfm-no" data-act="delitno"/);
  assert.ok(h.includes(t("cfmDelIter", "Іт.3")), "питання називає ітерацію");
  assert.doesNotMatch(h, /data-act="iter"/);
  assert.ok(h.indexOf('class="cfm-no"') < h.indexOf('class="cfm-yes"'));
});

test("питання лише при відкритому дропдауні ітерації", () => {
  assert.doesNotMatch(html({ openDd: null, iterDelAsk: true }), /class="cfm"/);
});

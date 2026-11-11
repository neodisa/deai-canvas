import assert from "node:assert/strict";
import test from "node:test";

import { barModel } from "../app/bar-model.js";
import { barHTML, taskListHTML } from "../app/shell-bar.js";
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

/* Двері в палітру. До 02.09.2026 палітра жила ТІЛЬКИ на ⌘K, і власник шукав її
   словами «поиск по функционалам, куда-то он делся, потерялся» — тобто схована
   дія без видимих дверей це не схована дія, а зникла. Тест стереже три речі, і
   кожна має свою причину впасти. */
test("палітра має видимі двері в смузі", () => {
  const h = html();
  assert.match(h, /data-act="palette"/, "кнопки палітри в смузі немає");

  // Іконка — без неї кнопка невидима на вузьких ширинах, де підпис уже схований.
  const btn = /<button[^>]*data-act="palette"[\s\S]*?<\/button>/.exec(h);
  assert.ok(btn, "кнопка палітри не розібралась");
  assert.match(btn[0], /<svg/, "кнопка палітри без іконки");

  // Підпис-акорд у власному класі: контейнерний запит ховає саме його на 1180.
  assert.match(btn[0], /class="lbl-pal"/, "підпис не має класу, за який його ховає CSS");

  // Акорд оком видно, екранним читачем — ні: для нього «⌘K» просто два символи.
  assert.match(btn[0], /aria-keyshortcuts="[^"]*K/, "акорд не оголошений для читача");
});

/* Логотип — вхід на екран «Задачі». Стоїть ПЕРЕД палітрою (свідома зміна
   порядку: «де я / до всіх задач» старше за «що я можу»). Імʼя кнопки несе
   `aria-label`, бо всередині лише декоративний SVG. */
test("логотип — кнопка data-act=home перед палітрою, з іменем і станом", () => {
  const h = html();
  const btn = /<button[^>]*data-act="home"[\s\S]*?<\/button>/.exec(h);
  assert.ok(btn, "кнопки логотипа в смузі немає");
  assert.match(btn[0], /aria-label="[^"]+"/, "кнопка логотипа без імені для читача");
  assert.match(btn[0], /<svg[^>]*viewBox="0 0 283 283"/, "у кнопці немає логотипа");
  assert.ok(!/ctl--on/.test(btn[0]), "без homeOpen логотип не активний");
  assert.ok(h.indexOf('data-act="home"') < h.indexOf('data-act="palette"'),
    "логотип мусить стояти перед палітрою");
  const on = /<button[^>]*data-act="home"[^>]*>/.exec(html({ homeOpen: true }))[0];
  assert.match(on, /ctl--on/, "на екрані «Задачі» логотип мусить бути активним");
  /* Кнопка не вимикається повторним кліком, тож це не перемикач: стан «ми тут»
     оголошуємо як `aria-current="page"`, а не `aria-pressed`. */
  assert.match(on, /aria-current="page"/, "активний логотип не оголошений як поточна сторінка");
  assert.ok(!/aria-pressed/.test(on), "логотип не перемикач — aria-pressed тут брехня");
  assert.ok(!/aria-current/.test(btn[0]), "поза екраном «Задачі» aria-current не ставимо");
});

/* Логотип на сторінці «Підключення»: крошка каже «Підключення», тож логотип не світиться й не оголошує себе поточною
   сторінкою (інакше читач екрана чув би «поточна сторінка» двічі, а око — дві підсвічені «де я»). Кнопка при цьому лишається:
   вона веде на «Задачі». */
test("логотип на «Підключенні»: без ctl--on і aria-current, але кнопка й імʼя на місці; на «Задачах» — як було", () => {
  const conn = /<button[^>]*data-act="home"[\s\S]*?<\/button>/.exec(html({ homeOpen: true, homePage: "conn", taskId: "t1" }));
  assert.ok(conn, "кнопки логотипа на сторінці «Підключення» нема — дорога на «Задачі» зникла");
  assert.doesNotMatch(conn[0], /ctl--on/, "логотип світиться на «Підключенні»");
  assert.doesNotMatch(conn[0], /aria-current/, "логотип оголошує себе поточною сторінкою на «Підключенні»");
  assert.match(conn[0], /aria-label="[^"]+"/, "кнопка логотипа втратила імʼя");
  for (const o of [{ homeOpen: true }, { homeOpen: true, homePage: "tasks" }]) {
    const tasks = /<button[^>]*data-act="home"[^>]*>/.exec(html(o))[0];
    assert.match(tasks, /ctl--on/, JSON.stringify(o));
    assert.match(tasks, /aria-current="page"/, JSON.stringify(o));
  }
});

/* Екран «Задачі»: три зони лишаються в DOM (грид на них тримається), але
   склад інший — лише «де я» і шлях назад. */
test("екран «Задачі»: крошка «Задачі» і «Назад до …», без макета й публікації", () => {
  const h = html({ homeOpen: true });
  assert.equal((h.match(/class="zone /g) || []).length, 3, "зон мусить лишитись три");
  assert.match(h, /crumb--flat[^>]*>[\s\S]*?Задачі/, "немає плоскої крошки «Задачі»");
  const back = /<button[^>]*data-act="back"[\s\S]*?<\/button>/.exec(h);
  assert.ok(back, "немає кнопки «Назад»");
  assert.match(back[0], /LIGA-7003/, "«Назад» не називає задачу");
  assert.match(back[0], /aria-label="[^"]*LIGA-7003/, "«Назад» без імені для читача");
  assert.ok(!/data-dd="task"/.test(h), "крошка-перемикач задач на екрані «Задачі» зайва");
  assert.ok(!/data-dd="iter"/.test(h), "крошка ітерації на екрані «Задачі» зайва");
  assert.ok(!/data-act="publish"/.test(h), "публікація без вигляду задачі безглузда");
  assert.ok(!/data-act="mode"/.test(h), "сегмент «Макет/Огляд» без задачі безглуздий");
  assert.match(h, /data-act="home"/, "логотип мусить лишитись");
  assert.match(h, /data-act="palette"/, "палітра мусить лишитись");
});

/* Порядок несучий: двері стоять ПЕРЕД крошками (голова зони 1). Якби вони
   поїхали в хвіст, вони б розділяли крошки й зону 2 — тобто читались би як
   частина «де я», чим вони не є. */
test("двері палітри стоять перед крошками, а не між ними й зоною 2", () => {
  const h = html();
  const pal = h.indexOf('data-act="palette"');
  const crumbs = h.indexOf('class="crumbs"');
  const zone2 = h.indexOf('class="zone zone-2"');
  assert.ok(pal !== -1 && crumbs !== -1 && zone2 !== -1);
  assert.ok(pal < crumbs, "двері палітри мусять бути перед крошками");
  assert.ok(crumbs < zone2, "крошки мусять лишитись у зоні 1");
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

/* Без ітерацій крошки ітерації немає взагалі — так само, як зникають інспектор
   і «Флоу». «Є, але вимкнена» читалось би як «щось поламалось». */
test("без ітерацій крошки ітерації немає, крошка задачі лишається", () => {
  const h = html({ hasIteration: false });
  assert.match(h, /data-dd="task"/);
  assert.doesNotMatch(h, /data-dd="iter"/);
});

/* Дропдаун малюється лише коли відкритий: тримати в DOM усі закриті меню
   означає платити за них на кожному рендері й ловити їхні `id` пошуком. */
test("дропдаун малюється лише для відкритого меню", () => {
  assert.doesNotMatch(html(), /class="dd"/);
  assert.match(barHTML(barModel(S()), S({ openDd: "iter" })), /class="dd"/);
});

/* Task 3 Плану B: `state.taskList` — те, чого `bar-model.js` свідомо не
   несе (список задач приходить з окремого `/api/tasks`, а не з `/api/task`,
   який бачить модель). Без цього перемикання задач лишилось би в новій
   смузі кнопкою, що нічого не робить: жоден `data-act="task"` не доїхав би
   до розмітки, і делегація в app.js мала б звідки клікати, та нікуди. */
test("дропдаун задачі несе перелік із state.taskList, поточна позначена", () => {
  const st = S({
    openDd: "task",
    taskList: [{ id: "a", jira: "", title: "Перша" }, { id: "b", jira: "LIGA-1", title: "Друга" }],
    curTaskId: "b",
  });
  const h = barHTML(barModel(st), st);
  assert.match(h, /data-act="task" data-val="a"/);
  assert.match(h, /data-act="task" data-val="b"/);
  // позначена саме «b» (curTaskId), а не «a»
  const bItem = h.slice(h.indexOf('data-val="b"') - 40, h.indexOf('data-val="b"') + 10);
  assert.match(bItem, /dd-item--on/);
});

/* ── Пошук і клавіатура в перемикачі задач (батч 1.52, Task 5) ───────────── */
const TASKS = [
  { id: "alpha", jira: "LIGA-11", title: "LIGA-11 · Перша задача" },
  { id: "beta", jira: "LIGA-22", title: "Друга <b>задача</b>" },
  { id: "gone", jira: "LIGA-33", title: "Без теки", missing: true },
  { id: "boss-interface", jira: "", title: "Boss" },
];
const dd = (o = {}) => {
  const st = S({ openDd: "task", taskList: TASKS, curTaskId: "alpha", taskQuery: "", taskCursor: 0, ...o });
  const h = barHTML(barModel(st), st);
  const at = h.indexOf('class="dd dd--tasks"');
  if (at < 0) return "";
  const hint = h.indexOf("dd-hint", at);          // кінець дропдауна — підказка футера
  return h.slice(at, hint < 0 ? undefined : h.indexOf("</span>", hint) + 7);
};
const itemOf = (h, id) => new RegExp(`<button[^>]*data-act="task" data-val="${id}"[\\s\\S]*?</button>`).exec(h)?.[0] ?? "";

test("дропдаун задач: поле пошуку з плейсхолдером і заголовок «Нещодавні» при порожньому запиті", () => {
  const h = dd();
  assert.match(h, /<input[^>]*id="task-q"/);
  assert.ok(h.includes(`placeholder="${t("taskSearchPh")}"`), "плейсхолдер зі словника");
  assert.ok(h.includes(t("recentTasks")), "порожній запит — «Нещодавні»");
  assert.ok(!dd({ taskQuery: "перш" }).includes(t("recentTasks")), "із запитом заголовка нема");
});

test("дропдаун задач: значення поля — з state.taskQuery, екрановане", () => {
  assert.match(dd({ taskQuery: 'a"b<' }), /id="task-q"[^>]*value="a&quot;b&lt;"/);
});

test("дропдаун задач: фільтр за ключем / id / назвою, усі слова, без регістру", () => {
  const ids = (q) => [...dd({ taskQuery: q }).matchAll(/data-act="task" data-val="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids(""), ["alpha", "beta", "gone", "boss-interface"]);
  assert.deepEqual(ids("liga-22"), ["beta"]);
  assert.deepEqual(ids("BOSS"), ["boss-interface"]);
  assert.deepEqual(ids("друга задача"), ["beta"]);
  assert.deepEqual(ids("друга перша"), []);
});

test("пункт: ключ Jira зверху, назва без дубля ключа, ✓ на поточній", () => {
  const h = dd();
  const a = itemOf(h, "alpha");
  assert.match(a, /dd-k">LIGA-11</, "ключ окремим рядком");
  assert.match(a, /dd-t">Перша задача</, "назва без ключа");
  assert.ok(!/LIGA-11 · Перша/.test(a), "ключ не дублюється в назві");
  assert.match(a, /dd-item--on/);
  assert.match(a, /<use href="#i-check"/, "✓ на поточній");
  assert.ok(!/#i-check/.test(itemOf(h, "beta")), "✓ лише на поточній");
  assert.match(itemOf(h, "boss-interface"), /dd-k">boss-interface</, "без Jira ключ = id");
});

test("пункт: підсвітка збігів у <mark>, а текст назви лишається текстом (екранування ДО підсвітки)", () => {
  const b = itemOf(dd({ taskQuery: "задача" }), "beta");
  assert.match(b, /<mark>задача<\/mark>/);
  assert.ok(!b.includes("<b>"), "тег з назви не став розміткою");
  assert.match(b, /&lt;b&gt;<mark>задача<\/mark>&lt;\/b&gt;/);
  const k = itemOf(dd({ taskQuery: "liga-2" }), "beta");
  assert.match(k, /dd-k"><mark>LIGA-2<\/mark>2</, "ключ підсвічується теж");
});

test("задача без теки: причина в приглушеному рядку, пункт ПОЗНАЧЕНИЙ, але не disabled (Enter мусить сказати причину)", () => {
  const g = itemOf(dd(), "gone");
  assert.match(g, /dd-item--missing/);
  assert.ok(g.includes(t("folderMissing")));
  assert.ok(!/\sdisabled/.test(g), "disabled зробив би пункт недосяжним для клавіатури");
  assert.ok(!itemOf(dd(), "beta").includes(t("folderMissing")));
});

test("taskCursor позначає активний пункт; за межами — затискається; футер = останній досяжний", () => {
  const cur = (h) => [...h.matchAll(/<button[^>]*dd-item--cur[^>]*data-act="([^"]+)" data-val="([^"]*)"/g)]
    .map((m) => `${m[1]}:${m[2]}`);
  assert.deepEqual(cur(dd({ taskCursor: 1 })), ["task:beta"]);
  assert.deepEqual(cur(dd({ taskCursor: 0 })), ["task:alpha"]);
  assert.deepEqual(cur(dd({ taskCursor: 99 })), ["home:"], "понад кінець — футер");
  assert.deepEqual(cur(dd({ taskCursor: -5 })), ["task:alpha"]);
  assert.deepEqual(cur(dd({ taskCursor: 4 })), ["home:"], "індекс n (після n пунктів) — футер");
});

test("футер «Усі задачі»: data-act=home, останній у списку з підказкою клавіш", () => {
  const h = dd();
  const acts = [...h.matchAll(/data-act="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(acts.at(-1), "home");
  assert.ok(h.includes(t("allTasks")));
  assert.ok(h.includes(t("ddKeysHint")));
  assert.equal(taskListHTML(S({ taskList: TASKS })).includes("data-act=\"home\""), false,
    "футер не входить у перемальовку списку");
});

test("порожня видача: активного пункту нема (-1), футер активний лише після ↓ (0)", () => {
  const none = dd({ taskQuery: "zzzz", taskCursor: -1 });
  assert.ok(!/dd-item--cur/.test(none), "активного нема");
  assert.ok(!/aria-activedescendant/.test(none));
  assert.match(dd({ taskQuery: "zzzz", taskCursor: 0 }), /dd-item--foot dd-item--cur/);
  // непорожня видача -1 не діє: перший пункт активний
  assert.match(itemOf(dd({ taskCursor: -1 }), "alpha"), /dd-item--cur/);
});

test("a11y: combobox-поле керує listbox-ом через aria-activedescendant; поточна — aria-current", () => {
  const h = dd({ taskCursor: 1 });
  const input = /<input[^>]*id="task-q"[^>]*>/.exec(h)[0];
  assert.match(input, /role="combobox"/);
  assert.match(input, /aria-controls="task-list"/);
  assert.match(input, /aria-activedescendant="task-opt-1"/);
  assert.match(h, /<div class="dd-list" id="task-list" role="listbox"/);
  assert.match(itemOf(h, "beta"), /id="task-opt-1"/);
  assert.match(itemOf(h, "beta"), /dd-item--cur/, "id у активного збігається з курсором");
  assert.match(itemOf(h, "alpha"), /aria-current="true"/, "поточна задача");
  assert.ok(!/aria-current/.test(itemOf(h, "beta")));
  assert.ok(!/aria-selected/.test(h), "aria-selected не вживаємо — це не вибір");
  assert.match(dd({ taskCursor: 99 }), /aria-activedescendant="task-opt-foot"/);
  assert.match(dd({ taskCursor: 99 }), /id="task-opt-foot"/);
});

test("нічого не знайдено: текст із запитом (екранованим), футер лишається", () => {
  const h = dd({ taskQuery: "<zz>" });
  assert.ok(h.includes(t("noTasksFound", "&lt;zz&gt;")));
  assert.ok(!/data-act="task"/.test(h));
  assert.match(h, /data-act="home"/);
});

/* Без `state.taskList` (наприклад, дропдаун ще не відкривали) дропдаун не
   падає — лишається порожнім списком, а не кидає на `undefined.map`. */
test("дропдаун задачі не падає без state.taskList", () => {
  assert.doesNotThrow(() => barHTML(barModel(S({ openDd: "task" })), S({ openDd: "task" })));
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
  for (const dd of [null, "task", "iter", "more", "gl", "pub"]) {
    const st = S({ openDd: dd, commentMode: "project", iterList, taskList, gl: "behind" });
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
  const h = html({ space: SP() });
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
  const c = chip(html({ space: SP({ name: long }) }));
  assert.match(c, /data-dd="space" title="Дуже довга назва простору клієнта «Альфа» &amp; Co"/);
  const evil = chip(html({ space: SP({ name: '"><img src=x onerror=alert(1)>' }) }));
  assert.doesNotMatch(evil, /<img/, "назва з даних не стала тегом");
  assert.match(evil, /title="&quot;&gt;&lt;img/);
});

test("фішка стоїть після палітри й ПЕРЕД крошками задачі", () => {
  const h = html({ space: SP() });
  const pal = h.indexOf('data-act="palette"');
  const sp = h.indexOf('data-dd="space"');
  const crumbs = h.indexOf('class="crumbs"');
  assert.ok(pal !== -1 && sp !== -1 && crumbs !== -1);
  assert.ok(pal < sp && sp < crumbs, "порядок: палітра → простір → крошки");
});

test("без `space` фішки нема ніде — ні в смузі задачі, ні на екрані «Задачі»", () => {
  assert.doesNotMatch(html(), /data-dd="space"/);
  assert.doesNotMatch(html({ homeOpen: true }), /data-dd="space"/);
  assert.doesNotMatch(html({ space: null }), /space-dot/);
});

test("на екрані «Задачі» фішка є — це той самий перемикач, а не крошка", () => {
  const h = html({ space: SP(), homeOpen: true });
  assert.ok(chip(h), "на екрані «Задачі» фішки нема");
  assert.ok(h.indexOf('data-dd="space"') < h.indexOf("crumb--flat"), "фішка перед крошкою «Задачі»");
});

test("назва простору екранується: <b> не стає тегом, лапка не виходить з атрибута", () => {
  const evil = '<b>x</b>" onclick="alert(1)';
  const h = html({ space: SP({ name: evil }) });
  assert.doesNotMatch(h, /<b>x<\/b>/, "назва стала розміткою");
  assert.match(chip(h), /&lt;b&gt;x&lt;\/b&gt;/);
  assert.doesNotMatch(h, /onclick="alert/, "лапка вийшла з атрибута");
});

test("колір: лише space-1…6; усе інше — space-1, а не довільний CSS у style", () => {
  const dot = (color) => /class="space-dot"[^>]*style="([^"]*)"/.exec(chip(html({ space: SP({ color }) })))[1];
  assert.equal(dot("space-4"), "background:var(--space-4)");
  for (const bad of ["red", "space-2);position:fixed;(", "space-9", undefined]) {
    assert.equal(dot(bad), "background:var(--space-1)", String(bad));
  }
});

test("дропдаун просторів: закритий — нема; відкритий — перелік із ✓, підписом і діями", () => {
  assert.doesNotMatch(html({ space: SP(), spaces: SPACES }), /Простори/);
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
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
test("дропдаун просторів: «Підключення…» після «Назва й колір…»", () => {
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(h, /data-act="spaceedit"[\s\S]*?<\/button>\s*<button[^>]*data-act="conn"[\s\S]*?Підключення…/);
  const conn = /<button[^>]*data-act="conn"[\s\S]*?<\/button>/.exec(h)?.[0];
  assert.match(conn, /<svg/, "пункт без іконки");
  assert.equal((h.match(/data-act="conn"/g) || []).length, 1, "пункт один");
  assert.doesNotMatch(html({ space: SP(), spaces: SPACES }), /data-act="conn"/, "закритий дропдаун пункту не несе");
  assert.match(html({ space: SP(), openDd: "space" }), /data-act="conn"/, "без переліку просторів пункт теж є");
});

/* Клавіатурний roving по дропдауну просторів іде за `.dd--spaces .dd-item` (`app.js`, `rovingIndex`): пункт без цього
   класу випав би зі стрілок. Тож «Підключення…» мусить бути саме `ddItem`, а не окремою кнопкою. */
test("дропдаун просторів: «Підключення…» — `dd-item` у `.dd--spaces`, тож клавіатурний roving його бере", () => {
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
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
test("дропдаун просторів: «Підключення…» нема на самій сторінці «Підключення», є скрізь, де ведуть на неї", () => {
  const on = (o) => /data-act="conn"/.test(html({ space: SP(), spaces: SPACES, openDd: "space", ...o }));
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

test("дропдаун просторів: «Connections…» англійською", () => {
  setLang("en");
  try {
    assert.match(html({ space: SP(), spaces: SPACES, openDd: "space" }), /data-act="conn"[\s\S]*?Connections…/);
  } finally { setLang("uk"); }
});

/* Смуга на сторінці «Підключення»: склад як на «Задачах», крошка інша. Плоска крошка — не кнопка, «назад до задачі»
   лишається (вона про задачу, з якої прийшли, а не про сторінку). */
test("смуга на сторінці «Підключення»: плоска крошка «Підключення», «назад до задачі» лишається", () => {
  const h = html({ space: SP(), homeOpen: true, homePage: "conn", taskId: "t1" });
  assert.match(h, /crumb crumb--flat[\s\S]*?Підключення</);
  assert.doesNotMatch(h, /<span class="txt">Задачі</);
  assert.match(h, /data-act="back"/);
  /* Екран, а не смуга задачі: зони 2 і 3 порожні, як на «Задачах». Логотип тут НЕ «поточний»: сторінка названа крошкою. */
  assert.equal((h.match(/class="zone /g) || []).length, 3);
  assert.doesNotMatch(h, /data-act="figma"|data-act="publish"|data-dd="iter"/);
  assert.doesNotMatch(/<button[^>]*data-act="home"[^>]*>/.exec(h)[0], /ctl--on|aria-current/);
  /* Іконка крошки — `sliders` (та сама, що в дропдауні й палітрі), а не `grid` «Задач». */
  const flat = (x) => /<span class="crumb crumb--flat crumb--page">[\s\S]*?<\/span><\/span>/.exec(x)[0];
  const tasks = flat(html({ space: SP(), homeOpen: true, taskId: "t1" }));
  assert.match(flat(h), /#i-sliders/);
  assert.doesNotMatch(flat(h), /#i-grid/);
  assert.match(tasks, /#i-grid[\s\S]*Задачі</, "крошка «Задач» змінилась");
  /* Без задачі «назад» вести нікуди — і на цій сторінці теж. */
  assert.doesNotMatch(html({ space: SP(), homeOpen: true, homePage: "conn", taskId: "" }), /data-act="back"/);
});

/* Смуга на сторінці майстра (етап 3b): плоска крошка «Новий простір» з іконкою `plus`; жодної фішки простору й кнопки
   «назад до задачі» (модель їх не дає — розмітка не малює). Дві перевірки: на готовій моделі (контракт `crumb-wiz`) і наскрізно
   через `barModel` (склад, який справді збирає застосунок). */
test("крошка майстра: іконка plus і «Новий простір», жодної фішки простору й кнопки «назад»", () => {
  const model = { zone1: [{ id: "home", tier: 0, on: false }, { id: "palette", tier: 0 }, { id: "crumb-wiz", tier: 0, labelKey: "wzCrumb" }], zone2: [], zone3: [] };
  const h = barHTML(model, {});
  assert.match(h, /<span class="crumb crumb--flat crumb--page">[\s\S]*?#i-plus[\s\S]*?<span class="txt">Новий простір<\/span>/);
  assert.doesNotMatch(h, /data-act="back"/);
  assert.doesNotMatch(h, /space-chip/);
  /* Це «головний» склад оверлею: зони 2 і 3 порожні, жодного контрола задачі. */
  assert.equal((h.match(/class="zone /g) || []).length, 3);
  assert.doesNotMatch(h, /data-act="figma"|data-act="publish"|data-dd="iter"|data-dd="task"/);
});

test("смуга на сторінці майстра: з простором і задачею в стані — без фішки й «назад», крошка «Новий простір», логотип не світиться", () => {
  const h = html({ space: SP(), spaces: SPACES, homeOpen: true, homePage: "wiz", taskId: "t1" });
  assert.match(h, /<span class="crumb crumb--flat crumb--page">[\s\S]*?#i-plus[\s\S]*?<span class="txt">Новий простір<\/span>/);
  assert.doesNotMatch(h, /data-dd="space"/, "фішка простору на майстрі");
  assert.doesNotMatch(h, /data-act="back"/, "«назад до задачі» на майстрі");
  assert.doesNotMatch(h, /<span class="txt">Задачі<\/span>|<span class="txt">Підключення<\/span>/, "чужа крошка");
  const logo = /<button[^>]*data-act="home"[^>]*>/.exec(h);
  assert.ok(logo, "дорога на «Задачі» (логотип) мусить лишитись");
  assert.doesNotMatch(logo[0], /ctl--on|aria-current/);
  assert.match(logo[0], /aria-label="[^"]+"/);
  assert.match(h, /data-act="palette"/, "двері в палітру на місці");
  /* Англійською крошка — своє слово. */
  setLang("en");
  try {
    assert.match(html({ space: SP(), homeOpen: true, homePage: "wiz" }), /<span class="txt">New space<\/span>/);
  } finally { setLang("uk"); }
  /* Свідок: на «Задачах» із тим самим станом фішка й «назад» є. */
  const tasks = html({ space: SP(), spaces: SPACES, homeOpen: true, taskId: "t1" });
  assert.match(tasks, /data-dd="space"/);
  assert.match(tasks, /data-act="back"/);
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
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
  const gone = /<button[^>]*data-val="gone"[\s\S]*?<\/button>/.exec(h)[0];
  assert.match(gone, /dd-item--muted/);
  assert.doesNotMatch(gone, / disabled/, "вимкнений пункт не клікнути — а перейти й побачити причину треба");
  assert.match(gone, /файл задач недоступний/);
  assert.doesNotMatch(gone, /0 задач/, "«0 задач» про недоступний простір — брехня");
});

test("дропдаун просторів: назви й шляхи з реєстру екрануються", () => {
  const spaces = [{ id: "e", name: "<img src=x onerror=1>", color: "space-1", path: '"><script>', tasks: 1 }];
  const h = html({ space: SP({ id: "e" }), spaces, openDd: "space" });
  assert.doesNotMatch(h, /<img src=x/);
  assert.doesNotMatch(h, /<script>/);
});

test("дропдаун просторів без переліку не падає: лише дії «Новий…» і «Назва й колір…»", () => {
  const h = html({ space: SP(), openDd: "space" });
  assert.match(h, /data-act="spacenew"/);
  assert.match(h, /data-act="spaceedit"/);
  assert.doesNotMatch(h, /data-act="space"/);
});

test("дропдаун просторів у англійському інтерфейсі — англійською", () => {
  setLang("en");
  try {
    const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
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
  const h = html({ space: SP({ id: "p" }), spaces: evil, openDd: "space" });
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
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
  const rows = [...h.matchAll(/<button[^>]*data-act="space"[^>]*>/g)].map((m) => m[0]);
  assert.equal(rows.length, 3);
  assert.doesNotMatch(rows[0], /aria-current/);
  assert.match(rows[1], /data-val="p"[^>]*aria-current="true"/);
  assert.doesNotMatch(rows[2], /aria-current/);
  assert.equal((h.match(/aria-current/g) || []).length, 1, "поточний — один на весь дропдаун");
  // `current` — необовʼязковий параметр `ddItem`: решта дропдаунів його не знає
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  for (const openDd of ["iter", "gl", "pub", "more"]) {
    assert.doesNotMatch(html({ openDd, iterList, gl: "behind" }), /aria-current/, openDd);
  }
});

test("дропдаун просторів: роздільник перед «Новий простір…» є з переліком і нема без нього", () => {
  const withList = html({ space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(withList,
    /data-val="gone"[\s\S]*?<\/button>\s*<div class="dd-sep"><\/div>\s*<button[^>]*data-act="spacenew"/);
  assert.doesNotMatch(html({ space: SP(), openDd: "space" }), /dd-sep/, "порожній перелік — роздільника нема");
});

/* Снапшот-страж: простір З інтеграціями змінює смугу рівно на фішку — ні байтом
   більше. Це те, що береже ЛІГА (legacy-простір) від випадкових змін розмітки. */
test("розмітка зі space без відомостей про ролі = розмітка без space мінус блок фішки — побайтно", () => {
  const stripChip = (h) => h.replace(/<div class="ddhost space-h">[\s\S]*?<\/div>/, "");
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  for (const o of [{}, { homeOpen: true }, { openDd: "pub" }, { openDd: "gl", gl: "behind" },
    { openDd: "iter", iterList }, { openDd: "more" }, { hasIteration: false }, { tasksErr: true }]) {
    const withSpace = html({ ...o, space: { id: "p", name: "P", color: "space-2" } });
    assert.ok(chip(withSpace), `фішки нема: ${JSON.stringify(o)}`);
    assert.equal(stripChip(withSpace), html(o), `розмітка розійшлась: ${JSON.stringify(o)}`);
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

/* ── Пігулка оновлення (0.23.0) ────────────────────────────────────────────
   Є лише при `available` (рішення — `pillModel`), стоїть ОДРАЗУ ПІСЛЯ дверей у палітру й перед крошками, і на екрані «Задачі»
   теж. `data-act="update"` ↔ `id` контролу моделі. */
const UPD = { current: "0.1.0", latest: "0.2.0", available: true, state: "ok", checked_at: 1, boot: "a", restart_failed: false };

test("оновлення: пігулка є лише коли available; без нього вузла нема", () => {
  assert.match(html({ update: UPD }), /data-act="update"/);
  for (const update of [undefined, null, { ...UPD, available: false }, { ...UPD, state: "offline" }, { ...UPD, state: null }]) {
    assert.doesNotMatch(html({ update }), /data-act="update"|upd-pill/, JSON.stringify(update));
  }
});

test("оновлення: порядок — логотип, палітра, ПІГУЛКА, крошки, зона 2; на екрані «Задачі» так само", () => {
  for (const o of [{}, { homeOpen: true }, { homeOpen: true, homePage: "conn", taskId: "t1" }, { space: { id: "a", name: "A", color: "space-1" } }]) {
    const h = html({ update: UPD, ...o });
    const pal = h.indexOf('data-act="palette"');
    const upd = h.indexOf('data-act="update"');
    const crumbs = h.indexOf('class="crumbs"');
    assert.ok(pal !== -1 && upd !== -1 && crumbs !== -1, JSON.stringify(o));
    assert.ok(pal < upd, "пігулка мусить стояти ПІСЛЯ дверей у палітру");
    assert.ok(upd < crumbs, "пігулка мусить стояти ПЕРЕД крошками");
    if (o.space) assert.ok(upd < h.indexOf('data-dd="space"'), "і перед фішкою простору");
  }
});

test("оновлення: підпис пігулки — з версією, мовою інтерфейсу; ярус підпису — той самий, що в палітри", () => {
  setLang("uk");
  assert.match(html({ update: UPD }), /Оновлення 0\.2\.0/);
  setLang("en");
  assert.match(html({ update: UPD }), /Update 0\.2\.0/);
  setLang("uk");
  assert.equal(barModel(S({ update: UPD })).zone1.find((x) => x.id === "update").labelTier,
    barModel(S()).zone1.find((x) => x.id === "palette").labelTier);
});

test("оновлення: розмітка смуги з пігулкою збалансована за тегами", () => {
  const h = html({ update: UPD });
  for (const tag of ["div", "button", "span"]) {
    assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length, (h.match(new RegExp(`</${tag}>`, "g")) || []).length, tag);
  }
});

/* ── «Відгук» (0.23.0, Task 8) ─────────────────────────────────────────────
   Кнопка-іконка на ВСІХ екранах (задача, «Задачі», «Підключення», майстер): одразу після дверей у палітру, а коли є пігулка оновлення —
   після неї; перед фішкою простору й крошками. Стан без ключа `update` (еталони ЛІГИ) кнопки не має. */
test("«Відгук»: є на всіх екранах і доступний з клавіатури (нативна button, title/aria-label)", () => {
  setLang("uk");
  for (const o of [{}, { hasIteration: false }, { homeOpen: true }, { homeOpen: true, taskId: "" }, { homeOpen: true, homePage: "conn" }, { homeOpen: true, homePage: "wiz" }]) {
    const h = html({ update: null, ...o });
    const m = /<button[^>]*data-act="feedback"[^>]*>[\s\S]*?<\/button>/.exec(h);
    assert.ok(m, `${JSON.stringify(o)}: кнопки «Відгук» нема`);
    assert.match(m[0], /title="Баг \/ ідея"/);
    assert.match(m[0], /aria-label="Баг \/ ідея"/);
    assert.match(m[0], /<svg/);
    assert.doesNotMatch(m[0], /tabindex="-1"/, "кнопка мусить бути досяжна клавіатурою");
  }
  assert.doesNotMatch(html(), /data-act="feedback"/, "стан без ключа update — еталон: кнопки нема");
});

test("«Відгук»: порядок — палітра, пігулка оновлення (коли є), «Відгук», фішка простору, крошки", () => {
  for (const o of [{}, { homeOpen: true }, { homeOpen: true, homePage: "conn", taskId: "t1" }, { space: { id: "a", name: "A", color: "space-1" } }]) {
    for (const update of [null, UPD]) {
      const h = html({ update, ...o });
      const pal = h.indexOf('data-act="palette"');
      const upd = h.indexOf('data-act="update"');
      const fb = h.indexOf('data-act="feedback"');
      const crumbs = h.indexOf('class="crumbs"');
      assert.ok(pal !== -1 && fb !== -1 && crumbs !== -1, JSON.stringify(o));
      assert.ok(pal < fb, "«Відгук» — після дверей у палітру");
      if (update) assert.ok(upd !== -1 && upd < fb, "і після пігулки оновлення");
      assert.ok(fb < crumbs, "і перед крошками");
      if (o.space) assert.ok(fb < h.indexOf('data-dd="space"'), "і перед фішкою простору");
    }
  }
});

test("«Відгук»: розмітка смуги збалансована за тегами", () => {
  const h = html({ update: UPD });
  for (const tag of ["div", "button", "span"]) {
    assert.equal((h.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length, (h.match(new RegExp(`</${tag}>`, "g")) || []).length, tag);
  }
});

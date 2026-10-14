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
const SP = (o = {}) => ({ id: "p", name: "P", color: "space-2", integrations: false, ...o });
const chip = (h) => /<button[^>]*data-dd="space"[\s\S]*?<\/button>/.exec(h)?.[0];

test("простір без інтеграцій: розмітка не кидає, без GitLab і публікації, Figma лишається", () => {
  let h;
  assert.doesNotThrow(() => { h = html({ space: { integrations: false } }); });
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
test("розмітка зі space{integrations:true} = розмітка без space мінус блок фішки — побайтно", () => {
  const stripChip = (h) => h.replace(/<div class="ddhost space-h">[\s\S]*?<\/div>/, "");
  const iterList = [{ id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: false }];
  for (const o of [{}, { homeOpen: true }, { openDd: "pub" }, { openDd: "gl", gl: "behind" },
    { openDd: "iter", iterList }, { openDd: "more" }, { hasIteration: false }, { tasksErr: true }]) {
    const withSpace = html({ ...o, space: SP({ integrations: true }) });
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

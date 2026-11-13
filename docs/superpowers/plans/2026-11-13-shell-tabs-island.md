# Реліз 0.25.0 «Вкладки й острівець» (етап А редизайну оболонки) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** над смугою зʼявляється рядок вкладок відкритих задач (логотип → «Задачі», вкладки з кольором простору й станом Claude, «+», пігулка оновлення, шестерня → «Налаштування»); смуга задачі худне до ітерації й назви, режимів і ширин, Figma/Git/Публікації; острівець унизу стає інтерактивним (стан Claude | інспектор | баг/ідея); «Огляд» рухається колесом, а масштабується ⌘/Ctrl + колесом і щипком.

**Architecture:** три нові чисті модулі без DOM (`app/tabs-model.js` — список вкладок і правила відкриття/закриття/чистки; `app/tabs-view.js` — розмітка рядка вкладок; `app/island.js` — розмітка інструментів острівця) з тестами `node:test`; `app/bar-model.js`/`app/shell-bar.js` втрачають контроли, що переїхали; проводка — в `app/app.js` через наявні `BAR_ACTIONS` (делегація з нових вузлів `#tabs` і `#hud`); сервер отримує один читальний маршрут `GET /api/claude-statuses` (чиста функція `claude_views` у `serve.py`). Камера: чиста `wheelIntent` у `app/camera.js`.

**Tech Stack:** ванільний ES-модульний JS (`node:test`), CSS у `app/styles.css`, Python 3 stdlib (`unittest`, 3.9-сумісний), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-13-shell-redesign-design.md`, розділ «Етап А». Продуктові принципи: `PRODUCT.md`. Візуальний референс — прототип v5 власника (артефакт; у репо його нема — тексти й розміри нижче достатні). **ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач.**

**Рівень строгості — середній** (`PRODUCT.md`/процес): лише інтерфейс і один читальний маршрут, дані не змінюються. Без таблиць мутацій, але **кожна нова перевірка доводиться мутацією** (один рядок → червоніє → відновлено). Один ревʼюер у кінці (після T11), перед релізом — перевірка проти живого канвасу.

Базова лінія на `646f7b2`: JS `node --test tests/*.test.mjs` — записати число з першого прогону в звіті T1 (на 0.24.0 було 2067 pass).

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Робоче дерево: `<repo>` = `deai-canvas-dev`, гілка `feat/shell-redesign`. Коміти лише так, з переліком шляхів; новий файл спершу `git add -- <шлях>`:
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`; ніколи `--amend`, `stash`, `reset`, `checkout` інших гілок.
- ⛔ Живий канвас працює з ІНШОГО дерева (`deai-canvas`, порт 8765). Його не чіпаємо: ні файлів, ні процесу, ні порту.
- ⛔ У жоден комітований файл не пишемо справжніх імен, хостів, імен користувачів машини, ключів, шляхів зі scratchpad чи тимчасових тек.
- Правки наявних файлів — точкові (`Edit`); нові файли — `Write`.

**Прогони й середовище**

- JS (після кожної задачі): `node --test tests/*.test.mjs && node tests/inspector-core.test.mjs`.
- Python (лише T4 і T11): кожен прогін під тимчасовим `HOME`, без `DC_TASKS_FILE`/`DEAI_HOME`, без `.pyc`:
  `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'` (і так само `-s bin`, `-s app`).
- Живі — по одному файлу, ПОСЛІДОВНО:
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`.
- Мережі в тестах нема; порти 8765/4317 не чіпаються; справжні `~/.deai`, `~/deai-work`, `~/deai-published`, `~/.claude/pipeline-feedback/`, `~/.gitconfig`, справжній `tasks.json` не змінюються; процеси зупиняємо лише за PID (ніколи `pkill -f`/`killall`).
- ≤ 1 виконавець одночасно. Тести, які ламає задача, правляться в ТІЙ САМІЙ задачі й згадуються у звіті одним рядком із причиною.
- Кириличних рядкових літералів у `app/*.js` (крім `i18n.js`) бути не може — `tests/i18n-literals.test.mjs`; тексти лише через `t()`. Іконки — лише з `app/icons.js` (`tests/icons.test.mjs` звіряє виклики `ico('…')`).

---

## Поправки до спеки (звірено з кодом на `646f7b2`; мають перевагу)

1. **Окремий вузол `#tabs`, не всередині `#bar`.** Смуга `#bar` лишається рівно смугою (модель/розмітка `bar-model`/`shell-bar`); рядок вкладок — свій вузол над нею: `<nav id="tabs" class="tabs">` у `app/index.html` ПЕРЕД `#bar`. Висоти — токени: `--h-tabs:36px` і `--h-top:calc(var(--h-tabs) + var(--h-bar))` у `:root` (`styles.css:51`). Усі споживачі «низ смуги» (`top:46px` у `.cv-stage`, `.cv-canvas`, `.pages-panel`; `top:var(--h-bar)` у `.errbar`, `.panel`, `.insp`, `#tasks-home`, `.cn-drawer`) переходять на `var(--h-top)`; `.bar-mount` і `.bar` — `top:var(--h-tabs)`. Чистий перегляд ховає й `#tabs` (`html.cv-clean #tabs`), і правило `html.cv-clean .cv-stage{top:0}` лишається.
2. **Вкладки — клієнтський стан під ключем `dc-tabs`** (`localStorage`, у `try/catch`, як інші `dc-*`): `{"v":1,"tabs":[{id,title,space,color,jira}]}`. Ключ вкладки — `id` задачі (сервер перемикає задачу за `id`: `POST /api/task-switch {id}`). Ліміт 12 вкладок: при переповненні випадає найстаріша неактивна.
3. **Відкриття задачі будь-яким шляхом додає вкладку** — в одному місці: після успішного читання задачі в `render()` (`app.js:1150`, де ставиться `curTask`/`curTaskList`) викликається `rememberTab()`; так покриті і старт, і `switchTask`, і картки «Задач», і ⌘K, і агент, що перемкнув задачу.
4. **Чистка вкладок.** Перевірити можна лише задачі ПОТОЧНОГО простору (`/api/tasks` віддає список поточного): після успішного `render()` прибираються вкладки, у яких `space === <поточний простір>` і `id` нема в `curTaskList.tasks`. Вкладка іншого простору, якої вже нема, лишається, доки людина її не закриє: перемикання на неї покаже причину тостом (`switchTask` → `tell`), а мовчки викидати вкладку через збій мережі чи тимчасово недоступний простір — гірше за одну зайву вкладку. Задача без теки (`refuseMissingTask`) — теж лишається: теку можуть повернути. Без шару просторів (`space` порожній) — порівнюємо всі вкладки з `space === null`.
5. **Стан Claude на кожній вкладці** — новий читальний маршрут `GET /api/claude-statuses` → `{"tasks": {"<ключ>": {"state","age_s"}}}`, де ключ — те, що шле мод у серцебитті (`id` або Jira-ключ задачі). Чиста `claude_views(beats, now)` у `serve.py` поруч із `claude_view` (`serve.py:1193`) застосовує ТОЙ САМИЙ TTL і ту саму мапу станів. Маршрут не потребує задачі й реєстру: додається в `Handler._MACHINE_ROUTES`. Клієнт опитує його тим самим таймером, що `/api/claude-status` (`CLAUDE_EVERY_MS`), лише коли відкрита хоч одна вкладка; вкладка бере `tasks[id] ?? tasks[jira]`.
6. **Склад смуги задачі** (`barModel`, звичайна гілка): `zone1 = [iter?, title]`, де `title` — `{id:"title", tier:0, label}` (назва задачі без префікса, `cleanTitle`; приглушена). Зникають: `home`, `palette`, `space`, `task` (перемикач задач із пошуком), `update`, `feedback`; із `zone2` — `inspector`. Ярус «⋯» лишається лише для ширин (`vp`, `TIERS.view`).
7. **Склад смуги «Задач»/«Налаштувань»/майстра:** `wiz` → `zone1 = [crumb-wiz]`; `tasks`/`conn` → `zone1 = [space?, crumb-tasks|crumb-conn]`. Зникають `home`, `palette`, `back`, `update`, `feedback`. «Нова задача» лишається на самому екрані (до етапу Д).
8. **Перемикач задач у смузі видаляється повністю**, разом із проводкою: `crumbTask`, `taskListHTML`, `taskFootHTML`, `visibleTasks`, `taskCursorIndex`, `activeAttr` (`shell-bar.js`), стан і обробники `taskQ`/`taskCursor`/`taskComposing`/`taskPaintPending`/`taskDdWasOpen`/`#task-q`/`.dd--tasks` (`app.js`), CSS `.dd--tasks*`. `mark()` лишається (його бере `tasks-home.js`). Ключі i18n, що стали непотрібні, видаляються з обох словників (тест `i18n-keys` має бути зеленим).
9. **«Підключення» → «Налаштування»** в етапі А — лише назва й вхід: `cnTitle` = «Налаштування» / «Settings», `cnTitleIn` = «Налаштування · {name}» / «Settings · {name}», `spaceConn` = «Налаштування простору «{name}»» / «Settings of the space “{name}”». Розкладка сторінки — етап Е.
10. **Острівець — один вузол `#hud`** замість `#claude-hud` як контейнера: `<div id="hud" class="cv-hud"><div class="island"><div id="claude-hud" class="isl-claude" role="status"></div><div id="isl-tools" class="isl-tools"></div></div></div>`. `#claude-hud` лишається з тим самим id і `role="status"` (його заповнює `paintClaude`, `ISLAND_SHELL` усередині); `role="status"` — лише на сегменті Claude, не на кнопках. `.cv-hud` лишається `pointer-events:none`; `.island` — `pointer-events:auto`. Острівець видно завжди, крім чистого перегляду (на «Задачах»/«Налаштуваннях» — лише баг, сегмента Claude там нема). Тост і стійкі плашки піднімаються над острівцем завжди, а не лише при `claude-on`.
11. **Кнопки острівця тримають наявні імена дій**: `data-act="inspector"` (лише в «Макеті») і `data-act="feedback"`; делегація кліку з `#hud` іде в ті самі `BAR_ACTIONS` (як делегація з `#insp-panel`, `app.js:6056`). Кнопка коментарів — етап Б.
12. **Логотип у рядку вкладок** тримає `data-act="home"`; шестерня — нова дія `settings` (`enterHome({page:'conn'})` з тим самим захистом незбереженої панелі, що в `home`); «+» — нова дія `tabnew` (= `home`); вкладка — `tab` (перемкнути; з відкритих «Задач» — через `homeOpenTask`); хрестик — `tabclose`. `BAR_ACTIONS.back` видаляється (у палітрі дії `back` нема). Пігулка оновлення переїжджає в рядок вкладок без змін розмітки (`updatePillHTML`, `data-act="update"`).
13. **Колесо в «Огляді»** (`app.js:7368`): `ctrlKey || metaKey` → масштаб (щипок трекпада приходить як `wheel` з `ctrlKey`; підсилення `PINCH_GAIN = 6` лише для `ctrlKey`), інакше — рух камери на `deltaX/deltaY` (з `deltaMode` 1 = рядки ×16, 2 = сторінки × висоту вьюпорта). Ті самі винятки (панель скарг, панель коментатора) лишаються. Чиста `wheelIntent(e, viewH)` і `panBy(cam, dx, dy)` — у `app/camera.js`.
14. **`#cv-zoom` стає кнопкою** (`<button id="cv-zoom" class="cv-zoom" type="button">`) з тим самим відсотком; клік → `fitAll()` і скидання `userMoved`. `#canvas-hint` перекладається (`t('canvasHint')`, текст ставить `app.js` при старті й при зміні мови) і стоїть над острівцем (`bottom:66px`); правило `body.claude-on #canvas-hint{visibility:hidden}` прибирається, натомість підказка ховається, коли острівець піднято (`body.claude-lift`).
15. **Еталони ЛІГИ (`tests/fixtures/legacy-golden/`) змінюються свідомо** — смуга ЛІГИ втратила контроли так само, як усі. Перезнімаються в T6 (`UPDATE_GOLDEN=1 node --test tests/legacy-golden.test.mjs`), diff еталонів переглядається очима й коротко описується у звіті (що зникло — лише контроли з поправок 6–7).

---

## Структура файлів

| Файл | Що робить | Задача |
|---|---|---|
| `app/icons.js` | + `bug`, `gear` | T1 |
| `app/i18n.js` | нові ключі (вкладки, острівець, підказка, логотип), перейменування «Налаштування» | T1 |
| `app/tabs-model.js` (новий) | читання/запис/відкриття/закриття/чистка вкладок, модель рядка | T2 |
| `app/tabs-view.js` (новий) | розмітка рядка вкладок | T3 |
| `app/serve.py` | `claude_views`, `GET /api/claude-statuses` | T4 |
| `app/island.js` (новий) | розмітка інструментів острівця | T5 |
| `app/bar-model.js`, `app/shell-bar.js` | худа смуга, без перемикача задач | T6 |
| `app/app.js`, `app/index.html`, `app/styles.css` | проводка вкладок і острівця, висоти | T7 |
| `app/camera.js`, `app/app.js`, `app/index.html`, `app/styles.css` | колесо, кнопка масштабу, підказка | T8 |
| `tests/css-guards.test.mjs`, `tests/live/tabs.test.mjs` (новий) | охоронці й живий сценарій | T9 |
| `tests/live/*.test.mjs` | селектори, що переїхали | T10 |
| `CHANGELOG.md`, `package.json`, `README.md` | реліз 0.25.0 | T11 |

---

### Task 1: Іконки й тексти

**Files:**
- Modify: `app/icons.js` (мапа `ICONS`)
- Modify: `app/i18n.js` (обидва словники, `uk` і `en`)
- Test: `tests/icons.test.mjs`, `tests/i18n-keys.test.mjs` (наявні — мають лишитись зеленими)

- [ ] **Step 1: Базова лінія.** `node --test tests/*.test.mjs 2>&1 | tail -5` — записати `pass`/`fail` у звіт.

- [ ] **Step 2: Додати іконки** в `ICONS` (після `x`), у тому ж стилі (24×24, `stroke-width="1.7"`, круглі закінчення):

```js
  bug: `<symbol id="i-bug" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="7" y="7" width="10" height="13" rx="5"/><path d="M9.5 7V5.5a2.5 2.5 0 0 1 5 0V7"/><path d="M12 11v9"/><path d="M7 12H3.5M20.5 12H17M7.5 8.5 5 6M16.5 8.5 19 6M7 16.5l-3 2M17 16.5l3 2"/></symbol>`,
  gear: `<symbol id="i-gear" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></symbol>`,
```

- [ ] **Step 3: Додати ключі i18n** поруч із `fbOpen` в обох словниках (тексти — точно ці):

| ключ | uk | en |
|---|---|---|
| `tabsNav` | `'Відкриті задачі'` | `'Open tasks'` |
| `tabOpen` | `'Відкрити задачу'` | `'Open a task'` |
| `tabClose` | `(id) => \`Закрити вкладку ${id}\`` | `(id) => \`Close tab ${id}\`` |
| `tabTitle` | `(id, title) => (title ? \`${id} · ${title}\` : id)` | те саме |
| `settings` | `'Налаштування'` | `'Settings'` |
| `logoTitle` | `'Усі задачі · ⌘K — усі дії'` | `'All tasks · ⌘K — all actions'` |
| `islandNav` | `'Інструменти'` | `'Tools'` |
| `fbIsland` | `'Баг / ідея'` | `'Bug / idea'` |
| `inspectorKey` | `'Інспектор · I'` | `'Inspector · I'` |
| `canvasHint` | `'колесо — рух · ⌘ + колесо чи щипок — масштаб · клік по кадру — відкрити'` | `'wheel — pan · ⌘ + wheel or pinch — zoom · click a frame — open'` |
| `fitAll` | `'Вмістити все'` | `'Fit all'` |
| `claudeTab_working` | `'Claude працює'` | `'Claude is working'` |
| `claudeTab_waiting` | `'Claude чекає на вас'` | `'Claude is waiting for you'` |
| `claudeTab_blocked` | `'Claude заблоковано'` | `'Claude is blocked'` |
| `claudeTab_done` | `'Claude завершив'` | `'Claude is done'` |

Змінити значення (поправка 9): `cnTitle` → `'Налаштування'`/`'Settings'`; `cnTitleIn` → `` (name) => `Налаштування · ${name}` ``/`` (name) => `Settings · ${name}` ``; `spaceConn` → `` (name) => `Налаштування простору «${name}»` ``/`` (name) => `Settings of the space “${name}”` ``.

- [ ] **Step 4: Прогін.** `node --test tests/icons.test.mjs tests/i18n-keys.test.mjs tests/i18n.test.mjs` — PASS. Якщо `i18n-keys` скаржиться на «ключ ніде не вживається» для нових ключів — це очікувано до T3/T5/T7/T8: тоді в цьому кроці НЕ додавати ще не вживані ключі, а перенести їх у ту задачу, де зʼявляється перше вживання (і записати це у звіт).

- [ ] **Step 5: Повний JS-прогін** і коміт:
```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.25.0): іконки bug/gear і тексти вкладок та острівця

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/icons.js app/i18n.js
```

---

### Task 2: Модель вкладок (`app/tabs-model.js`)

**Files:**
- Create: `app/tabs-model.js`
- Test: `tests/tabs-model.test.mjs`

- [ ] **Step 1: Написати тест** `tests/tabs-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import {
  TABS_MAX, readTabs, writeTabs, upsertTab, closeTab, pruneTabs, tabsModel,
} from "../app/tabs-model.js";

const T = (id, extra = {}) => ({ id, title: `T ${id}`, space: "sp", color: "space-2", jira: null, ...extra });

test("readTabs: сміття, чужий формат, битий JSON — порожньо, без винятку", () => {
  for (const raw of [null, "", "{", "[]", '{"v":2,"tabs":[]}', '{"v":1}', '{"v":1,"tabs":{}}']) {
    assert.deepEqual(readTabs(raw), []);
  }
});

test("readTabs: відкидає записи без id, з неіснуючим кольором, дублі; обрізає довгі рядки", () => {
  const raw = JSON.stringify({ v: 1, tabs: [
    T("A"), { id: "" }, { title: "x" }, T("A"), T("B", { color: "red;position:fixed" }), T("C", { title: "x".repeat(500) }),
  ] });
  const out = readTabs(raw);
  assert.deepEqual(out.map((x) => x.id), ["A", "B", "C"]);
  assert.equal(out[1].color, null, "невідомий колір — null, а не рядок у style");
  assert.equal(out[2].title.length, 200);
});

test("writeTabs → readTabs — те саме", () => {
  const tabs = [T("A"), T("B", { space: null, color: null, jira: "LIGA-1" })];
  assert.deepEqual(readTabs(writeTabs(tabs)), tabs);
});

test("upsertTab: нова — в кінець; наявна — оновлюється на місці", () => {
  let tabs = upsertTab([], T("A"));
  tabs = upsertTab(tabs, T("B"));
  tabs = upsertTab(tabs, T("A", { title: "Нова назва" }));
  assert.deepEqual(tabs.map((x) => x.id), ["A", "B"]);
  assert.equal(tabs[0].title, "Нова назва");
});

test("upsertTab: понад TABS_MAX випадає найстаріша, але не та, що відкривається", () => {
  let tabs = [];
  for (let i = 0; i < TABS_MAX; i += 1) tabs = upsertTab(tabs, T(`T${i}`));
  tabs = upsertTab(tabs, T("NEW"));
  assert.equal(tabs.length, TABS_MAX);
  assert.equal(tabs[0].id, "T1");
  assert.equal(tabs.at(-1).id, "NEW");
});

test("closeTab: неактивна — next null; активна — правий сусід, інакше лівий, інакше home", () => {
  const tabs = [T("A"), T("B"), T("C")];
  assert.deepEqual(closeTab(tabs, "A", "C"), { tabs: [T("B"), T("C")], next: null });
  assert.equal(closeTab(tabs, "B", "B").next, "C");
  assert.equal(closeTab(tabs, "C", "C").next, "B");
  assert.equal(closeTab([T("A")], "A", "A").next, "home");
  assert.deepEqual(closeTab(tabs, "Z", "A"), { tabs, next: null }, "невідома — без змін");
});

test("pruneTabs: прибирає лише вкладки поточного простору, яких нема в списку", () => {
  const tabs = [T("A"), T("B"), T("X", { space: "other" })];
  assert.deepEqual(pruneTabs(tabs, "sp", ["A"]).map((x) => x.id), ["A", "X"]);
  assert.deepEqual(pruneTabs([T("A", { space: null })], null, []).map((x) => x.id), []);
});

test("tabsModel: активна лише поза оверлеєм; логотип/шестерня — за сторінкою; стан Claude за id або jira", () => {
  const tabs = [T("A"), T("B", { jira: "LIGA-9" })];
  const claude = { A: { state: "working" }, "LIGA-9": { state: "waiting" } };
  const m = tabsModel({ tabs, activeId: "A", homeOpen: false, homePage: "tasks", claude });
  assert.deepEqual(m.items.map((x) => [x.id, x.active, x.claude]), [["A", true, "working"], ["B", false, "waiting"]]);
  assert.equal(m.logoOn, false); assert.equal(m.gearOn, false);
  const h = tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "tasks", claude: null });
  assert.equal(h.items[0].active, false, "на «Задачах» жодна вкладка не активна");
  assert.equal(h.logoOn, true);
  assert.equal(tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "conn" }).gearOn, true);
  assert.equal(tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "wiz" }).logoOn, false);
});

test("tabsModel: невідомий стан Claude — без крапки, а не вигадана", () => {
  const m = tabsModel({ tabs: [T("A")], activeId: "A", claude: { A: { state: "weird" } } });
  assert.equal(m.items[0].claude, null);
});
```

- [ ] **Step 2: Прогін — FAIL** (`Cannot find module …/tabs-model.js`): `node --test tests/tabs-model.test.mjs`.

- [ ] **Step 3: Реалізація** `app/tabs-model.js`:

```js
/**
 * Вкладки відкритих задач (етап А редизайну оболонки, 0.25.0). Чисті функції: жодного DOM і жодного
 * `localStorage` — читає/пише `app.js` під ключем `TABS_KEY`, тут лише формат і правила.
 *
 * Чому стан клієнтський, а не серверний: поточна задача на сервері одна (`POST /api/task-switch`), а
 * набір відкритих вкладок — звичка людини в цьому вікні; інше вікно канваса може мати свій набір.
 * Ключ вкладки — `id` задачі, бо сервер перемикає задачу саме за `id`.
 */
import { SPACE_COLORS } from "./spaces-model.js";

export const TABS_KEY = "dc-tabs";
export const TABS_MAX = 12;
const STR_MAX = 200;
const CLAUDE_STATES = ["working", "waiting", "blocked", "done"];

const str = (v) => (typeof v === "string" ? v.slice(0, STR_MAX) : "");
const strOrNull = (v) => (typeof v === "string" && v ? v.slice(0, STR_MAX) : null);

function clean(x) {
  if (!x || typeof x !== "object") return null;
  const id = str(x.id);
  if (!id) return null;
  return {
    id,
    title: str(x.title),
    space: strOrNull(x.space),
    /* Колір іде в `style` (`tabs-view.js`): лише значення з білого списку, інакше `null`. */
    color: SPACE_COLORS.includes(x.color) ? x.color : null,
    jira: strOrNull(x.jira),
  };
}

/** Рядок зі сховища → масив вкладок. Будь-яке сміття — порожньо, без винятку. */
export function readTabs(raw) {
  let data;
  try { data = JSON.parse(raw); } catch (e) { return []; }
  if (!data || data.v !== 1 || !Array.isArray(data.tabs)) return [];
  const seen = new Set();
  const out = [];
  for (const x of data.tabs) {
    const t = clean(x);
    if (!t || seen.has(t.id)) continue;
    seen.add(t.id);
    out.push(t);
  }
  return out.slice(-TABS_MAX);
}

export const writeTabs = (tabs) => JSON.stringify({ v: 1, tabs });

/** Відкрити (чи оновити) вкладку. Нова — в кінець; понад ліміт випадає найстаріша, крім щойно відкритої. */
export function upsertTab(tabs, rec) {
  const t = clean(rec);
  if (!t) return tabs;
  const i = tabs.findIndex((x) => x.id === t.id);
  if (i >= 0) return tabs.map((x, j) => (j === i ? t : x));
  const out = [...tabs, t];
  while (out.length > TABS_MAX) out.splice(out.findIndex((x) => x.id !== t.id), 1);
  return out;
}

/** Закрити вкладку. `next`: `null` — активна не змінилась; id — куди перейти; `"home"` — вкладок не лишилось. */
export function closeTab(tabs, id, activeId) {
  const i = tabs.findIndex((x) => x.id === id);
  if (i < 0) return { tabs, next: null };
  const rest = tabs.filter((x) => x.id !== id);
  if (id !== activeId) return { tabs: rest, next: null };
  const right = tabs[i + 1];
  const left = tabs[i - 1];
  return { tabs: rest, next: right ? right.id : left ? left.id : "home" };
}

/** Прибрати вкладки ПОТОЧНОГО простору, яких більше нема в його списку задач (поправка 4). */
export function pruneTabs(tabs, spaceId, liveIds) {
  const live = new Set(liveIds);
  const sp = spaceId ?? null;
  return tabs.filter((x) => x.space !== sp || live.has(x.id));
}

/** Модель рядка вкладок для `tabs-view.js`. `claude` — `{ключ: {state}}` з `/api/claude-statuses` або `null`. */
export function tabsModel({ tabs, activeId, homeOpen = false, homePage = "tasks", claude = null, update = null }) {
  const stateOf = (t) => {
    const v = claude && (claude[t.id] || (t.jira && claude[t.jira]));
    return v && CLAUDE_STATES.includes(v.state) ? v.state : null;
  };
  return {
    logoOn: !!homeOpen && homePage === "tasks",
    gearOn: !!homeOpen && homePage === "conn",
    update,
    items: tabs.map((t) => ({
      id: t.id, title: t.title, color: t.color,
      active: !homeOpen && t.id === activeId,
      claude: stateOf(t),
    })),
  };
}
```

Якщо `SPACE_COLORS` не експортується з `spaces-model.js` — додати `export` до наявної константи (не дублювати список).

- [ ] **Step 4: Прогін — PASS:** `node --test tests/tabs-model.test.mjs`. Мутація: у `closeTab` поміняти `right ? right.id : left ? left.id` на `left ? left.id : right ? right.id` → тест «активна — правий сусід» червоніє → відновити.

- [ ] **Step 5: Повний JS-прогін і коміт** (`app/tabs-model.js`, `tests/tabs-model.test.mjs`, за потреби `app/spaces-model.js`), тема `feat(0.25.0): модель вкладок відкритих задач`.

---

### Task 3: Розмітка рядка вкладок (`app/tabs-view.js`)

**Files:**
- Create: `app/tabs-view.js`
- Test: `tests/tabs-view.test.mjs`

- [ ] **Step 1: Тест** `tests/tabs-view.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { tabsHTML } from "../app/tabs-view.js";

setLang("uk");
const vm = (over = {}) => ({
  logoOn: false, gearOn: false, update: null,
  items: [
    { id: "LIGA-1", title: "Картка <b>", color: "space-2", active: true, claude: "working" },
    { id: "LIGA-2", title: "", color: null, active: false, claude: null },
  ],
  ...over,
});

test("логотип, вкладки, «+», шестерня — у цьому порядку, з іменами дій", () => {
  const h = tabsHTML(vm());
  const acts = [...h.matchAll(/data-act="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(acts, ["home", "tab", "tabclose", "tab", "tabclose", "tabnew", "settings"]);
});

test("активна вкладка — aria-current, решта — ні; назва екранована й лише в підказці", () => {
  const h = tabsHTML(vm());
  assert.match(h, /data-act="tab" data-val="LIGA-1"[^>]*aria-current="page"/);
  assert.doesNotMatch(h, /data-val="LIGA-2"[^>]*aria-current/);
  assert.ok(h.includes("Картка &lt;b&gt;"));
  assert.ok(!h.includes("<b>"));
});

test("колір простору — лише токен у style; без кольору — нейтральна крапка", () => {
  const h = tabsHTML(vm());
  assert.ok(h.includes("background:var(--space-2)"));
  assert.equal((h.match(/class="tab-dot"/g) || []).length, 2);
});

test("стан Claude — крапка з класом стану й іменем для читача", () => {
  const h = tabsHTML(vm());
  assert.match(h, /class="tab-claude tab-claude--working" role="img" aria-label="Claude працює"/);
  assert.equal((h.match(/tab-claude--/g) || []).length, 1);
});

test("хрестик має імʼя з ідентифікатором задачі", () => {
  assert.ok(tabsHTML(vm()).includes('aria-label="Закрити вкладку LIGA-2"'));
});

test("логотип на «Задачах» і шестерня на «Налаштуваннях» — aria-current", () => {
  assert.match(tabsHTML(vm({ logoOn: true })), /data-act="home"[^>]*aria-current="page"/);
  assert.match(tabsHTML(vm({ gearOn: true })), /data-act="settings"[^>]*aria-current="page"/);
});

test("пігулка оновлення — лише коли є, перед шестернею", () => {
  assert.ok(!tabsHTML(vm()).includes('data-act="update"'));
  const h = tabsHTML(vm({ update: { version: "0.26.0", restart: false } }));
  assert.ok(h.indexOf('data-act="update"') < h.indexOf('data-act="settings"'));
});
```

- [ ] **Step 2: Прогін — FAIL.**

- [ ] **Step 3: Реалізація** `app/tabs-view.js`:

```js
/**
 * Розмітка рядка вкладок (етап А, 0.25.0). Чиста: модель — `tabsModel` (`tabs-model.js`), проводка — `app.js`.
 * Не `role="tablist"`: вкладка тут веде на іншу задачу (навігація), а не перемикає панель на сторінці, тож активна
 * несе `aria-current="page"`, як логотип на «Задачах».
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { LOGO_SVG } from "./logo.js";
import { spaceColorToken } from "./spaces-model.js";
import { updatePillHTML } from "./update-view.js";

const cur = (on) => (on ? ' aria-current="page"' : "");

function tabHTML(x) {
  const dot = x.color
    ? `<span class="tab-dot" style="background:var(--${spaceColorToken(x.color)})"></span>`
    : '<span class="tab-dot"></span>';
  const claude = x.claude
    ? `<span class="tab-claude tab-claude--${x.claude}" role="img" aria-label="${esc(t(`claudeTab_${x.claude}`))}"></span>`
    : "";
  const tip = esc(t("tabTitle", x.id, x.title));
  return `<div class="tab${x.active ? " tab--on" : ""}">`
    + `<button class="tab-main" data-act="tab" data-val="${esc(x.id)}" title="${tip}"${cur(x.active)}>`
    + `${dot}<span class="tab-id">${esc(x.id)}</span>${claude}</button>`
    + `<button class="tab-x" data-act="tabclose" data-val="${esc(x.id)}" aria-label="${esc(t("tabClose", x.id))}">`
    + `${ico("x", 12)}</button></div>`;
}

export function tabsHTML(m) {
  const logo = esc(t("logoTitle"));
  const open = esc(t("tabOpen"));
  const gear = esc(t("settings"));
  return `<button class="ctl ctl--icon logo-btn${m.logoOn ? " ctl--on" : ""}" data-act="home" aria-label="${esc(t("allTasks"))}" title="${logo}" aria-keyshortcuts="Meta+K Control+K"${cur(m.logoOn)}>${LOGO_SVG}</button>`
    + `<div class="tabs-list">${m.items.map(tabHTML).join("")}</div>`
    + `<button class="ctl ctl--icon tabs-new" data-act="tabnew" aria-label="${open}" title="${open}">${ico("plus")}</button>`
    + `<span class="tabs-sp"></span>`
    + updatePillHTML(m.update)
    + `<button class="ctl ctl--icon${m.gearOn ? " ctl--on" : ""}" data-act="settings" aria-label="${gear}" title="${gear}"${cur(m.gearOn)}>${ico("gear")}</button>`;
}
```

Примітка: `aria-keyshortcuts` на логотипі прибрати, якщо `tests/shell-bar.test.mjs` чи живий `shell-palette` чекає його рівно на кнопці палітри — палітра відкривається клавішею, а логотип лише підказує про неї в `title`. Рішення записати у звіт.

- [ ] **Step 4: PASS** + мутація: прибрати `${cur(x.active)}` → тест «активна вкладка — aria-current» червоніє → відновити.

- [ ] **Step 5: Повний JS-прогін і коміт** `feat(0.25.0): розмітка рядка вкладок`.

---

### Task 4: Сервер — статуси Claude для всіх вкладок

**Files:**
- Modify: `app/serve.py` (поруч із `claude_view`, `serve.py:1193`; маршрут поруч із `'/api/claude-status'` у `do_GET`, `serve.py:6143`; `Handler._MACHINE_ROUTES`)
- Test: `tests/test_claude_view.py` (наявний — додати клас)

- [ ] **Step 1: Прочитати** `claude_view`, `_CLAUDE_STATE`, `CLAUDE_TTL`, `Handler._MACHINE_ROUTES` і як `tests/test_claude_view.py` підіймає сервер (якщо підіймає) — щоб тест маршруту повторив той самий патерн.

- [ ] **Step 2: Тест** (додати в `tests/test_claude_view.py`):

```python
class ClaudeViewsAll(unittest.TestCase):
    """`claude_views` — статуси ВСІХ задач для вкладок (0.25.0): той самий TTL і та сама мапа станів, що в `claude_view`."""

    def test_freshest_beat_per_task_key(self):
        beats = {
            's1': {'task': 'A', 'status': 'working', 'at': 100},
            's2': {'task': 'A', 'status': 'waiting', 'at': 105},
            's3': {'task': 'LIGA-9', 'status': 'working', 'at': 104},
        }
        out = serve.claude_views(beats, 106)
        self.assertEqual(set(out), {'A', 'LIGA-9'})
        self.assertEqual(out['A']['state'], serve.claude_view(beats, 106, 'A')['state'])
        self.assertEqual(out['A']['age_s'], 1)

    def test_expired_beats_are_absent(self):
        beats = {'s1': {'task': 'A', 'status': 'working', 'at': 0}}
        now = serve.CLAUDE_TTL['working'] + 1
        self.assertEqual(serve.claude_views(beats, now), {})

    def test_garbage_task_keys_are_skipped(self):
        beats = {'s1': {'task': ['x'], 'status': 'working', 'at': 1}, 's2': {'task': '', 'status': 'working', 'at': 1}}
        self.assertEqual(serve.claude_views(beats, 1), {})

    def test_only_state_and_age_leave_the_server(self):
        beats = {'s1': {'task': 'A', 'status': 'working', 'at': 1, 'note': 'секрет', 'phase': 'x'}}
        self.assertEqual(set(serve.claude_views(beats, 1)['A']), {'state', 'age_s'})
```

(Імпорт `serve` і ключі `status`, які приймає `_CLAUDE_STATE`, — як у наявних тестах цього файла; якщо в них інші значення `status`, взяти звідти.)

- [ ] **Step 3: FAIL** — `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest tests.test_claude_view -v`.

- [ ] **Step 4: Реалізація** — після `claude_view`:

```python
def claude_views(beats, now):
    """Статуси всіх задач, де серцебиття ще свіже, — для вкладок канваса (0.25.0). Чиста функція.

    Ключ — те, що шле мод (`id` чи Jira-ключ задачі); клієнт шукає вкладку за обома. Назовні йдуть лише
    `state` і `age_s`: нотатка й фаза — для острівця поточної задачі (`claude_view`), не для списку."""
    keys = {b.get('task') for b in beats.values() if isinstance(b.get('task'), str) and b.get('task')}
    out = {}
    for k in keys:
        v = claude_view(beats, now, k)
        if v.get('state'):
            out[k] = {'state': v['state'], 'age_s': v['age_s']}
    return out
```

Маршрут у `do_GET` поруч із `/api/claude-status`:

```python
        if self.path == '/api/claude-statuses':
            with CLAUDE_LOCK:
                beats = dict(CLAUDE_BEATS)
            self._send_json({'tasks': claude_views(beats, time.time())})
            return
```

і `'/api/claude-statuses'` — у кортеж `Handler._MACHINE_ROUTES` (маршрут не читає ні реєстру, ні задачі). Тест маршруту: GET без задачі й без просторів → 200 і `{"tasks": {}}` — за патерном наявних тестів `_MACHINE_ROUTES` (знайти `grep -n "_MACHINE_ROUTES" tests/*.py`).

- [ ] **Step 5: Python-пакет повністю** (сканери джерела `serve.py` теж мають лишитись зеленими: `test_spaces_serve`, `test_comments_role`, `test_liga_migrate_b`, `test_liga_migrate_c`, `test_originals_gone`, `test_publish_module`, `test_tracks`, `test_serve`):
  `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'` (у фоні, ~3–5 хв). Мутація: у `claude_views` прибрати `if v.get('state')` → `test_expired_beats_are_absent` червоніє → відновити.

- [ ] **Step 6: Коміт** `feat(0.25.0): GET /api/claude-statuses — стан Claude для всіх вкладок` (`app/serve.py`, `tests/test_claude_view.py` + файл тесту маршруту, якщо інший).

---

### Task 5: Розмітка інструментів острівця (`app/island.js`)

**Files:**
- Create: `app/island.js`
- Test: `tests/island.test.mjs`

- [ ] **Step 1: Тест** `tests/island.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { islandToolsHTML } from "../app/island.js";

setLang("uk");
const acts = (h) => [...h.matchAll(/data-act="([a-z]+)"/g)].map((m) => m[1]);

test("«Макет»: інспектор, роздільник, баг — баг останній", () => {
  const h = islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: false });
  assert.deepEqual(acts(h), ["inspector", "feedback"]);
  assert.ok(h.indexOf("isl-sep") > h.indexOf('data-act="inspector"'));
});

test("«Огляд»: інспектора нема (знімки, не живий DOM)", () => {
  assert.deepEqual(acts(islandToolsHTML({ screen: "task", mode: "overview" })), ["feedback"]);
});

test("«Задачі» / «Налаштування»: лише баг", () => {
  assert.deepEqual(acts(islandToolsHTML({ screen: "home", mode: "layout" })), ["feedback"]);
});

test("інспектор — перемикач: aria-pressed за станом; імена й підказки з клавішею", () => {
  const on = islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: true });
  assert.match(on, /data-act="inspector" aria-pressed="true" aria-label="Інспектор" title="Інспектор · I"/);
  assert.match(on, /data-act="feedback" aria-label="Баг \/ ідея" title="Баг \/ ідея"/);
  assert.match(islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: false }), /aria-pressed="false"/);
});
```

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Реалізація** `app/island.js`:

```js
/**
 * Інструменти острівця внизу робочої зони (етап А, 0.25.0): інспектор (лише «Макет» — він працює по живому DOM,
 * у «Огляді» кадри — знімки) | баг/ідея останнім. Сегмент стану Claude — окремий вузол `#claude-hud` (`role="status"`,
 * його веде `paintClaude` в `app.js`), бо жива область не сміє містити кнопок. Кнопка коментарів — етап Б.
 * Дії — ті самі `BAR_ACTIONS` (`inspector`, `feedback`): делегація з `#hud` в `app.js`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

export function islandToolsHTML({ screen = "task", mode = "layout", inspectorOn = false } = {}) {
  const parts = [];
  if (screen === "task" && mode === "layout") {
    parts.push(`<button class="isl-btn${inspectorOn ? " isl-btn--on" : ""}" data-act="inspector" aria-pressed="${inspectorOn}"`
      + ` aria-label="${esc(t("inspector"))}" title="${esc(t("inspectorKey"))}">${ico("inspect")}</button>`);
    parts.push('<span class="isl-sep" aria-hidden="true"></span>');
  }
  const fb = esc(t("fbIsland"));
  parts.push(`<button class="isl-btn" data-act="feedback" aria-label="${fb}" title="${fb}">${ico("bug")}</button>`);
  return parts.join("");
}
```

Якщо `t("inspector")` в словнику — не «Інспектор», узяти фактичне значення в тест (не змінювати ключ).

- [ ] **Step 4: PASS** + мутація: умова `mode === "layout"` → `true` → тест «Огляд» червоніє → відновити.

- [ ] **Step 5: Повний JS-прогін і коміт** `feat(0.25.0): розмітка інструментів острівця`.

---

### Task 6: Худа смуга (модель і розмітка) без перемикача задач

**Files:**
- Modify: `app/bar-model.js` (`barModel`, гілки `homeOpen` і звичайна; `zone2` без `inspector`)
- Modify: `app/shell-bar.js` (`barHTML`, видалення `paletteBtn`, `updateBtn`, `feedbackBtn`, `homeBtn`, `back` у `homeCrumbs`, `crumbTask` і всього перемикача задач; новий `crumbTitle`; `ddMore` без інспектора)
- Modify: `app/app.js` (лише те, що перестало існувати: імпорт `taskListHTML`/`taskFootHTML`, стан і обробники перемикача задач — поправка 8; `barState()` + `taskTitle`)
- Modify: `app/styles.css` (лише видалення `.dd--tasks*` і правил кнопок, яких більше нема в смузі; нових стилів тут не додавати)
- Test: `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`, `tests/legacy-golden.test.mjs` + `tests/fixtures/legacy-golden/*`, інші, що впадуть

- [ ] **Step 1: Тести моделі першими.** У `tests/bar-model.test.mjs` переписати перевірки складу `zone1` (знайти `grep -n "zone1" tests/bar-model.test.mjs`) на новий склад і додати:

```js
test("смуга задачі: зона 1 — ітерація й назва; нічого з рядка вкладок чи острівця", () => {
  const m = barModel({ ...BASE, hasIteration: true, iterLabel: "Іт.3", taskTitle: "Картка" });
  assert.deepEqual(m.zone1.map((x) => x.id), ["iter", "title"]);
  assert.equal(m.zone1[1].label, "Картка");
  const ids = [...m.zone1, ...m.zone2, ...m.zone3].map((x) => x.id);
  for (const gone of ["home", "palette", "space", "task", "update", "feedback", "inspector"]) {
    assert.ok(!ids.includes(gone), `«${gone}» переїхав зі смуги`);
  }
});

test("смуга задачі без ітерації — лише назва", () => {
  assert.deepEqual(barModel({ ...BASE, taskTitle: "Картка" }).zone1.map((x) => x.id), ["title"]);
});

test("«Задачі»/«Налаштування»: фішка простору й заголовок; майстер — лише заголовок", () => {
  const sp = { id: "s", name: "S", color: "space-1" };
  assert.deepEqual(barModel({ ...BASE, homeOpen: true, homePage: "tasks", space: sp, taskId: "A" }).zone1.map((x) => x.id), ["space", "crumb-tasks"]);
  assert.deepEqual(barModel({ ...BASE, homeOpen: true, homePage: "conn", space: sp }).zone1.map((x) => x.id), ["space", "crumb-conn"]);
  assert.deepEqual(barModel({ ...BASE, homeOpen: true, homePage: "wiz", space: sp }).zone1.map((x) => x.id), ["crumb-wiz"]);
});
```

(`BASE` — наявний базовий стан у файлі; якщо його звуть інакше — взяти наявний.) Тести, що перевіряли `home`/`palette`/`update`/`feedback`/`back`/`inspector` у смузі, — видалити або перенести суть у T2/T3/T5 (у звіті — переліком).

- [ ] **Step 2: FAIL** — `node --test tests/bar-model.test.mjs`.

- [ ] **Step 3: Модель.** У `barModel`: прибрати змінні `home`, `palette`, `updateCtl`, `feedbackCtl` (і імпорт `pillModel`, якщо більше не вживається); гілка `homeOpen`:

```js
  if (s.homeOpen) {
    if (s.homePage === "wiz") {
      return { zone1: [{ id: "crumb-wiz", tier: 0, labelKey: "wzCrumb" }], zone2: [], zone3: [], error: tasksError(s) };
    }
    const crumb = s.homePage === "conn"
      ? { id: "crumb-conn", tier: 0, labelKey: "cnTitle" }
      : { id: "crumb-tasks", tier: 0, labelKey: "tasks" };
    return { zone1: [...spaceChip, crumb], zone2: [], zone3: [], error: tasksError(s) };
  }
```

звичайна гілка: `const zone1 = [];` → (якщо `s.hasIteration`) `zone1.push({ id: "iter", … })` без змін полів → `zone1.push({ id: "title", tier: 0, label: s.taskTitle || s.taskId || "" });`. Блок `if (s.mode === "layout") zone2.push({ id: "inspector", … })` — видалити. Коментарі-обґрунтування, що описували видалені контроли, — прибрати разом із ними; наверху `barModel` один абзац: «Логотип, пігулка оновлення, перемикач задач — у рядку вкладок (`tabs-view.js`); інспектор і відгук — в острівці (`island.js`); палітра — лише ⌘K (0.25.0)».

- [ ] **Step 4: Розмітка.** У `shell-bar.js`:
  - `barHTML`: `home`-гілка — `${spaceChip(model, state, openDd)}${homeCrumbs(model)}`; задачна — `<div class="crumbs">${crumbIter(model, openDd)}${crumbTitle(model)}</div>`.
  - новий:
    ```js
    /* Назва задачі — приглушено й нерухомо: «де я» тепер каже вкладка, а перемикати задачі — теж вона. */
    function crumbTitle(model) {
      const c = model.zone1.find((x) => x.id === "title");
      if (!c) return "";
      return `<span class="crumb crumb--flat crumb--title" title="${esc(c.label)}"><span class="txt">${esc(c.label)}</span></span>`;
    }
    ```
  - `homeCrumbs` — без гілки `back` (лише крошка сторінки).
  - видалити `paletteBtn`, `updateBtn`, `feedbackBtn`, `homeBtn`, `crumbTask`, `taskListHTML`, `taskFootHTML`, `visibleTasks`, `taskCursorIndex`, `activeAttr` і імпорти, що стали непотрібні (`LOGO_SVG`, `updatePillHTML`, `feedbackBtnHTML`, `matches`, `taskKey`, `cleanTitle` — кожен перевірити `grep`).
  - `ddMore`/`inspectorBtn`: інспектора в «⋯» і в зоні 2 більше нема — `inspectorBtn` видалити, `ddMore` лишає лише ширини.
- [ ] **Step 5: `app.js` — лише прибирання й одне поле.**
  - імпорт `barHTML` без `taskListHTML`/`taskFootHTML`;
  - видалити стан і функції перемикача задач (поправка 8): `grep -n "taskQ\|taskCursor\|taskComposing\|taskPaintPending\|taskDdWasOpen\|task-q\|dd--tasks\|initialTaskCursor\|paintTaskList" app/app.js` — кожне місце або видалити, або (якщо це загальна логіка `paintBar`) спростити так, щоб гілок для `openDd === 'task'` не лишилось;
  - `BAR_ACTIONS.task` лишається (його кличе ⌘K? — перевірити `grep -n "act: \"task\"" app/shell-palette.js`; якщо ніхто — лишити, бо T7 використає його для вкладки);
  - `barState()`: додати `taskTitle: curTask ? cleanTitle(curTask) : ''` (`cleanTitle` з `tasks-model.js`; перевірити, чи бере він задачу чи рядок — `grep -n "export function cleanTitle" app/tasks-model.js`).
  - Смуга на цьому кроці ще без логотипа й палітри — це нормально до T7 (рядок вкладок).
- [ ] **Step 6: CSS** — видалити `.dd--tasks*`, `.pal-open`, `.lbl-pal`, `.fb-btn` (якщо ніде більше не вживаються — `grep`), правила `.logo-btn` ЛИШИТИ (логотип переїде в рядок вкладок). Додати `.crumb--title{color:var(--lo)}` поруч із `.crumb--flat`.
- [ ] **Step 7: Решта юніт-тестів.** `node --test tests/*.test.mjs` — виправити `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs` та інші, що перевіряли видалене (суть видаленого контролю, якщо вона жива, тепер перевіряють T2/T3/T5). Еталони ЛІГИ: `UPDATE_GOLDEN=1 node --test tests/legacy-golden.test.mjs`, потім `git diff --stat tests/fixtures/legacy-golden/` і `git diff tests/fixtures/legacy-golden/ | grep '^[-+]' | grep -o 'data-act="[a-z]*"\|data-dd="[a-z]*"' | sort | uniq -c` — у diff зникають лише `home`, `palette`, `update`, `feedback`, `task`, `back`, `inspector`; палітри ЛІГИ (`palette-*.json`) не змінюються взагалі (якщо змінились — зупинитись і описати чому). Потім `node --test tests/legacy-golden.test.mjs` без `UPDATE_GOLDEN` — PASS.
- [ ] **Step 8: Повний JS-прогін — зелений.** Коміт `feat(0.25.0): смуга задачі — лише ітерація, назва, вигляд і «куди віддаю»` з усіма зміненими шляхами (перелічити явно).

---

### Task 7: Проводка рядка вкладок і острівця

**Files:**
- Modify: `app/index.html`
- Modify: `app/app.js`
- Modify: `app/styles.css`
- Test: `tests/css-guards.test.mjs` (статичні охоронці — T9), тут — лише наявні тести зелені + ручна перевірка в браузері

- [ ] **Step 1: `index.html`.** Перед `#bar`: `<nav id="tabs" class="tabs" aria-label="Відкриті задачі"></nav>` (`aria-label` перезаписує `app.js` через `t('tabsNav')` — у HTML кирилиця дозволена, як `Завантаження…`). Замість `<div id="claude-hud" class="cv-hud" role="status"></div>`:
  ```html
  <div id="hud" class="cv-hud"><div class="island" role="group" aria-label="Інструменти">
    <div id="claude-hud" class="isl-claude" role="status"></div><div id="isl-tools" class="isl-tools"></div>
  </div></div>
  ```
  (коментар над вузлом оновити: острівець = сегмент Claude + інструменти; `role="status"` — лише на сегменті.)

- [ ] **Step 2: `app.js` — стан вкладок.** Імпорти `TABS_KEY, readTabs, writeTabs, upsertTab, closeTab, pruneTabs, tabsModel` з `./tabs-model.js`, `pillModel` з `./update-model.js` (якщо ще не імпортовано), `tabsHTML` з `./tabs-view.js`, `islandToolsHTML` з `./island.js`. Поруч з іншими `dc-*`:
  ```js
  /* Вкладки відкритих задач (0.25.0): клієнтський стан цього вікна (`tabs-model.js`, його шапка). */
  let tabs = (() => { try { return readTabs(localStorage.getItem(TABS_KEY)); } catch (e) { return []; } })();
  function saveTabs() { try { localStorage.setItem(TABS_KEY, writeTabs(tabs)); } catch (e) {} }
  /** `{ключ: {state, age_s}}` з `/api/claude-statuses` або `null` (поправка 5). */
  let claudeAll = null;
  const tabsEl = document.getElementById('tabs');
  function paintTabs() {
    tabsEl.setAttribute('aria-label', t('tabsNav'));
    tabsEl.innerHTML = tabsHTML(tabsModel({ tabs, activeId: currentTaskId, homeOpen, homePage, claude: claudeAll,
      update: pillModel(updateInfo) }));
  }
  ```
  (`updateInfo` — той самий знімок, що `barState()` віддає як `update`, `app.js:887`/`1037`.)
- [ ] **Step 3: Запамʼятати вкладку.** У `render()` одразу після `curTask = task; curTaskList = taskList; …; currentTaskId = …` (`app.js:1150-1151`):
  ```js
    rememberTab(task, taskList);
  ```
  і функція:
  ```js
  /** Відкрита задача — вкладка (поправка 3); задачі поточного простору, яких нема, — геть (поправка 4). */
  function rememberTab(task, taskList) {
    const sp = task.space || null;
    const ids = (taskList.tasks || []).map((x) => x.id);
    tabs = pruneTabs(tabs, sp?.id ?? null, ids);
    const id = taskList.current ?? currentTaskId;
    const entry = (taskList.tasks || []).find((x) => x.id === id);
    if (id) tabs = upsertTab(tabs, { id, title: entry ? cleanTitle(entry) : '', space: sp?.id ?? null, color: sp?.color ?? null, jira: entry?.jira ?? null });
    saveTabs();
    paintTabs();
  }
  ```
  (поля `task.space`, `taskList.tasks[].jira` перевірити на реальній відповіді `/api/task`/`/api/tasks` — `grep -n "'space':" app/serve.py | head`; підлаштувати імена, не вигадувати.)
- [ ] **Step 4: Дії.** У `BAR_ACTIONS`:
  ```js
    /* Вкладка (0.25.0): та сама зміна задачі, що й скрізь (`switchTask`); з «Задач» — через `homeOpenTask`, який і виходить
       з оверлею. Відмова (нема теки, збій) — причину вже показано тостом, вкладка лишається (поправка 4). */
    tab: async (val) => {
      if (!val) return;
      if (homeOpen) { if (cnDrawer && !(await dismissCnDrawer())) return; await homeOpenTask(val); return; }
      if (val === currentTaskId) return;
      if (refuseMissingTask(val)) return;
      if (await switchTask(val)) render();
    },
    tabclose: async (val) => {
      const r = closeTab(tabs, val, homeOpen ? null : currentTaskId);
      tabs = r.tabs; saveTabs(); paintTabs();
      if (r.next === 'home') { enterHome({ page: 'tasks' }); return; }
      if (r.next) await BAR_ACTIONS.tab(r.next);
    },
    tabnew: () => BAR_ACTIONS.home(),
    settings: async () => { if (homeOpen && homePage === 'wiz') { await wiz.requestExit(); return; } if (cnDrawer && !(await dismissCnDrawer())) return; enterHome({ page: 'conn' }); },
  ```
  `BAR_ACTIONS.back` — видалити (`refuseMissingTask` повертає `true`, коли відмовив, `app.js:2743`). Перевірити, що ⌘K «Підключення простору» (`act: "conn"`) і «Задачі» (`act: "home"`) працюють як раніше.
- [ ] **Step 5: Делегація.** Клік по `#tabs` і по `#hud` — той самий шлях, що в смузі: знайти делегацію смуги (`app.js:2680`, `BAR_ACTIONS[act]?.(el.dataset.val, el, ev)`) і повісити на `tabsEl` та `document.getElementById('hud')` слухач, що робить рівно це для `closest('[data-act]')` (вимкнені `el.disabled` пропускати). Середня кнопка миші (`auxclick`, `button === 1`) по вкладці — `tabclose`.
- [ ] **Step 6: Острівець.**
  ```js
  const islTools = document.getElementById('isl-tools');
  function paintIsland() {
    islTools.innerHTML = islandToolsHTML({ screen: homeOpen ? 'home' : 'task', mode: mode === 'canvas' ? 'overview' : 'layout',
      inspectorOn: !!inspectorApi()?.on });
  }
  ```
  (`inspectorApi()?.on` — той самий вираз, з якого `barState()` бере `right`, `app.js:982`.) Кликати `paintIsland()` там, де кличеться `paintBar()` (в кінці `paintBar` — один виклик), і `paintTabs()` — там само. `paintClaude` лишається, але: `claudeHud` тепер сегмент; коли `islandParts` порожній — сегмент порожній і має клас `isl-claude--off` (`display:none`), роздільник між сегментом і інструментами — CSS `.isl-claude:not(:empty)+.isl-tools::before`. `document.body.classList.toggle('claude-on', …)` лишити (ним керуються стилі тосту — див. крок 8).
- [ ] **Step 7: Опит статусів для вкладок.** У `pollClaude` (поруч, тим самим таймером):
  ```js
  async function pollClaudeAll() {
    if (!tabs.length) { if (claudeAll) { claudeAll = null; paintTabs(); } return; }
    let r; try { r = await api('/api/claude-statuses'); } catch (e) { r = null; }
    const next = r && r.tasks && typeof r.tasks === 'object' ? r.tasks : null;
    if (JSON.stringify(next) === JSON.stringify(claudeAll)) return;
    claudeAll = next; paintTabs();
  }
  ```
  `setInterval(pollClaudeAll, CLAUDE_EVERY_MS)` і перший виклик на старті поруч із `pollClaude()`; у `visibilitychange`→`visible` — теж.
- [ ] **Step 8: CSS** (`styles.css`): токени `--h-tabs:36px;--h-top:calc(var(--h-tabs) + var(--h-bar))` у `:root` поруч із `--h-bar`; заміни верхів за поправкою 1 (кожне `top:46px` і `top:var(--h-bar)` зі списку); `html.cv-clean #tabs` — у правило чистого перегляду; нові стилі:
  ```css
  /* Рядок вкладок (0.25.0): над смугою, тло --s0. Вкладки стискаються й прокручуються, рядок не ширший за вікно. */
  .tabs{position:fixed;top:0;left:0;right:0;height:var(--h-tabs);z-index:var(--z-bar);display:flex;align-items:center;
    gap:2px;padding:0 6px;background:var(--s0);border-bottom:1px solid var(--line);min-width:0}
  .tabs .logo-btn{flex:none}
  .tabs-list{display:flex;align-items:stretch;gap:2px;min-width:0;overflow-x:auto;scrollbar-width:none;height:100%}
  .tabs-list::-webkit-scrollbar{display:none}
  .tab{display:flex;align-items:center;flex:0 1 auto;min-width:72px;max-width:180px;height:100%;
    border-radius:8px 8px 0 0;color:var(--mid)}
  .tab:hover{background:var(--s1)}
  .tab--on{background:var(--s1);color:var(--hi)}
  .tab-main{display:flex;align-items:center;gap:6px;min-width:0;flex:1;height:100%;padding:0 4px 0 10px;
    background:none;border:0;color:inherit;font:inherit;font-size:12px;cursor:pointer}
  .tab-id{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tab-dot{width:8px;height:8px;border-radius:2px;flex:none;background:var(--lo)}
  .tab-claude{width:7px;height:7px;border-radius:50%;flex:none}
  .tab-claude--working{background:#3fb950}.tab-claude--waiting{background:#d29922}
  .tab-claude--blocked{background:#f85149}.tab-claude--done{background:var(--sel)}
  .tab-x{display:grid;place-items:center;flex:none;width:28px;height:28px;margin-right:2px;border:0;border-radius:6px;
    background:none;color:inherit;cursor:pointer;opacity:0}
  .tab:hover .tab-x,.tab--on .tab-x,.tab-x:focus-visible{opacity:1}
  .tab-x:hover{background:var(--s2)}
  .tabs-new{flex:none}
  .tabs-sp{flex:1}
  /* Острівець (0.25.0): сегмент Claude | інструменти; центр — по видимій робочій зоні (`.cv-hud` має ті самі left/width). */
  .island{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);display:inline-flex;align-items:center;gap:4px;
    max-width:calc(100% - 28px);padding:4px;border-radius:999px;background:rgba(26,35,30,.92);color:#fff;
    pointer-events:auto;box-shadow:0 6px 20px rgba(0,0,0,.3);transition:bottom .2s ease}
  .isl-claude:empty{display:none}
  .isl-claude .claude-island{position:static;transform:none;background:none;padding:0 10px}
  .isl-tools{display:inline-flex;align-items:center;gap:2px}
  .isl-claude:not(:empty)+.isl-tools::before{content:"";width:1px;height:20px;margin:0 4px;background:rgba(255,255,255,.18)}
  .isl-btn{display:grid;place-items:center;width:36px;height:36px;border:0;border-radius:999px;background:none;color:inherit;cursor:pointer}
  .isl-btn:hover{background:rgba(255,255,255,.1)}
  .isl-btn--on{background:rgba(255,255,255,.18)}
  .isl-btn:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
  .isl-sep{width:1px;height:20px;margin:0 4px;background:rgba(255,255,255,.18)}
  body.claude-lift .island{bottom:76px}
  body.home-open .cv-hud{left:0!important;width:100%!important}
  body.home-open .isl-claude{display:none}
  ```
  Прибрати: `.claude-island{position:absolute;…bottom…}` і `body.claude-lift .claude-island{bottom:76px}` (позиціонує тепер `.island`); `body.home-open .cv-hud{display:none!important}`; підняття тосту/плашок — замість `body.claude-on:not(.home-open)` тепер `html:not(.cv-clean) .cv-toast{bottom:64px}` і `html:not(.cv-clean) .cv-notice{bottom:106px}` (острівець видно завжди). Тексти й кольори острівця — як були у `.claude-island`. Перевірити, що `#tasks-home`/`.cn-drawer` (z-index) не накривають `#hud` (`--z-widget` 60): якщо накривають — підняти `.cv-hud` до `calc(var(--z-bar) - 1)` і записати чому.
- [ ] **Step 9: Рядок вкладок на старті й на всіх екранах:** `paintTabs()` у `paintBar()`; `enterHome`/`leaveHome` уже кличуть `paintBar` — перевірити, що логотип/шестерня підсвічуються. `leaveHome` ставить фокус на `bar.querySelector('[data-act="home"]')` — замінити на `tabsEl.querySelector('[data-act="tab"][aria-current]') ?? tabsEl.querySelector('[data-act="home"]')`. Інші `bar.querySelector('[data-act="home"|"back"|"feedback"|"inspector"|"palette"]')` у `app.js` — знайти `grep -n "data-act=\\\\\?\"\(home\|back\|feedback\|inspector\|palette\|update\)" app/app.js` і перевести на `tabsEl`/`#hud`.
- [ ] **Step 10: Перевірка в браузері** (тимчасовий сервер з фікстурою, як у живих тестах; НЕ 8765): відкрити дві задачі через «Задачі», перемкнутися вкладкою, закрити активну, перезавантажити — вкладки на місці; острівець: інспектор вмикає панель і стає `aria-pressed="true"`; баг відкриває діалог відгуку; на «Задачах» острівець — лише баг. Записати у звіт, що саме перевірено.
- [ ] **Step 11: Повний JS-прогін зелений; коміт** `feat(0.25.0): рядок вкладок і інтерактивний острівець` (`app/index.html`, `app/app.js`, `app/styles.css` + тести, що правились).

---

### Task 8: «Огляд» — колесо рухає, ⌘/Ctrl і щипок масштабують; кнопка «Вмістити все»

**Files:**
- Modify: `app/camera.js`
- Modify: `app/app.js` (обробник `wheel` на `canvasEl`, `app.js:7368`; `#cv-zoom`; `#canvas-hint`)
- Modify: `app/index.html`, `app/styles.css`
- Test: `tests/camera.test.mjs`

- [ ] **Step 1: Тест** (додати в `tests/camera.test.mjs`):

```js
import { PINCH_GAIN, panBy, wheelIntent } from "../app/camera.js";

test("wheelIntent: без модифікатора — рух на deltaX/deltaY", () => {
  assert.deepEqual(wheelIntent({ deltaX: 3, deltaY: 40, deltaMode: 0 }, 800), { kind: "pan", dx: 3, dy: 40 });
});
test("wheelIntent: ⌘ — масштаб тим самим delta; Ctrl (щипок) — підсилений", () => {
  assert.deepEqual(wheelIntent({ deltaY: 100, metaKey: true, deltaMode: 0 }, 800), { kind: "zoom", delta: 100 });
  assert.deepEqual(wheelIntent({ deltaY: 2, ctrlKey: true, deltaMode: 0 }, 800), { kind: "zoom", delta: 2 * PINCH_GAIN });
});
test("wheelIntent: рядки ×16, сторінки × висоту вьюпорта", () => {
  assert.deepEqual(wheelIntent({ deltaX: 0, deltaY: 3, deltaMode: 1 }, 800), { kind: "pan", dx: 0, dy: 48 });
  assert.deepEqual(wheelIntent({ deltaX: 0, deltaY: 1, deltaMode: 2 }, 800), { kind: "pan", dx: 0, dy: 800 });
});
test("panBy: рух камери проти напрямку прокрутки, масштаб не змінюється", () => {
  assert.deepEqual(panBy({ x: 10, y: 20, scale: 0.5 }, 3, 40), { x: 7, y: -20, scale: 0.5 });
});
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: `camera.js`:**
```js
/** Підсилення щипка трекпада: він приходить як `wheel` з `ctrlKey` і крихітним `deltaY` (1–10), а колесо — 100. */
export const PINCH_GAIN = 6;
const LINE_PX = 16;

/** Колесо в «Огляді» (0.25.0, як у Figma): ⌘/Ctrl + колесо і щипок — масштаб, просто колесо / два пальці — рух. */
export function wheelIntent(e, viewH) {
  const k = e.deltaMode === 1 ? LINE_PX : e.deltaMode === 2 ? viewH : 1;
  if (e.ctrlKey || e.metaKey) return { kind: "zoom", delta: e.deltaY * k * (e.ctrlKey && !e.metaKey ? PINCH_GAIN : 1) };
  return { kind: "pan", dx: (e.deltaX || 0) * k, dy: (e.deltaY || 0) * k };
}

/** Зсунути камеру на (dx, dy) пікселів екрана. */
export const panBy = (cam, dx, dy) => ({ x: cam.x - dx, y: cam.y - dy, scale: cam.scale });
```
- [ ] **Step 4: Обробник** у `app.js:7368+`: після винятків (панель скарг, коментатор) і `e.preventDefault(); userMoved = true;` —
```js
    const r = canvasEl.getBoundingClientRect();
    const from = camTarget || { x: cvx, y: cvy, scale: cvscale };
    const w = wheelIntent(e, r.height);
    camTo(w.kind === 'zoom'
      ? zoomAt(from, { cx: e.clientX - r.left, cy: e.clientY - r.top, delta: w.delta })
      : panBy(from, w.dx, w.dy));
```
Довгий коментар про накопичення щигликів лишити (він про `from`), додати одне речення: «рух — так само від цілі, щоб флік трекпадом не гасив сам себе». Перевірити, що `camTo` для руху не запускає переліт довше, ніж треба (якщо рух відчутно «пливе» — для `pan` ставити камеру одразу тим самим шляхом, що тягнення мишею; знайти, як рухає `pointermove`-панорама, і використати те саме).
- [ ] **Step 5: `#cv-zoom` → кнопка** (`index.html`: `<button id="cv-zoom" class="cv-zoom" type="button">100%</button>`); в `app.js` при старті: `zoomEl.title = t('fitAll'); zoomEl.setAttribute('aria-label', t('fitAll'));` і `zoomEl.addEventListener('click', () => { userMoved = false; fitAll(); });`. CSS: `.cv-zoom` — `cursor:pointer;border:0;font:inherit` + `:hover`/`:focus-visible` як у `.ctl`; висота ≥ 28px.
- [ ] **Step 6: Підказка:** `index.html` — `#canvas-hint` порожній (текст ставить `app.js`: `document.getElementById('canvas-hint').textContent = t('canvasHint')` при старті й у `switchLang`). CSS: `.cv-canvas-hint{bottom:66px}`; прибрати `body.claude-on #canvas-hint{visibility:hidden}`; додати `body.claude-lift #canvas-hint{visibility:hidden}`.
- [ ] **Step 7: PASS** (`node --test tests/camera.test.mjs`) + мутація: у `wheelIntent` прибрати `|| e.metaKey` → тест «⌘ — масштаб» червоніє → відновити. Живий `tests/live/canvas.test.mjs` (у ньому колесо й `#cv-zoom`) — прогнати, виправити очікування «колесо = зум» на «⌘ + колесо = зум» і додати перевірку «колесо без модифікатора не змінює `#cv-zoom`».
- [ ] **Step 8: Повний JS-прогін; коміт** `feat(0.25.0): «Огляд» — колесо рухає, ⌘ і щипок масштабують; «Вмістити все»`.

---

### Task 9: Охоронці макета й живий сценарій вкладок

**Files:**
- Modify: `tests/css-guards.test.mjs`
- Create: `tests/live/tabs.test.mjs`

- [ ] **Step 1: Статичні охоронці** (у `css-guards.test.mjs`, за наявним патерном читання `styles.css`):
  - жоден селектор не має `top:46px` (висота смуги — лише токенами);
  - `.tabs` має `height:var(--h-tabs)`, `.tabs-list` — `overflow-x:auto` і `min-width:0` (рядок не розпирає вікно);
  - `.isl-btn` — `width` і `height` ≥ 28px; `.tab-x` — ≥ 28px; `.cv-zoom` — `min-height` або `height` ≥ 28px;
  - `.cv-hud` має `pointer-events:none`, а `.island` — `pointer-events:auto` (клік крізь порожню смужку йде в макет).
  Кожен — мутацією (прибрати рядок у CSS → червоніє → відновити).
- [ ] **Step 2: Живий** `tests/live/tabs.test.mjs` (фікстура з ≥ 2 задачами — взяти з `tests/live/tasks-home.test.mjs`, як він відкриває задачу з екрана «Задачі»):
  1. Старт → у `#tabs` одна вкладка поточної задачі, `aria-current="page"`.
  2. Логотип → «Задачі» → відкрити другу задачу карткою → дві вкладки, активна — друга.
  3. Клік по першій вкладці → задача перемкнулась (у смузі назва першої; `aria-current` на першій).
  4. Хрестик активної → активною стала сусідня; хрестик останньої → екран «Задачі» (`#tasks-home` видно).
  5. Відкрити задачу, `page.reload()` → вкладки ті самі.
  6. На 1024×700: `document.documentElement.scrollWidth <= innerWidth`; `#tabs` і `#bar` не ширші за вікно; права межа `.island` < лівої межі `#insp-panel`, коли інспектор відкрито.
  7. Острівець: «Макет» — кнопки `inspector` і `feedback`; «Огляд» — лише `feedback`; на «Задачах» — лише `feedback`.
- [ ] **Step 3: Прогнати новий живий файл; коміт** `test(0.25.0): охоронці макета і живий сценарій вкладок`.

---

### Task 10: Живі тести — переїзд селекторів

**Files:**
- Modify: `tests/live/*.test.mjs` (перелік знаходить grep нижче)

- [ ] **Step 1: Механічні заміни** (лише ці, через `sed -i ''` або `Edit`):
  - `#bar [data-act="home"]` → `#tabs [data-act="home"]`
  - `#bar [data-act="inspector"]` → `#hud [data-act="inspector"]`
  - `#bar [data-act="feedback"]` → `#hud [data-act="feedback"]`
- [ ] **Step 2: Ручні правки** — кожен файл з `grep -ln 'data-act="back"\|data-act=\\"back\\"\|dd="task"\|task-q\|act="palette"\|\.space-chip\|\.dd \[data-act="inspector"\]\|claude-hud\|canvas-hint' tests/live/*.mjs`:
  - «Назад до задачі» (`back`) → клік по вкладці задачі `#tabs [data-act="tab"][data-val="<id>"]`;
  - перемикач задач (`dd="task"`, `#task-q`): `tests/live/task-dropdown.test.mjs` і `tests/live/shell-typing.test.mjs` — перевіряли саме видалений контрол → видалити файли (кожен рядком у звіті: що перевіряли й чому більше нема що перевіряти — пошук задач живе на екрані «Задачі», його тест `tasks-home`); в інших файлах перемикання задачі — через «Задачі» → картка або вкладку;
  - кнопка палітри (`act="palette"`) → `page.keyboard.press('Meta+k')` (на Linux CI — `Control+k`; узяти той самий хелпер, що вже є в `shell-palette.test.mjs`);
  - `#bar .space-chip` на екрані ЗАДАЧІ → спершу `#tabs [data-act="home"]`, далі фішка на смузі «Задач» (вона там лишилась);
  - `.dd [data-act="inspector"]` (ярус «⋯») → `#hud [data-act="inspector"]` (інспектор більше не ховається в «⋯»);
  - `claude-hud`: селектори острівця (`#claude-hud .claude-island`) лишаються робочими; перевірки «острівця нема на «Задачах»» → «на «Задачах» сегмента Claude нема, острівець є»;
  - `canvas-hint`: текст — `t('canvasHint')`; перевірки «підказка схована, коли видно Claude» → прибрати.
- [ ] **Step 3: Прогнати КОЖЕН змінений файл послідовно**, далі — весь живий набір послідовно у фоні:
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/*.test.mjs` (довго; 3 відомі падіння з 0.23 — `live-dashboard-role #6`, `live-inspector-ds #2/#4` — звірити з `646f7b2`, а не лагодити тут).
- [ ] **Step 4: Коміт** `test(0.25.0): живі тести — селектори рядка вкладок і острівця` (усі змінені/видалені шляхи явно; видалення — `git rm -- <шлях>` і цей шлях у переліку коміту).

---

### Task 11: Реліз-документи 0.25.0

**Files:**
- Modify: `CHANGELOG.md` (новий розділ `## [0.25.0] — 13.11.2026` у форматі файла, англійською, як попередні)
- Modify: `package.json` (`"version": "0.25.0"`)
- Modify: `README.md` (лише якщо там описано смугу/палітру-кнопку/колесо «Огляду» — виправити описи, не дописувати нових розділів)

- [ ] **Step 1: CHANGELOG** — «Added»: tabs row (open tasks, space colour, Claude state per tab, `GET /api/claude-statuses`), interactive island (inspector, bug/idea), «Fit all» zoom button; «Changed»: task bar slimmed (iteration + title, view, Figma/Git/Publish), Connections → Settings (gear), Overview wheel = pan / ⌘·Ctrl·pinch = zoom, gesture hint translated; «Removed»: task switcher dropdown in the bar (tabs + Tasks screen replace it), palette button (⌘K stays), «Back to task» button.
- [ ] **Step 2: Перевірка версії** — `grep -rn "0\.24\.0" package.json app/*.py app/*.js | grep -v CHANGELOG` — якщо версію ще десь пінять (тести `test_canvas_app.py`, `pwa`), оновити там же.
- [ ] **Step 3: Повний прогін** — JS, Python ×3 (у фоні), живі вже пройшли в T10. Коміт `docs(0.25.0): CHANGELOG 0.25.0, версія`.

---

## Після T11 (контролер)

1. Один ревʼюер (Sonnet, англійською, на архівній копії, без `cd` у репо) — на весь діф `646f7b2..HEAD` проти спеки й поправок: доступність (імена, `aria-current`, `aria-pressed`, фокус після закриття вкладки), охоронці, що не можуть впасти, залишки перемикача задач, витоки приватних даних.
2. Перевірка проти живого — після релізу (живий канвас оновлюється лише ff `main` + тег, кнопкою оновлення): відкрити дві реальні задачі, перемкнутися, закрити, перезавантажити вкладку; острівець і статус Claude від мода (точка на вкладці, де Claude працює); «Огляд» колесом, ⌘ + колесом і щипком; бейдж Dock не змінився.
3. Реліз: ff `main`, анотований тег `v0.25.0` (neodisa), push після `git remote get-url origin`; оновлення живого канвасу кнопкою оновлення (як 0.23.2).

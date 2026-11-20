# Етап «Відповіді в коментарях» (0.34.0) — план

> **Для виконавців:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (контролер) / superpowers:test-driven-development
> (виконавець). Кроки з чекбоксами (`- [ ]`).

**Мета:** відповіді (один рівень) на коментарі в Deai і в публічному превʼю, агент читає й відповідає, нові відповіді
позначаються в Deai; три баги коментатора (знімок мовчки зникає, маршрут береться при збереженні, «На іншій сторінці» в
превʼю); форма над макетом — у токенах і мові оболонки.

**Спека:** `docs/superpowers/specs/2026-11-20-comment-replies-design.md` — джерело правди для поведінки й текстів.

**Архітектура:**
- **Відповідь** — поле `replies` коментаря. Його носять:
  - коментатор (`commenter/src/comment-layer.js`);
  - обидва сховища: локальне (внутрішньо в піні), `supabase-comments` (окрема таблиця `comment_replies`);
  - комбіноване `dual-store.js`;
  - сервер (`agent_pin`, роль `comments`).
- **Панелі** Deai й превʼю читають відповіді зі знімка коментатора й пишуть через нові методи хоста
  (`reply/editReply/removeReply`).
- **Нове в коментаторі** — лише за опціями хоста; без них — як було.

**Стек:** vanilla JS (ES-модулі й класичні скрипти), коментатор — esbuild 0.25.12 (детермінована збірка), Python 3 stdlib,
`node --test`, `unittest`, Playwright (живі).

**Рівень строгості:** повний. Окреме ревʼю — на кожну задачу, що чіпає коментатор (T1–T4) чи схему/сховища Supabase (T6).

---

## Розвідка (для виконавців)

### Коментатор `commenter/src/comment-layer.js`

- **Ініціалізація:** `init` :531, `_hostOpts` :545, `_buildUI` :602 (`STYLE` :202 іде в `<style>` :607, `.root` :608).
- **Форми:**
  - `_openCompose(el, sel, extra)` :1213 — збереження :1239 кличе `_addComment(el, text, sel, extra, aud)`;
  - текст — `_upHandler` :787 → `_openCompose(anchor, txt, {mode:'text'})`;
  - область — `_areaUp` :813 → `_openCompose(el, '', {mode:'area', rect})`;
  - «Кілька» — `_toggleMulti` :1061, `_clearMulti` :1067, `_finishMulti` :1074;
  - полотно — `_openCanvasCompose` :1143, `_addCanvasComment` :1171.
- **Створення й знімок:** `_addComment` :1244 (читає `location` :1249–1250), `_finishComment` :1286, `_captureShot` :1303,
  `SHOT_MAX_NODES`/`SHOT_MAX_SVG`/`loadShotLib` :2063–2077 (відхилений проміс кешується назавжди).
- **Злиття й запис:** `_onExternalChange` :579, `_persist` :1652, `stripRuntime` :1945.
- **Скоуп і знімок для хоста:** `_inScope` :1690 (лише ітерація, сторінку не розрізняє), `_relocate` :1359,
  `snapshot()` :1904 (`where` за `meta.route` :1908).
- **Власна панель:** `_card` :1580 (звичайна картка :1621).
- **Методи:** `editComment` :1928, `setMeta` :1877, `_emit` :1889, `removeComment(id, opts)` :1755, `getUser` :51,
  `nowStamp` :2047, `genId` :2079, `findMatch`/`MATCH_THRESHOLD` (`anchor.js` :77–78).
- **Тести коментатора:**
  - `commenter/test/*.test.mjs` — без DOM: вирізають функції регекспом (2 пробіли — функція верхнього рівня, 4 — метод).
    **Не міняй форму й відступи** `getUser`, `removeComment(id, opts)`, `ctxLine`, `composeTop`, `isTypingField`/`keyOrigin`,
    `BACKUP_PREFIX`;
  - поведінку перевіряють живі `tests/live/commenter-host.test.mjs` / `commenter-shot.test.mjs`: `page.setContent` + бандл,
    `html2canvas` — шпигун.
- **Збірка:** `cd commenter && npm ci && npm run build` (пише `app/vendor/comment-layer.min.js`, `anchor.min.js`,
  `commenter/build-stamp.json`); охоронець — `tests/commenter-stamp.test.mjs`.

### Сховища

- **`app/vendor/local-adapter.js`:**
  - `clean()` :9 — білий список (без `replies`!);
  - `mergePin(s, w, m)` :41 — по полях, `STATUS_GROUP`; `mergeMeta` :53;
  - злиття в `save` → `mergeThenWrite` :115 проти свіжого GET.
- **`app/vendor/dual-store.js`:**
  - `FIELDS` :15 — детектор змін, без `replies` зміна не помічається;
  - `teamDown` :50, `save` :89–106, `remove` :111, `uploadShot` :145.
- **`app/modules/supabase-comments/adapter.js`:**
  - відображення: `rowToComment` :54 (тест вимагає рівно 11 полів, `tests/supabase-comments-adapter.test.mjs:242` —
    **не розширювати**), `commentToRow` :63;
  - стан: `create` :133, `written`, `fetchAll` :213;
  - realtime: `relevant` :242, канал :250, `ownEcho` :257;
  - знімок сесії: `snapStorage` / `readSnap` / `writeSnap` :90–116;
  - запис і видалення: `upsert` :295, `doSave` :354, `store` :395 (`remove` — `delete().in('id').eq('project_id')`).
- **Тести сховищ:**
  - `tests/local-adapter.test.mjs` (`fakeServer`);
  - `tests/dual-store.test.mjs` (`vm`, `fake(rows)`);
  - `tests/supabase-comments-adapter.test.mjs` — фейковий supabase-js `world(opts)`: `failSelect`, `failUpserts`, ручні
    таймери `runTimers`/`drive`;
  - `tests/memo-adapter.test.mjs`.
- **Фікстура `tests/fixtures/modules/memo-comments/`:** зберігає коментар цілим JSON; живий сервіс — `tests/live/_memo.mjs`.

### Сервер `app/modules/supabase-comments/server.py`

- `TABLE_PATH` :66, `NO_SCHEMA_CODES` :68, `_request(ctx, method, query, *, timeout, body, prefer, limit)` :222,
  `_classify` :273, `_row_to_comment` :294.
- Ролі: `list` :325, `recent` :345, `resolve` :364, `check` :387.
- Тести — `tests/test_supabase_comments.py`:
  - `FakeSupabase` :119 — лише `/comments`, POST/DELETE → 405, `no_table`, `override`;
  - `SeamMixin` / `Tripwire`.

### Оболонка Deai

- **`app/comments-model.js`:** `commentSections` :35 (`isFresh` — лише командні), `openCount` :50, `filterCounts` :56,
  `matchQuery` :13.
- **`app/comments-view.js`:** `cardHTML` :33 (рядок дій :66–91, права `st.actions` :84), `commentsPanelHTML` :107.
- **`app/app.js` — стан і панель:**
  - стан коментарів :132–154;
  - `paintComments` :1913 (збереження фокуса й чернетки :1920–1937);
  - `myName` :1946, `readTeamDown` :1951.
- **`app/app.js` — «нові»:**
  - `cmtNewsUpdate` :1958, `newsToast` :1998, `setCommentsOpen` :2008;
  - `onCommentsEvent` :2091, слухач `message` :2098;
  - `pollTabNews` :6933.
- **`app/app.js` — дії й поля:**
  - `BAR_ACTIONS` `cmt*` :2335–2361 — кожна дія в окремому рядку, що починається рівно з двох пробілів
    (`tests/comments-wiring.test.mjs`);
  - `input`/`keydown` панелі :7602–7612.
- **`app/comment-news.js`:** `teamOf`, `isNew`, `baseline`, `markSeen`, `arrived`, `newsByPage`, `countNew`.
- **Острівець:** `app/island.js:15–20` (`isl-count--new`).
- **`app/i18n.js`:**
  - `plural(n, one, few, many)` :43 — лише uk; en — тернарником;
  - `UK` :52, коментарі :1371–1434; `EN` :1474, коментарі :2598–2661;
  - `t()` кидає на відсутній ключ.

### Превʼю

- **`app/ext-comments.js`:**
  - `PREVIEW_ACTIONS` :36, `CMT_ACTS` :38 (недосяжне без запису тут), `CMT_EVENTS` :34;
  - `ownStore` :70;
  - `createExtComments` :124: `paint` :148, `ensureName` :216, дії :249–283, `onMessage` :316.
- **`app/ext-shell.js`:** `EXT_ACTIONS` для `CMT_ACTS` :1103.
- **Обмеження:** превʼю везе `ext-comments.js` як є й імпортує лише чисті модулі — **без `comment-news.js`**.

### Сервер і агент

- **`app/serve.py` — сніпети коментатора:**
  - `HOST_ARG` :2992, `PREVIEW_HOST_ARG` :3017, `host_arg` :3043;
  - сніпети: `LOCAL_COMMENT_SNIPPET` :3052 (без `host` — байт-у-байт фікстури `tests/fixtures/comments-role/`),
    `DUAL_COMMENT_SNIPPET` :3215;
  - вставка коментатора в превʼю :4706.
- **`app/serve.py` — агент:**
  - `agent_pin` :3503 (білий список), `agent_news` :3566, `for_agent` :3592;
  - `ProjectComments` :3602: `_module`, `recent` — зразок необовʼязкової функції.
- **`app/serve.py` — маршрути:**
  - `_comments` :7211, `_comment_news` :7254;
  - `_local_file` :7279, `_local_comments_post` :7292 (без злиття, лише прибирає `_el/_pending/_aud`).
- **`app/deai_modules.py`:** `ROLE_OPTIONAL_FUNCTIONS` :108.
- **`bin/inbox.py`:**
  - `show_pins` :272, `cmd_list` :366;
  - `find_target` :473, `write_local_resolved` :512, `cmd_resolve` :550;
  - `EPILOG` :682, `build_parser` :694.
  - Тести — `tests/test_inbox.py`: `FakeNet`, `sbconf.patch_open`, `InboxCase` :98, `run_main`.
- **Довідка:** `app/templates/agents.md` :43–55 (розділ Comments); `docs/modules/comments.md` (таблиці :59–69, :97–103).

---

## Спільні правила (для КОЖНОЇ задачі)

- **Тека й гілка:** `/Users/sergeyarkhipov/Liga Tools/deai-canvas/.claude/worktrees/reverent-sutherland-266302`, гілка
  `neodis/reverent-sutherland-266302`. Інших гілок і живого дерева `~/Liga Tools/deai-canvas` не чіпати.
- **Коміт:**
  - нові файли — `git add -- <файли>`;
  - потім `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`;
  - ніколи `git add -A`, `--amend`, `stash`, `reset`, `rebase`, `checkout` інших гілок;
  - ніколи не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і
    `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`.
- **Межі тестів:**
  - не торкаються портів 8765/4317, `~/Liga Tools/deai-canvas`, справжніх `~/.deai`, `~/deai-published`, `~/deai-work`,
    `~/.gitconfig`, `tasks.json`, `~/.claude/pipeline-feedback`, Teams, справжнього Supabase (лише фейки), Jira, Vercel;
  - `python3 -B`; без мережевих встановлень (виняток — `npm ci` у `commenter/` з наявного lock-файла).
- **Живі тести:**
  - по одному файлу: `node --test --import ./tests/live/_env.mjs tests/live/<f>.test.mjs`;
  - не паралельно з Python;
  - перед прогоном — замок `mkdir /private/tmp/deai-live.lock` (зайнято — чекати й повторити), `rmdir` одразу після;
    замок, старший за 60 хв, можна зняти.
- **Процеси:** лише за PID, ніколи `pkill`/`killall`/`while pgrep -f`; без `rm -rf`.
- **Мутації:** кожна НОВА перевірка доводиться мутацією (зламати → червоне → повернути → зелене) — у звіт.
- **Тексти:**
  - обидві мови в `app/i18n.js`; кирилиці поза `i18n.js` у JS оболонки нема (`tests/i18n-literals.test.mjs`);
  - коментатор лишається англомовним за замовчуванням — переклад дає хост (`host.labels`);
  - жодних підписів, яких нема в спеці.
- **CSS:** `tests/css-guards.test.mjs` — повні літерали класів, кольори лише токенами.
- **Коментатор:**
  - лише опційні, зворотно сумісні зміни API;
  - без нових опцій — та сама розмітка й стилі (`STYLE` не змінювати: нові стилі — окремим `<style>` лише за опцією);
  - після кожної зміни `commenter/src` — збірка й `tests/commenter-stamp.test.mjs`.
- **Звіт виконавця (англійською):** що зроблено, файли, команди й їх вихід (хвіст), мутації, відкриті питання.

---

### Task 1: Коментатор — контекст у момент вибору цілі (баг 2) і сторінка за тегом у режимі хоста (баг 3)

**Файли:**
- `commenter/src/comment-layer.js`;
- збірка: `app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`, `commenter/build-stamp.json`;
- новий `commenter/test/page-of.test.mjs`;
- новий `tests/live/commenter-context.test.mjs`;
- новий золотий `tests/live/commenter-golden.test.mjs` + еталони `tests/fixtures/commenter-golden/*.html`.

- [ ] **Золотий еталон — ПЕРШИМ, до будь-якої зміни `commenter/src`** (спека §7):
  - `tests/live/commenter-golden.test.mjs`: `page.setContent` з поточним бандлом `app/vendor/comment-layer.min.js`,
    в'юпорт 1280×800, шпигун `html2canvas`, сховище в памʼяті з трьома фіксованими пінами (відкритий з `meta.route`
    поточної сторінки, закритий, пін іншої сторінки), `init` БЕЗ `host`;
  - стани:
    1. одразу після `init`;
    2. відкрита власна панель зі списком;
    3. режим «Елемент», клік по елементу — відкрита форма;
    4. режим «Кілька», два вибрані — форма «Кілька»;
  - для кожного — `shadowRoot.innerHTML` з нормалізацією лише нестабільного (id піна з `genId`, якщо зʼявляється, — на
    `ID`) і порівняння з `tests/fixtures/commenter-golden/<стан>.html`;
  - еталони пише той самий файл за `DC_GOLDEN_WRITE=1` (запис — один раз, ДО змін; закомітити разом із тестом); без
    змінної — лише порівнює;
  - мутація: змінити один символ у `STYLE` у збірці → червоний; повернути.
  - Коміт окремим комітом: `test(0.34): золотий еталон тіньового DOM коментатора без нових опцій`.
- [ ] **Функція `pageOf(v)`** — верхнього рівня, 2 пробіли відступу, самодостатня (для вирізання регекспом): сторінка з
  тегу версії, `'1/holovna'` → `'holovna'`, `'3'` → `''`, `null` → `''`.
- [ ] **Метод `_captureAt(el, aud)`** — контекст, знятий у момент вибору цілі:
  - повертає `{ url, route, version, viewport, fp, outerHTML, text, where }`:
    - `url` = `location.href`;
    - `route` = `location.pathname + location.hash`;
    - `version` = `this.appVersion`;
    - `viewport` = `{w: innerWidth, h: innerHeight}`;
    - `fp` = `fingerprint(el, this.target)`;
    - `outerHTML`, `text` — з `el`;
    - `where` = `captureContext(el, this.target, { heading: true })` у `try`;
  - заголовок розділу (`heading`) прибирається вже в `_addComment`, якщо аудиторія не приватна (правило TD-36 не
    змінюється).
- [ ] **Зняття контексту за режимами:**
  - **`_openCompose`** знімає `at = this._captureAt(el)` першим рядком і передає `Object.assign({}, extra, { at })` у
    `_addComment`. Поле `extra.mode` лишається як було: для «Елемента» `mode` не пишеться.
  - **«Кілька»:**
    - `_toggleMulti` знімає `this._multiAt`, коли вибір із порожнього стає непорожнім, і перезнімає його, коли
      знято перший елемент (`_multiSel[0]` змінився);
    - `_clearMulti` скидає `_multiAt`;
    - `_finishMulti` передає `at: this._multiAt` (або свіжий `_captureAt(els[0])`, якщо його нема).
- [ ] **`_addComment` бере контекст з `extra.at`.**
  - Береться все: `url`, `route`, `version`, `viewport`, `outerHTML`, `text` (у `buildContextBundle`), `fp`, `meta.ctx`
    (з `heading`, лише коли `this.appLocal || this._audPrivate(aud)`).
  - Без `extra.at` — як зараз: інші виклики сумісні.
  - Полотно (`_addCanvasComment`) не змінюється.
- [ ] **Знімок:** якщо `shotTarget` уже не в документі (`!shotTarget.isConnected`) і поточний маршрут дорівнює
  `at.route`, ціль шукається наново `findMatch(at.fp, this.target)`; береться за `score ≥ MATCH_THRESHOLD`. Інакше —
  поведінка T2 (поки що знімка просто нема).
- [ ] **Метод `_otherPage(c)`:**
  - `true` лише коли разом: `this._hostOpts`, `!this.anchors`, `this.appVersion != null`,
    `c.meta && c.meta.version != null`, `pageOf(c.meta.version) !== pageOf(this.appVersion)`;
  - інакше `false`.
- [ ] **Де «На іншій сторінці»:**
  - **`snapshot().where`:**
    - у режимі хоста (`this._hostOpts && !this.anchors`): `_otherPage(c)` → `'elsewhere'`;
    - пін з `meta.version` тієї самої сторінки — маршрут НЕ порівнюється;
    - пін без `meta.version` — стара перевірка маршрутом;
    - без хоста — без змін.
  - **`_relocate`:** пін, для якого `_otherPage(c)`, не якориться (`c._el = null`) — у Deai й превʼю пін з іншої
    сторінки не малюється на схожому елементі цієї.
- [ ] **Тести:**
  - **`commenter/test/page-of.test.mjs`** — вирізати `pageOf` регекспом (як `host-user.test.mjs`): `'1/a'`, `'12/b/c'`
    (→ `'b/c'`), `'3'`, `null`, `undefined`, число `3`.
  - **`tests/live/commenter-context.test.mjs`** — `page.setContent` з бандлом, як у `commenter-host.test.mjs`;
    шпигун `html2canvas`; сховище в памʼяті:
    1. З `host`, режим «Елемент»:
       - клік по елементу → форма;
       - `history.pushState({}, "", "/other#x")` → текст → «Comment»;
       - у піні `meta.route` / `meta.url` — моменту кліку, `fp` — як `fingerprint` у момент кліку (порахувати в тесті до
         `pushState`).
    2. Те саме без `host` (виправлення діє скрізь).
    3. «Текст»: виділення → `pushState` → збереження → маршрут кліку.
    4. «Область»: протяг мишею → `pushState` → збереження → маршрут кліку.
    5. «Кілька»:
       - вибір першого → `pushState` → вибір другого → збереження → маршрут першого вибору;
       - зняття першого вибору перезнімає контекст.
    6. Знімок, елемент перемальовано: клік → елемент видалено й вставлено ідентичний клон → збереження → `html2canvas`
       отримав приєднаний клон.
    7. Сторінка за тегом, з `host`, `version: "1/holovna"`:
       - пін `meta.version: "1/poshuk"` → `snapshot().where === "elsewhere"`, у `.pins` немає його піна;
       - пін `meta.version: "1/holovna"`, `meta.route: "/commented"`, а сторінка має інший шлях → `where !== "elsewhere"`;
       - пін без `meta.version`, з іншим маршрутом → `"elsewhere"`.
    8. Без `host`: пін з іншим `meta.route` — `elsewhere` у власній панелі, як було (рядок `.otherpage` у картці).
- [ ] **Мутації** — у звіт:
  - `_openCompose` не передає `at` → 1 червоний;
  - прибрати перезняття в `_toggleMulti` → 5 червоний;
  - прибрати гілку хоста в `where` → 7 червоний;
  - прибрати `_otherPage` у `_relocate` → 7 (пін намальовано) червоний;
  - прибрати повторний пошук цілі → 6 червоний.
- [ ] **Прогін:**
  - `cd commenter && npm ci && npm run build`;
  - `node --test tests/commenter-stamp.test.mjs commenter/test/*.test.mjs`;
  - `node --test tests/*.test.mjs`;
  - живі по одному: `commenter-context`, `commenter-host`, `commenter-shot`, `comments`, `comments-team`, `comments-panel`,
    `preview-comments`, `pin-where`, `offscreen-pin`, `overview-comments`.
- [ ] **Коміт:** `fix(0.34): коментатор — контекст піна в момент вибору цілі; сторінка за тегом у режимі хоста`.

### Task 2: Коментатор — знімок ніколи не зникає мовчки (баг 1)

**Файли:**
- `commenter/src/comment-layer.js`, `commenter/src/shot-scope.js`;
- збірка;
- `tests/live/commenter-shot.test.mjs`, новий `tests/live/commenter-heavy.test.mjs`;
- юніт у `commenter/test/` за потреби.

- [ ] **`meta.shotMiss` — код причини**, якщо після спроби знімка в піні нема ні `meta.shot`, ні `meta.shotUrl`.
  - Коди:
    - `too-big` — понад ліміт після обрізки SVG, див. нижче;
    - `no-lib` — `html2canvas` не завантажився;
    - `timeout` — рендер не вклався в 8 с;
    - `render` — виняток `html2canvas`, `toDataURL`, `drawImage`;
    - `detached` — цілі нема в документі навіть після пошуку з T1;
    - `upload` — `uploadShot` є, але повернув `null`, не встиг чи кинув; інлайн-знімок, як і зараз, у сховище не їде
      (`stripRuntime`/адаптер).
  - Так само в `_finishCanvasComment`: `anchors.shot` повернув `null` чи не встиг → `render`/`timeout`; завантаження —
    `upload`.
  - Знімок є → `shotMiss` не пишеться.
  - `_captureShot` повертає `{ url }` чи `{ miss: '<код>' }` (внутрішній контракт; зовнішнього API нема).
- [ ] **Бібліотека й таймаути:**
  - завантаження бібліотеки — окремий таймаут 8 с; рендер — свої 8 с;
  - `loadShotLib` після відмови скидає кешований проміс: наступний пін пробує знову.
- [ ] **Обрізка SVG замість відмови:**
  - лічимо корені `svg` у цілі й їх нащадків;
  - поки сума нащадків ≤ `SHOT_MAX_SVG` — як зараз; понад бюджет — `shotScope` отримує набір «порожніх» коренів,
    `ignoreElements` повертає `true` для НАЩАДКІВ цих коренів (сам `svg` клонується й тримає свій розмір);
  - ліміт вузлів `SHOT_MAX_NODES` рахується після обрізки (нащадки порожніх коренів не входять); понад нього — `too-big`;
  - числа `1500`/`300` не змінюються.
- [ ] **Завантаження:** одна повторна спроба `uploadShot` (через 500 мс), потім `upload`.
- [ ] **Опція `shotLib`** (необовʼязкова, рядок-адреса копії `html2canvas` для хостів із CSP): `loadShotLib` бере її
  замість адреси CDN; без опції — CDN, як зараз. Лише `http(s):` чи відносна адреса; інше ігнорується.
- [ ] **Межа стенда.** Справжнього `html2canvas` офлайн нема (ні в `node_modules`, ні в кеші npm), тож стенд міряє,
  ЯКА гілка гасить знімок (вузли, SVG, відʼєднання, бібліотека, завантаження), а не час рендеру. Числа лімітів не
  змінюються. Час рендеру й частку 19/39 — за агрегатами ревʼю з дозволу власника чи переглядом на канвасі власника
  (лише перегляд) — у звіт контролера, не в цю задачу.
- [ ] **Тести:**
  - **`commenter-shot.test.mjs`:** дві наявні перевірки «знімка нема» тепер чекають `meta.shotMiss === "too-big"`
    (> 1500 вузлів) і обрізку SVG — `html2canvas` ВИКЛИКАНО, а `ignoreElements` повертає `true` для `path` усередині
    порожнього `svg` і `false` для самого `svg`. Свідома заміна перевірки — у звіт.
  - **Новий `commenter-heavy.test.mjs`** («важка SPA»; згенерована сторінка: 40 карток × 10 інлайн-SVG-іконок по 4
    вузли, таблиця 30×8):
    1. картка з іконками понад бюджет → знімок є (шпигун викликаний), `shotMiss` нема;
    2. ціль > 1500 вузлів після обрізки → `shotMiss: "too-big"`, `html2canvas` не викликано;
    3. CDN недоступний (`html2canvas` не визначено, скрипт CDN перехоплено `route.abort`) → `shotMiss: "no-lib"`;
       після появи бібліотеки наступний пін зі знімком (кеш скинуто);
    4. `html2canvas` кидає → `render`;
    5. `html2canvas` висить → `timeout` (вкоротити таймаут нельзя — використати `page.clock`);
    6. `uploadShot` повертає `null` двічі → `upload` і рівно 2 виклики; перший `null`, другий URL → `shotUrl`, без
       `shotMiss`;
    7. ціль зникла, двійника нема → `detached`;
    8. полотно (`anchors.shot` → `null`) → `render`;
    9. `shotLib: "/lib/h2c.js"` — завантажено саме цю адресу (`page.route`), CDN не запитано; `shotLib: "javascript:…"`
       → CDN.
- [ ] **Мутації:**
  - кожен код → його тест червоний (прибрати запис коду);
  - повернути кешування відхиленої бібліотеки → 3 червоний;
  - прибрати обрізку → 1 червоний;
  - прибрати повтор → 6 червоний.
- [ ] **Прогін:** як у T1 + `commenter-heavy`.
- [ ] **Коміт:** `fix(0.34): знімок піна — причина замість тиші, обрізка SVG, повтор завантаження`.

### Task 3: Коментатор — відповіді (API хоста, злиття, власна панель)

**Файли:**
- `commenter/src/comment-layer.js`;
- збірка;
- новий `tests/live/commenter-replies.test.mjs`;
- юніт `commenter/test/` (`stripRuntime`).

- [ ] **Поле `replies`:** `stripRuntime` знімає `_el`/`_pending` з коментаря і `_pending` з кожної відповіді (копія
  масиву, а не мутація). `snapshot()` і `getComments()` віддають копію `replies`.
- [ ] **Методи (працюють лише з `this._hostOpts`; без нього — `null`/`false`):**
  - **`reply(id, text)`:**
    - текст обрізаний, порожній → `null`; коментар не знайдено чи `status !== 'open'` → `null`;
    - відповідь `{ id: genId(), author: getUser(this.user, this.opts && this.opts.defaultUser, this._hostOpts).name,
      text, ts: nowStamp(), _pending: true }`; `c.replies = (c.replies || []).concat(r)`; `c._pending = true`;
    - `this._emit('onReply', { comment: id, reply: r.id })` ДО першого `onChange`; потім `_persist(); _render()`;
    - повертає `r.id`.
  - **`editReply(id, rid, text)`:** порожній → `false`; нема → `false`; інакше `text`, `editedTs = nowStamp()`,
    `_pending` на відповіді й коментарі, `_persist(); _render()`, `true`.
  - **`removeReply(id, rid)`:** нема → `false`; інакше відфільтрувати, `c._pending = true`, `_persist(); _render()`,
    `true`.
- [ ] **`_onExternalChange`:** для локального коментаря з `_pending`, який є в зовнішньому наборі, відповіді з `_pending`
  зливаються в зовнішню копію за id — локальна версія перекриває, нові дописуються; порядок — за `ts`, далі за порядком.
- [ ] **`_persist`:** після успішного запису знімає `_pending` і з відповідей.
- [ ] **`_carryToCurrent`:** копія коментаря відповіді НЕ переносить (нова ітерація — нова розмова); старий лишається
  зі своєю гілкою.
- [ ] **Власна панель (без хоста):** `_card` для коментаря з `replies.length > 0` додає один рядок
  `<div class="when">N replies</div>` (`1 reply`) після рядка часу. Без відповідей розмітка картки байт-у-байт та сама.
  Пошук власної панелі не змінюється.
- [ ] **Тести `tests/live/commenter-replies.test.mjs`:**
  1. **З `host`:**
     - `reply` → `onReply` прийшов раніше за `onChange` з цією відповіддю;
     - сховище отримало коментар із `replies` без `_pending`;
     - `snapshot().comments[i].replies` — копія (мутація знімка не змінює коментатор).
  2. `reply` на закритий / невідомий / з порожнім текстом → `null`; `editReply`/`removeReply` невідомих → `false`.
  3. `editReply` ставить `editedTs`, `removeReply` прибирає; обидва — `_persist`.
  4. Без `host`: `reply` → `null`; картка з двома відповідями має «2 replies»; без відповідей HTML картки дорівнює
     еталону, знятому з того самого бандла без поля.
  5. **Злиття:** сховище повертає зовнішню зміну (інший коментар змінився), поки запис відповіді «висить» (`save` —
     проміс, що не розвʼязано) → відповідь лишається в знімку; після розвʼязання — без `pending`.
  6. `carry` не переносить відповіді.
- [ ] **Юніт** `commenter/test/strip-runtime.test.mjs` (вирізати `stripRuntime`): вкладені `_pending` знято, вхід не
  змінено.
- [ ] **Мутації:**
  - `onReply` після `_persist` → 1 червоний;
  - прибрати злиття → 5 червоний;
  - прибрати перевірку `status` → 2 червоний;
  - `stripRuntime` без відповідей → юніт червоний.
- [ ] **Прогін:** як у T1 + `commenter-replies`.
- [ ] **Коміт:** `feat(0.34): коментатор — відповіді (reply/editReply/removeReply, onReply), злиття відповідей у польоті`.

### Task 4: Коментатор і хости — вигляд форми з оболонки (`host.theme`, `host.labels`)

**Файли:**
- `commenter/src/comment-layer.js`;
- збірка;
- `app/serve.py` (`HOST_ARG`, `PREVIEW_HOST_ARG`);
- `app/app.js` (постачальники `window.__dcCmtTheme`, `window.__dcCmtLabels`);
- `app/ext-shell.js` (те саме в превʼю);
- `app/i18n.js` (ключі `cmtForm*`);
- тести:
  - `tests/test_comments_role.py` — синхронізація `HOST_ARG` з `app.js`, якщо пришпилено;
  - `tests/live/commenter-host.test.mjs`;
  - `tests/live/comments-panel.test.mjs`;
  - `tests/live/preview-comments.test.mjs`.

- [ ] **`host.theme`:**
  - коментатор кличе `host.theme()` один раз у `_buildUI` (у `try`);
  - обʼєкт фільтрується за білим списком ключів `s1 s2 s3 s4 line line2 hi mid lo dim sel sel-hover sel-tint-2 on-sel
    open bad local-pin` і значенням (рядок ≤ 200 символів без `;{}<>`);
  - є хоч один ключ → на `.root` ставляться `--<ключ>` і клас `themed`, а в тіньовий корінь — окремий
    `<style data-cl-theme>` з правилами `.root.themed .compose…`, `.root.themed .mcompose…`. Вигляд — як у прототипі
    (`scratchpad/proto2/overlay-frame.js`, константа `CSS`):
    - поверхня `--s2`, радіус 8, тінь;
    - шрифт `system-ui`;
    - цитата цілі без курсиву, рамки й смуги, тег у моноширинному чипі;
    - поле `--s1`, у фокусі рамка `--sel`;
    - адресат — сегмент;
    - кнопки 28 px: друга — `--s3`, головна — `--sel`/`--on-sel`.
  - `STYLE` не змінюється.
- [ ] **`host.labels`:**
  - `host.labels()` → `{ placeholder, cancel, submit, target, quote, area, multiTitle, clear }`;
  - підставляються в `_openCompose`, `_openCanvasCompose` і форму «Кілька» замість англійських;
  - `target`/`area` — шаблони з `{tag}` і `{text}`, `quote` — з `{text}`, `multiTitle` — з `{n}`; підстановки — лише
    через `esc()`;
  - відсутній ключ — англійський текст; з `themed` тег у `target` рендериться як `<code>tag</code>`;
  - без `labels` — рядки дослівно як зараз.
- [ ] **Хости:**
  - `HOST_ARG` і `PREVIEW_HOST_ARG` отримують функції:
    `theme: function () { try { var f = window.parent && window.parent.__dcCmtTheme; return typeof f === 'function' ? f() : null; } catch (e) { return null; } }`,
    так само `labels` через `window.parent.__dcCmtLabels`;
  - `app.js` і `ext-shell.js` визначають ці функції:
    - тема — `getComputedStyle(document.body)` для ключів білого списку;
    - підписи — з `t()`.
  - **Ключі i18n:**
    - uk: «Що змінити?», «Скасувати», «Коментувати», «{tag} · «{text}»», ««{text}»», «область · {tag}»,
      «Коментар до елементів: {n}», «Очистити»;
    - en: «What should change?», «Cancel», «Comment», «{tag} · “{text}”», «“{text}”», «area · {tag}»,
      «Comment on {n} elements», «Clear».
- [ ] **Тести (живі):**
  - **`commenter-host.test.mjs`:**
    - з `host.theme` — обчислений `background-color` `.compose` дорівнює переданому `s2`, головна кнопка — `sel`, клас
      `themed` є;
    - шкідливе значення (`red;}` ) відкинуто;
    - з `host.labels` — placeholder і кнопки з підписів, `<img>` у тексті цілі екрановано;
    - без обох — `style` тіньового кореня один (без `data-cl-theme`), placeholder `Leave a change request…`.
  - **`comments-panel.test.mjs`** (Deai): форма над макетом має `themed` і placeholder з i18n (uk типово).
  - **`preview-comments.test.mjs`:** те саме в превʼю.
- [ ] **Мутації:**
  - прибрати фільтр значень → тест шкідливого значення червоний;
  - прибрати `esc` у шаблоні → тест екранування червоний;
  - зламати `theme` в `HOST_ARG` → Deai-тест червоний.
- [ ] **Прогін:** як у T1 + `node --test tests/*.test.mjs`, `python3 -B -m unittest tests.test_comments_role tests.test_serve`.
- [ ] **Коміт:** `feat(0.34): форма коментатора в токенах і мові оболонки (host.theme, host.labels)`.

### Task 5: Сховища — локальне, комбіноване, фікстура memo

**Файли:**
- `app/vendor/local-adapter.js`, `app/vendor/dual-store.js`;
- `tests/fixtures/modules/memo-comments/adapter.js`;
- тести: `tests/local-adapter.test.mjs`, `tests/dual-store.test.mjs`, `tests/memo-adapter.test.mjs`.

- [ ] **Локальне:**
  - `clean()` пропускає `replies`: масив, кожен елемент — лише `{id, author, text, ts, editedTs, agent}`, рядки
    відфільтровано, порожній масив → поле не пишеться;
  - `mergePin`: для `replies` злиття по id трьома сторонами (спека §1):
    - відповідь, змінена вкладкою (`m` ≠ `w`), — з `m`;
    - відповідь із `s`, якої нема в `w`, — лишається;
    - відповідь, що була в `w` і якої нема в `m`, — прибрана;
    - решта — з `s`; порядок — за `ts`, потім за порядком появи.
- [ ] **Комбіноване:**
  - `FIELDS` + `replies` (зміна гілки помічається);
  - новий геттер `repliesDown` (з командного сховища: `team.repliesDown`, рядок або `null`; при `teamDown` — `null`, бо
    причина вже показана);
  - метод `supportsReplies(aud)`: `'local'` → `true`; `'project'` → `!!team && team.supportsReplies === true`.
- [ ] **Фікстура memo:** `supportsReplies: true` (коментар зберігається цілим JSON — `replies` ходять самі).
- [ ] **Тести:**
  - **local-adapter:**
    - `replies` переживають запис;
    - злиття: агент дописав відповідь на диск, вкладка тим часом додала свою → обидві;
    - вкладка видалила відому → нема;
    - чужу, нову з диска, вкладка не знала → лишається;
    - `clean` відкидає зайві поля відповіді.
  - **dual-store:**
    - зміна лише `replies` → запис у відповідне сховище;
    - `repliesDown` / `supportsReplies` для обох сторін і при впалому командному.
  - **memo:** `supportsReplies === true`.
- [ ] **Мутації:**
  - прибрати `replies` з `FIELDS` → червоний;
  - злиття «з `m` цілим масивом» → тест «обидві» червоний.
- [ ] **Прогін:** `node --test tests/*.test.mjs`; живі `comments`, `comments-team`.
- [ ] **Коміт:** `feat(0.34): сховища — відповіді в локальному файлі (злиття по id) і в комбінованому сховищі`.

### Task 6: Supabase — таблиця `comment_replies`, адаптер і сервер модуля (окреме ревʼю)

**Файли:**
- новий `app/modules/supabase-comments/replies.sql`;
- `app/modules/supabase-comments/schema.sql` (той самий блок наприкінці);
- `app/modules/supabase-comments/adapter.js`, `app/modules/supabase-comments/server.py`;
- `app/modules/supabase-comments/README.md` (крок «відповіді»);
- тести:
  - `tests/supabase-comments-adapter.test.mjs`, `tests/supabase-comments-bundle.test.mjs`;
  - `tests/test_supabase_comments.py` (розширити `FakeSupabase`: шлях `/comment_replies`, POST з
    `Prefer: return=representation`, DELETE, `no_table` окремо для кожної таблиці);
  - новий `tests/test_supabase_replies_sql.py`.

- [ ] **SQL** (спека §1; лише прийоми з `schema.sql`):
  - таблиця й індекс `comment_replies_project_idx`;
  - RLS і чотири політики `clr_read/clr_insert/clr_update/clr_delete` з `drop policy if exists`;
  - `grant select, insert, update, delete … to anon, authenticated`;
  - `revoke truncate, references, trigger …`;
  - функція й тригер `clr_project_id_immutable`;
  - функція й statement-тригер `clr_delete_scope_guard` (один `project_id`, ≤ 100 рядків);
  - `alter publication supabase_realtime add table public.comment_replies` у блоці `do … exception when duplicate_object`;
  - жодного `references`, `on delete cascade`, `foreign key`;
  - шапка — попередження «окремий проєкт / LIGA: виконати лише replies.sql».
  - Блок у `schema.sql` між маркерами `-- >>> replies` / `-- <<< replies` дорівнює `replies.sql` (без шапки) дослівно.
- [ ] **Адаптер:**
  - константа `REPLIES = 'comment_replies'`;
  - **`fetchAll`:**
    - паралельно з коментарями — `from(REPLIES).select('*').eq('project_id', channel).order('created_at')`;
    - відповіді чіпляються до коментаря за `comment_id` (`{id, author, text, ts, editedTs: edited_ts, agent}`), сироти
      відкидаються;
    - помилка з кодом `PGRST205`/`42P01` чи статус 404 → `supportsReplies = false`, `repliesDown = 'no-replies-schema'`;
    - інша помилка → `repliesDown` = її текст;
    - коментарі в обох випадках як зараз;
  - `rowToComment`/`commentToRow` НЕ змінюються (відповіді — окремим кешем);
  - **`doSave`:**
    - рядки коментарів — як зараз;
    - відповіді (лише коли `supportsReplies`) — різницею проти `writtenReplies`: upsert змінених (той самий `raced`,
      повтори);
    - видалення відповідей, які адаптер знав для коментарів зі списку і яких більше нема;
  - **`remove(ids)`:** спершу `delete().in('comment_id', ids).eq('project_id', channel)` з `REPLIES` (лише коли
    `supportsReplies`), потім коментарі;
  - **realtime:** другий `.on('postgres_changes', {…, table: REPLIES}, …)` на тому самому каналі; `relevant`/`ownEcho`
    для відповідей — за `writtenReplies`;
  - **знімок сесії:** `{t, rows, replies}`; старий формат без `replies` вважається НЕзасіяним (свіже читання);
  - **геттери:** `supportsReplies` (`true` після успішного читання таблиці), `repliesDown`.
- [ ] **Сервер модуля:**
  - `_request` отримує необовʼязковий `table=TABLE_PATH`;
  - **`list`:** другий GET до `/rest/v1/comment_replies` (`project_id=eq.…&order=created_at&select=id,comment_id,author,text,ts,edited_ts,agent&limit=…`),
    відповіді в `comment['replies']`; відсутня таблиця — без відповідей і без помилки;
  - **`recent`:** ще й відповіді на відкриті коментарі (≤ 200 разом, нові першими): `{id, ts, author, status: 'open',
    version, parent}`, де `version` — з коментаря;
  - **нова `reply(ctx, channel, id, text, author)`:**
    - GET коментаря (`id=eq…&project_id=eq…&select=id,status`): нема → `module-error` «коментар не знайдено»;
      закритий → «коментар закрито»;
    - POST `comment_replies` з `Prefer: return=representation`, тіло `{id: uuid4, comment_id, project_id, author, text:
      _utf8(text)[:4000], ts: time.strftime('%d.%m.%Y %H:%M'), agent: True}`;
    - повертає `{id}`;
  - **`check`:** після «таблиця comments доступна» — GET `comment_replies?select=id&limit=1`:
    - 200 → `replies: True`, detail «таблиці comments і comment_replies доступні»;
    - no-schema → `ok: True`, `replies: False`, detail «таблиця comments доступна; для відповідей виконайте replies.sql».
- [ ] **Тести:**
  - **SQL статично (`test_supabase_replies_sql.py`):**
    - блок `schema.sql` == `replies.sql`;
    - є `enable row level security`, чотири `create policy` на `comment_replies`, `revoke truncate`, публікація;
    - нема `references`/`cascade`/`foreign key`;
    - ідемпотентність (`if not exists`, `drop … if exists`, `create or replace`).
  - **Адаптер:**
    - читання двох таблиць;
    - `PGRST205` → коментарі є, `supportsReplies === false`, `repliesDown === 'no-replies-schema'`, запис відповідей
      не йде;
    - запис різницею (змінена одна відповідь → один upsert у `comment_replies`, жодного в `comments`);
    - видалення відповіді;
    - `remove` — спершу відповіді;
    - realtime-подія `comment_replies` іншого каналу ігнорується, свого — перечитує, власне відлуння — ні;
    - старий знімок сесії → свіже читання;
    - тест 11 полів `rowToComment` — зелений без змін.
  - **Python:** `list` з відповідями / без таблиці, `recent` з `parent`, `reply` (тіло, `Prefer`, відмови), `check` обидва
    випадки; ключ не втікає в помилки (наявний `KeySafetyTest`-стиль).
- [ ] **Мутації:**
  - каскад у SQL → статичний тест червоний;
  - видалення коментаря без відповідей спершу → тест `remove` червоний;
  - `reply` без перевірки статусу → червоний;
  - `check` без другої таблиці → червоний.
- [ ] **Прогін:**
  - `node --test tests/*.test.mjs`;
  - `python3 -B -m unittest tests.test_supabase_comments tests.test_supabase_replies_sql`;
  - живі `comments-team`, `preview-comments`.
- [ ] **Коміт:** `feat(0.34): supabase-comments — таблиця comment_replies (replies.sql), адаптер і сервер модуля`.

### Task 7: Оболонка Deai — гілка в картці, «Нове», тексти

**Файли:**
- `app/comments-model.js`, `app/comments-view.js`, `app/comment-news.js`, `app/app.js`, `app/i18n.js`, `app/styles.css`;
- тести:
  - `tests/comments-model.test.mjs`, `tests/comments-view*.test.mjs`, `tests/comment-news.test.mjs`,
    `tests/comments-wiring.test.mjs`, `tests/css-guards.test.mjs`;
  - живі `tests/live/comments-panel.test.mjs`, `tests/live/comments-team.test.mjs`.

- [ ] **Модель:**
  - `matchQuery` шукає й у тексті та авторах відповідей;
  - `commentSections`: «свіжий» — відкритий коментар, коли `fresh.has(c.id) && audOf(c) === "project"` АБО хоч одна
    його відповідь у `fresh`;
  - `filterCounts.fresh` → `{ local, project }`: свіжих коментарів для кожного фільтра (бейдж «+K» на обох);
  - новий експорт `repliesOf(c)` — масив, відсортований за `ts`.
- [ ] **Новини (`comment-news.js`):**
  - **новий експорт `newsItems(comments)`:**
    - командні відкриті коментарі (як `teamOf`);
    - відповіді на відкриті коментарі будь-якого каналу:
      `{ id: r.id, ts: r.ts, author: r.author, status: 'open', version: c.meta && c.meta.version, parent: c.id }`;
  - `isNew` / `baseline` / `arrived` / `countNew` працюють з ним без змін (є `status`, `author`, `id`).
- [ ] **Вигляд — гілка в `cardHTML`:**
  - **рядок гілки** між `done` і рядком дій; новий `st` (усе необовʼязкове; без них — як було):
    - `threads: Set` — розгорнуті;
    - `replying: id`;
    - `replyEdit: "cid|rid"`;
    - `replyDelAsk: "cid|rid"`;
    - `isOwnReply(r)`, `canDeleteReply(r)`;
    - `repliesOff(c) → string|null`;
  - **розмітка — як у прототипі `scratchpad/proto2/overlay.js` (`threadHTML`/`replyHTML`):**
    - `.cmt-thread`, `.cmt-rsum` (`data-act="cmtthread"` чи, без відповідей, `cmtreply`), `.cmt-rlast`, `.cmt-rnew`;
    - `ol.cmt-replies > li.cmt-reply(.cmt-reply--new)`, `.cmt-rhead`, `.cmt-rwho(.cmt-ragent)`, `.cmt-redited`, `.cmt-rtext`;
    - `.cmt-rbox(.cmt-rbox--on) > textarea.cmt-rta[data-val=cid]`, `.cmt-rrow`, `.cmt-rhint`, кнопки `cmtreplycancel` /
      `cmtreplysend` (`.cmt-act--pri`);
    - `.cmt-rnote` — коли `repliesOff(c)`;
    - правка відповіді — `textarea.cmt-redit` + `cmtreditsave` / `cmtreditcancel`;
    - кнопки `cmtredit` / `cmtrdel` (значення `cid|rid`);
    - підтвердження `confirmHTML` з `cmtrdelyes` / `cmtrdelno`;
  - **закриті** — рядок «› N відповідей» без поля й без дій над відповідями;
  - **`cmtdel` коментаря з відповідями** — питання `cfmDelCmtReplies(n)`;
  - **«Без знімка: …»** — `.cmt-shotmiss` з іконкою `camera`, текст `t("cmtShotMiss_" + code)`, лише коли
    `meta.shotMiss` відомий;
  - **заголовок розділу «Нове»** — `cmtNewTitle` змінює значення: uk «Нове», en «New».
- [ ] **Тексти (`i18n.js`, uk + en):**
  - `cmtReplies(n)` (uk через `plural`: відповідь/відповіді/відповідей; en `reply/replies`), `cmtReplyNew(k)` («+K
    нова»/«+K new»), `cmtReplyNewChip`;
  - `cmtReply`, `cmtReplyPh`, `cmtReplySend`, `cmtReplyHint`;
  - `cmtReplyEdited`, `cmtReplyEdit`, `cmtReplyDelete`, `cfmDelReply`, `cfmDelCmtReplies(n)`;
  - `cmtRepliesOff`, `cmtTeamRepliesDown(why)`, `cmtRepliesNoSchema`, `cmtRepliesNoModule`;
  - `cmtReplyToast(who, n)` («Нова відповідь від {who} · #{n}»);
  - `cmtShotMiss_<код>` — рядок «Без знімка: <причина>.» / «No screenshot: <reason>.»:

    | код | uk | en |
    |---|---|---|
    | `too-big` | елемент завеликий для знімка | the element is too large to capture |
    | `no-lib` | бібліотека знімків не завантажилась | the screenshot library didn't load |
    | `timeout` | знімок не встиг | the screenshot timed out |
    | `render` | знімок не вдався | the screenshot failed |
    | `detached` | елемент зник зі сторінки до збереження | the element left the page before saving |
    | `upload` | знімок не завантажився в сховище | the screenshot didn't upload |

  - смуга й нотатка:
    - `cmtTeamRepliesDown(why)` — «Відповіді команди недоступні: {why}» / «Team replies are unavailable: {why}»;
    - `cmtRepliesNoSchema` — «у базі немає таблиці відповідей — виконайте replies.sql модуля» / «the database has no
      replies table — run the module's replies.sql»;
    - `cmtRepliesNoModule` — «модуль коментарів не підтримує відповідей» / «the comments module doesn't support
      replies»;
    - `cmtRepliesOff` — «Відповіді команди недоступні — причина вгорі панелі.» / «Team replies are unavailable — see the
      reason at the top of the panel.»;
  - гілка: `cmtReply` «Відповісти»/«Reply», `cmtReplyPh` «Відповісти…»/«Reply…», `cmtReplySend` «Надіслати»/«Send»,
    `cmtReplyHint` «⌘↵ — надіслати»/«⌘↵ to send», `cmtReplyEdited` «змінено»/«edited», `cmtReplyNewChip` «нова»/«new»,
    `cfmDelReply` «Видалити відповідь?»/«Delete this reply?», `cfmDelCmtReplies(n)` «Видалити назавжди разом із N
    відповідями?» (uk `plural` в орудному: відповіддю/відповідями/відповідями) / «Delete permanently along with N
    replies?» (`1 reply`);
  - імʼя агента — наявний `cmtAudLocal` («AI»).
- [ ] **Проводка (`app.js`):**
  - **стан:** `cmtThreads`, `cmtReplying`, `cmtReplyDraft`, `cmtReplyEdit`, `cmtReplyEditDraft`, `cmtReplyDelAsk`;
    скидання при зміні задачі/рамки там, де скидаються `cmtEditing`/`cmtDelAsk`;
  - **`BAR_ACTIONS`** (кожна в окремому рядку з двома пробілами): `cmtthread`, `cmtreply`, `cmtreplysend`,
    `cmtreplycancel`, `cmtredit`, `cmtreditsave`, `cmtreditcancel`, `cmtrdel`, `cmtrdelyes`, `cmtrdelno` → `cmtLayer()`
    `.reply` / `.editReply` / `.removeReply`;
  - **права в Deai:**
    - змінити — `r.author === myName() && !r.agent`;
    - видалити — будь-яку;
    - відповісти — відкритий коментар, `repliesOff(c)` null;
  - **`repliesOff(c)`:**
    - локальний → `null`;
    - командний → `readRepliesDown(L)` (новий, як `readTeamDown`: `L.store.repliesDown`) чи «модуль не підтримує»,
      коли `L.store.supportsReplies && !L.store.supportsReplies('project')`;
  - **смуга `cmt-teamdown`** з `cmtTeamRepliesDown` (для `no-replies-schema` — `cmtRepliesNoSchema`);
  - **`paintComments`** зберігає фокус і курсор `textarea.cmt-rta`/`.cmt-redit` та чернетки, як для `.cmt-edit`;
  - **`input`/`keydown`:** ⌘/Ctrl+↵ у `.cmt-rta` → `cmtreplysend`, у `.cmt-redit` → `cmtreditsave`; Esc → скасувати;
  - **новини:**
    - `cmtNewsUpdate` бере `newsItems(all)` замість `teamOf(all)`;
    - «бачив» посувається й для відповідей: де зараз `markSeen` отримує id видимих карток, він отримує ще й id відповідей
      цих карток (картка видима — її відповіді бачені, як у спеці §4);
    - тост для відповіді — `cmtReplyToast(автор, n батьківського)`, дія відкриває панель, вибирає батьківський коментар,
      розгортає гілку (`cmtThreads.add`), прокручує;
  - **острівець** — без змін у коді (число вже `cmtNewsN`).
- [ ] **CSS (`styles.css`):** класи з прототипу (`scratchpad/proto2/overlay.css`, блок «ПРОПОЗИЦІЯ 0.34»), лише токени;
  лінія гілки 1 px `--line2`; нова відповідь — тон `--open` 10 %, без бічної смуги.
- [ ] **Тести:**
  - **модель:** пошук по відповідях; свіжість за відповіддю (локальний коментар з новою відповіддю AI — у `fresh`);
    `filterCounts.fresh` по обох фільтрах;
  - **новини:** `newsItems` — відповіді закритих не входять, `parent`/`version` заповнені; `isNew` власної відповіді —
    `false`;
  - **вигляд:**
    - множина uk 1/2/5/11/21/22;
    - згорнута / розгорнута гілка;
    - поле лише на відкритому;
    - нотатка `repliesOff`;
    - агент має `cmt-ragent`;
    - екранування тексту й автора відповіді (`<img src=x>`);
    - питання видалення з кількістю;
    - `shotMiss` усіх кодів;
    - без нових полів `st` розмітка картки без відповідей не змінилась (порівняти з рядком до зміни — зафіксувати
      еталон у тесті);
  - **проводка:** нові дії в `BAR_ACTIONS`; `readRepliesDown` у `try`; localStorage у `try` (наявний тест);
  - **живі `comments-panel.test.mjs`:**
    - відповісти на локальний пін → гілка «1 відповідь», запис у файлі задачі;
    - змінити свою, видалити;
    - закритий без поля;
    - пошук знаходить коментар за текстом відповіді;
  - **живі `comments-team.test.mjs`:**
    - відповідь у командному (memo);
    - відповідь іншого автора, дописана в memo, → «Нове», бейдж, тост «Нова відповідь від …», фільтр «+1»;
    - відповідь у `.dc-local-comments.json` з `agent: true` (як від `inbox.py`) → те саме після фокуса вікна;
    - модуль без `supportsReplies` → нотатка й смуга, локальні відповідають.
- [ ] **Мутації:**
  - свіжість лише за `c.id` → тест AI-відповіді червоний;
  - без `esc` → тест екранування червоний;
  - кнопка поля на закритому → червоний;
  - `teamOf` замість `newsItems` → живий тест тосту червоний.
- [ ] **Прогін:** `node --test tests/*.test.mjs`; живі `comments-panel`, `comments-team`, `comments`, `shell-typing`,
  `claude-status`.
- [ ] **Коміт:** `feat(0.34): панель Deai — відповіді в картці, «Нове» з відповідями, «Без знімка: …»`.

### Task 8: Публічне превʼю — відповіді

**Файли:**
- `app/ext-comments.js`, `app/ext-shell.js`, `app/serve.py` (`PREVIEW_HOST_ARG.onReply`);
- тести:
  - `tests/ext-comments.test.mjs`, `tests/comments-view-preview.test.mjs`;
  - `tests/test_serve.py` (збірка превʼю: `onReply` у сторінці);
  - живий `tests/live/preview-comments.test.mjs`.

- [ ] **`PREVIEW_HOST_ARG`:** `onReply: function (o) { send({ ev: 'reply', id: o && o.reply }); }`;
  `CMT_EVENTS` превʼю + `"reply"` → `own.add(id)`.
- [ ] **Дії та права:**
  - `CMT_ACTS` + усі нові `cmt*` дії відповідей (той самий перелік, що в T7);
  - у `paint`: `isOwnReply: (r) => ownIds.has(r.id)`, `canDeleteReply` — те саме, `repliesOff` — з `L.store` як у Deai,
    `threads` / `replying` / … — у `st` превʼю;
  - перед `reply` — `await ensureName()`; скасовано → нічого не надсилати, чернетку лишити;
  - `editReply` / `removeReply` — лише через охоронця «своя відповідь» (`own.has(rid)`) на відкритому коментарі.
- [ ] **«Нового» в превʼю нема** (жодних `fresh`); `comment-news.js` не імпортується (наявний тест закриття імпортів).
- [ ] **Тести:**
  - **юніт:** охоронець своєї відповіді; `paint` передає функції прав; відповідь на закритий неможлива;
  - **Python:** сторінка превʼю має `onReply` у `host`;
  - **живі `preview-comments.test.mjs`:**
    - імʼя питається один раз (перед першою відповіддю, якщо ще не питалось перед коментарем);
    - своя відповідь — змінити/видалити, чужа — без кнопок;
    - закритий — без поля;
    - `prompt()` не кликали;
    - запис відповіді в memo;
    - картки з Deai (маршрут `/commented`) без «На іншій сторінці» (баг 3 наскрізно).
- [ ] **Мутації:**
  - прибрати `own.add` для `reply` → тест «своя» червоний;
  - прибрати `ensureName` → тест імені червоний.
- [ ] **Прогін:** `node --test tests/*.test.mjs`; `python3 -B -m unittest tests.test_serve`; живі `preview-comments`,
  `ext-shell`, `preview-follow`.
- [ ] **Коміт:** `feat(0.34): превʼю — відповіді (свої змінити й видалити, імʼя один раз)`.

### Task 9: Агент і сервер — `inbox.py`, `/api/comment-news`, довідка

**Файли:**
- `app/serve.py` (`agent_pin`, `agent_news`, `ProjectComments.reply`, `_comment_news`, `_local_file`-помічник);
- `app/deai_modules.py` (`ROLE_OPTIONAL_FUNCTIONS['comments'] = ('recent', 'reply')`);
- `bin/inbox.py`, `app/templates/agents.md`;
- тести: `tests/test_inbox.py`, `tests/test_comments_agent.py`, `tests/test_comments_role.py`.

- [ ] **`agent_pin`:**
  - пропускає `replies`: список ≤ 200 елементів `{id, author, text, ts, editedTs, agent}`;
  - рядки через ту саму очистку, що текст піна;
  - `id` за `_AGENT_ID`, інакше відповідь відкинута;
  - `meta.shotMiss` проходить у `meta`, як і решта `meta`.
- [ ] **`agent_news`:** пропускає `parent` (за `_AGENT_ID`).
- [ ] **`ProjectComments.reply(task, tid, pin_id, text, internal=False)`:**
  - `self.prov.fn('reply') is None` → `None` (не підтримує);
  - інакше `_AGENT_ID`-перевірка й `self._module('reply', task, tid, internal, pin_id, text, 'AI')`.
- [ ] **`_comment_news`:**
  - до елементів модуля додає відповіді `agent: true` з локального файла задачі на відкриті локальні піни (той самий вигляд
    елемента з `parent`);
  - `supported` — `True`, якщо є хоч одне джерело (локальний файл існує чи модуль має `recent`).
- [ ] **Вкладки (`pollTabNews` у `app.js`):** перевірити, що число на вкладці рахує й елементи з `parent` тим самим
  набором «бачив» (поля `id/author/status` ті самі); якщо фільтр відкидає їх — виправити й покрити юніт-тестом.
- [ ] **`inbox.py`:**
  - **`show_pins`:**
    - під піном `↳ відповіді (N):` і до 20 останніх рядків `<автор>, <ДД.ММ ГГ:ХХ>: <текст>` (кожен ≤ 300 через
      `agent_line`), відповіді агента позначені `AI`;
    - `↳ без знімка: <причина>` для `meta.shotMiss` (українські тексти — словник у `inbox.py`, коди зі спеки);
  - **підкоманда `reply ID --text "…"`** (`--dry-run`): пошук — `find_target`;
    - **локальний** — `write_local_reply(path, id, text, now)`: перечитати файл перед записом, додати `{id: uuid4,
      author: 'AI', text, ts, agent: true}`, `atomic_write_json`;
    - **командний:**
      - лише `for_agent(p, 'project')`; інакше відмова «пін не доручено AI — відповідати можна лише в дорученому»;
      - `pc.reply(...)`; `None` → відмова «модуль коментарів не підтримує відповідей»;
    - **відмови:** закритий; порожній текст; > 4000;
    - вихід: `✓ {id8} відповідь додано ({локальний|проєкт})`;
  - `EPILOG` і підказка наприкінці переліку — з прикладом `reply`.
- [ ] **`agents.md`:**
  - у розділі Comments приклад `inbox.py reply <comment-id> --text "question or note"`;
  - одне речення: питай у гілці, якщо зміст коментаря неоднозначний, замість вгадування; відповідь у командному піні
    бачать колеги;
  - відповіді людей під піном — частина задачі.
- [ ] **Тести:**
  - **`test_inbox.py`:**
    - вивід гілки й `shotMiss`;
    - `reply` локальний (файл, атомарність — інший запис між читанням і записом не губиться);
    - командний (тіло POST через `FakeNet`, `agent: true`);
    - відмови (недоручений, закритий, модуль без `reply`, порожній), `--dry-run` нічого не пише;
  - **`test_comments_agent.py`:** `agent_pin` з `replies` (шкідливі id відкинуто, керівні символи вичищено);
    `/api/comment-news` з локальними відповідями агента;
  - **`test_comments_role.py`:** `reply` — необовʼязкова функція (модуль без неї валідний).
- [ ] **Мутації:**
  - прибрати `for_agent` у `reply` → тест «недоручений» червоний;
  - прибрати перечитування → тест атомарності червоний.
- [ ] **Прогін:**
  - `python3 -B -m unittest discover -s tests`;
  - `python3 -B -m unittest discover -s bin -p 'test_*.py'`;
  - `python3 -B -m unittest discover -s app -p 'test_*.py'`.
- [ ] **Коміт:** `feat(0.34): агент — відповіді в inbox.py (читання й reply), новини відповідей на вкладках`.

### Task 10 (контролер): документи, сумісність, версія

- [ ] **README:**
  - «Comments»: відповіді, агент (`inbox.py reply`), «Нове»;
  - «The published preview»: відповіді в превʼю;
  - «Pin screenshots»: `shotMiss`.
- [ ] **Документи модулів:**
  - `app/modules/supabase-comments/README.md` — крок `replies.sql` для наявних проєктів і застереження для бази ЛІГИ;
  - `docs/modules/comments.md`:
    - `replies` у коментарі;
    - `supportsReplies` / `repliesDown` у контракті сховища;
    - необовʼязкова `reply` у серверній половині;
    - `recent` з `parent`.
- [ ] **Коментатор:** `commenter/README.md` — нові опції хоста (`onReply`, `theme`, `labels`), методи, `shotMiss`.
- [ ] **Реліз:**
  - CHANGELOG `[0.34.0]` (або наступна вільна) і «Що нового» діалогу оновлення;
  - `package.json` — версія.
- [ ] **Перевірки:**
  - заборонений список:
    `DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses`;
  - фінальне ревʼю всієї гілки.

### Task 11 (контролер): реліз

- [ ] **Перед злиттям:**
  - `git -C "$HOME/Liga Tools/deai-canvas" log --oneline -1` і версія в `package.json`;
  - злити `main` (етап «Перший запуск») у гілку — `git merge`;
  - конфлікти в `i18n.js`, `app.js`, `styles.css`, CHANGELOG, `package.json` — вручну;
  - взяти наступну вільну мінорну.
- [ ] **Релізний прогін:**
  - JS юніт, `commenter/test`;
  - Python `discover -s tests` (+ `bin`, `app`);
  - заборонений список;
  - усі живі файли по одному.
- [ ] **Живе дерево:**
  - `git merge --ff-only`; анотований тег з `-c user.name=neodisa`;
  - канвас: зупинити за PID (`lsof -nP -iTCP:8765 -sTCP:LISTEN`), `./start.command >/dev/null 2>&1`, перевірити
    `/api/update`.
- [ ] **Push — лише після явного «да» власника;** перед push звірити SHA гілки з HEAD і origin.
- [ ] **Власнику:**
  - виконати `replies.sql` у своїх проєктах Supabase і в базі ЛІГИ (лише з його «да»; я не застосовую);
  - перепублікувати активні превʼю;
  - як оновити бандл коментатора в живому продукті.

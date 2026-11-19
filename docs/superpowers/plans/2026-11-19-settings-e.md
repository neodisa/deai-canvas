# Етап Е — Налаштування й AGENTS.md (0.31.0) — план

> **Для виконавців:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (контролер) / superpowers:test-driven-development
> (виконавець). Кроки з чекбоксами (`- [ ]`).

**Мета:** сторінка «Налаштування» з лівою навігацією (Простір · Модулі · AGENTS.md / Загальне · Оновлення · Гарячі
клавіші), модулі карточками з однією дією, каталог і «Свій модуль», «В Figma» як вимикач простору, колір простору фарбує
вікно, AGENTS.md із шаблону, що зберігає «Ваше».

**Спека:** `docs/superpowers/specs/2026-11-19-settings-e-design.md` (джерело правди для поведінки й текстів).
**Прототип:** https://claude.ai/artifact/RfC5kh614NqWqsAvm8DEz5 (вигляд; класи — наші, `app/styles.css`).

**Архітектура:** чисті моделі в нових модулях (`app/settings-model.js`, `app/modules-grid.js`, `app/agents_md.py`),
розмітка — чисті рядки у `*-view.js`, проводка — `app/app.js`. Сервер — `app/serve.py` (маршрути) + `app/agents_md.py`.

**Стек:** vanilla JS (ES-модулі), Python 3 stdlib, `node --test`, `unittest`, Playwright (живі).

---

## Спільні правила (для КОЖНОЇ задачі)

- Робоча тека: `/Users/sergeyarkhipov/Liga Tools/deai-canvas-dev`, гілка `feat/settings-e`. Інших гілок не чіпати.
- Коміт: `git add -- <нові файли>` і
  `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`.
  Ніколи `git add -A`, `--amend`, `stash`, `reset`, `checkout` інших гілок, `rebase`. Ніколи не стейджити
  `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `…2026-11-09-agents-sdk-policy-addendum.md`.
- Тести НЕ торкаються портів 8765/4317, живого дерева `~/Liga Tools/deai-canvas`, справжніх `~/.deai`, `~/deai-published`,
  `~/deai-work`, `~/.gitconfig`, `~/.claude/pipeline-feedback`, Teams, Supabase, Jira. `DEAI_HOME`/`DC_TASKS_FILE` — лише у
  фікстурах тестів. Python — `python3 -B`. Без встановлення пакетів із мережі.
- Живі тести — ПО ОДНОМУ файлу: `node --test --import ./tests/live/_env.mjs tests/live/<f>.test.mjs`; ніколи паралельно з
  Python-набором. Сервери зупиняти лише за PID; ніколи `pkill`/`killall` за шаблоном; без `rm -rf` (тимчасові теки —
  `mktemp -d`).
- Кожна НОВА перевірка доводиться мутацією: зламати код → тест червоний → повернути → зелений (записати у звіт).
- Тексти: обидві мови в `app/i18n.js` (uk + en, однаковий набір ключів — є тест). Жодних підписів-пояснень, яких нема в
  спеці (правило власника «без зайвих підписів»).
- `tests/css-guards.test.mjs` вимагає ПОВНІ літерали класів у JS/CSS (не склеювати `'cn-' + x`).
- Публічний репо: жодних реальних імен, внутрішніх хостів, IP, ключів, користувацьких шляхів у коді/тестах/доках.
- Наявні тести, що пришпилюють стару розмітку «Налаштувань» (`tests/connections-view.test.mjs`, `tests/connections-wiring.test.mjs`,
  `tests/live/connections.test.mjs`, `tests/live/own-modules.test.mjs`, `tests/trust-flow.test.mjs`…), оновлювати свідомо:
  перевірка ПОВЕДІНКИ зберігається (той самий ендпоінт, той самий фокус, той самий тост), змінюється лише розмітка. Не
  видаляти перевірку без заміни; у звіті — список змінених перевірок.
- Наприкінці задачі: `node --test tests/*.test.mjs`, `python3 -B -m unittest discover -s tests` (лише якщо чіпали Python),
  живі файли, які задача зачепила.

---

### Task 1: Каркас — навігація й розділи

**Файли:** Create `app/settings-model.js`, `tests/settings-model.test.mjs`. Modify `app/connections-view.js`
(`connPageHTML` → каркас), `app/app.js` (`connSec`, `enterConnections`, `BAR_ACTIONS.settings`), `app/styles.css`,
`app/i18n.js`. Live: `tests/live/settings-nav.test.mjs` (новий; `PORT_BASE` — вільний, напр. 28600).

- [ ] Модель (`settings-model.js`, чисті функції):
  ```js
  export const SECTIONS = ['space', 'mods', 'agents', 'app', 'upd', 'keys'];
  export const SEC_KEY = 'deai.settingsSec';
  export function readSec(stored) { return SECTIONS.includes(stored) ? stored : 'mods'; }
  /** Навігація: [{group:'space'|'app', id, icon, labelKey, badge?: {kind:'count'|'dot', n?}}] */
  export function navItems({ trustWaiting = 0, agentsOutdated = false } = {}) { … }
  ```
  Іконки: space→`palette`, mods→`puzzle`, agents→`doc`, app→`desktop`, upd→`refresh`, keys→`keyboard`. Нові символи
  `palette`, `puzzle`, `doc`, `keyboard`, `code` додати в `SPRITE` (`app/icons.js`) — шляхи з прототипу (`proto-e/sprite-e.svg`,
  контролер дасть текст).
- [ ] Розмітка: `.set` (grid 224px | 1fr), `.set-nav` (групи `h6`, кнопки `.nav-i[data-act="csec"][data-v]`,
  `aria-current="page"` на поточній), `.set-main > .set-in` (вміст розділу). Групи: «Простір · {імʼя}» з `.sp-dot`, «Застосунок».
  Розділи, яких ще нема (до своїх задач), малюють лише `<h1>`.
- [ ] `connSec` у app.js: читається з `localStorage[SEC_KEY]` (try/catch), пишеться на зміну; `enterConnections(role)` з
  `role` → `mods` + фокус ролі (як зараз); ⌘K «Налаштування простору» і «Налаштування…» з фішки → `mods`; шестерня →
  збережений.
- [ ] `< 760px`: навігація рядком (CSS), без `h6`.
- [ ] i18n (uk/en): `setNavSpace` «Простір · {name}» / «Space · {name}», `setNavApp` «Застосунок»/«App», `setSecSpace`
  «Простір»/«Space», `setSecMods` «Модулі»/«Modules», `setSecAgents` «AGENTS.md», `setSecApp` «Загальне»/«General»,
  `setSecUpd` «Оновлення»/«Updates», `setSecKeys` «Гарячі клавіші»/«Keyboard shortcuts», `setTrustWaiting` (title лічильника)
  «Чекає довіри»/«Awaiting trust», `setAgentsOutdated` «Є новіший шаблон»/«A newer template is available».
- [ ] Юніт: `readSec` (невідоме → `mods`), `navItems` (порядок, групи, бейджі).
- [ ] Живий: шестерня → `mods`; клік «Гарячі клавіші» → `aria-current` переходить, вміст `h1`; вихід і знову шестерня →
  той самий розділ; перезавантаження сторінки → той самий; ⌘K «Налаштування простору» → `mods`; ширина 700 → навігація
  рядком (обчислений `flex-direction: row`).
- [ ] Коміт: `feat(0.31.0): налаштування — ліва навігація й розділи`.

### Task 2: Модулі — сітка карток

**Файли:** Create `app/modules-grid.js`, `tests/modules-grid.test.mjs`. Modify `app/connections-view.js`,
`app/connections-model.js` (лише якщо треба експорт), `app/app.js` (делегація `data-cn`), `app/styles.css`, `app/i18n.js`,
наявні тести «Налаштувань» (див. спільні правила).

- [ ] Модель:
  ```js
  /** Стан картки → {badge, action|null, menu: [...]} за таблицею спеки §2. Бере `cardView(e)` як джерело правди про
   *  дозволені дії й лише вибирає одну на картку, решту — в меню. */
  export function cardModel(e) { … }
  /** Що в сітці: увімкнені, свої (усі), «Не встановлено»; у порядку ROLE_ORDER, далі «Інше». */
  export function gridEntries(list) { … }
  /** Ролі без жодного модуля в сітці (крім «Інше») → [{role, icon, titleKey, noneKey}]. */
  export function emptyRoles(list) { … }
  ```
  Таблиця дій (спека §2): ok → `null`; unchecked → `check`; error → `configure` (свій refused без знімка → `trustinfo`);
  untrusted → `trust`; свій довірений вимкнений → `enable`; missing → `null`. Меню: `configure` (є налаштування), `check`
  (увімкнений), `trust`→«Код» (свій), `untrust` (свій довірений), розділювач, `disable` (увімкнений).
- [ ] Розмітка картки `.mc` (див. прототип): `.mc-top` (`.mc-ic`, `.mc-name` b+span, `.mc-tag` «свій», `.mc-more`
  `data-cn="menu"` `aria-haspopup="menu"`), `.mc-why` (причина помилки, наявний `whyOf`), `.mc-foot` (`.bdg.bdg--{ok|err|off|trust|unchecked|missing}` + одна
  кнопка `data-cn="<act>"`). Уся картка — `role="button"`/`tabindex=0`, клік/Enter: увімкнений → шухляда (`configure`),
  untrusted → `trust`.
- [ ] Меню «⋯» — наявний `.cv-ctx` (як меню картки задачі етапу Д), стрілки/Esc/фокус назад на «⋯».
- [ ] Вимкнення — питання в картці `.cfm` (класи етапу Д): `cnDisableAsk(name)` + наслідок `disableConsequences`; фокус
  «Скасувати»; Esc/«Скасувати» → картка з фокусом на «⋯»; «Вимкнути» → наявний `POST /api/module-disable`, тост як зараз.
- [ ] «Без модуля · N» — `h2.sub` + `.mg` пунктирних `.mc.mc--empty` (`data-role`), кнопка `data-cn="cat"` «Додати»
  (до Task 3 — відкриває наявний перелік як зараз; у Task 3 — каталог).
- [ ] Заголовок розділу: `h1` «Модулі» + кнопка «Додати модуль» (`data-cn="cat"`).
- [ ] Прибрати зі сторінки блок `.cn-agent` і секції по ролях («Зараз: …», лід ролі). Рядки `cnLead*`, `cnAgent*`, `cnNow*`,
  що більше ніде не вживаються, — видалити з обох мов (є тест на невживані ключі? — перевірити; якщо ні, просто прибрати).
  Розділ «Не встановлені на цьому компʼютері» — тепер картки зі станом «Не встановлено» в сітці.
- [ ] Тексти: «Довіритись…» → «Довірити»; «Потрібна довіра» → «Чекає довіри»; кнопка діалогу довіри «Довіряю» → «Довірити».
  Нові: `mcAdd` «Додати модуль»/«Add module», `mcAddRole` «Додати»/«Add», `mcEmptyH(n)` «Без модуля · {n}»/«No module · {n}»,
  `mcMore(name)` «Дії модуля {name}»/«{name} actions», `mcCode` «Код»/«Code», `mcUntrust` — наявний `cnUntrust`.
- [ ] `enterConnections(role)`: фокус на картці модуля ролі, інакше на пунктирній картці ролі.
- [ ] Юніт: `cardModel` — кожен рядок таблиці (мінімум 8 випадків, включно з own refused з/без знімка, changed, missing);
  `gridEntries` (вимкнений вбудований НЕ в сітці; свій невімкнений — у сітці; порядок); `emptyRoles` (роль із вимкненим
  вбудованим — порожня; «Інше» ніколи).
- [ ] Живий (`tests/live/connections.test.mjs` оновити + нові кейси): картка помилки має одну кнопку «Налаштувати» → шухляда;
  «⋯ → Вимкнути» → питання в картці, фокус «Скасувати», Esc → без запиту; «Вимкнути» → `module-disable` і картка зникає,
  зʼявляється пунктирна роль; свій недовірений → «Довірити» відкриває діалог довіри.
- [ ] Коміт: `feat(0.31.0): модулі — картки з однією дією, питання в картці, ролі без модуля`.

### Task 3: Каталог «Додати модуль» і «Свій модуль»

**Файли:** Create `app/catalog-model.js`, `tests/catalog-model.test.mjs`. Modify `app/connections-view.js` (або новий
`app/catalog-view.js`), `app/app.js`, `app/serve.py` (`/api/modules` → `deai.authoring`), `app/i18n.js`, `app/styles.css`.
Live: новий кейс у `tests/live/connections.test.mjs`.

- [ ] Сервер: відповідь `GET /api/modules` отримує `deai: {authoring: <абсолютний шлях до docs/modules/authoring.md цієї
  установки>}` (від кореня репо, як `bin/` у serve.py). Python-тест: ключ є, шлях закінчується на `docs/modules/authoring.md`
  й існує.
- [ ] Модель:
  ```js
  /** Групи каталогу: вбудовані, яких нема в сітці, за ROLE_ORDER → [{role, rows:[{id, nameKey|name, descKey, replaces: name|null}]}] */
  export function catalogGroups(list) { … }
  /** Текст запиту агенту (мовою інтерфейсу) */
  export function ownPrompt({ space, folder, authoring, what, lang }) { … }
  ```
- [ ] Діалог (система поповерів етапу В, `askForm`/підкладка): сторінка 1 — групи, рядок `.cat` (іконка, назва, опис,
  кнопка `Підключити`/`Замінити {name}`), підсвічена роль (`.cat--hl`, коли відкрито з пунктирної картки); останній —
  `.cat.cat--own` «Свій модуль» → «Як додати ›». Сторінка 2 (той самий діалог): «‹» назад, `ol.steps` (3 кроки спеки),
  поле `textarea#own-what`, `pre.prompt`, «Скопіювати запит» (`navigator.clipboard.writeText`, відмова → виділити текст;
  тост «Запит скопійовано — вставте його агенту»).
- [ ] Вибір модуля → закрити діалог → наявна шухляда «Підключити» (`cnReplaceAsk` НЕ показувати — кнопка вже каже
  «Замінити»); без налаштувань → одразу `module-enable` і тост.
- [ ] Тексти (uk/en): `catTitle` «Додати модуль», `catConnect` «Підключити», `catReplace(name)` «Замінити {name}»,
  `catOwn` «Свій модуль», `catOwnLead` «Агент напише модуль під вашу задачу; він житиме в теці простору.», `catOwnHow`
  «Як додати», `ownStep1/2/3` (спека §3), `ownWhat` «Що має робити модуль», `ownWhatPh` «напр. звіряти кольори макета з
  brand.css», `ownCopy` «Скопіювати запит», `ownCopied`, `catBack` «Назад до каталогу».
- [ ] Юніт: `catalogGroups` (увімкнений не в каталозі; зайнята роль → `replaces`; порядок); `ownPrompt` (містить імʼя,
  теку, authoring-шлях, `what`; порожнє `what` → нейтральна підстановка; обидві мови).
- [ ] Живий: «Додати» на пунктирній ролі → діалог із підсвіченою групою; «Підключити» → шухляда «Підключити»; «Свій
  модуль» → «Скопіювати запит» → тост; Esc на 2-й сторінці закриває діалог, фокус назад на «Додати модуль».
- [ ] Коміт: `feat(0.31.0): каталог модулів і «Свій модуль» із запитом агенту`.

### Task 4: «В Figma» — вимикач простору

**Файли:** Modify `app/serve.py` (`POST /api/space-tool`, `tools` у `GET /api/modules`), `app/spaces.py` (читання/запис
`tools` у `space.json`, якщо запис простору живе там), `app/bar-model.js`, `app/shell-palette.js`, `app/modules-grid.js`,
`app/connections-view.js`, `app/app.js`, `app/i18n.js`. Tests: Python (новий `tests/test_space_tools.py`), юніт,
живий кейс.

- [ ] `space.json`: `"tools": {"figma": false}`; відсутній ключ/об'єкт = увімкнено. Лише ключ `figma` дозволений (інший →
  400). Запис — тим самим шляхом, що `space-update` (атомарно, з тією ж перевіркою Origin/машинних маршрутів).
- [ ] `GET /api/modules` → `tools: {figma: true|false}`.
- [ ] Сітка: картка «В Figma» (роль «Інструменти», іконка `figma`), стан «Увімкнено»/«Вимкнено»; вимкнено → кнопка
  «Увімкнути» на картці; увімкнено → «⋯ → Вимкнути» (питання в картці з наслідком «Кнопки «В Figma» в смузі нема.»).
  Без шухляди.
- [ ] Смуга й ⌘K: стан `figmaOff` (з `tools.figma === false` поточного простору) → кнопки `figma` в `bar-model` і пункту
  ⌘K нема. Зміна простору — перечитати.
- [ ] Тексти: `roleTools` «Інструменти»/«Tools», `toolOn` «Увімкнено»/«On», `toolOff` «Вимкнено»/«Off», `toolEnable`
  «Увімкнути»/«Turn on», `toolFigmaNone` «Кнопки «В Figma» в смузі нема.»/«No «To Figma» button in the bar.».
- [ ] Тести: Python — запис/читання, невідомий інструмент → 400, відсутній ключ = увімкнено, неявний простір → 400/помилка
  як у `space-update`; юніт — `bar-model` без `figma` при `figmaOff`, палітра без пункту; живий — вимкнути на картці →
  смуга макета без кнопки «В Figma»; увімкнути → кнопка є.
- [ ] Коміт: `feat(0.31.0): «В Figma» вмикається й вимикається в модулях простору`.

### Task 5: AGENTS.md — генератор і API

**Файли:** Create `app/agents_md.py`, `app/templates/agents.md`, `tests/test_agents_md.py`. Modify `app/serve.py`
(маршрути), майстер нового простору (де створюється тека простору — `spaces.py`/`serve.py` `space-new`).

- [ ] Шаблон `app/templates/agents.md` (англійською), єдина підстановка — `{version}` (у маркері begin). Блок НЕ залежить
  від компʼютера (спека §4): жодних абсолютних шляхів, імені користувача, імені простору. Шляхи установки — як
  `<deai>/bin/inbox.py`, `<deai>/docs/modules/authoring.md` + рядок, як дізнатись `<deai>`: `GET
  http://127.0.0.1:8765/api/agents-md?space=<id>` → `paths.deai` (або Settings → AGENTS.md). Зміст — розділи спеки §4.
  Перший рядок блоку — маркер begin, останній — `<!-- deai:end -->`.
- [ ] `agents_md.py`:
  ```python
  BEGIN_RE = re.compile(r'^<!-- deai:begin v(?P<v>[0-9.]+)[^\n]*-->$', re.M)
  END = '<!-- deai:end -->'
  def render_block(*, version) -> str                      # з маркерами, закінчується '\n'; без машинних даних
  def split(text) -> tuple[str | None, str, str | None]    # (block|None, own, file_version|None)
  def status(space_dir, *, version) -> dict                # {path, exists, hasBlock, outdated, newer, version, fileVersion, block, own}
  def write(space_dir, *, version) -> dict                 # створює/оновлює; атомарно; newer → відмова (ValueError 'newer')
  ```
  - `newer` = версія файла > поточної (semver, порівняння кортежами цілих). `outdated` = `hasBlock` і НЕ `newer` і версія
    файла < поточної і текст блоку без рядка begin ≠ згенерований без рядка begin. Файла нема / блоку нема →
    `outdated: False`, клієнт показує «Створити» / «Оновити з шаблону» за `exists`/`hasBlock`.
  - Маршрут додає `paths: {deai, inbox, authoring}` — абсолютні шляхи ЦІЄЇ установки (лише у відповіді, не у файлі).
  - Блоку нема, а файл є → новий блок + `'\n'` + увесь старий текст (байт-у-байт).
  - Блок є → замінюється лише він; текст до блоку й після — байт-у-байт.
  - Атомарно: `tempfile.NamedTemporaryFile(dir=space_dir, delete=False)` → `os.replace`; виняток → тимчасовий файл прибрати,
    старий файл цілий.
- [ ] Маршрути: `GET /api/agents-md?space=<id>`, `POST /api/agents-md {space}`. Неявний простір / без теки → 409
  `{error:'no-folder'}`. Версія — та сама, що `/api/update` `current`. Origin/машинні маршрути — як `space-update`.
- [ ] Майстер нового простору: після створення теки — `agents_md.write(...)` (помилка запису AGENTS.md не валить створення
  простору — лише лог).
- [ ] Тести (`tests/test_agents_md.py`): render містить маркери й `<deai>/bin/inbox.py`; render НЕ містить `/Users/`,
  `/home/`, `C:\\`, домашньої теки чи теки установки (дві різні установки/`DEAI_HOME` → байт-у-байт однаковий блок);
  `newer` (файл 9.9.9) → не outdated, `write` відмовляє, файл цілий; write на порожній теці; оновлення зберігає текст
  до і після блоку байт-у-байт (з CRLF і без кінцевого `\n` у «Ваше»); файл без маркерів; outdated за вмістом (змінена версія
  при незмінному тексті → не outdated); збій `os.replace` (patch) → старий файл цілий, тимчасових файлів нема;
  **кожна команда шаблону існує**: `bin/inbox.py` містить підкоманду `resolve` і прапорці `--task`, `--reason`; кожен
  `/api/...` з шаблону є в `app/serve.py`; маршрути GET/POST (через наявний харнес serve-тестів), 409 для неявного простору;
  `space-new` створює AGENTS.md.
- [ ] Коміт: `feat(0.31.0): AGENTS.md простору з шаблону Deai — генератор і API`.

### Task 6: AGENTS.md — розділ у Налаштуваннях

**Файли:** Create `app/agents-view.js`, `tests/agents-view.test.mjs`. Modify `app/app.js`, `app/styles.css`, `app/i18n.js`.
Live: `tests/live/agents-md.test.mjs` (новий).

- [ ] Розділ `agents`: `h1` + «Скопіювати» (`navigator.clipboard`, тост «AGENTS.md скопійовано») + «Оновити з шаблону»
  (активна лише при `outdated` або `exists && !hasBlock`); плашка `.note` при `outdated`: «Шаблон Deai {v} новіший за цей
  файл ({fv}).» + кнопка; `newer` → плашка «Цей блок записав новіший Deai ({fv}) — оновіть Deai.», «Оновити з шаблону»
  неактивна; нема файла → «AGENTS.md ще нема» + «Створити»; `409 no-folder` → «У цього простору нема теки».
  Переглядач `.ag`: `.ag-bar` (шлях моно + копіювати шлях), `.ag-part` «З шаблону · Deai {v}» (`pre` блоку), `.ag-part.ag-own`
  «Ваше · не чіпається» (`pre` own; порожнє «Ваше» — частину не показувати).
- [ ] Після «Оновити»/«Створити» — тост «AGENTS.md оновлено · ваші нотатки на місці» / «AGENTS.md створено».
- [ ] Крапка в навігації (`agentsOutdated`) — з того самого GET (робиться при вході на сторінку налаштувань).
- [ ] Юніт: view для 6 станів (нема файла, без блоку, актуальний, застарілий, новіший, no-folder); екранування вмісту.
- [ ] Живий: фікстура простору з AGENTS.md, де блок старий і є «Ваше» → плашка є, крапка в навігації → «Оновити» → файл
  на диску: «Ваше» байт-у-байт, блок новий, плашки нема; простір без файла → «Створити» → файл є.
- [ ] Коміт: `feat(0.31.0): розділ AGENTS.md у Налаштуваннях`.

### Task 7: Простір — назва, колір, тека; колір фарбує вікно

**Файли:** Modify `app/styles.css` (токени), `app/app.js` (`data-space-color` на `<html>`), `app/connections-view.js` або
новий `app/space-view.js`, `app/i18n.js`, `tests/css-guards.test.mjs`. Live: кейс у `tests/live/settings-nav.test.mjs`.

- [ ] Токени поверхонь у `:root` → oklch від `--sp-h` (відтінок) і `--sp-k` (множник хроми). Значення L/C — з теперішніх hex
  (контролер виміряв, відтінок усіх ≈162):
  ```css
  --sp-h:162;--sp-k:1;
  --s0:oklch(.2455 calc(.016*var(--sp-k)) var(--sp-h));--s1:oklch(.3099 calc(.0163*var(--sp-k)) var(--sp-h));
  --s2:oklch(.3449 calc(.0169*var(--sp-k)) var(--sp-h));--s3:oklch(.386 calc(.0175*var(--sp-k)) var(--sp-h));
  --s4:oklch(.439 calc(.015*var(--sp-k)) var(--sp-h));--line:var(--s3);--line2:oklch(.4713 calc(.0157*var(--sp-k)) var(--sp-h));
  --hi:oklch(.9745 calc(.0066*var(--sp-k)) var(--sp-h));--mid:oklch(.8595 calc(.0103*var(--sp-k)) var(--sp-h));
  --dim:oklch(.7454 calc(.0123*var(--sp-k)) var(--sp-h));--lo:oklch(.5601 calc(.0132*var(--sp-k)) var(--sp-h));
  --sel:oklch(.9299 calc(.0101*var(--sp-k)) var(--sp-h));--sel-hover:oklch(.9696 calc(.005*var(--sp-k)) var(--sp-h));
  --on-sel:var(--s0);--on-hi:var(--s0);--sel-text:oklch(.9 calc(.0184*var(--sp-k)) var(--sp-h));
  --sel-tint:color-mix(in oklch,var(--sel) 12%,transparent);--sel-tint-2:color-mix(in oklch,var(--sel) 26%,transparent);
  :root[data-space-color="space-2"]{--sp-h:240;--sp-k:1.35} /* 3:80 1.35 · 4:30 1.3 · 5:300 1.35 · 6:200 1.35 */
  ```
  `--sel-ink`, `--ok/--bad/--open`, світлий контент (`--bg`, `--card`…) — без змін. Інші літерали з зеленим тоном у
  styles.css (`rgba(26,35,30,…)` тощо) — лишити (поза межами).
- [ ] `app.js`: при кожній зміні поточного простору (`applySpaceMeta`, `afterSpaceChange`, старт) —
  `document.documentElement.dataset.spaceColor = space.color` (невідомий → `space-1`). `<meta name="theme-color">` —
  обчислений `--s0`.
- [ ] Розділ `space`: «Назва» (`input#sp-name`, Enter/blur → `space-update`), «Колір простору» (`role="radiogroup"`, 6
  `.sw` з мініатюрою `.sw-pv` у відтінку свого кольору, назва `spaceColorName(n)`, вибір → `space-update` одразу),
  «Тека» (`.path` моно + «Скопіювати шлях»). Неявний простір — лише «Назва» недоступна? — як зараз у діалозі.
- [ ] Тексти: `spName` «Назва»/«Name», `spColorH` «Колір простору»/«Space colour», `spFolder` «Тека»/«Folder»,
  `spCopyPath` «Скопіювати шлях»/«Copy path», `spPathCopied` «Шлях скопійовано»/«Path copied».
- [ ] CSS-страж (`tests/css-guards.test.mjs`): `--s0…--s4`, `--line2`, `--hi`, `--mid`, `--dim`, `--lo`, `--sel` визначені через
  `var(--sp-h)`; для `space-1` перерахунок oklch→sRGB (функція в тесті) дає hex у межах ±2 на канал від старих
  (`#1A231E #29332E #323C36 #3C4741 #4B5550 #545E58 #F3F8F5 #CBD3CF #A6AFAA #6E7772 #E2EAE6`); кожен `space-N` має правило з
  `--sp-h`, рівним відтінку `--space-N`.
- [ ] Живий: колір «Фіолетовий» у розділі → обчислений фон `.bar`/смуги змінився (hue ≈300), фішка простору — фіолетова;
  повернути «Зелений» → фон дорівнює початковому.
- [ ] Коміт: `feat(0.31.0): колір простору фарбує вікно; розділ «Простір»`.

### Task 8: Застосунок — Загальне, Оновлення, Гарячі клавіші

**Файли:** Modify `app/shell-palette.js` (дані клавіш → масив `KEYS`), `app/app.js`, `app/update-view.js`/`update-model.js`
(повторне використання), `app/pwa.js` (лише експорт, якщо треба), `app/i18n.js`, `app/styles.css`. Tests: юніт + живий кейс.

- [ ] `KEYS` — один масив `[{group:'general'|'layout', labelKey, kbd}]`; `keysHTML()` (аркуш `?`) і розділ `keys` малюють
  з нього. Наявний тест «кожна клавіша має живий обробник» має читати `KEYS`.
- [ ] `app`: рядки `.row` у `.rows`: «Мова інтерфейсу» — `.seg` `role="radiogroup"` «Українська | English» → той самий шлях,
  що ⌘K `langUk/langEn`; «Окреме вікно» — `canInstall()` → «Встановити» (`pwainstall`), `isStandalone()` → «Встановлено»,
  інакше рядок не малюємо.
- [ ] `upd`: «Deai Canvas {current}», рядок стану (`upSt_*`, або «остання перевірка {коли}» з `checked_at`), «Перевірити
  зараз» (`POST /api/update-check`, кнопка зайнята «Перевіряю…»), при `available` — «Оновити до {latest}» відкриває наявний
  діалог оновлення.
- [ ] Тексти: `appLang` «Мова інтерфейсу», `appWindow` «Окреме вікно», `appWindowLead` «Deai Canvas як застосунок, без вкладок
  браузера», `appInstall` «Встановити», `appInstalled` «Встановлено», `updCheckNow` «Перевірити зараз», `updChecking`
  «Перевіряю…», `updTo(v)` «Оновити до {v}», `updLast(when)` «остання перевірка {when}» (en — дзеркально).
- [ ] Юніт: `KEYS` ↔ аркуш (той самий набір), розділ `keys` містить кожен `kbd`; розділ `upd` для станів ok/available/offline.
- [ ] Живий: «Загальне» → English → інтерфейс англійською (заголовок розділу «General»), назад; «Оновлення» → «Перевірити
  зараз» шле `POST /api/update-check` (фікстурний сервер з вимкненим мережевим апдейтером — як у наявних живих тестах
  оновлення); «Гарячі клавіші» — `⌘K` присутній.
- [ ] Коміт: `feat(0.31.0): група «Застосунок» — мова, окреме вікно, оновлення, гарячі клавіші`.

### Task 9 (контролер): документи й реліз

- [ ] `docs/modules/authoring.md`: «Підключення» → «Налаштування → Модулі», «Довіритись…» → «Довірити».
- [ ] README: розділ налаштувань/модулів, AGENTS.md; статус 0.31.0.
- [ ] CHANGELOG `[0.31.0] — DD.MM.2026`, `package.json` 0.31.0.
- [ ] Фінальний ревʼюер (Sonnet) на весь діф `main..feat/settings-e`; релізний прогін: JS юніт, commenter, inspector-core,
  Python (tests/bin/app), УСІ живі файли по одному; заборонений список.

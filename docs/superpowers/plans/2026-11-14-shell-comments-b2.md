# Реліз 0.27.0 «Claude і команда разом» (етап Б2) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** в одній панелі коментарів — і піни для Claude (локальний файл задачі), і командні (модуль ролі `comments`); адресат обирається у формі піна; Claude бере командний коментар лише за дорученням (`meta.assignee = "claude"`); дизайнер дізнається про нові командні (розділ, бейдж острівця, тост, число в дереві й на вкладках).

**Architecture:** у робочому місці (`/commented?…&host=1`) з командним постачальником сторінка піднімає ОДИН шар коментатора на комбінованому сховищі `app/vendor/dual-store.js` (локальний адаптер + адаптер модуля); адресат піна = сховище, на копіях для коментатора — службове `_aud`. Коментатор у режимі хоста з ≥ 2 аудиторіями малює чипи адресата у формі, фарбує пін за `_aud` і вміє `setMeta`. Агентові правило одне — `for_agent(comment, store)` у `serve.py` (його кличуть `inbox.py`, `state.py`, `/comments`). «Нові» рахує оболонка: набір побачених id у localStorage; для інших вкладок — легка необовʼязкова функція ролі `recent` через `GET /api/comment-news`.

**Tech Stack:** ванільний ES-модульний JS (`node:test`), esbuild 0.25.12 (лише збірка коментатора), Python 3 stdlib (`unittest`, 3.9-сумісний), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-13-shell-comments-design.md`, розділ «Б2» (погоджено власником 13.11.2026). Принципи: `PRODUCT.md` (принцип 6 — коментатор окремий продукт). **ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач.**

**Рівень строгості — повний:** на кожну задачу — виконавець і ревʼюер (спершу відповідність задачі, потім якість); кожна нова перевірка доводиться мутацією (один рядок → червоніє → відновлено; у звіті — що саме мутовано); після T12 — фінальне ревʼю всієї гілки, релізний прогін, перевірка проти живого канвасу (T13, контролер). Пуш — лише з дозволу власника.

Базова лінія на `8cdf802` (= 0.26.0): JS 2113 pass; Python 5084 / bin OK / app 170; живі 537. T1 записує числа першого прогону у звіт.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Робоче дерево: `<repo>` = `deai-canvas-dev`, гілка `feat/shell-comments-b2` (від `main` 8cdf802). Коміти лише так, з переліком шляхів; новий файл спершу `git add -- <шлях>`:
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`; ніколи `--amend`, `stash`, `reset`, `checkout` інших гілок. У zsh список шляхів у змінній розгортати як `${=P}`.
- ⛔ Живий канвас працює з ІНШОГО дерева (`deai-canvas`, порт 8765). Його не чіпаємо: ні файлів, ні процесу, ні порту.
- ⛔ У жоден комітований файл не пишемо справжніх імен людей, хостів, імен користувачів машини, ключів, шляхів зі scratchpad чи тимчасових тек.
- Правки наявних файлів — точкові (`Edit`); нові файли — `Write`.

**Прогони й середовище**

- JS (після кожної задачі): `node --test tests/*.test.mjs && node --test commenter/test/*.test.mjs && node tests/inspector-core.test.mjs`.
- Python (кожна задача, що чіпає `.py`): під тимчасовим `HOME`, без `DC_TASKS_FILE`/`DEAI_HOME`, без `.pyc`:
  `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'` (і так само `-s bin`, `-s app`). Окремий файл: `… python3 -B -m unittest tests.test_comments_agent`.
- Живі — по одному файлу, ПОСЛІДОВНО:
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`.
- Чекати фоновий прогін — лише за PID (`while kill -0 $PID 2>/dev/null; do sleep 10; done`) або за рядком у лозі. ⛔ Ніколи `while pgrep -f …` (збігається сам із собою й не закінчується ніколи).
- Мережі в тестах нема (лише 127.0.0.1); порти 8765/4317 не чіпаються; справжні `~/.deai`, `~/deai-work`, `~/deai-published`, `~/.claude/pipeline-feedback/`, `~/.gitconfig`, справжній `tasks.json` не змінюються; процеси зупиняємо лише за PID (ніколи `pkill -f`/`killall`).
- ≤ 1 виконавець одночасно. Тести, які ламає задача, правляться в ТІЙ САМІЙ задачі й згадуються у звіті одним рядком із причиною. Тест не можна «підігнати» під нову поведінку мовчки: у звіті — що він охороняв і де ця охорона тепер.
- Кириличних рядкових літералів у `app/*.js` (крім `i18n.js`) бути не може — `tests/i18n-literals.test.mjs`; тексти лише через `t()`. Іконки — лише з `app/icons.js` (`tests/icons.test.mjs`). Класи `pin`, `cp`, `cluster`, `cbadge` у `app/*.js` заборонені (`tests/principle6.test.mjs`) — в оболонці лише `cmt-*`, `isl-*`, `tab-*`, `row-*`.
- CSS — лише наявні токени (`tests/css-guards.test.mjs`); бурштин — `var(--open)`.
- Збірка коментатора після кожної правки `commenter/src/`: `cd commenter && npm ci && npm run build && cd ..` — оновлює `app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`, `commenter/build-stamp.json`; охоронець `tests/commenter-stamp.test.mjs` мусить бути зеленим. Усі три файли — у тому ж коміті, що й зміна джерела.

---

## Поправки до спеки (звірено з кодом на `8cdf802`; мають перевагу)

1. **`_aud` переживає `stripRuntime`.** Спека каже «`stripRuntime` його знімає», але тоді комбіноване сховище не дізналось би адресата в `save()`. Насправді `stripRuntime` (`commenter/src/comment-layer.js`) знімає лише `_el`/`_pending` — так і лишається. `_aud` не потрапляє на диск і в базу, бо: комбіноване сховище знімає його перед передачею в під-сховища; локальний адаптер (`clean`) і `supabase-comments` (`commentToRow`) пишуть лише свій білий список; сервер у `POST /api/local-comments` вичищає `_el`, `_pending` **і `_aud`**.
2. **Маркер «бачив» — НАБІР id, а не `ts`.** `ts` коментатора — локальний час автора з точністю до хвилини (`nowStamp`: `DD.MM.YYYY HH:MM`), а команда в різних поясах (UTC+1 і UTC+2): маркер за `ts` губив би нові коментарі колег зі «старішим» поясом і плутав коментарі однієї хвилини. Тому `localStorage['dc-seen:<простір>:<задача>'] = {"v":1,"ids":[…]}` (останні 1000). Перший погляд на задачу (маркера нема) — усе наявне вважається баченим (без зливи «нових»). Звідси ж: `recent(ctx, channel)` — **без `since`**; маршрут — `GET /api/comment-news?task=<id>` → `{supported, items:[{id, ts, author, status:'open', version}]}`; рахує клієнт.
3. **Комбіноване сховище — лише з `host=1` і командним постачальником.** Сторінка `/commented` без `host` (відкрита напряму, еталони `tests/fixtures/comments-role/`) — байт-у-байт як у 0.26.0, параметр `ch` там діє як і раніше. З `host=1` параметр `ch` не діє: є постачальник (навіть зламаний) — комбінований сніпет; нема — локальний із `host`, як у Б1.
4. **Падіння командного не ховає коментатора.** У комбінованому сніпеті теги файлів адаптера модуля — БЕЗ `onerror`-банера; адаптер не завантажився / `create` кинув / сховище без `load`/`save` / сервер не зібрав конфіг (`ModuleError`) → `DeaiDualStore({teamDown: <причина>})`, піднімається лише локальне, аудиторія в коментатора одна (чипів нема). Банер `__clDown` лишається лише для падіння самого шару коментатора чи локального адаптера. Оболонка читає причину з `L.store.teamDown` (той самий origin) і показує смугу в панелі.
5. **Скріншот локального піна не їде в командне сховище.** Коментатор кличе `this.store.uploadShot(id, shot, comment)` (третій аргумент — новий); комбіноване сховище передає виклик модулю ЛИШЕ для `comment._aud === 'project'`, інакше `null` (скріншот лишається в `meta.shot`, як у локальних пінів завжди). Без третього аргументу — `null`. Інакше скрін фідбеку для Claude лягав би в публічний кошик Storage колег.
6. **Комбіноване сховище не чіпає під-сховища без змін.** `save(list)` порівнює нормалізовану частину кожного адресата з тим, що під-сховище зараз тримає (`load()` чи власна тінь після запису), і кличе `save` під-сховища лише коли частина змінилась. Без цього будь-яка дія з локальним піном переписувала б увесь командний список (у будь-якому модулі, не лише Supabase).
7. **Тінь командної частини.** `supabase-comments` після запису не сповіщає підписників (лише realtime згодом). Локальний адаптер сповіщає синхронно ПІД ЧАС `save`, і обʼєднання тоді взяло б СТАРИЙ командний кеш — доручення «відкочувалось» би на екрані до realtime. Тому комбіноване сховище тримає тінь щойно відданої командної частини, поки командне сховище не заговорить само.
8. **`supabase-comments`: запис різницею + realtime лише свого каналу.** (а) `save` шле upsert лише рядків, що відрізняються від останнього прочитаного/записаного знімка; порівняння — канонічним JSON із сортованими ключами (Postgres `jsonb` переставляє ключі `meta`, і наївне порівняння вважало б зміненим кожен рядок); нема змін — нема запиту. (б) Подія realtime перечитує канал лише коли стосується його: INSERT/UPDATE — `payload.new.project_id === channel`; DELETE (несе лише ключ) — id є в нашому кеші; незнайома форма — перечитати. Причина: з Б2 кожна сторінка задачі ЛІГИ підписана на командний канал, а підписка — на всю таблицю; без фільтра кожен коментар будь-де давав би `select *` (зі знімками HTML) у кожному відкритому вікні — урок квоти трафіку 21.10.2026. Версія модуля → 1.3.0.
9. **Нумерація.** У комбінованому режимі коментатор без `local:true`: номери на всіх пінах. Новий пін бере `max(seq)` по обох сховищах + 1, тож нові номери унікальні; старі номери локальних і командних незалежні (L#3 і P#3 можуть співіснувати) — картка показує адресата, `#N` знаходить обидва. Колір піна — `audiences[i].color` (локальний — `#7C6CF0`, як був); командний — колір коментатора за замовчуванням.
10. **Перемикання каналу в робочому місці зникає повністю:** `commentMode`, `effMode`, `setAudience`, приймач `dc-audience`, `BAR_ACTIONS.aud`/`cmtch`, пункти палітри `aud-local`/`aud-project` (і `effectiveCommentMode`, якщо більше ніким не вживається), `&ch=` у `frame.src`. Аварійний вихід палітри «до локального» зайвий: падіння командного більше не валить коментатора (поправка 4). Живий `tests/live/comment-audience.test.mjs` видаляється в T11 з переліком, де тепер кожна його охорона.
11. **«Огляд»** бере дві конфігурації наявного `/api/comment-config` (`ch=local` і, коли є командний постачальник, `ch=project`) і складає те саме `DeaiDualStore` на клієнті; сервер `/api/comment-config` не змінюється. `env.channel()` → `'dual'`/`'local'` (ключ інстансу); `projectId` — локальний ключ (`<задача>/local`).
12. **Пам'ять вибору адресата:** ключ `localStorage['dc-cmt-aud']` (спільний для рамки й оболонки — той самий origin). Коментатор отримує `host.defaultAudience()` і `host.onAudiencePick(id)`; рамці їх дає `HOST_ARG` (`serve.py`), «Огляду» — оболонка. Пару «ключ у Python ↔ ключ у `app.js`» приколює тест.
13. **Розділ «Нові від команди»** — набір `cmtFresh` поточного відкриття панелі: нові на момент відкриття + ті, що прийшли, поки вона відкрита. Маркер «бачив» посувається одразу (і на відкриття, і на прихід при відкритій панелі); `cmtFresh` чиститься при закритті панелі, зміні задачі чи виду. Нові картки не дублюються в «Відкритих».
14. **Тост** — стійка плашка `notice('cmt-news', …, [{act:'cmtshownew', label, run}])`, лише коли панель ЗАКРИТА і лише для того, що з'явилось у знімку під час сесії (`arrived` відносно попереднього знімка; перший знімок після завантаження — не «під час сесії»). «Показати» → відкрити панель, вибрати найновішу, `focus(id)`.
15. **«Не я»** — `author !== localStorage['comment-layer:user']` (імʼя, яке пише коментатор, той самий origin); імені нема — «мого» нема. Власний пін однаково не стає «новим»: створюється лише при відкритій панелі (режим = панель, Б1), а тоді маркер посувається одразу.
16. **Число в дереві** — нове поле рядка `news` (бурштинове), а не наявне `count` (воно про склад теки). Сторінку піна дає `pinTarget(c).page` з `app/overview-pins.js` (та сама логіка, що на «Огляді»).
17. **Вкладки:** опит `GET /api/comment-news` для відкритих вкладок, крім активної (активна — острівець), лише вкладок поточного простору, лише коли вікно видиме; одразу при зміні складу вкладок і на `focus` вікна, далі раз на 90 с. Вкладки інших просторів — без числа (маршрут бачить лише задачі простору запиту).
18. **Урок Б1 «ітерацію закриття — окремим полем» розглянуто й НЕ беремо в Б2:** для командних пінів окреме поле вимагало б PATCH усього `meta` (урок `patch_project_pin`: PostgREST міняє `jsonb` цілком, ризик затерти `shot`/`shotUrl`) або колонки (не-ціль спеки). Лишається правило Б1 для обох сховищ (`byClaude = resolvedV != null && resolveReason !== 'resolved manually'`); T8 додає тест на командний пін, закритий агентом і вручну.

---

## Структура файлів

| Файл | Що робить | Задача |
|---|---|---|
| `app/serve.py` (`for_agent`, `/comments`), `bin/inbox.py`, `bin/state.py`, `tests/test_comments_agent.py` | правило агента, `--all` | T1 |
| `app/deai_modules.py`, `app/modules/supabase-comments/server.py`, `app/modules/supabase-comments/module.json`, `tests/fixtures/modules/memo-comments/server.py`, `app/serve.py` (`agent_news`, `ProjectComments.recent`, `/api/comment-news`), `tests/test_supabase_comments.py`, `tests/test_comments_agent.py` | роль `recent` і маршрут | T2 |
| `app/modules/supabase-comments/adapter.js`, `tests/supabase-comments-adapter.test.mjs` | запис різницею, realtime свого каналу | T3 |
| `commenter/src/comment-layer.js` (+ збірка), `app/serve.py` (`_local_comments_post`), `tests/test_serve.py`, `tests/live/commenter-host.test.mjs` | чипи адресата, колір, `setMeta`, `uploadShot(…, c)` | T4 |
| `app/vendor/dual-store.js` (новий), `tests/dual-store.test.mjs` (новий) | комбіноване сховище | T5 |
| `app/serve.py` (`DUAL_COMMENT_SNIPPET`, `HOST_ARG`, `_commented`), `app/i18n.js`, `tests/test_comments_role.py`, `tests/test_publish_module.py` | комбінований сніпет рамки | T6 |
| `app/overview-comments.js`, `app/index.html`, `tests/overview-comments-module.test.mjs` | «Огляд» на комбінованому сховищі | T7 |
| `app/comments-model.js`, `app/comment-news.js` (новий), `app/comments-view.js`, `app/island.js`, `app/tabs-model.js`, `app/tabs-view.js`, `app/shell-panel.js`, `app/i18n.js`, `tests/comments-model.test.mjs`, `tests/comment-news.test.mjs` (новий), `tests/comments-view.test.mjs`, `tests/island.test.mjs`, `tests/tabs-*.test.mjs`, `tests/shell-panel*.test.mjs` | чисті модулі | T8 |
| `app/app.js`, `app/shell-palette.js`, `app/styles.css`, `app/spaces-model.js`, тести палітри й еталони | проводка в оболонці | T9 |
| `app/app.js` | числа на вкладках | T10 |
| `tests/live/_memo.mjs` (новий), `tests/live/comments.test.mjs`, `tests/live/comments-team.test.mjs` (новий), `tests/live/comment-audience.test.mjs` (видалити), інші `tests/live/*.test.mjs` | живі сценарії й міграція | T11 |
| `CHANGELOG.md`, `package.json`, `README.md`, `commenter/README.md`, `docs/modules/comments.md`, `app/modules/supabase-comments/README.md` | реліз 0.27.0 | T12 |

---

### Task 1: Правило агента `for_agent`, `inbox.py --all`, `state.py`, `/comments`

**Files:**
- Modify: `app/serve.py` (біля `class ProjectComments`; метод `_comments`)
- Modify: `bin/inbox.py` (`cmd_list`, `build_parser`, `_main`, докстрінг модуля)
- Modify: `bin/state.py` (`_team_comments`)
- Test: `tests/test_comments_agent.py`

- [ ] **Step 1: Базова лінія.** `node --test tests/*.test.mjs 2>&1 | grep -E "^# (tests|pass|fail)"` і три Python-прогони — числа у звіт.

- [ ] **Step 2: Тести (червоні).** У `tests/test_comments_agent.py`:
  - у `cl()` нічого не міняти — доручення задаємо через `meta`: допоміжна функція поруч із `cl`:
    ```python
    def assigned(c):
        """Той самий пін, доручений Claude (`meta.assignee`, спека Б-Р6)."""
        c = dict(c)
        c['meta'] = {**c['meta'], 'assignee': 'claude'}
        return c
    ```
  - новий клас `ForAgentUnitTest(unittest.TestCase)`:
    ```python
    class ForAgentUnitTest(unittest.TestCase):
        def test_local_pins_are_always_for_the_agent(self):
            self.assertTrue(serve.for_agent({'id': 'a', 'meta': None}, 'local'))
            self.assertTrue(serve.for_agent({'id': 'a'}, 'local'))

        def test_a_team_pin_is_for_the_agent_only_when_assigned_to_claude(self):
            self.assertTrue(serve.for_agent({'meta': {'assignee': 'claude'}}, 'project'))
            for meta in (None, {}, {'assignee': 'Claude'}, {'assignee': 'olena'}, {'assignee': ['claude']}, 'claude'):
                self.assertFalse(serve.for_agent({'meta': meta}, 'project'), meta)
            self.assertFalse(serve.for_agent('not a pin', 'project'))
    ```
  - у `InboxModuleTest` — нові тести:
    ```python
    def test_by_default_inbox_shows_only_team_pins_assigned_to_claude(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [assigned(cl('c0ffee01-aaaa', 'Доручене', seq=7)), cl('c0ffee02-bbbb', 'Чуже', seq=8)])
        rc, out, err = self.inbox([])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('-- ПРОЄКТ · доручені Claude (модуль memo-comments) --', out)
        self.assertIn('Доручене', out)
        self.assertNotIn('Чуже', out)
        self.assertIn('ще 1 відкритих командних без доручення Claude — усі: python3 bin/inbox.py --all', out)
        self.assertIn('Разом до відпрацювання: 0 локальних + 1 проєктних', out)

    def test_all_shows_every_team_pin_exactly_as_before(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [assigned(cl('c0ffee01-aaaa', 'Доручене', seq=7)), cl('c0ffee02-bbbb', 'Чуже', seq=8)])
        rc, out, _ = self.inbox(['--all'])
        self.assertEqual(rc, 0, out)
        self.assertIn('-- ПРОЄКТ (колеги + історія, модуль memo-comments) --', out)
        self.assertIn('Доручене', out)
        self.assertIn('Чуже', out)
        self.assertNotIn('без доручення', out)

    def test_resolve_still_finds_an_unassigned_team_pin(self):
        """`resolve` шукає серед УСІХ: агент, що бачив пін через `--all`, мусить уміти його закрити."""
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee02-bbbb', 'Чуже')])
        rc, out, _ = self.inbox(['resolve', 'c0ffee02', '--reason', 'зроблено'])
        self.assertEqual(rc, 0, out)
        self.assertIn('✓ c0ffee02 закрито (проєкт)', out)
    ```
  - тест для `state.py` (знайти наявний тест лічильника `state` у файлі — пошук `state.` — і за його зразком): засіяти один доручений і один недоручений відкриті командні піни → рядок містить `+ 1 проєктних (доручено Claude); ще 1 командних без доручення`.
  - тест маршруту `/comments` (за зразком наявного тесту маршруту в цьому файлі чи в `tests/test_comments_role.py` — пошук `'/comments'`): типово в `comments` лише доручений і `hidden == 1`, `all is False`; з `?all=1` — обидва й `all is True`, без `hidden`.
  Run: `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest tests.test_comments_agent` → FAIL (`for_agent` нема, рядків нема).

- [ ] **Step 3: `for_agent` у `app/serve.py`** — одразу ПЕРЕД `class ProjectComments:`:
  ```python
  #: Хто бере командний коментар (Deai 0.27.0, спека Б-Р6): лише доручений Claude — `meta.assignee == 'claude'`.
  ASSIGNEE_CLAUDE = 'claude'


  def for_agent(c, store):
      """Чи цей пін — робота Claude. `store`: `'local'` (локальний файл задачі — завжди так) чи `'project'` (командний канал —
      лише доручений: `meta.assignee == 'claude'`). ОДНЕ правило для `bin/inbox.py`, `bin/state.py` і маршруту `/comments`
      (спека Б2.3): три копії розійшлися б у числах. Приймає обидві форми піна (CommentLayer і рядок REST): `meta` в них однакове."""
      if store == 'local':
          return True
      meta = c.get('meta') if isinstance(c, dict) else None
      return isinstance(meta, dict) and meta.get('assignee') == ASSIGNEE_CLAUDE
  ```

- [ ] **Step 4: `/comments`** (`def _comments` у `app/serve.py`): після `channel = …` прочитати `show_all = q.get('all', ['0'])[0] == '1'`; у `try` замінити тіло відповіді:
  ```python
              pins = pc.pins(task, tid, internal)
              # Б2.3: агентові — лише доручені командні (`for_agent`); `?all=1` — усі, як до 0.27.0.
              mine = pins if show_all else [p for p in pins if for_agent(p, 'project')]
              body = {'project': project, 'comments': mine, 'all': show_all}
              if not show_all:
                  body['hidden'] = len(pins) - len(mine)
              if isinstance(pins, ModulePins) and pins.note():
                  body['warning'] = pins.note()
              self._send_json(body)
  ```
  Докстрінг методу — один рядок про `?all=1`.

- [ ] **Step 5: `bin/inbox.py`.** Імпорт `for_agent` разом із рештою з `serve`. `cmd_list(where=False, task_id=None, show_all=False)`; у гілці `elif proj_err is None:` (замість наявних трьох рядків):
  ```python
      elif proj_err is None:
          # Б2.3: типово — лише доручені Claude командні (`for_agent`); `--all` — усі, байт-у-байт як до 0.27.0.
          mine = proj if show_all else [p for p in proj if for_agent(p, 'project')]
          print(_newest_line(mine))
          if isinstance(proj, ModulePins) and proj.note():
              print(f'  ⚠ {proj.note()}')
          ext = show_pins(mine, 'проєкт', 'P', wmap)
          if not show_all:
              hidden = len([p for p in proj if p.get('status') != 'resolved' and not for_agent(p, 'project')])
              if hidden:
                  flag = f' --task {shlex.quote(tid)}' if task_id is not None else ''
                  print(f'  ще {hidden} відкритих командних без доручення Claude — усі: python3 bin/inbox.py{flag} --all')
  ```
  Заголовок секції: `print(f'\n-- ПРОЄКТ (колеги + історія, {source}) --' if show_all else f'\n-- ПРОЄКТ · доручені Claude ({source}) --')`. `--where` лишається на ПОВНОМУ `proj` (як було). У `build_parser` — `ap.add_argument('--all', action='store_true', help='усі командні коментарі, а не лише доручені Claude (як до 0.27.0)')`; `_main` → `cmd_list(where=a.where, task_id=a.task, show_all=a.all)`. `resolve` НЕ фільтрується. У докстрінгу модуля, пункт «ПРОЄКТ», — одне речення: типово лише доручені Claude (`meta.assignee`), `--all` — усі.

- [ ] **Step 6: `bin/state.py`** (`_team_comments`, гілка `pc.kind == 'module'`): імпорт `for_agent` з `serve`; рахувати
  ```python
              pins = pc.pins(task, tid)
              open_ = [p for p in pins if p.get('status') != 'resolved']
              n = len([p for p in open_ if for_agent(p, 'project')])
              k = len(open_) - n
  ```
  і повертати `n, f' + {n} проєктних (доручено Claude)' + (f'; ще {k} командних без доручення' if k else '') + (f' (⚠ {note})' if note else '')`. Решта гілок без змін.

- [ ] **Step 7: Наявні тести, що зламались** (очікувано: усі, що сіють недоручені командні піни й читають `inbox`/`state`/`/comments` без `--all`): правити в ТІЙ ЖЕ задачі одним із двох способів — `self.inbox(['--all'])` / `?all=1` там, де тест про форму виводу всіх пінів; `assigned(cl(…))` там, де тест про роботу агента. У звіті — перелік із причиною кожної правки.

- [ ] **Step 8: Прогін і мутації.** Три Python-прогони зелені. Мутації (кожна → червоно → відновити): (1) `for_agent` для `'project'` повертає `True`; (2) у `cmd_list` прибрати фільтр (`mine = proj`); (3) у `_team_comments` рахувати `n = len(open_)`.

- [ ] **Step 9: Commit** — `app/serve.py bin/inbox.py bin/state.py tests/test_comments_agent.py` (+ інші правлені тести): `feat(agent): Claude бере командний коментар лише за дорученням (for_agent, inbox --all)`.

---

### Task 2: Роль `recent` і маршрут `GET /api/comment-news`

**Files:**
- Modify: `app/deai_modules.py:108` (`ROLE_OPTIONAL_FUNCTIONS`)
- Modify: `app/modules/supabase-comments/server.py` (нова `recent`), `app/modules/supabase-comments/module.json` (`"version": "1.3.0"`)
- Modify: `tests/fixtures/modules/memo-comments/server.py` (нова `recent`)
- Modify: `app/serve.py` (`agent_news`, `ProjectComments.recent`, `_comment_news`, маршрут у `do_GET`)
- Test: `tests/test_supabase_comments.py`, `tests/test_comments_agent.py`, `tests/test_modules.py` (якщо там приколото склад `ROLE_OPTIONAL_FUNCTIONS` чи версію модуля)

- [ ] **Step 1: Тести (червоні).**
  - `tests/test_supabase_comments.py` (за зразком наявних тестів `list` — пошук `def test_list` / `'GET'`): `recent(ctx, 'dc/x')` шле ОДИН `GET` із запитом, що містить `project_id=eq.dc%2Fx`, `status=eq.open`, `select=id,ts,author,status,version:meta->>version`, `order=created_at.desc`, `limit=200`; у запиті НЕМА `html_snapshot`, `meta` цілком і `select=*`; відповідь `[{'id':'a','ts':'t','author':'o','status':'open','version':'2'}]` → той самий список; не список → `ModuleError`.
  - `tests/test_comments_agent.py`: (а) `serve.agent_news` — неправильний `id` (з `/`), дубль, `status:'resolved'`, не-обʼєкт пропускаються; `ts`/`author` з керівними символами очищені; `version` int → рядок; > 200 → 200; не список → `ModuleError`. (б) клас на `AgentEnv`: `enable_memo_in(plain)`, `seed(… [cl('c0ffee01-aaaa','Новий'), cl('c0ffee02-bbbb','Старе', status='resolved')])`, запит до маршруту `/api/comment-news?task=px` (тим самим способом, що наявні тести маршруту `/comments`) → `{'supported': True, 'items': [{'id':'c0ffee01-aaaa','ts':'19.10.2026 10:00','author':'Олена','status':'open','version':'2/me--welcome'}]}`; простір без постачальника → `{'supported': False, 'items': []}`; невідома задача → 404; `task=../x` → 400; модуль без `recent` (підмінити `fns` чи тимчасовий модуль без функції — як зручніше на наявних фікстурах) → `{'supported': False, 'items': []}`.
  Run → FAIL.

- [ ] **Step 2: `app/deai_modules.py`:** `ROLE_OPTIONAL_FUNCTIONS = {'vcs': ('validate', 'mirror_dir'), 'dashboard': ('open_comments',), 'comments': ('recent',)}` і в докстрінгу `class Module` після «`validate`, `mirror_dir` у `vcs`» дописати «, `recent` у `comments`».

- [ ] **Step 3: `supabase-comments/server.py`** — після `def list(...)`:
  ```python
  RECENT_ROWS = 200        # «нових» на вкладці більше не покажемо; найновіші — за `created_at`


  def recent(ctx, channel):
      """Відкриті коментарі каналу для лічильника «нових» (Deai 0.27.0, роль `comments`, необовʼязкова): лише `id, ts, author,
      status, version` — БЕЗ знімків HTML, скріншотів і `fp` (урок квоти трафіку 21.10.2026: опит вкладок іде раз на 90 с)."""
      channel = _need_text(ctx, channel, 'канал коментарів')
      query = (f'project_id=eq.{_quote(channel)}&status=eq.open'
               f'&select=id,ts,author,status,version:meta->>version&order=created_at.desc&limit={RECENT_ROWS}')
      try:
          status, payload = _request(ctx, 'GET', query, timeout=CALL_TIMEOUT_S, limit=MAX_SMALL)
      except _ResponseError as e:
          raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
      if not 200 <= status < 300:
          raise _fail(ctx, status, payload)
      rows = _json(payload)
      if not isinstance(rows, type([])):
          raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
      return [{'id': r.get('id'), 'ts': r.get('ts'), 'author': r.get('author'), 'status': r.get('status'),
               'version': r.get('version')} for r in rows if isinstance(r, dict)]
  ```
  (Якщо `MAX_SMALL` замалий для 200 рядків — взяти `MAX_BODY`, як `list`; рішення й причина — у звіт.) `module.json`: `"version": "1.3.0"`.

- [ ] **Step 4: Фікстура `memo-comments/server.py`** — після `resolve`:
  ```python
  def recent(ctx, channel):
      """Необовʼязкова функція ролі (Deai 0.27.0): відкриті коментарі без важких полів."""
      return [{'id': c.get('id'), 'ts': c.get('ts'), 'author': c.get('author'), 'status': c.get('status'),
               'version': (c.get('meta') or {}).get('version')}
              for c in list(ctx, channel) if isinstance(c, dict) and c.get('status') != 'resolved']
  ```
  (`list` тут — функція ролі цього файла, див. його шапку.)

- [ ] **Step 5: `app/serve.py`.** Після `def agent_pins(raw)`:
  ```python
  #: Скільки «нових» віддає `/api/comment-news` (і чекає від `recent` модуля).
  MAX_NEWS = 200


  def agent_news(raw):
      """Відповідь `recent` модуля → `[{id, ts, author, status: 'open', version}]` лише відкритих, ≤ `MAX_NEWS`. Не список —
      `ModuleError`. Поля — як у `agent_pin`: `id` за `_AGENT_ID` (інакше пропуск), однорядкові тексти без керівних символів."""
      if not isinstance(raw, list):
          raise deai_modules.ModuleError('module-error', message='the comments module must answer recent() with a list')
      out, seen = [], set()
      for c in raw[:MAX_NEWS * 4]:
          if not isinstance(c, dict) or c.get('status') == 'resolved':
              continue
          pid = c.get('id')
          if not isinstance(pid, str) or not _AGENT_ID.fullmatch(pid) or pid in seen:
              continue
          seen.add(pid)
          v = c.get('version')
          ver = str(v) if isinstance(v, int) and not isinstance(v, bool) else agent_line(v, 200)
          out.append({'id': pid, 'ts': agent_line(c.get('ts'), 40), 'author': agent_line(c.get('author'), 200),
                      'status': 'open', 'version': ver or None})
          if len(out) >= MAX_NEWS:
              break
      return out
  ```
  У `class ProjectComments` — після `pins`:
  ```python
      def recent(self, task, tid):
          """Відкриті командні коментарі каналу задачі для лічильника «нових» (`agent_news` відповіді необовʼязкової
          `recent(ctx, channel)` модуля); модуль без неї — `None` (вкладка просто без числа). Канал — той, у який пише рамка
          (`internal=False`)."""
          self._check()
          if self.prov.fn('recent') is None:
              return None
          return agent_news(self._module('recent', task, tid, False))
  ```
  Обробник (поруч із `_comments`):
  ```python
      def _comment_news(self):
          """`GET /api/comment-news?task=<id>` — легкі відкриті командні коментарі задачі для числа на вкладці (Deai 0.27.0,
          поправка 2 плану Б2: «нові» рахує клієнт за набором побачених id). Лише задачі простору запиту; модуль без `recent`
          чи простір без постачальника — `supported: false`, а не помилка."""
          q = parse_qs(urlparse(self.path).query)
          tid = q.get('task', [''])[0]
          if not NAME_RE.fullmatch(tid):
              self.send_error(400, 'bad task')
              return
          task = load_tasks().get('tasks', {}).get(tid)
          if not isinstance(task, dict):
              self._send_json({'ok': False, 'error': 'unknown task'}, status=404)
              return
          pc = ProjectComments(spaces.active_space())
          if pc.kind != 'module':
              self._send_json({'supported': False, 'items': []})
              return
          try:
              items = pc.recent(task, tid)
          except (OSError, deai_modules.ModuleError) as e:
              self._send_json({'supported': True, 'items': [], 'error': agent_line(str(e), 300)})
              return
          self._send_json({'supported': items is not None, 'items': items or []})
  ```
  У `do_GET` поруч із `/api/comment-config`: `if self.path.split('?')[0] == '/api/comment-news': self._comment_news(); return`.

- [ ] **Step 6: Прогін і мутації.** Python зелений. Мутації: (1) у `recent` модуля `select=*`; (2) у `agent_news` не пропускати `resolved`; (3) у `_comment_news` прибрати перевірку `pc.kind`.

- [ ] **Step 7: Commit** — `feat(comments): необовʼязкова роль recent і GET /api/comment-news (легкі нові без знімків)`.

---

### Task 3: `supabase-comments`: запис різницею й realtime свого каналу

**Files:**
- Modify: `app/modules/supabase-comments/adapter.js`
- Test: `tests/supabase-comments-adapter.test.mjs`

- [ ] **Step 1: Тести (червоні)** — на наявному фейку клієнта supabase у цьому тест-файлі (підглянути, як він ловить `upsert`/`select`/`channel().on()`; якщо фейк не віддає колбек `postgres_changes` — розширити його так, щоб тест міг викликати колбек із `payload`):
  1. `save` того самого списку, що прийшов з `select`, — НУЛЬ викликів `upsert`;
  2. змінено один пін (`meta.assignee`) — `upsert` рівно з ОДНИМ рядком (його `id`);
  3. база повернула `meta` з іншим порядком ключів (`{seq:1, version:'2'}` проти коментатора `{version:'2', seq:1}`) — `save` без змін не шле нічого;
  4. після успішного запису повторний `save` того самого — нічого; після невдалого (`upsert` повертає `error` усі 3 спроби) — повторний `save` шле знову;
  5. realtime: `{eventType:'INSERT', new:{project_id:'інший'}}` — жодного `select`; `{eventType:'UPDATE', new:{project_id:<наш канал>}}` — один `select` (після згладжування 120 мс; використати наявний у тестах спосіб чекати таймер); `{eventType:'DELETE', old:{id:<id з нашого кешу>}}` — `select`; `{eventType:'DELETE', old:{id:'чужий'}}` — нічого; `{}` (незнайома форма) — `select`.
  Run: `node --test tests/supabase-comments-adapter.test.mjs` → FAIL.

- [ ] **Step 2: Реалізація.** Після `commentToRow`:
  ```js
  /* Канонічний JSON (ключі обʼєктів відсортовано, `undefined` пропущено): Postgres `jsonb` переставляє ключі `meta`, і наївне
     `JSON.stringify` вважало б зміненим кожен рядок (поправка 8 плану Б2). */
  function stable(v) {
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    if (v && typeof v === 'object') {
      return '{' + Object.keys(v).filter(function (k) { return v[k] !== undefined; }).sort()
        .map(function (k) { return JSON.stringify(k) + ':' + stable(v[k]); }).join(',') + '}';
    }
    return JSON.stringify(v === undefined ? null : v);
  }
  ```
  У `create`: `var written = {};   // id → stable(рядка), який база точно має (останнє читання чи успішний запис)`.
  У `fetchAll` після `cache = …`: `written = {}; cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });`.
  `save`:
  ```js
        save: function (comments) {
          var rows = comments.map(function (c) { return commentToRow(c, channel); });
          /* Запис РІЗНИЦЕЮ (Deai 0.27.0): лише рядки, яких база ще не має в такому вигляді. Застарілий список одного вікна вже не
             перетирає чужого закриття чи доручення в РЕШТІ рядків; два записи в ОДИН рядок — виграє останній. */
          var changed = rows.filter(function (r) { return written[r.id] !== stable(r); });
          if (!changed.length) { cache = comments.slice(); seq++; return Promise.resolve(); }
          return upsert(changed, 0).then(function (err) {
            cache = comments.slice();
            seq++;
            if (!err) { changed.forEach(function (r) { written[r.id] = stable(r); }); return; }
            warn('save failed after retries', err);
            throw new Error('supabase save failed: ' + err.message);
          });
        },
  ```
  `remove` після успіху: `ids.forEach(function (id) { delete written[id]; });`.
  Realtime:
  ```js
      /* Подія realtime стосується НАШОГО каналу? Підписка — на всю таблицю (DELETE несе лише ключ, фільтр у підписці губив би
         видалення), тож відсіюємо тут: без цього кожен коментар будь-де давав би `select *` у кожному відкритому вікні
         (з Б2 кожна сторінка задачі підписана; урок квоти трафіку 21.10.2026). */
      function relevant(p) {
        var n = p && p.new, o = p && p.old;
        if (n && n.project_id != null) return n.project_id === channel;
        var id = o && o.id;
        if (id == null) return true;                       // незнайома форма — краще перечитати
        return cache.some(function (c) { return c.id === id; });
      }
  ```
  і `.on('postgres_changes', { event: '*', schema: 'public', table: TABLE }, function (p) { if (relevant(p)) scheduleFetch(); })`. Оновити шапку файла (два речення: запис різницею; фільтр подій).

- [ ] **Step 3: Прогін і мутації.** Мутації: (1) `stable` → `JSON.stringify`; (2) `changed = rows`; (3) `relevant` → `return true`.

- [ ] **Step 4: Commit** — `fix(supabase-comments): запис лише змінених рядків і realtime лише свого каналу`.

---

### Task 4: Коментатор: чипи адресата, колір, `setMeta`, `uploadShot(…, c)`

**Files:**
- Modify: `commenter/src/comment-layer.js` (+ збірка: `app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`, `commenter/build-stamp.json`)
- Modify: `app/serve.py` (`_local_comments_post`)
- Test: `tests/test_serve.py`, `tests/live/commenter-host.test.mjs`

Контракт (для `commenter/README.md` у T12): `audiences[i]` може мати `color` (лише `#rgb`…`#rrggbbaa`) і `note` (рядок під чипом); `host.defaultAudience` (функція чи рядок) і `host.onAudiencePick(id)`. Чипи у формі — ЛИШЕ з `host` і ≥ 2 аудиторіями; без `host` форма байт-у-байт як була.

- [ ] **Step 1: Тест сервера (червоний)** у `tests/test_serve.py` — за зразком наявного тесту, що ловить вичищення `_el`/`_pending` у `POST /api/local-comments` (пошук `_pending`): той самий запис із `_aud: 'project'` → у файлі задачі ключа `_aud` нема. Мутація потім — прибрати `'_aud'` із кортежу.

- [ ] **Step 2: Живі тести (червоні)** — дописати в `tests/live/commenter-host.test.mjs` (там уже є сторінка з коментатором і власним фейковим сховищем; брати її `init` і додати опції). Сценарії:
  - A: `host` + `audiences: [{id:'local',label:'L',color:'#7C6CF0'},{id:'project',label:'P',note:'бачать колеги'}]`, `host.defaultAudience: () => 'project'` → увімкнути режим, клік по елементу → у формі (`shadowRoot .compose`) два `.caud-b`; натиснута (`aria-pressed="true"`) — `P`; `.caud-note` = `бачать колеги`; клік по `L` → `.caud-note` порожня; «Comment» → у сховище пішов пін з `_aud: 'local'`; `onAudiencePick` отримав `'local'`.
  - B: пін з `_aud:'local'` → `.pin` має інлайн `background` `rgb(124, 108, 240)` і `data-aud="local"`; пін з `_aud:'project'` (без `color`) — інлайн-фону нема.
  - C: без `host` (ті самі `audiences`) → у формі `.caud-b` нема (шлях без хоста — як був).
  - D: `host` + одна аудиторія → чипів нема.
  - E: `CommentLayer.setMeta(id, {assignee:'claude'})` → `true`, у сховище пішов пін з `meta.assignee === 'claude'`; `setMeta(id, {assignee:null})` → ключ зник; невідомий id → `false`.
  - F: сховище з `uploadShot(id, shot, c)`, що записує третій аргумент, → при створенні піна з `_aud` той `c._aud` дійшов до `uploadShot` (якщо в цьому тест-файлі захоплення скріншота недоступне — перевірити через `_finishComment` прямим викликом на тестовій сторінці; у звіті — як саме).
  - G: `carry(id)` піна з `_aud:'project'` → копія має `_aud:'project'`.
  Run: `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/commenter-host.test.mjs` → FAIL.

- [ ] **Step 3: Методи коментатора** (у обʼєкті віджета, поруч з API хоста — після `_hostInset`):
  ```js
    /** Аудиторії для чипів адресата у формі: лише з хостом і ≥ 2 аудиторіями (Deai 0.27.0). Без хоста — `[]`: форма як була. */
    _formAuds() {
      const a = this.opts && this.opts.audiences;
      if (!this._hostOpts || !Array.isArray(a)) return [];
      const ok = a.filter((x) => x && typeof x.id === 'string' && x.id);
      return ok.length >= 2 ? ok : [];
    },
    /** Адресат за замовчуванням: `host.defaultAudience` (функція чи рядок), якщо він серед аудиторій, інакше перша. */
    _defaultAud(auds) {
      const d = this._hostOpts && this._hostOpts.defaultAudience;
      let v = null;
      try { v = typeof d === 'function' ? d() : d; } catch (e) { v = null; }
      return auds.some((x) => x.id === v) ? v : auds[0].id;
    },
    _audChipsHTML() {
      const auds = this._formAuds();
      if (!auds.length) return '';
      const cur = this._defaultAud(auds);
      return '<div class="caud" role="group">' + auds.map((x) => `<button type="button" class="caud-b" data-pick="${esc(x.id)}"`
        + ` aria-pressed="${x.id === cur}">${icon(x.icon, 13)}<span>${esc(x.label)}</span></button>`).join('')
        + '</div><div class="caud-note"></div>';
    },
    /** Чипи: один натиснутий; рядок під ними — `note` вибраної аудиторії (напр. «команда бачить це в превʼю»). */
    _wireAudChips(box) {
      const auds = this._formAuds();
      const note = box.querySelector('.caud-note');
      const sync = () => {
        const on = box.querySelector('.caud-b[aria-pressed="true"]');
        const a = on && auds.find((x) => x.id === on.getAttribute('data-pick'));
        if (note) note.textContent = a && typeof a.note === 'string' ? a.note : '';
      };
      box.querySelectorAll('.caud-b').forEach((b) => {
        b.onclick = () => {
          box.querySelectorAll('.caud-b').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
          sync();
        };
      });
      sync();
    },
    _pickedAud(box) {
      const on = box && box.querySelector('.caud-b[aria-pressed="true"]');
      return on ? on.getAttribute('data-pick') : null;
    },
    /** Колір піна за адресатом: `audiences[i].color` лише `#rgb`…`#rrggbbaa`, інакше `null` (колір за замовчуванням). */
    _audColor(c) {
      const list = c && c._aud && this.opts && Array.isArray(this.opts.audiences) ? this.opts.audiences : null;
      const a = list && list.find((x) => x && x.id === c._aud);
      return a && typeof a.color === 'string' && /^#[0-9a-f]{3,8}$/i.test(a.color) ? a.color : null;
    },
    /** Змінити поля `meta` піна (Deai 0.27.0: доручення `assignee`): `null`/`undefined` прибирає ключ. Звичайний `_persist`. */
    setMeta(id, patch) {
      const c = this._inited && this.comments.find((x) => x.id === id);
      if (!c || !patch || typeof patch !== 'object') return false;
      c.meta = Object.assign({}, c.meta || {});
      for (const k of Object.keys(patch)) { if (patch[k] == null) delete c.meta[k]; else c.meta[k] = patch[k]; }
      c._pending = true;
      this._persist(); this._render();
      return true;
    },
  ```

- [ ] **Step 4: Форми.** В обох композерах (`_openCompose` і `_openCanvasCompose`) розмітку `box.innerHTML` доповнити чипами ПЕРЕД `<div class="row">` (`${this._audChipsHTML()}`), після `this._sh.appendChild(box)` — `this._wireAudChips(box);`. У `save.onclick`:
  - DOM: `const aud = this._pickedAud(box); if (aud) this._emit('onAudiencePick', aud); this._addComment(el, text, sel, extra, aud); box.remove();`
  - полотно: `const aud = this._pickedAud(box); if (aud) this._emit('onAudiencePick', aud); this._addCanvasComment(t, text, aud); box.remove();`
  `_addComment(el, text, sel, extra, aud)` і `_addCanvasComment(t, text, aud)`: в обʼєкт нового піна (поруч із `_pending: true`) — `...(aud ? { _aud: aud } : {})`. `captureContext(..., { heading: this.appLocal || this._formAuds().length > 0 })` (у комбінованому режимі розділ потрібен і агентові, і колегам).
  CSS у стилях віджета, поруч із `.compose .row`:
  ```css
    .compose .caud{display:flex;gap:6px;margin-top:8px}
    .compose .caud-b{display:inline-flex;align-items:center;gap:5px;min-height:28px;padding:0 10px;border-radius:var(--rsm);border:1px solid var(--line);background:var(--s2);color:var(--lo);font:12px/1 inherit;cursor:pointer}
    .compose .caud-b[aria-pressed="true"]{border-color:var(--line2);color:var(--hi)}
    .compose .caud-note{min-height:0;margin-top:4px;font-size:11px;color:var(--lo)}
    .compose .caud-note:empty{display:none}
  ```
  (змінні — ті, що вже є в стилях віджета; перевірити назви там, де визначено `.compose textarea`).

- [ ] **Step 5: Пін, перенесення, скріншот.**
  - DOM-піни (`_placePins`, після `p.className = 'pin'; p.textContent = …`): `const col = this._audColor(c); if (col) p.style.background = col; if (c._aud) p.dataset.aud = c._aud;`
  - піни полотна (`_placeCanvasPins`, де виставляється `label` для `w.firstChild`): `const col = c ? this._audColor(c) : null; w.firstChild.style.background = col || ''; if (c && c._aud) w.firstChild.dataset.aud = c._aud; else delete w.firstChild.dataset.aud;`
  - `_carryToCurrent`: у копію — `...(src._aud ? { _aud: src._aud } : {})`.
  - обидва виклики `this.store.uploadShot(id, shot)` → `this.store.uploadShot(id, shot, c)` (DOM — `c`; полотно — `c()`). Коментар на одному з них: третій аргумент — для комбінованого сховища (поправка 5 плану Б2).

- [ ] **Step 6: Сервер.** `_local_comments_post` у `app/serve.py`: кортеж вичищення `('_el', '_pending')` → `('_el', '_pending', '_aud')` і коментар над ним — «`_aud` — службова позначка адресата комбінованого сховища (0.27.0)».

- [ ] **Step 7: Збірка й прогони.** `cd commenter && npm ci && npm run build && cd ..`; JS (усі три набори, разом зі штампом), `test_serve`, живий `commenter-host` — зелені; ще живий `comments-panel.test.mjs` (шлях Б1 не зламано).

- [ ] **Step 8: Мутації** (у `commenter/src` → збірка → червоно → відновити → збірка; детермінізм: після відновлення `git diff --exit-code app/vendor commenter/build-stamp.json`): (1) `_formAuds` без перевірки `this._hostOpts`; (2) `_audColor` без регекспа (повертає будь-який рядок) — тест із `color: 'red;x'`; (3) у `_carryToCurrent` прибрати `_aud`; (4) `uploadShot(id, shot)` без `c`.

- [ ] **Step 9: Commit** — джерело, три файли збірки, `app/serve.py`, тести: `feat(commenter): чипи адресата, колір піна за _aud, setMeta, uploadShot з піном`.

---

### Task 5: Комбіноване сховище `app/vendor/dual-store.js`

**Files:**
- Create: `app/vendor/dual-store.js`
- Create: `tests/dual-store.test.mjs`

- [ ] **Step 1: Тест (червоний)** — `tests/dual-store.test.mjs`:
  ```js
  import assert from "node:assert/strict";
  import test from "node:test";
  import { readFileSync } from "node:fs";
  import vm from "node:vm";

  /* Файл — класичний скрипт (`window.DeaiDualStore`), як `local-adapter.js`: вантажимо у пісочницю з `window`. */
  function load() {
    const win = {};
    vm.runInNewContext(readFileSync(new URL("../app/vendor/dual-store.js", import.meta.url), "utf8"), { window: win });
    return win.DeaiDualStore;
  }
  /** Фейкове під-сховище: тримає `cache`, пише журнал; `notifyOnSave` — як локальний адаптер (синхронно в `save`). */
  function fake(rows = [], { notifyOnSave = false, shots = false } = {}) {
    const s = { cache: rows.map((r) => ({ ...r })), subs: [], log: [] };
    s.store = {
      ready: Promise.resolve(),
      load: () => s.cache,
      save: (list) => { s.log.push(["save", list.map((c) => ({ ...c }))]); s.cache = list.map((c) => ({ ...c })); if (notifyOnSave) s.subs.forEach((f) => f(s.cache)); return Promise.resolve(); },
      remove: (ids) => { s.log.push(["remove", ids]); s.cache = s.cache.filter((c) => !ids.includes(c.id)); return Promise.resolve(); },
      subscribe: (f) => s.subs.push(f),
      refresh: () => { s.log.push(["refresh"]); return Promise.resolve(); },
      close: () => s.log.push(["close"]),
    };
    if (shots) s.store.uploadShot = (id, d) => { s.log.push(["shot", id]); return Promise.resolve("https://x/" + id); };
    return s;
  }
  const P = (id, extra = {}) => ({ id, author: "a", text: "t", status: "open", fp: null, htmlSnapshot: null, meta: { seq: 1 }, bornV: 1, resolvedV: null, resolveReason: null, ts: "14.11.2026 10:00", ...extra });

  test("load — обʼєднання з _aud на копіях; під-сховища свого _aud не бачать", async () => {
    const L = fake([P("l1")]), T = fake([P("t1")]);
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    assert.deepEqual(d.load().map((c) => [c.id, c._aud]), [["l1", "local"], ["t1", "project"]]);
    assert.equal("_aud" in L.cache[0], false);
    assert.equal(d.teamDown, null);
  });

  test("save ділить за _aud, знімає _aud, без _aud — локальне; незмінна частина не пишеться", async () => {
    const L = fake([P("l1")]), T = fake([P("t1")]);
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    const list = d.load().map((c) => ({ ...c }));
    list.push({ ...P("n1"), _aud: "project" }, P("n2"));         // n2 без _aud → локальне
    await d.save(list);
    assert.deepEqual(L.log.at(-1)[1].map((c) => c.id), ["l1", "n2"]);
    assert.deepEqual(T.log.at(-1)[1].map((c) => c.id), ["t1", "n1"]);
    assert.equal(T.log.at(-1)[1].some((c) => "_aud" in c), false);
    const before = [L.log.length, T.log.length];
    await d.save(d.load().map((c) => ({ ...c })));               // нічого не змінилось
    assert.deepEqual([L.log.length, T.log.length], before);
  });

  test("тінь командної частини: синхронне сповіщення локального не відкочує щойно змінений командний пін", async () => {
    const L = fake([P("l1")], { notifyOnSave: true }), T = fake([P("t1")]);   // командне після save НЕ сповіщає
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    let seen = null;
    d.subscribe((u) => { seen = u; });
    const list = d.load().map((c) => ({ ...c }));
    list[0] = { ...list[0], text: "змінено локально" };
    list[1] = { ...list[1], meta: { seq: 1, assignee: "claude" } };
    await d.save(list);
    assert.equal(seen.find((c) => c.id === "t1").meta.assignee, "claude");
  });

  test("remove — туди, де пін живе; невідомий id — в обидва", async () => {
    const L = fake([P("l1")]), T = fake([P("t1")]);
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    await d.remove(["t1"]);
    assert.deepEqual(T.log.at(-1), ["remove", ["t1"]]);
    assert.equal(L.log.some((e) => e[0] === "remove"), false);
    await d.remove(["x9"]);
    assert.deepEqual([L.log.at(-1), T.log.at(-1)], [["remove", ["x9"]], ["remove", ["x9"]]]);
  });

  test("скріншот у командне сховище — лише для командного піна (поправка 5)", async () => {
    const L = fake(), T = fake([], { shots: true });
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    assert.equal(await d.uploadShot("a", "data:image/jpeg;base64,AA", { _aud: "local" }), null);
    assert.equal(await d.uploadShot("a", "data:image/jpeg;base64,AA"), null);
    assert.equal(await d.uploadShot("b", "data:image/jpeg;base64,AA", { _aud: "project" }), "https://x/b");
    assert.deepEqual(T.log.filter((e) => e[0] === "shot"), [["shot", "b"]]);
  });

  test("командного нема: локальне працює, teamDown — причина, командний запис відмовляє", async () => {
    const L = fake([P("l1")]);
    const d = load()({ local: L.store, team: null, teamDown: "адаптер не завантажився" });
    await d.ready;
    assert.equal(d.teamDown, "адаптер не завантажився");
    assert.deepEqual(d.load().map((c) => c.id), ["l1"]);
    await assert.rejects(d.save([...d.load(), { ...P("n1"), _aud: "project" }]));
    assert.deepEqual(L.log.at(-1)[1].map((c) => c.id), ["l1"]);
  });

  test("команда впала на ready — teamDown, під-сховище закрите, далі лише локальне", async () => {
    const L = fake([P("l1")]), T = fake([P("t1")]);
    T.store.ready = Promise.reject(new Error("сервіс не відповів"));
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    assert.equal(d.teamDown, "сервіс не відповів");
    assert.deepEqual(d.load().map((c) => c.id), ["l1"]);
    assert.ok(T.log.some((e) => e[0] === "close"));
  });

  test("сповіщення будь-якого під-сховища — свіже обʼєднання; refresh і close — обом", async () => {
    const L = fake([P("l1")]), T = fake([P("t1")]);
    const d = load()({ local: L.store, team: T.store });
    await d.ready;
    let got = null;
    d.subscribe((u) => { got = u.map((c) => c.id + ":" + c._aud); });
    T.cache = [P("t1"), P("t2")]; T.subs.forEach((f) => f(T.cache));
    assert.deepEqual(got, ["l1:local", "t1:project", "t2:project"]);
    await d.refresh();
    await d.refreshLocal();                                     // лише локальне: командне — це трафік
    d.close();
    assert.deepEqual([L.log.filter((e) => e[0] !== "save").map((e) => e[0]), T.log.map((e) => e[0])],
      [["refresh", "refresh", "close"], ["refresh", "close"]]);
  });
  ```
  Run: `node --test tests/dual-store.test.mjs` → FAIL (файла нема).

- [ ] **Step 2: Реалізація** — `app/vendor/dual-store.js`:
  ```js
  /*!
   * Комбіноване сховище коментарів Deai (0.27.0, етап Б2): локальний файл задачі (фідбек Claude) + командний канал модуля
   * ролі `comments` — ОДИН контракт сховища comment-layer: { ready, load, save, remove, subscribe, refresh, close, uploadShot }.
   * Адресат піна — СХОВИЩЕ, де він лежить (спека Б-Р5). Коментатору — копії зі службовим `_aud` ('local' | 'project');
   * під-сховищам `_aud` не йде (адаптери однаково пишуть лише свій білий список). Пін без `_aud` — локальний: приватне
   * за замовчуванням, колегам випадково не поїде.
   * ⛔ Незмінну частину адресата не пишемо (поправка 6 плану Б2): інакше кожна дія з локальним піном переписувала б увесь
   *   командний список. ⛔ Тінь командної частини (поправка 7): локальний адаптер сповіщає синхронно ПІД ЧАС `save`, а
   *   командний — лише згодом (realtime), і обʼєднання взяло б старий командний кеш. ⛔ Скріншот — у командне сховище лише
   *   командного піна (поправка 5): скрін фідбеку для Claude не мусить лягти в публічний кошик колег.
   * Падіння командного (`team: null` + `teamDown`, або його `ready` відмовив) — локальне працює далі; причина — `teamDown`.
   * Attaches window.DeaiDualStore. Без DOM: тест — `tests/dual-store.test.mjs`.
   */
  (function () {
    var FIELDS = ['id', 'author', 'text', 'status', 'fp', 'htmlSnapshot', 'meta', 'bornV', 'resolvedV', 'resolveReason', 'ts'];
    function strip(c) { var o = {}; for (var k in c) if (k !== '_aud') o[k] = c[k]; return o; }
    function tag(list, aud) {
      return (list || []).map(function (c) { var o = {}; for (var k in c) o[k] = c[k]; o._aud = aud; return o; });
    }
    function stable(v) {
      if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
      if (v && typeof v === 'object') {
        return '{' + Object.keys(v).filter(function (k) { return v[k] !== undefined; }).sort()
          .map(function (k) { return JSON.stringify(k) + ':' + stable(v[k]); }).join(',') + '}';
      }
      return JSON.stringify(v === undefined ? null : v);
    }
    /* Відбиток частини для «чи змінилась»: лише поля контракту, `null` замість відсутнього, порядок — за id. */
    function sig(list) {
      return stable((list || []).map(function (c) {
        var o = {}; for (var i = 0; i < FIELDS.length; i++) o[FIELDS[i]] = c[FIELDS[i]] == null ? null : c[FIELDS[i]];
        return o;
      }).sort(function (a, b) { return String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0; }));
    }
    function has(list, id) { for (var i = 0; i < (list || []).length; i++) if (list[i] && list[i].id === id) return true; return false; }

    function DualStore(opts) {
      var local = opts.local;
      var team = opts.team || null;
      var subs = [];
      var shadow = null;                       // командна частина, щойно віддана в `team.save`, поки `team` не заговорить сам
      var store = { teamDown: team ? null : String(opts.teamDown || 'team comments unavailable') };
      function teamList() { return team ? (shadow || team.load()) : []; }
      function union() { return tag(local.load(), 'local').concat(tag(teamList(), 'project')); }
      function notify() { var u = union(); for (var i = 0; i < subs.length; i++) { try { subs[i](u); } catch (e) {} } }
      function dropTeam(why) {
        if (team && typeof team.close === 'function') { try { team.close(); } catch (e) {} }
        team = null; shadow = null; store.teamDown = String(why || 'team comments unavailable');
      }
      if (typeof local.subscribe === 'function') local.subscribe(function () { notify(); });
      if (team && typeof team.subscribe === 'function') team.subscribe(function () { shadow = null; notify(); });
      store.ready = Promise.all([
        Promise.resolve(local.ready),
        team ? Promise.resolve(team.ready).catch(function (e) { dropTeam((e && e.message) || 'team comments did not answer'); }) : null,
      ]).then(function () {});
      store.load = function () { return union(); };
      store.save = function (list) {
        var mine = { local: [], project: [] };
        for (var i = 0; i < (list || []).length; i++) {
          var c = list[i]; if (!c) continue;
          mine[c._aud === 'project' ? 'project' : 'local'].push(strip(c));
        }
        var doLocal = sig(mine.local) !== sig(local.load());
        var doTeam = !!team && sig(mine.project) !== sig(teamList());
        /* Тінь — ДО локального запису: локальний адаптер сповіщає синхронно всередині `save`, і обʼєднання в тому
           сповіщенні мусить уже бачити нову командну частину (поправка 7). */
        if (doTeam) shadow = mine.project;
        var jobs = [];
        if (doLocal) jobs.push(Promise.resolve(local.save(mine.local)));
        if (doTeam) jobs.push(Promise.resolve(team.save(mine.project)));
        else if (!team && mine.project.length) {
          jobs.push(Promise.reject(new Error('team comments unavailable: ' + store.teamDown)));
        }
        return Promise.all(jobs).then(function () {});
      };
      store.remove = function (ids) {
        ids = ids || [];
        var l = [], t = [];
        for (var i = 0; i < ids.length; i++) {
          var inL = has(local.load(), ids[i]), inT = has(teamList(), ids[i]);
          if (inL || !inT) l.push(ids[i]);
          if (team && (inT || !inL)) t.push(ids[i]);
        }
        if (shadow) shadow = shadow.filter(function (c) { return t.indexOf(c.id) < 0; });
        var jobs = [];
        if (l.length && typeof local.remove === 'function') jobs.push(Promise.resolve(local.remove(l)));
        if (t.length && typeof team.remove === 'function') jobs.push(Promise.resolve(team.remove(t)));
        return Promise.all(jobs).then(function () {});
      };
      store.subscribe = function (f) { if (typeof f === 'function') subs.push(f); };
      store.refresh = function () {
        return Promise.all([
          typeof local.refresh === 'function' ? local.refresh() : null,
          team && typeof team.refresh === 'function' ? team.refresh() : null,
        ]).then(function () {});
      };
      /* Свіжість локальних (спека Б2.1): локальний адаптер живих оновлень не має, а агент пише в той самий файл
         (`inbox.py resolve`). Оболонка кличе це на `focus` свого вікна й на відкриття панелі; командне не чіпаємо (трафік). */
      store.refreshLocal = function () {
        return typeof local.refresh === 'function' ? Promise.resolve(local.refresh()).then(function () {}) : Promise.resolve();
      };
      store.close = function () {
        subs.length = 0;
        if (typeof local.close === 'function') { try { local.close(); } catch (e) {} }
        if (team && typeof team.close === 'function') { try { team.close(); } catch (e) {} }
      };
      store.uploadShot = function (id, dataUrl, c) {
        if (!team || typeof team.uploadShot !== 'function' || !c || c._aud !== 'project') return Promise.resolve(null);
        return Promise.resolve(team.uploadShot(id, dataUrl));
      };
      return store;
    }
    if (typeof window !== 'undefined') window.DeaiDualStore = DualStore;
  })();
  ```
  (Примітка для `remove` у тесті «невідомий id — в обидва»: обидва під-сховища отримують `["x9"]`.)

- [ ] **Step 3: Прогін і мутації.** Мутації: (1) `strip(c)` → `c` у `save` (командне бачить `_aud`); (2) `teamList()` → `team.load()` у `union` (тінь вимкнено); (3) рядок `if (doTeam) shadow = …` перенести ПІСЛЯ `local.save` (тінь запізнюється); (4) у `uploadShot` прибрати `c._aud !== 'project'`; (5) `doTeam` без порівняння `sig`.

- [ ] **Step 4: Commit** — `feat(comments): комбіноване сховище DeaiDualStore (локальне + командне)`.

---

### Task 6: Комбінований сніпет рамки (`DUAL_COMMENT_SNIPPET`)

**Files:**
- Modify: `app/serve.py` (`HOST_ARG`, нові `DUAL_AUDIENCES_JS`, `DUAL_COMMENT_SNIPPET`, `inject_dual_comment_layer`, гілка в `_commented`)
- Modify: `app/i18n.js` (ключі підписів чипів — для пари з Python)
- Test: `tests/test_comments_role.py`, `tests/test_publish_module.py`

- [ ] **Step 1: Тести (червоні)** у `tests/test_comments_role.py` (на наявних `PagesEnv`/`CommentsEnv` — тими самими викликами, що вже тестують `/commented` з `host=1`; пошук `host=1`):
  1. простір із модулем `memo` + `/commented?it=it1&host=1` → у сторінці `window.DeaiDualStore(`, `local-adapter.js`, `dual-store.js`, файли адаптера модуля БЕЗ `onerror=` (регексп на теги `/api/module-client/`), `projectId: "<tid>/local"`, `color: '#7C6CF0'`, `defaultAudience`; НЕМА `ch=` у логіці вибору (параметр `ch=project` у запиті нічого не змінює — відповідь та сама);
  2. той самий простір, `/commented?it=it1&ch=project` БЕЗ `host` → сторінка байт-у-байт та сама, що до задачі (еталони `tests/fixtures/comments-role/` не змінюються; наявні тести еталонів — зелені без правок);
  3. простір без постачальника + `host=1` → локальний сніпет (як у Б1), `DeaiDualStore` нема;
  4. постачальник є, а конфіг не зібрався (`ModuleError`, напр. без обовʼязкового налаштування — як у наявному тесті «comments-unconfigured») + `host=1` → комбінований сніпет із `var why = "командні коментарі не піднялись (<код>)"`, без тегів адаптера, без банера-примітки `COMMENT_NOTICE_SNIPPET`;
  5. `HOST_ARG` містить `localStorage.getItem('dc-cmt-aud')` і `localStorage.setItem('dc-cmt-aud'` (тест ПАРИ з `app/app.js` додає T9, коли ключ зʼявиться там);
  6. пара підписів (за зразком `test_audience_labels_match_dictionary` — знайти його): підписи `uk`/`en` у `DUAL_AUDIENCES_JS` дорівнюють `audChipLocal`, `audChipTeam`, `audChipTeamNote` у `app/i18n.js`.
  У `tests/test_publish_module.py`: збірка превʼю ніколи не містить `DeaiDualStore`, `dual-store.js`, `defaultAudience` (за зразком наявного тесту «публікація без host» з Б1).
  Run → FAIL.

- [ ] **Step 2: `app/i18n.js`** — нові ключі (uk / en):
  - `audChipLocal`: `Claude` / `Claude`
  - `audChipTeam`: `Команді` / `Team`
  - `audChipTeamNote`: `Командні коментарі видно колегам у превʼю` / `Team comments are visible to colleagues in the preview`

- [ ] **Step 3: `HOST_ARG`** — у повернутий обʼєкт дописати (після `onMode`):
  ```js
            onMode: function (on) { send({ ev: 'mode', on: !!on }); },
            defaultAudience: function () { try { return localStorage.getItem('dc-cmt-aud'); } catch (e) { return null; } },
            onAudiencePick: function (id) { try { localStorage.setItem('dc-cmt-aud', id); } catch (e) {} }
  ```
  (кома після `onMode` обовʼязкова; коментар над `HOST_ARG` — одне речення про ключ `dc-cmt-aud`, поправка 12.)

- [ ] **Step 4: Сніпет.** Після `inject_module_comment_layer`:
  ```python
  # Комбінований канал робочого місця (Deai 0.27.0, Б2.1) — лише з `host=1` і командним постачальником: ОДИН шар коментатора на
  # ДВА сховища (`app/vendor/dual-store.js`), адресат піна = сховище. Відмінності від `MODULE_COMMENT_SNIPPET`:
  #   · теги адаптера модуля — БЕЗ `onerror`-банера: падіння командного не ховає локальних (смуга в панелі оболонки, поправка 4);
  #   · `why` від сервера (конфіг модуля не зібрався) — адаптер навіть не пробуємо;
  #   · аудиторій дві лише коли командне живе (`team`), інакше одна — і чипів у формі нема (коментатор малює їх від двох).
  # Банер `__clDown` — ПЕРШИМ тегом, як у `MODULE_COMMENT_SNIPPET` (порядок несучий, див. коментар над `_COMMENT_DOWN_BANNER`).
  DUAL_AUDIENCES_JS = """(function () {
          var uk = { local: 'Claude', team: 'Команді', note: 'Командні коментарі видно колегам у превʼю' };
          var en = { local: 'Claude', team: 'Team', note: 'Team comments are visible to colleagues in the preview' };
          var L = uk;
          try { if (localStorage.getItem('dc-lang') === 'en') L = en; } catch (e) {}
          return [{ id: 'local', label: L.local, icon: 'bot', color: '#7C6CF0' },
                  { id: 'project', label: L.team, icon: 'team', note: L.note }];
        })()"""

  DUAL_CLIENT_TAG = '\n<script src="{src}"></script>'

  DUAL_COMMENT_SNIPPET = '\n' + _COMMENT_DOWN_BANNER + """
  <script src="{assets}/local-adapter.js" onerror="window.__clDown('локальний адаптер не завантажився')"></script>
  <script src="{assets}/dual-store.js" onerror="window.__clDown('сховище коментарів не завантажилось')"></script>
  <script src="{assets}/comment-layer.min.js" onerror="window.__clDown('шар коментарів не завантажився')"></script>{client_tags}{inspector}
  <script>
  window.__deaiCommentsCfg = {cfg_js};
  (function () {{
    var init = function () {{
      var cfg = window.__deaiCommentsCfg, team = null, why = {why_js};
      if (!window.CommentLayer || !window.CommentLayerLocal || !window.DeaiDualStore) {{
        window.__clDown('шар коментарів не піднявся');
        return;
      }}
      if (!why) {{
        try {{
          if (!window.DeaiComments) throw new Error('адаптер командних коментарів не завантажився');
          team = window.DeaiComments.create(Object.assign({{}}, cfg, {{ onChange: function () {{}} }}));
          if (!team || typeof team.load !== 'function' || typeof team.save !== 'function') {{
            throw new Error('адаптер повернув сховище без load/save');
          }}
        }} catch (e) {{
          if (team && typeof team.close === 'function') {{ try {{ team.close(); }} catch (x) {{}} }}
          team = null;
          why = (e && e.message) || 'адаптер не зміг піднятись';
        }}
      }}
      var auds = {auds_js};
      var store = window.DeaiDualStore({{ local: window.CommentLayerLocal({{ endpoint: {endpoint_js} }}), team: team, teamDown: why }});
      store.ready.then(function () {{
        window.CommentLayer.init({{ projectId: {project_js}, storage: store, version: {version_js},
          audiences: store.teamDown ? auds.slice(0, 1) : auds{host} }});
      }});
    }};
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
  }})();
  </script>"""


  def inject_dual_comment_layer(html, assets_base, client_urls, config, endpoint, project, version='', team_error=None,
                                profile='', space=None):
      """Комбінований канал робочого місця (Deai 0.27.0): локальний адаптер + адаптер модуля через `DeaiDualStore`, режим хоста
      завжди, інспектор завжди (як `inject_module_comment_layer` з `inspector=True`). `team_error` — причина, з якої сервер не
      зібрав конфіг модуля (тоді `client_urls` порожній, `config` — `{}`). ⛔ Публікація сюди не доходить ніколи."""
      assets = html_escape(assets_base, quote=True)
      snippet = DUAL_COMMENT_SNIPPET.format(
          assets=assets,
          client_tags=''.join(DUAL_CLIENT_TAG.format(src=html_escape(u, quote=True)) for u in client_urls),
          inspector=INSPECTOR_TAG.format(assets=assets, ds=inspector_ds_arg(profile, space)),
          cfg_js=js_literal(config or {}), why_js=js_literal(team_error), auds_js=DUAL_AUDIENCES_JS,
          endpoint_js=js_literal(endpoint), project_js=js_literal(project), version_js=js_literal(version),
          host=host_arg(True))
      return _insert_before_body(html, snippet)
  ```
  Перевірити, що `js_literal(None)` дає `null` (якщо ні — `js_literal(team_error or '')` і в JS `if (!why)` працює однаково; рішення — у звіт).

- [ ] **Step 5: `_commented`.** Одразу після обчислення `prov, prov_err` і `team` (перед `notice = None`) — обчислити `local_key` (перенести рядок `local_key = …` вище, щоб він був спільним) і додати гілку:
  ```python
              if host and (prov is not None or prov_err is not None):
                  # Б2 (0.27.0): робоче місце з командним постачальником — ОДИН шар на обидва сховища; `ch` тут не діє.
                  # Постачальник не вирішився чи конфіг не зібрався — комбінований сніпет із причиною: локальні працюють, а
                  # панель оболонки каже, чому нема командних (поправка 4 плану Б2).
                  mod, module_cfg, team_err = None, None, None
                  if prov_err is not None:
                      team_err = f'командні коментарі не піднялись ({prov_err.code})'
                  else:
                      try:
                          mod, cctx, route_channel = comments_route(page_space, prov)
                          module_cfg = {**deai_modules.comments_client(page_space, mod, cctx), 'channel': route_channel(task, tid)}
                      except deai_modules.ModuleError as e:
                          team_err = f'командні коментарі не піднялись ({e.code})'
                  html = inject_dual_comment_layer(
                      html, f'{origin}/app/vendor', module_client_urls(mod, page_space) if module_cfg else [],
                      module_cfg or {}, f'{origin}/api/local-comments', local_key,
                      version=pm.page_version_tag(it, page), team_error=team_err,
                      profile=task_ds(task, page_space), space=page_space)
              else:
                  <наявний код гілки без змін: notice, ch, module_cfg, inject_module_… / inject_local_…>
  ```
  (Оформити як `if … : … else:` з наявним кодом під `else` — без зміни його поведінки; `host` у наявних викликах лишається — гілка `else` з `host=True` тепер означає «простору без постачальника».)

- [ ] **Step 6: Прогін і мутації.** Python (усі три), JS зелені; наявні тести еталонів без правок. Мутації: (1) у `DUAL_CLIENT_TAG` повернути `onerror="window.__clDown(…)"`; (2) у `_commented` умову `host and …` → `prov is not None` (комбінований без `host` — еталони червоні); (3) `audiences: store.teamDown ? … : auds` → `auds`.

- [ ] **Step 7: Commit** — `feat(serve): комбінований сніпет робочого місця (локальні + командні в одному шарі)`.

---

### Task 7: «Огляд» на комбінованому сховищі

**Files:**
- Modify: `app/overview-comments.js` (`start`, шапка про `env.channel`)
- Modify: `app/index.html` (`<script src="vendor/dual-store.js">` поруч із `vendor/local-adapter.js`)
- Test: `tests/overview-comments-module.test.mjs`

- [ ] **Step 1: Тести (червоні)** у `tests/overview-comments-module.test.mjs` (на наявних фейках `fetch`/`window`/`CommentLayer.create` цього файла; пошук `comment-config`):
  1. `env.channel() === 'dual'` → два запити `/api/comment-config?ch=local&it=…` і `…ch=project…`; `CommentLayer.create().init` отримує `storage` = обʼєкт з `teamDown === null`, `projectId` = `project` з локальної відповіді, `local: false`, `audiences` = `env.audiences()`;
  2. `ch=project` відповів 409 → `init` отримує сховище з `teamDown` (рядок помилки), шар піднявся (а не `env.fail`);
  3. `env.channel() === 'local'` → один запит `ch=local`, `storage` — локальне (`window.CommentLayerLocal`), `local: true`, як було.
  Run → FAIL.

- [ ] **Step 2: Реалізація `start(key)`:**
  ```js
      const [it, ch] = key.split("|");
      const cfgOf = (c) => fetch(`/api/comment-config?ch=${encodeURIComponent(c)}&it=${encodeURIComponent(it)}`)
        .then(async (r) => { if (!r.ok) throw await configError(r); return r.json(); });
      const cfg = await cfgOf("local");
      if (stale()) return;
      let store;
      const local = window.CommentLayerLocal({ endpoint: cfg.endpoint });
      if (ch === "dual") {
        // Б2 (0.27.0): локальні + командні в одному шарі; командне не піднялось — лише локальні й причина (`teamDown`).
        let team = null, why = null;
        try { team = await moduleStore(await cfgOf("project")); }
        catch (e) { why = (e && e.message) || String(e); }
        if (stale()) { closeQuietly(team); closeQuietly(local); return; }
        store = window.DeaiDualStore({ local, team, teamDown: why });
      } else {
        store = local;
      }
  ```
  далі як було (`await store.ready` з `closeQuietly(store)` у `catch`, `stale()`, `cl.destroy()`), а в `init`: `projectId: cfg.project, storage: store, version: cfg.version, local: ch !== "dual", anchors: provider, audiences: ch === "dual" ? env.audiences() : [], defaultUser: cfg.user || null, host: env.host || undefined` (`onAudience` прибрати — каналу більше не перемикаємо, поправка 10). Шапка JSDoc `env`: `channel: () => 'dual'|'local'`, без `onAudience`.

- [ ] **Step 3: `app/index.html`** — `vendor/dual-store.js` одразу після тегу `vendor/local-adapter.js` (той самий вигляд тегу).

- [ ] **Step 4: Прогін і мутації.** JS зелений. Мутації: (1) `local: ch !== "dual"` → `true`; (2) у `catch` командного — `throw e` (падіння командного валить «Огляд»).

- [ ] **Step 5: Commit** — `feat(overview): «Огляд» на комбінованому сховищі`.

---

### Task 8: Чисті модулі оболонки (модель, «нові», розмітка, острівець, вкладки, дерево)

**Files:**
- Modify: `app/comments-model.js`, `app/comments-view.js`, `app/island.js`, `app/tabs-model.js`, `app/tabs-view.js`, `app/shell-panel.js`, `app/i18n.js`
- Create: `app/comment-news.js`
- Test: `tests/comments-model.test.mjs`, `tests/comment-news.test.mjs` (новий), `tests/comments-view.test.mjs`, `tests/island.test.mjs`, тести вкладок і панелі дерева (знайти: `ls tests | grep -E "tabs|shell-panel"`)

- [ ] **Step 1: i18n** (uk / en) — нові ключі:
  - `cmtFilter`: `Кому` / `Addressee`
  - `cmtFAll`: `Усі` / `All`; `cmtFLocal`: `Для Claude` / `For Claude`; `cmtFTeam`: `Команда` / `Team`
  - `cmtAudLocal`: `Claude` / `Claude`; `cmtAudTeam`: `Команда` / `Team`
  - `cmtAssign`: `Доручити Claude` / `Assign to Claude`; `cmtUnassign`: `Забрати в Claude` / `Take back from Claude`; `cmtAssignedBadge`: `Claude` / `Claude`
  - `cmtTeamDown`: `(why) => \`Командні коментарі недоступні: ${why}\`` / `(why) => \`Team comments are unavailable: ${why}\``
  - `cmtNewTitle`: `Нові від команди` / `New from the team`
  - `cmtNewToast`: `(who) => \`Новий коментар від ${who}\`` / `(who) => \`New comment from ${who}\``
  - `cmtNewToastN`: `(n) => \`Нових коментарів від команди: ${n}\`` / `(n) => \`New team comments: ${n}\``
  - `cmtShowNew`: `Показати` / `Show`
  - `cmtIslandNew`: `(n) => \`Коментарі: нових від команди — ${n}\`` / `(n) => \`Comments: ${n} new from the team\``
  - `tabNews`: `(n) => \`Нових командних коментарів: ${n}\`` / `(n) => \`New team comments: ${n}\``
  - `rowNews`: `(n) => \`Нових коментарів від команди: ${n}\`` / `(n) => \`New team comments: ${n}\``
  Прибрати ключі, що стануть мертвими після T9, — НЕ тут, а в T9 (там і охоронець мертвих ключів, якщо він є).

- [ ] **Step 2: `app/comment-news.js`** (новий) і його тест. Код:
  ```js
  /**
   * «Нові командні коментарі» (Deai 0.27.0, Б2.4). Чиста: ні DOM, ні мережі, ні localStorage — сховище дає `app.js`.
   * Новий = командний (`_aud === 'project'` у знімку; у відповіді `/api/comment-news` — усі), відкритий, не мій, id не бачили.
   * ⛔ Маркер «бачив» — НАБІР id, а не `ts` (поправка 2 плану Б2): `ts` коментатора — локальний час автора з точністю до
   *   хвилини, а команда в різних поясах; маркер за часом губив би нові або плутав коментарі однієї хвилини.
   */
  import { pinTarget } from "./overview-pins.js";

  export const SEEN_MAX = 1000;
  /** Ключ маркера в localStorage: простір (або `-`) і задача — id задач у різних просторах можуть збігатися. */
  export const seenKey = (spaceId, taskId) => `dc-seen:${spaceId || "-"}:${taskId}`;
  /** Рядок зі сховища → `Set` id; маркера нема або він битий — `null` (перший погляд, див. `baseline`). */
  export function readSeen(raw) {
    if (typeof raw !== "string" || !raw) return null;
    try {
      const v = JSON.parse(raw);
      return v && v.v === 1 && Array.isArray(v.ids) ? new Set(v.ids.filter((x) => typeof x === "string")) : null;
    } catch { return null; }
  }
  /** `Set` → рядок для сховища: лише останні `SEEN_MAX` (порядок — додавання). */
  export const writeSeen = (set) => JSON.stringify({ v: 1, ids: [...(set || [])].slice(-SEEN_MAX) });
  /** Перший погляд на задачу: усе, що вже є, — бачене (накопичене не вивалюється «новим»). */
  export const baseline = (items) => new Set((items || []).map((c) => c && c.id).filter((x) => typeof x === "string"));
  /** Додати id у маркер (переставляючи в кінець — `writeSeen` тримає найсвіжіші). */
  export function markSeen(seen, ids) {
    const s = new Set(seen || []);
    for (const id of ids || []) if (typeof id === "string") { s.delete(id); s.add(id); }
    return s;
  }
  /** Командні коментарі знімка коментатора. */
  export const teamOf = (comments) => (Array.isArray(comments) ? comments.filter((c) => c && c._aud === "project") : []);
  /** Чи «новий»: відкритий, не мій (`me` — імʼя автора цього вікна; порожнє — «мого» нема), id не бачили. */
  export const isNew = (c, seen, me) => !!c && typeof c.id === "string" && c.status === "open"
    && !(me && c.author === me) && !!seen && !seen.has(c.id);
  /** Що зʼявилось відносно попереднього знімка (`prevIds` — `Set` або `null` для першого: тоді нічого). */
  export function arrived(prevIds, comments) {
    if (!prevIds) return [];
    return (comments || []).filter((c) => c && typeof c.id === "string" && !prevIds.has(c.id));
  }
  /** Нові за сторінками дерева: `{pageId: n}`; сторінку дає тег версії піна, як на «Огляді» (`pinTarget`). */
  export function newsByPage(comments) {
    const out = {};
    for (const c of comments || []) {
      const t = pinTarget(c);
      if (t && t.page) out[t.page] = (out[t.page] || 0) + 1;
    }
    return out;
  }
  ```
  Тест `tests/comment-news.test.mjs` — по одному `test` на функцію: `seenKey("liga","t1") === "dc-seen:liga:t1"`, `seenKey(null,"t1") === "dc-seen:-:t1"`; `readSeen` (null, "", "x{", `{"v":2,…}`, валідний із не-рядком у `ids` → лише рядки); `writeSeen` обрізає до 1000 останніх (1005 id → перші 5 зникли); `baseline`; `markSeen` переставляє наявний id у кінець; `teamOf`; `isNew` (закритий — ні; мій — ні; `me=""` — так; бачений — ні; `seen=null` — ні); `arrived(null, …) → []`, нові відносно набору; `newsByPage` (`meta.version: "3/stattia"` → `stattia`, `"3"` → `main`, без версії і без `url` — пропуск).

- [ ] **Step 3: `app/comments-model.js`** — додати й змінити:
  ```js
  /** Адресат картки: `_aud` комбінованого сховища; без нього (лише локальний канал) — 'local'. */
  export const audOf = (c) => (c && c._aud === "project" ? "project" : "local");
  /** Доручено Claude (`meta.assignee`, спека Б-Р6) — те саме правило, що `for_agent` у `serve.py`. */
  export const assignedToClaude = (c) => !!(c && c.meta && c.meta.assignee === "claude");
  /** Фільтр панелі «Усі / Для Claude / Команда». */
  export const FILTERS = ["all", "local", "project"];
  const passFilter = (c, f) => (f === "local" || f === "project" ? audOf(c) === f : true);
  ```
  `commentSections(snapshot, { query = "", filter = "all", fresh = null } = {})` → `{ fresh, open, earlier, closed }`:
  ```js
    const hit = (c) => matchQuery(c, query) && passFilter(c, filter);
    const isFresh = (c) => !!(fresh && fresh.has(c.id)) && c.status === "open";
    return {
      fresh: all.filter((c) => isFresh(c) && hit(c)).sort(byNewest),
      open: all.filter((c) => c.status === "open" && c.scope === "current" && !isFresh(c) && hit(c)).sort(byNewest),
      earlier: all.filter((c) => c.status === "open" && c.scope === "earlier" && !isFresh(c) && hit(c)).sort(byNewest),
      closed: all.filter((c) => c.status === "resolved" && c.scope === "current" && hit(c))
        .sort((a, b) => (closedAt(b) - closedAt(a)) || byNewest(a, b)),
    };
  ```
  `openCount` — без змін (усі адресати). Тести: фільтр `local`/`project`/`all`; пін без `_aud` — локальний; свіжий не дублюється у «Відкритих»; закритий у `fresh` не потрапляє.

- [ ] **Step 4: `app/comments-view.js`.** Імпорт: `import { FILTERS, assignedToClaude, audOf, commentSections, openCount, shotSrc } from "./comments-model.js";`. Стан `st` отримує `filter`, `dual` (bool: у просторі є командний постачальник), `teamDown` (рядок|null), `fresh` (`Set`|null); `channel` і `team` — прибрати.
  - Сегмент каналу (`seg`) → сегмент фільтра (той самий клас `.cmt-ch` — правило 28px з Б1):
    ```js
    const FILTER_KEY = { all: "cmtFAll", local: "cmtFLocal", project: "cmtFTeam" };
    const seg = st.dual
      ? `<div class="cmt-ch" role="group" aria-label="${esc(t("cmtFilter"))}">`
        + FILTERS.map((f) => `<button type="button" data-act="cmtfilter" data-val="${f}" aria-pressed="${(st.filter || "all") === f}">`
          + `${esc(t(FILTER_KEY[f]))}</button>`).join("") + "</div>"
      : "";
    ```
  - Смуга падіння командного — одразу після `search`: `const down = st.teamDown ? \`<p class="cmt-teamdown" role="alert">${esc(t("cmtTeamDown", st.teamDown))}</p>\` : "";`
  - У `cardHTML` (лише коли `st.dual`): адресат у шапці після автора — `<span class="cmt-aud cmt-aud--${audOf(c)}">${esc(t(audOf(c) === "project" ? "cmtAudTeam" : "cmtAudLocal"))}</span>`; бейдж доручення — `assignedToClaude(c) ? \`<span class="cmt-badge">${esc(t("cmtAssignedBadge"))}</span>\` : ""`; для відкритих командних (`kind` `open`/`fresh`, `audOf(c) === "project"`) у дії, ПЕРЕД «Редагувати», — `btn(assignedToClaude(c) ? "cmtunassign" : "cmtassign", c.id, t(assignedToClaude(c) ? "cmtUnassign" : "cmtAssign"))` (текстова кнопка, без іконки).
  - Розділ «Нові від команди» — над «Відкритими»: `const fresh = s.fresh.length ? \`<section class="cmt-sec cmt-sec--new" aria-label="${esc(t("cmtNewTitle"))}"><h3 class="cmt-h cmt-h--new">${esc(t("cmtNewTitle"))} <span>${s.fresh.length}</span></h3>${s.fresh.map((c) => cardHTML(c, st, "open")).join("")}</section>\` : "";` і `commentSections(st.snapshot, { query: st.query, filter: st.filter, fresh: st.fresh })`; `none` рахує й `s.fresh`.
  - Тести (`tests/comments-view.test.mjs`; `base()` у ньому — замінити `channel`/`team` на `filter: "all", dual: false, teamDown: null, fresh: null`): без `dual` сегмента нема; з `dual` — три кнопки, натиснута за `filter`; смуга з текстом причини (екранована: `"<b>"` → `&lt;b&gt;`); адресат і бейдж; кнопка «Доручити»/«Забрати» лише на відкритих командних, не на локальних і не на закритих; розділ «Нові» з числом і без дубля у «Відкритих»; **поправка 18:** командний пін, закритий агентом (`resolvedV: 4`, `resolveReason: "кнопку перенесено"`) → «Зроблено · Іт.4», закритий вручну (`resolvedV: 1`, `resolveReason: "resolved manually"`) → «Закрито» (без «Іт.»).

- [ ] **Step 5: `app/island.js`** — параметр `commentsNew = 0`: коли `> 0`, замість нейтрального числа — `<span class="isl-count isl-count--new" aria-hidden="true">${n > 99 ? "99+" : n}</span>`, `aria-label` = `t("cmtIslandNew", commentsNew)`. Тест у `tests/island.test.mjs`: нові → клас `isl-count--new` і число нових; без нових — як було.

- [ ] **Step 6: Вкладки.** `tabsModel({…, news = null})` → кожен `item.news = news && Number(news[t.id]) > 0 ? Number(news[t.id]) : 0`. `tabs-view.js` `tabHTML`: після `tab-id` — `x.news ? \`<span class="tab-news" role="img" aria-label="${esc(t("tabNews", x.news))}">${x.news > 99 ? "99+" : x.news}</span>\` : ""`. Тести: модель (число, нуль, нема `news`) і розмітка (екранування не потрібне — число, але перевірити `aria-label`).

- [ ] **Step 7: Дерево.** `app/shell-panel.js` (рядок, поруч із `cnt`): `const news = row.news ? \`<span class="row-news" title="${esc(t("rowNews", row.news))}">${row.news > 99 ? "99+" : row.news}</span>\` : "";` і вставити `${news}` після `${cnt}`. У статичному превʼю `row.news` нема — розмітка там байт-у-байт (наявний тест превʼю мусить лишитись зеленим без правок). Тест: рядок із `news: 2` має `.row-news` з `2`.

- [ ] **Step 8: Прогін і мутації.** JS зелений. Мутації: (1) `isNew` без `!(me && c.author === me)`; (2) `commentSections` без `!isFresh(c)` в `open`; (3) `readSeen` приймає `v !== 1`; (4) `byClaude` в `comments-view.js` без `resolveReason !== MANUAL_REASON` (тест поправки 18).

- [ ] **Step 9: Commit** — `feat(shell): модель «нових», фільтр адресата, доручення в картці, числа острівця/вкладок/дерева`.

---

### Task 9: Проводка в оболонці

**Files:**
- Modify: `app/app.js`, `app/shell-palette.js`, `app/styles.css`, `app/spaces-model.js` (якщо `effectiveCommentMode` більше ніхто не вживає), `app/i18n.js` (мертві ключі)
- Test: `tests/shell-palette.test.mjs` (+ еталони палітри), `tests/test_comments_role.py` (пара `dc-cmt-aud`), живі `tests/live/comments-panel.test.mjs`, `tests/live/overview-comments.test.mjs`

- [ ] **Step 1: Прибрати перемикання каналу** (поправка 10): `commentMode`, `effMode`, `setAudience` (і його довгий коментар), приймач `dc-audience`, `BAR_ACTIONS.aud`, `BAR_ACTIONS.cmtch`, поле `commentMode` у `barState()` і `paletteState()`, пункти `aud-local`/`aud-project` у `app/shell-palette.js` (разом із коментарем над ними), `&ch=${effMode()}` у `frame.src` (обидва рядки біля `host=1`). `effectiveCommentMode` у `spaces-model.js` і його тест — прибрати, якщо `grep -rn effectiveCommentMode app tests` показує лише їх. Мертві ключі i18n (`cmtChannel`, `cmtChLocal`, `cmtChTeam`, `audLocal`, `audProject`, `audCur`, а також ті, що `grep` покаже невживаними) — прибрати з обох мов. Еталони палітри — перезняти тим самим способом, що в Б1 (подивитись `git show 2147bf3 --stat` і повідомлення коміту, яким скриптом їх знімали).

- [ ] **Step 2: Стан і ключі.** Біля `let cmtOpen…`:
  ```js
  /** Фільтр панелі «Усі / Для Claude / Команда» (Б2) — памʼятається на вікно. */
  let cmtFilter = (() => { try { const v = localStorage.getItem('dc-cmt-filter'); return FILTERS.includes(v) ? v : 'all'; } catch (e) { return 'all'; } })();
  /** Причина, з якої командні недоступні (`L.store.teamDown`), або `null`. */
  let cmtTeamDown = null;
  /** «Нові від команди» цього відкриття панелі (поправка 13), id попереднього знімка (поправка 14), число нових для острівця. */
  const cmtFresh = new Set();
  let cmtPrevIds = null;
  let cmtNewsN = 0;
  let cmtNewsPages = {};
  /** Ключ памʼяті адресата — спільний із рамкою (`HOST_ARG` у `serve.py`; пару приколює `test_comments_role`). */
  const CMT_AUD_KEY = 'dc-cmt-aud';
  ```
  Імпорти: `FILTERS`, `audOf` з `comments-model.js`; усе з `comment-news.js`.

- [ ] **Step 3: «Нові».**
  ```js
  /** Імʼя автора цього вікна — те, що пише коментатор (той самий origin); нема — «мого» нема (поправка 15). */
  const myName = () => { try { return localStorage.getItem('comment-layer:user') || ''; } catch (e) { return ''; } };
  const cmtSeenKey = () => seenKey(spaceNow()?.id, currentTaskId);
  function loadSeen(key) { try { return readSeen(localStorage.getItem(key)); } catch (e) { return null; } }
  function saveSeen(key, set) { try { localStorage.setItem(key, writeSeen(set)); } catch (e) {} }
  /** Знімок коментатора поточного виду змінився: маркер, свіжі, число острівця, дерево, тост. */
  function cmtNewsUpdate() {
    const all = cmtSnap && Array.isArray(cmtSnap.comments) ? cmtSnap.comments : null;
    if (!all || !currentTaskId) { cmtNewsN = 0; cmtNewsPages = {}; return; }
    const team = teamOf(all);
    const key = cmtSeenKey();
    let seen = loadSeen(key);
    if (!seen) { seen = baseline(team); saveSeen(key, seen); }
    const fresh = team.filter((c) => isNew(c, seen, myName()));
    const came = arrived(cmtPrevIds, fresh);
    cmtPrevIds = new Set(all.map((c) => c.id));
    if (cmtOpen) {
      for (const c of fresh) cmtFresh.add(c.id);
      if (fresh.length) saveSeen(key, markSeen(seen, fresh.map((c) => c.id)));
      cmtNewsN = 0; cmtNewsPages = {};
      return;
    }
    cmtNewsN = fresh.length;
    cmtNewsPages = newsByPage(fresh);
    if (came.length) newsToast(came);
  }
  function newsToast(came) {
    const last = came[came.length - 1];
    notice('cmt-news', came.length === 1 ? t('cmtNewToast', last.author || '—') : t('cmtNewToastN', came.length), [{
      act: 'cmtshownew', label: t('cmtShowNew'),
      run: () => { dropNotice('cmt-news'); setCommentsOpen(true); cmtSel = last.id; paintComments(); cmtLayer()?.focus(last.id); },
    }]);
  }
  ```
  Виклик `cmtNewsUpdate()` — у `onCommentsEvent` після кожного присвоєння `cmtSnap` (`ready`, `change`) і в `cmtViewSwitch` після `cmtSnap = …`; потім `paintComments()` (він уже кличе `paintIsland`) і перемальовка дерева (знайти функцію, що малює панель сторінок, — пошук `panelHTML(` — і кликати її, коли `cmtNewsPages` змінились: порівняти `JSON.stringify` з попереднім).
  `setCommentsOpen(on)`: при `on` — `cmtNewsUpdate()` спершу НЕ кличемо; натомість: `const key = cmtSeenKey(); const seen = loadSeen(key) || new Set(); const fresh = teamOf(cmtSnap?.comments).filter((c) => isNew(c, seen, myName())); fresh.forEach((c) => cmtFresh.add(c.id)); if (fresh.length) saveSeen(key, markSeen(seen, fresh.map((c) => c.id))); cmtNewsN = 0; cmtNewsPages = {}; dropNotice('cmt-news');`; при `!on` — `cmtFresh.clear()`. Зміна задачі (місце, де скидається `cmtSnap` при переході на іншу задачу) і `cmtViewSwitch` — `cmtFresh.clear(); cmtPrevIds = null;`.
  `paintIsland` (знайти, де кличеться `islandToolsHTML`): передати `commentsNew: cmtNewsN`. Рядки дерева (місце з `count: s ? …`, ~`app.js:4398`): `news: cmtNewsPages[p.id] || 0`.
  **Свіжість локальних (спека Б2.1):** `const cmtRefreshLocal = () => { try { cmtLayer()?.store?.refreshLocal?.(); } catch (e) {} };` — кликати в `setCommentsOpen(true)` і на `window` `focus` (один слухач; той самий, що в T10 кличе опит вкладок, — або два окремі, як чистіше).

- [ ] **Step 4: Панель.** `paintComments` → `commentsPanelHTML({ snapshot: cmtSnap, query: cmtQuery, selectedId: cmtSel, editingId: cmtEditing, expanded: cmtExpanded, filter: cmtFilter, dual: !noTeamComments(), teamDown: cmtTeamDown, fresh: cmtFresh, down: cmtSnap ? null : cmtDown() })`. `cmtTeamDown` — у `onCommentsEvent` на `ready` і в `cmtViewSwitch`: 
  ```js
  /** Причина падіння командного з комбінованого сховища шару (`DeaiDualStore.teamDown`), або `null`. */
  function readTeamDown(L) { try { const v = L && L.store && L.store.teamDown; return typeof v === 'string' && v ? v : null; } catch (e) { return null; } }
  ```
  `dropFrameCmt` — `cmtTeamDown = null` (у «Огляді» — лише коли скидається шар полотна).
  `BAR_ACTIONS`:
  ```js
    cmtfilter: (f) => { if (!FILTERS.includes(f)) return; cmtFilter = f; try { localStorage.setItem('dc-cmt-filter', f); } catch (e) {} paintComments(); },
    cmtassign: (id) => { cmtLayer()?.setMeta?.(id, { assignee: 'claude' }); },
    cmtunassign: (id) => { cmtLayer()?.setMeta?.(id, { assignee: null }); },
  ```
  (перевірити, що делегація з `#cmt-panel` пропускає ці `data-act` так само, як `cmtres`/`cmtdel`).

- [ ] **Step 5: «Огляд».** У `env` для `overviewComments` (`app.js` ~5252): `channel: () => (noTeamComments() ? 'local' : 'dual')`; `audiences: () => [{ id: 'local', label: t('audChipLocal'), icon: 'bot', color: '#7C6CF0' }, { id: 'project', label: t('audChipTeam'), icon: 'team', note: t('audChipTeamNote') }]`; `onAudience` — прибрати; у `host` — `defaultAudience: () => { try { return localStorage.getItem(CMT_AUD_KEY); } catch (e) { return null; } }`, `onAudiencePick: (id) => { try { localStorage.setItem(CMT_AUD_KEY, id); } catch (e) {} }`. Колір `#7C6CF0` — і в Python (`DUAL_AUDIENCES_JS`), і тут: пару приколює тест у `tests/test_comments_role.py` (рядок `#7C6CF0` є в обох файлах) — додати разом із парою `dc-cmt-aud`. Якщо `css-guards`/інший охоронець забороняє hex у `app/*.js` — винести в `const LOCAL_PIN_COLOR = '#7C6CF0'` з коментарем «колір піна коментатора (не CSS оболонки)» і, за потреби, дозволити в охоронці точково; рішення — у звіт.

- [ ] **Step 6: Стилі** (`app/styles.css`, лише токени):
  ```css
  .isl-count--new{background:var(--open);color:var(--on-sel)}
  .tab-news{margin-left:4px;min-width:15px;height:15px;padding:0 4px;border-radius:999px;background:var(--open);color:var(--on-sel);font-size:10px;font-weight:600;line-height:15px;text-align:center;box-sizing:border-box;flex:none}
  .row-news{flex:none;margin-left:4px;min-width:15px;height:15px;padding:0 4px;border-radius:999px;background:var(--open);color:var(--on-sel);font-size:10px;font-weight:600;line-height:15px;text-align:center;box-sizing:border-box}
  .cmt-teamdown{margin:8px 12px;padding:8px 10px;border-radius:var(--r-sm, 6px);background:color-mix(in srgb,var(--bad) 12%,transparent);color:var(--bad);font-size:12px}
  .cmt-aud{font-size:11px;color:var(--dim)}
  .cmt-aud--project{color:var(--open)}
  .cmt-badge{font-size:10px;padding:0 6px;border-radius:999px;border:1px solid var(--line2);color:var(--dim)}
  .cmt-h--new{color:var(--open)}
  ```
  (Назви токенів радіуса/ліній звірити з наявними правилами `.cmt-*` у цьому файлі; невідомий токен — охоронець червоніє.)

- [ ] **Step 7: Тести.** `tests/shell-palette.test.mjs` — пункти `aud-*` зникли (тест на їх відсутність замість старих); пара ключа `dc-cmt-aud` і кольору в `tests/test_comments_role.py`; живі `comments-panel.test.mjs` і `overview-comments.test.mjs` — прогнати; що зламалось через зниклий сегмент каналу — мігрувати (селектори `cmtch` → `cmtfilter` лише там, де тест був про форму сегмента; тести про ПЕРЕМИКАННЯ каналу — видалити з переліком у звіті й посиланням на T11, де їх замінять сценарії адресата).

- [ ] **Step 8: Прогін і мутації.** JS, Python, два живі файли — зелені. Мутації: (1) `setCommentsOpen(true)` не посуває маркер (свіжі лишаються «новими» після відкриття — тест T11 червоніє; тут — юніт-рівнем недоступно, тому мутацію довести в T11 і записати у звіт T9 як відкладену); (2) `cmtfilter` без перевірки `FILTERS.includes`; (3) `newsToast` при відкритій панелі (прибрати `return` у гілці `cmtOpen`).

- [ ] **Step 9: Commit** — `feat(shell): адресат і доручення в панелі, нові від команди (острівець, тост, дерево), без перемикача каналу`.

---

### Task 10: Числа на вкладках (`/api/comment-news`)

**Files:**
- Modify: `app/app.js`

- [ ] **Step 1: Реалізація** (поруч із `pollClaudeAll`):
  ```js
  /* Нові командні на ІНШИХ вкладках (поправка 17): лише вкладки поточного простору, крім активної (її рахує острівець), лише
     коли вікно видиме; одразу при зміні складу вкладок і на `focus`, далі раз на 90 с. Відповідь — легкі відкриті коментарі
     (`recent` модуля без знімків), «нові» рахуємо тут за тим самим маркером, що острівець. */
  const NEWS_EVERY_MS = 90000;
  let tabNews = {};
  let newsBusy = false;
  async function pollTabNews() {
    if (newsBusy || document.visibilityState !== 'visible') return;
    newsBusy = true;
    try {
      const sp = spaceNow()?.id ?? null;
      const next = {};
      for (const x of tabs) {
        if (x.id === currentTaskId || (x.space ?? null) !== sp) continue;
        let r = null;
        try {
          const res = await fetch(`/api/comment-news?task=${encodeURIComponent(x.id)}`);
          r = res.ok ? await res.json() : null;
        } catch (e) { r = null; }
        if (!r || !r.supported || !Array.isArray(r.items)) continue;
        const key = seenKey(sp, x.id);
        let seen = loadSeen(key);
        if (!seen) { seen = baseline(r.items); saveSeen(key, seen); }
        const n = r.items.filter((c) => isNew(c, seen, myName())).length;
        if (n) next[x.id] = n;
      }
      if (JSON.stringify(next) !== JSON.stringify(tabNews)) { tabNews = next; paintTabs(); }
    } finally { newsBusy = false; }
  }
  setInterval(pollTabNews, NEWS_EVERY_MS);
  window.addEventListener('focus', () => { pollTabNews(); });
  ```
  `paintTabs` → `tabsModel({…, news: tabNews})`. Після кожної зміни складу вкладок (`saveTabs()` кличуть усі місця зміни — додати `pollTabNews()` поруч із ним, або в `saveTabs` — що чистіше; рішення у звіт) і при зміні активної задачі. Активна вкладка числа не має (острівець), а при переході НА неї — її число зникає одразу (`delete tabNews[id]` + `paintTabs()`).
  Перевірити, що `x.space` справді так називається в записі вкладки (`tabs-model.js`, `upsertTab`); якщо інакше — підлаштувати.

- [ ] **Step 2: Прогін.** JS зелений; живий `tabs.test.mjs` зелений (запити `/api/comment-news` у просторі без постачальника віддають `supported:false` — вкладки без чисел).

- [ ] **Step 3: Commit** — `feat(shell): числа нових командних коментарів на вкладках`.

---

### Task 11: Живі сценарії Б2 і міграція живих тестів

**Files:**
- Create: `tests/live/_memo.mjs` (не `*.test.mjs` — допоміжний)
- Modify: `tests/live/comments.test.mjs` (бере `startMemo` з `_memo.mjs`, поведінка без змін)
- Create: `tests/live/comments-team.test.mjs`
- Delete: `tests/live/comment-audience.test.mjs`
- Modify: інші `tests/live/*.test.mjs`, що впадуть у повному прогоні

- [ ] **Step 1: Винести `startMemo`** (і потрібні йому константи) з `tests/live/comments.test.mjs` у `tests/live/_memo.mjs` без змін поведінки; `comments.test.mjs` імпортує. Прогнати `comments.test.mjs` — зелений, той самий підсумок.

- [ ] **Step 2: `tests/live/comments-team.test.mjs`** — оточення як у `comments.test.mjs` (простір із модулем `memo-comments`, задача з двома сторінками, `hermetic`-маршрутизація: усе поза 127.0.0.1 — `abort`), робоче місце відкривається через оболонку (рамка з `host=1`). Сценарії (кожен — окремий `test`; кожен чистить `localStorage` перед стартом):
  1. **Адресат і памʼять вибору:** відкрити панель (C), клік по елементу макета → у формі два чипи; натиснутий «Claude»; клік «Команді» → видно рядок-примітку; «Comment» → пін зʼявився в `memo.store` каналу задачі, рядок без `_aud`; локальний файл задачі пінa не має. Друга форма → натиснутий «Команді» (запамʼятовано, `localStorage['dc-cmt-aud'] === 'project'`).
  2. **Колір:** локальний пін (`.pin[data-aud="local"]` у тіньовому DOM рамки) має фон `rgb(124, 108, 240)`; командний — ні.
  3. **Фільтр:** засіяти 1 локальний (файл задачі) + 1 командний (`memo`) → «Для Claude» — лише локальна картка, «Команда» — лише командна, «Усі» — обидві; кнопки сегмента ≥ 28px заввишки; вибір переживає перезавантаження оболонки.
  4. **Доручення:** на командній картці «Доручити Claude» → у `memo.store` у рядка `meta.assignee === 'claude'`; бейдж «Claude» на картці; `GET /comments` тестового сервера (типово) повертає цей пін і `hidden: 0`; «Забрати в Claude» → `meta.assignee` нема, `/comments` — порожньо, `hidden: 1`, `/comments?all=1` — пін є. (Якщо в оточенні тесту `bin/inbox.py --task <задача>` запускається з тим самим `HOME`/`DEAI_HOME`, що в сервера, — один прогін `inbox.py` до й після «Забрати»; інакше лише маршрут, і в звіті — чому.)
  5. **Нові від команди:** панель закрита; після першого знімка (маркер-база) дописати командний пін іншого автора прямо в `memo.store` (`author: 'Колега'`, `meta.version` сторінки 2) → за ≤ 3 с (`memo` опитує раз на секунду): на острівці `.isl-count--new` з `1`; плашка `.cv-notice[data-notice="cmt-news"]` з «Новий коментар від Колега»; у дереві рядок сторінки 2 має `.row-news` з `1`. «Показати» → панель відкрита, розділ «Нові від команди» з карткою, бейдж острівця нейтральний (не `--new`), плашки нема. Перезавантажити оболонку → пін уже не новий (маркер збережено). Мутація (відкладена з T9): `setCommentsOpen(true)` не посуває маркер → після перезавантаження пін знову «новий» — червоно.
  6. **Свій пін не «новий»:** створити командний пін через форму (сценарій 1) → після закриття панелі й нового знімка бейдж нейтральний.
  7. **Число на вкладці:** дві задачі простору відкриті вкладками; активна — перша; у `memo.store` каналу ДРУГОЇ задачі після бази (перший опит) дописати пін колеги → `window.dispatchEvent(new Event('focus'))` → `.tab-news` на вкладці другої задачі з `1`; перейти на неї → число зникло.
  8. **Падіння командного:** маршрут Playwright `abort` для `**/api/module-client/**/memo-comments/adapter.js` (точний шлях — як у `comments.test.mjs`) → у рамці НЕМА `#cl-down`; панель показує `.cmt-teamdown` з причиною; у формі чипів нема; локальний пін ставиться й пишеться у файл задачі.
  9. **Без `host` — як було:** `/commented?it=…&ch=project` напряму (без оболонки) → ручка коментатора видна, `DeaiDualStore` у сторінці нема.

- [ ] **Step 3: `comment-audience.test.mjs` — видалити.** У звіті таблиця «охорона → де тепер»: перемикання каналу сегментом → сценарії 1, 3 (адресат і фільтр); 28px сегмента → сценарій 3; чужий `postMessage` не перемикає канал → приймача `dc-audience` більше нема (перевірка `grep -rn "dc-audience" app` — порожньо), а чужі посилки `dc-comments` стереже `comments-panel.test.mjs` (Б1); аварійний вихід ⌘K → сценарій 8 (падіння командного не валить локальних).

- [ ] **Step 4: Повний живий прогін ПОСЛІДОВНО** (фоном із логом, чекати за PID): `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/*.test.mjs > <лог> 2>&1`. Кожне падіння — розібрати: зміна поведінки Б2 (банер `__clDown` при мертвому адаптері в РОБОЧОМУ місці → тепер смуга в панелі; `ch=` у `frame.src`; пункти палітри `aud-*`) → мігрувати тест і написати в звіт, що він охороняв і де ця охорона тепер; регресія → зупинитись і доповісти контролеру (не «чинити тест»).

- [ ] **Step 5: Commit** — `test(live): Б2 — адресат, фільтр, доручення, нові від команди, падіння командного`.

---

### Task 12: Документація й версія 0.27.0

**Files:** `CHANGELOG.md`, `package.json`, `README.md`, `commenter/README.md`, `docs/modules/comments.md`, `app/modules/supabase-comments/README.md`

- [ ] **Step 1: `CHANGELOG.md`** — розділ `## [0.27.0] — <DD.MM.YYYY дня релізу>` над `[0.26.0]`, вступ англійською одним реченням, далі за зразком 0.26.0:
  - **Додано:** адресат піна у формі (Claude / Команді, примітка про видимість, памʼять вибору); фільтр панелі «Усі / Для Claude / Команда»; «Доручити Claude» / «Забрати в Claude» і бейдж; «Нові від команди» — розділ, бурштиновий бейдж острівця, плашка «Показати», число в дереві й на вкладках; смуга «Командні коментарі недоступні: …» замість банера; `inbox.py --all`; необовʼязкова функція ролі `recent` і `GET /api/comment-news`.
  - **Змінено (поведінка агента — окремим жирним пунктом першим):** «**Claude бачить лише доручені командні коментарі.** `bin/inbox.py`, `bin/state.py` і `/comments` показують локальні й доручені (`meta.assignee = "claude"`); усі — `inbox.py --all` / `/comments?all=1`.» Далі: у робочому місці один шар на обидва канали — перемикача «Claude / Команда» і параметра `ch` більше нема; номери на всіх пінах, локальні — фіолетові; `supabase-comments` 1.3.0 пише лише змінені рядки й реагує лише на події свого каналу.
  - **Не змінено:** опубліковані превʼю, `/commented` без `host=1`, дані (міграції нема, `schema.sql` той самий).
  (Розділ CHANGELOG — те саме джерело, з якого діалог оновлення показує «Що нового»: окремого тексту для діалогу не треба.)
- [ ] **Step 2: `package.json`** — `"version": "0.27.0"`.
- [ ] **Step 3: `README.md`** — розділ про коментарі: адресат, доручення, нові; `inbox.py --all`.
- [ ] **Step 4: `commenter/README.md`** — `audiences[i].color`/`note`, `host.defaultAudience`/`onAudiencePick`, `setMeta(id, patch)`, `uploadShot(id, dataUrl, comment)`; правило «чипи лише з `host` і ≥ 2 аудиторіями».
- [ ] **Step 5: `docs/modules/comments.md`** — необовʼязкова `recent(ctx, channel)` → `[{id, ts, author, status, version}]` (без важких полів; навіщо — опит вкладок); браузерне сховище: `uploadShot` може отримати третій аргумент; рекомендація писати різницею. `app/modules/supabase-comments/README.md` — 1.3.0: `recent`, запис різницею, фільтр realtime.
- [ ] **Step 6: Commit** — `docs: реліз 0.27.0 — Claude і команда разом`.

---

### Task 13: Фінальне ревʼю, релізний прогін, перевірка проти живого (контролер)

- [ ] **Step 1: Фінальне ревʼю** (один ревʼюер, Sonnet, англійський бриф) усієї гілки `main..feat/shell-comments-b2` проти спеки (Б2 + поправки цього плану): приватність (скрін і локальний фідбек не їдуть у командне; `_aud` не на диску й не в базі), трафік Supabase (запис різницею, realtime свого каналу, `recent` без важких полів), шлях без `host` байт-у-байт, публікація без комбінованого сховища, безпека розмітки (тексти лише через `esc`), охоронці доведені мутаціями. Ревʼюер працює з копією-архівом гілки, не з деревом. Знахідки → виправлення окремими комітами → повторне ревʼю.
- [ ] **Step 2: Релізний прогін:** JS (усі три набори), Python (3 discover, тимчасовий `HOME`), живі — усі ПОСЛІДОВНО. Детермінізм збірки: `cd commenter && npm ci && npm run build && cd .. && git diff --exit-code app/vendor commenter/build-stamp.json`. Охоронець забороненого списку (`DEAI_FORBIDDEN_LIST=<forbidden-list> DEAI_REQUIRE_FORBIDDEN_LIST=1`) — зелений.
- [ ] **Step 3: Локальний реліз:** злиття в `main` (fast-forward), анотований тег `v0.27.0` (автор neodisa). Живий канвас 8765 — перезапуск на 0.27.0 (зупинка за PID, `start.command >/dev/null 2>&1`, слухач — `lsof -iTCP:8765 -sTCP:LISTEN`).
- [ ] **Step 4: Перевірка проти живого** (справжня задача ЛІГИ): ⛔ командний канал ЛІГИ — ЛИШЕ ЧИТАННЯ. Спершу відкрити задачу з вкладкою мережі (DevTools / `read_network_requests`) і переконатись, що саме відкриття НЕ шле `POST`/`PATCH` у спільний Supabase (можливий одноразовий запис — дописування `meta.seq` старим пінам у `_backfillSeq`): якщо шле — зупинитись, нічого не клікати й доповісти власнику. Далі: панель показує і локальні, і командні з адресатом; фільтр; ЛОКАЛЬНИЙ пін через форму (чип «Claude») — створити, закрити, видалити; `bin/inbox.py` бачить його, а командних недоручених не показує (`--all` — показує); «Огляд» — той самий список. Доручення, «Команді» й закриття командних на живому НЕ робимо (це запис у спільне). Прибрати тестовий пін.
- [ ] **Step 5: Пуш — лише з дозволу власника** (пуш на GitHub = пігулка оновлення всій команді): перевірити `git remote get-url origin`, пушити `main` і тег `v0.27.0`; ніколи — `backup-pre-rewrite-4d1` і `fix/supabase-egress`.

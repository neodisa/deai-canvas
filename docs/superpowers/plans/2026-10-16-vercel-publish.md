# Свій Vercel (2b-1) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** модуль `vercel-publish` публікує превʼю задачі на власний Vercel людини через REST API (без Node/CLI); ядро вміє модулі «публікація за адресою»; UI показує результат і дає посилання.

**Architecture:** маніфест отримує `publish_target` (`folder`|`url`); `publish_with_module` у `app/serve.py` розгалужується: `folder` — як у 0.2.0, `url` — без теки, з записом `publish_url`/`publish_remote`; модуль — stdlib-HTTP до `api.vercel.com` (файли за SHA-1 → публікація → очікування `READY` → `alias` → перевірка → прибирання старих).

**Tech Stack:** Python 3 stdlib (`urllib`, `hashlib`, `http.server` у тестах), unittest, ES-модулі без збирача, `node:test`, Playwright.

Спека: `docs/superpowers/specs/2026-10-16-vercel-publish-design.md`. Попередній план-зразок: `docs/superpowers/plans/2026-10-14-modules-2a.md`.

## Правила репо, яких мусить триматись кожна задача

- Репо продукту `neodisa/deai-canvas` (корінь репо), гілка `main`. Автор комітів: `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit …`; повідомлення українською з рядком `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Стейджити лише свої файли. НЕ пушити.
- ⛔ Порти 8765/4317 — живі сервери власника; свої — випадкові, зупиняти лише за PID; жодного `pkill`/`killall`. Справжні `~/.deai`, `~/deai-published`, `tasks.json` не чіпати. `DEAI_HOME` у оболонці НЕ виставляти.
- ⛔ ЖОДНОГО реального запиту до Vercel у тестах: підставний API в процесі + розтяжка мережі (сокети лише на `127.0.0.1`).
- Усі прогони — через сторож памʼяті `python3 "$G" <с> <МБ> <команда>` (`G` — `scratchpad/bin/guard.py`, шлях дає координатор), послідовно; мутації — `python3 -B`, відновлення байт-у-байт.
- Рядки UI — `t('key')` в обох словниках `app/i18n.js`; `esc`; кольори — токени.
- Повний набір наприкінці: `npm test` зелений (база 0.2.0: node 1195 + inspector-core; py tests/ 1684 skip 1; bin 156; app 170).

## Файли

| Файл | Відповідальність |
|---|---|
| `app/deai_modules.py` | `publish_target` у маніфесті; коди `vercel-auth`, `vercel-busy` у `STATUS` |
| `app/serve.py` | `publish_with_module`: гілка `url`; `/api/task`: `publish_share_url`, `publish_remote` |
| `app/modules/vercel-publish/{module.json,server.py}` (нові) | REST-клієнт Vercel, `publish`, `check` |
| `app/spaces-model.js`, `app/app.js`, `app/bar-model.js`, `app/i18n.js` | плашка «Опубліковано на Vercel», посилання, застереження, тексти помилок |
| тести | `tests/test_publish_module.py` (`UrlTarget`), `tests/test_vercel_publish.py` (новий), node-тести UI, `tests/live/vercel.test.mjs` (новий) |
| `CHANGELOG.md`, `README.md`, `package.json`, спека | 0.3.0 |

---

### Task 1: ядро — модулі «публікація за адресою»

**Files:** Modify `app/deai_modules.py` (`_check_manifest` ~:266, `Module.__slots__` ~:109, `STATUS` ~:83), `app/serve.py` (`publish_with_module` ~:3328, `/api/task` ~:4242, `task_preview_gate` ~:3426); tests `tests/test_modules.py`, `tests/test_publish_module.py` (новий клас `UrlTarget` з фікстурним модулем у тимчасовій `builtin_dir`).

- Маніфест: необовʼязкове `publish_target` ∈ {`folder`, `url`}, типово `folder`; інше → `bad-manifest`. `Module.publish_target` (атрибут). Лише модулям із роллю `publish` поле має сенс; для інших — ігнорується, але валідується.
- `STATUS += {'vercel-auth': 409, 'vercel-busy': 409}`.
- `publish_with_module` для `url`:
  - без `published_root`/`folder_ok`/`bad-task-id`; лок — лише тека збірки задачі (`_task_dir_key`), зайнято → 409 `publish-busy`;
  - `ctx = module_ctx(space, prov)` один раз; `gate_pw = ctx['secrets'].get('password') or None`; `build_preview(task, tid, its, comments=False, gate_pw=gate_pw)`;
  - `build_only` → відповідь збірки (як для `folder`);
  - `task_arg = {'id': tid, 'title': …, 'dir': task['dir'], 'state': <publish_remote.state з ПЕРЕчитаної мети, якщо module збігається, інакше {}>}`; `deai_modules.call(prov, 'publish', ctx, built['dir'], task_arg)` без `timeout`;
  - перевірка результату: `url` — рядок `https://`, `urlsplit` без `username`/`password`/`fragment`, хост непорожній; `state` — `dict`, `json.dumps` ≤ 4096 байт, значення лише `str`/`int`/`float`/`bool`/`None` (рекурсивно без вкладених обʼєктів глибше 1); `verified` — `bool`; `warnings` — список рядків ≤ 5 по ≤ 300 символів. Порушення → `ModuleError('module-error')` (текст: модуль уже виконався — публікація могла відбутись).
  - ПЕРЕчитати `iterations.json`, записати `publish_url`, `published_at` (`time.strftime('%d.%m.%Y %H:%M')`, як ЛІГА), `publish_verified`, `publish_remote = {'module': prov.id, 'state': state, 'published_at': <ISO UTC>}`; `publish_local` не чіпати.
  - відповідь: `{'ok': True, 'url', 'verified', 'iterations', 'frames', 'warnings'?, 'frames_warnings'?, 'code_stale'?}`; жодних `git_autocommit`-пушу, `_registry_push`, `_overview_sync`.
- `/api/task`: `publish_remote` (без змін форми); для простору, чий постачальник `publish` — `url`-модуль: `publish_gate` (`true`, коли секрет `password` модуля непорожній) і, коли є `publish_url`, `publish_share_url` = `publish_url` + `#k=<пароль>` (`urllib.parse.quote(pw, safe='')`), без пароля — `publish_url`. Для `legacy` і `folder`-модулів цих полів нема. Нечитабельні секрети → поля відсутні (не 5xx). `task_preview_gate` для будь-якого модуля — `state:'module'` (як є).
- `folder`-гілка — БЕЗ змін (тести 0.2.0 зелені без правок).
- [ ] Тести (`UrlTarget`, фікстурний модуль `url-pub` у тимчасовій `builtin_dir`, `publish` пише, що отримав, і повертає налаштовуваний результат): маніфест (`url`/`folder`/невідоме значення → `error`); публікація пише 4 поля мети й не чіпає `publish_local`; `state` туди-назад (друга публікація отримує збережений `state`; `state` іншого модуля — не передається); валідація `url` (`http://`, з `user:pass@`, з `#frag`, порожній хост, не рядок) і `state` (> 4096, вкладений обʼєкт, не `dict`) → 502 і мета незмінна; `publish-busy` на теці збірки; `build_only`; `gate_pw` із секрету (і `''` → без гейта); `/api/task` `publish_share_url` з паролем/без, відсутній для `legacy`/`folder`; ЛІГА-шлях і `folder`-модуль — наявні тести без змін; нуль `git_autocommit`/`_registry_push`/`_overview_sync`.
- [ ] Мутації: прийняти `http://`; прибрати межу 4 КБ; записати `publish_url` для `folder`-модуля; не передати `state`; не перечитати мету; `publish_share_url` для `folder`-модуля.
- [ ] Коміт `feat(publish): модулі «публікація за адресою» — publish_target url, publish_remote, посилання з паролем`.

### Task 2: модуль `vercel-publish`

**Files:** Create `app/modules/vercel-publish/module.json` (як у спеці), `app/modules/vercel-publish/server.py`; Create `tests/test_vercel_publish.py`.

- `server.py` (stdlib; allowlist імпортів як у `static-publish`: `hashlib, json, os, re, secrets, socket, time, urllib.error, urllib.parse, urllib.request`; без `serve`/`deai_modules`/`exec`/`eval`/`__import__`):
  - `API_BASE = 'https://api.vercel.com'` (тести підміняють через `fn.__globals__`); `_req(ctx, method, path, *, body=None, headers=None, timeout=30)` — `Authorization: Bearer <token>` лише тут; JSON-відповідь; помилки мапляться: 401/403 → `ctx['ModuleError']('vercel-auth', message=…)`, 429 → `vercel-busy`, інше → `RuntimeError` з коротким текстом Vercel (`error.message`, ≤ 200), мережа (`URLError`, `socket.timeout`) → `RuntimeError('Vercel недоступний')`. Токен НІКОЛИ не потрапляє в текст винятку.
  - `team` → `teamId=<…>` якщо починається з `team_`, інакше `slug=<…>`; додається до КОЖНОГО запиту API.
  - `publish(ctx, build_dir, task)`:
    1. проєкт: `state.project`/`state.project_id` або нове `pv-<8 цифр>` (`secrets.randbelow`) з перевіркою `GET /v9/projects/<імʼя>` → має бути 404 (інакше нове імʼя, ≤ 3 спроби → `RuntimeError`);
    2. файли: обхід `build_dir` (`os.walk`, відсортовано, без симлінків — симлінк → `RuntimeError`), SHA-1/розмір, `POST /v2/files` (`Content-Type: application/octet-stream`, `x-vercel-digest`, `Content-Length`, таймаут 60) по разу на SHA-1;
    3. `POST /v13/deployments` з тілом зі спеки; `id` публікації;
    4. очікування `GET /v13/deployments/{id}` (інтервал 1,5 с — константа `POLL_S`, межа 180 с — `POLL_MAX_S`, тести ставлять малі) до `READY`; `ERROR`/`CANCELED` → `RuntimeError(errorMessage)`;
    5. адреса — найкоротший `alias`, що закінчується на `.vercel.app`; нема → `https://<url публікації>` + попередження;
    6. перевірка — `GET` адреси БЕЗ авторизації, без редиректів (власний `HTTPRedirectHandler`, що не йде далі), таймаут 20: 200 → `verified`; 401/403 чи 30x на `vercel.com` → `verified:false` + попередження про Deployment Protection; інше → `verified:false`;
    7. прибирання — `GET /v6/deployments?projectId=<id>&target=production&limit=20`, сортування за `created` спадно, `DELETE /v13/deployments/{uid}` для всіх після трьох найновіших — лише коли `projectId` публікації == `state.project_id` (або щойно створений цим викликом); збій → попередження;
    8. повертає `{'url', 'verified', 'warnings', 'state': {'project', 'project_id', 'deployment'}}`.
  - `check(ctx)`: без токена → `{'ok': False, 'error': 'no-token'}`; `GET /v2/user` (+ `GET /v2/teams/<team>` за наявності) → `ok`; `vercel-auth`/мережа → `{'ok': False, 'error': …, 'detail'}`; нічого не створює.
- [ ] Тести (підставний API — `http.server` у потоці на `127.0.0.1:0`, записує кожен запит із заголовками й тілом; розтяжка `socket.create_connection`/`getaddrinfo` пропускає лише `127.0.0.1`; справжній `catalog()` вантажить модуль зі `status=='ok'`): повний цикл (порядок запитів; `POST /v2/files` по разу на вміст; тіло публікації: `name`, `target: production`, `files[{file,sha,size}]`, `projectSettings.framework: null`); `teamId`/`slug`; очікування `READY` після кількох `BUILDING`; `ERROR` → `module-error` з текстом; тайм-аут очікування; вибір `alias`; без `alias` → адреса публікації + попередження; перевірка захисту (302 на `vercel.com/login…` → `verified:false` + попередження) і що запит перевірки — БЕЗ `Authorization`; 401 на будь-якому кроці → `vercel-auth`; 429 → `vercel-busy`; токен відсутній у всіх текстах винятків і у всіх запитах, крім заголовка `Authorization` до API; прибирання (5 старих → видалено 2, три лишились; чужий `projectId` → нуль `DELETE`; збій `DELETE` → попередження); перша публікація — `GET /v9/projects/<імʼя>` 200 → нове імʼя; симлінк у збірці → помилка до будь-якого `POST`; `check` (ok, 401, мережа, без токена, з `team`); статичний allowlist імпортів.
- [ ] Мутації: токен у запиті перевірки; токен у тексті винятку; прибрати перевірку `projectId` у прибиранні; дозволити редирект у перевірці; прийняти не-`.vercel.app` alias як основну адресу; без перевірки `GET /v9/projects` для нового імені.
- [ ] Коміт `feat(modules): vercel-publish — публікація на свій Vercel через REST API`.

### Task 3: інтерфейс

**Files:** Modify `app/spaces-model.js` (`previewTarget` ~:431, `copyUrl` ~:449, `publishErr` ~:524, нове `isRemotePublish`), `app/app.js` (дія публікації ~:1690-1725, `copylink`, `openpreview`), `app/bar-model.js` (застереження без пароля), `app/i18n.js`; node-тести (`tests/spaces-publish.test.mjs`, `tests/bar-model.test.mjs`, `tests/spaces-wiring.test.mjs`).

- `capabilities.publish` для `url`-модуля — його id (`vercel-publish`); UI дізнається тип із `/api/task`: є `publish_remote` (або відповідь публікації з `url` і без `local`) → «зовнішня модульна».
- Відповідь публікації з `url` у просторі з модулем (`!isLegacyPublish(space)`) → плашка `notice('publish-remote', t('publishRemoteDone'), …)` з «Відкрити» (`window.open(url, '_blank', 'noopener')`, лише `https:`) і «Скопіювати посилання» (`publish_share_url` після `render()`); `warnings` — другий рядок; ЛІГА-відповідь (`legacy`) — як було (`render()`).
- `copylink` для зовнішньої модульної — `task.publish_share_url` (сервер уже склав `#k=`), інакше як було; `openpreview` — `publish_url`, `noopener`.
- Застереження в дропдауні публікації: `task.publish_gate === false` (сервер дає поле лише для `url`-модуля, Task 1) → `t('publishPublicWarn')`; поля нема → нічого.
- `publishErr`: `vercel-auth` → `publishErrVercelAuth`, `vercel-busy` → `publishErrVercelBusy` (uk+en).
- Плашку `publish-remote` гасити в `resetPerTaskState` (як `publish-local`).
- [ ] Тести: модель (зовнішня модульна ціль, посилання з `publish_share_url`, лише `https:` у «Відкрити», застереження без пароля, тексти помилок), wiring-піни (`noopener`, плашка гаситься), i18n; золотий знімок ЛІГА (`tests/legacy-golden.test.mjs`) — без змін.
- [ ] Мутації: «Відкрити» приймає `javascript:`; `copylink` складає `#k=` сам; застереження для `legacy`; плашка не гаситься.
- [ ] Коміт `feat(ui): публікація на Vercel — плашка, посилання з паролем, застереження про публічне превʼю`.

### Task 4: живий тест, документи, 0.3.0

**Files:** Create `tests/live/vercel.test.mjs` (`PORT_BASE` — вільна смуга, перевірити `tests/live-ports.test.mjs`); Modify `CHANGELOG.md`, `README.md`, `package.json` (`0.3.0`), `docs/design/spaces-and-modules.md`, спека (відхилення, якщо були).

- Живий сценарій: простір без інтеграцій, `static-publish` вимкнено, `vercel-publish` увімкнено через `POST /api/module-enable` з фіктивним токеном (без `check` у мережу — `page.route`/сервер не ходить: `check` впаде з `network` — це вердикт, не помилка); `POST /api/publish` у браузері перехоплено `page.route` відповіддю `{ok:true, url:'https://pv-12345678.vercel.app', verified:true}`; плашка `publish-remote`, «Відкрити» (`popup` на ту адресу — перехоплений `page.route`), «Скопіювати посилання»; жодного запиту за межі localhost, крім перехоплених.
- Документи: розділ модуля в README (токен — де взяти, `team`, пароль, захист Vercel), CHANGELOG 0.3.0 з точними числами тестів, статус у `spaces-and-modules.md`.
- [ ] `node --test --test-concurrency=1 tests/live/vercel.test.mjs tests/live/modules.test.mjs tests/live/spaces.test.mjs` → PASS; `npm test` зелений; коміт `docs: 0.3.0 — свій Vercel (2b-1)`.

---

## Після плану (не задачі виконавців)

- Ревʼю кожної задачі (одне коло), фінальне ревʼю діапазону `v0.2.0..HEAD` (інтеграція, мережа, приватність).
- Тег `v0.3.0`, пуш `main` і тегу в `neodisa/deai-canvas`.

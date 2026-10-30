# Етап 4b-2 «Коментарі ЛІГИ через `supabase-comments`» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** простір ЛІГА веде командні коментарі через вбудований модуль `supabase-comments` (неявний постачальник);
зашитий шлях коментарів і константи `SUPABASE_URL`/`SUPABASE_KEY` зникають з ядра; адреса й ключ — у конфігу установки.
Реліз 0.10.0.

**Architecture:** `comments_provider()` і далі віддає `'legacy'` для ЛІГИ, але нова функція ядра `comments_route(space,
prov)` перетворює будь-якого постачальника на трійку `(модуль, ctx, channel)`: для ЛІГИ — вбудований `supabase-comments`,
`ctx` з конфігу установки (`_comments_legacy_ctx`, як `_vcs_legacy_ctx` у 4a) і канал `comment_channel`. Усі місця, що
розгалужувались на `'legacy'` (сторінка `/commented`, `/api/comment-config`, збірка превʼю, `ProjectComments`, `inbox`,
`state`, «Огляд»), ідуть одним шляхом модуля. Модуль 1.1.0 отримує скріншоти (`shots_bucket` → `uploadShot`), номер
ітерації в `resolve` і certifi.

**Tech Stack:** Python 3 stdlib (`unittest`, `urllib`), ванільний JS (`node:test`, `vm`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-10-30-legacy-comments-module-design.md` (+ поправки нижче). Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5), навіть якщо твоя власна модель інша. Коміт — лише з переліком шляхів;
  новий файл спершу `git add -- <шлях>`.
- В індекс додавати лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл
  `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — не чіпати й не комітити.

**Прогони й середовище**

- Кожен прогін тестів — через охоронця памʼяті: `python3 "$G" <секунд> <МБ> <команда…>`. Шлях `$G` дає контролер.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати: порти 8765 і 4317; справжні `~/.deai`, `~/deai-published`,
  `~/.gitconfig`, `tasks.json` дизайнера.
- Процеси зупиняти лише за PID. Ніколи `pkill`/`killall` за шаблоном.
- **Жодної мережі в тестах і жодного справжнього Supabase.** Модуль — через шов `_open` (як `tests/test_supabase_comments.py`);
  ядро — `mock.patch` на `serve.urllib.request.urlopen` чи підставні функції; браузер — `page.route`/`context.route`.
- Репозиторій приватний і знеособлений: у коді, тестах і документах — лише вигадані адреси (`https://demo.supabase.co`,
  `https://abcdefghijkl.supabase.co`) і ключі (`sb_publishable_test…`). Справжніх хостів, ключів, імен людей — ніде.

**Конвенції коду**

- Коментарі українською. Тексти інтерфейсу лише через `t()`, обидві мови (`UK` і `EN` у `app/i18n.js`); кирилиці в
  літералах `app/**/*.js` поза словником бути не може (`tests/i18n-literals.test.mjs`) — тексти `console.warn` в адаптері
  модуля англійською, як наявні.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs` — зелений БЕЗ `UPDATE_GOLDEN=1`. `tests/test_comments_role.py` (`GoldenPinTest`) — зелений
  БЕЗ `UPDATE_COMMENTS_GOLDEN=1`, окрім Task 5, де СВІДОМО переписуються рівно два файли (`page-legacy-project.html`,
  `config-legacy-project.json`); решта еталонів теки — побайтно ті самі (sha256 до/після у звіті).
- Кожна нова перевірка доводиться мутацією: прибрати охорону одним рядком → потрібний тест червоніє → файл відновлено
  побайтно (sha256). Мутації Python — лише `python3 -B`, з охоронцем і тайм-аутом, по одній.

**Набори тестів**

- Юніти: `npm test` (включає Python-набори `tests`, `bin`, `app`).
- Живі — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.
- Номери рядків — орієнтир («≈»): шукати за назвою функції.

---

## Поправки до спеки, знайдені під час планування

Вносяться в спеку тим самим комітом, що й план.

1. **`INTERNAL_TINT` — справді мертвий.** Жоден виклик `inject_comment_layer` не передає `internal=True` (сторінки й
   превʼю — лише основний канал; внутрішній канал читає тільки агент через `/comments`). Тому `INTERNAL_TINT` і параметр
   `internal` сніпета видаляються; у `inject_module_comment_layer` прапорця `internal` НЕ додаємо. Правку спеки про
   «сині піни» прибрати.
2. **`comments_provider()` не змінює форми.** Він і далі `(Module | 'legacy' | None, помилка)` — його кличуть десятки
   тестів і місць. Нова функція `comments_route(space, prov)` → `(module, ctx, channel)`; `channel(task, tid,
   internal=False)`. Для `'legacy'` — вбудований `supabase-comments`, `_comments_legacy_ctx()`, `comment_channel`.
3. **`deai_modules.comments_client(space, prov, ctx=None)`** — необовʼязковий готовий `ctx` (для ЛІГИ — з конфігу
   установки, без `space.json` і `secrets.json`).
4. **Номер ітерації отримує лише вбудований `supabase-comments`.** Свій модуль простору (3c) міг оголосити
   `resolve(ctx, channel, id, reason)` — зайвий аргумент його зламав би. `ProjectComments.takes_iteration` — `True`, коли
   модуль вбудований `supabase-comments` (у ЛІГИ — завжди).
5. **`build_preview(comments=True)` зникає:** лишаються `False` і словник модуля; `True` → `ValueError` (як `'legacy'`).
6. **Новий код каркаса `comments-unconfigured` (409)** — нема `supabase_url`/`supabase_key`. Клієнт показує код сирим (як
   решту кодів у `errCommentConfig`), окремий текст не потрібен.
7. **Еталон старого адаптера для паритетних тестів.** `app/vendor/supabase-adapter.min.js` переїжджає (`git mv`) у
   `tests/fixtures/legacy-comments/supabase-adapter.min.js`: з ним звіряються форма рядків і адреси скріншотів.
8. **Ще свідомі відмінності** (дописати в розділ спеки): `inbox resolve --dry-run` друкує однаковий для всіх просторів
   рядок `[dry-run] Supabase: resolve <канал> <id> Іт.N «причина»` замість сирого PATCH; `state` пише «проєктні: не
   дістати (<код>)» замість тихого `0`, коли Supabase ЛІГИ не відповів.

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `app/modules/supabase-comments/server.py` | `shots_bucket` (`_bucket`, `client_config`, `check`), `resolve(…, iteration=None)`, TLS certifi в `_opener` |
| `app/modules/supabase-comments/module.json` | налаштування `shots_bucket`, версія 1.1.0 |
| `app/modules/supabase-comments/adapter.js` | `uploadShot`, коли в конфігу є `shotsBucket` |
| `app/deai_modules.py` | `comments_client(…, ctx=None)`, код `comments-unconfigured` у `STATUS` |
| `app/serve.py` | `supabase_config()` з конфігу установки; `COMMENTS_MODULE`, `LEGACY_SHOTS_BUCKET`, `_comments_legacy_ctx`, `comments_route`; `ProjectComments`, `_commented`, `_comment_config`, `publish_comments(space, task, tid, …)`, `build_preview` без `True`; 4c-споживачі на `supabase_config()`; геть: `SUPABASE_URL`/`SUPABASE_KEY`, `COMMENT_SNIPPET`, `inject_comment_layer`, `INTERNAL_TINT`, `supabase_pins` |
| `bin/inbox.py`, `bin/state.py` | через `ProjectComments` без `legacy=`; геть `patch_project_pin`, `project_body`, `_open_pins` |
| `bin/overview_push.py` | `_supabase()` без конфігу — зрозуміла помилка |
| `bin/import_preview.py` | заморожені маркери старого сніпета |
| `app/overview-comments.js`, `app/index.html` | без гілки `SB_JS`/`CommentLayerSupabase`; без старого адаптера |
| `app/vendor/supabase-adapter.min.js` | → `tests/fixtures/legacy-comments/supabase-adapter.min.js` |
| `tests/fixtures/legacy-comments/before-4b2.json` (новий) | знімок поведінки 0.9.0 (Task 1) |
| `tests/fixtures/legacy-comments/old-snippet-page.html` (новий) | сторінка зі старим сніпетом для `import_preview` (Task 1) |
| `tests/test_legacy_comments.py` (новий) | диференційний тест і нові тести ядра |
| тести, що приколюють старий шлях | Task 4–6 (переліки — у задачах) |
| `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `docs/modules/comments.md`, `tasks.example.json`, `package.json` | Task 7 |

---

### Task 1: знімок поведінки 0.9.0 (до будь-яких змін коду)

**Files:**
- Create: `tests/fixtures/legacy-comments/before-4b2.json`, `tests/fixtures/legacy-comments/old-snippet-page.html`
- Скрипт запису — у scratchpad контролера (НЕ в репо: він кличе функції, яких після 4b-2 не буде).

Знімок рахується на НЕЗМІНЕНОМУ коді (HEAD = коміт плану). Кожне значення — нормалізоване, щоб Task 4–5 могли
порахувати те саме новим кодом і порівняти.

- [ ] **Step 1: Скрипт `record_before.py`** (у теці, яку дасть контролер), запуск з кореня репо `python3 -B <скрипт>`.
  Скрипт ставить `DC_NO_OVERVIEW=1`, тимчасовий `DC_TASKS_FILE` (фікстура з однією задачею `t1`: `comment_project:
  "proj/alpha"`, і другою `t2` без `comment_project`), імпортує `serve` з `app/` і пише JSON:

```python
import json, os, re, sys, tempfile
from unittest import mock

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
tmp = tempfile.mkdtemp()
os.environ['DC_NO_OVERVIEW'] = '1'
os.environ['DC_TASKS_FILE'] = os.path.join(tmp, 'tasks.json')
with open(os.environ['DC_TASKS_FILE'], 'w') as f:
    json.dump({'tasks': {'t1': {'comment_project': 'proj/alpha'}, 't2': {}}}, f)
import serve  # noqa: E402

out = {}
SNIP = re.compile(r"projectId: '([^']*)', storage: store,\s*version: '([^']*)'")


def page_facts(html):
    m = SNIP.search(html)
    return {'channel': m.group(1), 'version': m.group(2),
            'audiences': 'audiences:' in html, 'inspector': 'inspector' in html and '/inspector.js' in html}


# 1. Канали ЛІГИ (comment_channel) — основний і внутрішній.
out['channels'] = {
    't1': serve.comment_channel({'comment_project': 'proj/alpha'}, 't1'),
    't1_internal': serve.comment_channel({'comment_project': 'proj/alpha'}, 't1', internal=True),
    't2': serve.comment_channel({}, 't2'),
    't2_internal': serve.comment_channel({}, 't2', internal=True),
}
# 2. Сніпет сторінки: робоче місце (інспектор + аудиторії) і превʼю (без них).
work = serve.inject_comment_layer('<html><body></body></html>', 'proj/alpha', '/app/vendor', version='1/main',
                                  inspector=True, audiences=True)
pub = serve.inject_comment_layer('<html><body></body></html>', 'dc/t2', '../comment-layer', version='2/kartka')
out['page_work'] = page_facts(work)
out['page_publish'] = page_facts(pub)
# 3. Піни агента: що бачить inbox із рядків Supabase (шлях ЛІГИ — supabase_pins).
ROWS = [
    {'id': 'c1', 'text': 'Збільшити відступ', 'status': 'open', 'author': 'A', 'ts': '30.10.2026 10:00',
     'meta': {'version': '1/main', 'shotUrl': 'https://demo.supabase.co/x.jpg'}, 'born_v': 1, 'fp': {'tag': 'div'},
     'html_snapshot': {'text': 'x'}, 'resolved_v': None, 'resolve_reason': None},
    {'id': 'c2', 'text': 'Готово', 'status': 'resolved', 'author': 'B', 'ts': '30.10.2026 11:00',
     'meta': None, 'born_v': 1, 'fp': None, 'html_snapshot': None, 'resolved_v': 2, 'resolve_reason': 'зроблено'},
]


class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status = json.dumps(body).encode(), status

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen = []


def fake_urlopen(req, timeout=None, context=None):
    seen.append({'method': req.get_method(), 'url': req.full_url,
                 'body': json.loads(req.data) if req.data else None,
                 'headers': {k.lower(): v for k, v in req.header_items()}})
    return _Resp(ROWS if req.get_method() == 'GET' else [])


with mock.patch.object(serve.spaces, 'integrations_on', return_value=True), \
        mock.patch.object(serve.spaces, 'require_integrations', return_value=None), \
        mock.patch('urllib.request.urlopen', fake_urlopen):
    pins = serve.ProjectComments(None).pins({'comment_project': 'proj/alpha'}, 't1')
    out['pins'] = pins
    out['pins_query_channel'] = re.search(r'project_id=eq\.([^&]+)', seen[-1]['url']).group(1)
    import inbox  # noqa: E402
    seen.clear()
    inbox.patch_project_pin('c1', 3, 'виправлено')
    out['resolve'] = {'id_filter': re.search(r'id=eq\.([^&]+)', seen[-1]['url']).group(1),
                      'body': seen[-1]['body']}
    # 4. Тиша Teams: шлях, метод, тіло, ключ = ключ конфігу.
    os.environ.pop('DC_TASKS_FILE')
    os.environ.pop('DC_NO_OVERVIEW')
    seen.clear()
    serve.teams_rpc('teams_mute_state', {})
    url, key = serve.supabase_config()
    r = seen[-1]
    out['teams_rpc'] = {'path': r['url'][len(url):], 'method': r['method'], 'body': r['body'],
                        'apikey_is_config': r['headers'].get('apikey') == key,
                        'bearer_is_config': r['headers'].get('authorization') == 'Bearer ' + key}

json.dump(out, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
```

  Якщо якийсь виклик падає на поточному коді (інша сигнатура, інший шов мережі) — ПІДЛАШТУВАТИ скрипт під код, а не код
  під скрипт, і записати в звіті, що саме змінено. `teams_rpc` під `DC_TASKS_FILE` кидає — тому оточення знімається перед
  ним; мережі все одно нема (`urlopen` підмінено).

- [ ] **Step 2: Запис.** `python3 -B <скрипт> tests/fixtures/legacy-comments/before-4b2.json`. Переглянути файл:
  `channels.t1 == "proj/alpha"`, `channels.t2_internal == "dc/t2/internal"`, `page_work.channel == "proj/alpha"`,
  `resolve.body == {"status": "resolved", "resolved_v": 3, "resolve_reason": "виправлено"}`, два піни. Значень справжніх
  хостів/ключів у файлі бути не може (константи в репо — заглушки `REDACTED`; `teams_rpc` записує лише шлях і булеві).

- [ ] **Step 3: Сторінка зі старим сніпетом для `import_preview`.** Тим самим інтерпретатором:

```python
html = serve.inject_comment_layer('<html><head><title>x</title></head><body><main>макет</main></body></html>',
                                  'chan', '../comment-layer', version='1/kartka')
open('tests/fixtures/legacy-comments/old-snippet-page.html', 'w', encoding='utf-8').write(html)
```

  (рівно ті аргументи, що в `bin/test_import_preview.py` ≈38; якщо там інший HTML — узяти його).

- [ ] **Step 4: Коміт.**

```bash
git add -- tests/fixtures/legacy-comments/before-4b2.json tests/fixtures/legacy-comments/old-snippet-page.html
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(4b-2): знімок поведінки коментарів ЛІГИ 0.9.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/fixtures/legacy-comments/before-4b2.json tests/fixtures/legacy-comments/old-snippet-page.html
```

---

### Task 2: модуль `supabase-comments` 1.1.0 — скріншоти, ітерація, TLS

**Files:**
- Modify: `app/modules/supabase-comments/server.py`, `app/modules/supabase-comments/module.json`,
  `app/modules/supabase-comments/adapter.js`, `app/modules/supabase-comments/README.md`
- Test: `tests/test_supabase_comments.py`, `tests/supabase-comments-adapter.test.mjs`

- [ ] **Step 1: Падаючі тести Python** (у `tests/test_supabase_comments.py`, на наявній базі `Base`/шва `_open`):
  - `ClientConfigTest.test_shots_bucket_in_config`: `settings={'url': U, 'shots_bucket': 'overview-thumbs'}` →
    `client_config` == `{'url': U, 'key': K, 'shotsBucket': 'overview-thumbs'}`; без `shots_bucket` / `''` / `'  '` —
    ключа `shotsBucket` нема.
  - `ClientConfigTest.test_bad_shots_bucket`: `'Overview'`, `'a/b'`, `'../x'`, `'-x'`, `'x'*64`, `5` → `bad-settings`,
    текст без значення.
  - `CheckTest.test_bad_shots_bucket_verdict`: `check` з поганим кошиком → `{'ok': False, 'error': 'bad-settings', …}`
    без мережі (жодного `_open`).
  - `ResolveTest.test_iteration_sets_resolved_v`: `resolve(ctx, ch, 'c1', 'r', 3)` → тіло `{'status': 'resolved',
    'resolve_reason': 'r', 'resolved_v': 3}`; `iteration=None`, `0`, `-1`, `True`, `'3'`, `2.0` → без `resolved_v`.
  - `StaticTest`: сигнатура `resolve` → `['ctx', 'channel', 'id', 'reason', 'iteration']` (оновити наявну перевірку
    сигнатур); `_opener` має `HTTPSHandler` з контекстом (перевірити `any(isinstance(h, urllib.request.HTTPSHandler)
    for h in g['_opener'].handlers)`).
  - `CatalogTest`: версія `1.1.0`, налаштування `shots_bucket` (`type: text`, `required: false`).

- [ ] **Step 2: Прогін — червоні.** `python3 "$G" 300 2048 python3 -m unittest tests.test_supabase_comments -v`

- [ ] **Step 3: Реалізація `server.py`.** Біля `_KEY_RE`:

```python
#: Кошик Storage для скріншотів пінів (налаштування `shots_bucket`): правило імені кошика Supabase, лише нижній регістр.
_BUCKET_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,62}', re.ASCII)
_BAD_BUCKET = 'shots_bucket: імʼя кошика Storage — малі латинські літери, цифри, «-» і «_», до 63 знаків'
```

  Після `_need_key`:

```python
def _bucket(ctx):
    """Кошик скріншотів пінів або `''` (налаштування нема чи порожнє — скріншоти не вантажимо). Інше — `bad-settings`."""
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    raw = st.get('shots_bucket') if isinstance(st, dict) else None
    if raw is None or (isinstance(raw, str) and not raw.strip(' \t\r\n')):
        return ''
    if not isinstance(raw, str) or not _BUCKET_RE.fullmatch(raw.strip(' \t\r\n')):
        raise _error(ctx, 'bad-settings', _BAD_BUCKET)
    return raw.strip(' \t\r\n')
```

  `client_config`:

```python
def client_config(ctx):
    """ПУБЛІЧНА конфігурація для сторінок: канонічна адреса проєкту, публічний ключ і (коли задано) кошик скріншотів
    `shotsBucket` — адаптер тоді вміє `uploadShot`. У мережу не ходить."""
    cfg = {'url': _base(ctx), 'key': _need_key(ctx)}
    bucket = _bucket(ctx)
    if bucket:
        cfg['shotsBucket'] = bucket
    return cfg
```

  `resolve` — новий необовʼязковий аргумент (docstring модуля оновити: «`resolved_v` — коли ядро передало номер
  ітерації»):

```python
def resolve(ctx, channel, id, reason, iteration=None):  # noqa: A002 — імена аргументів ролі
    channel = _need_text(ctx, channel, 'канал коментарів')
    id = _need_text(ctx, id, 'id коментаря')
    body = {'status': 'resolved'}
    if isinstance(reason, str) and reason:
        body['resolve_reason'] = _utf8(reason)
    if type(iteration) is int and iteration >= 1:     # `bool` — підклас `int`: `True` не номер ітерації
        body['resolved_v'] = iteration
    …решта без змін…
```

  `check` — одразу після перевірки `_base`:

```python
    try:
        _bucket(ctx)
    except Exception as e:  # noqa: BLE001 — `bad-settings`: вердикт, а не виняток
        return {'ok': False, 'error': 'bad-settings', 'detail': _clean(getattr(e, 'message', None) or e, '')}
```

  TLS (замість `_opener = urllib.request.build_opener(_NoRedirect)`):

```python
def _tls():
    """Перевірений TLS: сховище certifi, коли пакет є (Python з python.org на macOS не бачить системного), інакше типове."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — нема certifi чи зіпсований: типовий контекст
        return ssl.create_default_context()


_opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_tls()))
```

  `UA = 'deai-canvas-supabase-comments/1.1'`.

- [ ] **Step 4: `module.json`** — версія `1.1.0`, третє налаштування:

```json
   {"key": "shots_bucket", "type": "text", "label": "Кошик Storage для скріншотів пінів (необовʼязково)", "required": false}
```

- [ ] **Step 5: Падаючі тести адаптера** (`tests/supabase-comments-adapter.test.mjs`; у світ `world()` додати підставний
  `fetch`, що записує виклики й відповідає `{ok, status, blob()}` за опцією `upload: "ok" | "fail" | "reject"`):
  - без `shotsBucket` у cfg — у сховища НЕМА `uploadShot` (`typeof store.uploadShot === "undefined"`);
  - з `shotsBucket: "overview-thumbs"`: `uploadShot("c1", "data:image/jpeg;base64,AAAA")` → один `fetch(dataUrl)` і один
    `POST ${URL}/storage/v1/object/overview-thumbs/comment-shots/c1.jpg` із заголовками `apikey`, `Authorization: Bearer`,
    `Content-Type: image/jpeg`, `x-upsert: true`, `Cache-Control: 3600`; результат —
    `${URL}/storage/v1/object/public/overview-thumbs/comment-shots/c1.jpg` (рівно форма старого адаптера: тест читає
    `tests/fixtures/legacy-comments/supabase-adapter.min.js` після Task 4 — до того шлях `app/vendor/…`, тож порівняння
    форми робити рядками-літералами, а не читанням файла);
  - `uploadShot` з `"https://x/y.png"`, `""`, `null`, id `"../x"`, `"a b"` → `null` без жодного `fetch`;
  - відповідь `ok: false` → `null` + `console.warn` англійською без ключа; відхилений `fetch` → `null`, не кидає;
  - після `close()` → `null` без `fetch`;
  - `shotsBucket` з поганим іменем (`"A/B"`) → `uploadShot` нема.

- [ ] **Step 6: Реалізація `adapter.js`** — у `create`, після `var refetchTimer = null;`:

```js
    var SHOT_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;      // той самий білий список, що `_AGENT_ID` ядра
    var bucket = typeof cfg.shotsBucket === 'string' && /^[a-z0-9][a-z0-9_-]{0,62}$/.test(cfg.shotsBucket) ? cfg.shotsBucket : '';
    var base = String(cfg.url).replace(/\/+$/, '');

    /* Скріншот піна → Storage (`<bucket>/comment-shots/<id>.jpg`, upsert); результат — публічна адреса або null. Форма
       адрес і заголовків — як у старого адаптера ЛІГИ: її бере картка Teams із `meta.shotUrl`. Ніколи не кидає. */
    function uploadShot(id, dataUrl) {
      if (closed || typeof id !== 'string' || !SHOT_ID.test(id) || typeof dataUrl !== 'string' || !/^data:image\//.test(dataUrl)) {
        return Promise.resolve(null);
      }
      var path = 'comment-shots/' + id + '.jpg';
      var type = (dataUrl.match(/^data:([^;,]+)/) || [0, 'image/jpeg'])[1];
      return Promise.resolve().then(function () { return fetch(dataUrl); })
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          return fetch(base + '/storage/v1/object/' + bucket + '/' + path, {
            method: 'POST',
            headers: { apikey: cfg.key, Authorization: 'Bearer ' + cfg.key, 'Content-Type': type, 'x-upsert': 'true', 'Cache-Control': '3600' },
            body: blob
          });
        })
        .then(function (res) {
          if (res && res.ok) return base + '/storage/v1/object/public/' + bucket + '/' + path;
          warn('shot upload failed', 'HTTP ' + (res && res.status));
          return null;
        })
        .catch(function (e) { warn('shot upload failed', e); return null; });
    }
```

  і в обʼєкті сховища замість `return { … }` — `var store = { … }; if (bucket) store.uploadShot = uploadShot; return store;`.
  Шапку файла доповнити: `cfg = { …client_config (url, key[, shotsBucket]), channel, onChange }`, `store` — `[uploadShot]`.

- [ ] **Step 7: Зелені.** `python3 "$G" 300 2048 python3 -m unittest tests.test_supabase_comments -v` і
  `python3 "$G" 300 2048 node --test tests/supabase-comments-adapter.test.mjs tests/supabase-comments-bundle.test.mjs`.
  Мутації (по одній, sha256 відновлення): `type(iteration) is int` → `isinstance(iteration, int)` (червоніє `True`);
  прибрати `_bucket(ctx)` із `check`; у адаптері прибрати `SHOT_ID.test(id)`; `if (bucket)` → `if (true)`.

- [ ] **Step 8: README модуля** — розділ «Скріншоти пінів» (`shots_bucket`, публічний кошик, політика вставки для ролі
  `anon` — текст «налаштуйте у Storage → Policies», без SQL) і рядок про `resolved_v`.

- [ ] **Step 9: Коміт** шляхами: чотири файли модуля й два тести.

---

### Task 3: конфіг установки — `supabase_config()`; константи геть

**Files:**
- Modify: `app/serve.py` (`SUPABASE_URL`/`SUPABASE_KEY` ≈128, `supabase_config` ≈132, `_team_fetch` ≈1632, `teams_rpc` ≈2158,
  `inject_comment_layer` ≈2542, `supabase_pins` ≈2143, `_comment_config` ≈5727, `_overview_sync` ≈6974),
  `app/deai_modules.py` (`STATUS`), `bin/inbox.py` (`patch_project_pin`, dry-run), `bin/overview_push.py` (`_supabase`)
- Test: `tests/test_legacy_comments.py` (новий), `bin/test_overview_push.py`, тести, що імпортують `SUPABASE_URL`/`SUPABASE_KEY`

Після цієї задачі старий шлях коментарів ще живий, але бере адресу й ключ з `supabase_config()`.

- [ ] **Step 1: Падаючі тести** `tests/test_legacy_comments.py` → клас `SupabaseConfigTest` (тимчасовий `DC_TASKS_FILE`,
  `mock.patch.dict(os.environ, …, clear=False)` з викинутими `SUPABASE_URL`/`SUPABASE_KEY`):
  - корінь `tasks.json` з `supabase_url: "https://demo.supabase.co/"`, `supabase_key: "sb_publishable_test"` →
    `("https://demo.supabase.co", "sb_publishable_test")`;
  - нема в файлі, є в оточенні → з оточення; є в обох → з файла; у файлі лише `supabase_url` → пара з оточення (не
    змішуються), а коли й там нема — `(None, None)`;
  - `http://…`, `''`, `5`, ключ `'   '` → `(None, None)`; файла нема / не JSON / не обʼєкт → оточення чи `(None, None)`;
  - `hasattr(serve, 'SUPABASE_URL') is False`, `hasattr(serve, 'SUPABASE_KEY') is False`;
  - `_team_fetch()` без конфігу і без `DC_TASKS_FILE`/`DC_NO_OVERVIEW` (знято в тесті) → `([], 'Supabase не налаштовано')`
    без жодного `urlopen` (підмінений, що падає);
  - `teams_rpc('teams_mute_state', {})` без конфігу (і без ізоляційних змінних, з `require_integrations` підміненим) →
    `OSError`, без `urlopen`; з конфігом → запит на `<url>/rest/v1/rpc/teams_mute_state` з `apikey` конфігу; порівняти з
    `before-4b2.json["teams_rpc"]` (шлях, метод, тіло, обидва булеві — `True`);
  - `deai_modules.STATUS['comments-unconfigured'] == 409`.

- [ ] **Step 2: Прогін — червоні.** `python3 "$G" 300 2048 python3 -m unittest tests.test_legacy_comments -v`

- [ ] **Step 3: Реалізація.** На місці констант (≈126-135):

```python
def supabase_config():
    """`(url, key)` проєкту Supabase простору ЛІГА з конфігу УСТАНОВКИ або `(None, None)` (4b-2: констант у коді нема).

    Джерела по черзі: корінь старого `tasks.json` (`supabase_url`, `supabase_key` — той самий файл, що несе
    `gitlab_ssh_key`), далі змінні оточення `SUPABASE_URL`/`SUPABASE_KEY`. Пара береться ЦІЛОЮ з одного джерела: адреса з
    файла й ключ з оточення не змішуються. Адреса — лише `https://` (без `/` в кінці); повну перевірку (DNS-імʼя, сервісний
    ключ) робить модуль `supabase-comments`. Кешу нема: файл маленький. Значень — ні в текстах, ні в журналах."""
    try:
        cfg = load_legacy_tasks()
    except (OSError, ValueError):
        cfg = None
    cfg = cfg if isinstance(cfg, dict) else {}
    for url, key in ((cfg.get('supabase_url'), cfg.get('supabase_key')),
                     (os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))):
        if isinstance(url, str) and isinstance(key, str) and url.strip().startswith('https://') and key.strip():
            return url.strip().rstrip('/'), key.strip()
    return None, None
```

  `load_legacy_tasks` визначено нижче в модулі — це нормально (виклик під час виконання). Споживачі — `url, key =
  supabase_config()` на початку місця використання:
  - `_team_fetch`, гілка `else`: `url, key = supabase_config()`; `if url is None: return [], 'Supabase не налаштовано'`;
    далі `f'{url}/rest/v1/overview_projects?…'` і заголовки з `key`.
  - `teams_rpc`: після перевірки ізоляції — `url, key = supabase_config()`; `if url is None: raise OSError('Supabase не
    налаштовано')`; запит на `f'{url}/rest/v1/rpc/{name}'`.
  - `supabase_pins` (живе до Task 4): `url, key = supabase_config()`; `None` → `OSError('Supabase не налаштовано')`.
  - `inject_comment_layer` (живе до Task 5): `sb_url, sb_key = supabase_config()`; `None` → `''` (сторінка однаково
    скаже банером, що база не відповіла).
  - `_comment_config`, гілка ЛІГИ (живе до Task 5): `sbUrl`/`sbKey` з `supabase_config()`; `None` → `raise
    deai_modules.ModuleError('comments-unconfigured', message='Supabase простору ЛІГА не налаштовано (supabase_url і
    supabase_key у tasks.json)')`.
  - `_overview_sync`: `url, key = supabase_config()`; `if url is None: return` (до відкриття лога); `env = {**os.environ,
    'SUPABASE_URL': url, 'SUPABASE_KEY': key}`.
  - `bin/inbox.py patch_project_pin` і dry-run: `url, key = supabase_config()`; `None` → `OSError('Supabase не
    налаштовано')` / рядок dry-run `[dry-run] Supabase не налаштовано`.
  - `bin/overview_push.py _supabase()`: після запасного `supabase_config()` — `if not (url and key): raise
    RuntimeError("Supabase не налаштовано: supabase_url і supabase_key у tasks.json або SUPABASE_URL/SUPABASE_KEY")`;
    коментар «тонкий геттер поруч із SUPABASE_URL/KEY» → «геттер конфігу установки (`serve.supabase_config`)».
  - `deai_modules.STATUS`: `'comments-unconfigured': 409` (коментар: «простір ЛІГА без адреси/ключа Supabase у конфігу
    установки»).

- [ ] **Step 4: Тести, що бачили константи.** `grep -rn "SUPABASE_URL\|SUPABASE_KEY" tests bin/test_*.py app/test_*.py`:
  кожне `serve.SUPABASE_URL`/`serve.SUPABASE_KEY` замінити на значення фікстури (покласти `supabase_url`/`supabase_key` у
  `tasks.json` фікстури тесту чи `mock.patch.object(serve, 'supabase_config', return_value=(U, K))`). Змінні оточення в
  `bin/test_overview_push.py` лишаються (оточення — законне джерело). Додати тест: `_supabase()` без оточення й без конфігу
  → `RuntimeError` з текстом «не налаштовано», без значень.

- [ ] **Step 5: Зелені + мутації.** `python3 "$G" 900 4096 npm test`. Мутації: у `supabase_config` прибрати
  `.startswith('https://')`; змішати джерела (`cfg.get('supabase_url') or os.environ…`); у `_team_fetch` прибрати
  `if url is None` — кожна червонить свій тест.

- [ ] **Step 6: Коміт** шляхами (`app/serve.py`, `app/deai_modules.py`, `bin/inbox.py`, `bin/overview_push.py`,
  `tests/test_legacy_comments.py`, змінені тести).

---

### Task 4: агент — ЛІГА через модуль (`comments_route`, `ProjectComments`, `inbox`, `state`)

**Files:**
- Modify: `app/serve.py` (нові `COMMENTS_MODULE`, `LEGACY_SHOTS_BUCKET`, `_comments_legacy_ctx`, `comments_route` —
  поруч із `comments_provider` ≈2663; `ProjectComments` ≈2914; геть `supabase_pins`), `app/deai_modules.py`
  (`comments_client`), `bin/inbox.py`, `bin/state.py`
- Move: `app/vendor/supabase-adapter.min.js` → `tests/fixtures/legacy-comments/supabase-adapter.min.js` — НЕ тут, а в Task 5
- Test: `tests/test_legacy_comments.py`, `tests/test_comments_agent.py`, `tests/test_inbox.py`, `tests/test_state.py`,
  `tests/test_integrations_off.py`, `tests/test_spaces_serve.py`

- [ ] **Step 1: Падаючі тести** у `tests/test_legacy_comments.py` (клас `LegacyAgentTest`; конфіг — фікстура `tasks.json` з
  `supabase_url: "https://demo.supabase.co"`, `supabase_key: "sb_publishable_test"`; мережа — підміна `_open` у глобалах
  завантаженого модуля: `deai_modules.catalog()['supabase-comments']` — подивитись, як `tests/test_supabase_comments.py`
  дістає `g` модуля, і зробити так само):
  - `_comments_legacy_ctx()` → `settings == {'url': 'https://demo.supabase.co', 'shots_bucket': 'overview-thumbs'}`,
    `secrets == {'key': 'sb_publishable_test'}`, `ModuleError` — клас ядра; без конфігу → `ModuleError` з кодом
    `comments-unconfigured`; НЕ кличе `deai_modules.module_ctx` (підмінити на `AssertionError`).
  - `comments_route(None, 'legacy')` → `(m, ctx, channel)`: `m.id == 'supabase-comments'`; `channel({'comment_project':
    'proj/alpha'}, 't1') == 'proj/alpha'`; `channel({}, 't2', internal=True) == 'dc/t2/internal'` — порівняти з
    `before-4b2.json["channels"]` (усі чотири).
  - **Диференційний, піни:** `ProjectComments(None).pins({'comment_project': 'proj/alpha'}, 't1')`, коли модуль отримує
    рядки `ROWS` (ті самі, що в Task 1 — скопіювати в тест), → список, кожен елемент якого збігається з
    `before-4b2.json["pins"]` за полями `id, text, status, author, ts, meta, born_v, fp, html_snapshot, resolved_v,
    resolve_reason` (зайві поля нового шляху дозволені — це свідома відмінність «санітарна обробка/select=*»; відсутні —
    ні). Запит модуля — з `project_id=eq.proj%2Falpha` (канал `before-4b2.json["pins_query_channel"]` у тому ж кодуванні).
  - **Диференційний, розвʼязання:** `ProjectComments(None).resolve({'comment_project': 'proj/alpha'}, 't1', 'c1',
    'виправлено', iteration=3)` → PATCH модуля з тілом, що МІСТИТЬ `before-4b2.json["resolve"]["body"]` (порядок ключів
    неважливий), і фільтром `id=eq.c1` (+ `project_id=eq.proj%2Falpha` — свідома відмінність).
  - `ProjectComments(None).kind == 'legacy'`, `.label == 'Supabase'`, `.takes_iteration is True`; для свого модуля
    простору (`origin == 'space'`) `takes_iteration is False` і `resolve` модуля кличеться з 4 аргументами (підставний
    модуль з `resolve(ctx, channel, id, reason)` не падає).
  - Без конфігу: `pins` → `ModuleError('comments-unconfigured')` (очищений `agent_error`), не `OSError`.
  - `hasattr(serve, 'supabase_pins') is False`; `inbox` не має `patch_project_pin`/`project_body`; `state` не має
    `_open_pins`.

- [ ] **Step 2: Прогін — червоні.**

- [ ] **Step 3: Реалізація ядра.** `deai_modules.comments_client`:

```python
def comments_client(space, prov, ctx=None):
    """…(docstring як був)… `ctx` — готовий `ctx` постачальника (4b-2: простір ЛІГА будує його з конфігу установки, без
    `space.json` і `secrets.json`); `None` — `_ctx(space, prov)`, як раніше."""
    …
    ctx = _ctx(space, prov) if ctx is None else ctx
```

  `serve.py`, одразу після `comments_provider`:

```python
#: Модуль, яким простір ЛІГА веде командні коментарі (4b-2) — той самий вбудований, що й у звичайних просторів.
COMMENTS_MODULE = 'supabase-comments'
#: Кошик Storage ЛІГИ для скріншотів пінів: картка Teams бере `meta.shotUrl` звідти (як старий адаптер 0.9.0).
LEGACY_SHOTS_BUCKET = 'overview-thumbs'
COMMENTS_UNCONFIGURED = 'Supabase простору ЛІГА не налаштовано (supabase_url і supabase_key у tasks.json)'


def _comments_legacy_ctx():
    """`ctx` неявного постачальника коментарів простору ЛІГА: `supabase-comments` з адресою й ключем конфігу установки
    (`supabase_config`) і кошиком скріншотів ЛІГИ. Нема конфігу — `ModuleError('comments-unconfigured')`.

    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
    справжній `~/.deai` машини (той самий урок, що `_vcs_legacy_ctx`)."""
    url, key = supabase_config()
    if url is None:
        raise deai_modules.ModuleError('comments-unconfigured', message=COMMENTS_UNCONFIGURED)
    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
            'settings': {'url': url, 'shots_bucket': LEGACY_SHOTS_BUCKET},
            'secrets': {'key': key}, 'ModuleError': deai_modules.ModuleError}


def comments_route(space, prov):
    """Як вести командні коментарі для ВЖЕ вирішеного постачальника `prov` (`Module` чи `'legacy'` з `comments_provider`):
    `(module, ctx, channel)`, де `channel(task, tid, internal=False)` — канал задачі.

    `'legacy'` (ЛІГА) — вбудований `COMMENTS_MODULE`, `_comments_legacy_ctx()` і канал `comment_channel` (`comment_project`
    чи `dc/<задача>`: на ньому історія, тиша Teams і лічильники дашборда); модуль — `module_ctx` і `channel_for`.
    Кидає `ModuleError` (`comments-unconfigured`, `module-error`, коди `module_ctx`). Не кличе код модуля."""
    if prov == 'legacy':
        try:
            m = deai_modules.catalog().get(COMMENTS_MODULE)            # лише вбудовані: без простору
        except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
            raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
        if m is None or m.status != 'ok':
            raise deai_modules.ModuleError('module-error', message=f'{COMMENTS_MODULE} module is not loaded')
        return m, _comments_legacy_ctx(), (lambda task, tid, internal=False: comment_channel(task, tid, internal=internal))
    if not isinstance(prov, deai_modules.Module):
        raise deai_modules.ModuleError('module-error', message='comments: no provider')
    return (prov, deai_modules.module_ctx(space, prov),
            lambda task, tid, internal=False: deai_modules.channel_for(space, tid, internal=internal))
```

  `ProjectComments` (таблицю в коментарі над класом оновити: `'legacy'` — «модуль `supabase-comments` з конфігом
  установки, канал `comment_channel`»):

```python
    @property
    def takes_iteration(self):
        """Чи передаємо номер ітерації в `resolve`: лише вбудованому `supabase-comments` (свій модуль простору міг оголосити
        `resolve(ctx, channel, id, reason)` — зайвий аргумент його зламав би). У ЛІГИ — завжди."""
        if self.kind == 'legacy':
            return True
        return (self.kind == 'module' and self.prov.id == COMMENTS_MODULE
                and getattr(self.prov, 'origin', 'builtin') == 'builtin')

    def _module(self, fn, task, tid, internal, *args):
        """Виклик функції модуля (`list`/`resolve`) для каналу задачі — і для модуля простору, і для ЛІГИ (`comments_route`);
        будь-який `ModuleError` — з очищеним текстом."""
        if self.kind == 'legacy':
            spaces.require_integrations()          # `IntegrationsOff` (`OSError`), як колись у `supabase_pins`
        try:
            mod, ctx, channel = comments_route(self.space, self.prov)
            return deai_modules.call(mod, fn, ctx, channel(task, tid, internal), *args,
                                     timeout=deai_modules.COMMENTS_TIMEOUT)
        except deai_modules.ModuleError as e:
            raise agent_error(e) from None

    def pins(self, task, tid, internal=False):
        """Проєктні піни задачі у формі рядків REST. `IntegrationsOff` — нікого (`'off'`), `ModuleError` — рішення чи
        виклик модуля не вдались (або відповідь не список)."""
        self._check()
        return agent_pins(self._module('list', task, tid, internal))

    def resolve(self, task, tid, pin_id, reason, iteration=None, internal=False):
        """Закрити пін модулем (`resolve(ctx, channel, id, reason[, iteration])`); номер ітерації — лише коли
        `takes_iteration`. `id` — лише за білим списком `_AGENT_ID` (як і в `list`)."""
        self._check()
        if not isinstance(pin_id, str) or not _AGENT_ID.fullmatch(pin_id):
            raise deai_modules.ModuleError('module-error', message='comments: the pin id is not a safe identifier')
        args = (pin_id, reason, iteration) if self.takes_iteration and iteration is not None else (pin_id, reason)
        self._module('resolve', task, tid, internal, *args)
        return None
```

  `channel()` лишається як є (для `'legacy'` уже `comment_channel`). Видалити `supabase_pins` і згадки про нього в
  docstring-ах (`ProjectComments`, таблиця над класом).

- [ ] **Step 4: `bin/inbox.py`.** Імпорти без `supabase_pins`, `supabase_config` (якщо більше не потрібні); обидва
  `pc.pins(task, tid, legacy=…)` → `pc.pins(task, tid)`; видалити `patch_project_pin` і `project_body`; у `cmd_resolve`:

```python
    for p in project_pins:
        it_tag = f' Іт.{n}' if pc.takes_iteration else ''
        if a.dry_run:
            print(f'[dry-run] {pc.label}: resolve {pc.channel(task, tid)} {p["id"]}{it_tag} '
                  f'{json.dumps(reason, ensure_ascii=False)}')
            continue
        try:
            pc.resolve(task, tid, p['id'], reason, iteration=n)
            print(f'✓ {p["id"][:8]} закрито (проєкт{"," + it_tag if it_tag else ""}): «{reason}»')
        except Exception as e:  # noqa: BLE001 — кожен пін звітує сам за себе
            print(f'✗ {p["id"][:8]}: {pc.label} не прийняв ({_say(e)})')
            failed += 1
```

  Рядок успіху ЛІГИ має лишитись байт у байт `✓ <id8> закрито (проєкт, Іт.N): «…»` — перевірити тестом.

- [ ] **Step 5: `bin/state.py`.** Імпорти без `supabase_pins`; видалити `_open_pins`; у `_team_comments` гілку
  `if pc.kind == 'module':` → `if pc.kind in ('module', 'legacy'):` і прибрати останні два рядки з `_open_pins`
  (лишити `return 0, ', проєктних нема'` для `'off'`). Docstring: «ЛІГА — тим самим модулем».

- [ ] **Step 6: Міграція старих тестів.** `grep -rn "supabase_pins\|patch_project_pin\|project_body\|_open_pins\|legacy=lambda"
  tests bin/test_*.py`: тести, що підміняли `supabase_pins`/`patch_project_pin`, переводяться на підміну
  `serve.comments_route` (повертає підставний модуль-обʼєкт із `list`/`resolve`) або шов `_open` модуля; тести точного
  PATCH (`test_inbox.py` ResolveProject/DryRun) — на нову форму (див. поправку 8 у плані); `test_comments_agent.py`
  DecisionTest лишає `kind == 'legacy'`. Жоден тест не видаляється без заміни, що перевіряє ту саму властивість
  (у звіті — таблиця «старий тест → новий»).

- [ ] **Step 7: Зелені + мутації.** `python3 "$G" 900 4096 npm test`. Мутації: `comment_channel` → `channel_for` у
  `comments_route`; прибрати `'shots_bucket'` із `_comments_legacy_ctx`; `takes_iteration` для `'legacy'` → `False`;
  прибрати `spaces.require_integrations()` у `_module`.

- [ ] **Step 8: Коміт** шляхами.

---

### Task 5: сторінки — `/commented`, превʼю, `/api/comment-config`, «Огляд»; старий шлях геть

**Files:**
- Modify: `app/serve.py` (`_commented` ≈5519, `_comment_config` ≈5727, `publish_comments` ≈3791 і три виклики ≈4144,
  ≈4357, ≈7446, `build_preview` ≈3830; геть `COMMENT_SNIPPET`, `inject_comment_layer`, `INTERNAL_TINT`, коментарі
  «Чому прапорець» над `INSPECTOR_TAG`/`audiences_arg`, що згадують `COMMENT_SNIPPET`, — переписати на модульний сніпет),
  `bin/import_preview.py`, `app/overview-comments.js`, `app/index.html`, `tests/_sources.mjs`
- Move: `git mv app/vendor/supabase-adapter.min.js tests/fixtures/legacy-comments/supabase-adapter.min.js`
- Test: `tests/test_legacy_comments.py`, `tests/test_comments_role.py` (+ два еталони), `tests/test_serve.py`,
  `tests/test_publish_module.py`, `tests/test_integrations_off.py`, `tests/test_supabase_comments.py` (`ParityTest`),
  `tests/overview-comments-module.test.mjs`, `tests/shell-palette.test.mjs`, `bin/test_import_preview.py`

- [ ] **Step 1: Падаючі тести** у `tests/test_legacy_comments.py` (клас `LegacyPagesTest`, сервер — як у
  `tests/test_comments_role.py` (`ServerEnv`/`tca`), фікстура з конфігом Supabase):
  - **Диференційний, сторінка:** `/commented?ch=project` задачі з `comment_project: "proj/alpha"` → у HTML є
    `__deaiCommentsCfg`, `/api/module-client/supabase-comments/supabase.min.js` і `…/adapter.js`; з `__deaiCommentsCfg`
    (розібрати JSON-літерал) `channel == before["page_work"]["channel"]`, `shotsBucket == "overview-thumbs"`; версія в
    `CommentLayer.init` == `before["page_work"]["version"]` для тієї ж сторінки; `audiences`/`inspector` як у
    `before["page_work"]`; НЕМА `cdn.jsdelivr.net/npm/@supabase`, `supabase-adapter.min.js`, `CommentLayerSupabase`.
  - Без конфігу Supabase: сторінка локальна + примітка з кодом `comments-unconfigured`; вкладки «Команда» нема.
  - **Превʼю:** `build_preview(task, tid, its, comments=publish_comments(space, task, tid)[0], gate_pw='1100',
    build='legacy')` → у `publish/comment-layer/` рівно `comment-layer.min.js`, `supabase.min.js`, `adapter.js`; у сторінках
    канал `before["page_publish"]["channel"]`-форми (`dc/<tid>` для задачі без `comment_project`) і версія; ні інспектора,
    ні аудиторій; `manifest.json["build"] == "legacy"`.
  - `publish_comments(space, task, tid, module_publish=True)` для `'legacy'` → `(False, None)` (як було);
    без конфігу → `(False, 'comments-unconfigured')`.
  - `build_preview(…, comments=True)` → `ValueError` до змін на диску.
  - `/api/comment-config?ch=project&it=it1` → `{'ch', 'module': 'supabase-comments', 'client': [...], 'config': {'url',
    'key', 'shotsBucket'}, 'channel': 'proj/alpha', 'version', 'user'?}`; ключів `sbUrl`/`sbKey`/`project` нема; без конфігу
    → 409 `comments-unconfigured`.
  - `hasattr(serve, n) is False` для `COMMENT_SNIPPET`, `inject_comment_layer`, `INTERNAL_TINT`; файла
    `app/vendor/supabase-adapter.min.js` нема; `app/index.html` не згадує `supabase-adapter`.

- [ ] **Step 2: Прогін — червоні.**

- [ ] **Step 3: `_commented`.** Блок вибору сніпета (≈5585-5615) — один шлях для будь-якого постачальника:

```python
            module_cfg = mod = None
            if ch == 'project' and prov is not None:
                # Командний канал веде модуль ролі `comments`: власний модуль простору або (ЛІГА) вбудований
                # `supabase-comments` з конфігом установки й каналом `comment_channel` (`comments_route`). Відмова — не 5xx:
                # сторінка лишається РОБОЧОЮ (локальні коментарі) і каже, чому нема командних.
                try:
                    mod, cctx, channel = comments_route(page_space, prov)
                    module_cfg = {**deai_modules.comments_client(page_space, mod, cctx), 'channel': channel(task, tid)}
                except deai_modules.ModuleError as e:
                    ch, notice, team = 'local', e.code, False
            if module_cfg is not None:
                html = inject_module_comment_layer(
                    html, f'{origin}/app/vendor', module_client_urls(mod, page_space), module_cfg, version=ver,
                    inspector=True, audiences=team, profile=task.get('profile') or '', space=page_space)
            else:
                …локальна гілка без змін…
```

  (`elif ch == 'project': inject_comment_layer(…)` зникає.) Оновити коментар над блоком: `'legacy'` — це теж модуль.

- [ ] **Step 4: `_comment_config`.** Гілки `isinstance(prov, Module)` і `elif ch == 'project'` → одна:

```python
        if ch == 'project':
            # Командний канал — модуль ролі `comments` (у ЛІГИ — `supabase-comments` з конфігом установки, `comments_route`).
            # «Огляд» (`overview-comments.js`) складає з цього `DeaiComments.create({...config, channel, onChange})`.
            mod, cctx, channel = comments_route(space, prov)
            self._send_json({'ch': ch, 'module': mod.id, 'client': module_client_urls(mod, space),
                             'config': deai_modules.comments_client(space, mod, cctx), 'channel': channel(task, tid),
                             'version': ver, **user})
        else:
            …локальна без змін…
```

  `ModuleError` летить у центральний обробник (як і раніше для модуля) → 409 `comments-unconfigured`.

- [ ] **Step 5: `publish_comments(space, task, tid, *, module_publish=False)`** — таблицю в docstring: `'legacy'` у збірці
  ЛІГИ → «словник модуля (`supabase-comments`, канал `comment_channel`)», у збірці модуля публікації — `False`, як було.

```python
    prov, err = comments_provider(space)
    if err is not None:
        return False, err.code
    if prov is None or (prov == 'legacy' and module_publish):
        return False, None
    try:
        mod, ctx, channel = comments_route(space, prov)
        config = deai_modules.comments_client(space, mod, ctx)
        return {'module': mod, 'config': config, 'channel': channel(task, tid)}, None
    except deai_modules.ModuleError as e:
        return False, e.code
```

  Три виклики — додати `task`. `build_preview`: прибрати гілку `adapter is None` (`BUNDLES`, `inject_comment_layer`);
  `comments` — лише `False` чи словник (`True` → `ValueError` тим самим текстом-шаблоном); docstring оновити (пункт `True`
  прибрати). `BUNDLES`/`BUILD_KINDS`/`LAYER_BUNDLE` лишаються (їх читають `ops/reseal_gate.py` і перевірка імен файлів
  адаптера) — коментар над `BUNDLES`: «імена бандлів СТАРИХ збірок ЛІГИ (до 0.10.0); нові їх не везуть».

- [ ] **Step 6: Видалення.** `COMMENT_SNIPPET`, `inject_comment_layer`, `INTERNAL_TINT`; `git mv` старого адаптера в
  `tests/fixtures/legacy-comments/`; у `_COMMENT_DOWN_BANNER`-коментарі прибрати «шаблон ЛІГА чіпати не можна (його розбирає
  import_preview)» → «маркери старого сніпета `import_preview` тримає замороженими». `bin/import_preview.py`: замінити

```python
_SNIPPET_HEAD = serve.COMMENT_SNIPPET.lstrip('\n').split('\n', 2)
```

  і похідні на ЗАМОРОЖЕНІ літерали — значення обчислити ДО видалення (`python3 -B -c "…print(repr(…))"`) і вставити
  рядками з коментарем «старий сніпет ЛІГИ (до 0.10.0) — заморожено: опубліковані превʼю в обігу ще його несуть».
  `bin/test_import_preview.py` ≈38: замість `serve.inject_comment_layer(...)` — читання
  `tests/fixtures/legacy-comments/old-snippet-page.html` (Task 1).

- [ ] **Step 7: «Огляд» і оболонка.** `app/overview-comments.js`: видалити `SB_JS` і гілку
  `else if (cfg.ch === "project") { … CommentLayerSupabase … }` — для `project` завжди `moduleStore(cfg)`; умову
  `if (cfg.module)` лишити (локальний канал без модуля). `app/index.html` ≈28 — рядок `vendor/supabase-adapter.min.js`
  видалити. `tests/_sources.mjs` — прибрати старий адаптер з переліку джерел.

- [ ] **Step 8: Еталони.** `UPDATE_COMMENTS_GOLDEN=1` лише для `page-legacy-project.html` і `config-legacy-project.json`
  (якщо механізм оновлює всі — оновити, а решту файлів теки відновити побайтно й показати sha256 до/після). Нові еталони
  переглянути очима: модульний сніпет, канал `proj/…`/`dc/…`, жодного справжнього хоста — лише значення фікстури.

- [ ] **Step 9: Міграція старих тестів.** `grep -rln "inject_comment_layer\|COMMENT_SNIPPET\|sbUrl\|CommentLayerSupabase\|supabase-adapter\|comments=True"
  tests bin/test_*.py`: тести видаленого сніпета (банер першим тегом, інспектор/аудиторії за прапорцем, екранування) —
  перенести на `inject_module_comment_layer`, ЯКЩО такої перевірки для модульного сніпета ще нема; інакше видалити з
  посиланням на наявний тест. `ParityTest` у `tests/test_supabase_comments.py` — читає старий адаптер з нового шляху
  фікстури. `tests/test_integrations_off.py`, `tests/test_publish_module.py`, `tests/test_serve.py`,
  `tests/overview-comments-module.test.mjs` (≈132, ≈232), `tests/shell-palette.test.mjs` — на нову форму. Таблиця
  «старий тест → новий/видалено, чому» — у звіті.

- [ ] **Step 10: Зелені + мутації.** `python3 "$G" 900 4096 npm test`. Мутації: у `_commented` `channel(task, tid)` →
  `deai_modules.channel_for(page_space, tid)`; у `publish_comments` прибрати `and module_publish`; у `_comment_config`
  передати `None` замість `cctx`.

- [ ] **Step 11: Коміт** шляхами (включно з `git mv`: обидва шляхи в pathspec).

---

### Task 6: живі тести

**Files:** `tests/live/comments.test.mjs`, `tests/live/comment-audience.test.mjs`, `tests/live/shell-typing.test.mjs`,
`tests/live/canvas.test.mjs`, `tests/live/inspector-project.test.mjs`, `tests/live/overview-comments.test.mjs`,
`tests/live/teams-mute.test.mjs` — усе, що `grep -ln "supabase-adapter\|CommentLayerSupabase\|cdn.jsdelivr.net\|COMMENT_SNIPPET\|SUPABASE" tests/live`.

- [ ] **Step 1:** ЛІГА-фікстури живих тестів (`tasks.json`, що їх пишуть тести) — додати `supabase_url:
  "https://abcdefghijkl.supabase.co"`, `supabase_key: "sb_publishable_test"`. Заглушки старого адаптера/CDN замінити на
  перехоплення `https://abcdefghijkl.supabase.co/**` (REST: `[]`, realtime-websocket — abort) так, як це вже робить
  `tests/live/comments.test.mjs` для простору з модулем (≈230). `comments.test.mjs` ≈586: ЛІГА-сторінка тепер — модульний
  сніпет (`/api/module-client/supabase-comments/`), без CDN і `supabase-adapter`; канал у `__deaiCommentsCfg` —
  `comment_project` задачі.
- [ ] **Step 2:** додати один живий сценарій: ЛІГА без `supabase_url` у фікстурі → `/commented?ch=project` показує
  банер-примітку з `comments-unconfigured`, рамка робоча (локальні піни ставляться).
- [ ] **Step 3:** прогін кожного зміненого файла ПО ОДНОМУ: `python3 "$G" 600 4096 node --test --test-concurrency=1 tests/live/<файл>`;
  потім `tests/live-ports.test.mjs` через `npm test`. `inspector-ds` 2/4 — стара червона з v0.7.0, не чіпати.
- [ ] **Step 4: Коміт** шляхами.

---

### Task 7: документи й версія 0.10.0

**Files:** `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `docs/modules/comments.md`,
`tasks.example.json`, `package.json`

- [ ] `CHANGELOG.md` — `## [0.10.0] — дата` (дату ставить контролер у релізі; до того `— невипущено`): Added (модуль
  1.1.0: `shots_bucket`/`uploadShot`, `resolve(…, iteration)`, certifi; код `comments-unconfigured`), Changed (ЛІГА —
  коментарі через `supabase-comments`; конфіг Supabase у `tasks.json`; перелік свідомих відмінностей зі спеки), Removed
  (`SUPABASE_URL`/`SUPABASE_KEY`, старий сніпет і адаптер, `supabase_pins`, `patch_project_pin`), «Як оновитись»: один раз
  дописати `supabase_url`/`supabase_key` у корінь `tasks.json` простору ЛІГА (чи `SUPABASE_URL`/`SUPABASE_KEY` в оточення).
- [ ] `README.md` — у розділ простору ЛІГА: конфіг Supabase; у розділ модуля коментарів — скріншоти.
- [ ] `docs/design/spaces-and-modules.md` — «Stage 4b-2» (стан: зроблено; що лишилось ядру ЛІГИ для 4c/4d).
- [ ] `docs/modules/comments.md` — `shots_bucket`, `uploadShot` у контракті сховища (необовʼязковий), `iteration` у
  `resolve` (лише вбудованому модулю).
- [ ] `tasks.example.json` — `"supabase_url": "https://<ref>.supabase.co"`, `"supabase_key": "sb_publishable_…"` у корені.
- [ ] `package.json` — `0.10.0`.
- [ ] `npm test` зелений; коміт шляхами.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`67e9009`).
2. Повні прогони: `npm test`; Python 3.13 і `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона з v0.7.0).
3. Дата в CHANGELOG → тег `v0.10.0` (анотований, від neodisa) → явний `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять (`project-deai-opensource.md`), статус пайплайна, звіт власнику (із нагадуванням: дописати конфіг Supabase ЛІГИ
   у справжній `tasks.json` перед оновленням — інакше командні коментарі ЛІГИ вимкнуться).

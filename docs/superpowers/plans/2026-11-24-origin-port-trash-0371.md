# Патч 0.37.1: порт у перевірці Origin, Host і три вади кошика — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрити записи в канвас зі сторінок інших локальних портів і DNS rebinding; прибрати три вади кошика ітерацій 0.36.

**Architecture:** `_local_origin(origin, port)` вимагає схему `http`, локальний хост і ПОРТ канваса; заголовок `Host`
перевіряється один раз на весь запит у `parse_request` (усі методи, обидва класи обробника). Кошик: вік слота
перевіряється при поверненні, прострочене прибирається й при читанні кошика для `/api/task`, битий `entry.json` —
JSON-відмова `bad-entry`, а не 5xx.

**Tech Stack:** Python stdlib (`http.server`, `unittest`), `app/serve.py`, `app/iter_trash.py`.

**Рівень строгості:** повний (межа безпеки сервера). Один виконавець, ревʼю після кожної задачі.

---

## Рішення (24.11.2026)

1. **Origin.** Є заголовок — має бути `http://<хост>:<порт канваса>`, хост ∈ {`localhost`, `127.0.0.1`, `[::1]`}.
   Інший порт, `https`, порт пропущено, `null` — відмова. Нема заголовка — пускаємо, як і тепер (curl, хук Stop,
   urllib, мод Claude Code: усі шлють запит без Origin). Відповідь лишається `403 {"ok": false, "error": "foreign origin"}`.
2. **Host.** Є заголовок — має бути `<хост>:<порт канваса>` з тим самим набором хостів (регістр не важить). Інакше
   `403 {"ok": false, "error": "bad-host"}` до будь-якої обробки, для GET/HEAD/POST/OPTIONS. Нема заголовка — пускаємо
   (браузер шле його завжди; rebinding без нього неможливий).
3. **Content-Type НЕ вимагаємо.** Браузер завжди шле Origin на крос-походженний POST, тож порт закриває діру сам;
   вимога JSON-типу лише зламала б агентів, що шлють `curl -d`. Скелет `AGENTS.md` не міняється.
4. **Кошик.** (1) повернення простроченого слота — `410 {"ok": false, "error": "expired"}`; (2) `task_iteration_trash`
   перед переліком кличе `purge` (у try: прибирання не сміє зламати `/api/task`), і маршрут повернення — після успіху;
   (3) `entry.json`, що не читається як `{"entry": {...}}`, — `IterTrashError('bad-entry')` → `400`.
5. **Поза патчем:** autosync крок 2 і трейлер `Deai-Actor: ai` (пункт 4 боргу) — у гілці хука Stop (рішення власника).

## Файли

- Modify: `app/iter_trash.py` — `slot_time`, `_slot_entry` (bad-entry), `restore_prepare(..., now=None)` (expired).
- Modify: `app/serve.py` — `_local_origin(origin, port)`, новий `_local_host(host, port)`, `parse_request` у
  `Handler`, усі виклики `_local_origin`, `_iteration_restore`, `task_iteration_trash`.
- Test: `tests/test_iter_trash.py`, `tests/test_iteration_api.py`, `tests/test_spaces_serve.py` (+ підлаштувати наявні тести,
  що шлють Origin з портом 8765 до тестового сервера на іншому порту — їх знаходить повний прогін).
- `CHANGELOG.md`, `package.json` — контролер на релізі.

---

### Task 1: Кошик — вік, прибирання, битий запис

**Files:** Modify `app/iter_trash.py`, `app/serve.py` (`_iteration_restore`, `task_iteration_trash`); Test
`tests/test_iter_trash.py`, `tests/test_iteration_api.py`.

- [ ] **Step 1: Падаючі юніти `iter_trash`** (у `tests/test_iter_trash.py`, поруч із наявними класами; хелпери фікстур —
  ті, що вже є у файлі для `move_to_trash`):

```python
class RestoreAgeAndBadEntry(unittest.TestCase):
    # фікстура: тимчасова тека задачі з iterations/it2, move_to_trash(task_dir, {'id': 'it2'}, T0)

    def test_restore_refuses_an_expired_slot(self):
        later = T0 + datetime.timedelta(days=iter_trash.KEEP_DAYS, seconds=1)
        with self.assertRaises(iter_trash.IterTrashError) as cm:
            iter_trash.restore_prepare(self.dir, self.slot, [], now=later)
        self.assertEqual(cm.exception.code, 'expired')
        self.assertTrue(os.path.isdir(os.path.join(iter_trash.trash_root(self.dir), self.slot, 'files')))  # нічого не рушили

    def test_restore_at_exactly_keep_days_still_works(self):
        edge = T0 + datetime.timedelta(days=iter_trash.KEEP_DAYS)
        entry, _ = iter_trash.restore_prepare(self.dir, self.slot, [], now=edge)
        self.assertEqual(entry['id'], 'it2')

    def test_restore_without_now_keeps_old_behaviour(self):
        far = iter_trash.restore_prepare(self.dir, self.slot, [])   # тести/виклики без часу — як у 0.36
        self.assertEqual(far[0]['id'], 'it2')

    def test_bad_entry_json_is_a_coded_refusal(self):
        for raw in ('{', '[]', '{"entry": 5}', '{"x": {}}'):
            with self.subTest(raw=raw):
                with open(os.path.join(iter_trash.trash_root(self.dir), self.slot, 'entry.json'), 'w') as f:
                    f.write(raw)
                with self.assertRaises(iter_trash.IterTrashError) as cm:
                    iter_trash.restore_prepare(self.dir, self.slot, [])
                self.assertEqual(cm.exception.code, 'bad-entry')

    def test_slot_time_parses_the_name(self):
        self.assertEqual(iter_trash.slot_time('it2--20261117-091500-2'),
                         datetime.datetime(2026, 11, 17, 9, 15, tzinfo=datetime.timezone.utc))
        self.assertIsNone(iter_trash.slot_time('it2--20261399-000000'))
        self.assertIsNone(iter_trash.slot_time('nope'))
```

- [ ] **Step 2: Запустити — FAIL** (`python3 -B -m unittest tests.test_iter_trash -v`: `slot_time` нема, `now` не параметр,
  `bad-entry` вилітає як `ValueError`/`KeyError`/`TypeError`).

- [ ] **Step 3: Реалізація в `app/iter_trash.py`.**

```python
def slot_time(slot):
    """Час видалення з імені слота (aware UTC) або `None` — імʼя не слот чи дата в ньому непридатна."""
    s = SLOT_RE.fullmatch(slot) if isinstance(slot, str) else None
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s.group(2), '%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
```

  `purge` і `list_slots` переходять на `slot_time` (та сама семантика: `None` → слот не чіпаємо / пропускаємо).
  `_slot_entry`: читання й розбір у try → `IterTrashError('bad-entry', ...)` на `ValueError`, `KeyError`, `TypeError`,
  а також коли `entry` не `dict` (`OSError` лишається `OSError` — маршрут уже відповідає `restore-failed`).
  `restore_prepare(task_dir, slot, taken_ids, now=None)`: перед будь-яким рухом файлів, якщо `now` задано —
  `at = slot_time(slot)`; `at is None or at < now - timedelta(days=KEEP_DAYS)` → `IterTrashError('expired', 'the slot is past its keep time')`.
  Межа та сама, що в `purge` (`at < edge` — прострочений, рівно 7 діб — ще ні). Докстрінг `IterTrashError` доповнити кодами.

- [ ] **Step 4: Падаючі тести маршруту** (`tests/test_iteration_api.py`, клас `TrashList`):

```python
    def test_restore_of_an_expired_slot_is_410(self):
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        later = iter_trash.utcnow() + datetime.timedelta(days=iter_trash.KEEP_DAYS, minutes=1)
        with mock.patch.object(serve.iter_trash, 'utcnow', return_value=later):
            st, body = self.post('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual((st, body), (410, {'ok': False, 'error': 'expired'}))

    def test_bad_entry_is_400_json_not_500(self):
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        # зіпсувати entry.json слота d['trash'] у теці задачі фікстури
        st, body = self.post('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual((st, body['error']), (400, 'bad-entry'))

    def test_task_read_purges_expired_slots(self):
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        later = iter_trash.utcnow() + datetime.timedelta(days=iter_trash.KEEP_DAYS, minutes=1)
        with mock.patch.object(serve.iter_trash, 'utcnow', return_value=later):
            _, task = self.jget('/api/task')
        self.assertEqual(task['iteration_trash'], [])
        self.assertFalse(os.path.exists(os.path.join(<тека задачі фікстури>, '.trash', 'iterations', d['trash'])))

    def test_purge_failure_does_not_break_task(self):
        with mock.patch.object(serve.iter_trash, 'purge', side_effect=OSError('boom')):
            st, task = self.jget('/api/task')
        self.assertEqual((st, task['iteration_trash']), (200, []))
```

  (Тека задачі — тим самим способом, яким її вже знаходять інші тести файла; `serve.iter_trash` — той самий модуль, що
  імпортує `serve`.)

- [ ] **Step 5: FAIL**, потім **реалізація в `app/serve.py`:**
  - `_iteration_restore`: `now = iter_trash.utcnow()`; `restore_prepare(task['dir'], slot, ids, now=now)`; статус відмови
    `{'not-in-trash': 404, 'expired': 410}.get(e.code, 400)`; після `restore_finish` — `try: iter_trash.purge(task['dir'], now) except Exception: pass`.
  - `task_iteration_trash`: `now = iter_trash.utcnow()`; `try: iter_trash.purge(task['dir'], now) except Exception: pass`
    перед `list_slots(task['dir'], now)` (один `now` на обидва).

- [ ] **Step 6: PASS** — `python3 -B -m unittest tests.test_iter_trash tests.test_iteration_api -v`.

- [ ] **Step 7: Мутації** (кожна — тест червоніє; потім відкотити): прибрати перевірку `now` у `restore_prepare`;
  прибрати `purge` з `task_iteration_trash`; повернути `json.load` без try у `_slot_entry`. Ганяти `python3 -B`.

- [ ] **Step 8: Коміт** `fix(trash): повернення лише непрострочених, прибирання при читанні, битий запис — bad-entry`.

### Task 2: Origin з портом і перевірка Host

**Files:** Modify `app/serve.py`; Test `tests/test_spaces_serve.py` (+ наявні тести, що зламаються).

- [ ] **Step 1: Падаючі юніти чистих функцій** (новий клас у `tests/test_spaces_serve.py`):

```python
class LocalOriginAndHost(unittest.TestCase):
    def test_origin(self):
        P = 48123
        good = (None, '', f'http://127.0.0.1:{P}', f'http://localhost:{P}', f'http://LOCALHOST:{P}', f'http://[::1]:{P}')
        bad = (f'http://127.0.0.1:{P + 1}', f'http://localhost:3000', 'http://127.0.0.1', 'http://localhost',
               f'https://127.0.0.1:{P}', 'null', 'http://evil.example', f'http://localhost.evil.example:{P}',
               f'http://127.0.0.1.evil.example:{P}', 'file://', f'ws://127.0.0.1:{P}')
        for o in good:
            with self.subTest(o=o):
                self.assertTrue(serve._local_origin(o, P))
        for o in bad:
            with self.subTest(o=o):
                self.assertFalse(serve._local_origin(o, P))

    def test_host(self):
        P = 48123
        good = (None, f'127.0.0.1:{P}', f'localhost:{P}', f'LocalHost:{P}', f'[::1]:{P}')
        bad = ('', f'127.0.0.1:{P + 1}', '127.0.0.1', 'localhost', f'evil.example:{P}', 'evil.example',
               f'localhost.evil.example:{P}', f'127.0.0.1:{P}@evil', f'127.0.0.1:{P} ', f'::1:{P}', 'x' * 300)
        for h in good:
            with self.subTest(h=h):
                self.assertTrue(serve._local_host(h, P))
        for h in bad:
            with self.subTest(h=h):
                self.assertFalse(serve._local_host(h, P))
```

- [ ] **Step 2: FAIL**, потім **реалізація:**

```python
#: Хости, з яких канвас приймає запити (Host) і чиї сторінки можуть слати POST (Origin) — лише з портом канваса.
_LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1')


def _local_origin(origin, port):
    """Origin відсутній (curl, хук Stop, мод Claude Code) — так. Є — лише `http://<локальний хост>:<port>`: сторінка з
    іншого локального порту (чужий dev-сервер) не пише в канвас простим POST без preflight."""
    if not origin:
        return True
    try:
        u = urlparse(origin)
        return u.scheme == 'http' and (u.hostname or '').lower() in _LOCAL_HOSTS and u.port == port
    except ValueError:
        return False


_HOST_HDR_RE = re.compile(r'^(localhost|127\.0\.0\.1|\[::1\]):(\d{1,5})$', re.I)


def _local_host(host, port):
    """`Host` відсутній — так; є — лише `<локальний хост>:<port>` (захист від DNS rebinding: чужий домен, що
    резолвиться в 127.0.0.1, приходить зі своїм іменем у Host)."""
    if host is None:
        return True
    m = _HOST_HDR_RE.fullmatch(host)
    return bool(m) and int(m.group(2)) == port
```

  Усі виклики `_local_origin(x)` → `_local_origin(x, self.server.server_address[1])` (grep: має не лишитись жодного
  виклику з одним аргументом).

  У базовому класі обробника (`Handler` — той, від якого походять обидва класи з `do_GET`; перевірити, що `Routed`
  успадковує його, і що інших `ThreadingHTTPServer(...)` з іншими класами нема):

```python
    def parse_request(self):
        if not super().parse_request():
            return False
        if not _local_host(self.headers.get('Host'), self.server.server_address[1]):
            self.close_connection = True
            self._drain_body()                      # якщо наявний хелпер безпечний до розбору маршруту; інакше — не читати тіло
            self._send_json({'ok': False, 'error': 'bad-host'}, status=403)
            return False
        return True
```

  Перевірити, що `_send_json` не залежить від стану, який ставиться пізніше (`_take_task`, `_task_override`, простір) —
  якщо залежить, відповісти мінімально: `send_response(403)`, `Content-Type: application/json`, `Content-Length`, тіло.
  Порожній Host (`Host:` без значення) — відмова (рядок не None).

- [ ] **Step 3: Падаючі HTTP-тести** (той самий файл, на фікстурі живого тестового сервера, як `test_the_local_origin_still_works`):
  - `GET /api/task` з `Host: evil.example:<port>` → `403 {"ok": false, "error": "bad-host"}`; з `Host: localhost:<port>` → 200.
  - `POST /api/space-switch` з `Origin: http://localhost:<port+1>` → `403 foreign origin`, стан реєстру не змінився.
  - `POST` з `Origin: http://127.0.0.1:<port>` і без Origin → 200 (контроль).
  - `OPTIONS /api/task` з чужим Host → 403 `bad-host` (а не 501).
  - Сирий сокет або `http.client` з явним `Host` (`conn.putrequest(..., skip_host=True)` + `putheader('Host', ...)`).

- [ ] **Step 4: PASS**, потім **повний прогін Python** (`python3 -B -m unittest discover -s tests -p 'test_*.py'`, далі
  `-s bin`, `-s app`) — під навантаженням сусідньої сесії до ~20 хв, чекати рядка підсумку, не вважати зависанням.
  Тести, що шлють `Origin` з портом 8765 (чи без порту) до тестового сервера на іншому порту і чекають успіху, —
  перевести на `self.port`; тести, що чекають відмови чужому Origin, — лишити.

- [ ] **Step 5: Мутації:** прибрати `u.port == port`; прибрати `u.scheme == 'http'`; повернути `parse_request` без
  перевірки Host — кожна мутація валить щонайменше один тест. `python3 -B`.

- [ ] **Step 6: Коміт** `fix(security): Origin лише з портом канваса, Host перевіряється на кожному запиті`.

### Task 3 (контролер): реліз 0.37.1

- `CHANGELOG.md` — розділ `[0.37.1] — <дата>`: «Виправлено» (Origin з портом, Host, кошик ×3), «Відомі обмеження»: лише
  якщо щось лишилось.
- `package.json` → `0.37.1`.
- Охоронець публічного репо (`tests.test_no_internal_addresses` з `DEAI_REQUIRE_FORBIDDEN_LIST=1`).
- Релізний прогін: усі юніт-набори + живі `canvas`, `iterations-list`, `ext-shell`, `tabs` по одному під замком.
- Злиття ff у живий `main`, анотований тег, перезапуск канваса з чистим env, push — лише за «да» власника.
- Повідомити сесію гайда агента (вона вливає 0.37.1 у гілку хука Stop).

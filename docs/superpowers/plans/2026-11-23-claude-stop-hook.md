# «Підключити» ставить Stop-хук Claude Code — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** кнопка «Підключити» в «Налаштування → AGENTS.md» (рядок «Claude Code») ставить ще й Stop-хук Claude Code в
`<простір>/.claude/settings.local.json`; хук після кожної відповіді шле канвасу JSON сесії на `POST /api/autosync`, а канвас за
`cwd` знаходить простір і комітить кожну свою брудну ітерацію кожної його задачі як `itN: зміни AI` — без скіла власника.

**Architecture:** новий `app/claude_hook.py` (чистий запис хука: злиття, атомарно, стани) + режим «за шляхом» у `_autosync`
(`app/serve.py`) + ключ `hook` і дії `claude: true` / `hook: false` у `/api/agents-md` + рядок «Claude Code» (`setup-model.js`,
`first-run.js`, `app.js`, `i18n.js`, `styles.css`). Нових маршрутів нема.

**Tech Stack:** Python 3 stdlib (`http.server`, `unittest`, `json`, `os`), ES-модулі + `node:test`, Markdown. Без нових залежностей.

**Спека:** `docs/superpowers/specs/2026-11-23-claude-stop-hook-design.md`.

---

## Правила для виконавця (обовʼязково)

- Працюй лише в цьому worktree. Живий чекаут `deai-canvas`, порти 8765/4317 (на 8765 працює справжній канвас), справжні `~/.deai`,
  `~/.claude`, `~/deai-published`, `~/deai-work`, `~/.gitconfig` і мережу тести НЕ чіпають. Тести пишуть лише в тимчасові теки
  (`tempfile.mkdtemp`) і слухають лише порт 0.
- Коміт — лише так (кожен шлях явно; нові файли спершу `git add <шляхи>`; ніколи `git add -A`, `reset`, `stash`, `rebase`, `--amend`):

  ```bash
  git add <шляхи>
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<type>(stop-hook): <Ukrainian subject>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
- Репо публічний: жодних реальних імен людей, внутрішніх хостів, ключів, абсолютних локальних шляхів у файлах (тести беруть шляхи
  з `tempfile`).
- Тести одного файла: `python3 -B -m unittest discover -s tests -p "test_claude_hook.py" -v` (замінюй імʼя файла). Один клас:
  `python3 -B -m unittest tests.test_agents_md.HookRoutes -v`. Увесь Python: `python3 -B -m unittest discover -s tests -p "test_*.py"`.
  JS: `node --test tests/*.test.mjs`. Повний прогін — лише в Task 7.
- `rm -rf`/`shutil.rmtree` — лише всередині `tempfile.mkdtemp()` у тестах; жодних `pkill` за шаблоном. Перезапуск справжнього канваса —
  не наша справа (див. памʼять про чисте оточення: ніколи `./start.command` з оболонки агента).
- Живі (Playwright) тести — лише під замком і з тимчасовим `HOME`:
  `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo rc=$rc`.
- Версія, `package.json` і `CHANGELOG.md` — лише в Task 7 і лише після явного «да» власника.
- Коментарі й докстрінги в коді — українською (як у кодовій базі); `docs/agents/*` і `SETUP.md` — англійською (без кирилиці в
  `SETUP.md`: його стереже `tests/test_setup_md.py`).

## Що перевірено в коді (факти, на які спирається план)

- **«Запит назвав задачу»** = `self._task_override is not None`. `do_POST` викликає `_take_task()` першим; той скидає
  `_task_override`, ставить його лише для префікса `/t/<id>/` чи заголовка `X-Canvas-Task`; без обох викликає
  `_pin_current_space()` (простір запиту = поточний простір машини) і лишає `None`. `/api/autosync` НЕ у `_REGISTRY_ROUTES`,
  тож заголовок і префікс діють.
- `_current_task()` = `task_for(load_tasks(), self._task_override)`; `load_tasks()` читає файл простору ЗАПИТУ. Тому режим «за
  шляхом» робить `spaces.set_request_space(<знайдений простір>)` і далі користується тим самим `_vcs_ctx()`, що й сьогодні.
  `spaces.space_current_task` НЕ потрібен (воно ще й може мігрувати реєстр, тобто писати на диск) — отже охоронець
  `CurrentTaskReadGuard.SPACES_CURRENT_ALLOWED` лишається без змін (див. Task 2, Step 5, де це доводиться запуском).
- Простір за шляхом: `agent_guide.find_space(spaces.read_registry()['spaces'], path=cwd)` — найдовший префікс; неявні
  пропускає; не абсолютний шлях → `None`; нічого не знайшов → `None`.
- Задачі простору: `spaces._space_tasks(sp)` → `{id: {dir, title, …}}` (нечитабельний `tasks.json` → `{}`, не кидає).
- `ai_commit(task)` без `.git` у `task['dir']` → `None`; з `.git` → `{it, sha, its}` або `None`; не залежить від простору запиту.
- Тіло POST розбирається ДО обробника (`json.loads`), тому `self._autosync(payload)` (рядок, на який спирається охоронець `bad-body`
  в `test_serve`) лишається. Для `/api/local-shots` ліміт тіла перевіряється кортежем `self.path in ('/api/local-shots',)` — так само
  робимо для `/api/autosync` (регексп охоронця ловить лише `self.path == '/api/…'`).
- `self.server.server_port` — справжній порт сервера (перевірено на `ThreadingHTTPServer(('127.0.0.1', 0), …)`).
- `curl --data-binary @-` читає весь stdin і шле `Content-Length` (не chunked), тож ліміт 413 до читання працює. На 413 curl без
  `--fail` сам виходить з кодом 0 (тіло відкидає `-o /dev/null`); `|| true` страхує від транспортних збоїв: канвас вимкнено (7),
  таймаут 5 с (28), обрив зʼєднання (55/56) — зокрема коли сервер відмовляє на 413, не вичитавши тіло (доводить Task 5).
- Для порожнього простору (`E` у `Fixture`) `load_tasks()` дає файл без `current` → `NoTask`, а не `SpaceUnavailable`.

## Карта файлів

| Файл | Що | Задача |
|---|---|---|
| `app/claude_hook.py` (новий) | `HOOK_MARK`, `FILE`, `command`, `status`, `connect`, `disconnect`, `.git/info/exclude`, `elsewhere` | 1 |
| `tests/test_claude_hook.py` (новий) | усі випадки спеки для запису хука (лише тимчасові теки) | 1 |
| `app/serve.py` | `AUTOSYNC_BODY_MAX`; 413 у `do_POST`; `_autosync` «за шляхом» + `_ai_commit_space`; `hook` / `claude: true` / `hook: false` у `_agents_md`; `import claude_hook` | 2, 3 |
| `tests/test_autosync_path.py` (новий) | `/api/autosync` за `cwd`: простір, усі задачі, пріоритет заголовка, `no-space`, ліміт, stderr | 2 |
| `tests/test_agents_md.py` | клас `HookRoutes` для `GET|POST /api/agents-md` (хук) | 3 |
| `app/setup-model.js` | `claudeRow(claude, hook)` — 6 станів + CLAUDE.md `unreadable` + старий сервер | 4 |
| `app/first-run.js` | `agentRowsHTML`: список «що буде записано», кнопки «Підключити» / «Оновити» / «Відключити» | 4 |
| `app/app.js` | `agentsClaude` (тост за відповіддю), `agentsUnhook`, дія `unhook` | 4 |
| `app/i18n.js` | ключі `frClaudeWill*`, `frClaudeHook*`, `frClaudeUpdate`, `frClaudeDisconnect`, `frHook*` (uk і en) | 4 |
| `app/styles.css` | `.fr-will` (список із `<code>`) | 4 |
| `tests/setup-model.test.mjs`, `tests/agents-view.test.mjs` | стани `claudeRow` і розмітка рядка | 4 |
| `tests/test_claude_hook_e2e.py` (новий) | справжня команда хука через `sh -c` проти тестового сервера | 5 |
| `docs/agents/hooks.md`, `SETUP.md` | хук від «Підключити», режим `/api/autosync` за `cwd` | 6 |
| `tests/live/agents-md.test.mjs` | сценарій 5: Підключити → ✓ → Відключити → кнопка знову | 7 |
| `CHANGELOG.md`, `package.json` | версія й запис — лише після «да» | 7 |

Відхилення від запропонованого поділу: нема (сім задач, як у вимогах). Дві уточнені деталі: (а) `status`/`disconnect` приймають
`port`, бо без нього не відрізнити `ok` від `stale`; (б) пошук «чужого репозиторію» (`elsewhere`) зупиняється на домашній теці
(вона й усе вище — не «інший репозиторій»), що робить тести герметичними через `claude_hook._home`.

---

### Task 1: `app/claude_hook.py` — запис хука в `.claude/settings.local.json`

**Files:**
- Create: `app/claude_hook.py`
- Create: `tests/test_claude_hook.py`

- [ ] **Step 1: Написати падаючі тести**

Створи `tests/test_claude_hook.py`:

```python
"""Stop-хук Claude Code простору (23.11.2026): `app/claude_hook.py` пише ОДНУ нашу групу в `hooks.Stop` файла
`<простір>/.claude/settings.local.json` — злиттям, атомарно, не чіпаючи чужого. Усе — у тимчасових теках; «домівка» підмінена
(`_home`), тож тести не залежать від справжнього HOME, а ні `~/.claude`, ні мережі не чіпають."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
import claude_hook  # noqa: E402

PORT = 8765
OTHER = 9911
LINE = '/.claude/settings.local.json'


def _put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))


def _get(path):
    with open(path, 'rb') as f:
        return f.read()


def _json(path):
    return json.loads(_get(path).decode('utf-8'))


def _ours(port=PORT):
    return {'type': 'command', 'timeout': 10, 'command': claude_hook.command(port)}


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='claude-hook-'))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.space = os.path.join(self.root, 'space')
        os.makedirs(self.space)
        self.dir = os.path.join(self.space, '.claude')
        self.f = os.path.join(self.dir, 'settings.local.json')
        for patcher in (mock.patch.object(claude_hook, '_home', return_value=self.root),
                        mock.patch.object(claude_hook, '_WINDOWS', False)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def state(self, port=PORT):
        return claude_hook.status(self.space, port)['state']

    def tmp_files(self):
        return [n for n in os.listdir(self.dir) if n.endswith('.tmp')] if os.path.isdir(self.dir) else []

    def racing(self, mutate):
        """Підмінює читання так, що ПЕРЕД повторною звіркою (тимчасовий файл уже лежить) хтось змінює файл."""
        real = claude_hook._read_raw
        done = []

        def wrapper(space_dir):
            d = os.path.join(space_dir, '.claude')
            if not done and os.path.isdir(d) and any(n.endswith('.tmp') for n in os.listdir(d)):
                done.append(1)
                mutate()
            return real(space_dir)
        return mock.patch.object(claude_hook, '_read_raw', wrapper)


class Command(Base):
    def test_the_command_is_the_documented_one_with_the_mark_last(self):
        self.assertEqual(
            claude_hook.command(8765),
            "curl -s --noproxy '*' --max-time 5 -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary @- "
            "http://127.0.0.1:8765/api/autosync || true # deai-autosync")
        self.assertTrue(claude_hook.command(1).endswith(claude_hook.HOOK_MARK))
        self.assertEqual(claude_hook.HOOK_MARK, '# deai-autosync')
        self.assertEqual(claude_hook.FILE, '.claude/settings.local.json')

    def test_the_port_must_be_a_number(self):
        with self.assertRaises(ValueError):
            claude_hook.command('8765; rm -rf x')
        self.assertIn(':4317/', claude_hook.command('4317'))


class Status(Base):
    def test_no_file_is_missing_and_status_writes_nothing(self):
        self.assertEqual(claude_hook.status(self.space, PORT), {'state': 'missing', 'path': self.f})
        self.assertFalse(os.path.exists(self.dir))

    def test_a_file_without_our_group_is_missing(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo hi'}]}]}}))
        self.assertEqual(self.state(), 'missing')

    def test_our_command_for_the_current_port_is_ok_for_another_it_is_stale(self):
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.state(PORT), 'ok')
        self.assertEqual(self.state(OTHER), 'stale')

    def test_the_mark_with_an_old_command_is_stale(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'curl old # deai-autosync'}]}]}}))
        self.assertEqual(self.state(), 'stale')

    def test_two_copies_are_stale_and_connect_collapses_them(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [_ours(OTHER)]}, {'hooks': [_ours(PORT)]}]}}))
        self.assertEqual(self.state(), 'stale')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.state(), 'ok')
        self.assertEqual(_json(self.f)['hooks']['Stop'], [{'hooks': [_ours(PORT)]}])

    def test_status_never_raises(self):
        with mock.patch.object(claude_hook, '_read_raw', side_effect=RuntimeError('boom')):
            self.assertEqual(claude_hook.status(self.space, PORT)['state'], 'unreadable')


class Connect(Base):
    def test_creates_the_folder_and_the_file(self):
        st = claude_hook.connect(self.space, PORT)
        self.assertEqual(st, {'state': 'ok', 'path': self.f})
        doc = _json(self.f)
        self.assertEqual(doc, {'hooks': {'Stop': [{'hooks': [_ours()]}]}})
        self.assertEqual(_get(self.f).decode('utf-8'), json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
        self.assertEqual(self.tmp_files(), [])

    def test_an_empty_object_gets_the_hook(self):
        _put(self.f, '{}')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_json(self.f), {'hooks': {'Stop': [{'hooks': [_ours()]}]}})

    def test_foreign_hooks_and_other_keys_survive_by_content(self):
        foreign = {'permissions': {'allow': ['Bash(ls)']}, 'env': {'A': 'б'},
                   'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'echo pre'}]}],
                             'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}
        _put(self.f, json.dumps(foreign))
        claude_hook.connect(self.space, PORT)
        doc = _json(self.f)
        self.assertEqual(doc['permissions'], foreign['permissions'])
        self.assertEqual(doc['env'], foreign['env'])
        self.assertEqual(doc['hooks']['PreToolUse'], foreign['hooks']['PreToolUse'])
        self.assertEqual(doc['hooks']['Stop'][0], foreign['hooks']['Stop'][0])
        self.assertEqual(doc['hooks']['Stop'][1], {'hooks': [_ours()]})
        self.assertEqual(len(doc['hooks']['Stop']), 2)
        self.assertIn('"б"', _get(self.f).decode('utf-8'), 'ensure_ascii=False')

    def test_a_stale_hook_is_rewritten_with_the_new_port(self):
        claude_hook.connect(self.space, OTHER)
        self.assertEqual(self.state(PORT), 'stale')
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')
        self.assertEqual(_json(self.f)['hooks']['Stop'], [{'hooks': [_ours(PORT)]}])

    def test_connecting_again_writes_nothing(self):
        claude_hook.connect(self.space, PORT)
        before, ino = _get(self.f), os.stat(self.f).st_ino
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')
        self.assertEqual(_get(self.f), before)
        self.assertEqual(os.stat(self.f).st_ino, ino, 'файл не переписувався')

    def test_a_group_that_mixes_our_and_a_foreign_hook_keeps_the_foreign_one(self):
        mixed = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo keep'}, _ours(OTHER)]}]}}
        _put(self.f, json.dumps(mixed))
        claude_hook.connect(self.space, PORT)
        stop = _json(self.f)['hooks']['Stop']
        self.assertEqual(stop[0], {'hooks': [{'type': 'command', 'command': 'echo keep'}]})
        self.assertEqual(stop[1], {'hooks': [_ours(PORT)]})

    def test_the_mode_of_an_existing_file_is_kept(self):
        _put(self.f, '{}')
        os.chmod(self.f, 0o600)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(stat.S_IMODE(os.stat(self.f).st_mode), 0o600)

    def test_a_new_file_follows_the_umask(self):
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(stat.S_IMODE(os.stat(self.f).st_mode), 0o644)

    def test_a_change_between_read_and_replace_is_refused_and_leaves_their_file(self):
        _put(self.f, '{"a": 1}')

        def mutate():
            _put(self.f, '{"a": 2}')
        with self.racing(mutate):
            with self.assertRaises(ValueError) as cm:
                claude_hook.connect(self.space, PORT)
        self.assertEqual(str(cm.exception), 'changed')
        self.assertEqual(_get(self.f), b'{"a": 2}')
        self.assertEqual(self.tmp_files(), [])

    def test_a_file_that_appears_meanwhile_is_not_overwritten(self):
        def mutate():
            _put(self.f, '{"theirs": true}')
        with self.racing(mutate):
            with self.assertRaises(ValueError):
                claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.f), b'{"theirs": true}')
        self.assertEqual(self.tmp_files(), [])


class Unreadable(Base):
    """Нечитне не чіпаємо взагалі: стан `unreadable`, `connect`/`disconnect` кидають `OSError`, байти ті самі."""

    def check(self, raw):
        _put(self.f, raw)
        self.assertEqual(self.state(), 'unreadable', raw)
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        with self.assertRaises(OSError):
            claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_get(self.f), raw if isinstance(raw, bytes) else raw.encode('utf-8'))
        self.assertEqual(self.tmp_files(), [])

    def test_content_that_is_not_ours_to_merge(self):
        for raw in ('{not json', '', '[]', '5', 'null', '"x"', '{"hooks": []}', '{"hooks": null}',
                    '{"hooks": {"Stop": {}}}', '{"hooks": {"Stop": null}}', b'\xff\xfe\x00bad'):
            with self.subTest(raw=raw):
                self.check(raw)

    def test_a_symlinked_file_is_not_followed(self):
        target = os.path.join(self.root, 'target.json')
        _put(target, '{}')
        os.makedirs(self.dir)
        os.symlink(target, self.f)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(target), b'{}')
        self.assertTrue(os.path.islink(self.f))

    def test_a_symlinked_claude_folder_is_not_followed(self):
        other = os.path.join(self.root, 'other-claude')
        os.makedirs(other)
        os.symlink(other, self.dir)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(os.listdir(other), [])

    def test_a_file_instead_of_the_claude_folder_and_a_folder_instead_of_the_file(self):
        _put(self.dir, 'i am a file')
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.dir), b'i am a file')
        os.remove(self.dir)
        os.makedirs(self.f)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertTrue(os.path.isdir(self.f))


class Disconnect(Base):
    def test_nothing_to_remove_writes_nothing(self):
        self.assertEqual(claude_hook.disconnect(self.space, PORT)['state'], 'missing')
        self.assertFalse(os.path.exists(self.dir))
        _put(self.f, '{"hooks": {"Stop": []}, "x":   1}')
        before = _get(self.f)
        claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_get(self.f), before, 'порожній Stop людини — не наше, байти ті самі')

    def test_foreign_hooks_stay_and_only_ours_go(self):
        original = {'env': {'A': '1'}, 'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'command': 'echo pre'}]}],
                                                  'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}
        _put(self.f, json.dumps(original))
        claude_hook.connect(self.space, PORT)
        self.assertEqual(claude_hook.disconnect(self.space, PORT)['state'], 'missing')
        self.assertEqual(_json(self.f), original)

    def test_a_stop_and_hooks_emptied_by_us_are_removed_but_other_keys_stay(self):
        _put(self.f, json.dumps({'env': {'A': '1'}}))
        claude_hook.connect(self.space, PORT)
        claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_json(self.f), {'env': {'A': '1'}})

    def test_a_file_that_becomes_empty_is_deleted(self):
        claude_hook.connect(self.space, PORT)
        self.assertEqual(claude_hook.disconnect(self.space, PORT), {'state': 'missing', 'path': self.f})
        self.assertFalse(os.path.exists(self.f))
        self.assertEqual(self.tmp_files(), [])

    def test_disconnect_removes_every_copy_of_ours(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [_ours(OTHER)]}, {'hooks': [_ours(PORT)]}]}}))
        claude_hook.disconnect(self.space, PORT)
        self.assertFalse(os.path.exists(self.f))

    def test_a_change_before_removal_is_refused(self):
        claude_hook.connect(self.space, PORT)
        doc = _json(self.f)
        doc['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': 'echo keep'}]})
        _put(self.f, json.dumps(doc))
        claude_hook.connect(self.space, OTHER)             # лишилось дві групи: наша й чужа

        def mutate():
            _put(self.f, '{"theirs": 1}')
        with self.racing(mutate):
            with self.assertRaises(ValueError) as cm:
                claude_hook.disconnect(self.space, OTHER)
        self.assertEqual(str(cm.exception), 'changed')
        self.assertEqual(_get(self.f), b'{"theirs": 1}')


class Exclude(Base):
    """`.git/info/exclude`: рядок додаємо один раз, лише коли МИ створили файл і `.git` — тека."""

    def setUp(self):
        super().setUp()
        self.git = os.path.join(self.space, '.git')
        self.exclude = os.path.join(self.git, 'info', 'exclude')

    def lines(self):
        return _get(self.exclude).decode('utf-8').split('\n')

    def test_a_created_file_adds_the_line_once(self):
        os.makedirs(self.git)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.lines(), [LINE, ''])
        claude_hook.connect(self.space, OTHER)             # перезапис (stale) нового рядка не додає
        claude_hook.disconnect(self.space, OTHER)          # файл видалено
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.lines().count(LINE), 1)

    def test_existing_exclude_text_is_kept_and_gets_a_newline_first(self):
        _put(self.exclude, '# mine')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.exclude), ('# mine\n' + LINE + '\n').encode('utf-8'))

    def test_a_file_that_already_existed_is_not_ours_to_hide(self):
        os.makedirs(self.git)
        _put(self.f, '{}')
        claude_hook.connect(self.space, PORT)
        self.assertFalse(os.path.exists(self.exclude))

    def test_a_git_file_worktree_or_submodule_gets_no_exclude(self):
        _put(self.git, 'gitdir: ../elsewhere\n')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.git), b'gitdir: ../elsewhere\n')
        self.assertEqual(self.state(), 'ok')

    def test_no_git_means_no_git(self):
        claude_hook.connect(self.space, PORT)
        self.assertFalse(os.path.exists(self.git))

    def test_an_unwritable_exclude_does_not_fail_the_connect(self):
        os.makedirs(os.path.join(self.git, 'info', 'exclude'))      # exclude — тека: дописати не можна
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')


class Elsewhere(Base):
    def setUp(self):
        super().setUp()
        self.outer = os.path.join(self.root, 'outer')
        os.makedirs(os.path.join(self.outer, '.git'))
        self.inner = os.path.join(self.outer, 'a', 'space')
        os.makedirs(self.inner)

    def test_a_space_inside_another_repository_is_elsewhere_and_nothing_is_written(self):
        self.assertEqual(claude_hook.status(self.inner, PORT),
                         {'state': 'elsewhere', 'path': os.path.join(self.inner, '.claude', 'settings.local.json')})
        self.assertEqual(claude_hook.connect(self.inner, PORT)['state'], 'elsewhere')
        self.assertFalse(os.path.exists(os.path.join(self.inner, '.claude')))

    def test_the_repository_root_itself_is_not_elsewhere(self):
        self.assertEqual(claude_hook.status(self.outer, PORT)['state'], 'missing')

    def test_a_space_with_its_own_git_dir_or_file_is_not_elsewhere(self):
        os.mkdir(os.path.join(self.inner, '.git'))
        self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')
        shutil.rmtree(os.path.join(self.inner, '.git'))
        _put(os.path.join(self.inner, '.git'), 'gitdir: ../x\n')
        self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_the_home_folder_repository_does_not_count(self):
        with mock.patch.object(claude_hook, '_home', return_value=self.outer):
            self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_on_windows_there_is_no_elsewhere(self):
        with mock.patch.object(claude_hook, '_WINDOWS', True):
            self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_a_plain_space_without_any_repository_above_is_not_elsewhere(self):
        self.assertEqual(self.state(), 'missing')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Запустити — має впасти**

Run: `python3 -B -m unittest discover -s tests -p "test_claude_hook.py" -v 2>&1 | tail -8`
Expected: `ModuleNotFoundError: No module named 'claude_hook'` (імпорт у верхівці файла), `FAILED (errors=1)`.

- [ ] **Step 3: Реалізувати `app/claude_hook.py`**

Створи `app/claude_hook.py`:

```python
"""Stop-хук Claude Code простору (23.11.2026): «Підключити» ставить у `hooks.Stop` файла `<простір>/.claude/settings.local.json`
ОДНУ нашу групу, яка після кожної відповіді Claude шле канвасу JSON сесії на `POST /api/autosync` (сервер бере з нього лише `cwd`).

Лише ця машина: локальний файл налаштувань теки простору, не командний `.claude/settings.json` і не глобальний `~/.claude`.
Наш хук відрізняє від чужих мітка `# deai-autosync` наприкінці команди — інших ознак нема. Хук завжди тихий: без виводу, `|| true`,
канвас вимкнено → нічого. Windows на справжній машині не перевірено (команда — синтаксис sh).

Запис — злиття, а не перезапис: чужі хуки й ключі лишаються; наші групи (точніше, наші записи в групах) прибираємо й ставимо одну
свіжу, тож повторне «Підключити» не дублює. Нечитне (симлінк, не-звичайний файл чи тека `.claude`, не UTF-8, не JSON, верхній
рівень не обʼєкт, `hooks` не обʼєкт, `hooks.Stop` не список) не чіпаємо взагалі: стан `unreadable`, `connect`/`disconnect` → `OSError`.
Запис атомарний (тимчасовий файл у `.claude/`, `fsync`, права як у наявного, новий — за umask); перед заміною файл читається ще раз,
і зміна (чужа правка, файл, що зʼявився) — `ValueError('changed')`. Форматування файла може змінитись (відступ 2 пробіли).
"""
import json
import os
import uuid

HOOK_MARK = '# deai-autosync'
FILE = '.claude/settings.local.json'
EXCLUDE_LINE = '/' + FILE
#: Шов тестів: на Windows стану `elsewhere` нема (там файл завжди поруч із `.claude/settings.json`).
_WINDOWS = os.name == 'nt'


def _home():
    """Домашня тека (шов тестів): її `.git` і все вище — не «інший репозиторій»."""
    return os.path.expanduser('~')


def command(port):
    """Команда хука для порту канваса. `port` не число → `ValueError` (у shell-рядок потрапляє лише ціле)."""
    return ("curl -s --noproxy '*' --max-time 5 -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary @- "
            f"http://127.0.0.1:{int(port)}/api/autosync || true {HOOK_MARK}")


def _dir(space_dir):
    return os.path.join(space_dir, os.path.dirname(FILE))


def _path(space_dir):
    return os.path.join(space_dir, *FILE.split('/'))


def _read_raw(space_dir):
    """Байти файла налаштувань чи `None` (файла нема). Симлінк чи не-тека `.claude`, симлінк чи не-звичайний файл, відмова
    читання — `OSError`: такий файл ми не читаємо й не замінюємо (заміна розірвала б симлінк)."""
    d = _dir(space_dir)
    if os.path.islink(d) or (os.path.lexists(d) and not os.path.isdir(d)):
        raise OSError('.claude: not a directory')
    p = _path(space_dir)
    if os.path.islink(p) or (os.path.lexists(p) and not os.path.isfile(p)):
        raise OSError('settings.local.json: not a regular file')
    try:
        with open(p, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        return None


def _parse(raw):
    """Обʼєкт налаштувань з байтів (`None` → `{}`); усе, з чим ми не вміємо зливати, — `OSError`."""
    if raw is None:
        return {}
    try:
        doc = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise OSError('settings.local.json: not JSON') from None
    if not isinstance(doc, dict):
        raise OSError('settings.local.json: not an object')
    if 'hooks' in doc:
        hooks = doc['hooks']
        if not isinstance(hooks, dict):
            raise OSError('settings.local.json: hooks is not an object')
        if 'Stop' in hooks and not isinstance(hooks['Stop'], list):
            raise OSError('settings.local.json: hooks.Stop is not a list')
    return doc


def _is_ours(h):
    return isinstance(h, dict) and isinstance(h.get('command'), str) and HOOK_MARK in h['command']


def _our_hooks(doc):
    out = []
    for g in (doc.get('hooks') or {}).get('Stop') or []:
        if isinstance(g, dict) and isinstance(g.get('hooks'), list):
            out += [h for h in g['hooks'] if _is_ours(h)]
    return out


def _strip(doc, prune):
    """Прибрати наші записи з `hooks.Stop` (на місці). Група, що спорожніла через нас, зникає; чужі записи тієї самої групи
    лишаються. `prune` — ще й прибрати порожні `Stop` і `hooks`, що спорожніли через нас. Повертає `(doc, скільки прибрано)`."""
    hooks = doc.get('hooks')
    if not isinstance(hooks, dict) or not isinstance(hooks.get('Stop'), list):
        return doc, 0
    kept, removed = [], 0
    for g in hooks['Stop']:
        if isinstance(g, dict) and isinstance(g.get('hooks'), list) and any(_is_ours(h) for h in g['hooks']):
            rest = [h for h in g['hooks'] if not _is_ours(h)]
            removed += len(g['hooks']) - len(rest)
            if rest:
                kept.append({**g, 'hooks': rest})
            continue
        kept.append(g)
    if removed == 0:
        return doc, 0
    if kept or not prune:
        hooks['Stop'] = kept
    else:
        del hooks['Stop']
        if not hooks:
            del doc['hooks']
    return doc, removed


def _add(doc, port):
    doc.setdefault('hooks', {}).setdefault('Stop', []).append(
        {'hooks': [{'type': 'command', 'timeout': 10, 'command': command(port)}]})


def _elsewhere(space_dir):
    """Тека простору всередині ІНШОГО git-репозиторію: `.git` є в предку, а не в самій теці (`.git` — тека чи файл). Домашня тека
    й усе вище не рахуються. Claude Code тоді читає `settings.local.json` з кореня того репозиторію, а туди ми не пишемо."""
    if _WINDOWS:
        return False
    cur = os.path.realpath(space_dir)
    if os.path.lexists(os.path.join(cur, '.git')):
        return False
    home = os.path.realpath(_home())
    cur = os.path.dirname(cur)
    while True:
        if cur == home:
            return False
        if os.path.lexists(os.path.join(cur, '.git')):
            return True
        up = os.path.dirname(cur)
        if up == cur:
            return False
        cur = up


def status(space_dir, port):
    """`{state, path}`; ніколи не кидає. `elsewhere` (хук тут не діє) — раніше за решту; далі `unreadable`, `missing` (нашого хука
    нема), `stale` (є, але команда інша для `port` чи записів більше одного), `ok`."""
    p = _path(space_dir)
    try:
        if _elsewhere(space_dir):
            return {'state': 'elsewhere', 'path': p}
        ours = _our_hooks(_parse(_read_raw(space_dir)))
        if not ours:
            state = 'missing'
        elif len(ours) == 1 and ours[0].get('command') == command(port):
            state = 'ok'
        else:
            state = 'stale'
        return {'state': state, 'path': p}
    except Exception:  # noqa: BLE001 — статус для UI не кидає: що б не сталось, це «не читається»
        return {'state': 'unreadable', 'path': p}


def _write(space_dir, doc, before):
    """Атомарний запис `doc`; `before` — байти, які ми читали (`None` — файла не було). Інакше `ValueError('changed')`."""
    d = _dir(space_dir)
    os.makedirs(d, exist_ok=True)
    path = _path(space_dir)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + '\n'
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = None
    tmp = os.path.join(d, f'.settings.local.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)     # права нового файла — за umask
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        if _read_raw(space_dir) != before:      # файл змінили між читанням і заміною: чужу правку не губимо
            raise ValueError('changed')
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _exclude(space_dir):
    """Локально сховати наш файл від git: `.git/info/exclude` (спільний `.gitignore` не чіпаємо). Раз; лише коли `.git` — тека
    (файл `.git` — worktree чи submodule — не чіпаємо). Best-effort: збій тут не провалює «Підключити»."""
    g = os.path.join(space_dir, '.git')
    if os.path.islink(g) or not os.path.isdir(g):
        return
    p = os.path.join(g, 'info', 'exclude')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, encoding='utf-8', errors='surrogateescape', newline='') as f:
                old = f.read()
        except FileNotFoundError:
            old = ''
        if EXCLUDE_LINE in [ln.strip() for ln in old.splitlines()]:
            return
        with open(p, 'a', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(('' if not old or old.endswith('\n') else '\n') + EXCLUDE_LINE + '\n')
    except OSError:
        pass


def connect(space_dir, port):
    """«Підключити»: поставити (чи оновити) наш хук. Повертає `status` після запису. `elsewhere` — нічого не пишемо; `ok` — запису нема;
    нечитне — `OSError`; зміна під час запису — `ValueError('changed')`. Файл, який створили МИ, ховаємо в `.git/info/exclude`."""
    st = status(space_dir, port)
    if st['state'] == 'elsewhere' or st['state'] == 'ok':
        return st
    if st['state'] == 'unreadable':
        raise OSError('unreadable')
    raw = _read_raw(space_dir)
    doc, _ = _strip(_parse(raw), prune=False)
    _add(doc, port)
    _write(space_dir, doc, raw)
    if raw is None:
        _exclude(space_dir)
    return status(space_dir, port)


def disconnect(space_dir, port):
    """«Відключити»: прибрати наші записи; порожні `Stop` і `hooks`, що спорожніли через нас, — теж; файл, що став `{}`, видаляємо
    (тека `.claude/` лишається). Нічого нашого нема — нічого не пишемо. Нечитне — `OSError`; зміна — `ValueError('changed')`."""
    raw = _read_raw(space_dir)
    doc, removed = _strip(_parse(raw), prune=True)
    if removed:
        if doc:
            _write(space_dir, doc, raw)
        else:
            if _read_raw(space_dir) != raw:
                raise ValueError('changed')
            os.remove(_path(space_dir))
    return status(space_dir, port)
```

- [ ] **Step 4: Запустити — має пройти**

Run: `python3 -B -m unittest discover -s tests -p "test_claude_hook.py" -v 2>&1 | tail -8`
Expected: `OK` (усі тести зелені).

Якщо червоніє `test_a_change_before_removal_is_refused`: у `disconnect` перевірка «зміни» робиться читанням `_read_raw` без тимчасового
файла — `racing` спрацьовує лише коли в `.claude/` лежить `*.tmp`. Для гілки видалення (`doc` порожній) тест має готувати саме її:
перевір, що в тесті після `connect(OTHER)` ЧУЖА група ще є (тоді гілка — `_write`, тимчасовий файл є). Якщо тест потрапляє в гілку
видалення — замінити `mutate`-тригер у `racing` на «перше повторне читання після першого», тобто лічильник викликів `_read_raw`.

- [ ] **Step 5: Коміт**

```bash
git add app/claude_hook.py tests/test_claude_hook.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(stop-hook): запис Stop-хука Claude Code в settings.local.json простору" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/claude_hook.py tests/test_claude_hook.py
```

---

### Task 2: `POST /api/autosync` — режим «за шляхом» (`cwd`)

**Files:**
- Modify: `app/serve.py` (`LOCAL_SHOT_BODY_MAX` → нова константа; `do_POST`; `_autosync`; новий `_ai_commit_space`)
- Create: `tests/test_autosync_path.py`

- [ ] **Step 1: Написати падаючі тести**

Створи `tests/test_autosync_path.py`:

```python
"""`POST /api/autosync` за шляхом (23.11.2026): без задачі в запиті й з абсолютним `cwd` у тілі простір знаходиться за префіксом,
і КОЖНА його задача з `.git` фіксує свої брудні власні ітерації як `itN: зміни AI`. Заголовок/префікс задачі важать більше за `cwd`.
З тіла сервер бере лише `cwd`. Усе — у тимчасових `HOME`/`DEAI_HOME`; мережі й справжніх конфігів нема (простір `P` без ролі `vcs`)."""
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None
MARK = 'SECRET-REPLY-7f3a91'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


class AutosyncByPath(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_HOME'] = cls.deai          # стенд уже ізолює; присвоєння — для охоронця test_serve
        patcher = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'Lead', 'GIT_AUTHOR_EMAIL': 'lead@example.com',
                                               'GIT_COMMITTER_NAME': 'Lead', 'GIT_COMMITTER_EMAIL': 'lead@example.com'})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.y_dir = os.path.join(cls.p_path, 'y')
        cls.bare_dir = os.path.join(cls.p_path, 'bare')
        cfg = base._read(cls.p_file)
        cfg['tasks']['y'] = {'title': 'Ігрек', 'dir': cls.y_dir, 'track': 'tool'}
        cfg['tasks']['bare'] = {'title': 'Без git', 'dir': cls.bare_dir, 'track': 'tool'}
        base._write(cls.p_file, cfg)

    def setUp(self):
        super().setUp()
        for tid, d in (('x', self.x_dir), ('y', self.y_dir)):
            shutil.rmtree(d, ignore_errors=True)
            base._task_dir(d, tid)
            st, _ = self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'}, {'X-Canvas-Task': tid})   # it2 + git init + коміт
            self.assertEqual(st, 200)
        shutil.rmtree(self.bare_dir, ignore_errors=True)
        base._task_dir(self.bare_dir, 'bare')

    def dirty(self, d, it='it2', text='<p>AI</p>'):
        with open(os.path.join(d, 'iterations', it, 'index.html'), 'a', encoding='utf-8') as f:
            f.write(text)

    def status(self, d):
        return _git(d, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/')    # iterations.json після `/api/iteration` лишається брудним: не ітерація

    def subject(self, d):
        return _git(d, 'log', '-1', '--format=%s').strip()

    # ---- простір за cwd

    def test_cwd_in_the_space_commits_every_task_with_git(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        self.dirty(self.bare_dir, 'it1')
        st, body = self.post('/api/autosync', {'cwd': self.p_path})        # машина «стоїть» на старому просторі: простір — за шляхом
        self.assertEqual((st, body['reason']), (200, 'no-gitlab'))
        self.assertEqual(sorted(body['ai_tasks']), ['x', 'y'])
        for tid in ('x', 'y'):
            self.assertEqual(body['ai_tasks'][tid]['its'], ['it2'])
            self.assertEqual(body['ai_tasks'][tid]['it'], 'it2')
        self.assertEqual(body['ai'], body['ai_tasks']['x'], '`ai` — результат поточної задачі простору (x)')
        for d in (self.x_dir, self.y_dir):
            self.assertEqual(self.subject(d), 'it2: зміни AI')
            self.assertIn('Deai-Actor: ai', _git(d, 'log', '-1', '--format=%b'))
            self.assertEqual(self.status(d), '')
        self.assertFalse(os.path.exists(os.path.join(self.bare_dir, '.git')), 'задача без git лишається без репо')
        self.assertFalse(os.path.exists(os.path.join(self.a_dir, '.git')), 'інші простори не зачеплено')

    def test_cwd_deeper_in_a_task_folder_finds_the_space(self):
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': os.path.join(self.x_dir, 'iterations', 'it2')})
        self.assertEqual((st, sorted(body['ai_tasks'])), (200, ['y']))

    def test_only_tasks_with_something_to_commit_are_listed(self):
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual((st, sorted(body['ai_tasks']), body['ai']), (200, ['y'], None))     # поточна — x, там чисто

    def test_nothing_dirty_gives_an_empty_map(self):
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual((st, body['ai_tasks'], body['ai']), (200, {}, None))
        self.assertEqual(self.status(self.x_dir) + self.status(self.y_dir), '')

    def test_ai_is_the_current_task_of_that_space(self):
        self.restore_bytes(self.p_file)
        cfg = base._read(self.p_file)
        cfg['current'] = 'y'
        base._write(self.p_file, cfg)
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual(body['ai'], body['ai_tasks']['y'])

    def test_a_failing_task_does_not_stop_the_others_and_the_log_is_clean(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        real = serve.ai_commit

        def flaky(task):
            if task['dir'] == self.x_dir:
                raise RuntimeError('boom')
            return real(task)
        err = io.StringIO()
        with mock.patch.object(serve, 'ai_commit', flaky), mock.patch.object(sys, 'stderr', err):
            st, body = self.post('/api/autosync', {'cwd': self.p_path, 'last_assistant_message': MARK * 40, 'session_id': MARK})
        self.assertEqual(st, 200)
        self.assertEqual(sorted(body['ai_tasks']), ['y'])
        self.assertIsNone(body['ai'])                                   # поточна x — збій
        self.assertIn("autosync: ai-commit 'x'", err.getvalue())
        self.assertIn('RuntimeError', err.getvalue())
        self.assertNotIn(MARK, err.getvalue())
        self.assertEqual(self.subject(self.y_dir), 'it2: зміни AI')

    # ---- пріоритети

    def test_a_task_header_beats_cwd(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path}, {'X-Canvas-Task': 'x'})
        self.assertEqual(st, 200)
        self.assertNotIn('ai_tasks', body, 'названа задача — режим як у 0.36.0')
        self.assertEqual(body['ai']['it'], 'it2')
        self.assertEqual(self.status(self.x_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.y_dir), 'y не чіпали')

    def test_the_task_prefix_beats_cwd_and_a_no_space_cwd(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/t/y/api/autosync', {'cwd': self.tmp})       # cwd поза просторами, але задачу названо
        self.assertEqual(st, 200)
        self.assertNotIn('ai_tasks', body)
        self.assertEqual(body['ai']['it'], 'it2')
        self.assertEqual(self.status(self.y_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_without_cwd_it_is_the_current_task_of_the_machine(self):
        spaces.switch_space(self.p_id)
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        for payload in ({}, {'cwd': 5}, {'cwd': ''}, {'session_id': 's'}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/autosync', payload)
                self.assertEqual(st, 200)
                self.assertNotIn('ai_tasks', body)
        self.assertEqual(self.status(self.x_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.y_dir), 'поточна машини — x; y не чіпали')

    # ---- no-space, no-task

    def test_cwd_outside_every_space_is_no_space_and_nothing_runs(self):
        self.dirty(self.x_dir)
        for cwd in (self.tmp, 'relative/path', '/'):
            with self.subTest(cwd=cwd):
                st, body = self.post('/api/autosync', {'cwd': cwd})
                self.assertEqual((st, body), (200, {'ok': True, 'changed': False, 'reason': 'no-space', 'ai': None}))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_a_space_without_a_current_task_is_no_task(self):
        st, body = self.post('/api/autosync', {'cwd': self.e_path})
        self.assertEqual((st, body), (200, {'ok': True, 'changed': False, 'reason': 'no-task', 'ai': None, 'ai_tasks': {}}))

    # ---- ліміт тіла й приватність

    def test_the_body_cap_is_two_mebibytes(self):
        self.assertEqual(serve.AUTOSYNC_BODY_MAX, 2 * 1024 * 1024)

    def test_a_body_over_the_cap_is_413_before_reading_and_nothing_runs(self):
        self.dirty(self.x_dir)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.putrequest('POST', '/api/autosync')
            conn.putheader('Content-Type', 'application/json')
            conn.putheader('Content-Length', str(10 * 1024 * 1024))
            conn.endheaders()                                           # тіло НЕ шлемо: відмова мусить прийти до читання
            r = conn.getresponse()
            got = json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()
        self.assertEqual((r.status, got['code'], got['ok']), (413, 'body-too-large', False))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_a_body_within_the_cap_is_processed(self):
        self.dirty(self.x_dir)
        with mock.patch.object(serve, 'AUTOSYNC_BODY_MAX', 4096):
            st, body = self.post('/api/autosync', {'cwd': self.p_path, 'pad': 'x' * 3000})
            self.assertEqual((st, sorted(body['ai_tasks'])), (200, ['x']))
            st, got = self.post('/api/autosync', {'cwd': self.p_path, 'pad': 'x' * 5000})
            self.assertEqual((st, got['code']), (413, 'body-too-large'))

    def test_the_other_fields_of_the_body_never_reach_the_log_or_the_answer(self):
        self.dirty(self.x_dir)
        err = io.StringIO()
        payload = {'cwd': self.p_path, 'session_id': MARK + '-s', 'transcript_path': '/t/' + MARK,
                   'hook_event_name': 'Stop', 'stop_hook_active': False, 'last_assistant_message': MARK * 50}
        with mock.patch.object(sys, 'stderr', err):
            st, body = self.post('/api/autosync', payload)
        self.assertEqual(st, 200)
        self.assertNotIn(MARK, err.getvalue())
        self.assertNotIn(MARK, json.dumps(body))

    def test_a_foreign_origin_is_refused_and_nothing_runs(self):
        self.dirty(self.x_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path}, {'Origin': 'http://evil.example'})
        self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Запустити — має впасти**

Run: `python3 -B -m unittest discover -s tests -p "test_autosync_path.py" 2>&1 | tail -15`
Expected: `FAILED`: `KeyError: 'ai_tasks'` (старий `_autosync` не знає режиму), `AttributeError: module 'serve' has no attribute
'AUTOSYNC_BODY_MAX'`, `no-space`-тести — `AssertionError` (відповідь не збігається). Тести заголовка/префікса й `cwd: 5` — вже зелені.

- [ ] **Step 3: Константа й 413 у `app/serve.py`**

Edit 1. Старий рядок (унікальний):

```python
LOCAL_SHOT_MAX = 8 * 1024 * 1024
```

Новий:

```python
LOCAL_SHOT_MAX = 8 * 1024 * 1024
#: `POST /api/autosync`: тіло ≤ 2 МіБ (413 ДО читання). Stop-хук Claude Code шле туди весь JSON сесії (разом з текстом останньої
#: відповіді), а з нього потрібен лише `cwd`; хук на 413 мовчить, наступна відповідь закомітить.
AUTOSYNC_BODY_MAX = 2 * 1024 * 1024
```

Edit 2. У `do_POST` після блоку `local-shots`. Старий текст:

```python
                self._refuse_unread(413, 'body-too-large', 'screenshot body is too large')    # так само: ДО читання
                return
```

Новий:

```python
                self._refuse_unread(413, 'body-too-large', 'screenshot body is too large')    # так само: ДО читання
                return
            if length > AUTOSYNC_BODY_MAX and self.path in ('/api/autosync',):   # кортеж, не `==`: той самий довід, що й у `local-shots`
                self._refuse_unread(413, 'body-too-large', 'autosync body is too large')       # так само: ДО читання
                return
```

- [ ] **Step 4: `_autosync` «за шляхом» і `_ai_commit_space`**

Edit 3. У `_autosync` старий блок (унікальний, від першого виклику до гілки `autosync-off`):

```python
        tid, task, vcs, err = self._vcs_ctx()
        try:
            ai = ai_commit(task) if task is not None else None
        except Exception:  # noqa: BLE001 — локальний збій коміту AI не валить хук: історія просто без цього запису
            sys.stderr.write(_mask_repo(traceback.format_exc()))
            ai = None
        if err is not None or vcs is None or vcs[3] is None:
            out = {'ok': True, 'changed': False, 'reason': 'no-gitlab', 'ai': ai}
            self._send_json({**out, 'code': err.code} if err is not None else out)
            return
        if not (vcs[1].get('settings') or {}).get('autosync'):
            self._send_json({'ok': True, 'changed': False, 'reason': 'autosync-off', 'ai': ai})
            return
```

Новий:

```python
        # Режим «за шляхом» (Stop-хук від «Підключити»): задачу запит НЕ назвав (`_task_override is None`: ні заголовка, ні `/t/<id>/`),
        # у тілі абсолютний `cwd`. Тіло розібрано вище; звідси береться ЛИШЕ `cwd` — решту (текст відповіді, `session_id`) не читаємо й
        # нікуди не пишемо. Простір запиту стає знайденим, тож далі все — рівно як у режимі задачі (`_vcs_ctx` читає ЙОГО файл задач).
        cwd = payload.get('cwd')
        by_path = self._task_override is None and isinstance(cwd, str) and bool(cwd)
        extra, ai_tasks = {}, None
        if by_path:
            sp = agent_guide.find_space(spaces.read_registry()['spaces'], path=cwd)
            if sp is None:
                self._send_json({'ok': True, 'changed': False, 'reason': 'no-space', 'ai': None})
                return
            spaces.set_request_space(sp['id'])
            ai_tasks = self._ai_commit_space(sp)
            extra = {'ai_tasks': ai_tasks}
        try:
            tid, task, vcs, err = self._vcs_ctx()
        except spaces.NoTask:
            if not by_path:
                raise
            self._send_json({'ok': True, 'changed': False, 'reason': 'no-task', 'ai': None, **extra})
            return
        if by_path:
            ai = ai_tasks.get(tid)              # уже закомічено вище, для ВСІХ задач; тут лише результат поточної (сумісність)
        else:
            try:
                ai = ai_commit(task) if task is not None else None
            except Exception:  # noqa: BLE001 — локальний збій коміту AI не валить хук: історія просто без цього запису
                sys.stderr.write(_mask_repo(traceback.format_exc()))
                ai = None
        if err is not None or vcs is None or vcs[3] is None:
            out = {'ok': True, 'changed': False, 'reason': 'no-gitlab', 'ai': ai, **extra}
            self._send_json({**out, 'code': err.code} if err is not None else out)
            return
        if not (vcs[1].get('settings') or {}).get('autosync'):
            self._send_json({'ok': True, 'changed': False, 'reason': 'autosync-off', 'ai': ai, **extra})
            return
```

Edit 4. Гілка збою (унікальний рядок):

```python
            self._send_json({**_vcs_failure(e), 'synced': False, 'changed': False, 'reason': 'offline' if offline else 'error', 'ai': ai})
```

Новий:

```python
            self._send_json({**_vcs_failure(e), 'synced': False, 'changed': False, 'reason': 'offline' if offline else 'error', 'ai': ai, **extra})
```

Edit 5. Фінальна відповідь (унікальний рядок):

```python
        self._send_json({**r, 'ai': ai})
```

Новий:

```python
        self._send_json({**r, 'ai': ai, **extra})
```

Edit 6. Докстрінг `_autosync` — додай абзац наприкінці (старий кінець докстрінга, унікальний):

```python
        в `_guarded` і дають ті самі 404/409/503, що й будь-який маршрут."""
```

Новий:

```python
        в `_guarded` і дають ті самі 404/409/503, що й будь-який маршрут.

        Режим «за шляхом» (23.11.2026; Stop-хук, який ставить «Підключити», шле весь JSON сесії): задачі в запиті нема, у тілі абсолютний
        `cwd` → простір — найдовший префікс серед зареєстрованих (`agent_guide.find_space`), `ai_commit` для КОЖНОЇ його задачі з
        `.git` (`_ai_commit_space`), далі крок відправки — для ПОТОЧНОЇ задачі цього простору, лише коли в модулі ввімкнено autosync.
        Відповідь додатково несе `ai_tasks`. `cwd` поза просторами — `reason: "no-space"`; простір без поточної задачі — `reason:
        "no-task"` (хук мовчить на обох). З тіла береться лише `cwd`."""
```

Edit 7. Новий метод перед `_gitlab_pull`. Старий рядок (унікальний):

```python
    def _gitlab_pull(self, payload):
```

Новий:

```python
    def _ai_commit_space(self, sp):
        """Режим «за шляхом» `/api/autosync`: `ai_commit` для КОЖНОЇ задачі простору `sp` (її тека є на цій машині); задача без `.git`
        — `None` (`ai_commit` сам). Збій однієї — рядок у stderr (лише імʼя задачі й трасування; тіла запиту тут нема), решта йде.
        Повертає `{id задачі: {it, sha, its}}` лише для задач, де щось закомічено."""
        out = {}
        for tid, row in spaces._space_tasks(sp).items():
            d = row.get('dir') if isinstance(row, dict) else None
            if not isinstance(d, str) or not os.path.isdir(d):
                continue
            try:
                ai = ai_commit(row)
            except Exception:  # noqa: BLE001 — збій однієї задачі не валить хук і не зупиняє інші
                sys.stderr.write(f'autosync: ai-commit {tid!r} failed\n' + _mask_repo(traceback.format_exc()))
                continue
            if ai:
                out[tid] = ai
        return out

    def _gitlab_pull(self, payload):
```

- [ ] **Step 5: Запустити — має пройти; охоронці репо зелені**

Run: `python3 -B -m unittest discover -s tests -p "test_autosync_path.py" -v 2>&1 | tail -12`
Expected: `OK` (усі тести).

Run: `python3 -B -m unittest discover -s tests -p "test_iteration_api.py" 2>&1 | tail -4` → `OK` (поведінка без `cwd` не змінилась).

Run: `python3 -B -m unittest tests.test_serve.CurrentTaskReadGuard tests.test_serve.TestsCannotWriteLiveConfig 2>&1 | tail -4` → `OK`.
Пояснення, чому оновлень `SPACES_CURRENT_ALLOWED` не треба: `_autosync` не кличе `spaces.current_id`/`spaces.space_current_task`
(простір бере `find_space`, поточну задачу — `_vcs_ctx()` → `task_for`), а прямого читання ключа `current` у ньому нема.
Нова тестова файл-фікстура містить `switch_space(` (писар просторів), тому має `os.environ['DEAI_HOME'] = …` і `spaces_guard` у
`setUpModule`/`tearDownModule` — це й перевіряє `TestsCannotWriteLiveConfig`.

Run: `python3 -B -m unittest tests.test_serve -k not_a_json_object -v 2>&1 | tail -5` — охоронець `bad-body`
(`test_a_body_that_is_not_a_json_object_is_json_bad_body_on_every_route`) бачить `/api/autosync` і `self._autosync(payload)`; `OK`.

- [ ] **Step 6: Коміт**

```bash
git add tests/test_autosync_path.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(stop-hook): /api/autosync за cwd — AI-коміти всіх задач простору" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/serve.py tests/test_autosync_path.py
```

---

### Task 3: `/api/agents-md` — ключ `hook`, «Підключити» ставить хук, `{hook: false}` знімає

**Files:**
- Modify: `app/serve.py` (`import claude_hook`; `_agents_md_post`; `_agents_md`; новий `_connect_hook`)
- Modify: `tests/test_agents_md.py` (імпорт + клас `HookRoutes`)

- [ ] **Step 1: Написати падаючі тести**

Edit 1 у `tests/test_agents_md.py`. Старий рядок (унікальний):

```python
import agents_md  # noqa: E402
```

Новий:

```python
import agents_md  # noqa: E402
import claude_hook  # noqa: E402
```

Edit 2. Перед `class IterationHeader(base.Fixture):` (унікальний рядок) встав клас; новий текст = клас + рядок-якір:

```python
class HookRoutes(base.Fixture):
    """Stop-хук Claude Code через `GET|POST /api/agents-md` (23.11.2026): ключ `hook`; `claude: true` ставить ще й хук (лише коли
    стан `missing`/`stale`); `hook: false` знімає. Порт — порт цього сервера. Усе — у тимчасовій теці простору `P`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)

    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.p_path, 'CLAUDE.md')
        self.dotclaude = os.path.join(self.p_path, '.claude')
        self.settings = os.path.join(self.dotclaude, 'settings.local.json')
        self.outer_git = os.path.join(self.home, 'deai-work', '.git')       # предок теки простору (усередині тимчасової домівки)
        self.addCleanup(self._clear)
        self._clear()

    def _clear(self):
        for d in (self.dotclaude, self.outer_git):
            if os.path.islink(d) or os.path.isfile(d):
                os.remove(d)
            else:
                shutil.rmtree(d, ignore_errors=True)
        for p in (self.claude, os.path.join(self.p_path, 'AGENTS.md')):
            if os.path.isdir(p) and not os.path.islink(p):
                os.rmdir(p)
            elif os.path.lexists(p):
                os.remove(p)

    def doc(self):
        return json.loads(_get(self.settings).decode('utf-8'))

    def put_settings(self, data):
        os.makedirs(self.dotclaude, exist_ok=True)
        _put(self.settings, data)

    def our_command(self):
        return self.doc()['hooks']['Stop'][0]['hooks'][0]['command']

    def test_get_reports_a_missing_hook_and_writes_nothing(self):
        st, body = self.jget(f'/api/agents-md?space={self.p_id}')
        self.assertEqual(st, 200)
        self.assertEqual(body['hook'], {'state': 'missing', 'path': self.settings})
        self.assertFalse(os.path.exists(self.dotclaude))

    def test_connect_writes_claude_md_and_the_hook_with_the_port_of_this_server(self):
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state'], body['hook']['state']), (200, 'ok', 'ok'))
        self.assertNotIn('hookError', body)
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n')
        self.assertEqual(self.our_command(), claude_hook.command(self.port))
        self.assertFalse(os.path.exists(os.path.join(self.p_path, 'AGENTS.md')), '«Підключити» не створює AGENTS.md')
        self.assertEqual(self.jget(f'/api/agents-md?space={self.p_id}')[1]['hook']['state'], 'ok')

    def test_connect_with_claude_md_already_ok_still_adds_the_hook(self):
        _put(self.claude, b'@AGENTS.md\n')
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['hook']['state']), (200, 'ok'))
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n')

    def test_connect_fixes_a_stale_hook(self):
        claude_hook.connect(self.p_path, self.port + 1)
        self.assertEqual(self.jget(f'/api/agents-md?space={self.p_id}')[1]['hook']['state'], 'stale')
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['hook']['state']), (200, 'ok'))
        self.assertEqual(self.our_command(), claude_hook.command(self.port))
        self.assertEqual(len(self.doc()['hooks']['Stop']), 1)

    def test_an_unreadable_settings_file_is_skipped_but_claude_md_is_connected(self):
        self.put_settings(b'{not json')
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state'], body['hook']['state']), (200, 'ok', 'unreadable'))
        self.assertNotIn('hookError', body)
        self.assertEqual(_get(self.settings), b'{not json')

    def test_a_space_inside_another_repository_gets_no_hook(self):
        os.makedirs(self.outer_git)
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state'], body['hook']['state']), (200, 'ok', 'elsewhere'))
        self.assertFalse(os.path.exists(self.dotclaude))

    def test_a_change_during_the_hook_write_is_a_hook_error_but_claude_md_stays_connected(self):
        self.put_settings(b'{"a": 1}')
        real = claude_hook._read_raw
        done = []

        def wrapper(space_dir):
            d = os.path.join(space_dir, '.claude')
            if not done and os.path.isdir(d) and any(n.endswith('.tmp') for n in os.listdir(d)):
                done.append(1)
                self.put_settings(b'{"a": 2}')
            return real(space_dir)
        with mock.patch.object(claude_hook, '_read_raw', wrapper):
            st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state'], body['hookError']), (200, 'ok', 'changed'))
        self.assertEqual(body['hook']['state'], 'missing')
        self.assertEqual(_get(self.settings), b'{"a": 2}')

    def test_an_unreadable_claude_md_stays_503_and_the_hook_is_not_touched(self):
        os.mkdir(self.claude)
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['code']), (503, 'unreadable'))
        self.assertFalse(os.path.exists(self.dotclaude))

    def test_disconnect_removes_only_the_hook(self):
        self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': False})
        self.assertEqual((st, body['hook']['state'], body['claude']['state']), (200, 'missing', 'ok'))
        self.assertFalse(os.path.exists(self.settings), 'файл, що став {}, видалено')
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n')

    def test_disconnect_keeps_foreign_hooks(self):
        foreign = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}
        self.put_settings(json.dumps(foreign).encode())
        self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': False})
        self.assertEqual((st, body['hook']['state']), (200, 'missing'))
        self.assertEqual(self.doc(), foreign)

    def test_disconnect_of_an_unreadable_file_is_503_and_changed_is_409(self):
        self.put_settings(b'{not json')
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': False})
        self.assertEqual((st, body['code']), (503, 'unreadable'))
        self.assertEqual(_get(self.settings), b'{not json')
        os.remove(self.settings)
        self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        doc = self.doc()
        doc['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': 'echo keep'}]})
        self.put_settings(json.dumps(doc).encode())
        real = claude_hook._read_raw
        done = []

        def wrapper(space_dir):
            d = os.path.join(space_dir, '.claude')
            if not done and os.path.isdir(d) and any(n.endswith('.tmp') for n in os.listdir(d)):
                done.append(1)
                self.put_settings(b'{"theirs": 1}')
            return real(space_dir)
        with mock.patch.object(claude_hook, '_read_raw', wrapper):
            st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': False})
        self.assertEqual((st, body['code']), (409, 'changed'))
        self.assertEqual(_get(self.settings), b'{"theirs": 1}')

    def test_hook_true_is_not_a_command_it_is_the_old_create_or_update(self):
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': True})
        self.assertEqual((st, body['exists']), (200, True))
        self.assertFalse(os.path.exists(self.dotclaude))

    def test_a_foreign_origin_cannot_disconnect(self):
        self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'hook': False}, {'Origin': 'http://evil.example'})
        self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual(self.jget(f'/api/agents-md?space={self.p_id}')[1]['hook']['state'], 'ok')


class IterationHeader(base.Fixture):
```

(`_put`, `_get`, `json`, `shutil`, `mock` у файлі вже імпортовані/оголошені.)

- [ ] **Step 2: Запустити — має впасти**

Run: `python3 -B -m unittest tests.test_agents_md.HookRoutes 2>&1 | tail -12`
Expected: `KeyError: 'hook'` / `AssertionError` (сервер не знає ключа й дії), `FAILED`.

- [ ] **Step 3: Реалізація в `app/serve.py`**

Edit 1. Імпорт. Старий рядок (унікальний):

```python
import agent_guide  # живий гайд агента й автооновлення блоків AGENTS.md (23.11.2026)
```

Новий:

```python
import agent_guide  # живий гайд агента й автооновлення блоків AGENTS.md (23.11.2026)
import claude_hook  # Stop-хук Claude Code простору: правки AI в історії без скіла власника (23.11.2026)
```

Edit 2. `_agents_md_post`. Старий текст (3 рядки):

```python
        """`POST /api/agents-md {space[, claude: true]}`: створити/оновити блок; з `claude: true` — лише підключити CLAUDE.md
        (`agents_md.claude_connect`: дописати `@AGENTS.md` на початок чи створити файл), AGENTS.md не чіпається."""
        self._agents_md(payload.get('space'), 'claude' if payload.get('claude') is True else True)
```

Новий:

```python
        """`POST /api/agents-md {space[, claude: true | hook: false]}`: створити/оновити блок; з `claude: true` — «Підключити»:
        CLAUDE.md (`agents_md.claude_connect`: дописати `@AGENTS.md` на початок чи створити файл) і Stop-хук (`claude_hook.connect`,
        лише коли його стан `missing`/`stale`), AGENTS.md не чіпається; з `hook: false` — «Відключити»: лише хук (`claude_hook.disconnect`).
        `hook: true` команди не є: це звичайне створення/оновлення."""
        if payload.get('hook') is False:
            write = 'unhook'
        else:
            write = 'claude' if payload.get('claude') is True else True
        self._agents_md(payload.get('space'), write)
```

Edit 3. Тіло `_agents_md`. Старий текст (унікальний):

```python
        version = updater.current_version(UPDATER_ROOT)
        try:
            if write == 'claude':
                agents_md.claude_connect(folder)
                st = agents_md.status(folder, version=version)
            elif write:
```

Новий:

```python
        version = updater.current_version(UPDATER_ROOT)
        port = self.server.server_port          # порт цього канваса: у команду хука
        hook_error = None
        try:
            if write == 'unhook':
                claude_hook.disconnect(folder, port)         # лише хук: CLAUDE.md і AGENTS.md не чіпаємо
                st = agents_md.status(folder, version=version)
            elif write == 'claude':
                agents_md.claude_connect(folder)
                st = agents_md.status(folder, version=version)
                hook_error = self._connect_hook(folder, port)
            elif write:
```

Edit 4. Відповідь. Старий рядок (унікальний):

```python
        self._send_json({'ok': True, 'space': sp['id'], **st, 'claude': agents_md.claude_status(folder),
```

Новий:

```python
        self._send_json({'ok': True, 'space': sp['id'], **st, 'claude': agents_md.claude_status(folder),
                         'hook': claude_hook.status(folder, port), **({'hookError': hook_error} if hook_error else {}),
```

Edit 5. Докстрінг `_agents_md`. Старий рядок (унікальний):

```python
        у відповіді, у файл вони не потрапляють. Версія — та сама, що `current` у `GET /api/update`."""
```

Новий:

```python
        у відповіді, у файл вони не потрапляють. Версія — та сама, що `current` у `GET /api/update`.
        `hook` — стан Stop-хука Claude Code (`claude_hook.status`: `ok`/`missing`/`stale`/`unreadable`/`elsewhere`, абсолютний шлях —
        лише тут). `hookError` (`changed`/`unreadable`) зʼявляється, коли CLAUDE.md підключено, а хук поставити не вдалося (200; клієнт
        показує тост збою). `hook: false` — `changed` → 409, нечитний файл → 503, як і для AGENTS.md. Старт канваса хука НЕ чіпає."""
```

Edit 6. Новий метод перед `_agent_guide_get`. Старий рядок (унікальний):

```python
    def _agent_guide_get(self):
```

Новий:

```python
    @staticmethod
    def _connect_hook(folder, port):
        """Друга половина «Підключити»: поставити Stop-хук, коли його стан `missing`/`stale` (для `ok`, `elsewhere` і `unreadable` —
        ні: людина не просила, чи хук тут не діє, чи файл не наш). Повертає `None` або код збою (`changed`/`unreadable`): CLAUDE.md
        на цей момент уже підключено, тож збій хука — не збій відповіді."""
        if claude_hook.status(folder, port)['state'] not in ('missing', 'stale'):
            return None
        try:
            claude_hook.connect(folder, port)
        except ValueError as e:
            return str(e)
        except OSError:
            return 'unreadable'
        return None

    def _agent_guide_get(self):
```

- [ ] **Step 4: Запустити — має пройти**

Run: `python3 -B -m unittest tests.test_agents_md.HookRoutes -v 2>&1 | tail -10` → `OK`.
Run: `python3 -B -m unittest discover -s tests -p "test_agents_md.py" 2>&1 | tail -4` → `OK`.
Run: `python3 -B -m unittest discover -s tests -p "test_first_run_serve.py" 2>&1 | tail -4` → `OK`: наявні тести `claude: true`
лишаються зеленими (хук ставиться в теку простору `P` у тимчасовій домівці; тест `test_post_claude_true_prepends_the_import`
не дивиться на `.claude/`).
Run: `python3 -B -m unittest discover -s tests -p "test_agent_guide.py" 2>&1 | tail -4` → `OK`.

- [ ] **Step 5: Коміт**

```bash
git add tests/test_agents_md.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(stop-hook): «Підключити» ставить хук, «Відключити» знімає — ключ hook в /api/agents-md" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/serve.py tests/test_agents_md.py
```

---

### Task 4: Рядок «Claude Code» — шість станів, список «що буде записано», дії

**Files:**
- Modify: `app/setup-model.js`, `app/first-run.js`, `app/app.js`, `app/i18n.js`, `app/styles.css`
- Modify: `tests/setup-model.test.mjs`, `tests/agents-view.test.mjs`

- [ ] **Step 1: Написати падаючі тести**

Edit 1 у `tests/setup-model.test.mjs`. Старий імпорт (рядок 3):

```js
import { PW_STATE_KEY, claudeRow, pwItem, pwLine, runCommand, shotsBlock, shq } from "../app/setup-model.js";
```

Новий:

```js
import { DICT } from "../app/i18n.js";
import { PW_STATE_KEY, claudeRow, pwItem, pwLine, runCommand, shotsBlock, shq } from "../app/setup-model.js";
```

Edit 2. Замінити старий тест `claudeRow` (рядки 14–21):

```js
test("claudeRow: чотири стани; «Підключити» лише для missing і no-import", () => {
  assert.deepEqual(claudeRow({ state: "ok" }), { icon: "check", tone: "ok", textKey: "frClaudeOk", connect: false });
  assert.deepEqual(claudeRow({ state: "missing" }), { icon: "warn", tone: "warn", textKey: "frClaudeMissing", connect: true });
  assert.deepEqual(claudeRow({ state: "no-import" }), { icon: "warn", tone: "warn", textKey: "frClaudeNoImport", connect: true });
  assert.deepEqual(claudeRow({ state: "unreadable" }), { icon: "warn", tone: "warn", textKey: "frClaudeUnreadable", connect: false });
  assert.equal(claudeRow(undefined), null);
  assert.equal(claudeRow({ state: "weird" }), null);
});
```

на:

```js
const MD = { code: "CLAUDE.md", textKey: "frClaudeWillMd" };
const HOOK = { code: ".claude/settings.local.json", textKey: "frClaudeWillHook" };
const row = (icon, textKey, items = [], button = null) => ({ icon, tone: icon === "check" ? "ok" : "warn", textKey, items, button });
const H = (state) => ({ state });

test("claudeRow, старий сервер без `hook`: як у 0.33.0 — текст про CLAUDE.md, «Підключити» для missing і no-import", () => {
  assert.deepEqual(claudeRow({ state: "ok" }), row("check", "frClaudeOk"));
  assert.deepEqual(claudeRow({ state: "missing" }), row("warn", "frClaudeMissing", [], "connect"));
  assert.deepEqual(claudeRow({ state: "no-import" }), row("warn", "frClaudeNoImport", [], "connect"));
  assert.deepEqual(claudeRow({ state: "ok" }, undefined), row("check", "frClaudeOk"));
  assert.deepEqual(claudeRow({ state: "ok" }, { state: "weird" }), row("check", "frClaudeOk"), "невідомий стан хука — як старий сервер");
});

test("claudeRow, стан 1: CLAUDE.md не підключено — список (CLAUDE.md і, коли хук missing/stale, хук), кнопка «Підключити»", () => {
  for (const cs of ["missing", "no-import"]) {
    assert.deepEqual(claudeRow({ state: cs }, H("missing")), row("warn", null, [MD, HOOK], "connect"));
    assert.deepEqual(claudeRow({ state: cs }, H("stale")), row("warn", null, [MD, HOOK], "connect"));
    for (const hs of ["ok", "elsewhere", "unreadable"]) {
      assert.deepEqual(claudeRow({ state: cs }, H(hs)), row("warn", null, [MD], "connect"), `${cs}/${hs}: хука в списку нема`);
    }
  }
});

test("claudeRow, стани 2–6: CLAUDE.md ok — хук missing / ok / stale / elsewhere / unreadable", () => {
  const ok = { state: "ok" };
  assert.deepEqual(claudeRow(ok, H("missing")), row("warn", null, [HOOK], "connect"));
  assert.deepEqual(claudeRow(ok, H("ok")), row("check", "frClaudeHookOk", [], "disconnect"));
  assert.deepEqual(claudeRow(ok, H("stale")), row("warn", "frClaudeHookStale", [], "update"));
  assert.deepEqual(claudeRow(ok, H("elsewhere")), row("warn", "frClaudeHookElsewhere"));
  assert.deepEqual(claudeRow(ok, H("unreadable")), row("warn", "frClaudeHookUnreadable"));
});

test("claudeRow: CLAUDE.md не читається — як зараз (без кнопки й списку), хук неважливий; стану нема — null", () => {
  for (const hook of [undefined, H("missing"), H("ok"), H("stale"), H("elsewhere"), H("unreadable")]) {
    assert.deepEqual(claudeRow({ state: "unreadable" }, hook), row("warn", "frClaudeUnreadable"));
  }
  assert.equal(claudeRow(undefined), null);
  assert.equal(claudeRow(undefined, H("ok")), null);
  assert.equal(claudeRow({ state: "weird" }, H("ok")), null);
});

test("claudeRow: усі ключі рядка є в обох мовах", () => {
  const keys = new Set(["frClaudeTitle", "frClaudeConnect", "frClaudeUpdate", "frClaudeDisconnect", "frClaudeConnected",
    "frClaudeFailed", "frHookConnected", "frHookDisconnected", "frHookFailed"]);
  for (const cs of ["ok", "missing", "no-import", "unreadable"]) {
    for (const hook of [undefined, H("ok"), H("missing"), H("stale"), H("elsewhere"), H("unreadable")]) {
      const r = claudeRow({ state: cs }, hook);
      if (r.textKey) keys.add(r.textKey);
      for (const i of r.items) keys.add(i.textKey);
    }
  }
  for (const lang of ["uk", "en"]) for (const k of keys) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа ${k}`);
});
```

Edit 3. Наприкінці `tests/agents-view.test.mjs` дописати (`cat >> tests/agents-view.test.mjs`):

```js
/* ── Stop-хук Claude Code (23.11.2026): рядок «Claude Code» із двома файлами ────────────────────────────── */
const HK = (state) => ({ state, path: "/Users/a/deai-work/p/.claude/settings.local.json" });
const withHook = (claude, hook, busy = false) => agentsBodyHTML(A({ state: claude }, { hook: HK(hook) }), busy);
const lis = (h) => (h.match(/<li><code>/g) ?? []).length;

test("рядок «Claude Code», стан 1: CLAUDE.md не підключено — список із двох файлів, «Підключити»", () => {
  const h = withHook("missing", "missing");
  assert.match(h, /data-claude="missing" data-hook="missing"/);
  assert.match(h, /<ul class="fr-will"><li><code>CLAUDE\.md<\/code> — рядок @AGENTS\.md<\/li>/);
  assert.match(h, /<li><code>\.claude\/settings\.local\.json<\/code> — правки Claude в історії як AI, лише на цьому компʼютері<\/li>/);
  assert.equal(lis(h), 2);
  assert.match(h, /data-v="claude"[^>]*>Підключити</);
  assert.doesNotMatch(h, /data-v="unhook"/);
  assert.doesNotMatch(h, /Claude Code прочитає|Поруч нема CLAUDE\.md/, "без пояснювальних підписів: список — це згода");
});

test("рядок «Claude Code», стан 2: CLAUDE.md ok, хук missing — один пункт, «Підключити»", () => {
  const h = withHook("ok", "missing");
  assert.equal(lis(h), 1);
  assert.match(h, /<li><code>\.claude\/settings\.local\.json<\/code>/);
  assert.match(h, /data-v="claude"[^>]*>Підключити</);
});

test("рядок «Claude Code», стан 3: обидва ok — галочка, текст, «Відключити» (знімає лише хук), списку нема", () => {
  const h = withHook("ok", "ok");
  assert.match(h, /data-claude="ok" data-hook="ok"><span class="fr-ic fr-ic--ok">/);
  assert.match(h, /Читає AGENTS\.md; його правки в історії — як AI\./);
  assert.match(h, /data-v="unhook"[^>]*>Відключити</);
  assert.doesNotMatch(h, /fr-will|data-v="claude"/);
  assert.match(withHook("ok", "ok", true), /data-v="unhook" disabled/);
});

test("рядок «Claude Code», стан 4: хук stale — текст про порт і «Оновити» (та сама дія, що «Підключити»)", () => {
  const h = withHook("ok", "stale");
  assert.match(h, /Хук веде на інший порт канваса\./);
  assert.match(h, /data-v="claude"[^>]*>Оновити</);
  assert.doesNotMatch(h, /fr-will/);
});

test("рядок «Claude Code», стани 5 і 6: elsewhere і unreadable — пояснення без кнопки", () => {
  const el = withHook("ok", "elsewhere");
  assert.match(el, /Читає AGENTS\.md\. Хук тут не діє: тека простору всередині іншого git-репозиторію\./);
  assert.doesNotMatch(el, /data-v="(claude|unhook)"/);
  const un = withHook("ok", "unreadable");
  assert.match(un, /\.claude\/settings\.local\.json не читається \(симлінк, тека чи не JSON\)\./);
  assert.doesNotMatch(un, /data-v="(claude|unhook)"/);
});

test("рядок «Claude Code»: CLAUDE.md не читається — як було, без кнопки; старий сервер — без data-hook", () => {
  const h = withHook("unreadable", "ok");
  assert.match(h, /не читається/);
  assert.doesNotMatch(h, /data-v="(claude|unhook)"|fr-will/);
  assert.doesNotMatch(agentsBodyHTML(A({ state: "ok" })), /data-hook/);
});

test("рядок «Claude Code»: англійською ті самі стани", () => {
  setLang("en");
  const h = withHook("missing", "missing");
  assert.match(h, /<li><code>CLAUDE\.md<\/code> — the line @AGENTS\.md<\/li>/);
  assert.match(h, /data-v="claude"[^>]*>Connect</);
  assert.match(withHook("ok", "ok"), /data-v="unhook"[^>]*>Disconnect</);
  assert.match(withHook("ok", "stale"), /data-v="claude"[^>]*>Update</);
});
```

Edit 4. Наприкінці `tests/connections-wiring.test.mjs`-стилю — проводка в `app.js` (той самий файл, що й інші тести `AGENTS.md`; допиши
в кінець `tests/connections-wiring.test.mjs`; `fnc` — його наявний помічник):

```js
test("AGENTS.md, рядок «Claude Code»: «Підключити»/«Оновити» — POST {claude:true}, «Відключити» — POST {hook:false}; тост залежить від відповіді", () => {
  const c = fnc("agentsClaude");
  assert.match(c, /claude: true/);
  assert.match(c, /d\.hookError \? 'frHookFailed'/, "збій хука при підключеному CLAUDE.md — тост збою");
  assert.match(c, /d\.hook\?\.state === 'ok' \? 'frHookConnected' : 'frClaudeConnected'/);
  const u = fnc("agentsUnhook");
  assert.match(u, /hook: false/);
  assert.match(u, /'frHookDisconnected'/);
  assert.match(fnc("agentsAction"), /v === 'unhook'\) agentsUnhook\(\)/);
  assert.match(fnc("agentsRowCall"), /agentsSt\.seq \+= 1;/, "читання, що летіло до запису, застаріло");
  assert.doesNotMatch(fnc("agentsAction"), /await/, "writeText — у тому ж такті, що й клік");
});
```

- [ ] **Step 2: Запустити — має впасти**

Run: `node --test tests/setup-model.test.mjs tests/agents-view.test.mjs tests/connections-wiring.test.mjs 2>&1 | tail -25`
Expected: падають нові тести (`claudeRow` повертає стару форму; немає `.fr-will`, `unhook`, `agentsRowCall`, ключів словника).

- [ ] **Step 3: `app/setup-model.js` — `claudeRow(claude, hook)`**

Edit. Старий текст (функція разом із докстрінгом):

```js
/** Рядок «Claude Code» розділу AGENTS.md за `claude` з `GET /api/agents-md`; `null` — стану нема (старий сервер). */
export function claudeRow(claude) {
  switch (claude?.state) {
    case "ok": return { icon: "check", tone: "ok", textKey: "frClaudeOk", connect: false };
    case "missing": return { icon: "warn", tone: "warn", textKey: "frClaudeMissing", connect: true };
    case "no-import": return { icon: "warn", tone: "warn", textKey: "frClaudeNoImport", connect: true };
    case "unreadable": return { icon: "warn", tone: "warn", textKey: "frClaudeUnreadable", connect: false };
    default: return null;
  }
}
```

Новий:

```js
const WILL_MD = { code: "CLAUDE.md", textKey: "frClaudeWillMd" };
const WILL_HOOK = { code: ".claude/settings.local.json", textKey: "frClaudeWillHook" };
const HOOK_STATES = ["ok", "missing", "stale", "unreadable", "elsewhere"];

/** Рядок «Claude Code» розділу AGENTS.md за `claude` і `hook` з `GET /api/agents-md`; `null` — стану CLAUDE.md нема.
    `{icon, tone, textKey | null, items: [{code, textKey}], button: null | "connect" | "update" | "disconnect"}`.
    `items` — список «що буде записано» (він і є згода людини; тоді пояснювального тексту нема). Старий сервер без `hook`
    (чи невідомий стан) — як у 0.33.0: лише CLAUDE.md. CLAUDE.md не читається — без кнопки, хук неважливий. */
export function claudeRow(claude, hook) {
  const cs = claude?.state;
  if (!["ok", "missing", "no-import", "unreadable"].includes(cs)) return null;
  const row = (icon, textKey, items = [], button = null) => ({ icon, tone: icon === "check" ? "ok" : "warn", textKey, items, button });
  if (cs === "unreadable") return row("warn", "frClaudeUnreadable");
  const hs = HOOK_STATES.includes(hook?.state) ? hook.state : null;
  if (hs === null) {
    if (cs === "ok") return row("check", "frClaudeOk");
    return row("warn", cs === "missing" ? "frClaudeMissing" : "frClaudeNoImport", [], "connect");
  }
  const hookItems = hs === "missing" || hs === "stale" ? [WILL_HOOK] : [];
  if (cs !== "ok") return row("warn", null, [WILL_MD, ...hookItems], "connect");
  switch (hs) {
    case "ok": return row("check", "frClaudeHookOk", [], "disconnect");
    case "missing": return row("warn", null, hookItems, "connect");
    case "stale": return row("warn", "frClaudeHookStale", [], "update");
    case "elsewhere": return row("warn", "frClaudeHookElsewhere");
    default: return row("warn", "frClaudeHookUnreadable");
  }
}
```

- [ ] **Step 4: `app/first-run.js` — розмітка рядка**

Edit 1. Старий рядок:

```js
  const row = claudeRow(a?.claude);
```

Новий:

```js
  const row = claudeRow(a?.claude, a?.hook);
```

Edit 2. Старий блок (рядки `const cl = row … : "";`):

```js
  const cl = row
    ? `<div class="set-row" data-claude="${esc(a.claude.state)}"><span class="fr-ic fr-ic--${row.tone}">${ico(row.icon, 16)}</span>`
      + `<div class="set-row-l"><span class="set-row-t">${esc(t("frClaudeTitle"))}</span><span class="set-row-s">${esc(t(row.textKey))}</span></div>`
      + (row.connect ? `<div class="set-row-a"><button type="button" class="ctl ctl--out" data-th="ag" data-v="claude"${busy ? " disabled" : ""}>${esc(t("frClaudeConnect"))}</button></div>` : "")
      + `</div>`
    : "";
```

Новий:

```js
  // кнопка → [data-v, ключ підпису]: «Підключити» і «Оновити» — та сама дія (`{claude: true}`), «Відключити» знімає лише хук
  const BTN = { connect: ["claude", "frClaudeConnect"], update: ["claude", "frClaudeUpdate"], disconnect: ["unhook", "frClaudeDisconnect"] };
  const btn = row?.button ? BTN[row.button] : null;
  const will = row?.items.length
    ? `<ul class="fr-will">${row.items.map((i) => `<li><code>${esc(i.code)}</code> — ${esc(t(i.textKey))}</li>`).join("")}</ul>`
    : "";
  const cl = row
    ? `<div class="set-row" data-claude="${esc(a.claude.state)}"${a.hook?.state ? ` data-hook="${esc(a.hook.state)}"` : ""}>`
      + `<span class="fr-ic fr-ic--${row.tone}">${ico(row.icon, 16)}</span>`
      + `<div class="set-row-l"><span class="set-row-t">${esc(t("frClaudeTitle"))}</span>`
      + (row.textKey ? `<span class="set-row-s">${esc(t(row.textKey))}</span>` : "") + will + `</div>`
      + (btn ? `<div class="set-row-a"><button type="button" class="ctl ctl--out" data-th="ag" data-v="${btn[0]}"${busy ? " disabled" : ""}>${esc(t(btn[1]))}</button></div>` : "")
      + `</div>`
    : "";
```

- [ ] **Step 5: `app/app.js` — дії**

Edit 1. Замінити `agentsClaude` (старий текст — увесь блок з докстрінгом):

```js
/** «Підключити» CLAUDE.md (0.33.0): `POST /api/agents-md {space, claude: true}` — дописати `@AGENTS.md` на початок чи
    створити файл. Відповідь — той самий стан розділу (з `claude`); збій — тост і перечитування. */
async function agentsClaude() {
  const sid = agentsSt.spaceId;
  if (agentsSt.busy || !sid || sid !== connState.spaceId) return;
  agentsSt.busy = true;
  paintHome();
  let data = null;
  try { data = await post('/api/agents-md', { space: sid, claude: true }); } catch (e) { data = null; }
  agentsSt.seq += 1;
  agentsSt.busy = false;
  if (!connOpen() || connState.spaceId !== sid) return;
  if (data) { agentsSt.data = data; toast(t('frClaudeConnected')); }
  else { toast(t('frClaudeFailed')); loadAgents(); }
  paintHome();
  if (connSec === 'agents') focusAgents();
}
```

на:

```js
/** Дія рядка «Claude Code»: `POST /api/agents-md {space, …extra}`. Відповідь — той самий стан розділу (з `claude` і `hook`); тост
    за відповіддю (`okKey(data)`), збій — `failKey` і перечитування. Читання, що летіло до запису, застаріло (`seq`). */
async function agentsRowCall(extra, okKey, failKey) {
  const sid = agentsSt.spaceId;
  if (agentsSt.busy || !sid || sid !== connState.spaceId) return;
  agentsSt.busy = true;
  paintHome();
  let data = null;
  try { data = await post('/api/agents-md', { space: sid, ...extra }); } catch (e) { data = null; }
  agentsSt.seq += 1;
  agentsSt.busy = false;
  if (!connOpen() || connState.spaceId !== sid) return;
  if (data) { agentsSt.data = data; toast(t(okKey(data))); }
  else { toast(t(failKey)); loadAgents(); }
  paintHome();
  if (connSec === 'agents') focusAgents();
}

/** «Підключити» / «Оновити» (0.33.0, хук — 23.11.2026): `{claude: true}` — CLAUDE.md і Stop-хук Claude Code. Збій хука при
    підключеному CLAUDE.md сервер віддає як `hookError` (200): тост збою. */
function agentsClaude() {
  return agentsRowCall({ claude: true },
    (d) => (d.hookError ? 'frHookFailed' : d.hook?.state === 'ok' ? 'frHookConnected' : 'frClaudeConnected'), 'frClaudeFailed');
}

/** «Відключити»: `{hook: false}` — знімає лише хук (CLAUDE.md лишається). */
function agentsUnhook() {
  return agentsRowCall({ hook: false }, () => 'frHookDisconnected', 'frHookFailed');
}
```

Edit 2. У `agentsAction` (унікальний рядок):

```js
  else if (v === 'claude') agentsClaude();
```

Новий:

```js
  else if (v === 'claude') agentsClaude();
  else if (v === 'unhook') agentsUnhook();
```

- [ ] **Step 6: `app/i18n.js` — ключі (uk і en)**

Edit 1 (uk). Старий рядок (унікальний):

```js
  frClaudeFailed: 'Не вдалося змінити CLAUDE.md — файл змінився чи не читається',
```

Новий:

```js
  frClaudeFailed: 'Не вдалося змінити CLAUDE.md — файл змінився чи не читається',
  frClaudeWillMd: 'рядок @AGENTS.md',
  frClaudeWillHook: 'правки Claude в історії як AI, лише на цьому компʼютері',
  frClaudeHookOk: 'Читає AGENTS.md; його правки в історії — як AI.',
  frClaudeHookStale: 'Хук веде на інший порт канваса.',
  frClaudeHookElsewhere: 'Читає AGENTS.md. Хук тут не діє: тека простору всередині іншого git-репозиторію.',
  frClaudeHookUnreadable: '.claude/settings.local.json не читається (симлінк, тека чи не JSON).',
  frClaudeUpdate: 'Оновити',
  frClaudeDisconnect: 'Відключити',
  frHookConnected: 'Підключено · правки Claude Code в історії — як AI',
  frHookDisconnected: 'Хук відключено',
  frHookFailed: 'Не вдалося змінити .claude/settings.local.json — файл змінився чи не читається',
```

Edit 2 (en). Старий рядок (унікальний):

```js
  frClaudeFailed: 'Could not change CLAUDE.md — the file changed or cannot be read',
```

Новий:

```js
  frClaudeFailed: 'Could not change CLAUDE.md — the file changed or cannot be read',
  frClaudeWillMd: 'the line @AGENTS.md',
  frClaudeWillHook: 'Claude’s edits show up in history as AI, on this computer only',
  frClaudeHookOk: 'Reads AGENTS.md; its edits show up in history as AI.',
  frClaudeHookStale: 'The hook points to a different canvas port.',
  frClaudeHookElsewhere: 'Reads AGENTS.md. The hook does not apply here: the space folder is inside another git repository.',
  frClaudeHookUnreadable: '.claude/settings.local.json cannot be read (a symlink, a folder or not JSON).',
  frClaudeUpdate: 'Update',
  frClaudeDisconnect: 'Disconnect',
  frHookConnected: 'Connected · Claude Code edits show up in history as AI',
  frHookDisconnected: 'Hook disconnected',
  frHookFailed: 'Could not change .claude/settings.local.json — the file changed or cannot be read',
```

- [ ] **Step 7: `app/styles.css` — список «що буде записано»**

Edit. Старий рядок (унікальний):

```css
.fr-run{margin-bottom:16px}
```

Новий:

```css
.fr-run{margin-bottom:16px}
.fr-will{display:flex;flex-direction:column;gap:4px;margin:6px 0 0;padding:0;list-style:none;font-size:12px;line-height:1.45;color:var(--mid)}
.fr-will code{padding:1px 5px;border-radius:var(--r-sm);background:var(--s3);color:var(--hi);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;overflow-wrap:anywhere}
```

- [ ] **Step 8: Запустити — має пройти**

Run: `node --test tests/setup-model.test.mjs tests/agents-view.test.mjs tests/connections-wiring.test.mjs tests/first-run.test.mjs tests/i18n.test.mjs tests/i18n-keys.test.mjs tests/i18n-literals.test.mjs tests/css-guards.test.mjs tests/js-parses.test.mjs 2>&1 | tail -12`
Expected: усе `pass`, `fail 0`. Якщо `css-guards`/`i18n-literals` скаржаться — це їхній сигнал: клас `fr-will` має бути лише в `styles.css` і в
`first-run.js`; у JS не має бути кириличних літералів поза `i18n.js`.

- [ ] **Step 9: Коміт**

```bash
git add tests/setup-model.test.mjs tests/agents-view.test.mjs tests/connections-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(stop-hook): рядок «Claude Code» із хуком — шість станів і список запису" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/setup-model.js app/first-run.js app/app.js app/i18n.js app/styles.css tests/setup-model.test.mjs tests/agents-view.test.mjs tests/connections-wiring.test.mjs
```

---

### Task 5: Наскрізний тест — справжня команда хука проти тестового сервера

**Files:**
- Create: `tests/test_claude_hook_e2e.py`

Мета: довести, що рядок команди з `claude_hook.command(port)` (записаний справжнім `POST /api/agents-md`) працює в `sh -c` з
підробленим JSON сесії на stdin: брудна власна ітерація стає `itN: зміни AI`; канвас вимкнено — тиша й код 0; завеликий JSON — тиша
й код 0, нічого не закомічено. Нові виробничі зміни тут не потрібні (реалізація Task 1–3); тест — доказ контракту.

- [ ] **Step 1: Написати тест**

Створи `tests/test_claude_hook_e2e.py`:

```python
"""Наскрізно (23.11.2026): рядок команди з «Підключити» запускається через `sh -c` з підробленим JSON сесії Claude Code на stdin
проти тестового сервера в процесі (порт 0). Хук тихий за будь-яких обставин: порожній stdout/stderr і код 0. Лише loopback; справжні
`~/.deai`, `~/.claude` і порт 8765 не чіпаються."""
import json
import os
import shutil
import socket
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import claude_hook  # noqa: E402
import serve  # noqa: E402,F401
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None
CURL = shutil.which('curl')


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


@unittest.skipUnless(CURL and shutil.which('sh'), 'потрібні sh і curl')
class HookEndToEnd(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_HOME'] = cls.deai          # стенд уже ізолює; присвоєння — для охоронця test_serve
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)
        patcher = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'Lead', 'GIT_AUTHOR_EMAIL': 'lead@example.com',
                                               'GIT_COMMITTER_NAME': 'Lead', 'GIT_COMMITTER_EMAIL': 'lead@example.com'})
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def setUp(self):
        super().setUp()
        shutil.rmtree(self.x_dir, ignore_errors=True)
        base._task_dir(self.x_dir, 'x')
        st, _ = self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'}, {'X-Canvas-Task': 'x'})     # it2 + git init + коміт
        self.assertEqual(st, 200)
        shutil.rmtree(os.path.join(self.p_path, '.claude'), ignore_errors=True)
        for name in ('CLAUDE.md', 'AGENTS.md'):
            p = os.path.join(self.p_path, name)
            if os.path.lexists(p):
                os.remove(p)
        # хук ставимо справжньою кнопкою, а команду беремо з файла, який вона записала
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['hook']['state']), (200, 'ok'))
        with open(os.path.join(self.p_path, '.claude', 'settings.local.json'), encoding='utf-8') as f:
            self.cmd = json.load(f)['hooks']['Stop'][0]['hooks'][0]['command']
        self.assertEqual(self.cmd, claude_hook.command(self.port))

    def run_hook(self, cmd, stdin):
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}     # loopback — без проксі оточення
        return subprocess.run(['sh', '-c', cmd], input=stdin, capture_output=True, text=True, env=env, timeout=30, cwd=self.tmp)

    def session(self, **extra):
        return json.dumps({'session_id': 's-1', 'transcript_path': '/t/x.jsonl', 'cwd': self.p_path, 'hook_event_name': 'Stop',
                           'stop_hook_active': False, 'last_assistant_message': 'готово', **extra})

    def dirty(self):
        with open(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html'), 'a', encoding='utf-8') as f:
            f.write('<p>AI</p>')

    def test_a_dirty_own_iteration_becomes_an_ai_commit(self):
        self.dirty()
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')
        self.assertIn('Deai-Actor: ai', _git(self.x_dir, 'log', '-1', '--format=%b'))
        self.assertEqual(_git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'), '')

    def test_a_second_call_after_the_same_reply_is_safe(self):
        self.dirty()
        self.run_hook(self.cmd, self.session())
        head = _git(self.x_dir, 'rev-parse', 'HEAD')
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(_git(self.x_dir, 'rev-parse', 'HEAD'), head)

    def test_with_the_canvas_stopped_the_hook_is_silent_and_exits_zero(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            free = s.getsockname()[1]                     # порт, на якому ніхто не слухає
        r = self.run_hook(claude_hook.command(free), self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def test_an_oversized_session_json_is_silent_and_commits_nothing_the_next_reply_does(self):
        self.dirty()
        big = self.session(last_assistant_message='x' * (serve.AUTOSYNC_BODY_MAX + 1024))
        r = self.run_hook(self.cmd, big)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertIn('iterations/it2/index.html', _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'))
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')

    def test_a_session_started_outside_every_space_does_nothing(self):
        self.dirty()
        r = self.run_hook(self.cmd, self.session(cwd=self.tmp))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertIn('iterations/it2/index.html', _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Запустити**

Run: `python3 -B -m unittest discover -s tests -p "test_claude_hook_e2e.py" -v 2>&1 | tail -12`
Expected: `OK` (5 тестів; на машині без `curl` — `skipped`). Тести мають пройти одразу: Task 1–3 уже в гілці. Якщо
`test_an_oversized…` чи `test_with_the_canvas_stopped…` дає `returncode != 0` — це дірка в команді, а не в тесті: `|| true`
має ховати будь-який транспортний код `curl` (перевір, що в `claude_hook.command` він ПЕРЕД міткою). На сам 413 curl без `--fail`
і так виходить з 0.

- [ ] **Step 3: Мутаційна перевірка доказу** (не комітити зміни)

Тимчасово прибери `|| true` з `claude_hook.command` → `test_with_the_canvas_stopped…` має впасти (код 7). Поверни рядок.

- [ ] **Step 4: Коміт**

```bash
git add tests/test_claude_hook_e2e.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(stop-hook): наскрізно — команда хука через sh проти тестового сервера" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/test_claude_hook_e2e.py
```

---

### Task 6: Документи для агентів — `docs/agents/hooks.md` і `SETUP.md`

**Files:**
- Modify: `docs/agents/hooks.md`
- Modify: `SETUP.md`

Каркас AGENTS.md (`app/templates/agents.md`, 69 рядків при бюджеті 80) НЕ змінюється: його рядок про `POST /api/autosync` — запасний
шлях для агентів без хука. Рядок 2 теми `hooks` (її індекс у блоці) НЕ змінюється, щоб не міняти мітку `guide` без потреби.

- [ ] **Step 1: `docs/agents/hooks.md`**

Edit 1. Після абзацу про `SessionStart` (старий текст — речення, що закінчує вступ):

```markdown
The same section has a `SessionStart` hook that prints the live guide (`GET /api/agent-guide`) at the start of a Claude Code session.
```

Новий:

```markdown
The same section has a `SessionStart` hook that prints the live guide (`GET /api/agent-guide`) at the start of a Claude Code session.

## The Stop hook the canvas installs

The person presses «Connect» in Settings → AGENTS.md (row «Claude Code»; the button reads «Connect», «Update» or «Disconnect»).
The canvas then writes ONE Stop hook into `<space folder>/.claude/settings.local.json` — the local file of this computer, never the
team's `.claude/settings.json` and never `~/.claude/settings.json`. It merges into `hooks.Stop` and leaves other hooks and keys
alone; its command is a silent `curl` that ends with the mark `# deai-autosync` (that mark is how the canvas recognises its own
hook) and posts to `http://127.0.0.1:<port>/api/autosync`, the port of the canvas that was running when the button was pressed.
After every reply Claude Code gives the hook a JSON on stdin and the hook forwards it; the canvas reads only `cwd` from it. The hook
prints nothing, never blocks, and does nothing while the canvas is stopped. Do not add such a hook by hand: ask the person to press
the button. The hook is not installed when the space folder is inside another git repository (Claude Code reads the settings file
from the root of that repository) or when the settings file is unreadable (a symlink, a folder, not JSON); the row says so.
A canvas restart never changes the hook; if the canvas later runs on another port the row offers «Update».
This is the hook of Claude Code only; for another agent use the call below by hand (see `AGENTS.md`).

When a session of such an agent ends a reply, every own changed iteration of every task of the space is committed as `itN: зміни AI`
(see «Autosync by folder» below). A change a person makes outside the canvas in the same minute is committed as AI too.
```

Edit 2. Наприкінці файла (після абзацу «…The task is named by `X-Canvas-Task`, as everywhere; without it, the\ncurrent one.») додай, як новий підрозділ:

```markdown

### Autosync by folder

    POST http://127.0.0.1:8765/api/autosync {"cwd": "/absolute/path/inside/the/space", …anything else is ignored}

Without `X-Canvas-Task` (or the `/t/<task-id>` prefix) and with an absolute `cwd` in the body, the canvas finds the space by the
longest matching folder among the registered spaces and commits the own changed iterations of EVERY task of that space that has a
`.git` (a failure in one task is logged and the rest go on). Then it sends the newest own iteration of the space's CURRENT task, as
above (only with the module's autosync on). The answer has the fields of that send plus `ai` (the current task's AI commit) and
`ai_tasks`: `{"<task-id>": {"it", "sha", "its"}}` for every task where something was committed (`{}` when nothing was).
`{"ok": true, "changed": false, "reason": "no-space", "ai": null}` — `cwd` is in no registered space, nothing is done;
`reason: "no-task"` — the space has no current task (the AI commits of the other tasks were still made). A named task always wins
over `cwd`; with neither a task nor `cwd`, the current task of the computer is used. The canvas reads only `cwd` from the body
(never the text of the reply or the session id) and keeps nothing; a body over 2 MiB is `413 body-too-large` before it is read.
```

- [ ] **Step 2: `SETUP.md` («Agent status»)**

Edit. Старий текст (початок другого абзацу розділу):

```markdown
Agents read `AGENTS.md` once, when a session starts. To also give Claude Code the live state of the canvas (the space,
```

Новий:

```markdown
For Claude Code the canvas installs the Stop hook itself: the person presses the button of the «Claude Code» row in
Settings → AGENTS.md (it reads «Connect»). That one press also connects `CLAUDE.md` and writes the hook into
`.claude/settings.local.json` of the space folder, so the agent's edits to iterations are committed in the history as AI
without any skill. Do not write that hook by hand — tell the person to press the button (the row lists exactly what it writes).

Agents read `AGENTS.md` once, when a session starts. To also give Claude Code the live state of the canvas (the space,
```

- [ ] **Step 3: Перевірки покриття**

Run: `python3 -B -m unittest discover -s tests -p "test_agent_guide_coverage.py" 2>&1 | tail -4` → `OK` (нових маршрутів нема; `/api/autosync` описаний).
Run: `python3 -B -m unittest discover -s tests -p "test_agent_guide.py" 2>&1 | tail -4` → `OK`.
Run: `python3 -B -m unittest discover -s tests -p "test_setup_md.py" 2>&1 | tail -4` → `OK` (у `SETUP.md` нема кирилиці, маршрути існують).
Run: `python3 -c "import sys; sys.path.insert(0,'app'); import agents_md; print(len(agents_md.render_block(version='0.36.0').splitlines()))"` → число ≤ 80 і
`git diff --stat -- app/templates/agents.md` порожній (каркас не змінено).

- [ ] **Step 4: Коміт**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs(stop-hook): хук від «Підключити» і режим /api/autosync за cwd" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/agents/hooks.md SETUP.md
```

---

### Task 7: Живий тест рядка, повна перевірка, фінальне ревʼю, реліз (реліз — лише після «да» власника)

**Files:**
- Modify: `tests/live/agents-md.test.mjs`
- Modify (лише після «да»): `package.json`, `CHANGELOG.md`

- [ ] **Step 1: Живий сценарій 5**

Edit у `tests/live/agents-md.test.mjs`. Старий рядок (унікальний, останній у файлі):

```js
guardRealDeai();
```

Новий:

```js
test("5: «Claude Code» — «Підключити» ставить CLAUDE.md і хук, галочка; «Відключити» знімає хук, кнопка знову", async (t) => {
  const server = await boot(t, PORT_BASE + 40, null);
  const { page, errors } = server;
  const space = server.spaces[0].path;
  const settings = path.join(space, ".claude", "settings.local.json");
  const claude = path.join(space, "CLAUDE.md");
  const port = new URL(server.url).port;
  await gear(page);
  await toAgents(page);
  await page.waitForSelector('[data-claude="missing"][data-hook="missing"]', { timeout: 15000 });
  assert.equal(await page.locator(".fr-will li").count(), 2, "список «що буде записано»: CLAUDE.md і хук");
  assert.match(await page.locator(".fr-will").textContent(), /CLAUDE\.md.*\.claude\/settings\.local\.json/);
  assert.equal((await page.locator('[data-claude] [data-v="claude"]').textContent()).trim(), "Підключити");
  assert.equal(existsSync(settings), false, "до згоди нічого не записано");

  await page.click('[data-claude] [data-v="claude"]');
  await page.waitForSelector('[data-claude="ok"][data-hook="ok"]', { timeout: 15000 });
  assert.equal((await toastText(page)).trim(), "Підключено · правки Claude Code в історії — як AI");
  assert.equal(readFileSync(claude, "utf8"), "@AGENTS.md\n");
  const cmd = JSON.parse(readFileSync(settings, "utf8")).hooks.Stop[0].hooks[0].command;
  assert.ok(cmd.endsWith("# deai-autosync"), "наша мітка");
  assert.ok(cmd.includes(`:${port}/api/autosync`), "порт цього канваса");
  assert.equal(await page.locator(".fr-will").count(), 0, "підключено — списку нема");
  assert.match(await page.locator("[data-claude]").textContent(), /Читає AGENTS\.md; його правки в історії — як AI\./);
  assert.equal((await page.locator('[data-claude] [data-v="unhook"]').textContent()).trim(), "Відключити");
  assert.equal((await api(server)).hook.state, "ok");

  await page.waitForFunction(() => !document.querySelector("#cv-toast.show"), null, { timeout: 15000 });
  await page.click('[data-claude] [data-v="unhook"]');
  await page.waitForSelector('[data-claude="ok"][data-hook="missing"]', { timeout: 15000 });
  assert.equal((await toastText(page)).trim(), "Хук відключено");
  assert.equal(existsSync(settings), false, "файл, що став порожнім, видалено");
  assert.equal(readFileSync(claude, "utf8"), "@AGENTS.md\n", "CLAUDE.md не зачеплено");
  assert.equal(await page.locator(".fr-will li").count(), 1, "знову один пункт — хук");
  assert.equal((await page.locator('[data-claude] [data-v="claude"]').textContent()).trim(), "Підключити", "кнопка повернулась");
  assert.deepEqual(errors, []);
});

guardRealDeai();
```

Run (під замком, один файл):

```bash
until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/agents-md.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo rc=$rc
```
Expected: `rc=0`, усі 5 сценаріїв (`# pass 5`).

Run (теж під замком; перший запуск проводить `[data-v="claude"]` через новий рядок):

```bash
until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/first-run.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo rc=$rc
```
Expected: `rc=0` (сценарій з `[data-claude="missing"] [data-v="claude"]` проходить з хуком).

- [ ] **Step 2: Усі тести**

Run: `python3 -B -m unittest discover -s tests -p "test_*.py"` → `OK`.
Run: `node --test tests/*.test.mjs` → `fail 0`.

- [ ] **Step 3: Охоронник публічного репо**

```bash
DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses
```
Expected: `OK`.

- [ ] **Step 4: Фінальне ревʼю** — `superpowers:code-reviewer` (sonnet) по всій гілці проти спеки; окремо попросити звернути увагу на:
запис у файл налаштувань людини (атомарність, `changed`, симлінки), приватність тіла в `_autosync`, відсутність абсолютних шляхів у
файлах репо, сумісність відповіді `/api/autosync` для хука dev-pipeline (він реагує лише на `blocked`/`foreign-only`/`offline`/`changed`/`catchup`;
нові причини `no-space`/`no-task` для нього «невідомі», тож мовчить).

- [ ] **Step 5: Ручна перевірка на копії** (без справжнього `~/.claude`): у тимчасовій теці створити простір, натиснути кнопку в UI тестового канваса
не потрібно — достатньо `python3 -c` з `claude_hook.connect(<temp>, 4317)`/`disconnect` і перегляду файла очима: відступ 2, наша група одна,
мітка наприкінці.

- [ ] **Step 6: Реліз — лише після явного «да» власника на push/мерж**

Версія — наступна вільна мінорна після 0.37.0 на момент злиття (`git fetch` не робити без «да»; дивись `package.json` у `main`):
`package.json` → `version`; `CHANGELOG.md` — новий розділ зверху у форматі наявних (`## [X.Y.0] — DD.MM.YYYY`, «Додано»/«Змінено»).
Зміст: «Підключити» в «Налаштування → AGENTS.md» ставить і Stop-хук Claude Code в `.claude/settings.local.json` простору (мітка
`# deai-autosync`; лише ця машина; список запису в рядку; «Оновити» при іншому порту, «Відключити» знімає лише хук); `POST /api/autosync`
за `cwd` (`no-space`, `no-task`, `ai_tasks`; тіло ≤ 2 МіБ); хук канвас сам не ставить і не лагодить при старті.
«Owner actions after update»: у кожному просторі відкрити «Налаштування → AGENTS.md» і натиснути «Підключити» в рядку «Claude Code» (рядок
показує кнопку, поки хука нема); хук діє й у вже відкритих сесіях Claude Code.
«Виправлено» (Task 8): крок відправки автосинку комітить решту теки задачі без `Deai-Actor: ai`. Чужі правки, файли поза ітераціями
й перший коміт теки в історії більше не «правка AI», а `sync` від людини.
«Known limits» (ризик прийнято): коли хук спрацьовує, УСЕ незакомічене у СВОЇХ ітераціях цієї машини комітиться як AI. Це стосується
й ручної правки людини поза канвасом (у редакторі), ще не закоміченої. Правки через канвас уже закомічені під іменем людини.

---

### Task 8: Крок відправки автосинку без трейлера AI (поправка 24.11.2026, спека — розділ 5)

Виконується ДО Task 7 Step 6 (реліз). Після неї — повторити Task 7 Steps 2–4: усі тести, охоронник, фінальне ревʼю.

**Files:**
- Modify: `app/serve.py` — у `autosync()` тема `git_autocommit` без `\n\n{iter_history.AI_TRAILER}`, плюс коментар «чому».
- Modify: `tests/phase_i_subjects.py` — прибрати переклад `itN: автосинк (…)` → `+ трейлер` (`_SYNC`, `TRAILER`), докстрінг.
- Modify: `tests/test_liga_migrate_b.py:205` — очікування `['it1: автосинк (design-canvas)']`.
- Test: `tests/test_vcs_core.py` — клас `Legacy`, поруч із `test_the_local_autocommit_of_the_autosync_keeps_the_design_canvas_signature_in_liga`.
- Modify: `docs/agents/hooks.md` (розділ «Autosync», кроки 1–2), `docs/agents/vcs.md` (абзац «Committing locally…»).

- [ ] **Step 1: Падаючі тести** (`tests/test_vcs_core.py`, клас `Legacy`; `import iter_history` угорі файла, якщо його нема)

```python
    # ---------------------------------------------------------------- крок 2 без трейлера AI (спека Stop-хука, розділ 5)
    def test_the_autosync_commit_is_a_person_commit_without_the_ai_trailer(self):
        """Крок 2 комітить решту теки (і файл поза ітераціями) БЕЗ `Deai-Actor: ai`.
        Мутація: поверни `\\n\\n{iter_history.AI_TRAILER}` у тему коміту в `autosync()` — тест червоніє."""
        self.write_it1('<h1>v-plain</h1>')
        write(os.path.join(self.task_dir, 'notes.md'), 'чиясь нотатка')
        serve.autosync('t1', self.task, self.gl)
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%B'), 'it1: автосинк (design-canvas)')
        self.assertIn('notes.md', self.out(self.task_dir, 'show', '--name-only', '--format=', 'HEAD').split())

    def test_the_first_commit_of_a_folder_without_git_is_not_signed_ai(self):
        """Тека без `.git`: крок 1 її не чіпає (`ai_commit` → `None`), крок 2 створює репо — і перший коміт теж не «AI»."""
        self.assertFalse(os.path.exists(os.path.join(self.task_dir, '.git')))
        self.assertIsNone(serve.ai_commit(self.task))
        serve.autosync('t1', self.task, self.gl)
        self.assertNotIn('Deai-Actor', self.out(self.task_dir, 'log', '--format=%B'))

    def test_after_the_ai_step_a_colleague_edit_is_a_person_sync_and_mine_stays_ai(self):
        """Порядок маршруту `/api/autosync`: `ai_commit` (крок 1), далі `autosync` (крок 2). В історії ітерації колеги — `sync` від
        людини (до поправки — `ai`); у своїй — коміт кроку 1 `ai`, над ним `sync` кроку 2 (тема називає `it1`) від людини."""
        serve.autosync('t1', self.task, self.gl)                      # `.git` і перша відправка
        write(os.path.join(self.task_dir, 'iterations', 'it2', 'index.html'), '<h1>чуже</h1>')
        self.save_meta({'iterations': [{'id': 'it1'},
                                       {'id': 'it2', 'author': 'Ольга', 'author_key': 'designer2@example.com'}],
                        'current': 'it1'})
        self.write_it1('<h1>v-ai</h1>')
        self.assertEqual(serve.ai_commit(self.task)['its'], ['it1'])
        r = serve.autosync('t1', self.task, self.gl)
        self.assertTrue(r.get('synced'), r)
        theirs = iter_history.history(self.task_dir, {'id': 'it2'})['entries'][0]
        self.assertEqual((theirs['kind'], theirs['actor']['kind']), ('sync', 'person'))
        mine = iter_history.history(self.task_dir, {'id': 'it1'})['entries']
        self.assertEqual([(e['kind'], e['actor']['kind']) for e in mine[:2]], [('sync', 'person'), ('ai', 'ai')])
```

Тест `test_the_local_autocommit_of_the_autosync_is_signed_deai_in_an_ordinary_space` (клас `Plain`) лишається як є: тема та сама.

- [ ] **Step 2: Запустити — має впасти**

Run: `python3 -B -m unittest tests.test_vcs_core -k without_the_ai_trailer -k not_signed_ai -k colleague_edit_is_a_person_sync`
Expected: FAIL — у тілі коміту `Deai-Actor: ai`; історія `it2` — `('ai', 'ai')`.

- [ ] **Step 3: `app/serve.py`, `autosync()`**

```python
    # Крок 2 — БЕЗ трейлера `Deai-Actor: ai` (спека Stop-хука, розділ 5, 24.11.2026): свої брудні ітерації вже закомітив як AI
    # крок 1 (`ai_commit` у маршруті), тож тут лишається те, чиє авторство невідоме — ітерації колег, файли поза ітераціями,
    # перший коміт теки без `.git`. Його підписуємо як будь-який коміт дії канваса: людина, git-ідентичність цієї машини.
    local = git_autocommit(task['dir'], f'{it}: автосинк ({"deai" if v is not None and not v[2] else "design-canvas"})')
```

- [ ] **Step 4: Знімки фази «И»** — `tests/phase_i_subjects.py`: прибрати `_SYNC`, `TRAILER` і гілку `if _SYNC.match(text)`; у докстрінгу замість
пункту про автосинк — «`itN: автосинк (<інструмент>)` — без перекладу: з 24.11.2026 крок 2 автосинку знову комітить без трейлера (спека
Stop-хука, розділ 5), як у знімках». `tests/test_liga_migrate_b.py:205` → `['it1: автосинк (design-canvas)']`.

- [ ] **Step 5: Документи**

`docs/agents/hooks.md`, «Autosync»:
- у кроці 1 замість «(colleagues' iterations and other files stay uncommitted)» — «(colleagues' iterations and other files are not part of it)»;
- крок 2:

```
2. Then, with autosync on and your newest own iteration changed since the last send, it commits whatever is still
   uncommitted in the task folder (colleagues' iterations, files outside iterations, the folder's first commit) as
   `itN: автосинк (deai)` (`design-canvas` in a LIGA space) without the AI trailer, so the history shows it as a person's
   `sync`, and sends that iteration to the repository. It never answers with a server error.
```

`docs/agents/vcs.md`, кінець абзацу «Committing locally…»: «A send first commits the rest of the task folder as `itN: автосинк (…)`
without the AI trailer: the history shows it as a person's `sync`, not as your edit.»

`docs/agents/iterations.md`: перевірити, що опис `sync` («a commit `itN: автосинк` without the AI trailer») і `ai` правдиві; якщо тема згадує
`args.synced`, додати, що так позначено старі коміти автосинку з трейлером (0.36.0–0.37.x).

- [ ] **Step 6: Запустити — має пройти**

Run: `python3 -B -m unittest tests.test_vcs_core tests.test_liga_migrate_b tests.test_liga_migrate_c tests.test_liga_parity_4d4b tests.test_iter_history tests.test_iteration_api tests.test_autosync_path tests.test_claude_hook_e2e tests.test_gitlab_sync tests.test_serve tests.test_agent_guide tests.test_agent_guide_coverage`
Expected: OK. Потім мутаційна перевірка (не комітити): повернути трейлер у `autosync()` — три нові тести й `test_liga_migrate_b` червоніють.

- [ ] **Step 7: Коміт**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "fix(autosync): крок відправки комітить решту теки без трейлера AI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/serve.py tests/test_vcs_core.py tests/phase_i_subjects.py tests/test_liga_migrate_b.py docs/agents/hooks.md docs/agents/vcs.md docs/agents/iterations.md
```

---

## Самоперевірка плану проти спеки

| Пункт спеки | Де |
|---|---|
| Хук — одна група з `timeout: 10`, точна команда, `<port>` = `self.server.server_port`, мітка `# deai-autosync` | Task 1 (`command`, тест `test_the_command_is_the_documented_one…`), Task 3 (`port = self.server.server_port`) |
| Хук тихий (`-s`, `-o /dev/null`, `|| true`), не блокує | Task 1 (`command`), Task 5 (тиша й код 0, зупинений канвас, 413) |
| `/api/autosync`: задача в запиті → як раніше; `cwd` → простір за префіксом, `ai_commit` усіх задач з `.git`, збій однієї — stderr; крок відправки поточної; `no-space`; без обох — як було | Task 2 (`_autosync`, `_ai_commit_space`; тести: усі задачі, заголовок/префікс > `cwd`, `no-space`, без `cwd`, збій задачі) |
| Відповідь: поля кроку відправки, `ai`, `ai_tasks` | Task 2 (`extra` у всіх відповідях режиму; тести) |
| З тіла лише `cwd`; секрет не в stderr; запит не виходить за межі машини | Task 2 (`test_the_other_fields…`, `test_a_failing_task…`) |
| `AUTOSYNC_BODY_MAX` 2 МіБ → 413 до читання | Task 2 (константа, `do_POST`, тести), Task 5 (хук мовчить на 413) |
| Подвійний виклик безпечний | Task 5 (`test_a_second_call…`) |
| Origin | Task 2 (`test_a_foreign_origin…`), Task 3 (403 на `hook: false`) |
| `claude_hook`: злиття, одна свіжа група, `ok` без запису | Task 1 (`Connect`, `Status`) |
| `unreadable` (симлінк файла й `.claude`, не-тека, не UTF-8, не JSON, не обʼєкт, `hooks`, `Stop`) | Task 1 (`Unreadable`) |
| Атомарний запис, права, `fsync`, повторне читання → `ValueError('changed')` | Task 1 (`_write`, тести `changed`, режим, umask) |
| Нема `.claude/` — створюємо | Task 1 (`test_creates_the_folder_and_the_file`) |
| «Відключити»: наші групи, порожні `Stop`/`hooks`, `{}` → файл видалено | Task 1 (`Disconnect`) |
| `.git/info/exclude` раз, лише коли МИ створили файл; `.git`-файл не чіпаємо | Task 1 (`Exclude`) |
| `elsewhere` (предок з `.git`, не домашня; Windows — нема) | Task 1 (`Elsewhere`) |
| `GET` → `hook`; `POST claude: true` → CLAUDE.md + хук для `missing`/`stale`; `elsewhere`/`unreadable` пропуск; збій хука → відповідь зі станами; `changed` 409, `unreadable` 503; `hook: false` | Task 3 (`_agents_md`, `_connect_hook`, `HookRoutes`) |
| Старт канваса хука не чіпає | Task 3 (змін у `refresh_spaces`/`serve_main` нема); Task 6 (документовано); Task 7 (CHANGELOG) |
| Рядок: 6 станів, список = згода, CLAUDE.md `unreadable`, старий сервер, тексти uk+en, тости | Task 4 (`claudeRow`, `agentRowsHTML`, i18n, `app.js`) |
| Документи: `hooks.md`, `SETUP.md`; каркас не змінюється | Task 6 |
| Тести: усі пункти списку спеки | Task 1, 2, 4, 5; живий — Task 7; сторож покриття — Task 6 |
| Реліз після 0.37.0, лише після «да»; «Owner actions after update» | Task 7, Step 6 |

Узгодженість імен між задачами: `claude_hook.command/status/connect/disconnect`, `HOOK_MARK`, `FILE`, `_home`, `_WINDOWS`, `_read_raw` (Task 1) — ті
самі в Task 3 і в тестах Task 3/5; `AUTOSYNC_BODY_MAX`, `_ai_commit_space`, `ai_tasks`, `no-space`, `no-task` (Task 2) — ті самі в Task 5 і docs;
ключ відповіді `hook`, поле `hookError`, дія `{hook: false}` (Task 3) — ті самі в `app.js` (Task 4: `d.hookError`, `d.hook?.state`, `hook: false`);
`data-hook`, `data-v="unhook"`, `.fr-will` (Task 4) — ті самі в живому тесті (Task 7); `claudeRow` → `{icon, tone, textKey, items, button}` — ті самі
в `first-run.js` і тестах.

Помічені й виправлені під час самоперевірки: (1) помічник `fnc` у `connections-wiring.test.mjs` шукає лише `function name(`, тож `agentsClaude`/`agentsUnhook`
оголошено функціями, а не стрілками; (2) `claudeRow` спершу віддавав `connect: true/false`, але рядкові стани 3–4 потребують різних кнопок — перейшли на `button`; (3) `disconnect`
спершу не мав `port`, хоча `status` після запису його потребує — додано `port` (відступ від сигнатури в спеці, описаний у «Карті файлів»).

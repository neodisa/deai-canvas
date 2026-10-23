# Етап 3c «Свої модулі простору й діалог довіри» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** свої модулі простору (`<простір>/modules/<id>/`) виконуються лише після довіри людини — знімок показаних байтів у `<DEAI_HOME>/trusted/<хеш>/`, запис у `<DEAI_HOME>/trust.json`, останнє слово за системним вікном ОС; екран «Підключення», діалог довіри й крок 2 майстра їх показують; реліз 0.7.0.

**Architecture:** новий `app/module_trust.py` — сканер теки, хеш, порівняння, записи довіри, знімки, системне вікно (без імпорту ядра модулів). `deai_modules.catalog(space)` додає до вбудованих свої модулі простору: довірений вантажиться зі знімка (з тайм-аутом), недовірений — лише маніфест без виконання; явно ввімкнений свій модуль, що не працює, — помилка ролі без запасного шляху. `serve.py` отримує `GET/POST /api/module-trust`, `POST /api/module-untrust` і адресу адаптера з простором. Клієнт: картки й примітки (`connections-*`), діалог (`trust-view.js` + `openTrust` у `app.js`), рядки кроку 2 майстра.

**Tech Stack:** Python 3 stdlib (`unittest`, `subprocess`, `hashlib`), ванільний ES-модульний JS (`node:test`), Playwright Chromium для живого тесту.

**Спека:** `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md` (ревізія 2) — читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

- Репо: `<repo>`. Гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5), навіть якщо твоя власна модель інша.
- Додавати в індекс лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — його не чіпати й не комітити.
- Кожен прогін тестів — через охоронця памʼяті: `python3 "$G" <секунд> <МБ> <команда…>` (шлях `$G` дає контролер), напр. `python3 "$G" 900 3000 npm test`. Якщо охоронця нема — сказати контролеру, а не запускати без нього.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати порти 8765 і 4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`. Процеси зупиняти лише за PID, ніколи `pkill`/`killall` за шаблоном.
- **Системне вікно ОС у тестах не показувати**: юніти підміняють `module_trust.confirm`/`subprocess.run` або ставлять шов `DEAI_TRUST_CONFIRM` (діє лише з ізольованим `DEAI_HOME`). Єдиний ручний показ вікна — Task 9, крок «вручну», з `giving up after 3`.
- Жодної мережі в тестах.
- Конвенції коду: коментарі українською; тексти інтерфейсу лише через `t()` (обидві мови `UK` і `EN` у `app/i18n.js`); кирилиці в літералах `app/**/*.js` поза словником бути не може (`tests/i18n-literals.test.mjs`); дані в розмітку лише через `esc()` з `app/esc.js`; іконки лише відомі `ico()` з `app/icons.js` (іконки `shield` НЕМА — для довіри `lock`); CSS лише токенами.
- ЛІГА-golden (`tests/legacy-golden.test.mjs`) мусить лишатись зеленим БЕЗ `UPDATE_GOLDEN=1`; запис вбудованого модуля в `GET /api/modules` і відповідь простору без своїх модулів — побайтно ті самі (наявні шпильки `tests/test_modules_api.py` не правити).
- Кожна нова перевірка доводиться мутацією: прибрати охорону одним рядком → потрібний тест червоніє → файл відновлено побайтно. Мутації Python — лише `python3 -B` (інакше застарілий `.pyc`), з охоронцем памʼяті й тайм-аутом.
- Повний набір юнітів: `npm test`. Живі тести — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.
- Номери рядків у плані — орієнтир («≈»): шукати за назвою функції.

## Поправки до спеки, знайдені під час планування (внесені в спеку тим самим комітом, що й план)

1. Іконки `shield` у `app/icons.js` нема — бейдж і дія довіри беруть `lock`.
2. **Майстер:** `initialPick` НЕ змінюється. Якби він не вибирав увімкнений недовірений модуль, `offRows` побачив би роль «Без модуля» і `writePlan` ВИМКНУВ би модуль, який колега ввімкнув у `space.json`, — лише тому, що людина пройшла майстер. Натомість: радіо такого модуля вибране й `disabled` з кнопкою «Довіритись…» поруч; крок 3 не малює для нього картки (налаштувань не записує), а показує рядок «чекає довіри».
3. `roleHolders` (`connections-model.js`) уже рахує будь-який увімкнений не-`missing` модуль власником — змін не треба. `erroredOfFreed` (`wizard-model.js`) теж без змін: недовірений має `status: untrusted`, а не `error`, тож окремого `disable` не отримує (його вимкне `replace`, бо сервер тепер рахує його власником ролі).
4. Нові причини `refused`: `unreadable` (теку чи файл не відкрити) і `unstable` (файл змінився під час читання).
5. Запит довіри чекає системного вікна до 120 с: клієнт шле його окремою функцією `trustPost` зі стелею `TRUST_POST_TIMEOUT_MS` = 150 с, а не через `formApi` з типовими 20 с (`formApi` не чіпаємо: його тіло дослівно стереже `tests/spaces-wiring.test.mjs`).
6. `cnTrustNeededWhy` — без аргументу ролі (причина картки малюється `whyHTML`, який аргументів не передає).
7. Запис свого модуля в `GET /api/modules` несе ще `runs: true|false` — чи виконується тут його код (робочий знімок). Без нього клієнт не відрізнить `refused` без знімка (картка «Чому не можна…») від `refused` зі знімком (працює попередня версія): обидва мають `trust: "refused"`.
8. Текст системного вікна живе лише в Python (`module_trust.CONFIRM_TEXT`, Task 2); ключа `trSystemAsk` у `app/i18n.js` нема. Причини `refused`/`untrusted` у словнику — повні речення `trWhy*` (+ `trWhyOther` для невідомого коду); шаблони `cnTrustRefusedNew(why)` і `trRefused(why)` їх вставляють.
9. Нові ключі «Підключень» перевіряє новий `tests/connections-own.test.mjs` (свій тест «кожен ключ моделі є в обох мовах»), а не перелік у `connections-view.test.mjs`.
10. Майстер, крок 3: модуль, вибраний на кроці 2, що тепер потребує довіри й ще не ввімкнений (довіру забрали між кроками), — назад на крок 2 з тостом `cnRefUntrusted`; у `writePlan` такий модуль дає операцію `untrusted` (відмова без запиту), а не `enable` — `runOp` без картки інакше впав би на `forms.get(id).fields`.
11. Роль «на папері» (свій модуль, що тут не працює) у `capabilities` — `None` БЕЗ ключа `error`: клієнт (`connPageHTML`, `providerLine`, крок 2 майстра) читає `capabilities.error` як «space.json не читається» і сховав би всі картки — разом із «Довіритись…» у сценарії «колега закомітив». Рядок «Зараз» такої ролі — «Зараз: «<назва>» — чекає довіри на цьому компʼютері» (`providerLine` → `kind: 'waiting'`, ключ `cnNowWaiting`).
12. Ревʼю плану проти коду (22.10.2026), виправлено до старту Task 2: (а) Task 6 — тест рядка довіри шукав «Є зміни в теці», а текст ключа — «У теці є зміни»; (б) Tasks 3/5 — нові файли тестів САМІ присвоюють `DEAI_HOME` (охоронець `test_serve.SPACE_WRITERS` розбирає джерело файла, присвоєння в імпортованому `Env`/`World` не бачить) і повертають права знімкам перед `rmtree`; (в) Task 6 — наявний пін `loadConn` у `connections-wiring` оновлюється разом із `notes = []`; (г) Task 4 — `_holders`/`_role_conflict`/`grant_trust` беруть ролі й із запису `space.json` (`_roles_of`): зламаний маніфест чи тека, що не приїхала, теж тримають роль «на папері» — інакше пройшов би другий постачальник, а `_paper_failure` затінив би робочого; (ґ) Task 10 — застарілі речення README і `comments.md`, обмеження «старі знімки не прибираються».

## Структура файлів

| файл | відповідальність |
|---|---|
| `app/module_trust.py` (новий) | сканер (`scan`, `fingerprint`, `name_ok`), хеш, `diff`, `tilde`; записи `trust.json` (`load_records`, `put_record`, `drop_record`); знімки (`ensure_snapshot`, `verify_snapshot`, `sweep`); системне вікно (`confirm_command`, `confirm`, `ask`, шов) |
| `app/deai_modules.py` (зміна) | `catalog(space)`, свої модулі (`own_modules`, `own_notes`, `own_sig`), `Module` з полями довіри, завантаження знімка з тайм-аутом, `CORE_STATUS`, простір у API з id; ролі «на папері», помилка ролі без запасного шляху, `roles` у `space.json`; `trust_view`, `grant_trust`, `revoke_trust` |
| `app/serve.py` (зміна) | поля свого модуля й `notes` у `GET /api/modules`, `module_write` без `check` для недовіреного, `task_publish_share`, маршрути `module-trust`/`module-untrust`, адреса адаптера з простором, попередження про шов на старті |
| `app/connections-model.js` (зміна) | `cardView` для своїх модулів, `trustLine`, `noteView`, причини в `whyOf` |
| `app/connections-view.js` (зміна) | пігулка «свій», бейдж `untrusted`, дії `trust`/`trustinfo`, рядок довіри, примітки, «Забрати довіру» в панелі, речення для агента |
| `app/trust-view.js` (новий) | розмітка діалогу довіри, `sizeText`, `trustWhyKey` |
| `app/wizard-model.js`, `app/wizard-view.js`, `app/wizard.js` (зміни) | `needsTrust`, рядок свого модуля на кроці 2, «чекає довіри» на кроці 3, `deps.openTrust` |
| `app/app.js` (зміна) | `openTrust`, `untrustFlow`, `connTrust`, дії `trust`/`trustinfo`/`untrust`, `notes` у стані «Підключень», стеля часу запиту довіри |
| `app/i18n.js`, `app/styles.css` (зміни) | ключі `cn*`/`tr*`/`wz*`, правила `.cn-tag--own`, `.cn-badge--untrusted`, `.cn-trust`, `.cn-notes`, `.tr-*`, `.wz-opt-row`, `.wz-wait` |
| `tests/test_module_trust.py` (новий) | сканер, записи, знімки, системне вікно |
| `tests/test_modules_own.py` (новий) | свої модулі в каталозі, ролі, довіра в ядрі |
| `tests/test_modules_trust_api.py` (новий) | HTTP: `module-trust`, `module-untrust`, адаптер, поля списку |
| `tests/trust-view.test.mjs` (новий), `tests/connections-*.test.mjs`, `tests/wizard-*.test.mjs` (зміни) | юніти клієнта |
| `tests/live/own-modules.test.mjs` (новий) | живий сценарій |
| `docs/modules/authoring.md` (новий), `docs/modules/comments.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | документи й версія 0.7.0 |

---

### Task 1: `module_trust` — сканер теки, хеш, порівняння

**Files:**
- Create: `app/module_trust.py`
- Test: `tests/test_module_trust.py`

- [ ] **Step 1: Тести сканера (червоні)**

Створи `tests/test_module_trust.py`:

```python
"""`app/module_trust.py`: сканер теки свого модуля, хеш, порівняння з довіреним (Task 1); записи довіри, знімки й
системне вікно (Task 2). Спека: `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`.

Кожен тест має власні `HOME` і `DEAI_HOME` (тимчасові); справжній `~/.deai` стереже `spaces_guard`. Системне вікно ОС
не показується НІКОЛИ: `subprocess.run` і `confirm` підмінені там, де до них доходить.
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import module_trust as mt  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _put(root, rel, data=b'x'):
    p = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))
    return p


def _case_insensitive(d):
    probe = os.path.join(d, 'CaseProbe')
    open(probe, 'w').close()
    try:
        return os.path.exists(os.path.join(d, 'caseprobe'))
    finally:
        os.remove(probe)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='mt-'))
        self.addCleanup(self._cleanup)
        self.home = os.path.join(self.tmp, 'home')
        self.deai = os.path.join(self.home, '.deai-test')
        os.makedirs(self.home)
        env = mock.patch.dict(os.environ, {'HOME': self.home, 'DEAI_HOME': self.deai})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DEAI_TRUST_CONFIRM', None)
        mt.reset_cache()
        self.addCleanup(mt.reset_cache)
        if hasattr(mt, 'clear_declined'):              # зʼявляється в Task 2
            mt.clear_declined()
            self.addCleanup(mt.clear_declined)
        self.mod = os.path.join(self.tmp, 'space', 'modules', 'netlify')
        _put(self.mod, 'module.json', json.dumps({'api': 1, 'id': 'netlify', 'roles': ['publish']}))
        _put(self.mod, 'server.py', 'def check(ctx):\n    return {"ok": True}\n')

    def _cleanup(self):
        for dp, dns, fns in os.walk(self.tmp):        # знімки — 0500/0400: повернути запис перед видаленням
            os.chmod(dp, 0o700)
        shutil.rmtree(self.tmp, ignore_errors=True)


class ScanTest(Base):
    def test_counts_files_and_reads_manifest(self):
        sc = mt.scan(self.mod)
        self.assertEqual([f[0] for f in sc.files], ['module.json', 'server.py'])
        self.assertEqual(sc.total, sum(f[1] for f in sc.files))
        self.assertEqual(json.loads(sc.manifest)['id'], 'netlify')
        self.assertIsNone(sc.data)
        self.assertRegex(sc.hash, r'^[0-9a-f]{64}$')

    def test_hash_is_the_documented_canonical_form(self):
        sc = mt.scan(self.mod)
        h = hashlib.sha256()
        for path, size, sha in sorted(sc.files, key=lambda f: f[0].encode('utf-8')):
            h.update(f'{path}\0{size}\0{sha}\n'.encode('utf-8'))
        self.assertEqual(sc.hash, h.hexdigest())

    def test_hash_reacts_to_content_rename_and_new_file(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, 'server.py', 'def check(ctx):\n    return {"ok": False}\n')
        h1 = mt.scan(self.mod, with_data=True).hash
        self.assertNotEqual(h0, h1)
        os.rename(os.path.join(self.mod, 'server.py'), os.path.join(self.mod, 'main.py'))
        h2 = mt.scan(self.mod, with_data=True).hash
        self.assertNotEqual(h1, h2)
        _put(self.mod, 'extra.txt', 'x')
        self.assertNotEqual(h2, mt.scan(self.mod, with_data=True).hash)

    def test_skips_finder_python_and_git_litter(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, '.DS_Store', b'\0\1')
        _put(self.mod, '__pycache__/server.cpython-313.pyc', b'pyc')
        _put(self.mod, 'lib/helper.pyc', b'pyc')
        _put(self.mod, '.git/HEAD', 'ref: refs/heads/main')
        sc = mt.scan(self.mod, with_data=True)
        self.assertEqual(sc.hash, h0)
        self.assertEqual(sorted(sc.data), ['module.json', 'server.py'])

    def test_other_hidden_files_count(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, '.env', 'X=1')
        sc = mt.scan(self.mod, with_data=True)
        self.assertIn('.env', [f[0] for f in sc.files])
        self.assertNotEqual(sc.hash, h0)

    def assertRefused(self, code, root=None):
        with self.assertRaises(mt.Refused) as cm:
            mt.scan(root or self.mod, with_data=True)
        self.assertEqual(cm.exception.code, code, cm.exception.detail)
        return cm.exception

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_refuses_symlinked_file_dir_and_root(self):
        os.symlink(os.path.join(self.mod, 'server.py'), os.path.join(self.mod, 'alias.py'))
        self.assertIn('alias.py', self.assertRefused('symlink').detail)
        os.remove(os.path.join(self.mod, 'alias.py'))
        os.symlink(self.tmp, os.path.join(self.mod, 'up'))
        self.assertRefused('symlink')
        os.remove(os.path.join(self.mod, 'up'))
        link = os.path.join(self.tmp, 'link-mod')
        os.symlink(self.mod, link)
        self.assertRefused('symlink', link)

    @unittest.skipIf(os.name == 'nt', 'жорсткі посилання')
    def test_refuses_hardlink(self):
        os.link(os.path.join(self.mod, 'server.py'), os.path.join(self.tmp, 'outside.py'))
        self.assertRefused('hardlink')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO')
    def test_refuses_fifo(self):
        os.mkfifo(os.path.join(self.mod, 'pipe'))
        self.assertRefused('special-file')

    def test_too_many_files_refused_before_reading_anything(self):
        for i in range(mt.MAX_FILES):
            _put(self.mod, f'f/{i:03}.txt', 'x')
        with mock.patch.object(mt, '_read', side_effect=AssertionError('читання до відмови')):
            self.assertRefused('too-many-files')

    def test_too_big_refused_before_reading_anything(self):
        p = _put(self.mod, 'big.bin', b'')
        with open(p, 'r+b') as f:
            f.truncate(mt.MAX_BYTES + 1)              # розріджений файл: швидко й без 5 МіБ на диску
        with mock.patch.object(mt, '_read', side_effect=AssertionError('читання до відмови')):
            self.assertRefused('too-big')

    def test_depth_limit(self):
        _put(self.mod, '/'.join(['d'] * mt.MAX_DEPTH) + '/ok.txt', 'x')
        mt.scan(self.mod, with_data=True)
        _put(self.mod, '/'.join(['e'] * (mt.MAX_DEPTH + 1)) + '/deep.txt', 'x')
        self.assertRefused('too-deep')

    def test_name_rules(self):
        for bad in ('a\x01b', 'a‮b.js', 'CON', 'nul.txt', 'Com1.js', 'tail.', 'tail ', ' '):
            self.assertFalse(mt.name_ok(bad), repr(bad))
        for good in ('server.py', '.env', 'README', 'ж.txt', 'con-rules.md', 'a b.txt'):
            self.assertTrue(mt.name_ok(good), repr(good))

    def test_bad_name_on_disk_is_refused_and_detail_is_escaped(self):
        _put(self.mod, 'a‮b.js', 'x')
        e = self.assertRefused('bad-name')
        self.assertNotIn('‮', e.detail)

    def test_case_and_nfc_twins_key(self):
        self.assertEqual(mt.twin_key('Server.PY'), mt.twin_key('server.py'))
        self.assertEqual(mt.twin_key('é.js'), mt.twin_key('é.js'))

    def test_case_twins_on_disk(self):
        if _case_insensitive(self.mod):
            self.skipTest('ФС нечутлива до регістру: двійників не створити')
        _put(self.mod, 'A.js', 'x')
        _put(self.mod, 'a.js', 'y')
        self.assertRefused('bad-name')

    def test_unstable_file(self):
        p = os.path.join(self.mod, 'server.py')
        st = os.lstat(p)
        with open(p, 'ab') as f:
            f.write(b'# grew')
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'unstable')

    def test_cache_skips_reading_until_the_tree_changes(self):
        first = mt.scan(self.mod)
        with mock.patch.object(mt, '_read', side_effect=AssertionError('перечитав без змін')):
            self.assertEqual(mt.scan(self.mod), first)
        p = os.path.join(self.mod, 'server.py')
        st = os.stat(p)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5 * 10 ** 9))
        with mock.patch.object(mt, '_read', side_effect=AssertionError('read')):
            with self.assertRaises(AssertionError):
                mt.scan(self.mod)

    def test_cached_refusal_is_raised_again(self):
        _put(self.mod, 'CON', 'x')
        for _ in range(2):
            with self.assertRaises(mt.Refused):
                mt.scan(self.mod)

    def test_with_data_bypasses_cache_and_carries_bytes(self):
        mt.scan(self.mod)
        with mock.patch.object(mt, '_read', wraps=mt._read) as rd:
            sc = mt.scan(self.mod, with_data=True)
        self.assertEqual(rd.call_count, 2)
        self.assertEqual(sc.data['server.py'], open(os.path.join(self.mod, 'server.py'), 'rb').read())


class DiffTest(Base):
    def test_diff_against_record(self):
        sc = mt.scan(self.mod)
        rec = [{'path': 'module.json', 'size': 1, 'sha256': sc.files[0][2]},
               {'path': 'server.py', 'size': 1, 'sha256': '0' * 64},
               {'path': 'old.js', 'size': 300, 'sha256': '1' * 64}]
        files, removed = mt.diff(sc.files, rec)
        self.assertEqual([(f['path'], f['change']) for f in files], [('module.json', 'same'), ('server.py', 'changed')])
        self.assertEqual(removed, [{'path': 'old.js', 'size': 300}])

    def test_diff_without_record_is_all_new(self):
        files, removed = mt.diff(mt.scan(self.mod).files, None)
        self.assertEqual({f['change'] for f in files}, {'new'})
        self.assertEqual(removed, [])

    def test_tilde_only_on_a_path_boundary(self):
        self.assertEqual(mt.tilde(os.path.join(self.home, 'w', 'm')), os.path.join('~', 'w', 'm'))
        self.assertEqual(mt.tilde(self.home + '2/m'), self.home + '2/m')
        self.assertEqual(mt.tilde('/elsewhere/m'), '/elsewhere/m')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 120 1500 python3 -m unittest tests.test_module_trust -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'module_trust'`.

- [ ] **Step 3: Сканер**

Створи `app/module_trust.py`:

```python
"""Свої модулі простору (етап 3c, спека `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`).

Тут — усе, що стосується ДОВІРИ, і нічого з ядра модулів: сканер теки модуля, хеш, порівняння з довіреним (Task 1);
записи `<DEAI_HOME>/trust.json`, знімки `<DEAI_HOME>/trusted/<хеш>/` і системне вікно підтвердження (Task 2). Не
імпортує ні `serve`, ні `deai_modules` (вони імпортують його); з ядра бере лише `spaces` (домівка, шар).

Правила теки (`scan`): обхід без переходу за посиланнями, глибина ≤ `MAX_DEPTH`; лише теки й звичайні файли з
`st_nlink == 1`; `.DS_Store`, теки `__pycache__` і `.git`, файли `*.pyc` пропускаються (не в хеші, не в знімку), бо їх
плодять Finder, локальний запуск і git; ≤ `MAX_FILES` файлів і ≤ `MAX_BYTES` разом — обхід обривається на першому
перевищенні, не читаючи решти; імена — `name_ok` і без двійників за регістром/NFC (`twin_key`). Перше порушення —
`Refused(code, detail)`. Кожен файл читається один раз (`O_NOFOLLOW|O_NONBLOCK`, `fstat` того ж дескриптора).

Хеш теки — sha256 рядків `"<шлях>\\0<розмір>\\0<sha256>\\n"` (UTF-8), відсортованих за UTF-8 байтами шляху.
"""
import errno
import hashlib
import os
import stat
import threading
import unicodedata
from collections import namedtuple

import spaces

MAX_FILES = 200
MAX_BYTES = 5 * 1024 * 1024
MAX_DEPTH = 8
#: Скільки записів дерева бере `fingerprint` — з запасом над `MAX_FILES` (пропущені `*.pyc` теж записи).
FP_MAX = 2000
SKIP_FILES = frozenset({'.DS_Store'})
SKIP_DIRS = frozenset({'__pycache__', '.git'})
SKIP_SUFFIXES = ('.pyc',)
_WIN_RESERVED = frozenset({'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(10)), *(f'lpt{i}' for i in range(10))})
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_OPEN_FLAGS = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)

#: Причини відмови сканера (`Refused.code`). `bad-manifest` ставить ядро (`deai_modules`), не сканер.
REFUSAL_CODES = ('symlink', 'hardlink', 'special-file', 'too-many-files', 'too-big', 'too-deep', 'bad-name',
                 'unreadable', 'unstable', 'bad-manifest')


class Refused(Exception):
    """Теку не можна довірити: `code` — з `REFUSAL_CODES`, `detail` — відносний шлях і пояснення (≤300, лише ASCII-
    безпечне для показу: імена з керівними символами екрануються)."""

    def __init__(self, code, detail=''):
        self.code = code
        self.detail = str(detail)[:300]
        super().__init__(f'{code}: {self.detail}' if self.detail else code)


#: Результат сканування: `hash` теки; `files` — кортеж `(шлях, розмір, sha256)` за UTF-8 байтами шляху; `total` — байтів
#: разом; `manifest` — байти `module.json` (чи `None`); `data` — `{шлях: байти}` лише з `with_data=True`, інакше `None`.
Scan = namedtuple('Scan', 'hash files total manifest data')


def name_ok(name):
    """Імʼя файла чи теки придатне: кодується в UTF-8, без символів категорій `Cc`/`Cf`/`Zl`/`Zp` (керівні, двонапрямні —
    U+202E підробив би перелік файлів у діалозі), не зарезервоване у Windows (`CON`, `nul.txt`…), без крапки чи пробілу
    в кінці, не `.`/`..`."""
    if not isinstance(name, str) or not name or name in ('.', '..'):
        return False
    try:
        name.encode('utf-8')
    except UnicodeEncodeError:
        return False
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in name):
        return False
    if name[-1] in '. ':
        return False
    return name.split('.', 1)[0].lower() not in _WIN_RESERVED


def twin_key(name):
    """Ключ двійників: два імені однієї теки з однаковим ключем на нечутливій до регістру чи нормалізації ФС — один
    файл, і знімок розійшовся б із хешем."""
    return unicodedata.normalize('NFC', name).casefold()


def _shown(rel):
    """Шлях для тексту відмови: керівні й двонапрямні символи — `\\uXXXX`, решта як є."""
    return ''.join(c if unicodedata.category(c) not in ('Cc', 'Cf', 'Zl', 'Zp') else f'\\u{ord(c):04x}' for c in rel)


def _lstat(p, rel):
    try:
        return os.lstat(p)
    except OSError:
        raise Refused('unreadable', _shown(rel) or '.') from None


def _is_link(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & _REPARSE)


#: Для ядра (`deai_modules`: сама тека `modules/` простору): посилання — і точка повторного розбору Windows теж.
is_link = _is_link


def _walk(root):
    """`[(відносний шлях, абсолютний шлях, lstat)]` файлів теки `root` за UTF-8 байтами шляху — з усіма перевірками
    структури й меж, БЕЗ читання вмісту. Перше порушення — `Refused`."""
    st = _lstat(root, '')
    if _is_link(st):
        raise Refused('symlink', '.')
    if not stat.S_ISDIR(st.st_mode):
        raise Refused('special-file', '.')
    out = []
    total = 0

    def rec(d, rel, depth):
        nonlocal total
        try:
            names = sorted(os.listdir(d))
        except OSError:
            raise Refused('unreadable', _shown(rel) or '.') from None
        seen = {}
        for n in names:
            r = f'{rel}/{n}' if rel else n
            if not name_ok(n):
                raise Refused('bad-name', _shown(r))
            k = twin_key(n)
            if k in seen:
                raise Refused('bad-name', f'{_shown(r)} and {_shown(seen[k])} differ only by case or Unicode form')
            seen[k] = r
            p = os.path.join(d, n)
            s = _lstat(p, r)
            if _is_link(s):
                raise Refused('symlink', _shown(r))
            if stat.S_ISDIR(s.st_mode):
                if n in SKIP_DIRS:
                    continue
                if depth + 1 > MAX_DEPTH:
                    raise Refused('too-deep', _shown(r))
                rec(p, r, depth + 1)
                continue
            if not stat.S_ISREG(s.st_mode):
                raise Refused('special-file', _shown(r))
            if n in SKIP_FILES or n.endswith(SKIP_SUFFIXES):
                continue
            if s.st_nlink != 1:
                raise Refused('hardlink', _shown(r))
            out.append((r, p, s))
            total += s.st_size
            if len(out) > MAX_FILES:
                raise Refused('too-many-files', f'more than {MAX_FILES} files')
            if total > MAX_BYTES:
                raise Refused('too-big', f'more than {MAX_BYTES // (1024 * 1024)} MiB')

    rec(root, '', 0)
    out.sort(key=lambda e: e[0].encode('utf-8'))
    return out


def _read(rel, p, st):
    """Байти файла `p` (lstat `st`), прочитані РАЗ: `O_NOFOLLOW|O_NONBLOCK` (посилання чи FIFO, підкладені між `lstat` і
    `open`, не пройдуть і не підвісять потік), `fstat` того ж дескриптора — звичайний файл, `nlink == 1`, ті самі
    `dev`/`ino`; прочитано рівно `st_size` байтів. Інакше — `Refused`."""
    try:
        fd = os.open(p, _OPEN_FLAGS)
    except OSError as e:
        raise Refused('symlink' if e.errno == errno.ELOOP else 'unreadable', _shown(rel)) from None
    try:
        fs = os.fstat(fd)
        if (not stat.S_ISREG(fs.st_mode) or fs.st_nlink != 1
                or (fs.st_dev, fs.st_ino) != (st.st_dev, st.st_ino)):
            raise Refused('unstable', _shown(rel))
        chunks, n = [], 0
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                break
            n += len(b)
            if n > st.st_size:
                raise Refused('unstable', _shown(rel))
            chunks.append(b)
        if n != st.st_size:
            raise Refused('unstable', _shown(rel))
        return b''.join(chunks)
    finally:
        os.close(fd)


def tree_hash(files):
    """Хеш теки з `(шлях, розмір, sha256)` — канонічна форма зі спеки."""
    h = hashlib.sha256()
    for path, size, sha in sorted(files, key=lambda f: f[0].encode('utf-8')):
        h.update(f'{path}\0{size}\0{sha}\n'.encode('utf-8'))
    return h.hexdigest()


def _scan(root, with_data):
    files, data, total, manifest = [], ({} if with_data else None), 0, None
    for rel, p, st in _walk(root):
        raw = _read(rel, p, st)
        files.append((rel, len(raw), hashlib.sha256(raw).hexdigest()))
        total += len(raw)
        if rel == 'module.json':
            manifest = raw
        if with_data:
            data[rel] = raw
    files = tuple(files)
    return Scan(tree_hash(files), files, total, manifest, data)


def fingerprint(root):
    """Дешевий відбиток дерева `root` — лише `lstat` (тип, розмір, `mtime_ns`, `ino`, `nlink`), без читання; `None`,
    коли самого `root` нема. Не більше `FP_MAX` записів, тека не глибше `MAX_DEPTH`, за посиланнями не ходить.
    Кеш `scan` і ключі кешів ядра порівнюють саме його."""
    out = []

    def rec(d, rel, depth):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            out.append((rel, 'unreadable'))
            return
        for n in names:
            if len(out) > FP_MAX:
                return
            p = os.path.join(d, n)
            r = f'{rel}/{n}' if rel else n
            try:
                s = os.lstat(p)
            except OSError:
                out.append((r, 'gone'))
                continue
            out.append((r, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ino, s.st_nlink))
            if stat.S_ISDIR(s.st_mode) and not _is_link(s) and n not in SKIP_DIRS and depth < MAX_DEPTH:
                rec(p, r, depth + 1)

    try:
        s = os.lstat(root)
    except OSError:
        return None
    out.append(('.', s.st_mode, s.st_ino))
    if stat.S_ISDIR(s.st_mode) and not _is_link(s):
        rec(root, '', 0)
    return tuple(out)


#: Кеш `scan`: `{корінь: (відбиток, Scan | Refused)}` (без байтів файлів — `data` не кешується). Межа `CACHE_MAX`.
_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_MAX = 256


def reset_cache():
    """Скинути кеші модуля (тести; після запису довіри)."""
    with _CACHE_LOCK:
        _CACHE.clear()
        _REC_CACHE.clear()


def forget(root):
    """Прибрати з кешу `scan` одну теку (знімок щойно записано чи замінено)."""
    with _CACHE_LOCK:
        _CACHE.pop(os.path.normpath(os.path.abspath(root)), None)


def scan(root, with_data=False):
    """`Scan` теки `root` або `Refused`. Без `with_data` — з кешем за `fingerprint` (відбиток береться ДО читання: зміна
    під час сканування дасть промах наступного разу, а не застарілий хіт). `with_data=True` (довіра, знімок) — завжди
    свіже читання, з байтами."""
    root = os.path.normpath(os.path.abspath(root))
    if with_data:
        return _scan(root, True)
    fp = fingerprint(root)
    with _CACHE_LOCK:
        hit = _CACHE.get(root)
    if hit is not None and fp is not None and hit[0] == fp:
        res = hit[1]
    else:
        try:
            res = _scan(root, False)
        except Refused as e:
            res = e
        if fp is not None:
            with _CACHE_LOCK:
                _CACHE[root] = (fp, res)
                while len(_CACHE) > CACHE_MAX:
                    _CACHE.pop(next(iter(_CACHE)))
    if isinstance(res, Refused):
        raise Refused(res.code, res.detail)
    return res


def diff(files, record_files):
    """Тека проти запису довіри: `(files, removed)`. `files` — `[{path, size, change}]` у порядку `files`, `change` —
    `same`/`changed`/`new` (за sha256 файла; без запису — усі `new`); `removed` — `[{path, size}]` файлів запису, яких у
    теці нема (за UTF-8 байтами шляху)."""
    was = {}
    for f in record_files or ():
        if isinstance(f, dict) and isinstance(f.get('path'), str):
            was[f['path']] = f
    out = []
    for path, size, sha in files:
        old = was.get(path)
        out.append({'path': path, 'size': size,
                    'change': 'new' if old is None else ('same' if old.get('sha256') == sha else 'changed')})
    have = {f[0] for f in files}
    removed = [{'path': p, 'size': f['size'] if isinstance(f.get('size'), int) else 0}
               for p, f in sorted(was.items(), key=lambda kv: kv[0].encode('utf-8')) if p not in have]
    return out, removed


def tilde(p):
    """`p` з `~` замість домашньої теки — лише на межі компонента (`/Users/x2` не стає `~2`)."""
    home = os.path.expanduser('~').rstrip(os.sep)
    if home and (p == home or p.startswith(home + os.sep)):
        return '~' + p[len(home):]
    return p


_REC_CACHE = {}      # Task 2: кеш записів `trust.json`
```

- [ ] **Step 4: Прогін — зелені**

Run: `python3 "$G" 120 1500 python3 -m unittest tests.test_module_trust -v`
Expected: PASS (тести з `skip` на Windows/без FIFO — `skipped`).

- [ ] **Step 5: Мутації (кожна — один рядок, файл відновити побайтно; `python3 -B`)**

| мутація в `app/module_trust.py` | має впасти |
|---|---|
| `if s.st_nlink != 1:` → `if False:` | `test_refuses_hardlink` |
| `if _is_link(s):` (у `rec`) → `if False:` | `test_refuses_symlinked_file_dir_and_root` |
| `if n in SKIP_FILES or …: continue` → прибрати `continue` | `test_skips_finder_python_and_git_litter` |
| `if len(out) > MAX_FILES:` → `if False:` | `test_too_many_files_refused_before_reading_anything` |
| `if k in seen:` → `if False:` | `test_case_and_nfc_twins_key` не впаде (він про `twin_key`) — `test_case_twins_on_disk` (на ФС, чутливій до регістру); на macOS зафіксуй у звіті, що свідок лише на Linux |
| `hit[0] == fp` → `True` | `test_cache_skips_reading_until_the_tree_changes` |
| `if n != st.st_size:` разом із `if n > st.st_size:` → `if False:` | `test_unstable_file` |

Команда мутаційного прогону: `python3 "$G" 120 1500 python3 -B -m unittest tests.test_module_trust`.

- [ ] **Step 6: Коміт**

```bash
git add app/module_trust.py tests/test_module_trust.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): module_trust — сканер теки свого модуля, хеш, порівняння

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `module_trust` — записи довіри, знімки, системне вікно

**Files:**
- Modify: `app/module_trust.py`
- Modify: `tests/test_module_trust.py`
- Modify: `tests/test_serve.py` (`SPACE_WRITERS` ≈1945)

У `tests/test_module_trust.py` (`Base.setUp`) заміни `if hasattr(mt, 'clear_declined'): mt.clear_declined()` на
безумовний `mt.clear_declined()` (коментар «зʼявляється в Task 2» прибери): після цієї задачі перейменування мусить
падати голосно.

- [ ] **Step 1: Тести (червоні)** — допиши в `tests/test_module_trust.py` перед `if __name__`:

```python
class RecordsTest(Base):
    def rec(self, h='a' * 64, mid='netlify'):
        return {'id': mid, 'name': 'Netlify', 'version': '1', 'roles': ['publish'], 'hash': h,
                'files': [{'path': 'server.py', 'size': 1, 'sha256': 'b' * 64}], 'trusted_at': '2026-10-22T00:00:00Z'}

    def snap(self, h='a' * 64):
        os.makedirs(mt.snapshot_dir(h))

    def test_no_file_is_empty(self):
        self.assertEqual(mt.load_records(), {})

    def test_layer_off_reads_nothing(self):
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            os.environ.pop('DEAI_HOME')
            with mock.patch.object(spaces, '_read_json', side_effect=AssertionError('читав при вимкненому шарі')):
                self.assertEqual(mt.load_records(), {})
            with self.assertRaises(RuntimeError):
                mt.put_record('/k', self.rec())

    def test_put_and_load(self):
        self.snap()
        mt.put_record('/k', self.rec())
        self.assertEqual(mt.load_records()['/k']['hash'], 'a' * 64)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(mt.trust_file()).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(self.deai).st_mode), 0o700)

    def test_put_refuses_without_snapshot(self):
        with self.assertRaises(mt.SnapshotGone):
            mt.put_record('/k', self.rec())
        self.assertFalse(os.path.exists(mt.trust_file()))

    def test_unreadable_file_is_an_error_and_is_not_overwritten(self):
        os.makedirs(self.deai)
        with open(mt.trust_file(), 'w') as f:
            f.write('{not json')
        before = open(mt.trust_file(), 'rb').read()
        with self.assertRaises(mt.TrustUnreadable):
            mt.load_records()
        self.snap()
        with self.assertRaises(mt.TrustUnreadable):
            mt.put_record('/k', self.rec())
        with self.assertRaises(mt.TrustUnreadable):
            mt.drop_record('/k')
        self.assertEqual(open(mt.trust_file(), 'rb').read(), before)

    def test_drop_removes_record_and_only_unreferenced_snapshot(self):
        self.snap('a' * 64)
        mt.put_record('/k1', self.rec('a' * 64))
        mt.put_record('/k2', self.rec('a' * 64))
        self.assertTrue(mt.drop_record('/k1'))
        self.assertTrue(os.path.isdir(mt.snapshot_dir('a' * 64)), 'на знімок ще посилається /k2')
        self.assertTrue(mt.drop_record('/k2'))
        self.assertFalse(os.path.exists(mt.snapshot_dir('a' * 64)))
        self.assertFalse(mt.drop_record('/k2'))
        self.assertEqual(mt.load_records(), {})


class SnapshotTest(Base):
    def test_snapshot_holds_the_scanned_bytes_read_only(self):
        sc = mt.scan(self.mod, with_data=True)
        _put(self.mod, 'server.py', 'changed after the scan')
        d = mt.ensure_snapshot(sc)
        self.assertEqual(d, mt.snapshot_dir(sc.hash))
        self.assertEqual(open(os.path.join(d, 'server.py'), 'rb').read(), sc.data['server.py'])
        self.assertTrue(mt.verify_snapshot(sc.hash))
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o500)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, 'server.py')).st_mode), 0o400)

    def test_intact_snapshot_is_kept(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        ino = os.stat(d).st_ino
        mt.ensure_snapshot(mt.scan(self.mod, with_data=True))
        self.assertEqual(os.stat(d).st_ino, ino)

    def test_damaged_snapshot_is_detected_and_repaired(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        os.chmod(d, 0o700)
        p = os.path.join(d, 'server.py')
        os.chmod(p, 0o600)
        with open(p, 'w') as f:
            f.write('tampered')
        mt.forget(d)
        self.assertFalse(mt.verify_snapshot(sc.hash))
        mt.ensure_snapshot(sc)
        self.assertTrue(mt.verify_snapshot(sc.hash))
        self.assertEqual(open(os.path.join(mt.snapshot_dir(sc.hash), 'server.py'), 'rb').read(), sc.data['server.py'])

    def test_requires_bytes(self):
        with self.assertRaises(ValueError):
            mt.ensure_snapshot(mt.scan(self.mod))

    def test_sweep_removes_only_old_leftovers(self):
        root = mt.trusted_root()
        old, fresh = os.path.join(root, '.tmp-old'), os.path.join(root, '.old-fresh')
        for d in (old, fresh):
            os.makedirs(os.path.join(d, 'x'))
        past = time.time() - mt.STALE_S - 10
        os.utime(old, (past, past))
        mt.sweep()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))


class ConfirmTest(Base):
    TEXTS = ('Deai Canvas', 'Trust «x"; do shell script "touch /tmp/pwn" --»?', 'Довіряю', 'Скасувати')

    def test_darwin_text_goes_as_arguments_not_into_the_script(self):
        argv, extra = mt.confirm_command('darwin', *self.TEXTS)
        self.assertEqual(argv[:2], ['osascript', '-e'])
        self.assertNotIn('pwn', argv[2])
        self.assertEqual(argv[3:], [self.TEXTS[1], self.TEXTS[0], self.TEXTS[2], self.TEXTS[3]])
        self.assertEqual(extra, {})

    def test_windows_text_goes_through_the_environment(self):
        argv, extra = mt.confirm_command('win32', *self.TEXTS)
        self.assertEqual(argv[0], 'powershell')
        self.assertNotIn('pwn', ' '.join(argv))
        self.assertEqual(extra['DEAI_CONFIRM_MSG'], self.TEXTS[1])

    def test_linux_needs_a_display_and_a_tool(self):
        self.assertIsNone(mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/' + n, env={}))
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/zenity' if n == 'zenity' else None,
                                     env={'DISPLAY': ':0'})
        self.assertEqual(argv[0], 'zenity')
        self.assertIn(self.TEXTS[1], argv)
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/kdialog' if n == 'kdialog' else None,
                                     env={'WAYLAND_DISPLAY': 'w'})
        self.assertEqual(argv[0], 'kdialog')
        self.assertIsNone(mt.confirm_command('linux', *self.TEXTS, which=lambda n: None, env={'DISPLAY': ':0'}))

    def test_interpret(self):
        P = lambda rc, out='': mock.Mock(returncode=rc, stdout=out)  # noqa: E731
        self.assertEqual(mt._interpret('osascript', P(0, 'yes\n')), 'yes')
        self.assertEqual(mt._interpret('osascript', P(0, 'no\n')), 'no')
        self.assertEqual(mt._interpret('osascript', P(1, '')), 'unavailable')
        self.assertEqual(mt._interpret('zenity', P(0)), 'yes')
        self.assertEqual(mt._interpret('zenity', P(5)), 'no')
        self.assertEqual(mt._interpret('zenity', P(255)), 'unavailable')

    def test_texts_are_cleaned_and_clipped(self):
        title, msg, yes, no = mt.confirm_texts('uk', 'N‮a\ud800me' + 'x' * 200, 'netlify', 'f' * 64, '/p\x07ath')
        self.assertNotIn('‮', msg)
        self.assertNotIn('\ud800', msg)
        msg.encode('utf-8')                                     # пройде в argv
        self.assertNotIn('\x07', msg)
        self.assertIn('ffffffffffff', msg)
        self.assertNotIn('f' * 13, msg)
        self.assertEqual(set(mt.CONFIRM_TEXT), {'uk', 'en'})
        self.assertEqual(mt.confirm_texts('zz', 'n', 'i', 'f' * 64, '/p'), mt.confirm_texts('uk', 'n', 'i', 'f' * 64, '/p'))

    def test_seam_needs_a_non_default_deai_home(self):
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes'}):
            self.assertEqual(mt.seam_value(), 'yes')
            with mock.patch.object(mt, '_real_default_home', lambda: os.path.realpath(self.deai)):
                self.assertIsNone(mt.seam_value())
            os.environ.pop('DEAI_HOME')
            self.assertIsNone(mt.seam_value())
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'maybe'}):
            self.assertIsNone(mt.seam_value())

    def test_confirm_uses_the_seam_and_never_a_window(self):
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'no'}), \
                mock.patch.object(mt.subprocess, 'run', side_effect=AssertionError('вікно в тесті')):
            self.assertEqual(mt.confirm(*self.TEXTS), 'no')

    def test_confirm_runs_the_command_and_maps_failures(self):
        os.environ.pop(mt.SEAM_ENV, None)
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript', '-e', 's'], {})), \
                mock.patch.object(mt.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='yes')):
            self.assertEqual(mt.confirm(*self.TEXTS), 'yes')
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript'], {})), \
                mock.patch.object(mt.subprocess, 'run', side_effect=mt.subprocess.TimeoutExpired('osascript', 1)):
            self.assertEqual(mt.confirm(*self.TEXTS), 'no')
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript'], {})), \
                mock.patch.object(mt.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(mt.confirm(*self.TEXTS), 'unavailable')
        with mock.patch.object(mt, 'confirm_command', return_value=None):
            self.assertEqual(mt.confirm(*self.TEXTS), 'unavailable')

    def test_ask_one_window_at_a_time(self):
        gate, inside = threading.Event(), threading.Event()

        def slow(*a):
            inside.set()
            gate.wait(5)
            return 'yes'
        with mock.patch.object(mt, 'confirm', slow):
            box = []
            th = threading.Thread(target=lambda: box.append(mt.ask('/k', 'h', self.TEXTS)))
            th.start()
            inside.wait(5)
            self.assertEqual(mt.ask('/k2', 'h2', self.TEXTS), 'busy')
            gate.set()
            th.join(5)
        self.assertEqual(box, ['yes'])

    def test_ask_cools_down_after_a_decline(self):
        clock = [100.0]
        with mock.patch.object(mt, 'confirm', return_value='no') as c:
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0]), 'no')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0] + 5), 'declined')
            self.assertEqual(c.call_count, 1)
            self.assertEqual(mt.ask('/k', 'other', self.TEXTS, now=lambda: clock[0] + 5), 'no')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0] + mt.DECLINE_COOLDOWN + 1), 'no')
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 120 1500 python3 -m unittest tests.test_module_trust -v`
Expected: FAIL — `AttributeError: module 'module_trust' has no attribute 'snapshot_dir'` тощо.

- [ ] **Step 3: Реалізація** — допиши в `app/module_trust.py` (імпорти — до верхнього блоку імпортів: `json` не потрібен; додай `re`, `secrets`, `shutil`, `subprocess`, `sys`, `tempfile`, `time`; `from atomic_io import WRITE_LOCK, atomic_write_json`). Заміни рядок-заглушку `_REC_CACHE = {}` в кінці на цей блок:

```python
# ------------------------------------------------------------------------------------- записи довіри

HASH_RE = re.compile(r'[0-9a-f]{64}')
#: Залишки `.tmp-*`/`.old-*` у `trusted/`, старші за стільки секунд, прибирає `sweep`.
STALE_S = 3600

#: Кеш `load_records`: `{'v': (відбиток файла, записи)}`.
_REC_CACHE = {}


class TrustUnreadable(Exception):
    """`trust.json` є, але не читається чи не тієї форми: довіра НЕ вважається порожньою, і файл не переписується
    (інакше мовчки зникли б інші довіри)."""


class SnapshotGone(Exception):
    """Знімка, на який мав би вказати запис, уже нема (паралельне «Забрати довіру» відсунуло його)."""


def trust_file():
    return os.path.join(spaces.home(), 'trust.json')


def trusted_root():
    return os.path.join(spaces.home(), 'trusted')


def snapshot_dir(h):
    return os.path.join(trusted_root(), h)


def key_for(space_path, mid):
    """Ключ запису довіри — `realpath(<простір>/modules/<id>)`; рахується й для теки, якої вже нема."""
    return os.path.realpath(os.path.join(space_path, 'modules', mid))


def _secure(path, mode):
    if os.name != 'nt':
        os.chmod(path, mode)


def _sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def records_sig():
    """Відбиток `trust.json` для ключів кешів ядра; шар вимкнено — `None`."""
    return _sig(trust_file()) if spaces.layer_on() else None


def _valid_record(r):
    return (isinstance(r, dict) and isinstance(r.get('id'), str) and isinstance(r.get('hash'), str)
            and bool(HASH_RE.fullmatch(r['hash'])) and isinstance(r.get('files'), list))


def _read_file():
    """Вміст `trust.json` як `{'version': 1, 'modules': {…}}`; файла нема — порожній; не читається чи не та форма —
    `TrustUnreadable`."""
    try:
        data = spaces._read_json(trust_file())
    except FileNotFoundError:
        return {'version': 1, 'modules': {}}
    except (OSError, ValueError):
        raise TrustUnreadable('trust.json is unreadable') from None
    if not isinstance(data, dict) or not isinstance(data.get('modules', {}), dict):
        raise TrustUnreadable('trust.json: "modules" is not an object')
    data = dict(data)
    data['modules'] = dict(data.get('modules', {}))
    data.setdefault('version', 1)
    return data


def load_records():
    """`{ключ: запис}` з `trust.json` (лише записи правильної форми). Файла нема чи шар просторів вимкнено — `{}` без
    звернення до диска; не читається — `TrustUnreadable`. Кеш за відбитком файла; віддає новий словник."""
    if not spaces.layer_on():
        return {}
    sig = _sig(trust_file())
    with _CACHE_LOCK:
        hit = _REC_CACHE.get('v')
    if hit is not None and sig is not None and hit[0] == sig:
        return dict(hit[1])
    recs = {k: v for k, v in _read_file()['modules'].items() if isinstance(k, str) and _valid_record(v)}
    if sig is not None:
        with _CACHE_LOCK:
            _REC_CACHE['v'] = (sig, recs)
    return dict(recs)


def _require_layer():
    if not spaces.layer_on():
        raise RuntimeError('spaces layer is off: trust is not written')


def _write_file(data):
    home, path = spaces.home(), trust_file()
    os.makedirs(home, mode=0o700, exist_ok=True)
    _secure(home, 0o700)
    if os.path.exists(path):
        _secure(path, 0o600)                         # ДО запису: атомарна заміна переносить режим цілі
    atomic_write_json(path, data)
    _secure(path, 0o600)
    with _CACHE_LOCK:
        _REC_CACHE.clear()


def put_record(key, rec):
    """Записати довіру `rec` під ключем `key`: під `WRITE_LOCK` лише читання-зміна-запис файла (атомарно, 0600). Знімок
    `rec['hash']` мусить існувати — перевірка під тим самим локом, інакше `SnapshotGone`. ⚠️ Знімок пишуть ДО
    (`ensure_snapshot`), кеші ядра скидають ПІСЛЯ — і те, і те поза локом."""
    _require_layer()
    with WRITE_LOCK:
        data = _read_file()
        if not _real_dir(snapshot_dir(rec['hash'])):
            raise SnapshotGone(rec['hash'])
        data['modules'][key] = rec
        _write_file(data)


def drop_record(key):
    """Прибрати довіру `key`; `True`, якщо запис був. Знімок, на який більше не посилається жоден запис, відсувається в
    `.old-*` ПІД тим самим локом (паралельна довіра того ж хешу побачить його відсутність і відмовить), видаляється —
    після локу."""
    _require_layer()
    aside = None
    with WRITE_LOCK:
        data = _read_file()
        rec = data['modules'].pop(key, None)
        if rec is None:
            return False
        h = rec.get('hash') if isinstance(rec, dict) else None
        still = any(isinstance(r, dict) and r.get('hash') == h for r in data['modules'].values())
        if isinstance(h, str) and HASH_RE.fullmatch(h) and not still and _real_dir(snapshot_dir(h)):
            aside = _aside(snapshot_dir(h))
        _write_file(data)
    if aside:
        _rmtree(aside)
    sweep()
    return True


# ------------------------------------------------------------------------------------------- знімки

def _real_dir(p):
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and not _is_link(st)


def _aside(d):
    """Атомарно перейменувати теку `d` в `.old-<випадкове>` поруч; новий шлях."""
    dst = os.path.join(os.path.dirname(d), f'.old-{secrets.token_hex(8)}')
    os.rename(d, dst)
    forget(d)
    return dst


def _rmtree(p):
    """Видалити теку знімка: спершу повернути теки на запис (знімок — 0500/0400)."""
    for dp, _dns, _fns in os.walk(p):
        try:
            _secure(dp, 0o700)
        except OSError:
            pass
    shutil.rmtree(p, ignore_errors=True)


def sweep(now=None):
    """Прибрати в `trusted/` теки `.tmp-*`/`.old-*`, старші за `STALE_S` (залишки обірваних записів і видалень)."""
    root = trusted_root()
    now = time.time() if now is None else now
    try:
        names = os.listdir(root)
    except OSError:
        return
    for n in names:
        if not (n.startswith('.tmp-') or n.startswith('.old-')):
            continue
        p = os.path.join(root, n)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if now - st.st_mtime > STALE_S and stat.S_ISDIR(st.st_mode) and not _is_link(st):
            _rmtree(p)


def verify_snapshot(h):
    """Знімок `h` цілий: справжня тека `trusted/<h>` і її хеш (сканер з кешем відбитка) дорівнює `h`."""
    if not (isinstance(h, str) and HASH_RE.fullmatch(h)):
        return False
    d = snapshot_dir(h)
    if not _real_dir(d):
        return False
    try:
        return scan(d).hash == h
    except Refused:
        return False


def ensure_snapshot(sc):
    """Знімок рівно байтів `sc` (з `scan(…, with_data=True)`) у `trusted/<sc.hash>/`: файли 0400, теки 0500. Цілий знімок
    із цим хешем лишається; пошкоджений — відсувається й пишеться наново. Пишеться в `.tmp-*` і перейменовується (та
    сама тека-батько — атомарно). Повертає теку знімка."""
    if sc.data is None:
        raise ValueError('ensure_snapshot: scan(…, with_data=True) is required')
    _require_layer()
    sweep()
    root = trusted_root()
    os.makedirs(root, mode=0o700, exist_ok=True)
    _secure(spaces.home(), 0o700)
    _secure(root, 0o700)
    final = snapshot_dir(sc.hash)
    if _real_dir(final):
        if verify_snapshot(sc.hash):
            return final
        _rmtree(_aside(final))
    elif os.path.lexists(final):
        os.unlink(final)                              # посилання чи файл на місці знімка
    tmp = tempfile.mkdtemp(prefix='.tmp-', dir=root)
    try:
        for rel, raw in sc.data.items():
            p = os.path.join(tmp, *rel.split('/'))
            os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                         | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
        for dp, _dns, fns in os.walk(tmp, topdown=False):
            for n in fns:
                _secure(os.path.join(dp, n), 0o400)
            _secure(dp, 0o500)
        try:
            os.rename(tmp, final)
        except OSError:
            if not verify_snapshot(sc.hash):          # паралельний запис того ж хешу встиг першим — тоді ок
                raise
            _rmtree(tmp)
        tmp = None
    finally:
        if tmp:
            _rmtree(tmp)
    forget(final)
    return final


# ------------------------------------------------------------------------------------ системне вікно

CONFIRM_TIMEOUT = 120
DECLINE_COOLDOWN = 30
SEAM_ENV = 'DEAI_TRUST_CONFIRM'

#: Тексти рідного вікна. Мова — з `lang` запиту довіри; невідома — `uk`.
CONFIRM_TEXT = {
    'uk': {'title': 'Deai Canvas', 'yes': 'Довіряю', 'no': 'Скасувати',
           'ask': 'Довіритись модулю «{name}» ({id}, відбиток {hash})?\n\n'
                  'Його код виконуватиметься на цьому компʼютері з вашими правами.\n\nТека: {path}'},
    'en': {'title': 'Deai Canvas', 'yes': 'Trust', 'no': 'Cancel',
           'ask': 'Trust the module “{name}” ({id}, fingerprint {hash})?\n\n'
                  'Its code will run on this computer with your permissions.\n\nFolder: {path}'},
}

_OSA = '''on run argv
  set msg to item 1 of argv
  set ttl to item 2 of argv
  set yesB to item 3 of argv
  set noB to item 4 of argv
  tell me to activate
  try
    set r to display dialog msg with title ttl buttons {noB, yesB} default button noB cancel button noB with icon caution giving up after 120
  on error number -128
    return "no"
  end try
  if gave up of r then return "no"
  if button returned of r is yesB then return "yes"
  return "no"
end run'''

_PS = ("Add-Type -AssemblyName System.Windows.Forms; "
       "$r = [System.Windows.Forms.MessageBox]::Show($env:DEAI_CONFIRM_MSG, $env:DEAI_CONFIRM_TITLE, 'YesNo', 'Warning', 'Button2'); "
       "if ($r -eq 'Yes') { 'yes' } else { 'no' }")


def _clean(s, n=80):
    """Рядок для системного вікна: без `Cc`/`Cf`/`Cs`/`Zl`/`Zp`, не довший за `n` (з «…»). `Cs` — самотній сурогат
    (`"\\ud800"` з `module.json`): у `argv` підпроцесу він дав би `UnicodeEncodeError` замість вікна."""
    s = ''.join(c for c in str(s) if unicodedata.category(c) not in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp'))
    return s if len(s) <= n else s[:n - 1] + '…'


def confirm_texts(lang, name, mid, h, path):
    """`(заголовок, текст, «так», «ні»)` вікна довіри мовою `lang` (`uk`/`en`, інакше `uk`)."""
    tx = CONFIRM_TEXT.get(lang) or CONFIRM_TEXT['uk']
    msg = tx['ask'].format(name=_clean(name), id=_clean(mid), hash=str(h)[:12], path=_clean(path))
    return tx['title'], msg, tx['yes'], tx['no']


def confirm_command(platform, title, msg, yes, no, which=shutil.which, env=None):
    """`(argv, додаткове оточення)` рідного вікна для `platform` (`sys.platform`) або `None` — нема чим показати. Текст
    іде АРГУМЕНТОМ (macOS, Linux) чи ЗМІННОЮ ОТОЧЕННЯ (Windows) — ніколи не підставляється в код скрипта."""
    env = os.environ if env is None else env
    if platform == 'darwin':
        return ['osascript', '-e', _OSA, msg, title, yes, no], {}
    if platform.startswith('win'):
        return (['powershell', '-NoProfile', '-NonInteractive', '-Command', _PS],
                {'DEAI_CONFIRM_MSG': msg, 'DEAI_CONFIRM_TITLE': title})
    if not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        return None
    if which('zenity'):
        return ['zenity', '--question', '--no-markup', '--title', title, '--text', msg,
                '--ok-label', yes, '--cancel-label', no, f'--timeout={CONFIRM_TIMEOUT}'], {}
    if which('kdialog'):
        return ['kdialog', '--title', title, '--yes-label', yes, '--no-label', no, '--warningyesno', msg], {}
    return None


def _interpret(argv0, proc):
    """Відповідь вікна з завершеного процесу: `yes`/`no`/`unavailable`."""
    if argv0 in ('osascript', 'powershell'):
        if proc.returncode != 0:
            return 'unavailable'
        return 'yes' if (proc.stdout or '').strip().lower() == 'yes' else 'no'
    if proc.returncode == 0:
        return 'yes'
    if proc.returncode in (1, 5):                     # zenity: 1 — «ні», 5 — тайм-аут; kdialog: 1 — «ні»
        return 'no'
    return 'unavailable'


def _real_default_home():
    """Справжній типовий `~/.deai` — з бази користувачів (POSIX), а не з `$HOME`, який тест чи оточення могли підмінити."""
    try:
        import pwd
        base = pwd.getpwuid(os.getuid()).pw_dir
    except (ImportError, KeyError):
        base = os.path.expanduser('~')
    return os.path.realpath(os.path.join(base, '.deai'))


def seam_value(env=None):
    """Тестовий шов `DEAI_TRUST_CONFIRM` (`yes`/`no`/`unavailable`) або `None`. Діє ЛИШЕ коли `DEAI_HOME` задано й це не
    справжній типовий `~/.deai`: на робочій машині змінна, що випадково лишилась, нічого не робить."""
    env = os.environ if env is None else env
    v = env.get(SEAM_ENV)
    home = env.get('DEAI_HOME')
    if v not in ('yes', 'no', 'unavailable') or not home:
        return None
    if os.path.realpath(os.path.expanduser(home)) == _real_default_home():
        return None
    return v


def confirm(title, msg, yes, no):
    """Рідне вікно ОС → `'yes'`/`'no'`/`'unavailable'`. Блокує потік до відповіді; тайм-аут — `'no'`."""
    seam = seam_value()
    if seam is not None:
        return seam
    cmd = confirm_command(sys.platform, title, msg, yes, no)
    if cmd is None:
        return 'unavailable'
    argv, extra = cmd
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CONFIRM_TIMEOUT + 10,
                              env={**os.environ, **extra}, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 'no'
    except OSError:
        return 'unavailable'
    return _interpret(argv[0], proc)


_ASK_LOCK = threading.Lock()
_DECLINED = {}


def clear_declined():
    """Забути відмови (тести)."""
    _DECLINED.clear()


def ask(key, h, texts, now=time.monotonic):
    """Системне підтвердження довіри `(key, h)`: `'yes'`/`'no'`/`'unavailable'`, `'busy'` (уже відкрите інше вікно) чи
    `'declined'` (той самий `(key, h)` відхилено менш як `DECLINE_COOLDOWN` с тому — вікна не показуємо). Поза локами
    ядра: блокує лише свій потік."""
    t = _DECLINED.get((key, h))
    if t is not None and now() - t < DECLINE_COOLDOWN:
        return 'declined'
    if not _ASK_LOCK.acquire(blocking=False):
        return 'busy'
    try:
        r = confirm(*texts)
    finally:
        _ASK_LOCK.release()
    if r == 'no':
        _DECLINED[(key, h)] = now()
    return r
```

У `tests/test_serve.py` (`SPACE_WRITERS` ≈1945) додай `'put_record(', 'drop_record(', 'ensure_snapshot(', 'grant_trust(', 'revoke_trust('` — тести, що їх кличуть, мусять ізолювати `DEAI_HOME`.

- [ ] **Step 4: Прогін — зелені**

Run: `python3 "$G" 180 1500 python3 -m unittest tests.test_module_trust tests.test_serve -v 2>&1 | tail -15`
Expected: PASS.

- [ ] **Step 5: Мутації**

| мутація | має впасти |
|---|---|
| у `put_record` прибрати перевірку `_real_dir(snapshot_dir(…))` | `test_put_refuses_without_snapshot` |
| у `drop_record` `not still` → `True` | `test_drop_removes_record_and_only_unreferenced_snapshot` |
| у `load_records` `except (OSError, ValueError)` гілку `_read_file` → `return {'version': 1, 'modules': {}}` | `test_unreadable_file_is_an_error_and_is_not_overwritten` |
| у `ensure_snapshot` `if verify_snapshot(sc.hash): return final` → `return final` (без перевірки) | `test_damaged_snapshot_is_detected_and_repaired` |
| у `seam_value` прибрати порівняння з `_real_default_home()` | `test_seam_needs_a_non_default_deai_home` |
| у `ask` прибрати `_DECLINED[(key, h)] = now()` | `test_ask_cools_down_after_a_decline` |
| у `confirm_command` для `darwin` вставити `msg` у скрипт (`_OSA.replace('item 1 of argv', '"' + msg + '"')`) | `test_darwin_text_goes_as_arguments_not_into_the_script` |

- [ ] **Step 6: Коміт**

```bash
git add app/module_trust.py tests/test_module_trust.py tests/test_serve.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): module_trust — записи довіри, знімки, системне вікно ОС

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `deai_modules` — каталог простору зі своїми модулями

**Files:**
- Modify: `app/deai_modules.py` (константи ≈85–127, `ModuleError` ≈129, `Module` ≈145, `reset_caches` ≈206, `catalog` ≈523, `effective_state` ≈628, `_need_module` ≈706, `validate_settings` ≈713, `preflight` ≈759, `write_module_state` ≈811, `write_secrets` ≈1068, `module_ctx` ≈1237, `check` ≈1260, `published_root` ≈885)
- Create: `tests/test_modules_own.py`

- [ ] **Step 1: Тести (червоні)** — створи `tests/test_modules_own.py`:

```python
"""Свої модулі простору в каталозі ядра (етап 3c, Task 3–4): `catalog(space)`, недовірений код не виконується,
довірений — зі знімка, примітки, тайм-аут завантаження; ролі «на папері», постачальник без запасного шляху, довіра в
ядрі (`trust_view`, `grant_trust`, `revoke_trust`). Спека `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`.

Оточення — `Env` з `test_modules` (тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`, тека вбудованих — тимчасова). Системне
вікно НІКОЛИ не показується: шов `DEAI_TRUST_CONFIRM` (діє з тимчасовим `DEAI_HOME`) чи підмінений `module_trust.ask`.
Мітка-файл `DEAI_OWN_CANARY`: `server.py` фікстури дописує в неї свій `__file__` при КОЖНОМУ виконанні верхнього рівня.
"""
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402
import module_trust as mt  # noqa: E402
from test_modules import Env, _write, _read, ALL_FNS  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


OWN_SERVER = '''import os
VERSION = "v1"
_p = os.environ.get("DEAI_OWN_CANARY")
if _p:
    with open(_p, "a") as _f:
        _f.write(__file__ + "\\n")


def check(ctx):
    return {"ok": True, "detail": "own " + VERSION}


def publish(ctx, build_dir, task):
    return {"folder": build_dir}


def tokens(ctx):
    return {"tokens": {}, "source": "own"}


def client_config(ctx):
    return {}


def list(ctx, channel):
    return []


def resolve(ctx, channel, pin_id, resolved):
    return {"ok": True}
'''


def _unlock(tree):
    """Знімки довіри — 0500/0400, а тести ставлять ще й chmod 0: `rmtree(…, ignore_errors=True)` мовчки лишив би такі
    теки на диску. Повертає право запису ТЕКАМ (файлам не треба: видалення — право теки, що їх містить)."""
    for root, dirs, _files in os.walk(tree):
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), 0o700)
            except OSError:
                pass


class OwnEnv(Env):
    def setUp(self):
        super().setUp()
        # Власне присвоєння, хоч `Env` уже поставив те саме: охоронець `test_serve` (`SPACE_WRITERS` →
        # `_assigns_deai_home`) розбирає джерело САМЕ цього файла — присвоєння в імпортованому `Env` він не бачить
        os.environ['DEAI_HOME'] = self.deai
        self.canary = os.path.join(self.tmp, 'canary.log')
        os.environ['DEAI_OWN_CANARY'] = self.canary
        self.addCleanup(os.environ.pop, 'DEAI_OWN_CANARY', None)
        os.environ.pop(mt.SEAM_ENV, None)
        self.addCleanup(os.environ.pop, mt.SEAM_ENV, None)
        # Сітка: справжнє системне вікно в тесті недосяжне. Шов `DEAI_TRUST_CONFIRM` відповідає в `confirm` РАНІШЕ за
        # `confirm_command`, тож тестам зі швом чи підміненим `ask` вона не заважає, а `subprocess` решти коду не чіпає
        net = mock.patch.object(mt, 'confirm_command', side_effect=AssertionError('системне вікно в тесті'))
        net.start()
        self.addCleanup(net.stop)
        mt.clear_declined()
        self.sp = self.new_space()

    def tearDown(self):
        _unlock(self.tmp)                  # до `Env.tearDown`: той робить `rmtree(…, ignore_errors=True)`
        super().tearDown()

    def own(self, mid='acme', roles=('publish',), sp=None, server=OWN_SERVER, settings=None, extra=None):
        d = os.path.join((sp or self.sp)['path'], 'modules', mid)
        man = {'api': 1, 'id': mid, 'name': mid.title(), 'version': '1.0.0', 'roles': list(roles),
               'settings': settings or [{'key': 'token', 'type': 'secret', 'label': 'Token'}]}
        man.update(extra or {})
        _write(os.path.join(d, 'module.json'), man)
        _write(os.path.join(d, 'server.py'), server)
        return d

    def trust(self, mid='acme', sp=None):
        """Довіра в обхід ядра (Task 3 ще не має `grant_trust`): знімок + запис."""
        sp = sp or self.sp
        sc = mt.scan(os.path.join(sp['path'], 'modules', mid), with_data=True)
        mt.ensure_snapshot(sc)
        mt.put_record(mt.key_for(sp['path'], mid), {
            'id': mid, 'name': mid, 'version': '1', 'roles': ['publish'], 'hash': sc.hash,
            'files': [{'path': p, 'size': n, 'sha256': h} for p, n, h in sc.files], 'trusted_at': 'x'})
        return sc.hash

    def ran(self):
        try:
            with open(self.canary) as f:
                return [ln for ln in f.read().splitlines() if ln]
        except FileNotFoundError:
            return []

    def enable_raw(self, mid='acme', roles=('publish',), sp=None):
        """Як колега, що закомітив `space.json`: запис увімкненого свого модуля без жодної довіри тут."""
        p = self.space_json(sp or self.sp)
        data = _read(p)
        data.setdefault('modules', {})[mid] = {'enabled': True, 'settings': {}, 'roles': list(roles)}
        _write(p, data)


class CatalogTest(OwnEnv):
    def test_catalog_without_space_is_builtin_only(self):
        self.mk('pub')
        self.own()
        self.assertEqual(sorted(dm.catalog()), ['pub'])
        self.assertEqual(sorted(dm.catalog(self.sp)), ['acme', 'pub'])

    def test_untrusted_is_listed_from_its_manifest_and_never_runs(self):
        self.own(settings=[{'key': 'site', 'type': 'text', 'label': 'Site'}])
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.origin, m.trust, m.record, m.status, m.error_code),
                         ('space', 'untrusted', False, 'untrusted', 'module-untrusted'))
        self.assertEqual((m.name, m.roles, [s['key'] for s in m.settings]), ('Acme', ['publish'], ['site']))
        self.assertEqual(m.source, os.path.join('~', 'work', 'alpha', 'modules', 'acme'))
        dm.effective_state(self.sp)
        dm.capabilities(self.sp)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'acme')
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-untrusted', 409))
        for call in (lambda: dm.preflight(self.sp, 'acme', enabling=True),
                     lambda: dm.preflight(self.sp, 'acme', enabling=True, replace=True),
                     lambda: dm.write_module_state(self.sp, 'acme', enabled=True)):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'module-untrusted')
        self.assertEqual(self.ran(), [], 'код недовіреного модуля виконано')
        self.assertNotIn('acme', dm.space_modules(self.sp))

    def test_settings_secrets_and_disable_of_untrusted_are_allowed(self):
        self.own()
        dm.validate_settings('acme', {}, self.sp)
        dm.write_secrets(self.sp['id'], 'acme', {'token': 's3'}, space=self.sp)
        dm.write_module_state(self.sp, 'acme', enabled=False)
        self.assertEqual(self.ran(), [])

    def test_trusted_runs_from_the_snapshot(self):
        self.own()
        h = self.trust()
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.record), ('ok', 'trusted', True))
        self.assertEqual(m.dir, mt.snapshot_dir(h))
        self.assertEqual(dm.check(self.sp, 'acme'), {'ok': True, 'detail': 'own v1'})
        self.assertTrue(self.ran())
        self.assertTrue(all(p.startswith(mt.trusted_root()) for p in self.ran()), self.ran())

    def test_changed_folder_keeps_running_the_trusted_snapshot(self):
        d = self.own()
        self.trust()
        _write(os.path.join(d, 'server.py'), OWN_SERVER.replace('"v1"', '"v2"'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.trust, m.status), ('changed', 'ok'))
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v1')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_refused_folder(self):
        d = self.own()
        os.symlink(os.path.join(d, 'server.py'), os.path.join(d, 'alias.py'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.error_code), ('error', 'refused', 'symlink', 'module-untrusted'))
        self.assertIn('alias.py', m.error)
        os.remove(os.path.join(d, 'alias.py'))
        self.trust()
        os.symlink(os.path.join(d, 'server.py'), os.path.join(d, 'alias.py'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.record), ('ok', 'refused', True), 'знімок працює, нова версія — ні')

    def test_damaged_snapshot_is_untrusted_with_a_record(self):
        self.own()
        h = self.trust()
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        _write(os.path.join(snap, 'server.py'), 'raise SystemExit')
        mt.forget(snap)
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.record), ('untrusted', 'untrusted', 'snapshot-damaged', True))
        self.assertEqual(self.ran(), [])

    def test_unreadable_trust_file_means_untrusted(self):
        self.own()
        self.trust()
        _write(mt.trust_file(), '{oops')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust_error), ('untrusted', 'trust-unreadable'))

    def test_notes_and_ignored_folders(self):
        self.mk('pub')
        self.own('pub')                                     # id вбудованого
        os.makedirs(os.path.join(self.sp['path'], 'modules', '_drafts'))
        os.makedirs(os.path.join(self.sp['path'], 'modules', 'nomanifest'))
        _write(os.path.join(self.sp['path'], 'modules', 'README'), 'x')
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules/pub', 'code': 'id-taken'}])
        self.assertNotIn('nomanifest', dm.catalog(self.sp))
        self.assertIs(dm.catalog(self.sp)['pub'].origin, 'builtin')

    def test_too_many_modules(self):
        for i in range(dm.MAX_OWN_MODULES + 1):
            self.own(f'm{i:02}')
        cat = dm.catalog(self.sp)
        self.assertEqual(sum(1 for m in cat.values() if m.origin == 'space'), dm.MAX_OWN_MODULES)
        self.assertEqual(dm.own_notes(self.sp), [{'folder': f'modules/m{dm.MAX_OWN_MODULES:02}', 'code': 'too-many-modules'}])

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_modules_link_and_unreadable(self):
        real = os.path.join(self.tmp, 'elsewhere')
        os.makedirs(real)
        os.symlink(real, os.path.join(self.sp['path'], 'modules'))
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-link'}])
        os.remove(os.path.join(self.sp['path'], 'modules'))
        self.own()
        base = os.path.join(self.sp['path'], 'modules')
        os.chmod(base, 0)
        self.addCleanup(os.chmod, base, 0o755)
        if os.access(base, os.R_OK):
            self.skipTest('root читає все')
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-unreadable'}])

    def test_two_spaces_with_the_same_bytes_do_not_share_module_objects(self):
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        self.own()
        self.own(sp=sp2)
        self.trust()
        self.trust(sp=sp2)
        a, b = dm.catalog(self.sp)['acme'], dm.catalog(sp2)['acme']
        self.assertEqual(a.dir, b.dir, 'одна тека знімка')
        self.assertIsNot(a, b)
        self.assertNotEqual(a.source, b.source)

    def test_load_timeout(self):
        self.own(server='import time\ntime.sleep(10)\n' + OWN_SERVER)
        self.trust()
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.3):
            t0 = time.monotonic()
            m = dm.catalog(self.sp)['acme']
            self.assertLess(time.monotonic() - t0, 3)
            self.assertEqual((m.status, m.error_code), ('error', 'module-error'))
            self.assertIn('timed out', m.error)
            t0 = time.monotonic()
            dm.catalog(self.sp)
            self.assertLess(time.monotonic() - t0, 1, 'результат тайм-ауту не закешовано')

    def test_enabling_a_trusted_own_module_writes_its_roles(self):
        self.own()
        self.trust()
        dm.write_module_state(self.sp, 'acme', enabled=True, replace=True)
        self.assertEqual(_read(self.space_json(self.sp))['modules']['acme']['roles'], ['publish'])

    def test_builtin_cache_eviction_does_not_drop_snapshots(self):
        self.mk('pub')
        self.own()
        self.trust()
        dm.catalog(self.sp)
        n = len(self.ran())
        dm.catalog()
        dm.catalog(self.sp)
        self.assertEqual(len(self.ran()), n, 'знімок виконано вдруге без змін')
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 180 1500 python3 -m unittest tests.test_modules_own -v 2>&1 | tail -20`
Expected: FAIL (`catalog() takes 0 positional arguments`, `own_notes` нема тощо).

- [ ] **Step 3: Реалізація в `app/deai_modules.py`**

3a. Імпорти — додай `from collections import OrderedDict` і після `import spaces` — `import module_trust`.

3b. Після словника `STATUS` (≈127):

```python
#: Коди ЯДРА для своїх модулів і довіри (етап 3c). Окремо від `STATUS`: `_run` пропускає як є лише коди `STATUS`, тож
#: модуль не кине «module-untrusted» від свого імені.
CORE_STATUS = {'module-untrusted': 409, 'module-changed': 409, 'module-refused': 409, 'trust-needs-ui': 403,
               'trust-declined': 409, 'trust-no-confirm': 409, 'trust-busy': 409, 'trust-unreadable': 409}
#: Своїх модулів у просторі — не більше (за абеткою); решта — примітки `too-many-modules`.
MAX_OWN_MODULES = 32
#: Скільки секунд чекати верхнього рівня `server.py` знімка свого модуля.
LOAD_TIMEOUT = 5
#: Скільки знімків тримає кеш завантаження своїх модулів.
OWN_CACHE_MAX = 64
UNTRUSTED_TEXT = 'module is not trusted on this computer'
```

У `ModuleError.__init__` рядок статусу: `self.status = status if isinstance(status, int) else STATUS.get(code, CORE_STATUS.get(code, 500))`.

3c. `Module`: у `__slots__` додай `'origin', 'trust', 'record', 'source', 'trust_error'`; у сигнатуру `__init__` — `origin='builtin', trust=None, record=False, source='', trust_error=None`; у тіло:

```python
        self.origin = origin            # 'builtin' | 'space' (свій модуль простору, етап 3c)
        self.trust = trust              # свій: 'untrusted' | 'trusted' | 'changed' | 'refused'; вбудований — None
        self.record = bool(record)      # свій: чи є запис довіри (у `untrusted` з пошкодженим знімком — є)
        self.source = source            # свій: тека в просторі, з `~`
        self.trust_error = trust_error  # свій: причина `untrusted`/`refused` (код)
```

Допиши в докстрінг класу абзац: «Свій модуль простору (`origin='space'`) без робочого знімка — `status='untrusted'` чи `'error'` (`refused`) з `error_code='module-untrusted'`: функцій нема, ролі й налаштування — з маніфесту теки.»

3d. Після `_load_dir` (≈520) — свої модулі:

```python
# ------------------------------------------------------------------------------- свої модулі простору (3c)

#: Кеш знімків своїх модулів: `{тека знімка: (відбиток, Module)}` у порядку використання; лок — на теку.
_OWN_CACHE = OrderedDict()
_OWN_LOCKS = {}


def _clone(m, **kw):
    """Новий `Module` з полями `m` і змінами `kw`: обʼєкт свого модуля — свій на кожен виклик (два простори з однаковими
    байтами ділять теку знімка, але не обʼєкт), а рішення про довіру не живе в кеші."""
    c = Module.__new__(Module)
    for s in Module.__slots__:
        setattr(c, s, getattr(m, s))
    c.roles = list(m.roles)
    c.settings = [dict(s) for s in m.settings]
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def untrusted_own(m):
    """Свій модуль без робочого знімка (недовірений чи `refused` без довіри): код не виконується, вмикати не можна."""
    return getattr(m, 'origin', 'builtin') == 'space' and m.error_code == 'module-untrusted'


def _builtin_ids():
    """Id модулів із тек вбудованих (`app/modules`, `DEAI_EXTRA_MODULES`, і ті, що програли як `shadowed`)."""
    _, items, lost = _scan()
    return {n for n, _ in items} | {n for n, _ in lost}


def _manifest_from_bytes(raw, folder, d):
    """`(метадані, None)` чи `(None, причина)` — маніфест свого модуля з УЖЕ прочитаних сканером байтів (не повторним
    читанням з диска), з тим самим захистом, що `spaces._read_json` (розмір, глибина), і `_check_manifest`."""
    if raw is None:
        return None, 'module.json: not found'
    if len(raw) > spaces.MAX_JSON_BYTES:
        return None, f'module.json: bigger than {spaces.MAX_JSON_BYTES} bytes'
    try:
        man = json.loads(raw.decode('utf-8'))
    except RecursionError:
        return None, 'module.json: nested too deep'
    except ValueError as e:                                   # UnicodeDecodeError — теж ValueError
        return None, f'module.json: {_short(e)}'
    return _check_manifest(man, folder, d)


def _meta_kw(meta):
    if not meta:
        return {}
    return dict(name=meta['name'], version=meta['version'], api=API_VERSION, roles=meta['roles'],
                settings=meta['settings'], publish_target=meta['publish_target'])


def _own_base(space):
    p = _space_path(space)
    return os.path.join(p, 'modules') if p and spaces.layer_on() else None


def _own_listing(space):
    """`([(id, тека)], примітки)` своїх модулів простору: лише `lstat`/`listdir`, без читання файлів модулів. Модуль —
    підтека з імʼям за `ID_RE`, у якій є `module.json`; решта ігнорується. Примітки — `id-taken`, `too-many-modules`,
    `modules-link`, `modules-unreadable`."""
    base = _own_base(space)
    if base is None:
        return [], []
    try:
        st = os.lstat(base)
    except FileNotFoundError:
        return [], []
    except OSError:
        return [], [{'folder': 'modules', 'code': 'modules-unreadable'}]
    if module_trust.is_link(st) or not stat.S_ISDIR(st.st_mode):
        return [], [{'folder': 'modules', 'code': 'modules-link'}]
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return [], [{'folder': 'modules', 'code': 'modules-unreadable'}]
    taken = _builtin_ids()
    out, notes = [], []
    for n in names:
        d = os.path.join(base, n)
        if not ID_RE.fullmatch(n) or not os.path.lexists(os.path.join(d, 'module.json')):
            continue
        if n in taken:
            notes.append({'folder': f'modules/{n}', 'code': 'id-taken'})
        elif len(out) >= MAX_OWN_MODULES:
            notes.append({'folder': f'modules/{n}', 'code': 'too-many-modules'})
        else:
            out.append((n, d))
    return out, notes


def own_notes(space):
    """Примітки своїх модулів простору (`[{folder, code}]`) для `GET /api/modules`; нічого не виконує й не хешує."""
    return _own_listing(space)[1]


def own_modules(space):
    """`{id: Module}` своїх модулів простору — новий обʼєкт на кожен виклик. Довірений — зі знімка (`_load_own`); без
    робочого знімка — без виконання, з маніфестом теки (якщо він розбирається). ⚠️ Може виконати код знімка — НЕ під
    `WRITE_LOCK`."""
    cands, _ = _own_listing(space)
    if not cands:
        return {}
    try:
        records, rec_err = module_trust.load_records(), None
    except module_trust.TrustUnreadable:
        records, rec_err = {}, 'trust-unreadable'
    return {mid: _own_module(space, mid, d, records, rec_err) for mid, d in cands}


def _own_module(space, mid, d, records, rec_err):
    try:
        sc, refused = module_trust.scan(d), None
    except module_trust.Refused as e:
        sc, refused = None, e
    meta = None
    if sc is not None:
        meta, why = _manifest_from_bytes(sc.manifest, mid, d)
        if why:
            refused = module_trust.Refused('bad-manifest', why)
    rec = None if rec_err else records.get(module_trust.key_for(_space_path(space), mid))
    base = dict(origin='space', source=module_trust.tilde(d), record=rec is not None)
    if rec is not None and module_trust.verify_snapshot(rec['hash']):
        m = _load_own(module_trust.snapshot_dir(rec['hash']), mid)
        trust = 'refused' if refused else ('trusted' if sc.hash == rec['hash'] else 'changed')
        return _clone(m, trust=trust, trust_error=refused.code if refused else None, **base)
    if refused:
        text = f'{refused.code}: {refused.detail}' if refused.detail else refused.code
        return Module(mid, status='error', error=text[:MAX_MESSAGE], error_code='module-untrusted', dir=d,
                      trust='refused', trust_error=refused.code, **_meta_kw(meta), **base)
    why = rec_err or ('snapshot-damaged' if rec is not None else None)
    return Module(mid, status='untrusted', error=UNTRUSTED_TEXT, error_code='module-untrusted', dir=d,
                  trust='untrusted', trust_error=why, **_meta_kw(meta), **base)


def _load_own(d, mid):
    """`Module` знімка `d` (id — `mid`). Верхній рівень `server.py` виконується в потоці-демоні з тайм-аутом
    `LOAD_TIMEOUT` і ПОЗА `_LOAD_LOCK` (лок — на теку знімка, щоб не будувати двічі): зависання свого модуля не блокує
    ні каталог інших просторів, ні вбудовані модулі. Не встиг — `module-error` «load timed out»; результат кешується за
    відбитком теки (потік-сирота доживає свій час)."""
    fp = module_trust.fingerprint(d)
    with _LOAD_LOCK:
        hit = _OWN_CACHE.get(d)
        lock = _OWN_LOCKS.setdefault(d, threading.Lock())
    if hit is not None and hit[0] == fp:
        return hit[1]
    with lock:
        with _LOAD_LOCK:
            hit = _OWN_CACHE.get(d)
        if hit is not None and hit[0] == fp:
            return hit[1]
        box = []
        sid = spaces.request_space_id()

        def work():
            try:
                with spaces.request_space(sid):
                    box.append(_build(d, mid))
            except BaseException as e:  # noqa: BLE001 — і `KeyboardInterrupt` модуля не валить сервер
                box.append(_failed(mid, d, 'module-error', _exc_text(e)))
        t = threading.Thread(target=work, name=f'deai-own-load-{mid}', daemon=True)
        t.start()
        t.join(LOAD_TIMEOUT)
        mod = box[0] if box else _failed(mid, d, 'module-error', f'load timed out after {LOAD_TIMEOUT} s')
        with _LOAD_LOCK:
            _OWN_CACHE[d] = (fp, mod)
            _OWN_CACHE.move_to_end(d)
            while len(_OWN_CACHE) > OWN_CACHE_MAX:
                old, _ = _OWN_CACHE.popitem(last=False)
                _OWN_LOCKS.pop(old, None)
        return mod
```

3e. `catalog` (≈523) — заміни:

```python
def catalog(space=None):
    """`{id: Module}` за абеткою: вбудовані (`app/modules` і, якщо задана, тека `DEAI_EXTRA_MODULES`; `id` вбудованого
    виграє — програш у `shadowed()`) і — коли передано простір — його свої модулі (`own_modules`: свіжі обʼєкти, довіра
    рахується щоразу). Модулі з помилкою — тут, зі `status='error'`; недовірені свої — зі `status='untrusted'`.
    ⚠️ Виконує код модулів (першого разу чи після зміни файлів) — НЕ кликати під `WRITE_LOCK`."""
    _, items, _ = _scan()
    out = {name: _load_dir(d, name) for name, d in items}
    live = {d for _, d in items}
    with _LOAD_LOCK:
        for k in [k for k in _CACHE if k not in live]:      # лише теки вбудованих: знімки — у `_OWN_CACHE`
            del _CACHE[k]
    if space:
        out.update(own_modules(space))
        out = dict(sorted(out.items()))
    return out
```

3f. `reset_caches` — під `_LOAD_LOCK` додай `_OWN_CACHE.clear()` і `_OWN_LOCKS.clear()`, наприкінці — `module_trust.reset_cache()`. Поруч з `last_check` додай:

```python
def forget_check(space_id, module_id):
    """Забути останній `check` модуля в просторі й кеш `capabilities` простору (довіра змінила код, що виконуватиметься)."""
    with _STATE_LOCK:
        _LAST_CHECK.pop((space_id, module_id), None)
        _CAPS.pop(space_id, None)
```

3g. Простір у функціях з id модуля:

- `_need_module(module_id, space=None)`: `m = catalog(space).get(module_id) if isinstance(module_id, str) else None`.
- `validate_settings(module_id, settings, space=None)`: `return _validate_patch(_need_module(module_id, space), settings)`.
- `write_secrets(space_id, module_id, patch, space=None)`: `m = _need_module(module_id, space)`; у докстрінг — «`space` — запис простору, щоб знайти СВІЙ модуль; без нього — лише вбудовані».
- `module_ctx(space, module)`: `m = module if isinstance(module, Module) else _need_module(module, space)`.
- `check(space, module_id)`: `m = _need_module(module_id, space)`.
- `published_root(space, module)`: `m = module if isinstance(module, Module) else _need_module(module, space)`.
- `effective_state(space)`: `catalog(space)`.
- `preflight`: `cat = catalog(space)`; одразу після перевірки `m is None`:

```python
    if enabling and untrusted_own(m):
        raise ModuleError('module-untrusted', message=f'{m.id}: {UNTRUSTED_TEXT}')
```

- `write_module_state`: `cat = catalog(space)`; після `patch = _validate_patch(m, settings)` (ДО локу):

```python
    if enabled is True and untrusted_own(m):
        raise ModuleError('module-untrusted', message=f'{m.id}: {UNTRUSTED_TEXT}')
```

і в тілі під локом, після `entry['enabled'] = …`:

```python
        if enabled is True and m.origin == 'space':
            entry['roles'] = list(m.roles)      # ролі свого модуля — у `space.json`: без теки (не приїхала з git) роль
                                                # однаково знає, що її веде він (`_paper_failure`)
```

- [ ] **Step 4: Прогін — зелені + старі модулі**

Run: `python3 "$G" 600 2500 python3 -m unittest tests.test_modules_own tests.test_modules tests.test_modules_api tests.test_comments_role tests.test_serve -v 2>&1 | tail -15`
Expected: PASS. Якщо падає наявний тест через `mock.patch.object(dm, 'catalog', spy)` зі `spy()` без аргументів — зміни `spy` на `spy(space=None)` (лише сигнатуру шпигуна; перевірки не чіпати).

- [ ] **Step 5: Мутації** (`python3 -B`, по одній)

| мутація | має впасти |
|---|---|
| `_own_module`: `if rec is not None and module_trust.verify_snapshot(rec['hash']):` → `if rec is not None:` | `test_damaged_snapshot_is_untrusted_with_a_record` |
| `untrusted_own`: `return False` | `test_untrusted_is_listed_from_its_manifest_and_never_runs` |
| `catalog`: прибрати `out.update(own_modules(space))` | `test_catalog_without_space_is_builtin_only` |
| `_load_own`: `t.join(LOAD_TIMEOUT)` → `t.join()` | `test_load_timeout` |
| `_own_listing`: `if n in taken:` → `if False:` | `test_notes_and_ignored_folders` |
| `catalog`: умова витіснення `if k not in live` застосована й до `_OWN_CACHE` (додай цикл витіснення по `_OWN_CACHE`) | `test_builtin_cache_eviction_does_not_drop_snapshots` |
| `_clone`: повертати `m` (без копії, `setattr` на ньому) | `test_two_spaces_with_the_same_bytes_do_not_share_module_objects` |

- [ ] **Step 6: Коміт**

```bash
git add app/deai_modules.py tests/test_modules_own.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): catalog(space) — свої модулі простору, знімок із тайм-аутом, недовірений не виконується

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Якщо підправлено шпигуна в старих тестах — додай ці файли поіменно.)

---

### Task 4: `deai_modules` — ролі «на папері», постачальник без запасного шляху, довіра в ядрі

**Files:**
- Modify: `app/deai_modules.py` (`_normalize` ≈580, `_holders` ≈726, `_provider_for` ≈1330, `_caps_key`/`capabilities` ≈1395)
- Modify: `tests/test_modules_own.py`

- [ ] **Step 1: Тести (червоні)** — допиши в `tests/test_modules_own.py`:

```python
class RolesTest(OwnEnv):
    def test_space_json_roles_survive_normalize(self):
        self.enable_raw()
        self.assertEqual(dm.space_modules(self.sp)['acme']['roles'], ['publish'])

    def test_untrusted_enabled_own_module_holds_its_role_on_paper(self):
        self.mk('pub')
        self.own()
        self.enable_raw()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(self.sp, 'pub', enabled=True)
        self.assertEqual(cm.exception.code, 'role-taken')
        st = dm.write_module_state(self.sp, 'pub', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['acme'])
        self.assertFalse(dm.space_modules(self.sp)['acme']['enabled'])

    def test_missing_or_broken_own_module_still_holds_its_role(self):
        self.mk('pub')
        self.enable_raw('ghost', ('publish',))                 # тека не приїхала з git — ролі лише в записі
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(self.sp, 'pub', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.message), ('role-taken', 'publish is already provided by ghost'))
        _write(os.path.join(self.sp['path'], 'modules', 'acme', 'module.json'), '{oops')   # маніфест не розбирається
        self.enable_raw('acme', ('publish',))
        st = dm.write_module_state(self.sp, 'pub', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['acme', 'ghost'])
        mods = dm.space_modules(self.sp)
        self.assertEqual((mods['acme']['enabled'], mods['ghost']['enabled'], mods['pub']['enabled']), (False, False, True))

    def test_provider_raises_for_untrusted_own_without_falling_back(self):
        self.mk('static-publish')                              # неявний типовий у просторі без інтеграцій
        self.own()
        self.enable_raw()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps.get('error')), (None, None), 'стан ролі, а не «space.json не читається»')

    def test_integrations_space_no_legacy_for_untrusted_publish_or_comments(self):
        sp = self.new_space('Liga', integrations=True)
        self.own('acme', roles=('publish',), sp=sp)
        self.own('talk', roles=('comments',), sp=sp, extra={'client': ['a.js']})
        _write(os.path.join(sp['path'], 'modules', 'talk', 'a.js'), '//')
        self.enable_raw('acme', ('publish',), sp=sp)
        self.enable_raw('talk', ('comments',), sp=sp)
        for role in ('publish', 'comments'):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.provider(role, sp)
            self.assertEqual(cm.exception.code, 'module-untrusted', role)
        caps = dm.capabilities(sp)
        self.assertEqual((caps['publish'], caps['comments']), (None, None))
        self.assertNotIn('error', caps)

    def test_missing_own_comments_module_is_an_error_not_legacy(self):
        sp = self.new_space('Liga', integrations=True)
        self.enable_raw('talk', ('comments',), sp=sp)          # тека не приїхала з git
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('comments', sp)
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(dm.capabilities(sp)['comments'], None)

    def test_integrations_space_without_explicit_modules_never_reads_the_catalog(self):
        sp = self.new_space('Liga', integrations=True)
        self.own('acme', sp=sp)
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог на шляху ЛІГА')):
            self.assertEqual(dm.provider('publish', sp), 'legacy')
            self.assertEqual(dm.provider('comments', sp), 'legacy')

    def test_tokens_role_errors_too(self):
        self.own('ds', roles=('tokens',))
        self.enable_raw('ds', ('tokens',))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('tokens', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')

    def test_caps_key_sees_trust_and_folder_changes(self):
        self.own()
        self.enable_raw()
        self.assertIsNone(dm.capabilities(self.sp)['publish'])
        self.trust()
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'acme')


class TrustCoreTest(OwnEnv):
    def setUp(self):
        super().setUp()
        os.environ[mt.SEAM_ENV] = 'yes'
        self.d = self.own()

    def view(self, mid='acme'):
        return dm.trust_view(self.sp, mid)

    def test_view_shape_and_no_execution(self):
        v = self.view()
        self.assertEqual((v['id'], v['state'], v['record'], v['roles']), ('acme', 'untrusted', False, ['publish']))
        self.assertRegex(v['hash'], r'^[0-9a-f]{64}$')
        self.assertEqual({f['change'] for f in v['files']}, {'new'})
        self.assertEqual(v['settings'], [{'key': 'token', 'type': 'secret', 'label': 'Token', 'public': False}])
        self.assertEqual(v['path'], os.path.join('~', 'work', 'alpha', 'modules', 'acme'))
        self.assertEqual(self.ran(), [])
        with self.assertRaises(dm.ModuleError) as cm:
            dm.trust_view(self.sp, 'nope')
        self.assertEqual(cm.exception.code, 'unknown-module')

    def test_grant_runs_the_snapshot_and_clears_the_last_check(self):
        dm.write_secrets(self.sp['id'], 'acme', {'token': 's'}, space=self.sp)
        dm._remember(self.sp, 'acme', {'ok': False, 'error': 'old'})
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertIsNone(dm.last_check(self.sp['id'], 'acme'))
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'trusted')
        self.assertEqual(self.view()['state'], 'trusted')
        self.assertEqual({f['change'] for f in self.view()['files']}, {'same'})

    def test_changed_view_and_regrant(self):
        h0 = self.view()['hash']
        dm.grant_trust(self.sp, 'acme', h0, 'uk')
        _write(os.path.join(self.d, 'server.py'), OWN_SERVER.replace('"v1"', '"v2"'))
        _write(os.path.join(self.d, 'new.js'), '//')
        v = self.view()
        self.assertEqual(v['state'], 'changed')
        self.assertEqual({f['path']: f['change'] for f in v['files']},
                         {'module.json': 'same', 'server.py': 'changed', 'new.js': 'new'})
        dm.grant_trust(self.sp, 'acme', v['hash'], 'uk')
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v2')

    def test_grant_refusals(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-changed')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', 'short', 'uk')
        self.assertEqual(cm.exception.code, 'bad-settings')
        _write(os.path.join(self.d, 'CON'), 'x')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-refused')
        self.assertEqual(self.ran(), [])

    def test_grant_maps_the_system_window(self):
        h = self.view()['hash']
        for answer, code in (('no', 'trust-declined'), ('declined', 'trust-declined'),
                             ('unavailable', 'trust-no-confirm'), ('busy', 'trust-busy')):
            with mock.patch.object(mt, 'ask', return_value=answer):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.grant_trust(self.sp, 'acme', h, 'uk')
            self.assertEqual(cm.exception.code, code, answer)
        self.assertEqual(mt.load_records(), {})

    def test_grant_passes_language_and_cleaned_texts(self):
        with mock.patch.object(mt, 'ask', return_value='yes') as ask:
            dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'en')
        title, msg, yes, no = ask.call_args[0][2]
        self.assertEqual((yes, no), ('Trust', 'Cancel'))
        self.assertIn('acme', msg)

    def test_grant_refuses_a_second_provider(self):
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        self.enable_raw()                                       # колега закомітив і свій модуль
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'role-taken')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_link_alias_has_no_trust_of_its_own_and_revoke_leaves_the_target(self):
        d = self.own()
        self.trust()
        os.symlink(d, os.path.join(self.sp['path'], 'modules', 'aaa'))
        v = dm.trust_view(self.sp, 'aaa')
        self.assertEqual((v['state'], v['record'], v['refused']['code']), ('refused', False, 'symlink'))
        self.assertFalse(dm.revoke_trust(self.sp, 'aaa'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.trust, m.record), ('trusted', True), 'довіру acme не знято через аліас')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'aaa', 'a' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-refused')

    def test_forget_own_during_a_load_keeps_that_load_out_of_the_cache(self):
        """Повторна довіра, поки перше (збійне) завантаження ще в польоті: його результат не мусить пережити довіру."""
        self.own(server=SLEEPY)                               # `SLEEPY` і ворота — з Task 3 (звір імена в цьому файлі)
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.5):
            t = threading.Thread(target=dm.catalog, args=(self.sp,))
            t.start()
            for _ in range(100):                              # дочекатись потоку завантаження
                if any(x.name == 'deai-own-load-acme' for x in threading.enumerate()):
                    break
                time.sleep(0.01)
            dm.forget_own(h)
            t.join(5)
        self.assertNotIn((mt.snapshot_dir(h), 'acme'), dm._OWN_CACHE)

    def test_retrust_forgets_a_cached_load_failure(self):
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        d = mt.snapshot_dir(h)
        bad = dm._failed('acme', d, 'module-error', 'load timed out after 5 s')
        with dm._LOAD_LOCK:
            dm._OWN_CACHE[(d, 'acme')] = (mt.fingerprint(d), bad)      # ніби перше завантаження не встигло
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'error')
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')                   # ті самі байти — знімок той самий
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'ok')

    def test_snapshot_removed_meanwhile_is_module_changed(self):
        with mock.patch.object(mt, 'put_record', side_effect=mt.SnapshotGone('x')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'module-changed')

    def test_unreadable_trust_file(self):
        _write(mt.trust_file(), '{oops')
        for call in (lambda: dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk'),
                     lambda: dm.revoke_trust(self.sp, 'acme')):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'trust-unreadable')

    def test_revoke_keeps_space_json_and_works_without_the_folder(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        dm.write_module_state(self.sp, 'acme', enabled=True, replace=True)
        before = open(self.space_json(self.sp), 'rb').read()
        self.assertTrue(dm.revoke_trust(self.sp, 'acme'))
        self.assertEqual(open(self.space_json(self.sp), 'rb').read(), before)
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'untrusted')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        import shutil
        shutil.rmtree(self.d)
        self.assertTrue(dm.revoke_trust(self.sp, 'acme'))
        self.assertFalse(dm.revoke_trust(self.sp, 'acme'))
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 180 1500 python3 -m unittest tests.test_modules_own -v 2>&1 | tail -20`
Expected: FAIL (`trust_view` нема, ролі не тримаються тощо).

- [ ] **Step 3: Реалізація**

3a. `_normalize` — після рядка `out[mid] = {...}`:

```python
        roles = e.get('roles')                     # пише вмикання СВОГО модуля (`write_module_state`); вбудовані — без
        if (isinstance(roles, list) and roles
                and all(isinstance(r, str) and r in ROLES_CALLED + ROLES_RESERVED for r in roles)):
            out[mid]['roles'] = list(dict.fromkeys(roles))
```

3b. `_holders` — заміни тіло й додай `_holds` перед ним:

```python
def _holds(o, space, explicit):
    """Чи тримає модуль `o` свої ролі: завантажений і ввімкнений (зокрема неявно) — так; СВІЙ модуль, ЯВНО ввімкнений
    у `space.json`, — так навіть коли тут не працює («на папері»: роль за ним, доки людина її не віддасть — інакше пізніша
    довіра дала б двох постачальників). Вбудований, що не завантажився, — ні, як і було."""
    if o.status == 'ok':
        return _enabled_in(o, space, explicit)[0]
    return o.origin == 'space' and explicit.get(o.id, {}).get('enabled') is True


def _roles_of(oid, cat, explicit):
    """Ролі модуля `oid`: з маніфесту (каталог) і — для СВОГО модуля чи теки, якої в каталозі нема, — ще й із запису
    `space.json` (їх пише вмикання свого модуля). Маніфест зламаний (ролей у каталозі нема) чи тека не приїхала з git —
    роль усе одно за ним «на папері», а не вільна для другого постачальника."""
    o = cat.get(oid)
    out = set(o.roles) if o is not None else set()
    if o is None or o.origin == 'space':
        out |= set(explicit.get(oid, {}).get('roles', ()))
    return out


def _holders(m, cat, space, explicit):
    """Id ІНШИХ модулів, що зараз тримають хоч одну роль `m`, за абеткою: з каталогу — за `_holds`; явно ввімкнений
    запис `space.json`, чиєї теки в каталозі нема, — теж (ролі з запису, «на папері»)."""
    mine = set(m.roles)
    out = []
    for oid in sorted(set(cat) | set(explicit)):
        if oid == m.id or not (mine & _roles_of(oid, cat, explicit)):
            continue
        o = cat.get(oid)
        if _holds(o, space, explicit) if o is not None else explicit[oid]['enabled'] is True:
            out.append(oid)
    return out
```

`_role_conflict` (≈741) — текст із тих самих ролей: `cat[oid]` для теки, якої нема, дав би `KeyError`, а порожній
перетин із ролями маніфесту — `IndexError`:

```python
    for oid in _holders(m, cat, space, explicit):
        return f'{sorted(set(m.roles) & _roles_of(oid, cat, explicit))[0]} is already provided by {oid}'
```

3b′. Покоління кешу знімків (ревʼю Task 3): `forget_own` посеред завантаження інакше програє — збійне завантаження,
що ще в польоті, допише себе в кеш ПІСЛЯ повторної довіри. Біля `_OWN_CACHE`: `_OWN_GEN = 0  # піднімає `forget_own``;
у `forget_own` (під `_LOAD_LOCK`, перед чисткою) — `global _OWN_GEN; _OWN_GEN += 1`; у `_load_own` — у ПЕРШОМУ блоці
`with _LOAD_LOCK:` запам'ятай `gen = _OWN_GEN`, а при записі в кеш (теж під `_LOAD_LOCK`) пиши лише `if _OWN_GEN == gen:`
(результат усе одно повертається викликачу). Онови докстрінг `_load_own` одним реченням.

3c. Перед `_provider_for`:

```python
def _paper_failure(role, cat, explicit):
    """`ModuleError` для ролі `role`, яку «на папері» веде явно ввімкнений СВІЙ модуль, що тут не працює, — або `None`.
    Модуль у каталозі, свій і не `ok` → `module-untrusted` (недовірений) чи `module-error`; модуля в каталозі нема, а
    запис `space.json` несе `roles` із цією роллю (їх пише вмикання свого модуля) → `module-error` (тека не приїхала чи
    зникла). Позначка `paper` каже `capabilities`, що роль — `None`, а не запасний `'legacy'`."""
    for mid in sorted(explicit):
        e = explicit[mid]
        if not e['enabled']:
            continue
        m = cat.get(mid)
        if m is not None:
            if m.origin != 'space' or m.status == 'ok' or role not in (m.roles or e.get('roles', [])):
                continue
            code = 'module-untrusted' if m.error_code == 'module-untrusted' else 'module-error'
            err = ModuleError(code, message=f'{mid}: {m.error or UNTRUSTED_TEXT}')
        elif role in e.get('roles', ()):
            err = ModuleError('module-error', message=f'{mid}: the module folder is missing')
        else:
            continue
        err.paper = True
        return err
    return None
```

3d. `_provider_for(role, space, get_cat=None)`: заміни `cat = catalog()` на

```python
    cat = get_cat() if get_cat is not None else catalog(space)
    paper = _paper_failure(role, cat, explicit)
    if paper is not None:
        raise paper                                     # свій модуль веде роль на папері: ні неявного, ні `'legacy'`
```

(решта — як була). Додай у докстрінг абзац про `_paper_failure`.

3e. `_caps_key`: додай елемент `own_sig(space)`; поруч — функцію:

```python
def own_sig(space):
    """Відбиток своїх модулів простору для ключів кешів: `fingerprint` кожної підтеки `modules/` і відбиток
    `trust.json`. Лише `lstat`/`listdir`: нічого не виконує й не хешує (шлях ЛІГА лишається «до каталогу»)."""
    base = _own_base(space)
    if base is None:
        return None
    try:
        names = sorted(os.listdir(base))[:MAX_OWN_MODULES * 4]
    except OSError:
        names = []
    return (tuple((n, module_trust.fingerprint(os.path.join(base, n))) for n in names), module_trust.records_sig())
```

3f. `capabilities`: один лінивий каталог на виклик і `None` для помилки «на папері»:

```python
        box = {}

        def get_cat():
            if 'c' not in box:
                box['c'] = catalog(space)
            return box['c']
        caps, error = {}, None
        for role in ROLES_CALLED:
            try:
                p = _provider_for(role, space, get_cat)
                caps[role] = p.id if isinstance(p, Module) else p
            except ModuleError as e:
                if getattr(e, 'paper', False):
                    caps[role] = None       # роль «на папері» за своїм модулем, що тут не працює: не `'legacy'` і НЕ
                    continue                # `error` — клієнт читає `error` як «space.json не читається» й сховав би картки
                error = error or e.code
                caps[role] = 'legacy' if role == 'publish' and spaces.integrations_for(space) else None
```

У докстрінг `capabilities` допиши: «Роль, яку «на папері» веде свій модуль, що тут не працює (`_paper_failure`), — `None` без ключа `error`: це стан ролі, а не простору (екран «Підключення» показує `error` як нечитабельний `space.json` і ховає картки — разом із «Довіритись…»).»

3g. Довіра в ядрі — у кінець файла (секція «довіра своїм модулям»; `import time` уже є):

```python
# ------------------------------------------------------------------------------ довіра своїм модулям (3c)

def _own_or_404(space, mid):
    """Тека свого модуля `mid` простору або `unknown-module` (нема серед своїх; вбудований id — теж)."""
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        raise ModuleError('unknown-module', message=str(mid)[:60])
    cands = dict(_own_listing(space)[0])
    if mid not in cands:
        raise ModuleError('unknown-module', message=f'{mid}: not an own module of this space')
    return cands[mid]


def _is_alias(space, mid):
    """Тека модуля — посилання (аліас): `key_for` бере `realpath`, тож її ключ — ключ ЦІЛІ, тобто чужий запис довіри."""
    try:
        return module_trust.is_link(os.lstat(os.path.join(_space_path(space), 'modules', mid)))
    except OSError:                     # теки нема — запис за шляхом, «Забрати довіру» зниклої теки працює
        return False


def _trust_setting(s):
    v = {'key': s['key'], 'type': s['type'], 'label': s['label']}
    if s['type'] == 'secret':
        v['public'] = bool(s.get('public'))
    return v


def trust_view(space, mid):
    """Дані діалогу довіри (`GET /api/module-trust`): тека сканується (з кешем відбитка) і порівнюється із записом
    довіри; назва, версія, ролі й налаштування — з маніфесту ТЕКИ (нової версії). Код теки не виконує (для вже
    довіреного модуля `own_modules` вантажить хіба його ЗНІМОК — той, що й так працює)."""
    src = _own_or_404(space, mid)
    m = own_modules(space).get(mid)
    rec = None
    if m is not None and m.record:      # `m.record` уже знає про аліас (Task 3); нечитабельний trust.json дає False
        try:
            rec = module_trust.load_records().get(module_trust.key_for(_space_path(space), mid))
        except module_trust.TrustUnreadable:
            rec = None
    out = {'id': mid, 'name': m.name if m else mid, 'version': m.version if m else '',
           'roles': list(m.roles) if m else [], 'settings': [], 'path': module_trust.tilde(src),
           'state': m.trust if m else 'untrusted', 'record': rec is not None}
    try:
        sc = module_trust.scan(src)
    except module_trust.Refused as e:
        out.update(state='refused', refused={'code': e.code, 'detail': e.detail})
        return out
    meta, why = _manifest_from_bytes(sc.manifest, mid, src)
    if why:
        out.update(state='refused', refused={'code': 'bad-manifest', 'detail': why[:MAX_MESSAGE]})
        return out
    files, removed = module_trust.diff(sc.files, rec['files'] if rec else None)
    out.update(name=meta['name'], version=meta['version'], roles=list(meta['roles']),
               settings=[_trust_setting(s) for s in meta['settings']], hash=sc.hash, files=files, removed=removed,
               total={'files': len(sc.files), 'bytes': sc.total})
    return out


def grant_trust(space, mid, want_hash, lang='uk'):
    """Довіра своєму модулю `mid` — рівно версії з хешем `want_hash`, яку бачила людина. Порядок (спека, «API»):
    сканування з байтами → `module-refused` / `module-changed` → «другий постачальник» (`role-taken`) → СИСТЕМНЕ ВІКНО
    поза локами (`trust-declined` / `trust-no-confirm` / `trust-busy`) → знімок із просканованих байтів → запис під
    `WRITE_LOCK` (`module-changed`, коли знімок встигли відсунути) → скидання `_LAST_CHECK` і `capabilities`.
    ⚠️ Блокує потік до відповіді людини (до `module_trust.CONFIRM_TIMEOUT` с); НЕ кликати під `WRITE_LOCK`."""
    _require_writable(space)
    src = _own_or_404(space, mid)
    if not isinstance(want_hash, str) or not module_trust.HASH_RE.fullmatch(want_hash):
        raise _bad('hash: expected the 64-character fingerprint shown in the dialog')
    key = module_trust.key_for(_space_path(space), mid)
    try:
        module_trust.load_records()
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    try:
        sc = module_trust.scan(src, with_data=True)
    except module_trust.Refused as e:
        raise ModuleError('module-refused', message=f'{e.code}: {e.detail}'[:MAX_MESSAGE]) from None
    meta, why = _manifest_from_bytes(sc.manifest, mid, src)
    if why:
        raise ModuleError('module-refused', message=f'bad-manifest: {why}'[:MAX_MESSAGE])
    if sc.hash != want_hash:
        raise ModuleError('module-changed', message='the module folder changed after the dialog was opened')
    explicit = space_modules(space)
    if explicit.get(mid, {}).get('enabled') is True:
        probe = types.SimpleNamespace(id=mid, roles=list(meta['roles']))      # ролі НОВОЇ версії теки
        why = _role_conflict(probe, catalog(space), space, explicit)
        if why:
            raise ModuleError('role-taken', message=why)
    texts = module_trust.confirm_texts(lang, meta['name'], mid, sc.hash, module_trust.tilde(src))
    answer = module_trust.ask(key, sc.hash, texts)
    if answer != 'yes':
        code = {'busy': 'trust-busy', 'unavailable': 'trust-no-confirm'}.get(answer, 'trust-declined')
        raise ModuleError(code, message=f'system confirmation: {answer}')
    try:
        module_trust.ensure_snapshot(sc)
        module_trust.put_record(key, {
            'id': mid, 'name': meta['name'], 'version': meta['version'], 'roles': list(meta['roles']),
            'hash': sc.hash, 'files': [{'path': p, 'size': n, 'sha256': h} for p, n, h in sc.files],
            'trusted_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    except module_trust.SnapshotGone:
        raise ModuleError('module-changed', message='the snapshot was removed meanwhile — try again') from None
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    except OSError as e:
        raise ModuleError('unwritable', message=f'trust: {type(e).__name__}') from None
    forget_check(_space_id(space), mid)
    forget_own(sc.hash)                     # завантаження знімка (і закешований збій, як-от тайм-аут) — наново


def revoke_trust(space, mid):
    """Забрати довіру свого модуля `mid` (ключ — за шляхом, тож і для теки, якої вже нема). `space.json` не чіпає;
    `True`, якщо запис був. `trust-unreadable` — файл довіри не читається (не переписуємо)."""
    _require_writable(space)
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        raise ModuleError('unknown-module', message=str(mid)[:60])
    if _is_alias(space, mid):
        return False                    # у аліаса свого запису нема; ключ збігся б із ключем цілі — чужу довіру не чіпаємо
    try:
        removed = module_trust.drop_record(module_trust.key_for(_space_path(space), mid))
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    except OSError as e:
        raise ModuleError('unwritable', message=f'trust: {type(e).__name__}') from None
    forget_check(_space_id(space), mid)
    return removed
```

- [ ] **Step 4: Прогін — зелені + регресія ядра**

Run: `python3 "$G" 400 2500 python3 -m unittest tests.test_modules_own tests.test_modules tests.test_modules_api tests.test_comments_role tests.test_publish_module -v 2>&1 | tail -15`
Expected: PASS.

- [ ] **Step 5: Мутації**

| мутація | має впасти |
|---|---|
| `_holds`: прибрати гілку `origin == 'space'` (повертати `False` для не-`ok`) | `test_untrusted_enabled_own_module_holds_its_role_on_paper` |
| `_roles_of`: прибрати `out |= …` (ролі з запису) | `test_missing_or_broken_own_module_still_holds_its_role` |
| `_holders`: `sorted(set(cat) | set(explicit))` → `sorted(cat)` | `test_missing_or_broken_own_module_still_holds_its_role` |
| `grant_trust`: прибрати `raise ModuleError('role-taken', …)` | `test_grant_refuses_a_second_provider` |
| `_provider_for`: прибрати `raise paper` | `test_provider_raises_for_untrusted_own_without_falling_back`, `test_integrations_space_no_legacy_…` |
| `_paper_failure`: прибрати гілку `elif role in e.get('roles', ())` | `test_missing_own_comments_module_is_an_error_not_legacy` |
| `capabilities`: прибрати гілку `paper` (`continue`) | `test_integrations_space_no_legacy_for_untrusted_publish_or_comments`, `test_provider_raises_for_untrusted_own_without_falling_back` |
| `_caps_key`: прибрати `own_sig(space)` | `test_caps_key_sees_trust_and_folder_changes` |
| `grant_trust`: `if sc.hash != want_hash:` → `if False:` | `test_grant_refusals` |
| `grant_trust`: `if answer != 'yes':` → `if False:` | `test_grant_maps_the_system_window` |
| `grant_trust`: прибрати `forget_check(...)` | `test_grant_runs_the_snapshot_and_clears_the_last_check` |
| `grant_trust`: прибрати `forget_own(sc.hash)` | `test_retrust_forgets_a_cached_load_failure` |
| `revoke_trust`: прибрати `if _is_alias(...)` | `test_a_link_alias_has_no_trust_of_its_own_and_revoke_leaves_the_target` |
| `trust_view`: запис без умови `m.record` | `test_a_link_alias_has_no_trust_of_its_own_and_revoke_leaves_the_target` |
| `_load_own`: зберігати в кеш без звірки `_OWN_GEN` | `test_forget_own_during_a_load_keeps_that_load_out_of_the_cache` |

- [ ] **Step 6: Коміт**

```bash
git add app/deai_modules.py tests/test_modules_own.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): ролі свого модуля «на папері», помилка ролі без запасного шляху, довіра в ядрі

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `serve.py` — список, маршрути довіри, адаптер з простором

**Files:**
- Modify: `app/serve.py` (`CHECK_NOT_A_VERDICT` ≈4664, `_module_status` ≈4703, `module_list` ≈4724, `module_write` ≈4790, `task_publish_share` ≈4380, `module_client_urls` ≈2595 і виклики ≈5497/≈5658, `module_client_target` ≈7709, `_REGISTRY_ROUTES` ≈5087, `do_GET` ≈5221, `do_POST` ≈6286, `_modules_get`/`_module_post` ≈7109–7160, старт ≈8046)
- Create: `tests/test_modules_trust_api.py`

- [ ] **Step 1: Тести (червоні)** — створи `tests/test_modules_trust_api.py`:

```python
"""HTTP своїх модулів і довіри (етап 3c, Task 5): поля свого модуля й `notes` у `GET /api/modules`, `GET/POST
/api/module-trust`, `POST /api/module-untrust`, адреса адаптера з простором, `module-settings` недовіреного без `check`.

Світ — `World` з `test_modules_api` (сервер у процесі, ізольовані `HOME`/`DEAI_HOME`, жодної мережі). Системне вікно —
шов `DEAI_TRUST_CONFIRM` (діє, бо `DEAI_HOME` тимчасовий) чи підмінений `module_trust.ask`.
"""
import json
import os
import shutil
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import serve  # noqa: E402
import deai_modules as dm  # noqa: E402
import module_trust as mt  # noqa: E402
from test_modules_api import World, _write  # noqa: E402
from test_modules_own import _unlock  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


SERVER = '''def check(ctx):
    return {"ok": True, "detail": "own"}


def publish(ctx, build_dir, task):
    return {"folder": build_dir}


def client_config(ctx):
    return {"hello": "world"}


def list(ctx, channel):
    return []


def resolve(ctx, channel, pin_id, resolved):
    return {"ok": True}
'''


class TrustApi(World):
    def setUp(self):
        super().setUp()
        # Власне присвоєння (`World` уже поставив те саме через `patch.dict` і сам його поверне): охоронець `test_serve`
        # (`SPACE_WRITERS` → `_assigns_deai_home`) розбирає джерело САМЕ цього файла
        os.environ['DEAI_HOME'] = self.deai
        self.addCleanup(_unlock, self.tmp)           # LIFO: раніше за `rmtree` світу — інакше знімки 0500 лишились би
        # Сітка: справжнє системне вікно в тесті недосяжне. Шов `DEAI_TRUST_CONFIRM` відповідає в `confirm` РАНІШЕ за
        # `confirm_command`, тож тестам зі швом чи підміненим `ask` вона не заважає, а `subprocess` решти коду не чіпає
        net = mock.patch.object(mt, 'confirm_command', side_effect=AssertionError('системне вікно в тесті'))
        net.start()
        self.addCleanup(net.stop)
        self.modules()
        mt.clear_declined()
        os.environ[mt.SEAM_ENV] = 'yes'
        self.addCleanup(os.environ.pop, mt.SEAM_ENV, None)
        self.browser = {'Origin': self.base, 'Sec-Fetch-Site': 'same-origin'}

    def own(self, mid='acme', roles=('publish',), client=None, space=None):
        d = os.path.join((space or self.off)['path'], 'modules', mid)
        man = {'api': 1, 'id': mid, 'name': mid.title(), 'version': '1.0.0', 'roles': list(roles),
               'settings': [{'key': 'token', 'type': 'secret', 'label': 'Token'}]}
        if client:
            man['client'] = client
            for n in client:
                _write(os.path.join(d, n), f'/* {n} v1 */')
        _write(os.path.join(d, 'module.json'), json.dumps(man))
        _write(os.path.join(d, 'server.py'), SERVER)
        return d

    def view(self, mid='acme', space='off'):
        st, body = self.get(f'/api/module-trust?space={space}&id={mid}')
        self.assertEqual(st, 200, body)
        return body['trust']

    def grant(self, mid='acme', space='off', headers=None):
        return self.post('/api/module-trust', {'space': space, 'id': mid, 'hash': self.view(mid, space)['hash']},
                         headers=self.browser if headers is None else headers)

    def test_listing_fields_and_builtins_unchanged(self):
        self.own()
        lst = self.listing()
        e = lst['acme']
        self.assertEqual((e['builtin'], e['custom'], e['trust'], e['record'], e['status'], e['runs']),
                         (False, True, 'untrusted', False, 'untrusted', False))
        self.assertEqual(e['source'], os.path.join('~', 'deai-work', 'off', 'modules', 'acme'))
        self.assertNotIn('custom', lst['css-tokens'])
        self.assertNotIn('trust', lst['css-tokens'])

    def test_notes_only_when_present(self):
        st, body = self.get('/api/modules')
        self.assertEqual(sorted(body), ['modules'])
        self.own('css-tokens')
        st, body = self.get('/api/modules')
        self.assertEqual(body['notes'], [{'folder': 'modules/css-tokens', 'code': 'id-taken'}])

    def test_trust_needs_browser_headers(self):
        self.own()
        for headers in ({}, {'Origin': self.base}, {'Sec-Fetch-Site': 'same-origin'}):
            st, body = self.grant(headers=headers)
            self.refused(st, body, 403, 'trust-needs-ui')
        st, body = self.grant(headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual((st, body.get('error')), (403, 'foreign origin'))
        self.assertEqual(mt.load_records(), {})

    def test_trust_flow(self):
        self.own()
        st, body = self.grant()
        self.assertEqual((st, body['ok'], body['module']['trust'], body['module']['runs']), (200, True, 'trusted', True), body)
        st, body = self.post('/api/module-enable', {'id': 'acme', 'secrets': {'token': 'tok'}, 'replace': True})
        self.assertEqual((st, body['check']['ok']), (200, True), body)

    def test_trust_refusals(self):
        d = self.own()
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': '0' * 64}, headers=self.browser)
        self.refused(st, body, 409, 'module-changed')
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'css-tokens', 'hash': '0' * 64},
                             headers=self.browser)
        self.refused(st, body, 404, 'unknown-module')
        h = self.view()['hash']
        _write(os.path.join(d, 'NUL'), 'x')
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': h}, headers=self.browser)
        self.refused(st, body, 409, 'module-refused')

    def test_odd_lang_falls_back_to_uk_and_never_breaks_the_request(self):
        self.own()
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='no') as ask:
            for lang in ([], {}, 7, 'zz'):
                st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': h, 'lang': lang},
                                     headers=self.browser)
                self.refused(st, body, 409, 'trust-declined')
                self.assertEqual(ask.call_args[0][2][2], mt.CONFIRM_TEXT['uk']['yes'], lang)

    def test_system_window_answers(self):
        self.own()
        os.environ[mt.SEAM_ENV] = 'no'
        st, body = self.grant()
        self.refused(st, body, 409, 'trust-declined')
        with mock.patch.object(mt, 'confirm', side_effect=AssertionError('вікно знову')):
            os.environ[mt.SEAM_ENV] = 'yes'
            st, body = self.grant()
        self.refused(st, body, 409, 'trust-declined')
        mt.clear_declined()
        os.environ[mt.SEAM_ENV] = 'unavailable'
        st, body = self.grant()
        self.refused(st, body, 409, 'trust-no-confirm')
        os.environ[mt.SEAM_ENV] = 'yes'
        mt._ASK_LOCK.acquire()
        try:
            st, body = self.grant()
        finally:
            mt._ASK_LOCK.release()
        self.refused(st, body, 409, 'trust-busy')

    def test_untrust_keeps_space_json_and_works_without_the_folder(self):
        d = self.own()
        self.grant()
        self.post('/api/module-enable', {'id': 'acme', 'replace': True})
        before = self.sj_bytes()
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'})
        self.assertEqual((st, body['ok'], body['module']['trust']), (200, True, 'untrusted'), body)
        self.assertEqual(self.sj_bytes(), before)
        self.grant()
        shutil.rmtree(d)
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'})
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(mt.load_records(), {})

    def test_untrusted_settings_without_check_and_refused_check_and_enable(self):
        self.own()
        st, body = self.post('/api/module-settings', {'id': 'acme', 'secrets': {'token': 'tok'}})
        self.assertEqual(st, 200, body)
        self.assertNotIn('check', body)
        st, body = self.post('/api/module-check', {'id': 'acme'})
        self.refused(st, body, 409, 'module-untrusted')
        before = self.sj_bytes()
        st, body = self.post('/api/module-enable', {'id': 'acme', 'replace': True})
        self.refused(st, body, 409, 'module-untrusted')
        self.assertEqual(self.sj_bytes(), before)

    def test_adapter_is_served_from_the_snapshot_by_space(self):
        d = self.own('talk', roles=('comments',), client=['adapter.js'])
        st, raw = self.get('/api/module-client/off/talk/adapter.js')
        self.assertEqual(st, 404, 'недовірений адаптер роздано')
        self.grant('talk')
        _write(os.path.join(d, 'adapter.js'), '/* adapter.js v2 */')
        st, raw = self.get('/api/module-client/off/talk/adapter.js')
        self.assertEqual((st, raw), (200, '/* adapter.js v1 */'))
        self.assertEqual(self.get('/api/module-client/talk/adapter.js')[0], 404, 'свій модуль — лише з простором')
        self.assertEqual(self.get('/api/module-client/on/talk/adapter.js')[0], 404, 'чужий простір')
        self.assertEqual(self.get('/api/module-client/off/css-tokens/x.js')[0], 404)
        mod = dm.catalog(self.off)['talk']
        self.assertEqual(serve.module_client_urls(mod, self.off), ['/api/module-client/off/talk/adapter.js'])

    def test_publish_share_sees_an_own_url_module(self):
        d = self.own('vpub', roles=('publish',))
        man = json.loads(open(os.path.join(d, 'module.json')).read())
        man['publish_target'] = 'url'
        man['settings'].append({'key': 'password', 'type': 'secret', 'label': 'Password'})
        _write(os.path.join(d, 'module.json'), json.dumps(man))
        self.grant('vpub')
        self.post('/api/module-enable', {'id': 'vpub', 'replace': True, 'secrets': {'password': 'pw'}})
        spaces.set_request_space('off')
        self.addCleanup(spaces.clear_request_space)
        out = serve.task_publish_share(self.off, {})
        self.assertIs(out.get('publish_gate'), True, out)

    def test_seam_warning(self):
        self.assertIn('DEAI_TRUST_CONFIRM', serve.trust_seam_warning() or '')
        os.environ.pop(mt.SEAM_ENV)
        self.assertIsNone(serve.trust_seam_warning())


if __name__ == '__main__':
    unittest.main()
```

⚠️ Звір у `test_publish_share_sees_an_own_url_module`, що повертає `task_publish_share` для простору з паролем і без публікації (докстрінг: «чи заданий пароль ЗАРАЗ») — очікування `publish_gate: True`. Якщо форма інша (функція вимагає ще щось у `meta`), підлаштуй ВХІД тесту, а не очікування.

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 180 2000 python3 -m unittest tests.test_modules_trust_api -v 2>&1 | tail -20`
Expected: FAIL.

- [ ] **Step 3: Реалізація в `app/serve.py`**

3a. Імпорт поруч з `import deai_modules`: `import module_trust`.

3b. `CHECK_NOT_A_VERDICT = ('unknown-module', 'space-json-unreadable', 'module-untrusted')` і в коментар над ним: «`module-untrusted` — свій модуль без довіри: його код не виконувався, вердикту нема».

3c. `_module_status` — першим рядком тіла:

```python
    if m.status == 'untrusted':
        return 'untrusted', m.error                     # свій модуль без довіри (3c): не «помилка», а «потрібна довіра»
```

3d. `module_list`: `cat = deai_modules.catalog(space)`; після побудови `e = {...}` (до `last_check`):

```python
        if m.origin == 'space':                         # свій модуль простору (3c); запис вбудованого не змінюється
            e.update(builtin=False, custom=True, trust=m.trust, record=m.record, source=m.source,
                     runs=not deai_modules.untrusted_own(m))      # код виконується тут (робочий знімок)
            if m.trust_error:
                e['trust_error'] = m.trust_error
```

Поруч додай:

```python
def modules_payload(space):
    """Тіло `GET /api/modules`: `{modules}` і — ЛИШЕ коли є — `notes` своїх модулів простору (відповідь простору без
    своїх модулів побайтно та сама, що до 3c)."""
    out = {'modules': module_list(space)}
    notes = deai_modules.own_notes(space)
    if notes:
        out['notes'] = notes
    return out
```

і в `_modules_get`: `self._send_json(modules_payload(sp))`.

3e. `module_write`: `deai_modules.validate_settings(mid, settings, space)`; `deai_modules.write_secrets(space['id'], mid, secrets, space=space)`; заміни останній рядок на:

```python
    m = deai_modules.catalog(space).get(mid)
    replaced = state.get('replaced') if swap else None
    if m is not None and deai_modules.untrusted_own(m):
        return None, replaced                           # свій модуль без довіри: перевіряти нічого (код не виконується)
    return module_check_verdict(space, mid), replaced
```

і докстрінг: «Повертає `(вердикт | None, replaced | None)`: вердикт `check` або `None` (`disable`; налаштування свого модуля без довіри)». У `_module_post`: `if action != 'disable' and verdict is not None: out['check'] = verdict`.

3f. `task_publish_share`: `mod = deai_modules.catalog(space).get(pub)`.

3g. `module_client_urls`:

```python
def module_client_urls(prov, space=None):
    """Кореневі адреси файлів браузерного адаптера модуля `prov` у порядку маніфесту: вбудований —
    `/api/module-client/<id>/<файл>`, свій модуль простору (3c) — `/api/module-client/<простір>/<id>/<файл>` (свій модуль
    є лише у своєму просторі; роздається зі знімка). Без `/t/<задача>/`: це маршрут простору, а не задачі."""
    if getattr(prov, 'origin', 'builtin') == 'space':
        sid = quote(str((space or {}).get('id', '')), safe='')
        return [f'{MODULE_CLIENT_PREFIX}{sid}/{prov.id}/{name}' for name in prov.client]
    return [f'{MODULE_CLIENT_PREFIX}{prov.id}/{name}' for name in prov.client]
```

Виклики: ≈5497 `module_client_urls(prov, page_space)`, ≈5658 `module_client_urls(prov, space)` (імена змінних простору в цих місцях — звір; це ті самі простори, що йдуть у `comments_client`). Перевір `grep -n "module_client_urls(" app/serve.py` — інших викликів нема.

3h. `module_client_target`:

```python
        parts = [unquote(p, errors='strict') for p in path[len(MODULE_CLIENT_PREFIX):].split('/')]
        sp = None
        if len(parts) == 3:                             # свій модуль: /<простір>/<модуль>/<файл>
            sid, mid, name = parts
            if not spaces.SPACE_ID_RE.fullmatch(sid):
                return None
            sp = next((s for s in spaces.read_registry()['spaces'] if s['id'] == sid), None)
            if sp is None:
                return None
        elif len(parts) == 2:
            mid, name = parts
        else:
            return None
        if not deai_modules.ID_RE.fullmatch(mid) or not deai_modules.CLIENT_RE.fullmatch(name):
            return None
        mod = deai_modules.catalog(sp).get(mid)
        if (mod is None or mod.status != 'ok' or 'comments' not in mod.roles or name not in mod.client
                or mod.origin != ('space' if sp else 'builtin')):
            return None
        return mod, name
```

Онови докстрінг і коментар над `MODULE_CLIENT_PREFIX` (дві форми адреси; свій — зі знімка).

3i. Маршрути: у `_REGISTRY_ROUTES` додай `'/api/module-trust', '/api/module-untrust'`. У `do_GET` поруч із гілкою `'/api/modules'`: `elif self.path.split('?')[0] == '/api/module-trust': self._module_trust_get()` (повтори форму сусідньої гілки — `if`/`elif` як там). У `do_POST` після `'/api/module-check'`:

```python
        elif self.path == '/api/module-trust':
            self._module_trust_post(payload)
        elif self.path == '/api/module-untrust':
            self._module_untrust(payload)
```

Методи — поруч із `_modules_get`:

```python
    def _module_trust_get(self):
        """`GET /api/module-trust?space=&id=` → `{ok: true, trust: <дані діалогу>}` (`deai_modules.trust_view`)."""
        q = parse_qs(urlparse(self.path).query)
        sp = self._module_space(q.get('space', [None])[0])
        if sp is None:
            return
        self._send_json({'ok': True, 'trust': deai_modules.trust_view(sp, q.get('id', [None])[0])})

    def _module_trust_post(self, payload):
        """`POST /api/module-trust {space, id, hash, lang?}` → `{ok: true, module}`. Лише з браузера канваса: `Origin`
        Є й локальний І `Sec-Fetch-Site: same-origin` — інакше 403 `trust-needs-ui`. Це фільтр від curl агента, а не
        межа: межа — системне вікно ОС у `grant_trust` (скрипт сторінки макета шле ті самі заголовки)."""
        origin = self.headers.get('Origin')
        if not origin or not _local_origin(origin) or self.headers.get('Sec-Fetch-Site') != 'same-origin':
            self._space_error(403, 'trust-needs-ui', 'trust is granted only from the canvas page in a browser')
            return
        sp = self._module_space(payload.get('space'))
        if sp is None:
            return
        mid = payload.get('id')
        lang = payload.get('lang')
        lang = lang if isinstance(lang, str) and lang in module_trust.CONFIRM_TEXT else 'uk'   # `[]` у `in` — TypeError
        deai_modules.grant_trust(sp, mid, payload.get('hash'), lang)
        self._send_json({'ok': True, 'module': module_entry(sp, mid)})

    def _module_untrust(self, payload):
        """`POST /api/module-untrust {space, id}` → `{ok: true, module: <запис> | null}`: зняти довіру — безпечний
        напрям, тож ні `Sec-Fetch-Site`, ні системного вікна (`deai_modules.revoke_trust`)."""
        sp = self._module_space(payload.get('space'))
        if sp is None:
            return
        mid = payload.get('id')
        deai_modules.revoke_trust(sp, mid)
        self._send_json({'ok': True, 'module': module_entry(sp, mid)})
```

`ModuleError` з цих викликів відповідає центральний `_guarded` (`{ok: false, code, error}`, статус — `e.status`, тобто й `CORE_STATUS`).

3j. Попередження про шов:

```python
def trust_seam_warning():
    """Рядок для журналу старту, коли діє тестовий шов `DEAI_TRUST_CONFIRM` (довіра без системного вікна), інакше `None`."""
    v = module_trust.seam_value()
    if v is None:
        return None
    return f'⚠ DEAI_TRUST_CONFIRM={v}: own-module trust is answered WITHOUT the system window (test seam)'
```

і в місці старту (≈8046, після `print(f'Design Canvas v2: …')`): `w = trust_seam_warning()` → `if w: print(w, file=sys.stderr)`.

- [ ] **Step 4: Прогін — зелені + увесь Python**

Run: `python3 "$G" 900 3000 npm test`
Expected: PASS (node + усі набори Python, і на `python3` 3.9 — як налаштовано в `npm test`).

- [ ] **Step 5: Мутації**

| мутація | має впасти |
|---|---|
| `_module_trust_post`: прибрати `or self.headers.get('Sec-Fetch-Site') != 'same-origin'` | `test_trust_needs_browser_headers` |
| `_module_trust_post`: `if not origin or …` → `if (origin and not _local_origin(origin)) or …` (пропускає без Origin) | `test_trust_needs_browser_headers` |
| `module_client_target`: прибрати `or mod.origin != (...)` | `test_adapter_is_served_from_the_snapshot_by_space` |
| `module_list`: прибрати `e.update(...)` для свого | `test_listing_fields_and_builtins_unchanged` |
| `module_list`: `runs=True` завжди | `test_listing_fields_and_builtins_unchanged` |
| `modules_payload`: завжди класти `notes` | `test_notes_only_when_present` |
| `module_write`: прибрати гілку `untrusted_own` | `test_untrusted_settings_without_check_and_refused_check_and_enable` |
| `CHECK_NOT_A_VERDICT` без `module-untrusted` | той самий тест (check стане 200-вердиктом) |
| `task_publish_share`: `catalog(space)` → `catalog()` | `test_publish_share_sees_an_own_url_module` |

- [ ] **Step 6: Коміт**

```bash
git add app/serve.py tests/test_modules_trust_api.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): API довіри (module-trust/untrust), свої модулі в списку, адаптер зі знімка за простором

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: «Підключення» — картки своїх модулів, примітки, словник, стилі

**Files:**
- Modify: `app/connections-model.js` (`cardView` ≈84, `whyOf` ≈123, `REFUSAL_KEYS` ≈134; нові `isOwn`, `ownRuns`, `trustWhyKey`, `trustLine`, `noteView`)
- Modify: `app/connections-view.js` (`BADGES`, `ACTIONS`, `cardHTML`, `agentHTML`, `connPageHTML`, `drawerHTML`; нові `ownTagHTML`, `trustLineHTML`)
- Modify: `app/app.js` (`connState` ≈188, `connView` ≈2639, `loadConn` ≈2652)
- Modify: `app/i18n.js` (`UK` і `EN` — після `cnTimeout`; `publishErrUntrusted` — поруч із `publishErrModule`), `app/styles.css` (після правил `.cn-agent`)
- Modify: `app/spaces-model.js` (`PUBLISH_ERR_KEYS` ≈696)
- Create: `tests/connections-own.test.mjs`
- Modify: `tests/css-guards.test.mjs`, `tests/connections-wiring.test.mjs`

- [ ] **Step 1: Тести (червоні)** — створи `tests/connections-own.test.mjs`:

```js
/**
 * Свої модулі простору на екрані «Підключення» (Deai 0.7.0, етап 3c; спека
 * `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`, «Екран «Підключення»»): `cardView` для кожного стану
 * таблиці, причина, рядок довіри, примітки, нові відмови; розмітка — пігулка «свій», бейдж, дії, «Забрати довіру».
 * Вбудовані модулі — без змін (їх стережуть наявні `connections-model.test.mjs` і `connections-view.test.mjs`).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import {
  cardView, isOwn, noteView, ownRuns, providerLine, refusalView, roleHolders, trustLine, trustWhyKey, whyOf,
} from "../app/connections-model.js";
import { cardHTML, connPageHTML, drawerHTML, nowHTML } from "../app/connections-view.js";

const own = (over = {}) => ({
  id: "acme", name: "Acme", version: "1.0.0", api: 1, roles: ["publish"], builtin: false, custom: true,
  enabled: false, implicit: false, status: "untrusted", trust: "untrusted", record: false, runs: false,
  source: "~/work/alpha/modules/acme", error: "module is not trusted on this computer", settings: [], ...over,
});
const builtin = (over = {}) => ({
  id: "static-publish", name: "Static", version: "1", api: 1, roles: ["publish"], builtin: true,
  enabled: true, implicit: false, status: "ok", settings: [], ...over,
});
const pick = (v) => ({ badge: v.badge, actions: v.actions, why: v.why });

test("isOwn / ownRuns: лише `custom: true`; `runs` — лише у свого", () => {
  assert.equal(isOwn(own()), true);
  assert.equal(isOwn(builtin()), false);
  assert.equal(isOwn(builtin({ custom: "true" })), false, "лише справжнє true");
  assert.equal(ownRuns(own({ runs: true })), true);
  assert.equal(ownRuns(builtin({ runs: true })), false, "вбудований не «свій», навіть з полем runs");
});

test("cardView: кожен стан таблиці спеки", () => {
  assert.deepEqual(pick(cardView(own())), { badge: "untrusted", actions: ["trust"], why: false });
  assert.deepEqual(pick(cardView(own({ enabled: true }))), { badge: "untrusted", actions: ["trust", "disable"], why: true });
  const refused = { trust: "refused", status: "error", trust_error: "symlink", error: "symlink: alias.py: symbolic link" };
  assert.deepEqual(pick(cardView(own(refused))), { badge: "error", actions: ["trustinfo"], why: true });
  assert.deepEqual(pick(cardView(own({ ...refused, enabled: true }))), { badge: "error", actions: ["trustinfo", "disable"], why: true });
  /* Знімок працює: як у вбудованого + дія довіри. */
  assert.deepEqual(pick(cardView(own({ trust: "refused", runs: true, status: "ok", enabled: true, trust_error: "too-big" }))),
    { badge: "ok", actions: ["configure", "check", "disable", "trustinfo"], why: false });
  assert.deepEqual(pick(cardView(own({ trust: "changed", runs: true, status: "unchecked" }))),
    { badge: "off", actions: ["enable", "trust"], why: false });
  assert.deepEqual(pick(cardView(own({ trust: "changed", runs: true, status: "error", enabled: true, error: "check failed" }))),
    { badge: "error", actions: ["configure", "check", "disable", "trust"], why: true });
  assert.deepEqual(pick(cardView(own({ trust: "trusted", runs: true, status: "ok", enabled: true }))),
    { badge: "ok", actions: ["configure", "check", "disable"], why: false });
});

test("cardView вбудованого — рівно як до 3c (жодних дій довіри)", () => {
  assert.deepEqual(pick(cardView(builtin())), { badge: "ok", actions: ["configure", "check", "disable"], why: false });
  assert.deepEqual(pick(cardView(builtin({ enabled: false }))), { badge: "off", actions: ["enable"], why: false });
  assert.deepEqual(pick(cardView(builtin({ trust: "changed" }))), { badge: "ok", actions: ["configure", "check", "disable"], why: false },
    "поле trust без custom — не свій модуль");
});

test("whyOf: недовірений увімкнений — потрібна довіра; недовірений вимкнений — нічого; refused без знімка — причина + деталь", () => {
  assert.deepEqual(whyOf(own({ enabled: true })), { key: "cnTrustNeededWhy", detail: "" });
  assert.equal(whyOf(own()), null);
  assert.deepEqual(whyOf(own({ trust: "refused", status: "error", trust_error: "hardlink", error: "hardlink: a.py" })),
    { key: "trWhyHardlink", detail: "hardlink: a.py" });
  assert.equal(whyOf(own({ trust: "refused", status: "error", error: "x".repeat(400) })).detail.length, 300, "деталь обрізано");
});

test("trustWhyKey: кожна причина спеки має свій ключ, невідома — trWhyOther", () => {
  const codes = ["symlink", "hardlink", "special-file", "too-many-files", "too-big", "too-deep", "bad-name", "unreadable",
    "unstable", "bad-manifest", "snapshot-damaged", "trust-unreadable"];
  const keys = codes.map(trustWhyKey);
  assert.equal(new Set(keys).size, codes.length, "ключі не повторюються");
  assert.ok(!keys.includes("trWhyOther"));
  assert.equal(trustWhyKey("nope"), "trWhyOther");
  assert.equal(trustWhyKey("__proto__"), "trWhyOther", "Map, а не обʼєкт");
});

test("trustLine: changed / refused зі знімком / пошкоджений знімок / нечитабельний файл довіри; інакше null", () => {
  assert.deepEqual(trustLine(own({ trust: "changed", runs: true })), { key: "cnTrustChanged", why: null });
  assert.deepEqual(trustLine(own({ trust: "refused", runs: true, trust_error: "too-deep" })), { key: "cnTrustRefusedNew", why: "trWhyTooDeep" });
  assert.equal(trustLine(own({ trust: "refused", runs: false, status: "error" })), null, "без знімка — причина в whyOf, не тут");
  assert.deepEqual(trustLine(own({ trust_error: "snapshot-damaged", record: true })), { key: "cnTrustDamaged", why: null });
  assert.deepEqual(trustLine(own({ trust_error: "trust-unreadable" })), { key: "cnRefTrustUnreadable", why: null });
  assert.equal(trustLine(own({ trust: "trusted", runs: true })), null);
  assert.equal(trustLine(own()), null);
  assert.equal(trustLine(builtin({ trust: "changed" })), null);
});

test("noteView: коди → ключі з текою; невідомий — cnNoteOther; сміття відкинуто", () => {
  assert.deepEqual(noteView([
    { folder: "modules/pub", code: "id-taken" }, { folder: "modules/m32", code: "too-many-modules" },
    { folder: "modules", code: "modules-link" }, { folder: "modules", code: "modules-unreadable" },
    { folder: "modules/x", code: "what" }, null, { code: "id-taken" }, { folder: 3, code: "id-taken" },
  ]), [
    { key: "cnNoteIdTaken", folder: "modules/pub" }, { key: "cnNoteTooMany", folder: "modules/m32" },
    { key: "cnNoteLink", folder: "modules" }, { key: "cnNoteUnreadable", folder: "modules" },
    { key: "cnNoteOther", folder: "modules/x" },
  ]);
  assert.deepEqual(noteView(undefined), []);
});

test("refusalView: нові коди довіри мають свої тексти", () => {
  const want = {
    "module-untrusted": "cnRefUntrusted", "module-changed": "cnRefChanged", "module-refused": "cnRefRefused",
    "trust-needs-ui": "cnRefNeedsUi", "trust-declined": "cnRefDeclined", "trust-no-confirm": "cnRefNoConfirm",
    "trust-busy": "cnRefBusy", "trust-unreadable": "cnRefTrustUnreadable",
  };
  for (const [code, key] of Object.entries(want)) assert.equal(refusalView({ code }).key, key, code);
});

test("providerLine: роль «на папері» за увімкненим недовіреним — «чекає довіри», а не «нікого»", () => {
  const caps = { publish: null, comments: null, tokens: null };
  const list = [own({ enabled: true })];
  assert.deepEqual(providerLine("publish", caps, list), { kind: "waiting", id: "acme", entry: list[0] });
  assert.equal(providerLine("publish", caps, [own()]).kind, "none", "невключений роль не тримає");
  assert.equal(providerLine("publish", caps, [own({ enabled: true, trust: "trusted", runs: true, status: "ok" })]).kind, "none");
  assert.equal(providerLine("comments", caps, list).kind, "none", "чужа роль");
  assert.equal(providerLine("publish", { ...caps, error: "space-json-unreadable" }, list).kind, "error", "стан простору — першим");
  assert.match(nowHTML("publish", { space: { capabilities: caps }, list }), /Зараз: «Acme» — чекає довіри на цьому компʼютері/);
});

test("roleHolders: увімкнений недовірений свій модуль — власник ролі (сервер так само тримає роль «на папері»)", () => {
  const list = [own({ enabled: true }), builtin({ id: "vercel-publish", enabled: false })];
  assert.deepEqual(roleHolders(list[1], list).map((x) => x.id), ["acme"]);
});

test("cardHTML: пігулка «свій» з текою в title, бейдж «Потрібна довіра» з замком, кнопка «Довіритись…»", () => {
  const h = cardHTML(own({ name: '<img src=x onerror="alert(1)">', source: '~/a"b<c' }), new Map());
  assert.match(h, /<span class="cn-tag cn-tag--own" title="~\/a&quot;b&lt;c">свій<\/span>/);
  assert.match(h, /cn-badge cn-badge--untrusted"><svg[^>]*>.*?<\/svg>Потрібна довіра/s);
  assert.match(h, /data-cn="trust" data-id="acme">/);
  assert.doesNotMatch(h, /<img/, "назва з маніфесту — текст");
  assert.doesNotMatch(cardHTML(builtin(), new Map()), /cn-tag--own|data-cn="trust/);
});

test("cardHTML: рядок довіри під описом; «Чому не можна…» для refused", () => {
  const h = cardHTML(own({ trust: "changed", runs: true, status: "unchecked" }), new Map());
  assert.match(h, /<p class="cn-trust">.*У теці є зміни/s);
  const r = cardHTML(own({ trust: "refused", status: "error", trust_error: "symlink", error: "symlink: a" }), new Map());
  assert.match(r, /data-cn="trustinfo"/);
  assert.match(r, /class="cn-why".*У теці є символьне посилання/s);
});

test("connPageHTML: примітки під головою — лише коли є", () => {
  const sp = { id: "alpha", name: "Alpha", path: "~/work/alpha", capabilities: { publish: null, comments: null, tokens: null } };
  const base = { space: sp, list: [own()], failed: null, busy: new Map() };
  assert.doesNotMatch(connPageHTML({ ...base, notes: [] }), /cn-notes/);
  assert.doesNotMatch(connPageHTML(base), /cn-notes/, "без поля notes — як до 3c");
  const h = connPageHTML({ ...base, notes: [{ folder: "modules/<b>", code: "id-taken" }] });
  assert.match(h, /<ul class="cn-notes"><li class="cn-note">/);
  assert.match(h, /modules\/&lt;b&gt;/);
  assert.match(h, /Агент може написати свій модуль/, "речення для агента");
});

test("drawerHTML: «Забрати довіру» лише у свого модуля з записом довіри", () => {
  const d = (entry) => drawerHTML({ entry, mode: "edit", fields: [], form: { values: {}, erase: [] }, busy: false,
    result: null, errors: {}, spaceName: "S" });
  assert.match(d(own({ record: true, runs: true, trust: "trusted", status: "ok", enabled: true })), /data-cn-dr="untrust"/);
  assert.doesNotMatch(d(own({ record: false })), /data-cn-dr="untrust"/);
  assert.doesNotMatch(d(builtin({ record: true })), /data-cn-dr="untrust"/);
});

test("словник: кожен ключ, який віддає модель для своїх модулів, є в обох мовах", () => {
  const keys = new Set(["cnCustom", "cnBadgeUntrusted", "cnTrust", "cnTrustInfo", "cnUntrust", "cnUntrustAsk", "cnUntrustRole", "cnNowWaiting",
    "cnUntrustKeeps", "cnToastTrusted", "cnToastUntrusted", "cnAgentOwn", "trWhyOther"]);
  for (const c of ["symlink", "hardlink", "special-file", "too-many-files", "too-big", "too-deep", "bad-name", "unreadable",
    "unstable", "bad-manifest", "snapshot-damaged", "trust-unreadable"]) keys.add(trustWhyKey(c));
  for (const e of [own({ enabled: true }), own({ trust: "changed", runs: true }), own({ trust: "refused", runs: true, trust_error: "x" }),
    own({ trust_error: "snapshot-damaged" }), own({ trust_error: "trust-unreadable" })]) {
    const w = whyOf(e); if (w) keys.add(w.key);
    const l = trustLine(e); if (l) { keys.add(l.key); if (l.why) keys.add(l.why); }
  }
  for (const n of noteView(["id-taken", "too-many-modules", "modules-link", "modules-unreadable", "?"].map((code) => ({ folder: "f", code })))) keys.add(n.key);
  for (const code of ["module-untrusted", "module-changed", "module-refused", "trust-needs-ui", "trust-declined", "trust-no-confirm",
    "trust-busy", "trust-unreadable"]) keys.add(refusalView({ code }).key);
  assert.ok(keys.size >= 40, `зібрано лише ${keys.size}`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа «${k}»`);
});
```

Допиши в `tests/css-guards.test.mjs` (у секцію пар, після тесту `--muted на --bg і на --card`):

```js
test("свої модулі (3c): замок «Потрібна довіра» — --open на --s2 і --s3 >= 3:1; «Забрати довіру» в діалозі — --bad-ink на --g50 >= 4.5:1", () => {
  for (const bg of ["s2", "s3"]) {
    const { a, b, ratio } = pairRatio("open", bg);
    assert.ok(ratio >= 3, `--open (${a}) на --${bg} (${b}) дає ${ratio.toFixed(2)}:1`);
  }
  const { a, b, ratio } = pairRatio("bad-ink", "g50");
  assert.ok(ratio >= 4.5, `--bad-ink (${a}) на --g50 (${b}) дає ${ratio.toFixed(2)}:1`);
});
```

Допиши в `tests/connections-wiring.test.mjs`:

```js
test("3c: примітки своїх модулів — зі списку модулів у стан сторінки; зміна простору їх чистить", () => {
  assert.match(src, /const connState = \{ spaceId: null, list: null, notes: \[\], failed: null, busy: new Map\(\), seq: 0 \};/);
  const b = fnc("loadConn");
  assert.match(b, /connState\.notes = Array\.isArray\(r\?\.notes\) \? r\.notes : \[\];/);
  assert.match(b, /connState\.list = null; connState\.notes = \[\];/, "інший простір — без чужих приміток");
  assert.match(src, /const connView = \(\) => \(\{ space: connSpace\(\), list: connState\.list, notes: connState\.notes,/);
});
```

У тому ж файлі ОНОВИ наявний пін тесту «loadConn: `spaces` вирішує, чи перечитувати простори…» (≈рядок 301): у регексі
гілки зміни простору `connState\.list = null; connState\.failed = null;` → `connState\.list = null; connState\.notes = \[\]; connState\.failed = null;`.
Інакше Step 5 його зламає: старий пін вимагає `failed = null` одразу після `list = null`, новий — `notes = []`.

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 120 1500 node --test tests/connections-own.test.mjs tests/css-guards.test.mjs tests/connections-wiring.test.mjs 2>&1 | tail -20`
Expected: FAIL (`isOwn` не експортовано, ключів нема тощо).

- [ ] **Step 3: Модель** — `app/connections-model.js`.

3a. У докстрінг файла (після абзацу про вхід) допиши: «Свої модулі простору (3c) мають у записі ще `custom: true`, `trust` (`untrusted|trusted|changed|refused`), `record`, `runs` (чи виконується тут їхній код), `source`, `trust_error?`; `GET /api/modules` може нести `notes` (`[{folder, code}]`).»

3b. Після `builtinText` додай:

```js
/* ── свої модулі простору (етап 3c) ───────────────────────────────────────────────────────────────── */

/** Свій модуль простору: запис `GET /api/modules` з `custom: true` (вбудовані цього поля не мають). */
export const isOwn = (e) => e?.custom === true;
/** Код свого модуля виконується тут (робочий довірений знімок): `runs: true`. Недовірений і `refused` без знімка — ні. */
export const ownRuns = (e) => isOwn(e) && e.runs === true;

const TRUST_WHY = new Map([
  ["symlink", "trWhySymlink"], ["hardlink", "trWhyHardlink"], ["special-file", "trWhySpecial"],
  ["too-many-files", "trWhyTooMany"], ["too-big", "trWhyTooBig"], ["too-deep", "trWhyTooDeep"],
  ["bad-name", "trWhyBadName"], ["unreadable", "trWhyUnreadable"], ["unstable", "trWhyUnstable"],
  ["bad-manifest", "trWhyBadManifest"], ["snapshot-damaged", "trWhyDamaged"], ["trust-unreadable", "trWhyTrustFile"],
]);
/** Ключ словника причини `refused`/`untrusted` (код сервера `trust_error`, `refused.code`); невідомий — `trWhyOther`. */
export const trustWhyKey = (code) => TRUST_WHY.get(code) ?? "trWhyOther";

/**
 * Рядок довіри під описом картки свого модуля: `{key, why}` (`why` — ключ причини для шаблону або `null`) чи `null`.
 * `changed` — у теці є нова версія; `refused` зі знімком — нова версія не годиться, працює попередня; недовірений з
 * пошкодженим знімком — довіритись знову; файл довіри не читається — сказати це. `refused` без знімка — не тут: його
 * причина — у `whyOf` (картка без робочого коду).
 */
export function trustLine(e) {
  if (!isOwn(e)) return null;
  if (e.trust === "changed") return { key: "cnTrustChanged", why: null };
  if (e.trust === "refused" && ownRuns(e)) return { key: "cnTrustRefusedNew", why: trustWhyKey(e.trust_error) };
  if (e.trust_error === "snapshot-damaged") return { key: "cnTrustDamaged", why: null };
  if (e.trust_error === "trust-unreadable") return { key: "cnRefTrustUnreadable", why: null };
  return null;
}

const NOTE_KEYS = new Map([
  ["id-taken", "cnNoteIdTaken"], ["too-many-modules", "cnNoteTooMany"], ["modules-link", "cnNoteLink"],
  ["modules-unreadable", "cnNoteUnreadable"],
]);
/** Примітки `GET /api/modules` (`[{folder, code}]`) → `[{key, folder}]`; невідомий код — `cnNoteOther`, сміття — геть. */
export function noteView(notes) {
  return (Array.isArray(notes) ? notes : [])
    .filter((n) => n && typeof n.folder === "string" && typeof n.code === "string")
    .map((n) => ({ key: NOTE_KEYS.get(n.code) ?? "cnNoteOther", folder: n.folder }));
}
```

3c. `cardView` — заміни повністю:

```js
/**
 * Картка: бейдж (`missing|off|ok|unchecked|error|untrusted`), дії (`enable|configure|check|disable|trust|trustinfo`), чи
 * показувати причину. Вбудований — рівно як до 3c. Свій модуль без робочого коду: недовірений — «Потрібна довіра» і
 * «Довіритись…», `refused` без знімка — «Помилка» і «Чому не можна…» (+ «Вимкнути», коли ввімкнений). Свій зі знімком —
 * як вбудований, плюс «Довіритись…» для `changed` і «Чому не можна…» для `refused` (нова версія не годиться).
 */
export function cardView(e) {
  if (e?.status === "missing") return { badge: "missing", actions: ["disable"], why: true, implicit: false };
  if (isOwn(e) && !ownRuns(e)) {
    const off = e.enabled === true ? ["disable"] : [];
    if (e.trust === "refused") return { badge: "error", actions: ["trustinfo", ...off], why: true, implicit: false };
    return { badge: "untrusted", actions: ["trust", ...off], why: e.enabled === true, implicit: false };
  }
  let v;
  if (!e?.enabled) v = { badge: "off", actions: ["enable"], why: false, implicit: false };
  else {
    const badge = e.status === "ok" ? "ok" : e.status === "error" ? "error" : "unchecked";
    v = { badge, actions: ["configure", "check", "disable"], why: badge === "error", implicit: e.implicit === true };
  }
  if (isOwn(e) && e.trust === "changed") v.actions.push("trust");
  else if (isOwn(e) && e.trust === "refused") v.actions.push("trustinfo");
  return v;
}
```

3d. `whyOf` — після рядка `if (e.status === "missing") …` встав:

```js
  if (isOwn(e) && !ownRuns(e)) {
    /* Свій без робочого коду: `refused` — причина й деталь сервера; недовірений — лише коли ввімкнений (роль не працює). */
    if (e.trust === "refused") return { key: trustWhyKey(e.trust_error), detail: clip(e.error) };
    return e.enabled === true ? { key: "cnTrustNeededWhy", detail: "" } : null;
  }
```

(`clip` оголошено вище за `whyOf` — так і лишається.)

3e. `REFUSAL_KEYS` — допиши пари:

```js
  ["module-untrusted", "cnRefUntrusted"], ["module-changed", "cnRefChanged"], ["module-refused", "cnRefRefused"],
  ["trust-needs-ui", "cnRefNeedsUi"], ["trust-declined", "cnRefDeclined"], ["trust-no-confirm", "cnRefNoConfirm"],
  ["trust-busy", "cnRefBusy"], ["trust-unreadable", "cnRefTrustUnreadable"],
```

3f. `providerLine` — гілку «роль без постачальника» заміни на:

```js
  if (typeof v !== "string" || !v) {
    /* Роль «на папері» за увімкненим своїм модулем, що тут не працює (3c): сервер віддає `null` без `error`
       (поправка 11), але це не «нікого» — роль чекає довіри. */
    const waiting = (Array.isArray(list) ? list : []).find((x) => x && x.enabled === true && isOwn(x) && !ownRuns(x)
      && Array.isArray(x.roles) && x.roles.includes(role));
    if (waiting) return { kind: "waiting", id: waiting.id, entry: waiting };
    return { kind: "none", noneKey: roleKeys(role)?.none ?? null };
  }
```

і в його докстрінг — `{kind: 'waiting', id, entry}`.

`roleHolders` НЕ змінюється (поправка 3).

- [ ] **Step 4: Розмітка** — `app/connections-view.js`.

4a. Імпорт моделі: додай `isOwn, noteView, trustLine` (за абеткою в наявному списку). У шапці файла `connPageHTML(v)`: `v = {space, list, notes, failed, busy}`; `notes — примітки своїх модулів (`GET /api/modules`), може не бути`; `busy` — ще й `'trust'`.

4b. `BADGES` — додай `untrusted: ["cnBadgeUntrusted", "lock"],`. `ACTIONS` — додай:

```js
  trust: ["cnTrust", "lock", "ctl ctl--out"],
  trustinfo: ["cnTrustInfo", "help", "ctl"],
```

4c. Після `whyHTML`:

```js
/** Пігулка «свій» (свій модуль простору; підказка — його тека в просторі). */
export const ownTagHTML = (e) => (isOwn(e)
  ? `<span class="cn-tag cn-tag--own" title="${esc(String(e.source || ""))}">${esc(t("cnCustom"))}</span>` : "");

/** Текст рядка довіри (`trustLine` моделі) мовою інтерфейсу або `""`. Спільний з кроком 2 майстра. */
export function trustLineText(e) {
  const l = trustLine(e);
  return l ? (l.why ? t(l.key, t(l.why)) : t(l.key)) : "";
}

/** Рядок довіри під описом картки або `""`. */
export function trustLineHTML(e) {
  const s = trustLineText(e);
  return s ? `<p class="cn-trust">${ico("lock", 13)}<span>${esc(s)}</span></p>` : "";
}
```

4d. `cardHTML`: у шапці після пігулки «типово» — `${ownTagHTML(e)}`; рядок опису замінити на

```js
    ${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}${trustLineHTML(e)}
```

4e. `nowHTML` — гілка `waiting` перед `none`:

```js
  const txt = p.kind === "legacy" ? t("cnNowLegacy")
    : p.kind === "error" ? t("cnNowError")
      : p.kind === "waiting" ? t("cnNowWaiting", modName(p.entry))
        : p.kind === "none" ? (p.noneKey ? t("cnNowNone", t(p.noneKey)) : t("cnNowNobody"))
          : t("cnNow", p.entry ? modName(p.entry) : p.id);
```

4f. `agentHTML` — перед закриттям `</div></div>` додай `<span class="cn-agent-own">${esc(t("cnAgentOwn"))}</span>`.

4g. `connPageHTML` — перед `export function connPageHTML`:

```js
/** Примітки своїх модулів (`notes` відповіді) рядками під головою; нема — `""`. */
function notesHTML(notes) {
  const list = noteView(notes);
  if (!list.length) return "";
  return `<ul class="cn-notes">${list.map((n) => `<li class="cn-note">${ico("warn", 13)}`
    + `<span>${esc(t(n.key, n.folder))}</span></li>`).join("")}</ul>`;
}
```

і останній `return` функції: `return wrap(\`${notesHTML(v.notes)}${sections.map(…).join("")}${miss}${agentHTML(sp)}\`);`.

4h. `drawerHTML` — у `.cn-dr-foot` ПЕРШИМ (ліворуч, до кнопки «Перевірити»):

```js
${isOwn(e) && e.record === true
      ? `<button type="button" class="ctl ctl--out cn-dr-untrust" data-cn-dr="untrust"${d.busy ? " disabled" : ""}>${ico("trash")}${esc(t("cnUntrust"))}</button>` : ""}
```

- [ ] **Step 5: Стан сторінки** — `app/app.js`.

- рядок `connState`: `const connState = { spaceId: null, list: null, notes: [], failed: null, busy: new Map(), seq: 0 };` і в коментарі над ним — «`notes` — примітки своїх модулів простору (3c)»; у коментарі `busy` (якщо перелічені дії) — ще `'trust'`.
- `connView`: `const connView = () => ({ space: connSpace(), list: connState.list, notes: connState.notes, failed: connState.failed, busy: connState.busy });`
- `loadConn`, гілка зміни простору: `connState.spaceId = sp.id; connState.list = null; connState.notes = []; connState.failed = null; connState.busy.clear();`
- `loadConn`, успіх: після `connState.list = …` — `connState.notes = Array.isArray(r?.notes) ? r.notes : [];`

- [ ] **Step 5′: Відмова публікації `module-untrusted`** (ревʼю Task 4: з Task 4 `POST /api/publish` для ввімкненого
недовіреного свого модуля дає 409 `module-untrusted`, а клієнт показав би загальне «Не вдалося: …») — `app/spaces-model.js`,
`PUBLISH_ERR_KEYS`: після `["module-error", "publishErrModule"]` додай `["module-untrusted", "publishErrUntrusted"]`
(без тексту сервера: `publishErr` дасть `{key, args: []}`). У `app/i18n.js` поруч із `publishErrModule`:
UK `publishErrUntrusted: 'Модуль публікації цього простору чекає довіри на цьому компʼютері — відкрийте «Підключення».',`
(апостроф — U+02BC, як у решті словника), EN `publishErrUntrusted: "This space's publish module is waiting for your trust on this computer — open Connections.",`.
Тест — у `tests/connections-own.test.mjs`: `publishErr({ code: 'module-untrusted', status: 409 })` →
`{ key: 'publishErrUntrusted', args: [] }` (імпорт із `../app/spaces-model.js`), і ключ є в обох словниках.

- [ ] **Step 6: Словник** — `app/i18n.js`, після `cnTimeout` в `UK`:

```js
  /* Свої модулі простору (етап 3c): картки, примітки, відмови довіри */
  cnCustom: 'свій',
  cnNowWaiting: (name) => `Зараз: «${name}» — чекає довіри на цьому компʼютері`,
  cnBadgeUntrusted: 'Потрібна довіра',
  cnTrust: 'Довіритись…',
  cnTrustInfo: 'Чому не можна…',
  cnTrustNeededWhy: 'Модуль увімкнено в просторі, але на цьому компʼютері йому не довірено — його роль не працює.',
  cnTrustChanged: 'У теці є зміни — довіртесь, щоб їх застосувати.',
  cnTrustRefusedNew: (why) => `Нову версію теки не можна довірити. ${why} Працює попередня.`,
  cnTrustDamaged: 'Знімок модуля пошкоджено — довіртесь знову.',
  cnUntrust: 'Забрати довіру',
  cnUntrustAsk: (name) => `Забрати довіру до «${name}»? Його код більше не виконуватиметься на цьому компʼютері.`,
  cnUntrustRole: (roles) => `Роль «${roles}» не працюватиме, доки ви не довіритесь знову чи не підключите інший модуль.`,
  cnUntrustKeeps: 'Простір і його налаштування не зміняться.',
  cnToastTrusted: (name) => `Довірено: ${name}`,
  cnToastUntrusted: (name) => `Довіру забрано: ${name}`,
  cnAgentOwn: 'Агент може написати свій модуль у теці modules/ простору — довіритись йому зможете лише ви.',
  cnNoteIdTaken: (folder) => `${folder}: такий id уже має вбудований модуль — теку пропущено.`,
  cnNoteTooMany: (folder) => `${folder}: забагато своїх модулів у просторі (понад 32) — теку пропущено.`,
  cnNoteLink: (folder) => `${folder}: це посилання, а не тека — свої модулі не завантажено.`,
  cnNoteUnreadable: (folder) => `${folder}: тека не читається — свої модулі не завантажено.`,
  cnNoteOther: (folder) => `${folder}: теку пропущено.`,
  cnRefUntrusted: 'Модуль не довірено на цьому компʼютері.',
  cnRefChanged: 'Тека модуля змінилась, поки був відкритий діалог. Перегляньте ще раз.',
  cnRefRefused: 'Цій теці не можна довіритись.',
  cnRefNeedsUi: 'Довіритись можна лише з канваса на localhost у браузері, що шле Sec-Fetch-Site (Safari — від 16.4).',
  cnRefDeclined: 'Довіру не підтверджено в системному вікні.',
  cnRefNoConfirm: 'Не вдалося показати системне вікно підтвердження (нема графічної сесії?). Довіра можлива лише з нього.',
  cnRefBusy: 'Уже відкрито інше системне вікно підтвердження.',
  cnRefTrustUnreadable: 'Файл довіри не читається — перевірте ~/.deai/trust.json.',
  trWhySymlink: 'У теці є символьне посилання.',
  trWhyHardlink: 'У теці є жорстке посилання.',
  trWhySpecial: 'У теці є спеціальний файл (не звичайний файл і не тека).',
  trWhyTooMany: 'У теці забагато файлів (понад 200).',
  trWhyTooBig: 'Тека завелика (понад 5 МіБ).',
  trWhyTooDeep: 'Забагато вкладених тек (понад 8).',
  trWhyBadName: 'У теці є файл з недопустимим імʼям.',
  trWhyUnreadable: 'Файл чи тека не читається.',
  trWhyUnstable: 'Файл змінювався під час читання — спробуйте ще раз.',
  trWhyBadManifest: 'module.json не читається чи неповний.',
  trWhyDamaged: 'Знімок модуля пошкоджено.',
  trWhyTrustFile: 'Файл довіри не читається.',
  trWhyOther: 'Тека не годиться для модуля.',
```

і в `EN` після `cnTimeout`:

```js
  /* Own space modules (stage 3c): cards, notes, trust refusals */
  cnCustom: 'own',
  cnNowWaiting: (name) => `Now: “${name}” — waiting for trust on this computer`,
  cnBadgeUntrusted: 'Needs trust',
  cnTrust: 'Trust…',
  cnTrustInfo: 'Why not…',
  cnTrustNeededWhy: 'The module is on in this space, but it is not trusted on this computer — its role does not work.',
  cnTrustChanged: 'The folder has changes — trust them to apply.',
  cnTrustRefusedNew: (why) => `The new version of the folder cannot be trusted. ${why} The previous one keeps running.`,
  cnTrustDamaged: 'The module snapshot is damaged — trust it again.',
  cnUntrust: 'Revoke trust',
  cnUntrustAsk: (name) => `Revoke trust in “${name}”? Its code will no longer run on this computer.`,
  cnUntrustRole: (roles) => `The “${roles}” role will not work until you trust it again or connect another module.`,
  cnUntrustKeeps: 'The space and its settings stay as they are.',
  cnToastTrusted: (name) => `Trusted: ${name}`,
  cnToastUntrusted: (name) => `Trust revoked: ${name}`,
  cnAgentOwn: 'The agent can write an own module in the space’s modules/ folder — only you can trust it.',
  cnNoteIdTaken: (folder) => `${folder}: a built-in module already has this id — folder skipped.`,
  cnNoteTooMany: (folder) => `${folder}: too many own modules in the space (over 32) — folder skipped.`,
  cnNoteLink: (folder) => `${folder}: this is a link, not a folder — own modules were not loaded.`,
  cnNoteUnreadable: (folder) => `${folder}: the folder cannot be read — own modules were not loaded.`,
  cnNoteOther: (folder) => `${folder}: folder skipped.`,
  cnRefUntrusted: 'The module is not trusted on this computer.',
  cnRefChanged: 'The module folder changed while the dialog was open. Review it again.',
  cnRefRefused: 'This folder cannot be trusted.',
  cnRefNeedsUi: 'Trust can be granted only from the canvas on localhost in a browser that sends Sec-Fetch-Site (Safari 16.4 or later).',
  cnRefDeclined: 'Trust was not confirmed in the system window.',
  cnRefNoConfirm: 'Could not show the system confirmation window (no graphical session?). Trust is possible only through it.',
  cnRefBusy: 'Another system confirmation window is already open.',
  cnRefTrustUnreadable: 'The trust file cannot be read — check ~/.deai/trust.json.',
  trWhySymlink: 'The folder contains a symbolic link.',
  trWhyHardlink: 'The folder contains a hard link.',
  trWhySpecial: 'The folder contains a special file (neither a regular file nor a folder).',
  trWhyTooMany: 'The folder has too many files (over 200).',
  trWhyTooBig: 'The folder is too big (over 5 MiB).',
  trWhyTooDeep: 'Too many nested folders (over 8).',
  trWhyBadName: 'The folder contains a file with a forbidden name.',
  trWhyUnreadable: 'A file or folder cannot be read.',
  trWhyUnstable: 'A file changed while it was being read — try again.',
  trWhyBadManifest: 'module.json cannot be read or is incomplete.',
  trWhyDamaged: 'The module snapshot is damaged.',
  trWhyTrustFile: 'The trust file cannot be read.',
  trWhyOther: 'The folder does not fit a module.',
```

- [ ] **Step 7: Стилі** — `app/styles.css`, після правил `.cn-agent …`:

```css
/* Свої модулі простору (3c): пігулка «свій», бейдж «Потрібна довіра» (замок бурштиновий, як «чекає дії»), рядок довіри,
   примітки під головою, речення для агента, «Забрати довіру» в панелі (текст світлий — `--bad` на `--s2` дає лише 4.1:1). */
.cn-tag--own{border-color:var(--mid);color:var(--mid)}
.cn-badge--untrusted{color:var(--hi)}
.cn-badge--untrusted .ico{color:var(--open)}
.cn-trust{display:flex;align-items:flex-start;gap:6px;margin:0;font-size:12px;line-height:1.4;color:var(--mid)}
.cn-trust .ico{flex:none;margin-top:1px;color:var(--open)}
.cn-notes{display:flex;flex-direction:column;gap:6px;margin:12px 0 0;padding:0;list-style:none}
.cn-note{display:flex;align-items:flex-start;gap:8px;font-size:12.5px;line-height:1.4;color:var(--mid);overflow-wrap:anywhere}
.cn-note .ico{flex:none;margin-top:1px;color:var(--open)}
.cn-agent-own{display:block;margin-top:8px;color:var(--mid)}
.cn-dr-untrust{border-color:var(--bad);color:var(--hi)}
.cn-dr-untrust .ico{color:var(--bad)}
```

- [ ] **Step 8: Прогін — зелені + увесь клієнт**

Run: `python3 "$G" 300 2500 node --test tests/*.test.mjs 2>&1 | tail -15`
Expected: PASS, зокрема `connections-css.test.mjs` (кожен клас `cn-` має правило), `i18n-keys.test.mjs`, `i18n-literals.test.mjs`, `legacy-golden.test.mjs` (БЕЗ `UPDATE_GOLDEN=1`).

- [ ] **Step 9: Мутації** (по одній, файл відновлюється побайтно: `git diff --stat` порожній після відкату)

| мутація | має впасти |
|---|---|
| `cardView`: прибрати гілку `isOwn(e) && !ownRuns(e)` | `cardView: кожен стан таблиці` |
| `cardView`: прибрати `v.actions.push("trust")` | той самий |
| `cardView`: `isOwn(e)` → `e?.trust` (свій за полем `trust`) | `cardView вбудованого — рівно як до 3c` |
| `whyOf`: прибрати гілку свого | `whyOf: …` |
| `trustLine`: прибрати `&& ownRuns(e)` | `trustLine: …` |
| `noteView`: прибрати `.filter(...)` | `noteView: …` |
| `providerLine`: прибрати пошук `waiting` | `providerLine: роль «на папері»…` |
| `notesHTML`: повертати `<ul class="cn-notes"></ul>` для порожнього | `connPageHTML: примітки…` |
| `drawerHTML`: умова кнопки без `e.record === true` | `drawerHTML: «Забрати довіру»…` |
| `ownTagHTML`: `esc(String(e.source…))` → `String(e.source…)` | `cardHTML: пігулка «свій»…` |
| `loadConn`: прибрати `connState.notes = []` у гілці зміни простору | `3c: примітки…` (wiring) |

- [ ] **Step 10: Коміт**

```bash
git add app/connections-model.js app/connections-view.js app/app.js app/i18n.js app/styles.css \
  tests/connections-own.test.mjs tests/css-guards.test.mjs tests/connections-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): «Підключення» — картки своїх модулів, стани довіри, примітки

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: діалог довіри — `trust-view.js`, `openTrust`, «Забрати довіру»

**Files:**
- Create: `app/trust-view.js`, `tests/trust-view.test.mjs`
- Modify: `app/app.js` (імпорти ≈54; `connAction` ≈2697; нова секція «довіра своєму модулю» після `afterModulesChange` ≈2800; `wireCnDrawer` ≈3134; новий `cnDrawerUntrust` після `cnDrawerCheck`)
- Modify: `app/i18n.js` (`UK`/`EN` — після блоку 3c з Task 6), `app/styles.css` (після правил `.cv-form-err`/`.cv-field input[aria-invalid]`)
- Modify: `tests/connections-wiring.test.mjs`

- [ ] **Step 1: Тести (червоні)** — створи `tests/trust-view.test.mjs`:

```js
/**
 * Діалог довіри своєму модулю (Deai 0.7.0, етап 3c; спека, «Діалог довіри»): розмітка `trustDialogHTML` для `askForm`
 * (контракт форми, фокус на «Скасувати», екранування всього з диска, обрізання до 80, позначки змін, режим `refused`),
 * `sizeText`, стеля запиту довіри, правила CSS і словник.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import { TR_MAX, TRUST_POST_TIMEOUT_MS, sizeText, trustDialogHTML } from "../app/trust-view.js";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const base = (over = {}) => ({
  id: "acme", name: "Acme", version: "1.2", roles: ["publish"], path: "~/work/alpha/modules/acme",
  state: "untrusted", record: false, hash: "ab".repeat(32),
  settings: [{ key: "token", type: "secret", label: "Token", public: false }, { key: "site", type: "text", label: "Site id" }],
  files: [{ path: "module.json", size: 120, change: "new" }, { path: "server.py", size: 12034, change: "new" }],
  removed: [], total: { files: 2, bytes: 12154 }, ...over,
});

test("контракт askForm: один form-діалог, «Довіряю» — submit data-a=ok, «Скасувати» — data-a=cancel з ЄДИНИМ data-autofocus", () => {
  const h = trustDialogHTML(base());
  assert.equal((h.match(/<form/g) || []).length, 1);
  assert.match(h, /<form class="cv-form tr" novalidate role="dialog" aria-modal="true" aria-labelledby="tr-h">/);
  assert.match(h, /<h2 class="cv-form-h" id="tr-h">Довіритись модулю «Acme»\?<\/h2>/);
  assert.match(h, /<button type="submit" data-a="ok">Довіряю<\/button>/);
  assert.match(h, /<button type="button" data-a="cancel" data-autofocus>Скасувати<\/button>/);
  assert.equal((h.match(/data-autofocus/g) || []).length, 1, "Enter, натиснутий не дивлячись, не довіряє");
  assert.match(h, /<p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden><\/p>/);
  assert.match(h, /<p class="tr-wait" data-tr-wait role="status" hidden>Підтвердіть у системному вікні…<\/p>/);
  assert.doesNotMatch(h, /data-tr="untrust"/, "без запису довіри забирати нічого");
});

test("зміст: версія й ролі, шлях, відбиток 12 знаків, попередження, «Просить» з позначками секретів, файли з розмірами", () => {
  const h = trustDialogHTML(base({ settings: [
    { key: "token", type: "secret", label: "Token", public: false },
    { key: "anon", type: "secret", label: "Anon key", public: true },
    { key: "site", type: "text", label: "Site id" },
  ] }));
  assert.match(h, /<p class="tr-meta">v1\.2 · Публікація<\/p>/);
  assert.match(h, /<code>~\/work\/alpha\/modules\/acme<\/code> · Відбиток abababababab</);
  assert.match(h, /class="tr-warn".*з вашими правами.*Після «Довіряю» система попросить/s);
  assert.doesNotMatch(h, /сторінках канваса/, "попередження про JavaScript — лише для ролі comments");
  assert.match(h, /<li>Token <span class="tr-mark">секрет<\/span><\/li>/);
  assert.match(h, /<li>Anon key <span class="tr-mark">публічний \(потрапляє в сторінки\)<\/span><\/li>/);
  assert.match(h, /<li>Site id<\/li>/);
  assert.match(h, /Файли \(2, 11,9 КБ\)/);
  assert.match(h, /<ul class="tr-files" tabindex="0" aria-label="Файли модуля">/);
  assert.match(h, /<code>server\.py<\/code><span class="tr-size">11,8 КБ<\/span><\/li>/);
  assert.doesNotMatch(h, /tr-mark">новий/, "без запису довіри «новий» — кожен файл, позначка нічого не каже");
  assert.match(trustDialogHTML(base({ settings: [] })), /<p class="tr-none">Налаштувань не просить\.<\/p>/);
  assert.match(trustDialogHTML(base({ roles: ["comments"] })), /Його JavaScript виконуватиметься в сторінках канваса/);
});

test("нова версія: свій заголовок, лічильник змін, позначки «новий»/«змінено», рядок «Прибрано»; запис — кнопка «Забрати довіру»", () => {
  const h = trustDialogHTML(base({ state: "changed", record: true,
    files: [{ path: "module.json", size: 1, change: "same" }, { path: "server.py", size: 2, change: "changed" },
      { path: "new.js", size: 3, change: "new" }],
    removed: [{ path: "old.js", size: 9 }], total: { files: 3, bytes: 6 } }));
  assert.match(h, /id="tr-h">Довіритись новій версії «Acme»\?</);
  assert.match(h, /Файли \(3, 6 Б\) · змінено від минулої довіри: 3/);
  assert.match(h, /<code>server\.py<\/code><span class="tr-size">2 Б<\/span><span class="tr-mark">змінено<\/span>/);
  assert.match(h, /<code>new\.js<\/code><span class="tr-size">3 Б<\/span><span class="tr-mark">новий<\/span>/);
  assert.match(h, /<code>module\.json<\/code><span class="tr-size">1 Б<\/span><\/li>/, "незмінний — без позначки");
  assert.match(h, /<p class="tr-removed">Прибрано: old\.js<\/p>/);
  assert.match(h, /<button type="button" class="tr-untrust" data-tr="untrust">Забрати довіру<\/button>/);
});

test("refused: без «Довіряю» й попередження, причина і деталь, «Закрити» з фокусом; «Забрати довіру» — якщо запис є", () => {
  const h = trustDialogHTML({ id: "acme", name: "Acme", version: "1", roles: ["publish"], path: "~/m/acme", state: "refused",
    record: true, refused: { code: "symlink", detail: "alias.py: symbolic link" } });
  assert.doesNotMatch(h, /data-a="ok"|tr-warn|Відбиток|tr-files/);
  assert.match(h, /<p class="tr-refused" role="alert">.*Цій теці не можна довіритись\. У теці є символьне посилання\.<span class="cn-why-detail">alias\.py: symbolic link<\/span>/s);
  assert.match(h, /<button type="button" data-a="cancel" data-autofocus>Закрити<\/button>/);
  assert.match(h, /data-tr="untrust"/);
  assert.match(trustDialogHTML({ id: "x", state: "refused", refused: { code: "zzz" } }), /Тека не годиться для модуля\./);
});

test("усе з диска — текст: <img onerror> у назві, шляху, файлі, мітці й деталі не стає тегом; рядки обрізано до TR_MAX", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const h = trustDialogHTML(base({ name: evil, version: evil, path: evil, settings: [{ key: "k", type: "text", label: evil }],
    files: [{ path: evil, size: 1, change: "new" }], removed: [{ path: evil, size: 1 }], record: true }));
  assert.doesNotMatch(h, /<img/);
  assert.match(h, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  const r = trustDialogHTML({ id: "x", state: "refused", refused: { code: "symlink", detail: evil } });
  assert.doesNotMatch(r, /<img/);
  const long = "n".repeat(200);
  const l = trustDialogHTML(base({ name: long, files: [{ path: `${long}.py`, size: 1, change: "new" }] }));
  assert.ok(l.includes(`«${"n".repeat(TR_MAX - 1)}…»`), "назва обрізана");
  assert.ok(l.includes(`<code>${"n".repeat(TR_MAX - 1)}…</code>`), "імʼя файла обрізане");
  assert.equal(TR_MAX, 80);
});

test("повторне відкриття: рядок угорі «Тека змінилась…»", () => {
  assert.match(trustDialogHTML(base({ reopened: true })), /<p class="tr-reopened" role="status">Тека змінилась, поки діалог був відкритий/);
  assert.doesNotMatch(trustDialogHTML(base()), /tr-reopened/);
});

test("sizeText: байти до 1 КБ, далі КБ / МБ з однією цифрою після коми", () => {
  assert.equal(sizeText(0), "0 Б");
  assert.equal(sizeText(1023), "1023 Б");
  assert.equal(sizeText(1024), "1,0 КБ");
  assert.equal(sizeText(12154), "11,9 КБ");
  assert.equal(sizeText(5 * 1024 * 1024), "5,0 МБ");
  assert.equal(sizeText("сміття"), "0 Б");
  assert.equal(sizeText(-5), "0 Б");
});

test("стеля запиту довіри довша за 120 с системного вікна сервера, але скінченна", () => {
  assert.ok(TRUST_POST_TIMEOUT_MS > 120000 && TRUST_POST_TIMEOUT_MS <= 180000, String(TRUST_POST_TIMEOUT_MS));
});

test("кожен клас tr-* розмітки має правило в styles.css", () => {
  const src = read("trust-view.js").replace(/\/\*[\s\S]*?\*\//g, "");
  const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) for (const c of m[1].split(/\s+/)) if (/^tr-/.test(c)) classes.add(c);
  assert.ok(classes.size >= 12, `знайдено лише ${classes.size}: ${[...classes]}`);
  const missing = [...classes].filter((c) => !new RegExp(`\\.${c}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], `класи без правила: ${missing.join(", ")}`);
});

test("словник: кожен ключ, який кличе trust-view.js, є в обох мовах", () => {
  const keys = new Set([...read("trust-view.js").matchAll(/\bt\("(\w+)"/g)].map((m) => m[1]));
  assert.ok(keys.size >= 15, `зібрано лише ${keys.size}`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає «${k}»`);
});
```

Допиши в `tests/connections-wiring.test.mjs`:

```js
test("3c: «Довіритись…» і «Чому не можна…» картки ведуть у connTrust; простір фіксується ДО діалогу", () => {
  assert.match(fnc("connAction"), /else if \(act === 'trust' \|\| act === 'trustinfo'\) connTrust\(e\);/);
  const b = fnc("connTrust");
  assert.ok(b.indexOf("const spaceId = connState.spaceId;") < b.indexOf("openTrust(e, spaceId)"));
});

test("3c: openTrust — свіжі дані, діалог, довіра через trustPost (своя стеля); module-changed — знову з позначкою; «Забрати довіру» — після закриття", () => {
  const b = fnc("openTrust");
  assert.match(b, /formApi\(`\/api\/module-trust\?space=\$\{encodeURIComponent\(spaceId\)\}&id=\$\{encodeURIComponent\(entry\.id\)\}`\)/);
  assert.match(b, /askForm\(\(\) => trustDialogHTML\(\{ \.\.\.d, reopened \}\)/);
  assert.match(b, /trustPost\(\{ space: spaceId, id: d\.id, hash: d\.hash, lang: getLang\(\) \}\)/);
  assert.match(b, /if \(err\?\.code === 'module-changed'\) \{ again = true; return undefined; \}/);
  assert.match(b, /if \(again\) \{ reopened = true; continue; \}/);
  assert.match(b, /if \(form\.getAttribute\('aria-busy'\) === 'true'\) return;/, "під час запиту «Забрати довіру» нічого не позначає");
  assert.ok(b.indexOf("await askForm(") < b.indexOf("untrustFlow(entry, spaceId)"), "питання — лише після закриття діалогу");
  assert.match(b, /await afterModulesChange\(\);/);
  const p = fnc("trustPost");
  assert.match(p, /setTimeout\(\(\) => ctl\.abort\(\), TRUST_POST_TIMEOUT_MS\)/);
  assert.match(p, /\.finally\(\(\) => clearTimeout\(timer\)\)/);
  assert.match(src, /import \{ TRUST_POST_TIMEOUT_MS, trustDialogHTML \} from '\.\/trust-view\.js';/);
});

test("3c: «Забрати довіру» — небезпечне питання, запит у зафіксований простір, далі afterModulesChange; у панелі — модуль і простір ДО її закриття", () => {
  const u = fnc("untrustFlow");
  assert.match(u, /askYesNo\(lines\.join\('\\n\\n'\), \{ yes: t\('cnUntrust'\), danger: true \}\)/);
  assert.match(u, /postForm\('\/api\/module-untrust', \{ space: spaceId, id: entry\.id \}\)/);
  assert.ok(u.indexOf("askYesNo(") < u.indexOf("postForm("));
  assert.match(u, /await afterModulesChange\(\);/);
  const d = fnc("cnDrawerUntrust");
  assert.ok(d.indexOf("const { entry, spaceId } = cnDrawer;") < d.indexOf("dismissCnDrawer()"));
  assert.match(fnc("wireCnDrawer"), /else if \(a === 'untrust'\) cnDrawerUntrust\(\);/);
});
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 120 1500 node --test tests/trust-view.test.mjs tests/connections-wiring.test.mjs 2>&1 | tail -20`
Expected: FAIL (`trust-view.js` нема, функцій нема).

- [ ] **Step 3: `app/trust-view.js`** (новий):

```js
/**
 * Діалог довіри своєму модулю простору (Deai 0.7.0, етап 3c; спека
 * `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`, «Діалог довіри»). Чиста розмітка для `askForm`
 * (`app/ask.js`), як `space-dialogs.js`: ні DOM, ні fetch. Проводку (запит довіри, повторне відкриття, «Забрати
 * довіру») дає `openTrust` в `app.js`.
 *
 *   trustDialogHTML(d)  d — `trust` з `GET /api/module-trust` ({id, name, version, roles, settings, path, state, record,
 *                       refused?, hash?, files?, removed?, total?}) + `reopened` (тека змінилась, поки діалог був відкритий).
 *
 * Контракт `askForm`: один `<form role="dialog" aria-modal="true" aria-labelledby="tr-h">`; «Довіряю» —
 * `button[type=submit][data-a=ok]`; «Скасувати»/«Закрити» — `data-a=cancel` з `data-autofocus` (інакше фокус ліг би на
 * першу кнопку, і Enter, натиснутий не дивлячись, довіряв би); слот помилки `[data-form-error]`; рядок очікування
 * системного вікна `[data-tr-wait]`; «Забрати довіру» — `data-tr="untrust"`.
 *
 * ⛔ Усе з диска (назва, версія, шлях, імена файлів, мітки налаштувань, деталь відмови) — лише через `esc()` і обрізане
 * до `TR_MAX`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { trustWhyKey } from "./connections-model.js";
import { roleTitle } from "./connections-view.js";

/** Найдовший рядок із диска в діалозі. */
export const TR_MAX = 80;
/** Стеля запиту довіри: сервер чекає людину в системному вікні до 120 с (`module_trust.CONFIRM_TIMEOUT`). */
export const TRUST_POST_TIMEOUT_MS = 150000;

const cut = (s) => {
  const v = String(s ?? "");
  return v.length > TR_MAX ? `${v.slice(0, TR_MAX - 1)}…` : v;
};
const list0 = (x) => (Array.isArray(x) ? x : []);

/** Розмір людині: до 1 КБ — байти, далі КБ чи МБ з однією цифрою після коми (роздільник — у словнику). */
export function sizeText(n) {
  const b = Math.max(0, Math.floor(Number(n) || 0));
  if (b < 1024) return t("trSizeB", String(b));
  if (b < 1024 * 1024) return t("trSizeKb", (b / 1024).toFixed(1));
  return t("trSizeMb", (b / (1024 * 1024)).toFixed(1));
}

function asksHTML(settings) {
  const items = list0(settings).filter((s) => s && typeof s.key === "string");
  if (!items.length) return `<p class="tr-none">${esc(t("trAsksNone"))}</p>`;
  return `<p class="tr-h3">${esc(t("trAsks"))}</p><ul class="tr-asks">${items.map((s) => {
    const mark = s.type === "secret"
      ? ` <span class="tr-mark">${esc(t(s.public === true ? "trSecretPublic" : "trSecret"))}</span>` : "";
    return `<li>${esc(cut(s.label || s.key))}${mark}</li>`;
  }).join("")}</ul>`;
}

/* Позначки «новий»/«змінено» — лише коли є запис довіри: без нього кожен файл «новий», і позначка нічого не каже. */
function filesHTML(d) {
  const files = list0(d.files).filter((f) => f && typeof f.path === "string");
  const removed = list0(d.removed).filter((f) => f && typeof f.path === "string");
  const marks = d.record === true;
  const changed = files.filter((f) => f.change === "new" || f.change === "changed").length + removed.length;
  const head = t("trFiles", Number(d.total?.files ?? files.length), sizeText(d.total?.bytes ?? 0))
    + (d.state === "changed" ? ` · ${t("trChangedCount", changed)}` : "");
  const rows = files.map((f) => {
    const m = marks && (f.change === "new" || f.change === "changed")
      ? `<span class="tr-mark">${esc(t(f.change === "new" ? "trNew" : "trChanged"))}</span>` : "";
    return `<li><code>${esc(cut(f.path))}</code><span class="tr-size">${esc(sizeText(f.size))}</span>${m}</li>`;
  }).join("");
  const gone = removed.length
    ? `<p class="tr-removed">${esc(t("trRemoved", removed.map((f) => cut(f.path)).join(", ")))}</p>` : "";
  return `<p class="tr-h3">${esc(head)}</p>`
    + `<ul class="tr-files" tabindex="0" aria-label="${esc(t("trFilesList"))}">${rows}</ul>${gone}`;
}

/** Діалог довіри. `state: refused` — без «Довіряю» й попередження: лише причина і «Закрити». */
export function trustDialogHTML(d) {
  const name = cut(d?.name || d?.id || "");
  const refused = d?.state === "refused";
  const title = d?.state === "changed" ? t("trTitleNew", name) : t("trTitle", name);
  const roles = list0(d?.roles).map((r) => cut(roleTitle(r))).join(" · ");
  const meta = [d?.version ? `v${cut(d.version)}` : "", roles].filter(Boolean).join(" · ");
  const print = !refused && d?.hash ? ` · ${esc(t("trFingerprint", String(d.hash).slice(0, 12)))}` : "";
  const body = refused
    ? `<p class="tr-refused" role="alert">${ico("warn", 13)}<span>${esc(t("trRefused", t(trustWhyKey(d.refused?.code))))}`
      + `${d.refused?.detail ? `<span class="cn-why-detail">${esc(cut(d.refused.detail))}</span>` : ""}</span></p>`
    : `<div class="tr-warn">${ico("warn")}<div><p>${esc(t("trWarn"))}</p>`
      + `${list0(d?.roles).includes("comments") ? `<p>${esc(t("trWarnComments"))}</p>` : ""}`
      + `<p>${esc(t("trWarnSystem"))}</p></div></div>${asksHTML(d.settings)}${filesHTML(d)}`;
  const untrust = d?.record === true
    ? `<button type="button" class="tr-untrust" data-tr="untrust">${esc(t("cnUntrust"))}</button>` : "";
  return `<form class="cv-form tr" novalidate role="dialog" aria-modal="true" aria-labelledby="tr-h">
    ${d?.reopened ? `<p class="tr-reopened" role="status">${esc(t("trReopened"))}</p>` : ""}
    <h2 class="cv-form-h" id="tr-h">${esc(title)}</h2>
    <p class="tr-meta">${esc(meta)}</p>
    <p class="tr-path"><code>${esc(cut(d?.path))}</code>${print}</p>
    ${body}
    <p class="tr-wait" data-tr-wait role="status" hidden>${esc(t("trWaiting"))}</p>
    <p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden></p>
    <div class="cv-ask-row">${untrust}
      <button type="button" data-a="cancel" data-autofocus>${esc(t(refused ? "trClose" : "askCancel"))}</button>
      ${refused ? "" : `<button type="submit" data-a="ok">${esc(t("trTrust"))}</button>`}</div>
  </form>`;
}
```

- [ ] **Step 4: Проводка в `app/app.js`**

4a. Імпорт поруч з `connections-view.js`: `import { TRUST_POST_TIMEOUT_MS, trustDialogHTML } from './trust-view.js';`. `askForm`, `askYesNo`, `tell`, `getLang`, `refusalView`, `modName`, `roleTitle` уже імпортовані.

4b. `connAction` — після `else if (act === 'disable') connDisable(e);`:

```js
  else if (act === 'trust' || act === 'trustinfo') connTrust(e);
```

(Відкрита панель стоїть на заваді й цим діям — гілка `cnDrawer && (act !== 'disable' || …)` вище закриває її першою, як для «Налаштувати».)

4c. Після `afterModulesChange` (перед секцією «бічна панель») — нова секція:

```js
/* ── довіра своєму модулю (етап 3c) ──────────────────────────────────────────────────────────────────────
   Діалог — `askForm` з розміткою `trust-view.js`; ним користуються картки «Підключень» (`connTrust`) і крок 2 майстра
   (`deps.openTrust`). Межа «довіряє лише людина» — системне вікно ОС, яке сервер показує ПІСЛЯ «Довіряю» і чекає до
   120 с, тож запит іде через `trustPost` зі своєю стелею, а не через `formApi` (20 с). */

/** `POST /api/module-trust` зі стелею `TRUST_POST_TIMEOUT_MS`: обрив — `code: 'timeout'`, як у `formApi`. */
function trustPost(body) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TRUST_POST_TIMEOUT_MS);
  return api('/api/module-trust', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal,
  })
    .catch((e) => { throw e?.name === 'AbortError' ? Object.assign(new Error('timeout'), { code: 'timeout' }) : e; })
    .finally(() => clearTimeout(timer));
}

/**
 * Діалог довіри модулю `entry` простору `spaceId` (зафіксованого ВИКЛИКАЧЕМ до відкриття: агент, що перемкнув активний
 * простір, діалог не збиває). `true` — довіру видано (модулі вже перечитано, `afterModulesChange`).
 *   — «Довіряю» → рядок «Підтвердіть у системному вікні…» → `POST /api/module-trust {space, id, hash, lang}`;
 *   — `module-changed` (тека змінилась, поки діалог був відкритий) → діалог закривається й відкривається знову зі
 *     свіжими даними та рядком угорі;
 *   — інша відмова (`trust-declined`, `trust-no-confirm`, `trust-busy`, `role-taken`…) → текст у діалозі, він лишається;
 *   — «Забрати довіру» → діалог закривається (питання поверх нього перебило б його), далі `untrustFlow`.
 */
async function openTrust(entry, spaceId) {
  let reopened = false;
  for (;;) {
    let d;
    try {
      d = (await formApi(`/api/module-trust?space=${encodeURIComponent(spaceId)}&id=${encodeURIComponent(entry.id)}`))?.trust;
    } catch (err) {
      const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n'));
      return false;
    }
    if (!d) return false;
    let again = false;
    let untrust = false;
    let granted = false;
    await askForm(() => trustDialogHTML({ ...d, reopened }), {
      onMount: (form) => {
        /* «Забрати довіру» сама діалогу не відповідає: позначка + «Скасувати». Під час запиту (`aria-busy`) — нічого:
           «Скасувати» тоді не закриває, а позначка лишилась би й спрацювала б після успішної довіри. */
        form.querySelector('[data-tr="untrust"]')?.addEventListener('click', () => {
          if (form.getAttribute('aria-busy') === 'true') return;
          untrust = true;
          form.querySelector('[data-a="cancel"]')?.click();
        });
      },
      onSubmit: async (_vals, ctl) => {
        const wait = ctl.form.querySelector('[data-tr-wait]');
        if (wait) wait.hidden = false;
        try {
          await trustPost({ space: spaceId, id: d.id, hash: d.hash, lang: getLang() });
          granted = true;
          return undefined;
        } catch (err) {
          if (err?.code === 'module-changed') { again = true; return undefined; }
          const r = refusalView(err);
          return [t(r.key), r.detail].filter(Boolean).join(' — ');
        } finally {
          if (wait) wait.hidden = true;
        }
      },
      focusBack: () => homeNode()?.querySelector(`[data-cn][data-id="${CSS.escape(entry.id)}"]:not([disabled])`) ?? null,
    });
    if (untrust) { await untrustFlow(entry, spaceId); return false; }
    if (again) { reopened = true; continue; }
    if (!granted) return false;
    toast(t('cnToastTrusted', modName(entry)));
    await afterModulesChange();
    return true;
  }
}

/**
 * «Забрати довіру»: питання (небезпечна дія; для ввімкненого — які ролі перестануть працювати), далі
 * `POST /api/module-untrust` у простір `spaceId`, зафіксований ДО питання (як `connDisable`). `space.json` не змінюється.
 */
async function untrustFlow(entry, spaceId) {
  const name = modName(entry);
  const roles = (entry.roles || []).map(roleTitle).join(', ');
  const lines = [t('cnUntrustAsk', name), ...(entry.enabled === true && roles ? [t('cnUntrustRole', roles)] : []), t('cnUntrustKeeps')];
  if (!(await askYesNo(lines.join('\n\n'), { yes: t('cnUntrust'), danger: true }))) return false;
  try { await postForm('/api/module-untrust', { space: spaceId, id: entry.id }); }
  catch (err) { const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n')); return false; }
  toast(t('cnToastUntrusted', name));
  await afterModulesChange();
  return true;
}

/** «Довіритись…» / «Чому не можна…» на картці: діалог для простору сторінки (знімок до відкриття), потім фокус на картку. */
async function connTrust(e) {
  const spaceId = connState.spaceId;
  await openTrust(e, spaceId);
  if (connOpen() && connState.spaceId === spaceId) refocusCard(e.id, 'trust');
}
```

4d. Після `cnDrawerCheck`:

```js
/** «Забрати довіру» в панелі свого модуля: модуль і простір — з панелі ДО її закриття (питання «Відкинути?» могло
 *  висіти, а сторінка — перейти в інший простір), далі — те саме питання й запит, що з діалогу довіри. */
async function cnDrawerUntrust() {
  if (!cnDrawer || cnDrawer.busy) return;
  const { entry, spaceId } = cnDrawer;
  if (!(await dismissCnDrawer())) return;
  await untrustFlow(entry, spaceId);
}
```

і у `wireCnDrawer` після `else if (a === 'erase') toggleCnErase(b);`: `else if (a === 'untrust') cnDrawerUntrust();`

- [ ] **Step 5: Словник** — `app/i18n.js`, після блоку 3c з Task 6 в `UK`:

```js
  /* Діалог довіри своєму модулю (етап 3c, `trust-view.js`) */
  trTitle: (name) => `Довіритись модулю «${name}»?`,
  trTitleNew: (name) => `Довіритись новій версії «${name}»?`,
  trFingerprint: (h) => `Відбиток ${h}`,
  trWarn: 'Код цього модуля виконується на цьому компʼютері з вашими правами: читає й пише файли, ходить у мережу, бачить секрети, які ви йому дасте. Довіряйте лише коду, який ви чи ваша команда переглянули.',
  trWarnComments: 'Його JavaScript виконуватиметься в сторінках канваса й в опублікованих превʼю.',
  trWarnSystem: 'Після «Довіряю» система попросить підтвердити у своєму вікні.',
  trAsks: 'Просить:',
  trAsksNone: 'Налаштувань не просить.',
  trSecret: 'секрет',
  trSecretPublic: 'публічний (потрапляє в сторінки)',
  trFiles: (n, size) => `Файли (${n}, ${size})`,
  trFilesList: 'Файли модуля',
  trChangedCount: (k) => `змінено від минулої довіри: ${k}`,
  trNew: 'новий',
  trChanged: 'змінено',
  trRemoved: (list) => `Прибрано: ${list}`,
  trTrust: 'Довіряю',
  trClose: 'Закрити',
  trRefused: (why) => `Цій теці не можна довіритись. ${why}`,
  trReopened: 'Тека змінилась, поки діалог був відкритий, — перегляньте ще раз.',
  trWaiting: 'Підтвердіть у системному вікні…',
  trSizeB: (x) => `${x} Б`,
  trSizeKb: (x) => `${String(x).replace('.', ',')} КБ`,
  trSizeMb: (x) => `${String(x).replace('.', ',')} МБ`,
```

і в `EN`:

```js
  /* Trust dialog for an own module (stage 3c, `trust-view.js`) */
  trTitle: (name) => `Trust the module “${name}”?`,
  trTitleNew: (name) => `Trust the new version of “${name}”?`,
  trFingerprint: (h) => `Fingerprint ${h}`,
  trWarn: 'This module’s code runs on this computer with your permissions: it reads and writes files, goes online and sees the secrets you give it. Trust only code that you or your team have reviewed.',
  trWarnComments: 'Its JavaScript will run in canvas pages and in published previews.',
  trWarnSystem: 'After “Trust” the system will ask you to confirm in its own window.',
  trAsks: 'Asks for:',
  trAsksNone: 'Asks for no settings.',
  trSecret: 'secret',
  trSecretPublic: 'public (goes into pages)',
  trFiles: (n, size) => `Files (${n}, ${size})`,
  trFilesList: 'Module files',
  trChangedCount: (k) => `changed since the last trust: ${k}`,
  trNew: 'new',
  trChanged: 'changed',
  trRemoved: (list) => `Removed: ${list}`,
  trTrust: 'Trust',
  trClose: 'Close',
  trRefused: (why) => `This folder cannot be trusted. ${why}`,
  trReopened: 'The folder changed while the dialog was open — review it again.',
  trWaiting: 'Confirm in the system window…',
  trSizeB: (x) => `${x} B`,
  trSizeKb: (x) => `${x} KB`,
  trSizeMb: (x) => `${x} MB`,
```

- [ ] **Step 6: Стилі** — `app/styles.css`, після правила `.cv-field input[aria-invalid="true"]`:

```css
/* Діалог довіри своєму модулю (3c, `trust-view.js`): та сама біла картка `askForm`, що в діалогу простору, ширша — під
   список файлів. «Забрати довіру» — ліворуч у рядку кнопок, небезпечна (`--bad-ink` на `--g50` ≥ 4.5:1). */
.cv-ask--form:has(.tr){width:560px}
.tr-meta,.tr-path{margin:-8px 0 0;font-size:12px;line-height:1.4;color:var(--g600);overflow-wrap:anywhere}
.tr-reopened{padding:8px 10px;border:1px solid var(--g450);border-radius:6px;background:var(--g50);font-size:13px;color:var(--g900)}
.tr-warn{display:flex;gap:8px;padding:10px 12px;border:1px solid var(--g450);border-radius:6px;background:var(--g50);
  font-size:13px;line-height:1.45;color:var(--g900)}
.tr-warn .ico{flex:none;margin-top:2px;color:var(--bad-ink)}
.cv-ask--form .tr-warn p{margin:0 0 6px}
.cv-ask--form .tr-warn p:last-child{margin:0}
.tr-h3{font-weight:600;color:var(--g700)}
.tr-none{color:var(--g600)}
.tr-asks{margin:-8px 0 0;padding-left:18px;font-size:13px;color:var(--g900)}
.tr-mark{margin-left:6px;padding:0 6px;border:1px solid var(--g450);border-radius:999px;font-size:11px;color:var(--g700);white-space:nowrap}
.tr-files{max-height:180px;overflow:auto;margin:-8px 0 0;padding:6px 8px;list-style:none;border:1px solid var(--g450);
  border-radius:6px;font-size:12px}
.tr-files:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.tr-files li{display:flex;align-items:center;gap:8px;padding:2px 0;color:var(--g900)}
.tr-files code{flex:1;min-width:0;overflow-wrap:anywhere}
.tr-size{flex:none;color:var(--g600)}
.tr-removed{font-size:12px;color:var(--g600);overflow-wrap:anywhere}
.tr-refused{display:flex;gap:8px;color:var(--g900)}
.tr-refused .ico{flex:none;margin-top:2px;color:var(--bad-ink)}
.tr-wait{color:var(--g700)}
.cv-ask button.tr-untrust{margin-right:auto;border-color:var(--bad-ink);background:var(--g50);color:var(--bad-ink)}
```

- [ ] **Step 7: Прогін — зелені + увесь клієнт**

Run: `python3 "$G" 300 2500 node --test tests/*.test.mjs 2>&1 | tail -15`
Expected: PASS (`i18n.test.mjs` — та сама арність в обох мовах, `i18n-literals` — кирилиці поза словником нема, `js-parses`, `icons`).

- [ ] **Step 8: Мутації**

| мутація | має впасти |
|---|---|
| `trustDialogHTML`: прибрати `data-autofocus` з «Скасувати» | `контракт askForm…` |
| `filesHTML`: `const marks = true;` | `зміст: …` (позначка «новий» без запису) |
| `trustDialogHTML`: `esc(cut(d?.path))` → `cut(d?.path)` | `усе з диска — текст…` |
| `cut`: повертати `v` без обрізання | `усе з диска…` (обрізання) |
| `trustDialogHTML`: `refused ? "" : …` для кнопки «Довіряю» → завжди кнопка | `refused: …` |
| `openTrust`: прибрати рядок `if (form.getAttribute('aria-busy') === 'true') return;` | `3c: openTrust …` (wiring) |
| `openTrust`: прибрати `continue` після `reopened = true` | той самий |
| `trustPost`: `TRUST_POST_TIMEOUT_MS` → `FORM_POST_TIMEOUT_MS` | той самий |
| `cnDrawerUntrust`: брати `entry, spaceId` ПІСЛЯ `dismissCnDrawer()` | `3c: «Забрати довіру» …` |

- [ ] **Step 9: Коміт**

```bash
git add app/trust-view.js app/app.js app/i18n.js app/styles.css tests/trust-view.test.mjs tests/connections-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): діалог довіри своєму модулю, «Забрати довіру» з картки й панелі

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: майстер — свій модуль на кроці 2, «чекає довіри» на кроці 3

**Files:**
- Modify: `app/wizard-model.js` (імпорт ≈12; новий `needsTrust`; `writePlan` ≈186)
- Modify: `app/wizard-view.js` (імпорти ≈30; `optionHTML` ≈102; `step3HTML` ≈187; новий `waitHTML`; шапка файла)
- Modify: `app/wizard.js` (стан `open` ≈99; `view` ≈110; `loadStep3` ≈376; `runOp` ≈431; `submit3` — селектор фокуса; `click` ≈633; новий `trustFrom`)
- Modify: `app/app.js` (`createWizard({…})` ≈1338 — нова залежність `openTrust`)
- Modify: `app/i18n.js`, `app/styles.css` (після правил `.wz-off`)
- Create: `tests/wizard-own.test.mjs`
- Modify: `tests/wizard-wiring.test.mjs`

- [ ] **Step 1: Тести (червоні)** — створи `tests/wizard-own.test.mjs`:

```js
/**
 * Свої модулі простору в майстрі (Deai 0.7.0, етап 3c; спека, «Майстер (крок 2)» з поправками 2 і 10 плану):
 * `needsTrust`, НЕзмінний `initialPick`, операція `untrusted` у `writePlan`, рядок свого модуля на кроці 2 у трьох станах і
 * рядок «чекає довіри» на кроці 3.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { holdersByRole, initialPick, needsTrust, offRows, writePlan } from "../app/wizard-model.js";
import { wizardHTML } from "../app/wizard-view.js";

const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const OWN = (id, roles, extra = {}) => M(id, roles, { custom: true, builtin: false, trust: "untrusted", runs: false,
  record: false, status: "untrusted", source: `~/w/modules/${id}`, ...extra });

test("needsTrust: свій без робочого коду — так; свій зі знімком і вбудований — ні", () => {
  assert.equal(needsTrust(OWN("a", ["publish"])), true);
  assert.equal(needsTrust(OWN("a", ["publish"], { trust: "refused", status: "error" })), true);
  assert.equal(needsTrust(OWN("a", ["publish"], { trust: "changed", runs: true, status: "ok" })), false);
  assert.equal(needsTrust(M("vercel-publish", ["publish"])), false);
});

test("initialPick НЕ змінено: увімкнений недовірений (колега закомітив) — вибраний, тож writePlan його НЕ вимикає", () => {
  const list = [OWN("acme", ["publish"], { enabled: true }), M("vercel-publish", ["publish"])];
  const pick = initialPick(list);
  assert.deepEqual([...pick], ["acme"]);
  assert.deepEqual(offRows(list, pick), []);
  assert.deepEqual(writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list }), [],
    "ні disable, ні settings (картки й форми нема)");
});

test("writePlan: вибраний невключений модуль, що тепер потребує довіри, — операція untrusted, а не enable", () => {
  const was = [OWN("acme", ["publish"], { trust: "trusted", runs: true, status: "ok" })];
  const now = [OWN("acme", ["publish"])];
  assert.deepEqual(writePlan({ list: now, pick: new Set(["acme"]), forms: new Map(), atPick: holdersByRole(was), prevList: was }),
    [{ op: "untrusted", id: "acme", roles: ["publish"], stale: [] }]);
});

const V2 = (list, pick, over = {}) => ({
  step: 2, created: true, busy: false, s1: { name: "S", color: "space-1", path: "~/s", folderFirst: false },
  s2: { list, failed: null, capsError: false, pick, path: "~/s" },
  s3: { cards: [], offs: [], waits: [], failed: null, loading: false },
  s4: { title: "", id: "", source: "empty", from: "", spaceName: "S", tasks: 0 }, ...over,
});

test("крок 2: недовірений — радіо вимкнене, пігулка «свій», «Довіритись…» ПОЗА label; увімкнений — ще й причина", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"], { enabled: true })], new Set(["acme"])));
  assert.match(h, /<div class="wz-opt-row"><label class="wz-opt" for="wz-o-0-0"><input type="radio" id="wz-o-0-0" name="wz-r-0" value="acme" data-wz-pick data-role="publish" checked disabled>/);
  assert.match(h, /<span class="cn-tag cn-tag--own" title="~\/w\/modules\/acme">свій<\/span>/);
  assert.match(h, /<\/label><button type="button" class="ctl ctl--out" data-wz="trust" data-id="acme">.*Довіритись…<\/button><\/div>/s);
  assert.match(h, /class="wz-opt-why".*йому не довірено/s);
  const off = wizardHTML(V2([OWN("acme", ["publish"])], new Set()));
  assert.match(off, /value="acme" data-wz-pick data-role="publish" disabled>/);
  assert.doesNotMatch(off, /wz-opt-why/, "невключений недовірений — без причини: просто чекає довіри");
});

test("крок 2: refused без знімка — радіо вимкнене й причина, кнопки нема; changed — вибирається з рядком «є зміни»", () => {
  const r = wizardHTML(V2([OWN("acme", ["publish"], { trust: "refused", status: "error", trust_error: "too-big", error: "too-big: 6 MiB" })], new Set()));
  assert.match(r, /value="acme" data-wz-pick data-role="publish" disabled>/);
  assert.match(r, /class="wz-opt-why".*Тека завелика/s);
  assert.doesNotMatch(r, /data-wz="trust"|wz-opt-row/);
  const c = wizardHTML(V2([OWN("acme", ["publish"], { trust: "changed", runs: true, status: "ok" })], new Set()));
  assert.match(c, /value="acme" data-wz-pick data-role="publish">/, "радіо доступне");
  assert.match(c, /<span class="wz-opt-trust">.*У теці є зміни/s);
});

test("крок 2 зайнятий: «Довіритись…» теж вимкнена", () => {
  assert.match(wizardHTML(V2([OWN("acme", ["publish"])], new Set(), { busy: "save" })), /data-wz="trust" data-id="acme" disabled>/);
});

test("крок 3: рядок «чекає довіри» замість картки; без карток — не «нічого не підключаємо»", () => {
  const e = OWN("acme", ["publish"], { enabled: true, name: "<b>Acme</b>" });
  const h = wizardHTML(V2([e], new Set(["acme"]), { step: 3,
    s3: { cards: [], offs: [], waits: [{ entry: e, result: null }], failed: null, loading: false } }));
  assert.match(h, /<ul class="wz-waits"><li class="wz-wait" data-id="acme" tabindex="-1">/);
  assert.match(h, /Публікація: «&lt;b&gt;Acme&lt;\/b&gt;» чекає довіри/);
  assert.doesNotMatch(h, /Нічого не підключаємо|wz-card/);
});
```

Допиши в `tests/wizard-wiring.test.mjs`:

```js
test("3c: «Довіритись…» на кроці 2 — deps.openTrust з простором майстра, потім loadStep2; app.js передає openTrust", () => {
  assert.match(fn(W, "click"), /else if \(a === "trust"\) trustFrom\(b\.dataset\.id\);/);
  const b = fn(W, "trustFrom");
  assert.match(b, /await deps\.openTrust\(e, mine\.spaceId\);/);
  assert.match(b, /if \(wz !== mine \|\| mine\.step !== 2\) return;/);
  assert.ok(b.indexOf("deps.openTrust(") < b.indexOf("loadStep2()"));
  assert.match(read("app.js"), /openTrust: \(entry, spaceId\) => openTrust\(entry, spaceId\),/);
});

test("3c: крок 3 — картки лише тим, хто не чекає довіри; невключений, що тепер потребує довіри, — назад на крок 2; untrusted — відмова без запиту", () => {
  const b = fn(W, "loadStep3");
  assert.match(b, /picked\.some\(\(e\) => needsTrust\(e\) && e\.enabled !== true\)/);
  assert.match(b, /mine\.cards = picked\.filter\(\(e\) => !needsTrust\(e\)\)\.map\(cardFrom\);/);
  assert.match(b, /mine\.waits = picked\.filter\(needsTrust\)\.map\(\(entry\) => \(\{ entry, result: null \}\)\);/);
  const r = fn(W, "runOp");
  assert.match(r, /else if \(op\.op === "untrusted"\)/);
  assert.ok(r.indexOf('op.op === "untrusted"') < r.indexOf("deps.post("), "відмова без запиту");
  assert.match(r, /for \(const w of mine\.waits\) if \(w\.entry\.id === op\.id\) w\.result = result;/);
});
```

- [ ] **Step 2: Прогін — червоні**

Run: `python3 "$G" 120 1500 node --test tests/wizard-own.test.mjs tests/wizard-wiring.test.mjs 2>&1 | tail -20`
Expected: FAIL.

- [ ] **Step 3: Модель** — `app/wizard-model.js`.

Імпорт: `import { ROLE_ORDER, formPatch, isDirty, isOwn, ownRuns } from "./connections-model.js";`. Після `entryOf`:

```js
/** Свій модуль простору, чий код тут не виконується (недовірений чи `refused` без знімка, 3c): на кроці 2 його не вибрати,
 *  крок 3 не малює йому картки — вмикати й налаштовувати нічого до довіри. `initialPick` його НЕ виключає (поправка 2):
 *  увімкнений колегою лишається вибраним, інакше `writePlan` вимкнув би його лише тому, що людина пройшла майстер. */
export const needsTrust = (e) => isOwn(e) && !ownRuns(e);
```

`writePlan` — у циклі `for (const e of pickedInOrder(list, pick))`, ПЕРШИМ рядком після `const roles = rolesOf(e);`:

```js
    if (e.enabled !== true && needsTrust(e)) {
      /* Вибраний на кроці 2, а тепер потребує довіри (її забрали між кроками): вмикати не можна — відмова без запиту
         (`runOp`), а не `enable`, бо картки (й форми) для нього може не бути. */
      ops.push({ op: "untrusted", id: e.id, roles, stale: [] });
      continue;
    }
```

і в докстрінг `writePlan` — рядок `untrusted — вибраний невключений, що тепер потребує довіри: відмова без запиту.`

- [ ] **Step 4: Розмітка** — `app/wizard-view.js`.

4a. Імпорти: з `connections-view.js` додай `ownTagHTML, trustLineText`; з `wizard-model.js` — `needsTrust`. У шапці файла: `s3 = {cards, offs, waits, failed|null, loading}`, `waits — [{entry, result}]: вибрані, що чекають довіри (3c)`; гачок `[data-wz="trust"][data-id]` — «Довіритись…» на кроці 2.

4b. `optionHTML` — заміни повністю:

```js
function optionHTML(e, i, j, role, s, dis) {
  const id = `wz-o-${i}-${j}`;
  const on = pickedFor(s.pick, s.list, role) === e.id;
  const desc = builtinText(e.id)?.desc;
  /* Свій модуль без робочого коду (3c) не вибирається: радіо вимкнене завжди (і вибране, якщо його ввімкнув колега). */
  const wait = needsTrust(e);
  /* «Замість кого»: поточні тримачі ролей цього модуля (зі списку сервера), коли сам він ще не ввімкнений. */
  const instead = e.enabled === true || wait ? [] : roleHolders(e, s.list);
  const why = e.status === "error" || (wait && e.enabled === true) ? whyOf(e) : null;
  const line = trustLineText(e);
  const label = `<label class="wz-opt" for="${id}"><input type="radio" id="${id}" name="wz-r-${i}" value="${esc(e.id)}"`
    + ` data-wz-pick data-role="${esc(role)}"${on ? " checked" : ""}${wait ? " disabled" : dis}>`
    + `<span class="wz-opt-body"><span class="wz-opt-top"><b>${esc(modName(e))}</b>`
    + `${e.implicit === true ? `<span class="cn-tag">${esc(t("cnImplicit"))}</span>` : ""}${ownTagHTML(e)}</span>`
    + `${desc ? `<span class="wz-opt-desc">${esc(t(desc))}</span>` : ""}`
    + `${line ? `<span class="wz-opt-trust">${ico("lock", 13)}<span>${esc(line)}</span></span>` : ""}`
    + `${instead.length ? `<span class="wz-opt-instead">${esc(t("wzInstead", instead.map(modName).join(", ")))}</span>` : ""}`
    + `${why ? `<span class="wz-opt-why">${ico("warn", 13)}<span>${esc(t(why.key))}${detail(why.detail)}</span></span>` : ""}`
    + `</span></label>`;
  /* «Довіритись…» — ПОРУЧ із label, а не всередині: клік по кнопці в label клікнув би й радіо. Лише недовіреному:
     `refused` без знімка довірити не можна (причина вже в рядку). */
  if (!wait || e.trust === "refused") return label;
  return `<div class="wz-opt-row">${label}${btn(`data-wz="trust" data-id="${esc(e.id)}"`, t("cnTrust"), { icon: "lock", dis: !!dis })}</div>`;
}
```

4c. Перед `step3HTML`:

```js
/** Рядок «чекає довіри» кроку 3: вибраний (увімкнений колегою) свій модуль без довіри — налаштувати його можна після неї. */
function waitHTML(w) {
  return `<li class="wz-wait" data-id="${esc(w.entry.id)}" tabindex="-1">${ico("lock", 13)}`
    + `<span>${esc(t("wzWaitTrust", rolesLine(w.entry), modName(w.entry)))}</span>${resultHTML(w.result)}</li>`;
}
```

і в `step3HTML`, гілка `else`:

```js
    const waits = (s.waits ?? []).length ? `<ul class="wz-waits">${s.waits.map(waitHTML).join("")}</ul>` : "";
    const offs = s.offs.length ? `<ul class="wz-offs">${s.offs.map(offHTML).join("")}</ul>` : "";
    const cards = s.cards.length
      ? `<fieldset class="wz-cards"${busy ? " disabled" : ""}>${s.cards.map((c, i) => cardHTML(c, i, busy)).join("")}</fieldset>`
      : (offs || waits ? "" : `<p class="cn-dr-none">${esc(t("wzS3Nothing"))}</p>`);
    body = waits + offs + cards;
```

- [ ] **Step 5: Контролер** — `app/wizard.js`.

5a. Імпорт з `wizard-model.js`: додай `needsTrust`. Стан `open`: `cards: [], offs: [], waits: [], s3failed: null, s3loading: false,`. `view()`: `s3: { cards: wz.cards, offs: wz.offs, waits: wz.waits, failed: wz.s3failed, loading: wz.s3loading },`.

5b. `loadStep3`: на початку — `mine.cards = []; mine.offs = []; mine.waits = []; mine.s3failed = null; mine.s3loading = true;`; рядок `mine.cards = pickedInOrder(mine.list, mine.pick).map(cardFrom);` заміни на:

```js
    const picked = pickedInOrder(mine.list, mine.pick);
    /* Вибраний невключений модуль тепер потребує довіри (її забрали між кроками): вмикати нічого — назад на крок 2. */
    if (picked.some((e) => needsTrust(e) && e.enabled !== true)) {
      mine.s3loading = false;
      deps.toast(t(refusalView({ code: "module-untrusted" }).key));
      go(2);
      return;
    }
    /* Увімкнений колегою, але не довірений тут — без картки (налаштовувати й перевіряти нічого), рядком «чекає довіри». */
    mine.cards = picked.filter((e) => !needsTrust(e)).map(cardFrom);
    mine.waits = picked.filter(needsTrust).map((entry) => ({ entry, result: null }));
```

5c. `runOp` — гілка перед `} else if (op.stale.length) {`:

```js
    } else if (op.op === "untrusted") {
      result = { kind: "refused", ...refusalView({ code: "module-untrusted" }) };
```

і після `if (card) card.result = result;`: `for (const w of mine.waits) if (w.entry.id === op.id) w.result = result;`.

5d. `submit3`, фокус на першу відмову: селектор `".wz-card .cn-res--err, .wz-off .cn-res--err, .wz-wait .cn-res--err"` і `closest(".wz-card, .wz-off, .wz-wait")`.

5e. `click` — після `else if (a === "copy") copyPhrase();`: `else if (a === "trust") trustFrom(b.dataset.id);`. Перед `click`:

```js
  /** «Довіритись…» у рядку свого модуля (крок 2): діалог довіри `app.js` (`deps.openTrust`) для простору майстра, далі
      список перечитується — вибір інших ролей зберігається (`loadStep2` чистить лише зниклі модулі). Фокус — на радіо
      модуля, а нема (довіри не дали) — на ту саму кнопку; лише коли фокус справді втрачено. */
  async function trustFrom(id) {
    if (!wz || wz.busy || wz.step !== 2) return;
    const mine = wz;
    const e = (mine.list || []).find((x) => x?.id === id);
    if (!e) return;
    await deps.openTrust(e, mine.spaceId);
    if (wz !== mine || mine.step !== 2) return;
    await loadStep2();
    if (wz !== mine || !focusLost()) return;
    const sel = CSS.escape(id);
    (deps.node()?.querySelector(`input[data-wz-pick][value="${sel}"]:not([disabled])`)
      ?? deps.node()?.querySelector(`[data-wz="trust"][data-id="${sel}"]`))?.focus({ preventScroll: true });
  }
```

У шапці `createWizard` (докстрінг `deps`, якщо перелічено) — `openTrust(entry, spaceId)` → `Promise<boolean>`.

5f. `app/app.js`, `createWizard({…})`: після `afterModulesChange: () => afterModulesChange(),` — `openTrust: (entry, spaceId) => openTrust(entry, spaceId),`.

- [ ] **Step 6: Словник і стилі**

`UK` (поруч з `wzOffRowPlain`): `wzWaitTrust: (role, name) => \`${role}: «${name}» чекає довіри на цьому компʼютері — налаштувати його можна після неї, у «Підключенні».\`,`
`EN`: `wzWaitTrust: (role, name) => \`${role}: “${name}” is waiting for trust on this computer — you can set it up afterwards in Connections.\`,`

`app/styles.css`, після правил `.wz-off …`:

```css
/* Свій модуль на кроці 2 (3c): рядок «варіант + Довіритись…» (кнопка поза label), рядок «є зміни»; крок 3 — «чекає довіри». */
.wz-opt-row{display:flex;flex-direction:column;gap:6px;min-width:0}
.wz-opt-row > .wz-opt{flex:1}
.wz-opt-row > .ctl{align-self:flex-start}
.wz-opt-trust{display:flex;gap:6px;font-size:12px;color:var(--mid)}
.wz-opt-trust .ico{flex:none;margin-top:1px;color:var(--open)}
.wz-waits{display:flex;flex-direction:column;gap:8px;margin:0 0 12px;padding:0;list-style:none}
.wz-wait{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 10px;border:1px dashed var(--line2);
  border-radius:var(--r-sm);font-size:12.5px;color:var(--mid)}
.wz-wait .ico{flex:none;color:var(--open)}
.wz-wait > span{overflow-wrap:anywhere;min-width:0}
.wz-wait .cn-res{flex-basis:100%}
```

- [ ] **Step 7: Прогін — зелені + увесь клієнт**

Run: `python3 "$G" 300 2500 node --test tests/*.test.mjs 2>&1 | tail -15`
Expected: PASS (зокрема `wizard-css.test.mjs` — кожен клас `wz-*` має правило; наявні `wizard-model`/`wizard-view` — без змін).

- [ ] **Step 8: Мутації**

| мутація | має впасти |
|---|---|
| `optionHTML`: `${wait ? " disabled" : dis}` → `${dis}` | `крок 2: недовірений…` |
| `optionHTML`: кнопку всередину `<label>` (без `wz-opt-row`) | той самий |
| `initialPick`: виключити `needsTrust` | `initialPick НЕ змінено…` |
| `writePlan`: прибрати гілку `untrusted` | `writePlan: …untrusted…` |
| `loadStep3`: `mine.cards = picked.map(cardFrom)` | `3c: крок 3 …` (wiring) |
| `runOp`: прибрати гілку `untrusted` | той самий |
| `trustFrom`: прибрати `await loadStep2()` | `3c: «Довіритись…» на кроці 2…` |

- [ ] **Step 9: Коміт**

```bash
git add app/wizard-model.js app/wizard-view.js app/wizard.js app/app.js app/i18n.js app/styles.css \
  tests/wizard-own.test.mjs tests/wizard-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(3c): майстер — свій модуль на кроці 2 з «Довіритись…», «чекає довіри» на кроці 3

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: живий тест і ручна перевірка системного вікна

**Files:**
- Create: `tests/live/own-modules.test.mjs`
- Modify: `tests/live/_spaces-kit.mjs` (`realDeai` — ще `trust.json` і `trusted/`)

- [ ] **Step 1: Сторож справжнього `~/.deai`** — у `realDeai()` (`tests/live/_spaces-kit.mjs`) після `secrets`:

```js
  /* Довіра своїм модулям (3c): живий тест пише `trust.json` і знімки `trusted/` — лише в тимчасовий `DEAI_HOME`. */
  trust: sha(path.join(REAL_DEAI, "trust.json")),
  trusted: existsSync(path.join(REAL_DEAI, "trusted")),
```

(`existsSync` уже імпортовано — звір; якщо ні, додай до імпорту `node:fs`.)

- [ ] **Step 2: Живий тест** — створи `tests/live/own-modules.test.mjs`:

```js
/**
 * Свої модулі простору й довіра (Deai 0.7.0, етап 3c) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium. Системне вікно ОС замінює шов `DEAI_TRUST_CONFIRM` (діє лише з
 * тимчасовим `DEAI_HOME`); ⛔ у автотестах вікно не показується НІКОЛИ. Модуль `memo-own` лежить у теці простору
 * (`<простір>/modules/memo-own/`); його `server.py` дописує свій `__file__` у мітку-файл `DEAI_OWN_CANARY` при кожному
 * виконанні верхнього рівня — так видно, ЧИ виконувався код і ЗВІДКИ (знімок у `<DEAI_HOME>/trusted/`, а не тека).
 *
 * Сценарії: 1 — повний шлях (недовірений → діалог → довіра → підключення → правка на диску → стара версія працює →
 * повторна довіра → «Забрати довіру»); 2 — системне вікно відмовило; 3 — «колега закомітив» (увімкнений, але не довірений);
 * 4 — майстер: «Довіритись…» на кроці 2; 5 — запит без заголовків браузера → 403.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, postJson, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs` стереже, що бази не збігаються). */
const PORT_BASE = 13600;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
const CARD = '.cn-card[data-id="memo-own"]';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

const SERVER_PY = (version) => `import os
VERSION = "${version}"
_p = os.environ.get("DEAI_OWN_CANARY")
if _p:
    with open(_p, "a") as _f:
        _f.write(__file__ + "\\n")


def check(ctx):
    return {"ok": True, "detail": "own " + VERSION}


def publish(ctx, build_dir, task):
    raise ctx["ModuleError"]("module-error", message="memo-own does not publish")
`;

/** Тека свого модуля в просторі `spacePath` (роль `publish`, перевірка локальна). */
function writeOwn(spacePath, version = "v1") {
  const d = path.join(spacePath, "modules", "memo-own");
  mkdirSync(d, { recursive: true });
  writeFileSync(path.join(d, "module.json"), JSON.stringify({ api: 1, id: "memo-own", name: "Memo own (test)",
    version: "1.0.0", roles: ["publish"], settings: [{ key: "note", type: "text", label: "Note (test)" }] }));
  writeFileSync(path.join(d, "server.py"), SERVER_PY(version));
  return d;
}

/** Сервер + сторінка. `seam` — відповідь «системного вікна»; `committed` — `space.json` уже вмикає `memo-own` (колега). */
async function boot(t, { seam = "yes", committed = false, extraFolder = null } = {}) {
  const canary = path.join(mkdtempSync(path.join(tmpdir(), "dc-live-canary-")), "canary.log");
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_TRUST_CONFIRM: seam, DEAI_OWN_CANARY: canary },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }] });
  t.after(() => stop(server.child));
  const spacePath = server.spaces[0].path;
  const ownDir = writeOwn(spacePath);
  if (committed) {
    const p = path.join(spacePath, "space.json");
    const sj = JSON.parse(readFileSync(p, "utf8"));
    sj.modules = { "memo-own": { enabled: true, settings: {}, roles: ["publish"] }, "static-publish": { enabled: false, settings: {} } };
    writeFileSync(p, JSON.stringify(sj));
  }
  if (extraFolder) writeOwn(path.join(server.home, extraFolder));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  const ran = () => { try { return readFileSync(canary, "utf8").split("\n").filter(Boolean); } catch { return []; } };
  return { ...server, page, errors, spacePath, ownDir, ran };
}

async function openConnections(page) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector(CARD, { timeout: 15000 });
}

const check = async (url) => (await (await postJson(url, "/api/module-check", { space: "studio", id: "memo-own" })).json());
const capsOf = async (url) => (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((x) => x.id === "studio").capabilities;
const dialogText = (page) => page.locator("form.tr").textContent();
const sjText = (s) => readFileSync(path.join(s.spacePath, "space.json"), "utf8");

test("1: недовірений не виконується → діалог → довіра → підключення зі знімка → правка на диску (працює стара) → повторна довіра → «Забрати довіру»", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await openConnections(page);
  await page.waitForSelector(`${CARD} .cn-badge--untrusted`);
  assert.match(await page.locator(`${CARD} .cn-tag--own`).textContent(), /свій/);
  assert.equal(await page.locator(`${CARD} [data-cn="enable"]`).count(), 0, "«Підключити» нема до довіри");
  assert.deepEqual(s.ran(), [], "код недовіреного модуля виконано");

  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.a), "cancel", "фокус — на «Скасувати»");
  const d1 = await dialogText(page);
  assert.match(d1, /Довіритись модулю «Memo own \(test\)»\?/);
  assert.match(d1, /Відбиток [0-9a-f]{12}/);
  assert.match(d1, /server\.py/);
  assert.match(d1, /з вашими правами/);
  assert.deepEqual(s.ran(), [], "діалог (GET /api/module-trust) код не виконує");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} [data-cn="enable"]`);
  const trusted = path.join(s.deaiHome, "trusted") + path.sep;
  assert.ok(s.ran().length > 0 && s.ran().every((p) => p.startsWith(trusted)), `виконується лише знімок: ${s.ran()}`);

  await page.click(`${CARD} [data-cn="enable"]`);
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="submit"]');
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");                  // «Замінити?» — роль тримає неявна «Публікація в теку»
  await page.click('.cv-ask-scrim [data-a="ok"]');
  await page.waitForSelector(`${CARD} .cn-badge--ok`, { timeout: 15000 });
  assert.equal((await check(s.url)).check.detail, "own v1");

  writeFileSync(path.join(s.ownDir, "server.py"), SERVER_PY("v2"));
  await page.click(`${CARD} [data-cn="check"]`);
  await page.waitForFunction((sel) => /У теці є зміни/.test(document.querySelector(`${sel} .cn-trust`)?.textContent ?? ""), CARD);
  assert.equal((await check(s.url)).check.detail, "own v1", "працює довірена версія, а не правка на диску");

  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  assert.match(await dialogText(page), /Довіритись новій версії/);
  assert.match(await page.locator("form.tr .tr-files").textContent(), /server\.py.*змінено/s);
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  assert.equal((await check(s.url)).check.detail, "own v2");

  const before = sjText(s);
  await page.click(`${CARD} [data-cn="configure"]`);
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="untrust"]');
  await page.click('#cn-drawer [data-cn-dr="untrust"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Забрати довіру до «Memo own \(test\)»/);
  await page.click('.cv-ask-scrim [data-a="ok"]');
  await page.waitForSelector(`${CARD} .cn-badge--untrusted`, { timeout: 15000 });
  assert.equal(sjText(s), before, "space.json не змінено");
  const caps = await capsOf(s.url);
  assert.equal(caps.publish, null, "роль «на папері» за недовіреним — без постачальника, не «Публікація в теку»");
  assert.equal(caps.error, undefined, "і це не «space.json не читається»");
  assert.match(await page.locator(".cn-sec .cn-now").first().textContent(), /чекає довіри/);
  assert.deepEqual(s.errors, []);
});

test("2: системне вікно відмовило — текст у діалозі, діалог лишається, довіри нема", async (t) => {
  const s = await boot(t, { seam: "no" });
  const { page } = s;
  await openConnections(page);
  await page.click(`${CARD} [data-cn="trust"]`);
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForFunction(() => /Довіру не підтверджено в системному вікні/.test(document.querySelector("form.tr [data-form-error]")?.textContent ?? ""));
  assert.equal(await page.locator("form.tr").count(), 1, "діалог лишився");
  await page.click('form.tr [data-a="cancel"]');
  await page.waitForSelector("form.tr", { state: "detached" });
  await page.waitForSelector(`${CARD} .cn-badge--untrusted`);
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

test("3: колега закомітив — «Увімкнено, але не довірено», «Зараз: … чекає довіри», картки на місці (не «space.json не читається»)", async (t) => {
  const s = await boot(t, { committed: true });
  const { page } = s;
  await openConnections(page);
  await page.waitForSelector(`${CARD} .cn-badge--untrusted`);
  assert.match(await page.locator(`${CARD} .cn-why`).textContent(), /увімкнено в просторі, але на цьому компʼютері йому не довірено/);
  assert.equal(await page.locator(`${CARD} [data-cn="disable"]`).count(), 1);
  assert.equal(await page.locator(".cn-err").count(), 0, "сторінка не вважає це нечитабельним space.json");
  assert.match(await page.locator(".cn-sec .cn-now").first().textContent(), /Memo own \(test\).*чекає довіри/);
  assert.deepEqual(s.ran(), []);
  assert.deepEqual(s.errors, []);
});

test("4: майстер — «Довіритись…» у рядку кроку 2 робить модуль доступним для вибору", async (t) => {
  const s = await boot(t, { extraFolder: path.join("work", "fresh") });
  const { page } = s;
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('#tasks-home .wz[data-step="1"]');
  await page.fill("#sp-name", "Fresh");
  await page.fill("#sp-path", "~/work/fresh");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="2"] [data-wz="trust"][data-id="memo-own"]', { timeout: 15000 });
  assert.equal(await page.locator('input[data-wz-pick][value="memo-own"]').isDisabled(), true);
  await page.click('[data-wz="trust"][data-id="memo-own"]');
  await page.waitForSelector("form.tr");
  await page.click('form.tr [data-a="ok"]');
  await page.waitForSelector('input[data-wz-pick][value="memo-own"]:not([disabled])', { timeout: 15000 });
  assert.equal(await page.locator('[data-wz="trust"][data-id="memo-own"]').count(), 0);
  assert.deepEqual(s.errors, []);
});

test("5: запит довіри без заголовків браузера (агент, curl) — 403 trust-needs-ui, довіри нема", async (t) => {
  const s = await boot(t);
  const st = await (await fetch(`${s.url}/api/module-trust?space=studio&id=memo-own`)).json();
  const res = await postJson(s.url, "/api/module-trust", { space: "studio", id: "memo-own", hash: st.trust.hash });
  assert.equal(res.status, 403);
  assert.equal((await res.json()).code, "trust-needs-ui");
  assert.equal((await (await fetch(`${s.url}/api/modules?space=studio`)).json()).modules.find((m) => m.id === "memo-own").trust, "untrusted");
  assert.deepEqual(s.ran(), []);
});

guardRealDeai();
```

⚠️ Перед прогоном звір із наявними живими тестами (`connections.test.mjs`, `wizard.test.mjs`) селектори входів (`#bar [data-act="conn"]`, `.dd--spaces [data-act="spacenew"]`, `#sp-path`) і форму `postJson` (`_spaces-kit.mjs`) — якщо щось інакше, правиться ТЕСТ під наявний інтерфейс, а не інтерфейс. Сценарій 4: простір створюється в теці `~/work/fresh`, де вже лежить `modules/memo-own/` (тека без `space.json` — створення простору її приймає).

- [ ] **Step 3: Прогін живого тесту** (лише цей файл, послідовно)

Run: `python3 "$G" 600 4000 node --test --test-concurrency=1 tests/live/own-modules.test.mjs 2>&1 | tail -20`
Expected: PASS 6/6 (5 сценаріїв + сторож `~/.deai`). Далі `tests/live/connections.test.mjs` і `tests/live/wizard.test.mjs` (по одному) — без регресій.

- [ ] **Step 4: Мутації живого** (по одній, з охоронцем; після кожної — `git diff --stat` порожній)

| мутація | має впасти |
|---|---|
| `deai_modules.capabilities`: прибрати гілку `paper` (`continue`) — помилка «на папері» знову йде в `error` | 3 (сторінка показує «space.json не читається» без карток), 1 |
| `openTrust`: без `await afterModulesChange()` після довіри | 1 (картка не оновлюється) |
| `grant_trust`: прибрати `forget_check` | 1 (`check` після повторної довіри — `own v1`) — якщо не впаде, записати в звіт задачі: юніт `test_grant_runs_the_snapshot_and_clears_the_last_check` стереже це окремо |
| `_module_trust_post`: прибрати перевірку `Sec-Fetch-Site` | 5 |
| `optionHTML`: без кнопки «Довіритись…» | 4 |

- [ ] **Step 5: Ручна перевірка системного вікна (macOS, ЛИШЕ контролер, один раз)**

На машині розробника, з охоронцем, вікно з `giving up after 3` (саме гасне за 3 с, кнопок не тиснути):

```bash
python3 "$G" 30 300 python3 -B -c "
import subprocess, sys
sys.path.insert(0, 'app')
import module_trust as mt
title, msg, yes, no = mt.confirm_texts('uk', 'Тест «лапки» \" і \\\\ слеш', 'manual-check', '0'*64, '~/tmp/x')
argv, extra = mt.confirm_command('darwin', title, msg, yes, no)
argv = [a.replace('giving up after 120', 'giving up after 3') for a in argv]
p = subprocess.run(argv, capture_output=True, text=True, timeout=20)
print('rc', p.returncode, 'out', repr(p.stdout), 'err', repr(p.stderr[:200]))
print('answer', mt._interpret(argv[0], p))
"
```

Expected: вікно зʼявилось поверх (назва з лапками й `\` — як є), за 3 с зникло, `answer no`. Результат (і чи вікно було поверх) — у звіт релізу. Якщо `_interpret` має іншу сигнатуру — звір із Task 2 і виклич так, як там.

- [ ] **Step 6: Коміт**

```bash
git add tests/live/own-modules.test.mjs tests/live/_spaces-kit.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(3c): живий тест своїх модулів і довіри (шов системного вікна)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: документи й версія 0.7.0

**Files:**
- Create: `docs/modules/authoring.md`
- Modify: `docs/modules/comments.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json`

- [ ] **Step 1: `docs/modules/authoring.md`** (англійською, як решта `docs/modules/`):

````markdown
# Writing your own module

For Deai Canvas **0.7.0**. A module adds one capability — a *role* — to a space: publishing previews, design-system
tokens, team comments. Built-in modules live in `app/modules/`; **your own modules live in the space**, in
`<space>/modules/<id>/`, so they travel with the space through git. Their code runs on your computer only after **you**
trust it.

**Коротко (uk).** Свій модуль — тека `<простір>/modules/<id>/` з `module.json` і `server.py`. Канвас його бачить одразу,
але код не виконує, доки людина не довіриться: «Підключення» → «Довіритись…» → діалог із файлами → «Довіряю» → системне
вікно ОС. Довіра — до точних байтів: канвас копіює їх у знімок `~/.deai/trusted/<відбиток>/` і виконує лише знімок. Зміна
теки не діє до повторної довіри. Агент може написати модуль, але довіритись — ні.

## 1. The folder

```
<space>/modules/acme-publish/
  module.json      the manifest
  server.py        the functions of the role (standard library only)
  adapter.js       browser files — only for the comments role, listed in "client"
```

* The folder name is the module `id`: `[a-z0-9][a-z0-9-]{0,39}`, the same as `id` in the manifest.
* An id that a built-in module already has is skipped (the Connections screen says so); so are folders without a
  `module.json`. At most 32 own modules per space (alphabetical order; the rest are skipped with a note).
* Folder rules — a folder that breaks one cannot be trusted, and the trust dialog says which rule:
  at most **200 files**, **5 MiB** in total, **8** levels of folders; only regular files and folders — no symbolic or
  hard links, no devices or pipes; file names without control, bidirectional or invisible characters, without names
  reserved on Windows (`CON`, `NUL`, `COM1`…), and no two names that differ only in letter case or Unicode form.
  `.DS_Store`, `__pycache__/`, `.git/` and `*.pyc` are ignored; every other file — hidden ones included — is part of
  what you trust.

## 2. The manifest (`module.json`)

```json
{"api": 1, "id": "acme-publish", "name": "Acme hosting", "version": "1.0.0",
 "roles": ["publish"], "publish_target": "url",
 "settings": [
   {"key": "site", "type": "text", "label": "Site id", "required": true},
   {"key": "token", "type": "secret", "label": "API token"}
 ]}
```

* `api` — `1`. `name` and `version` — strings shown to people.
* `roles` — the roles the module provides: `publish`, `tokens`, `comments` (called by the core today); `vcs`,
  `tracker`, `dashboard`, `notify` are reserved. One provider per role per space.
* `publish_target` (publish only) — `folder` (default) or `url`.
* `client` (comments only) — the browser files; see [comments.md](comments.md).
* `settings` — what the module asks for: `text`, `path`, `bool`, `select` (with `options`) or `secret`; `required`,
  `default` and (secret only) `public` as in the built-in modules. Settings are stored in the space's `space.json`;
  secrets — in `~/.deai/secrets.json`, never in the space.

A manifest that breaks these rules makes the module show as broken; nothing of it runs.

## 3. `server.py`

Every module has `check(ctx) -> {"ok": bool, "error"?: str, "detail"?: str}` — a read-only health check (5 s). A role
adds its own functions:

| role | functions |
|---|---|
| `publish` | `publish(ctx, build_dir, task)` |
| `tokens` | `tokens(ctx)` |
| `comments` | `client_config(ctx)`, `list(ctx, channel)`, `resolve(ctx, channel, id, reason)` |

The exact return values are those of the built-in modules — read `app/modules/static-publish/` (`folder`),
`app/modules/vercel-publish/` (`url`), `app/modules/css-tokens/` and [comments.md](comments.md).

`ctx` is `{"space": {id, path}, "settings": {…}, "secrets": {…only this module's…}, "folder_ok": f, "ModuleError": class}`.
Raise `ctx["ModuleError"](code, "message")` for a failure; texts are cut to 300 characters and scrubbed of your secrets.

`server.py` is executed by the core (not imported): write it against the **standard library only**.

## 4. Trust

1. Put the folder into `<space>/modules/`. The Connections screen shows the module with «own» and «Needs trust»; its
   code has not run.
2. «Trust…» opens a dialog: what the module asks for, every file with its size, the fingerprint. «Trust» then asks the
   **operating system** to confirm in its own window (macOS dialog, Windows message box, Linux `zenity`/`kdialog`). Only
   a person at the computer can answer it: a script on a page and an agent without control of the screen cannot.
3. The canvas copies exactly the bytes you saw into `~/.deai/trusted/<fingerprint>/` (read-only) and runs only that
   snapshot. Write the module's state into the space folder or your own cache, never next to `__file__`.
4. Editing the folder does not change what runs: the card says «The folder has changes» and the previous version keeps
   working until you trust the new one. A new version that breaks a folder rule cannot be trusted; the old one keeps
   running.
5. «Revoke trust» (card panel or dialog) stops the code; `space.json` and the settings stay. A module that is on in the
   space but not trusted on this computer keeps its role «on paper»: the role reports an error instead of falling back
   to another provider.

The module's top level gets **5 s** to load; a module that hangs is shown as broken (its thread lives until the server
restarts). Browser code of a trusted `comments` module runs in canvas pages and published previews with the canvas's
own access — that is part of what you trust.

## 5. The agent

An agent can write the folder, read `GET /api/modules?space=<id>` and `GET /api/module-trust?space=<id>&id=<module>`, and
— after **you** trust the module — connect and configure it (`POST /api/module-enable`, `/api/module-settings`). It cannot
trust: `POST /api/module-trust` needs the canvas page in a browser (`Origin` and `Sec-Fetch-Site: same-origin`) and then
the system window. It may revoke trust (`POST /api/module-untrust {space, id}`). Ask the person to trust the module.

## 6. Trying it locally

Create the folder in a test space, open «Connections», trust it, connect it and press «Check»: the verdict of your
`check` is shown on the card. After every edit, trust again — that is the point.
````

- [ ] **Step 2: `docs/modules/comments.md`** — у «Коротко (uk)» речення «У 0.4.0 працюють **лише вбудовані модулі** … етап 3, після діалогу довіри.» заміни на «З 0.7.0 модуль коментарів може бути й своїм — у `<простір>/modules/<id>/`, після довіри людини (див. [authoring.md](authoring.md)); JS адаптера виконується в origin канваса, тож входить у те, чому людина довіряє.». У «## 4. Security» пункт «That is why 0.4.0 loads **built-in modules only** …» заміни на: «That is why a space's own `comments` module runs only after a person trusts it ([authoring.md](authoring.md)); the adapter of a trusted own module is served from its snapshot at `GET /api/module-client/<space>/<id>/<file>`.» Опис адреси в «### Manifest» доповни: «own modules: `GET /api/module-client/<space>/<id>/<file>`». Перше речення файла «For Deai Canvas **0.4.0**.» → «For Deai Canvas **0.7.0**.».

- [ ] **Step 3: `README.md`**

- статус: `v0.6.0` → `v0.7.0`; речення «…being turned into optional per-space modules, and a space's own modules are next.» → «…being turned into optional per-space modules. A space can carry **its own modules** in `<space>/modules/`; their code runs only after you trust it.»
- «## Modules», перший абзац: перше речення «A **module** is a folder `app/modules/<id>/` with `module.json`…» → «A **module** is a folder — built in at `app/modules/<id>/` or a space's own at `<space>/modules/<id>/` — with `module.json`…»; останнє речення «Only built-in modules exist so far; a space's own modules come with stage 3c.» прибери (перше вже каже, де живуть свої). Після абзацу про Connections — новий підрозділ:

```markdown
**Own modules.** Put a module folder into `<space>/modules/<id>/` (by hand, from git, or ask the agent to write one —
see `docs/modules/authoring.md`). Connections shows it with «own» and «Needs trust»; nothing of it runs yet. «Trust…»
lists its files and settings, and «Trust» asks the operating system to confirm in its own window. The canvas then runs
a read-only snapshot of exactly those bytes (`~/.deai/trusted/`); a later edit of the folder waits for a new trust
(«The folder has changes»), and «Revoke trust» stops it without touching `space.json`. A module a colleague turned on
in `space.json` stays «on, but not trusted» on your computer until you trust it. An agent can write and connect an own
module but cannot trust it — ask the person.
```

- «**Your own service.**» (розділ про коментарі): останнє речення «A space's own modules load only after the trust dialog of stage 3c, so for now the module has to be built in (`app/modules/`).» → «The module can live in the space itself (`<space>/modules/<id>/`) and runs after you trust it — see [`docs/modules/authoring.md`](docs/modules/authoring.md).»
- «## Roadmap», пункт 3c: `- **3c** (0.7, next) — …` → `- ✅ **3c** (0.7) — a space's own modules from `<space>/modules/`, run from a snapshot only after a person trusts them (dialog + system window).`; решту пунктів не чіпати.

- [ ] **Step 4: `CHANGELOG.md`** — новий розділ над `## [0.6.0]` (дата — день релізу у форматі `DD.MM.YYYY`):

```markdown
## [0.7.0] — <DD.MM.YYYY>

Stage 3c: a space's own modules and the trust dialog. A space can carry modules in `<space>/modules/<id>/`;
their code runs only after a person trusts exactly the bytes they saw. Design:
`docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`; plan:
`docs/superpowers/plans/2026-10-22-own-modules-trust.md`. The legacy space is unchanged
(`tests/legacy-golden.test.mjs` is green without a re-shoot).

### Added

- **Own modules** (`app/deai_modules.py`): `catalog(space)` adds the space's modules to the built-in ones. An
  untrusted module is listed from its manifest and never executed; a trusted one runs from a read-only snapshot
  (`<DEAI_HOME>/trusted/<fingerprint>/`) with a 5 s load timeout. Folder rules (200 files, 5 MiB, depth 8, no links
  or special files, safe names) and notes for skipped folders (`id-taken`, `too-many-modules`, `modules-link`,
  `modules-unreadable`).
- **Trust** (`app/module_trust.py`): scanner and fingerprint, `trust.json` records, snapshots, and the operating
  system's own confirmation window (macOS `osascript`, Windows message box, Linux `zenity`/`kdialog`) as the final
  word. API: `GET /api/module-trust`, `POST /api/module-trust` (only from the canvas page: `Origin` +
  `Sec-Fetch-Site: same-origin`), `POST /api/module-untrust`.
- **Connections**: «own» tag, «Needs trust» badge, «Trust…» / «Why not…», trust lines («The folder has changes»…),
  notes under the head, «Revoke trust» in the panel; the trust dialog (`app/trust-view.js`) with files, sizes,
  changes since the last trust and the fingerprint.
- **Wizard, step 2**: an own module with «Trust…» in its row; step 3 shows «waiting for trust» for a module a
  colleague turned on.
- `docs/modules/authoring.md` — writing your own module.

### Changed

- A role held «on paper» by an own module that is on in `space.json` but does not run here reports
  `module-untrusted`/`module-error` instead of falling back to the implicit `static-publish` or to the legacy path;
  `capabilities` gives `null` for it without `error`. Enabling an own module writes its `roles` into `space.json`.
- The comments adapter of an own module is served at `/api/module-client/<space>/<id>/<file>`.

### Security

- Trust is bound to the bytes shown: changed folder → «changed», the old snapshot keeps running until re-trust.
- `DEAI_TRUST_CONFIRM` is a test seam that answers the system window; it works only with a non-default
  `DEAI_HOME`, and the server prints a warning when it is on.
- Known limits: no sandbox (a trusted module runs with your permissions); the Windows and Linux system windows are
  covered by command-building unit tests only; Safari older than 16.4 does not send `Sec-Fetch-Site`; snapshots
  replaced by a re-trust are not cleaned up (each up to 5 MiB, read-only, in `<DEAI_HOME>/trusted/`).
```

Перелік у розділі звір із тим, що реально влилось (git log від `v0.6.0`): нічого, чого нема в коді, не писати.

- [ ] **Step 5: `docs/design/spaces-and-modules.md`** — у шапці: до переліку «Built so far» додай «, stage 3c (a space's own modules with a trust dialog, 0.7.0)», а рядок «Next: 3c (…)» заміни на «Next: stage 4 — the in-house integrations of the legacy space (team dashboard, git sync) as optional per-space modules.» Під `## Status` після розділу «Stage 3b» — новий:

```markdown
### Stage 3c — own modules and trust (0.7.0, <DD.MM.YYYY>)

Spec: `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md` (revision 2 + the planning amendments listed in
`docs/superpowers/plans/2026-10-22-own-modules-trust.md`). What is built:

- **Own modules** in `<space>/modules/<id>/`: listed from the manifest, executed only from a trusted snapshot.
- **Trust**: the dialog shows files, sizes and the fingerprint; the operating system's own window is the boundary.
  Records in `<DEAI_HOME>/trust.json`, snapshots in `<DEAI_HOME>/trusted/`, untrust keeps `space.json`.
- **Roles on paper**: an own module that is on in the space but does not run here keeps its role and reports an
  error; no implicit or legacy fallback.
- **UI**: Connections (cards, notes, panel), the trust dialog, wizard step 2/3.
```

- [ ] **Step 6: `package.json`** — `"version": "0.6.0"` → `"version": "0.7.0"`.

- [ ] **Step 7: Прогін усього**

Run: `python3 "$G" 900 3000 npm test`
Expected: PASS (тести на версію/README, якщо є, — зелені).

- [ ] **Step 8: Коміт**

```bash
git add docs/modules/authoring.md docs/modules/comments.md README.md CHANGELOG.md docs/design/spaces-and-modules.md package.json
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs(3c): свої модулі — authoring.md, README, CHANGELOG 0.7.0; версія 0.7.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від `v0.6.0` (Sonnet-ревʼюер, `git archive` зрізу, мутації ключових охорон).
2. `npm test` + живі: `own-modules`, `connections`, `wizard`, `modules`, `spaces-flows` — послідовно.
3. Тег `v0.7.0` (анотований, автор `neodisa`), явний пуш: `git push origin <sha>:refs/heads/main`, `git push origin refs/tags/v0.7.0`.
4. Памʼять: `project-deai-opensource.md` + рядок `MEMORY.md`.

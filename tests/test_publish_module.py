"""Одна збірка превʼю — `serve.build_preview` — для ЛІГА й для модулів публікації.

Етап 2а, Task 3. `Handler._publish` збирав `publish/` у власному тілі, а модуль
`static-publish` (Task 4) мусить зібрати ТЕ САМЕ превʼю в локальну теку — БЕЗ
коментарів (Supabase там нема) і, за бажанням, БЕЗ парольного гейта. Друга копія збірки
розійшлась би з першою мовчки (рівно та пара «джерело / копія», проти якої написана
серія релізів 1.10–1.14), тому збірка винесена в одну функцію, а `_publish` лише кличе її.

Що доводиться:
  * `comments=False` — у дереві нема ні `comment-layer/`, ні жодного рядка `supabase`, ні
    ін'єкції в сторінках; контроль (рішення ЛІГИ — словник `supabase-comments`, 4b-2) ту саму ін'єкцію МАЄ —
    без контролю «нема» нічого б не доводило;
  * `gate_pw=None` — обгортка відкривається сама (`__gateOpen`), `authgate` нема ніде, `<title>`
    сторінок не чіпаний, а в обгортку не їде `'None'` замість пароля;
  * `gate_pw='x'` — гейт і в обгортці, і в КОЖНІЙ внутрішній сторінці (інцидент 03.08.2026);
  * шлях ЛІГА — `/api/publish` кличе `build_preview(comments=<`publish_comments`>, gate_pw=<preview_password>)`, його
    дерево збігається з прямим викликом, а відповідь має ті самі ключі в тому ж порядку (порядок
    ключів JSON спостережуваний).

⛔ Ізоляція: власні тимчасові `HOME` і `DC_TASKS_FILE` (+ `DC_NO_OVERVIEW`), `DEAI_HOME` прибрано з
оточення на час тесту — шар просторів вимкнено, як у публікаційних тестах `test_serve.py`; справжній
`~/.deai` стереже `spaces_guard` (знімок на вході в модуль, звірка на виході). Мережі нема: усі
публікації тут `build_only`.

Task 4b (`Dispatch`, `ResealModuleBuilds`, один тест у `BuildPreview`) — ДИСПЕТЧЕР ролі `publish` у
`Handler._publish`: `deai_modules.provider('publish')` вирішує, хто публікує. `'legacy'` — зашитий шлях ЛІГА
(збірка + Vercel; його відповіді незмінні), `None` — 409 `no-publish-module`, `Module` (`static-publish`) —
збірка БЕЗ коментатора в локальну теку, без жодного виходу назовні. Світ `Dispatch` — шар просторів УВІМКНЕНО:
свої `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`, два простори (`off` без інтеграцій, `on` з ними), сервер у процесі й
РОЗТЯЖКА (`Tripwire`: будь-яка мережа й будь-який підпроцес — запис і відмова; loopback лише на порт цього
сервера). Розтяжка доводить «нуль записів» разом із шпигунами за точками виходу ЛІГА (`_overview_sync`,
`_registry_push`, `git_autocommit`, шов ЛІГИ `_publish_legacy_call`…): вони б спрацювали навіть при `DC_NO_OVERVIEW`.
"""
import builtins
import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unicodedata
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import deai_modules as dm  # noqa: E402
import fake_npx  # noqa: E402
import liga_fixture  # noqa: E402
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402

_REAL = None
#: Справжній `~/deai-published` машини дизайнера (домівка — з бази користувачів, як у `spaces_guard`: `$HOME` тести
#: підміняють). Знімок фіксується ПРИ ІМПОРТІ (`discover` імпортує все раніше, ніж щось запустить), тож витік з іншого
#: файла тестів не видасться за чистий старт. Копія `_published_snapshot` з `test_static_publish.py` (імена й mtime
#: верхнього рівня, без читання вмісту й без слідування за посиланнями).
_REAL_PUBLISHED = os.path.join(spaces_guard.REAL_USER_HOME, 'deai-published')
#: Справжні `tasks.json` репозиторію й змінна `DC_TASKS_FILE` середовища прогону: роздача й публікація пишуть лише у
#: тимчасовий світ тестів, а `DC_TASKS_FILE` лишається таким, яким був (його підміна — `mock.patch.dict`).
_REAL_TASKS = os.path.join(ROOT, 'tasks.json')


def _published_snapshot():
    try:
        st = os.lstat(_REAL_PUBLISHED)
    except FileNotFoundError:
        return None
    except OSError as e:
        return ('unreadable', type(e).__name__)
    if not os.path.isdir(_REAL_PUBLISHED) or os.path.islink(_REAL_PUBLISHED):
        return ('not-a-dir', st.st_mtime_ns)
    try:
        with os.scandir(_REAL_PUBLISHED) as it:
            entries = sorted((e.name, e.stat(follow_symlinks=False).st_mtime_ns) for e in it)
    except OSError as e:
        return ('unreadable', type(e).__name__)
    return ('dir', st.st_mtime_ns, entries)


def _tasks_snapshot():
    """`(md5, mtime_ns)` справжнього `tasks.json` репозиторію; `None` — файла нема."""
    try:
        with open(_REAL_TASKS, 'rb') as fh:
            digest = hashlib.md5(fh.read()).hexdigest()
        return digest, os.stat(_REAL_TASKS).st_mtime_ns
    except OSError:
        return None


_REAL_PUBLISHED_BEFORE = _published_snapshot()
_REAL_TASKS_BEFORE = _tasks_snapshot()
_REAL_TASKS_ENV_BEFORE = os.environ.get('DC_TASKS_FILE')


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)
    now = _published_snapshot()
    if now != _REAL_PUBLISHED_BEFORE:
        raise AssertionError(f'тести змінили справжній {_REAL_PUBLISHED}: було {_REAL_PUBLISHED_BEFORE!r}, тепер {now!r}')
    if _tasks_snapshot() != _REAL_TASKS_BEFORE:
        raise AssertionError(f'тести змінили справжній {_REAL_TASKS}')
    if os.environ.get('DC_TASKS_FILE') != _REAL_TASKS_ENV_BEFORE:
        raise AssertionError('DC_TASKS_FILE у середовищі прогону змінено й не повернуто: '
                             f'було {_REAL_TASKS_ENV_BEFORE!r}, тепер {os.environ.get("DC_TASKS_FILE")!r}')


class RealStateGuards(unittest.TestCase):
    """Охоронці справжнього стану самі мають вміти падати: знімок бачить зʼявлення теки, нові імена й зміну часу
    `~/deai-published`, а також правку справжнього `tasks.json`."""

    def test_the_published_snapshot_sees_a_new_folder_a_new_name_and_a_touch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = os.path.join(tmp, 'deai-published')
            with mock.patch.dict(globals(), {'_REAL_PUBLISHED': pub}):
                none = _published_snapshot()
                os.mkdir(pub)
                empty = _published_snapshot()
                os.mkdir(os.path.join(pub, 'off'))
                one = _published_snapshot()
                self.assertEqual(_published_snapshot(), one)                  # стабільний, коли нічого не міняли
                os.utime(os.path.join(pub, 'off'), ns=(1, 1))
                touched = _published_snapshot()
        self.assertIsNone(none)
        self.assertEqual(len({repr(x) for x in (none, empty, one, touched)}), 4, (none, empty, one, touched))

    def test_the_module_teardown_raises_when_real_state_changed(self):
        """Сам `tearDownModule` — не декорація: підмінений «знімок до» (інший за справжній стан) його валить."""
        tearDownModule()                                                      # контроль: зараз усе чисто
        for name, bogus in (('_REAL_PUBLISHED_BEFORE', ('dir', 1, [('сторонній', 1)])),
                            ('_REAL_TASKS_BEFORE', ('0' * 32, 1)),
                            ('_REAL_TASKS_ENV_BEFORE', '/інший/tasks.json')):
            with self.subTest(name), mock.patch.dict(globals(), {name: bogus}):
                with self.assertRaises(AssertionError):
                    tearDownModule()

    def test_the_real_paths_are_the_real_ones_and_the_world_never_points_at_them(self):
        self.assertEqual(_REAL_PUBLISHED, os.path.join(spaces_guard.REAL_USER_HOME, 'deai-published'))
        self.assertEqual(_REAL_TASKS, os.path.join(ROOT, 'tasks.json'))
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, 'tasks.json')
            with mock.patch.dict(globals(), {'_REAL_TASKS': fake}):
                self.assertIsNone(_tasks_snapshot())
                with open(fake, 'w') as fh:
                    fh.write('{}')
                first = _tasks_snapshot()
                with open(fake, 'w') as fh:
                    fh.write('{"a": 1}')
                self.assertNotEqual(_tasks_snapshot(), first)
        self.assertNotEqual(os.environ.get('DEAI_HOME'), os.path.join(spaces_guard.REAL_USER_HOME, '.deai'))


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    return urllib.request.urlopen(req)


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _tree(root):
    """{відносний шлях: sha256} усього дерева — для порівняння двох збірок байт у байт."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(out.items()))


def _title(html):
    m = re.search(r'<title>(.*?)</title>', html, flags=re.I | re.S)
    return m.group(1) if m else None


#: Сторінки фікстури: відносний шлях у `iterations/` → `<title>` джерела. Заголовки з сутностями й
#: лапками — щоб «не чіпаний» перевірялось на тому, що `_inject_gate` справді переписує.
SOURCE_PAGES = {
    'it1/alpha/index.html': 'Альфа &amp; R&amp;D «Суди»',
    'it1/gamma/index.html': 'Гамма',
    'it2/index.html': 'Друга ітерація',
}


class TaskFixture(unittest.TestCase):
    """Тимчасова задача `fixture` (дві опубліковані ітерації) у світі БЕЗ шару просторів: спільна основа
    `BuildPreview` і `ResealModuleBuilds`. Власних тестів не має."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-bp-task-')
        self.cfgdir = tempfile.mkdtemp(prefix='dc-bp-cfg-')
        self.home = tempfile.mkdtemp(prefix='dc-bp-home-')
        for d in (self.tmp, self.cfgdir, self.home):
            self.addCleanup(shutil.rmtree, d, True)
        env = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DC_TASKS_FILE': os.path.join(self.cfgdir, 'tasks.json'),
            'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'})
        env.start()
        self.addCleanup(env.stop)       # `patch.dict` повертає й виставлений нижче `DEAI_HOME`
        # 4d-4b: шлях ЛІГА (`/api/publish`, коментарі превʼю) живе лише на ЯВНИХ записах `vercel-publish` і `supabase-comments` простору ЛІГА
        # (запасного шляху без простору нема), тож світ цієї фікстури — реєстр із одним простором ЛІГА (`legacy`: його задачі — у `DC_TASKS_FILE`).
        # Пароль превʼю в записі порожній: типовий 1100 — той, що перевіряють тести (секрет записів ЛІГИ окремо стереже `test_liga_migrate*`).
        self.deai = os.path.join(self.home, 'league-deai')
        self.league_path = os.path.join(self.home, 'league-space')
        os.makedirs(self.deai, mode=0o700)
        liga_fixture.write_records(self.league_path, self.deai, 'liga', ('publish', 'comments'),
                                   {'publish': {'secrets': {'password': ''}}})
        atomic_write_json(os.path.join(self.deai, 'spaces.json'), {
            'version': 1, 'current': 'liga',
            'spaces': [{'id': 'liga', 'path': self.league_path, 'legacy': True, 'integrations': True}]})
        os.environ['DEAI_HOME'] = self.deai
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        for rel, title in SOURCE_PAGES.items():
            src = os.path.join(self.tmp, 'iterations', rel)
            os.makedirs(os.path.dirname(src), exist_ok=True)
            with open(src, 'w', encoding='utf-8') as fh:
                fh.write(f'<!DOCTYPE html><html><head><title>{title}</title></head>'
                         f'<body><h1>{rel}</h1></body></html>')
        with open(os.path.join(self.tmp, 'iterations', 'it1', 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'alpha', 'name': 'Альфа'}, {'id': 'gamma', 'name': 'Гамма'}]}, fh)
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [
                {'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'перша', 'published': True},
                {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'друга', 'published': True}]}, fh)
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1'})

    def _tasks(self, task):
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as fh:
            json.dump({'current': 'fixture', 'design_work_root': self.cfgdir,
                       'tasks': {'fixture': task}}, fh)

    def _args(self):
        """(task, tid, its) — те саме, що `_publish` дає збірці: поточна задача й ОПУБЛІКОВАНІ ітерації."""
        tid, task = serve.task_for(serve.load_tasks(), None)
        its = [i for i in serve.load_meta(task).get('iterations', []) if i.get('published')]
        return task, tid, its

    def _league(self):
        """Рішення про коментарі для збірки ЛІГА: вбудований `supabase-comments` із ЯВНОГО запису простору ЛІГА (4d-4b: конфіг установки й
        `serve.supabase_config` зникли; було — підставний конфіг на весь модуль) і каналом `dc/<задача>` — те саме, що `Handler._publish`
        отримує з `publish_comments`; простір ЛІГА — із `setUp` цієї фікстури, закріплений простором запиту на час виклику."""
        task, tid, _its = self._args()
        with spaces.request_space('liga'):
            comments, warn = serve.publish_comments(spaces.active_space(), task, tid)
        self.assertIsNone(warn)
        self.assertIsInstance(comments, dict)
        return comments

    def _build(self, **kw):
        task, tid, its = self._args()
        kw.setdefault('build', 'legacy')          # хто збирає — обовʼязковий аргумент; за замовчуванням тут «ЛІГА»
        return serve.build_preview(task, tid, its, **kw)

    def _server(self):
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        return f'http://127.0.0.1:{httpd.server_address[1]}'


class BuildPreview(TaskFixture):
    """`serve.build_preview` напряму на тимчасовій задачі + `/api/publish` (build_only) на тій самій."""

    @staticmethod
    def _mentions(root, needle, skip_top=('shell',)):
        """Чи є в файлі дерева `needle` (без урахування регістру). Без `shell/`: це наші ж модулі
        оболонки, їхні коментарі — не артефакт коментатора, і майбутня згадка слова там не мусить
        червонити тест не з тієї причини. Лишаються сторінки, обгортка, маніфест, `comment-layer/`."""
        for dirpath, dirs, files in os.walk(root):
            if os.path.relpath(dirpath, root).split(os.sep)[0] in skip_top:
                dirs[:] = []
                continue
            for fn in files:
                with open(os.path.join(dirpath, fn), 'rb') as fh:
                    if needle in fh.read().lower():
                        return True
        return False

    def _source_title(self, rel):
        return _title(_read(os.path.join(self.tmp, 'iterations', rel)))

    def _inner_pages(self, pub):
        """Шляхи внутрішніх сторінок — з маніфесту: він і є «що поїхало» (а не звірка з нашою ж константою)."""
        man = json.loads(_read(os.path.join(pub, 'manifest.json')))
        paths = [p['path'] for p in man['pages']]
        self.assertEqual(sorted(paths), sorted(SOURCE_PAGES), 'фікстура й маніфест розійшлись')
        return paths

    # ---- форма результату --------------------------------------------------------------------

    def test_result_has_the_publish_shape_without_ok_and_code_stale(self):
        res = self._build(comments=self._league(), gate_pw='x')
        self.assertEqual(list(res), ['dir', 'iterations', 'frames'])
        self.assertEqual(res['dir'], os.path.join(self.tmp, 'publish'))
        self.assertEqual((res['iterations'], res['frames']), (2, 0))
        self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'index.html')))

    def test_broken_shots_manifest_surfaces_as_frames_warnings(self):
        shots = os.path.join(self.tmp, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        res = self._build(comments=self._league(), gate_pw='x')
        self.assertEqual(list(res), ['dir', 'iterations', 'frames', 'frames_warnings'])
        self.assertTrue(any('it1' in w for w in res['frames_warnings']), res['frames_warnings'])
        self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'it1', 'alpha', 'index.html')))

    def test_build_wipes_the_previous_publish_first(self):
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(os.path.join(pub, 'old'))
        with open(os.path.join(pub, 'old', 'stale.html'), 'w') as fh:
            fh.write('від минулої збірки')
        self._build(comments=False, gate_pw=None)
        self.assertFalse(os.path.exists(os.path.join(pub, 'old')))

    # ---- мітка збирача ------------------------------------------------------------------------

    def test_the_manifest_carries_who_built_it_as_its_last_key(self):
        for kind in serve.BUILD_KINDS:
            with self.subTest(build=kind):
                pub = self._build(comments=False, gate_pw=None, build=kind)['dir']
                man = json.loads(_read(os.path.join(pub, 'manifest.json')))
                self.assertEqual(man['build'], kind)
                self.assertEqual(list(man)[-1], 'build', 'мітка — останній ключ: решта файла лишається як була')
        self.assertEqual(serve.BUILD_KINDS, ('legacy', 'module'))

    def test_the_mark_is_the_only_difference_in_the_manifest(self):
        """ЛІГА-збірка змінилась рівно на одне поле маніфесту: прибери його — решта байт у байт та сама."""
        pub = self._build(comments=self._league(), gate_pw='x')['dir']
        with_mark = json.loads(_read(os.path.join(pub, 'manifest.json')))
        self.assertEqual(with_mark.pop('build'), 'legacy')
        legacy_tree = _tree(pub)
        legacy_tree.pop('manifest.json')
        direct = serve.publish_manifest(*self._manifest_args(pub))
        self.assertEqual(direct, with_mark, 'без `build=` маніфест той самий, що був до мітки')
        self.assertNotIn('build', direct)
        self.assertTrue(legacy_tree)

    def _manifest_args(self, pub):
        task, tid, its = self._args()
        trees = {it['id']: serve.iteration_pages(task, it['id']) for it in its}
        pages = serve.published_pages(task, its, trees)
        return task, tid, its, pages, {}, os.path.join(self.cfgdir), trees

    def test_the_build_kind_is_required_and_checked_before_the_disk_is_touched(self):
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(pub)
        with open(os.path.join(pub, 'keep.txt'), 'w', encoding='utf-8') as fh:
            fh.write('попередня збірка')
        task, tid, its = self._args()
        with self.assertRaises(TypeError):
            serve.build_preview(task, tid, its, comments=False, gate_pw=None)           # `build` не названо — не збираємо
        for bad in ('', 'LEGACY', 'other', None, True, 1, ['legacy']):
            with self.subTest(build=bad):
                with self.assertRaises(ValueError):
                    serve.build_preview(task, tid, its, comments=False, gate_pw=None, build=bad)
                self.assertEqual(os.listdir(pub), ['keep.txt'])

    def test_the_preview_shell_reads_only_named_fields_so_the_mark_does_not_reach_it(self):
        """Оболонка (`ext-shell.js`) бере з маніфесту названі поля; нове поле їй не потрібне й нічого не міняє."""
        src = _read(os.path.join(ROOT, 'app', 'ext-shell.js'))
        self.assertNotRegex(src, r'\bman\??\.build\b')
        self.assertNotRegex(src, r'Object\.(keys|entries|values)\(\s*man\s*\)')   # маніфест «цілком» оболонка не обходить

    # ---- comments ----------------------------------------------------------------------------

    def test_comments_on_is_the_control_for_the_comments_off_checks(self):
        """Без цього контролю «у дереві нема supabase» могло б бути простою відсутністю фічі."""
        pub = self._build(comments=self._league(), gate_pw='x')['dir']
        for b in ('comment-layer.min.js', 'supabase.min.js', 'adapter.js'):          # шар + файли адаптера модуля
            self.assertTrue(os.path.isfile(os.path.join(pub, 'comment-layer', b)), b)
        self.assertFalse(os.path.exists(os.path.join(pub, 'comment-layer', 'supabase-adapter.min.js')))
        for rel in self._inner_pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertIn('CommentLayer.init', html, rel)
            self.assertIn('dc/fixture', html, rel)
            depth_up = '../' * rel.count('/')           # `it1/alpha/index.html` → `../../`
            self.assertIn(f'{depth_up}comment-layer/comment-layer.min.js', html, rel)
        self.assertTrue(self._mentions(pub, b'supabase'),
                        'контроль: з коментарями supabase у дереві МАЄ бути')

    def test_published_pages_never_carry_the_space_or_the_inspector(self):
        """Етап 2а, Task 7: `sp=<id простору>` іде в URL інспектора ЛИШЕ на робочому місці дизайнера
        (`/commented`). Опублікована сторінка (Vercel чи тека) до `/api/ds-tokens` дістатись не може, а
        збірка ЛІГА мусить лишитись байт-у-байт такою, як була: `build_preview` кличе
        `inject_module_comment_layer` без `inspector`, `profile` і `space`. Простір ТУТ підставлено справжній
        (інакше шар вимкнено, `describe` дає `None`, і тест не бачив би витоку, навіть якби він був)."""
        real = {'id': 'design-1', 'path': self.tmp, 'legacy': False, 'integrations': False}
        self.assertIsNotNone(serve.spaces.describe(real), 'контроль: цей простір для describe реальний')
        calls = []
        orig = serve.inject_module_comment_layer

        def spy(*a, **kw):
            calls.append(kw)
            return orig(*a, **kw)
        comments = self._league()           # ДО підміни простору: рішення й задача — із простору ЛІГА фікстури, а не з підставного `real`
        task, tid, its = self._args()
        with mock.patch.object(serve.spaces, 'active_space', return_value=real), \
                mock.patch.object(serve, 'inject_module_comment_layer', spy):
            pub = serve.build_preview(task, tid, its, comments=comments, gate_pw='x', build='legacy')['dir']
        self.assertEqual(len(calls), len(SOURCE_PAGES), 'кожна сторінка пройшла через інʼєкцію')
        for kw in calls:
            self.assertEqual(set(kw) - {'version', 'inspector', 'audiences'}, set(), f'публікація передала зайве: {sorted(kw)}')
            self.assertEqual((kw.get('inspector'), kw.get('audiences')), (False, False))
        for rel in self._inner_pages(pub) + ['index.html']:
            html = _read(os.path.join(pub, rel))
            self.assertNotIn('sp=', html, rel)
            self.assertNotIn('inspector', html, rel)
            self.assertNotIn('ds-tokens', html, rel)

    def test_comments_off_leaves_no_supabase_no_layer_folder_no_injection(self):
        for gate_pw in ('x', None):
            with self.subTest(gate_pw=gate_pw):
                pub = self._build(comments=False, gate_pw=gate_pw)['dir']
                self.assertFalse(os.path.exists(os.path.join(pub, 'comment-layer')))
                for dirpath, dirs, _files in os.walk(pub):
                    self.assertNotIn('comment-layer', dirs, dirpath)
                self.assertFalse(self._mentions(pub, b'supabase'), 'supabase у дереві без коментарів')
                for rel in self._inner_pages(pub):
                    html = _read(os.path.join(pub, rel))
                    for gone in ('CommentLayer', 'comment-layer', 'supabase', 'dc-audience'):
                        self.assertNotIn(gone, html, f'{rel}: {gone}')

    def test_comments_off_still_carries_everything_else(self):
        """Прапорець вимикає ЛИШЕ коментатор: оболонка, маніфест і сторінки на місці."""
        pub = self._build(comments=False, gate_pw=None)['dir']
        for m in serve.SHELL_MODULES:
            self.assertTrue(os.path.isfile(os.path.join(pub, 'shell', m)), m)
        self.assertTrue(os.path.isfile(os.path.join(pub, 'manifest.json')))
        for rel in self._inner_pages(pub):
            self.assertIn(f'<h1>{rel}</h1>', _read(os.path.join(pub, rel)))

    # ---- gate --------------------------------------------------------------------------------

    def test_no_gate_wrapper_opens_itself_and_pages_are_untouched(self):
        for label, comments in (('league', self._league()), ('off', False)):
            with self.subTest(comments=label):
                pub = self._build(comments=comments, gate_pw=None)['dir']
                wrapper = _read(os.path.join(pub, 'index.html'))
                # ТОЧНИЙ маркер, а не підрядок: у справжнього гейта `window.__gateOpen=true;` теж є
                # (всередині `unlock()`), тож голе `__gateOpen=true` не відрізняло б обгортки з гейтом
                self.assertIn('<script>window.__gateOpen=true;</script>', wrapper)
                self.assertNotIn('authgate', wrapper)
                self.assertIn('<title>Перегляд макета</title>', wrapper)
                # `str(None)` у шаблоні дав би пароль «None», що копіюється в посилання колезі
                self.assertNotIn("__extPw='None'", wrapper)
                self.assertNotIn('__extPw="None"', wrapper)
                self.assertIn('window.__extPw="";', wrapper)
                for rel in self._inner_pages(pub):
                    html = _read(os.path.join(pub, rel))
                    self.assertNotIn('authgate', html, rel)
                    self.assertNotIn('__origTitle', html, rel)
                    self.assertEqual(_title(html), self._source_title(rel), rel)
                    self.assertEqual(html.count('<title>'), 1, rel)

    def test_no_gate_never_touches_the_gate_helpers(self):
        """Гейта нема — отже, `gate_html` не кличеться взагалі, а `_inject_gate` не чіпає сторінок."""
        with mock.patch.object(serve, 'gate_html', side_effect=AssertionError('gate_html')), \
             mock.patch.object(serve, '_inject_gate', side_effect=AssertionError('_inject_gate')):
            self._build(comments=False, gate_pw=None)

    def test_gate_is_in_the_wrapper_and_in_every_inner_page(self):
        pub = self._build(comments=self._league(), gate_pw='x')['dir']
        wrapper = _read(os.path.join(pub, 'index.html'))
        self.assertIn('authgate', wrapper)
        self.assertNotIn('<script>window.__gateOpen=true;</script>', wrapper)   # самовідкриття — лише без гейта
        self.assertIn('window.__extPw="x";', wrapper)
        for rel in self._inner_pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertIn('id="authgate"', html, rel)
            self.assertEqual(_title(html), 'Перегляд макета', rel)     # до пароля назви нема й у title
            self.assertIn('window.__origTitle=', html, rel)
        # ті самі ключі, що читає `preview_gate_state`: КОЖНА сторінка з гейтом І з цим паролем
        task = self._args()[0]
        st = serve.preview_gate_state(task, 'x')
        self.assertEqual((st['state'], st['stale'], st['ungated']), ('current', 0, 0), st)

    def test_empty_password_is_a_gate_not_the_absence_of_one(self):
        """«Без гейта» — лише `None`. `''` (забутий пароль у викликача) не мусить мовчки відкрити
        превʼю: це гейт, що відчиняється порожнім полем, і він ВИДИМИЙ у дереві."""
        pub = self._build(comments=False, gate_pw='')['dir']
        self.assertIn('id="authgate"', _read(os.path.join(pub, 'index.html')))
        for rel in self._inner_pages(pub):
            self.assertIn('id="authgate"', _read(os.path.join(pub, rel)), rel)

    def test_gate_helpers_are_looked_up_at_call_time(self):
        """`serve.gate_html` лишається підмінюваним: збірка бере його з модуля при виклику, а не
        захоплює значенням за замовчуванням (так само `preview_index_html` — тест нижче)."""
        with mock.patch.object(serve, 'gate_html', lambda tid, pw: f'<!--GATE:{tid}:{pw}-->'):
            pub = self._build(comments=False, gate_pw='pw1')['dir']
        self.assertIn('<!--GATE:fixture:pw1-->', _read(os.path.join(pub, 'index.html')))
        for rel in self._inner_pages(pub):
            self.assertIn('<!--GATE:fixture:pw1-->', _read(os.path.join(pub, rel)), rel)

    def test_preview_index_html_is_looked_up_at_call_time(self):
        """Те саме для обгортки: підміна `serve.preview_index_html` бачить і гейт, і пароль — справжні для
        ЛІГА, `NO_GATE_OPEN` і порожній пароль для превʼю без гейта."""
        seen = lambda gate, pw: f'<!--W:{gate}|{pw}-->'     # noqa: E731
        with mock.patch.object(serve, 'preview_index_html', seen), \
             mock.patch.object(serve, 'gate_html', lambda tid, pw: '<!--G-->'):
            # обидві збірки лягають в ОДНУ `publish/` (кожна її затирає) — читаємо відразу після своєї
            wrapper = os.path.join(self._build(comments=False, gate_pw='pw2')['dir'], 'index.html')
            self.assertEqual(_read(wrapper), '<!--W:<!--G-->|pw2-->')
            wrapper = os.path.join(self._build(comments=False, gate_pw=None)['dir'], 'index.html')
            self.assertEqual(_read(wrapper), f'<!--W:{serve.NO_GATE_OPEN}|-->')

    def test_empty_iteration_list_raises_before_touching_the_disk(self):
        """Порожній `its` — `ValueError` ДО будь-якої зміни: інакше збірка затерла б `publish/` і записала
        порожній маніфест (400 для дизайнера лишається в `_publish`)."""
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(pub)
        keep = os.path.join(pub, 'keep.txt')
        with open(keep, 'w', encoding='utf-8') as fh:
            fh.write('попередня збірка')
        task, tid, _its = self._args()
        for gate_pw in ('x', None):
            with self.subTest(gate_pw=gate_pw):
                with self.assertRaises(ValueError):
                    serve.build_preview(task, tid, [], comments=self._league(), gate_pw=gate_pw, build='legacy')
                self.assertEqual(os.listdir(pub), ['keep.txt'])
                self.assertEqual(_read(keep), 'попередня збірка')

    # ---- шлях ЛІГА ---------------------------------------------------------------------------

    def test_league_publish_calls_build_preview_with_comments_and_the_preview_password(self):
        base = self._server()
        for custom in (None, "o'k</script>"):
            with self.subTest(preview_password=custom):
                task = {'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1'}
                if custom:
                    task['preview_password'] = custom
                self._tasks(task)
                want = serve.preview_password(self._args()[0])          # 4d-4b: `(task, space)`, корінь `tasks.json` не читається
                self.assertEqual(want, custom or serve.DEFAULT_PREVIEW_PW)
                with mock.patch.object(serve, 'build_preview', wraps=serve.build_preview) as bp:
                    body = json.load(_post(base + '/api/publish', {'build_only': True}))
                self.assertTrue(body['ok'], body)
                self.assertEqual(bp.call_count, 1)
                args, kwargs = bp.call_args
                comments = kwargs.pop('comments')
                self.assertEqual(kwargs, {'gate_pw': want, 'build': 'legacy'})
                self.assertEqual((comments['module'].id, comments['channel']), ('supabase-comments', 'dc/fixture'))
                self.assertEqual((args[1], [i['id'] for i in args[2]]), ('fixture', ['it1', 'it2']))
                # гейт справді несе саме цей пароль — на КОЖНІЙ сторінці
                self.assertEqual(serve.preview_gate_state(args[0], want)['state'], 'current')

    def test_the_league_preview_password_is_the_secret_of_the_publish_record(self):
        """4d-4b: пароль превʼю — задачі, далі секрет `password` запису `vercel-publish` простору, далі 1100; кореня `tasks.json` не читаємо."""
        task = self._args()[0]
        with spaces.request_space('liga'):
            space = spaces.active_space()
        self.assertEqual(serve.preview_password(task, space), serve.DEFAULT_PREVIEW_PW, 'секрет запису порожній — типовий')
        liga_fixture.write_records(self.league_path, self.deai, 'liga', ('publish', 'comments'),
                                   {'publish': {'secrets': {'password': 'record-pw'}}})
        dm.reset_caches()
        self.assertEqual(serve.preview_password(task, space), 'record-pw')
        self.assertEqual(serve.preview_password(dict(task, preview_password='own-pw'), space), 'own-pw', 'пароль задачі — вище секрету запису')

    def test_league_publish_tree_equals_the_direct_build(self):
        base = self._server()
        body = json.load(_post(base + '/api/publish', {'build_only': True}))
        via_http = _tree(body['dir'])
        pw = serve.preview_password(self._args()[0])
        direct = _tree(self._build(comments=self._league(), gate_pw=pw)['dir'])
        self.assertEqual(via_http, direct)
        self.assertIn('comment-layer/comment-layer.min.js', direct)
        self.assertIn('comment-layer/adapter.js', direct)

    def test_league_publish_response_keeps_keys_and_their_order(self):
        """`ok` першим, далі `dir`/`iterations`/`frames`, потім `frames_warnings`, потім `code_stale`:
        порядок ключів JSON спостережуваний, `_publish` складає відповідь із результату збірки."""
        base = self._server()
        body = json.load(_post(base + '/api/publish', {'build_only': True}))
        self.assertEqual(list(body)[:4], ['ok', 'dir', 'iterations', 'frames'])
        self.assertEqual(body['dir'], os.path.join(self.tmp, 'publish'))
        self.assertEqual((body['ok'], body['iterations'], body['frames']), (True, 2, 0))
        tail = list(body)[4:]
        self.assertEqual(tail, [k for k in ('frames_warnings', 'code_stale') if k in tail])
        # із попередженням кадрів — воно стоїть ПЕРЕД `code_stale`
        shots = os.path.join(self.tmp, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            body = json.load(_post(base + '/api/publish', {'build_only': True}))
        self.assertEqual(list(body), ['ok', 'dir', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
        self.assertEqual(body['code_stale'], 'код новіший за процес')

    def test_league_deploy_still_works_from_the_built_dir(self):
        """Деплой (гілка БЕЗ `build_only`) читає `pub` після збірки: шов ЛІГИ (`_publish_legacy_call`) отримує ту саму теку, де
        модуль запускає `vercel link/deploy/inspect`, а скоуп із відповіді модуля йде в `_remember_vercel_scope`. Усі
        `build_only`-тести цього не бачать: вилучення збірки без `pub = built['dir']` ламало б лише справжню публікацію."""
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'vercel_project': 'pv-22222222'})
        base = self._server()
        want = os.path.join(self.tmp, 'publish')
        url = 'https://pv-22222222-abc.vercel.app'
        seen = {}

        def seam(task, tid, build_dir, proj, npx):
            seen['call'] = (tid, build_dir, proj, npx)
            return {'url': url, 'deploy_url': url, 'verified': True, 'verify': None, 'warnings': [], 'cleanup_warning': None,
                    'state': {'project': proj, 'task': tid, 'scope': 'team_x'}}

        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve, '_publish_legacy_call', seam), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, '_remember_vercel_scope',
                               lambda tid, task, org: seen.__setitem__('scope', (tid, org))), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        self.assertEqual(body.get('url'), url, body)
        self.assertEqual(body['dir'], want)
        self.assertEqual(seen['call'], ('fixture', want, 'pv-22222222', '/usr/bin/node'))   # теку збірки отримує шов
        self.assertEqual(seen['scope'], ('fixture', 'team_x'))

    def test_league_deploy_keeps_a_toggle_made_while_it_was_running(self):
        """Деплой тривав хвилини, а `_publish` тримав `meta`, прочитаний НА ВХОДІ: запис `publish_url` зі старим
        `meta` відкочував би зелену крапку, яку дизайнер перемкнув за цей час (`publish-toggle`). Тому
        `iterations.json` перечитується ПЕРЕД `save_meta`, а записуються лише власні поля публікації.
        Перемикання робить шов ЛІГИ (`_publish_legacy_call`) — під час «деплою», між читанням і записом."""
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'vercel_project': 'pv-33333333'})
        base = self._server()
        url = 'https://pv-33333333-abc.vercel.app'

        def toggled_meanwhile(task, tid, build_dir, proj, npx):
            meta = serve.load_meta(task)
            for it in meta['iterations']:
                if it['id'] == 'it2':
                    it['published'] = False
            serve.save_meta(task, meta)
            return {'url': url, 'deploy_url': url, 'verified': True, 'verify': None, 'warnings': [],
                    'cleanup_warning': None, 'state': {'project': proj, 'task': tid}}

        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve, '_publish_legacy_call', toggled_meanwhile), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, '_remember_vercel_scope', lambda tid, task, org: None), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        self.assertEqual(body.get('url'), url, body)
        meta = json.loads(_read(os.path.join(self.tmp, 'iterations.json')))
        self.assertEqual(meta['publish_url'], url)
        self.assertTrue(meta['published_at'] and meta['publish_verified'] is True)
        self.assertEqual({i['id']: i['published'] for i in meta['iterations']},
                         {'it1': True, 'it2': False}, 'перемикання під час деплою відкотилось')

    def test_league_publish_without_published_iterations_is_still_a_400(self):
        """«Немає ітерацій» лишилось у `_publish`: збірка отримує вже готовий перелік і не вгадує його."""
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [{'id': 'it1', 'date': 'x', 'note': 'н', 'published': False}]}, fh)
        base = self._server()
        with mock.patch.object(serve, 'build_preview', side_effect=AssertionError('build_preview')):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                _post(base + '/api/publish', {'build_only': True})
        self.assertEqual(ctx.exception.code, 400)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'publish')))



# ======================================================================= 4b-1: ЛІГА публікує через `vercel-publish`

BEFORE_4B1 = os.path.join(ROOT, 'tests', 'fixtures', 'legacy-publish', 'before-4b1.json')
LP_D = 'https://pv-12345678-abc.vercel.app'
LP_A = 'https://pv-12345678.vercel.app'
#: Успішний сценарій фальшивого `npx` (ті самі відповіді, що в знімку 0.8.0), плюс порожній `list` — прибирання модуля.
LP_OK = {'link': {'code': 0, 'org': 'team_x'}, 'deploy': {'code': 0, 'stdout': f'Production: {LP_D}\nAliased: {LP_A}\n'},
         'inspect': {'code': 0, 'stdout': LP_A + '\n'}, 'list': {'code': 0, 'stdout': '{"deployments": []}'}}
#: Що модуль бачить на адресі превʼю (шов `_fetch_page`) у трьох способах перевірки знімка.
LP_PAGES = {'authgate': (200, '', '<html><div id="authgate"></div></html>'),
            'nogate': (200, '', '<html>чужий сайт</html>'),
            'sso': (302, 'https://vercel.com/sso-api?next=x', '')}
#: (імʼя, сценарій npx | None — «npx нема», додаткові поля задачі, спосіб перевірки): ті самі, що зняв `record_before.py`.
LP_SCENARIOS = [
    ('success', LP_OK, {}, 'authgate'),
    ('deploy_login', {**LP_OK, 'deploy': {'code': 1, 'stderr': 'Error: Please run vercel login'}}, {}, 'authgate'),
    ('deploy_scope', {**LP_OK, 'deploy': {'code': 1, 'stderr': "Error: You don't have access to the team 'x'"}}, {}, 'authgate'),
    ('deploy_forbidden', {**LP_OK, 'deploy': {'code': 1, 'stderr': 'Error: Forbidden'}}, {}, 'authgate'),
    ('deploy_generic', {**LP_OK, 'deploy': {'code': 1, 'stderr': 'E' * 700 + 'ХВІСТ'}}, {}, 'authgate'),
    ('deploy_no_url', {**LP_OK, 'deploy': {'code': 0, 'stdout': 'Deployed, but nothing to see\n'}}, {}, 'authgate'),
    ('no_npx', None, {}, 'authgate'),
    ('known_scope', LP_OK, {'vercel_scope': 'team_x'}, 'authgate'),
    ('protected', LP_OK, {}, 'sso'),
    ('no_gate', LP_OK, {}, 'nogate'),
]


class NetTripwire:
    """Розтяжка мережі для тестів гілки ЛІГИ (як `Tripwire` у `test_vercel_publish.py`): `socket.getaddrinfo` (імена),
    `socket.socket.connect` і `connect_ex` (сама спроба зʼєднання, навіть за готовою адресою) пускають лише loopback; усе
    інше — запис у `violations` і `OSError`. Підпроцеси НЕ блокуються (тут працює фальшивий `npx`). Падіння `tearDown`, коли
    `violations` непорожній, ловить і випадок, коли код проковтнув `OSError` (`_fetch_page` модуля так і робить)."""

    def __init__(self):
        self.violations = []
        self._stack = contextlib.ExitStack()

    def start(self):
        real_gai, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
        outer = self

        def gai(host, *a, **kw):
            if host not in LOOPBACK:
                outer.violations.append(('getaddrinfo', str(host)))
                raise OSError(f'tripwire: {host}')
            return real_gai(host, *a, **kw)

        def connect(sock, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in LOOPBACK:
                outer.violations.append(('connect', str(host)))
                raise OSError(f'tripwire: {host}')
            return real_connect(sock, address)

        def connect_ex(sock, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in LOOPBACK:
                outer.violations.append(('connect_ex', str(host)))
                return 1
            return real_connect_ex(sock, address)
        for owner, name, repl in ((socket, 'getaddrinfo', gai), (socket.socket, 'connect', connect),
                                  (socket.socket, 'connect_ex', connect_ex)):
            self._stack.enter_context(mock.patch.object(owner, name, repl))

    def stop(self):
        self._stack.close()


class NetTripwireItself(unittest.TestCase):
    """Охоронець, який не може впасти, нічого не вартий: розтяжка сама доводиться."""

    def test_records_and_blocks_everything_but_loopback(self):
        trip = NetTripwire()
        trip.start()
        self.addCleanup(trip.stop)
        with self.assertRaises(OSError):
            socket.getaddrinfo('pv-12345678.vercel.app', 443)
        s = socket.socket()
        self.addCleanup(s.close)
        with self.assertRaises(OSError):
            s.connect(('93.184.216.34', 443))
        self.assertNotEqual(s.connect_ex(('93.184.216.34', 443)), 0)
        self.assertEqual([k for k, _ in trip.violations], ['getaddrinfo', 'connect', 'connect_ex'])
        socket.getaddrinfo('127.0.0.1', 80)                                   # loopback — не порушення
        self.assertEqual(len(trip.violations), 3)
        trip.stop()
        self.assertEqual(socket.getaddrinfo.__module__, 'socket')


class LegacyPublishViaModule(TaskFixture):
    """4b-1, Task 4: гілка `'legacy'` у `Handler._publish` кличе модуль `vercel-publish` (режим `cli`) через ОДИН шов —
    `serve._publish_legacy_call`. Світ: справжній модуль із каталогу, ФАЛЬШИВИЙ `npx` (`tests/fake_npx.py`) через
    `serve._node_bin`, перевірка превʼю — шов `_fetch_page` у глобалах модуля (мережі нема), шпигуни за `_registry_push`,
    `git_autocommit`, `Handler._overview_sync`. Еталон — `before-4b1.json`: поведінка 0.8.0, знята до зміни коду."""

    def setUp(self):
        super().setUp()
        # розтяжка мережі: перевірка превʼю (`_fetch_page`) підмінена, але підміна — не гарантія; будь-яка спроба вийти за
        # loopback валить тест у `tearDown`, навіть якщо код проковтнув `OSError`
        self.net = NetTripwire()
        self.net.start()
        self.addCleanup(self.net.stop)
        self.npxdir = tempfile.mkdtemp(prefix='dc-lp-npx-')
        self.addCleanup(shutil.rmtree, self.npxdir, True)
        self.module = dm.catalog().get('vercel-publish')
        self.assertEqual(self.module.status, 'ok', self.module)
        self._iterations0 = _read(os.path.join(self.tmp, 'iterations.json'))      # чистий `iterations.json` для кожного прогону

    def tearDown(self):
        violations = list(self.net.violations)
        self.net.stop()
        self.assertEqual(violations, [], 'тест вийшов у мережу')

    # ---- світ ----

    def _norm(self, text):
        """Теки задачі → `<TASK>` (спершу `realpath`: cwd фальшивого `npx` реальний, а `dir` відповіді — як записано)."""
        return text.replace(os.path.realpath(self.tmp), '<TASK>').replace(self.tmp, '<TASK>')

    def _legacy(self, sc, extra=None, mode='authgate', page=None, npx=True, extra_patches=()):
        """Одна публікація ЛІГИ через `/api/publish`; повертає знімок у формі `before-4b1.json`."""
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            fh.write(self._iterations0)           # сценарії одного тесту не бачать записів один одного (як у знімку: світ на сценарій)
        task = {'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1', 'vercel_project': 'pv-12345678', **(extra or {})}
        self._tasks(task)
        npx_path = fake_npx.make(self.npxdir, sc) if sc is not None else None
        spies = {'registry_push': [], 'git_autocommit': [], 'overview_sync': 0}
        checked = []
        want_page = page if page is not None else LP_PAGES[mode]

        def fetch(url):
            checked.append(url)
            return want_page(url) if callable(want_page) else want_page

        def overview_sync(handler):
            spies['overview_sync'] += 1
        g = self.module.fn('publish').__globals__
        base = self._server()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.dict(g, {'_fetch_page': fetch}))
            st.enter_context(mock.patch.object(serve, '_node_bin', lambda name='npx': npx_path))
            st.enter_context(mock.patch.object(serve, '_registry_push', lambda tid: spies['registry_push'].append(tid) or False))
            st.enter_context(mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: spies['git_autocommit'].append(list(a))))
            st.enter_context(mock.patch.object(serve.Handler, '_overview_sync', overview_sync))
            st.enter_context(mock.patch.object(serve, 'server_code_staleness', lambda *a, **kw: None))
            for p in extra_patches:
                st.enter_context(p)
            raw = _post(base + '/api/publish', {}).read().decode('utf-8')
        rec = json.loads(_read(os.environ['DC_TASKS_FILE']))['tasks']['fixture']
        meta = json.loads(_read(os.path.join(self.tmp, 'iterations.json')))
        if 'published_at' in meta:
            meta['published_at'] = '<set>'
        return {'response': json.loads(self._norm(raw), object_pairs_hook=lambda pairs: [list(p) for p in pairs]),
                'task': json.loads(self._norm(json.dumps(rec, ensure_ascii=False))),
                'iterations_json': meta,
                'npx_calls': [{'argv': c['argv'], 'cwd': self._norm(c['cwd'])} for c in fake_npx.calls(self.npxdir)]
                if npx_path else [],
                'spies': json.loads(self._norm(json.dumps(spies, ensure_ascii=False))), 'checked_urls': checked}

    @staticmethod
    def _resp(obs):
        return dict(obs['response'])

    # ---- 1: диференційний ----

    def test_1_differential_against_the_0_8_0_snapshot(self):
        with open(BEFORE_4B1, encoding='utf-8') as fh:
            before = json.load(fh)['scenarios']
        self.assertEqual([n for n, *_ in LP_SCENARIOS], list(before), 'сценарії тесту й знімка розійшлись')
        for name, sc, extra, mode in LP_SCENARIOS:
            with self.subTest(scenario=name):
                old = before[name]
                new = self._legacy(sc, extra, mode)
                # порядок ключів відповіді спостережуваний: порівнюємо СПИСКИ ПАР
                self.assertEqual(new['response'], old['response'])
                for key in ('task', 'iterations_json', 'spies', 'checked_urls'):
                    self.assertEqual(new[key], old[key], key)
                n = len(old['npx_calls'])
                self.assertEqual(new['npx_calls'][:n], old['npx_calls'], 'знімок — ПРЕФІКС нового argv-журналу')
                self.assertTrue(all(c['argv'][2] in ('list', 'remove') for c in new['npx_calls'][n:]),
                                [c['argv'] for c in new['npx_calls'][n:]])

    # ---- 2: прибирання ----

    def test_2_cleanup_removes_the_old_ones_and_warns_only_when_it_failed(self):
        def entry(host, created):
            return {'url': host, 'name': 'pv-12345678', 'state': 'READY', 'target': 'production', 'createdAt': created}
        listing = {'deployments': [entry('pv-12345678.vercel.app', 50)] + [entry(f'pv-12345678-o{i}.vercel.app', i) for i in range(1, 5)]}
        obs = self._legacy({**LP_OK, 'list': {'code': 0, 'stdout': json.dumps(listing)},
                            'remove': {'code': 0, 'stdout': 'Removed'}})
        removes = [c['argv'] for c in obs['npx_calls'] if c['argv'][2] == 'remove']
        self.assertEqual(sorted(a[3] for a in removes), ['pv-12345678-o1.vercel.app', 'pv-12345678-o2.vercel.app'])
        self.assertNotIn('cleanup_warning', self._resp(obs))
        self.assertEqual(self._resp(obs)['verified'], True)
        # `list` падає → попередження, і воно — ОСТАННІЙ ключ відповіді; сама публікація вдала
        obs = self._legacy({**LP_OK, 'list': {'code': 1, 'stderr': 'boom'}})
        keys = [k for k, _ in obs['response']]
        self.assertEqual(keys[-1], 'cleanup_warning', keys)
        self.assertEqual(keys[:-1], ['ok', 'dir', 'iterations', 'frames', 'url', 'deploy_url', 'verified'])
        self.assertIn('Старі публікації не прибрано', self._resp(obs)['cleanup_warning'])
        self.assertEqual(self._resp(obs)['url'], LP_A)

    def test_2b_cleanup_warning_comes_after_the_verify_keys(self):
        obs = self._legacy({**LP_OK, 'list': {'code': 1, 'stderr': 'boom'}}, mode='sso')
        keys = [k for k, _ in obs['response']]
        self.assertEqual(keys[-3:], ['verify_error', 'verify_hint', 'cleanup_warning'], keys)

    # ---- 3: deploy_error ----

    def test_3_deploy_error_is_the_0_8_0_text_built_from_the_full_raw_output(self):
        pad = ''.join(chr(0x41 + i % 26) for i in range(1000))
        for code, marker in (('vercel-login', ' please run vercel login'), ('vercel-scope', ' scope not found'),
                             ('vercel-auth', ' forbidden')):
            with self.subTest(code=code):
                raw = pad[:-len(marker)] + marker
                self.assertEqual(len(raw), 1000)
                obs = self._legacy({**LP_OK, 'deploy': {'code': 1, 'stderr': raw}})
                hint = serve._LEGACY_DEPLOY_HINTS[code]
                want = f'{hint}\n\n— вивід vercel —\n{raw[-300:]}'
                self.assertEqual(self._resp(obs)['deploy_error'], want)
                self.assertEqual(len(self._resp(obs)['deploy_error']), len(hint) + len('\n\n— вивід vercel —\n') + 300)
        with self.subTest(code='vercel-deploy'):
            raw = pad[:1000]
            obs = self._legacy({**LP_OK, 'deploy': {'code': 1, 'stderr': raw}})
            self.assertEqual(self._resp(obs)['deploy_error'], raw[-400:])
            self.assertEqual(len(self._resp(obs)['deploy_error']), 400)
        with self.subTest(code='empty output'):                 # 0.8.0 віддавало '' — тепер людський рядок ядра
            obs = self._legacy({**LP_OK, 'deploy': {'code': 1}})
            self.assertEqual(self._resp(obs)['deploy_error'], serve._LEGACY_EMPTY_OUTPUT)
        with self.subTest(code='vercel-no-url'):
            obs = self._legacy({**LP_OK, 'deploy': {'code': 0, 'stdout': 'нічого'}})
            self.assertEqual(self._resp(obs)['deploy_error'], serve._LEGACY_NO_URL)

    def test_3b_the_hint_texts_are_the_0_8_0_texts(self):
        self.assertEqual(set(serve._LEGACY_DEPLOY_HINTS), {'vercel-login', 'vercel-scope', 'vercel-auth'})
        self.assertTrue(serve._LEGACY_DEPLOY_HINTS['vercel-login'].startswith('Vercel не авторизований на цій машині'))
        self.assertIn('tasks.json → vercel_scope', serve._LEGACY_DEPLOY_HINTS['vercel-scope'])
        self.assertTrue(serve._LEGACY_DEPLOY_HINTS['vercel-auth'].startswith('Немає доступу до Vercel-проєкту'))
        self.assertIn('пароль 1100', serve._LEGACY_PROTECTION_HINT)

    # ---- 4: захист Vercel ----

    def test_4_vercel_protection_gives_the_reason_and_the_hint(self):
        obs = self._legacy(LP_OK, mode='sso')
        resp = self._resp(obs)
        self.assertIs(resp['verified'], False)
        self.assertEqual(resp['verify_error'], 'vercel_protection')
        self.assertEqual(resp['verify_hint'], serve._LEGACY_PROTECTION_HINT)
        self.assertEqual(obs['iterations_json']['publish_verified'], False)
        # чужий сайт без гейта: причина є, підказки про захист нема
        resp = self._resp(self._legacy(LP_OK, mode='nogate'))
        self.assertEqual(resp['verify_error'], 'на URL відповідає не наш макет (немає гейта)')
        self.assertNotIn('verify_hint', resp)

    # ---- 5: імʼя мінтиться ДО деплою ----

    def test_5_the_project_name_is_minted_before_the_deploy(self):
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1'})          # без `vercel_project`
        npx = fake_npx.make(self.npxdir, {**LP_OK, 'deploy': {'code': 1, 'stderr': 'boom'}})
        base = self._server()
        with mock.patch.object(serve, '_node_bin', lambda name='npx': npx), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        self.assertEqual(body['deploy_error'], 'boom')
        rec = json.loads(_read(os.environ['DC_TASKS_FILE']))['tasks']['fixture']
        self.assertRegex(rec['vercel_project'], r'^pv-\d{8}$')
        link = next(c['argv'] for c in fake_npx.calls(self.npxdir) if c['argv'][2] == 'link')
        self.assertEqual(link[-2:], ['--project', rec['vercel_project']])

    # ---- 6: скоуп ----

    def _legacy_via_seam(self, task_extra, result):
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1', 'vercel_project': 'pv-12345678', **task_extra})
        base = self._server()
        seen = []

        def seam(task, tid, build_dir, proj, npx):
            seen.append((dict(task), tid, build_dir, proj, npx))
            return result
        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/npx'), \
             mock.patch.object(serve, '_publish_legacy_call', seam), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        return body, seen

    @staticmethod
    def _seam_result(**over):
        res = {'url': LP_A, 'deploy_url': LP_D, 'verified': True, 'verify': None, 'warnings': [], 'cleanup_warning': None,
               'state': {'project': 'pv-12345678', 'task': 'fixture', 'scope': 'team_x'}}
        res.update(over)
        return res

    def test_6_the_scope_from_the_module_state_is_remembered_but_never_overwritten(self):
        _body, seen = self._legacy_via_seam({}, self._seam_result())
        rec = json.loads(_read(os.environ['DC_TASKS_FILE']))['tasks']['fixture']
        self.assertEqual(rec['vercel_scope'], 'team_x')
        self.assertEqual(seen[0][1:4], ('fixture', os.path.join(self.tmp, 'publish'), 'pv-12345678'))
        _body, _seen = self._legacy_via_seam({'vercel_scope': 'team_old'}, self._seam_result())
        rec = json.loads(_read(os.environ['DC_TASKS_FILE']))['tasks']['fixture']
        self.assertEqual(rec['vercel_scope'], 'team_old')
        _body, _seen = self._legacy_via_seam({}, self._seam_result(state={'project': 'pv-12345678', 'task': 'fixture'}))
        rec = json.loads(_read(os.environ['DC_TASKS_FILE']))['tasks']['fixture']
        self.assertNotIn('vercel_scope', rec)

    # ---- OSError після вдалого деплою (як у 0.8.0) ----

    def test_an_oserror_after_a_successful_deploy_is_a_deploy_error_not_a_500(self):
        """У 0.8.0 весь блок після деплою стояв у `try … except (OSError, …) as e: deploy_error = str(e)`: збій реєстру чи запису
        `iterations.json` давав `deploy_error` у відповіді 200, а `git_autocommit` і `_overview_sync` усе одно відбувались.
        `url` пишеться у відповідь лише після `save_meta` — тож при збої раніше його там нема."""
        def boom(msg):
            def raiser(*a, **kw):
                raise OSError(msg)
            return raiser
        cases = {'registry': ([mock.patch.object(serve, '_registry_push', boom('реєстр недоступний'))],
                              'реєстр недоступний', ['ok', 'dir', 'iterations', 'frames', 'deploy_error'], False),
                 'save_meta': ([mock.patch.object(serve, 'save_meta', boom('диск повний'))],
                               'диск повний', ['ok', 'dir', 'iterations', 'frames', 'deploy_error'], False),
                 'after_url': ([mock.patch.object(serve, '_not_task_link', boom('пізній збій'))],
                               'пізній збій', ['ok', 'dir', 'iterations', 'frames', 'url', 'deploy_url', 'deploy_error'], True)}
        for name, (patches, text, keys, wrote) in cases.items():
            with self.subTest(failing=name):
                obs = self._legacy(LP_OK, extra_patches=patches)          # `_post` кидає на не-200: статус 200 доведено
                self.assertEqual([k for k, _ in obs['response']], keys)
                self.assertEqual(self._resp(obs)['deploy_error'], text)
                self.assertEqual(obs['spies']['git_autocommit'], [['<TASK>', 'publish: 2 iteration(s)']])
                self.assertEqual(obs['spies']['overview_sync'], 1)
                self.assertEqual('publish_url' in obs['iterations_json'], wrote)

    # ---- 7: publish_remote ----

    def test_7_publish_remote_never_appears_for_the_league(self):
        obs = self._legacy(LP_OK)
        self.assertNotIn('publish_remote', obs['iterations_json'])
        self.assertEqual(obs['iterations_json']['publish_url'], LP_A)
        self.assertEqual(sorted(obs['iterations_json']), ['iterations', 'publish_url', 'publish_verified', 'published_at'])

    # ---- 8: модуль не завантажився ----

    def test_8_a_module_that_is_not_loaded_is_refused_before_any_build(self):
        """Було: «модуль не завантажено» — `deploy_error` ПІСЛЯ збірки (неявний постачальник не питав каталогу). 4d-4b: ЛІГА публікує лише явним
        записом `vercel-publish`, тож незавантажений модуль (запис є, ввімкнений) = помилка `module-error` (502, рішення I2) ДО збірки, жоден `vercel` не
        запускається, git і дашборд не чіпаються (замінено тим, що відмова раніша й чесніша)."""
        real = serve.deai_modules.catalog
        broken = types.SimpleNamespace(id='vercel-publish', status='error', roles=('publish',), origin='builtin')
        variants = {'missing': lambda *a, **kw: {k: v for k, v in real(*a, **kw).items() if k != 'vercel-publish'},
                    'broken': lambda *a, **kw: {**real(*a, **kw), 'vercel-publish': broken}}
        for name, fake in variants.items():
            with self.subTest(catalog=name):
                base = self._server()
                with mock.patch.object(serve.deai_modules, 'catalog', fake), \
                        mock.patch.object(serve, 'build_preview') as bp, \
                        mock.patch.object(serve, '_node_bin') as node, \
                        mock.patch.object(serve, 'git_autocommit') as gc:
                    with self.assertRaises(urllib.error.HTTPError) as cm:
                        _post(base + '/api/publish', {})
                body = json.loads(cm.exception.read().decode('utf-8'))
                # Рішення контролера 4d-4b (I2): ЯВНО ввімкнений запис, який нічим обслужити, — ПОМИЛКА (`module-error`, 502), а не «нікого» (409).
                self.assertEqual((cm.exception.code, body['ok'], body['code']), (502, False, 'module-error'))
                for spy in (bp, node, gc):
                    spy.assert_not_called()

    # ---- 9: звичайний простір ----

    def test_9_an_ordinary_space_passes_gated_to_the_module(self):
        task, tid, its = self._args()
        prov = types.SimpleNamespace(id='vercel-publish')
        for secrets, want in (({'password': 'pw1'}, True), ({'password': ''}, False), ({}, False)):
            with self.subTest(secrets=secrets):
                seen = []

                def call(module, fn, ctx, build_dir, task_arg, **kw):
                    seen.append(task_arg)
                    return {'url': LP_A, 'state': {}, 'verified': True}
                sent = _Stub()
                with mock.patch.object(serve.deai_modules, 'module_ctx', lambda sp, p: {'secrets': dict(secrets)}), \
                     mock.patch.object(serve.deai_modules, 'call', call), \
                     mock.patch.object(serve, 'publish_comments', lambda *a, **kw: (False, None)), \
                     mock.patch.object(serve, 'build_preview', lambda *a, **kw: {'dir': self.tmp, 'iterations': 2, 'frames': 0}):
                    serve._publish_by_url(sent, prov, {}, {'id': 'x'}, tid, task, its)
                self.assertEqual(sent.sent[0][1]['ok'], True, sent.sent)
                self.assertIs(seen[0]['gated'], want)
                self.assertEqual(set(seen[0]), {'id', 'title', 'dir', 'state', 'gated'})
                self.assertNotIn('legacy_state', seen[0])        # ключ довіри до стану ставить ЛИШЕ адаптер ЛІГИ (4b-1)

    def test_9b_an_ordinary_space_gets_the_tail_of_a_vercel_deploy_failure_not_the_head(self):
        """`ModuleError.message` — ГОЛОВА (300 знаків) останніх 4000 знаків виводу CLI, а корисне — у кінці: звичайний простір
        (`publish_target: url`) отримує ХВІСТ `full`. Інші коди й ЛІГА (`_legacy_deploy_error`) — без змін."""
        task, tid, its = self._args()
        prov = types.SimpleNamespace(id='vercel-publish')
        full = 'HEAD-' + 'x' * 1000 + 'THE-REASON-AT-THE-END'
        for code, want in (('vercel-deploy', full[-300:]), ('vercel-login', full[:300]), ('module-error', full[:300])):
            with self.subTest(code=code):
                def call(module, fn, ctx, build_dir, task_arg, **kw):
                    raise serve.deai_modules.ModuleError(code, message=full)
                sent = _Stub()
                with mock.patch.object(serve.deai_modules, 'module_ctx', lambda sp, p: {'secrets': {}}), \
                     mock.patch.object(serve.deai_modules, 'call', call), \
                     mock.patch.object(serve, 'publish_comments', lambda *a, **kw: (False, None)), \
                     mock.patch.object(serve, 'build_preview', lambda *a, **kw: {'dir': self.tmp, 'iterations': 2, 'frames': 0}):
                    with self.assertRaises(serve.deai_modules.ModuleError) as cm:
                        serve._publish_by_url(sent, prov, {}, {'id': 'x'}, tid, task, its)
                self.assertEqual((cm.exception.code, cm.exception.message), (code, want))
                self.assertEqual(cm.exception.status, serve.deai_modules.ModuleError(code).status)
        tail = serve.deai_modules.ModuleError('vercel-deploy', message=full)
        self.assertIn('THE-REASON-AT-THE-END', tail.full[-300:])
        self.assertNotIn('THE-REASON-AT-THE-END', tail.message)               # доказ, що без правки людина бачила б голову

    # ---- 10: транспорту в ядрі нема ----

    def test_10_the_vercel_transport_is_gone_from_the_core(self):
        src = _read(os.path.join(ROOT, 'app', 'serve.py'))
        for needle in ("'vercel', 'deploy'", "'vercel', 'link'", "'vercel', 'inspect'", 'def _deploy_urls', 'def _stable_alias',
                       'def _check_published', 'def _deploy_hint'):
            self.assertNotIn(needle, src, needle)
        for name in ('_deploy_urls', '_stable_alias', '_check_published', '_deploy_hint'):
            self.assertFalse(hasattr(serve, name), name)

    # ---- шов ----

    def test_the_seam_hands_the_module_a_cli_ctx_and_the_gated_task(self):
        seen = {}

        def call(module, fn, ctx, build_dir, task_arg, **kw):
            seen.update(module=module.id, fn=fn, ctx=ctx, build_dir=build_dir, task=task_arg)
            return {'url': LP_A, 'deploy_url': LP_D, 'state': {'project': 'p', 'task': 't'}, 'verified': True}
        with mock.patch.object(serve.deai_modules, 'call', call):
            res = serve._publish_legacy_call({'title': 'T', 'dir': '/d', 'vercel_scope': 'team_x'}, 'tid', '/b', 'pv-1', '/bin/npx')
        self.assertEqual(res['url'], LP_A)
        self.assertEqual((seen['module'], seen['fn'], seen['build_dir']), ('vercel-publish', 'publish', '/b'))
        self.assertEqual(seen['task'], {'id': 'tid', 'title': 'T', 'dir': '/d', 'gated': True, 'legacy_state': True,
                                        'state': {'project': 'pv-1', 'task': 'tid', 'scope': 'team_x'}})
        self.assertEqual(seen['ctx']['settings'], {'auth': 'cli', 'team': ''})
        self.assertEqual(seen['ctx']['secrets'], {})
        self.assertEqual(seen['ctx']['find_tool']('npx'), '/bin/npx')
        self.assertIsNone(seen['ctx']['find_tool']('node'))
        self.assertIs(seen['ctx']['ModuleError'], serve.deai_modules.ModuleError)
        for bad in ({'url': LP_A, 'state': {}, 'verified': True},                        # без `deploy_url`
                    {'url': 'http://x.vercel.app', 'deploy_url': LP_D, 'state': {}, 'verified': True},
                    {'url': LP_A, 'deploy_url': LP_D, 'state': {}, 'verified': 'yes'}):
            with self.subTest(bad=bad), mock.patch.object(serve.deai_modules, 'call', lambda *a, **kw: bad):
                with self.assertRaises(serve.deai_modules.ModuleError):
                    serve._publish_legacy_call({'title': 'T', 'dir': '/d'}, 'tid', '/b', 'pv-1', '/bin/npx')

    def test_the_scope_is_not_put_in_the_state_when_the_task_has_none(self):
        seen = {}
        with mock.patch.object(serve.deai_modules, 'call', lambda m, f, c, b, t, **kw: seen.update(t=t) or
                               {'url': LP_A, 'deploy_url': LP_D, 'state': {}, 'verified': True}):
            serve._publish_legacy_call({'title': 'T', 'dir': '/d'}, 'tid', '/b', 'pv-1', '/bin/npx')
        self.assertEqual(seen['t']['state'], {'project': 'pv-1', 'task': 'tid'})

    def test_a_failure_of_the_module_never_leaves_a_half_written_publication(self):
        """Відмова модуля: у `iterations.json` нема ні адреси, ні часу публікації, реєстр не чіпано."""
        obs = self._legacy({**LP_OK, 'deploy': {'code': 1, 'stderr': 'boom'}})
        self.assertNotIn('publish_url', obs['iterations_json'])
        self.assertEqual(obs['spies']['registry_push'], [])
        self.assertEqual(obs['spies']['git_autocommit'], [['<TASK>', 'publish: 2 iteration(s)']])


# ============================================================================== Task 4b: диспетчер ролі `publish`

MID = 'static-publish'
ISO_UTC = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
#: `preview_gate`, яким `/api/task` відповідає, коли публікує модуль: ТА САМА форма, що в `preview_gate_state`
#: (UI читає ті самі ключі), `state: 'module'` і нулі — «без гейта» для локальної збірки не попередження.
MODULE_GATE = {'state': 'module', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0}
LOOPBACK = ('127.0.0.1', 'localhost', '::1')


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


def _write_task_files(task_dir):
    """Ті самі сторінки й ітерації, що в `TaskFixture` (`SOURCE_PAGES`; обидві ітерації опубліковані)."""
    for rel, title in SOURCE_PAGES.items():
        src = os.path.join(task_dir, 'iterations', rel)
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src, 'w', encoding='utf-8') as fh:
            fh.write(f'<!DOCTYPE html><html><head><title>{title}</title></head>'
                     f'<body><h1>{rel}</h1></body></html>')
    _write_json(os.path.join(task_dir, 'iterations', 'it1', 'pages.json'),
                {'pages': [{'id': 'alpha', 'name': 'Альфа'}, {'id': 'gamma', 'name': 'Гамма'}]})
    _write_json(os.path.join(task_dir, 'iterations.json'), {'iterations': [
        {'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'перша', 'published': True},
        {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'друга', 'published': True}],
        'publish_url': None})


class Tripwire:
    """Усе, що виходить з машини, — у запис (`hits`) і `OSError('tripwire')`: мережа (`urlopen`,
    `create_connection`) і БУДЬ-ЯКИЙ підпроцес (на шляху модуля нема ні `git`, ні `npx`, ні `overview_push.py`).
    Loopback пускається лише на порти ЦЬОГО тесту (`allow_ports`: сервер у процесі): будь-який інший порт
    (8765 справжнього канваса!) теж «вихід»."""

    def __init__(self):
        self.hits = []
        self.allow_ports = set()
        real_urlopen, real_cc = urllib.request.urlopen, socket.create_connection

        def urlopen(target, *a, **kw):
            u = urllib.parse.urlparse(getattr(target, 'full_url', None) or str(target))
            if u.hostname in LOOPBACK and u.port in self.allow_ports:
                return real_urlopen(target, *a, **kw)
            self.hits.append(('urlopen', getattr(target, 'full_url', str(target))))
            raise OSError('tripwire')

        def create_connection(address, *a, **kw):
            if address[0] in LOOPBACK and address[1] in self.allow_ports:
                return real_cc(address, *a, **kw)
            self.hits.append(('socket', f'{address[0]}:{address[1]}'))
            raise OSError('tripwire')

        def spawn(kind):
            def blocked(args, *a, **kw):
                self.hits.append((kind, args if isinstance(args, str) else ' '.join(map(str, args))))
                raise OSError('tripwire')
            return blocked

        self._stack = contextlib.ExitStack()
        for owner, name, repl in ((urllib.request, 'urlopen', urlopen),
                                  (socket, 'create_connection', create_connection),
                                  (subprocess, 'run', spawn('run')), (subprocess, 'Popen', spawn('popen'))):
            self._stack.enter_context(mock.patch.object(owner, name, repl))

    def stop(self):
        self._stack.close()


class TripwireItself(unittest.TestCase):
    """Охоронець, який не може впасти, нічого не вартий: розтяжка сама доводиться."""

    def test_records_and_blocks_every_way_out_but_the_allowed_loopback_port(self):
        trip = Tripwire()
        self.addCleanup(trip.stop)
        with self.assertRaises(OSError):
            urllib.request.urlopen('https://example.invalid/x')
        with self.assertRaises(OSError):
            socket.create_connection(('example.invalid', 443))
        with self.assertRaises(OSError):
            subprocess.run(['git', 'push'])
        with self.assertRaises(OSError):
            subprocess.Popen(['npx', 'vercel'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', 8765), timeout=1)       # порт справжнього канваса
        self.assertEqual([k for k, _ in trip.hits], ['urlopen', 'socket', 'run', 'popen', 'socket'])
        trip.stop()
        self.assertEqual(urllib.request.urlopen.__module__, 'urllib.request')
        self.assertEqual(subprocess.run.__module__, 'subprocess')


class _Stub:
    """Мінімум, який має зовнішня заглушка `Handler` (`boss_autopublish.py`): рівно ті чотири методи, що
    `_publish` кликав ДО диспетчера. Нічого іншого з обробника диспетчер не бере."""

    def __init__(self):
        self.sent = []
        self.overview = 0

    def _current_task(self):
        return serve.task_for(serve.load_tasks(), None)

    def send_error(self, code, message=None):
        self.sent.append(('error', code, message))

    def _send_json(self, obj, status=200):
        self.sent.append((status, obj))

    def _overview_sync(self):
        self.overview += 1


class DispatchWorld(unittest.TestCase):
    """Світ (без тестів — їх додають `Dispatch` і `PublishedRoute`): шар просторів увімкнено; `off` (без
    інтеграцій, задача `tx`, поточний) і `on` (з інтеграціями, задача `ty`); сервер у процесі; розтяжка;
    шпигуни за точками виходу ЛІГА."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-disp-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, 'home')
        # DEAI_HOME — у домівці (як у test_static_publish): інакше тимчасова тека macOS (`/var`) дала б
        # `path-system` раніше за `path-deai-home`
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        os.makedirs(self.deai, mode=0o700)
        env = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DEAI_HOME': self.deai,
            'DC_TASKS_FILE': os.path.join(self.tmp, 'legacy', 'tasks.json'),     # старий файл: лише вигадана пара Supabase (4d-2)
            'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'})
        env.start()
        self.addCleanup(env.stop)
        # справжня тека інструмента (репозиторій) не може стати ціллю публікації, навіть якщо правило колись
        # зламається, а `path-tool` перевіряється саме як причина
        tool = mock.patch.object(spaces, 'ROOT', self.tool)
        tool.start()
        self.addCleanup(tool.stop)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        self.off_path = os.path.join(self.home, 'deai-work', 'off')
        self.on_path = os.path.join(self.home, 'deai-work', 'on')
        self.off = self._space('off', self.off_path, False, 'tx')
        self.on = self._space('on', self.on_path, True, 'ty')
        # 4d-4b: простір з інтеграціями («ЛІГА») публікує й веде коментарі лише ЯВНИМИ записами `vercel-publish` і `supabase-comments`
        # (запасного шляху нема); пароль превʼю в записі порожній — типовий 1100, як було. Пишемо ДО реєстру й до кешів модулів.
        liga_fixture.write_records(self.on_path, self.deai, 'on', ('publish', 'comments'),
                                   {'publish': {'secrets': {'password': ''}},
                                    'comments': {'settings': {'url': sbconf.SB_URL}, 'secrets': {'key': sbconf.SB_KEY}}}, 'On')
        atomic_write_json(os.path.join(self.deai, 'spaces.json'),
                          {'version': 1, 'current': 'off', 'spaces': [self.off, self.on]})
        self.tx_dir = os.path.join(self.off_path, 'tx')
        self.ty_dir = os.path.join(self.on_path, 'ty')
        self.folder = os.path.join(self.home, 'deai-published', 'off')
        self.dest = os.path.join(self.folder, 'tx')
        # розтяжка ПЕРШОЮ, сервер — після неї (його порт їй дозволяється)
        self.trip = Tripwire()
        self.addCleanup(self.trip.stop)
        self.spies = {}
        for owner, name in ((serve.Handler, '_overview_sync'), (serve, '_registry_push'),
                            (serve, 'git_autocommit'), (serve, '_publish_legacy_call'), (serve, '_node_bin'),
                            (serve, '_remember_vercel_scope')):
            patch = mock.patch.object(owner, name)
            self.spies[name] = patch.start()
            self.addCleanup(patch.stop)
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        self.port = httpd.server_address[1]
        self.trip.allow_ports.add(self.port)
        self.base = f'http://127.0.0.1:{self.port}'

    # ---- фікстури ----

    def _space(self, sid, path, integrations, tid):
        """Простір `sid` із задачею `tid`: тека, `space.json`, `tasks.json`, файли задачі. Повертає запис реєстру."""
        _write_json(os.path.join(path, 'space.json'), {'name': sid.title(), 'color': 'space-1'})
        _write_json(os.path.join(path, 'tasks.json'), {
            'design_work_root': path, 'current': tid,
            'tasks': {tid: {'title': f'Задача {tid}', 'dir': os.path.join(path, tid)}}})
        _write_task_files(os.path.join(path, tid))
        return {'id': sid, 'path': path, 'legacy': False, 'integrations': integrations}

    def replace_publisher(self, space, mid):
        """Власний модуль публікації ЗАМІНЮЄ запис ЛІГИ `vercel-publish` у `on` (одна роль — один постачальник, інакше `role-taken`): запис
        спершу вимикається (налаштування й секрет лишаються), далі вмикається `mid`. У інших просторах — просто вмикає."""
        if space['id'] == self.on['id']:
            dm.write_module_state(space, 'vercel-publish', enabled=False)
        dm.write_module_state(space, mid, enabled=True)

    def _register(self, rec):
        """Додати запис простору в реєстр (мимо `create_space`: він відмовив би в повторі id задачі)."""
        path = os.path.join(self.deai, 'spaces.json')
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
        reg['spaces'].append(rec)
        atomic_write_json(path, reg)
        return rec

    def _call(self, method, path, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, raw = r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read().decode('utf-8')
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw                    # `send_error` відповідає HTML

    def post(self, path, payload=None, headers=None):
        return self._call('POST', path, {} if payload is None else payload, headers)

    def get(self, path, headers=None):
        return self._call('GET', path, None, headers)

    def meta(self, task_dir=None):
        return json.loads(_read(os.path.join(task_dir or self.tx_dir, 'iterations.json')))

    def set_folder(self, value, space=None):
        dm.write_module_state(space or self.off, MID, settings={'folder': value})

    def assert_quiet(self):
        """Жодного виходу назовні: розтяжка порожня, а жодна точка виходу ЛІГА не кликана."""
        self.assertEqual(self.trip.hits, [])
        for name, spy in self.spies.items():
            self.assertEqual(spy.call_count, 0, f'{name} кликано на шляху модуля')

    def assert_nothing_built(self):
        self.assertFalse(os.path.exists(os.path.join(self.tx_dir, 'publish')), 'publish/ зібрано до відмови')


class Dispatch(DispatchWorld):
    """Диспетчер ролі `publish` у `Handler._publish` (Task 4b): хто публікує, куди, під якими замками."""

    # ---- публікація у простір без інтеграцій ----

    def test_publish_lands_in_the_folder_with_a_marker_and_writes_publish_local(self):
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames'])
        self.assertEqual(body['local'], {'path': self.dest, 'url': '/published/off/tx/'})
        self.assertEqual((body['ok'], body['iterations'], body['frames']), (True, 2, 0))
        for rel in ('index.html', 'manifest.json', *SOURCE_PAGES):
            self.assertTrue(os.path.isfile(os.path.join(self.dest, rel)), rel)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))
        self.assertEqual(os.listdir(self.folder), ['tx'])                  # ні .tmp-, ні .old-
        meta = self.meta()
        pl = meta['publish_local']
        self.assertEqual((pl['module'], pl['path']), (MID, self.dest))
        self.assertRegex(pl['published_at'], ISO_UTC)
        self.assertEqual(set(pl), {'module', 'path', 'published_at'})
        # поля ВЕРСІЇ ЛІГА не чіпаємо: `publish_url`, `published_at`, `publish_verified`
        self.assertIsNone(meta['publish_url'])
        self.assertNotIn('published_at', meta)
        self.assertNotIn('publish_verified', meta)
        self.assertEqual([i['published'] for i in meta['iterations']], [True, True])
        self.assert_quiet()

    def test_the_build_has_no_comment_layer_and_no_supabase(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        self.assertFalse(os.path.exists(os.path.join(self.dest, 'comment-layer')))
        for dirpath, _dirs, files in os.walk(self.dest):
            if os.path.relpath(dirpath, self.dest).split(os.sep)[0] == 'shell':
                continue
            for fn in files:
                self.assertNotIn(b'supabase', _bytes(os.path.join(dirpath, fn)).lower(), fn)

    def test_republish_replaces_the_folder_and_refreshes_publish_local(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        first = self.meta()['publish_local']
        with open(os.path.join(self.dest, 'stale.txt'), 'w') as fh:
            fh.write('від минулої публікації')
        with open(os.path.join(self.tx_dir, 'iterations', 'it2', 'index.html'), 'w', encoding='utf-8') as fh:
            fh.write('<!DOCTYPE html><html><head><title>v2</title></head><body><h1>друга версія</h1></body></html>')
        time.sleep(1.1)                                                     # `published_at` — з точністю до секунди
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertFalse(os.path.exists(os.path.join(self.dest, 'stale.txt')))
        self.assertIn('друга версія', _read(os.path.join(self.dest, 'it2', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))
        self.assertEqual(os.listdir(self.folder), ['tx'])
        again = self.meta()['publish_local']
        self.assertEqual(again['path'], first['path'])
        self.assertGreater(again['published_at'], first['published_at'])
        self.assert_quiet()

    def test_build_only_builds_the_task_folder_and_publishes_nothing(self):
        st, body = self.post('/api/publish', {'build_only': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body)[:4], ['ok', 'dir', 'iterations', 'frames'])
        self.assertEqual(body['dir'], os.path.join(self.tx_dir, 'publish'))
        self.assertNotIn('local', body)
        self.assertTrue(os.path.isfile(os.path.join(body['dir'], 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(body['dir'], 'comment-layer')))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')), 'тека публікації зʼявилась')
        self.assertNotIn('publish_local', self.meta())
        self.assert_quiet()

    def test_response_keys_and_their_order_carry_frames_warnings_and_code_stale(self):
        shots = os.path.join(self.tx_dir, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            st, body = self.post('/api/publish', {'build_only': True})
            self.assertEqual(list(body), ['ok', 'dir', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
        self.assertTrue(any('it1' in w for w in body['frames_warnings']), body['frames_warnings'])
        self.assertEqual(body['code_stale'], 'код новіший за процес')

    def test_no_iterations_marked_is_the_same_400_before_any_build(self):
        meta = self.meta()
        for it in meta['iterations']:
            it['published'] = False
        _write_json(os.path.join(self.tx_dir, 'iterations.json'), meta)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 400)
        self.assertIn('no iterations marked for publish - toggle the green dot first', body)
        self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    def test_a_custom_folder_setting_is_honoured(self):
        custom = os.path.join(self.home, 'pubs', 'custom')
        self.set_folder(custom)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['local']['path'], os.path.join(custom, 'tx'))
        self.assertTrue(os.path.isfile(os.path.join(custom, 'tx', 'index.html')))
        self.assertFalse(os.path.exists(self.folder))

    # ---- `no-publish-module`, `bad-folder` ----

    def test_a_space_without_integrations_and_without_a_module_gets_409_no_publish_module(self):
        dm.write_module_state(self.off, MID, enabled=False)
        st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'no-publish-module'))
        self.assertTrue(body['error'])
        self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    def test_a_bad_folder_is_409_bad_folder_and_the_build_never_starts(self):
        """Теку перевіряє ДИСПЕТЧЕР до збірки: модуль перевірив би її теж (друга лінія), але `publish/` уже було б
        зібрано (`rmtree` + повна збірка задарма). Відповідь від цього не залежить — тож доводиться саме
        `publish/`, якого нема."""
        folders = {
            'тека задачі': self.tx_dir, 'тека простору': self.off_path, 'домівка': self.home, '~': '~',
            'усередині DEAI_HOME': os.path.join(self.deai, 'pub'), 'тека інструмента': os.path.join(self.tool, 'pub')}
        for what, value in folders.items():
            with self.subTest(what):
                self.set_folder(value)
                st, body = self.post('/api/publish')
                self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'bad-folder'), body)
                self.assertTrue(body['error'].startswith('path-'), body)
                self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    # ---- id задачі, який модуль відмовить, і шлях, який він повернув ----

    def _task_space(self, sid, tid):
        """Простір без інтеграцій `sid` із задачею `tid`, зроблений поточним (запис реєстру мимо `switch_space`)."""
        rec = self._register(self._space(sid, os.path.join(self.home, 'deai-work', sid), False, tid))
        path = os.path.join(self.deai, 'spaces.json')
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
        reg['current'] = sid
        atomic_write_json(path, reg)
        return rec

    def test_a_task_id_the_module_would_refuse_is_400_before_any_build(self):
        """`NAME_RE` сервера пускає Unicode, `static-publish` — лише `[A-Za-z0-9_-]{1,128}` і не імена пристроїв
        Windows: раніше такий id давав 502 `module-error` ПІСЛЯ збірки (`rmtree` + повна збірка задарма)."""
        for i, tid in enumerate(('задача', 'x' * 129, 'NUL', 'com1', 'Aux')):
            with self.subTest(tid=tid[:20]):
                rec = self._task_space(f'bad{i}', tid)
                task_dir = os.path.join(rec['path'], tid)
                for payload in ({}, {'build_only': True}):
                    st, body = self.post('/api/publish', payload)
                    self.assertEqual((st, body.get('ok'), body.get('code')), (400, False, 'bad-task-id'), body)
                    self.assertTrue(body['error'])
                    self.assertFalse(os.path.exists(os.path.join(task_dir, 'publish')), 'publish/ зібрано до відмови')
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')), 'тека публікації зачеплена')
        self.assert_quiet()

    def test_task_ids_the_module_accepts_still_publish(self):
        """Контроль до тесту вище: перевірка не різе зайвого (межа 128, великі літери, `_` і `-`)."""
        for i, tid in enumerate(('x' * 128, 'Task_1-b', 'console')):
            with self.subTest(tid=tid[:20]):
                self._task_space(f'ok{i}', tid)
                st, body = self.post('/api/publish')
                self.assertEqual(st, 200, body)
                self.assertEqual(body['local']['path'], os.path.join(self.home, 'deai-published', f'ok{i}', tid))

    def test_a_module_that_returns_a_path_other_than_the_destination_is_502_and_writes_nothing(self):
        """Адреса в `publish_local` і в `local` мусить бути тією, що перевірено й замкнено: `<тека>/<задача>`."""
        module = dm.catalog()[MID]
        other = os.path.join(self.home, 'elsewhere', 'tx')
        with mock.patch.dict(module._fns, {'publish': lambda ctx, build, task: {'path': other}}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), body)
        self.assertNotIn('publish_local', self.meta())

    def test_the_destination_through_a_symlinked_folder_is_still_the_destination(self):
        """Порівняння — за `realpath`: модуль, що повернув шлях через посилання на ту саму теку, не відмовляється."""
        real = os.path.join(self.home, 'pubs', 'real')
        os.makedirs(real)
        alias = os.path.join(self.home, 'pubs', 'alias')
        os.symlink(real, alias)
        self.set_folder(real)
        module = dm.catalog()[MID]
        real_publish = module.fn('publish')

        def via_alias(ctx, build, task):
            real_publish(ctx, build, task)
            return {'path': os.path.join(alias, task['id'])}

        with mock.patch.dict(module._fns, {'publish': via_alias}):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(self.meta()['publish_local']['path'], os.path.join(alias, 'tx'))

    # ---- пароль ----

    def test_a_password_secret_gates_the_wrapper_and_every_page(self):
        dm.write_secrets('off', MID, {'password': 'pw-Ключ-1'})
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        wrapper = _read(os.path.join(self.dest, 'index.html'))
        self.assertIn('id="authgate"', wrapper)
        self.assertIn(f'window.__extPw={json.dumps("pw-Ключ-1", ensure_ascii=False)};', wrapper)
        self.assertNotIn('<script>window.__gateOpen=true;</script>', wrapper)
        for rel in SOURCE_PAGES:
            self.assertIn('id="authgate"', _read(os.path.join(self.dest, rel)), rel)
        # ті самі ключі, що читає `preview_gate_state`: КОЖНА сторінка з гейтом І з цим паролем
        gate = serve.preview_gate_state({'dir': self.tx_dir}, 'pw-Ключ-1')
        self.assertEqual((gate['state'], gate['stale'], gate['ungated']), ('current', 0, 0), gate)
        # пароль у відповіді й у метаданих не світиться (він у сторінках лише ЯК гейт)
        self.assertNotIn('pw-Ключ-1', json.dumps(body, ensure_ascii=False))
        self.assertNotIn('pw-Ключ-1', _read(os.path.join(self.tx_dir, 'iterations.json')))
        self.assertNotIn('pw-Ключ-1', _read(os.path.join(self.off_path, 'space.json')))

    def test_no_secret_means_no_gate_and_the_wrapper_opens_itself(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        wrapper = _read(os.path.join(self.dest, 'index.html'))
        self.assertIn('<script>window.__gateOpen=true;</script>', wrapper)
        self.assertNotIn('authgate', wrapper)
        for rel in SOURCE_PAGES:
            self.assertNotIn('authgate', _read(os.path.join(self.dest, rel)), rel)

    def test_an_empty_password_secret_is_no_password_not_a_gate_that_opens_with_an_empty_field(self):
        """`''` у секретах — «пароля нема» (`or None`); а `build_preview(gate_pw='')` — гейт, що відчиняється
        порожнім полем (сторінки ЗМІНЕНО, `<title>` переписано). Без пароля сторінки не чіпаються взагалі."""
        dm.write_secrets('off', MID, {'password': ''})
        self.assertEqual(self.post('/api/publish')[0], 200)
        self.assertIn('<script>window.__gateOpen=true;</script>', _read(os.path.join(self.dest, 'index.html')))
        for rel in SOURCE_PAGES:
            html = _read(os.path.join(self.dest, rel))
            self.assertNotIn('authgate', html, rel)
            self.assertEqual(_title(html), _title(_read(os.path.join(self.tx_dir, 'iterations', rel))), rel)

    # ---- помилки модуля: ОДНЕ місце відповіді (`_guarded`) ----

    def test_a_broken_space_json_without_integrations_is_409_space_json_unreadable(self):
        """Простір без інтеграцій потребує явних рішень із `space.json`: `provider` кидає `ModuleError`, а
        `_guarded` відповідає за ВСІ маршрути однаково — JSON із кодом і статусом ядра, а не обірване зʼєднання."""
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'), body)
        self.assertIn('space.json', body['error'])
        self.assert_nothing_built()
        self.assert_quiet()

    def test_a_module_error_from_the_module_keeps_its_code_and_status_and_loses_the_secret(self):
        dm.write_secrets('off', MID, {'password': 'S3cr3t-pw'})
        module = dm.catalog()[MID]

        def refuses(ctx, build, task):
            raise ctx['ModuleError']('bad-folder', message='не можу писати з S3cr3t-pw')

        with mock.patch.dict(module._fns, {'publish': refuses}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'bad-folder'), body)
        self.assertNotIn('S3cr3t-pw', json.dumps(body, ensure_ascii=False))
        self.assertIn('***', body['error'])

    def test_a_crashing_module_is_502_module_error_without_the_secret(self):
        dm.write_secrets('off', MID, {'password': 'S3cr3t-pw'})
        module = dm.catalog()[MID]

        def crashes(ctx, build, task):
            raise RuntimeError('впало на S3cr3t-pw')

        with mock.patch.dict(module._fns, {'publish': crashes}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (502, False, 'module-error'), body)
        self.assertNotIn('S3cr3t-pw', json.dumps(body, ensure_ascii=False))

    def test_a_module_that_returns_no_path_is_502_and_writes_no_publish_local(self):
        module = dm.catalog()[MID]
        with mock.patch.dict(module._fns, {'publish': lambda ctx, build, task: {}}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['code']), (502, 'module-error'), body)
        self.assertNotIn('publish_local', self.meta())

    def test_a_broken_space_json_with_integrations_refuses_to_publish(self):
        """Було: `provider('publish')` ковтав `space-json-unreadable` і віддавав неявного постачальника — ЛІГА-публікація працювала без
        `space.json` (а комментарі йшли без шару з `comments_unavailable`). 4d-4b: запису публікації прочитати нема звідки, запасного нема —
        `space-json-unreadable` для КОЖНОЇ ролі, публікація відмовляє ДО збірки (спільний Supabase тим паче не їде)."""
        with open(os.path.join(self.on_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.on)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        st, body = self.post('/api/publish', {'build_only': True}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, body['ok'], body['code']), (dm.STATUS['space-json-unreadable'], False, 'space-json-unreadable'), body)
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish')), 'збірку не починали')

    # ---- простір ЛІГА, неявний і зафіксований шляхи ----

    def test_a_space_with_integrations_and_the_league_record_is_the_league_path(self):
        st, body = self.post('/api/publish', {'build_only': True}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, list(body)[:4]), (200, ['ok', 'dir', 'iterations', 'frames']), body)
        self.assertTrue(os.path.isdir(os.path.join(body['dir'], 'comment-layer')))
        self.assertNotIn('local', body)
        self.assertNotIn('publish_local', self.meta(self.ty_dir))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))

    def test_an_explicitly_enabled_module_wins_where_integrations_are_on(self):
        self.replace_publisher(self.on, MID)
        st, body = self.post('/api/publish', {}, {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, body)
        want = os.path.join(self.home, 'deai-published', 'on', 'ty')
        self.assertEqual(body['local'], {'path': want, 'url': '/published/on/ty/'})
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish', 'comment-layer')))
        self.assertEqual(self.meta(self.ty_dir)['publish_local']['path'], want)
        self.assert_quiet()

    def test_an_unpinned_request_space_has_nobody_to_publish(self):
        """Було: інструменти ЛІГА й зовнішні заглушки обробника кликали `_publish` БЕЗ зафіксованого простору запиту, і `provider` віддавав
        неявного постачальника — шлях ЛІГА працював навіть у машині БЕЗ інтеграцій. 4d-4b: явний запис діє лише в закріпленому просторі,
        тож без простору запиту публікувати нікому: `409 no-publish-module`, збірки й дашборда нема."""
        spaces.clear_request_space()
        self.assertIsNone(dm.provider('publish'))
        stub = _Stub()
        serve.Handler._publish(stub, {'build_only': True})
        self.assertEqual(stub.sent, [(409, serve.no_publish_module_body())])
        self.assert_nothing_built()
        self.assertEqual(stub.overview, 0)

    def test_a_request_without_any_space_has_nobody_to_publish(self):
        """`''` — запит прямо сказав «без простору» (просторів нема): це не простір ЛІГА, публікувати нікому."""
        stub = _Stub()
        with spaces.request_space(''):
            serve.Handler._publish(stub, {})
        self.assertEqual(stub.sent, [(409, serve.no_publish_module_body())])
        self.assert_nothing_built()
        self.assert_quiet()

    def test_the_module_path_needs_only_the_four_methods_of_an_external_stub(self):
        stub = _Stub()
        with spaces.request_space('off'):
            serve.Handler._publish(stub, {})
        (st, body), = stub.sent
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(body['local']['path'], self.dest)
        self.assertEqual(stub.overview, 0, 'модуль не штовхає дашборд команди')
        stub = _Stub()
        meta = self.meta()
        for it in meta['iterations']:
            it['published'] = False
        _write_json(os.path.join(self.tx_dir, 'iterations.json'), meta)
        with spaces.request_space('off'):
            serve.Handler._publish(stub, {})
        self.assertEqual(stub.sent, [('error', 400, 'no iterations marked for publish - toggle the green dot first')])

    # ---- серіалізація публікацій одного призначення ----

    def _slow(self, owner=dm, name='call'):
        """Патч `owner.name` (типово `deai_modules.call`): перший виклик стоїть, доки `release` не подано; решта
        викликів лише відмічаються й ідуть далі. Повертає `(entered, inside, second, release, kwargs)`."""
        real = getattr(owner, name)
        entered, kwargs = [], []
        inside, second, release = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)                       # тест, що впав, не лишає потік стояти

        def slow(*args, **kw):
            entered.append(args)
            kwargs.append(kw)
            if len(entered) == 1:
                inside.set()
                release.wait(20)
            else:
                second.set()
            return real(*args, **kw)
        patch = mock.patch.object(owner, name, slow)
        patch.start()
        self.addCleanup(patch.stop)
        return entered, inside, second, release, kwargs

    def _concurrent(self, first, second_run, entered, inside, release):
        """Запустити `first`, дочекатись, що вона всередині (стоїть), запустити `second_run` в окремому потоці й
        дати їй 5 с: вона мусить ВІДПОВІСТИ (замок зайнятий — одразу 409, інше призначення — працює), а не чекати.
        Потім відпустити першу. Повертає `(відповідь першої, відповідь другої, скільки викликів увійшло в патч,
        поки перша стояла)`."""
        box = {}
        t1 = threading.Thread(target=lambda: box.__setitem__('first', first()), daemon=True)
        t2 = threading.Thread(target=lambda: box.__setitem__('second', second_run()), daemon=True)
        t1.start()
        self.assertTrue(inside.wait(15), 'перша публікація не дійшла до патча')
        t2.start()
        t2.join(5)
        waited = t2.is_alive()
        seen = len(entered)
        release.set()
        t1.join(30)
        t2.join(30)
        self.assertFalse(t1.is_alive() or t2.is_alive(), 'публікація зависла')
        self.assertFalse(waited, 'друга публікація ЧЕКАЛА (замок мусить відповідати одразу: 409 publish-busy)')
        return box['first'], box['second'], seen

    def _publish_in(self, sid, payload=None):
        """Публікація в просторі `sid` напряму через `Handler._publish` із заглушкою: відповідь — `(статус, тіло)`."""
        def run():
            stub = _Stub()
            with spaces.request_space(sid):
                serve.Handler._publish(stub, {} if payload is None else payload)
            return stub.sent[0]
        return run

    def assert_busy(self, st, body):
        self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'publish-busy'), body)
        self.assertTrue(body['error'])

    def test_a_second_publish_of_one_task_is_409_busy_while_the_first_runs(self):
        """Замок БЕЗ очікування: зависла мережева тека не нагромаджує потоки, що чекають, а повторний клік дістає
        чітку відповідь одразу. Коли перша публікація вийшла, замок вільний."""
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'), lambda: self.post('/api/publish'),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'друга публікація тієї ж задачі зайшла в модуль, поки перша ще всередині')
        self.assertEqual(first[0], 200, first)
        self.assertEqual(self.post('/api/publish')[0], 200, 'замок не відпущено після першої публікації')
        # `timeout=` перетворив би виклик на робочий потік: що не вклався, копіював би далі БЕЗ замка
        self.assertEqual(kwargs, [{}, {}], 'publish кликано з timeout')
        self.assertEqual(os.listdir(self.folder), ['tx'])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))

    def test_build_only_obeys_the_same_lock(self):
        """`build_only` теж стирає `<задача>/publish/`, з якого перша публікація копіює: те саме 409."""
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'),
                                            lambda: self.post('/api/publish', {'build_only': True}),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(first[0], 200, first)
        self.assertEqual(self.post('/api/publish', {'build_only': True})[0], 200)

    def test_the_build_runs_under_the_lock_too(self):
        """Збірка стирає й пише `<задача>/publish/`, з якого модуль копіює: друга публікація тієї самої задачі не
        сміє почати збірку, поки перша ще триває (лишила б напівзібрану теку під першою)."""
        entered, inside, second, release, kwargs = self._slow(serve, 'build_preview')
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'), lambda: self.post('/api/publish'),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'друга збірка тієї ж задачі почалась, поки перша публікація ще триває')
        self.assertEqual(first[0], 200, first)

    def test_the_lock_is_released_after_a_failed_publish(self):
        """Замок без очікування, який не відпущено після збою, зробив би задачу «зайнятою» назавжди."""
        module = dm.catalog()[MID]

        def crashes(ctx, build, task):
            raise RuntimeError('впало')

        with mock.patch.dict(module._fns, {'publish': crashes}):
            self.assertEqual(self.post('/api/publish')[0], 502)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)

    def test_the_lock_is_keyed_by_the_destination_not_by_the_space(self):
        """Правило `folder_ok` пускає ту саму теку для двох просторів (і тека одного — типова теку іншого): задачі
        `t1` двох просторів ділили б `<тека>/t1` без взаємного виключення, коли замок на (простір, задача)."""
        s1 = self._register(self._space('s1', os.path.join(self.home, 'deai-work', 's1'), False, 't1'))
        s2 = self._register(self._space('s2', os.path.join(self.home, 'deai-work', 's2'), False, 't1'))
        shared = os.path.join(self.home, 'deai-published', 's1')           # типова тека s1
        self.set_folder(shared, s2)
        self.assertEqual(dm.published_root(s1, MID), shared)
        self.assertEqual(dm.published_root(s2, MID), shared)
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(self._publish_in('s1'), self._publish_in('s2'), entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'публікації двох просторів у ТУ САМУ теку не виключають одна одну')
        self.assertEqual((first[0], first[1]['ok']), (200, True), first)
        self.assertEqual(kwargs, [{}])
        self.assertEqual(self._publish_in('s2')()[0], 200, 'після першої публікації друга проходить')
        self.assertEqual(sorted(os.listdir(shared)), ['t1'])
        self.assertTrue(os.path.isfile(os.path.join(shared, 't1', '.deai-published')))
        for rec in (s1, s2):
            pl = self.meta(os.path.join(rec['path'], 't1'))['publish_local']
            self.assertEqual(pl['path'], os.path.join(shared, 't1'))

    def test_tasks_with_different_destinations_do_not_block_each_other(self):
        """Замок — на призначення, не глобальний: публікація однієї задачі не тримає іншу (ні 409, ні очікування)."""
        self._register(self._space('s1', os.path.join(self.home, 'deai-work', 's1'), False, 't1'))
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(self._publish_in('off'), self._publish_in('s1'), entered, inside, release)
        self.assertEqual((sec[0], sec[1]['ok']), (200, True), sec)
        self.assertEqual(seen, 2, 'різні призначення чекали одне одного')
        self.assertEqual(first[0], 200)

    def test_the_lock_key_is_the_real_folder_and_the_case_folded_task_id(self):
        real = os.path.join(self.tmp, 'real-folder')
        os.makedirs(real)
        alias = os.path.join(self.tmp, 'alias-folder')
        os.symlink(real, alias)
        key = serve._publish_key(real, 'Task-1')
        self.assertEqual(serve._publish_key(alias, 'task-1'), key)         # посилання й регістр — те саме призначення
        self.assertEqual(serve._publish_key(real + '/', 'TASK-1'), key)
        self.assertEqual(serve._publish_key(real.upper(), 'task-1'), key)   # macOS: `Foo` і `foo` — одна тека
        self.assertNotEqual(serve._publish_key(real, 'task-2'), key)
        self.assertNotEqual(serve._publish_key(os.path.join(self.tmp, 'other'), 'task-1'), key)
        self.assertIs(serve._publish_lock(key), serve._publish_lock(serve._publish_key(alias, 'task-1')))
        self.assertIsNot(serve._publish_lock(key), serve._publish_lock(serve._publish_key(real, 'task-2')))

    def test_the_lock_key_folds_nfc_and_nfd_spellings_of_a_cyrillic_folder(self):
        """macOS бачить `й` (U+0439) і `и`+U+0306 як одну теку: ключ нормалізується в NFC (`folder_ok` теж)."""
        nfc = unicodedata.normalize('NFC', 'Тека-й-ї')
        nfd = unicodedata.normalize('NFD', 'Тека-й-ї')
        self.assertNotEqual(nfc, nfd, 'свідок: у тесті справді два різні написання')
        self.assertEqual(serve._publish_key(os.path.join(self.tmp, nfc), 'T'),
                         serve._publish_key(os.path.join(self.tmp, nfd), 'T'))
        self.assertEqual(serve._publish_key(os.path.join(self.tmp, 'p'), nfc),
                         serve._publish_key(os.path.join(self.tmp, 'p'), nfd))

    def test_the_build_dir_of_one_task_is_locked_even_if_the_folder_setting_changes_mid_flight(self):
        """`build_preview` завжди пише `<тека задачі>/publish/`, а замок призначення ключиться за (тека, задача):
        налаштування `folder` змінили, поки перша публікація стоїть, — друга мала б ІНШЕ призначення, вільний
        замок і зайшла б у збірку тієї ж `publish/` разом із першою. Тож задачу замикає ще й її тека збірки."""
        f2 = os.path.join(self.home, 'pubs', 'two')
        entered, inside, second, release, kwargs = self._slow(serve, 'build_preview')

        def second_run():
            self.set_folder(f2)                                 # інше призначення → замок призначення вільний
            return self.post('/api/publish')

        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'), second_run, entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'друга збірка тієї ж задачі почалась, поки перша ще пише `publish/`')
        self.assertEqual((first[0], first[1]['ok']), (200, True), first)
        self.assertFalse(os.path.exists(f2), 'відмова створила теку нового призначення')
        self.assertEqual(self.post('/api/publish')[0], 200, 'замок теки збірки не відпущено')

    def test_the_task_dir_lock_key_is_the_real_case_folded_dir(self):
        real = os.path.join(self.tmp, 'real-task')
        os.makedirs(real)
        alias = os.path.join(self.tmp, 'alias-task')
        os.symlink(real, alias)
        key = serve._task_dir_key(real)
        self.assertEqual(serve._task_dir_key(alias), key)                   # посилання на теку — та сама тека
        self.assertEqual(serve._task_dir_key(real.upper()), key)            # macOS: `Foo` і `foo` — одна тека
        self.assertEqual(serve._task_dir_key(real + '/'), key)
        self.assertNotEqual(serve._task_dir_key(os.path.join(self.tmp, 'other')), key)
        # у спільному словнику замків ключ теки збірки не збігається з ключем призначення (одинак проти пари)
        self.assertNotEqual(key, serve._publish_key(real, 'x'))
        self.assertEqual(len(key), 1)

    def test_both_locks_are_taken_in_a_fixed_order_and_released_together(self):
        """Порядок — тека збірки, потім призначення; обидва без очікування; зайнятий другий не лишає взятим перший."""
        folder = os.path.join(self.tmp, 'dest')
        os.makedirs(folder)
        tdir = os.path.join(self.tmp, 'task')
        os.makedirs(tdir)
        build, dest = serve._publish_lock(serve._task_dir_key(tdir)), serve._publish_lock(serve._publish_key(folder, 't'))
        with serve._try_publish_locks(tdir, folder, 't') as got:
            self.assertTrue(got)
            self.assertTrue(build.locked() and dest.locked())
            with serve._try_publish_locks(tdir, folder, 't') as again:
                self.assertFalse(again)
        self.assertFalse(build.locked() or dest.locked(), 'замок не відпущено після виходу з блоку')
        dest.acquire()                                                      # призначення зайняте кимось іншим
        try:
            with serve._try_publish_locks(tdir, folder, 't') as got:
                self.assertFalse(got)
            self.assertFalse(build.locked(), 'зайняте призначення лишило замок теки збірки взятим')
        finally:
            dest.release()
        with self.assertRaises(RuntimeError):                               # виняток у блоці теж відпускає
            with serve._try_publish_locks(tdir, folder, 't'):
                raise RuntimeError('впало')
        self.assertFalse(build.locked() or dest.locked())

    def test_a_path_outside_the_destination_says_the_files_may_already_have_been_written(self):
        """До цієї відмови модуль УЖЕ відпрацював: текст не сміє натякати, що нічого не сталося."""
        module = dm.catalog()[MID]
        other = os.path.join(self.home, 'elsewhere', 'tx')
        with mock.patch.dict(module._fns, {'publish': lambda ctx, build, task: {'path': other}}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), body)
        self.assertIn('may already have been written', body['error'])
        self.assertNotIn(other, body['error'], 'шлях із відповіді модуля потрапив у текст помилки')
        self.assertLessEqual(len(body['error']), dm.MAX_MESSAGE)

    def test_the_folder_that_is_checked_locked_and_written_is_one_value(self):
        """`ctx` будується ОДИН раз, тека береться з нього: налаштування, змінене між перевіркою `folder_ok` і
        записом, не розводить ключ замка (і перевірену теку) з текою, у яку модуль справді пише."""
        f1, f2 = os.path.join(self.home, 'pubs', 'one'), os.path.join(self.home, 'pubs', 'two')
        self.set_folder(f1)
        real_ok, real_key = dm.folder_ok, serve._publish_key
        checked, keyed = [], []

        def changing(space, folder, **kw):
            checked.append(folder)
            res = real_ok(space, folder, **kw)
            self.set_folder(f2)                                 # налаштування змінили ПІСЛЯ перевірки
            return res

        def spy(folder, tid):
            keyed.append(folder)
            return real_key(folder, tid)

        with mock.patch.object(dm, 'folder_ok', changing), mock.patch.object(serve, '_publish_key', spy):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['local']['path'], os.path.join(f1, 'tx'))
        self.assertEqual((set(checked), keyed), ({f1}, [f1]))
        self.assertTrue(os.path.isfile(os.path.join(f1, 'tx', 'index.html')))
        self.assertFalse(os.path.exists(f2), 'модуль писав у теку, якої не перевіряли й не замикали')

    def test_publish_local_is_written_from_a_fresh_read_of_iterations_json(self):
        """Між публікацією (`call`) і записом `publish_local` дизайнер перемкнув зелену крапку: запис зі старого
        `meta` (прочитаного на вході) відкотив би її."""
        real = dm.call

        def toggled_meanwhile(module, fn, ctx, *args, **kw):
            res = real(module, fn, ctx, *args, **kw)
            st, body = self.post('/api/publish-toggle', {'id': 'it2'})
            self.assertEqual((st, body['published']), (200, False), body)
            return res

        with mock.patch.object(dm, 'call', toggled_meanwhile):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        meta = self.meta()
        self.assertEqual({i['id']: i['published'] for i in meta['iterations']}, {'it1': True, 'it2': False})
        self.assertEqual(meta['publish_local']['path'], self.dest)

    # ---- `/api/task` ----

    def test_api_task_shows_publish_local_and_a_module_gate_state(self):
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(task['preview_gate'], MODULE_GATE)
        self.assertNotIn('publish_local', task)
        self.assertEqual(set(task['preview_gate']), set(serve.preview_gate_state({'dir': self.tx_dir}, 'x')))
        self.assertEqual(self.post('/api/publish')[0], 200)
        st, task = self.get('/api/task')
        self.assertEqual(task['publish_local'], self.meta()['publish_local'])
        self.assertEqual(task['preview_gate'], MODULE_GATE)             # ПІСЛЯ збірки теж: без «ungated»
        self.assertIsNone(task['publish_url'])

    def test_api_task_in_a_league_space_has_the_old_gate_and_no_publish_local(self):
        st, task = self.get('/api/task', {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, task)
        self.assertEqual(task['preview_gate'], serve.preview_gate_state({'dir': self.ty_dir}, task['preview_password']))
        self.assertEqual(task['preview_gate']['state'], 'none')
        self.assertNotIn('publish_local', task)

    def test_api_task_does_not_fail_on_a_broken_space_json(self):
        """`/api/task` питає `capabilities()` (тотальна, не кидає), а не `provider()`: зіпсований `space.json`
        не мусить гасити весь інтерфейс. Модуля при цьому не видно — шлях гейта звичайний."""
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertNotEqual(task['preview_gate']['state'], 'module')

    # ---- пароль превʼю ЛІГА ----

    def test_preview_password_is_refused_unless_the_league_publishes(self):
        tasks = os.path.join(self.off_path, 'tasks.json')
        before = _bytes(tasks)
        st, body = self.post('/api/preview-password', {'password': 'abcd'})
        self.assertEqual((st, body), (409, serve.integrations_off_body('публікація зʼявиться з модулями')))
        self.assertEqual(_bytes(tasks), before, 'пароль записано в простір, де публікує модуль')
        # явно ввімкнений модуль у просторі З інтеграціями — теж не шлях ЛІГА
        self.replace_publisher(self.on, MID)
        st, body = self.post('/api/preview-password', {'password': 'abcd'}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, body['code']), (409, 'integrations-off'), body)
        # нечитабельний space.json у просторі без інтеграцій — та сама відповідь, а не `space-json-unreadable`
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, body = self.post('/api/preview-password', {'password': 'abcd'})
        self.assertEqual((st, body), (409, serve.integrations_off_body('публікація зʼявиться з модулями')))

    def test_preview_password_still_works_for_the_league_path(self):
        dm.write_module_state(self.on, MID, enabled=False)                 # явне «вимкнено» у просторі ЛІГА
        st, body = self.post('/api/preview-password', {'password': 'abcd'}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, body['ok'], body['preview_password']), (200, True, 'abcd'), body)
        with open(os.path.join(self.on_path, 'tasks.json'), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['ty']['preview_password'], 'abcd')


class TaskIdParity(unittest.TestCase):
    """Правило id задачі живе ДВІЧІ: у `static-publish` (`ID_RE`, `MAX_ID`, `_RESERVED`) і в ядрі
    (`serve.publish_id_ok`: диспетчер відмовляє до збірки, роздача `/published/…` пускає лише такі id).
    Друга копія розійшлась би з першою мовчки — тож обидві стороні дається ОДИН корпус, і приймати чи
    відмовляти вони мусять однаково. Модуль — справжній (з каталогу), `publish` із рукописним `ctx`: перша
    його дія — перевірка id, тож «відмовив через id» видно з тексту помилки (`task id:`), а прийнятий id
    доходить до наступного кроку (теки), що в `ctx` без налаштувань кидає вже ІНШУ помилку."""

    CORPUS = [
        '', '-', '_', '--', 'a', 'A', 'z-Z_9', '0', '9', 'task-1', 'Task_1-b',
        '\u0663', '\u0663\u0664', 'a\u0663', '\u0661', 'COM\u0661',      # юнікодні цифри (арабо-індійські)
        '\u212a', 'a\u212a', '\u017f', 'a\u017f', 'NU\u017f', '\u0130', '\u0131',   # `K` (Кельвін), `ſ`, `İ`, `ı`
        'K', 'k', 'ſ', 'a\n', '\n', 'a\nb', '\na', 'a\r', 'a\x00', '\x00', 'a\x00b', 'a b', ' a', 'a ',
        'a.b', '.', '..', '.a', 'a/b', 'a\\b', 'a:b', 'a%2f', '\u0437\u0430\u0434\u0430\u0447\u0430', 'a\u0301', 'a\u200b',
        'COM0', 'COM1', 'COM9', 'COM10', 'com1', 'Com5', 'LPT0', 'LPT1', 'lpt9', 'LPT10', 'CON', 'con', 'Con', 'console',
        'CON1', 'PRN', 'prn', 'AUX', 'aux', 'NUL', 'nul', 'NULL', 'COM', 'LPT', 'CONN', 'xCON', 'CON-', 'CON_1',
        'CON.txt', 'NUL ', 'a-b-c', '-a', 'a-', '_a', 'a_',
        'x' * 1, 'x' * 127, 'x' * 128, 'x' * 129, 'x' * 255, 'x' * 1000, '-' * 128, '-' * 129, '1' * 128,
        None, 5, 1.5, b'abc', ['a'], ('a',), True,
    ]

    def _module_accepts(self, tid):
        publish = dm.catalog()[MID].fn('publish')
        try:
            publish({}, '/nonexistent', {'id': tid})
        except Exception as e:  # noqa: BLE001 — важить лише, ЧОМУ відмовлено
            self.assertIsInstance(e, RuntimeError, e)               # рукописний `ctx` без класу помилки ядра
            return 'task id' not in str(e)
        self.fail(f'publish із ctx без налаштувань не мав успіху ({tid!r})')

    def test_the_core_and_the_module_accept_and_refuse_the_same_ids(self):
        verdicts = {}
        for tid in self.CORPUS:
            with self.subTest(tid=repr(tid)[:40]):
                core, module = serve.publish_id_ok(tid), self._module_accepts(tid)
                self.assertEqual(core, module, f'розбіжність для {tid!r:.60}: ядро {core}, модуль {module}')
                verdicts[repr(tid)[:60]] = core
        # свідки: корпус справді має і прийняті, і відмовлені (інакше «однаково» нічого не доводило б)
        self.assertGreater(sum(verdicts.values()), 10)
        self.assertGreater(len(verdicts) - sum(verdicts.values()), 40)

    def test_the_corpus_pins_the_known_edges(self):
        """Корпус — не лише «однаково», а й «правильно» на межах, заради яких він складений."""
        accepted = ('a', '0', 'task-1', 'Task_1-b', 'console', 'COM10', 'COM0', 'LPT0', 'x' * 128, '-', '_', 'CONN')
        refused = ('', 'x' * 129, '\u0663', '\u212a', '\u017f', 'a\n', 'a\x00', 'CON', 'con', 'NUL', 'COM1', 'lpt9',
                   'a.b', 'a/b', '..', 'a b', '\u0437\u0430\u0434\u0430\u0447\u0430', None, 5)
        for tid in accepted:
            self.assertTrue(serve.publish_id_ok(tid), repr(tid))
            self.assertTrue(self._module_accepts(tid), repr(tid))
        for tid in refused:
            self.assertFalse(serve.publish_id_ok(tid), repr(tid))
            self.assertFalse(self._module_accepts(tid), repr(tid))


class _PublishedTests:
    """Спільні тести роздачі опублікованого: `GET /published/<простір>/<задача>/<файл>` (Task 5). НЕ `TestCase`: їх
    запускають два набори з одним і тим самим світом — `PublishedRoute` (обхід теки ДЕСКРИПТОРАМИ, як на macOS і
    Linux) і `PublishedRouteFallback` (запасний шляховий спосіб, який використовує ОС без `dir_fd`, — його ввімкнено
    підміною `_PUBLISHED_DIRFD`). Поведінка зовні (що віддається, заголовки, 404) мусить бути однаковою; різні лише
    тести підміни між перевіркою й відкриттям, і вони в самих наборах.

    Світ — той самий, що в `Dispatch`; у `setUp` задача `tx` простору `off` публікується справжнім модулем
    (`static-publish`) у `<домівка>/deai-published/off/tx`. Усе, що не має віддаватись, ЛЕЖИТЬ на диску (файл за
    посиланням, крапковий файл, тека не того id…) — «404» там, де нічого нема, нічого б не доводило; а контроль
    поруч доводить, що сам файл віддавався б.

    Відповіді зчитуються `http.client`-ом із сирим шляхом (urllib склав би `..` і не дав би перевірити `%2e%2e`)
    і БЕЗ слідування за переадресацією."""

    CSP = 'sandbox allow-scripts allow-forms allow-popups allow-modals'

    def setUp(self):
        super().setUp()
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.root = '/published/off/tx/'
        self.addCleanup(self.assert_quiet)          # розтяжка й шпигуни — після КОЖНОГО тесту: роздача нічого не кличе назовні

    # ---- допоміжне ----

    def fetch(self, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request('GET', path, headers=headers or {})
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def assert_sandboxed(self, hd, what=''):
        self.assertEqual(hd.get('content-security-policy'), self.CSP, f'CSP: {what}')
        self.assertEqual(hd.get('x-content-type-options'), 'nosniff', f'nosniff: {what}')
        self.assertEqual(hd.get('access-control-allow-origin'), '*', f'ACAO: {what}')

    def ok(self, path, headers=None):
        st, hd, body = self.fetch(path, headers)
        self.assertEqual(st, 200, f'{path} → {st}')
        self.assert_sandboxed(hd, path)
        return hd, body

    def gone(self, path, headers=None):
        """404 БЕЗ подробиць (ні шляху, ні причини) і з тими самими захисними заголовками."""
        st, hd, body = self.fetch(path, headers)
        self.assertEqual(st, 404, f'{path} → {st}')
        self.assert_sandboxed(hd, path)
        self.assertEqual(body, b'not found\n', f'{path}: тіло 404 несе подробиці')
        return hd

    def put(self, path, text='x', mode='w'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, encoding=None if 'b' in mode else 'utf-8') as fh:
            fh.write(text)
        return path

    # ---- що віддається ----

    def test_the_wrapper_a_page_a_module_script_a_style_and_the_manifest_are_served(self):
        hd, body = self.ok(self.root)
        self.assertEqual((hd['content-type'], body), ('text/html; charset=utf-8', _bytes(os.path.join(self.dest, 'index.html'))))
        self.assertEqual(self.ok(self.root + 'index.html')[1], body)
        for rel in SOURCE_PAGES:
            hd, body = self.ok(self.root + rel)
            self.assertEqual((hd['content-type'], body), ('text/html; charset=utf-8', _bytes(os.path.join(self.dest, rel))), rel)
        scripts = sorted(n for n in os.listdir(os.path.join(self.dest, 'shell')) if n.endswith('.js'))
        self.assertIn('ext-shell.js', scripts)
        for name in scripts:                        # `<script type=module>` без JS-MIME браузер відкидає
            hd, body = self.ok(f'{self.root}shell/{name}')
            self.assertEqual(hd['content-type'], 'text/javascript; charset=utf-8', name)
            self.assertEqual(body, _bytes(os.path.join(self.dest, 'shell', name)), name)
        hd, body = self.ok(self.root + 'shell/styles.css')
        self.assertEqual(hd['content-type'], 'text/css; charset=utf-8')
        hd, body = self.ok(self.root + 'manifest.json')
        self.assertEqual(hd['content-type'], 'application/json')
        self.assertEqual(json.loads(body), json.loads(_read(os.path.join(self.dest, 'manifest.json'))))

    def test_a_page_without_meta_charset_is_served_as_utf8(self):
        """Збірка пише сторінки в UTF-8, а макет може не мати `<meta charset>`: без `charset` у заголовку браузер
        читав би їх як windows-1252, і гейт-оверлей, що його вкладаємо МИ (українською), виходив кракозябрами —
        це видно було в живому браузері. Тут сторінка має кирилицю й не має `<meta charset>`."""
        page = _bytes(os.path.join(self.dest, 'it2', 'index.html'))
        self.assertNotIn(b'charset', page.lower(), 'свідок: у сторінці нема своєї кодировки')
        self.put(os.path.join(self.dest, 'it2', 'cyr.html'), '<p>Привіт</p>')
        hd, body = self.ok(self.root + 'it2/cyr.html')
        self.assertEqual(hd['content-type'], 'text/html; charset=utf-8')
        self.assertEqual(body.decode('utf-8'), '<p>Привіт</p>')
        self.assertEqual(self.ok(self.root + 'manifest.json')[0]['content-type'], 'application/json')   # JSON — без charset

    def test_percent_encoding_is_decoded_per_segment(self):
        self.ok('/published/%6ff%66/%74x/%69ndex.html')                  # `off`, `tx`, `index.html`
        self.ok('/published/off/tx/it1/%61lpha/index.html')

    def test_a_directory_with_a_slash_serves_its_index_and_without_one_redirects_keeping_the_query(self):
        self.assertEqual(self.ok(self.root + 'it1/alpha/')[1], _bytes(os.path.join(self.dest, 'it1', 'alpha', 'index.html')))
        for path, want in (('/published/off/tx', '/published/off/tx/'),
                           ('/published/off/tx?a=1&b=%D0%B6', '/published/off/tx/?a=1&b=%D0%B6'),
                           ('/published/off/tx/it1/alpha', '/published/off/tx/it1/alpha/'),
                           ('/published/off/tx/it1/alpha?z=1', '/published/off/tx/it1/alpha/?z=1'),
                           ('/published/off/tx/it1/alpha?', '/published/off/tx/it1/alpha/')):
            with self.subTest(path=path):
                st, hd, body = self.fetch(path)
                self.assertIn(st, (301, 302), path)
                self.assertEqual(hd['location'], want)
                self.assert_sandboxed(hd, path)
        # тека без `index.html`: перенаправлення на `…/`, а там 404 (не нескінченний цикл)
        self.put(os.path.join(self.dest, 'bare', 'a.txt'))                  # тека без index.html
        self.assertEqual(self.fetch(self.root + 'bare')[0], 301)
        self.gone(self.root + 'bare/')
        self.gone(self.root + 'index.html/')                                # файл зі слешем — не файл
        self.gone(self.root + 'no-such.html')
        self.gone(self.root + 'no-such/')

    def test_every_response_is_sandboxed_200_304_redirect_and_404(self):
        hd, _ = self.ok(self.root + 'manifest.json')
        etag = hd['etag']
        st, hd2, body = self.fetch(self.root + 'manifest.json', {'If-None-Match': etag})
        self.assertEqual((st, body), (304, b''))
        self.assertEqual(hd2['etag'], etag)
        self.assert_sandboxed(hd2, '304')
        st, hd3, _ = self.fetch(self.root + 'manifest.json', {'If-None-Match': '"other"'})
        self.assertEqual(st, 200, 'чужий ETag не дає 304')
        self.assert_sandboxed(hd3, '200 після чужого ETag')
        st, hd4, _ = self.fetch('/published/off/tx')
        self.assertIn(st, (301, 302))
        self.assert_sandboxed(hd4, 'redirect')
        self.gone(self.root + 'nope.txt')                                   # 404 у межах опублікованого
        self.gone('/published/nope/tx/')                                    # 404 до жодного читання теки
        self.gone('/published/')

    def test_the_content_type_of_a_404_is_plain_text(self):
        hd = self.gone(self.root + 'nope.txt')
        self.assertEqual(hd['content-type'], 'text/plain; charset=utf-8')

    # ---- чия це теки, і чи вона ще дозволена ----

    def test_a_space_whose_publisher_is_not_static_publish_serves_nothing(self):
        """`on` має інтеграції → publisher `'legacy'` (ЛІГА): `/published/on/…` не віддає нічого, хоч файли ЛЕЖАТЬ у
        типовій теці модуля. Контроль: явно ввімкнений `static-publish` у `on` — і той самий файл віддається."""
        on_dest = os.path.join(self.home, 'deai-published', 'on', 'ty')
        self.put(os.path.join(on_dest, 'index.html'), 'on-index')
        self.put(os.path.join(on_dest, '.deai-published'), 'marker')
        self.assertEqual(dm.provider('publish', self.on).id, 'vercel-publish')      # було `implicit.for_role('publish')`: тепер явний запис ЛІГИ
        self.gone('/published/on/ty/')
        self.gone('/published/on/ty/index.html')
        self.replace_publisher(self.on, MID)
        self.assertEqual(self.ok('/published/on/ty/index.html')[1], b'on-index')

    def test_a_space_where_the_module_is_switched_off_serves_nothing_any_more(self):
        self.ok(self.root + 'manifest.json')
        dm.write_module_state(self.off, MID, enabled=False)
        self.gone(self.root + 'manifest.json')
        self.gone(self.root)
        dm.write_module_state(self.off, MID, enabled=True)
        self.ok(self.root + 'manifest.json')

    def test_an_unknown_space_or_task_is_404(self):
        for path in ('/published/nope/tx/manifest.json', '/published/OFF/tx/manifest.json',
                     '/published/off/nope/manifest.json',
                     '/published/off//manifest.json', '/published//tx/manifest.json', '/published/off',
                     '/published/off/', '/published/o%66f/tx/%2e/manifest.json'):
            with self.subTest(path=path):
                self.gone(path)

    def test_the_space_comes_from_the_url_not_from_the_request(self):
        """`/published/<простір>/…` вирішує URL: ні поточний простір машини, ні `X-Canvas-Task` (навіть невідомий чи
        порожній — на API це 404/400) не мають значення. Тут два простори зі СВОЇМИ теками й задачами."""
        self._register(self._space('s2', os.path.join(self.home, 'deai-work', 's2'), False, 't2'))
        st, body = self.post('/api/publish', headers={'X-Canvas-Task': 't2'})
        self.assertEqual(st, 200, body)
        s2_dest = os.path.join(self.home, 'deai-published', 's2', 't2')
        self.assertEqual(body['local']['path'], s2_dest)
        self.put(os.path.join(self.dest, 'who.txt'), 'off/tx')
        self.put(os.path.join(s2_dest, 'who.txt'), 's2/t2')
        for headers in ({}, {'X-Canvas-Task': 'tx'}, {'X-Canvas-Task': 't2'}, {'X-Canvas-Task': 'no-such-task'},
                        {'X-Canvas-Task': ''}, {'X-Canvas-Task': ' '}):
            with self.subTest(headers=headers):
                self.assertEqual(self.ok('/published/s2/t2/who.txt', headers)[1], b's2/t2')
                self.assertEqual(self.ok('/published/off/tx/who.txt', headers)[1], b'off/tx')
                self.gone('/published/s2/tx/who.txt', headers)              # задача іншого простору тут не існує
                self.gone('/published/off/t2/who.txt', headers)

    def test_a_referer_from_an_iteration_still_works_outside_published_and_changes_nothing_inside(self):
        """Усе поза `HANDLED_PREFIXES` статичний фолбек віддає з теки ітерації за Referer. Перелік має `/published/` (зі
        слешем): `/publishedx` і голий `/published` лишаються там, де були ДО роздачі, — під фолбеком (приманки в
        ітераціях віддаються, як і раніше), а `/published/…` — наш, і приманка `published/off/tx/decoy.txt` НЕ віддається."""
        self.assertIn('/published/', serve.HANDLED_PREFIXES)
        self.assertNotIn('/published', serve.HANDLED_PREFIXES)
        it1 = os.path.join(self.tx_dir, 'iterations', 'it1')
        it2 = os.path.join(self.tx_dir, 'iterations', 'it2')
        self.put(os.path.join(it1, 'published', 'off', 'tx', 'decoy.txt'), 'DECOY')
        self.put(os.path.join(it1, 'publishedx'), 'DECOY-X')
        self.put(os.path.join(it2, 'published'), 'DECOY-BARE')
        ref1 = {'Referer': f'{self.base}/it-assets/it1/alpha/index.html'}
        ref2 = {'Referer': f'{self.base}/it-assets/it2/index.html'}
        self.assertEqual(self.fetch('/it-assets/it1/publishedx', ref1)[2], b'DECOY-X')     # свідок: через /it-assets віддається
        st, hd, body = self.fetch('/publishedx', ref1)
        self.assertEqual((st, body), (200, b'DECOY-X'), '/publishedx мусить лишитись під фолбеком за Referer')
        st, hd, body = self.fetch('/published', ref2)
        self.assertEqual((st, body), (200, b'DECOY-BARE'), 'голий /published мусить лишитись під фолбеком за Referer')
        self.assertNotIn('content-security-policy', hd, 'голий /published не наш маршрут')
        self.gone(self.root + 'decoy.txt', ref1)
        self.assertEqual(self.ok(self.root + 'it2/index.html', ref1)[1], _bytes(os.path.join(self.dest, 'it2', 'index.html')))

    def test_a_bare_published_is_not_our_route(self):
        st, hd, body = self.fetch('/published')
        self.assertEqual(st, 404)
        self.assertNotIn('content-security-policy', hd)
        self.assertNotEqual(body, b'not found\n')

    def test_a_folder_the_rules_refuse_serves_nothing_even_if_the_task_dir_looks_published(self):
        """Правило теки (`folder_ok`) діє на КОЖНУ видачу, а не лише при публікації: налаштування змінили на теку,
        яку вона відмовила б, — і те, що там лежить (файли задачі!), не віддається. Марковану теку задачі кладемо
        самі, щоб між файлом і відповіддю стояло лише правило теки."""
        self.ok(self.root + 'manifest.json')
        bad = {'тека простору': self.off_path, 'домівка': self.home, 'усередині DEAI_HOME': os.path.join(self.deai, 'pub'),
               'тека інструмента': os.path.join(self.tool, 'pub')}
        for what, folder in bad.items():
            with self.subTest(what):
                self.put(os.path.join(folder, 'tx', '.deai-published'), 'marker')
                self.put(os.path.join(folder, 'tx', 'secret.txt'), 'сек')
                self.set_folder(folder)
                self.assertFalse(dm.folder_ok(self.off, folder)[0], 'свідок: правило справді відмовляє цю теку')
                self.gone(self.root + 'secret.txt')
                self.gone(self.root)
        self.set_folder(os.path.join(self.home, 'deai-published', 'off'))
        self.ok(self.root + 'manifest.json')

    def test_unreadable_inputs_of_the_folder_rules_serve_nothing(self):
        self.ok(self.root + 'manifest.json')
        with mock.patch.object(dm, 'folder_inputs', return_value=None):
            self.gone(self.root + 'manifest.json')
        self.ok(self.root + 'manifest.json')

    def test_a_broken_space_json_is_404_without_details(self):
        self.put(os.path.join(self.off_path, 'space.json'), '{ не json')
        for path in (self.root + 'manifest.json', self.root, self.root + 'index.html', self.root + 'shell/ext-shell.js'):
            self.gone(path)                                     # `gone` вимагає порожнє тіло: ні шляху, ні причини

    def test_a_broken_registry_is_404_not_a_503_with_a_path(self):
        """На API нечитабельний реєстр — 503 `spaces-unreadable` із шляхом; для статичного файла в пісочниці це
        витік подробиць (і сторінка в iframe показала б шлях), тож тут — той самий порожній 404."""
        self.put(os.path.join(self.deai, 'spaces.json'), '{')
        self.gone(self.root + 'manifest.json')
        self.gone('/published/off/tx/')
        st, _, _ = self.fetch('/api/task')
        self.assertEqual(st, 503, 'свідок: API на тому самому реєстрі справді 503')

    # ---- вихід за межі ----

    def test_traversal_in_any_spelling_is_404(self):
        secret = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        self.put(os.path.join(self.folder, 'sibling', 'index.html'), 'SIBLING')           # сусідня задача:
        self.put(os.path.join(self.folder, 'sibling', '.deai-published'), 'm')            # сама по собі віддається
        self.assertEqual(self.ok('/published/off/sibling/index.html')[1], b'SIBLING')     # контроль
        self.assertEqual(self.ok(self.root + 'manifest.json')[0]['content-type'], 'application/json')    # контроль
        self.assertTrue(os.path.isfile(secret))
        for path in ('/published/off/tx/../secret.txt', '/published/off/tx/%2e%2e/secret.txt',
                     '/published/off/tx/%2E%2E/secret.txt', '/published/off/tx/..%2fsecret.txt',
                     '/published/off/tx/%2e%2e%2fsecret.txt', '/published/off/tx/%2e%2e%5csecret.txt',
                     '/published/off/tx/..%5csecret.txt', '/published/off/tx/.%2e/secret.txt',
                     '/published/off/%2e%2e/off/tx/manifest.json', '/published/off/tx/it1/../manifest.json',
                     '/published/off/tx/./manifest.json', '/published/off/tx/%2e/manifest.json',
                     '/published/off/..%2ftx/manifest.json', '/published/off%2ftx/manifest.json',
                     '/published/off/tx%2fmanifest.json', '/published/off/tx/it1%2f..%2fmanifest.json',
                     '/published/off/tx/%252e%252e/secret.txt', '/published/off/tx//manifest.json',
                     '/published/off/tx/it1//alpha/index.html', '/published/off/tx/%2fsecret.txt',
                     '/published/off/tx/../sibling/index.html', '/published/off/tx/%2e%2e/sibling/index.html'):
            with self.subTest(path=path):
                self.gone(path)
        # `%2f` усередині сегмента не стає сегментом: це ОДНЕ імʼя `it1/alpha/index.html`, а не шлях до сторінки
        self.assertTrue(os.path.isfile(os.path.join(self.dest, 'it1', 'alpha', 'index.html')))
        self.gone('/published/off/tx/it1%2falpha%2findex.html')

    def test_broken_encodings_are_404(self):
        for path in ('/published/off/tx/%00', '/published/off/tx/manifest.json%00', '/published/off/tx/%00manifest.json',
                     '/published/off/tx/%ff', '/published/off/tx/%c0%af', '/published/off/tx/%', '/published/off/tx/%zz',
                     '/published/off/tx/%1fmanifest.json', '/published/off/tx/%7fmanifest.json',
                     '/published/off/tx/a%3ab', '/published/off/%00/manifest.json', '/published/%ff/tx/', '/published/off/%ff/'):
            with self.subTest(path=path):
                self.gone(path)

    def test_an_invalid_utf8_escape_does_not_alias_a_file_named_with_the_replacement_character(self):
        """`%ff` — не UTF-8: `unquote` без `errors='strict'` дав би U+FFFD, тобто адресу ІНШОГО (наявного) файла."""
        self.put(os.path.join(self.dest, '\ufffd.txt'), 'REPL')
        self.assertEqual(self.ok(self.root + '%EF%BF%BD.txt')[1], b'REPL')                  # контроль: справжній U+FFFD
        self.gone(self.root + '%ff.txt')
        self.gone(self.root + '%c0%af.txt')

    def test_windows_separators_and_stream_syntax_are_refused_even_where_the_name_is_legal(self):
        """`\\` і `:` — законні в імені на POSIX, але на Windows це роздільник і потік NTFS (`a::$DATA`); сегмент із
        ними не віддаємо ніде: роздача мусить поводитись однаково на обох системах."""
        for name in ('we\\ird.txt', 'co:lon.txt'):
            self.put(os.path.join(self.dest, name), 'ODD')
            self.assertTrue(os.path.isfile(os.path.join(self.dest, name)), f'свідок: файл {name!r} існує')
            self.gone(self.root + urllib.parse.quote(name, safe=''))
        self.gone(self.root + 'it1%5c..%5cmanifest.json')

    def test_a_symlink_file_is_404_even_when_it_points_inside_the_published_folder(self):
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        os.symlink(outside, os.path.join(self.dest, 'out.txt'))                       # назовні
        os.symlink(os.path.join(self.dest, 'manifest.json'), os.path.join(self.dest, 'in.json'))   # усередину
        self.put(os.path.join(self.dest, 'copy.json'), _read(os.path.join(self.dest, 'manifest.json')))
        self.ok(self.root + 'copy.json')                                              # контроль: звичайний файл тут віддається
        self.gone(self.root + 'out.txt')
        self.gone(self.root + 'in.json')
        # `index.html` теки — теж посилання (звичайна тека, а її індекс веде всередину)
        os.makedirs(os.path.join(self.dest, 'lnkidx'))
        os.symlink(os.path.join(self.dest, 'index.html'), os.path.join(self.dest, 'lnkidx', 'index.html'))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, 'lnkidx', 'index.html')))
        self.gone(self.root + 'lnkidx/')
        self.gone(self.root + 'lnkidx/index.html')

    def test_a_symlink_dir_is_404_even_when_it_points_inside_the_published_folder(self):
        out = os.path.join(self.folder, 'elsewhere')
        self.put(os.path.join(out, 'index.html'), 'OUT')
        self.put(os.path.join(out, 'a.txt'), 'OUT')
        os.symlink(out, os.path.join(self.dest, 'outdir'))                            # назовні
        os.symlink(os.path.join(self.dest, 'it1'), os.path.join(self.dest, 'indir'))  # усередину
        self.ok(self.root + 'it1/alpha/index.html')                                   # контроль
        for path in ('outdir/', 'outdir/index.html', 'outdir/a.txt', 'outdir', 'indir/alpha/index.html', 'indir/alpha/',
                     'indir/pages.json', 'indir', 'indir/'):
            with self.subTest(path=path):
                self.gone(self.root + path)             # навіть без слеша: посилання відсікається ДО перенаправлення

    def test_a_symlinked_task_folder_is_404(self):
        real = os.path.join(self.folder, 'real-tx')
        os.rename(self.dest, real)
        os.symlink(real, self.dest)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, 'manifest.json')), 'свідок: через посилання файл читається')
        for path in ('manifest.json', '', 'index.html', 'shell/ext-shell.js'):
            self.gone(self.root + path)

    def test_the_realpath_check_holds_even_when_islink_lies(self):
        """Друга лінія: теки-стики Windows (junction) `os.path.islink` не вважає посиланням (до Python 3.12), а
        `realpath` веде за межі. Тут `islink` підмінено на «ні» — і посилання назовні все одно не віддається."""
        out = os.path.join(self.folder, 'elsewhere')
        self.put(os.path.join(out, 'a.txt'), 'OUT')
        self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        os.symlink(out, os.path.join(self.dest, 'outdir'))
        os.symlink(os.path.join(self.folder, 'secret.txt'), os.path.join(self.dest, 'out.txt'))
        with mock.patch.object(os.path, 'islink', return_value=False):
            self.gone(self.root + 'outdir/a.txt')
            self.gone(self.root + 'out.txt')
            self.ok(self.root + 'manifest.json')

    def test_dotfiles_and_dot_folders_are_404(self):
        self.put(os.path.join(self.dest, '.hidden', 'x'), 'H')
        self.put(os.path.join(self.dest, '.hidden', 'index.html'), 'H')
        self.put(os.path.join(self.dest, 'it1', '.env'), 'ENV')
        self.put(os.path.join(self.dest, '.well-known', 'a.txt'), 'W')
        self.put(os.path.join(self.dest, '.tmp-tx-deadbeef', 'index.html'), 'T')
        self.put(os.path.join(self.dest, '.old-tx-cafebabe', 'index.html'), 'O')
        self.put(os.path.join(self.folder, '.tmp-tx-deadbeef', 'index.html'), 'T')
        self.put(os.path.join(self.folder, '.old-tx-cafebabe', '.deai-published'), 'O')
        self.assertTrue(os.path.isfile(os.path.join(self.dest, serve.PUBLISHED_MARKER)), 'свідок: маркер модуля там, де ядро його шукає')
        for path in ('.deai-published', '.hidden/x', '.hidden/index.html', '.hidden/', 'it1/.env', '.well-known/a.txt',
                     '.tmp-tx-deadbeef/index.html', '.old-tx-cafebabe/index.html', '%2edeai-published', '.HIDDEN/x'):
            with self.subTest(path=path):
                self.gone(self.root + path)
        self.gone('/published/off/.tmp-tx-deadbeef/index.html')
        self.gone('/published/off/.old-tx-cafebabe/.deai-published')

    def test_task_ids_the_module_could_never_publish_are_404(self):
        """Id задачі — те саме правило, що в диспетчері й модулі (`publish_id_ok`): Unicode, імена пристроїв Windows
        і 129 символів не віддаються, хоч би така тека лежала в теці публікації."""
        names = {'юнікод': 'задача', 'CON': 'CON', 'con': 'con', 'NUL': 'NUL', 'COM1': 'COM1', '129': 'x' * 129,
                 'крапка': 'a.b', 'пробіл': 'a b'}
        for what, name in names.items():
            try:
                self.put(os.path.join(self.folder, name, 'index.html'), 'BAD')
                self.put(os.path.join(self.folder, name, '.deai-published'), 'm')
            except OSError:
                continue                                    # ФС не дозволяє таку теку (Windows: CON) — і гаразд
            with self.subTest(what):
                self.gone('/published/off/' + urllib.parse.quote(name, safe='') + '/')
                self.gone('/published/off/' + urllib.parse.quote(name, safe='') + '/index.html')
        # контроль: межа 128 і `console` (не імʼя пристрою) віддаються
        for name in ('x' * 128, 'console', 'COM10', 'Task_1-b'):
            self.put(os.path.join(self.folder, name, 'index.html'), 'GOOD')
            self.put(os.path.join(self.folder, name, '.deai-published'), 'm')
            self.assertEqual(self.ok(f'/published/off/{name}/')[1], b'GOOD', name)

    def test_only_a_folder_the_module_marked_is_served(self):
        """Теку `<тека>/<id>` без маркера модуля не віддаємо: налаштування `folder` може вказувати на теку з чужим
        вмістом (вона пройшла `folder_ok`), а `Access-Control-Allow-Origin: *` дав би його читати будь-якій
        сторінці. Маркер — те, що модуль пише сам (`.deai-published`) і за чим відрізняє свої теки."""
        self.put(os.path.join(self.folder, 'foreign', 'index.html'), 'FOREIGN')
        self.put(os.path.join(self.folder, 'foreign', 'notes.txt'), 'FOREIGN')
        self.gone('/published/off/foreign/')
        self.gone('/published/off/foreign/notes.txt')
        self.put(os.path.join(self.folder, 'foreign', '.deai-published'), 'm')
        self.assertEqual(self.ok('/published/off/foreign/notes.txt')[1], b'FOREIGN')       # контроль
        os.remove(os.path.join(self.dest, '.deai-published'))
        self.gone(self.root + 'manifest.json')
        os.symlink(os.path.join(self.folder, 'foreign', 'notes.txt'), os.path.join(self.dest, '.deai-published'))
        self.gone(self.root + 'manifest.json')                                              # маркер — звичайний файл, не посилання

    # ---- довкола ----

    def test_a_post_with_origin_null_is_still_refused(self):
        """Сторінка в пісочниці без `allow-same-origin` має Origin `null`; API канваса такі POST відхиляє, тож
        опублікована сторінка не може керувати канвасом (CORS їй для цього й не дає)."""
        shutil.rmtree(os.path.join(self.tx_dir, 'publish'))
        st, body = self.post('/api/publish', headers={'Origin': 'null'})
        self.assertEqual((st, body.get('ok')), (403, False), body)
        self.assertFalse(os.path.exists(os.path.join(self.tx_dir, 'publish')), 'публікація виконалась попри чужий Origin')

    def test_a_hard_link_to_a_file_outside_is_404(self):
        """Копії модуля мають `st_nlink == 1`; жорстке посилання на чужий файл — ні, і `islink` його не бачить."""
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        link = os.path.join(self.dest, 'hard.txt')
        try:
            os.link(outside, link)
        except OSError:
            self.skipTest('ФС без жорстких посилань')
        self.assertEqual(os.stat(link).st_nlink, 2, 'свідок: файл справді має два імені')
        self.put(os.path.join(self.dest, 'copy.txt'), 'SECRET')                               # контроль: копія з тим самим вмістом
        self.assertEqual(self.ok(self.root + 'copy.txt')[1], b'SECRET')
        self.gone(self.root + 'hard.txt')

    def test_a_folder_setting_in_another_letter_case_still_serves(self):
        """На ФС без урахування регістру (macOS) налаштування `~/Deai-Published` і справжня `~/deai-published` — одна
        тека; шлях ВІДКРИТОГО файла ядро віддає зі справжнім регістром диска, тож тека задачі беретиться в тій самій
        формі (з дескриптора), а не `realpath` написаного: інакше порівняння двох написань дало б хибний 404."""
        upper = os.path.join(self.home, 'DEAI-PUBLISHED', 'off')
        if not os.path.isdir(upper):
            self.skipTest('ФС розрізняє регістр')
        self.set_folder(upper)
        self.assertEqual(dm.published_root(self.off, MID), upper)
        self.assertTrue(dm.folder_ok(self.off, upper)[0])
        self.ok(self.root + 'manifest.json')
        self.ok(self.root + 'it1/alpha/index.html')

    def test_a_large_file_is_streamed_in_chunks_and_arrives_intact(self):
        data = bytes(range(256)) * 20480                                                         # 5 МіБ
        self.put(os.path.join(self.dest, 'big.bin'), data, 'wb')
        sizes, real_fdopen = [], os.fdopen

        class Spy:
            def __init__(self, f):
                self.f = f

            def read(self, n=-1):
                sizes.append(n)
                return self.f.read(n)

            def __getattr__(self, name):
                return getattr(self.f, name)

        with mock.patch.object(os, 'fdopen', lambda *a, **kw: Spy(real_fdopen(*a, **kw))):
            hd, body = self.ok(self.root + 'big.bin')
        self.assertEqual(hd['content-length'], str(len(data)))
        self.assertEqual(hashlib.sha256(body).hexdigest(), hashlib.sha256(data).hexdigest())
        self.assertEqual(hd['content-type'], 'application/octet-stream')
        self.assertGreaterEqual(len(sizes), len(data) // serve.PUBLISHED_CHUNK)
        self.assertTrue(all(0 < n <= serve.PUBLISHED_CHUNK for n in sizes), f'файл читався не шматками: {sizes[:3]}')

    def test_control_characters_in_a_name_are_refused_even_where_the_name_is_legal(self):
        for name in ('ctl\x1f.txt', 'del\x7f.txt', 'nl\x0a.txt'):
            self.put(os.path.join(self.dest, name), 'CTL')
            self.assertTrue(os.path.isfile(os.path.join(self.dest, name)), f'свідок: файл {name!r} існує')
            self.gone(self.root + urllib.parse.quote(name, safe=''))
        self.put(os.path.join(self.dest, 'ctl.txt'), 'OK')                                       # контроль: без керівного
        self.assertEqual(self.ok(self.root + 'ctl.txt')[1], b'OK')

    def raw_head(self, target):
        """Сирий запит із ТОЧНИМИ байтами цілі (http.client відмовив би на керівних): `(статус, {заголовок: байти}, голова)`."""
        with socket.create_connection(('127.0.0.1', self.port), timeout=10) as sock:
            sock.sendall(b'GET ' + target + b' HTTP/1.0\r\nHost: x\r\n\r\n')
            data = b''
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        head = data.partition(b'\r\n\r\n')[0]
        lines = head.split(b'\r\n')
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(b': ')
            headers[name.lower().decode('ascii')] = value
        return int(lines[0].split()[1]), headers, head

    def test_the_redirect_location_stays_inside_published_whatever_the_query_holds(self):
        expected = {'server', 'date', 'location', 'content-length', 'content-security-policy',
                    'x-content-type-options', 'access-control-allow-origin', 'cache-control'}
        queries = (b'a=1#frag//evil.com', b'//evil.com', b'\\\\evil.com', b'x=%0d%0aSet-Cookie:%20a=b',
                   b'q=\x01\x02\x7f\xe9\xff', b'u=http://evil.com/%2e%2e', b'a=1&b=%D0%B6', b'')
        for q in queries:
            with self.subTest(query=q):
                target = b'/published/off/tx' + (b'?' + q if q else b'')
                st, headers, head = self.raw_head(target)
                self.assertEqual(st, 301, head)
                loc = headers['location']
                self.assertTrue(loc.startswith(b'/published/off/tx/'), loc)
                self.assertFalse(loc.startswith(b'//'), loc)
                self.assertTrue(all(0x21 <= c <= 0x7e for c in loc), f'Location несе керівні чи не-ASCII байти: {loc!r}')
                self.assertNotIn(b'#', loc, 'фрагмент не став `%23`')
                self.assertNotIn(b'\r', head.replace(b'\r\n', b''), 'CR усередині заголовків')
                self.assertLessEqual(set(headers), expected, 'зʼявився вставлений заголовок')
                self.assertEqual(head.count(b'\r\n'), len(headers), 'зайвий рядок у голові відповіді')
        st, headers, _ = self.raw_head(b'/published/off/tx?a=1#frag')
        self.assertEqual(headers['location'], b'/published/off/tx/?a=1%23frag')
        st, headers, _ = self.raw_head(b'/published/off/tx?x=%0d%0aSet-Cookie:%20a=b')
        self.assertEqual(headers['location'], b'/published/off/tx/?x=%0d%0aSet-Cookie:%20a=b')   # `%0d%0a` лишився ТЕКСТОМ

    def test_a_symlinked_publish_folder_is_still_served(self):
        """Сама тека публікації може бути посиланням (як при публікації: `realpath` розвʼязується ОДИН раз)."""
        real = os.path.join(self.home, 'pubs', 'real')
        alias = os.path.join(self.home, 'pubs', 'alias')
        os.makedirs(real)
        os.symlink(real, alias)
        self.set_folder(alias)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['local']['path'], os.path.join(alias, 'tx'))
        self.assertTrue(os.path.isfile(os.path.join(real, 'tx', 'index.html')))
        self.ok(self.root + 'manifest.json')
        self.ok(self.root + 'it1/alpha/')

    def fd_count(self):
        if not os.path.isdir('/dev/fd'):
            self.skipTest('нема /dev/fd')
        return len(os.listdir('/dev/fd'))

    def settled_fd_growth(self, before, limit=12):
        """Дескриптори вирівнюються не миттєво (потік обробника дописує після відповіді клієнту): чекаємо до 5 с."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            growth = self.fd_count() - before
            if growth < limit:
                return growth
            time.sleep(0.1)
        return self.fd_count() - before

    def test_serving_leaks_no_descriptors_on_200_304_404_and_a_dropped_client(self):
        data = bytes(range(256)) * 20480                                                         # 5 МіБ: не вміщається в буфери сокета
        self.put(os.path.join(self.dest, 'big.bin'), data, 'wb')
        etag = self.ok(self.root + 'manifest.json')[0]['etag']
        before = self.fd_count()
        for _ in range(60):
            self.assertEqual(self.fetch(self.root + 'manifest.json')[0], 200)
            self.assertEqual(self.fetch(self.root + 'manifest.json', {'If-None-Match': etag})[0], 304)
            self.assertEqual(self.fetch(self.root + 'nope.txt')[0], 404)
            self.assertEqual(self.fetch(self.root + 'it1/alpha')[0], 301)
        self.assertLess(self.settled_fd_growth(before), 12, '200/304/404/301 лишають дескриптори')
        before = self.fd_count()
        for _ in range(25):                                                                      # клієнт іде посеред відповіді
            sock = socket.create_connection(('127.0.0.1', self.port), timeout=10)
            sock.sendall(b'GET ' + self.root.encode() + b'big.bin HTTP/1.0\r\nHost: x\r\n\r\n')
            sock.recv(4096)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b'\x01\x00\x00\x00\x00\x00\x00\x00')   # RST при закритті
            sock.close()
        self.assertLess(self.settled_fd_growth(before), 12, 'обрив клієнта посеред файла лишає дескриптор')

    def test_a_file_that_vanishes_between_the_check_and_the_read_is_404(self):
        """Публікація посеред заміни теки: файл був у перевірці, а до читання зник — порожній 404 із захисними
        заголовками, а не обрив зʼєднання."""
        gone = os.path.join(self.dest, 'vanished.txt')
        with mock.patch.object(serve, 'published_target', return_value=('file', gone, self.dest)):
            self.gone(self.root + 'vanished.txt')

    def test_nothing_leaves_the_machine(self):
        for path in (self.root, self.root + 'manifest.json', '/published/off/tx', self.root + 'nope', '/published/nope/x/'):
            self.fetch(path)
        self.assert_quiet()


class PublishedRoute(_PublishedTests, DispatchWorld):
    """Роздача на ОС з `dir_fd` (macOS, Linux): обхід теки дескрипторами (`serve._published_walk`), закрито по збою.
    Підміну диска вставляємо ШВАМИ — `_published_openat`/`_published_statat`/`_published_fstat`, що їх обхід кличе між
    кроками: перед відкриттям імені диск змінюється (посилання замість файла, теки, жорстке посилання…) — і відповідь
    мусить бути 404 (чи, коли підміна після відкриття, лишитись відповіддю про те, що вже відкрито)."""

    def setUp(self):
        if not serve._PUBLISHED_DIRFD:
            if sys.platform in ('darwin', 'linux'):          # тут обхід МУСИТЬ діяти: мовчазний пропуск знищив би тести
                self.fail('на macOS/Linux обхід дескрипторами вимкнено (`_PUBLISHED_DIRFD` хибне)')
            self.skipTest('ОС без dir_fd: обхід дескрипторами не діє')
        super().setUp()

    def seam(self, name, when, mutate, after=False):
        """Шов `serve.<name>`: на першому виклику, для якого `when(*args)` істинне, виконується `mutate()` — ПЕРЕД
        справжнім викликом (`after=True` — ПІСЛЯ нього). `fired` — чи спрацював (хук, що не спрацював, нічого б не доводив)."""
        real = getattr(serve, name)
        fired = []

        def wrapper(*args, **kw):
            hit = not fired and when(*args, **kw)
            if hit and not after:
                fired.append(1)
                mutate()
            out = real(*args, **kw)
            if hit and after:
                fired.append(1)
                mutate()
            return out
        patch = mock.patch.object(serve, name, wrapper)
        patch.start()
        self.addCleanup(patch.stop)
        return fired

    def test_the_walk_is_the_one_in_charge_here(self):
        found = serve.published_target('/published/off/tx/manifest.json')
        self.assertEqual(found[0], 'opened')
        os.close(found[2][0])

    # ---- файл: імʼя зайняли між lstat і open ----

    def test_a_file_swapped_for_a_symlink_between_the_lstat_and_the_open_is_refused(self):
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        victim = self.put(os.path.join(self.dest, 'swap.txt'), 'REAL')
        self.put(os.path.join(self.dest, 'inside.txt'), 'INSIDE')
        self.assertEqual(self.ok(self.root + 'swap.txt')[1], b'REAL')                         # контроль: без підміни віддається
        for target in (outside, os.path.join(self.dest, 'inside.txt')):                       # назовні й усередину — обидва `O_NOFOLLOW`
            with self.subTest(target=os.path.basename(target)):
                if os.path.lexists(victim):
                    os.remove(victim)                                      # без `put` крізь посилання в чужий файл
                self.put(victim, 'REAL')

                def swap(target=target):
                    os.remove(victim)
                    os.symlink(target, victim)
                fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'swap.txt', swap)
                self.gone(self.root + 'swap.txt')
                self.assertTrue(fired, 'підміна не відбулась: тест порожній')
                self.assertEqual(_read(target), 'SECRET' if target == outside else 'INSIDE')

    def test_a_file_replaced_by_another_regular_file_between_the_lstat_and_the_open_is_refused(self):
        """Той самий `(st_dev, st_ino)`, що в `lstat`, або відмова: імʼя між `lstat` і `open` не сміє вказати на інший файл."""
        victim = self.put(os.path.join(self.dest, 'swap.txt'), 'REAL')

        def swap():
            self.put(victim + '.new', 'NEW-CONTENT')
            os.replace(victim + '.new', victim)
        self.assertEqual(self.ok(self.root + 'swap.txt')[1], b'REAL')
        fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'swap.txt', swap)
        self.gone(self.root + 'swap.txt')
        self.assertTrue(fired)

    def test_a_file_swapped_after_the_open_is_served_as_it_was_opened(self):
        """Те, що вже відкрито, не міняється від підміни імені ПІСЛЯ відкриття: віддається відкритий файл, не нове імʼя."""
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        victim = self.put(os.path.join(self.dest, 'swap.txt'), 'REAL')

        def swap():
            os.remove(victim)
            os.symlink(outside, victim)
        fired = self.seam('_published_fstat', lambda fd: True, swap, after=True)       # імʼя підмінено ПІСЛЯ `fstat`
        hd, body = self.ok(self.root + 'swap.txt')
        self.assertEqual(body, b'REAL')
        self.assertTrue(fired)

    def test_a_fifo_swapped_in_between_the_lstat_and_the_open_is_404_and_does_not_hang_a_thread(self):
        if not hasattr(os, 'mkfifo'):
            self.skipTest('нема mkfifo')
        victim = self.put(os.path.join(self.dest, 'it2', 'pipe.txt'), 'REAL')
        self.assertEqual(self.ok(self.root + 'it2/pipe.txt')[1], b'REAL')

        def swap():
            os.remove(victim)
            os.mkfifo(victim)
        fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'pipe.txt', swap)
        t0 = time.monotonic()
        self.gone(self.root + 'it2/pipe.txt')
        self.assertLess(time.monotonic() - t0, 5, '`open` на FIFO завис')
        self.assertTrue(fired)

    # ---- жорсткі посилання ----

    def test_a_hard_link_dropped_between_the_open_and_the_fstat_is_still_refused(self):
        """Файл має два імені на момент `lstat`; друге імʼя прибирається, поки ми відкриваємо, — `fstat` побачив би
        `nlink == 1` і той самий `ino`, і лише перевірка `nlink` ДО відкриття (в `lstat`) відмовляє. Тож шов `fstat`
        з незвʼязуванням у нормі НЕ спрацьовує (відмова вже була), а без цієї перевірки спрацьовує і файл віддається —
        на цьому тримається доведення мутацією."""
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        link = os.path.join(self.dest, 'h.txt')
        os.link(outside, link)
        self.assertEqual(os.stat(outside).st_nlink, 2, 'свідок: на момент `lstat` файл має два імені')
        self.seam('_published_fstat', lambda fd: True, lambda: os.unlink(link))
        hd, body = self.fetch(self.root + 'h.txt')[1:]
        self.assertNotIn(b'SECRET', body)
        self.gone(self.root + 'h.txt')

    def test_a_hard_link_made_between_the_lstat_and_the_open_is_refused(self):
        """Файл мав одне імʼя на момент `lstat`; другим іменем його зв'язали, поки ми відкривали: `fstat` — `nlink == 2`
        (той самий `ino`, тож порівняння `ino` цього не бачить)."""
        victim = self.put(os.path.join(self.dest, 'h3.txt'), 'REAL')
        self.assertEqual(self.ok(self.root + 'h3.txt')[1], b'REAL')
        fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'h3.txt',
                          lambda: os.link(victim, os.path.join(self.folder, 'alias.txt')))
        self.gone(self.root + 'h3.txt')
        self.assertTrue(fired)

    # ---- проміжні теки й тека задачі ----

    def test_an_intermediate_directory_swapped_for_a_symlink_before_its_open_is_refused(self):
        self.put(os.path.join(self.dest, 'sub', 'page.txt'), 'REAL')
        out = self.put(os.path.join(self.folder, 'elsewhere', 'page.txt'), 'OUT')
        self.assertEqual(self.ok(self.root + 'sub/page.txt')[1], b'REAL')

        def swap():
            os.rename(os.path.join(self.dest, 'sub'), os.path.join(self.dest, 'sub.moved'))
            os.symlink(os.path.dirname(out), os.path.join(self.dest, 'sub'))
        fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'sub', swap)
        self.gone(self.root + 'sub/page.txt')
        self.assertTrue(fired)

    def outside_task(self):
        """Тека ПОЗА `<тека>/<задача>`, що має маркер і файл — приманка для підміни теки задачі посиланням."""
        out = os.path.join(self.home, 'outside-task')
        self.put(os.path.join(out, '.deai-published'), 'm')
        self.put(os.path.join(out, 'index.html'), 'SECRET-OUTSIDE')
        self.put(os.path.join(out, 'manifest.json'), 'SECRET-OUTSIDE')
        return out

    def test_the_task_folder_swapped_for_a_symlink_before_its_open_is_refused(self):
        out = self.outside_task()

        def swap():
            os.rename(self.dest, self.dest + '.moved')
            os.symlink(out, self.dest)
        self.assertEqual(self.ok(self.root + 'manifest.json')[0]['content-type'], 'application/json')
        fired = self.seam('_published_openat', lambda name, *a, **kw: name == 'tx', swap)
        self.gone(self.root + 'index.html')
        self.assertTrue(fired)

    def test_the_task_folder_swapped_for_a_symlink_after_the_marker_check_never_serves_the_outside(self):
        """Підміна ПІСЛЯ перевірки маркера: тека задачі вже відкрита дескриптором, тож далі йде ТА, що відкрито, — і
        нічого з чужої теки (раніше `realpath` вів за посиланням, і «своєю» ставала чужа тека)."""
        out = self.outside_task()

        def swap():
            os.rename(self.dest, self.dest + '.moved')
            os.symlink(out, self.dest)
        fired = self.seam('_published_statat', lambda name, dir_fd: name == '.deai-published', swap, after=True)
        hd, body = self.ok(self.root + 'index.html')
        self.assertNotIn(b'SECRET-OUTSIDE', body)
        self.assertEqual(body, _bytes(os.path.join(self.dest + '.moved', 'index.html')))
        self.assertTrue(fired)

    def test_an_ancestor_of_the_folder_swapped_between_the_realpath_and_the_open_is_refused(self):
        """Предка теки публікації підмінили посиланням: відкриття веде до іншої теки, і шлях ВІДКРИТОГО дескриптора
        (ядро) не збігається зі схваленим `realpath` — відмова, хоч остання складова й справжня тека."""
        root = os.path.join(self.home, 'deai-published')
        outside_root = os.path.join(self.home, 'outside-root')
        self.put(os.path.join(outside_root, 'off', 'tx', '.deai-published'), 'm')
        self.put(os.path.join(outside_root, 'off', 'tx', 'index.html'), 'SECRET-OUTSIDE')

        def swap():
            os.rename(root, root + '.moved')
            os.symlink(outside_root, root)
        self.assertEqual(self.ok(self.root + 'index.html')[1], _bytes(os.path.join(self.dest, 'index.html')))
        fired = self.seam('_published_openat', lambda name, flags, dir_fd=None: dir_fd is None, swap)
        self.gone(self.root + 'index.html')
        self.assertTrue(fired)

    # ---- імена, журнал розбіжності, повторна folder_ok ----

    def test_the_walk_refuses_a_name_that_is_not_one_path_component_before_any_openat(self):
        """Другий замок за `_published_segments`: обхід сам не відкриває ні `..`, ні порожнє, ні імʼя зі `/` чи NUL
        (`..` відносно теки-дескриптора виводить за межі теки без жодного посилання). Прямий виклик обходу."""
        self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        ok = lambda path: True
        opened = serve._published_walk(self.folder, 'tx', ['manifest.json'], False, ok)       # контроль: звичайне імʼя проходить
        self.assertEqual(opened[0], 'manifest.json')
        os.close(opened[1][0])
        calls = []
        real = serve._published_openat

        def spy(*args, **kw):
            calls.append(args[0])
            return real(*args, **kw)
        cases = [('tx', ['..', 'secret.txt'], False), ('tx', ['sub', '..', 'secret.txt'], False), ('tx', ['.'], True),
                 ('tx', [''], False), ('tx', ['a/b'], False), ('tx', ['a\0b'], False), ('tx', ['it1', '..'], True),
                 ('..', ['tx', 'manifest.json'], False), ('', ['manifest.json'], False), ('.', [], True),
                 ('tx/..', [], True), ('t\0x', [], True), ('tx', [None], False)]
        with mock.patch.object(serve, '_published_openat', spy):
            for tid, rel, trailing in cases:
                with self.subTest(tid=tid, rel=rel):
                    self.assertIsNone(serve._published_walk(self.folder, tid, rel, trailing, ok))
        self.assertEqual(calls, [], f'обхід відкривав щось до відмови: {calls}')

    def test_a_kernel_path_mismatch_is_a_constant_404_with_one_log_line_per_folder(self):
        """Шлях теки за `realpath` і шлях її відкритого дескриптора розійшлись (зовнішній том, FUSE, iCloud): роздача —
        порожній 404 (закрито по збою), а оператор отримує ОДИН рядок у stderr сервера (не у відповіді) на теку."""
        serve._PUBLISHED_WARNED.clear()
        self.addCleanup(serve._PUBLISHED_WARNED.clear)
        buf = io.StringIO()
        with mock.patch.object(serve, '_published_fd_path', return_value='/mnt/other/off'), \
                mock.patch.object(sys, 'stderr', buf):
            for _ in range(8):                                              # завантаження сторінки — десятки файлів
                self.gone(self.root + 'manifest.json')                      # `gone`: тіло завжди `not found\n`
            self.gone(self.root)
        lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith('published:')]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(os.path.realpath(self.folder), lines[0])
        self.assertIn('/mnt/other/off', lines[0])
        # інша тека — окремий рядок
        two = os.path.join(self.home, 'pubs', 'two')
        self.set_folder(two)
        self.assertEqual(self.post('/api/publish')[0], 200)
        buf = io.StringIO()
        with mock.patch.object(serve, '_published_fd_path', return_value='/mnt/other/two'), mock.patch.object(sys, 'stderr', buf):
            for _ in range(5):
                self.gone(self.root + 'manifest.json')
        lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith('published:')]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(os.path.realpath(two), lines[0])

    def test_an_unavailable_kernel_path_is_logged_once_too(self):
        serve._PUBLISHED_WARNED.clear()
        self.addCleanup(serve._PUBLISHED_WARNED.clear)
        buf = io.StringIO()
        with mock.patch.object(serve, '_published_fd_path', return_value=None), mock.patch.object(sys, 'stderr', buf):
            for _ in range(5):
                self.gone(self.root + 'manifest.json')
        lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith('published:')]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn('недоступний', lines[0])

    def test_folder_ok_is_run_again_on_the_folder_that_was_really_opened(self):
        """Посилання-предка перенаправили МІЖ `folder_ok` і відкриттям (на теку простору): `realpath` і шлях дескриптора
        збігаються, але вказують на чужу теку — її відсікає лише повторна `folder_ok` на ВІДКРИТІЙ теці. Теку задачі
        простору позначено маркером, щоб між файлом (`iterations.json`) і відповіддю стояла лише ця перевірка."""
        self.put(os.path.join(self.tx_dir, '.deai-published'), 'm')
        root = os.path.join(self.home, 'deai-published')
        self.gone(self.root + 'iterations.json')                                  # контроль: до підміни це не під текою публікації
        real = dm.folder_ok
        fired = []

        def after_first(*args, **kw):
            out = real(*args, **kw)
            if not fired:
                fired.append(1)
                os.rename(root, root + '.moved')
                os.symlink(os.path.join(self.home, 'deai-work'), root)           # `<root>/off` тепер = тека простору
            return out
        with mock.patch.object(dm, 'folder_ok', after_first):
            self.gone(self.root + 'iterations.json')
            self.gone(self.root + 'manifest.json')
        self.assertTrue(fired)
        self.assertEqual(os.path.realpath(os.path.join(root, 'off')), os.path.realpath(self.off_path), 'свідок: підміна справді повела в простір')
        self.assertFalse(dm.folder_ok(self.off, self.off_path)[0], 'свідок: правило відмовляє теку простору')

    # ---- закрито по збою ----

    def test_without_a_descriptor_path_nothing_is_served_on_a_platform_that_has_one(self):
        """Шлях дескриптора теки недоступний (збій `F_GETPATH`: довгий шлях; Python без нього) — на ОС, що його ДАЄ, це
        відмова, а не відкат на `realpath`."""
        self.ok(self.root + 'manifest.json')
        with mock.patch.object(serve, '_published_fd_path', return_value=None):
            self.gone(self.root + 'manifest.json')
            self.gone(self.root)
            self.assertIsNone(serve.published_target('/published/off/tx/manifest.json'))

    def test_a_failing_getpath_is_a_404_and_not_a_fallback(self):
        if serve.fcntl is None or not hasattr(serve.fcntl, 'F_GETPATH'):
            self.skipTest('ОС без F_GETPATH')
        real = serve.fcntl.fcntl

        def failing(fd, cmd, *a):
            if cmd == serve.fcntl.F_GETPATH:
                raise OSError(28, 'No space left on device')
            return real(fd, cmd, *a)
        with mock.patch.object(serve.fcntl, 'fcntl', failing):
            self.gone(self.root + 'manifest.json')
        self.ok(self.root + 'manifest.json')

    def test_a_missing_marker_or_a_foreign_marker_kind_on_the_task_folder_is_refused_by_the_fd_check(self):
        """Маркер перевіряється `lstat`-ом у ВІДКРИТІЙ теці: тека (не файл) чи посилання з тим самим іменем — не маркер."""
        os.remove(os.path.join(self.dest, '.deai-published'))
        os.mkdir(os.path.join(self.dest, '.deai-published'))
        self.gone(self.root + 'manifest.json')

    def test_the_capability_check_is_what_picks_the_walk(self):
        self.assertTrue(serve._PUBLISHED_DIRFD)
        with mock.patch.object(serve, '_PUBLISHED_DIRFD', False):
            found = serve.published_target('/published/off/tx/manifest.json')
            self.assertEqual(found[0], 'file')


class PublishedRouteFallback(_PublishedTests, DispatchWorld):
    """Той самий набір поведінки на ОС БЕЗ `dir_fd` (Windows): `_PUBLISHED_DIRFD` вимкнено, і роздача йде запасним шляховим
    способом (`_published_target_by_path` + `open_published_file`). Він слабший — і документований як такий; тут
    доводиться те, що він усе ж робить: відмовляє підміну, яка вже сталась до відкриття, віддає звичайні файли."""

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(serve, '_PUBLISHED_DIRFD', False)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_path_based_fallback_is_what_runs(self):
        found = serve.published_target('/published/off/tx/manifest.json')
        self.assertEqual(found[0], 'file')

    # ---- підміна між перевіркою й відкриттям (лише запасний спосіб: рішення і `open` розділені) ----

    def after_resolve(self, mutate):
        """Підміна `published_target`: рішення ухвалено (усі перевірки шляху пройдено), і ЛИШЕ ТОДІ диск змінюється — рівно
        той проміжок між перевіркою й відкриттям файла, який використовує гонка з посиланнями."""
        real = serve.published_target

        def hooked(path):
            found = real(path)
            mutate()
            return found
        return mock.patch.object(serve, 'published_target', hooked)

    def test_a_file_swapped_for_a_symlink_after_the_checks_is_not_followed(self):
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        victim = self.put(os.path.join(self.dest, 'swap.txt'), 'REAL')
        self.put(os.path.join(self.dest, 'inside.txt'), 'INSIDE')
        self.assertEqual(self.ok(self.root + 'swap.txt')[1], b'REAL')                         # контроль: без підміни віддається

        def to(target):
            def swap():
                os.remove(victim)
                os.symlink(target, victim)
            return swap
        with self.after_resolve(to(outside)):                  # назовні: це ловить і перевірка шляху дескриптора
            self.gone(self.root + 'swap.txt')
        os.remove(victim)
        self.put(victim, 'REAL')
        with self.after_resolve(to(os.path.join(self.dest, 'inside.txt'))):     # усередину: лише `O_NOFOLLOW`
            self.gone(self.root + 'swap.txt')

    def test_without_a_descriptor_path_the_fallback_still_refuses_an_escape(self):
        """ОС без шляху дескриптора (Windows): запасний варіант — `realpath(target)` ПІСЛЯ відкриття. Слабший, але
        підміну, що вже сталась до відкриття, ловить, а звичайні файли віддаються."""
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        with mock.patch.object(serve, '_published_fd_path', return_value=None):
            self.assertEqual(self.ok(self.root + 'it2/index.html')[1], _bytes(os.path.join(self.dest, 'it2', 'index.html')))
            self.put(os.path.join(self.dest, 'sub', 'page.txt'), 'REAL')
            self.assertEqual(self.ok(self.root + 'sub/page.txt')[1], b'REAL')

            def swap_dir():
                os.rename(os.path.join(self.dest, 'sub'), os.path.join(self.dest, 'sub.moved'))
                os.symlink(os.path.dirname(outside), os.path.join(self.dest, 'sub'))
            self.put(os.path.join(self.folder, 'page.txt'), 'OUT')
            with self.after_resolve(swap_dir):
                self.gone(self.root + 'sub/page.txt')

    def test_an_intermediate_directory_swapped_for_a_symlink_after_the_checks_is_not_followed(self):
        """`O_NOFOLLOW` дивиться лише на ОСТАННЮ складову: проміжну теку підмінили посиланням — відкриття веде за межі,
        і ловить його тільки перевірка, де дескриптор лежить насправді."""
        self.put(os.path.join(self.dest, 'sub', 'page.txt'), 'REAL')
        out = self.put(os.path.join(self.folder, 'elsewhere', 'page.txt'), 'OUT')
        self.assertEqual(self.ok(self.root + 'sub/page.txt')[1], b'REAL')

        def swap():
            os.rename(os.path.join(self.dest, 'sub'), os.path.join(self.dest, 'sub.moved'))
            os.symlink(os.path.dirname(out), os.path.join(self.dest, 'sub'))
        with self.after_resolve(swap):
            self.gone(self.root + 'sub/page.txt')

    def test_a_fifo_swapped_in_after_the_checks_is_404_and_does_not_hang_a_thread(self):
        if not hasattr(os, 'mkfifo'):
            self.skipTest('нема mkfifo')
        victim = self.put(os.path.join(self.dest, 'it2', 'pipe.txt'), 'REAL')
        self.assertEqual(self.ok(self.root + 'it2/pipe.txt')[1], b'REAL')

        def swap():
            os.remove(victim)
            os.mkfifo(victim)
        t0 = time.monotonic()
        with self.after_resolve(swap):
            self.gone(self.root + 'it2/pipe.txt')
        self.assertLess(time.monotonic() - t0, 5, '`open` на FIFO завис')

    def test_rejected_fallback_opens_do_not_leak_descriptors(self):
        if not os.path.isdir('/dev/fd'):
            self.skipTest('нема /dev/fd')
        outside = self.put(os.path.join(self.folder, 'secret.txt'), 'SECRET')
        hard = os.path.join(self.dest, 'hard.txt')
        os.link(outside, hard)
        real_dest = serve._published_real_dir(self.dest)
        fds = lambda: len(os.listdir('/dev/fd'))
        before = fds()
        for _ in range(150):
            self.assertIsNone(serve.open_published_file(hard, real_dest))                    # nlink 2
            self.assertIsNone(serve.open_published_file(self.dest, real_dest))               # тека, не файл
            self.assertIsNone(serve.open_published_file(outside, real_dest))                 # поза текою задачі
            self.assertIsNone(serve.open_published_file(os.path.join(self.dest, 'нема'), real_dest))
        self.assertLess(fds() - before, 10, 'відхилені відкриття лишають дескриптори')
        opened = serve.open_published_file(os.path.join(self.dest, 'manifest.json'), real_dest)
        self.assertIsNotNone(opened)
        os.close(opened[0])                                                                  # власність перейшла до нас


class PublishedMode(unittest.TestCase):
    """Режим захисту `/published` — рядок старту сервера (де можливостей ОС нема, ТИХО діє слабший запасний спосіб:
    оператор мусить це бачити)."""

    def test_the_line_names_the_active_mode_in_both_modes(self):
        with mock.patch.object(serve, '_PUBLISHED_DIRFD', True):
            fd = serve.published_mode_line()
        with mock.patch.object(serve, '_PUBLISHED_DIRFD', False):
            path = serve.published_mode_line()
        self.assertEqual(len(fd.splitlines()), 1)
        self.assertEqual(len(path.splitlines()), 1)
        self.assertTrue(fd.startswith('/published:') and path.startswith('/published:'))
        self.assertIn('дескрипторами', fd)
        self.assertNotIn('ЗАПАСНИЙ', fd)
        self.assertIn('ЗАПАСНИЙ', path)
        self.assertIn('слабший', path)
        self.assertNotEqual(fd, path)

    def test_the_main_block_prints_the_line_and_a_started_server_really_does(self):
        src = open(serve.__file__, encoding='utf-8').read()
        main = src.split("if __name__ == '__main__':")[1]
        self.assertIn('print(published_mode_line())', main)
        tmp = tempfile.mkdtemp(prefix='dc-start-')
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {**{k: v for k, v in os.environ.items() if k not in ('DEAI_HOME', 'DC_TASKS_FILE', 'PORT')},
               'HOME': tmp, 'DC_TASKS_FILE': os.path.join(tmp, 'tasks.json'), 'PORT': '0', 'DC_NO_OVERVIEW': '1'}
        proc = subprocess.Popen([sys.executable, '-u', '-B', serve.__file__], env=env, cwd=tmp,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        lines = []
        reader = threading.Thread(target=lambda: [lines.append(ln.rstrip('\n')) for ln in proc.stdout], daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not any(ln.startswith('/published:') for ln in lines):
                time.sleep(0.1)
        finally:
            proc.kill()                                                    # свій процес, за дескриптором, не за шаблоном
            proc.wait(10)
        self.assertTrue(any(ln.startswith('Design Canvas v2:') for ln in lines), lines)
        mode = [ln for ln in lines if ln.startswith('/published:')]
        self.assertEqual(len(mode), 1, lines)
        self.assertEqual(mode[0], serve.published_mode_line())
        self.assertEqual(lines.index(mode[0]), lines.index(next(ln for ln in lines if ln.startswith('Design Canvas v2:'))) + 1)


class ResealModuleBuilds(TaskFixture):
    """`ops/reseal_gate.py` ніколи не перепечатує й не деплоїть збірку модуля: вона локальна, без `comment-layer/`,
    і її гейт (пароль модуля) — не пароль ЛІГА. Рішення — за АРТЕФАКТОМ (`publish/comment-layer/`), а не за
    `iterations.json`: збірка ЛІГА має коментатор завжди, збірка модуля (`comments=False`) — ніколи."""

    def _reseal(self, *args):
        spec = importlib.util.spec_from_file_location('reseal_gate', os.path.join(ROOT, 'ops', 'reseal_gate.py'))
        rg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rg)
        deployed = []
        rg.deploy = lambda pub, task=None: deployed.append(pub) or (True, '')
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['reseal_gate.py', *args]), contextlib.redirect_stdout(out):
            rg.main()
        return out.getvalue(), deployed

    def _wrapper(self):
        return os.path.join(self.tmp, 'publish', 'index.html')

    def test_a_league_build_is_resealed_and_deployed(self):
        """Контроль: без нього «модуль пропущено» могло б означати, що reseal не робить нічого."""
        task, tid, its = self._args()
        serve.build_preview(task, tid, its, comments=self._league(), build='legacy',
                            gate_pw=serve.preview_password(task))
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(deployed, [os.path.join(self.tmp, 'publish')])

    def test_a_module_build_is_skipped_before_anything_is_rewritten_or_deployed(self):
        for gate_pw in (None, 'pw-модуля'):
            for args in (('fixture',), ('--build', 'fixture'), ()):
                with self.subTest(gate_pw=gate_pw, args=args):
                    task, tid, its = self._args()
                    serve.build_preview(task, tid, its, comments=False, gate_pw=gate_pw, build='module')
                    before = _bytes(self._wrapper())
                    out, deployed = self._reseal(*args)
                    self.assertIn('збірка модуля публікації', out)
                    self.assertNotIn('передеплоєно', out)
                    self.assertNotIn('перезібрано', out)
                    self.assertEqual(deployed, [], 'збірку модуля відправлено на Vercel')
                    self.assertEqual(_bytes(self._wrapper()), before, 'обгортку модуля перезаписано')

    def _manifest_path(self):
        return os.path.join(self.tmp, 'publish', 'manifest.json')

    def _with_the_old_league_bundle(self):
        """Збірка ЛІГИ ДО 0.10.0 везла в `comment-layer/` ще й бандл `supabase-adapter.min.js`; збірки 4b-2 — ні (адаптер дає
        модуль). Запасне правило `reseal_gate` для збірок БЕЗ мітки розпізнає ЛІГУ саме за ним, тож старий склад
        відтворюємо копією ЗНІМКА старого бандла (`tests/fixtures/legacy-comments/`)."""
        shutil.copy2(OLD_LEAGUE_ADAPTER, os.path.join(self.tmp, 'publish', 'comment-layer', 'supabase-adapter.min.js'))

    def _drop_build_mark(self):
        """Збірка, зроблена ДО мітки: той самий маніфест без ключа `build`."""
        man = json.loads(_read(self._manifest_path()))
        self.assertIn('build', man, 'контроль: мітка була')
        del man['build']
        with open(self._manifest_path(), 'w', encoding='utf-8') as fh:
            json.dump(man, fh, ensure_ascii=False, indent=1)

    def test_a_league_build_with_module_comments_is_resealed_and_deployed(self):
        """ЛІГА + модуль коментарів: у `comment-layer/` лише шар і адаптер (бандлів ЛІГА нема), а збірка йде на Vercel, і
        ротація пароля мусить дійти до живого превʼю. Рішення — за міткою `build: legacy`, не за складом теки."""
        prov, _mods = _memo_provider(self)
        task, tid, its = self._args()
        comments = {'module': prov, 'config': {'endpoint': ENDPOINT}, 'channel': 'deai/s/fixture'}
        serve.build_preview(task, tid, its, comments=comments, build='legacy',
                            gate_pw=serve.preview_password(task))
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, 'publish', 'comment-layer'))),
                         ['adapter.js', 'comment-layer.min.js'], 'контроль: бандлів ЛІГА там нема')
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(deployed, [os.path.join(self.tmp, 'publish')])

    def test_a_league_build_without_comments_is_resealed_and_deployed(self):
        """ЛІГА, де коментарі не піднялись (`comments_unavailable`): `comment-layer/` нема зовсім, збірка — все одно ЛІГА."""
        task, tid, its = self._args()
        serve.build_preview(task, tid, its, comments=False, build='legacy',
                            gate_pw=serve.preview_password(task))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'publish', 'comment-layer')), 'контроль')
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(deployed, [os.path.join(self.tmp, 'publish')])

    def test_the_mark_wins_over_the_content_of_comment_layer_in_both_directions(self):
        task, tid, its = self._args()
        # `module` + повний набір СТАРИХ бандлів ЛІГА → усе одно модуль (не деплоїмо)
        serve.build_preview(task, tid, its, comments=self._league(), gate_pw='1100', build='module')
        self._with_the_old_league_bundle()
        out, deployed = self._reseal('fixture')
        self.assertIn('мітка збірки build: module', out)
        self.assertEqual(deployed, [])
        # `legacy` + порожня збірка без коментарів → ЛІГА
        serve.build_preview(task, tid, its, comments=False, gate_pw='1100', build='legacy')
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(len(deployed), 1)

    def test_an_old_league_build_without_the_mark_is_resealed_by_its_bundles(self):
        task, tid, its = self._args()
        serve.build_preview(task, tid, its, comments=self._league(), gate_pw='1100', build='legacy')
        self._with_the_old_league_bundle()
        self._drop_build_mark()
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(deployed, [os.path.join(self.tmp, 'publish')])

    def test_an_old_module_build_without_the_mark_is_skipped_and_the_message_says_why(self):
        task, tid, its = self._args()
        serve.build_preview(task, tid, its, comments=False, gate_pw=None, build='module')
        self._drop_build_mark()
        before = _bytes(self._wrapper())
        out, deployed = self._reseal('fixture')
        self.assertIn('мітки збірки нема', out)
        self.assertIn('збірку модуля', out)
        self.assertEqual(deployed, [])
        self.assertEqual(_bytes(self._wrapper()), before)

    def test_the_fallback_compares_bundle_names_exactly_not_case_insensitively(self):
        """Без мітки адаптер модуля з іменем `Supabase-Adapter.min.js` на macOS/Windows відкрився б як бандл ЛІГА через
        `isfile` — а це не він. Імена звіряються за переліком теки."""
        prov, _mods = _memo_provider(self)
        task, tid, its = self._args()
        comments = {'module': prov, 'config': {}, 'channel': 'deai/s/fixture'}
        serve.build_preview(task, tid, its, comments=comments, gate_pw=None, build='module')
        self._drop_build_mark()
        layer = os.path.join(self.tmp, 'publish', 'comment-layer')
        os.rename(os.path.join(layer, 'adapter.js'), os.path.join(layer, 'Supabase-Adapter.min.js'))
        out, deployed = self._reseal('fixture')
        self.assertIn('мітки збірки нема', out)
        self.assertEqual(deployed, [])

    def test_an_unreadable_or_unknown_mark_falls_back_to_the_bundles(self):
        task, tid, its = self._args()
        for garbage in ('{broken', '[]', '{"build": "other"}', '{"build": null}', '{"build": 7}'):
            with self.subTest(manifest=garbage):
                serve.build_preview(task, tid, its, comments=self._league(), gate_pw='1100', build='legacy')
                self._with_the_old_league_bundle()
                with open(self._manifest_path(), 'w', encoding='utf-8') as fh:
                    fh.write(garbage)
                out, deployed = self._reseal('fixture')
                self.assertEqual(len(deployed), 1, out)                 # бандли ЛІГА є → ЛІГА
                serve.build_preview(task, tid, its, comments=False, gate_pw=None, build='module')
                with open(self._manifest_path(), 'w', encoding='utf-8') as fh:
                    fh.write(garbage)
                out, deployed = self._reseal('fixture')
                self.assertEqual(deployed, [], out)                     # бандлів нема → модуль

    def test_a_module_build_with_module_comments_is_skipped_too(self):
        """2b-2: збірка модуля, що несе коментарі МОДУЛЯ, теж має `publish/comment-layer/` — тож саме наявності теки мало:
        ЛІГА-збірка — це та, де є ОБИДВА бандли ЛІГА (`serve.BUNDLES`); збірка з коментарями модуля їх не має."""
        prov, _mods = _memo_provider(self)
        for gate_pw in (None, 'pw-модуля'):
            for args in (('fixture',), ('--build', 'fixture'), ()):
                with self.subTest(gate_pw=gate_pw, args=args):
                    task, tid, its = self._args()
                    comments = {'module': prov, 'config': {'endpoint': ENDPOINT}, 'channel': 'deai/s/fixture'}
                    serve.build_preview(task, tid, its, comments=comments, gate_pw=gate_pw, build='module')
                    self.assertTrue(os.path.isdir(os.path.join(self.tmp, 'publish', 'comment-layer')), 'контроль')
                    before = _bytes(self._wrapper())
                    out, deployed = self._reseal(*args)
                    self.assertIn('збірка модуля публікації', out)
                    self.assertNotIn('передеплоєно', out)
                    self.assertNotIn('перезібрано', out)
                    self.assertEqual(deployed, [], 'збірку з коментарями модуля відправлено на Vercel ЛІГА')
                    self.assertEqual(_bytes(self._wrapper()), before, 'обгортку модуля перезаписано')

    def test_the_decision_is_made_from_the_artifact_not_from_iterations_json(self):
        """`publish_local` у `iterations.json` нічого не міняє: збірка ЛІГА з ним усе одно деплоїться, а збірка
        модуля БЕЗ нього (метадані втрачено) усе одно пропускається."""
        task, tid, its = self._args()
        meta = serve.load_meta(task)
        meta['publish_local'] = {'module': 'static-publish', 'path': '/x', 'published_at': '2026-10-15T10:00:00Z'}
        serve.save_meta(task, meta)
        serve.build_preview(task, tid, its, comments=self._league(), gate_pw='1100', build='legacy')
        out, deployed = self._reseal('fixture')
        self.assertEqual(len(deployed), 1, out)
        meta.pop('publish_local')
        serve.save_meta(task, meta)
        serve.build_preview(task, tid, its, comments=False, gate_pw=None, build='module')
        out, deployed = self._reseal('fixture')
        self.assertIn('збірка модуля', out)
        self.assertEqual(deployed, [])


# ============================================================================ 2b-1, Task 1: «публікація за адресою»

URL_MID = 'url-pub'
GOOD_URL = 'https://pv-12345678.vercel.app'
GOOD_STATE = {'project': 'pv-12345678', 'project_id': 'prj_1', 'deployment': 'dpl_1'}
UA_STAMP = re.compile(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}')
_GONE = object()          # «прибрати ключ» у `result(…)`
#: Модуль-фікстура `publish_target: url`: пише в `builtins._URLPUB`, що отримав, і віддає налаштований результат
#: (словник — як є, виклик — його значення); `gate` (Event) утримує ПЕРШИЙ виклик усередині модуля.
URL_SERVER = '''import builtins, copy, os
def check(ctx):
    return {"ok": True}
def publish(ctx, build_dir, task):
    cfg = builtins._URLPUB
    cfg["calls"].append({"build_dir": build_dir, "task": copy.deepcopy(task),
                         "built": os.path.isfile(os.path.join(build_dir, "index.html")),
                         "settings": dict(ctx["settings"]), "secret_keys": sorted(ctx["secrets"])})
    if cfg["gate"] is not None and len(cfg["calls"]) == 1:
        cfg["entered"].set()
        cfg["gate"].wait(20)
    res = cfg["result"]
    return res(ctx, build_dir, task) if callable(res) else copy.deepcopy(res)
'''


def result(**over):
    """Добрий результат `publish` модуля «за адресою» із підміною полів; `_GONE` — прибрати ключ."""
    out = {'url': GOOD_URL, 'state': dict(GOOD_STATE), 'verified': True, 'warnings': []}
    for k, v in over.items():
        if v is _GONE:
            out.pop(k, None)
        else:
            out[k] = v
    return out


class UrlTarget(DispatchWorld):
    """Модулі `publish_target: url` (2b-1, Task 1): диспетчер не знає про теку, пише `publish_url`/`publish_remote`,
    перевіряє відповідь модуля й нічого не пушить. Фікстурний модуль `url-pub` — у тимчасовій `builtin_dir` разом із
    копією справжнього `static-publish` (контроль: його гілка `folder` лишається такою, якою була)."""

    def setUp(self):
        super().setUp()
        self.cfg = {'calls': [], 'result': result(), 'gate': None, 'entered': threading.Event()}
        builtins._URLPUB = self.cfg
        self.addCleanup(lambda: hasattr(builtins, '_URLPUB') and delattr(builtins, '_URLPUB'))
        self.mods = os.path.join(self.tmp, 'modules')
        shutil.copytree(os.path.join(ROOT, 'app', 'modules', MID), os.path.join(self.mods, MID),
                        ignore=shutil.ignore_patterns('__pycache__'))
        for league_mid in ('vercel-publish', 'supabase-comments'):        # записи простору ЛІГА (`on`) — вбудовані модулі (4d-4b)
            shutil.copytree(os.path.join(ROOT, 'app', 'modules', league_mid), os.path.join(self.mods, league_mid),
                            ignore=shutil.ignore_patterns('__pycache__'))
        self.module(URL_MID, URL_SERVER, publish_target='url')
        patch = mock.patch.object(dm, 'builtin_dir', lambda: self.mods)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        self.enable_url(self.off)
        self.assertEqual(dm.catalog()[URL_MID].status, 'ok', dm.catalog()[URL_MID].error)

    # ---- фікстури ----

    def module(self, mid, server, roles=('publish',), **manifest):
        man = {'api': 1, 'id': mid, 'name': mid, 'version': '1.0.0', 'roles': list(roles),
               'settings': [{'key': 'password', 'type': 'secret', 'label': 'Password'},
                            {'key': 'token', 'type': 'secret', 'label': 'Token'}]}
        for k, v in manifest.items():
            if v is _GONE:
                man.pop(k, None)
            else:
                man[k] = v
        _write_json(os.path.join(self.mods, mid, 'module.json'), man)
        with open(os.path.join(self.mods, mid, 'server.py'), 'w', encoding='utf-8') as fh:
            fh.write(server)

    def enable_url(self, space):
        dm.write_module_state(space, MID, enabled=False)
        self.replace_publisher(space, URL_MID)

    def enable_folder(self, space):
        dm.write_module_state(space, URL_MID, enabled=False)
        dm.write_module_state(space, MID, enabled=True)

    def seed_meta(self, task_dir=None, **fields):
        path = os.path.join(task_dir or self.tx_dir, 'iterations.json')
        meta = json.loads(_read(path))
        meta.update(fields)
        _write_json(path, meta)

    def publish(self, payload=None, headers=None):
        return self.post('/api/publish', payload, headers)

    def bytes_meta(self):
        return _bytes(os.path.join(self.tx_dir, 'iterations.json'))

    def refused(self, res, what):
        """Відповідь `publish` модуля відхилено: 502 `module-error`, мета не чіпана, текст чесний (модуль уже
        відпрацював — публікація могла відбутись), а самого значення від модуля в тексті нема."""
        before = self.bytes_meta()
        self.cfg['result'] = res
        st, body = self.publish()
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), (what, body))
        self.assertIn('already run', body['error'], what)
        self.assertIn('may already have happened', body['error'], what)
        self.assertEqual(self.bytes_meta(), before, f'мету записано попри відхилену відповідь: {what}')
        return body

    # ---- маніфест ----

    def test_publish_target_defaults_to_folder_and_accepts_folder_and_url(self):
        self.module('t-url', 'def check(ctx):\n    return {"ok": True}\ndef publish(c, b, t):\n    return {}\n',
                    publish_target='url')
        self.module('t-folder', 'def check(ctx):\n    return {"ok": True}\ndef publish(c, b, t):\n    return {}\n',
                    publish_target='folder')
        self.module('t-none', 'def check(ctx):\n    return {"ok": True}\ndef publish(c, b, t):\n    return {}\n',
                    publish_target=_GONE)
        cat = dm.catalog()
        self.assertEqual([(cat[m].status, cat[m].publish_target) for m in ('t-url', 't-folder', 't-none')],
                         [('ok', 'url'), ('ok', 'folder'), ('ok', 'folder')])
        self.assertEqual(cat[MID].publish_target, 'folder')               # справжній `static-publish` не міняв маніфест
        self.assertEqual(cat[URL_MID].publish_target, 'url')

    def test_any_other_publish_target_is_a_bad_manifest(self):
        fn = 'def check(ctx):\n    return {"ok": True}\ndef publish(c, b, t):\n    return {}\n'
        bad = ['ftp', '', 'URL', 'Folder', ' url', None, 1, True, ['url'], {'url': 1}, 0.5]
        for i, value in enumerate(bad):
            self.module(f'bad-{i}', fn, publish_target=value)
        # лише модулі без ролі `publish` теж валідуються: поле не мусить мовчки лишатись сміттям
        self.module('bad-tokens', 'def check(ctx):\n    return {"ok": True}\ndef tokens(c):\n    return {}\n',
                    roles=('tokens',), publish_target='nope')
        cat = dm.catalog()
        for i, value in enumerate(bad):
            with self.subTest(value=value):
                m = cat[f'bad-{i}']
                self.assertEqual((m.status, m.error_code), ('error', 'bad-manifest'), m.error)
                self.assertIn('publish_target', m.error)
                self.assertIsNone(m.fn('publish'))
        self.assertEqual((cat['bad-tokens'].status, cat['bad-tokens'].error_code), ('error', 'bad-manifest'))

    def test_the_new_status_codes_pass_through_the_core(self):
        self.assertEqual((dm.STATUS['vercel-auth'], dm.STATUS['vercel-busy']), (409, 409))
        self.assertEqual((dm.ModuleError('vercel-auth').status, dm.ModuleError('vercel-busy').status), (409, 409))

    # ---- запис мети й відповідь ----

    def test_publish_writes_the_four_fields_and_leaves_publish_local_alone(self):
        local = {'module': 'static-publish', 'path': '/old/tx', 'published_at': '2026-10-01T10:00:00Z'}
        self.seed_meta(publish_local=local)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'url', 'verified', 'iterations', 'frames'])
        self.assertEqual((body['ok'], body['url'], body['verified'], body['iterations'], body['frames']),
                         (True, GOOD_URL, True, 2, 0))
        self.assertNotIn('local', body)
        meta = self.meta()
        self.assertEqual(meta['publish_url'], GOOD_URL)
        self.assertRegex(meta['published_at'], r'^' + UA_STAMP.pattern + r'$')
        self.assertEqual(meta['published_at'], time.strftime('%d.%m.%Y %H:%M'), 'формат/час ЛІГА')
        self.assertIs(meta['publish_verified'], True)
        remote = meta['publish_remote']
        self.assertEqual(set(remote), {'module', 'state', 'published_at', 'url', 'gated'})
        self.assertEqual((remote['module'], remote['state'], remote['url'], remote['gated']),
                         (URL_MID, GOOD_STATE, GOOD_URL, False))
        self.assertRegex(remote['published_at'], r'^' + ISO_UTC.pattern + r'$')
        self.assertEqual(meta['publish_local'], local, '`publish_local` не чіпаємо')
        self.assertEqual([i['published'] for i in meta['iterations']], [True, True])
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')), 'тека публікації зʼявилась')
        self.assert_quiet()

    def test_verified_false_and_warnings_are_stored_and_returned(self):
        self.cfg['result'] = result(verified=False, warnings=['Deployment Protection увімкнено', 'другий рядок'])
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'url', 'verified', 'iterations', 'frames', 'warnings'])
        self.assertEqual((body['verified'], body['warnings']),
                         (False, ['Deployment Protection увімкнено', 'другий рядок']))
        self.assertIs(self.meta()['publish_verified'], False)

    def test_empty_or_absent_warnings_are_not_in_the_response(self):
        for res in (result(warnings=[]), result(warnings=_GONE)):
            self.cfg['result'] = res
            st, body = self.publish()
            self.assertEqual(st, 200, body)
            self.assertNotIn('warnings', body)

    def test_response_key_order_with_frames_warnings_and_code_stale(self):
        shots = os.path.join(self.tx_dir, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        self.cfg['result'] = result(warnings=['w'])
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'url', 'verified', 'iterations', 'frames', 'warnings',
                                      'frames_warnings', 'code_stale'])
        self.assertTrue(any('it1' in w for w in body['frames_warnings']))
        self.assertEqual(body['code_stale'], 'код новіший за процес')

    def test_the_module_gets_the_build_dir_and_exactly_the_task_arg(self):
        self.assertEqual(self.publish()[0], 200)
        call, = self.cfg['calls']
        self.assertEqual(call['build_dir'], os.path.join(self.tx_dir, 'publish'))
        self.assertTrue(call['built'], 'модуль викликано до того, як збірка лягла')
        # `gated` (4b-1): без пароля превʼю — `False` (з паролем `True`: `LegacyPublishViaModule.test_9`)
        self.assertEqual(call['task'], {'id': 'tx', 'title': 'Задача tx', 'dir': self.tx_dir, 'state': {}, 'gated': False})
        self.assertEqual(call['settings'], {})                 # жодного `folder`: теку модуль «за адресою» не знає
        self.assertEqual(call['secret_keys'], [])

    def test_the_url_branch_has_no_folder_no_bad_task_id_and_no_destination_lock(self):
        """Для `url` id задачі в адресу не йде (імʼя проєкту непрозоре), тека не потрібна, `bad-folder` неможливий."""
        for i, tid in enumerate(('задача', 'x' * 129, 'NUL')):
            with self.subTest(tid=tid[:10]):
                rec = self._task_space(f'u{i}', tid)
                self.enable_url(rec)
                st, body = self.publish()
                self.assertEqual(st, 200, body)
                self.assertEqual(body['url'], GOOD_URL)
                self.assertEqual(self.cfg['calls'][-1]['task']['id'], tid)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    def _task_space(self, sid, tid):
        rec = self._register(self._space(sid, os.path.join(self.home, 'deai-work', sid), False, tid))
        path = os.path.join(self.deai, 'spaces.json')
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
        reg['current'] = sid
        atomic_write_json(path, reg)
        return rec

    def test_no_iterations_marked_is_the_same_400_before_any_build_or_call(self):
        meta = self.meta()
        for it in meta['iterations']:
            it['published'] = False
        _write_json(os.path.join(self.tx_dir, 'iterations.json'), meta)
        st, body = self.publish()
        self.assertEqual(st, 400)
        self.assertIn('no iterations marked for publish - toggle the green dot first', body)
        self.assert_nothing_built()
        self.assertEqual(self.cfg['calls'], [])

    # ---- `state` туди-назад ----

    def test_state_round_trip_the_second_publish_gets_what_the_first_returned(self):
        self.assertEqual(self.publish()[0], 200)
        self.cfg['result'] = result(state={'project': 'pv-12345678', 'project_id': 'prj_1', 'deployment': 'dpl_2',
                                           'n': 2, 'ok': True, 'ratio': 0.5, 'none': None})
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.cfg['calls'][0]['task']['state'], {})
        self.assertEqual(self.cfg['calls'][1]['task']['state'], GOOD_STATE)
        self.cfg['result'] = result()
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.cfg['calls'][2]['task']['state'],
                         {'project': 'pv-12345678', 'project_id': 'prj_1', 'deployment': 'dpl_2',
                          'n': 2, 'ok': True, 'ratio': 0.5, 'none': None})

    def test_a_state_stored_by_another_module_is_not_passed(self):
        self.seed_meta(publish_remote={'module': 'vercel-publish', 'state': {'project': 'чужий'},
                                       'published_at': '2026-10-01T10:00:00Z'})
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.cfg['calls'][0]['task']['state'], {})
        # і перезаписаний: тепер там цей модуль
        self.assertEqual(self.meta()['publish_remote']['module'], URL_MID)

    def test_a_malformed_stored_publish_remote_is_an_empty_state_not_a_crash(self):
        for bad in ('рядок', 5, None, [], {'module': URL_MID}, {'module': URL_MID, 'state': ['x']},
                    {'module': URL_MID, 'state': 'x'}, {'state': {'a': 1}}):
            with self.subTest(bad=bad):
                self.cfg['calls'].clear()
                self.seed_meta(publish_remote=bad)
                st, body = self.publish()
                self.assertEqual(st, 200, body)
                self.assertEqual(self.cfg['calls'][0]['task']['state'], {})

    def test_the_state_is_read_fresh_after_the_build_not_at_the_start(self):
        """Збірка триває: стан, записаний за цей час, мусить дійти до модуля (інакше новіша публікація
        перезаписалась би застарілим станом)."""
        real = serve.build_preview

        def build_then_store(*a, **kw):
            out = real(*a, **kw)
            self.seed_meta(publish_remote={'module': URL_MID, 'state': {'project': 'нове'},
                                           'published_at': '2026-10-01T10:00:00Z'})
            return out
        with mock.patch.object(serve, 'build_preview', build_then_store):
            self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.cfg['calls'][0]['task']['state'], {'project': 'нове'})

    def test_meta_is_reread_before_writing_so_a_toggle_made_during_the_publish_survives(self):
        def toggles(ctx, build, task):
            path = os.path.join(task['dir'], 'iterations.json')
            meta = json.loads(_read(path))
            meta['iterations'][1]['published'] = False
            meta['custom'] = 'від дизайнера'
            _write_json(path, meta)
            return result()
        self.cfg['result'] = toggles
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        meta = self.meta()
        self.assertEqual({i['id']: i['published'] for i in meta['iterations']}, {'it1': True, 'it2': False})
        self.assertEqual(meta['custom'], 'від дизайнера')
        self.assertEqual(meta['publish_url'], GOOD_URL)

    # ---- перевірка відповіді модуля ----

    def test_a_bad_url_is_refused_and_the_meta_is_untouched(self):
        bad = ['http://pv-1.vercel.app', 'ftp://pv-1.vercel.app', '//pv-1.vercel.app', 'pv-1.vercel.app', '',
               'https://', 'https:///path', 'https://:443/', 'https://u:p@pv-1.vercel.app', 'https://u@pv-1.vercel.app',
               'https://@pv-1.vercel.app', 'https://pv-1.vercel.app/#frag', 'https://pv-1.vercel.app/#',
               'https://pv-1.vercel.app/ x', 'https://pv-1.vercel.app/\n', 'https://pv-1.vercel.app\\evil',
               'https://[::1', 'https://pv-1.vercel.app/' + 'a' * 2100,
               None, 5, True, ['https://pv-1.vercel.app'], b'https://pv-1.vercel.app', {'url': GOOD_URL}, _GONE]
        for url in bad:
            with self.subTest(url=url if not isinstance(url, str) else url[:60]):
                self.refused(result(url=url), 'url')

    def test_good_urls_are_accepted(self):
        for url in ('https://pv-1.vercel.app', 'https://pv-1.vercel.app/', 'https://pv-1.vercel.app:8443/a/b?x=1&y=2',
                    'https://xn--e1afmkfd.example/', 'https://a.b'):
            with self.subTest(url=url):
                self.cfg['result'] = result(url=url)
                st, body = self.publish()
                self.assertEqual((st, body.get('url')), (200, url), body)
                self.assertEqual(self.meta()['publish_url'], url)

    def test_a_state_over_4096_is_refused_and_exactly_4096_is_accepted(self):
        pad = 4096 - len(json.dumps({'k': ''}))
        self.cfg['result'] = result(state={'k': 'x' * pad})
        self.assertEqual(len(json.dumps(self.cfg['result']['state'])), 4096)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(self.meta()['publish_remote']['state'], {'k': 'x' * pad})
        self.refused(result(state={'k': 'x' * (pad + 1)}), 'state 4097')
        self.refused(result(state={f'k{i}': 'x' * 100 for i in range(60)}), 'state many keys')

    def test_a_state_that_is_not_a_flat_object_of_scalars_is_refused(self):
        nan, inf = float('nan'), float('inf')
        bad = {'вкладений обʼєкт': {'a': {'b': 1}}, 'вкладений список': {'a': [1, 2]}, 'кортеж': {'a': (1,)},
               'байти': {'a': b'x'}, 'множина': {'a': {1}}, 'ключ не рядок': {1: 'a'}, 'NaN': {'a': nan},
               'inf': {'a': inf}, 'сурогат у значенні': {'a': '\ud800'}, 'сурогат у ключі': {'\ud800': 'a'},
               'список': ['project'], 'None': None, 'рядок': 'project', 'число': 5, 'відсутній': _GONE}
        for what, state in bad.items():
            with self.subTest(what):
                self.refused(result(state=state), what)

    def test_scalar_values_of_every_allowed_type_are_stored_as_they_are(self):
        state = {'s': 'рядок', 'i': 3, 'f': 1.5, 'b': False, 'n': None, 'empty': ''}
        self.cfg['result'] = result(state=state)
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.meta()['publish_remote']['state'], state)
        self.cfg['result'] = result(state={})
        self.assertEqual(self.publish()[0], 200)                    # порожній стан — теж стан
        self.assertEqual(self.meta()['publish_remote']['state'], {})

    def test_verified_must_be_a_real_bool(self):
        for v in (1, 0, 'true', 'yes', None, [], _GONE):
            with self.subTest(verified=v):
                self.refused(result(verified=v), 'verified')

    def test_warnings_must_be_a_short_list_of_short_strings(self):
        bad = {'рядок': 'увага', 'None': None, 'не рядок в списку': ['a', 5], 'шість': ['w'] * 6,
               'задовгий': ['x' * 301], 'словник': {'a': 'b'}, 'кортеж': ('a',), 'сурогат': ['\ud800']}
        for what, warnings in bad.items():
            with self.subTest(what):
                self.refused(result(warnings=warnings), what)
        self.cfg['result'] = result(warnings=['x' * 300] * 5)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(body['warnings'], ['x' * 300] * 5)

    def test_a_result_that_is_not_an_object_is_refused(self):
        for res in (None, 'https://pv-1.vercel.app', [GOOD_URL], 5, True):
            with self.subTest(res=res):
                self.refused(res, 'result')

    def test_the_refusal_text_does_not_echo_the_modules_values(self):
        dm.write_secrets('off', URL_MID, {'password': 'S3cr3t-pw'})
        body = self.refused(result(url='http://leak-S3cr3t-pw.example/NOT-HTTPS'), 'url')
        text = json.dumps(body, ensure_ascii=False)
        self.assertNotIn('S3cr3t-pw', text)
        self.assertNotIn('leak-', text)
        self.assertLessEqual(len(body['error']), 300)

    # ---- помилки модуля ----

    def test_a_vercel_auth_or_busy_error_is_409_with_its_code_and_without_the_secret(self):
        dm.write_secrets('off', URL_MID, {'password': 'S3cr3t-pw'})
        before = self.bytes_meta()
        for code in ('vercel-auth', 'vercel-busy'):
            with self.subTest(code):
                def refuses(ctx, build, task, code=code):
                    raise ctx['ModuleError'](code, message='Vercel відмовив S3cr3t-pw')
                self.cfg['result'] = refuses
                st, body = self.publish()
                self.assertEqual((st, body['ok'], body['code']), (409, False, code), body)
                self.assertIn('Vercel відмовив', body['error'])
                self.assertNotIn('S3cr3t-pw', json.dumps(body, ensure_ascii=False))
                self.assertEqual(self.bytes_meta(), before)
        self.cfg['result'] = result()
        self.assertEqual(self.publish()[0], 200, 'замок не відпущено після відмови модуля')

    def test_an_unknown_code_or_a_crash_is_502_module_error(self):
        def weird(ctx, build, task):
            raise ctx['ModuleError']('weird-code', message='x')

        def crash(ctx, build, task):
            raise RuntimeError('впало')
        for fn in (weird, crash):
            self.cfg['result'] = fn
            st, body = self.publish()
            self.assertEqual((st, body['code']), (502, 'module-error'), body)
        meta = self.meta()
        self.assertIsNone(meta['publish_url'])
        for key in ('published_at', 'publish_verified', 'publish_remote'):
            self.assertNotIn(key, meta)

    # ---- замок і виклик ----

    def _hold_first(self):
        gate = threading.Event()
        self.cfg['gate'] = gate
        self.addCleanup(gate.set)
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__('first', self.publish()), daemon=True)
        t.start()
        self.assertTrue(self.cfg['entered'].wait(15), 'перша публікація не дійшла до модуля')
        return gate, t, box

    def _answers_at_once(self, fn):
        """Відповідь `fn()` у потоці: вона мусить прийти, поки перша публікація ще стоїть, — а не чекати."""
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__('r', fn()), daemon=True)
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), 'відповідь ЧЕКАЛА замка (мусить бути одразу: 409 publish-busy)')
        return box['r']

    def test_a_second_publish_or_build_of_the_task_is_409_busy_while_the_module_runs(self):
        gate, t, box = self._hold_first()
        for payload in ({}, {'build_only': True}):
            st, body = self._answers_at_once(lambda: self.publish(payload))
            self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'publish-busy'), body)
            self.assertTrue(body['error'])
        self.assertEqual(len(self.cfg['calls']), 1, 'друга публікація тієї ж задачі зайшла в модуль')
        gate.set()
        t.join(30)
        self.assertEqual(box['first'][0], 200, box['first'])
        self.assertEqual(self.publish()[0], 200, 'замок не відпущено після публікації')

    def test_the_lock_is_the_build_dir_of_the_task_and_nothing_wider(self):
        """Інша задача (інший простір) публікується одночасно: замок не глобальний."""
        self.enable_url(self.on)
        gate, t, box = self._hold_first()
        st, body = self._answers_at_once(lambda: self.publish({}, {'X-Canvas-Task': 'ty'}))
        self.assertEqual((st, body.get('url')), (200, GOOD_URL), body)
        self.assertEqual(self.cfg['calls'][1]['task']['id'], 'ty')
        gate.set()
        t.join(30)
        self.assertEqual(box['first'][0], 200, box['first'])

    def test_the_lock_is_shared_with_the_folder_branch_of_the_same_task(self):
        """Збірка `<задача>/publish/` одна й та сама для обох гілок: поки url-публікація стоїть у модулі, людина
        перемкнула простір на `folder`-модуль — його публікація тієї ж задачі теж відповідає `publish-busy` одразу
        (інакше стерла б і писала б `<задача>/publish/` під першою), а коли перша вийшла, замок вільний."""
        gate, t, box = self._hold_first()
        self.enable_folder(self.off)
        for payload in ({}, {'build_only': True}):
            st, body = self._answers_at_once(lambda: self.publish(payload))
            self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'publish-busy'), body)
        self.assertFalse(os.path.exists(self.dest), 'folder-публікація пройшла повз замок теки збірки')
        gate.set()
        t.join(30)
        self.assertEqual(box['first'][0], 200, box['first'])
        st, body = self.publish()
        self.assertEqual((st, list(body)[:2]), (200, ['ok', 'local']), body)
        self.assertEqual(len(self.cfg['calls']), 1, 'url-модуль кликано для folder-публікації')

    def test_the_module_is_called_without_a_timeout(self):
        """`timeout=` перетворив би виклик на робочий потік, що не вклався б і працював далі БЕЗ замка."""
        real, seen = dm.call, []

        def spy(*a, **kw):
            seen.append((a[1], kw))
            return real(*a, **kw)
        with mock.patch.object(dm, 'call', spy):
            self.assertEqual(self.publish()[0], 200)
        self.assertEqual(seen, [('publish', {})])

    def test_the_lock_is_released_after_a_refused_result(self):
        self.refused(result(url='http://x.example'), 'url')
        self.cfg['result'] = result()
        self.assertEqual(self.publish()[0], 200)

    # ---- `build_only` і пароль ----

    def test_build_only_builds_and_neither_calls_the_module_nor_writes_the_meta(self):
        before = self.bytes_meta()
        st, body = self.publish({'build_only': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body)[:4], ['ok', 'dir', 'iterations', 'frames'])
        self.assertEqual(body['dir'], os.path.join(self.tx_dir, 'publish'))
        self.assertTrue(os.path.isfile(os.path.join(body['dir'], 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(body['dir'], 'comment-layer')))
        self.assertEqual(self.cfg['calls'], [])
        self.assertEqual(self.bytes_meta(), before)
        for key in ('url', 'local', 'verified'):
            self.assertNotIn(key, body)
        self.assert_quiet()

    def test_a_password_secret_gates_the_build_and_never_reaches_the_response_or_the_meta(self):
        dm.write_secrets('off', URL_MID, {'password': 'pw-Ключ-1'})
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        pub = os.path.join(self.tx_dir, 'publish')
        wrapper = _read(os.path.join(pub, 'index.html'))
        self.assertIn('id="authgate"', wrapper)
        self.assertIn(f'window.__extPw={json.dumps("pw-Ключ-1", ensure_ascii=False)};', wrapper)
        for rel in SOURCE_PAGES:
            self.assertIn('id="authgate"', _read(os.path.join(pub, rel)), rel)
        self.assertNotIn('pw-Ключ-1', json.dumps(body, ensure_ascii=False))
        self.assertNotIn('pw-Ключ-1', _read(os.path.join(self.tx_dir, 'iterations.json')))
        self.assertEqual(self.cfg['calls'][0]['secret_keys'], ['password'])

    def test_no_secret_or_an_empty_one_is_no_gate(self):
        for pw in (None, ''):
            with self.subTest(password=pw):
                if pw is not None:
                    dm.write_secrets('off', URL_MID, {'password': pw})
                self.assertEqual(self.publish()[0], 200)
                pub = os.path.join(self.tx_dir, 'publish')
                self.assertIn('<script>window.__gateOpen=true;</script>', _read(os.path.join(pub, 'index.html')))
                for rel in SOURCE_PAGES:
                    html = _read(os.path.join(pub, rel))
                    self.assertNotIn('authgate', html, rel)
                    self.assertEqual(_title(html), _title(_read(os.path.join(self.tx_dir, 'iterations', rel))), rel)

    # ---- `/api/task` ----

    def share(self, task):
        return {k: task[k] for k in ('publish_gate', 'publish_share_url') if k in task}

    def test_api_task_publish_gate_and_share_url_with_a_password(self):
        pw = 'p@ss w/ö#?&=%+'
        dm.write_secrets('off', URL_MID, {'password': pw})
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(self.share(task), {'publish_gate': True})         # адреси ще нема — посилання нема
        self.assertEqual(task['preview_gate'], MODULE_GATE)
        self.assertNotIn('publish_remote', task)
        self.assertEqual(self.publish()[0], 200)
        st, task = self.get('/api/task')
        self.assertEqual(task['publish_url'], GOOD_URL)
        stored = self.meta()['publish_remote']
        self.assertEqual(stored['gated'], True)
        self.assertRegex(stored['gate_hash'], r'^[0-9a-f]{16}$')
        self.assertEqual(task['publish_remote'], {k: v for k, v in stored.items() if k != 'gate_hash'})
        self.assertEqual(task['publish_gate'], True)
        want = GOOD_URL + '#k=' + urllib.parse.quote(pw, safe='')
        self.assertEqual(task['publish_share_url'], want)
        self.assertEqual(task['publish_share_url'].count('#'), 1)
        key = task['publish_share_url'].split('#k=', 1)[1]
        for raw in (' ', '/', '#', '?', '&', '=', '+', 'ö', '@'):
            self.assertNotIn(raw, key)
        self.assertEqual(urllib.parse.unquote(key), pw)
        self.assertIn('%20', want)
        self.assertIn('%C3%B6', want)
        self.assertEqual(task['preview_gate'], MODULE_GATE)

    def test_api_task_without_a_password_shares_the_plain_url_and_the_gate_is_false(self):
        for pw in (None, ''):
            with self.subTest(password=pw):
                if pw is not None:
                    dm.write_secrets('off', URL_MID, {'password': pw})
                self.assertEqual(self.publish()[0], 200)
                st, task = self.get('/api/task')
                self.assertEqual(self.share(task), {'publish_gate': False, 'publish_share_url': GOOD_URL})
                self.assertNotIn('#', task['publish_share_url'])

    def test_api_task_has_no_share_fields_for_the_folder_module(self):
        """Навіть коли в мету лишилась адреса від ЛІГА чи від минулого модуля: `folder`-модуль посилання не дає."""
        self.enable_folder(self.off)
        self.seed_meta(publish_url='https://pv-old.vercel.app', published_at='01.01.2026 10:00')
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(self.share(task), {})
        self.assertEqual(task['publish_url'], 'https://pv-old.vercel.app')
        self.assertEqual(self.publish()[0], 200)
        st, task = self.get('/api/task')
        self.assertEqual(self.share(task), {})
        self.assertIn('publish_local', task)

    def test_api_task_has_no_share_fields_for_the_league_path(self):
        """Шлях ЛІГА (простір з інтеграціями, явний запис `vercel-publish`), навіть коли модуль «за адресою» стоїть у каталозі."""
        self.assertEqual(dm.provider('publish', self.on).id, 'vercel-publish')
        self.seed_meta(self.ty_dir, publish_url='https://pv-12345678.vercel.app', published_at='01.01.2026 10:00')
        st, task = self.get('/api/task', {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, task)
        self.assertEqual(self.share(task), {})
        self.assertNotIn('publish_remote', task)

    def test_api_task_in_a_league_space_with_an_enabled_url_module_has_the_fields(self):
        """Явно ввімкнений модуль має пріоритет і в просторі ЛІГА (як у 0.2.0)."""
        self.enable_url(self.on)
        dm.write_secrets('on', URL_MID, {'password': 'pw1'})
        st, task = self.get('/api/task', {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, self.share(task)), (200, {'publish_gate': True}), task)
        self.assertEqual(self.publish({}, {'X-Canvas-Task': 'ty'})[0], 200)
        st, task = self.get('/api/task', {'X-Canvas-Task': 'ty'})
        self.assertEqual(self.share(task), {'publish_gate': True, 'publish_share_url': GOOD_URL + '#k=pw1'})

    def test_api_task_does_not_fail_and_drops_the_fields_on_unreadable_secrets_or_space_json(self):
        dm.write_secrets('off', URL_MID, {'password': 'pw1'})
        self.assertEqual(self.publish()[0], 200)
        with open(os.path.join(self.deai, 'secrets.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(self.share(task), {})
        self.assertEqual(task['publish_url'], GOOD_URL)                    # решта задачі на місці
        self.assertEqual(task['id'], 'tx')
        os.remove(os.path.join(self.deai, 'secrets.json'))
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(self.share(task), {})

    def test_api_task_share_url_uses_the_module_password_not_the_league_one(self):
        dm.write_secrets('off', URL_MID, {'password': 'модульний'})
        self.assertEqual(self.publish()[0], 200)
        st, task = self.get('/api/task')
        self.assertEqual(task['publish_share_url'], GOOD_URL + '#k=' + urllib.parse.quote('модульний', safe=''))
        self.assertNotIn(task['preview_password'], task['publish_share_url'].split('#k=')[1])

    # ---- секрети в результаті модуля ----

    SIMPLE = 'vcp_S3cr3tTokenValue123'
    SPECIAL = 'tok-Ü/ab c&"d=9'                    # URL-кодована й JSON-екранована форми відрізняються від сирої

    def set_token(self, value):
        dm.write_secrets('off', URL_MID, {'token': value})

    def set_password(self, value):
        dm.write_secrets('off', URL_MID, {'password': value})                 # None — прибрати

    def assert_secret_nowhere(self, secret, *responses):
        """Секрет не в жодній відповіді, не в `iterations.json` і не в `/api/task` — у жодній з його форм."""
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        texts = [self.bytes_meta().decode('utf-8')]
        for obj in (task, *responses):
            texts += [json.dumps(obj, ensure_ascii=True), json.dumps(obj, ensure_ascii=False)]
        forms = {secret, urllib.parse.quote(secret, safe=''), json.dumps(secret)[1:-1],
                 json.dumps(secret, ensure_ascii=False)[1:-1]}
        for form in forms:
            for text in texts:
                self.assertNotIn(form, text, f'секрет {form!r} лишився у відповіді чи в мета')

    def test_a_secret_in_the_url_or_the_state_is_refused_and_leaks_nowhere(self):
        simple, special = self.SIMPLE, self.SPECIAL
        cases = {
            'адреса: ?t=<токен>': (simple, result(url=GOOD_URL + '/?t=' + simple)),
            'адреса: шлях': (simple, result(url=GOOD_URL + '/' + simple)),
            'адреса: URL-кодований': (special, result(url=GOOD_URL + '/?t=' + urllib.parse.quote(special, safe=''))),
            'state: Bearer <токен>': (simple, result(state={'dbg': 'Bearer ' + simple})),
            'state: JSON-екранований': (special, result(state={'dbg': 'Bearer ' + special})),
            'state: ключ': (simple, result(state={simple: 1})),
        }
        for what, (secret, res) in cases.items():
            with self.subTest(what):
                self.set_token(secret)
                body = self.refused(res, what)
                self.assertIn('contains a secret', body['error'])
                self.assert_secret_nowhere(secret, body)

    def test_a_secret_in_the_warnings_is_cut_out_and_the_publish_goes_on(self):
        for secret in (self.SIMPLE, self.SPECIAL):
            with self.subTest(secret):
                self.set_token(secret)
                self.cfg['result'] = result(warnings=['oops ' + secret, urllib.parse.quote(secret, safe='') + ' end'])
                st, body = self.publish()
                self.assertEqual(st, 200, body)
                self.assertEqual(body['warnings'], ['oops ***', '*** end'])
                self.assert_secret_nowhere(secret, body)

    def test_the_password_is_allowed_in_url_and_state_but_is_cut_out_of_warnings(self):
        """Пароль превʼю — не секрет від глядача (вшитий у сторінки): ядро саме дописує його в посилання, тож у
        `url`/`state` він відмову не викликає. Попередження ж він не потрібен — там його вирізано, як і токен."""
        pw = 'pw-visible-1234'
        self.set_password(pw)
        self.cfg['result'] = result(url=GOOD_URL + '/?k=' + pw, state={'hint': pw}, warnings=['щось ' + pw])
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(self.meta()['publish_remote']['state'], {'hint': pw})
        self.assertEqual(body['warnings'], ['щось ***'])

    def test_short_secrets_are_not_searched_for_but_eight_characters_are(self):
        self.set_token('abc1234')                                       # 7
        self.cfg['result'] = result(url=GOOD_URL + '/?q=abc1234', warnings=['abc1234 тут'])
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(body['warnings'], ['abc1234 тут'])
        self.set_token('abc12345')                                      # 8
        self.refused(result(url=GOOD_URL + '/?q=abc12345'), 'вісім знаків')

    def test_a_clean_publish_never_puts_the_token_anywhere(self):
        self.set_token(self.SIMPLE)
        self.set_password('pw-Ключ-1234')
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(self.cfg['calls'][0]['secret_keys'], ['password', 'token'])
        self.assert_secret_nowhere(self.SIMPLE, body)

    # ---- гейт за опублікованою збіркою й посилання лише до своєї адреси ----

    def api_share(self):
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        return {k: task[k] for k in ('publish_gate', 'publish_gate_stale', 'publish_share_url') if k in task}

    def test_publish_remote_records_the_url_and_the_gate_of_the_published_build(self):
        self.assertEqual(self.publish()[0], 200)
        remote = self.meta()['publish_remote']
        self.assertEqual((remote['url'], remote['gated']), (GOOD_URL, False))
        self.assertNotIn('gate_hash', remote)
        self.set_password('pw-Ключ-1')
        self.assertEqual(self.publish()[0], 200)
        remote = self.meta()['publish_remote']
        self.assertEqual((remote['url'], remote['gated']), (GOOD_URL, True))
        self.assertEqual(remote['gate_hash'], hashlib.sha256('pw-Ключ-1'.encode('utf-8')).hexdigest()[:16])
        self.assertNotIn('pw-Ключ-1', self.bytes_meta().decode('utf-8'), 'пароль у метаданих')
        st, task = self.get('/api/task')
        self.assertNotIn('gate_hash', task['publish_remote'])
        self.assertNotIn(remote['gate_hash'], json.dumps(task))

    def test_publish_gate_follows_the_published_build_and_flags_a_changed_password(self):
        self.assertEqual(self.api_share(), {'publish_gate': False})              # ще не публікували: пароль ЗАРАЗ
        self.set_password('pw-before')
        self.assertEqual(self.api_share(), {'publish_gate': True})
        self.set_password(None)
        # 1. опубліковано БЕЗ пароля — превʼю публічне
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.api_share(), {'publish_gate': False, 'publish_share_url': GOOD_URL})
        # 2. пароль задали ПІСЛЯ: застереження «публічне» лишається, превʼю пора перепублікувати, ключа в посиланні нема
        self.set_password('pw-new-1')
        self.assertEqual(self.api_share(), {'publish_gate': False, 'publish_gate_stale': True,
                                            'publish_share_url': GOOD_URL})
        # 3. перепублікували — тепер з гейтом, посилання відчиняється з ключем
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.api_share(), {'publish_gate': True, 'publish_share_url': GOOD_URL + '#k=pw-new-1'})
        # 4. пароль змінили — посилання з НОВИМ ключем не відчинило б збірку зі старим: ключа не даємо
        self.set_password('pw-new-2')
        self.assertEqual(self.api_share(), {'publish_gate': True, 'publish_gate_stale': True,
                                            'publish_share_url': GOOD_URL})
        # 5. пароль зняли — збірка й далі з гейтом
        self.set_password(None)
        self.assertEqual(self.api_share(), {'publish_gate': True, 'publish_gate_stale': True,
                                            'publish_share_url': GOOD_URL})
        # 6. повернули ТОЙ САМИЙ пароль — збірка знову відповідає налаштуванню
        self.set_password('pw-new-1')
        self.assertEqual(self.api_share(), {'publish_gate': True, 'publish_share_url': GOOD_URL + '#k=pw-new-1'})
        # 7. перепублікували без пароля — публічне, без застарілого
        self.set_password(None)
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.api_share(), {'publish_gate': False, 'publish_share_url': GOOD_URL})

    def test_a_share_link_goes_only_to_the_address_this_module_published(self):
        self.set_password('pw-1')
        other = 'https://pv-liga.vercel.app'
        # ЛІГА-публікація лишила адресу, а модуль ще не публікував
        self.seed_meta(publish_url=other, published_at='01.01.2026 10:00')
        self.assertEqual(self.api_share(), {'publish_gate': True})
        # модуль → ЛІГА → модуль
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.api_share()['publish_share_url'], GOOD_URL + '#k=pw-1')
        self.seed_meta(publish_url=other, published_at='02.01.2026 10:00', publish_verified=True)
        self.assertEqual(self.api_share(), {'publish_gate': True}, 'ключ приклеєно до адреси ЛІГА')
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.api_share()['publish_share_url'], GOOD_URL + '#k=pw-1')
        # запис іншого модуля з тією самою адресою — теж не наш
        remote = dict(self.meta()['publish_remote'])
        self.seed_meta(publish_remote={**remote, 'module': 'vercel-publish'})
        self.assertEqual(self.api_share(), {'publish_gate': True})

    def test_a_hand_edited_or_malformed_publish_url_gets_no_key(self):
        self.set_password('pw-1')
        self.assertEqual(self.publish()[0], 200)
        good = dict(self.meta()['publish_remote'])
        self.seed_meta(publish_url=GOOD_URL + '#already')
        self.assertEqual(self.api_share(), {'publish_gate': True}, 'до виправленої вручну адреси ключ не клеїмо')
        # навіть коли вручну виправлено ОБИДВА поля: подвійний фрагмент `#already#k=…` не складаємо
        self.seed_meta(publish_url=GOOD_URL + '#already', publish_remote={**good, 'url': GOOD_URL + '#already'})
        share = self.api_share()
        self.assertEqual(share['publish_share_url'], GOOD_URL + '#already')
        self.assertNotIn('#k=', share['publish_share_url'])
        for bad_url in (5, ['x'], '', None, {'a': 1}):
            with self.subTest(publish_url=bad_url):
                self.seed_meta(publish_url=bad_url, publish_remote=good)
                self.assertEqual(self.api_share(), {'publish_gate': True})
        for bad_remote in ('рядок', 5, ['x'], {'module': URL_MID}, {**good, 'url': 5},
                           {k: v for k, v in good.items() if k != 'url'}):      # без `url` — запис попереднього формату
            with self.subTest(publish_remote=bad_remote):
                self.seed_meta(publish_url=GOOD_URL, publish_remote=bad_remote)
                self.assertEqual(self.api_share(), {'publish_gate': True})

    def test_the_gate_hash_is_a_short_total_fingerprint(self):
        self.assertEqual(serve._gate_hash('pw'), hashlib.sha256(b'pw').hexdigest()[:16])
        self.assertNotEqual(serve._gate_hash('pw'), serve._gate_hash('pw2'))
        for bad in (None, 5, b'pw', ['pw'], '\ud800'):
            with self.subTest(bad=bad):
                self.assertIsNone(serve._gate_hash(bad))

    def test_a_remote_without_a_hash_counts_as_a_changed_password(self):
        self.set_password('pw-1')
        self.assertEqual(self.publish()[0], 200)
        remote = {k: v for k, v in self.meta()['publish_remote'].items() if k != 'gate_hash'}
        self.seed_meta(publish_remote=remote)
        self.assertEqual(self.api_share(), {'publish_gate': True, 'publish_gate_stale': True,
                                            'publish_share_url': GOOD_URL})

    def test_a_password_that_cannot_be_encoded_is_no_password_and_does_not_break_api_task(self):
        """Самотній сурогат у `secrets.json`, правленому вручну: `quote` падав би на ньому поза `try` (5xx)."""
        self.set_password('good-pw')
        self.assertEqual(self.publish()[0], 200)
        bad = json.dumps({'off': {URL_MID: {'password': '\ud800x'}}})
        with open(os.path.join(self.deai, 'secrets.json'), 'w', encoding='utf-8') as fh:
            fh.write(bad)
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual({k: task[k] for k in ('publish_gate', 'publish_gate_stale', 'publish_share_url')},
                         {'publish_gate': True, 'publish_gate_stale': True, 'publish_share_url': GOOD_URL})
        os.remove(os.path.join(self.tx_dir, 'iterations.json'))             # ще не публікували: «пароля нема»
        _write_task_files(self.tx_dir)
        self.assertEqual(self.api_share(), {'publish_gate': False})

    # ---- адреса, що лише схожа на правильну ----

    def test_a_url_that_only_looks_right_is_refused(self):
        bad = {
            'bidi override': 'https://pv-1.vercel.app/\u202e', 'bidi isolate': 'https://pv-1.vercel.app/\u2066x',
            'C1 control NEL': 'https://pv-1.vercel.app/\x85', 'C1 CSI': 'https://pv-1.vercel.app/\x9b',
            'zero width': 'https://pv-1.vercel.app/\u200b',
            'кирилична а в хості': 'https://pv-1.vercel.\u0430pp', 'кирилична р': 'https://\u0440v-1.vercel.app',
            'IDN не punycode': 'https://пв.example', 'fullwidth slash': 'https://pv-1.vercel.app\uff0fx',
            'порт :abc': 'https://pv-1.vercel.app:abc/', 'порт :99999': 'https://pv-1.vercel.app:99999/',
            'порт :65536': 'https://pv-1.vercel.app:65536/', 'порт :-1': 'https://pv-1.vercel.app:-1/',
            'хост .': 'https://./', 'хост -': 'https://-/', 'хост ..': 'https://../', 'a..b': 'https://a..b/',
            '.a.b': 'https://.a.b/', 'a.b.': 'https://a.b./', '-a.b': 'https://-a.b/', 'a-.b': 'https://a-.b/',
            'a.-b': 'https://a.-b/', 'підкреслення': 'https://a_b.c/', 'IPv6': 'https://[::1]/',
            'мітка 64': 'https://' + 'a' * 64 + '.example/', 'хост 254': 'https://' + '.'.join(['a' * 50] * 5) + '.bcd/',
            # IP-адреси в будь-якій формі й одномітковий хост — не адреса превʼю (докстрінг `_url_host_ok`)
            'IPv4': 'https://127.0.0.1/', 'IPv4 десяткове': 'https://2130706433/', 'IPv4 hex': 'https://0x7f.1/',
            'IPv4 hex повне': 'https://0x7f.0x0.0x0.0x1/', 'IPv4 скорочене': 'https://127.1/',
            'метадані хмари': 'https://169.254.169.254/latest', 'IPv4 і порт': 'https://10.0.0.1:8080/',
            'localhost': 'https://localhost/', 'localhost і порт': 'https://localhost:3000/', 'одна мітка': 'https://intranet/',
            'остання мітка цифрова': 'https://a.b.123/', 'IPv6 і порт': 'https://[::1]:8443/',
        }
        for what, url in bad.items():
            with self.subTest(what):
                self.refused(result(url=url), what)

    def test_the_host_rule_is_two_or_more_dns_labels_with_an_alphabetic_last_one(self):
        """Саме правило, без розбору адреси: докстрінг `_url_host_ok` обіцяв «IP-адреси не пускаємо», а крапкова IPv4 за
        формою збігалась з міткою й проходила."""
        ok = ('pv-1.vercel.app', 'a.b', 'xn--e1afmkfd.xn--p1ai', 'a-b.c-d.example', '1.example', '0x7f.example',
              'a' * 63 + '.example')
        bad = ('127.0.0.1', '2130706433', '0x7f.1', '0x7f.0x0.0x0.0x1', '127.1', '169.254.169.254', '10.0.0.1',
               'localhost', 'intranet', 'a', '1', 'a.b.1', 'a.b.0x7f', '::1', '[::1]', '', '.', 'a..b', 'a.b.', '.a.b',
               'a.-b', 'A.B', None, 5, b'a.b')
        for host in ok:
            with self.subTest(ok=host):
                self.assertTrue(serve._url_host_ok(host), host)
        for host in bad:
            with self.subTest(bad=host):
                self.assertFalse(serve._url_host_ok(host), host)

    def test_ascii_urls_with_ports_and_punycode_hosts_are_still_accepted(self):
        for url in ('https://pv-1.vercel.app:443/', 'https://a.b:1/', 'https://a.b:65535/x',
                    'https://xn--e1afmkfd.xn--p1ai/', 'https://' + 'a' * 63 + '.example/', 'https://a-b.c-d.example',
                    'https://a.b:/'):
            with self.subTest(url=url):
                self.cfg['result'] = result(url=url)
                st, body = self.publish()
                self.assertEqual((st, body.get('url')), (200, url), body)

    # ---- контроль: гілка `folder` і ЛІГА не змінились, нічого не вийшло назовні ----

    def test_a_present_url_module_does_not_change_the_folder_branch(self):
        self.enable_folder(self.off)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames'])
        meta = self.meta()
        self.assertEqual(meta['publish_local']['module'], MID)
        for key in ('published_at', 'publish_verified', 'publish_remote'):
            self.assertNotIn(key, meta, f'`{key}` записано для folder-модуля')
        self.assertIsNone(meta['publish_url'])
        self.assertEqual(self.cfg['calls'], [])
        self.assert_quiet()

    def test_nothing_goes_out_from_the_core_on_any_url_path(self):
        dm.write_secrets('off', URL_MID, {'password': 'pw1'})
        self.publish()
        self.publish({'build_only': True})
        self.cfg['result'] = result(url='http://x.example')
        self.publish()
        self.get('/api/task')
        self.assert_quiet()


# ============================================================================ 2b-2, Task 3: превʼю з коментарями модуля

#: Знімок старого бандла адаптера ЛІГИ (до 0.10.0): у `app/vendor/` його більше нема.
OLD_LEAGUE_ADAPTER = os.path.join(ROOT, 'tests', 'fixtures', 'legacy-comments', 'supabase-adapter.min.js')
MEMO_ID = 'memo-comments'
MEMO_SRC = os.path.join(ROOT, 'tests', 'fixtures', 'modules', MEMO_ID)
LAYER_SRC = os.path.join(ROOT, 'app', 'vendor', 'comment-layer.min.js')
#: Непублічний секрет (`token`: лише сервер модуля) і публічний (`pubkey`: може потрапити в сторінки).
TOKEN, PUBKEY = 'tok-SECRET-93', 'pk-OPEN-93'
ENDPOINT = 'http://127.0.0.1:4777'


def _copy_module(src, mods, mid=None):
    dest = os.path.join(mods, mid or os.path.basename(src))
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns('__pycache__'))
    return dest


def _memo_provider(case):
    """`(Module memo-comments, тека вбудованих модулів)` у світі, де `dm.builtin_dir` указує на тимчасову теку з
    фікстурою (`TaskFixture`: шар просторів вимкнено, тож каталог — єдине, що потрібне Module)."""
    mods = tempfile.mkdtemp(prefix='dc-bp-mods-')
    case.addCleanup(shutil.rmtree, mods, True)
    _copy_module(MEMO_SRC, mods)
    # ЛІГА (4b-2) веде коментарі вбудованим `supabase-comments`: у світі з підміненим каталогом він мусить бути поруч.
    _copy_module(os.path.join(ROOT, 'app', 'modules', 'supabase-comments'), mods)
    patch = mock.patch.object(dm, 'builtin_dir', lambda: mods)
    patch.start()
    case.addCleanup(patch.stop)
    dm.reset_caches()
    case.addCleanup(dm.reset_caches)
    prov = dm.catalog()[MEMO_ID]
    case.assertEqual(prov.status, 'ok', prov.error)
    return prov, mods


def _files(root, skip_top=('shell',)):
    """{відносний шлях: байти} усього дерева (без `shell/`: це наші ж модулі оболонки)."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        if os.path.relpath(dirpath, root).split(os.sep)[0] in skip_top:
            dirs[:] = []
            continue
        for fn in files:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, root)] = _bytes(p)
    return out


def _page_cfg(html):
    """Конфіг сторінки: `window.__deaiCommentsCfg = <літерал>;` → dict (літерал — валідний JSON)."""
    m = re.search(r'window\.__deaiCommentsCfg = (\{.*?\});\n', html)
    assert m, 'у сторінці нема window.__deaiCommentsCfg'
    return json.loads(m.group(1))


class CommentsBuild(TaskFixture):
    """`build_preview(comments={'module': Module, 'config': {…}, 'channel': '…'})` напряму: що кладе збірка в `publish/`."""

    def setUp(self):
        super().setUp()
        self.prov, self.mods = _memo_provider(self)
        self.channel = 'deai/s1/fixture'

    def comments(self, **over):
        return {'module': self.prov, 'config': {'endpoint': ENDPOINT, 'pubkey': PUBKEY}, 'channel': self.channel, **over}

    def pages(self, pub):
        man = json.loads(_read(os.path.join(pub, 'manifest.json')))
        return [p['path'] for p in man['pages']]

    def test_the_build_has_exactly_the_layer_and_the_declared_adapter_files(self):
        pub = self._build(comments=self.comments(), gate_pw=None)['dir']
        vend = os.path.join(pub, 'comment-layer')
        self.assertEqual(sorted(os.listdir(vend)), ['adapter.js', 'comment-layer.min.js'])
        self.assertEqual(_bytes(os.path.join(vend, 'comment-layer.min.js')), _bytes(LAYER_SRC))
        self.assertEqual(_bytes(os.path.join(vend, 'adapter.js')), _bytes(os.path.join(MEMO_SRC, 'adapter.js')))
        self.assertFalse(os.path.exists(os.path.join(vend, 'supabase-adapter.min.js')))
        for dirpath, dirs, _files_ in os.walk(pub):
            self.assertNotIn('comment-layer', [d for d in dirs if dirpath != pub], dirpath)    # одна тека, у корені збірки

    def test_a_module_with_several_client_files_ships_each_in_the_manifest_order(self):
        d = _copy_module(MEMO_SRC, self.mods, 'twin-comments')
        man = json.loads(_read(os.path.join(d, 'module.json')))
        man.update(id='twin-comments', client=['lib.js', 'adapter.js'])
        _write_json(os.path.join(d, 'module.json'), man)
        with open(os.path.join(d, 'lib.js'), 'w', encoding='utf-8') as fh:
            fh.write('window.__lib = 1;\n')
        twin = dm.catalog()['twin-comments']
        self.assertEqual((twin.status, twin.client), ('ok', ('lib.js', 'adapter.js')), twin.error)
        pub = self._build(comments=self.comments(module=twin), gate_pw=None)['dir']
        self.assertEqual(sorted(os.listdir(os.path.join(pub, 'comment-layer'))),
                         ['adapter.js', 'comment-layer.min.js', 'lib.js'])
        html = _read(os.path.join(pub, 'it2', 'index.html'))
        at = [html.index(f'<script src="../comment-layer/{n}"') for n in ('lib.js', 'adapter.js')]
        self.assertEqual(at, sorted(at))
        self.assertLess(at[1], html.index('window.__deaiCommentsCfg'))

    def test_every_page_loads_the_layer_and_the_adapter_by_paths_relative_to_its_own_depth(self):
        pub = self._build(comments=self.comments(), gate_pw=None)['dir']
        pages = self.pages(pub)
        self.assertEqual(sorted(pages), sorted(SOURCE_PAGES))
        self.assertEqual(sorted({p.count('/') for p in pages}), [1, 2], 'фікстура мусить мати сторінки різної глибини')
        for rel in pages:
            html = _read(os.path.join(pub, rel))
            up = '../' * rel.count('/')               # `it1/alpha/index.html` → `../../`, `it2/index.html` → `../`
            with self.subTest(rel=rel):
                at = [html.index(s) for s in (
                    f'<script src="{up}comment-layer/comment-layer.min.js"',
                    f'<script src="{up}comment-layer/adapter.js"',
                    'window.__deaiCommentsCfg = ',
                    'window.DeaiComments.create(')]
                self.assertEqual(at, sorted(at), 'порядок: шар → адаптер → конфіг → завантажувач')
                # жодної адреси, що залежала б від хоста канваса чи іншої глибини
                for src in re.findall(r'<script src="([^"]*)"', html):
                    self.assertRegex(src, r'^(\.\./)+comment-layer/[a-z.-]+\.js$', src)
                self.assertNotIn('/app/vendor', html)
                self.assertNotIn('/api/module-client/', html)
                # у публікації нема ні інспектора, ні вкладок аудиторій, ні простору в URL, ні CDN Supabase
                for gone in ('inspector', 'audiences', 'onAudience', 'sp=', 'ds-tokens', 'supabase', 'jsdelivr', 'dc/fixture'):
                    self.assertNotIn(gone, html.lower() if gone == 'supabase' else html, gone)

    def test_the_page_config_is_the_public_config_plus_the_core_channel_and_the_version(self):
        pub = self._build(comments=self.comments(), gate_pw=None)['dir']
        for rel in self.pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertEqual(_page_cfg(html), {'endpoint': ENDPOINT, 'pubkey': PUBKEY, 'channel': self.channel}, rel)
        html = _read(os.path.join(pub, 'it1', 'alpha', 'index.html'))
        self.assertIn(f'version: "{serve.pm.page_version_tag("it1", {"id": "alpha"})}"', html)

    def test_the_core_channel_wins_over_a_channel_key_in_the_config(self):
        cm = self.comments(config={'endpoint': ENDPOINT, 'channel': 'evil/channel', 'onChange': 'x'})
        pub = self._build(comments=cm, gate_pw=None)['dir']
        self.assertEqual(_page_cfg(_read(os.path.join(pub, 'it2', 'index.html')))['channel'], self.channel)

    def test_a_hostile_config_value_cannot_break_out_of_the_script(self):
        hostile = '</script><script>alert(1)</script>\u2028&"\'\\'
        pub = self._build(comments=self.comments(config={'endpoint': hostile}), gate_pw=None)['dir']
        html = _read(os.path.join(pub, 'it2', 'index.html'))
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertNotIn('\u2028', html)
        self.assertEqual(_page_cfg(html)['endpoint'], hostile)

    def test_the_gate_still_covers_every_page_of_a_module_build(self):
        pub = self._build(comments=self.comments(), gate_pw='x')['dir']
        for rel in self.pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertIn('id="authgate"', html, rel)
            self.assertIn('window.__deaiCommentsCfg', html, rel)
        self.assertEqual(serve.preview_gate_state(self._args()[0], 'x')['state'], 'current')

    def test_the_league_build_and_a_module_build_share_one_template_and_differ_only_in_the_adapter_files(self):
        """4b-2: окремого шаблону ЛІГИ нема (було: «два види сніпета не позичають один в одного»). Обидві збірки йдуть через
        `inject_module_comment_layer`; ЛІГА везе файли вбудованого `supabase-comments`, модуль — свої."""
        calls = []
        orig = serve.inject_module_comment_layer

        def spy(html, assets_base, client_urls, config, **kw):
            calls.append((client_urls, config))
            return orig(html, assets_base, client_urls, config, **kw)
        with mock.patch.object(serve, 'inject_module_comment_layer', spy):
            self._build(comments=self.comments(), gate_pw=None)
            module_calls, calls[:] = list(calls), []
            pub = self._build(comments=self._league(), gate_pw=None)['dir']
        self.assertEqual(len(module_calls), len(calls), 'одна ін\'єкція на сторінку в обох збірках')
        self.assertTrue(all(urls[-1].endswith('/adapter.js') for urls, _cfg in calls + module_calls))
        self.assertEqual(sorted(os.listdir(os.path.join(pub, 'comment-layer'))),
                         ['adapter.js', 'comment-layer.min.js', 'supabase.min.js'])
        self.assertIn('CommentLayer.init', _read(os.path.join(pub, 'it2', 'index.html')))

    def test_anything_but_false_or_a_complete_module_dict_raises_before_touching_the_disk(self):
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(pub)
        keep = os.path.join(pub, 'keep.txt')
        with open(keep, 'w', encoding='utf-8') as fh:
            fh.write('попередня збірка')
        task, tid, its = self._args()
        bad = _copy_module(MEMO_SRC, self.mods, 'bad-comments')           # не завантажений модуль: `status` не `ok`
        os.remove(os.path.join(bad, 'adapter.js'))
        man = json.loads(_read(os.path.join(bad, 'module.json')))
        man['id'] = 'bad-comments'
        _write_json(os.path.join(bad, 'module.json'), man)
        broken = dm.catalog()['bad-comments']
        self.assertEqual(broken.status, 'error')
        cases = {
            "'legacy' (значення постачальника, а не рішення збірки)": 'legacy', 'None': None, '1': 1, '0': 0,
            'True (4b-2: шляху «зашитий Supabase» нема)': True,
            'порожній словник': {},
            'без channel': {'module': self.prov, 'config': {}},
            'без config': {'module': self.prov, 'channel': self.channel},
            'зайвий ключ': {**self.comments(), 'files': []},
            'module — рядок': self.comments(module=MEMO_ID),
            'module — не `ok`': self.comments(module=broken),
            'config — список': self.comments(config=[]),
            'порожній channel': self.comments(channel=''),
            'channel — не рядок': self.comments(channel=7),
        }
        for what, comments in cases.items():
            with self.subTest(what):
                with self.assertRaises(ValueError):
                    serve.build_preview(task, tid, its, comments=comments, gate_pw=None, build='module')
                self.assertEqual(os.listdir(pub), ['keep.txt'])
                self.assertEqual(_read(keep), 'попередня збірка')

    def test_a_module_without_the_comments_role_is_refused(self):
        _copy_module(os.path.join(ROOT, 'app', 'modules', 'css-tokens'), self.mods)
        tokens = dm.catalog()['css-tokens']
        self.assertEqual(tokens.status, 'ok', tokens.error)
        with self.assertRaises(ValueError):
            self._build(comments=self.comments(module=tokens), gate_pw=None)

    def test_a_symlinked_adapter_file_refuses_the_build_before_the_previous_one_is_wiped(self):
        outside = os.path.join(self.cfgdir, 'outside.js')
        with open(outside, 'w', encoding='utf-8') as fh:
            fh.write('window.OUTSIDE = 1;')
        first = _tree(self._build(comments=self.comments(), gate_pw=None)['dir'])
        adapter = os.path.join(self.mods, MEMO_ID, 'adapter.js')
        os.remove(adapter)
        os.symlink(outside, adapter)                  # Module вже в памʼяті (з каталогу ДО підміни): це вікно між рішенням і збіркою
        with self.assertRaises(dm.ModuleError) as cm:
            self._build(comments=self.comments(), gate_pw=None)
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertIn('adapter.js', cm.exception.message)
        self.assertEqual(_tree(os.path.join(self.tmp, 'publish')), first, 'попередню збірку не чіпано')
        self.assertNotIn(b'OUTSIDE', b''.join(_files(os.path.join(self.tmp, 'publish')).values()))

    def test_a_hard_linked_or_vanished_adapter_file_refuses_the_build_too(self):
        adapter = os.path.join(self.mods, MEMO_ID, 'adapter.js')
        link = os.path.join(self.cfgdir, 'hard.js')
        os.link(adapter, link)                        # жорстке посилання: `st_nlink` 2 — файл «ще чийсь»
        with self.assertRaises(dm.ModuleError):
            self._build(comments=self.comments(), gate_pw=None)
        os.remove(link)
        os.remove(adapter)
        with self.assertRaises(dm.ModuleError):
            self._build(comments=self.comments(), gate_pw=None)

    def test_an_adapter_file_that_grew_past_the_limit_after_loading_refuses_the_build(self):
        with open(os.path.join(self.mods, MEMO_ID, 'adapter.js'), 'a', encoding='utf-8') as fh:
            fh.write('/*' + 'x' * dm.MAX_CLIENT_BYTES + '*/')
        with self.assertRaises(dm.ModuleError) as cm:
            self._build(comments=self.comments(), gate_pw=None)
        self.assertIn(str(dm.MAX_CLIENT_BYTES), cm.exception.message)

    def test_an_adapter_file_named_like_a_core_bundle_is_refused_before_anything_is_written(self):
        """Також ЗА ІНШОГО РЕГІСТРУ: на macOS/Windows `Comment-layer.min.js` — це той самий файл, що й шар коментатора."""
        n = 0
        for core in serve.BUNDLES:
            for name in (core, core[0].upper() + core[1:], core.replace('layer', 'LAYER').replace('adapter', 'ADAPTER')):
                n += 1
                with self.subTest(name=name):
                    mid = f'clash-{n}'
                    d = _copy_module(MEMO_SRC, self.mods, mid)
                    man = json.loads(_read(os.path.join(d, 'module.json')))
                    man.update(id=mid, client=[name])
                    _write_json(os.path.join(d, 'module.json'), man)
                    os.rename(os.path.join(d, 'adapter.js'), os.path.join(d, name))
                    clash = dm.catalog()[mid]
                    self.assertEqual(clash.status, 'ok', clash.error)
                    pub = os.path.join(self.tmp, 'publish')
                    with self.assertRaises(dm.ModuleError):
                        self._build(comments=self.comments(module=clash), gate_pw=None)
                    self.assertFalse(os.path.exists(pub), 'збірка почалась, хоч файл адаптера підмінив би шар')

    def test_the_layer_bundle_name_is_the_literal_one_and_one_of_the_league_bundles(self):
        self.assertEqual(serve.LAYER_BUNDLE, 'comment-layer.min.js')
        self.assertIn(serve.LAYER_BUNDLE, serve.BUNDLES)

    def test_built_pages_import_back_to_the_source_for_both_kinds_of_comments_gated_and_not(self):
        """Коловий тест: сторінки, які справді склала `build_preview`, `bin/import_preview.strip_publish` повертає в ВИХІДНІ
        (імпорт чужого превʼю з коментарями модуля, 2b-2). ЛІГА — контроль."""
        sys.path.insert(0, os.path.join(ROOT, 'bin'))
        self.addCleanup(sys.path.remove, os.path.join(ROOT, 'bin'))
        import import_preview as ip
        for label, comments in (('legacy', self._league()), ('module', self.comments())):
            for gate_pw in ('x', None):
                with self.subTest(comments=label, gate=gate_pw is not None):
                    pub = self._build(comments=comments, gate_pw=gate_pw)['dir']
                    for rel in self.pages(pub):
                        built = _read(os.path.join(pub, rel))
                        src = _read(os.path.join(self.tmp, 'iterations', rel))
                        if label == 'legacy' and gate_pw is None:
                            continue                   # збірка ЛІГА без гейта не існує (пароль ЛІГА є завжди)
                        clean, ok = ip.strip_publish(built)
                        self.assertTrue(ok, rel)
                        self.assertEqual(clean, src, rel)
                        self.assertNotIn('__deaiCommentsCfg', clean)


class PublishCommentsDecision(TaskFixture):
    """`serve.publish_comments` як таблиця: (постачальник ролі `comments`) × (шлях ЛІГА чи модуль публікації)."""

    SPACE = {'id': 's1', 'path': '/nowhere', 'legacy': False, 'integrations': True}

    def setUp(self):
        super().setUp()
        self.prov, _mods = _memo_provider(self)

    CTX = {'ctx': 'sentinel'}         # `module_ctx` підставний: простір `/nowhere` справжнього `space.json` не має

    def decide(self, prov, *, module_publish, tid='t1', err=None, config=None, config_error=None, task=None, space=None):
        space = space or self.SPACE
        asked = []
        provider = mock.patch.object(serve, 'comments_provider',
                                     lambda space: (asked.append(space), (prov, err))[1])
        client = mock.patch.object(dm, 'comments_client', mock.Mock(
            side_effect=config_error, return_value=config if config is not None else {'endpoint': ENDPOINT}))
        with provider, client as cc, mock.patch.object(dm, 'module_ctx', return_value=self.CTX):
            out = serve.publish_comments(space, task or {}, tid, module_publish=module_publish)
        self.assertEqual(asked, [space], 'простір передається провайдеру як є, один раз')
        return out, cc

    def test_the_league_comments_are_the_builtin_module_only_on_the_league_path(self):
        """4b-2: ЛІГА на своєму шляху — словник вбудованого `supabase-comments` з каналом ЛІГИ (`comment_project` задачі чи
        `dc/<задача>`) і `ctx` із `module_ctx` запису; у збірці МОДУЛЯ публікації — як і було, `False`. 4d-4b: постачальник — запис `supabase-comments`
        простору ЛІГА фікстури (було `implicit.for_role('comments')` і ctx з конфігу установки)."""
        league = {'id': 'liga', 'path': self.league_path, 'legacy': True, 'integrations': True}
        prov = dm.catalog(league)['supabase-comments']
        (comments, warn), cc = self.decide(prov, module_publish=False, task={'comment_project': 'proj/alpha'}, space=league)
        self.assertIsNone(warn)
        self.assertEqual((comments['module'].id, comments['channel']), ('supabase-comments', 'proj/alpha'))
        self.assertEqual(self.decide(prov, module_publish=False, space=league)[0][0]['channel'], 'dc/t1')
        ((space, mod, ctx), _kw), = cc.call_args_list[:1]
        self.assertEqual((space, mod.id), (league, 'supabase-comments'))
        self.assertEqual(ctx, self.CTX, 'ctx — від `module_ctx` запису, а не з конфігу установки')
        self.assertEqual(self.decide(prov, module_publish=True, space=league)[0], (False, None))

    def test_no_provider_means_no_comments_on_both_paths(self):
        for module_publish in (False, True):
            self.assertEqual(self.decide(None, module_publish=module_publish)[0], (False, None))

    def test_unexpected_provider_values_mean_no_comments_never_the_league_snippet(self):
        for odd in ('LEGACY', 'other', 1, True, ['legacy'], {'id': 'x'}):
            for module_publish in (False, True):
                with self.subTest(odd=odd, module_publish=module_publish):
                    self.assertEqual(self.decide(odd, module_publish=module_publish)[0], (False, None))

    def test_a_module_gives_its_module_its_checked_config_and_the_core_channel_on_both_paths(self):
        for module_publish in (False, True):
            with self.subTest(module_publish=module_publish):
                (comments, warn), cc = self.decide(self.prov, module_publish=module_publish,
                                                   config={'endpoint': ENDPOINT, 'pubkey': 'p'})
                self.assertIsNone(warn)
                self.assertEqual(set(comments), {'module', 'config', 'channel'})
                self.assertIs(comments['module'], self.prov)
                self.assertEqual(comments['config'], {'endpoint': ENDPOINT, 'pubkey': 'p'})
                self.assertEqual(comments['channel'], 'deai/s1/t1')
                cc.assert_called_once_with(self.SPACE, self.prov, self.CTX)      # перевірений `comments_client`, а не сирий виклик

    def test_a_failed_decision_is_false_plus_the_code_never_the_league_snippet(self):
        for module_publish in (False, True):
            for err in (dm.ModuleError('module-error', message='x'), dm.ModuleError('space-json-unreadable', message='x')):
                with self.subTest(module_publish=module_publish, code=err.code):
                    self.assertEqual(self.decide(None, module_publish=module_publish, err=err)[0], (False, err.code))
            with self.subTest(module_publish=module_publish, what='client_config'):
                out, _cc = self.decide(self.prov, module_publish=module_publish,
                                       config_error=dm.ModuleError('check-timeout', message='slow'))
                self.assertEqual(out, (False, 'check-timeout'))

    def test_a_bad_channel_is_a_failure_before_any_module_code_runs(self):
        for tid in ('a/b', '', 'a\nb'):
            with self.subTest(tid=tid):
                out, cc = self.decide(self.prov, module_publish=False, tid=tid)
                self.assertEqual(out, (False, 'module-error'))
                cc.assert_not_called()


class CommentsPublish(DispatchWorld):
    """Усі шляхи публікації (ЛІГА, `static-publish`, модуль «за адресою») і рішення про коментарі превʼю: воно береться з
    `provider('comments', простір)` — ОДИН раз на публікацію, з простором ЯВНО, а не з `integrations_on()`.

    Світ — `DispatchWorld` + тека вбудованих модулів: справжній `static-publish`, фікстура `memo-comments`, фікстура
    `url-pub` (`publish_target: url`). Простір `off` — без інтеграцій (задача `tx`), `on` — з ними (задача `ty`)."""

    URL = 'url-pub'

    def setUp(self):
        super().setUp()
        self.mods = os.path.join(self.tmp, 'modules')
        _copy_module(os.path.join(ROOT, 'app', 'modules', MID), self.mods)
        _copy_module(MEMO_SRC, self.mods)
        _copy_module(os.path.join(ROOT, 'app', 'modules', 'supabase-comments'), self.mods)   # ЛІГА (4b-2) — вбудований модуль
        _copy_module(os.path.join(ROOT, 'app', 'modules', 'vercel-publish'), self.mods)      # ЛІГА публікує явним записом (4d-4b)
        _write_json(os.path.join(self.mods, self.URL, 'module.json'),
                    {'api': 1, 'id': self.URL, 'name': self.URL, 'version': '1.0.0', 'roles': ['publish'],
                     'publish_target': 'url',
                     'settings': [{'key': 'password', 'type': 'secret', 'label': 'Password'}]})
        with open(os.path.join(self.mods, self.URL, 'server.py'), 'w', encoding='utf-8') as fh:
            fh.write('def check(ctx):\n    return {"ok": True}\n'
                     'def publish(ctx, build_dir, task):\n'
                     f'    return {{"url": "{GOOD_URL}", "state": {{}}, "verified": True}}\n')
        patch = mock.patch.object(dm, 'builtin_dir', lambda: self.mods)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        self.addCleanup(self.trip_is_quiet)

    def trip_is_quiet(self):
        self.assertEqual(self.trip.hits, [], 'вихід за межі процесу')

    # ---- фікстури ----

    def enable_memo(self, space, token=TOKEN, pubkey=PUBKEY, endpoint=ENDPOINT):
        if space['id'] == self.on['id']:
            dm.write_module_state(space, 'supabase-comments', enabled=False)   # одна роль — один постачальник: свій модуль ЗАМІНЮЄ запис ЛІГИ
        dm.write_module_state(space, MEMO_ID, enabled=True, settings={'endpoint': endpoint})
        dm.write_secrets(space['id'], MEMO_ID, {'token': token, 'pubkey': pubkey})
        self.assertIsInstance(dm.provider('comments', space), dm.Module)

    def enable_url(self, space):
        dm.write_module_state(space, MID, enabled=False)
        self.replace_publisher(space, self.URL)

    def break_memo(self):
        """Явно ввімкнений модуль коментарів, що не завантажився (оголошений файл адаптера зник)."""
        os.remove(os.path.join(self.mods, MEMO_ID, 'adapter.js'))
        self.assertEqual(dm.catalog()[MEMO_ID].status, 'error')

    def leak_memo(self):
        """`client_config` модуля показує значення НЕпублічного секрету `token` — ядро мусить це відхилити."""
        path = os.path.join(self.mods, MEMO_ID, 'server.py')
        src = _read(path)
        leaky = src.replace("ctx['secrets'].get('pubkey') or ''", "ctx['secrets'].get('token') or ''")
        self.assertNotEqual(src, leaky, 'фікстура змінилась: нема що підміняти')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(leaky)

    def publish(self, payload=None, task=None):
        return self.post('/api/publish', payload, {'X-Canvas-Task': task} if task else None)

    def assert_module_build(self, root, channel, pages=tuple(SOURCE_PAGES)):
        """Збірка з коментарями модуля `memo-comments` у `root` (`publish/` або опублікована тека)."""
        vend = os.path.join(root, 'comment-layer')
        self.assertEqual(sorted(os.listdir(vend)), ['adapter.js', 'comment-layer.min.js'])
        self.assertEqual(_bytes(os.path.join(vend, 'comment-layer.min.js')), _bytes(LAYER_SRC))
        self.assertEqual(_bytes(os.path.join(vend, 'adapter.js')), _bytes(os.path.join(MEMO_SRC, 'adapter.js')))
        for rel in pages:
            html = _read(os.path.join(root, rel))
            up = '../' * rel.count('/')
            self.assertIn(f'<script src="{up}comment-layer/comment-layer.min.js"', html, rel)
            self.assertIn(f'<script src="{up}comment-layer/adapter.js"', html, rel)
            self.assertEqual(_page_cfg(html), {'endpoint': ENDPOINT, 'pubkey': PUBKEY, 'channel': channel}, rel)
        self.assert_no_secret_and_no_shared_service(root)

    def assert_no_secret_and_no_shared_service(self, root):
        """Ні секрету модуля, ні спільного Supabase ЛІГА (адреса, ключ, CDN, бандл) в жодному файлі збірки. Шар коментатора
        (`comment-layer.min.js`, ядрова вендорна копія) у заголовку згадує слово «Supabase» і має власний CDN: для нього
        перевіряються лише значення (секрет, адреса, ключ), а не слова."""
        for rel, data in _files(root).items():
            for needle in (TOKEN, sbconf.SB_URL, sbconf.SB_KEY, 'sbUrl', 'sbKey'):
                self.assertNotIn(needle.encode(), data, f'{rel}: {needle}')
            if os.path.basename(rel) != 'comment-layer.min.js':
                for word in (b'supabase', b'cdn.jsdelivr.net'):
                    self.assertNotIn(word, data.lower(), f'{rel}: {word!r}')

    def assert_no_comments(self, root):
        self.assertFalse(os.path.exists(os.path.join(root, 'comment-layer')))
        for rel, data in _files(root).items():
            for needle in (b'CommentLayer', b'comment-layer', b'__deaiCommentsCfg', b'DeaiComments'):
                self.assertNotIn(needle, data, f'{rel}: {needle!r}')
        self.assert_no_secret_and_no_shared_service(root)

    def served(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request('GET', path)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    # ---- static-publish: простір без інтеграцій ----

    def test_static_publish_ships_the_comments_of_the_module_of_the_space(self):
        self.enable_memo(self.off)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames'], 'відповідь без нових ключів')
        self.assertEqual(body['local']['path'], self.dest)
        self.assert_module_build(self.dest, 'deai/off/tx')
        self.assert_module_build(os.path.join(self.tx_dir, 'publish'), 'deai/off/tx')
        self.assertEqual(self.meta()['publish_local']['path'], self.dest)
        self.assert_quiet()

    def test_build_only_ships_them_too(self):
        self.enable_memo(self.off)
        st, body = self.publish({'build_only': True})
        self.assertEqual((st, list(body)), (200, ['ok', 'dir', 'iterations', 'frames']), body)
        self.assert_module_build(body['dir'], 'deai/off/tx')
        self.assertFalse(os.path.exists(self.dest), 'build_only нічого не публікує')
        self.assert_quiet()

    def test_the_channel_is_the_one_of_the_commented_page(self):
        """Піни, поставлені в канвасі (`/commented?ch=project`), і піни в превʼю мусять лежати в ОДНОМУ каналі."""
        self.enable_memo(self.off)
        st, body = self.publish({'build_only': True})
        self.assertEqual(st, 200, body)
        pub_cfg = _page_cfg(_read(os.path.join(body['dir'], 'it2', 'index.html')))
        st, _hd, page = self.served('/commented?it=it1&ch=project')
        self.assertEqual(st, 200)
        self.assertEqual(pub_cfg, _page_cfg(page.decode('utf-8')))

    def test_without_a_comments_module_a_plain_space_builds_without_comments_as_before(self):
        st, body = self.publish()
        self.assertEqual((st, list(body)), (200, ['ok', 'local', 'iterations', 'frames']), body)
        self.assert_no_comments(self.dest)
        self.assertNotIn('comments_unavailable', body)

    def test_a_comments_module_that_was_switched_off_again_means_no_comments(self):
        self.enable_memo(self.off)
        dm.write_module_state(self.off, MEMO_ID, enabled=False)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assert_no_comments(self.dest)
        self.assertNotIn('comments_unavailable', body)

    def test_republishing_after_removing_the_module_leaves_no_comment_layer_behind(self):
        self.enable_memo(self.off)
        self.assertEqual(self.publish()[0], 200)
        self.assertTrue(os.path.isdir(os.path.join(self.dest, 'comment-layer')))
        dm.write_module_state(self.off, MEMO_ID, enabled=False)
        self.assertEqual(self.publish()[0], 200)
        self.assert_no_comments(self.dest)

    # ---- простір з інтеграціями ----

    def test_a_module_publish_in_an_integrations_space_with_the_league_comments_ships_none(self):
        """Рішення: модуль публікації в просторі ЛІГА, де коментарі — зашитий шлях (`'legacy'`), лишає `comments=False`, як у
        0.3.0: спільний Supabase ЛІГА (адреса й ключ) не їде в превʼю, що його зібрав модуль."""
        self.replace_publisher(self.on, MID)
        self.assertEqual(dm.provider('comments', self.on).id, 'supabase-comments')       # було `implicit.for_role('comments')`
        st, body = self.publish(task='ty')
        self.assertEqual((st, list(body)), (200, ['ok', 'local', 'iterations', 'frames']), body)
        want = os.path.join(self.home, 'deai-published', 'on', 'ty')
        self.assertEqual(body['local']['path'], want)
        self.assert_no_comments(want)
        self.assert_no_comments(os.path.join(self.ty_dir, 'publish'))
        self.assert_quiet()

    def test_a_url_module_in_an_integrations_space_with_the_league_comments_ships_none(self):
        """Те саме для модуля «за адресою» (Vercel): зашитий Supabase ЛІГА не їде в превʼю, яке зібрав модуль."""
        self.replace_publisher(self.on, self.URL)
        self.assertEqual(dm.provider('comments', self.on).id, 'supabase-comments')
        st, body = self.publish(task='ty')
        self.assertEqual((st, list(body)), (200, ['ok', 'url', 'verified', 'iterations', 'frames']), body)
        self.assert_no_comments(os.path.join(self.ty_dir, 'publish'))

    def test_a_module_publish_in_an_integrations_space_with_a_comments_module_ships_the_module_comments(self):
        self.replace_publisher(self.on, MID)
        self.enable_memo(self.on)
        st, body = self.publish(task='ty')
        self.assertEqual(st, 200, body)
        self.assert_module_build(os.path.join(self.home, 'deai-published', 'on', 'ty'), 'deai/on/ty')
        self.assert_quiet()

    def test_the_league_path_gets_the_module_snippet_when_the_space_has_a_comments_module(self):
        self.enable_memo(self.on)
        self.assertEqual(dm.provider('publish', self.on).id, 'vercel-publish')
        st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual((st, list(body)), (200, ['ok', 'dir', 'iterations', 'frames']), body)
        self.assert_module_build(body['dir'], 'deai/on/ty')
        for rel in SOURCE_PAGES:                                   # гейт ЛІГА — як був: пароль на кожній сторінці
            self.assertIn('id="authgate"', _read(os.path.join(body['dir'], rel)), rel)

    def test_the_league_path_with_the_league_comments_ships_the_builtin_module_build(self):
        """4b-2: у просторі ЛІГА без власного модуля коментарів збірка несе вбудований `supabase-comments` (було: «стара збірка»
        з бандлами ЛІГИ): його файли, конфіг ЗАПИСУ ЛІГИ й канал ЛІГИ."""
        self.assertEqual(dm.provider('comments', self.on).id, 'supabase-comments')
        with mock.patch.object(serve, 'build_preview', wraps=serve.build_preview) as bp:
            st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual((st, list(body)), (200, ['ok', 'dir', 'iterations', 'frames']), body)
        comments = bp.call_args.kwargs['comments']
        self.assertEqual((comments['module'].id, comments['channel']), ('supabase-comments', 'dc/ty'))
        vend = os.path.join(body['dir'], 'comment-layer')
        self.assertEqual(sorted(os.listdir(vend)), ['adapter.js', 'comment-layer.min.js', 'supabase.min.js'])
        html = _read(os.path.join(body['dir'], 'it2', 'index.html'))
        self.assertIn('CommentLayer.init', html)
        cfg = _page_cfg(html)
        self.assertEqual((cfg['channel'], cfg['url'], cfg['key']), ('dc/ty', sbconf.SB_URL, sbconf.SB_KEY))
        self.assertNotIn('cdn.jsdelivr.net', html)

    def test_the_league_path_with_a_broken_enabled_comments_module_ships_no_comments_at_all_and_warns(self):
        """Явно ввімкнений модуль коментарів, що зламався, у просторі ЛІГА: НЕ спільний Supabase (піни несли б знімки
        приватних макетів у чужий сервіс), а жодних коментарів + попередження. Сама публікація йде."""
        self.enable_memo(self.on)
        self.break_memo()
        with self.assertRaises(dm.ModuleError):
            dm.provider('comments', self.on)                       # контроль: рішення справді «відмова», а не «legacy»
        with mock.patch.object(serve, 'build_preview', wraps=serve.build_preview) as bp:
            st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'dir', 'iterations', 'frames', 'comments_unavailable'])
        self.assertEqual(body['comments_unavailable'], 'module-error')
        self.assertIs(bp.call_args.kwargs['comments'], False)
        self.assert_no_comments(body['dir'])

    def test_the_league_path_with_an_unreadable_space_json_refuses_before_any_build(self):
        """Було: збірка без коментарів + `comments_unavailable: space-json-unreadable`. 4d-4b: без `space.json` нема й запису публікації —
        відмова ДО збірки (`space-json-unreadable` для кожної ролі), коментарі тим паче не їдуть."""
        with open(os.path.join(self.on_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{broken')
        st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual((st, body['ok'], body['code']), (dm.STATUS['space-json-unreadable'], False, 'space-json-unreadable'), body)
        self.assertNotIn('dir', body)
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish')))

    def test_a_module_publish_with_a_broken_enabled_comments_module_still_publishes_without_comments(self):
        self.replace_publisher(self.on, MID)
        self.enable_memo(self.on)
        self.break_memo()
        st, body = self.publish(task='ty')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames', 'comments_unavailable'])
        self.assertEqual(body['comments_unavailable'], 'module-error')
        want = os.path.join(self.home, 'deai-published', 'on', 'ty')
        self.assertEqual(self.meta(self.ty_dir)['publish_local']['path'], want, 'публікація відбулась')
        self.assert_no_comments(want)

    # ---- відмова самого модуля: жодних коментарів, ніколи не «legacy» ----

    def path_world(self, path):
        """`(простір, X-Canvas-Task)` для шляху публікації `static` | `league` | `url`: чиста фікстура memo, у просторі
        ввімкнено рівно потрібний модуль публікації (`league` — жодного: публікує ЛІГА) і memo."""
        shutil.rmtree(os.path.join(self.mods, MEMO_ID), True)
        _copy_module(MEMO_SRC, self.mods)
        dm.reset_caches()
        secrets = os.path.join(self.deai, 'secrets.json')
        if os.path.exists(secrets):
            os.remove(secrets)
        space, task = (self.on, 'ty') if path == 'league' else (self.off, None)
        dm.write_module_state(space, MID, enabled=False)
        dm.write_module_state(space, self.URL, enabled=False)
        if path == 'static':
            dm.write_module_state(space, MID, enabled=True)
        elif path == 'url':
            dm.write_module_state(space, self.URL, enabled=True)
        self.enable_memo(space)
        return space, task

    def test_a_failing_client_config_means_no_comments_and_a_warning_on_every_publish_path(self):
        def secret_in_config(space):
            self.leak_memo()

        def no_endpoint(space):
            dm.write_module_state(space, MEMO_ID, settings={'endpoint': None})
        for failure, code, inject in (('секрет у client_config', 'module-error', secret_in_config),
                                      ('нема обовʼязкового налаштування', 'bad-settings', no_endpoint)):
            for path in ('static', 'league', 'url'):
                with self.subTest(failure=failure, path=path):
                    space, task = self.path_world(path)
                    inject(space)
                    st, body = self.publish({'build_only': True}, task=task)
                    self.assertEqual(st, 200, body)
                    self.assertEqual(body['comments_unavailable'], code, body)
                    self.assertNotIn(TOKEN, json.dumps(body))
                    self.assert_no_comments(body['dir'])

    def test_unreadable_secrets_on_the_league_path_mean_no_comments_and_a_warning(self):
        """Лише ЛІГА: модуль публікації теж читає секрети (пароль), тож на його шляхах відмова приходить раніше й інша."""
        space, task = self.path_world('league')
        with open(os.path.join(self.deai, 'secrets.json'), 'w', encoding='utf-8') as fh:
            fh.write('{broken')
        st, body = self.publish({'build_only': True}, task=task)
        # було: збірка без коментарів + `comments_unavailable`. 4d-4b: пароль превʼю — секрет запису ЛІГИ, тож нечитабельні секрети
        # відмовляють ДО збірки (fail-closed, `preview_password`), а не після неї
        self.assertEqual((st, body['ok'], body['code']), (dm.STATUS['secrets-unreadable'], False, 'secrets-unreadable'), body)
        self.assertNotIn('dir', body)

    def test_the_warning_is_the_code_only_never_a_message_or_a_value(self):
        self.leak_memo()
        self.enable_memo(self.off)
        st, body = self.publish()
        self.assertEqual((st, body['comments_unavailable']), (200, 'module-error'), body)
        self.assertEqual(sorted(k for k in body if 'comments' in k), ['comments_unavailable'])
        self.assertNotIn(TOKEN, json.dumps(body))
        self.assert_no_comments(self.dest)

    # ---- модуль «за адресою» ----

    def test_a_url_module_ships_the_comments_of_the_module_of_the_space(self):
        self.enable_url(self.off)
        self.enable_memo(self.off)
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'url', 'verified', 'iterations', 'frames'], 'відповідь без нових ключів')
        self.assert_module_build(os.path.join(self.tx_dir, 'publish'), 'deai/off/tx')

    def test_a_url_module_without_a_comments_module_builds_without_comments_as_before(self):
        self.enable_url(self.off)
        st, body = self.publish()
        self.assertEqual((st, list(body)), (200, ['ok', 'url', 'verified', 'iterations', 'frames']), body)
        self.assert_no_comments(os.path.join(self.tx_dir, 'publish'))

    def test_a_url_module_with_a_broken_comments_module_warns_before_code_stale(self):
        self.enable_url(self.off)
        self.enable_memo(self.off)
        self.leak_memo()
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'url', 'verified', 'iterations', 'frames', 'comments_unavailable', 'code_stale'])
        self.assertEqual(body['comments_unavailable'], 'module-error')
        self.assert_no_comments(os.path.join(self.tx_dir, 'publish'))

    # ---- одне рішення, простір — явно ----

    def comments_asked(self, task=None):
        """Скільки разів і з яким простором питали `provider('comments', …)` за ОДНУ публікацію."""
        calls = []
        real = dm.provider

        def spy(role, space=None):
            calls.append((role, space))
            return real(role, space)
        with mock.patch.object(dm, 'provider', spy):
            st, body = self.publish({'build_only': True}, task=task)
        self.assertEqual(st, 200, body)
        return [space for role, space in calls if role == 'comments']

    def assert_asked_once_about(self, asked, space):
        self.assertEqual(len(asked), 1, f'рішення про коментарі прийнято {len(asked)} разів')
        self.assertIsInstance(asked[0], dict, 'простір мусить бути переданий явно (запис реєстру), а не `None`')
        self.assertEqual(asked[0]['id'], space['id'])

    def test_static_publish_asks_the_comments_provider_once_with_the_explicit_space(self):
        self.assert_asked_once_about(self.comments_asked(), self.off)

    def test_a_url_module_asks_the_comments_provider_once_with_the_explicit_space(self):
        self.enable_url(self.off)
        self.assert_asked_once_about(self.comments_asked(), self.off)

    def test_the_league_path_asks_the_comments_provider_once_with_the_explicit_space(self):
        self.assert_asked_once_about(self.comments_asked('ty'), self.on)

    def test_a_module_publish_never_asks_which_comments_the_league_would_use(self):
        """Коментарі модульної публікації в `off` — не за `integrations_on()` (це «чи ввімкнено ЛІГА»), а за постачальником."""
        self.enable_memo(self.off)
        with mock.patch.object(spaces, 'integrations_on', side_effect=AssertionError('integrations_on')):
            st, body = self.publish({'build_only': True})
        self.assertEqual(st, 200, body)
        self.assert_module_build(body['dir'], 'deai/off/tx')

    # ---- /published/… роздає скопійовані файли адаптера ----

    def test_published_serves_the_layer_the_adapter_and_the_pages_with_the_snippet_in_the_sandbox(self):
        self.enable_memo(self.off)
        self.assertEqual(self.publish()[0], 200)
        csp = 'sandbox allow-scripts allow-forms allow-popups allow-modals'
        for name, source in (('adapter.js', os.path.join(MEMO_SRC, 'adapter.js')),
                             ('comment-layer.min.js', LAYER_SRC)):
            st, hd, data = self.served(f'/published/off/tx/comment-layer/{name}')
            self.assertEqual(st, 200, name)
            self.assertEqual(data, _bytes(source), name)
            self.assertEqual(hd['content-type'], 'text/javascript; charset=utf-8', name)
            self.assertEqual((hd.get('content-security-policy'), hd.get('x-content-type-options'),
                              hd.get('access-control-allow-origin')), (csp, 'nosniff', '*'), name)
        st, hd, data = self.served('/published/off/tx/it1/alpha/index.html')
        self.assertEqual(st, 200)
        html = data.decode('utf-8')
        self.assertIn('<script src="../../comment-layer/adapter.js"', html)
        self.assertEqual(_page_cfg(html)['channel'], 'deai/off/tx')
        self.assertEqual(self.served('/published/off/tx/comment-layer/supabase-adapter.min.js')[0], 404)   # бандла ЛІГА нема

    # ---- мітка збирача в маніфесті кожного шляху ----

    def built_by(self, root):
        return json.loads(_read(os.path.join(root, 'manifest.json'))).get('build')

    def test_every_publish_path_marks_its_manifest_with_who_built_it(self):
        st, body = self.publish({'build_only': True}, task='ty')                           # ЛІГА (простір `on`)
        self.assertEqual((st, self.built_by(body['dir'])), (200, 'legacy'), body)
        st, body = self.publish({'build_only': True})                                       # static-publish
        self.assertEqual((st, self.built_by(body['dir'])), (200, 'module'), body)
        self.enable_url(self.off)
        st, body = self.publish({'build_only': True})                                       # модуль «за адресою»
        self.assertEqual((st, self.built_by(body['dir'])), (200, 'module'), body)
        self.assertEqual(self.built_by(os.path.join(self.tx_dir, 'publish')), 'module')

    def test_a_league_build_with_module_comments_or_without_comments_is_still_marked_league(self):
        self.enable_memo(self.on)
        st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual((st, self.built_by(body['dir'])), (200, 'legacy'), body)
        self.break_memo()
        st, body = self.publish({'build_only': True}, task='ty')
        self.assertEqual((st, body['comments_unavailable'], self.built_by(body['dir'])), (200, 'module-error', 'legacy'), body)

    # ---- рішення про коментарі — поза замками збірки ----

    def locked_during(self, space_task, publish_kwargs=None):
        """Чи тримається замок теки збірки задачі, поки йде `publish_comments` і поки йде `build_preview` (контроль)."""
        lock = serve._publish_lock(serve._task_dir_key(space_task))
        seen = {}
        real_pc, real_bp = serve.publish_comments, serve.build_preview

        def pc(*a, **kw):
            seen['comments'] = lock.locked()
            return real_pc(*a, **kw)

        def bp(*a, **kw):
            seen['build'] = lock.locked()
            return real_bp(*a, **kw)
        with mock.patch.object(serve, 'publish_comments', pc), mock.patch.object(serve, 'build_preview', bp):
            st, body = self.publish(**(publish_kwargs or {}))
        self.assertEqual(st, 200, body)
        return seen

    def test_the_comments_decision_runs_before_the_build_lock_on_both_module_paths(self):
        """Рішення виконує код модуля (до 10 с) і нічого не пише: замок збірки тримається ЛИШЕ під збірку й копіювання."""
        self.enable_memo(self.off)
        self.assertEqual(self.locked_during(self.tx_dir), {'comments': False, 'build': True})
        self.enable_url(self.off)
        self.assertEqual(self.locked_during(self.tx_dir), {'comments': False, 'build': True})

    def test_a_busy_publish_still_answers_409_and_the_comments_decision_does_not_write_anything(self):
        self.enable_memo(self.off)
        lock = serve._publish_lock(serve._task_dir_key(self.tx_dir))
        self.assertTrue(lock.acquire(blocking=False))
        try:
            st, body = self.publish()
        finally:
            lock.release()
        self.assertEqual((st, body.get('code')), (409, 'publish-busy'), body)
        self.assert_nothing_built()

    # ---- пісочниця `/published`: модальні вікна є, `allow-same-origin` — ні ----

    def test_the_published_sandbox_allows_modals_for_the_prompts_of_the_comment_layer_but_never_the_canvas_origin(self):
        want = {'sandbox', 'allow-scripts', 'allow-forms', 'allow-popups', 'allow-modals'}
        csp = dict(serve.PUBLISHED_HEADERS)['Content-Security-Policy']
        self.assertEqual(set(csp.split()), want)
        self.assertNotIn('allow-same-origin', csp)
        self.enable_memo(self.off)
        self.assertEqual(self.publish()[0], 200)
        for path, status in (('/published/off/tx/it1/alpha/index.html', 200), ('/published/off/tx/comment-layer/adapter.js', 200),
                             ('/published/off/tx/nothing', 404), ('/published/off/tx/.deai-published', 404)):
            got, headers, _body = self.served(path)
            self.assertEqual(got, status, path)
            self.assertEqual(set(headers['content-security-policy'].split()), want, path)

    # ---- файл адаптера підмінили між рішенням і збіркою ----

    def test_a_symlinked_adapter_file_at_build_time_is_a_502_module_error_that_keeps_the_previous_publish(self):
        self.enable_memo(self.off)
        self.assertEqual(self.publish()[0], 200)
        before = _tree(self.dest)
        built_before = _tree(os.path.join(self.tx_dir, 'publish'))
        meta_before = self.meta()['publish_local']
        outside = os.path.join(self.tmp, 'outside.js')
        with open(outside, 'w', encoding='utf-8') as fh:
            fh.write('window.OUTSIDE = 1;')
        adapter = os.path.join(self.mods, MEMO_ID, 'adapter.js')
        real = serve.publish_comments
        calls = []

        def swapped_after_the_decision(*a, **kw):
            out = real(*a, **kw)
            calls.append(out)
            os.remove(adapter)
            os.symlink(outside, adapter)                       # вікно між рішенням (Module вже вибрано) і збіркою
            return out
        with mock.patch.object(serve, 'publish_comments', swapped_after_the_decision):
            st, body = self.publish()
        self.assertEqual(len(calls), 1)
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), body)
        self.assertNotIn('OUTSIDE', json.dumps(body))
        self.assertEqual(_tree(self.dest), before, 'опубліковане не чіпано')
        self.assertEqual(_tree(os.path.join(self.tx_dir, 'publish')), built_before, 'збірку не стерто до відмови')
        self.assertEqual(self.meta()['publish_local'], meta_before)
        # замки відпущено: після ремонту публікація йде
        os.remove(adapter)
        shutil.copy2(os.path.join(MEMO_SRC, 'adapter.js'), adapter)
        self.assertEqual(self.publish()[0], 200)

    def test_the_league_path_with_a_symlinked_adapter_file_is_the_same_502_and_no_vercel(self):
        self.enable_memo(self.on)
        outside = os.path.join(self.tmp, 'outside.js')
        with open(outside, 'w', encoding='utf-8') as fh:
            fh.write('window.OUTSIDE = 1;')
        adapter = os.path.join(self.mods, MEMO_ID, 'adapter.js')
        real = serve.publish_comments

        def swapped_after_the_decision(*a, **kw):
            out = real(*a, **kw)
            os.remove(adapter)
            os.symlink(outside, adapter)
            return out
        with mock.patch.object(serve, 'publish_comments', swapped_after_the_decision):
            st, body = self.publish({}, task='ty')                 # справжня публікація: без `build_only`
        self.assertEqual((st, body.get('code')), (502, 'module-error'), body)
        self.assertEqual(self.spies['_node_bin'].call_count, 0, 'дійшло до деплою')
        self.assertEqual(self.spies['_publish_legacy_call'].call_count, 0, 'модуль Vercel не кликано')
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish')), 'збірку почато, хоч файл адаптера небезпечний')


if __name__ == '__main__':
    unittest.main()

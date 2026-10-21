"""`POST /api/task-new` з `from` — задача з наявної теки (Deai 0.6.0, етап 3b; спека
`docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`, «Сервер: задача з наявної теки»).

Сервер і простори — фікстура `test_spaces_serve.Fixture`: старий простір з інтеграціями (`legacy_id`), `P` без
інтеграцій (`p_id`, `p_path`, задача `x`), порожній `E`. ⛔ Ізоляція та сама: тимчасові `HOME`/`DEAI_HOME`; справжній
`~/.deai` стереже `spaces_guard`.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_spaces_serve import Fixture, _read  # noqa: E402  (модуль сам ставить app/ і bin/ у sys.path)
import serve  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class TaskFrom(Fixture):
    """Тека-джерело — у тимчасовій теці класу; задача лягає в `P`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Структурний охоронець (`test_serve.TestsCannotWriteLiveConfig`) вимагає присвоєння `DEAI_HOME` у САМОМУ файлі,
        # що кличе `/api/task-new`. Ізоляцію робить `Fixture.setUpClass` (і повертає env у `tearDownClass`); тут її
        # повторено явно, тим самим значенням.
        os.environ['DEAI_HOME'] = cls.deai

    def setUp(self):
        super().setUp()
        for p in (os.path.join(self.deai, 'spaces.json'), self.legacy_file, self.p_file):
            self.restore_bytes(p)
        self.src = tempfile.mkdtemp(prefix='adopt-src-', dir=self.tmp)
        self.addCleanup(shutil.rmtree, self.src, True)

    def made(self, tid):
        """Тека задачі, яку може лишити `task-new` (стирає cleanup)."""
        p = os.path.join(self.p_path, tid)
        self.addCleanup(shutil.rmtree, p, True)
        return p

    def put(self, rel, data=b'x'):
        p = os.path.join(self.src, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
        return p

    def full_source(self):
        """Макет зі сміттям навколо: що копіюється, а що ні — див. `test_copies_the_folder_without_junk_and_links`."""
        self.put('index.html', b'<!doctype html><h1>Adopted</h1>')
        self.put('page.css', b'h1{color:red}')
        self.put('img/a.png', b'\x89PNG')
        self.put('sub/keep.py', b'1')                 # .py у ПІДТЕЦІ — не службове (асиметрія `_is_tool_junk`)
        self.put('sub/.hidden/x', b'1')               # і крапкова тека в ПІДТЕЦІ — теж: службове лише в корені
        self.put('.git/config', b'[core]')
        self.put('node_modules/x/i.js', b'1')
        self.put('sub/.git/config', b'[core]')        # `.git`/`node_modules` — на БУДЬ-ЯКОМУ рівні, не лише в корені
        self.put('sub/node_modules/y/i.js', b'1')
        self.put('.vercel/project.json', b'{}')       # службова ТЕКА в корені (`_is_tool_junk`), не з `_ADOPT_SKIP_ANY`
        self.put('sub/.DS_Store', b'junk')
        self.put('build.py', b'print(1)')             # службове в корені
        self.put('.canvas-state.json', b'{}')         # чужий підпис публікації
        outside = os.path.join(self.tmp, 'outside-secret.txt')
        with open(outside, 'w', encoding='utf-8') as f:
            f.write('outside')
        os.symlink(outside, os.path.join(self.src, 'link.txt'))
        os.symlink(self.tmp, os.path.join(self.src, 'linkdir'))

    def it1_files(self, tid):
        root = os.path.join(self.p_path, tid, 'iterations', 'it1')
        out = set()
        for dp, dns, fns in os.walk(root):
            for f in fns:
                out.add(os.path.relpath(os.path.join(dp, f), root))
        return out

    def test_copies_the_folder_without_junk_and_links(self):
        self.full_source()
        tdir = self.made('ad1')
        st, body = self.post('/api/task-new', {'id': 'ad1', 'title': 'Ad', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad1'), {'index.html', 'page.css', os.path.join('img', 'a.png'),
                                                 os.path.join('sub', 'keep.py'), os.path.join('sub', '.hidden', 'x')})
        sizes = sum(len(x) for x in (b'<!doctype html><h1>Adopted</h1>', b'h1{color:red}', b'\x89PNG', b'1', b'1'))
        self.assertEqual(body['copied'], {'files': 5, 'bytes': sizes, 'skipped_links': 2})
        self.assertEqual((body['space'], body['dir']), (self.p_id, tdir))
        with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), encoding='utf-8') as f:
            self.assertIn('Adopted', f.read(), 'стартовий макет замість теки-джерела')
        self.assertIn('ad1', _read(self.p_file)['tasks'])
        with open(os.path.join(tdir, 'iterations.json'), encoding='utf-8') as f:
            its = json.load(f)['iterations']
        self.assertEqual([x['id'] for x in its], ['it1'])
        self.assertTrue(os.path.isfile(os.path.join(self.src, 'build.py')), 'джерело змінилось')

    def test_tilde_is_expanded(self):
        home_src = os.path.join(self.home, 'mock-tilde')
        os.makedirs(home_src, exist_ok=True)
        self.addCleanup(shutil.rmtree, home_src, True)
        with open(os.path.join(home_src, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>T</h1>')
        self.made('ad2')
        st, body = self.post('/api/task-new', {'id': 'ad2', 'space': self.p_id, 'from': '~/mock-tilde'})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad2'), {'index.html'})

    def refused(self, payload, status, code):
        st, body = self.post('/api/task-new', payload)
        self.assertEqual((st, body.get('ok'), body.get('code')), (status, False, code), body)
        return body

    def assert_nothing(self, tid):
        self.assertFalse(os.path.lexists(os.path.join(self.p_path, tid)), 'тека задачі зʼявилась')
        self.assertNotIn(tid, _read(self.p_file)['tasks'])

    def test_only_a_space_without_integrations(self):
        self.put('index.html')
        before = _read(self.legacy_file)
        self.refused({'id': 'ad3', 'space': self.legacy_id, 'from': self.src}, 400, 'from-needs-plain-space')
        self.assertEqual(_read(self.legacy_file), before)
        self.refused({'id': 'ad3', 'space': self.p_id, 'from': self.src, 'gitlab': {'repo': 'r', 'path': 'p'}},
                     400, 'from-needs-plain-space')
        self.assert_nothing('ad3')

    def test_bad_from_values(self):
        for bad in (5, '', '   '):                    # `from: null` — поля нема (див. `test_from_null_means_no_from`)
            with self.subTest(bad=bad):
                self.refused({'id': 'ad4', 'space': self.p_id, 'from': bad}, 400, 'bad-request')
        self.assert_nothing('ad4')

    def test_from_null_means_no_from(self):
        self.made('ad4n')
        st, body = self.post('/api/task-new', {'id': 'ad4n', 'space': self.p_id, 'from': None})
        self.assertEqual(st, 200, body)
        self.assertNotIn('copied', body)

    def test_not_a_folder_or_no_index(self):
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': os.path.join(self.src, 'nope')}, 400, 'from-not-found')
        f = self.put('file.txt')
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': f}, 400, 'from-not-found')
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': self.src}, 400, 'from-no-index')
        target = self.put('real.html')
        os.symlink(target, os.path.join(self.src, 'index.html'))
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': self.src}, 400, 'from-no-index')
        self.assert_nothing('ad5')

    def test_the_folder_must_not_contain_the_task_folder(self):
        with open(os.path.join(self.p_path, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>space root</h1>')
        self.addCleanup(os.remove, os.path.join(self.p_path, 'index.html'))
        self.refused({'id': 'ad6', 'space': self.p_id, 'from': self.p_path}, 400, 'from-contains-space')
        parent = os.path.dirname(self.p_path)
        with open(os.path.join(parent, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>parent</h1>')
        self.addCleanup(os.remove, os.path.join(parent, 'index.html'))
        self.refused({'id': 'ad6', 'space': self.p_id, 'from': parent}, 400, 'from-contains-space')
        self.assert_nothing('ad6')

    def test_an_ancestor_that_cannot_be_compared_does_not_break_the_request(self):
        """Windows: порівняння теки з предком (`samefile`) між дисками може кинути `OSError` — це «не та сама
        тека», а не обірваний запит."""
        self.put('index.html')
        self.made('ad6d')
        with mock.patch.object(serve.os.path, 'samefile', side_effect=OSError('different drives')):
            st, body = self.post('/api/task-new', {'id': 'ad6d', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad6d'), {'index.html'})

    def test_the_task_folder_must_not_exist_yet(self):
        self.put('index.html')
        existing = self.made('ad7')
        os.makedirs(existing)
        with open(os.path.join(existing, 'mine.txt'), 'w', encoding='utf-8') as f:
            f.write('чужий файл')
        self.refused({'id': 'ad7', 'space': self.p_id, 'from': self.src}, 409, 'task-dir-exists')
        self.assertEqual(os.listdir(existing), ['mine.txt'], 'чужу теку зачеплено')
        self.assertNotIn('ad7', _read(self.p_file)['tasks'])

    def test_too_big_by_files_and_by_bytes(self):
        self.put('index.html', b'12345')
        self.put('a.css', b'12345')
        self.put('b.css', b'12345')
        with mock.patch.object(serve, 'ADOPT_MAX_FILES', 2):
            body = self.refused({'id': 'ad8', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        self.assertEqual(body['files'], 3)
        with mock.patch.object(serve, 'ADOPT_MAX_BYTES', 9):
            body = self.refused({'id': 'ad8', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        self.assertGreater(body['bytes'], 9)
        self.assert_nothing('ad8')

    def test_a_bad_task_id_is_refused_before_any_scan(self):
        self.put('index.html')
        with mock.patch.object(serve, 'adopt_scan', side_effect=AssertionError('обхід до перевірки id')):
            self.refused({'id': 'bad id', 'space': self.p_id, 'from': self.src}, 400, 'bad-task-id')

    def test_a_failure_mid_copy_leaves_nothing(self):
        self.put('index.html')
        self.put('a.css')
        self.put('b.css')
        real = shutil.copy2
        calls = []

        def flaky(s, d, *a, **k):
            calls.append(s)
            if len(calls) == 2:
                raise OSError('disk full')
            return real(s, d, *a, **k)

        self.made('ad9')
        with mock.patch.object(serve.shutil, 'copy2', flaky):
            st, body = self.post('/api/task-new', {'id': 'ad9', 'space': self.p_id, 'from': self.src})
        self.assertEqual((st, body['code']), (500, 'task-create-failed'), body)
        self.assert_nothing('ad9')

    # ---------- Ревʼю a8ae345: відмови, відкат, гонки ----------

    def test_a_differently_cased_path_of_the_space_is_still_the_space(self):
        """APFS не розрізняє регістр: `<тека простору>.upper()` — та сама тека, і рядкове порівняння її не бачить."""
        up = self.p_path.upper()
        if not os.path.exists(up):
            self.skipTest('файлова система розрізняє регістр')
        with open(os.path.join(self.p_path, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>space root</h1>')
        self.addCleanup(os.remove, os.path.join(self.p_path, 'index.html'))
        self.refused({'id': 'ad6c', 'space': self.p_id, 'from': up}, 400, 'from-contains-space')
        self.assert_nothing('ad6c')

    def test_a_path_that_cannot_exist_is_not_found_not_a_dropped_connection(self):
        for bad in ('/tmp/x\x00y', '/tmp/\ud800x'):      # NUL і самотній сурогат → ValueError у `realpath`
            with self.subTest(bad=bad):
                self.refused({'id': 'ad4v', 'space': self.p_id, 'from': bad}, 400, 'from-not-found')
        self.assert_nothing('ad4v')

    def test_a_relative_from_is_refused_not_resolved_against_the_server_cwd(self):
        """Сервер — той самий процес, що й тест: `chdir` у теку-джерело робить `.` і імʼя теки РЕАЛЬНИМИ шляхами, тож
        відмова доводить саме вимогу абсолютного шляху, а не те, що такої теки нема."""
        self.put('index.html')
        before = os.getcwd()
        self.addCleanup(os.chdir, before)
        os.chdir(os.path.dirname(self.src))
        for bad in ('.', os.path.basename(self.src), '../' + os.path.basename(os.path.dirname(self.src)) + '/'
                    + os.path.basename(self.src), '~no-such-user-hopefully/x'):
            with self.subTest(bad=bad):
                self.refused({'id': 'ad4r', 'space': self.p_id, 'from': bad}, 400, 'from-not-found')
        self.assert_nothing('ad4r')

    def test_an_unreadable_subfolder_refuses_the_whole_folder(self):
        if os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0):
            self.skipTest('chmod 000 не діє (Windows чи root)')
        self.put('index.html')
        self.put('locked/a.txt')
        locked = os.path.join(self.src, 'locked')
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o755)
        self.refused({'id': 'ad4u', 'space': self.p_id, 'from': self.src}, 400, 'from-not-found')
        self.assert_nothing('ad4u')

    def test_a_directory_named_index_html_is_not_an_index(self):
        os.makedirs(os.path.join(self.src, 'index.html'))
        self.refused({'id': 'ad5d', 'space': self.p_id, 'from': self.src}, 400, 'from-no-index')
        self.assert_nothing('ad5d')

    def test_a_fifo_in_the_source_is_skipped_not_opened(self):
        """`copy2` на fifo блокується назавжди; `isfile` у обході — єдина перепона."""
        if not hasattr(os, 'mkfifo'):
            self.skipTest('нема os.mkfifo')
        self.put('index.html')
        os.mkfifo(os.path.join(self.src, 'pipe'))
        self.made('ad5f')
        st, body = self.post('/api/task-new', {'id': 'ad5f', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad5f'), {'index.html'})
        self.assertEqual(body['copied'], {'files': 1, 'bytes': 1, 'skipped_links': 0})

    def test_a_dangling_symlink_is_counted_as_a_skipped_link(self):
        self.put('index.html')
        os.symlink(os.path.join(self.tmp, 'no-such-target'), os.path.join(self.src, 'dangling.txt'))
        self.made('ad5l')
        st, body = self.post('/api/task-new', {'id': 'ad5l', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad5l'), {'index.html'})
        self.assertEqual(body['copied']['skipped_links'], 1)

    def test_the_limits_are_inclusive(self):
        """Рівно ліміт — приймаємо, на одиницю більше — відмова (`>`, не `>=`)."""
        self.put('index.html', b'12345')
        self.put('a.css', b'1234')
        self.made('ad8b')
        with mock.patch.object(serve, 'ADOPT_MAX_BYTES', 9), mock.patch.object(serve, 'ADOPT_MAX_FILES', 2):
            st, body = self.post('/api/task-new', {'id': 'ad8b', 'space': self.p_id, 'from': self.src})
            self.assertEqual((st, body['copied']['files'], body['copied']['bytes']), (200, 2, 9), body)
        self.made('ad8c')
        with mock.patch.object(serve, 'ADOPT_MAX_BYTES', 8):
            self.refused({'id': 'ad8c', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        with mock.patch.object(serve, 'ADOPT_MAX_FILES', 1):
            self.refused({'id': 'ad8c', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        self.assert_nothing('ad8c')

    def test_copied_files_get_a_fresh_mtime(self):
        """`copy2` зберігає mtime джерела; свіжа задача зі старою датою збрехала б у `_last_changed` і в «Задачах»."""
        old = 946684800                               # 01.01.2000
        for rel in ('index.html', 'img/a.png'):
            os.utime(self.put(rel), (old, old))
        self.made('ad12')
        st, body = self.post('/api/task-new', {'id': 'ad12', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        it1 = os.path.join(self.p_path, 'ad12', 'iterations', 'it1')
        for rel in ('index.html', os.path.join('img', 'a.png')):
            self.assertGreater(os.path.getmtime(os.path.join(it1, rel)), time.time() - 300, rel)

    def test_a_failure_after_the_copy_still_leaves_nothing_and_a_retry_works(self):
        """Не лише `adopt_copy`: збій запису реєстру теж прибирає теку, інакше повтор отримав би `task-dir-exists`."""
        self.put('index.html')
        self.made('ad10')
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, body = self.post('/api/task-new', {'id': 'ad10', 'space': self.p_id, 'from': self.src})
        self.assertEqual((st, body['code']), (500, 'task-create-failed'), body)
        self.assert_nothing('ad10')
        st, body = self.post('/api/task-new', {'id': 'ad10', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)

    def test_a_folder_that_appears_after_the_check_is_not_touched(self):
        """Гонка: другий запит створив теку між перевіркою `lexists` і записом. Теку займає `makedirs` БЕЗ
        `exist_ok` — відмова `409`, і прибирання не зачіпає чужу теку."""
        self.put('index.html')
        tdir = self.made('ad11')
        real_scan = serve.adopt_scan

        def scan_then_lose_the_race(src):
            out = real_scan(src)
            os.makedirs(tdir)
            with open(os.path.join(tdir, 'mine.txt'), 'w', encoding='utf-8') as f:
                f.write('чужий файл')
            return out

        with mock.patch.object(serve, 'adopt_scan', scan_then_lose_the_race):
            self.refused({'id': 'ad11', 'space': self.p_id, 'from': self.src}, 409, 'task-dir-exists')
        self.assertEqual(os.listdir(tdir), ['mine.txt'], 'чужу теку зачеплено')
        self.assertNotIn('ad11', _read(self.p_file)['tasks'])

    def test_a_subfolder_swapped_for_a_link_after_the_scan_is_not_followed(self):
        """TOCTOU: обхід бачив звичайну підтеку, а до копії її підмінили на посилання назовні."""
        self.put('index.html')
        self.put('sub/a.txt', b'inside')
        secret = os.path.join(self.tmp, 'secret-dir')
        os.makedirs(secret, exist_ok=True)
        self.addCleanup(shutil.rmtree, secret, True)
        with open(os.path.join(secret, 'a.txt'), 'w', encoding='utf-8') as f:
            f.write('SECRET-OUTSIDE')
        real_scan = serve.adopt_scan

        def scan_then_swap(src):
            out = real_scan(src)
            shutil.rmtree(os.path.join(src, 'sub'))
            os.symlink(secret, os.path.join(src, 'sub'))
            return out

        self.made('ad13')
        with mock.patch.object(serve, 'adopt_scan', scan_then_swap):
            st, body = self.post('/api/task-new', {'id': 'ad13', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad13'), {'index.html'}, 'вміст посилання назовні скопійовано')
        self.assertEqual(body['copied'], {'files': 1, 'bytes': 1, 'skipped_links': 1},
                         'відповідь мусить казати, що скопійовано насправді, а не що бачив обхід')


class AdoptCopy(unittest.TestCase):
    """`adopt_copy` без сервера: що між обходом і копією змінили на диску."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='adopt-copy-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, 'src')
        self.dst = os.path.join(self.tmp, 'dst')
        os.makedirs(os.path.join(self.src, 'sub', 'deep'))
        for rel, data in (('index.html', 'x'), ('sub/a.txt', 'inside'), ('sub/deep/b.txt', 'deeper')):
            with open(os.path.join(self.src, rel), 'w', encoding='utf-8') as f:
                f.write(data)
        self.outside = os.path.join(self.tmp, 'outside')
        os.makedirs(os.path.join(self.outside, 'deep'))
        for rel in ('a.txt', 'deep/b.txt'):
            with open(os.path.join(self.outside, rel), 'w', encoding='utf-8') as f:
                f.write('SECRET-OUTSIDE')

    def test_a_plain_copy_reports_what_it_copied(self):
        files, total, links = serve.adopt_scan(self.src)
        self.assertEqual(serve.adopt_copy(self.src, self.dst, files), (3, total, 0))
        self.assertEqual(total, len('x') + len('inside') + len('deeper'))

    def test_a_subfolder_swapped_for_a_link_is_skipped_and_counted(self):
        files, _, _ = serve.adopt_scan(self.src)
        shutil.rmtree(os.path.join(self.src, 'sub'))
        os.symlink(self.outside, os.path.join(self.src, 'sub'))
        self.assertEqual(serve.adopt_copy(self.src, self.dst, files), (1, 1, 2))
        self.assertFalse(os.path.lexists(os.path.join(self.dst, 'sub')))

    def test_a_deeper_component_swapped_for_a_link_is_skipped_too(self):
        files, _, _ = serve.adopt_scan(self.src)
        shutil.rmtree(os.path.join(self.src, 'sub', 'deep'))
        os.symlink(os.path.join(self.outside, 'deep'), os.path.join(self.src, 'sub', 'deep'))
        self.assertEqual(serve.adopt_copy(self.src, self.dst, files), (2, len('x') + len('inside'), 1))
        self.assertFalse(os.path.lexists(os.path.join(self.dst, 'sub', 'deep', 'b.txt')))

    def test_a_file_swapped_for_a_link_is_skipped_and_counted(self):
        files, _, _ = serve.adopt_scan(self.src)
        os.remove(os.path.join(self.src, 'sub', 'a.txt'))
        os.symlink(os.path.join(self.outside, 'a.txt'), os.path.join(self.src, 'sub', 'a.txt'))
        self.assertEqual(serve.adopt_copy(self.src, self.dst, files), (2, len('x') + len('deeper'), 1))
        self.assertFalse(os.path.lexists(os.path.join(self.dst, 'sub', 'a.txt')))


if __name__ == '__main__':
    unittest.main()

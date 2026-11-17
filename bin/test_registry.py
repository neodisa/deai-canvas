#!/usr/bin/env python3
"""Тесты реестра задач (bin/registry.py) — чистая логика, без сети и без git."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as rg  # noqa: E402

_ISO = {}
_REAL_GITSYNC_SETTING = rg._gitsync_setting      # справжня функція — для тестів самого шлюзу


def setUpModule():
    """Жоден тест цього файла не бачить живого tasks.json дерева, змінних реєстру і справжнього ~/.deai."""
    tmp = tempfile.mkdtemp(prefix='reg-test-')
    _ISO['tmp'] = tmp
    _ISO['patches'] = [
        mock.patch.object(rg, 'TASKS_PATH', os.path.join(tmp, 'absent-tasks.json')),
        mock.patch.dict(os.environ, {}, clear=False),
        # Захисно: жоден тест, що явно не задав налаштування git-sync, не читає справжній ~/.deai
        mock.patch.object(rg, '_gitsync_setting', lambda name: None),
    ]
    for p in _ISO['patches']:
        p.start()
    for k in ('DEAI_REGISTRY_REPO', 'DEAI_REGISTRY_SSH_KEY', 'DEAI_HOME', 'DC_TASKS_FILE'):
        os.environ.pop(k, None)


def tearDownModule():
    for p in reversed(_ISO.get('patches', [])):
        p.stop()
    shutil.rmtree(_ISO.get('tmp', ''), ignore_errors=True)


def stamp(hours_ago):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - hours_ago * 3600))


class TestEntryFromTask(unittest.TestCase):
    def test_keeps_only_shared_fields(self):
        task = {'title': 'LIGA-1 · X', 'jira': 'LIGA-1', 'profile': 'seo',
                'gitlab': {'repo': 'git@h:g/r.git', 'path': 'mockup/x'},
                'dir': '/Users/someone/design-work/x',          # машинное
                'live': 'http://localhost:4317/x/index.html'}   # машинное
        e = rg.entry_from_task('x', task)
        self.assertEqual(e['id'], 'x')
        self.assertEqual(e['schema'], 1)
        self.assertEqual(e['profile'], 'seo')
        self.assertEqual(e['gitlab']['path'], 'mockup/x')
        # машинное наверх не уезжает — у коллеги эти пути ведут в никуда
        self.assertNotIn('dir', e)
        self.assertNotIn('live', e)
        self.assertIn('updated_at', e)

    def test_tags_are_shared_and_travel_when_non_empty(self):
        """4b-3: мітки задачі їдуть у реєстр — колега на іншій машині бачить ті самі. Порожній список — як і будь-яке
        порожнє переносиме поле — у запис не йде."""
        self.assertIn('tags', rg.SHARED)
        e = rg.entry_from_task('x', {'title': 'X', 'tags': ['alpha', 'beta']})
        self.assertEqual(e['tags'], ['alpha', 'beta'])
        self.assertNotIn('tags', rg.entry_from_task('x', {'title': 'X'}), 'ключа нема — і в записі нема')
        self.assertNotIn('tags', rg.entry_from_task('x', {'title': 'X', 'tags': None}))

    def test_an_empty_tag_list_travels_too(self):
        """«Людина прибрала всі мітки» — значення, а не відсутність: без ключа інша машина лишила б свої старі мітки."""
        self.assertEqual(rg.entry_from_task('x', {'title': 'X', 'tags': []})['tags'], [])

    def test_owner_filled_from_identity(self):
        real = rg._identity
        rg._identity = lambda: ('Тест Дизайнер', 'test@example.com')
        try:
            e = rg.entry_from_task('x', {'title': 'X', 'profile': 'seo'})
        finally:
            rg._identity = real
        self.assertEqual(e['owner'], 'Тест Дизайнер')
        self.assertEqual(e['owner_key'], 'test@example.com')

    def test_keep_owner_does_not_steal_authorship(self):
        """Правка чужой задачи не переписывает владельца на себя."""
        real = rg._identity
        rg._identity = lambda: ('Хтось Інший', 'other@example.com')
        try:
            e = rg.entry_from_task('x', {'title': 'X', 'profile': 'seo'},
                                   keep_owner=('Перший Автор', 'first@example.com'))
        finally:
            rg._identity = real
        self.assertEqual(e['owner'], 'Перший Автор')
        self.assertEqual(e['owner_key'], 'first@example.com')

    def test_identity_absent_leaves_owner_empty(self):
        real = rg._identity
        rg._identity = lambda: (None, None)
        try:
            e = rg.entry_from_task('x', {'title': 'X'})
        finally:
            rg._identity = real
        self.assertNotIn('owner', e)


class TestSyncAge(unittest.TestCase):
    def test_utc_stamp_not_shifted_by_local_timezone(self):
        """Метка в UTC: timegm, а не mktime — иначе возраст врёт на офсет/DST."""
        self.assertAlmostEqual(rg.sync_age_h({'registry': {'synced_at': stamp(2)}}), 2.0, places=1)
        self.assertAlmostEqual(rg.sync_age_h({'registry': {'synced_at': stamp(0)}}), 0.0, places=2)

    def test_never_synced(self):
        self.assertIsNone(rg.sync_age_h({}))
        self.assertIsNone(rg.sync_age_h({'registry': {}}))

    def test_garbage_stamp_is_none_not_crash(self):
        self.assertIsNone(rg.sync_age_h({'registry': {'synced_at': 'коли-небудь'}}))

    def test_future_stamp_clamped_to_zero(self):
        future = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))
        self.assertEqual(rg.sync_age_h({'registry': {'synced_at': future}}), 0.0)


class TestStaleness(unittest.TestCase):
    def setUp(self):
        self._real = rg.remote_head

    def tearDown(self):
        rg.remote_head = self._real

    def test_fresh_within_ttl(self):
        rg.remote_head = lambda cfg: 'same'
        st = rg.staleness({'registry': {'synced_at': stamp(1), 'head': 'same'}})
        self.assertEqual(st['state'], 'fresh')
        self.assertEqual(st['hint'], '')

    def test_stale_beyond_ttl(self):
        rg.remote_head = lambda cfg: 'same'
        st = rg.staleness({'registry': {'synced_at': stamp(rg.TTL_H + 1), 'head': 'same'}})
        self.assertEqual(st['state'], 'stale')

    def test_behind_beats_freshness(self):
        """Коллега что-то зарегистрировал — важнее возраста кеша, даже если он свежий."""
        rg.remote_head = lambda cfg: 'newer'
        st = rg.staleness({'registry': {'synced_at': stamp(0), 'head': 'older'}})
        self.assertEqual(st['state'], 'behind')

    def test_offline_when_remote_unreachable(self):
        rg.remote_head = lambda cfg: None
        st = rg.staleness({'registry': {'synced_at': stamp(0), 'head': 'x'}})
        self.assertEqual(st['state'], 'offline')

    def test_never_when_no_stamp(self):
        rg.remote_head = lambda cfg: None
        st = rg.staleness({}, check_remote=False)
        self.assertEqual(st['state'], 'never')

    def test_skip_remote_check(self):
        rg.remote_head = lambda cfg: self.fail('не мусить ходити в мережу')
        st = rg.staleness({'registry': {'synced_at': stamp(0), 'head': 'x'}}, check_remote=False)
        self.assertEqual(st['state'], 'fresh')


class TestReadRegistry(unittest.TestCase):
    def test_reads_by_id_field_and_skips_nonjson(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tdir = os.path.join(d, 'registry', 'tasks')
            os.makedirs(tdir)
            with open(os.path.join(tdir, 'a.json'), 'w', encoding='utf-8') as f:
                json.dump({'id': 'a', 'title': 'A', 'profile': 'seo'}, f)
            with open(os.path.join(tdir, 'README.md'), 'w', encoding='utf-8') as f:
                f.write('не задача')
            reg = rg.read_registry(d)
            self.assertEqual(list(reg), ['a'])
            self.assertEqual(reg['a']['profile'], 'seo')

    def test_missing_dir_is_empty_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rg.read_registry(d), {})


if __name__ == '__main__':
    unittest.main()


class TestSyncDoesNotClobberConcurrentEdits(unittest.TestCase):
    """Синхронізація реєстру не сміє відкотити те, що змінилось ПОКИ вона йшла.

    `cmd_pull` і `push_tasks` читають `tasks.json` НА ПОЧАТКУ, далі роблять
    мережеву роботу (clone/reset/push — секунди), і `save_tasks(cfg)` наприкінці
    кладе на місце СВІЙ знімок. Усе, що змінилось за цей час, зникає мовчки:
    зокрема `current`, тобто перемикання задачі відкочується саме тоді, коли
    людина щойно його зробила. Симптом збиває з пантелику — `/api/iteration-pages`
    віддає порожньо, `/it-assets/<it>/…` дає 404, і виглядає як зламана ітерація,
    а не як перемкнута назад задача (фідбек 31.08.2026).

    ⚠️ Записка називала іншу причину («вкладка /app/ на конекті пушить свій
    current»). Такого пуша в коді немає: `POST /api/task-switch` кличе рівно одне
    місце (`app/app.js`), і воно спрацьовує лише на вибір у дропдауні. Тому
    перевіряється МЕХАНІЗМ, який справді є, а не той, що припускався.
    """

    def setUp(self):
        import json
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix='dc-reg-race-')
        self.file = os.path.join(self.tmp, 'tasks.json')
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'current': 'a', 'tasks': {'a': {'title': 'A'}, 'b': {'title': 'B'}}}, f)
        self._path = rg.TASKS_PATH
        rg.TASKS_PATH = self.file
        # 4d-4a: `pull` → `_work_root` читає реєстр просторів (`DEAI_HOME`) і `~/deai-work` (`HOME`): без підміни тест читав би справжній
        # `~/.deai` розробника (як `_RegistrySandbox`; клас лишається власним — він не мусить мати фікстур `nova`/`courts`)
        from unittest import mock
        env = mock.patch.dict(os.environ, {'HOME': self.tmp, 'DEAI_HOME': os.path.join(self.tmp, 'deai')})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DC_TASKS_FILE', None)

    def tearDown(self):
        import shutil
        rg.TASKS_PATH = self._path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_class_is_sandboxed_from_the_developers_machine(self):
        # (l) `pull` читає реєстр просторів (`DEAI_HOME`) і `~/deai-work` (`HOME`): обидва — тимчасові, а не справжні `~/.deai`/`~`
        self.assertEqual(os.path.realpath(os.environ['HOME']), os.path.realpath(self.tmp))
        self.assertEqual(os.path.realpath(os.environ['DEAI_HOME']), os.path.realpath(os.path.join(self.tmp, 'deai')))
        self.assertNotIn('DC_TASKS_FILE', os.environ)

    def _switch_to_b(self):
        """Те, що робить `POST /api/task-switch` у вікні між читанням і записом."""
        import json
        with open(self.file, encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['current'] = 'b'
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)

    def _fake_git(self, switched):
        class R:
            stdout = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
            stderr = ''
            returncode = 0

        def git(args, cwd, cfg, check=True, timeout=120):
            # Перемикання відбувається ПОСЕРЕД мережевої роботи — рівно так, як
            # у житті: людина тисне задачу в дропдауні, поки йде синхронізація.
            if not switched:
                switched.append(True)
                self._switch_to_b()
            return R()
        return git

    def test_pull_keeps_task_switched_during_the_run(self):
        import json
        from unittest import mock
        switched = []
        with mock.patch.object(rg, 'ensure_clone', lambda cfg, **kw: self.tmp), \
             mock.patch.object(rg, '_git', self._fake_git(switched)), \
             mock.patch.object(rg, 'read_registry', lambda d: {'a': {'title': 'A'}}):
            rg.cmd_pull(None)
        self.assertTrue(switched, 'фікстура не перемикала задачу — тест вакуумний')
        with open(self.file, encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertEqual(cfg['current'], 'b', 'pull відкотив перемикання задачі')
        # І свою роботу pull усе-таки зробив.
        self.assertIn('registry', cfg)

    def test_push_keeps_task_switched_during_the_run(self):
        import json
        from unittest import mock
        switched = []
        with mock.patch.object(rg, 'ensure_clone', lambda cfg, **kw: self.tmp), \
             mock.patch.object(rg, '_git', self._fake_git(switched)):
            rg.push_tasks(['a'])
        self.assertTrue(switched, 'фікстура не перемикала задачу — тест вакуумний')
        with open(self.file, encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertEqual(cfg['current'], 'b', 'push відкотив перемикання задачі')
        self.assertIn('registry', cfg)


# ---------- Фікстура тесту не сміє стати спільним станом (інцидент `nova`) ----------

#: Дослівно запис із гілки `registry` (перевірено 27.09.2026 читанням клону).
NOVA_REG = {
    'schema': 1, 'id': 'nova', 'title': 'Нова', 'profile': 'united',
    'gitlab': {'repo': '/var/folders/pn/lqccppvd47s08wdtnyhh0rkr0000gp/T/'
                       'dc-syncverify-slc0axws/origin.git',
               'path': 'mockup/t1'},
    'owner': 'Designer One', 'updated_at': '2026-09-15T10:50:29Z'}
COURTS = {'title': 'Суди', 'profile': 'united',
          'gitlab': {'repo': 'git@gitlab.internal.example:ORG/united-design.git',
                     'path': 'mockup/courts'},
          'dir': '/Users/someone/design-work/courts'}


class TestFixturePathReason(unittest.TestCase):
    """Одне джерело правди «ця задача — фікстура тесту» для пуша, pull,
    дашборда й доктора. Порівняння — по МЕЖІ компонента шляху."""

    def test_nova_incident_is_fixture(self):
        why = rg.fixture_path_reason(NOVA_REG)
        self.assertIsNotNone(why, 'саме цей запис протік у спільний реєстр')
        self.assertIn('gitlab.repo', why)

    def test_task_dir_in_tempfile_is_fixture(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='dc-syncverify-') as d:
            why = rg.fixture_path_reason({'title': 'Нова', 'dir': os.path.join(d, 'nova')})
        self.assertIsNotNone(why)
        self.assertIn('dir', why)

    def test_system_tmp_roots(self):
        for p in ('/tmp/x/nova', '/private/tmp/x', '/var/folders/ab/T/x',
                  '/private/var/folders/ab/T/x', '/tmp'):
            self.assertIsNotNone(rg.fixture_path_reason({'dir': p}), p)

    def test_file_url_repo_is_local_path(self):
        self.assertIsNotNone(rg.fixture_path_reason(
            {'gitlab': {'repo': 'file:///tmp/dc-x/origin.git'}}))

    def test_component_boundary_not_substring(self):
        """Підрядок назвав би фікстурою справжню задачу — і пуш її відмовив би."""
        for p in ('/tmpfoo/x', '/var/folders-archive/x', '/private/tmpx/y',
                  '/Users/someone/tmp/x', '/Users/someone/var/folders/x'):
            self.assertIsNone(rg.fixture_path_reason({'dir': p}), p)

    def test_real_tasks_are_clean(self):
        self.assertIsNone(rg.fixture_path_reason(COURTS))
        self.assertIsNone(rg.fixture_path_reason(
            {'gitlab': {'repo': 'https://gitlab.internal.example/ORG/united-design.git'}}))
        self.assertIsNone(rg.fixture_path_reason({'title': 'X'}))
        self.assertIsNone(rg.fixture_path_reason({'gitlab': 'не словник', 'dir': ''}))
        self.assertIsNone(rg.fixture_path_reason(None))

    def test_custom_tmpdir_is_honoured(self):
        """`$TMPDIR` у CI буває де завгодно — зашитого списку мало."""
        from unittest import mock
        with mock.patch.object(rg.tempfile, 'gettempdir', lambda: '/Volumes/ci-scratch/T'):
            self.assertIsNotNone(rg.fixture_path_reason({'dir': '/Volumes/ci-scratch/T/dc-x/nova'}))
            self.assertIsNone(rg.fixture_path_reason({'dir': '/Volumes/ci-scratch/work/nova'}))

    def test_tmpdir_equal_to_home_does_not_poison_real_tasks(self):
        """`TMPDIR=$HOME` (або `/`) не має зробити фікстурою КОЖНУ задачу."""
        from unittest import mock
        home = os.path.expanduser('~')
        for t in (home, os.path.dirname(home), '/'):
            with mock.patch.object(rg.tempfile, 'gettempdir', lambda t=t: t):
                self.assertIsNone(rg.fixture_path_reason(
                    {'dir': os.path.join(home, 'design-work', 'courts')}), t)

    def test_home_inside_system_tmp_is_not_a_fixture_but_sibling_is(self):
        """`HOME=$(mktemp -d)` (набори на релізі): `/var/folders` накриває весь дім,
        але робота під домом — справжня; фікстура поруч із домом — досі фікстура."""
        from unittest import mock
        h = '/var/folders/zz/abc/T/tmp.HOMEX'
        with mock.patch.dict(os.environ, {'HOME': h}):
            self.assertIsNone(rg.fixture_path_reason({'dir': h + '/design-work/courts'}))
            self.assertIsNotNone(rg.fixture_path_reason({'dir': '/var/folders/zz/abc/T/dc-x/nova'}))

    def test_home_equal_to_temp_root_still_flags_fixtures(self):
        """`HOME=/tmp` (дім ЗБІГАЄТЬСЯ з тимчасовим коренем, а не лежить під ним) не вимикає розпізнавання: `/tmp/dc-x/nova` — досі фікстура."""
        from unittest import mock
        for h in ('/tmp', '/private/tmp', '/var/folders'):
            with mock.patch.dict(os.environ, {'HOME': h}):
                self.assertIsNotNone(rg.fixture_path_reason({'dir': h + '/dc-x/nova'}), h)

    def _linked(self):
        """(справжня тека, симлінк на неї) у tempfile — і вимкнені зашиті корені,
        щоб перевірити саме realpath, а не збіг із `/var/folders`."""
        import tempfile
        from unittest import mock
        base = tempfile.mkdtemp(prefix='dc-link-')
        self.addCleanup(__import__('shutil').rmtree, base, True)
        real = os.path.join(base, 'real')
        os.makedirs(real)
        link = os.path.join(base, 'link')
        os.symlink(real, link)
        p = mock.patch.object(rg, '_TEMP_ROOTS', ())
        p.start()
        self.addCleanup(p.stop)
        return os.path.realpath(real), link

    def test_tmpdir_is_taken_after_realpath(self):
        from unittest import mock
        real, link = self._linked()
        with mock.patch.object(rg.tempfile, 'gettempdir', lambda: link):
            self.assertIsNotNone(rg.fixture_path_reason({'dir': os.path.join(real, 'nova')}))

    def test_task_path_is_taken_after_realpath(self):
        from unittest import mock
        real, link = self._linked()
        with mock.patch.object(rg.tempfile, 'gettempdir', lambda: real):
            self.assertIsNotNone(rg.fixture_path_reason({'dir': os.path.join(link, 'nova')}))


class _RegistrySandbox(unittest.TestCase):
    """Ізольований tasks.json + підмінені clone/git: жодного справжнього реєстру."""

    def setUp(self):
        import json
        import tempfile
        from unittest import mock
        self.tmp = tempfile.mkdtemp(prefix='dc-reg-fixture-')
        self.addCleanup(__import__('shutil').rmtree, self.tmp, True)
        self.file = os.path.join(self.tmp, 'tasks.json')
        self.clone = os.path.join(self.tmp, 'clone')
        os.makedirs(self.clone)
        nova_local = dict(NOVA_REG, dir=os.path.join(self.tmp, 'gone', 'nova'))
        nova_local.pop('schema'), nova_local.pop('id'), nova_local.pop('updated_at')
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'current': 'courts', 'tasks': {'nova': nova_local,
                                                      'courts': dict(COURTS)}}, f)
        self._path = rg.TASKS_PATH
        rg.TASKS_PATH = self.file
        self.addCleanup(setattr, rg, 'TASKS_PATH', self._path)
        self.git_calls = []
        # 4d-4a: `_work_root` читає реєстр просторів (`spaces.read_registry`) і `~/deai-work`: домівка й `DEAI_HOME` — тимчасові,
        # справжні `~/.deai`/`~/deai-work` тут не бачать і не чіпають; реєстру просторів у `DEAI_HOME` нема (читання не пише).
        env = mock.patch.dict(os.environ, {'HOME': self.tmp, 'DEAI_HOME': os.path.join(self.tmp, 'deai')})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DC_TASKS_FILE', None)

        class R:
            stdout = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
            stderr = ''
            returncode = 0

        def git(args, cwd, cfg, check=True, timeout=120):
            self.git_calls.append(list(args))
            return R()
        for name, fake in (('_git', git),
                           ('ensure_clone', lambda cfg, **kw: self.clone),
                           ('_identity', lambda: ('Тест', 't@t'))):
            p = mock.patch.object(rg, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def _registry_files(self):
        tdir = os.path.join(self.clone, 'registry', 'tasks')
        return sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []

    def _quiet(self, fn, *args):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            res = fn(*args)
        return res, out.getvalue(), err.getvalue()


class TestPushRefusesFixtures(_RegistrySandbox):
    """Бар'єр стоїть на САМОМУ пуші: тест, що забув `DC_TASKS_FILE`, більше не
    може зробити свою фікстуру спільним станом (15.09.2026 конфіг НЕ був
    підмінений, тож гвард `serve._registry_push` не спрацював)."""

    def test_push_all_skips_fixture_and_pushes_the_rest(self):
        res, _out, err = self._quiet(rg.push_tasks, None)
        self.assertEqual(list(res), ['courts'])
        self.assertEqual(list(res.refused), ['nova'])
        self.assertEqual(self._registry_files(), ['courts.json'],
                         'фікстура поїхала в спільний реєстр')
        commits = [c for c in self.git_calls if 'commit' in c]
        self.assertEqual(commits[0][-1], 'registry: courts')
        self.assertIn('«nova»', err, 'відмова мусить бути гучною')
        self.assertIn('tasks.json', err, 'і казати, що робити')

    def test_only_fixture_does_not_even_touch_the_clone(self):
        from unittest import mock
        with mock.patch.object(rg, 'ensure_clone',
                               lambda cfg, **kw: self.fail('клон чіпати не можна')):
            res, _out, _err = self._quiet(rg.push_tasks, ['nova'])
        self.assertEqual(list(res), [])
        self.assertIn('nova', res.refused)
        self.assertEqual(self.git_calls, [])

    def test_cmd_push_exit_codes(self):
        import argparse
        rc, out, _err = self._quiet(rg.cmd_push, argparse.Namespace(all=False, id='nova'))
        self.assertEqual(rc, 1, '`push nova` — попросили рівно її, і її не віддали')
        self.assertIn('nova', out)
        rc, out, _err = self._quiet(rg.cmd_push, argparse.Namespace(all=True, id=None))
        self.assertEqual(rc, 0, '`--all`: решта поїхала — це не провал')
        self.assertIn('courts', out)
        self.assertNotIn('nova.json', self._registry_files())


class TestPullSkipsFixtures(_RegistrySandbox):
    """Сміття, що ВЖЕ протекло в реєстр, не розповзається в кеш колег."""

    def _pull(self, registry):
        from unittest import mock
        with mock.patch.object(rg, 'read_registry', lambda d: dict(registry)), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            return self._quiet(rg.cmd_pull, None)

    def _tasks(self):
        import json
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks']

    def test_pull_does_not_cache_registry_fixture(self):
        import json
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {}}, f)
        _rc, out, err = self._pull({'nova': NOVA_REG, 'courts': dict(COURTS, id='courts')})
        self.assertIn('courts', self._tasks(), 'контроль: чиста задача приїхала')
        self.assertNotIn('nova', self._tasks(), 'фікстура з реєстру лягла в кеш')
        self.assertIn('сміття-фікстура: nova', err)
        self.assertIn('registry/tasks/nova.json', err)
        self.assertIn('реєстр підтягнуто: 1 задач', out)

    def test_pull_does_not_advise_pushing_a_fixture(self):
        """Фікстура лише в кеші: порада «віддай push» штовхала б пушити сміття."""
        _rc, out, err = self._pull({'courts': dict(COURTS, id='courts')})
        self.assertNotIn('nova', out, f'порада про фікстуру: {out}')
        self.assertIn('у кеші фікстура: nova', err)


class TestPullSkipsTrash(_RegistrySandbox):
    """Етап Д: задача, видалена на цій машині (запис кошика чи надгробок), не воскресає з реєстру."""

    def _pull(self, registry):
        from unittest import mock
        with mock.patch.object(rg, 'read_registry', lambda d: dict(registry)), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            return self._quiet(rg.cmd_pull, None)

    def _cfg(self):
        import json
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)

    def _write(self, cfg):
        import json
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)

    def test_trashed_and_purged_ids_stay_gone(self):
        cfg = self._cfg()
        cfg['tasks'].pop('courts')
        entry = dict(COURTS)
        cfg['trash'] = {'courts': {'entry': entry, 'dir': None, 'trashDir': None, 'at': '2026-11-17T10:00:00Z'},
                        'dead': {'purged': '2026-11-17T11:00:00Z'}}
        self._write(cfg)
        self._pull({'courts': dict(COURTS, id='courts'), 'dead': dict(COURTS, id='dead', title='Dead')})
        after = self._cfg()
        self.assertNotIn('courts', after['tasks'])
        self.assertNotIn('dead', after['tasks'])
        self.assertEqual(after['trash']['courts']['entry'], entry, 'запис кошика мусить пережити pull цілим')
        self.assertEqual(after['trash']['dead'], {'purged': '2026-11-17T11:00:00Z'}, 'надгробок теж')

    def test_garbage_trash_is_treated_as_empty(self):
        for garbage in ('x', ['courts'], 5, None):
            cfg = self._cfg()
            cfg['tasks'].pop('courts', None)
            cfg['trash'] = garbage
            self._write(cfg)
            self._pull({'courts': dict(COURTS, id='courts')})
            self.assertIn('courts', self._cfg()['tasks'], f'сміттєвий trash {garbage!r} не мусить ховати задачу')

    def test_missing_trash_key_still_pulls(self):
        cfg = self._cfg()
        cfg['tasks'].pop('courts', None)
        cfg.pop('trash', None)
        self._write(cfg)
        self._pull({'courts': dict(COURTS, id='courts')})
        self.assertIn('courts', self._cfg()['tasks'])


class TestTrack(_RegistrySandbox):
    """4d-1: `track` — переносиме поле. 4d-4a: межа `track`/`profile` — одна функція `_track_of_entry`; запис машини на 0.14.0 має
    лише `profile`, і `pull` дописує йому `track`; тека задачі — з ЯВНИХ напрямків простору ЛІГИ (було: `design_work_roots`
    старого файла через адаптер)."""

    def _cfg(self):
        return {'design_work_root': os.path.join(self.tmp, 'shared')}

    def _liga(self, tracks_list=None, default='united'):
        """Простір ЛІГИ реєстру з явними напрямками (`space.json` у тимчасовій теці); `spaces.read_registry` підмінено."""
        import json
        from unittest import mock
        sys.path.insert(0, os.path.join(rg.ROOT, 'app'))
        import spaces
        path = os.path.realpath(os.path.join(self.tmp, 'liga'))
        os.makedirs(path, exist_ok=True)
        tracks_list = [{'id': 'united', 'root': 'united-dir'}, {'id': 'seo', 'root': 'seo-dir'}, {'id': 'plain'}] \
            if tracks_list is None else tracks_list
        with open(os.path.join(path, 'space.json'), 'w', encoding='utf-8') as f:
            json.dump({'tracks': tracks_list, 'default_track': default}, f)
        reg = {'version': 1, 'spaces': [{'id': 'liga', 'name': 'Liga', 'legacy': True, 'path': path}]}
        p = mock.patch.object(spaces, 'read_registry', lambda: reg)
        p.start()
        self.addCleanup(p.stop)
        return path

    def test_track_of_entry_is_the_one_boundary(self):
        for e, want in (({'track': 'seo', 'profile': 'united'}, 'seo'), ({'profile': 'united'}, 'united'),
                        ({'track': 'seo'}, 'seo'), ({'track': '', 'profile': 'united'}, 'united'),
                        ({'track': 5, 'profile': 'united'}, 'united'), ({'track': None, 'profile': 'united'}, 'united'),
                        ({}, None), ({'track': '', 'profile': ''}, None), ({'profile': 5}, None), (None, None),
                        (['united'], None), ('united', None)):
            self.assertEqual(rg._track_of_entry(e), want, repr(e))

    def test_track_travels_in_the_registry_next_to_profile(self):
        self.assertIn('track', rg.SHARED)
        self.assertIn('profile', rg.SHARED, 'колеги на 0.14.0 читають `profile`')
        e = rg.entry_from_task('x', {'title': 'X', 'track': 'seo', 'profile': 'seo'})
        self.assertEqual((e['track'], e['profile']), ('seo', 'seo'))
        self.assertNotIn('track', rg.entry_from_task('x', {'title': 'X'}), 'порожнього напрямку в записі нема')

    def test_work_root_takes_the_track_of_an_entry(self):
        # (г) було `…reads_track_then_profile`: корені з `design_work_roots` старого файла; тепер — `root` явних напрямків
        cfg = self._cfg()
        liga = self._liga()
        seo, united = os.path.join(liga, 'seo-dir'), os.path.join(liga, 'united-dir')
        self.assertEqual(rg._work_root(cfg, {'profile': 'seo'}), seo, 'запис машини на 0.14.0: лише `profile`')
        self.assertEqual(rg._work_root(cfg, {'track': 'seo'}), seo, '⛔ лише `track` не мусить іти в спільний корінь')
        self.assertEqual(rg._work_root(cfg, {'track': 'seo', 'profile': 'united'}), seo, '`track` перемагає')
        self.assertEqual(rg._work_root(cfg, {'track': 'united', 'profile': 'seo'}), united)
        self.assertEqual(rg._work_root(cfg, {'track': 'plain'}), liga, 'напрямок без `root` — тека простору')
        self.assertEqual(rg._work_root(cfg, {'track': 'zzz'}), united, 'невідомий — `root` дефолтного')
        self.assertEqual(rg._work_root(cfg, {}), united, 'без напрямку — `root` дефолтного')

    def test_work_root_without_a_liga_space_is_the_shared_root(self):
        cfg = self._cfg()
        shared = os.path.join(self.tmp, 'shared')
        for task in ({'profile': 'seo'}, {'track': 'seo'}, {}):
            self.assertEqual(rg._work_root(cfg, task), shared, repr(task))          # у `DEAI_HOME` реєстру просторів нема
        self.assertEqual(rg._work_root({}, {'track': 'seo'}), os.path.expanduser('~/deai-work'), 'нема й кореня в cfg')

    def test_work_root_survives_a_broken_spaces_registry_and_says_so_once(self):
        # реєстр просторів не читається (`SpacesError`): `pull` НЕ падає посеред роботи, корінь — спільний, причина вголос раз
        from unittest import mock
        sys.path.insert(0, os.path.join(rg.ROOT, 'app'))
        import spaces
        cfg = self._cfg()
        shared = os.path.join(self.tmp, 'shared')
        self.addCleanup(setattr, rg, '_WORK_ROOT_WARNED', rg._WORK_ROOT_WARNED)
        rg._WORK_ROOT_WARNED = False
        boom = spaces.SpacesError('spaces-unreadable', os.path.join(self.tmp, 'spaces.json'), 'broken')
        with mock.patch.object(spaces, 'read_registry', side_effect=boom):
            res1, _out, err1 = self._quiet(rg._work_root, cfg, {'track': 'seo'})
            res2, _out, err2 = self._quiet(rg._work_root, cfg, {'profile': 'united'})
        self.assertEqual((res1, res2), (shared, shared))
        self.assertIn('spaces-unreadable', err1)
        self.assertEqual(err2, '', 'друге попередження не друкується')

    def test_pull_survives_a_broken_spaces_registry(self):
        import json
        from unittest import mock
        sys.path.insert(0, os.path.join(rg.ROOT, 'app'))
        import spaces
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(dict(self._cfg(), tasks={}), f)
        self.addCleanup(setattr, rg, '_WORK_ROOT_WARNED', rg._WORK_ROOT_WARNED)
        rg._WORK_ROOT_WARNED = False
        reg = {'old': {'schema': 1, 'id': 'old', 'title': 'O', 'profile': 'seo'}}
        with mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
                mock.patch.object(spaces, 'read_registry', side_effect=spaces.SpacesError('spaces-unreadable', 'x')):
            self._quiet(rg.cmd_pull, None)
        with open(self.file, encoding='utf-8') as f:
            task = json.load(f)['tasks']['old']
        self.assertEqual((task['dir'], task['track']), (os.path.join(self.tmp, 'shared', 'old'), 'seo'))

    def test_pull_with_a_really_corrupt_spaces_json_still_saves_state_and_reads_once(self):
        import json
        from unittest import mock
        sys.path.insert(0, os.path.join(rg.ROOT, 'app'))
        import spaces
        os.makedirs(os.environ['DEAI_HOME'])
        with open(os.path.join(os.environ['DEAI_HOME'], 'spaces.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(dict(self._cfg(), tasks={}), f)
        self.addCleanup(setattr, rg, '_WORK_ROOT_WARNED', rg._WORK_ROOT_WARNED)
        rg._WORK_ROOT_WARNED = False
        reg = {'a': {'schema': 1, 'id': 'a', 'title': 'A', 'profile': 'seo'},
               'b': {'schema': 1, 'id': 'b', 'title': 'B', 'track': 'united'}}
        with mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
                mock.patch.object(spaces, 'read_registry', wraps=spaces.read_registry) as rr:
            _res, _out, err = self._quiet(rg.cmd_pull, None)
        self.assertEqual(rr.call_count, 1, 'вигляд збудовано раз на pull, а не на кожну задачу')
        self.assertIn('spaces-unreadable', err)
        with open(self.file, encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertEqual(sorted(cfg['tasks']), ['a', 'b'])
        self.assertEqual(cfg['tasks']['a']['dir'], os.path.join(self.tmp, 'shared', 'a'))
        self.assertIn('registry', cfg, 'стан синхронізації збережено')

    def _pull(self, reg):
        """`cmd_pull` над порожнім локальним файлом: `(tasks, writes)` — що лягло в `tasks.json` і що `pull` передав у
        `_save_registry_state` як «своє» (точковий запис)."""
        import json
        from unittest import mock
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(dict(self._cfg(), tasks={}), f)
        saved = []
        real = rg._save_registry_state
        with mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
                mock.patch.object(rg, '_save_registry_state', lambda w, r: saved.append(w) or real(w, r)):
            self._quiet(rg.cmd_pull, None)
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks'], saved[0]

    def test_pull_gives_a_profile_only_entry_its_track(self):
        # (а) межа: запис реєстру старої машини має лише `profile`; без цього в кеші він не мав би напрямку
        liga = self._liga()
        tasks, writes = self._pull({'old': {'schema': 1, 'id': 'old', 'title': 'O', 'profile': 'seo'}})
        self.assertEqual((tasks['old']['track'], tasks['old']['profile']), ('seo', 'seo'))
        self.assertEqual(writes['old']['track'], 'seo', 'і в точковому записі `pull`, а не лише в памʼяті')
        self.assertEqual(tasks['old']['dir'], os.path.join(liga, 'seo-dir', 'old'))

    def test_pull_track_wins_over_profile(self):
        # (б)
        liga = self._liga()
        tasks, writes = self._pull({'both': {'schema': 1, 'id': 'both', 'title': 'B', 'track': 'seo', 'profile': 'united'},
                                    'new': {'schema': 1, 'id': 'new', 'title': 'N', 'track': 'seo'},
                                    'empty': {'schema': 1, 'id': 'empty', 'title': 'E', 'track': '', 'profile': 'united'},
                                    'none': {'schema': 1, 'id': 'none', 'title': 'X'}})
        self.assertEqual((tasks['both']['track'], tasks['both']['profile']), ('seo', 'united'))
        self.assertEqual(tasks['new']['track'], 'seo')
        self.assertEqual(tasks['empty']['track'], 'united', 'порожній `track` не затуляє `profile`')
        self.assertNotIn('track', tasks['none'], 'нема ні `track`, ні `profile` — напрямку не вигадуємо')
        self.assertNotIn('track', writes['none'])
        self.assertEqual(tasks['both']['dir'], os.path.join(liga, 'seo-dir', 'both'))

    def _pull_over_local_track(self, entry):
        """`pull` одного запису реєстру поверх локальної задачі `x` із `track: plain`: `(tasks, writes)`."""
        import json
        from unittest import mock
        self._liga()
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(dict(self._cfg(), tasks={'x': {'title': 'X', 'track': 'plain', 'dir': os.path.join(self.tmp, 'x')}}), f)
        saved = []
        real = rg._save_registry_state
        with mock.patch.object(rg, 'read_registry', lambda d: {'x': dict({'schema': 1, 'id': 'x', 'title': 'X'}, **entry)}), \
                mock.patch.object(rg, '_save_registry_state', lambda w, r: saved.append(w) or real(w, r)):
            self._quiet(rg.cmd_pull, None)
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks'], saved[0]

    def test_pull_a_profile_only_entry_replaces_a_local_track(self):
        # (m) запис БЕЗ `track` написала стара машина: її `profile` — істина, тож локальний `track` замінюється (раніше: лише коли порожній)
        tasks, writes = self._pull_over_local_track({'profile': 'seo'})
        self.assertEqual((tasks['x']['track'], tasks['x']['profile']), ('seo', 'seo'))
        self.assertEqual(writes['x']['track'], 'seo', 'і в точковому записі `pull`')

    def test_pull_an_entry_with_its_own_track_wins_over_the_local_one(self):
        tasks, writes = self._pull_over_local_track({'track': 'seo', 'profile': 'united'})
        self.assertEqual((tasks['x']['track'], tasks['x']['profile']), ('seo', 'united'))
        self.assertEqual(writes['x']['track'], 'seo')

    def test_pull_keeps_a_local_track_when_the_entry_names_no_direction(self):
        # (було `test_pull_keeps_a_local_track` з записом `profile: seo`: правило (m) його змінило — профіль-only запис тепер ЗАМІНЮЄ)
        tasks, writes = self._pull_over_local_track({})
        self.assertEqual(tasks['x']['track'], 'plain')
        self.assertNotIn('track', writes['x'])
        tasks, _w = self._pull_over_local_track({'profile': 5})
        self.assertEqual(tasks['x']['track'], 'plain', '`profile` не рядок — напрямку нема, локальний лишається')

    def test_pull_view_is_reset_even_after_an_exception(self):
        # (k) `_PULL_VIEW` живе рівно на час `pull`: збій посеред роботи не лишає застарілий вигляд для наступного виклику
        from unittest import mock
        self._liga()
        with open(self.file, 'w', encoding='utf-8') as f:
            f.write('{"tasks": {}}')
        with mock.patch.object(rg, 'read_registry', lambda d: {'a': {'schema': 1, 'id': 'a', 'title': 'A', 'profile': 'seo'}}), \
                mock.patch.object(rg, '_save_registry_state', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self._quiet(rg.cmd_pull, None)
        self.assertIsNone(rg._PULL_VIEW)

    def test_pull_view_is_built_once_per_pull_and_fresh_outside_it(self):
        from unittest import mock
        self._liga()
        calls = []
        real = rg._liga_view
        with mock.patch.object(rg, '_liga_view', lambda: calls.append(1) or real()):
            self._pull({'a': {'schema': 1, 'id': 'a', 'title': 'A', 'profile': 'seo'},
                        'b': {'schema': 1, 'id': 'b', 'title': 'B', 'track': 'united'},
                        'c': {'schema': 1, 'id': 'c', 'title': 'C', 'profile': 'united'}})
            self.assertEqual(len(calls), 1, 'вигляд збудовано раз на pull, а не на кожну задачу')
            self.assertIsNone(rg._PULL_VIEW)
            rg._work_root(self._cfg(), {'track': 'seo'})
            rg._work_root(self._cfg(), {'track': 'seo'})
            self.assertEqual(len(calls), 3, 'поза `pull` — свіжий вигляд на кожен виклик')

    def test_status_shows_no_drift_after_such_a_pull(self):
        # (в) `status` порівнює лише ключі, що є в записі реєстру: допис `track` розбіжності не дає
        from unittest import mock
        self._liga()
        reg = {'old': {'schema': 1, 'id': 'old', 'title': 'O', 'profile': 'seo'},
               'new': {'schema': 1, 'id': 'new', 'title': 'N', 'track': 'seo', 'profile': 'seo'}}
        self._pull(reg)
        with mock.patch.object(rg, 'staleness', lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
                mock.patch.object(rg, 'fixture_path_reason', lambda e: None), \
                mock.patch.object(rg, 'read_registry', lambda d: dict(reg)):       # теки тесту лежать у тимчасовій — не «фікстури»
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertIn('розбіжностей немає', out)
        self.assertNotIn('розійшлися', out)

    def test_status_counts_tracks_from_either_key(self):
        from unittest import mock
        reg = {'a': {'schema': 1, 'id': 'a', 'track': 'seo'}, 'b': {'schema': 1, 'id': 'b', 'profile': 'seo'},
               'c': {'schema': 1, 'id': 'c', 'track': 'mobile', 'profile': 'seo'}, 'd': {'schema': 1, 'id': 'd'}}
        with mock.patch.object(rg, 'staleness', lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
             mock.patch.object(rg, 'read_registry', lambda d: dict(reg)):
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertIn('напрямки: ? 1, mobile 1, seo 2', out)


class TestStatusNamesFixtures(_RegistrySandbox):
    def test_status_names_junk_instead_of_advising_pull(self):
        from unittest import mock
        with mock.patch.object(rg, 'staleness',
                               lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
             mock.patch.object(rg, 'read_registry',
                               lambda d: {'nova': NOVA_REG, 'courts': dict(COURTS, id='courts')}):
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertIn('сміття-фікстура: nova', out)
        self.assertNotIn('немає локально: nova', out)
        self.assertNotIn('розбіжностей немає', out)


# ---------- fb-29092026-d64d35: реєстр не носить МАШИННУ форму адреси ----------
#
# boss-interface: 25.08.2026 ця машина віддала в реєстр `repo: git@10.0.0.7:…`
# (ручний обхід split-DNS до 1.33), 21.09 колега перезаписав на `https://…`.
# Реєстр головніший, тож `pull` розносив обидві форми всім — а SSH-ключ
# налаштований на ІМʼЯ хоста, і fetch/push на IP падали.
IP_REPO = 'git@10.0.0.7:ORG/liga360-design.git'
HTTPS_REPO = 'https://gitlab.internal.example/ORG/liga360-design.git'
SSH_REPO = 'git@gitlab.internal.example:ORG/liga360-design.git'


class TestCanonicalRepo(unittest.TestCase):
    def test_ip_and_https_forms_become_the_ssh_name(self):
        for form in (IP_REPO, HTTPS_REPO, SSH_REPO,
                     'ssh://git@gitlab.internal.example:22/ORG/liga360-design.git',
                     'git@gitlab.internal.example:ORG/liga360-design'):
            self.assertEqual(rg.canonical_repo(form), SSH_REPO, form)

    def test_foreign_host_and_local_path_are_left_alone(self):
        for form in ('git@github.com:x/y.git', '/tmp/origin.git',
                     'file:///tmp/origin.git'):
            self.assertEqual(rg.canonical_repo(form), form)

    def test_same_project_ignores_transport_not_path(self):
        self.assertTrue(rg.same_project(IP_REPO, HTTPS_REPO))
        self.assertFalse(rg.same_project(SSH_REPO,
                                         'git@gitlab.internal.example:ORG/united-design.git'))
        self.assertFalse(rg.same_project(SSH_REPO, 'git@github.com:ORG/liga360-design.git'))


class TestPushSendsProjectNotTransport(unittest.TestCase):
    def test_entry_has_canonical_repo_and_no_machine_keys(self):
        task = {'title': 'Б', 'profile': 'liga360',
                'gitlab': {'repo': IP_REPO, 'path': 'mockup/boss', 'branch': 'main',
                           'ssh_key': '~/.ssh/id_liga', 'host_ip': '10.0.0.7'}}
        gl = rg.entry_from_task('boss', task)['gitlab']
        self.assertEqual(gl, {'repo': SSH_REPO, 'path': 'mockup/boss', 'branch': 'main'})
        self.assertEqual(task['gitlab']['repo'], IP_REPO, 'локальну задачу не чіпаємо')


class TestPullKeepsLocalTransport(_RegistrySandbox):
    def _pull(self, local_gl, reg_gl):
        import json
        from unittest import mock
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {'boss': {'title': 'Б', 'profile': 'liga360',
                                          'dir': os.path.join(self.tmp, 'boss'),
                                          **({'gitlab': local_gl} if local_gl else {})}}}, f)
        reg = {'boss': {'schema': 1, 'id': 'boss', 'title': 'Б', 'profile': 'liga360',
                        'gitlab': reg_gl}}
        with mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            _rc, out, _err = self._quiet(rg.cmd_pull, None)
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks']['boss']['gitlab'], out

    def test_registry_ip_form_does_not_replace_my_working_address(self):
        gl, out = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss', 'branch': 'main',
                              'ssh_key': '~/.ssh/id_liga'},
                             {'repo': IP_REPO, 'path': 'mockup/boss'})
        self.assertEqual(gl['repo'], SSH_REPO, 'IP з реєстру затер робочу адресу')
        self.assertEqual(gl['ssh_key'], '~/.ssh/id_liga', 'машинний ключ загубився')
        self.assertEqual(gl['branch'], 'main')
        self.assertNotIn('оновлено полів', out, 'різниця лише в транспорті — не оновлення')

    def test_old_entry_with_foreign_machine_keys_does_not_take_mine(self):
        """Записи, віддані ДО цього фіксу, могли везти чужий `ssh_key`/`host_ip`."""
        gl, _ = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss', 'ssh_key': '~/.ssh/mine'},
                           {'repo': IP_REPO, 'path': 'mockup/boss',
                            'ssh_key': '/Users/colleague/.ssh/id', 'host_ip': '10.0.0.7'})
        self.assertEqual(gl.get('ssh_key'), '~/.ssh/mine')

    def test_my_non_canonical_form_survives(self):
        """Своя НЕканонічна форма (HTTPS, IP, ssh://…:порт) того самого проєкту —
        лишається. Ревʼю 29.09.2026: коли всі тести мали локально канонічну форму,
        мутація «завжди канонічна з реєстру» жила зеленою."""
        for mine in (HTTPS_REPO, IP_REPO,
                     'ssh://git@gitlab.internal.example:2222/ORG/liga360-design.git'):
            with self.subTest(mine=mine):
                gl, _ = self._pull({'repo': mine, 'path': 'mockup/boss'},
                                   {'repo': SSH_REPO, 'path': 'mockup/boss'})
                self.assertEqual(gl['repo'], mine)

    def test_foreign_machine_keys_do_not_land_where_i_have_none(self):
        """Чужий `ssh_key` на машині без свого дав би `ssh -i <чужий шлях>
        -o IdentitiesOnly=yes` — і той самий клас збою, що boss-interface."""
        gl, _ = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss'},
                           {'repo': IP_REPO, 'path': 'mockup/boss',
                            'ssh_key': '/Users/colleague/.ssh/id', 'host_ip': '10.0.0.7'})
        self.assertNotIn('ssh_key', gl)
        self.assertNotIn('host_ip', gl)

    def test_https_from_colleague_does_not_replace_ssh(self):
        gl, _ = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss'},
                           {'repo': HTTPS_REPO, 'path': 'mockup/boss'})
        self.assertEqual(gl['repo'], SSH_REPO)

    def test_new_machine_gets_canonical_form_not_the_ip(self):
        gl, _ = self._pull(None, {'repo': IP_REPO, 'path': 'mockup/boss'})
        self.assertEqual(gl['repo'], SSH_REPO)

    def test_moved_to_another_project_is_still_taken_from_registry(self):
        """Реєстр головніший у тому, ЯКИЙ проєкт: переїзд задачі мусить доїхати."""
        gl, out = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss'},
                             {'repo': 'git@gitlab.internal.example:ORG/united-design.git',
                              'path': 'mockup/boss'})
        self.assertEqual(gl['repo'], 'git@gitlab.internal.example:ORG/united-design.git')
        self.assertIn('оновлено полів: boss', out)

    def test_path_change_still_arrives(self):
        gl, _ = self._pull({'repo': SSH_REPO, 'path': 'mockup/boss'},
                           {'repo': IP_REPO, 'path': 'mockup/boss-interface'})
        self.assertEqual((gl['repo'], gl['path']), (SSH_REPO, 'mockup/boss-interface'))


class TestPullTags(_RegistrySandbox):
    """Мітки (4b-3) при pull: очищені мітки доїжджають, запис БЕЗ ключа місцевих міток не чіпає."""

    def _pull_tags(self, local, reg_extra):
        import json
        from unittest import mock
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {'boss': {'title': 'Б', 'profile': 'liga360', 'dir': os.path.join(self.tmp, 'boss'),
                                          **({'tags': local} if local is not None else {})}}}, f)
        reg = {'boss': {'schema': 1, 'id': 'boss', 'title': 'Б', 'profile': 'liga360', **reg_extra}}
        with mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            self._quiet(rg.cmd_pull, None)
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks']['boss']

    def test_cleared_tags_reach_a_machine_that_still_has_the_old_ones(self):
        self.assertEqual(self._pull_tags(['a'], {'tags': []})['tags'], [])

    def test_changed_tags_replace_the_local_ones(self):
        self.assertEqual(self._pull_tags(['a'], {'tags': ['b', 'c']})['tags'], ['b', 'c'])

    def test_an_entry_without_the_key_leaves_local_tags_untouched(self):
        self.assertEqual(self._pull_tags(['a'], {})['tags'], ['a'])
        self.assertNotIn('tags', self._pull_tags(None, {}))

    def test_a_fresh_machine_gets_the_cleared_list_not_the_derived_tag(self):
        self.assertEqual(self._pull_tags(None, {'tags': []})['tags'], [])


class TestStatusIgnoresTransport(_RegistrySandbox):
    def test_transport_only_difference_is_not_drift(self):
        import json
        from unittest import mock
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {'boss': {'title': 'Б', 'profile': 'liga360',
                                          'gitlab': {'repo': SSH_REPO, 'path': 'mockup/boss',
                                                     'branch': 'main'}}}}, f)
        reg = {'boss': {'schema': 1, 'id': 'boss', 'title': 'Б', 'profile': 'liga360',
                        'gitlab': {'repo': HTTPS_REPO, 'path': 'mockup/boss'}}}
        with mock.patch.object(rg, 'staleness',
                               lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
             mock.patch.object(rg, 'read_registry', lambda d: dict(reg)):
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertNotIn('розійшлися поля', out, 'status штовхав би робити шкідливий pull')
        self.assertIn('розбіжностей немає', out)


# ---------- Превʼю спільної задачі — у ВЛАСНИКА (рішення власника 29.09.2026) ----------
#
# fb-29092026-69e9c7 + fb-29092026-210ec1: колега віддав boss-interface зі СВОЇМ
# vercel_project/vercel_scope, і перший `pull` власника перемикнув би його
# публікацію в чужу команду. Кожна публікація заміняє деплой цілком — ітерації з
# іншої машини зникали. Тепер прив'язку в реєстрі міняє лише машина власника;
# у решти вона машинна.
OWNER = ('Власник', 'owner@x')
MINE = {'vercel_project': 'pv-11111111', 'vercel_scope': 'team_mine'}
THEIRS = {'vercel_project': 'pv-22222222', 'vercel_scope': 'team_owner'}


class TestVercelBindingBelongsToOwner(_RegistrySandbox):
    """`_identity` у пісочниці — ('Тест', 't@t'): це «я»."""

    def _write_local(self, task):
        import json
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {'boss': task}}, f)

    def _local(self):
        import json
        with open(self.file, encoding='utf-8') as f:
            return json.load(f)['tasks']['boss']

    def _reg_file(self, entry):
        import json
        tdir = os.path.join(self.clone, 'registry', 'tasks')
        os.makedirs(tdir, exist_ok=True)
        with open(os.path.join(tdir, 'boss.json'), 'w', encoding='utf-8') as f:
            json.dump(entry, f)

    def _reg_now(self):
        import json
        with open(os.path.join(self.clone, 'registry', 'tasks', 'boss.json'),
                  encoding='utf-8') as f:
            return json.load(f)

    def _base(self, **kw):
        return {'title': 'Б', 'profile': 'liga360',
                'gitlab': {'repo': SSH_REPO, 'path': 'mockup/boss'}, **kw}

    def test_non_owner_push_keeps_owners_binding(self):
        self._reg_file({'schema': 1, 'id': 'boss', 'owner': OWNER[0], 'owner_key': OWNER[1],
                        **self._base(), **THEIRS})
        self._write_local(self._base(owner=OWNER[0], owner_key=OWNER[1], title='Б2', **MINE))
        self._quiet(rg.push_tasks, ['boss'])
        reg = self._reg_now()
        self.assertEqual((reg['vercel_project'], reg['vercel_scope']),
                         (THEIRS['vercel_project'], THEIRS['vercel_scope']),
                         'не-власник переписав прив\'язку превʼю в реєстрі')
        self.assertEqual(reg['title'], 'Б2', 'решта полів їде як і раніше')
        local = self._local()
        self.assertEqual(local['vercel_project'], MINE['vercel_project'],
                         'push підсунув мені прив\'язку власника в локальний кеш')

    def test_owner_push_writes_own_binding(self):
        self._reg_file({'schema': 1, 'id': 'boss', 'owner': 'Тест', 'owner_key': 't@t',
                        **self._base(), **THEIRS})
        self._write_local(self._base(owner='Тест', owner_key='t@t', **MINE))
        self._quiet(rg.push_tasks, ['boss'])
        self.assertEqual(self._reg_now()['vercel_project'], MINE['vercel_project'])

    def _pull(self, local, reg):
        from unittest import mock
        self._write_local(local)
        with mock.patch.object(rg, 'read_registry', lambda d: {'boss': dict(reg, id='boss')}), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            return self._quiet(rg.cmd_pull, None)

    def test_non_owner_pull_keeps_own_binding(self):
        self._pull(self._base(owner=OWNER[0], owner_key=OWNER[1], **MINE),
                   self._base(owner=OWNER[0], owner_key=OWNER[1], **THEIRS))
        self.assertEqual(self._local()['vercel_project'], MINE['vercel_project'])

    def test_non_owner_without_binding_does_not_take_owners(self):
        """Інакше перша ж публікація не-власника пішла б у проєкт власника (чи в його
        команду) і замінила б його деплой цілком."""
        self._pull(self._base(owner=OWNER[0], owner_key=OWNER[1]),
                   self._base(owner=OWNER[0], owner_key=OWNER[1], **THEIRS))
        self.assertNotIn('vercel_project', self._local())

    def test_owner_second_machine_takes_binding(self):
        self._pull(self._base(owner='Тест', owner_key='t@t'),
                   self._base(owner='Тест', owner_key='t@t', **THEIRS))
        self.assertEqual((self._local()['vercel_project'], self._local().get('vercel_scope')),
                         (THEIRS['vercel_project'], THEIRS['vercel_scope']),
                         'пара взята наполовину — публікація піде без --scope')

    def test_non_owner_push_does_not_seed_empty_registry_binding(self):
        """У реєстрі прив'язки ще немає — не-власник не сміє стати її джерелом."""
        self._reg_file({'schema': 1, 'id': 'boss', 'owner': OWNER[0], 'owner_key': OWNER[1],
                        **self._base()})
        self._write_local(self._base(owner=OWNER[0], owner_key=OWNER[1], title='Б2', **MINE))
        self._quiet(rg.push_tasks, ['boss'])
        reg = self._reg_now()
        self.assertNotIn('vercel_project', reg)
        self.assertNotIn('vercel_scope', reg)

    def test_owner_known_only_from_registry_still_counts(self):
        """Локальна задача ще без `owner_key` (свіжий `task_new`), власник — у реєстрі."""
        self._pull(self._base(), self._base(owner=OWNER[0], owner_key=OWNER[1], **THEIRS))
        self.assertNotIn('vercel_project', self._local(),
                         'власника видно лише в реєстрі, а його пару взяв не-власник')

    def test_owner_is_told_registry_holds_a_foreign_binding(self):
        """Інакше чужа пара в реєстрі (boss-interface 21.09) жила б мовчки, доки
        власник випадково не опублікує."""
        from unittest import mock
        self._write_local(self._base(owner='Тест', owner_key='t@t', **MINE))
        reg = dict(self._base(owner='Тест', owner_key='t@t', **THEIRS), schema=1, id='boss')
        with mock.patch.object(rg, 'staleness',
                               lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
             mock.patch.object(rg, 'read_registry', lambda d: {'boss': reg}):
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertIn('boss', out)
        self.assertIn('push boss', out)

    def test_owner_keeps_local_binding_over_registry(self):
        """Реєстр міг уже встигнути отримати чужу прив'язку (boss-interface, 21.09)."""
        self._pull(self._base(owner='Тест', owner_key='t@t', **MINE),
                   self._base(owner='Тест', owner_key='t@t', **THEIRS))
        self.assertEqual(self._local()['vercel_project'], MINE['vercel_project'])

    def test_status_does_not_advise_pull_for_binding(self):
        from unittest import mock
        self._write_local(self._base(owner=OWNER[0], owner_key=OWNER[1], **MINE))
        reg = dict(self._base(owner=OWNER[0], owner_key=OWNER[1], **THEIRS), schema=1, id='boss')
        with mock.patch.object(rg, 'staleness',
                               lambda cfg: {'state': 'fresh', 'age_h': 0.1, 'hint': ''}), \
             mock.patch.object(rg, 'read_registry', lambda d: {'boss': reg}):
            _rc, out, _err = self._quiet(rg.cmd_status, None)
        self.assertNotIn('розійшлися поля', out)


class TestIdentitySameAsServer(unittest.TestCase):
    """Сервер (`serve.machine_identity`) читає `DC_IDENTITY_*` раніше за git-конфіг;
    реєстр мусить так само — інакше машина без git-конфіга для сервера
    «не-власник», а для реєстру «власник», і її прив'язка їде в реєстр."""

    def test_env_identity_wins(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'}):
            self.assertEqual(rg._identity(), ('Я', 'me@x'))


class TestGitQuotesSshKey(unittest.TestCase):
    """Шлях ключа зі пробілом не має розвалити `GIT_SSH_COMMAND` (див. `shlex.quote` у модулі git-sync)."""

    def test_key_path_with_a_space_is_one_shell_word(self):
        import shlex
        from unittest import mock
        seen = {}

        def fake_run(args, **kw):
            seen['env'] = kw['env']
            return mock.Mock(returncode=0, stdout='', stderr='')
        with mock.patch.object(rg, '_ssh_key', return_value='/tmp/dir with space/id key'), \
                mock.patch.object(rg.subprocess, 'run', fake_run):
            rg._git(['status'], '.', {})
        argv = shlex.split(seen['env']['GIT_SSH_COMMAND'])
        self.assertEqual(argv[:3], ['ssh', '-i', '/tmp/dir with space/id key'])


GOOD_REPO = 'git@gitlab.example.test:ORG/design-office.git'


class TestRegistryConfig(unittest.TestCase):
    """Реєстр налаштовується, а не вшитий: корінь tasks.json, змінні, чесне «не налаштовано»."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='reg-cfg-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tasks = os.path.join(self.tmp, 'tasks.json')
        p = mock.patch.object(rg, 'TASKS_PATH', self.tasks)
        p.start()
        self.addCleanup(p.stop)
        e = mock.patch.dict(os.environ)
        e.start()
        self.addCleanup(e.stop)
        for k in ('DEAI_REGISTRY_REPO', 'DEAI_REGISTRY_SSH_KEY'):
            os.environ.pop(k, None)

    def write(self, data):
        with open(self.tasks, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    # G1
    def test_nothing_configured_is_an_honest_error(self):
        self.write({'tasks': {}})
        self.assertIsNone(rg.registry_repo())
        with self.assertRaises(rg.NotConfigured) as cm:
            rg.require_repo()
        msg = str(cm.exception)
        self.assertIn('registry_repo', msg)
        self.assertIn('DEAI_REGISTRY_REPO', msg)
        self.assertNotIn('internal.example', msg, 'заглушку не показуємо як адресу')

    def test_the_placeholder_itself_counts_as_not_configured(self):
        self.write({'registry_repo': rg.PLACEHOLDER_REPO})
        self.assertIsNone(rg.registry_repo())

    def test_missing_tasks_file_is_not_configured_not_a_crash(self):
        self.assertIsNone(rg.registry_repo())

    def test_root_key_is_used(self):
        self.write({'registry_repo': GOOD_REPO})
        self.assertEqual(rg.registry_repo(), GOOD_REPO)
        self.assertEqual(rg.require_repo(), GOOD_REPO)

    def test_env_beats_the_file(self):
        self.write({'registry_repo': GOOD_REPO})
        os.environ['DEAI_REGISTRY_REPO'] = 'git@other.example.test:G/r.git'
        self.assertEqual(rg.registry_repo(), 'git@other.example.test:G/r.git')

    # G2
    def test_unsafe_forms_are_refused_before_any_git(self):
        for bad in ('-oProxyCommand=touch /tmp/x', '--upload-pack=x', 'ext::sh -c id', 'git@host:', 'http://h/r.git',
                    'a b', 'git@host:p\nq', '\x00', 123,
                    'ssh://a@-oProxyCommand=x/p', 'https://u@-oProxyCommand=x/p', 'ssh://-oProxyCommand=x/p',
                    'https://', 'ssh://-oProxyCommand=x@h/p', 'https://-u@h/p'):
            self.write({'registry_repo': bad})
            self.assertIsNone(rg.registry_repo(), repr(bad))
            with self.assertRaises(rg.NotConfigured) as cm:
                rg.require_repo()
            self.assertIn('registry_repo', str(cm.exception))

    def test_accepted_forms(self):
        for ok in (GOOD_REPO, 'ssh://git@gitlab.example.test/ORG/r.git', 'https://gitlab.example.test/ORG/r.git',
                   'ssh://git@gitlab.example.test:2222/group/sub/r.git', 'https://u_1:p@gitlab.example.test/g/r.git',
                   '/var/tmp/local-bare.git'):
            self.write({'registry_repo': ok})
            self.assertEqual(rg.registry_repo(), ok)

    def test_clone_and_ls_remote_put_dashdash_before_the_address(self):
        self.write({'registry_repo': GOOD_REPO})
        seen = []
        d = os.path.join(self.tmp, 'clone')
        with mock.patch.object(rg, 'clone_dir', return_value=d), \
                mock.patch.object(rg, '_git', side_effect=lambda a, c, cfg, **k: seen.append(a) or mock.Mock(stdout='')):
            rg.ensure_clone({})
            rg.remote_head({})
        clone = next(a for a in seen if a[0] == 'clone')
        self.assertEqual(clone[clone.index(GOOD_REPO) - 1], '--')
        ls = next(a for a in seen if a[0] == 'ls-remote')
        self.assertEqual(ls[ls.index(GOOD_REPO) - 1], '--')

    def test_invalid_repo_gets_its_own_honest_message(self):
        """Задано, але форма непідтримувана — це не «не налаштовано»: людина має побачити, що саме не так."""
        for bad in ('http://gitlab.example.test/r.git', 'git://gitlab.example.test/r.git', 'deploy@gitlab.example.test:x',
                    'git@gitlab.example.test:/abs', 'ssh://a@-oProxyCommand=x/p', 'git@host:p\nq\x1b[31m'):
            self.write({'registry_repo': bad})
            with self.assertRaises(rg.NotConfigured) as cm:
                rg.require_repo()
            msg = str(cm.exception)
            self.assertIn('непідтримувану форму', msg, repr(bad))
            self.assertNotIn('не налаштовано', msg, repr(bad))
            self.assertNotIn('\x1b', msg)
            self.assertNotIn('\n', msg)
            st = rg.staleness({}, check_remote=True)
            self.assertEqual(st['state'], 'offline')
            self.assertIn('непідтримувану форму', st['hint'], repr(bad))
            self.assertNotIn('\x1b', st['hint'])

    def test_cli_prints_the_invalid_form_message(self):
        import io
        self.write({'registry_repo': 'http://gitlab.example.test/r.git'})
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['registry.py', 'pull']):
            with self.assertRaises(SystemExit) as cm:
                rg.main()
        self.assertIn('непідтримувану форму', str(cm.exception.code))
        with mock.patch.object(sys, 'argv', ['registry.py', 'status']), mock.patch.object(sys, 'stdout', out):
            rg.main()
        self.assertIn('непідтримувану форму', out.getvalue())
        self.assertNotIn('не налаштовано', out.getvalue())

    def test_unset_and_placeholder_keep_the_not_configured_message(self):
        self.write({'registry_repo': rg.PLACEHOLDER_REPO})
        with self.assertRaises(rg.NotConfigured) as cm:
            rg.require_repo()
        self.assertIn('не налаштовано', str(cm.exception))

    def test_unconfigured_never_reaches_git(self):
        self.write({'tasks': {}})
        with mock.patch.object(rg, '_git', side_effect=AssertionError('git не мав викликатись')):
            with self.assertRaises(rg.NotConfigured):
                rg.ensure_clone({})
            self.assertIsNone(rg.remote_head({}))

    def test_staleness_says_not_configured(self):
        self.write({'tasks': {}})
        st = rg.staleness({}, check_remote=True)
        self.assertEqual(st['state'], 'offline')
        self.assertIn('не налаштовано', st['hint'])

    # G3
    def test_canonical_host_follows_the_configured_repo(self):
        self.write({'registry_repo': GOOD_REPO})
        self.assertEqual(rg.canonical_repo('git@10.0.0.7:ORG/x.git'), 'git@gitlab.example.test:ORG/x.git')
        self.assertEqual(rg.canonical_repo('https://gitlab.example.test/ORG/x'), 'git@gitlab.example.test:ORG/x.git')
        self.assertTrue(rg.same_project('git@10.0.0.7:ORG/x.git', 'https://gitlab.example.test/ORG/x.git'))

    def test_canonical_host_without_config_is_the_placeholder_host(self):
        self.write({'tasks': {}})
        self.assertEqual(rg.canon_host(), 'gitlab.internal.example')

    # ключ SSH
    def test_ssh_key_order_env_then_root_then_default(self):
        self.write({'registry_ssh_key': '~/.ssh/from_root'})
        self.assertTrue(rg._ssh_key().endswith('/.ssh/from_root'))
        os.environ['DEAI_REGISTRY_SSH_KEY'] = '/keys/from_env'
        self.assertEqual(rg._ssh_key(), '/keys/from_env')
        os.environ.pop('DEAI_REGISTRY_SSH_KEY')
        self.write({'tasks': {}})
        self.assertTrue(rg._ssh_key().endswith('/.ssh/gitlab_ed25519'))

    def test_relative_ssh_key_becomes_absolute(self):
        """Відносний ключ не має залежати від cwd git (clone іде з теки-батька, fetch — із клону)."""
        self.write({'registry_ssh_key': 'keys/id_rel'})
        k = rg._ssh_key()
        self.assertTrue(os.path.isabs(k), k)
        self.assertEqual(k, os.path.abspath('keys/id_rel'))

    def test_gitsync_settings_are_not_read_for_a_temp_tasks_file(self):
        """Шлюз як у `_space_json_allowed`: TASKS_PATH тесту — не простір, справжній git-sync не читаємо."""
        import deai_modules
        import spaces
        home = os.path.join(self.tmp, 'home')
        os.makedirs(home)
        rec = {'git-sync': {'enabled': True, 'settings': {'ssh_key': '/leak/id', 'host_ip': '10.0.0.9'}}}
        reg = {'spaces': [{'legacy': True, 'path': home}]}
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ['DEAI_HOME'] = home                   # шар «увімкнено», як на машині розробника
        self.write({'tasks': {}})
        boom = mock.Mock(side_effect=AssertionError('space.json сусіда прочитано'))
        with mock.patch.object(spaces, 'read_registry', return_value=reg), \
                mock.patch.object(deai_modules, 'space_modules', boom):
            self.assertTrue(spaces.layer_on())
            self.assertIsNone(_REAL_GITSYNC_SETTING('ssh_key'))
            self.assertIsNone(_REAL_GITSYNC_SETTING('host_ip'))
            self.assertFalse(boom.called)
        # і навпаки: коли TASKS_PATH — справжній файл простору, налаштування читаються
        with mock.patch.object(spaces, 'read_registry', return_value=reg), \
                mock.patch.object(deai_modules, 'space_modules', return_value=rec), \
                mock.patch.object(spaces, 'legacy_tasks_file', return_value=self.tasks):
            self.assertEqual(_REAL_GITSYNC_SETTING('ssh_key'), '/leak/id')

    def test_registry_settings_never_read_the_real_deai_home(self):
        """Тимчасовий TASKS_PATH — не простір: space.json сусіда не читаємо (як `cross_check` у pull)."""
        self.write({'tasks': {}})
        self.assertFalse(rg._space_json_allowed())


def _proc(rc=0, out='', err=''):
    return mock.Mock(returncode=rc, stdout=out, stderr=err)


class TestRegistryGitTransport(unittest.TestCase):
    """П13: `_git` не висить без ключа (BatchMode/ConnectTimeout) і обходить split-DNS через `host_ip` модуля git-sync."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='reg-git-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tasks = os.path.join(self.tmp, 'tasks.json')
        with open(self.tasks, 'w', encoding='utf-8') as f:
            json.dump({'registry_repo': GOOD_REPO}, f)
        for p in (mock.patch.object(rg, 'TASKS_PATH', self.tasks), mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        for k in ('DEAI_REGISTRY_REPO', 'DEAI_REGISTRY_SSH_KEY', 'GIT_SSH_COMMAND'):
            os.environ.pop(k, None)

    def _run(self, replies, host_ip='10.0.0.7', args=('ls-remote', '--', GOOD_REPO, 'x')):
        calls = []

        def fake(cmd, **kw):
            calls.append((cmd, kw['env']))
            return replies.pop(0)
        with mock.patch.object(rg.subprocess, 'run', side_effect=fake), \
                mock.patch.object(rg, '_gitsync_setting', side_effect=lambda n: host_ip if n == 'host_ip' else None):
            try:
                r = rg._git(list(args), self.tmp, {}, check=False)
            except OSError as e:
                r = e
        return r, calls

    def test_ssh_command_is_batch_with_connect_timeout(self):
        _, calls = self._run([_proc()])
        ssh = calls[0][1]['GIT_SSH_COMMAND']
        self.assertIn('-o BatchMode=yes', ssh)
        self.assertRegex(ssh, r'-o ConnectTimeout=\d+')
        self.assertEqual(calls[0][0][0:2], ['git', 'ls-remote'], 'без `-c` перед першою спробою')

    def test_resolver_failure_retries_once_via_ip_with_hostkeyalias(self):
        _, calls = self._run([_proc(128, '', 'ssh: Could not resolve hostname gitlab.example.test'), _proc(0, 'ok')])
        self.assertEqual(len(calls), 2)
        cmd, env = calls[1]
        self.assertEqual(cmd[:3], ['git', '-c', 'url.git@10.0.0.7:.insteadOf=git@gitlab.example.test:'])
        self.assertIn('-o HostKeyAlias=gitlab.example.test', env['GIT_SSH_COMMAND'])

    def test_host_key_checking_is_never_disabled(self):
        """И перша спроба, и повтор через IP: `accept-new` + `IdentitiesOnly`, ніколи `StrictHostKeyChecking=no`."""
        _, calls = self._run([_proc(128, '', 'Could not resolve hostname a'), _proc(0, 'ok')])
        self.assertEqual(len(calls), 2)
        for _, env in calls:
            ssh = env['GIT_SSH_COMMAND']
            self.assertIn('StrictHostKeyChecking=accept-new', ssh)
            self.assertIn('IdentitiesOnly=yes', ssh)
            self.assertNotIn('StrictHostKeyChecking=no', ssh)

    def test_other_failures_do_not_retry(self):
        _, calls = self._run([_proc(128, '', 'Permission denied (publickey).')])
        self.assertEqual(len(calls), 1)

    def test_no_host_ip_no_retry(self):
        _, calls = self._run([_proc(128, '', 'Could not resolve hostname x')], host_ip=None)
        self.assertEqual(len(calls), 1)

    def test_garbage_host_ip_is_ignored(self):
        for bad in ('-oProxyCommand=x', 'not an ip', '10.0.0.7 -o x', 7):
            _, calls = self._run([_proc(128, '', 'Could not resolve hostname x')], host_ip=bad)
            self.assertEqual(len(calls), 1, repr(bad))

    def test_non_scp_registry_has_no_ip_retry(self):
        with open(self.tasks, 'w', encoding='utf-8') as f:
            json.dump({'registry_repo': 'https://gitlab.example.test/ORG/r.git'}, f)
        _, calls = self._run([_proc(128, '', 'Could not resolve host: gitlab.example.test')])
        self.assertEqual(len(calls), 1)

    def test_failure_after_retry_raises_when_checked(self):
        replies = [_proc(128, '', 'Could not resolve hostname a'), _proc(128, '', 'still bad')]
        with mock.patch.object(rg.subprocess, 'run', side_effect=lambda *a, **k: replies.pop(0)), \
                mock.patch.object(rg, '_gitsync_setting', side_effect=lambda n: '10.0.0.7' if n == 'host_ip' else None):
            with self.assertRaises(OSError):
                rg._git(['ls-remote', '--', GOOD_REPO], self.tmp, {})


def _git_cli(*a, cwd):
    return __import__('subprocess').run(['git', *a], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


class TestEnsureCloneRepoints(unittest.TestCase):
    """Існуючий клон не лишається на старому origin, коли `registry_repo` змінили (локальні bare-репо, без мережі)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='reg-repoint-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tasks = os.path.join(self.tmp, 'tasks.json')
        self.clone = os.path.join(self.tmp, 'clone')
        self.bares = {}
        for n in ('old', 'new'):
            b = os.path.join(self.tmp, n + '.git')
            _git_cli('init', '--bare', '-b', 'registry', b, cwd=self.tmp)
            w = os.path.join(self.tmp, 'w-' + n)
            _git_cli('clone', '--quiet', b, w, cwd=self.tmp)
            _git_cli('checkout', '-b', 'registry', cwd=w)
            with open(os.path.join(w, 'f.txt'), 'w') as f:
                f.write(n)
            _git_cli('add', 'f.txt', cwd=w)
            _git_cli('-c', 'user.name=t', '-c', 'user.email=t@example.test', 'commit', '-qm', n, cwd=w)
            _git_cli('push', '--quiet', 'origin', 'registry', cwd=w)
            self.bares[n] = b
        for p in (mock.patch.object(rg, 'TASKS_PATH', self.tasks), mock.patch.object(rg, 'clone_dir', lambda: self.clone),
                  mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        for k in ('DEAI_REGISTRY_REPO', 'DEAI_REGISTRY_SSH_KEY', 'GIT_SSH_COMMAND'):
            os.environ.pop(k, None)

    def use(self, repo):
        with open(self.tasks, 'w', encoding='utf-8') as f:
            json.dump({'registry_repo': repo}, f)

    def test_changed_registry_repo_repoints_origin_and_fetches_new_content(self):
        self.use(self.bares['old'])
        rg.ensure_clone({})
        self.assertEqual(_git_cli('config', '--get', 'remote.origin.url', cwd=self.clone), self.bares['old'])
        self.use(self.bares['new'])
        rg.ensure_clone({})
        self.assertEqual(_git_cli('config', '--get', 'remote.origin.url', cwd=self.clone), self.bares['new'])
        self.assertEqual(_git_cli('log', '-1', '--format=%s', 'origin/registry', cwd=self.clone), 'new')

    def test_same_repo_does_not_touch_origin(self):
        self.use(self.bares['old'])
        rg.ensure_clone({})
        seen = []
        real = rg._git
        with mock.patch.object(rg, '_git', side_effect=lambda a, *r, **k: seen.append(a) or real(a, *r, **k)):
            rg.ensure_clone({})
        self.assertFalse([a for a in seen if a[:2] == ['remote', 'set-url']], seen)

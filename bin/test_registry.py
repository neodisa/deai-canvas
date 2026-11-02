#!/usr/bin/env python3
"""Тесты реестра задач (bin/registry.py) — чистая логика, без сети и без git."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as rg  # noqa: E402


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

    def tearDown(self):
        import shutil
        rg.TASKS_PATH = self._path
        shutil.rmtree(self.tmp, ignore_errors=True)

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

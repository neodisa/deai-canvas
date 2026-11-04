"""Сервер екрана «Задачі»: `serve.tasks_overview`, `serve.team_rows`,
`serve.task_thumb_path` і два маршрути `/api/tasks-overview`, `/api/task-thumb`.

Три речі, на яких екран може збрехати, і кожна має свого сторожа нижче:
  * мережа з ізольованого прогону (`team_rows` без `DC_TEAM_FAKE`);
  * кеш рядків дашборда (інакше кожен вхід на екран б'є в Supabase);
  * кадр картки, що вказує за межі теки `shots/` (symlink → чужий файл).
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
import deai_modules as dm  # noqa: E402
import make_before_4c2 as mb2  # noqa: E402  (світ знімка 0.12.0: сервер у процесі, `scrub`)
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules as tm  # noqa: E402  (каркас `Env`: тимчасові HOME/DEAI_HOME, тека модулів-фікстур)
import tracker  # noqa: E402

_REAL = None


def setUpModule():
    """Клас `TrackerOverviewSpaces` створює простори: справжній `~/.deai` стереже знімок на вході й звірка на виході."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


# Справжній urlopen — клієнт тестів, коли тест підміняє `urllib.request.urlopen`
# (глобально, бо сервер живе в своєму потоці), щоб побачити мережу СЕРВЕРА.
_real_urlopen = urllib.request.urlopen

WEBP = b'RIFF\x00\x00\x00\x00WEBPVP8 fake-bytes'


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def make_task(root, tid, its=('it1',), pages=None, publish_url=None):
    """Тека задачі з iterations.json і (за бажання) pages.json ОСТАННЬОЇ ітерації.
    Повертає запис для `tasks.json` (`{'dir': …}`)."""
    d = os.path.join(root, tid)
    _write_json(os.path.join(d, 'iterations.json'), {
        'iterations': [{'id': i, 'date': '01.10.2026 10:00'} for i in its],
        'publish_url': publish_url})
    for i in its:
        idir = os.path.join(d, 'iterations', i)
        os.makedirs(idir, exist_ok=True)
        with open(os.path.join(idir, 'index.html'), 'w') as f:
            f.write('<html></html>')
    if pages is not None:
        _write_json(os.path.join(d, 'iterations', its[-1], 'pages.json'),
                    {'pages': [{'id': p, 'name': p, 'kind': 'page'} for p in pages]})
    return {'dir': d, 'title': tid.upper(), 'jira': 'LIGA-' + tid}


def add_shot(task, it, key, sha='s1', in_manifest=True, write_file=True):
    """Кадр `<key>.webp` у shots/ ітерації + (за бажання) запис у манифесті."""
    sdir = os.path.join(task['dir'], 'iterations', it, 'shots')
    os.makedirs(sdir, exist_ok=True)
    mpath = os.path.join(sdir, 'manifest.json')
    man = {'contract': 'x', 'checkedAt': None, 'shots': {}}
    if os.path.isfile(mpath):
        with open(mpath, encoding='utf-8') as f:
            man = json.load(f)
    if in_manifest:
        man['shots'][key] = {'sha': sha, 'stale': False}
    _write_json(mpath, man)
    if write_file:
        with open(os.path.join(sdir, key + '.webp'), 'wb') as f:
            f.write(WEBP)


def reset_team_cache():
    """4c-1: кеш рядків команди — словник НА ПРОСТІР (`{id: запис}`), тож скидається повністю (колишнє `update(at=0.0, rows=None…)`
    лишило б у словнику чужі ключі `at`/`rows`)."""
    with serve._TEAM_LOCK:
        serve._TEAM_CACHE.clear()


class _NetLog:
    """Записувач шва `_open` вбудованого `supabase-dashboard` (4c-1: читання вкладки «Команда» ЛІГИ ходить крізь нього, а не крізь
    `urllib.request.urlopen`). `calls` — запити (`Request`, тайм-аут); `resp` — що віддати (`Resp`) чи виняток."""

    def __init__(self, resp=None):
        self.calls, self.resp = [], resp

    def __call__(self, req, timeout=None):
        self.calls.append((req, timeout))
        if isinstance(self.resp, BaseException):
            raise self.resp
        return self.resp if self.resp is not None else sbconf.Resp(b'[]')


class _TmpCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='dc-tov-')
        reset_team_cache()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        reset_team_cache()


class TasksOverviewTest(_TmpCase):
    def setUp(self):
        """⛔ Похідна мітка задачі залежить від напрямків простору (4d-1), тож `tasks_overview` може спитати простір запиту, а
        при ввімкненому шарі це читання справжнього реєстру машини. Шар вимкнено: лише `DC_TASKS_FILE`, без `DEAI_HOME` —
        простір неявний (ЛІГА), реєстр не читається й не пишеться."""
        super().setUp()
        p = mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.root, 'no-such-tasks.json')})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()

    def _cfg(self, **tasks):
        return {'current': next(iter(tasks)), 'tasks': tasks}

    def test_mine_is_ordered_by_opened_recent_first(self):
        a = make_task(self.root, 'a')
        b = make_task(self.root, 'b')
        c = make_task(self.root, 'c')
        a['opened'] = '2026-10-01T10:00:00Z'
        b['opened'] = '2026-10-03T10:00:00Z'      # найсвіжіше відкрита
        out = serve.tasks_overview(self._cfg(a=a, b=b, c=c), ([], None))
        self.assertEqual([m['id'] for m in out['mine']], ['b', 'a', 'c'])
        self.assertEqual(out['mine'][0]['opened'], '2026-10-03T10:00:00Z')

    def test_basic_fields_come_from_task_and_state(self):
        t = make_task(self.root, 'a', its=('it1', 'it2'), pages=['home', 'about'],
                      publish_url='https://example.test/p')
        out = serve.tasks_overview(self._cfg(a=t), ([], None))
        m = out['mine'][0]
        self.assertEqual((m['id'], m['jira'], m['title'], m['iter'], m['iterations']),
                         ('a', 'LIGA-a', 'A', 'it2', 2))
        self.assertEqual(m['pages'], 2)
        self.assertEqual(m['published'], 'https://example.test/p')
        self.assertIs(m['missing'], False)

    def test_missing_dir_is_flagged_and_does_not_break(self):
        gone = {'dir': os.path.join(self.root, 'нема-такої'), 'title': 'Зникла'}
        ok = make_task(self.root, 'ok')
        out = serve.tasks_overview(self._cfg(gone=gone, ok=ok), ([], None))
        by = {m['id']: m for m in out['mine']}
        self.assertIs(by['gone']['missing'], True)
        self.assertIs(by['ok']['missing'], False)
        self.assertIsNone(by['gone']['thumb'])
        self.assertIsNone(by['gone']['changed'])
        self.assertIsNone(by['gone']['published'])

    def test_dashboard_row_with_same_id_is_merged(self):
        t = make_task(self.root, 'a')
        other = make_task(self.root, 'b')
        row = {'id': 'a', 'jira_status': 'In Progress', 'jira_status_cat': 'indeterminate',
               'open_comments': 3}
        out = serve.tasks_overview(self._cfg(a=t, b=other), ([row], None))
        by = {m['id']: m for m in out['mine']}
        self.assertEqual((by['a']['jiraStatus'], by['a']['jiraCat'], by['a']['comments']),
                         ('In Progress', 'indeterminate', 3))
        # ⛔ Без рядка дашборда — «невідомо», а не «0 коментарів»: екран не має
        # обіцяти тишу там, де просто немає відповіді
        self.assertEqual((by['b']['jiraStatus'], by['b']['jiraCat'], by['b']['comments']),
                         (None, None, None))

    def test_local_thumb_carries_the_sha_as_cache_key(self):
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'home', sha='abc123')
        out = serve.tasks_overview(self._cfg(a=t), ([], None))
        self.assertEqual(out['mine'][0]['thumb'], '/api/task-thumb?task=a&v=abc123')

    def test_without_local_shot_the_dashboard_thumb_is_used(self):
        t = make_task(self.root, 'a', pages=['home'])
        row = {'id': 'a', 'thumb_url': 'https://cdn.test/a.png'}
        out = serve.tasks_overview(self._cfg(a=t), ([row], None))
        self.assertEqual(out['mine'][0]['thumb'], 'https://cdn.test/a.png')

    def test_local_shot_wins_over_the_dashboard_one_for_mine(self):
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'home', sha='zz9')
        row = {'id': 'a', 'thumb_url': 'https://cdn.test/a.png'}
        out = serve.tasks_overview(self._cfg(a=t), ([row], None))
        self.assertTrue(out['mine'][0]['thumb'].startswith('/api/task-thumb?task=a'))

    def test_task_id_the_thumb_route_would_reject_gets_no_local_thumb(self):
        """Маршрут відповів би 400 → на картці зламана картинка. Краще чесний фолбек."""
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'home', sha='abc')
        row = {'id': 'a b', 'thumb_url': 'https://cdn.test/ab.png'}
        out = serve.tasks_overview(self._cfg(**{'a b': t}), ([row], None))
        self.assertEqual(out['mine'][0]['thumb'], 'https://cdn.test/ab.png')

    def test_no_thumb_anywhere_is_none(self):
        t = make_task(self.root, 'a', pages=['home'])
        out = serve.tasks_overview(self._cfg(a=t), ([], None))
        self.assertIsNone(out['mine'][0]['thumb'])

    def test_changed_is_mtime_of_the_last_iteration(self):
        t = make_task(self.root, 'a', its=('it1', 'it2'))
        stamp = 1_700_000_000
        for dp, _, names in os.walk(os.path.join(t['dir'], 'iterations', 'it2')):
            for n in names:
                os.utime(os.path.join(dp, n), (stamp, stamp))
        # стара ітерація свіжіша — але вона не остання, тож не рахується
        os.utime(os.path.join(t['dir'], 'iterations', 'it1', 'index.html'))
        out = serve.tasks_overview(self._cfg(a=t), ([], None))
        self.assertEqual(out['mine'][0]['changed'], stamp)

    def test_team_rows_are_mapped_and_mine_flag_follows_local_ids(self):
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'home', sha='abc')
        rows = [
            {'id': 'a', 'name': 'Моя', 'jira': 'LIGA-1', 'jira_status': 'Done',
             'jira_status_cat': 'done', 'open_comments': None, 'thumb_url': None,
             'code_url': 'https://p.test/a', 'updated_at': '2026-10-02T10:00:00Z',
             'designer': 'Ольга', 'iterations': 4, 'pages': 7},
            {'id': 'zz', 'name': 'Чужа', 'open_comments': 2,
             'thumb_url': 'https://cdn.test/zz.png'},
        ]
        out = serve.tasks_overview(self._cfg(a=t), (rows, None), now=1234.5)
        mine_row, foreign = out['team']['rows']
        self.assertIs(mine_row['mine'], True)
        self.assertIs(foreign['mine'], False)
        self.assertEqual((mine_row['title'], mine_row['jira'], mine_row['jiraStatus'],
                          mine_row['jiraCat'], mine_row['preview'], mine_row['updated'],
                          mine_row['designer'], mine_row['iterations'], mine_row['pages']),
                         ('Моя', 'LIGA-1', 'Done', 'done', 'https://p.test/a',
                          '2026-10-02T10:00:00Z', 'Ольга', 4, 7))
        self.assertEqual(mine_row['comments'], 0)        # null → 0 для рядків команди
        self.assertEqual(foreign['comments'], 2)
        # своя без thumb_url — локальний кадр, чужа — її thumb_url
        self.assertEqual(mine_row['thumb'], '/api/task-thumb?task=a&v=abc')
        self.assertEqual(foreign['thumb'], 'https://cdn.test/zz.png')
        self.assertIsNone(out['team']['error'])
        self.assertEqual(out['team']['fetchedAt'], 1234.5)

    def test_team_error_passes_through_and_mine_survives(self):
        t = make_task(self.root, 'a')
        out = serve.tasks_overview(self._cfg(a=t), ([], 'нема VPN'))
        self.assertEqual(out['team']['error'], 'нема VPN')
        self.assertEqual(out['team']['rows'], [])
        self.assertEqual([m['id'] for m in out['mine']], ['a'])

    def test_garbage_rows_are_ignored_not_fatal(self):
        t = make_task(self.root, 'a')
        out = serve.tasks_overview(self._cfg(a=t), (['рядок', None, {'id': ['x']}, {'id': 'a'}], None))
        ids = [r['id'] for r in out['team']['rows']]
        self.assertIn('a', ids)


class TeamRowsTest(_TmpCase):
    def setUp(self):
        super().setUp()
        # конфіг Supabase — підставний (4b-2): без нього `_team_fetch` не ходить у мережу, а тут мережу підмінено навмисно
        cfg = mock.patch.object(serve, 'supabase_config', return_value=(sbconf.SB_URL, sbconf.SB_KEY))
        cfg.start()
        self.addCleanup(cfg.stop)

    def _fake(self, rows):
        p = os.path.join(self.root, 'team.json')
        _write_json(p, rows)
        return p

    def test_isolated_run_without_fake_makes_no_network_call(self):
        """⛔ Закон ізоляції: під DC_NO_OVERVIEW/DC_TASKS_FILE шарити мережею не можна."""
        for var in ('DC_NO_OVERVIEW', 'DC_TASKS_FILE'):
            reset_team_cache()
            env = {var: '1'}
            net = _NetLog()
            sbconf.patch_dashboard_open(self, net)      # 4c-1: мережа ЛІГИ — шов `_open` модуля, а не `urlopen`
            with mock.patch.dict(os.environ, env):
                os.environ.pop('DC_TEAM_FAKE', None)
                with mock.patch('urllib.request.urlopen',
                                side_effect=AssertionError('мережа з ізольованого прогону')) as uo:
                    rows, err = serve.team_rows(now=1000.0)
            self.assertEqual(uo.call_count, 0, var)
            self.assertEqual(net.calls, [], var)         # модуль не кликано взагалі: ізоляція стоїть ДО нього
            self.assertEqual(rows, [])
            self.assertTrue(err and isinstance(err, str), var)

    def test_fake_file_is_the_test_seam(self):
        fake = self._fake([{'id': 'a', 'name': 'N'}])
        with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_TEAM_FAKE': fake}):
            rows, err = serve.team_rows(now=1000.0)
        self.assertEqual(rows, [{'id': 'a', 'name': 'N'}])
        self.assertIsNone(err)

    def test_second_call_within_ttl_does_not_reread(self):
        fake = self._fake([{'id': 'a'}])
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            first = serve.team_rows(now=1000.0)
            os.remove(fake)                       # якби перечитало — була б помилка
            second = serve.team_rows(now=1000.0 + serve.TEAM_TTL - 1)
        self.assertEqual(first, ([{'id': 'a'}], None))
        self.assertEqual(second, first)

    def test_cache_expires_after_ttl(self):
        fake = self._fake([{'id': 'a'}])
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            serve.team_rows(now=1000.0)
            self._fake([{'id': 'b'}])
            rows, _ = serve.team_rows(now=1000.0 + serve.TEAM_TTL + 1)
        self.assertEqual(rows, [{'id': 'b'}])

    def test_refresh_bypasses_the_cache(self):
        fake = self._fake([{'id': 'a'}])
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            serve.team_rows(now=1000.0)
            self._fake([{'id': 'b'}])
            cached, _ = serve.team_rows(now=1001.0)
            fresh, _ = serve.team_rows(now=1001.0, refresh=True)
        self.assertEqual(cached, [{'id': 'a'}])
        self.assertEqual(fresh, [{'id': 'b'}])

    def test_error_is_cached_shorter_so_retry_makes_sense(self):
        fake = os.path.join(self.root, 'ще-нема.json')
        self.assertLess(serve.TEAM_ERR_TTL, serve.TEAM_TTL)
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            rows, err = serve.team_rows(now=1000.0)
            self.assertEqual(rows, [])
            self.assertTrue(err)
            _write_json(fake, [{'id': 'a'}])      # база «ожила» на тому ж шляху
            # у вікні помилки — ще кешована помилка, не кожен клік б'є в мережу
            _, err2 = serve.team_rows(now=1000.0 + serve.TEAM_ERR_TTL - 1)
            self.assertEqual(err2, err)
            rows3, err3 = serve.team_rows(now=1000.0 + serve.TEAM_ERR_TTL + 1)
        self.assertEqual((rows3, err3), ([{'id': 'a'}], None))

    def test_failed_refetch_keeps_the_last_good_rows(self):
        """Збій дашборда не стирає останні відомі рядки: вкладка «Команда» показує
        їх із позначкою «дані на <час>», а не порожнечу."""
        fake = self._fake([{'id': 'a'}])
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            serve.team_rows(now=1000.0)
            os.remove(fake)
            t = 1000.0 + serve.TEAM_TTL + 1
            rows, err = serve.team_rows(now=t)
            self.assertEqual(rows, [{'id': 'a'}])
            self.assertTrue(err)
            # у вікні помилки — те саме з кешу, rowsAt лишається часом УСПІХУ
            rows2, err2, rows_at = serve.team_snapshot(now=t + 1)
            self.assertEqual((rows2, err2, rows_at), ([{'id': 'a'}], err, 1000.0))
            # через err-TTL повторна спроба; успіх оновлює rowsAt й знімає помилку
            _write_json(fake, [{'id': 'b'}])
            rows3, err3, rows_at3 = serve.team_snapshot(now=t + serve.TEAM_ERR_TTL + 1)
        self.assertEqual((rows3, err3, rows_at3),
                         ([{'id': 'b'}], None, t + serve.TEAM_ERR_TTL + 1))

    def test_first_ever_failure_has_no_rows_and_no_rows_at(self):
        fake = os.path.join(self.root, 'нема.json')
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}):
            rows, err, rows_at = serve.team_snapshot(now=1000.0)
        self.assertEqual((rows, rows_at), ([], None))
        self.assertTrue(err)

    def test_overview_team_exposes_rows_at_next_to_fetched_at(self):
        out = serve.tasks_overview({'tasks': {}}, ([], None), now=5.0, rows_at=3.0)
        self.assertEqual((out['team']['fetchedAt'], out['team']['rowsAt']), (5.0, 3.0))
        self.assertIsNone(serve.tasks_overview({'tasks': {}}, ([], None))['team']['rowsAt'])

    def test_non_io_error_is_logged_to_stderr_but_still_swallowed(self):
        """Помилку програмування не можна тихо видати за «команда недоступна». 4c-1: «помилка програмування» — збій у САМОМУ
        ядрі (`normalize_rows`); збій у модулі (`KeyError` у `_open`) модуль сам перетворює на `ModuleError` — це не код ядра."""
        with mock.patch.dict(os.environ):
            for var in ('DC_NO_OVERVIEW', 'DC_TASKS_FILE', 'DC_TEAM_FAKE'):
                os.environ.pop(var, None)
            sbconf.patch_dashboard_open(self, _NetLog())
            err = io.StringIO()
            with mock.patch.object(dashboard, 'normalize_rows', side_effect=KeyError('баг')), \
                    contextlib.redirect_stderr(err):
                rows, msg = serve.team_rows(now=1000.0)
            self.assertEqual(rows, [])
            self.assertTrue(msg)
            self.assertIn('KeyError', err.getvalue())
            reset_team_cache()
            quiet = io.StringIO()
            sbconf.patch_dashboard_open(self, _NetLog(OSError('нема VPN')))
            with contextlib.redirect_stderr(quiet):
                rows, msg = serve.team_rows(now=1000.0)
            self.assertEqual(quiet.getvalue(), '')         # звичайна мережа — без шуму
            self.assertTrue(msg)

    def test_never_raises_on_bad_payload(self):
        for payload in ('{"not": "a list"}', 'не json', '"рядок"'):
            reset_team_cache()
            p = os.path.join(self.root, 'bad.json')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(payload)
            with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': p}):
                rows, err = serve.team_rows(now=1000.0)
            self.assertEqual(rows, [], payload)
            self.assertTrue(err, payload)

    def test_network_failure_is_an_error_string_not_an_exception(self):
        reset_team_cache()
        with mock.patch.dict(os.environ, {}, clear=False):
            for var in ('DC_NO_OVERVIEW', 'DC_TASKS_FILE', 'DC_TEAM_FAKE'):
                os.environ.pop(var, None)
            net = _NetLog(OSError('нема VPN'))
            sbconf.patch_dashboard_open(self, net)
            with mock.patch('urllib.request.urlopen', side_effect=AssertionError('серверу більше не кликати urlopen')) as uo:
                rows, err = serve.team_rows(now=1000.0)
        self.assertEqual(uo.call_count, 0)
        self.assertEqual(len(net.calls), 1)
        # 4c-1 (свідома відмінність від 0.11.0): тайм-аут запиту — 4 с модуля (було 3 с), а текст помилки — модуля, а не `OSError`
        self.assertEqual(net.calls[0][1], 4)
        self.assertEqual(net.calls[0][0].full_url.split('?')[0], sbconf.SB_URL + '/rest/v1/overview_projects')
        self.assertEqual((rows, err), ([], 'Supabase недоступний (OSError)'))


class TaskThumbPathTest(_TmpCase):
    def test_picks_the_first_openable_page_with_a_shot(self):
        t = make_task(self.root, 'a', pages=['home', 'about'])
        add_shot(t, 'it1', 'about', sha='sa')
        add_shot(t, 'it1', 'home', sha='sh')
        path, sha = serve.task_thumb_path(t)
        self.assertEqual(sha, 'sh')
        self.assertEqual(os.path.basename(path), 'home.webp')

    def test_skips_a_page_without_a_manifest_entry(self):
        t = make_task(self.root, 'a', pages=['home', 'about'])
        add_shot(t, 'it1', 'home', in_manifest=False)     # файл є, запису нема
        add_shot(t, 'it1', 'about', sha='sa')
        path, sha = serve.task_thumb_path(t)
        self.assertEqual((os.path.basename(path), sha), ('about.webp', 'sa'))

    def test_skips_a_manifest_entry_whose_file_is_gone(self):
        t = make_task(self.root, 'a', pages=['home', 'about'])
        add_shot(t, 'it1', 'home', write_file=False)
        add_shot(t, 'it1', 'about', sha='sa')
        self.assertEqual(os.path.basename(serve.task_thumb_path(t)[0]), 'about.webp')

    def test_falls_back_to_other_manifest_keys_defaults_before_widths(self):
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'poshuk@390', sha='mobile')            # мобільна ширина
        add_shot(t, 'it1', 'poshuk~30d36f19', sha='state')        # стан сторінки
        path, sha = serve.task_thumb_path(t)
        self.assertEqual(sha, 'state')

    def test_page_shot_beats_state_and_width_keys_even_when_listed_first(self):
        t = make_task(self.root, 'a', pages=['home'])
        add_shot(t, 'it1', 'home~30d36f19', sha='state')
        add_shot(t, 'it1', 'home@390', sha='mobile')
        add_shot(t, 'it1', 'home', sha='page')
        self.assertEqual(serve.task_thumb_path(t)[1], 'page')

    def test_only_the_last_iteration_counts(self):
        t = make_task(self.root, 'a', its=('it1', 'it2'), pages=['home'])
        add_shot(t, 'it1', 'home', sha='old')
        self.assertIsNone(serve.task_thumb_path(t))

    def test_symlink_out_of_shots_is_rejected(self):
        """⛔ Ціна помилки — віддача будь-якого файла з диска."""
        secret = os.path.join(self.root, 'secret.webp')
        with open(secret, 'wb') as f:
            f.write(b'SECRET')
        t = make_task(self.root, 'a', pages=['home', 'about'])
        add_shot(t, 'it1', 'home', sha='sh', write_file=False)
        add_shot(t, 'it1', 'about', sha='sa')
        os.symlink(secret, os.path.join(t['dir'], 'iterations', 'it1', 'shots', 'home.webp'))
        path, sha = serve.task_thumb_path(t)
        self.assertEqual((os.path.basename(path), sha), ('about.webp', 'sa'))
        # і коли кандидата-рятівника нема — нічого, а не чужий файл
        os.remove(os.path.join(t['dir'], 'iterations', 'it1', 'shots', 'about.webp'))
        self.assertIsNone(serve.task_thumb_path(t))

    def test_unsafe_manifest_key_is_never_joined_into_a_path(self):
        t = make_task(self.root, 'a', pages=['home'])
        outside = os.path.join(self.root, 'x.webp')
        with open(outside, 'wb') as f:
            f.write(b'X')
        sdir = os.path.join(t['dir'], 'iterations', 'it1', 'shots')
        os.makedirs(sdir)
        _write_json(os.path.join(sdir, 'manifest.json'),
                    {'shots': {'../../../../x': {'sha': 'evil'}}})
        self.assertIsNone(serve.task_thumb_path(t))

    def test_never_raises_on_broken_inputs(self):
        self.assertIsNone(serve.task_thumb_path({}))
        self.assertIsNone(serve.task_thumb_path({'dir': os.path.join(self.root, 'нема')}))
        self.assertIsNone(serve.task_thumb_path(None))
        t = make_task(self.root, 'a', pages=['home'])
        sdir = os.path.join(t['dir'], 'iterations', 'it1', 'shots')
        os.makedirs(sdir)
        with open(os.path.join(sdir, 'manifest.json'), 'w') as f:
            f.write('{зламано')
        self.assertIsNone(serve.task_thumb_path(t))
        with open(os.path.join(sdir, 'manifest.json'), 'w') as f:
            f.write('[1, 2]')
        self.assertIsNone(serve.task_thumb_path(t))


class TasksOverviewHttpTest(unittest.TestCase):
    """Живий сервер: маршрути, статуси, кеш-заголовки."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix='dc-tov-http-')
        cls.alpha = make_task(cls.root, 'alpha', pages=['home'])
        add_shot(cls.alpha, 'it1', 'home', sha='deadbeef')
        cls.alpha['opened'] = '2026-10-03T10:00:00Z'
        cls.beta = make_task(cls.root, 'beta', pages=['home'])   # без кадрів
        cfgdir = tempfile.mkdtemp(prefix='dc-tov-cfg-')
        cls.cfgdir = cfgdir
        cls.tasks_file = os.path.join(cfgdir, 'tasks.json')
        _write_json(cls.tasks_file, {'current': 'alpha',
                                     'tasks': {'alpha': cls.alpha, 'beta': cls.beta}})
        cls.team_file = os.path.join(cfgdir, 'team.json')
        _write_json(cls.team_file, [{'id': 'alpha', 'name': 'A', 'jira_status': 'Done',
                                     'open_comments': 5}])
        os.environ['DC_TASKS_FILE'] = cls.tasks_file
        os.environ['DC_NO_OVERVIEW'] = '1'
        os.environ['DC_TEAM_FAKE'] = cls.team_file
        cls.httpd = serve.make_server(0)
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for var in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE'):
            os.environ.pop(var, None)
        reset_team_cache()
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.cfgdir, ignore_errors=True)

    def setUp(self):
        reset_team_cache()

    def get(self, path):
        """(status, headers, body) без винятку на 4xx."""
        try:
            with _real_urlopen(self.base + path) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers, e.read()

    def test_overview_has_current_mine_team(self):
        status, headers, body = self.get('/api/tasks-overview')
        self.assertEqual(status, 200)
        self.assertIn('application/json', headers['Content-Type'])
        data = json.loads(body)
        self.assertEqual(data['current'], 'alpha')
        self.assertEqual([m['id'] for m in data['mine']], ['alpha', 'beta'])
        self.assertEqual(data['mine'][0]['thumb'], '/api/task-thumb?task=alpha&v=deadbeef')
        self.assertEqual(data['mine'][0]['jiraStatus'], 'Done')
        self.assertEqual(data['mine'][0]['comments'], 5)
        self.assertEqual([r['id'] for r in data['team']['rows']], ['alpha'])
        self.assertIsNone(data['team']['error'])
        self.assertIsInstance(data['team']['rowsAt'], float)   # шов маршруту → відповідь

    def test_overview_refresh_param_bypasses_team_cache(self):
        self.get('/api/tasks-overview')
        _write_json(self.team_file, [{'id': 'alpha', 'name': 'A'}, {'id': 'zz', 'name': 'Z'}])
        try:
            cached = json.loads(self.get('/api/tasks-overview')[2])
            fresh = json.loads(self.get('/api/tasks-overview?refresh=1')[2])
        finally:
            _write_json(self.team_file, [{'id': 'alpha', 'name': 'A', 'jira_status': 'Done',
                                          'open_comments': 5}])
        self.assertEqual(len(cached['team']['rows']), 1)
        self.assertEqual(len(fresh['team']['rows']), 2)

    def test_overview_isolated_without_fake_reports_error_not_500(self):
        # патч глобальний (сервер у своєму потоці) — і мутація «прибрали гвард»
        # не піде в живий Supabase, а лише зачепить лічильник нижче. 4c-1: мережа ЛІГИ — шов `_open` модуля; конфіг підставний,
        # інакше «Supabase не налаштовано» зупинило б запит і без ізоляції (тест був би порожнім).
        net = _NetLog(OSError('мережі нема'))
        sbconf.patch_dashboard_open(self, net)
        with mock.patch.dict(os.environ), \
                mock.patch.object(serve, 'supabase_config', return_value=(sbconf.SB_URL, sbconf.SB_KEY)):
            os.environ.pop('DC_TEAM_FAKE')
            with mock.patch('urllib.request.urlopen', side_effect=OSError('мережі нема')) as uo:
                status, _, body = self.get('/api/tasks-overview')
        self.assertEqual(uo.call_count, 0)
        self.assertEqual(net.calls, [])
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data['team']['rows'], [])
        self.assertTrue(data['team']['error'])
        self.assertEqual(len(data['mine']), 2)

    def test_thumb_serves_webp(self):
        status, headers, body = self.get('/api/task-thumb?task=alpha')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/webp')
        self.assertEqual(body, WEBP)
        self.assertEqual(headers['Content-Length'], str(len(WEBP)))

    def test_thumb_without_version_is_not_cached_forever(self):
        _, headers, _ = self.get('/api/task-thumb?task=alpha')
        self.assertEqual(headers['Cache-Control'], 'no-cache')

    def test_thumb_with_version_is_immutable(self):
        _, headers, _ = self.get('/api/task-thumb?task=alpha&v=deadbeef')
        cc = headers['Cache-Control']
        self.assertEqual(cc, 'private, max-age=31536000, immutable')

    def test_thumb_with_a_stale_version_is_not_immutable(self):
        """⛔ Вічний кеш лише під СВОЇМ sha: інакше новий кадр застряг би в браузері
        під старим `v` на рік (перезйомка між оглядом і запитом кадру)."""
        status, headers, body = self.get('/api/task-thumb?task=alpha&v=old-sha')
        self.assertEqual(status, 200)
        self.assertEqual(body, WEBP)                       # віддаємо ПОТОЧНІ байти
        self.assertEqual(headers['Cache-Control'], 'no-cache')

    def test_thumb_bad_id_is_400(self):
        for bad in ('..%2Fx', 'a%2Fb', 'alpha%0A', '', '%00'):
            status, _, _ = self.get('/api/task-thumb?task=' + bad)
            self.assertEqual(status, 400, bad)
        self.assertEqual(self.get('/api/task-thumb')[0], 400)

    def test_thumb_unknown_task_is_404(self):
        self.assertEqual(self.get('/api/task-thumb?task=nope')[0], 404)

    def test_thumb_task_without_shots_is_404(self):
        self.assertEqual(self.get('/api/task-thumb?task=beta')[0], 404)


# ---------- Статуси трекера на екрані «Задачі» (4c-2, Task 5) ----------

BEFORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'tracker', 'before-4c2.json')


def reset_tracker_cache():
    with serve._TRACKER_LOCK:
        serve._TRACKER_CACHE.clear()


def _st(name, cat='done'):
    return {'name': name, 'cat': cat}


class _Prov:
    """Постачальник-заглушка для `tracker_snapshot(resolved=…)`: лише `id` (`who`); сам виклик підмінено `_tracker_fetch`."""

    def __init__(self, mid):
        self.id = mid


class _Fetch:
    """Підміна `serve._tracker_fetch`: рахує виклики (`calls` — списки ключів) і віддає записане по черзі; останнє повторюється."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, space, prov, keys):
        self.calls.append(list(keys))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return a(keys) if callable(a) else a


class _OkResp:
    """Відповідь-заглушка шва `_open` `jira-tracker`: контекстний менеджер із `status` і `read`."""

    def __init__(self, body):
        self._body, self.status = json.dumps(body).encode('utf-8'), 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self._body


class TrackerOverview(_TmpCase):
    """`tasks_overview(…, tracker=…)` (пріоритет джерел), кеш `tracker_snapshot` на простір, шов `DC_TRACKER_FAKE`, ізоляція ЛІГИ
    й диференційний зі знімком 0.12.0. Усе без мережі: `_tracker_fetch` підмінено, а справжній модуль — крізь шов `_open`."""

    def setUp(self):
        super().setUp()
        reset_tracker_cache()
        self.addCleanup(reset_tracker_cache)
        # оточення ізоляції не просочується: кожен тест сам вирішує, чи воно є
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TRACKER_FAKE', 'DC_TEAM_FAKE'):
            os.environ.pop(var, None)
        with open(BEFORE, encoding='utf-8') as fh:
            self.snap = json.load(fh)

    def _cfg(self, **tasks):
        return {'current': next(iter(tasks)), 'tasks': tasks}

    def _snapshot(self, fetch, keys=('DEMO-1',), space='A', prov='legacy', **kw):
        with spaces.request_space(space), mock.patch.object(serve, '_tracker_fetch', fetch):
            return serve.tracker_snapshot(list(keys), resolved=(None, _Prov(prov) if prov != 'legacy' else 'legacy'), **kw)

    # ---- пріоритет у tasks_overview ----

    def test_tracker_status_wins_then_dashboard_row_then_none(self):
        a = make_task(self.root, 'a')
        a['jira'] = 'DEMO-1'
        b = make_task(self.root, 'b')
        b['jira'] = 'DEMO-2'
        c = make_task(self.root, 'c')
        c['jira'] = 'DEMO-3'
        rows = [{'id': 'a', 'jira_status': 'In Review', 'jira_status_cat': 'indeterminate', 'open_comments': 1},
                {'id': 'b', 'jira_status': 'Blocked', 'jira_status_cat': 'new'}]
        out = serve.tasks_overview(self._cfg(a=a, b=b, c=c), (rows, None),
                                   tracker=({'DEMO-1': _st('Done')}, None, 100.0))
        got = {m['id']: (m['jiraStatus'], m['jiraCat']) for m in out['mine']}
        self.assertEqual(got['a'], ('Done', 'done'), 'статус трекера перемагає рядок дашборда')
        self.assertEqual(got['b'], ('Blocked', 'new'), 'трекер мовчить про ключ — рядок дашборда')
        self.assertEqual(got['c'], (None, None), 'ні того, ні того — «невідомо»')
        self.assertEqual(out['tracker'], {'error': None, 'okAt': 100.0})
        self.assertEqual([m['comments'] for m in out['mine'] if m['id'] == 'a'], [1], 'лічильник коментарів — з дашборда')

    def test_a_tracker_status_without_a_category_still_wins_with_a_none_category(self):
        a = make_task(self.root, 'a')
        a['jira'] = 'DEMO-1'
        rows = [{'id': 'a', 'jira_status': 'In Review', 'jira_status_cat': 'indeterminate'}]
        out = serve.tasks_overview(self._cfg(a=a), (rows, None), tracker=({'DEMO-1': _st('Custom', None)}, None, 1.0))
        self.assertEqual((out['mine'][0]['jiraStatus'], out['mine'][0]['jiraCat']), ('Custom', None))

    def test_team_rows_never_get_tracker_statuses(self):
        a = make_task(self.root, 'a')
        a['jira'] = 'DEMO-1'
        rows = [{'id': 'a', 'jira': 'DEMO-1', 'jira_status': 'In Review', 'jira_status_cat': 'indeterminate'},
                {'id': 'x', 'jira': 'DEMO-9', 'jira_status': None}]
        out = serve.tasks_overview(self._cfg(a=a), (rows, None),
                                   tracker=({'DEMO-1': _st('Done'), 'DEMO-9': _st('Done')}, None, 1.0))
        self.assertEqual([(r['id'], r['jiraStatus'], r['jiraCat']) for r in out['team']['rows']],
                         [('a', 'In Review', 'indeterminate'), ('x', None, None)])

    def test_no_tracker_keeps_the_0_12_0_behaviour_and_says_tracker_null(self):
        a = make_task(self.root, 'a')
        a['jira'] = 'DEMO-1'
        rows = [{'id': 'a', 'jira_status': 'In Review', 'jira_status_cat': 'indeterminate'}]
        out = serve.tasks_overview(self._cfg(a=a), (rows, None))
        self.assertIsNone(out['tracker'])
        self.assertEqual((out['mine'][0]['jiraStatus'], out['mine'][0]['jiraCat']), ('In Review', 'indeterminate'))

    def test_a_tracker_error_is_reported_next_to_the_kept_statuses(self):
        a = make_task(self.root, 'a')
        a['jira'] = 'DEMO-1'
        out = serve.tasks_overview(self._cfg(a=a), ([], None), tracker=({'DEMO-1': _st('Done')}, 'Jira недосяжна', 50.0))
        self.assertEqual(out['tracker'], {'error': 'Jira недосяжна', 'okAt': 50.0})
        self.assertEqual(out['mine'][0]['jiraStatus'], 'Done', 'збій не знімає останній відомий статус')

    # ---- диференційний зі знімком 0.12.0 ----

    def test_the_league_overview_is_the_0_12_0_body_plus_tracker_null(self):
        """⛔ Ізоляція (`DC_TASKS_FILE`): трекер ЛІГИ не кличеться — тіло ТЕ САМЕ, що записав знімок, плюс `tracker: null`; модуль
        `jira-tracker` (`_open`) не викликано ні разу."""
        def boom(req, timeout):
            raise AssertionError('мережа: ізольований прогін не ходить у Jira')
        calls = []
        sbconf.patch_open(self, lambda req, timeout: calls.append(req) or boom(req, timeout), 'jira-tracker')
        with mock.patch.object(serve, 'jira_config', side_effect=AssertionError('конфіг Jira з ізольованого прогону')):
            with tempfile.TemporaryDirectory(prefix='dc-tov-diff-') as tmp:
                for var in mb2.CLEAN:
                    os.environ.pop(var, None)
                got = mb2.tasks_overview(tmp)
        reset_team_cache()
        want = self.snap['tasks_overview']
        self.assertEqual(calls, [])
        self.assertEqual(got['status'], 200)
        self.assertEqual(got['body'], {**want['body'], 'tracker': None})
        self.assertEqual(got['volatile'], want['volatile'])
        self.assertEqual(serve._TRACKER_CACHE, {}, 'ізоляція нічого не кешує')

    # ---- шов DC_TRACKER_FAKE і ізоляція ----

    def _fake_file(self, data):
        p = os.path.join(self.root, 'trk-fake.json')
        _write_json(p, data)
        return p

    def test_the_fake_seam_gives_statuses_even_in_isolation_and_keeps_only_asked_keys(self):
        fake = self._fake_file({'DEMO-1': _st('Done'), 'DEMO-2': {'name': '', 'cat': 'done'}, 'DEMO-7': _st('Other'),
                                'DEMO-3': {'name': 'Odd', 'cat': 'weird'}})
        for var in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            reset_tracker_cache()
            with mock.patch.dict(os.environ, {var: '1', 'DC_TRACKER_FAKE': fake}):
                got = serve.tracker_snapshot(['DEMO-1', 'DEMO-2', 'DEMO-3'], now=10.0, resolved=(None, 'legacy'))
            self.assertEqual(got, ({'DEMO-1': _st('Done'), 'DEMO-3': _st('Odd', None)}, None, 10.0), var)

    def test_isolation_without_the_seam_means_no_tracker_and_no_work(self):
        def boom(req, timeout):
            raise AssertionError('мережа')
        sbconf.patch_open(self, boom, 'jira-tracker')
        for var in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            with self.subTest(var=var), mock.patch.dict(os.environ, {var: '1'}), \
                    mock.patch.object(serve, 'jira_config', side_effect=AssertionError('конфіг')):
                self.assertIsNone(serve.tracker_snapshot(['DEMO-1'], now=1.0, resolved=(None, 'legacy')))
                self.assertEqual(serve._TRACKER_CACHE, {})

    def test_a_broken_fake_file_is_an_error_text_not_an_exception(self):
        bad = os.path.join(self.root, 'bad.json')
        with open(bad, 'w', encoding='utf-8') as fh:
            fh.write('не json')
        for payload in (bad, self._fake_file(['не', 'словник']), os.path.join(self.root, 'нема.json')):
            reset_tracker_cache()
            with mock.patch.dict(os.environ, {'DC_TRACKER_FAKE': payload}):
                got = serve.tracker_snapshot(['DEMO-1'], now=1.0, resolved=(None, 'legacy'))
            self.assertEqual((got[0], got[2]), ({}, None), payload)
            self.assertTrue(got[1] and isinstance(got[1], str), payload)

    # ---- ЛІГА без ізоляції: справжній модуль, шов `_open` ----

    def _jira_answer(self, keys_seen):
        def fake_open(req, timeout):
            body = json.loads(req.data.decode('utf-8'))
            keys_seen.append((body['jql'], timeout))
            issues = [{'key': k, 'fields': {'status': {'name': 'In Review', 'statusCategory': {'key': 'indeterminate'}}}}
                      for k in body['jql'][len('key in ('):-1].split(',')]
            return _OkResp({'issues': issues})
        return fake_open

    def test_the_league_asks_jira_through_the_module_with_the_read_budget_and_at_most_100_keys(self):
        seen = []
        sbconf.patch_open(self, self._jira_answer(seen), 'jira-tracker')
        keys = ['DEMO-%d' % i for i in range(1, 121)]
        with mock.patch.object(serve, 'jira_config', return_value=('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1')):
            got = serve.tracker_snapshot(keys, now=5.0, resolved=(None, 'legacy'))
        self.assertEqual(len(seen), 1, 'одним викликом')
        self.assertEqual(seen[0][1], tracker.READ_SOCKET_S)
        self.assertEqual(seen[0][0], 'key in (' + ','.join(keys[:100]) + ')')
        self.assertEqual(sorted(got[0]), sorted(keys[:100]))
        self.assertEqual((got[1], got[2]), (None, 5.0))
        # перші 100 ключів уже в кеші: той самий набір — без повторного запиту, а не «новий ключ» щоразу
        with mock.patch.object(serve, 'jira_config', return_value=('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1')):
            serve.tracker_snapshot(keys, now=6.0, resolved=(None, 'legacy'))
        self.assertEqual(len(seen), 1)

    def test_the_league_without_jira_base_says_so_and_makes_no_network_call(self):
        def boom(req, timeout):
            raise AssertionError('мережа: без конфігу Jira не питається')
        sbconf.patch_open(self, boom, 'jira-tracker')
        with mock.patch.object(serve, 'jira_config', return_value=(None, None, None)):
            got = serve.tracker_snapshot(['DEMO-1'], now=5.0, resolved=(None, 'legacy'))
            nothing = serve.tracker_snapshot([], now=5.0, refresh=True, resolved=(None, 'legacy'))
        self.assertEqual(got, ({}, tracker.UNCONFIGURED, None))
        self.assertEqual(nothing, ({}, None, 5.0), 'нема що питати — нема й плашки')

    def test_junk_keys_are_dropped_before_anything_is_asked(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None))
        got = self._snapshot(f, keys=(None, 5, ['x'], 'DEMO-1', 'DEMO-1'), now=1.0)
        self.assertEqual(f.calls, [['DEMO-1']])
        self.assertEqual(got, ({'DEMO-1': _st('Done')}, None, 1.0))

    def test_an_unexpected_exception_is_an_error_text_with_the_class_only_and_is_logged(self):
        """Не `ModuleError` і не мережа — збій коду ядра: плашка називає лише клас (`str(e)` чужого винятку не чищений і міг би
        винести токен), а stderr отримує назву класу."""
        err = io.StringIO()
        with mock.patch.object(serve, 'jira_config', return_value=('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1')), \
                mock.patch.object(tracker, 'statuses', side_effect=RuntimeError('boom tok-test-1')), \
                contextlib.redirect_stderr(err):
            got = serve.tracker_snapshot(['DEMO-1'], now=1.0, resolved=(None, 'legacy'))
        self.assertEqual(got, ({}, 'RuntimeError', None))
        self.assertIn('RuntimeError', err.getvalue())
        self.assertNotIn('tok-test-1', err.getvalue())

    def test_a_network_error_is_the_class_name_and_stays_quiet_on_stderr(self):
        err = io.StringIO()
        with mock.patch.object(serve, 'jira_config', return_value=('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1')), \
                mock.patch.object(tracker, 'statuses', side_effect=OSError('нема VPN')), contextlib.redirect_stderr(err):
            got = serve.tracker_snapshot(['DEMO-1'], now=1.0, resolved=(None, 'legacy'))
        self.assertEqual(got, ({}, 'OSError', None))
        self.assertEqual(err.getvalue(), '')

    # ---- кеш ----

    def test_a_second_call_within_the_ttl_does_not_ask_again_and_the_ttl_expires(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None))
        first = self._snapshot(f, now=1000.0)
        second = self._snapshot(f, now=1000.0 + serve.TRACKER_TTL - 1)
        self.assertEqual(first, ({'DEMO-1': _st('Done')}, None, 1000.0))
        self.assertEqual(second, first)
        self.assertEqual(len(f.calls), 1)
        self._snapshot(f, now=1000.0 + serve.TRACKER_TTL + 1)
        self.assertEqual(len(f.calls), 2)

    def test_the_ttls_are_the_designed_ones(self):
        self.assertEqual((serve.TRACKER_TTL, serve.TRACKER_ERR_TTL), (300, 30))

    def test_refresh_bypasses_the_cache(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None))
        self._snapshot(f, now=1000.0)
        self._snapshot(f, now=1001.0)
        self.assertEqual(len(f.calls), 1)
        self._snapshot(f, now=1002.0, refresh=True)
        self.assertEqual(len(f.calls), 2)

    def test_a_key_that_was_not_asked_before_is_a_new_request_but_a_subset_is_not(self):
        f = _Fetch(lambda keys: ({k: _st('S ' + k) for k in keys}, None))
        self._snapshot(f, keys=('DEMO-1', 'DEMO-2'), now=1000.0)
        self._snapshot(f, keys=('DEMO-2',), now=1001.0)
        self.assertEqual(len(f.calls), 1, 'підмножина ключів — з кешу')
        got = self._snapshot(f, keys=('DEMO-1', 'DEMO-3'), now=1002.0)
        self.assertEqual(len(f.calls), 2, 'новий ключ — новий запит')
        self.assertEqual(sorted(got[0]), ['DEMO-1', 'DEMO-3'])

    def test_an_error_is_cached_shorter_so_retry_makes_sense(self):
        self.assertLess(serve.TRACKER_ERR_TTL, serve.TRACKER_TTL)
        f = _Fetch(({}, 'down'), ({'DEMO-1': _st('Done')}, None))
        first = self._snapshot(f, now=1000.0)
        self.assertEqual(first, ({}, 'down', None))
        within = self._snapshot(f, now=1000.0 + serve.TRACKER_ERR_TTL - 1)
        self.assertEqual((within, len(f.calls)), (first, 1), 'у вікні помилки мертвий трекер не питаємо')
        after = self._snapshot(f, now=1000.0 + serve.TRACKER_ERR_TTL + 1)
        self.assertEqual(after, ({'DEMO-1': _st('Done')}, None, 1000.0 + serve.TRACKER_ERR_TTL + 1))

    def test_a_failure_after_a_success_keeps_the_last_statuses_and_the_time_of_success(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None), ({}, 'down'))
        self._snapshot(f, now=1000.0)
        t = 1000.0 + serve.TRACKER_TTL + 1
        got = self._snapshot(f, now=t)
        self.assertEqual(got, ({'DEMO-1': _st('Done')}, 'down', 1000.0), 'статуси лишились, okAt — час УСПІХУ')
        again = self._snapshot(f, now=t + 1)
        self.assertEqual(again, got)
        self.assertEqual(len(f.calls), 2)

    def test_the_first_ever_failure_has_no_statuses_and_no_ok_at(self):
        got = self._snapshot(_Fetch(({}, 'down')), now=1000.0)
        self.assertEqual(got, ({}, 'down', None))

    def test_a_new_key_while_the_tracker_is_down_does_not_hammer_it(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None), ({}, 'down'))
        self._snapshot(f, keys=('DEMO-1',), now=1000.0)
        t = 1000.0 + serve.TRACKER_TTL + 1
        self._snapshot(f, keys=('DEMO-1', 'DEMO-2'), now=t)
        self._snapshot(f, keys=('DEMO-1', 'DEMO-2'), now=t + 1)
        self.assertEqual(len(f.calls), 2, 'новий ключ при збої — один запит на вікно помилки')

    def test_a_clock_that_jumped_back_does_not_keep_a_stale_cache_alive(self):
        f = _Fetch(({'DEMO-1': _st('Done')}, None))
        self._snapshot(f, now=5000.0)
        self._snapshot(f, now=1000.0)
        self.assertEqual(len(f.calls), 2)

    def test_another_provider_starts_a_clean_entry(self):
        f = _Fetch(({'DEMO-1': _st('Old')}, None), ({}, 'down'))
        self._snapshot(f, prov='mod-a', now=1000.0)
        got = self._snapshot(f, prov='mod-b', now=1001.0)
        self.assertEqual(len(f.calls), 2, 'інший постачальник — запит, а не кеш попереднього')
        self.assertEqual(got, ({}, 'down', None), 'статуси старого постачальника не стають «останніми відомими» нового')

    def test_the_cache_is_per_space(self):
        f = _Fetch(lambda keys: ({'DEMO-1': _st('Done')}, None), ({}, 'down'))
        a = self._snapshot(f, space='A', now=1000.0)
        b = self._snapshot(f, space='B', now=1001.0)
        self.assertEqual(len(f.calls), 2, 'кеш простору A не видно в B')
        self.assertEqual(a[0], {'DEMO-1': _st('Done')})
        self.assertEqual(b, ({}, 'down', None), 'збій B не підхопив статуси A')
        self.assertEqual(sorted(serve._TRACKER_CACHE), ['A', 'B'])
        self.assertEqual(self._snapshot(f, space='A', now=1002.0), a, 'збій B не зачепив A')
        self.assertEqual(len(f.calls), 2)

    def test_the_lock_is_its_own_and_a_busy_team_lock_does_not_block_it(self):
        self.assertIsNot(serve._TRACKER_LOCK, serve._TEAM_LOCK)
        done = threading.Event()
        box = []

        def work():
            box.append(self._snapshot(_Fetch(({'DEMO-1': _st('Done')}, None)), now=1.0))
            done.set()
        with serve._TEAM_LOCK:                       # «Команда» зараз чекає мертвий Supabase
            th = threading.Thread(target=work, daemon=True)
            th.start()
            finished = done.wait(3)
        th.join(3)
        self.assertTrue(finished, 'трекер чекав лок команди')
        self.assertEqual(box[0][0], {'DEMO-1': _st('Done')})

    def test_no_provider_is_none_and_a_registry_failure_is_an_error_without_a_cache(self):
        self.assertIsNone(serve.tracker_snapshot(['DEMO-1'], now=1.0, resolved=(None, None)))
        boom = spaces.SpacesError('spaces-unreadable', '<registry>', 'тест')
        with mock.patch.object(serve, 'tracker_resolve', side_effect=boom):
            got = serve.tracker_snapshot(['DEMO-1'], now=1.0)
        self.assertEqual(got, ({}, 'реєстр просторів не читається (spaces-unreadable)', None))
        with mock.patch.object(serve, 'tracker_resolve', side_effect=dm.ModuleError('space-json-unreadable', message='space.json')):
            got = serve.tracker_snapshot(['DEMO-1'], now=1.0)
        self.assertEqual(got, ({}, 'space.json', None))
        self.assertEqual(serve._TRACKER_CACHE, {})


#: Модуль-фікстура ролі `tracker`: пише ключі кожного виклику в `log_file`, віддає `Fake <ключ>`; `fail` — текст помилки.
FAKE_TRACKER_SERVER = tm.CHECK_ONLY + """
import json
def statuses(ctx, keys):
    with open(ctx['settings']['log_file'], 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(keys) + '\\n')
    if ctx['settings'].get('fail'):
        raise ctx['ModuleError']('tracker-error', message=ctx['settings']['fail'])
    return {k: {'name': 'Fake ' + k, 'cat': 'done'} for k in keys}
"""
_TRK_SETTINGS = [{'key': 'log_file', 'type': 'text', 'label': 'Log file (test)', 'required': True},
                 {'key': 'fail', 'type': 'text', 'label': 'Fail with this text (test)'}]


class TrackerOverviewSpaces(tm.Env):
    """Звичайний простір із фейковим модулем трекера (без дашборда): екран бере статуси в нього, кеш — на простір, зламане
    рішення ролі — плашка з причиною. Мережі нема: фейковий модуль у `self.mods`."""

    def setUp(self):
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai          # як у `DashboardRole`: статичний охоронець шукає присвоєння в самому файлі
        reset_tracker_cache()
        self.addCleanup(reset_tracker_cache)
        self.mk('fake-trk', roles=('tracker',), server=FAKE_TRACKER_SERVER, settings=_TRK_SETTINGS)

    def space_with_tracker(self, name='Plain', fail=None):
        sp = self.new_space(name)
        log = self.hp(name.lower() + '.log')
        dm.write_module_state(sp, 'fake-trk', enabled=True, settings={'log_file': log, **({'fail': fail} if fail else {})})
        return sp, log

    def asked(self, log):
        try:
            with open(log, encoding='utf-8') as fh:
                return [json.loads(line) for line in fh]
        except OSError:
            return []

    def snap_in(self, sp, keys=('DEMO-1',), **kw):
        with spaces.request_space(sp['id']):
            return serve.tracker_snapshot(list(keys), **kw)

    def seed_tasks(self, sp, jira='DEMO-1'):
        d = os.path.join(sp['path'], 't1')
        mb2._write(os.path.join(d, 'iterations.json'),
                   {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
        mb2._write(os.path.join(sp['path'], 'tasks.json'), {'design_work_root': sp['path'], 'current': 't1', 'tasks': {
            't1': {'title': 'Demo', 'dir': d, 'profile': 'tool', 'jira': jira, 'opened': '2026-11-01T10:00:00Z'}}})

    def http_overview(self, sp):
        spaces.switch_space(sp['id'])
        with mb2.Server() as srv:
            status, body = srv.get('/api/tasks-overview?refresh=1')
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_a_plain_space_takes_statuses_from_its_tracker_with_no_dashboard(self):
        sp, log = self.space_with_tracker()
        self.seed_tasks(sp)
        data = self.http_overview(sp)
        self.assertIsNone(data['team'], 'дашборда нема — вкладки «Команда» нема')
        self.assertEqual((data['mine'][0]['jiraStatus'], data['mine'][0]['jiraCat']), ('Fake DEMO-1', 'done'))
        self.assertIsNone(data['tracker']['error'])
        self.assertIsInstance(data['tracker']['okAt'], float)
        self.assertEqual(self.asked(log), [['DEMO-1']])

    def test_a_failing_tracker_module_is_a_banner_with_its_text_and_my_tasks_live(self):
        sp, _ = self.space_with_tracker(fail='tracker is down')
        self.seed_tasks(sp)
        data = self.http_overview(sp)
        self.assertEqual(data['tracker'], {'error': 'tracker is down', 'okAt': None})
        self.assertEqual([m['id'] for m in data['mine']], ['t1'])
        self.assertIsNone(data['mine'][0]['jiraStatus'])

    def test_an_undecidable_role_is_a_banner_not_a_500_and_is_not_cached(self):
        """Зламаний `space.json` простору з інтеграціями — `ModuleError` рішення ролі: `tracker: {error, okAt: null}`, «Мої» живуть,
        кешу нема."""
        ig = self.new_space('Integ', integrations=True)
        with open(self.space_json(ig), 'w', encoding='utf-8') as fh:
            fh.write('{broken')
        self.seed_tasks(ig)
        data = self.http_overview(ig)
        self.assertIsNone(data['tracker']['okAt'])
        self.assertTrue(data['tracker']['error'] and len(data['tracker']['error']) <= 200)
        self.assertEqual([m['id'] for m in data['mine']], ['t1'])
        self.assertEqual(serve._TRACKER_CACHE, {})

    def test_a_space_with_no_tasks_asks_nothing_and_shows_no_banner(self):
        sp, log = self.space_with_tracker()
        data = self.http_overview(sp)
        self.assertEqual((data['mine'], data['tracker']['error']), ([], None))
        self.assertEqual(self.asked(log), [], 'нема ключів — нема виклику модуля')

    def test_with_a_dashboard_too_the_tracker_wins_for_mine_and_team_rows_keep_the_dashboard(self):
        """Простір із дашбордом І трекером: «Мої» — статус трекера, «Команда» — статус дашборда (без змін); обидва джерела живі."""
        self.mk('fake-dash', roles=('dashboard',), server=tm.CHECK_ONLY + (
            'def rows(ctx):\n    return [{"id": "t1", "name": "T", "jira": "DEMO-1", "jira_status": "Row Status", "jira_status_cat": "new"}]\n'
            'def push(ctx, cards, mode):\n    return {"ok": 0, "failed": {}}\n'))
        sp, _ = self.space_with_tracker()
        dm.write_module_state(sp, 'fake-dash', enabled=True)
        self.seed_tasks(sp)
        data = self.http_overview(sp)
        self.assertEqual((data['mine'][0]['jiraStatus'], data['mine'][0]['jiraCat']), ('Fake DEMO-1', 'done'))
        self.assertEqual((data['team']['rows'][0]['jiraStatus'], data['team']['rows'][0]['jiraCat']), ('Row Status', 'new'))
        self.assertIsNone(data['tracker']['error'])

    def test_a_dashboard_failure_and_a_tracker_failure_are_reported_separately(self):
        self.mk('bad-dash', roles=('dashboard',), server=tm.CHECK_ONLY + (
            'def rows(ctx):\n    raise ctx["ModuleError"]("dashboard-error", message="dash down")\n'
            'def push(ctx, cards, mode):\n    return {"ok": 0, "failed": {}}\n'))
        sp, _ = self.space_with_tracker(fail='trk down')
        dm.write_module_state(sp, 'bad-dash', enabled=True)
        self.seed_tasks(sp)
        data = self.http_overview(sp)
        self.assertEqual(data['team']['error'], 'dash down')
        self.assertEqual(data['tracker'], {'error': 'trk down', 'okAt': None})

    def test_a_space_without_a_provider_has_tracker_null(self):
        sp = self.new_space('Bare')
        self.seed_tasks(sp)
        data = self.http_overview(sp)
        self.assertIsNone(data['tracker'])

    def test_the_cache_keeps_two_spaces_apart_and_a_failure_keeps_the_last_statuses(self):
        a, alog = self.space_with_tracker('Alpha')
        b, blog = self.space_with_tracker('Bravo')
        ra = self.snap_in(a, now=1000.0)
        self.snap_in(b, now=1000.0)
        self.assertEqual(ra, ({'DEMO-1': _st('Fake DEMO-1')}, None, 1000.0))
        self.assertEqual((self.asked(alog), self.asked(blog)), ([['DEMO-1']], [['DEMO-1']]), 'кожному просторові — свій запит')
        dm.write_module_state(a, 'fake-trk', enabled=True, settings={'log_file': alog, 'fail': 'a is down'})
        got = self.snap_in(a, now=1000.0 + serve.TRACKER_TTL + 1)
        self.assertEqual(got, ({'DEMO-1': _st('Fake DEMO-1')}, 'a is down', 1000.0))
        self.assertEqual(self.snap_in(b, now=1000.0 + 5), ({'DEMO-1': _st('Fake DEMO-1')}, None, 1000.0), 'збій A не став станом B')
        self.assertEqual(len(self.asked(blog)), 1)


if __name__ == '__main__':
    unittest.main()


class TasksListMissingTest(unittest.TestCase):
    """`/api/tasks` каже, чия тека є на ЦІЙ машині: перемикач задач не пускає в
    задачу з чужою текою (реєстр їде в git, а теки — ні), а без цього поля
    браузер дізнавався б про це лише помилкою після кліку."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix='dc-tl-')
        here = make_task(cls.root, 'here')
        ghost = {'dir': os.path.join(cls.root, 'нема-такої-теки'), 'title': 'Привид'}
        nodir = {'title': 'Без поля dir'}
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-tl-cfg-')
        tasks_file = os.path.join(cls.cfgdir, 'tasks.json')
        _write_json(tasks_file, {'current': 'here',
                                 'tasks': {'here': here, 'ghost': ghost, 'nodir': nodir}})
        os.environ['DC_TASKS_FILE'] = tasks_file
        os.environ['DC_NO_OVERVIEW'] = '1'
        cls.httpd = serve.make_server(0)
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for var in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            os.environ.pop(var, None)
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.cfgdir, ignore_errors=True)

    def test_missing_flag_reflects_the_folder_on_this_machine(self):
        with _real_urlopen(self.base + '/api/tasks') as res:
            data = json.loads(res.read())
        by_id = {t['id']: t for t in data['tasks']}
        self.assertIs(by_id['here']['missing'], False)
        self.assertIs(by_id['ghost']['missing'], True)
        # запис без `dir` — теж «теки нема», а не виняток на всю відповідь
        self.assertIs(by_id['nodir']['missing'], True)
        # решта полів не постраждала
        self.assertEqual(by_id['ghost']['title'], 'Привид')
        self.assertEqual(data['current'], 'here')

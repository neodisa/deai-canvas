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
import serve  # noqa: E402

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
    with serve._TEAM_LOCK:
        serve._TEAM_CACHE.update(at=0.0, rows=None, error=None, rowsAt=None)


class _TmpCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='dc-tov-')
        reset_team_cache()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        reset_team_cache()


class TasksOverviewTest(_TmpCase):
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
    def _fake(self, rows):
        p = os.path.join(self.root, 'team.json')
        _write_json(p, rows)
        return p

    def test_isolated_run_without_fake_makes_no_network_call(self):
        """⛔ Закон ізоляції: під DC_NO_OVERVIEW/DC_TASKS_FILE шарити мережею не можна."""
        for var in ('DC_NO_OVERVIEW', 'DC_TASKS_FILE'):
            reset_team_cache()
            env = {var: '1'}
            with mock.patch.dict(os.environ, env):
                os.environ.pop('DC_TEAM_FAKE', None)
                with mock.patch('urllib.request.urlopen',
                                side_effect=AssertionError('мережа з ізольованого прогону')) as uo:
                    rows, err = serve.team_rows(now=1000.0)
            self.assertEqual(uo.call_count, 0, var)
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
        """Помилку програмування не можна тихо видати за «команда недоступна»."""
        with mock.patch.dict(os.environ):
            for var in ('DC_NO_OVERVIEW', 'DC_TASKS_FILE', 'DC_TEAM_FAKE'):
                os.environ.pop(var, None)
            err = io.StringIO()
            with mock.patch('urllib.request.urlopen', side_effect=KeyError('баг')), \
                    contextlib.redirect_stderr(err):
                rows, msg = serve.team_rows(now=1000.0)
            self.assertEqual(rows, [])
            self.assertTrue(msg)
            self.assertIn('KeyError', err.getvalue())
            reset_team_cache()
            quiet = io.StringIO()
            with mock.patch('urllib.request.urlopen', side_effect=OSError('нема VPN')), \
                    contextlib.redirect_stderr(quiet):
                serve.team_rows(now=1000.0)
            self.assertEqual(quiet.getvalue(), '')         # звичайна мережа — без шуму

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
            with mock.patch('urllib.request.urlopen', side_effect=OSError('нема VPN')) as uo:
                rows, err = serve.team_rows(now=1000.0)
        self.assertEqual(uo.call_count, 1)
        self.assertEqual(uo.call_args.kwargs.get('timeout'), 3)
        self.assertEqual((rows, err), ([], 'нема VPN'))


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
        with mock.patch.dict(os.environ):
            os.environ.pop('DC_TEAM_FAKE')
            # патч глобальний (сервер у своєму потоці) — і мутація «прибрали гвард»
            # не піде в живий Supabase, а лише зачепить лічильник нижче
            with mock.patch('urllib.request.urlopen', side_effect=OSError('мережі нема')) as uo:
                status, _, body = self.get('/api/tasks-overview')
        self.assertEqual(uo.call_count, 0)
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

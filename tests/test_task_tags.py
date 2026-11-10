"""Мітки задач, сервер (Deai 0.11.0, етап 4b-3, Task 2; спека `docs/superpowers/specs/2026-11-02-task-tags-design.md` §1–2).

Що доводиться:
  * `normalize_tags` — правила вводу (обрізання, дублікати без регістру, межі, `TagsError`);
  * `task_tags` — читання не кидає: явний ключ `tags` (навіть `[]`) перемагає похідну мітку ЛІГИ з `profile`;
  * `tags` — ОСТАННІЙ ключ у рядках `/api/tasks` (з `?all=1` — перед `space`) і «Моїх» `/api/tasks-overview`; у `/api/task` — після `profile`;
  * `POST /api/task-new` приймає `tags` (400 `bad-tags`), `POST /api/task-tags` замінює їх у ТОМУ просторі, де лежить
    задача, і не чіпає ні поточну задачу, ні поточний простір машини; після запису — `_registry_push`;
  * `bin/registry.py`: `tags` у `SHARED`;
  * 4d-4a: `serve.profile_repos()` зник; таблиця «напрямок → репозиторій» — `tests/test_liga_adapter.py::LegacyReposTable`;
    `_task_new_write` і `_liga_flow` беруть репо з ЯВНИХ напрямків простору ЛІГИ (`TaskNewFromTracksTest`, знімок `before-4b3.json`).

Сервер і простори — фікстура `test_spaces_serve.Fixture`: старий простір з інтеграціями (`legacy_id`, задача `a`,
профіль `tool`), `P` без інтеграцій (`p_id`, задачі `x`, `gone`), порожній `E`. ⛔ Ізоляція та сама: тимчасові `HOME`,
`DEAI_HOME`, `DC_TASKS_FILE`, `DC_NO_OVERVIEW` — `_registry_push` у спільний реєстр не пише; де треба довести, що його
кличуть, — він підмінений.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_spaces_serve import Fixture, _bytes, _md5, _read, _write  # noqa: E402  (модуль сам ставить app/ і bin/)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import tracks  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class NormalizeTags(unittest.TestCase):
    def test_trims_collapses_and_dedups_case_insensitively_keeping_the_first(self):
        self.assertEqual(serve.normalize_tags([' Alpha ', 'alpha', 'b  c', 'B C']), ['Alpha', 'b c'])

    def test_empty_items_are_dropped(self):
        self.assertEqual(serve.normalize_tags(['', '  ']), [])
        self.assertEqual(serve.normalize_tags([]), [])

    def test_at_most_ten(self):
        self.assertEqual(len(serve.normalize_tags([f't{i}' for i in range(10)])), 10)
        with self.assertRaises(serve.TagsError):
            serve.normalize_tags([f't{i}' for i in range(11)])

    def test_a_tag_is_at_most_32_characters(self):
        self.assertEqual(serve.normalize_tags(['x' * 32]), ['x' * 32])
        with self.assertRaises(serve.TagsError):
            serve.normalize_tags(['x' * 33])

    def test_invisible_and_bidi_characters_are_refused(self):
        """Нульової ширини й двоспрямовані керування (U+202E «розвертає» текст) — відмова, як і керівні знаки: мітка не
        мусить виглядати не тим, чим є, і дві «однакові» мітки не мусять різнитися невидимим знаком."""
        for ch in ('\u200b', '\u200d', '\u200f', '\u202a', '\u202e', '\u2060', '\u2064', '\u2066', '\u2069', '\ufeff'):
            for tag in (f'a{ch}b', f'{ch}a', f'a{ch}'):
                with self.subTest(ch=hex(ord(ch)), tag=tag), self.assertRaises(serve.TagsError):
                    serve.normalize_tags([tag])
        self.assertEqual(serve.normalize_tags(['\u2065x', 'a\u2010b']), ['\u2065x', 'a\u2010b'],
                         'сусідні кодові точки (U+2065 не призначено, U+2010 дефіс) не зачеплено')

    def test_a_huge_list_is_refused_before_any_per_item_work(self):
        with mock.patch.object(tracks, 'clean_tag') as clean:
            with self.assertRaises(serve.TagsError):
                serve.normalize_tags([''] * (serve.TAGS_RAW_MAX + 1))
        clean.assert_not_called()
        self.assertEqual(serve.normalize_tags([''] * serve.TAGS_RAW_MAX), [])

    def test_comma_and_control_characters_are_refused(self):
        for bad in ('a,b', 'a\x00b', 'a\x7fb', 'a\x85b', 'a\nb', 'a\tb'):
            with self.subTest(bad=bad), self.assertRaises(serve.TagsError):
                serve.normalize_tags([bad])

    def test_edge_whitespace_is_trimmed_but_inner_control_whitespace_is_refused_not_glued(self):
        """`\\n`/`\\t` по краях — обрізаються; усередині — відмова, а не тихе склеювання `a\\nb` в `a b`."""
        self.assertEqual(serve.normalize_tags(['\n a \t', 'c   d']), ['a', 'c d'])

    def test_not_a_list_or_not_strings_is_refused(self):
        for bad in (5, 'abc', None, {'a': 1}, [1], ['ok', None], [['x']]):
            with self.subTest(bad=bad), self.assertRaises(serve.TagsError):
                serve.normalize_tags(bad)

    def test_the_limit_counts_after_deduplication(self):
        self.assertEqual(len(serve.normalize_tags([f't{i}' for i in range(10)] + ['T0', 't1'])), 10)


class TaskTags(unittest.TestCase):
    def setUp(self):
        """⛔ `task_tags` без `sp` питає простір запиту (4d-1: похідна мітка залежить від напрямків простору), а при ввімкненому
        шарі це читання справжнього реєстру машини. Шар вимкнено: лише `DC_TASKS_FILE`, без `DEAI_HOME` — простір неявний
        (ЛІГА), реєстр не читається й не пишеться."""
        p = mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(tempfile.gettempdir(), 'deai-no-such-tasks.json')})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()

    def test_explicit_tags_win(self):
        self.assertEqual(serve.task_tags({'tags': ['x']}), ['x'])

    def test_an_explicit_empty_list_is_not_replaced_by_the_profile(self):
        """Людина свідомо прибрала всі мітки: похідна мітка не воскресає."""
        self.assertEqual(serve.task_tags({'tags': [], 'track': 'united'}), [])

    def test_derived_from_the_track_without_the_key(self):
        # 4d-4a: було `…from_the_profile…` — читалось `profile`, а підписи United/LIGA360/SEO давав адаптер ЛІГИ. Тепер читається
        # `track`, а простір без напрямків (шар вимкнено) віддає значення як є: нижній регістр (відмінність спеки 4)
        for track, tag in (('united', 'united'), ('liga360', 'liga360'), ('seo', 'seo'), ('tool', 'tool')):
            with self.subTest(track=track):
                self.assertEqual(serve.task_tags({'track': track}), [tag])
                self.assertEqual(serve.task_tags({'profile': track}), [], 'лише `profile` — без похідної мітки')

    def test_the_derived_tag_obeys_the_stored_tag_rules(self):
        """Діалог правки заповнюється поточними мітками: похідна, що після збереження розпалась би (кома) чи не пройшла б
        (довга, керівний знак), — не показується; пробіли обрізаються й стискаються."""
        for profile in ('a,b', 'x' * 33, 'a\nb', 'a\x00b', '\x85'):
            with self.subTest(profile=profile):
                self.assertEqual(serve.task_tags({'track': profile}), [])         # 4d-4a: значення читається з `track`, не з `profile`
        self.assertEqual(serve.task_tags({'track': '  my   tool '}), ['my tool'])
        self.assertEqual(serve.task_tags({'track': 'x' * 32}), ['x' * 32])
        # і те, що показано, проходить `normalize_tags` без змін (замкнений цикл «показали → зберегли»)
        for track in ('united', 'tool', '  my   tool '):
            tags = serve.task_tags({'track': track})
            self.assertEqual(serve.normalize_tags(tags), tags)

    def test_no_track_means_no_tags(self):
        # було `test_no_profile_means_no_tags`; `profile` теж більше нічого не дає (див. `…derived_from_the_track…`)
        for task in ({'track': None}, {'track': ''}, {'track': '  '}, {}, {'track': 5}, {'profile': 'united'}):
            with self.subTest(task=task):
                self.assertEqual(serve.task_tags(task), [])

    def test_a_corrupt_key_does_not_fall_back_to_the_track(self):
        self.assertEqual(serve.task_tags({'tags': 'junk', 'track': 'seo'}), [])
        self.assertEqual(serve.task_tags({'tags': None, 'track': 'seo'}), [])

    def test_reading_drops_invisible_and_bidi_items_and_derived_tags(self):
        self.assertEqual(serve.task_tags({'tags': ['ok', 'a\u202eb', 'c\u200bd', '\ufeffe', 'f']}), ['ok', 'f'])
        for profile in ('a\u202eb', 'a\u200bb', '\ufeffseo'):
            with self.subTest(profile=profile):
                self.assertEqual(serve.task_tags({'track': profile}), [])         # 4d-4a: з `track`

    def test_reading_never_raises_and_drops_bad_items(self):
        self.assertEqual(serve.task_tags({'tags': ['ok', 5, 'a,b', 'OK', '  ', 'x' * 33]}), ['ok'])

    def test_reading_stops_scanning_at_the_limit(self):
        """Після `TAGS_MAX` мітки не розбираються далі (файл руками набитий тисячами): лічильник викликів `tracks.read_tag`."""
        with mock.patch.object(tracks, 'read_tag', wraps=tracks.read_tag) as rt:
            out = serve.task_tags({'tags': [f't{i}' for i in range(500)]})
        self.assertEqual(len(out), serve.TAGS_MAX)
        self.assertEqual(rt.call_count, serve.TAGS_MAX)

    def test_reading_caps_at_the_limit(self):
        self.assertEqual(len(serve.task_tags({'tags': [f't{i}' for i in range(15)]})), serve.TAGS_MAX)

    def test_a_non_dict_task_is_empty(self):
        for task in (None, 'x', 5, []):
            with self.subTest(task=task):
                self.assertEqual(serve.task_tags(task), [])


class TagsApi(Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Структурні охоронці (`test_serve.TestsCannotWriteLiveConfig`) вимагають присвоєння в САМОМУ файлі, що кличе
        # `/api/task-new`; ізоляцію робить `Fixture.setUpClass` (і повертає env у cleanup) — тут те саме значення явно.
        os.environ['DEAI_HOME'] = cls.deai
        os.environ['DC_TASKS_FILE'] = cls.legacy_file

    @property
    def reg_path(self):
        return os.path.join(self.deai, 'spaces.json')

    def setUp(self):
        super().setUp()
        for path in (self.reg_path, self.legacy_file, self.p_file):
            self.restore_bytes(path)

    def tags_of(self, path, tid):
        return _read(path)['tasks'][tid].get('tags', 'ABSENT')

    # ---------- рядки відповідей ----------

    def test_tasks_rows_carry_tags_last(self):
        st, body = self.jget('/api/tasks')
        self.assertEqual(st, 200)
        row = body['tasks'][0]
        self.assertEqual(list(row)[-1], 'tags')
        self.assertEqual(row['tags'], ['tool'], 'без ключа tags — похідна мітка з track')
        cfg = _read(self.legacy_file)
        cfg['tasks']['a']['tags'] = ['Alpha', 'beta']
        _write(self.legacy_file, cfg)
        self.assertEqual(self.jget('/api/tasks')[1]['tasks'][0]['tags'], ['Alpha', 'beta'])
        cfg['tasks']['a']['tags'] = []
        _write(self.legacy_file, cfg)
        self.assertEqual(self.jget('/api/tasks')[1]['tasks'][0]['tags'], [])

    def test_tasks_all_rows_carry_tags_before_space(self):
        """`?all=1` додає `space` ПІСЛЯ рядка простору, тож `tags` лишається останнім ключем самого рядка задачі."""
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual(st, 200)
        for row in body['tasks']:
            self.assertEqual(list(row)[-2:], ['tags', 'space'])
            self.assertEqual(row['tags'], ['tool'])

    def test_task_carries_tags_right_after_jira(self):
        """`/api/task` — не рядок списку, а відповідь про одну задачу з багатьма доданими ключами: `tags` стоїть у «шапці»
        (було після `profile`, який 4d-4a прибрав з відповіді; тепер після `jira`), не в хвості, який дописують публікація й превʼю."""
        st, body = self.jget('/api/task')
        self.assertEqual(st, 200)
        self.assertEqual(body['tags'], ['tool'])
        keys = list(body)
        self.assertNotIn('profile', keys)
        self.assertEqual(keys[keys.index('jira') + 1], 'tags')
        cfg = _read(self.legacy_file)
        cfg['tasks']['a']['tags'] = ['k']
        _write(self.legacy_file, cfg)
        self.assertEqual(self.jget('/api/task')[1]['tags'], ['k'])

    def test_overview_mine_rows_carry_tags_last(self):
        cfg = _read(self.legacy_file)
        cfg['tasks']['a']['tags'] = ['mine']
        _write(self.legacy_file, cfg)
        st, body = self.jget('/api/tasks-overview')
        self.assertEqual(st, 200)
        row = body['mine'][0]
        self.assertEqual((row['id'], row['tags'], list(row)[-1]), ('a', ['mine'], 'tags'))

    # ---------- task-new ----------

    def test_task_new_stores_normalized_tags(self):
        self.addCleanup(shutil.rmtree, os.path.join(self.p_path, 'tg1'), True)
        st, body = self.post('/api/task-new', {'id': 'tg1', 'space': self.p_id, 'tags': ['A', 'a', 'B']})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.tags_of(self.p_file, 'tg1'), ['A', 'B'])
        self.assertEqual(self.jget('/t/tg1/api/task')[1]['tags'], ['A', 'B'])

    def test_task_new_without_tags_has_no_key(self):
        self.addCleanup(shutil.rmtree, os.path.join(self.p_path, 'tg2'), True)
        for i, payload in enumerate(({}, {'tags': []}, {'tags': [' ']})):
            tid = f'tg2{i}'
            self.addCleanup(shutil.rmtree, os.path.join(self.p_path, tid), True)
            with self.subTest(payload=payload):
                st, body = self.post('/api/task-new', {'id': tid, 'space': self.p_id, **payload})
                self.assertEqual(st, 200, body)
                self.assertEqual(self.tags_of(self.p_file, tid), 'ABSENT')

    def test_task_new_bad_tags_is_400_and_creates_nothing(self):
        before = (_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path))
        for bad in ('A', 5, [1], ['a,b'], ['a\u202eb'], [''] * 101, ['x' * 33], [f't{i}' for i in range(11)], {'a': 1}):
            with self.subTest(bad=bad):
                st, body = self.post('/api/task-new', {'id': 'tgbad', 'space': self.p_id, 'tags': bad})
                self.assertEqual((st, body['code'], body['ok']), (400, 'bad-tags', False))
                self.assertFalse(os.path.lexists(os.path.join(self.p_path, 'tgbad')))
        self.assertEqual((_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path)), before)

    def test_task_new_null_tags_is_no_field(self):
        self.addCleanup(shutil.rmtree, os.path.join(self.p_path, 'tg3'), True)
        st, body = self.post('/api/task-new', {'id': 'tg3', 'space': self.p_id, 'tags': None})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.tags_of(self.p_file, 'tg3'), 'ABSENT')

    # ---------- task-tags ----------

    def test_task_tags_replaces_and_normalizes(self):
        with mock.patch.object(serve, '_registry_push', return_value=False):
            st, body = self.post('/api/task-tags', {'id': 'a', 'tags': [' Alpha ', 'alpha', 'beta']})
        self.assertEqual((st, body), (200, {'ok': True, 'tags': ['Alpha', 'beta']}))
        self.assertEqual(self.tags_of(self.legacy_file, 'a'), ['Alpha', 'beta'])
        self.assertEqual(self.jget('/api/task')[1]['tags'], ['Alpha', 'beta'])

    def test_task_tags_empty_list_is_stored_as_empty_and_hides_the_derived_tag(self):
        with mock.patch.object(serve, '_registry_push', return_value=False):
            st, body = self.post('/api/task-tags', {'id': 'a', 'tags': []})
        self.assertEqual((st, body), (200, {'ok': True, 'tags': []}))
        self.assertEqual(self.tags_of(self.legacy_file, 'a'), [])
        self.assertEqual(self.jget('/api/task')[1]['tags'], [])
        self.assertEqual(self.jget('/api/task')[1]['track'], 'tool', 'напрямок лишається полем задачі (було `profile`)')

    def test_task_tags_unknown_task_is_json_404(self):
        before = (_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path))
        with mock.patch.object(serve, '_registry_push') as push:
            for payload in ({'id': 'nope', 'tags': []}, {'tags': []}, {'id': 5, 'tags': []}, {'id': None, 'tags': []},
                            {'id': '', 'tags': []}, {'id': ['x'], 'tags': []}):
                with self.subTest(payload=payload):
                    st, body = self.post('/api/task-tags', payload)
                    self.assertEqual((st, body['code'], body['ok']), (404, 'unknown-task', False))
            push.assert_not_called()
        self.assertEqual((_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path)), before)

    def test_task_tags_bad_tags_of_an_unknown_task_are_400_before_any_lookup(self):
        """Мітки перевіряються ПЕРШИМИ (дешево, без диска): невідома задача з поганими мітками — 400, а не 404."""
        with mock.patch.object(spaces, 'find_task') as find, mock.patch.object(serve, '_registry_push') as push:
            st, body = self.post('/api/task-tags', {'id': 'nope', 'tags': ['a,b']})
        self.assertEqual((st, body['code']), (400, 'bad-tags'))
        find.assert_not_called()
        push.assert_not_called()

    def test_task_tags_vanished_between_lookup_and_read_is_404(self):
        """`find_task` сказав «є в P», а до читання файла задачу вилучили: 404 JSON, файл не змінено."""
        p_space = next(s for s in spaces.read_registry()['spaces'] if s['id'] == self.p_id)
        before = (_md5(self.p_file), _md5(self.legacy_file))
        with mock.patch.object(spaces, 'find_task', return_value=p_space), \
                mock.patch.object(serve, '_registry_push') as push:
            st, body = self.post('/api/task-tags', {'id': 'vanished', 'tags': ['a']})
        self.assertEqual((st, body['code']), (404, 'unknown-task'))
        push.assert_not_called()
        self.assertEqual((_md5(self.p_file), _md5(self.legacy_file)), before)

    def test_task_tags_bad_tags_is_400_and_the_file_is_untouched(self):
        before = (_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path))
        with mock.patch.object(serve, '_registry_push') as push:
            for bad in ('A', 5, None, [1], ['a,b'], ['x' * 33], [f't{i}' for i in range(11)], {'a': 1}):
                with self.subTest(bad=bad):
                    st, body = self.post('/api/task-tags', {'id': 'a', 'tags': bad})
                    self.assertEqual((st, body['code'], body['ok']), (400, 'bad-tags', False))
            st, body = self.post('/api/task-tags', {'id': 'a'})          # без ключа tags — теж не список
            self.assertEqual((st, body['code']), (400, 'bad-tags'))
            push.assert_not_called()
        self.assertEqual((_md5(self.p_file), _md5(self.legacy_file), _md5(self.reg_path)), before)

    def test_task_tags_writes_to_the_space_of_the_task_and_moves_nothing(self):
        """Поточний простір — старий (`a`); задача `x` — у P: мітки лягають у файл P, а `current` машини, поточний простір,
        `current` і `opened` обох файлів лишаються як були."""
        legacy_before = _bytes(self.legacy_file)
        reg_before = _bytes(self.reg_path)
        p_before = _read(self.p_file)
        with mock.patch.object(serve, '_registry_push', return_value=False):
            st, body = self.post('/api/task-tags', {'id': 'x', 'tags': ['alpha', 'beta']})
        self.assertEqual((st, body), (200, {'ok': True, 'tags': ['alpha', 'beta']}))
        after = _read(self.p_file)
        self.assertEqual(after['tasks']['x']['tags'], ['alpha', 'beta'])
        expected = json.loads(json.dumps(p_before))
        expected['tasks']['x']['tags'] = ['alpha', 'beta']
        self.assertEqual(after, expected, 'змінилися лише мітки задачі (current/opened не чіпані)')
        self.assertEqual(_bytes(self.legacy_file), legacy_before, 'старий файл змінився')
        self.assertEqual(_bytes(self.reg_path), reg_before, 'реєстр просторів змінився: перемкнуло простір')
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)

    def test_task_tags_does_not_make_the_task_current_in_its_own_file(self):
        """`gone` у P не поточна (`current` = `x`): правка міток не перемикає й `current` файла задач, і не ставить `opened`."""
        with mock.patch.object(serve, '_registry_push', return_value=False):
            st, _ = self.post('/api/task-tags', {'id': 'gone', 'tags': ['t']})
        self.assertEqual(st, 200)
        after = _read(self.p_file)
        self.assertEqual((after['current'], after['tasks']['gone']['tags']), ('x', ['t']))
        self.assertNotIn('opened', after['tasks']['gone'])

    def test_task_tags_pushes_the_registry_for_that_task(self):
        with mock.patch.object(serve, '_registry_push', return_value=True) as push:
            st, _ = self.post('/api/task-tags', {'id': 'x', 'tags': ['alpha']})
        self.assertEqual(st, 200)
        push.assert_called_once_with('x')

    def test_task_tags_is_a_registry_route_so_the_task_prefix_and_header_do_not_apply(self):
        self.assertIn('/api/task-tags', serve.Handler._REGISTRY_ROUTES)
        before = _md5(self.p_file)
        st, body = self.post('/t/x/api/task-tags', {'id': 'x', 'tags': ['zzz']})
        self.assertEqual(st, 400, 'префіксна форма реєстрових маршрутів відхиляється, як і в `task-switch`')
        self.assertEqual(_md5(self.p_file), before)
        # заголовок `X-Canvas-Task` не вибирає простір: задача — за `id` у тілі
        with mock.patch.object(serve, '_registry_push', return_value=False):
            st, _ = self.post('/api/task-tags', {'id': 'x', 'tags': ['hdr']}, {'X-Canvas-Task': 'a'})
        self.assertEqual(st, 200)
        self.assertEqual(self.tags_of(self.p_file, 'x'), ['hdr'])
        self.assertEqual(self.tags_of(self.legacy_file, 'a'), 'ABSENT')

    def test_task_tags_id_in_two_spaces_is_ambiguous_409_and_nothing_changes(self):
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        before = (_md5(self.p_file), _md5(self.legacy_file))
        with mock.patch.object(serve, '_registry_push') as push:
            st, body = self.post('/api/task-tags', {'id': 'a', 'tags': ['x']})
        self.assertEqual((st, body['code']), (409, 'ambiguous-task'))
        push.assert_not_called()
        self.assertEqual((_md5(self.p_file), _md5(self.legacy_file)), before)

    def test_task_tags_unknown_id_with_an_unreadable_space_file_is_503_not_404(self):
        self.p_before = _bytes(self.p_file)
        _write(self.p_file, '{not json')
        with mock.patch.object(serve, '_registry_push') as push:
            st, body = self.post('/api/task-tags', {'id': 'x', 'tags': ['x']})
        self.assertEqual((st, body['code']), (503, 'space-unavailable'), body)
        push.assert_not_called()
        # а коли всі файли читаються — невідома задача лишається 404 (не 503)
        _write(self.p_file, self.p_before.decode('utf-8'))
        self.assertEqual(self.post('/api/task-tags', {'id': 'nope', 'tags': []})[0], 404)



class TaskNewFromTracksTest(unittest.TestCase):
    """Було `ProfileReposTest` (4b-3, `serve.profile_repos()` з кореня старого `tasks.json`). 4d-4a: таблицю й її тести перенесено
    в `tests/test_liga_adapter.py::LegacyReposTable` (`liga_migrate._legacy_repos`); тут лишилось те, що рантайм робить з
    РЕПО НАПРЯМКУ: `gitlab`-маппінг запису (`_task_new_write`) — з ЯВНИХ напрямків простору ЛІГИ реєстру (`space.json`), а не з
    файла. (Ознака потоку ЛІГА `_liga_flow` зникла в 4d-4c.)

    ⛔ Ізоляція: `spaces.read_registry` підмінено — реєстр машини не читається, `space.json` лежить у тимчасовій теці;
    `_task_new_write` працює лише над словником `cfg`, `vcs_provider` — без мережі."""

    REPO = 'git@git.example:org/a.git'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.liga = {'id': 'sp-liga', 'name': 'Liga', 'legacy': True, 'path': os.path.join(self.tmp.name, 'liga')}
        os.makedirs(self.liga['path'])
        self.registry = {'version': 1, 'spaces': [self.liga]}
        patcher = mock.patch.object(spaces, 'read_registry', side_effect=lambda: self.registry)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, tracks_list):
        with open(os.path.join(self.liga['path'], 'space.json'), 'w', encoding='utf-8') as f:
            json.dump({'tracks': tracks_list}, f)

    # ---------- диференційний: те саме, що давала константа ----------

    def snapshot(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'task-tags', 'before-4b3.json'),
                  encoding='utf-8') as f:
            return json.load(f)['gitlab']

    def new_gitlab(self, track):
        """`gitlab` запису, який `_task_new_write` кладе в задачу `t-demo` з цим напрямком: репо дає `track_repo` явних напрямків
        простору ЛІГИ (мережі й GitLab-модуля нема)."""
        cfg = {}
        with mock.patch.object(serve, 'vcs_provider', return_value=None):
            serve._task_new_write(cfg, 't-demo', 'T', '', track, None, None,
                                  os.path.join(self.tmp.name, 'task-' + track), None, None,
                                  serve.track_repo(serve._TrackView(self.liga), track), True)
        return cfg['tasks']['t-demo'].get('gitlab')

    def test_explicit_tracks_reproduce_the_snapshot_of_the_old_constant(self):
        snap = self.snapshot()
        self.assertGreaterEqual(len(snap), 4, 'знімок має профілі з репо й без')
        self.write([{'id': p, 'repo': v['gitlab']['repo'] if v['gitlab'] else ''} for p, v in snap.items()])
        for profile, want in snap.items():
            with self.subTest(profile=profile):
                self.assertEqual(self.new_gitlab(profile), want['gitlab'])      # ключ `liga_flow` знімка заморожено, не читаємо (4d-4c)

    def test_without_repos_a_liga_task_has_no_default_repo(self):
        self.write([{'id': 'united'}])
        self.assertIsNone(self.new_gitlab('united'))


if __name__ == '__main__':
    unittest.main()

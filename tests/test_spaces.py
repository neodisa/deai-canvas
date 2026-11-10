"""`app/spaces.py`: реєстр просторів машини, міграція старого `tasks.json`,
резолвер задачі між просторами, активний простір запиту, предикат інтеграцій.

Кожен тест має ВЛАСНІ тимчасові `HOME`, `DEAI_HOME` і `DC_TASKS_FILE` і повертає
оточення як було. Справжній `~/.deai` і справжній `tasks.json` не чіпаються; справжній реєстр
додатково стереже `spaces_guard` (знімок на вході в модуль, звірка на виході).
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
import unicodedata
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import spaces  # noqa: E402
import spaces_guard  # noqa: E402

_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _md5(path):
    return hashlib.md5(_bytes(path)).hexdigest()


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def race(n, fn):
    """`n` потоків стартують разом (Barrier) і кличуть `fn(i)`; повертає
    `[('ok', результат) | ('err', виняток)]` у порядку потоків."""
    bar = threading.Barrier(n)
    out = [None] * n

    def run(i):
        try:
            bar.wait(10)
            out[i] = ('ok', fn(i))
        except BaseException as e:  # noqa: BLE001 — збираємо будь-який виняток потоку
            out[i] = ('err', e)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return out


class Env(unittest.TestCase):
    """Тимчасові HOME/DEAI_HOME/DC_TASKS_FILE; старого файла спершу НЕМА."""

    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='spaces-'))
        self.saved = {k: os.environ.get(k) for k in _ENV}
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        self.deai = os.path.join(self.tmp, 'deai')
        self.legacy = os.path.join(self.tmp, 'legacy', 'tasks.json')
        os.environ['HOME'] = self.home
        os.environ['DEAI_HOME'] = self.deai
        os.environ['DC_TASKS_FILE'] = self.legacy
        spaces.clear_request_space()
        # Сторож: `WRITE_LOCK` не реентерабельний, і виклик `load_registry()` під ним —
        # дедлок, тобто ЗАВИСЛИЙ набір замість червоного тесту. Через 10 с лок
        # відпускається, а tearDown валить тест.
        self.deadlock = threading.Event()

        def wake():
            self.deadlock.set()
            try:
                spaces.WRITE_LOCK.release()
            except RuntimeError:
                pass
        self.watchdog = threading.Timer(10, wake)
        self.watchdog.daemon = True
        self.watchdog.start()

    def tearDown(self):
        self.watchdog.cancel()
        spaces.clear_request_space()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.deadlock.is_set():
            self.fail('тест завис на WRITE_LOCK довше 10 с — схоже на дедлок (load_registry під локом?)')

    def hp(self, *parts):
        return os.path.join(self.home, *parts)

    @property
    def reg_file(self):
        return os.path.join(self.deai, 'spaces.json')

    def write_legacy(self, tasks, **extra):
        cfg = dict(extra)
        cfg['tasks'] = tasks
        _write(self.legacy, cfg)

    def write_registry(self, space_list, current):
        _write(self.reg_file, {'version': 1, 'current': current, 'spaces': space_list})

    def two_spaces(self, p_integrations=False):
        """Старий файл (задача `a`, простір `liga`) + простір `p` із задачею `x`."""
        self.write_legacy({'a': {'dir': self.hp('Liga', 'x', 'a')}}, registry={})
        self.p_path = self.hp('deai-work', 'p')
        _write(os.path.join(self.p_path, 'tasks.json'),
               {'design_work_root': self.p_path, 'tasks': {'x': {'dir': os.path.join(self.p_path, 'x')}}})
        self.write_registry([
            {'id': 'liga', 'path': self.hp('Liga'), 'legacy': True, 'integrations': True},
            {'id': 'p', 'path': self.p_path, 'legacy': False, 'integrations': p_integrations},
        ], 'liga')


class LayerOn(Env):
    def test_truth_table(self):
        cases = [
            ({}, True),                                             # нічого не задано — справжній режим
            ({'DEAI_HOME': '/x'}, True),
            ({'DEAI_HOME': '/x', 'DC_TASKS_FILE': '/y'}, True),
            ({'DC_TASKS_FILE': '/y'}, False),                       # усі наявні тести
            ({'DC_TASKS_FILE': '/y', 'DEAI_HOME': ''}, False),      # порожнє = не задано
            ({'DC_TASKS_FILE': ''}, True),
            ({'DC_TASKS_FILE': '', 'DEAI_HOME': ''}, True),
        ]
        for env, want in cases:
            with self.subTest(env=env):
                for k in ('DEAI_HOME', 'DC_TASKS_FILE'):
                    os.environ.pop(k, None)
                os.environ.update(env)
                self.assertIs(spaces.layer_on(), want)


class Migration(Env):
    def test_nothing_anywhere_gives_virtual_empty_registry_and_writes_nothing(self):
        self.assertEqual(spaces.load_registry(), {'version': 1, 'current': None, 'spaces': []})
        self.assertFalse(os.path.exists(self.reg_file))
        self.assertFalse(os.path.exists(self.deai))

    def test_legacy_file_appearing_later_becomes_the_legacy_space(self):
        spaces.load_registry()                       # порожній віртуальний, нічого не закрито
        self.write_legacy({'a': {'dir': self.hp('Liga', 'United', 'design-work', 'a')},
                           'b': {'dir': self.hp('Liga', 'SEO', 'b')}},
                          design_work_root=self.hp('Liga', 'United', 'design-work'), registry={})
        reg = spaces.load_registry()
        want = {'version': 1, 'current': 'liga', 'spaces': [
            {'id': 'liga', 'path': self.hp('Liga'), 'legacy': True, 'integrations': True}]}
        self.assertEqual(reg, want)
        self.assertEqual(_read(self.reg_file), want)
        self.assertEqual(_mode(self.deai), 0o700)
        self.assertEqual(_mode(self.reg_file), 0o600)         # як лишає atomic_write_json
        self.assertFalse(os.path.exists(self.reg_file + '.bak'))   # першого разу копіювати нічого

    def test_an_old_file_without_any_roots_leaves_room_for_the_first_new_space(self):
        """Старий файл без `design_work_root(s)` і без задач → запасна тека legacy-простору
        `~/deai-work/main`; типова тека першого «Нового простору» `~/deai-work/personal` вільна
        (раніше вона була «над» `~/deai-work` → `path-overlap`), створення проходить."""
        self.write_legacy({})
        reg = spaces.load_registry()
        self.assertEqual([(s['legacy'], s['path']) for s in reg['spaces']],
                         [(True, self.hp('deai-work', 'main'))])
        want = self.hp('deai-work', 'personal')
        self.assertEqual(spaces.check_new_path(want, reg, spaces.all_task_dirs(reg)), (want, None))
        sid = spaces.create_space('Особисте', 'space-2', want)
        self.assertEqual([s['id'] for s in spaces.load_registry()['spaces']], ['main', sid])

    def test_quick_start_example_file_leaves_room_for_the_first_new_space(self):
        """Quick Start каже `cp tasks.example.json tasks.json`: міграція робить із цього файла
        legacy-простір, а типова тека першого «Нового простору» — `~/deai-work/<slug>`. Приклад
        із коренем `~/deai-work` ставив legacy НАД нею → `path-overlap` на першому ж просторі."""
        example = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'tasks.example.json')
        _write(self.legacy, _read(example))
        reg = spaces.load_registry()
        self.assertEqual([(s['legacy'], s['path']) for s in reg['spaces']],
                         [(True, self.hp('deai-work', 'main'))])
        want = self.hp('deai-work', 'personal')
        self.assertEqual(spaces.check_new_path(want, reg, spaces.all_task_dirs(reg)), (want, None))

    def test_second_load_changes_nothing(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        before_legacy = _md5(self.legacy)
        spaces.load_registry()
        # стара дата: якщо повторний load перепише файл, mtime зміниться
        os.utime(self.reg_file, ns=(10**9, 10**9))
        body = _bytes(self.reg_file)
        spaces.load_registry()
        self.assertEqual(os.stat(self.reg_file).st_mtime_ns, 10**9)
        self.assertEqual(_bytes(self.reg_file), body)
        self.assertEqual(_md5(self.legacy), before_legacy)

    def test_no_markers_means_integrations_off(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}, 'b': {'dir': self.hp('Liga', 'b')}})
        self.assertIs(spaces.load_registry()['spaces'][0]['integrations'], False)

    def test_marker_only_in_a_task_means_integrations_on(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')},
                           'b': {'dir': self.hp('Liga', 'b'), 'gitlab': {'project': 'g/p'}}})
        self.assertIs(spaces.load_registry()['spaces'][0]['integrations'], True)

    def test_top_level_markers_each_switch_integrations_on(self):
        for key in ('registry', 'gitlab_host_ip', 'gitlab_ssh_key'):
            with self.subTest(key=key):
                shutil.rmtree(self.deai, ignore_errors=True)
                self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, **{key: 'x'})
                self.assertIs(spaces.load_registry()['spaces'][0]['integrations'], True)

    def test_existing_registry_keeps_current_and_gets_legacy_first(self):
        personal = {'id': 'personal', 'path': self.hp('deai-work', 'personal'),
                    'legacy': False, 'integrations': False}
        self.write_registry([personal], 'personal')
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        reg = spaces.load_registry()
        self.assertEqual([s['id'] for s in reg['spaces']], ['liga', 'personal'])
        self.assertIs(reg['spaces'][0]['legacy'], True)
        self.assertEqual(reg['current'], 'personal')
        self.assertEqual(reg['spaces'][1], personal)

    def test_migration_onto_existing_registry_leaves_a_bak_with_the_old_content(self):
        self.write_registry([{'id': 'personal', 'path': self.hp('deai-work', 'personal'),
                              'legacy': False, 'integrations': False}], 'personal')
        old = _bytes(self.reg_file)
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        spaces.load_registry()
        self.assertNotEqual(_bytes(self.reg_file), old)
        self.assertEqual(_bytes(self.reg_file + '.bak'), old)

    def test_migration_rereads_the_registry_under_the_lock(self):
        """Між нелоковим читанням і локовим хтось дописав простір — міграція його не втрачає."""
        other = {'id': 'other', 'path': self.hp('deai-work', 'other'), 'legacy': False, 'integrations': False}
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        real, calls = spaces._read_registry, []

        def read_then_a_writer_strikes():
            reg = real()
            if not calls:
                calls.append(1)
                self.write_registry([other], 'other')
            return reg
        with mock.patch.object(spaces, '_read_registry', read_then_a_writer_strikes):
            spaces.load_registry()
        reg = _read(self.reg_file)
        self.assertEqual([s['id'] for s in reg['spaces']], ['liga', 'other'])
        self.assertEqual(reg['current'], 'other')

    def test_broken_legacy_file_is_not_migrated_and_not_fatal(self):
        _write(self.legacy, '{ не json')
        self.assertEqual(spaces.load_registry(), {'version': 1, 'current': None, 'spaces': []})
        self.assertFalse(os.path.exists(self.reg_file))

    def test_concurrent_first_loads_migrate_exactly_once(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        for rnd in range(15):
            with self.subTest(round=rnd):
                shutil.rmtree(self.deai, ignore_errors=True)
                out = race(8, lambda i: spaces.load_registry())
                self.assertTrue(all(kind == 'ok' for kind, _ in out), out)
                reg = _read(self.reg_file)
                self.assertEqual([s['id'] for s in reg['spaces']], ['liga'])
                for _, got in out:
                    self.assertEqual([s['id'] for s in got['spaces']], ['liga'])


class LegacyPath(Env):
    def lp(self, tasks=None, **cfg):
        cfg['tasks'] = tasks if tasks is not None else {}
        return spaces.legacy_path(cfg)

    def test_single_task_gives_work_folder_not_task_folder(self):
        d = self.hp('Liga', 'United', 'design-work')
        self.assertEqual(self.lp({'a': {'dir': os.path.join(d, 'a')}}), d)

    def test_no_tasks_uses_design_work_root(self):
        self.assertEqual(self.lp({}, design_work_root=self.hp('Work', 'dw')), self.hp('Work', 'dw'))

    def test_no_tasks_uses_design_work_roots_values(self):
        roots = {'united': self.hp('Liga', 'United', 'design-work'),
                 'seo': self.hp('Liga', 'SEO', 'design-work'), 'junk': 5}
        self.assertEqual(self.lp({}, design_work_roots=roots), self.hp('Liga'))

    def test_no_tasks_and_no_roots_falls_back_to_a_child_of_deai_work(self):
        """Запасна тека — ДОЧІРНЯ `~/deai-work/main`, а не сама `~/deai-work`: та перекриває типову
        теку нового простору `~/deai-work/<slug>` (`path-overlap` на першому ж «Новий простір»)."""
        self.assertEqual(self.lp({}), self.hp('deai-work', 'main'))

    def test_common_ancestor_with_tilde(self):
        got = self.lp({'a': {'dir': '~/Liga/X/a'}, 'b': {'dir': self.hp('Liga', 'Y', 'b')}})
        self.assertEqual(got, self.hp('Liga'))

    def test_junk_dirs_are_ignored_without_exception(self):
        junk = {'a': {'dir': 'rel/x'}, 'b': {'dir': None}, 'c': {'dir': 5}, 'd': 'not-a-dict', 'e': {}}
        self.assertEqual(self.lp(junk), self.hp('deai-work', 'main'))
        junk['f'] = {'dir': self.hp('Liga', 'Z', 'f')}
        self.assertEqual(self.lp(junk), self.hp('Liga', 'Z'))

    def test_common_part_is_home_itself_falls_back(self):
        tasks = {'a': {'dir': self.hp('a', 'x')}, 'b': {'dir': self.hp('b', 'y')}}
        self.assertEqual(self.lp(tasks), self.hp('deai-work', 'main'))
        # запасне правило бере design_work_root, якщо він прийнятний
        self.assertEqual(self.lp(tasks, design_work_root=self.hp('c')), self.hp('c'))

    def test_dir_inside_tool_folder_falls_back(self):
        got = self.lp({'a': {'dir': os.path.join(spaces.ROOT, 'x', 'a')}})
        self.assertEqual(got, self.hp('deai-work', 'main'))

    def test_non_dict_sections_do_not_crash(self):
        self.assertEqual(spaces.legacy_path({'tasks': [], 'design_work_roots': 7}), self.hp('deai-work', 'main'))

    def test_the_owners_shape_is_unchanged_by_the_fallback(self):
        """Машина власника: задачі й корені під `~/Liga` → спільний предок, запасне правило не
        вмикається (міграція не змінилась)."""
        roots = {'united': self.hp('Liga', 'United', 'design-work'), 'seo': self.hp('Liga', 'SEO', 'design-work')}
        tasks = {'a': {'dir': self.hp('Liga', 'United', 'design-work', 'a')},
                 'b': {'dir': self.hp('Liga', 'SEO', 'design-work', 'b')}}
        self.assertEqual(self.lp(tasks, design_work_roots=roots,
                                 design_work_root=self.hp('Liga', 'United', 'design-work')), self.hp('Liga'))
        self.assertEqual(self.lp({}, design_work_roots=roots), self.hp('Liga'))


class Slug(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(spaces.slug('Liga'), 'liga')
        self.assertEqual(spaces.slug('Client X!'), 'client-x')
        self.assertEqual(spaces.slug('Особисте'), '')

    def test_slug_is_cut_to_forty_after_the_edge_dashes_are_gone(self):
        self.assertEqual(spaces.slug('!' + 'a' * 45), 'a' * 40)
        self.assertEqual(spaces.slug('a' * 39 + '!!b'), 'a' * 39)      # обрізка по тире → тире геть

    def test_unique_id(self):
        self.assertEqual(spaces.unique_id('', set()), 'space-1')
        self.assertEqual(spaces.unique_id('liga', {'liga'}), 'liga-2')
        self.assertEqual(spaces.unique_id('', {'space-1'}), 'space-2')
        self.assertEqual(spaces.unique_id('liga', set()), 'liga')

    def test_unique_id_of_a_maximal_slug_still_fits_the_id_pattern(self):
        base = 'a' * 40
        got = spaces.unique_id(base, {base})
        self.assertNotEqual(got, base)
        self.assertRegex(got, spaces.SPACE_ID_RE.pattern)
        self.assertTrue(spaces.SPACE_ID_RE.fullmatch(got))


class ReadJson(Env):
    def test_size_cap(self):
        p = os.path.join(self.tmp, 'cap.json')
        # пробіли в хвості: обрізаний до ліміту файл лишається ВАЛІДНИМ JSON, тож відмовляє
        # саме перевірка розміру, а не парсер
        _write(p, '{}' + ' ' * (spaces.MAX_JSON_BYTES - 2))                # рівно ліміт
        self.assertEqual(spaces._read_json(p), {})
        _write(p, '{}' + ' ' * (spaces.MAX_JSON_BYTES - 1))                # на байт більше
        with self.assertRaises(ValueError):
            spaces._read_json(p)

    def test_deep_nesting_is_value_error_not_recursion_error(self):
        p = os.path.join(self.tmp, 'deep.json')
        _write(p, '[' * 200000)
        with self.assertRaises(ValueError):
            spaces._read_json(p)

    def test_callers_degrade_instead_of_raising(self):
        sp = {'id': 'x', 'path': self.hp('deep')}
        _write(os.path.join(sp['path'], 'space.json'), '[' * 200000)
        self.assertEqual(spaces.space_meta(sp), ('deep', 'space-1'))
        _write(os.path.join(sp['path'], 'tasks.json'), '"' + 'a' * spaces.MAX_JSON_BYTES + '"')
        self.assertEqual(spaces.task_count(sp), 0)


class Broken(Env):
    def test_unreadable_registry_raises_and_is_never_overwritten(self):
        ok = {'id': 'a', 'path': self.hp('a'), 'legacy': False, 'integrations': False}
        reg = lambda *sp, **kw: json.dumps({'version': kw.get('v', 1), 'current': 'a', 'spaces': list(sp)})  # noqa: E731
        cases = {
            'garbage': '{',
            'version-2': reg(ok, v=2),
            'no-path': reg({'id': 'a'}),
            'relative-path': reg(dict(ok, path='rel/dir')),
            # рукописний реєстр: NUL і самотній сурогат (JSON його приймає) — шлях, на якому
            # `realpath` кидає ValueError/UnicodeEncodeError, тож це не шлях, а `spaces-unreadable`
            'path-with-nul': reg(dict(ok, path=self.hp('a') + '\0x')),
            'path-lone-surrogate': reg(dict(ok, path=self.hp('a', '\ud800'))),
            'bad-id-upper': reg(dict(ok, id='Bad')),
            'bad-id-traversal': reg(dict(ok, id='../x')),
            'bad-id-too-long': reg(dict(ok, id='a' * 41)),
            'id-not-str': reg(dict(ok, id=5)),
            'duplicate-ids': reg(ok, dict(ok, path=self.hp('b'))),
            'integrations-not-bool': reg(dict(ok, integrations='yes')),
            'integrations-number': reg(dict(ok, integrations=1)),
            'integrations-null': reg(dict(ok, integrations=None)),
            'legacy-not-bool': reg(dict(ok, legacy=1)),
            'legacy-string': reg(dict(ok, legacy='true')),
            'spaces-not-list': json.dumps({'version': 1, 'current': None, 'spaces': {}}),
            'top-level-list': '[]',
            'too-big': ' ' * (spaces.MAX_JSON_BYTES + 1) + '{}',
            'too-deep': '[' * 200000,
        }
        # старий файл є: міграція вже спробувала б дописати простір у битий реєстр
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        for name, text in cases.items():
            with self.subTest(case=name):
                _write(self.reg_file, text)
                with self.assertRaises(spaces.SpacesError) as cm:
                    spaces.load_registry()
                self.assertEqual(cm.exception.code, 'spaces-unreadable')
                with open(self.reg_file, encoding='utf-8') as f:
                    self.assertEqual(f.read(), text)

    def test_flags_may_be_absent_from_a_registry_entry(self):
        self.write_registry([{'id': 'a', 'path': self.hp('a')}], 'a')
        reg = spaces.load_registry()
        self.assertEqual(reg['spaces'], [{'id': 'a', 'path': self.hp('a')}])
        self.assertIs(spaces.integrations_for(reg['spaces'][0]), False)

    def test_valid_registry_with_max_length_id_is_accepted(self):
        self.write_registry([{'id': 'a' * 40, 'path': self.hp('a'), 'legacy': False, 'integrations': False}], None)
        self.assertEqual(spaces.load_registry()['spaces'][0]['id'], 'a' * 40)

    def test_registry_write_failure_is_spaces_unwritable(self):
        _write(self.deai, 'я файл, а не тека')              # DEAI_HOME — звичайний файл
        with self.assertRaises(spaces.SpacesError) as cm, spaces.WRITE_LOCK:
            spaces._write_locked({'version': 1, 'current': None, 'spaces': []})
        self.assertEqual(cm.exception.code, 'spaces-unwritable')


class FindTask(Env):
    def test_resolves_task_to_its_space(self):
        self.two_spaces()
        self.assertEqual(spaces.find_task('x')['id'], 'p')
        self.assertIs(spaces.find_task('a')['legacy'], True)
        self.assertIsNone(spaces.find_task('nope'))
        self.assertIsNone(spaces.find_task(None))

    def test_same_id_in_two_spaces_is_ambiguous(self):
        self.two_spaces()
        cfg = _read(self.legacy)
        cfg['tasks']['x'] = {'dir': self.hp('Liga', 'x', 'x')}
        _write(self.legacy, cfg)
        with self.assertRaises(spaces.AmbiguousTask):
            spaces.find_task('x')
        self.assertEqual(spaces.find_task('a')['id'], 'liga')   # решта задач резолвиться


class RequestSpace(Env):
    def test_raw_value_has_three_states(self):
        self.assertIsNone(spaces.request_space_id())
        spaces.set_request_space('p')
        self.assertEqual(spaces.request_space_id(), 'p')
        spaces.set_request_space('')
        self.assertEqual(spaces.request_space_id(), '')
        spaces.clear_request_space()
        self.assertIsNone(spaces.request_space_id())

    def test_context_manager_sets_and_restores_the_previous_value(self):
        with spaces.request_space('p'):
            self.assertEqual(spaces.request_space_id(), 'p')
            with spaces.request_space(''):
                self.assertEqual(spaces.request_space_id(), '')
            self.assertEqual(spaces.request_space_id(), 'p')
        self.assertIsNone(spaces.request_space_id())

    def test_context_manager_restores_after_an_exception(self):
        spaces.set_request_space('liga')
        with self.assertRaises(RuntimeError):
            with spaces.request_space('p'):
                raise RuntimeError('boom')
        self.assertEqual(spaces.request_space_id(), 'liga')

    def test_context_manager_does_not_leak_into_other_threads(self):
        seen = []
        with spaces.request_space('p'):
            t = threading.Thread(target=lambda: seen.append(spaces.request_space_id()))
            t.start()
            t.join()
        self.assertEqual(seen, [None])


class ActiveSpace(Env):
    def test_defaults_to_current_then_request_space_then_current_again(self):
        self.two_spaces()
        self.assertEqual(spaces.active_space()['id'], 'liga')
        self.assertEqual(spaces.active_tasks_file(), self.legacy)
        spaces.set_request_space('p')
        self.assertEqual(spaces.active_space()['id'], 'p')
        self.assertEqual(spaces.active_tasks_file(), os.path.join(self.p_path, 'tasks.json'))
        spaces.clear_request_space()
        self.assertEqual(spaces.active_space()['id'], 'liga')

    def test_request_space_is_thread_local(self):
        self.two_spaces()
        spaces.set_request_space('p')
        seen = {}
        t = threading.Thread(target=lambda: seen.update(other=spaces.active_space()['id']))
        t.start()
        t.join()
        self.assertEqual(seen['other'], 'liga')           # чужий потік простору не бачить
        spaces.clear_request_space()

        def work():
            spaces.set_request_space('p')
            seen['inner'] = spaces.active_space()['id']
        t = threading.Thread(target=work)
        t.start()
        t.join()
        self.assertEqual(seen['inner'], 'p')
        self.assertEqual(spaces.active_space()['id'], 'liga')   # і наш не змінився

    def test_unknown_request_space_does_not_fall_back_to_another_one(self):
        self.two_spaces()
        spaces.set_request_space('ghost')
        self.assertIsNone(spaces.active_space())
        with self.assertRaises(spaces.NoTask):
            spaces.active_tasks_file()

    def test_empty_request_space_means_no_space_even_when_spaces_exist(self):
        self.two_spaces()
        with spaces.request_space(''):
            self.assertIsNone(spaces.active_space())
            with self.assertRaises(spaces.NoTask):
                spaces.active_tasks_file()

    def test_empty_request_space_does_not_read_the_registry(self):
        _write(self.reg_file, '{ битий')
        with spaces.request_space(''):
            self.assertIsNone(spaces.active_space())       # не кинув SpacesError

    def test_stale_current_falls_back_to_first_space(self):
        self.two_spaces()
        reg = _read(self.reg_file)
        reg['current'] = 'ghost'
        _write(self.reg_file, reg)
        self.assertEqual(spaces.active_space()['id'], 'liga')

    def test_no_spaces_at_all_raises_no_task(self):
        self.assertIsNone(spaces.active_space())
        with self.assertRaises(spaces.NoTask) as cm:
            spaces.active_tasks_file()
        self.assertIsNone(cm.exception.space)

    def test_default_new_task_space_prefers_the_legacy_entry_then_current(self):
        """4d-4c (Д1): перший запис із `legacy: true`, а не з прапорця `integrations`; без нього — поточний."""
        self.two_spaces()
        spaces.switch_space('p')
        self.assertEqual(spaces.default_new_task_space()['id'], 'liga')
        reg = _read(self.reg_file)
        reg['spaces'][0]['integrations'] = False                 # прапорець ні на що не впливає
        _write(self.reg_file, reg)
        self.assertEqual(spaces.default_new_task_space()['id'], 'liga')
        reg['spaces'][0]['legacy'] = False
        _write(self.reg_file, reg)
        os.remove(spaces.legacy_tasks_file())                    # інакше перша міграція повернула б запис `legacy`
        self.assertEqual(spaces.default_new_task_space()['id'], 'p')


class Integrations(Env):
    def test_no_request_space_means_on_and_the_registry_is_never_touched(self):
        """Інструменти ЛІГА (doctor, registry, тести без ізоляції): простору запиту нема —
        інтеграції є, і `<DEAI_HOME>` ми не створюємо й не читаємо."""
        self.assertIsNone(spaces.request_space_id())
        self.assertIs(spaces.integrations_on(), True)
        spaces.require_integrations()
        self.assertFalse(os.path.exists(self.deai))

    def test_no_request_space_ignores_even_a_broken_registry(self):
        _write(self.reg_file, '{ битий')
        self.assertIs(spaces.integrations_on(), True)          # не кинув SpacesError
        self.assertEqual(_bytes(self.reg_file), '{ битий'.encode())

    def test_no_request_space_ignores_the_current_space(self):
        self.two_spaces()
        spaces.switch_space('p')                               # поточний — без інтеграцій
        self.assertIs(spaces.integrations_on(), True)
        spaces.require_integrations()

    def test_request_space_decides(self):
        self.two_spaces()
        with spaces.request_space('liga'):
            self.assertIs(spaces.integrations_on(), True)
            spaces.require_integrations()
        with spaces.request_space('p'):
            self.assertIs(spaces.integrations_on(), False)
            with self.assertRaises(spaces.IntegrationsOff) as cm:
                spaces.require_integrations()
            self.assertIsInstance(cm.exception, OSError)   # наявні `except OSError` деградують чесно
        with spaces.request_space(''):
            self.assertIs(spaces.integrations_on(), False)  # запит без простору
        with spaces.request_space('ghost'):
            self.assertIs(spaces.integrations_on(), False)  # невідомий простір

    def test_integrations_for(self):
        self.assertIs(spaces.integrations_for(None), False)
        self.assertIs(spaces.integrations_for({}), False)
        self.assertIs(spaces.integrations_for({'integrations': 0}), False)
        self.assertIs(spaces.integrations_for({'integrations': False}), False)
        self.assertIs(spaces.integrations_for({'integrations': True}), True)
        # вимикач закривається: усе, що не рівно True, — «ні»
        for junk in ('yes', 1, [1], {'a': 1}, 'true'):
            with self.subTest(value=junk):
                self.assertIs(spaces.integrations_for({'integrations': junk}), False)


class RegistryHelpers(Env):
    def test_current_id(self):
        self.assertIsNone(spaces.current_id())                  # просторів нема
        self.two_spaces()
        self.assertEqual(spaces.current_id(), 'liga')
        spaces.switch_space('p')
        self.assertEqual(spaces.current_id(), 'p')

    def test_space_current_task(self):
        self.two_spaces()
        p_file = os.path.join(self.p_path, 'tasks.json')
        _write(p_file, {'current': 'x', 'tasks': {'x': {}}})
        self.assertEqual(spaces.space_current_task('p'), 'x')
        _write(self.legacy, {'current': 'a', 'tasks': {'a': {}, 'b': {}}})
        self.assertEqual(spaces.space_current_task('liga'), 'a')
        # `current` вказує на задачу, якої нема / нема ключа / не рядок
        for cfg in ({'current': 'ghost', 'tasks': {'x': {}}}, {'tasks': {'x': {}}},
                    {'current': 5, 'tasks': {'x': {}}}, {'current': 'x'}, {'current': 'x', 'tasks': []}, []):
            with self.subTest(cfg=cfg):
                _write(p_file, cfg)
                self.assertIsNone(spaces.space_current_task('p'))
        _write(p_file, '{ битий')
        self.assertIsNone(spaces.space_current_task('p'))
        os.remove(p_file)
        self.assertIsNone(spaces.space_current_task('p'))       # файла нема
        self.assertIsNone(spaces.space_current_task('ghost'))   # простору нема

    def test_read_registry_never_migrates(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        self.assertEqual(spaces.read_registry(), {'version': 1, 'current': None, 'spaces': []})
        self.assertFalse(os.path.exists(self.deai))
        spaces.load_registry()                                  # а ось це мігрує
        self.assertEqual([s['id'] for s in spaces.read_registry()['spaces']], ['liga'])

    def test_task_ids_by_space_lists_every_space_that_holds_an_id(self):
        """Дубль між просторами видно як список довший за один елемент, у порядку реєстру."""
        self.two_spaces()
        reg = spaces.read_registry()
        self.assertEqual(spaces.task_ids_by_space(reg), {'a': ['liga'], 'x': ['p']})
        cfg = _read(self.legacy)
        cfg['tasks']['x'] = {'dir': self.hp('Liga', 'x', 'x')}
        _write(self.legacy, cfg)
        by = spaces.task_ids_by_space(reg)
        self.assertEqual(by['x'], ['liga', 'p'])
        self.assertEqual(by['a'], ['liga'])

    def test_task_ids_by_space_reads_like_find_task_and_writes_nothing(self):
        """Нечитабельний файл задач — порожній (його показує `unreadable_task_files`), простір без
        файла — теж; і, на відміну від `load_registry`, нічого не мігрує."""
        self.two_spaces()
        reg = spaces.read_registry()
        _write(os.path.join(self.p_path, 'tasks.json'), '{ битий')
        os.remove(self.legacy)
        self.assertEqual(spaces.task_ids_by_space(reg), {})
        self.assertEqual(spaces.task_ids_by_space({'version': 1, 'current': None, 'spaces': []}), {})
        before = _bytes(self.reg_file)
        spaces.task_ids_by_space(reg)
        self.assertEqual(_bytes(self.reg_file), before)
        self.assertFalse(os.path.exists(self.reg_file + '.bak'))

    def test_read_registry_raises_on_a_broken_file(self):
        _write(self.reg_file, '{')
        with self.assertRaises(spaces.SpacesError):
            spaces.read_registry()

    def test_task_count(self):
        self.two_spaces()
        self.assertEqual(spaces.task_count(spaces.find_task('x')), 1)
        _write(self.legacy, {'tasks': {'a': {}, 'b': {}, 'c': {}}})
        self.assertEqual(spaces.task_count({'id': 'liga', 'legacy': True, 'path': self.hp('Liga')}), 3)
        self.assertEqual(spaces.task_count({'id': 'z', 'path': self.hp('nope')}), 0)


class LayerOff(Env):
    def test_only_dc_tasks_file_means_old_behaviour(self):
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}})
        self.assertIs(spaces.layer_on(), False)
        self.assertEqual(spaces.active_tasks_file(), self.legacy)
        self.assertIs(spaces.integrations_on(), True)
        self.assertEqual(spaces.find_task('a')['id'], 'legacy')
        self.assertIsNone(spaces.find_task('nope'))
        spaces.switch_space('whatever')                   # шар вимкнено — мовчки, без запису
        self.assertFalse(os.path.exists(self.hp('.deai')))

    def test_helpers_work_off_the_legacy_file_and_leave_no_trace(self):
        """`space_current_task`, `task_count`, `current_id` у вимкненому шарі беруть неявний
        простір (старий файл), а не читають реєстр у `<HOME>/.deai`."""
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}, 'b': {'dir': self.hp('Liga', 'b')}}, current='a')
        self.assertEqual(spaces.space_current_task('legacy'), 'a')
        self.assertIsNone(spaces.space_current_task('ghost'))
        self.assertEqual(spaces.task_count(spaces.active_space()), 2)
        self.assertEqual(spaces.current_id(), 'legacy')
        self.assertFalse(os.path.exists(self.hp('.deai')))

    def test_integrations_are_on_whatever_the_request_space(self):
        del os.environ['DEAI_HOME']
        for sid in (None, '', 'p'):
            with self.subTest(request=sid):
                with spaces.request_space(sid):
                    self.assertIs(spaces.integrations_on(), True)

    def test_load_registry_is_virtual_and_does_not_touch_deai_home(self):
        """Старий файл є, `DEAI_HOME` нема: при ввімкненому шарі тут була б міграція
        в `<HOME>/.deai/spaces.json`. Вимкнений шар — лише віртуальний реєстр."""
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        reg = spaces.load_registry()
        self.assertEqual(reg, {'version': 1, 'current': 'legacy', 'spaces': [dict(spaces.IMPLICIT)]})
        self.assertFalse(os.path.exists(self.hp('.deai')))
        self.assertFalse(os.path.exists(spaces.registry_path()))

    def test_load_registry_does_not_even_read_a_registry_there(self):
        del os.environ['DEAI_HOME']
        reg_file = self.hp('.deai', 'spaces.json')
        _write(reg_file, '{ битий')
        self.assertEqual(spaces.load_registry()['current'], 'legacy')   # не кинув SpacesError
        self.assertEqual(spaces.read_registry()['current'], 'legacy')   # і публічний читач теж
        self.assertEqual(spaces.current_id(), 'legacy')
        with open(reg_file, encoding='utf-8') as f:
            self.assertEqual(f.read(), '{ битий')
        self.assertEqual(os.listdir(self.hp('.deai')), ['spaces.json'])  # і не лишив .bak

    def test_virtual_registry_is_a_copy_not_the_constant(self):
        del os.environ['DEAI_HOME']
        for get in (spaces.load_registry, spaces.read_registry):
            reg = get()
            reg['spaces'][0]['integrations'] = False
            reg['spaces'][0]['id'] = 'hacked'
        self.assertIs(spaces.IMPLICIT['integrations'], True)
        self.assertEqual(spaces.IMPLICIT['id'], 'legacy')
        self.assertEqual(spaces.load_registry()['spaces'][0], spaces.IMPLICIT)
        self.assertIsNot(spaces.load_registry()['spaces'][0], spaces.IMPLICIT)

    def test_implicit_space_is_never_returned_by_reference(self):
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}})
        for name, get in (('active_space', spaces.active_space),
                          ('find_task', lambda: spaces.find_task('a')),
                          ('default_new_task_space', spaces.default_new_task_space)):
            with self.subTest(fn=name):
                got = get()
                self.assertEqual(got, spaces.IMPLICIT)
                self.assertIsNot(got, spaces.IMPLICIT)
                got['integrations'] = False
                self.assertIs(spaces.IMPLICIT['integrations'], True)

    def test_describe_hides_the_implicit_space(self):
        del os.environ['DEAI_HOME']
        self.assertIsNone(spaces.describe(spaces.active_space()))
        self.assertIsNone(spaces.describe(dict(spaces.IMPLICIT)))
        self.assertIsNone(spaces.describe(None))
        # справжній простір зі слагом `legacy` має шлях — він НЕ неявний
        real = {'id': 'legacy', 'path': self.hp('work'), 'legacy': False, 'integrations': False}
        self.assertEqual(spaces.describe(real)['id'], 'legacy')

    def test_writers_refuse_with_spaces_off_and_leave_no_trace(self):
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        calls = {
            'create_space': lambda: spaces.create_space('X', 'space-1', self.hp('deai-work', 'x')),
            'update_space': lambda: spaces.update_space('legacy', name='X'),
            '_write_locked': lambda: spaces._write_locked({'version': 1, 'current': None, 'spaces': []}),
        }
        for name, call in calls.items():
            with self.subTest(call=name):
                with self.assertRaises(spaces.SpacesError) as cm:
                    call()
                self.assertEqual(cm.exception.code, 'spaces-off')
        self.assertFalse(os.path.exists(self.hp('.deai')))
        self.assertFalse(os.path.exists(self.hp('deai-work')))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.legacy), 'space.json')))


class NewPath(Env):
    REG = {'version': 1, 'current': None, 'spaces': []}

    def check(self, path, reg=None, task_dirs=()):
        return spaces.check_new_path(path, reg or self.REG, list(task_dirs))

    def reg_with(self, *paths):
        return {'version': 1, 'current': None, 'spaces': [
            {'id': f's{i}', 'path': p, 'legacy': False, 'integrations': False} for i, p in enumerate(paths)]}

    def test_relative_path(self):
        self.assertEqual(self.check('deai-work/x'), (None, 'path-not-absolute'))
        self.assertEqual(self.check(''), (None, 'path-not-absolute'))
        self.assertEqual(self.check(None), (None, 'path-not-absolute'))

    def test_nul_byte_is_rejected_up_front(self):
        self.assertEqual(self.check(self.hp('deai-work', 'a\0b')), (None, 'path-not-absolute'))
        self.assertEqual(self.check('/a\0'), (None, 'path-not-absolute'))

    def test_too_broad(self):
        for p in ('/', self.home, os.path.dirname(self.home)):
            with self.subTest(path=p):
                self.assertEqual(self.check(p), (None, 'path-too-broad'))

    def test_double_leading_slash_is_not_a_way_round(self):
        self.assertEqual(self.check('//usr/x'), (None, 'path-system'))
        self.assertEqual(self.check('/' + self.home), (None, 'path-too-broad'))
        self.assertEqual(self.check('/' + self.hp('.ssh')), (None, 'path-system'))
        self.assertEqual(self.check('//'), (None, 'path-too-broad'))

    def test_system_places(self):
        for p in (self.hp('Library', 'x'), self.hp('.ssh'), self.hp('.deai', 'x'), '/usr/x',
                  self.hp('LIBRARY', 'x'), self.hp('library')):
            with self.subTest(path=p):
                self.assertEqual(self.check(p), (None, 'path-system'))

    def test_symlink_in_home_to_a_dotfolder_is_still_system(self):
        os.makedirs(self.hp('.ssh'))
        os.symlink(self.hp('.ssh'), self.hp('proj'))
        self.assertEqual(self.check(self.hp('proj', 'x')), (None, 'path-system'))

    def test_symlink_in_home_out_to_a_system_folder_is_system(self):
        os.symlink('/usr', self.hp('out'))
        self.assertEqual(self.check(self.hp('out', 'x')), (None, 'path-system'))

    def test_system_check_looks_at_the_real_location_of_the_path(self):
        """Текстово шлях «чистий», справжній — системний. Створити симлінк поза `/var/folders`
        на macOS нічим, тому `realpath` підміняємо."""
        real = os.path.realpath

        def fake(p, *a, **kw):
            return '/usr/local/x' if str(p).startswith('/Volumes/link') else real(p, *a, **kw)
        self.assertEqual(self.check('/Volumes/link/x'), ('/Volumes/link/x', None))
        with mock.patch('os.path.realpath', fake):
            self.assertEqual(self.check('/Volumes/link/x'), (None, 'path-system'))

    def test_symlink_alias_of_home_is_home(self):
        alias = os.path.join(self.tmp, 'alias')
        os.symlink(self.home, alias)
        self.assertEqual(self.check(alias), (None, 'path-too-broad'))
        self.assertEqual(self.check(os.path.join(alias, '.ssh')), (None, 'path-system'))
        want = os.path.join(alias, 'deai-work', 'x')
        self.assertEqual(self.check(want), (want, None))

    def test_system_dirs_are_exactly_the_spec_list(self):
        self.assertEqual(set(spaces.SYSTEM_DIRS), {'/System', '/Library', '/usr', '/bin', '/sbin',
                                                   '/etc', '/private', '/var', '/Applications'})

    def test_places_the_spec_does_not_list_are_not_system(self):
        """Не залежить від диска (чи є `/opt`, чи це симлінк) і від місця checkout-а:
        `ROOT` підміняємо, а відповідь лише «не path-system»."""
        with mock.patch.object(spaces, 'ROOT', self.hp('tool', 'design-canvas')):
            for p in ('/Volumes/Work/x', '/opt/work', '/Users/Shared/x'):
                with self.subTest(path=p):
                    self.assertNotEqual(self.check(p)[1], 'path-system')

    def test_existing_file_is_not_a_folder(self):
        f = self.hp('deai-work', 'afile')
        _write(f, 'x')
        self.assertEqual(self.check(f), (None, 'path-not-dir'))
        self.assertEqual(self.check(self.hp('deai-work', 'afile', 'sub')), (self.hp('deai-work', 'afile', 'sub'), None))

    def test_tool_folder_and_above_it(self):
        # checkout під системною текою (CI в /opt…) дає path-system РАНІШЕ за path-tool:
        # домівка тестів стоїть деінде. На звичайній машині вимога строга.
        in_system = any(spaces.ROOT == d or spaces.ROOT.startswith(d + os.sep)
                        for d in spaces.SYSTEM_DIRS)
        want = ('path-tool', 'path-system') if in_system else ('path-tool',)
        for p in (spaces.ROOT, os.path.dirname(spaces.ROOT)):
            with self.subTest(path=p):
                got, why = self.check(p)
                self.assertIsNone(got)
                self.assertIn(why, want)

    def test_tool_folder_check_does_not_depend_on_where_the_checkout_lives(self):
        fake = self.hp('tool', 'design-canvas')
        with mock.patch.object(spaces, 'ROOT', fake):
            self.assertEqual(self.check(fake), (None, 'path-tool'))
            self.assertEqual(self.check(os.path.dirname(fake)), (None, 'path-tool'))
            self.assertEqual(self.check(os.path.join(fake, 'x')), (None, 'path-tool'))
            self.assertEqual(self.check(self.hp('tool-other')), (self.hp('tool-other'), None))
            # сусід з тим самим початком імені — не частина теки інструмента
            self.assertEqual(self.check(fake + '-other'), (fake + '-other', None))

    def test_registered_and_overlapping(self):
        reg = self.reg_with(self.hp('deai-work', 'a'))
        self.assertEqual(self.check(self.hp('deai-work', 'a'), reg), (None, 'path-registered'))
        self.assertEqual(self.check(self.hp('deai-work', 'a', 'sub'), reg), (None, 'path-overlap'))
        self.assertEqual(self.check(self.hp('deai-work'), reg), (None, 'path-overlap'))
        dirs = [self.hp('Work', 't1')]
        self.assertEqual(self.check(self.hp('Work', 't1', 'inner'), reg, dirs), (None, 'path-overlap'))
        self.assertEqual(self.check(self.hp('Work'), reg, dirs), (None, 'path-overlap'))

    def test_sibling_with_a_common_name_prefix_is_not_an_overlap(self):
        reg = self.reg_with(self.hp('deai-work', 'a'))
        dirs = [self.hp('Work', 't1')]
        for p in (self.hp('deai-work', 'ab'), self.hp('Work', 't10')):
            with self.subTest(path=p):
                self.assertEqual(self.check(p, reg, dirs), (p, None))

    def test_registered_path_is_compared_in_nfc(self):
        composed = 'café'
        decomposed = unicodedata.normalize('NFD', composed)
        self.assertNotEqual(composed, decomposed)
        reg = self.reg_with(self.hp('deai-work', composed))
        self.assertEqual(self.check(self.hp('deai-work', decomposed), reg), (None, 'path-registered'))
        self.assertEqual(self.check(self.hp('deai-work', decomposed, 'sub'), reg), (None, 'path-overlap'))
        # ... і обернено: у реєстрі NFD, питаємо NFC
        reg = self.reg_with(self.hp('deai-work', decomposed))
        self.assertEqual(self.check(self.hp('deai-work', composed), reg), (None, 'path-registered'))

    def test_registered_symlink_alias_is_registered(self):
        os.makedirs(self.hp('deai-work', 'real'))
        os.symlink(self.hp('deai-work', 'real'), self.hp('deai-work', 'link'))
        reg = self.reg_with(self.hp('deai-work', 'real'))
        self.assertEqual(self.check(self.hp('deai-work', 'link'), reg), (None, 'path-registered'))
        self.assertEqual(self.check(self.hp('deai-work', 'link', 'sub'), reg), (None, 'path-overlap'))

    # ---------- той самий каталог під іншим регістром (macOS: APFS без урахування регістру) ----------

    def case_insensitive(self):
        """Файлова система тимчасової теки не розрізняє регістр? Інакше тести цього блоку
        нічого не доводять — пропуск із причиною (а не зелене «нічого не перевірено»)."""
        probe = os.path.join(self.tmp, 'CaseProbe')
        os.makedirs(probe)
        if not os.path.exists(os.path.join(self.tmp, 'caseprobe')):
            self.skipTest('файлова система тимчасової теки розрізняє регістр імен (CaseProbe ≠ caseprobe): '
                          'варіант `CASEa` проти `caseA` там — інша тека')
        self.assertTrue(os.path.samefile(probe, os.path.join(self.tmp, 'caseprobe')))

    def test_a_case_variant_of_a_registered_folder_is_registered(self):
        self.case_insensitive()
        os.makedirs(self.hp('deai-work', 'caseA'))
        reg = self.reg_with(self.hp('deai-work', 'caseA'))
        self.assertEqual(self.check(self.hp('deai-work', 'CASEa'), reg), (None, 'path-registered'))
        self.assertEqual(self.check(self.hp('deai-work', 'caseA'), reg), (None, 'path-registered'))
        # ... і обернено: у реєстрі інший регістр, ніж питаємо
        reg = self.reg_with(self.hp('deai-work', 'CASEA'))
        self.assertEqual(self.check(self.hp('deai-work', 'casea'), reg), (None, 'path-registered'))

    def test_a_case_variant_subfolder_or_parent_of_a_registered_folder_is_an_overlap(self):
        self.case_insensitive()
        os.makedirs(self.hp('deai-work', 'caseA', 'inner'))
        reg = self.reg_with(self.hp('deai-work', 'caseA'))
        # підтека, якої ще нема на диску: предок з іншим регістром — та сама тека, що в реєстрі
        self.assertEqual(self.check(self.hp('deai-work', 'CASEA', 'sub'), reg), (None, 'path-overlap'))
        self.assertEqual(self.check(self.hp('deai-work', 'CASEA', 'inner'), reg), (None, 'path-overlap'))
        # зареєстрована тека ВСЕРЕДИНІ того, що питаємо (інший регістр предка)
        reg = self.reg_with(self.hp('deai-work', 'caseA', 'inner'))
        self.assertEqual(self.check(self.hp('deai-work', 'CASEA'), reg), (None, 'path-overlap'))

    def test_a_case_variant_of_a_task_folder_is_an_overlap(self):
        self.case_insensitive()
        os.makedirs(self.hp('Work', 'caseT', 't1'))
        dirs = [self.hp('Work', 'caseT', 't1')]
        self.assertEqual(self.check(self.hp('Work', 'CASET'), self.REG, dirs), (None, 'path-overlap'))
        self.assertEqual(self.check(self.hp('Work', 'CASET', 'T1', 'x'), self.REG, dirs), (None, 'path-overlap'))
        self.assertEqual(self.check(self.hp('Work', 'caseT', 't2'), self.REG, dirs), (self.hp('Work', 'caseT', 't2'), None))

    def test_a_case_variant_of_a_folder_that_is_not_registered_is_fine(self):
        """Контроль: тека справді інша (`caseB` поряд із зареєстрованою `caseA`) — не збіг."""
        self.case_insensitive()
        os.makedirs(self.hp('deai-work', 'caseA'))
        reg = self.reg_with(self.hp('deai-work', 'caseA'))
        for p in (self.hp('deai-work', 'CASEB'), self.hp('deai-work', 'caseAB'), self.hp('deai-work', 'CASEAB', 'x')):
            with self.subTest(path=p):
                self.assertEqual(self.check(p, reg), (p, None))

    def test_a_registered_folder_that_is_gone_falls_back_to_the_text_comparison(self):
        """Теки нема на диску — порівнювати файловою системою нічим: лишається текст/realpath у NFC
        (той самий регістр — збіг; інший регістр — невідомо, пускаємо, як і було)."""
        reg = self.reg_with(self.hp('deai-work', 'Ghost'))
        self.assertEqual(self.check(self.hp('deai-work', 'Ghost'), reg), (None, 'path-registered'))
        self.assertEqual(self.check(self.hp('deai-work', 'Ghost', 'x'), reg), (None, 'path-overlap'))

    def test_fine_path_is_returned_normalised(self):
        want = self.hp('deai-work', 'personal')
        self.assertEqual(self.check(want), (want, None))
        self.assertEqual(self.check(want + '/'), (want, None))
        self.assertEqual(self.check(self.hp('deai-work', 'x', '..', 'personal')), (want, None))
        self.assertEqual(self.check('~/deai-work/personal'), (want, None))
        self.assertEqual(self.check('/' + want), (want, None))      # `//…` → один провідний `/`

    def test_home_and_path_in_different_unicode_forms_are_the_same_home(self):
        """macOS віддає імена в NFD, а користувач друкує NFC: правила домівки мусять це
        знати, інакше `relpath` дає `..` і будь-який шлях стає «системним»."""
        name = 'Андрій'
        nfd, nfc = unicodedata.normalize('NFD', name), unicodedata.normalize('NFC', name)
        self.assertNotEqual(nfd, nfc)
        base = os.path.join(self.tmp, 'users')
        for home_form, typed_form in ((nfd, nfc), (nfc, nfd)):
            with self.subTest(home=home_form == nfd and 'NFD' or 'NFC'):
                os.environ['HOME'] = os.path.join(base, home_form)
                want = os.path.join(base, typed_form, 'deai-work', 'x')
                self.assertEqual(self.check(want), (want, None))
                self.assertEqual(self.check(os.path.join(base, typed_form, '.ssh')), (None, 'path-system'))
                self.assertEqual(self.check(os.path.join(base, typed_form, 'Library', 'x')), (None, 'path-system'))
                self.assertEqual(self.check(os.path.join(base, typed_form)), (None, 'path-too-broad'))

    def test_home_rules_win_over_system_dirs(self):
        """Домівка під системною текою (macOS: /var/folders/…) — це все одно домівка:
        шлях усередині неї системним не вважається. Суто текстово, без диска."""
        os.environ['HOME'] = '/var/tmp/spaces-textual-home'
        self.assertTrue(any('/var/tmp/x'.startswith(d + '/') for d in spaces.SYSTEM_DIRS))
        want = '/var/tmp/spaces-textual-home/deai-work/personal'
        self.assertEqual(self.check(want), (want, None))
        self.assertEqual(self.check('/var/tmp/spaces-textual-home/Library/x'), (None, 'path-system'))
        self.assertEqual(self.check('/var/tmp/other'), (None, 'path-system'))   # поза домівкою — системна


class Peek(Env):
    def test_happy_path(self):
        p = self.hp('deai-work', 'adopt')
        _write(os.path.join(p, 'space.json'), {'name': 'Усиновлений', 'color': 'space-4'})
        _write(os.path.join(p, 'tasks.json'), {'tasks': {'a': {}, 'b': {}}})
        self.assertEqual(spaces.peek(p), {'path': p, 'exists': True, 'name': 'Усиновлений',
                                          'color': 'space-4', 'tasks': 2})

    def test_empty_folder_and_missing_folder(self):
        os.makedirs(self.hp('deai-work', 'empty'))
        self.assertEqual(spaces.peek(self.hp('deai-work', 'empty')),
                         {'path': self.hp('deai-work', 'empty'), 'exists': True})
        self.assertEqual(spaces.peek(self.hp('deai-work', 'nope')),
                         {'path': self.hp('deai-work', 'nope'), 'exists': False})

    def test_tilde_and_double_slash_are_normalised(self):
        os.makedirs(self.hp('deai-work', 'e'))
        want = {'path': self.hp('deai-work', 'e'), 'exists': True}
        self.assertEqual(spaces.peek('~/deai-work/e'), want)
        self.assertEqual(spaces.peek('/' + self.hp('deai-work', 'e')), want)

    def registry_with(self, *paths):
        self.write_registry([{'id': f's{i}', 'path': p, 'legacy': False, 'integrations': False}
                             for i, p in enumerate(paths)], 's0')

    def test_a_registered_folder_says_registered(self):
        p = self.hp('deai-work', 'reg')
        _write(os.path.join(p, 'space.json'), {'name': 'Реєстрований', 'color': 'space-2'})
        self.registry_with(self.hp('deai-work', 'other'), p)
        before = _md5(self.reg_file)
        self.assertEqual(spaces.peek(p), {'path': p, 'exists': True, 'name': 'Реєстрований',
                                          'color': 'space-2', 'registered': True})
        self.assertEqual(spaces.peek('~/deai-work/reg')['registered'], True)
        self.assertEqual(_md5(self.reg_file), before, 'peek переписав реєстр')

    def test_a_folder_that_is_not_registered_has_no_registered_key(self):
        os.makedirs(self.hp('deai-work', 'free'))
        self.registry_with(self.hp('deai-work', 'other'))
        self.assertEqual(spaces.peek(self.hp('deai-work', 'free')),
                         {'path': self.hp('deai-work', 'free'), 'exists': True})
        # підтека зареєстрованої — не «зареєстрована» (це `path-overlap`, а не збіг теки)
        os.makedirs(self.hp('deai-work', 'other', 'sub'))
        self.assertNotIn('registered', spaces.peek(self.hp('deai-work', 'other', 'sub')))

    def test_a_case_variant_of_a_registered_folder_says_registered(self):
        probe = os.path.join(self.tmp, 'CaseProbe')
        os.makedirs(probe)
        if not os.path.exists(os.path.join(self.tmp, 'caseprobe')):
            self.skipTest('файлова система тимчасової теки розрізняє регістр імен: варіант регістру там — інша тека')
        os.makedirs(self.hp('deai-work', 'caseA'))
        self.registry_with(self.hp('deai-work', 'caseA'))
        got = spaces.peek(self.hp('deai-work', 'CASEa'))
        self.assertEqual((got['exists'], got.get('registered')), (True, True))
        self.assertEqual(got['path'], self.hp('deai-work', 'CASEa'))     # шлях віддаємо, як ввели

    def test_a_registered_folder_that_is_not_on_disk_is_compared_by_text(self):
        self.registry_with(self.hp('deai-work', 'Ghost'))
        self.assertEqual(spaces.peek(self.hp('deai-work', 'Ghost')),
                         {'path': self.hp('deai-work', 'Ghost'), 'exists': False, 'registered': True})
        self.assertNotIn('registered', spaces.peek(self.hp('deai-work', 'Other')))

    def test_peek_stays_a_plain_answer_when_the_registry_cannot_be_read(self):
        """Пошкоджений реєстр — не привід кидати: «зареєстровано чи ні» невідомо, ключа нема; решта
        відповіді — як була (маршрут `space-peek` завжди 200)."""
        os.makedirs(self.hp('deai-work', 'e'))
        _write(self.reg_file, '{ битий')
        before = _md5(self.reg_file)
        self.assertEqual(spaces.peek(self.hp('deai-work', 'e')),
                         {'path': self.hp('deai-work', 'e'), 'exists': True})
        self.assertEqual(_md5(self.reg_file), before)

    def test_peek_without_a_registry_or_with_the_layer_off_has_no_registered_key(self):
        os.makedirs(self.hp('deai-work', 'e'))
        want = {'path': self.hp('deai-work', 'e'), 'exists': True}
        self.assertEqual(spaces.peek(self.hp('deai-work', 'e')), want)       # реєстру нема
        self.assertFalse(os.path.exists(self.deai), 'peek створив <DEAI_HOME>')
        os.environ.pop('DEAI_HOME')                                           # шар вимкнено: лише DC_TASKS_FILE
        self.assertEqual(spaces.peek(self.hp('deai-work', 'e')), want)        # неявний простір без шляху — не збіг
        # Неявний простір має `path: ''`, а `realpath('')` — поточна тека процесу: без пропуску
        # порожнього шляху будь-яка тека, у якій стоїть сервер, вважалась би «зареєстрованою».
        old = os.getcwd()
        os.chdir(self.hp('deai-work', 'e'))
        self.addCleanup(os.chdir, old)
        self.assertEqual(spaces.peek(os.getcwd()), {'path': os.getcwd(), 'exists': True})

    def test_peek_over_a_hand_edited_registry_with_an_unusable_path_does_not_raise(self):
        """Реєстр із NUL чи самотнім сурогатом у шляху відхиляє `_validate` (`spaces-unreadable`), а
        `peek` усе одно відповідає (маршрут `space-peek` — завжди 200), без ключа `registered`."""
        os.makedirs(self.hp('deai-work', 'e'))
        want = {'path': self.hp('deai-work', 'e'), 'exists': True}
        for bad in (self.hp('a') + '\0x', self.hp('a', '\ud800')):
            with self.subTest(path=bad):
                _write(self.reg_file, json.dumps({'version': 1, 'current': 's0', 'spaces': [
                    {'id': 's0', 'path': bad, 'legacy': False, 'integrations': False}]}))
                self.assertEqual(spaces.peek(self.hp('deai-work', 'e')), want)

    def test_peek_swallows_whatever_the_comparison_throws(self):
        """Другий заслін: чого б не кинула перевірка «зареєстровано» (`ValueError` від NUL, `UnicodeEncodeError`,
        `OSError` файлової системи), `peek` лишається простою відповіддю."""
        os.makedirs(self.hp('deai-work', 'e'))
        self.registry_with(self.hp('deai-work', 'e'))
        want = {'path': self.hp('deai-work', 'e'), 'exists': True}
        for exc in (ValueError('embedded null byte'), UnicodeEncodeError('utf-8', '\ud800', 0, 1, 'surrogates'),
                    OSError('stat failed'), spaces.SpacesError('spaces-unreadable', self.reg_file, 'x')):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(spaces, '_is_registered', side_effect=exc):
                    self.assertEqual(spaces.peek(self.hp('deai-work', 'e')), want)

    def test_a_typed_path_with_a_lone_surrogate_is_not_a_path(self):
        """Самотній сурогат у ТИПОВОМУ шляху (JSON-тіло `space-new`) — як NUL: `path-not-absolute`, а не
        `UnicodeEncodeError` із `realpath` посеред відповіді."""
        bad = self.hp('deai-work', '\ud800x')
        self.assertEqual(spaces.peek(bad), {'path': bad, 'exists': False, 'error': 'path-not-absolute'})
        self.assertEqual(spaces.check_new_path(bad, {'version': 1, 'current': None, 'spaces': []}, []),
                         (None, 'path-not-absolute'))

    def test_relative_or_empty_path_is_refused_without_touching_the_disk(self):
        trap = os.path.join(self.tmp, 'cwd')
        _write(os.path.join(trap, 'rel', 'space.json'), {'name': 'Пастка', 'color': 'space-3'})
        _write(os.path.join(trap, 'rel', 'tasks.json'), {'tasks': {'a': {}}})
        old = os.getcwd()
        os.chdir(trap)
        try:
            for raw in ('rel', 'rel/', '', '   ', None, 'a\0b'):
                with self.subTest(path=raw):
                    got = spaces.peek(raw)
                    self.assertEqual(got, {'path': '' if raw is None else raw,
                                           'exists': False, 'error': 'path-not-absolute'})
        finally:
            os.chdir(old)


class TaskFileShape(Env):
    """Файл задач, що ІСНУЄ, але не читається як `{"tasks": {…}}`, — не «порожній простір»: у ньому
    можуть лежати id, яких ми не бачимо. Хто створює id (`create_space`, `task-new`), мусить
    відмовити, а не вважати його порожнім."""

    SHAPES = ('{ битий', '[]', '5', '{"tasks": []}', '{"tasks": null}', '{"tasks": {"x": 5}}',
              '{"tasks": {"x": null}}')

    def test_valid_tasks_cfg(self):
        for cfg, want in (({}, True), ({'tasks': {}}, True), ({'tasks': {'x': {}}, 'current': 'x'}, True),
                          ({'tasks': []}, False), ({'tasks': None}, False), ({'tasks': 'x'}, False),
                          ({'tasks': {'x': 5}}, False), ({'tasks': {'x': None}}, False),
                          ({'tasks': {'x': {}, 'y': []}}, False), ([], False), (5, False), (None, False)):
            with self.subTest(cfg=cfg):
                self.assertIs(spaces.valid_tasks_cfg(cfg), want)

    def test_unreadable_task_files_lists_existing_broken_files_only(self):
        self.two_spaces()
        p_file = os.path.join(self.p_path, 'tasks.json')
        self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [])
        for raw in self.SHAPES:
            with self.subTest(raw=raw):
                _write(p_file, raw)
                self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [p_file])
        os.remove(p_file)                                   # файла нема — це «недоступний», а не «битий»
        self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [])
        _write(p_file, {'tasks': {}})
        _write(self.legacy, '{')                            # старий файл — теж файл простору
        self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [self.legacy])

    def test_create_space_refuses_when_another_space_file_is_unreadable(self):
        self.two_spaces()
        p_file = os.path.join(self.p_path, 'tasks.json')
        q = self.hp('deai-work', 'q')
        for raw in self.SHAPES:
            with self.subTest(raw=raw):
                _write(p_file, raw)
                before = _md5(self.reg_file)
                with self.assertRaises(spaces.InputError) as cm:
                    spaces.create_space('Q', 'space-1', q)
                self.assertEqual((cm.exception.code, cm.exception.path), ('space-unavailable', p_file))
                self.assertEqual(str(cm.exception), f'space-unavailable: {p_file}')
                self.assertEqual(_md5(self.reg_file), before)
                self.assertFalse(os.path.exists(q), 'теку створено попри відмову')
        _write(p_file, {'tasks': {}})
        self.assertEqual(spaces.create_space('Q', 'space-1', q), 'q')       # полагодили — створюється

    def test_create_space_refuses_when_the_old_file_is_unreadable(self):
        self.two_spaces()
        _write(self.legacy, '{')
        with self.assertRaises(spaces.InputError) as cm:
            spaces.create_space('Q', 'space-1', self.hp('deai-work', 'q'))
        self.assertEqual((cm.exception.code, cm.exception.path), ('space-unavailable', self.legacy))

    def test_create_space_refuses_an_adopted_folder_whose_own_tasks_file_is_unreadable(self):
        """Тека, яку «усиновлюють», приносить власні id: не прочитавши їх, колізій не перевірити."""
        self.two_spaces()
        q = self.hp('deai-work', 'q')
        for raw in self.SHAPES:
            with self.subTest(raw=raw):
                _write(os.path.join(q, 'tasks.json'), raw)
                before = _md5(self.reg_file)
                with self.assertRaises(spaces.InputError) as cm:
                    spaces.create_space('Q', 'space-1', q)
                self.assertEqual((cm.exception.code, cm.exception.path),
                                 ('space-unavailable', os.path.join(q, 'tasks.json')))
                self.assertEqual(_md5(self.reg_file), before)
                self.assertFalse(os.path.exists(os.path.join(q, 'space.json')))

    def test_a_missing_tasks_file_does_not_block_creation(self):
        self.two_spaces()
        os.remove(os.path.join(self.p_path, 'tasks.json'))
        self.assertEqual(spaces.create_space('Q', 'space-1', self.hp('deai-work', 'q')), 'q')


class BrokenLegacyOnFirstStart(Env):
    """Старий `tasks.json` є, але не читається, і простору `legacy` у реєстрі ще нема (перший запуск).
    Це НЕ чиста машина: у файлі задачі людини. Раніше `load_registry` мовчки віддавав порожній реєстр,
    і все виглядало як «просторів нема» (привітання, 404 `no-task`). Тепер `legacy_unreadable` називає
    файл, `listing()` несе `legacy_error`, а створення id відмовляє."""

    #: Що МІГРАЦІЯ не бере: не JSON, не обʼєкт, понад ліміт розміру. (Обʼєкт із поганою формою
    #: `tasks` мігрується, а відмовляє вже `load_tasks()` — окремий тест нижче.)
    UNREADABLE = {
        'обрізаний JSON': '{"current": "a", "tasks": {"a": {"dir": "/x',
        'не JSON': '{ не json',
        'масив': '[]',
        'число': '5',
        'понад мегабайт': '{"pad": "' + 'a' * (1 << 20) + '"}',
    }

    def want_error(self):
        return {'path': self.legacy, 'code': 'space-unavailable'}

    def test_every_unreadable_shape_is_named_not_swallowed(self):
        for what, raw in self.UNREADABLE.items():
            with self.subTest(what=what):
                _write(self.legacy, raw)
                self.assertEqual(spaces.legacy_unreadable(), self.legacy)
                self.assertEqual(spaces.legacy_unreadable(spaces.read_registry()), self.legacy)
                got = spaces.listing()
                self.assertEqual(got, {'current': None, 'spaces': [], 'legacy_error': self.want_error()})
                # міграції нема, реєстр не створено, файл не чіпано
                self.assertFalse(os.path.exists(self.deai))
                self.assertEqual(_bytes(self.legacy), raw.encode())

    def test_an_unreadable_file_by_permissions_is_named_too(self):
        _write(self.legacy, {'tasks': {}})
        os.chmod(self.legacy, 0)
        try:
            if os.access(self.legacy, os.R_OK):
                self.skipTest('процес читає файл без прав (root) — перевірка беззмістовна')
            self.assertEqual(spaces.legacy_unreadable(), self.legacy)
            self.assertEqual(spaces.listing()['legacy_error'], self.want_error())
        finally:
            os.chmod(self.legacy, 0o600)

    def test_nothing_to_report_when_the_file_is_absent_or_fine(self):
        self.assertIsNone(spaces.legacy_unreadable())                    # файла нема — чиста машина
        self.assertNotIn('legacy_error', spaces.listing())
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        self.assertIsNone(spaces.legacy_unreadable())                    # читається — мігрує як завжди
        got = spaces.listing()
        self.assertNotIn('legacy_error', got)
        self.assertEqual([s['id'] for s in got['spaces']], ['liga'])

    def test_a_directory_in_place_of_the_file_is_not_a_broken_file(self):
        os.makedirs(self.legacy)                                         # не файл — як «нема»
        self.assertIsNone(spaces.legacy_unreadable())

    def test_an_object_with_a_bad_tasks_shape_is_migrated_not_reported(self):
        """Обʼєкт мігрується (як і було), далі його відмову дає `load_tasks()`; `legacy_error` — лише
        про файл, якого міграція не взяла."""
        for raw in ('{"tasks": []}', '{"tasks": null}', '{"tasks": {"x": 5}}'):
            with self.subTest(raw=raw):
                shutil.rmtree(self.deai, ignore_errors=True)
                _write(self.legacy, raw)
                got = spaces.listing()                                   # мігрує, як і до цієї правки
                self.assertNotIn('legacy_error', got)
                self.assertEqual(len(got['spaces']), 1)
                self.assertIsNone(spaces.legacy_unreadable())            # простір legacy уже в реєстрі

    def test_fixing_the_file_migrates_on_the_next_read_as_usual(self):
        _write(self.legacy, '{"tasks": {"a": {"dir": ')
        self.assertIn('legacy_error', spaces.listing())
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        got = spaces.listing()
        self.assertNotIn('legacy_error', got)
        self.assertEqual((got['current'], [s['id'] for s in got['spaces']]), ('liga', ['liga']))
        self.assertIsNone(spaces.legacy_unreadable())
        _write(self.legacy, '{')                                         # зламали ПІСЛЯ міграції
        self.assertIsNone(spaces.legacy_unreadable(), 'простір legacy уже в реєстрі: це справа load_tasks')
        self.assertNotIn('legacy_error', spaces.listing())

    def test_other_spaces_do_not_hide_it_and_the_registry_is_left_alone(self):
        personal = {'id': 'personal', 'path': self.hp('deai-work', 'personal'),
                    'legacy': False, 'integrations': False}
        self.write_registry([personal], 'personal')
        before = _md5(self.reg_file)
        _write(self.legacy, '{')
        got = spaces.listing()
        self.assertEqual([s['id'] for s in got['spaces']], ['personal'])
        self.assertEqual(got['legacy_error'], self.want_error())
        self.assertEqual(_md5(self.reg_file), before)

    def test_layer_off_never_reports_it(self):
        del os.environ['DEAI_HOME']
        _write(self.legacy, '{')
        self.assertIsNone(spaces.legacy_unreadable())
        self.assertIsNone(spaces.legacy_unreadable({'spaces': []}), 'явний реєстр без legacy при вимкненому шарі')
        self.assertEqual(spaces.unreadable_task_files({'spaces': []}), [])
        self.assertEqual(spaces.listing(), {'current': None, 'spaces': [], 'off': True})
        self.assertFalse(os.path.exists(self.hp('.deai')))

    def test_it_blocks_the_creation_of_ids_like_any_unreadable_tasks_file(self):
        """id в нечитабельному файлі невидимі: новий простір міг би зайняти те саме id (і зіткнутись
        після ремонту файла)."""
        _write(self.legacy, '{')
        self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [self.legacy])
        q = self.hp('deai-work', 'q')
        with self.assertRaises(spaces.InputError) as cm:
            spaces.create_space('Q', 'space-1', q)
        self.assertEqual((cm.exception.code, cm.exception.path), ('space-unavailable', self.legacy))
        self.assertFalse(os.path.exists(q), 'теку створено попри відмову')
        self.assertFalse(os.path.exists(self.reg_file), 'реєстр записано попри відмову')
        self.write_legacy({}, registry={})                               # полагодили — створюється
        self.assertEqual(spaces.create_space('Q', 'space-1', q), 'q')

    def test_a_registered_legacy_space_is_listed_once_not_twice(self):
        self.two_spaces()
        _write(self.legacy, '{')
        self.assertEqual(spaces.unreadable_task_files(spaces.read_registry()), [self.legacy])


class NoTaskMessage(Env):
    """Підказка CLI на `NoTask`: «створи простір» брехало, коли в ІНШИХ просторах задачі є."""

    EMPTY = 'задач немає — створи простір і задачу в канвасі'

    def test_nothing_anywhere_keeps_the_old_message(self):
        self.assertEqual(spaces.no_task_message(spaces.NoTask(None)), self.EMPTY)
        self.write_registry([{'id': 'e', 'path': self.hp('deai-work', 'e'), 'legacy': False,
                              'integrations': False}], 'e')
        _write(self.hp('deai-work', 'e', 'tasks.json'), {'tasks': {}})
        self.assertEqual(spaces.no_task_message(spaces.NoTask('e')), self.EMPTY)

    def test_other_spaces_with_tasks_are_named_in_the_message(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'tasks.json'), {'design_work_root': self.p_path, 'tasks': {}})
        msg = spaces.no_task_message(spaces.NoTask('p'))             # p порожній, а в liga є `a`
        self.assertIn('у поточному просторі задач нема; є в інших', msg)
        self.assertIn('--task <id>', msg)
        self.assertNotIn('створи простір', msg)

    def test_tasks_only_in_the_current_space_do_not_count_as_other(self):
        self.two_spaces()
        os.remove(self.legacy)                                       # liga без файла: задач нема
        self.assertEqual(spaces.no_task_message(spaces.NoTask('p')), self.EMPTY)   # `x` — у САМОМУ p

    def test_no_space_in_the_error_means_the_old_message_even_if_tasks_exist(self):
        self.two_spaces()
        self.assertEqual(spaces.no_task_message(spaces.NoTask(None)), self.EMPTY)

    def test_layer_off_and_a_broken_registry_never_raise(self):
        self.two_spaces()
        _write(self.reg_file, '{')
        self.assertEqual(spaces.no_task_message(spaces.NoTask('p')), self.EMPTY)
        del os.environ['DEAI_HOME']
        self.assertEqual(spaces.no_task_message(spaces.NoTask('p')), self.EMPTY)


class InputErrorContract(Env):
    """Відмови валідації несуть код АТРИБУТОМ: сервер відображає їх за `code`, а не розбирає текст."""

    def test_the_error_is_a_value_error_with_the_old_text(self):
        e = spaces.InputError('task-id-collision', 'a, b')
        self.assertIsInstance(e, ValueError)
        self.assertEqual((e.code, e.detail, e.path, str(e)), ('task-id-collision', 'a, b', None,
                                                              'task-id-collision: a, b'))
        self.assertEqual(str(spaces.InputError('name-required')), 'name-required')

    def test_every_refusal_of_create_and_update_carries_its_code(self):
        self.two_spaces()
        q = self.hp('deai-work', 'q')
        _write(os.path.join(q, 'tasks.json'), {'tasks': {'x': {}}})          # `x` вже є в просторі p
        cases = [
            (lambda: spaces.create_space('', 'space-1', q), 'name-required'),
            (lambda: spaces.create_space('Q', 'space-1', 'rel'), 'path-not-absolute'),
            (lambda: spaces.create_space('Q', 'space-1', self.home), 'path-too-broad'),
            (lambda: spaces.create_space('Q', 'space-1', self.p_path), 'path-registered'),
            (lambda: spaces.create_space('Q', 'space-1', q), 'task-id-collision'),
            (lambda: spaces.update_space('p', name='  '), 'name-required'),
        ]
        for call, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(spaces.InputError) as cm:
                    call()
                self.assertEqual(cm.exception.code, code)

    def test_unwritable_is_an_input_error_too(self):
        parent = self.hp('deai-work', 'afile')
        _write(parent, 'x')
        with self.assertRaises(spaces.InputError) as cm:
            spaces.create_space('X', 'space-1', os.path.join(parent, 'sub'))
        self.assertEqual(cm.exception.code, 'path-unwritable')


class Listing(Env):
    """`listing()` — те, що віддає `GET /api/spaces`: поточний і всі простори з лічильником
    задач та ознакою «файл задач є». Мігрує (бо питає `load_registry()`), як і `current_id()`."""

    def test_shape_counts_and_flags(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'space.json'), {'name': 'Клієнт', 'color': 'space-4'})
        self.assertEqual(spaces.listing(), {'current': 'liga', 'spaces': [
            {'id': 'liga', 'name': 'Liga', 'color': 'space-1', 'path': self.hp('Liga'),
             'legacy': True, 'integrations': True, 'tasks': 1, 'available': True},
            {'id': 'p', 'name': 'Клієнт', 'color': 'space-4', 'path': self.p_path,
             'legacy': False, 'integrations': False, 'tasks': 1, 'available': True}]})

    def test_current_follows_the_switch(self):
        self.two_spaces()
        spaces.switch_space('p')
        self.assertEqual(spaces.listing()['current'], 'p')

    def test_a_space_without_a_tasks_file_is_unavailable_with_zero_tasks(self):
        self.two_spaces()
        os.remove(os.path.join(self.p_path, 'tasks.json'))
        got = {s['id']: s for s in spaces.listing()['spaces']}
        self.assertEqual((got['p']['available'], got['p']['tasks']), (False, 0))
        self.assertEqual((got['liga']['available'], got['liga']['tasks']), (True, 1))
        # старий файл — це файл ЦЬОГО checkout-а: нема його — простір `legacy` недоступний
        os.remove(self.legacy)
        got = {s['id']: s for s in spaces.listing()['spaces']}
        self.assertEqual((got['liga']['available'], got['liga']['tasks']), (False, 0))

    def test_a_broken_tasks_file_counts_as_zero_but_stays_available(self):
        """Файл є — `available`; чи він читається, каже `/api/task` (503 `space-unavailable`)."""
        self.two_spaces()
        _write(os.path.join(self.p_path, 'tasks.json'), '{ битий')
        got = {s['id']: s for s in spaces.listing()['spaces']}
        self.assertEqual((got['p']['available'], got['p']['tasks']), (True, 0))

    def test_no_spaces_at_all_is_empty_and_writes_nothing(self):
        self.assertEqual(spaces.listing(), {'current': None, 'spaces': []})
        self.assertFalse(os.path.exists(self.deai))

    def test_the_old_file_is_migrated_on_the_way(self):
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        got = spaces.listing()
        self.assertEqual([s['id'] for s in got['spaces']], ['liga'])
        self.assertEqual(got['current'], 'liga')
        self.assertTrue(os.path.isfile(self.reg_file))

    def test_a_broken_registry_raises(self):
        _write(self.reg_file, '{')
        with self.assertRaises(spaces.SpacesError) as cm:
            spaces.listing()
        self.assertEqual(cm.exception.code, 'spaces-unreadable')

    def test_layer_off_is_an_honest_empty_listing(self):
        """Неявний простір — не простір для UI (`describe` ховає його): без `off` клієнт
        прочитав би порожній список як «просторів нема» і показав привітання."""
        del os.environ['DEAI_HOME']
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}})
        self.assertEqual(spaces.listing(), {'current': None, 'spaces': [], 'off': True})
        self.assertFalse(os.path.exists(self.hp('.deai')))


class Describe(Env):
    def test_flags_name_and_colour(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'space.json'), {'name': 'Клієнт', 'color': 'space-4'})
        liga = spaces.describe(spaces.find_task('a'))
        self.assertEqual(liga, {'id': 'liga', 'name': 'Liga', 'color': 'space-1', 'path': self.hp('Liga'),
                                'legacy': True, 'integrations': True})
        p = spaces.describe(spaces.find_task('x'))
        self.assertEqual(p, {'id': 'p', 'name': 'Клієнт', 'color': 'space-4', 'path': self.p_path,
                             'legacy': False, 'integrations': False})
        self.assertIsNone(spaces.describe(None))


class CreateSpace(Env):
    def test_creates_folder_files_and_registry_entry(self):
        p = self.hp('deai-work', 'personal')
        sid = spaces.create_space('Особисте', 'space-2', p)
        self.assertEqual(sid, 'space-1')                   # кирилична назва — слаг порожній
        self.assertEqual(_read(os.path.join(p, 'space.json')), {'name': 'Особисте', 'color': 'space-2'})
        self.assertEqual(_read(os.path.join(p, 'tasks.json')), {'design_work_root': p, 'tasks': {}})
        reg = spaces.load_registry()
        self.assertEqual(reg['spaces'], [{'id': 'space-1', 'path': p, 'legacy': False, 'integrations': False}])
        self.assertEqual(reg['current'], 'space-1')

    def test_new_files_are_world_readable_like_the_rest_of_the_work(self):
        p = self.hp('deai-work', 'modes')
        spaces.create_space('Modes', 'space-1', p)
        self.assertEqual(_mode(os.path.join(p, 'space.json')), 0o644)
        self.assertEqual(_mode(os.path.join(p, 'tasks.json')), 0o644)
        self.assertEqual(_mode(self.reg_file), 0o600)         # реєстр лишається приватним

    def test_existing_files_are_left_alone_including_their_mode(self):
        p = self.hp('deai-work', 'old')
        _write(os.path.join(p, 'space.json'), {'name': 'Старе', 'color': 'space-4'})
        _write(os.path.join(p, 'tasks.json'), {'tasks': {'z': {}}})
        os.chmod(os.path.join(p, 'space.json'), 0o600)
        os.chmod(os.path.join(p, 'tasks.json'), 0o640)
        spaces.create_space('Нове', 'space-2', p)
        self.assertEqual(_read(os.path.join(p, 'space.json')), {'name': 'Старе', 'color': 'space-4'})
        self.assertEqual(_read(os.path.join(p, 'tasks.json')), {'tasks': {'z': {}}})
        self.assertEqual(_mode(os.path.join(p, 'space.json')), 0o600)
        self.assertEqual(_mode(os.path.join(p, 'tasks.json')), 0o640)

    def test_task_id_collision_with_another_space_is_refused(self):
        self.write_legacy({'x': {'dir': self.hp('Liga', 'x')}}, registry={})
        spaces.load_registry()                              # міграція: простір liga з задачею x
        before = _md5(self.reg_file)
        q = self.hp('deai-work', 'q')
        _write(os.path.join(q, 'tasks.json'), {'tasks': {'x': {}}})
        with self.assertRaises(ValueError) as cm:
            spaces.create_space('Q', 'space-1', q)
        self.assertEqual(str(cm.exception), 'task-id-collision: x')
        self.assertEqual(_md5(self.reg_file), before)
        self.assertFalse(os.path.exists(os.path.join(q, 'space.json')))   # нічого не дописано в чужу теку

    def test_path_over_a_task_dir_of_another_space_is_an_overlap(self):
        """Задача простору `p` лежить ПОЗА його текою; новий простір над нею — відмова."""
        self.write_legacy({}, registry={})
        elsewhere = self.hp('elsewhere')
        p = self.hp('deai-work', 'p')
        _write(os.path.join(p, 'tasks.json'), {'tasks': {'t': {'dir': os.path.join(elsewhere, 't')}}})
        self.write_registry([{'id': 'p', 'path': p, 'legacy': False, 'integrations': False}], 'p')
        with self.assertRaises(ValueError) as cm:
            spaces.create_space('E', 'space-1', elsewhere)
        self.assertEqual(str(cm.exception), 'path-overlap')
        self.assertFalse(os.path.exists(elsewhere))

    def test_unknown_colour_becomes_first(self):
        p = self.hp('deai-work', 'c')
        spaces.create_space('C', 'magenta', p)
        self.assertEqual(_read(os.path.join(p, 'space.json'))['color'], 'space-1')

    def test_empty_name_is_refused(self):
        for name in ('', '   ', None):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as cm:
                    spaces.create_space(name, 'space-1', self.hp('deai-work', 'n'))
                self.assertEqual(str(cm.exception), 'name-required')
        self.assertFalse(os.path.exists(self.hp('deai-work')))

    def test_bad_path_is_refused_with_its_code(self):
        with self.assertRaises(ValueError) as cm:
            spaces.create_space('X', 'space-1', 'relative/dir')
        self.assertEqual(str(cm.exception), 'path-not-absolute')

    def test_existing_file_at_the_path_is_path_not_dir(self):
        f = self.hp('deai-work', 'afile')
        _write(f, 'x')
        with self.assertRaises(ValueError) as cm:
            spaces.create_space('X', 'space-1', f)
        self.assertEqual(str(cm.exception), 'path-not-dir')
        self.assertFalse(os.path.exists(self.reg_file))

    def test_filesystem_failure_is_path_unwritable_and_changes_no_registry(self):
        parent = self.hp('deai-work', 'afile')
        _write(parent, 'x')                                  # батьківська «тека» — файл
        with self.assertRaises(ValueError) as cm:
            spaces.create_space('X', 'space-1', os.path.join(parent, 'sub'))
        self.assertEqual(str(cm.exception), 'path-unwritable')
        self.assertIsInstance(cm.exception.__cause__, OSError)
        self.assertFalse(os.path.exists(self.reg_file))

    def test_validation_errors_keep_their_own_code(self):
        """`path-unwritable` обгортає лише файлову систему, а не наші `ValueError(code)`."""
        for path, code in (('rel', 'path-not-absolute'), (self.home, 'path-too-broad'),
                           (self.hp('.ssh', 'x'), 'path-system')):
            with self.subTest(code=code):
                with self.assertRaises(ValueError) as cm:
                    spaces.create_space('X', 'space-1', path)
                self.assertEqual(str(cm.exception), code)

    def test_slug_id_is_made_unique(self):
        a = spaces.create_space('Client', 'space-1', self.hp('deai-work', 'a'))
        b = spaces.create_space('Client', 'space-1', self.hp('deai-work', 'b'))
        self.assertEqual((a, b), ('client', 'client-2'))
        self.assertEqual(spaces.load_registry()['current'], 'client-2')

    def test_pending_migration_does_not_deadlock(self):
        """`create_space` кличе `load_registry()` (міграція бере `WRITE_LOCK`) ПОЗА локом."""
        self.write_legacy({'a': {'dir': self.hp('Liga', 'a')}}, registry={})
        box = {}
        t = threading.Thread(daemon=True, target=lambda: box.update(
            sid=spaces.create_space('Pers', 'space-2', self.hp('deai-work', 'pers'))))
        t.start()
        t.join(5)
        if t.is_alive():                                    # дедлок: розбудити, щоб не завис весь набір
            try:
                spaces.WRITE_LOCK.release()
            except RuntimeError:
                pass
            t.join(2)
            self.fail('create_space завис: load_registry() під WRITE_LOCK')
        reg = spaces.load_registry()
        self.assertEqual([s['id'] for s in reg['spaces']], ['liga', 'pers'])
        self.assertEqual(reg['current'], 'pers')
        self.assertEqual(box['sid'], 'pers')

    def test_concurrent_creation_of_the_same_path_has_exactly_one_winner(self):
        for rnd in range(20):
            with self.subTest(round=rnd):
                path = self.hp('deai-work', f'dup{rnd}')
                out = race(8, lambda i: spaces.create_space('D', 'space-1', path))
                wins = [r for kind, r in out if kind == 'ok']
                errs = [str(r) for kind, r in out if kind == 'err' and isinstance(r, ValueError)]
                other = [r for kind, r in out if kind == 'err' and not isinstance(r, ValueError)]
                self.assertEqual(other, [])
                self.assertEqual(len(wins), 1, out)
                self.assertEqual(len(errs), 7)
                self.assertTrue(set(errs) <= {'path-registered', 'path-overlap'}, errs)
        reg = _read(self.reg_file)
        self.assertEqual(len(reg['spaces']), 20)
        self.assertEqual(len({s['path'] for s in reg['spaces']}), 20)
        self.assertEqual(len({s['id'] for s in reg['spaces']}), 20)


class UpdateSwitch(Env):
    def test_update_writes_space_json_and_meta_reads_it_back(self):
        self.two_spaces()
        sp = spaces.find_task('x')
        new = spaces.update_space('p', name='  Клієнт  ', color='space-5')
        self.assertEqual(new, {'name': 'Клієнт', 'color': 'space-5'})
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')), new)
        self.assertEqual(spaces.space_meta(sp), ('Клієнт', 'space-5'))
        # частковий апдейт лишає решту
        spaces.update_space('p', name='Інше')
        self.assertEqual(spaces.space_meta(sp), ('Інше', 'space-5'))
        self.assertEqual(spaces.describe(sp)['name'], 'Інше')
        spaces.update_space('p', color='space-2')
        self.assertEqual(spaces.space_meta(sp), ('Інше', 'space-2'))

    @staticmethod
    def stall_after_first_call(name):
        """Патч `spaces.<name>`: ПЕРШИЙ виклик спершу відпрацьовує як є, а тоді спить 0,1 с —
        потік тримає застарілі дані саме тоді, коли інший встигає записати своє."""
        real, calls = getattr(spaces, name), []

        def wrapper(*a, **kw):
            res = real(*a, **kw)
            if not calls:
                calls.append(1)
                time.sleep(0.1)
            return res
        return mock.patch.object(spaces, name, wrapper)

    @staticmethod
    def run_two(first, second, gap=0.03):
        """`first` стартує раніше за `second` на `gap` с; повертає винятки обох (None — без)."""
        errs = [None, None]

        def run(i, fn):
            try:
                fn()
            except BaseException as e:  # noqa: BLE001
                errs[i] = e
        t1 = threading.Thread(target=run, args=(0, first))
        t2 = threading.Thread(target=run, args=(1, second))
        t1.start()
        time.sleep(gap)
        t2.start()
        t1.join(30)
        t2.join(30)
        return errs

    def test_concurrent_updates_of_one_space_do_not_lose_each_other(self):
        """Читання-зміна-запис `space.json` ПІД локом: назва від одного, колір від іншого."""
        self.two_spaces()
        with self.stall_after_first_call('space_meta'):
            errs = self.run_two(lambda: spaces.update_space('p', name='A'),
                                lambda: spaces.update_space('p', color='space-5'))
        self.assertEqual(errs, [None, None])
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')), {'name': 'A', 'color': 'space-5'})

    def test_switch_does_not_clobber_a_concurrent_create(self):
        """`switch_space` читає реєстр і пише його ПІД одним локом: простір, створений
        паралельно, не губиться застарілою копією."""
        self.two_spaces()
        made = []
        with self.stall_after_first_call('_space'):
            errs = self.run_two(lambda: spaces.switch_space('p'),
                                lambda: made.append(spaces.create_space('New', 'space-2', self.hp('deai-work', 'new'))))
        self.assertEqual(errs, [None, None])
        reg = _read(self.reg_file)
        self.assertEqual([s['id'] for s in reg['spaces']], ['liga', 'p', 'new'])
        self.assertEqual(reg['current'], 'new')              # створення йшло ПІСЛЯ перемикання

    def test_update_keeps_the_mode_of_an_existing_space_json(self):
        self.two_spaces()
        sj = os.path.join(self.p_path, 'space.json')
        _write(sj, {'name': 'Було', 'color': 'space-3'})
        os.chmod(sj, 0o640)
        spaces.update_space('p', name='Стало')
        self.assertEqual(_mode(sj), 0o640)

    def test_update_keeps_unknown_keys_of_space_json(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'space.json'),
               {'name': 'Було', 'color': 'space-3', 'note': 'мій ключ', 'extra': {'a': [1, 2]}})
        spaces.update_space('p', name='Стало')
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')),
                         {'name': 'Стало', 'color': 'space-3', 'note': 'мій ключ', 'extra': {'a': [1, 2]}})

    def test_update_over_a_broken_space_json_starts_from_scratch(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'space.json'), '{ битий')
        spaces.update_space('p', name='Нове')
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')), {'name': 'Нове', 'color': 'space-1'})

    def test_update_with_empty_name_is_refused_and_changes_nothing(self):
        self.two_spaces()
        _write(os.path.join(self.p_path, 'space.json'), {'name': 'Було', 'color': 'space-3'})
        for name in ('', '   ', '\n'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as cm:
                    spaces.update_space('p', name=name, color='space-6')
                self.assertEqual(str(cm.exception), 'name-required')
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')), {'name': 'Було', 'color': 'space-3'})

    def test_update_legacy_space_whose_folder_does_not_exist_yet(self):
        self.two_spaces()
        self.assertFalse(os.path.isdir(self.hp('Liga')))
        spaces.update_space('liga', name='ЛІГА')
        self.assertEqual(spaces.space_meta({'id': 'liga', 'path': self.hp('Liga')})[0], 'ЛІГА')
        self.assertEqual(_mode(self.hp('Liga', 'space.json')), 0o644)

    def test_update_failure_on_the_filesystem_is_path_unwritable(self):
        self.two_spaces()
        os.remove(os.path.join(self.p_path, 'tasks.json'))
        shutil.rmtree(self.p_path)
        _write(self.p_path, 'я файл, а не тека простору')
        with self.assertRaises(ValueError) as cm:
            spaces.update_space('p', name='X')
        self.assertEqual(str(cm.exception), 'path-unwritable')

    def test_meta_falls_back_to_folder_name_and_first_colour(self):
        sp = {'id': 'z', 'path': self.hp('deai-work', 'folder-name')}
        self.assertEqual(spaces.space_meta(sp), ('folder-name', 'space-1'))
        _write(os.path.join(sp['path'], 'space.json'), '{ битий')
        self.assertEqual(spaces.space_meta(sp), ('folder-name', 'space-1'))

    def test_meta_validates_every_field(self):
        sp = {'id': 'z', 'path': self.hp('deai-work', 'folder-name')}
        sj = os.path.join(sp['path'], 'space.json')
        cases = [
            ({'name': 'Ok', 'color': 'magenta'}, ('Ok', 'space-1')),                   # невідомий колір
            ({'name': 'Ok', 'color': 3}, ('Ok', 'space-1')),
            ({'name': 'Ok', 'color': 'space-6'}, ('Ok', 'space-6')),
            ({'name': 5, 'color': 'space-2'}, ('folder-name', 'space-2')),             # назва не рядок
            ({'name': '   ', 'color': 'space-2'}, ('folder-name', 'space-2')),
            ({'name': 'x' * 100}, ('x' * 60, 'space-1')),                              # обрізано до 60
            ({'name': '  ' + 'y' * 100}, ('y' * 60, 'space-1')),
            ([], ('folder-name', 'space-1')),                                          # не обʼєкт
            (7, ('folder-name', 'space-1')),
            ('рядок', ('folder-name', 'space-1')),
        ]
        for content, want in cases:
            with self.subTest(content=content):
                _write(sj, content)
                self.assertEqual(spaces.space_meta(sp), want)

    def test_meta_with_empty_or_missing_path_does_not_touch_the_filesystem(self):
        """Неявний простір (`path == ''`): не читати `space.json` відносно cwd."""
        trap = os.path.join(self.tmp, 'cwd')
        _write(os.path.join(trap, 'space.json'), {'name': 'Пастка', 'color': 'space-3'})
        old = os.getcwd()
        os.chdir(trap)
        try:
            self.assertEqual(spaces.space_meta({'id': 'legacy', 'path': ''}), ('legacy', 'space-1'))
            self.assertEqual(spaces.space_meta({'id': 'z'}), ('z', 'space-1'))
        finally:
            os.chdir(old)

    def test_switch_changes_current(self):
        self.two_spaces()
        spaces.switch_space('p')
        self.assertEqual(_read(self.reg_file)['current'], 'p')
        self.assertEqual(spaces.active_space()['id'], 'p')

    def test_unknown_id_raises_key_error(self):
        self.two_spaces()
        with self.assertRaises(KeyError):
            spaces.switch_space('ghost')
        with self.assertRaises(KeyError):
            spaces.update_space('ghost', name='X')


if __name__ == '__main__':
    unittest.main()

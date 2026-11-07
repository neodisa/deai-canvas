"""Міграція ЛІГИ, четвертий крок — напрямки остаточно явні (етап 4d-4a, 0.20.0).

Тут: знімок поведінки 0.19.0 (`Before4d4aShape`, Task 1); крок `liga-4d4a` — розрахунок, запис, відкат LIFO на чотири кроки, старт
і CLI (Task 2–3); паритет після міграції (`AfterMigrationParity4d4a`, Task 7). Спека
`docs/superpowers/specs/2026-11-07-liga-tracks-final-design.md`.
"""
import json
import os
import re
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4a.json')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402
from make_before_4d4a import POSTS, STANDS, UNKNOWN_ONLY_IN_NOTES, VALUES  # noqa: E402  (сценарії — ті самі, що в генераторі)
from test_liga_migrate import _WriteStand  # noqa: E402  (стенд запису 4d-3a: тимчасові HOME/DEAI_HOME, CLI, пошук секретів)

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard`."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


SECTIONS_LIGA = ['api', 'ds', 'labels', 'registry', 'repos', 'roots', 'roots_cli', 'task_new', 'view']
SECTIONS_PLAIN = ['api', 'ds', 'labels', 'repos', 'roots', 'task_new', 'view']


class Before4d4aShape(unittest.TestCase):
    """Знімок 0.19.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_and_meta(self):
        self.assertEqual(sorted(self.snap), ['meta', 'non_loopback_attempts', 'stands'])
        self.assertEqual(sorted(self.snap['stands']), sorted(STANDS))
        self.assertEqual(self.snap['meta'], {'version': '0.19.0', 'source_commit': '80dc34a',
                                             'generator': 'tests/make_before_4d4a.py', 'volatile_stripped': []})
        self.assertEqual(self.snap['non_loopback_attempts'], 0)

    def test_machine_independent(self):
        """⛔ Ні справжніх шляхів, ні імені користувача, ні тимчасових тек, ні штампів часу: лише `~/…`/`<tmp>`."""
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/' + 'Users/', '/home/', '/var/' + 'folders', '/' + 'private/', '/tmp/', 'before-4d4a-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))

    def test_sections_and_scenarios_are_exact(self):
        want_values = sorted(repr(v) for v in VALUES)
        for name, st in self.snap['stands'].items():
            self.assertEqual(sorted(st), SECTIONS_PLAIN if name == 'plain' else SECTIONS_LIGA, name)
            self.assertEqual(sorted(st['task_new']), sorted(k for k, _ in POSTS), name)
            self.assertEqual(sorted(st['roots']), sorted(want_values + (["'app'", "'web'"] if name == 'plain' else [])), name)
            tasks = ['a-%d' % i for i in range(1, 9)] + (['a-9'] if name == 'notes' else [])
            tasks = [t for t in tasks if not (name != 'notes' and t in UNKNOWN_ONLY_IN_NOTES)]
            self.assertEqual(sorted(st['labels']), tasks, name)

    def test_the_stands_witness_the_adapter(self):
        """Знімок ловить саме те, що зникне: адаптерні мітки старого запису, `profile` у відповіді API, корені адаптера."""
        s = self.snap['stands']
        self.assertEqual(s['parity']['labels']['a-2'], ['United'], 'запис лише з `profile` дає мітку адаптера')
        self.assertEqual(s['parity']['roots']["'united'"], '~/work/shared')
        for name in ('parity', 'notes', 'explicit'):
            for tid, row in s[name]['api']['task'].items():
                self.assertIn('profile', row['keys'], (name, tid))
        self.assertEqual(s['notes']['roots']["'seo'"], '~/.hidden/seo')
        self.assertEqual(s['notes']['roots']["'liga360'"], 'rel/l360')
        self.assertEqual(s['notes']['roots']["'united'"], '~/work/united', 'власний корінь united ≠ спільного')
        self.assertEqual(s['plain']['labels']['a-2'], ['united'])
        self.assertEqual(s['parity']['task_new']['track_upper']['status'], 200, 'ЛІГА 0.19 приймає будь-який рядок напрямку')
        self.assertEqual(s['plain']['task_new']['track_zzz']['code'], 'unknown-track')

    def test_registry_of_a_profile_only_record_per_liga_stand(self):
        """Запис лише з `profile: seo` — корінь у реєстрі різний на кожному стенді (у 0.20 дописаний `track` дає те саме)."""
        s = self.snap['stands']
        self.assertEqual({n: s[n]['registry']['profile_only_seo'] for n in ('parity', 'notes', 'explicit')},
                         {'parity': '~/work/shared', 'notes': '~/.hidden/seo', 'explicit': '~/work/seo'})

    def test_non_id_keys_and_unknown_values_witnesses_on_the_notes_stand(self):
        """`Bad_Key` адаптер відкидає (нема в переліку id); задача `a-9` зі значенням `Weird` має мітку й ДС «як є»."""
        n = self.snap['stands']['notes']
        self.assertEqual(n['view']['ids'], ['united', 'liga360', 'seo', 'custom-x'])
        self.assertNotIn('Bad_Key', json.dumps(n['view']) + json.dumps(n['repos']) + json.dumps(n['roots']))
        self.assertEqual((n['labels']['a-9'], n['ds']['a-9']), (['Weird'], 'Weird'))
        self.assertNotIn('a-9', self.snap['stands']['parity']['labels'])


# ---------------------------------------------------------------------------------------------------------------- Task 2: крок liga-4d4a

D = 'liga-4d4a'
ORIG_SPACE = b'{"name": "Liga",\n  "x": {"k": [1,  2]}}\n'


class _StepD(_WriteStand):
    """Стенд РЕАЛЬНИХ чотирьох кроків (`ALL_STEPS = (A, B, C, D)`); `_Stand.setUp` ставить `STEPS = ALL_STEPS[:1]` — тут перекриваємо.
    Конфіг `_Stand.config()`: `united` без власного кореня (паритет повний), `custom-x` зі своїм; задачі `a-1` (`track: seo`) і
    `a-2` (лише `profile: united`). `HOME`/`DEAI_HOME` патчить `_Stand.setUp`; значення вигадані."""

    def setUp(self):
        super().setUp()
        p = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS)
        p.start()
        self.addCleanup(p.stop)

    def plan_d(self, **kw):
        return self.lm.plan(step=D, **kw)

    def marks(self):
        return self.read_json(self.space_path()).get('migrations') or {}

    def tasks(self):
        return self.read_json(self.tasks_path)['tasks']

    def hidden_root(self):
        return os.path.join(self.home, '.hidden', 'seo')         # прихована тека в домівці: `tracks.normalize` кореня не прийме

    def start(self):
        return self.quiet(self.lm.startup)


class StepDConstants(_StepD):
    def test_steps_list_and_shape(self):
        lm = self.lm
        self.assertEqual([s.mark for s in lm.ALL_STEPS], ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D])
        self.assertIs(lm.ALL_STEPS[3], lm.STEP_D)
        self.assertEqual(lm.STEPS, lm.ALL_STEPS)
        d = lm.STEP_D
        self.assertEqual((d.mark, d.roles, d.tracks, d.suffix, d.ungated), (D, (), True, '-liga-4d4a', True))
        self.assertEqual(d.entries(self.cfg, set()), {}, 'ролей крок не має')

    def test_stamp_names_tell_the_steps_apart(self):
        lm = self.lm
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d4a'), lm.STEP_D)
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d4a-2'), lm.STEP_D)
        self.assertIsNone(lm.step_of_stamp('20261107-120000-liga-4d4a-pre-restore'))
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d3c'), lm.STEP_C)

    def test_new_abort_codes(self):
        self.assertIn('abort-tracks', self.lm.ABORT_CODES)
        self.assertIn('abort-records', self.lm.ABORT_CODES)
        for code in ('abort-tracks', 'abort-records'):
            self.assertTrue(self.lm._REASONS[code])
            self.assertNotIn(code, self.lm.BENIGN)


class AdapterApplies(unittest.TestCase):
    """`tracks.adapter_applies(raw, path)` — ОДИН критерій «зараз діє адаптер» (кличе лише міграція; рантайм — ні, див. `NoTracksAdapter`)."""

    def test_matrix(self):
        import tracks
        good = [{'id': 'united'}]
        for raw, want in ((None, True), ([], True), ({}, True), ('x', True), (5, True), ([{'id': 'Bad'}], True),
                          ([5, None], True), (good, False), ([{'id': 'united'}, {'id': 'Bad'}], False)):
            self.assertEqual(tracks.adapter_applies(raw, '/x'), want, repr(raw))


class StepDPlanTest(_StepD):
    """`plan(step='liga-4d4a')` — чистий розрахунок: напрямки БЕЗ воріт паритету, нотатки, записи задач."""

    def test_ready_without_the_parity_gate(self):
        """Конфіг, на якому 4d-3a відмовляється (`united` зі своїм коренем), для 4d-4a — звичайний випадок із нотаткою."""
        work = os.path.join(self.home, 'work')
        self.config(design_work_roots={'united': os.path.join(work, 'united'), 'custom-x': os.path.join(work, 'custom')})
        a = self.lm.plan(step='liga-4d3a')
        self.assertEqual(a['tracks_reason'], 'tracks-unknown-values', 'свідок: ворота 4d-3a тут закриті')
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', True, None))
        sj = p['space_json']
        self.assertEqual([(t['id'], t['label'], t['root'], t['repo'], t['ds']) for t in sj['tracks']], [
            ('united', 'United', os.path.join(work, 'united'), self.REPO_U, 'united'),
            ('liga360', 'LIGA360', os.path.join(work, 'shared'), '', 'liga360'),
            ('seo', 'SEO', os.path.join(work, 'shared'), self.REPO_S, 'seo'),
            ('custom-x', 'custom-x', os.path.join(work, 'custom'), '', 'custom-x')])
        self.assertEqual(sj['default_track'], 'united')
        self.assertEqual(p['notes'], ['default-root-differs'])
        self.assertEqual(sj['migrations'], {D: {'roles': [], 'tracks': True, 'records': 1, 'notes': ['default-root-differs']}})
        self.assertEqual((p['roles'], p['secrets']), ({}, {}), 'ролей і секретів крок не має')

    def test_full_parity_has_no_notes(self):
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['notes'], p['records']), ('ready', True, [], ['a-2']))

    def test_every_kind_of_note_in_a_fixed_order(self):
        work = os.path.join(self.home, 'work')
        tasks = dict(self.cfg['tasks'], w={'dir': os.path.join(work, 'w'), 'profile': 'Weird'})
        self.config(tasks=tasks,
                    design_work_roots={'united': os.path.join(work, 'united'), 'seo': self.hidden_root(), 'Bad_Key': os.path.join(work, 'b')},
                    profile_repos={'united': self.REPO_U, 'Other_Key': self.REPO_S})
        p = self.plan_d()
        self.assertEqual(p['notes'], ['root-dropped:seo', 'unknown-values', 'default-root-differs', 'non-id-keys'])
        seo = next(t for t in p['space_json']['tracks'] if t['id'] == 'seo')
        self.assertIsNotNone(seo['root'], 'у `space.json` лежить розгорнутий корінь адаптера, відкидає його читач (`normalize`)')

    def test_a_relative_root_is_rebased_not_dropped(self):
        """Відносний корінь адаптера (вів у теку відносно процесу) став відносним до теки простору — окрема нотатка."""
        sub = os.path.join(self.home, 'sp')
        os.makedirs(sub)
        self.registry(path=sub)
        self.config(design_work_roots={'liga360': 'rel/l360'})
        p = self.plan_d()
        self.assertIn('root-rebased:liga360', p['notes'])
        self.assertNotIn('root-dropped:liga360', p['notes'])
        got = next(t for t in p['space_json']['tracks'] if t['id'] == 'liga360')['root']
        self.assertEqual(got, 'rel/l360', 'у `space.json` лишається значення адаптера; відносність розвʼяже `normalize`')

    def test_tasks_without_a_value_give_no_unknown_note(self):
        tasks = dict(self.cfg['tasks'], n1={'dir': '/x'}, n2={'dir': '/x', 'track': 5}, n3={'dir': '/x', 'profile': ''})
        self.config(tasks=tasks)
        self.assertNotIn('unknown-values', self.plan_d()['notes'])

    def test_notes_carry_no_paths_or_values(self):
        self.config(design_work_roots={'seo': self.hidden_root()})
        for n in self.plan_d()['notes']:
            self.assertRegex(n, r'^[a-z-]+(:[a-z0-9-]+)?$', n)

    def test_own_valid_tracks_are_kept(self):
        own = [{'id': 'web', 'label': 'Web'}]
        self.space_json({'tracks': own, 'default_track': 'web'})
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-present'))
        self.assertEqual(p['space_json']['tracks'], own)
        self.assertEqual(p['space_json']['default_track'], 'web')
        self.assertEqual(p['records'], ['a-2'], 'записи задач крок виправляє й тоді')

    def test_empty_or_unusable_tracks_are_replaced_exactly_where_the_runtime_applies_the_adapter(self):
        for raw in ([], {}, [{'id': 'Bad'}], [5, None], None):
            self.space_json({'tracks': raw})
            p = self.plan_d()
            self.assertEqual((p['status'], p['tracks']), ('ready', True), repr(raw))

    def test_records_matrix(self):
        recs = {'fix1': {'profile': 'seo'}, 'fix2': {'track': '', 'profile': 'seo'}, 'fix3': {'track': 5, 'profile': 'seo'},
                'fix4': {'track': None, 'profile': 'zzz'}, 'keep1': {'track': 'a', 'profile': 'b'}, 'keep2': {'profile': ''},
                'keep3': {'profile': 5}, 'keep4': {}, 'keep5': 'not a dict', 'keep6': {'track': 'x'}}
        self.assertEqual(self.lm._records_to_fix({'tasks': recs}), ['fix1', 'fix2', 'fix3', 'fix4'])
        for bad in (None, [], {}, {'tasks': None}, {'tasks': []}):
            self.assertEqual(self.lm._records_to_fix(bad), [])

    def test_skip_nothing_when_there_is_nothing_to_write(self):
        self.space_json({'tracks': [{'id': 'web'}]})
        self.config(tasks={'a-1': {'dir': '/x', 'track': 'seo'}, 'a-2': {'dir': '/y', 'profile': ''}})
        before = self.snapshot_tree()
        p = self.plan_d()
        self.assertEqual((p['status'], p['space_json']), ('skip-nothing', None))
        self.assertEqual(self.lm.run(step=D), 'skip-nothing')
        self.assertEqual(self.snapshot_tree(), before, 'позначки й бекапу нема: наступний старт перевірить знову')

    def test_abort_tracks_when_the_calculated_list_differs_from_the_adapter(self):
        """Понад `MAX_TRACKS` (20) id: `normalize` відкинув би зайві, тож явний список ≠ адаптеру — нічого не пишемо."""
        keys = {'t%02d' % i: self.REPO_U for i in range(21)}
        self.config(profile_repos=keys)
        p = self.plan_d()
        self.assertEqual((p['status'], p['space_json']), ('abort-tracks', None))
        self.assertTrue(p['reason'])
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(step=D), 'abort-tracks')
        self.assertEqual({k: v for k, v in self.snapshot_tree().items() if os.sep + 'migrations' + os.sep not in k},
                         {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k}, 'жодного запису, крім журналу')

    def test_skip_codes(self):
        cases = {'skip-integrations-off': lambda: self._write(os.path.join(self.deai, 'spaces.json'), json.dumps(
                     {'version': 1, 'current': 'legacy', 'spaces': [{'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': False}]})),
                 'skip-done': lambda: self.space_json({'migrations': {D: {'at': 'x', 'roles': []}}}),
                 'skip-held': lambda: self.space_json({'migrations': {D: {'held': True}}}),
                 'skip-path-in-git': lambda: os.makedirs(os.path.join(self.space_dir, '.git')),
                 'skip-space-json-unreadable': lambda: self.space_json('{broken'),
                 'skip-tasks-unreadable': lambda: self._write(self.tasks_path, '{broken')}
        for code, arrange in cases.items():
            self.setUp_clean()
            arrange()
            self.assertEqual(self.plan_d()['status'], code, code)

    def setUp_clean(self):
        for p in (self.space_path(), os.path.join(self.space_dir, '.git')):
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        self.registry()
        self.config()

    def test_an_earlier_held_step_holds_d_with_its_own_text(self):
        self.space_json({'migrations': {'liga-4d3c': {'held': True}}})
        p = self.plan_d()
        self.assertEqual(p['status'], 'skip-held')
        self.assertIn('liga-4d3c', p['reason'])

    def test_plan_is_pure_and_the_report_has_the_counts(self):
        before = self.snapshot_tree()
        p = self.plan_d()
        self.assertEqual(self.snapshot_tree(), before)
        text = self.lm.report(p, D)
        self.assertIn('liga-4d4a: ready', text)
        self.assertIn('tracks: migrate', text)
        self.assertIn('records: 1; notes: -', text)
        self.assert_no_secrets(text)


class StepDRunTest(_StepD):
    """`run(step='liga-4d4a')`: бекап → записи задач → ОДИН запис `space.json` з позначкою."""

    def seed(self):
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)

    def test_run_writes_tracks_records_mark_and_backup(self):
        self.seed()
        old_tasks = self.read(self.tasks_path)
        old_a1 = self.tasks()['a-1']
        self.assertEqual(self.lm.run(step=D), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual((sj['name'], sj['x']), ('Liga', {'k': [1, 2]}), 'чужі ключі space.json збережено')
        self.assertEqual([t['id'] for t in sj['tracks']], ['united', 'liga360', 'seo', 'custom-x'])
        mark = sj['migrations'][D]
        self.assertEqual(sorted(mark), ['at', 'backup', 'notes', 'records', 'roles', 'tracks'])
        self.assertEqual((mark['roles'], mark['tracks'], mark['records'], mark['notes']), ([], True, 1, []))
        t = self.tasks()
        self.assertEqual((t['a-2']['track'], t['a-2']['profile']), ('united', 'united'), '`profile` лишається (спільний реєстр)')
        self.assertEqual(t['a-1'], old_a1, 'запис, що вже має `track`, не чіпаємо')
        self.assertEqual(self.read(self.tasks_path + '.bak'), old_tasks, '`.bak` — як у `serve.save_tasks`')
        b = os.path.join(self.deai, 'backups', mark['backup'])
        self.assertEqual(self.read(b, 'tasks.json'), old_tasks, 'бекап кроку містить tasks.json ДО запису')
        self.assertEqual(self.read_json(b, 'manifest.json')['migration'], D)
        self.assertEqual(self.backups(), [mark['backup']])
        self.assert_no_secrets_in_logs()

    def test_the_second_start_is_skip_done_and_writes_nothing(self):
        self.assertEqual(self.lm.run(step=D), 'done')
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(step=D), 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)

    def test_tasks_file_is_reread_under_the_lock_before_writing(self):
        """Задача, додана між розрахунком і записом, теж виправляється; чужі правки не губляться."""
        real = self.lm._backup

        def backup_then_add_a_task(*a, **kw):
            name = real(*a, **kw)
            cfg = self.read_json(self.tasks_path)
            cfg['tasks']['late'] = {'dir': '/x', 'profile': 'seo'}
            cfg['jira_base'] = 'https://jira.example.com/changed'
            self._write(self.tasks_path, cfg)
            return name
        with self.mock.patch.object(self.lm, '_backup', backup_then_add_a_task):
            self.assertEqual(self.lm.run(step=D), 'done')
        cfg = self.read_json(self.tasks_path)
        self.assertEqual((cfg['tasks']['late']['track'], cfg['tasks']['a-2']['track']), ('seo', 'united'))
        self.assertEqual(cfg['jira_base'], 'https://jira.example.com/changed')
        self.assertEqual(self.marks()[D]['records'], 2, 'у позначці — скільки записано насправді')

    def test_a_failed_space_write_leaves_harmless_records_and_the_next_run_starts_over(self):
        with self.mock.patch.object(self.lm, '_write_space', side_effect=OSError):
            self.assertEqual(self.lm.run(step=D), 'abort-write')
        self.assertNotIn(D, self.marks() if os.path.exists(self.space_path()) else {})
        self.assertEqual(self.tasks()['a-2']['track'], 'united', 'записи вже є — нешкідливо (`track` = `profile`)')
        self.assertEqual(self.lm.run(step=D), 'done')
        mark = self.marks()[D]
        self.assertEqual((mark['tracks'], mark['records']), (True, 0), 'другий прогін: напрямки пишуться, записів уже нема')

    def test_a_failed_tasks_write_is_abort_records_and_space_json_stays(self):
        self.seed()
        before_space = self.read(self.space_path())
        with self.mock.patch.object(self.lm.shutil, 'copy2', side_effect=OSError):
            self.assertEqual(self.lm.run(step=D), 'abort-records')
        self.assertEqual(self.read(self.space_path()), before_space)
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-records')
        self.assertEqual(self.lm.run(step=D), 'done')

    def test_owner_tracks_written_after_the_plan_are_not_overwritten(self):
        """Між розрахунком і записом власник додав свої напрямки: ворота «адаптер діє» перевіряються ще раз під замком."""
        real = self.lm._backup

        def backup_then_own_tracks(*a, **kw):
            name = real(*a, **kw)
            self._write(self.space_path(), json.dumps({'tracks': [{'id': 'web', 'label': 'Web'}], 'default_track': 'web'}))
            return name
        with self.mock.patch.object(self.lm, '_backup', backup_then_own_tracks):
            self.assertEqual(self.lm.run(step=D), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual([t['id'] for t in sj['tracks']], ['web'])
        self.assertEqual(sj['migrations'][D]['tracks'], False, 'позначка каже, що напрямків крок НЕ писав')

    def test_restore_puts_back_space_json_only_and_keeps_the_tasks_file(self):
        """⛔ Відкат повертає `space.json` (як і для 4d-3a…c) і НЕ чіпає `tasks.json`: той файл — жива база, у ній уже нові задачі."""
        self.seed()
        before_space = self.read(self.space_path())
        self.assertEqual(self.lm.run(step=D), 'done')
        stamp = self.backups()[0]
        cfg = self.read_json(self.tasks_path)
        cfg['tasks']['fresh'] = {'dir': '/x', 'title': 'created after the migration'}
        self._write(self.tasks_path, cfg)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(self.read(self.space_path()), before_space)
        t = self.tasks()
        self.assertIn('fresh', t)
        self.assertEqual(t['a-2']['track'], 'united', '`track = profile` безпечний для 0.19: мітка й ДС ті самі')

    def test_no_secret_anywhere(self):
        code, out, err = self.cli('run')
        self.assertEqual(code, 0)
        self.assert_no_secrets(out, err)
        self.assert_no_secrets_in_logs()


# ---------------------------------------------------------------------------------------------------------------- Task 3: вивід, status, CLI, LIFO

class LifoFourSteps(_StepD):
    """Відкат LIFO на чотири кроки; відмова називає ОСТАННІЙ застосований бекап (тепер це бекап кроку d)."""

    def setUp(self):
        super().setUp()
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        for s in self.lm.ALL_STEPS[:3]:
            self.assertEqual(self.lm.run(step=s), 'done', s.mark)
        self.after_abc = (self.read(self.space_path()), os.path.exists(self.secrets_path()) and self.read(self.secrets_path()))
        self.assertEqual(self.lm.run(step=D), 'done')
        self.a, self.b, self.c, self.d = [next(x for x in self.backups() if x.endswith(s)) for s in ('4d3a', '4d3b', '4d3c', '4d4a')]

    def test_restore_of_an_earlier_step_is_refused_naming_d_and_writes_nothing(self):
        for stamp in (self.a, self.b, self.c):
            before = self.snapshot_tree()
            st, info = self.lm._restore(stamp)
            self.assertEqual((st, info['rollback_first']), ('refuse-later-applied', self.d), stamp)
            self.assertEqual(self.lm.restore(stamp, hold=True), 'refuse-later-applied')
            self.assertEqual(self.snapshot_tree(), before)

    def test_cli_names_d_and_exits_nonzero(self):
        code, out, _err = self.cli('restore', self.c)
        self.assertEqual(code, 1)
        self.assertIn(self.d, out)
        self.assertNotIn(self.b, out)

    def test_in_order_d_then_c_then_b_then_a(self):
        self.assertEqual(self.lm.restore(self.d), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_abc[0], 'space.json — побайтно стан після c')
        self.assertEqual(self.lm.restore(self.b), 'refuse-later-applied')
        self.assertEqual(self.lm.restore(self.c), 'restored')
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')

    def test_hold_of_d_holds_only_d(self):
        self.assertEqual(self.lm.restore(self.d, hold=True), 'restored')
        marks = self.marks()
        self.assertEqual(marks[D], {'held': True})
        self.assertEqual({k: ('held' in v) for k, v in marks.items() if k != D}, {'liga-4d3a': False, 'liga-4d3b': False, 'liga-4d3c': False})
        self.assertEqual(self.plan_d()['status'], 'skip-held')
        self.assertEqual(self.lm.run(step=D), 'skip-held')

    def test_a_held_d_does_not_hold_the_earlier_steps(self):
        self.assertEqual(self.lm.restore(self.d, hold=True), 'restored')
        self.assertEqual(self.lm.restore(self.c), 'restored', 'ранні кроки відкочуються далі')

    def test_a_held_c_holds_d_on_the_next_start(self):
        self.assertEqual(self.lm.restore(self.d), 'restored')
        self.assertEqual(self.lm.restore(self.c, hold=True), 'restored')
        p = self.plan_d()
        self.assertEqual(p['status'], 'skip-held')
        self.assertIn('liga-4d3c', p['reason'])


class FourStepsStartup(_StepD):
    """`startup()`/CLI: чотири кроки по порядку; підсумок напрямків одним рядком; підказка відкату — для останнього кроку."""

    def test_order_backups_and_one_restore_hint(self):
        st, err = self.start()
        self.assertEqual(st, 'done')
        marks = [m for m in re.findall(r'^(liga-4d\w+): done', err, re.M)]
        self.assertEqual(marks, ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D])
        stamps = self.backups()
        self.assertEqual(len(stamps), 4)
        self.assertEqual(err.count('відкат:'), 1)
        self.assertIn('відкат: bin/migrate_liga.py restore %s --hold' % stamps[-1], err)
        self.assertIn('раніші кроки (%s)' % ', '.join(stamps[:3]), err)
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual(sorted(last['steps']), ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D], 'звіт d не стирає звіти a, b, c')
        self.assertEqual(last['step'], D)

    def test_the_tracks_line_has_the_notes_and_no_paths(self):
        work = os.path.join(self.home, 'work')
        self.config(design_work_roots={'united': os.path.join(work, 'united'), 'seo': self.hidden_root()})
        _st, err = self.start()
        line = next(x for x in err.splitlines() if x.strip().startswith('напрямки:'))
        self.assertEqual(line.strip(), 'напрямки: записано; записи: 1; нотатки: root-dropped:seo, default-root-differs')
        self.assertNotIn(self.home, err)
        self.assert_no_secrets(err)

    def test_a_clean_parity_run_says_only_the_tracks_and_records(self):
        _st, err = self.start()
        line = next(x for x in err.splitlines() if x.strip().startswith('напрямки:'))
        self.assertEqual(line.strip(), 'напрямки: вже явні; записи: 1', 'крок а уже записав напрямки — d дописує лише записи')

    def test_skip_nothing_of_d_is_silent_and_the_second_start_prints_nothing(self):
        self.start()
        st, err = self.start()
        self.assertEqual((st, err), ('skip-done', ''))

    def test_the_not_migrated_line_when_d_is_skipped_for_a_reason(self):
        self.space_json({'migrations': {D: {'held': True}}})
        _st, err = self.start()
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)
        self.assertIn('нові задачі лягають у теку простору', err)
        os.makedirs(os.path.join(self.space_dir, '.git'))
        self.space_json({})
        _st, err = self.start()
        self.assertIn('liga-4d4a: skip-path-in-git', err)
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)

    def test_not_said_when_nothing_is_wrong(self):
        self.start()
        _st, err = self.start()
        self.assertNotIn(self.lm.TRACKS_NOT_MIGRATED, err)

    def test_an_abort_of_d_is_the_start_result_and_is_not_masked(self):
        self.config(profile_repos={'t%02d' % i: self.REPO_U for i in range(21)})
        st, err = self.start()
        self.assertEqual(st, 'abort-tracks')
        self.assertIn('liga-4d4a: abort-tracks', err)
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)
        self.assertEqual(len([m for m in re.findall(r'^liga-4d\w+: done', err, re.M)]), 3, 'a, b, c пройшли')

    def test_cli_run_dry_run_and_status(self):
        code, out, _err = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a: ready', out)
        self.assertIn('records: 1; notes: -', out)
        code, out, _err = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a: done', out)
        self.assertIn('  напрямки: вже явні; записи: 1; бекап: ', out)
        self.assertEqual(out.count('відкат:'), 1)
        code, out, _err = self.cli('status')
        self.assertEqual(code, 0)
        self.assertIn('ролі: -, напрямки: ні, записи: 1, нотатки: -', out)
        self.assert_no_secrets(out)

    def test_cli_prints_the_not_migrated_line_for_a_refused_step(self):
        self.space_json({'migrations': {D: {'held': True}}})
        code, out, _err = self.cli('run')
        self.assertEqual(code, 0, 'skip-held — не помилка')
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, out)



class FollowUpsOfTask2(_StepD):
    """Правки за ревʼю Task 2: A — `records`/`notes` видно в `status`; B — гонка за `tasks.json` між процесами; C — збій запису
    не лишає бекапів; D — `records` у звіті збою означає «записано», а не «планувалось»."""

    def test_a_status_shows_records_and_notes_codes_only(self):
        self.config(design_work_roots={'united': os.path.join(self.home, 'work', 'united'), 'seo': self.hidden_root()})
        self.assertEqual(self.lm.run(step=D), 'done')
        m = self.lm.status()['steps'][D]['mark']
        self.assertEqual((m['records'], m['notes']), (1, ['root-dropped:seo', 'default-root-differs']))
        text = self.lm.status_text(self.lm.status())
        self.assertIn('записи: 1, нотатки: root-dropped:seo, default-root-differs', text)
        self.assertNotIn(self.home, text)

    def _racing_copy2(self, times):
        """`shutil.copy2`, що ПІСЛЯ копії дописує в `tasks.json` чужу задачу (інший процес) `times` разів поспіль."""
        real, calls = self.lm.shutil.copy2, []

        def copy2(src, dst, *a, **kw):
            out = real(src, dst, *a, **kw)
            if len(calls) < times:
                cfg = self.read_json(self.tasks_path)
                cfg['tasks']['race%d' % len(calls)] = {'dir': '/x', 'profile': 'seo', 'pad': 'x' * (len(calls) + 1)}
                self._write(self.tasks_path, cfg)
            calls.append(1)
            return out
        return copy2

    def test_b_a_write_by_another_process_between_read_and_write_is_not_lost(self):
        with self.mock.patch.object(self.lm.shutil, 'copy2', self._racing_copy2(1)):
            self.assertEqual(self.lm.run(step=D), 'done')
        t = self.tasks()
        self.assertEqual((t['race0']['track'], t['a-2']['track']), ('seo', 'united'), 'чужу задачу збережено й виправлено')
        self.assertEqual(self.marks()[D]['records'], 2)

    def test_b_a_file_that_keeps_changing_is_abort_records_and_not_overwritten(self):
        with self.mock.patch.object(self.lm.shutil, 'copy2', self._racing_copy2(99)):
            self.assertEqual(self.lm.run(step=D), 'abort-records')
        self.assertNotIn('track', self.tasks()['a-2'], 'ми поверх чужого запису не писали')
        self.assertNotIn(D, self.marks() if os.path.exists(self.space_path()) else {})

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'root ігнорує права')
    def test_c_a_read_only_tasks_folder_gives_abort_records_without_a_backup(self):
        folder = os.path.dirname(self.tasks_path)
        before = os.listdir(os.path.join(self.deai, 'backups')) if os.path.isdir(os.path.join(self.deai, 'backups')) else []
        os.chmod(folder, 0o555)
        self.addCleanup(os.chmod, folder, 0o755)
        self.assertEqual(self.lm.run(step=D), 'abort-records')
        after = os.listdir(os.path.join(self.deai, 'backups')) if os.path.isdir(os.path.join(self.deai, 'backups')) else []
        self.assertEqual(after, before, 'бекап не створено — нема що чистити, коли збій постійний')

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'root ігнорує права')
    def test_c_a_read_only_tasks_file_gives_abort_records_without_a_backup(self):
        os.chmod(self.tasks_path, 0o444)
        self.addCleanup(os.chmod, self.tasks_path, 0o644)
        self.assertEqual(self.lm.run(step=D), 'abort-records')
        self.assertEqual(self.backups(), [])

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'root ігнорує права')
    def test_c_a_read_only_folder_does_not_matter_when_there_are_no_records(self):
        cfg = self.read_json(self.tasks_path)
        cfg['tasks']['a-2']['track'] = 'united'
        self._write(self.tasks_path, cfg)
        folder = os.path.dirname(self.tasks_path)
        os.chmod(folder, 0o555)
        self.addCleanup(os.chmod, folder, 0o755)
        self.assertEqual(self.lm.run(step=D), 'done', 'записувати tasks.json нема чого — не вимагаємо прав')

    def test_d_a_failed_records_write_reports_zero_written_and_the_planned_count(self):
        with self.mock.patch.object(self.lm.shutil, 'copy2', side_effect=OSError):
            st, info = self.lm._run(None, self.lm.STEP_D)
        self.assertEqual((st, info['records'], info['records_planned']), ('abort-records', 0, 1))
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['records'], 0)

    def test_d_a_failed_space_write_reports_the_records_really_written(self):
        with self.mock.patch.object(self.lm, '_write_space', side_effect=OSError):
            st, info = self.lm._run(None, self.lm.STEP_D)
        self.assertEqual((st, info['records'], info['records_planned']), ('abort-write', 1, 1))

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


# ---------------------------------------------------------------------------------------------------------------- Task 7: паритет після міграції

import tempfile  # noqa: E402

from test_liga_migrate_b import _ABSENT, _diff  # noqa: E402  (порівняння знімків ключ у ключ — імпорт, не друга копія)


def _collect(tmp, name, run_d=True):
    """Один стенд знімка 0.19.0 у НЕізольованому шарі (`DEAI_HOME` + реєстр просторів, без `DC_TASKS_FILE`) з ЛІГОЮ, мігрованою кроком D
    (`plain` — без D: звичайний простір). Збирає ті самі розділи, що `tests/make_before_4d4a.py`, але НОВИМИ формами підписів:
    `serve.track_root(sp, tid)` (без `cfg`), `roots.plan(cfg, view)`, `registry._work_root(cfg, entry)` через вигляд простору."""
    import liga_migrate as lm
    import registry
    import roots
    import serve
    from make_before_4d3a import Server, Vcs, scrub
    from make_before_4d3b import _call
    import make_before_4d4a as g
    rig, sp, cfg = g._stand(tmp, name)
    out, dinfo = {}, None
    spy = mock.MagicMock(return_value=False)
    with rig.activate(), mock.patch.object(serve, 'vcs_provider', Vcs()), mock.patch.object(serve, '_registry_push', spy), \
            mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None):
        if run_d and name != 'plain':
            dinfo = {'status': lm.run(step=lm.STEP_D), 'mark': lm.status()['steps'][D]['mark']}
        tasks = cfg['tasks']
        items, default = serve.space_tracks(sp)
        out['view'] = {'ids': [t['id'] for t in items], 'labels': [t['label'] for t in items], 'default': default,
                       'repos': {t['id']: t['repo'] for t in items}, 'ds': {t['id']: t['ds'] for t in items},
                       'roots': {t['id']: g.rel(t['root'], rig.home) for t in items}}
        values = g.VALUES + (('web', 'app') if name == 'plain' else ())
        out['repos'] = {repr(v): serve.track_repo(sp, v) for v in values}
        out['roots'] = {repr(v): g.rel(serve.track_root(sp, v), rig.home) for v in values}
        cfg = serve.load_legacy_tasks() if name != 'plain' else cfg          # tasks.json ПІСЛЯ кроку D (його читають і `roots`, і API)
        tasks = cfg['tasks']
        out['labels'] = {tid: serve.task_tags(t, sp) for tid, t in tasks.items()}
        out['ds'] = {tid: serve.task_ds(t, sp) for tid, t in tasks.items()}
        if name != 'plain':
            with serve.spaces.request_space(sp['id']):
                view = serve._TrackView(sp)
                out['roots_cli'] = {'plan': {r[0]: r[1:] for r in scrub([list(r) for r in roots.plan(cfg, view)], rig.home)},
                                    'in_use': {r[0]: r[1:] for r in scrub([list(r) for r in roots.roots_in_use(cfg, view)], rig.home)}}
                out['registry'] = {k: g.rel(registry._work_root(cfg, e), rig.home) for k, e in g.REGISTRY_ENTRIES.items()}
        with Server() as srv:
            posts = {}
            for key, body in g.POSTS:
                body = dict(body, space=sp['id'])
                st, resp = _call(srv, 'POST', '/api/task-new', body=body)
                row = {'status': st, 'code': resp.get('code') if isinstance(resp, dict) else None}
                with open(g.spaces_tasks_file(sp), encoding='utf-8') as f:
                    saved = json.load(f)['tasks']
                row['entry'] = g._entry_view(saved[body['id']], rig.home) if body['id'] in saved else None
                posts[key] = row
            out['task_new'] = posts
            api = {'task': {}}
            for tid in ('a-1', 'a-2', 'a-3', 'a-6', 'a-8'):
                if name == 'plain':
                    break
                st, body = srv.req('GET', '/api/task', task=tid)
                api['task'][tid] = {'status': st, 'keys': {k: True for k in sorted(body)} if isinstance(body, dict) else None,
                                    'profile': body.get('profile', '<absent>'), 'track': body.get('track'), 'tags': body.get('tags')}
            st, body = srv.req('GET', '/api/tasks')
            api['tasks'] = {'status': st, 'rows': [{k: r.get(k, '<absent>') for k in ('id', 'profile', 'track', 'tags')}
                                                    for r in sorted(body.get('tasks', []), key=lambda r: r['id'])
                                                    if r['id'].startswith('a-')]}
            st, body = srv.req('GET', '/api/spaces')
            row = next(r for r in body['spaces'] if r['id'] == sp['id'])
            api['space_row'] = {'tracks': row.get('tracks'), 'default_track': row.get('default_track')}
            out['api'] = api
    return scrub(out, rig.home), dinfo


def _flat(obj, path=''):
    from test_liga_migrate_b import _flat as flat
    return flat(obj, path)


def _no_profile(stand):
    """Знімок/стенд без ключа `profile` у відповідях API (його ВІДСУТНІСТЬ доводить `test_api_has_no_profile`): `api.task.*` (`profile`,
    `keys.profile`) і рядки `api.tasks.rows`."""
    s = json.loads(json.dumps(stand))
    api = s.get('api') or {}
    for row in (api.get('task') or {}).values():
        row.pop('profile', None)
        (row.get('keys') or {}).pop('profile', None)
    for row in (api.get('tasks') or {}).get('rows', []):
        row.pop('profile', None)
    return s


def _to(before, path, after):
    """Очікувана зміна листка: «було» береться з ЗНІМКА (`before`), «стало» — буквальне значення, закріплене тут."""
    return before_leaf(before, path), after


def before_leaf(before, path):
    return _flat(before).get(path, _ABSENT)


# Свідомі відмінності 0.19.0 → 0.20.0 на стендах знімка. Кожна група — з причиною (спека `2026-11-07-liga-tracks-final-design.md`
# «Свідомі відмінності» і ПОПРАВКИ плану); зайва різниця червоніє так само, як зникла очікувана.

#: `task-new` із `track` поза переліком/не за шаблоном — 400 для ВСІХ просторів (спека §5, відмінність 1): ЛІГА 0.19 приймала будь-який рядок.
_REJECTED = (('track_upper', 'bad-track'), ('track_with_slash', 'bad-track'), ('track_zzz', 'unknown-track'))


def _expect_task_new_common(before):
    exp = {}
    for key, code in _REJECTED:
        p = '/task_new/%s' % key
        exp[p + '/status'] = (200, 400)
        exp[p + '/code'] = (None, code)
        exp[p + '/entry'] = (_ABSENT, None)               # знімок: словник записів (листки), тепер — `None` (запису нема)
        for leaf, val in _flat(before['task_new'][key]['entry'], p + '/entry').items():
            exp[leaf] = (val, _ABSENT)
    # `profile` на вході — лише коли це id напрямку простору (спека §5): `United`/`zzz` ігноруються, задача — у дефолтний `united`
    # (його репо — `gitlab`); `track` пишеться, `profile` дзеркалить його (для колег на 0.14.0)
    for key, old in (('profile_upper', 'United'), ('profile_zzz', 'zzz')):
        p = '/task_new/%s/entry' % key
        exp[p + '/keys/gitlab'] = (_ABSENT, True)
        exp[p + '/profile'] = (old, 'united')
        exp[p + '/track'] = (old, 'united')
    return exp


def _expect_unknown_in_plan(before, ids):
    """`bin/roots.py plan`: задача без/з невідомим напрямком — «напрямок невідомий», не чіпається (Task 4/6: `track_root` невідомого
    дає дефолтний, а переселяти задачу без напрямку нема куди). У 0.19 такі задачі йшли в спільний корінь адаптера."""
    exp = {}
    for tid in ids:
        old = before['roots_cli']['plan'][tid]
        exp['/roots_cli/plan/%s[2]' % tid] = (old[2], None)
        exp['/roots_cli/plan/%s[3]' % tid] = (old[3], 'напрямок невідомий')
    return exp


def _expect_own(ids, now):
    """`roots_in_use`: «власний корінь» — тепер корінь явного напрямку; `now` — що стало."""
    return {'/roots_cli/in_use/%s[1]' % tid: (not now, now) for tid in ids}


def _expect_parity(before):
    exp = _expect_task_new_common(before)
    exp.update(_expect_own(('liga360', 'seo', 'united'), True))     # спільний корінь адаптера став явним коренем кожного напрямку
    exp.update(_expect_unknown_in_plan(before, ('a-6', 'a-8')))
    return exp


def _expect_explicit(before):
    exp = _expect_task_new_common(before)
    exp.update(_expect_own(('liga360', 'united'), True))            # `seo` мав власний корінь і в 0.19
    exp.update(_expect_unknown_in_plan(before, ('a-6', 'a-8')))
    return exp


def _expect_notes(before):
    """Корені, що їх адаптер брав зі спільного/системного/відносного, нотатки `root-dropped`/`default-root-differs` (спека §1, відмінність 2):
    `seo`, `liga360` — у теку простору; невідоме значення, `None` і порожнє — у корінь дефолтного `united`; `Bad_Key` — не напрямок."""
    space, united = '<tmp>/liga-space', '~/work/united'
    exp = _expect_task_new_common(before)
    exp.update(_expect_unknown_in_plan(before, ('a-4', 'a-5', 'a-6', 'a-8', 'a-9')))
    for k, v in {'/registry/both_conflict': space, '/registry/profile_only_seo': space, '/registry/track_only_seo': space,
                 '/registry/none': united, '/registry/profile_unknown': united,
                 "/roots/''": united, "/roots/'United'": united, "/roots/'zzz'": united, '/roots/7': united, '/roots/None': united,
                 "/roots/'liga360'": space, "/roots/'seo'": space,
                 '/roots_cli/in_use/United[0]': united, '/roots_cli/in_use/Weird[0]': united, '/roots_cli/in_use/zzz[0]': united,
                 '/roots_cli/in_use/—[0]': united, '/roots_cli/in_use/liga360[0]': space, '/roots_cli/in_use/seo[0]': space,
                 '/roots_cli/plan/a-1[2]': space + '/a-1', '/roots_cli/plan/a-3[2]': space + '/a-3', '/roots_cli/plan/a-7[2]': space + '/a-7',
                 '/task_new/profile_seo/entry/dir': space + '/n-pseo', '/task_new/track_seo/entry/dir': space + '/n-seo',
                 '/task_new/profile_upper/entry/dir': united + '/n-pup', '/task_new/profile_zzz/entry/dir': united + '/n-pzzz',
                 '/view/roots/liga360': None, '/view/roots/seo': None}.items():
        exp[k] = _to(before, k, v)
    exp.update(_expect_own(('liga360', 'seo'), False))              # корінь відкинуто: «власного» кореня нема
    exp['/roots_cli/in_use/Bad_Key[0]'] = _to(before, '/roots_cli/in_use/Bad_Key[0]', _ABSENT)     # ключ поза `ID_RE` — не напрямок
    exp['/roots_cli/in_use/Bad_Key[1]'] = _to(before, '/roots_cli/in_use/Bad_Key[1]', _ABSENT)
    return exp


def _expect_plain(before):
    """Звичайний простір: запис лише з `profile` (він ніколи не писав `track`) після 0.20 без напрямку — мітки й ДС нема (спека §3)."""
    return {'/ds/a-2': ('united', ''), '/labels/a-2[0]': ('united', _ABSENT), '/labels/a-2[]': (_ABSENT, [])}


EXPECT_BUILDERS = {'parity': _expect_parity, 'notes': _expect_notes, 'explicit': _expect_explicit, 'plain': _expect_plain}

#: Що бачить людина: мітки, ДС-аргумент, репо, перелік напрямків (крім коренів нових задач), відповіді API (крім `profile`).
_SEEN = ('/labels', '/ds', '/repos', '/api/', '/view/ids', '/view/labels', '/view/default', '/view/repos', '/view/ds')


class AfterMigrationParity4d4a(unittest.TestCase):
    """Сценарії знімка 0.19.0 (`before-4d4a.json`) на МІГРОВАНІЙ ЛІЗІ, НЕізольовано: `DEAI_HOME` + реєстр просторів, без `DC_TASKS_FILE`/
    `DC_NO_OVERVIEW` (шлях власника; живі тести ізольовані і його не доводять). Три стенди ЛІГИ проходять крок D кодом (`lm.run(step=
    STEP_D)`), `plain` — без нього. Збір — `_collect` (ті самі розділи, що в генераторі знімка, нові підписи функцій). Мережі нема
    (`NoNet`, `SocketTripwire`), справжній `~/.deai` стереже `spaces_guard`."""

    @classmethod
    def setUpClass(cls):
        import contextlib
        from make_before_4d3a import CLEAN, NoNet, SocketTripwire
        import deai_modules as dm
        with open(BEFORE, encoding='utf-8') as f:
            cls.before = json.load(f)['stands']
        cls.after, cls.dinfo, cls.wire_count = {}, {}, 0
        with contextlib.ExitStack() as stack:
            tmp = os.path.realpath(stack.enter_context(tempfile.TemporaryDirectory(prefix='after-4d4a-')))
            home = os.path.join(tmp, 'home')
            os.makedirs(home)
            # `DEAI_HOME` тут — запобіжник (стереже статичний `TestsCannotWriteLiveConfig`): кожен стенд ставить власний через `rig.activate()`
            stack.enter_context(mock.patch.dict(os.environ, {'HOME': home, 'DEAI_HOME': os.path.join(home, '.deai')}))
            wire = stack.enter_context(SocketTripwire())
            stack.enter_context(mock.patch('urllib.request.urlopen', NoNet()))
            for name in CLEAN:
                os.environ.pop(name, None)
            for name in STANDS:
                dm.reset_caches()
                cls.after[name], cls.dinfo[name] = _collect(tmp, name)
            dm.reset_caches()
            cls.wire_count = wire.count

    def _diff(self, name):
        return _diff(_no_profile(self.before[name]), _no_profile(self.after[name]))

    def test_all_steps_ran(self):
        """Три ЛІГИ справді мігровано кроком D (`done`, позначка з бекапом); `plain` крок не бачив. Мережі не було."""
        self.assertEqual(self.wire_count, 0)
        for name, (records, tracks_written, notes) in {
                'parity': (1, True, []), 'explicit': (1, False, []),
                'notes': (2, True, ['root-dropped:liga360', 'root-dropped:seo', 'unknown-values', 'default-root-differs', 'non-id-keys'])}.items():
            d = self.dinfo[name]
            self.assertEqual(d['status'], 'done', name)
            m = d['mark']
            self.assertEqual((m['records'], m['tracks'], m['notes'], m['roles']), (records, tracks_written, notes, []), name)
            self.assertRegex(m['backup'], r'-liga-4d4a$')
        self.assertIsNone(self.dinfo['plain'])

    def test_snapshot_is_big_enough_to_mean_something(self):
        """Порівняння не порожнє: сотні листків на стенд, ті самі розділи, що в знімку (інакше «нема відмінностей» нічого б не казало)."""
        for name in STANDS:
            self.assertEqual(sorted(self.after[name]), sorted(self.before[name]), name)
            self.assertGreater(len(_flat(self.before[name])), 100 if name == 'plain' else 250, name)

    def test_only_expected_differences_parity(self):
        self.assertEqual(self._diff('parity'), _expect_parity(self.before['parity']))

    def test_only_expected_differences_notes(self):
        self.assertEqual(self._diff('notes'), _expect_notes(self.before['notes']))

    def test_only_expected_differences_explicit(self):
        self.assertEqual(self._diff('explicit'), _expect_explicit(self.before['explicit']))

    def test_only_expected_differences_plain(self):
        self.assertEqual(self._diff('plain'), _expect_plain(self.before['plain']))

    def test_expected_diff_is_exact_not_loose(self):
        """Охоронець самого порівняння: зайвий листок і зниклий очікуваний — обидва червоніють на КОЖНОМУ стенді."""
        for name in STANDS:
            exp = EXPECT_BUILDERS[name](self.before[name])
            before = _no_profile(self.before[name])
            extra = _no_profile(self.after[name])
            extra['labels']['a-1'] = ['змінено']                                        # зайвий листок
            d = _diff(before, extra)
            self.assertIn('/labels/a-1[0]', d)
            self.assertNotEqual(d, exp, name)
            missing = _no_profile(self.after[name])
            if name == 'plain':
                missing['ds']['a-2'] = self.before[name]['ds']['a-2']                   # очікувана зміна «не сталась»
            else:
                missing['task_new']['track_zzz'] = self.before[name]['task_new']['track_zzz']
            d = _diff(before, missing)
            self.assertNotEqual(d, exp, name)
            self.assertNotIn('/ds/a-2' if name == 'plain' else '/task_new/track_zzz/status', d)

    def test_nothing_a_person_sees_changed(self):
        """Мітки, `?ds=`, репо, перелік напрямків і ВСІ відповіді API (крім `profile`) — рівно знімок: жодної різниці під `_SEEN` на
        жодній ЛІЗІ, і розділи непорожні. Єдина різниця для людини — на `plain` (запис лише з `profile`, спека §3)."""
        for name in ('parity', 'notes', 'explicit'):
            self.assertEqual([p for p in self._diff(name) if p.startswith(_SEEN)], [], name)
            flat = _flat(self.after[name])
            for prefix in ('/labels/', '/ds/', '/repos/', '/api/task/', '/api/tasks/', '/view/ids'):
                self.assertGreater(len([k for k in flat if k.startswith(prefix)]), 3, name + ' ' + prefix)
        self.assertEqual(sorted(p for p in self._diff('plain') if p.startswith(_SEEN)), ['/ds/a-2', '/labels/a-2[0]', '/labels/a-2[]'])

    def test_api_has_no_profile(self):
        """`/api/task` і рядки `/api/tasks` більше не віддають `profile` (спека §3, відмінність 3); `track` і `tags` — як були."""
        for name in ('parity', 'notes', 'explicit'):
            api = self.after[name]['api']
            self.assertEqual(sorted(api['task']), ['a-1', 'a-2', 'a-3', 'a-6', 'a-8'])
            for tid, row in api['task'].items():
                self.assertEqual(row['status'], 200, (name, tid))
                self.assertNotIn('profile', row['keys'], (name, tid))
                self.assertEqual(row['profile'], '<absent>', (name, tid))
                self.assertIn('track', row['keys'], (name, tid))
            self.assertGreaterEqual(len(api['tasks']['rows']), 6)
            for row in api['tasks']['rows']:
                self.assertEqual(row['profile'], '<absent>', (name, row['id']))
        # контроль: у знімку 0.19.0 `profile` БУВ — тест не порожній
        self.assertIn('profile', self.before['parity']['api']['task']['a-2']['keys'])

    def test_a_profile_only_record_keeps_its_label_ds_and_registry_root(self):
        """Серце паритету: `a-2` має лише `profile: united` — без дописаного кроком `track` він втратив би мітку й ДС. Тепер (після D) — ті
        самі, що знімок; і корінь запису реєстру лише з `profile: seo` — корінь напрямку `seo` (там, де він є)."""
        for name in ('parity', 'notes', 'explicit'):
            self.assertEqual(self.after[name]['labels']['a-2'], ['United'], name)
            self.assertEqual(self.after[name]['ds']['a-2'], 'united', name)
        self.assertEqual(self.after['explicit']['registry']['profile_only_seo'], '~/work/seo')
        self.assertEqual(self.after['parity']['registry']['profile_only_seo'], '~/work/shared')



BEFORE_4D1 = os.path.join(_HERE, 'fixtures', 'tracks', 'before-4d1.json')


class AfterMigrationServer4d4a(_StepD):
    """Сценарії знімка 0.14.0 (`tracks/before-4d1.json`: мітки, сторінки, `task_new`, маршрут) через СПРАВЖНІЙ `serve` на ЛІЗІ, мігрованій кроком D
    у НЕізольованому шарі (`DEAI_HOME` + реєстр; `DC_TASKS_FILE` нема). До 4d-4a ці перевірки були в `test_tracks.py::ServerLegacyParity`
    на неявному просторі з адаптером; адаптера нема — предмет той самий: те, що бачить людина, після кроку D лишилось, а свідомі
    відмінності названі окремо. Конфіг — той, що генератор знімка: `united`/`seo` зі своїми коренями, спільний `shared`, репо `united`/`seo`.
    Тимчасові `HOME`/`DEAI_HOME` — з `_Stand.setUp`; мережі нема."""

    def setUp(self):
        super().setUp()
        import make_before_4d1 as gen
        import serve
        self.gen, self.serve = gen, serve
        with open(BEFORE_4D1, encoding='utf-8') as f:
            self.snap = json.load(f)
        for name in gen.CLEAN:
            if name != 'DEAI_HOME':
                os.environ.pop(name, None)
        w = os.path.join(self.home, 'work')
        self.shared, self.united_root, self.seo_root = (os.path.join(w, n) for n in ('shared', 'united', 'seo'))
        self.cfg_base = {'design_work_roots': {'united': self.united_root, 'seo': self.seo_root}, 'design_work_root': self.shared,
                         'profile_repos': dict(gen.REPOS)}
        self.vcs = gen.Vcs()                                  # `vcs_provider` → `None` (ролі нема), рахує, скільки разів питали
        self.pushes = []
        for name, new in (('vcs_provider', self.vcs), ('_registry_push', lambda tid: self.pushes.append(tid) or False),
                          ('git_autocommit', lambda *a, **k: None)):
            patcher = self.mock.patch.object(serve, name, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = self.mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        net = self.mock.patch.object(serve.urllib.request, 'urlopen', gen.NoNet())
        self.net = net.start()
        self.addCleanup(net.stop)

    def migrate(self, tasks, **extra):
        """Конфіг знімка + задачі `tasks` → крок D → `(sp, мігрований cfg)`."""
        self.config(supabase=False, jira=False, tasks=tasks, **dict(self.cfg_base, **extra))
        self.assertEqual(self.lm.run(step=D), 'done')
        sp = self.spaces.active_space()
        self.assertEqual(sp['id'], 'legacy')
        return sp, self.serve.load_legacy_tasks()

    def rel(self, text):
        return self.gen.rel(text, self.home)

    # --- a: мітки, всі 24 сценарії знімка
    def test_a_tags_every_scenario_after_the_step(self):
        serve, spaces = self.serve, self.spaces
        scen = self.snap['tags']
        self.assertEqual(len(scen), 24)
        tasks = {'t%02d' % i: dict(sc['task']) for i, (_n, sc) in enumerate(sorted(scen.items())) if isinstance(sc['task'], dict)}
        sp, cfg = self.migrate(tasks)
        n = 0
        for i, (name, sc) in enumerate(sorted(scen.items())):
            want = sc['result']['result']
            task = cfg['tasks']['t%02d' % i] if isinstance(sc['task'], dict) else sc['task']     # запис ПІСЛЯ кроку: `track` дописано
            with self.subTest(scenario=name):
                self.assertEqual(serve.task_tags(task, sp), want)
                with spaces.request_space(sp['id']):
                    self.assertEqual(serve.task_tags(task), want)                                 # без `sp` — простір запиту
                n += 1
        self.assertEqual(n, 24)
        # профіль-число лишився без `track` (крок пише лише непорожній РЯДОК) і дає порожньо, як 0.14.0
        self.assertNotIn('track', cfg['tasks']['t%02d' % sorted(scen).index('no_tags_profile_5')])

    # --- b: розмітка `/commented` через справжній сервер для всіх готових задач знімка
    def set_current(self, tid):
        cfg = self.read_json(self.tasks_path)
        cfg['current'] = tid
        self._write(self.tasks_path, cfg)

    def test_b_pages_through_a_real_server(self):
        import http.client
        gen = self.gen
        seeded, ids = gen._seeded(self.home)
        for tid in ids:
            self._write(os.path.join(seeded['tasks'][tid]['dir'], 'iterations', 'it1', 'index.html'),
                        '<!DOCTYPE html><html><head><title>t</title></head><body><h1>Alpha</h1></body></html>')
        sp, _cfg = self.migrate(seeded['tasks'], supabase_url='https://demo.supabase.example', supabase_key='pk-test-1')
        want = self.snap['pages']
        got = {}
        with gen.Server() as srv:
            for tid in ids:
                row = {}
                for key, query in (('local', '/commented?it=it1'), ('project', '/commented?it=it1&ch=project')):
                    self.set_current(tid)
                    try:
                        st, html = srv.req('GET', query, raw_text=True)
                    except (http.client.HTTPException, OSError) as e:
                        row[key] = {'status': None, 'error': type(e).__name__}
                        continue
                    row[key] = {'status': st, 'inspector_tails': gen._INSPECTOR_SRC.findall(html or ''),
                                'project_channel': isinstance(html, str) and '__deaiCommentsCfg' in html}
                got[tid] = row
        self.assertEqual(sorted(got), sorted(k for k in want if k != 'urlopen_calls'))
        n = 0
        for tid, row in got.items():
            for ch in ('local', 'project'):
                cell = row[ch]
                if tid == 's-five':                       # свідома відмінність: 0.14.0 рвав зʼєднання на профілі-числі, тепер чиста сторінка без `?ds=`
                    self.assertEqual(want[tid][ch], {'error': 'RemoteDisconnected', 'status': None}, ch)
                    self.assertEqual((cell['status'], cell['inspector_tails'], cell['project_channel']), (200, ['?sp=legacy'], ch == 'project'))
                    continue
                # шар увімкнено: до `?ds=` додається `sp=<простір>` (у знімку шар був вимкнений — `sp` не було); решта — рівно знімок
                self.assertEqual(len(cell['inspector_tails']), 1, (tid, ch))
                tail = cell['inspector_tails'][0]
                self.assertTrue(tail.endswith('sp=legacy'), (tid, ch, tail))
                tail = tail[:-len('&sp=legacy')] if tail != '?sp=legacy' else ''
                self.assertEqual({**cell, 'inspector_tails': [tail]}, {k: v for k, v in want[tid][ch].items()}, (tid, ch))
                n += 1
        self.assertEqual(n, 18)                           # 9 задач × 2 канали (`s-five` — окремо)
        self.assertEqual(self.net.calls, 0)

    # --- c: пряме `task_new` для кожного профілю знімка
    def test_c_direct_task_new_matches_the_snapshot_modulo_the_default_root(self):
        serve, gen = self.serve, self.gen
        sp, _cfg = self.migrate({}, profile_repos={'united': gen.REPOS['united']})              # як у знімку: репо лише в `united`
        self.assertEqual(sorted(self.snap['task_new']), sorted(str(p) for p in gen.PROFILES))
        for prof in gen.PROFILES:
            with self.subTest(profile=prof):
                cfg = serve.load_legacy_tasks()
                cfg['tasks'].pop('t1', None)
                calls = self.vcs.calls
                res = serve.task_new(cfg, 't1', track=prof, legacy=True, root=serve.track_root(sp, prof), repo=serve.track_repo(sp, prof))
                saved = serve.load_legacy_tasks()
                want = self.snap['task_new'][str(prof)]
                view = gen._entry_view(saved['tasks']['t1'], self.home)
                entry, keys = dict(view['entry']), list(view['keys'])
                track = entry.pop('track', '<нема>')
                if 'track' in keys:
                    keys.remove('track')
                # свідома відмінність (спека §2): невідомий напрямок і `None` лягають у корінь ДЕФОЛТНОГО напрямку (`united`), а не в спільний
                shared_to_default = prof in ('zzz', None)
                want_dir = '~/work/united/t1' if shared_to_default else want['entry']['dir']
                self.assertEqual(want['entry']['dir'], '~/work/shared/t1' if shared_to_default else want_dir)
                self.assertEqual(entry, {**want['entry'], 'dir': want_dir})        # `gitlab`, `title`, `jira`, `profile` — як було
                self.assertEqual(sorted(keys), want['keys'])
                self.assertEqual(track, '<нема>' if prof is None else prof)        # `track` дзеркалить значення; `None` — не пишеться
                self.assertEqual(entry['profile'], prof)                           # `profile` лишається (колеги на 0.14.0 читають його)
                self.assertEqual({**{k: v for k, v in res.items() if k != 'dir'}, 'dir': gen.rel(res['dir'], self.home)},
                                 {**want['result'], 'dir': want_dir})
                self.assertEqual((saved['current'], view['has_opened']), (want['current'], want['has_opened']))
                self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'iterations', 'it1', 'index.html')))
                self.assertEqual(self.vcs.calls - calls, want['vcs_provider_calls'])
        self.assertEqual(self.net.calls, 0)

    # --- d: маршрут `POST /api/task-new`, сценарії знімка
    def post_scenarios(self, srv, sp, posts):
        out = {}
        for name, body in posts:
            st, resp = srv.req('POST', '/api/task-new', dict(body, space=sp['id']))
            row = {'status': st, 'ok': resp.get('ok'), 'code': resp.get('code')} if isinstance(resp, dict) else {'status': st}
            if isinstance(resp, dict) and 'dir' in resp:
                row['dir'] = self.rel(resp['dir'])
            saved = self.serve.load_legacy_tasks()['tasks'].get(body['id'])
            row['entry'] = None if saved is None else {k: self.rel(v) if k == 'dir' else v for k, v in saved.items() if k != 'opened'}
            out[name] = row
        return out

    def test_d_route_task_new_matches_the_snapshot_modulo_the_named_differences(self):
        """11 із 12 сценаріїв `POST /api/task-new` знімка (12-й, `profile: 5` → `bad-profile`, — той самий 400) на мігрованій ЛІЗІ: статус, код, тека й
        запис — рівно знімок, КРІМ названих відмінностей. (1) запис несе й `track` (= `profile`; знімок 0.14.0 його не мав). (2) `profile` поза
        переліком напрямків (`zzz`, `United`) тепер ІГНОРУЄТЬСЯ (спека §5, відмінність 1): задача — у дефолтному `united` (його корінь і репо)."""
        sp, _cfg = self.migrate({}, profile_repos=dict(self.gen.REPOS))
        with self.gen.Server() as srv:
            got = self.post_scenarios(srv, sp, self.gen._POSTS)
        want = self.snap['route']['task_new']
        self.assertEqual(sorted(got), sorted(want))
        united_repo = {'path': 'mockup/%s', 'repo': self.gen.REPOS['united']}
        overrides = {                                                                 # сценарій → (id задачі, `gitlab`, що додається)
            'unknown_zzz': ('r-zzz', dict(united_repo, path='mockup/r-zzz')),
            'uppercase_United': ('r-upper', dict(united_repo, path='mockup/r-upper')),
            'explicit_gitlab': ('r-gl', None)}                                        # явний `gitlab` лишився; змінюються тека й `profile`
        n = 0
        for name, row in got.items():
            w = want[name]
            if w['status'] != 200:
                self.assertEqual((row['status'], row['code'], row['ok'], row['entry']), (w['status'], w['code'], w['ok'], None), name)
                continue
            entry = dict(row['entry'])
            self.assertEqual(entry.pop('track'), entry['profile'], name)           # відмінність (1): `track` дзеркалить `profile`
            exp_entry, exp_dir = dict(w['entry']), w['dir']
            if name in overrides:                                                  # відмінність (2)
                tid, gitlab = overrides[name]
                exp_dir = '~/work/united/' + tid
                exp_entry.update(dir=exp_dir, profile='united')
                if gitlab:
                    exp_entry['gitlab'] = gitlab
            self.assertEqual((row['status'], row['code'], row['ok'], row['dir']), (200, None, True, exp_dir), name)
            self.assertEqual(entry, exp_entry, name)
            n += 1
        self.assertEqual(n, 11)
        self.assertEqual(self.net.calls, 0)


class DefaultRootAndLayerOff4d4a(_StepD):
    """Корінь нової задачі без адаптера (Поправка 5 плану) — НЕізольовано, на ЛІЗІ після кроку D: `default_task_root(cfg)` у всіх формах
    `design_work_root` (є, нема, не рядок, список, `~`), пряме `task_new` без `root`, `track_root` невідомого напрямку (→ корінь дефолтного) і
    ЛІГА зі шаром ВИМКНЕНИМ (`DC_TASKS_FILE` без `DEAI_HOME`: неявний простір, напрямків нема, `track_root` → `None`)."""

    def setUp(self):
        super().setUp()
        import serve
        self.serve = serve
        for name in ('vcs_provider', '_registry_push', 'git_autocommit'):
            p = self.mock.patch.object(serve, name, lambda *a, **k: None)
            p.start()
            self.addCleanup(p.stop)

    def test_e_default_task_root_pins(self):
        serve = self.serve
        home = os.path.expanduser('~')
        self.assertEqual(home, self.home)
        self.assertEqual(serve.DEFAULT_TASK_ROOT, '~/deai-work')
        for cfg, want in (({'design_work_root': '/srv/shared'}, '/srv/shared'),
                          ({'design_work_root': '~/work/shared'}, os.path.join(home, 'work', 'shared')),       # `~` розгорнуто
                          ({}, os.path.join(home, 'deai-work')),                                               # нема → дефолт у домівці
                          ({'design_work_root': ''}, os.path.join(home, 'deai-work')),
                          ({'design_work_root': None}, os.path.join(home, 'deai-work')),
                          ({'design_work_root': 5}, os.path.join(home, 'deai-work')),                          # не рядок
                          ({'design_work_root': ['/srv/x']}, os.path.join(home, 'deai-work')),                 # список
                          ({'design_work_root': {'a': 1}}, os.path.join(home, 'deai-work')),
                          (None, os.path.join(home, 'deai-work')), ([], os.path.join(home, 'deai-work'))):     # сам cfg не словник
            with self.subTest(cfg=cfg):
                self.assertEqual(serve.default_task_root(cfg), want)
        self.assertFalse(os.path.exists(os.path.join(home, 'deai-work')), 'порожню теку дефолтного кореня сам `default_task_root` не створює')

    def test_e_direct_task_new_without_root_lands_in_the_default_root(self):
        serve = self.serve
        cfg = {'tasks': {}, 'current': None, 'design_work_root': os.path.join(self.home, 'work', 'shared')}
        res = serve.task_new(cfg, 'direct-1', track='united')
        self.assertEqual(res['dir'], os.path.join(self.home, 'work', 'shared', 'direct-1'))
        cfg = {'tasks': {}, 'current': None}
        res = serve.task_new(cfg, 'direct-2')
        self.assertEqual(res['dir'], os.path.join(self.home, 'deai-work', 'direct-2'), 'без кореня й без `design_work_root` — `~/deai-work` ТЕСТОВОЇ домівки')

    def migrated(self):
        self.config(supabase=False, jira=False, design_work_roots={'united': os.path.join(self.home, 'work', 'united'),
                                                                    'seo': os.path.join(self.home, 'work', 'seo')})
        self.assertEqual(self.lm.run(step=D), 'done')
        return self.spaces.active_space()

    def test_g_an_unknown_track_gets_the_root_of_the_default_track(self):
        """Спека §2: невідомий напрямок → `root` ДЕФОЛТНОГО (у 0.19 — спільний корінь адаптера); відомий — свій; `repo` невідомого — `''`."""
        serve = self.serve
        sp = self.migrated()
        united, seo, shared = (os.path.join(self.home, 'work', n) for n in ('united', 'seo', 'shared'))
        self.assertEqual((serve.track_root(sp, 'united'), serve.track_root(sp, 'seo'), serve.track_root(sp, 'liga360')), (united, seo, shared))
        for unknown in ('zzz', 'United', '', None, 7, ['united'], 'Bad/Id'):
            with self.subTest(track=unknown):
                self.assertEqual(serve.track_root(sp, unknown), united)
                self.assertEqual(serve.track_repo(sp, unknown), '')
        # напрямки без `root` — шлях простору (не «нема»)
        self.assertEqual(serve.track_root(self.spaces.active_space(), 'united'), united)

    def test_g_a_space_without_a_default_track_root_falls_back_to_the_space_path(self):
        serve = self.serve
        self.space_json({'tracks': [{'id': 'web', 'label': 'Web'}], 'default_track': 'web'})
        sp = self.spaces.active_space()
        self.assertEqual((serve.track_root(sp, 'web'), serve.track_root(sp, 'zzz'), serve.track_root(sp, None)), (self.space_dir,) * 3)
        self.space_json({})
        self.assertEqual(serve.track_root(sp, 'web'), self.space_dir, 'напрямків нема — шлях простору')

    def test_f_the_layer_off_implicit_space_has_no_tracks(self):
        """Шар ВИМКНЕНО (`DC_TASKS_FILE` без `DEAI_HOME`): адаптер колись давав тут `united`/`liga360`/`seo` з кореня `tasks.json`; тепер — ніяких
        напрямків, `track_root` → `None` (викликач бере `default_task_root`), мітка — значення як є."""
        serve, spaces = self.serve, self.spaces
        self.config(supabase=False, jira=False, design_work_roots={'united': os.path.join(self.home, 'work', 'united')},
                    tasks={'p-1': {'dir': '/x', 'profile': 'united'}, 'p-2': {'dir': '/x', 'track': 'seo'}})
        with self.mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}):                 # `patch.dict` повертає оточення на виході
            os.environ['DC_TASKS_FILE'] = self.tasks_path                                # ізольований режим: файл задач — тимчасовий
            os.environ.pop('DEAI_HOME')
            self.assertFalse(spaces.layer_on())
            sp = spaces.active_space()
            self.assertIsNone(spaces.describe(sp))
            self.assertEqual(serve.space_tracks(sp), ([], None))
            for t in ('united', 'seo', None, 'zzz'):
                self.assertIsNone(serve.track_root(sp, t), repr(t))
                self.assertEqual(serve.track_repo(sp, t), '', repr(t))
            cfg = serve.load_tasks()
            self.assertEqual(serve.task_tags(cfg['tasks']['p-1'], sp), [])                        # лише `profile`: без `track` мітки нема
            self.assertEqual(serve.task_tags(cfg['tasks']['p-2'], sp), ['seo'])                   # `track` без напрямків — значення як є
            self.assertEqual(serve.task_ds(cfg['tasks']['p-2'], sp), 'seo')
            res = serve.task_new(cfg, 'off-1', track='united', legacy=True, root=serve.track_root(sp, 'united') or serve.default_task_root(cfg))
            self.assertEqual(res['dir'], os.path.join(self.home, 'work', 'shared', 'off-1'), 'нема напрямків → `design_work_root` кореня файла')


class Task3Minors4d4a(_StepD):
    """Правки за ревʼю Task 3, доведені в Task 7: (1) `_records_writable` дивиться й на наявний `tasks.json.bak`; (2) `.bak` на успіху = байти ДО
    міграції, а `tasks.json` на відмові — нетронутий; (3) підказка «напрямки не мігровані» НЕ друкується для жодного тихого статусу
    (у т.ч. `skip-busy`, мутація якого раніше виживала) і друкується для кожного іншого."""

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'root ігнорує права')
    def test_an_unwritable_bak_is_abort_records_before_any_backup(self):
        bak = self.tasks_path + '.bak'
        self._write(bak, '{"old": true}')
        os.chmod(bak, 0o444)
        self.addCleanup(os.chmod, bak, 0o644)
        before, bak_before = self.read(self.tasks_path), self.read(bak)
        self.assertEqual(self.lm.run(step=D), 'abort-records')
        self.assertEqual(self.backups(), [], 'бекапу кроку нема: збій передбачено ДО нього')
        self.assertEqual((self.read(self.tasks_path), self.read(bak)), (before, bak_before))
        self.assertFalse(self.lm._records_writable(self.tasks_path))
        os.chmod(bak, 0o644)
        self.assertTrue(self.lm._records_writable(self.tasks_path))

    def test_records_writable_is_true_without_a_bak_and_with_a_writable_one(self):
        self.assertFalse(os.path.exists(self.tasks_path + '.bak'))
        self.assertTrue(self.lm._records_writable(self.tasks_path))
        self._write(self.tasks_path + '.bak', '{}')
        self.assertTrue(self.lm._records_writable(self.tasks_path))

    def test_an_existing_bak_is_replaced_by_the_pre_migration_bytes(self):
        self._write(self.tasks_path + '.bak', '{"stale": true}')
        old = self.read(self.tasks_path)
        self.assertEqual(self.lm.run(step=D), 'done')
        self.assertEqual(self.read(self.tasks_path + '.bak'), old)
        self.assertNotEqual(self.read(self.tasks_path), old)

    def test_tasks_json_is_untouched_by_every_abort_before_the_write(self):
        before = self.read(self.tasks_path)
        self.config(profile_repos={'t%02d' % i: self.REPO_U for i in range(21)})          # `abort-tracks`
        before = self.read(self.tasks_path)
        self.assertEqual(self.lm.run(step=D), 'abort-tracks')
        self.assertEqual(self.read(self.tasks_path), before)
        self.assertFalse(os.path.exists(self.tasks_path + '.bak'), 'бекап `.bak` — лише коли записуємо')
        self.assertEqual(self.backups(), [])

    def stub_d(self, status):
        """Контекст: крок D «закінчується» заданим статусом (інші кроки не біжать) — перевіряємо ЛИШЕ вибір рядка-підказки. ⛔ Тільки
        локальні `with`-підміни: `patch.stopall()` зняв би й підміну `HOME`/`DEAI_HOME` стенда (тест пішов би в справжній `~/.deai`)."""
        import contextlib
        stack = contextlib.ExitStack()
        stack.enter_context(self.mock.patch.object(self.lm, 'STEPS', (self.lm.STEP_D,)))
        stack.enter_context(self.mock.patch.object(self.lm, '_run', lambda home, step: (status, {'reason': 'x'})))
        return stack

    def test_the_hint_is_not_printed_for_any_quiet_status_and_is_for_every_other(self):
        # ⛔ Тихий перелік ЗАШИТО літералом: очікування, виведене з самої константи, пропустило б мутацію «додати/прибрати статус»
        quiet = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-nothing', 'skip-integrations-off', 'skip-busy')
        self.assertEqual(sorted(self.lm.TRACKS_QUIET), sorted(quiet))
        every = tuple(dict.fromkeys(('done',) + self.lm.SKIP_CODES + self.lm.ABORT_CODES))
        self.assertTrue(set(quiet) <= set(every), set(quiet) - set(every))
        loud = sorted(set(every) - set(quiet))
        self.assertIn('skip-held', loud)
        self.assertIn('abort-records', loud)
        for status in every:
            with self.subTest(status=status), self.stub_d(status):
                _st, err = self.start()
                self.assertEqual(self.lm.TRACKS_NOT_MIGRATED in err, status not in quiet, (status, err))
                self.assertEqual(self.lm.tracks_not_migrated(status), status not in quiet)

    def test_the_cli_prints_the_hint_only_for_a_non_quiet_status(self):
        for status in ('done', 'skip-busy', 'skip-nothing', 'skip-held', 'abort-records'):
            with self.subTest(status=status), self.stub_d(status):
                _code, out, _err = self.cli('run')
                self.assertEqual(self.lm.TRACKS_NOT_MIGRATED in out, status not in self.lm.TRACKS_QUIET, status)


class LigaFlowPositive4d4a(_StepD):
    """Позитивний шлях `_liga_flow` на ЛІЗІ у НЕізольованому шарі (стенд кроку D: тимчасові `HOME`/`DEAI_HOME`, реєстр з простором ЛІГИ)."""

    def test_j_liga_flow_recognises_a_track_with_a_repo_in_a_liga_space_whose_integrations_are_off(self):
        """Ознака потоку ЛІГА (Task 6) — `profile`/`track` = id напрямку з непорожнім `repo` у просторі ЛІГИ реєстру (`legacy: true`), ЯКИЙ БИ
        не був його прапорець `integrations` (тут — `false`, як у 0.19 без інтеграцій). Інакше — лише `jira`/`gitlab`."""
        import serve
        reg = self.read_json(self.deai, 'spaces.json')
        reg['spaces'][0]['integrations'] = False
        self._write(os.path.join(self.deai, 'spaces.json'), reg)
        self.space_json({'tracks': [{'id': 'united', 'repo': self.REPO_U}, {'id': 'seo'}], 'default_track': 'united'})
        for payload, want in (({'profile': 'united'}, True), ({'track': 'united'}, True), ({'track': 'united', 'profile': 'seo'}, True),
                              ({'profile': 'seo'}, False), ({'track': 'zzz'}, False), ({'profile': 5}, False), ({'profile': ''}, False),
                              ({'profile': 'United'}, False), ({}, False),
                              ({'jira': 'LIGA-1'}, True), ({'jira': '  '}, False), ({'gitlab': {'repo': 'git@x:y/z.git'}}, True)):
            with self.subTest(payload=payload):
                self.assertIs(serve._liga_flow(payload), want)
        self.space_json({'tracks': [{'id': 'united'}]})                               # репо нема — напрямок не ознака
        self.assertIs(serve._liga_flow({'profile': 'united'}), False)
        self._write(os.path.join(self.deai, 'spaces.json'), '{broken')               # реєстр не читається — не ознака, не 500
        self.assertIs(serve._liga_flow({'profile': 'united'}), False)
        self.assertIs(serve._liga_flow({'jira': 'LIGA-1'}), True)

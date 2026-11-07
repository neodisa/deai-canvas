"""Етап 4d-4b: п'ятий крок міграції ЛІГИ `liga-4d4b` — останні оригінали кореня `tasks.json` (копія в запис і видалення з кореня)."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402
from test_liga_migrate import _WriteStand  # noqa: E402

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard` (тести пишуть лише у власні тимчасові теки)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class _StandE(_WriteStand):
    """Стенд кроку Е: простір ЛІГА з УЖЕ мігрованими A–C записами (рівні оригіналам) і коренем з усіма вісьмома ключами."""

    SSH, HOSTIP, PW = '~/.ssh/id_example', '203.0.113.7', 'pw-alpha'
    ALL = ('supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip', 'preview_password')

    def setUp(self):
        super().setUp()
        self.secret_values = (self.SB_KEY, self.JIRA_TOKEN, self.PW)
        self.lm_steps = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS)
        self.lm_steps.start()
        self.addCleanup(self.lm_steps.stop)
        self.E = self.lm.STEP_E
        self.rec_all()

    # --- стенд
    def rec_all(self, **over):
        """Явні записи A–C (рівні кореню) + `secrets.json`; `over` — заміна окремих частин: `mods`, `secrets`."""
        mods = {
            'supabase-dashboard': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'table': 'overview_projects', 'compat': 'comment-layer'}},
            'supabase-teams': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'compat': 'comment-layer'}},
            'supabase-comments': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'shots_bucket': 'overview-thumbs', 'compat': 'comment-layer'}},
            'jira-tracker': {'enabled': True, 'shared_state': True, 'settings': {'base': self.JIRA_BASE, 'email': self.JIRA_EMAIL}},
            'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas'}},
            'vercel-publish': {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}},
        }
        mods.update(over.get('mods', {}))
        for k in over.get('drop', ()):
            mods.pop(k, None)
        self.space_json({'name': 'Liga', 'modules': mods, 'migrations': over.get('migrations', {})})
        sec = {'supabase-dashboard': {'key': self.SB_KEY}, 'supabase-teams': {'key': self.SB_KEY}, 'supabase-comments': {'key': self.SB_KEY},
               'jira-tracker': {'token': self.JIRA_TOKEN}}
        sec.update(over.get('secrets', {}))
        self._write(self.secrets_path(), {'legacy': sec})
        os.chmod(self.secrets_path(), 0o600)

    def root(self, **extra):
        """Корінь `tasks.json` ЛІГИ: усі вісім ключів (`extra` — заміна/додавання; `None` — прибрати ключ)."""
        cfg = self.config(supabase=False, jira=False)
        cfg.update(supabase_url=self.SB_URL, supabase_key=self.SB_KEY, jira_base=self.JIRA_BASE, jira_email=self.JIRA_EMAIL,
                   jira_token=self.JIRA_TOKEN, gitlab_ssh_key=self.SSH, gitlab_host_ip=self.HOSTIP, preview_password=self.PW,
                   registry={'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'})     # `registry` — маркер ЛІГИ, що лишається (як на справжніх машинах)
        for k, v in extra.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        self.cfg = cfg
        self._write(self.tasks_path, cfg)
        return cfg

    def run_e(self):
        return self.lm._run(None, self.E)

    def mark(self):
        return self.read_json(self.space_path())['migrations'][self.E.mark]

    def tasks(self):
        return self.read_json(self.tasks_path)


class PlanE(_StandE):
    def test_regular_all_eight_removed_two_copied(self):
        self.root()
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')
        d = p['originals']
        self.assertEqual(sorted(d['remove']), sorted(self.ALL))
        self.assertEqual(sorted(d['copied']), ['gitlab_host_ip', 'gitlab_ssh_key', 'preview_password'])
        self.assertEqual(d['notes'], [])
        self.assertEqual(p['roles'], {})
        self.assertEqual(p['space_json']['migrations']['liga-4d4b']['roles'], [])

    def test_plan_is_pure(self):
        self.root()
        before = self.snapshot_tree()
        self.lm.plan(step=self.E)
        self.assertEqual(self.snapshot_tree(), before)

    def test_nothing_to_do_is_skip_nothing(self):
        self.root(**{k: None for k in self.ALL})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-nothing')

    def test_notes_alone_are_not_skip_nothing(self):
        self.root(**dict({k: None for k in self.ALL}, jira_base='https://example.com/x'))          # непридатна форма (шлях)
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(p['notes'], ['unfit:jira_base'])

    def test_unfit_values_stay(self):
        self.root(supabase_key='has space', jira_email='  ', gitlab_host_ip=7, preview_password=True)
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['notes']), ['unfit:gitlab_host_ip', 'unfit:jira_email', 'unfit:preview_password', 'unfit:supabase_key'])
        for k in ('supabase_key', 'jira_email', 'gitlab_host_ip', 'preview_password'):
            self.assertIn(k, d['kept'])
            self.assertNotIn(k, d['remove'])

    def test_missing_holder_keeps_key(self):
        self.rec_all(drop=('jira-tracker',))
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['jira_base', 'jira_email', 'jira_token'])
        self.assertIn('no-record:jira-tracker', d['notes'])

    def test_disabled_or_not_shared_holder_is_not_a_holder(self):
        self.rec_all(mods={'git-sync': {'enabled': False, 'shared_state': True, 'settings': {}}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['gitlab_host_ip', 'gitlab_ssh_key'])
        self.rec_all(mods={'git-sync': {'enabled': True, 'settings': {}}})
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['gitlab_host_ip', 'gitlab_ssh_key'])

    def test_supabase_pair_is_all_or_nothing(self):
        self.rec_all(drop=('supabase-teams',))
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('partial:supabase', d['notes'])
        self.assertIn('no-record:supabase-teams', d['notes'])
        self.assertEqual(sorted(k for k in d['kept'] if k.startswith('supabase')), ['supabase_key', 'supabase_url'])
        self.assertIn('jira_base', d['remove'])                      # решта оригіналів — незалежно

    def test_differs_keeps_root_and_does_not_overwrite(self):
        self.rec_all(mods={'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'ssh_key': '/other/key', 'compat': 'design-canvas'}}},
                     secrets={'jira-tracker': {'token': 'other-token'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('differs:gitlab_ssh_key', d['notes'])
        self.assertIn('differs:jira_token', d['notes'])
        self.assertIn('gitlab_ssh_key', d['kept'])
        self.assertNotIn('gitlab_ssh_key', d['remove'])
        self.assertNotIn('ssh_key', d['copy_settings'].get('git-sync', {}))
        self.assertIn('host_ip', d['copy_settings']['git-sync'])       # порожнє поле копіюється й тоді, коли сусіднє відрізняється

    def test_password_conflict_never_overwrites_the_secret(self):                    # рішення контролера 07.11.2026 замість Д4
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {})
        self.assertIn('differs:preview_password', d['notes'])
        self.assertNotIn('overwrote:password', d['notes'])
        self.assertIn('preview_password', d['kept'])
        self.assertNotIn('preview_password', d['remove'])

    def test_empty_password_secret_is_still_filled_from_the_root(self):
        self.rec_all()
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})
        self.assertIn('preview_password', d['remove'])

    def test_blank_password_secret_is_still_filled_from_the_root(self):
        self.rec_all(secrets={'vercel-publish': {'password': ''}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})

    def test_falsy_number_or_bool_password_is_unfit(self):
        for bad in (0, 0.0, False, True):
            with self.subTest(bad=bad):
                self.root(preview_password=bad)
                d = self.lm.plan(step=self.E)['originals']
                self.assertIn('unfit:preview_password', d['notes'])
                self.assertIn('preview_password', d['kept'])
                self.assertEqual(d['copy_secrets'], {})

    def test_password_needs_design_canvas_compat(self):
        self.rec_all(mods={'vercel-publish': {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'compat': ''}}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('preview_password', d['kept'])
        self.assertIn('no-record:vercel-publish', d['notes'])

    def test_numeric_password_is_stringified(self):
        self.root(preview_password=4321)
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': '4321'}})

    def test_url_normalised_before_comparison(self):
        self.root(supabase_url=' %s/ ' % self.SB_URL, supabase_key=' %s ' % self.SB_KEY)
        self.assertIn('supabase_url', self.lm.plan(step=self.E)['originals']['remove'])
        self.assertIn('supabase_key', self.lm.plan(step=self.E)['originals']['remove'])

    def test_marker_guard_keeps_one_marker_key(self):
        self.root(registry=None)                                      # маркерів, окрім `gitlab_*`, у корені нема
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('marker-kept:gitlab_host_ip', d['notes'])
        self.assertIn('gitlab_host_ip', d['kept'])
        self.assertNotIn('gitlab_host_ip', d['remove'])

    def test_marker_guard_silent_when_registry_key_present(self):
        self.root(registry={'head': 'abc'})
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['notes'], [])
        self.assertIn('gitlab_host_ip', d['remove'])

    def test_marker_guard_uses_ssh_key_when_it_is_the_only_marker(self):
        self.root(gitlab_host_ip=None, registry=None)
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('marker-kept:gitlab_ssh_key', d['notes'])

    def test_gates(self):
        self.root()
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}}})
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'skip-held')                   # held раннього кроку тримає Е
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'at': 'x'}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'held': True}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-held')

    def test_provider_unchanged_check(self):
        self.root()
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')                        # запис git-sync з новими налаштуваннями лишається тим самим постачальником

    def test_provider_change_by_the_copy_aborts(self):
        """Копія, після якої роль вирішувалася б ІНШИМ постачальником, — `abort-provider` (охоронець без цього тесту не міг би впасти)."""
        self.root()
        git_sync = self.dm.catalog()['git-sync']

        def shifting(role, space, explicit_override=None, **kw):
            if role == 'vcs' and ((explicit_override or {}).get('git-sync', {}).get('settings') or {}).get('host_ip'):
                return git_sync                                       # лише ПІСЛЯ копії `host_ip` роль «зʼявляється»
            return None
        with self.mock.patch.object(self.dm, '_provider_for', shifting):
            self.assertEqual(self.lm.plan(step=self.E)['status'], 'abort-provider')


class RunE(_StandE):
    def test_run_copies_verifies_removes_then_marks(self):
        self.root()
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        t = self.tasks()
        for k in self.ALL:
            self.assertNotIn(k, t)
        self.assertEqual(sorted(t['tasks']), ['a-1', 'a-2'])          # решта файла — як була
        self.assertIn('design_work_root', t)
        sj = self.read_json(self.space_path())
        self.assertEqual(sj['modules']['git-sync']['settings']['ssh_key'], self.SSH)
        self.assertEqual(sj['modules']['git-sync']['settings']['host_ip'], self.HOSTIP)
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish'], {'password': self.PW})
        m = self.mark()
        self.assertEqual((m['roles'], m['copied'], m['kept'], m['notes']),
                         ([], ['gitlab_host_ip', 'gitlab_ssh_key', 'preview_password'], [], []))
        self.assertEqual(sorted(m['removed']), sorted(self.ALL))
        self.assertTrue(m['backup'].endswith('-liga-4d4b'))
        self.assert_no_secrets_in_logs()

    def test_mark_is_written_last(self):
        self.root()
        order = []
        real_commit, real_space = self.lm._commit_originals, self.lm._commit_space
        self.mock.patch.object(self.lm, '_commit_originals', lambda *a, **k: order.append('root') or real_commit(*a, **k)).start()
        self.mock.patch.object(self.lm, '_commit_space', lambda *a, **k: order.append('mark') or real_space(*a, **k)).start()
        self.addCleanup(self.mock.patch.stopall)
        self.run_e()
        self.assertEqual(order, ['root', 'mark'])

    def test_backup_and_dot_bak_hold_the_bytes_before(self):
        self.root()
        before = self.read(self.tasks_path)
        _st, info = self.run_e()
        self.assertEqual(self.read(self.deai, 'backups', info['backup'], 'tasks.json'), before)
        self.assertEqual(self.read(self.tasks_path + '.bak'), before)

    def test_abort_before_backup_when_tasks_unwritable(self):
        self.root()
        before = self.snapshot_tree()
        with self.mock.patch.object(self.lm, '_records_writable', lambda p: False):
            st, _info = self.run_e()
        self.assertEqual(st, 'abort-originals')
        self.assertEqual(self.tree_without_logs(), {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k})
        self.assertEqual(self.backups(), [])

    def test_abort_before_backup_when_secrets_unwritable(self):
        self.root()
        before = self.snapshot_tree()
        with self.mock.patch.object(self.lm, '_secrets_writable', lambda: False):
            st, _info = self.run_e()
        self.assertEqual(st, 'abort-secrets')
        self.assertEqual(self.tree_without_logs(), {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k})
        self.assertEqual(self.backups(), [])

    def test_abort_before_backup_when_the_space_dir_is_read_only(self):
        if os.geteuid() == 0:
            self.skipTest('root ignores permission bits')
        self.root()
        before = self.snapshot_tree()
        os.chmod(self.space_dir, 0o555)
        self.addCleanup(os.chmod, self.space_dir, 0o755)
        st, _info = self.run_e()
        os.chmod(self.space_dir, 0o755)
        self.assertEqual(st, 'abort-write')
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.tree_without_logs(), {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k})

    def test_abort_before_backup_when_space_json_is_read_only(self):
        if os.geteuid() == 0:
            self.skipTest('root ignores permission bits')
        self.root()
        os.chmod(self.space_path(), 0o444)
        self.addCleanup(os.chmod, self.space_path(), 0o644)
        st, _info = self.run_e()
        self.assertEqual(st, 'abort-write')
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.tasks()['preview_password'], self.PW)

    def test_copies_and_backup_are_fsynced_before_the_root_is_touched(self):
        self.root()
        events = []
        real = self.lm._commit_originals
        for name, fn in (('fsync_path', lambda p: events.append(('sync', os.path.basename(p)))),
                         ('_commit_originals', lambda *a, **k: events.append(('root', '')) or real(*a, **k))):
            patcher = self.mock.patch.object(self.lm, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        at = events.index(('root', ''))
        synced = {n for kind, n in events[:at] if kind == 'sync'}
        self.assertTrue({'secrets.json', 'space.json', 'tasks.json', 'manifest.json'} <= synced, synced)

    def test_root_write_asks_for_fsync(self):
        self.root()
        seen = []
        real = self.lm.atomic_write_json
        patcher = self.mock.patch.object(self.lm, 'atomic_write_json',
                                         lambda path, data, *a, **k: seen.append((os.path.basename(path), k.get('fsync'))) or real(path, data, *a, **k))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.run_e()
        self.assertIn(('legacy-tasks.json', True), seen)

    def test_abort_verify_when_the_copy_does_not_read_back(self):
        self.root()
        real = self.dm._load_secrets
        calls = {'n': 0}

        def lying():
            calls['n'] += 1
            out = real()
            if calls['n'] >= 3:                                     # перевірка прочитанням — після плану, бекапу й запису
                out = json.loads(json.dumps(out))
                out.get('legacy', {}).pop('vercel-publish', None)
            return out
        with self.mock.patch.object(self.dm, '_load_secrets', lying):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-verify')
        self.assertEqual(self.tasks()['preview_password'], self.PW)      # нічого не видалено
        self.assertNotIn('liga-4d4b', self.read_json(self.space_path()).get('migrations', {}))

    def test_failure_before_the_root_leaves_copies_and_next_start_finishes(self):
        self.root()
        with self.mock.patch.object(self.lm, '_commit_originals', side_effect=OSError('x')):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-originals')
        self.assertIn('preview_password', self.tasks())                  # корінь цілий
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish'], {'password': self.PW})   # копії лежать
        self.assertNotIn('liga-4d4b', self.read_json(self.space_path()).get('migrations', {}))
        st, _i = self.run_e()                                          # повтор доробляє
        self.assertEqual(st, 'done')
        self.assertNotIn('preview_password', self.tasks())

    def test_failure_between_root_and_mark_is_finished_by_next_start(self):
        self.root()
        with self.mock.patch.object(self.lm, '_commit_space', side_effect=OSError('x')):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-write')
        for k in self.ALL:
            self.assertNotIn(k, self.tasks())                           # ключі вже видалені, позначки нема
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'skip-nothing')                    # нічого видаляти; позначка не пишеться (див. Поправку)

    def test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key(self):
        """Вікно між перевіркою копій і видаленням: людина міняє `ssh_key` на екрані «Підключення» ПІСЛЯ `abort-verify`-перевірки, але ДО запису кореня.
        Свіже рішення всередині `_commit_originals` бачить розбіжність і ключ лишає (інакше єдина копія була б значенням, якого людина вже не хоче)."""
        self.root()
        real = self.lm._verify_copies

        def verify_then_tamper(sid, space_path, d):
            ok = real(sid, space_path, d)
            data = self.read_json(self.space_path())
            data['modules']['git-sync']['settings']['ssh_key'] = '/changed/by/a/person'
            self._write(self.space_path(), data)
            return ok
        with self.mock.patch.object(self.lm, '_verify_copies', verify_then_tamper):
            st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertIn('gitlab_ssh_key', self.tasks())
        self.assertIn('gitlab_ssh_key', self.mark()['kept'])
        self.assertNotIn('gitlab_ssh_key', self.mark()['removed'])
        self.assertNotIn('gitlab_host_ip', self.tasks())             # решта ключів видалена, як планувалось
        self.assertEqual(self.read_json(self.space_path())['modules']['git-sync']['settings']['ssh_key'], '/changed/by/a/person')   # правку людини не перетерто

    def test_a_setting_cleared_between_copy_and_delete_keeps_the_root_value(self):
        """Людина стирає щойно скопійований `host_ip` між перевіркою й видаленням: у записі порожньо, тож корінь — ЄДИНА копія значення й лишається
        (свіже рішення бачить «порожньо й копіюємо», а не «рівність»)."""
        self.root()
        real = self.lm._verify_copies

        def verify_then_clear(sid, space_path, d):
            ok = real(sid, space_path, d)
            data = self.read_json(self.space_path())
            data['modules']['git-sync']['settings']['host_ip'] = ''
            self._write(self.space_path(), data)
            return ok
        with self.mock.patch.object(self.lm, '_verify_copies', verify_then_clear):
            st, _info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertEqual(self.tasks()['gitlab_host_ip'], self.HOSTIP)
        self.assertIn('gitlab_host_ip', self.mark()['kept'])
        self.assertNotIn('gitlab_host_ip', self.mark()['removed'])
        self.assertNotIn('gitlab_ssh_key', self.tasks())                 # решта — видалено

    def test_merge_never_overwrites_a_value_a_person_set(self):
        """Людина вписала `host_ip` між планом і записом налаштувань: злиття його не перетирає, перевірка каже `abort-verify`, корінь цілий."""
        self.root()
        real = self.lm._merge_settings

        def person_then_merge(space_path, patches):
            sj = self.read_json(self.space_path())
            sj['modules']['git-sync']['settings']['host_ip'] = '198.51.100.9'
            self._write(self.space_path(), sj)
            return real(space_path, patches)
        with self.mock.patch.object(self.lm, '_merge_settings', person_then_merge):
            st, _info = self.run_e()
        self.assertEqual(st, 'abort-verify')
        self.assertEqual(self.read_json(self.space_path())['modules']['git-sync']['settings']['host_ip'], '198.51.100.9')
        self.assertEqual(self.tasks()['gitlab_host_ip'], self.HOSTIP)

    def test_run_never_deletes_the_last_marker_key(self):
        self.root(registry=None)                                      # без `registry` єдиний маркер файла ЛІГИ — `gitlab_*`
        st, _info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertEqual(self.tasks()['gitlab_host_ip'], self.HOSTIP)
        self.assertIn('marker-kept:gitlab_host_ip', self.mark()['notes'])
        self.assertIn('gitlab_host_ip', self.mark()['kept'])
        self.assertTrue(self.spaces.has_markers(self.tasks()))

    def test_race_on_tasks_file_aborts(self):
        self.root()
        before = self.read(self.tasks_path)
        n = {'i': 0}

        def moving(p):
            n['i'] += 1
            return (n['i'], 1)
        with self.mock.patch.object(self.lm, '_file_sig', moving):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-originals')
        self.assertEqual(self.read(self.tasks_path), before)             # постійна гонка: файл не переписано

    def test_a_concurrent_edit_of_the_root_is_never_overwritten(self):
        """Інший процес дописує в `tasks.json` між читанням і записом (сервер зберігає задачі): `_file_sig` бачить зміну, ретрай читає свіже — правка вціліла."""
        self.root()
        real_sig = self.lm._file_sig
        n = {'i': 0}

        def sig_with_a_foreign_write(p):
            n['i'] += 1
            if n['i'] == 2:                                           # друга звірка першої спроби: між читанням файла й записом
                cur = self.tasks()
                cur['tasks']['a-3'] = {'dir': '/new', 'title': 'Added by another process'}
                self._write(self.tasks_path, cur)
            return real_sig(p)
        with self.mock.patch.object(self.lm, '_file_sig', sig_with_a_foreign_write):
            st, _i = self.run_e()
        self.assertEqual(st, 'done')
        self.assertIn('a-3', self.tasks()['tasks'])                      # правка іншого процесу не затерта (ретрай прочитав свіже)
        for k in self.ALL:
            self.assertNotIn(k, self.tasks())

    def test_idempotent(self):
        self.root()
        self.assertEqual(self.run_e()[0], 'done')
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')

    def test_notes_only_still_writes_mark(self):
        self.root(**dict({k: None for k in self.ALL}, jira_base='https://example.com/x'))
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertEqual(self.mark()['notes'], ['unfit:jira_base'])
        self.assertEqual(self.mark()['removed'], [])
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')

    def test_foreign_edits_to_space_json_survive(self):
        self.root()
        real = self.lm._merge_settings

        def edit_then_merge(space_path, patches):
            sj = self.read_json(self.space_path())
            sj['name'] = 'Renamed by a person'
            self._write(self.space_path(), sj)
            return real(space_path, patches)
        with self.mock.patch.object(self.lm, '_merge_settings', edit_then_merge):
            self.run_e()
        self.assertEqual(self.read_json(self.space_path())['name'], 'Renamed by a person')


if __name__ == '__main__':
    unittest.main()

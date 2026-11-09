"""Етап 4d-4b: п'ятий крок міграції ЛІГИ `liga-4d4b` — останні оригінали кореня `tasks.json` (копія в запис і видалення з кореня)."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import atomic_io  # noqa: E402
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

    def test_password_conflict_root_wins_and_names_the_key(self):                    # рішення власника 09.11.2026 (замінює рішення контролера 07.11)
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})
        self.assertIn('replaced:preview_password', d['notes'])
        self.assertNotIn('differs:preview_password', d['notes'])
        self.assertNotIn('preview_password', d['kept'])
        self.assertIn('preview_password', d['remove'])
        self.assertIn('preview_password', d['copied'])

    def test_password_conflict_keeps_other_differs_never_overwritten(self):
        """Лише `preview_password` перемагає корінь: `jira_token`/`gitlab_ssh_key` з відмінним значенням запису не перезаписуються."""
        self.rec_all(mods={'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'ssh_key': '/other/key', 'compat': 'design-canvas'}}},
                     secrets={'jira-tracker': {'token': 'other-token'}, 'vercel-publish': {'password': 'inert-old'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})
        self.assertIn('differs:jira_token', d['notes'])
        self.assertIn('differs:gitlab_ssh_key', d['notes'])
        self.assertIn('jira_token', d['kept'])
        self.assertIn('gitlab_ssh_key', d['kept'])

    def test_password_conflict_executes_replace_and_removes_root_key(self):
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        self.root()
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish']['password'], self.PW)
        self.assertNotIn('preview_password', self.tasks())
        self.assertIn('replaced:preview_password', info['notes'])
        bk = self.read_json(self.deai, 'backups', info['backup'], 'secrets.json')           # старе значення живе в датованому бекапі
        self.assertEqual(bk['legacy']['vercel-publish']['password'], 'inert-old')

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
        for name, tag, real in (('_commit_originals', 'root', real_commit), ('_commit_space', 'mark', real_space)):
            patcher = self.mock.patch.object(self.lm, name, lambda *a, _t=tag, _r=real, **k: order.append(_t) or _r(*a, **k))
            patcher.start()
            self.addCleanup(patcher.stop)                                # ⛔ не `stopall`: він зупинив би й патчі HOME/DEAI_HOME стенда
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

    def test_fsync_failure_after_rename_is_reported_not_aborted(self):
        """m2: корінь УЖЕ переписано, лише `fsync` після rename збоїв: `done` (позначка є) + прапорець у звіті й підсумку, а не `abort-originals`."""
        self.root()
        with self.mock.patch.object(atomic_io, 'fsync_path', side_effect=OSError('no fsync')):
            st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertIs(info['durability_unconfirmed'], True)
        for k in self.ALL:
            self.assertNotIn(k, self.tasks())
        self.assertEqual(self.mark()['removed'], sorted(self.ALL))
        self.assertIn('довговічність', self.lm.originals_summary(info))

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


class RestoreE(_StandE):
    """Відкат кроку Е: домердж видалених ключів у ЖИВИЙ `tasks.json` (корінь першим), потім `space.json` і секрети; LIFO на п'ять кроків."""

    def ran(self, **root):
        self.root(**root)
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        return info['backup']

    def live_edit(self, fn):
        cfg = self.tasks()
        fn(cfg)
        self._write(self.tasks_path, cfg)

    def test_restore_merges_removed_keys_back_and_keeps_live_edits(self):
        stamp = self.ran()
        before_space = self.read_json(self.deai, 'backups', stamp, 'space.json')

        def edit(cfg):
            cfg['tasks']['fresh'] = {'dir': '/x', 'title': 'created after the step'}
            cfg['preview_password'] = 'my-own-password'              # людина вписала свій ключ у корінь після кроку
        self.live_edit(edit)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        t = self.tasks()
        self.assertIn('fresh', t['tasks'])
        self.assertEqual(t['preview_password'], 'my-own-password')       # `kept-live`
        for k in self.ALL:
            if k != 'preview_password':
                self.assertEqual(t[k], self.cfg[k], k)
        self.assertEqual(info['root_restored'], sorted(k for k in self.ALL if k != 'preview_password'))
        self.assertEqual(info['kept_live'], ['preview_password'])
        self.assertIs(info['root_fallback'], False)                       # перелік ключів — з позначки `removed`
        self.assertEqual(self.read_json(self.space_path()), before_space)
        self.assertNotIn('password', self.read_json(self.secrets_path())['legacy'].get('vercel-publish', {}))

    def _ran_with_old_password(self):
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        return self.ran()

    def test_restore_puts_the_replaced_password_secret_back(self):
        """Рішення власника 09.11.2026: крок замінив `inert-old` на корінь; відкат — справжній `undo`: секрет `inert-old` і корінь `preview_password` назад."""
        stamp = self._ran_with_old_password()
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish']['password'], self.PW)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish']['password'], 'inert-old')
        self.assertEqual(self.tasks()['preview_password'], self.PW)
        self.assertEqual(info['kept_live_secrets'], [])

    def test_restore_keeps_a_password_secret_changed_by_a_person_after_the_step(self):
        """Людина змінила секрет ПІСЛЯ кроку: відкат його не затирає (`kept_live_secrets`, лише ім'я ключа); корінь усе одно повертається."""
        stamp = self._ran_with_old_password()
        sec = self.read_json(self.secrets_path())
        sec['legacy']['vercel-publish']['password'] = 'person-new'
        self._write(self.secrets_path(), sec)
        os.chmod(self.secrets_path(), 0o600)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish']['password'], 'person-new')
        self.assertEqual(self.tasks()['preview_password'], self.PW)
        self.assertEqual(info['kept_live_secrets'], ['preview_password'])
        self.assertNotIn('person-new', json.dumps(info))
        self.assertNotIn('inert-old', json.dumps(info))

    def test_restore_never_rewrites_the_whole_file(self):
        stamp = self.ran()

        def edit(cfg):
            cfg['design_work_root'] = '/changed/after/the/step'       # ключ є і в бекапі, але з іншим значенням
            cfg['live_only_key'] = {'x': 1}
            cfg['tasks']['fresh'] = {'dir': '/x'}
        self.live_edit(edit)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        t = self.tasks()
        self.assertEqual(t['design_work_root'], '/changed/after/the/step')
        self.assertEqual(t['live_only_key'], {'x': 1})
        self.assertIn('fresh', t['tasks'])
        self.assertEqual(t['gitlab_host_ip'], self.HOSTIP)

    def test_restore_with_hold_marks_only_e(self):
        stamp = self.ran()
        self.assertEqual(self.lm.restore(stamp, hold=True), 'restored')
        self.assertEqual(self.read_json(self.space_path())['migrations'], {'liga-4d4b': {'held': True}})
        self.assertEqual(self.tasks()['jira_base'], self.JIRA_BASE)
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-held')

    def test_restore_takes_the_key_list_from_the_mark(self):
        stamp = self.ran()
        sj = self.read_json(self.space_path())
        sj['migrations'][self.E.mark]['removed'] = ['jira_base']
        self._write(self.space_path(), sj)
        st, info = self.lm._restore(stamp)
        self.assertEqual((st, info['root_restored']), ('restored', ['jira_base']))
        self.assertEqual(sorted(k for k in self.ALL if k in self.tasks()), ['jira_base'])

    def test_restore_fallback_when_mark_lacks_removed(self):
        stamp = self.ran()
        sj = self.read_json(self.space_path())
        del sj['migrations'][self.E.mark]['removed']
        self._write(self.space_path(), sj)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        self.assertEqual(info['root_restored'], sorted(self.ALL))
        self.assertEqual(self.tasks()['preview_password'], self.PW)
        self.assertIs(info['root_fallback'], True)                        # m1: перелік узято з усіх `ORIGINAL_KEYS`, а не з позначки

    def test_restore_fallback_when_space_json_is_unreadable(self):
        stamp = self.ran()
        self._write(self.space_path(), '{not json')
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        self.assertEqual(info['root_restored'], sorted(self.ALL))
        self.assertIs(info['root_fallback'], True)

    def test_restore_fallback_when_the_mark_is_held(self):
        stamp = self.ran()
        sj = self.read_json(self.space_path())
        sj['migrations'][self.E.mark] = {'held': True}
        self._write(self.space_path(), sj)
        st, info = self.lm._restore(stamp)
        self.assertEqual((st, info['root_fallback']), ('restored', True))

    def pre_restore_dirs(self):
        root = os.path.join(self.deai, 'backups')
        return sorted(n for n in os.listdir(root) if n.endswith('-pre-restore') or '-pre-restore-' in n)

    def test_restore_fsync_failure_after_rename_is_reported_not_aborted(self):
        """m2: `fsync` ПІСЛЯ rename не вдався — файл уже записано: відкат не `abort-restore`, а `restored` + прапорець."""
        stamp = self.ran()
        with self.mock.patch.object(atomic_io, 'fsync_path', side_effect=OSError('no fsync')):
            st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        self.assertIs(info['root_durability_unconfirmed'], True)
        self.assertEqual(self.tasks()['jira_base'], self.JIRA_BASE)       # ключі справді повернено
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.tasks_path)) if n.endswith('.tmp')], [])

    def test_restore_aborts_when_the_live_file_keeps_changing(self):
        stamp = self.ran()
        tasks_before, space_before = self.read(self.tasks_path), self.read(self.space_path())
        n = {'i': 0}

        def moving(path):
            n['i'] += 1
            return (n['i'], 1)
        with self.mock.patch.object(self.lm, '_file_sig', moving):
            st, _info = self.lm._restore(stamp)
        self.assertEqual(st, 'abort-restore')
        self.assertEqual(self.read(self.tasks_path), tasks_before)
        self.assertEqual(self.read(self.space_path()), space_before)         # корінь першим: space.json не чіпано
        self.assertEqual(self.pre_restore_dirs(), [])                         # m4: збій до запису не лишає осиротілої запобіжної копії

    def test_restore_refuses_when_the_live_file_is_unreadable(self):
        stamp = self.ran()
        self._write(self.tasks_path, '{broken')
        space_before = self.read(self.space_path())
        st, _info = self.lm._restore(stamp)
        self.assertEqual(st, 'refuse-tasks-unreadable')
        self.assertEqual(self.read(self.tasks_path), b'{broken')
        self.assertEqual(self.read(self.space_path()), space_before)
        self.assertEqual(self.pre_restore_dirs(), [])                         # m4: відмова — нічого не записано, зокрема й `-pre-restore`

    def test_restore_with_a_missing_live_file_refuses_and_the_cli_says_to_recreate_it(self):
        """m3: ВІДСУТНІЙ живий tasks.json теж `refuse-tasks-unreadable`; підказка CLI каже створити файл."""
        stamp = self.ran()
        os.remove(self.tasks_path)
        self.assertEqual(self.lm._restore(stamp)[0], 'refuse-tasks-unreadable')
        code, out, _e = self.cli('restore', stamp)
        self.assertEqual(code, 1)
        self.assertIn('нема', out)
        self.assertIn('створіть', out)
        self.assertFalse(os.path.exists(self.tasks_path))
        self.assertEqual(self.pre_restore_dirs(), [])

    def test_lifo_five_steps(self):
        self.root()
        sid = self.lm.plan(step=self.E)['space_id']
        names = {}
        for s in self.lm.ALL_STEPS[:4]:
            names[s.mark] = self.lm._backup(self.spaces.home(), sid, self.space_dir, s)
        sj = self.read_json(self.space_path())
        sj['migrations'] = {m: {'at': '2026-11-07T00:00:00', 'backup': b} for m, b in names.items()}
        self._write(self.space_path(), sj)
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        e = info['backup']
        for m in ('liga-4d3a', 'liga-4d3b', 'liga-4d3c', 'liga-4d4a'):
            before = self.snapshot_tree()
            got, extra = self.lm._restore(names[m])
            self.assertEqual((got, extra['rollback_first']), ('refuse-later-applied', e), m)
            self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.restore(e), 'restored')
        for m in ('liga-4d3a', 'liga-4d3b', 'liga-4d3c'):
            got, extra = self.lm._restore(names[m])
            self.assertEqual((got, extra['rollback_first']), ('refuse-later-applied', names['liga-4d4a']), m)
        self.assertEqual(self.lm.restore(names['liga-4d4a']), 'restored')
        self.assertEqual(self.lm.restore(names['liga-4d3c']), 'restored')


class RolesState(_StandE):
    """`roles_state()` (§4.1): шість ролей, причина — перша застосовна, команда виправлення без шляхів і значень."""

    def by_role(self):
        return {r['role']: r for r in self.lm.roles_state()}

    def test_all_six_on_when_records_are_enabled(self):
        got = self.lm.roles_state()
        self.assertEqual([r['role'] for r in got], ['publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify'])
        self.assertTrue(all(r['on'] and r['reason'] is None and r['fix'] == '' for r in got))
        self.assertEqual(self.lm.roles_lines(got), [])

    def test_disabled_record(self):
        self.rec_all(mods={'jira-tracker': {'enabled': False, 'shared_state': True, 'settings': {'base': self.JIRA_BASE, 'email': self.JIRA_EMAIL}}})
        r = self.by_role()['tracker']
        self.assertEqual((r['on'], r['reason']), (False, 'disabled'))
        self.assertIn('«Підключення»', r['fix'])

    def test_no_record_with_skipped_code_from_the_last_report(self):
        self.rec_all(drop=('jira-tracker',), migrations={'liga-4d3a': {'at': 'x', 'roles': ['dashboard', 'notify'], 'tracks': False, 'backup': 'b'}})
        self._write(os.path.join(self.deai, 'migrations', 'last.json'),
                    {'steps': {'liga-4d3a': {'status': 'done', 'skipped': {'tracker': 'no-jira'}}}})
        r = self.by_role()['tracker']
        self.assertEqual(r['reason'], 'no-jira')
        self.assertIn('pipeline-feedback', r['fix'])                     # текст каже, що оточення й pipeline-feedback більше не читаються

    def test_applied_step_without_the_role_and_without_a_report_is_not_migrated(self):
        self.rec_all(drop=('jira-tracker',), migrations={'liga-4d3a': {'at': 'x', 'roles': ['dashboard', 'notify'], 'tracks': False, 'backup': 'b'}})
        self.assertEqual(self.by_role()['tracker']['reason'], 'not-migrated')

    def test_held_step_names_unhold(self):
        self.rec_all(drop=('jira-tracker', 'supabase-dashboard', 'supabase-teams'), migrations={'liga-4d3a': {'held': True}})
        r = self.by_role()['tracker']
        self.assertEqual(r['reason'], 'skip-held')
        self.assertIn('migrate_liga.py unhold liga-4d3a', r['fix'])

    def test_early_step_held_names_the_early_mark_for_later_owners(self):
        """`held` кроку A тримає B і C: роль `publish` (власник C) каже `skip-held` і `unhold liga-4d3a`, а не оманливе `no-record`/`run`."""
        self.rec_all(drop=('vercel-publish', 'git-sync', 'supabase-comments'), migrations={'liga-4d3a': {'held': True}})
        for role in ('publish', 'comments', 'vcs'):
            r = self.by_role()[role]
            self.assertEqual(r['reason'], 'skip-held', role)
            self.assertIn('migrate_liga.py unhold liga-4d3a', r['fix'], role)

    def test_permanent_skip_codes_come_from_the_real_plan_not_from_last_json(self):
        """I1: постійні пропуски (`_not_ready` пише їх НЕ в `last['steps']`) — реальні сценарії: тека простору в git; нечитаний старий tasks.json."""
        self.rec_all(drop=('vercel-publish',))
        os.makedirs(os.path.join(self.space_dir, '.git'))
        r = self.by_role()['publish']
        self.assertEqual(r['reason'], 'skip-path-in-git')
        self.assertIn('поза робоче дерево git', r['fix'])
        self.assertNotEqual(r['reason'], 'no-record')
        os.rmdir(os.path.join(self.space_dir, '.git'))
        self._write(self.tasks_path, '{broken')
        r = self.by_role()['publish']
        self.assertEqual(r['reason'], 'skip-tasks-unreadable')
        self.assertIn('tasks.json', r['fix'])

    def test_real_startup_with_the_space_in_git_names_the_cause_not_run(self):
        """I1: справжній старт (простір у git work tree): роль `publish` — `skip-path-in-git` з підказкою перенести теку, а не оманливий `no-record → run`."""
        self.rec_all(drop=('vercel-publish',))
        os.makedirs(os.path.join(self.space_dir, '.git'))
        _st, err = self.quiet(self.lm.startup)
        line = [ln for ln in err.splitlines() if ln.startswith('ролі ЛІГИ вимкнено: publish')]
        self.assertEqual(len(line), 1, err)
        self.assertIn('skip-path-in-git', line[0])
        self.assertNotIn('no-record', line[0])

    def test_abort_code_from_the_plan_points_to_status(self):
        self.rec_all(drop=('vercel-publish',))
        with self.mock.patch.object(self.lm, 'plan', lambda *a, **k: {'status': 'abort-write'}):
            r = self.by_role()['publish']
        self.assertEqual(r['reason'], 'abort-write')
        self.assertIn('migrate_liga.py status', r['fix'])
        self.assertIn('рядок кроку', r['fix'])

    def test_record_deleted_after_the_step_is_not_told_to_run(self):
        """I1: крок застосовано і роль у `roles` позначки, а запису нема (людина видалила): окремий код; `run` нічого б не зробив."""
        self.rec_all(drop=('jira-tracker',), migrations={'liga-4d3a': {'at': 'x', 'roles': ['dashboard', 'notify', 'tracker'], 'tracks': False, 'backup': 'b'}})
        r = self.by_role()['tracker']
        self.assertEqual(r['reason'], 'record-removed')
        self.assertIn('«Підключення»', r['fix'])
        self.assertIn('restore', r['fix'])
        self.assertNotIn('migrate_liga.py run', r['fix'])

    def test_fix_wording_for_not_migrated_vcs_and_comments(self):
        self.rec_all(drop=('git-sync', 'supabase-comments'), migrations={'liga-4d3b': {'at': 'x', 'roles': [], 'tracks': False, 'backup': 'b'}})
        for role in ('vcs', 'comments'):
            r = self.by_role()[role]
            self.assertEqual(r['reason'], 'not-migrated', role)
            self.assertIn('migrate_liga.py run', r['fix'], role)
            self.assertIn('«Підключення»', r['fix'], role)

    def test_role_served_by_another_explicit_module_is_on_with_that_module(self):
        """m5/I2: `publish` веде ІНШИЙ явний модуль (`static-publish`) — роль `on`, `served-by:<id>`, а не `no-record` з порадою `run`."""
        self.rec_all(drop=('vercel-publish',), mods={'static-publish': {'enabled': True, 'shared_state': True, 'settings': {}}})
        r = self.by_role()['publish']
        self.assertEqual((r['on'], r['module'], r['reason'], r['fix']), (True, 'static-publish', 'served-by:static-publish', ''))
        self.assertEqual(self.lm.roles_lines(self.lm.roles_state()), [])
        self.assertEqual(self.by_role()['tracker']['module'], 'jira-tracker')
        self.assertIn('publish (static-publish): так (інший модуль)', self.lm.status_text(self.lm.status()))

    def test_both_publishers_enabled_is_never_module_error(self):
        """I2: власний запис увімкнено, а роль веде інший модуль — не `module-error`: роль працює."""
        self.rec_all(mods={'static-publish': {'enabled': True, 'shared_state': True, 'settings': {}}})
        r = self.by_role()['publish']
        self.assertTrue(r['on'], r)
        self.assertNotEqual(r['reason'], 'module-error')

    def test_no_record_default_names_run(self):
        self.rec_all(drop=('supabase-comments',))
        r = self.by_role()['comments']
        self.assertEqual(r['reason'], 'no-record')
        self.assertIn('migrate_liga.py run', r['fix'])

    def test_broken_module_is_module_error(self):
        self.rec_all(mods={'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'compat': 'bogus-value'}}})
        r = self.by_role()['vcs']
        self.assertFalse(r['on'])
        self.assertIn(r['reason'], ('bad-settings', 'module-error'))

    def test_unreadable_space_json_names_every_role(self):
        self._write(self.space_path(), '{not json')
        got = self.lm.roles_state()
        self.assertEqual({r['reason'] for r in got}, {'space-json-unreadable'})
        self.assertEqual(len(got), 6)

    def test_integrations_off_is_quiet(self):
        self.registry()
        reg = self.read_json(os.path.join(self.deai, 'spaces.json'))
        reg['spaces'][0]['integrations'] = False
        self._write(os.path.join(self.deai, 'spaces.json'), reg)
        got = self.lm.roles_state()
        self.assertEqual({r['reason'] for r in got}, {'integrations-off'})
        self.assertEqual(self.lm.roles_lines(got), [])

    def test_layer_off_and_no_liga_give_nothing(self):
        self.registry(entry=False)
        self.assertEqual(self.lm.roles_state(), [])

    def test_lines_carry_no_values_or_paths(self):
        self.rec_all(drop=('jira-tracker',))
        text = '\n'.join(self.lm.roles_lines(self.lm.roles_state()))
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-record; виправити:', text)
        for bad in (self.tmp, self.SB_KEY, self.JIRA_TOKEN):
            self.assertNotIn(bad, text)

    def test_restore_tasks_unreadable_has_a_cli_hint(self):
        """Task 6 віддає `refuse-tasks-unreadable`; CLI `restore` підказує, що робити (без шляхів)."""
        self.root()
        self.run_e()
        stamp = self.mark()['backup']
        with self.mock.patch.object(self.lm, '_restore', lambda *a, **k: ('refuse-tasks-unreadable', {})):
            code, out, _e = self.cli('restore', stamp)
        self.assertEqual(code, 1)
        self.assertIn('refuse-tasks-unreadable', out)
        self.assertIn('tasks.json', out.split('refuse-tasks-unreadable', 1)[1])


class StartupE(_StandE):
    """Старт: п'ять кроків, рядки Е, рядок «єдина копія», блок вимкнених ролей; ізольований прогін блок не друкує."""

    def fresh_unmigrated_tree(self):
        """Стара установка 0.16: записів нема, корінь має оригінали; `JIRA_*` у оточенні (старт з терміналу)."""
        import shutil
        shutil.rmtree(self.space_dir)
        os.makedirs(self.space_dir)
        if os.path.exists(self.secrets_path()):
            os.remove(self.secrets_path())
        self.root()
        for k, v in (('JIRA_EMAIL', self.JIRA_EMAIL), ('JIRA_TOKEN', self.JIRA_TOKEN)):
            patcher = self.mock.patch.dict(os.environ, {k: v})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_five_steps_five_backups_one_restore_hint(self):
        self.fresh_unmigrated_tree()
        st, err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        marks = ('liga-4d3a', 'liga-4d3b', 'liga-4d3c', 'liga-4d4a', 'liga-4d4b')
        for m in marks:
            self.assertIn('%s: ' % m, err)
        self.assertEqual(len(self.backups()), 5)
        e_stamp = [b for b in self.backups() if b.endswith('-liga-4d4b')][0]
        self.assertEqual(err.count('відкат: bin/migrate_liga.py restore'), 1)
        self.assertIn('restore %s --hold' % e_stamp, err)               # підказка відкату — для найпізнішого кроку, E включно
        self.assertIn(self.lm.ORIGINALS_REMOVED_LINE, err)
        self.assertIn('скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password', err)
        self.assertIn('видалено:', err)
        self.assertNotIn('ролі ЛІГИ вимкнено', err)                       # усі шість ролей увімкнено
        for v in (self.SB_KEY, self.JIRA_TOKEN, self.PW, self.SSH, self.HOSTIP, self.tmp):
            self.assertNotIn(v, err)

    def test_off_roles_are_named_on_every_start_while_off(self):
        self.fresh_unmigrated_tree()
        for k in ('JIRA_EMAIL', 'JIRA_TOKEN'):
            patcher = self.mock.patch.dict(os.environ)
            patcher.start()
            self.addCleanup(patcher.stop)
            os.environ.pop(k)                                             # трекер не мігрує: `no-jira`
        _st, err1 = self.quiet(self.lm.startup)
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-jira; виправити:', err1)
        _st, err2 = self.quiet(self.lm.startup)                           # другий старт: кроки skip-done, але рядок лишається
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-jira', err2)
        for v in (self.SB_KEY, self.tmp):
            self.assertNotIn(v, err1 + err2)

    def test_roles_state_failure_does_not_turn_a_good_migration_into_abort_internal(self):
        """I3: `roles_state()` кинув — старт повертає СПРАВЖНІЙ статус міграції, `last.json` не отруєно `abort-internal`."""
        self.fresh_unmigrated_tree()
        with self.mock.patch.object(self.lm, 'roles_state', side_effect=RuntimeError('boom')):
            st, err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        self.assertNotIn('abort-internal', err)
        self.assertIn('RuntimeError', err)                                # один рядок із кодом, без тексту винятку
        self.assertNotIn('boom', err)
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertNotEqual(last.get('status'), 'abort-internal')

    def test_identical_permanent_skip_is_printed_once_naming_the_steps(self):
        """M1: п'ять однакових `skip-path-in-git` — один рядок статусу, решта кроків названо в одному рядку."""
        self.registry()
        self.space_json({'name': 'Liga'})
        os.makedirs(os.path.join(self.space_dir, '.git'))
        _st, err = self.quiet(self.lm.startup)
        self.assertEqual(err.count('skip-path-in-git —'), 1, err)
        same = [ln for ln in err.splitlines() if 'те саме для' in ln]
        self.assertEqual(len(same), 1, err)
        for m in ('liga-4d3b', 'liga-4d3c', 'liga-4d4a', 'liga-4d4b'):
            self.assertIn(m, same[0])
        self.assertNotIn('liga-4d3a', same[0])

    def test_second_start_of_a_fully_migrated_liga_is_silent_and_writes_nothing(self):
        """M2: усі шість ролей `on`, другий старт — stderr порожній, дерево файлів не змінилось."""
        self.fresh_unmigrated_tree()
        self.quiet(self.lm.startup)
        self.assertTrue(all(s['on'] for s in self.lm.roles_state()))
        before = self.snapshot_tree()
        st, err = self.quiet(self.lm.startup)
        self.assertEqual((st, err), ('skip-done', ''))
        self.assertEqual(self.snapshot_tree(), before)

    def test_isolated_run_prints_no_roles_block(self):
        self.fresh_unmigrated_tree()
        for k in ('JIRA_EMAIL', 'JIRA_TOKEN'):
            patcher = self.mock.patch.dict(os.environ)
            patcher.start()
            self.addCleanup(patcher.stop)
            os.environ.pop(k)
        self.quiet(self.lm.startup)
        alt = os.path.join(self.tmp, 'alt-deai')                          # ⛔ не `~/.deai` стенда: на ньому шов — `refuse-real-home` і до блоку не доходить
        os.makedirs(alt)
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path, 'DEAI_HOME': alt, 'DC_MIGRATE_LIGA': '1'}):
            off = [{'role': 'tracker', 'module': 'jira-tracker', 'on': False, 'reason': 'no-jira', 'fix': 'x'}]
            with self.mock.patch.object(self.lm, 'roles_state', lambda *a, **k: off):      # навіть коли роль «вимкнена» — ізольований прогін мовчить
                st, err = self.quiet(self.lm.startup)
        self.assertNotEqual(st, 'refuse-real-home')                       # шов відпрацював: до блоку дійшли
        self.assertNotIn('ролі ЛІГИ вимкнено', err)


class StatusAndCli(_StandE):
    def test_status_text_has_originals_and_roles_sections(self):
        self.root()
        self.run_e()
        text = self.lm.status_text(self.lm.status())
        self.assertIn('Міграція ЛІГИ (liga-4d4b)', text)
        self.assertIn('скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password', text)
        self.assertIn('видалено:', text)
        self.assertIn('Ролі ЛІГИ', text)
        self.assertIn('publish (vercel-publish): так', text)
        for v in (self.SB_KEY, self.JIRA_TOKEN, self.PW, self.SSH, self.HOSTIP):
            self.assertNotIn(v, text)

    def test_cli_dry_run_names_keys_not_values(self):
        self.root()
        code, out, _err = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4b: ready', out)
        self.assertIn('copy: gitlab_ssh_key, gitlab_host_ip, preview_password', out)
        self.assert_no_secrets(out)
        self.assertNotIn(self.SSH, out)

    def test_cli_unhold(self):
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}, 'liga-4d4b': {'at': 'x', 'backup': 'b'}}})
        code, out, _e = self.cli('unhold', 'liga-4d4a')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a unhold: unheld', out)
        self.assertNotIn('liga-4d4a', self.read_json(self.space_path())['migrations'])
        self.assertIn('liga-4d4b', self.read_json(self.space_path())['migrations'])      # чужі позначки лишились
        code, out, _e = self.cli('unhold', 'liga-4d4b')                  # застосований крок — не `held`
        self.assertEqual(code, 1)
        self.assertIn('refuse-not-held', out)
        self.assertEqual(self.cli('unhold', 'liga-nope')[0], 1)

    def test_cli_unhold_explains_every_refusal_in_one_line(self):
        """M3: кожна відмова `unhold` — рядок «що сталось»; `refuse-mark` перелічує чинні позначки."""
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'at': 'x', 'backup': 'b'}}})
        _c, out, _e = self.cli('unhold', 'liga-nope')
        self.assertIn('refuse-mark', out)
        for m in ('liga-4d3a', 'liga-4d3b', 'liga-4d3c', 'liga-4d4a', 'liga-4d4b'):
            self.assertIn(m, out)
        _c, out, _e = self.cli('unhold', 'liga-4d4b')
        self.assertIn('не утримано', out)
        for st, needle in (('abort-unhold', 'не вдалося'), ('skip-busy', 'інший процес'), ('abort-lock', 'замок')):
            with self.mock.patch.object(self.lm, 'unhold', lambda *a, _s=st, **k: _s):
                _c, out, _e = self.cli('unhold', 'liga-4d4a')
            self.assertIn('unhold: %s' % st, out)
            self.assertIn(needle, out, st)

    def test_status_names_unhold_for_a_held_step(self):
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}}})
        text = self.lm.status_text(self.lm.status())
        self.assertIn('migrate_liga.py unhold liga-4d4a', text)

    def test_unhold_checks_home_like_run(self):
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}}})
        self.assertEqual(self.lm.unhold('liga-4d4a', home=os.path.join(self.tmp, 'elsewhere')), 'abort-internal')
        self.assertEqual(self.read_json(self.space_path())['migrations'], {'liga-4d4a': {'held': True}})
        self.assertEqual(self.lm.unhold('liga-4d4a', home=self.deai), 'unheld')

    def test_unhold_lets_the_step_run_again(self):
        self.root()
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'held': True}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-held')
        self.assertEqual(self.lm.unhold('liga-4d4b'), 'unheld')
        self.assertNotEqual(self.lm.plan(step=self.E)['status'], 'skip-held')

    def test_unhold_refuses_without_liga_and_in_layer_off(self):
        self.registry(entry=False)
        self.assertEqual(self.lm.unhold('liga-4d4a'), 'refuse-no-liga')
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}):
            os.environ.pop('DEAI_HOME')
            self.assertEqual(self.lm.unhold('liga-4d4a'), 'skip-layer-off')


if __name__ == '__main__':
    unittest.main()

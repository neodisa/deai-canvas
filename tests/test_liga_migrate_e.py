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

    def test_password_conflict_is_overwritten_with_the_root(self):                    # Д4
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})
        self.assertIn('overwrote:password', d['notes'])
        self.assertIn('preview_password', d['remove'])

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


if __name__ == '__main__':
    unittest.main()

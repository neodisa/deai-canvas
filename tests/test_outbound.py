"""Вихідні дії вирішує запис ролі `vcs`, а не прапорець простору (етап 4d-4c): предикат `vcs_outbound` і його споживачі."""
import contextlib
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in ('app', 'bin'):
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
import liga_fixture as lf  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules  # noqa: E402
import spaces  # noqa: E402
import serve  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _liga(fx):
    return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True}


class VcsOutbound(unittest.TestCase):
    def test_a_migrated_liga_is_outbound(self):
        fx = lf.LigaFixture(self).env().build()
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), True)

    def test_no_record_is_closed(self):
        fx = lf.LigaFixture(self).env().build(roles=())
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_a_disabled_record_is_closed(self):
        fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'enabled': False}})
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_git_sync_without_the_liga_scheme_is_closed(self):
        fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'settings': {'compat': ''}}})
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_unreadable_space_json_is_closed(self):
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_nobody_layer_off_and_the_implicit_space_are_closed(self):
        fx = lf.LigaFixture(self).env().build()
        for sp in (None, {}, dict(spaces.IMPLICIT)):
            self.assertIs(deai_modules.vcs_outbound(sp), False, sp)
        with mock.patch.object(spaces, 'layer_on', return_value=False):
            self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_it_is_the_same_fact_as_the_client_reads(self):
        """Той самий факт, що `serve.vcs_legacy_texts` (і JS `isLegacyVcs`): рішення не розходяться."""
        for kw in ({}, {'roles': ()}, {'overrides': {'vcs': {'settings': {'compat': ''}}}}):
            fx = lf.LigaFixture(self).env().build(**kw)
            sp = _liga(fx)
            self.assertIs(deai_modules.vcs_outbound(sp),
                          serve.vcs_legacy_texts(deai_modules.provider('vcs', sp), sp), kw)

    def test_the_second_call_does_not_walk_the_catalog_again(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertIs(deai_modules.vcs_outbound(sp), True)
        with mock.patch.object(deai_modules, 'catalog', side_effect=AssertionError('каталог')):
            self.assertIs(deai_modules.vcs_outbound(sp), True)

    def test_a_provider_with_another_id_is_closed_even_with_the_compat_record(self):
        fx = lf.LigaFixture(self).env().build()
        other = deai_modules.Module('other-vcs', roles=['vcs'])
        with mock.patch.object(deai_modules, '_capabilities_full', return_value=({}, {'vcs': other})):
            self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_a_non_builtin_provider_is_closed_even_with_the_compat_record(self):
        fx = lf.LigaFixture(self).env().build()
        own = deai_modules.Module(deai_modules.VCS_MODULE, roles=['vcs'], origin='space')
        with mock.patch.object(deai_modules, '_capabilities_full', return_value=({}, {'vcs': own})):
            self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_a_failure_while_reading_is_closed_not_an_exception(self):
        fx = lf.LigaFixture(self).env().build()
        with mock.patch.object(deai_modules, '_capabilities_full', side_effect=RuntimeError('boom')):
            self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_a_compat_value_that_is_not_allowed_is_closed(self):
        fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'settings': {'compat': 'x'}}})
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)


class OutboundGates(unittest.TestCase):
    """Ворота серверу: автопуш, реєстр команди, ціль `gitlab`/`ssh`, канал коментарів. Реальний `git push` перехоплено — мережі нема."""

    def setUp(self):
        self.fx = lf.LigaFixture(self).env().build(key_file=True)
        p = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com',
                                         'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@example.com'})
        p.start()
        self.addCleanup(p.stop)
        self.n = 0

    def add_plain(self, modules=None):
        """Другий (звичайний) простір у реєстрі: `{'id': 'plain', …}`."""
        p = os.path.join(self.fx.tmp, 'plain')
        os.makedirs(p)
        with open(os.path.join(p, 'space.json'), 'w') as f:
            json.dump(dict({'name': 'Plain'}, **({'modules': modules} if modules else {})), f)
        reg_path = os.path.join(self.fx.deai, 'spaces.json')
        with open(reg_path) as f:
            reg = json.load(f)
        reg['spaces'].append({'id': 'plain', 'path': p, 'legacy': False})
        with open(reg_path, 'w') as f:
            json.dump(reg, f)
        deai_modules.reset_caches()
        return {'id': 'plain', 'path': p, 'legacy': False}

    def autocommit(self, sid):
        """`True`, коли `git_autocommit` спробував `git push`; `sid=None` — простір запиту не зафіксовано."""
        self.n += 1
        d = os.path.join(self.fx.tmp, 'work', 't%d' % self.n)
        os.makedirs(d)
        with open(os.path.join(d, 'f.txt'), 'w') as f:
            f.write('x')
        subprocess.run(['git', 'init', '-q'], cwd=d, check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', os.path.join(self.fx.tmp, 'nowhere.git')], cwd=d, check=True)
        pushes, real = [], subprocess.run

        def run(cmd, *a, **kw):
            if isinstance(cmd, (list, tuple)) and list(cmd[:2]) == ['git', 'push']:
                pushes.append(1)
                return subprocess.CompletedProcess(cmd, 0, '', '')
            return real(cmd, *a, **kw)
        ctx = spaces.request_space(sid) if sid is not None else contextlib.nullcontext()
        with ctx, mock.patch.object(subprocess, 'run', run):
            serve.git_autocommit(d, 'x')
        return bool(pushes)

    def test_liga_pushes_a_plain_git_sync_space_does_not(self):
        self.add_plain({'git-sync': {'enabled': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}'}}})
        self.assertTrue(self.autocommit('legacy'))
        self.assertFalse(self.autocommit('plain'))

    def test_an_unfixed_request_space_is_closed(self):
        """Поправка 2: незафіксований простір = неявний, `False` (раніше «інтеграції ввімкнено» й пуш)."""
        self.assertFalse(self.autocommit(None))

    def test_a_worker_thread_carries_its_space(self):
        out = []
        with spaces.request_space('legacy'):
            fn = serve._in_space(lambda: out.append(self.autocommit(None)))
        t = threading.Thread(target=fn)
        t.start()
        t.join()
        bare = threading.Thread(target=lambda: out.append(self.autocommit(None)))
        bare.start()
        bare.join()
        self.assertEqual(out, [True, False])

    def test_the_registry_is_for_a_liga_with_its_scheme_only(self):
        self.add_plain()
        with spaces.request_space('legacy'):
            self.assertTrue(serve.registry_allowed())
        with spaces.request_space('plain'):
            self.assertFalse(serve.registry_allowed())
        self.assertFalse(serve.registry_allowed())                      # не зафіксовано
        fx2 = lf.LigaFixture(self).env().build(roles=())               # немігрована ЛІГА
        with spaces.request_space('legacy'):
            self.assertFalse(serve.registry_allowed())

    def test_registry_fails_closed_when_the_space_is_unreadable(self):
        """Збій читання простору (`SpacesError`) — реєстр ЗАКРИТО: `registry_allowed()` False, `push_tasks` не викликається."""
        env = {k: v for k, v in os.environ.items() if k not in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW')}   # гвард конфігу не мусить закривати замість воріт
        fake = mock.MagicMock()
        boom = spaces.SpacesError('spaces-unreadable', 'p')
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(spaces, 'effective_space', side_effect=boom), \
                mock.patch.dict('sys.modules', {'registry': fake}):
            self.assertFalse(serve.registry_allowed())
            self.assertFalse(serve._registry_push('t1'))
            fake.push_tasks.assert_not_called()

    def test_a_non_liga_space_with_the_liga_scheme_still_has_no_registry(self):
        """Реєстр команди — лише `legacy: true`: звичайний простір зі схемою ЛІГИ (`compat`) в нього не пише, хоча `vcs_outbound` для нього True."""
        self.add_plain({'git-sync': {'enabled': True, 'settings': {'compat': 'design-canvas', 'branch': 'main', 'path': 'm/{task}'}}})
        with spaces.request_space('plain'):
            self.assertTrue(serve._vcs_outbound_here())
            self.assertFalse(serve.registry_allowed())

    def test_the_gitlab_target_and_ssh_follow_the_scheme(self):
        self.add_plain()
        task = {'gitlab': {'repo': 'g/r', 'path': 'mockup/t1', 'ssh_key': '~/.ssh/k', 'host_ip': '203.0.113.7'}}
        with spaces.request_space('legacy'):
            got = serve.vcs_target('t1', task, {})
            self.assertEqual(got['repo'], 'g/r')
            self.assertEqual(got['host_ip'], '203.0.113.7')
            self.assertEqual(serve._vcs_ssh(task['gitlab'])['host_ip'], '203.0.113.7')
        with spaces.request_space('plain'):
            self.assertIsNone(serve.vcs_target('t1', task, {}))
            self.assertEqual(serve._vcs_ssh(task['gitlab']), {})

    def test_the_task_comment_channel_follows_the_comments_provider(self):
        self.add_plain()
        with spaces.request_space('legacy'):
            self.assertEqual(serve._task_comment_channel(_liga(self.fx), {}, 't1'), 'dc/t1')
        with spaces.request_space('plain'):
            self.assertIsNone(serve._task_comment_channel({'id': 'plain', 'path': os.path.join(self.fx.tmp, 'plain'), 'legacy': False}, {}, 't1'))

    def test_state_registry_line(self):
        import state
        import registry
        self.add_plain()
        fresh = {'age_h': 1, 'state': 'fresh', 'hint': ''}
        with mock.patch.object(registry, 'staleness', return_value=fresh) as st:
            with spaces.request_space('plain'):
                self.assertEqual(state._registry_line({}), '')
                st.assert_not_called()
            with spaces.request_space('legacy'):
                self.assertIn('Реєстр', state._registry_line({}))

    def test_a_plain_space_with_a_comments_module_gets_a_channel(self):
        """Поправка 10: звичайний простір із ввімкненим модулем коментарів тепер має `comment_channel` (раніше — `None` без прапорця)."""
        sp = self.add_plain({deai_modules.COMMENTS_MODULE: {'enabled': True, 'settings': {}}})
        with spaces.request_space('plain'):
            self.assertIsInstance(deai_modules.comments_prov_cached(sp), deai_modules.Module)
            self.assertIsNotNone(serve._task_comment_channel(sp, {}, 't1'))
        with mock.patch.object(deai_modules, 'comments_prov_cached', return_value=None):
            self.assertIsNone(serve._task_comment_channel(sp, {}, 't1'))

    def test_state_registry_line_uses_the_space_fixed_by_task_anywhere(self):
        """Рядок реєстру CLI бере простір задачі, який фіксує `task_anywhere` (а не незафіксований — інакше рядок ЛІГИ зник би)."""
        self.assertIsNone(spaces.request_space_id())
        td = os.path.join(self.fx.tmp, 'work', 'cli-t1')
        os.makedirs(td)
        lf.LigaFixture(self).env().build(tasks={'t1': {'dir': td}})
        try:
            serve.task_anywhere('t1', load=serve.load_tasks)
            self.assertEqual(spaces.request_space_id(), 'legacy')
            self.assertTrue(serve.registry_allowed())
        finally:
            spaces.clear_request_space()

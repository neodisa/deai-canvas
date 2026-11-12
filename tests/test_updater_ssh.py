"""Апдейтер і локальний ssh клону (0.24.0): `core.sshCommand` з `.git/config` зберігається, `insteadOf` працює; лише викидні репо в тимчасових теках."""
import io
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import spaces_guard  # noqa: E402
import updater  # noqa: E402
from test_updater import GIT_ENV, git, make_world  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        e = mock.patch.dict(os.environ, {**GIT_ENV})
        e.start()
        self.addCleanup(e.stop)
        for k in ('GIT_SSH_COMMAND', 'GIT_SSH', 'DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DEAI_NO_UPDATE_CHECK', 'DEAI_UPDATE_REMOTE', 'DEAI_HOME',
                  'DESIGN_CANVAS_DIR', 'DEAI_CANVAS_DIR', 'LIGA_TOOLS', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS'):
            os.environ.pop(k, None)


class LocalSshCommand(Base):
    DEFAULT = 'ssh -o BatchMode=yes -o ConnectTimeout=10'

    def test_no_local_config_keeps_the_default(self):
        _, work = make_world(self.tmp)
        env = updater._git_env(cwd=work, network=True)
        self.assertEqual(env['GIT_SSH_COMMAND'], self.DEFAULT)

    # G1
    def test_local_ssh_command_is_kept_and_hardened(self):
        _, work = make_world(self.tmp)
        git(['config', '--local', 'core.sshCommand', 'ssh -i /k/id -o IdentitiesOnly=yes -o HostKeyAlias=gl.example'], work)
        env = updater._git_env(cwd=work, network=True)
        self.assertEqual(env['GIT_SSH_COMMAND'],
                         'ssh -i /k/id -o IdentitiesOnly=yes -o HostKeyAlias=gl.example -o BatchMode=yes -o ConnectTimeout=10')

    # G2
    def test_global_and_system_config_are_not_read(self):
        _, work = make_world(self.tmp)
        glob = os.path.join(self.tmp, 'global.gitconfig')
        with open(glob, 'w') as f:
            f.write('[core]\n\tsshCommand = ssh -i /evil/global\n')
        with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': glob}):
            env = updater._git_env(cwd=work, network=True)
        self.assertEqual(env['GIT_SSH_COMMAND'], self.DEFAULT)

    def test_include_in_the_local_config_is_not_followed(self):
        _, work = make_world(self.tmp)
        inc = os.path.join(self.tmp, 'inc.cfg')
        with open(inc, 'w') as f:
            f.write('[core]\n\tsshCommand = ssh -i /evil/include\n')
        git(['config', '--local', 'include.path', inc], work)
        self.assertEqual(updater._git_env(cwd=work, network=True)['GIT_SSH_COMMAND'], self.DEFAULT)

    def test_multiline_or_nul_values_are_ignored(self):
        _, work = make_world(self.tmp)
        with mock.patch.object(updater, '_communicate', return_value=(0, 'ssh -i a\nssh -i b\n', '')):
            self.assertIsNone(updater._local_ssh_command(work))
        with mock.patch.object(updater, '_communicate', return_value=(0, 'ssh\x00 -i a\n', '')):
            self.assertIsNone(updater._local_ssh_command(work))

    def test_a_non_repo_cwd_gives_no_value(self):
        plain = os.path.join(self.tmp, 'plain')
        os.makedirs(plain)
        self.assertIsNone(updater._local_ssh_command(plain))
        self.assertIsNone(updater._local_ssh_command(None))

    # G3
    def test_only_network_subcommands_read_the_local_config(self):
        _, work = make_world(self.tmp)
        git(['config', '--local', 'core.sshCommand', 'ssh -i /k'], work)
        calls = []
        real = updater._communicate

        def spy(argv, cwd, env, timeout):
            calls.append(argv)
            return real(argv, cwd, env, timeout)
        with mock.patch.object(updater, '_communicate', side_effect=spy):
            updater.run_git(['status', '--porcelain'], work, 10)
        self.assertEqual(len(calls), 1, 'status не питає core.sshCommand: %r' % calls)
        calls.clear()
        with mock.patch.object(updater, '_communicate', side_effect=spy):
            updater.run_git(['ls-remote', '--tags', '--refs', '--', work], work, 10)
        self.assertEqual(len(calls), 2, 'ls-remote спершу читає локальний ssh: %r' % calls)

    def test_subcommand_skips_dash_c_pairs(self):
        self.assertEqual(updater._subcommand(['-c', 'gc.auto=0', '-c', 'x=y', 'fetch', '--', 'u']), 'fetch')
        self.assertEqual(updater._subcommand(['--no-pager', 'ls-remote']), 'ls-remote')
        self.assertIsNone(updater._subcommand([]))

    # G4
    def test_explicit_environment_ssh_command_still_wins(self):
        _, work = make_world(self.tmp)
        git(['config', '--local', 'core.sshCommand', 'ssh -i /k'], work)
        with mock.patch.dict(os.environ, {'GIT_SSH_COMMAND': 'my-ssh'}):
            self.assertEqual(updater._git_env(cwd=work, network=True)['GIT_SSH_COMMAND'], 'my-ssh')

    # G5
    def test_insteadof_in_the_local_config_is_applied_by_git(self):
        """`url.<реальний шлях>.insteadOf = <вигадана адреса>`: ls-remote за вигаданою адресою доходить до справжнього bare-репо."""
        remote, work = make_world(self.tmp, tags=('v0.1.0', 'v0.2.0'))
        fake = 'https://mirror.example.test/o/r.git'
        git(['config', '--local', 'url.%s.insteadOf' % remote, fake], work)
        rc, out, err = updater.run_git(['ls-remote', '--tags', '--refs', '--', fake], work, 20)
        self.assertEqual(rc, 0, err)
        self.assertIn('refs/tags/v0.2.0', out)

    def test_check_uses_the_local_ssh_command_end_to_end(self):
        """Клон із origin=ssh-адресою й локальним sshCommand-обгорткою: `git` реально кличе обгортку, а та отримує `BatchMode`."""
        remote, work = make_world(self.tmp)
        wrapper = os.path.join(self.tmp, 'fake-ssh.sh')
        log = os.path.join(self.tmp, 'ssh.log')
        with open(wrapper, 'w') as f:
            f.write('#!/bin/sh\necho "$@" >> "%s"\nexit 255\n' % log)
        os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IXUSR)
        git(['remote', 'set-url', 'origin', 'git@gl.example.test:o/r.git'], work)
        git(['config', '--local', 'core.sshCommand', wrapper + ' -o IdentitiesOnly=yes'], work)
        rc, _, _ = updater.run_git(['ls-remote', '--tags', '--refs', '--', 'git@gl.example.test:o/r.git'], work, 20)
        self.assertNotEqual(rc, 0)
        with open(log) as f:
            line = f.read()
        self.assertIn('IdentitiesOnly=yes', line)
        self.assertIn('BatchMode=yes', line)
        self.assertIn('ConnectTimeout=10', line)

    # П21.1: git виконує core.sshCommand через `sh -c`, тож метасимволи в локальному значенні ламають дописані опції.
    def test_shell_metacharacters_in_the_local_value_are_rejected(self):
        _, work = make_world(self.tmp)
        bad = {
            'comment': 'ssh -i "/k/id" # коментар',
            'trailing-backslash': 'ssh -i /k/id\\',
            'unbalanced-quote': 'ssh -i "/k/id',
            'semicolon': 'ssh -i /k/id;',
            'pipe': 'ssh -i /k/id |',
            'amp': 'ssh -i /k/id &',
            'backtick': 'ssh -i `id`',
            'dollar-paren': 'ssh -i $(id)',
        }
        for name, val in bad.items():
            with self.subTest(name):
                git(['config', '--local', 'core.sshCommand', val], work)
                err = io.StringIO()
                with mock.patch('sys.stderr', err):
                    env = updater._git_env(cwd=work, network=True)
                self.assertEqual(env['GIT_SSH_COMMAND'], self.DEFAULT)
                self.assertIn('updater: ssh-command-rejected', err.getvalue())
                self.assertNotIn('/k/id', err.getvalue())

    def test_quoted_path_with_space_is_accepted(self):
        _, work = make_world(self.tmp)
        git(['config', '--local', 'core.sshCommand', 'ssh -i "/path with space/key"'], work)
        self.assertEqual(updater._git_env(cwd=work, network=True)['GIT_SSH_COMMAND'],
                         'ssh -i "/path with space/key" -o BatchMode=yes -o ConnectTimeout=10')

    def test_valid_value_with_identity_reaches_the_wrapper_with_hardening(self):
        remote, work = make_world(self.tmp)
        wrapper = os.path.join(self.tmp, 'echo-ssh.sh')
        log = os.path.join(self.tmp, 'echo.log')
        with open(wrapper, 'w') as f:
            f.write('#!/bin/sh\necho "$@" >> "%s"\nexit 255\n' % log)
        os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IXUSR)
        key = os.path.join(self.tmp, 'key')
        git(['remote', 'set-url', 'origin', 'git@gl.example.test:o/r.git'], work)
        git(['config', '--local', 'core.sshCommand', '%s -i %s -o IdentitiesOnly=yes' % (wrapper, key)], work)
        updater.run_git(['ls-remote', '--tags', '--refs', '--', 'git@gl.example.test:o/r.git'], work, 20)
        with open(log) as f:
            line = f.read()
        for part in ('-i ' + key, 'IdentitiesOnly=yes', 'BatchMode=yes', 'ConnectTimeout=10'):
            self.assertIn(part, line)

    # П21.2
    def test_subdirectory_of_a_repo_does_not_read_the_parent_config(self):
        _, work = make_world(self.tmp)
        git(['config', '--local', 'core.sshCommand', 'ssh -i /k'], work)
        sub = os.path.join(work, 'sub')
        os.makedirs(sub, exist_ok=True)
        self.assertIsNone(updater._local_ssh_command(sub))
        self.assertEqual(updater._git_env(cwd=sub, network=True)['GIT_SSH_COMMAND'], self.DEFAULT)
        self.assertEqual(updater._local_ssh_command(work), 'ssh -i /k')

    # П21.3
    def test_subcommand_skips_values_of_space_form_global_options(self):
        for opt in ('-C', '--git-dir', '--work-tree', '--namespace', '--exec-path', '--super-prefix', '--config-env'):
            with self.subTest(opt):
                self.assertEqual(updater._subcommand([opt, 'x', 'fetch']), 'fetch')
                self.assertEqual(updater._subcommand(['-c', 'a=b', opt, 'x', 'ls-remote']), 'ls-remote')

    # П21.4
    def test_inherited_git_config_environment_does_not_influence_the_result(self):
        _, work = make_world(self.tmp)
        for extra in ({'GIT_CONFIG_PARAMETERS': "'core.sshcommand'='ssh -i /evil'"},
                      {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.sshCommand', 'GIT_CONFIG_VALUE_0': 'ssh -i /evil'}):
            with self.subTest(sorted(extra)):
                with mock.patch.dict(os.environ, extra):
                    env = updater._git_env(cwd=work, network=True)
                self.assertEqual(env['GIT_SSH_COMMAND'], self.DEFAULT)
                self.assertNotIn('/evil', env['GIT_SSH_COMMAND'])
                # `git config --local` сам не читає ці змінні, тож додатково: до дочірнього `git` вони не доходять
                seen = []
                real = updater._communicate

                def spy(argv, cwd, e, timeout):
                    seen.append(e)
                    return real(argv, cwd, e, timeout)
                with mock.patch.dict(os.environ, extra), mock.patch.object(updater, '_communicate', side_effect=spy):
                    updater._local_ssh_command(work)
                self.assertTrue(seen)
                for e in seen:
                    self.assertFalse([k for k in e if k in ('GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT') or k.startswith(('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_'))])


if __name__ == '__main__':
    unittest.main()

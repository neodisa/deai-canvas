"""Ядро оновлення (0.23.0): теги, remote, перевірка, стан `update.json`, `blocked`, ізоляція. Лише викидні git-репо в тимчасових теках
(remote — шлях файлової системи): мережі нема, глобальний git-конфіг не читається."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import isolation  # noqa: E402
import spaces_guard  # noqa: E402
import updater  # noqa: E402

_REAL = None
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'}


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def git(args, cwd=None):
    p = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'init.defaultBranch=main'] + args,
                       cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout


def write_pkg(work, version):
    with open(os.path.join(work, 'package.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': 'x', 'version': version}, f)


def commit_version(work, version, tag=None):
    write_pkg(work, version)
    git(['add', '--', 'package.json'], work)
    git(['commit', '-m', 'v' + version], work)
    if tag:
        git(['tag', tag], work)


def make_world(tmp, version='0.1.0', tags=('v0.1.0',)):
    """bare-remote + клон `work` з package.json і тегами; повертає (remote, work)."""
    remote, work = os.path.join(tmp, 'remote.git'), os.path.join(tmp, 'work')
    git(['init', '--bare', '-b', 'main', remote])
    git(['clone', remote, work])
    git(['checkout', '-B', 'main'], work)
    write_pkg(work, version)
    git(['add', '--', 'package.json'], work)
    git(['commit', '-m', 'init'], work)
    for t in tags:
        git(['tag', t], work)
    git(['push', 'origin', 'main', '--tags'], work)
    return remote, work


def push_tag(work, version):
    """Новий реліз у remote (комміт + тег + push), а потім робоче дерево відкочується на попередній коміт, як у відстаючого користувача."""
    prev = git(['rev-parse', 'HEAD'], work).strip()
    commit_version(work, version, 'v' + version)
    git(['push', 'origin', 'refs/tags/v' + version], work)       # лише тег: main у remote не рухається, тож пуші не конфліктують
    git(['reset', '--hard', prev], work)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, 'home')
        e = mock.patch.dict(os.environ, {**GIT_ENV})
        e.start()
        self.addCleanup(e.stop)
        for k in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DEAI_NO_UPDATE_CHECK', 'DEAI_UPDATE_REMOTE', 'DEAI_HOME'):
            os.environ.pop(k, None)

    def upd(self, root, **kw):
        kw.setdefault('home', lambda: self.home)
        return updater.Updater(root, **kw)


class TagParsing(unittest.TestCase):
    def test_semver_tags_only(self):
        out = '\n'.join('%040d\trefs/tags/%s' % (i, t) for i, t in enumerate(
            ['v0.9.0', 'v0.10.0', 'v0.10.0-rc1', 'v1.0', 'vX.Y.Z', 'latest', 'v0.2.0.1', 'v0.10.1']))
        self.assertEqual(updater.latest_tag(out), '0.10.1')      # 10 > 9 за числами, не за рядками

    def test_none_when_no_tags(self):
        self.assertIsNone(updater.latest_tag(''))

    def test_tag_regex_blocks_option_injection(self):
        for bad in ('v1.2.3 --upload-pack=x', '-v1.2.3', 'v1.2.3\n', 'v1.2', 'xv1.2.3', 'v1.2.3x', ' v1.2.3'):
            self.assertIsNone(updater.parse_tag(bad), repr(bad))
        self.assertEqual(updater.parse_tag('v1.22.3'), (1, 22, 3))

    def test_version_tuple_numeric(self):
        self.assertGreater(updater.version_tuple('0.10.0'), updater.version_tuple('0.9.9'))
        self.assertIsNone(updater.version_tuple('unknown'))


class RemoteChoice(Base):
    def test_upstream_then_origin_then_env_override(self):
        remote, work = make_world(self.tmp)
        up = os.path.join(self.tmp, 'up.git')
        git(['init', '--bare', '-b', 'main', up])
        # без upstream — origin
        self.assertEqual(updater.remote_for(work)[1], remote)
        # upstream гілки main = інший remote
        git(['remote', 'add', 'up', up], work)
        git(['config', 'branch.main.remote', 'up'], work)
        self.assertEqual(updater.remote_for(work)[1], up)
        # перекриття змінною: імʼя remote, а потім адреса-шлях
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': 'origin'}):
            self.assertEqual(updater.remote_for(work)[1], remote)
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': '/somewhere/else.git'}):
            self.assertEqual(updater.remote_for(work)[1], '/somewhere/else.git')

    def test_missing_remote_and_bad_env(self):
        work = os.path.join(self.tmp, 'solo')
        git(['init', '-b', 'main', work])
        self.assertEqual(updater.remote_for(work)[2], 'no-remote')
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': '-oProxyCommand=x'}):
            self.assertEqual(updater.remote_for(work)[2], 'bad-remote')

    def test_bad_remote_is_refused_before_any_git_call(self):
        for r in ('-oProxyCommand=x', 'ext::sh -c id', 'file:///etc/passwd;x', '', 'https://', '--upload-pack=x', 'a b',
                  'https://host/x\nfoo', 'ssh://-oProxyCommand=x/y'):
            self.assertEqual(updater.check_remote(r), False, repr(r))
        for r in ('origin', 'up-stream.1', 'https://git.example/o/r.git', 'ssh://git@git.example/o/r.git',
                  'git@git.example:o/r.git', '/tmp/x/remote.git'):
            self.assertEqual(updater.check_remote(r), True, repr(r))
        calls = []

        def fake(args, cwd, timeout, env_extra=None):
            calls.append(args)
            return 0, '', ''
        work = os.path.join(self.tmp, 'w')
        os.makedirs(os.path.join(work, '.git'))
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': '-oProxyCommand=x'}):
            st = self.upd(work, run=fake).check()
        self.assertEqual((st['state'], st['reason']), ('error', 'bad-remote'))
        self.assertEqual(calls, [], 'git не кликано з поганим remote')

    def test_remote_host_only_never_userinfo(self):
        self.assertEqual(updater.remote_host('https://TOKEN@git.example/o/r.git'), 'git.example')
        self.assertEqual(updater.remote_host('https://user:p@ss@git.example:8443/o/r.git'), 'git.example')
        self.assertEqual(updater.remote_host('git@git.example:o/r.git'), 'git.example')
        self.assertEqual(updater.remote_host('ssh://git@git.example/o/r.git'), 'git.example')
        self.assertEqual(updater.remote_host('/tmp/x/remote.git'), 'local')
        self.assertIsNone(updater.remote_host('whatever'))


class Check(Base):
    def test_available_and_state_file_0600(self):
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        u = self.upd(work)
        self.assertFalse(u.status()['available'])
        self.assertIsNone(u.status()['state'])                    # до першої перевірки стан невідомий, не вигаданий
        u.check()
        st = u.status()
        self.assertEqual((st['current'], st['latest'], st['available'], st['state'], st['reason']), ('0.1.0', '0.2.0', True, 'ok', None))
        self.assertEqual(st['remote_host'], 'local')
        self.assertIsNone(st['blocked'])
        p = os.path.join(self.home, 'update.json')
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        for k in ('checked_at', 'latest', 'state', 'reason'):
            self.assertIn(k, data)
        self.assertEqual(data['latest'], '0.2.0')

    def test_not_available_when_equal_or_older(self):
        remote, work = make_world(self.tmp, version='0.3.0', tags=('v0.1.0', 'v0.3.0'))
        u = self.upd(work)
        u.check()
        self.assertEqual((u.status()['latest'], u.status()['available']), ('0.3.0', False))
        commit_version(work, '0.4.0')                              # локальна версія новіша за тег
        u.check()
        self.assertFalse(u.status()['available'])
        self.assertIsNone(u.status()['blocked'])

    def test_offline_keeps_previous_latest(self):
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        u = self.upd(work)
        u.check()
        shutil.rmtree(remote)
        u.check()
        st = u.status()
        self.assertEqual((st['state'], st['reason'], st['latest'], st['available']), ('offline', 'unreachable', '0.2.0', True))

    def test_timeout_is_offline_timeout(self):
        remote, work = make_world(self.tmp)
        real = updater.run_git

        def slow(args, cwd, timeout, env_extra=None):
            if args[0] == 'ls-remote':
                return 124, '', 'timeout'
            return real(args, cwd, timeout, env_extra)
        u = self.upd(work, run=slow)
        u.check()
        self.assertEqual((u.status()['state'], u.status()['reason']), ('offline', 'timeout'))

    def test_not_a_git_clone_is_no_git(self):
        root = os.path.join(self.tmp, 'plain')
        os.makedirs(root)
        write_pkg(root, '0.1.0')
        u = self.upd(root)
        u.check()
        self.assertEqual((u.status()['state'], u.status()['available']), ('no-git', False))

    def test_no_git_binary_is_no_git(self):
        root = os.path.join(self.tmp, 'w')
        os.makedirs(os.path.join(root, '.git'))
        u = self.upd(root, run=lambda a, c, t, e=None: (127, '', 'no-git-binary'))
        u.check()
        self.assertEqual(u.status()['state'], 'no-git')

    def test_status_has_no_paths_or_urls(self):
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        u = self.upd(work)
        u.check()
        body = json.dumps(u.status())
        for needle in (self.tmp, remote, work, '.git', 'remote.git'):
            self.assertNotIn(needle, body)
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            self.assertNotIn(self.tmp, f.read())

    def test_status_never_exposes_userinfo_even_from_a_tokened_remote(self):
        remote, work = make_world(self.tmp)
        git(['remote', 'set-url', 'origin', 'https://TOKEN123@git.example/o/r.git'], work)
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        u = self.upd(work)
        u.check()
        st = u.status()
        self.assertEqual((st['state'], st['remote_host']), ('disabled', 'git.example'))
        self.assertNotIn('TOKEN123', json.dumps(st))
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            self.assertNotIn('TOKEN123', f.read())

    def test_blocked_codes(self):
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        u = self.upd(work)
        u.check()
        self.assertIsNone(u.status()['blocked'])
        # untracked ігнорується
        open(os.path.join(work, 'junk.txt'), 'w').close()
        self.assertIsNone(u.status()['blocked'])
        # змінений відстежуваний файл
        with open(os.path.join(work, 'package.json'), 'a') as f:
            f.write(' ')
        self.assertEqual(u.status()['blocked'], 'dirty')
        git(['checkout', '--', 'package.json'], work)
        self.assertIsNone(u.status()['blocked'])
        # busy
        busy = self.upd(work, busy=lambda: 'shooting')
        self.assertEqual(busy.status()['blocked'], 'busy')
        # worktree
        wt = os.path.join(self.tmp, 'wt')
        git(['worktree', 'add', '-b', 'side', wt], work)
        self.assertEqual(self.upd(wt).status()['blocked'], 'worktree')
        # detached
        git(['checkout', '--detach'], work)
        self.assertEqual(u.status()['blocked'], 'detached')
        # not-git: корінь без .git, а стан із latest
        plain = os.path.join(self.tmp, 'plain')
        os.makedirs(plain)
        write_pkg(plain, '0.1.0')
        pu = self.upd(plain)
        pu._save({'latest': '0.2.0', 'state': 'ok'})
        self.assertEqual(pu.status()['blocked'], 'not-git')

    def test_blocked_not_computed_when_nothing_to_update(self):
        remote, work = make_world(self.tmp)
        calls = []
        real = updater.run_git

        def counting(args, cwd, timeout, env_extra=None):
            calls.append(args[0])
            return real(args, cwd, timeout, env_extra)
        u = self.upd(work, run=counting)
        u.check()
        calls.clear()
        self.assertFalse(u.status()['available'])
        self.assertEqual(calls, [], 'git не викликається, коли оновлення нема')
        self.assertIsNone(u.status()['blocked'])

    def test_status_uses_optional_locks_off(self):
        """Читальні виклики `git` не оновлюють індекс живого дерева (`GIT_OPTIONAL_LOCKS=0`) і не пускають `ext::`."""
        seen = []

        def fake_run(argv, **kw):
            seen.append((argv, kw['env']))
            return subprocess.CompletedProcess(argv, 0, '', '')
        with mock.patch.object(updater.subprocess, 'run', fake_run):
            updater.run_git(['status', '--porcelain'], self.tmp, 5)
        argv, env = seen[0]
        self.assertEqual(env.get('GIT_OPTIONAL_LOCKS'), '0')
        self.assertEqual(env.get('GIT_TERMINAL_PROMPT'), '0')
        self.assertEqual(argv[:3], ['git', '-c', 'protocol.ext.allow=never'])

    def test_run_git_failure_codes(self):
        with mock.patch.object(updater.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 1)):
            self.assertEqual(updater.run_git(['x'], self.tmp, 1), (124, '', 'timeout'))
        with mock.patch.object(updater.subprocess, 'run', side_effect=FileNotFoundError()):
            self.assertEqual(updater.run_git(['x'], self.tmp, 1), (127, '', 'no-git-binary'))

    def test_network_remote_refused_when_isolated_or_disabled(self):
        remote, work = make_world(self.tmp)
        git(['remote', 'set-url', 'origin', 'https://git.example/o/r.git'], work)
        for env in ({'DEAI_NO_UPDATE_CHECK': '1'}, {'DC_TASKS_FILE': '/x/tasks.json'}, {'DC_NO_OVERVIEW': '1'}):
            calls = []
            real = updater.run_git

            def counting(args, cwd, timeout, env_extra=None):
                calls.append(args[0])
                return real(args, cwd, timeout, env_extra)
            with mock.patch.dict(os.environ, env):
                u = self.upd(work, run=counting)
                st = u.check()
            self.assertEqual((st['state'], st['reason']), ('disabled', 'check-disabled'), env)
            self.assertNotIn('ls-remote', calls, env)
        # remote — ШЛЯХ: мережі нема, перевірка виконана навіть із вимкненням
        git(['remote', 'set-url', 'origin', remote], work)
        push_tag(work, '0.2.0')
        with mock.patch.dict(os.environ, {'DEAI_NO_UPDATE_CHECK': '1'}):
            st = self.upd(work).check()
        self.assertEqual((st['state'], st['latest']), ('ok', '0.2.0'))
        self.assertTrue(updater.network_allowed('/tmp/x.git'))
        self.assertTrue(updater.network_allowed('https://git.example/x'))     # оточення чисте: дозволено
        with mock.patch.dict(os.environ, {'DEAI_NO_UPDATE_CHECK': '1'}):
            self.assertFalse(updater.network_allowed('git@git.example:o/r.git'))

    def test_no_state_file_in_real_home_when_isolated(self):
        """Ізольований прогін зі «справжнім» home не пише `update.json`, стан живе в памʼяті. ⛔ «Справжній» home тут — ТИМЧАСОВА тека
        (підмінений `real_home`): мутований код не має шансу написати у справжній `~/.deai`."""
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        fake_real = os.path.join(self.tmp, 'fake-real-home')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/tasks.json'}), \
                mock.patch.object(isolation, 'real_home', lambda h: h == fake_real):
            u = updater.Updater(work, home=lambda: fake_real)
            u.check()
            self.assertEqual(u.status()['latest'], '0.2.0')       # стан живе в памʼяті процесу
            self.assertFalse(os.path.exists(fake_real), 'тека «справжнього» home не створена')
            # ізольований із іншим (тимчасовим) home — пише
            self.upd(work).check()
        self.assertTrue(os.path.isfile(os.path.join(self.home, 'update.json')))

    def test_isolated_real_home_writes_nothing_even_in_a_fake_pwd_home(self):
        """Предикат перевіряється на тимчасовому «справжньому домі» (підміна `real_home`): файл не зʼявляється, стан у памʼяті."""
        remote, work = make_world(self.tmp)
        push_tag(work, '0.2.0')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/tasks.json'}), \
                mock.patch.object(isolation, 'real_home', lambda h: True):
            u = self.upd(work)
            u.check()
            self.assertEqual(u.status()['latest'], '0.2.0')
        self.assertFalse(os.path.exists(os.path.join(self.home, 'update.json')))

    def test_boot_token_is_stable_in_process_and_random(self):
        self.assertRegex(updater.BOOT, r'^[0-9a-f]{16}$')
        remote, work = make_world(self.tmp)
        u = self.upd(work)
        self.assertEqual(u.status()['boot'], u.status()['boot'])
        self.assertEqual(u.status()['boot'], updater.BOOT)
        code = 'import sys; sys.path.insert(0, %r); import updater; print(updater.BOOT)' % os.path.join(os.path.dirname(HERE), 'app')
        other = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, env={**os.environ, 'HOME': self.tmp})
        self.assertNotEqual(other.stdout.strip(), updater.BOOT)     # новий процес — новий токен

    def test_current_version_matches_liga_migrate_tool_version(self):
        import liga_migrate
        self.assertEqual(updater.current_version(updater.PRODUCT_ROOT), liga_migrate._tool_version())
        self.assertNotEqual(updater.current_version(updater.PRODUCT_ROOT), 'unknown')
        self.assertEqual(updater.current_version(self.tmp), 'unknown')

    def test_check_never_raises(self):
        remote, work = make_world(self.tmp)

        def boom(args, cwd, timeout, env_extra=None):
            raise RuntimeError('x')
        st = self.upd(work, run=boom).check()
        self.assertEqual((st['state'], st['reason']), ('error', 'internal'))

    def test_state_file_keeps_unknown_keys(self):
        """Ключі, яких перевірка не пише (`last_update`, `notes` із наступних задач), `check()` не затирає."""
        remote, work = make_world(self.tmp)
        u = self.upd(work)
        u._save({'last_update': {'from': '0.0.9', 'to': '0.1.0', 'at': 1}, 'notes': ['x']})
        u.check()
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['last_update']['to'], '0.1.0')
        self.assertEqual(data['notes'], ['x'])


class Background(Base):
    def test_not_started_when_disabled_by_env(self):
        with mock.patch.dict(os.environ, {'DEAI_NO_UPDATE_CHECK': '1'}):
            self.assertIsNone(updater.start_background(mock.Mock()))

    def test_runs_check_then_stops(self):
        done = threading.Event()
        upd = mock.Mock()
        upd.check.side_effect = lambda: done.set()
        t = updater.start_background(upd, first_delay=0, every=3600)
        self.addCleanup(t.stop_event.set)
        self.assertTrue(t.daemon)
        self.assertTrue(done.wait(5))
        t.stop_event.set()
        t.join(5)
        self.assertFalse(t.is_alive())

    def test_stop_before_first_check_means_no_check(self):
        upd = mock.Mock()
        stop = threading.Event()
        stop.set()
        t = updater.start_background(upd, stop=stop, first_delay=60)
        t.join(5)
        upd.check.assert_not_called()


if __name__ == '__main__':
    unittest.main()

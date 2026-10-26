"""`app/modules/git-sync` (роль `vcs`, етап 4a): транспорт синку макетів із git.

Модуль вантажиться так само, як його виконує ядро: `exec` у свіжий `types.ModuleType`, без `sys.modules`. Git — СПРАВЖНІЙ,
на локальних bare-репо в тимчасовій теці (абсолютний шлях і `file://`); мережа — лише через підставний `subprocess.run`.
Кожен тест — свій `HOME` у тимчасовій теці: глобальний git-конфіг людини не читається й не пишеться.
"""
import ast
import contextlib
import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(_HERE), 'app')
SERVER = os.path.join(APP, 'modules', 'git-sync', 'server.py')


class FakeModuleError(Exception):
    def __init__(self, code, status=None, message=''):
        super().__init__(f'{code}: {message}')
        self.code, self.message = code, message


def load():
    m = types.ModuleType('deai_mod_git_sync_test')
    with open(SERVER, encoding='utf-8') as f:
        exec(compile(f.read(), SERVER, 'exec', dont_inherit=True), m.__dict__)
    return m


def _can_symlink():
    d = tempfile.mkdtemp(prefix='git-sync-sym-')
    try:
        os.symlink(d, os.path.join(d, 'l'))
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        shutil.rmtree(d, ignore_errors=True)


needs_symlink = unittest.skipUnless(_can_symlink(), 'симлінки недоступні (Windows без привілеїв)')


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


class FakeProc:
    def __init__(self, rc=0, err='', out=''):
        self.returncode, self.stderr, self.stdout = rc, err, out


class Recorder:
    """Підставний `subprocess.run`: відповіді йдуть по черзі (остання повторюється), кожен виклик запамʼятовано.
    Відповідь — `(rc, stderr[, stdout])` або виняток, який треба кинути."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        a = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(a, BaseException):
            raise a
        return FakeProc(*a)

    def argv(self, i):
        return self.calls[i][0]

    def env(self, i):
        return self.calls[i][1]['env']


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='git-sync-mod-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {'HOME': self.tmp, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@t',
               'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@t'}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('GIT_SSH_COMMAND', None)
        self.m = load()
        self.cache = os.path.join(self.tmp, 'cache')

    def ctx(self, **settings):
        return {'space': {'id': 's', 'path': self.tmp}, 'settings': settings, 'secrets': {},
                'ModuleError': FakeModuleError, 'cache_dir': self.cache}

    def bare(self, name='origin.git', seed=True):
        """Bare-репо; `seed` — з першим комітом у `main` (README) через «колегу»."""
        origin = os.path.join(self.tmp, name)
        os.makedirs(origin)
        sh(['git', 'init', '--bare', '-q', '-b', 'main', '.'], origin)
        if seed:
            self.peer = os.path.join(self.tmp, 'peer-' + name)
            sh(['git', 'clone', '-q', origin, self.peer], self.tmp)
            with open(os.path.join(self.peer, 'README.md'), 'w') as f:
                f.write('seed\n')
            sh(['git', 'add', '-A'], self.peer)
            sh(['git', 'commit', '-qm', 'seed'], self.peer)
            sh(['git', 'push', '-q', 'origin', 'HEAD:main'], self.peer)
        return origin

    def key_file(self, name='k'):
        p = os.path.join(self.tmp, name)
        with open(p, 'w') as f:
            f.write('not a real key\n')
        return p


class Validate(Base):
    """Перевірка цілі: до БУДЬ-ЯКОГО виклику git і без нього; провал — `vcs-bad-target`."""

    def target(self, repo='/abs/origin.git', **kw):
        t = {'repo': repo, 'path': 'mockup/t1', 'branch': 'main'}
        t.update(kw)
        return t

    def bad(self, t, ctx=None):
        with self.assertRaises(FakeModuleError) as cm:
            self.m.validate(ctx or self.ctx(), t)
        self.assertEqual(cm.exception.code, 'vcs-bad-target')
        return cm.exception

    def test_good_repos_are_accepted_and_normalized(self):
        for repo in ('/abs/origin.git', 'file:///abs/origin.git', 'ssh://git@h:2222/o/r.git', 'https://user@h/o/r.git',
                     'git@gitlab.internal.example:ORG/r.git', 'h:o/r.git', 'user.name-1@h-1.example_x.com:o/r.git'):
            with self.subTest(repo=repo):
                self.assertEqual(self.m.validate(self.ctx(), self.target(repo)),
                                 {'repo': repo, 'path': 'mockup/t1', 'branch': 'main', 'ssh_key': None, 'host_ip': None})

    def test_bad_repos_are_refused(self):
        for repo in ('', ' x', 'a b', 'x\n', '-oProxyCommand=x', 'ext::sh', 'fd::3', 'http://h/r.git', 'ftp://h/r',
                     'ssh://-oProxy/r', 'file://host/x', 'relative/dir', 'git@-oProxy:x', 'ssh://h:99999/r',
                     'h;id>x:o/r.git', 'u$(x)@h:o/r.git', 'h&x:o/r.git', 'h|x:o/r.git', 'h`x`:o/r.git', 'u;x@h:o/r.git',
                     'h<x:o/r.git', 'h:-x', '-u@h:o/r.git', '-o@h:p', 'ssh://-u@h/r', 'ssh://-oProxyCommand=x@h/r',
                     'https://-u@h/r', '/tmp/a b', 'h:o/a b', '/tmp/a\x00b', '/tmp/a\x7fb', '/tmp/a\x1bb', None, 123):
            with self.subTest(repo=repr(repo)):
                self.bad(self.target(repo))

    def test_a_password_in_the_address_is_refused_and_never_echoed(self):
        e = self.bad(self.target('https://u:p@h/r.git'))
        self.assertNotIn('p@', str(e))
        self.assertNotIn('u:p', str(e))
        self.assertIn('password', e.message)

    def test_target_must_be_an_object(self):
        for t in (None, 'x', ['/abs/origin.git'], 7):
            with self.subTest(t=repr(t)):
                self.bad(t)

    def test_branch_defaults_to_main_and_follows_check_ref_format(self):
        for t in (self.target(branch=None), self.target(branch=''), self.target(branch='  '), {'repo': '/o', 'path': 'p'}):
            with self.subTest(t=t):
                self.assertEqual(self.m.validate(self.ctx(), t)['branch'], 'main')
        for raw, want in ((' main ', 'main'), ('\tfeature/x\n', 'feature/x')):
            with self.subTest(trimmed=repr(raw)):
                self.assertEqual(self.m.validate(self.ctx(), self.target(branch=raw))['branch'], want)
        for b in ('main', 'feature/x', 'rel-1.2', 'a.b'):
            with self.subTest(good=b):
                self.assertEqual(self.m.validate(self.ctx(), self.target(branch=b))['branch'], b)
        for b in ('-x', 'a..b', '@{-1}', 'x.lock', '.x', 'a//b', 'a/', 'a b', 'a~1', 'a:b', '@', '/a', 'a.', 'a^b',
                  'a?b', 'a*b', 'a[b', 'a\\b', 'a\x00b', 'a\x7fb', 'a/b.lock/c', 'a/.b', 'a@{b'):
            with self.subTest(bad=repr(b)):
                self.bad(self.target(branch=b))

    def test_path_is_trimmed_of_slashes_and_must_be_a_plain_folder(self):
        self.assertEqual(self.m.validate(self.ctx(), self.target(path='mockup/t1'))['path'], 'mockup/t1')
        self.assertEqual(self.m.validate(self.ctx(), self.target(path='/mockup/t1/'))['path'], 'mockup/t1')
        for p in ('.', 'a/./b', 'a/../b', '', '/', '-x', ':/x', 'a*', 'a?', 'a[', 'a\\b', '.git', 'a/.GIT/b', 'a\x00b',
                  '.git.', 'a/.git./b', 'a/.GIT../b', 'a/.git /b', 'a/.git. ./b',
                  'a//b', '..', 'a/..', None, 5):
            with self.subTest(path=repr(p)):
                self.bad(self.target(path=p))

    def test_the_ntfs_short_name_of_dot_git_is_refused_like_dot_git(self):
        """На NTFS `.git` має коротке імʼя `GIT~1`: шлях через нього веде в `.git` так само, як `.git`."""
        for p in ('GIT~1', 'git~1/hooks', 'a/GIT~2', 'a/git~12/b', 'git~1.', 'a/GIT~1 /b', 'a/git~1. ./b'):
            with self.subTest(bad=p):
                self.bad(self.target(path=p))
        for p in ('git~x', 'agit~1', 'git~', 'git~1x', 'a/git~1a', 'git-1', 'a/b~1'):
            with self.subTest(good=p):
                self.assertEqual(self.m.validate(self.ctx(), self.target(path=p))['path'], p)

    def test_the_ntfs_short_name_is_refused_in_the_ignore_list_of_a_pull_too(self):
        with self.assertRaises(FakeModuleError) as cm:
            self.m.pull(self.ctx(), {'repo': '/abs/origin.git', 'path': 'mockup/t1'}, self.tmp + '/d',
                        {'ignore': ['GIT~1']})
        self.assertEqual(cm.exception.code, 'vcs-bad-target')

    def test_ssh_key_must_be_an_existing_file_and_tilde_is_expanded(self):
        k = self.key_file()
        self.assertEqual(self.m.validate(self.ctx(), self.target(ssh_key='~/k'))['ssh_key'], k)
        self.assertEqual(self.m.validate(self.ctx(), self.target(ssh_key=k))['ssh_key'], k)
        os.mkdir(os.path.join(self.tmp, 'dir'))
        for bad in (os.path.join(self.tmp, 'dir'), 'k', 'rel/k', os.path.join(self.tmp, 'nope')):
            with self.subTest(key=bad):
                self.bad(self.target(ssh_key=bad))

    def test_host_ip_must_be_an_ip_address(self):
        for ip in ('10.0.0.7', '::1', '2001:db8::1'):
            with self.subTest(ip=ip):
                self.assertEqual(self.m.validate(self.ctx(), self.target(host_ip=ip))['host_ip'], ip)
        for ip in ('host', '10.0.0', 'git@10.0.0.7', '-1', '10.0.0.7:22', 'fe80::1%eth0', '::1%$(id)', '::1%'):
            with self.subTest(ip=ip):
                self.bad(self.target(host_ip=ip))
        self.assertEqual(self.m.validate(self.ctx(), self.target(host_ip=' 10.0.0.7 '))['host_ip'], '10.0.0.7')

    def test_the_target_wins_over_the_settings(self):
        a, b = self.key_file('a'), self.key_file('b')
        r = self.m.validate(self.ctx(ssh_key=a, host_ip='10.0.0.1'), self.target(ssh_key=b, host_ip='10.0.0.2'))
        self.assertEqual((r['ssh_key'], r['host_ip']), (b, '10.0.0.2'))

    def test_an_empty_string_in_the_target_means_not_set(self):
        a = self.key_file('a')
        for empty in ('', '   ', None):
            with self.subTest(empty=repr(empty)):
                r = self.m.validate(self.ctx(ssh_key=a, host_ip='10.0.0.1'), self.target(ssh_key=empty, host_ip=empty))
                self.assertEqual((r['ssh_key'], r['host_ip']), (a, '10.0.0.1'))
        r = self.m.validate(self.ctx(ssh_key='', host_ip=''), self.target(ssh_key='', host_ip=''))
        self.assertEqual((r['ssh_key'], r['host_ip']), (None, None))

    def test_settings_are_checked_too(self):
        self.bad(self.target(), self.ctx(ssh_key=os.path.join(self.tmp, 'nope')))
        self.bad(self.target(), self.ctx(host_ip='not-an-ip'))

    def test_no_git_is_called(self):
        boom = Recorder(AssertionError('validate не мусить кликати git'))
        with mock.patch.object(self.m.subprocess, 'run', boom):
            self.m.validate(self.ctx(), self.target())
            self.m.mirror_dir(self.ctx(), self.target())
            self.bad(self.target('ext::sh'))
        self.assertEqual(boom.calls, [])

    def test_without_the_error_class_a_runtime_error_carries_the_code(self):
        with self.assertRaises(RuntimeError) as cm:
            self.m.validate({}, self.target('ext::sh'))
        self.assertIn('vcs-bad-target', str(cm.exception))

    def test_error_text_never_carries_a_password(self):
        e = self.m._err(self.ctx(), 'vcs-error', 'fatal: unable to access https://user:secret@h/r.git/: boom')
        self.assertNotIn('secret', e.message)
        self.assertIn('://***@h/r.git', e.message)
        r = self.m._err({}, 'vcs-error', 'https://user:secret@h/x')
        self.assertNotIn('secret', str(r))

    def test_the_whole_userinfo_is_masked_not_only_user_and_password(self):
        """Токен у позиції користувача (`https://TOKEN@host`) — той самий секрет, що й пароль."""
        for text, keep in (("fatal: unable to access 'https://TOKEN123@h/r.git/'", '://***@h/r.git/'),
                           ("fatal: unable to access 'https://user:p@ss@h/r.git/'", '://***@h/r.git/'),
                           ('fatal: unable to access https://user:secret@h/r.git/: boom', '://***@h/r.git/: boom'),
                           ('fatal: could not push ssh://TOKEN123@h:2222/o/r.git', '://***@h:2222/o/r.git')):
            with self.subTest(text=text):
                m = self.m._err(self.ctx(), 'vcs-error', text).message
                self.assertIn(keep, m)
                for leaked in ('TOKEN123', 'secret', 'p@ss', 'ss@'):
                    self.assertNotIn(leaked, m)

    def test_text_without_userinfo_is_left_alone(self):
        for text in ("fatal: repository 'https://h/o/r.git/' not found", 'git@h: Permission denied (publickey).',
                     "fatal: path 'https://h/a@b' unknown", 'ssh: connect to host h port 22: refused'):
            with self.subTest(text=text):
                self.assertEqual(self.m._err(self.ctx(), 'vcs-error', text).message, text)


    def test_error_text_is_capped(self):
        self.assertEqual(len(self.m._err(self.ctx(), 'vcs-error', 'x' * 1000).message), 300)
        self.assertEqual(len(str(self.m._err({}, 'vcs-error', 'x' * 1000))), len('vcs-error: ') + 300)


class MirrorDir(Base):
    def md(self, repo, flat=False, **kw):
        ctx = self.ctx()
        if flat:
            ctx['mirror_flat'] = True
        return self.m.mirror_dir(ctx, dict({'repo': repo, 'path': 'p', 'branch': 'main'}, **kw))

    def test_local_path_goes_under_local(self):
        self.assertEqual(self.md('/x/origin.git'), os.path.join(self.cache, 'mirrors', 'local', 'x-origin.git'))
        self.assertEqual(self.md('file:///x/origin.git'), os.path.join(self.cache, 'mirrors', 'local', 'x-origin.git'))

    def test_ssh_url_with_a_port_keeps_the_port_in_the_host(self):
        self.assertEqual(self.md('ssh://git@h:2222/o/r.git'), os.path.join(self.cache, 'mirrors', 'h-2222', 'o-r.git'))

    def test_scp_form(self):
        self.assertEqual(self.md('git@gitlab.internal.example:ORG/r.git'),
                         os.path.join(self.cache, 'mirrors', 'gitlab.internal.example', 'ORG-r.git'))
        self.assertEqual(self.md('h:o/r.git'), os.path.join(self.cache, 'mirrors', 'h', 'o-r.git'))

    def test_https_url(self):
        self.assertEqual(self.md('https://user@github.com/o/r.git'),
                         os.path.join(self.cache, 'mirrors', 'github.com', 'o-r.git'))

    def test_github_and_gitlab_with_the_same_path_do_not_mix(self):
        a, b = self.md('git@github.com:ORG/r.git'), self.md('git@gitlab.internal.example:ORG/r.git')
        self.assertNotEqual(a, b)
        self.assertNotEqual(os.path.dirname(a), os.path.dirname(b))

    def test_the_address_of_the_target_is_validated_first(self):
        with self.assertRaises(FakeModuleError) as cm:
            self.md('ext::sh')
        self.assertEqual(cm.exception.code, 'vcs-bad-target')

    def test_flat_mode_is_the_0_7_0_rule(self):
        self.assertEqual(self.md('git@h:ORG/r.git', flat=True), os.path.join(self.cache, 'ORG-r.git'))
        self.assertEqual(self.md('/x/origin.git', flat=True), os.path.join(self.cache, 'x-origin.git'))

    def test_a_slug_that_is_empty_or_dots_is_refused_and_never_leaves_the_cache(self):
        for repo in ('file:///..', 'file:///.', 'file:///', 'file:////', 'file:///-'):
            for flat in (False, True):
                with self.subTest(repo=repo, flat=flat):
                    with self.assertRaises(FakeModuleError) as cm:
                        self.md(repo, flat=flat)
                    self.assertEqual(cm.exception.code, 'vcs-bad-target')
        for repo in ('/x/..', 'git@h:../..', 'ssh://h/../x', 'file:///a/../..', '/..x', 'h:..-'):
            for flat in (False, True):
                with self.subTest(escape=repo, flat=flat):
                    try:
                        d = self.md(repo, flat=flat)
                    except FakeModuleError as e:
                        self.assertEqual(e.code, 'vcs-bad-target')
                        continue
                    self.assertEqual(os.path.commonpath([self.cache, os.path.abspath(d)]), self.cache)
                    self.assertNotEqual(os.path.abspath(d), self.cache)

    def test_without_a_cache_dir_it_is_an_error_and_nothing_is_created(self):
        ctx = self.ctx()
        del ctx['cache_dir']
        with self.assertRaises(FakeModuleError) as cm:
            self.m.mirror_dir(ctx, {'repo': '/x/o.git', 'path': 'p'})
        self.assertEqual(cm.exception.code, 'vcs-error')
        self.md('/x/o.git')
        self.assertFalse(os.path.exists(self.cache))


class Transport(Base):
    """`_Git` на підставному `subprocess.run` (мережа — лише тут і лише так)."""

    def target(self, repo='git@h:A/b.git', **kw):
        t = {'repo': repo, 'path': 'mockup/t1', 'branch': 'main', 'ssh_key': None, 'host_ip': None}
        t.update(kw)
        return t

    def go(self, rec, t, args=('push', 'origin', 'main'), cwd='/tmp', conn=None, **kw):
        with mock.patch.object(self.m.subprocess, 'run', rec):
            return self.m._Git(self.ctx(), t, connect_timeout=conn).run(list(args), cwd, **kw)

    def refuse(self, rec, t, what='fetch', conn=None):
        with mock.patch.object(self.m.subprocess, 'run', rec):
            with self.assertRaises(FakeModuleError) as cm:
                self.m._Git(self.ctx(), t, connect_timeout=conn).must(['fetch', 'origin'], '/tmp', what)
        return cm.exception

    def shell_args(self, cmd):
        """Як `sh -c` (так git виконує `GIT_SSH_COMMAND`) розбирає команду. База — `printf '%s\\n'`, тож кожен аргумент
        друкується рядком; інʼєкція в команду проявилась би зайвими файлами в `self.tmp`."""
        r = subprocess.run(cmd, shell=True, cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()

    # --- повтор через IP ---

    def test_resolver_failure_retries_once_over_the_ip(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        r = self.go(rec, self.target(host_ip='10.0.0.7'))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(rec.calls), 2, rec.calls)
        retry = rec.argv(1)
        self.assertEqual(retry[:3], ['git', '-c', 'url.git@10.0.0.7:.insteadOf=git@h:'])
        self.assertEqual(retry[3:], ['push', 'origin', 'main'])
        self.assertIn('HostKeyAlias=h', rec.env(1)['GIT_SSH_COMMAND'])
        self.assertEqual(rec.argv(0), ['git', 'push', 'origin', 'main'], 'перша спроба — без підміни адреси')
        self.assertNotIn('GIT_SSH_COMMAND', rec.env(0), 'без ключа й підміни команду ssh людини не чіпаємо')

    def test_a_second_resolver_failure_is_not_retried_again(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'))
        r = self.go(rec, self.target(host_ip='10.0.0.7'))
        self.assertEqual(r.returncode, 128)
        self.assertEqual(len(rec.calls), 2)

    def test_no_ip_means_one_attempt(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'))
        r = self.go(rec, self.target())
        self.assertEqual(r.returncode, 128)
        self.assertEqual(len(rec.calls), 1)

    def test_other_failures_are_not_retried(self):
        rec = Recorder((1, 'error: failed to push some refs'))
        self.assertEqual(self.go(rec, self.target(host_ip='10.0.0.7')).returncode, 1)
        self.assertEqual(len(rec.calls), 1)

    def test_a_success_is_not_retried(self):
        rec = Recorder((0, 'Could not resolve hostname in the output of a good run'))
        self.go(rec, self.target(host_ip='10.0.0.7'))
        self.assertEqual(len(rec.calls), 1)

    def test_the_ip_form_in_brackets_for_ipv6(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target(host_ip='::1'))
        self.assertEqual(rec.argv(1)[1:3], ['-c', 'url.git@[::1]:.insteadOf=git@h:'])

    def test_the_retry_works_for_the_scp_form_without_a_user(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target('h:o/r.git', host_ip='10.0.0.7'))
        self.assertEqual(rec.argv(1)[1:3], ['-c', 'url.10.0.0.7:.insteadOf=h:'])

    def test_the_retry_is_only_for_the_scp_form(self):
        for repo in ('ssh://git@h/o/r.git', 'https://h/o/r.git', '/abs/o.git', 'file:///abs/o.git'):
            with self.subTest(repo=repo):
                rec = Recorder((128, 'fatal: Could not resolve hostname h'))
                self.go(rec, self.target(repo, host_ip='10.0.0.7'))
                self.assertEqual(len(rec.calls), 1)

    def test_the_retry_keeps_the_key_and_the_base_command(self):
        os.environ['GIT_SSH_COMMAND'] = 'my-ssh -v'
        k = self.key_file()
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target(ssh_key=k, host_ip='10.0.0.7'))
        first, second = rec.env(0)['GIT_SSH_COMMAND'], rec.env(1)['GIT_SSH_COMMAND']
        self.assertNotIn('HostKeyAlias', first)
        self.assertTrue(second.startswith('my-ssh -v -o BatchMode=yes'), second)
        self.assertIn(f'-i {k}', second)
        self.assertTrue(second.endswith('-o HostKeyAlias=h'), second)

    @unittest.skipIf(os.name == 'nt', 'sh -c — лише POSIX')
    def test_the_host_key_alias_is_one_shell_word_even_for_a_hostile_host(self):
        """Другий рубіж: `validate` такий хост не пустить, але `_Git` не мусить на нього покладатись — git виконує
        `GIT_SSH_COMMAND` через shell."""
        os.environ['GIT_SSH_COMMAND'] = "printf '%s\\n'"
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target('git@h;>pwned:o/r.git', host_ip='10.0.0.7'))
        self.assertEqual(len(rec.calls), 2)
        self.assertEqual(self.shell_args(rec.env(1)['GIT_SSH_COMMAND'])[-2:], ['-o', 'HostKeyAlias=h;>pwned'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'pwned')), 'команда з хоста виконалась')

    # --- оточення ---

    def test_every_call_carries_the_safe_environment(self):
        os.environ['GIT_ALLOW_PROTOCOL'] = 'ext:file'
        os.environ['GIT_TERMINAL_PROMPT'] = '1'
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target(host_ip='10.0.0.7'))
        self.assertEqual(len(rec.calls), 2)
        for i in (0, 1):
            env = rec.env(i)
            self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
            self.assertEqual(env['GIT_ALLOW_PROTOCOL'], 'ssh:https:file')
            self.assertEqual(env['GIT_LITERAL_PATHSPECS'], '1')

    def test_literal_pathspecs_can_be_switched_off_for_one_call(self):
        os.environ['GIT_LITERAL_PATHSPECS'] = '1'
        rec = Recorder((0, ''))
        self.go(rec, self.target(), literal=False)
        self.assertNotIn('GIT_LITERAL_PATHSPECS', rec.env(0))

    def test_cwd_and_timeout_are_passed_on(self):
        rec = Recorder((0, ''))
        self.go(rec, self.target(), cwd='/somewhere')
        self.assertEqual(rec.calls[0][1]['cwd'], '/somewhere')
        self.assertEqual(rec.calls[0][1]['timeout'], self.m.GIT_TIMEOUT)
        self.go(rec, self.target(), timeout=7)
        self.assertEqual(rec.calls[1][1]['timeout'], 7)

    # --- GIT_SSH_COMMAND ---

    def test_without_a_key_or_an_ip_the_humans_ssh_is_left_alone(self):
        rec = Recorder((0, ''))
        self.go(rec, self.target())
        self.assertNotIn('GIT_SSH_COMMAND', rec.env(0))
        os.environ['GIT_SSH_COMMAND'] = 'ssh -F /my/config'
        self.go(rec, self.target())
        self.assertEqual(rec.env(1)['GIT_SSH_COMMAND'], 'ssh -F /my/config')

    def test_with_a_key_the_command_is_composed(self):
        k = self.key_file('my key')
        t = self.m.validate(self.ctx(), {'repo': 'git@h:o/r.git', 'path': 'p', 'ssh_key': k})
        rec = Recorder((0, ''))
        self.go(rec, t)
        self.assertEqual(rec.env(0)['GIT_SSH_COMMAND'],
                         f"ssh -o BatchMode=yes -i '{k}' -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new")

    @unittest.skipIf(os.name == 'nt', 'sh -c — лише POSIX')
    def test_the_key_is_one_shell_word_whatever_its_name(self):
        os.environ['GIT_SSH_COMMAND'] = "printf '%s\\n'"
        k = self.key_file("a b'; touch pwned; $(touch pwned2) `touch pwned3`")
        rec = Recorder((0, ''))
        self.go(rec, self.target(ssh_key=k))
        args = self.shell_args(rec.env(0)['GIT_SSH_COMMAND'])
        self.assertEqual(args[args.index('-i') + 1], k)
        self.assertEqual(args.count('-i'), 1)
        for stray in ('pwned', 'pwned2', 'pwned3'):
            self.assertFalse(os.path.exists(os.path.join(self.tmp, stray)), f'команда з імені ключа виконалась: {stray}')

    def test_the_base_command_is_the_one_from_the_environment(self):
        os.environ['GIT_SSH_COMMAND'] = 'false'
        k = self.key_file()
        rec = Recorder((0, ''))
        self.go(rec, self.target(ssh_key=k))
        self.assertTrue(rec.env(0)['GIT_SSH_COMMAND'].startswith('false '), rec.env(0)['GIT_SSH_COMMAND'])

    def test_connect_timeout_only_when_the_module_composes_the_command(self):
        rec = Recorder((0, ''))
        self.go(rec, self.target(), conn=3)
        self.assertNotIn('GIT_SSH_COMMAND', rec.env(0))
        self.go(rec, self.target(ssh_key=self.key_file()), conn=3)
        self.assertIn('-o BatchMode=yes -o ConnectTimeout=3 -i ', rec.env(1)['GIT_SSH_COMMAND'])
        self.go(rec, self.target(ssh_key=self.key_file()))
        self.assertNotIn('ConnectTimeout', rec.env(2)['GIT_SSH_COMMAND'])

    # --- класифікація ---

    def test_a_timeout_is_offline(self):
        e = self.refuse(Recorder(subprocess.TimeoutExpired('git', 5)), self.target())
        self.assertEqual(e.code, 'vcs-offline')
        self.assertIn('no answer', e.message)

    def test_a_timeout_on_the_retry_is_offline_too(self):
        e = self.refuse(Recorder((128, 'Could not resolve hostname h'), subprocess.TimeoutExpired('git', 5)),
                        self.target(host_ip='10.0.0.7'))
        self.assertEqual(e.code, 'vcs-offline')

    def test_classification_by_stderr(self):
        cases = [
            ('git@h: Permission denied (publickey).\nfatal: Could not read from remote repository.', 'vcs-auth'),
            ('Host key verification failed.\nfatal: Could not read from remote repository.', 'vcs-auth'),
            ("fatal: Authentication failed for 'https://h/r.git/'", 'vcs-auth'),
            ("fatal: could not read Username for 'https://h': terminal prompts disabled", 'vcs-auth'),
            ('ssh: Could not resolve hostname h: nodename nor servname provided', 'vcs-offline'),
            ('ssh: connect to host h port 22: Operation timed out', 'vcs-offline'),
            ('ssh: connect to host h port 22: Network is unreachable', 'vcs-offline'),
            ("fatal: Unable to create '/m/.git/index.lock': File exists.", 'vcs-busy'),
            ('Permission denied, please try again.', 'vcs-auth'),
            ('error: failed to push some refs to h', 'vcs-error'),
            ('', 'vcs-error'),
        ]
        for err, code in cases:
            with self.subTest(err=err[:40]):
                self.assertEqual(self.refuse(Recorder((128, err)), self.target()).code, code)

    def test_local_permission_errors_are_neither_auth_nor_busy(self):
        """Права на теку дзеркала — не відмова віддаленого сервера: людині не треба міняти ключ чи чекати."""
        for err in ("fatal: Unable to create '/m/.git/index.lock': Permission denied",
                    "error: cannot open '.git/FETCH_HEAD': Permission denied",
                    "fatal: Unable to create '/m/.git/index.lock': No space left on device"):
            with self.subTest(err=err[:50]):
                self.assertEqual(self.refuse(Recorder((128, err)), self.target()).code, 'vcs-error')

    def test_the_two_ssh_wordings_of_a_refused_login_are_auth(self):
        for err in ('git@h: Permission denied (publickey).', 'git@h: Permission denied (publickey,password).',
                    'Permission denied, please try again.'):
            with self.subTest(err=err):
                self.assertEqual(self.refuse(Recorder((128, err)), self.target()).code, 'vcs-auth')

    def test_a_missing_git_or_cwd_is_a_vcs_error_not_a_raw_oserror(self):
        for exc in (FileNotFoundError(2, 'No such file or directory', 'git'), NotADirectoryError(20, 'Not a directory'),
                    PermissionError(13, 'Permission denied')):
            with self.subTest(exc=type(exc).__name__):
                e = self.refuse(Recorder(exc), self.target())
                self.assertEqual(e.code, 'vcs-error')
                self.assertIn('git fetch', e.message)

    def test_output_is_decoded_as_utf8_with_replacement_whatever_the_locale_of_the_parent(self):
        """Кирилиця авторів і тек: декодування не залежить від локалі батька (Windows — cp1251/cp1252)."""
        rec = Recorder((0, ''))
        self.go(rec, self.target())
        self.assertEqual(rec.calls[0][1].get('encoding'), 'utf-8')
        self.assertEqual(rec.calls[0][1].get('errors'), 'replace')

    def test_the_locale_is_pinned_so_that_the_classification_reads_english(self):
        """Класифікація помилок і «гілки на origin нема» спираються на англійський текст git."""
        rec = Recorder((0, ''))
        with mock.patch.dict(os.environ, {'LC_ALL': 'uk_UA.UTF-8', 'LANG': 'uk_UA.UTF-8', 'LANGUAGE': 'uk'}):
            self.go(rec, self.target())
        self.assertEqual(rec.env(0)['LC_ALL'], 'C')
        self.assertNotIn('LANGUAGE', rec.env(0))

    def test_the_identity_and_repository_variables_of_the_parent_never_reach_git(self):
        """`GIT_AUTHOR_*` перекрили б `meta.author`, `GIT_DIR` і подібні відвели б git від дзеркала."""
        names = ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_AUTHOR_DATE', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL',
                 'GIT_COMMITTER_DATE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE', 'GIT_CEILING_DIRECTORIES', 'GIT_COMMON_DIR',
                 'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS', 'GIT_ICASE_PATHSPECS')
        rec = Recorder((0, ''))
        with mock.patch.dict(os.environ, {n: 'x' for n in names}):
            self.go(rec, self.target())
        for n in names:
            with self.subTest(var=n):
                self.assertNotIn(n, rec.env(0))

    def test_the_global_git_config_of_the_person_is_not_isolated(self):
        """Credential helper, `insteadOf` і налаштування ssh людини — у глобальному конфігу: модуль їх не ховає."""
        rec = Recorder((0, ''))
        with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': '/my/gitconfig', 'GIT_CONFIG_NOSYSTEM': '0'}):
            self.go(rec, self.target())
        self.assertEqual(rec.env(0)['GIT_CONFIG_GLOBAL'], '/my/gitconfig')
        self.assertEqual(rec.env(0)['GIT_CONFIG_NOSYSTEM'], '0')

    def test_the_messages_name_the_git_subcommand_not_the_leading_dash_c(self):
        """`commit` викликається як `git -c user.name=… -c user.email=… commit`: у тексті має бути `commit`, не `-c`."""
        args = ['-c', 'user.name=A', '-c', 'user.email=a@x', 'commit', '-q', '-m', 'x']
        for exc, text in ((subprocess.TimeoutExpired('git', 120), 'git commit: no answer in 120 s'),
                          (ValueError('embedded null byte'), 'git commit: embedded null byte'),
                          (FileNotFoundError(2, 'No such file or directory'), 'git commit: ')):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(self.m.subprocess, 'run', Recorder(exc)):
                    with self.assertRaises(FakeModuleError) as cm:
                        self.m._Git(self.ctx(), self.target()).run(args, '/tmp')
                self.assertTrue(cm.exception.message.startswith(text), cm.exception.message)
        with mock.patch.object(self.m.subprocess, 'run', Recorder(subprocess.TimeoutExpired('git', 5))):
            with self.assertRaises(FakeModuleError) as cm:
                self.m._Git(self.ctx(), self.target()).run(['fetch', 'origin'], '/tmp')
        self.assertTrue(cm.exception.message.startswith('git fetch: '), cm.exception.message)

    def test_a_value_error_from_the_process_call_is_a_vcs_error(self):
        """NUL в аргументі: `subprocess.run` кидає `ValueError`, а не `OSError`."""
        e = self.refuse(Recorder(ValueError('embedded null byte')), self.target())
        self.assertEqual(e.code, 'vcs-error')
        self.assertIn('git fetch', e.message)

    def test_https_refusals_of_github_and_gitlab_are_auth(self):
        for err in ("remote: Permission to o/r.git denied to user.\nfatal: unable to access 'https://github.com/o/r.git/': "
                    "The requested URL returned error: 403",
                    "fatal: unable to access 'https://h/o/r.git/': The requested URL returned error: 403",
                    'remote: Permission to o/r.git denied to deploy-key.'):
            with self.subTest(err=err[:50]):
                self.assertEqual(self.refuse(Recorder((128, err)), self.target()).code, 'vcs-auth')
        for err in ("error: cannot open '.git/FETCH_HEAD': Permission denied",
                    "fatal: unable to access 'https://h/o/r.git/': The requested URL returned error: 500"):
            with self.subTest(err=err[:50]):
                self.assertEqual(self.refuse(Recorder((128, err)), self.target()).code, 'vcs-error')

    def test_a_deadline_gives_the_retry_only_the_time_that_is_left(self):
        """Бюджет на ВСІ спроби: перша вклалась у `used`, повтор отримує решту, а не повний тайм-аут."""
        clock = [1000.0]
        seen = []

        def run(argv, **kw):
            seen.append(kw['timeout'])
            if len(seen) == 1:
                clock[0] += used
                return FakeProc(128, 'ssh: Could not resolve hostname h')
            return FakeProc(0, '')
        t = self.target(host_ip='10.0.0.7')
        for used, retried in ((0.5, True), (2.5, True), (2.9, True), (3.1, False), (3.99, False)):
            seen.clear()
            clock[0] = 1000.0
            with self.subTest(used=used):
                with mock.patch.object(self.m.subprocess, 'run', run), mock.patch.object(self.m.time, 'monotonic',
                                                                                           lambda: clock[0]):
                    r = self.m._Git(self.ctx(), t, deadline=1000.0 + 4).run(['ls-remote'], '/tmp', 4)
                self.assertEqual(len(seen), 2 if retried else 1)
                self.assertEqual(seen[0], 4, 'перша спроба — повний тайм-аут')
                if retried:
                    self.assertAlmostEqual(seen[1], 4 - used, places=6)
                    self.assertLessEqual(used + seen[1], 4 + 1e-9)
                    self.assertEqual(r.returncode, 0)
                else:
                    self.assertEqual(r.returncode, 128, 'без повтору віддаємо першу відмову')

    def test_without_a_deadline_the_retry_gets_the_full_timeout(self):
        rec = Recorder((128, 'ssh: Could not resolve hostname h'), (0, ''))
        self.go(rec, self.target(host_ip='10.0.0.7'), timeout=120)
        self.assertEqual([c[1]['timeout'] for c in rec.calls], [120, 120])

    def test_stdout_is_read_when_stderr_is_empty(self):
        self.assertEqual(self.refuse(Recorder((128, '', 'Permission denied (publickey)')), self.target()).code,
                         'vcs-auth')

    def test_the_other_failures_are_vcs_error_short_and_without_a_password(self):
        err = 'x' * 900 + " fatal: unable to access 'https://u:p@h/r.git/': boom"
        e = self.refuse(Recorder((128, err)), self.target(), what='clone')
        self.assertEqual(e.code, 'vcs-error')
        self.assertLessEqual(len(e.message), 300)
        self.assertNotIn('://u:p@', e.message)
        self.assertTrue(e.message.startswith('clone failed: '), e.message)

    def test_the_end_of_stderr_survives_the_length_limit(self):
        """Найважливіше git пише останнім рядком: обрізати треба початок, не кінець."""
        err = 'noise ' * 200 + 'fatal: THE-LAST-WORD'
        e = self.refuse(Recorder((128, err)), self.target(), what='fetch')
        self.assertLessEqual(len(e.message), 300)
        self.assertTrue(e.message.endswith('THE-LAST-WORD'), e.message)

    def test_the_hint_after_the_text_survives_the_length_limit(self):
        err = 'noise ' * 200 + 'fatal: Not possible to fast-forward, aborting.'
        g = self.m._Git(self.ctx(), self.target())
        e = g.fail('pull --ff-only', FakeProc(128, err), tail='. Підказка: відправте з іншої машини.')
        self.assertLessEqual(len(e.message), 300)
        self.assertTrue(e.message.startswith('pull --ff-only failed: '), e.message)
        self.assertTrue(e.message.endswith('. Підказка: відправте з іншої машини.'), e.message)
        self.assertIn('fast-forward', e.message)

    def test_a_password_is_masked_even_when_the_cut_falls_inside_the_address(self):
        err = "fatal: unable to access 'https://user:secret@h/r.git/'"
        g = self.m._Git(self.ctx(), self.target())
        for keep in range(1, len(err) + 1):
            with self.subTest(keep=keep):
                self.assertNotIn('secret', g.fail('fetch', FakeProc(128, err), keep=keep).message)


class RealGit(Base):
    """Те саме оточення на справжньому git і локальних bare-репо: захисні змінні не мусять ламати штатні адреси."""

    def git(self):
        return self.m._Git(self.ctx(), {'repo': '/x', 'path': 'p', 'branch': 'main', 'ssh_key': None, 'host_ip': None})

    def test_clone_by_absolute_path_and_by_file_url(self):
        origin = self.bare()
        for i, url in enumerate((origin, 'file://' + origin)):
            with self.subTest(url=url):
                dest = os.path.join(self.tmp, f'clone{i}')
                self.git().must(['clone', '--quiet', '--', url, dest], self.tmp, 'clone')
                with open(os.path.join(dest, 'README.md')) as f:
                    self.assertEqual(f.read(), 'seed\n')

    def test_ls_remote_sees_the_branch(self):
        out = self.git().must(['ls-remote', '--', self.bare()], self.tmp, 'ls-remote').stdout
        self.assertIn('refs/heads/main', out)

    def test_non_utf8_stderr_does_not_raise(self):
        """git повторює в stderr байти з імені шляху: не-UTF-8 не мусить давати `UnicodeDecodeError`."""
        bad = os.path.join(self.tmp, 'no-such-\udcff.git')
        with self.assertRaises(FakeModuleError) as cm:
            self.git().must(['clone', '--', bad, os.path.join(self.tmp, 'd')], self.tmp, 'clone')
        self.assertEqual(cm.exception.code, 'vcs-error')

    def test_no_git_in_path_is_a_vcs_error(self):
        with mock.patch.dict(os.environ, {'PATH': os.path.join(self.tmp, 'empty')}):
            with self.assertRaises(FakeModuleError) as cm:
                self.git().run(['--version'], self.tmp)
        self.assertEqual(cm.exception.code, 'vcs-error')
        self.assertIn('git --version', cm.exception.message)

    def test_a_vanished_cwd_is_a_vcs_error(self):
        with self.assertRaises(FakeModuleError) as cm:
            self.git().run(['status'], os.path.join(self.tmp, 'gone'))
        self.assertEqual(cm.exception.code, 'vcs-error')

    def test_a_missing_repo_is_a_vcs_error_with_the_what_prefix(self):
        with self.assertRaises(FakeModuleError) as cm:
            self.git().must(['clone', '--', os.path.join(self.tmp, 'nope.git'), os.path.join(self.tmp, 'd')],
                            self.tmp, 'clone')
        self.assertEqual(cm.exception.code, 'vcs-error')
        self.assertTrue(cm.exception.message.startswith('clone failed: '), cm.exception.message)


class Check(Base):
    """`check` для «Підключення»: каркас чекає 5 с, тож git має межу 4 с; відмови — словник, не виняток."""

    def go(self, **settings):
        return self.m.check(self.ctx(**settings))

    def test_without_a_repo_it_is_ok_and_git_is_not_called(self):
        boom = Recorder(AssertionError('check без repo не кличе git'))
        with mock.patch.object(self.m.subprocess, 'run', boom):
            for settings in ({}, {'repo': ''}, {'repo': '   '}, {'repo': None}):
                with self.subTest(settings=settings):
                    r = self.go(**settings)
                    self.assertEqual(r['ok'], True)
                    self.assertIn('per task', r['detail'])
        self.assertEqual(boom.calls, [])

    def test_a_local_repo_with_the_branch_is_found(self):
        self.assertEqual(self.go(repo=self.bare()), {'ok': True, 'detail': 'branch main found'})

    def test_a_branch_that_only_ends_with_the_name_is_not_found(self):
        """`ls-remote` зіставляє шаблон із хвостом імені: без `refs/heads/` `feature/other` дав би «other found»."""
        origin = self.bare()
        sh(['git', 'push', '-q', 'origin', 'HEAD:refs/heads/feature/other'], self.peer)
        self.assertIn('not on the remote yet', self.go(repo=origin, branch='other')['detail'])
        self.assertEqual(self.go(repo=origin, branch='feature/other')['detail'], 'branch feature/other found')

    def test_the_branch_comes_from_the_settings(self):
        origin = self.bare()
        sh(['git', 'push', '-q', 'origin', 'HEAD:other'], self.peer)
        self.assertEqual(self.go(repo=origin, branch='other')['detail'], 'branch other found')
        self.assertIn('not on the remote yet', self.go(repo=origin, branch='nope')['detail'])

    def test_an_empty_repo_is_ok_and_says_the_first_send_creates_the_branch(self):
        r = self.go(repo=self.bare(seed=False))
        self.assertTrue(r['ok'])
        self.assertIn('not on the remote yet', r['detail'])

    def test_a_bad_target_is_refused_without_git(self):
        boom = Recorder(AssertionError('погана ціль — до git не доходить'))
        bad = [{'repo': 'ext::sh'}, {'repo': '/abs/o.git', 'branch': '-x'}, {'repo': '/abs/o.git', 'path': '../x'},
               {'repo': '/abs/o.git', 'ssh_key': os.path.join(self.tmp, 'nope')}, {'repo': '/abs/o.git', 'host_ip': 'h'}]
        with mock.patch.object(self.m.subprocess, 'run', boom):
            for settings in bad:
                with self.subTest(settings=settings):
                    r = self.go(**settings)
                    self.assertEqual((r['ok'], r['error']), (False, 'vcs-bad-target'))
                    self.assertTrue(r['detail'])
        self.assertEqual(boom.calls, [])

    def test_a_timeout_is_offline(self):
        with mock.patch.object(self.m.subprocess, 'run', Recorder(subprocess.TimeoutExpired('git', 4))):
            r = self.go(repo='/abs/o.git')
        self.assertEqual((r['ok'], r['error']), (False, 'vcs-offline'))
        self.assertIn('no answer', r['detail'])

    def test_git_gets_a_four_second_limit_and_a_literal_address(self):
        rec = Recorder((0, '', 'abc\trefs/heads/main\n'))
        with mock.patch.object(self.m.subprocess, 'run', rec):
            r = self.go(repo='/abs/o.git')
        self.assertTrue(r['ok'])
        self.assertEqual(rec.calls[0][1]['timeout'], 4)
        self.assertEqual(rec.argv(0), ['git', 'ls-remote', '--heads', '--', '/abs/o.git', 'refs/heads/main'])

    def test_the_ssh_connect_timeout_is_set_when_the_module_composes_the_command(self):
        rec = Recorder((0, '', 'abc\trefs/heads/main\n'))
        with mock.patch.object(self.m.subprocess, 'run', rec):
            self.go(repo='git@h:o/r.git', ssh_key=self.key_file())
            self.go(repo='git@h:o/r.git')
        self.assertIn('-o ConnectTimeout=3', rec.env(0)['GIT_SSH_COMMAND'])
        self.assertNotIn('GIT_SSH_COMMAND', rec.env(1), 'без ключа ssh людини не чіпаємо')

    def test_a_missing_git_is_a_vcs_error_not_offline(self):
        origin = self.bare()
        with mock.patch.dict(os.environ, {'PATH': os.path.join(self.tmp, 'empty')}):
            r = self.go(repo=origin)
        self.assertEqual((r['ok'], r['error']), (False, 'vcs-error'))
        with mock.patch.object(self.m.subprocess, 'run', Recorder(FileNotFoundError(2, 'No such file', 'git'))):
            self.assertEqual(self.go(repo='/abs/o.git')['error'], 'vcs-error')

    def test_all_attempts_share_one_four_second_budget(self):
        """Каркас чекає `check` 5 с: першу спробу з'їло `used`, повтор через IP не може дістати більше решти."""
        clock = [500.0]
        seen = []

        def run(argv, **kw):
            seen.append(kw['timeout'])
            if len(seen) == 1:
                clock[0] += used
                return FakeProc(128, 'ssh: Could not resolve hostname h')
            clock[0] += kw['timeout']
            return FakeProc(128, 'ssh: Could not resolve hostname h')
        for used in (0.4, 1.5, 3.2, 3.9):
            seen.clear()
            clock[0] = 500.0
            with self.subTest(used=used):
                with mock.patch.object(self.m.subprocess, 'run', run), mock.patch.object(self.m.time, 'monotonic',
                                                                                           lambda: clock[0]):
                    r = self.go(repo='git@h:o/r.git', host_ip='10.0.0.7')
                self.assertLessEqual(clock[0] - 500.0, 4 + 1e-9, f'check не вклався в 4 с: {seen}')
                self.assertEqual((r['ok'], r['error']), (False, 'vcs-offline'))
                self.assertEqual(len(seen), 2 if 4 - used >= 1 else 1)

    def test_failures_come_back_as_a_dict_with_the_code(self):
        cases = [((128, 'git@h: Permission denied (publickey).'), 'vcs-auth'),
                 ((128, 'ssh: Could not resolve hostname h'), 'vcs-offline'),
                 ((128, 'fatal: something else'), 'vcs-error')]
        for answer, code in cases:
            with self.subTest(code=code):
                with mock.patch.object(self.m.subprocess, 'run', Recorder(answer)):
                    r = self.go(repo='git@h:o/r.git')
                self.assertEqual((r['ok'], r['error']), (False, code))
                self.assertTrue(r['detail'].startswith('ls-remote failed: '), r['detail'])

    def test_a_missing_local_repo_is_a_vcs_error(self):
        r = self.go(repo=os.path.join(self.tmp, 'nope.git'))
        self.assertEqual((r['ok'], r['error']), (False, 'vcs-error'))

    def test_the_default_path_does_not_break_the_check(self):
        self.assertTrue(self.go(repo=self.bare(), path='')['ok'])
        self.assertTrue(self.go(repo=self.bare('o2.git'), path='mockup/{task}')['ok'])


def fake_run(sub, answer, before=None):
    """Підставний `subprocess.run`: підкоманда git `sub` (після можливих `-c …`) отримує `answer` — виняток кидається,
    кортеж `(rc, stderr[, stdout])` повертається; `before(argv)` — побічна дія перед відповіддю. Решта — справжній git."""
    real = subprocess.run

    def run(argv, **kw):
        i = 1
        while argv[i] == '-c':
            i += 2
        if argv[i] != sub:
            return real(argv, **kw)
        if before:
            before(argv)
        if isinstance(answer, BaseException):
            raise answer
        return FakeProc(*answer)
    return run


def cut_inside_a_token(n, token='ghp_SECRETTOKEN1234567890'):
    """Текст, останні `n` символів якого починаються посеред токена в userinfo: наївне «обрізати, потім маскувати»
    лишило б його хвіст (різ ховає `://`). Повертає (текст, хвіст токена, що не мусить дожити до відповіді)."""
    tail = token[8:] + '@h.example/o/r.git/'
    return 'x' * 50 + 'https://' + token[:8] + tail + 'y' * (n - len(tail)), token[8:]


class Repo(Base):
    """Спільне для status/push/pull: справжній git на локальних bare-репо. Оточення процесу тут НЕ чиститься: `Base` ставить
    `GIT_AUTHOR_*`/`GIT_COMMITTER_*` = «T», і особистість коміту модуля (`meta.author`) мусить пережити це сама —
    модуль знімає ці змінні в `_Git._env`. Помічники «колеги» й дзеркала ставлять свою особистість явно."""
    META = {'message': 'deai: sync mockup/t1 (Т) · it1\n\nтіло', 'author': {'name': 'Анна', 'email': 'a@x'}}
    PERMISSION = 'git@h: Permission denied (publickey).\nfatal: Could not read from remote repository.'

    def target(self, origin, **kw):
        t = {'repo': origin, 'path': 'mockup/t1', 'branch': 'main'}
        t.update(kw)
        return t

    def mirror(self, origin, **kw):
        return self.m.mirror_dir(self.ctx(), self.target(origin, **kw))

    def git(self, cwd, *args, who='Колега', when=None):
        env = dict(os.environ, GIT_AUTHOR_NAME=who, GIT_AUTHOR_EMAIL='c@x', GIT_COMMITTER_NAME=who,
                   GIT_COMMITTER_EMAIL='c@x')
        if when is not None:
            env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = f'{when} +0000'
        r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, encoding='utf-8', env=env)
        self.assertEqual(r.returncode, 0, f'git {" ".join(args)}: {r.stderr}')
        return r.stdout

    def peer_commit(self, files=None, msg='peer', who='Колега', when=None, links=None, branch='main'):
        """Коміт «колеги» поверх актуального origin: `files` — {шлях: текст}, `links` — {шлях: ціль симлінка}."""
        self.git(self.peer, 'fetch', '-q', 'origin')
        self.git(self.peer, 'reset', '-q', '--hard', f'origin/{branch}')
        for rel, text in (files or {}).items():
            p = os.path.join(self.peer, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        for rel, to in (links or {}).items():
            p = os.path.join(self.peer, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            os.symlink(to, p)
        self.git(self.peer, 'add', '-A')
        self.git(self.peer, 'commit', '-qm', msg, who=who, when=when)
        self.git(self.peer, 'push', '-q', 'origin', f'HEAD:{branch}')

    def peer_branch(self, branch, files, msg='branch work', when=None):
        """Нова гілка `branch` на origin від `main` з одним комітом «колеги»."""
        self.git(self.peer, 'fetch', '-q', 'origin')
        self.git(self.peer, 'checkout', '-q', '-B', branch, 'origin/main')
        for rel, text in files.items():
            p = os.path.join(self.peer, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        self.git(self.peer, 'add', '-A')
        self.git(self.peer, 'commit', '-qm', msg, when=when)
        self.git(self.peer, 'push', '-q', 'origin', branch)

    def peer_commit_by_nobody(self, files, subject):
        """Коміт із ПОРОЖНІМ імʼям автора: `git commit` його не створить, але чужий обʼєкт git приймає."""
        self.git(self.peer, 'fetch', '-q', 'origin')
        self.git(self.peer, 'reset', '-q', '--hard', 'origin/main')
        for rel, text in files.items():
            p = os.path.join(self.peer, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        self.git(self.peer, 'add', '-A')
        tree = self.git(self.peer, 'write-tree').strip()
        parent = self.git(self.peer, 'rev-parse', 'HEAD').strip()
        body = (f'tree {tree}\nparent {parent}\nauthor  <e@x> 1700000000 +0000\n'
                f'committer T <t@t> 1700000000 +0000\n\n{subject}\n')
        r = subprocess.run(['git', 'hash-object', '-t', 'commit', '-w', '--literally', '--stdin'], cwd=self.peer,
                           input=body, capture_output=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.git(self.peer, 'push', '-q', 'origin', f'{r.stdout.strip()}:refs/heads/main')

    def refs(self, origin):
        return self.git(origin, 'for-each-ref', '--format=%(refname) %(objectname)')

    def src(self, files=None, name='src'):
        d = os.path.join(self.tmp, name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        for rel, text in (files if files is not None else {'index.html': '<p>1</p>\n', '.canvas-state.json': '{}\n'}).items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        return d

    def dst(self, name='dst'):
        d = os.path.join(self.tmp, name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        return d

    def files_at(self, origin, ref='main'):
        r = subprocess.run(['git', 'ls-tree', '-r', '--name-only', ref], cwd=origin, capture_output=True,
                           encoding='utf-8')
        return r.stdout.split() if r.returncode == 0 else []

    def show(self, origin, spec):
        return self.git(origin, 'show', spec)

    def head(self, origin, ref='main'):
        r = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', ref], cwd=origin, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    def refused(self, call, code=None):
        with self.assertRaises(FakeModuleError) as cm:
            call()
        if code:
            self.assertEqual(cm.exception.code, code, cm.exception.message)
        return cm.exception


class Status(Repo):
    def go(self, origin, **kw):
        return self.m.status(self.ctx(), self.target(origin, **kw))

    def test_the_first_status_clones_the_mirror(self):
        origin = self.bare()
        r = self.go(origin)
        self.assertTrue(os.path.isdir(os.path.join(self.mirror(origin), '.git')))
        self.assertEqual(set(r), {'behind', 'behind_path', 'unpushed', 'on_remote', 'web', 'label'})
        self.assertEqual((r['behind'], r['behind_path'], r['unpushed']), (0, 0, 0))
        self.assertIs(r['on_remote'], False)
        self.assertIsNone(r['web'])
        self.assertEqual(r['label'], 'Git')

    def test_a_colleague_commit_is_behind_and_only_a_commit_in_the_path_is_behind_path(self):
        origin = self.bare()
        self.go(origin)
        self.peer_commit({'ci/build.yml': 'x\n'})
        r = self.go(origin)
        self.assertEqual((r['behind'], r['behind_path'], r['on_remote']), (1, 0, False))
        self.peer_commit({'mockup/t1/index.html': '<p>c</p>\n'})
        r = self.go(origin)
        self.assertEqual((r['behind'], r['behind_path'], r['on_remote']), (2, 1, True))

    def test_a_local_commit_in_the_mirror_is_unpushed(self):
        origin = self.bare()
        self.go(origin)
        self.git(self.mirror(origin), 'commit', '--allow-empty', '-qm', 'local')
        r = self.go(origin)
        self.assertEqual((r['unpushed'], r['behind']), (1, 0))

    def test_an_interrupted_clone_leaves_neither_a_mirror_nor_a_temp_folder(self):
        origin = self.bare()
        md = self.mirror(origin)

        def half_clone(argv):
            os.makedirs(os.path.join(argv[-1], '.git'), exist_ok=True)      # напівклон уже на диску
        with mock.patch.object(self.m.subprocess, 'run',
                               fake_run('clone', subprocess.TimeoutExpired('git', 1), before=half_clone)):
            self.refused(lambda: self.go(origin), 'vcs-offline')
        self.assertFalse(os.path.exists(md))
        self.assertEqual([n for n in os.listdir(os.path.dirname(md)) if not n.endswith('@lock')], [])
        self.assertEqual(self.go(origin)['behind'], 0, 'наступна спроба клонує заново')

    def test_origin_of_the_mirror_follows_the_target(self):
        a, b = self.bare('p-q/o.git'), self.bare('p/q/o.git')
        self.assertEqual(self.mirror(a), self.mirror(b), 'передумова: обидві адреси дають одну теку дзеркала')
        self.go(a)
        url = lambda: self.git(self.mirror(a), 'config', '--get', 'remote.origin.url').strip()
        self.assertEqual(url(), a)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.go(b)
        self.assertEqual(url(), b)
        self.assertIn('origin', err.getvalue())

    def test_offline_is_never_a_silent_zero(self):
        origin = self.bare()
        self.go(origin)
        os.rename(origin, origin + '.gone')
        e = self.refused(lambda: self.go(origin))
        self.assertIn(e.code, ('vcs-error', 'vcs-offline'))
        self.assertIn('fetch failed', e.message)

    def test_an_empty_remote_is_not_an_error_and_has_no_answer_for_on_remote(self):
        origin = self.bare(seed=False)
        for _ in range(2):          # другий статус робить fetch гілки, якої на origin ще нема: теж не помилка
            r = self.go(origin)
            self.assertEqual((r['behind'], r['behind_path'], r['unpushed'], r['on_remote']), (0, 0, 0, None))
        self.assertEqual(self.git(self.mirror(origin), 'symbolic-ref', 'HEAD').strip(), 'refs/heads/main')

    def test_an_empty_remote_gets_its_head_on_the_target_branch(self):
        origin = self.bare(seed=False)          # HEAD самого bare-репо — main
        self.go(origin, branch='dev')
        self.assertEqual(self.git(self.mirror(origin), 'symbolic-ref', 'HEAD').strip(), 'refs/heads/dev')

    def test_a_missing_branch_of_a_non_empty_remote_is_a_clone_failure(self):
        origin = self.bare()
        md = self.mirror(origin)
        e = self.refused(lambda: self.go(origin, branch='nope'))
        self.assertTrue(e.message.startswith('clone failed: '), e.message)
        self.assertFalse(os.path.exists(md))
        self.assertEqual([n for n in os.listdir(os.path.dirname(md)) if not n.endswith('@lock')], [])

    def test_a_folder_in_the_mirror_place_that_is_not_a_clone_is_refused(self):
        origin = self.bare()
        md = self.mirror(origin)
        os.makedirs(md)
        keep = os.path.join(md, 'keep.txt')
        with open(keep, 'w') as f:
            f.write('x')
        e = self.refused(lambda: self.go(origin), 'vcs-error')
        self.assertIn('not a git clone', e.message)
        self.assertTrue(os.path.isfile(keep))

    def test_unpushed_counts_the_local_commits_while_the_remote_has_no_branch_yet(self):
        origin = self.bare(seed=False)
        t = self.target(origin)
        with mock.patch.object(self.m.subprocess, 'run', fake_run('push', (1, self.PERMISSION))):
            self.assertFalse(self.m.push(self.ctx(), t, self.src(), self.META)['pushed'])
        r = self.m.status(self.ctx(), t)
        self.assertEqual((r['unpushed'], r['behind'], r['on_remote']), (1, 0, None))

    def test_a_tag_instead_of_a_branch_is_a_clone_failure(self):
        """`clone --branch <тег>` дає detached HEAD і успіх; працювати так тихо не можна."""
        origin = self.bare()
        self.git(self.peer, 'tag', 'v1')
        self.git(self.peer, 'push', '-q', 'origin', 'v1')
        md = self.mirror(origin)
        e = self.refused(lambda: self.go(origin, branch='v1'), 'vcs-error')
        self.assertTrue(e.message.startswith('clone failed: '), e.message)
        self.assertIn('not a branch', e.message)
        self.assertFalse(os.path.exists(md))
        self.assertEqual([n for n in os.listdir(os.path.dirname(md)) if not n.endswith('@lock')], [])

    def test_a_token_in_the_old_origin_is_masked_in_the_realignment_notice(self):
        origin = self.bare()
        self.go(origin)
        self.git(self.mirror(origin), 'remote', 'set-url', 'origin', 'https://TOKEN123@h.example/o/r.git')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.go(origin)
        self.assertIn('***@h.example', err.getvalue())
        self.assertNotIn('TOKEN123', err.getvalue())

    def test_a_git_dir_in_the_environment_does_not_hijack_the_mirror(self):
        origin = self.bare()
        other = self.bare('other.git', seed=False)
        hostile = {'GIT_DIR': other, 'GIT_WORK_TREE': self.tmp, 'GIT_INDEX_FILE': os.path.join(self.tmp, 'idx')}
        with mock.patch.dict(os.environ, hostile):
            for _ in range(2):                       # перший статус клонує, другий працює з готовим дзеркалом
                r = self.go(origin)
                self.assertEqual((r['behind'], r['on_remote']), (0, False))
        self.assertTrue(os.path.isdir(os.path.join(self.mirror(origin), '.git')))
        self.assertEqual(self.refs(other), '')

    @needs_symlink
    def test_a_dangling_symlink_in_the_mirror_place_is_refused(self):
        origin = self.bare()
        md = self.mirror(origin)
        os.makedirs(os.path.dirname(md))
        os.symlink(os.path.join(self.tmp, 'nowhere'), md)
        e = self.refused(lambda: self.go(origin), 'vcs-error')
        self.assertIn('not a git clone', e.message)
        self.assertTrue(os.path.islink(md))

    def test_a_cache_that_cannot_be_created_is_a_vcs_error(self):
        origin = self.bare()
        os.makedirs(self.cache)
        with open(os.path.join(self.cache, 'mirrors'), 'w') as f:      # файл на місці теки
            f.write('x')
        t = self.target(origin)
        self.refused(lambda: self.m.status(self.ctx(), t), 'vcs-error')
        self.refused(lambda: self.m.push(self.ctx(), t, self.src(), self.META), 'vcs-error')
        self.refused(lambda: self.m.pull(self.ctx(), t, self.dst()), 'vcs-error')

    def test_a_clone_folder_that_cannot_be_made_is_a_vcs_error(self):
        origin = self.bare()
        with mock.patch.object(self.m.tempfile, 'mkdtemp', side_effect=OSError(28, 'No space left on device')):
            self.refused(lambda: self.go(origin), 'vcs-error')

    def test_a_failed_rename_of_the_clone_is_a_vcs_error_and_leaves_no_temp_folder(self):
        origin = self.bare()
        md = self.mirror(origin)
        with mock.patch.object(self.m.os, 'rename', side_effect=OSError(18, 'Invalid cross-device link')):
            self.refused(lambda: self.go(origin), 'vcs-error')
        self.assertEqual([n for n in os.listdir(os.path.dirname(md)) if not n.endswith('@lock')], [])

    def test_a_busy_mirror_is_refused_by_all_three_operations(self):
        origin = self.bare()
        t = self.target(origin)
        src, dst = self.src(), self.dst()
        with self.m._Lock(self.ctx(), self.mirror(origin), wait=0):
            with mock.patch.object(self.m, 'LOCK_WAIT', 2):
                t0 = time.monotonic()
                self.refused(lambda: self.m.status(self.ctx(), t), 'vcs-busy')
                self.assertLess(time.monotonic() - t0, 1, 'status не чекає на зайняте дзеркало')
            with mock.patch.object(self.m, 'LOCK_WAIT', 0):
                self.refused(lambda: self.m.push(self.ctx(), t, src, self.META), 'vcs-busy')
                self.refused(lambda: self.m.pull(self.ctx(), t, dst), 'vcs-busy')

    def test_a_bad_target_is_refused_before_any_git(self):
        boom = Recorder(AssertionError('погана ціль — до git не доходить'))
        src, dst = self.src(), self.dst()
        t = {'repo': 'ext::sh', 'path': 'mockup/t1'}
        with mock.patch.object(self.m.subprocess, 'run', boom):
            self.refused(lambda: self.m.status(self.ctx(), t), 'vcs-bad-target')
            self.refused(lambda: self.m.push(self.ctx(), t, src, self.META), 'vcs-bad-target')
            self.refused(lambda: self.m.pull(self.ctx(), t, dst), 'vcs-bad-target')
        self.assertEqual(boom.calls, [])


class Push(Repo):
    def go(self, origin, src, meta='default', **kw):
        return self.m.push(self.ctx(), self.target(origin, **kw), src, self.META if meta == 'default' else meta)

    def test_the_first_push_commits_under_the_authors_name(self):
        origin = self.bare()
        r = self.go(origin, self.src())
        self.assertTrue(r.pop('sha'))
        self.assertEqual(r, {'ok': True, 'synced': True, 'changed': True, 'pushed': True, 'error': None})
        who, subj = self.git(origin, 'log', '-1', '--format=%an%n%s', 'main').splitlines()
        self.assertEqual((who, subj), ('Анна', 'deai: sync mockup/t1 (Т) · it1'))
        self.assertEqual(self.git(origin, 'log', '-1', '--format=%ae %cn', 'main').strip(), 'a@x Анна')
        self.assertIn('тіло', self.git(origin, 'log', '-1', '--format=%B', 'main'))
        files = self.files_at(origin)
        self.assertIn('mockup/t1/.canvas-state.json', files)
        self.assertIn('mockup/t1/index.html', files)
        self.assertIn('README.md', files)

    def test_a_repeat_without_changes_does_not_push(self):
        origin = self.bare()
        src = self.src()
        self.go(origin, src)
        head = self.head(origin)
        self.assertEqual(self.go(origin, src), {'ok': True, 'synced': True, 'changed': False, 'pushed': False})
        self.assertEqual(self.head(origin), head)

    def test_a_file_removed_from_src_leaves_the_repo(self):
        origin = self.bare()
        self.go(origin, self.src({'index.html': 'a\n', 'old.html': 'b\n'}))
        self.assertIn('mockup/t1/old.html', self.files_at(origin))
        r = self.go(origin, self.src({'index.html': 'a\n'}))
        self.assertTrue(r['changed'] and r['pushed'])
        self.assertEqual([f for f in self.files_at(origin) if f.startswith('mockup/')], ['mockup/t1/index.html'])

    def test_a_commit_of_a_colleague_in_the_path_blocks_and_changes_nothing(self):
        origin = self.bare()
        self.go(origin, self.src())
        self.peer_commit({'mockup/t1/index.html': '<p>c</p>\n'}, msg='peer edit')
        head = self.head(origin)
        r = self.go(origin, self.src({'index.html': '<p>2</p>\n'}))
        top = r.pop('behind_top')
        self.assertEqual(r, {'ok': False, 'synced': False, 'blocked': 'behind', 'behind': 1, 'behind_path': 1})
        self.assertEqual((top['author'], top['subject']), ('Колега', 'peer edit'))
        self.assertRegex(top['date'], r'^\d\d\.\d\d\.\d{4} \d\d:\d\d$')
        self.assertEqual(self.head(origin), head)
        self.assertEqual(self.show(origin, 'main:mockup/t1/index.html'), '<p>c</p>\n')

    def test_a_commit_of_a_colleague_outside_the_path_is_fast_forwarded_and_the_push_goes_on(self):
        origin = self.bare()
        self.go(origin, self.src())
        self.peer_commit({'ci/build.yml': 'x\n'})
        r = self.go(origin, self.src({'index.html': '<p>2</p>\n'}))
        self.assertEqual((r['ok'], r['changed'], r['pushed']), (True, True, True))
        self.assertEqual(self.show(origin, 'main:mockup/t1/index.html'), '<p>2</p>\n')
        self.assertIn('ci/build.yml', self.files_at(origin))

    def test_a_diverged_mirror_is_not_pushed(self):
        origin = self.bare()
        self.m.status(self.ctx(), self.target(origin))              # клон
        self.git(self.mirror(origin), 'commit', '--allow-empty', '-qm', 'local')
        self.peer_commit({'ci/build.yml': 'x\n'}, msg='peer')
        head = self.head(origin)
        r = self.go(origin, self.src())
        top, err = r.pop('behind_top'), r.pop('error')
        self.assertEqual(r, {'ok': False, 'synced': False, 'blocked': 'diverged', 'behind': 1, 'ahead': 1})
        self.assertEqual(top['subject'], 'peer')
        self.assertTrue(err)
        self.assertEqual(self.head(origin), head)
        self.assertNotIn('mockup/t1/index.html', self.files_at(origin))

    def test_another_branch_of_a_known_repo_continues_its_own_history(self):
        """Дзеркало вже є (на main); `dev` на origin має свій коміт: локальна `dev` мусить стати поверх `origin/dev`,
        а не новим коренем — інакше push відбився б як non-fast-forward."""
        origin = self.bare()
        self.go(origin, self.src())                                 # дзеркало створено для main
        self.peer_branch('dev', {'mockup/t1/index.html': 'dev\n', 'dev-only.txt': 'x\n'})
        dev_head = self.head(origin, 'refs/heads/dev')
        r = self.go(origin, self.src({'index.html': 'mine\n'}), branch='dev')
        self.assertEqual((r['ok'], r['changed'], r['pushed']), (True, True, True))
        self.assertEqual(self.head(origin, 'refs/heads/dev~1'), dev_head)
        self.assertEqual(self.show(origin, 'dev:mockup/t1/index.html'), 'mine\n')
        self.assertIn('dev-only.txt', self.files_at(origin, 'dev'))

    def test_a_rejected_push_reports_its_code_and_the_next_push_catches_up(self):
        origin = self.bare()
        src = self.src()
        with mock.patch.object(self.m.subprocess, 'run', fake_run('push', (1, self.PERMISSION))):
            r = self.go(origin, src)
        self.assertEqual((r['ok'], r['synced'], r['pushed'], r['changed'], r['code']),
                         (False, False, False, True, 'vcs-auth'))
        self.assertIn('Permission denied', r['error'])
        self.assertNotIn('mockup/t1/index.html', self.files_at(origin))
        self.assertEqual(self.m.status(self.ctx(), self.target(origin))['unpushed'], 1)
        r = self.go(origin, src)                                    # той самий src: нічого нового, але коміт не доїхав
        self.assertEqual(r, {'ok': True, 'synced': True, 'changed': False, 'pushed': True, 'catchup': True,
                             'error': None})
        self.assertIn('mockup/t1/index.html', self.files_at(origin))
        self.assertEqual(self.m.status(self.ctx(), self.target(origin))['unpushed'], 0)

    def test_the_first_push_into_an_empty_remote_creates_the_branch(self):
        origin = self.bare(seed=False)
        r = self.go(origin, self.src())
        self.assertEqual((r['ok'], r['changed'], r['pushed']), (True, True, True))
        self.assertTrue(self.head(origin, 'refs/heads/main'))
        self.assertIn('mockup/t1/index.html', self.files_at(origin))
        self.assertEqual(self.go(origin, self.src()), {'ok': True, 'synced': True, 'changed': False, 'pushed': False})

    def test_the_first_push_into_an_empty_remote_creates_a_branch_other_than_its_head(self):
        origin = self.bare(seed=False)
        self.go(origin, self.src(), branch='dev')
        self.assertTrue(self.head(origin, 'refs/heads/dev'))
        self.assertIsNone(self.head(origin, 'refs/heads/main'))

    def test_an_empty_src_into_an_empty_remote_is_not_reported_as_sent(self):
        """Гілки на origin ще нема, нових змін теж: «synced» тут було б брехнею (bgSanctions, 12 днів «✓»)."""
        origin = self.bare(seed=False)
        r = self.go(origin, self.src({}))
        self.assertEqual((r['ok'], r['synced'], r['pushed']), (False, False, False))
        self.assertTrue(r['error'])
        self.assertIsNone(self.head(origin, 'refs/heads/main'))

    def test_a_src_that_is_not_a_folder_is_a_vcs_error_and_touches_no_git(self):
        origin = self.bare()
        f = os.path.join(self.tmp, 'file.txt')
        with open(f, 'w') as fh:
            fh.write('x')
        boom = Recorder(AssertionError('зламаний src — до git не доходить'))
        with mock.patch.object(self.m.subprocess, 'run', boom):
            for bad in (os.path.join(self.tmp, 'nope'), f, None, 5):
                with self.subTest(src=repr(bad)):
                    self.refused(lambda: self.go(origin, bad), 'vcs-error')
        self.assertEqual(boom.calls, [])

    def test_without_meta_the_commit_gets_a_neutral_identity(self):
        origin = self.bare()
        for i, meta in enumerate((None, 'x', {}, {'author': 'x'}, {'author': {'name': '  ', 'email': ''}})):
            with self.subTest(meta=repr(meta)):
                self.assertTrue(self.go(origin, self.src({'index.html': f'{i}\n'}), meta=meta)['pushed'])
                self.assertEqual(self.git(origin, 'log', '-1', '--format=%an|%ae|%s', 'main').strip(),
                                 'Deai Canvas|deai@localhost|deai: sync')

    def test_a_failed_status_is_an_error_not_a_quiet_success(self):
        """Порожній вивід `status` при відмові git читався б як «змін нема» — і push звітував би «synced»."""
        origin = self.bare()
        with mock.patch.object(self.m.subprocess, 'run', fake_run('status', (128, 'fatal: boom'))):
            e = self.refused(lambda: self.go(origin, self.src()), 'vcs-error')
        self.assertTrue(e.message.startswith('status failed: '), e.message)

    def test_a_failed_commit_is_an_error(self):
        origin = self.bare()
        with mock.patch.object(self.m.subprocess, 'run', fake_run('commit', (1, 'error: gpg failed to sign the data'))):
            e = self.refused(lambda: self.go(origin, self.src()), 'vcs-error')
        self.assertTrue(e.message.startswith('commit failed: '), e.message)

    def test_a_file_in_the_place_of_the_folder_is_a_vcs_error(self):
        origin = self.bare()
        self.peer_commit({'mockup': 'не тека\n'})
        e = self.refused(lambda: self.go(origin, self.src()), 'vcs-error')
        self.assertIn('cannot replace', e.message)

    def test_a_staged_stray_file_in_the_mirror_is_not_committed_along(self):
        origin = self.bare()
        self.m.status(self.ctx(), self.target(origin))
        md = self.mirror(origin)
        with open(os.path.join(md, 'stray.txt'), 'w') as f:
            f.write('чуже\n')
        self.git(md, 'add', 'stray.txt')
        self.assertTrue(self.go(origin, self.src())['pushed'])
        self.assertNotIn('stray.txt', self.files_at(origin))

    def test_a_failed_commit_leaves_a_clean_tree_that_the_next_pull_trusts(self):
        origin = self.bare()
        self.go(origin, self.src({'index.html': 'v1-committed\n'}))
        with mock.patch.object(self.m.subprocess, 'run', fake_run('commit', (1, 'error: gpg failed to sign the data'))):
            self.refused(lambda: self.go(origin, self.src({'index.html': 'LOCAL\n', 'x.html': 'x\n'})), 'vcs-error')
        md = self.mirror(origin)
        self.assertEqual(self.git(md, 'status', '--porcelain').strip(), '')
        self.peer_commit({'ci/build.yml': 'x\n'}, msg='peer outside the path')
        dst = self.dst()
        r = self.m.pull(self.ctx(), self.target(origin), dst)
        self.assertEqual(r['last_commit']['author'], 'Анна')
        self.assertEqual(os.listdir(dst), ['index.html'])
        with open(os.path.join(dst, 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'v1-committed\n')

    def test_a_failed_first_commit_on_an_empty_remote_leaves_a_clean_tree(self):
        """HEAD ще не народжений: `reset --hard HEAD` тут неможливий, а індекс після `add` уже повний."""
        origin = self.bare(seed=False)
        with mock.patch.object(self.m.subprocess, 'run', fake_run('commit', (1, 'error: gpg failed to sign the data'))):
            self.refused(lambda: self.go(origin, self.src()), 'vcs-error')
        self.assertEqual(self.git(self.mirror(origin), 'status', '--porcelain').strip(), '')
        self.assertTrue(self.go(origin, self.src())['pushed'])
        self.assertIn('mockup/t1/index.html', self.files_at(origin))

    def test_a_copy_that_breaks_midway_leaves_a_clean_tree(self):
        origin = self.bare()
        self.go(origin, self.src({'index.html': 'a\n', 'b.html': 'b\n'}))
        new = self.src({'index.html': 'A\n', 'b.html': 'B\n', 'c.html': 'C\n'})
        real_tree, real_copy, calls = shutil.copytree, shutil.copy2, [0]

        def flaky_copy(s, d, **kw):
            calls[0] += 1
            if calls[0] == 2:
                raise PermissionError(13, 'boom', s)
            return real_copy(s, d, **kw)

        def tree(*a, **kw):
            kw['copy_function'] = flaky_copy
            return real_tree(*a, **kw)
        with mock.patch.object(self.m.shutil, 'copytree', tree):
            e = self.refused(lambda: self.go(origin, new), 'vcs-error')
        self.assertIn('cannot replace', e.message)
        md = self.mirror(origin)
        self.assertEqual(self.git(md, 'status', '--porcelain').strip(), '')
        self.assertEqual(sorted(os.listdir(os.path.join(md, 'mockup/t1'))), ['b.html', 'index.html'])
        self.assertEqual(self.m.status(self.ctx(), self.target(origin))['unpushed'], 0)

    def test_a_branch_that_is_not_on_a_non_empty_remote_is_refused_and_origin_is_untouched(self):
        """Друкарська помилка в гілці не мусить породити на origin кореневий коміт із усім індексом `main`."""
        origin = self.bare()
        self.git(self.peer, 'tag', 'v1')
        self.git(self.peer, 'push', '-q', 'origin', 'v1')
        self.m.status(self.ctx(), self.target(origin))              # дзеркало вже є
        before = self.refs(origin)
        for branch in ('typo-branch', 'v1'):                        # другий — тег, а не гілка
            with self.subTest(branch=branch):
                e = self.refused(lambda: self.go(origin, self.src(), branch=branch), 'vcs-error')
                self.assertIn('not found on the remote', e.message)
        self.assertEqual(self.refs(origin), before)

    def test_a_failed_ls_remote_never_turns_into_a_new_branch(self):
        """Мережевий збій дає порожній stdout `ls-remote`: без перевірки rc це читалось би як «репо порожнє» і
        гілка-друкарська помилка створилась би на origin."""
        cases = (('timeout', subprocess.TimeoutExpired('git', 120), 'vcs-offline'),
                 ('resolve', (128, "fatal: unable to access 'https://TOKEN123@h.example/o/r.git/': Could not resolve host: "
                                   "h.example"), 'vcs-offline'),
                 ('auth', (128, self.PERMISSION), 'vcs-auth'),
                 ('silent', (128, ''), 'vcs-error'))
        for i, (label, answer, code) in enumerate(cases):
            for op in ('push', 'pull'):
                with self.subTest(case=label, op=op):
                    origin = self.bare(f'ls-{i}-{op}.git')
                    t = self.target(origin, branch='typo')
                    self.m.status(self.ctx(), self.target(origin))             # дзеркало на main, `typo` у ньому нема
                    md = self.mirror(origin)
                    head, refs = self.git(md, 'symbolic-ref', 'HEAD'), self.refs(origin)
                    call = ((lambda: self.m.push(self.ctx(), t, self.src(), self.META)) if op == 'push'
                            else (lambda: self.m.pull(self.ctx(), t, self.dst())))
                    with mock.patch.object(self.m.subprocess, 'run', fake_run('ls-remote', answer)):
                        e = self.refused(call, code)
                    self.assertNotIn('TOKEN123', e.message)
                    if label == 'resolve':
                        self.assertIn('***@h.example', e.message)
                    self.assertEqual(self.git(md, 'symbolic-ref', 'HEAD'), head)
                    self.assertEqual(self.refs(origin), refs)
                    self.assertEqual(self.git(md, 'for-each-ref', 'refs/heads/typo'), '')

    def test_the_first_commit_after_the_remote_was_emptied_holds_only_the_path(self):
        """Усі гілки origin видалено, а дзеркало ще має дерево старої гілки: індекс лишився б повним, і перший коміт
        нової гілки ніс би README та решту чужого дерева."""
        origin = self.bare()
        self.m.status(self.ctx(), self.target(origin))              # дзеркало з деревом main (README.md)
        self.git(origin, 'update-ref', '-d', 'refs/heads/main')
        self.assertEqual(self.refs(origin), '')
        r = self.go(origin, self.src(), branch='dev')
        self.assertEqual((r['ok'], r['changed'], r['pushed']), (True, True, True))
        self.assertEqual(self.files_at(origin, 'dev'), ['mockup/t1/.canvas-state.json', 'mockup/t1/index.html'])
        self.assertEqual(self.git(origin, 'rev-list', '--count', 'dev').strip(), '1')
        self.assertFalse(os.path.exists(os.path.join(self.mirror(origin), 'README.md')))

    def test_the_author_of_the_meta_wins_over_the_identity_variables_of_the_parent(self):
        origin = self.bare()
        env = {'GIT_AUTHOR_NAME': 'EnvPerson', 'GIT_AUTHOR_EMAIL': 'env@x', 'GIT_COMMITTER_NAME': 'EnvPerson',
               'GIT_COMMITTER_EMAIL': 'env@x', 'GIT_AUTHOR_DATE': '2001-01-01T00:00:00',
               'GIT_COMMITTER_DATE': '2001-01-01T00:00:00'}
        with mock.patch.dict(os.environ, env):
            self.assertTrue(self.go(origin, self.src())['pushed'])
        who, when = self.git(origin, 'log', '-1', '--format=%an|%cn|%ae|%ce|%at', 'main').strip().rsplit('|', 1)
        self.assertEqual(who, 'Анна|Анна|a@x|a@x')
        self.assertGreater(int(when), 1700000000, 'дата коміту — «зараз», а не з GIT_*_DATE')

    def test_a_token_is_masked_before_the_error_is_cut(self):
        """Маска після обрізання лишала б хвіст токена, бо різ ховає `://`."""
        g = self.m._Git(self.ctx(), {'repo': 'x'})
        text, leaked = cut_inside_a_token(300)
        err = self.m._pushed(g, FakeProc(1, text), changed=True)['error']
        self.assertNotIn(leaked, err)
        self.assertTrue(err)
        origin = self.bare()
        self.m.status(self.ctx(), self.target(origin))
        self.peer_commit({'ci/build.yml': 'x\n'})
        text, leaked = cut_inside_a_token(200)
        with mock.patch.object(self.m.subprocess, 'run', fake_run('merge', (128, text))):
            r = self.go(origin, self.src())
        self.assertEqual(r['blocked'], 'diverged')
        self.assertNotIn(leaked, r['error'])
        self.assertTrue(r['error'])

    def test_control_characters_in_meta_are_refused_before_any_git(self):
        origin = self.bare()
        boom = Recorder(AssertionError('зіпсований meta — до git не доходить'))
        bad = [{'message': 'a\x00b'}, {'message': 'a\x1bb'}, {'message': 'a\x7fb'},
               {'author': {'name': 'A\x00', 'email': 'a@x'}}, {'author': {'name': 'A\nB', 'email': 'a@x'}},
               {'author': {'name': 'A', 'email': 'a\x00@x'}}, {'author': {'name': 'A', 'email': 'a@x\n'}}]
        src = self.src()
        with mock.patch.object(self.m.subprocess, 'run', boom):
            for meta in bad:
                with self.subTest(meta=meta):
                    self.refused(lambda: self.go(origin, src, meta=meta), 'vcs-error')
        self.assertEqual(boom.calls, [])
        meta = {'message': 'рядок\n\n\tтіло\r\n', 'author': {'name': 'Анна', 'email': 'a@x'}}
        self.assertTrue(self.go(origin, src, meta=meta)['pushed'], 'перенос рядка й табуляція в повідомленні — норма')

    @needs_symlink
    def test_symlinks_in_src_are_not_carried_into_the_repo(self):
        """Лінк у спільному репо виніс би локальні шляхи, а розіменування — вміст поза текою макета."""
        origin = self.bare()
        outside = os.path.join(self.tmp, 'outside')
        os.makedirs(os.path.join(outside, 'sub'))
        for rel in ('secret.txt', 'sub/inner.txt'):
            with open(os.path.join(outside, rel), 'w') as f:
                f.write('не для репо\n')
        src = self.src()
        os.symlink(os.path.join(outside, 'secret.txt'), os.path.join(src, 'leak.txt'))
        os.symlink(outside, os.path.join(src, 'leakdir'))
        os.symlink('index.html', os.path.join(src, 'rel'))
        self.assertTrue(self.go(origin, src)['pushed'])
        self.assertEqual([f for f in self.files_at(origin) if f.startswith('mockup/')],
                         ['mockup/t1/.canvas-state.json', 'mockup/t1/index.html'])

    def test_a_non_ascii_path_works_under_the_pinned_locale(self):
        origin = self.bare()
        kw = {'path': 'mockup/Задача 1'}
        with mock.patch.dict(os.environ, {'LC_ALL': 'uk_UA.UTF-8', 'LANG': 'uk_UA.UTF-8', 'LANGUAGE': 'uk'}):
            self.assertTrue(self.go(origin, self.src(), **kw)['pushed'])
            self.assertEqual(self.go(origin, self.src(), **kw), {'ok': True, 'synced': True, 'changed': False,
                                                                 'pushed': False})
            self.assertIs(self.m.status(self.ctx(), self.target(origin, **kw))['on_remote'], True)
            dst = self.dst()
            self.assertEqual(self.m.pull(self.ctx(), self.target(origin, **kw), dst)['last_commit']['author'], 'Анна')
        self.assertEqual(sorted(os.listdir(dst)), ['.canvas-state.json', 'index.html'])

    def test_behind_top_keeps_an_empty_author_field_and_cuts_a_long_subject(self):
        origin = self.bare()
        self.go(origin, self.src())
        self.peer_commit_by_nobody({'mockup/t1/index.html': '<p>c</p>\n'}, subject='тема без автора')
        top = self.go(origin, self.src({'index.html': '2\n'}))['behind_top']
        self.assertEqual((top['author'], top['subject']), ('', 'тема без автора'))
        self.assertRegex(top['date'], r'^\d\d\.\d\d\.\d{4} \d\d:\d\d$')
        self.peer_commit({'mockup/t1/index.html': '<p>d</p>\n'}, msg='я' * 200)
        top = self.go(origin, self.src({'index.html': '3\n'}))['behind_top']
        self.assertEqual(top['subject'], 'я' * 120)

    # --- симлінки в чужому репо ---

    @needs_symlink
    def test_a_symlinked_folder_in_the_repo_is_not_followed_out_of_the_mirror(self):
        origin = self.bare()
        outside = os.path.join(self.tmp, 'outside')
        os.makedirs(os.path.join(outside, 't1'))
        for rel in ('keep.txt', 't1/keep.txt'):
            with open(os.path.join(outside, rel), 'w') as f:
                f.write('мій файл\n')
        self.peer_commit(links={'mockup': outside})
        e = self.refused(lambda: self.go(origin, self.src()), 'vcs-error')
        self.assertIn('symlink', e.message)
        self.assertEqual(sorted(os.listdir(outside)), ['keep.txt', 't1'])
        self.assertEqual(os.listdir(os.path.join(outside, 't1')), ['keep.txt'], 'тека поза дзеркалом не заміщена')

    @needs_symlink
    def test_a_symlink_into_the_mirror_itself_is_refused_too(self):
        """`mockup -> .git`: шлях `mockup/refs` лишається ВСЕРЕДИНІ дзеркала, але це `.git/refs`; `rmtree` знищив би репо."""
        origin = self.bare()
        self.peer_commit(links={'mockup': '.git'})
        md = self.mirror(origin)
        self.refused(lambda: self.go(origin, self.src(), path='mockup/refs'), 'vcs-error')
        self.assertTrue(os.path.isdir(os.path.join(md, '.git', 'refs', 'heads')))
        self.assertEqual(self.git(md, 'rev-parse', '--verify', 'HEAD').strip(), self.head(origin))


class Pull(Repo):
    def go(self, origin, dst=None, opts=None, **kw):
        return self.m.pull(self.ctx(), self.target(origin, **kw), self.dst() if dst is None else dst, opts)

    def test_a_folder_of_a_colleague_is_copied_with_its_author_and_time(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '<p>c</p>\n', 'mockup/t1/.canvas-state.json': '{}\n'},
                         when=1700000000)
        dst = self.dst()
        r = self.go(origin, dst)
        self.assertEqual(r, {'found': True, 'last_commit': {'author': 'Колега', 'time': 1700000000}})
        self.assertIsInstance(r['last_commit']['time'], int)
        with open(os.path.join(dst, 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), '<p>c</p>\n')
        self.assertTrue(os.path.isfile(os.path.join(dst, '.canvas-state.json')))

    def test_a_second_pull_brings_the_newer_version(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '1\n'}, when=1700000000)
        self.go(origin)
        self.peer_commit({'mockup/t1/index.html': '2\n'}, who='Інша', when=1700000100)
        dst = self.dst()
        r = self.go(origin, dst)
        self.assertEqual(r['last_commit'], {'author': 'Інша', 'time': 1700000100})
        with open(os.path.join(dst, 'index.html')) as f:
            self.assertEqual(f.read(), '2\n')

    def test_a_missing_folder_is_found_false_and_dst_stays_empty(self):
        origin = self.bare()
        dst = self.dst()
        self.assertEqual(self.go(origin, dst), {'found': False, 'last_commit': None})
        self.assertEqual(os.listdir(dst), [])

    def test_an_empty_remote_is_found_false_not_an_error(self):
        origin = self.bare(seed=False)
        dst = self.dst()
        self.assertEqual(self.go(origin, dst), {'found': False, 'last_commit': None})
        self.assertEqual(os.listdir(dst), [])

    def test_frames_do_not_count_as_work_when_ignored(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '<p>c</p>\n'}, who='Колега', when=1700000000)
        self.peer_commit({'mockup/t1/shots/a.png': 'png\n'}, who='Кадри', when=1700000500)
        r = self.go(origin, opts={'ignore': ['shots']})
        self.assertEqual(r['last_commit'], {'author': 'Кадри', 'time': 1700000000})
        r = self.go(origin)
        self.assertEqual(r['last_commit'], {'author': 'Кадри', 'time': 1700000500})
        r = self.go(origin, opts={'ignore': ['shots/']})
        self.assertEqual(r['last_commit']['time'], 1700000000, 'слеш по краях не заважає')

    def test_when_only_ignored_folders_changed_the_time_is_none(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/shots/a.png': 'png\n'}, when=1700000500)
        r = self.go(origin, opts={'ignore': ['shots']})
        self.assertEqual(r, {'found': True, 'last_commit': {'author': 'Колега', 'time': None}})

    def test_a_diverged_mirror_is_an_error_with_a_hint_and_nothing_is_copied(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '1\n'})
        self.go(origin)
        self.git(self.mirror(origin), 'commit', '--allow-empty', '-qm', 'local')
        self.peer_commit({'mockup/t1/index.html': '2\n'})
        dst = self.dst()
        e = self.refused(lambda: self.go(origin, dst), 'vcs-error')
        self.assertTrue(e.message.startswith('pull --ff-only failed: '), e.message)
        self.assertIn('локальний(х) коміт(ів)', e.message)
        self.assertLessEqual(len(e.message), 300)
        self.assertEqual(os.listdir(dst), [])

    def test_broken_arguments_are_refused_before_any_git(self):
        origin = self.bare()
        boom = Recorder(AssertionError('зламані аргументи — до git не доходить'))
        full = self.dst('full')
        with open(os.path.join(full, 'x'), 'w') as f:
            f.write('x')
        with mock.patch.object(self.m.subprocess, 'run', boom):
            for opts in ({'ignore': ['../x']}, {'ignore': ['a/../b']}, {'ignore': ['']}, {'ignore': [5]},
                         {'ignore': 'shots'}, {'ignore': ['.git']}, {'ignore': ['a*']}, {'ignore': [':(top)x']}):
                with self.subTest(opts=opts):
                    self.refused(lambda: self.go(origin, opts=opts), 'vcs-bad-target')
            for bad in (full, os.path.join(self.tmp, 'nope'), None, 5):
                with self.subTest(dst=repr(bad)):
                    self.refused(lambda: self.m.pull(self.ctx(), self.target(origin), bad), 'vcs-error')
        self.assertEqual(boom.calls, [])

    def test_ignore_is_optional(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '1\n'}, when=1700000000)
        for opts in (None, {}, {'ignore': None}, {'ignore': []}, 'x', 5):
            with self.subTest(opts=repr(opts)):
                self.assertEqual(self.go(origin, opts=opts)['last_commit']['time'], 1700000000)

    def test_another_branch_of_a_known_repo_gets_its_own_local_branch(self):
        origin = self.bare()
        self.go(origin)                                             # дзеркало вже є, і воно на main
        self.peer_branch('dev', {'mockup/t1/index.html': 'dev\n'}, when=1700000000)
        dst = self.dst()
        r = self.go(origin, dst, branch='dev')
        self.assertEqual(r['found'], True)
        with open(os.path.join(dst, 'index.html')) as f:
            self.assertEqual(f.read(), 'dev\n')
        self.assertEqual(self.git(self.mirror(origin), 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'dev')

    def test_a_dirty_mirror_is_never_handed_out_as_the_work_of_a_colleague(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': 'origin\n'})
        self.go(origin)
        md = self.mirror(origin)
        for rel, text in (('mockup/t1/index.html', 'LOCAL-UNCOMMITTED\n'), ('mockup/t1/extra.html', 'сміття\n')):
            with open(os.path.join(md, rel), 'w', encoding='utf-8') as f:
                f.write(text)
        dst = self.dst()
        r = self.go(origin, dst)
        self.assertEqual(os.listdir(dst), ['index.html'])
        with open(os.path.join(dst, 'index.html')) as f:
            self.assertEqual(f.read(), 'origin\n')
        self.assertEqual(r['last_commit']['author'], 'Колега')

    def test_a_dirty_tree_does_not_block_switching_to_another_branch(self):
        """`checkout` відмовився б перезаписати зміни: чистка йде ДО нього, а не після."""
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': 'main\n'})
        self.go(origin)
        self.peer_branch('dev', {'mockup/t1/index.html': 'dev\n'})
        with open(os.path.join(self.mirror(origin), 'mockup/t1/index.html'), 'w') as f:
            f.write('LOCAL-UNCOMMITTED\n')
        dst = self.dst()
        self.assertTrue(self.go(origin, dst, branch='dev')['found'])
        with open(os.path.join(dst, 'index.html')) as f:
            self.assertEqual(f.read(), 'dev\n')

    def test_a_branch_that_is_not_on_a_non_empty_remote_is_refused_and_origin_is_untouched(self):
        origin = self.bare()
        self.git(self.peer, 'tag', 'v1')
        self.git(self.peer, 'push', '-q', 'origin', 'v1')
        self.go(origin)
        before = self.refs(origin)
        for branch in ('typo-branch', 'v1'):
            with self.subTest(branch=branch):
                dst = self.dst()
                e = self.refused(lambda: self.go(origin, dst, branch=branch), 'vcs-error')
                self.assertIn('not found on the remote', e.message)
                self.assertEqual(os.listdir(dst), [])
        self.assertEqual(self.refs(origin), before)

    def test_a_copy_failure_is_a_vcs_error(self):
        origin = self.bare()
        self.peer_commit({'mockup/t1/index.html': '1\n'})
        with mock.patch.object(self.m.shutil, 'copytree', side_effect=OSError(13, 'denied')):
            e = self.refused(lambda: self.go(origin), 'vcs-error')
        self.assertIn('cannot copy', e.message)

    # --- симлінки в чужому репо ---

    @needs_symlink
    def test_a_symlinked_folder_in_the_repo_is_not_followed_out_of_the_mirror(self):
        origin = self.bare()
        outside = os.path.join(self.tmp, 'outside')
        os.makedirs(os.path.join(outside, 't1'))
        with open(os.path.join(outside, 't1', 'secret.txt'), 'w') as f:
            f.write('не для чужих очей\n')
        self.peer_commit(links={'mockup': outside})
        dst = self.dst()
        e = self.refused(lambda: self.go(origin, dst), 'vcs-error')
        self.assertIn('symlink', e.message)
        self.assertEqual(os.listdir(dst), [], 'нічого з-поза дзеркала не скопійовано')

    @needs_symlink
    def test_a_symlink_inside_the_folder_is_not_carried(self):
        origin = self.bare()
        outside = os.path.join(self.tmp, 'outside')
        os.makedirs(outside)
        with open(os.path.join(outside, 'secret.txt'), 'w') as f:
            f.write('secret\n')
        self.peer_commit({'mockup/t1/index.html': '<p>c</p>\n'},
                         links={'mockup/t1/leak.txt': os.path.join(outside, 'secret.txt'),
                                'mockup/t1/leakdir': outside, 'mockup/t1/rel': 'index.html'})
        dst = self.dst()
        self.assertTrue(self.go(origin, dst)['found'])
        self.assertEqual(os.listdir(dst), ['index.html'])
        for n in ('leak.txt', 'leakdir', 'rel'):
            self.assertFalse(os.path.lexists(os.path.join(dst, n)), n)


@unittest.skipIf(os.name == 'nt', 'flock між процесами — лише POSIX')
class Waiting(Repo):
    """`push` і `pull` ЧЕКАЮТЬ на зайняте дзеркало (на відміну від `status`): лок тримає інший процес."""

    def hold(self, origin, seconds):
        md = self.mirror(origin)
        os.makedirs(os.path.dirname(md), exist_ok=True)
        code = ('import fcntl, sys, time\n'
                "f = open(sys.argv[1], 'a+')\n"
                'fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n'
                "print('ready', flush=True)\n"
                'time.sleep(float(sys.argv[2]))\n')
        proc = subprocess.Popen([sys.executable, '-c', code, md + '@lock', str(seconds)], stdout=subprocess.PIPE,
                                text=True)
        watchdog = threading.Timer(20, proc.kill)         # дочірній завис — не вішати прогін
        watchdog.start()

        def stop():
            watchdog.cancel()
            proc.kill()                                   # лише за PID, без pkill
            proc.wait()
            proc.stdout.close()
        self.addCleanup(stop)
        self.assertEqual(proc.stdout.readline().strip(), 'ready')

    def test_push_and_pull_wait_until_the_other_process_lets_go(self):
        origin = self.bare()
        t = self.target(origin)
        calls = (('push', lambda: self.m.push(self.ctx(), t, self.src(), self.META)),
                 ('pull', lambda: self.m.pull(self.ctx(), t, self.dst())))
        for name, call in calls:
            with self.subTest(op=name), mock.patch.object(self.m, 'LOCK_WAIT', 15):
                self.hold(origin, 0.7)
                t0 = time.monotonic()
                r = call()
                self.assertGreaterEqual(time.monotonic() - t0, 0.4, 'операція не дочекалась звільнення лока')
                self.assertTrue(r.get('pushed') or r.get('found') is not None, r)


class WebLabel(Base):
    def both(self, repo, path='mockup/t1', branch='main'):
        t = {'repo': repo, 'path': path, 'branch': branch}
        return self.m.label_of(t), self.m.web_url(t)

    def test_github_ssh(self):
        self.assertEqual(self.both('git@github.com:o/r.git'),
                         ('GitHub', 'https://github.com/o/r/commits/main/mockup/t1'))

    def test_gitlab_ssh_with_a_port_drops_the_ssh_port(self):
        self.assertEqual(self.both('ssh://git@gitlab.example.test:2222/g/r.git'),
                         ('GitLab', 'https://gitlab.example.test/g/r/-/commits/main/mockup/t1'))

    def test_gitlab_scp_form_and_subgroups(self):
        self.assertEqual(self.both('git@gitlab.internal.example:ORG/sub/r.git', branch='dev'),
                         ('GitLab', 'https://gitlab.internal.example/ORG/sub/r/-/commits/dev/mockup/t1'))

    def test_https_keeps_the_web_port_and_trims_the_dot_git_and_the_slash(self):
        self.assertEqual(self.both('https://gitlab.example.test:8443/g/r.git/'),
                         ('GitLab', 'https://gitlab.example.test:8443/g/r/-/commits/main/mockup/t1'))
        self.assertEqual(self.both('https://user@github.com/o/r'),
                         ('GitHub', 'https://github.com/o/r/commits/main/mockup/t1'))

    def test_the_host_is_compared_in_lower_case(self):
        self.assertEqual(self.both('git@GitHub.com:o/r.git')[0], 'GitHub')

    def test_an_unknown_host_has_no_web_page(self):
        self.assertEqual(self.both('https://git.example.test/o/r'), ('Git', None))
        self.assertEqual(self.both('git@h:o/r.git'), ('Git', None))
        self.assertEqual(self.both('ssh://git@git.example.test/o/r.git'), ('Git', None))

    def test_a_github_look_alike_is_not_github(self):
        self.assertEqual(self.both('git@github.com.evil.test:o/r.git'), ('Git', None))

    def test_local_repos_have_no_web_page(self):
        for repo in ('file:///x/r.git', '/x/r.git', 'file://localhost/x/r.git'):
            with self.subTest(repo=repo):
                self.assertEqual(self.both(repo), ('Git', None))

    def test_a_space_in_the_path_is_encoded(self):
        self.assertEqual(self.both('git@github.com:o/r.git', path='mockup/a b')[1],
                         'https://github.com/o/r/commits/main/mockup/a%20b')
        self.assertEqual(self.both('git@github.com:o/r.git', branch='feature/x')[1],
                         'https://github.com/o/r/commits/feature/x/mockup/t1')


class Catalog(Base):
    """Каталог вбудованих модулів бачить КОЖНУ підтеку `app/modules`: без маніфесту це був би зламаний модуль."""

    def test_the_manifest_is_read_and_the_module_is_ok(self):
        sys.path.insert(0, APP)
        self.addCleanup(sys.path.remove, APP)
        import deai_modules as dm
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        m = dm.catalog()['git-sync']
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual((m.id, m.roles), ('git-sync', ['vcs']))
        self.assertEqual([(s['key'], s['type'], s.get('default')) for s in m.settings],
                         [('repo', 'text', None), ('branch', 'text', 'main'), ('path', 'text', 'mockup/{task}'),
                          ('ssh_key', 'text', None), ('host_ip', 'text', None), ('autosync', 'bool', False)])
        self.assertTrue(callable(m.fn('check')))
        self.assertIn('git-sync', dm.KNOWN_OTHER_MODULES)


class Lock(Base):
    def md(self):
        return os.path.join(self.cache, 'mirrors', 'local', 'x')

    def hold(self, wait=60, hold_for=10):
        """Потік тримає лок, доки не скажуть `release`."""
        held, release = threading.Event(), threading.Event()

        def run():
            with self.m._Lock(self.ctx(), self.md(), wait=wait):
                held.set()
                release.wait(hold_for)
        th = threading.Thread(target=run)
        th.start()
        self.addCleanup(th.join, 5)
        self.addCleanup(release.set)
        self.assertTrue(held.wait(5), 'потік не взяв лок')
        return release, th

    def test_the_second_holder_gets_busy_at_once_and_takes_it_after_the_release(self):
        release, th = self.hold()
        t0 = time.monotonic()
        with self.assertRaises(FakeModuleError) as cm:
            with self.m._Lock(self.ctx(), self.md(), wait=0):
                self.fail('зайнятий лок не мусить віддаватись')
        self.assertEqual(cm.exception.code, 'vcs-busy')
        self.assertLess(time.monotonic() - t0, 0.5)
        release.set()
        th.join(5)
        with self.m._Lock(self.ctx(), self.md(), wait=0):
            pass

    def test_a_wait_of_one_second_waits_and_then_gives_up(self):
        self.hold()
        t0 = time.monotonic()
        with self.assertRaises(FakeModuleError) as cm:
            with self.m._Lock(self.ctx(), self.md(), wait=1):
                pass
        spent = time.monotonic() - t0
        self.assertEqual(cm.exception.code, 'vcs-busy')
        self.assertGreaterEqual(spent, 0.9)
        self.assertLess(spent, 5)

    def test_a_waiter_gets_the_lock_when_it_is_freed_in_time(self):
        release, _ = self.hold()
        threading.Timer(0.4, release.set).start()
        t0 = time.monotonic()
        with self.m._Lock(self.ctx(), self.md(), wait=10):
            pass
        self.assertLess(time.monotonic() - t0, 5)

    def test_a_wait_sleeps_between_the_attempts(self):
        self.hold()
        calls = []
        real = self.m._try_lock

        def counting(fh):
            calls.append(1)
            return real(fh)
        with mock.patch.object(self.m, '_try_lock', counting):
            with self.assertRaises(FakeModuleError):
                with self.m._Lock(self.ctx(), self.md(), wait=1):
                    pass
        self.assertGreaterEqual(len(calls), 2, 'за секунду очікування мусить бути не одна спроба')
        self.assertLessEqual(len(calls), 8, 'очікування крутиться без сну')

    def test_the_lock_file_of_one_repo_is_never_the_mirror_folder_of_another(self):
        """`o/foo` і `o/foo.lock`: файл лока `foo` не може лежати там, де дзеркало `foo.lock`."""
        a = self.m.mirror_dir(self.ctx(), {'repo': 'git@h:o/foo', 'path': 'p'})
        b = self.m.mirror_dir(self.ctx(), {'repo': 'git@h:o/foo.lock', 'path': 'p'})
        os.makedirs(b)
        with self.m._Lock(self.ctx(), a, wait=0):
            pass
        with self.m._Lock(self.ctx(), b, wait=0):
            pass
        flat = self.ctx()
        flat['mirror_flat'] = True
        fa = self.m.mirror_dir(flat, {'repo': 'git@h:o/foo', 'path': 'p'})
        fb = self.m.mirror_dir(flat, {'repo': 'git@h:o/foo.lock', 'path': 'p'})
        os.makedirs(fb)
        with self.m._Lock(flat, fa, wait=0):
            pass

    def test_a_failed_attempt_leaves_no_open_file(self):
        self.hold()
        lk = self.m._Lock(self.ctx(), self.md(), wait=0)
        with self.assertRaises(FakeModuleError):
            lk.__enter__()
        self.assertTrue(lk.fh.closed)

    def test_the_lock_file_sits_next_to_the_mirror_folder_and_the_folder_is_created(self):
        with self.m._Lock(self.ctx(), self.md(), wait=0) as lk:
            self.assertEqual(lk.path, self.md() + '@lock')
            self.assertTrue(os.path.isfile(self.md() + '@lock'))
        self.assertTrue(lk.fh.closed)
        self.assertFalse(os.path.exists(self.md()), 'сам лок дзеркала не створює')

    def test_it_is_released_when_the_body_raises(self):
        with self.assertRaises(ValueError):
            with self.m._Lock(self.ctx(), self.md(), wait=0):
                raise ValueError('boom')
        with self.m._Lock(self.ctx(), self.md(), wait=0):
            pass

    @unittest.skipIf(os.name == 'nt', 'flock між процесами — лише POSIX')
    def test_another_process_holding_the_file_makes_us_busy(self):
        os.makedirs(os.path.dirname(self.md()))
        code = ('import fcntl, sys, time\n'
                "f = open(sys.argv[1], 'a+')\n"
                'fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n'
                "print('ready', flush=True)\n"
                'time.sleep(60)\n')
        proc = subprocess.Popen([sys.executable, '-c', code, self.md() + '@lock'], stdout=subprocess.PIPE, text=True)
        watchdog = threading.Timer(15, proc.kill)      # дочірній не відповів — не вішати прогін
        watchdog.start()

        def stop():
            watchdog.cancel()
            proc.kill()
            proc.wait()
            proc.stdout.close()
        self.addCleanup(stop)
        self.assertEqual(proc.stdout.readline().strip(), 'ready')
        with self.assertRaises(FakeModuleError) as cm:
            with self.m._Lock(self.ctx(), self.md(), wait=0):
                self.fail('лок тримає інший процес')
        self.assertEqual(cm.exception.code, 'vcs-busy')
        proc.kill()
        proc.wait()
        with self.m._Lock(self.ctx(), self.md(), wait=0):       # процес помер — ядро ОС зняло лок
            pass


class SourceShape(unittest.TestCase):
    #: Усе, що `server.py` може імпортувати (exec-иться ядром: без `serve`, ядра, сусідів, `importlib`).
    ALLOWED_IMPORTS = {'fcntl', 'ipaddress', 'msvcrt', 'os', 're', 'shlex', 'shutil', 'subprocess', 'sys', 'tempfile',
                       'time', 'urllib'}

    @classmethod
    def setUpClass(cls):
        with open(SERVER, encoding='utf-8') as f:
            cls.src = f.read()
        cls.tree = ast.parse(cls.src)

    def test_imports_are_an_explicit_stdlib_allowlist(self):
        mods = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, 'відносний імпорт: модуль exec-иться, сусідів нема')
                mods.add((node.module or '').split('.')[0])
        self.assertTrue(mods, 'очікували хоч один імпорт')
        self.assertEqual(mods - self.ALLOWED_IMPORTS, set(), 'імпорт поза списком дозволених')
        self.assertFalse(mods & {'serve', 'deai_modules', 'spaces', 'importlib'})

    def test_no_dynamic_code_or_imports(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(names & {'__import__', 'exec', 'eval', 'compile', 'importlib'}, set())
        self.assertEqual(attrs & {'__import__', 'exec', 'eval', 'import_module', 'system', 'popen'}, set())

    def test_no_file_relative_loading(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn('__file__', names | attrs)
        self.assertNotIn('sys.path', self.src)

    def test_the_functions_of_this_stage_exist(self):
        funcs = {n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'check', 'status', 'push', 'pull', 'validate', 'mirror_dir'} <= funcs)

    def test_no_shell_true_anywhere(self):
        kws = [k for n in ast.walk(self.tree) if isinstance(n, ast.Call) for k in n.keywords if k.arg == 'shell']
        self.assertEqual(kws, [], 'жодного shell=...: git кличеться списком аргументів')


if __name__ == '__main__':
    unittest.main()

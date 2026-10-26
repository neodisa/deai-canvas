"""`app/modules/git-sync` (роль `vcs`, етап 4a): транспорт синку макетів із git.

Модуль вантажиться так само, як його виконує ядро: `exec` у свіжий `types.ModuleType`, без `sys.modules`. Git — СПРАВЖНІЙ,
на локальних bare-репо в тимчасовій теці (абсолютний шлях і `file://`); мережа — лише через підставний `subprocess.run`.
Кожен тест — свій `HOME` у тимчасовій теці: глобальний git-конфіг людини не читається й не пишеться.
"""
import ast
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
        env = {'HOME': self.tmp, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@t',
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

    def test_output_is_decoded_with_replacement(self):
        rec = Recorder((0, ''))
        self.go(rec, self.target())
        self.assertEqual(rec.calls[0][1].get('errors'), 'replace')

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
        self.assertTrue({'check', 'validate', 'mirror_dir'} <= funcs)

    def test_no_shell_true_anywhere(self):
        kws = [k for n in ast.walk(self.tree) if isinstance(n, ast.Call) for k in n.keywords if k.arg == 'shell']
        self.assertEqual(kws, [], 'жодного shell=...: git кличеться списком аргументів')


if __name__ == '__main__':
    unittest.main()

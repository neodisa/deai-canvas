"""Застосування оновлення (0.23.0): передумови, `fetch` тега, `merge --ff-only`, смоук, відкат, перезапуск. УСЕ — на викидних git-світах у
тимчасових теках (remote — шлях файлової системи, мережі нема); `execv` скрізь підроблений; справжні дерева не чіпаються."""
import inspect
import json
import os
import re
import shutil
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
import test_updater as tu  # noqa: E402  (помічники `git`/`make_world`/`commit_version`/`GIT_ENV`)
import updater  # noqa: E402

_REAL = None
OK_APP = 'VALUE = 1\n'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def make_app_world(tmp, version='0.1.0'):
    """`make_world` + `app/serve.py` у кореневому коміті тега v0.1.0 (смоук імпортує `serve`)."""
    remote, work = tu.make_world(tmp, version, tags=())
    os.makedirs(os.path.join(work, 'app'))
    with open(os.path.join(work, 'app', 'serve.py'), 'w') as f:
        f.write(OK_APP)
    tu.git(['add', '--', 'app/serve.py'], work)
    tu.git(['commit', '-m', 'app'], work)
    tu.git(['tag', 'v' + version], work)
    tu.git(['push', 'origin', 'main', '--tags'], work)
    return remote, work


def release(work, version, files=None, tag=None, pkg_version=None):
    """Новий реліз у remote (коміт + тег + push тега), а `work` повертається на попередній коміт (відстаючий користувач)."""
    prev = tu.git(['rev-parse', 'HEAD'], work).strip()
    for rel, body in (files or {}).items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(body)
        tu.git(['add', '--', rel], work)
    tu.commit_version(work, pkg_version or version, tag or 'v' + version)
    tu.git(['push', 'origin', 'refs/tags/' + (tag or 'v' + version)], work)
    tu.git(['tag', '-d', tag or 'v' + version], work)                   # у відстаючого користувача тега ще нема: його принесе fetch
    tu.git(['reset', '--hard', prev], work)


def V(args):
    """Аргументи `git` без ведучих `-c k=v` (дієслово — `V(args)[0]`)."""
    args = list(args)
    while args[:1] == ['-c']:
        args = args[2:]
    return args


def head(work):
    return tu.git(['rev-parse', 'HEAD'], work).strip()


class Base(tu.Base):
    def setUp(self):
        super().setUp()
        hm = os.path.join(self.tmp, 'hm')
        os.makedirs(hm)
        e = mock.patch.dict(os.environ, {'HOME': hm})
        e.start()
        self.addCleanup(e.stop)
        r = mock.patch.object(isolation, 'real_home', lambda home: False)     # жоден мутант не дістанеться справжнього ~/.deai
        r.start()
        self.addCleanup(r.stop)
        self.remote, self.work = make_app_world(self.tmp)

    def counting(self):
        calls = []
        real = updater.run_git
        self.raw = []

        def run(args, cwd, timeout, env_extra=None):
            calls.append(V(args))
            self.raw.append(list(args))
            return real(args, cwd, timeout, env_extra)
        return calls, run

    def ready(self, version='0.2.0', **kw):
        """Реліз у remote + свіжа перевірка → `Updater`, готовий до `apply`."""
        release(self.work, version, **kw.pop('release', {}))
        u = self.upd(self.work, **kw)
        u.check()
        self.assertTrue(u.status()['available'])
        return u

    def assertUntouched(self, old, status_clean=True):
        self.assertEqual(head(self.work), old)
        if status_clean:
            self.assertEqual(tu.git(['status', '--porcelain', '--untracked-files=no'], self.work), '')


class Apply(Base):
    def test_fast_forward_then_restart_not_scheduled_by_apply(self):
        u = self.ready()
        old = head(self.work)
        with mock.patch.object(updater, 'exec_restart') as rs:
            code, body = u.apply()
        self.assertEqual((code, body), (202, {'ok': True, 'to': '0.2.0', 'restart': 'auto'}))
        rs.assert_not_called()                                              # рестарт планує `serve` ПІСЛЯ відповіді
        self.assertEqual(head(self.work), tu.git(['rev-parse', 'v0.2.0^{commit}'], self.work).strip())
        self.assertNotEqual(head(self.work), old)
        self.assertEqual(updater.current_version(self.work), '0.2.0')
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            lu = json.load(f)['last_update']
        self.assertEqual((lu['from'], lu['to']), ('0.1.0', '0.2.0'))
        self.assertIsInstance(lu['at'], int)
        self.assertFalse(u.status()['available'])

    def test_nothing_to_update(self):
        calls, run = self.counting()
        u = self.upd(self.work, run=run)
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'nothing-to-update'}))
        self.assertEqual(calls, [])
        u._save({'latest': '0.1.0', 'state': 'ok'})                           # не новіший за поточну
        self.assertEqual(u.apply()[1]['code'], 'nothing-to-update')
        u._save({'latest': '0.2.0; rm -rf', 'state': 'ok'})                   # не тег → ціль не існує, git не викликано
        self.assertEqual(u.apply()[1]['code'], 'nothing-to-update')
        u._save({'latest': 5})
        self.assertEqual(u.apply()[1]['code'], 'nothing-to-update')
        self.assertEqual(calls, [])

    def test_dirty_blocks_and_changes_nothing(self):
        calls, run = self.counting()
        u = self.ready(run=run)
        old = head(self.work)
        pkg = os.path.join(self.work, 'package.json')
        with open(pkg, 'a') as f:
            f.write(' ')
        with open(pkg, 'rb') as f:
            before = f.read()
        calls.clear()
        code, body = u.apply()
        self.assertEqual((code, body['code']), (409, 'dirty'))
        self.assertEqual(head(self.work), old)
        with open(pkg, 'rb') as f:
            self.assertEqual(f.read(), before)
        self.assertNotIn('fetch', [c[0] for c in calls])
        self.assertNotIn('merge', [c[0] for c in calls])

    def test_untracked_file_does_not_block(self):
        u = self.ready()
        open(os.path.join(self.work, 'junk.txt'), 'w').close()
        self.assertEqual(u.apply()[0], 202)

    def test_detached_and_worktree_and_not_git(self):
        u = self.ready()
        wt = os.path.join(self.tmp, 'wt')
        tu.git(['worktree', 'add', '-b', 'side', wt], self.work)
        uw = self.upd(wt)
        uw._save({'latest': '0.2.0', 'state': 'ok'})
        self.assertEqual(uw.apply(), (409, {'ok': False, 'code': 'worktree'}))
        old = head(self.work)
        tu.git(['checkout', '--detach'], self.work)
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'detached'}))
        self.assertEqual(head(self.work), old)
        plain = os.path.join(self.tmp, 'plain')
        os.makedirs(plain)
        tu.write_pkg(plain, '0.1.0')
        pu = self.upd(plain)
        pu._save({'latest': '0.2.0', 'state': 'ok'})
        self.assertEqual(pu.apply(), (409, {'ok': False, 'code': 'not-git'}))

    def test_busy_blocks(self):
        calls, run = self.counting()
        u = self.ready(run=run, busy=lambda: 'shooting')
        old = head(self.work)
        calls.clear()
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'busy'}))
        self.assertUntouched(old)
        self.assertNotIn('fetch', [c[0] for c in calls])

    def test_diverged_local_commit(self):
        u = self.ready()
        with open(os.path.join(self.work, 'local.txt'), 'w') as f:
            f.write('mine')
        tu.git(['add', '--', 'local.txt'], self.work)
        tu.git(['commit', '-m', 'local'], self.work)
        old = head(self.work)
        calls, run = self.counting()
        u.run = run
        code, body = u.apply()
        self.assertEqual((code, body['code'], body['hint']), (409, 'diverged', 'merge-hint'))
        self.assertEqual(head(self.work), old)
        self.assertNotIn('merge', [c[0] for c in calls])
        self.assertNotIn(self.tmp, json.dumps(body))
        self.assertTrue(os.path.exists(os.path.join(self.work, 'local.txt')))

    def test_offline_fetch_fails_changes_nothing(self):
        calls, run = self.counting()
        u = self.ready(run=run)
        old = head(self.work)
        shutil.rmtree(self.remote)
        calls.clear()
        code, body = u.apply()
        self.assertEqual((code, body['code']), (503, 'offline'))
        self.assertUntouched(old)
        self.assertEqual([c[0] for c in calls if c[0] in ('merge', 'reset')], [])

    def test_tag_conflict(self):
        calls, run = self.counting()
        u = self.ready(run=run)
        old = head(self.work)
        tu.git(['tag', 'v0.2.0', old], self.work)                           # локальний v0.2.0 на ІНШОМУ коміті
        calls.clear()
        code, body = u.apply()
        self.assertEqual((code, body['code']), (409, 'tag-conflict'))
        self.assertUntouched(old)
        self.assertEqual([c[0] for c in calls if c[0] in ('merge', 'reset')], [])

    def test_tag_missing_in_remote(self):
        u = self.ready()
        tu.git(['--git-dir', self.remote, 'tag', '-d', 'v0.2.0'], self.work)
        old = head(self.work)
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'tag-missing'}))
        self.assertUntouched(old)

    def test_tag_whose_package_json_says_another_version_is_refused(self):
        """Тег `v0.2.0` в remote ЗАРАЗ указує на коміт з `package.json` іншої версії → нічого не зливається."""
        calls, run = self.counting()
        u = self.ready(run=run, release={'pkg_version': '0.3.0'})
        old = head(self.work)
        calls.clear()
        code, body = u.apply()
        self.assertEqual((code, body['code']), (409, 'tag-mismatch'))
        self.assertUntouched(old)
        self.assertEqual([c[0] for c in calls if c[0] in ('merge', 'reset')], [])

    def test_remote_is_resolved_at_apply_time_not_from_the_stored_state(self):
        """Після `check` origin перемкнули на інший remote, де той самий тег — з іншим вмістом → береться ЦЕЙ remote й тег відхиляється."""
        u = self.ready()
        other_remote = os.path.join(self.tmp, 'other.git')
        other_work = os.path.join(self.tmp, 'other')
        tu.git(['init', '--bare', '-b', 'main', other_remote])
        tu.git(['clone', other_remote, other_work])
        tu.git(['checkout', '-B', 'main'], other_work)
        tu.commit_version(other_work, '0.5.0', 'v0.2.0')
        tu.git(['push', 'origin', 'main', '--tags'], other_work)
        old = head(self.work)
        tu.git(['remote', 'set-url', 'origin', other_remote], self.work)
        code, body = u.apply()
        self.assertEqual((code, body['code']), (409, 'tag-mismatch'))
        self.assertUntouched(old)
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': 'bad remote; x'}):
            self.assertEqual(u.apply()[1]['code'], 'bad-remote')

    def test_remote_env_override_is_honoured_at_apply_time(self):
        """`DEAI_UPDATE_REMOTE` на ЦЬОМУ виклику перекриває origin: fetch іде з нього (а не з якогось «origin» чи збереженого)."""
        u = self.ready()
        other_remote = os.path.join(self.tmp, 'other2.git')
        other_work = os.path.join(self.tmp, 'other2')
        tu.git(['init', '--bare', '-b', 'main', other_remote])
        tu.git(['clone', other_remote, other_work])
        tu.git(['checkout', '-B', 'main'], other_work)
        tu.commit_version(other_work, '0.5.0', 'v0.2.0')
        tu.git(['push', 'origin', 'main', '--tags'], other_work)
        old = head(self.work)
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': other_remote}):
            code, body = u.apply()
        self.assertEqual((code, body['code']), (409, 'tag-mismatch'))
        self.assertEqual(head(self.work), old)

    def test_ff_only_is_enforced_even_if_history_moves_after_the_ancestor_check(self):
        """Між `merge-base` і `merge` зʼявився локальний коміт: `--ff-only` відмовляє; HEAD чужий → `error`, без reset і без merge-коміту."""
        ident = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'}
        u = self.ready()
        real = updater.run_git
        seen = []

        def run(args, cwd, timeout, env_extra=None):
            r = real(args, cwd, timeout, env_extra)
            if V(args)[0] == 'merge-base':
                with open(os.path.join(self.work, 'late.txt'), 'w') as f:
                    f.write('late')
                tu.git(['add', '--', 'late.txt'], self.work)
                tu.git(['commit', '-m', 'late'], self.work)
            if V(args)[0] == 'merge':
                seen.append(V(args))
            return r
        u.run = run
        with mock.patch.dict(os.environ, ident):
            code, body = u.apply()
        self.assertEqual((code, body['code']), (500, 'error'))
        self.assertTrue(os.path.exists(os.path.join(self.work, 'late.txt')))
        self.assertEqual(seen[0][:2], ['merge', '--ff-only'])
        self.assertTrue(re.match(r'^[0-9a-f]{40}$', seen[0][2]))
        self.assertEqual(tu.git(['rev-list', '--merges', 'HEAD'], self.work), '')

    def test_network_remote_is_refused_when_isolated(self):
        calls, run = self.counting()
        u = self.ready(run=run)
        tu.git(['remote', 'set-url', 'origin', 'https://git.example/o/r.git'], self.work)
        old = head(self.work)
        calls.clear()
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'disabled'}))
        self.assertNotIn('fetch', [c[0] for c in calls])
        self.assertEqual(head(self.work), old)

    def test_smoke_failure_rolls_back_to_old_head(self):
        u = self.ready(release={'files': {'app/x.py': 'def broken(:\n'}})
        old = head(self.work)
        calls, run = self.counting()
        u.run = run
        code, body = u.apply()
        self.assertEqual((code, body), (500, {'ok': False, 'code': 'rolled-back'}))
        self.assertUntouched(old)
        self.assertFalse(os.path.exists(os.path.join(self.work, 'app', 'x.py')))
        self.assertEqual(updater.current_version(self.work), '0.1.0')
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            self.assertNotIn('last_update', json.load(f))

    def test_smoke_failure_import_error_also_rolls_back(self):
        u = self.ready(release={'files': {'app/serve.py': 'import nonexistent_module_xyz\n'}})
        old = head(self.work)
        self.assertEqual(u.apply()[1]['code'], 'rolled-back')
        self.assertUntouched(old)
        with open(os.path.join(self.work, 'app', 'serve.py')) as f:
            self.assertEqual(f.read(), OK_APP)

    def test_rollback_resets_only_to_the_recorded_head(self):
        """Єдиний `reset` — `--hard <старий sha>` і лише ПІСЛЯ успішного merge; у вдалому оновленні `reset` нема зовсім."""
        u = self.ready(release={'files': {'app/x.py': 'def broken(:\n'}})
        old = head(self.work)
        calls, run = self.counting()
        u.run = run
        self.assertEqual(u.apply()[1]['code'], 'rolled-back')
        resets = [i for i, c in enumerate(calls) if c[0] == 'reset']
        self.assertIn(['-c', 'gc.auto=0', 'reset', '--hard', old], self.raw)
        merges = [i for i, c in enumerate(calls) if c[0] == 'merge']
        self.assertEqual([calls[i] for i in resets], [['reset', '--hard', old]])
        self.assertEqual(len(merges), 1)
        self.assertGreater(resets[0], merges[0])
        self.assertTrue(re.match(r'^[0-9a-f]{40}$', old))
        # успіх: жодного reset
        shutil.rmtree(self.tmp + '/w2', ignore_errors=True)
        u2 = self.ready_fresh('0.3.0')
        calls2, run2 = self.counting()
        u2.run = run2
        self.assertEqual(u2.apply()[0], 202)
        self.assertEqual([c for c in calls2 if c[0] == 'reset'], [])

    def ready_fresh(self, version):
        """Другий, чистий світ у своїй теці (щоб не залежати від стану першого)."""
        d = os.path.join(self.tmp, 'w2')
        os.makedirs(d)
        _, work = make_app_world(d)
        release(work, version)
        u = self.upd(work, home=lambda: os.path.join(d, 'home'))
        u.check()
        return u

    def test_rollback_failure_is_reported_as_such(self):
        u = self.ready(release={'files': {'app/x.py': 'def broken(:\n'}})
        real = updater.run_git

        def run(args, cwd, timeout, env_extra=None):
            if V(args)[0] == 'reset':
                return 1, '', 'nope'
            return real(args, cwd, timeout, env_extra)
        u.run = run
        self.assertEqual(u.apply()[1]['code'], 'rollback-failed')

    def test_merge_failure_does_not_trigger_a_rollback(self):
        u = self.ready()
        real = updater.run_git
        calls = []

        def run(args, cwd, timeout, env_extra=None):
            calls.append(V(args)[0])
            if V(args)[0] == 'merge':
                return 1, '', 'refused'
            return real(args, cwd, timeout, env_extra)
        u.run = run
        old = head(self.work)
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'merge-failed'}))
        self.assertNotIn('reset', calls)
        self.assertEqual(head(self.work), old)

    def test_fetch_and_merge_argv_are_hardened(self):
        calls, run = self.counting()
        u = self.ready(run=run)
        self.assertEqual(u.apply()[0], 202)
        fetch = [a for a in self.raw if V(a)[0] == 'fetch'][0]
        self.assertEqual(fetch[:6], ['-c', 'transfer.fsckObjects=true', '-c', 'fetch.fsckObjects=true', '-c', 'gc.auto=0'])
        for flag in ('--no-tags', '--no-recurse-submodules', '--'):
            self.assertIn(flag, fetch)
        self.assertLess(fetch.index('--'), len(fetch) - 2)
        merge = [a for a in self.raw if V(a)[0] == 'merge'][0]
        self.assertEqual(merge[:4], ['-c', 'gc.auto=0', 'merge', '--ff-only'])

    def _merge_scenario(self, merge_effect):
        """`merge` підроблено: `merge_effect(old, target)` міняє дерево/HEAD і повертає rc; решта git — справжній."""
        u = self.ready()
        old = head(self.work)
        target = tu.git(['--git-dir', self.remote, 'rev-parse', 'v0.2.0^{commit}'], self.work).strip()
        real = updater.run_git
        verbs = []

        def run(args, cwd, timeout, env_extra=None):
            v = V(args)
            verbs.append(v)
            if v[0] == 'merge':
                return merge_effect(old, target), '', ''
            return real(args, cwd, timeout, env_extra)
        u.run = run
        return u, old, target, verbs

    def test_merge_killed_after_dirtying_the_tree_rolls_back(self):
        def effect(old, target):
            with open(os.path.join(self.work, 'package.json'), 'a') as f:
                f.write(' ')
            return 124
        u, old, target, verbs = self._merge_scenario(effect)
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'rolled-back'}))
        self.assertEqual([v for v in verbs if v[0] == 'reset'], [['reset', '--hard', old]])
        self.assertUntouched(old)

    def test_edit_saved_during_fetch_blocks_the_merge_and_survives(self):
        u = self.ready()
        old = head(self.work)
        real = updater.run_git
        verbs = []
        pkg = os.path.join(self.work, 'package.json')

        def run(args, cwd, timeout, env_extra=None):
            v = V(args)
            verbs.append(v[0])
            r = real(args, cwd, timeout, env_extra)
            if v[0] == 'fetch':
                with open(pkg, 'a') as f:
                    f.write('\n// my edit\n')
            return r
        u.run = run
        with open(pkg, 'rb') as f:
            before = f.read()
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'dirty'}))
        self.assertNotIn('merge', verbs)
        self.assertNotIn('reset', verbs)
        with open(pkg, 'rb') as f:
            self.assertEqual(f.read(), before + b'\n// my edit\n')
        self.assertEqual(head(self.work), old)

    def test_refused_merge_with_a_users_edit_never_resets_it(self):
        pkg = os.path.join(self.work, 'package.json')

        def effect(old, target):
            with open(pkg, 'a') as f:
                f.write('\n// my edit\n')
            return 1                                       # ff-only відмовив атомарно: «local changes would be overwritten»
        u, old, target, verbs = self._merge_scenario(effect)
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'merge-failed'}))
        self.assertEqual([v for v in verbs if v[0] == 'reset'], [])
        with open(pkg) as f:
            self.assertTrue(f.read().endswith('\n// my edit\n'))
        self.assertEqual(head(self.work), old)

    def test_fetch_rejected_by_fsck_is_its_own_code(self):
        u = self.ready()
        real = updater.run_git
        verbs = []

        def run(args, cwd, timeout, env_extra=None):
            verbs.append(V(args)[0])
            if V(args)[0] == 'fetch':
                return 128, '', 'error: object 1234: badTimezone: invalid author/committer line\nfatal: fsck error in packed object'
            return real(args, cwd, timeout, env_extra)
        u.run = run
        old = head(self.work)
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'fetch-rejected'}))
        self.assertNotIn('merge', verbs)
        self.assertEqual(head(self.work), old)

    def test_a_new_successful_apply_clears_restart_failed(self):
        u = self.ready()
        u.mark_restart_failed()
        self.assertTrue(u.status()['restart_failed'])
        self.assertEqual(u.apply()[0], 202)
        self.assertFalse(u.status()['restart_failed'])
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            self.assertNotIn('restart_failed', json.load(f))

    def test_merge_that_moved_head_then_failed_rolls_back(self):
        def effect(old, target):
            tu.git(['reset', '--hard', target], self.work)
            return 1
        u, old, target, verbs = self._merge_scenario(effect)
        self.assertEqual(u.apply()[1]['code'], 'rolled-back')
        self.assertEqual([v for v in verbs if v[0] == 'reset'], [['reset', '--hard', old]])
        self.assertUntouched(old)

    def test_merge_that_fails_cleanly_is_merge_failed_without_reset(self):
        u, old, target, verbs = self._merge_scenario(lambda old, target: 1)
        self.assertEqual(u.apply()[1]['code'], 'merge-failed')
        self.assertEqual([v for v in verbs if v[0] == 'reset'], [])
        self.assertUntouched(old)

    def test_merge_failure_with_unexpected_head_is_error_without_reset(self):
        def effect(old, target):
            with open(os.path.join(self.work, 'other.txt'), 'w') as f:
                f.write('x')
            tu.git(['add', '--', 'other.txt'], self.work)
            tu.git(['commit', '-m', 'someone else'], self.work)
            return 1
        u, old, target, verbs = self._merge_scenario(effect)
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'error'}))
        self.assertEqual([v for v in verbs if v[0] == 'reset'], [])
        self.assertNotEqual(head(self.work), old)                          # чужий коміт не чіпали
        self.assertTrue(os.path.exists(os.path.join(self.work, 'other.txt')))

    def test_failed_rollback_after_merge_failure_is_rollback_failed(self):
        def effect(old, target):
            with open(os.path.join(self.work, 'package.json'), 'a') as f:
                f.write(' ')
            return 124
        u, old, target, verbs = self._merge_scenario(effect)
        inner = u.run

        def run(args, cwd, timeout, env_extra=None):
            if V(args)[0] == 'reset':
                return 1, '', 'index.lock'
            return inner(args, cwd, timeout, env_extra)
        u.run = run
        self.assertEqual(u.apply()[1]['code'], 'rollback-failed')

    def test_last_update_save_failure_still_succeeds(self):
        u = self.ready()

        def boom(state):
            raise OSError('disk')
        u._save = boom
        self.assertEqual(u.apply(), (202, {'ok': True, 'to': '0.2.0', 'restart': 'auto'}))

    def test_garbage_head_never_reaches_merge_or_reset(self):
        """`old` — 40-hex sha, перевірений регексом, ДО fetch/merge: що завгодно інше — `500 error`, і жодного запису в дерево."""
        u = self.ready()
        real = updater.run_git
        calls = []

        def run(args, cwd, timeout, env_extra=None):
            calls.append(V(args)[0])
            if args[:2] == ['rev-parse', '--verify'] and args[2] == 'HEAD':
                return 0, '--hard\n', ''
            return real(args, cwd, timeout, env_extra)
        u.run = run
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'error'}))
        for forbidden in ('fetch', 'merge', 'reset'):
            self.assertNotIn(forbidden, calls)

    def test_the_module_has_exactly_one_reset(self):
        src = inspect.getsource(updater)
        self.assertEqual(len(re.findall(r"'reset'", src)), 1)          # одне місце — `_rollback`
        self.assertEqual(len(re.findall(r"self\._rollback\(", src)), 2)  # викликається з двох місць, власного reset нема
        self.assertEqual(len(re.findall(r"'--hard'", src)), 1)

    def test_target_comes_from_state_not_request(self):
        """`apply` нічого не приймає ззовні; ціль — лише `latest` зі стану (HTTP-шар перевіряє те саме з тілом запиту)."""
        self.assertEqual(list(inspect.signature(updater.Updater.apply).parameters), ['self'])
        u = self.ready('0.2.0')
        self.assertEqual(u.apply()[1]['to'], '0.2.0')

    def test_second_apply_while_running_is_busy(self):
        u = self.ready()
        real = updater.run_git
        inside, release_it = threading.Event(), threading.Event()

        def run(args, cwd, timeout, env_extra=None):
            if V(args)[0] == 'fetch':
                inside.set()
                release_it.wait(10)
            return real(args, cwd, timeout, env_extra)
        u.run = run
        out = []
        t = threading.Thread(target=lambda: out.append(u.apply()))
        t.start()
        self.assertTrue(inside.wait(10))
        self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'busy'}))
        release_it.set()
        t.join(30)
        self.assertEqual(out[0][0], 202)

    def test_isolated_process_refuses_apply_on_product_root_without_the_seam(self):
        calls = []

        def run(args, cwd, timeout, env_extra=None):
            calls.append(args)
            return 1, '', 'x'
        u = self.upd(self.work, run=run)
        u._save({'latest': '0.2.0', 'state': 'ok'})
        iso = {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}
        with mock.patch.object(updater, 'PRODUCT_ROOT', self.work), mock.patch.dict(os.environ, iso):
            self.assertEqual(u.apply(), (409, {'ok': False, 'code': 'isolated'}))
            self.assertEqual(calls, [], 'git не викликався')
            with mock.patch.dict(os.environ, {'DEAI_UPDATE_TEST_APPLY': '1'}):
                code, body = u.apply()
                self.assertNotEqual(body.get('code'), 'isolated')
                self.assertTrue(calls, 'із швом дійшло до git')
        calls.clear()
        # інший корінь (викидний) в ізольованому прогоні — не відсікається
        with mock.patch.object(updater, 'PRODUCT_ROOT', os.path.join(self.tmp, 'elsewhere')), mock.patch.dict(os.environ, iso):
            u.apply()
            self.assertTrue(calls)

    def test_not_isolated_process_on_product_root_is_not_refused_by_the_gate(self):
        calls = []
        u = self.upd(self.work, run=lambda a, c, t, e=None: (calls.append(a), (1, '', ''))[1])
        u._save({'latest': '0.2.0', 'state': 'ok'})
        with mock.patch.object(updater, 'PRODUCT_ROOT', self.work):
            self.assertNotEqual(u.apply()[1].get('code'), 'isolated')

    def test_no_pyc_written_by_the_smoke(self):
        u = self.ready(release={'files': {'app/helper.py': 'X = 2\n'}})
        self.assertEqual(u.apply()[0], 202)
        found = [os.path.join(d, f) for d, ds, fs in os.walk(self.work) if '.git' not in d.split(os.sep)
                 for f in fs + ds if f.endswith('.pyc') or f == '__pycache__']
        self.assertEqual(found, [])

    def test_apply_never_raises(self):
        u = self.ready()

        def boom(*a, **k):
            raise RuntimeError('x')
        u.run = boom
        self.assertEqual(u.apply(), (500, {'ok': False, 'code': 'error'}))


class Smoke(Base):
    def _tree(self, serve_src, name='tree'):
        root = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(root, 'app'))
        os.makedirs(os.path.join(root, 'bin'))
        with open(os.path.join(root, 'app', 'serve.py'), 'w') as f:
            f.write(serve_src)
        return root

    def test_good_tree_passes_and_bad_syntax_in_bin_fails(self):
        root = self._tree(OK_APP)
        self.assertTrue(updater.smoke_check(root))
        with open(os.path.join(root, 'bin', 'x.py'), 'w') as f:
            f.write('def (:\n')
        self.assertFalse(updater.smoke_check(root))

    def test_child_env_is_scrubbed_and_isolated_and_cleaned_up(self):
        root = self._tree(OK_APP)
        seen = {}

        def fake(argv, cwd, env, timeout):
            seen.update(argv=argv, cwd=cwd, env=env, timeout=timeout)
            seen['exists_during'] = os.path.isdir(env['HOME'])
            return 0, '', ''
        parent = {'PYTHONPATH': '/poison', 'DEAI_HOME': '/real/deai', 'DC_TASKS_FILE': '/real/tasks.json', 'GIT_DIR': '/x',
                  'DEAI_UPDATE_REMOTE': 'zzz', 'SECRET_TOKEN': 'abc'}
        with mock.patch.object(updater, '_communicate', fake), mock.patch.dict(os.environ, parent):
            self.assertTrue(updater.smoke_check(root))
        env = seen['env']
        self.assertNotIn('PYTHONPATH', env)
        for leaked in ('GIT_DIR', 'DEAI_UPDATE_REMOTE', 'SECRET_TOKEN'):
            self.assertNotIn(leaked, env)
        tmp_prefix = os.path.realpath(tempfile.gettempdir())
        for k in ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE'):
            self.assertTrue(os.path.realpath(env[k]).startswith(tmp_prefix), k)
            self.assertNotIn('/real/', env[k])
        self.assertEqual((env['DEAI_NO_UPDATE_CHECK'], env['PYTHONDONTWRITEBYTECODE']), ('1', '1'))
        self.assertIn('-B', seen['argv'])
        self.assertIn('-I', seen['argv'])
        self.assertEqual((seen['cwd'], seen['timeout']), (root, 30))
        self.assertTrue(seen['exists_during'])
        self.assertFalse(os.path.exists(env['HOME']), 'тимчасові теки видалено')
        self.assertEqual(updater.SMOKE_TIMEOUT_S, 30)

    def test_child_does_not_inherit_the_parents_path_or_home_or_cwd_for_real(self):
        poison = os.path.join(self.tmp, 'poison')
        os.makedirs(poison)
        with open(os.path.join(poison, 'evilmod_xyz.py'), 'w') as f:
            f.write('X = 1\n')
        root = self._tree('import evilmod_xyz\n')
        with mock.patch.dict(os.environ, {'PYTHONPATH': poison}), mock.patch.object(sys, 'path', sys.path + [poison]):
            self.assertFalse(updater.smoke_check(root), 'дитина побачила sys.path/PYTHONPATH батька')
        probe = ('import os\nassert os.environ["HOME"] != %r\nassert os.environ["DEAI_HOME"] != %r\n'
                 'assert os.environ["DC_TASKS_FILE"].endswith("tasks.json")\nassert os.environ["DEAI_NO_UPDATE_CHECK"] == "1"\n'
                 'assert os.path.realpath(os.getcwd()) == %r\nassert "PYTHONPATH" not in os.environ\n'
                 'import sys\nassert not any("poison" in p for p in sys.path)\n')
        root2 = self._tree(probe % (os.environ['HOME'], '/real/deai', os.path.realpath(os.path.join(self.tmp, 'tree2'))), 'tree2')
        with mock.patch.dict(os.environ, {'PYTHONPATH': poison, 'DEAI_HOME': '/real/deai'}):
            self.assertTrue(updater.smoke_check(root2))

    def test_timeout_kills_the_child(self):
        root = self._tree('import time\ntime.sleep(30)\n')
        with mock.patch.object(updater, 'SMOKE_TIMEOUT_S', 1):
            self.assertFalse(updater.smoke_check(root))

    def test_smoke_is_not_py_compile(self):
        src = inspect.getsource(updater)
        for needle in ('import py_compile', 'py_compile.compile', "'py_compile'", 'compileall'):
            self.assertNotIn(needle, src)


class Restart(Base):
    def setUp(self):
        super().setUp()
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        s = mock.patch.object(updater, '_RESTART_SNAPSHOT', None)
        s.start()
        self.addCleanup(s.stop)

    def test_exec_restart_uses_snapshot_cwd_and_argv(self):
        got = {}
        snap_cwd = os.path.join(self.tmp, 'launch')
        os.makedirs(snap_cwd)
        snap = {'cwd': snap_cwd, 'argv': [sys.executable, '-B', 'app/serve.py']}

        def fake(path, argv):
            got.update(path=path, argv=argv, cwd=os.path.realpath(os.getcwd()))
        self.assertFalse(updater.exec_restart(snap, execv=fake))           # підробний execv повертається → False
        self.assertEqual(got['path'], sys.executable)
        self.assertEqual(got['argv'], [sys.executable, '-B', 'app/serve.py'])
        self.assertEqual(got['cwd'], os.path.realpath(snap_cwd))

    def test_snapshot_taken_before_chdir_and_argv_from_orig_argv(self):
        start = os.path.join(self.tmp, 'start')
        os.makedirs(start)
        os.chdir(start)
        with mock.patch.object(sys, 'orig_argv', ['python3', '-B', 'app/serve.py'], create=True):
            snap = updater.snapshot_restart()
        self.assertEqual(snap, {'cwd': os.getcwd(), 'argv': [sys.executable, '-B', 'app/serve.py']})
        os.chdir(self.tmp)                                                  # хтось змінив cwd після старту
        got = {}
        updater.exec_restart(execv=lambda p, a: got.update(cwd=os.path.realpath(os.getcwd())))
        self.assertEqual(got['cwd'], os.path.realpath(start))

    def test_snapshot_falls_back_to_sys_argv_without_orig_argv(self):
        with mock.patch.object(sys, 'orig_argv', None, create=True), mock.patch.object(sys, 'argv', ['app/serve.py']):
            self.assertEqual(updater.snapshot_restart()['argv'], [sys.executable, 'app/serve.py'])

    def test_exec_restart_refused_when_isolated_without_the_seam(self):
        called = []
        snap = {'cwd': self.tmp, 'argv': [sys.executable, 'x']}
        iso = {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}
        with mock.patch.dict(os.environ, iso):
            self.assertFalse(updater.exec_restart(snap, execv=lambda *a: called.append(a)))
            self.assertEqual(called, [])
            with mock.patch.dict(os.environ, {'DEAI_UPDATE_TEST_APPLY': '1'}):
                updater.exec_restart(snap, execv=lambda *a: called.append(a))
        self.assertEqual(len(called), 1)

    def test_windows_is_manual(self):
        called = []
        snap = {'cwd': self.tmp, 'argv': [sys.executable, 'x']}
        with mock.patch.object(updater, '_is_windows', lambda: True):
            self.assertFalse(updater.exec_restart(snap, execv=lambda *a: called.append(a)))
            u = self.ready()
            self.assertEqual(u.apply(), (202, {'ok': True, 'to': '0.2.0', 'restart': 'manual'}))
        self.assertEqual(called, [])

    def test_no_snapshot_means_no_restart(self):
        called = []
        self.assertFalse(updater.exec_restart(execv=lambda *a: called.append(a)))
        self.assertEqual(called, [])

    def test_failing_execv_restores_cwd_and_returns_false(self):
        here = os.path.realpath(os.getcwd())
        snap = {'cwd': self.tmp, 'argv': [sys.executable]}

        def boom(*a):
            raise OSError('no')
        self.assertFalse(updater.exec_restart(snap, execv=boom))
        self.assertEqual(os.path.realpath(os.getcwd()), here)


if __name__ == '__main__':
    unittest.main()

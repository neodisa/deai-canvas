"""Stop-хук Claude Code простору (23.11.2026): `app/claude_hook.py` пише ОДНУ нашу групу в `hooks.Stop` файла
`<простір>/.claude/settings.local.json` — злиттям, атомарно, не чіпаючи чужого. Усе — у тимчасових теках; «домівка» підмінена
(`_home`), тож тести не залежать від справжнього HOME, а ні `~/.claude`, ні мережі не чіпають."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
import claude_hook  # noqa: E402

PORT = 8765
OTHER = 9911
LINE = '/.claude/settings.local.json'


def _put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))


def _get(path):
    with open(path, 'rb') as f:
        return f.read()


def _json(path):
    return json.loads(_get(path).decode('utf-8'))


def _ours(port=PORT):
    return {'type': 'command', 'timeout': 10, 'command': claude_hook.command(port)}


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='claude-hook-'))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.space = os.path.join(self.root, 'space')
        os.makedirs(self.space)
        self.dir = os.path.join(self.space, '.claude')
        self.f = os.path.join(self.dir, 'settings.local.json')
        for patcher in (mock.patch.object(claude_hook, '_home', return_value=self.root),
                        mock.patch.object(claude_hook, '_WINDOWS', False)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def state(self, port=PORT):
        return claude_hook.status(self.space, port)['state']

    def tmp_files(self):
        return [n for n in os.listdir(self.dir) if n.endswith('.tmp')] if os.path.isdir(self.dir) else []

    def racing(self, mutate):
        """Підмінює читання так, що ПЕРЕД повторною звіркою (тимчасовий файл уже лежить) хтось змінює файл."""
        real = claude_hook._read_raw
        done = []

        def wrapper(space_dir):
            d = os.path.join(space_dir, '.claude')
            if not done and os.path.isdir(d) and any(n.endswith('.tmp') for n in os.listdir(d)):
                done.append(1)
                mutate()
            return real(space_dir)
        return mock.patch.object(claude_hook, '_read_raw', wrapper)


class Command(Base):
    def test_the_command_is_the_documented_one_with_the_mark_last(self):
        self.assertEqual(
            claude_hook.command(8765),
            "curl -s --noproxy '*' --max-time 5 -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary @- "
            "http://127.0.0.1:8765/api/autosync || true # deai-autosync")
        self.assertTrue(claude_hook.command(1).endswith(claude_hook.HOOK_MARK))
        self.assertEqual(claude_hook.HOOK_MARK, '# deai-autosync')
        self.assertEqual(claude_hook.FILE, '.claude/settings.local.json')

    def test_the_port_must_be_a_number(self):
        with self.assertRaises(ValueError):
            claude_hook.command('8765; rm -rf x')
        self.assertIn(':4317/', claude_hook.command('4317'))


class Status(Base):
    def test_no_file_is_missing_and_status_writes_nothing(self):
        self.assertEqual(claude_hook.status(self.space, PORT), {'state': 'missing', 'path': self.f})
        self.assertFalse(os.path.exists(self.dir))

    def test_a_file_without_our_group_is_missing(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo hi'}]}]}}))
        self.assertEqual(self.state(), 'missing')

    def test_our_command_for_the_current_port_is_ok_for_another_it_is_stale(self):
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.state(PORT), 'ok')
        self.assertEqual(self.state(OTHER), 'stale')

    def test_the_mark_with_an_old_command_is_stale(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'curl old # deai-autosync'}]}]}}))
        self.assertEqual(self.state(), 'stale')

    def test_two_copies_are_stale_and_connect_collapses_them(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [_ours(OTHER)]}, {'hooks': [_ours(PORT)]}]}}))
        self.assertEqual(self.state(), 'stale')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.state(), 'ok')
        self.assertEqual(_json(self.f)['hooks']['Stop'], [{'hooks': [_ours(PORT)]}])

    def test_status_never_raises(self):
        with mock.patch.object(claude_hook, '_read_raw', side_effect=RuntimeError('boom')):
            self.assertEqual(claude_hook.status(self.space, PORT)['state'], 'unreadable')


class Connect(Base):
    def test_creates_the_folder_and_the_file(self):
        st = claude_hook.connect(self.space, PORT)
        self.assertEqual(st, {'state': 'ok', 'path': self.f})
        doc = _json(self.f)
        self.assertEqual(doc, {'hooks': {'Stop': [{'hooks': [_ours()]}]}})
        self.assertEqual(_get(self.f).decode('utf-8'), json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
        self.assertEqual(self.tmp_files(), [])

    def test_an_empty_object_gets_the_hook(self):
        _put(self.f, '{}')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_json(self.f), {'hooks': {'Stop': [{'hooks': [_ours()]}]}})

    def test_foreign_hooks_and_other_keys_survive_by_content(self):
        foreign = {'permissions': {'allow': ['Bash(ls)']}, 'env': {'A': 'б'},
                   'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'echo pre'}]}],
                             'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}
        _put(self.f, json.dumps(foreign))
        claude_hook.connect(self.space, PORT)
        doc = _json(self.f)
        self.assertEqual(doc['permissions'], foreign['permissions'])
        self.assertEqual(doc['env'], foreign['env'])
        self.assertEqual(doc['hooks']['PreToolUse'], foreign['hooks']['PreToolUse'])
        self.assertEqual(doc['hooks']['Stop'][0], foreign['hooks']['Stop'][0])
        self.assertEqual(doc['hooks']['Stop'][1], {'hooks': [_ours()]})
        self.assertEqual(len(doc['hooks']['Stop']), 2)
        self.assertIn('"б"', _get(self.f).decode('utf-8'), 'ensure_ascii=False')

    def test_a_stale_hook_is_rewritten_with_the_new_port(self):
        claude_hook.connect(self.space, OTHER)
        self.assertEqual(self.state(PORT), 'stale')
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')
        self.assertEqual(_json(self.f)['hooks']['Stop'], [{'hooks': [_ours(PORT)]}])

    def test_connecting_again_writes_nothing(self):
        claude_hook.connect(self.space, PORT)
        before, ino = _get(self.f), os.stat(self.f).st_ino
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')
        self.assertEqual(_get(self.f), before)
        self.assertEqual(os.stat(self.f).st_ino, ino, 'файл не переписувався')

    def test_a_group_that_mixes_our_and_a_foreign_hook_keeps_the_foreign_one(self):
        mixed = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo keep'}, _ours(OTHER)]}]}}
        _put(self.f, json.dumps(mixed))
        claude_hook.connect(self.space, PORT)
        stop = _json(self.f)['hooks']['Stop']
        self.assertEqual(stop[0], {'hooks': [{'type': 'command', 'command': 'echo keep'}]})
        self.assertEqual(stop[1], {'hooks': [_ours(PORT)]})

    def test_the_mode_of_an_existing_file_is_kept(self):
        _put(self.f, '{}')
        os.chmod(self.f, 0o600)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(stat.S_IMODE(os.stat(self.f).st_mode), 0o600)

    def test_a_new_file_follows_the_umask(self):
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(stat.S_IMODE(os.stat(self.f).st_mode), 0o644)

    def test_a_change_between_read_and_replace_is_refused_and_leaves_their_file(self):
        _put(self.f, '{"a": 1}')

        def mutate():
            _put(self.f, '{"a": 2}')
        with self.racing(mutate):
            with self.assertRaises(ValueError) as cm:
                claude_hook.connect(self.space, PORT)
        self.assertEqual(str(cm.exception), 'changed')
        self.assertEqual(_get(self.f), b'{"a": 2}')
        self.assertEqual(self.tmp_files(), [])

    def test_a_file_that_appears_meanwhile_is_not_overwritten(self):
        def mutate():
            _put(self.f, '{"theirs": true}')
        with self.racing(mutate):
            with self.assertRaises(ValueError):
                claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.f), b'{"theirs": true}')
        self.assertEqual(self.tmp_files(), [])


class Unreadable(Base):
    """Нечитне не чіпаємо взагалі: стан `unreadable`, `connect`/`disconnect` кидають `OSError`, байти ті самі."""

    def check(self, raw):
        _put(self.f, raw)
        self.assertEqual(self.state(), 'unreadable', raw)
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        with self.assertRaises(OSError):
            claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_get(self.f), raw if isinstance(raw, bytes) else raw.encode('utf-8'))
        self.assertEqual(self.tmp_files(), [])

    def test_content_that_is_not_ours_to_merge(self):
        for raw in ('{not json', '', '[]', '5', 'null', '"x"', '{"hooks": []}', '{"hooks": null}',
                    '{"hooks": {"Stop": {}}}', '{"hooks": {"Stop": null}}', b'\xff\xfe\x00bad'):
            with self.subTest(raw=raw):
                self.check(raw)

    def test_a_symlinked_file_is_not_followed(self):
        target = os.path.join(self.root, 'target.json')
        _put(target, '{}')
        os.makedirs(self.dir)
        os.symlink(target, self.f)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(target), b'{}')
        self.assertTrue(os.path.islink(self.f))

    def test_a_symlinked_claude_folder_is_not_followed(self):
        other = os.path.join(self.root, 'other-claude')
        os.makedirs(other)
        os.symlink(other, self.dir)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(os.listdir(other), [])

    def test_a_file_instead_of_the_claude_folder_and_a_folder_instead_of_the_file(self):
        _put(self.dir, 'i am a file')
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.dir), b'i am a file')
        os.remove(self.dir)
        os.makedirs(self.f)
        self.assertEqual(self.state(), 'unreadable')
        with self.assertRaises(OSError):
            claude_hook.connect(self.space, PORT)
        self.assertTrue(os.path.isdir(self.f))


class Disconnect(Base):
    def test_nothing_to_remove_writes_nothing(self):
        self.assertEqual(claude_hook.disconnect(self.space, PORT)['state'], 'missing')
        self.assertFalse(os.path.exists(self.dir))
        _put(self.f, '{"hooks": {"Stop": []}, "x":   1}')
        before = _get(self.f)
        claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_get(self.f), before, 'порожній Stop людини — не наше, байти ті самі')

    def test_foreign_hooks_stay_and_only_ours_go(self):
        original = {'env': {'A': '1'}, 'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'command': 'echo pre'}]}],
                                                  'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}
        _put(self.f, json.dumps(original))
        claude_hook.connect(self.space, PORT)
        self.assertEqual(claude_hook.disconnect(self.space, PORT)['state'], 'missing')
        self.assertEqual(_json(self.f), original)

    def test_a_stop_and_hooks_emptied_by_us_are_removed_but_other_keys_stay(self):
        _put(self.f, json.dumps({'env': {'A': '1'}}))
        claude_hook.connect(self.space, PORT)
        claude_hook.disconnect(self.space, PORT)
        self.assertEqual(_json(self.f), {'env': {'A': '1'}})

    def test_a_file_that_becomes_empty_is_deleted(self):
        claude_hook.connect(self.space, PORT)
        self.assertEqual(claude_hook.disconnect(self.space, PORT), {'state': 'missing', 'path': self.f})
        self.assertFalse(os.path.exists(self.f))
        self.assertEqual(self.tmp_files(), [])

    def test_disconnect_removes_every_copy_of_ours(self):
        _put(self.f, json.dumps({'hooks': {'Stop': [{'hooks': [_ours(OTHER)]}, {'hooks': [_ours(PORT)]}]}}))
        claude_hook.disconnect(self.space, PORT)
        self.assertFalse(os.path.exists(self.f))

    def test_a_change_before_removal_is_refused(self):
        claude_hook.connect(self.space, PORT)
        doc = _json(self.f)
        doc['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': 'echo keep'}]})
        _put(self.f, json.dumps(doc))
        claude_hook.connect(self.space, OTHER)             # лишилось дві групи: наша й чужа

        def mutate():
            _put(self.f, '{"theirs": 1}')
        with self.racing(mutate):
            with self.assertRaises(ValueError) as cm:
                claude_hook.disconnect(self.space, OTHER)
        self.assertEqual(str(cm.exception), 'changed')
        self.assertEqual(_get(self.f), b'{"theirs": 1}')


class Exclude(Base):
    """`.git/info/exclude`: рядок додаємо один раз, лише коли МИ створили файл і `.git` — тека."""

    def setUp(self):
        super().setUp()
        self.git = os.path.join(self.space, '.git')
        self.exclude = os.path.join(self.git, 'info', 'exclude')

    def lines(self):
        return _get(self.exclude).decode('utf-8').split('\n')

    def test_a_created_file_adds_the_line_once(self):
        os.makedirs(self.git)
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.lines(), [LINE, ''])
        claude_hook.connect(self.space, OTHER)             # перезапис (stale) нового рядка не додає
        claude_hook.disconnect(self.space, OTHER)          # файл видалено
        claude_hook.connect(self.space, PORT)
        self.assertEqual(self.lines().count(LINE), 1)

    def test_existing_exclude_text_is_kept_and_gets_a_newline_first(self):
        _put(self.exclude, '# mine')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.exclude), ('# mine\n' + LINE + '\n').encode('utf-8'))

    def test_a_file_that_already_existed_is_not_ours_to_hide(self):
        os.makedirs(self.git)
        _put(self.f, '{}')
        claude_hook.connect(self.space, PORT)
        self.assertFalse(os.path.exists(self.exclude))

    def test_a_git_file_worktree_or_submodule_gets_no_exclude(self):
        _put(self.git, 'gitdir: ../elsewhere\n')
        claude_hook.connect(self.space, PORT)
        self.assertEqual(_get(self.git), b'gitdir: ../elsewhere\n')
        self.assertEqual(self.state(), 'ok')

    def test_no_git_means_no_git(self):
        claude_hook.connect(self.space, PORT)
        self.assertFalse(os.path.exists(self.git))

    def test_an_unwritable_exclude_does_not_fail_the_connect(self):
        os.makedirs(os.path.join(self.git, 'info', 'exclude'))      # exclude — тека: дописати не можна
        self.assertEqual(claude_hook.connect(self.space, PORT)['state'], 'ok')


class Elsewhere(Base):
    def setUp(self):
        super().setUp()
        self.outer = os.path.join(self.root, 'outer')
        os.makedirs(os.path.join(self.outer, '.git'))
        self.inner = os.path.join(self.outer, 'a', 'space')
        os.makedirs(self.inner)

    def test_a_space_inside_another_repository_is_elsewhere_and_nothing_is_written(self):
        self.assertEqual(claude_hook.status(self.inner, PORT),
                         {'state': 'elsewhere', 'path': os.path.join(self.inner, '.claude', 'settings.local.json')})
        self.assertEqual(claude_hook.connect(self.inner, PORT)['state'], 'elsewhere')
        self.assertFalse(os.path.exists(os.path.join(self.inner, '.claude')))

    def test_the_repository_root_itself_is_not_elsewhere(self):
        self.assertEqual(claude_hook.status(self.outer, PORT)['state'], 'missing')

    def test_a_space_with_its_own_git_dir_or_file_is_not_elsewhere(self):
        os.mkdir(os.path.join(self.inner, '.git'))
        self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')
        shutil.rmtree(os.path.join(self.inner, '.git'))
        _put(os.path.join(self.inner, '.git'), 'gitdir: ../x\n')
        self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_the_home_folder_repository_does_not_count(self):
        with mock.patch.object(claude_hook, '_home', return_value=self.outer):
            self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_on_windows_there_is_no_elsewhere(self):
        with mock.patch.object(claude_hook, '_WINDOWS', True):
            self.assertEqual(claude_hook.status(self.inner, PORT)['state'], 'missing')

    def test_a_plain_space_without_any_repository_above_is_not_elsewhere(self):
        self.assertEqual(self.state(), 'missing')


if __name__ == '__main__':
    unittest.main()

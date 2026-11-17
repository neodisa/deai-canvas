"""Кошик задач простору (етап Д, 0.30.0): модуль без сервера — лише `cfg` і тимчасовий диск."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))
import task_trash as tt  # noqa: E402

NOW = datetime.datetime(2026, 11, 17, 10, 15, 0, tzinfo=datetime.timezone.utc)
LATER = datetime.datetime(2026, 11, 17, 11, 0, 0, tzinfo=datetime.timezone.utc)


class TrashCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='task-trash-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, 'work')

    def mk(self, tid, files=('index.html',)):
        d = os.path.join(self.root, tid)
        os.makedirs(d)
        for f in files:
            with open(os.path.join(d, f), 'w', encoding='utf-8') as fh:
                fh.write(tid)
        return d

    def cfg(self, **tasks):
        return {'current': next(iter(tasks), None), 'tasks': {k: dict(v) for k, v in tasks.items()}}


class TrashDirFor(TrashCase):
    def test_next_to_task_folder_with_stamp(self):
        d = self.mk('a')
        self.assertEqual(tt.trash_dir_for(d, 'a', NOW), os.path.join(self.root, '.deai-trash', 'a-20261117-101500'))

    def test_taken_name_gets_suffix(self):
        d = self.mk('a')
        os.makedirs(os.path.join(self.root, '.deai-trash', 'a-20261117-101500'))
        os.makedirs(os.path.join(self.root, '.deai-trash', 'a-20261117-101500-2'))
        self.assertTrue(tt.trash_dir_for(d, 'a', NOW).endswith('a-20261117-101500-3'))


    def test_hostile_ids_are_rejected(self):
        d = self.mk('a')
        for bad in ('/x', 'a/../z', '..', '.', '', None):
            with self.assertRaises(tt.TrashError, msg=repr(bad)) as cm:
                tt.trash_dir_for(d, bad, NOW)
            self.assertEqual(cm.exception.code, 'bad-id')


class Delete(TrashCase):
    def test_moves_folder_and_entry_in_one_cfg(self):
        d = self.mk('a')
        cfg = self.cfg(a={'title': 'A', 'dir': d, 'vercel_project': 'p'}, b={'title': 'B', 'dir': self.mk('b')})
        rec, _undo = tt.delete(cfg, 'a', NOW, order=['a', 'b'])
        self.assertNotIn('a', cfg['tasks'])
        self.assertFalse(os.path.exists(d))
        self.assertTrue(os.path.isfile(os.path.join(rec['trashDir'], 'index.html')))
        self.assertEqual(cfg['trash']['a']['entry'], {'title': 'A', 'dir': d, 'vercel_project': 'p'})
        self.assertEqual(rec['dir'], d)
        self.assertEqual(rec['at'], '2026-11-17T10:15:00Z')

    def test_current_moves_to_most_recent_other(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')}, c={'dir': self.mk('c')})
        cfg['current'] = 'b'
        tt.delete(cfg, 'b', NOW, order=['b', 'c', 'a'])
        self.assertEqual(cfg['current'], 'c')

    def test_current_falls_back_when_order_is_incomplete(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')})
        tt.delete(cfg, 'a', NOW, order=['a'])
        self.assertEqual(cfg['current'], 'b')

    def test_current_falls_back_to_first_remaining_with_empty_order(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')}, c={'dir': self.mk('c')})
        tt.delete(cfg, 'a', NOW)
        self.assertEqual(cfg['current'], 'b')

    def test_refuses_when_live_trash_record_exists(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d})
        cfg['trash'] = {'a': {'entry': {'dir': '/old'}, 'dir': '/old', 'trashDir': None, 'at': 'x'}}
        with self.assertRaises(tt.TrashError) as cm:
            tt.delete(cfg, 'a', NOW)
        self.assertEqual(cm.exception.code, 'task-in-trash')
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))
        self.assertIn('a', cfg['tasks'])
        self.assertEqual(cfg['trash']['a']['dir'], '/old')

    def test_tombstone_is_overwritten(self):
        cfg = self.cfg(a={'dir': self.mk('a')})
        cfg['trash'] = {'a': {'purged': 'x'}}
        tt.delete(cfg, 'a', NOW)
        self.assertIn('entry', cfg['trash']['a'])

    def test_failed_rename_leaves_cfg_and_folder(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d}, b={'dir': self.mk('b')})
        with mock.patch('task_trash.os.rename', side_effect=OSError('boom')):
            with self.assertRaises(OSError):
                tt.delete(cfg, 'a', NOW, order=['a', 'b'])
        self.assertIn('a', cfg['tasks'])
        self.assertNotIn('trash', cfg)
        self.assertEqual(cfg['current'], 'a')
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))

    def test_last_task_drops_current(self):
        cfg = self.cfg(a={'dir': self.mk('a')})
        tt.delete(cfg, 'a', NOW, order=['a'])
        self.assertNotIn('current', cfg)

    def test_non_current_keeps_current(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')})
        tt.delete(cfg, 'b', NOW, order=['a', 'b'])
        self.assertEqual(cfg['current'], 'a')

    def test_missing_folder_gives_record_without_trash_dir(self):
        gone = os.path.join(self.root, 'gone')
        cfg = self.cfg(g={'dir': gone})
        rec, undo = tt.delete(cfg, 'g', NOW)
        self.assertIsNone(rec['trashDir'])
        undo()                                            # нічого не переносили — нічого й не вертає
        self.assertFalse(os.path.exists(os.path.join(self.root, '.deai-trash')))

    def test_undo_brings_folder_back(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d})
        rec, undo = tt.delete(cfg, 'a', NOW)
        undo()
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))
        self.assertFalse(os.path.exists(rec['trashDir']))

    def test_garbage_trash_value_is_replaced(self):
        cfg = self.cfg(a={'dir': self.mk('a')})
        cfg['trash'] = ['сміття']
        tt.delete(cfg, 'a', NOW)
        self.assertIn('a', cfg['trash'])


class Restore(TrashCase):
    def trashed(self):
        d = self.mk('a')
        cfg = self.cfg(a={'title': 'A', 'dir': d}, b={'dir': self.mk('b')})
        rec, _ = tt.delete(cfg, 'a', NOW, order=['a', 'b'])
        return cfg, d, rec

    def test_moves_back_and_restores_entry(self):
        cfg, d, _rec = self.trashed()
        entry, _undo = tt.restore(cfg, 'a')
        self.assertEqual(entry['title'], 'A')
        self.assertIn('a', cfg['tasks'])
        self.assertNotIn('a', cfg['trash'])
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))

    def test_refuses_when_original_folder_exists(self):
        cfg, d, rec = self.trashed()
        os.makedirs(d)                                    # агент записав у стару теку знову
        with self.assertRaises(tt.TrashError) as cm:
            tt.restore(cfg, 'a')
        self.assertEqual(cm.exception.code, 'task-dir-exists')
        self.assertTrue(os.path.isdir(rec['trashDir']), 'тека в кошику мусить лишитись')
        self.assertIn('a', cfg['trash'])

    def test_refuses_when_id_is_taken(self):
        cfg, _d, _rec = self.trashed()
        cfg['tasks']['a'] = {'dir': '/elsewhere'}
        with self.assertRaises(tt.TrashError) as cm:
            tt.restore(cfg, 'a')
        self.assertEqual(cm.exception.code, 'task-exists')

    def test_unknown_and_tombstone_are_not_in_trash(self):
        cfg, _d, _rec = self.trashed()
        tt.purge(cfg, 'a', LATER)
        for tid in ('a', 'nope'):
            with self.assertRaises(tt.TrashError) as cm:
                tt.restore(cfg, tid)
            self.assertEqual(cm.exception.code, 'not-in-trash')

    def test_refuses_without_original_folder_and_moves_nothing(self):
        cfg, _d, rec = self.trashed()
        cfg['trash']['a']['dir'] = None
        with self.assertRaises(tt.TrashError) as cm:
            tt.restore(cfg, 'a')
        self.assertEqual(cm.exception.code, 'task-restore-failed')
        self.assertTrue(os.path.isdir(rec['trashDir']))
        self.assertIn('a', cfg['trash'])
        self.assertNotIn('a', cfg['tasks'])

    def test_undo_puts_folder_back_into_trash(self):
        cfg, d, rec = self.trashed()
        _entry, undo = tt.restore(cfg, 'a')
        undo()
        self.assertTrue(os.path.isdir(rec['trashDir']))
        self.assertFalse(os.path.exists(d))


class Purge(TrashCase):
    def test_removes_folder_and_leaves_tombstone(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d})
        rec, _ = tt.delete(cfg, 'a', NOW)
        tt.purge(cfg, 'a', LATER)
        self.assertFalse(os.path.exists(rec['trashDir']))
        self.assertEqual(cfg['trash']['a'], {'purged': '2026-11-17T11:00:00Z'})
        self.assertFalse(tt.in_trash(cfg, 'a'))

    def test_missing_trash_folder_still_leaves_tombstone(self):
        cfg = {'tasks': {}, 'trash': {'x': {'entry': {}, 'dir': None,
                                            'trashDir': os.path.join(self.root, '.deai-trash', 'x-1'), 'at': 'x'}}}
        tt.purge(cfg, 'x', LATER)
        self.assertEqual(cfg['trash']['x'], {'purged': '2026-11-17T11:00:00Z'})

    def test_refuses_a_path_outside_the_trash(self):
        victim = self.mk('victim')
        cfg = {'tasks': {}, 'trash': {'x': {'entry': {}, 'dir': victim, 'trashDir': victim, 'at': 'x'}}}
        with self.assertRaises(tt.TrashError) as cm:
            tt.purge(cfg, 'x', LATER)
        self.assertEqual(cm.exception.code, 'task-purge-failed')
        self.assertTrue(os.path.isfile(os.path.join(victim, 'index.html')))
        self.assertIn('entry', cfg['trash']['x'])

    def test_symlink_in_trash_is_unlinked_not_followed(self):
        target = self.mk('target')
        trash = os.path.join(self.root, '.deai-trash')
        os.makedirs(trash)
        link = os.path.join(trash, 'x-20261117-101500')
        os.symlink(target, link)
        cfg = {'tasks': {}, 'trash': {'x': {'entry': {}, 'dir': None, 'trashDir': link, 'at': 'x'}}}
        tt.purge(cfg, 'x', LATER)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(os.path.isfile(os.path.join(target, 'index.html')))


class Listing(TrashCase):
    def test_newest_first_without_tombstones_and_garbage(self):
        cfg = {'tasks': {}, 'trash': {
            'old': {'entry': {'title': 'O'}, 'at': '2026-11-16T10:00:00Z'},
            'new': {'entry': {'title': 'N'}, 'at': '2026-11-17T10:00:00Z'},
            'dead': {'purged': '2026-11-17T09:00:00Z'},
            'junk': 5}}
        self.assertEqual([k for k, _ in tt.listing(cfg)], ['new', 'old'])

    def test_clear_tombstone_keeps_live_records(self):
        cfg = {'trash': {'dead': {'purged': 'x'}, 'live': {'entry': {}, 'at': 'x'}}}
        tt.clear_tombstone(cfg, 'dead')
        tt.clear_tombstone(cfg, 'live')
        self.assertEqual(list(cfg['trash']), ['live'])


class InsideTrash(unittest.TestCase):
    def test_only_a_direct_child_of_the_trash_dir(self):
        d = tt.TRASH_DIRNAME
        self.assertTrue(tt.inside_trash(os.path.join('/w', d, 'x-1')))
        for bad in (os.path.join('/w', 'x'), os.path.join('/w', d), os.path.join('/w', d, 'a', 'b'),
                    os.path.join('/w', d, '..'), '', '/'):
            self.assertFalse(tt.inside_trash(bad), bad)


if __name__ == '__main__':
    unittest.main()

"""Кошик ітерацій (фаза И, Р6): перенесення без стирання, повернення, прибирання через 7 днів, номер без повторів."""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import iter_trash as tr  # noqa: E402

T0 = datetime.datetime(2026, 11, 23, 10, 0, 0, tzinfo=datetime.timezone.utc)


def _task(ids):
    d = tempfile.mkdtemp(prefix='itrash-')
    for i in ids:
        os.makedirs(os.path.join(d, 'iterations', i))
        with open(os.path.join(d, 'iterations', i, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(f'<h1>{i}</h1>')
    return d


class MoveAndRestore(unittest.TestCase):
    def setUp(self):
        self.d = _task(['it1', 'it2', 'it3'])
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_move_keeps_files_and_entry(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'note': 'Друга'}, T0)
        self.assertEqual(slot, 'it2--20261123-100000')
        self.assertFalse(os.path.exists(os.path.join(self.d, 'iterations', 'it2')))
        base = os.path.join(self.d, '.trash', 'iterations', slot)
        self.assertTrue(os.path.isfile(os.path.join(base, 'files', 'index.html')))
        with open(os.path.join(base, 'entry.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['entry'], {'id': 'it2', 'note': 'Друга'})

    def test_same_second_gets_suffix(self):
        a = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        os.makedirs(os.path.join(self.d, 'iterations', 'it2'))
        b = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        self.assertEqual((a, b), ('it2--20261123-100000', 'it2--20261123-100000-2'))

    def test_restore_puts_back_same_id(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'note': 'Друга', 'git': 'abc1234'}, T0)
        entry, renamed = tr.restore(self.d, slot, ['it1', 'it3'])
        self.assertEqual((entry['id'], renamed, entry['git']), ('it2', False, 'abc1234'))
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it2', 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(self.d, '.trash', 'iterations', slot)))

    def test_restore_collision_takes_next_free_id_and_drops_git(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'git': 'abc1234'}, T0)
        os.makedirs(os.path.join(self.d, 'iterations', 'it2'))       # хтось уже зайняв it2
        entry, renamed = tr.restore(self.d, slot, ['it1', 'it2', 'it3'])
        self.assertEqual((entry['id'], renamed), ('it4', True))
        self.assertNotIn('git', entry)
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it4', 'index.html')))

    def test_restore_unknown_slot(self):
        with self.assertRaises(tr.IterTrashError) as c:
            tr.restore(self.d, 'it9--20261123-100000', ['it1'])
        self.assertEqual(c.exception.code, 'not-in-trash')
        for bad in ('../x', 'it2', 'it2--x', '', 5, None):
            with self.assertRaises(tr.IterTrashError) as c:
                tr.restore(self.d, bad, ['it1'])
            self.assertEqual(c.exception.code, 'bad-slot')

    def test_bad_id_refused(self):
        for bad in ('', '..', 'a/b', 'it 1', None):
            with self.assertRaises(tr.IterTrashError):
                tr.move_to_trash(self.d, {'id': bad}, T0)


class NextIdAndPurge(unittest.TestCase):
    def setUp(self):
        self.d = _task(['it1', 'it2', 'it3'])
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_next_id_counts_trash(self):
        tr.move_to_trash(self.d, {'id': 'it3'}, T0)
        self.assertEqual(tr.next_id(self.d, ['it1', 'it2']), 'it4')

    def test_next_id_counts_stray_folders(self):
        os.makedirs(os.path.join(self.d, 'iterations', 'it7'))
        self.assertEqual(tr.next_id(self.d, ['it1']), 'it8')

    def test_purge_removes_only_older_than_keep(self):
        old = tr.move_to_trash(self.d, {'id': 'it1'}, T0 - datetime.timedelta(days=8))
        fresh = tr.move_to_trash(self.d, {'id': 'it2'}, T0 - datetime.timedelta(days=6))
        self.assertEqual(tr.purge(self.d, T0), [old])
        root = os.path.join(self.d, '.trash', 'iterations')
        self.assertEqual(os.listdir(root), [fresh])

    def test_purge_without_trash_is_noop(self):
        self.assertEqual(tr.purge(self.d, T0), [])


class InsertOrdered(unittest.TestCase):
    def test_inserts_by_number(self):
        its = [{'id': 'it1'}, {'id': 'it3'}, {'id': 'it5'}]
        tr.insert_ordered(its, {'id': 'it4'})
        self.assertEqual([i['id'] for i in its], ['it1', 'it3', 'it4', 'it5'])

    def test_non_numeric_goes_last(self):
        its = [{'id': 'it1'}]
        tr.insert_ordered(its, {'id': 'draft'})
        self.assertEqual([i['id'] for i in its], ['it1', 'draft'])


if __name__ == '__main__':
    unittest.main()

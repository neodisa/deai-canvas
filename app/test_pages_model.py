import json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import pages_model as pm


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
    def _index(self, rel=''):
        p = os.path.join(self.d, rel)
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, 'index.html'), 'w') as f:
            f.write('<html><body>x</body></html>')


_PROBE = ('import fcntl, sys\n'
          'fh = open(sys.argv[1], "a")\n'
          'try:\n'
          '    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
          'except BlockingIOError:\n'
          '    sys.exit(3)\n')


def _probe_lock(iter_dir):
    """Код виходу дочірнього процесу, що без очікування пробує взяти .pages.lock:
    3 — лок хтось тримає, 0 — вільний."""
    return subprocess.run([sys.executable, '-c', _PROBE,
                           os.path.join(iter_dir, '.pages.lock')]).returncode


class TestBackwardCompat(Base):
    def test_no_pages_json_but_index_returns_implicit_main(self):
        self._index()
        pages = pm.read_pages(self.d)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]['id'], 'main')
        self.assertEqual(pm.page_rel(pages[0]), '')

    def test_empty_dir_returns_no_pages(self):
        self.assertEqual(pm.read_pages(self.d), [])


class TestVersionTag(Base):
    def test_implicit_main_keeps_plain_iter_num(self):
        self.assertEqual(pm.page_version_tag('it3', {'id': 'main'}), '3')

    def test_explicit_page_is_composite(self):
        self.assertEqual(pm.page_version_tag('it3', {'id': 'detali'}), '3/detali')


class TestCrud(Base):
    def test_add_creates_folder_and_entry(self):
        pages = []
        pages, pg = pm.add_page(self.d, pages, 'Категорія')
        self.assertTrue(os.path.isfile(os.path.join(self.d, pg['id'], 'index.html')))
        self.assertEqual(pm.read_pages(self.d)[0]['name'], 'Категорія')
        self.assertTrue(pg['published'])

    def test_add_child_two_levels(self):
        pages = []
        pages, parent = pm.add_page(self.d, pages, 'Категорія')
        pages, child = pm.add_page(self.d, pages, 'Порожньо', parent_id=parent['id'])
        self.assertEqual(pm.read_pages(self.d)[0]['children'][0]['name'], 'Порожньо')

    def test_delete_removes_folder(self):
        pages = []
        pages, pg = pm.add_page(self.d, pages, 'Деталі')
        pages = pm.delete_page(self.d, pages, pg['id'])
        self.assertFalse(os.path.isdir(os.path.join(self.d, pg['id'])))
        self.assertEqual(pm.read_pages(self.d), [])

    def test_rename_keeps_id_changes_name(self):
        pages, pg = pm.add_page(self.d, [], 'Деталі')
        pages = pm.rename_page(self.d, pages, pg['id'], 'Деталі картки')
        self.assertEqual(pm.find_page(pages, pg['id'])[0]['name'], 'Деталі картки')

    def test_set_published_toggle(self):
        pages, pg = pm.add_page(self.d, [], 'Деталі')
        pages = pm.set_published(self.d, pages, pg['id'], False)
        self.assertFalse(pm.find_page(pages, pg['id'])[0]['published'])

    def test_cyrillic_name_transliterates_to_latin_id(self):
        pages, pg = pm.add_page(self.d, [], 'Деталі')
        self.assertEqual(pg['id'], 'detali')
        self.assertEqual(pm.page_version_tag('it3', pg), '3/detali')

    def _snapshot(self):
        """Усе, що лежить у теці ітерації, і байти pages.json (None, якщо його нема)."""
        p = pm.pages_path(self.d)
        raw = None
        if os.path.isfile(p):
            with open(p, 'rb') as fh:
                raw = fh.read()
        return sorted(os.listdir(self.d)), raw

    def test_add_under_state_rejected(self):
        pages, parent = pm.add_page(self.d, [], 'Категорія')
        pages, child = pm.add_page(self.d, pages, 'Порожньо', parent_id=parent['id'], kind='state')
        before = self._snapshot()
        with self.assertRaises(pm.TreeError) as ctx:
            pm.add_page(self.d, pages, 'Глибше', parent_id=child['id'])
        self.assertEqual(ctx.exception.code, 'state-has-children')
        # відкат: відмовлена вставка не лишає сироту в дереві, яке тримає викликач
        self.assertEqual([f['page']['id'] for f in pm.flatten(pages)], [parent['id'], child['id']])
        # і нічого на диску: ні теки відмовленої сторінки, ні перезапису pages.json
        # (.bak теж не зʼявився б) — валідація стоїть ДО файлових побічних ефектів
        self.assertEqual(self._snapshot(), before)

    def test_add_persists_explicit_kind(self):
        """kind пишеться явно: без нього сторінка під сторінкою читалась би
        як легасі-стан, і вкладена сторінка тихо ставала б станом."""
        pages, top = pm.add_page(self.d, [], 'Категорія')
        pages, pg = pm.add_page(self.d, pages, 'Вкладена', parent_id=top['id'], kind='page')
        pages, st = pm.add_page(self.d, pages, 'Варіант', parent_id=top['id'], kind='state')
        self.assertEqual([top['kind'], pg['kind'], st['kind']], ['page', 'page', 'state'])
        on_disk = pm.read_pages(self.d)
        self.assertEqual([(c['id'], c['kind']) for c in on_disk[0]['children']],
                         [(pg['id'], 'page'), (st['id'], 'state')])
        self.assertEqual([(f['page']['id'], f['kind']) for f in pm.flatten(on_disk)],
                         [(top['id'], 'page'), (pg['id'], 'page'), (st['id'], 'state')])

    def test_add_folder_kind_rejected(self):
        """Теку створює окрема операція: у неї нема index.html."""
        with self.assertRaises(pm.TreeError) as ctx:
            pm.add_page(self.d, [], 'Тека', kind='folder')
        self.assertEqual(ctx.exception.code, 'bad-kind')
        self.assertEqual(os.listdir(self.d), [])

    def test_add_unknown_parent_rejected(self):
        pages, top = pm.add_page(self.d, [], 'Категорія')
        before = self._snapshot()
        with self.assertRaises(pm.TreeError) as ctx:
            pm.add_page(self.d, pages, 'Сирота', parent_id='nope')
        self.assertEqual(ctx.exception.code, 'not-found')
        self.assertEqual(self._snapshot(), before)

    def test_add_state_at_root_rejected_and_rolled_back(self):
        """Гілка відкату для кореня окрема від гілки «є батько»."""
        pages = []
        with self.assertRaises(pm.TreeError) as ctx:
            pm.add_page(self.d, pages, 'Стан без сторінки', kind='state')
        self.assertEqual(ctx.exception.code, 'state-outside-page')
        self.assertEqual(pages, [])
        self.assertEqual(os.listdir(self.d), [])

    def test_add_to_single_page_preserves_main(self):
        self._index()  # root index.html, no pages.json → implicit main
        pages = pm.read_pages(self.d)          # [{'id':'main',...}]
        pages, pg = pm.add_page(self.d, pages, 'Деталі')
        ids = [p['id'] for p in pm.read_pages(self.d)]
        self.assertEqual(ids, ['main', pg['id']])   # main збережено, без дубля
        self.assertEqual(ids.count('main'), 1)


class TestValidate(Base):
    def test_state_with_children_raises(self):
        # без kind: b — легасі-стан (дитина сторінки) із дитиною
        bad = [{'id': 'a', 'name': 'A', 'children': [
            {'id': 'b', 'name': 'B', 'children': [{'id': 'c', 'name': 'C'}]}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.validate(bad)
        self.assertEqual(ctx.exception.code, 'state-has-children')

    def test_duplicate_id_raises(self):
        with self.assertRaises(ValueError):
            pm.validate([{'id': 'a', 'name': 'A'}, {'id': 'a', 'name': 'B'}])


class TestOpenable(Base):
    def test_group_is_not_openable(self):
        pages = [{'id': 'g', 'name': 'Список', 'isGroup': True, 'children': [
            {'id': 'g-short', 'name': 'Коротко'}]}]
        ids = [p['id'] for p in pm.openable_pages(pages)]
        self.assertEqual(ids, ['g-short'])


class TestPreview(unittest.TestCase):
    TREE = [
        {'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'w', 'name': 'W', 'kind': 'folder', 'children': [
                {'id': 's', 'name': 'S', 'kind': 'state'}]}]},
        {'id': 'd', 'name': 'Чернетки', 'kind': 'folder', 'published': False, 'children': [
            {'id': 'x', 'name': 'X', 'kind': 'page'}]},
        {'id': 'e', 'name': 'Порожня', 'kind': 'folder'},
        {'id': 'h', 'name': 'H', 'kind': 'page', 'published': False, 'children': [
            {'id': 'hs', 'name': 'HS', 'kind': 'state'}]}]

    def test_hidden_hides_the_whole_subtree(self):
        ids = [f['page']['id'] for f in pm.preview_flat(self.TREE)]
        self.assertEqual(ids, ['p', 's'])      # ні x (тека схована), ні hs (сторінка схована)

    def test_outline_keeps_folders_with_something_to_open(self):
        got = [(f['page']['id'], f['kind'], f['depth']) for f in pm.preview_outline(self.TREE)]
        # «Порожня» — тека без жодної відкриваної сторінки — у превʼю не їде
        self.assertEqual(got, [('p', 'page', 0), ('w', 'folder', 1), ('s', 'state', 2)])

    def test_an_explicitly_published_child_does_not_outlive_its_hidden_parent(self):
        """Старе правило дивилось лише на сам вузол, тож `published: true` дитини
        при схованому батьку виносило її в превʼю. Тепер ховає найближчий
        схований предок — будь-якого типу, і явне `true` на нащадку цього не
        скасовує."""
        tree = [{'id': 'a', 'name': 'A', 'published': False, 'children': [
            {'id': 'a1', 'name': 'A1', 'published': True}]}]        # легасі: без kind
        self.assertEqual(pm.preview_flat(tree), [])
        self.assertEqual(pm.preview_outline(tree), [])

    def test_only_a_literal_false_hides(self):
        """Як і раніше: приховує рівно `published is False`, а не будь-яке хибне
        значення — `None`/`0`/відсутній ключ лишають вузол видимим."""
        tree = [{'id': 'a', 'name': 'A', 'published': None},
                {'id': 'b', 'name': 'B', 'published': 0},
                {'id': 'c', 'name': 'C'}]
        self.assertEqual([f['page']['id'] for f in pm.preview_flat(tree)], ['a', 'b', 'c'])

    def test_rows_have_the_same_shape_as_flatten_and_keep_the_tree_order(self):
        """`preview_*` — той самий формат, що `flatten` (`page/parent/depth/kind`):
        консументи читають однакові поля, а kind виведено з усього дерева, не з
        піддерева (легасі-стан під сторінкою лишається станом)."""
        tree = [{'id': 'p', 'name': 'P', 'children': [        # легасі: без kind
            {'id': 'g', 'name': 'G', 'isGroup': True, 'children': [
                {'id': 'c', 'name': 'C'}]},
            {'id': 's', 'name': 'S'}]},
            {'id': 'q', 'name': 'Q'}]
        whole = pm.flatten(tree)
        self.assertEqual(pm.preview_outline(tree), whole)
        self.assertEqual(pm.preview_flat(tree), [f for f in whole if f['kind'] != 'folder'])
        self.assertEqual([(f['page']['id'], f['parent'], f['depth'], f['kind'])
                          for f in pm.preview_flat(tree)],
                         [('p', None, 0, 'page'), ('c', 'g', 2, 'page'),
                          ('s', 'p', 1, 'state'), ('q', None, 0, 'page')])

    def test_a_folder_holding_only_empty_folders_is_dropped_too(self):
        """«Є що відкрити» — у ВСЬОМУ піддереві, а не серед прямих дітей: тека з
        порожньою текою всередині нікуди не веде, а тека з глибоко схованою
        сторінкою — веде."""
        tree = [{'id': 'a', 'name': 'A', 'kind': 'folder', 'children': [
            {'id': 'b', 'name': 'B', 'kind': 'folder'}]},
            {'id': 'c', 'name': 'C', 'kind': 'folder', 'children': [
                {'id': 'd', 'name': 'D', 'kind': 'folder', 'children': [
                    {'id': 'e', 'name': 'E', 'kind': 'page'}]}]}]
        self.assertEqual([f['page']['id'] for f in pm.preview_outline(tree)], ['c', 'd', 'e'])

    def test_a_folder_does_not_borrow_the_page_of_its_next_sibling(self):
        """Порожня тека стоїть ПЕРЕД сторінкою того ж рівня: пошук нащадків
        зупиняється на першому не глибшому за теку рядку, тож сусідня сторінка
        теку не «рятує»."""
        tree = [{'id': 'f', 'name': 'F', 'kind': 'folder'},
                {'id': 'p', 'name': 'P', 'kind': 'page'}]
        self.assertEqual([f['page']['id'] for f in pm.preview_outline(tree)], ['p'])

    def test_a_folder_whose_only_content_is_hidden_is_dropped(self):
        tree = [{'id': 'f', 'name': 'F', 'kind': 'folder', 'children': [
            {'id': 'p', 'name': 'P', 'kind': 'page', 'published': False}]}]
        self.assertEqual(pm.preview_outline(tree), [])

    def test_does_not_touch_the_tree(self):
        import copy
        before = copy.deepcopy(self.TREE)
        pm.preview_flat(self.TREE)
        pm.preview_outline(self.TREE)
        self.assertEqual(self.TREE, before)


class TestReservedIds(Base):
    """Id сторінки стає ТЕКОЮ в ітерації; імена, що там уже щось означають
    (`main` → корінь, спільні `assets/icons/fonts`, склад кадрів `shots`,
    службові `publish/iterations`), slug мусить обходити."""

    NAMES = ('Icons', 'Assets', 'Fonts', 'Shots', 'Main', 'Publish', 'Iterations')

    def test_add_page_never_takes_a_reserved_id(self):
        os.makedirs(os.path.join(self.d, 'icons'))
        with open(os.path.join(self.d, 'icons', 'a.svg'), 'w') as fh:
            fh.write('<svg/>')
        for name in self.NAMES:
            with self.subTest(name=name):
                _, page = pm.add_page(self.d, [], name)
                self.assertEqual(page['id'], name.lower() + '-2')
        self.assertEqual(os.listdir(os.path.join(self.d, 'icons')), ['a.svg'],
                         'справжній спільний icons/ зачеплено')

    def test_add_folder_never_takes_a_reserved_id(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                _, f = pm.op_add_folder([], name)
                self.assertEqual(f['id'], name.lower() + '-2')

    def test_add_page_avoids_a_dir_that_already_exists_on_disk(self):
        os.makedirs(os.path.join(self.d, 'img'))       # спільна тека, якої нема в дереві
        _, page = pm.add_page(self.d, [], 'Img')
        self.assertEqual(page['id'], 'img-2')
        self.assertTrue(os.path.isdir(os.path.join(self.d, 'img')))

    def test_existing_trees_with_reserved_ids_still_validate(self):
        """Резерв — лише для НОВИХ id: інакше наявне дерево з `icons` стало б
        нечитабельним."""
        pm.validate([{'id': 'icons', 'name': 'I', 'kind': 'folder'}])


class TestAddPageIndex(Base):
    """`index` — позиція нової сторінки серед дітей батька: CLI з `--after`
    пише дерево ОДИН раз (інакше .bak тримав би проміжний стан)."""

    def _tree(self):
        return [{'id': 'a', 'name': 'A', 'kind': 'page'},
                {'id': 'b', 'name': 'B', 'kind': 'page'}]

    def test_index_inserts_among_root_children_and_clamps(self):
        for index, want in ((0, ['n', 'a', 'b']), (1, ['a', 'n', 'b']),
                            (99, ['a', 'b', 'n']), (-5, ['n', 'a', 'b']), (-1, ['n', 'a', 'b']), (None, ['a', 'b', 'n'])):
            with self.subTest(index=index):
                pages, node = pm.add_page(self.d, self._tree(), 'N', index=index)
                self.assertEqual([x['id'] for x in pages],
                                 [w if w != 'n' else node['id'] for w in want])
                shutil.rmtree(os.path.join(self.d, node['id']), True)

    def test_index_inserts_among_the_parents_children(self):
        tree = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'x', 'name': 'X', 'kind': 'folder', 'isGroup': True},
            {'id': 'y', 'name': 'Y', 'kind': 'folder', 'isGroup': True}]}]
        pages, node = pm.add_page(self.d, tree, 'N', parent_id='p', index=1)
        self.assertEqual([c['id'] for c in pages[0]['children']], ['x', node['id'], 'y'])

    def test_bad_index_is_bad_index_and_leaves_no_trace(self):
        for bad in (True, 1.5, '1', [0]):
            with self.subTest(index=bad):
                tree = self._tree()
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.add_page(self.d, tree, 'N', index=bad)
                self.assertEqual(ctx.exception.code, 'bad-index')
                self.assertEqual(len(tree), 2)
                self.assertEqual(os.listdir(self.d), [])


class TestReparent(Base):
    def test_reparent_leaf_under_top_level(self):
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, b = pm.add_page(self.d, pages, 'Деталі')
        pages = pm.reparent_page(self.d, pages, b['id'], a['id'])
        self.assertEqual(pm.read_pages(self.d)[0]['children'][0]['id'], b['id'])

    def test_reparent_self_rejected_no_data_loss(self):
        pages, a = pm.add_page(self.d, [], 'Категорія')
        with self.assertRaises(ValueError):
            pm.reparent_page(self.d, pages, a['id'], a['id'])
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [a['id']])  # уцілів

    def test_reparent_page_with_children_is_allowed_now(self):
        """Було «максимум 2 рівні» й відмова для сторінки з дітьми; тепер глибина
        вільна, а діти (стани) їдуть разом із сторінкою."""
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, child = pm.add_page(self.d, pages, 'Порожньо', parent_id=a['id'], kind='state')
        pages, b = pm.add_page(self.d, pages, 'Деталі')
        pm.reparent_page(self.d, pages, a['id'], b['id'])
        on_disk = pm.read_pages(self.d)
        self.assertEqual([p['id'] for p in on_disk], [b['id']])
        moved = on_disk[0]['children'][0]
        self.assertEqual(moved['id'], a['id'])
        self.assertEqual([(c['id'], c['kind']) for c in moved['children']],
                         [(child['id'], 'state')])

    def test_reparent_legacy_state_keeps_its_kind_on_disk(self):
        """Реальний шлях: стара задача (pages.json без kind). Стан, перенесений
        у теку своєї сторінки, лишається станом і в файлі."""
        with open(pm.pages_path(self.d), 'w', encoding='utf-8') as fh:
            json.dump({'pages': _tree('LEGACY', _rules())}, fh)
        pm.reparent_page(self.d, pm.read_pages(self.d), 's1', 'w')
        on_disk = pm.read_pages(self.d)
        self.assertEqual({f['page']['id']: f['kind'] for f in pm.flatten(on_disk)},
                         {'p': 'page', 's2': 'state', 'w': 'folder', 's1': 'state', 'g': 'folder'})

    def test_reparent_under_state_rejected(self):
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, child = pm.add_page(self.d, pages, 'Порожньо', parent_id=a['id'], kind='state')
        pages, b = pm.add_page(self.d, pages, 'Деталі')
        before = self._bytes()
        with self.assertRaises(pm.TreeError) as ctx:
            pm.reparent_page(self.d, pages, b['id'], child['id'])  # батько — стан
        self.assertEqual(ctx.exception.code, 'state-has-children')
        self.assertEqual(self._bytes(), before, 'відмова переписала pages.json')

    def test_reparent_lands_at_the_end_and_none_means_root(self):
        """Контракт «у кінець дітей» лишився з часів двох рівнів; parent None —
        верхній рівень (у кінець кореня)."""
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, c1 = pm.add_page(self.d, pages, 'Перша', parent_id=a['id'])
        pages, b = pm.add_page(self.d, pages, 'Деталі')
        pm.reparent_page(self.d, pages, b['id'], a['id'])
        self.assertEqual([c['id'] for c in pm.read_pages(self.d)[0]['children']],
                         [c1['id'], b['id']])
        pm.reparent_page(self.d, pm.read_pages(self.d), c1['id'], None)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [a['id'], c1['id']])

    def test_delete_and_reparent_update_the_callers_list_in_place(self):
        """Як і add_page: викликач тримає ТОЙ САМИЙ список і бачить зміну без
        повторного читання (serve колись віддавав його далі)."""
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, b = pm.add_page(self.d, pages, 'Деталі')
        out = pm.reparent_page(self.d, pages, b['id'], a['id'])
        self.assertIs(out, pages)
        self.assertEqual([p['id'] for p in pages], [a['id']])
        out = pm.delete_page(self.d, pages, a['id'])
        self.assertIs(out, pages)
        self.assertEqual(pages, [])

    def _bytes(self):
        with open(pm.pages_path(self.d), 'rb') as fh:
            return fh.read()


class TestMove(Base):
    """Порядок сторінок (fb-09092026-d4c51b): досі в моделі не було жодної
    функції, що його міняє, — лише `reparent_page`, яка кладе в кінець."""

    def _three(self, parent_id=None):
        pages = []
        ids = []
        for n in ('Перша', 'Друга', 'Третя'):
            pages, pg = pm.add_page(self.d, pages, n, parent_id=parent_id)
            ids.append(pg['id'])
        return pages, ids

    def test_move_to_top_and_persisted(self):
        pages, (a, b, c) = self._three()
        pm.move_page(self.d, pages, c, 0)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [c, a, b])

    def test_move_down_by_one(self):
        pages, (a, b, c) = self._three()
        pm.move_page(self.d, pages, a, 1)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [b, a, c])

    def test_index_is_clamped_not_refused(self):
        pages, (a, b, c) = self._three()
        pm.move_page(self.d, pages, a, 99)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [b, c, a])
        pm.move_page(self.d, pm.read_pages(self.d), a, -5)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [a, b, c])

    def test_moves_among_siblings_only(self):
        """Дочірня сторінка переставляється серед ДІТЕЙ свого батька і не
        виринає на верхній рівень — зміна вкладеності це інша дія."""
        pages, top = pm.add_page(self.d, [], 'Головна')
        pages, other = pm.add_page(self.d, pages, 'Пошук')
        kids = []
        for n in ('Стан 1', 'Стан 2', 'Стан 3'):
            pages, pg = pm.add_page(self.d, pages, n, parent_id=top['id'])
            kids.append(pg['id'])
        pm.move_page(self.d, pages, kids[2], 0)
        got = pm.read_pages(self.d)
        self.assertEqual([p['id'] for p in got], [top['id'], other['id']])
        self.assertEqual([p['id'] for p in got[0]['children']], [kids[2], kids[0], kids[1]])

    def test_same_place_does_not_rewrite(self):
        """Клік «на місці» не пише: кожен запис знімає `.bak`, і порожня дія
        затерла б останню справжню резервну копію."""
        pages, (a, b, c) = self._three()
        p = pm.pages_path(self.d)
        before = os.stat(p).st_mtime_ns
        pm.move_page(self.d, pages, b, 1)
        self.assertEqual(os.stat(p).st_mtime_ns, before)

    def test_bad_input_rejected_without_data_loss(self):
        pages, (a, b, c) = self._three()
        for bad in (('nope', 0), (a, '1'), (a, None), (a, True)):
            with self.assertRaises(ValueError):
                pm.move_page(self.d, pm.read_pages(self.d), *bad)
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], [a, b, c])


class TestDeleteCascade(Base):
    def test_delete_parent_removes_child_folders(self):
        pages, a = pm.add_page(self.d, [], 'Категорія')
        pages, child = pm.add_page(self.d, pages, 'Порожньо', parent_id=a['id'])
        pages = pm.delete_page(self.d, pages, a['id'])
        self.assertFalse(os.path.isdir(os.path.join(self.d, a['id'])))
        self.assertFalse(os.path.isdir(os.path.join(self.d, child['id'])))
        self.assertEqual(pm.read_pages(self.d), [])


FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'tests', 'fixtures', 'tree-rules.json')


def _rules():
    with open(FIXTURE, encoding='utf-8') as fh:
        return json.load(fh)


def _tree(spec, rules):
    """`BASE` → копія trees.BASE; `DEEP:N` → N тек одна в одній; список → як є."""
    if isinstance(spec, list):
        return json.loads(json.dumps(spec))
    if spec.startswith('DEEP:'):
        n = int(spec.split(':')[1])
        root = cur = {'id': 'f1', 'name': 'F1', 'kind': 'folder'}
        for i in range(2, n + 1):
            nxt = {'id': f'f{i}', 'name': f'F{i}', 'kind': 'folder'}
            cur['children'] = [nxt]
            cur = nxt
        return [root]
    return json.loads(json.dumps(rules['trees'][spec]))


class TestKindOf(unittest.TestCase):
    def test_explicit_kind_wins(self):
        self.assertEqual(pm.kind_of({'kind': 'state'}, None), 'state')

    def test_legacy_group_is_folder(self):
        self.assertEqual(pm.kind_of({'isGroup': True}, 'page'), 'folder')

    def test_legacy_child_of_page_is_state(self):
        self.assertEqual(pm.kind_of({}, 'page'), 'state')

    def test_legacy_child_of_folder_and_root_is_page(self):
        self.assertEqual(pm.kind_of({}, 'folder'), 'page')
        self.assertEqual(pm.kind_of({}, None), 'page')

    def test_bad_kind_falls_back_to_inference(self):
        # validate відмовить окремо; kind_of лише не падає на смітті
        self.assertEqual(pm.kind_of({'kind': 'widget'}, 'page'), 'state')


class TestDeepTree(unittest.TestCase):
    TREE = [{'id': 'a', 'name': 'A', 'kind': 'folder', 'children': [
        {'id': 'b', 'name': 'B', 'kind': 'folder', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page', 'children': [
                {'id': 'd', 'name': 'D', 'kind': 'state'}]}]}]}]

    def test_flatten_walks_every_level_with_kind(self):
        got = [(f['page']['id'], f['parent'], f['depth'], f['kind'])
               for f in pm.flatten(self.TREE)]
        self.assertEqual(got, [('a', None, 0, 'folder'), ('b', 'a', 1, 'folder'),
                               ('c', 'b', 2, 'page'), ('d', 'c', 3, 'state')])

    def test_find_page_returns_the_real_sibling_list(self):
        page, sibs = pm.find_page(self.TREE, 'd')
        self.assertEqual(page['id'], 'd')
        self.assertIs(sibs, self.TREE[0]['children'][0]['children'][0]['children'])

    def test_path_of(self):
        self.assertEqual([n['id'] for n in pm.path_of(self.TREE, 'd')], ['a', 'b', 'c', 'd'])
        self.assertEqual(pm.path_of(self.TREE, 'zzz'), [])

    def test_openable_skips_only_folders(self):
        self.assertEqual([p['id'] for p in pm.openable_pages(self.TREE)], ['c', 'd'])


class TestFlattenLegacyKinds(unittest.TestCase):
    """Вузли без kind мусять виглядати, як панель показувала до kind: тип
    дитини виводиться з типу БАТЬКА, тож flatten мусить передавати його вниз."""

    @staticmethod
    def _kinds(tree):
        return [(f['page']['id'], f['kind']) for f in pm.flatten(tree)]

    def test_child_of_unkinded_page_is_state(self):
        tree = [{'id': 'p', 'name': 'P', 'children': [{'id': 'c', 'name': 'C'}]}]
        self.assertEqual(self._kinds(tree), [('p', 'page'), ('c', 'state')])

    def test_group_then_page_then_state(self):
        tree = [{'id': 'g', 'name': 'G', 'isGroup': True, 'children': [
            {'id': 'c', 'name': 'C', 'children': [{'id': 'd', 'name': 'D'}]}]}]
        self.assertEqual(self._kinds(tree),
                         [('g', 'folder'), ('c', 'page'), ('d', 'state')])


class TestSharedRulesValidate(unittest.TestCase):
    def test_cases(self):
        rules = _rules()
        for case in rules['validate']:
            with self.subTest(case['name']):
                tree = _tree(case['tree'], rules)
                if case['err'] is None:
                    pm.validate(tree)
                else:
                    with self.assertRaises(pm.TreeError) as ctx:
                        pm.validate(tree)
                    self.assertEqual(ctx.exception.code, case['err'])


class TestSharedRulesVisible(unittest.TestCase):
    """Видимість превʼю: ті самі кейси ганяє tree-model.test.mjs (visibleIds) і
    звіряє з published кожної картки buildRows — три місця, одне правило."""

    def test_cases(self):
        rules = _rules()
        for case in rules['visible']:
            with self.subTest(case['name']):
                tree = _tree(case['tree'], rules)
                self.assertEqual([f['page']['id'] for f in pm._visible(tree)],
                                 case['visible'])
                self.assertEqual([f['page']['id'] for f in pm.preview_flat(tree)],
                                 case['open'])
                # теки в «видимих», але не у відкриваних — рівно різниця наборів
                outline = [f['page']['id'] for f in pm.preview_outline(tree)]
                self.assertTrue(set(case['open']) <= set(outline) <= set(case['visible']))


class TestHandEditedStructure(unittest.TestCase):
    """pages.json, який правили руками: не-рядкова назва й не-списковий children
    мусять дати TreeError, а не голий AttributeError/TypeError (500 без коду)."""

    BAD_CHILDREN = ({'id': 'x'}, 'abc', 7)

    def test_validate_name_not_a_string_is_empty_name(self):
        for bad in (5, ['a'], {'a': 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.validate([{'id': 'p', 'name': bad, 'kind': 'page'}])
                self.assertEqual(ctx.exception.code, 'empty-name')

    def test_every_op_refuses_non_list_children_with_a_code(self):
        for bad in self.BAD_CHILDREN:
            tree = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': bad}]
            ops = {
                'move': lambda t: pm.op_move(t, ['p'], None, 0),
                'add_folder': lambda t: pm.op_add_folder(t, 'F'),
                'group': lambda t: pm.op_group(t, ['p'], 'G'),
                'unwrap': lambda t: pm.op_unwrap(t, 'p'),
                'delete': lambda t: pm.op_delete(t, 'p', 'all'),
                'set_kind': lambda t: pm.op_set_kind(t, 'p', 'state'),
            }
            for name, fn in ops.items():
                with self.subTest(bad=bad, op=name):
                    with self.assertRaises(pm.TreeError) as ctx:
                        fn(json.loads(json.dumps(tree)))
                    self.assertEqual(ctx.exception.code, 'corrupt')


class TestHandEditedFile(Base):
    def test_readers_report_corrupt_for_non_list_children_and_non_object_nodes(self):
        for raw in (b'{"pages": [{"id": "p", "children": {"a": 1}}]}',
                    b'{"pages": [{"id": "p", "children": "abc"}]}',
                    b'{"pages": [7]}',
                    b'{"pages": [{"id": "p", "children": [null]}]}'):
            with self.subTest(raw=raw):
                with open(pm.pages_path(self.d), 'wb') as fh:
                    fh.write(raw)
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.read_pages(self.d)
                self.assertEqual(ctx.exception.code, 'corrupt')


class TestSharedRulesMove(unittest.TestCase):
    def test_cases(self):
        rules = _rules()
        for case in rules['move']:
            with self.subTest(case['name']):
                tree = _tree(case['tree'], rules)
                before = json.dumps(tree)
                if case['err']:
                    with self.assertRaises(pm.TreeError) as ctx:
                        pm.op_move(tree, case['ids'], case['parent'], case['index'])
                    self.assertEqual(ctx.exception.code, case['err'])
                    self.assertEqual(json.dumps(tree), before, 'відмова зачепила дерево')
                    continue
                out = pm.op_move(tree, case['ids'], case['parent'], case['index'])
                if case.get('noop'):
                    self.assertEqual(json.dumps(out), before)
                for nid, kids in (case.get('order') or {}).items():
                    node, _ = pm.find_page(out, nid)
                    self.assertEqual([c['id'] for c in node.get('children') or []], kids)
                if case.get('kinds'):
                    flat = {f['page']['id']: f['kind'] for f in pm.flatten(out)}
                    for nid, kind in case['kinds'].items():
                        self.assertEqual(flat[nid], kind, f'тип {nid} змінився після операції')


class TestOps(Base):
    TREE = [{'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
        {'id': 's1', 'name': 'Порожньо', 'kind': 'state'},
        {'id': 's2', 'name': 'Помилка', 'kind': 'state'}]},
        {'id': 'q', 'name': 'Особа', 'kind': 'page'}]

    def tree(self):
        return json.loads(json.dumps(self.TREE))

    def test_add_folder_inside_page(self):
        out, f = pm.op_add_folder(self.tree(), 'Віджет «Санкції»', parent='p')
        self.assertEqual(f['kind'], 'folder')
        self.assertTrue(f['isGroup'])
        self.assertEqual([c['id'] for c in out[0]['children']], ['s1', 's2', f['id']])

    def test_add_folder_under_state_refused(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_add_folder(self.tree(), 'X', parent='s1')
        self.assertEqual(ctx.exception.code, 'state-has-children')

    def test_group_siblings_keeps_position(self):
        out, f = pm.op_group(self.tree(), ['s2', 's1'], 'Віджет')
        kids = out[0]['children']
        self.assertEqual([c['id'] for c in kids], [f['id']])
        self.assertEqual([c['id'] for c in kids[0]['children']], ['s1', 's2'])

    def test_group_non_siblings_refused(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_group(self.tree(), ['s1', 'q'], 'X')
        self.assertEqual(ctx.exception.code, 'not-siblings')

    def test_unwrap_folder_lifts_children_in_place(self):
        out, f = pm.op_group(self.tree(), ['s1', 's2'], 'W')
        out, removed = pm.op_unwrap(out, f['id'])
        self.assertEqual([c['id'] for c in out[0]['children']], ['s1', 's2'])
        self.assertEqual(removed, [])       # у теки немає файлів

    def test_unwrap_page_that_would_orphan_states_refused(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_unwrap(self.tree(), 'p')
        self.assertEqual(ctx.exception.code, 'state-outside-page')

    def test_set_kind_state_to_page_and_back(self):
        out = pm.op_set_kind(self.tree(), 's1', 'page')
        self.assertEqual(pm.find_page(out, 's1')[0]['kind'], 'page')
        out = pm.op_set_kind(out, 's1', 'state')
        self.assertEqual(pm.find_page(out, 's1')[0]['kind'], 'state')

    def test_set_kind_folder_refused(self):
        out, f = pm.op_add_folder(self.tree(), 'W', parent='p')
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_set_kind(out, f['id'], 'page')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_delete_all_reports_every_file_dir(self):
        out, removed = pm.op_delete(self.tree(), 'p', 'all')
        self.assertEqual([p['id'] for p in out], ['q'])
        self.assertEqual(sorted(removed), ['p', 's1', 's2'])


    def test_add_folder_is_published_and_honours_index(self):
        out, f = pm.op_add_folder(self.tree(), 'Віджет', parent='p', index=1)
        self.assertTrue(f['published'])
        self.assertEqual([c['id'] for c in out[0]['children']], ['s1', f['id'], 's2'])

    def test_group_non_contiguous_goes_to_first_position_in_tree_order(self):
        """Тека стає на місце ПЕРШОГО з вибраних (за порядком дерева, а не за
        порядком id у запиті), а не першого-з-краю чи останнього."""
        tree = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'a', 'name': 'A', 'kind': 'state'},
            {'id': 's1', 'name': 'S1', 'kind': 'state'},
            {'id': 'x', 'name': 'X', 'kind': 'state'},
            {'id': 's2', 'name': 'S2', 'kind': 'state'},
            {'id': 'b', 'name': 'B', 'kind': 'state'}]}]
        out, f = pm.op_group(tree, ['s2', 's1'], 'W')
        kids = out[0]['children']
        self.assertEqual([c['id'] for c in kids], ['a', f['id'], 'x', 'b'])
        self.assertEqual([c['id'] for c in kids[1]['children']], ['s1', 's2'])

    def test_group_with_any_unknown_id_refused_and_tree_untouched(self):
        """Як op_move: невідомий id серед вибраних — відмова, а не тиха менша група."""
        tree = self.tree()
        before = json.dumps(tree)
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_group(tree, ['s1', 'zzz'], 'X')
        self.assertEqual(ctx.exception.code, 'not-found')
        self.assertEqual(json.dumps(tree), before)

    def test_group_legacy_states_stay_states_inside_the_folder(self):
        """Без закріплення типу легасі-стани (без kind) у теці всередині сторінки
        виводились би як СТОРІНКИ — найважливіший сценарій «згорнути в віджет»."""
        legacy = [{'id': 'p', 'name': 'P', 'children': [
            {'id': 's1', 'name': 'S1'}, {'id': 's2', 'name': 'S2'}]}]
        out, f = pm.op_group(legacy, ['s1', 's2'], 'Віджет')
        kinds = {x['page']['id']: x['kind'] for x in pm.flatten(out)}
        self.assertEqual(kinds, {'p': 'page', f['id']: 'folder', 's1': 'state', 's2': 'state'})

    def test_unwrap_legacy_page_in_folder_stays_a_page_after_lifting(self):
        """Теку підняли до сторінки: дитина без kind виводилась би вже як стан."""
        legacy = [{'id': 'p', 'name': 'P', 'children': [
            {'id': 'w', 'name': 'W', 'isGroup': True, 'children': [
                {'id': 'c', 'name': 'C'}]}]}]
        self.assertEqual({x['page']['id']: x['kind'] for x in pm.flatten(legacy)},
                         {'p': 'page', 'w': 'folder', 'c': 'page'})
        out, removed = pm.op_unwrap(legacy, 'w')
        self.assertEqual({x['page']['id']: x['kind'] for x in pm.flatten(out)},
                         {'p': 'page', 'c': 'page'})
        # і через delete — той самий шлях
        out, _ = pm.op_delete(legacy, 'w', 'unwrap')
        self.assertEqual(pm.find_page(out, 'c')[0]['kind'], 'page')

    def test_reorder_within_same_parent_does_not_pin_kinds(self):
        """Закріплюємо тип лише коли змінюється батько; перестановка лишає вузли
        байт-у-байт (інакше порожній клік переписував би файл)."""
        legacy = _tree('LEGACY', _rules())
        out = pm.op_move(legacy, ['s2'], 'p', 0)
        self.assertEqual([c['id'] for c in pm.find_page(out, 'p')[0]['children']], ['s2', 's1', 'w'])
        self.assertTrue(all('kind' not in x['page'] for x in pm.flatten(out)))

    def test_pinning_does_not_launder_an_invalid_kind(self):
        """Явний, але невалідний kind лишається невалідним — validate мусить його
        побачити, а не закріплення тихо перетворити на виведений."""
        bad = [{'id': 'p', 'name': 'P', 'children': [
            {'id': 'w', 'name': 'W', 'isGroup': True},
            {'id': 'x', 'name': 'X', 'kind': 'widget'}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_move(bad, ['x'], 'w', 0)
        self.assertEqual(ctx.exception.code, 'bad-kind')
        bad = [{'id': 'p', 'name': 'P', 'children': [
            {'id': 'w', 'name': 'W', 'isGroup': True, 'children': [
                {'id': 'x', 'name': 'X', 'kind': 'widget'}]}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_unwrap(bad, 'w')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_group_with_nothing_to_group_refused(self):
        for ids in ([], ['nope']):
            with self.assertRaises(pm.TreeError) as ctx:
                pm.op_group(self.tree(), ids, 'X')
            self.assertEqual(ctx.exception.code, 'not-found')

    def test_unwrap_page_reports_its_own_dir_but_not_the_children(self):
        tree = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]}]
        out, removed = pm.op_unwrap(tree, 'p')
        self.assertEqual([n['id'] for n in out], ['c'])
        self.assertEqual(removed, ['p'])     # файли діти збережено

    def test_unwrap_implicit_main_has_no_dir_to_remove(self):
        """У неявної main теки нема: '' у списку стирання = rmtree усієї ітерації."""
        tree = [{'id': 'main', 'name': 'Головна', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]}]
        out, removed = pm.op_unwrap(tree, 'main')
        self.assertEqual(removed, [])

    def test_set_kind_folder_as_target_refused(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_set_kind(self.tree(), 's1', 'folder')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_delete_all_skips_folders_and_the_implicit_main(self):
        out, removed = pm.op_delete(_tree('BASE', _rules()), 'p', 'all')
        self.assertEqual(sorted(removed), ['p', 's1', 's2'])      # тека w файлів не має
        main = [{'id': 'main', 'name': 'Головна', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]}]
        out, removed = pm.op_delete(main, 'main', 'all')
        self.assertEqual((out, removed), ([], ['c']))

    def test_delete_unknown_mode_refused_not_treated_as_all(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_delete(self.tree(), 'p', 'nope')
        self.assertEqual(ctx.exception.code, 'bad-mode')
        out, removed = pm.op_delete(self.tree(), 'q', 'unwrap')    # делегує в op_unwrap
        self.assertEqual(([n['id'] for n in out], removed), (['p'], ['q']))

    def test_delete_unknown_node_refused(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_delete(self.tree(), 'nope', 'all')
        self.assertEqual(ctx.exception.code, 'not-found')

    def test_move_index_must_be_an_integer(self):
        for bad in ('1', None, True, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.op_move(self.tree(), ['q'], None, bad)
                self.assertEqual(ctx.exception.code, 'bad-index')

    def test_move_negative_index_clamps_to_start(self):
        """Зріз `dest[-1:-1]` вставив би ПЕРЕД останнім, а не на початок."""
        tree = [{'id': i, 'name': i.upper(), 'kind': 'page'} for i in 'abc']
        out = pm.op_move(tree, ['c'], None, -1)
        self.assertEqual([n['id'] for n in out], ['c', 'a', 'b'])

    def test_move_leaves_no_empty_children_behind(self):
        out = pm.op_move(_tree('BASE', _rules()), ['s1', 's2'], 'q', 0)
        w, _ = pm.find_page(out, 'w')
        self.assertNotIn('children', w)

    def test_ops_do_not_touch_their_input(self):
        """Кожна операція чиста: помилка посеред не лишає напівзмінене дерево,
        а успіх не підміняє те, що тримає викликач."""
        tree = self.tree()
        before = json.dumps(tree)
        pm.op_move(tree, ['q'], 'p', 0)
        pm.op_add_folder(tree, 'F', parent='p')
        pm.op_group(tree, ['s1', 's2'], 'W')
        pm.op_unwrap(tree, 'q')
        pm.op_set_kind(tree, 's1', 'page')
        pm.op_delete(tree, 'p', 'all')
        self.assertEqual(json.dumps(tree), before)


    # --- передперевірка входу (_precheck) і лагодження зламаного легасі ---

    def test_set_kind_repairs_a_broken_legacy_tree(self):
        """[p[c[d]]] без kind невалідне (c виводиться станом із дитиною), але саме
        op_set_kind(c, 'page') його й лагодить — тож вхід цілим validate не
        перевіряємо. d мусить лишитись сторінкою, а не перевивестись у стан."""
        broken = [{'id': 'p', 'name': 'P', 'children': [
            {'id': 'c', 'name': 'C', 'children': [{'id': 'd', 'name': 'D'}]}]}]
        with self.assertRaises(pm.TreeError):
            pm.validate(broken)
        out = pm.op_set_kind(broken, 'c', 'page')
        self.assertEqual({f['page']['id']: f['kind'] for f in pm.flatten(out)},
                         {'p': 'page', 'c': 'page', 'd': 'page'})

    def test_set_kind_does_not_launder_an_invalid_kind_elsewhere(self):
        tree = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 's', 'name': 'S', 'kind': 'state'},
            {'id': 'x', 'name': 'X', 'kind': 'widget'}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_set_kind(tree, 's', 'page')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_set_kind_to_the_kind_it_already_has_is_a_noop(self):
        """Без матеріалізації: інакше «порожній» клік дописав би kind у весь файл."""
        legacy = [{'id': 'p', 'name': 'P', 'children': [{'id': 's', 'name': 'S'}]}]
        out = pm.op_set_kind(legacy, 's', 'state')        # вже стан
        self.assertEqual(json.dumps(out), json.dumps(legacy))
        out = pm.op_set_kind(legacy, 'p', 'page')         # вже сторінка
        self.assertEqual(json.dumps(out), json.dumps(legacy))

    def test_every_op_refuses_a_node_without_id_with_bad_id(self):
        """Було голий KeyError('id') → 500. Вузол без id — батько цілі, щоб
        операція дійшла до нього раніше, ніж до validate."""
        bad = [{'name': 'Без id', 'kind': 'page', 'children': [
            {'id': 's', 'name': 'S', 'kind': 'state'}]}]
        calls = {
            'op_move': lambda: pm.op_move(bad, ['s'], None, 0),
            'op_add_folder': lambda: pm.op_add_folder(bad, 'F'),
            'op_group': lambda: pm.op_group(bad, ['s'], 'G'),
            'op_unwrap': lambda: pm.op_unwrap(bad, 's'),
            'op_set_kind': lambda: pm.op_set_kind(bad, 's', 'page'),
            'op_delete': lambda: pm.op_delete(bad, 's', 'all'),
        }
        for name, call in calls.items():
            with self.subTest(name):
                with self.assertRaises(pm.TreeError) as ctx:
                    call()
                self.assertEqual(ctx.exception.code, 'bad-id')

    def test_delete_refuses_a_tree_with_an_invalid_kind_even_inside_the_deleted_subtree(self):
        """Передперевірка йде по всьому входу, не лише по тому, що лишається:
        інакше видалення сусіда мовчки «лікувало» б сміття, якого ніхто не бачив."""
        bad = [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'x', 'name': 'X', 'kind': 'widget'}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_delete(bad, 'p', 'all')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_ops_refuse_an_id_that_is_not_a_string(self):
        bad = [{'id': 5, 'name': 'P', 'kind': 'page'}]
        for call in (lambda: pm.op_add_folder(bad, 'F'), lambda: pm.op_move(bad, [5], None, 0)):
            with self.assertRaises(pm.TreeError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, 'bad-id')

    # --- чесність no-op і повернені значення ---

    def test_move_prunes_empty_children_only_where_it_touched(self):
        """Чужий `children: []` збоку не чіпаємо — інакше «порожній» перенос
        переписав би файл заради косметики."""
        tree = [{'id': 'a', 'name': 'A', 'kind': 'page', 'children': []},
                {'id': 'b', 'name': 'B', 'kind': 'page'}]
        out = pm.op_move(tree, ['b'], None, 1)
        self.assertEqual(json.dumps(out), json.dumps(tree))
        self.assertEqual(pm.find_page(out, 'a')[0]['children'], [])

    def test_move_of_nothing_leaves_no_children_key_on_the_destination(self):
        """`_children_of` лишає порожній `children: []` на батьку-призначенні, якщо
        вставляти нічого: це теж наш слід, і його прибирає сам op_move."""
        tree = [{'id': 'r', 'name': 'R', 'kind': 'page'}]
        out = pm.op_move(tree, [], 'r', 0)
        self.assertEqual(json.dumps(out), json.dumps(tree))

    def test_group_returns_the_folder_from_the_result_with_its_children(self):
        out, f = pm.op_group(self.tree(), ['s2', 's1'], 'Віджет')
        self.assertIs(f, pm.find_page(out, f['id'])[0])
        self.assertEqual([c['id'] for c in f['children']], ['s1', 's2'])

    def test_add_folder_name_must_be_a_string(self):
        for bad in (5, None, '', '   ', ['x']):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.op_add_folder(self.tree(), bad)
                self.assertEqual(ctx.exception.code, 'empty-name')

    def test_add_folder_index_must_be_none_or_an_integer(self):
        for bad in ('1', True, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.op_add_folder(self.tree(), 'F', parent='p', index=bad)
                self.assertEqual(ctx.exception.code, 'bad-index')
        out, f = pm.op_add_folder(self.tree(), 'F', parent='p', index=0)    # 0 — число, не «нема»
        self.assertEqual([c['id'] for c in out[0]['children']][0], f['id'])


class TestMaterializeAndRev(Base):
    def _bytes(self):
        with open(pm.pages_path(self.d), 'rb') as fh:
            return fh.read()

    def test_write_materializes_kind_and_keeps_isgroup_for_folders(self):
        legacy = [{'id': 'g', 'name': 'G', 'isGroup': True, 'children': [
            {'id': 'a', 'name': 'A', 'children': [{'id': 'b', 'name': 'B'}]}]}]
        pm.write_pages(self.d, legacy)
        with open(pm.pages_path(self.d), encoding='utf-8') as fh:
            on_disk = json.load(fh)['pages']
        g = on_disk[0]
        self.assertEqual((g['kind'], g['isGroup']), ('folder', True))
        a = g['children'][0]
        self.assertEqual(a['kind'], 'page')
        self.assertNotIn('isGroup', a)
        self.assertEqual(a['children'][0]['kind'], 'state')

    def test_write_adds_isgroup_to_an_explicit_folder(self):
        """Явний kind=folder без isGroup: стара версія канваса відкрила б такий
        вузол як сторінку — isGroup дописується завжди."""
        pm.write_pages(self.d, [{'id': 'f', 'name': 'F', 'kind': 'folder'}])
        self.assertIs(pm.read_pages(self.d)[0]['isGroup'], True)

    def test_write_refuses_bad_kind_instead_of_laundering_it(self):
        """materialize кличеться ПІСЛЯ validate: навпаки невалідний kind тихо
        став би виведеним, і файл із сміттям виглядав би чистим."""
        with self.assertRaises(pm.TreeError) as ctx:
            pm.write_pages(self.d, [{'id': 'a', 'name': 'A', 'kind': 'widget'}])
        self.assertEqual(ctx.exception.code, 'bad-kind')
        self.assertFalse(os.path.exists(pm.pages_path(self.d)))

    def test_write_drops_isgroup_from_non_folders(self):
        """Застарілий `isGroup` на вузлі з явним kind не лишається: колега на
        старій версії відкрив би такий вузол як теку."""
        pm.write_pages(self.d, [{'id': 'x', 'name': 'X', 'kind': 'page', 'isGroup': True}])
        self.assertNotIn('isGroup', pm.read_pages(self.d)[0])

    def test_rev_changes_with_file_and_is_empty_without_it(self):
        self.assertEqual(pm.pages_rev(self.d), '')
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        r1 = pm.pages_rev(self.d)
        pm.write_pages(self.d, [{'id': 'a', 'name': 'B'}])
        self.assertNotEqual(pm.pages_rev(self.d), r1)

    def test_mutate_refuses_stale_rev_without_writing(self):
        """Застарілий rev відмовляє ДО change: зміна, що пише, не має ні
        запуститись, ні лишити слід на диску."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        before = self._bytes()
        ran = []

        def change(pages):
            ran.append(True)
            return pm.op_add_folder(pages, 'F')

        with self.assertRaises(pm.TreeError) as ctx:
            pm.mutate(self.d, change, rev='deadbeef')
        self.assertEqual(ctx.exception.code, 'stale')
        self.assertEqual(ran, [], 'change запущено попри застарілий rev')
        self.assertEqual(self._bytes(), before)
        self.assertFalse(os.path.exists(pm.pages_path(self.d) + '.bak'))

    def test_mutate_writes_once_and_returns_extra(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        rev = pm.pages_rev(self.d)
        extra = pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'), rev=rev)
        self.assertEqual(extra['kind'], 'folder')
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], ['a', extra['id']])

    def test_mutate_without_rev_skips_the_stale_check(self):
        """CLI (`bin/pages.py`) не має rev панелі: він читає й пише під одним локом."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        extra = pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'))
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], ['a', extra['id']])

    def test_mutate_checks_rev_inside_the_lock(self):
        """rev, звірений ПОЗА локом, лишає вікно: чужий запис між перевіркою й
        читанням проскочить, і застаріла правка його затре. Тримаємо лок, стартуємо
        mutate зі старим rev, міняємо файл і відпускаємо — mutate мусить побачити
        нову версію й відмовити."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        rev = pm.pages_rev(self.d)
        seen = []

        def worker():
            try:
                pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'), rev=rev)
                seen.append('written')
            except pm.TreeError as e:
                seen.append(e.code)

        with pm.pages_lock(self.d):
            t = threading.Thread(target=worker)
            t.start()
            time.sleep(0.3)        # worker уже стоїть на локу (а в збитій версії — за перевіркою)
            pm.write_pages(self.d, [{'id': 'a', 'name': 'Інша'}])
        t.join(10)
        self.assertEqual(seen, ['stale'])
        self.assertEqual([(p['id'], p['name']) for p in pm.read_pages(self.d)], [('a', 'Інша')])

    def test_mutate_reads_the_file_once_for_rev_and_tree(self):
        """rev і дерево — з ОДНОГО читання: два окремі читання лишали б вікно,
        де rev відповідає одній версії файла, а змінене дерево — іншій."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        rev = pm.pages_rev(self.d)
        real, calls = pm._read_raw, []

        def counting(iter_dir):
            calls.append(iter_dir)
            return real(iter_dir)

        with mock.patch.object(pm, '_read_raw', counting):
            pm.mutate(self.d, lambda pages: (pages, None), rev=rev)
        self.assertEqual(len(calls), 1)

    def test_mutate_noop_does_not_touch_the_file(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}])
        rev = pm.pages_rev(self.d)
        mtime = os.path.getmtime(pm.pages_path(self.d))
        pm.mutate(self.d, lambda pages: (pm.op_move(pages, ['a'], None, 0), None), rev=rev)
        self.assertEqual(os.path.getmtime(pm.pages_path(self.d)), mtime)
        # перший запис не мав попередника, тож .bak міг зʼявитись лише від
        # зайвого запису в mutate (mtime сам по собі залежить від зерна годинника)
        self.assertFalse(os.path.exists(pm.pages_path(self.d) + '.bak'))

    def test_mutate_noop_with_a_stray_empty_children_does_not_write(self):
        """Чужий `children: []` десь збоку не робить «порожній» перенос зміною."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A', 'children': []},
                                {'id': 'b', 'name': 'B'}])
        before = self._bytes()
        pm.mutate(self.d, lambda pages: (pm.op_move(pages, ['b'], None, 1), None))
        self.assertEqual(self._bytes(), before)
        self.assertFalse(os.path.exists(pm.pages_path(self.d) + '.bak'))

    def test_mutate_first_change_on_implicit_main_keeps_it(self):
        """Старт легасі-задачі: pages.json нема, rev порожній, а панель показує
        неявну main. Перша ж зміна мусить її зберегти, а не стерти."""
        self._index()
        rev = pm.pages_rev(self.d)
        self.assertEqual(rev, '')
        extra = pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'), rev=rev)
        on_disk = pm.read_pages(self.d)
        self.assertEqual([(p['id'], p['kind']) for p in on_disk],
                         [('main', 'page'), (extra['id'], 'folder')])

    def test_mutate_with_rev_returns_the_rev_of_what_it_wrote(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        r0 = pm.pages_rev(self.d)
        extra, r1, changed = pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'),
                                       rev=r0, with_rev=True)
        self.assertEqual(extra['kind'], 'folder')
        self.assertNotEqual(r1, r0)
        self.assertEqual(r1, pm.pages_rev(self.d))
        self.assertIs(changed, True)

    def test_mutate_with_rev_on_noop_returns_the_unchanged_rev(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}])
        r0 = pm.pages_rev(self.d)
        extra, r1, changed = pm.mutate(
            self.d, lambda pages: (pm.op_move(pages, ['a'], None, 0), 'x'),
            rev=r0, with_rev=True)
        self.assertEqual((extra, r1, changed), ('x', r0, False))

    def test_mutate_with_rev_on_a_missing_file_is_empty_rev_when_nothing_changes(self):
        self._index()                       # неявна main, pages.json нема
        extra, r, changed = pm.mutate(self.d, lambda pages: (pages, 'x'), with_rev=True)
        self.assertEqual((extra, r, changed), ('x', '', False))

    def test_mutate_rev_after_is_taken_under_the_lock(self):
        """rev, знятий ПІСЛЯ відпускання лока, міг би вже належати чужому запису.
        Конкурент стартує зсередини change й чекає лока; pages_rev сповільнено, щоб
        він устиг записати, якби лок був уже відпущений."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        real_rev = pm.pages_rev
        captured, rival = {}, []

        def slow_rev(iter_dir):
            time.sleep(0.3)
            return real_rev(iter_dir)

        def start_rival(pages):
            th = threading.Thread(
                target=lambda: pm.mutate(self.d, lambda p: pm.op_add_folder(p, 'Чужа')))
            th.start()
            rival.append(th)
            return pm.op_add_folder(pages, 'Моя')

        def after(extra):
            captured['rev'] = real_rev(self.d)       # що щойно записано, під локом

        with mock.patch.object(pm, 'pages_rev', slow_rev):
            extra, rev_after, _ = pm.mutate(self.d, start_rival, after=after, with_rev=True)
        rival[0].join(10)
        self.assertEqual(rev_after, captured['rev'])
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], ['a', 'moia', 'chuzha'])

    def test_mutate_after_runs_under_the_lock_after_the_write(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        seen = {}

        def after(extra):
            seen['extra'] = extra
            seen['lock_held'] = _probe_lock(self.d) == 3
            seen['rev'] = pm.pages_rev(self.d)

        extra, rev_after, _ = pm.mutate(self.d, lambda pages: pm.op_add_folder(pages, 'F'),
                                        after=after, with_rev=True)
        self.assertIs(seen['extra'], extra)
        self.assertTrue(seen['lock_held'], 'after виконано поза локом')
        self.assertEqual(seen['rev'], rev_after, 'after виконано до запису')

    def test_mutate_after_is_skipped_when_nothing_was_written(self):
        """Нічого не записано — нічого й доробляти (хук стирає теки)."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}])
        calls = []
        pm.mutate(self.d, lambda pages: (pm.op_move(pages, ['a'], None, 0), None),
                  after=calls.append)
        self.assertEqual(calls, [])

    def test_concurrent_mutates_lose_no_update(self):
        """6 потоків × 5 змін: без справжнього лока два потоки читають одну версію,
        і остання запис затирає решту. `sleep` у change розкриває вікно."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        errors = []

        def change(pages):
            time.sleep(0.002)
            return pm.op_add_folder(pages, 'F')

        def worker():
            for _ in range(5):
                try:
                    pm.mutate(self.d, change)
                except Exception as e:          # noqa: BLE001 — збираємо для асерту
                    errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        self.assertEqual(errors, [])
        ids = [p['id'] for p in pm.read_pages(self.d)]
        self.assertEqual(len(ids), 31)
        self.assertEqual(len(set(ids)), 31)


class TestReadPagesRev(Base):
    """`read_pages_rev` — читання для GET: дерево й rev з ОДНОГО прочитання, без лока.

    Лок тут шкодить, а не допомагає: `pages_lock` створює `.pages.lock` (це
    піднімає mtime теки ітерації, а автосинк вибирає робочу ітерацію саме за
    mtime), падає на теці «лише для читання» і змушує читача чекати писаря.
    Запис же атомарний (`atomic_write_json` замінює файл цілком), тож одне
    читання — узгоджений знімок."""

    def test_returns_the_tree_and_the_rev_of_the_same_bytes(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        pages, rev = pm.read_pages_rev(self.d)
        self.assertEqual(pages, pm.read_pages(self.d))
        self.assertEqual(rev, pm.pages_rev(self.d))
        self.assertRegex(rev, r'^[0-9a-f]{16}$')

    def test_reads_the_file_exactly_once(self):
        """Два читання (дерево, потім rev) лишали б вікно, де писар вліз між ними
        і клієнт отримав дерево одного стану з rev іншого."""
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        real, calls = pm._read_raw, []

        def counting(iter_dir):
            calls.append(iter_dir)
            return real(iter_dir)

        with mock.patch.object(pm, '_read_raw', counting):
            pm.read_pages_rev(self.d)
        self.assertEqual(len(calls), 1)

    def test_takes_no_lock_and_creates_no_lock_file(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        with pm.pages_lock(self.d):        # писар тримає лок: читач не чекає
            pages, _ = pm.read_pages_rev(self.d)
        self.assertEqual([p['id'] for p in pages], ['a'])
        os.remove(os.path.join(self.d, '.pages.lock'))
        before = sorted(os.listdir(self.d))
        pm.read_pages_rev(self.d)
        self.assertEqual(sorted(os.listdir(self.d)), before)
        self.assertFalse(os.path.exists(os.path.join(self.d, '.pages.lock')))

    def test_implicit_main_has_an_empty_rev(self):
        self._index()
        pages, rev = pm.read_pages_rev(self.d)
        self.assertEqual(([p['id'] for p in pages], rev), (['main'], ''))

    def test_missing_directory_is_empty_and_created_nowhere(self):
        gone = os.path.join(self.d, 'it99')
        self.assertEqual(pm.read_pages_rev(gone), ([], ''))
        self.assertFalse(os.path.exists(gone))


class TestCorruptFile(Base):
    """pages.json, який не розбирається, — відмова з кодом `corrupt`, а не голий
    JSONDecodeError (обробники сторінок на ньому рвали зʼєднання без відповіді)."""

    BAD = (b'{oops', b'', b'\xff\xfe\x00', b'[]', b'null', b'"x"',
           b'{"pages": "x"}', b'{"pages": {"a": 1}}')

    def _corrupt(self, raw):
        with open(pm.pages_path(self.d), 'wb') as fh:
            fh.write(raw)

    def test_every_reader_reports_corrupt(self):
        for raw in self.BAD:
            with self.subTest(raw=raw):
                self._corrupt(raw)
                for call in (pm.read_pages, pm.read_pages_rev):
                    with self.assertRaises(pm.TreeError) as ctx:
                        call(self.d)
                    self.assertEqual(ctx.exception.code, 'corrupt')

    def test_a_file_without_the_pages_key_is_just_empty(self):
        """`{}` — не биття: ключа `pages` просто ще нема."""
        self._corrupt(b'{}')
        self.assertEqual(pm.read_pages(self.d), [])

    def test_the_rev_of_a_corrupt_file_still_exists(self):
        """rev — відбиток байтів, а не розбору: він не мусить падати разом із ним."""
        self._corrupt(b'{oops')
        self.assertRegex(pm.pages_rev(self.d), r'^[0-9a-f]{16}$')

    def test_mutate_refuses_without_running_change_or_writing_and_frees_the_lock(self):
        self._corrupt(b'{oops')
        ran = []

        def change(pages):
            ran.append(True)
            return pm.op_add_folder(pages, 'F')

        with self.assertRaises(pm.TreeError) as ctx:
            pm.mutate(self.d, change)
        self.assertEqual(ctx.exception.code, 'corrupt')
        self.assertEqual(ran, [])
        with open(pm.pages_path(self.d), 'rb') as fh:
            self.assertEqual(fh.read(), b'{oops')
        self.assertFalse(os.path.exists(pm.pages_path(self.d) + '.bak'))
        self.assertEqual(_probe_lock(self.d), 0, 'лок не відпущено після corrupt')

    def test_corrupt_is_reported_before_stale(self):
        """Застарілий rev на битому файлі — справжня причина «corrupt», а не
        «перечитай»: перечитування лише повернуло б ту саму відмову."""
        self._corrupt(b'{oops')
        with self.assertRaises(pm.TreeError) as ctx:
            pm.mutate(self.d, lambda pages: (pages, None), rev='deadbeef')
        self.assertEqual(ctx.exception.code, 'corrupt')


class TestUngroup(Base):
    TREE = [{'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
        {'id': 'f', 'name': 'Віджет', 'kind': 'folder', 'isGroup': True, 'children': [
            {'id': 's1', 'name': 'S1', 'kind': 'state'},
            {'id': 's2', 'name': 'S2', 'kind': 'state'}]},
        {'id': 's3', 'name': 'S3', 'kind': 'state'}]},
        {'id': 'q', 'name': 'Особа', 'kind': 'page'}]

    def tree(self):
        return json.loads(json.dumps(self.TREE))

    def test_folder_is_replaced_by_its_children_in_place(self):
        out = pm.op_ungroup(self.tree(), 'f')
        self.assertEqual([c['id'] for c in out[0]['children']], ['s1', 's2', 's3'])

    def test_returns_the_tree_and_leaves_the_input_untouched(self):
        t = self.tree()
        out = pm.op_ungroup(t, 'f')
        self.assertIsInstance(out, list)
        self.assertEqual(t, self.tree())

    def test_page_and_state_are_refused_with_bad_kind(self):
        """«Розгрупувати» сторінку прибрало б її з дерева, не стерши файли, — тиха
        осиротіла тека. Видаляти сторінку — це `op_delete` з явним mode."""
        for nid in ('p', 'q', 's3'):
            with self.subTest(node=nid):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.op_ungroup(self.tree(), nid)
                self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_unknown_id_is_not_found(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_ungroup(self.tree(), 'nope')
        self.assertEqual(ctx.exception.code, 'not-found')

    def test_legacy_isgroup_folder_without_a_kind_is_a_folder(self):
        legacy = [{'id': 'g', 'name': 'G', 'isGroup': True, 'children': [
            {'id': 'a', 'name': 'A'}]}]
        out = pm.op_ungroup(legacy, 'g')
        self.assertEqual([p['id'] for p in out], ['a'])

    def test_explicit_kind_beats_a_contradicting_isgroup_flag(self):
        """Вручну зіпсований `kind: page` + `isGroup: true`: тип для всіх операцій —
        явний kind (`kind_of`), тож це сторінка, і розгрупувати її не можна."""
        t = [{'id': 'p', 'name': 'P', 'kind': 'page', 'isGroup': True}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_ungroup(t, 'p')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_a_legacy_child_of_a_page_is_a_state_not_a_folder(self):
        """Тип без kind виводиться з БАТЬКА: дитина сторінки — стан. Перевірка
        «це тека» мусить брати тип з ЦІЛОГО дерева, не з сирого вузла."""
        t = [{'id': 'p', 'name': 'P', 'children': [{'id': 'c', 'name': 'C'}]}]
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_ungroup(t, 'c')
        self.assertEqual(ctx.exception.code, 'bad-kind')

    def test_a_node_without_id_is_bad_id_not_a_crash(self):
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_ungroup([{'name': 'no id'}], 'x')
        self.assertEqual(ctx.exception.code, 'bad-id')
        with self.assertRaises(pm.TreeError) as ctx:
            pm.op_ungroup([None], 'x')
        self.assertEqual(ctx.exception.code, 'bad-id')


class TestLegacyWritersReportRuleCodes(Base):
    """Старі писарі відмовляють TreeError з кодом, а не голим ValueError: обробник
    відповідає через `_tree_error` без широкого `except ValueError`, який глушив би
    і чужі помилки."""

    def test_rename_unknown_page_is_not_found(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        with self.assertRaises(pm.TreeError) as ctx:
            pm.rename_page(self.d, pm.read_pages(self.d), 'nope', 'X')
        self.assertEqual(ctx.exception.code, 'not-found')

    def test_set_published_unknown_page_is_not_found(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        with self.assertRaises(pm.TreeError) as ctx:
            pm.set_published(self.d, pm.read_pages(self.d), 'nope', False)
        self.assertEqual(ctx.exception.code, 'not-found')

    def test_add_page_with_an_empty_name_is_empty_name(self):
        for name in ('', '   ', None):
            with self.assertRaises(pm.TreeError) as ctx:
                pm.add_page(self.d, [], name)
            self.assertEqual(ctx.exception.code, 'empty-name')
        self.assertEqual(os.listdir(self.d), [], 'відмова лишила слід на диску')

    def test_add_page_name_that_is_not_a_string_is_empty_name(self):
        """`name: 5` із тіла запиту інакше падав AttributeError на `.strip()` —
        обірване зʼєднання замість JSON-відмови."""
        for name in (5, ['x'], {'a': 1}, True):
            with self.subTest(name=name):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.add_page(self.d, [], name)
                self.assertEqual(ctx.exception.code, 'empty-name')
        self.assertEqual(os.listdir(self.d), [], 'відмова лишила слід на диску')

    def test_rename_page_name_that_is_not_a_string_is_empty_name(self):
        pm.write_pages(self.d, [{'id': 'a', 'name': 'A'}])
        for name in (5, ['x'], {'a': 1}, None):
            with self.subTest(name=name):
                with self.assertRaises(pm.TreeError) as ctx:
                    pm.rename_page(self.d, pm.read_pages(self.d), 'a', name)
                self.assertEqual(ctx.exception.code, 'empty-name')
        self.assertEqual(pm.read_pages(self.d)[0]['name'], 'A', 'відмова змінила імʼя')


class TestPagesLock(Base):
    def test_lock_file_lives_in_iteration_as_dotfile(self):
        # крапка спереду: експорт колегам і штамп зʼємки dot-файли пропускають
        with pm.pages_lock(self.d):
            self.assertTrue(os.path.isfile(os.path.join(self.d, '.pages.lock')))

    def test_lock_excludes_other_processes_and_is_released(self):
        """`bin/pages.py` — окремий процес: лок мусить бути справжнім flock, а не
        лише потоковим. Дочірній процес пробує взяти той самий файл без очікування."""
        with pm.pages_lock(self.d):
            self.assertEqual(_probe_lock(self.d), 3, 'лок не тримається')
        self.assertEqual(_probe_lock(self.d), 0, 'лок не відпущено після виходу')
        with self.assertRaises(RuntimeError):
            with pm.pages_lock(self.d):
                raise RuntimeError('зміна впала')
        self.assertEqual(_probe_lock(self.d), 0, 'лок не відпущено після винятку')
        with pm.pages_lock(self.d):        # і той самий потік може взяти його знову
            pass

    def test_missing_iteration_is_not_found_and_nothing_is_created(self):
        gone = os.path.join(self.d, 'it99')
        for call in (lambda: pm.mutate(gone, lambda pages: (pages, None)),
                     lambda: pm.pages_lock(gone).__enter__()):
            with self.assertRaises(pm.TreeError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, 'not-found')
        self.assertFalse(os.path.exists(gone), 'лок створив теку-привид')

    def test_nested_acquisition_in_one_thread_raises_instead_of_deadlocking(self):
        # timeout приглушено: у збитій версії (без гварда) другий захват упирається
        # в 'busy' за соті секунди, а не висить 10 с
        with mock.patch.object(pm, 'LOCK_TIMEOUT', 0.2):
            with pm.pages_lock(self.d):
                with self.assertRaises(RuntimeError):
                    with pm.pages_lock(self.d):
                        pass
                self.assertEqual(_probe_lock(self.d), 3, 'зовнішній лок зірвано')
            # mutate усередині mutate — той самий випадок
            with self.assertRaises(RuntimeError):
                pm.mutate(self.d, lambda pages: (pm.mutate(self.d, lambda p: (p, None)), None))

    def test_other_threads_wait_instead_of_tripping_the_reentrancy_guard(self):
        """Гвард потоковий: інший потік чекає, а не отримує RuntimeError."""
        done = []

        def other():
            with pm.pages_lock(self.d):
                done.append(True)

        with pm.pages_lock(self.d):
            th = threading.Thread(target=other)
            th.start()
            time.sleep(0.1)
            self.assertEqual(done, [])
        th.join(10)
        self.assertEqual(done, [True])

    def test_wait_is_bounded_and_ends_in_busy(self):
        holder = ('import fcntl, sys, time\n'
                  'fh = open(sys.argv[1], "a")\n'
                  'fcntl.flock(fh, fcntl.LOCK_EX)\n'
                  'print("ready", flush=True)\n'
                  'time.sleep(60)\n')
        proc = subprocess.Popen([sys.executable, '-c', holder,
                                 os.path.join(self.d, '.pages.lock')],
                                stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'ready')
            with mock.patch.object(pm, 'LOCK_TIMEOUT', 0.2):
                started = time.monotonic()
                with self.assertRaises(pm.TreeError) as ctx:
                    with pm.pages_lock(self.d):
                        pass
                self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(ctx.exception.code, 'busy')
        finally:
            proc.kill()
            proc.wait()
            proc.stdout.close()
        with pm.pages_lock(self.d):        # процес помер — лок знову вільний
            pass


class TestDuplicateIds(Base):
    """Дубль id у pages.json (злиття гілок у git його дає; validate зве це dup-id)
    не має коштувати даних: операція прибирає ОДИН вузол, а теку `<id>/` ділить
    із тим, що лишився, — стерти її означало б знищити файли живої сторінки."""

    DUP = [{'id': 'x', 'name': 'X1', 'kind': 'page'},
           {'id': 'x', 'name': 'X2', 'kind': 'page'}]

    def _write_raw(self, pages):
        with open(pm.pages_path(self.d), 'w', encoding='utf-8') as fh:
            json.dump({'pages': pages}, fh)
        self._index('x')

    def test_delete_does_not_report_a_dir_the_survivor_still_uses(self):
        out, removed = pm.op_delete(json.loads(json.dumps(self.DUP)), 'x', 'all')
        self.assertEqual([p['name'] for p in out], ['X2'])
        self.assertEqual(removed, [])

    def test_delete_still_reports_the_dirs_nobody_else_uses(self):
        tree = [{'id': 'x', 'name': 'X', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C1', 'kind': 'state'}]},
            {'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
                {'id': 'c', 'name': 'C2', 'kind': 'state'}]}]
        out, removed = pm.op_delete(tree, 'x', 'all')
        self.assertEqual(removed, ['x'])            # c ще живе під p

    def test_unwrap_does_not_report_a_dir_the_survivor_still_uses(self):
        tree = [{'id': 'x', 'name': 'X1', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]},
            {'id': 'x', 'name': 'X2', 'kind': 'page'}]
        out, removed = pm.op_unwrap(tree, 'x')
        self.assertEqual([p['id'] for p in out], ['c', 'x'])
        self.assertEqual(removed, [])

    def test_delete_on_disk_keeps_the_survivors_dir(self):
        self._write_raw(self.DUP)
        pm.mutate(self.d, lambda pages: pm.op_delete(pages, 'x', 'all'),
                  after=lambda removed: pm.remove_dirs(self.d, removed))
        self.assertEqual([p['name'] for p in pm.read_pages(self.d)], ['X2'])
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'x', 'index.html')),
                        'теку живої сторінки стерто')

    def test_unwrap_on_disk_keeps_the_survivors_dir(self):
        self._write_raw([{'id': 'x', 'name': 'X1', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]},
            {'id': 'x', 'name': 'X2', 'kind': 'page'}])
        self._index('c')
        pm.mutate(self.d, lambda pages: pm.op_unwrap(pages, 'x'),
                  after=lambda removed: pm.remove_dirs(self.d, removed))
        self.assertEqual([p['id'] for p in pm.read_pages(self.d)], ['c', 'x'])
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'x', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'c', 'index.html')))


class TestDeleteOrder(Base):
    def test_delete_writes_tree_before_removing_dirs(self):
        """Старий порядок (rmtree → write_pages) губив файли, якщо запис
        відмовляв: теки вже стерті, а pages.json лишався старим."""
        pages, a = pm.add_page(self.d, [], 'А')
        with open(pm.pages_path(self.d), 'rb') as fh:
            raw_before = fh.read()
        tree_before = json.dumps(pages)
        with mock.patch.object(pm, 'write_pages', side_effect=pm.TreeError('stale')):
            with self.assertRaises(pm.TreeError):
                pm.delete_page(self.d, pages, a['id'])
        self.assertTrue(os.path.isdir(os.path.join(self.d, a['id'])), 'тека стерта до запису')
        self.assertEqual(json.dumps(pages), tree_before, 'відмова зачепила список викликача')
        with open(pm.pages_path(self.d), 'rb') as fh:
            self.assertEqual(fh.read(), raw_before)

    def test_remove_dirs_never_wipes_the_iteration_itself(self):
        """'' (неявна main) у списку стирання означав би rmtree усієї ітерації."""
        self._index('a')
        self._index()
        self.assertEqual(pm.remove_dirs(self.d, ['', 'a']), [''])
        self.assertFalse(os.path.isdir(os.path.join(self.d, 'a')))
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'index.html')))

    def test_remove_dirs_refuses_ids_that_escape_the_iteration(self):
        it = os.path.join(self.d, 'it')
        os.makedirs(os.path.join(it, 'ok'))
        victim = os.path.join(self.d, 'victim')
        os.makedirs(victim)
        failed = pm.remove_dirs(it, ['../victim', 'a/b', 'ok'])
        self.assertTrue(os.path.isdir(victim), 'rmtree вийшов за межі ітерації')
        self.assertEqual(failed, ['../victim', 'a/b'])
        self.assertFalse(os.path.isdir(os.path.join(it, 'ok')))

    def test_remove_dirs_refuses_reserved_ids(self):
        """Легасі-сторінка з id `assets` дала б rmtree спільної теки ітерації."""
        reserved = sorted(pm.RESERVED_IDS - {pm.IMPLICIT_ID})
        for rid in reserved:
            os.makedirs(os.path.join(self.d, rid))
        os.makedirs(os.path.join(self.d, 'ok'))
        failed = pm.remove_dirs(self.d, reserved + ['ok'])
        self.assertEqual(failed, reserved)
        for rid in reserved:
            self.assertTrue(os.path.isdir(os.path.join(self.d, rid)), f'{rid} стерто')
        self.assertFalse(os.path.isdir(os.path.join(self.d, 'ok')))

    def test_remove_dirs_reports_failures_but_not_missing_dirs(self):
        with open(os.path.join(self.d, 'file'), 'w') as fh:     # файл, а не тека
            fh.write('x')
        failed = pm.remove_dirs(self.d, ['file', 'gone'])
        self.assertEqual(failed, ['file'])
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'file')))


if __name__ == '__main__':
    unittest.main()


class TestRestore(unittest.TestCase):
    """fb-01102026-71980b: зовнішній скрипт переписав pages.json своїм списком —
    теки й kind:state зникли. `op_restore` повертає організацію з попереднього
    дерева, не губить нових сторінок і не воскрешає видалених."""

    PREV = [
        {'id': 'f', 'name': 'Віджет', 'kind': 'folder', 'isGroup': True, 'children': [
            {'id': 'a', 'name': 'Картка', 'kind': 'page', 'children': [
                {'id': 's', 'name': 'Помилка', 'kind': 'state'}]},
            {'id': 'b', 'name': 'Особа', 'kind': 'page'}]},
        {'id': 'c', 'name': 'Пошук', 'kind': 'page'}]

    def test_restores_folder_and_state_keeps_new_page(self):
        cur = [{'id': 'a', 'name': 'a', 'kind': 'page'}, {'id': 's', 'name': 's', 'kind': 'page'},
               {'id': 'b', 'name': 'b', 'kind': 'page'}, {'id': 'c', 'name': 'c', 'kind': 'page'},
               {'id': 'd', 'name': 'Нова', 'kind': 'page'}]
        out, restored = pm.op_restore(cur, self.PREV)
        self.assertEqual(restored, ['f'])
        self.assertEqual([n['id'] for n in out], ['f', 'c', 'd'])
        f = out[0]
        self.assertEqual([n['id'] for n in f['children']], ['a', 'b'])
        self.assertEqual(f['children'][0]['children'][0], {'id': 's', 'name': 'Помилка', 'kind': 'state'})
        pm.validate(out)

    def test_page_deleted_by_script_is_not_resurrected(self):
        cur = [{'id': 'a', 'name': 'a', 'kind': 'page'}, {'id': 'c', 'name': 'c', 'kind': 'page'}]
        out, _ = pm.op_restore(cur, self.PREV)
        ids = [f['page']['id'] for f in pm.flatten(out)]
        self.assertNotIn('b', ids)
        self.assertNotIn('s', ids)
        self.assertEqual(ids, ['f', 'a', 'c'])

    def test_children_of_vanished_page_are_lifted(self):
        prev = [{'id': 'x', 'name': 'X', 'kind': 'page', 'children': [
            {'id': 'k', 'name': 'K', 'kind': 'folder', 'children': [
                {'id': 'y', 'name': 'Y', 'kind': 'page'}]}]}]
        cur = [{'id': 'y', 'name': 'y', 'kind': 'page'}]
        out, restored = pm.op_restore(cur, prev)
        self.assertEqual(restored, ['k'])
        self.assertEqual([f['page']['id'] for f in pm.flatten(out)], ['k', 'y'])

    def test_same_tree_is_noop(self):
        out, restored = pm.op_restore(json.loads(json.dumps(self.PREV)), self.PREV)
        self.assertEqual(restored, [])
        self.assertEqual(out, self.PREV)

    def test_duplicate_folder_id_in_prev_is_placed_once(self):
        """Ревʼю 1.47, M7: дубль id теки в `prev` (ручна правка) не дає дубля в дереві."""
        prev = [{'id': 'f', 'name': 'F', 'kind': 'folder', 'children': [{'id': 'a', 'name': 'A', 'kind': 'page'}]},
                {'id': 'f', 'name': 'F2', 'kind': 'folder', 'children': [{'id': 'b', 'name': 'B', 'kind': 'page'}]}]
        cur = [{'id': 'a', 'name': 'a', 'kind': 'page'}, {'id': 'b', 'name': 'b', 'kind': 'page'}]
        out, restored = pm.op_restore(cur, prev)
        self.assertEqual(restored, ['f'])
        self.assertEqual([f['page']['id'] for f in pm.flatten(out)], ['f', 'a', 'b'])

    def test_state_left_without_page_becomes_page(self):
        """Ревʼю 1.47, M8: стан, чия сторінка зникла, — не «нічий стан» (validate
        відмовив би всьому відновленню), а сторінка."""
        prev = [{'id': 'x', 'name': 'X', 'kind': 'page', 'children': [{'id': 's', 'name': 'S', 'kind': 'state'}]}]
        cur = [{'id': 's', 'name': 's', 'kind': 'page'}]
        out, _ = pm.op_restore(cur, prev)
        self.assertEqual(out, [{'id': 's', 'name': 'S', 'kind': 'page'}])

    def test_bad_prev_is_bad_prev(self):
        for bad in (None, {}, 'x', [1], [{'id': 'f', 'children': 'nope'}]):
            with self.subTest(bad=bad), self.assertRaises(pm.TreeError) as ctx:
                pm.op_restore([], bad)
            self.assertEqual(ctx.exception.code, 'bad-prev')

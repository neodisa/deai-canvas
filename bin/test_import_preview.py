"""Тести `bin/import_preview.py` — імпорт ітерації з ЧУЖОГО опублікованого превʼю.

fb-29092026-210ec1: дві машини публікували одну задачу в різні Vercel-проєкти, і
ітерації колеги довелось переносити руками — зняти сніпет коментатора й гейт,
відновити title з `__origTitle`. Тепер це команда. Перевіряємо:
  · вирізання вставок публікації — КОЛОВИМ тестом на тих самих функціях, якими
    `serve.build_preview` їх вставляє (розійдуться — тест червоніє);
  · дерево сторінок із `manifest.outline`;
  · збирання файлів за посиланнями (статичний хостинг переліку не віддає);
  · ітерація — ЧУЖА (джерело — превʼю) + моя робоча копія поруч (правило
    15.09.2026: робота не починається поверх чужої ітерації).
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
import import_preview as ip  # noqa: E402
import serve  # noqa: E402

PAGE = ('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
        '<title>Картка «Ромашка»</title><link rel="stylesheet" href="../assets/app.css">'
        '</head><body><h1>Картка</h1><img src="../icons/a.svg" srcset="../icons/a.svg 1x, ../icons/a@2x.svg 2x">'
        '<script type="module" src="../main.js"></script></body></html>')


def published(html, depth_up='../'):
    """Рівно те, що робить `serve.build_preview` зі сторінкою."""
    out = serve.inject_comment_layer(html, 'chan', f'{depth_up}comment-layer', version='1/kartka')
    return serve._inject_gate(out, serve.gate_html('t', '1100'))


MODULE_CFG = {'endpoint': 'http://127.0.0.1:4777', 'pubkey': 'pk-OPEN', 'channel': 'deai/other-space/t1'}


def published_module(html, depth_up='../', gated=True, cfg=None):
    """Рівно те, що робить `serve.build_preview` зі сторінкою, коли превʼю несе коментарі МОДУЛЯ (2b-2): сніпет модуля
    (без інспектора й вкладок) і, коли є пароль, гейт. Модуль публікації без пароля — БЕЗ гейта (`gated=False`)."""
    out = serve.inject_module_comment_layer(
        html, f'{depth_up}comment-layer', [f'{depth_up}comment-layer/adapter.js'], cfg or MODULE_CFG,
        version='1/kartka', inspector=False, audiences=False)
    return serve._inject_gate(out, serve.gate_html('t', '1100')) if gated else out


class StripModuleComments(unittest.TestCase):
    """Сторінка превʼю з коментарями МОДУЛЯ (2b-2): імпорт знімає її сніпет так само, як сніпет ЛІГА, — із гейтом і без."""

    def test_a_gated_module_page_roundtrips_byte_for_byte(self):
        self.assertEqual(ip.strip_publish(published_module(PAGE)), (PAGE, True))

    def test_an_ungated_module_page_roundtrips_byte_for_byte(self):
        """Модуль публікації без пароля: гейта нема, `<title>` не чіпали — лишається вирізати сам сніпет."""
        html = published_module(PAGE, gated=False)
        self.assertIn('__deaiCommentsCfg', html, 'контроль: сніпет у сторінці справді є')
        self.assertNotIn('authgate', html)
        self.assertEqual(ip.strip_publish(html), (PAGE, True))

    def test_a_page_without_a_title_or_a_body_tag_roundtrips_too(self):
        for gated in (True, False):
            with self.subTest(gated=gated):
                page = PAGE.replace('<title>Картка «Ромашка»</title>', '')
                self.assertEqual(ip.strip_publish(published_module(page, gated=gated)), (page, True))
                bare = '<div>без body</div>'
                self.assertEqual(ip.strip_publish(published_module(bare, gated=gated)), (bare, True))

    def test_the_title_comes_back_from_the_gate_only_when_there_was_a_gate(self):
        page = PAGE.replace('<title>Картка «Ромашка»</title>', '<title>R&amp;D «Суди»</title>')
        self.assertEqual(ip.strip_publish(published_module(page, gated=True)), (page, True))
        self.assertEqual(ip.strip_publish(published_module(page, gated=False)), (page, True))

    def test_page_depths_and_hostile_config_values_do_not_confuse_the_cut(self):
        hostile = {'endpoint': '</script><script>alert(1)</script>\u2028&"\'\\', 'pubkey': 'x', 'channel': 'a/b'}
        for depth_up in ('', '../', '../../'):
            for gated in (True, False):
                with self.subTest(depth_up=depth_up, gated=gated):
                    self.assertEqual(ip.strip_publish(published_module(PAGE, depth_up, gated, hostile)), (PAGE, True))

    def test_both_kinds_of_snippet_are_cut_by_their_own_template_bounds(self):
        """Шаблони модуля й ЛІГА різні: межі беруться з обох, а не вгадуються."""
        self.assertTrue(ip._MODULE_START.startswith('\n<script>\nwindow.__clDown'))
        self.assertNotEqual(ip._MODULE_START, ip._SNIPPET_START)
        self.assertIn(ip._MODULE_START, ip._SNIPPET_STARTS)
        self.assertTrue(ip._module_end().endswith('</script>'))
        self.assertEqual(ip.strip_publish(published(PAGE)), (PAGE, True), 'контроль: ЛІГА лишилась як була')

    def test_a_drifted_module_template_is_not_stripped_and_says_so(self):
        """Шаблон змінився, межі не збіглись: `strip_publish` чесно каже «не вирізано» (а імпорт тоді зупиняється)."""
        for gated in (True, False):
            with self.subTest(gated=gated):
                html = published_module(PAGE, gated=gated).replace('function (why) {', 'function (reason) {', 1)
                self.assertFalse(ip.strip_publish(html)[1])


class Strip(unittest.TestCase):
    def test_roundtrip_restores_page_byte_for_byte(self):
        clean, ok = ip.strip_publish(published(PAGE))
        self.assertTrue(ok)
        self.assertEqual(clean, PAGE)

    def test_page_without_title_roundtrips_too(self):
        page = PAGE.replace('<title>Картка «Ромашка»</title>', '')
        self.assertEqual(ip.strip_publish(published(page)), (page, True))

    def test_page_without_injections_is_untouched_and_said(self):
        self.assertEqual(ip.strip_publish(PAGE), (PAGE, False))

    # Назва з сутностями. `serve._inject_gate` кладе в `__origTitle` РОЗЕКРАНОВАНИЙ текст
    # (`document.title` — текст, не розмітка), а імпорт пише його назад у `<title>` як РОЗМІТКУ:
    # без екранування `A &lt;/title&gt;&lt;b&gt;x&lt;/b&gt;` ставала справжньою розміткою в ітерації.
    # (Єдине, що не відновлюється: видима назва з ЛІТЕРАЛЬНОЮ сутністю — вихідний `&amp;amp;`. У новому
    # форматі в `__origTitle` це текст `&amp;`, а в старому сирому — готова сутність: розрізнити їх
    # нічим, і старі превʼю не подвоюємо — це важливіше за таку назву.)
    ENTITY_TITLES = ('R&amp;D', 'A &lt;/title&gt;&lt;b&gt;x&lt;/b&gt;', '&lt;/script&gt;&lt;img src=x&gt;',
                     'Тарифи &laquo;Про&raquo; &#39;x&#39;', 'a &amp; b &lt; c',
                     'Фін. &quot;звіт&quot; &#x26; ко')

    def entity_page(self, src):
        return PAGE.replace('<title>Картка «Ромашка»</title>', f'<title>{src}</title>')

    @staticmethod
    def title_of(page):
        m = re.search(r'<title>(.*?)</title>', page, flags=re.S)
        return m.group(1) if m else None

    def test_an_entity_title_never_becomes_markup_after_import(self):
        import html
        for src in self.ENTITY_TITLES:
            with self.subTest(title=src):
                page = self.entity_page(src)
                clean, ok = ip.strip_publish(published(page))
                self.assertTrue(ok)
                inner = self.title_of(clean)
                self.assertIsNotNone(inner)
                self.assertNotIn('<', inner, 'назва стала розміткою')
                self.assertNotIn('>', inner)
                self.assertEqual(clean.count('<title>'), 1)
                self.assertEqual(clean.count('</title>'), 1)
                self.assertNotIn('<b>x</b>', clean)
                self.assertNotIn('<img src=x>', clean)
                # тут видима назва та сама, що була (сутності ↔ символи)
                self.assertEqual(html.unescape(inner), html.unescape(src))
                # решта сторінки — байт у байт; відрізняється лише запис назви
                self.assertEqual(clean.replace(f'<title>{inner}</title>', ''),
                                 page.replace(f'<title>{src}</title>', ''))

    def test_the_common_entity_titles_come_back_byte_for_byte(self):
        for src in ('R&amp;D', 'A &lt;/title&gt;&lt;b&gt;x&lt;/b&gt;', 'a &amp; b &lt; c'):
            with self.subTest(title=src):
                page = self.entity_page(src)
                self.assertEqual(ip.strip_publish(published(page)), (page, True))

    def test_a_title_with_a_lone_ampersand_or_angle_brackets_is_escaped_not_doubled(self):
        """Сирий `&` (не сутність) → `&amp;`, а вже екранований не подвоюється; `<`/`>` — завжди сутності."""
        import html
        for src, want in (('AT&T', 'AT&amp;T'), ('R&amp;D &amp; Q&A', 'R&amp;D &amp; Q&amp;A'),
                          ('a <b> c', 'a &lt;b&gt; c')):
            with self.subTest(title=src):
                clean, ok = ip.strip_publish(published(self.entity_page(src)))
                self.assertTrue(ok)
                self.assertEqual(self.title_of(clean), want)
                self.assertEqual(html.unescape(want), html.unescape(src))


class Outline(unittest.TestCase):
    def test_flat_outline_becomes_tree_of_one_iteration(self):
        outline = [
            {'it': 'it2', 'key': 'w', 'name': 'Віджет', 'kind': 'folder', 'depth': 0},
            {'it': 'it2', 'key': 'kartka', 'name': 'Картка', 'kind': 'page', 'depth': 1},
            {'it': 'it2', 'key': 's-err', 'name': 'Помилка', 'kind': 'state', 'depth': 2},
            {'it': 'it2', 'key': 'osoba', 'name': 'Особа', 'kind': 'page', 'depth': 0},
            {'it': 'it1', 'key': 'old', 'name': 'Стара', 'kind': 'page', 'depth': 0},
        ]
        tree = ip.outline_tree(outline, 'it2')
        self.assertEqual(tree, [
            {'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'children': [
                {'id': 'kartka', 'name': 'Картка', 'kind': 'page', 'children': [
                    {'id': 's-err', 'name': 'Помилка', 'kind': 'state'}]}]},
            {'id': 'osoba', 'name': 'Особа', 'kind': 'page'}])


class Refs(unittest.TestCase):
    def test_html_css_js_references(self):
        self.assertEqual(ip.refs(PAGE, 'html'),
                         {'../assets/app.css', '../icons/a.svg', '../icons/a@2x.svg', '../main.js'})
        self.assertEqual(ip.refs("@import 'base.css'; a{background:url(\"../img/bg.png\")} b{src:url(f.woff2)}", 'css'),
                         {'base.css', '../img/bg.png', 'f.woff2'})
        self.assertEqual(ip.refs('import("./chunk-AB12.js");const i="assets/x.svg";fetch("https://cdn/x.js")', 'js'),
                         {'./chunk-AB12.js', 'assets/x.svg'})

    def test_external_data_and_anchor_refs_are_ignored(self):
        html = '<a href="#top"></a><img src="data:image/png;base64,AA"><script src="https://cdn.x/y.js"></script>'
        self.assertEqual(ip.refs(html, 'html'), set())

    def test_root_relative_and_encoded_anchor_refs_are_not_iteration_files(self):
        """Реальний boss-interface it15: 252 «не знайдено» — шляхи даних від кореня
        сайту (`/trademarks/…jpg`, 404 і в самому превʼю) та `%23n` (закодований якір)."""
        self.assertEqual(ip.refs('const a="/trademarks/1.jpg";', 'js'), set())
        self.assertEqual(ip.refs('<a href="%23n">x</a><img src="img/a%20b.png">', 'html'), {'img/a b.png'})


class ImportFixture(unittest.TestCase):
    """Фікстура сайту превʼю колеги й тека задачі: спільна основа `ImportIteration` і `ImportModuleComments`. Тестів нема."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, 'iterations', 'it1'))
        with open(os.path.join(self.d, 'iterations', 'it1', 'index.html'), 'w') as f:
            f.write('<html><body>моя</body></html>')
        with open(os.path.join(self.d, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.10.2026 10:00', 'note': 'моя', 'published': True}]}, f)
        base = 'https://pv-x.vercel.app'
        man = {'iters': [{'id': 'it3', 'num': 3, 'note': 'колега'}, {'id': 'it5', 'num': 5, 'note': 'остання'}],
               'pages': [{'id': 'it5/kartka', 'it': 'it5', 'key': 'kartka', 'name': 'Картка', 'depth': 0,
                          'path': 'it5/kartka/index.html'}],
               'outline': [{'it': 'it5', 'key': 'kartka', 'name': 'Картка', 'kind': 'page', 'depth': 0}]}
        self.site = {
            f'{base}/manifest.json': json.dumps(man).encode(),
            f'{base}/it5/kartka/index.html': published(PAGE).encode(),
            f'{base}/it5/assets/app.css': b"@import 'fonts.css';.x{background:url(../icons/bg.png)}",
            f'{base}/it5/assets/fonts.css': b'',
            f'{base}/it5/icons/a.svg': b'<svg/>',
            f'{base}/it5/icons/bg.png': b'PNG',
            f'{base}/it5/main.js': b'import("./chunk-1.js")',
            f'{base}/it5/chunk-1.js': b'export const x=1',
        }
        self.base = base

    def fetch(self, url):
        if url in getattr(self, 'down', ()):
            raise ip.FetchError(f'{url}: timed out')
        if url in self.site:
            return self.site[url]
        raise ip.FetchError(f'404 {url}', code=404)


class ImportIteration(ImportFixture):
    def test_404_in_source_is_not_an_import_failure_but_network_is(self):
        """Усе, що превʼю віддає 404, бите й у колеги (на boss-interface it15 — 200
        шрифтів із вшитого beasties CSS, на вигляд не впливає). Справжній збій
        імпорту — лише мережа: його кажемо окремо й гучно."""
        self.down = {f'{self.base}/it5/chunk-1.js'}
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual(rep['broken'], ['icons/a@2x.svg'])
        self.assertEqual(rep['failed'], ['chunk-1.js'])

    def test_imports_latest_iteration_as_foreign_plus_my_working_copy(self):
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertEqual((rep['imported'], rep['working']), ('it2', 'it3'))
        self.assertEqual(rep['source_it'], 'it5')
        self.assertEqual(rep['broken'], ['icons/a@2x.svg'])
        self.assertEqual(rep['failed'], [])
        root = os.path.join(self.d, 'iterations', 'it2')
        with open(os.path.join(root, 'kartka', 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), PAGE, 'сторінка не очищена від вставок публікації')
        for rel in ('assets/app.css', 'assets/fonts.css', 'icons/bg.png', 'main.js', 'chunk-1.js'):
            self.assertTrue(os.path.isfile(os.path.join(root, rel)), rel)
        self.assertFalse(os.path.exists(os.path.join(root, 'comment-layer')))
        with open(os.path.join(root, 'pages.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['pages'][0]['id'], 'kartka')
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it3', 'kartka', 'index.html')))
        with open(os.path.join(self.d, 'iterations.json'), encoding='utf-8') as f:
            its = {i['id']: i for i in json.load(f)['iterations']}
        self.assertEqual(its['it2']['from_preview'], f'{self.base} · it5')
        self.assertTrue(its['it2']['author_key'].startswith('preview:'))
        self.assertFalse(serve.iteration_is_mine(its['it2'], 'my-key'), 'імпорт виглядає моїм')
        self.assertEqual(its['it3']['from'], 'it2')
        self.assertFalse(its['it2']['published'])

    def test_explicit_source_iteration_and_unknown_one(self):
        self.site[f'{self.base}/it3/index.html'] = published(PAGE.replace('../', ''), '').encode()
        man = json.loads(self.site[f'{self.base}/manifest.json'])
        man['pages'].append({'id': 'it3', 'it': 'it3', 'key': 'main', 'name': 'Головна', 'depth': 0,
                             'path': 'it3/index.html'})
        self.site[f'{self.base}/manifest.json'] = json.dumps(man).encode()
        rep = ip.import_iteration(self.d, self.base, src_it='it3', fetch=self.fetch)
        self.assertEqual(rep['source_it'], 'it3')
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, src_it='it9', fetch=self.fetch)
        self.assertIn('it9', str(ctx.exception))

    def test_hostile_manifest_cannot_write_outside_the_iteration(self):
        """Ревʼю 1.51 (висока): шлях сторінки з manifest.json — чужі дані. `..`,
        абсолютний шлях чи `%2e%2e` не сміють вивести запис за теку ітерації
        (інакше «превʼю колеги» перезаписало б ~/.zshrc)."""
        for bad in ('it5/../../../evil.html', '/etc/evil.html', 'it5/%2e%2e/%2e%2e/evil.html',
                    'it5/kartka/../../../../evil.html'):
            man = json.loads(self.site[f'{self.base}/manifest.json'])
            man['pages'] = [{'id': 'x', 'it': 'it5', 'key': 'x', 'name': 'x', 'depth': 0, 'path': bad}]
            self.site[f'{self.base}/manifest.json'] = json.dumps(man).encode()
            self.site[f'{self.base}/{bad.lstrip("/")}'] = b'<html>evil</html>'
            with self.subTest(path=bad), self.assertRaises(ip.ImportError_):
                ip.import_iteration(self.d, self.base, fetch=self.fetch)
        parent = os.path.dirname(self.d)
        self.assertFalse(any(n == 'evil.html' for n in os.listdir(parent)), 'файл записано поза задачею')

    def test_crawled_links_cannot_leave_the_iteration(self):
        """Посилання зі сторінки на `../../x` не стає файлом поза ітерацією."""
        self.site[f'{self.base}/it5/kartka/index.html'] = published(
            PAGE.replace('../main.js', '../../../../escape.js')).encode()
        self.site[f'{self.base}/escape.js'] = b'evil'
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertNotIn('escape.js', os.listdir(os.path.dirname(self.d)))
        self.assertFalse(any('..' in p for p in rep['broken'] + rep['failed']))

    def test_oversized_file_is_failed_not_written_and_total_is_capped(self):
        """TD-36: чуже превʼю не сміє закачати гігабайти — файл понад ліміт не
        пишемо (його видно в «не скачано»), сумарний обсяг понад ліміт — відмова."""
        self.site[f'{self.base}/it5/icons/bg.png'] = b'x' * (ip.MAX_FILE + 1)
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('icons/bg.png', rep['failed'])
        old = ip.MAX_TOTAL
        try:
            ip.MAX_TOTAL = 10
            with self.assertRaises(ip.ImportError_):
                ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        finally:
            ip.MAX_TOTAL = old

    def test_redirect_to_another_host_is_refused(self):
        h = ip.SameHostRedirect()
        req = ip.urllib.request.Request('https://pv-1.vercel.app/it5/a.css')
        with self.assertRaises(ip.urllib.error.HTTPError):
            h.redirect_request(req, None, 302, 'Found', {}, 'https://evil.example/a.css')
        self.assertIsNotNone(h.redirect_request(req, None, 302, 'Found', {}, 'https://pv-1.vercel.app/it5/b.css'))

    def test_dry_run_writes_nothing(self):
        before = sorted(os.listdir(os.path.join(self.d, 'iterations')))
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'iterations'))), before)
        self.assertGreater(rep['files'], 5)


class ImportModuleComments(ImportFixture):
    """Імпорт цілої ітерації з превʼю з коментарями модуля: та сама фікстура сайту, що в `ImportIteration`, — але
    сторінка джерела несе сніпет модуля."""

    def serve_page(self, html):
        self.site[f'{self.base}/it5/kartka/index.html'] = html.encode()

    def written(self):
        root = os.path.join(self.d, 'iterations')
        out = {}
        for dp, _dirs, files in os.walk(root):
            for f in files:
                with open(os.path.join(dp, f), 'rb') as fh:
                    out[os.path.relpath(os.path.join(dp, f), root)] = fh.read()
        return out

    def test_a_gated_page_with_module_comments_imports_clean(self):
        self.serve_page(published_module(PAGE))
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertEqual(rep['unstripped'], [])
        with open(os.path.join(self.d, 'iterations', rep['imported'], 'kartka', 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), PAGE)

    def test_an_ungated_page_with_module_comments_imports_clean_and_carries_nothing_of_the_other_space(self):
        self.serve_page(published_module(PAGE, gated=False))
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertEqual(rep['unstripped'], [])
        for name, data in self.written().items():
            for mark in (b'__deaiCommentsCfg', b'DeaiComments', b'4777', b'pk-OPEN', b'deai/other-space'):
                self.assertNotIn(mark, data, f'{name}: {mark!r}')
            self.assertNotIn(b'comment-layer', data, name)

    def test_the_two_working_copies_do_not_get_a_second_layer_on_the_next_publish(self):
        """Імпортована ітерація публікується знову: коментатор ЇЇ простору додається РІВНО один раз."""
        self.serve_page(published_module(PAGE, gated=False))
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        with open(os.path.join(self.d, 'iterations', rep['working'], 'kartka', 'index.html'), encoding='utf-8') as f:
            again = serve.inject_module_comment_layer(
                f.read(), '../comment-layer', ['../comment-layer/adapter.js'],
                {'endpoint': 'http://127.0.0.1:1', 'channel': 'deai/mine/t1'}, version='1/kartka')
        self.assertEqual(again.count('window.__deaiCommentsCfg ='), 1)
        self.assertEqual(again.count('comment-layer.min.js'), 1)

    def test_a_page_whose_module_snippet_is_not_recognised_is_refused_and_nothing_is_written(self):
        """Запобіжник, незалежний від шаблонів: коли межі не збіглись, а сніпет (його конфіг) лишився, — імпорт стоп."""
        drifted = published_module(PAGE, gated=False).replace('function (why) {', 'function (reason) {', 1)
        self.serve_page(drifted)
        before = self.written()
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertIn('kartka/index.html', str(ctx.exception))
        self.assertIn('коментарів модуля', str(ctx.exception))
        self.assertEqual(self.written(), before, 'зупинений імпорт щось записав')
        with open(os.path.join(self.d, 'iterations.json'), encoding='utf-8') as f:
            self.assertEqual([i['id'] for i in json.load(f)['iterations']], ['it1'])

    def test_a_page_that_merely_mentions_the_adapter_global_is_refused_too(self):
        """Лишився хоч слід адаптера (`DeaiComments`) — не пишемо: це чужий код у ітерації."""
        self.serve_page(published(PAGE).replace('</body>', '<script>window.DeaiComments = {};</script></body>', 1))
        with self.assertRaises(ip.ImportError_):
            ip.import_iteration(self.d, self.base, fetch=self.fetch)


def legacy_wrapper(data, pw='1100'):
    """Обгортка превʼю старого формату (04.08–02.09.2026): дані інлайном у `var D`."""
    return ('<!DOCTYPE html><html><head><title>t</title></head><body><script>'
            f'var D={serve.js_literal(data)},PW={serve.js_literal(pw)},P=D.pages,I=D.iters,cur=null;'
            '</script></body></html>')


class LegacyWrapper(unittest.TestCase):
    """fb-09102026-8b12a5: превʼю до 02.09.2026 не мають manifest.json — дані в обгортці."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, 'iterations', 'it1'))
        with open(os.path.join(self.d, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.10.2026 10:00', 'note': 'моя', 'published': True}]}, f)
        self.base = 'https://pv-old.vercel.app'
        self.data = {
            'iters': [{'id': 'it2', 'label': 'Іт.2'}, {'id': 'it4', 'label': 'Іт.4'}],
            'pages': [
                {'id': 'it4', 'it': 'it4', 'name': 'Головна', 'depth': 0, 'path': 'it4/index.html'},
                {'id': 'it4/kartka', 'it': 'it4', 'name': 'Картка }," },PW=', 'depth': 0, 'path': 'it4/kartka/index.html'},
                {'id': 'it4/kartka-empty', 'it': 'it4', 'name': 'Порожньо', 'depth': 1, 'path': 'it4/kartka-empty/index.html'},
                {'id': 'it2', 'it': 'it2', 'name': 'Стара', 'depth': 0, 'path': 'it2/index.html'},
            ]}
        self.site = {
            f'{self.base}/': legacy_wrapper(self.data, pw='секрет-1100').encode(),
            f'{self.base}/it4/index.html': published(PAGE.replace('../', ''), '').encode(),
            f'{self.base}/it4/kartka/index.html': published(PAGE).encode(),
            f'{self.base}/it4/kartka-empty/index.html': published(PAGE).encode(),
            f'{self.base}/it4/assets/app.css': b'', f'{self.base}/it4/icons/a.svg': b'<svg/>',
            f'{self.base}/it4/main.js': b'', f'{self.base}/it4/icons/a@2x.svg': b'<svg/>',
        }
        self.down = set()
        self.log = []

    def fetch(self, url):
        self.log.append(url)
        if url in self.down:
            raise ip.FetchError(f'{url}: timed out')
        if url in self.site:
            return self.site[url]
        raise ip.FetchError(f'404 {url}', code=404)

    def snapshot(self):
        """Усе, що лежить у теці задачі: {шлях: байти}."""
        out = {}
        for dp, _, fs in os.walk(self.d):
            for name in fs:
                with open(os.path.join(dp, name), 'rb') as f:
                    out[os.path.relpath(os.path.join(dp, name), self.d)] = f.read()
        return out

    def wrapper_with(self, js_data):
        """Обгортка, де після `var D=` стоїть СИРИЙ текст (кривий JSON теж)."""
        return ('<!DOCTYPE html><html><head><title>t</title></head><body><script>'
                f'var D={js_data},PW="{SECRET}",P=D.pages;</script></body></html>').encode()

    def test_legacy_manifest_shape(self):
        man = ip.legacy_manifest(self.data)
        self.assertEqual([(i['id'], i['num']) for i in man['iters']], [('it2', 2), ('it4', 4)])
        self.assertEqual([(p['it'], p['key'], p['path']) for p in man['pages'] if p['it'] == 'it4'],
                         [('it4', 'main', 'it4/index.html'), ('it4', 'kartka', 'it4/kartka/index.html'),
                          ('it4', 'kartka-empty', 'it4/kartka-empty/index.html')])
        self.assertEqual([(r['key'], r['depth']) for r in man['outline'] if r['it'] == 'it4'],
                         [('main', 0), ('kartka', 0), ('kartka-empty', 1)])

    def test_imports_latest_from_legacy_wrapper_with_tree(self):
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertEqual((rep['source_it'], rep['format']), ('it4', 'legacy-wrapper'))
        root = os.path.join(self.d, 'iterations', rep['imported'])
        self.assertTrue(os.path.isfile(os.path.join(root, 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(root, 'kartka', 'index.html')))
        with open(os.path.join(root, 'pages.json'), encoding='utf-8') as f:
            tree = json.load(f)['pages']
        kartka = next(p for p in tree if p['id'] == 'kartka')
        self.assertEqual([c['id'] for c in kartka.get('children', [])], ['kartka-empty'],
                         'стан під сторінкою загубився — дерево не відновлено за глибиною')

    def test_password_from_legacy_wrapper_goes_nowhere(self):
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertNotIn('секрет-1100', json.dumps(rep, ensure_ascii=False))
        for dp, _, fs in os.walk(self.d):
            for name in fs:
                with open(os.path.join(dp, name), 'rb') as f:
                    self.assertNotIn('секрет-1100'.encode(), f.read(), os.path.join(dp, name))

    def test_network_error_on_manifest_is_not_a_reason_to_guess(self):
        self.down = {f'{self.base}/manifest.json'}
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('manifest.json', str(ctx.exception))

    def test_no_manifest_and_no_legacy_data_says_both(self):
        self.site[f'{self.base}/'] = b'<html><body>not a canvas</body></html>'
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('var D', str(ctx.exception))

    def test_manifest_preview_reports_its_format(self):
        self.site[f'{self.base}/manifest.json'] = json.dumps(ip.legacy_manifest(self.data)).encode()
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual(rep['format'], 'manifest')

    # ── ревʼю P1 · I1: старі шаблони сніпета, гейт із паролем ────────────────────

    def test_old_snippet_pages_import_without_the_password(self):
        """Превʼю 04.08–27.08.2026 мають СТАРИЙ сніпет (з Supabase-тегом першим). Якщо
        його не зняти, гейт із ПАРОЛЕМ відкритим текстом потрапляє у файли імпорту — а
        канвас потім комітить їх у GitLab."""
        for variant in ('38b4080', '5ed9bf7'):
            with self.subTest(variant=variant):
                self.setUp()
                for rel, html in (('it4/index.html', PAGE.replace('../', '')),
                                  ('it4/kartka/index.html', PAGE), ('it4/kartka-empty/index.html', PAGE)):
                    self.site[f'{self.base}/{rel}'] = published_old(html, variant).encode()
                self.assertIn(SECRET.encode(), self.site[f'{self.base}/it4/kartka/index.html'], 'фікстура без пароля')
                rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
                self.assertEqual(rep['unstripped'], [])
                root = os.path.join(self.d, 'iterations', rep['imported'])
                with open(os.path.join(root, 'kartka', 'index.html'), encoding='utf-8') as f:
                    self.assertEqual(f.read(), PAGE)
                for path, data in self.snapshot().items():
                    self.assertNotIn(SECRET.encode(), data, path)
                    self.assertNotIn(b'authgate', data, path)

    def test_page_with_unknown_gate_is_refused_before_anything_is_written(self):
        """Запобіжник, незалежний від шаблонів: сторінка, з якої гейт зняти не вдалось
        (невідомий шаблон), не пишеться — інакше пароль потрапив би у файли. І нічого
        не пишеться ВЗАГАЛІ: ні файлів, ні теки ітерації, ні запису в iterations.json."""
        unknown_start = serve._inject_gate(
            serve._insert_before_body(PAGE, '\n<script src="https://example.com/other-layer.js"></script>'),
            serve.gate_html('t', SECRET))
        unknown_end = published_old(PAGE, '5ed9bf7').replace('})();</script>', '})();/*v2*/</script>')
        for name, page in (('невідомий початок', unknown_start), ('невідомий кінець гейта', unknown_end)):
            for dry in (True, False):
                with self.subTest(case=name, dry_run=dry):
                    self.setUp()
                    self.site[f'{self.base}/it4/kartka/index.html'] = page.encode()
                    before = self.snapshot()
                    with self.assertRaises(ip.ImportError_) as ctx:
                        ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=dry)
                    self.assertIn('гейтом', str(ctx.exception))
                    self.assertIn('kartka/index.html', str(ctx.exception))
                    self.assertNotIn(SECRET, str(ctx.exception))
                    self.assertEqual(self.snapshot(), before, 'щось записано попри відмову')

    # ── ревʼю P1 · I2: криві дані старої обгортки — помилка, не traceback ────────

    def test_malformed_legacy_data_is_an_error_not_a_traceback(self):
        unexpected = 'дані старої обгортки (var D) мають несподіваний вигляд'
        digits = '9' * 5000
        cases = [
            ('D — масив', '[1,2]', 'var D'),
            ('D — null', 'null', 'var D'),
            ('iters — не список', '{"iters": 5, "pages": []}', unexpected),
            ('pages — рядок', '{"iters": [], "pages": "x"}', unexpected),
            ('елементи — не обʼєкти', '{"iters": [1, "a", null], "pages": [1, null, "p"]}', 'немає ітерацій'),
            ('id/it — не рядки', '{"iters": [{"id": 5}, {"id": null}], "pages": [{"id": 7, "it": [1]}]}', 'немає ітерацій'),
            ('id ітерації з 5000 цифр',
             f'{{"iters": [{{"id": "it{digits}"}}], "pages": [{{"id": "it{digits}", "it": "it{digits}", '
             f'"name": "x", "depth": 0, "path": "p"}}]}}', 'підозрілий шлях'),
            ('глибока вкладеність масивів', '[' * 100000, 'var D'),
            ('глибока вкладеність обʼєктів', '{"a":' * 100000, 'var D'),
        ]
        for name, js, fragment in cases:
            with self.subTest(case=name):
                self.site[f'{self.base}/'] = self.wrapper_with(js)
                with self.assertRaises(ip.ImportError_) as ctx:
                    ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
                msg = str(ctx.exception)
                self.assertIn(fragment, msg)
                if fragment == unexpected:
                    self.assertEqual(msg, unexpected, 'текст винятку не мусить просочуватись у повідомлення')

    def test_deeply_nested_manifest_json_is_an_error_not_recursion_error(self):
        self.site[f'{self.base}/manifest.json'] = b'[' * 100000
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('manifest.json', str(ctx.exception))

    def test_manifest_json_that_is_not_an_object_is_an_error(self):
        self.site[f'{self.base}/manifest.json'] = b'[1, 2]'
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('manifest.json', str(ctx.exception))

    def test_legacy_depth_is_coerced_into_a_valid_range(self):
        """`depth` із чужих даних: сміття → 0, завелике → стеля `pm.MAX_DEPTH - 1` (щоб
        дерево з рядків не вийшло за межу вкладеності й не впало у validate)."""
        top = ip.pm.MAX_DEPTH - 1
        for raw, want in (('abc', 0), (None, 0), (True, 0), (-5, 0), (2.5, 0), (float('inf'), 0),
                          (0, 0), (1, 1), (10 ** 30, top)):
            with self.subTest(depth=raw):
                man = ip.legacy_manifest({'iters': [{'id': 'it1'}], 'pages': [
                    {'id': 'it1/a', 'it': 'it1', 'name': 'a', 'depth': raw, 'path': 'it1/a/index.html'}]})
                self.assertEqual(man['outline'][0]['depth'], want)

    def test_long_chain_of_depths_still_makes_a_valid_tree(self):
        pages = [{'id': f'it1/p{i}', 'it': 'it1', 'name': f'p{i}', 'depth': i, 'path': f'it1/p{i}/index.html'}
                 for i in range(100)]
        man = ip.legacy_manifest({'iters': [{'id': 'it1'}], 'pages': pages})
        ip.pm.validate(ip.outline_tree(man['outline'], 'it1'))

    def test_iteration_id_with_thousands_of_digits_does_not_crash_the_numbering(self):
        man = ip.legacy_manifest({'iters': [{'id': 'it' + '9' * 5000}, {'id': 'it3'}]})
        self.assertEqual([i['num'] for i in man['iters']], [0, 3])

    # ── ревʼю P1 · I3: дерево перевіряється ДО запису й у dry-run ───────────────

    def test_duplicate_pages_in_legacy_data_fail_before_any_write_and_any_crawl(self):
        data = {**self.data, 'pages': self.data['pages'] + [
            {'id': 'it4/kartka', 'it': 'it4', 'name': 'Дубль', 'depth': 0, 'path': 'it4/kartka/index.html'}]}
        self.site[f'{self.base}/'] = legacy_wrapper(data).encode()
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                self.log.clear()
                before = self.snapshot()
                with self.assertRaises(ip.ImportError_) as ctx:
                    ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=dry)
                self.assertIn('kartka', str(ctx.exception))
                self.assertEqual(self.snapshot(), before, 'щось записано попри невалідне дерево')
                self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'iterations'))), ['it1'])
                self.assertFalse([u for u in self.log if '/it4/' in u], 'файли качались до перевірки дерева')

    # ── ревʼю P1 · M2/M3/M1 ──────────────────────────────────────────────────────

    def test_var_d_in_title_or_in_an_earlier_script_does_not_hide_the_real_data(self):
        html = legacy_wrapper(self.data).replace('<title>t</title>', '<title>Fix var D= parser</title>')
        html = html.replace('<script>var D=', '<script>var D=null;var D=', 1)
        self.site[f'{self.base}/'] = html.encode()
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual((rep['source_it'], rep['format']), ('it4', 'legacy-wrapper'))

    def test_legacy_errors_do_not_blame_manifest_json_but_manifest_ones_do(self):
        self.site[f'{self.base}/'] = legacy_wrapper({'iters': [], 'pages': []}).encode()
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('даних превʼю', str(ctx.exception))
        self.assertNotIn('manifest.json', str(ctx.exception))
        bad = {**self.data, 'pages': [{'id': 'it4', 'it': 'it4', 'name': 'x', 'depth': 0, 'path': '../evil.html'}]}
        self.site[f'{self.base}/'] = legacy_wrapper(bad).encode()
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('даних превʼю', str(ctx.exception))
        self.assertNotIn('manifest.json', str(ctx.exception))
        self.site[f'{self.base}/manifest.json'] = json.dumps({'iters': [], 'pages': []}).encode()
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('manifest.json', str(ctx.exception))

    def test_missing_wrapper_is_404_but_unreachable_wrapper_is_not(self):
        del self.site[f'{self.base}/']
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('404', str(ctx.exception))
        self.down = {f'{self.base}/'}
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('timed out', str(ctx.exception))
        self.assertIn('повтори', str(ctx.exception))
        self.assertNotIn('404', str(ctx.exception))

    def test_cli_says_the_legacy_tree_is_approximate(self):
        def run(fmt):
            err = io.StringIO()
            rep = {'format': fmt, 'failed': [], 'broken': [], 'unstripped': []}
            with mock.patch.object(ip, 'import_iteration', return_value=rep), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ip.main(['--task-dir', self.d, self.base]), 0)
            return err.getvalue()
        note = run('legacy-wrapper')
        self.assertIn('наближено', note)
        self.assertIn('теки-організатори', note)
        self.assertEqual(run('manifest'), '')



# ── Старі шаблони публікації ───────────────────────────────────────────────────
# БУКВАЛЬНО з історії (`git show <sha>:design-canvas/app/serve.py`), а не імпорт
# чинного коду: тест мусить зберігати те, що колись справді потрапило у світ.
# Превʼю 04.08–27.08.2026 мають сніпет коментатора, що починається тегом
# бібліотеки Supabase (38b4080 — без `onerror`, 5ed9bf7 — з ним); чинний шаблон
# (6ced2ae) починається банером. Гейт у всіх версіях однаковий, крім рядка з
# KEY/P: у 38b4080 пароль у лапках шаблону, з 5ed9bf7 — JS-літералом.
_OLD_COMMENT_38B4080 = """
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script src="{assets}/supabase-adapter.min.js"></script>
<script src="{assets}/comment-layer.min.js"></script>
<script>
(function () {{
  var init = function () {{
    var store = window.CommentLayerSupabase({{
      url: '{sb_url}', anonKey: '{sb_key}', projectId: '{project}',
    }});
    store.ready.then(function () {{
      window.CommentLayer.init({{ projectId: '{project}', storage: store, version: '{version}' }});
    }});
  }};
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
}})();
</script>"""

_OLD_COMMENT_5ED9BF7 = """
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2" onerror="window.__clDown&&window.__clDown('бібліотека Supabase не завантажилась')"></script>
<script src="{assets}/supabase-adapter.min.js" onerror="window.__clDown&&window.__clDown('адаптер коментарів не завантажився')"></script>
<script src="{assets}/comment-layer.min.js" onerror="window.__clDown&&window.__clDown('шар коментарів не завантажився')"></script>
<script>
(function () {{
  /* Банер оголошений ПЕРШИМ і на window: `onerror` тегів вище спрацьовує до того,
     як цей скрипт виконається, тому вони кличуть його через `window.__clDown` з
     охоронцем. Мовчазний збій тут — найгірший стан на превʼю: колега бачить
     сторінку без пінів і робить висновок, що коментарів немає, хоча вони є. */
  window.__clDown = function (why) {{
    if (document.getElementById('cl-down')) return;
    var d = document.createElement('div');
    d.id = 'cl-down';
    d.textContent = 'Коментарі недоступні: ' + why;
    d.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;'
      + 'background:#d14343;color:#fff;font:13px/1.4 system-ui,sans-serif;'
      + 'padding:8px 12px;border-radius:6px;box-shadow:0 4px 14px rgba(0,0,0,.3)';
    (document.body || document.documentElement).appendChild(d);
  }};
  var init = function () {{
    if (!window.CommentLayerSupabase || !window.CommentLayer) {{
      window.__clDown('шар коментарів не піднявся');
      return;
    }}
    var store = window.CommentLayerSupabase({{
      url: '{sb_url}', anonKey: '{sb_key}', projectId: '{project}',
    }});
    store.ready.then(function () {{
      window.CommentLayer.init({{ projectId: '{project}', storage: store, version: '{version}' }});
    }}).catch(function (e) {{
      window.__clDown((e && e.message) || 'база не відповіла');
    }});
  }};
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
}})();
</script>"""

_OLD_GATE_38B4080 = """
<style>#authgate{{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:#eef0f2;font-family:system-ui,sans-serif}}
#authform{{width:320px;background:#fff;border:1px solid #d5d9dd;padding:32px 28px;display:flex;flex-direction:column;gap:14px}}
#authform input{{height:40px;padding:0 12px;border:1px solid #d5d9dd;font-size:14px}}
#authform button{{height:44px;background:#2d6ae3;color:#fff;border:0;font-size:14px;cursor:pointer}}
#agerr{{display:none;font-size:12px;color:#c0362c}}</style>
<div id="authgate"><form id="authform">
  <!-- До входу назви задачі/тікета не показуємо: URL превью може потрапити
       кому завгодно, а контекст має бути за паролем (правило 30.07.2026). -->
  <b>Перегляд макета</b><span style="font-size:13px;color:#6b7280">захищено · введіть пароль</span>
  <input id="agpass" type="password" autocomplete="current-password" placeholder="Пароль">
  <div id="agerr">Невірний пароль</div><button type="submit">Увійти</button>
</form></div>
<script>(function(){{var KEY='{key}',P='{pw}';
function unlock(){{var g=document.getElementById('authgate');if(g)g.remove();
  // Справжній заголовок — лише після входу (до нього в title нейтральний текст).
  try{{if(window.__origTitle)document.title=window.__origTitle;}}catch(e){{}}
  // Хук для обгортки: вона НЕ вантажить iframe до розблокування, інакше внутрішня
  // сторінка (у якої тепер теж є гейт) показала б свій гейт усередині рамки.
  window.__gateOpen=true;if(window.__onGateOpen)window.__onGateOpen();}}
function save(){{try{{sessionStorage.setItem(KEY,'1')}}catch(e){{}}}}
// Безшовний вхід із Liga Design Office: токен у hash (#k=<код>) → авто-розблокування.
// ⛔ Прибираємо з hash ЛИШЕ свій `k=`, решту лишаємо: там їде `p=<сторінка>` —
// глибоке посилання обгортки. Раніше тут стояв голий pathname+search, і hash
// зносився цілком, тобто посилання «відкрий саме цю ітерацію» гинуло на вході.
try{{var h=location.hash||'',m=h.match(/(?:^#|&)k=([^&]+)/);
  if(m&&decodeURIComponent(m[1])===P){{save();
    var rest=h.replace(/^#/,'').split('&').filter(function(s){{
      return s&&s.indexOf('k=')!==0;}}).join('&');
    history.replaceState(null,'',location.pathname+location.search+(rest?'#'+rest:''));
    unlock();return;}}}}catch(e){{}}
try{{if(sessionStorage.getItem(KEY)==='1'){{unlock();return;}}}}catch(e){{}}
document.getElementById('authform').addEventListener('submit',function(e){{
  e.preventDefault();
  if(document.getElementById('agpass').value===P){{save();unlock();}}
  else document.getElementById('agerr').style.display='block';}});}})();</script>"""

_OLD_GATE_5ED9BF7 = _OLD_GATE_38B4080.replace(
    "var KEY='{key}',P='{pw}';", "var KEY={key_js},P={pw_js};")
assert _OLD_GATE_5ED9BF7 != _OLD_GATE_38B4080

SECRET = 'секрет-1100'  # вигаданий пароль: у тестах «пароль превʼю» — лише він


def published_old(html, variant, depth_up='../', pw=SECRET):
    """Сторінка, опублікована СТАРИМ шаблоном (`variant` — sha коміту). Вставка перед
    `</body>` і нейтралізація title — рівно як у тодішніх `inject_comment_layer` і
    `_inject_gate` (в обох версіях однакові)."""
    kw = dict(assets=f'{depth_up}comment-layer', sb_url='https://x.supabase.co', sb_key='anon-key',
              project='chan', version='1/kartka')
    if variant == '38b4080':
        snippet, gate = _OLD_COMMENT_38B4080.format(**kw), _OLD_GATE_38B4080.format(key='t_auth', pw=pw)
    else:
        snippet = _OLD_COMMENT_5ED9BF7.format(**kw)
        gate = _OLD_GATE_5ED9BF7.format(key_js=serve.js_literal('t_auth'), pw_js=serve.js_literal(pw))

    def before_body(page, frag):
        m = re.search(r'</body>', page, flags=re.I)
        return page + frag if not m else page[:m.start()] + frag + page[m.start():]
    page = before_body(html, snippet)
    m = re.search(r'<title>(.*?)</title>', page, flags=re.I | re.S)
    if m:
        gate = f'<script>window.__origTitle={json.dumps(m.group(1))};</script>' + gate
        page = page[:m.start()] + '<title>Перегляд макета</title>' + page[m.end():]
    return before_body(page, gate)


class OldTemplates(unittest.TestCase):
    """Ревʼю P1 · I1: старі сніпети знімаються так само, як чинний — байт у байт."""

    def test_each_old_template_strips_back_to_the_original_page(self):
        no_title = PAGE.replace('<title>Картка «Ромашка»</title>', '')
        for variant in ('38b4080', '5ed9bf7'):
            for name, page in (('з title', PAGE), ('без title', no_title)):
                with self.subTest(variant=variant, page=name):
                    pub = published_old(page, variant)
                    self.assertIn(SECRET, pub, 'фікстура без пароля — тест нічого б не довів')
                    self.assertEqual(ip.strip_publish(pub), (page, True))

    def test_an_old_format_entity_title_is_not_double_escaped(self):
        """До виправлення `__origTitle` ніс СИРИЙ вихідний текст заголовка (`json.dumps(m.group(1))`):
        сутності в ньому вже були сутностями. Такі превʼю ще живі — імпорт не має їх подвоювати
        (`R&amp;D` → `R&amp;amp;D`) і не має робити розміткою."""
        for variant in ('38b4080', '5ed9bf7'):
            for src in ('R&amp;D', 'A &lt;/title&gt;&lt;b&gt;x&lt;/b&gt;', 'Тарифи &laquo;Про&raquo;'):
                with self.subTest(variant=variant, title=src):
                    page = PAGE.replace('<title>Картка «Ромашка»</title>', f'<title>{src}</title>')
                    pub = published_old(page, variant)
                    self.assertIn(f'window.__origTitle={json.dumps(src)}', pub, 'фікстура не старого формату')
                    self.assertEqual(ip.strip_publish(pub), (page, True))

    def test_gate_marker_is_in_every_known_gate(self):
        """Запобіжник стоїть на маркері, за яким `serve._inject_gate` розпізнає гейт: він
        мусить бути і в чинному гейті, і в обох старих (інакше запобіжник сліпий)."""
        for name, gate in (('чинний', serve.gate_html('t', SECRET)),
                           ('38b4080', _OLD_GATE_38B4080.format(key='t_auth', pw=SECRET)),
                           ('5ed9bf7', _OLD_GATE_5ED9BF7.format(key_js='"t_auth"', pw_js=f'"{SECRET}"'))):
            with self.subTest(gate=name):
                self.assertIn(ip._GATE_MARK, gate)


if __name__ == '__main__':
    unittest.main()

"""`app/modules/css-tokens`: токени дизайн-системи з CSS-файла для інспектора (роль `tokens`).

Дві площини перевірки:
  * розбір і читання — безпосередньо: `server.py` вантажиться так само, як це робить ядро
    (`exec` у свіжий модуль, без `importlib` і `__pycache__`), тож тест бачить саме ті функції,
    що й сервер, а не окрему копію;
  * інтеграція — через справжній `deai_modules` і справжню теку `app/modules` (маніфест,
    `resolve_settings`, `provider`, `capabilities`, `check`, `call`).

Кожен тест має власні `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; справжній `~/.deai` стереже
`spaces_guard` (інтеграційні тести створюють простори).
"""
import ast
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402

MODULE_DIR = os.path.join(os.path.dirname(_HERE), 'app', 'modules', 'css-tokens')
SERVER = os.path.join(MODULE_DIR, 'server.py')
_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE')
_REAL = None
MIB = 1024 * 1024


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def load_server():
    """Свіжий екземпляр `server.py` — як у `deai_modules._build`: байти, `exec(compile(…))`, без
    `importlib`, без `sys.modules`, без `__pycache__`."""
    with open(SERVER, 'rb') as f:
        raw = f.read()
    ns = types.ModuleType('deai_mod_css-tokens')
    ns.__file__ = SERVER
    exec(compile(raw, SERVER, 'exec', dont_inherit=True), ns.__dict__)
    return ns


S = load_server()


def parse(text):
    return S.parse_css_tokens(text)


def root(body):
    return ':root{' + body + '}'


# ----------------------------------------------------------------------------------- розбір

class CommentsTest(unittest.TestCase):
    def test_comments_are_stripped(self):
        self.assertEqual(parse('/* x */ :root { --a: 1; /* --b: 2; */ --c: 3 } /* tail'),
                         {'--a': ['1'], '--c': ['3']})

    def test_comment_inside_a_value_is_a_separator(self):
        self.assertEqual(parse(root('--sp: 1px/* gap */2px')), {'--sp': ['1px 2px']})

    def test_commented_out_rule_gives_nothing(self):
        self.assertEqual(parse('/* :root { --a: 1 } */'), {})

    def test_comment_markers_inside_quotes_and_url_are_kept(self):
        got = parse(root('--q: "a /* not a comment */ b"; --u: url(//cdn.test/*.png); --v: url( x/*y*/z.png )'))
        self.assertEqual(got['--q'], ['"a /* not a comment */ b"'])
        self.assertEqual(got['--u'], ['url(//cdn.test/*.png)'])
        self.assertEqual(got['--v'], ['url( x/*y*/z.png )'])

    def test_unterminated_comment_swallows_the_rest_without_crashing(self):
        self.assertEqual(parse(':root{--a:1} /* never closed :root{--b:2}'), {'--a': ['1']})


class SelectorsTest(unittest.TestCase):
    def test_root_html_and_data_theme_qualify(self):
        css = (':root{--a:1} html{--b:2} [data-theme=dark]{--c:3} html[data-theme="x"]{--d:4} '
               ':root[data-theme]{--e:5} HTML{--f:6} body[data-theme-x]{--g:7}')
        self.assertEqual(set(parse(css)), {'--a', '--b', '--c', '--d', '--e', '--f', '--g'})

    def test_any_selector_of_the_list_qualifies(self):
        self.assertEqual(parse('.a, :root , .b{--a:1}'), {'--a': ['1']})
        self.assertEqual(parse('.a,\n  html.dark{--a:1}'), {'--a': ['1']})

    def test_html_as_an_attribute_or_part_of_a_word_is_not_html(self):
        css = '.card[html]{--c1:1} a[data-html]{--c2:2} .x-html{--c3:3} .my_html{--c4:4} htmlx{--c5:5} xhtml{--c6:6}'
        self.assertEqual(parse(css), {})

    def test_other_selectors_are_ignored(self):
        css = ('.card{--c1:1} body{--c2:2} div.html{--c3:3} .html{--c4:4} #html{--c5:5} '
               '[title="html"]{--c6:6} [data-x=root]{--c7:7} a:hover{--c8:8} *{--c9:9} .root-x{--c10:10}')
        self.assertEqual(parse(css), {})

    def test_a_component_scoped_under_a_theme_is_not_a_token(self):
        """`[data-theme=dark] .card` задає змінну картці, а не темі: рівень кореня — крайній
        складений селектор (суб'єкт), а не будь-яка згадка."""
        self.assertEqual(parse('[data-theme=dark] .card{--card-bg:#000} html body{--b:1}'), {})
        self.assertEqual(parse('.dark :root{--a:1} html > body , html{--b:2}'), {'--a': ['1'], '--b': ['2']})

    def test_commas_and_combinators_inside_brackets_and_strings_do_not_split(self):
        self.assertEqual(parse('[data-x="a,b"] .card, [data-y~="p q"] :root{--a:1}'), {'--a': ['1']})
        self.assertEqual(parse('.card[title="x, :root"]{--c:1}'), {})            # кома в рядку — не роздільник
        self.assertEqual(parse(':is(html, .a) .card{--c:1}'), {})                # кома в дужках — не роздільник
        self.assertEqual(parse('.card:has(> .a ~ .b){--c:1}'), {})
        self.assertEqual(parse(r'.a\,b, :root{--d:1}'), {'--d': ['1']})
        self.assertEqual(parse('.a[title="["] :root .x{--c:1}'), {})              # `[` у рядку не відкриває дужку
        self.assertEqual(parse(r'[title="a\" , :root"]{--c:1}'), {})
        self.assertEqual(parse(r'[title="a\" b"] :root .x{--c:1}'), {})           # `\"` не закриває рядок
        self.assertEqual(parse(r'[title="a\" b"] :root{--c:1}'), {'--c': ['1']})
        self.assertEqual(parse('.a[title="["] :root{--c:1}'), {'--c': ['1']})

    def test_declarations_are_taken_only_for_custom_properties(self):
        self.assertEqual(parse(root('color: red; --a: 1; background: blue; -webkit-x: 2; -a: 3')), {'--a': ['1']})

    def test_names_are_case_sensitive_and_kept_as_written(self):
        self.assertEqual(parse(root('--Brand: 1; --brand: 2')), {'--Brand': ['1'], '--brand': ['2']})

    def test_last_declaration_without_semicolon_and_spaces(self):
        self.assertEqual(parse(':root{--a :  1 ;--b:2}'), {'--a': ['1'], '--b': ['2']})


class ThemeFormsTest(unittest.TestCase):
    """Теми, які дизайнери справді пишуть: Bootstrap 5.3 (`[data-bs-theme]`) і Tailwind v4 (`@theme`)."""

    def test_any_data_attribute_with_theme_in_its_name_qualifies(self):
        css = ('[data-bs-theme=dark]{--a:1} [data-color-theme="x"]{--b:2} html[data-bs-theme]{--c:3}'
               ' [ data-theme-x ]{--d:4} body[DATA-BS-THEME=light]{--e:5} :root[data-mantine-theme]{--f:6}')
        self.assertEqual(set(parse(css)), {'--a', '--b', '--c', '--d', '--e', '--f'})

    def test_bootstrap_dark_theme_gives_a_second_value(self):
        css = ':root, [data-bs-theme=light]{--bs-body-bg:#fff} [data-bs-theme=dark]{--bs-body-bg:#212529}'
        self.assertEqual(parse(css), {'--bs-body-bg': ['#fff', '#212529']})

    def test_other_attributes_and_bare_classes_are_not_root_level(self):
        """`.dark { … }` (голий клас) НЕ береться: клас може стояти на будь-якому елементі, тож це були б
        і токени, і локальні змінні компонентів впереміш."""
        css = ('.dark{--n1:1} .theme-dark{--n2:2} [data-mode=dark]{--n3:3} [bs-theme=dark]{--n4:4}'
               ' [data-bs-mode]{--n5:5} [theme]{--n6:6} [data-bs-theme=dark] .card{--n7:7}'
               ' [data-x=theme]{--n8:8} [title="data-theme"]{--n9:9} body.dark{--n10:10}')
        self.assertEqual(parse(css), {})

    def test_tailwind_4_theme_block(self):
        css = ('@theme { --color-brand: #f00; --font-sans: "Inter", sans-serif; --spacing: 0.25rem; }'
               ' @theme inline { --color-fg: var(--text) } :root { --text: #111 }')
        self.assertEqual(parse(css), {'--color-brand': ['#f00'], '--font-sans': ['"Inter", sans-serif'],
                                      '--spacing': ['0.25rem'], '--color-fg': ['#111'], '--text': ['#111']})

    def test_tailwind_theme_modifiers_and_nesting(self):
        css = ('@theme static { --a: 1 } @THEME default { --b: 2 } @layer theme { @theme { --c: 3 } }'
               ' @media print { @theme { --d: 4 } }')
        self.assertEqual(parse(css), {'--a': ['1'], '--b': ['2'], '--c': ['3'], '--d': ['4']})

    def test_tailwind_namespace_reset_is_not_a_token(self):
        css = '@theme { --color-*: initial; --font-*: initial; --color-brand: #f00 }'
        self.assertEqual(parse(css), {'--color-brand': ['#f00']})

    def test_tailwind_theme_inner_at_rules_give_no_tokens(self):
        css = ('@theme { --animate-wiggle: wiggle 1s; @keyframes wiggle { 0% { --k: 1 } to { --k: 2 } }'
               ' --after: 5 }')
        self.assertEqual(parse(css), {'--animate-wiggle': ['wiggle 1s'], '--after': ['5']})

    def test_only_the_theme_at_rule_itself(self):
        css = ('@themes { --a: 1 } @theme-x { --b: 2 } @thème { --c: 3 } @font-face { --d: 4 }'
               ' @property --p { initial-value: 1 } .x { @theme { --e: 5 } }')
        self.assertEqual(parse(css), {'--e': ['5']})          # внутрішній `@theme` — теж `@theme`; решта ні

    def test_a_theme_block_with_selector_after_it_closes_properly(self):
        css = '@theme { --a: 1 } .card { --nope: 2 } :root { --b: 3 }'
        self.assertEqual(parse(css), {'--a': ['1'], '--b': ['3']})


class NestingTest(unittest.TestCase):
    def test_media_layer_supports_are_flattened(self):
        css = ('@media (prefers-color-scheme: dark) { :root { --bg: #000 } }'
               '@layer base { :root { --fg: #111 } }'
               '@supports (color: oklch(0 0 0)) { html { --ok: oklch(0 0 0) } }')
        self.assertEqual(parse(css), {'--bg': ['#000'], '--fg': ['#111'], '--ok': ['oklch(0 0 0)']})

    def test_any_depth(self):
        css = ('@layer a { @media (min-width: 600px) { @supports (display: grid) { @media print {'
               ' :root { --deep: 1 } } } } }')
        self.assertEqual(parse(css), {'--deep': ['1']})

    def test_container_and_document_groups_are_descended_too(self):
        self.assertEqual(parse('@container (min-width: 1px) { :root { --c: 1 } }'), {'--c': ['1']})

    def test_native_nesting_inside_a_root_rule(self):
        css = (':root { --a: 1; @media (prefers-color-scheme: dark) { --a: 2; --b: 3 }'
               ' &[data-theme=dark] { --a: 4 } .dark & { --a: 5 } & .card { --a: 6 } }')
        self.assertEqual(parse(css), {'--a': ['1', '2', '4', '5'], '--b': ['3']})

    def test_every_conditional_group_passes_the_root_down_when_nested_in_it(self):
        css = (':root { @layer x { --l: 1 } @supports (a: b) { --s: 2 } @container (min-width: 1px) { --c: 3 }'
               ' @document url-prefix() { --d: 4 } @media print { @layer y { --deep: 5 } } }')
        self.assertEqual(parse(css), {'--l': ['1'], '--s': ['2'], '--c': ['3'], '--d': ['4'], '--deep': ['5']})

    def test_declarations_after_a_nested_block_still_belong_to_the_root(self):
        self.assertEqual(parse(':root { --a: 1; .card { --x: 1 } @media print { --m: 2 } --b: 2 }'),
                         {'--a': ['1'], '--m': ['2'], '--b': ['2']})
        self.assertEqual(parse('.card { :root & { --x: 1 } } :root { --ok: 1 }'), {'--ok': ['1']})

    def test_nesting_does_not_make_a_bare_ampersand_qualify(self):
        self.assertEqual(parse('.x { &.y { --a: 1 } @media print { --b: 2 } }'), {})

    def test_declarations_directly_in_a_group_rule_are_not_tokens(self):
        self.assertEqual(parse('@media print { --a: 1 }'), {})

    def test_statement_at_rules_do_not_break_the_next_rule(self):
        css = ('@charset "utf-8"; @import url("x.css") layer(a); @layer base, theme;'
               ' :root { --a: 1 } @namespace svg url(http://x);')
        self.assertEqual(parse(css), {'--a': ['1']})

    def test_font_face_keyframes_property_page_give_no_tokens(self):
        css = ('@font-face { font-family: X; --nope: 1; src: url(a.woff2) } '
               '@keyframes k { from { --f: 1 } to { --t: 2 } } @property --p { syntax: "*"; inherits: false }'
               ' @page :first { --pg: 1 } :root { --ok: 1 }')
        self.assertEqual(parse(css), {'--ok': ['1']})

    def test_other_at_rules_give_no_tokens_themselves_but_are_looked_into(self):
        css = ('@scope (.card) { :root { --s: 1 } .x { --nope: 2 } }'
               ' @-moz-document url-prefix() { html { --d: 3 } }'
               ' @starting-style { :root { --st: 4 } }'
               ' @font-face { --nf: 1 } @unknown { --nu: 1; :root { --in: 5 } }')
        self.assertEqual(parse(css), {'--s': ['1'], '--d': ['3'], '--st': ['4'], '--in': ['5']})

    def test_a_group_does_not_pass_the_root_into_other_at_rules(self):
        self.assertEqual(parse(':root { @font-face { --a: 1 } @scope (.x) { --b: 2 } }'), {})

    def test_an_at_rule_with_inner_braces_does_not_unbalance_the_file(self):
        self.assertEqual(parse('@keyframes k { 0% { a: b } 50% { c: d } } :root { --a: 1 }'), {'--a': ['1']})

    def test_unbalanced_braces_never_crash(self):
        self.assertEqual(parse(':root { --a: 1 } } } :root { --b: 2 }'), {'--a': ['1'], '--b': ['2']})
        self.assertEqual(parse(':root { --a: 1; @media x { --b: 2 '), {'--a': ['1'], '--b': ['2']})   # EOF закриває блоки
        self.assertEqual(parse('{{{ ;;; }}}'), {})

    def test_stray_closing_brace_before_any_rule(self):
        self.assertEqual(parse('} :root{--a:1}'), {'--a': ['1']})


class ListsTest(unittest.TestCase):
    def test_values_are_collected_per_name_in_source_order(self):
        css = (':root{--bg:#fff} [data-theme=dark]{--bg:#000} '
               '@media (prefers-contrast: more){:root{--bg:#eee}}')
        self.assertEqual(parse(css), {'--bg': ['#fff', '#000', '#eee']})

    def test_duplicate_values_are_listed_once(self):
        self.assertEqual(parse(':root{--a:1} @media print{:root{--a:1}} html{--a:2;--a:1}'), {'--a': ['1', '2']})

    def test_two_themes_aliasing_the_same_value_list_it_once(self):
        css = root('--a: #fff; --b: #fff; --x: var(--a)') + '[data-theme=dark]{--x: var(--b)}'
        self.assertEqual(parse(css)['--x'], ['#fff'])

    def test_a_name_with_very_many_distinct_values_stays_linear(self):
        n = 60000
        css = ''.join(f':root{{--a: v{i}}}' for i in range(n))
        t0 = time.monotonic()
        got = parse(css)
        self.assertLess(time.monotonic() - t0, 4)
        self.assertEqual(len(got['--a']), n)

    def test_whitespace_in_a_value_is_collapsed(self):
        self.assertEqual(parse(root('--f:  Inter ,\n\t"Helvetica Neue" ,   sans-serif  ')),
                         {'--f': ['Inter , "Helvetica Neue" , sans-serif']})

    def test_names_come_out_in_first_seen_order(self):
        self.assertEqual(list(parse(root('--z:1;--a:2') + root('--m:3;--a:4'))), ['--z', '--a', '--m'])

    def test_empty_value_keeps_the_name_known_without_a_value(self):
        self.assertEqual(parse(root('--off:; --on: 1; --blank:   ')), {'--off': [], '--on': ['1'], '--blank': []})

    def test_empty_and_garbage_inputs(self):
        for text in ('', '   ', '\n', 'not css at all', ';;;', '@@@', '\x00\x01\x02', ':root', ':root{'):
            self.assertEqual(parse(text), {}, repr(text))


class QuotesAndUrlTest(unittest.TestCase):
    def test_semicolon_and_brace_inside_quotes_do_not_cut_the_value(self):
        css = root('--a: "x;y}z{w"; --b: \'p;q}r\'; --c: 1')
        self.assertEqual(parse(css), {'--a': ['"x;y}z{w"'], '--b': ["'p;q}r'"], '--c': ['1']})

    def test_escaped_quote_inside_a_string(self):
        self.assertEqual(parse(root(r'--a: "he said \"hi;\" }"; --b: 1')), {'--a': [r'"he said \"hi;\" }"'], '--b': ['1']})

    def test_semicolon_and_brace_inside_url(self):
        css = root('--img: url(data:image/svg+xml;base64,AAAA}BBB); --b: 2')
        self.assertEqual(parse(css), {'--img': ['url(data:image/svg+xml;base64,AAAA}BBB)'], '--b': ['2']})

    def test_quoted_url_and_uppercase_url(self):
        css = root('--a: url("a;b}c.png"); --b: URL(x;y.png); --c: 3')
        self.assertEqual(parse(css), {'--a': ['url("a;b}c.png")'], '--b': ['URL(x;y.png)'], '--c': ['3']})

    def test_a_quoted_url_with_a_paren_inside_the_string(self):
        css = root('--u: url("a)b;c}"); --k: 2')
        self.assertEqual(parse(css), {'--u': ['url("a)b;c}")'], '--k': ['2']})
        self.assertEqual(parse(root("--u: url( 'a)b;c}' ); --k: 2")), {'--u': ["url( 'a)b;c}' )"], '--k': ['2']})

    def test_url_not_at_a_word_boundary_is_not_a_url(self):
        """`curl(…)` — звичайна функція, а не `url(…)`: коментар усередині неї прибирається."""
        self.assertEqual(parse(root('--a: curl(/* c */ x); --b: url(/* c */ x)')),
                         {'--a': ['curl( x)'], '--b': ['url(/* c */ x)']})

    def test_quotes_make_braces_in_selectors_harmless(self):
        self.assertEqual(parse('[data-x="{"]{--no:1} :root{--a:1}'), {'--a': ['1']})

    def test_unterminated_string_spoils_its_declaration_only(self):
        """Рядок без закривної лапки кінчається на розриві рядка й, як bad-string у CSS, робить
        недійсною всю декларацію (вона тягнеться до `;`, тож `--b` пропадає разом із `--a`)."""
        got = parse(root('--a: "oops;\n--b: 2; --c: 3'))
        self.assertEqual(got, {'--c': ['3']})
        self.assertEqual(parse(root("--a: 'oops\n; --b: 2")), {'--b': ['2']})
        self.assertEqual(parse(root('--a: "ok"; --b: "never')), {'--a': ['"ok"']})

    def test_escaped_semicolon_outside_quotes_does_not_cut(self):
        self.assertEqual(parse(root(r'--a: x\;y; --b: 2')), {'--a': [r'x\;y'], '--b': ['2']})

    def test_semicolon_inside_parentheses_does_not_cut(self):
        self.assertEqual(parse(root('--a: foo(1;2); --b: 3')), {'--a': ['foo(1;2)'], '--b': ['3']})

    def test_block_value_of_a_custom_property_stays_whole(self):
        self.assertEqual(parse(root('--blk: { color: red; width: 1px }; --b: 2')),
                         {'--blk': ['{ color: red; width: 1px }'], '--b': ['2']})


class ImportantTest(unittest.TestCase):
    def test_important_is_dropped(self):
        css = root('--a: red !important; --b: 1px!IMPORTANT; --c: 2 ! important ; --d: x')
        self.assertEqual(parse(css), {'--a': ['red'], '--b': ['1px'], '--c': ['2'], '--d': ['x']})

    def test_important_inside_a_string_stays(self):
        self.assertEqual(parse(root('--a: "x !important"')), {'--a': ['"x !important"']})

    def test_stripping_important_is_linear_in_whitespace_runs(self):
        """`\\s*!\\s*important\\s*\\Z` із невиверненим `sub` — квадрат на довгих проміжках: 100 КБ пробілів
        у лапках = 7 с, 2 МіБ ≈ 45 хв, і сервер стоїть. Тепер — лінійно."""
        gap = ' ' * 200_000
        inputs = {
            'string': root('--a: "' + gap + '"'),
            'unquoted url': root('--a: url(' + gap + 'x)'),
            'bang in string': root('--a: "!' + gap + '"'),
            'many bangs': root('--a: "' + '! ' * 100_000 + '"'),
            'bang then spaces then word': root('--a: "x !' + gap + 'importan"'),
            'quoted url': root("--a: url('" + gap + "')"),
        }
        for name, css in inputs.items():
            t0 = time.monotonic()
            got = parse(css)
            dt = time.monotonic() - t0
            self.assertLess(dt, 1.0, f'{name}: {dt:.1f} с')
            self.assertEqual(len(got['--a']), 1, name)

    def test_important_after_a_long_value_and_inside_functions(self):
        gap = ' ' * 50_000
        self.assertEqual(parse(root('--a: "x' + gap + 'y" !important'))['--a'], ['"x' + gap + 'y"'])
        self.assertEqual(parse(root('--a: calc(1px + 2px) !important'))['--a'], ['calc(1px + 2px)'])
        self.assertEqual(parse(root('--a: red\t\n!\n important\n'))['--a'], ['red'])

    def test_important_does_not_create_a_second_value(self):
        self.assertEqual(parse(root('--a: 1') + root('--a: 1 !important')), {'--a': ['1']})


class VarTest(unittest.TestCase):
    def test_var_is_expanded_when_defined(self):
        self.assertEqual(parse(root('--b: #fff; --a: var(--b)')), {'--b': ['#fff'], '--a': ['#fff']})

    def test_var_may_be_defined_later_in_the_file(self):
        self.assertEqual(parse(root('--a: var(--b)') + root('--b: #fff')), {'--a': ['#fff'], '--b': ['#fff']})

    def test_var_carries_every_theme_of_the_target(self):
        css = root('--c: #fff; --a: var(--c)') + '[data-theme=dark]{--c:#000}'
        self.assertEqual(parse(css), {'--c': ['#fff', '#000'], '--a': ['#fff', '#000']})

    def test_var_inside_a_function_and_two_vars_in_one_value(self):
        css = root('--r: 1; --g: 2; --b: 3; --rgb: rgb(var(--r) var(--g) var(--b)); --x: calc(var(--r)*2)')
        got = parse(css)
        self.assertEqual(got['--rgb'], ['rgb(1 2 3)'])
        self.assertEqual(got['--x'], ['calc(1*2)'])

    def test_two_vars_with_themes_give_every_combination(self):
        css = (root('--p: 1; --q: a; --pair: var(--p) var(--q)') +
               '[data-theme=dark]{--p: 2; --q: b}')
        self.assertEqual(parse(css)['--pair'], ['1 a', '1 b', '2 a', '2 b'])

    def test_fallback_is_dropped_when_the_target_is_defined(self):
        self.assertEqual(parse(root('--b: red; --a: var(--b, blue)'))['--a'], ['red'])

    def test_a_paren_or_comma_inside_a_string_of_the_fallback_does_not_end_the_var(self):
        self.assertEqual(parse(root('--a: 1; --b: var(--a, ")")'))['--b'], ['1'])
        self.assertEqual(parse(root("--a: 1; --b: var(--a, ')')"))['--b'], ['1'])
        self.assertEqual(parse(root('--a: 1; --b: var(--a, url(x)y)'))['--b'], ['1'])
        self.assertEqual(parse(root('--a: 1; --b: var(--a, url(")"))'))['--b'], ['1'])

    def test_nested_var_in_the_fallback_does_not_confuse_the_scan(self):
        self.assertEqual(parse(root('--b: red; --a: var(--b, var(--zzz, 1))'))['--a'], ['red'])

    def test_uppercase_var_and_spaces(self):
        self.assertEqual(parse(root('--b: 1; --a: VAR( --b )'))['--a'], ['1'])

    def test_chain_up_to_five_hops(self):
        css = root('--f: 1; --e: var(--f); --d: var(--e); --c: var(--d); --b: var(--c); --a: var(--b)')
        got = parse(css)
        self.assertEqual(got['--a'], ['1'])        # a→b→c→d→e→f: п'ять стрибків
        self.assertEqual(got['--b'], ['1'])

    def test_six_hops_is_too_deep(self):
        css = root('--g: 1; --f: var(--g); --e: var(--f); --d: var(--e); --c: var(--d); --b: var(--c); --a: var(--b)')
        got = parse(css)
        self.assertEqual(got['--a'], [])           # шість стрибків — вже задовго
        self.assertEqual(got['--b'], ['1'])        # а його п'ять — ще ні
        self.assertEqual(got['--g'], ['1'])

    def test_cycle_gives_an_empty_list(self):
        got = parse(root('--a: var(--b); --b: var(--a); --ok: 1'))
        self.assertEqual(got, {'--a': [], '--b': [], '--ok': ['1']})

    def test_self_reference_gives_an_empty_list(self):
        self.assertEqual(parse(root('--a: var(--a)')), {'--a': []})

    def test_a_dependent_on_a_cycle_is_empty_too(self):
        got = parse(root('--a: var(--b); --b: var(--a); --c: var(--a); --d: var(--c)'))
        self.assertEqual(got, {'--a': [], '--b': [], '--c': [], '--d': []})

    def test_undefined_gives_an_empty_list_even_with_a_fallback(self):
        got = parse(root('--a: var(--nope); --b: var(--nope, red)'))
        self.assertEqual(got, {'--a': [], '--b': []})

    def test_one_unresolvable_value_empties_the_whole_token(self):
        """Неповний список зробив би хибний вирок «перевизначено» для темної теми — порожній
        список чесніший."""
        got = parse(root('--a: #fff') + '[data-theme=dark]{--a: var(--nope)}')
        self.assertEqual(got, {'--a': []})

    def test_a_valueless_target_does_not_resolve(self):
        self.assertEqual(parse(root('--e: ; --a: var(--e)')), {'--e': [], '--a': []})

    def test_malformed_var_gives_an_empty_list(self):
        for bad in ('var()', 'var(notaname)', 'var(--b', 'var(--b,'):
            self.assertEqual(parse(root('--b: 1; --a: ' + bad + '}')).get('--a'), [], bad)

    def test_var_inside_a_string_or_url_is_text(self):
        css = root('--b: 1; --s: "var(--b)"; --u: url(var(--b).png)')
        got = parse(css)
        self.assertEqual(got['--s'], ['"var(--b)"'])
        self.assertEqual(got['--u'], ['url(var(--b).png)'])

    def test_a_longer_ident_ending_in_var_is_not_a_var(self):
        self.assertEqual(parse(root('--b: 1; --a: myvar(--b)'))['--a'], ['myvar(--b)'])

    def test_var_expansion_only_inside_the_same_file(self):
        """`@import` не відстежується: змінна з чужого файла — невизначена."""
        self.assertEqual(parse('@import "other.css"; ' + root('--a: var(--from-other)')), {'--a': []})

    @staticmethod
    def themed(name, n, prefix):
        """`--name` із `n` різними значеннями (кореневе + `n-1` тем)."""
        out = [f':root{{--{name}: {prefix}0}}']
        out += [f'[data-theme=t{prefix}{i}]{{--{name}: {prefix}{i}}}' for i in range(1, n)]
        return ''.join(out)

    def test_exactly_the_combination_limit_is_allowed(self):
        self.assertEqual(S.MAX_COMBOS, 64)
        css = self.themed('p', 4, 'p') + self.themed('q', 4, 'q') + self.themed('r', 4, 'r')
        got = parse(css + root('--ok: var(--p) var(--q) var(--r)') + root('--bad: var(--p) var(--q) var(--r) x'))
        self.assertEqual(len(got['--ok']), 64)
        self.assertEqual(len(set(got['--ok'])), 64)
        self.assertEqual(len(got['--bad']), 64)               # 4·4·4·1 — ще 64
        css = self.themed('p', 4, 'p') + self.themed('q', 4, 'q') + self.themed('r', 5, 'r')
        got = parse(css + root('--over: var(--p) var(--q) var(--r)'))
        self.assertEqual(got['--over'], [])                   # 4·4·5 = 80

    def test_the_combination_limit_is_for_one_value_not_for_a_dependent_chain(self):
        css = self.themed('a', 8, 'a') + root('--b: var(--a)') + root('--c: var(--b) var(--b)')
        got = parse(css)
        self.assertEqual(len(got['--b']), 8)
        self.assertEqual(len(got['--c']), 64)                 # 8·8

    def test_too_many_combinations_gives_an_empty_list(self):
        themes = ''.join(f'[data-theme=t{i}]{{--p:{i};--q:{i};--r:{i}}}' for i in range(5))
        got = parse(root('--p:x;--q:y;--r:z;--big: var(--p) var(--q) var(--r)') + themes)
        self.assertEqual(got['--big'], [])         # 6·6·6 = 216 > 64
        self.assertEqual(len(got['--p']), 6)

    def test_wide_fan_in_stays_fast(self):
        """500 змінних, кожна посилається на 20 попередніх: без запамʼятовування це експонента."""
        parts = ['--v0: 1;']
        for i in range(1, 500):
            refs = ' '.join(f'var(--v{j})' for j in range(max(0, i - 20), i))
            parts.append(f'--v{i}: {refs};')
        t0 = time.monotonic()
        got = parse(root(''.join(parts)))
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(got['--v1'], ['1'])
        self.assertEqual(got['--v400'], [])        # понад п'ять стрибків або понад 64 комбінації


class ExpansionBudgetTest(unittest.TestCase):
    """`var()`-розгортання множить значення: без стелі «тема × правило» вибухає пам'яттю."""
    themed = staticmethod(VarTest.themed)

    def test_the_limits_are_what_the_docs_say(self):
        self.assertEqual((S.MAX_VALUES, S.MAX_EXPANDED), (1024, 20000))

    def test_many_rules_of_one_token_over_themes_are_capped_per_token(self):
        css = self.themed('a', 64, 'a') + ''.join(f':root{{--b: var(--a) {n}}}' for n in range(20000))
        t0 = time.monotonic()
        got = parse(css)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual(len(got['--a']), 64)
        self.assertEqual(got['--b'], [])
        self.assertLess(len(json.dumps(got)), 2000)

    def test_exactly_the_per_token_limit_is_allowed(self):
        rules = lambda k: ''.join(f':root{{--b: var(--a) {n}}}' for n in range(k))        # noqa: E731
        got = parse(self.themed('a', 64, 'a') + rules(S.MAX_VALUES // 64))
        self.assertEqual(len(got['--b']), S.MAX_VALUES)
        got = parse(self.themed('a', 64, 'a') + rules(S.MAX_VALUES // 64 + 1))
        self.assertEqual(got['--b'], [])

    def test_the_cap_counts_expansions_even_when_they_collapse_to_the_same_values(self):
        """Дубльовані розгортання не лишають слідів у виході, але коштують часу: стеля — на роботу."""
        aliases = ''.join(f':root{{--b: var(--a, {n})}}' for n in range(5000))
        t0 = time.monotonic()
        got = parse(self.themed('a', 64, 'a') + aliases)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual(got['--b'], [])

    def test_literal_values_are_not_capped(self):
        n = S.MAX_VALUES * 3
        got = parse(''.join(f':root{{--lit: v{i}}}' for i in range(n)))
        self.assertEqual(len(got['--lit']), n)

    def test_many_tokens_over_themes_are_capped_per_file(self):
        per = 50
        self.assertEqual(S.MAX_EXPANDED % per, 0)
        fit = S.MAX_EXPANDED // per
        css = self.themed('a', per, 'a') + ''.join(f':root{{--b{i}: var(--a)}}' for i in range(fit + 300))
        got = parse(css)
        lens = [len(got[f'--b{i}']) for i in range(fit + 300)]
        self.assertEqual(lens[:fit], [per] * fit)             # рівно стеля — ще можна
        self.assertEqual(lens[fit:], [0] * 300)               # далі — «значень не знаємо»
        self.assertLessEqual(sum(lens), S.MAX_EXPANDED)


class BigInputTest(unittest.TestCase):
    def test_two_mebibytes_of_css_parse_in_time(self):
        rule = ':root{--color-aaaaaaaaaa-%d: #%06x; --x-%d: calc(1px*2); --y-%d: url(a;b.png)}\n'
        out, n = [], 0
        while sum(map(len, out)) < 2 * MIB - 200:
            out.append(rule % (n, n, n, n))
            n += 1
        text = ''.join(out)
        t0 = time.monotonic()
        got = parse(text)
        dt = time.monotonic() - t0
        self.assertLess(dt, 4, f'розбір 2 МіБ зайняв {dt:.1f} с — більше за тайм-аут check (5 с) з запасом')
        self.assertEqual(len(got), 3 * n)


# -------------------------------------------------------------------------------------- читання

class Fs(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='csstok-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.s = load_server()          # свіжий кеш на кожен тест

    def path(self, name='tokens.css'):
        return os.path.join(self.tmp, name)

    def write(self, text, name='tokens.css', mode='w'):
        p = self.path(name)
        with open(p, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
            f.write(text)
        return p

    @staticmethod
    def ctx(path):
        return {'space': {'id': 's', 'path': '/x'}, 'settings': {'file': path}, 'secrets': {}}

    def tokens(self, path):
        return self.s.tokens(self.ctx(path))

    def bump(self, p, seconds=5):
        st = os.stat(p)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 10 ** 9))


class ReadTest(Fs):
    def test_shape_of_the_result(self):
        p = self.write(root('--a: 1') + '[data-theme=dark]{--a:2}')
        res = self.tokens(p)
        self.assertEqual(set(res), {'tokens', 'source'})
        self.assertEqual(res['tokens'], {'--a': ['1', '2']})
        self.assertEqual(res['source'], 'tokens.css')
        json.dumps(res)

    def test_a_file_without_tokens_is_an_empty_dict_not_an_error(self):
        self.assertEqual(self.tokens(self.write('body{color:red}'))['tokens'], {})

    def test_bom_and_crlf_and_invalid_utf8_are_tolerated(self):
        p = self.write(b'\xef\xbb\xbf@media (min-width:1px){:root{\r\n--a: 1;\r\n--b: \xff\xfe;\r\n}}', mode='wb')
        got = self.tokens(p)['tokens']              # BOM, CRLF і биті байти читанню не шкодять (саме зняття BOM
        #                                             не спостережне: розбір толерантний до U+FEFF на початку)
        self.assertEqual(got['--a'], ['1'])
        self.assertEqual(len(got['--b']), 1)

    def test_missing_file(self):
        with self.assertRaises(self.s.TokensError) as cx:
            self.tokens(self.path('nope.css'))
        self.assertIn('not found', str(cx.exception))

    def test_a_path_the_os_cannot_even_encode_is_a_tokens_error(self):
        for bad in ('a\0b.css', '\ud800.css', self.path('x\0')):
            with self.assertRaises(self.s.TokensError, msg=repr(bad)) as cx:
                self.tokens(bad)
            self.assertEqual(str(cx.exception), 'file: bad path')

    def test_fstat_failure_is_a_tokens_error_and_closes_the_descriptor(self):
        p = self.write(root('--a: 1'))
        closed, opened = [], []
        real_open, real_close = os.open, os.close

        def spy_open(*a, **k):
            fd = real_open(*a, **k)
            opened.append(fd)
            return fd

        def spy_close(fd):
            closed.append(fd)
            return real_close(fd)

        def boom(fd):
            raise OSError(5, 'Input/output error')
        with mock.patch.object(self.s.os, 'open', spy_open), mock.patch.object(self.s.os, 'close', spy_close), \
                mock.patch.object(self.s.os, 'fstat', boom):
            with self.assertRaises(self.s.TokensError) as cx:
                self.tokens(p)
        self.assertIn('cannot be read', str(cx.exception))
        self.assertEqual(sorted(opened), sorted(closed))

    def test_no_file_setting(self):
        for settings in ({}, {'file': ''}, {'file': '   '}, {'file': None}, {'file': 3}):
            with self.assertRaises(self.s.TokensError, msg=repr(settings)) as cx:
                self.s.tokens({'space': {}, 'settings': settings, 'secrets': {}})
            self.assertIn('not set', str(cx.exception))

    def test_directory_is_refused(self):
        os.mkdir(self.path('dir.css'))
        with self.assertRaises(self.s.TokensError) as cx:
            self.tokens(self.path('dir.css'))
        self.assertIn('regular file', str(cx.exception))

    @unittest.skipIf(os.name == 'nt', 'POSIX special files')
    def test_fifo_is_refused_without_hanging(self):
        fifo = self.path('pipe.css')
        os.mkfifo(fifo)
        box = []

        def work():
            try:
                self.tokens(fifo)
                box.append('returned')
            except Exception as e:  # noqa: BLE001
                box.append(e)
        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(5)
        if th.is_alive():                                   # відкрити писача, щоб потік-сирота не висів
            try:
                fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                os.close(fd)
            except OSError:
                pass
            th.join(2)
            self.fail('читання FIFO зависло')
        self.assertTrue(box and isinstance(box[0], self.s.TokensError), box)
        self.assertIn('regular file', str(box[0]))

    @unittest.skipIf(os.name == 'nt', 'POSIX special files')
    def test_the_type_is_checked_on_the_descriptor_not_on_the_path(self):
        """Між перевіркою й `open` файл можна підмінити (шлях був звичайним файлом, а відкрився FIFO):
        перевіряється те, що відкрито, а не те, що лежало за шляхом."""
        p = self.write(root('--a: 1'))
        fifo = self.path('pipe.css')
        os.mkfifo(fifo)
        real_open = os.open
        swapped = lambda path, flags, *a, **k: real_open(fifo, flags, *a, **k)      # noqa: E731
        with mock.patch.object(self.s.os, 'open', swapped):
            with self.assertRaises(self.s.TokensError) as cx:
                self.tokens(p)
        self.assertIn('regular file', str(cx.exception))

    @unittest.skipIf(os.name == 'nt' or not os.path.exists('/dev/null'), 'POSIX special files')
    def test_device_is_refused(self):
        with self.assertRaises(self.s.TokensError) as cx:
            self.tokens('/dev/null')
        self.assertIn('regular file', str(cx.exception))

    @unittest.skipIf(os.name == 'nt', 'symlinks')
    def test_symlink_to_a_regular_file_is_followed(self):
        real = self.write(root('--a: 1'), 'real.css')
        os.symlink(real, self.path('link.css'))
        self.assertEqual(self.tokens(self.path('link.css'))['tokens'], {'--a': ['1']})

    @unittest.skipIf(os.name == 'nt', 'symlinks')
    def test_symlink_to_a_directory_or_a_dangling_one_is_refused(self):
        os.mkdir(self.path('d'))
        os.symlink(self.path('d'), self.path('dl.css'))
        os.symlink(self.path('gone'), self.path('dangling.css'))
        for name in ('dl.css', 'dangling.css'):
            with self.assertRaises(self.s.TokensError, msg=name):
                self.tokens(self.path(name))

    def test_size_limit(self):
        head = root('--a: 1')
        ok = self.write(head + ' ' * (2 * MIB - len(head)), 'ok.css')
        self.assertEqual(os.path.getsize(ok), 2 * MIB)
        self.assertEqual(self.tokens(ok)['tokens'], {'--a': ['1']})        # рівно 2 МіБ — ще можна
        big = self.write(head + ' ' * (2 * MIB - len(head) + 1), 'big.css')
        self.assertEqual(os.path.getsize(big), 2 * MIB + 1)
        with self.assertRaises(self.s.TokensError) as cx:
            self.tokens(big)
        self.assertIn('2 MiB', str(cx.exception))

    def test_an_oversize_file_is_refused_before_reading_a_byte(self):
        big = self.write(' ' * (2 * MIB + 1), 'big.css')
        with mock.patch.object(self.s.os, 'read', side_effect=AssertionError('прочитано завеликий файл')):
            with self.assertRaises(self.s.TokensError):
                self.tokens(big)

    def test_every_descriptor_is_closed_on_every_path(self):
        ok = self.write(root('--a: 1'))
        big = self.write(' ' * (2 * MIB + 1), 'big.css')
        os.mkdir(self.path('d'))
        opened, closed = [], []
        real_open, real_close = os.open, os.close

        def spy_open(*a, **k):
            fd = real_open(*a, **k)
            opened.append(fd)
            return fd

        def spy_close(fd):
            closed.append(fd)
            return real_close(fd)
        with mock.patch.object(self.s.os, 'open', spy_open), mock.patch.object(self.s.os, 'close', spy_close):
            self.tokens(ok)
            self.tokens(ok)                                        # із кешу
            for bad in (big, self.path('d'), self.path('nope.css')):
                with self.assertRaises(self.s.TokensError):
                    self.tokens(bad)
        self.assertEqual(len(opened), 4)
        self.assertEqual(sorted(opened), sorted(closed))

    def test_the_read_itself_is_bounded(self):
        """Файл виріс між `fstat` і читанням (чи `fstat` збрехав): читаємо рівно ліміт + 1 байт і
        відмовляємо, а не тягнемо потік, поки не скінчиться."""
        p = self.write(root('--a: 1'))
        real_fstat = os.fstat
        handed = []

        class Lie:
            def __init__(self, st):
                self._st = st
                self.st_size = 10             # «малий» файл

            def __getattr__(self, k):
                return getattr(self._st, k)

        def endless(fd, n):
            if sum(handed) > 3 * MIB:
                raise AssertionError('читання без межі')
            handed.append(n)
            return b'x' * n
        with mock.patch.object(self.s.os, 'fstat', lambda fd: Lie(real_fstat(fd))), \
                mock.patch.object(self.s.os, 'read', endless):
            with self.assertRaises(self.s.TokensError) as cx:
                self.tokens(p)
        self.assertIn('2 MiB', str(cx.exception))
        self.assertEqual(sum(handed), 2 * MIB + 1)
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})

    def test_result_is_a_copy_the_cache_cannot_be_poisoned(self):
        p = self.write(root('--a: 1'))
        first = self.tokens(p)
        first['tokens']['--a'].append('EVIL')
        first['tokens']['--b'] = ['x']
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})


class CacheTest(Fs):
    def counted(self):
        calls = []
        real = self.s.parse_css_tokens

        def spy(text):
            calls.append(text)
            return real(text)
        return calls, mock.patch.object(self.s, 'parse_css_tokens', spy)

    def test_unchanged_file_is_parsed_once(self):
        p = self.write(root('--a: 1'))
        calls, patch = self.counted()
        with patch:
            for _ in range(3):
                self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})
        self.assertEqual(len(calls), 1)

    def test_changed_mtime_reparses(self):
        p = self.write(root('--a: 1'))
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})
        st = os.stat(p)
        self.write(root('--a: 2'))                       # той самий розмір
        self.assertEqual(os.path.getsize(p), st.st_size)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 7 * 10 ** 9))
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['2']})

    def test_a_sub_second_mtime_change_reparses(self):
        p = self.write(root('--a: 1'))
        st = os.stat(p)
        base = (int(st.st_mtime) + 10) * 10 ** 9
        os.utime(p, ns=(st.st_atime_ns, base))
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})
        self.write(root('--a: 2'))
        os.utime(p, ns=(st.st_atime_ns, base + 50))
        if os.stat(p).st_mtime_ns != base + 50:
            self.skipTest('файлова система без наносекундних mtime')
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['2']})

    def test_changed_size_reparses_even_with_the_same_mtime(self):
        p = self.write(root('--a: 1'))
        st = os.stat(p)
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1']})
        self.write(root('--a: 1; --b: 2'))
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))     # mtime повернуто
        self.assertNotEqual(os.path.getsize(p), st.st_size)
        self.assertEqual(self.tokens(p)['tokens'], {'--a': ['1'], '--b': ['2']})

    def test_two_files_with_the_same_size_and_mtime_do_not_share_an_entry(self):
        a = self.write(root('--a: 1'), 'a.css')
        b = self.write(root('--b: 2'), 'b.css')
        st = os.stat(a)
        os.utime(b, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual(os.path.getsize(a), os.path.getsize(b))
        self.assertEqual(self.tokens(a)['tokens'], {'--a': ['1']})
        self.assertEqual(self.tokens(b)['tokens'], {'--b': ['2']})

    def test_cache_is_bounded(self):
        for i in range(self.s._CACHE_MAX + 5):
            self.tokens(self.write(root(f'--a{i}: 1'), f'f{i}.css'))
        self.assertLessEqual(len(self.s._CACHE), self.s._CACHE_MAX)

    def test_a_new_version_of_a_file_replaces_the_old_entry_of_the_same_path(self):
        p = self.write(root('--a: 1'))
        other = self.write(root('--o: 1'), 'other.css')
        self.tokens(other)
        for i in range(2, 6):
            self.write(root(f'--a: {i}; --pad: {"x" * i}'))
            self.bump(p, i)
            self.assertEqual(self.tokens(p)['tokens']['--a'], [str(i)])
            self.assertEqual(len([k for k in self.s._CACHE if k[0] == p]), 1)
        self.assertEqual(len([k for k in self.s._CACHE if k[0] == other]), 1)      # чужий шлях не зачеплено
        self.assertEqual(len(self.s._CACHE), 2)

    def test_the_oldest_entry_goes_first(self):
        files = [self.write(root(f'--a{i}: 1'), f'f{i}.css') for i in range(self.s._CACHE_MAX + 3)]
        for f in files:
            self.tokens(f)
        calls, patch = self.counted()
        with patch:
            self.tokens(files[-1])
            self.tokens(files[-2])
            self.assertEqual(len(calls), 0)                  # найновіші лишились
            self.tokens(files[0])
            self.assertEqual(len(calls), 1)                  # найстаріший витіснено

    def test_a_failed_read_leaves_no_entry(self):
        with self.assertRaises(self.s.TokensError):
            self.tokens(self.path('nope.css'))
        self.assertEqual(len(self.s._CACHE), 0)

    def test_a_fresh_load_has_a_fresh_cache(self):
        p = self.write(root('--a: 1'))
        self.tokens(p)
        other = load_server()
        self.assertEqual(len(other._CACHE), 0)


class CheckTest(Fs):
    def check(self, path):
        return self.s.check(self.ctx(path))

    def test_ok_reports_the_count(self):
        res = self.check(self.write(root('--a: 1; --b: 2') + '[data-theme=dark]{--a: 3}'))
        self.assertEqual(res['ok'], True)
        self.assertIn('2', res.get('detail', ''))

    def test_no_tokens_is_not_ok(self):
        res = self.check(self.write('body{color:red} .a{--x:1}'))
        self.assertFalse(res['ok'])
        self.assertIn(':root', res['error'])

    def test_check_never_raises_whatever_the_path(self):
        for bad in ('a\0b.css', '\ud800.css', '', '   ', None, 3, '/dev/null/x', self.tmp, self.path('nope')):
            res = self.s.check(self.ctx(bad))
            self.assertEqual(res['ok'], False, repr(bad))
            self.assertIsInstance(res['error'], str)
        self.assertEqual(self.check('a\0b.css'), {'ok': False, 'error': 'file: bad path'})
        self.assertEqual(self.check('\ud800.css'), {'ok': False, 'error': 'file: bad path'})
        self.assertEqual(self.s.check({}), {'ok': False, 'error': 'file: not set'})
        self.assertEqual(self.s.check(None), {'ok': False, 'error': 'file: not set'})

    def test_unreadable_is_not_ok_and_does_not_raise(self):
        self.assertEqual(self.check(self.path('nope.css')), {'ok': False, 'error': 'file: not found'})
        os.mkdir(self.path('d.css'))
        res = self.check(self.path('d.css'))
        self.assertFalse(res['ok'])
        self.assertIn('regular file', res['error'])

    def test_a_token_whose_value_cannot_be_resolved_still_counts(self):
        self.assertTrue(self.check(self.write(root('--a: var(--nope)')))['ok'])

    def test_check_creates_nothing(self):
        p = self.write(root('--a: 1'))
        before = sorted(os.listdir(self.tmp))
        self.check(p)
        self.check(self.path('nope.css'))
        self.assertEqual(sorted(os.listdir(self.tmp)), before)


# -------------------------------------------------------------------------------- вигляд модуля

class SourceShapeTest(unittest.TestCase):
    #: Усе, що `server.py` може імпортувати (exec-иться ядром: без `serve`, ядра, сусідів, `importlib`).
    ALLOWED_IMPORTS = {'itertools', 'os', 're', 'stat', 'threading'}

    def test_imports_are_an_explicit_stdlib_allowlist(self):
        with open(SERVER, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, 'відносний імпорт: модуль exec-иться, сусідів нема')
                mods.add((node.module or '').split('.')[0])
        self.assertTrue(mods, 'очікували хоч один імпорт')
        self.assertEqual(mods - self.ALLOWED_IMPORTS, set(), 'імпорт поза списком дозволених')

    def test_no_dynamic_code_or_imports(self):
        with open(SERVER, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(names & {'__import__', 'exec', 'eval', 'compile', 'importlib'}, set())
        self.assertEqual(attrs & {'__import__', 'exec', 'eval', 'import_module', 'system', 'popen'}, set())

    def test_no_file_relative_loading(self):
        with open(SERVER, encoding='utf-8') as f:
            src = f.read()
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn('__file__', names | attrs)
        self.assertNotIn('sys.path', src)

    def test_the_two_role_functions_exist(self):
        self.assertTrue(callable(S.check) and callable(S.tokens) and callable(S.parse_css_tokens))


# ---------------------------------------------------------------- інтеграція з каркасом модулів

class FrameworkTest(unittest.TestCase):
    """Справжній `app/modules`, справжній `deai_modules`; тимчасові HOME/DEAI_HOME/DC_TASKS_FILE."""

    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='csstok-fw-'))
        self.saved = {k: os.environ.get(k) for k in _ENV}
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        os.environ['HOME'] = self.home
        os.environ['DEAI_HOME'] = os.path.join(self.tmp, 'deai')
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'legacy', 'tasks.json')
        spaces.clear_request_space()
        dm.reset_caches()
        self.deadlock = threading.Event()

        def wake():
            self.deadlock.set()
            try:
                spaces.WRITE_LOCK.release()
            except RuntimeError:
                pass
        self.watchdog = threading.Timer(10, wake)
        self.watchdog.daemon = True
        self.watchdog.start()

    def tearDown(self):
        self.watchdog.cancel()
        spaces.clear_request_space()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dm.reset_caches()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.deadlock.is_set():
            self.fail('тест завис на WRITE_LOCK')

    def new_space(self, name='Alpha', integrations=False):
        sid = spaces.create_space(name, 'space-1', os.path.join(self.home, 'work', name.lower()))
        if integrations:
            reg_file = os.path.join(self.tmp, 'deai', 'spaces.json')
            with open(reg_file, encoding='utf-8') as f:
                reg = json.load(f)
            for s in reg['spaces']:
                if s['id'] == sid:
                    s['integrations'] = True
            with open(reg_file, 'w', encoding='utf-8') as f:
                json.dump(reg, f)
        return next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)

    def css(self, sp, text, name='tokens.css'):
        p = os.path.join(sp['path'], name)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return p

    # ---- каталог ----
    def test_the_real_catalog_loads_css_tokens(self):
        m = dm.catalog()['css-tokens']
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual(m.roles, ['tokens'])
        self.assertEqual(m.api, 1)
        self.assertEqual(m.dir, MODULE_DIR)
        self.assertEqual(len(m.settings), 1)
        s = m.settings[0]
        self.assertEqual((s['key'], s['type'], s['required']), ('file', 'path', True))
        self.assertNotIn('default', s)
        self.assertEqual(m.secret_keys(), [])
        self.assertTrue(callable(m.fn('check')) and callable(m.fn('tokens')))
        self.assertIsNone(m.fn('publish'))

    def test_loading_leaves_no_bytecode_behind(self):
        dm.catalog()
        self.assertFalse(os.path.exists(os.path.join(MODULE_DIR, '__pycache__')))

    def test_manifest_on_disk(self):
        with open(os.path.join(MODULE_DIR, 'module.json'), encoding='utf-8') as f:
            man = json.load(f)
        self.assertEqual((man['api'], man['id'], man['roles']), (1, 'css-tokens', ['tokens']))
        self.assertEqual([x['key'] for x in man['settings']], ['file'])

    # ---- у просторі ----
    def test_off_by_default_and_taken_by_enabling(self):
        sp = self.new_space()
        self.assertIsNone(dm.provider('tokens', sp))
        self.assertIsNone(dm.capabilities(sp)['tokens'])
        dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': 'tokens.css'})
        self.assertEqual(dm.provider('tokens', sp).id, 'css-tokens')
        self.assertEqual(dm.capabilities(sp)['tokens'], 'css-tokens')

    def test_check_through_the_core(self):
        sp = self.new_space()
        self.css(sp, root('--a: 1; --b: var(--a)'))
        dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': 'tokens.css'})
        self.assertEqual(dm.check(sp, 'css-tokens'), {'ok': True, 'detail': '2 tokens'})
        self.assertEqual(dm.last_check(sp['id'], 'css-tokens'), {'ok': True, 'detail': '2 tokens'})

    def test_check_failures_are_ok_false_results(self):
        sp = self.new_space()
        dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': 'nope.css'})
        self.assertEqual(dm.check(sp, 'css-tokens'), {'ok': False, 'error': 'file: not found'})
        self.css(sp, 'body{}', 'nope.css')
        self.assertFalse(dm.check(sp, 'css-tokens')['ok'])

    def test_the_required_file_setting_is_enforced_by_the_core(self):
        sp = self.new_space()
        dm.write_module_state(sp, 'css-tokens', enabled=True)
        with self.assertRaises(dm.ModuleError) as cx:
            dm.check(sp, 'css-tokens')
        self.assertEqual(cx.exception.code, 'bad-settings')

    def test_tokens_through_the_core_with_a_relative_and_a_symbolic_path(self):
        sp = self.new_space()
        self.css(sp, root('--a: 1'))
        os.makedirs(os.path.join(self.home, 'ds'))
        with open(os.path.join(self.home, 'ds', 'brand.css'), 'w', encoding='utf-8') as f:
            f.write(root('--b: 2'))
        m = dm.catalog()['css-tokens']
        for stored, want, source in (('tokens.css', {'--a': ['1']}, 'tokens.css'),
                                     ('{home}/ds/brand.css', {'--b': ['2']}, 'brand.css'),
                                     ('~/ds/brand.css', {'--b': ['2']}, 'brand.css')):
            dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': stored})
            ctx = dm._ctx(sp, m)
            self.assertTrue(os.path.isabs(ctx['settings']['file']), stored)
            self.assertEqual(dm.call(m, 'tokens', ctx), {'tokens': want, 'source': source}, stored)

    def test_a_broken_file_is_a_module_error_through_the_core(self):
        sp = self.new_space()
        dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': 'nope.css'})
        m = dm.catalog()['css-tokens']
        with self.assertRaises(dm.ModuleError) as cx:
            dm.call(m, 'tokens', dm._ctx(sp, m))
        self.assertEqual(cx.exception.code, 'module-error')
        self.assertIn('not found', cx.exception.message)

    def test_the_tokens_role_is_free_in_a_liga_space(self):
        sp = self.new_space(integrations=True)
        self.assertIsNone(dm.provider('tokens', sp))
        dm.write_module_state(sp, 'css-tokens', enabled=True, settings={'file': 'tokens.css'})
        self.assertEqual(dm.provider('tokens', sp).id, 'css-tokens')
        self.assertEqual(dm.provider('publish', sp), 'legacy')       # публікацію ЛІГА це не зачепило


def _md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


if __name__ == '__main__':
    unittest.main()

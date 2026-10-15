"""`app/modules/static-publish`: неявний постачальник ролі `publish` — збірка превʼю → тека ПОЗА простором.

Модуль перевіряється через справжній `deai_modules` і справжню теку `app/modules` (маніфест,
`provider`, `capabilities`, `module_ctx`, `call`, `check`): так тест бачить саме те, що виконає
сервер, зокрема `ctx['folder_ok']` і `ctx['ModuleError']`, які ядро кладе в `ctx`.

Кожен тест має власні `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`
(тести створюють простори), справжній `~/deai-published` не чіпається: `{home}` — тимчасова домівка.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402

MODULE_DIR = os.path.join(os.path.dirname(_HERE), 'app', 'modules', 'static-publish')
SERVER = os.path.join(MODULE_DIR, 'server.py')
MARKER = '.deai-published'
MID = 'static-publish'
SECRET = 'hunter2-SECRET-pw'
_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def put(path, text='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def tree(root):
    """Знімок теки без слідування за посиланнями: `{відносний шлях: ('d',) | ('f', md5) | ('l', ціль)}`.
    Порівнюючи знімки до й після, тест бачить і зайве створене, і зайве видалене, і змінений вміст."""
    out = {}
    for dp, dns, fns in os.walk(root, followlinks=False):
        for n in dns + fns:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out[rel] = ('l', os.readlink(p))
            elif os.path.isdir(p):
                out[rel] = ('d',)
            else:
                with open(p, 'rb') as f:
                    out[rel] = ('f', hashlib.md5(f.read()).hexdigest())
    return out


class StaticPublish(unittest.TestCase):
    """Справжній `app/modules`, справжній `deai_modules`; тимчасові HOME/DEAI_HOME/DC_TASKS_FILE."""

    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='statpub-'))
        # Прибирання — cleanup-ом (виконується ПІСЛЯ tearDown і в зворотному порядку): тест, що зняв права на
        # теку (`chmod 0o500`), відновлює їх своїм cleanup-ом, зареєстрованим ПІЗНІШЕ, тож до rmtree.
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.saved = {k: os.environ.get(k) for k in _ENV}
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        # DEAI_HOME — у домівці (як у test_modules): інакше тимчасова тека macOS дала б `path-system` раніше за `path-deai-home`
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        os.environ['HOME'] = self.home
        os.environ['DEAI_HOME'] = self.deai
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'legacy', 'tasks.json')
        # Теку інструмента підміняємо тимчасовою: справжня (репозиторій) не може стати ціллю публікації, навіть якщо
        # правило колись зламається, а `path-tool` перевіряється саме як причина.
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        patch = mock.patch.object(spaces, 'ROOT', self.tool)
        patch.start()
        self.addCleanup(patch.stop)
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
        self.sp = self.new_space()
        self.m = dm.catalog()[MID]
        self.folder = os.path.join(self.home, 'deai-published', self.sp['id'])
        self.build = os.path.join(self.tmp, 'build')
        self.make_build({'index.html': '<h1>v1</h1>', 'assets/app.css': 'a{}'})

    def tearDown(self):
        self.watchdog.cancel()
        spaces.clear_request_space()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dm.reset_caches()
        if self.deadlock.is_set():
            self.fail('тест завис на WRITE_LOCK')

    # ---- фікстури ----
    def hp(self, *parts):
        return os.path.join(self.home, *parts)

    def new_space(self, name='Alpha', integrations=False):
        sid = spaces.create_space(name, 'space-1', os.path.join(self.home, 'work', name.lower()))
        if integrations:
            reg_file = os.path.join(self.deai, 'spaces.json')
            with open(reg_file, encoding='utf-8') as f:
                reg = json.load(f)
            for s in reg['spaces']:
                if s['id'] == sid:
                    s['integrations'] = True
            with open(reg_file, 'w', encoding='utf-8') as f:
                json.dump(reg, f)
        return next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)

    def make_build(self, files):
        shutil.rmtree(self.build, ignore_errors=True)
        os.makedirs(self.build)
        for rel, text in files.items():
            put(os.path.join(self.build, rel), text)

    def set_folder(self, value):
        dm.write_module_state(self.sp, MID, settings={'folder': value})

    def ctx(self):
        return dm.module_ctx(self.sp, MID)

    def pub(self, tid='t1', ctx=None, build=None):
        """Публікація через ядро: `dm.call` — як це робитиме диспетчер."""
        return dm.call(self.m, 'publish', ctx if ctx is not None else self.ctx(),
                       build or self.build, {'id': tid, 'title': 'T ' + str(tid), 'dir': self.hp('t', str(tid))})

    def direct(self, ctx, tid='t1', build=None):
        """Виклик функції модуля напряму (без `call`): так видно, що кидає сам модуль."""
        return self.m.fn('publish')(ctx, build or self.build, {'id': tid, 'title': 'T', 'dir': self.hp('t')})

    def read(self, *parts):
        with open(os.path.join(self.folder, *parts), encoding='utf-8') as f:
            return f.read()

    def is_marked(self, *parts):
        return os.path.isfile(os.path.join(self.folder, *parts, MARKER))

    def refused(self, code='bad-folder', status=409, **kw):
        """`with self.refused(): …` — блок мусить кинути `ModuleError` ядра з цим кодом і статусом."""
        outer = self

        class _Ctx:
            def __enter__(self_):
                self_.cm = outer.assertRaises(dm.ModuleError)
                self_.cx = self_.cm.__enter__()
                return self_.cx

            def __exit__(self_, *exc):
                done = self_.cm.__exit__(*exc)
                if done:
                    outer.assertEqual((self_.cx.exception.code, self_.cx.exception.status), (code, status))
                return done
        return _Ctx()

    # ------------------------------------------------------------------------------- каталог
    def test_the_real_catalog_loads_static_publish(self):
        m = dm.catalog()[MID]
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual(m.roles, ['publish'])
        self.assertEqual((m.api, m.name, m.version, m.dir), (1, 'Публікація в теку', '1.0.0', MODULE_DIR))
        by = {s['key']: s for s in m.settings}
        self.assertEqual(list(by), ['folder', 'password'])
        self.assertEqual((by['folder']['type'], by['folder']['required'], by['folder']['default']),
                         ('path', True, '{home}/deai-published/{space_id}'))
        self.assertEqual((by['password']['type'], by['password']['required']), ('secret', False))
        self.assertNotIn('default', by['password'])
        self.assertEqual(m.secret_keys(), ['password'])
        self.assertTrue(callable(m.fn('check')) and callable(m.fn('publish')))
        self.assertIsNone(m.fn('tokens'))

    def test_manifest_on_disk(self):
        with open(os.path.join(MODULE_DIR, 'module.json'), encoding='utf-8') as f:
            man = json.load(f)
        self.assertEqual((man['api'], man['id'], man['roles']), (1, MID, ['publish']))
        self.assertEqual([(s['key'], s['type']) for s in man['settings']],
                         [('folder', 'path'), ('password', 'secret')])

    def test_loading_leaves_no_bytecode_behind(self):
        dm.catalog()
        self.assertFalse(os.path.exists(os.path.join(MODULE_DIR, '__pycache__')))

    # ------------------------------------------------------------- неявний постачальник ролі
    def test_it_is_the_implicit_provider_in_a_space_without_integrations(self):
        self.assertEqual(dm.provider('publish', self.sp).id, MID)
        self.assertEqual(dm.capabilities(self.sp), {'publish': MID, 'tokens': None})
        st = dm.effective_state(self.sp)[MID]
        self.assertEqual((st['enabled'], st['implicit']), (True, True))
        self.assertEqual(st['settings'], {'folder': '{home}/deai-published/{space_id}'})

    def test_legacy_and_none_cases_stay_as_they_were(self):
        ig = self.new_space('Liga', integrations=True)
        self.assertEqual(dm.provider('publish', ig), 'legacy')       # простір ЛІГА: зашитий шлях
        self.assertEqual(dm.capabilities(ig)['publish'], 'legacy')
        self.assertIsNone(dm.provider('tokens', self.sp))
        spaces.clear_request_space()
        self.assertEqual(dm.provider('publish'), 'legacy')           # простір запиту не зафіксовано
        self.assertIsNone(dm.provider('tokens'))
        dm.write_module_state(self.sp, MID, enabled=False)           # явне «вимкнено» — модуля нема, а ЛІГИ теж
        self.assertIsNone(dm.provider('publish', self.sp))
        dm.write_module_state(self.sp, MID, enabled=True)
        self.assertEqual(dm.provider('publish', self.sp).id, MID)

    def test_the_default_folder_is_outside_the_space_and_passes_the_core_rules(self):
        self.assertEqual(dm.published_root(self.sp, MID), self.folder)
        self.assertNotEqual(os.path.commonpath([self.folder, self.sp['path']]), self.sp['path'])
        self.assertEqual(dm.folder_ok(self.sp, self.folder), (True, None))

    # ------------------------------------------------------------------------------ публікація
    def test_publish_into_an_empty_folder(self):
        self.assertFalse(os.path.exists(self.folder))
        res = self.pub('t1')
        self.assertEqual(res, {'path': os.path.join(self.folder, 't1')})
        self.assertEqual(self.read('t1', 'index.html'), '<h1>v1</h1>')
        self.assertEqual(self.read('t1', 'assets', 'app.css'), 'a{}')
        self.assertTrue(self.is_marked('t1'))
        self.assertEqual(os.listdir(self.folder), ['t1'])            # ні .tmp-, ні .old-

    def test_republish_replaces_the_content_and_keeps_the_marker(self):
        self.pub('t1')
        self.make_build({'index.html': '<h1>v2</h1>', 'new/page.html': 'p'})
        self.assertEqual(self.pub('t1'), {'path': os.path.join(self.folder, 't1')})
        self.assertEqual(self.read('t1', 'index.html'), '<h1>v2</h1>')
        self.assertEqual(self.read('t1', 'new', 'page.html'), 'p')
        self.assertFalse(os.path.exists(os.path.join(self.folder, 't1', 'assets')))   # старе зникло
        self.assertTrue(self.is_marked('t1'))
        self.assertEqual(os.listdir(self.folder), ['t1'])

    def test_tasks_do_not_touch_each_other(self):
        self.pub('t1')
        before = tree(os.path.join(self.folder, 't1'))
        self.make_build({'index.html': 'other'})
        self.pub('t2')
        self.pub('t2')
        self.assertEqual(tree(os.path.join(self.folder, 't1')), before)
        self.assertEqual(sorted(os.listdir(self.folder)), ['t1', 't2'])

    def test_the_result_is_a_plain_path_dict(self):
        res = self.direct(self.ctx())
        self.assertEqual(list(res), ['path'])
        self.assertIsInstance(res['path'], str)

    def test_a_task_id_may_hold_word_chars_and_dashes(self):
        for tid in ('t-1', 'T_2', '123', 'a-b-c'):
            self.assertEqual(self.pub(tid), {'path': os.path.join(self.folder, tid)})

    # ----------------------------------------------------------- наявна тека задачі: маркер
    def test_an_existing_folder_without_the_marker_is_refused_and_untouched(self):
        dest = os.path.join(self.folder, 't1')
        put(os.path.join(dest, 'precious.txt'), 'mine')
        put(os.path.join(dest, 'sub', 'deep.txt'), 'deep')
        before = tree(self.folder)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(self.folder), before)                   # нічого не створено й не видалено

    def test_a_symlink_at_the_task_folder_is_refused_and_the_target_untouched(self):
        victim = os.path.join(self.tmp, 'victim')
        put(os.path.join(victim, 'keep.txt'), 'keep')
        put(os.path.join(victim, MARKER), '')                        # навіть із маркером усередині цілі
        os.makedirs(self.folder)
        os.symlink(victim, os.path.join(self.folder, 't1'))
        before_v, before_f = tree(victim), tree(self.folder)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(victim), before_v)
        self.assertEqual(tree(self.folder), before_f)
        self.assertTrue(os.path.islink(os.path.join(self.folder, 't1')))

    def test_a_dangling_symlink_and_a_plain_file_at_the_task_folder_are_refused(self):
        os.makedirs(self.folder)
        os.symlink(os.path.join(self.tmp, 'nowhere'), os.path.join(self.folder, 't1'))
        put(os.path.join(self.folder, 't2'), 'i am a file')
        before = tree(self.folder)
        for tid in ('t1', 't2'):
            with self.refused():
                self.pub(tid)
        self.assertEqual(tree(self.folder), before)

    def test_the_marker_must_be_a_regular_file(self):
        dest = os.path.join(self.folder, 't1')
        put(os.path.join(dest, 'a.txt'), 'a')
        put(os.path.join(self.tmp, 'outside-marker'), '')
        os.symlink(os.path.join(self.tmp, 'outside-marker'), os.path.join(dest, MARKER))
        before = tree(self.folder)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(self.folder), before)
        os.remove(os.path.join(dest, MARKER))
        os.mkdir(os.path.join(dest, MARKER))                          # теку-«маркер» теж не приймаємо
        before = tree(self.folder)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(self.folder), before)

    def test_a_refusal_deletes_nothing_not_even_this_tasks_marked_leftovers(self):
        put(os.path.join(self.folder, 't1', 'precious.txt'), 'mine')
        put(os.path.join(self.folder, '.tmp-t1-0123abcd', MARKER), '')
        before = tree(self.folder)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(self.folder), before)

    # ------------------------------------------------------------------------ залишки .tmp/.old
    def leftover(self, name, marked=True, body='stale'):
        d = os.path.join(self.folder, name)
        put(os.path.join(d, 'f.txt'), body)
        if marked:
            put(os.path.join(d, MARKER), '')
        return d

    def test_marked_leftovers_of_this_task_are_cleaned_up(self):
        self.pub('t1')
        a = self.leftover('.tmp-t1-0123abcd')
        b = self.leftover('.old-t1-89abcdef')
        self.make_build({'index.html': 'v2'})
        self.pub('t1')
        self.assertFalse(os.path.exists(a) or os.path.exists(b))
        self.assertEqual(os.listdir(self.folder), ['t1'])

    def test_other_tasks_unmarked_and_odd_leftovers_are_kept(self):
        self.pub('t1')
        keep = [
            self.leftover('.tmp-t2-0123abcd'),                        # чужої задачі, з маркером
            self.leftover('.old-t2-0123abcd'),
            self.leftover('.tmp-t1-ffffffff', marked=False),          # без маркера
            self.leftover('.old-t1-eeeeeeee', marked=False),
            self.leftover('.tmp-t1-0123abcd9'),                       # не наш формат: 9 символів
            self.leftover('.tmp-t1-0123abc'),                         # 7 символів
            self.leftover('.tmp-t1-ABCDEF01'),                        # регістр: ми генеруємо нижній
            self.leftover('.tmp-t1-zzzzzzzz'),                        # не hex
            self.leftover('.tmp-t1-aaaaaaaa-bbbbbbbb'),               # залишок задачі `t1-aaaaaaaa`, не `t1`
            self.leftover('.tmp-t1'),
            self.leftover('x.tmp-t1-0123abcd'),
            self.leftover('t1-0123abcd'),
        ]
        put(os.path.join(self.folder, '.tmp-t1-bbbbbbbb'), 'file, not a dir')      # не тека
        keep.append(os.path.join(self.folder, '.tmp-t1-bbbbbbbb'))
        before = tree(self.folder)
        before.pop('t1'), before.pop(os.path.join('t1', 'index.html')), before.pop(os.path.join('t1', 'assets'))
        before.pop(os.path.join('t1', 'assets', 'app.css')), before.pop(os.path.join('t1', MARKER))
        self.pub('t1')
        after = tree(self.folder)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith('t1' + os.sep) and k != 't1'}, before)
        for p in keep:
            self.assertTrue(os.path.lexists(p), p)

    def test_a_symlinked_leftover_is_kept_and_its_target_untouched(self):
        self.pub('t1')
        victim = os.path.join(self.tmp, 'victim')
        put(os.path.join(victim, 'keep.txt'), 'keep')
        put(os.path.join(victim, MARKER), '')
        os.symlink(victim, os.path.join(self.folder, '.old-t1-aaaaaaaa'))
        os.symlink(victim, os.path.join(self.folder, '.tmp-t1-bbbbbbbb'))
        before = tree(victim)
        self.make_build({'index.html': 'v2'})
        self.pub('t1')
        self.assertEqual(tree(victim), before)
        self.assertTrue(os.path.islink(os.path.join(self.folder, '.old-t1-aaaaaaaa')))
        self.assertTrue(os.path.islink(os.path.join(self.folder, '.tmp-t1-bbbbbbbb')))

    def test_a_symlinked_leftover_is_never_even_handed_to_rmtree(self):
        """`shutil.rmtree` сам відмовляється від посилання, але на це не покладаємось: модуль не передає його видаленню."""
        self.pub('t1')
        victim = os.path.join(self.tmp, 'victim')
        put(os.path.join(victim, MARKER), '')
        links = [os.path.join(self.folder, '.old-t1-aaaaaaaa'), os.path.join(self.folder, '.tmp-t1-bbbbbbbb')]
        for link in links:
            os.symlink(victim, link)
        self.make_build({'index.html': 'v2'})
        with mock.patch.object(shutil, 'rmtree', wraps=shutil.rmtree) as spy:
            self.pub('t1')
        handed = {os.path.abspath(c.args[0]) for c in spy.call_args_list}
        self.assertFalse(handed & set(links), handed)
        self.assertNotIn(victim, handed)

    def test_a_leftover_with_a_symlinked_marker_is_kept(self):
        self.pub('t1')
        d = self.leftover('.tmp-t1-cccccccc', marked=False)
        put(os.path.join(self.tmp, 'm'), '')
        os.symlink(os.path.join(self.tmp, 'm'), os.path.join(d, MARKER))
        self.pub('t1')
        self.assertTrue(os.path.isdir(d))

    # ---------------------------------------------------------------------------- ідентифікатор
    def test_a_bad_task_id_is_an_error_and_nothing_is_created(self):
        for bad in ('../x', 'a/b', '', '.x', '..', 'тест', 'a b', 't1\n', 'a\\b', 'x\0y', 'é', None, 5, ['t1']):
            with self.refused('module-error', 502):
                self.pub(bad)
            self.assertFalse(os.path.exists(os.path.dirname(self.folder)), repr(bad))
        with self.refused('module-error', 502):
            dm.call(self.m, 'publish', self.ctx(), self.build, 't1')           # task не словник
        with self.refused('module-error', 502):
            dm.call(self.m, 'publish', self.ctx(), self.build, {'title': 'no id'})
        self.assertFalse(os.path.exists(os.path.dirname(self.folder)))

    def test_a_missing_build_is_an_error_and_nothing_is_created(self):
        with self.refused('module-error', 502):
            self.pub('t1', build=os.path.join(self.tmp, 'no-such-build'))
        put(os.path.join(self.tmp, 'a-file'), 'x')
        with self.refused('module-error', 502):
            self.pub('t1', build=os.path.join(self.tmp, 'a-file'))
        self.assertFalse(os.path.exists(os.path.dirname(self.folder)))

    # ------------------------------------------------------------------- правила теки з ядра
    def bad_folders(self):
        sp2 = self.new_space('Beta')
        put(os.path.join(self.sp['path'], 'tasks.json'),
            json.dumps({'tasks': {'t9': {'dir': self.hp('designs', 't9')}}}))
        return {
            'path-registered': self.sp['path'],
            'path-overlap': os.path.join(sp2['path'], 'pub'),
            'path-too-broad': self.home,
            'path-deai-home': os.path.join(self.deai, 'pub'),
            'path-overlap/task': self.hp('designs', 't9'),
            'path-overlap/task-inside': self.hp('designs', 't9', 'pub'),
            'path-tool': os.path.join(self.tool, 'pub'),
        }

    def test_the_core_folder_rules_are_rechecked_on_publish_and_nothing_is_created(self):
        bad = self.bad_folders()
        for why, folder in bad.items():
            self.set_folder(folder)
            before = tree(self.tmp)
            with self.refused():
                self.pub('t1')
            self.assertEqual(tree(self.tmp), before, why)                # ні теки, ні .tmp-, ні батьківської
        self.set_folder('~')                                             # `~` — домівка
        before = tree(self.tmp)
        with self.refused():
            self.pub('t1')
        self.assertEqual(tree(self.tmp), before)

    def test_check_reports_the_folder_rule_code(self):
        for why, folder in self.bad_folders().items():
            self.set_folder(folder)
            before = tree(self.tmp)
            res = dm.check(self.sp, MID)
            self.assertEqual((res['ok'], res['error']), (False, 'bad-folder'), why)
            self.assertEqual(res['detail'], why.split('/')[0], why)          # код правила ядра, а не вигадка модуля
            self.assertEqual(tree(self.tmp), before, why)

    def test_a_refusal_from_the_core_rule_is_enforced_even_if_the_setting_looks_fine(self):
        """Правило береться з `ctx`, а не з налаштування: ядро, що відмовило, — остаточне слово."""
        ctx = self.ctx()
        ctx['folder_ok'] = lambda folder: (False, 'path-registered')
        before = tree(self.tmp)
        with self.refused():
            self.pub('t1', ctx=ctx)
        self.assertEqual(tree(self.tmp), before)
        res = self.m.fn('check')(ctx)
        self.assertEqual((res['ok'], res['error'], res['detail']), (False, 'bad-folder', 'path-registered'))

    def test_a_ctx_without_a_usable_rule_fails_closed(self):
        base = self.ctx()
        broken = {'no key': None, 'not callable': 5, 'raises': mock.Mock(side_effect=RuntimeError('boom')),
                  'odd result': lambda f: None, 'odd tuple': lambda f: ('yes', None)}
        for label, rule in broken.items():
            ctx = dict(base)
            if label == 'no key':
                ctx.pop('folder_ok')
            else:
                ctx['folder_ok'] = rule
            before = tree(self.tmp)
            with self.refused():
                self.pub('t1', ctx=ctx)
            self.assertEqual(tree(self.tmp), before, label)
            res = self.m.fn('check')(ctx)
            self.assertEqual((res['ok'], res['error']), (False, 'bad-folder'), label)

    def test_a_missing_or_relative_folder_setting_is_refused(self):
        for settings in ({}, {'folder': ''}, {'folder': None}, {'folder': 'rel/pub'}, {'folder': 5}):
            ctx = dict(self.ctx(), settings=settings)
            before = tree(self.tmp)
            with self.refused():
                self.pub('t1', ctx=ctx)
            self.assertEqual(tree(self.tmp), before, settings)
            res = self.m.fn('check')(ctx)
            self.assertFalse(res['ok'], settings)
            self.assertIn(res['error'], ('no-folder', 'bad-folder'))

    def test_the_error_class_is_the_cores_when_the_ctx_has_it_and_a_plain_error_otherwise(self):
        ctx = self.ctx()
        put(os.path.join(self.folder, 't1', 'a.txt'), 'a')                 # без маркера → відмова
        with self.assertRaises(dm.ModuleError) as cx:
            self.direct(ctx)                                               # напряму: це `ModuleError` ядра
        self.assertEqual((cx.exception.code, cx.exception.status), ('bad-folder', 409))
        ctx.pop('ModuleError')
        with self.assertRaises(Exception) as cx:
            self.direct(ctx)                                               # без класу — звичайний виняток, не мовчання
        self.assertNotIsInstance(cx.exception, dm.ModuleError)
        self.assertIn('bad-folder', str(cx.exception))

    # ------------------------------------------------------------------------------------ check
    def test_check_is_ok_for_the_default_folder_and_creates_nothing(self):
        before = tree(self.tmp)
        res = dm.check(self.sp, MID)
        self.assertEqual(res, {'ok': True, 'detail': self.folder})
        self.assertEqual(dm.last_check(self.sp['id'], MID), res)
        self.assertEqual(tree(self.tmp), before)
        self.assertFalse(os.path.exists(os.path.dirname(self.folder)))      # навіть батьківської
        self.assertEqual(self.m.fn('check')(self.ctx()), {'ok': True, 'detail': self.folder})
        self.assertEqual(tree(self.tmp), before)

    def test_check_is_ok_for_an_existing_writable_folder(self):
        os.makedirs(self.folder)
        before = tree(self.tmp)
        self.assertTrue(dm.check(self.sp, MID)['ok'])
        self.assertEqual(tree(self.tmp), before)

    def test_check_refuses_an_unwritable_nearest_ancestor(self):
        if os.geteuid() == 0:
            self.skipTest('root обходить права доступу')
        ro = self.hp('ro')
        os.makedirs(ro)
        os.chmod(ro, 0o500)
        self.addCleanup(os.chmod, ro, 0o700)                                # до rmtree з setUp
        self.set_folder(self.hp('ro', 'deep', 'pub'))
        before = tree(self.tmp)
        res = dm.check(self.sp, MID)
        self.assertEqual((res['ok'], res['error']), (False, 'not-writable'))
        self.assertIn(ro, res['detail'])
        self.assertEqual(tree(self.tmp), before)
        self.assertFalse(os.path.exists(self.hp('ro', 'deep')))
        with self.assertRaises(Exception):                                  # а публікація теж не вдається й нічого не лишає
            self.pub('t1')
        self.assertFalse(os.path.exists(self.hp('ro', 'deep')))
        self.assertEqual(tree(self.tmp), before)

    def test_check_refuses_when_the_nearest_existing_ancestor_is_a_file(self):
        put(self.hp('afile'), 'x')
        self.set_folder(self.hp('afile', 'pub'))
        before = tree(self.tmp)
        res = dm.check(self.sp, MID)
        self.assertEqual((res['ok'], res['error'], res['detail']), (False, 'bad-folder', 'path-not-dir'))
        self.assertEqual(tree(self.tmp), before)

    def test_check_through_the_core_needs_the_folder_setting(self):
        for ctx in ({}, {'settings': {}}, {'settings': None}):
            res = self.m.fn('check')(ctx)
            self.assertEqual((res['ok'], res['error']), (False, 'no-folder'))

    # -------------------------------------------------------------------- атомарність і збої
    def test_a_failing_copy_leaves_no_tmp_and_the_published_version_intact(self):
        self.pub('t1')
        before = tree(self.folder)
        self.make_build({'index.html': 'v2'})

        def boom(src, dst, *a, **k):
            os.makedirs(dst)
            put(os.path.join(dst, 'half.txt'), 'half')
            raise OSError('disk full')
        with mock.patch.object(shutil, 'copytree', side_effect=boom):
            with self.refused('module-error', 502) as cx:
                self.pub('t1')
        self.assertIn('disk full', cx.exception.message)
        self.assertEqual(tree(self.folder), before)                         # .tmp-* прибрано, v1 на місці

    def test_a_failing_copy_into_a_fresh_folder_leaves_no_tmp(self):
        def boom(src, dst, *a, **k):
            os.makedirs(dst)
            raise OSError('disk full')
        with mock.patch.object(shutil, 'copytree', side_effect=boom):
            with self.refused('module-error', 502):
                self.pub('t1')
        self.assertEqual(os.listdir(self.folder), [])                       # лише тека, яку створили самі

    def test_a_failure_after_the_copy_still_removes_the_tmp(self):
        self.pub('t1')
        before = tree(self.folder)
        self.make_build({'index.html': 'v2'})
        os.mkdir(os.path.join(self.build, MARKER))                          # маркер не записати: на його місці тека
        with self.refused('module-error', 502):
            self.pub('t1')
        self.assertEqual(tree(self.folder), before)

    def test_a_failing_swap_puts_the_old_version_back_and_removes_the_tmp(self):
        self.pub('t1')
        before = tree(self.folder)
        self.make_build({'index.html': 'v2'})
        real = os.rename

        def flaky(src, dst, *a, **k):
            if os.path.basename(src).startswith('.tmp-'):
                raise OSError('rename refused')
            return real(src, dst, *a, **k)
        with mock.patch.object(os, 'rename', flaky):
            with self.refused('module-error', 502):
                self.pub('t1')
        self.assertEqual(tree(self.folder), before)                         # v1 повернуто, .old-/.tmp- нема
        self.assertTrue(self.is_marked('t1'))

    def test_a_folder_that_appears_during_the_copy_is_still_not_overwritten(self):
        """Перевірка маркера повторюється безпосередньо перед заміною: за час копіювання теку могли підмінити."""
        real = shutil.copytree
        dest = os.path.join(self.folder, 't1')

        def racing(src, dst, *a, **k):
            r = real(src, dst, *a, **k)
            if os.path.basename(dst).startswith('.tmp-'):
                put(os.path.join(dest, 'someone-elses.txt'), 'theirs')
            return r
        with mock.patch.object(shutil, 'copytree', racing):
            with self.refused():
                self.pub('t1')
        self.assertEqual(os.listdir(self.folder), ['t1'])                  # .tmp-* прибрано
        self.assertEqual(os.listdir(dest), ['someone-elses.txt'])

    def test_the_marker_is_only_written_to_the_tmp_copy_after_the_content(self):
        """Маркер — ознака завершеної копії: поки копіюється, `.tmp-*` його не має (прибирання залишків його не зачепить)."""
        seen = []
        real = shutil.copytree

        def spy(src, dst, *a, **k):
            r = real(src, dst, *a, **k)
            if os.path.basename(dst).startswith('.tmp-'):              # copytree викликає себе й для підтек
                seen.append(os.path.exists(os.path.join(dst, MARKER)))
            return r
        with mock.patch.object(shutil, 'copytree', spy):
            self.pub('t1')
        self.assertEqual(seen, [False])

    # --------------------------------------------------------------------------- помилки й секрети
    def test_errors_keep_their_code_and_status_through_call_and_never_leak_the_secret(self):
        dm.write_secrets(self.sp['id'], MID, {'password': SECRET})
        self.assertEqual(self.ctx()['secrets'], {'password': SECRET})
        put(os.path.join(self.folder, 't1', 'a.txt'), 'a')                  # без маркера
        texts = []
        with self.refused('bad-folder', 409) as cx:
            self.pub('t1')
        texts += [cx.exception.message, str(cx.exception), repr(cx.exception)]
        self.assertTrue(cx.exception.message)
        self.assertLessEqual(len(cx.exception.message), 300)
        self.assertIsNone(cx.exception.__cause__)
        self.assertIsNone(cx.exception.__context__)
        self.set_folder(self.sp['path'])
        with self.refused('bad-folder', 409) as cx:
            self.pub('t1')
        texts += [cx.exception.message, str(cx.exception)]
        with self.refused('module-error', 502) as cx:
            self.pub('../x')
        texts += [cx.exception.message, str(cx.exception)]
        res = dm.check(self.sp, MID)
        texts += [json.dumps(res)]
        for t in texts:
            self.assertNotIn(SECRET, t)

    def test_a_secret_that_lands_in_a_message_is_scrubbed_by_the_core(self):
        """Підстраховка ядра, не модуля: навіть коли пароль збігається з частиною шляху, у відповіді його нема."""
        dm.write_secrets(self.sp['id'], MID, {'password': 'deai-published'})
        self.set_folder(os.path.join(self.sp['path']))
        with self.refused('bad-folder', 409) as cx:
            self.pub('t1')
        self.assertNotIn('deai-published', cx.exception.message)

    # -------------------------------------------------------------------------- ядро й диспетчер
    def test_publish_goes_through_the_cores_provider_and_call_with_the_real_ctx(self):
        prov = dm.provider('publish', self.sp)
        self.assertIs(prov, self.m)
        res = dm.call(prov, 'publish', dm.module_ctx(self.sp, prov), self.build, {'id': 't1', 'title': 'T', 'dir': 'd'})
        self.assertEqual(res['path'], os.path.join(self.folder, 't1'))
        self.assertTrue(self.is_marked('t1'))

    def test_the_folder_may_be_changed_in_the_space_settings(self):
        self.set_folder('~/elsewhere/{space_id}')
        res = self.pub('t1')
        self.assertEqual(res['path'], self.hp('elsewhere', self.sp['id'], 't1'))
        self.assertFalse(os.path.exists(self.folder))


# -------------------------------------------------------------------------------- вигляд модуля

class SourceShape(unittest.TestCase):
    #: Усе, що `server.py` може імпортувати (exec-иться ядром: без `serve`, ядра, сусідів, `importlib`).
    ALLOWED_IMPORTS = {'os', 're', 'secrets', 'shutil', 'stat'}

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

    def test_the_module_never_touches_the_secrets(self):
        """Пароль превʼю потрібен збірці (його вкладає ядро), а не публікації в теку: модуль його не читає, тож у
        його помилках його не може бути."""
        consts = {n.value for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        self.assertNotIn('secrets', consts)
        self.assertNotIn('secrets', names)
        self.assertNotIn('password', consts)

    def test_the_two_role_functions_exist(self):
        funcs = {n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'check', 'publish'} <= funcs)

    def test_the_marker_and_the_id_rule_are_the_documented_ones(self):
        ns = {}
        exec(compile(self.src, SERVER, 'exec', dont_inherit=True), ns)
        self.assertEqual(ns['MARKER'], MARKER)
        self.assertEqual(ns['ID_RE'].pattern, r'[\w-]+')
        self.assertTrue(ns['ID_RE'].flags & re.ASCII)


if __name__ == '__main__':
    unittest.main()

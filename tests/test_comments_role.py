"""Роль `comments` у ядрі (етап 2b-2, Task 1): постачальник, `comments_client`, канал, роздача адаптера, `DEAI_EXTRA_MODULES`.

Що доводиться (маніфест — `client` і `public` — у `test_modules.py`, класи `ManifestClientTest` і `ManifestPublicSecretTest`):
  * `provider('comments', space)` і `capabilities().comments`: явно ввімкнений модуль → він (в обох видах простору);
    простір з `integrations` без модуля → `'legacy'` (БЕЗ каталогу); інакше `None` (неявного типового нема);
  * `comments_client`: форма (плаский JSON-обʼєкт ≤ 4 КіБ зі str/int/float/bool/None), жодного значення НЕпублічного секрету
    (навіть короткого й у перекодованому вигляді) у значеннях, публічний секрет дозволений, текст відмови без значень;
  * `channel_for`: `deai/<простір>/<задача>[/internal]`;
  * `GET /api/module-client/<модуль>/<файл>`: рівно оголошені файли модулів ролі `comments`, зі `status == 'ok'`; ті самі
    захисні відкриття, що й `/published` (без посилань, дескриптором); усе інше — 404 зі сталим тілом;
  * `DEAI_EXTRA_MODULES`: друга тека вбудованих модулів (тестовий шов): справжній каталог вантажить фікстуру
    `memo-comments`, а `id` вбудованого модуля виграє.

Task 2 (сторінки канваса й «Огляд»): `LegacyPagesTest` — ЛІГА (`'legacy'`) і «нікого» (`None`) байт у байт як до 2b-2 (еталони
`tests/fixtures/comments-role/`, зняті з коду bc2d786 до правки); `ModulePagesTest` — `/commented?ch=project` і
`/api/comment-config?ch=project` для модуля: порядок скриптів, публічна конфігурація без непублічних секретів, екранування,
канал ядра, відмова модуля (локальний шар + видима примітка, ніколи не 5xx), центральна відповідь модулів.

⛔ Ізоляція: власні тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`. Розтяжка мережі:
сокет лише на 127.0.0.1 (підставний сервіс `memo` у процесі й власний сервер тесту).
"""
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, _HERE)                                   # пакета `tests` нема — охоронець і `test_modules` поруч
import deai_modules as dm  # noqa: E402
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules as tm  # noqa: E402  — `Env` (тимчасові HOME/DEAI_HOME, `mk`, `new_space`) і `COMMENTS_FNS`

FIXTURES = os.path.join(ROOT, 'tests', 'fixtures', 'modules')
MEMO = os.path.join(FIXTURES, 'memo-comments')
ADAPTER = os.path.join(MEMO, 'adapter.js')
NOT_FOUND = b'not found\n'                                  # тіло КОЖНОЇ відмови маршруту адаптера: ні причини, ні шляху
#: Вбудовані модулі справжнього `app/modules` за абеткою (каталог без `DEAI_EXTRA_MODULES`): новий вбудований модуль — тут і лише тут.
BUILTIN_IDS = ['css-tokens', 'git-sync', 'static-publish', 'supabase-comments', 'supabase-dashboard', 'vercel-publish']
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _fn(name, body):
    return f'def {name}:\n    {body}\n'


LIST_RESOLVE = ('def list(ctx, channel):\n    return []\n'
                'def resolve(ctx, channel, id, reason):\n    return None\n')
#: Налаштування модулів-фікстур: непублічний `token`, публічний `pubkey`, звичайне `note`.
CFG_SETTINGS = [{'key': 'token', 'type': 'secret', 'label': 'Token'},
                {'key': 'pubkey', 'type': 'secret', 'public': True, 'label': 'Public key'},
                {'key': 'note', 'type': 'text', 'label': 'Note'}]


def cfg_server(body):
    """`server.py` модуля ролі `comments`, чий `client_config` повертає `eval`-вираз `body` (бачить `ctx`)."""
    return 'import urllib.parse as up\n' + tm.CHECK_ONLY + _fn('client_config(ctx)', f'return {body}') + LIST_RESOLVE


class CommentsEnv(tm.Env):
    """`tm.Env` + помічники ролі `comments`."""

    def mkcm(self, mid='cm', server=None, settings=None, client=('adapter.js',), files=None, roles=('comments',),
             patch=None):
        """Модуль ролі `comments` у `self.mods`; `files` — `{імʼя: вміст}` (типово — кожен із `client`)."""
        p = {'client': list(client), **(patch or {})}
        d = self.mk(mid, roles=roles, settings=settings, server=tm.COMMENTS_FNS if server is None else server, patch=p)
        for name in (client if files is None else files):
            _write(os.path.join(d, name), tm.CLIENT_JS if files is None else files[name])
        return d

    def install_memo(self):
        """Фікстура `memo-comments` у `self.mods`; другий виклик нічого не робить (а не `FileExistsError`)."""
        dest = os.path.join(self.mods, 'memo-comments')
        if not os.path.isdir(dest):
            shutil.copytree(MEMO, dest, ignore=shutil.ignore_patterns('__pycache__'))

    def enable_memo(self, sp, endpoint='http://127.0.0.1:9', secrets=None):
        self.install_memo()
        dm.write_module_state(sp, 'memo-comments', enabled=True, settings={'endpoint': endpoint})
        if secrets is not None:
            dm.write_secrets(sp['id'], 'memo-comments', secrets)
        return dm.provider('comments', sp)


# ------------------------------------------------------------------------------------------ постачальник

class ProviderTest(CommentsEnv):
    def test_a_plain_space_without_a_module_has_no_provider(self):
        sp = self.new_space()
        self.assertIsNone(dm.provider('comments', sp))
        self.assertIsNone(dm.capabilities(sp)['comments'])

    def test_an_integrations_space_without_a_module_is_legacy_and_never_reads_the_catalog(self):
        self.mkcm()
        ig = self.new_space(integrations=True)
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог не потрібен')):
            self.assertEqual(dm.provider('comments', ig), 'legacy')
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy'})
        dm.write_module_state(ig, 'cm', enabled=False)               # явне «вимкнено» — теж не модуль
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог не потрібен')):
            self.assertEqual(dm.provider('comments', ig), 'legacy')

    def test_an_enabled_module_is_the_provider_in_both_kinds_of_space(self):
        self.mkcm()
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        for sp in (plain, ig):
            dm.write_module_state(sp, 'cm', enabled=True)
            prov = dm.provider('comments', sp)
            self.assertIsInstance(prov, dm.Module)
            self.assertEqual(prov.id, 'cm')
            self.assertEqual(dm.capabilities(sp)['comments'], 'cm')
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'cm', 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy'})   # publish — як було
        dm.write_module_state(ig, 'cm', enabled=False)               # вимкнули — назад до зашитого шляху
        dm.write_module_state(plain, 'cm', enabled=False)
        self.assertEqual(dm.provider('comments', ig), 'legacy')
        self.assertIsNone(dm.provider('comments', plain))

    def test_a_module_that_is_present_but_not_enabled_is_not_a_provider_and_there_is_no_implicit_default(self):
        self.mk('static-publish')                                    # неявний типовий є лише в `publish`
        self.mkcm()
        plain = self.new_space()
        self.assertEqual(dm.provider('publish', plain).id, 'static-publish')
        self.assertIsNone(dm.provider('comments', plain))
        self.assertEqual(dm.capabilities(plain), {'publish': 'static-publish', 'tokens': None, 'comments': None, 'vcs': None, 'dashboard': None, 'tracker': None})

    def test_a_broken_space_json_is_total_for_capabilities_and_409_for_provider(self):
        self.mkcm()
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        for sp in (plain, ig):
            _write(self.space_json(sp), '{broken')
        for sp in (plain, ig):               # і без інтеграцій, і з ними: невідомо, що людина вмикала — 409, а не 'legacy'
            with self.assertRaises(dm.ModuleError) as cm:
                dm.provider('comments', sp)
            self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409))
        self.assertEqual(dm.capabilities(plain),
                         {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'dashboard': None, 'tracker': None, 'error': 'space-json-unreadable'})
        self.assertEqual(dm.provider('publish', ig), 'legacy')       # шлях ЛІГА для публікації пошкодженим файлом не ламається
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy', 'dashboard': None, 'tracker': None,
                                               'error': 'space-json-unreadable'})

    def test_capabilities_names_exactly_the_called_roles(self):
        sp = self.new_space()
        self.assertEqual(set(dm.capabilities(sp)), {'publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker'})
        self.assertEqual(set(dm.capabilities(None)), {'publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker'})
        self.assertEqual(set(dm.capabilities({})), {'publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker'})

    def test_one_provider_per_space(self):
        self.mkcm('cm-a')
        self.mkcm('cm-b')
        sp = self.new_space()
        dm.write_module_state(sp, 'cm-a', enabled=True)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'cm-b', enabled=True)
        self.assertEqual(cm.exception.code, 'role-taken')
        self.assertIn('comments', cm.exception.message)
        other = self.new_space('Other')
        dm.write_module_state(other, 'cm-b', enabled=True)           # в іншому просторі — можна
        self.assertEqual(dm.provider('comments', other).id, 'cm-b')
        self.assertEqual(dm.provider('comments', sp).id, 'cm-a')

    def test_a_broken_enabled_comments_module_is_an_error_in_a_plain_space_too_never_silence(self):
        """Без інтеграцій запасного шляху нема, але тиша — «коментарів немає» без причини — теж брехня: явно ввімкнений і
        загублений модуль коментарів дає `module-error` (як у просторі ЛІГА), а `capabilities` несе `error`."""
        self.mkcm('cm-bad', client=('a.js',), files={})              # оголошений файл не лежить на диску
        self.assertEqual(dm.catalog()['cm-bad'].status, 'error')
        plain = self.new_space('Plain')
        _write(self.space_json(plain), json.dumps({'modules': {'cm-bad': {'enabled': True}}}))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('comments', plain)
        self.assertEqual((cm.exception.code, cm.exception.status, cm.exception.message),
                         ('module-error', 502, dm.COMMENTS_MODULE_BROKEN))
        self.assertEqual(dm.capabilities(plain), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'dashboard': None, 'tracker': None,
                                                  'error': 'module-error'})

    def test_a_plain_space_without_any_comments_entry_stays_none_without_an_error(self):
        """Тиша лишається тишею там, де людина про коментарі нічого не вирішувала: порожній `space.json`, лише вимкнений
        запис, модуль іншої ролі (справний чи зламаний із відомою роллю), застарілий запис невідомого модуля."""
        self.mk('pub-ok')
        self.mk('pub-syntax', server='def check(:\n')
        self.mkcm()
        plain = self.new_space('Plain')
        for body in ({}, {'modules': {'cm': {'enabled': False}}}, {'modules': {'pub-ok': {'enabled': True}}},
                     {'modules': {'pub-syntax': {'enabled': True}}}, {'modules': {'ghost': {'enabled': True}}}):
            with self.subTest(body=body):
                _write(self.space_json(plain), json.dumps(body))
                self.assertIsNone(dm.provider('comments', plain))
                self.assertEqual(dm.capabilities(plain)['comments'], None)
                self.assertNotIn('error', dm.capabilities(plain))

    def enabled_entry(self, sp, *ids):
        _write(self.space_json(sp), json.dumps({'modules': {mid: {'enabled': True} for mid in ids}}))

    def test_an_enabled_comments_module_that_is_lost_is_an_error_never_the_shared_league_service(self):
        """Простір з інтеграціями + ЯВНО ввімкнений модуль коментарів, що не завантажився: `'legacy'` повів би піни (зі
        знімками приватних макетів) у СПІЛЬНИЙ Supabase ЛІГА — тому `module-error`, а `capabilities.comments` — `None`."""
        self.mkcm('cm-files', client=('a.js',), files={})            # (1) маніфест не пройшов: нема оголошеного файла
        self.mkcm('cm-syntax', server='def check(:\n')              # (2) `server.py` не компілюється (роль відома)
        self.mkcm('cm-json')                                         # (3) `module.json` не розібрати (ролі невідомі)
        _write(os.path.join(self.mods, 'cm-json', 'module.json'), '{broken')
        for mid in ('cm-files', 'cm-syntax', 'cm-json', 'supabase-comments'):    # (4) вбудованого модуля коментарів нема в каталозі
            with self.subTest(module=mid):
                ig = self.new_space(f'Ig{mid.replace("-", "")}', integrations=True)
                self.enabled_entry(ig, mid)
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.provider('comments', ig)
                self.assertEqual((cm.exception.code, cm.exception.status, cm.exception.message),
                                 ('module-error', 502, dm.COMMENTS_MODULE_BROKEN))
                self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy',
                                                       'error': 'module-error'})
        self.assertEqual(dm.catalog()['cm-files'].status, 'error')
        self.assertEqual(dm.catalog()['cm-syntax'].status, 'error')
        self.assertEqual(dm.catalog()['cm-json'].status, 'error')

    def test_an_unrelated_stale_entry_does_not_take_the_league_comments_away(self):
        """Запис, якого нема в каталозі й про який не відомо, що він вів коментарі (модуль прибрали, теку джерел більше не
        названо), — пил у `space.json`: ЛІГА лишається на своєму шляху, без помилки."""
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'ghost', 'memo-comments')            # обидва — відсутні в каталозі цього тесту
        self.assertEqual(dm.provider('comments', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy'})

    def test_a_broken_manifest_of_an_unknown_id_is_lost_but_of_a_known_other_builtin_is_not(self):
        """Маніфест не розібрано — ролі невідомі: невідомий id вважаємо тим, що міг вести коментарі; а вбудований модуль
        ІНШОЇ ролі (`KNOWN_OTHER_MODULES`) коментарів не вів ніколи — його поломка шлях не блокує."""
        for mid in ('static-publish', 'css-tokens', 'vercel-publish'):
            self.mk(mid)
            _write(os.path.join(self.mods, mid, 'module.json'), '{broken')
        self.mk('stranger')
        _write(os.path.join(self.mods, 'stranger', 'module.json'), '{broken')
        self.assertTrue(all(dm.catalog()[m].status == 'error' and not dm.catalog()[m].roles
                            for m in ('static-publish', 'css-tokens', 'vercel-publish', 'stranger')))
        for kind, integrations in (('league', True), ('plain', False)):
            for mid in ('static-publish', 'css-tokens', 'vercel-publish'):
                with self.subTest(kind=kind, module=mid):
                    sp = self.new_space(f'{kind}{mid.replace("-", "")}', integrations=integrations)
                    self.enabled_entry(sp, mid)
                    want = 'legacy' if integrations else None
                    self.assertEqual(dm.provider('comments', sp), want)
                    self.assertNotIn('error', dm.capabilities(sp))
            with self.subTest(kind=kind, module='stranger'):
                sp = self.new_space(f'{kind}stranger', integrations=integrations)
                self.enabled_entry(sp, 'stranger')
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.provider('comments', sp)
                self.assertEqual(cm.exception.code, 'module-error')
                self.assertEqual(dm.capabilities(sp)['error'], 'module-error')

    def test_a_missing_builtin_comments_module_is_lost_in_both_kinds_of_space(self):
        for kind, integrations in (('league', True), ('plain', False)):
            with self.subTest(kind=kind):
                sp = self.new_space(f'{kind}missing', integrations=integrations)
                self.enabled_entry(sp, 'supabase-comments')          # у каталозі цього тесту його нема
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.provider('comments', sp)
                self.assertEqual(cm.exception.message, dm.COMMENTS_MODULE_BROKEN)

    def test_the_lost_entry_rule_is_a_pure_function_of_the_catalog_and_the_entries(self):
        ok = dm.Module('ok-m', roles=['publish'])
        broken_cm = dm.Module('b-cm', roles=['comments'], status='error', error='x', error_code='module-error')
        broken_pub = dm.Module('b-pub', roles=['publish'], status='error', error='x', error_code='module-error')
        broken_unknown = dm.Module('b-unk', roles=[], status='error', error='x', error_code='bad-manifest')
        broken_css = dm.Module('css-tokens', roles=[], status='error', error='x', error_code='bad-manifest')
        cat = {m.id: m for m in (ok, broken_cm, broken_pub, broken_unknown, broken_css)}
        lost = dm._enabled_module_is_lost
        on, off = {'enabled': True, 'settings': {}}, {'enabled': False, 'settings': {}}
        self.assertFalse(lost(cat, {}))
        self.assertTrue(lost(cat, {'b-cm': on}))
        self.assertTrue(lost(cat, {'b-unk': on}))
        self.assertTrue(lost(cat, {'supabase-comments': on}))
        for quiet in ({'b-cm': off}, {'ok-m': on}, {'b-pub': on}, {'css-tokens': on}, {'ghost': on}, {'b-unk': off},
                      {'supabase-comments': off}):
            self.assertFalse(lost(cat, quiet), quiet)
        self.assertTrue(lost(cat, {'ghost': on, 'b-cm': on}))        # одна справжня втрата серед пилу — втрата

    def test_publish_of_that_space_stays_the_league_path(self):
        self.mkcm('cm-files', client=('a.js',), files={})
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'cm-files')
        self.assertEqual(dm.provider('publish', ig), 'legacy')

    def test_the_league_path_returns_once_the_lost_entry_is_gone_or_disabled(self):
        self.mkcm('cm-files', client=('a.js',), files={})
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'cm-files')
        with self.assertRaises(dm.ModuleError):
            dm.provider('comments', ig)
        _write(self.space_json(ig), json.dumps({'modules': {'cm-files': {'enabled': False}}}))     # вимкнув
        self.assertEqual(dm.provider('comments', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy'})
        self.enabled_entry(ig, 'cm-files')
        _write(self.space_json(ig), json.dumps({'name': 'x'}))                                     # прибрав запис
        self.assertEqual(dm.provider('comments', ig), 'legacy')

    def test_a_lost_module_of_another_role_or_a_healthy_one_does_not_block_the_league_path(self):
        """Блокує лише те, що могло вести коментарі: модуль із розібраним маніфестом БЕЗ ролі `comments` (справний чи
        зламаний `server.py`) шлях ЛІГА не чіпає."""
        self.mk('pub-ok')                                            # справний publish
        self.mk('pub-syntax', server='def check(:\n')               # зламаний publish, але роль відома
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'pub-ok', 'pub-syntax')
        self.assertEqual(dm.catalog()['pub-syntax'].status, 'error')
        self.assertEqual(dm.catalog()['pub-syntax'].roles, ['publish'])
        self.assertEqual(dm.provider('comments', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig)['comments'], 'legacy')
        self.assertNotIn('error', dm.capabilities(ig))

    def test_a_working_comments_module_wins_over_an_unrelated_lost_entry(self):
        self.mkcm()
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'cm', 'supabase-comments')           # справжня втрата: вбудованого модуля нема в каталозі
        self.assertEqual(dm.provider('comments', ig).id, 'cm')
        self.assertEqual(dm.capabilities(ig)['comments'], 'cm')

    def test_the_decision_follows_the_files_without_a_cache_reset(self):
        d = self.mkcm()
        ig = self.new_space('Integ', integrations=True)
        self.enabled_entry(ig, 'cm')
        self.assertEqual(dm.capabilities(ig)['comments'], 'cm')
        os.remove(os.path.join(d, 'adapter.js'))                     # модуль зламався → не 'legacy', а помилка
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy',
                                               'error': 'module-error'})
        _write(os.path.join(d, 'adapter.js'), tm.CLIENT_JS)
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'cm', 'vcs': 'legacy', 'dashboard': 'legacy', 'tracker': 'legacy'})

    def test_the_capabilities_cache_follows_enabling_and_the_adapter_files(self):
        d = self.mkcm()
        sp = self.new_space()
        self.assertIsNone(dm.capabilities(sp)['comments'])
        dm.write_module_state(sp, 'cm', enabled=True)
        self.assertEqual(dm.capabilities(sp)['comments'], 'cm')
        os.remove(os.path.join(d, 'adapter.js'))
        self.assertIsNone(dm.capabilities(sp)['comments'])           # модуль зламався — постачальником не є
        _write(os.path.join(d, 'adapter.js'), tm.CLIENT_JS)
        self.assertEqual(dm.capabilities(sp)['comments'], 'cm')


# --------------------------------------------------------------------------------------- comments_client

class CommentsClientTest(CommentsEnv):
    TOKEN, PUB = 'tok-SECRET-1', 'pub-OPEN-2'

    def setUp(self):
        super().setUp()
        self.n = 0

    def run_cfg(self, body, secrets=None, note=None, raw=None):
        """Новий модуль (власний простір) з `client_config`, що повертає `body`; `comments_client` над ним. `raw` —
        значення, дописані в `secrets.json` ВРУЧНУ (ключів, яких нема в маніфесті, `write_secrets` не прийме)."""
        self.n += 1
        mid = f'cfg-{self.n}'
        self.mkcm(mid, server=cfg_server(body), settings=CFG_SETTINGS)
        sp = self.new_space(f'Space{self.n}')
        dm.write_module_state(sp, mid, enabled=True, settings={'note': note} if note else None)
        dm.write_secrets(sp['id'], mid, secrets if secrets is not None else {'token': self.TOKEN, 'pubkey': self.PUB})
        if raw:
            data = tm._read(self.secrets_file)
            data[sp['id']][mid].update(raw)
            tm._write(self.secrets_file, data)
        return dm.comments_client(sp, dm.provider('comments', sp))

    def refused(self, body, secrets=None, code='module-error'):
        with self.assertRaises(dm.ModuleError) as cm:
            self.run_cfg(body, secrets)
        self.assertEqual(cm.exception.code, code, body)
        return cm.exception

    def test_the_shape_of_the_memo_fixture(self):
        sp = self.new_space()
        prov = self.enable_memo(sp, 'http://127.0.0.1:4321', {'token': 'tok-x', 'pubkey': 'pk-live'})
        cfg = dm.comments_client(sp, prov)
        self.assertEqual(cfg, {'endpoint': 'http://127.0.0.1:4321', 'pubkey': 'pk-live'})
        self.assertIs(type(cfg), dict)
        cfg['endpoint'] = 'x'                                        # копія: правка не псує наступний виклик
        self.assertEqual(dm.comments_client(sp, prov)['endpoint'], 'http://127.0.0.1:4321')

    def test_an_unset_public_key_is_an_empty_string_and_a_missing_endpoint_is_bad_settings(self):
        sp = self.new_space()
        prov = self.enable_memo(sp, 'http://127.0.0.1:4321')
        self.assertEqual(dm.comments_client(sp, prov), {'endpoint': 'http://127.0.0.1:4321', 'pubkey': ''})
        other = self.new_space('Other')
        dm.write_module_state(other, 'memo-comments', enabled=True)          # без `endpoint`
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(other, dm.provider('comments', other))
        self.assertEqual(cm.exception.code, 'bad-settings')

    def test_the_provider_must_be_a_comments_module(self):
        self.mk('pub')
        sp = self.new_space()
        for prov in ('legacy', None, 'cm', dm.catalog()['pub'], object()):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.comments_client(sp, prov)
            self.assertEqual(cm.exception.code, 'module-error', repr(prov))

    def test_only_plain_flat_json_objects_pass(self):
        for body in ('[]', '"str"', 'None', '5', 'True', '{"a": {"b": 1}}', '{"a": [1]}', '{"a": (1,)}',
                     '{"a": b"x"}', '{"a": {1, 2}}', '{1: "a"}', '{"a": float("nan")}', '{"a": float("inf")}',
                     '{"a": object()}', '{None: "a"}'):
            self.refused(body)
        ok = self.run_cfg('{"s": "x", "i": 1, "f": 1.5, "b": True, "n": None, "e": ""}')
        self.assertEqual(ok, {'s': 'x', 'i': 1, 'f': 1.5, 'b': True, 'n': None, 'e': ''})
        self.assertEqual(self.run_cfg('{}'), {})

    def test_the_config_is_capped_at_4096_bytes_of_json(self):
        self.assertEqual(len(json.dumps({'k': 'x' * 4087})), 4096)
        self.assertEqual(len(self.run_cfg('{"k": "x" * 4087}')['k']), 4087)         # рівно 4096 — ще можна
        self.refused('{"k": "x" * 4088}')                                           # 4097 — вже ні
        self.refused('{"k": "x" * 100000}')
        self.refused('{"k%d" % i: "x" * 200 for i in range(30)}')                   # межа — на ВЕСЬ обʼєкт

    def test_a_private_secret_in_a_value_is_refused_even_short_embedded_or_reencoded(self):
        t = self.TOKEN
        cases = [
            ('{"x": ctx["secrets"]["token"]}', None),
            (f'{{"x": "https://h/?k=" + ctx["secrets"]["token"] + "&z=1"}}', None),
            ('{"ok": "fine", "x": "a-" + ctx["secrets"]["token"]}', None),
            ('{"x": "abcQdef"}', {'token': 'Q', 'pubkey': self.PUB}),                  # навіть один символ
            ('{"port": 8080}', {'token': '8080'}),                                     # число, що збіглося
            ('{"v": 1.5}', {'token': '1.5'}),
            ('{"x": "a%20b%26c"}', {'token': 'a b&c'}),                                # URL-кодування
            ('{"x": "a\\\\\\"b"}', {'token': 'a"b'}),                                  # екранування JSON
            ('{"x": "xпароль-ключx"}', {'token': 'пароль-ключ'}),                       # не-ASCII як є
        ]
        errors = []
        for body, secrets in cases:
            errors.append(self.refused(body, secrets))
        with self.assertRaises(dm.ModuleError) as cm:              # ключа нема в маніфесті (файл правили вручну): теж непублічний
            self.run_cfg('{"x": "xx-stray-yy"}', {'token': t}, raw={'stray': '-stray-'})
        errors.append(cm.exception)
        # відмова одна й та сама — без значень (ні секрету, ні конфігу), без імен із конфігу
        self.assertEqual({e.message for e in errors}, {errors[0].message})
        self.assertEqual({e.status for e in errors}, {502})
        for e in errors:
            for leaked in (t, self.PUB, 'Q', 'stray', 'https://h', 'пароль', 'a%20b'):
                self.assertNotIn(leaked, str(e) + e.message)

    def test_keys_are_scanned_too(self):
        for body in ('{"k-" + ctx["secrets"]["token"]: 1}', '{ctx["secrets"]["token"]: "v"}',
                     '{"x " + ctx["secrets"]["token"] + "/y": 1}', '{up.quote(ctx["secrets"]["token"]): 1}'):
            e = self.refused(body)
            self.assertEqual(e.message, dm.CLIENT_CONFIG_LEAK, body)
        self.assertEqual(self.run_cfg('{"k-ok": 1}'), {'k-ok': 1})

    def test_percent_encoded_forms_are_found_by_decoding_the_text(self):
        """`quote` (з `/` у safe), `quote_plus` і `urlencode` дають різні вигляди секрету з `+ / = пробіл` (типові для base64):
        охоронець розкодовує кожен текст (`unquote`, `unquote_plus`) і шукає сирі форми."""
        b64 = 'ab+c/d=e=='
        for body, token in (
                ('{"u": up.quote(ctx["secrets"]["token"])}', b64),
                ('{"u": up.quote_plus(ctx["secrets"]["token"])}', b64),
                ('{"u": "https://h/?" + up.urlencode({"k": ctx["secrets"]["token"]})}', b64),
                ('{"u": up.quote_plus(ctx["secrets"]["token"])}', 'a b c'),          # пробіл → `+`
                ('{"u": up.quote(ctx["secrets"]["token"])}', 'a b c'),               # пробіл → `%20`
                ('{up.quote_plus(ctx["secrets"]["token"]): 1}', b64),                # у ключі теж
        ):
            with self.subTest(body=body, token=token):
                e = self.refused(body, {'token': token})
                self.assertEqual(e.message, dm.CLIENT_CONFIG_LEAK)
        self.assertEqual(self.run_cfg('{"u": up.quote_plus("zzz+/=")}', {'token': 'a b c'}), {'u': 'zzz%2B%2F%3D'})

    def test_lone_surrogates_are_refused_in_keys_and_values(self):
        """Рядок, що не кодується в UTF-8, пройшов би перевірку, а потім обривав відповідь сторінки: відмова тут."""
        for body in ('{"x": "\\ud800"}', '{"x": "a\\udfffb"}', '{"\\ud800": 1}', '{"k": "ok", "x\\udc00y": "v"}',
                     '{"x": chr(0xD800)}', '{"x": "tail" + chr(0xDBFF)}'):
            e = self.refused(body)
            self.assertIn('valid text', e.message, body)
        self.assertEqual(self.run_cfg('{"x": "\\U0001F600 ї \\u2028", "ключ": "значення"}'),
                         {'x': '\U0001F600 ї \u2028', 'ключ': 'значення'})              # справжній Unicode — можна

    def test_any_value_error_overflow_or_unicode_error_inside_the_check_is_the_refusal(self):
        for boom in (ValueError('v'), OverflowError('o'), UnicodeEncodeError('utf-8', 'x', 0, 1, 'u'),
                     UnicodeDecodeError('utf-8', b'x', 0, 1, 'd')):
            with self.subTest(boom=type(boom).__name__):
                with mock.patch.object(dm, '_text_views', side_effect=boom):
                    e = self.refused('{"x": "anything"}')
                self.assertEqual(type(e), dm.ModuleError)
                self.assertIn('serializable', e.message)
                self.assertNotIn(self.TOKEN, str(e))
        with mock.patch.object(dm, '_secret_forms', side_effect=OverflowError('o')):
            self.refused('{"x": 1}')

    def test_a_giant_int_is_a_refusal_not_a_raw_value_error(self):
        for body in ('{"n": 10 ** 5000}', '{"n": -10 ** 5000}', '{"n": 10 ** 4400, "s": "x"}'):
            e = self.refused(body)
            self.assertEqual(type(e), dm.ModuleError)
            self.assertEqual(e.code, 'module-error')
            # Причина залежить від версії Python: де є ліміт цифр у `int` (3.11+, 3.9.14+), `json.dumps` кидає
            # `ValueError` («is not serializable»); де його нема (3.9.6), число серіалізується й упирається в `MAX_CLIENT_CONFIG`.
            # Обидві відмови — `ModuleError('module-error')` із ФІКСОВАНИМ текстом без значення.
            self.assertTrue(e.message.endswith(('is not serializable', f'bigger than {dm.MAX_CLIENT_CONFIG} bytes')),
                            e.message)
        self.assertEqual(self.run_cfg('{"n": 10 ** 18}'), {'n': 10 ** 18})

    def test_what_is_validated_is_what_is_returned(self):
        """Копія СПЕРШУ, перевірка копії: підклас `dict`, що показує чистий вигляд методам `items`/`values`/`keys`, а в
        сховищі тримає витік, не проходить (інакше перевірявся б «вигляд», а віддавалося б `dict(cfg)` зі сховища: CPython
        копіює такий підклас зі сховища, поки не перевизначено `__iter__`)."""
        liar = ('class Liar(dict):\n'
                '    def items(self): return iter([("x", "clean")])\n'
                '    def values(self): return iter(["clean"])\n'
                '    def keys(self): return iter(["x"])\n'
                '    def __getitem__(self, k): return "clean"\n'
                '    def get(self, k, d=None): return "clean"\n')
        self.n += 1
        mid = f'liar-{self.n}'
        self.mkcm(mid, server=tm.CHECK_ONLY + liar + _fn('client_config(ctx)', 'return Liar({"x": ctx["secrets"]["token"]})')
                  + LIST_RESOLVE, settings=CFG_SETTINGS)
        sp = self.new_space('Liar')
        dm.write_module_state(sp, mid, enabled=True)
        dm.write_secrets(sp['id'], mid, {'token': self.TOKEN})
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(sp, dm.provider('comments', sp))
        self.assertEqual((cm.exception.code, cm.exception.message), ('module-error', dm.CLIENT_CONFIG_LEAK))
        # підклас, що кидає при копіюванні, — теж відмова, а не сирий виняток
        boom = ('class Boom(dict):\n'
                '    def __iter__(self): raise RuntimeError("boom")\n'
                '    def keys(self): raise RuntimeError("boom")\n')
        self.n += 1
        mid = f'boom-{self.n}'
        self.mkcm(mid, server=tm.CHECK_ONLY + boom + _fn('client_config(ctx)', 'return Boom({"x": 1})') + LIST_RESOLVE,
                  settings=CFG_SETTINGS)
        sp2 = self.new_space('Boom')
        dm.write_module_state(sp2, mid, enabled=True)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(sp2, dm.provider('comments', sp2))
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn('boom', cm.exception.message)

    def test_the_result_is_a_plain_dict_detached_from_the_module(self):
        self.n += 1
        mid = f'keep-{self.n}'
        server = (tm.CHECK_ONLY + 'CFG = {"x": "one"}\n' + _fn('client_config(ctx)', 'return CFG') + LIST_RESOLVE)
        self.mkcm(mid, server=server, settings=CFG_SETTINGS)
        sp = self.new_space('Keep')
        dm.write_module_state(sp, mid, enabled=True)
        prov = dm.provider('comments', sp)
        got = dm.comments_client(sp, prov)
        self.assertIs(type(got), dict)
        prov.fn('client_config').__globals__['CFG']['x'] = 'two'                 # модуль змінює свій словник уже після
        self.assertEqual(got, {'x': 'one'})

    def test_a_public_secret_may_appear_and_so_may_an_empty_or_absent_private_one(self):
        self.assertEqual(self.run_cfg('{"pk": ctx["secrets"]["pubkey"], "u": "https://h/?pk=" + ctx["secrets"]["pubkey"]}'),
                         {'pk': self.PUB, 'u': f'https://h/?pk={self.PUB}'})
        self.assertEqual(self.run_cfg('{"x": "anything"}', {'token': ''}), {'x': 'anything'})     # порожній — нема що ховати
        self.assertEqual(self.run_cfg('{"x": "anything"}', {}), {'x': 'anything'})                # секретів нема взагалі
        self.assertEqual(self.run_cfg('{"x": "no-q-here"}', {'token': 'Q'}), {'x': 'no-q-here'})  # не збіглося — можна
        self.assertEqual(self.run_cfg('{"n": ctx["settings"].get("note")}', note='the token is elsewhere'),
                         {'n': 'the token is elsewhere'})              # звичайне налаштування — не секрет

    def test_a_secret_of_another_module_or_space_does_not_count(self):
        self.mkcm('cfg-a', server=cfg_server('{"x": "mine-secret-other"}'), settings=CFG_SETTINGS)
        a = self.new_space('A')
        b = self.new_space('B')
        dm.write_module_state(a, 'cfg-a', enabled=True)
        dm.write_secrets(b['id'], 'cfg-a', {'token': 'mine-secret-other'})
        self.assertEqual(dm.comments_client(a, dm.provider('comments', a)), {'x': 'mine-secret-other'})

    def test_an_exception_of_the_module_is_scrubbed_like_any_call(self):
        with self.assertRaises(dm.ModuleError) as cm:
            self.run_cfg('(_ for _ in ()).throw(RuntimeError("bad " + ctx["secrets"]["token"]))')
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn(self.TOKEN, str(cm.exception))
        self.assertIn('***', cm.exception.message)

    def test_a_module_that_does_not_answer_is_check_timeout(self):
        self.n += 1
        self.mkcm('slow', server=tm.CHECK_ONLY + 'import time\ndef client_config(ctx):\n    time.sleep(3)\n    return {}\n'
                  + LIST_RESOLVE)
        sp = self.new_space()
        dm.write_module_state(sp, 'slow', enabled=True)
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.comments_client(sp, dm.provider('comments', sp))
        self.assertEqual((cm.exception.code, cm.exception.status), ('check-timeout', 504))

    def test_unreadable_secrets_are_not_an_empty_config(self):
        sp = self.new_space()
        prov = self.enable_memo(sp, 'http://127.0.0.1:4321')
        _write(self.secrets_file, '{broken')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(sp, prov)
        self.assertEqual(cm.exception.code, 'secrets-unreadable')


# --------------------------------------------------------------------------------------------- канал

class ChannelTest(unittest.TestCase):
    def test_the_channel_of_a_task_and_its_internal_one(self):
        sp = {'id': 'liga', 'path': '/x', 'integrations': True}
        self.assertEqual(dm.channel_for(sp, 't-1'), 'deai/liga/t-1')
        self.assertEqual(dm.channel_for(sp, 't-1', internal=True), 'deai/liga/t-1/internal')
        self.assertEqual(dm.channel_for(sp, 't-1', False), 'deai/liga/t-1')
        self.assertEqual(dm.channel_for({'id': 'a'}, 'ABC-1'), 'deai/a/ABC-1')

    def test_the_same_task_in_two_spaces_never_shares_a_channel(self):
        self.assertNotEqual(dm.channel_for({'id': 'a'}, 't'), dm.channel_for({'id': 'b'}, 't'))
        self.assertNotEqual(dm.channel_for({'id': 'a'}, 't'), dm.channel_for({'id': 'a'}, 't', internal=True))

    def test_an_empty_space_or_task_is_refused(self):
        for sp, tid in (({'id': ''}, 't'), ({}, 't'), (None, 't'), ({'id': 'a'}, ''), ({'id': 'a'}, None)):
            with self.assertRaises(dm.ModuleError, msg=repr((sp, tid))) as cm:
                dm.channel_for(sp, tid)
            self.assertEqual(cm.exception.code, 'module-error')

    def test_a_space_id_must_be_a_valid_space_id(self):
        """`SPACE_ID_RE` (`[a-z0-9][a-z0-9-]{0,39}`): `a/b` у id простору ламав би розбір каналу на складові."""
        for bad in ('a/b', 'A', 'a b', '-a', 'a_b', 'a.b', 'a' * 41, 'a\n', 'ї', '..', '/'):
            with self.assertRaises(dm.ModuleError, msg=repr(bad)):
                dm.channel_for({'id': bad}, 't')
        self.assertEqual(dm.channel_for({'id': 'a' * 40}, 't'), 'deai/' + 'a' * 40 + '/t')
        self.assertEqual(dm.channel_for({'id': 'legacy'}, 't'), 'deai/legacy/t')            # id неявного простору

    def test_a_task_id_has_no_slash_or_control_characters(self):
        for bad in ('b/t', '/t', 't/', 'a/b/c', 't\n', 't\0', 't\x1f', 't\x7f', '\t'):
            with self.assertRaises(dm.ModuleError, msg=repr(bad)) as cm:
                dm.channel_for({'id': 'a'}, bad)
            self.assertEqual(cm.exception.code, 'module-error')
        for ok in ('t', 'ABC-1', 't_1.x', 'ї-задача', 't 1', 'internal'):
            self.assertEqual(dm.channel_for({'id': 'a'}, ok), f'deai/a/{ok}')

    def test_no_two_pairs_make_the_same_channel(self):
        """`a` + `b/t` і `a/b` + `t` давали б один канал `deai/a/b/t` — тепер обидві пари відмовлено."""
        for sp, tid in (({'id': 'a'}, 'b/t'), ({'id': 'a/b'}, 't')):
            with self.assertRaises(dm.ModuleError):
                dm.channel_for(sp, tid)


# ------------------------------------------------------------------------------- підставний сервіс `memo`

class MemoService:
    """Мінімальний сервіс коментарів для `memo-comments` на 127.0.0.1: пам'ять + журнал запитів."""

    def __init__(self):
        self.comments = {}            # канал → список
        self.log = []                 # (метод, шлях, заголовок Authorization, тіло)
        self.redirect = None          # адреса, на яку сервіс відповідає 302 (перевірка «переадресації не виконуються»)
        svc = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _chan(self):
                from urllib.parse import unquote
                parts = self.path.split('/')                          # ['', 'c', '<канал>', ...]
                return unquote(parts[2]), '/'.join(parts[3:])

            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _redirected(self):
                if not svc.redirect:
                    return False
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
                self.send_response(302)
                self.send_header('Location', svc.redirect + self.path)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return True

            def do_GET(self):
                svc.log.append(('GET', self.path, self.headers.get('Authorization'), None))
                if self._redirected():
                    return
                chan, _ = self._chan()
                self._send(svc.comments.get(chan, []))

            def do_POST(self):
                if svc.redirect:
                    svc.log.append(('POST', self.path, self.headers.get('Authorization'), None))
                    self._redirected()
                    return
                raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                svc.log.append(('POST', self.path, self.headers.get('Authorization'), json.loads(raw or b'null')))
                chan, tail = self._chan()
                data = json.loads(raw or b'{}')
                rows = svc.comments.setdefault(chan, [])
                if tail == 'resolve':
                    for c in rows:
                        if c['id'] == data['id']:
                            c.update(status='resolved', resolveReason=data['reason'])
                self._send({'ok': True})
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f'http://127.0.0.1:{self.port}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def loopback_only(case):
    """Розтяжка: `socket.create_connection` лише до 127.0.0.1 (будь-який порт); решта — запис і `OSError`."""
    hits = []
    real = socket.create_connection

    def guarded(address, *a, **kw):
        if address[0] != '127.0.0.1':
            hits.append(f'{address[0]}:{address[1]}')
            raise OSError('tripwire')
        return real(address, *a, **kw)
    p = mock.patch.object(socket, 'create_connection', guarded)
    p.start()
    case.addCleanup(p.stop)
    case.addCleanup(lambda: case.assertEqual(hits, [], 'вихід за межі 127.0.0.1'))


class MemoFixtureTest(CommentsEnv):
    """Серверна половина фікстури `memo-comments` працює проти справжнього HTTP-сервісу (на 127.0.0.1): це еталон для
    авторів модулів, тож він мусить бути справним, а секрет `token` — іти лише в заголовок запиту сервера."""

    def setUp(self):
        super().setUp()
        loopback_only(self)
        self.svc = MemoService()
        self.addCleanup(self.svc.stop)
        self.sp = self.new_space()
        self.prov = self.enable_memo(self.sp, self.svc.url, {'token': 'tok-memo', 'pubkey': 'pk-memo'})
        self.ctx = dm.module_ctx(self.sp, self.prov)

    def test_list_reads_the_channel_and_sends_the_token_only_as_a_header(self):
        chan = dm.channel_for(self.sp, 'task-1')
        self.svc.comments[chan] = [{'id': 'c1', 'text': 'hi', 'status': 'open'}]
        self.assertEqual(dm.call(self.prov, 'list', self.ctx, chan), [{'id': 'c1', 'text': 'hi', 'status': 'open'}])
        method, path, auth, _ = self.svc.log[-1]
        self.assertEqual((method, path, auth), ('GET', f'/c/deai%2F{self.sp["id"]}%2Ftask-1', 'Bearer tok-memo'))
        self.assertEqual(dm.call(self.prov, 'list', self.ctx, 'deai/none/other'), [])
        cfg = dm.comments_client(self.sp, self.prov)
        self.assertNotIn('tok-memo', json.dumps(cfg))

    def test_resolve_posts_the_id_and_the_reason(self):
        chan = dm.channel_for(self.sp, 'task-1')
        self.svc.comments[chan] = [{'id': 'c1', 'status': 'open'}, {'id': 'c2', 'status': 'open'}]
        self.assertIsNone(dm.call(self.prov, 'resolve', self.ctx, chan, 'c1', 'fixed in it2'))
        method, path, auth, body = self.svc.log[-1]
        self.assertEqual((method, path, auth, body), ('POST', f'/c/deai%2F{self.sp["id"]}%2Ftask-1/resolve',
                                                      'Bearer tok-memo', {'id': 'c1', 'reason': 'fixed in it2'}))
        self.assertEqual([(c['id'], c['status']) for c in self.svc.comments[chan]], [('c1', 'resolved'), ('c2', 'open')])

    def test_check_is_ok_and_a_non_http_endpoint_is_refused(self):
        self.assertEqual(dm.check(self.sp, 'memo-comments'), {'ok': True})
        dm.write_module_state(self.sp, 'memo-comments', settings={'endpoint': 'file:///etc/passwd'})
        ctx = dm.module_ctx(self.sp, self.prov)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.prov, 'list', ctx, 'deai/x/y')
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertIn('http', cm.exception.message)

    def test_a_dead_service_is_a_module_error_without_the_token(self):
        self.svc.stop()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.prov, 'list', self.ctx, 'deai/x/y')
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn('tok-memo', cm.exception.message)

    def test_redirects_are_refused_and_the_token_never_follows_them(self):
        """Сервіс відповідає 302 на сторонню адресу: фікстура не йде за нею (токен у `Authorization` лишився б у чужому
        запиті) — це `HTTPError`, а на «чужому» сервісі не зʼявляється жодного запиту."""
        sink = MemoService()
        self.addCleanup(sink.stop)
        self.svc.redirect = sink.url
        chan = dm.channel_for(self.sp, 'task-1')
        for fn, args in (('list', (chan,)), ('resolve', (chan, 'c1', 'r'))):
            with self.assertRaises(dm.ModuleError, msg=fn) as cm:
                dm.call(self.prov, fn, self.ctx, *args)
            self.assertEqual(cm.exception.code, 'module-error')
            self.assertIn('302', cm.exception.message)
            self.assertNotIn('tok-memo', cm.exception.message)
        self.assertEqual(sink.log, [], 'токен поїхав за переадресацією')
        self.assertEqual([m for m, *_ in self.svc.log], ['GET', 'POST'])                      # свій сервіс запитано по разу

    def test_install_memo_is_idempotent(self):
        self.install_memo()
        self.install_memo()
        self.assertEqual(dm.catalog()['memo-comments'].status, 'ok')

    def test_the_fixture_imports_only_the_stdlib_and_never_the_core(self):
        import ast
        tree = ast.parse(_read(os.path.join(MEMO, 'server.py')).decode('utf-8'))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split('.')[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or '').split('.')[0])
        self.assertEqual(mods, {'json', 'urllib'})


# --------------------------------------------------------------------------------- DEAI_EXTRA_MODULES

class ExtraModulesTest(CommentsEnv):
    def set_extra(self, extra):
        """`DEAI_EXTRA_MODULES` = `extra` (`None` — прибрати) до кінця тесту. ⛔ НЕ `mock.patch.dict(os.environ)` у тілі
        тесту: його `stop` у `addCleanup` біжить ПІСЛЯ `Env.tearDown` і повернув би в оточення тимчасові `DEAI_HOME`/`HOME`
        цього тесту (витік у наступні модулі тестів). Тут відновлюється лише одна змінна."""
        prior = os.environ.get('DEAI_EXTRA_MODULES')

        def restore():
            if prior is None:
                os.environ.pop('DEAI_EXTRA_MODULES', None)
            else:
                os.environ['DEAI_EXTRA_MODULES'] = prior
        self.addCleanup(restore)
        if extra is None:
            os.environ.pop('DEAI_EXTRA_MODULES', None)
        else:
            os.environ['DEAI_EXTRA_MODULES'] = extra

    def real_catalog(self, extra=FIXTURES):
        """Справжній каталог (`app/modules`) + `DEAI_EXTRA_MODULES=extra`."""
        patch = mock.patch.object(dm, 'builtin_dir', tm._REAL_BUILTIN_DIR)
        patch.start()
        self.addCleanup(patch.stop)
        self.set_extra(extra)
        dm.reset_caches()
        return dm.catalog()

    def test_extra_dir_reads_the_environment_each_time(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_EXTRA_MODULES', None)
            self.assertIsNone(dm.extra_dir())
            for blank in ('', '   '):
                os.environ['DEAI_EXTRA_MODULES'] = blank
                self.assertIsNone(dm.extra_dir(), repr(blank))
            os.environ['DEAI_EXTRA_MODULES'] = FIXTURES + '/'
            self.assertEqual(dm.extra_dir(), FIXTURES)               # нормалізований абсолютний шлях
            os.environ['DEAI_EXTRA_MODULES'] = os.path.relpath(FIXTURES)
            self.assertEqual(dm.extra_dir(), FIXTURES)

    def test_the_real_catalog_loads_the_memo_fixture_as_an_ok_module(self):
        cat = self.real_catalog()
        m = cat['memo-comments']
        self.assertEqual((m.status, m.error, m.error_code), ('ok', None, None))
        self.assertEqual((m.roles, m.client, m.dir), (['comments'], ('adapter.js',), MEMO))
        self.assertEqual([s['key'] for s in m.settings], ['endpoint', 'token', 'pubkey'])
        self.assertEqual(m.private_secret_keys(), ['token'])
        for name in ('client_config', 'list', 'resolve', 'check'):
            self.assertTrue(callable(m.fn(name)), name)
        self.assertEqual([k for k in cat if k != 'memo-comments'], BUILTIN_IDS)
        self.assertTrue(all(cat[k].status == 'ok' for k in cat), {k: cat[k].error for k in cat})
        self.assertEqual(list(cat), sorted(cat))                     # за абеткою, обидві теки разом
        self.assertEqual(dm.shadowed(), {})

    def test_the_known_module_lists_are_exactly_the_real_builtins_split_by_the_comments_role(self):
        """Правило «загубився модуль коментарів» (`_enabled_module_is_lost`) спирається на два списки id; істина — маніфести
        справжніх вбудованих модулів, а не самі списки: новий вбудований модуль, не записаний ні в один, червонить це."""
        cat = self.real_catalog(extra=None)
        comments = {k for k, m in cat.items() if 'comments' in m.roles}
        self.assertEqual(comments, set(dm.KNOWN_COMMENTS_MODULES))
        # ⚠️ 4c-2 Task 2: `jira-tracker` уже в `KNOWN_OTHER_MODULES`, а самого модуля ще нема (Task 3 його додає). Task 3 МУСИТЬ
        # прибрати `- {'jira-tracker'}` — інакше цей інваріант лишиться послабленим.
        self.assertEqual(set(cat) - comments, set(dm.KNOWN_OTHER_MODULES) - {'jira-tracker'})
        self.assertTrue(comments)
        self.assertEqual(set(dm.KNOWN_COMMENTS_MODULES) & set(dm.KNOWN_OTHER_MODULES), set())

    def test_without_the_variable_the_fixture_is_not_there(self):
        cat = self.real_catalog(extra=None)
        self.assertNotIn('memo-comments', cat)
        self.assertEqual(sorted(cat), BUILTIN_IDS)

    def test_unset_again_drops_the_module_without_a_cache_reset(self):
        self.real_catalog()
        self.assertIn('memo-comments', dm.catalog())
        self.assertIn(MEMO, dm._CACHE)
        os.environ.pop('DEAI_EXTRA_MODULES')
        self.assertNotIn('memo-comments', dm.catalog())
        self.assertNotIn(MEMO, dm._CACHE)                            # запис кешу чужої теки прибрано
        os.environ['DEAI_EXTRA_MODULES'] = FIXTURES
        self.assertEqual(dm.catalog()['memo-comments'].status, 'ok')

    def test_an_id_of_a_builtin_module_wins_and_the_extra_one_is_an_error(self):
        marker = os.path.join(self.tmp, 'marker')
        extra = os.path.join(self.tmp, 'extra')
        d = os.path.join(extra, 'static-publish')                    # той самий id, що й у вбудованого
        _write(os.path.join(d, 'module.json'), json.dumps(
            {'api': 1, 'id': 'static-publish', 'name': 'Impostor', 'version': '9', 'roles': ['comments'],
             'client': ['a.js']}))
        _write(os.path.join(d, 'server.py'), f'open({marker!r}, "w").close()\n' + tm.COMMENTS_FNS)
        _write(os.path.join(d, 'a.js'), tm.CLIENT_JS)
        shutil.copytree(MEMO, os.path.join(extra, 'memo-comments'))   # сусід без конфлікту — вантажиться
        cat = self.real_catalog(extra)
        built_in = cat['static-publish']
        self.assertEqual((built_in.status, built_in.name, built_in.roles),
                         ('ok', 'Публікація в теку', ['publish']))
        self.assertEqual(built_in.dir, os.path.join(ROOT, 'app', 'modules', 'static-publish'))
        self.assertEqual(cat['memo-comments'].status, 'ok')
        lost = dm.shadowed()['static-publish']
        self.assertEqual((lost.status, lost.error_code, lost.dir), ('error', 'bad-manifest', d))
        self.assertIn('built-in', lost.error)
        self.assertIsNone(lost.fn('check'))
        self.assertEqual(set(dm.shadowed()), {'static-publish'})
        self.assertFalse(os.path.exists(marker), 'server.py модуля, що програв конфлікт, не мусить виконуватись')

    def test_the_same_folder_twice_is_not_a_conflict(self):
        cat = self.real_catalog(extra=tm._REAL_BUILTIN_DIR())
        self.assertEqual(sorted(cat), BUILTIN_IDS)
        self.assertEqual(dm.shadowed(), {})

    def test_a_missing_or_foreign_extra_folder_changes_nothing(self):
        for extra in (os.path.join(self.tmp, 'nowhere'), os.path.join(FIXTURES, 'memo-comments', 'adapter.js')):
            cat = self.real_catalog(extra)
            self.assertEqual(sorted(cat), BUILTIN_IDS, extra)

    def test_hidden_and_stray_entries_of_the_extra_folder_are_ignored_like_builtin_ones(self):
        extra = os.path.join(self.tmp, 'extra')
        os.makedirs(os.path.join(extra, '.hidden'))
        os.makedirs(os.path.join(extra, '__pycache__'))
        _write(os.path.join(extra, 'stray.txt'), 'x')
        shutil.copytree(MEMO, os.path.join(extra, 'memo-comments'))
        cat = self.real_catalog(extra)
        self.assertEqual(sorted(cat), sorted([*BUILTIN_IDS, 'memo-comments']))

    def test_the_capabilities_cache_follows_the_variable(self):
        """Простір ввімкнув `memo-comments`, а модуля на цій машині ще нема (`missing`): поява теки в оточенні сама
        змінює відповідь — без скидання кешів."""
        self.real_catalog(extra=None)
        sp = self.new_space()
        _write(self.space_json(sp), json.dumps({'modules': {'memo-comments': {'enabled': True,
                                                                             'settings': {'endpoint': 'http://127.0.0.1:9'}}}}))
        self.assertIsNone(dm.capabilities(sp)['comments'])
        k1 = dm._caps_key(sp)
        os.environ['DEAI_EXTRA_MODULES'] = FIXTURES
        self.assertNotEqual(dm._caps_key(sp), k1)
        self.assertEqual(dm.capabilities(sp)['comments'], 'memo-comments')
        os.environ.pop('DEAI_EXTRA_MODULES')
        self.assertIsNone(dm.capabilities(sp)['comments'])

    def test_an_extra_module_is_enabled_and_works_like_a_builtin_one(self):
        self.real_catalog()
        sp = self.new_space()
        dm.write_module_state(sp, 'memo-comments', enabled=True, settings={'endpoint': 'http://127.0.0.1:4321'})
        self.assertEqual(dm.capabilities(sp)['comments'], 'memo-comments')
        self.assertEqual(dm.comments_client(sp, dm.provider('comments', sp)),
                         {'endpoint': 'http://127.0.0.1:4321', 'pubkey': ''})
        self.assertEqual(dm.check(sp, 'memo-comments'), {'ok': True})


class ExtraModulesLineTest(unittest.TestCase):
    """`DEAI_EXTRA_MODULES` діє мовчки лише для того, хто його виставив: сервер пише про нього ОДИН рядок у stderr
    (поруч із рядком режиму `/published`)."""

    def test_the_line_names_the_folder_and_is_one_line(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_EXTRA_MODULES', None)
            self.assertIsNone(serve.extra_modules_line())
            os.environ['DEAI_EXTRA_MODULES'] = '  '
            self.assertIsNone(serve.extra_modules_line())
            os.environ['DEAI_EXTRA_MODULES'] = FIXTURES
            line = serve.extra_modules_line()
        self.assertEqual(len(line.splitlines()), 1)
        self.assertTrue(line.startswith('DEAI_EXTRA_MODULES:'))
        self.assertIn(FIXTURES, line)
        with mock.patch.dict(os.environ, {'DEAI_EXTRA_MODULES': '/tmp/x\ny'}):          # навіть шлях із переведенням рядка
            self.assertEqual(len(serve.extra_modules_line().splitlines()), 1)

    def start_server(self, extra):
        """Справжній процес `serve.py` (PORT=0, шар вимкнено); `(рядки stdout, рядки stderr)` після старту."""
        tmp = tempfile.mkdtemp(prefix='dc-extra-')
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {k: v for k, v in os.environ.items()
               if k not in ('DEAI_HOME', 'DC_TASKS_FILE', 'PORT', 'DEAI_EXTRA_MODULES')}
        env.update(HOME=tmp, DC_TASKS_FILE=os.path.join(tmp, 'tasks.json'), PORT='0', DC_NO_OVERVIEW='1')
        if extra:
            env['DEAI_EXTRA_MODULES'] = extra
        proc = subprocess.Popen([sys.executable, '-u', '-B', serve.__file__], env=env, cwd=tmp,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = [], []
        for stream, sink in ((proc.stdout, out), (proc.stderr, err)):
            threading.Thread(target=lambda st=stream, sk=sink: [sk.append(ln.rstrip('\n')) for ln in st], daemon=True).start()
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not any(ln.startswith('/published:') for ln in out):
                time.sleep(0.1)
            if extra:
                while time.monotonic() < deadline and not any(ln.startswith('DEAI_EXTRA_MODULES:') for ln in err):
                    time.sleep(0.1)
            else:
                time.sleep(0.5)                                              # рядок (якби був) іде одразу за режимом /published
        finally:
            proc.kill()                                                      # свій процес, за дескриптором, не за шаблоном
            proc.wait(10)
        return out, err

    def test_a_started_server_prints_the_line_once_to_stderr_next_to_the_published_mode(self):
        src = open(serve.__file__, encoding='utf-8').read()
        main = src.split("if __name__ == '__main__':")[1]
        self.assertLess(main.index('print(published_mode_line())'), main.index('extra_modules_line()'))
        out, err = self.start_server(FIXTURES)
        self.assertTrue(any(ln.startswith('/published:') for ln in out), out)
        mine = [ln for ln in err if ln.startswith('DEAI_EXTRA_MODULES:')]
        self.assertEqual(len(mine), 1, err)
        with mock.patch.dict(os.environ, {'DEAI_EXTRA_MODULES': FIXTURES}):
            self.assertEqual(mine[0], serve.extra_modules_line())
        self.assertIn(FIXTURES, mine[0])
        self.assertFalse(any('DEAI_EXTRA_MODULES' in ln for ln in out), out)       # не в stdout

    def test_without_the_variable_the_server_stays_silent_about_it(self):
        out, err = self.start_server(None)
        self.assertTrue(any(ln.startswith('/published:') for ln in out), out)
        self.assertEqual([ln for ln in out + err if 'DEAI_EXTRA_MODULES' in ln], [])


# --------------------------------------------------------------------------- GET /api/module-client/…

class RouteTest(unittest.TestCase):
    """Маршрут роздачі файлів адаптера на справжньому сервері в процесі. Шар просторів ВИМКНЕНО (лише `DC_TASKS_FILE`):
    маршрут не читає ні реєстр, ні задачі. Вбудована тека — тимчасова (`builtin_dir` підмінено), справжня фікстура —
    через `DEAI_EXTRA_MODULES`."""

    PATH = '/api/module-client/memo-comments/adapter.js'

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-modclient-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mods = os.path.join(self.tmp, 'builtin')
        os.makedirs(self.mods)
        env = mock.patch.dict(os.environ, {'HOME': os.path.join(self.tmp, 'home'),
                                           'DC_TASKS_FILE': os.path.join(self.tmp, 'legacy', 'tasks.json'),
                                           'DC_NO_OVERVIEW': '1', 'DEAI_EXTRA_MODULES': FIXTURES})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        patch = mock.patch.object(dm, 'builtin_dir', lambda: self.mods)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        loopback_only(self)
        quiet = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
        quiet.start()
        self.addCleanup(quiet.stop)
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        self.port = httpd.server_address[1]

    # ---- помічники ----
    def fetch(self, path, headers=None, method='GET', body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def mkmod(self, mid='cm', files=None, roles=('comments',), client=('adapter.js',), server=None):
        """Модуль у тимчасовій вбудованій теці; `files` — `{імʼя: вміст}` (типово — файли `client`)."""
        d = os.path.join(self.mods, mid)
        man = {'api': 1, 'id': mid, 'name': mid, 'version': '1', 'roles': list(roles)}
        if client is not None:
            man['client'] = list(client)
        _write(os.path.join(d, 'module.json'), json.dumps(man))
        _write(os.path.join(d, 'server.py'), tm.COMMENTS_FNS if server is None else server)
        for name, text in (files if files is not None else {n: f'/* {mid}:{n} */\n' for n in (client or ())}).items():
            _write(os.path.join(d, name), text)
        return d

    def assert_not_found(self, path, **kw):
        st, hdr, body = self.fetch(path, **kw)
        self.assertEqual((st, body), (404, NOT_FOUND), path)
        self.assertEqual(hdr.get('x-content-type-options'), 'nosniff', path)
        self.assertTrue(hdr.get('content-type', '').startswith('text/plain'), path)
        self.assertEqual(hdr.get('content-length'), str(len(NOT_FOUND)), path)
        self.assertNotIn('etag', hdr, path)

    # ---- 200 / 304 ----
    def test_the_declared_adapter_is_served_byte_for_byte_with_its_headers(self):
        st, hdr, body = self.fetch(self.PATH)
        self.assertEqual(st, 200)
        self.assertEqual(body, _read(ADAPTER))
        self.assertEqual(hdr['content-type'], 'text/javascript; charset=utf-8')
        self.assertEqual(hdr['x-content-type-options'], 'nosniff')
        self.assertEqual(hdr['content-length'], str(len(body)))
        self.assertEqual(hdr['cache-control'], 'no-cache')
        self.assertRegex(hdr['etag'], r'^"[0-9a-f]+-[0-9a-f]+"$')

    def test_a_conditional_request_gets_304_with_the_same_protective_headers(self):
        _, hdr, _ = self.fetch(self.PATH)
        st, hdr304, body = self.fetch(self.PATH, headers={'If-None-Match': hdr['etag']})
        self.assertEqual((st, body), (304, b''))
        self.assertEqual(hdr304['etag'], hdr['etag'])
        self.assertEqual(hdr304['x-content-type-options'], 'nosniff')
        st, _, body = self.fetch(self.PATH, headers={'If-None-Match': '"nope"'})
        self.assertEqual((st, body), (200, _read(ADAPTER)))

    def test_the_etag_follows_the_file(self):
        d = self.mkmod('cm', files={'adapter.js': '/* one */\n'})
        _, h1, b1 = self.fetch('/api/module-client/cm/adapter.js')
        _write(os.path.join(d, 'adapter.js'), '/* two two */\n')
        _, h2, b2 = self.fetch('/api/module-client/cm/adapter.js')
        self.assertEqual((b1, b2), (b'/* one */\n', b'/* two two */\n'))
        self.assertNotEqual(h1['etag'], h2['etag'])
        st, _, body = self.fetch('/api/module-client/cm/adapter.js', headers={'If-None-Match': h1['etag']})
        self.assertEqual((st, body), (200, b'/* two two */\n'))

    def test_every_declared_file_is_served_and_the_query_string_is_ignored(self):
        self.mkmod('multi', client=('b.js', 'a.js'), files={'b.js': '/*b*/\n', 'a.js': '/*a*/\n'})
        self.assertEqual(self.fetch('/api/module-client/multi/a.js?v=3&x=%00')[::2], (200, b'/*a*/\n'))
        self.assertEqual(self.fetch('/api/module-client/multi/b.js')[::2], (200, b'/*b*/\n'))
        self.assertEqual(self.fetch('/api/module-client/multi/adapter%2Ejs')[0], 404)    # у `multi` такого нема

    def test_a_large_declared_file_is_served_whole(self):
        big = ('x' * 99 + '\n') * 5000
        self.mkmod('big', files={'adapter.js': big})
        st, hdr, body = self.fetch('/api/module-client/big/adapter.js')
        self.assertEqual((st, body), (200, big.encode()))
        self.assertEqual(hdr['content-length'], str(len(big)))

    # ---- 404 ----
    def test_undeclared_files_of_a_module_are_not_found(self):
        d = self.mkmod('cm', files={'adapter.js': '/*ok*/\n', 'other.js': '/*not declared*/\n', '.hidden.js': 'x',
                                    'README.md': 'x', 'sub/x.js': 'x'})
        self.assertEqual(self.fetch('/api/module-client/cm/adapter.js')[::2], (200, b'/*ok*/\n'))
        for name in ('other.js', '.hidden.js', 'README.md', 'server.py', 'module.json', 'sub/x.js', 'sub%2Fx.js',
                     'ADAPTER.js', 'Adapter.js', 'adapter.js.map', 'missing.js', 'sub', ''):
            self.assert_not_found(f'/api/module-client/cm/{name}')
        self.assertTrue(os.path.isfile(os.path.join(d, 'other.js')))        # файл на диску є — його не віддають

    def test_hostile_paths_are_not_found(self):
        self.mkmod('cm')
        for path in ('/api/module-client/', '/api/module-client/cm', '/api/module-client/cm/',
                     '/api/module-client//adapter.js', '/api/module-client/cm//adapter.js',
                     '/api/module-client/cm/adapter.js/', '/api/module-client/cm/adapter.js/x',
                     '/api/module-client/../cm/adapter.js', '/api/module-client/cm/../cm/adapter.js',
                     '/api/module-client/cm/..%2Fcm%2Fadapter.js', '/api/module-client/cm/%2e%2e/cm/adapter.js',
                     '/api/module-client/%2e%2e/adapter.js', '/api/module-client/%2e%2e%2fcm/adapter.js',
                     '/api/module-client/cm/%2e%2e', '/api/module-client/cm/%2e%2e%2fserver.py',
                     '/api/module-client/cm/.adapter.js', '/api/module-client/cm/%2eadapter.js',
                     '/api/module-client/cm/adapter.js%00', '/api/module-client/cm/adapter.js%00.png',
                     '/api/module-client/cm/adapter.js%2f..%2fserver.py', '/api/module-client/cm/adapter.js%5c',
                     '/api/module-client/cm/%ff.js', '/api/module-client/cm/%c0%af.js',
                     # некоректний UTF-8: «м'яке» розкодування (`ignore`) склало б із них оголошене імʼя
                     '/api/module-client/cm/adapter%ff.js', '/api/module-client/cm/adap%ffter.js',
                     '/api/module-client/cm/%ffadapter.js', '/api/module-client/cm/adapter.js%ff',
                     '/api/module-client/c%ffm/adapter.js', '/api/module-client/%ffcm/adapter.js',
                     '/api/module-client/cm/adapter%c0%af.js', '/api/module-client/cm/adapter%80.js',
                     '/api/module-client/CM/adapter.js', '/api/module-client/cm%2fx/adapter.js',
                     '/api/module-client/' + 'a' * 4000 + '/adapter.js', '/api/module-client/cm/' + 'a' * 4000 + '.js'):
            with self.subTest(path=path[:100]):
                self.assert_not_found(path)
        self.assertEqual(self.fetch('/api/module-client/cm/adapter.js?../../etc')[0], 200)   # query не ходить по теках

    def test_an_unknown_module_a_module_without_the_role_and_a_failed_module_are_not_found(self):
        self.mkmod('plain', roles=('publish',), client=None, server=tm.ALL_FNS,
                   files={'adapter.js': '/*x*/\n', 'client.js': '/*x*/\n'})
        self.mkmod('broken', server='def check(:\n', files={'adapter.js': '/*x*/\n'})      # server.py не компілюється
        self.mkmod('nofile', files={})                                                      # оголошений файл не лежить
        self.assertEqual(dm.catalog()['plain'].status, 'ok')
        self.assertEqual({k: dm.catalog()[k].status for k in ('broken', 'nofile')}, {'broken': 'error', 'nofile': 'error'})
        for path in ('/api/module-client/plain/adapter.js', '/api/module-client/plain/client.js',
                     '/api/module-client/broken/adapter.js', '/api/module-client/nofile/adapter.js',
                     '/api/module-client/ghost/adapter.js', '/api/module-client/static-publish/adapter.js'):
            self.assert_not_found(path)

    def test_a_symlink_swapped_in_after_loading_is_not_followed(self):
        """Підміна файла посиланням, коли модуль уже в кеші (каталог бачить стару версію): відкриття саме відмовляє."""
        d = self.mkmod('cm')
        stale = dm.catalog()['cm']
        self.assertEqual(self.fetch('/api/module-client/cm/adapter.js')[0], 200)
        secret = os.path.join(self.tmp, 'secret.txt')
        _write(secret, 'TOP-SECRET\n')
        os.remove(os.path.join(d, 'adapter.js'))
        os.symlink(secret, os.path.join(d, 'adapter.js'))
        with mock.patch.object(dm, 'catalog', return_value={'cm': stale}):
            self.assert_not_found('/api/module-client/cm/adapter.js')
        self.assert_not_found('/api/module-client/cm/adapter.js')          # і без підробки каталогу: модуль уже `error`

    def test_a_fifo_or_a_hard_link_swapped_in_after_loading_is_not_served(self):
        d = self.mkmod('cm')
        stale = dm.catalog()['cm']
        target = os.path.join(d, 'adapter.js')
        outside = os.path.join(self.tmp, 'outside.js')
        _write(outside, '/*outside*/\n')
        os.remove(target)
        os.mkfifo(target)                                                  # відкриття без O_NONBLOCK зависло б
        with mock.patch.object(dm, 'catalog', return_value={'cm': stale}):
            self.assert_not_found('/api/module-client/cm/adapter.js')
        os.remove(target)
        os.link(outside, target)
        with mock.patch.object(dm, 'catalog', return_value={'cm': stale}):
            self.assert_not_found('/api/module-client/cm/adapter.js')

    def test_a_module_folder_that_is_a_symlink_is_not_served_from(self):
        """Тека модуля — звичайна тека: через посилання на теку (каталог його бачить, `isdir` іде за посиланням) маршрут не
        відкриває нічого."""
        real = os.path.join(self.tmp, 'real-cm')
        os.makedirs(real)
        _write(os.path.join(real, 'module.json'), json.dumps(
            {'api': 1, 'id': 'cm', 'name': 'cm', 'roles': ['comments'], 'client': ['adapter.js']}))
        _write(os.path.join(real, 'server.py'), tm.COMMENTS_FNS)
        _write(os.path.join(real, 'adapter.js'), '/*behind a link*/\n')
        os.symlink(real, os.path.join(self.mods, 'cm'))
        self.assertEqual(dm.catalog()['cm'].status, 'ok')
        self.assert_not_found('/api/module-client/cm/adapter.js')

    # ---- як маршрут вбудований у сервер ----
    def test_the_task_header_and_the_registry_do_not_matter(self):
        self.assertEqual(self.fetch(self.PATH, headers={'X-Canvas-Task': 'ghost'})[::2], (200, _read(ADAPTER)))
        self.assertEqual(self.fetch(self.PATH, headers={'X-Canvas-Task': ''})[0], 200)
        deai = os.path.join(self.tmp, 'deai')
        os.makedirs(deai)
        _write(os.path.join(deai, 'spaces.json'), '{broken')                 # шар увімкнено, реєстр не читається
        with mock.patch.dict(os.environ, {'DEAI_HOME': deai}):
            self.assertEqual(self.fetch(self.PATH)[::2], (200, _read(ADAPTER)))
            self.assertEqual(self.fetch('/api/modules')[0], 503)            # контроль: решта API лягла б
        self.assertEqual(os.listdir(deai), ['spaces.json'])                  # і ми нічого не мігрували

    def test_it_is_a_get_without_an_origin_check_and_a_post_is_not_served(self):
        self.assertEqual(self.fetch(self.PATH, headers={'Origin': 'https://evil.example'})[0], 200)
        self.assertNotEqual(self.fetch(self.PATH, method='POST', body=b'{}', headers={'Origin': 'http://127.0.0.1'})[0], 200)

    def test_the_prefix_is_a_handled_prefix_and_the_route_is_not_a_registry_one(self):
        self.assertTrue(self.PATH.startswith(serve.HANDLED_PREFIXES))       # `/api/` уже покриває `/api/module-client/`
        self.assertNotIn('/api/module-client/', serve.Handler._REGISTRY_ROUTES)


# ----------------------------------------------------------------- сторінки канваса й `/api/comment-config` (Task 2)

GOLDEN = os.path.join(ROOT, 'tests', 'fixtures', 'comments-role')
#: `UPDATE_COMMENTS_GOLDEN=1` перезнімає еталони ЛІГА/«нічого» ЗІ СТАНУ КОДУ, який зараз на диску. Знімати їх можна лише
#: з коду ДО змін Task 2 (чи свідомо, коли ЛІГА змінилась навмисне): еталон і є доказ «байт у байт, як було».
UPDATE_GOLDEN = os.environ.get('UPDATE_COMMENTS_GOLDEN') == '1'
TOKEN, PUBKEY = 'tok-SECRET-9', 'pk-OPEN-9'


class PagesEnv(CommentsEnv):
    """Справжній сервер у процесі й два простори: `plain` (без інтеграцій) і `liga` (з інтеграціями); в обох — задача
    `x` з ітерацією `it1`. Поточний простір перемикає `use()`. Оточення — власне (шар просторів увімкнено, мережа — лише
    127.0.0.1, особа машини порожня)."""

    def setUp(self):
        super().setUp()
        # ЛІГА (4b-2) веде коментарі ВБУДОВАНИМ `supabase-comments`; `tm.Env` підміняє `builtin_dir()` порожньою текою.
        sbconf._ensure_builtin()
        for key, val in (('DC_NO_OVERVIEW', '1'), ('DC_IDENTITY_NAME', ''), ('DC_IDENTITY_EMAIL', '')):
            prior = os.environ.get(key)
            os.environ[key] = val
            self.addCleanup(lambda k=key, v=prior: os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))
        loopback_only(self)
        self.plain = self.new_space('Plain')
        self.liga = self.new_space('Liga', integrations=True)
        for sp in (self.plain, self.liga):
            self.write_task(sp)
        quiet = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
        quiet.start()
        self.addCleanup(quiet.stop)
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        self.port = httpd.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.use(self.plain)

    @staticmethod
    def write_task(sp, tid='x'):
        d = os.path.join(sp['path'], tid)
        _write(os.path.join(d, 'iterations.json'), json.dumps(
            {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start', 'published': False}],
             'publish_url': None}))
        _write(os.path.join(d, 'iterations', 'it1', 'index.html'),
               f'<!DOCTYPE html><html><head><title>t</title></head><body><h1>{tid}</h1></body></html>')
        _write(os.path.join(sp['path'], 'tasks.json'), json.dumps(
            {'design_work_root': sp['path'], 'current': tid,
             'tasks': {tid: {'title': 'Ікс', 'dir': d, 'profile': 'tool'}}}))

    def use(self, sp):
        spaces.switch_space(sp['id'])
        self.cur = sp

    def fetch(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('GET', path)
            r = conn.getresponse()
            return r.status, r.read().decode('utf-8')
        finally:
            conn.close()

    def page(self, ch='project', extra=''):
        st, html = self.fetch(f'/commented?it=it1&ch={ch}{extra}')
        self.assertEqual(st, 200, html[:300])
        return html

    def config(self, ch='project'):
        st, body = self.fetch(f'/api/comment-config?ch={ch}&it=it1')
        return st, json.loads(body)

    def norm(self, text):
        """Те, що різниться між прогонами (порт, id простору, публічні сталі ЛІГА), — на плейсхолдери: еталон лишається
        сталим, а решта розмітки порівнюється побайтно."""
        return (text.replace(self.origin, '{ORIGIN}').replace(f'sp={self.cur["id"]}', 'sp={SP}')
                .replace(sbconf.SB_URL, '{SB_URL}').replace(sbconf.SB_KEY, '{SB_KEY}'))

    def golden(self, name, actual):
        """Порівняти з еталоном `tests/fixtures/comments-role/<name>`; `UPDATE_COMMENTS_GOLDEN=1` — перезнімає."""
        path = os.path.join(GOLDEN, name)
        text = self.norm(actual)
        if UPDATE_GOLDEN:
            os.makedirs(GOLDEN, exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
            return
        with open(path, encoding='utf-8', newline='') as f:
            self.assertEqual(text, f.read(), name)

    def enable(self, sp, endpoint='http://127.0.0.1:9', secrets=None):
        """`memo-comments` у `sp` (токен непублічний, ключ публічний). Модуль ставиться один раз на тест."""
        if not os.path.isdir(os.path.join(self.mods, 'memo-comments')):
            self.install_memo()
        dm.write_module_state(sp, 'memo-comments', enabled=True, settings={'endpoint': endpoint})
        dm.write_secrets(sp['id'], 'memo-comments', {'token': TOKEN, 'pubkey': PUBKEY} if secrets is None else secrets)
        return dm.provider('comments', sp)

    #: Те, чого не сміє бути на сторінці, що лишилась без командного каналу: зашитий СПІЛЬНИЙ сервіс ЛІГА.
    SHARED = ('supabase', 'CommentLayerSupabase', 'cdn.jsdelivr.net')

    def break_module(self, sp=None):
        """Ввімкнути `memo-comments` у `sp` (типово — `self.liga`) і зламати його (оголошений файл зник → модуль `error`)."""
        self.enable(sp or self.liga)
        os.remove(os.path.join(self.mods, 'memo-comments', 'adapter.js'))
        self.assertEqual(dm.catalog()['memo-comments'].status, 'error')

    def assert_local_with_notice(self, html, code):
        self.assertIn('local-adapter.js', html)
        self.assertNotIn('__deaiCommentsCfg', html)
        self.assertNotIn('/api/module-client/', html)
        self.assertNotIn('audiences:', html)                           # командного каналу нема — вкладки «Команда» теж
        for shared in self.SHARED + (sbconf.SB_URL, sbconf.SB_KEY):
            self.assertNotIn(shared, html, shared)
        self.assertNotIn('supabase', html.lower())
        notice = re.search(r"window\.__clDown\(([^\n]*)\);\s*</script>\s*</body>", html)
        self.assertIsNotNone(notice, 'примітка про відмову має бути видимою')
        self.assertIn(code, notice.group(1))

    def assert_no_shared_service_in(self, body):
        for shared in (sbconf.SB_URL, sbconf.SB_KEY, 'sbUrl', 'sbKey'):
            self.assertNotIn(shared, body, shared)

    def cfg_of(self, html):
        """Конфіг сторінки: `window.__deaiCommentsCfg = <літерал>;` → dict (літерал — валідний JSON)."""
        m = re.search(r'window\.__deaiCommentsCfg = (\{.*?\});\n', html)
        self.assertIsNotNone(m, 'у сторінці нема window.__deaiCommentsCfg')
        return json.loads(m.group(1))


class LegacyPagesTest(PagesEnv):
    """ЛІГА й «нічого» — БАЙТ У БАЙТ як до 2b-2: еталони зняті з коду bc2d786 (до Task 2)."""

    def test_the_league_project_page_is_the_builtin_module_page_golden(self):
        """4b-2: ЄДИНИЙ еталон, що свідомо змінився (разом з `config-legacy-project.json`): сторінка ЛІГИ — сніпет модуля
        `supabase-comments` (конфіг установки, канал `dc/x`). Решта еталонів теки — ті самі байти, що до 4b-2."""
        self.use(self.liga)
        self.assertEqual(dm.provider('comments', self.liga), 'legacy')
        self.golden('page-legacy-project.html', self.page('project'))

    def test_the_league_local_page_is_byte_identical_and_keeps_its_audience_tabs(self):
        self.use(self.liga)
        self.golden('page-legacy-local.html', self.page('local'))

    def test_without_a_provider_the_project_page_is_demoted_to_local_byte_identical(self):
        self.assertIsNone(dm.provider('comments', self.plain))
        html = self.page('project')
        self.assertNotIn('audiences:', html)
        self.assertNotIn('__deaiCommentsCfg', html)
        self.golden('page-none-project.html', html)

    def test_a_module_that_was_disabled_again_leaves_exactly_the_demotion(self):
        self.enable(self.plain)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        self.golden('page-none-project.html', self.page('project'))

    def test_the_league_space_gets_the_builtin_module_snippet_only_on_the_project_channel(self):
        """4b-2: проєктний канал ЛІГИ — модуль `supabase-comments` (було: «ЛІГА ніколи не отримує сніпета модуля»); локальний
        канал, як і був, без модуля й без Supabase."""
        self.use(self.liga)
        local = self.page('local')
        for gone in ('__deaiCommentsCfg', '/api/module-client/', 'DeaiComments', 'cdn.jsdelivr.net', 'supabase'):
            self.assertNotIn(gone, local, gone)
        project = self.page('project')
        self.assertIn('/api/module-client/supabase-comments/adapter.js', project)
        self.assertEqual(self.cfg_of(project)['url'], sbconf.SB_URL)
        self.assertNotIn('cdn.jsdelivr.net', project)

    def test_comment_config_legacy_none_and_local_keep_their_bodies(self):
        self.use(self.liga)
        st, body = self.fetch('/api/comment-config?ch=project&it=it1')
        self.assertEqual(st, 200)
        self.golden('config-legacy-project.json', body)
        self.assertEqual(set(json.loads(body)), {'ch', 'module', 'client', 'config', 'channel', 'version'})
        self.use(self.plain)
        st, body = self.fetch('/api/comment-config?ch=project&it=it1')
        self.assertEqual(st, 409)
        self.golden('config-none-project.json', body)
        self.assertEqual(json.loads(body)['code'], 'integrations-off')
        st, body = self.fetch('/api/comment-config?ch=local&it=it1')
        self.assertEqual(st, 200)
        self.golden('config-none-local.json', body)
        self.assertEqual(json.loads(body)['endpoint'], '/api/local-comments')


class LeaguePrivacyTest(PagesEnv):
    """Простір ЛІГА (з інтеграціями), де людина ЯВНО ввімкнула модуль коментарів, що потім не завантажився, або де
    `space.json` не прочитати: сторінка НЕ переходить мовчки на зашитий СПІЛЬНИЙ Supabase ЛІГА (піни несли б знімки
    приватних макетів), а лишається на локальному шарі з приміткою; `/api/comment-config` — центральна відповідь модулів.
    Усе — через справжній HTTP."""

    def setUp(self):
        super().setUp()
        self.use(self.liga)

    def test_a_broken_enabled_module_leaves_the_page_local_with_a_notice_and_no_shared_snippet(self):
        self.break_module()
        self.assert_local_with_notice(self.page('project'), 'module-error')

    def test_a_broken_enabled_module_makes_comment_config_the_central_error(self):
        self.break_module()
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        body = json.loads(raw)
        self.assertEqual((st, body['ok'], body['code']), (502, False, 'module-error'))
        self.assertEqual(body['error'], dm.COMMENTS_MODULE_BROKEN)
        self.assert_no_shared_service_in(raw)

    def test_an_unreadable_space_json_leaves_the_page_local_with_a_notice_and_no_shared_snippet(self):
        _write(self.space_json(self.liga), '{broken')
        self.assert_local_with_notice(self.page('project'), 'space-json-unreadable')

    def test_an_unreadable_space_json_makes_comment_config_the_409(self):
        _write(self.space_json(self.liga), '{broken')
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        body = json.loads(raw)
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'))
        self.assert_no_shared_service_in(raw)

    def test_the_task_endpoint_reports_no_team_comments_with_the_error(self):
        _write(self.space_json(self.liga), '{broken')
        st, raw = self.fetch('/api/task')
        self.assertEqual(st, 200, raw)
        self.assertEqual(json.loads(raw)['space']['capabilities'],
                         {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy', 'dashboard': None, 'tracker': None, 'error': 'space-json-unreadable'})

    def test_the_local_page_of_that_space_has_no_shared_snippet_either(self):
        self.break_module()
        html = self.page('local')
        self.assertIn('local-adapter.js', html)
        for shared in self.SHARED + (sbconf.SB_URL, sbconf.SB_KEY):
            self.assertNotIn(shared, html, shared)

    def test_controls_a_disabled_or_absent_entry_keeps_the_league_snippet(self):
        # Шлях ЛІГИ з 4b-2 — вбудований `supabase-comments` з конфігом установки (було: зашитий сніпет з CDN Supabase).
        self.break_module()
        dm.write_module_state(self.liga, 'memo-comments', enabled=False)             # людина вимкнула — шлях ЛІГИ
        html = self.page('project')
        self.assertIn('/api/module-client/supabase-comments/adapter.js', html)
        self.assertEqual(self.cfg_of(html)['url'], sbconf.SB_URL)
        self.assertEqual(self.fetch('/api/comment-config?ch=project&it=it1')[0], 200)
        _write(self.space_json(self.liga), json.dumps({'name': 'x'}))                # запису нема взагалі
        self.assertIn('/api/module-client/supabase-comments/adapter.js', self.page('project'))


class PlainSpaceLostModuleTest(PagesEnv):
    """Простір БЕЗ інтеграцій, де людина ЯВНО ввімкнула модуль коментарів, що потім не завантажився: запасного шляху нема,
    але й тиші нема — сторінка лишається локальною З приміткою, `comment-config` називає помилку модуля (а не
    «integrations-off»), `/api/task` несе `capabilities.error`. Простір без жодного запису про коментарі — як і було."""

    def setUp(self):
        super().setUp()
        self.use(self.plain)

    def capabilities(self):
        st, raw = self.fetch('/api/task')
        self.assertEqual(st, 200, raw)
        return json.loads(raw)['space']['capabilities']

    def test_the_page_stays_local_with_a_notice_and_no_tabs(self):
        self.break_module(self.plain)
        self.assert_local_with_notice(self.page('project'), 'module-error')

    def test_comment_config_names_the_module_error_not_integrations_off(self):
        self.break_module(self.plain)
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        body = json.loads(raw)
        self.assertEqual((st, body['ok'], body['code']), (502, False, 'module-error'))
        self.assertEqual(body['error'], dm.COMMENTS_MODULE_BROKEN)
        self.assertNotIn('integrations-off', raw)
        self.assert_no_shared_service_in(raw)

    def test_the_task_endpoint_carries_the_error(self):
        self.break_module(self.plain)
        self.assertEqual(self.capabilities(),
                         {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'dashboard': None, 'tracker': None, 'error': 'module-error'})

    def test_the_local_page_has_no_notice_and_the_local_comments_work(self):
        self.break_module(self.plain)
        html = self.page('local')
        self.assertIn('local-adapter.js', html)
        self.assertNotIn('window.__clDown(', html)

    def test_without_a_comments_entry_nothing_changes_even_with_a_stale_unrelated_one(self):
        for body in ({}, {'modules': {'ghost': {'enabled': True}}}):
            with self.subTest(body=body):
                _write(self.space_json(self.plain), json.dumps(body))
                self.golden('page-none-project.html', self.page('project'))
                st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
                self.golden('config-none-project.json', raw)
                self.assertEqual((st, json.loads(raw)['code']), (409, 'integrations-off'))
                self.assertNotIn('error', self.capabilities())

    def test_a_stale_unrelated_entry_keeps_the_league_snippet_in_a_league_space(self):
        self.use(self.liga)
        _write(self.space_json(self.liga), json.dumps({'modules': {'ghost': {'enabled': True}}}))
        self.assertIn('/api/module-client/supabase-comments/adapter.js', self.page('project'))
        self.assertEqual(self.fetch('/api/comment-config?ch=project&it=it1')[0], 200)
        self.assertNotIn('error', self.capabilities())


class ModulePagesTest(PagesEnv):
    def setUp(self):
        super().setUp()
        self.prov = self.enable(self.plain, 'http://127.0.0.1:4555')

    def test_the_module_page_loads_core_then_adapter_then_config_then_the_loader(self):
        html = self.page('project')
        at = [html.index(s) for s in (
            'window.__clDown = function',
            f'<script src="{self.origin}/app/vendor/comment-layer.min.js"',
            '<script src="/api/module-client/memo-comments/adapter.js"',
            'window.__deaiCommentsCfg = ',
            'window.DeaiComments.create(')]
        self.assertEqual(at, sorted(at), 'порядок скриптів несучий: банер → шар → адаптер → конфіг → завантажувач')
        self.assertEqual(html.count('/api/module-client/'), 1)
        self.assertEqual(html.count('comment-layer.min.js'), 1)
        for gone in ('supabase', 'local-adapter.js', 'CommentLayerSupabase', 'CommentLayerLocal'):
            self.assertNotIn(gone, html.lower() if gone == 'supabase' else html, gone)
        self.assertIn('storage: store', html)
        self.assertIn('window.CommentLayer.init(', html)

    def test_the_adapter_tag_reports_its_own_failure_through_the_banner(self):
        html = self.page('project')
        tag = re.search(r'<script src="/api/module-client/memo-comments/adapter\.js"[^>]*>', html).group(0)
        self.assertRegex(tag, r'onerror="window\.__clDown\(')
        layer = re.search(r'<script src="[^"]*comment-layer\.min\.js"[^>]*>', html).group(0)
        self.assertRegex(layer, r'onerror="window\.__clDown\(')

    def test_the_page_config_is_the_public_config_plus_the_channel_and_nothing_else(self):
        html = self.page('project')
        self.assertEqual(self.cfg_of(html), {'endpoint': 'http://127.0.0.1:4555', 'pubkey': PUBKEY,
                                             'channel': f'deai/{self.plain["id"]}/x'})
        self.assertNotIn(TOKEN, html)
        self.assertIn('window.CommentLayer.init({ projectId: cfg.channel,', html)

    def test_the_loader_passes_the_version_and_an_onchange_hook_and_survives_a_missing_ready(self):
        html = self.page('project')
        ver = serve.pm.page_version_tag('it1', {'id': serve.pm.IMPLICIT_ID})
        self.assertIn(f'version: "{ver}"', html)
        self.assertIn('onChange: function', html)
        self.assertIn('Promise.resolve(store.ready)', html)             # `ready` — необовʼязковий у контракті
        self.assertRegex(html, r'catch \(e\) \{\s*window\.__clDown\(')   # create() кинув — банер, не мовчки

    def test_the_audience_tabs_and_the_inspector_are_there_like_in_the_league_page(self):
        html = self.page('project')
        self.assertIn('audiences:', html)
        self.assertRegex(html, r"id: 'project', label: L\.team, active: true")
        self.assertRegex(html, r"id: 'local', label: L\.local, active: false")
        self.assertRegex(html, r'<script type="module" src="[^"]*/inspector\.js\?ds=tool&sp=' + re.escape(self.plain['id']))
        self.assertIn('onAudience:', html)

    def test_the_local_page_of_a_module_space_has_the_audience_tabs_with_local_active(self):
        html = self.page('local')
        self.assertIn('local-adapter.js', html)
        self.assertRegex(html, r"id: 'local', label: L\.local, active: true")
        self.assertRegex(html, r"id: 'project', label: L\.team, active: false")
        self.assertNotIn('__deaiCommentsCfg', html)

    def test_a_space_with_integrations_and_a_module_gets_the_module_not_the_league_snippet(self):
        self.use(self.liga)
        self.enable(self.liga, 'http://127.0.0.1:4556')
        html = self.page('project')
        self.assertEqual(self.cfg_of(html)['channel'], f'deai/{self.liga["id"]}/x')
        for gone in ('supabase', 'dc/x'):
            self.assertNotIn(gone, html.lower())

    def test_two_spaces_with_the_same_task_id_never_share_a_channel(self):
        self.use(self.liga)
        self.enable(self.liga, 'http://127.0.0.1:4556')
        liga_channel = self.cfg_of(self.page('project'))['channel']
        self.use(self.plain)
        self.assertNotEqual(self.cfg_of(self.page('project'))['channel'], liga_channel)

    def test_a_hostile_config_value_cannot_break_out_of_the_script(self):
        hostile = '</script><script>alert(1)</script>\u2028\u2029&"\'\\'
        self.mkcm('hostile', server=cfg_server('{"endpoint": ctx["settings"]["note"], "pubkey": ctx["secrets"]["pubkey"]}'),
                  settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'hostile', enabled=True, settings={'note': hostile})
        dm.write_secrets(self.plain['id'], 'hostile', {'token': TOKEN, 'pubkey': PUBKEY})
        html = self.page('project')
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertNotIn('\u2028', html)
        self.assertNotIn('\u2029', html)
        self.assertIn('\\u003c/script\\u003e', html)
        self.assertEqual(self.cfg_of(html)['endpoint'], hostile)           # літерал розбирається назад у те саме значення

    def test_the_channel_is_the_cores_even_if_the_module_config_names_one(self):
        self.mkcm('chan', server=cfg_server('{"channel": "evil/channel", "onChange": "x", "k": 1}'), settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'chan', enabled=True)
        self.assertEqual(self.cfg_of(self.page('project'))['channel'], f'deai/{self.plain["id"]}/x')
        body = self.config('project')[1]
        self.assertEqual(body['channel'], f'deai/{self.plain["id"]}/x')
        self.assertEqual(body['config']['channel'], 'evil/channel')         # конфіг віддаємо як є; склеює і ставить канал ХОСТ

    def test_the_adapter_files_are_loaded_in_the_manifest_order_before_the_config(self):
        self.mkcm('twin', client=('a.js', 'b.js'), server=cfg_server('{"k": 1}'), settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'twin', enabled=True)
        html = self.page('project')
        at = [html.index(f'<script src="/api/module-client/twin/{n}"') for n in ('a.js', 'b.js')]
        self.assertEqual(at, sorted(at), 'файли адаптера — у порядку маніфесту')
        self.assertLess(at[1], html.index('window.__deaiCommentsCfg'))

    # ---- відмова модуля: локальний шар + видима примітка, ніколи не 5xx ----
    def assert_fallback(self, html, code):
        self.assertIn('local-adapter.js', html)
        self.assertNotIn('__deaiCommentsCfg', html)
        self.assertNotIn('DeaiComments', html)
        self.assertNotIn('/api/module-client/', html)
        self.assertNotIn('audiences:', html)                # вкладка «Команда» вела б у ту саму відмову: на локальній сторінці її нема
        self.assertNotIn('onAudience', html)
        notice = re.search(r"window\.__clDown\(([^\n]*)\);\s*</script>\s*</body>", html)
        self.assertIsNotNone(notice, 'примітка про відмову має бути видимою (банер) в кінці сторінки')
        self.assertIn(code, notice.group(1))
        self.assertIn('window.__clDown = function', html)
        for secret in (TOKEN, PUBKEY):
            self.assertNotIn(secret, html)

    def test_a_private_secret_in_the_config_falls_back_to_the_local_layer_with_a_notice(self):
        self.mkcm('leaky', server=cfg_server('{"endpoint": ctx["secrets"]["token"]}'), settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'leaky', enabled=True)
        dm.write_secrets(self.plain['id'], 'leaky', {'token': TOKEN, 'pubkey': PUBKEY})
        self.assert_fallback(self.page('project'), 'module-error')

    def test_missing_settings_fall_back_with_the_code(self):
        dm.write_module_state(self.plain, 'memo-comments', settings={'endpoint': None})        # `None` знімає ключ
        self.assert_fallback(self.page('project'), 'bad-settings')

    def test_a_module_that_does_not_answer_falls_back_with_check_timeout(self):
        self.mkcm('slow', server=tm.CHECK_ONLY + 'import time\ndef client_config(ctx):\n    time.sleep(3)\n    return {}\n'
                  + LIST_RESOLVE)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'slow', enabled=True)
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            self.assert_fallback(self.page('project'), 'check-timeout')

    def test_unreadable_secrets_fall_back_with_the_code(self):
        _write(self.secrets_file, '{broken')
        self.assert_fallback(self.page('project'), 'secrets-unreadable')

    def test_an_unreadable_space_json_falls_back_to_local_with_the_code_and_without_tabs(self):
        _write(self.space_json(self.plain), '{broken')
        html = self.page('project')
        self.assertIn('local-adapter.js', html)
        self.assertNotIn('audiences:', html)                               # провайдера не вирішити — вкладок нема
        self.assertIn('space-json-unreadable', html)

    def test_a_lone_surrogate_in_the_config_falls_back_with_a_notice_not_a_dropped_connection(self):
        self.mkcm('surr', server=cfg_server('{"endpoint": "\\ud800"}'), settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'surr', enabled=True)
        self.assert_fallback(self.page('project'), 'module-error')
        st, body = self.config('project')
        self.assertEqual((st, body['code']), (502, 'module-error'))

    def test_a_clean_local_page_has_no_notice(self):
        self.assertNotIn('window.__clDown', self.page('local'))

    # ---- /api/comment-config ----
    def test_comment_config_of_a_module_names_the_adapter_the_public_config_and_the_channel(self):
        st, body = self.config('project')
        self.assertEqual(st, 200)
        self.assertEqual(body, {
            'ch': 'project', 'module': 'memo-comments',
            'client': ['/api/module-client/memo-comments/adapter.js'],
            'config': {'endpoint': 'http://127.0.0.1:4555', 'pubkey': PUBKEY},
            'channel': f'deai/{self.plain["id"]}/x',
            'version': serve.pm.page_version_tag('it1', {'id': serve.pm.IMPLICIT_ID})})
        self.assertNotIn(TOKEN, json.dumps(body))

    def test_comment_config_carries_the_machine_identity_when_there_is_one(self):
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        self.assertEqual(self.config('project')[1]['user'], {'name': 'Lead'})

    def test_comment_config_client_urls_are_served_by_the_adapter_route(self):
        for url in self.config('project')[1]['client']:
            st, body = self.fetch(url)
            self.assertEqual(st, 200, url)
            self.assertIn('DeaiComments', body)

    def test_comment_config_local_is_unchanged_in_a_module_space(self):
        st, body = self.config('local')
        self.assertEqual((st, body['ch'], body['endpoint']), (200, 'local', '/api/local-comments'))
        self.assertNotIn('module', body)

    def test_comment_config_module_errors_use_the_central_mapping(self):
        dm.write_module_state(self.plain, 'memo-comments', settings={'endpoint': None})
        st, body = self.config('project')
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'bad-settings'))
        dm.write_module_state(self.plain, 'memo-comments', settings={'endpoint': 'http://127.0.0.1:9'})
        _write(self.secrets_file, '{broken')
        st, body = self.config('project')
        self.assertEqual((st, body['code']), (409, 'secrets-unreadable'))
        _write(self.secrets_file, '{}')
        self.mkcm('leaky', server=cfg_server('{"endpoint": ctx["secrets"]["token"]}'), settings=CFG_SETTINGS)
        dm.write_module_state(self.plain, 'memo-comments', enabled=False)
        dm.write_module_state(self.plain, 'leaky', enabled=True)
        dm.write_secrets(self.plain['id'], 'leaky', {'token': TOKEN, 'pubkey': PUBKEY})
        st, body = self.config('project')
        self.assertEqual((st, body['code']), (502, 'module-error'))
        self.assertNotIn(TOKEN, json.dumps(body))
        self.mkcm('slow', server=tm.CHECK_ONLY + 'import time\ndef client_config(ctx):\n    time.sleep(3)\n    return {}\n'
                  + LIST_RESOLVE)
        dm.write_module_state(self.plain, 'leaky', enabled=False)
        dm.write_module_state(self.plain, 'slow', enabled=True)
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            st, body = self.config('project')
        self.assertEqual((st, body['code']), (504, 'check-timeout'))

    def test_comment_config_with_an_unreadable_space_json_is_the_modules_409(self):
        _write(self.space_json(self.plain), '{broken')
        st, body = self.config('project')
        self.assertEqual((st, body['code']), (409, 'space-json-unreadable'))


# ------------------------------------------------------------ вузькі перевірки сніпета, примітки, еталонів (fixup Task 2)

class GoldenPinTest(unittest.TestCase):
    """Еталони ЛІГА/«нічого» — зняті з коду bc2d786 ДО Task 2 і є доказом «байт у байт, як було». `UPDATE_COMMENTS_GOLDEN=1`
    перезнімає їх з коду, що на диску, — тож без цього піна можна було б непомітно «оновити» еталон під зламану розмітку.
    Хеші нижче — єдиний спосіб змінити еталон свідомо: правка ЛІГА навмисна → перезняти, подивитись diff очима, тут оновити.

    4b-2 свідомо переписала РІВНО два еталони: `page-legacy-project.html` і `config-legacy-project.json` (проєктний канал ЛІГИ
    тепер іде вбудованим модулем `supabase-comments`); решта — ті самі байти, що були."""

    PINNED = {
        'config-legacy-project.json': '1902c6bb59f0e32bd20068d5979940a97ad392a2752b161bbc841509c4ef5892',
        'config-none-local.json': '02da2eb3d4f6b11c77b32765877cbdd7cd498c2b4bb02af86cb340c5d49024a3',
        'config-none-project.json': 'c995db0e753b0270167a9e610c1aac33bee715677792cf86cfb430cd50e7bb32',
        'page-legacy-local.html': '2dc27d049848297412db855195a4a469a9d8e92bd585d74b82aeea34e07aff08',
        'page-legacy-project.html': '28ebf5739a8580881964c44194fe9a45d0b68223c184d97f0715575317c560fb',
        'page-none-project.html': '56b9b4779251d9157e4ccd490f0ceb2643bde1504aeebdba591259f70acc5dfb',
    }

    def test_the_golden_files_are_exactly_the_pinned_captures(self):
        import hashlib
        have = {n: hashlib.sha256(_read(os.path.join(GOLDEN, n))).hexdigest() for n in sorted(os.listdir(GOLDEN))}
        self.assertEqual(have, self.PINNED)


class SnippetUnitTest(unittest.TestCase):
    """Екранування у функціях інʼєкції — напряму, без сервера: hostile імена файлів, `assets`, `version`, `why`."""

    HOSTILE = '</script><script>alert(1)</script>"\'&  '

    def inject(self, **kw):
        args = dict(html='<html><body></body></html>', assets_base='http://h:1/app/vendor', client_urls=['/api/module-client/m/a.js'],
                    config={'channel': 'c'}, version='1')
        args.update(kw)
        return serve.inject_module_comment_layer(args.pop('html'), args.pop('assets_base'), args.pop('client_urls'),
                                                 args.pop('config'), **args)

    def test_adapter_urls_are_attribute_escaped_and_each_is_one_tag(self):
        urls = ['/x"><script>alert(1)</script>.js', "/y' onerror='alert(1).js", '/z&amp;.js']
        out = self.inject(client_urls=urls)
        self.assertNotIn('"><script>alert(1)', out)
        self.assertNotIn("' onerror='alert(1)", out.replace('&#x27;', ''))
        self.assertIn('src="/x&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;.js"', out)
        self.assertIn('src="/y&#x27; onerror=&#x27;alert(1).js"', out)
        self.assertIn('src="/z&amp;amp;.js"', out)
        self.assertEqual(out.count('<script src='), 1 + len(urls))                 # шар + по тегу на файл

    def test_a_hostile_assets_base_cannot_leave_the_src_attribute(self):
        out = self.inject(assets_base='http://h"><script>alert(1)</script>/app', inspector=True)
        self.assertNotIn('"><script>alert(1)', out)
        self.assertIn('http://h&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;/app/comment-layer.min.js', out)
        self.assertIn('/app/inspector.js', out.replace('&lt;/script&gt;', ''))

    def test_a_hostile_version_is_a_js_literal_that_round_trips(self):
        out = self.inject(version='1"</script><script>alert(1)// ')
        self.assertNotIn('</script><script>alert(1)', out)
        self.assertNotIn(' ', out)
        m = re.search(r'version: ("(?:[^"\\]|\\.)*")', out)
        self.assertEqual(json.loads(m.group(1)), '1"</script><script>alert(1)// ')

    def test_a_hostile_config_still_round_trips(self):
        out = self.inject(config={'channel': 'c', 'k': self.HOSTILE})
        self.assertNotIn('</script><script>alert(1)', out)
        self.assertEqual(json.loads(re.search(r'window\.__deaiCommentsCfg = (\{.*?\});\n', out).group(1))['k'], self.HOSTILE)

    def test_the_notice_text_is_a_js_literal_that_round_trips(self):
        out = serve.inject_comment_notice('<html><body></body></html>', self.HOSTILE)
        self.assertNotIn('</script><script>alert(1)', out)
        self.assertNotIn(' ', out)
        self.assertNotIn(' ', out)
        m = re.search(r'window\.__clDown\((".*")\);</script>', out)
        self.assertEqual(json.loads(m.group(1)), self.HOSTILE)

    def test_the_banner_function_is_the_same_as_the_league_one(self):
        """Банер модульної сторінки не розходиться зі СТАРИМ ЛІГА-шним (4b-2: шаблону `COMMENT_SNIPPET` уже нема — еталон
        старого банера лежить у знімку сторінки `tests/fixtures/legacy-comments/old-snippet-page.html`)."""
        old = _read(os.path.join(ROOT, 'tests', 'fixtures', 'legacy-comments', 'old-snippet-page.html')).decode('utf-8')
        pat = re.compile(r'window\.__clDown = function \(why\) \{.*?\n\};', re.S)
        legacy = pat.search(old)
        mine = pat.search(serve._COMMENT_DOWN_BANNER.replace('{{', '{').replace('}}', '}'))
        self.assertIsNotNone(legacy)
        self.assertIsNotNone(mine)
        self.assertEqual(mine.group(0), legacy.group(0))
        mine = re.search(r'window\.__clDown = function \(why\) \{\{.*?\n\}\};', serve._COMMENT_DOWN_BANNER, re.S)
        self.assertEqual(serve.MODULE_COMMENT_SNIPPET.count(mine.group(0)), 1, 'модульний сніпет несе той самий банер')


@unittest.skipUnless(shutil.which('node'), 'node не знайдено')
class LoaderRuntimeTest(unittest.TestCase):
    """Завантажувач модульної сторінки ВИКОНУЄТЬСЯ (node, `vm`, підставні `window`/`document`): які сховища пускає в
    коментатор, а які — у банер. Решта тестів лише читають текст."""

    HARNESS = r"""
const vm = require('node:vm');
const { html, mode, noFactory } = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const banners = [], inits = [], created = [];
const sb = {};
sb.window = sb;
sb.document = { readyState: 'complete', getElementById: () => null, createElement: () => ({ style: {} }),
  body: { appendChild: (el) => banners.push(el.textContent) }, addEventListener() {} };
sb.localStorage = { getItem: () => null };
sb.CommentLayer = { init: (o) => inits.push(o) };
const ok = () => ({ ready: Promise.resolve(), load: () => [], save: async () => {} });
const stores = {
  ok,
  noready: () => ({ load: () => [], save: async () => {} }),
  nosave: () => ({ ready: Promise.resolve(), load: () => [] }),
  noload: () => ({ ready: Promise.resolve(), save: async () => {} }),
  nostore: () => null,
  throws: () => { throw new Error('boom'); },
  rejects: () => ({ ready: Promise.reject(new Error('down')), load: () => [], save: async () => {} }),
};
if (!noFactory) sb.DeaiComments = { create: (cfg) => { created.push(cfg); return stores[mode](); } };
vm.createContext(sb);
for (const s of scripts) vm.runInContext(s, sb);
setTimeout(() => console.log(JSON.stringify({
  banners,
  inits: inits.map((i) => ({ projectId: i.projectId, version: i.version, storage: !!i.storage, audiences: i.audiences.map((a) => a.id) })),
  created: created.map((c) => ({ channel: c.channel, endpoint: c.endpoint, onChange: typeof c.onChange })),
})), 30);
"""

    def run_loader(self, mode, no_factory=False):
        import subprocess
        html = serve.inject_module_comment_layer('<html><body></body></html>', 'http://h/app/vendor', ['/api/module-client/m/a.js'],
                                                 {'channel': 'deai/s/t', 'endpoint': 'http://svc'}, version='3', audiences=True)
        r = subprocess.run(['node', '-e', self.HARNESS], input=json.dumps({'html': html, 'mode': mode, 'noFactory': no_factory}),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        return json.loads(r.stdout)

    def test_a_valid_store_boots_the_commenter_with_the_channel_version_and_tabs(self):
        for mode in ('ok', 'noready'):                                       # `ready` необовʼязковий
            out = self.run_loader(mode)
            self.assertEqual(out['banners'], [], mode)
            self.assertEqual(out['inits'], [{'projectId': 'deai/s/t', 'version': '3', 'storage': True,
                                             'audiences': ['local', 'project']}], mode)
            self.assertEqual(out['created'], [{'channel': 'deai/s/t', 'endpoint': 'http://svc', 'onChange': 'function'}], mode)

    def test_a_store_without_load_or_save_is_a_banner_not_a_dead_commenter(self):
        for mode in ('nosave', 'noload', 'nostore'):
            out = self.run_loader(mode)
            self.assertEqual(out['inits'], [], mode)
            self.assertEqual(len(out['banners']), 1, mode)
            self.assertIn('load/save', out['banners'][0], mode)

    def test_a_factory_that_throws_or_a_ready_that_rejects_is_a_banner_with_the_reason(self):
        out = self.run_loader('throws')
        self.assertEqual((out['inits'], len(out['banners'])), ([], 1))
        self.assertIn('boom', out['banners'][0])
        out = self.run_loader('rejects')
        self.assertEqual((out['inits'], len(out['banners'])), ([], 1))
        self.assertIn('down', out['banners'][0])

    def test_a_missing_adapter_factory_is_a_banner(self):
        out = self.run_loader('ok', no_factory=True)
        self.assertEqual((out['inits'], out['created'], len(out['banners'])), ([], [], 1))


class SingleSpaceResolutionTest(PagesEnv):
    """Простір вирішується ОДИН раз на запит: постачальник, конфіг і канал рахуються з одного запису (див. коментар у
    `_commented`), а не з трьох читань реєстру."""

    def spy(self):
        seen = {}
        real_p, real_c = dm.provider, dm.comments_client

        def p(role, space=None):
            seen['provider'] = space
            return real_p(role, space)

        def c(space, prov, ctx=None):          # 4b-2: необовʼязковий готовий `ctx` (ЛІГА — з конфігу установки)
            seen['client'] = space
            return real_c(space, prov, ctx)
        for name, fn in (('provider', p), ('comments_client', c)):
            patch = mock.patch.object(dm, name, fn)
            patch.start()
            self.addCleanup(patch.stop)
        return seen

    def test_the_page_uses_one_space_record_for_the_provider_and_the_config(self):
        self.enable(self.plain, 'http://127.0.0.1:4555')
        seen = self.spy()
        self.page('project')
        self.assertIsNotNone(seen['provider'])
        self.assertIs(seen['provider'], seen['client'])
        self.assertEqual(seen['client']['id'], self.plain['id'])

    def test_comment_config_uses_one_space_record_for_the_provider_and_the_config(self):
        self.enable(self.plain, 'http://127.0.0.1:4555')
        seen = self.spy()
        self.assertEqual(self.config('project')[0], 200)
        self.assertIsNotNone(seen['provider'])
        self.assertIs(seen['provider'], seen['client'])

    def test_a_league_page_resolves_the_provider_from_the_same_record_too(self):
        self.use(self.liga)
        seen = self.spy()
        self.page('project')
        self.assertEqual(seen['provider']['id'], self.liga['id'])

    def test_without_the_spaces_layer_the_hardcoded_path_is_asked_without_a_space(self):
        with mock.patch.object(serve.spaces, 'layer_on', return_value=False):
            seen = {}
            real = dm.provider

            def p(role, space=None):
                seen['provider'] = space
                return real(role, space)
            with mock.patch.object(dm, 'provider', p):
                self.assertEqual(serve.comments_provider({'id': 'legacy', 'path': '', 'integrations': True}), ('legacy', None))
        self.assertIsNone(seen['provider'])


if __name__ == '__main__':
    unittest.main()

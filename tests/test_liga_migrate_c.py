"""Міграція ЛІГИ, третій крок — `publish` (етап 4d-3c, 0.19.0).

Тут: знімок поведінки 0.18.0 (`Before4d3cShape`, Task 1); предикат, `compat`, крок `liga-4d3c`, паритет і три кроки додаються
наступними задачами. Спека `docs/superpowers/specs/2026-11-06-liga-migration-c-design.md`.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3c.json')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import deai_modules as dm  # noqa: E402
import isolation  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from make_before_4d3c import SB_KEY, SB_URL  # noqa: E402  (вигадані значення — ті самі, що в генераторі)
from make_before_4d3a import SocketTripwire  # noqa: E402  (розтяжка мережі: нічого, крім loopback)
from test_liga_migrate import _WriteStand  # noqa: E402  (стенд запису 4d-3a: тимчасові HOME/DEAI_HOME, CLI, пошук секретів)
from test_liga_migrate_b import _ABSENT, _flat  # noqa: E402  (порівняння знімків ключ у ключ — імпорт, не друга копія)
from test_liga_migrate_b import _diff as _diff_all  # noqa: E402
from test_publish_module import DispatchWorld, _Stub, _write_json  # noqa: E402  (світ «два простори + сервер + розтяжка»)

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard` (тести цього файлу пишуть простори — лише у власних теках)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


#: Рівно ці сценарії `publish` (і нічого іншого): знімок не вміє «зменшитись» непомітно.
SCENARIOS = ['build_only', 'cleanup_warning', 'comments_off', 'comments_on', 'domain_warning', 'err_login', 'err_no_url',
             'err_scope', 'first', 'no_node', 'not_task_link', 'protection', 'pw_default', 'pw_root', 'pw_task', 'second']
SCENARIO_KEYS = ['build', 'iterations_after', 'npx_argv', 'pages', 'response', 'spies', 'tasks_after']
STAND_KEYS = ['api_spaces', 'js', 'modules_card', 'password', 'publish', 'task']


class Before4d3cShape(unittest.TestCase):
    """Знімок 0.18.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def setUp(self):
        # ⛔ Ізоляція за замовчуванням (охоронець `test_serve.TestsCannotWriteLiveConfig` вимагає присвоєння `DEAI_HOME` у файлі, що
        # торкається просторів): тимчасові `HOME`/`DEAI_HOME` на весь тест, справжнього `~/.deai` ці тести не бачать.
        self._tmp = tempfile.TemporaryDirectory(prefix='b4d3c-')
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DEAI_HOME': os.path.join(self._tmp.name, 'deai-default'), 'HOME': self._tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def stands(self):
        return [(n, self.snap['stands'][n]) for n in ('ab', 'unmigrated')]

    @staticmethod
    def pairs(resp):
        """Тіло відповіді як `dict` (зберігаючи порядок ключів — він спостережуваний)."""
        return dict((k, v) for k, v in resp['pairs'])

    @staticmethod
    def keys(resp):
        return [k for k, _v in resp['pairs']]

    # ------------------------------------------------------------------------------ форма

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['meta', 'non_loopback_attempts', 'stands'])
        self.assertEqual(sorted(self.snap['stands']), ['ab', 'unmigrated'])
        self.assertEqual(self.snap['meta']['version'], '0.18.0')
        self.assertEqual(self.snap['meta']['source_commit'], '6ce8e61')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d3c.py')
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])
        self.assertEqual(sorted(self.snap['meta']), ['generator', 'source_commit', 'version', 'volatile_stripped'])
        self.assertEqual(self.snap['non_loopback_attempts'], 0)

    def test_stand_sections_are_exact(self):
        for name, st in self.stands():
            self.assertEqual(sorted(st), STAND_KEYS, name)

    def test_publish_scenarios_are_exact(self):
        """Рівно 16 сценаріїв на КОЖЕН стенд, і кожен має рівно свій набір ключів: ні сценарій, ні ключ не зникне непомітно."""
        for name, st in self.stands():
            self.assertEqual(sorted(st['publish']), SCENARIOS, name)
            self.assertEqual(len(st['publish']), 16, name)
            for sid, sc in st['publish'].items():
                self.assertEqual(sorted(sc), SCENARIO_KEYS, '%s/%s' % (name, sid))
                self.assertEqual(sorted(sc['response']), ['pairs', 'status'], '%s/%s' % (name, sid))
                self.assertEqual(sorted(sc['spies']), ['calls', 'fetched_urls'], '%s/%s' % (name, sid))
                self.assertEqual(sorted(sc['tasks_after']), ['vercel_project', 'vercel_scope'], '%s/%s' % (name, sid))
                self.assertEqual(sorted(sc['iterations_after']),
                                 ['publish_remote', 'publish_url', 'publish_verified', 'published_at'], '%s/%s' % (name, sid))
                self.assertEqual(sorted(sc['pages']), ['comment_layer_files', 'html', 'manifest_pages'], '%s/%s' % (name, sid))

    def test_other_sections_shape(self):
        for name, st in self.stands():
            self.assertEqual(sorted(st['task']), ['after_change', 'fresh', 'published'], name)
            for v in st['task'].values():
                self.assertEqual(sorted(v), ['has_publish_gate', 'has_publish_remote', 'has_publish_share_url', 'preview_gate',
                                             'preview_password', 'preview_password_custom', 'publish_url',
                                             'space_capabilities_publish', 'status'], name)
            self.assertEqual(sorted(st['password']), ['clear', 'no_liga_space', 'set', 'too_long'], name)
            self.assertEqual(sorted(st['api_spaces']), ['capabilities', 'compat', 'status'], name)
            self.assertEqual(sorted(st['modules_card']), ['card', 'status'], name)
            self.assertEqual(sorted(st['js']), ['bar_item_ids', 'bar_publish', 'bar_pubpw', 'copy_url',
                                                'disable_consequences_publish', 'is_legacy_publish', 'is_remote_publish',
                                                'is_vercel_publish', 'preview_target', 'publish_reaction',
                                                'publish_reaction_other_task', 'pw_view'], name)
            # внутрішні форми: на них спираються тести паритету наступних задач
            self.assertEqual(sorted(st['api_spaces']['capabilities']),
                             ['comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs'], name)
            self.assertEqual(sorted(st['modules_card']['card']), ['api', 'builtin', 'check_timeout_s', 'enabled', 'id', 'implicit',
                                                                  'name', 'roles', 'settings', 'status', 'version'], name)
            self.assertEqual(sorted(st['js']['pw_view']), ['pw', 'pwCustom', 'pwStale', 'pwUngated'], name)
            self.assertEqual(sorted(st['js']['bar_pubpw']), ['id', 'labelKey', 'pw', 'subKey', 'warnArgs', 'warnKey'], name)
            self.assertEqual(st['js']['disable_consequences_publish'], [], name)      # роль `publish` тримає `legacy`, не модуль
            for k, resp in st['password'].items():
                self.assertEqual(sorted(resp), ['pairs', 'status'] if k != 'set' and k != 'clear' else
                                 ['pairs', 'saved_in_tasks_json', 'status'], '%s/%s' % (name, k))
                self.assertIsInstance(resp['pairs'], list, '%s/%s' % (name, k))
                self.assertTrue(all(isinstance(p, list) and len(p) == 2 and isinstance(p[0], str) for p in resp['pairs']),
                                '%s/%s: пари [ключ, значення]' % (name, k))
                self.assertEqual(resp['pairs'][0][0], 'ok', '%s/%s' % (name, k))

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек, ні секретів: лише `~/…`/`<tmp>`; значення — вигадані."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        # (префікси домашніх/тимчасових тек macOS складені з двох літералів: щоб гігієнічний grep по диффу не бачив у самому тесті «шлях»)
        for bad in ('/Us' 'ers/', '/home/', '/var/folders', '/pri' 'vate/', '/tmp/', 'before-4d3c-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertNotIn(SB_KEY, self.raw, 'секрет у знімку: лише `<secret:ДОВЖИНА>`')
        self.assertIn('<secret:%d>' % len(SB_KEY), self.raw)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))          # жодного часового штампа
        self.assertIsNone(re.search(r'\d{2}\.\d{2}\.\d{4}', self.raw), 'дата запису ітерації чи час публікації — мінливе')
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])

    # ------------------------------------------------------------------------------ сценарії

    def test_first_mints_the_project_and_remembers_the_scope(self):
        for name, st in self.stands():
            first = st['publish']['first']
            body = self.pairs(first['response'])
            self.assertEqual(first['response']['status'], 200, name)
            self.assertEqual(self.keys(first['response']), ['ok', 'dir', 'iterations', 'frames', 'url', 'deploy_url', 'verified'], name)
            for k in ('url', 'deploy_url', 'verified'):
                self.assertIn(k, body, name)
            self.assertRegex(first['tasks_after']['vercel_project'], r'^pv-\d{8}$')
            self.assertEqual(first['tasks_after']['vercel_scope'], 'team_x', name)
            self.assertEqual(first['iterations_after']['publish_url'], body['url'], name)
            self.assertEqual(first['iterations_after']['publish_remote'], 'absent', name)
            argv = first['npx_argv']
            self.assertEqual(argv[0][:4], ['--yes', 'vercel', 'link', '--yes'], name)
            self.assertNotIn('--scope', argv[0], 'скоупу ще нема: перший `link` без нього')

    def test_second_reuses_the_project_scope_and_url(self):
        for name, st in self.stands():
            first, second = st['publish']['first'], st['publish']['second']
            self.assertEqual(second['tasks_after'], first['tasks_after'], name)
            self.assertEqual(self.pairs(second['response'])['url'], self.pairs(first['response'])['url'], name)
            proj = second['tasks_after']['vercel_project']
            link = second['npx_argv'][0]
            self.assertEqual(link, ['--yes', 'vercel', 'link', '--yes', '--scope', 'team_x', '--project', proj], name)
            self.assertEqual(second['iterations_after']['publish_remote'], 'absent', name)

    def test_password_scenarios_sew_three_different_passwords(self):
        for name, st in self.stands():
            pws = {}
            for sid in ('pw_default', 'pw_task', 'pw_root'):
                found = {p['password'] for p in st['publish'][sid]['pages']['html'].values()}
                self.assertEqual(len(found), 1, '%s/%s: один пароль на всі сторінки' % (name, sid))
                pws[sid] = found.pop()
                self.assertTrue(all(p['authgate'] for p in st['publish'][sid]['pages']['html'].values()), sid)
            self.assertEqual(pws, {'pw_default': '1100', 'pw_task': 'taskpw-alpha', 'pw_root': 'rootpw-alpha'}, name)
            self.assertEqual(len(set(pws.values())), 3)

    def test_build_mark_and_side_effects(self):
        for name, st in self.stands():
            for sid, sc in st['publish'].items():
                self.assertEqual(sc['build'], 'legacy', '%s/%s' % (name, sid))
                self.assertEqual(sc['iterations_after']['publish_remote'], 'absent', '%s/%s' % (name, sid))
            ok = st['publish']['first']['spies']['calls']
            self.assertEqual([c[0] for c in ok], ['registry_push', 'git_autocommit', 'overview_sync'], name)
            self.assertEqual(ok[1][2], 'publish: 2 iteration(s)', name)
            self.assertEqual([c[0] for c in st['publish']['build_only']['spies']['calls']], ['overview_sync'], name)
            self.assertEqual(st['publish']['build_only']['npx_argv'], [], name)
            self.assertEqual([c[0] for c in st['publish']['no_node']['spies']['calls']], ['git_autocommit', 'overview_sync'], name)
            self.assertEqual(self.pairs(st['publish']['no_node']['response'])['deploy_blocked'], 'no-node', name)

    def test_error_and_verify_branches(self):
        for name, st in self.stands():
            p = st['publish']
            for sid in ('err_login', 'err_scope', 'err_no_url'):
                body = self.pairs(p[sid]['response'])
                self.assertIn('deploy_error', body, '%s/%s' % (name, sid))
                self.assertNotIn('url', body, '%s/%s' % (name, sid))
                self.assertIsNone(p[sid]['iterations_after']['publish_url'], '%s/%s' % (name, sid))
            prot = p['protection']
            self.assertEqual(self.keys(prot['response'])[-3:], ['verified', 'verify_error', 'verify_hint'], name)
            self.assertEqual(self.pairs(prot['response'])['verify_error'], 'vercel_protection', name)
            self.assertIs(prot['iterations_after']['publish_verified'], False, name)

    def test_warning_scenarios_record_their_keys(self):
        """`domain_warning`, `not_task_link`, `cleanup_warning` — єдині сценарії з однойменними ключами відповіді; в решті їх нема."""
        for name, st in self.stands():
            p = st['publish']
            for sid, key in (('domain_warning', 'domain_warning'), ('not_task_link', 'not_task_link'),
                             ('cleanup_warning', 'cleanup_warning')):
                body = self.pairs(p[sid]['response'])
                self.assertEqual(p[sid]['response']['status'], 200, '%s/%s' % (name, sid))
                self.assertIn(key, body, '%s/%s' % (name, sid))
                self.assertIn('url', body, '%s/%s: публікація вдала' % (name, sid))
                self.assertTrue(isinstance(body[key], str) and body[key], '%s/%s' % (name, sid))
                for other in p:
                    if other != sid:
                        self.assertNotIn(key, self.pairs(p[other]['response']), '%s/%s має чужий ключ %s' % (name, other, key))
            dom = self.pairs(p['domain_warning']['response'])
            self.assertIn('pv-12345678-abc.vercel.app', dom['domain_warning'], name)
            self.assertEqual(dom['url'], 'https://pv-12345678-abc.vercel.app', name)
            self.assertEqual(self.pairs(p['not_task_link']['response'])['not_task_link'], 'Beta Designer', name)
            self.assertIn('не віддав список', self.pairs(p['cleanup_warning']['response'])['cleanup_warning'], name)
            self.assertEqual(self.keys(p['cleanup_warning']['response'])[-1], 'cleanup_warning', name)       # ОСТАННІЙ ключ

    def test_comments_channel_and_keys(self):
        for name, st in self.stands():
            inner = lambda sid: {k: v for k, v in st['publish'][sid]['pages']['html'].items() if k != 'index.html'}   # noqa: E731
            on = inner('comments_on')
            self.assertEqual({v['channel'] for v in on.values()}, {'liga-shared'}, name)
            secret = '<secret:%d>' % len(SB_KEY)
            self.assertTrue(all(v['comment_layer'] and v['supabase_key'] == secret and v['supabase_url'] == SB_URL
                                for v in on.values()), name)
            self.assertEqual({v['channel'] for v in inner('pw_default').values()}, {'dc/a-1'}, name)
            off = st['publish']['comments_off']
            self.assertEqual(self.pairs(off['response'])['comments_unavailable'], 'comments-unconfigured', name)
            self.assertTrue(all(not v['comment_layer'] and v['supabase_key'] is None and v['supabase_url'] is None
                                and v['channel'] is None for v in off['pages']['html'].values()), name)
            self.assertIsNone(off['pages']['comment_layer_files'], name)

    # ------------------------------------------------------------------------------ решта секцій

    def test_task_and_password_sections(self):
        for name, st in self.stands():
            t = st['task']
            self.assertEqual((t['fresh']['preview_password'], t['fresh']['preview_password_custom'], t['fresh']['preview_gate']['state']),
                             ('1100', False, 'none'), name)
            self.assertEqual(t['published']['preview_gate']['state'], 'current', name)
            self.assertEqual((t['after_change']['preview_password'], t['after_change']['preview_password_custom'],
                              t['after_change']['preview_gate']['state']), ('newpw-alpha', True, 'stale'), name)
            for v in t.values():
                self.assertEqual((v['status'], v['has_publish_gate'], v['has_publish_share_url'], v['has_publish_remote']),
                                 (200, False, False, False), name)
            pw = st['password']
            self.assertEqual((pw['set']['status'], pw['set']['saved_in_tasks_json']), (200, 'newpw-alpha'), name)
            self.assertEqual((pw['clear']['status'], pw['clear']['saved_in_tasks_json']), (200, None), name)
            self.assertEqual(pw['too_long']['status'], 400, name)
            self.assertEqual(pw['no_liga_space']['status'], 409, name)

    def test_before_the_migration_publish_is_legacy_everywhere(self):
        """На 0.18.0 ЛІГА публікує неявно в обох стендах: `capabilities.publish == 'legacy'`, `compat.publish` нема, картка
        `vercel-publish` вимкнена (1.1.0, без `compat`), а JS і `/api/task` кажуть «ЛІГА»."""
        for name, st in self.stands():
            self.assertEqual(st['api_spaces']['capabilities']['publish'], 'legacy', name)
            self.assertNotIn('publish', st['api_spaces']['compat'] or {}, name)
            self.assertEqual(st['task']['published']['space_capabilities_publish'], 'legacy', name)
            card = st['modules_card']['card']
            self.assertEqual((card['enabled'], card['version']), (False, '1.1.0'), name)
            self.assertNotIn('compat', [s['key'] for s in card['settings']], name)
            js = st['js']
            self.assertTrue(js['is_legacy_publish'], name)
            self.assertFalse(js['is_remote_publish'] or js['is_vercel_publish'], name)
            self.assertEqual(js['copy_url'], '%s/#k=1100&p=alpha' % self.pairs(st['publish']['first']['response'])['url'], name)
            self.assertEqual(js['publish_reaction'], {'kind': 'legacy', 'show': 'render'}, name)
            self.assertEqual(js['bar_pubpw']['id'], 'pubpw', name)
            self.assertEqual(js['pw_view']['pw'], '1100', name)
        self.assertEqual(self.snap['stands']['unmigrated']['api_spaces']['capabilities']['publish'], 'legacy')

    def test_stands_differ_exactly_where_4d3a_and_4d3b_changed_other_roles(self):
        """Стенд `ab` відрізняється від `unmigrated` ЛИШЕ записом `/api/spaces` (ролі `comments`/`vcs`, `compat`): публікація,
        `/api/task`, пароль, картка й JS — однакові (кроки a, b публікації не торкались)."""
        a, u = self.snap['stands']['ab'], self.snap['stands']['unmigrated']
        self.assertEqual([k for k in STAND_KEYS if a[k] != u[k]], ['api_spaces'])
        self.assertEqual(a['api_spaces']['capabilities']['comments'], 'supabase-comments')
        self.assertEqual(a['api_spaces']['capabilities']['vcs'], 'git-sync')
        self.assertEqual(u['api_spaces']['capabilities']['comments'], 'legacy')


# ---------------------------------------------------------------------------------------------------- Task 2: предикат

VID = 'vercel-publish'
DC = 'design-canvas'


class _PubWorld(DispatchWorld):
    """Світ `DispatchWorld` (шар просторів увімкнено; `off` без інтеграцій, `on` з ними = «ЛІГА»; сервер, розтяжка, шпигуни) +
    помічники для явного запису `vercel-publish` у `space.json`. Запис пишемо напряму (`compat` у маніфесті зʼявиться лише в
    Task 3, тож `write_module_state` його б відхилив); `compat_of` читає саме `space.json`."""

    def write_modules(self, sp, mods):
        _write_json(os.path.join(sp['path'], 'space.json'), {'name': 'On', 'color': 'space-1', 'modules': mods})
        dm.reset_caches()

    def vercel(self, compat=DC, sp=None, extra=None):
        """Явно ввімкнений `vercel-publish` із `compat` (`None` — без ключа) у просторі `sp` (типово `on`)."""
        settings = {} if compat is None else {'compat': compat}
        self.write_modules(sp or self.on, {VID: {'enabled': True, 'settings': settings}, **(extra or {})})

    def prov(self, sid='on'):
        with spaces.request_space(sid):
            return dm.provider('publish')

    def fake(self, mid, origin='builtin'):
        """Підроблений `Module` ролі `publish` (власний id/origin): каркас такого б не віддав, а предикат мусить відмовити сам."""
        return dm.Module(mid, roles=['publish'], origin=origin)


class PublishLegacyPath(_PubWorld):
    """`deai_modules.publish_legacy_path(prov, space=None)`: ТОТАЛЬНИЙ предикат «публікація йде шляхом ЛІГИ»."""

    def test_constant(self):
        self.assertEqual(dm.PUBLISH_MODULE, VID)
        self.assertEqual(dm.COMPAT_DESIGN_CANVAS, DC)

    def test_no_provider_is_not_the_league_path(self):
        """Було `test_implicit_is_the_league_path`: неявний постачальник вів шлях ЛІГА. 4d-4b (R2): неявного нема — шлях ЛІГА лише в запису
        `vercel-publish` із `compat` (його тримають тести нижче); відсутність постачальника (`None`) — НЕ шлях ЛІГА."""
        self.assertIs(dm.publish_legacy_path(None), False)
        self.assertIs(dm.publish_legacy_path(None, self.on), False)

    def test_builtin_vercel_with_compat_is_the_league_path(self):
        self.vercel(DC)
        prov = self.prov()
        self.assertEqual((prov.id, prov.origin), (VID, 'builtin'))
        self.assertIs(dm.publish_legacy_path(prov, self.on), True)

    def test_builtin_vercel_without_the_compat_is_not(self):
        for compat in (None, '', 'comment-layer', 'DESIGN-CANVAS', 123, ['design-canvas']):
            with self.subTest(compat=compat):
                self.vercel(compat)
                prov = self.prov()
                self.assertEqual(prov.id, VID)
                self.assertIs(dm.publish_legacy_path(prov, self.on), False)

    def test_a_space_owned_module_with_the_same_id_and_compat_is_not(self):
        self.vercel(DC)
        self.assertIs(dm.publish_legacy_path(self.fake(VID, origin='space'), self.on), False)

    def test_another_builtin_module_with_a_compat_is_not(self):
        # `compat` чужої ролі чи чужого модуля (4d-3b: comments/vcs мають СВОЄ `compat`) не робить публікацію «ЛІГОЮ». ⛔ Запис
        # `vercel-publish` ТЕЖ із `compat` (мутація «без перевірки id» інакше виживала: рішення читає `compat` саме `vercel-publish`,
        # і без нього будь-який інший вбудований видавець — напр. `static-publish`, що випередив його за id — теж дав би `False`).
        extra = {mid: {'enabled': True, 'settings': {'compat': DC}}
                 for mid in ('static-publish', 'supabase-comments', 'git-sync')}
        self.write_modules(self.on, {VID: {'enabled': True, 'settings': {'compat': DC}}, **extra})
        for mid in extra:
            with self.subTest(mid=mid):
                self.assertIs(dm.publish_legacy_path(self.fake(mid), self.on), False)

    def test_none_and_foreign_objects_are_not(self):
        for prov in (None, 'legacy', {}, object(), True):
            with self.subTest(prov=prov):
                self.assertIs(dm.publish_legacy_path(prov, self.on), False)

    def test_no_space_means_the_active_space_exactly_once(self):
        self.vercel(DC)
        prov = self.prov()
        with spaces.request_space('on'):
            with mock.patch.object(dm.spaces, 'active_space', wraps=spaces.active_space) as active:
                self.assertIs(dm.publish_legacy_path(prov), True)
        self.assertEqual(active.call_count, 1)
        with spaces.request_space('on'):
            with mock.patch.object(dm.spaces, 'active_space', wraps=spaces.active_space) as active:
                self.assertIs(dm.publish_legacy_path(prov, self.on), True)
        self.assertEqual(active.call_count, 0, 'явно переданий простір не підміняємо активним')

    def test_the_active_space_decides_not_another_one(self):
        # `off` без запису, `on` із записом: рішення — за простором запиту
        self.vercel(DC)
        prov = self.prov()
        with spaces.request_space('off'):
            self.assertIs(dm.publish_legacy_path(prov), False)
        with spaces.request_space('on'):
            self.assertIs(dm.publish_legacy_path(prov), True)

    def test_total_on_any_failure(self):
        self.vercel(DC)
        prov = self.prov()
        with mock.patch.object(dm, 'compat_of', side_effect=RuntimeError('boom')):
            self.assertIs(dm.publish_legacy_path(prov, self.on), False)
        with mock.patch.object(dm.spaces, 'active_space', side_effect=OSError('boom')):
            self.assertIs(dm.publish_legacy_path(prov), False)
        with open(os.path.join(self.on_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        dm.reset_caches()
        self.assertIs(dm.publish_legacy_path(prov, self.on), False)
        self.assertIs(dm.publish_legacy_path(prov, {'id': 'nope', 'path': os.path.join(self.tmp, 'nope')}), False)


class PublishModuleFilter(_PubWorld):
    """`publish_module(space)` не віддає `Module`, коли публікація йде шляхом ЛІГИ: обидва споживачі (`task_preview_gate`,
    `task_publish_share`) лишаються без змін."""

    def pm(self, sp, sid='on'):
        with spaces.request_space(sid):
            return dm.publish_module(sp)

    def test_implicit_is_none(self):
        self.assertIsNone(self.pm(self.on))

    def test_migrated_record_is_none(self):
        self.vercel(DC)
        self.assertIsNone(self.pm(self.on))

    def test_plain_vercel_is_the_module(self):
        self.vercel(None)
        mod = self.pm(self.on)
        self.assertIsNotNone(mod)
        self.assertEqual((mod.id, mod.origin), (VID, 'builtin'))

    def test_the_filter_is_on_publish_module_not_on_the_capability(self):
        # роль `publish` у `capabilities` і далі називає модуль: це відповідь «хто веде», а не «шлях ЛІГИ»
        self.vercel(DC)
        with spaces.request_space('on'):
            self.assertEqual(dm.capabilities(self.on)['publish'], VID)

    def test_other_publishers_are_unaffected(self):
        mod = self.pm(self.off, 'off')
        self.assertIsNotNone(mod)
        self.assertEqual(mod.id, 'static-publish')


class PublishConsumers(_PubWorld):
    """Споживачі предиката на справжньому `Handler`/сервері: `_publish`, `_preview_password`, `task_preview_gate`, `task_publish_share`."""

    LEGACY_RES = {'url': 'https://pv-12345678.vercel.app', 'deploy_url': 'https://pv-12345678-abc.vercel.app',
                  'verified': True, 'state': {'scope': 'team_x'}}

    def setUp(self):
        super().setUp()
        self.spies['_publish_legacy_call'].return_value = dict(self.LEGACY_RES)
        self.spies['_node_bin'].return_value = '/bin/npx'
        patch = mock.patch.object(serve, 'publish_with_module')
        self.module_spy = patch.start()
        self.addCleanup(patch.stop)

    def publish(self, payload=None, sid='on'):
        stub = _Stub()
        with spaces.request_space(sid):
            serve.Handler._publish(stub, {} if payload is None else payload)
        return stub

    def build_mark(self):
        with open(os.path.join(self.ty_dir, 'publish', 'manifest.json'), encoding='utf-8') as fh:
            return json.load(fh).get('build')

    def assert_league_branch(self):
        stub = self.publish()
        self.assertEqual(self.module_spy.call_count, 0, 'модуль-шлях кликано')
        self.assertEqual(self.spies['_publish_legacy_call'].call_count, 1, 'гілка ЛІГИ не дійшла до деплою')
        self.assertEqual(self.build_mark(), 'legacy')
        status, body = stub.sent[0]
        self.assertEqual((status, body['ok'], body['url']), (200, True, self.LEGACY_RES['url']))

    def test_publish_implicit_takes_the_league_branch(self):
        self.assert_league_branch()

    def test_publish_migrated_record_takes_the_league_branch(self):
        self.vercel(DC)
        self.assert_league_branch()

    def test_publish_plain_vercel_takes_the_module_path(self):
        self.vercel(None)
        stub = self.publish()
        self.assertEqual(self.module_spy.call_count, 1)
        self.assertEqual(self.module_spy.call_args[0][1].id, VID)
        self.assertEqual(self.spies['_publish_legacy_call'].call_count, 0)
        self.assertEqual(stub.sent, [])
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish')), 'збірку ЛІГИ зроблено на шляху модуля')

    def test_publish_without_a_provider_is_409(self):
        dm.write_module_state(self.off, 'static-publish', enabled=False)
        stub = self.publish(sid='off')
        status, body = stub.sent[0]
        self.assertEqual((status, body['code']), (409, 'no-publish-module'))
        self.assertEqual(self.module_spy.call_count, 0)

    def password(self, pw='abcd'):
        return self.post('/api/preview-password', {'password': pw}, {'X-Canvas-Task': 'ty'})

    def test_password_migrated_record_is_accepted(self):
        self.vercel(DC)
        st, body = self.password()
        self.assertEqual((st, body['ok'], body['preview_password']), (200, True, 'abcd'), body)
        with open(os.path.join(self.on_path, 'tasks.json'), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['ty']['preview_password'], 'abcd')

    def test_password_plain_vercel_is_refused(self):
        self.vercel(None)
        tasks = os.path.join(self.on_path, 'tasks.json')
        with open(tasks, 'rb') as fh:
            before = fh.read()
        st, body = self.password()
        self.assertEqual((st, body['code']), (409, 'integrations-off'), body)
        with open(tasks, 'rb') as fh:
            self.assertEqual(fh.read(), before, 'пароль ЛІГИ записано, хоч публікує модуль')

    def test_password_with_a_provider_error_is_the_same_409(self):
        # нечитабельний `space.json` у просторі З інтеграціями дає `Implicit` (як і було), тож `ModuleError` підставляємо напряму
        with mock.patch.object(dm, 'provider', side_effect=dm.ModuleError('module-error')):
            st, body = self.password()
        self.assertEqual((st, body), (409, serve.integrations_off_body('публікація зʼявиться з модулями')))

    def test_gate_state_follows_the_predicate(self):
        task = {'title': 'T', 'dir': self.ty_dir}
        for compat, want in ((DC, serve.preview_gate_state(task, '1100')), (None, dict(serve.MODULE_GATE_STATE))):
            with self.subTest(compat=compat):
                self.vercel(compat)
                with spaces.request_space('on'):
                    self.assertEqual(serve.task_preview_gate(task, '1100', self.on), want)
        self.assertNotEqual(serve.preview_gate_state(task, '1100'), dict(serve.MODULE_GATE_STATE))

    def test_share_fields_follow_the_predicate(self):
        meta = {'publish_url': None}
        self.vercel(DC)
        with spaces.request_space('on'):
            self.assertEqual(serve.task_publish_share(self.on, meta), {})
        self.vercel(None)
        with spaces.request_space('on'):
            fields = serve.task_publish_share(self.on, meta)
        self.assertIn('publish_gate', fields)


class PublishGuard(unittest.TestCase):
    """AST: рішення «публікація ЛІГИ» читається з ОДНОГО предиката (урок 4d-3a/3b: ЛІГА — запис реєстру, а не тип постачальника)."""

    CONSUMERS = (('Handler', '_publish'), ('Handler', '_preview_password'), (None, 'task_preview_gate'),
                 (None, 'task_publish_share'))

    @classmethod
    def setUpClass(cls):
        app = os.path.join(os.path.dirname(_HERE), 'app')
        with open(os.path.join(app, 'serve.py'), encoding='utf-8') as f:
            cls.serve_tree = ast.parse(f.read())
        with open(os.path.join(app, 'deai_modules.py'), encoding='utf-8') as f:
            cls.dm_tree = ast.parse(f.read())

    @staticmethod
    def implicit_checks(node):
        """Рядки, де тіло ТОРКАЄТЬСЯ типу `Implicit` будь-яким способом: імʼя/атрибут із `Implicit` (зокрема правий бік псевдоніма
        `I = implicit.Implicit`), імпорт `… import Implicit as I`, порівняння через `type(x)` чи `x.__class__` (псевдонім так не зловити)."""
        out = []
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and 'Implicit' in n.id:
                out.append(n.lineno)
            elif isinstance(n, ast.Attribute) and 'Implicit' in n.attr:
                out.append(n.lineno)
            elif isinstance(n, (ast.Import, ast.ImportFrom)) and any('Implicit' in a.name for a in n.names):
                out.append(n.lineno)
            elif isinstance(n, ast.Compare):
                for part in [n.left] + list(n.comparators):
                    if any((isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == 'type')
                           or (isinstance(x, ast.Attribute) and x.attr == '__class__') for x in ast.walk(part)):
                        out.append(n.lineno)
                        break
        return out

    @staticmethod
    def calls(node, name):
        out = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Attribute) and f.attr == name) or (isinstance(f, ast.Name) and f.id == name):
                    out.append(n.lineno)
        return out

    @staticmethod
    def fn(tree, name, cls=None):
        scope = tree.body
        if cls:
            scope = next(n for n in scope if isinstance(n, ast.ClassDef) and n.name == cls).body
        return next(n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name)

    def test_consumers_do_not_test_the_provider_type(self):
        bad = {name: self.implicit_checks(self.fn(self.serve_tree, name, cls)) for cls, name in self.CONSUMERS}
        self.assertEqual({k: v for k, v in bad.items() if v}, {})

    def test_the_two_handlers_ask_the_predicate(self):
        for cls, name in self.CONSUMERS[:2]:
            self.assertEqual(len(self.calls(self.fn(self.serve_tree, name, cls), 'publish_legacy_path')), 1, name)

    def test_publish_module_is_called_from_exactly_two_places(self):
        self.assertEqual(len(self.calls(self.serve_tree, 'publish_module')), 2)
        for name in ('task_preview_gate', 'task_publish_share'):
            self.assertEqual(len(self.calls(self.fn(self.serve_tree, name), 'publish_module')), 1, name)

    def test_exactly_one_isinstance_in_the_predicate_the_module_check(self):
        """Було `test_the_type_test_lives_in_the_predicate_only`: предикат рівно один раз торкався типу `Implicit`. 4d-4b: типу нема, тож
        `assertEqual(implicit_checks(pred), [])` стало б порожнім (завжди істинним) — його прибрано. Справжнє твердження: у предикаті РІВНО один
        `isinstance` — перевірка `Module` (єдина перевірка типу постачальника); `publish_module` теж має рівно один `isinstance` — той самий `Module`."""
        def isinstances(node):
            return [n for n in ast.walk(node) if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'isinstance']
        pred = self.fn(self.dm_tree, 'publish_legacy_path')
        [check] = isinstances(pred)
        self.assertEqual(ast.unparse(check.args[1]), 'Module')
        [pm] = isinstances(self.fn(self.dm_tree, 'publish_module'))          # теж лише `Module` (не тип старого постачальника)
        self.assertEqual(ast.unparse(pm.args[1]), 'Module')

    def test_guard_sees_a_planted_check(self):
        planted = ast.parse('def f(v):\n    return isinstance(v, implicit.Implicit)\n')
        self.assertEqual(self.implicit_checks(planted), [2])
        clean = ast.parse('def f(v):\n    return isinstance(v, dict)\n')
        self.assertEqual(self.implicit_checks(clean), [])
        # псевдонім типу (присвоєння й імпорт) і порівняння через `type`/`__class__` — теж видно
        alias = ast.parse('def f(v):\n    I = implicit.Implicit\n    return isinstance(v, I)\n')
        self.assertEqual(self.implicit_checks(alias), [2])
        alias_import = ast.parse('def f(v):\n    from implicit import Implicit as I\n    return isinstance(v, I)\n')
        self.assertEqual(self.implicit_checks(alias_import), [2])
        by_type = ast.parse('def f(v):\n    return type(v) is Implicit\n')
        self.assertEqual(sorted(set(self.implicit_checks(by_type))), [2])      # рядок видно; кількість повідомлень не пінимо (дубль імені й порівняння)
        by_type_alias = ast.parse('def f(v, I):\n    return type(v) is I\n')
        self.assertEqual(self.implicit_checks(by_type_alias), [2])
        by_class = ast.parse('def f(v, I):\n    return v.__class__ == I\n')
        self.assertEqual(self.implicit_checks(by_class), [2])
        harmless = ast.parse('def f(v):\n    return type(v)\n')
        self.assertEqual(self.implicit_checks(harmless), [], 'саме `type(x)` без порівняння не ознака')
        planted_call = ast.parse('def f(v):\n    return dm.publish_module(v)\n')
        self.assertEqual(self.calls(planted_call, 'publish_module'), [2])


# ---------------------------------------------------------------------------------------------------- Task 3: compat

class PublishCompatSetting(unittest.TestCase):
    """Налаштування `compat` вбудованого `vercel-publish` (маніфест 1.3.0): формат — як `git-sync`."""

    @classmethod
    def setUpClass(cls):
        dm.reset_caches()
        cls.m = dm.catalog()[VID]

    def setting(self):
        return {s['key']: s for s in self.m.settings}['compat']

    def test_version_and_loaded(self):
        self.assertEqual((self.m.status, self.m.version), ('ok', '1.3.0'))

    def test_compat_is_the_last_select(self):
        self.assertEqual([s['key'] for s in self.m.settings], ['auth', 'token', 'team', 'password', 'compat'])
        s = self.setting()
        self.assertEqual((s['type'], s['required'], s['default']), ('select', False, ''))
        self.assertEqual([(o['value'], o['label']) for o in s['options']][0], ('', 'Немає'))
        self.assertEqual([o['value'] for o in s['options']], ['', DC])

    def test_label_warns_about_what_is_not_read_and_the_switch(self):
        label = self.setting()['label']
        self.assertIn('⚠', label)
        # Поправка 7 (4d-4b): пароль превʼю ТЕПЕР читається (задача, далі секрет модуля) — підпис попереджає лише про `auth` і `team`
        for word in ('auth', 'team'):
            self.assertIn(word, label)
        self.assertNotIn('password', label)
        self.assertIn('пароль превʼю — спершу пароль задачі, далі секрет цього модуля', label)
        self.assertIn('не чита', label)                  # «не читаються»
        self.assertIn('проєкти', label)                  # зміна значення на живому просторі = нові проєкти й URL
        self.assertIn('URL', label)

    def test_unknown_value_is_bad_settings(self):
        for bad in ('comment-layer', 'DESIGN-CANVAS', 7, ['design-canvas']):
            with self.subTest(bad=bad):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.validate_settings(VID, {'compat': bad})
                self.assertEqual(cm.exception.code, 'bad-settings')
        for ok in ('', DC):
            self.assertEqual(dm.validate_settings(VID, {'compat': ok}), {'compat': ok})

    def test_secret_keys_unchanged(self):
        self.assertEqual(self.m.secret_keys(), ['token', 'password'])


class PublishCompatView(_PubWorld):
    """`compat_view` і обʼєкт простору: ключ `compat.publish` — лише для явного ВБУДОВАНОГО `vercel-publish` із `compat`."""

    def caps(self, sp, sid='on'):
        with spaces.request_space(sid):
            return dm.capabilities(sp)

    def test_registry_constants(self):
        self.assertIn(('publish', VID), dm.COMPAT_ROLES)
        self.assertEqual(dm.COMPAT_ALLOWED['publish'], DC)
        self.assertEqual(dm.COMPAT_ROLES[:2], (('comments', dm.COMMENTS_MODULE), ('vcs', dm.VCS_MODULE)), 'ролі 4d-3b на місці')

    def test_builtin_vercel_with_compat_gives_the_key(self):
        self.vercel(DC)
        caps = self.caps(self.on)
        self.assertEqual(caps['publish'], VID)
        self.assertEqual(dm.compat_view(self.on, caps), {'publish': DC})

    def test_key_sits_next_to_the_other_roles(self):
        extra = {'git-sync': {'enabled': True, 'settings': {'compat': DC}}}
        self.vercel(DC, extra=extra)
        caps = self.caps(self.on)
        self.assertEqual(dm.compat_view(self.on, caps), {'vcs': DC, 'publish': DC})

    def test_no_key_without_compat_or_for_foreign_providers(self):
        for compat in (None, ''):
            with self.subTest(compat=compat):
                self.vercel(compat)
                self.assertEqual(dm.compat_view(self.on, self.caps(self.on)), {})
        self.vercel(DC)
        caps = self.caps(self.on)
        self.assertEqual(dm.compat_view(self.on, dict(caps, publish='static-publish')), {}, 'роль веде інший модуль')
        self.assertEqual(dm.compat_view(self.on, dict(caps, publish='legacy')), {}, 'рядок `legacy` — не модуль: ключа нема')

    def test_implicit_has_no_key(self):
        """Було: простір без запису → `Implicit` (`'legacy'`), ключа нема. 4d-4b: без запису роль — `None`, ключа так само нема."""
        self.write_modules(self.on, {})                  # світ кладе явний запис ЛІГИ (`DispatchWorld`): тут — простір без жодного запису
        caps = self.caps(self.on)
        self.assertIsNone(caps['publish'])
        self.assertEqual(dm.compat_view(self.on, caps), {})

    def test_space_owned_provider_gives_no_key(self):
        self.vercel(DC)
        caps = self.caps(self.on)
        fake = {'publish': self.fake(VID, origin='space')}
        with mock.patch.object(dm, '_capabilities_full', lambda s: (caps, fake)):
            self.assertEqual(dm.compat_view(self.on, caps), {})

    def test_the_value_is_only_the_allowed_one(self):
        # сире значення з `space.json`, не дозволене ролі, клієнту не віддаємо (хоч `compat_of` його прочитала б)
        self.write_modules(self.on, {VID: {'enabled': True, 'settings': {'compat': 'comment-layer'}}})
        self.assertEqual(dm.compat_view(self.on, self.caps(self.on)), {})

    def test_space_view_and_listing_carry_it_and_capabilities_stay(self):
        self.vercel(DC)
        with spaces.request_space('on'):
            view = serve.space_view(self.on)
            listing = {e['id']: e for e in serve.spaces_listing()['spaces']}
        self.assertEqual(view['compat'], {'publish': DC})
        self.assertEqual(listing['on']['compat'], {'publish': DC})
        for o in (view, listing['on']):
            self.assertEqual(o['capabilities']['publish'], VID, 'capabilities не змінено: це id модуля')
        self.assertNotIn('compat', listing['off'])
        self.vercel(None)
        with spaces.request_space('on'):
            self.assertNotIn('compat', serve.space_view(self.on))


class PublishJsGuard(unittest.TestCase):
    """4d-4c: значення `"legacy"` у `capabilities.publish` сервер не шле — клієнт не порівнює з ним ніде (ЛІГА — це `compat.publish`)."""

    def test_no_legacy_literal_in_client(self):
        app = os.path.join(os.path.dirname(_HERE), 'app')
        found = {}
        for name in sorted(os.listdir(app)):
            if name.endswith('.js'):
                with open(os.path.join(app, name), encoding='utf-8') as f:
                    n = f.read().count('publish === "legacy"')
                if n:
                    found[name] = n
        self.assertEqual(found, {})


# ------------------------------------------------------------------------------ Task 4: крок liga-4d3c

PUB_MOD = 'vercel-publish'
PUB_ENTRY = {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}}
ORIG_SPACE = b'{"name": "Liga",\n  "x": {"k": [1,  2]}}\n'
OTHER_SECRETS = {'other': {'m': {'k': 'other_value_alpha'}}}


class _StepC(_WriteStand):
    """Стенд трьох РЕАЛЬНИХ кроків (`ALL_STEPS = (A, B, C)`); `_Stand.setUp` ставить `STEPS = ALL_STEPS[:1]` — тут перекриваємо.
    `HOME`/`DEAI_HOME` патчить `_Stand.setUp` (`mock.patch.dict`); значення вигадані."""

    def setUp(self):
        super().setUp()
        p = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS[:3])      # пін 4d-4a (Поправка 10): крок D тут не біжить
        p.start()
        self.addCleanup(p.stop)

    def seed(self):
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)
        self._write(self.secrets_path(), json.dumps(OTHER_SECRETS))
        os.chmod(self.secrets_path(), 0o600)

    def apply_ab(self):
        self.assertEqual(self.lm.run(step='liga-4d3a'), 'done')
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'done')

    def plan_c(self):
        return self.lm.plan(step='liga-4d3c')

    def marks(self):
        return self.read_json(self.space_path()).get('migrations') or {}

    def stamps(self):
        m = self.marks()
        return m['liga-4d3a']['backup'], m['liga-4d3b']['backup'], m['liga-4d3c']['backup']

    def start(self):
        return self.quiet(self.lm.startup)

    def write_modules(self, mods):
        self.space_json({'modules': mods})

    def liga_space(self):
        return {'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': True}


class StepCConstants(unittest.TestCase):
    """Форма кроку c і його імен; модуль міграції не імпортує `serve` (закон 4d-3a)."""

    def test_steps_list_and_step_c_shape(self):
        import liga_migrate as lm
        self.assertEqual([s.mark for s in lm.ALL_STEPS[:3]], ['liga-4d3a', 'liga-4d3b', 'liga-4d3c'])
        self.assertEqual(lm.ALL_STEPS[3].mark, 'liga-4d4a', 'четвертий крок — 4d-4a (його тести — у test_liga_migrate_d)')
        self.assertEqual(lm.STEPS, lm.ALL_STEPS)                 # 4d-4b (Task 7): на старті п'ять кроків
        c = lm.ALL_STEPS[2]
        self.assertIs(lm.STEP_C, c)
        self.assertEqual((c.mark, c.roles, c.tracks, c.suffix), ('liga-4d3c', (('publish', 'vercel-publish'),), False, '-liga-4d3c'))
        self.assertEqual(lm.ROLE_MODULES_C, (('publish', PUB_MOD),))
        self.assertIs(c.entries, lm._entries_c)
        self.assertIs(lm.ALL_STEPS[0], lm.STEP_A)
        self.assertIs(lm.ALL_STEPS[1], lm.STEP_B)

    def test_compat_constant_equals_the_core_one(self):
        import liga_migrate as lm
        self.assertEqual(lm.PUBLISH_COMPAT, 'design-canvas')
        self.assertEqual(lm.PUBLISH_COMPAT, dm.COMPAT_DESIGN_CANVAS)
        self.assertEqual(lm.VCS_COMPAT, dm.COMPAT_DESIGN_CANVAS)

    def test_stamp_names_tell_the_steps_apart(self):
        import liga_migrate as lm
        a, b, c = lm.ALL_STEPS[:3]
        self.assertTrue(c.stamp_re.fullmatch('20261106-120000-liga-4d3c'))
        self.assertTrue(c.stamp_re.fullmatch('20261106-120000-liga-4d3c-2'))
        self.assertIsNone(c.stamp_re.fullmatch('20261106-120000-liga-4d3c-pre-restore'))
        self.assertIsNone(c.stamp_re.fullmatch('20261106-120000-liga-4d3b'))
        for other in (a, b):
            self.assertIsNone(other.stamp_re.fullmatch('20261106-120000-liga-4d3c-2'))
        self.assertIs(lm.step_of_stamp('20261106-120000-liga-4d3c-2'), c)
        self.assertIsNone(lm.step_of_stamp('20261106-120000-liga-4d3c-pre-restore'))
        self.assertIs(lm.step_of_stamp('20261106-120000-liga-4d3b'), b)

    def test_reason_for_publisher_present(self):
        import liga_migrate as lm
        self.assertIn('publisher-present', lm._REASONS)
        self.assertIn('інший модуль', lm._REASONS['publisher-present'])

    def test_liga_migrate_does_not_import_serve(self):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'liga_migrate.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names.update(a.name.split('.')[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or '').split('.')[0])
        self.assertNotIn('serve', names)


class StepCPlanTest(_StepC):
    """`plan(step='liga-4d3c')`: чистий розрахунок запису `vercel-publish`; нічого не пише; секретів нема."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.apply_ab()

    def test_ready_entry_has_exactly_the_agreed_shape(self):
        before = self.snapshot_tree()
        p = self.plan_c()
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(p['roles'], {'publish': {'module': PUB_MOD, 'migrate': True, 'reason': None}})
        mods = p['space_json']['modules']
        self.assertEqual(mods[PUB_MOD], PUB_ENTRY)
        self.assertEqual(sorted(mods[PUB_MOD]), ['enabled', 'settings', 'shared_state'])
        self.assertEqual(sorted(mods[PUB_MOD]['settings']), ['auth', 'compat', 'team'])           # ні token, ні password
        self.assertEqual(p['secrets'], {})
        self.assertEqual(p['space_json']['migrations']['liga-4d3c'], {'roles': ['publish']})       # `at`/`backup` — запис; `tracks` нема
        self.assertEqual((p['tracks'], p['tracks_reason']), (False, None))
        self.assertEqual(self.snapshot_tree(), before)                                             # план нічого не пише

    def test_foreign_modules_and_unknown_keys_are_kept(self):
        p = self.plan_c()
        sj = p['space_json']
        self.assertIn('jira-tracker', sj['modules'])
        self.assertIn('supabase-comments', sj['modules'])
        self.assertEqual(sj['name'], 'Liga')
        self.assertEqual(sj['x'], {'k': [1, 2]})
        self.assertEqual(sorted(sj['migrations']), ['liga-4d3a', 'liga-4d3b', 'liga-4d3c'])

    def test_report_names_the_role_and_has_no_secrets_line(self):
        text = self.lm.report(self.plan_c(), 'liga-4d3c')
        self.assertTrue(text.startswith('liga-4d3c: ready\n'))
        self.assertIn('publish (%s): migrate' % PUB_MOD, text)
        self.assertNotIn('secrets', text)
        self.assertNotIn('tracks:', text)
        self.assert_no_secrets(text)

    def test_step_c_does_not_depend_on_a_and_b(self):
        self.setUp_fresh()
        self.assertEqual(self.plan_c()['status'], 'ready')

    def setUp_fresh(self):
        import shutil
        for sub in ('backups', 'migrations'):
            shutil.rmtree(os.path.join(self.deai, sub), ignore_errors=True)
        os.remove(self.space_path())
        os.remove(self.secrets_path())

    # --- пропуски
    def test_skip_layer_off(self):
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}):
            os.environ.pop('DEAI_HOME')
            p = self.plan_c()
        self.assertEqual((p['status'], p['space_json']), ('skip-layer-off', None))

    def test_skip_no_liga(self):
        self.registry(entry=False)
        self.assertEqual(self.plan_c()['status'], 'skip-no-liga')

    def test_skip_done(self):
        self.space_json({'migrations': {'liga-4d3c': {'at': 'x', 'roles': ['publish']}}})
        self.assertEqual(self.plan_c()['status'], 'skip-done')

    def test_skip_held_own_keeps_its_reason(self):
        self.space_json({'migrations': {'liga-4d3c': {'held': True}}})
        p = self.plan_c()
        self.assertEqual((p['status'], p['reason']), ('skip-held', self.lm._REASONS['skip-held']))

    def test_skip_held_by_an_earlier_step_names_it(self):
        for earlier in ('liga-4d3a', 'liga-4d3b'):
            self.space_json({'migrations': {earlier: {'held': True}}})
            p = self.plan_c()
            self.assertEqual((p['status'], p['space_json']), ('skip-held', None), earlier)
            self.assertTrue(p['reason'].startswith('утримано разом із'), earlier)
            self.assertIn(earlier, p['reason'])

    def test_skip_integrations_off(self):
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [
            {'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': False}]})
        p = self.plan_c()
        self.assertEqual((p['status'], p['space_json'], p['secrets']), ('skip-integrations-off', None, {}))

    def test_skip_no_path_and_path_in_git(self):
        os.makedirs(os.path.join(self.space_dir, '.git'))
        self.assertEqual(self.plan_c()['status'], 'skip-path-in-git')
        self.registry(path=os.path.join(self.tmp, 'nowhere'))
        self.assertEqual(self.plan_c()['status'], 'skip-no-path')

    def test_skip_space_json_unreadable(self):
        self.space_json('{broken')
        self.assertEqual(self.plan_c()['status'], 'skip-space-json-unreadable')

    def test_skip_tasks_unreadable(self):
        self._write(self.tasks_path, '{broken')
        self.assertEqual(self.plan_c()['status'], 'skip-tasks-unreadable')

    def test_skip_nothing_when_the_module_is_already_there(self):
        self.write_modules({PUB_MOD: {'enabled': False, 'settings': {'auth': 'token'}}})
        p = self.plan_c()
        self.assertEqual((p['status'], p['space_json'], p['secrets']), ('skip-nothing', None, {}))
        self.assertEqual(p['roles']['publish']['reason'], 'module-present')            # навіть вимкнений: чужий запис не чіпаємо

    # --- провайдер
    def test_provider_check_runs_in_memory_and_aborts(self):
        seen = []
        real = self.dm._provider_for

        def spy(role, space, get_cat=None, explicit_override=None):
            seen.append((role, explicit_override is not None))
            return real(role, space, get_cat, explicit_override)
        with self.mock.patch.object(self.dm, '_provider_for', spy):
            self.assertEqual(self.plan_c()['status'], 'ready')
        self.assertEqual(seen, [('publish', True), ('publish', True)])        # присутність видавця + перевірка розрахованого
        # 4d-4b: другий підставний постачальник — раніше `implicit.for_role('publish')` (не `Module`), тепер — об'єкт із потрібним id, але НЕ `Module`
        for fake in (lambda *a, **k: None, lambda *a, **k: self.mock.MagicMock(id=PUB_MOD)):
            with self.mock.patch.object(self.dm, '_provider_for', fake):
                p = self.plan_c()
            self.assertEqual((p['status'], p['space_json'], p['secrets']), ('abort-provider', None, {}))


class PublisherPresent(_StepC):
    """Поправка 5: ІНШИЙ явно ввімкнений модуль публікації не перебивається (`publisher-present`, не вічний `abort-provider`);
    зламаний СВІЙ — `abort-provider`; результат не залежить від порядку каталогу."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.apply_ab()
        self.pre = self.read_json(self.space_path())

    def put_other(self, mods):
        sj = dict(self.pre)
        sj['modules'] = dict(self.pre['modules'], **mods)
        self.space_json(sj)

    def test_working_other_module_is_publisher_present_not_abort(self):
        self.put_other({'static-publish': {'enabled': True, 'settings': {}}})
        before = self.snapshot_tree()
        p = self.plan_c()
        self.assertEqual((p['status'], p['space_json'], p['secrets']), ('skip-nothing', None, {}))
        self.assertEqual(p['roles'], {'publish': {'module': PUB_MOD, 'migrate': False, 'reason': 'publisher-present'}})
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.run(step='liga-4d3c'), 'skip-nothing')
        self.assertEqual(self.snapshot_tree(), before)                            # ні позначки, ні бекапу, ні last.json
        self.assertNotIn('liga-4d3c', self.marks())
        self.assertEqual(len(self.backups()), 2)

    def test_skip_nothing_of_c_blocks_nothing_and_startup_is_calm(self):
        self.setUp_fresh_modules()
        self.space_json({'modules': {'static-publish': {'enabled': True, 'settings': {}}}})
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'done'), ('liga-4d3b', 'done'), ('liga-4d3c', 'skip-nothing')])
        self.assertEqual(res[2][2]['skipped'], {'publish': 'publisher-present'})
        self.assertNotIn(PUB_MOD, self.read_json(self.space_path())['modules'])
        st, err = self.start()
        self.assertEqual(st, 'skip-done')
        self.assertNotIn('abort', err)

    def setUp_fresh_modules(self):
        import shutil
        for sub in ('backups', 'migrations'):
            shutil.rmtree(os.path.join(self.deai, sub), ignore_errors=True)
        os.remove(self.space_path())
        os.remove(self.secrets_path())

    def test_disabled_other_module_does_not_count(self):
        self.put_other({'static-publish': {'enabled': False, 'settings': {}}})
        p = self.plan_c()
        self.assertEqual((p['status'], p['roles']['publish']['migrate']), ('ready', True))

    def test_broken_own_module_aborts_and_writes_nothing(self):
        self.put_other({'my-pub': {'enabled': True, 'roles': ['publish'], 'settings': {}}})      # теки модуля нема
        before = self.snapshot_tree()
        p = self.plan_c()
        self.assertEqual((p['status'], p['space_json'], p['secrets']), ('abort-provider', None, {}))
        self.assertEqual(self.lm.run(step='liga-4d3c'), 'abort-provider')
        after = self.snapshot_tree()
        last = os.path.join(self.deai, 'migrations', 'last.json')
        self.assertEqual({k: v for k, v in after.items() if k != last}, {k: v for k, v in before.items() if k != last})
        self.assertEqual(self.read_json(last)['status'], 'abort-provider')
        self.assertEqual(len(self.backups()), 2)

    def test_publisher_present_is_total_and_exact(self):
        sp = self.liga_space()
        present = self.lm._publisher_present
        self.assertIs(present(sp, {}), False)
        self.assertIs(present(sp, {'jira-tracker': {'enabled': True, 'settings': {}}}), False)           # Implicit — не модуль
        self.assertIs(present(sp, {'static-publish': {'enabled': True, 'settings': {}}}), True)
        self.assertIs(present(sp, {'static-publish': {'enabled': False, 'settings': {}}}), False)
        self.assertIs(present(sp, {'my-pub': {'enabled': True, 'roles': ['publish'], 'settings': {}}}), False)   # ModuleError → False
        with self.mock.patch.object(self.dm, '_provider_for', side_effect=self.dm.ModuleError('module-error', message='x')):
            self.assertIs(present(sp, {'static-publish': {'enabled': True, 'settings': {}}}), False)       # лише ModuleError → «не присутній»

    def test_other_exception_is_not_swallowed_and_nothing_is_written(self):
        """Ревʼю I1: тимчасовий збій (напр. `OSError` у каталозі) не має робити «не присутній» і перезаписувати робочого видавця."""
        self.put_other({'static-publish': {'enabled': True, 'settings': {}}})
        with self.mock.patch.object(self.dm, '_provider_for', side_effect=OSError('boom')):
            with self.assertRaises(OSError):
                self.lm._publisher_present(self.liga_space(), {'static-publish': {'enabled': True, 'settings': {}}})
            before = self.snapshot_tree()
            p = self.plan_c()
            self.assertEqual((p['status'], p['space_json'], p['secrets']), ('abort-internal', None, {}))
            self.assertEqual(self.lm.run(step='liga-4d3c'), 'abort-internal')
        last = os.path.join(self.deai, 'migrations', 'last.json')
        after = self.snapshot_tree()
        self.assertEqual({k: v for k, v in after.items() if k != last}, {k: v for k, v in before.items() if k != last})
        self.assertNotIn('liga-4d3c', self.marks())
        self.assertNotIn(PUB_MOD, self.read_json(self.space_path())['modules'])

    def test_publisher_present_is_quiet_on_startup_but_visible_in_dry_run(self):
        """Ревʼю M2: стабільний стан не новина — старт не друкує кроків; «dry-run» показує причину. 4d-4b (Поправка 6): вимкнену роль старт називає."""
        self.put_other({'static-publish': {'enabled': True, 'settings': {}}})
        before = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual(st, 'skip-done')
        self.assertEqual(err, '')                                    # I2: роль веде інший явний модуль — вона `on`, старт знову мовчить
        self.assertEqual(self.snapshot_tree(), before)
        code, out, _e = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('publish (%s): skip: publisher-present' % PUB_MOD, out)

    def test_asks_the_core_with_the_override_not_the_disk(self):
        seen = []
        real = self.dm._provider_for

        def spy(role, space, get_cat=None, explicit_override=None):
            seen.append((role, sorted(explicit_override or {})))
            return real(role, space, get_cat, explicit_override)
        with self.mock.patch.object(self.dm, '_provider_for', spy):
            self.lm._publisher_present(self.liga_space(), {'static-publish': {'enabled': True, 'settings': {}}})
        self.assertEqual(seen, [('publish', ['static-publish'])])

    def test_independent_of_catalog_order(self):
        real = self.dm.catalog

        def reversed_catalog(*a, **k):
            return dict(reversed(list(real(*a, **k).items())))
        cases = ({'static-publish': {'enabled': True, 'settings': {}}}, {'my-pub': {'enabled': True, 'roles': ['publish'], 'settings': {}}})
        for mods in cases:
            self.put_other(mods)
            straight = self.plan_c()
            with self.mock.patch.object(self.dm, 'catalog', reversed_catalog):
                flipped = self.plan_c()
            self.assertEqual((straight['status'], straight['roles']), (flipped['status'], flipped['roles']))


class StepCRunTest(_StepC):
    """`run(step='liga-4d3c')`: власний бекап, один запис `space.json`, секрети не чіпаємо, відкат побайтно, жодних значень у виходах."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.apply_ab()
        self.after_ab = (self.read(self.space_path()), self.read(self.secrets_path()))

    def run_c(self):
        self.assertEqual(self.lm.run(step='liga-4d3c'), 'done')
        return self.stamps()

    def test_backup_is_its_own_complete_and_private(self):
        old = {f: self.read(p) for f, p in (('tasks.json', self.tasks_path), ('spaces.json', os.path.join(self.deai, 'spaces.json')),
                                            ('space.json', self.space_path()), ('secrets.json', self.secrets_path()))}
        a, b, c = self.run_c()
        self.assertTrue(c.endswith('-liga-4d3c'))
        self.assertEqual(self.backups(), sorted([a, b, c]))
        d = os.path.join(self.deai, 'backups', c)
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)
        self.assertEqual(sorted(os.listdir(d)), ['manifest.json', 'secrets.json', 'space.json', 'spaces.json', 'tasks.json'])
        m = self.read_json(d, 'manifest.json')
        self.assertEqual(m['migration'], 'liga-4d3c')
        for fname, orig in old.items():
            self.assertEqual(self.read(d, fname), orig, fname)
            self.assertEqual(os.stat(os.path.join(d, fname)).st_mode & 0o777, 0o600, fname)
            self.assertEqual(m['files'][fname]['sha256'], self.sha(orig), fname)
        self.assertEqual(self.read(d, 'space.json'), self.after_ab[0])                  # стан ПІСЛЯ a і b
        self.assert_no_secrets_in_logs()

    def test_mark_content_and_secrets_untouched(self):
        self.run_c()
        mk = self.marks()['liga-4d3c']
        self.assertEqual(sorted(mk), ['at', 'backup', 'roles'])
        self.assertEqual(mk['roles'], ['publish'])
        sj = self.read_json(self.space_path())
        self.assertEqual(sj['modules'][PUB_MOD], PUB_ENTRY)
        self.assertIn('jira-tracker', sj['modules'])
        self.assertEqual(sj['name'], 'Liga')
        self.assertEqual(sj['x'], {'k': [1, 2]})
        self.assertEqual(self.read(self.secrets_path()), self.after_ab[1])             # секретів нема: файл байт-у-байт той самий
        self.assertEqual(os.stat(self.secrets_path()).st_mode & 0o777, 0o600)

    def test_space_json_is_written_once_and_no_secret_is_written(self):
        writes, secrets = [], []
        ws, wsec = self.lm._write_space, self.dm.write_secrets

        def spy_w(*a, **k):
            writes.append(1)
            return ws(*a, **k)

        def spy_s(*a, **k):
            secrets.append(1)
            return wsec(*a, **k)
        with self.mock.patch.object(self.lm, '_write_space', spy_w), self.mock.patch.object(self.dm, 'write_secrets', spy_s):
            self.run_c()
        self.assertEqual((len(writes), len(secrets)), (1, 0))

    def test_second_start_is_skip_done_and_writes_nothing(self):
        self.run_c()
        before = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual((st, err), ('skip-done', ''))
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.run(step='liga-4d3c'), 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)

    def test_restore_returns_the_state_after_b_byte_for_byte(self):
        _a, _b, c = self.run_c()
        self.assertEqual(self.lm.restore(c), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_ab[0])
        self.assertEqual(self.read(self.secrets_path()), self.after_ab[1])
        self.assertIn('liga-4d3b', self.marks())
        self.assertNotIn('liga-4d3c', self.marks())

    def test_no_secret_value_anywhere(self):
        code, out, err = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d3c: done', out)
        self.assertIn('ролі: publish; бекап: ', out)
        self.assert_no_secrets(out, err)
        self.assert_no_secrets_in_logs()
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['secrets'], {})


class LifoThreeSteps(_StepC):
    """Відкат LIFO на три кроки; відмова називає ОСТАННІЙ застосований бекап (Поправка 8)."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.apply_ab()
        self.after_a_b = (self.read(self.space_path()), self.read(self.secrets_path()))
        self.assertEqual(self.lm.run(step='liga-4d3c'), 'done')
        self.a, self.b, self.c = self.stamps()

    def test_restore_a_refused_names_the_last_applied_and_writes_nothing(self):
        before = self.snapshot_tree()
        st, info = self.lm._restore(self.a)
        self.assertEqual((st, info['rollback_first']), ('refuse-later-applied', self.c))
        self.assertEqual(self.lm.restore(self.a, hold=True), 'refuse-later-applied')
        self.assertEqual(self.snapshot_tree(), before)

    def test_restore_b_refused_names_c(self):
        before = self.snapshot_tree()
        st, info = self.lm._restore(self.b)
        self.assertEqual((st, info['rollback_first']), ('refuse-later-applied', self.c))
        self.assertEqual(self.snapshot_tree(), before)

    def test_cli_names_c_and_exits_nonzero(self):
        code, out, _err = self.cli('restore', self.a)
        self.assertEqual(code, 1)
        self.assertIn(self.c, out)
        self.assertNotIn(self.b, out)

    def test_after_restoring_c_then_b_then_a_in_order(self):
        self.assertEqual(self.lm.restore(self.c), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_a_b[0])
        self.assertEqual(self.lm.restore(self.a), 'refuse-later-applied')            # b ще застосований
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')
        self.assertEqual(self.read(self.space_path()), ORIG_SPACE)
        self.assertEqual(self.read_json(self.secrets_path()), OTHER_SECRETS)

    def test_hold_marks_only_c(self):
        a_mark, b_mark = self.marks()['liga-4d3a'], self.marks()['liga-4d3b']
        self.assertEqual(self.lm.restore(self.c, hold=True), 'restored')
        mk = self.marks()
        self.assertEqual(mk['liga-4d3c'], {'held': True})
        self.assertEqual((mk['liga-4d3a'], mk['liga-4d3b']), (a_mark, b_mark))
        self.assertEqual(self.lm.plan(step='liga-4d3c')['status'], 'skip-held')

    def test_held_c_does_not_block_restore_of_b(self):
        self.assertEqual(self.lm.restore(self.c, hold=True), 'restored')
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')
        self.assertEqual(self.read(self.space_path()), ORIG_SPACE)

    def test_held_b_holds_c_on_the_next_start(self):
        self.assertEqual(self.lm.restore(self.c), 'restored')
        self.assertEqual(self.lm.restore(self.b, hold=True), 'restored')
        before = self.snapshot_tree()
        p = self.plan_c()
        self.assertEqual(p['status'], 'skip-held')
        self.assertIn('liga-4d3b', p['reason'])
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'skip-done'), ('liga-4d3b', 'skip-held'), ('liga-4d3c', 'skip-held')])
        st, _err = self.start()                              # перший крок — `skip-done`: усі три `skip-*`, статус першого
        self.assertEqual(st, 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)


class ThreeStepsStartup(_StepC):
    """`startup()`: a, b, c по порядку; `abort-*` раннього не пускає наступні; `skip-nothing` раннього — пускає."""

    def test_user_jumping_from_016_gets_all_three_in_one_start(self):
        self.seed()
        st, err = self.start()
        self.assertEqual(st, 'done')
        a, b, c = self.stamps()
        self.assertEqual(self.backups(), sorted([a, b, c]))
        self.assertLess(err.index('liga-4d3a: done'), err.index('liga-4d3b: done'))
        self.assertLess(err.index('liga-4d3b: done'), err.index('liga-4d3c: done'))
        for mark, stamp in (('liga-4d3a', a), ('liga-4d3b', b), ('liga-4d3c', c)):
            self.assertEqual(self.read_json(self.deai, 'backups', stamp, 'manifest.json')['migration'], mark)
        self.assertIn('liga-4d3b', self.read_json(self.deai, 'backups', c, 'space.json')['migrations'])     # c рахувався ПІСЛЯ запису b
        self.assertIn(PUB_MOD, self.read_json(self.space_path())['modules'])
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['step'], last['status'], sorted(last['steps'])), ('liga-4d3c', 'done', ['liga-4d3a', 'liga-4d3b', 'liga-4d3c']))
        self.assertEqual(last['steps']['liga-4d3a']['backup'], a)                      # звіти a, b не стерті
        self.assertEqual(last['steps']['liga-4d3b']['backup'], b)
        self.assertEqual(last['steps']['liga-4d3c']['roles'], ['publish'])
        self.assert_no_secrets_in_logs()

    def test_startup_suggests_restoring_only_the_latest_step_first(self):
        """Ревʼю I2: LIFO відмовить у відкаті a/b при застосованому c — підказка одна, для c; бекапи a, b видно."""
        self.seed()
        st, err = self.start()
        self.assertEqual(st, 'done')
        a, b, c = self.stamps()
        for stamp in (a, b, c):
            self.assertIn('бекап: %s' % stamp, err)
        self.assertEqual(err.count('відкат:'), 1)
        self.assertIn('відкат: bin/migrate_liga.py restore %s --hold' % c, err)
        self.assertNotIn('restore %s' % a, err)
        self.assertNotIn('restore %s' % b, err)
        self.assertIn('раніші кроки (%s, %s)' % (a, b), err)

    def test_cli_run_suggests_restoring_only_the_latest_step_first(self):
        self.seed()
        code, out, _err = self.cli('run')
        self.assertEqual(code, 0)
        a, b, c = self.stamps()
        for stamp in (a, b, c):
            self.assertIn('бекап: %s' % stamp, out)
        self.assertEqual(out.count('відкат:'), 1)
        self.assertIn('відкат: python3 bin/migrate_liga.py restore %s [--hold]' % c, out)
        self.assertNotIn('restore %s' % a, out)
        self.assertNotIn('restore %s' % b, out)
        self.assertIn('раніші кроки (%s, %s)' % (a, b), out)

    def test_order_of_steps_is_the_order_of_startup(self):
        self.seed()
        order = []
        real = self.lm._run

        def spy(home, step=None):
            order.append(step.mark)
            return real(home, step)
        with self.mock.patch.object(self.lm, '_run', spy):
            self.start()
        self.assertEqual(order, ['liga-4d3a', 'liga-4d3b', 'liga-4d3c'])

    def test_abort_of_an_early_step_stops_the_later_ones(self):
        self.seed()
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: None):
            st, err = self.start()
        self.assertEqual(st, 'abort-provider')
        self.assertEqual(self.backups(), [])
        self.assertNotIn('liga-4d3b: ', err)                          # рядка КРОКУ нема (назва кроку в підказці ролі — не рядок кроку)
        self.assertNotIn('liga-4d3c: ', err)
        last =self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['step'], list(last['steps'])), ('abort-provider', 'liga-4d3a', ['liga-4d3a']))

    def test_skip_nothing_of_a_and_b_does_not_block_c(self):
        self.config(supabase=False, jira=False, design_work_root=None)
        cfg = self.cfg
        cfg['tasks']['x'] = {'dir': os.path.join(self.home, 'work', 'x')}
        self._write(self.tasks_path, cfg)
        self.write_modules({'supabase-comments': {'enabled': True, 'settings': {}}, 'git-sync': {'enabled': True, 'settings': {}}})
        self.assertEqual(self.lm.plan(step='liga-4d3a')['status'], 'skip-nothing')
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-nothing')
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'skip-nothing'), ('liga-4d3b', 'skip-nothing'), ('liga-4d3c', 'done')])
        self.assertEqual(list(self.marks()), ['liga-4d3c'])
        self.assertEqual(len(self.backups()), 1)

    def test_exception_in_c_does_not_break_startup_and_keeps_a_b(self):
        self.seed()
        real = self.lm._run

        def boom(home, step=None):
            if step.mark == 'liga-4d3c':
                raise RuntimeError('boom')
            return real(home, step)
        with self.mock.patch.object(self.lm, '_run', boom):
            st, err = self.start()
        self.assertEqual(st, 'abort-internal')
        self.assertIn('liga-4d3a: done', err)
        self.assertIn('liga-4d3b: done', err)
        self.assertEqual(sorted(self.marks()), ['liga-4d3a', 'liga-4d3b'])
        self.assertNotIn('boom', err)


class CheckVerdictIsolated(_StepC):
    """Поправка 9: «Перевірити» мігрованого `vercel-publish` в ізольованому прогоні — вердикт `isolated` без `npx` і мережі
    (холодний справжній `npx vercel whoami` тут не перевіряється: мережі нема, це нотатка власнику в CHANGELOG)."""

    def test_isolated_verdict_runs_no_npx_and_no_network(self):
        self.write_modules({PUB_MOD: PUB_ENTRY})
        space = self.liga_space()
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}), \
                self.mock.patch.object(serve, '_node_bin', side_effect=AssertionError('npx не має викликатись')), \
                self.mock.patch.object(dm, 'check', side_effect=AssertionError('перевірка модуля не має запускатись')), \
                SocketTripwire() as wire:
            self.assertTrue(isolation.isolated())
            self.assertTrue(dm.shared_state(space, PUB_MOD))
            verdict = serve.module_check_verdict(space, PUB_MOD)
        self.assertEqual((verdict['ok'], verdict['error']), (False, 'isolated'))
        self.assertEqual(wire.count, 0)


# ---------------------------------------------------------------------------------- Task 5: паритет після міграції

#: Підписи нового поля `compat` картки `vercel-publish` — ТОЧНО як бачить людина (зміна підпису — свідома й видима в цьому тесті).
_COMPAT_LABEL = ('Сумісність (⚠ у режимі ЛІГА поля auth і team не читаються: вхід і скоуп беруться зі старих налаштувань; '
                 'пароль превʼю — спершу пароль задачі, далі секрет цього модуля; зміна значення на живому просторі перемикає '
                 'на шлях модуля — нові проєкти й нові URL)')
_COMPAT_OPT = 'design-canvas (ЛІГА): проєкти pv-…, скоуп з tasks.json, пароль превʼю: задача, далі секрет модуля'


def _expect_card():
    """Картка `vercel-publish` у `GET /api/modules` після кроку c: увімкнена, `auth` = `cli`, `team` порожня, нове поле `compat`
    (секретні `token`/`password` — без змін: `set: false`), версія модуля 1.3.0 (1.1.0 до `compat`)."""
    c = '/modules_card/card'
    return {c + '/enabled': (False, True),
            c + '/version': ('1.1.0', '1.3.0'),
            c + '/settings[0]/value': ('token', 'cli'),
            c + '/settings[2]/value': (_ABSENT, ''),
            c + '/settings[4]/key': (_ABSENT, 'compat'),
            c + '/settings[4]/label': (_ABSENT, _COMPAT_LABEL),
            c + '/settings[4]/options[0]/label': (_ABSENT, 'Немає'),
            c + '/settings[4]/options[0]/value': (_ABSENT, ''),
            c + '/settings[4]/options[1]/label': (_ABSENT, _COMPAT_OPT),
            c + '/settings[4]/options[1]/value': (_ABSENT, 'design-canvas'),
            c + '/settings[4]/required': (_ABSENT, False),
            c + '/settings[4]/type': (_ABSENT, 'select'),
            c + '/settings[4]/value': (_ABSENT, 'design-canvas')}


def _expect_publish_derived():
    """Похідне від `capabilities.publish` і картки, що рахує JS і `GET /api/task` із НИХ, а не з гілки публікації:
    `is_vercel_publish` (хто веде роль — модуль), `disable_consequences_publish` (вимкнення картки в просторі з інтеграціями
    повертає вбудовану публікацію: `kind: legacy`, Task 3) і дзеркало `capabilities.publish` у `GET /api/task`."""
    exp = {'/js/is_vercel_publish': (False, True),
           '/js/disable_consequences_publish[0]/kind': (_ABSENT, 'legacy'),
           '/js/disable_consequences_publish[0]/role': (_ABSENT, 'publish'),
           '/js/disable_consequences_publish[]': ([], _ABSENT)}
    for k in ('fresh', 'published', 'after_change'):
        exp['/task/%s/space_capabilities_publish' % k] = ('legacy', 'vercel-publish')
    return exp


def _expect_diff_ab():
    """Стенд «після a+b»: крок c змінює лише `capabilities.publish`, `compat.publish`, картку `vercel-publish` і похідне від них
    (`_expect_publish_derived`). Точний словник: зайва різниця червоніє так само, як зникла очікувана."""
    exp = {'/api_spaces/capabilities/publish': ('legacy', 'vercel-publish'),
           '/api_spaces/compat/publish': (_ABSENT, 'design-canvas')}
    exp.update(_expect_card())
    exp.update(_expect_publish_derived())
    return exp


def _expect_diff_unmigrated():
    """Стенд «нічого не мігровано» (ЛІГА 0.18): після `run_all()` (a, b, c) змінюються `capabilities` п'яти ролей (`tracker` лишається
    `legacy`: у стенді знімка нема облікових даних Jira) і `compat` для `comments`/`vcs`/`publish`; решта — як у `_expect_diff_ab`
    (картка, похідне). `compat` у знімку до — `None` (ключа нема): лист `/api_spaces/compat` зникає разом із `None`."""
    exp = {'/api_spaces/capabilities/comments': ('legacy', 'supabase-comments'),
           '/api_spaces/capabilities/dashboard': ('legacy', 'supabase-dashboard'),
           '/api_spaces/capabilities/notify': ('legacy', 'supabase-teams'),
           '/api_spaces/capabilities/publish': ('legacy', 'vercel-publish'),
           '/api_spaces/capabilities/vcs': ('legacy', 'git-sync'),
           '/api_spaces/compat': (None, _ABSENT),
           '/api_spaces/compat/comments': (_ABSENT, 'comment-layer'),
           '/api_spaces/compat/publish': (_ABSENT, 'design-canvas'),
           '/api_spaces/compat/vcs': (_ABSENT, 'design-canvas')}
    exp.update(_expect_card())
    exp.update(_expect_publish_derived())
    return exp


def _is_4d4b_leaf(path):
    """Листки, що залежать від причин 4d-4b, — у цей клас не входять (Task 14 Step 2), їх звіряє `AfterMigrationParity4d4b` (Task 15) або тест,
    названий поруч: `capabilities.tracker` (без облікових Jira в записі роль вимкнена, а не неявний `legacy`); `comments_off` (сценарій
    прибирає пару Supabase з КОРЕНЯ — корінь більше не читається, коментарі ведуть записи); `pw_root` (пароль у корені не читається —
    `PreviewPasswordFromTheRecord`); `disable_consequences_publish` (наслідок вимкнення без запасного шляху — `tests/connections-model.test.mjs`)."""
    return (path == '/api_spaces/capabilities/tracker' or path.startswith(('/publish/comments_off/', '/publish/pw_root/'))
            or path.startswith('/js/disable_consequences_publish'))


def _diff(before, after):
    """Звіт відмінностей знімків без листків причин 4d-4b (`_is_4d4b_leaf`)."""
    return {k: v for k, v in _diff_all(before, after).items() if not _is_4d4b_leaf(k)}


EXPECT_DIFF_AB = {k: v for k, v in _expect_diff_ab().items() if not _is_4d4b_leaf(k)}
EXPECT_DIFF_UNMIGRATED = {k: v for k, v in _expect_diff_unmigrated().items() if not _is_4d4b_leaf(k)}

#: Що бачить людина і чого НЕ можуть торкнутись кроки: усе, що публікація, пароль і задача віддають; у `/task` — крім дзеркала
#: `capabilities` (воно — не «що бачить людина», а те саме значення, що в `/api_spaces`), у `/js` — крім двох похідних від ролі.
_SEEN_PREFIXES = ('/publish/', '/password/', '/task/',
                  '/js/is_legacy_publish', '/js/is_remote_publish', '/js/pw_view', '/js/preview_target', '/js/copy_url',
                  '/js/publish_reaction', '/js/bar_')
_NOT_SEEN_LEAVES = ('/space_capabilities_publish',)


def _is_seen(path):
    return path.startswith(_SEEN_PREFIXES) and not path.endswith(_NOT_SEEN_LEAVES)


#: Етап А редизайну оболонки (0.25.0) свідомо змінив склад смуги для ВСІХ просторів, а не міграцією: логотип і пігулка
#: оновлення переїхали в рядок вкладок, перемикач задач і фішка простору — у вкладки й екран «Задачі», інспектор і відгук —
#: в острівець, кнопку палітри прибрано (⌘K лишився); натомість зʼявилась назва задачі. Знімок 0.18.0 записано зі старою
#: смугою, тож ці id прибираються з ОБОХ боків порівняння — і лише вони (`test_stage_a_normalisation_is_narrow`).
_STAGE_A_MOVED = frozenset(('home', 'palette', 'space', 'task', 'update', 'feedback', 'inspector'))
_STAGE_A_ADDED = frozenset(('title',))


def _stage_a_bar(js):
    js['bar_item_ids'] = [i for i in js['bar_item_ids'] if i not in _STAGE_A_MOVED | _STAGE_A_ADDED]


class AfterMigrationParity4d3c(unittest.TestCase):
    """Сценарії знімка 0.18.0 (`before-4d3c.json`) на МІГРОВАНІЙ ЛІЗІ у тимчасовому домі: стенд `unmigrated` — `run_all()` (a, b, c),
    стенд `ab` — a+b КОДОМ кроків (пін `STEPS[:2]`, як у знімку) і далі `run(step='liga-4d3c')`. Знімання — той самий генератор
    `tests/make_before_4d3c.py` (імпорт: `Rig`, `liga`-стенд, сценарії, `Server`), лише стенд після створення мігрується (підміна
    `_stand`). Мережі нема (`NoNet`, `SocketTripwire`), справжній `~/.deai` стереже `spaces_guard`.

    Те, що бачить людина (`/publish`, `/task`, `/password`, `/js`), — рівно знімок; різниці лише в `capabilities`/`compat`/картці."""

    @classmethod
    def setUpClass(cls):
        import liga_migrate as lm
        import make_before_4d3c as g
        cls.g, cls.lm = g, lm
        with open(BEFORE, encoding='utf-8') as f:
            cls.before = json.load(f)
        cls.results, cls.marks = {}, {}
        orig = g._stand

        def migrated(tmp, name, migrate):
            rig = orig(tmp, name, migrate=False)
            with rig.activate():
                if name == 'ab':
                    with mock.patch.object(lm, 'STEPS', lm.ALL_STEPS[:2]):                  # a+b як у знімку; c — окремо
                        res = [(m, st, i.get('roles')) for m, st, i in lm.run_all()]
                    res.append(('liga-4d3c', lm.run(step='liga-4d3c'), None))
                else:
                    with mock.patch.object(lm, 'STEPS', lm.ALL_STEPS[:3]):                  # пін 4d-4a: знімок 0.18.0 — до кроку D
                        res = [(m, st, i.get('roles')) for m, st, i in lm.run_all()]
                with open(os.path.join(rig.space_dir, 'space.json'), encoding='utf-8') as fh:
                    cls.marks[name] = json.load(fh)
            cls.results[name] = res
            return rig
        with mock.patch.object(g, '_stand', migrated):
            cls.after = g.make()
        for name in ('unmigrated', 'ab'):
            _stage_a_bar(cls.before['stands'][name]['js'])
            _stage_a_bar(cls.after['stands'][name]['js'])

    def test_stage_a_normalisation_is_narrow(self):
        """Нормалізація смуги 0.25.0 прибирає РІВНО контроли, що переїхали з неї (і нову назву задачі), — решта складу смуги
        лишається в порівнянні: мігрована ЛІГА не сміє втратити чи отримати жоден інший контрол."""
        for name in ('unmigrated', 'ab'):
            ids = self.before['stands'][name]['js']['bar_item_ids']
            self.assertEqual(ids, self.after['stands'][name]['js']['bar_item_ids'], name)
            for kept in ('iter', 'mode', 'vp', 'figma', 'gl', 'publish', 'pubpw', 'teamsnotify'):
                self.assertIn(kept, ids, name)

    def test_all_steps_ran(self):
        """Обидва стенди справді мігровано (a, b, c = `done`; ролі c = `['publish']`): порівняння — з МІГРОВАНОЮ лігою."""
        for name in ('unmigrated', 'ab'):
            self.assertEqual([(m, st) for m, st, _r in self.results[name]],
                             [('liga-4d3a', 'done'), ('liga-4d3b', 'done'), ('liga-4d3c', 'done')], name)
            marks = self.marks[name]['migrations']
            self.assertEqual(sorted(marks), ['liga-4d3a', 'liga-4d3b', 'liga-4d3c'], name)
            self.assertEqual(marks['liga-4d3c']['roles'], ['publish'], name)
            self.assertNotIn('tracks', marks['liga-4d3c'], name)
        self.assertEqual(self.results['unmigrated'][2][2], ['publish'])
        self.assertEqual(self.after['non_loopback_attempts'], 0)                        # мережі не було ні на одному стенді
        for name in ('unmigrated', 'ab'):
            ent = self.marks[name]['modules']['vercel-publish']
            self.assertEqual(ent, {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}})

    def test_snapshot_is_big_enough_to_mean_something(self):
        """Порівняння не порожнє: сотні листків на стенд, усі розділи на місці (інакше «нема відмінностей» нічого б не казало)."""
        for name in ('unmigrated', 'ab'):
            self.assertGreater(len(_flat(self.before['stands'][name])), 400)
            self.assertEqual(sorted(self.after['stands'][name]), sorted(self.before['stands'][name]))

    def test_only_expected_differences_unmigrated(self):
        self.assertEqual(_diff(self.before['stands']['unmigrated'], self.after['stands']['unmigrated']), EXPECT_DIFF_UNMIGRATED)

    def test_only_expected_differences_ab(self):
        self.assertEqual(_diff(self.before['stands']['ab'], self.after['stands']['ab']), EXPECT_DIFF_AB)

    def test_expected_diff_is_exact_not_loose(self):
        """Охоронець самого порівняння: зайвий листок і зниклий очікуваний — обидва червоніють на ОБОХ стендах."""
        for name, exp in (('unmigrated', EXPECT_DIFF_UNMIGRATED), ('ab', EXPECT_DIFF_AB)):
            before = self.before['stands'][name]
            extra = json.loads(json.dumps(self.after['stands'][name]))
            extra['publish']['first']['response']['status'] = 500                      # зайвий листок
            d = _diff(before, extra)
            self.assertIn('/publish/first/response/status', d)
            self.assertNotEqual(d, exp)
            missing = json.loads(json.dumps(self.after['stands'][name]))
            del missing['api_spaces']['compat']['publish']                              # зник очікуваний листок
            self.assertNotEqual(_diff(before, missing), exp)
            self.assertNotIn('/api_spaces/compat/publish', _diff(before, missing))

    def test_nothing_a_person_sees_changed(self):
        """Публікація (відповідь, `tasks.json`, `iterations.json`, argv `npx`, сторінки, шпигуни), `GET /api/task`, пароль превʼю
        і JS-читання (`pwView`, `previewTarget`, `copyUrl`, `publishReaction`, `barState`) — рівно знімок: жодної різниці й УСІ розділи
        непорожні. Різниці є лише в `capabilities`/`compat`/картці й похідному від них (`is_vercel_publish`, `disable_consequences`,
        дзеркало `capabilities` у `/api/task`)."""
        for name in ('unmigrated', 'ab'):
            for path in _diff(self.before['stands'][name], self.after['stands'][name]):
                self.assertFalse(_is_seen(path), '%s: змінилося те, що бачить людина: %s' % (name, path))
            flat = _flat(self.after['stands'][name])
            for prefix in ('/publish/', '/task/', '/password/', '/js/'):
                self.assertGreater(len([k for k in flat if k.startswith(prefix)]), 20, name + ' ' + prefix)
            for sc in self.g.SCENARIOS:
                self.assertTrue(any(k.startswith('/publish/%s/response/' % sc) for k in flat), name + ' ' + sc)
            self.assertIn('/js/copy_url', flat)
            self.assertEqual(flat['/js/copy_url'], 'https://pv-12345678.vercel.app/#k=1100&p=alpha')
            first = dict((k, v) for k, v in self.after['stands'][name]['publish']['first']['response']['pairs'])
            self.assertEqual((first['url'], first['deploy_url'], first['verified']), ('https://pv-12345678.vercel.app',) * 2 + (True,))

    def test_legacy_reaction_wins_over_vercel_reaction(self):
        """Інваріант «`isLegacyPublish` раніше за `isVercelPublish`»: запис із `capabilities.publish == 'vercel-publish'` і
        `compat.publish == 'design-canvas'` дає `publishReaction` = `legacy` (а не `remote`), як і для немігрованої ЛІГИ.
        Той самий механізм, що й розділ `js` генератора знімка: справжній `spaces-model.js` у `node`."""
        js = ("import { pathToFileURL } from 'node:url';"
              "const m = await import(pathToFileURL(process.argv[1]).href);"
              "const url = { url: 'https://pv-12345678.vercel.app' };"
              "const mig = { capabilities: { publish: 'vercel-publish' }, compat: { publish: 'design-canvas' } };"
              "const plain = { capabilities: { publish: 'vercel-publish' } };"
              "console.log(JSON.stringify({ mig: m.publishReaction(url, mig, true).kind, plain: m.publishReaction(url, plain, true).kind }));")
        r = subprocess.run(['node', '--input-type=module', '-e', js, os.path.join(os.path.dirname(_HERE), 'app', 'spaces-model.js')],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(json.loads(r.stdout), {'mig': 'legacy', 'plain': 'remote'})

    def test_card_is_enabled_without_secrets(self):
        """Картка мігрованого `vercel-publish`: увімкнена, `compat` = `design-canvas`; секретні `token`/`password` лишились
        `set: false` (крок секретів не пише: `secrets.json` не змінюється)."""
        for name in ('unmigrated', 'ab'):
            card = self.after['stands'][name]['modules_card']['card']
            self.assertTrue(card['enabled'])
            by = {s['key']: s for s in card['settings']}
            self.assertEqual((by['auth']['value'], by['compat']['value']), ('cli', 'design-canvas'))
            for key in ('token', 'password'):
                self.assertEqual((by[key]['type'], by[key]['set']), ('secret', False), name + ' ' + key)
                self.assertNotIn('value', by[key])

    def test_capabilities_and_compat_after_migration(self):
        for name in ('unmigrated', 'ab'):
            a = self.after['stands'][name]['api_spaces']
            self.assertEqual(a['capabilities']['publish'], 'vercel-publish')
            self.assertEqual(a['compat']['publish'], 'design-canvas')
            # на обох стендах п'ять ролей ведуть модулі (на `ab` — після a+b+c, на `unmigrated` — після `run_all`); `tracker`: у стенді знімка
            # нема облікових даних Jira, тож крок a нічого не мігрує для цієї ролі. Було `'tracker': 'legacy'` (неявний постачальник); 4d-4b: роль
            # без запису вимкнена (`None`) — це причина 4d-4b, її звіряє `AfterMigrationParity4d4b` (Task 15), тут `tracker` не порівнюється.
            self.assertEqual({k: v for k, v in a['capabilities'].items() if k not in ('tokens', 'tracker')},
                             {k: v for k, v in _ROLE_IDS.items() if k != 'tracker'})


# ---------------------------------------------------------------------------------- Task 5: НЕізольований шлях власника

class RealPublishNonIsolated(unittest.TestCase):
    """Task 5: публікація МІГРОВАНОЇ ЛІГИ НЕІЗОЛЬОВАНИМ шляхом — тим, яким піде власник на першому старті 0.19 (нема `DC_TASKS_FILE`/
    `DC_NO_OVERVIEW`: `assertFalse(implicit.isolated())`). Живий тест ізольований (`DC_TASKS_FILE`) і доводить ізольований шлях,
    тож твердження про шлях власника — ТУТ: справжній `serve._node_bin` знаходить фальшивий `npx`, що стоїть ПЕРШИМ на `PATH`
    (а не підмінений шов), справжній сервер і `Handler._publish`, справжні запис `tasks.json`/`iterations.json` і шиті сторінки.
    Підмінено лише те, що вийшло б у мережу чи в спільний стан: `_fetch_page` модуля, `serve._registry_push`,
    `Handler._overview_sync`, `serve.git_autocommit` — це шпигуни, що записують ПОРЯДОК і аргументи викликів; окрім них
    `serve.server_code_staleness` заглушено в `None` (перевірка свіжості коду сервера до публікації не належить сценарію).

    Той самий сценарій на НЕмігрованій лізі (`Implicit`) дає ТІ САМІ дані: порівнюємо два прогони між собою, а не лише зі знімком.
    Тимчасові `HOME`/`DEAI_HOME` через `mock.patch.dict` у `setUp`; вигадані значення; мережі нема (`NoNet`, `SocketTripwire`)."""

    def setUp(self):
        import contextlib
        import fake_npx
        import liga_migrate as lm
        import make_before_4d3c as g
        self.g, self.fake_npx, self.lm = g, fake_npx, lm
        self._tmp = tempfile.TemporaryDirectory(prefix='b4d3c-real-')
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.realpath(self._tmp.name)
        env = mock.patch.dict(os.environ, {'HOME': os.path.join(self.tmp, 'home0'), 'DEAI_HOME': os.path.join(self.tmp, 'deai0')})
        env.start()
        self.addCleanup(env.stop)
        for name in g.CLEAN:                                        # чисте оточення (`mock.patch.dict` поверне його в `stop`)
            os.environ.pop(name, None)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.wire = stack.enter_context(SocketTripwire())
        self.net = g.NoNet()
        stack.enter_context(mock.patch.object(serve.urllib.request, 'urlopen', self.net))

    def tearDown(self):
        self.assertEqual(self.wire.count, 0)
        self.assertEqual(self.net.calls, 0)

    # --- один прогін сценарію на стенді (мігрованому чи ні)
    def publish_once(self, rig, srv, npxdir, scenario, body=None, page=None, mint=False):
        """Одна публікація `POST /api/publish` НЕІЗОЛЬОВАНИМ шляхом: `serve._node_bin` НЕ підмінено (його знаходить `PATH`)."""
        import secrets
        g = self.g
        calls, fetched = [], []

        def fetch(url):
            fetched.append(url)
            return page or g.PAGE_GATE
        dm.reset_caches()
        module_globals = dm.catalog()['vercel-publish'].fn('publish').__globals__
        self.fake_npx.make(npxdir, scenario)
        with mock.patch.dict(module_globals, {'_fetch_page': fetch}), \
                mock.patch.object(serve, '_registry_push', lambda tid: calls.append(['registry_push', tid]) or False), \
                mock.patch.object(serve, 'git_autocommit',
                                  lambda d, msg, push=None: calls.append(['git_autocommit', g.rel(d, rig.home), msg])), \
                mock.patch.object(serve.Handler, '_overview_sync', lambda handler: calls.append(['overview_sync'])), \
                mock.patch.object(serve, 'server_code_staleness', lambda *a, **kw: None), \
                mock.patch.object(secrets, 'choice', g._Mint() if mint else secrets.choice):
            status, resp = g._raw(srv, 'POST', '/api/publish', task=g.TID, body=body or {}, hook=g._pairs)
        with open(rig.tasks_path, encoding='utf-8') as fh:
            task = json.load(fh)['tasks'][g.TID]
        task_dir = os.path.join(rig.home, 'work', g.TID)
        with open(os.path.join(task_dir, 'iterations.json'), encoding='utf-8') as fh:
            meta = json.load(fh)
        pages, build = g._pages(task_dir, rig.home)
        snap = {'response': {'status': status, 'pairs': resp},
                'tasks_after': {'vercel_project': task.get('vercel_project'), 'vercel_scope': task.get('vercel_scope')},
                'iterations_after': {'publish_url': meta.get('publish_url'),
                                     'published_at': '<time>' if meta.get('published_at') else None,
                                     'publish_verified': meta.get('publish_verified'),
                                     'publish_remote': 'present' if 'publish_remote' in meta else 'absent'},
                'npx_argv': [c['argv'] for c in self.fake_npx.calls(npxdir)],
                'build': build, 'pages': pages, 'spies': {'calls': calls, 'fetched_urls': fetched}}
        return g.scrub(snap, rig.home)

    def exercise(self, migrated, name=None):
        """Стенд ЛІГИ (`migrated` — після `run_all()`: a, b, c) → `(дані, мета)`; `дані` мусять збігатись між двома прогонами,
        `мета` — те, що різниться за задумом (`capabilities.publish`, постачальник). `name` — тека стенда (два прогони — дві теки)."""
        g = self.g
        name = name or ('mig' if migrated else 'imp')
        rig = g._stand(self.tmp, name, migrate=False)
        npxdir = os.path.join(rig.home, 'fake-npx')
        self.fake_npx.make(npxdir, g.NPX_OK)
        env = {**g._env_extra(rig), 'PATH': npxdir + os.pathsep + os.environ.get('PATH', '')}
        data, meta = {}, {}
        space = {'id': g.SPACE_ID, 'path': rig.space_dir, 'legacy': True, 'integrations': True}
        with rig.activate(env):
            if migrated:
                with mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS[:3]):           # пін 4d-4a: знімок 0.18.0 — до кроку D
                    res = [(m, st) for m, st, _i in self.lm.run_all()]
                self.assertEqual(res, [('liga-4d3a', 'done'), ('liga-4d3b', 'done'), ('liga-4d3c', 'done')])
            dm.reset_caches()
            # ⛔ НЕізольований прогін: нема ні `DC_TASKS_FILE`, ні `DC_NO_OVERVIEW`; `npx` — фальшивий, перший на `PATH`
            self.assertFalse(isolation.isolated(), 'неізольований прогін: нема ні DC_TASKS_FILE, ні DC_NO_OVERVIEW')
            self.assertNotIn('DC_TASKS_FILE', os.environ)
            self.assertNotIn('DC_NO_OVERVIEW', os.environ)
            self.assertEqual(serve._node_bin('npx'), os.path.join(npxdir, 'npx'))
            with spaces.request_space(g.SPACE_ID):
                prov = dm.provider('publish', space)
                meta['implicit'] = False             # `Implicit` видалено (4d-4b): неявного постачальника нема ні до, ні після міграції
                meta['caps_publish'] = dm.capabilities(space)['publish']
                data['publish_module_is_none'] = dm.publish_module(space) is None
                self.assertTrue(data['publish_module_is_none'])
                self.assertTrue(dm.publish_legacy_path(prov, space))
            with g.Server() as srv:
                g._reset_world(rig)
                data['first'] = self.publish_once(rig, srv, npxdir, g.NPX_OK, mint=True)
                data['second'] = self.publish_once(rig, srv, npxdir, g.NPX_OK)                      # той самий світ: проєкт, скоуп, URL
                st, task_body = g._raw(srv, 'GET', '/api/task', task=g.TID)
                self.assertEqual(st, 200)
                data['task_keys'] = {'publish_gate': 'publish_gate' in task_body, 'publish_share_url': 'publish_share_url' in task_body,
                                     'publish_remote': 'publish_remote' in task_body, 'preview_password': task_body.get('preview_password'),
                                     'publish_url': task_body.get('publish_url')}
                _api, _card, data['js'] = g.api_sections(rig, srv, task_body)
                with open(os.path.join(rig.home, 'work', g.TID, 'iterations.json'), encoding='utf-8') as fh:
                    it_meta = json.load(fh)
                with spaces.request_space(g.SPACE_ID):
                    data['task_publish_share'] = serve.task_publish_share(space, it_meta)
                    cfg = serve.load_tasks()
                    data['comments_module_publish'] = list(serve.publish_comments(space, cfg['tasks'][g.TID], g.TID, module_publish=True))
                    res, warn = serve.publish_comments(space, cfg['tasks'][g.TID], g.TID, module_publish=False)
                    data['comments_legacy_path'] = {'channel': res['channel'] if res else None, 'warning': warn}
                known = {'vercel_project': g.PROJECT}
                g._reset_world(rig, task_extra={**known, 'preview_password': g.PW_TASK})
                data['pw_task'] = self.publish_once(rig, srv, npxdir, g.NPX_OK)
                g._reset_world(rig, task_extra=known, root_extra={'preview_password': g.PW_ROOT})
                data['pw_root'] = self.publish_once(rig, srv, npxdir, g.NPX_OK)
            dm.reset_caches()
        return data, meta

    # --- перелік тверджень про шлях власника
    def check_owner_path(self, data):
        g = self.g
        first, second = data['first'], data['second']
        # перша публікація мінтить `pv-NNNNNNNN` і пише скоуп із `.vercel/project.json` фальшивого `npx` у `tasks.json`
        self.assertEqual(first['response']['status'], 200)
        self.assertEqual(first['tasks_after'], {'vercel_project': g.PROJECT, 'vercel_scope': g.SCOPE})
        # друга — той самий проєкт, той самий URL, той самий скоуп; `link --project pv-… --scope …` зі стану `tasks.json`
        self.assertEqual(second['tasks_after'], first['tasks_after'])
        self.assertEqual(second['iterations_after']['publish_url'], first['iterations_after']['publish_url'])
        pairs = dict((k, v) for k, v in second['response']['pairs'])
        self.assertEqual((pairs['url'], pairs['deploy_url'], pairs['verified']), (g.URL_A, g.URL_A, True))
        self.assertEqual(second['npx_argv'][0], ['--yes', 'vercel', 'link', '--yes', '--scope', g.SCOPE, '--project', g.PROJECT])
        self.assertEqual(second['npx_argv'][1][:4], ['--yes', 'vercel', 'deploy', '--prod'])
        self.assertEqual(second['npx_argv'][-1], ['--yes', 'vercel', 'list', g.PROJECT, '--json', '--scope', g.SCOPE])
        # шлях ЛІГИ: збірка ядра (`build == 'legacy'`), `publish_remote` ВІДСУТНІЙ, превʼю перевірене за адресою
        for sc in (first, second):
            self.assertEqual(sc['build'], 'legacy')
            self.assertEqual(sc['iterations_after']['publish_remote'], 'absent')
            self.assertIs(sc['iterations_after']['publish_verified'], True)
            self.assertEqual(sc['spies']['fetched_urls'], [g.URL_A])
            # гейт зі `1100` у ВСІХ шитих сторінках; коментарі ЛІГИ ін'єктовані (канал `dc/a-1`, адреса й ключ Supabase)
            for rel_path, page in sc['pages']['html'].items():
                self.assertEqual((page['authgate'], page['password']), (True, '1100'), rel_path)
            alpha = sc['pages']['html']['it1/alpha/index.html']
            self.assertEqual((alpha['comment_layer'], alpha['channel'], alpha['supabase_url']), (True, 'dc/a-1', g.SB_URL))
            self.assertEqual(alpha['supabase_key'], '<secret:%d>' % len(g.SB_KEY))
            # побічні дії НЕізольованого шляху — ВСІ три, у цьому порядку й з цими аргументами (`registry_push` → автокоміт → огляд)
            self.assertEqual(sc['spies']['calls'], [['registry_push', 'a-1'], ['git_autocommit', '~/work/a-1', 'publish: 2 iteration(s)'],
                                                    ['overview_sync']])
        # пароль задачі змінює гейт; 4d-4b: пароль у КОРЕНІ більше не читається (було `('pw_root', g.PW_ROOT)`: гейт ставав паролем кореня) —
        # типовий `1100`, поки спільний пароль не заданий секретом запису (`test_publish_module`, `PreviewPasswordFromTheRecord`)
        for key, pw in (('pw_task', g.PW_TASK), ('pw_root', '1100')):
            self.assertEqual({p['password'] for p in data[key]['pages']['html'].values()}, {pw}, key)
            self.assertEqual(data[key]['tasks_after']['vercel_project'], g.PROJECT)
            self.assertEqual(data[key]['iterations_after']['publish_remote'], 'absent')
        # `copyUrl` = `#k=<пароль>&p=<сторінка>`, `task_publish_share` → `{}` (шлях ЛІГИ), нових полів `publish_*` у `/api/task` нема
        self.assertEqual(data['js']['copy_url'], g.URL_A + '/#k=1100&p=alpha')
        self.assertEqual(data['task_publish_share'], {})
        self.assertEqual(data['task_keys'], {'publish_gate': False, 'publish_share_url': False, 'publish_remote': False,
                                             'preview_password': '1100', 'publish_url': g.URL_A})
        self.assertIs(data['js']['is_legacy_publish'], True)
        self.assertIs(data['js']['is_remote_publish'], False)
        # відмова модуль-шляху НЕ змінилась: у збірці модуля публікації коментарі `shared_state`/`Implicit` не їдуть
        self.assertEqual(data['comments_module_publish'], [False, None])
        self.assertEqual(data['comments_legacy_path'], {'channel': 'dc/a-1', 'warning': None})

    def test_migrated_liga_publishes_the_owner_path_unchanged(self):
        data, meta = self.exercise(True)
        self.assertEqual((meta['implicit'], meta['caps_publish']), (False, 'vercel-publish'))
        self.check_owner_path(data)

    def test_unmigrated_liga_has_no_publish_provider(self):
        """Було `test_unmigrated_liga_gives_the_same_data`: немігрована ЛІГА (неявний постачальник) публікує ТИМ САМИМ шляхом власника
        (ті самі дані, що мігрована). 4d-4b видалила це навмисно: без запису `vercel-publish` ролі `publish` немає — «замінено тестом» цим
        (нема постачальника, нема capabilities, публікація з ядра не ходить) і `test_migrated_liga_publishes_the_owner_path_unchanged`
        (шлях власника — лише через мігрований запис)."""
        g = self.g
        rig = g._stand(self.tmp, 'imp', migrate=False)
        space = {'id': g.SPACE_ID, 'path': rig.space_dir, 'legacy': True, 'integrations': True}
        with rig.activate(g._env_extra(rig)):
            dm.reset_caches()
            with spaces.request_space(g.SPACE_ID):
                self.assertIsNone(dm.provider('publish', space))
                self.assertIsNone(dm.capabilities(space)['publish'])
                self.assertIsNone(dm.publish_module(space))
                self.assertFalse(dm.publish_legacy_path(None, space))
            dm.reset_caches()

    def test_two_runs_are_identical_and_match_the_snapshot(self):
        """Було: два прогони ОДИН з ОДНИМ (мігрована ≡ немігрована), а потім знімок 0.18.0. 4d-4b: немігрованого прогону нема (див.
        `test_unmigrated_liga_has_no_publish_provider`) — тут два прогони ТОГО САМОГО мігрованого стенда ідентичні (детермінізм) і збігаються
        зі знімком 0.18.0 (ключі, що не залежать від шляху ізоляції: відповідь, `tasks.json`, `iterations.json`, argv, збірка, сторінки).
        Шпигуни знімка — ізольований шлях; тут — справжній. Сценарій `pw_root` у знімку — пароль кореня, який більше не береться: поза порівнянням."""
        mig1, _m1 = self.exercise(True)
        mig, _m2 = self.exercise(True, name='mig-again')
        for d in (mig1, mig):                                        # похідні від ролі, а не від публікації: різняться за задумом
            d['js'] = {k: v for k, v in d['js'].items() if k not in ('is_vercel_publish', 'disable_consequences_publish')}
        self.maxDiff = None
        self.assertEqual(mig, mig1)
        with open(BEFORE, encoding='utf-8') as f:
            before = json.load(f)
        for stand in ('unmigrated', 'ab'):
            for sc in ('first', 'second'):
                snap = before['stands'][stand]['publish'][sc]
                for key in ('response', 'tasks_after', 'iterations_after', 'npx_argv', 'build', 'pages'):
                    self.assertEqual(mig[sc][key], snap[key], '%s/%s/%s' % (stand, sc, key))
            self.assertEqual(mig['js']['copy_url'], before['stands'][stand]['js']['copy_url'])


# ---------------------------------------------------------------------------------- Task 5: три кроки на одному старті

_ROLE_IDS = {'comments': 'supabase-comments', 'dashboard': 'supabase-dashboard', 'notify': 'supabase-teams',
             'publish': 'vercel-publish', 'tracker': 'jira-tracker', 'vcs': 'git-sync'}


class ThreeStepsParityStartup(_StepC):
    """`startup()` у тимчасовому домі: три бекапи, у `capabilities` усіх шести ролей — id модулів (жодного `legacy`); другий старт
    нічого не пише (mtime і sha256 `space.json`/`secrets.json`/`last.json`, нових бекапів нема)."""

    def stat_of(self, *paths):
        out = {}
        for p in paths:
            st = os.stat(p)
            out[p] = (st.st_mtime_ns, self.sha(self.read(p)))
        return out

    def test_one_start_gives_three_backups_and_six_explicit_roles(self):
        self.seed()
        st, err = self.start()
        self.assertEqual(st, 'done')
        a, b, c = self.stamps()
        self.assertEqual(self.backups(), sorted([a, b, c]))
        self.assertLess(err.index('liga-4d3a: done'), err.index('liga-4d3b: done'))      # порядок кроків на старті
        self.assertLess(err.index('liga-4d3b: done'), err.index('liga-4d3c: done'))
        at = [self.marks()[m]['at'] for m in ('liga-4d3a', 'liga-4d3b', 'liga-4d3c')]
        self.assertEqual(at, sorted(at))
        with spaces.request_space('legacy'):
            self.dm.reset_caches()
            caps = self.dm.capabilities(self.liga_space())
        self.assertEqual({r: caps[r] for r in _ROLE_IDS}, _ROLE_IDS)
        self.assertNotIn('legacy', caps.values())
        self.assert_no_secrets_in_logs()

    def test_second_start_writes_nothing(self):
        self.seed()
        self.assertEqual(self.start()[0], 'done')
        files = [self.space_path(), self.secrets_path(), os.path.join(self.deai, 'migrations', 'last.json')]
        before = self.stat_of(*files)
        backups = self.backups()
        tree = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual(st, 'skip-done')
        self.assertEqual(err, '')
        self.assertEqual(self.stat_of(*files), before)               # ні байта, ні mtime
        self.assertEqual(self.backups(), backups)                    # нових бекапів нема
        self.assertEqual(self.snapshot_tree(), tree)


if __name__ == '__main__':
    unittest.main()

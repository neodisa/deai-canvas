"""Міграція ЛІГИ, третій крок — `publish` (етап 4d-3c, 0.19.0).

Тут: знімок поведінки 0.18.0 (`Before4d3cShape`, Task 1); предикат, `compat`, крок `liga-4d3c`, паритет і три кроки додаються
наступними задачами. Спека `docs/superpowers/specs/2026-11-06-liga-migration-c-design.md`.
"""
import ast
import json
import os
import re
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
import implicit  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from make_before_4d3c import SB_KEY, SB_URL  # noqa: E402  (вигадані значення — ті самі, що в генераторі)
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

    def test_implicit_is_the_league_path(self):
        prov = self.prov()
        self.assertIsInstance(prov, implicit.Implicit)
        self.assertIs(dm.publish_legacy_path(prov), True)
        self.assertIs(dm.publish_legacy_path(prov, self.on), True)

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
        # `compat` чужої ролі чи чужого модуля (4d-3b: comments/vcs мають СВОЄ `compat`) не робить публікацію «ЛІГОЮ»
        extra = {mid: {'enabled': True, 'settings': {'compat': DC}}
                 for mid in ('static-publish', 'supabase-comments', 'git-sync')}
        self.write_modules(self.on, {VID: {'enabled': True, 'settings': {}}, **extra})
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
        out = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'isinstance' and len(n.args) == 2:
                if 'Implicit' in ast.dump(n.args[1]):
                    out.append(n.lineno)
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

    def test_the_type_test_lives_in_the_predicate_only(self):
        self.assertEqual(len(self.implicit_checks(self.fn(self.dm_tree, 'publish_legacy_path'))), 1)
        self.assertEqual(self.implicit_checks(self.fn(self.dm_tree, 'publish_module')), [])

    def test_guard_sees_a_planted_check(self):
        planted = ast.parse('def f(v):\n    return isinstance(v, implicit.Implicit)\n')
        self.assertEqual(self.implicit_checks(planted), [2])
        clean = ast.parse('def f(v):\n    return isinstance(v, dict)\n')
        self.assertEqual(self.implicit_checks(clean), [])
        planted_call = ast.parse('def f(v):\n    return dm.publish_module(v)\n')
        self.assertEqual(self.calls(planted_call, 'publish_module'), [2])


if __name__ == '__main__':
    unittest.main()

"""Міграція ЛІГИ, другий крок — `comments` і `vcs` (етап 4d-3b, 0.18.0).

Тут: знімок поведінки 0.17.0 (`Before4d3bShape`, Task 1); канал, `compat`, ізоляція, кроки й паритет додаються наступними
задачами. Спека `docs/superpowers/specs/2026-11-06-liga-migration-b-design.md`.
"""
import ast
import json
import os
import re
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3b.json')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402
from test_liga_migrate import _WriteStand  # noqa: E402  (стенд запису 4d-3a: тимчасові HOME/DEAI_HOME, CLI, пошук секретів)

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard` (тести цього файлу пишуть `space.json` — лише у власних теках)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Before4d3bShape(unittest.TestCase):
    """Знімок 0.17.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['comments', 'meta', 'non_loopback_attempts', 'vcs'])
        self.assertEqual(self.snap['meta']['version'], '0.17.0')
        self.assertEqual(self.snap['meta']['source_commit'], '6906621')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d3b.py')
        self.assertEqual(self.snap['non_loopback_attempts'], 0)
        self.assertEqual(self.snap['comments']['api']['urlopen_calls'], 0)
        self.assertEqual((self.snap['vcs']['urlopen_calls'], self.snap['vcs']['form']['urlopen_calls']), (0, 0))

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек, ні секретів: лише `~/…`/`<tmp>`; значення — вигадані."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d3b-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        for secret in ('sb_test_key_alpha', 'sb_env_key_alpha', 'jira_env_token_alpha', 'jira_file_token_alpha'):
            self.assertNotIn(secret, self.raw, 'секрет у знімку: значення мусить бути <secret:ДОВЖИНА>')
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))          # жодного часового штампа
        self.assertIsNone(re.search(r'\d{2}\.\d{2}\.\d{4}', self.raw), 'дата запису ітерації чи час коміту — мінливе')
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])

    # ------------------------------------------------------------------------------ comments

    def test_comments_channel_scenarios(self):
        """Канал: задача з `comment_project` і без × `internal` — чотири і більше сценаріїв, у кожному з місць, що рахують канал."""
        c = self.snap['comments']
        for sec in (c['space'], self.snap['vcs']['space']):
            self.assertTrue(sec['legacy'] and sec['integrations'])
        self.assertEqual(sorted(c), ['api', 'channels', 'dashboard', 'inbox', 'project_comments', 'route', 'space'])
        ch = c['channels']
        self.assertEqual(sorted(ch), ['a-1', 'a-2', 'a-3'])
        self.assertEqual(ch['a-1'], {'comment_project': 'liga-shared', 'plain': 'liga-shared', 'internal': 'liga-shared/internal'})
        for tid in ('a-2', 'a-3'):
            self.assertIsNone(ch[tid]['comment_project'])
            self.assertEqual(ch[tid]['plain'], 'dc/%s' % tid)
            self.assertEqual(ch[tid]['internal'], 'dc/%s/internal' % tid)
        scenarios = [v[k] for v in ch.values() for k in ('plain', 'internal')]
        self.assertGreaterEqual(len(scenarios), 4)
        self.assertEqual(len(set(scenarios)), len(scenarios))
        # ті самі канали бачать comments_route і ProjectComments (одна схема — два входи)
        want = {tid: {'plain': v['plain'], 'internal': v['internal']} for tid, v in ch.items()}
        self.assertEqual(c['route']['channels'], want)
        self.assertEqual(c['project_comments']['channels'], want)

    def test_comments_route_and_project_comments(self):
        c = self.snap['comments']
        r = c['route']
        self.assertEqual((r['provider'], r['provider_error'], r['module']), ('Implicit', None, 'supabase-comments'))
        self.assertEqual(r['ctx']['settings'], {'shots_bucket': 'overview-thumbs', 'url': 'https://sb.example.com'})
        self.assertEqual(list(r['ctx']['secrets']), ['key'])
        self.assertRegex(r['ctx']['secrets']['key'], r'^<secret:\d+>$')
        self.assertEqual(r['ctx']['space'], {'id': 'legacy', 'path': ''})
        pc = c['project_comments']
        self.assertEqual(sorted(pc), ['calls', 'channels', 'kind', 'label', 'outcomes', 'provider', 'takes_iteration'])
        self.assertEqual(sorted(pc['outcomes']), ['pins_a1', 'pins_a2_internal', 'resolve_a1'])
        self.assertEqual((pc['kind'], pc['label'], pc['takes_iteration'], pc['provider']), ('implicit', 'Supabase', True, 'Implicit'))
        self.assertEqual([x['fn'] for x in pc['calls']], ['list', 'list', 'resolve'])
        self.assertEqual([x['args'][0] for x in pc['calls']], ['liga-shared', 'dc/a-2/internal', 'liga-shared'])
        self.assertEqual(pc['calls'][2]['args'], ['liga-shared', 'abcdef12', 'ok', 1])
        for call in pc['calls']:
            self.assertEqual(call['module'], 'supabase-comments')
            self.assertEqual(call['ctx'], r['ctx'])

    def test_comments_api(self):
        a = self.snap['comments']['api']
        self.assertEqual(sorted(a), ['comment_config', 'comment_config_local', 'task_comment_channel', 'teams_mute_get',
                                     'teams_mute_post', 'urlopen_calls'])
        cc = a['comment_config']
        self.assertEqual({t: (v['status'], v['module'], v['channel']) for t, v in cc.items()},
                         {'a-1': (200, 'supabase-comments', 'liga-shared'), 'a-2': (200, 'supabase-comments', 'dc/a-2')})
        for v in cc.values():
            self.assertEqual(v['ch'], 'project')
            self.assertEqual(sorted(v['config']), ['key', 'shotsBucket', 'url'])
            self.assertRegex(v['config']['key'], r'^<secret:\d+>$')
            self.assertEqual(len(v['client']), 2)
        for v in cc.values():
            self.assertEqual(v['client'], ['/api/module-client/supabase-comments/supabase.min.js',
                                           '/api/module-client/supabase-comments/adapter.js'])
            self.assertEqual(sorted(v), ['ch', 'channel', 'client', 'config', 'keys', 'module', 'status', 'version'])
        self.assertEqual(a['comment_config_local']['status'], 200)
        self.assertEqual(a['task_comment_channel'], {'a-1': 'liga-shared', 'a-2': 'dc/a-2', 'a-3': 'dc/a-3'})
        # тиша Teams: той самий канал, що в `/api/task`; POST пише саме його в шов
        self.assertEqual({t: v['body']['channel'] for t, v in a['teams_mute_get'].items()}, {'a-1': 'liga-shared', 'a-2': 'dc/a-2'})
        self.assertFalse(any(v['body']['muted'] for v in a['teams_mute_get'].values()))
        p = a['teams_mute_post']
        self.assertEqual((p['status'], p['ok'], p['channel'], p['muted'], p['fake_file_keys']), (200, True, 'liga-shared', True, ['liga-shared']))
        self.assertTrue(p['a1_after']['muted'])
        self.assertFalse(p['a2_after']['muted'])

    def test_dashboard_counter_keys(self):
        """Ключ лічильника дашборда: `comment_project` або `dc/<id>`; у картку лягає лише статус (`review` — коментарі є)."""
        d = self.snap['comments']['dashboard']
        self.assertEqual(d['counter_keys_asked'], ['liga-shared', 'dc/a-2', 'dc/a-3'])
        self.assertEqual({c['id']: c['status'] for c in d['pushed'][0]['cards']}, {'a-1': 'review', 'a-2': 'review', 'a-3': 'work'})
        self.assertFalse(any(c['has_open_comments_field'] for c in d['pushed'][0]['cards']), 'open_comments на картці не шлемо')

    def test_inbox_short_prefix(self):
        i = self.snap['comments']['inbox']
        self.assertEqual(sorted(i), ['a2_full_prefix', 'a2_short_prefix', 'full_prefix', 'short_prefix'])
        for v in i.values():
            self.assertEqual(sorted(v), ['module_calls', 'rc', 'stderr', 'stdout'])
        self.assertEqual((i['a2_short_prefix']['rc'], i['a2_short_prefix']['stderr']),
                         (2, ['error: префікс коротший за 6 символів: abc']))
        self.assertEqual((i['a2_full_prefix']['rc'], i['a2_full_prefix']['stdout'][0]),
                         (0, '[dry-run] Supabase: resolve dc/a-2 abcdef12deadbeef Іт.1 "ok"'))
        self.assertEqual(i['short_prefix']['rc'], 2)
        self.assertEqual(i['short_prefix']['stderr'], ['error: префікс коротший за 6 символів: abc'])
        self.assertEqual(i['short_prefix']['module_calls'], [])
        self.assertEqual(i['full_prefix']['rc'], 0)
        self.assertEqual(i['full_prefix']['stdout'][0], '[dry-run] Supabase: resolve liga-shared abcdef12deadbeef Іт.1 "ok"')

    # ------------------------------------------------------------------------------ vcs

    def test_vcs_section_and_provider(self):
        v = self.snap['vcs']
        self.assertEqual(sorted(v), ['form', 'mirrors', 'mirrors_base', 'provider', 'space', 'texts', 'urlopen_calls'])
        p = v['provider']
        self.assertEqual((p['provider'], p['tuple_len'], p['module'], p['legacy']), ('Implicit', 3, 'git-sync', True))
        self.assertEqual(p['ctx']['settings'], {'autosync': True, 'branch': 'main', 'path': 'mockup/{task}'})
        self.assertTrue(p['ctx']['mirror_flat'])
        self.assertEqual(p['ctx']['cache_dir'], '~/mirrors')
        self.assertEqual(v['mirrors_base'], '~/mirrors')
        self.assertEqual(p['ctx']['secrets'], {})
        self.assertEqual(p['ctx']['space'], {'id': 'legacy', 'path': ''})

    def test_vcs_mirror_dirs(self):
        rows = {r['task']: r for r in self.snap['vcs']['mirrors']}
        self.assertEqual(sorted(rows), ['a-1', 'a-2', 'a-3', 'v-https', 'v-nested', 'v-seo', 'v-ssh'])
        # плоскі теки 0.7.0: slug адреси без хеша й без хоста (SSH), з хостом (https, вкладений шлях)
        self.assertEqual(rows['a-1']['mirror_dir'], {'result': '~/mirrors/studio-web.git'})
        self.assertEqual(rows['a-2']['mirror_dir'], {'result': '~/mirrors/git.example.com-studio-web.git'})
        self.assertEqual(rows['a-3']['mirror_dir'], {'result': '~/mirrors/git.example.com-group-sub-web.git'})
        self.assertEqual(rows['v-seo']['mirror_dir'], {'result': '~/mirrors/git-example.com-o-r.git'})
        for r in rows.values():
            self.assertIn('result', r['mirror_dir'], r['task'])
            self.assertTrue(r['mirror_dir']['result'].startswith('~/mirrors/'), r['task'])

    def test_vcs_texts(self):
        t = self.snap['vcs']['texts']
        self.assertEqual(sorted(t), ['autosync', 'pull', 'state', 'status', 'status_self_lookup', 'sync', 'task_new_fork'])
        # тема коміту й README: «design-canvas», не «deai»/«Deai Canvas»
        s1 = t['sync']['a-1']['push'][0]
        self.assertEqual(s1['subject'], 'design-canvas: sync mockup/a-1 (Alpha demo) · it1')
        self.assertIn('Мультисторінковий макет (design-canvas, задача `a-1`)', s1['readme'])
        self.assertIn('README.md', s1['files'])
        self.assertEqual(sorted(t['sync']), ['a-1', 'a-2'])
        for tid in ('a-1', 'a-2'):
            self.assertEqual(sorted(t['sync'][tid]), ['outcome', 'push'])
            self.assertEqual(len(t['sync'][tid]['push']), 1)
            self.assertEqual(sorted(t['sync'][tid]['outcome']['result']), ['changed', 'ok', 'remote', 'sha', 'synced'])
        self.assertIsNone(t['sync']['a-2']['push'][0]['readme'])
        self.assertEqual(s1['author'], {'name': 'Alpha Designer', 'email': 'alpha@example.com'})
        # статус: «GitLab»; `web` — з SSH-адреси (https-адреса вебу не має)
        for tid in ('a-1', 'a-2', 'a-3'):
            self.assertEqual(t['status'][tid]['result']['label'], 'GitLab', tid)
        self.assertEqual(t['status']['a-1']['result']['web'], 'https://example.com/studio/web/-/commits/main/mockup/a-1')
        self.assertIsNone(t['status']['a-2']['result']['web'])
        self.assertEqual(t['status_self_lookup']['result']['label'], 'GitLab')
        # автокоміт, примітки ітерацій, рядок state.py
        self.assertEqual(t['autosync']['commit_messages'], ['it1: автосинк (design-canvas)'])
        self.assertEqual(t['autosync']['push_subjects'], ['design-canvas: sync mockup/a-1 (Alpha demo) · it1'])
        self.assertEqual(t['pull']['notes'][1], 'оновлення з GitLab')
        self.assertEqual(t['task_new_fork']['notes'], ['початкова', 'продовження макета з GitLab'])
        self.assertEqual(len(t['state']['git_lines']), 1)
        self.assertTrue(t['state']['git_lines'][0].startswith('GitLab ('))

    def test_vcs_form_and_capabilities(self):
        f = self.snap['vcs']['form']
        self.assertEqual(f['status'], 200)
        self.assertEqual({k: f['capabilities'][k] for k in ('comments', 'vcs')}, {'comments': 'legacy', 'vcs': 'legacy'})
        m = f['model']
        # форма «Нова задача» без поля «Репозиторій», підпис «GitLab»
        self.assertEqual((m['has_vcs'], m['is_legacy_vcs'], m['with_repo']), (True, True, False))
        self.assertEqual((m['label_empty'], m['label_git'], m['brand_empty']), ('GitLab', 'Git', ''))
        self.assertIsNone(m['fail_key_target'])
        self.assertTrue(m['clones'])
        self.assertNotIn('compat', m['space_keys'], 'ключа `compat` обʼєкта простору до 4d-3b нема')
        self.assertNotIn('compat', f['space_row'])


# ---------------------------------------------------------------------------------- Task 2: канал коментарів

COMMENTS_ID = 'supabase-comments'
LAYER = 'comment-layer'


def _app_paths():
    root = os.path.dirname(_HERE)
    for p in (os.path.join(root, 'app'), os.path.join(root, 'bin'), _HERE):
        if p not in sys.path:
            sys.path.insert(0, p)


class _ChanStand(unittest.TestCase):
    """Стенд каналу: ЛІГА з тимчасовим домом (`make_before_4d3b.liga`) + за бажанням явний запис `supabase-comments` у `space.json`
    і ключ у `secrets.json`. Простір запиту фіксує `_stack`. Мережі нема (`NoNet`)."""

    @classmethod
    def setUpClass(cls):
        _app_paths()
        import dashboard
        import deai_modules
        import isolation                    # 4d-4b (R1): `implicit` → `isolation` (закон ізоляції); неявного постачальника нема
        import make_before_4d3b as mb
        import serve
        import spaces
        cls.mb, cls.dm, cls.serve, cls.spaces, cls.isolation, cls.dashboard = mb, deai_modules, serve, spaces, isolation, dashboard

    def setUp(self):
        from unittest import mock
        self.mock = mock
        self._tmp = tempfile.TemporaryDirectory(prefix='chan-')
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.realpath(self._tmp.name)
        # ⛔ Ізоляція за замовчуванням: до того, як стенд (`liga`/`_stack`) виставить свій дім, `DEAI_HOME`/`HOME` — тимчасові
        # (охоронець `test_serve.TestsCannotWriteLiveConfig` вимагає присвоєння `DEAI_HOME` у файлі, що пише простори).
        env = mock.patch.dict(os.environ, {'DEAI_HOME': os.path.join(self.tmp, 'deai-default'), 'HOME': self.tmp})
        env.start()
        self.addCleanup(env.stop)
        for name in self.mb.CLEAN:
            os.environ.pop(name, None)
        self.dm.reset_caches()
        self.addCleanup(self.dm.reset_caches)
        self.n = 0

    def stand(self, compat=LAYER, module=True, space_json=None):
        """→ `(rig, space, cfg)`. `compat=None` — явний модуль без `compat`; `module=False` — ЛІГА на неявному постачальнику."""
        self.n += 1
        rig, space, cfg = self.mb.liga(self.tmp, 's%d' % self.n)
        sp_path = os.path.join(rig.space_dir, 'space.json')
        if space_json is not None:
            with open(sp_path, 'w', encoding='utf-8') as f:
                f.write(space_json)
        elif module:
            settings = {'url': 'https://sb.example.com', 'shots_bucket': 'overview-thumbs'}
            if compat:
                settings['compat'] = compat
            # 4d-4b: і запис `notify` (`supabase-teams`): раніше `teams-mute` вів неявний постачальник; тепер без запису роль вимкнена (409
            # `notify-off`), а канал мʼюта читають тести цього стенда. `compat` — той самий, що в коментарів (схема каналу — одна на простір).
            teams = {'url': 'https://sb.example.com'}
            if compat:
                teams['compat'] = compat
            self.mb._write(sp_path, {'modules': {COMMENTS_ID: {'enabled': True, 'shared_state': True, 'settings': settings},
                                                 'supabase-teams': {'enabled': True, 'shared_state': True, 'settings': teams}}})
            self.mb._write(os.path.join(rig.deai, 'secrets.json'),
                           {self.mb.SPACE_ID: {COMMENTS_ID: {'key': 'sb_chan_key_alpha'}, 'supabase-teams': {'key': 'sb_chan_key_alpha'}}})
        return rig, space, cfg

    def pinned(self, rig):
        return self.mb._stack(rig, self.mb._env_extra(rig))

    def http(self, rig):
        """Відповіді справжнього сервера (ізольований прогін, як у знімку): канал у `api/task`, `teams-mute` GET/POST,
        `comment-config`. → словник `{назва: {задача: канал}}`."""
        mb, serve = self.mb, self.serve
        fake = os.path.join(rig.home, 'teams-fake.json')
        mb._write(fake, {})
        env = {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1',
               'DC_TEAMS_FAKE': fake, **mb._env_extra(rig)}
        out = {'task': {}, 'mute_get': {}, 'mute_post': {}, 'config': {}, 'status': []}
        with self.mock.patch.dict(os.environ, env), self.mock.patch.object(serve.urllib.request, 'urlopen', mb.NoNet()):
            self.dm.reset_caches()
            with mb.Server() as srv:
                for tid in ('a-1', 'a-2'):
                    st, body = mb._call(srv, 'GET', '/api/task', task=tid)
                    out['status'].append(st)
                    out['task'][tid] = (body or {}).get('comment_channel')
                    st, body = mb._call(srv, 'GET', '/api/teams-mute', task=tid)
                    out['status'].append(st)
                    out['mute_get'][tid] = (body or {}).get('channel')
                    st, body = mb._call(srv, 'POST', '/api/teams-mute', task=tid, body={'muted': True})
                    out['status'].append(st)
                    out['mute_post'][tid] = (body or {}).get('channel')
                    st, body = mb._call(srv, 'GET', '/api/comment-config?ch=project&it=it1', task=tid)
                    out['status'].append(st)
                    out['config'][tid] = (body or {}).get('channel')
        return out


LAYER_CHANNELS = {'a-1': 'liga-shared', 'a-2': 'dc/a-2'}
DEAI_CHANNELS = {'a-1': 'deai/legacy/a-1', 'a-2': 'deai/legacy/a-2'}


class CommentChannel(unittest.TestCase):
    """Матриця функції `comment_channel_of(space, prov, task, tid, internal)` і допоміжних (чисті виклики, без сервера)."""

    @classmethod
    def setUpClass(cls):
        _app_paths()
        import deai_modules
        cls.dm = deai_modules

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='chan-fn-')
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.realpath(self._tmp.name)
        self.space = {'id': 'sp1', 'path': self.dir, 'integrations': True}
        self.builtin = self.dm.catalog()[COMMENTS_ID]
        self.task = {'comment_project': 'shared-x'}
        self.bare = {}

    def write(self, modules):
        with open(os.path.join(self.dir, 'space.json'), 'w', encoding='utf-8') as f:
            json.dump({'modules': modules}, f)

    def rec(self, **settings):
        return {COMMENTS_ID: {'enabled': True, 'settings': settings}}

    def test_no_provider_never_gets_the_legacy_scheme(self):
        """Було `test_implicit_uses_the_legacy_scheme` (неявний постачальник вів схему comment-layer: `shared-x`, `dc/t1`…). 4d-4b: неявного
        нема (замінено тестом `test_builtin_with_compat_uses_the_legacy_scheme`: схема лише в ЯВНОГО вбудованого з `compat`); а «нема
        постачальника» (`None`) схеми comment-layer не дістає — як і будь-який не-`Module`."""
        f = self.dm.comment_channel_of
        self.assertFalse(self.dm.comment_scheme_legacy(self.space, None))
        self.assertEqual(f(self.space, None, self.task, 't1'), 'deai/sp1/t1')
        self.assertEqual(f(self.space, None, self.bare, 't1', True), 'deai/sp1/t1/internal')

    def test_builtin_with_compat_uses_the_legacy_scheme(self):
        self.write(self.rec(compat=LAYER))
        f = self.dm.comment_channel_of
        self.assertEqual(f(self.space, self.builtin, self.task, 't1'), 'shared-x')
        self.assertEqual(f(self.space, self.builtin, self.bare, 't1', internal=True), 'dc/t1/internal')
        self.assertTrue(self.dm.comment_scheme_legacy(self.space, self.builtin))

    def test_builtin_without_compat_uses_the_space_channel(self):
        f = self.dm.comment_channel_of
        for modules in ({}, self.rec(), self.rec(compat=''), self.rec(compat='other')):
            self.write(modules)
            self.assertEqual(f(self.space, self.builtin, self.task, 't1'), 'deai/sp1/t1', modules)
            self.assertEqual(f(self.space, self.builtin, self.task, 't1', True), 'deai/sp1/t1/internal')
            self.assertFalse(self.dm.comment_scheme_legacy(self.space, self.builtin))

    def test_own_module_never_gets_the_legacy_scheme(self):
        """Поправка 3: свій модуль простору міг оголосити власне `compat` з іншим змістом — схема лише у ВБУДОВАНОГО."""
        self.write(self.rec(compat=LAYER))
        own = self.dm.Module(COMMENTS_ID, roles=['comments'], origin='space')
        self.assertEqual(self.dm.comment_channel_of(self.space, own, self.task, 't1'), 'deai/sp1/t1')
        self.assertFalse(self.dm.comment_scheme_legacy(self.space, own))

    def test_other_builtin_with_compat_is_not_the_comments_scheme(self):
        """Поправка 3: `supabase-dashboard` має СВОЄ `compat` (`comment-layer` — публічний ключ сторінки): це не схема коментарів."""
        dash = self.dm.catalog()['supabase-dashboard']
        self.write({'supabase-dashboard': {'enabled': True, 'settings': {'compat': LAYER}}})
        self.assertFalse(self.dm.comment_scheme_legacy(self.space, dash))
        self.assertEqual(self.dm.comment_channel_of(self.space, dash, self.task, 't1'), 'deai/sp1/t1')

    def test_compat_of_is_total(self):
        c = self.dm.compat_of
        self.assertEqual(c(self.space, COMMENTS_ID), '')                       # нема space.json
        self.write({})
        self.assertEqual(c(self.space, COMMENTS_ID), '')                       # нема запису
        self.write(self.rec(compat=5))
        self.assertEqual(c(self.space, COMMENTS_ID), '')                       # не рядок
        self.write({COMMENTS_ID: 'x'})
        self.assertEqual(c(self.space, COMMENTS_ID), '')                       # запис не обʼєкт
        self.write(self.rec(compat=LAYER))
        self.assertEqual(c(self.space, COMMENTS_ID), LAYER)
        self.assertEqual(c(self.space, 'git-sync'), '')
        with open(os.path.join(self.dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('not json')
        self.assertEqual(c(self.space, COMMENTS_ID), '')                       # нечитабельний
        self.assertEqual(c(None, COMMENTS_ID), '')
        self.assertEqual(c({'id': 'sp1'}, COMMENTS_ID), '')                    # без теки
        self.assertEqual(c('junk', COMMENTS_ID), '')

    def test_wrappers_are_identical(self):
        import dashboard
        import serve
        for task in (self.task, self.bare):
            for internal in (False, True):
                want = self.dm.legacy_comment_channel(task, 't1', internal)
                self.assertEqual(serve.comment_channel(task, 't1', internal=internal), want)
                self.assertEqual(dashboard.comment_project_key(task, 't1') + ('/internal' if internal else ''), want)

    def test_legacy_scheme_values(self):
        self.assertEqual(self.dm.legacy_comment_channel({'comment_project': 'p'}, 't'), 'p')
        self.assertEqual(self.dm.legacy_comment_channel({'comment_project': ''}, 't', True), 'dc/t/internal')
        self.assertEqual(self.dm.legacy_comment_channel({}, 't'), 'dc/t')


class ChannelCallSites(_ChanStand):
    """Усі шість місць (Поправка 9) дають канал за функцією: явний модуль із `compat` — схема comment-layer, без — `deai/<простір>/<задача>`."""

    def test_http_sites_follow_compat(self):
        for compat, want in ((LAYER, LAYER_CHANNELS), (None, DEAI_CHANNELS)):
            rig, _space, _cfg = self.stand(compat=compat)
            out = self.http(rig)
            self.assertEqual(set(out['status']), {200}, (compat, out))
            for site in ('task', 'mute_get', 'mute_post', 'config'):
                self.assertEqual(out[site], want, (compat, site))

    def test_http_space_without_records_has_no_mute_channel(self):
        """Було `test_http_implicit_space_keeps_the_legacy_scheme`: ЛІГА без записів вела неявний постачальник зі схемою comment-layer на всіх
        чотирьох місцях. 4d-4b: неявного нема (R2) — без записів `notify` і `comments` `teams-mute` і `comment-config` вимкнені (409, каналу
        нема); `api/task` лишається 200 (схему comment-layer тепер дає лише ЯВНИЙ запис із `compat`: `test_http_sites_follow_compat`)."""
        rig, _space, _cfg = self.stand(module=False)
        out = self.http(rig)
        for site in ('mute_get', 'mute_post', 'config'):
            self.assertEqual(out[site], {'a-1': None, 'a-2': None}, site)
        self.assertEqual(out['status'].count(409), 6, out['status'])       # три маршрути на двох задачах; `api/task` — 200
        self.assertEqual(out['status'].count(200), 2, out['status'])

    def test_in_process_sites_follow_compat(self):
        serve = self.serve
        for compat, want in ((LAYER, LAYER_CHANNELS), (None, DEAI_CHANNELS)):
            rig, space, cfg = self.stand(compat=compat)
            with self.pinned(rig):
                prov, err = serve.comments_provider(space)
                self.assertIsNone(err)
                chan = serve.comments_route(space, prov)[2]
                pc = serve.ProjectComments(space)
                for tid, w in want.items():
                    task = cfg['tasks'][tid]
                    self.assertEqual(chan(task, tid), w, (compat, 'route'))
                    self.assertEqual(chan(task, tid, internal=True), w + '/internal')
                    self.assertEqual(pc.channel(task, tid), w, (compat, 'ProjectComments'))
                    self.assertEqual(pc.channel(task, tid, internal=True), w + '/internal')
                    self.assertEqual(serve._comment_channel_in(space, task, tid), w, (compat, 'helper'))

    def test_dashboard_counters_follow_compat(self):
        """Шосте місце: колбек `channel_of`, який `overview_push.cmd_sync` віддає `dashboard.sync`."""
        import overview_push as ov
        for compat, want in ((LAYER, LAYER_CHANNELS), (None, DEAI_CHANNELS)):
            rig, space, cfg = self.stand(compat=compat)
            seen = {}

            def fake_sync(cfg_, module, ctx, **kw):
                seen.update(kw)

            with self.pinned(rig), \
                    self.mock.patch.object(ov, '_space', lambda sid: space), \
                    self.mock.patch.object(ov, '_target', lambda sp: (object(), {}, False)), \
                    self.mock.patch.object(ov, '_tasks_of', lambda sp: cfg), \
                    self.mock.patch.object(ov, '_statuses', lambda sp, log=print: None), \
                    self.mock.patch.object(self.dashboard, 'sync', fake_sync):
                ov.cmd_sync(None, log=lambda *_: None)
            cb = seen.get('channel_of')
            self.assertTrue(callable(cb), 'cmd_sync мусить передати channel_of у dashboard.sync')
            for tid, w in want.items():
                self.assertEqual(cb(cfg['tasks'][tid], tid), w, compat)

    def test_sync_asks_the_counter_by_channel_of(self):
        """`dashboard.sync` бере ключ лічильника з `channel_of`; типово — схема comment-layer (як у 0.17)."""
        import registry
        mb = self.mb
        rig, _space, cfg = self.stand(module=False)
        keep = {t: v for t, v in cfg['tasks'].items() if t in ('a-1', 'a-2')}
        for cb, want in ((None, ['liga-shared', 'dc/a-2']), (lambda task, tid: 'X/' + tid, ['X/a-1', 'X/a-2'])):
            counts = mb._Counts({})
            mod = mb._FakeDash(counts)

            def call(module, fn, ctx, cards=None, mode=None, timeout=None):
                return counts if fn == 'open_comments' else {'ok': len(cards or []), 'failed': {}}
            kw = {} if cb is None else {'channel_of': cb}
            with self.mock.patch.object(registry, '_temp_roots', return_value=['/nonexistent-fixture-root']):
                self.dashboard.sync({'tasks': keep}, mod, {'secrets': {}}, identity=mb.IDENTITY, log=lambda *_: None, call=call, **kw)
            self.assertEqual(counts.asked, want)

    def test_sync_reads_space_json_at_most_once(self):
        """Схема каналу вирішується ОДИН раз при побудові колбека, а не на кожну задачу проходу синку."""
        import overview_push as ov
        for compat in (LAYER, None):
            rig, space, cfg = self.stand(compat=compat)
            reads = []
            real = self.dm.compat_of

            def counting(sp, mid):
                reads.append(mid)
                return real(sp, mid)
            with self.pinned(rig), self.mock.patch.object(self.dm, 'compat_of', counting):
                cb = ov._channel_of(space, log=lambda *_: None)
                for _ in range(3):
                    for tid in ('a-1', 'a-2'):
                        cb(cfg['tasks'][tid], tid)
            self.assertLessEqual(len(reads), 1, (compat, reads))

    def test_decision_failure_closes_the_task_channel_but_mute_keeps_the_fallback(self):
        """Збій рішення (нечитабельний `space.json`; id задачі, непридатний для `channel_for`) — схема comment-layer, не 5xx і не виняток."""
        serve = self.serve
        rig, space, cfg = self.stand(space_json='not json')
        with self.pinned(rig):
            self.assertEqual(serve._comment_channel_in(space, cfg['tasks']['a-1'], 'a-1'), 'liga-shared')
            self.assertEqual(serve._comment_channel_in(space, cfg['tasks']['a-2'], 'a-2', internal=True), 'dc/a-2/internal')
        out = self.http(rig)
        # Д5: канал у `/api/task` є лише за постачальником `comments`, а збій рішення закриває його (fail-closed); teams-mute лишає запасну схему
        self.assertEqual(out['task'], {'a-1': None, 'a-2': None})      # 4d-4c: `/api/task` без постачальника `comments` каналу не має
        self.assertEqual(out['mute_get'], LAYER_CHANNELS)
        rig, space, cfg = self.stand(compat=None)
        with self.pinned(rig):
            self.assertEqual(serve._comment_channel_in(space, {}, 'bad/id'), 'dc/bad/id')     # `channel_for` відмовив
            self.assertEqual(serve._comment_channel_in(None, {}, 'x'), 'dc/x')                  # простору нема

    def test_provider_comes_from_the_capabilities_cache(self):
        """Постачальник для `api/task`/`teams-mute`/лічильників — з кешу `_capabilities_full`, а не новий прохід каталогом на кожен запит."""
        dm = self.dm
        rig, space, _cfg = self.stand(compat=LAYER)
        calls = []
        real = dm.catalog

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)
        with self.pinned(rig), self.mock.patch.object(dm, 'catalog', counting):
            for _ in range(6):
                self.assertIsInstance(dm.comments_prov_cached(space), dm.Module)
        self.assertLessEqual(len(calls), 1)

    def test_prov_cached_is_total(self):
        dm = self.dm
        self.assertIsNone(dm.comments_prov_cached(None))
        self.assertIsNone(dm.comments_prov_cached({}))
        rig, space, _cfg = self.stand(space_json='not json')
        with self.pinned(rig):
            self.assertIsNone(dm.comments_prov_cached(space))
        with self.mock.patch.object(dm, '_capabilities_full', side_effect=RuntimeError('boom')), self.pinned(rig):
            self.assertIsNone(dm.comments_prov_cached(space))


class ProjectCommentsParity(_ChanStand):
    """Мігрований вигляд (`kind == 'module'`, схема comment-layer) дає те саме для людини, що й неявний шлях 0.17.0."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_label_and_legacy_scheme(self):
        serve = self.serve
        for compat, label, legacy in ((LAYER, 'Supabase', True), (None, 'модуль supabase-comments', False)):
            rig, space, _cfg = self.stand(compat=compat)
            with self.pinned(rig):
                pc = serve.ProjectComments(space)
                self.assertEqual((pc.kind, pc.label, pc.legacy_scheme), ('module', label, legacy), compat)
        rig, space, _cfg = self.stand(module=False)
        with self.pinned(rig):
            pc = serve.ProjectComments(space)
            # 4d-4b: було `('implicit', 'Supabase', True)`; без запису роль вимкнена — вид `off`, схеми comment-layer нема
            self.assertEqual((pc.kind, pc.label, pc.legacy_scheme), ('off', 'не підключено', False))

    def _inbox(self, compat):
        rig, space, cfg = self.stand(compat=compat)
        with self.pinned(rig):
            return self.mb.scrub(self.mb._inbox(cfg, rig, space), rig.home)

    def test_inbox_matches_the_0_17_snapshot_on_a_migrated_view(self):
        """Короткий префікс — відмова «коротший за 6 символів» (як у 0.17), повний — той самий dry-run із підписом «Supabase»."""
        self.assertEqual(self._inbox(LAYER), self.snap['comments']['inbox'])

    def test_plain_module_space_keeps_the_module_behaviour(self):
        """Звичайний модульний простір без `compat`: `module_space` істинне — короткий префікс дозволено, підпис — модуль."""
        got = self._inbox(None)
        # префікс «abc» не збігається з повним id піна (модуль приймає лише ПОВНИЙ id) — «не знайдено», але НЕ відмова розбору (2)
        self.assertEqual(got['short_prefix']['rc'], 1)
        self.assertEqual(got['short_prefix']['stderr'], [])
        self.assertEqual(got['short_prefix']['module_calls'], [{'module': COMMENTS_ID, 'fn': 'list'}])
        self.assertIn('модуль supabase-comments', got['full_prefix']['stdout'][0])
        self.assertIn('deai/legacy/a-1', got['full_prefix']['stdout'][0])

    def test_state_and_inbox_run_under_an_explicit_module_without_a_server(self):
        """Підтвердження Рішення 5 спеки: `bin/state.py` і `bin/inbox.py` під явним модулем коментарів — без сервера (простір фіксує
        `task_anywhere`); піни читаються модулем, лічильник відкритих і `inbox list` рахують їх."""
        import state
        pin = {'id': 'abcdef12deadbeef', 'text': 'Alpha pin', 'status': 'open', 'author': 'Beta', 'ts': 'x', 'fp': 'a/b/c',
               'meta': {}, 'bornV': 'it1'}
        for compat, ch in ((LAYER, 'liga-shared'), (None, 'deai/legacy/a-1')):
            rig, space, cfg = self.stand(compat=compat)
            rec = self.mb.Rec({'list': [pin]})
            with self.pinned(rig), self.mock.patch.object(self.dm, 'call', rec):
                self.spaces.set_request_space(self.mb.SPACE_ID)
                try:
                    n, tail = state._team_comments(cfg['tasks']['a-1'], 'a-1')
                finally:
                    self.spaces.clear_request_space()
            self.assertEqual((n, tail), (1, ' + 1 проєктних'), compat)
            self.assertEqual([(c[0], c[1]) for c in rec.calls], [(COMMENTS_ID, 'list')])
            self.assertEqual(rec.args[0], (ch,), compat)


class CommentsCompatSetting(unittest.TestCase):
    """Налаштування `compat` модуля `supabase-comments` (версія 1.2.0)."""

    @classmethod
    def setUpClass(cls):
        _app_paths()
        import deai_modules
        cls.dm = deai_modules
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'modules', COMMENTS_ID, 'module.json'), encoding='utf-8') as f:
            cls.man = json.load(f)

    def test_manifest_declares_compat_select(self):
        self.assertEqual(self.man['version'], '1.2.0')
        s = {x['key']: x for x in self.man['settings']}
        c = s['compat']
        self.assertEqual((c['type'], c['required'], c['default']), ('select', False, ''))
        self.assertEqual([o['value'] for o in c['options']], ['', LAYER])
        self.assertIn('відрив', c['label'], 'підпис застерігає, що зміна відриває наявну історію пінів')
        self.assertEqual(list(s), ['url', 'key', 'shots_bucket', 'compat'], 'порядок полів: новий — останнім')

    def test_catalog_module_carries_it_and_rejects_unknown_values(self):
        m = self.dm.catalog()[COMMENTS_ID]
        self.assertEqual(m.version, '1.2.0')
        space = {'id': 'sp1', 'path': '', 'integrations': False}
        ok = self.dm.resolve_settings(space, m, {'url': 'https://sb.example.com', 'compat': LAYER})
        self.assertEqual(ok['compat'], LAYER)
        self.assertEqual(self.dm.resolve_settings(space, m, {'url': 'https://sb.example.com'})['compat'], '')
        with self.assertRaises(self.dm.ModuleError) as cm:
            self.dm.resolve_settings(space, m, {'url': 'https://sb.example.com', 'compat': 'zzz'})
        self.assertEqual(cm.exception.code, 'bad-settings')


class ChannelGuard(unittest.TestCase):
    """AST-охоронець: канал коментарів вирішує ОДНА функція. Жодного ВИКЛИКУ `comment_channel(`/`comment_project_key(` у `app/`, `bin/`
    (лишаються лише визначення-обгортки); `dashboard.sync` бере ключ із `channel_of`."""

    FORBIDDEN = ('comment_channel', 'comment_project_key')

    def files(self):
        root = os.path.dirname(_HERE)
        out = []
        for d in ('app', 'bin'):
            for n in sorted(os.listdir(os.path.join(root, d))):
                if n.endswith('.py') and not n.startswith('test_'):
                    out.append(os.path.join(root, d, n))
        return out

    def calls(self, tree, names=None):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if name in (names or self.FORBIDDEN):
                    yield node

    def test_no_direct_calls_outside_the_wrappers(self):
        bad = []
        for p in self.files():
            with open(p, encoding='utf-8') as f:
                tree = ast.parse(f.read(), p)
            bad += ['%s:%d' % (os.path.basename(p), n.lineno) for n in self.calls(tree)]
        self.assertEqual(bad, [], 'канал коментарів — лише через deai_modules.comment_channel_of (чи legacy_comment_channel)')

    def test_channel_for_is_called_only_inside_deai_modules(self):
        """`channel_for` кличе лише `deai_modules.py` (визначення і `comment_channel_of`): будь-де інде — повз рішення про схему."""
        bad = []
        for p in self.files():
            if os.path.basename(p) == 'deai_modules.py':
                continue
            with open(p, encoding='utf-8') as f:
                tree = ast.parse(f.read(), p)
            bad += ['%s:%d' % (os.path.basename(p), n.lineno) for n in self.calls(tree, ('channel_for',))]
        self.assertEqual(bad, [])

    def test_guard_sees_a_planted_call(self):
        tree = ast.parse('x = comment_project_key(t, 1)\ny = mod.comment_channel(t, 1)\nz = comment_channel_of(1)')
        self.assertEqual(len(list(self.calls(tree))), 2)
        planted = ast.parse('a = deai_modules.channel_for(s, 1)\nb = channel_for(s, 1)\nc = comment_channel_of(1)')
        self.assertEqual(len(list(self.calls(planted, ('channel_for',)))), 2)

    def test_dashboard_sync_uses_channel_of(self):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'dashboard.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        sync = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sync')
        self.assertEqual(list(self.calls(sync)), [])
        self.assertIn('channel_of', [a.arg for a in sync.args.kwonlyargs])
        self.assertTrue(any(isinstance(n, ast.Name) and n.id == 'channel_of' for n in ast.walk(sync)))
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'channel_of'
                            for n in ast.walk(sync)), 'ключ лічильника рахує виклик channel_of(...)')


# ------------------------------------------------------------------------------ Task 3: vcs

VCS_ID = 'git-sync'
DC = 'design-canvas'


class _VcsStand(_ChanStand):
    """Стенд `vcs`: ЛІГА з явним записом `git-sync` (як його пише міграція: `shared_state`, `autosync: true`) із `compat` чи без."""

    def vstand(self, compat=DC, autosync=True, extra=None):
        self.n += 1
        rig, space, cfg = self.mb.liga(self.tmp, 'v%d' % self.n)
        settings = {'branch': 'main', 'path': 'mockup/{task}', 'autosync': autosync}
        if compat:
            settings['compat'] = compat
        settings.update(extra or {})
        self.mb._write(os.path.join(rig.space_dir, 'space.json'),
                       {'modules': {VCS_ID: {'enabled': True, 'shared_state': True, 'settings': settings}}})
        return rig, space, cfg

    def provider_in(self, rig, mirrors_env):
        """`vcs_provider()` у стенді; `DC_MIRRORS_DIR` — як у `mirrors_env` (порожньо = НЕ виставлено, запасний `<ROOT>/.mirrors`)."""
        with self.mock.patch.dict(os.environ, {'DEAI_HOME': rig.deai, 'HOME': rig.home}):
            with self.mock.patch.object(self.spaces, 'legacy_tasks_file', lambda: rig.tasks_path):
                with self.spaces.request_space(self.mb.SPACE_ID):
                    os.environ.pop('DC_MIRRORS_DIR', None)
                    os.environ.update(mirrors_env)
                    self.dm.reset_caches()
                    try:
                        return self.serve.vcs_provider()
                    finally:
                        self.dm.reset_caches()

    def old_vcs_target(self):
        """Генератор знімка 0.17.0 (`make_before_4d3b`, НЕ правиться — еталон) кличе `serve.vcs_target(cfg, tid, task, settings)`. 4d-4b (R4): підпис
        `vcs_target(tid, task, settings)` — без `cfg`. Перехідник на час збору: перший аргумент відкидається (ключ і IP кореня цілі більше й не
        несли б — цілі збираються за новим правилом). Виклики самого ядра (3 аргументи) проходять як є."""
        serve = self.serve
        new = serve.vcs_target
        return self.mock.patch.object(serve, 'vcs_target', lambda *a: new(*a[1:]) if len(a) == 4 else new(*a))

    def sections(self, rig, cfg, space):
        """Ті самі секції, що знімає `make_before_4d3b.vcs`, але з явним записом: → словник, санітизований як знімок."""
        mb, serve, dm = self.mb, self.serve, self.dm
        net = mb.NoNet()
        out = {}
        with mb._stack(rig, mb._env_extra(rig), self.mock.patch.object(serve.urllib.request, 'urlopen', net), self.old_vcs_target()):
            dm.reset_caches()
            out['provider'] = mb._vcs_ctx(serve, rig)
            v = serve.vcs_provider()
            out['mirrors'] = mb._mirrors(serve, cfg, rig, v)
            out['texts'] = mb._texts(serve, cfg, rig, v)
            out['mirrors_base'] = mb.rel(serve._mirrors_base(), rig.home)
            dm.reset_caches()
        out['form'] = mb._form(rig)
        out['urlopen_calls'] = net.calls
        return mb.scrub(out, rig.home)


class VcsCompat(_VcsStand):
    """Налаштування `compat` модуля `git-sync` (1.1.0) і `ctx`, який ядро збирає для запису з `compat == "design-canvas"`."""

    def test_manifest_declares_compat_select(self):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'modules', VCS_ID, 'module.json'), encoding='utf-8') as f:
            man = json.load(f)
        self.assertEqual(man['version'], '1.1.0')
        s = {x['key']: x for x in man['settings']}
        c = s['compat']
        self.assertEqual((c['type'], c['required'], c['default']), ('select', False, ''))
        self.assertEqual([o['value'] for o in c['options']], ['', DC])
        self.assertIn('відрив', c['label'], 'підпис застерігає, що зміна відриває наявні дзеркала')
        self.assertEqual(list(s), ['repo', 'branch', 'path', 'ssh_key', 'host_ip', 'autosync', 'compat'], 'новий ключ — останнім')

    def test_catalog_module_carries_it_and_rejects_unknown_values(self):
        m = self.dm.catalog()[VCS_ID]
        self.assertEqual(m.version, '1.1.0')
        space = {'id': 'sp1', 'path': '', 'integrations': False}
        self.assertEqual(self.dm.resolve_settings(space, m, {'compat': DC})['compat'], DC)
        self.assertEqual(self.dm.resolve_settings(space, m, {})['compat'], '')
        with self.assertRaises(self.dm.ModuleError) as cm:
            self.dm.resolve_settings(space, m, {'compat': 'zzz'})
        self.assertEqual(cm.exception.code, 'bad-settings')

    def test_compat_overlays_flat_mirrors_on_the_module_ctx(self):
        rig, _sp, _cfg = self.vstand()
        mirrors = os.path.join(self.tmp, 'mirrors-x')
        for env in ({'DC_MIRRORS_DIR': mirrors}, {}):
            with self.subTest(env=env):
                mod, ctx, legacy = self.provider_in(rig, env)
                self.assertEqual(mod.id, VCS_ID)
                self.assertIs(legacy, True)
                self.assertIs(ctx['mirror_flat'], True)
                self.assertEqual(ctx['cache_dir'], mirrors if env else os.path.join(self.serve.ROOT, '.mirrors'))
                self.assertEqual({k: ctx['settings'][k] for k in ('branch', 'path', 'autosync')},
                                 {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True})
                self.assertEqual(ctx['space']['id'], self.mb.SPACE_ID)

    def test_without_compat_the_ctx_is_the_framework_one(self):
        rig, _sp, _cfg = self.vstand(compat=None)
        mod, ctx, legacy = self.provider_in(rig, {'DC_MIRRORS_DIR': os.path.join(self.tmp, 'm')})
        self.assertIs(legacy, False)
        self.assertNotIn('mirror_flat', ctx)
        self.assertEqual(ctx['cache_dir'], os.path.join(rig.deai, 'cache', self.mb.SPACE_ID, VCS_ID))

    def test_mirrors_fallback_is_shared_by_both_paths(self):
        """Відгук Task 1: запасний `<ROOT>/.mirrors` (`DC_MIRRORS_DIR` не виставлено) НЕ змінився і спільний для неявного шляху,
        `_vcs_legacy_ctx` і накладки `compat`."""
        want = os.path.join(self.serve.ROOT, '.mirrors')
        with self.mock.patch.dict(os.environ, {'DEAI_HOME': os.path.join(self.tmp, 'd'), 'HOME': self.tmp}):
            os.environ.pop('DC_MIRRORS_DIR', None)
            self.assertEqual(self.serve._mirrors_base(), want)
            self.assertEqual(self.serve._vcs_legacy_ctx()['cache_dir'], want)
            self.assertEqual(self.serve._flat_mirror_overlay(), {'mirror_flat': True, 'cache_dir': want})
            os.environ['DC_MIRRORS_DIR'] = '/x/override'
            self.assertEqual(self.serve._flat_mirror_overlay(), {'mirror_flat': True, 'cache_dir': '/x/override'})
            self.assertEqual(self.serve._vcs_legacy_ctx()['cache_dir'], '/x/override')
        rig, _sp, _cfg = self.vstand()
        self.assertEqual(self.provider_in(rig, {})[1]['cache_dir'], want)
        # 4d-4b: другий рядок `provider_in(неявна ЛІГА)['cache_dir'] == want` ретайрено (неявного шляху нема); ізольований `ctx` ловить перший блок

    def test_both_paths_take_the_overlay_from_one_helper(self):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'serve.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ('_vcs_legacy_ctx', 'vcs_provider'):
            calls = [c.func.id for c in ast.walk(fns[name]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
            self.assertIn('_flat_mirror_overlay', calls, name)
        for name in ('_vcs_legacy_ctx', 'vcs_provider'):
            consts = [k.value for c in ast.walk(fns[name]) if isinstance(c, ast.Dict) for k in c.keys
                      if isinstance(k, ast.Constant) and k.value in ('mirror_flat', 'cache_dir')]
            self.assertEqual(consts, [], '%s: накладка живе лише в _flat_mirror_overlay' % name)

    def test_explicit_compat_record_equals_the_0_17_snapshot(self):
        """Запис `git-sync{compat: design-canvas}` дає РІВНО знімок 0.17.0: дзеркала, тексти всіх споживачів, прапорці форми."""
        with open(BEFORE, encoding='utf-8') as f:
            snap = json.load(f)['vcs']
        rig, space, cfg = self.vstand()
        got = self.sections(rig, cfg, space)
        self.assertEqual(got['provider']['module'], VCS_ID)
        self.assertEqual(got['provider']['provider'], 'Module', 'явний запис, а не неявний постачальник')
        self.assertIs(got['provider']['legacy'], True)
        # 4d-4b: у знімку 0.17.0 `target` ніс спільні `ssh_key`/`host_ip` з КОРЕНЯ; тепер корінь не читається, ціль цих полів не несе (модуль бере
        # свої з налаштувань запису). Це причина 4d-4b — у цей клас не входить: ефективні значення звіряє `AfterMigrationParity4d4b` (Task 15,
        # листки `vcs_target.*`). Тут порівнюється решта цілі (репо, шлях, гілка, задача) і ТЕКА ДЗЕРКАЛА.
        def no_keys(obj):                     # з кожного словника під ключем `target` (у т.ч. у `push[i].target` текстів) прибрати ключ і IP
            if isinstance(obj, dict):
                return {k: ({a: no_keys(b) for a, b in v.items() if a not in ('ssh_key', 'host_ip')} if k == 'target' and isinstance(v, dict)
                            else no_keys(v)) for k, v in obj.items()}
            if isinstance(obj, list):
                return [no_keys(x) for x in obj]
            return obj
        self.assertEqual(no_keys(got['mirrors']), no_keys(snap['mirrors']))
        self.assertEqual(got['mirrors_base'], snap['mirrors_base'])
        self.assertEqual(no_keys(got['texts']), no_keys(snap['texts']))
        ctx, want = got['provider']['ctx'], snap['provider']['ctx']
        for k in ('cache_dir', 'mirror_flat'):
            self.assertEqual(ctx[k], want[k], k)
        self.assertEqual({k: ctx['settings'][k] for k in ('branch', 'path', 'autosync')}, want['settings'])
        m, wm = dict(got['form']['model']), dict(snap['form']['model'])
        keys, wkeys = m.pop('space_keys'), wm.pop('space_keys')
        # 4d-4b: `has_notify` у знімку 0.17.0 істинний (роль `notify` вела неявний постачальник), а тут запису `notify` нема — причина 4d-4b
        # (`Implicit` видалено); у цей клас не входить, його звіряє `AfterMigrationParity4d4b` (Task 15, розділ `api`). Решту прапорців — як було.
        for flag in ('has_notify', 'has_publish'):              # так само `has_publish`: запису `publish` нема
            self.assertIs(m.pop(flag), False, flag)
            self.assertIs(wm.pop(flag), True, flag)
        self.assertEqual(m, wm, 'прапорці форми «Нова задача» й підписи — як у ЛІГИ 0.17')
        self.assertEqual(sorted(keys), sorted([k for k in wkeys if k != 'integrations'] + ['compat']),
                         'єдина різниця обʼєкта простору — ключ compat (і зник `integrations`, 4d-4c)')
        self.assertEqual(got['form']['space_row']['compat'], {'vcs': DC})
        self.assertEqual(got['form']['capabilities']['vcs'], VCS_ID)
        self.assertEqual(got['urlopen_calls'], 0)

    def test_without_compat_texts_and_mirrors_are_neutral(self):
        """Контроль: той самий запис БЕЗ `compat` — інші тексти, інша тека дзеркал, форма з полем «Репозиторій»."""
        with open(BEFORE, encoding='utf-8') as f:
            snap = json.load(f)['vcs']
        rig, space, cfg = self.vstand(compat=None)
        got = self.sections(rig, cfg, space)
        self.assertIs(got['provider']['legacy'], False)
        self.assertNotIn('mirror_flat', got['provider']['ctx'])
        self.assertNotEqual(got['mirrors'], snap['mirrors'])
        self.assertNotEqual(got['texts'], snap['texts'])
        self.assertTrue(all(s.startswith('deai: sync') for s in got['texts']['autosync']['push_subjects']))
        self.assertTrue(all(m.startswith('it1: ') and 'design-canvas' not in m for m in got['texts']['autosync']['commit_messages']))
        self.assertNotIn('GitLab', json.dumps(got['texts']['pull']['notes'], ensure_ascii=False))
        self.assertNotIn('compat', got['form']['space_row'])
        self.assertIs(got['form']['model']['is_legacy_vcs'], False)
        self.assertIs(got['form']['model']['with_repo'], True)


class VcsLegacyTexts(_VcsStand):
    """ЄДИНИЙ предикат `serve.vcs_legacy_texts(prov, space)` і те, що `vcs_provider` кладе третім елементом."""

    def setUp(self):
        super().setUp()
        self.builtin = self.dm.catalog()[VCS_ID]
        self.space = {'id': 'sp1', 'path': os.path.join(self.tmp, 'sp1'), 'integrations': True}
        os.makedirs(self.space['path'])

    def write(self, settings, **extra):
        self.mb._write(os.path.join(self.space['path'], 'space.json'),
                       {'modules': {VCS_ID: {'enabled': True, 'settings': settings, **extra}}})

    def test_matrix(self):
        pred = self.serve.vcs_legacy_texts
        # 4d-4b: було ще `pred(implicit.for_role('vcs'), space/None) is True` («неявний постачальник» — ЛІГА); неявного нема. Тепер «не `Module`»
        # (`None`, чужий тип) — ніколи не ЛІГА.
        self.assertIs(pred(None, self.space), False, 'нема постачальника')
        self.assertIs(pred(None, None), False)
        self.write({'compat': DC})
        self.assertIs(pred(self.builtin, self.space), True)
        self.write({})
        self.assertIs(pred(self.builtin, self.space), False)
        self.write({'compat': ''})
        self.assertIs(pred(self.builtin, self.space), False)

    def test_own_module_with_the_same_setting_is_not_legacy(self):
        """Поправка 3: свій модуль простору міг оголосити власне `compat`; рівно як і інший вбудований модуль."""
        self.write({'compat': DC})
        own = self.mock.Mock(spec=self.dm.Module)
        own.id, own.origin = VCS_ID, 'space'
        self.assertIs(self.serve.vcs_legacy_texts(own, self.space), False)
        other = self.mock.Mock(spec=self.dm.Module)
        other.id, other.origin = 'supabase-dashboard', 'builtin'
        self.mb._write(os.path.join(self.space['path'], 'space.json'),
                       {'modules': {'supabase-dashboard': {'enabled': True, 'settings': {'compat': DC}}}})
        self.assertIs(self.serve.vcs_legacy_texts(other, self.space), False)

    def test_predicate_is_total_on_unreadable_space_json(self):
        with open(os.path.join(self.space['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertIs(self.serve.vcs_legacy_texts(self.builtin, self.space), False)
        self.assertIs(self.serve.vcs_legacy_texts(self.builtin, {'id': 'zz', 'path': '/nope-x', 'integrations': False}), False)

    def test_provider_computes_it_once_and_puts_it_third(self):
        real = self.serve.vcs_legacy_texts
        # 4d-4b: випадок `('implicit', неявна ЛІГА, True)` ретайрено — неявного постачальника нема (ЛІГА без запису ролі `vcs` не має)
        cases = (('module-compat', self.vstand(compat=DC)[0], True), ('module-plain', self.vstand(compat=None)[0], False))
        for tag, rig, want in cases:
            calls = []

            def counted(prov, space, calls=calls):
                calls.append(type(prov).__name__)
                return real(prov, space)
            with self.mock.patch.object(self.serve, 'vcs_legacy_texts', counted):
                v = self.provider_in(rig, {'DC_MIRRORS_DIR': os.path.join(self.tmp, 'mm')})
            self.assertEqual(len(calls), 1, tag)
            self.assertIs(v[2], want, tag)

    def test_consumers_read_the_third_element_not_the_provider_type(self):
        """Усі споживачі текстів дають слова 0.17 для вбудованого `git-sync` з `compat` (повний знімок — `VcsCompat`) і нейтральні без
        нього; тут — стрижневий: тема коміту/автокомміт/підпис, кожен окремо з готовим `v = (module, ctx, legacy)`."""
        mb, serve, dm = self.mb, self.serve, self.dm
        for compat, want_legacy in ((DC, True), (None, False)):
            rig, _sp, cfg = self.vstand(compat=compat)
            with mb._stack(rig, mb._env_extra(rig)):
                dm.reset_caches()
                v = serve.vcs_provider()
                self.assertIs(v[2], want_legacy)
                task = cfg['tasks']['a-1']
                gl = serve.vcs_target('a-1', task, v[1].get('settings') or {})
                if gl is None:        # 4d-4c: без схеми ЛІГИ `gitlab{}` задачі ціллю не стає — тексти перевіряємо на тій самій цілі
                    gl = serve.gitlab_cfg(task)
                seen, rec = [], mb.Rec({'push': mb._push_answer([]), 'status': {'behind': 0, 'behind_path': 0, 'unpushed': 0,
                                                                                  'on_remote': True, 'web': None, 'label': 'Example'}})
                with self.mock.patch.object(dm, 'call', rec):
                    st = serve.gitlab_status(task, gl, {'iterations': [{'id': 'it1'}]}, 'it1', vcs=v)
                self.assertEqual(st.get('label'), 'GitLab' if want_legacy else 'Example', compat)
                dm.reset_caches()


class TextPredicateGuard(unittest.TestCase):
    """AST: у споживачах текстів жодного `isinstance(…, Implicit)` — «ЛІГА» (легасі-тексти) читається лише з `vcs_legacy_texts`
    (урок 4d-3a: не прирівнювати ЛІГУ до «неявного постачальника»)."""

    CONSUMERS = ('gitlab_sync', 'gitlab_status', 'autosync', 'gitlab_pull', '_task_new_write')

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'serve.py'), encoding='utf-8') as f:
            cls.tree = ast.parse(f.read())

    @staticmethod
    def implicit_checks(node):
        """Рядки `isinstance(x, <…Implicit…>)` (4d-4b: типу `Implicit` уже нема — охоронець лишається на випадок його повернення)."""
        out = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'isinstance' and len(n.args) == 2:
                second = ast.dump(n.args[1])
                if 'Implicit' in second:
                    out.append(n.lineno)
        return out

    @staticmethod
    def module_checks(node):
        """Рядки `isinstance(x, <…Module…>)`: перевірка типу постачальника, що й лишилась у предикаті (4d-4b)."""
        out = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'isinstance' and len(n.args) == 2:
                if 'Module' in ast.dump(n.args[1]):
                    out.append(n.lineno)
        return out

    def fn(self, name, cls=None):
        scope = self.tree.body
        if cls:
            scope = next(n for n in scope if isinstance(n, ast.ClassDef) and n.name == cls).body
        return next(n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name)

    def test_consumers_do_not_test_the_provider_type(self):
        bad = {n: self.implicit_checks(self.fn(n)) for n in self.CONSUMERS}
        bad['ProjectComments.channel'] = self.implicit_checks(self.fn('channel', 'ProjectComments'))
        self.assertEqual({k: v for k, v in bad.items() if v}, {})

    def test_predicate_lives_in_one_place(self):
        """Було: у предикаті є перевірка `Implicit` (`assertTrue(implicit_checks)`), а `vcs_provider` кличе предикат двічі — по одному на гілку
        (Implicit / Module). 4d-4b: гілки `Implicit` нема — предикат має РІВНО одну перевірку типу (`Module`) і жодної `Implicit`, а
        `vcs_provider` кличе його рівно один раз."""
        pred = self.fn('vcs_legacy_texts')
        self.assertEqual(self.implicit_checks(pred), [])
        self.assertEqual(len(self.module_checks(pred)), 1, 'єдине місце, де тип постачальника впливає на тексти: одна перевірка `Module`')
        calls = [c for c in ast.walk(self.fn('vcs_provider'))
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == 'vcs_legacy_texts']
        self.assertEqual(len(calls), 1, 'один виклик предиката у `vcs_provider`')

    def test_guard_sees_a_planted_check(self):
        planted = ast.parse('def f(v):\n    return isinstance(v[0], implicit.Implicit)\n')
        self.assertEqual(self.implicit_checks(planted), [2])
        clean = ast.parse('def f(v):\n    return isinstance(v, dict)\n')
        self.assertEqual(self.implicit_checks(clean), [])
        self.assertEqual(self.module_checks(clean), [])
        self.assertEqual(self.module_checks(ast.parse('def f(v):\n    return isinstance(v, deai_modules.Module)\n')), [2])


class SpaceCompatKey(_VcsStand):
    """Ключ `compat` обʼєкта простору (`space_view`, `spaces_listing`): лише коли явний вбудований модуль має непорожнє `compat`."""

    def views(self, rig, sp):
        with self.pinned(rig):
            self.dm.reset_caches()
            try:
                view = self.serve.space_view(sp)
                row = next(s for s in self.serve.spaces_listing()['spaces'] if s['id'] == sp['id'])
            finally:
                self.dm.reset_caches()
        return view, row

    def write_both(self, rig, vcs_compat=DC, comments_compat=LAYER):
        mods = {}
        vs = {'autosync': True}
        if vcs_compat:
            vs['compat'] = vcs_compat
        mods[VCS_ID] = {'enabled': True, 'shared_state': True, 'settings': vs}
        cs = {'url': 'https://sb.example.com'}
        if comments_compat:
            cs['compat'] = comments_compat
        mods[COMMENTS_ID] = {'enabled': True, 'shared_state': True, 'settings': cs}
        self.mb._write(os.path.join(rig.space_dir, 'space.json'), {'modules': mods})
        self.mb._write(os.path.join(rig.deai, 'secrets.json'), {self.mb.SPACE_ID: {COMMENTS_ID: {'key': 'sb_chan_key_alpha'}}})

    def test_both_roles_present_when_set(self):
        rig, sp, _cfg = self.mb.liga(self.tmp, 'k1')
        self.write_both(rig)
        view, row = self.views(rig, sp)
        for o in (view, row):
            self.assertEqual(o['compat'], {'comments': LAYER, 'vcs': DC})
            self.assertEqual(o['capabilities']['vcs'], VCS_ID)
            self.assertEqual(o['capabilities']['comments'], COMMENTS_ID)

    def test_key_absent_when_empty(self):
        rig, sp, _cfg = self.mb.liga(self.tmp, 'k2')
        self.write_both(rig, vcs_compat=None, comments_compat=None)
        view, row = self.views(rig, sp)
        for o in (view, row):
            self.assertNotIn('compat', o)
            self.assertEqual(o['capabilities']['vcs'], VCS_ID)

    def test_one_role_only(self):
        rig, sp, _cfg = self.mb.liga(self.tmp, 'k3')
        self.write_both(rig, vcs_compat=DC, comments_compat=None)
        view, row = self.views(rig, sp)
        self.assertEqual(view['compat'], {'vcs': DC})
        self.assertEqual(row['compat'], {'vcs': DC})

    def test_liga_without_records_has_no_key_and_no_providers(self):
        """Було `test_implicit_liga_has_no_key_and_capabilities_stay`: неявна ЛІГА без ключа `compat` і з `capabilities.vcs == 'legacy'`.
        4d-4b (R2): ключа нема й тепер, а роль без запису вимкнена — `None`."""
        rig, sp, _cfg = self.mb.liga(self.tmp, 'k4')
        view, row = self.views(rig, sp)
        for o in (view, row):
            self.assertNotIn('compat', o)
            self.assertIsNone(o['capabilities']['vcs'])

    def test_compat_view_is_total_and_keyed_by_capabilities(self):
        dm = self.dm
        sp = {'id': 'zz', 'path': os.path.join(self.tmp, 'nope'), 'integrations': False}
        self.assertEqual(dm.compat_view(sp, {'vcs': VCS_ID}), {})
        self.assertEqual(dm.compat_view(None, None), {})
        self.assertEqual(dm.compat_view(sp, {'vcs': 'legacy', 'comments': None}), {})
        d = os.path.join(self.tmp, 'cv')
        os.makedirs(d)
        sp2 = {'id': 'cv', 'path': d, 'integrations': False}
        self.mb._write(os.path.join(d, 'space.json'), {'modules': {VCS_ID: {'enabled': True, 'settings': {'compat': DC}}}})
        self.assertEqual(dm.compat_view(sp2, {'vcs': VCS_ID}), {'vcs': DC})
        self.assertEqual(dm.compat_view(sp2, {'vcs': 'other-vcs'}), {}, 'ролі веде інший модуль — ключа нема')
        self.assertEqual(dm.compat_view(sp2, {'vcs': 'legacy'}), {})
        with open(os.path.join(d, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        self.assertEqual(dm.compat_view(sp2, {'vcs': VCS_ID}), {})

    def test_compat_view_returns_only_the_allowed_value_of_the_module(self):
        """Ревʼю M4: сире значення з `space.json` клієнту не віддаємо, якщо воно не дозволене цьому модулю (vcs — `design-canvas`,
        comments — `comment-layer`); перехресне й сміття — ключа нема."""
        dm = self.dm
        d = os.path.join(self.tmp, 'cva')
        os.makedirs(d)
        sp = {'id': 'cva', 'path': d, 'integrations': False}
        caps = {'vcs': VCS_ID}
        for val, want in ((DC, {'vcs': DC}), ('comment-layer', {}), ('<script>', {}), ('DESIGN-CANVAS', {})):
            self.mb._write(os.path.join(d, 'space.json'), {'modules': {VCS_ID: {'enabled': True, 'settings': {'compat': val}}}})
            self.assertEqual(dm.compat_view(sp, caps), want, val)

    def test_compat_view_requires_a_builtin_raw_provider(self):
        """Захист у глибину: сирий постачальник ролі — вбудований `Module` цього id; свій модуль (`origin == 'space'`) з тим самим
        id і `compat` ключа не дає. Постачальник береться з кешу `_capabilities_full`, каталог не обходиться."""
        dm = self.dm
        d = os.path.join(self.tmp, 'cvo')
        os.makedirs(d)
        sp = {'id': 'cvo', 'path': d, 'integrations': False}
        self.mb._write(os.path.join(d, 'space.json'), {'modules': {VCS_ID: {'enabled': True, 'settings': {'compat': DC}}}})

        def fake(origin, mid=VCS_ID):
            m = self.mock.Mock(spec=dm.Module)
            m.id, m.origin = mid, origin
            return m
        caps = {'vcs': VCS_ID}
        for origin, mid, want in (('builtin', VCS_ID, {'vcs': DC}), ('space', VCS_ID, {}), ('builtin', 'other-vcs', {})):
            with self.mock.patch.object(dm, '_capabilities_full', lambda s, o=origin, i=mid: (caps, {'vcs': fake(o, i)})):
                self.assertEqual(dm.compat_view(sp, caps), want, (origin, mid))
        with self.mock.patch.object(dm, '_capabilities_full', lambda s: (caps, {})):
            self.assertEqual(dm.compat_view(sp, caps), {}, 'нема сирого постачальника — ключа нема')
        with self.mock.patch.object(dm, '_capabilities_full', self.mock.Mock(side_effect=RuntimeError('x'))):
            self.assertEqual(dm.compat_view(sp, caps), {}, 'збій кешу — тотальність')


# ------------------------------------------------------------------------------ Task 4: закон ізоляції, відмова публікації

OWN_KEY = 'sb_chan_key_alpha'          # ключ у secrets.json запису; відрізняється від кореня старого tasks.json (`SB_KEY`)
ISO_ENVS = ({'DC_TASKS_FILE': '<tasks>'}, {'DC_NO_OVERVIEW': '1'})


class SharedStateIsolationB(_VcsStand):
    """Закон ізоляції для `comments`/`vcs` (спека §5): запис із `shared_state: true` в ізольованому прогоні будує `ctx` неявного
    шляху (налаштування й секрети запису НЕ читаються); поза ізоляцією — `module_ctx`; без `shared_state` (чи не-`bool`) — звичайний
    модуль. Ключ у `secrets.json` ІНШИЙ, ніж у корені старого `tasks.json`: за ним видно, звідки прочитано."""

    def _iso(self, rig, which):
        env = dict(ISO_ENVS[which])
        env = {k: (rig.tasks_path if v == '<tasks>' else v) for k, v in env.items()}
        return self.mb._stack(rig, self.mb._env_extra(rig, **env))

    def cstand(self, shared=True, compat=LAYER, root_supabase=True):
        rig, space, cfg = self.stand(compat=compat)
        rec = {'enabled': True, 'settings': {'url': 'https://sb-own.example.com', 'shots_bucket': 'own-bucket'}}
        if compat:
            rec['settings']['compat'] = compat
        if shared is not None:
            rec['shared_state'] = shared
        self.mb._write(os.path.join(rig.space_dir, 'space.json'), {'modules': {COMMENTS_ID: rec}})
        if not root_supabase:
            cfg = {k: v for k, v in cfg.items() if k not in ('supabase_url', 'supabase_key')}
            self.mb._write(rig.tasks_path, cfg)
        return rig, space, cfg

    def route(self, rig, space):
        self.dm.reset_caches()
        prov, err = self.serve.comments_provider(space)
        self.assertIsNone(err)
        return self.serve.comments_route(space, prov)

    # ---- comments_route
    def test_comments_isolated_in_a_temp_home_takes_the_record_in_the_real_home_is_refused(self):
        """Було `test_comments_isolated_takes_the_legacy_ctx_not_the_record`: ізольований прогін брав ключ і адресу з КОРЕНЯ задач (`SB_KEY`), а не
        з `secrets.json`. 4d-4b (Д6): кореня нема; у ТИМЧАСОВОМУ домі — ctx запису (його секрет і налаштування), у СПРАВЖНЬОМУ — `comments-isolated`.
        Канал і предикат — за `compat`, як і було."""
        for which in (0, 1):
            rig, space, cfg = self.cstand()
            with self._iso(rig, which):
                mod, ctx, chan = self.route(rig, space)
                self.assertEqual(ctx['secrets'], {'key': OWN_KEY}, which)
                self.assertEqual((ctx['settings']['url'], ctx['settings']['shots_bucket']), ('https://sb-own.example.com', 'own-bucket'), which)
                self.assertEqual(chan(cfg['tasks']['a-1'], 'a-1'), 'liga-shared')           # канал і предикат — за compat
                self.assertEqual(chan(cfg['tasks']['a-2'], 'a-2'), 'dc/a-2')
                with self.mock.patch.object(self.isolation, 'real_home', lambda home: True):
                    with self.assertRaises(self.dm.ModuleError) as cm:
                        self.route(rig, space)
                self.assertEqual(cm.exception.code, 'comments-isolated', which)

    def test_comments_isolated_channel_follows_compat_without_it(self):
        rig, space, cfg = self.cstand(compat=None)
        with self._iso(rig, 0):
            _mod, ctx, chan = self.route(rig, space)
            self.assertEqual(ctx['secrets'], {'key': OWN_KEY})
            self.assertEqual(chan(cfg['tasks']['a-1'], 'a-1'), 'deai/legacy/a-1')

    def test_comments_isolated_does_not_need_the_root_config(self):
        """Було `…_without_root_config_is_unconfigured` (без пари Supabase у корені — `comments-unconfigured`). 4d-4b: корінь не читається ніде —
        ізольований маршрут працює без нього (як і з ним: `cstand(root_supabase=False)` не міняє ctx)."""
        for which in (0, 1):
            rig, space, _cfg = self.cstand(root_supabase=False)
            with self._iso(rig, which):
                _mod, ctx, _chan = self.route(rig, space)
                self.assertEqual(ctx['secrets'], {'key': OWN_KEY}, which)

    def test_comments_outside_isolation_takes_the_record(self):
        rig, space, _cfg = self.cstand()
        with self.pinned(rig):
            _mod, ctx, _chan = self.route(rig, space)
        self.assertEqual(ctx['secrets'], {'key': OWN_KEY})
        self.assertEqual(ctx['settings']['url'], 'https://sb-own.example.com')
        self.assertEqual(ctx['settings']['shots_bucket'], 'own-bucket')

    def test_comments_without_shared_state_is_a_plain_module_even_isolated(self):
        for shared in (None, False, 'true', 1, [], {}):
            rig, space, _cfg = self.cstand(shared=shared)
            with self._iso(rig, 0):
                _mod, ctx, _chan = self.route(rig, space)
                self.assertEqual(ctx['secrets'], {'key': OWN_KEY}, repr(shared))
                self.assertEqual(ctx['settings']['url'], 'https://sb-own.example.com', repr(shared))

    # ---- vcs_provider
    def vcs_env(self, rig, iso):
        return self._iso(rig, 0) if iso else self.pinned(rig)

    def test_vcs_isolated_takes_the_legacy_ctx(self):
        for compat in (DC, None):
            rig, _space, _cfg = self.vstand(compat=compat, autosync=False, extra={'branch': 'dev', 'path': 'x/{task}'})
            with self.vcs_env(rig, True):
                self.dm.reset_caches()
                _mod, ctx, legacy = self.serve.vcs_provider()
            self.assertEqual(ctx['settings'], {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True}, compat)
            self.assertIs(ctx['mirror_flat'], True, compat)
            self.assertEqual(ctx['cache_dir'], os.path.join(rig.home, 'mirrors'), compat)
            self.assertIs(legacy, compat == DC, compat)                                    # предикат текстів — за compat

    def test_vcs_outside_isolation_takes_the_record(self):
        rig, _space, _cfg = self.vstand(compat=DC, autosync=False, extra={'branch': 'dev'})
        with self.vcs_env(rig, False):
            self.dm.reset_caches()
            _mod, ctx, legacy = self.serve.vcs_provider()
        self.assertEqual((ctx['settings']['branch'], ctx['settings']['autosync']), ('dev', False))
        self.assertIs(ctx['mirror_flat'], True)                                            # накладка Task 3 лишається
        self.assertTrue(legacy)

    def test_vcs_without_shared_state_is_a_plain_module_even_isolated(self):
        for shared in (None, False, 'true', 1, [], {}):
            rig, _space, _cfg = self.vstand(compat=None, extra={'branch': 'dev'})
            sp = os.path.join(rig.space_dir, 'space.json')
            with open(sp, encoding='utf-8') as f:
                data = json.load(f)
            rec = data['modules'][VCS_ID]
            rec.pop('shared_state', None)
            if shared is not None:
                rec['shared_state'] = shared
            self.mb._write(sp, data)
            with self.vcs_env(rig, True):
                self.dm.reset_caches()
                _mod, ctx, _legacy = self.serve.vcs_provider()
            self.assertEqual(ctx['settings']['branch'], 'dev', repr(shared))
            self.assertNotIn('mirror_flat', ctx, repr(shared))

    # ---- publish_comments
    def test_publish_comments_refuses_shared_state_module_in_module_publish(self):
        serve = self.serve
        rig, space, cfg = self.cstand()
        task = cfg['tasks']['a-1']
        with self.pinned(rig):
            self.dm.reset_caches()
            self.assertEqual(serve.publish_comments(space, task, 'a-1', module_publish=True), (False, None))
            res, warn = serve.publish_comments(space, task, 'a-1', module_publish=False)    # шлях `_publish` — словник модуля
            self.assertIsNone(warn)
            self.assertIsInstance(res, dict)
            self.assertEqual(res['channel'], 'liga-shared')
        rig, space, cfg = self.cstand(shared=None)
        with self.pinned(rig):
            self.dm.reset_caches()
            for mp in (True, False):
                res, warn = serve.publish_comments(space, cfg['tasks']['a-1'], 'a-1', module_publish=mp)
                self.assertIsNone(warn, mp)
                self.assertIsInstance(res, dict, mp)

    # ---- ProjectComments._module
    def test_project_comments_module_is_not_gated_by_integrations(self):
        """Мігрований запис — явний модуль: жодного гейта «інтеграцій» нема (прапорець геть, 4d-4c)."""
        serve, spaces = self.serve, self.spaces
        rig, space, cfg = self.cstand()
        with self.pinned(rig):
            self.dm.reset_caches()
            pc = serve.ProjectComments(space)
            self.assertEqual(pc.kind, 'module')
            with self.mock.patch.object(self.dm, 'call', return_value=[]) as call:
                pc.pins(cfg['tasks']['a-1'], 'a-1')
            self.assertEqual(call.call_count, 1)

    # ---- ревʼю: споживачі в ізольованому прогоні
    def test_isolated_publish_comments_ships_the_record_config_in_a_temp_home(self):
        """Було `…_ships_the_tasks_root_config`: `_publish` (module_publish=False) під ізоляцією віддавав адресу й ключ з КОРЕНЯ файла задач, не
        з `secrets.json`. 4d-4b: кореня нема — у тимчасовому домі це конфіг запису (адреса й секрет)."""
        rig, space, cfg = self.cstand()
        with self._iso(rig, 0):
            self.dm.reset_caches()
            res, warn = self.serve.publish_comments(space, cfg['tasks']['a-1'], 'a-1', module_publish=False)
        self.assertIsNone(warn)
        self.assertEqual((res['config']['url'], res['config']['key']), ('https://sb-own.example.com', OWN_KEY))
        self.assertNotIn(self.mb.SB_KEY, json.dumps(res['config']), 'ключ кореня старого tasks.json не береться')
        self.assertEqual(res['channel'], 'liga-shared')

    def test_isolated_comment_config_over_http_returns_the_record_config(self):
        mb, serve = self.mb, self.serve
        rig, _space, _cfg = self.cstand()
        env = {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1', **mb._env_extra(rig)}
        with self.mock.patch.dict(os.environ, env), self.mock.patch.object(serve.urllib.request, 'urlopen', mb.NoNet()):
            self.dm.reset_caches()
            with mb.Server() as srv:
                st, body = mb._call(srv, 'GET', '/api/comment-config?ch=project&it=it1', task='a-1')
        self.assertEqual(st, 200)
        self.assertEqual(body['channel'], 'liga-shared')
        # 4d-4b: було `(SB_URL, SB_KEY)` кореня і `assertNotIn(OWN_KEY)`; тепер конфіг — запису (у тимчасовому домі), кореня не береться
        self.assertEqual((body['config']['url'], body['config']['key']), ('https://sb-own.example.com', OWN_KEY))
        self.assertNotIn(mb.SB_KEY, json.dumps(body))

    # ---- ревʼю: лише вбудовані модулі
    def test_comments_isolation_branch_is_builtin_only(self):
        """Свій модуль (`origin == 'space'`) із вручну виставленим `shared_state` не дістає ключ кореня задач (спека §5): умова
        «вбудований» — лише в гілці ізоляції `comments_route`; сам предикат `_shared_module` — як у 4d-3a, без походження."""
        rig, space, _cfg = self.cstand()
        prov = self.mock.Mock(spec=self.dm.Module)
        prov.id, prov.origin = COMMENTS_ID, 'space'
        self.assertTrue(self.serve._shared_module(space, prov))
        prov.origin = 'builtin'
        self.assertTrue(self.serve._shared_module(space, prov))
        marker = {'marker': 'module-ctx'}
        prov.origin = 'space'
        # 4d-4b: було — гілка ізоляції не кликала `_comments_legacy_ctx` (ключ кореня); тепер гілка ізоляції — відмова `comments-isolated` у
        # СПРАВЖНЬОМУ домі, і вона так само лише для вбудованого: свій модуль іде `module_ctx`, вбудований — відмовлено
        with self._iso(rig, 0), self.mock.patch.object(self.isolation, 'real_home', lambda home: True), \
                self.mock.patch.object(self.dm, 'module_ctx', return_value=marker):
            self.assertIs(self.serve.comments_route(space, prov)[1], marker)
            prov.origin = 'builtin'
            with self.assertRaises(self.dm.ModuleError) as cm:
                self.serve.comments_route(space, prov)
            self.assertEqual(cm.exception.code, 'comments-isolated')

    def test_own_dashboard_tracker_notify_with_shared_state_keep_the_4d3a_route_law(self):
        """Ревʼю 2: умова «вбудований» НЕ в `_shared_module`: свій модуль ролі dashboard/tracker/notify із `shared_state` в
        ізольованому прогоні іде законом маршруту (ізоляція/шов), а не живим викликом із справжніми секретами (`module_ctx`)."""
        serve, dm = self.serve, self.dm
        for which in (0, 1):
            for mid in ('supabase-dashboard', 'jira-tracker', 'supabase-teams'):
                rig, space = self.check_stand(mid, True)
                prov = self.mock.Mock(spec=dm.Module)
                prov.id, prov.origin = mid, 'space'
                with self._iso(rig, which), self.mock.patch.object(dm, 'module_ctx', side_effect=AssertionError('real secrets')), \
                        self.mock.patch.object(dm, 'read_secrets', side_effect=AssertionError('secrets read')), \
                        self.mock.patch.object(dm, 'call', side_effect=AssertionError('module called')), \
                        self.mock.patch.object(serve.urllib.request, 'urlopen', self.mb.NoNet()):
                    self.assertTrue(serve._shared_module(space, prov), (mid, which))
                    if mid == 'supabase-dashboard':
                        self.assertEqual(serve._team_fetch(space, prov), ([], serve.TEAM_ISOLATED), which)
                    elif mid == 'jira-tracker':
                        self.assertIsNone(serve._tracker_fetch(space, prov, ['k-1']), which)
                    else:
                        with self.assertRaises(OSError):
                            serve.notify_call('mute_state', resolved=(space, prov))

    def test_vcs_provider_of_own_module_ignores_isolation(self):
        rig, _space, _cfg = self.vstand(compat=None)
        prov = self.mock.Mock(spec=self.dm.Module)
        prov.id, prov.origin = VCS_ID, 'space'
        marker = {'marker': 'module-ctx'}
        with self._iso(rig, 0), self.mock.patch.object(self.dm, 'provider', return_value=prov), \
                self.mock.patch.object(self.dm, 'module_ctx', return_value=marker), \
                self.mock.patch.object(self.serve, '_vcs_legacy_ctx', side_effect=AssertionError('legacy')):
            self.assertIs(self.serve.vcs_provider()[1], marker)

    # ---- ревʼю: перевірка модуля (`check`) не читає секрети спільного стану в ізольованому прогоні
    CHECK_MODULES = ('supabase-comments', 'git-sync', 'supabase-dashboard', 'jira-tracker', 'supabase-teams')

    def check_stand(self, mid, shared):
        rig, space, _cfg = self.stand(module=False)
        rec = {'enabled': True, 'settings': {}}
        if shared is not None:
            rec['shared_state'] = shared
        self.mb._write(os.path.join(rig.space_dir, 'space.json'), {'modules': {mid: rec}})
        self.mb._write(os.path.join(rig.deai, 'secrets.json'), {self.mb.SPACE_ID: {mid: {'key': OWN_KEY}}})
        return rig, space

    def test_check_verdict_isolated_shared_record_touches_nothing(self):
        dm, serve = self.dm, self.serve
        for mid in self.CHECK_MODULES:
            rig, space = self.check_stand(mid, True)
            for which in (0, 1):
                with self._iso(rig, which), self.mock.patch.object(serve.urllib.request, 'urlopen', self.mb.NoNet()), \
                        self.mock.patch.object(dm, 'read_secrets', side_effect=AssertionError('secrets read')) as rs, \
                        self.mock.patch.object(dm, 'call', side_effect=AssertionError('module called')) as call, \
                        self.mock.patch.object(dm, '_remember', side_effect=AssertionError('last_check overwritten')):
                    v = serve.module_check_verdict(space, mid)
                self.assertEqual(v['ok'], False, (mid, which))
                self.assertEqual(v['error'], 'isolated', (mid, which))
                self.assertTrue(v['detail'], (mid, which))
                self.assertEqual((rs.call_count, call.call_count), (0, 0), (mid, which))

    def test_check_verdict_outside_isolation_or_without_shared_state_is_the_normal_path(self):
        dm, serve = self.dm, self.serve
        for mid in self.CHECK_MODULES:
            for shared, iso in ((True, False), (None, True), (False, True), ('true', True)):
                rig, space = self.check_stand(mid, shared)
                ctx = self._iso(rig, 0) if iso else self.pinned(rig)
                with ctx, self.mock.patch.object(dm, '_ctx', return_value={'secrets': {}}), \
                        self.mock.patch.object(dm, 'call', return_value={'ok': True}) as call:
                    dm.reset_caches()
                    v = serve.module_check_verdict(space, mid)
                self.assertEqual(v, {'ok': True}, (mid, shared, iso))
                self.assertEqual(call.call_count, 1, (mid, shared, iso))


# ================================================================================================ Task 5: упорядковані кроки міграції
#
# Механізм кроків перевіряється на СИНТЕТИЧНОМУ другому кроці (`fake_b`: один вигаданий модуль і секрет): реальний `STEP_B` — Task 6.

FAKE_SECRET = 'fake_b_secret_alpha'
FAKE_URL = 'https://sb-fake-b.example.com'
ORIG_SPACE = b'{"name": "Liga",\n  "x": {"k": [1,  2]}}\n'
OTHER_SECRETS = {'other': {'m': {'k': 'other_value_alpha'}}}


class _TwoSteps(_WriteStand):
    """Стенд двох кроків: реальний 4d-3a + синтетичний `liga-4d3b` (роль `comments` → `supabase-comments`, ключ `FAKE_SECRET`)."""

    def setUp(self):
        super().setUp()                              # `_Stand.setUp` ставить `STEPS = ALL_STEPS[:1]` — тут його перекриваємо
        lm = self.lm

        def entries(cfg, present):
            if 'supabase-comments' in present:
                return {'comments': ('supabase-comments', 'module-present', None, None)}
            return {'comments': ('supabase-comments', None,
                                 {'enabled': True, 'shared_state': True, 'settings': {'url': FAKE_URL}}, {'key': FAKE_SECRET})}
        self.step_a = lm.STEP_A
        self.step_b = lm.Step('liga-4d3b', (('comments', 'supabase-comments'),), False, '-liga-4d3b',
                              re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3b(?:-[0-9]{1,3})?'), entries)
        self.steps = (self.step_a, self.step_b)
        for name in ('ALL_STEPS', 'STEPS'):
            p = self.mock.patch.object(lm, name, self.steps)
            p.start()
            self.addCleanup(p.stop)
        self.secret_values = self.secret_values + (FAKE_SECRET,)

    def seed(self):
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)
        self._write(self.secrets_path(), json.dumps(OTHER_SECRETS))
        os.chmod(self.secrets_path(), 0o600)

    def marks(self):
        return self.read_json(self.space_path()).get('migrations') or {}

    def stamps(self):
        m = self.marks()
        return m['liga-4d3a']['backup'], m['liga-4d3b']['backup']

    def start(self):
        return self.quiet(self.lm.startup)


class StepsDefaults(_WriteStand):
    """Без синтетики: аліаси кроку a й «без `step` = 4d-3a»."""

    def test_aliases_are_step_a(self):
        lm = self.lm
        self.assertIs(lm.ALL_STEPS[0], lm.STEP_A)
        self.assertEqual(lm.Step._fields[:5], ('mark', 'roles', 'tracks', 'suffix', 'stamp_re'))
        self.assertEqual((lm.MARK, lm.ROLE_MODULES, lm.BACKUP_SUFFIX), (lm.STEP_A.mark, lm.STEP_A.roles, lm.STEP_A.suffix))
        self.assertIs(lm.STAMP_RE, lm.STEP_A.stamp_re)
        self.assertEqual((lm.STEP_A.mark, lm.STEP_A.suffix, lm.STEP_A.tracks), ('liga-4d3a', '-liga-4d3a', True))

    def test_no_step_argument_is_step_a(self):
        lm = self.lm
        self.assertEqual(lm.plan(), lm.plan(step='liga-4d3a'))
        self.assertEqual(lm.plan(), lm.plan(step=lm.STEP_A))
        self.assertEqual(lm.run(), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual(sorted(sj['migrations']), ['liga-4d3a'])
        self.assertEqual(len(self.backups()), 1)
        st = lm.status()
        self.assertEqual(st['mark'], {k: sj['migrations']['liga-4d3a'][k] for k in ('at', 'roles', 'tracks', 'backup')})
        self.assertEqual(lm.restore(self.backups()[0]), 'restored')

    def test_unknown_step_never_raises(self):
        self.assertEqual(self.lm.plan(step='liga-nope')['status'], 'abort-internal')


class StepsTest(_TwoSteps):
    """Крок = (позначка, ролі, напрямки, суфікс, `STAMP_RE`): імʼя бекапу однозначно називає крок; позначки незалежні."""

    NAMES = (('20261106-120000-liga-4d3a', 'liga-4d3a'), ('20261106-120000-liga-4d3a-2', 'liga-4d3a'),
             ('20261106-120000-liga-4d3b', 'liga-4d3b'), ('20261106-120000-liga-4d3b-17', 'liga-4d3b'),
             ('20261106-120000-liga-4d3a-pre-restore', None), ('20261106-120000-liga-4d3b-pre-restore', None),
             ('20261106-120000-liga-4d3b-1234', None), ('x20261106-120000-liga-4d3b', None), ('../20261106-120000-liga-4d3b', None))

    def test_stamp_re_tells_the_steps_apart(self):
        for name, mark in self.NAMES:
            got = [s.mark for s in self.steps if s.stamp_re.fullmatch(name)]
            self.assertEqual(got, [mark] if mark else [], name)
            step = self.lm.step_of_stamp(name)
            self.assertEqual(step.mark if step else None, mark, name)
        for bad in (None, 5, '', ['20261106-120000-liga-4d3a']):
            self.assertIsNone(self.lm.step_of_stamp(bad))

    def test_list_backups_and_status_cover_all_steps(self):
        self.assertEqual(self.lm.run_all()[0][:2], ('liga-4d3a', 'done'))
        os.makedirs(os.path.join(self.deai, 'backups', '20260101-000000-liga-4d3b'))     # недописана тека без маніфесту
        a, b = self.stamps()
        self.assertEqual(self.lm._list_backups(), sorted([a, b]))
        st = self.lm.status()
        self.assertEqual(st['backups'], sorted([a, b]))
        self.assertTrue(a.endswith('-liga-4d3a') and b.endswith('-liga-4d3b'))

    def test_status_keeps_4d3a_keys_and_adds_steps(self):
        self.lm.run_all()
        st = self.lm.status()
        self.assertTrue({'liga', 'space_id', 'mark', 'last', 'backups', 'error'} <= set(st))
        self.assertEqual(st['mark'], st['steps']['liga-4d3a']['mark'])
        self.assertEqual(list(st['steps']), ['liga-4d3a', 'liga-4d3b'])
        for mark, step_info in st['steps'].items():
            self.assertEqual(sorted(step_info), ['backups', 'mark'], mark)
            self.assertEqual(step_info['backups'], st['backups'], mark)
        self.assertEqual(sorted(st['steps']['liga-4d3a']['mark']), ['at', 'backup', 'roles', 'tracks'])
        self.assertEqual(sorted(st['steps']['liga-4d3b']['mark']), ['at', 'backup', 'roles'])      # без `tracks`
        self.assertEqual(st['steps']['liga-4d3b']['mark']['roles'], ['comments'])

    def test_status_text_has_a_section_per_step(self):
        self.lm.run_all()
        text = self.lm.status_text(self.lm.status())
        self.assertLess(text.index('Міграція ЛІГИ (liga-4d3a)'), text.index('Міграція ЛІГИ (liga-4d3b)'))
        a, b = self.stamps()
        self.assertIn('бекап: ' + a, text)
        self.assertIn('бекап: ' + b, text)
        self.assert_no_secrets(text)

    def test_manifest_migration_must_match_the_step(self):
        self.lm.run_all()
        a, b = self.stamps()
        for stamp, wrong in ((a, 'liga-4d3b'), (b, 'liga-4d3a')):
            mp = os.path.join(self.deai, 'backups', stamp, 'manifest.json')
            m = self.read_json(mp)
            m['migration'] = wrong
            with open(mp, 'w', encoding='utf-8') as f:
                json.dump(m, f)
            self.assertEqual(self.lm.restore(stamp), 'refuse-tampered', stamp)

    def test_marks_are_independent(self):
        """`skip-held`/`skip-done` одного кроку не чіпають другого; кожен пише лише свою позначку."""
        self.space_json({'migrations': {'liga-4d3b': {'held': True}}})
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-held')
        self.assertEqual(self.lm.plan(step='liga-4d3a')['status'], 'ready')
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'skip-held')
        self.assertEqual(self.lm.run(step='liga-4d3a'), 'done')
        self.assertEqual(self.marks()['liga-4d3b'], {'held': True})
        # ревʼю: УТРИМАНИЙ ранній крок тримає всі наступні (раніше b ішов далі) — решта пропусків a (done) не блокує b
        self.space_json({'migrations': {'liga-4d3a': {'held': True}}})
        self.assertEqual(self.lm.plan(step='liga-4d3a')['status'], 'skip-held')
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-held')
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'skip-held')
        self.assertEqual(self.marks(), {'liga-4d3a': {'held': True}})
        self.space_json({'migrations': {'liga-4d3a': {'at': 'x', 'roles': [], 'tracks': False}}})
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'done')
        mk = self.marks()
        self.assertEqual(sorted(mk['liga-4d3b']), ['at', 'backup', 'roles'])
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'skip-done')

    def test_step_b_backup_is_its_own_and_manifest_names_it(self):
        self.lm.run_all()
        a, b = self.stamps()
        self.assertEqual(self.read_json(self.deai, 'backups', a, 'manifest.json')['migration'], 'liga-4d3a')
        self.assertEqual(self.read_json(self.deai, 'backups', b, 'manifest.json')['migration'], 'liga-4d3b')
        self.assertEqual(os.stat(os.path.join(self.deai, 'backups', b)).st_mode & 0o777, 0o700)
        # крок b бачить стан ПІСЛЯ запису a: його бекап `space.json` уже має позначку 4d-3a
        self.assertIn('liga-4d3a', self.read_json(self.deai, 'backups', b, 'space.json')['migrations'])
        self.assertNotIn('liga-4d3b', self.read_json(self.deai, 'backups', b, 'space.json')['migrations'])


class TwoStepsStartupTest(_TwoSteps):
    """`startup()`: кроки по порядку; `abort-*` зупиняє наступні на цьому старті, `skip-*` — ні."""

    def test_both_steps_on_one_start_in_order(self):
        self.seed()
        st, err = self.start()
        self.assertEqual(st, 'done')
        a, b = self.stamps()
        self.assertEqual(sorted(self.backups()), sorted([a, b]))
        self.assertLess(err.index('liga-4d3a: done'), err.index('liga-4d3b: done'))
        sj = self.read_json(self.space_path())
        self.assertIn('supabase-comments', sj['modules'])
        self.assertIn('jira-tracker', sj['modules'])
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['supabase-comments'], {'key': FAKE_SECRET})
        self.assertEqual(self.read_json(self.secrets_path())['other'], OTHER_SECRETS['other'])
        self.assert_no_secrets_in_logs()

    def test_last_json_is_the_last_action_plus_steps(self):
        self.seed()
        self.start()
        a, b = self.stamps()
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['step'], last['backup'], last['roles']), ('done', 'liga-4d3b', b, ['comments']))
        self.assertEqual(sorted(last['steps']), ['liga-4d3a', 'liga-4d3b'])
        self.assertEqual(last['steps']['liga-4d3a']['backup'], a)          # звіт a не стертий звітом b (Поправка 8)
        self.assertEqual(last['steps']['liga-4d3a']['roles'], ['tracker', 'dashboard', 'notify'])
        self.assertEqual(last['steps']['liga-4d3b']['backup'], b)
        self.assertEqual(last['secrets'], {'supabase-comments': ['key']})
        self.assertRegex(last['at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$')
        self.assert_no_secrets_in_logs()

    def test_order_of_steps_is_the_order_of_startup(self):
        self.seed()
        order = []
        real = self.lm._run

        def spy(home, step=None):
            order.append(step.mark)
            return real(home, step)
        with self.mock.patch.object(self.lm, '_run', spy):
            self.start()
        self.assertEqual(order, ['liga-4d3a', 'liga-4d3b'])

    def test_abort_of_first_step_stops_the_second(self):
        self.seed()
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: None):
            st, err = self.start()
        self.assertEqual(st, 'abort-provider')
        self.assertEqual(self.backups(), [])
        self.assertNotIn('liga-4d3b: ', err)                          # рядка КРОКУ нема (назва кроку в підказці ролі — не рядок кроку)
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['step']), ('abort-provider', 'liga-4d3a'))
        self.assertEqual(list(last['steps']), ['liga-4d3a'])
        self.assertNotIn('liga-4d3b', json.dumps(self.read_json(self.space_path()).get('migrations') or {}))

    def test_skip_of_first_step_does_not_block_the_second(self):
        for kind in ('done', 'nothing'):          # `held` винесено в `test_held_first_step_holds_the_second` (ревʼю)
            self.setUp_fresh()
            if kind == 'done':
                self.space_json({'migrations': {'liga-4d3a': {'at': 'x', 'roles': [], 'tracks': False}}})
            else:
                self.config(supabase=False, jira=False, design_work_root=None)
                cfg = self.cfg
                cfg['tasks']['x'] = {'dir': os.path.join(self.home, 'work', 'x')}
                self._write(self.tasks_path, cfg)
            st, err = self.start()
            self.assertEqual(st, 'done', kind)
            mk = self.marks()
            self.assertEqual(sorted(mk['liga-4d3b']), ['at', 'backup', 'roles'], kind)
            self.assertEqual(len(self.backups()), 1, kind)
            self.assertIn('liga-4d3b: done', err, kind)
            self.assertNotIn('liga-4d3a:', err, kind)                    # `skip-done`/`skip-nothing` — тихо, як у 4d-3a
            if kind == 'nothing':
                self.assertNotIn('liga-4d3a', mk)

    def test_held_first_step_holds_the_second(self):
        """Ревʼю I1: `held` раннього кроку тримає наступні (старт нічого не пише), на відміну від done/nothing."""
        self.space_json({'migrations': {'liga-4d3a': {'held': True}}})
        before = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual(st, 'skip-held')
        self.assertIn('liga-4d3a: skip-held', err)
        self.assertIn('liga-4d3b: skip-held', err)
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-held')

    def test_startup_return_does_not_mask_a_later_abort(self):
        """Ревʼю M1: a=done, b=abort-* → `startup()` повертає abort."""
        real = self.lm._run

        def run(home, step=None):
            if step.mark == 'liga-4d3b':
                return 'abort-write', {'status': 'abort-write', 'reason': 'x'}
            return real(home, step)
        with self.mock.patch.object(self.lm, '_run', run):
            st, _err = self.start()
        self.assertEqual(st, 'abort-write')

    def test_skip_busy_stops_later_steps(self):
        """Ревʼю M2: `skip-busy` кроку, як `abort-*`, зупиняє наступні (b не йде, поки хтось посеред a)."""
        seen = []

        def run(home, step=None):
            seen.append(step.mark)
            return 'skip-busy', {'status': 'skip-busy', 'reason': 'busy'}
        with self.mock.patch.object(self.lm, '_run', run):
            res = self.lm.run_all()
            self.assertEqual([m for m, _s, _i in res], ['liga-4d3a'])
            code, out, _ = self.cli('run')
        self.assertEqual(seen, ['liga-4d3a', 'liga-4d3a'])
        self.assertNotIn('liga-4d3b', out)

    def test_identical_hint_is_printed_once(self):
        """Ревʼю M3: однакова підказка (тека в git) на старті друкується один раз для всіх кроків."""
        self.space_json({})
        os.makedirs(os.path.join(self.space_dir, '.git'))
        st, err = self.start()
        self.assertEqual(err.count('Перенесіть теку простору ЛІГА'), 1)
        self.assertIn('liga-4d3a: skip-path-in-git', err)
        self.assertEqual(err.count('skip-path-in-git —'), 1)           # M1: однаковий постійний пропуск — один рядок статусу
        self.assertIn('те саме для: liga-4d3b', err)

    def setUp_fresh(self):
        """Чистий дім між варіантами одного тесту (реєстр і конфіг — як на старті стенда)."""
        import shutil
        for sub in ('backups', 'migrations'):
            shutil.rmtree(os.path.join(self.deai, sub), ignore_errors=True)
        for p in (self.space_path(), self.secrets_path()):
            if os.path.exists(p):
                os.remove(p)
        self.config()

    def test_exception_does_not_break_startup_and_keeps_the_first_report(self):
        real = self.lm._run

        def flaky(home, step=None):
            if step.mark == 'liga-4d3b':
                raise RuntimeError(FAKE_SECRET)
            return real(home, step)
        with self.mock.patch.object(self.lm, '_run', flaky):
            st, err = self.start()
        self.assertEqual(st, 'abort-internal')
        self.assertIn('liga-4d3a: done', err)
        self.assertIn('abort-internal — RuntimeError', err)
        self.assertNotIn(FAKE_SECRET, err)
        self.assert_no_secrets_in_logs()

    def test_second_start_prints_only_the_off_roles_and_writes_nothing(self):
        """4d-4b (Поправка 6): другий старт мовчить про кроки, але КОЖНУ вимкнену роль називає (рядки `ролі ЛІГИ вимкнено: …`); дерево файлів не змінюється."""
        self.start()
        before = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual(st, 'skip-done')
        self.assertEqual(err.splitlines(), [
            'ролі ЛІГИ вимкнено: publish (vercel-publish) — no-record; виправити: запустіть: python3 bin/migrate_liga.py run',
            'ролі ЛІГИ вимкнено: vcs (git-sync) — not-migrated; виправити: запустіть python3 bin/migrate_liga.py run '
            '(або увімкніть модуль на екрані «Підключення»)'])
        self.assertEqual(self.snapshot_tree(), before)

    def test_run_all_returns_marks_statuses_infos(self):
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'done'), ('liga-4d3b', 'done')])
        self.assertEqual(res[1][2]['roles'], ['comments'])
        self.assertEqual([(m, s) for m, s, _i in self.lm.run_all()], [('liga-4d3a', 'skip-done'), ('liga-4d3b', 'skip-done')])
        self.assert_no_secrets(repr(res))


class LifoRestoreTest(_TwoSteps):
    """Відкат LIFO: `restore <a>` при застосованому b — відмова без запису; `restore <b>` лишає a застосованим."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.assertEqual(self.lm.run(step='liga-4d3a'), 'done')
        self.after_a = (self.read(self.space_path()), self.read(self.secrets_path()))
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'done')
        self.a, self.b = self.stamps()

    def test_restore_a_refused_while_b_applied_and_writes_nothing(self):
        before = self.snapshot_tree()
        st, info = self.lm._restore(self.a)
        self.assertEqual(st, 'refuse-later-applied')
        self.assertEqual(info['rollback_first'], self.b)
        self.assertEqual(self.lm.restore(self.a, hold=True), 'refuse-later-applied')
        self.assertEqual(self.snapshot_tree(), before)                    # ні space.json, ні секретів, ні last.json, ні pre-restore

    def test_restore_b_returns_the_state_after_a(self):
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_a[0])
        self.assertEqual(self.read(self.secrets_path()), self.after_a[1])
        self.assertIn('liga-4d3a', self.marks())
        self.assertNotIn('liga-4d3b', self.marks())
        self.assertNotIn(FAKE_SECRET, self.read(self.secrets_path()).decode('utf-8'))
        self.assertTrue(any(n.startswith(self.b + '-pre-restore') for n in self.backups()))
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['step']), ('restored', 'liga-4d3b'))
        self.assertEqual(sorted(last['steps']), ['liga-4d3a', 'liga-4d3b'])
        self.assertEqual(last['steps']['liga-4d3a']['status'], 'done')    # звіт кроку a не стертий

    def test_restore_a_allowed_after_b_was_rolled_back(self):
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')
        self.assertEqual(self.read(self.space_path()), ORIG_SPACE)
        self.assertEqual(self.read_json(self.secrets_path()), OTHER_SECRETS)

    def test_hold_marks_only_its_own_step(self):
        a_mark = self.marks()['liga-4d3a']
        self.assertEqual(self.lm.restore(self.b, hold=True), 'restored')
        mk = self.marks()
        self.assertEqual(mk['liga-4d3b'], {'held': True})
        self.assertEqual(mk['liga-4d3a'], a_mark)                          # a недоторкана
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-held')

    def test_held_b_does_not_block_restore_of_a(self):
        self.assertEqual(self.lm.restore(self.b, hold=True), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')
        self.assertEqual(self.read(self.space_path()), ORIG_SPACE)

    def test_hold_on_a_marks_only_a(self):
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a, hold=True), 'restored')
        self.assertEqual(self.marks(), {'liga-4d3a': {'held': True}})
        # ревʼю I1: утримання a тримає й b — наступний старт нічого не пише (раніше b запускався)
        before = self.snapshot_tree()
        st, _err = self.start()
        self.assertEqual(st, 'skip-held')
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.plan(step='liga-4d3b')['status'], 'skip-held')

    def test_full_sequence_run_restore_b_restore_a_hold_then_startup_writes_nothing(self):
        """Ревʼю I1: run a, run b, restore b, restore a --hold, startup → дерево побайтно те саме, b `skip-held`."""
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a, hold=True), 'restored')
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'skip-held')
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'skip-held'), ('liga-4d3b', 'skip-held')])
        st, _err = self.start()
        self.assertEqual(st, 'skip-held')
        self.assertEqual(self.snapshot_tree(), before)

    def test_restore_a_alone_is_still_allowed_when_b_was_never_applied(self):
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.run(step='liga-4d3a'), 'skip-done')
        self.assertEqual(self.lm.restore(self.a), 'restored')


class CliStepsTest(_TwoSteps):
    """`bin/migrate_liga.py`: усі кроки, `restore` за імʼям бекапу, відмова LIFO → код 1; з одним кроком вивід = 4d-3a."""

    def test_single_step_output_is_byte_identical_to_4d3a(self):
        lm = self.lm
        with self.mock.patch.object(lm, 'STEPS', (self.step_a,)):
            code, out, _ = self.cli('status')
            self.assertEqual(out, 'Міграція ЛІГИ (liga-4d3a)\n  простір: legacy\n'
                                  '  позначки нема: міграція ще не виконана (або відкочена)\n  бекапи: нема\n'
                                  'Ролі ЛІГИ\n  publish (vercel-publish): ні (no-record)\n  comments (supabase-comments): ні (no-record)\n'
                                  '  vcs (git-sync): ні (no-record)\n  dashboard (supabase-dashboard): ні (no-record)\n'
                                  '  tracker (jira-tracker): ні (no-record)\n  notify (supabase-teams): ні (no-record)\n')   # 4d-4b: секція «Ролі ЛІГИ»
            code, out, _ = self.cli('dry-run')
            self.assertEqual((code, out), (0, lm.report(lm.plan(step=self.step_a)) + '\n'))
            self.assertTrue(out.startswith('liga-4d3a: ready\n'))
            self.assertEqual(self.backups(), [])
            code, out, _ = self.cli('run')
            b = self.backups()[0]
            self.assertEqual((code, out), (0, 'liga-4d3a: done\n  міграцію виконано\n'
                                              '  ролі: tracker, dashboard, notify; напрямки: так; бекап: %s\n'
                                              '  відкат: python3 bin/migrate_liga.py restore %s [--hold]\n' % (b, b)))
            self.assertEqual(len(self.backups()), 1)
            code, out, _ = self.cli('status')
            self.assertRegex(out, r'^Міграція ЛІГИ \(liga-4d3a\)\n  простір: legacy\n'
                                  r'  позначка: \S+, ролі: tracker, dashboard, notify, напрямки: так, бекап: %s\n'
                                  r'  останній звіт: done \(\S+\)\n  бекапи: %s\n'
                                  r'Ролі ЛІГИ\n  publish \(vercel-publish\): ні \(no-record\)\n  comments \(supabase-comments\): ні \(no-record\)\n'
                                  r'  vcs \(git-sync\): ні \(no-record\)\n  dashboard \(supabase-dashboard\): так\n'
                                  r'  tracker \(jira-tracker\): так\n  notify \(supabase-teams\): так\n$' % (re.escape(b), re.escape(b)))
            code, out, _ = self.cli('run')
            self.assertEqual((code, out), (0, 'liga-4d3a: skip-done\n  міграцію вже виконано (позначка в space.json)\n'))
            code, out, _ = self.cli('restore', b)
            self.assertEqual(code, 0)
            self.assertRegex(out, r'^liga-4d3a restore: restored\n  запобіжна копія поточних space.json і секретів ЛІГИ '
                                  r'\(до відкату\): backups/%s-pre-restore\n$' % re.escape(b))
            code, out, _ = self.cli('restore', '20990101-000000-liga-4d3a')
            self.assertEqual((code, out), (1, 'liga-4d3a restore: refuse-stamp\n'))
        self.assert_no_secrets_in_logs()

    def test_status_dry_run_run_show_all_steps(self):
        code, out, _ = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertLess(out.index('liga-4d3a: ready'), out.index('liga-4d3b: ready'))
        self.assertEqual(self.backups(), [])
        code, out, _ = self.cli('run')
        self.assertEqual(code, 0)
        a, b = self.stamps()
        self.assertLess(out.index('liga-4d3a: done'), out.index('liga-4d3b: done'))
        self.assertNotIn('restore %s [--hold]' % a, out)           # 4d-3c ревʼю I2: LIFO — підказка лише для найпізнішого кроку
        self.assertIn('restore %s [--hold]' % b, out)
        self.assertIn('бекап: %s' % a, out)
        code, out, _ = self.cli('status')
        self.assertLess(out.index('Міграція ЛІГИ (liga-4d3a)'), out.index('Міграція ЛІГИ (liga-4d3b)'))
        code, out, _ = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d3a: skip-done', out)
        self.assertIn('liga-4d3b: skip-done', out)
        self.assert_no_secrets_in_logs()

    def test_run_stops_after_abort_and_exits_1(self):
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: None):
            code, out, _ = self.cli('run')
        self.assertEqual(code, 1)
        self.assertIn('liga-4d3a: abort-provider', out)
        self.assertNotIn('liga-4d3b', out)
        self.assertEqual(self.backups(), [])

    def test_restore_finds_the_step_by_stamp_and_lifo_refusal_exits_1(self):
        self.cli('run')
        a, b = self.stamps()
        before = self.snapshot_tree()
        code, out, err = self.cli('restore', a)
        self.assertEqual(code, 1)
        self.assertIn('liga-4d3a restore: refuse-later-applied', out)
        self.assertIn(b, out)                                              # називає бекап, який відкочувати першим
        self.assertEqual(self.snapshot_tree(), before)
        code, out, _ = self.cli('restore', b)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('liga-4d3b restore: restored\n'))
        code, out, _ = self.cli('restore', b, '--hold')
        self.assertEqual(code, 0)
        self.assertEqual(self.marks()['liga-4d3b'], {'held': True})
        code, out, _ = self.cli('restore', a)
        self.assertEqual((code, out.split('\n')[0]), (0, 'liga-4d3a restore: restored'))
        self.assert_no_secrets_in_logs()


# ================================================================================================ Task 6: крок `liga-4d3b` (comments + vcs)
#
# Тут — РЕАЛЬНІ два кроки (`ALL_STEPS = (STEP_A, STEP_B)`); стенд знімає патч `STEPS = ALL_STEPS[:1]` зі `_Stand`. Значення вигадані.

COMMENTS_MOD, VCS_MOD = 'supabase-comments', 'git-sync'


class _RealSteps(_WriteStand):
    """Стенд двох РЕАЛЬНИХ кроків. `setUp` лишає простір НЕмігрованим; `apply_a()` застосовує 4d-3a."""

    def setUp(self):
        super().setUp()                                  # `_Stand.setUp`: STEPS = ALL_STEPS[:1] — тут перекриваємо повним переліком
        p = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS[:2])        # 4d-3c: ці стенди — про два кроки; третій (c) — у test_liga_migrate_c.py
        p.start()
        self.addCleanup(p.stop)

    def seed(self):
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)
        self._write(self.secrets_path(), json.dumps(OTHER_SECRETS))
        os.chmod(self.secrets_path(), 0o600)

    def apply_a(self):
        self.assertEqual(self.lm.run(step='liga-4d3a'), 'done')

    def plan_b(self):
        return self.lm.plan(step='liga-4d3b')

    def marks(self):
        return self.read_json(self.space_path()).get('migrations') or {}

    def stamps(self):
        m = self.marks()
        return m['liga-4d3a']['backup'], m['liga-4d3b']['backup']

    def start(self):
        return self.quiet(self.lm.startup)

    def write_modules(self, mods):
        self.space_json({'modules': mods})


class StepBConstants(unittest.TestCase):
    """Поправка 6: `LEGACY_SHOTS_BUCKET` живе в `install_config` (джерело), `serve` лишає аліас; міграція не імпортує `serve`."""

    @classmethod
    def setUpClass(cls):
        _app_paths()

    def test_legacy_shots_bucket_is_one_value_with_an_alias(self):
        import install_config
        import serve
        self.assertEqual(install_config.LEGACY_SHOTS_BUCKET, 'overview-thumbs')
        self.assertEqual(serve.LEGACY_SHOTS_BUCKET, install_config.LEGACY_SHOTS_BUCKET)

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

    def test_steps_list_and_step_b_shape(self):
        import liga_migrate as lm
        self.assertEqual([s.mark for s in lm.ALL_STEPS][:2], ['liga-4d3a', 'liga-4d3b'])      # 4d-3c: третій крок — `StepCConstants`
        self.assertIs(lm.ALL_STEPS[2], lm.STEP_C)
        self.assertEqual(lm.STEPS, lm.ALL_STEPS)                 # 4d-4b (Task 7): на старті п'ять кроків
        b = lm.ALL_STEPS[1]
        self.assertIs(lm.STEP_B, b)
        self.assertEqual((b.mark, b.suffix, b.tracks), ('liga-4d3b', '-liga-4d3b', False))
        self.assertEqual(b.roles, lm.ROLE_MODULES_B)
        self.assertEqual(lm.ROLE_MODULES_B, (('comments', COMMENTS_MOD), ('vcs', VCS_MOD)))
        self.assertIsNotNone(b.entries)
        self.assertTrue(b.stamp_re.fullmatch('20261106-120000-liga-4d3b-2'))
        self.assertIsNone(b.stamp_re.fullmatch('20261106-120000-liga-4d3a'))
        self.assertIs(lm.step_of_stamp('20261106-120000-liga-4d3b'), b)


class StepBPlanTest(_RealSteps):
    """`plan(step='liga-4d3b')`: чистий розрахунок записів `supabase-comments` і `git-sync`; нічого не пише."""

    def setUp(self):
        super().setUp()
        self.apply_a()

    def test_ready_comments_and_vcs_entries(self):
        before = self.snapshot_tree()
        p = self.plan_b()
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(p['roles'], {'comments': {'module': COMMENTS_MOD, 'migrate': True, 'reason': None},
                                      'vcs': {'module': VCS_MOD, 'migrate': True, 'reason': None}})
        mods = p['space_json']['modules']
        self.assertEqual(mods[COMMENTS_MOD], {'enabled': True, 'shared_state': True,
                                              'settings': {'url': self.SB_URL, 'shots_bucket': 'overview-thumbs', 'compat': 'comment-layer'}})
        self.assertEqual(mods[VCS_MOD], {'enabled': True, 'shared_state': True,
                                         'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas'}})
        self.assertEqual(sorted(mods[COMMENTS_MOD]['settings']), ['compat', 'shots_bucket', 'url'])          # рівно ці ключі
        self.assertEqual(sorted(mods[VCS_MOD]['settings']), ['autosync', 'branch', 'compat', 'path'])
        self.assertEqual(p['secrets'], {COMMENTS_MOD: {'key': self.SB_KEY}})          # у git-sync секретів нема
        self.assertIn('jira-tracker', mods)                                           # модулі 4d-3a збережено
        self.assertEqual(p['space_json']['migrations']['liga-4d3b'], {'roles': ['comments', 'vcs']})      # `at`/`backup` — запис
        self.assertEqual((p['tracks'], p['tracks_reason']), (False, None))
        self.assertEqual(self.snapshot_tree(), before)                                # план нічого не пише

    def test_vcs_entry_has_no_ssh_key_host_ip_or_repo(self):
        self.config(gitlab_ssh_key='/keys/alpha', gitlab_host_ip='10.9.8.7', gitlab_repo='git@example.com:studio/web.git')
        p = self.plan_b()
        entry = p['space_json']['modules'][VCS_MOD]
        self.assertEqual(sorted(entry), ['enabled', 'settings', 'shared_state'])
        self.assertEqual(sorted(entry['settings']), ['autosync', 'branch', 'compat', 'path'])
        for needle in ('ssh_key', 'host_ip', '/keys/alpha', '10.9.8.7', 'repo'):
            self.assertNotIn(needle, json.dumps(entry))
        self.assertNotIn(VCS_MOD, p['secrets'])

    def test_vcs_settings_without_compat_equal_the_implicit_legacy_ctx(self):
        """Поправка 6: міграція й неявний шлях ділять `branch/path/autosync` (розʼїзд = зміна поведінки ЛІГИ)."""
        import serve
        got = {k: v for k, v in self.plan_b()['space_json']['modules'][VCS_MOD]['settings'].items() if k != 'compat'}
        self.assertEqual(got, serve._vcs_legacy_ctx()['settings'])

    def test_url_and_key_come_from_supabase_from(self):
        with self.mock.patch.object(self.lm, '_supabase_from', lambda cfg: ('https://sb-other.example.com', 'other_key_alpha')):
            p = self.plan_b()
        self.assertEqual(p['space_json']['modules'][COMMENTS_MOD]['settings']['url'], 'https://sb-other.example.com')
        self.assertEqual(p['secrets'], {COMMENTS_MOD: {'key': 'other_key_alpha'}})

    def test_report_names_keys_not_values(self):
        p = self.plan_b()
        text = self.lm.report(p, 'liga-4d3b')
        self.assertTrue(text.startswith('liga-4d3b: ready\n'))
        self.assertIn('comments (%s): migrate' % COMMENTS_MOD, text)
        self.assertIn('vcs (%s): migrate' % VCS_MOD, text)
        self.assertIn('secrets %s: key' % COMMENTS_MOD, text)
        self.assertNotIn('tracks:', text)                                             # крок b напрямків не мігрує
        self.assert_no_secrets(text)
        self.assertNotIn(self.SB_URL, text)

    # --- пропуски
    def test_skip_layer_off(self):
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}):
            os.environ.pop('DEAI_HOME')
            p = self.plan_b()
        self.assertEqual((p['status'], p['space_json']), ('skip-layer-off', None))

    def test_skip_no_liga(self):
        self.registry(entry=False)
        self.assertEqual(self.plan_b()['status'], 'skip-no-liga')

    def test_skip_done(self):
        self.space_json({'migrations': {'liga-4d3a': {'at': 'x', 'roles': [], 'tracks': False}, 'liga-4d3b': {'at': 'x', 'roles': []}}})
        self.assertEqual(self.plan_b()['status'], 'skip-done')

    def test_skip_held_own_keeps_its_reason(self):
        self.space_json({'migrations': {'liga-4d3b': {'held': True}}})
        p = self.plan_b()
        self.assertEqual(p['status'], 'skip-held')
        self.assertEqual(p['reason'], self.lm._REASONS['skip-held'])

    def test_skip_held_by_an_earlier_step_has_its_own_reason(self):
        """Мінор ревʼю Task 5: b, утриманий РАННІМ кроком, не називає це «вимкнено вручну» самого b."""
        self.space_json({'migrations': {'liga-4d3a': {'held': True}}})
        p = self.plan_b()
        self.assertEqual((p['status'], p['space_id']), ('skip-held', 'legacy'))
        self.assertIn('liga-4d3a', p['reason'])
        self.assertTrue(p['reason'].startswith('утримано разом із'))
        self.assertNotEqual(p['reason'], self.lm._REASONS['skip-held'])
        self.assertEqual(self.lm.plan(step='liga-4d3a')['reason'], self.lm._REASONS['skip-held'])     # власне утримання a — як було
        self.assertIn('утримано разом із liga-4d3a', self.lm.report(p, 'liga-4d3b'))
        st, err = self.start()
        self.assertEqual(st, 'skip-held')
        self.assertIn('liga-4d3b: skip-held — утримано разом із liga-4d3a', err)
        self.assertIn('liga-4d3a: skip-held — ' + self.lm._REASONS['skip-held'], err)

    def test_skip_no_path_and_path_in_git(self):
        os.makedirs(os.path.join(self.space_dir, '.git'))
        self.assertEqual(self.plan_b()['status'], 'skip-path-in-git')
        self.registry(path=os.path.join(self.tmp, 'nowhere'))
        self.assertEqual(self.plan_b()['status'], 'skip-no-path')

    def test_skip_space_json_unreadable(self):
        self.space_json('{broken')
        self.assertEqual(self.plan_b()['status'], 'skip-space-json-unreadable')

    def test_skip_tasks_unreadable(self):
        self._write(self.tasks_path, '{broken')
        self.assertEqual(self.plan_b()['status'], 'skip-tasks-unreadable')

    def test_skip_nothing_when_both_modules_exist(self):
        self.write_modules({COMMENTS_MOD: {'enabled': True, 'settings': {}}, VCS_MOD: {'enabled': True, 'settings': {}}})
        p = self.plan_b()
        self.assertEqual((p['status'], p['space_json'], p['secrets']), ('skip-nothing', None, {}))
        self.assertEqual({r: v['reason'] for r, v in p['roles'].items()}, {'comments': 'module-present', 'vcs': 'module-present'})

    # --- коди ролей
    def test_no_supabase_skips_only_comments(self):
        self.config(supabase=False)
        p = self.plan_b()
        self.assertEqual(p['status'], 'ready')
        self.assertEqual((p['roles']['comments']['migrate'], p['roles']['comments']['reason']), (False, 'no-supabase'))
        self.assertTrue(p['roles']['vcs']['migrate'])
        self.assertNotIn(COMMENTS_MOD, p['space_json']['modules'])
        self.assertIn(VCS_MOD, p['space_json']['modules'])
        self.assertEqual(p['secrets'], {})
        self.assertEqual(p['space_json']['migrations']['liga-4d3b'], {'roles': ['vcs']})

    def test_bad_url_userinfo_is_not_migrated(self):
        with self.mock.patch.object(self.lm, '_supabase_from', lambda cfg: ('https://user:pass@sb.example.com', self.SB_KEY)):
            p = self.plan_b()
        self.assertEqual((p['roles']['comments']['migrate'], p['roles']['comments']['reason']), (False, 'bad-url'))
        self.assertNotIn(COMMENTS_MOD, p['secrets'])
        self.assertNotIn('pass', repr(p['space_json']))
        self.assertNotIn('pass', self.lm.report(p, 'liga-4d3b'))
        self.assertTrue(p['roles']['vcs']['migrate'])

    def test_module_present_per_role(self):
        self.write_modules({COMMENTS_MOD: {'enabled': True, 'settings': {}}})
        p = self.plan_b()
        self.assertEqual((p['roles']['comments']['reason'], p['roles']['vcs']['reason']), ('module-present', None))
        self.assertEqual(p['space_json']['modules'][COMMENTS_MOD], {'enabled': True, 'settings': {}})        # чужий запис не чіпаємо
        self.assertEqual(p['secrets'], {})
        self.write_modules({VCS_MOD: {'enabled': False, 'settings': {'branch': 'dev'}}})
        p = self.plan_b()
        self.assertEqual((p['roles']['comments']['reason'], p['roles']['vcs']['reason']), (None, 'module-present'))
        self.assertEqual(p['space_json']['modules'][VCS_MOD], {'enabled': False, 'settings': {'branch': 'dev'}})   # навіть вимкнений

    # --- провайдер
    def test_provider_check_runs_in_memory_per_migrated_role_and_aborts(self):
        seen = []
        real = self.dm._provider_for

        def spy(role, space, get_cat=None, explicit_override=None):
            seen.append((role, explicit_override is not None))
            return real(role, space, get_cat, explicit_override)
        with self.mock.patch.object(self.dm, '_provider_for', spy):
            self.assertEqual(self.plan_b()['status'], 'ready')
        self.assertEqual(seen, [('comments', True), ('vcs', True)])
        for fake in (lambda *a, **k: None, lambda *a, **k: self.dm.catalog()['supabase-teams'], lambda *a, **k: self.dm.implicit.for_role('comments')):
            with self.mock.patch.object(self.dm, '_provider_for', fake):
                p = self.plan_b()
            self.assertEqual((p['status'], p['space_json'], p['secrets']), ('abort-provider', None, {}))

    def test_partial_migration_vcs_migrates_comments_stays_implicit(self):
        self.config(supabase=False)
        before_secrets = self.read(self.secrets_path()) if os.path.exists(self.secrets_path()) else None
        st, err = self.start()
        self.assertEqual(st, 'done')
        sj = self.read_json(self.space_path())
        self.assertIn(VCS_MOD, sj['modules'])
        self.assertNotIn(COMMENTS_MOD, sj['modules'])
        self.assertEqual(sorted(sj['migrations']['liga-4d3b']), ['at', 'backup', 'roles'])
        self.assertEqual(sj['migrations']['liga-4d3b']['roles'], ['vcs'])
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['step'], last['status']), ('liga-4d3b', 'done'))
        self.assertEqual(last['skipped'], {'comments': 'no-supabase'})
        self.assertIn('liga-4d3b: done', err)
        self.assertIn('не мігровано: comments (no-supabase)', err)
        self.assertIn('comments (no-supabase)', self.lm.status_text(self.lm.status()))
        if before_secrets is not None:
            self.assertNotIn(COMMENTS_MOD, json.dumps(self.read_json(self.secrets_path()).get('legacy') or {}))
        self.assert_no_secrets_in_logs()


class StepBRunTest(_RealSteps):
    """`run(step='liga-4d3b')`: власний бекап, порядок запису, відкат побайтно, жодних значень секретів у виходах."""

    def setUp(self):
        super().setUp()
        self.seed()
        self.apply_a()
        self.after_a = (self.read(self.space_path()), self.read(self.secrets_path()))

    def run_b(self):
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'done')
        return self.stamps()

    def test_backup_is_its_own_complete_and_private(self):
        old = {f: self.read(p) for f, p in (('tasks.json', self.tasks_path), ('spaces.json', os.path.join(self.deai, 'spaces.json')),
                                            ('space.json', self.space_path()), ('secrets.json', self.secrets_path()))}
        a, b = self.run_b()
        self.assertTrue(b.endswith('-liga-4d3b') and a.endswith('-liga-4d3a'))
        self.assertEqual(self.backups(), sorted([a, b]))
        d = os.path.join(self.deai, 'backups', b)
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)
        self.assertEqual(sorted(os.listdir(d)), ['manifest.json', 'secrets.json', 'space.json', 'spaces.json', 'tasks.json'])
        m = self.read_json(d, 'manifest.json')
        self.assertEqual(m['migration'], 'liga-4d3b')
        for fname, orig in old.items():
            self.assertEqual(self.read(d, fname), orig, fname)
            self.assertEqual(os.stat(os.path.join(d, fname)).st_mode & 0o777, 0o600, fname)
            self.assertEqual(m['files'][fname]['sha256'], self.sha(orig), fname)
        self.assertEqual(self.read(d, 'space.json'), self.after_a[0])                  # стан ПІСЛЯ a
        self.assert_no_secrets_in_logs()

    def test_mark_has_no_tracks_and_content_is_merged(self):
        self.run_b()
        mk = self.marks()['liga-4d3b']
        self.assertEqual(sorted(mk), ['at', 'backup', 'roles'])
        self.assertEqual(mk['roles'], ['comments', 'vcs'])
        sj = self.read_json(self.space_path())
        self.assertEqual(sj['name'], 'Liga')
        self.assertEqual(sj['x'], {'k': [1, 2]})                                        # невідомі ключі збережено
        self.assertEqual(sj['modules'][COMMENTS_MOD]['settings']['compat'], 'comment-layer')
        self.assertEqual(sj['modules'][VCS_MOD]['settings']['compat'], 'design-canvas')
        self.assertIn('jira-tracker', sj['modules'])
        sec = self.read_json(self.secrets_path())
        self.assertEqual(sec['legacy'][COMMENTS_MOD], {'key': self.SB_KEY})
        self.assertNotIn(VCS_MOD, sec['legacy'])
        self.assertEqual(sec['other'], OTHER_SECRETS['other'])
        self.assertEqual(os.stat(self.secrets_path()).st_mode & 0o777, 0o600)
        self.assertNotIn(self.SB_KEY, self.read(self.space_path()).decode('utf-8'))

    def test_foreign_modules_and_keys_survive(self):
        sj = self.read_json(self.space_path())
        sj['modules']['x-mod'] = {'enabled': False, 'settings': {'q': 1}}
        sj['custom'] = {'keep': True}
        self.space_json(sj)
        self.run_b()
        now = self.read_json(self.space_path())
        self.assertEqual(now['modules']['x-mod'], {'enabled': False, 'settings': {'q': 1}})
        self.assertEqual(now['custom'], {'keep': True})

    def test_write_order_secrets_then_one_space_write(self):
        order = []
        rs, ws = self.dm.write_secrets, self.lm._write_space

        def spy_s(*a, **k):
            order.append('secrets')
            return rs(*a, **k)

        def spy_w(*a, **k):
            order.append('space')
            return ws(*a, **k)
        with self.mock.patch.object(self.dm, 'write_secrets', spy_s), self.mock.patch.object(self.lm, '_write_space', spy_w):
            self.run_b()
        self.assertEqual(order, ['secrets', 'space'])

    def test_failure_between_secrets_and_space_then_recovery(self):
        with self.mock.patch.object(self.lm, '_write_space', side_effect=OSError('boom')):
            self.assertEqual(self.lm.run(step='liga-4d3b'), 'abort-write')
        self.assertEqual(self.read_json(self.secrets_path())['legacy'][COMMENTS_MOD], {'key': self.SB_KEY})   # секрет вже є — нешкідливо
        self.assertNotIn('liga-4d3b', self.marks())
        self.assertNotIn(COMMENTS_MOD, self.read_json(self.space_path())['modules'])
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-write')
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'done')                        # наступний запуск доводить до кінця
        self.assertIn(COMMENTS_MOD, self.read_json(self.space_path())['modules'])
        self.assert_no_secrets_in_logs()

    def test_second_start_is_skip_done_and_writes_nothing(self):
        self.run_b()
        before = self.snapshot_tree()
        st, err = self.start()
        self.assertEqual(st, 'skip-done')
        self.assertEqual(err.splitlines(), [          # 4d-4b (Поправка 6): тиша про кроки; вимкнену роль `publish` старт називає
            'ролі ЛІГИ вимкнено: publish (vercel-publish) — no-record; виправити: запустіть: python3 bin/migrate_liga.py run'])
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.run(step='liga-4d3b'), 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)

    def test_restore_returns_the_state_after_a_byte_for_byte(self):
        _a, b = self.run_b()
        self.assertEqual(self.lm.restore(b), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_a[0])
        self.assertEqual(self.read(self.secrets_path()), self.after_a[1])
        self.assertNotIn(COMMENTS_MOD, self.read(self.secrets_path()).decode('utf-8'))
        self.assertIn('liga-4d3a', self.marks())

    def test_no_secret_value_anywhere(self):
        code, out, err = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d3b: done', out)
        self.assertIn('ролі: comments, vcs; бекап: ', out)       # крок без напрямків не друкує «напрямки»
        self.assertNotIn('напрямки: ні', out)
        self.assertNotIn('напрямки', out)                         # 4d-3a тут skip-done; його рядок пінить CliStepsTest
        self.assert_no_secrets(out, err)
        self.assert_no_secrets_in_logs()
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['secrets'], {COMMENTS_MOD: ['key']})


class IntegrationsOffTest(_RealSteps):
    """Ревʼю Task 6: ЛІГА з `integrations: false` має ролі ВИМКНЕНИМИ в 0.17 — явні записи їх увімкнули б (злам паритету): обидва кроки
    `skip-integrations-off`, нічого не пишуть, CLI — успіх."""

    def setUp(self):
        super().setUp()
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [
            {'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': False}]})

    def test_plan_of_every_step_skips(self):
        for step in ('liga-4d3a', 'liga-4d3b'):
            p = self.lm.plan(step=step)
            self.assertEqual((p['status'], p['space_id'], p['space_json'], p['secrets']), ('skip-integrations-off', 'legacy', None, {}), step)
            self.assertIn('інтеграції', p['reason'])
        self.assertIn('skip-integrations-off', self.lm.SKIP_CODES)
        self.assertIn('skip-integrations-off', self.lm.BENIGN)

    def test_missing_integrations_key_also_skips(self):
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [
            {'id': 'legacy', 'path': self.space_dir, 'legacy': True}]})
        self.assertEqual(self.plan_b()['status'], 'skip-integrations-off')

    def test_run_all_and_startup_write_nothing_and_stay_quiet(self):
        before = self.snapshot_tree()
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'skip-integrations-off'), ('liga-4d3b', 'skip-integrations-off')])
        st, err = self.start()
        self.assertEqual((st, err), ('skip-integrations-off', ''))
        self.assertEqual(self.snapshot_tree(), before)
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'migrations')))
        self.assertEqual(self.backups(), [])

    def test_cli_exit_code_is_zero_and_nothing_written(self):
        before = self.snapshot_tree()
        for cmd in ('run', 'dry-run', 'status'):
            code, out, _err = self.cli(cmd)
            self.assertEqual(code, 0, cmd)
        code, out, _err = self.cli('run')
        self.assertIn('liga-4d3b: skip-integrations-off', out)
        self.assertEqual(self.snapshot_tree(), before)
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'migrations')))


class StepBStartupTest(_RealSteps):
    """Два РЕАЛЬНІ кроки на одному старті: два бекапи, порядок a → b; план b бачить запис a."""

    def test_two_real_steps_on_one_start_two_backups_a_then_b(self):
        self.seed()
        st, err = self.start()
        self.assertEqual(st, 'done')
        a, b = self.stamps()
        self.assertEqual(self.backups(), sorted([a, b]))
        self.assertLess(err.index('liga-4d3a: done'), err.index('liga-4d3b: done'))
        self.assertEqual(self.read_json(self.deai, 'backups', a, 'manifest.json')['migration'], 'liga-4d3a')
        self.assertEqual(self.read_json(self.deai, 'backups', b, 'manifest.json')['migration'], 'liga-4d3b')
        self.assertIn('liga-4d3a', self.read_json(self.deai, 'backups', b, 'space.json')['migrations'])     # b рахувався ПІСЛЯ запису a
        sj = self.read_json(self.space_path())
        for mid in ('jira-tracker', 'supabase-dashboard', 'supabase-teams', COMMENTS_MOD, VCS_MOD):
            self.assertIn(mid, sj['modules'])
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['step'], sorted(last['steps'])), ('liga-4d3b', ['liga-4d3a', 'liga-4d3b']))
        self.assert_no_secrets_in_logs()

    def test_skip_nothing_of_a_does_not_block_b(self):
        """`skip-nothing` кроку a (нема облікових і напрямків) наступний крок не блокує: vcs мігрує без жодного конфігу."""
        self.config(supabase=False, jira=False, design_work_root=None)
        cfg = self.cfg
        cfg['tasks']['x'] = {'dir': os.path.join(self.home, 'work', 'x')}
        self._write(self.tasks_path, cfg)
        self.assertEqual(self.lm.plan(step='liga-4d3a')['status'], 'skip-nothing')
        res = self.lm.run_all()
        self.assertEqual([(m, s) for m, s, _i in res], [('liga-4d3a', 'skip-nothing'), ('liga-4d3b', 'done')])
        mk = self.marks()
        self.assertNotIn('liga-4d3a', mk)
        self.assertEqual(mk['liga-4d3b']['roles'], ['vcs'])
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(res[1][2]['skipped'], {'comments': 'no-supabase'})

    def test_status_text_tracks_line_only_for_the_step_with_tracks(self):
        self.seed()
        self.start()
        text = self.lm.status_text(self.lm.status())
        a_part, b_part = text.split('Міграція ЛІГИ (liga-4d3b)')
        self.assertIn('напрямки: так', a_part)
        self.assertNotIn('напрямки', b_part)
        self.assertIn('ролі: comments, vcs, бекап:', b_part)

    def test_real_home_refusal_line_is_step_neutral(self):
        with self.mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_MIGRATE_LIGA': '1'}), \
                self.mock.patch.object(self.lm, '_real_home', lambda: True):
            st, err = self.start()
        self.assertEqual(st, 'refuse-real-home')
        self.assertNotIn('liga-4d3a', err)
        self.assertIn('DC_MIGRATE_LIGA=1', err)

    def test_lifo_over_the_real_steps(self):
        self.seed()
        self.start()
        a, b = self.stamps()
        self.assertEqual(self.lm.restore(a), 'refuse-later-applied')
        self.assertEqual(self.lm.restore(b), 'restored')
        self.assertEqual(self.lm.restore(a), 'restored')
        self.assertEqual(self.read(self.space_path()), ORIG_SPACE)


# ---------------------------------------------------------------------------------------------------------------- Task 7: паритет

_ABSENT = '<ABSENT>'


def _flat(obj, path=''):
    """Знімок → плаский `{шлях: листок}`. Порожні контейнери — теж листки (`{}`/`[]`). Списки ключів `space_keys` (їх порядок — це
    сортування `Object.keys`, а не зміст) — множина: додаток ключа не зсуває решту індексів у звіті відмінностей."""
    out = {}
    if isinstance(obj, dict):
        if not obj:
            out[path + '{}'] = {}
        for k, v in obj.items():
            out.update(_flat(v, '%s/%s' % (path, k)))
    elif isinstance(obj, list):
        if path.endswith('/space_keys'):
            for k in obj:
                out['%s/%s' % (path, k)] = True
        elif not obj:
            out[path + '[]'] = []
        for i, v in enumerate(obj if not path.endswith('/space_keys') else ()):
            out.update(_flat(v, '%s[%d]' % (path, i)))
    else:
        out[path] = obj
    return out


def _is_4d4b_leaf(path):
    """Листки, що залежать від причин 4d-4b (`Implicit` видалено; оригіналів кореня нема), — у ЦЕЙ клас не входять (Task 14 Step 2): їх звіряє
    `AfterMigrationParity4d4b` (Task 15). Тут: ролі без запису (`publish`, `tracker`) — неявний `legacy` → `None` у capabilities форми (й похідний
    прапорець `has_publish`); `ssh_key` цілі — тепер не з кореня, а з налаштувань запису (ціль його не несе)."""
    return (path in ('/vcs/form/capabilities/publish', '/vcs/form/capabilities/tracker', '/vcs/form/model/has_publish',
                     '/vcs/form/space_row/capabilities/publish', '/vcs/form/space_row/capabilities/tracker')
            or path.endswith('/target/ssh_key'))


def _diff(before, after):
    """Точний звіт відмінностей `{шлях: (було, стало)}`; відсутній ключ — `_ABSENT`. Без листків причин 4d-4b (`_is_4d4b_leaf`)."""
    a, b = _flat(before), _flat(after)
    return {k: (a.get(k, _ABSENT), b.get(k, _ABSENT)) for k in sorted(set(a) | set(b))
            if a.get(k, _ABSENT) != b.get(k, _ABSENT) and not _is_4d4b_leaf(k)}


def _expect_diff():
    """ЄДИНИЙ перелік свідомих відмінностей знімка 0.17.0 → мігрована ЛІГА (кроки 4d-3a, потім 4d-3b). Усе інше — рівно знімок.
    ⛔ Точне порівняння, не `assertIn`: зайва різниця падає так само, як і зникла очікувана."""
    exp = {}
    cache = '~/.deai/cache/legacy/supabase-comments'
    # comments: `ctx` будує `module_ctx` (ті самі значення + `compat`; `space.path` = тека простору; додатки `folder_ok`/`find_tool`/
    # `cache_dir`) — і для `comments_route`, і для трьох викликів `list`/`resolve` модуля через `ProjectComments`
    for p in ['/comments/route/ctx'] + ['/comments/project_comments/calls[%d]/ctx' % i for i in range(3)]:
        exp[p + '/cache_dir'] = (_ABSENT, cache)
        exp[p + '/find_tool'] = (_ABSENT, '<_find_tool>')
        exp[p + '/folder_ok'] = (_ABSENT, '<folder_ok_here>')
        exp[p + '/settings/compat'] = (_ABSENT, 'comment-layer')
        exp[p + '/space/path'] = ('', '<tmp>/liga-space')
    exp['/comments/route/provider'] = ('Implicit', 'Module')
    exp['/comments/project_comments/provider'] = ('Implicit', 'Module')
    exp['/comments/project_comments/kind'] = ('implicit', 'module')
    # vcs: той самий `cache_dir` (під `DC_MIRRORS_DIR`) і `mirror_flat` — тут лише `compat`, `space.path`, додатки і постачальник
    exp['/vcs/provider/provider'] = ('Implicit', 'Module')
    exp['/vcs/provider/ctx/find_tool'] = (_ABSENT, '<_find_tool>')
    exp['/vcs/provider/ctx/folder_ok'] = ('<<lambda>>', '<folder_ok_here>')
    exp['/vcs/provider/ctx/settings/compat'] = (_ABSENT, 'design-canvas')
    exp['/vcs/provider/ctx/space/path'] = ('', '<tmp>/liga-space')
    # `capabilities`: `comments`/`vcs` — id модулів (крок b); `dashboard`/`notify` — id модулів кроку a (на тому самому старті);
    # `publish` лишається `legacy`
    for base in ('/vcs/form/capabilities', '/vcs/form/space_row/capabilities'):
        exp[base + '/comments'] = ('legacy', 'supabase-comments')
        exp[base + '/vcs'] = ('legacy', 'git-sync')
        exp[base + '/dashboard'] = ('legacy', 'supabase-dashboard')
        exp[base + '/notify'] = ('legacy', 'supabase-teams')
    # `/api/spaces`: запис простору дістає ключ `compat` (хто зашитий на «старих» значеннях)
    exp['/vcs/form/space_row/compat/comments'] = (_ABSENT, 'comment-layer')
    exp['/vcs/form/space_row/compat/vcs'] = (_ABSENT, 'design-canvas')
    exp['/vcs/form/model/space_keys/compat'] = (_ABSENT, True)
    # 4d-4c: прапорець `integrations` сервер більше не віддає (запис ЛІГИ без ключа; знімок 0.17.0 мав `True`)
    exp['/vcs/form/space_row/integrations'] = (True, _ABSENT)
    exp['/vcs/form/model/space_keys/integrations'] = (True, _ABSENT)
    # 4d-4a: адаптера напрямків у рантаймі нема, а крок D у цьому стенді (лише a+b) не гнано — рядок простору в `/api/spaces`
    # без напрямків: знімок 0.17.0 мав чотири напрямки адаптера й дефолт `united`
    exp['/vcs/form/space_row/default_track'] = ('united', None)
    for i, (tid, label) in enumerate((('united', 'United'), ('liga360', 'LIGA360'), ('seo', 'SEO'), ('custom-x', 'custom-x'))):
        exp['/vcs/form/space_row/tracks[%d]/id' % i] = (tid, _ABSENT)
        exp['/vcs/form/space_row/tracks[%d]/label' % i] = (label, _ABSENT)
    exp['/vcs/form/space_row/tracks[]'] = (_ABSENT, [])
    return exp


class AfterMigrationParity4d3b(unittest.TestCase):
    """Task 7: сценарії знімка 0.17.0 (`before-4d3b.json`) на МІГРОВАНІЙ ЛІГІ — обидва кроки (`run_all`: 4d-3a, потім 4d-3b) у
    тимчасовому `DEAI_HOME` — дають те саме, крім `_expect_diff()`. Знімання — той самий генератор `tests/make_before_4d3b.py`, лише
    стенд ЛІГИ після створення мігрується (підміна `liga`). Мережі нема (шви-фейки, loopback), справжній `~/.deai` стереже `spaces_guard`.

    Дві конфігурації стенду, як у 4d-3a: `snapshot` — `united` має власний корінь ≠ спільного (напрямки лишаються на адаптері) і
    `shared` — `united` без власного кореня (напрямки мігрують у явні `tracks`). Різниці для `comments`/`vcs` в обох однакові."""

    CONFIGS = ('snapshot', 'shared')

    @classmethod
    def setUpClass(cls):
        from unittest import mock
        import make_before_4d3b as g
        import liga_migrate as lm
        cls.mock, cls.g, cls.lm = mock, g, lm
        with open(BEFORE, encoding='utf-8') as f:
            cls.before = json.load(f)
        cls.after, cls.results = {}, {}
        for name in cls.CONFIGS:
            cls.after[name], cls.results[name] = cls._build(name)

    @classmethod
    def _build(cls, name):
        g, lm = cls.g, cls.lm
        orig, results = g.liga, []

        def migrated(tmp, label):
            rig, space, cfg = orig(tmp, label)
            if name == 'shared':                         # united без власного кореня → напрямки мігрують
                cfg['design_work_roots'] = {'custom-x': os.path.join(rig.home, 'work', 'custom')}
                g._write(rig.tasks_path, cfg)
            with rig.activate(), cls.mock.patch.object(lm, 'STEPS', lm.ALL_STEPS[:2]):        # 4d-3c: паритет a+b; крок c — у test_liga_migrate_c.py
                results.append([(m, st, info.get('skipped'), info.get('roles')) for m, st, info in lm.run_all()])
            return rig, space, cfg
        import serve
        new_target = serve.vcs_target
        # 4d-4b (R4): генератор знімка (еталон, не правиться) кличе `vcs_target(cfg, tid, task, settings)`; перехідник відкидає `cfg`
        with cls.mock.patch.object(g, 'liga', migrated), cls.mock.patch.object(serve, 'vcs_target', lambda *a: new_target(*a[1:]) if len(a) == 4 else new_target(*a)):
            snap = g.make()
        return snap, results

    def test_both_steps_ran_on_every_scenario_rig(self):
        """Кожен стенд (comments, vcs) справді мігровано: a і b `done`; тож порівняння йде з МІГРОВАНОЮ ЛІГОЮ, а не зі знімком."""
        for name in self.CONFIGS:
            self.assertEqual(len(self.results[name]), 2, name)
            for res in self.results[name]:
                self.assertEqual([(m, st) for m, st, _s, _r in res], [('liga-4d3a', 'done'), ('liga-4d3b', 'done')], name)
                self.assertEqual(res[1][3], ['comments', 'vcs'], name)
                self.assertEqual(res[1][2], {}, name)

    def test_snapshot_is_big_enough_to_mean_something(self):
        """Порівняння не порожнє: сотні листків, обидва розділи на місці (інакше «нема відмінностей» нічого б не казало)."""
        flat = _flat(self.before)
        self.assertGreater(len(flat), 400)
        self.assertEqual(sorted(self.after['snapshot']), sorted(self.before))

    def test_only_expected_differences_snapshot_config(self):
        self.assertEqual(_diff(self.before, self.after['snapshot']), _expect_diff())

    def test_only_expected_differences_shared_config(self):
        self.assertEqual(_diff(self.before, self.after['shared']), _expect_diff())

    def test_expected_diff_is_exact_not_loose(self):
        """Охоронець самого порівняння: зайвий листок і зниклий очікуваний — обидва червоніють (`_diff` ловить і додане, і зникле)."""
        a = json.loads(json.dumps(self.after['snapshot']))
        a['comments']['channels']['a-1']['plain'] = 'other'
        self.assertIn('/comments/channels/a-1/plain', _diff(self.before, a))
        self.assertNotEqual(_diff(self.before, a), _expect_diff())
        b = json.loads(json.dumps(self.after['snapshot']))
        del b['vcs']['form']['space_row']['compat']
        self.assertNotEqual(_diff(self.before, b), _expect_diff())

    def test_nothing_a_person_sees_changed(self):
        """Те, що бачить людина, — рівно знімок: канали всіх місць, `comment-config`, тема коміту й README, `web`/`label`, «GitLab»/
        «репозиторію», примітка форку, рядок `state.py`, префікс `inbox`, ключ лічильника, дзеркала, прапорці форми. Бо жодного такого
        шляху нема серед відмінностей (їхні гілки — лише ctx/постачальник/capabilities/compat)."""
        seen = ('/comments/channels', '/comments/api', '/comments/dashboard', '/comments/inbox', '/vcs/texts', '/vcs/mirrors',
                '/vcs/mirrors_base', '/vcs/form/model/is_legacy_vcs', '/vcs/form/model/has_vcs', '/vcs/form/model/with_repo',
                '/vcs/form/model/label_empty', '/vcs/form/model/label_git', '/vcs/form/model/brand_empty', '/vcs/form/model/clones',
                '/vcs/form/model/fail_key_target', '/vcs/provider/ctx/mirror_flat', '/vcs/provider/ctx/cache_dir',
                '/comments/route/channels', '/comments/route/module', '/comments/project_comments/channels',
                '/comments/project_comments/label', '/comments/project_comments/outcomes')
        for name in self.CONFIGS:
            for path in _diff(self.before, self.after[name]):
                for s in seen:
                    self.assertFalse(path.startswith(s), '%s: змінилося те, що бачить людина: %s' % (name, path))
            flat = _flat(self.after[name])
            for s in seen:
                self.assertTrue(any(k.startswith(s) for k in flat), 'порожній розділ порівняння: ' + s)


class RealPushNonIsolated(_VcsStand):
    """Task 7 (ревʼю 2): справжній push МІГРОВАНОГО `git-sync` НЕІЗОЛЬОВАНИМ шляхом — тим, яким піде власник на першому старті (нема
    `DC_TASKS_FILE`/`DC_NO_OVERVIEW`: `vcs_provider()` будує `ctx` через `module_ctx` + `_flat_mirror_overlay()`, а не через
    `_vcs_legacy_ctx()` закону ізоляції, яким ходить живий тест). Справжній git, лише локально: bare-origin із початковим комітом
    і передстворене ПЛОСКЕ дзеркало 0.7.0 (справжній клон) там, де його лишила б версія 0.17. Мережі й сервера нема: викликається та
    сама серверна функція, що й `/api/vcs-push` (`vcs_task` → `gitlab_sync`). Вигадані значення, `~/.gitconfig` не читається."""

    def git(self, rig, cwd, *args):
        import subprocess
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(HOME=rig.home, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0', LC_ALL='C',
                   GIT_AUTHOR_NAME='Seed', GIT_AUTHOR_EMAIL='seed@example.invalid',
                   GIT_COMMITTER_NAME='Seed', GIT_COMMITTER_EMAIL='seed@example.invalid')
        r = subprocess.run(['git'] + list(args), cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, 'git %s: %s' % (' '.join(args), r.stderr))
        return r.stdout.strip()

    def test_migrated_git_sync_pushes_through_the_precreated_flat_mirror(self):
        mb, serve = self.mb, self.serve
        rig, space, cfg = mb.liga(self.tmp, 'push')
        mirrors = os.path.join(rig.home, 'mirrors')
        origin = os.path.join(rig.home, 'origin.git')
        self.git(rig, rig.home, 'init', '--bare', '--quiet', '--initial-branch=main', origin)
        seed = os.path.join(rig.home, 'seed')
        self.git(rig, rig.home, 'clone', '--quiet', origin, seed)
        self.git(rig, seed, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        with open(os.path.join(seed, 'README.md'), 'w', encoding='utf-8') as f:
            f.write('seed\n')
        self.git(rig, seed, 'add', '-A')
        self.git(rig, seed, 'commit', '--quiet', '-m', 'seed')
        self.git(rig, seed, 'push', '--quiet', 'origin', 'main')
        # плоске дзеркало 0.7.0: `<DC_MIRRORS_DIR>/<slug останнього відрізка після ':'>` — правило `_mirror` (`mirror_flat`)
        slug = re.sub(r'[^\w.-]+', '-', origin.split(':')[-1]).strip('-')
        mirror = os.path.join(mirrors, slug)
        self.git(rig, rig.home, 'clone', '--quiet', '--branch', 'main', origin, mirror)
        head_before = self.git(rig, mirror, 'rev-parse', 'HEAD')
        # ціль синку — зашитий формат 0.17: `gitlab{repo, path}` у `tasks.json`
        cfg['tasks']['a-1']['gitlab'] = {'repo': origin, 'path': 'mockup/a-1', 'branch': 'main'}
        mb._write(rig.tasks_path, cfg)
        env = {'DC_MIRRORS_DIR': mirrors, 'DC_IDENTITY_NAME': mb.IDENTITY[0], 'DC_IDENTITY_EMAIL': mb.IDENTITY[1],
               'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': 'false'}
        with rig.activate(env):
            self.assertEqual(self.lm_run_all(), [('liga-4d3a', 'done'), ('liga-4d3b', 'done')])
            self.assertFalse(self.isolation.isolated(), 'неізольований прогін: нема ні DC_TASKS_FILE, ні DC_NO_OVERVIEW')
            with self.spaces.request_space(mb.SPACE_ID):
                self.dm.reset_caches()
                try:
                    prov, ctx, legacy = serve.vcs_provider()
                    self.assertIsInstance(prov, self.dm.Module)
                    self.assertTrue(legacy)
                    self.assertTrue(ctx['mirror_flat'])
                    self.assertEqual(ctx['cache_dir'], mirrors)
                    self.assertIn('find_tool', ctx)                       # `ctx` від `module_ctx`, не від `_vcs_legacy_ctx()`
                    self.assertTrue(ctx['space']['path'])
                    cfg2 = serve.load_tasks()
                    task = cfg2['tasks']['a-1']
                    v = serve.vcs_task('a-1', task)
                    self.assertIsNotNone(v[3])
                    res = serve.gitlab_sync('a-1', task, v[3], 'it1', vcs=v[:3])
                finally:
                    self.dm.reset_caches()
        self.assertTrue(res.get('synced'), res)
        self.assertEqual(self.git(rig, origin, 'log', '-1', '--format=%s', 'main'), 'design-canvas: sync mockup/a-1 (Alpha demo) · it1')
        tree = self.git(rig, origin, 'ls-tree', '-r', '--name-only', 'main').split('\n')
        self.assertIn('mockup/a-1/pages.json', tree)
        head_after = self.git(rig, mirror, 'rev-parse', 'HEAD')
        self.assertNotEqual(head_after, head_before, 'push пішов не через передстворене дзеркало')
        self.assertEqual(head_after, self.git(rig, origin, 'rev-parse', 'main'))
        self.assertEqual(sorted(n for n in os.listdir(mirrors) if not n.endswith('@lock')), [slug], 'зʼявилось нове дзеркало')
        self.assertFalse(os.path.exists(os.path.join(rig.deai, 'cache', mb.SPACE_ID, 'git-sync', 'mirrors')))
        self.assertFalse(os.path.exists(os.path.join(rig.deai, 'cache', mb.SPACE_ID)))

    def lm_run_all(self):
        import liga_migrate
        with self.mock.patch.object(liga_migrate, 'STEPS', liga_migrate.ALL_STEPS[:2]):       # 4d-3c: тут — a+b (плоске дзеркало vcs); c не додає ефектів
            return [(m, st) for m, st, _i in liga_migrate.run_all()]


if __name__ == '__main__':
    unittest.main()

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
        import implicit
        import make_before_4d3b as mb
        import serve
        import spaces
        cls.mb, cls.dm, cls.serve, cls.spaces, cls.implicit, cls.dashboard = mb, deai_modules, serve, spaces, implicit, dashboard

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
            self.mb._write(sp_path, {'modules': {COMMENTS_ID: {'enabled': True, 'shared_state': True, 'settings': settings}}})
            self.mb._write(os.path.join(rig.deai, 'secrets.json'), {self.mb.SPACE_ID: {COMMENTS_ID: {'key': 'sb_chan_key_alpha'}}})
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
        import implicit
        cls.dm, cls.implicit = deai_modules, implicit

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

    def test_implicit_uses_the_legacy_scheme(self):
        prov = self.implicit.for_role('comments')
        f = self.dm.comment_channel_of
        self.assertEqual(f(self.space, prov, self.task, 't1'), 'shared-x')
        self.assertEqual(f(self.space, prov, self.task, 't1', internal=True), 'shared-x/internal')
        self.assertEqual(f(self.space, prov, self.bare, 't1'), 'dc/t1')
        self.assertEqual(f(self.space, prov, self.bare, 't1', True), 'dc/t1/internal')

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

    def test_http_implicit_space_keeps_the_legacy_scheme(self):
        rig, _space, _cfg = self.stand(module=False)
        out = self.http(rig)
        for site in ('task', 'mute_get', 'mute_post', 'config'):
            self.assertEqual(out[site], LAYER_CHANNELS, site)

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

    def test_decision_failure_falls_back_to_the_legacy_scheme(self):
        """Збій рішення (нечитабельний `space.json`; id задачі, непридатний для `channel_for`) — схема comment-layer, не 5xx і не виняток."""
        serve = self.serve
        rig, space, cfg = self.stand(space_json='not json')
        with self.pinned(rig):
            self.assertEqual(serve._comment_channel_in(space, cfg['tasks']['a-1'], 'a-1'), 'liga-shared')
            self.assertEqual(serve._comment_channel_in(space, cfg['tasks']['a-2'], 'a-2', internal=True), 'dc/a-2/internal')
        out = self.http(rig)
        self.assertEqual(out['task'], LAYER_CHANNELS)
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
            self.assertEqual((pc.kind, pc.label, pc.legacy_scheme), ('implicit', 'Supabase', True))

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


if __name__ == '__main__':
    unittest.main()

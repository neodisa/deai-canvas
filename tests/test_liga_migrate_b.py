"""Міграція ЛІГИ, другий крок — `comments` і `vcs` (етап 4d-3b, 0.18.0).

Тут: знімок поведінки 0.17.0 (`Before4d3bShape`, Task 1); канал, `compat`, ізоляція, кроки й паритет додаються наступними
задачами. Спека `docs/superpowers/specs/2026-11-06-liga-migration-b-design.md`.
"""
import json
import os
import re
import sys
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
        self.assertFalse(any(c['keys_with_open_comments'] for c in d['pushed'][0]['cards']), 'open_comments на картці не шлемо')

    def test_inbox_short_prefix(self):
        i = self.snap['comments']['inbox']
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
        self.assertGreaterEqual(len(rows), 3)
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


if __name__ == '__main__':
    unittest.main()

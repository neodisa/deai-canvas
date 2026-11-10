"""Паритет після міграції `AfterMigrationParity4d4b` (етап 4d-4b): ті самі сценарії, що знімок 0.20.0 (`fixtures/liga-migration/before-4d4b.json`), на
МІГРОВАНІЙ ЛІЗІ п'ятьма кроками, НЕізольовано (шлях власника: `DEAI_HOME` + реєстр, без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`; живі тести ізольовані і
цього не доводять). Збір — `after_4d4b_collect.collect_all` (ті самі розділи, що в генераторі знімка, нові підписи функцій; на стендах `differs`/`partial` запис
міняється ПЕРЕД кроком Е, бо Е ці розбіжності й оцінює). Очікуваний перелік відмінностей — ТОЧНИЙ: кожен листок із «було» зі знімка і «стало» буквально.
Таблиці виміряні на реальній поведінці; кожен листок — або задуманий наслідок 4d-4b (`Implicit` видалено, оригінали не читаються), або зафіксована
відмінність (пароль превʼю `differs`: рішення власника 09.11.2026 — корінь перезаписує відмінний секрет, видимої зміни нема; решта `differs` — не перезаписується). Мережі нема (`SocketTripwire` + `NoNet`), справжній
`~/.deai` стереже `spaces_guard`."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'bin'))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
STANDS = ('regular', 'differs', 'partial', 'unmigrated', 'plain')
ABSENT = '<absent>'
#: Розділи, що порівнюються окремо буквальними списками (позиційні), а не листками.
SEPARATE = ('/root_keys', '/startup_text')


def _flat(obj, path=''):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flat(v, '%s/%s' % (path, k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flat(v, '%s[%d]' % (path, i)))
        out[path + '[]'] = len(obj)
    else:
        out[path] = obj
    return out


def _diff(before, after):
    """`{шлях: (було, стало)}` для листків, що відрізняються (відсутній — `ABSENT`), без `SEPARATE`."""
    fb, fa = _flat(before), _flat(after)
    return {k: (fb.get(k, ABSENT), fa.get(k, ABSENT)) for k in sorted(set(fb) | set(fa))
            if not k.startswith(SEPARATE) and fb.get(k, ABSENT) != fa.get(k, ABSENT)}


def _expect(before, after_literals):
    """Очікувана зміна: «було» береться зі ЗНІМКА, «стало» — буквальне значення з таблиці (не обчислене)."""
    fb = _flat(before)
    return {k: (fb.get(k, ABSENT), v) for k, v in after_literals.items()}


#: Пуск синку дашборда (`Handler._overview_sync`), шлях власника, запит БЕЗ зафіксованого простору: було — неявний простір (`Implicit`) → пуск із
#: аргументами `legacy`; тепер постачальника нема → синку нема. Однаково на всіх п'яти стендах (4d-4b: `Implicit` видалено).
DASH_IMPLICIT = {
    '/dashboard_sync/non_isolated/implicit_space/args': None,
    '/dashboard_sync/non_isolated/implicit_space/args[0]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/args[1]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/args[2][0]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/args[2][1]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/args[2][]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/args[]': ABSENT,
    '/dashboard_sync/non_isolated/implicit_space/called': False,
}
#: Те саме для простору, ЗАФІКСОВАНОГО в запиті, на немігрованій ЛІЗІ: роль `dashboard` вимкнена → синку нема.
DASH_IN_SPACE = {k.replace('/implicit_space/', '/in_space/'): v for k, v in DASH_IMPLICIT.items()}

EXPECT_REGULAR = dict({
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/api/modules/list/git-sync/fields/ssh_key': '~/.ssh/example',
    '/api/modules/list/vercel-publish/fields/password': '<set>',
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/provider/settings/ssh_key': '~/.ssh/example',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
}, **DASH_IMPLICIT)

#: `differs`: ключ SSH запису (`/other/key`) НЕ перезаписується коренем (рішення контролера 07.11.2026), а секрет `password` (`inert-old`) — ПЕРЕЗАПИСУЄТЬСЯ
#: коренем (рішення власника 09.11.2026): режим модуля бере секрет запису, що тепер = корінь → пароль превʼю `pw-alpha` НЕ змінюється (листка нема).
EXPECT_DIFFERS = dict({
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/registry_ssh': '/other/key',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
}, **DASH_IMPLICIT)

EXPECT_PARTIAL = dict({
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/api/modules/list/git-sync/fields/ssh_key': '~/.ssh/example',
    '/api/modules/list/vercel-publish/fields/password': '<set>',
    '/api/task/capabilities/notify': None,
    '/api/task/capabilities/tracker': None,
    '/api/tasks_overview/tracker': None,
    '/api/tasks_overview/tracker/error': ABSENT,
    '/api/tasks_overview/tracker/okAt': ABSENT,
    '/api/teams_mute/body/channel': ABSENT,
    '/api/teams_mute/body/code': 'notify-off',
    '/api/teams_mute/body/error': 'сповіщень Teams у просторі нема',
    '/api/teams_mute/body/ok': False,
    '/api/teams_mute/status': 409,
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/capabilities/ok/notify': None,
    '/capabilities/ok/tracker': None,
    '/isolation/notify_state/message': 'сповіщень Teams у просторі нема',
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/provider/in_space/notify/api': None,
    '/provider/in_space/notify/type': 'NoneType',
    '/provider/in_space/tracker/api': None,
    '/provider/in_space/tracker/type': 'NoneType',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/provider/settings/ssh_key': '~/.ssh/example',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
}, **DASH_IMPLICIT)

EXPECT_UNMIGRATED = dict({
    '/api/task/comment_channel': None,          # 4d-4c (Поправка 10): канал є лише за постачальником `comments`; немігрована ЛІГА без запису — `None`
    '/api/comment_config/channel': None,
    '/api/comment_config/code': 'integrations-off',
    '/api/comment_config/config': None,
    '/api/comment_config/config/key': ABSENT,
    '/api/comment_config/config/shotsBucket': ABSENT,
    '/api/comment_config/config/url': ABSENT,
    '/api/comment_config/module': None,
    '/api/comment_config/status': 409,
    '/api/task/capabilities/comments': None,
    '/api/task/capabilities/dashboard': None,
    '/api/task/capabilities/notify': None,
    '/api/task/capabilities/publish': None,
    '/api/task/capabilities/tracker': None,
    '/api/task/capabilities/vcs': None,
    '/api/task/preview_password': '1100',
    '/api/tasks_overview/team': None,
    '/api/tasks_overview/team/error': ABSENT,
    '/api/tasks_overview/team/tab': ABSENT,
    '/api/tasks_overview/tracker': None,
    '/api/tasks_overview/tracker/error': ABSENT,
    '/api/tasks_overview/tracker/okAt': ABSENT,
    '/api/teams_mute/body/channel': ABSENT,
    '/api/teams_mute/body/code': 'notify-off',
    '/api/teams_mute/body/error': 'сповіщень Teams у просторі нема',
    '/api/teams_mute/body/ok': False,
    '/api/teams_mute/status': 409,
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/capabilities/ok/comments': None,
    '/capabilities/ok/dashboard': None,
    '/capabilities/ok/notify': None,
    '/capabilities/ok/publish': None,
    '/capabilities/ok/tracker': None,
    '/capabilities/ok/vcs': None,
    '/isolation/comments_ctx/code': 'module-error',
    '/isolation/comments_ctx/key_set': ABSENT,
    '/isolation/comments_ctx/raised': 'ModuleError',
    '/isolation/comments_ctx/url': ABSENT,
    '/isolation/notify_state/message': 'сповіщень Teams у просторі нема',
    '/isolation/team_rows[1]': 'вимкнено: у просторі нема постачальника командного дашборда',
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/provider/in_space/comments/api': None,
    '/provider/in_space/comments/type': 'NoneType',
    '/provider/in_space/dashboard/api': None,
    '/provider/in_space/dashboard/type': 'NoneType',
    '/provider/in_space/notify/api': None,
    '/provider/in_space/notify/type': 'NoneType',
    '/provider/in_space/publish/api': None,
    '/provider/in_space/publish/type': 'NoneType',
    '/provider/in_space/tracker/api': None,
    '/provider/in_space/tracker/type': 'NoneType',
    '/provider/in_space/vcs/api': None,
    '/provider/in_space/vcs/type': 'NoneType',
    '/registry_ssh': '~/.ssh/gitlab_ed25519',
    '/vcs_target/provider': None,
    '/vcs_target/provider/legacy_texts': ABSENT,
    '/vcs_target/provider/settings/autosync': ABSENT,
    '/vcs_target/provider/settings/branch': ABSENT,
    '/vcs_target/provider/settings/compat': ABSENT,
    '/vcs_target/provider/settings/host_ip': ABSENT,
    '/vcs_target/provider/settings/path': ABSENT,
    '/vcs_target/provider/settings/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/effective/host_ip': ABSENT,
    '/vcs_target/task_gitlab/effective/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/target/branch': ABSENT,
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/path': ABSENT,
    '/vcs_target/task_gitlab/target/repo': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/target/task': ABSENT,
    '/vcs_target/task_gitlab_own_key/effective/host_ip': ABSENT,
    '/vcs_target/task_gitlab_own_key/effective/ssh_key': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/branch': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/path': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/repo': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/ssh_key': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/task': ABSENT,
    '/vcs_target/task_vcs/effective/host_ip': ABSENT,
    '/vcs_target/task_vcs/effective/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/branch': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/path': ABSENT,
    '/vcs_target/task_vcs/target/repo': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/task': ABSENT,
}, **dict(DASH_IMPLICIT, **DASH_IN_SPACE))

EXPECT_PLAIN = dict({
    # 4d-4c: простір без запису `static-publish` не має неявного публікатора (стенд складено без `create_space`)
    '/api/modules/list/static-publish/enabled': False,
    '/api/modules/list/static-publish/implicit': False,
    '/api/task/capabilities/publish': None,
    '/api/task/preview_gate/state': 'none',
    '/capabilities/ok/publish': None,
    '/provider/in_space/publish/api': None,
    '/provider/in_space/publish/type': 'NoneType',
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
}, **DASH_IMPLICIT)

ROOT_KEYS_AFTER_REGULAR = ['current', 'design_work_root', 'design_work_roots', 'profile_repos', 'registry', 'tasks']
ROOT_KEYS_AFTER_DIFFERS = ['current', 'design_work_root', 'design_work_roots', 'gitlab_ssh_key', 'jira_token', 'profile_repos', 'registry', 'tasks']
ROOT_KEYS_AFTER_PARTIAL = ['current', 'design_work_root', 'design_work_roots', 'jira_base', 'jira_email', 'jira_token', 'profile_repos', 'registry',
                           'supabase_key', 'supabase_url', 'tasks']
ROOT_KEYS_AFTER_UNMIGRATED = ['current', 'design_work_root', 'design_work_roots', 'gitlab_host_ip', 'gitlab_ssh_key', 'jira_base', 'jira_email',
                              'jira_token', 'preview_password', 'profile_repos', 'registry', 'supabase_key', 'supabase_url', 'tasks']
ROOT_KEYS_AFTER_PLAIN = list(ROOT_KEYS_AFTER_UNMIGRATED)

STARTUP_REGULAR = [
    'liga-4d3a: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3a',
    'liga-4d3b: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3b',
    'liga-4d3c: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3c',
    'liga-4d4a: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d4a',
    '  напрямки: записано; записи: 1; нотатки: default-root-differs',
    'liga-4d4b: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d4b',
    '  скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password; видалено: gitlab_host_ip, gitlab_ssh_key, jira_base, jira_email, jira_token, '
    'preview_password, supabase_key, supabase_url',
    '  оригінали видалено з tasks.json; копії — secrets.json, backups/ у домі Deai і tasks.json.bak (права 0600)',
    '  відкат: bin/migrate_liga.py restore <stamp>-liga-4d4b --hold',
    '  раніші кроки (<stamp>-liga-4d3a, <stamp>-liga-4d3b, <stamp>-liga-4d3c, <stamp>-liga-4d4a) — лише після відкату пізніших, у зворотному порядку',
]

_HOLD_TAIL = 'skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run'
#: Однаковий постійний пропуск на кількох кроках друкується ОДНИМ рядком «те саме для» (старт 4d-4a, M1) — не п'ятьма окремими.
STARTUP_UNMIGRATED = [
    'liga-4d3a: skip-held — міграцію вимкнено вручну (held у space.json)',
    'liga-4d3b: skip-held — утримано разом із liga-4d3a (ранній крок вимкнено вручну: held у space.json)',
    '  те саме для: liga-4d3c, liga-4d4a, liga-4d4b (skip-held)',
    '  напрямки ЛІГИ не мігровані — нові задачі лягають у теку простору',
    'ролі ЛІГИ вимкнено: publish (vercel-publish) — ' + _HOLD_TAIL,
    'ролі ЛІГИ вимкнено: comments (supabase-comments) — ' + _HOLD_TAIL,
    'ролі ЛІГИ вимкнено: vcs (git-sync) — ' + _HOLD_TAIL,
    'ролі ЛІГИ вимкнено: dashboard (supabase-dashboard) — ' + _HOLD_TAIL,
    'ролі ЛІГИ вимкнено: tracker (jira-tracker) — ' + _HOLD_TAIL,
    'ролі ЛІГИ вимкнено: notify (supabase-teams) — ' + _HOLD_TAIL,
    'preview_password у корені tasks.json Deai не читає, а запис vercel-publish пароля не має — превʼю візьме спільний '
    'пароль за замовчуванням; виправити: python3 bin/migrate_liga.py run (крок утримано (held) — спершу unhold; або задайте секрет password '
    'запису vercel-publish)',
]

#: Підсумок кроку Е (імена ключів і коди, без значень) на мігрованих стендах.
STEP_E_SUMMARY = {
    'regular': 'скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password; видалено: gitlab_host_ip, gitlab_ssh_key, jira_base, jira_email, '
               'jira_token, preview_password, supabase_key, supabase_url',
    'differs': 'скопійовано: gitlab_host_ip, preview_password; видалено: gitlab_host_ip, jira_base, jira_email, preview_password, supabase_key, '
               'supabase_url; лишилось: gitlab_ssh_key, jira_token; '
               'нотатки: differs:jira_token, differs:gitlab_ssh_key, replaced:preview_password',
    'partial': 'скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password; видалено: gitlab_host_ip, gitlab_ssh_key, preview_password; '
               'лишилось: jira_base, jira_email, jira_token, supabase_key, supabase_url; '
               'нотатки: partial:supabase, no-record:supabase-teams, no-record:jira-tracker',
}

EXPECT = {'regular': EXPECT_REGULAR, 'differs': EXPECT_DIFFERS, 'partial': EXPECT_PARTIAL, 'unmigrated': EXPECT_UNMIGRATED, 'plain': EXPECT_PLAIN}
ROOT_AFTER = {'regular': ROOT_KEYS_AFTER_REGULAR, 'differs': ROOT_KEYS_AFTER_DIFFERS, 'partial': ROOT_KEYS_AFTER_PARTIAL,
              'unmigrated': ROOT_KEYS_AFTER_UNMIGRATED, 'plain': ROOT_KEYS_AFTER_PLAIN}


class AfterMigrationParity4d4b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import deai_modules
        import after_4d4b_collect as col
        with open(BEFORE, encoding='utf-8') as f:
            cls.before = json.load(f)['stands']
        deai_modules.reset_caches()
        col.EXTRA.clear()
        cls.after = col.collect_all()
        cls.wire = cls.after.pop('_wire')
        cls.wire_stands = cls.after.pop('_wire_stands')
        cls.summary = cls.after.pop('_step_e_summary')
        deai_modules.reset_caches()

    def _diff(self, name):
        return _diff(self.before[name], self.after[name])

    def test_no_network_and_all_stands_present(self):
        # `SocketTripwire` рахує спроби НЕ-loopback з'єднань, які `NoNet`/розтяжка зупинили (жодна не дійшла до мережі). Точно, а не «не більше»
        # (r15-3): у знімку 10, нині 7 — без `Implicit` і без читання оригіналів. Побільшало чи побіднішало — треба знати, чому.
        self.assertEqual(self.wire, 7)
        self.assertEqual(self.wire_stands, {'regular': 3, 'differs': 3, 'partial': 1, 'unmigrated': 0, 'plain': 0})
        self.assertEqual(sum(self.wire_stands.values()), self.wire)
        self.assertEqual(sorted(self.after), sorted(STANDS))

    def test_snapshot_is_big_enough_to_mean_something(self):
        for name in STANDS:
            self.assertEqual(sorted(self.after[name]), sorted(self.before[name]), name)
            self.assertGreater(len(_flat(self.before[name])), 130 if name == 'plain' else 180, name)

    def test_exact_differences_regular(self):
        self.assertEqual(self._diff('regular'), _expect(self.before['regular'], EXPECT_REGULAR))

    def test_exact_differences_differs(self):
        self.assertEqual(self._diff('differs'), _expect(self.before['differs'], EXPECT_DIFFERS))

    def test_exact_differences_partial(self):
        self.assertEqual(self._diff('partial'), _expect(self.before['partial'], EXPECT_PARTIAL))

    def test_exact_differences_unmigrated(self):
        self.assertEqual(self._diff('unmigrated'), _expect(self.before['unmigrated'], EXPECT_UNMIGRATED))

    def test_exact_differences_plain(self):
        self.assertEqual(self._diff('plain'), _expect(self.before['plain'], EXPECT_PLAIN))

    def test_root_keys_are_literal(self):
        for name in STANDS:
            self.assertEqual(self.after[name]['root_keys'], ROOT_AFTER[name], name)

    def test_startup_lines_are_literal(self):
        self.assertEqual(self.after['regular']['startup_text'], STARTUP_REGULAR)
        self.assertEqual(self.after['unmigrated']['startup_text'], STARTUP_UNMIGRATED)

    def test_step_e_summaries_name_keys_not_values(self):
        """Рядок кроку Е на мігрованих стендах: імена ключів і коди розбіжностей (`differs:*`, `partial:supabase`, `no-record:*`); значень нема."""
        self.assertEqual(self.summary, STEP_E_SUMMARY)
        self.assertIn('replaced:preview_password', self.summary['differs'])             # код `replaced:` — лише ім'я ключа, без старого й нового значень
        for text in self.summary.values():
            for secret in ('pw-alpha', 'inert-old', 'other-token', '/other/key', '203.0.113.7'):
                self.assertNotIn(secret, text)

    def test_expected_diff_is_exact_not_loose(self):
        """Охоронець самого порівняння: зайвий листок і зниклий очікуваний — обидва червоніють на КОЖНОМУ стенді."""
        for name in STANDS:
            exp = _expect(self.before[name], EXPECT[name])
            extra = json.loads(json.dumps(self.after[name]))
            extra['api']['task']['preview_password'] = 'змінено'                         # зайвий листок
            d = _diff(self.before[name], extra)
            self.assertIn('/api/task/preview_password', d)
            self.assertNotEqual(d, exp, name)
            missing = json.loads(json.dumps(self.after[name]))                          # очікувана зміна «не сталась»: листок повернуто до «було»
            missing['provider']['implicit_space']['vcs']['type'] = self.before[name]['provider']['implicit_space']['vcs']['type']
            d = _diff(self.before[name], missing)
            self.assertNotIn('/provider/implicit_space/vcs/type', d)
            self.assertNotEqual(d, exp, name)
            self.assertNotEqual(_diff(self.before[name], self.before[name]), exp, name)  # і «нічого не змінилось»

    def test_what_a_person_sees_regular(self):
        """Звичайна мігрована ЛІГА: у відповідях API нових відмінностей лише три видимі поля на «Підключенні» (ssh_key, host_ip, «Пароль превʼю: задано»);
        `capabilities`, пароль превʼю, канали й ключі коментарів — РІВНО знімок."""
        api = {k for k in self._diff('regular') if k.startswith('/api/')}
        self.assertEqual(api, {'/api/modules/list/git-sync/fields/host_ip', '/api/modules/list/git-sync/fields/ssh_key',
                               '/api/modules/list/vercel-publish/fields/password'})
        a = self.after['regular']['api']
        self.assertEqual(a['task']['preview_password'], 'pw-alpha')
        self.assertEqual(a['task']['capabilities'], self.before['regular']['api']['task']['capabilities'])
        self.assertEqual(a['comment_config']['config']['key'], 'sb_test_key_alpha')

    def test_differing_password_is_replaced_by_the_root(self):
        """Рішення власника 09.11.2026 (замість рішення контролера 07.11): у `differs` секрет `password` був `inert-old`, корінь — `pw-alpha`. Крок Е
        перезаписує секрет коренем: люди бачать той самий пароль, корінь `preview_password` видалено, підсумок називає `replaced:preview_password`
        (значень нема); старе значення лишається в датованому бекапі."""
        self.assertEqual(self.before['differs']['api']['task']['preview_password'], 'pw-alpha')
        self.assertEqual(self.after['differs']['api']['task']['preview_password'], 'pw-alpha')
        self.assertNotIn('preview_password', self.after['differs']['root_keys'])
        self.assertIn('replaced:preview_password', self.summary['differs'])
        self.assertNotIn('differs:preview_password', self.summary['differs'])
        self.assertIn('лишилось: gitlab_ssh_key, jira_token;', self.summary['differs'])

    def test_differing_ssh_key_stays_the_records_and_registry_follows_it(self):
        """`differs`: запис вигравав (`/other/key`), корінь лишився з нотаткою `differs:gitlab_ssh_key`; реєстр тепер іде ключем запису."""
        self.assertEqual(self.after['differs']['vcs_target']['task_gitlab']['effective']['ssh_key'],
                         self.before['differs']['vcs_target']['task_gitlab']['effective']['ssh_key'])
        self.assertEqual(self.after['differs']['registry_ssh'], '/other/key')
        self.assertIn('gitlab_ssh_key', self.after['differs']['root_keys'])
        self.assertIn('differs:gitlab_ssh_key', self.summary['differs'])

    def test_unmigrated_loses_all_six_roles(self):
        """Таблиця «стало вимкнено» буквально: усі шість ролей — `None`, публікація/Teams/коментарі відмовляють, пароль превʼю — типовий 1100."""
        a = self.after['unmigrated']
        roles = ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')
        self.assertEqual({r: a['provider']['in_space'][r]['api'] for r in roles}, {r: None for r in roles})
        self.assertEqual(a['api']['task']['preview_password'], '1100')
        self.assertEqual(a['api']['teams_mute']['status'], 409)
        self.assertEqual(a['api']['teams_mute']['body']['code'], 'notify-off')
        self.assertEqual(a['api']['comment_config']['status'], 409)
        self.assertIsNone(a['vcs_target']['provider'])
        self.assertEqual(a['registry_ssh'], '~/.ssh/gitlab_ed25519')
        self.assertFalse(a['dashboard_sync']['non_isolated']['in_space']['called'])      # дашборд вимкнено — синку нема
        self.assertFalse(a['dashboard_sync']['non_isolated']['implicit_space']['called'])


#: Листки старших паритетів (4d-3b, 4d-3c), які Task 14 свідомо виніс із ТИХ класів (`_is_4d4b_leaf`), бо їх причина — 4d-4b (`Implicit` видалено,
#: оригіналів кореня нема). Тут вони закріплені ТОЧНО: «було» зі знімка старого етапу, «стало» — буквально. Значення виміряно на реальній поведінці
#: (однакові після кроків A–C і A–E: сценарії міняють корінь ПІСЛЯ міграції).
_CH = '/publish/comments_off/pages/html/%s/index.html/%s'
EXPECT_4D3C_LEAVES = dict({
    # capabilities.tracker: у знімку 4d-3c облікових Jira в записі нема → роль вимкнена (було неявний `legacy`)
    '/api_spaces/capabilities/tracker': None,
    # вимкнення `vercel-publish` у просторі з інтеграціями більше не повертає вбудовану публікацію: «немає» (було `[]`/нічого)
    '/js/disable_consequences_publish[0]/kind': 'none',
    '/js/disable_consequences_publish[0]/noneKey': 'cnNonePublish',
    '/js/disable_consequences_publish[0]/role': 'publish',
    '/js/disable_consequences_publish[]': ABSENT,
    # comments_off (імʼя сценарію зі знімка): пару кореня прибрано ПІСЛЯ міграції (записи й далі несуть конфіг); корінь не читається,
    # коментарі ведуть записи → шар коментарів ПРИСУТНІЙ. Вимкнений чи видалений ЗАПИС шару не дає — `test_legacy_comments.LegacyPagesTest`.
    '/publish/comments_off/pages/comment_layer_files': ABSENT,
    '/publish/comments_off/pages/comment_layer_files[0]': 'adapter.js',
    '/publish/comments_off/pages/comment_layer_files[1]': 'comment-layer.min.js',
    '/publish/comments_off/pages/comment_layer_files[2]': 'supabase.min.js',
    '/publish/comments_off/response/pairs[4][0]': 'url',
    '/publish/comments_off/response/pairs[4][1]': 'https://pv-12345678.vercel.app',
    '/publish/comments_off/response/pairs[5][0]': 'deploy_url',
    '/publish/comments_off/response/pairs[6][0]': 'verified',
    '/publish/comments_off/response/pairs[6][1]': True,
    '/publish/comments_off/response/pairs[7][0]': ABSENT,
    '/publish/comments_off/response/pairs[7][1]': ABSENT,
    # pw_root: пароль у корені після міграції не діє (крок Е переносить лише наявний на ту мить; пізніша зміна кореня ігнорується) → типовий 1100
    '/publish/pw_root/pages/html/index.html/password': '1100',
    '/publish/pw_root/pages/html/it1/alpha/index.html/password': '1100',
    '/publish/pw_root/pages/html/it1/gamma/index.html/password': '1100',
    '/publish/pw_root/pages/html/it2/index.html/password': '1100',
}, **{_CH % (p, k): v for p in ('it1/alpha', 'it1/gamma', 'it2') for k, v in
      (('channel', 'dc/a-1'), ('comment_layer', True), ('supabase_key', '<secret:17>'), ('supabase_url', 'https://sb.example.com'))})

#: 4d-3b (`before-4d3b.json`), конфігурації `snapshot` і `shared`: ролі без запису (`publish`, `tracker`) у формі «Нова задача» — `None` (було неявний
#: `legacy`), прапорець `has_publish` хибний; ціль git (дзеркала й тексти) більше НЕ несе `ssh_key` кореня — ключ бере модуль з налаштувань запису.
EXPECT_4D3B_LEAVES = dict({
    '/vcs/form/capabilities/publish': None,
    '/vcs/form/capabilities/tracker': None,
    '/vcs/form/model/has_publish': False,
    '/vcs/form/space_row/capabilities/publish': None,
    '/vcs/form/space_row/capabilities/tracker': None,
    '/vcs/texts/sync/a-1/push[0]/target/ssh_key': 'ABSENT',
    '/vcs/texts/sync/a-2/push[0]/target/ssh_key': 'ABSENT',
}, **{'/vcs/mirrors[%d]/target/ssh_key' % i: 'ABSENT' for i in range(7)})


class OlderParityLeaves4d4b(unittest.TestCase):
    """I3 (Task 14 → Task 15): листки 4d-3b/4d-3c, чия причина — 4d-4b, закріплені точно. Збір — ті самі генератори знімків (`make_before_4d3b/c`) на
    мігрованій ЛІЗІ, що й у старих класах; фільтр — їхній `_is_4d4b_leaf`. ssh_key/host_ip цілей git: у цьому класі (`/target/ssh_key` дзеркал і
    текстів — ABSENT) і в `AfterMigrationParity4d4b` (листки `vcs_target.*`: ціль без ключа/IP, ефективні значення рівні знімку)."""

    @classmethod
    def setUpClass(cls):
        from unittest import mock
        import liga_migrate as lm
        import make_before_4d3b as gb
        import make_before_4d3c as gc
        import test_liga_migrate_b as tb
        import test_liga_migrate_c as tc
        cls.tb, cls.tc = tb, tc
        # 4d-3c: ті самі два стенди, що в `AfterMigrationParity4d3c`, але ПОВНИЙ ланцюг A–E.
        with open(tc.BEFORE, encoding='utf-8') as f:
            cls.before_c = json.load(f)
        orig = gc._stand

        def migrated(tmp, name, migrate):
            rig = orig(tmp, name, migrate=False)
            with rig.activate():
                with mock.patch.object(lm, 'STEPS', lm.ALL_STEPS[:2 if name == 'ab' else 3]):
                    lm.run_all()
                if name == 'ab':
                    lm.run(step='liga-4d3c')
                for s in lm.ALL_STEPS[3:]:
                    lm.run(step=s)
            return rig
        with mock.patch.object(gc, '_stand', migrated):
            cls.after_c = gc.make()
        # 4d-3b: колектор старого класу (його `_build`), конфігурація `snapshot` і `shared`.
        class Holder:
            pass
        Holder.mock, Holder.g, Holder.lm = mock, gb, lm
        with open(tb.BEFORE, encoding='utf-8') as f:
            cls.before_b = json.load(f)
        cls.after_b = {n: tb.AfterMigrationParity4d3b._build.__func__(Holder, n)[0] for n in ('snapshot', 'shared')}

    @staticmethod
    def _leaves(flat_fn, absent, before, after, pred):
        fb, fa = flat_fn(before), flat_fn(after)
        return {k: (fb.get(k, absent), fa.get(k, absent)) for k in sorted(set(fb) | set(fa)) if fb.get(k, absent) != fa.get(k, absent) and pred(k)}

    @staticmethod
    def _want(flat_fn, absent, before, table):
        fb = flat_fn(before)
        lit = {k: (absent if v in ('ABSENT', ABSENT) else v) for k, v in table.items()}
        return {k: (fb.get(k, absent), v) for k, v in lit.items()}

    def test_4d3c_leaves_are_pinned_exactly_on_both_stands(self):
        tc = self.tc
        for name in ('unmigrated', 'ab'):
            got = self._leaves(tc._flat, tc._ABSENT, self.before_c['stands'][name], self.after_c['stands'][name], tc._is_4d4b_leaf)
            want = self._want(tc._flat, tc._ABSENT, self.before_c['stands'][name], EXPECT_4D3C_LEAVES)
            self.assertEqual(got, want, name)

    def test_4d3b_leaves_are_pinned_exactly_on_both_configs(self):
        tb = self.tb
        for name in ('snapshot', 'shared'):
            got = self._leaves(tb._flat, tb._ABSENT, self.before_b, self.after_b[name], tb._is_4d4b_leaf)
            want = self._want(tb._flat, tb._ABSENT, self.before_b, EXPECT_4D3B_LEAVES)
            self.assertEqual(got, want, name)

    def test_the_pin_is_exact_not_loose(self):
        """Зайвий і зниклий листок червоніють: зміна одного очікуваного значення дає інший результат порівняння."""
        tb = self.tb
        got = self._leaves(tb._flat, tb._ABSENT, self.before_b, self.after_b['snapshot'], tb._is_4d4b_leaf)
        bad = dict(EXPECT_4D3B_LEAVES, **{'/vcs/form/model/has_publish': True})
        self.assertNotEqual(got, self._want(tb._flat, tb._ABSENT, self.before_b, bad))
        short = {k: v for k, v in EXPECT_4D3B_LEAVES.items() if k != '/vcs/form/capabilities/tracker'}
        self.assertNotEqual(got, self._want(tb._flat, tb._ABSENT, self.before_b, short))


if __name__ == '__main__':
    unittest.main()

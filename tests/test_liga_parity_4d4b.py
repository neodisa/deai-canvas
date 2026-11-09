"""Паритет після міграції `AfterMigrationParity4d4b` (етап 4d-4b): ті самі сценарії, що знімок 0.20.0 (`fixtures/liga-migration/before-4d4b.json`), на
МІГРОВАНІЙ ЛІЗІ п'ятьма кроками, НЕізольовано (шлях власника: `DEAI_HOME` + реєстр, без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`; живі тести ізольовані і
цього не доводять). Збір — `after_4d4b_collect.collect_all` (ті самі розділи, що в генераторі знімка, нові підписи функцій; на стендах `differs`/`partial` запис
міняється ПЕРЕД кроком Е, бо Е ці розбіжності й оцінює). Очікуваний перелік відмінностей — ТОЧНИЙ: кожен листок із «було» зі знімка і «стало» буквально.
Таблиці виміряні на реальній поведінці; кожен листок — або задуманий наслідок 4d-4b (`Implicit` видалено, оригінали не читаються), або зафіксована
відмінність (пароль превʼю `differs`: рішення контролера — відмінний секрет НЕ перезаписується). Мережі нема (`SocketTripwire` + `NoNet`), справжній
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

#: `differs`: ключ SSH запису (`/other/key`) і секрет `password` (`inert-old`) НЕ перезаписуються коренем (рішення контролера замість Д4). Режим модуля
#: тепер бере секрет запису, а не корінь → пароль превʼю стає `inert-old` (єдиний листок понад прототип Додатка Д).
EXPECT_DIFFERS = dict({
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/api/task/preview_password': 'inert-old',
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
ROOT_KEYS_AFTER_DIFFERS = ['current', 'design_work_root', 'design_work_roots', 'gitlab_ssh_key', 'jira_token', 'preview_password', 'profile_repos',
                           'registry', 'tasks']
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
    '  оригінали видалено з tasks.json; єдина копія — secrets.json і backups/ у домі Deai',
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
]

#: Підсумок кроку Е (імена ключів і коди, без значень) на мігрованих стендах.
STEP_E_SUMMARY = {
    'regular': 'скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password; видалено: gitlab_host_ip, gitlab_ssh_key, jira_base, jira_email, '
               'jira_token, preview_password, supabase_key, supabase_url',
    'differs': 'скопійовано: gitlab_host_ip; видалено: gitlab_host_ip, jira_base, jira_email, supabase_key, supabase_url; '
               'лишилось: gitlab_ssh_key, jira_token, preview_password; '
               'нотатки: differs:jira_token, differs:gitlab_ssh_key, differs:preview_password',
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
        cls.summary = cls.after.pop('_step_e_summary')
        deai_modules.reset_caches()

    def _diff(self, name):
        return _diff(self.before[name], self.after[name])

    def test_no_network_and_all_stands_present(self):
        # `SocketTripwire` рахує спроби НЕ-loopback з'єднань, які `NoNet`/розтяжка зупинили (жодна не дійшла до мережі); у знімку їх 10 — без `Implicit`
        # і без читання оригіналів спроб не побільшало.
        with open(BEFORE, encoding='utf-8') as f:
            self.assertLessEqual(self.wire, json.load(f)['non_loopback_attempts'])
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

    def test_differing_password_is_never_overwritten_by_the_root(self):
        """Рішення контролера (замість Д4): у `differs` секрет `password` був `inert-old`, корінь — `pw-alpha`. Крок Е НЕ перезаписує секрет коренем:
        корінь лишає `preview_password`, підсумок називає `differs:preview_password`, а режим модуля віддає секрет запису (єдина видима зміна)."""
        self.assertEqual(self.before['differs']['api']['task']['preview_password'], 'pw-alpha')
        self.assertEqual(self.after['differs']['api']['task']['preview_password'], 'inert-old')
        self.assertIn('preview_password', self.after['differs']['root_keys'])
        self.assertIn('differs:preview_password', self.summary['differs'])
        self.assertIn('лишилось: gitlab_ssh_key, jira_token, preview_password', self.summary['differs'])

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


if __name__ == '__main__':
    unittest.main()

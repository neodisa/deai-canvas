"""Явна фікстура простору ЛІГА (4d-4b): ролі ЛІГИ — це ЯВНІ записи `space.json` + секрети в тимчасовому `DEAI_HOME`, а не облікові в корені
`tasks.json` чи в оточенні (рантайм їх більше не читає). Два способи, що дають однаковий результат:

* `LigaFixture.build()` — прямі записи (швидко, для тестів ролей); `LigaFixture.migrate()` — НАСПРАВДІ запускає `liga_migrate.run_all` на
  старому корені з вісьмома оригіналами («як у людини»): рантайм-тести, що мають перевіряти шлях міграції, беруть його.
* Лише ТИМЧАСОВІ теки: жодного шляху в справжній дім. Значення — вигадані (`https://sb.example.com`, `team_x`, `alpha@example.com`).

Використання: `fx = LigaFixture(self); fx.build(); …` — у `setUp` тесту, що вже підмінив `HOME`/`DEAI_HOME` (`fx.env()` робить це сам,
якщо тест цього не зробив).
"""
import json
import os
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))

SB_URL, SB_KEY = 'https://sb.example.com', 'sb_fixture_key_alpha'
JIRA_BASE, JIRA_EMAIL, JIRA_TOKEN = 'https://jira.example.com', 'alpha@example.com', 'jira_fixture_token_alpha'
SSH_KEY, HOST_IP, PASSWORD = '~/.ssh/id_example', '203.0.113.7', 'pw-fixture'
#: Шість ролей → (модуль, налаштування, секрети). Форма — та сама, що пишуть кроки A–C (`liga_migrate._entries_*`).
ROLE_RECORDS = {
    'dashboard': ('supabase-dashboard', {'url': SB_URL, 'table': 'overview_projects', 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'notify': ('supabase-teams', {'url': SB_URL, 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'comments': ('supabase-comments', {'url': SB_URL, 'shots_bucket': 'overview-thumbs', 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'tracker': ('jira-tracker', {'base': JIRA_BASE, 'email': JIRA_EMAIL}, {'token': JIRA_TOKEN}),
    'vcs': ('git-sync', {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas',
                         'ssh_key': SSH_KEY, 'host_ip': HOST_IP}, {}),
    'publish': ('vercel-publish', {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}, {'password': PASSWORD}),
}
ALL_ROLES = tuple(ROLE_RECORDS)
#: Явний запис публікації «у теку» (4d-4c: неявного типового нема) — для простору, зібраного руками, а не `create_space`.
PLAIN_PUBLISH = {'static-publish': {'enabled': True}}


def write_records(space_dir, deai_dir, sid='legacy', roles=ALL_ROLES, overrides=None, name='Liga'):
    """Явні записи `roles` у `space.json` теки `space_dir` і їхні секрети в `secrets.json` дому `deai_dir` (бакет `sid`). Для стендів, що самі
    створюють реєстр і простір (`spaces.create_space`), а `LigaFixture` їм зайвий; `LigaFixture.build` викликає її ж. Існуючі `space.json`/
    `secrets.json` ПЕРЕПИСУЮТЬСЯ (стенд кладе записи до того, як щось у них пише). Повертає `{модуль: запис}`."""
    mods, sec = {}, {}
    for role in roles:
        mid, settings, secrets = ROLE_RECORDS[role]
        o = (overrides or {}).get(role, {})
        mods[mid] = {'enabled': o.get('enabled', True), 'shared_state': True, 'settings': dict(settings, **o.get('settings', {}))}
        s = dict(secrets, **o.get('secrets', {}))
        if s:
            sec[mid] = s
    os.makedirs(space_dir, exist_ok=True)
    with open(os.path.join(space_dir, 'space.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'modules': mods, 'migrations': {}}, f)
    os.makedirs(deai_dir, exist_ok=True)
    secrets_path = os.path.join(deai_dir, 'secrets.json')
    with open(secrets_path, 'w', encoding='utf-8') as f:
        json.dump({sid: sec}, f)
    os.chmod(secrets_path, 0o600)
    return mods


class LigaFixture:
    """Тимчасовий `HOME`/`DEAI_HOME` + реєстр із простором ЛІГА (`legacy: true`, `integrations: true`) + `space.json` + `secrets.json`."""

    def __init__(self, test, tmp=None):
        self.test = test
        if tmp is None:
            d = tempfile.TemporaryDirectory(prefix='liga-fx-')
            test.addCleanup(d.cleanup)
            tmp = d.name
        self.tmp = os.path.realpath(tmp)
        self.home = os.path.join(self.tmp, 'home')
        self.deai = os.path.join(self.home, '.deai')
        self.space_dir = os.path.join(self.tmp, 'liga-space')
        self.tasks_path = os.path.join(self.tmp, 'legacy-tasks.json')
        for d in (self.home, self.deai, self.space_dir):
            os.makedirs(d, exist_ok=True)

    # --- оточення
    def env(self, **extra):
        """`HOME`/`DEAI_HOME` у тимчасовій теці, без жодних облікових оточення; `spaces.legacy_tasks_file` → `self.tasks_path`."""
        import deai_modules
        import spaces
        e = mock.patch.dict(os.environ, dict({'HOME': self.home, 'DEAI_HOME': self.deai}, **extra))
        e.start()
        self.test.addCleanup(e.stop)
        for name in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
                     'SUPABASE_SERVICE_KEY', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DEAI_EXTRA_MODULES'):
            if name not in extra:
                os.environ.pop(name, None)
        lf = mock.patch.object(spaces, 'legacy_tasks_file', lambda: self.tasks_path)
        lf.start()
        self.test.addCleanup(lf.stop)
        deai_modules.reset_caches()
        self.test.addCleanup(deai_modules.reset_caches)
        return self

    def fix_space(self):
        """Зафіксувати простір ЛІГА простором запиту ПОТОЧНОГО потоку (як це робить обробник запиту): без цього `spaces.effective_space()` віддає неявний
        простір (шар «не зафіксовано»), а не запис реєстру, і явні записи ролей не діють. Прибирається в `addCleanup`."""
        import spaces
        spaces.set_request_space('legacy')
        self.test.addCleanup(spaces.clear_request_space)
        return self

    def _write(self, path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))

    def registry(self, integrations=True):
        self._write(os.path.join(self.deai, 'spaces.json'),
                    {'version': 1, 'current': 'legacy', 'spaces': [{'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': integrations}]})

    # --- спосіб (а): прямі записи
    def key_file(self):
        """Справжній файл ключа SSH у тимчасовому `HOME` за шляхом, що веде `SSH_KEY` (`~/.ssh/id_example`): без нього `git-sync` із типовим
        записом дає `vcs-bad-target` («not an existing file»), і «ключ записи ЛІГИ резолвиться» ніхто б не довів. Вміст — не ключ (вигаданий
        рядок): модуль перевіряє лише наявність файла. Повертає абсолютний шлях."""
        path = os.path.join(self.home, '.ssh', 'id_example')
        self._write(path, 'not a real key\n')
        os.chmod(path, 0o600)
        return path

    def build(self, roles=ALL_ROLES, overrides=None, tasks=None, root_extra=None, key_file=False):
        """Явні записи `roles` (рівні тим, що пишуть кроки A–C) + `secrets.json`; корінь `tasks.json` БЕЗ облікових (лише `tasks`/маркер `registry`).
        `overrides[роль] = {'enabled': False, 'settings': {…}, 'secrets': {…}}` — заміна окремих частин запису. `key_file=True` — ще й справжній
        файл ключа за шляхом запису `git-sync` (`key_file()`); типово ні: поведінка наявних стендів не змінюється."""
        if key_file:
            self.key_file()
        self.registry()
        write_records(self.space_dir, self.deai, 'legacy', roles, overrides)
        root =dict({'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'tasks': tasks or {}}, **(root_extra or {}))
        self._write(self.tasks_path, root)
        import deai_modules
        deai_modules.reset_caches()
        return self

    # --- спосіб (б): справжня міграція зі старого кореня
    def legacy_root(self, **over):
        """Старий корінь із вісьмома оригіналами (`over` — заміна/додавання; `None` — прибрати ключ) і `registry`-маркером."""
        cfg = {'supabase_url': SB_URL, 'supabase_key': SB_KEY, 'jira_base': JIRA_BASE, 'jira_email': JIRA_EMAIL, 'jira_token': JIRA_TOKEN,
               'gitlab_ssh_key': SSH_KEY, 'gitlab_host_ip': HOST_IP, 'preview_password': PASSWORD,
               'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'tasks': {}}
        for k, v in over.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        self._write(self.tasks_path, cfg)
        return cfg

    def migrate(self, **over):
        """Старий корінь → `liga_migrate.run_all()` на всіх п'яти кроках. Повертає `[(позначка, статус, підсумок)]`. Потрібен `jira_email`/`jira_token`
        в ОТОЧЕННІ міграції (A читає їх із `JIRA_*`): виставляємо на час прогону й прибираємо."""
        import liga_migrate
        self.registry()
        self._write(os.path.join(self.space_dir, 'space.json'), {'name': 'Liga'})
        cfg = self.legacy_root(**over)
        env = {} if cfg.get('jira_email') is None else {'JIRA_EMAIL': cfg['jira_email'], 'JIRA_TOKEN': cfg.get('jira_token') or ''}
        with mock.patch.dict(os.environ, env), mock.patch.object(liga_migrate, 'STEPS', liga_migrate.ALL_STEPS):
            return liga_migrate.run_all()

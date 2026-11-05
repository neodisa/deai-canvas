"""Неявний постачальник ролі (4d-2): простір з інтеграціями без явного модуля (ЛІГА) чи вимкнений шар. Без мережі, без serve."""
import os


class Implicit:
    __slots__ = ('role', 'module_id', 'shared', 'fake_env')

    def __init__(self, role, module_id, shared, fake_env):
        for k, v in (('role', role), ('module_id', module_id), ('shared', shared), ('fake_env', fake_env)):
            object.__setattr__(self, k, v)

    def __setattr__(self, k, v):
        raise AttributeError('Implicit is immutable')

    def __repr__(self):
        return f'Implicit({self.role!r})'

    # ⛔ МІСТ 4d-2 Task 3→5: прибирається в Task 6 разом з охоронцем літерала. Поки `serve.py` і `bin/` порівнюють постачальника
    # з `'legacy'` (вони переходять на `isinstance` у Task 4), `Implicit` дорівнює цьому рядку — інакше їхні гілки мовчки зламались би.
    def __eq__(self, other):
        return other == 'legacy' or other is self

    def __hash__(self):
        return hash('legacy')       # ⛔ МІСТ 4d-2 Task 3→5: узгоджено з `__eq__`; прибирається в Task 6


#: Ролі із зашитим шляхом ЛІГИ (колишні `LEGACY_ROLES`; склад і порядок ті самі).
IMPLICIT_ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
_TABLE = {
    'publish':   Implicit('publish',   'vercel-publish',     True, None),
    'comments':  Implicit('comments',  'supabase-comments',  True, None),
    'vcs':       Implicit('vcs',       'git-sync',           True, None),
    'dashboard': Implicit('dashboard', 'supabase-dashboard', True, 'DC_TEAM_FAKE'),
    'tracker':   Implicit('tracker',   'jira-tracker',       True, 'DC_TRACKER_FAKE'),
    'notify':    Implicit('notify',    'supabase-teams',     True, 'DC_TEAMS_FAKE'),
}


def for_role(role):
    return _TABLE[role]


def isolated():
    """⛔ Закон ізоляції: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` — «стан не справжній цієї машини»; зі спільного стану ЛІГИ не ходимо."""
    return bool(os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'))


def route(p):
    """Куди йти неявному постачальнику: `('fake', шлях)` → `('isolated', None)` → `('live', None)`. Порядок однаковий для всіх
    ролей; що повертати в кожному випадку, вирішує роль (форми відповідей 0.15.0 різні: див. знімок `isolation`)."""
    fake = os.environ.get(p.fake_env) if p.fake_env else None
    if fake:
        return 'fake', fake
    if p.shared and isolated():
        return 'isolated', None
    return 'live', None

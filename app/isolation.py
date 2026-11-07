"""Закон ізоляції й шви тестів (4d-4b; раніше жив у `app/implicit.py`, який зник разом із запасним постачальником).

Чистий модуль: імпортує лише `os` (і `pwd` у `real_home`) — без `spaces`/`serve`/`deai_modules`, тож цикл імпорту неможливий (як було в `implicit.py`).

* `isolated()` — «стан не справжній цієї машини»: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`. Зі спільного стану ЛІГИ (Supabase, Jira, Teams) ізольований
  прогін не ходить ніколи; чи є шов — вирішує `route()`.
* `route(role)` — куди йти запису `shared_state`: `('fake', шлях)` → `('isolated', None)` → `('live', None)`. Порядок однаковий для всіх ролей; що
  повертати в кожному випадку, вирішує роль (форми відповідей 0.15.0 різні).
* `real_home(home)` — чи `home` — справжній `~/.deai` машини (за `pwd`, а не за `$HOME`: тест підміняє `HOME`, але не підміняє пароль ОС).
  ⛔ Суворіша за `liga_migrate._real_home`: для закону ізоляції «справжній» — лише `pwd`-дім; `<HOME>/.deai` тесту — НЕ справжній.
"""
import os

#: Шви тестів: роль → змінна оточення з шляхом до локального JSON замість живої бази. Лише для ролей, що ходять у спільний стан.
FAKE_ENV = {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'}


def isolated():
    """⛔ Закон ізоляції: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` — «стан не справжній цієї машини»; зі спільного стану ЛІГИ не ходимо."""
    return bool(os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'))


def route(role):
    """`('fake', шлях)` → `('isolated', None)` → `('live', None)` для запису `shared_state` ролі `role`. Шов (`FAKE_ENV[role]`) раніше за
    ізоляцію; роль без шва (`comments`, `vcs`, `publish`) — лише ізольовано чи живо."""
    env = FAKE_ENV.get(role)
    fake = os.environ.get(env) if env else None
    if fake:
        return 'fake', fake
    if isolated():
        return 'isolated', None
    return 'live', None


def real_home(home):
    """Чи `home` (шлях до `DEAI_HOME`) — справжній `~/.deai` машини: `<дім з пароля ОС>/.deai`. Порівняння — `realpath`, а коли він не
    збігся, ще й `os.path.samefile` (на macOS `realpath` не є перевіркою тотожності: регістр `~/.Deai` на нечутливій ФС і firmlink
    `/System/Volumes/Data/…` дають `samefile == True` при різних `realpath`; без цього Д6 відкривалася б). `samefile` кидає `OSError` (теки
    нема) — лишаємо результат `realpath`. Без `pwd` (Windows) дім ОС — `USERPROFILE` (НЕ `HOME`: його підміняє тест); не вдалось
    дізнатись дім ОС — вважаємо справжнім (безпечніший бік: облікових із цієї теки не беремо)."""
    try:
        try:
            import pwd
            base = pwd.getpwuid(os.getuid()).pw_dir
        except ImportError:
            base = os.environ.get('USERPROFILE')
            if not base:
                return True
        real = os.path.join(base, '.deai')
    except (KeyError, OSError):
        return True
    try:
        mine = os.path.expanduser(home)
        if os.path.realpath(mine) == os.path.realpath(real):
            return True
        try:
            return os.path.samefile(mine, real)
        except OSError:
            return False
    except (OSError, ValueError, TypeError):
        return True

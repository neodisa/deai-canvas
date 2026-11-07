#!/usr/bin/env python3
"""design-canvas · пуш статусу проєктів у командний дашборд: тонкий CLI над `app/dashboard.py` (етап 4c-1).

    overview_push.py sync [--space ID]   один прохід синку карток простору (без --space — простір ЛІГА, як кличе планувальник)
    overview_push.py discover            лише базові картки з реєстру задач (ЛІГА)

Збирання карток і сам прохід — у `app/dashboard.py`; запис у сховище робить МОДУЛЬ ролі `dashboard` простору
(`deai_modules.provider('dashboard', простір)`: вбудований `supabase-dashboard` чи свій модуль; без явного запису — «постачальника нема», запасного нема).
Статуси задач дає постачальник ролі `tracker` того самого простору (`_statuses`: вбудований `jira-tracker` чи свій модуль;
Jira-коду тут більше нема, етап 4c-2). Лишився один крок, що ще не став
роллю й передається в синк колбеком: реєстр GitLab (до 4d).
⛔ Скрипт НЕ імпортує сервер: його кличуть і фоном із сервера, і зовнішній планувальник, і серверу тут нічого не належить.
"""
import argparse, json, os, sys

# app/ (сусідня тека) на шляху імпорту — для чистих моделей (pages_model тощо)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

# task_state() і iter_count() переїхали в app/task_state.py — спільні із serve.py
# (екран «Задачі»). task_state кличе синк нижче; iter_count тут лише РЕЕКСПОРТ
# (тести беруть ov.iter_count), звідси F401
from task_state import iter_count, task_state  # noqa: F401

# Збирання карток переїхало в `app/dashboard.py` (етап 4c-1) без зміни поведінки; старі імена лишаються тут реекспортом —
# на них спираються `bin/test_overview_push.py` і знімок `tests/make_before_4c1.py` (підміняють їх на самому пушері).
from dashboard import (_PII, _GL_SSH, _GL_BRANCH, gitlab_web, to_iso, map_status, preview_source,  # noqa: F401
                       comment_project_key, _identity, _humanize)
from dashboard import build_card as build_row, card_has_pii as row_has_pii, discover_card as discover_row  # noqa: F401
import dashboard
import deai_modules
import install_config
import spaces
import tracker

# ---------- sync CLI: файл задач простору → картки → `push` модуля ролі `dashboard` ----------
# ⛔ Клієнта Supabase (`_supabase`, `upsert_project`, `open_comment_counts`) тут більше нема: запис і читання лічильників
# робить модуль (`supabase-dashboard`), конфіг — з УСТАНОВКИ (`install_config.supabase_config()`: файл раніше за оточення — як
# у сервера; відоме обмеження 0.10.0, коли пушер читав оточення першим, закрито). Урок, що зник разом із `_supabase`: окремий
# `overview_push.py sync` із чужим `SUPABASE_URL`/`SUPABASE_KEY` в оточенні писав ТУДИ; тепер оточення — лише запасний шлях.

def load_tasks_file(path=None):
    """Файл задач (`{'tasks': {…}}`). Без `path` — старий файл ЛІГИ (`install_config.legacy_tasks_path`: той самий `DC_TASKS_FILE`,
    що в сервера; пушер і сервер читали б РІЗНІ файли — сервер підмінений тестовий, пушер живий — і синк знову розʼїхався б із тим,
    що бачить дизайнер). Оточення читається на кожен виклик, не кешується."""
    with open(path or install_config.legacy_tasks_path(), encoding="utf-8") as f:
        return json.load(f)

# ---------- Discovery: реєстр задач (design-office, гілка registry) ----------
# Реєстр — ЄДИНЕ джерело істини по задачах усіх напрямків (united / liga360 / seo).
# Раніше тут сканувалась тека mockup/* ОДНОГО репо, тому напрямки в оверв'ю не
# розрізнялися і бачився тільки перший репозиторій.

def _registry():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import registry  # noqa
    return registry

def discover_projects(cfg):
    """{id: запис} із реєстру. {} при будь-якій помилці (нема VPN/доступу) — не падаємо."""
    try:
        reg = _registry()
        return reg.read_registry(reg.ensure_clone(cfg))
    except Exception:  # noqa: BLE001
        return {}


#: Коди виходу: 0 — проход відбувся (збій окремих карток — у лозі, не в коді: як було); 1 — не вдалось почати (нема файла
#: задач, постачальник відмовив, не налаштовано Supabase); 2 — невірне використання (невідомий простір, `discover` не для ЛІГИ).
EXIT_FAIL, EXIT_USAGE = 1, 2


class CliError(Exception):
    """Причина, з якою CLI не може почати: `code` — код виходу, `args[0]` — текст у лог."""
    def __init__(self, text, code=EXIT_FAIL):
        super().__init__(text)
        self.code = code


def _space(space_id):
    """Запис простору з реєстру: за `--space ID`; без нього (чи з `--legacy`) — простір ЛІГА (запис із `legacy`: так кличе
    зовнішній планувальник). ⛔ Жодного псевдоніма-id: `legacy` — припустимий id справжнього простору («Legacy»), тож `--space
    legacy` означає саме той простір, а ЛІГА — окремий прапорець `--legacy`. Невідомий — `CliError` (код 2)."""
    try:
        reg = spaces.load_registry()
    except spaces.SpacesError as e:
        raise CliError("⛔ overview: реєстр просторів не читається (%s)" % e.code)
    found = None
    for sp in reg["spaces"]:
        if space_id is None and sp.get("legacy"):
            found = sp
            break
        if space_id is not None and sp["id"] == space_id:
            found = sp
            break
    if found is None:
        raise CliError("⛔ overview: невідомий простір «%s»" % space_id if space_id is not None
                       else "⛔ overview: простору ЛІГА (legacy) у реєстрі нема", EXIT_USAGE)
    return found


def _target(sp):
    """`(module, ctx, legacy)` постачальника ролі `dashboard` простору `sp`; `(None, None, False)` — постачальника нема (запасного нема:
    без явного ввімкненого запису `supabase-dashboard` синкати нікуди). `ctx` — `module_ctx` запису. ⛔ `legacy` («це простір ЛІГА: є
    крок реєстру GitLab») — запис реєстру `legacy is True` (дашборд ЛІГИ — `Module` із `shared_state`)."""
    try:
        prov = deai_modules.provider("dashboard", sp)
        if prov is None:
            return None, None, False
        return prov, deai_modules.module_ctx(sp, prov), sp.get("legacy") is True
    except deai_modules.ModuleError as e:
        raise CliError("⛔ overview: %s" % (e.message or e.code))
    except spaces.SpacesError as e:
        raise CliError("⛔ overview: реєстр просторів не читається (%s)" % e.code)


def _tasks_of(sp):
    try:
        return load_tasks_file(spaces.tasks_file(sp))
    except (OSError, ValueError) as e:
        raise CliError("⛔ overview: файл задач простору «%s» не читається (%s)" % (sp["id"], type(e).__name__))


def _statuses(sp, log=print):
    """Колбек статусів для `dashboard.sync` від постачальника ролі `tracker` простору `sp` або `None` (кроку нема).
    Модуль простору (явний запис `jira-tracker`, ЛІГА теж) — з його `module_ctx`; не налаштовано (`tracker-unconfigured`) —
    `None` БЕЗ мережі. Нема постачальника — `None`. Збій вирішення ролі (нечитаний `space.json`, модуль не завантажився) — теж `None`,
    але рядком у `log`: синк іде далі без статусів, а причина не мовчить. Колбек питає трекер пакетами з бюджетами синку
    (`tracker.SYNC_TIMEOUT`/`SYNC_SOCKET_S`); його збій обробляє сам `dashboard.sync` (рядок у лог, наявні статуси не затираються).
    Хто постачальник — вирішує `provider` (прапорця ЛІГИ від дашборда тут нема). ⛔ Нічого тут не валить синк: старий Jira-крок (0.12.0) не кидав ніколи, тож і непередбачений
    збій вирішення ролі — лише `None` і назва класу в логу."""
    try:
        prov = deai_modules.provider("tracker", sp)
        if prov is None:
            return None
        module, ctx = prov, deai_modules.module_ctx(sp, prov)
    except deai_modules.ModuleError as e:
        if e.code == "tracker-unconfigured":        # запис без адреси/облікових — не збій, а «трекера нема»
            return None
        log("⚠ overview: статуси трекера недоступні: %s" % (e.message or e.code)[:200])
        return None
    except spaces.SpacesError as e:
        log("⚠ overview: статуси трекера недоступні: реєстр просторів не читається (%s)" % e.code)
        return None
    except Exception as e:  # noqa: BLE001 — крок статусів не валить синк (як 0.12.0): лише назва класу, `str(e)` не чищений
        log("⚠ overview: статуси трекера недоступні: %s" % type(e).__name__)
        return None
    return lambda keys: tracker.statuses(module, ctx, keys, timeout=tracker.SYNC_TIMEOUT, socket_s=tracker.SYNC_SOCKET_S)


def _channel_of(sp, log=print):
    """Колбек `channel_of(task, tid)` для `dashboard.sync` від постачальника ролі `comments` простору `sp`: канал рахує
    `deai_modules.comment_channel_of` (явний `supabase-comments` із `compat: "comment-layer"` — схема comment-layer, без — канал
    простору). Збій рішення про постачальника (реєстр, `space.json`, модуль) чи непридатний id задачі — схема comment-layer, як
    у 0.17.0; причина — рядком у `log` (один раз), синк іде далі."""
    try:
        prov = deai_modules.provider("comments", sp)
    except (deai_modules.ModuleError, spaces.SpacesError) as e:
        log("⚠ overview: постачальника коментарів не визначено (%s): ключ лічильника — схема comment-layer" % (getattr(e, "code", None) or type(e).__name__))
        prov = None

    # Рішення про схему — ОДИН раз тут (читає `space.json`), а не на кожну задачу проходу синку.
    legacy = deai_modules.comment_scheme_legacy(sp, prov) if prov is not None else True

    def channel_of(task, tid):
        if prov is not None:
            try:
                return deai_modules.comment_channel_of(sp, prov, task, tid, legacy=legacy)
            except deai_modules.ModuleError:
                pass
        return deai_modules.legacy_comment_channel(task, tid)
    return channel_of


def cmd_sync(space_id=None, *, call=None, log=print):
    sp = _space(space_id)
    module, ctx, legacy = _target(sp)
    if module is None:
        log("·  overview: у просторі «%s» нема постачальника командного дашборда — нічого синхронізувати" % sp["id"])
        return
    cfg = _tasks_of(sp)
    # Реєстр GitLab — крок ЛІГИ (колбек): звичайний простір його не має. Статуси трекера — від постачальника ролі `tracker`
    # будь-якого простору (нема постачальника чи конфігу — `None`, крок пропущено).
    dashboard.sync(cfg, module, ctx, discover=(lambda: discover_projects(cfg)) if legacy else None,
                   statuses=_statuses(sp, log), channel_of=_channel_of(sp, log), log=log, call=call)


def cmd_discover(space_id=None, *, call=None, log=print):
    """Лише базові картки з реєстру (ігнорує наявні рядки). Лише для ЛІГИ: реєстр GitLab — її крок."""
    sp = _space(space_id)
    module, ctx, legacy = _target(sp)
    if not legacy:
        raise CliError("⛔ overview: discover — лише для простору ЛІГА (реєстр задач GitLab)", EXIT_USAGE)
    cfg = _tasks_of(sp)
    reg, ok, failed = dashboard.push_registry(module, ctx, discover_projects(cfg), "/discover", log=log, call=call)
    for pid, why in failed.items():
        log("⚠ overview/discover: «%s»: %s" % (pid, why))
    log("✅ overview/discover: у реєстрі %d, оброблено %d (нові додано)" % (len(reg), ok))
    return list(reg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="overview_push.py", description="пуш карток задач у командний дашборд")
    sub = ap.add_subparsers(dest="cmd")
    p_sync = sub.add_parser("sync", help="один прохід синку карток простору")
    grp = p_sync.add_mutually_exclusive_group()
    grp.add_argument("--space", metavar="ID", help="id простору; без нього — простір ЛІГА")
    grp.add_argument("--legacy", action="store_true", help="простір ЛІГА (запис реєстру з legacy; те саме, що без --space)")
    sub.add_parser("discover", help="лише базові картки з реєстру задач (ЛІГА)")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)   # argparse сам виходить із кодом 2 на хибному використанні
    try:
        if args.cmd == "discover":
            cmd_discover()
        else:                       # без підкоманди — sync простору ЛІГА (як кликав зовнішній планувальник)
            cmd_sync(getattr(args, "space", None))
    except CliError as e:
        print(e.args[0])
        return e.code
    return 0

if __name__ == "__main__":
    sys.exit(main())

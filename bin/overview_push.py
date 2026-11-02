#!/usr/bin/env python3
"""design-canvas · пуш статусу проєктів у командний дашборд: тонкий CLI над `app/dashboard.py` (етап 4c-1).

    overview_push.py sync [--space ID]   один прохід синку карток простору (без --space — простір ЛІГА, як кличе планувальник)
    overview_push.py discover            лише базові картки з реєстру задач (ЛІГА)

Збирання карток і сам прохід — у `app/dashboard.py`; запис у сховище робить МОДУЛЬ ролі `dashboard` простору
(`deai_modules.provider('dashboard', простір)`: вбудований `supabase-dashboard`, свій модуль чи `'legacy'` для ЛІГИ з конфігом
установки). Тут лишились кроки, що ще не стали ролями й передаються в синк колбеками: реєстр GitLab і статуси Jira (до 4c-2/4d).
⛔ Скрипт НЕ імпортує сервер: його кличуть і фоном із сервера, і зовнішній планувальник, і серверу тут нічого не належить.
"""
import argparse, base64, json, os, sys
import urllib.request

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

# ---------- Jira статуси (реальний workflow-статус, сайт команди) ----------
_JIRA_BASE = "https://jira.example.com"

def _jira_creds():
    """(email, token) з env JIRA_EMAIL/JIRA_TOKEN або файлів у ~/.claude/pipeline-feedback/.
    Токен НІКОЛИ не в git/коді/чаті — лише локальний файл (chmod 600)."""
    def _read(env, path):
        v = os.environ.get(env)
        if v:
            return v.strip()
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return None
    email = _read("JIRA_EMAIL", "~/.claude/pipeline-feedback/jira-email")
    token = _read("JIRA_TOKEN", "~/.claude/pipeline-feedback/jira-token")
    return (email, token) if (email and token) else (None, None)

def jira_statuses(keys):
    """{key: {'name','cat'}} з Jira для списку ключів LIGA-XXXX. Best-effort:
    нема токена / помилка мережі → {} (щоб НЕ затерти наявні статуси)."""
    keys = [k for k in dict.fromkeys(k for k in keys if k)]  # унікальні, порядок збережено
    email, token = _jira_creds()
    if not keys or not (email and token):
        return {}
    jql = "key in (" + ",".join(keys) + ")"
    body = json.dumps({"jql": jql, "fields": ["status"], "maxResults": 100}).encode("utf-8")
    auth = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        f"{_JIRA_BASE}/rest/api/3/search/jql", data=body, method="POST",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json",
                 "Content-Type": "application/json"})
    out = {}
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as r:
            data = json.load(r)
        for iss in data.get("issues", []):
            st = (iss.get("fields") or {}).get("status") or {}
            out[iss.get("key")] = {"name": st.get("name"),
                                   "cat": (st.get("statusCategory") or {}).get("key")}
    except Exception:  # noqa: BLE001
        return {}
    return out

def _ssl_context():
    """Проверенный TLS: certifi, если есть (фикс macOS python.org — как в serve.py). Лишився лише для запиту до Jira."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()

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


def _legacy_config():
    """`(url, key)` ЛІГИ: конфіг установки (файл раніше за оточення); нема — запасна пара `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
    з оточення (спека §5), і лише так: `supabase_config()` сервісного ключа НЕ бачить (його читають і коментарі)."""
    url, key = install_config.supabase_config()
    if url is None:
        url, key = install_config.service_key_config()
    return url, key


def _target(sp):
    """`(module, ctx, legacy)` постачальника ролі `dashboard` простору `sp`; `(None, None, False)` — постачальника нема.
    `'legacy'` (ЛІГА) — вбудований модуль із `ctx` з конфігу установки (`dashboard.legacy_ctx`, НЕ `module_ctx`: у ЛІГИ нема
    `space.json`/`secrets.json`); інакше `module_ctx` простору."""
    try:
        prov = deai_modules.provider("dashboard", sp)
        if prov is None:
            return None, None, False
        if prov == "legacy":
            return dashboard.legacy_module(), dashboard.legacy_ctx(*_legacy_config(), space_id=sp["id"]), True
        return prov, deai_modules.module_ctx(sp, prov), False
    except deai_modules.ModuleError as e:
        raise CliError("⛔ overview: %s" % (e.message or e.code))
    except spaces.SpacesError as e:
        raise CliError("⛔ overview: реєстр просторів не читається (%s)" % e.code)


def _tasks_of(sp):
    try:
        return load_tasks_file(spaces.tasks_file(sp))
    except (OSError, ValueError) as e:
        raise CliError("⛔ overview: файл задач простору «%s» не читається (%s)" % (sp["id"], type(e).__name__))


def cmd_sync(space_id=None, *, call=None, log=print):
    sp = _space(space_id)
    module, ctx, legacy = _target(sp)
    if module is None:
        log("·  overview: у просторі «%s» нема постачальника командного дашборда — нічого синхронізувати" % sp["id"])
        return
    cfg = _tasks_of(sp)
    # Реєстр і Jira — кроки ЛІГИ (колбеки): звичайний простір їх не має, і ні в реєстр, ні в Jira не ходить.
    dashboard.sync(cfg, module, ctx, discover=(lambda: discover_projects(cfg)) if legacy else None,
                   statuses=jira_statuses if legacy else None, log=log, call=call)


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

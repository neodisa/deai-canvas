#!/usr/bin/env python3
"""design-canvas · пуш статусу проєктів у реєстр овервью (Supabase). Task 1: чиста логіка."""
import base64, json, os, re, subprocess, sys, time
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
                       comment_project_key, _identity, _humanize, _fixture_reason)
from dashboard import build_card as build_row, card_has_pii as row_has_pii, discover_card as discover_row  # noqa: F401
import dashboard as _dashboard

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

# ---------- Supabase write client (Task 2) ----------
# Конфіг Supabase: спершу env, інакше геттер конфігу установки (`serve.supabase_config`).
# ⚠️ Порядок джерел ПРОТИЛЕЖНИЙ `serve.supabase_config()` (там файл `tasks.json` важить більше за оточення) і тут оточення
# знає ще й `SUPABASE_SERVICE_KEY`. Сервер передає дитині `_overview_sync` конфіг через оточення — тож там усе збігається;
# окремий чи запланований `overview_push.py sync` із чужим `SUPABASE_URL`/`SUPABASE_KEY` в оточенні пише ТУДИ. Дашборд — етап 4c,
# поведінку тут не змінюємо (CHANGELOG 0.10.0, «Known limits»).

def _supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
        from serve import supabase_config  # геттер конфігу установки (`serve.supabase_config`)
        url, key = supabase_config()
    if not (url and key):
        raise RuntimeError("Supabase не налаштовано: supabase_url і supabase_key у tasks.json "
                           "або SUPABASE_URL/SUPABASE_KEY")
    return url.rstrip("/"), key

def _ssl_context():
    """Проверенный TLS: certifi, если есть (фикс macOS python.org — как в serve.py)."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()

def upsert_project(row, ignore=False):
    """ignore=False → merge-duplicates (оновити наявний рядок, для канваса).
    ignore=True → ignore-duplicates (лише вставити новий, НЕ чіпати наявний — для discover,
    щоб не затерти багаті дані канваса базовою карткою)."""
    url, key = _supabase()
    body = json.dumps([row]).encode("utf-8")
    resolution = "ignore-duplicates" if ignore else "merge-duplicates"
    req = urllib.request.Request(
        f"{url}/rest/v1/overview_projects?on_conflict=id",
        data=body, method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": f"resolution={resolution},return=minimal"})
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as r:
        return r.status

# ---------- sync CLI (Task 3): tasks.json → per-task state → rows → upsert ----------
# OFFLINE-testable: жодного імпорту serve.py і жодних мережевих викликів у логіці
# синхронізації самій по собі (лише upsert_project() у кінці ходить у мережу).

def _tasks_path():
    """Той самий DC_TASKS_FILE, що й у serve.tasks_path() — інакше пушер і сервер
    читали б РІЗНІ файли (сервер — підмінений тестовий, пушер — живий, або
    навпаки), і синк реєстру знову розʼїхався б із тим, що бачить дизайнер.
    Оточення читається на кожен виклик, не кешується."""
    return os.environ.get("DC_TASKS_FILE") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tasks.json")

def load_tasks_file(path=None):
    with open(path or _tasks_path(), encoding="utf-8") as f:
        return json.load(f)

def open_comment_counts():
    """Реальні лічильники ВІДКРИТИХ коментарів по project_id з таблиці comments
    (той самий Supabase, що й комментатор). Best-effort → {} при будь-якій помилці."""
    try:
        url, key = _supabase()
        req = urllib.request.Request(
            f"{url}/rest/v1/comments?status=eq.open&select=project_id",
            headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as r:
            rows = json.load(r)
    except Exception:  # noqa: BLE001
        return {}
    counts = {}
    for row in rows:
        pid = row.get("project_id")
        if pid:
            counts[pid] = counts.get(pid, 0) + 1
    return counts

# ---------- Discovery: реєстр задач (design-office, гілка registry) ----------
# Реєстр — ЄДИНЕ джерело істини по задачах усіх напрямків (united / liga360 / seo).
# Раніше тут сканувалась тека mockup/* ОДНОГО репо, тому напрямки в оверв'ю не
# розрізнялися і бачився тільки перший репозиторій.

def _serve():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
    import serve  # noqa
    return serve

def _registry():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import registry  # noqa
    return registry

def _drop_fixtures(entries, where):
    """{id: запис} без фікстур (`dashboard._drop_fixtures`); причину бере з ЦЬОГО модуля (`_fixture_reason`) — шов, яким
    тести пушера вимикають бар'єр підміною імені тут."""
    return _dashboard._drop_fixtures(entries, where, reason=_fixture_reason)

def discover_projects(cfg):
    """{id: запис} із реєстру. {} при будь-якій помилці (нема VPN/доступу) — не падаємо."""
    try:
        reg = _registry()
        return reg.read_registry(reg.ensure_clone(cfg))
    except Exception:  # noqa: BLE001
        return {}

def cmd_discover():
    cfg = load_tasks_file()
    reg = _drop_fixtures(discover_projects(cfg), "/discover")
    count = 0
    for pid, entry in reg.items():
        row = discover_row(pid, entry)
        if row_has_pii(row):
            continue
        try:
            upsert_project(row, ignore=True)  # лише нові
            count += 1
        except Exception as e:  # noqa: BLE001
            print(f"⚠ overview/discover: «{pid}»: {e}")
    print(f"✅ overview/discover: у реєстрі {len(reg)}, оброблено {count} (нові додано)")
    return list(reg)

def cmd_sync():
    cfg = load_tasks_file()
    designer, designer_key = _identity()
    # 0) Реєстр: усі заведені задачі всіх напрямків (базові картки); локальні задачі нижче їх збагатять
    disc = 0
    for pid, entry in _drop_fixtures(discover_projects(cfg), "").items():
        row = discover_row(pid, entry)
        if row_has_pii(row):
            continue
        try:
            upsert_project(row, ignore=True); disc += 1  # лише нові, не чіпати багаті рядки канваса
        except Exception:  # noqa: BLE001
            pass
    if disc:
        print(f"✅ overview: з реєстру оброблено {disc} задач (нові додано)")
    counts = open_comment_counts()  # реальні відкриті коменти → також рухають статус у «review»
    jstatus = jira_statuses([t.get("jira") for t in cfg.get("tasks", {}).values()])  # реальні Jira-статуси
    count = 0
    skipped = []
    # Фікстура в ЛОКАЛЬНОМУ кеші (живий tasks.json, затертий тестом, як
    # 15.09.2026) — теж не на дашборд, навіть поки її тимчасова тека ще існує.
    for tid, task in _drop_fixtures(cfg.get("tasks", {}), "").items():
        # ⛔ Немає теки задачі на цій машині — ми про неї НІЧОГО не знаємо, тому й
        # не пишемо: інакше task_state() віддає нулі, і синк вихолощує спільний
        # рядок (реальний випадок: `erb` обнулявся кожні 30 хв). Базова картка
        # такої задачі вже прийшла з реєстру кроком 0.
        d = task.get("dir") or ""
        if not os.path.isdir(d):
            skipped.append(tid)
            continue
        st = task_state(task)
        st["open_comments"] = counts.get(comment_project_key(task, tid), 0)
        js = jstatus.get(task.get("jira") or "")
        if js and js.get("name"):
            st["jira_status"] = js["name"]
            st["jira_status_cat"] = js.get("cat")
        row = build_row(tid, task, st, designer, designer_key)
        if row_has_pii(row):
            print(f"⚠ overview: пропущено «{tid}» — виявлено PII в даних")
            continue
        try:
            upsert_project(row)
            count += 1
        except Exception as e:  # noqa: BLE001
            print(f"⚠ overview: не вдалося синхронізувати «{tid}»: {e}")
    print(f"✅ overview: синхронізовано {count} проєктів")
    # Пропуски називаємо вголос: тиха «часткова» синхронізація виглядає як повна.
    if skipped:
        print(f"·  overview: пропущено {len(skipped)} — теки немає на цій машині "
              f"({', '.join(skipped)}); їхні картки лишились як були")

def main():
    args = sys.argv[1:]
    if not args or args[0] == "sync":
        cmd_sync()
    elif args[0] == "discover":
        cmd_discover()
    else:
        print("Використання: overview_push.py [sync|discover]")

if __name__ == "__main__":
    main()

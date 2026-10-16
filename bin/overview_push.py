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

_PII = [re.compile(r"№?\s*\d{2,4}/\d{3,5}/\d{2,4}"), re.compile(r"\b\d{10}\b"), re.compile(r"\b\d{8}\b")]

_GL_SSH = re.compile(r"^git@([^:]+):(.+?)(?:\.git)?$")
_GL_BRANCH = "main"  # дефолтна гілка репо макетів усіх напрямків (united/liga360/seo)

def gitlab_web(gl):
    """git@host:group/repo.git (+ path) → https-URL. З path — дип-лінк на теку проєкту
    в гілці main, без path — корінь проєкту. None, якщо нема repo."""
    if not isinstance(gl, dict):
        return None
    repo = gl.get("repo")
    if not repo:
        return None
    m = _GL_SSH.match(repo.strip())
    if m:
        base = f"https://{m.group(1)}/{m.group(2)}"
    elif repo.startswith("http"):
        base = repo[:-4] if repo.endswith(".git") else repo
    else:
        return None
    path = (gl.get("path") or "").strip("/")
    return f"{base}/-/tree/{_GL_BRANCH}/{path}" if path else base

def to_iso(dt):
    """«DD.MM.YYYY[ HH:MM]» (локальний час Києва) → ISO з офсетом +03:00. None, якщо не парситься."""
    if not dt:
        return None
    m = re.match(r"\s*(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", str(dt))
    if not m:
        return None
    d, mo, y, hh, mm = m.groups()
    return f"{y}-{mo}-{d}T{int(hh or 0):02d}:{mm or '00'}:00+03:00"

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

def map_status(st):
    if st.get("published") and st.get("finalized"):
        return "done"
    if st.get("open_comments", 0) > 0:
        return "review"
    if st.get("published"):
        return "pub"
    return "work"

def preview_source(code_url, figma):
    if code_url:
        return "code"
    if figma:
        return "figma"
    return None

def build_row(task_id, task, st, designer, designer_key):
    code_url = st.get("code_url")
    figma = task.get("figma") or st.get("figma")
    gl = task.get("gitlab") or {}
    # реальна дата апдейту прев'ю (published_at / остання ітерація), НЕ момент пушу
    updated_at = to_iso(st.get("last_update")) or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Heartbeat: момент, коли ЦЕЙ пушер відпрацював. Єдине поле, яким видно, що
    # машинно-залежне збагачення живе. Свідомо НЕ updated_at (той показує вік
    # макета: 495 год у watchlists-bg — норма) і НЕ jira_synced_at (його пише й
    # хмарний CI, тому зупинку пушера він маскує). Дашборд бере max(synced_at):
    # пушер один, а окремі задачі законно пропускаються, коли теки нема локально.
    synced_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row = {
        "id": task_id,
        "name": task.get("title", task_id),
        "status": map_status(st),
        "jira": task.get("jira"),
        "figma_url": figma,
        "code_url": code_url,
        "thumb_source": preview_source(code_url, figma),
        # ⛔ open_comments БІЛЬШЕ НЕ ШЛЕМО. З 07.08.2026 його рахує сама БД
        # (тригер ov_comments_recount на comments): обидві таблиці лежать в одному
        # Supabase, тож для підрахунку машина не потрібна взагалі — лічильник
        # оновлюється в мить, коли рецензент ставить пін, а не через 30 хв і не
        # «коли ноутбук увімкнуть». Якщо повернути ключ сюди, пушер перезатиратиме
        # свіже значення бази своїм локальним зрізом. Не повертай.
        "iterations": int(st.get("iterations", 0)),
        "pages": st.get("pages") or None,  # к-сть сторінок макета (None, якщо 0/невідомо)
        "gitlab_url": gitlab_web(gl),
        # сирі дані GitLab + comment-проєкт — для самодостатнього промпта «відкрити в канвасі»
        "gitlab_repo": gl.get("repo"),
        "gitlab_path": gl.get("path"),
        "comment_project": task.get("comment_project"),
        "backup_at": to_iso(st.get("backup_at")),
        "source": "canvas",
        "updated_at": updated_at,
        "synced_at": synced_at,
    }
    # Jira-статус додаємо ЛИШЕ коли реально отримали свіже значення — інакше пропускаємо
    # ключі (merge-duplicates збереже наявні, не затре null'ом).
    if st.get("jira_status"):
        row["jira_status"] = st["jira_status"]
        row["jira_status_cat"] = st.get("jira_status_cat")
        row["jira_synced_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Авторство картки НЕ присвоюємо. `registry.py pull` вписує в локальний
    # tasks.json ВСІ задачі реєстру, включно з чужими — і раніше будь-який синк
    # переписував `designer` чужого рядка на себе. Свій ключ знаємо з git-конфіга,
    # власника задачі — з реєстру (owner_key їде в SHARED).
    owner_key = task.get("owner_key")
    # «designer» — заглушка `_identity()` без git-email, тобто «особи немає», а не «чужий».
    if not owner_key or not designer_key or designer_key == "designer" or owner_key == designer_key:
        row["designer"] = designer
        row["designer_key"] = designer_key
    else:
        # Посилання картки — превʼю ВЛАСНИКА (рішення 29.09.2026, fb-29092026-69e9c7):
        # не-власник публікує у своє, і його синк лінк на картці не підміняє.
        row.pop("code_url", None)
        row.pop("thumb_source", None)
    # ⛔ None-и не відправляємо: у merge-duplicates вони ЗАТИРАЮТЬ наявні значення.
    # Саме так картка з відсутньою локально текою втрачала code_url/pages/jira.
    # Той самий фільтр, що й у discover_row() — щоб обидва шляхи поводились однаково.
    return {k: v for k, v in row.items() if v is not None}

def row_has_pii(row):
    blob = " ".join(str(row.get(k) or "") for k in ("name",))
    return any(p.search(blob) for p in _PII)

# ---------- Supabase write client (Task 2) ----------
# Реюзаємо конфіг comment-layer (serve.py): спершу env, інакше геттер serve.supabase_config().

def _supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
        from serve import supabase_config  # тонкий геттер поруч із SUPABASE_URL/KEY у serve.py
        url, key = supabase_config()
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

def _identity():
    def _git(key):
        try:
            out = subprocess.run(["git", "config", key], capture_output=True,
                                  text=True, timeout=5)
            val = out.stdout.strip()
            return val or None
        except Exception:  # noqa: BLE001
            return None
    name = _git("user.name") or os.environ.get("USER", "designer")
    email = _git("user.email") or "designer"
    return name, email

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

def comment_project_key(task, task_id):
    """Ключ проєкту в таблиці comments: явний comment_project, інакше «dc/<id>» (канвас)."""
    return task.get("comment_project") or f"dc/{task_id}"

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

def _humanize(pid):
    return (pid.replace("-", " ").replace("_", " ").strip().capitalize()) or pid

def _fixture_reason(task):
    """Причина, якщо задача вказує в тимчасову теку (фікстура тесту), інакше None.

    ⛔ Правило одне на всіх — `registry.fixture_path_reason`, тут лише делегуємо.
    Інцидент 15.09.2026: фікстура `nova` (gitlab.repo у /var/folders/…) протекла
    в реєстр, і крок 0 синку (`discover_row`) виставив її на КОМАНДНИЙ дашборд
    карткою «Нова» зі статусом `pub`. Дашборд — теж спільний стан, тож бар'єр
    стоїть і тут, на самому відвантаженні, а не лише на пуші в реєстр: у
    реєстрі сміття вже може лежати, і прибирає його людина, а не синк."""
    return _registry().fixture_path_reason(task)

def _drop_fixtures(entries, where):
    """{id: запис} без фікстур; кожну відкинуту — вголос, з причиною."""
    out = {}
    for tid, e in entries.items():
        why = _fixture_reason(e)
        if why:
            print(f"⛔ overview{where}: не віддаю на дашборд «{tid}» — {why}; "
                  f"прибери її з реєстру (гілка registry) і рядок з overview_projects")
            continue
        out[tid] = e
    return out

def discover_projects(cfg):
    """{id: запис} із реєстру. {} при будь-якій помилці (нема VPN/доступу) — не падаємо."""
    try:
        reg = _registry()
        return reg.read_registry(reg.ensure_clone(cfg))
    except Exception:  # noqa: BLE001
        return {}

def discover_row(pid, entry):
    """Картка проєкту з реєстру. Локальні задачі нижче збагатять її кодом/ітераціями."""
    gl = dict(entry.get("gitlab") or {})
    if gl.get("repo") and not gl.get("path"):
        gl["path"] = f"mockup/{pid}"          # конвенція: тека макета = id задачі
    row = {
        "id": pid,
        "name": entry.get("title") or _humanize(pid),
        "status": "pub",              # присутній у реєстрі = задача заведена
        "jira": entry.get("jira"),
        "comment_project": entry.get("comment_project"),
        "gitlab_repo": gl.get("repo"),
        "gitlab_path": gl.get("path"),
        "gitlab_url": gitlab_web(gl) if gl.get("repo") and gl.get("path") else None,
        "source": "registry",
        "updated_at": entry.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if entry.get("figma"):
        row["figma_url"] = entry["figma"]
    if entry.get("owner"):                # хто завів задачу — видно в дашборді
        row["designer"] = entry["owner"]
        row["designer_key"] = entry.get("owner_key")
    # напрямок дашборд виводить із gitlab_repo (окремої колонки в overview_projects немає)
    return {k: v for k, v in row.items() if v is not None}

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

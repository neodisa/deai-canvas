"""Збирання карток командного дашборда (етап 4c-1): чиста логіка, спільна для CLI-пушера й сервера.

Переїхало з `bin/overview_push.py` БЕЗ зміни поведінки (`build_row` → `build_card`, `discover_row` → `discover_card`,
`row_has_pii` → `card_has_pii`); старі імена пушер реекспортує. ⛔ Цей модуль НЕ імпортує `serve` (тягне сервер, мережу й увесь
стан) — його читають і CLI, і сервер; реєстр GitLab (`bin/registry.py`) підтягується ліниво, лише коли потрібен.
"""
import os
import re
import subprocess
import sys
import time

import deai_modules
from task_state import task_state

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

def build_card(task_id, task, st, designer, designer_key):
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
    # Той самий фільтр, що й у discover_card() — щоб обидва шляхи поводились однаково.
    return {k: v for k, v in row.items() if v is not None}

def card_has_pii(row):
    blob = " ".join(str(row.get(k) or "") for k in ("name",))
    return any(p.search(blob) for p in _PII)

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

def comment_project_key(task, task_id):
    """Ключ проєкту в таблиці comments: явний comment_project, інакше «dc/<id>» (канвас)."""
    return deai_modules.legacy_comment_channel(task, task_id)

def _registry():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
    import registry  # noqa
    return registry

def _humanize(pid):
    return (pid.replace("-", " ").replace("_", " ").strip().capitalize()) or pid

def _fixture_reason(task):
    """Причина, якщо задача вказує в тимчасову теку (фікстура тесту), інакше None.

    ⛔ Правило одне на всіх — `registry.fixture_path_reason`, тут лише делегуємо.
    Інцидент 15.09.2026: фікстура `nova` (gitlab.repo у /var/folders/…) протекла
    в реєстр, і крок 0 синку (`discover_row`, тепер `discover_card`) виставив її на КОМАНДНИЙ дашборд
    карткою «Нова» зі статусом `pub`. Дашборд — теж спільний стан, тож бар'єр
    стоїть і тут, на самому відвантаженні, а не лише на пуші в реєстр: у
    реєстрі сміття вже може лежати, і прибирає його людина, а не синк."""
    return _registry().fixture_path_reason(task)

def _drop_fixtures(entries, where, reason=None, log=print):
    """{id: запис} без фікстур; кожну відкинуту — вголос, з причиною.

    `reason` — шов: функція «запис → причина чи None»; без неї — `_fixture_reason` цього модуля (шукається на момент
    виклику, тож підміна в тестах працює). `log` — куди називати відкинуте (типово `print`; `sync` передає свій). Колись
    `bin/overview_push.py` передавав сюди СВІЙ `_fixture_reason` (його тести підміняли це ім'я на пушері); після 4c-1 (Task 6)
    кроки синку живуть тут, тож шов — `dashboard._fixture_reason`."""
    out = {}
    for tid, e in entries.items():
        why = (reason or _fixture_reason)(e)
        if why:
            log(f"⛔ overview{where}: не віддаю на дашборд «{tid}» — {why}; "
                f"прибери її з реєстру (гілка registry) і рядок з overview_projects")
            continue
        out[tid] = e
    return out

def discover_card(pid, entry):
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


# ------------------------------------------------------------------------------------ читання: рядки команди (Task 5)

#: Колонки рядка команди: ядро бере з відповіді модуля ЛИШЕ їх (решта — напр. `secret_col` чужої таблиці — відкидається).
#: Без `select=*` (урок колишнього `serve.TEAM_COLS`): таблицю пише пушер реєстру, і зайві поля, що там зʼявляться, не мають
#: їхати в кожну відповідь і в кеш. Той самий кортеж і в модулі `supabase-dashboard` (`TEAM_KEYS`): модулі не імпортують ядро,
#: тож тут його продубльовано.
TEAM_KEYS = ('id', 'name', 'jira', 'jira_status', 'jira_status_cat', 'open_comments', 'thumb_url', 'code_url',
             'updated_at', 'designer', 'iterations', 'pages')
MAX_ROWS = 500
#: Скільки ядро чекає на `rows` модуля. ⛔ НЕ 4 с: це власний тайм-аут модуля на ОПЕРАЦІЮ сокета (`READ_TIMEOUT_S`; у знімку 0.11.0
#: було 3 с на запит), а ядро мусить чекати ТРОХИ довше — тоді модуль встигає відповісти СВОЇМ текстом («Supabase недоступний
#: (…)»), а людина не бачить голого `check-timeout` ядра (урок `COMMENTS_TIMEOUT`). Тест `ReadPath` стереже нерівність.
READ_TIMEOUT = 6
#: Таблиця й модуль запису дашборда ЛІГИ (явний `supabase-dashboard`; запасного неявного постачальника більше нема, 4d-4b).
LEGACY_TABLE = 'overview_projects'
LEGACY_MODULE = 'supabase-dashboard'
UNCONFIGURED = 'Supabase не налаштовано: додайте адресу й ключ на екрані «Налаштування»'


def normalize_rows(data):
    """Рядки команди з відповіді `rows` модуля: лише обʼєкти з рядковим `id`, лише ключі `TEAM_KEYS`, не більше `MAX_ROWS`.
    Не список — `ValueError`. Чужий модуль міг би повернути що завгодно (і зайві колонки таблиці): екран бачить лише це."""
    if not isinstance(data, list):
        raise ValueError('rows: очікувався масив')
    out = []
    for r in data[:MAX_ROWS]:
        if isinstance(r, dict) and isinstance(r.get('id'), str):
            out.append({k: r.get(k) for k in TEAM_KEYS})
    return out


def rows(module, ctx):
    """Рядки команди від постачальника: `module.rows(ctx)` у робочому потоці за `READ_TIMEOUT`, далі `normalize_rows`.
    Кидає `ModuleError` (збій модуля, `check-timeout`) чи `ValueError` (відповідь не список)."""
    return normalize_rows(deai_modules.call(module, 'rows', ctx, timeout=READ_TIMEOUT))


# ------------------------------------------------------------------------------------------ запис: синк карток (Task 6)

#: Скільки ядро чекає на ОДИН виклик `push`/`open_comments` модуля. Це фоновий процес синку (не сервер і не екран): модуль сам
#: обмежує кожен пакет (15 с), а це стеля на весь виклик, щоб завислий модуль не тримав дитину вічно.
PUSH_TIMEOUT = 60


def _has_fn(module, name):
    """Чи має модуль функцію `name` (необовʼязкові функції ролі: `open_comments`)."""
    fn = getattr(module, 'fn', None)
    try:
        return callable(fn) and fn(name) is not None
    except Exception:  # noqa: BLE001 — незавантажений модуль/збій каталогу: «функції нема»
        return False


def _push(call, module, ctx, cards, mode):
    """`(ok, failed)` за один виклик `push(cards, mode)`. `failed` — `{id: текст}`. Не кидає: збій цілого сервісу
    (`ModuleError`, тайм-аут) чи відповідь не за контрактом — це ВСІ картки в `failed` з одним текстом (синк веде далі й
    називає їх вголос, а не падає посеред проходу)."""
    if not cards:
        return 0, {}
    try:
        res = call(module, 'push', ctx, cards, mode, timeout=PUSH_TIMEOUT)
    except deai_modules.ModuleError as e:
        text = (e.message or e.code or 'збій модуля')[:200]
        return 0, {c['id']: text for c in cards}
    except Exception as e:  # noqa: BLE001 — шов `call` у тестах / чужа реалізація: той самий висновок
        return 0, {c['id']: (str(e) or type(e).__name__)[:200] for c in cards}
    if not isinstance(res, dict):
        return 0, {c['id']: 'відповідь модуля не за контрактом push' for c in cards}
    ok = res.get('ok')
    failed = res.get('failed')
    failed = {str(k): str(v)[:200] for k, v in failed.items()} if isinstance(failed, dict) else {}
    return (ok if isinstance(ok, int) and not isinstance(ok, bool) else 0), failed


def push_registry(module, ctx, entries, where, *, log=print, call=None):
    """Базові картки з реєстру задач (крок 0 синку й команда `discover`; лише ЛІГА): фікстури відкидаються вголос
    (`_drop_fixtures`), PII-картки пропускаються, решта — `push(…, 'insert')` (наявні рядки НЕ чіпати: базова картка не має
    затерти багаті дані канваса). Повертає `(entries без фікстур, ok, failed)`."""
    reg = _drop_fixtures(entries, where, log=log)
    cards = []
    for pid, entry in reg.items():
        card = discover_card(pid, entry)
        if card_has_pii(card):
            continue
        cards.append(card)
    ok, failed = _push(call or deai_modules.call, module, ctx, cards, 'insert')
    return reg, ok, failed


def sync(cfg, module, ctx, *, discover=None, statuses=None, channel_of=None, identity=None, log=print, call=None):
    """Один прохід синку карток простору (спека §4). `cfg` — файл задач простору (`{'tasks': {…}}`); `module`/`ctx` —
    постачальник ролі `dashboard` (модуль + його `ctx`: `module_ctx` запису); `call` — `deai_modules.call` (шов для
    тестів); `identity` — `(імʼя, ключ)` дизайнера, без нього — `_identity()` (git-конфіг).
    `discover()` → `{id: запис}` (лише ЛІГА: реєстр GitLab) — крок, що ще не став роллю: звичайний простір його не має;
    `statuses(keys)` → `{ключ: {name, cat}}` — статуси трекера (будь-який простір із роллю `tracker`: колбек будує CLI з
    постачальника ролі; `None` — постачальника чи конфігу нема, крок пропущено);
    `channel_of(task, tid)` → канал коментарів задачі (ключ лічильника відкритих): його будує CLI з постачальника ролі `comments`
    через `deai_modules.comment_channel_of`; без нього — схема comment-layer (`legacy_comment_channel`, як у 0.17.0).

    Кроки: 0) базові картки з реєстру → `push(…, 'insert')`; 1) відкриті коментарі (`open_comments`, якщо модуль її має) →
    лічильники для статусу `review`; 2) статуси трекера; 3) задачі простору з текою НА ЦІЙ МАШИНІ → `build_card` → PII-фільтр →
    `push(…, 'merge')`; 4) підсумок у `log`. Повертає `{'discovered', 'synced', 'skipped', 'failed'}` (для тестів; CLI ігнорує).
    ⛔ Збій кроку НЕ валить проход і НЕ мовчить: назви карток із `failed` — у `log` вголос (мовчазна «часткова» синхронізація
    виглядає як повна)."""
    call = call or deai_modules.call
    channel_of = channel_of or deai_modules.legacy_comment_channel
    designer, designer_key = identity if identity is not None else _identity()
    summary = {'discovered': 0, 'synced': 0, 'skipped': [], 'failed': {}}
    # 0) Реєстр: усі заведені задачі всіх напрямків (базові картки); локальні задачі нижче їх збагатять
    if discover is not None:
        _, ok, failed = push_registry(module, ctx, discover(), '', log=log, call=call)
        summary['discovered'] = ok
        for pid, why in failed.items():
            log(f'⚠ overview: не вдалося додати з реєстру «{pid}»: {why}')
        if ok:
            log(f'✅ overview: з реєстру оброблено {ok} задач (нові додано)')
    # 1) Реальні відкриті коменти → також рухають статус у «review». Best-effort → {} при будь-якій помилці.
    counts = {}
    if _has_fn(module, 'open_comments'):
        try:
            got = call(module, 'open_comments', ctx, timeout=PUSH_TIMEOUT)
            counts = got if isinstance(got, dict) else {}
        except Exception:  # noqa: BLE001
            counts = {}
    # 2) Реальні статуси трекера (будь-який простір із роллю `tracker`)
    jstatus = {}
    if statuses is not None:
        try:
            jstatus = statuses([t.get('jira') for t in cfg.get('tasks', {}).values()]) or {}
        except Exception as e:  # noqa: BLE001 — best-effort: нема статусів ≠ затирати наявні (`{}`: картка без `jira_status`)
            jstatus = {}
            # ⛔ НЕ мовчки: до 4c-2 збій Jira тут не лишав сліду. Текст — повідомлення `ModuleError` (ядро вже вичистило з
            # нього секрети), інакше лише назва класу: `str(e)` чужого винятку не чищений і міг би винести секрет у лог.
            # Не довше 200 знаків
            why = (e.message if isinstance(e, deai_modules.ModuleError) else '') or type(e).__name__
            log(f'⚠ overview: статуси трекера недоступні: {why[:200]}')
    skipped = []
    cards = []
    # Фікстура в ЛОКАЛЬНОМУ кеші (живий tasks.json, затертий тестом, як
    # 15.09.2026) — теж не на дашборд, навіть поки її тимчасова тека ще існує.
    for tid, task in _drop_fixtures(cfg.get('tasks', {}), '', log=log).items():
        # ⛔ Немає теки задачі на цій машині — ми про неї НІЧОГО не знаємо, тому й
        # не пишемо: інакше task_state() віддає нулі, і синк вихолощує спільний
        # рядок (реальний випадок: `erb` обнулявся кожні 30 хв). Базова картка
        # такої задачі вже прийшла з реєстру кроком 0.
        d = task.get('dir') or ''
        if not os.path.isdir(d):
            skipped.append(tid)
            continue
        st = task_state(task)
        st['open_comments'] = counts.get(channel_of(task, tid), 0)
        js = jstatus.get(task.get('jira') or '')
        if js and js.get('name'):
            st['jira_status'] = js['name']
            st['jira_status_cat'] = js.get('cat')
        card = build_card(tid, task, st, designer, designer_key)
        if card_has_pii(card):
            log(f'⚠ overview: пропущено «{tid}» — виявлено PII в даних')
            continue
        cards.append(card)
    # 3) Картки задач: `merge` — оновити наявний рядок, нові поля зверху
    count, failed = _push(call, module, ctx, cards, 'merge')
    for tid, why in failed.items():
        log(f'⚠ overview: не вдалося синхронізувати «{tid}»: {why}')
    log(f'✅ overview: синхронізовано {count} проєктів')
    # Пропуски називаємо вголос: тиха «часткова» синхронізація виглядає як повна.
    if skipped:
        log(f"·  overview: пропущено {len(skipped)} — теки немає на цій машині "
            f"({', '.join(skipped)}); їхні картки лишились як були")
    summary.update(synced=count, skipped=skipped, failed=failed)
    return summary

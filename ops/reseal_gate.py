#!/usr/bin/env python3
"""Перевикотити гейт превʼю з ОНОВЛЕНИМ скриптом (безшовний вхід із Liga Design Office).
Перегенеровує лише publish/index.html (свитчер+гейт) з поточних шаблонів serve.py —
дизайн-контент і бандли комментатора незмінні — та передеплоює на Vercel.

Використання:
  python3 ops/reseal_gate.py --build courts        # тільки перезібрати index.html
  python3 ops/reseal_gate.py courts                # перезібрати + vercel deploy
  python3 ops/reseal_gate.py                        # усі задачі з publish/ (+deploy)
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
# ⛔ Обгортку НЕ збираємо тут своїми руками: і перелік сторінок, і сам HTML
# віддає serve. До 04.08.2026 цей скрипт мав власний обхід сторінок із власним
# фільтром — копія логіки публікації, яка мовчки розійшлась би з нею.
import spaces  # noqa: E402
from deai_modules import ModuleError  # noqa: E402
from serve import (BUILD_KINDS, BUNDLES, PREVIEW_SHELL_VERSION, gate_html, load_meta, preview_gate_state,  # noqa: E402
                   preview_index_html, preview_password, legacy_tasks_path)


def load_tasks():
    # Через serve.legacy_tasks_path(), а не свій join: інакше цей скрипт читав би інший
    # файл, ніж сервер, коли DC_TASKS_FILE перевизначено (тести, ізольований прогін). Саме
    # СТАРИЙ файл, а не файл «поточного простору»: це інструмент ЛІГА (Vercel-превʼю її задач).
    with open(legacy_tasks_path(), encoding="utf-8") as f:
        return json.load(f)


def liga_space():
    """Запис простору ЛІГА з реєстру (`legacy: true`) або `None`: пароль превʼю — секрет явного `vercel-publish` цього простору (4d-4b).
    Реєстр не читається — `None` (пароль задачі чи `1100`)."""
    try:
        return next((s for s in spaces.read_registry()["spaces"] if s.get("legacy") is True), None)
    except (spaces.SpacesError, KeyError, TypeError):     # реєстр без `spaces` чи з не-списком — «нема простору», а не збій
        return None


def rebuild_index(tid, task):
    pub = os.path.join(task["dir"], "publish")
    if not os.path.isfile(os.path.join(pub, "index.html")):
        return None
    its = [i for i in (load_meta(task) or {}).get("iterations", []) if i.get("published")]
    if not its:
        return None
    # Пароль — з tasks.json задачі (може бути свій), не хардкод.
    # ⚠️ Цей скрипт перезбирає ЛИШЕ обгортку. Гейт у внутрішніх сторінках додає
    # публікація; якщо превʼю зібрано до 03.08.2026, потрібна саме перепублікація,
    # а не reseal — інакше пряме посилання на сторінку так і минатиме пароль.
    try:
        pw = preview_password(task, liga_space())
    except ModuleError:       # fail-closed: нечитабельні секрети — обгортку не чіпаємо (`main` питає раніше й пропускає задачу)
        print(f"⚠ {tid}: секрети простору не читаються — пароль превʼю невідомий. Пропуск.")
        return None
    # ⛔ Обгортка з 02.09.2026 — тонкий каркас: перелік сторінок і назва задачі
    # лежать у `publish/manifest.json`, який пише ЛИШЕ публікація. Тому цей
    # скрипт їх більше не рахує — і не може зістарити (раніше рахував би, а
    # кадри в `_frames/` усе одно лишались би від старої публікації).
    # ⚠️ Зворотний бік, названий вголос: reseal на превʼю, зібраному ДО цієї
    # дати, дасть каркас без маніфеста — оболонка скаже «сторінки не
    # завантажились» і не піднімеся. Ліки ті самі, що вже описані нижче для
    # гейта у внутрішніх сторінках: таке превʼю треба ПЕРЕПУБЛІКУВАТИ, а не
    # перепечатувати.
    wrapper = preview_index_html(gate_html(tid, pw), pw)
    with open(os.path.join(pub, "index.html"), "w", encoding="utf-8") as f:
        f.write(wrapper)
    return pub


def build_kind(pub_dir):
    """`(вид, за_міткою)` збірки в `pub_dir`: `'legacy'` (збірка ЛІГА — її й перепечатуємо) чи `'module'` (збірка модуля
    публікації). `за_міткою` — чи вид сказала сама збірка.

    ПОЗИТИВНА мітка — `"build"` у `manifest.json` (її пише `serve.build_preview(build=…)`): `Handler._publish` пише
    `legacy`, модулі публікації — `module`. Склад `comment-layer/` для цього рішення не годиться (2b-2): збірка ЛІГА з
    коментарями модуля несе там лише шар і файли адаптера, ЛІГА без коментарів (`comments_unavailable`) — нічого, а
    локальна збірка модуля може нести те саме, що перша.
    Збірки БЕЗ мітки (зібрані до неї) — запасне правило: ЛІГА-збірка — та, де в `comment-layer/` є ОБИДВА бандли ЛІГА
    (`serve.BUNDLES`; імена звіряємо ТОЧНО за переліком теки, а не `isfile`: на macOS/Windows `Supabase-Adapter.min.js`
    теж «знайшовся б»), решта — модуль. Нечитабельний маніфест чи невідоме значення мітки — теж запасне правило."""
    try:
        with open(os.path.join(pub_dir, "manifest.json"), encoding="utf-8") as f:
            mark = json.load(f).get("build")
    except (OSError, ValueError, AttributeError):
        mark = None
    if mark in BUILD_KINDS:
        return mark, True
    try:
        names = set(os.listdir(os.path.join(pub_dir, "comment-layer")))
    except OSError:
        names = set()
    return ("legacy" if set(BUNDLES) <= names else "module"), False


def shell_version(pub_dir):
    """Покоління оболонки збірки: `shell` із `manifest.json` (його пише `serve.publish_manifest`). Немає ключа, нечитабельний
    маніфест чи не число — `0`: збірка зроблена до оболонки 0.32.0."""
    try:
        with open(os.path.join(pub_dir, "manifest.json"), encoding="utf-8") as f:
            v = json.load(f).get("shell")
    except (OSError, ValueError, AttributeError):
        return 0
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def deploy(pub, task=None):
    # `--scope`, як у публікації (serve._publish): без нього передеплой з машини,
    # де інший дефолтний скоуп, створив би ДРУГИЙ проєкт із тим самим імʼям — і
    # друге посилання. Зі скоупом vercel відмовить вголос.
    scope = (task or {}).get("vercel_scope")
    scope_args = ["--scope", scope] if scope else []
    out = subprocess.run(["npx", "--yes", "vercel", "deploy", "--prod", "--yes",
                          *scope_args],
                         cwd=pub, capture_output=True, text=True, timeout=300)
    return out.returncode == 0, (out.stdout or out.stderr)[-300:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build_only = "--build" in sys.argv
    cfg = load_tasks()
    ids = args or list(cfg.get("tasks", {}).keys())
    for tid in ids:
        task = cfg.get("tasks", {}).get(tid)
        if not task:
            print(f"⚠ {tid}: немає в tasks.json"); continue
        # ⛔ Збірку МОДУЛЯ публікації (`static-publish`, `vercel-publish`) не перепечатуємо й не деплоїмо на Vercel
        # ЛІГА: її гейт — пароль модуля, а не пароль ЛІГА (`preview_gate_state` нижче назвав би його «старим»).
        # Рішення — за АРТЕФАКТОМ, а не за `iterations.json` (метадані можна втратити, а збірку не сплутаєш): за
        # міткою `"build"` у `publish/manifest.json`, яку пише сама збірка (`build_kind`; для збірок без мітки —
        # запасне правило за бандлами ЛІГА). Питаємо ПЕРШИМ, до гейта, `rebuild_index` і `deploy`.
        pub_dir = os.path.join(task["dir"], "publish")
        if os.path.isdir(pub_dir):
            kind, marked = build_kind(pub_dir)
            if kind != "legacy":
                why = ("мітка збірки build: module" if marked
                       else "мітки збірки нема, бандлів коментатора ЛІГА нема — схоже на збірку модуля")
                print(f"·  {tid}: publish/ — збірка модуля публікації, не збірка ЛІГА ({why}) — пропуск")
                continue
        # ⛔ Нова обгортка на СТАРІЙ оболонці (`shell/` лежить у збірці й reseal її не оновлює) — зламане превʼю: відмовляємо
        # ДО будь-якого запису. Ліки — перепублікація з канваса.
        if os.path.isdir(pub_dir) and shell_version(pub_dir) < PREVIEW_SHELL_VERSION:
            print(f"⚠ {tid}: publish/ зібрано зі старою оболонкою (shell {shell_version(pub_dir)} < {PREVIEW_SHELL_VERSION}) — "
                  f"reseal перепечатує лише обгортку; потрібна перепублікація з канваса. Пропуск.")
            continue
        # ⛔ Питаємо ДО перезапису обгортки (ревʼю 1.52): інакше після відмови
        # локальний publish/ уже мав би обгортку з новим паролем, а деплой — ні.
        try:
            pw = preview_password(task, liga_space())
        except ModuleError:       # fail-closed: нечитабельні секрети — пароль невідомий, не підміняємо його на 1100
            print(f"⚠ {tid}: секрети простору не читаються — пароль превʼю невідомий. Пропуск.")
            continue
        gate = preview_gate_state(task, pw)
        if gate["inner_stale"]:
            print(f"⚠ {tid}: {gate['inner_stale']} внутрішніх сторінок зі старим паролем — "
                  f"reseal їх не перепечатує; потрібна перепублікація з канваса. Пропуск.")
            continue
        if gate["ungated"]:
            print(f"⚠ {tid}: {gate['ungated']} сторінок без гейта (зібрано до фікса TD-37) — "
                  f"reseal їх не лікує, потрібна перепублікація.")
        pub = rebuild_index(tid, task)
        if not pub:
            print(f"·  {tid}: немає publish/ або опублікованих ітерацій — пропуск"); continue
        if build_only:
            print(f"🔧 {tid}: index.html перезібрано (без деплою)"); continue
        ok, tail = deploy(pub, task)
        print(f"{'✅' if ok else '⚠'} {tid}: {'передеплоєно' if ok else 'помилка деплою — ' + tail}")


if __name__ == "__main__":
    main()

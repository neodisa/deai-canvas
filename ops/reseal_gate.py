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
from serve import (gate_html, load_meta, preview_gate_state,  # noqa: E402
                   preview_index_html, preview_password, tasks_path)


def load_tasks():
    # Через serve.tasks_path(), а не свій join: інакше цей скрипт читав би інший
    # файл, ніж сервер, коли DC_TASKS_FILE перевизначено (тести, ізольований прогін).
    with open(tasks_path(), encoding="utf-8") as f:
        return json.load(f)


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
    pw = preview_password(load_tasks(), task)
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
        # ⛔ Питаємо ДО перезапису обгортки (ревʼю 1.52): інакше після відмови
        # локальний publish/ уже мав би обгортку з новим паролем, а деплой — ні.
        pw = preview_password(cfg, task)
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

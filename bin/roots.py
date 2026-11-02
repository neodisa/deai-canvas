#!/usr/bin/env python3
"""Корені робочих тек по напрямках: показати розкладку і переселити задачі.

Вимога користувача 31.08.2026: три глобальні напрямки — Ліга Юнайтед, Ліга360,
ЛігаСЕО — лежать у ТРЬОХ теках і трьох репозиторіях. Репозиторії вже три
(`serve.profile_repos()`), а корінь був один: `design_work_root` = тека United, і в
ній опинились задачі всіх напрямків. Дизайнер це помітив і питає, чому SEO-задача
лежить у United — назва теки бреше про напрямок, а правду знає лише tasks.json.

    python3 bin/roots.py              # де що лежить і що не на своєму місці
    python3 bin/roots.py migrate      # що саме переїде (нічого не робить)
    python3 bin/roots.py migrate --apply

Переїзд — це `git mv`-подібна операція на рівні ФС: тека задачі цілком плюс
оновлення `dir` у tasks.json. Макети в GitLab не зачіпаються: там розкладка вже
правильна.
"""
import argparse
import contextlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
from serve import load_tasks, save_tasks, work_root  # noqa: E402


def plan(cfg):
    """Що куди має переїхати. Чиста функція — тому й перевіряється тестами.

    Повертає список записів: (tid, profile, звідки, куди, причина-стоп або None).
    Стоп-причини НЕ приховуємо: мовчазний пропуск задачі в міграції означав би,
    що дизайнер вважає переїзд завершеним, а частина лишилась на місці.
    """
    out = []
    for tid, t in sorted((cfg.get('tasks') or {}).items()):
        cur = t.get('dir')
        if not cur:
            out.append((tid, t.get('profile'), None, None, 'немає dir у tasks.json'))
            continue
        cur = os.path.expanduser(cur)
        want = os.path.join(work_root(cfg, t.get('profile')), tid)
        if os.path.normpath(cur) == os.path.normpath(want):
            continue
        stop = None
        if not os.path.isdir(cur):
            stop = 'теки нема на диску'
        elif os.path.exists(want):
            stop = f'ціль уже існує: {want}'
        out.append((tid, t.get('profile'), cur, want, stop))
    return out


def roots_in_use(cfg):
    """Корінь на кожен профіль + позначка, чи він СВІЙ, чи спільний фолбек."""
    roots = cfg.get('design_work_roots') or {}
    profiles = sorted({(t.get('profile') or '—') for t in (cfg.get('tasks') or {}).values()}
                      | set(roots))
    return [(p, work_root(cfg, p), p in roots) for p in profiles]


def cmd_status(cfg):
    print('Корені напрямків:')
    for profile, root, own in roots_in_use(cfg):
        mark = '✅ свій' if own else '⚠️ спільний (свого кореня немає)'
        print(f'   {profile:10} → {root}  [{mark}]')
    moves = plan(cfg)
    if not moves:
        print('Усі задачі лежать у корені свого напрямку.')
        return 0
    print(f'\nНе на своєму місці: {len(moves)}')
    for tid, profile, cur, want, stop in moves:
        print(f'   {tid} ({profile}): {cur} → {want}'
              + (f'   ⛔ {stop}' if stop else ''))
    print('\nПереселити: python3 bin/roots.py migrate --apply')
    return 0


def cmd_migrate(cfg, apply):
    moves = plan(cfg)
    if not moves:
        print('Переселяти нічого.')
        return 0
    moved = []
    for tid, profile, cur, want, stop in moves:
        if stop:
            print(f'⛔ {tid} ({profile}): {stop} — не чіпаю')
            continue
        print(f'{"→" if apply else "буде"} {tid} ({profile}): {cur} → {want}')
        if not apply:
            continue
        os.makedirs(os.path.dirname(want), exist_ok=True)
        shutil.move(cur, want)
        cfg['tasks'][tid]['dir'] = want
        moved.append(tid)
    if apply and moved:
        save_tasks(cfg)
        print(f'✅ переїхало: {", ".join(moved)} (dir у tasks.json оновлено)')
    elif not apply:
        print('\nЦе був сухий прогін. Насправді: --apply')
    return 0


class NoLegacySpace(Exception):
    """Шар просторів увімкнено, а простору `legacy` у реєстрі нема (і старого файла теж)."""


def _legacy_space():
    """Простір ЛІГА (`legacy`) на час команди: `roots.py` — інструмент ЛІГА, він працює зі
    СТАРИМ файлом, а не з файлом «поточного простору машини». Шар вимкнено — нічого не
    фіксуємо (файл і так один, `DC_TASKS_FILE`). Шар увімкнено — `load_registry()`: він мігрує
    старий файл у реєстр, якщо той зʼявився вже після створення реєстру. Реєстр не прочитати —
    `SpacesError`; простору `legacy` усе одно нема — `NoLegacySpace`: мовчки взятий файл
    «поточного простору» означав би, що `migrate --apply` переселяє теки іншого простору."""
    if not spaces.layer_on():
        return contextlib.nullcontext()
    sp = next((s for s in spaces.load_registry()['spaces'] if s.get('legacy')), None)
    if sp is None:
        raise NoLegacySpace()
    return spaces.request_space(sp['id'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='корені робочих тек по напрямках')
    ap.add_argument('cmd', nargs='?', default='status', choices=['status', 'migrate'])
    ap.add_argument('--apply', action='store_true', help='справді переселити')
    a = ap.parse_args(argv)
    try:
        space = _legacy_space()
    except spaces.SpacesError as e:
        print(f'error: реєстр просторів недоступний — {e}', file=sys.stderr)
        return 2
    except NoLegacySpace:
        # Той самий рядок для двох різних бід: «файла нема» лікується запуском із ЛІГИ, а «файл є, але
        # `load_registry()` його не змігрував» (битий JSON, не обʼєкт, більше 1 МіБ) — правкою файла.
        legacy = spaces.legacy_tasks_file()
        why = (f'старий файл {legacy} є, але його не вдалося прочитати як JSON-обʼєкт ≤1 МіБ'
               if os.path.isfile(legacy) else 'старого tasks.json не знайдено')
        print(f'error: простору ЛІГА (legacy) нема — {why}, roots.py '
              'нічого не переселяє (інший простір він не чіпає)', file=sys.stderr)
        return 2
    with space:
        cfg = load_tasks()
        return cmd_status(cfg) if a.cmd == 'status' else cmd_migrate(cfg, a.apply)


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Корені робочих тек по напрямках: показати розкладку і переселити задачі.

Вимога користувача 31.08.2026: три глобальні напрямки — Ліга Юнайтед, Ліга360,
ЛігаСЕО — лежать у ТРЬОХ теках і трьох репозиторіях. Репозиторії вже три
(явні `tracks` простору ЛІГИ), а корінь був один: `design_work_root` = тека United, і в
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
import tracks  # noqa: E402
import serve  # noqa: E402
from serve import load_tasks, save_tasks  # noqa: E402


def _view():
    """Напрямки простору ЛІГИ на час команди (`serve._TrackView`); простору нема — порожній вигляд."""
    sp = spaces.active_space()
    return serve._TrackView(sp)


def _root_of(cfg, view, track):
    return serve.track_root(view, track) or serve.default_task_root(cfg)


def plan(cfg, view=None):
    """Що куди має переїхати. Чиста функція — тому й перевіряється тестами. Корені — з ЯВНИХ напрямків простору ЛІГИ
    (`serve.track_root`); `view` — `serve._TrackView` цього простору (типово — активний).

    Повертає список записів: (tid, напрямок, звідки, куди, причина-стоп або None). Напрямок задачі — `tracks.of_task` (`track`).
    Стоп-причини НЕ приховуємо."""
    view = view or _view()
    out = []
    for tid, t in sorted((cfg.get('tasks') or {}).items()):
        track = tracks.of_task(t)
        cur = t.get('dir')
        if not cur:
            out.append((tid, track, None, None, 'немає dir у tasks.json'))
            continue
        cur = os.path.expanduser(cur)
        known = tracks.find(view.tracks, track)
        if known is not None and not known.get('root'):
            # ⛔ Напрямок відомий, але СВОГО кореня не має (після кроку D корінь, узятий адаптером зі спільного, відкинуто): `_root_of`
            # дав би теку простору, і задачу стягнуло б туди зі спільної теки. Як з невідомим напрямком: лише називаємо.
            out.append((tid, track, cur, None, 'корінь напрямку не задано'))
            continue
        if known is None:
            # ⛔ Напрямок невідомий простору (нема `track`, чи він поза переліком): такій задачі «свого» кореня нема, а корінь
            # дефолтного напрямку — не її. Переселення стягнуло б її з теки, де вона лежить, у чужу: не чіпаємо, лише називаємо.
            out.append((tid, track, cur, None, 'напрямок невідомий'))
            continue
        want = os.path.join(_root_of(cfg, view, track), tid)
        if os.path.normpath(cur) == os.path.normpath(want):
            continue
        stop = None
        if not os.path.isdir(cur):
            stop = 'теки нема на диску'
        elif os.path.exists(want):
            stop = f'ціль уже існує: {want}'
        out.append((tid, track, cur, want, stop))
    return out


def roots_in_use(cfg, view=None):
    """Корінь на кожен напрямок + позначка, чи він СВІЙ (`root` напрямку), чи тека простору. Напрямки — ті, що є в задачах
    (`tracks.of_task`, без напрямку — «—»), і явні напрямки простору."""
    view = view or _view()
    found = sorted({(tracks.of_task(t) or '—') for t in (cfg.get('tasks') or {}).values()} | {t['id'] for t in view.tracks})
    own = {t['id'] for t in view.tracks if t['root']}
    return [(p, _root_of(cfg, view, p), p in own) for p in found]


def cmd_status(cfg, view=None):
    print('Корені напрямків:')
    for track, root, own in roots_in_use(cfg, view):
        mark = '✅ свій корінь' if own else '⚠️ тека простору (свого кореня немає)'
        print(f'   {track:10} → {root}  [{mark}]')
    moves = plan(cfg, view)
    if not moves:
        print('Усі задачі лежать у корені свого напрямку.')
        return 0
    print(f'\nНе на своєму місці: {len(moves)}')
    for tid, track, cur, want, stop in moves:
        print(f'   {tid} ({track}): {cur}' + (f' → {want}' if want else '')
              + (f'   ⛔ {stop}' + (' — не чіпаю' if want is None else '') if stop else ''))
    print('\nПереселити: python3 bin/roots.py migrate --apply')
    return 0


def cmd_migrate(cfg, apply, view=None):
    moves = plan(cfg, view)
    if not moves:
        print('Переселяти нічого.')
        return 0
    moved = []
    for tid, track, cur, want, stop in moves:
        if stop:
            print(f'⛔ {tid} ({track}): {stop} — не чіпаю')
            continue
        print(f'{"→" if apply else "буде"} {tid} ({track}): {cur} → {want}')
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

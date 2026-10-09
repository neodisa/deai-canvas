#!/usr/bin/env python3
"""Design Canvas · state: «де ми зараз» по поточній задачі.

Для Claude на ВХОДІ в дизайн-задачу: `python3 bin/state.py` — визначити етап,
щоб продовжити роботу, а НЕ верстати макет з нуля. Показує: ітерації (яка
остання/опублікована), публікацію, стан GitLab (новіше від іншого дизайнера?),
відкриті пін-коментарі.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve import (load_tasks, load_meta, task_iterations, iter_num,  # noqa: E402
                   gitlab_cfg, gitlab_status, supabase_pins, comment_channel,
                   machine_identity, iteration_is_mine, iteration_pages)
import registry  # noqa: E402
import pages_model as pm  # noqa: E402
import urllib.request  # noqa: E402

#: Де шукати живий канвас: `PORT` оточення (так його й піднімають на
#: нестандартному порту), потім типовий 8765 і кілька сусідніх — рівно ті, що
#: брали сесії, коли 8765 був зайнятий.
CANVAS_PORTS = (8765, 8766, 8767, 8768)


def gitlab_line(st, path):
    """Рядок стану GitLab. Чиста функція — тому й перевіряється тестами.

    Порядок гілок несучий. «Ще не в репо» стоїть ВИЩЕ за «синхронізовано», бо це
    найтихіший стан із можливих: наздоганяти нічого (`behind=0`), локально все на
    місці (`dirty=False`) — і до 29.07.2026 він друкувався як «синхронізовано»
    для задач, яких на GitLab не існувало (dobFilter, riskFactors, bgSanctions).
    """
    if st.get('error'):
        return f'GitLab ({path}): помилка — {st["error"]}'
    if st.get('on_remote') is False:
        return (f'GitLab ({path}): ⚠ ЩЕ НЕ В РЕПО — макет ніколи не пушився, '
                f'робота існує в одному екземплярі. У канвасі: «↑ Надіслати Іт.N»')
    if st.get('behind'):
        # ⛔ ДВІ РІЗНІ НОВИНИ. `behind` рахується по ВСЬОМУ репо свідомо (інакше
        # дзеркало йде в non-fast-forward), тому верхній коміт СУСІДНЬОЇ задачі
        # читався як «хтось оновив ТВІЙ макет. Спершу Підтягнути!» — і відправляв
        # тягнути чуже там, де тека задачі байт-у-байт своя (lu-home, 09.09.2026).
        # Розбивки немає (старий статус) — лишаємось гучними: немає факту, немає
        # й підстав заспокоювати.
        if st.get('behind_path') or 'behind_path' not in st:
            return (f'GitLab ({path}): ⚠ на GitLab НОВІШЕ ({st["behind"]}) — '
                    f'хтось (інший дизайнер/машина) оновив макет. Спершу Підтягнути!')
        return (f'GitLab ({path}): репо попереду на {st["behind"]} коміт(ів), але '
                f'теку задачі ніхто не чіпав — пуш не заблокований, дзеркало '
                f'наздожене себе саме')
    if st.get('on_remote') is None:
        # «Не питали» — теж вголос: мовчазне «синхронізовано» тут було б тим самим
        # вигаданим спокоєм, лише з іншої причини.
        return (f'GitLab ({path}): стан невідомий — дзеркало без origin, '
                f'перевір підключення (VPN)')
    tail = ' · є незбережені зміни обраної ітерації' if st.get('dirty') else ''
    return f'GitLab ({path}): синхронізовано{tail}'


def iterations_line(its):
    """Перелік ітерацій рядком. Номер — З ID, а не з позиції в списку.

    Позиційна нумерація (`i + 1`) розходилась із канвасом, `iterations.json` і
    GitLab-синком щоразу, коли ітерацію видаляли: на courts лишилась одна з
    id=it4, і точка входу в задачу друкувала «Іт.1 (остання)» — номер, якого не
    бачить ні дизайнер, ні колеги. Беремо ТОЙ САМИЙ `iter_num`, що й публікація.
    """
    last = its[-1]
    return ', '.join(f'Іт.{iter_num(it["id"])}'
                     f'{" ✓превью" if it.get("published") else ""}'
                     f'{" (остання)" if it["id"] == last["id"] else ""}'
                     for it in its)


def working_iteration(its, my_key=''):
    """Ітерація, в якій працюють: остання СВОЯ (інакше просто остання).

    Один розрахунок на два консументи — рядок «продовжуємо з…» і запит статусу
    GitLab. Доти другий питав про `last['id']`, змінної з таким іменем у
    `main()` не існувало, і рядок роками мовчки ставав «не дістати статус
    (name 'last' is not defined)» — тобто сигнал «на GitLab новіше» не працював
    узагалі (знайдено ревʼю 15.09.2026).
    """
    if not its:
        return None
    mine = [it for it in its if iteration_is_mine(it, my_key)]
    return (mine or its)[-1]


def continue_line(its, my_key=''):
    """Рядок «з чого продовжуємо» — з останньої СВОЄЇ ітерації.

    Остання може бути ЧУЖОЮ: «Підтягнути» заводить пару «чужа + мій форк», а
    між ними на диску може опинитись що завгодно. Вказати на чужу означало б
    відправити дизайнера працювати поверх роботи колеги — рівно те, від чого
    ця пара й рятує.

    `my_key` з дефолтом: функцію кличуть і тести старим способом, одним
    аргументом, і поведінка там мусить лишитись колишньою.
    """
    last = working_iteration(its, my_key)
    foreign = [it for it in its if not iteration_is_mine(it, my_key)]
    mine = [it for it in its if iteration_is_mine(it, my_key)]
    if foreign and not mine:
        # ⛔ Своїх немає ЖОДНОЇ. Сказати тут «продовжуємо з останньої своєї» і
        # тут же назвати ту саму ітерацію чужою — це два протилежні твердження
        # про один обʼєкт, тобто інструмент бреше. Кажемо стан і дію.
        f = foreign[-1]
        who = f.get('author') or f.get('author_key') or 'колега'
        return (f'\n→ СВОЇХ ітерацій немає: остання — Іт.{iter_num(f["id"])} від '
                f'{who}. Працювати поверх чужої не можна: зроби копію '
                f'(POST /api/iteration {{"from": "{f["id"]}"}}) і працюй у ній. '
                'Макет вже є — НЕ верстати з нуля.')
    tail = ''
    if foreign:
        f = foreign[-1]
        who = f.get('author') or f.get('author_key') or 'колега'
        tail = (f'\n  Іт.{iter_num(f["id"])} — {who} (підтягнута, read-only за '
                'домовленістю): дивитись можна, працювати — у своїй.')
    return (f'\n→ ПРОДОВЖУЄМО з Іт.{iter_num(last["id"])} '
            f'({"остання своя" if foreign else "остання"}). '
            'Макет вже є — НЕ верстати з нуля; '
            'відкрити обрану ітерацію і працювати далі.' + tail)


def find_canvas_port(tid, ports=None, timeout=0.4):
    """Порт, на якому живий канвас віддає САМЕ цю задачу, або None.

    Питаємо `/api/task`, а не просто «чи слухає порт»: на сусідньому порту
    може сидіти інша копія інструмента з іншою поточною задачею (так було в
    bf360 на 8766), і адреса звідти відкрила б чужий макет.
    """
    env = os.environ.get('PORT')
    order = ([int(env)] if env and env.isdigit() else []) + [
        p for p in (ports or CANVAS_PORTS) if str(p) != env]
    for port in order:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/task',
                                        timeout=timeout) as res:
                if json.loads(res.read().decode('utf-8')).get('id') == tid:
                    return port
        except (OSError, ValueError):
            continue
    return None


def local_url_line(task, its, my_key, port):
    """Де відкрити робочу ітерацію в браузері, щоб зміряти верстку.

    ⛔ НАВІЩО (fb-22092026-79ae76, 22.09.2026). Маршрут існував завжди
    (`/it-assets/<itN>/<сторінка>/index.html` — статика ітерацій ПОТОЧНОЇ задачі, з
    відносними ассетами), але ніде не був названий, тож сесії вгадували
    `/preview/…`, діставали 404 і піднімали власний `http.server` поверх теки.
    `file://` не годиться — відносні шляхи до ассетів ламаються.

    Порт не вгадуємо: `find_canvas_port` питає живий канвас, чи ця задача в
    нього поточна. Немає — кажемо, що робити, а не друкуємо адресу, яка
    відкриє 404 або чужу задачу.
    """
    work = working_iteration(its, my_key)
    if not work:
        return None
    if port is None:
        return ('Локально: канвас із цією задачею не відповідає (8765…) — '
                'підніми ./start.command і перемкнись на задачу; сторінки '
                'ітерації тоді відкриваються за /it-assets/<itN>/<сторінка>/index.html')
    it = work['id']
    try:
        pages = pm.openable_pages(iteration_pages(task, it))
    except (OSError, ValueError):
        pages = []
    base = f'http://127.0.0.1:{port}'
    if not pages:
        return f'Локально: {base}/it-assets/{it}/index.html'
    first = pages[0]
    rel = pm.page_rel(first)
    # `index.html` — ЯВНО: статика ітерацій індексу теки не віддає, і
    # `/it-assets/it2/` дає 404 (перевірено на живому канвасі 27.09.2026 —
    # перша версія цього рядка друкувала саме таку мертву адресу, і юніт її
    # «підтверджував», бо звіряв рядок, а не маршрут).
    line = (f'Локально (Іт.{iter_num(it)}): {base}/it-assets/{it}/{rel + "/" if rel else ""}index.html'
            f' — сира сторінка «{first.get("name", first["id"])}»')
    if len(pages) > 1:
        line += f' (ще {len(pages) - 1}: /it-assets/{it}/<id сторінки>/index.html)'
    line += (f'\n  з коментатором: {base}/commented?it={it}&page={first["id"]}&ch=local'
             ' · обидві адреси — лише для поточної задачі канваса')
    return line


def _registry_line(cfg):
    """Свежесть локального кеша задач против реестра (источник истины)."""
    try:
        st = registry.staleness(cfg)
    except Exception as e:  # noqa: BLE001 — состояние реестра не должно ронять state
        return f'Реєстр: не дістати стан ({e})'
    age = st['age_h']
    age_s = 'ніколи' if age is None else (f'{age * 60:.0f} хв тому' if age < 1 else f'{age:.1f} год тому')
    icon = {'fresh': '✅', 'stale': '⚠', 'never': '⚠', 'behind': '⬇', 'offline': '⚠'}[st['state']]
    return f'Реєстр: {icon} синк {age_s}' + (f' — {st["hint"]}' if st['hint'] else '')


def _open_pins(project):
    try:
        return len([p for p in supabase_pins(project) if p.get('status') != 'resolved'])
    except Exception:  # noqa: BLE001
        return 0


def _pipeline_version():
    """Версія пайплайну. Пріоритет: VERSION вгору по дереву (у команди design-canvas
    лежить всередині design-office, де є VERSION); інакше — VERSION встановленого
    скіла (те саме джерело, що version_check.py); інакше 'dev'."""
    d = ROOT
    for _ in range(4):
        f = os.path.join(d, 'VERSION')
        if os.path.isfile(f):
            try:
                with open(f, encoding='utf-8') as fh:
                    return fh.read().strip()
            except OSError:
                break
        d = os.path.dirname(d)
    skill_ver = os.path.expanduser('~/.claude/skills/dev-pipeline/VERSION')
    try:
        with open(skill_ver, encoding='utf-8') as fh:
            v = fh.read().strip()
        if v:
            return v
    except OSError:
        pass
    return 'dev'


def main():
    cfg = load_tasks()
    tid = cfg['current']
    task = cfg['tasks'][tid]
    meta = load_meta(task)
    its = task_iterations(task)
    print(f'=== ДЕ МИ ЗАРАЗ · «{task.get("title", tid)}» ({tid}) ===')
    print(f'Пайплайн v{_pipeline_version()} · Профіль: {task.get("profile", "?")}'
          f' · Jira: {task.get("jira", "—")}')
    print(_registry_line(cfg))

    if not its:
        print('Ітерацій ще немає — це нова/порожня задача, можна починати макет.')
        return 0
    print(f'Ітерації ({len(its)}): {iterations_line(its)}')
    if meta.get('publish_url'):
        print(f'Опубліковано: {meta["publish_url"]}'
              f'{" · оновлено " + meta["published_at"] if meta.get("published_at") else ""}')
    else:
        print('Опубліковано: ще ні')

    gl = gitlab_cfg(cfg, task)
    if gl:
        try:
            work = working_iteration(its, machine_identity()[1])
            st = gitlab_status(task, gl, meta, work['id'] if work else None)
            print(gitlab_line(st, gl['path']))
        except Exception as e:  # noqa: BLE001
            print(f'GitLab: не дістати статус ({e})')
    else:
        print('GitLab: не налаштований для задачі')

    lf = os.path.join(task['dir'], '.dc-local-comments.json')
    try:
        ld = json.loads(open(lf, encoding='utf-8').read()) if os.path.isfile(lf) else []
        local = len([p for p in ld if p.get('status') != 'resolved'])
    except (OSError, ValueError):
        local = 0
    external = _open_pins(comment_channel(task, tid))
    print(f'Відкриті коментарі: {local} локальних (мені) + {external} проєктних'
          f'{" → python3 bin/inbox.py" if local + external else ""}')

    loc = local_url_line(task, its, machine_identity()[1], find_canvas_port(tid))
    if loc:
        print(loc)

    print(continue_line(its, machine_identity()[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())

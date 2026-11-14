#!/usr/bin/env python3
"""Design Canvas · state: «де ми зараз» по поточній задачі.

Для Claude на ВХОДІ в дизайн-задачу: `python3 bin/state.py` — визначити етап,
щоб продовжити роботу, а НЕ верстати макет з нуля. Показує: ітерації (яка
остання/опублікована), публікацію, стан GitLab (новіше від іншого дизайнера?),
відкриті пін-коментарі.

`--task <id>` — про названу задачу, а не про поточну. Поточна (`tasks.json` →
`current`) одна на машину, і паралельна сесія Claude її перемикає: без явної
назви «де ми зараз» раптом розповідає про ЧУЖУ задачу (fb-07102026-e627c2).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve import (registry_allowed, load_tasks, load_meta, task_iterations, iter_num,  # noqa: E402
                   vcs_task, _mask_repo, gitlab_status,
                   machine_identity, iteration_is_mine, iteration_pages,
                   task_anywhere, UnknownTask, TaskNotHere, NoTask, AmbiguousTask,
                   SpaceUnavailable, ProjectComments, for_agent)
import spaces  # noqa: E402
import tracks  # noqa: E402
import registry  # noqa: E402
import pages_model as pm  # noqa: E402
import shlex  # noqa: E402
import urllib.request  # noqa: E402
from urllib.parse import quote  # noqa: E402

#: Де шукати живий канвас: `PORT` оточення (так його й піднімають на
#: нестандартному порту), потім типовий 8765 і кілька сусідніх — рівно ті, що
#: брали сесії, коли 8765 був зайнятий.
CANVAS_PORTS = (8765, 8766, 8767, 8768)


def _api_prefix(tid):
    """`/t/<id>` для підказок із ЕНДПОЇНТОМ, які копіюють дослівно; порожній, коли
    задачу не названо. Без префікса `POST /api/…` б'є в ПОТОЧНУ задачу машини —
    тобто після `--task beta` підказка форкала б чужу задачу (ревʼю 12.10.2026)."""
    return f'/t/{quote(tid, safe="")}' if tid is not None else ''


def _busy_line(label, path):
    """Дзеркало зайняте (`vcs-busy`): лок тримають і відправка, і отримання, і перший клон. Це «спробуй ще раз», а не помилка."""
    return f'{label} ({path}): зайнято (іде синхронізація), спробуй ще раз'


def gitlab_line(st, path, tid=None, label='GitLab'):
    """Рядок стану синку з git. Чиста функція — тому й перевіряється тестами.

    `label` — підпис віддаленого репо (`GitLab` у просторі ЛІГА й для старих викликів, `Git`/`GitHub`… — те, що каже `label`
    статусу модуля): у кожному рядку замість слова «GitLab». Підказки з ендпоїнтом (`/api/vcs-push`, `/api/vcs-pull`)
    ведуть на нові адреси; старі `/api/gitlab-*` — застарілі псевдоніми, вони діють до 1.0.

    `tid` — задачу НАЗВАНО (`--task`): підказки з ендпоїнтом несуть префікс
    `/t/<id>/`, а кнопки канваса названі як діючі на ПОТОЧНУ задачу канваса.

    Порядок гілок несучий. «Ще не в репо» стоїть ВИЩЕ за «синхронізовано», бо це
    найтихіший стан із можливих: наздоганяти нічого (`behind=0`), локально все на
    місці (`dirty=False`) — і до 29.07.2026 він друкувався як «синхронізовано»
    для задач, яких на GitLab не існувало (dobFilter, riskFactors, bgSanctions).
    """
    if st.get('code') == 'vcs-busy':
        return _busy_line(label, path)
    if st.get('error'):
        return f'{label} ({path}): помилка — {_mask_repo(st["error"])}'
    if st.get('on_remote') is False:
        if tid is not None:
            # Кнопка в канвасі діє на ПОТОЧНУ задачу канваса, а не на названу.
            send = (f'POST {_api_prefix(tid)}/api/vcs-push {{"it": "itN"}} '
                    '(кнопка «↑ Надіслати Іт.N» в канвасі діє на поточну задачу '
                    'канваса, не на названу)')
        else:
            send = 'У канвасі: «↑ Надіслати Іт.N»'
        return (f'{label} ({path}): ⚠ ЩЕ НЕ В РЕПО — макет ніколи не пушився, '
                f'робота існує в одному екземплярі. {send}')
    if st.get('behind'):
        # ⛔ ДВІ РІЗНІ НОВИНИ. `behind` рахується по ВСЬОМУ репо свідомо (інакше
        # дзеркало йде в non-fast-forward), тому верхній коміт СУСІДНЬОЇ задачі
        # читався як «хтось оновив ТВІЙ макет. Спершу Підтягнути!» — і відправляв
        # тягнути чуже там, де тека задачі байт-у-байт своя (lu-home, 09.09.2026).
        # Розбивки немає (старий статус) — лишаємось гучними: немає факту, немає
        # й підстав заспокоювати.
        if st.get('behind_path') or 'behind_path' not in st:
            pull = (f' (POST {_api_prefix(tid)}/api/vcs-pull)' if tid is not None
                    else '')
            return (f'{label} ({path}): ⚠ на {label} НОВІШЕ ({st["behind"]}) — '
                    f'хтось (інший дизайнер/машина) оновив макет. '
                    f'Спершу Підтягнути!{pull}')
        return (f'{label} ({path}): репо попереду на {st["behind"]} коміт(ів), але '
                f'теку задачі ніхто не чіпав — пуш не заблокований, дзеркало '
                f'наздожене себе саме')
    if st.get('on_remote') is None:
        # «Не питали» — теж вголос: мовчазне «синхронізовано» тут було б тим самим
        # вигаданим спокоєм, лише з іншої причини.
        return (f'{label} ({path}): стан невідомий — дзеркало без origin, '
                f'перевір підключення (VPN)')
    tail = ' · є незбережені зміни обраної ітерації' if st.get('dirty') else ''
    return f'{label} ({path}): синхронізовано{tail}'


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


def continue_line(its, my_key='', tid=None):
    """Рядок «з чого продовжуємо» — з останньої СВОЄЇ ітерації.

    Остання може бути ЧУЖОЮ: «Підтягнути» заводить пару «чужа + мій форк», а
    між ними на диску може опинитись що завгодно. Вказати на чужу означало б
    відправити дизайнера працювати поверх роботи колеги — рівно те, від чого
    ця пара й рятує.

    `my_key` з дефолтом: функцію кличуть і тести старим способом, одним
    аргументом, і поведінка там мусить лишитись колишньою.

    `tid` — задачу НАЗВАНО (`--task`): ендпоїнт у підказці несе префікс `/t/<id>/`.
    Без нього скопійований дослівно `POST /api/iteration` форкав би ПОТОЧНУ задачу
    машини, а не названу.
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
                f'(POST {_api_prefix(tid)}/api/iteration {{"from": "{f["id"]}"}}) і працюй у ній. '
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


def find_canvas_port(tid, ports=None, timeout=0.4, explicit=False):
    """Порт, на якому живий канвас віддає САМЕ цю задачу, або None.

    Питаємо `/api/task`, а не просто «чи слухає порт»: на сусідньому порту
    може сидіти інша копія інструмента з іншою поточною задачею (так було в
    bf360 на 8766), і адреса звідти відкрила б чужий макет.

    `explicit` — задачу НАЗВАНО (`--task`): тоді питаємо про неї ПРЕФІКСОМ,
    `/t/<id>/api/task`, а не заголовком `X-Canvas-Task`. Без цього `/api/task`
    відповідає про поточну задачу канваса, і названа, але не поточна, виглядала б
    «канвас не відповідає». Саме префікс, бо адреси, які ми друкуємо далі, теж із
    префіксом: старий (не перезапущений) канвас заголовка не знає й відповів би
    про ПОТОЧНУ, тобто «підійшов» би, а його `/t/<id>/…` дав би 404. Невідома там
    задача — 404 (це `OSError`), порт пропускаємо. Без `explicit` префікса немає
    свідомо: порт підходить лише тоді, коли ТАМ поточна саме ця задача — бо адреси
    без префікса `/t/<id>/` відкривають поточну.
    """
    env = os.environ.get('PORT')
    order = ([int(env)] if env and env.isdigit() else []) + [
        p for p in (ports or CANVAS_PORTS) if str(p) != env]
    path = f'{_api_prefix(tid)}/api/task' if explicit else '/api/task'
    for port in order:
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{port}{path}')
            with urllib.request.urlopen(req, timeout=timeout) as res:
                if json.loads(res.read().decode('utf-8')).get('id') == tid:
                    return port
        except (OSError, ValueError):
            continue
    return None


def local_url_line(task, its, my_key, port, tid=None):
    """Де відкрити робочу ітерацію в браузері, щоб зміряти верстку.

    ⛔ НАВІЩО (fb-22092026-79ae76, 22.09.2026). Маршрут існував завжди
    (`/it-assets/<itN>/<сторінка>/index.html` — статика ітерацій ПОТОЧНОЇ задачі, з
    відносними ассетами), але ніде не був названий, тож сесії вгадували
    `/preview/…`, діставали 404 і піднімали власний `http.server` поверх теки.
    `file://` не годиться — відносні шляхи до ассетів ламаються.

    Порт не вгадуємо: `find_canvas_port` питає живий канвас, чи ця задача в
    нього поточна. Немає — кажемо, що робити, а не друкуємо адресу, яка
    відкриє 404 або чужу задачу.

    `tid` — задачу НАЗВАНО (`--task`): адреси несуть префікс `/t/<id>/`. Без
    нього вони відкривають ПОТОЧНУ задачу канваса, тобто після `--task beta`
    вели б у чужий макет, щойно інша сесія перемкне канвас.
    """
    work = working_iteration(its, my_key)
    if not work:
        return None
    if port is None:
        if tid is not None:
            # Названа задача: перемикати канвас НЕ треба — префікс `/t/<id>/`
            # відкриває її за будь-якої поточної. Треба лише, щоб канвас ЖИВ.
            return ('Локально: канвас не відповідає (8765…) — підніми ./start.command; '
                    'перемикатись на задачу не треба, адреси з префіксом /t/<id>/ '
                    'відкривають названу; сторінки ітерації тоді — '
                    f'{_api_prefix(tid)}/it-assets/<itN>/<сторінка>/index.html')
        return ('Локально: канвас із цією задачею не відповідає (8765…) — '
                'підніми ./start.command і перемкнись на задачу; сторінки '
                'ітерації тоді відкриваються за /it-assets/<itN>/<сторінка>/index.html')
    it = work['id']
    try:
        pages = pm.openable_pages(iteration_pages(task, it))
    except (OSError, ValueError):
        pages = []
    prefix = _api_prefix(tid)
    base = f'http://127.0.0.1:{port}{prefix}'
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
        line += f' (ще {len(pages) - 1}: {prefix}/it-assets/{it}/<id сторінки>/index.html)'
    if tid is None:
        line += (f'\n  з коментатором: {base}/commented?it={it}&page={first["id"]}&ch=local'
                 ' · обидві адреси — лише для поточної задачі канваса')
    else:
        # ⛔ `/t/<id>/commented` без `bare=1` сервер відхиляє (400): коментатор пише
        # піни на `/api/local-comments` без префікса, тобто в локальні коментарі
        # ПОТОЧНОЇ задачі, а не названої. Друкувати адресу, що веде в 400, не
        # можна — лишаємо те, що працює, і кажемо, куди йти коментувати.
        line += (f'\n  коментувати — у канвасі: http://127.0.0.1:{port}/app/ (вікно поточної '
                 'задачі канваса; під названою задачею коментатора нема) · адреса '
                 'сторінки вище з префіксом /t/<id>/ від поточної не залежить')
    return line


def _registry_line(cfg):
    """Свежесть локального кеша задач против реестра (источник истины).

    Простір без схеми ЛІГИ: реєстру команди для нього нема, рядок не друкується (порожній) і
    `registry.staleness` — а це `git ls-remote` — не кличеться."""
    if not registry_allowed():
        return ''
    try:
        st = registry.staleness(cfg)
    except Exception as e:  # noqa: BLE001 — состояние реестра не должно ронять state
        return f'Реєстр: не дістати стан ({e})'
    age = st['age_h']
    age_s = 'ніколи' if age is None else (f'{age * 60:.0f} хв тому' if age < 1 else f'{age:.1f} год тому')
    icon = {'fresh': '✅', 'stale': '⚠', 'never': '⚠', 'behind': '⬇', 'offline': '⚠'}[st['state']]
    return f'Реєстр: {icon} синк {age_s}' + (f' — {st["hint"]}' if st['hint'] else '')


def _team_comments(task, tid):
    """`(відкритих проєктних, хвіст рядка «Відкриті коментарі»)`.

    Хто веде командні коментарі, вирішує постачальник ролі `comments` ПРОСТОРУ задачі (`ProjectComments`; простір —
    явним записом `spaces.active_space()`, який зафіксував `task_anywhere`), а не прапорця `integrations`: у просторі з модулем
    коментарів вони є й без інтеграцій, а ЛІГА з модулем, що не завантажився, не має права йти в спільний Supabase.
    ЛІГА — тим самим модулем `supabase-comments` (явний запис, 4b-2): Supabase, що не відповів, — «не дістати (<код>)», а не
    тихий «0» (свідома відмінність від 0.9.0); простір без інтеграцій — «проєктних нема», без мережі."""
    try:
        pc = ProjectComments(spaces.active_space())
    except Exception as e:  # noqa: BLE001 — реєстр не прочитати: рішення «звідки» невідоме, а не «0» і не Supabase
        return 0, f', проєктні: не дістати ({getattr(e, "code", type(e).__name__)})'
    if pc.kind == 'module':                       # `kind` — внутрішній рядок `ProjectComments`, не значення постачальника
        try:
            pins = pc.pins(task, tid)
            open_ = [p for p in pins if p.get('status') != 'resolved']
            n = len([p for p in open_ if for_agent(p, 'project')])
            k = len(open_) - n
        except spaces.RoleOff:      # ЛІГА без інтеграцій: командних коментарів нема, мережі не було
            return 0, ', проєктних нема'
        except Exception as e:  # noqa: BLE001 — модуль не відповів: «0» читалось би як «тихо», а це «не дістати»
            code = getattr(e, 'code', type(e).__name__)
            if code == 'comments-unconfigured':      # установка без конфігу Supabase — не збій, а «не налаштовано»
                return 0, ', проєктні: Supabase не налаштовано'
            if code == 'comments-isolated':      # закон ізоляції (4d-4b): тестовий запуск не ходить у спільний проєкт — не збій
                return 0, ', проєктні: спільні коментарі вимкнено в ізольованому (тестовому) запуску'
            return 0, f', проєктні: не дістати ({code})'
        # Те, що не ввійшло (зіпсовані елементи, понад межу), — у тому ж рядку: «N відкритих» без цього збрехало б.
        note = pins.note() if hasattr(pins, 'note') else ''
        return n, (f' + {n} проєктних (доручено Claude)' + (f'; ще {k} командних без доручення' if k else '')
                   + (f' (⚠ {note})' if note else ''))
    if pc.kind == 'broken':
        return 0, f', проєктні: не дістати ({pc.err.code})'
    return 0, ', проєктних нема'


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


def build_parser():
    ap = argparse.ArgumentParser(
        prog='state.py',
        description='Де ми зараз по задачі: ітерації, публікація, GitLab, '
                    'відкриті коментарі. Без аргументів — про поточну задачу.')
    ap.add_argument('--task', metavar='ID',
                    help='задача з tasks.json замість поточної — для паралельних сесій')
    return ap


def main(argv=None):
    # Простір, який `task_anywhere` фіксує на потоці, не сміє пережити команду: `main()` кличуть
    # і в процесі (тести, інші скрипти), а потік — той самий.
    try:
        return _main(argv)
    finally:
        spaces.clear_request_space()


def _main(argv):
    a = build_parser().parse_args(argv)
    # СПЕРШУ задача (вона ж фіксує простір), ПОТІМ `load_tasks()`: інакше конфіг читався б
    # з поточного простору машини, а названа задача жила б в іншому.
    try:
        tid, task = task_anywhere(a.task, load=load_tasks)
        cfg = load_tasks()
    except TaskNotHere:
        # Назва ЯВНА, тож відкат на поточну неприпустимий; і «нова/порожня
        # задача» тут була б брехнею: задача є, лише теки на цій машині нема.
        print(f"error: задачі '{a.task}' немає на цій машині "
              '(є в реєстрі, теки нема)', file=sys.stderr)
        return 2
    except UnknownTask:
        print(f'error: немає задачі {a.task!r} у tasks.json', file=sys.stderr)
        return 2
    except NoTask as e:
        # «Створи простір» тут брехало б, коли задачі є в інших просторах (див. `no_task_message`).
        print(f'error: {spaces.no_task_message(e)}', file=sys.stderr)
        return 2
    except AmbiguousTask:
        print(f'error: задача {a.task!r} є в кількох просторах — перейменуй одну з них '
              '(або онови id в tasks.json простору)', file=sys.stderr)
        return 2
    except (SpaceUnavailable, spaces.SpacesError) as e:
        print(f'error: простір недоступний — {e}', file=sys.stderr)
        return 2
    named = a.task is not None      # назва ЯВНА: адреси й підказки її повторюють
    meta = load_meta(task)
    its = task_iterations(task)
    print(f'=== ДЕ МИ ЗАРАЗ · «{task.get("title", tid)}» ({tid}) ===')
    print(f'Пайплайн v{_pipeline_version()} · Напрямок: {tracks.of_task(task) or "—"}'
          f' · Jira: {task.get("jira", "—")}')
    line = _registry_line(cfg)
    if line:                        # порожній рядок друкувати нічого
        print(line)

    if not its:
        print('Ітерацій ще немає — це нова/порожня задача, можна починати макет.')
        return 0
    print(f'Ітерації ({len(its)}): {iterations_line(its)}')
    if meta.get('publish_url'):
        print(f'Опубліковано: {meta["publish_url"]}'
              f'{" · оновлено " + meta["published_at"] if meta.get("published_at") else ""}')
    else:
        print('Опубліковано: ще ні')

    # Синк із git — за РОЛЛЮ `vcs` простору, а не за інтеграціями: звичайний простір із `git-sync` синкає так само. Ролі нема
    # (простір без модуля) — «не налаштований», як для задачі без цілі; GitLab-маппінг у файлі такого простору ігнорується.
    try:
        vcs = vcs_task(tid, task)
    except OSError as e:            # `VcsError` — відмова постачальника; решта `OSError` — теж не traceback у точці входу в задачу
        vcs, vcs_err = None, e
    else:
        vcs_err = None
    label = 'Git' if vcs and not vcs[2] else 'GitLab'
    if vcs and vcs[3]:
        path = vcs[3]['path']
        try:
            work = working_iteration(its, machine_identity()[1])
            st = gitlab_status(task, vcs[3], meta, work['id'] if work else None, vcs=vcs[:3])
            print(gitlab_line(st, path, tid if named else None, label=st.get('label') or label))
        except Exception as e:  # noqa: BLE001
            if getattr(e, 'code', None) == 'vcs-busy':
                print(_busy_line(label, path))
            else:
                print(f'{label}: не дістати статус ({_mask_repo(str(e))})')
    elif vcs_err is not None and (task.get('gitlab') or task.get('vcs')):
        print(f'{label}: не дістати статус ({_mask_repo(str(vcs_err))})')
    else:
        # Постачальник відмовив, а в задачі нема ні `gitlab`, ні `vcs`: цій задачі нічого не належало, «не дістати статус» —
        # брехня (і крик на кожній задачі при зламаному каталозі). Ціль лише в налаштуваннях модуля тут не видно: постачальника нема.
        print(f'{label}: не налаштований для задачі')

    lf = os.path.join(task['dir'], '.dc-local-comments.json')
    try:
        ld = json.loads(open(lf, encoding='utf-8').read()) if os.path.isfile(lf) else []
        local = len([p for p in ld if p.get('status') != 'resolved'])
    except (OSError, ValueError):
        local = 0
    # Без інтеграцій командних коментарів нема: «нема», а не «+ 0» (нуль читався б як «питали — тихо»).
    external, team_part = _team_comments(task, tid)
    # Підказку копіюють дослівно: без `--task` вона відкрила б інбокс ПОТОЧНОЇ задачі.
    inbox_cmd = 'python3 bin/inbox.py' + (f' --task {shlex.quote(tid)}' if named else '')
    print(f'Відкриті коментарі: {local} локальних (мені){team_part}'
          f'{" → " + inbox_cmd if local + external else ""}')

    loc = local_url_line(task, its, machine_identity()[1],
                         find_canvas_port(tid, explicit=named), tid if named else None)
    if loc:
        print(loc)

    print(continue_line(its, machine_identity()[1], tid if named else None))
    return 0


if __name__ == '__main__':
    sys.exit(main())

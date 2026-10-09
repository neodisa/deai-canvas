#!/usr/bin/env python3
"""Структура сторінок ітерації — для Claude (і людей у терміналі).

⛔ pages.json руками НЕ переписувати: дизайнер організовує дерево в панелі
(теки, групування, перетягування), і перезапис файла цілком молча знищить його
теки. Ця команда додає/переносить вузол у НАЯВНЕ дерево під тим самим
міжпроцесним локом, що й сервер канваса (`pages_model.pages_lock`).

  pages.py list  --task-dir D --it itN
  pages.py add   --task-dir D --it itN --kind page|state|folder --name "…" [--into ID] [--after ID]
  pages.py move  --task-dir D --it itN --id ID (--into ID | --after ID | --root)
  pages.py rename --task-dir D --it itN --id ID --name "…"
  pages.py kind  --task-dir D --it itN --id ID --kind page|state

`--task-dir` — тека задачі (та, де лежить `iterations/`). Порушення правил →
код виходу 2 і `error <код>: <текст>` у stderr; дерево не змінюється. Так само
помилки вводу/виводу (`error io`). Не вказані обовʼязкові прапорці — повідомлення
самого argparse, теж код 2.

`move` вимагає РІВНО одну ціль: `--into`, `--after` або `--root` (кінець кореня);
без цілі вузол мовчки опинявся б у корені. `add` без цілі кладе в кінець кореня.
`--after` ставить вузол наступним сусідом `ID` у його батька; разом з `--into`
(лише для `add`) батько `ID` мусить збігатися з `--into`.
Успіх друкує JSON: add `{id, kind}`, move `{id, parent, index, changed}`,
rename `{id, name}`, kind `{id, kind}`.
Таймаут очікування лока — env `DC_PAGES_LOCK_TIMEOUT` (секунди; для тестів).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import pages_model as pm  # noqa: E402


# Те саме правило, що `serve.NAME_RE` для імені ітерації (там `fullmatch`, бо `$`
# пропускає імʼя з переносом): без `/` і `..` --it не вийде за теку iterations.
_IT_RE = re.compile(r'[\w-]+')


def _iter_dir(a):
    if not _IT_RE.fullmatch(a.it):
        raise pm.TreeError('bad-iteration', f'bad iteration name: {a.it!r}')
    return os.path.join(a.task_dir, 'iterations', a.it)


def _position(pages, into, after, moving=()):
    """(parent, index) для --into/--after: одразу після `after` серед його
    сусідів, інакше в кінець `into` (або кореня).

    ⚠️ Індекс `op_move` рахується серед дітей ПІСЛЯ виймання, тож рухомі вузли
    (`moving`) із сусідів викидаємо: інакше перенос уперед у межах одного батька
    ставив би вузол на місце раніше, ніж просили."""
    if after:
        if after in moving:
            raise pm.TreeError('bad-position', f'--after cannot be the moved node: {after}')
        path = pm.path_of(pages, after)
        if not path:
            raise pm.TreeError('not-found', f'no such id: {after}')
        parent = path[-2]['id'] if len(path) > 1 else None
        if into and into != parent:
            raise pm.TreeError('bad-position', f'--after {after} is not inside --into {into}')
        _, sibs = pm.find_page(pages, after)
        rest = [s for s in sibs if s.get('id') not in moving]
        return parent, next(i for i, s in enumerate(rest) if s is path[-1]) + 1
    return (into or None), 10 ** 9


def cmd_list(a):
    # read_pages на неіснуючій теці мовчки дає [] — «порожня ітерація», і list
    # опечатку в --it видав би за правду. Мутації це ловлять локом (not-found).
    if not os.path.isdir(_iter_dir(a)):
        raise pm.TreeError('not-found', f'no such iteration: {a.it}')
    for f in pm.flatten(pm.read_pages(_iter_dir(a))):
        print(f"{'  ' * f['depth']}{f['page']['id']}  [{f['kind']}]  {f['page']['name']}")


def cmd_add(a):
    idir = _iter_dir(a)
    with pm.pages_lock(idir):
        # ⛔ Усередині одного лока: `mutate` і `pages_lock` не вкладаються
        # (RuntimeError), тож тут читаємо/пишемо напряму — `write_pages` лока
        # не бере.
        pages = pm.read_pages(idir)
        parent, index = _position(pages, a.into, a.after)
        if a.kind == 'folder':
            new, node = pm.op_add_folder(pages, a.name, parent=parent, index=index)
            pm.write_pages(idir, new)
        else:
            # ОДИН запис: з `--after` позицію віддаємо самому add_page. Два записи
            # лишали б у .bak проміжний стан (вузол у кінці батька), а відмова
            # другого лишала б вузол не там, де обіцяно «дерево не змінено».
            pages, node = pm.add_page(idir, pages, a.name, parent_id=parent,
                                      kind=a.kind, index=index if a.after else None)
    print(json.dumps({'id': node['id'], 'kind': node['kind']}, ensure_ascii=False))


def cmd_move(a):
    if bool(a.into) + bool(a.after) + bool(a.root) != 1:
        raise pm.TreeError('bad-position', 'move needs exactly one of --into, --after, --root')

    def change(pages):
        parent, index = (None, 10 ** 9) if a.root else _position(
            pages, a.into, a.after, moving=(a.id,))
        new = pm.op_move(pages, [a.id], parent, index)
        path = pm.path_of(new, a.id)
        _, sibs = pm.find_page(new, a.id)
        where = {'parent': path[-2]['id'] if len(path) > 1 else None,
                 'index': next(i for i, s in enumerate(sibs) if s is path[-1])}
        return new, where
    where, _, changed = pm.mutate(_iter_dir(a), change, with_rev=True)
    print(json.dumps({'id': a.id, **where, 'changed': changed}, ensure_ascii=False))


def cmd_rename(a):
    idir = _iter_dir(a)
    with pm.pages_lock(idir):
        pages = pm.rename_page(idir, pm.read_pages(idir), a.id, a.name)
        name = pm.find_page(pages, a.id)[0]['name']
    print(json.dumps({'id': a.id, 'name': name}, ensure_ascii=False))


def cmd_kind(a):
    pm.mutate(_iter_dir(a), lambda pages: (pm.op_set_kind(pages, a.id, a.kind), None))
    print(json.dumps({'id': a.id, 'kind': a.kind}, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    def base(name):
        p = sub.add_parser(name)
        p.add_argument('--task-dir', required=True)
        p.add_argument('--it', required=True)
        return p
    base('list')
    p = base('add')
    p.add_argument('--kind', required=True, choices=['page', 'state', 'folder'])
    p.add_argument('--name', required=True)
    p.add_argument('--into')
    p.add_argument('--after')
    p = base('move')
    p.add_argument('--id', required=True)
    p.add_argument('--into')
    p.add_argument('--after')
    p.add_argument('--root', action='store_true', help='в кінець кореня')
    p = base('rename')
    p.add_argument('--id', required=True)
    p.add_argument('--name', required=True)
    p = base('kind')
    p.add_argument('--id', required=True)
    p.add_argument('--kind', required=True, choices=['page', 'state'])
    a = ap.parse_args(argv)
    try:
        if os.environ.get('DC_PAGES_LOCK_TIMEOUT'):
            pm.LOCK_TIMEOUT = float(os.environ['DC_PAGES_LOCK_TIMEOUT'])
        {'list': cmd_list, 'add': cmd_add, 'move': cmd_move,
         'rename': cmd_rename, 'kind': cmd_kind}[a.cmd](a)
    except ValueError as e:
        print(f"error {getattr(e, 'code', 'bad-request')}: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f'error io: {e}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

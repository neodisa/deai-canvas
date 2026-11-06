#!/usr/bin/env python3
"""Міграція простору ЛІГА (етап 4d-3a): стан, прогноз, запуск, відкат.

    python3 bin/migrate_liga.py status                       # позначка, останній звіт, бекапи
    python3 bin/migrate_liga.py dry-run                      # що мігрувало б (нічого не пише)
    python3 bin/migrate_liga.py run                          # виконати (бекап → секрети → space.json)
    python3 bin/migrate_liga.py restore <бекап> [--hold]     # повернути space.json і секрети ЛІГИ з бекапу (поточні — у backups/<бекап>-pre-restore)

Вихід 0 — успіх, 1 — інакше. ⛔ Друкує лише коди, імена ролей і ключів; значень секретів і адрес — ніколи.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import liga_migrate  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog='migrate_liga.py', description='Міграція простору ЛІГА (4d-3a)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    sub.add_parser('dry-run')
    sub.add_parser('run')
    r = sub.add_parser('restore')
    r.add_argument('stamp')
    r.add_argument('--hold', action='store_true', help='після відкату не мігрувати на наступному старті')
    a = ap.parse_args(argv)
    if a.cmd == 'status':
        print(liga_migrate.status_text(liga_migrate.status()))
        return 0
    if a.cmd == 'dry-run':
        code = 0
        for step in liga_migrate.STEPS:                      # кожен крок рахується на ПОТОЧНОМУ диску (нічого не пишемо)
            p = liga_migrate.plan(step=step)
            print(liga_migrate.report(p, step))
            code = 1 if p['status'].startswith('abort-') else code
        return code
    if a.cmd == 'run':
        code = 0
        for step in liga_migrate.STEPS:
            st, info = liga_migrate._run(None, step)
            print('%s: %s' % (step.mark, st))
            print('  ' + str(info.get('reason') or ''))
            if info.get('hint'):
                print('  що робити: ' + str(info['hint']))
            if st == 'done':
                tr = ('; напрямки: ' + ('так' if info.get('tracks') else 'ні')) if step.tracks else ''     # лише крок з напрямками
                print('  ролі: %s%s; бекап: %s' % (', '.join(info.get('roles') or []) or '-', tr, info.get('backup')))
                print('  відкат: python3 bin/migrate_liga.py restore %s [--hold]' % info.get('backup'))
            if st not in liga_migrate.BENIGN:
                code = 1
            if st.startswith('abort-') or st == 'skip-busy':     # як на старті: `abort-*`/`skip-busy` зупиняють наступні кроки
                break
        return code
    step = liga_migrate.step_of_stamp(a.stamp) or liga_migrate.ALL_STEPS[0]     # крок визначає імʼя бекапу
    st, info = liga_migrate._restore(a.stamp, hold=a.hold)
    print('%s restore: %s' % (step.mark, st))
    if st == 'restored':
        print('  запобіжна копія поточних space.json і секретів ЛІГИ (до відкату): backups/%s' % info.get('safety_copy'))
    if st == 'refuse-later-applied':
        print('  пізніший крок застосований: спершу відкотіть його бекап%s' % (
            ': python3 bin/migrate_liga.py restore %s [--hold]' % info['rollback_first'] if info.get('rollback_first') else ''))
    return 0 if st == 'restored' else 1


if __name__ == '__main__':
    sys.exit(main())

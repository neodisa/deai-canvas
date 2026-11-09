#!/usr/bin/env python3
"""Міграція простору ЛІГА (етап 4d-3a): стан, прогноз, запуск, відкат.

    python3 bin/migrate_liga.py status                       # позначка, останній звіт, бекапи
    python3 bin/migrate_liga.py dry-run                      # що мігрувало б (нічого не пише)
    python3 bin/migrate_liga.py run                          # виконати (бекап → секрети → space.json)
    python3 bin/migrate_liga.py restore <бекап> [--hold]     # повернути space.json і секрети ЛІГИ з бекапу (поточні — у backups/<бекап>-pre-restore)
    python3 bin/migrate_liga.py unhold <позначка>            # зняти `held` кроку (liga-4d4a…), щоб наступний запуск його виконав

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
    u = sub.add_parser('unhold')
    u.add_argument('mark', help='позначка кроку, напр. liga-4d4a')
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
        stamps_done = []
        for step in liga_migrate.STEPS:
            st, info = liga_migrate._run(None, step)
            print('%s: %s' % (step.mark, st))
            print('  ' + str(info.get('reason') or ''))
            if info.get('hint'):
                print('  що робити: ' + str(info['hint']))
            if st == 'done':
                if step.originals:                                       # 4d-4b: ролей нема — що скопійовано, видалено й лишилось (імена ключів)
                    print('  %s; бекап: %s' % (liga_migrate.originals_summary(info), info.get('backup')))
                elif step.ungated:                                       # 4d-4a: ролей нема — підсумок напрямків, записів і нотаток
                    print('  %s; бекап: %s' % (liga_migrate.summary_line(info), info.get('backup')))
                else:
                    tr = ('; напрямки: ' + ('так' if info.get('tracks') else 'ні')) if step.tracks else ''     # лише крок з напрямками
                    print('  ролі: %s%s; бекап: %s' % (', '.join(info.get('roles') or []) or '-', tr, info.get('backup')))
                stamps_done.append(info.get('backup'))
            elif step.ungated and not step.originals and liga_migrate.tracks_not_migrated(st):
                print('  ' + liga_migrate.TRACKS_NOT_MIGRATED)
            if st not in liga_migrate.BENIGN:
                code = 1
            if st.startswith('abort-') or st == 'skip-busy':     # як на старті: `abort-*`/`skip-busy` зупиняють наступні кроки
                break
        if stamps_done:                                          # ⛔ LIFO: підказка відкату — одна, для найпізнішого виконаного кроку
            print('  відкат: python3 bin/migrate_liga.py restore %s [--hold]' % stamps_done[-1])
            if len(stamps_done) > 1:
                print('  раніші кроки (%s) — лише після відкату пізніших, у зворотному порядку' % ', '.join(stamps_done[:-1]))
        return code
    if a.cmd == 'unhold':
        st = liga_migrate.unhold(a.mark)
        print('%s unhold: %s' % (a.mark, st))
        if st == 'unheld':
            print('  наступний запуск виконає крок: python3 bin/migrate_liga.py run')
        else:
            why = {
                'refuse-mark': 'невідома позначка; чинні: ' + ', '.join(s.mark for s in liga_migrate.ALL_STEPS),
                'refuse-not-held': 'крок не утримано (позначка не «вимкнено вручну») — знімати нічого',
                'refuse-no-liga': 'простору ЛІГА в реєстрі нема',
                'skip-layer-off': 'шар просторів вимкнено',
                'abort-unhold': 'не вдалося зняти утримання (space.json не читається чи не пишеться): перевірте файл простору ЛІГА',
                'skip-busy': 'міграцію зараз виконує інший процес: повторіть за мить',
                'abort-lock': 'не вдалося взяти замок міграції: перевірте теку migrations/ у домі Deai',
                'abort-internal': 'home не збігається з DEAI_HOME',
            }.get(st)
            if why:
                print('  ' + why)
        return 0 if st == 'unheld' else 1
    step = liga_migrate.step_of_stamp(a.stamp) or liga_migrate.ALL_STEPS[0]     # крок визначає імʼя бекапу
    st, info = liga_migrate._restore(a.stamp, hold=a.hold)
    print('%s restore: %s' % (step.mark, st))
    if st == 'restored':
        print('  запобіжна копія поточних space.json і секретів ЛІГИ (до відкату): backups/%s' % info.get('safety_copy'))
    if st == 'refuse-later-applied':
        print('  пізніший крок застосований: спершу відкотіть його бекап%s' % (
            ': python3 bin/migrate_liga.py restore %s [--hold]' % info['rollback_first'] if info.get('rollback_first') else ''))
    if st == 'refuse-tasks-unreadable':                      # 4d-4b: живий tasks.json не читається — відкат кроку Е нічого не записав
        print('  живий tasks.json не читається або його нема: виправте файл (чи відновіть його з tasks.json.bak), '
              'а коли файла нема — створіть його (достатньо {}), і повторіть відкат')
    if st == 'restored' and info.get('kept_live'):           # лише імена ключів, значень не друкуємо
        print('  залишено живими (корінь tasks.json): %s' % ', '.join(str(k) for k in info['kept_live']))
    if st == 'restored' and info.get('kept_live_secrets'):
        print('  залишено живими (секрети): %s' % ', '.join(str(k) for k in info['kept_live_secrets']))
    if st == 'restored' and info.get('root_fallback'):
        print('  перелік ключів кореня узято з бекапу (позначка кроку нечитана чи без переліку): повернено всі відсутні оригінали')
    if st == 'restored' and info.get('root_durability_unconfirmed'):
        print('  корінь tasks.json записано, але довговічність не підтверджено (fsync)')
    return 0 if st == 'restored' else 1


if __name__ == '__main__':
    sys.exit(main())

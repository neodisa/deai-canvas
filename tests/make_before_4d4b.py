#!/usr/bin/env python3
"""Генератор знімка поведінки оригіналів і запасного постачальника ЛІГИ на 0.20.0: `tests/fixtures/liga-migration/before-4d4b.json` (етап 4d-4b, Task 1).

Знімок знято ДО змін коду (код = 0.20.0, коміт `0d52a74`, тег `v0.20.0`) і лишається в репо еталоном паритету п'ятого кроку міграції ЛІГИ
(`liga-4d4b`): після 0.21 людина з мігрованою ЛІГОЮ бачить ті самі `capabilities`, пароль превʼю, канали, ключі SSH, що й до кроку, хоч оригінали
кореня `tasks.json` видалено, запасного постачальника (`Implicit`) нема, а закон ізоляції не читає кореня. Тести (`tests/test_liga_migrate_e.py`,
клас `AfterMigrationParity4d4b`) читають JSON, а не переганяють генератор. Запуск на НОВОМУ коді дасть не «до», а «після»: еталон не перезаписувати.

Спільні помічники (`Rig`, `NoNet`, `SocketTripwire`, `Server`, `scrub`, `rel`, `CLEAN`, `_write`, вигадані константи, `_call`) ІМПОРТУЮТЬСЯ з
`make_before_4d3a.py`/`make_before_4d3b.py`: друга копія розійшлась би.

П'ять стендів (усі — НЕізольовані: без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`, шлях власника; ізольований шлях — секція `isolation`):
  * `regular`    — ЛІГА мігрована кроками A–D, усі вісім оригіналів у корені РІВНІ записам;
  * `differs`    — те саме, але записи після міграції відрізняються від кореня (ssh_key, токен Jira, інертний пароль превʼю);
  * `partial`    — те саме, але записів `supabase-teams` і `jira-tracker` нема (часткова міграція);
  * `unmigrated` — ЛІГА з `held` на кроці 4d-3a: ролі веде `Implicit` (еталон таблиці «стало вимкнено»);
  * `plain`      — звичайний простір без інтеграцій.
Секції: `capabilities` (+ `error_path`: нечитабельний `space.json`), `provider` (для простору ЛІГА і для неявного простору запиту), `api`
(`/api/task`: пароль превʼю й гейт, канал; `/api/modules`; `/api/comment-config`; `/api/teams-mute`; `/api/tasks-overview`), `vcs_target` (цілі й
ЕФЕКТИВНІ ключ і IP), `registry_ssh` (ключ git реєстру), `startup_text` (рядки старту), `root_keys` (ключі кореня `tasks.json`),
`isolation` (форми відповідей ізольованого прогону: рядки команди, статуси, мовчання Teams, `ctx` коментарів),
`dashboard_sync` (пуск синку дашборда на всіх п'яти стендах: `<non_isolated|isolated|no_overview>` × `<in_space|implicit_space>` →
`{called, args}`; шпигун на `serve._overview_launch`, реальний `Handler._overview_sync`).

⚠️ ПІДПИСИ 0.20.0: `serve.vcs_target(cfg, tid, task, settings)`, `registry._ssh_key(cfg)`, `serve.preview_password(cfg, task)`; у новому коді —
`vcs_target(tid, task, settings)`, `_ssh_key()`, `preview_password(task, space)`. Тести «після» кличуть нову форму. Не міняти тут.

Запуск (з кореня репо): проти ЗАМОРОЖЕНОЇ копії старого коду:
    D=$(mktemp -d) && git archive v0.20.0 | tar -x -C "$D" && cp tests/make_before_4d4b.py "$D/tests/"
    HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4b.py" --out tests/fixtures/liga-migration/before-4d4b.json
Запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від `0d52a74`, генератор ВІДМОВЛЯЄ (код виходу 2).

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME`, чисте оточення, жодної мережі (розтяжка сокетів + `urlopen`), шпигуни замість
`serve._registry_push`/`serve.git_autocommit`/`Handler._overview_sync`; справжній `~/.deai` стереже `spaces_guard`; порти 8765/4317 не
чіпаємо (ефемерний порт loopback). Детермінований: два прогони побайтово однакові (часові штампи бекапів замінено `<stamp>`).
"""
import argparse
import io
import json
import contextlib
import os
import re
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

from make_before_4d3a import (CLEAN, JIRA_BASE, JIRA_ENV_EMAIL, JIRA_ENV_TOKEN, SB_KEY, SB_URL, SPACE_ID, NoNet, Rig, Server,  # noqa: E402
                              SocketTripwire, _write, rel, scrub)
from make_before_4d3b import _call  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
STANDS = ('regular', 'differs', 'partial', 'unmigrated', 'plain')
ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')
SSH, HOSTIP, PW = '~/.ssh/example', '203.0.113.7', 'pw-alpha'
STAMP = re.compile(r'[0-9]{8}-[0-9]{6}(-[0-9]{1,3})?')


def _stand(tmp, name, migrate=True):
    """`(rig, sp)`: ЛІГА чи звичайний простір (`plain`); ЛІГА мігрована справжнім `run_all()` (кроки A–D) — як у людини (`migrate=False` — перший старт, ще не мігровано)."""
    import liga_migrate as lm
    base = name.split('-')[0]                             # `<стенд>-startup` — окрема тека, той самий стенд
    rig = Rig(tmp, name)
    cfg = rig.config()
    cfg.update(jira_email=JIRA_ENV_EMAIL, jira_token=JIRA_ENV_TOKEN, gitlab_host_ip=HOSTIP, preview_password=PW,
               registry={'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'})
    _write(rig.tasks_path, cfg)
    liga = rig.registry()
    sp = liga
    if base == 'plain':
        plain_dir = os.path.join(rig.home, 'plain-space')
        _write(os.path.join(plain_dir, 'space.json'), {})
        pdir = os.path.join(plain_dir, 'p-1')
        _write(os.path.join(pdir, 'iterations.json'), {'iterations': [], 'publish_url': None})
        _write(os.path.join(plain_dir, 'tasks.json'), {'tasks': {'p-1': {'dir': pdir, 'title': 'Plain demo'}}, 'current': 'p-1'})
        sp = {'id': 'plain', 'path': plain_dir, 'legacy': False, 'integrations': False}
        _write(os.path.join(rig.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [liga, sp]})
        return rig, sp
    if not migrate and base != 'unmigrated':
        return rig, sp
    if base == 'unmigrated':
        _write(os.path.join(rig.space_dir, 'space.json'), {'migrations': {'liga-4d3a': {'held': True}}})
        return rig, sp
    with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), contextlib.redirect_stderr(io.StringIO()):
        res = lm.run_all()
    assert [r[1] for r in res] == ['done'] * len(lm.STEPS), res
    spj = os.path.join(rig.space_dir, 'space.json')
    with open(spj, encoding='utf-8') as f:
        data = json.load(f)
    sec_path = os.path.join(rig.deai, 'secrets.json')
    if base == 'differs':
        data['modules']['git-sync']['settings']['ssh_key'] = '/other/key'
        with open(sec_path, encoding='utf-8') as f:
            sec = json.load(f)
        sec['legacy']['vercel-publish'] = {'password': 'inert-old'}
        sec['legacy']['jira-tracker'] = {'token': 'other-token'}
        _write(sec_path, sec)
        os.chmod(sec_path, 0o600)
    elif base == 'partial':
        for mid in ('supabase-teams', 'jira-tracker'):
            data['modules'].pop(mid, None)
    _write(spj, data)
    return rig, sp


def _capabilities(sp, rig):
    import deai_modules as dm
    out = {'ok': dm.capabilities(sp)}
    spj = os.path.join(sp['path'], 'space.json')
    keep = None
    if os.path.isfile(spj):
        with open(spj, 'rb') as f:
            keep = f.read()
    _write(spj, '{not json')                              # нечитабельний space.json: `error_path`
    dm.reset_caches()
    out['error_path'] = dm.capabilities(sp)
    if keep is not None:
        with open(spj, 'wb') as f:
            f.write(keep)
    else:
        os.remove(spj)
    dm.reset_caches()
    return out


def _provider(sp):
    import deai_modules as dm
    import spaces

    def one(role, space=None):
        try:
            p = dm.provider(role, space) if space is not None else dm.provider(role)
            return {'api': dm.api_value(p), 'type': type(p).__name__}
        except Exception as e:  # noqa: BLE001
            return {'raised': type(e).__name__, 'code': getattr(e, 'code', None)}
    out = {'in_space': {r: one(r, sp) for r in ROLES}}
    with spaces.request_space(None):                       # простір запиту НЕ зафіксовано: неявний простір (0.20.0 — `Implicit`)
        out['implicit_space'] = {r: one(r) for r in ROLES}
    return out


def _api(rig, sp):
    tid = 'p-1' if sp['id'] == 'plain' else 'a-1'
    import serve
    out = {}
    spy = mock.MagicMock(return_value=False)
    with mock.patch.object(serve, '_registry_push', spy), mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None), Server() as srv:
        st, body = srv.req('GET', '/api/task', task=tid)
        keys = ('preview_password', 'preview_password_custom', 'preview_gate', 'comment_channel')
        out['task'] = {'status': st, **{k: (body or {}).get(k, '<absent>') for k in keys},
                       'capabilities': ((body or {}).get('space') or {}).get('capabilities'),
                       'compat': ((body or {}).get('space') or {}).get('compat', '<absent>')}
        st, body = srv.req('GET', '/api/modules?space=' + sp['id'])
        mods = (body or {}).get('modules') or []
        def fields(m):          # значення простих полів і «задано» секретів; без підписів (`label`) — вони не про поведінку
            return {f['key']: ('<set>' if f.get('set') else f.get('value', '<unset>')) if f.get('type') == 'secret' else f.get('value', '<unset>')
                    for f in (m.get('settings') or []) if isinstance(f, dict) and f.get('key')}
        out['modules'] = {'status': st, 'list': {m['id']: {'enabled': m.get('enabled'), 'implicit': m.get('implicit'), 'status': m.get('status'),
                                                              'fields': fields(m)} for m in mods}}
        st, body = srv.req('GET', '/api/comment-config?ch=project&it=it1', task=tid)
        body = body if isinstance(body, dict) else {}
        out['comment_config'] = {'status': st, 'module': body.get('module'), 'channel': body.get('channel'), 'config': body.get('config'),
                                 'code': body.get('code')}
        st, body = srv.req('GET', '/api/teams-mute', task=tid)
        out['teams_mute'] = {'status': st, 'body': body if isinstance(body, dict) else None}
        st, body = srv.req('GET', '/api/tasks-overview?refresh=1', task=tid)
        body = body if isinstance(body, dict) else {}
        team = body.get('team')
        out['tasks_overview'] = {'status': st, 'team': (None if team is None else {k: team.get(k) for k in ('error', 'tab') if isinstance(team, dict)}),
                                 'tracker': body.get('tracker')}
    return scrub(out, rig.home)


def _vcs_target(rig, sp):
    """Цілі `vcs_target` і ЕФЕКТИВНІ ключ та IP (ціль, інакше налаштування запису): саме вони доходять до git."""
    import serve
    cases = {'task_gitlab': {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1'}},
             'task_gitlab_own_key': {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1', 'ssh_key': '/own/key', 'host_ip': '198.51.100.9'}},
             'task_vcs': {'vcs': {'repo': 'git@example.com:o/r.git'}}}
    out = {}
    with serve.spaces.request_space(sp['id']):
        try:
            prov = serve.vcs_provider()
        except Exception as e:  # noqa: BLE001
            return {'raised': type(e).__name__}
        if prov is None:
            return {'provider': None}
        _mod, ctx, legacy = prov
        settings = ctx.get('settings') or {}
        out['provider'] = {'legacy_texts': legacy, 'settings': {k: settings.get(k) for k in ('ssh_key', 'host_ip', 'branch', 'path', 'autosync', 'compat')}}
        cfg = rig.cfg
        for key, task in cases.items():
            t = serve.vcs_target(cfg, 'a-1', task, settings)
            out[key] = {'target': t, 'effective': {'ssh_key': (t or {}).get('ssh_key') or (os.path.expanduser(settings['ssh_key']) if settings.get('ssh_key') else None),
                                                   'host_ip': (t or {}).get('host_ip') or settings.get('host_ip')}}
    return scrub(out, rig.home)


def _registry_ssh(rig):
    import registry
    return rel(registry._ssh_key(rig.cfg), rig.home)


def _startup_text(tmp, name):
    """Рядки ПЕРШОГО старту (`liga_migrate.startup`) на стенді, що ще не мігрований (`regular`) чи утриманий (`unmigrated`)."""
    import liga_migrate as lm
    rig, sp = _stand(tmp, name + '-startup', migrate=False)
    buf = io.StringIO()
    with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), contextlib.redirect_stderr(buf):
        lm.startup()
    return STAMP.sub('<stamp>', buf.getvalue()).splitlines()


def _isolation(rig, sp):
    """Форми відповідей ІЗОЛЬОВАНОГО прогону (`DC_TASKS_FILE`): рядки команди, статуси, мовчання Teams, `ctx` коментарів (де беруться облікові)."""
    import serve
    out = {}
    env = {'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1'}
    with mock.patch.dict(os.environ, env), serve.spaces.request_space(sp['id']):
        serve.deai_modules.reset_caches()
        out['team_rows'] = list(serve.team_rows(refresh=True))
        out['tracker'] = serve.tracker_snapshot(['DEMO-1'], refresh=True)
        try:
            out['notify_state'] = serve.notify_call('mute_state')
        except Exception as e:  # noqa: BLE001
            out['notify_state'] = {'raised': type(e).__name__, 'message': str(e)[:120]}
        try:
            space = serve.spaces.active_space()
            prov, err = serve.comments_provider(space)
            mod, ctx, _ch = serve.comments_route(space, prov)
            out['comments_ctx'] = {'url': ctx['settings'].get('url'), 'key_set': bool(ctx['secrets'].get('key'))}
        except Exception as e:  # noqa: BLE001
            out['comments_ctx'] = {'raised': type(e).__name__, 'code': getattr(e, 'code', None)}
        out['overview_launch_gate'] = {'isolated': serve.implicit.isolated()}
        serve.deai_modules.reset_caches()
    return scrub(out, rig.home)


def _dashboard_sync(rig, sp):
    """Поведінка ПУСКУ синку дашборда (`Handler._overview_sync`, РЕАЛЬНИЙ метод) без процесів: шпигун на `serve._overview_launch` пише
    «викликано чи ні» й аргументи `(ключ, legacy, ціль)`. Три оточення: `non_isolated` (шлях власника), `isolated` (лише `DC_TASKS_FILE`),
    `no_overview` (`DC_NO_OVERVIEW`); кожне — для простору, ЗАФІКСОВАНОГО в запиті (`in_space`), і для НЕзафіксованого (`implicit_space`).
    Форма значення: `{'called': bool, 'args': [key, legacy, target] | None}` або `{'raised': <тип>}`. Це читає паритет Task 15."""
    import serve

    def one(env, fixed):
        calls = []
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(serve, '_overview_launch', lambda *a: calls.append(list(a))), \
                    serve.spaces.request_space(sp['id'] if fixed else None):
                serve.deai_modules.reset_caches()
                serve.Handler._overview_sync(None)
        except Exception as e:  # noqa: BLE001
            return {'raised': type(e).__name__}
        finally:
            serve.deai_modules.reset_caches()
        return {'called': bool(calls), 'args': calls[0] if calls else None}
    envs = {'non_isolated': {}, 'isolated': {'DC_TASKS_FILE': rig.tasks_path}, 'no_overview': {'DC_NO_OVERVIEW': '1'}}
    out = {k: {'in_space': one(e, True), 'implicit_space': one(e, False)} for k, e in envs.items()}
    return scrub(out, rig.home)


def _scenarios(tmp, name):
    rig, sp = _stand(tmp, name)
    out = {}
    with rig.activate():
        import deai_modules as dm
        dm.reset_caches()
        with open(rig.tasks_path, encoding='utf-8') as f:
            out['root_keys'] = sorted(json.load(f))
        out['capabilities'] = _capabilities(sp, rig)
        out['provider'] = _provider(sp)
        out['api'] = _api(rig, sp)
        out['dashboard_sync'] = _dashboard_sync(rig, sp)
        if name != 'plain':
            out['vcs_target'] = _vcs_target(rig, sp)
            out['registry_ssh'] = _registry_ssh(rig)
            out['isolation'] = _isolation(rig, sp)
        dm.reset_caches()
    if name in ('regular', 'unmigrated'):
        out['startup_text'] = _startup_text(tmp, name)
    return scrub(out, rig.home)


def make():
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d4b-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire, mock.patch('urllib.request.urlopen', NoNet()):
            for n in CLEAN:
                os.environ.pop(n, None)
            snap = {'meta': {'version': '0.20.0', 'source_commit': _source_commit(), 'generator': 'tests/make_before_4d4b.py',
                             'volatile_stripped': ['backup stamps → <stamp>']}, 'stands': {}}
            for name in STANDS:
                snap['stands'][name] = _scenarios(tmp, name)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.20.0 = `0d52a74`; після нього лише docs 4d-4b). Зашито."""
    return '0d52a74'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — у `ROOT` нема `.git`
    (заморожена копія з `git archive`: довіряємо рецепту). Закрито за замовчуванням усередині git-теки."""
    if not os.path.lexists(os.path.join(ROOT, '.git')):
        return None
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return True
        src = _source_commit()
        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
            return True
        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin', 'ops'], capture_output=True, timeout=60)
        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin', 'ops'],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    return untracked.returncode != 0 or diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d4b: app/, bin/ або ops/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
              'Запускай із замороженої копії (git archive %s | tar -x -C <тека>), див. докстрінг.'
              % (_source_commit(), _source_commit()), file=sys.stderr)
        sys.exit(2)
    snap = make()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print('знімок записано:', args.out)


if __name__ == '__main__':
    main()

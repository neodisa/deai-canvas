"""Фальшивий `npx` для тестів режиму `cli` (4b-1): справжній виконуваний файл у тимчасовій теці. Читає
`scenario.json` поруч із собою, дописує свій argv і cwd у `log.jsonl`, відповідає за підкомандою `vercel`.
Сценарій: {"<підкоманда>": {"code": 0, "stdout": "...", "stderr": "...", "org": "team_x"} | [ {...}, {...} ]}
(список — відповіді по черзі; останню повторює), `"org"` пише `.vercel/project.json` у cwd (як справжній `vercel link`).
Мережі нема й бути не може: це лише Python, що друкує текст.

`npx` — це `#!/bin/sh`-обгортка, що викликає `sys.executable` на сусідньому `npx_body.py`: шебанг із шляхом інтерпретатора
зі пробілами (чи задовгим) не працює, а `env python3` у тестовому оточенні може вказати не туди. `make()` стирає журнал
і лічильники попереднього сценарію в тій самій теці."""
import glob
import json
import os
import shlex
import stat
import sys

SCRIPT = r'''import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, 'log.jsonl'), 'a', encoding='utf-8') as f:
    f.write(json.dumps({'argv': args, 'cwd': os.getcwd()}) + '\n')
sub = args[2] if len(args) > 2 and args[:2] == ['--yes', 'vercel'] else '?'
with open(os.path.join(here, 'scenario.json'), encoding='utf-8') as f:
    sc = json.load(f)
ans = sc.get(sub, {'code': 0})
if isinstance(ans, list):
    cnt_path = os.path.join(here, f'.n-{sub}')
    n = int(open(cnt_path).read()) if os.path.exists(cnt_path) else 0
    open(cnt_path, 'w').write(str(n + 1))
    ans = ans[min(n, len(ans) - 1)]
if ans.get('org'):
    os.makedirs('.vercel', exist_ok=True)
    with open(os.path.join('.vercel', 'project.json'), 'w') as f:
        json.dump({'orgId': ans['org'], 'projectId': 'prj_fake'}, f)
sys.stdout.flush()
sys.stdout.buffer.write(ans.get('stdout', '').encode('utf-8') + bytes.fromhex(ans.get('stdout_hex', '')))   # `stdout_hex` — сирі (можливо не UTF-8) байти
sys.stdout.flush()
sys.stderr.write(ans.get('stderr', ''))
sys.exit(ans.get('code', 0))
'''


def make(dirpath, scenario):
    """Покласти `npx` + `npx_body.py` + `scenario.json` у `dirpath`, стерши журнал і лічильники попереднього сценарію;
    повертає шлях до `npx`."""
    os.makedirs(dirpath, exist_ok=True)
    for stale in [os.path.join(dirpath, 'log.jsonl'), *glob.glob(os.path.join(dirpath, '.n-*'))]:
        if os.path.exists(stale):
            os.remove(stale)
    with open(os.path.join(dirpath, 'npx_body.py'), 'w', encoding='utf-8') as f:
        f.write(SCRIPT)
    p = os.path.join(dirpath, 'npx')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$(dirname "$0")/npx_body.py" "$@"\n')
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(os.path.join(dirpath, 'scenario.json'), 'w', encoding='utf-8') as f:
        json.dump(scenario, f)
    return p


def calls(dirpath):
    """Список `{'argv', 'cwd'}` у порядку викликів."""
    path = os.path.join(dirpath, 'log.jsonl')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]

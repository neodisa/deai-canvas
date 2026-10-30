"""Фальшивий `npx` для тестів режиму `cli` (4b-1): справжній виконуваний файл у тимчасовій теці. Читає
`scenario.json` поруч із собою, дописує свій argv і cwd у `log.jsonl`, відповідає за підкомандою `vercel`.
Сценарій: {"<підкоманда>": {"code": 0, "stdout": "...", "stderr": "...", "org": "team_x"} | [ {...}, {...} ]}
(список — відповіді по черзі; останню повторює), `"org"` пише `.vercel/project.json` у cwd (як справжній `vercel link`).
Мережі нема й бути не може: це лише Python, що друкує текст.

(шебанг — справжній `sys.executable`: `env python3` у тестовому оточенні може вказати не туди.)"""
import json
import os
import stat
import sys

SCRIPT = r'''#!/usr/bin/env python3
import json, os, sys
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
sys.stdout.write(ans.get('stdout', ''))
sys.stderr.write(ans.get('stderr', ''))
sys.exit(ans.get('code', 0))
'''


def make(dirpath, scenario):
    """Покласти `npx` + `scenario.json` у `dirpath`; повертає шлях до `npx`."""
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(dirpath, 'npx')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(SCRIPT.replace('/usr/bin/env python3', sys.executable, 1))
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

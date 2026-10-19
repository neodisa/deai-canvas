"""memo-comments — тестовий модуль ролі `comments`: еталон для авторів модулів (спека 2b-2).

Сервер коментарів — будь-який HTTP-сервіс за `endpoint` із трьома маршрутами:
    GET  <endpoint>/c/<канал>           → JSON-масив коментарів
    POST <endpoint>/c/<канал>           ← {"comments": [...]}   (upsert за `id`)
    POST <endpoint>/c/<канал>/remove    ← {"ids": [...]}
    POST <endpoint>/c/<канал>/resolve   ← {"id": "...", "reason": "..."}
Браузерна половина — `adapter.js` (ходить на ті самі маршрути); ця — для агента (`list`, `resolve`) і для ядра
(`client_config`, `check`). Лише stdlib: модуль не імпортує ні `serve`, ні `deai_modules`.

Два нюанси exec-завантаження: `list` ТІНИТЬ вбудовану `list` у цьому файлі (тому нижче `type([])`), а секрет
`token` іде лише в заголовок запиту сервера — у `client_config` його немає, і ядро це перевірить.
"""
import json
import urllib.request
from urllib.parse import quote

TIMEOUT = 10        # секунд на запит до сервісу


def _url(ctx, channel, tail=''):
    endpoint = ctx['settings']['endpoint']
    if not endpoint.startswith(('http://', 'https://')):
        raise ValueError('endpoint: expected an http(s) address')
    return endpoint.rstrip('/') + '/c/' + quote(channel, safe='') + tail


def _request(ctx, method, url, body=None):
    headers = {'Content-Type': 'application/json'}
    token = ctx['secrets'].get('token')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read() or b'null')


def client_config(ctx):
    """ПУБЛІЧНА конфігурація для сторінок: адреса сервісу й публічний ключ (порожній, якщо не заданий)."""
    return {'endpoint': ctx['settings']['endpoint'], 'pubkey': ctx['secrets'].get('pubkey') or ''}


def list(ctx, channel):  # noqa: A001 — імʼя функції ролі
    data = _request(ctx, 'GET', _url(ctx, channel))
    return data if isinstance(data, type([])) else []


def resolve(ctx, channel, id, reason):  # noqa: A002 — імена аргументів ролі
    _request(ctx, 'POST', _url(ctx, channel, '/resolve'), {'id': id, 'reason': reason})


def check(ctx):
    return {'ok': True}

"""`app/modules/supabase-teams/schema.sql`: СТАТИЧНІ перевірки схеми сповіщень Teams (роль `notify`, 4c-3, Task 3).

Postgres на машині нема, тож SQL не виконується: тест розбирає ТЕКСТ схеми регулярками (коментарі `--` зрізано, щоб слова з
шапки не рахувались як код). Кожна перевірка доводиться мутацією тексту (див. звіт Task 3): прибрав охоронця — тест червоніє.

Що доводиться:
  * кожна `security definer` має `set search_path`; тригерна функція — `security invoker` із `row_security_active`;
  * відправка й тригер ковтають помилки (`exception when others`);
  * `teams_mute_set` / `teams_mute_state` / `teams_notify_health` — `grant execute` ЛИШЕ `service_role`, `revoke` від
    `public`/`anon`/`authenticated`; `cl_send_teams` — `grant` `anon, authenticated` (кличе INVOKER-тригер);
  * обидві таблиці — RLS і `revoke all` від `anon, authenticated`;
  * картка: без `||` над даними коментаря (лише `jsonb_build_*`; єдиний виняток — обрізання тексту `left(`), без `format`/`concat`;
    картинка й кнопка — лише за `https://`; підписи — в одному `declare`-блоці;
  * ідемпотентність; свіжість 2 хв; тиша з підканалами; секрет Vault `teams_webhook_url`.
"""
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
SCHEMA = os.path.join(ROOT, 'app', 'modules', 'supabase-teams', 'schema.sql')

#: Повний блок функції: від `create or replace function public.<імʼя>(` до закриття `$$;`; тіло між `$$ … $$` не містить `$$`.
_FN = re.compile(r'create or replace function\s+public\.(\w+)\s*\((.*?)\bas\s+\$\$(.*?)\$\$;', re.S | re.I)


def sql():
    """Текст схеми без рядкових коментарів `-- …` (код, а не пояснення)."""
    with open(SCHEMA, encoding='utf-8') as f:
        raw = f.read()
    return '\n'.join(re.sub(r'--.*$', '', ln) for ln in raw.splitlines())


def functions():
    """`{імʼя: (заголовок, тіло)}`: заголовок — усе до `as $$` (сигнатура, `security …`, `set search_path`)."""
    out = {}
    for m in _FN.finditer(sql()):
        full = m.group(0)
        head = full[:full.lower().index('as $$')]
        out[m.group(1)] = (head, m.group(3))
    return out


def one_line(text):
    return ' '.join(text.split()).lower()


class SchemaFile(unittest.TestCase):
    def test_the_expected_functions_exist(self):
        self.assertEqual(sorted(functions()), ['cl_notify_teams', 'cl_send_teams', 'comment_teams_card',
                                               'teams_mute_set', 'teams_mute_state', 'teams_notify_health'])

    def test_the_header_warns(self):
        with open(SCHEMA, encoding='utf-8') as f:
            raw = f.read()
        head = raw.split('create extension', 1)[0]
        self.assertIn('DEDICATED SUPABASE PROJECT', head)
        self.assertIn('AFTER the schema of', head)
        self.assertIn('supabase-comments', head)
        self.assertIn('LIGA INSTALLATION: DO NOT RUN THIS', head)
        self.assertIn('NON-PUBLIC', head)
        self.assertIn('teams_webhook_url', head)

    def test_no_real_hosts_or_secrets_in_the_schema(self):
        with open(SCHEMA, encoding='utf-8') as f:
            raw = f.read()
        for needle in ('office.com', 'logic.azure', 'webhook.office', 'powerplatform', 'supabase.co', 'overview_projects'):
            self.assertNotIn(needle, raw, needle)
        self.assertNotRegex(raw, r"create_secret\('https")


class Security(unittest.TestCase):
    def test_every_security_definer_has_a_search_path(self):
        defs = [(n, h) for n, (h, _) in functions().items() if re.search(r'security\s+definer', h, re.I)]
        self.assertEqual(sorted(n for n, _ in defs), ['cl_send_teams', 'teams_mute_set', 'teams_mute_state',
                                                      'teams_notify_health'])
        for name, head in defs:
            self.assertRegex(head, r'set\s+search_path\s*=', name)

    def test_every_function_pins_its_search_path(self):
        for name, (head, _) in functions().items():
            self.assertRegex(head, r'set\s+search_path\s*=\s*pg_catalog', name)

    def test_the_trigger_function_is_invoker_and_checks_row_security(self):
        head, body = functions()['cl_notify_teams']
        self.assertRegex(head, r'security\s+invoker')
        self.assertNotRegex(head, r'security\s+definer')
        self.assertIn("row_security_active('public.comments')", body)

    def test_the_send_and_the_trigger_swallow_errors(self):
        for name in ('cl_send_teams', 'cl_notify_teams'):
            self.assertRegex(functions()[name][1], r'exception\s+when\s+others', name)

    def test_the_trigger_is_after_insert_and_recreated(self):
        s = one_line(sql())
        self.assertIn('drop trigger if exists cl_notify_teams on public.comments;', s)
        self.assertIn('create trigger cl_notify_teams after insert on public.comments for each row '
                      'execute function public.cl_notify_teams();', s)
        self.assertLess(s.index('drop trigger if exists cl_notify_teams'), s.index('create trigger cl_notify_teams'))

    def test_the_mute_and_health_functions_go_to_service_role_only(self):
        s = one_line(sql())
        sigs = {'teams_mute_set': r'teams_mute_set\(text, boolean, text\)', 'teams_mute_state': r'teams_mute_state\(\)',
                'teams_notify_health': r'teams_notify_health\(int\)'}
        for name, sig in sigs.items():
            self.assertRegex(s, rf'grant execute on function public\.{sig} to service_role;', name)
            self.assertRegex(s, rf'revoke all on function public\.{sig} from public, anon, authenticated;', name)
            for bad in ('anon', 'authenticated', 'public'):
                self.assertNotRegex(s, rf'grant [a-z ,]+ on function public\.{sig} to [a-z_, ]*\b{bad}\b', f'{name} {bad}')
            self.assertLess(s.index(f'revoke all on function public.{name}'), s.index(f'grant execute on function public.{name}'))

    def test_the_send_function_is_granted_to_the_public_roles_the_trigger_runs_as(self):
        s = one_line(sql())
        self.assertIn('revoke all on function public.cl_send_teams(text) from public;', s)
        self.assertIn('grant execute on function public.cl_send_teams(text) to anon, authenticated;', s)

    def test_the_card_builder_is_closed_to_the_public_roles(self):
        self.assertIn('revoke all on function public.comment_teams_card(public.comments) from public, anon, authenticated;',
                      one_line(sql()))

    def test_both_tables_have_rls_and_no_public_access(self):
        s = one_line(sql())
        for t in ('teams_delivery_log', 'teams_project_mute'):
            self.assertIn(f'alter table public.{t} enable row level security;', s, t)
            self.assertIn(f'revoke all on public.{t} from anon, authenticated;', s, t)
            self.assertNotRegex(s, rf'create policy [^;]*public\.{t}', t)
            self.assertNotRegex(s, rf'grant [a-z ,]+ on public\.{t} to', t)

    def test_the_webhook_secret_comes_from_vault_and_must_be_https(self):
        body = functions()['cl_send_teams'][1]
        self.assertIn('vault.decrypted_secrets', body)
        self.assertIn("name = 'teams_webhook_url'", body)
        self.assertRegex(body, r"hook\s*!~\*\s*'\^https://'")
        self.assertIn('net.http_post', body)
        health = functions()['teams_notify_health'][1]
        self.assertIn("s.name = 'teams_webhook_url'", health)
        self.assertNotRegex(health, r'select\s+s\.decrypted_secret\b', 'здоровʼя повертає факт наявності, не значення')


class Card(unittest.TestCase):
    def body(self):
        return functions()['comment_teams_card'][1]

    def test_the_card_has_no_concatenation_over_comment_data(self):
        """Кожен `||` у тілі — лише в рядку обрізання тексту (`left(`); картка — тільки `jsonb_build_*`."""
        body = self.body()
        for ln in body.splitlines():
            if '||' in ln:
                self.assertIn('left(', ln, f'конкатенація поза обрізанням тексту: {ln.strip()}')
        self.assertEqual(body.count('||'), 1)
        for bad in ('format(', 'concat(', 'concat_ws(', '::jsonb', 'to_jsonb(', 'replace(', 'regexp_replace('):
            self.assertNotIn(bad, body.lower(), bad)
        self.assertIn('jsonb_build_object', body)
        self.assertIn('jsonb_build_array', body)

    def test_the_project_is_the_channel_id(self):
        body = self.body()
        self.assertIn('c.project_id', body)
        self.assertNotIn('overview_projects', body)
        self.assertIn('c.meta->>', body)

    def test_the_image_and_the_button_need_https(self):
        body = self.body()
        self.assertRegex(body, r"shot_url\s+text\s*:=\s*case when c\.meta->>'shotUrl'\s*~\*\s*'\^https://")
        self.assertRegex(body, r"open_url\s+text\s*:=\s*case when c\.meta->>'url'\s*~\*\s*'\^https://")
        # у картку потрапляють лише ці змінні, а не сире `meta`
        self.assertIn("'url', shot_url", body)
        self.assertIn("'url', open_url", body)
        self.assertNotRegex(body, r"'url',\s*c\.meta")

    def test_the_labels_live_in_one_declare_block(self):
        body = self.body()
        decl, code = body.split('begin', 1)
        for lab in ('Новий коментар', 'Проєкт', 'Ітерація', 'Сторінка', 'Автор', 'Статус', 'Відкрити сторінку'):
            self.assertIn(lab, decl, lab)
            self.assertNotIn(lab, code, f'{lab}: підпис поза declare-блоком')

    def test_the_text_is_cut_to_500(self):
        self.assertIn('left(c.text, 500)', self.body())

    def test_the_envelope_is_an_adaptive_card_message(self):
        body = self.body()
        for needle in ("'type', 'message'", "'contentType', 'application/vnd.microsoft.card.adaptive'",
                       "'type', 'AdaptiveCard'", "'version', '1.4'"):
            self.assertIn(needle, body, needle)


class Behaviour(unittest.TestCase):
    def test_the_send_checks_freshness_and_the_mute_with_subchannels(self):
        body = functions()['cl_send_teams'][1]
        self.assertIn("interval '2 minutes'", body)
        self.assertIn('public.teams_project_mute', body)
        self.assertRegex(body, r"\|\|\s*'/'")                  # підканал — лише за `<канал>/`, не за голим префіксом
        self.assertIn('c.project_id = m.project_id', body)
        self.assertIn('insert into public.teams_delivery_log', body)

    def test_the_send_is_deduplicated_by_the_delivery_log(self):
        """Повторний виклик з тим самим id (функція відкрита ключу сторінки) не шле картку вдруге: рядок у журналі доставок
        для цього коментаря — вихід, і це ПІСЛЯ перевірки свіжості, але ДО тиші й будь-якої відправки."""
        body = one_line(functions()['cl_send_teams'][1])
        guard = ('if exists (select 1 from public.teams_delivery_log where comment_id = c.id) then return; end if;')
        self.assertIn(guard, body)
        self.assertLess(body.index("interval '2 minutes'"), body.index(guard))
        self.assertLess(body.index(guard), body.index('net.http_post'))
        self.assertLess(body.index(guard), body.index('public.teams_project_mute'))

    def test_the_mute_set_validates_its_arguments(self):
        body = functions()['teams_mute_set'][1]
        self.assertIn('length(p_project) not between 1 and 200', body)
        self.assertIn('p_muted is null', body)
        self.assertIn('on conflict (project_id) do update', body)
        self.assertRegex(functions()['teams_mute_set'][0], r'p_by text default \'\'')

    def test_the_health_returns_the_expected_columns(self):
        head = functions()['teams_notify_health'][0]
        for col in ('webhook_set boolean', 'sent bigint', 'responded bigint', 'failed bigint', 'last_failed_at timestamptz',
                    'last_sent_at timestamptz'):
            self.assertIn(col, head, col)
        self.assertIn('window_hours int default 6', head)

    def test_the_script_is_idempotent(self):
        s = one_line(sql())
        self.assertIn('create extension if not exists pg_net;', s)
        self.assertEqual(s.count('create table if not exists'), 2)
        self.assertNotRegex(s, r'create table (?!if not exists)')
        self.assertNotRegex(s, r'create function')                   # лише `create or replace function`
        self.assertEqual(len(re.findall(r'create or replace function', s)), 6)
        self.assertNotRegex(s, r'create trigger (?!cl_notify_teams)')
        self.assertNotRegex(s, r'\bdrop (table|function|extension)\b')


if __name__ == '__main__':
    unittest.main()

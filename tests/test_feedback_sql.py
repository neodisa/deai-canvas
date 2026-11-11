"""Відгук, T9: статичні перевірки `ops/feedback-collector.sql` (текстовий розбір, без бази).

Що доводиться: публічна (anon) роль лише ВСТАВЛЯЄ — у таблицю (колонковий грант без `created_at`) і в приватний бакет скриншотів; жодного
select/update/delete для публічних ролей; RLS увімкнено; тригер → Teams будує картку лише `jsonb_build_*` і ковтає всі помилки; у файлі нема
секретів і адрес."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'ops', 'feedback-collector.sql')
COLS = ['id', 'kind', 'text', 'contact', 'version', 'os', 'diag', 'shot_path']


def read():
    with open(PATH, encoding='utf-8') as f:
        return f.read()


def code_of(raw):
    """Без `--`-коментарів (рядкові літерали з `--` у файлі не трапляються)."""
    return '\n'.join(re.sub(r'--.*$', '', line) for line in raw.split('\n'))


def findings(raw):
    """Усі порушення правил файла (порожній список — файл чистий). Один вхід і для тесту, і для мутацій."""
    bad = []
    code = code_of(raw)
    low = code.lower()

    # --- секрети й адреси: у ВСЬОМУ файлі, разом із коментарями ---
    for needle in ('eyJ', 'sb_secret_', 'sb_publishable_', 'service_role', 'sb_'):
        if needle in raw:
            bad.append('secret-like literal: %s' % needle)
    for m in re.finditer(r'https?://', raw):
        if not (m.group(0) == 'https://' and raw[m.start() - 1:m.start()] == '^' and raw[m.end():m.end() + 1] == "'"):
            bad.append('url literal at %d' % m.start())
    if re.search(r'\b[a-z0-9-]+\.supabase\.(co|in)\b|\bpowerautomate\b|webhook\.office|logic\.azure', raw, re.I):
        bad.append('project/webhook address')

    # --- RLS ---
    if not re.search(r'alter\s+table\s+public\.feedback\s+enable\s+row\s+level\s+security\s*;', low):
        bad.append('rls not enabled on public.feedback')
    for pat in (r'disable\s+row\s+level', r'force\s+row\s+level\s+security\s+off', r'alter\s+default\s+privileges', r'drop\s+table', r'bypassrls'):
        if re.search(pat, low):
            bad.append('forbidden statement: %s' % pat)

    # --- політики: кожна лише `for insert to anon` на двох відомих таблицях ---
    created = len(re.findall(r'create\s+policy\b', low))
    pols = re.findall(r'create\s+policy\s+(\w+)\s+on\s+([\w.]+)\s+for\s+(\w+)\s+to\s+([\w,\s]+?)\s+(?:with\s+check|using)\b', low)
    if created != len(pols):
        bad.append('a policy not in the canonical form')
    for name, table, cmd, roles in pols:
        if table not in ('public.feedback', 'storage.objects'):
            bad.append('policy on a foreign table: %s' % table)
        if cmd != 'insert':
            bad.append('policy %s is for %s' % (name, cmd))
        if [r.strip() for r in roles.split(',')] != ['anon']:
            bad.append('policy %s is for roles %s' % (name, roles.strip()))
    for table in ('public.feedback', 'storage.objects'):
        if len([p for p in pols if p[1] == table]) != 1:
            bad.append('need exactly one policy on %s' % table)

    # --- гранти: єдиний — колонковий insert для anon; `revoke all` ДО нього ---
    grants = re.findall(r'\bgrant\b\s+(.+?)\s+on\s+(.+?)\s+to\s+([^;]+);', low, re.S)
    if len(grants) != 1:
        bad.append('expected exactly one grant, found %d' % len(grants))
    for privs, on, to in grants:
        m = re.fullmatch(r'insert\s*\(([^)]*)\)', privs.strip())
        if not m:
            bad.append('grant of %s' % privs.strip())
        elif [c.strip() for c in m.group(1).split(',')] != COLS:
            bad.append('grant columns differ: %s' % m.group(1))
        if on.strip() != 'public.feedback' or to.strip() != 'anon':
            bad.append('grant on %s to %s' % (on.strip(), to.strip()))
    rv = re.search(r'revoke\s+all\s+on\s+public\.feedback\s+from\s+anon,\s*authenticated,\s*public\s*;', low)
    gr = re.search(r'\bgrant\b', low)
    if not rv or (gr and rv.start() > gr.start()):
        bad.append('revoke all must precede the grant')

    # --- таблиця ---
    for pat in (r'create\s+table\s+if\s+not\s+exists\s+public\.feedback\b', r'id\s+uuid\s+primary\s+key', r'created_at\s+timestamptz\s+not\s+null\s+default\s+now\(\)',
                r"kind\s+text\s+not\s+null\s+check\s*\(\s*kind\s+in\s*\(\s*'bug'\s*,\s*'idea'\s*\)\s*\)",
                r'text\s+text\s+not\s+null\s+check\s*\(\s*char_length\(text\)\s+between\s+10\s+and\s+10000\s*\)',
                r'contact\s+text\s+check\s*\(\s*contact\s+is\s+null\s+or\s+char_length\(contact\)\s*<=\s*200\s*\)',
                r'octet_length\(diag::text\)\s*<=\s*65536',
                r"shot_path\s+~\s+'\^\[0-9a-f-\]\{36\}\\\.\(webp\|png\)\$'"):
        if not re.search(pat, low):
            bad.append('table definition lacks %s' % pat)

    # --- бакет ---
    m = re.search(r"insert\s+into\s+storage\.buckets\s*\(([^)]*)\)\s*values\s*\(([^;]*?)\)\s*on\s+conflict\s*\(id\)\s+do\s+update\s+set\s+([^;]*);", low, re.S)
    if not m:
        bad.append('bucket statement not found')
    else:
        cols = [c.strip() for c in m.group(1).split(',')]
        vals = re.match(r"\s*'feedback-shots'\s*,\s*'feedback-shots'\s*,\s*(\w+)\s*,\s*(\d+)\s*,\s*array\[([^\]]*)\]\s*$", m.group(2))
        if cols != ['id', 'name', 'public', 'file_size_limit', 'allowed_mime_types'] or not vals:
            bad.append('bucket columns/values')
        else:
            if vals.group(1) != 'false':
                bad.append('bucket is public')
            if vals.group(2) != '2097152':
                bad.append('bucket size limit')
            if sorted(re.findall(r"'([^']+)'", vals.group(3))) != ['image/png', 'image/webp']:
                bad.append('bucket mime types')
        if not re.search(r'public\s*=\s*false', m.group(3)) or 'file_size_limit = 2097152' not in m.group(3):
            bad.append('bucket upsert does not re-assert privacy/limit')
    if not re.search(r"on\s+storage\.objects\s+for\s+insert\s+to\s+anon\s+with\s+check\s*\(\s*bucket_id\s*=\s*'feedback-shots'\s+and\s+name\s*~\s*'", low):
        bad.append('storage policy is not insert-only to feedback-shots with a name check')

    # --- тригер → Teams ---
    fn = re.search(r'create\s+or\s+replace\s+function\s+public\.feedback_notify_teams\(\)(.*?)\$\$(.*?)\$\$\s*;', low, re.S)
    if not fn:
        bad.append('trigger function not found')
    else:
        head, body = fn.group(1), fn.group(2)
        if 'security definer' not in head:
            bad.append('trigger function is not security definer')
        if not re.search(r'set\s+search_path\s*=\s*pg_catalog,\s*public,\s*vault,\s*net\b', head):
            bad.append('search_path of the trigger function')
        if not re.search(r"vault\.decrypted_secrets\s+where\s+name\s*=\s*'teams_feedback_webhook_url'", body):
            bad.append('webhook is not read from Vault by the agreed name')
        if "'^https://'" not in body:
            bad.append('no https check of the webhook address')
        if 'jsonb_build_object' not in body or 'jsonb_build_array' not in body:
            bad.append('card is not built with jsonb_build_*')
        if body.count('||') != 1 or not re.search(r'left\(new\.text,\s*500\)\s*\|\|', body):
            bad.append('the only concatenation allowed is the 500-character cut')
        for pat in (r'\bformat\(', r'\bconcat\(', r'\bconcat_ws\(', r'string_agg', r'\bexecute\b'):
            if re.search(pat, body):
                bad.append('forbidden in the trigger function: %s' % pat)
        tail = body[body.find('exception when others'):] if 'exception when others' in body else ''
        if not tail or 'raise warning' not in tail or 'sqlstate' not in tail or 'return new' not in tail:
            bad.append('errors are not swallowed with sqlstate only')
        if 'sqlerrm' in body:
            bad.append('sqlerrm may echo the webhook address')
    if not re.search(r'revoke\s+all\s+on\s+function\s+public\.feedback_notify_teams\(\)\s+from\s+public,\s*anon,\s*authenticated\s*;', low):
        bad.append('trigger function is executable by public roles')
    if not re.search(r'create\s+trigger\s+feedback_notify_teams\s+after\s+insert\s+on\s+public\.feedback\s+for\s+each\s+row\s+execute\s+function\s+public\.feedback_notify_teams\(\)\s*;', low):
        bad.append('trigger is not after insert for each row')
    return bad


class FeedbackSql(unittest.TestCase):
    def test_the_collector_file_obeys_every_rule(self):
        self.assertEqual(findings(read()), [])

    # --- докази, що кожне правило може впасти (мутації прямо в тексті, файл не чіпаємо) ---
    def assertCaught(self, mutated, needle):
        got = findings(mutated)
        self.assertTrue(any(needle in f for f in got), '%r не спіймано: %s' % (needle, got))

    def test_the_rules_can_fail(self):
        raw = read()
        self.assertCaught(raw + "\ncreate policy leak on public.feedback for select to anon using (true);\n", 'policy leak is for select')
        self.assertCaught(raw + "\ncreate policy leak2 on public.feedback for all to authenticated using (true);\n", 'policy leak2')
        self.assertCaught(raw + "\ngrant select on public.feedback to anon;\n", 'expected exactly one grant')
        self.assertCaught(raw.replace('grant insert (id,', 'grant select, insert (id,'), 'grant of')
        self.assertCaught(raw.replace(' diag, shot_path) on public.feedback', ' diag, shot_path, created_at) on public.feedback'), 'grant columns differ')
        self.assertCaught(raw.replace('alter table public.feedback enable row level security;', ''), 'rls not enabled')
        self.assertCaught(raw.replace("values ('feedback-shots', 'feedback-shots', false,", "values ('feedback-shots', 'feedback-shots', true,"), 'bucket is public')
        self.assertCaught(raw.replace('on storage.objects for insert to anon', 'on storage.objects for select to anon'), 'policy feedback_shots_insert_anon is for select')
        self.assertCaught(raw + "\n-- key: sb_secret_abcdef\n", 'secret-like literal')
        self.assertCaught(raw + "\n-- see https://example.supabase.co/x\n", 'url literal')
        self.assertCaught(raw.replace("where name = 'teams_feedback_webhook_url'", "where name = 'teams_webhook_url'"), 'webhook is not read from Vault')
        self.assertCaught(raw.replace("raise warning 'feedback_notify_teams failed: sqlstate %', sqlstate;", "raise warning 'failed: %', sqlerrm;"), 'sqlerrm')
        self.assertCaught(raw.replace("revoke all on function public.feedback_notify_teams() from public, anon, authenticated;", ''), 'executable by public roles')
        self.assertCaught(raw.replace("'text', txt)", "'text', txt || new.contact)"), 'only concatenation')
        self.assertCaught(raw.replace('revoke all on public.feedback from anon, authenticated, public;\n', '') + '\nrevoke all on public.feedback from anon, authenticated, public;\n', 'revoke all must precede')

    def test_no_secret_or_address_in_the_file(self):
        raw = read()
        for needle in ('eyJ', 'sb_secret_', 'sb_publishable_', 'service_role'):
            self.assertNotIn(needle, raw)
        self.assertEqual([m.group(0) for m in re.finditer(r'https?://\S*', raw)], ["https://'"])


if __name__ == '__main__':
    unittest.main()

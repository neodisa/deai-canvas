"""Знімок поведінки 0.20.0 (`fixtures/liga-migration/before-4d4b.json`, етап 4d-4b, Task 1): на місці, без шляхів машини, достатньо великий, форма — та, на яку
спираються тести паритету (`AfterMigrationParity4d4b`). Сам знімок не переганяємо: еталон «до»; генератор відмовляється працювати на зміненому `app/`/`bin/`."""
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
FIXTURE_SHA256 = '428de53718091d44d180e8a8036bdfde07c39846459dd69fbbd1461001a0d4c8'
ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')


def _flat(o, p=''):
    if isinstance(o, dict):
        return {k2: v2 for k, v in o.items() for k2, v2 in _flat(v, '%s/%s' % (p, k)).items()}
    if isinstance(o, list):
        return {k2: v2 for i, v in enumerate(o) for k2, v2 in _flat(v, '%s[%d]' % (p, i)).items()}
    return {p: o}


class Before4d4bShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_the_reference_bytes_are_pinned(self):
        """Еталон «до» не правиться мовчки: зміна змісту — свідомий перезапис із замороженої копії й нова сума тут."""
        self.assertEqual(hashlib.sha256(self.raw.encode('utf-8')).hexdigest(), FIXTURE_SHA256)

    def test_meta(self):
        m = self.snap['meta']
        self.assertEqual((m['version'], m['source_commit'], m['generator']), ('0.20.0', '0d52a74', 'tests/make_before_4d4b.py'))
        self.assertEqual(self.snap['non_loopback_attempts'], 10)

    def test_five_stands_and_their_sections(self):
        st = self.snap['stands']
        self.assertEqual(sorted(st), ['differs', 'partial', 'plain', 'regular', 'unmigrated'])
        full = ['api', 'capabilities', 'dashboard_sync', 'isolation', 'provider', 'registry_ssh', 'root_keys', 'vcs_target']
        self.assertEqual(sorted(st['differs']), full)
        self.assertEqual(sorted(st['partial']), full)
        self.assertEqual(sorted(st['regular']), sorted(full + ['startup_text']))
        self.assertEqual(sorted(st['unmigrated']), sorted(full + ['startup_text']))
        self.assertEqual(sorted(st['plain']), ['api', 'capabilities', 'dashboard_sync', 'provider', 'root_keys'])

    def test_the_dashboard_sync_section_records_launch_behaviour_on_every_stand(self):
        """`dashboard_sync[<оточення>][<in_space|implicit_space>] = {called, args}`: те, що 0.20.0 запускає (чи ні) для пуску синку дашборда."""
        for name, st in self.snap['stands'].items():
            ds = st['dashboard_sync']
            self.assertEqual(sorted(ds), ['isolated', 'no_overview', 'non_isolated'], name)
            for env, v in ds.items():
                self.assertEqual(sorted(v), ['implicit_space', 'in_space'], (name, env))
                for where, r in v.items():
                    self.assertEqual(sorted(r), ['args', 'called'], (name, env, where))
                    self.assertEqual(r['called'], r['args'] is not None, (name, env, where))
            for env in ('isolated', 'no_overview'):                    # ізоляція й DC_NO_OVERVIEW — тиша всюди
                self.assertFalse(any(r['called'] for r in ds[env].values()), (name, env))
        for name in ('regular', 'differs', 'partial', 'unmigrated'):   # ЛІГА: запуск за легасі-ключем і в запиті, і без нього
            for where, r in self.snap['stands'][name]['dashboard_sync']['non_isolated'].items():
                self.assertEqual(r['args'], ['legacy', True, ['--space', 'legacy']], (name, where))
        plain = self.snap['stands']['plain']['dashboard_sync']['non_isolated']
        self.assertFalse(plain['in_space']['called'])                 # звичайний простір без модуля дашборда: нічого
        self.assertTrue(plain['implicit_space']['called'])            # неявний простір запиту — це ЛІГА

    def test_the_snapshot_records_the_implicit_provider_of_0_20(self):
        """Те, що після 0.21 ЗНИКАЄ: у неявному просторі й у немігрованій ЛІЗІ шість ролей — `Implicit`/`legacy`."""
        for name in ('regular', 'plain'):
            imp = self.snap['stands'][name]['provider']['implicit_space']
            self.assertEqual({r: imp[r]['api'] for r in ROLES if r != 'tokens'}, {r: 'legacy' for r in ROLES if r != 'tokens'}, name)
        un = self.snap['stands']['unmigrated']['provider']['in_space']
        self.assertEqual({r: un[r]['type'] for r in ROLES if r != 'tokens'}, {r: 'Implicit' for r in ROLES if r != 'tokens'})
        self.assertEqual(self.snap['stands']['regular']['provider']['in_space']['publish']['type'], 'Module')

    def test_the_originals_are_in_the_root_before_the_step(self):
        for name in ('regular', 'differs', 'partial', 'unmigrated'):
            keys = self.snap['stands'][name]['root_keys']
            for k in ('supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip', 'preview_password'):
                self.assertIn(k, keys, (name, k))

    def test_big_enough_to_mean_something(self):
        for name, st in self.snap['stands'].items():
            self.assertGreater(len(_flat(st)), 130 if name == 'plain' else 180, name)

    def test_machine_independent(self):
        """⛔ Ні справжніх шляхів, ні імен, ні тимчасових тек, ні часових штампів; значення — вигадані."""
        me = os.path.basename(os.path.expanduser('~'))
        # префікси складаємо з частин: у самому файлі тесту літералів домашніх/тимчасових тек нема
        prefixes = ('/' + 'Users/', '/' + 'home/', '/' + 'var/' + 'folders', '/' + 'private/', '/' + 'tmp/', 'before-4d4b-', 'C:' + '\\')
        for bad in prefixes + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))
        self.assertIsNone(re.search(r'\d{8}-\d{6}', self.raw))            # штампи бекапів → `<stamp>`

    def test_the_generator_refuses_to_overwrite_the_reference_on_changed_code(self):
        """Генератор у зміненому `app/` (тут — без `.git`-копії, тож перевіряємо лише, що він відмовляє за зашитим комітом у справжньому репо)."""
        src = os.path.join(_HERE, 'make_before_4d4b.py')
        with open(src, encoding='utf-8') as f:
            text = f.read()
        self.assertIn("return '0d52a74'", text)
        self.assertIn('sys.exit(2)', text)


if __name__ == '__main__':
    unittest.main()

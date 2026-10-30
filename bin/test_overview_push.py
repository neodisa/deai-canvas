import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overview_push as ov

class TestRow(unittest.TestCase):
    def _st(self, **kw):
        base = dict(iterations=1, published=False, gitlab_fresh=True,
                    open_comments=0, figma=None, code_url=None, finalized=False)
        base.update(kw); return base

    def test_status_mapping(self):
        self.assertEqual(ov.map_status(self._st(published=True, open_comments=0, finalized=True)), "done")
        self.assertEqual(ov.map_status(self._st(open_comments=3)), "review")
        self.assertEqual(ov.map_status(self._st(published=True, finalized=False)), "pub")
        self.assertEqual(ov.map_status(self._st()), "work")

    def test_preview_source_code_beats_figma(self):
        self.assertEqual(ov.preview_source(code_url="http://x", figma="http://f"), "code")
        self.assertEqual(ov.preview_source(code_url=None, figma="http://f"), "figma")
        self.assertEqual(ov.preview_source(code_url=None, figma=None), None)

    def test_build_row_fields(self):
        task = {"title": "Суди", "jira": "LIGA-7003", "profile": "united",
                "figma": "http://f", "gitlab": {"path": "mockup/courts"}}
        row = ov.build_row("courts", task, self._st(iterations=2, published=True, finalized=True,
                                                    code_url="http://p"), designer="Lead", designer_key="s@x")
        self.assertEqual(row["id"], "courts")
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["thumb_source"], "code")
        self.assertEqual(row["jira"], "LIGA-7003")
        self.assertEqual(row["source"], "canvas")
        self.assertIn("updated_at", row)

    def test_no_pii_in_row(self):
        task = {"title": "Компанія ЄДРПОУ 12345678", "jira": "LIGA-1"}
        self.assertTrue(ov.row_has_pii(ov.build_row("x", task, self._st(), "S", "s@x")))

    def test_enrichment_fields_in_row(self):
        task = {"title": "Суди", "jira": "LIGA-7003", "comment_project": "courts-widget",
                "gitlab": {"repo": "git@gitlab.internal.example:ORG/united-design.git",
                           "path": "mockup/courts"}}
        st = self._st(iterations=4, published=True,
                      last_update="17.07.2026 14:59", backup_at="17.07.2026 15:35")
        row = ov.build_row("courts", task, st, "Lead", "s@x")
        self.assertEqual(row["iterations"], 4)
        # сирі дані для промпта «відкрити в канвасі»
        self.assertEqual(row["gitlab_repo"], "git@gitlab.internal.example:ORG/united-design.git")
        self.assertEqual(row["gitlab_path"], "mockup/courts")
        self.assertEqual(row["comment_project"], "courts-widget")
        self.assertEqual(row["gitlab_url"],
                         "https://gitlab.internal.example/ORG/united-design/-/tree/main/mockup/courts")
        self.assertEqual(row["updated_at"], "2026-07-17T14:59:00+03:00")
        self.assertEqual(row["backup_at"], "2026-07-17T15:35:00+03:00")


class TestEnrichHelpers(unittest.TestCase):
    def test_gitlab_web_ssh_to_https(self):
        # без path — корінь проєкту
        self.assertEqual(
            ov.gitlab_web({"repo": "git@gitlab.internal.example:ORG/united-design.git"}),
            "https://gitlab.internal.example/ORG/united-design")
        # з path — дип-лінк на теку в гілці main
        self.assertEqual(
            ov.gitlab_web({"repo": "git@gitlab.internal.example:ORG/united-design.git",
                           "path": "mockup/courts"}),
            "https://gitlab.internal.example/ORG/united-design/-/tree/main/mockup/courts")
        self.assertIsNone(ov.gitlab_web({"path": "mockup/x"}))  # нема repo
        self.assertIsNone(ov.gitlab_web(None))

    def test_to_iso_parses_kyiv_datetime(self):
        self.assertEqual(ov.to_iso("17.07.2026 14:59"), "2026-07-17T14:59:00+03:00")
        self.assertEqual(ov.to_iso("20.07.2026"), "2026-07-20T00:00:00+03:00")
        self.assertIsNone(ov.to_iso(None))
        self.assertIsNone(ov.to_iso("вчора"))

    def test_iter_count_uses_max_ordinal(self):
        # канвас зберіг лише останню ітерацію it4 → реальна кількість = 4
        self.assertEqual(ov.iter_count([{"id": "it4", "from": "it3"}]), 4)
        self.assertEqual(ov.iter_count([{"id": "it1"}, {"id": "it2"}, {"id": "it3"}]), 3)
        self.assertEqual(ov.iter_count([{"note": "no id"}, {"note": "x"}]), 2)  # фолбек — довжина
        self.assertEqual(ov.iter_count([]), 0)


class TestDiscover(unittest.TestCase):
    def test_humanize(self):
        self.assertEqual(ov._humanize("erb"), "Erb")
        self.assertEqual(ov._humanize("ownership-structure"), "Ownership structure")
        self.assertEqual(ov._humanize(""), "")

    def test_discover_row_from_registry_entry(self):
        entry = {"id": "erb", "title": "ЄРБ · Єдиний реєстр боржників", "profile": "united",
                 "gitlab": {"repo": "git@gitlab.internal.example:ORG/united-design.git",
                            "path": "mockup/erb"}}
        row = ov.discover_row("erb", entry)
        self.assertEqual(row["id"], "erb")
        self.assertEqual(row["name"], "ЄРБ · Єдиний реєстр боржників")  # з реєстру, не вгадане з id
        self.assertEqual(row["status"], "pub")
        self.assertEqual(row["source"], "registry")
        self.assertEqual(row["gitlab_path"], "mockup/erb")
        self.assertEqual(row["gitlab_url"],
                         "https://gitlab.internal.example/ORG/united-design/-/tree/main/mockup/erb")
        # базова картка — без коду/статусу Jira (збагатиться, коли з нею попрацюють)
        self.assertNotIn("jira_status", row)
        self.assertIsNone(row.get("code_url"))

    def test_discover_row_direction_repo_and_path_fallback(self):
        """Напрямок читається з gitlab_repo (окремої колонки немає), path — за конвенцією."""
        entry = {"id": "blog", "title": "LIGA-7005 · Блог", "profile": "seo",
                 "jira": "LIGA-7005",
                 "gitlab": {"repo": "git@gitlab.internal.example:ORG/ligaseo-design.git"}}
        row = ov.discover_row("blog", entry)
        self.assertIn("ligaseo-design", row["gitlab_repo"])
        self.assertEqual(row["gitlab_path"], "mockup/blog")
        self.assertEqual(row["jira"], "LIGA-7005")

    def test_discover_row_without_gitlab_has_no_urls(self):
        row = ov.discover_row("x", {"id": "x", "title": "X", "profile": "seo"})
        self.assertNotIn("gitlab_repo", row)
        self.assertNotIn("gitlab_url", row)
        self.assertEqual(row["name"], "X")


class TestJiraStatuses(unittest.TestCase):
    def test_no_creds_returns_empty(self):
        real = ov._jira_creds
        ov._jira_creds = lambda: (None, None)
        try:
            self.assertEqual(ov.jira_statuses(["LIGA-1"]), {})
        finally:
            ov._jira_creds = real

    def test_empty_keys_returns_empty(self):
        self.assertEqual(ov.jira_statuses([]), {})

    def test_parses_status_and_category(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self):
                return json.dumps({"issues": [
                    {"key": "LIGA-7003", "fields": {"status": {
                        "name": "UI Work", "statusCategory": {"key": "indeterminate"}}}},
                    {"key": "LIGA-7008", "fields": {"status": {
                        "name": "To Do", "statusCategory": {"key": "new"}}}},
                ]}).encode("utf-8")

        real_creds = ov._jira_creds
        real_open = ov.urllib.request.urlopen
        ov._jira_creds = lambda: ("e@x", "tok")
        ov.urllib.request.urlopen = lambda req, timeout=None, context=None: FakeResponse()
        try:
            got = ov.jira_statuses(["LIGA-7003", "LIGA-7008"])
        finally:
            ov._jira_creds = real_creds
            ov.urllib.request.urlopen = real_open
        self.assertEqual(got["LIGA-7003"], {"name": "UI Work", "cat": "indeterminate"})
        self.assertEqual(got["LIGA-7008"], {"name": "To Do", "cat": "new"})


class TestSupabaseGetter(unittest.TestCase):
    """`_supabase()` без оточення й без конфігу установки — зрозуміла помилка, а не `None.rstrip` (4b-2).
    Старий файл задач — тимчасовий порожній (справжній `tasks.json` не читається), `SUPABASE_*` прибрані."""

    def test_no_env_and_no_config_is_a_clear_error_without_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "tasks.json")
            with open(empty, "w", encoding="utf-8") as f:
                f.write("{}")
            saved = {k: os.environ.get(k) for k in
                     ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "DC_TASKS_FILE")}
            for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY"):
                os.environ.pop(k, None)
            os.environ["DC_TASKS_FILE"] = empty
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    ov._supabase()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertIn("не налаштовано", str(ctx.exception))
        self.assertNotIn("https://", str(ctx.exception))

    def test_config_of_the_installation_is_used_when_env_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "tasks.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"supabase_url": "https://demo.supabase.co/", "supabase_key": "sb_publishable_test"}, f)
            saved = {k: os.environ.get(k) for k in
                     ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "DC_TASKS_FILE")}
            for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY"):
                os.environ.pop(k, None)
            os.environ["DC_TASKS_FILE"] = cfg
            try:
                got = ov._supabase()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertEqual(got, ("https://demo.supabase.co", "sb_publishable_test"))


class TestUpsertProject(unittest.TestCase):
    def setUp(self):
        self._old_url = os.environ.get("SUPABASE_URL")
        self._old_key = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_URL"] = "https://demo.supabase.co"
        os.environ["SUPABASE_KEY"] = "testkey"

    def tearDown(self):
        if self._old_url is None:
            os.environ.pop("SUPABASE_URL", None)
        else:
            os.environ["SUPABASE_URL"] = self._old_url
        if self._old_key is None:
            os.environ.pop("SUPABASE_KEY", None)
        else:
            os.environ["SUPABASE_KEY"] = self._old_key

    def test_upsert_project_posts_expected_request(self):
        captured = {}

        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None, context=None):
            captured["request"] = req
            return FakeResponse()

        real_urlopen = ov.urllib.request.urlopen
        ov.urllib.request.urlopen = fake_urlopen
        try:
            status = ov.upsert_project({"id": "x", "name": "n"})
        finally:
            ov.urllib.request.urlopen = real_urlopen

        self.assertEqual(status, 204)
        req = captured["request"]
        self.assertTrue(req.full_url.endswith("/rest/v1/overview_projects?on_conflict=id"))
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.headers.get("Apikey"), "testkey")
        self.assertEqual(req.headers.get("Authorization"), "Bearer testkey")
        self.assertIn("resolution=merge-duplicates", req.headers.get("Prefer", ""))
        body = json.loads(req.data.decode("utf-8"))
        self.assertIsInstance(body, list)
        self.assertIn({"id": "x", "name": "n"}, body)


class TestSync(unittest.TestCase):
    def _write_iters(self, d, meta):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "iterations.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # task1: 2 ітерації, НЕ опубліковано
        self.task1_dir = os.path.join(self.tmp, "task1")
        self._write_iters(self.task1_dir, {"iterations": [
            {"id": "it1", "published": False}, {"id": "it2", "published": False}]})
        # task2: dir інтенційно не існує (missing-dir case)
        self.task2_dir = os.path.join(self.tmp, "task2_missing")
        # task3: опубліковано (є publish_url) → code_url має бути ним, status=pub
        self.task3_dir = os.path.join(self.tmp, "task3")
        self._write_iters(self.task3_dir, {
            "iterations": [{"id": "it1", "published": True}],
            "publish_url": "https://dc-task3.vercel.app"})
        self.fixture = {
            "current": "task1",
            "tasks": {
                "task1": {"dir": self.task1_dir, "title": "Задача Один",
                          "jira": "LIGA-1", "profile": "united"},
                "task2": {"dir": self.task2_dir, "title": "Задача Два",
                          "jira": "LIGA-2", "profile": "united"},
                "task3": {"dir": self.task3_dir, "title": "Задача Три",
                          "jira": "LIGA-3", "profile": "united"},
            },
        }
        self.fixture_path = os.path.join(self.tmp, "tasks.json")
        with open(self.fixture_path, "w", encoding="utf-8") as f:
            json.dump(self.fixture, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_task_state_counts_iterations(self):
        st1 = ov.task_state(self.fixture["tasks"]["task1"])
        self.assertEqual(st1["iterations"], 2)
        self.assertFalse(st1["published"])
        self.assertFalse(st1["finalized"])
        self.assertEqual(st1["open_comments"], 0)
        self.assertIsNone(st1["code_url"])  # не опубліковано → без коду

        # missing dir must never raise, and counts as zero
        st2 = ov.task_state(self.fixture["tasks"]["task2"])
        self.assertEqual(st2["iterations"], 0)
        self.assertFalse(st2["published"])

        # published task → code_url = реальний publish_url (НЕ localhost)
        st3 = ov.task_state(self.fixture["tasks"]["task3"])
        self.assertEqual(st3["iterations"], 1)
        self.assertTrue(st3["published"])
        self.assertEqual(st3["code_url"], "https://dc-task3.vercel.app")

    def test_cmd_sync_upserts_each_task(self):
        captured = []

        def fake_upsert(row):
            captured.append(row)
            return 204

        real_upsert = ov.upsert_project
        real_loader = ov.load_tasks_file
        real_counts = ov.open_comment_counts
        real_jstatus = ov.jira_statuses
        real_discover = ov.discover_projects
        real_fixture = ov._fixture_reason
        ov.upsert_project = fake_upsert
        ov.load_tasks_file = lambda path=None: self.fixture
        # ⛔ До 27.09.2026 цей тест НЕ підміняв discover_projects — і крок 0
        # синку ходив у справжній клон реєстру (ensure_clone → git fetch/clone
        # по SSH). Тест про локальні задачі, реєстр йому не потрібен.
        ov.discover_projects = lambda cfg: {}
        # Теки задач фікстури лежать у tempfile — тобто самі по собі «фікстура»
        # для бар'єра `_fixture_reason` (див. TestFixturesNeverReachDashboard).
        # Тут перевіряється інше — підрахунок і статуси, — тому бар'єр вимкнено.
        ov._fixture_reason = lambda task: None
        # task1 без comment_project → ключ «dc/task1»; 5 відкритих коментарів → статус review
        ov.open_comment_counts = lambda: {"dc/task1": 5}
        # task3 (LIGA-3) має свіжий Jira-статус
        ov.jira_statuses = lambda keys: {"LIGA-3": {"name": "UI Work", "cat": "indeterminate"}}
        try:
            ov.cmd_sync()
        finally:
            ov.upsert_project = real_upsert
            ov.load_tasks_file = real_loader
            ov.open_comment_counts = real_counts
            ov.jira_statuses = real_jstatus
            ov.discover_projects = real_discover
            ov._fixture_reason = real_fixture

        # task2 (теки немає) свідомо ПРОПУСКАЄТЬСЯ: раніше він їхав із нулями і
        # вихолощував спільний рядок — див. TestNoHollowingOtherPeoplesCards.
        # Головне тут — синк не падає через відсутню теку, а доходить до решти задач.
        self.assertEqual(len(captured), 2)
        by_id = {r["id"]: r for r in captured}
        self.assertEqual(set(by_id), {"task1", "task3"})
        # open_comments у рядок НЕ їде з 07.08.2026 (рахує тригер БД, див.
        # build_row); локальний лічильник лише рухає статус.
        self.assertNotIn("open_comments", by_id["task1"])
        self.assertEqual(by_id["task1"]["status"], "review")  # відкриті коменти → рев'ю
        self.assertEqual(by_id["task3"]["status"], "pub")
        self.assertEqual(by_id["task3"]["code_url"], "https://dc-task3.vercel.app")
        self.assertEqual(by_id["task3"]["thumb_source"], "code")
        # task3 отримав свіжий Jira-статус; task1/task2 — ні (ключ відсутній у мапі)
        self.assertEqual(by_id["task3"]["jira_status"], "UI Work")
        self.assertEqual(by_id["task3"]["jira_status_cat"], "indeterminate")
        self.assertIn("jira_synced_at", by_id["task3"])
        self.assertNotIn("jira_status", by_id["task1"])  # немає свіжого → ключ пропущено


class TestNoHollowingOtherPeoplesCards(unittest.TestCase):
    """Синк дашборду не має псувати чужі картки.

    Інцидент 03.08.2026: `cmd_sync` ходив по ВСІХ задачах локального tasks.json і
    відправляв повний payload разом із None-ами. `registry.py pull` вписує в
    tasks.json усі задачі реєстру — включно з чужими, у яких теки на цій машині
    немає. Для них task_state() віддавав нулі, а merge-duplicates записував їх у
    спільний рядок: картка колеги втрачала code_url/pages/jira, статус падав у
    «work», авторство переписувалось на того, хто синхронізувався, а updated_at
    ставав «щойно» — і картка випливала нагору як свіжа.
    """

    def _st(self, **kw):
        base = dict(iterations=0, published=False, open_comments=0,
                    figma=None, code_url=None, finalized=False)
        base.update(kw)
        return base

    def test_row_never_carries_nulls(self):
        """None-ключів у payload не має бути взагалі — вони затирають наявне."""
        task = {"title": "Задача без нічого"}  # ні jira, ні figma, ні gitlab
        row = ov.build_row("t1", task, self._st(), "Lead", "s@x")
        self.assertEqual([k for k, v in row.items() if v is None], [])
        for gone in ("jira", "figma_url", "code_url", "pages", "backup_at"):
            self.assertNotIn(gone, row, f"{gone}=None не має їхати в Supabase")

    def test_pages_kept_when_known(self):
        """Фільтр None не має ламати передачу реальних значень."""
        row = ov.build_row("t1", {"title": "X"}, self._st(pages=3, iterations=2), "S", "s@x")
        self.assertEqual(row["pages"], 3)
        self.assertEqual(row["iterations"], 2)

    def test_foreign_card_keeps_its_author(self):
        task = {"title": "Чужа задача", "owner": "Olha Sydoruk",
                "owner_key": "designer2@example.com"}
        row = ov.build_row("doc-check", task, self._st(), "Designer One", "designer@x")
        self.assertNotIn("designer", row, "авторство чужої картки не присвоюємо")
        self.assertNotIn("designer_key", row)

    def test_foreign_card_link_stays_the_owners(self):
        """Превʼю спільної задачі — у власника (рішення 29.09.2026). Не-власник
        публікує у СВОЄ превʼю, і його синк не сміє підмінити посилання на картці."""
        task = {"title": "Чужа задача", "owner": "Olha Sydoruk",
                "owner_key": "designer2@example.com"}
        st = self._st(published=True, code_url="https://pv-9-mine.vercel.app")
        row = ov.build_row("doc-check", task, st, "Designer One", "designer@x")
        self.assertNotIn("code_url", row)
        self.assertNotIn("thumb_source", row)

    def test_machine_without_git_email_is_not_a_stranger(self):
        """Без git-email `_identity` дає заглушку «designer» — це «особи немає»,
        а не «чужий»: інакше власні картки такої машини губили б лінк."""
        task = {"title": "Моя", "owner": "S", "owner_key": "designer@x"}
        st = self._st(published=True, code_url="https://pv-1.vercel.app")
        row = ov.build_row("courts", task, st, "S", "designer")
        self.assertEqual(row.get("code_url"), "https://pv-1.vercel.app")

    def test_own_card_still_carries_the_link(self):
        task = {"title": "Моя", "owner": "Designer One", "owner_key": "designer@x"}
        st = self._st(published=True, code_url="https://pv-1.vercel.app")
        row = ov.build_row("courts", task, st, "Designer One", "designer@x")
        self.assertEqual(row["code_url"], "https://pv-1.vercel.app")

    def test_own_card_still_signed(self):
        task = {"title": "Моя задача", "owner": "Designer One", "owner_key": "designer@x"}
        row = ov.build_row("courts", task, self._st(), "Designer One", "designer@x")
        self.assertEqual(row["designer"], "Designer One")
        self.assertEqual(row["designer_key"], "designer@x")

    def test_card_without_known_owner_is_signed(self):
        """Реєстр недоступний (нема VPN) → owner_key невідомий: підписуємо як своє,
        інакше свіжозаведені задачі лишались би без автора."""
        row = ov.build_row("new", {"title": "Нова"}, self._st(), "Lead", "s@x")
        self.assertEqual(row["designer"], "Lead")

    def test_sync_skips_tasks_without_local_dir(self):
        """cmd_sync не чіпає задачі, теки яких немає на цій машині."""
        tmp = tempfile.mkdtemp(prefix="ov-skip-")
        self.addCleanup(shutil.rmtree, tmp, True)
        here = os.path.join(tmp, "mine")
        os.makedirs(os.path.join(here, "iterations", "it1"))
        with open(os.path.join(here, "iterations.json"), "w", encoding="utf-8") as f:
            json.dump({"iterations": [{"id": "it1", "date": "01.08.2026 10:00"}]}, f)

        cfg = {"tasks": {
            "mine": {"title": "Моя", "dir": here},
            "foreign": {"title": "Чужа", "dir": os.path.join(tmp, "nope"),
                        "owner": "Olha", "owner_key": "m@x"},
        }}
        sent = []
        orig = (ov.load_tasks_file, ov.upsert_project, ov.discover_projects,
                ov.open_comment_counts, ov.jira_statuses, ov._fixture_reason)
        ov.load_tasks_file = lambda path=None: cfg
        ov.upsert_project = lambda row, ignore=False: sent.append(row) or 201
        ov.discover_projects = lambda c: {}
        ov.open_comment_counts = lambda: {}
        ov.jira_statuses = lambda keys: {}
        # Тека «mine» — у tempfile, тобто для бар'єра фікстур вона фікстура;
        # тут перевіряється пропуск задач БЕЗ теки, тому бар'єр вимкнено.
        ov._fixture_reason = lambda task: None
        try:
            ov.cmd_sync()
        finally:
            (ov.load_tasks_file, ov.upsert_project, ov.discover_projects,
             ov.open_comment_counts, ov.jira_statuses, ov._fixture_reason) = orig

        ids = [r["id"] for r in sent]
        self.assertIn("mine", ids)
        self.assertNotIn("foreign", ids,
                         "задачу без локальної теки синк не має торкатись")


class TestFixturesNeverReachDashboard(unittest.TestCase):
    """Фікстура тесту не сміє стати карткою на КОМАНДНОМУ дашборді.

    Інцидент 15.09.2026: фікстура `nova` (gitlab.repo у /var/folders/…)
    протекла в реєстр, і крок 0 синку (`discover_row`) виставив її на дашборд
    карткою «Нова» зі статусом `pub`. Бар'єр тут — справжній
    `registry.fixture_path_reason`, НЕ підмінений.
    """

    NOVA = {"schema": 1, "id": "nova", "title": "Нова", "profile": "united",
            "gitlab": {"repo": "/var/folders/pn/lqccppvd47s08wdtnyhh0rkr0000gp/T/"
                               "dc-syncverify-slc0axws/origin.git",
                       "path": "mockup/t1"},
            "owner": "Designer One", "updated_at": "2026-09-15T10:50:29Z"}
    ERB = {"id": "erb", "title": "ЄРБ", "profile": "united",
           "gitlab": {"repo": "git@gitlab.internal.example:ORG/united-design.git",
                      "path": "mockup/erb"}}

    def _run(self, fn, cfg, registry):
        import io
        from contextlib import redirect_stdout
        sent, buf = [], io.StringIO()
        orig = (ov.load_tasks_file, ov.upsert_project, ov.discover_projects,
                ov.open_comment_counts, ov.jira_statuses)
        ov.load_tasks_file = lambda path=None: cfg
        ov.upsert_project = lambda row, ignore=False: sent.append(row) or 201
        ov.discover_projects = lambda c: dict(registry)
        ov.open_comment_counts = lambda: {}
        ov.jira_statuses = lambda keys: {}
        try:
            with redirect_stdout(buf):
                fn()
        finally:
            (ov.load_tasks_file, ov.upsert_project, ov.discover_projects,
             ov.open_comment_counts, ov.jira_statuses) = orig
        return [r["id"] for r in sent], buf.getvalue()

    def test_sync_does_not_send_registry_fixture(self):
        ids, out = self._run(ov.cmd_sync, {"tasks": {}},
                             {"nova": self.NOVA, "erb": self.ERB})
        self.assertIn("erb", ids, "контроль: чиста картка з реєстру їде як завжди")
        self.assertNotIn("nova", ids, "фікстура з реєстру поїхала на дашборд")
        self.assertIn("«nova»", out, "відмова мусить бути названа вголос")

    def test_discover_does_not_send_registry_fixture(self):
        ids, out = self._run(ov.cmd_discover, {"tasks": {}},
                             {"nova": self.NOVA, "erb": self.ERB})
        self.assertEqual(ids, ["erb"])
        self.assertIn("«nova»", out)

    def test_sync_does_not_send_local_fixture_even_if_its_dir_exists(self):
        """15.09.2026 живий tasks.json затерла фікстура. Поки її тимчасова
        тека ще існує, пропуск «теки немає» її НЕ зупиняє — лише бар'єр."""
        tmp = tempfile.mkdtemp(prefix="dc-syncverify-")
        self.addCleanup(shutil.rmtree, tmp, True)
        d = os.path.join(tmp, "nova")
        os.makedirs(d)
        with open(os.path.join(d, "iterations.json"), "w", encoding="utf-8") as f:
            json.dump({"iterations": [{"id": "it1", "published": True}],
                       "publish_url": "https://x.vercel.app"}, f)
        ids, out = self._run(ov.cmd_sync,
                             {"tasks": {"nova": {"title": "Нова", "dir": d}}}, {})
        self.assertEqual(ids, [])
        self.assertIn("«nova»", out)


if __name__ == "__main__":
    unittest.main()

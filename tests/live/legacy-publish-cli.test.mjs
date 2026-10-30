/**
 * Живе проведення публікації простору ЛІГА через модуль `vercel-publish` у режимі `cli` (Deai 4b-1, Task 6).
 *
 * Юніти (`tests/test_publish_module.py`, `tests/test_vercel_publish.py`) доводять кожну ланку; тут увесь шлях разом, БЕЗ
 * підміни `/api/publish`: клік «Опублікувати» в смузі → справжній `POST /api/publish` → адаптер ЛІГИ → модуль → ФАЛЬШИВИЙ
 * `npx` (`tests/fake_npx.py`) → текст ЛІГИ у вікні, яке бачить людина.
 *
 * ⛔ Мережі нема й бути не може. Сценарій — `deploy` із кодом 0, але БЕЗ жодної адреси `*.vercel.app` у виводі: модуль кидає
 * `vercel-no-url`, ядро віддає `deploy_error = _LEGACY_NO_URL` і нічого не зберігає. Це єдиний «успішний» шлях деплою, що не
 * потребує `api.vercel.com` (перевірку сторінки модуль робить лише ПІСЛЯ знайденої адреси). Фальшивий `npx` ставимо першим у
 * `PATH` процесу сервера: ядро шукає `npx` через `_node_bin`, а той дивиться в `PATH` процесу насамперед.
 *
 * Мапа «сценарій → запобіжник» (мутаційно):
 *   · текст у вікні — `_legacy_deploy_error` (`app/serve.py`): без гілки `vercel-no-url` людина побачила б сирий хвіст виводу;
 *   · `link` із `--project pv-<8 цифр>` — привʼязка задача→проєкт (`_vercel_project` + `state` у `_publish_legacy_call`);
 *   · `deploy --prod --yes` у `publish/` задачі — що саме запускає модуль і де;
 *   · жодних `list`/`remove`: адреси нема → прибирати нічого (чистка лише після успіху).
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { VIEW, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 13800;

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const TESTS = path.join(ROOT, "tests");

/** Текст ЛІГИ для `vercel-no-url` — зі справжнього `app/serve.py` (`_LEGACY_NO_URL`), а не з пам'яті: збіг байт у байт. */
function legacyNoUrl() {
  const src = readFileSync(path.join(ROOT, "app", "serve.py"), "utf8");
  const m = src.match(/_LEGACY_NO_URL = \(\s*'([^']*)'\s*'([^']*)'\s*\)/);
  assert.ok(m, "не знайшов _LEGACY_NO_URL у app/serve.py — змінився формат константи");
  return m[1] + m[2];
}

/** Журнал фальшивого `npx`: `[{argv, cwd}]`, через сам `tests/fake_npx.py` (один формат на Python і Node). */
function npxCalls(dir) {
  const r = spawnSync("python3", ["-B", "-c",
    "import sys, json; sys.path.insert(0, sys.argv[1]); import fake_npx; print(json.dumps(fake_npx.calls(sys.argv[2])))",
    TESTS, dir], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

test("публікація ЛІГИ: клік → модуль → фальшивий npx → текст ЛІГИ «URL не знайдено»", async (t) => {
  const fakeDir = mkdtempSync(path.join(tmpdir(), "dc-live-npx-"));
  t.after(() => rmSync(fakeDir, { recursive: true, force: true }));
  const made = spawnSync("python3", ["-B", "-c",
    "import sys; sys.path.insert(0, sys.argv[1]); import fake_npx; "
    + "fake_npx.make(sys.argv[2], {'deploy': {'code': 0, 'stdout': 'Done, no address here'}, 'link': {'code': 0}})",
    TESTS, fakeDir], { encoding: "utf8" });
  assert.equal(made.status, 0, made.stderr);

  const A = taskFixture({
    html: (id) => `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>${id}</title></head><body><h1>${id}</h1></body></html>`,
  });
  t.after(() => rmSync(A.dir, { recursive: true, force: true }));
  const server = await startServer(null, {
    portBase: PORT_BASE,
    env: { PATH: `${fakeDir}:${process.env.PATH}` },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { a: { dir: A.dir, title: "Задача A" } } }],
  });
  t.after(() => stop(server.child));
  t.after(() => rmSync(server.home, { recursive: true, force: true }));

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const requests = [];
  const outside = [];
  context.on("request", (r) => {
    requests.push(r.url());
    if (!isLocal(r.url())) outside.push(r.url());
  });
  /* Підстраховка до свідка нижче: навіть якби сторінка пішла назовні, звідти нічого не повернеться. */
  await context.route((u) => !isLocal(u.href), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();

  /* ⛔ Справжній `POST /api/publish` — свідок, що його не підмінено: без нього «текст у вікні» міг би прийти з чого завгодно. */
  const posts = [];
  const answers = [];
  page.on("request", (r) => { if (r.method() === "POST" && new URL(r.url()).pathname === "/api/publish") posts.push(r.url()); });
  page.on("response", async (r) => {
    if (r.request().method() === "POST" && new URL(r.url()).pathname === "/api/publish") answers.push(await r.json());
  });

  await page.goto(`${server.url}/app/`);
  await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 });
  await page.click('[data-act="publish"]');

  const box = page.locator(".cv-ask");
  await box.waitFor({ timeout: 30000 });
  const shown = await box.textContent();
  const want = legacyNoUrl();
  assert.equal(posts.length, 1, "клік не дійшов до справжнього /api/publish");
  assert.ok(shown.includes(want), `у вікні нема тексту ЛІГИ «${want}»; є: ${shown}`);
  assert.equal(answers.length, 1);
  assert.equal(answers[0].deploy_error, want, "deploy_error сервера не дорівнює тексту ЛІГИ");
  assert.equal(answers[0].url, undefined, "адреси нема — і в відповіді її бути не може");

  /* Журнал фальшивого npx: що модуль запускав, де і з чим. */
  const calls = npxCalls(fakeDir);
  const sub = (c) => c.argv[2];
  const link = calls.find((c) => sub(c) === "link");
  const deploy = calls.find((c) => sub(c) === "deploy");
  assert.ok(link, `нема виклику link: ${JSON.stringify(calls)}`);
  assert.ok(deploy, `нема виклику deploy: ${JSON.stringify(calls)}`);
  assert.deepEqual(link.argv.slice(0, 2), ["--yes", "vercel"]);
  const proj = link.argv[link.argv.indexOf("--project") + 1];
  assert.match(proj ?? "", /^pv-\d{8}$/, `link без --project pv-<8 цифр>: ${link.argv.join(" ")}`);
  for (const flag of ["--prod", "--yes"]) assert.ok(deploy.argv.includes(flag), `deploy без ${flag}: ${deploy.argv.join(" ")}`);
  const publishDir = realpathSync(path.join(A.dir, "publish"));
  assert.equal(realpathSync(link.cwd), publishDir, "link запущено не в publish/ задачі");
  assert.equal(realpathSync(deploy.cwd), publishDir, "deploy запущено не в publish/ задачі");
  const bad = calls.filter((c) => ["list", "remove", "rm"].includes(sub(c)));
  assert.deepEqual(bad, [], "адреси нема → чистки старих деплоїв бути не повинно");

  /* Привʼязка задача→проєкт мінтиться ДО деплою і лишається в tasks.json, навіть коли деплой не дав адреси. */
  const cfg = JSON.parse(readFileSync(server.legacyFile, "utf8"));
  assert.match(cfg.tasks.a.vercel_project ?? "", /^pv-\d{8}$/, "vercel_project не змінтився в tasks.json");
  assert.equal(cfg.tasks.a.vercel_project, proj, "проєкт у link не збігся з тим, що записано в tasks.json");

  /* Жодної мережі: свідок, що запити були (інакше «жодного» зеленіло б на порожнечі), і жодного не-localhost. */
  assert.ok(requests.length > 5, `свідок: замало запитів (${requests.length})`);
  assert.deepEqual(outside, [], `сторінка вийшла за межі машини: ${outside.join(", ")}`);
});

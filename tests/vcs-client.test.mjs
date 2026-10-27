/**
 * Клієнт синку з git за роллю `vcs` (етап 4a, Task 6): гейт `hasVcs`/`isLegacyVcs`, смуга й палітра з підписом
 * репозиторію, тексти з підписом, мапер кодів, проводка в `app/app.js`.
 *
 * `app.js` у Node не імпортується (DOM на верхньому рівні), тож проводку стережуть статичні перевірки джерела
 * (як `tests/spaces-wiring.test.mjs`), а ВИСНОВКИ дій `glpush`/`glpull` — виконанням їхнього тіла із заглушками
 * (`actFn`): що людина побачить для кожної відповіді сервера, а не що написано в рядку.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { barModel } from "../app/bar-model.js";
import { formFields, formPatch, initialForm, refusalView, roleCardId, verdictText, writePayload } from "../app/connections-model.js";
import { resultHTML } from "../app/connections-view.js";
import { holdersByRole, initialPick, wizardSections, writePlan } from "../app/wizard-model.js";
import { wizardHTML } from "../app/wizard-view.js";
import { DICT, setLang, t } from "../app/i18n.js";
import { filterActions, paletteActions } from "../app/shell-palette.js";
import { barHTML } from "../app/shell-bar.js";
import { taskFormHTML, wireTaskForm } from "../app/space-dialogs.js";
import {
  FORM_POST_TIMEOUT_MS, TASK_VCS_POST_TIMEOUT_MS, VCS_BUSY_MAX_TRIES, VCS_BUSY_RETRY_MS, currentSpace, hasVcs, isLegacyVcs,
  requestErrText, spaceChanged, taskCreateClones, taskErrField, taskErrKey, taskErrShowsReason, taskFormError, vcsBrand, vcsErrKey, vcsFailKey,
  vcsLabel, vcsWebUrl,
} from "../app/spaces-model.js";

test.beforeEach(() => setLang("uk"));

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/* ── гейт: обидві форми відповіді ────────────────────────────────────────── */

test("hasVcs: ключ capabilities.vcs вирішує, а без ключа — integrations, як було до 4a", () => {
  assert.equal(hasVcs({ integrations: false, capabilities: { vcs: "git-sync" } }), true, "модуль у просторі без інтеграцій");
  assert.equal(hasVcs({ integrations: true, capabilities: { vcs: null } }), false, "роль вимкнено — синку нема, хоч інтеграції є");
  assert.equal(hasVcs({ integrations: true, capabilities: { publish: "legacy" } }), true, "ключа нема + інтеграції");
  assert.equal(hasVcs({ integrations: false, capabilities: { publish: "static-publish" } }), false, "ключа нема + без інтеграцій");
  assert.equal(hasVcs({ integrations: false }), false, "стара форма без capabilities");
  assert.equal(hasVcs({ integrations: true }), true);
  assert.equal(hasVcs({ id: "x" }), true, "простір без відомостей не краде в людини синк");
  assert.equal(hasVcs({ integrations: false, capabilities: { vcs: "legacy" } }), true, "'legacy' — це теж постачальник");
  assert.equal(hasVcs({ integrations: true, capabilities: null }), true, "capabilities не обʼєкт — як без ключа");
});

test("hasVcs(null) — true, як hasTeamComments(null): невідомий простір синк не відбирає", () => {
  assert.equal(hasVcs(null), true);
  assert.equal(hasVcs(undefined), true);
  assert.equal(isLegacyVcs(null), true);
  assert.equal(isLegacyVcs(undefined), true);
});

test("isLegacyVcs: 'legacy' і «ключа нема за інтеграцій» — так, модуль чи вимкнено — ні", () => {
  assert.equal(isLegacyVcs({ capabilities: { vcs: "legacy" } }), true);
  assert.equal(isLegacyVcs({ integrations: false, capabilities: { vcs: "legacy" } }), true, "ключ вирішує сам");
  assert.equal(isLegacyVcs({ integrations: true }), true, "ключа нема, інтеграції не вимкнені");
  assert.equal(isLegacyVcs({ id: "x" }), true);
  assert.equal(isLegacyVcs({ capabilities: { vcs: "git-sync" } }), false);
  assert.equal(isLegacyVcs({ integrations: true, capabilities: { vcs: "git-sync" } }), false, "модуль — не ЛІГА, хоч інтеграції є");
  assert.equal(isLegacyVcs({ integrations: true, capabilities: { vcs: null } }), false);
  assert.equal(isLegacyVcs({ integrations: false }), false);
  assert.equal(isLegacyVcs({ integrations: false, capabilities: { publish: "static-publish" } }), false);
});

test("стеля запиту створення задачі, що клонує, — 400 с: не менша за найгірший шлях сервера (validate 5 + клон 180 + другий клон 180), довша за стелю форми", () => {
  assert.equal(TASK_VCS_POST_TIMEOUT_MS, 400000);
  assert.ok(TASK_VCS_POST_TIMEOUT_MS > FORM_POST_TIMEOUT_MS);
  /* Числа сервера: `deai_modules.CHECK_TIMEOUT` (межа `validate`) і `git-sync/server.py: CLONE_TIMEOUT` (клон; за «no branch» — ще раз без `--branch`).
     Клієнт, що обриває раніше за відповідь, лишив би «помилку» при створеній задачі. */
  const py = (f) => readFileSync(new URL(f, import.meta.url), "utf8");
  const clone = Number(/^CLONE_TIMEOUT = (\d+)/m.exec(py("../app/modules/git-sync/server.py"))?.[1]);
  const validate = Number(/^CHECK_TIMEOUT = (\d+)/m.exec(py("../app/deai_modules.py"))?.[1]);
  assert.ok(clone > 0 && validate > 0, "числа сервера знайдено");
  assert.ok(TASK_VCS_POST_TIMEOUT_MS >= (validate + 2 * clone) * 1000, `стеля ${TASK_VCS_POST_TIMEOUT_MS} мс < ${validate} + 2×${clone} с сервера`);
});

/* ── підпис репозиторію: білий список GitLab/GitHub/Git, решта — за простором ─ */

const LIGA = { id: "liga", integrations: true, capabilities: { vcs: "legacy" } };
const PLAIN = { id: "plain", integrations: false, capabilities: { vcs: "git-sync" } };
/** ЛІГА (простір з інтеграціями), де синк веде явно ввімкнений `git-sync`: поле «Репозиторій» є, але сервер усе одно бере профільний gitlab. */
const LIGA_GIT = { id: "liga-git", integrations: true, capabilities: { vcs: "git-sync" } };
/** ЛІГА без ролі `vcs` (`capabilities.vcs == null`: роль «на папері» за своїм модулем, що не працює): `vcs_provider()` відмовляє одразу — клону нема. */
const LIGA_NOVCS = { id: "liga-novcs", integrations: true, capabilities: { vcs: null } };

test("taskCreateClones: сервер клонує, коли в тілі є vcs або простір з інтеграціями має роль vcs (профільний gitlab); невідомий простір — довга стеля як безпечніша", () => {
  /* `_task_new_write`: `if gitlab or (vcs and adopt_src is None)`. `gitlab` бере профіль простору з інтеграціями (`task-new`: `integrations_for(sp)` →
     `profile 'united'`), а `vcs_provider()` без ролі дає `None` — клону нема. Форма не шле `from`. */
  const body = { id: "a", title: "A", space: "x" };
  const withVcs = { ...body, vcs: { repo: "git@h:o/r.git" } };
  for (const sp of [PLAIN, NOVCS, LIGA, LIGA_GIT, LIGA_NOVCS, null, undefined, { id: "old" }]) {
    assert.equal(taskCreateClones(sp, withVcs), true, `${sp?.id}: vcs у тілі — клон завжди`);
  }
  assert.equal(taskCreateClones(LIGA, body), true, "ЛІГА, зашитий шлях");
  assert.equal(taskCreateClones(LIGA_GIT, body), true, "ЛІГА з явним git-sync: сервер бере профільний gitlab і клонує, хоч поле порожнє");
  assert.equal(taskCreateClones(PLAIN, body), false, "звичайний простір: без vcs профілю нема");
  assert.equal(taskCreateClones(NOVCS, body), false, "без ролі клонувати нічого");
  assert.equal(taskCreateClones(LIGA_NOVCS, body), false, "ЛІГА без ролі vcs: vcs_provider() = None");
  assert.equal(taskCreateClones(null, body), true, "простір невідомий: довга стеля безпечніша за обрив посеред клону");
  assert.equal(taskCreateClones(undefined, body), true);
  assert.equal(taskCreateClones({ id: "old" }, body), true, "стара форма відповіді (без integrations і capabilities) — як hasVcs/isLegacyVcs: синк не відбираємо");
  assert.equal(taskCreateClones({ id: "old", integrations: false }, body), false);
  assert.equal(taskCreateClones(PLAIN, undefined), false, "тіла нема — vcs у ньому не лежить");
  assert.equal("vcs" in body, false, "тіло не мутується");
});

test("vcsLabel: білий список; інше й порожнє — «GitLab» у ЛІГА, нейтральний «Git» деінде", () => {
  for (const space of [LIGA, PLAIN, undefined, null]) {
    assert.equal(vcsLabel("GitLab", space), "GitLab");
    assert.equal(vcsLabel("GitHub", space), "GitHub");
    assert.equal(vcsLabel("Git", space), "Git");
  }
  for (const x of ["", null, undefined, 5, "github", "Bitbucket", "Git\nEvil", "G".repeat(500), "constructor", "__proto__", "toString"]) {
    assert.equal(vcsLabel(x, LIGA), "GitLab", `ЛІГА: ${String(x).slice(0, 12)}`);
    assert.equal(vcsLabel(x, PLAIN), "Git", `звичайний: ${String(x).slice(0, 12)}`);
    assert.equal(vcsLabel(x, undefined), "GitLab", "невідомий простір (шар вимкнено) — як ЛІГА");
  }
  assert.equal(vcsLabel("", { integrations: true }), "GitLab", "стара форма з інтеграціями — ЛІГА");
  assert.equal(vcsLabel("", { integrations: false, capabilities: { vcs: "git-sync" } }), "Git");
});

test("vcsBrand: підпис, коли він не «GitLab» (GitHub, Git); для ЛІГИ й «GitLab» — порожньо", () => {
  assert.equal(vcsBrand("GitHub"), "GitHub");
  assert.equal(vcsBrand("Git"), "Git");
  assert.equal(vcsBrand("GitHub", PLAIN), "GitHub");
  assert.equal(vcsBrand("GitLab", PLAIN), "", "репо на GitLab у звичайному просторі — типовий підпис");
  for (const x of ["GitLab", "", null, undefined, 5, "github", "constructor", "__proto__", "toString", "hasOwnProperty"]) {
    assert.equal(vcsBrand(x), "", String(x));
    assert.equal(vcsBrand(x, LIGA), "", `ЛІГА ${String(x)}`);
  }
  for (const x of ["", null, undefined, "Bitbucket", "constructor"]) {
    assert.equal(vcsBrand(x, PLAIN), "Git", `звичайний простір без відомого підпису: ${String(x)}`);
  }
});

test("vcsWebUrl: лише http(s); решта — null (пункт «Історія» як без web)", () => {
  assert.equal(vcsWebUrl("https://github.com/o/r/commits/main/mockup"), "https://github.com/o/r/commits/main/mockup");
  assert.equal(vcsWebUrl("http://gitea.local/o/r"), "http://gitea.local/o/r");
  for (const x of [null, undefined, "", "file:///tmp/x", "javascript:alert(1)", "data:text/html,x", "ftp://h/x", "//h/x", "git@h:o/r", 5, {}]) {
    assert.equal(vcsWebUrl(x), null, String(x));
  }
});

test("vcsFailKey: як vcsErrKey, але в ЛІГА vcs-bad-target — без «Підключення» (ціль у tasks.json)", () => {
  for (const space of [PLAIN, LIGA]) {
    assert.equal(vcsFailKey("vcs-offline", space), "vcsErrOffline");
    assert.equal(vcsFailKey("vcs-auth", space), "vcsErrAuth");
    assert.equal(vcsFailKey("vcs-busy", space), "vcsErrBusy");
    assert.equal(vcsFailKey("vcs-error", space), null);
  }
  assert.equal(vcsFailKey("vcs-bad-target", PLAIN), "vcsErrTarget");
  assert.equal(vcsFailKey("vcs-bad-target", LIGA), null);
  assert.equal(vcsFailKey("vcs-bad-target", undefined), null, "невідомий простір — як ЛІГА");
});

test("requestErrText: HTML від send_error → рядок статусу, JSON-помилка й мережа → власний текст", () => {
  const html = Object.assign(new Error("<!DOCTYPE HTML><html><head><title>Error response</title>"), {
    status: 400, statusText: "no gitlab configured for this task", body: "<!DOCTYPE HTML>\n<html>…",
  });
  assert.equal(requestErrText(html), "no gitlab configured for this task");
  const json = Object.assign(new Error("path not found"), { status: 400, statusText: "Bad Request", body: '{"ok":false,"error":"path not found"}' });
  assert.equal(requestErrText(json), "path not found", "JSON-помилка без code — свій текст, не «Bad Request»");
  const coded = Object.assign(new Error("boom"), { status: 400, code: "vcs-error", statusText: "Bad Request", body: '{"error":"boom","code":"vcs-error"}' });
  assert.equal(requestErrText(coded), "boom");
  assert.equal(requestErrText(new TypeError("Failed to fetch")), "Failed to fetch");
  const noStatus = Object.assign(new Error("<html>x"), { status: 500, statusText: "", body: "<html>x" });
  assert.equal(requestErrText(noStatus), "<html>x", "рядка статусу нема — лишається що є");
});

test("стеля повторів «зайнято»: ≈5 с і кілька спроб, не нескінченно", () => {
  assert.equal(VCS_BUSY_RETRY_MS, 5000);
  assert.ok(VCS_BUSY_MAX_TRIES >= 2 && VCS_BUSY_MAX_TRIES <= 10);
});

/* ── смуга ───────────────────────────────────────────────────────────────── */

const base = {
  mode: "layout", view: "grid", vp: "desktop", vpw: "",
  taskId: "LIGA-7003", iterLabel: "Іт.3", iterNote: "Правки",
  hasIteration: true, flowRaw: true, pagesError: "", flowError: "",
  gl: "sync", published: true, pubStale: false, iterPub: true, pagePub: true,
  iterOnGl: true, tasksErr: "", right: null,
};
const glZone = (o) => barModel({ ...base, ...o }).zone3.find((x) => x.id === "gl");
const ids3 = (o) => barModel({ ...base, ...o }).zone3.map((x) => x.id);

test("зона синку — за hasVcs, а Teams лишається на integrations", () => {
  assert.ok(ids3({ space: { integrations: false, capabilities: { vcs: "git-sync", publish: "static-publish" } } }).includes("gl"),
    "модуль у просторі без інтеграцій дає зону синку");
  assert.ok(!ids3({ space: { integrations: true, capabilities: { vcs: null, publish: "legacy" } } }).includes("gl"),
    "роль вимкнено — зони нема");
  const pubIds = (space) => barModel({ ...base, space, teams: { channel: "c", muted: false } })
    .zone3.find((x) => x.id === "publish").items.map((x) => x.id);
  assert.ok(!pubIds({ integrations: false, capabilities: { vcs: "git-sync", publish: "static-publish" } }).includes("teamsnotify"),
    "без інтеграцій Teams нема, хоч синк є");
  assert.ok(pubIds({ integrations: true, capabilities: { vcs: null, publish: "legacy" } }).includes("teamsnotify"),
    "з інтеграціями Teams є, хоч синку нема");
});

test("підпис зони: GitHub/Git — свої ключі й поле brand; GitLab чи порожньо — типовий і БЕЗ поля brand", () => {
  const gh = glZone({ glLabel: "GitHub" });
  assert.equal(gh.labelKey, "vcsGitHub");
  assert.equal(gh.brand, "GitHub");
  const git = glZone({ glLabel: "Git" });
  assert.equal(git.labelKey, "vcsGit");
  assert.equal(git.brand, "Git");
  for (const glLabel of ["GitLab", "", undefined, null, "constructor", "__proto__"]) {
    const z = glZone({ glLabel });
    assert.equal(z.labelKey, "gitlab", String(glLabel));
    assert.ok(!("brand" in z), `у типового підпису поля brand нема (${String(glLabel)})`);
  }
  assert.equal(glZone({}).labelKey, "gitlab");
});

test("причина «збігається»: з підписом — vcsSyncWhy, без — glSync", () => {
  const why = (o) => glZone({ gl: "sync", ...o }).items.find((x) => x.id === "glpush").whyKey;
  assert.equal(why({ glLabel: "GitHub" }), "vcsSyncWhy");
  assert.equal(why({ glLabel: "Git" }), "vcsSyncWhy");
  assert.equal(why({}), "glSync");
  assert.equal(why({ glLabel: "GitLab" }), "glSync");
  const ahead = glZone({ gl: "ahead", glLabel: "GitHub" }).items.find((x) => x.id === "glpush");
  assert.equal(ahead.whyKey, "", "поза sync причини нема");
});

test("підпис без відомого репо: звичайний простір — нейтральний «Git», ЛІГА — «GitLab» (дані bar без label)", () => {
  for (const glLabel of ["", undefined, "Bitbucket", "constructor"]) {
    const z = glZone({ glLabel, space: PLAIN });
    assert.equal(z.labelKey, "vcsGit", `звичайний: ${String(glLabel)}`);
    assert.equal(z.brand, "Git");
    const l = glZone({ glLabel, space: LIGA });
    assert.equal(l.labelKey, "gitlab", `ЛІГА: ${String(glLabel)}`);
    assert.ok(!("brand" in l));
  }
  const gitlabRepo = glZone({ glLabel: "GitLab", space: PLAIN });
  assert.equal(gitlabRepo.labelKey, "gitlab", "репо на GitLab у звичайному просторі — типовий підпис");
  assert.ok(!("brand" in gitlabRepo));
  const why = (space) => glZone({ gl: "sync", glLabel: "", space }).items.find((x) => x.id === "glpush").whyKey;
  assert.equal(why(PLAIN), "vcsSyncWhy");
  assert.equal(why(LIGA), "glSync");
});

test("«Історія»: без web (file://, Gitea, Bitbucket) пункту нема; у помилці й для ЛІГИ — як було", () => {
  const ids = (o) => glZone(o).items.map((x) => x.id);
  for (const gl of ["sync", "ahead"]) {
    assert.deepEqual(ids({ gl, glNoWeb: true }), ["glpush"], gl);
    assert.deepEqual(ids({ gl, glNoWeb: false }), ["glpush", "glhistory"], gl);
    assert.deepEqual(ids({ gl }), ["glpush", "glhistory"], `${gl}: прапорця нема — як було`);
  }
  assert.deepEqual(ids({ gl: "behind", glNoWeb: true }), ["glpull", "glpush"]);
  assert.deepEqual(ids({ gl: "off", glNoWeb: true }), ["glsetup"]);
  assert.deepEqual(ids({ gl: "error", glNoWeb: false }), ["glpush", "glhistory"], "стан помилки — пункт лишається");
  const html0 = html({ openDd: "gl", gl: "sync", glNoWeb: true, glLabel: "Git", space: PLAIN });
  assert.ok(!html0.includes('data-act="glhistory"'), "у розмітці історії нема");
  assert.ok(html({ openDd: "gl", gl: "sync", glLabel: "GitHub", space: PLAIN }).includes('data-act="glhistory"'));
});

test("«Зайнято» (vcs-busy без придатного стану): ні «збігається», ні помилка — сіра крапка й «Надіслати» без причини", () => {
  const z = glZone({ gl: "busy", glNoWeb: true });
  assert.equal(z.status, "busy");
  const push = z.items.find((x) => x.id === "glpush");
  assert.equal(push.disabled, false, "клік дозволений: він покаже vcsErrBusy");
  assert.equal(push.whyKey, "");
  assert.ok(!z.items.some((x) => x.id === "glpull"));
  assert.match(html({ gl: "busy" }), /dot dot--off/, "крапка сіра, не червона й не зелена");
});

const html = (o) => { const s = { ...base, ...o }; return barHTML(barModel(s), s); };

test("розмітка зони й меню: підпис репозиторію в кнопці й у пунктах; ЛІГА — дослівно GitLab", () => {
  const dd = html({ openDd: "gl", gl: "behind", glLabel: "GitHub" });
  assert.match(dd, /<span class="[^"]*">GitHub<\/span>/, "кнопка зони");
  assert.ok(dd.includes("Надіслати Іт.3 на GitHub"));
  assert.ok(dd.includes("Підтягнути Іт.3 з GitHub"));
  assert.ok(dd.includes("Історія на GitHub"));
  assert.ok(!dd.includes("GitLab"), "у GitHub-просторі слова GitLab нема ніде");
  const git = html({ openDd: "gl", gl: "behind", glLabel: "Git" });
  assert.ok(git.includes("Надіслати Іт.3 на Git<") || git.includes("Надіслати Іт.3 на Git\n"), "Git без хвоста");
  assert.ok(!git.includes("GitLab") && !git.includes("GitHub"));
  const liga = html({ openDd: "gl", gl: "behind" });
  assert.ok(liga.includes("Надіслати Іт.3 на GitLab"));
  assert.ok(liga.includes("Підтягнути Іт.3 з GitLab"));
  assert.ok(liga.includes("Історія на GitLab"));
  assert.ok(!liga.includes("GitHub"));
  setLang("en");
  const en = html({ openDd: "gl", gl: "behind", glLabel: "GitHub" });
  assert.ok(en.includes("Push Іт.3 to GitHub") && en.includes("Pull Іт.3 from GitHub") && en.includes("History on GitHub"));
  assert.ok(!en.includes("GitLab"));
});

test("розмітка меню: «збігається» — з підписом «з репозиторієм», у ЛІГА — «з GitLab»", () => {
  assert.ok(html({ openDd: "gl", gl: "sync", glLabel: "GitHub" }).includes("Збігається з репозиторієм"));
  assert.ok(html({ openDd: "gl", gl: "sync" }).includes("Збігається з GitLab"));
  setLang("en");
  assert.ok(html({ openDd: "gl", gl: "sync", glLabel: "Git" }).includes("Matches the repository"));
});

/* ── палітра ─────────────────────────────────────────────────────────────── */

const P = (o = {}) => ({
  mode: "layout", view: "grid", hasIteration: true, pagesError: "", flowRaw: true, flowError: "",
  published: true, iterPub: true, pagePub: true, pickedPage: "main",
  gl: "behind", iterLabel: "Іт.3", lang: "uk", commentMode: "local", ...o,
});
const gl = (o) => paletteActions(P(o)).filter((a) => /^gl/.test(a.id));

test("палітра: glpull/glpush з підписом несуть labelArgs [ітерація, підпис]; без підпису — форма 0.7.0", () => {
  for (const a of gl({ glBrand: "GitHub" }).filter((x) => x.id === "glpull" || x.id === "glpush")) {
    assert.deepEqual(a.labelArgs, ["Іт.3", "GitHub"], a.id);
    assert.equal(a.val, "Іт.3", "val лишається");
  }
  assert.equal(gl({ glBrand: "GitHub" }).length, 2, "glpull + glpush");
  for (const glBrand of [undefined, "", null]) {
    for (const a of gl({ glBrand })) assert.ok(!("labelArgs" in a), `${a.id}: без підпису поля labelArgs нема`);
  }
});

test("палітра: підпис видно в тексті пункту й у пошуку", () => {
  const acts = paletteActions(P({ glBrand: "GitHub" }));
  const push = acts.find((a) => a.id === "glpush");
  assert.deepEqual(filterActions(acts, "на github").map((a) => a.id), ["glpush"]);
  assert.equal(t(push.labelKey, ...push.labelArgs), "Надіслати Іт.3 на GitHub");
  assert.deepEqual(filterActions(paletteActions(P()), "github"), [], "без підпису слова GitHub нема");
});

test("палітра: причина «збігається» — з підписом vcsSyncWhy, без — glSync", () => {
  const push = (o) => gl({ gl: "sync", ...o }).find((a) => a.id === "glpush");
  assert.equal(push({ glBrand: "GitHub" }).whyKey, "vcsSyncWhy");
  assert.equal(push({}).whyKey, "glSync");
  assert.equal(push({ glBrand: "GitHub", gl: "ahead" }).whyKey, "");
});

test("палітра: пункти синку — за hasVcs, не за integrations", () => {
  const ids = (space) => paletteActions(P({ space })).map((a) => a.id);
  const GL = ["glpush", "glpull"];
  const mod = ids({ integrations: false, capabilities: { vcs: "git-sync", publish: "static-publish" } });
  for (const id of GL) assert.ok(mod.includes(id), `${id}: модуль у просторі без інтеграцій`);
  const off = ids({ integrations: true, capabilities: { vcs: null, publish: "legacy" } });
  for (const id of GL) assert.ok(!off.includes(id), `${id}: роль вимкнено`);
  assert.ok(!paletteActions(P({ gl: "off", space: { integrations: true, capabilities: { vcs: null } } })).some((a) => a.id === "glsetup"));
  assert.ok(paletteActions(P({ gl: "off", space: { integrations: false, capabilities: { vcs: "git-sync" } } })).some((a) => a.id === "glsetup"));
  for (const space of [undefined, null, { integrations: true }]) {
    for (const id of GL) assert.ok(ids(space).includes(id), `${id}: ${JSON.stringify(space)}`);
  }
  assert.ok(!ids({ integrations: false }).includes("glpush"), "стара форма без інтеграцій — синку нема");
});

/* ── словник ─────────────────────────────────────────────────────────────── */

/* Тексти 0.7.0 для ЛІГИ — ДОСЛІВНО (знято з коду до цього батчу). Без підпису чи з «GitLab» — рівно вони. */
const OLD = [
  ["glPush", ["Іт.2"], "Надіслати Іт.2 на GitLab", "Push Іт.2 to GitLab"],
  ["glPull", ["Іт.2"], "Підтягнути Іт.2 з GitLab", "Pull Іт.2 from GitLab"],
  ["glHistory", [], "Історія на GitLab", "History on GitLab"],
  ["glBehindMsg", [3],
    "На GitLab зʼявилися новіші зміни (3) по цьому макету.\nСпершу натисни «⤓ Підтягнути» — чужа версія прийде окремою ітерацією,\nзвір її з твоєю, і тоді синхронізуй.",
    "GitLab has newer changes (3) for this layout.\nFirst click «⤓ Pull» — the other version will arrive as a separate iteration,\ncompare it with yours, then sync."],
  ["glSyncFailedMsg", ["ERR"],
    "GitLab-синхронізація не вдалася — макет ЗАЛИШИВСЯ на цій машині,\nколеги його не бачать:\n\nERR",
    "GitLab sync failed — the layout STAYED on this machine,\ncolleagues don’t see it:\n\nERR"],
  ["glCatchupToast", [], "Довезли незапушений комміт — тепер макет на GitLab.",
    "Caught up the unpushed commit — the layout is now on GitLab."],
  ["glNothingToSendToast", [], "Нічого надсилати — обрана ітерація вже на GitLab (нічого не змінилось).",
    "Nothing to send — the selected iteration is already on GitLab (no changes)."],
  ["glPushedToast", ["abc123"], "Надіслано на GitLab · комміт abc123", "Sent to GitLab · commit abc123"],
  ["glPullConfirmMsg", [],
    "Підтягнути зміни з GitLab як нову ітерацію?\nПоточний макет не зміниться — зʼявиться нова ітерація для порівняння.",
    "Pull changes from GitLab as a new iteration?\nThe current layout won’t change — a new iteration will appear to compare."],
  ["glPullUnchangedToast", ["Іт.4"], "На GitLab те саме, що в Іт.4 — нової ітерації не заводив",
    "GitLab has the same as Іт.4 — no new iteration created"],
  ["glPullOlderToast", ["Іт.1", "Іт.2", "Іт.3"],
    "З GitLab приїхала старша версія (Іт.1 — лягла історією). Продовжуємо з твоєї Іт.2: копія в Іт.3",
    "GitLab had an older version (Іт.1 — kept as history). Continuing from your Іт.2: copy in Іт.3"],
];

test("тексти з підписом: без підпису й з «GitLab» — дослівно 0.7.0, обома мовами", () => {
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const [key, args, uk, en] of OLD) {
      const want = lang === "uk" ? uk : en;
      assert.equal(t(key, ...args), want, `${lang}/${key}: без підпису`);
      assert.equal(t(key, ...args, "GitLab"), want, `${lang}/${key}: з «GitLab»`);
    }
  }
});

test("тексти з підписом: GitHub і Git підставляються, слова GitLab не лишається, обома мовами", () => {
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const [key, args] of OLD) {
      const gh = t(key, ...args, "GitHub");
      assert.ok(gh.includes("GitHub"), `${lang}/${key}: підпису нема в «${gh}»`);
      assert.ok(!gh.includes("GitLab"), `${lang}/${key}: лишилось GitLab у «${gh}»`);
      const g = t(key, ...args, "Git");
      assert.ok(/Git(?!Lab|Hub)/.test(g), `${lang}/${key}: «${g}»`);
      assert.ok(!g.includes("GitLab") && !g.includes("GitHub"), `${lang}/${key}: «${g}»`);
    }
  }
});

test("тип і арність 15 текстів з підписом однакові в обох мовах (підпис — параметр зі значенням за замовчуванням)", () => {
  for (const [key] of OLD) {
    assert.equal(typeof DICT.uk[key], "function", `uk/${key}: значення стало функцією`);
    assert.equal(typeof DICT.en[key], "function", `en/${key}: значення стало функцією`);
    assert.equal(DICT.en[key].length, DICT.uk[key].length, `арність ${key}`);
  }
});

test("15 мертвих gl-ключів прибрано з обох словників", () => {
  const dead = ["glCatchUpLabel", "glDirtyTitle", "glErrorLabel", "glHistoryLabel", "glHistoryTitle", "glIterationFallback",
    "glPullBadge", "glPullTitle", "glSendLabel", "glSyncedLabel", "glSyncedLabelBare", "glSyncedTitle", "glSyncingLabel",
    "glThisIterationFallback", "glUnpushedTitle"];
  assert.equal(dead.length, 15);
  for (const k of dead) {
    assert.ok(!(k in DICT.uk), `uk: «${k}» мертвий, але лишився`);
    assert.ok(!(k in DICT.en), `en: «${k}» мертвий, але лишився`);
  }
});

test("нові ключі: підписи, причина, чотири помилки дій — обома мовами, з підписом у тексті", () => {
  assert.equal(t("vcsGitHub"), "GitHub");
  assert.equal(t("vcsGit"), "Git");
  assert.equal(t("vcsSyncWhy"), "Збігається з репозиторієм");
  assert.equal(t("vcsErrOffline", "GitHub"), "GitHub не відповідає — немає мережі чи VPN. Макет лишився на цьому компʼютері.");
  assert.equal(t("vcsErrAuth", "GitHub"), "GitHub не пускає — перевір SSH-ключ чи вхід у git на цьому компʼютері.");
  assert.equal(t("vcsErrBusy"), "Синхронізація вже йде — спробуй за хвилину.");
  assert.equal(t("vcsErrTarget"), "Адреса репозиторію, гілка чи тека не підходять — виправ їх на «Підключенні».");
  setLang("en");
  assert.equal(t("vcsGitHub"), "GitHub");
  assert.equal(t("vcsGit"), "Git");
  assert.equal(t("vcsSyncWhy"), "Matches the repository");
  assert.equal(t("vcsErrOffline", "GitHub"), "GitHub is not answering — no network or VPN. The layout stayed on this computer.");
  assert.equal(t("vcsErrAuth", "GitHub"), "GitHub refused access — check the SSH key or the git sign-in on this computer.");
  assert.equal(t("vcsErrBusy"), "A sync is already running — try again in a minute.");
  assert.equal(t("vcsErrTarget"), "The repository address, branch or folder is not valid — fix them on Connections.");
});

/* ── мапер помилок дій ───────────────────────────────────────────────────── */

test("vcsErrKey: чотири коди → ключі, решта → null", () => {
  assert.equal(vcsErrKey("vcs-offline"), "vcsErrOffline");
  assert.equal(vcsErrKey("vcs-auth"), "vcsErrAuth");
  assert.equal(vcsErrKey("vcs-busy"), "vcsErrBusy");
  assert.equal(vcsErrKey("vcs-bad-target"), "vcsErrTarget");
  for (const c of ["vcs-error", "module-error", "bad-settings", "constructor", "__proto__", "", undefined, null, 5]) {
    assert.equal(vcsErrKey(c), null, String(c));
  }
});

/* ── проводка в app.js (статика) ─────────────────────────────────────────── */

/** Тіло функції за збалансованими дужками (`function name(` у корені файла). */
function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  return balanced(open);
}
function balanced(open) {
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error("немає закриття дужки");
}
/** Дія `BAR_ACTIONS.<name>: [async] () => {…}` — текст виразу. */
function actSource(name) {
  const m = new RegExp(`\\n  ${name}: (async )?\\(\\) => \\{`).exec(src);
  assert.ok(m, `BAR_ACTIONS.${name} (() => {…}) немає`);
  const open = m.index + m[0].length - 1;
  return `${m[1] ?? ""}() => ${balanced(open)}`;
}
/** Повний текст функції-декларації верхнього рівня (`[async ]function name(…) {…}`). */
function declSource(name) {
  const m = new RegExp(`\\n((?:async )?function ${name}\\()`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const start = m.index + 1;
  const open = src.indexOf("{", src.indexOf(")", start));
  return src.slice(start, open) + balanced(open);
}

test("refreshGitlab питає /api/vcs-status за noVcs(), а loadTeamsMute лишається на noOutward()", () => {
  const body = fn("refreshGitlab");
  const guard = body.indexOf("\n  if (noVcs()) {");
  const call = body.indexOf("await api(`/api/vcs-status?it=${encodeURIComponent(picked || '')}`)");
  assert.ok(guard > 0, "вихід без запиту за noVcs()");
  assert.ok(call > guard, "запит статусу — ПІСЛЯ гейта: без ролі мережі нема");
  assert.match(fn("loadTeamsMute"), /^\{[^]*?\n  if \(noOutward\(\)\) \{ teamsMute = null; return; \}\n  try \{ teamsMute = await api\('\/api\/teams-mute'\)/);
  assert.match(src, /const noVcs = \(\) => needsWelcome\(spacesResp\) \|\| !hasVcs\(spaceNow\(\)\);/);
  assert.match(src, /const noOutward = \(\) => spaceNow\(\)\?\.integrations === false \|\| needsWelcome\(spacesResp\);/,
    "Teams лишається на integrations");
});

test("дії синку ходять на /api/vcs-*, старих адрес у клієнті нема", () => {
  assert.match(actSource("glpush"), /post\('\/api\/vcs-push', \{ it: picked \}\)/);
  assert.match(actSource("glpull"), /post\('\/api\/vcs-pull', \{\}\)/);
  assert.doesNotMatch(src, /\/api\/gitlab-/, "псевдоніми лишаються для хука й старих клієнтів, UI ходить на нові");
});

test("afterModulesChange: render() → refreshGitlab() → paintBar() (spaceNow бере простір із render)", () => {
  const body = fn("afterModulesChange");
  const r = body.indexOf("await render(");
  const g = body.indexOf("await refreshGitlab();");
  const p = body.indexOf("paintBar();");
  assert.ok(r > 0 && g > 0 && p > 0, "усі три виклики на місці");
  assert.ok(r < g, "refreshGitlab ПІСЛЯ render: spaceNow() читає curTask.space, який оновлює render");
  assert.ok(g < p, "і ДО paintBar: смуга малюється вже з новим станом");
});

test("glsetup: у ЛІГА — повідомлення про tasks.json, деінде — «Підключення»", () => {
  assert.match(src, /\n  glsetup: \(\) => \{ if \(isLegacyVcs\(spaceNow\(\)\)\) tell\(t\('glSetupMsg'\)\); else enterConnections\('vcs'\); \},/);
  /* Task 7 (поправка 4): «Налаштувати…» веде не просто на «Підключення», а на картку модуля ролі vcs — поведінку стережуть
     тести «Task 7» нижче. */
});

test("стан смуги й палітри несе підпис, «нема web» і «зайнято» поіменно", () => {
  assert.match(src, /\n    glLabel: glCache\?\.label \|\| '',/);
  assert.match(src, /\n    glNoWeb: !!\(glCache\?\.configured && !glCache\.error && !glCache\.busy && !vcsWebUrl\(glCache\.web\)\),/,
    "у «зайнято» web ще невідомий — пункт «Історія» не ховаємо (інакше він блимав би); клік у ньому каже про зайнятість");
  assert.match(src, /\? 'off'\s*: glCache\.busy \? 'busy'\s*: glCache\.error \? 'error'/, "«зайнято» — окремий стан, раніше за «помилку»");
  assert.match(src, /gl: st\.gl, glBrand: vcsBrand\(st\.glLabel, st\.space\), iterLabel: st\.iterLabel,/);
  const names = /import \{([^}]*)\} from '\.\/spaces-model\.js'/.exec(src)?.[1] ?? "";
  for (const n of ["hasVcs", "isLegacyVcs", "vcsBrand", "vcsFailKey", "vcsLabel", "vcsWebUrl", "requestErrText",
    "VCS_BUSY_MAX_TRIES", "VCS_BUSY_RETRY_MS"]) {
    assert.match(names, new RegExp(`\\b${n}\\b`), `${n} не імпортовано з spaces-model.js`);
  }
});


/* ── виконання дій із заглушками: що побачить людина ─────────────────────── */

/** Допоміжні функції `app.js`, які дії кличуть (беруться з тексту джерела, не переписуються в тесті). */
const HELPERS = ["glLabelNow", "glFailText"];

/**
 * Збирає з тексту `app.js` функції-декларації й дії в одному `with (env)`. Імена, яких вони торкаються, беруться з `env`:
 * забутий — ReferenceError (тест червоніє, а не мовчки бере глобальне). Змінні модуля (`glCache`, `glKey`…) — поля `env`,
 * тож присвоєння в коді змінюють `env`, а тест їх читає.
 */
function load(env, { funcs = [], acts = [] } = {}) {
  const decls = funcs.map(declSource).join("\n");
  const body = acts.map((n) => `${JSON.stringify(n)}: ${actSource(n)}`).join(",\n");
  const ret = `{ ${funcs.map((f) => `${f}: ${f}, `).join("")}acts: { ${body} } }`;
  // eslint-disable-next-line no-new-func
  return new Function("env", `with (env) { ${decls}\nreturn ${ret}; }`)(env);
}
const actFn = (name, env) => load(env, { funcs: HELPERS, acts: [name] }).acts[name];

/** Середовище: усе, чого торкаються дії й `refreshGitlab`, — заглушки, що пишуть у `log`. */
function mkEnv(over = {}) {
  const log = { tell: [], toast: [], post: [], ask: [], refresh: 0, render: 0, open: [], api: [], timers: [], cleared: 0, clearedIds: [], paint: 0 };
  const env = {
    log,
    space: PLAIN,
    spaceNow: () => env.space,
    curTask: { id: "A" },
    glCache: { configured: true, label: "GitHub", behind: 0, unpushed: 0 },
    glKey: null, glSeq: 0, glBusyTimer: null, glBusyFor: null, glBusyTries: 0,
    homeOpen: false,
    picked: "it3",
    noVcs: () => false,
    status: {},
    api: async (path) => { log.api.push(path); return env.status; },
    post: async (path, body) => { log.post.push([path, body]); return env.reply; },
    reply: {},
    tell: (m) => log.tell.push(m),
    toast: (m) => log.toast.push(m),
    askYesNo: async (msg, o) => { log.ask.push([msg, o]); return env.yes !== false; },
    yes: true,
    refreshGitlab: async () => { log.refresh += 1; },
    render: () => { log.render += 1; },
    paintBar: () => { log.paint += 1; },
    itNum: (id) => String(id).replace(/\D/g, ""),
    window: { open: (...a) => log.open.push(a) },
    setTimeout: (fn, ms) => { log.timers.push({ fn, ms }); return log.timers.length; },
    clearTimeout: (id) => { log.clearedIds.push(id); log.cleared += 1; },
    t, vcsErrKey, vcsFailKey, vcsLabel, vcsWebUrl, requestErrText, VCS_BUSY_MAX_TRIES, VCS_BUSY_RETRY_MS,
    ...over,
  };
  return env;
}

const run = async (name, reply, over) => {
  const env = mkEnv({ reply, ...over });
  await actFn(name, env)();
  return env.log;
};

test("glpush: відмова з кодом → свій текст із підписом; без коду чи з чужим кодом → glSyncFailedMsg з причиною", async () => {
  let log = await run("glpush", { ok: false, error: "x", code: "vcs-offline" });
  assert.deepEqual(log.tell, [t("vcsErrOffline", "GitHub")]);
  assert.ok(log.tell[0].startsWith("GitHub не відповідає"));
  log = await run("glpush", { ok: false, error: "x", code: "vcs-auth" });
  assert.deepEqual(log.tell, [t("vcsErrAuth", "GitHub")]);
  log = await run("glpush", { ok: false, error: "x", code: "vcs-busy" });
  assert.deepEqual(log.tell, [t("vcsErrBusy")]);
  log = await run("glpush", { ok: false, error: "x", code: "vcs-bad-target" });
  assert.deepEqual(log.tell, [t("vcsErrTarget")]);
  log = await run("glpush", { ok: false, error: "boom", code: "vcs-error" });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "boom", "GitHub")], "код без свого тексту — загальне повідомлення з причиною");
  log = await run("glpush", { ok: false, error: "boom" });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "boom", "GitHub")]);
  log = await run("glpush", { ok: false });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "—", "GitHub")]);
});

test("glpush: «позаду», «чужа», успіхи — тексти з підписом; ЛІГА — тексти 0.7.0", async () => {
  let log = await run("glpush", { ok: false, blocked: "behind", behind: 2 });
  assert.deepEqual(log.tell, [t("glBehindMsg", 2, "GitHub")]);
  assert.ok(log.tell[0].includes("На GitHub"));
  log = await run("glpush", { ok: false, blocked: "foreign", author: "Олена" });
  assert.deepEqual(log.tell, [t("glForeignMsg", "Олена")]);
  log = await run("glpush", { ok: true, synced: true, catchup: true });
  assert.deepEqual(log.toast, [t("glCatchupToast", "GitHub")]);
  log = await run("glpush", { ok: true, synced: true, changed: false });
  assert.deepEqual(log.toast, [t("glNothingToSendToast", "GitHub")]);
  log = await run("glpush", { ok: true, synced: true, changed: true, pushed: true, sha: "abc123" });
  assert.deepEqual(log.toast, [t("glPushedToast", "abc123", "GitHub")]);
  assert.deepEqual(log.post, [["/api/vcs-push", { it: "it3" }]]);
  assert.equal(log.refresh, 1);
  assert.equal(log.render, 1);

  const liga = { space: LIGA, glCache: { configured: true, label: "GitLab" } };
  log = await run("glpush", { ok: true, synced: true, changed: true, pushed: true, sha: "abc123" }, liga);
  assert.deepEqual(log.toast, ["Надіслано на GitLab · комміт abc123"]);
  log = await run("glpush", { ok: false, error: "boom" }, liga);
  assert.ok(log.tell[0].startsWith("GitLab-синхронізація не вдалася"));
  log = await run("glpush", { ok: false, code: "vcs-offline" }, liga);
  assert.ok(log.tell[0].startsWith("GitLab не відповідає"));
  log = await run("glpush", { ok: true, synced: true, catchup: true }, { space: LIGA, glCache: { configured: true } });
  assert.deepEqual(log.toast, ["Довезли незапушений комміт — тепер макет на GitLab."], "статус без підпису в ЛІГА — GitLab");
});

test("підпис дій — один нормалізатор: без label у ЛІГА «GitLab», у звичайному просторі «Git»; чужий текст не лізе в тости", async () => {
  // M3 (мутації, що виживали): статус без label + код → підпис мусить прийти з простору, а не з `||` у дії.
  const noLabel = { configured: true, error: "ssh: no route", code: "vcs-offline" };
  let log = await run("glpush", {}, { space: LIGA, glCache: noLabel });
  assert.ok(log.tell[0].startsWith("GitLab не відповідає"), log.tell[0]);
  log = await run("glpush", {}, { space: PLAIN, glCache: noLabel });
  assert.ok(log.tell[0].startsWith("Git не відповідає"), log.tell[0]);
  log = await run("glpush", { ok: false, code: "vcs-offline" }, { space: LIGA, glCache: { configured: true } });
  assert.ok(log.tell[0].startsWith("GitLab не відповідає"));
  log = await run("glpush", { ok: false, code: "vcs-offline" }, { space: PLAIN, glCache: { configured: true } });
  assert.ok(log.tell[0].startsWith("Git не відповідає"));
  log = await run("glpull", { ok: false, code: "vcs-auth" }, { space: LIGA, glCache: null });
  assert.ok(log.tell[0].startsWith("GitLab не пускає"));
  log = await run("glpull", { ok: false, code: "vcs-auth" }, { space: PLAIN, glCache: null });
  assert.ok(log.tell[0].startsWith("Git не пускає"));
  // свій модуль із довільним label: у діях — те саме, що в смузі (білий список), без довжини й переносів рядка
  log = await run("glpush", { ok: true, synced: true, changed: true, pushed: true, sha: "s1" },
    { space: PLAIN, glCache: { configured: true, label: "Bitbucket\nEvil" + "x".repeat(300) } });
  assert.deepEqual(log.toast, ["Надіслано на Git · комміт s1"]);
});

test("glpush: помилка статусу в кеші — спершу мапер коду, інакше errFailed; запиту нема", async () => {
  // M2: кешована помилка раніше оминала мапер і показувала сирий stderr git
  let log = await run("glpush", {}, { glCache: { configured: true, label: "GitHub", error: "ssh: connect to host failed", code: "vcs-offline" } });
  assert.deepEqual(log.tell, [t("vcsErrOffline", "GitHub")]);
  assert.deepEqual(log.post, []);
  log = await run("glpush", {}, { glCache: { configured: true, label: "GitHub", error: "Permission denied", code: "vcs-auth" } });
  assert.deepEqual(log.tell, [t("vcsErrAuth", "GitHub")]);
  log = await run("glpush", {}, { glCache: { configured: true, label: "GitHub", error: "weird", code: "vcs-error" } });
  assert.deepEqual(log.tell, [t("errFailed", "weird")], "код без свого тексту — причина як була");
  log = await run("glpush", {}, { glCache: { configured: true, error: "offline" } });
  assert.deepEqual(log.tell, [t("errFailed", "offline")], "без коду — як було");
  assert.deepEqual(log.post, []);
});

test("glpush: запит упав — людський текст (HTML від send_error → рядок статусу), не сирий HTML", async () => {
  // M1: 400 від send_error (нема ролі/цілі, bad iteration) приходив як перші 200 символів HTML
  const htmlErr = Object.assign(new Error("<!DOCTYPE HTML><html><head><title>Error response</title></head>"), {
    status: 400, statusText: "no gitlab configured for this task", body: "<!DOCTYPE HTML><html>…",
  });
  for (const act of ["glpush", "glpull"]) {
    const env = mkEnv();
    env.post = async () => { throw htmlErr; };
    await actFn(act, env)();
    assert.deepEqual(env.log.tell, [t("errFailed", "no gitlab configured for this task")], act);
    assert.ok(!env.log.tell[0].includes("<"), `${act}: у тексті розмітки нема`);
  }
  const net = mkEnv();
  net.post = async () => { throw new TypeError("Failed to fetch"); };
  await actFn("glpush", net)();
  assert.deepEqual(net.log.tell, [t("errFailed", "Failed to fetch")]);
  assert.deepEqual((await run("glpush", {}, { glCache: null })).post, [], "без кешу — нічого");
});

test("glpush у стані «зайнято»: vcsErrBusy без запиту до git, і одразу перепитує статус", async () => {
  const log = await run("glpush", {}, { glCache: { configured: true, busy: true } });
  assert.deepEqual(log.tell, [t("vcsErrBusy")]);
  assert.deepEqual(log.post, [], "до git — нічого: статусу ще нема");
  assert.equal(log.refresh, 1, "клік — привід перепитати, а не лишити людину з вічним «зайнято»");
  assert.equal(log.render, 1);
});

test("glpull: відмова приходить 200 {ok:false, error, code} — її мусить показати сама дія, а не catch", async () => {
  let log = await run("glpull", { ok: false, error: "x", code: "vcs-auth" });
  assert.deepEqual(log.tell, [t("vcsErrAuth", "GitHub")]);
  log = await run("glpull", { ok: false, error: "x", code: "vcs-busy" });
  assert.deepEqual(log.tell, [t("vcsErrBusy")]);
  log = await run("glpull", { ok: false, error: "x", code: "vcs-offline" });
  assert.deepEqual(log.tell, [t("vcsErrOffline", "GitHub")]);
  log = await run("glpull", { ok: false, error: "x", code: "vcs-bad-target" });
  assert.deepEqual(log.tell, [t("vcsErrTarget")]);
  // «path … not found in repo» — без `code`: причина з сервера, а не мовчання
  log = await run("glpull", { ok: false, error: "path 'mockup/x' not found in repo" });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "path 'mockup/x' not found in repo", "GitHub")]);
  log = await run("glpull", { ok: false, error: "x", code: "vcs-error" });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "x", "GitHub")]);
  log = await run("glpull", { ok: false });
  assert.deepEqual(log.tell, [t("glSyncFailedMsg", "—", "GitHub")]);
  assert.deepEqual(log.toast, []);
});

test("ЛІГА: vcs-bad-target — старе glSyncFailedMsg (ціль у tasks.json), три інші коди — свої тексти", async () => {
  // M6: «виправ на «Підключенні»» у ЛІГА брехня — там ціль живе в tasks.json
  const liga = { space: LIGA, glCache: { configured: true, label: "GitLab" } };
  for (const act of ["glpush", "glpull"]) {
    let log = await run(act, { ok: false, error: "bad repo", code: "vcs-bad-target" }, liga);
    assert.deepEqual(log.tell, [t("glSyncFailedMsg", "bad repo", "GitLab")], `${act}: ЛІГА`);
    assert.ok(!log.tell[0].includes("Підключенні"));
    log = await run(act, { ok: false, error: "bad repo", code: "vcs-bad-target" }, { space: PLAIN, glCache: { configured: true, label: "GitHub" } });
    assert.deepEqual(log.tell, [t("vcsErrTarget")], `${act}: звичайний простір`);
    log = await run(act, { ok: false, error: "e", code: "vcs-offline" }, liga);
    assert.deepEqual(log.tell, [t("vcsErrOffline", "GitLab")], `${act}: offline`);
    log = await run(act, { ok: false, error: "e", code: "vcs-auth" }, liga);
    assert.deepEqual(log.tell, [t("vcsErrAuth", "GitLab")]);
    log = await run(act, { ok: false, error: "e", code: "vcs-busy" }, liga);
    assert.deepEqual(log.tell, [t("vcsErrBusy")]);
  }
});

test("glpull: питання й тости несуть підпис; unchanged і «старша» — як були; нова ітерація — без тосту", async () => {
  let log = await run("glpull", { ok: true, unchanged: true, iteration: null, same_as: "it2" });
  assert.deepEqual(log.ask[0], [t("glPullConfirmMsg", "GitHub"), { yes: t("glPullConfirmYes") }]);
  assert.deepEqual(log.post, [["/api/vcs-pull", {}]]);
  assert.deepEqual(log.toast, [t("glPullUnchangedToast", "it2", "GitHub")]);
  assert.ok(log.toast[0].startsWith("На GitHub те саме"));
  assert.deepEqual(log.tell, []);
  log = await run("glpull", { ok: true, iteration: { id: "it5" }, fork: { id: "it6" }, continue_from: "it4" });
  assert.deepEqual(log.toast, [t("glPullOlderToast", t("iterTag", "5"), t("iterTag", "4"), t("iterTag", "6"), "GitHub")]);
  log = await run("glpull", { ok: true, iteration: { id: "it5" }, fork: null, continue_from: null });
  assert.deepEqual(log.toast, []);
  assert.deepEqual(log.tell, []);
  assert.equal(log.refresh, 1);

  log = await run("glpull", { ok: true, unchanged: true, same_as: "it2" }, { space: LIGA, glCache: { configured: true, label: "GitLab" } });
  assert.deepEqual(log.ask[0][0], "Підтягнути зміни з GitLab як нову ітерацію?\nПоточний макет не зміниться — зʼявиться нова ітерація для порівняння.");
  assert.deepEqual(log.toast, ["На GitLab те саме, що в it2 — нової ітерації не заводив"]);
});

test("glpull: «Ні» у питанні — запиту нема; запит упав — errFailed (catch лишився для транспорту)", async () => {
  const log = await run("glpull", {}, { yes: false });
  assert.deepEqual(log.post, []);
  const env = mkEnv();
  env.post = async () => { throw new Error("net down"); };
  await actFn("glpull", env)();
  assert.deepEqual(env.log.tell, [t("errFailed", "net down")]);
});

test("glhistory: відкриває лише http(s) із відповіді; інше — як без web (нічого)", () => {
  const open = (web) => {
    const env = mkEnv({ glCache: { configured: true, web } });
    load(env, { acts: ["glhistory"] }).acts.glhistory();
    return env.log.open;
  };
  assert.deepEqual(open("https://github.com/o/r/commits/main/mockup"), [["https://github.com/o/r/commits/main/mockup", "_blank", "noopener"]]);
  assert.equal(open("http://gitea.local/o/r").length, 1);
  for (const web of [null, undefined, "", "javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "git@h:o/r"]) {
    assert.deepEqual(open(web), [], String(web));
  }
  const none = mkEnv({ glCache: null });
  load(none, { acts: ["glhistory"] }).acts.glhistory();
  assert.deepEqual(none.log.open, []);
});

/* ── refreshGitlab: «зайнято» тримається ключем «простір|задача|ітерація» ─── */

const refresh = (over) => {
  const env = mkEnv(over);
  const f = load(env, { funcs: ["glKeyNow", "cancelGlRetry", "dropGlState", "scheduleGlRetry", "refreshGitlab"] });
  return { env, ...f };
};
/** `api()`, що відповідає, коли скаже тест: `q[i].res(відповідь)` / `q[i].rej(помилка)` — для запізнілих відповідей. */
function deferredApi(env) {
  const q = [];
  env.api = (path) => { env.log.api.push(path); return new Promise((res, rej) => q.push({ res, rej })); };
  return q;
}
const BUSY = { configured: true, error: "dзеркало зайняте", code: "vcs-busy" };
const REAL_A = { configured: true, label: "GitHub", behind: 0, unpushed: 0, dirty: false, gitlab_it: "it1" };

test("refreshGitlab: звичайна відповідь — у кеш під ключем «простір|задача|ітерація», повторів нема", async () => {
  const { env, refreshGitlab } = refresh({ status: REAL_A, glCache: null });
  await refreshGitlab();
  assert.equal(env.glCache, REAL_A);
  assert.equal(env.glKey, "plain|A|it3");
  assert.deepEqual(env.log.api, ["/api/vcs-status?it=it3"]);
  assert.deepEqual(env.log.timers, []);
});

test("refreshGitlab: простір без ролі vcs — кеш скинуто, мережі й таймера нема", async () => {
  const { env, refreshGitlab } = refresh({ status: REAL_A, glCache: REAL_A, glBusyTimer: 7, noVcs: () => true });
  await refreshGitlab();
  assert.equal(env.glCache, null);
  assert.deepEqual(env.log.api, []);
  assert.ok(env.log.clearedIds.includes(7), "відкладений повтор справді скасовано (clearTimeout(7)), а не лише забуто");
  assert.equal(env.glBusyTimer, null);
  assert.equal(env.glSeq, 1, "запізнілі відповіді, що летять, відкидаються");
  assert.equal(env.glKey, null);
});

test("(i) vcs-busy без попереднього стану: «зайнято», не помилка й не «збігається», повтор заплановано", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  await refreshGitlab();
  assert.equal(env.glCache.busy, true);
  assert.equal(env.glCache.configured, true);
  assert.ok(!env.glCache.error, "це не помилка: крапка не червона, дія не показує сирий текст сервера");
  assert.ok(!("behind" in env.glCache) && !("gitlab_it" in env.glCache), "ніякого вигаданого стану");
  assert.equal(env.glKey, "plain|A|it3");
  assert.equal(env.log.timers.length, 1);
  assert.equal(env.log.timers[0].ms, VCS_BUSY_RETRY_MS);
});

test("(ii) vcs-busy після перемикання задачі: стан задачі A не показується для B", async () => {
  const { env, refreshGitlab } = refresh({ status: REAL_A, glCache: null });
  await refreshGitlab();                      // кеш зібрано для A
  assert.equal(env.glCache, REAL_A);
  env.curTask = { id: "B" };                  // перемкнули задачу: resetPerTaskState glCache не чіпає
  env.status = BUSY;
  await refreshGitlab();
  assert.notEqual(env.glCache, REAL_A, "стан A — чужий для B");
  assert.equal(env.glCache.busy, true);
  assert.ok(!("gitlab_it" in env.glCache), "хмарки «збігається» на it1 нема");
  assert.equal(env.glKey, "plain|B|it3");
  // та сама історія з іншою ітерацією тієї самої задачі
  const second = refresh({ status: REAL_A, glCache: null });
  await second.refreshGitlab();
  second.env.picked = "it4";
  second.env.status = BUSY;
  await second.refreshGitlab();
  assert.equal(second.env.glCache.busy, true, "ітерація — частина ключа");
  // і простір теж
  const third = refresh({ status: REAL_A, glCache: null });
  await third.refreshGitlab();
  third.env.space = { ...PLAIN, id: "other" };
  third.env.status = BUSY;
  await third.refreshGitlab();
  assert.equal(third.env.glCache.busy, true, "простір — частина ключа");
});

test("vcs-busy того самого ключа: власний стан лишається (крапка не фарбується в помилку), повтор заплановано", async () => {
  const { env, refreshGitlab } = refresh({ status: REAL_A, glCache: null });
  await refreshGitlab();
  env.status = BUSY;
  await refreshGitlab();
  assert.equal(env.glCache, REAL_A, "той самий обʼєкт");
  assert.equal(env.glKey, "plain|A|it3");
  assert.equal(env.log.timers.length, 1);
});

test("повтор після «зайнято»: той самий ключ — перепитує й малює смугу; новий стан замінює «зайнято»", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  await refreshGitlab();
  assert.equal(env.glCache.busy, true);
  env.status = REAL_A;                        // синхронізація скінчилась
  await env.log.timers[0].fn();
  assert.equal(env.log.api.length, 2, "повторний запит статусу");
  assert.equal(env.glCache, REAL_A);
  assert.equal(env.log.paint, 1, "смуга перемальована");
  assert.equal(env.log.timers.length, 1, "після відповіді без busy нових повторів нема");
});

const REAL_B = { configured: true, label: "GitHub", behind: 0, unpushed: 2, dirty: true, gitlab_it: null };

test("повтор після перемикання задачі, ітерації чи простору опитує ПОТОЧНИЙ стан і знімає «зайнято»", async () => {
  for (const change of [
    (e) => { e.curTask = { id: "B" }; },
    (e) => { e.picked = "it9"; },
    (e) => { e.space = { ...PLAIN, id: "other" }; },
  ]) {
    const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
    await refreshGitlab();
    change(env);
    env.status = REAL_B;
    await env.log.timers[0].fn();
    assert.equal(env.log.api.length, 2, "запит статусу пішов — про те, що відкрито зараз");
    assert.equal(env.glCache, REAL_B, "«зайнято» знято");
    assert.equal(env.log.paint, 1);
  }
});

test("повтор не стріляє, коли ролі вже нема або відкрито екран «Задачі» (смуга під оверлеєм)", async () => {
  for (const change of [(e) => { e.noVcs = () => true; }, (e) => { e.homeOpen = true; }]) {
    const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
    await refreshGitlab();
    change(env);
    await env.log.timers[0].fn();
    assert.equal(env.log.api.length, 1, "запит статусу не пішов");
    assert.equal(env.log.paint, 0);
  }
});

test("повтори «зайнято» скінченні: після VCS_BUSY_MAX_TRIES спроб нових таймерів нема", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  const n = await exhaust(env, refreshGitlab);
  assert.equal(n, VCS_BUSY_MAX_TRIES, `рівно ${VCS_BUSY_MAX_TRIES} відкладених опитів і край`);
  assert.equal(env.glCache.busy, true, "стан лишається «зайнято»; клік у ньому перепитає статус");
});

test("«зайнято» на запит, що летів під час перемикання (новішого запиту нема): кеш — під ключем запиту, повтор опитує поточне", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  env.api = async (path) => { env.log.api.push(path); env.curTask = { id: "B" }; return BUSY; };  // людина перемкнула задачу, поки запит летів
  await refreshGitlab();
  assert.equal(env.glKey, "plain|A|it3", "кеш підписано ключем запиту (A), а не поточним (B)");
  assert.equal(env.log.timers.length, 1);
  env.api = async (path) => { env.log.api.push(path); return REAL_B; };
  await env.log.timers[0].fn();
  assert.equal(env.log.api.length, 2, "повтор не губиться через зміну ключа — він опитує те, що відкрито");
  assert.equal(env.glCache, REAL_B);
});

/** Вичерпує всі відкладені опити поточного ключа: кожен таймер спрацьовує, поки нові не перестануть зʼявлятись. */
async function exhaust(env, refreshGitlab) {
  await refreshGitlab();
  let fired = 0;
  // стеля 30 — лише щоб відсутня межа повторів дала червоний тест, а не нескінченний цикл
  while (env.log.timers.length > fired && fired < 30) { fired += 1; await env.log.timers[fired - 1].fn(); }
  return env.log.timers.length;
}

test("лічильник спроб скидається звичайною відповіддю: після неї «зайнято» знову дає повтори", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  assert.equal(await exhaust(env, refreshGitlab), VCS_BUSY_MAX_TRIES);
  const n = env.log.timers.length;
  env.status = REAL_A;
  await refreshGitlab();                      // синхронізація скінчилась
  env.status = BUSY;
  env.glCache = null;
  await refreshGitlab();                      // і знову почалась
  assert.equal(env.log.timers.length, n + 1, "лічильник почався спочатку");
});

test("лічильник спроб свій на кожен ключ: нова задача не успадковує вичерпані повтори попередньої", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  assert.equal(await exhaust(env, refreshGitlab), VCS_BUSY_MAX_TRIES);
  const n = env.log.timers.length;
  env.curTask = { id: "B" };
  env.glCache = null;
  await refreshGitlab();
  assert.equal(env.log.timers.length, n + 1, "B має власні спроби");
});

test("помилка запиту статусу: кеш і ключ скинуто (без застарілого стану)", async () => {
  const { env, refreshGitlab } = refresh({ glCache: REAL_A, glKey: "plain|A|it3" });
  env.api = async () => { throw new Error("net"); };
  await refreshGitlab();
  assert.equal(env.glCache, null);
  assert.equal(env.glKey, null);
});

/* ── запізнілі відповіді: застосовується лише найновіший запит ─────────────── */

test("запізніла відповідь старої задачі не перезаписує кеш нової (R1 повільна, R2 швидка)", async () => {
  const { env, refreshGitlab } = refresh({ glCache: null, picked: "it1" });
  const q = deferredApi(env);
  const r1 = refreshGitlab();                           // питаємо про A — VPN, секунди
  env.curTask = { id: "B" }; env.picked = "it2";
  const r2 = refreshGitlab();                           // перемкнули на B — швидка відповідь
  q[1].res(REAL_B); await r2;
  assert.equal(env.glCache, REAL_B);
  assert.equal(env.glKey, "plain|B|it2");
  q[0].res(REAL_A); await r1;                           // а це дотяглась A
  assert.equal(env.glCache, REAL_B, "смуга не малює стан A для B");
  assert.equal(env.glKey, "plain|B|it2");
});

test("запізніла «зайнято» старого ключа не затирає добрий стан нового і не скидає повтор", async () => {
  const { env, refreshGitlab } = refresh({ glCache: null, picked: "it1" });
  const q = deferredApi(env);
  const r1 = refreshGitlab();
  env.curTask = { id: "B" }; env.picked = "it2";
  const r2 = refreshGitlab();
  q[1].res(REAL_B); await r2;
  q[0].res(BUSY); await r1;
  assert.equal(env.glCache, REAL_B, "добрий стан B лишився");
  assert.ok(!env.glCache.busy);
  assert.deepEqual(env.log.timers, [], "запізніла busy не заплановує повтор");
});

test("запізніла помилка запиту старої задачі не скидає кеш нової", async () => {
  const { env, refreshGitlab } = refresh({ glCache: null, picked: "it1" });
  const q = deferredApi(env);
  const r1 = refreshGitlab();
  env.curTask = { id: "B" }; env.picked = "it2";
  const r2 = refreshGitlab();
  q[1].res(REAL_B); await r2;
  q[0].rej(new Error("net")); await r1;
  assert.equal(env.glCache, REAL_B);
  assert.equal(env.glKey, "plain|B|it2");
});

test("порядок відповідей зворотний (A швидка, B повільна): застосовується B, стан A не лишається", async () => {
  const { env, refreshGitlab } = refresh({ glCache: null, picked: "it1" });
  const q = deferredApi(env);
  const r1 = refreshGitlab();
  env.curTask = { id: "B" }; env.picked = "it2";
  const r2 = refreshGitlab();
  q[0].res(REAL_A); await r1;                           // A — найстаріший запит: відкинуто
  assert.equal(env.glCache, null, "поки B не відповіла, чужого стану нема");
  q[1].res(REAL_B); await r2;
  assert.equal(env.glCache, REAL_B);
});

test("роль vcs зникла, поки запит летів: відповідь не воскрешає кеш", async () => {
  const { env, refreshGitlab } = refresh({ glCache: null });
  const q = deferredApi(env);
  const r1 = refreshGitlab();
  env.noVcs = () => true;
  await refreshGitlab();                                // перемкнули в простір без синку
  q[0].res(REAL_A); await r1;
  assert.equal(env.glCache, null);
});

test("resetSpaceState: кеш і ключ скинуто, відкладений повтор скасовано, відповідь старого простору відкинуто", async () => {
  const env = mkEnv({
    glCache: REAL_A, glKey: "plain|A|it1", glBusyTimer: 5, glSeq: 3,
    curTaskList: null, homeData: null, currentTaskId: "A", taskSwitchGen: 0, homeSeq: 0, teamsMute: {},
    tasksErr: true, tasksErrKey: "k", homeUi: { q: "x", profiles: { clear() {} }, designers: { clear() {} } },
    saveHomeUi: () => {}, taskQ: "q", taskCursor: 4, resetPerTaskState: async () => {}, loadSpaces: async () => {},
  });
  const q = deferredApi(env);
  const f = load(env, { funcs: ["glKeyNow", "cancelGlRetry", "dropGlState", "scheduleGlRetry", "refreshGitlab", "resetSpaceState"] });
  const r = f.refreshGitlab();                          // запит старого простору в польоті
  await f.resetSpaceState({ reload: false });
  assert.ok(env.log.clearedIds.includes(5), "відкладений повтор скасовано");
  assert.equal(env.glBusyTimer, null);
  assert.equal(env.glCache, null);
  assert.equal(env.glKey, null);
  q[0].res(REAL_A); await r;
  assert.equal(env.glCache, null, "стан старого простору не повернувся");
});

test("звичайна відповідь справді скасовує відкладений повтор (clearTimeout, а не лише забуте посилання)", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  await refreshGitlab();
  const pending = env.glBusyTimer;
  assert.ok(pending, "таймер заплановано");
  env.status = REAL_A;
  await refreshGitlab();
  assert.ok(env.log.clearedIds.includes(pending), "після OK відкладений таймер скасовано — зайвого опиту не буде");
  assert.equal(env.glBusyTimer, null);
});

test("enterHome скасовує відкладений повтор, leaveHome повертає його лише для «зайнято» без таймера", () => {
  assert.match(fn("enterHome"), /\n {2}cancelGlRetry\(\);/, "екран «Задачі» не опитує статус і не малює смугу під оверлеєм");
  assert.match(fn("leaveHome"), /await render\(\);[^]*?if \(glCache\?\.busy && !glBusyTimer\) scheduleGlRetry\(glKeyNow\(\)\);/,
    "вернулись до задачі зі станом «зайнято» — повтор знову заплановано");
  assert.match(fn("resetSpaceState"), /glCache = null; teamsMute = null;\n {2}dropGlState\(\);/);
});

/* ── реальний потік: refresh викликається ДО render ───────────────────────── */

/**
 * `switchTask`, `wizOpenTask` і створення задачі питають статус, коли сервер уже перемкнено, а `curTask` ще старий і
 * `picked = null` (його скинув `resetPerTaskState`); `render()` перемикає `curTask` і нормалізує `picked` лише ПІСЛЯ.
 * Тест відтворює саме цей порядок.
 */
const flow = (over) => {
  const env = mkEnv({
    glCache: REAL_A, glKey: "plain|A|it1", curTask: { id: "A" }, picked: "it1", status: BUSY,
    currentTaskId: "A", taskSwitchGen: 0, homeData: null, homeReady: () => false, spaceChanged,
    resetPerTaskState: async () => { env.picked = null; },
    resetSpaceState: async () => { throw new Error("простір не змінювався"); },
    leaveHome: async () => { env.curTask = { id: "B" }; env.picked = "it1"; },
    post: async () => ({ space: "plain" }),
    ...over,
  });
  const f = load(env, { funcs: ["glKeyNow", "cancelGlRetry", "dropGlState", "scheduleGlRetry", "refreshGitlab", "switchTask", "wizOpenTask"] });
  return { env, ...f };
};
const render = (env) => { env.curTask = { id: "B" }; env.picked = "it1"; };

test("потік switchTask (refresh до render): ключ — цільова задача, повтор після render стріляє й знімає «зайнято»", async () => {
  const { env, switchTask } = flow();
  assert.equal(await switchTask("B"), true);
  assert.equal(env.glKey, "plain|B|", "ключ запиту — задача B, до якої сервер уже перемкнено, а не curTask A");
  assert.equal(env.glCache.busy, true, "стан A не тримається для B");
  assert.equal(env.log.timers.length, 1);
  render(env);                                          // BAR_ACTIONS.task / leaveHome
  env.status = REAL_B;
  await env.log.timers[0].fn();
  assert.equal(env.log.api.length, 2, "повтор опитав B");
  assert.equal(env.glCache, REAL_B, "«зайнято» зникло саме");
  assert.equal(env.glKey, "plain|B|it1");
  assert.equal(env.log.paint, 1);
});

test("потік switchTask: два переходи до render першого — стан першої цілі не тримається для другої", async () => {
  const { env, switchTask } = flow({ status: REAL_B });
  await switchTask("B");
  assert.equal(env.glCache, REAL_B);
  env.status = BUSY;
  await switchTask("C");                                // curTask досі A
  assert.equal(env.glKey, "plain|C|");
  assert.equal(env.glCache.busy, true, "REAL_B належить B, а питали про C");
});

test("потік wizOpenTask (refresh до leaveHome): ключ — нова задача, повтор після render знімає «зайнято»", async () => {
  const { env, wizOpenTask } = flow();
  await wizOpenTask({ id: "B", space: "plain" });
  assert.equal(env.glKey, "plain|B|", "ключ — made.id, а не curTask");
  assert.equal(env.glCache.busy, true);
  env.status = REAL_B;
  await env.log.timers[0].fn();
  assert.equal(env.glCache, REAL_B);
});

test("створення задачі: refreshGitlab питає про made.id (всі три потоки передають цільову задачу)", () => {
  assert.match(fn("newTaskDialog"), /currentTaskId = made\.id; taskSwitchGen \+= 1;\s*await refreshGitlab\(made\.id\);\s*await leaveHome\(\);/);
  assert.match(fn("wizOpenTask"), /currentTaskId = made\.id; taskSwitchGen \+= 1;\s*await refreshGitlab\(made\.id\);\s*await leaveHome\(\);/);
  assert.match(fn("switchTask"), /await refreshGitlab\(val\);\s*currentTaskId = val;/);
});

test("glhistory у стані «зайнято»: web ще невідомий — кажемо про зайнятість, а не мовчимо", () => {
  const env = mkEnv({ glCache: { configured: true, busy: true } });
  load(env, { acts: ["glhistory"] }).acts.glhistory();
  assert.deepEqual(env.log.tell, [t("vcsErrBusy")]);
  assert.deepEqual(env.log.open, []);
});

test("друга «зайнято» поспіль замінює відкладений повтор, а не множить таймери", async () => {
  const { env, refreshGitlab } = refresh({ status: BUSY, glCache: null });
  await refreshGitlab();
  const first = env.glBusyTimer;
  await refreshGitlab();
  assert.ok(env.log.clearedIds.includes(first), "попередній таймер скасовано перед новим");
  assert.notEqual(env.glBusyTimer, first);
});

/* ══ Task 7: «Підключення», майстер і форма нової задачі з роллю vcs ═══════════════════════════════════════════ */

const wsrc = readFileSync(new URL("../app/wizard.js", import.meta.url), "utf8");
const asrc = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");

/** Текст функції-декларації `name` будь-де в `text` (вкладеної теж): від `function` до парної `}`. */
function nested(text, name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(text);
  assert.ok(m, `нема функції ${name}`);
  const open = text.indexOf("{", text.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") { depth -= 1; if (depth === 0) return text.slice(m.index, i + 1); }
  }
  throw new Error("немає закриття дужки");
}
/** Вираз однорядкового поля обʼєкта-залежностей `  name: <вираз>,` у `src`. */
function depExpr(name) {
  const m = new RegExp(`\\n  ${name}: (.*),\\n`).exec(src);
  assert.ok(m, `у createWizard({...}) нема залежності ${name}`);
  return m[1];
}
const evalIn = (env, code) => new Function("env", `with (env) { return (${code}); }`)(env);

/* ── ключі словника ──────────────────────────────────────────────────────── */

test("Task 7: нові ключі «Підключень» і форми — обома мовами, тексти дослівно (з поправкою на місце вживання «нікого»)", () => {
  const UK = {
    cnRoleVcs: "Синхронізація з git",
    cnRoleVcsLead: "Відправляти ітерації в git-репозиторій і отримувати правки колег.",
    cnNoneVcs: "макети лише на цьому компʼютері",
    cnModGitName: "Git",
    cnModGitDesc: "Будь-який git-репозиторій — GitHub, GitLab чи свій сервер. Доступ — через git цього компʼютера (SSH-ключ чи збережений вхід), Deai паролів не зберігає.",
    cnFieldGitRepo: "Репозиторій (типовий для задач)",
    cnFieldGitBranch: "Гілка",
    cnFieldGitPath: "Тека в репозиторії ({task} — id задачі)",
    cnFieldGitSshKey: "SSH-ключ (необовʼязково)",
    cnFieldGitHostIp: "IP сервера, коли DNS у VPN не відповідає (необовʼязково)",
    cnFieldGitAutosync: "Відправляти після кожної відповіді агента",
    cnErrVcsOffline: "Репозиторій не відповідає — немає мережі чи VPN.",
    cnErrVcsAuth: "Немає доступу — перевір SSH-ключ чи вхід у git.",
    cnErrVcsTarget: "Адреса, гілка чи тека не підходять.",
    cnErrVcsBusy: "Синхронізація вже йде — перевір за хвилину.",
    cnErrVcsError: "Git відмовив.",
    newTaskRepo: "Репозиторій (необовʼязково)",
    newTaskRepoPh: "типовий з «Підключення»",
    taskErrVcsTarget: "Адреса репозиторію не підходить: ssh://, https://, git@сервер:шлях або тека на диску.",
    taskErrVcsRole: "У просторі немає синхронізації з git — підключи її на «Підключенні».",
  };
  const EN = {
    cnRoleVcs: "Git sync",
    cnRoleVcsLead: "Send iterations to a git repository and pull colleagues’ changes.",
    cnNoneVcs: "layouts stay on this computer only",
    cnModGitName: "Git",
    cnModGitDesc: "Any git repository — GitHub, GitLab or your own server. Access goes through this computer’s git (SSH key or saved sign-in); Deai stores no passwords.",
    cnFieldGitRepo: "Repository (default for tasks)",
    cnFieldGitBranch: "Branch",
    cnFieldGitPath: "Folder in the repository ({task} is the task id)",
    cnFieldGitSshKey: "SSH key (optional)",
    cnFieldGitHostIp: "Server IP when DNS over VPN fails (optional)",
    cnFieldGitAutosync: "Send after every agent reply",
    cnErrVcsOffline: "The repository is not answering — no network or VPN.",
    cnErrVcsAuth: "No access — check the SSH key or the git sign-in.",
    cnErrVcsTarget: "The address, branch or folder is not valid.",
    cnErrVcsBusy: "A sync is running — check again in a minute.",
    cnErrVcsError: "Git refused.",
    newTaskRepo: "Repository (optional)",
    newTaskRepoPh: "the default from Connections",
    taskErrVcsTarget: "The repository address is not valid: ssh://, https://, git@host:path or a local folder.",
    taskErrVcsRole: "This space has no git sync — connect it on Connections.",
  };
  for (const [lang, want] of [["uk", UK], ["en", EN]]) {
    setLang(lang);
    for (const [k, v] of Object.entries(want)) assert.equal(DICT[lang][k], v, `${lang}.${k}`);
  }
});

test("Task 7: «Підключення» не лишає мертвих vcs-ключів: кожен cnErrVcs* і cnField/cnMod git — досяжний через модель", () => {
  setLang("uk");
  const reach = new Set();
  for (const code of ["vcs-offline", "vcs-auth", "vcs-bad-target", "vcs-busy", "vcs-error"]) reach.add(verdictText({ ok: false, error: code }).key);
  for (const k of Object.keys(DICT.uk).filter((x) => /^cnErrVcs/.test(x))) assert.ok(reach.has(k), `${k} ніхто не показує`);
});

/* ── поле «Репозиторій» і запит створення: виконання newTaskDialog із заглушками ─────────────────────────── */

const TASK_HELPERS = ["newTaskDialog", "showCreateWait"];
const GIT_ENTRY = { id: "git-sync", enabled: true, roles: ["vcs"], settings: [{ key: "repo", value: "git@gh.example:o/r.git" }, { key: "branch", value: "main" }] };
const PUB_ENTRY = { id: "static-publish", enabled: true, roles: ["publish"], settings: [{ key: "repo", value: "ЧУЖЕ" }] };
const NOVCS = { id: "plain", integrations: false, capabilities: { vcs: null } };

/** Середовище `newTaskDialog`: усе, чого він торкається, — заглушки з журналом; `askForm` лише запамʼятовує параметри діалогу. */
function mkTaskEnv(over = {}) {
  const log = { api: [], form: [], post: [], taskPost: [], focus: [], toast: [], leave: 0, refresh: [], reset: [], wire: [] };
  const env = {
    log,
    space: PLAIN,
    spaceNow: () => env.space,
    modules: { modules: [PUB_ENTRY, GIT_ENTRY] },
    formApi: async (p) => { log.form.push(p); return { tasks: [{ id: "taken-1" }] }; },
    api: async (p) => { log.api.push(p); if (env.apiFails) throw new Error("net"); return env.modules; },
    askForm: async (build, opts) => { env.html = build(); env.opts = opts; },
    taskFormHTML, wireTaskForm: (form, o) => log.wire.push([form, o]),
    homeNode: () => null,
    taskFormError, taskErrField, taskErrKey, taskErrShowsReason, taskCreateClones, hasVcs, isLegacyVcs, requestErrText, spaceChanged, t,
    postForm: async (p, b) => { log.post.push([p, b]); return env.reply; },
    taskPost: async (b) => { log.taskPost.push(b); return env.reply; },
    reply: { id: "t-1", space: "plain" },
    resetSpaceState: async () => { log.reset.push("space"); },
    resetPerTaskState: async () => { log.reset.push("task"); },
    homeData: { old: 1 }, currentTaskId: "A", taskSwitchGen: 0,
    refreshGitlab: async (id) => { log.refresh.push(id); },
    leaveHome: async () => { log.leave += 1; },
    toast: (m) => log.toast.push(m),
    ...over,
  };
  return env;
}
/** Форма діалогу: головна кнопка, слот помилки (перед ним вставляється рядок-статус) і фальшивий `document` для нього. */
function fakeForm() {
  const form = { notes: [], ok: { textContent: "Створити задачу" }, slot: {} };
  form.slot.before = (n) => { form.notes.push(n); n.live = true; };
  form.querySelector = (s) => (s === 'button[data-a="ok"]' ? form.ok : s === "[data-form-error]" ? form.slot : null);
  form.document = {
    createElement: () => {
      const n = { textContent: "", className: "", attrs: {}, live: false, setAttribute(k, v) { n.attrs[k] = v; }, remove() { n.live = false; } };
      return n;
    },
  };
  return form;
}
const taskDialog = async (over) => {
  const form = fakeForm();
  const timers = [];
  const env = mkTaskEnv({
    document: form.document, setTimeout: (fn, ms) => { timers.push({ fn, ms, on: true }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].on = false; }, ...over,
  });
  await load(env, { funcs: TASK_HELPERS }).newTaskDialog();
  const ctl = { form, focus: (n) => env.log.focus.push(n) };
  return { env, ctl, form, timers, submit: (vals) => env.opts.onSubmit({ title: "Лендинг", id: "lend", ...vals }, ctl) };
};
const tick = () => new Promise((r) => setImmediate(r));

test("форма: у звичайному просторі з роллю vcs є поле «Репозиторій»; у ЛІГА й без ролі — розмітка дослівно як була", async () => {
  for (const [space, withRepo] of [[PLAIN, true], [LIGA, false], [NOVCS, false]]) {
    const { env } = await taskDialog({ space });
    assert.equal(/id="tf-repo"/.test(env.html), withRepo, JSON.stringify(space));
    if (!withRepo) assert.equal(env.html, taskFormHTML(), "розмітка без поля — рівно та, що була до 4a");
  }
});

test("підказка: типовий repo з GET /api/modules?space=… (лише вмикнений модуль з роллю vcs) стає placeholder після монтування", async () => {
  const { env } = await taskDialog();
  const attrs = {};
  const input = { setAttribute: (k, v) => { attrs[k] = v; } };
  const form = { isConnected: true, querySelector: (s) => (s === "#tf-repo" ? input : null) };
  env.opts.onMount(form);
  await tick();
  assert.deepEqual(env.log.api, ["/api/modules?space=plain"], "запит із простором форми");
  assert.equal(attrs.placeholder, "git@gh.example:o/r.git");
  assert.equal(env.log.wire.length, 1, "проводка id/назви лишилась");
  assert.equal(env.log.wire[0][0], form);
});

test("підказка: вимкнений модуль, модуль без ролі vcs, збій запиту й порожній repo — placeholder не чіпаємо, помилки нема", async () => {
  for (const modules of [
    { modules: [{ ...GIT_ENTRY, enabled: false }] },
    { modules: [PUB_ENTRY] },
    { modules: [{ ...GIT_ENTRY, settings: [{ key: "repo" }] }] },
    { modules: [{ ...GIT_ENTRY, settings: [{ key: "repo", value: "" }] }] },
    {}, null,
  ]) {
    const { env } = await taskDialog({ modules });
    const attrs = {};
    env.opts.onMount({ isConnected: true, querySelector: () => ({ setAttribute: (k, v) => { attrs[k] = v; } }) });
    await tick();
    assert.deepEqual(attrs, {}, JSON.stringify(modules));
  }
  const { env } = await taskDialog({ apiFails: true });
  const attrs = {};
  env.opts.onMount({ isConnected: true, querySelector: () => ({ setAttribute: (k, v) => { attrs[k] = v; } }) });
  await tick();
  assert.deepEqual(attrs, {}, "збій запиту підказки не ламає форму");
});

test("підказка не питається там, де поля нема (ЛІГА, без ролі): жодного зайвого запиту", async () => {
  for (const space of [LIGA, NOVCS]) {
    const { env } = await taskDialog({ space });
    env.opts.onMount({ isConnected: true, querySelector: () => null });
    await tick();
    assert.deepEqual(env.log.api, [], JSON.stringify(space));
  }
});

test("підказка, що приїхала, коли форму вже закрито (відчеплена), нічого не пише", async () => {
  const { env } = await taskDialog();
  const attrs = {};
  env.opts.onMount({ isConnected: false, querySelector: () => ({ setAttribute: (k, v) => { attrs[k] = v; } }) });
  await tick();
  assert.deepEqual(attrs, {});
});

test("запит: зі значенням поля — vcs: {repo} (обрізане) через taskPost (клон — довга стеля); з порожнім чи пробілами — ключа vcs у тілі НЕМАЄ, а запит іде звичайним postForm", async () => {
  let r = await taskDialog();
  await r.submit({ repo: "  git@h:o/r.git \n" });
  assert.deepEqual(r.env.log.taskPost, [{ id: "lend", title: "Лендинг", space: "plain", vcs: { repo: "git@h:o/r.git" } }]);
  assert.deepEqual(r.env.log.post, [], "заповнене поле — сервер клонує, потрібна довга стеля, а не postForm");
  for (const repo of ["", "   ", "\n\t", undefined]) {
    r = await taskDialog();
    await r.submit({ repo });
    assert.deepEqual(r.env.log.post, [["/api/task-new", { id: "lend", title: "Лендинг", space: "plain" }]],
      `repo=${JSON.stringify(repo)}: порожнє поле не стає vcs: {repo: ''}, а без vcs сервер не клонує — звичайна стеля 20 с`);
    assert.deepEqual(r.env.log.taskPost, [], `repo=${JSON.stringify(repo)}: довгого запиту нема`);
  }
});

test("запит у ЛІГА: vcs не йде НІКОЛИ (навіть якщо значення repo якось прийшло), але стеля довга — перший клон триває хвилини", async () => {
  const r = await taskDialog({ space: LIGA });
  await r.submit({ repo: "git@h:o/r.git" });
  assert.deepEqual(r.env.log.taskPost, [{ id: "lend", title: "Лендинг", space: "liga" }]);
  assert.deepEqual(r.env.log.post, []);
});

test("запит у просторі без синку: звичайний postForm зі стелею 20 с, не taskPost і без vcs", async () => {
  const r = await taskDialog({ space: NOVCS });
  await r.submit({ repo: "git@h:o/r.git" });
  assert.deepEqual(r.env.log.post, [["/api/task-new", { id: "lend", title: "Лендинг", space: "plain" }]]);
  assert.deepEqual(r.env.log.taskPost, []);
});

test("перевірка id/назви йде ДО запиту; успіх — задача поточна, refreshGitlab(made.id), вихід з екрана", async () => {
  let r = await taskDialog();
  const msg = await r.submit({ title: "   " });
  assert.equal(msg, t("titleRequired"));
  assert.deepEqual(r.env.log.focus, ["title"]);
  assert.deepEqual(r.env.log.taskPost, [], "запиту не було");
  r = await taskDialog();
  const ok = await r.submit({ repo: "git@h:o/r.git" });
  assert.equal(ok, undefined);
  assert.deepEqual(r.env.log.reset, ["task"], "простір той самий — скидається лише пер-задачне");
  assert.deepEqual(r.env.log.refresh, ["t-1"]);
  assert.equal(r.env.log.leave, 1);
  assert.equal(r.env.currentTaskId, "t-1");
  assert.equal(r.env.homeData, null);
});

test("відмови створення: адреса — на поле repo; нема ролі — текст без поля; 409 space.json — готовий текст", async () => {
  const fail = async (code, message = "server text", status) => {
    const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error(message), { code, status }); } });
    const text = await r.submit({ repo: "ext::sh -c x" });
    return { text, focus: r.env.log.focus, refresh: r.env.log.refresh, leave: r.env.log.leave };
  };
  let f = await fail("vcs-bad-target", "repo address not allowed");
  assert.equal(f.text, `${t("taskErrVcsTarget")}\n${t("taskErrWhy", "repo address not allowed")}`, "M1: причина сервера — другим рядком");
  assert.deepEqual(f.focus, ["repo"], "aria-invalid і фокус — на полі «Репозиторій»");
  assert.equal(f.leave, 0, "після відмови з екрана не виходимо");
  f = await fail("vcs-needs-role");
  assert.equal(f.text, t("taskErrVcsRole"));
  assert.deepEqual(f.focus, []);
  f = await fail("space-json-unreadable", "unreadable", 409);
  assert.equal(f.text, t("cnRefSpaceJson"));
  assert.deepEqual(f.focus, []);
  f = await fail("task-exists");
  assert.equal(f.text, t("idTaken"));
  assert.deepEqual(f.focus, ["id"], "наявні відмови не змінились");
  f = await fail("timeout", "timeout");
  assert.equal(f.text, t("formTimeout"), "обрив стелі — той самий текст «міг устигнути»");
});

test("check-timeout / module-error (504/502 завислого чи зламаного модуля): загальний текст відмови з причиною сервера, поле не підсвічується", async () => {
  for (const [code, message] of [["check-timeout", "module check timed out"], ["module-error", "git-sync: boom"], ["vcs-error", "git-sync module is not loaded"]]) {
    const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error(message), { code }); } });
    const text = await r.submit({ repo: "git@h:o/r.git" });
    assert.equal(text, t("errFailed", message), code);
    assert.ok(text.includes(message), "причину сервера видно людині");
    assert.deepEqual(r.env.log.focus, [], `${code}: чужого поля не підсвічуємо`);
    assert.equal(r.env.log.leave, 0);
  }
  setLang("en");
  const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error("module check timed out"), { code: "check-timeout" }); } });
  assert.equal(await r.submit({ repo: "git@h:o/r.git" }), "Failed: module check timed out");
});

test("відмова без коду й невідомий код — загальний текст taskErrGeneric (як було), без причини сервера", async () => {
  for (const code of [undefined, "something-new"]) {
    const fail = async () => { throw Object.assign(new Error("<html>500"), { code }); };
    /* Порожнє поле — звичайний шлях (`postForm`); ЛІГА — довгий (`taskPost`): текст той самий. */
    let r = await taskDialog({ postForm: fail });
    assert.equal(await r.submit({}), t("taskErrGeneric"), String(code));
    r = await taskDialog({ space: LIGA, taskPost: fail });
    assert.equal(await r.submit({}), t("taskErrGeneric"), `ЛІГА, ${String(code)}`);
  }
});

/* ── taskPost: стеля 400 с, обрив → timeout ──────────────────────────────── */

function taskPostEnv(over = {}) {
  const log = { api: [], timers: [], cleared: [] };
  const env = {
    log, TASK_VCS_POST_TIMEOUT_MS,
    api: (path, opts) => { log.api.push([path, opts]); return env.apiImpl(path, opts); },
    apiImpl: async () => ({ ok: true, id: "t-1" }),
    setTimeout: (fn, ms) => { log.timers.push({ fn, ms }); return log.timers.length; },
    clearTimeout: (id) => log.cleared.push(id),
    ...over,
  };
  return env;
}

test("taskPost: POST /api/task-new з JSON-тілом і сигналом; стеля — TASK_VCS_POST_TIMEOUT_MS (400 с), таймер знімається", async () => {
  const env = taskPostEnv();
  const { taskPost } = load(env, { funcs: ["taskPost"] });
  const res = await taskPost({ id: "x", space: "s" });
  assert.deepEqual(res, { ok: true, id: "t-1" });
  assert.equal(env.log.api.length, 1);
  const [path, opts] = env.log.api[0];
  assert.equal(path, "/api/task-new");
  assert.equal(opts.method, "POST");
  assert.deepEqual(opts.headers, { "Content-Type": "application/json" });
  assert.equal(opts.body, JSON.stringify({ id: "x", space: "s" }));
  assert.ok(opts.signal instanceof AbortSignal, "сигнал доходить до fetch");
  assert.equal(env.log.timers.length, 1);
  assert.equal(env.log.timers[0].ms, 400000);
  assert.deepEqual(env.log.cleared, [1], "завершений запит не обрізається таймером");
});

test("taskPost: коли стеля минула — запит обривається, відмова має code: 'timeout' (формa каже formTimeout); інші відмови — як були", async () => {
  const env = taskPostEnv({
    apiImpl: (path, opts) => new Promise((_, rej) => {
      opts.signal.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
    }),
  });
  const { taskPost } = load(env, { funcs: ["taskPost"] });
  const p = taskPost({ id: "x" });
  env.log.timers[0].fn();
  await assert.rejects(p, (e) => e.code === "timeout" && e.message === "timeout");
  assert.deepEqual(env.log.cleared, [1]);
  assert.equal(taskErrKey("timeout"), "formTimeout");

  const env2 = taskPostEnv({ apiImpl: async () => { throw Object.assign(new Error("exists"), { code: "task-exists", status: 400 }); } });
  const f2 = load(env2, { funcs: ["taskPost"] });
  await assert.rejects(f2.taskPost({ id: "x" }), (e) => e.code === "task-exists" && e.status === 400, "чужа відмова не стає timeout");
  assert.deepEqual(env2.log.cleared, [1], "і на відмові таймер знято");
});

test("taskPost: порожнє тіло — {} (як postForm); стеля довша за стелю форми", async () => {
  const env = taskPostEnv();
  await load(env, { funcs: ["taskPost"] }).taskPost(undefined);
  assert.equal(env.log.api[0][1].body, "{}");
  assert.ok(env.log.timers[0].ms > FORM_POST_TIMEOUT_MS);
});

test("імпорти app.js: стеля, ключі й помічники Task 7 імпортовано", () => {
  const sm = /import \{([^}]*)\} from '\.\/spaces-model\.js'/.exec(src)?.[1] ?? "";
  for (const n of ["TASK_VCS_POST_TIMEOUT_MS", "taskErrShowsReason", "taskCreateClones"]) assert.match(sm, new RegExp(`\\b${n}\\b`), `${n} не імпортовано з spaces-model.js`);
  const cm = /import \{([^}]*)\} from '\.\/connections-model\.js'/.exec(src)?.[1] ?? "";
  assert.match(cm, /\broleCardId\b/, "roleCardId не імпортовано з connections-model.js");
});

/* ── майстер: запит кроку 4 не клонує ────────────────────────────────────── */

/** Тіло виклику `createWizard({...})` в `app.js` — проводка майстра. */
const wizWiring = () => {
  const m = /\nconst wiz = createWizard\(\{[\s\S]*?\n\}\);/.exec(src);
  assert.ok(m, "у app.js нема const wiz = createWizard({...})");
  return m[0];
};

/** Крок 4 майстра виконуємо як є: `submit4` із заглушками; `post` — вираз залежності з `app.js` над підставними `postForm`/`taskPost`. */
async function runSubmit4(post, extra = {}) {
  const calls = [];
  const wz = { step: 4, spaceId: "sp1", checking: false, taskIds: [], s4: { title: " Лендинг ", id: "lend", source: "empty", from: "" }, ...extra };
  const env = {
    wz, calls, t, taskFormError, taskErrField, taskErrKey,
    capture: () => {}, clearError: () => {}, setBusy: () => {}, showError: (f, k, fld) => calls.push(["showError", k, fld]),
    spaceGone: () => calls.push(["spaceGone"]),
    deps: { node: () => ({ querySelector: () => ({}) }), toast: (m) => calls.push(["toast", m]), openTask: async (m) => calls.push(["openTask", m]), exit: () => {}, post },
  };
  await new Function("env", `with (env) { ${nested(wsrc, "submit4")}\nreturn submit4(); }`)(env);
  return calls;
}

test("майстер: запит кроку 4 не несе vcs, сервер його не клонує — ЗАВЖДИ звичайний postForm (20 с), навіть у просторі з синком; довгого запиту в проводці нема", async () => {
  const log = [];
  const post = evalIn({
    postForm: async (p, b) => { log.push(["postForm", p, b]); return { id: "lend" }; },
    taskPost: async (b) => { log.push(["taskPost", b]); return { id: "lend" }; },
  }, depExpr("post"));
  const calls = await runSubmit4(post);
  assert.deepEqual(log, [["postForm", "/api/task-new", { id: "lend", title: "Лендинг", space: "sp1" }]],
    "завислий сервер не тримає майстер 400 с: клону в цього запиту нема, тіло без vcs");
  assert.deepEqual(calls.at(-1), ["openTask", { id: "lend" }]);
  /* З теки (`from`): так само коротко — `adopt_src` клон прибирає (`vcs and adopt_src is None`). */
  log.length = 0;
  await runSubmit4(post, { s4: { title: "Лендинг", id: "lend", source: "folder", from: "/tmp/m" } });
  assert.deepEqual(log.map((c) => c[0]), ["postForm"], "створення з теки теж не клонує");
  /* Статично: ні залежності `postTask`, ні `taskPost` у проводці майстра — довгий шлях лишився лише формі нової задачі. */
  assert.doesNotMatch(wizWiring(), /postTask|taskPost/);
  assert.doesNotMatch(wsrc, /postTask|taskPost/, "майстер не знає про довгу стелю");
});

test("майстер: submit4 створює задачу через deps.post (виконання з підставними залежностями); тіло — як до 4a", async () => {
  const calls = await runSubmit4(async (p, b) => ({ id: "lend", seen: [p, b] }));
  assert.deepEqual(calls.at(-1), ["openTask", { id: "lend", seen: ["/api/task-new", { id: "lend", title: "Лендинг", space: "sp1" }] }]);
});

test("майстер: статичний пін — deps.post(\"/api/task-new\", …); у шапці залежностей майстра довгого запиту нема", () => {
  assert.match(nested(wsrc, "submit4"), /made = await deps\.post\("\/api\/task-new", \{ id: vals\.id, title: vals\.title\.trim\(\), space: mine\.spaceId, \.\.\.\(folder \? \{ from \} : \{\}\) \}\);/);
  assert.match(wsrc, /post\(path, body\)[^\n]*postForm/, "шапка файла описує post як postForm");
  assert.doesNotMatch(nested(wsrc, "submit4"), /vcs/, "крок 4 майстра не шле vcs");
});

test("форма не ламається на полі, якого в ній нема: ctl.focus('repo') у майстрі й showError — тихий вихід", () => {
  /* `ask.js`: `ctl.focus(name)` → `namedItem(name)` → `if (!f) return;`. Виконуємо САМ метод. */
  const m = /focus\(name\) \{[\s\S]*?\n {8}\},/.exec(asrc);
  assert.ok(m, "метод focus у askForm");
  const focus = new Function("formEl", `return { ${m[0].replace(/,\s*$/, "")} }.focus;`)({ elements: { namedItem: () => null } });
  assert.doesNotThrow(() => focus("repo"));
  /* Майстер: `showError(form, key, "repo")` — `querySelector('[name="repo"]')` порожнє, текст помилки все одно показано. */
  const slot = { textContent: "", hidden: true };
  const form = { isConnected: true, querySelector: (s) => (s === "#wz-err" ? slot : null), querySelectorAll: () => [] };
  const env = { wz: { step: 4 }, deps: { node: () => null }, t };
  const showError = new Function("env", `with (env) { ${nested(wsrc, "showError")}\nreturn showError; }`)(env);
  assert.doesNotThrow(() => showError(form, "taskErrVcsTarget", taskErrField("taskErrVcsTarget")));
  assert.equal(slot.textContent, t("taskErrVcsTarget"));
  assert.equal(slot.hidden, false);
});

/* ── «Налаштувати…» → «Підключення» на картку ролі vcs (поправка 4) ───────────────────────────────────── */

test("glsetup: у ЛІГА — повідомлення про tasks.json й БЕЗ переходу; деінде — enterConnections('vcs')", () => {
  const go = (space) => {
    const entered = [];
    const env = mkEnv({ space, isLegacyVcs, enterConnections: (...a) => entered.push(a) });
    load(env, { acts: ["glsetup"] }).acts.glsetup();
    return { entered, tell: env.log.tell };
  };
  assert.deepEqual(go(LIGA), { entered: [], tell: [t("glSetupMsg")] });
  assert.deepEqual(go(PLAIN), { entered: [["vcs"]], tell: [] }, "роль vcs — фокус піде на картку її модуля");
});

test("enterConnections(role): запамʼятовує роль і вимагає фокус; без ролі — чистить стару (фокус на першу картку, як було)", () => {
  const run = (role, pre = {}) => {
    const env = {
      currentSpace: () => ({ id: "plain" }), spacesResp: {}, connEntrySeq: 0, connFocusPending: false, connFocusRole: "stale", ...pre,
      enterHome: (o) => { env.entered = o; },
    };
    new Function("env", `with (env) { ${declSource("enterConnections")}\nreturn enterConnections; }`)(env)(...(role === undefined ? [] : [role]));
    return env;
  };
  let env = run("vcs");
  assert.equal(env.connFocusRole, "vcs");
  assert.equal(env.connFocusPending, true, "навіть коли сторінка вже відкрита (enterHome не «свіжий») — фокус потрібен");
  assert.deepEqual(env.entered, { page: "conn" });
  env = run(undefined);
  assert.equal(env.connFocusRole, "", "звичайний вхід не успадковує стару роль");
  assert.equal(env.connFocusPending, false, "а фокус на першу картку ставить enterHome (fresh) сам");
  assert.deepEqual(env.entered, { page: "conn" });
  env = run("vcs", { currentSpace: () => null });
  assert.equal(env.entered, undefined, "простору нема — входу нема");
  assert.equal(env.connFocusRole, "stale", "і стан не чіпаємо");
  assert.equal(env.connFocusPending, false);
});

/* Холодний старт: сторінка `/api/spaces` не питала (`spacesResp === null`), а простір смуга знає з `curTask.space`. «Налаштувати
   репозиторій…» (`glsetup`), кнопка «Підключення» на «Задачах», що ще вантажаться, і клік по «Підключення…», що випередив відповідь
   дропдауна, мовчали — тепер вхід САМ читає перелік. Виконуємо СПРАВЖНІ `enterConnections` і `loadSpaces` (лічильник `spacesSeq`
   відкидає застарілі відповіді — на ньому тримаються тести порядку); мережа — `api`, що віддає відкладені відповіді. */
function defer() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
function mkConn(initial, over = {}) {
  const env = {
    currentSpace, t, spacesResp: initial, spacesSeq: 0, taskSwitchGen: 0, connEntrySeq: 0, connFocusPending: false, connFocusRole: "stale",
    entered: [], told: [], order: [], calls: [], waits: [], registry: { current: "plain", spaces: [PLAIN] },
    /* Кожен запит — своя відкладена відповідь (`waits[i]`): тест сам вирішує, коли й у якому порядку їх розв'язати. */
    api: (path) => { env.calls.push(path); env.order.push("api"); const d = defer(); env.waits.push(d); return d.promise; },
    tell: (m) => env.told.push(m),
    enterHome: (o) => { env.order.push("enter"); env.entered.push(o); },
    ...over,
  };
  return env;
}
const enterIn = (env, extra = {}) => load(env, { funcs: ["enterConnections", "loadSpaces"], ...extra });

test("enterConnections: холодний старт (перелік просторів ще не питали) — читає його РІВНО раз і лише тоді входить, з фокусом на ролі", async () => {
  const env = mkConn(null);
  const done = enterIn(env).enterConnections("vcs");
  assert.deepEqual(env.calls, ["/api/spaces"], "перелік замовлено одразу, один запит");
  assert.deepEqual(env.entered, [], "поки перелік у дорозі — входу нема (інакше сторінка відкрилась би без простору)");
  assert.equal(env.connFocusPending, false);
  env.waits[0].resolve(env.registry);
  await done;
  assert.equal(env.calls.length, 1, "один запит на вхід");
  assert.deepEqual(env.order, ["api", "enter"], "вхід — ПІСЛЯ читання переліку");
  assert.deepEqual(env.entered, [{ page: "conn", spaces: false }], "щойно прочитаний перелік loadConn вдруге не питає");
  assert.equal(env.connFocusRole, "vcs");
  assert.equal(env.connFocusPending, true, "фокус сяде на картку модуля ролі");
  assert.deepEqual(env.told, []);
});

test("enterConnections: теплий (перелік уже є) — без зайвого запиту й синхронно, як було; `loadConn` перечитає перелік сам", () => {
  for (const warm of [{ current: "plain", spaces: [PLAIN] }, { current: "gone", spaces: [PLAIN] }]) {
    const env = mkConn(warm);
    const p = enterIn(env).enterConnections("vcs");
    assert.deepEqual(env.calls, [], "перелік є — запиту нема");
    if (currentSpace(warm)) {
      assert.deepEqual(env.entered, [{ page: "conn" }], "вхід у тому ж такті, без `spaces: false`");
      assert.equal(env.connFocusRole, "vcs");
      assert.equal(env.connFocusPending, true);
    } else {
      assert.deepEqual(env.entered, [], "поточного простору в переліку нема — мовчання, як було");
      assert.equal(env.connFocusRole, "stale", "і стан не чіпаємо");
      assert.equal(env.connFocusPending, false);
    }
    assert.deepEqual(env.told, [], "теплий шлях ніколи не кличе помилку читання");
    assert.ok(p instanceof Promise);
  }
  const off = mkConn({ off: true, spaces: [] });
  enterIn(off).enterConnections("vcs");
  assert.deepEqual(off.calls, [], "шар просторів вимкнено — це готова відповідь, а не «ще не питали»");
  assert.deepEqual(off.entered, []);
  assert.deepEqual(off.told, []);
});

test("enterConnections: холодний, але простору справді нема (порожній реєстр, шар вимкнено) — один запит і мовчання, стан не чіпаємо", async () => {
  for (const registry of [{ current: null, spaces: [] }, { off: true, spaces: [] }]) {
    const env = mkConn(null);
    const done = enterIn(env).enterConnections("vcs");
    env.waits[0].resolve(registry);
    await done;
    assert.equal(env.calls.length, 1);
    assert.deepEqual(env.entered, []);
    assert.deepEqual(env.told, [], "відповідь прийшла — це не збій читання");
    assert.equal(env.connFocusRole, "stale");
    assert.equal(env.connFocusPending, false);
  }
});

test("enterConnections: перелік не прочитався (реєстр/сервер мовчить) — не мовчимо: tell із причиною про spaces.json, входу нема", async () => {
  const env = mkConn(null);
  const done = enterIn(env).enterConnections("vcs");
  env.waits[0].reject(Object.assign(new Error("boom"), { code: "spaces-unreadable" }));
  await done;
  assert.deepEqual(env.told, [t("tasksErrSpaces")], "рівно одне повідомлення наявним ключем словника");
  assert.match(env.told[0], /spaces\.json/);
  assert.deepEqual(env.entered, []);
  assert.equal(env.connFocusRole, "stale");
  assert.equal(env.connFocusPending, false);
  assert.equal(env.spacesResp, null, "loadSpaces збій лише проковтнув");
});

test("enterConnections: поки перелік летить, людина пішла (логотип/майстер/відкрила задачу — connEntrySeq; інша задача чи простір — taskSwitchGen) — виходимо мовчки, без tell", async () => {
  for (const depart of [(e) => { e.connEntrySeq += 1; }, (e) => { e.taskSwitchGen += 1; }]) {
    for (const reply of ["ok", "fail"]) {
      const env = mkConn(null);
      const done = enterIn(env).enterConnections("vcs");
      depart(env);
      if (reply === "ok") env.waits[0].resolve(env.registry); else env.waits[0].reject(new Error("x"));
      await done;
      assert.deepEqual(env.entered, [], `пішла — вхід не відбувся (${reply})`);
      assert.deepEqual(env.told, [], `і про збій читання мовчимо: вона вже вирішила інакше (${reply})`);
      assert.equal(env.connFocusRole, "stale");
      assert.equal(env.connFocusPending, false);
    }
  }
});

test("enterConnections: два паралельні холодні входи, відповіді не по черзі — навігація РІВНО одна (у будь-якому порядку відповідей), без tell", async () => {
  for (const order of [[1, 0], [0, 1]]) {
    const env = mkConn(null);
    const lib = enterIn(env);
    const a = lib.enterConnections("vcs");
    const b = lib.enterConnections("vcs");
    assert.equal(env.calls.length, 2, "обидва кліки замовили перелік");
    for (const i of order) { env.waits[i].resolve(env.registry); await tick(); }
    await Promise.all([a, b]);
    assert.deepEqual(env.entered, [{ page: "conn", spaces: false }], `навігація одна (порядок відповідей ${order})`);
    assert.deepEqual(env.told, [], "відкинута застарілою відповіддю — не збій");
    assert.equal(env.connFocusRole, "vcs");
    assert.deepEqual(env.spacesResp, env.registry);
  }
});

test("enterConnections: відповідь відкинув новіший запит переліку (дропдаун/палітра) — це не збій читання, tell не показуємо", async () => {
  const env = mkConn(null);
  const lib = enterIn(env);
  const entry = lib.enterConnections("vcs");
  const other = lib.loadSpaces();                      // палітра відкрилась, поки наш запит у польоті
  env.waits[0].resolve(env.registry);                  // наша відповідь — застаріла: `spacesSeq` пішов далі, `spacesResp` лишився `null`
  await entry;
  assert.equal(env.spacesResp, null);
  assert.deepEqual(env.told, [], "чужий запит у польоті — не «реєстр не читається»");
  assert.deepEqual(env.entered, []);
  env.waits[1].resolve(env.registry);
  await other;
  assert.deepEqual(env.spacesResp, env.registry, "перелік усе ж зʼявився — від чужого запиту");
});

test("кнопка «Підключення» на «Задачах», що ще вантажаться (homeData = {loading:true}) — холодний вхід: wireHome → enterConnections читає перелік один раз і веде на сторінку", async () => {
  const handlers = {};
  const env = mkConn(null, {
    homeOpen: true, homePage: "tasks", homeData: { loading: true, space: PLAIN },
    wiz: { click: () => { throw new Error("майстер не мав би бути"); } },
  });
  load(env, { funcs: ["enterConnections", "loadSpaces", "wireHome"] }).wireHome({ addEventListener: (type, fn) => { handlers[type] = fn; } });
  const btn = { dataset: { th: "conn" } };
  handlers.click({ target: { closest: (sel) => (sel === "[data-th]" ? btn : null) } });
  assert.deepEqual(env.calls, ["/api/spaces"], "кнопка не чекає, поки екран дочитає перелік сам");
  assert.deepEqual(env.entered, []);
  env.waits[0].resolve(env.registry);
  await tick();
  assert.deepEqual(env.entered, [{ page: "conn", spaces: false }]);
  assert.equal(env.connFocusRole, "", "кнопка веде без ролі: фокус на першу картку ставить enterHome (fresh)");
  assert.deepEqual(env.told, []);
});

test("лічильник входу: enterHome із явною сторінкою й leaveHome його збільшують (це «людина пішла»), оновлення без сторінки — ні", () => {
  assert.match(fn("enterHome"), /\n  if \(page !== undefined\) connEntrySeq \+= 1;\n/);
  assert.match(fn("leaveHome"), /\n  connEntrySeq \+= 1;/);
  assert.match(src, /\nlet connEntrySeq = 0;\n/, "оголошено серед стану модуля (TDZ: enterHome кличе вже перший render)");
  assert.ok(src.indexOf("let connEntrySeq = 0;") < src.indexOf("function enterHome("), "`let` ВИЩЕ за enterHome");
});

test("glsetup на холодному старті: клік веде на «Підключення» з фокусом на ролі vcs (справжні glsetup, enterConnections і loadSpaces)", async () => {
  const env = mkConn(null, { ...mkEnv({ space: PLAIN, isLegacyVcs }), spaceNow: () => PLAIN, entered: [], told: [], order: [], calls: [], waits: [] });
  Object.assign(env, { api: (path) => { env.calls.push(path); const d = defer(); env.waits.push(d); return d.promise; }, tell: (m) => env.told.push(m) });
  const lib = enterIn(env, { acts: ["glsetup"] });
  lib.acts.glsetup();
  assert.deepEqual(env.calls, ["/api/spaces"]);
  env.waits[0].resolve(env.registry);
  await tick();
  assert.deepEqual(env.entered, [{ page: "conn", spaces: false }]);
  assert.equal(env.connFocusRole, "vcs");
  assert.deepEqual(env.told, [], "повідомлення про tasks.json — лише в ЛІГА");
});

/** Вузол-картка для `focusConnLanding`: кнопки `[data-cn]` (перша не вимкнена), `focus` пише в журнал. */
function mkHome(cards, log) {
  const btn = (id, name, disabled = false) => ({ id, name, disabled, focus: (o) => log.push([`${id}/${name}`, o]) });
  const q = new Map(cards.map(([id, ...names]) => [id, names.map((n, i) => btn(id, n, i === 0 && id.startsWith("off:")))]));
  return {
    querySelector: (sel) => {
      const card = /^\.cn-card\[data-id="(.+)"\]$/.exec(sel);
      if (card) {
        const list = q.get(card[1]);
        if (!list) return null;
        return { querySelector: (s) => (s.includes(":not([disabled])") ? list.find((b) => !b.disabled) ?? null : list[0]) };
      }
      if (sel === '.cn-card [data-cn], [data-cn="retry"]') return [...q.values()][0]?.[0] ?? null;
      return null;
    },
  };
}
test("focusConnLanding: роль vcs → кнопка картки її модуля (і прокрутка — preventScroll не ставимо); без ролі чи картки — перша кнопка, як було", () => {
  const log = [];
  const state = { list: [{ id: "static-publish", roles: ["publish"], enabled: true }, { id: "git-sync", roles: ["vcs"], enabled: true }],
    spaceId: "plain" };
  const env = (home, over = {}) => ({
    homeNode: () => home, CSS: { escape: (s) => s }, roleCardId, connState: state,
    connSpace: () => ({ id: "plain", capabilities: { vcs: "git-sync" } }), ...over,
  });
  const land = (e, role) => new Function("env", `with (env) { ${declSource("focusConnLanding")}\nreturn focusConnLanding; }`)(e)(role);
  const home = mkHome([["static-publish", "configure"], ["git-sync", "configure", "check"]], log);
  land(env(home), "vcs");
  assert.deepEqual(log.splice(0), [["git-sync/configure", { preventScroll: false }]], "картка ролі, з прокруткою");
  land(env(home), "");
  assert.deepEqual(log.splice(0), [["static-publish/configure", { preventScroll: true }]], "без ролі — перша кнопка першої картки, без прокрутки (як було)");
  land(env(home, { connSpace: () => ({ id: "plain", capabilities: { vcs: null } }), connState: { ...state, list: [] } }), "vcs");
  assert.deepEqual(log.splice(0), [["static-publish/configure", { preventScroll: true }]], "картки ролі нема — запасний шлях");
  const off = mkHome([["off:git-sync", "enable", "x"]], log);
  land(env(off, { connSpace: () => ({ id: "plain", capabilities: { vcs: null } }),
    connState: { ...state, list: [{ id: "off:git-sync", roles: ["vcs"], enabled: false }] } }), "vcs");
  assert.deepEqual(log.splice(0), [["off:git-sync/x", { preventScroll: false }]], "перша НЕвимкнена кнопка картки");
  assert.doesNotThrow(() => land(env(null), "vcs"), "вузла нема — тихо");
});

test("loadConn: перший фокус бере роль із connFocusRole і не краде фокус у палітри чи діалогу", () => {
  const b = fn("loadConn").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(b, /if \(connFocusPending\) \{\s*connFocusPending = false;\s*const role = connFocusRole;\s*connFocusRole = '';\s*if \(!paletteOverlay && !document\.querySelector\('\.cv-ask-scrim'\)\) focusConnLanding\(role\);\s*\}/);
  assert.match(src, /\nlet connFocusRole = '';/, "стан оголошено поруч із connFocusPending (TDZ)");
});

test("newTaskDialog (статично, як просить план): поле — за hasVcs && !isLegacyVcs, vcs у тілі — лише зі значенням, довгий запит (taskPost) — лише коли він клонує", () => {
  const b = fn("newTaskDialog");
  assert.match(b, /const withRepo = hasVcs\(sp\) && !isLegacyVcs\(sp\);/);
  assert.match(b, /taskFormHTML\(withRepo \? \{ repo: \{\} \} : \{\}\)/, "поле «Репозиторій» передається формі лише тоді");
  assert.match(b, /const repo = withRepo \? String\(vals\.repo \?\? ''\)\.trim\(\) : '';/);
  assert.match(b, /\.\.\.\(repo \? \{ vcs: \{ repo \} \} : \{\}\)/, "порожнє значення — ключа vcs у тілі нема");
  assert.match(b, /made = await \(clones \? taskPost\(body\) : postForm\('\/api\/task-new', body\)\);/);
  assert.match(b, /return taskErrShowsReason\(e\.code, 'vcs' in body\) \? t\('errFailed', why\) : t\(key2\);/);
  assert.match(src, /\nfunction taskPost\(body\) \{\n {2}const ctl = new AbortController\(\);\n {2}const timer = setTimeout\(\(\) => ctl\.abort\(\), TASK_VCS_POST_TIMEOUT_MS\);/);
});

/* ══ Ревʼю Task 7: ознака довгого створення, git-sync без repo, причини відмов, стеля 400 с ═════════════════════ */

test("ревʼю Task 7: нові ключі — обома мовами, тексти дослівно", () => {
  setLang("uk");
  assert.equal(DICT.uk.taskCreateWait, "Перший клон репозиторію може тривати кілька хвилин");
  assert.equal(DICT.en.taskCreateWait, "The first clone of the repository may take a few minutes");
  assert.equal(DICT.uk.cnCheckOkGitNoRepo, "Працює. Типовий репозиторій не задано — задайте його вище або в задачі; задача без нього лишиться без синхронізації.");
  assert.equal(DICT.en.cnCheckOkGitNoRepo, "Works. No default repository — set it above or in a task; a task without one stays unsynced.");
  assert.equal(DICT.uk.taskErrWhy("x"), "Причина: x");
  assert.equal(DICT.en.taskErrWhy("x"), "Reason: x");
});

/* ── I1: ознака довгого створення ────────────────────────────────────────── */

const deferred = () => { let res; let rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { p, res, rej }; };

test("I1: поки йде taskPost — кнопка «Створюю…», рядок-статус role=status у формі (текст з затримкою), після відмови — усе зняте", async () => {
  const d = deferred();
  const r = await taskDialog({ taskPost: () => d.p });
  const sub = r.submit({ repo: "git@h:o/r.git" });
  await tick();
  assert.equal(r.form.ok.textContent, t("wzCreating"), "підпис кнопки на час запиту");
  assert.equal(r.form.notes.length, 1, "один рядок-статус");
  const note = r.form.notes[0];
  assert.equal(note.attrs.role, "status", "жива область: читач озвучить");
  assert.equal(note.className, "cv-form-note");
  assert.equal(note.textContent, "", "щойно вставлена жива область порожня: текст ставиться пізніше, інакше читач її не озвучить");
  assert.equal(r.timers.length, 1);
  assert.equal(r.timers[0].ms, 150, "затримка потрібна: щойно вставлену живу область читач не озвучує, а зміну тексту в ній — так");
  r.timers[0].fn();
  assert.equal(note.textContent, "Перший клон репозиторію може тривати кілька хвилин");
  d.rej(Object.assign(new Error("offline"), { code: "vcs-bad-target" }));
  await sub;
  assert.equal(r.form.ok.textContent, "Створити задачу", "після відмови підпис кнопки повернуто");
  assert.equal(note.live, false, "рядок-статус знято");
});

test("I1: після успіху рядок-статус знято, а підпис «Створюю…» лишається до закриття діалогу (форма ще вимкнена)", async () => {
  const d = deferred();
  const r = await taskDialog({ taskPost: () => d.p });
  const sub = r.submit({ repo: "git@h:o/r.git" });
  await tick();
  r.timers[0].fn();
  d.res({ id: "t-1", space: "plain" });
  await sub;
  assert.equal(r.form.notes[0].live, false);
  assert.equal(r.form.ok.textContent, t("wzCreating"), "підпис не блимає назад, поки dialog продовжує перехід");
  assert.equal(r.timers[0].on, false, "таймер тексту знято (не спрацює на знятому рядку)");
});

test("I1: затримка тексту знімається й на відмові (таймер не стріляє на вже знятому рядку)", async () => {
  const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error("x"), { code: "task-exists" }); } });
  await r.submit({ repo: "git@h:o/r.git" });
  assert.equal(r.timers.length, 1);
  assert.equal(r.timers[0].on, false);
});

test("довга стеля й рядок про клон — лише коли запит справді клонує: поле заповнене чи простір ЛІГА; порожнє поле, простір без синку — звичайний шлях без жодної ознаки", async () => {
  /* Сервер клонує, лише коли є `vcs` у тілі (без `from`) або профільний `gitlab` ЛІГИ (`_task_new_write`). Решта запитів — миттєві. */
  const cases = [
    ["заповнене поле", PLAIN, { repo: "git@h:o/r.git" }, true],
    ["ЛІГА без поля", LIGA, {}, true],
    ["ЛІГА, значення repo якось прийшло", LIGA, { repo: "git@h:o/r.git" }, true],
    ["ЛІГА з явним git-sync, порожнє поле (сервер бере профільний gitlab)", LIGA_GIT, { repo: "" }, true],
    ["ЛІГА з явним git-sync, самі пробіли", LIGA_GIT, { repo: "  " }, true],
    ["ЛІГА з явним git-sync, поле не прийшло", LIGA_GIT, {}, true],
    ["ЛІГА з явним git-sync, заповнене поле", LIGA_GIT, { repo: "git@h:o/r.git" }, true],
    ["ЛІГА без ролі vcs", LIGA_NOVCS, {}, false],
    ["простір зі старої форми відповіді (без integrations і capabilities)", { id: "old" }, {}, true],
    ["порожнє поле", PLAIN, { repo: "" }, false],
    ["самі пробіли", PLAIN, { repo: "   " }, false],
    ["поле не прийшло", PLAIN, {}, false],
    ["простір без синку", NOVCS, {}, false],
    ["простір без синку, значення repo якось прийшло", NOVCS, { repo: "git@h:o/r.git" }, false],
  ];
  for (const [name, space, vals, clones] of cases) {
    const r = await taskDialog({ space, reply: { id: "t-1", space: space.id } });
    await r.submit(vals);
    assert.deepEqual([r.env.log.taskPost.length, r.env.log.post.length], clones ? [1, 0] : [0, 1], `${name}: ${clones ? "довгий" : "звичайний"} запит`);
    assert.deepEqual([r.form.notes.length, r.timers.length], clones ? [1, 1] : [0, 0], `${name}: рядок-статус і його таймер`);
    assert.equal(r.form.ok.textContent, clones ? t("wzCreating") : "Створити задачу", `${name}: підпис кнопки`);
  }
});

test("невідомий простір (spaceNow() порожній): форму не відкриваємо й нічого не питаємо — як і було", async () => {
  const r = await taskDialog({ space: null });
  assert.equal(r.env.opts, undefined, "askForm не кликано");
  assert.deepEqual([r.env.log.post, r.env.log.taskPost, r.env.log.api, r.timers], [[], [], [], []]);
});

test("звичайний запит (порожнє поле, простір без синку): поки він летить — жодних ознак довгого створення, а відмова нічого не мусить знімати", async () => {
  for (const [space, vals] of [[PLAIN, { repo: "" }], [PLAIN, {}], [NOVCS, {}]]) {
    const d = deferred();
    const r = await taskDialog({ space, postForm: () => d.p });
    const sub = r.submit(vals);
    await tick();
    assert.deepEqual([r.form.ok.textContent, r.form.notes.length, r.timers.length], ["Створити задачу", 0, 0], `${space.id}: форма як була`);
    d.rej(Object.assign(new Error("offline"), { code: "task-exists" }));
    await sub;
    assert.deepEqual([r.form.ok.textContent, r.form.notes.length, r.timers.length], ["Створити задачу", 0, 0]);
  }
});

test("I1: англійською — той самий рядок мовою інтерфейсу", async () => {
  setLang("en");
  const d = deferred();
  const r = await taskDialog({ taskPost: () => d.p });
  const sub = r.submit({ repo: "git@h:o/r.git" });
  await tick();
  r.timers[0].fn();
  assert.equal(r.form.ok.textContent, "Creating…");
  assert.equal(r.form.notes[0].textContent, "The first clone of the repository may take a few minutes");
  d.res({ id: "t-1", space: "plain" });
  await sub;
});

test("I1: showCreateWait — статично: рядок вставляється ПЕРЕД слотом помилки, не в ЛІГА-розмітку; майстер уже має «Створюю…» і не клонує", () => {
  const b = fn("newTaskDialog");
  assert.match(b, /const clones = taskCreateClones\(sp, body\);/, "клонує лише запит із vcs у тілі або простір з інтеграціями й роллю vcs");
  assert.match(b, /const stopWait = clones \? showCreateWait\(ctl\.form\) : null;/);
  assert.match(declSource("showCreateWait"), /slot\.before\(note\)/);
  /* Майстер: запит кроку 4 не несе `vcs` (клон у сервера — лише для `gitlab`/`vcs`), форма вже підписується «Створюю…» (`setBusy`). */
  const s4 = nested(wsrc, "submit4");
  assert.match(s4, /setBusy\(form, true, "wzCreating"\)/);
  assert.doesNotMatch(s4, /vcs/, "крок 4 майстра не шле vcs, тож перший клон там не відбувається — рядка про клон там бути не мусить");
});

/* ── M1/M2: причини відмов ───────────────────────────────────────────────── */

test("M1: vcs-bad-target — перший рядок про адресу + друга лінія з причиною сервера (текст сервера — як дані, не розмітка)", async () => {
  const evil = "branch: <img src=x onerror=alert(1)>";
  const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error(evil), { code: "vcs-bad-target" }); } });
  const text = await r.submit({ repo: "git@h:o/r.git" });
  assert.equal(text, `${t("taskErrVcsTarget")}\n${t("taskErrWhy", evil)}`);
  assert.deepEqual(r.env.log.focus, ["repo"], "підсвітка поля лишилась");
  /* Слот помилки пише `textContent` (не `innerHTML`): рядок із сервера не стає розміткою. */
  assert.match(asrc, /error\(msg\) \{\s*const el = errEl\(\);\s*if \(!el\) return;\s*el\.textContent = msg \|\| '';/);
  /* HTML-тіло відмови (без JSON) — причина зі статусного рядка, не розмітка: `requestErrText`. */
  const html = await taskDialog({ taskPost: async () => { throw Object.assign(new Error("<!DOCTYPE HTML>"), { code: "vcs-bad-target", body: "<!DOCTYPE HTML>", statusText: "bad target" }); } });
  assert.equal(await html.submit({ repo: "git@h:o/r.git" }), `${t("taskErrVcsTarget")}\n${t("taskErrWhy", "bad target")}`);
});

test("M1: порожня причина — лише перший рядок (без «Причина: »)", async () => {
  const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error(""), { code: "vcs-bad-target" }); } });
  assert.equal(await r.submit({ repo: "git@h:o/r.git" }), t("taskErrVcsTarget"));
});

test("M2: з vcs у тілі БУДЬ-ЯКИЙ незмаплений код (bad-settings, secrets-unreadable, bad-manifest, без коду) — «Не вдалося: <причина>», без підсвітки", async () => {
  for (const code of ["bad-settings", "secrets-unreadable", "bad-manifest", "module-changed", "task-create-failed", "something-new", undefined]) {
    const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error("server says no"), { code }); } });
    const text = await r.submit({ repo: "git@h:o/r.git" });
    assert.equal(text, t("errFailed", "server says no"), String(code));
    assert.deepEqual(r.env.log.focus, [], `${String(code)}: підсвітки нема`);
  }
});

test("M2: без vcs у тілі (порожнє поле, ЛІГА, простір без синку) незмаплений код лишається загальним «Спробуй ще раз» — як було", async () => {
  const boom = async () => { throw Object.assign(new Error("boom"), { code: "bad-settings" }); };
  /* Порожнє поле й простір без синку — звичайний шлях (`postForm`), ЛІГА — довгий (`taskPost`): загальний текст той самий. */
  for (const [space, vals] of [[PLAIN, { repo: "" }], [PLAIN, {}], [NOVCS, {}], [LIGA, { repo: "x" }], [LIGA, {}]]) {
    const r = await taskDialog({ space, postForm: boom, taskPost: boom });
    assert.equal(await r.submit(vals), t("taskErrGeneric"), JSON.stringify([space.id, vals]));
  }
});

test("M2: змаплені коди з vcs у тілі лишають свій текст (task-exists, timeout, space.json), причина сервера їх не підміняє", async () => {
  for (const [code, key] of [["task-exists", "idTaken"], ["timeout", "formTimeout"], ["space-json-unreadable", "cnRefSpaceJson"], ["vcs-needs-role", "taskErrVcsRole"]]) {
    const r = await taskDialog({ taskPost: async () => { throw Object.assign(new Error("server text"), { code }); } });
    assert.equal(await r.submit({ repo: "git@h:o/r.git" }), t(key), code);
  }
});

/* ── I2: git-sync без repo — жодного сирого англійського detail ────────────── */

const GIT_E = (repo) => ({ id: "git-sync", name: "Синхронізація з git", roles: ["vcs"], enabled: true, implicit: false, status: "ok",
  settings: [{ key: "repo", type: "text", label: "Репозиторій", required: false, ...(repo === undefined ? {} : { value: repo }) },
    { key: "branch", type: "text", label: "Гілка", required: false, value: "main" }] });

test("I2: verdictText для вбудованого git-sync — успіх без repo: локалізований текст без detail; з repo: просто «Працює.» без англійського detail", () => {
  setLang("uk");
  assert.deepEqual(verdictText({ ok: true, detail: "the repository is set per task" }, GIT_E(undefined)),
    { key: "cnCheckOkGitNoRepo", detail: "" });
  assert.deepEqual(verdictText({ ok: true, detail: "the repository is set per task" }, GIT_E("")), { key: "cnCheckOkGitNoRepo", detail: "" });
  assert.deepEqual(verdictText({ ok: true, detail: "the repository is set per task" }, GIT_E("   ")), { key: "cnCheckOkGitNoRepo", detail: "" });
  assert.deepEqual(verdictText({ ok: true, detail: "branch main found" }, GIT_E("git@h:o/r.git")), { key: "cnCheckOk", detail: "" });
  assert.deepEqual(verdictText({ ok: true, detail: "branch dev is not on the remote yet — the first send creates it" }, GIT_E("git@h:o/r.git")),
    { key: "cnCheckOk", detail: "" });
  /* Решта модулів і відмови — як було: деталь іде людині (це діагностика, а не мова автора). */
  assert.deepEqual(verdictText({ ok: true, detail: "2 tokens" }, { id: "css-tokens", settings: [] }), { key: "cnCheckOk", detail: "2 tokens" });
  assert.deepEqual(verdictText({ ok: true, detail: "2 tokens" }), { key: "cnCheckOk", detail: "2 tokens" });
  assert.deepEqual(verdictText({ ok: true, detail: "x" }, { ...GIT_E(undefined), custom: true }), { key: "cnCheckOk", detail: "x" },
    "СВІЙ модуль з id git-sync — не вбудований: його мова — його справа");
  assert.deepEqual(verdictText({ ok: false, error: "vcs-offline", detail: "fatal: x" }, GIT_E(undefined)), { key: "cnErrVcsOffline", detail: "fatal: x" });
  assert.deepEqual(verdictText({ ok: true, detail: "d" }, { id: "git-sync" }), { key: "cnCheckOk", detail: "" },
    "запис без settings: невідомо, чи є repo, — не стверджуємо «без репозиторію»");
});

test("I2: «Перевірити» в панелі — виконання cnDrawerCheck: у результаті немає сирого англійського рядка модуля", async () => {
  const mk = (entry, check) => {
    const env = {
      cnDrawer: { busy: false, entry, spaceId: "plain", id: "git-sync", form: null },
      readCnForm: () => ({ values: {}, erase: [] }), cnDrawerNode: () => ({}), paintCnDrawer: () => {}, loadConn: () => {},
      postForm: async () => ({ check }), verdictText, refusalView,
    };
    return env;
  };
  const env = mk(GIT_E(undefined), { ok: true, detail: "the repository is set per task" });
  await new Function("env", `with (env) { ${declSource("cnDrawerCheck")}\nreturn cnDrawerCheck(); }`)(env);
  assert.deepEqual(env.cnDrawer.result, { kind: "ok", key: "cnCheckOkGitNoRepo", detail: "" });
  const html = resultHTML(env.cnDrawer.result);
  assert.match(html, /Працює\. Типовий репозиторій не задано — задайте його вище або в задачі; задача без нього лишиться без синхронізації\./);
  assert.doesNotMatch(html, /the repository|per task/i);
  setLang("en");
  assert.match(resultHTML(env.cnDrawer.result), /Works\. No default repository — set it above or in a task; a task without one stays unsynced\./);
  setLang("uk");
  const ok = mk(GIT_E("git@h:o/r.git"), { ok: true, detail: "branch main found" });
  await new Function("env", `with (env) { ${declSource("cnDrawerCheck")}\nreturn cnDrawerCheck(); }`)(ok);
  assert.doesNotMatch(resultHTML(ok.cnDrawer.result), /branch main/);
  assert.match(resultHTML(ok.cnDrawer.result), /Працює\./);
});

test("I2: збереження в панелі (cnSubmit) передає запис модуля до verdictText — статично", () => {
  assert.match(declSource("cnSubmit"), /result: \{ kind: 'failed', \.\.\.verdictText\(r\?\.check, entry\) \}/);
  assert.match(declSource("cnDrawerCheck"), /\.\.\.verdictText\(r\?\.check, mine\.entry\) \}/);
});

test("I2: крок 3 майстра — runOp: результат запису git-sync без repo локалізований, без англійського detail", async () => {
  const entry = GIT_E(undefined);
  const fields = formFields(entry);
  const init = initialForm(fields);
  const card = { entry, fields, values: init.values, erase: [], result: null };
  const mine = { cards: [card], spaceId: "sp1", offs: [], waits: [] };
  const posts = [];
  const env = {
    t, holdersByRole: () => new Map(), refusalView, modName: (e) => e.id, writePayload, formPatch, verdictText,
    deps: { post: async (path, body) => { posts.push([path, body]); return { check: { ok: true, detail: "the repository is set per task" }, module: entry }; } },
    cardFrom: (e) => ({ entry: e }), clearSecrets: () => {}, paint: () => {},
  };
  const run = new Function("env", `with (env) { ${nested(wsrc, "runOp")}\nreturn runOp; }`)(env);
  const res = await run(mine, { op: "settings", id: "git-sync", roles: ["vcs"], stale: [], after: [] }, [entry],
    new Map([["git-sync", { fields, init, cur: init }]]), { written: new Set(), replaced: new Set(), touched: new Set() });
  assert.deepEqual(res, { kind: "ok", key: "cnCheckOkGitNoRepo", detail: "" });
  assert.equal(posts[0][0], "/api/module-settings");
  assert.doesNotMatch(resultHTML(card.result), /the repository|per task/i);
  assert.match(nested(wsrc, "runOp"), /\.\.\.verdictText\(r\?\.check, r\?\.module \?\? card\?\.entry\)/);
});

/* ── M4: крок 2 майстра — git-sync типово не вибраний ────────────────────── */

test("M4: крок 2 — git-sync (не ввімкнений) має секцію «Синхронізація з git», «Без модуля» відмічено, у плані запису нема enable", () => {
  const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
  const list = [
    M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok" }), M("vercel-publish", ["publish"]),
    M("supabase-comments", ["comments"]), M("git-sync", ["vcs"]), M("css-tokens", ["tokens"]),
  ];
  const pick = initialPick(list);
  assert.deepEqual([...pick], ["static-publish"], "вибрані лише ті, хто зараз тримає роль");
  const secs = wizardSections(list);
  assert.deepEqual(secs.map((x) => x.role), ["publish", "comments", "vcs", "tokens"]);
  const h = wizardHTML({
    step: 2, created: true, busy: false, s1: { name: "S", color: "space-1", path: "~/s", folderFirst: false },
    s2: { list, failed: null, capsError: false, pick, path: "~/s" },
    s3: { cards: [], offs: [], waits: [], failed: null, loading: false },
    s4: { title: "", id: "", source: "empty", from: "", spaceName: "S", tasks: 0 },
  });
  const sec = /<fieldset class="wz-sec"[^>]*><legend class="cn-sec-h">Синхронізація з git<\/legend>[\s\S]*?<\/fieldset>/.exec(h)?.[0] ?? "";
  assert.ok(sec, "секція vcs є на кроці 2");
  assert.match(sec, /value="git-sync"[^>]*data-role="vcs"(?![^>]*checked)[^>]*>/, "радіо git-sync НЕ відмічене");
  assert.match(sec, /<input type="radio" id="wz-o-\d-none" name="wz-r-\d" value="" data-wz-pick data-role="vcs" checked>/, "«Без модуля» відмічено");
  const plan = writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list });
  assert.deepEqual(plan.filter((o) => o.id === "git-sync"), [], "git-sync у плані запису немає: нічого не вмикається мовчки");
  assert.deepEqual(plan, []);
});

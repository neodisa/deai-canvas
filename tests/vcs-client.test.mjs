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
import { DICT, setLang, t } from "../app/i18n.js";
import { filterActions, paletteActions } from "../app/shell-palette.js";
import { barHTML } from "../app/shell-bar.js";
import {
  FORM_POST_TIMEOUT_MS, TASK_VCS_POST_TIMEOUT_MS, VCS_BUSY_MAX_TRIES, VCS_BUSY_RETRY_MS, hasVcs, isLegacyVcs,
  requestErrText, spaceChanged, vcsBrand, vcsErrKey, vcsFailKey, vcsLabel, vcsWebUrl,
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

test("стеля запиту створення задачі з синком — 200 с, довша за стелю форми", () => {
  assert.equal(TASK_VCS_POST_TIMEOUT_MS, 200000);
  assert.ok(TASK_VCS_POST_TIMEOUT_MS > FORM_POST_TIMEOUT_MS);
});

/* ── підпис репозиторію: білий список GitLab/GitHub/Git, решта — за простором ─ */

const LIGA = { id: "liga", integrations: true, capabilities: { vcs: "legacy" } };
const PLAIN = { id: "plain", integrations: false, capabilities: { vcs: "git-sync" } };

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
  assert.match(src, /\n  glsetup: \(\) => \{ if \(isLegacyVcs\(spaceNow\(\)\)\) tell\(t\('glSetupMsg'\)\); else enterConnections\(\); \},/);
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

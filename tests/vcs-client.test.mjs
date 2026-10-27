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
  FORM_POST_TIMEOUT_MS, TASK_VCS_POST_TIMEOUT_MS, hasVcs, isLegacyVcs, vcsBrand, vcsErrKey,
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

/* ── підпис репозиторію: лише два відомі, решта — «GitLab» ────────────────── */

test("vcsBrand: GitHub і Git — підпис, решта (і службові імена обʼєкта) — порожньо", () => {
  assert.equal(vcsBrand("GitHub"), "GitHub");
  assert.equal(vcsBrand("Git"), "Git");
  for (const x of ["GitLab", "", null, undefined, 5, "github", "constructor", "__proto__", "toString", "hasOwnProperty"]) {
    assert.equal(vcsBrand(x), "", String(x));
  }
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
/** Дія `BAR_ACTIONS.<name>: async () => {…}` — текст виразу. */
function actSource(name) {
  const head = `\n  ${name}: async () => {`;
  const i = src.indexOf(head);
  assert.ok(i > 0, `BAR_ACTIONS.${name} (async () => {…}) немає`);
  const open = i + head.length - 1;
  return `async () => ${balanced(open)}`;
}

test("refreshGitlab питає /api/vcs-status за noVcs(), а loadTeamsMute лишається на noOutward()", () => {
  const body = fn("refreshGitlab");
  const guard = body.indexOf("\n  if (noVcs()) { glCache = null; return; }\n");
  const call = body.indexOf("await api(`/api/vcs-status?it=${encodeURIComponent(picked || '')}`)");
  assert.ok(guard > 0, "вихід без запиту за noVcs()");
  assert.ok(call > guard, "запит статусу — ПІСЛЯ гейта: без ролі мережі нема");
  assert.match(fn("loadTeamsMute"), /^\{[^]*?\n  if \(noOutward\(\)\) \{ teamsMute = null; return; \}\n  try \{ teamsMute = await api\('\/api\/teams-mute'\)/);
  assert.match(src, /const noVcs = \(\) => needsWelcome\(spacesResp\) \|\| !hasVcs\(spaceNow\(\)\);/);
  assert.match(src, /const noOutward = \(\) => spaceNow\(\)\?\.integrations === false \|\| needsWelcome\(spacesResp\);/,
    "Teams лишається на integrations");
});

test("refreshGitlab: vcs-busy лишає попередній стан, інакше крапка смуги фарбувалась би в помилку", () => {
  assert.match(fn("refreshGitlab"), /glCache = \(r\.code === 'vcs-busy' && glCache\) \? glCache : r; \}\n  catch \{ glCache = null; \}/);
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

test("стан смуги й палітри несе підпис репозиторію поіменно", () => {
  assert.match(src, /\n    glLabel: glCache\?\.label \|\| '',/);
  assert.match(src, /gl: st\.gl, glBrand: vcsBrand\(st\.glLabel\), iterLabel: st\.iterLabel,/);
  const names = /import \{([^}]*)\} from '\.\/spaces-model\.js'/.exec(src)?.[1] ?? "";
  for (const n of ["hasVcs", "isLegacyVcs", "vcsBrand", "vcsErrKey"]) {
    assert.match(names, new RegExp(`\\b${n}\\b`), `${n} не імпортовано з spaces-model.js`);
  }
});

/* ── виконання дій із заглушками: що побачить людина ─────────────────────── */

/**
 * Збирає дію з тексту `app.js`. Імена, яких дія торкається, беруться з `env` (`with`): забутий — ReferenceError,
 * тобто тест червоніє, а не мовчки бере глобальне. `glCache` — поле `env`, тож тест міняє його між викликами.
 */
function actFn(name, env) {
  // eslint-disable-next-line no-new-func
  return new Function("env", `with (env) { return (${actSource(name)}); }`)(env);
}

/** Середовище дії: усе, що вона кличе, — заглушки, що пишуть у `log`. */
function mkEnv(over = {}) {
  const log = { tell: [], toast: [], post: [], ask: [], refresh: 0, render: 0 };
  const env = {
    log,
    glCache: { configured: true, label: "GitHub", behind: 0, unpushed: 0 },
    picked: "it3",
    post: async (path, body) => { log.post.push([path, body]); return env.reply; },
    reply: {},
    tell: (m) => log.tell.push(m),
    toast: (m) => log.toast.push(m),
    askYesNo: async (msg, o) => { log.ask.push([msg, o]); return env.yes !== false; },
    yes: true,
    refreshGitlab: async () => { log.refresh += 1; },
    render: () => { log.render += 1; },
    itNum: (id) => String(id).replace(/\D/g, ""),
    t, vcsErrKey,
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

  const liga = { glCache: { configured: true, label: "GitLab" } };
  log = await run("glpush", { ok: true, synced: true, changed: true, pushed: true, sha: "abc123" }, liga);
  assert.deepEqual(log.toast, ["Надіслано на GitLab · комміт abc123"]);
  log = await run("glpush", { ok: false, error: "boom" }, liga);
  assert.ok(log.tell[0].startsWith("GitLab-синхронізація не вдалася"));
  log = await run("glpush", { ok: false, code: "vcs-offline" }, liga);
  assert.ok(log.tell[0].startsWith("GitLab не відповідає"));
  log = await run("glpush", { ok: true, synced: true, catchup: true }, { glCache: { configured: true } });
  assert.deepEqual(log.toast, ["Довезли незапушений комміт — тепер макет на GitLab."], "статус без підпису — GitLab");
});

test("glpush: помилка статусу в кеші — повідомлення, без запиту; запит упав — errFailed", async () => {
  let log = await run("glpush", {}, { glCache: { configured: true, error: "offline", code: "vcs-offline" } });
  assert.deepEqual(log.tell, [t("errFailed", "offline")]);
  assert.deepEqual(log.post, []);
  const env = mkEnv();
  env.post = async () => { throw new Error("net"); };
  await actFn("glpush", env)();
  assert.deepEqual(env.log.tell, [t("errFailed", "net")]);
  log = await run("glpush", {}, { glCache: null });
  assert.deepEqual(log.post, [], "без кешу — нічого");
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

  log = await run("glpull", { ok: true, unchanged: true, same_as: "it2" }, { glCache: { configured: true, label: "GitLab" } });
  assert.deepEqual(log.ask[0][0], "Підтягнути зміни з GitLab як нову ітерацію?\nПоточний макет не зміниться — зʼявиться нова ітерація для порівняння.");
  assert.deepEqual(log.toast, ["На GitLab те саме, що в it2 — нової ітерації не заводив"]);
});

test("glpull: «Ні» у питанні — запиту нема; запит упав — errFailed (catch лишився для транспорту)", async () => {
  let log = await run("glpull", {}, { yes: false });
  assert.deepEqual(log.post, []);
  const env = mkEnv();
  env.post = async () => { throw new Error("net down"); };
  await actFn("glpull", env)();
  assert.deepEqual(env.log.tell, [t("errFailed", "net down")]);
});

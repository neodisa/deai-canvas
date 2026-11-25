/**
 * Проводка просторів у `app/app.js`, яку юніти моделі не бачать (`app.js` не
 * імпортується в Node: DOM на верхньому рівні). Правила самі — у
 * `app/spaces-model.js` і тестуються імпортом (`tests/spaces-state.test.mjs`); тут —
 * що `app.js` ними КОРИСТУЄТЬСЯ там, де це несуче, і що не лишилось другого шляху
 * повз правило. Мінімум текстових перевірок, за взірцем `tests/tree-actions-wiring.test.mjs`.
 * Живу поведінку (клік → екран) покриває `tests/live/spaces.test.mjs` (Task 8).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  publishErr, publishReaction, remoteNoticeLines, remoteOpenUrl, remoteShareUrl, safeLocalUrl, spaceChanged,
} from "../app/spaces-model.js";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
const bar = readFileSync(new URL("../app/shell-bar.js", import.meta.url), "utf8");
const pal = readFileSync(new URL("../app/shell-palette.js", import.meta.url), "utf8");

/** Тіло функції за збалансованими дужками: від першого `) {` після заголовка. */
function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}

/* ── дії смуги ↔ розмітка ──────────────────────────────────────────────── */

test("кожна дія просторів з розмітки смуги й палітри має обробник у BAR_ACTIONS", () => {
  for (const act of ["space", "spacenew", "spaceedit"]) {
    assert.match(bar, new RegExp(`act: "${act}"`), `смуга не малює ${act}`);
    assert.match(src, new RegExp(`\\n  ${act}: `), `BAR_ACTIONS.${act} немає — кнопка нічого б не робила`);
  }
  for (const act of ["space", "spacenew"]) {
    assert.match(pal, new RegExp(`act: "${act}"`), `палітра не має ${act}`);
  }
});

test("`space`: не перемикає на той самий простір, помилка перемикання — тост-діалог, далі afterSpaceChange", () => {
  const i = src.indexOf("\n  space: async (val) => {");
  assert.ok(i > 0);
  const body = src.slice(i, src.indexOf("\n  spacenew:", i));
  assert.match(body, /val === spaceNow\(\)\?\.id\) return;/);
  assert.match(body, /post\('\/api\/space-switch', \{ id: val \}\)/);
  assert.match(body, /catch \(e\) \{ tellError\(t\('errTSpaceSwitch'\), e\.message\); return; \}/);
  assert.match(body, /await navigating\(\(\) => afterSpaceChange\(\)\);/);
});

/* ── вимикач інтеграцій: опитування НЕ запускаються ────────────────────── */

test("refreshGitlab і loadTeamsMute: першим рядком — вихід без запиту, коли інтеграцій нема", () => {
  // GitLab (синк із git) — на `noVcs` (роль `vcs`, 4a); коментар між гейтом і запитом дозволений.
  assert.match(fn("refreshGitlab"), /^\{[^]*?\n  if \(noVcs\(\)\) \{ glCache = null; dropGlState\(\); return; \}\n  const seq = \+\+glSeq;\n  const key = glKeyNow\(task\);\n  try \{\n    const r = await api\(`\/api\/vcs-status/);
  assert.match(fn("loadTeamsMute"), /^\{[^]*?\n  if \(noNotify\(\)\) \{ teamsMute = null; return; \}\n  try \{ teamsMute = await api\('\/api\/teams-mute'\)/);
  assert.match(src, /const noNotify = \(\) => needsWelcome\(spacesResp\) \|\| !hasNotify\(spaceNow\(\)\);/,
    "4c-3: Teams-тиша — на ролі `notify`; просторів нема зовсім — теж без опитувань");
});

test("список просторів: спершу задача відкритого запису, потім реєстр", () => {
  assert.match(src, /const spaceNow = \(\) => curTask\?\.space \?\? currentSpace\(spacesResp\);/);
});

/* ── канал коментарів: перемикача нема (0.27.0, поправка 10 плану Б2) ─────────────────── */

test("канал коментарів: «Огляд» — комбінований за наявності командного каналу, інакше локальний; рамка без `ch`", () => {
  assert.equal([...src.matchAll(/&ch=/g)].length, 0, "рамка просить `ch` — його вибір тепер на боці сервера (`host=1`)");
  assert.match(src, /channel: \(\) => \(noTeamComments\(\) \? 'local' : 'dual'\),/);
  assert.match(src, /audiences: \(\) => \(noTeamComments\(\) \? \[\] : \[/, "без командного каналу (роль `comments`) чипів адресата нема");
  assert.match(src, /id: 'local', label: t\('audChipLocal'\), icon: 'bot', color: LOCAL_PIN_COLOR, private: true/,
    "локальна аудиторія «Огляду» — приватна (поправка 20), колір — спільний із `DUAL_AUDIENCES_JS`");
});

test("перемикач каналу прибрано повністю: жодного `effMode`/`commentMode`/`setAudience`/`dc-audience`/`dc-comment-mode`", () => {
  for (const dead of [/\beffMode\b/, /\blet commentMode\b/, /\bsetAudience\b/, /dc-audience/, /dc-comment-mode/, /\bcmtch\b/, /\bBAR_ACTIONS\.aud\b/, /^  aud: /m, /effectiveCommentMode/]) {
    assert.doesNotMatch(src, dead, String(dead));
  }
});

/* ── скидання стану при зміні простору ─────────────────────────────────── */

test("resetSpaceState: усе, що належить простору, скидається В ОДНОМУ місці", () => {
  const body = fn("resetSpaceState");
  for (const piece of [
    "await resetPerTaskState();",
    "curTask = null; curTaskList = null; homeData = null; currentTaskId = null;",
    "taskSwitchGen += 1; homeSeq += 1;",
    "glCache = null; teamsMute = null;",
    "tasksErr = false; tasksErrKey = null;",
    "homeUi.q = ''; homeUi.tags.clear(); homeUi.designers.clear(); saveHomeUi();",
    "if (reload) await loadSpaces();",
  ]) assert.ok(body.includes(piece), `resetSpaceState не робить: ${piece}`);
  assert.match(src, /async function resetSpaceState\(\{ reload = true \} = \{\}\) \{/, "за замовчуванням реєстр перечитується");
  assert.ok(body.indexOf("await resetPerTaskState()") < body.indexOf("curTask = null"),
    "пер-задачний стан скидається ПЕРШИМ (він ще читає сервер нового простору)");
  assert.ok(body.indexOf("curTask = null") < body.indexOf("if (reload) await loadSpaces()"), "реєстр перечитується ПІСЛЯ скидання");
});

test("afterSpaceChange: забути → (екран «Задачі» лишається екраном) → render → статус GitLab нового простору", () => {
  const body = fn("afterSpaceChange");
  const order = ["await resetSpaceState();", "if (homeOpen) enterHome({ spaces: false });", "await render();", "await refreshGitlab();", "paintBar();"];
  let at = -1;
  for (const piece of order) {
    const i = body.indexOf(piece, at + 1);
    assert.ok(i > at, `afterSpaceChange: «${piece}» немає або стоїть не за порядком`);
    at = i;
  }
});

test("switchTask: простір відповіді порівнюється з відомим; змінився — скидається весь простір", () => {
  const body = fn("switchTask");
  assert.match(body, /const sw = await post\('\/api\/task-switch'/);
  assert.match(body, /if \(spaceChanged\(spaceNow\(\)\?\.id, sw\?\.space\)\) await resetSpaceState\(\);\s*else await resetPerTaskState\(\);/);
});

test("«Нова задача» (етап Д: картка в сітці): простір називається ЯВНО, зайняті id — з усіх просторів, запит і перехід — усередині відправки", () => {
  assert.doesNotMatch(src, /function newTaskDialog\(/, "діалог замінила картка в сітці");
  const open = fn("openNewTaskCard");
  assert.match(open, /formApi\('\/api\/tasks\?all=1'\)/);
  const body = fn("createTask");
  assert.match(body, /space: sp\.id/, "без `space` сервер пішов би в простір з інтеграціями");
  assert.match(body, /postForm\('\/api\/task-new'/);
  assert.match(body, /taskFormError\(vals, await taken, trashIds\)/, "перевірка id (з урахуванням кошика) ДО запиту");
  assert.match(body, /if \(spaceChanged\(sp\.id, made\.space\)\) await resetSpaceState\(\);\s*else await resetPerTaskState\(\);/);
  assert.match(body, /await leaveHome\(\);/);
  /* Перехід — УСЕРЕДИНІ відправки, після відповіді сервера: картку могли закрити, а задачу вже створено. */
  assert.ok(body.indexOf("postForm('/api/task-new'") < body.indexOf("await leaveHome();"), "перехід ПІСЛЯ відповіді сервера");
  assert.match(body, /\} catch \(e\) \{ toast\(t\('errFailed', e\.message\)\); \}\s*return undefined;/,
    "збій переходу — тост, а не «не вдалося створити» для задачі, що вже є");
  assert.match(fn("closeNewTaskCard"), /homeNode\(\)\?\.querySelector\('\[data-th="newtask"\]'\)\?\.focus/, "після закриття фокус — на картку «+»");
  assert.match(body, /ctl\.focus\(taskErrField\(key\)\)/, "поле помилки — aria-invalid");
});

test("діалог простору (лише «Назва й колір…»): запит і оновлення — усередині onSubmit (помилка лишається в діалозі), focusBack", () => {
  /* Новий простір створює майстер (`wizard.js`, етап 3b): його запити, перехід і «Особисте» стережуть `tests/wizard-wiring.test.mjs`
     й `tests/wizard-model.test.mjs`; діалог `new` у `app.js` більше нема. */
  assert.doesNotMatch(src, /function openSpaceNew\(/);
  const ed = fn("openSpaceEdit");
  assert.match(ed, /postForm\('\/api\/space-update', \{ id: cur\.id, name, color: vals\.color \}\)/);
  assert.match(ed, /applySpaceMeta\(cur\.id, saved\)/);
  assert.ok(ed.indexOf("postForm('/api/space-update'") < ed.indexOf("applySpaceMeta("), "оновлення вузлів — після відповіді сервера, усередині onSubmit");
  assert.doesNotMatch(ed, /afterSpaceChange|render\(\)/, "перейменування не перезавантажує макет");
  assert.match(ed, /focusBack: spaceDialogFocusBack,/);
  assert.match(src, /const spaceDialogFocusBack = \(\) => chipEl\(\) \?\? homeNode\(\)\?\.querySelector\('\[data-th="spacenew"\]'\);/);
});

test("applySpaceMeta: нова назва й колір — і в реєстрі, і в задачі, і в даних екрана «Задачі» (кожне окремо)", () => {
  const body = fn("applySpaceMeta");
  assert.match(body, /if \(spacesResp\?\.spaces\) spacesResp = \{ \.\.\.spacesResp, spaces: spacesResp\.spaces\.map\(patch\) \};/);
  assert.match(body, /if \(curTask\?\.space\) curTask = \{ \.\.\.curTask, space: patch\(curTask\.space\) \};/,
    "фішка бере простір із `curTask.space` — без цього рядка стара назва лишилась би в смузі");
  assert.match(body, /if \(homeData\?\.space\) homeData = \{ \.\.\.homeData, space: patch\(homeData\.space\) \};/,
    "заголовок екрана «Задачі» — із `homeData.space`");
  assert.match(body, /paintBar\(\);\s*if \(homeOpen\) paintHome\(\);/);
  assert.match(body, /const patch = \(x\) => \(x && x\.id === id \? \{ \.\.\.x, name, color \} : x\);/, "чужі простори не чіпаємо");
});

/* ── «задачі нема», привітання, висячий current ─────────────────────────── */

test("render: no-task — не помилка смуги; причина читання — через readErrKey; порожній сцені — blankStage", () => {
  const body = fn("render");
  const iNo = body.indexOf("e?.code === 'no-task'");
  assert.ok(iNo > 0, "render не розрізняє no-task");
  assert.ok(iNo < body.indexOf("tasksErr = true;"), "no-task перевіряється ДО встановлення помилки смуги");
  assert.match(body, /await showNoTask\(\); return;/);
  assert.match(body, /tasksErrKey = e\?\.key \|\| readErrKey\(e\?\.code\) \|\| null;/);
  assert.match(body, /if \(!curTask\) \{ await loadSpaces\(\); blankStage\(\); paintBar\(\); return; \}/);
});

test("render: простір відповіді змінився проти показаної задачі (агент, інша вкладка) — resetSpaceState ДО того, як стан задачі читається", () => {
  const body = fn("render");
  const guard = "if (curTask && spaceChanged(curTask.space?.id, task.space?.id)) {";
  const iGuard = body.indexOf(guard);
  assert.ok(iGuard > 0, "render не порівнює простір відповіді з показаною задачею");
  assert.match(body.slice(iGuard, iGuard + 220), /await resetSpaceState\(\);\s*if \(homeOpen\) enterHome\(\{ spaces: false \}\);/);
  assert.ok(iGuard > body.indexOf("taskList = await api('/api/tasks');"), "порівнюємо з УЖЕ завантаженою відповіддю");
  assert.ok(iGuard < body.indexOf("curTask = task;"), "скидання — ДО присвоєння нової задачі (скидання саме обнуляє curTask)");
  /* Умова «була попередня задача»: на старті й після showNoTask `curTask === null`, і скидати там нічого. */
  assert.match(guard, /^if \(curTask &&/);
});

test("render: пакет тюнера нової задачі читається, коли його не читали (`tuneRev` невизначена) — запис без base_rev затер би .dc-tuner.json", () => {
  const body = fn("render");
  assert.match(body, /if \(tuneRev === undefined\) await loadTune\(\);/);
  assert.ok(body.indexOf("curTask = task;") < body.indexOf("if (tuneRev === undefined) await loadTune();"));
  assert.ok(body.indexOf("if (tuneRev === undefined) await loadTune();") < body.indexOf("} catch (e) {"), "усередині try: збій читання не стає помилкою смуги");
});

test("resetPerTaskState: lastCheck теж пер-задачний (id ітерації є в кожній задачі)", () => {
  const body = fn("resetPerTaskState");
  assert.match(body, /lastCheck = null;/);
  for (const piece of ["tuneRev = undefined;", "tuneState = emptyTune();", "await loadTune();"]) assert.ok(body.includes(piece), piece);
});

test("showNoTask: лікує висячий current ЯВНИМ результатом loadSpaces, скидає простір і перероблює render; інакше — екран «Задачі»", () => {
  const body = fn("showNoTask");
  assert.match(body, /const healed = await loadSpaces\(\{ heal: true \}\);/);
  assert.match(body, /if \(healed\) \{\s*await resetSpaceState\(\{ reload: false \}\);\s*if \(homeOpen\) enterHome\(\{ spaces: false \}\);\s*return render\(\);\s*\}/,
    "вилікувано: пер-задачний стан (тюнер!) скинуто, реєстр не перечитується вдруге");
  assert.match(body, /if \(curTask\) await resetPerTaskState\(\);\s*curTask = null;/, "задачу забуваємо разом із її станом, до обнулення");
  assert.match(body, /blankStage\(\);\s*enterHome\(\{ spaces: false \}\);/);
  assert.doesNotMatch(src, /spacesHealed/, "бокового каналу (прапорець модуля) нема");
  const ls = fn("loadSpaces");
  assert.match(src, /async function loadSpaces\(\{ heal = false \} = \{\}\) \{/);
  assert.match(ls, /const to = heal \? healTarget\(r\) : null;/);
  assert.match(ls, /post\('\/api\/space-switch', \{ id: to \}\)/);
  assert.match(ls, /healed = healTarget\(r\) === null;/, "«вилікувано» — лише коли реєстр справді більше не висить");
  assert.match(ls, /if \(seq === spacesSeq\) spacesResp = r;\s*return healed;/, "стара відповідь не перезаписує нову; результат — явний");
});

test("лікування висячого current — лише з render()/loadHome(): решта викликів loadSpaces не перемикає сервер", () => {
  /* Без коментарів: у докстрінгах `loadSpaces({heal})` згадується, а викликом не є. */
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const calls = [...code.matchAll(/(?<!function )loadSpaces\(([^)]*)\)/g)].map((m) => m[1]);
  assert.equal(calls.filter((a) => a === "{ heal: true }").length, 2, "рівно два лікарі: showNoTask (з render) і loadHome");
  assert.deepEqual(calls.filter((a) => a !== "{ heal: true }" && a !== ""), [], "інші виклики — без аргументів");
  assert.ok(calls.filter((a) => a === "").length >= 4, "дропдаун, палітра, render без задачі, resetSpaceState — без лікування");
  assert.match(fn("showNoTask"), /loadSpaces\(\{ heal: true \}\)/);
  assert.match(fn("loadHome"), /loadSpaces\(\{ heal: true \}\)/);
  assert.match(src, /if \(openDd === 'space'\) loadSpaces\(\)\.then\(/, "відкриття дропдауна — без лікування");
  assert.match(fn("openPalette"), /loadSpaces\(\)\.then\(/, "відкриття палітри — без лікування");
});

test("екран «Задачі»: привітання за spacesResp, простори — першими в loadHome, помилка простору — смугою", () => {
  /* Привітання — першим і за `spacesResp` на ОБОХ сторінках оверлею; далі «Підключення» чи список задач. */
  assert.match(fn("paintHome"), /needsWelcome\(spacesResp\) \? welcomeHTML\(welcomeView\(\)\)\s*: homePage === 'conn' \? connPageHTML\(connView\(\)\) : homeHTML\(homeView\(\), homeData\)/);
  const lh = fn("loadHome");
  const iSpaces = lh.indexOf("await loadSpaces({ heal: true })");
  assert.ok(iSpaces >= 0, "loadHome не питає простори взагалі");
  assert.ok(iSpaces < lh.indexOf("await api(`/api/tasks-overview"),
    "простори (лікують current) мусять бути ПЕРЕД оглядом задач");
  assert.match(lh, /if \(needsWelcome\(spacesResp\)\) \{[\s\S]*?paintHome\(\);\s*return;/);
  assert.match(lh, /const key = readErrKey\(e\?\.code\);\s*if \(key\) \{ tasksErr = true; tasksErrKey = key; paintBar\(\); \}/);
  assert.match(fn("enterHome"), /homeData = \{ loading: true, space: spaceNow\(\) \}/);
});

test("loadHome: перелік просторів не перепитується, коли його щойно перечитали (`spaces: false`); лікування скидає простір", () => {
  const lh = fn("loadHome");
  assert.match(src, /async function loadHome\(refresh = false, \{ spaces = true \} = \{\}\) \{/);
  assert.match(lh, /if \(spaces\) \{\s*const healed = await loadSpaces\(\{ heal: true \}\);\s*if \(seq !== homeSeq \|\| !homeOpen\) return;/);
  assert.match(lh, /if \(healed\) \{ await resetSpaceState\(\{ reload: false \}\); if \(homeOpen\) enterHome\(\{ spaces: false \}\); return; \}/);
  assert.match(src, /function enterHome\(\{ spaces = true, page \} = \{\}\) \{/);
  assert.match(fn("enterHome"), /loadHome\(false, \{ spaces \}\);/);
  assert.match(src, /home: async \(\) => \{ if \(homeOpen && homePage === 'wiz'\) \{ await wiz\.requestExit\(\); return; \} if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return; await navigating\(\(\) => enterHome\(\{ page: 'tasks' \}\)\); \},/, "вхід логотипом перепитує простори (там і лікування) і веде саме на «Задачі»; брудна панель «Підключення» спершу питає, майстер — через wiz.requestExit");
});

test("loadHome: успішний огляд знімає смугу «простір не читається» (але не чужу причину) і перемальовує смугу", () => {
  const lh = fn("loadHome");
  const guard = "if (tasksErr && isReadErrKey(tasksErrKey)) { tasksErr = false; tasksErrKey = null; paintBar(); }";
  assert.ok(lh.includes(guard), "успішний loadHome не чистить смугу");
  assert.ok(lh.indexOf("homeData = r;") < lh.indexOf(guard), "чистимо ПІСЛЯ успіху огляду");
  assert.ok(lh.indexOf(guard) < lh.lastIndexOf("paintHome();"), "і до фінальної перемальовки екрана");
  /* Гілка успіху — поза catch: у catch (збій) смугу, навпаки, виставляють. */
  assert.ok(lh.indexOf(guard) > lh.indexOf("} catch (e) {"), "перевірка стоїть ПІСЛЯ try/catch, тобто лише на успіху");
});

test("екран «Задачі»: повернення до вікна (focus, visibilitychange) перечитує його — простір, який завів агент, зʼявляється", () => {
  const body = fn("refreshHomeOnReturn");
  assert.match(body, /shouldRefreshHome\(\{ open: homeOpen, visible: document\.visibilityState === 'visible', last: homeRefreshedAt, now, forced: homeForced \}\)/);
  assert.match(body, /homeRefreshedAt = now;\s*(?:\/\*[\s\S]*?\*\/\s*)?homePage === 'conn' \? loadConn\(\) : loadHome\(\);/);
  assert.match(src, /window\.addEventListener\('focus', refreshHomeOnReturn\);/);
  assert.match(src, /document\.addEventListener\('visibilitychange', refreshHomeOnReturn\);/);
});

test("«Спробувати ще» (`loadHome(true)`): поки летить, перечитування з фокуса його не перебиває (`homeForced`)", () => {
  const body = fn("retryHome");
  assert.match(body, /homeForced = true;\s*try \{ await loadHome\(true\); \} finally \{ homeForced = false; \}/,
    "прапорець знімається в finally: збій чи перебиття не лишають перечитування вимкненим назавжди");
  assert.match(src, /case 'retry': retryHome\(\); break;/, "кнопка повтору йде через retryHome, а не голим loadHome(true)");
  /* Без коментарів: у докстрінгах `loadHome(true)` згадується, а викликом не є. */
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  assert.equal([...code.matchAll(/loadHome\(true\)/g)].length, 1, "примусове перечитування — лише через retryHome");
  assert.match(src, /let homeForced = false;/);
});

test("діалоги: запити space-new / space-update / task-new і перелік id йдуть через formApi/postForm зі стелею часу (завислий сервер не тримає канвас під підкладкою)", () => {
  assert.match(src, /import \{\s*FORM_POST_TIMEOUT_MS,/, "стеля — з моделі, одне число на весь застосунок");
  const fa = fn("formApi");
  assert.match(fa, /const ctl = new AbortController\(\);\s*const timer = setTimeout\(\(\) => ctl\.abort\(\), FORM_POST_TIMEOUT_MS\);/);
  assert.match(fa, /api\(path, \{ \.\.\.opts, signal: ctl\.signal \}\)/, "сигнал доходить до fetch");
  assert.match(fa, /e\?\.name === 'AbortError' \? Object\.assign\(new Error\('timeout'\), \{ code: 'timeout' \}\) : e/,
    "обрив стає `code: 'timeout'` (spaceErrKey/taskErrKey → formTimeout), решта помилок — як були");
  assert.match(fa, /\.finally\(\(\) => clearTimeout\(timer\)\)/, "таймер знімається, інакше він обрізав би вже завершений запит");
  assert.match(src, /const postForm = \(path, body\) => formApi\(path, \{\s*method: 'POST'/);
  for (const [name, url] of [["openSpaceEdit", "space-update"], ["createTask", "task-new"]]) {
    const b = fn(name);
    assert.match(b, new RegExp(`postForm\\('/api/${url}'`), `${name}: запит без стелі`);
    assert.doesNotMatch(b, new RegExp(`[^m]post\\('/api/${url}'`), `${name}: лишився голий post`);
  }
  assert.match(fn("openNewTaskCard"), /const taken = formApi\('\/api\/tasks\?all=1'\)/, "перелік id теж зі стелею: `await taken` у відправці не висить");
});

test("екран «Задачі»: вкладка — за effectiveTab (збережена `team` не переписується), кнопки задачі й простору", () => {
  assert.match(src, /if \(effectiveTab\(homeUi, homeData\) === v\) break;/);
  assert.doesNotMatch(src, /if \(homeUi\.tab === v\) break;/, "стара перевірка вернулась");
  assert.match(src, /case 'newtask': openNewTaskCard\(\); break;/);
  assert.match(src, /case 'spacenew': openWizard\(\); break;/);
});

test("keepFocus: порядковий номер серед збігів — подвійна кнопка «Нова задача» не краде фокус", () => {
  const body = fn("keepFocus");
  assert.match(body, /const nth = key \? \[\.\.\.root\.querySelectorAll\(key\)\]\.indexOf\(a\) : -1;/);
  assert.match(body, /const n = all\[nth\] \?\? all\[0\];/);
});

/* ── палітра, смуга, клавіатура ────────────────────────────────────────── */

test("палітра ⌘K: простори — масив лише коли шар увімкнено; вимикач передається", () => {
  const body = fn("paletteState");
  assert.match(body, /spaces: spacesResp && !spacesResp\.off \? spacesResp\.spaces : undefined,/);
  assert.match(body, /spaceId: st\.space\?\.id \?\? null,/);
  /* Task 8 (модулі 2а): до вимикача додано `capabilities` — на них тепер стоїть публікація в ⌘K
     (`hasPublish`); прапорця `integrations` сервер більше не шле (4d-4c). */
  assert.match(body, /space: st\.space \? \{ id: st\.space\.id, capabilities: st\.space\.capabilities, compat: st\.space\.compat, tools: st\.space\.tools \} : null,/);
  assert.match(fn("openPalette"), /loadSpaces\(\)\.then\(\(\) => \{ if \(paletteOverlay === 'pal'\) repaintPaletteList\(\); \}\);/);
});

test("смуга: стан несе space/spaces; дропдаун просторів освіжається при відкритті", () => {
  const body = fn("barState");
  assert.match(body, /space: spaceNow\(\),/);
  assert.match(body, /spaces: spacesResp && !spacesResp\.off \? spacesResp\.spaces : \[\],/);
  assert.match(src, /if \(openDd === 'space'\) loadSpaces\(\)\.then\(\(\) => \{ if \(openDd === 'space'\) paintBar\(\); \}\);/);
});

test("клавіатура дропдауна просторів: roving focus через rovingIndex, Esc повертає фокус на фішку", () => {
  assert.match(src, /bar\.addEventListener\('keydown', \(ev\) => \{[\s\S]*?closest\?\.\('\.dd--spaces'\)[\s\S]*?rovingIndex\(rows\.indexOf\(document\.activeElement\), rows\.length, ev\.key\)/);
  assert.match(src, /if \(to === null\) return;\s*ev\.preventDefault\(\);/, "чужу клавішу не гасимо");
  assert.match(src, /const wasSpaces = openDd === 'space';[\s\S]*?if \(wasSpaces\) focusChip\(\);/);
  const pb = fn("paintBar");
  assert.match(pb, /spRow >= 0 \? spRow : \(spFresh \? Math\.max\(cur, 0\) : -1\)/, "перемальовка зберігає рядок фокуса, щойно відкрите — поточний");
  assert.match(pb, /chipHadFocus/);
});

test("api(): помилка несе `code` і `status` (сервер просторів завжди шле `code` разом з `error`)", () => {
  /* `statusText` і `body` — додатково (Task 8 follow-up): причина code-less 400 лежить там, а не в `code`. */
  assert.match(fn("api"), /Object\.assign\(new Error\(msg\.slice\(0, 200\) \|\| String\(res\.status\)\),\s+\{ status: res\.status, code, statusText: res\.statusText, body: txt\.slice\(0, 1000\) \}\)/);
});

test("blankStage: чистить сцену, полотно й панель — під смугою помилки не лишається чужий макет", () => {
  const body = fn("blankStage");
  for (const piece of ["ovc.leave();", "canvasEl.hidden = true; stage.hidden = false;", "frame.src = 'about:blank'",
    "picked = null; pickedPage = null; pickedState = null;", "panelPages = [];", "renderPanel();"]) {
    assert.ok(body.includes(piece), `blankStage не робить: ${piece}`);
  }
});

/* ── ⌘K поверх зайнятої форми, фокус після дропдауна ───────────────────── */

test("openPalette: під відкритим діалогом (.cv-ask-scrim) не відкривається — ПЕРШИМ рядком, до зміни стану палітри", () => {
  const body = fn("openPalette");
  const guard = "if (askUp()) return;";   // етап В: `askUp()` = модальна картка АБО поповер
  assert.ok(body.includes(guard), "⌘K відкрив би палітру поверх форми, що чекає відповіді сервера");
  assert.ok(body.indexOf(guard) < body.indexOf("paletteOverlay = 'pal'"), "перевірка ДО будь-якої зміни стану");
  assert.ok(body.indexOf(guard) < body.indexOf("openDd = null"), "і до закриття дропдауна");
  /* ⌘K іде через openPalette: другого входу повз перевірку нема (кнопки палітри в смузі вже нема). */
  assert.match(src, /if \(meta && ev\.key\.toLowerCase\(\) === 'k'\) \{\s*ev\.preventDefault\(\);\s*openPalette\(\);/);
});

test("дропдаун просторів: після Enter/кліку на рядку фокус вертається на фішку ДО виклику дії (діалог запамʼятає її відкривачем)", () => {
  const i = src.indexOf("const fromSpaces = openDd === 'space' && !!el.closest('.dd--spaces');");
  assert.ok(i > 0, "делегація смуги не знає, що клік був у дропдауні просторів");
  const tail = src.slice(i, i + 1400);
  assert.ok(tail.indexOf("openDd = null;") < tail.indexOf("if (fromSpaces) focusChip();"), "фішку фокусуємо ПІСЛЯ закриття дропдауна");
  assert.ok(tail.indexOf("paintBar();") < tail.indexOf("if (fromSpaces) focusChip();"), "і після перемальовки смуги (вузол фішки новий)");
  assert.ok(tail.indexOf("if (fromSpaces) focusChip();") < tail.indexOf("BAR_ACTIONS[act]?.("), "і ДО дії: діалог бере відкривача з activeElement");
});

/* ── публікація за `capabilities.publish` (модулі 2а, Task 8) ─────────────────
   Правила — у `spaces-model.js` (`tests/spaces-publish.test.mjs`); тут — що `app.js` ними
   КОРИСТУЄТЬСЯ і що не лишилось другого шляху повз правило. `noOutward` НЕ змінено: на ньому
   стоять опитування GitLab/Teams; публікація пішла на `hasPublish`, а командний канал
   коментарів (2b-2) — на `noTeamComments`/`hasTeamComments` (`capabilities.comments`). */

/** Тіло дії `BAR_ACTIONS`: від `\n  <name>:` до наступної дії рівня 2 пробілів (або кінця мапи). */
function barAct(name) {
  const i = src.indexOf(`\n  ${name}: `);
  assert.ok(i > 0, `BAR_ACTIONS.${name} немає`);
  const m = /\n  [a-zA-Z]+: |\n};/.exec(src.slice(i + 5));
  return src.slice(i, i + 5 + (m ? m.index : 4000));
}

test("смуга: `published` — publish_url АБО publish_local, ціль превʼю і пароль — через модель", () => {
  const body = fn("barState");
  assert.match(body, /published: isPublished\(curTask\),/);
  assert.doesNotMatch(body, /published: !!\(curTask && curTask\.publish_url\)/, "старий шлях лишився");
  assert.match(body, /\.\.\.pwView\(curTask, spaceNow\(\)\),/, "пароль і попередження про гейт — повз правило");
  assert.doesNotMatch(body, /curTask\?\.preview_password/, "сирий пароль ЛІГА в смузі повз `pwView`");
  assert.doesNotMatch(body, /preview_gate\?\.state === 'stale'/, "pwStale повз `pwView`");
  assert.match(body, /pwError: pwUnreadable\(curTask, spaceNow\(\)\),/, "помилка секретів доходить до смуги через модель");
  assert.match(body, /pubLocal: /);
  assert.match(body, /pubWhen: /);
  assert.match(body, /previewTarget\(curTask, spaceNow\(\)\)/);
});

test("публікація: відповідь модуля (`local`) — плашка «Опубліковано локально» з «Відкрити», а не «деплой не вдався»", () => {
  const body = barAct("publish");
  assert.match(body, /if \(view\.kind === 'legacy'\) \{ render\(\); return; \}/, "шлях ЛІГА змінено: лише `render()`, без плашки");
  assert.doesNotMatch(body, /isLegacyPublish\(spaceNow\(\)\)/, "ЛІГА чи модуль — за простором ВИКЛИКУ (`sp0`), а не поточним: людина могла перейти");
  assert.match(body, /const local = safeLocalUrl\(r\.local\?\.url, location\.origin\);/, "адресу з відповіді звіряємо з оригіном канваса");
  assert.match(body, /if \(view\.kind === 'local'\) \{/);
  assert.match(body, /notice\('publish-local', t\(view\.key\)/, "текст плашки — з рішення моделі (`publishReaction`: `publishLocalDone`)");
  assert.match(body, /act: 'open'/);
  assert.match(body, /window\.open\(local, '_blank', 'noopener'\)/, "без noopener відкрита сторінка бачить `window.opener`");
  /* `publishDeployFailed` — лише для відповіді без `url` і без `local` (ЛІГА без деплою). */
  assert.ok(body.indexOf("view.kind === 'local'") < body.indexOf("publishDeployFailed"),
    "гілка `local` мусить стояти ДО «деплой не вдався» (інакше успішна публікація модулем читається як невдалий деплой)");
  assert.match(body, /const m = publishErr\(e\);\n\s+tell\(t\(m\.key, \.\.\.\(m\.reasonKey \? \[t\(m\.reasonKey\)\] : m\.args\)\)\);/, "відмова повз `publishErr`");
  assert.doesNotMatch(body, /catch \(e\) \{ tell\(t\('errFailed', e\.message\)\); \}/, "стара загальна відмова лишилась");
});

test("публікація: `comments_unavailable` з відповіді — рядок у вікні попереджень (код — через модель, текст — зі словника)", () => {
  const body = barAct("publish");
  const warn = /const warn = \[([^\]]*)\]\.filter\(Boolean\);/.exec(body);
  assert.ok(warn, "список попереджень `warn` зник");
  assert.match(body, /const cmtCode = commentsUnavailableCode\(r\);/, "код — лише через модель (безпечні символи)");
  assert.match(warn[1], /cmtCode \? t\('publishCommentsUnavailable', cmtCode\) : null/, "рядка про коментарі немає у `warn`");
  assert.match(warn[1], /r\.code_stale/, "попередження про код не зникло");
  assert.match(body, /if \(warn\.length\) tell\(warn\.join\('\\n\\n'\)\);/, "усі попередження — одним вікном");
  assert.match(src, /import \{[^}]*\bcommentsUnavailableCode\b[^}]*\} from '\.\/spaces-model\.js';/);
});

test("«Відкрити превью» і «Скопіювати посилання»: ціль — з моделі, локальне посилання без пароля", () => {
  const open = barAct("openpreview");
  assert.match(open, /previewTarget\(curTask, spaceNow\(\)\)/);
  assert.match(open, /window\.open\(/);
  assert.doesNotMatch(open, /curTask\?\.publish_url/, "відкриття повз `previewTarget`");
  const copy = barAct("copylink");
  assert.match(copy, /previewTarget\(curTask, spaceNow\(\)\)/);
  assert.match(copy, /copyUrl\(target, \{/);
  assert.match(copy, /origin: location\.origin/);
  assert.doesNotMatch(copy, /#k=/, "фрагмент із паролем збирається лише в моделі (`copyUrl`)");
  assert.match(copy, /if \(copyLinkRefused\(curTask, spaceNow\(\), target\)\) \{ tell\(t\('pwUnreadable'\)\); return; \}/, "нечитабельні секрети — помилка, а не посилання з порожнім ключем");
  assert.ok(copy.indexOf("copyLinkRefused(") < copy.indexOf("copyUrl(target"), "відмова — ДО складання посилання");
});

test("палітра й смуга: публікація — на hasPublish, GitLab — на hasVcs", () => {
  assert.match(pal, /import \{ figmaOff, hasPublish, hasVcs \} from "\.\/spaces-model\.js";/);
  assert.match(pal, /const noVcs = !hasVcs\(s\.space\);/, "синк із git — на ролі `vcs`");
  assert.match(pal, /if \(hasPublish\(s\.space\)\) \{\n    out\.push\(\{\n      id: "publish"/);
  assert.match(pal, /if \(!noVcs\) \{\n    \/\/ Той самий трьохгілковий розгляд/);
  assert.doesNotMatch(pal, /hasTeamComments|aud-project|aud-local/, "палітра більше не знає про командний канал (перемикач прибрано)");
  const model = readFileSync(new URL("../app/bar-model.js", import.meta.url), "utf8");
  assert.match(model, /hasPublish\(s\.space\)/);
  assert.match(model, /isLegacyPublish\(s\.space\)/);
  assert.doesNotMatch(model, /const OUTWARD = /, "спільний набір «назовні» мав розщепитись на gl і publish");
});

test("командний канал у app.js — `noTeamComments` на hasTeamComments; `noOutward` його не питає", () => {
  assert.match(src, /const noTeamComments = \(\) => needsWelcome\(spacesResp\) \|\| !hasTeamComments\(spaceNow\(\)\);/);
  assert.match(src, /hasNotify, hasTeamComments, healTarget,/, "імпорт із spaces-model.js (4c-3: додався hasNotify)");
  // GitLab на `noVcs`, Teams-тиша на `noNotify` (4c-3), а канал `project` на `noOutward`-подібне більше не спирається
  assert.doesNotMatch(src, /noOutward\(\)[^;\n]*(?:'project'|audiences)|(?:'project'|audiences)[^;\n]*noOutward\(\)/);
});

test("`noNotify` у app.js — на hasNotify (роль `notify`); `noOutward` зник, публікація його не питала", () => {
  assert.match(src, /const noNotify = \(\) => needsWelcome\(spacesResp\) \|\| !hasNotify\(spaceNow\(\)\);/);
  assert.match(src, /hasNotify, hasTeamComments, healTarget,/, "імпорт із spaces-model.js");
  assert.doesNotMatch(src, /\bnoOutward\b\(/, "4c-3: тиша Teams більше не на `integrations` — виклику noOutward() не лишилось");
  assert.doesNotMatch(src, /hasPublish\(spaceNow\(\)\)[^;]*noNotify|noNotify\(\)[^;]*hasPublish/);
  const model = readFileSync(new URL("../app/bar-model.js", import.meta.url), "utf8");
  assert.match(model, /\.\.\.\(hasNotify\(s\.space\) \? \[teamsItem\(s\.teams\)\] : \[\]\),/, "пункт Teams у смузі — за роллю, не за noInteg");
  assert.doesNotMatch(model, /noInteg/);
});

test("дропдаун публікації: підпис «локально» й застереження про ЛІГА-гейт — за моделлю", () => {
  assert.match(bar, /const subText = sub\.subKey \? t\(sub\.subKey, \.\.\.\(sub\.subArgs \|\| \[\]\)\) : "";\n\s+return ddItem\(\{ act: sub\.id, icon, title: t\(sub\.labelKey\), why, sub: subText \}\);/);
  assert.match(bar, /c\.legacy \? `<div class="dd-note">\$\{t\("pubGateTruth"\)\}<\/div>` : ""/);
});

test("плашка «Опубліковано локально» гаситься разом із задачею; відмова несе statusText і тіло", () => {
  /* Стійка плашка без таймера не сміє пережити свою задачу: `resetPerTaskState` кличуть і перемикання задачі, і
     простору (`resetSpaceState`), і створення задачі. */
  assert.match(fn("resetPerTaskState"), /^\{[^]*?dropNotice\('publish-local'\);/);
  /* Причина code-less 400 лежить у рядку статусу й тілі, а `message` розмітку ріже по 200 знаків — `api()` їх віддає. */
  assert.match(fn("api"), /statusText: res\.statusText, body: txt\.slice\(0, 1000\)/);
});

/* ── публікація на свій Vercel (2b-1, Task 3): проводка плашки, посилань і застережень ──────────
   Правила (`safeRemoteUrl`, `remoteShareUrl`, `remoteNoticeLines`, `isRemotePublish`, `previewTarget`/`copyUrl`)
   тестує `tests/spaces-publish.test.mjs`; тут — що `app.js` ними користується і що не лишилось другого шляху повз них. */

/** Гілка модульної відповіді з `url` у дії «Опублікувати»: від `if (view.kind === 'remote') {` до гілки `local`. */
const remoteBranch = () => {
  const body = barAct("publish");
  const from = body.indexOf("if (view.kind === 'remote') {");
  assert.ok(from > 0, "гілки `if (view.kind === 'remote') {` нема");
  return body.slice(from, body.indexOf("if (view.kind === 'local')", from));
};

test("публікація: відповідь з `url` у просторі модуля — плашка (текст із моделі); ЛІГА — лише render()", () => {
  const body = barAct("publish");
  const br = remoteBranch();
  assert.match(body, /const view = publishReaction\(r, sp0, sameTask\(\)\);/, "рішення — з простору ВИКЛИКУ (`sp0`) і чи людина досі на задачі");
  assert.match(body, /if \(view\.kind === 'legacy'\) \{ render\(\); return; \}/, "ЛІГА-відповідь мусить лишитись `render()` без плашки");
  /* оновлена задача (`publish_share_url`) — ДО плашки; кнопки беруть посилання від неї */
  assert.match(br, /try \{ await render\(\); \} catch \(e\) \{/, "збій перемальовки ПІСЛЯ вдалої публікації не робить із неї «Не вдалося»");
  assert.ok(br.indexOf("await render()") < br.indexOf("notice('publish-remote'"), "плашка раніше за оновлення задачі");
  assert.match(br, /notice\('publish-remote', t\(view\.key\),/, "текст плашки — з рішення моделі (Vercel чи загальний)");
  assert.match(br, /remoteNoticeLines\(r\)/, "другий рядок плашки (`warnings`/підказка) — через модель");
});

test("гонка з перемиканням задачі: простір і задача захоплюються ДО запиту; не на тій задачі — тост, а нова задача не чіпається", () => {
  /* Без коментарів: у них самих трапляється «`render()`» і «`notice`» — порядок міряємо за КОДОМ. */
  const body = barAct("publish").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const post = body.indexOf("await post('/api/publish'");
  assert.ok(post > 0);
  for (const decl of ["const t0 = currentTaskId;", "const sp0 = spaceNow();", "const label0 = "]) {
    const at = body.indexOf(decl);
    assert.ok(at > 0 && at < post, `${decl} мусить стояти ДО запиту (Vercel-публікація триває хвилини)`);
  }
  assert.match(body, /const sameTask = \(\) => currentTaskId === t0 && !spaceChanged\(sp0\?\.id, spaceNow\(\)\?\.id\);/);
  /* тост — одразу після рішення, до будь-якого render()/notice() */
  const toastAt = body.indexOf("if (view.show === 'toast') { toast(t(view.key, label0)); return; }");
  assert.ok(toastAt > post, "тосту для чужої задачі нема");
  assert.ok(toastAt < body.indexOf("render()", post), "`render()` нової задачі не мусить виконуватись на тості");
  assert.ok(toastAt < body.indexOf("notice('publish-"), "плашка мусить стояти ПІСЛЯ перевірки задачі");
  /* після `await render()` людина могла встигнути перейти — перевіряємо ще раз */
  const br = remoteBranch();
  assert.match(br, /const late = publishReaction\(r, sp0, sameTask\(\)\);\s*if \(late\.show === 'toast'\) \{ toast\(t\(late\.key, label0\)\); return; \}/);
  assert.ok(br.indexOf("late.show") < br.indexOf("notice('publish-remote'"));
});

/* Дія `publish` з `app.js`, ЗІБРАНА З ДЖЕРЕЛА й запущена з підставними залежностями (DOM нема): поведінка, а не лише текст. Правила
   (`publishReaction`, `remoteShareUrl`…) — справжні, з моделі; решта (`post`, `render`, `notice`…) — підставні й записують виклики. */
function publishAction(env) {
  const body = barAct("publish");
  const expr = body.slice(body.indexOf("async (val, el)"), body.lastIndexOf("}") + 1);
  const deps = {
    t: (key) => key, tell: () => {}, toast: () => {}, notice: () => {}, copyLinkText: () => {}, post: async () => ({}),
    render: async () => {}, window: { open: () => {} }, location: { origin: "http://localhost:8765" },
    currentTaskId: "t1", curTask: { id: "t1" }, spaceNow: () => ({ id: "v", capabilities: { publish: "vercel-publish" } }),
    publishErr, publishReaction, remoteNoticeLines, remoteOpenUrl, remoteShareUrl, safeLocalUrl, spaceChanged, ...env,
  };
  const names = Object.keys(deps);
  return new Function(...names, `return (${expr});`)(...names.map((n) => deps[n]));
}
const publishButton = () => {
  const lbl = { textContent: "Опублікувати" };
  return { lbl, el: { disabled: false, querySelector: (sel) => (sel === ".lbl-pub" ? lbl : null) } };
};

test("публікація: кнопка оживає на ВСІХ шляхах (`finally`) — і коли `render()` чи `notice()` кидають у гілці Vercel", async () => {
  const ok = { ok: true, url: "https://pv-12345678.vercel.app", verified: true, warnings: [] };
  const flipSpace = () => { let n = 0; return () => (n++ === 0 ? { id: "v", capabilities: { publish: "vercel-publish" } } : { id: "other", capabilities: { publish: "vercel-publish" } }); };
  const scenarios = {
    "render() кидає синхронно": { post: async () => ok, render: () => { throw new Error("render boom"); } },
    "render() відхиляє проміс": { post: async () => ok, render: async () => { throw new Error("render boom"); } },
    "notice() кидає": { post: async () => ok, notice: () => { throw new Error("notice boom"); } },
    "успіх Vercel (плашка)": { post: async () => ok },
    "людина перейшла на іншу задачу (тост, ранній return)": { post: async () => ok, spaceNow: flipSpace() },
    "публікація ЛІГА (`render()` і return)": { post: async () => ({ ok: true, url: "https://pv-1.example.app" }),
      spaceNow: () => ({ id: "liga", capabilities: { publish: "vercel-publish" }, compat: { publish: "design-canvas" } }) },
    "локальна публікація (плашка й return)": { post: async () => ({ ok: true, local: { path: "/x", url: "/published/p/t/" } }),
      spaceNow: () => ({ id: "p", capabilities: { publish: "static-publish" } }) },
    "відмова сервера (catch)": { post: async () => { throw Object.assign(new Error("boom"), { code: "module-error" }); } },
  };
  for (const [name, env] of Object.entries(scenarios)) {
    const { el, lbl } = publishButton();
    const calls = [];
    const act = publishAction({ tell: (m) => calls.push(["tell", m]), ...env });
    try { await act("", el); } catch (e) { assert.fail(`${name}: дія не мусить кидати назовні — ${e.message}`); }
    assert.equal(el.disabled, false, `${name}: кнопка лишилась вимкненою`);
    assert.equal(lbl.textContent, "Опублікувати", `${name}: підпис лишився «публікую…»`);
  }
});

test("публікація: поки запит іде, кнопка вимкнена й підписана «publishBusy» (контроль — без нього «оживає» ні про що)", async () => {
  const { el, lbl } = publishButton();
  let seen = null;
  const act = publishAction({ post: async () => { seen = { disabled: el.disabled, text: lbl.textContent }; return { ok: true, url: "https://pv-1.vercel.app" }; } });
  await act("", el);
  assert.deepEqual(seen, { disabled: true, text: "publishBusy" });
  assert.equal(el.disabled, false);
});

test("плашка Vercel: «Відкрити» — посилання з паролем (`remoteOpenUrl`) лише для безпечного https, `noopener`; «Скопіювати» — те саме посилання", () => {
  const br = remoteBranch();
  assert.match(br, /const share = remoteShareUrl\(curTask, r\.url\);/, "посилання з паролем — від оновленої задачі, а не вигадане в UI");
  assert.match(br, /const openUrl = remoteOpenUrl\(share, r\.url\);/, "«Відкрити» — повз сиру адресу з відповіді; гейт власника проходить через `#k=`");
  assert.match(br, /\.\.\.\(openUrl \? \[\{ act: 'open'/, "без безпечної адреси кнопки «Відкрити» нема");
  assert.match(br, /window\.open\(openUrl, '_blank', 'noopener'\)/, "без noopener відкрита сторінка бачить `window.opener`");
  assert.equal([...br.matchAll(/window\.open\(/g)].length, 1, "інших window.open у гілці нема — кожен мусив би мати свій захист");
  assert.match(br, /act: 'open'/);
  assert.match(br, /act: 'copy'/);
  assert.match(br, /label: t\('copyLink'\)/);
  assert.match(br, /run: \(\) => copyLinkText\(share\)/, "копіюємо те саме посилання, що відкриваємо");
  assert.doesNotMatch(br, /#k=/, "фрагмент із паролем складає сервер");
  assert.doesNotMatch(br, /window\.open\(r\.url/, "сира адреса з відповіді повз `safeRemoteUrl`");
});

test("гілка модульної відповіді стоїть раніше за `local` і за «деплой не вдався»", () => {
  const body = barAct("publish");
  assert.ok(body.indexOf("if (view.kind === 'remote') {") < body.indexOf("if (view.kind === 'local')"));
  assert.ok(body.indexOf("if (view.kind === 'remote') {") < body.indexOf("publishDeployFailed"));
});

test("`notice()` вміє додаткові рядки (textContent, не розмітка); без них розмітка плашки та сама", () => {
  assert.match(src, /function notice\(id, text, actions = \[\], onDismiss = null, lines = \[\]\) \{/);
  const body = fn("notice");
  assert.match(body, /cv-notice-sub/);
  assert.match(body, /\.textContent = /);
  assert.doesNotMatch(body, /innerHTML/, "рядки попереджень модуля — дані, не розмітка");
  assert.match(body, /cv-notice-body/);
  assert.match(body, /lines\.length/, "без рядків — звичайний `span`, як для інших плашок");
});

test("плашка `publish-remote` гаситься разом із задачею — поряд із `publish-local`", () => {
  assert.match(fn("resetPerTaskState"), /^\{[^]*?dropNotice\('publish-remote'\);/);
  assert.match(fn("resetPerTaskState"), /dropNotice\('publish-local'\);/, "плашку локальної публікації не прибрано");
});

test("«Відкрити превью» для публікації модулем: адреса проходить `safeRemoteUrl`, `noopener`", () => {
  const open = barAct("openpreview");
  assert.match(open, /remoteOpenUrl\(target\.share, target\.url\)/, "«Відкрити» веде на посилання з паролем, коли воно безпечне");
  assert.doesNotMatch(open, /safeRemoteUrl\(target\.url\)/, "стара перевірка лише адреси — власник упирався б у гейт");
  assert.match(open, /'noopener'/);
  assert.match(open, /target\.remote/, "перевірка лише для зовнішньої модульної цілі — ЛІГА як було");
});

test("«Скопіювати посилання»: ціль і готове посилання — з моделі (`copyUrl`), UI `#k=` не складає; запис у буфер спільний з плашкою", () => {
  const copy = barAct("copylink");
  assert.match(copy, /copyUrl\(target, \{/);
  assert.doesNotMatch(copy, /#k=|encodeURIComponent/, "посилання з паролем складає лише модель (`copyUrl`)");
  assert.match(copy, /await copyLinkText\(url\)/);
  const helper = fn("copyLinkText");
  assert.match(helper, /navigator\.clipboard\.writeText\(url\)/);
  assert.match(helper, /toast\(t\('toastCopied'\)\)/);
  assert.match(helper, /ask\(t\('askCopyLinkPrompt'\), url, \{ readOnly: true \}\)/, "фолбек без буфера лишився");
  const br = remoteBranch();
  assert.match(br, /copyLinkText\(/, "плашка копіює тим самим шляхом, що й дропдаун");
});

test("смуга: застереження Vercel — те, що віддав сервер (`publish_gate`/`publish_gate_stale`), без вигадок", () => {
  const body = fn("barState");
  assert.match(body, /pubGate: curTask\?\.publish_gate,/, "`undefined` (поля нема) мусить дійти до моделі як є: нема поля — нема тривоги");
  assert.match(body, /pubGateStale: curTask\?\.publish_gate_stale === true,/);
});

test("імпорти: нові правила Vercel беруться з моделі просторів", () => {
  const head = src.slice(0, src.indexOf("} from './spaces-model.js'"));
  for (const name of ["publishReaction", "remoteNoticeLines", "remoteOpenUrl", "remoteShareUrl", "spaceChanged"]) {
    assert.match(head, new RegExp(`\\b${name}\\b`), `${name} не імпортовано`);
  }
});

test("розмітка дропдауна: застереження Vercel малюються з `c.notes`, текст — через `esc(t(…))`", () => {
  assert.match(bar, /\(c\.notes \|\| \[\]\)\.map\(\(n\) => `<div class="dd-note dd-note--\$\{n\.id\}">\$\{esc\(t\(n\.key\)\)\}<\/div>`\)/);
  assert.match(bar, /\$\{c\.legacy \? `<div class="dd-note">\$\{t\("pubGateTruth"\)\}<\/div>` : ""\}\$\{notes\}<\/div>`/);
});

test("етап Д, виправлення ревʼю: гейт живості, слот поза стрілками, resetSpaceState скидає homeEdit, пізні дані — за newFormEl", () => {
  const open = fn("openNewTaskCard");
  assert.match(open, /const isLive = \(\) => newFormEl === form && homeOpen && homePage === 'tasks';/, "форма жива лише на відкритому екрані «Задачі»");
  assert.match(open, /\{ \.\.\.\(newFormCtx \?\? \{ sp, withRepo, taken \}\), trashIds \}, isLive\)/, "гейт іде в createTask; кошик читається при відправці");
  assert.match(open, /catch \(e\) \{\s*ctl\.error\(t\('errFailed', requestErrText\(e\)\)\);/, "несподіваний збій — у слот помилки");
  assert.match(open, /form\.remove\(\);/);
  const task = fn("createTask");
  const gate = task.indexOf("if (!isLive())");
  assert.ok(gate > 0, "гейт є");
  assert.ok(gate < task.indexOf("await leaveHome()") && gate < task.indexOf("currentTaskId = made.id"), "гейт — ДО навігації й зміни поточної задачі");
  assert.match(fn("resetSpaceState"), /resetHomeEdit\(\);/, "зміна простору скидає стан екрана задач");
  assert.match(fn("closeNewTaskCard"), /homeEdit = \{ \.\.\.homeEdit, newForm: false \};/, "закриття не стирає решту homeEdit");
  assert.match(src, /const homeCards = \(\) => \[\.\.\.\(homeNode\(\)\?\.querySelectorAll\('\.th-card:not\(#th-new-slot\)'\)/, "слот без tabindex не зупиняє стрілки");
  assert.match(fn("mountRepoHint"), /newFormEl === form/);
  assert.doesNotMatch(fn("mountRepoHint"), /isConnected/);
});

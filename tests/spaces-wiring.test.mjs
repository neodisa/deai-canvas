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
  assert.match(body, /catch \(e\) \{ tell\(t\('errFailed', e\.message\)\); return; \}/);
  assert.match(body, /await afterSpaceChange\(\);/);
});

/* ── вимикач інтеграцій: опитування НЕ запускаються ────────────────────── */

test("refreshGitlab і loadTeamsMute: першим рядком — вихід без запиту, коли інтеграцій нема", () => {
  assert.match(fn("refreshGitlab"), /^\{[^]*?\n  if \(noOutward\(\)\) \{ glCache = null; return; \}\n  try \{ glCache = await api\(/);
  assert.match(fn("loadTeamsMute"), /^\{[^]*?\n  if \(noOutward\(\)\) \{ teamsMute = null; return; \}\n  try \{ teamsMute = await api\('\/api\/teams-mute'\)/);
  assert.match(src, /const noOutward = \(\) => spaceNow\(\)\?\.integrations === false \|\| needsWelcome\(spacesResp\);/,
    "простір, про який знаємо, — рівно `=== false`; просторів нема зовсім — теж без опитувань");
});

test("список просторів: спершу задача відкритого запису, потім реєстр", () => {
  assert.match(src, /const spaceNow = \(\) => curTask\?\.space \?\? currentSpace\(spacesResp\);/);
});

/* ── канал коментарів затискається при ВИКОРИСТАННІ ────────────────────── */

test("канал коментарів: усі читання йдуть через effMode(), сирий commentMode не потрапляє в URL чи канал", () => {
  assert.doesNotMatch(src, /&ch=\$\{commentMode\}/, "рамка просить `ch` повз затиск");
  assert.equal([...src.matchAll(/&ch=\$\{effMode\(\)\}/g)].length, 2, "обидві гілки applyMode");
  assert.match(src, /channel: \(\) => effMode\(\),/);
  assert.match(src, /audiences: \(\) => \(noOutward\(\) \? \[\] : \[/, "без інтеграцій вкладок аудиторій нема");
  assert.match(src, /active: effMode\(\) === 'local'/);
  assert.match(src, /active: effMode\(\) === 'project'/);
  assert.match(src, /commentMode: effMode\(\),/, "палітра й смуга бачать ДІЮЧИЙ канал");
});

test("збережений вибір (localStorage) не переписується затиском: запис лише в setAudience, читання сире", () => {
  assert.equal([...src.matchAll(/setItem\('dc-comment-mode'/g)].length, 1);
  assert.match(fn("setAudience"), /setItem\('dc-comment-mode'/);
  assert.match(src, /let commentMode = \(\(\) => \{ try \{ return localStorage\.getItem\('dc-comment-mode'\) \|\| 'local'; \}/,
    "читання при старті — сире значення, без затиску");
  const body = fn("setAudience");
  assert.match(body, /if \(ch === 'project' && noOutward\(\)\) return;/, "команди без інтеграцій — відмова");
  assert.match(body, /if \(effMode\(\) === ch\) return;/, "порівняння з ДІЮЧИМ: `local` у просторі без інтеграцій не переписує збережений `project`");
  assert.ok(body.indexOf("noOutward()") < body.indexOf("effMode() === ch"));
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
    "homeUi.q = ''; homeUi.profiles.clear(); homeUi.designers.clear(); saveHomeUi();",
    "taskQ = ''; taskCursor = 0;",
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

test("newTaskDialog: простір називається ЯВНО, зайняті id — з усіх просторів, запит і перехід — усередині onSubmit", () => {
  const body = fn("newTaskDialog");
  assert.match(body, /space: sp\.id/, "без `space` сервер пішов би в простір з інтеграціями");
  assert.match(body, /formApi\('\/api\/tasks\?all=1'\)/);
  assert.match(body, /onSubmit: async \(vals, ctl\) => \{[\s\S]*?postForm\('\/api\/task-new'/);
  assert.match(body, /taskFormError\(vals, await taken\)/, "перевірка id ДО запиту");
  assert.match(body, /if \(spaceChanged\(sp\.id, made\.space\)\) await resetSpaceState\(\);\s*else await resetPerTaskState\(\);/);
  assert.match(body, /await leaveHome\(\);/);
  /* Перехід — УСЕРЕДИНІ onSubmit, після відповіді сервера: діалог, перебитий іншим питанням, не
     лишає сервер із задачею, а екран — без переходу. Нема `if (!v || !made) return` після askForm. */
  const sub = body.slice(body.indexOf("onSubmit:"));
  assert.ok(sub.indexOf("postForm('/api/task-new'") < sub.indexOf("await leaveHome();"), "перехід ПІСЛЯ відповіді сервера");
  assert.doesNotMatch(body, /if \(!v \|\| !made\) return;/, "продовження успіху не залежить від долі діалогу");
  assert.match(body, /\} catch \(e\) \{ toast\(t\('errFailed', e\.message\)\); \}\s*return undefined;/,
    "збій переходу — тост, а не «не вдалося створити» для задачі, що вже є");
  assert.match(body, /focusBack: \(\) => homeNode\(\)\?\.querySelector\('\[data-th="newtask"\]'\),/);
  assert.match(body, /ctl\.focus\(taskErrField\(key\)\)/, "поле помилки — aria-invalid");
});

test("діалоги простору: запит і перехід — усередині onSubmit (помилка лишається в діалозі), focusBack, перша вільна тека", () => {
  const nu = fn("openSpaceNew");
  assert.match(nu, /onSubmit: async \(vals, ctl\) => \{[\s\S]*?postForm\('\/api\/space-new'/);
  assert.match(nu, /catch \(e\) \{[\s\S]*?return t\(spaceErrKey\(e\.code\)\);/, "код відмови → ключ словника, e.code, не e.key");
  assert.match(nu, /api\(`\/api\/space-peek\?path=\$\{encodeURIComponent\(p\)\}`\)/);
  assert.match(nu, /needsWelcome\(spacesResp\) \? t\('personalName'\)/, "перший простір — «Особисте»");
  /* Тека — вільна: реєстр передається і в початковий шлях, і в проводку (там — функцією, щоб бачити оновлення). */
  assert.match(nu, /const taken = \(\) => \(spacesResp\?\.spaces \?\? \[\]\)\.map\(\(x\) => x\.path\);/);
  assert.match(nu, /path: defaultSpacePath\(name0, '~', taken\(\)\)/);
  assert.match(nu, /wireSpaceDialog\(form, \{\s*mode: 'new', taken, peek:/);
  /* Перехід — після відповіді сервера, ВСЕРЕДИНІ onSubmit; ззовні (після await askForm) його нема. */
  const sub = nu.slice(nu.indexOf("onSubmit:"));
  assert.ok(sub.indexOf("postForm('/api/space-new'") < sub.indexOf("await afterSpaceChange();"));
  assert.match(sub, /try \{ await afterSpaceChange\(\); \}\s*catch \(e\) \{ toast\(t\('errFailed', e\.message\)\); \}\s*return undefined;/);
  assert.doesNotMatch(nu.slice(0, nu.indexOf("onSubmit:")), /afterSpaceChange/);
  assert.doesNotMatch(nu, /if \(!v \|\| !made\)/, "перехід не залежить від результату askForm");
  assert.match(nu, /focusBack: spaceDialogFocusBack,/);
  assert.match(nu, /const field = spaceErrField\(e\.code\);\s*if \(field\) ctl\.focus\(field\);/);
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
  assert.match(fn("paintHome"), /needsWelcome\(spacesResp\) \? welcomeHTML\(\) : homeHTML\(homeView\(\), homeData\)/);
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
  assert.match(src, /function enterHome\(\{ spaces = true \} = \{\}\) \{/);
  assert.match(fn("enterHome"), /loadHome\(false, \{ spaces \}\);/);
  assert.match(src, /home: \(\) => enterHome\(\),/, "вхід логотипом перепитує простори (там і лікування)");
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
  assert.match(body, /homeRefreshedAt = now;\s*loadHome\(\);/);
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
  for (const [name, url] of [["openSpaceNew", "space-new"], ["openSpaceEdit", "space-update"], ["newTaskDialog", "task-new"]]) {
    const b = fn(name);
    assert.match(b, new RegExp(`postForm\\('/api/${url}'`), `${name}: запит без стелі`);
    assert.doesNotMatch(b, new RegExp(`[^m]post\\('/api/${url}'`), `${name}: лишився голий post`);
  }
  assert.match(fn("newTaskDialog"), /const taken = formApi\('\/api\/tasks\?all=1'\)/, "перелік id теж зі стелею: `await taken` у onSubmit не висить");
});

test("екран «Задачі»: вкладка — за effectiveTab (збережена `team` не переписується), кнопки задачі й простору", () => {
  assert.match(src, /if \(effectiveTab\(homeUi, homeData\) === v\) break;/);
  assert.doesNotMatch(src, /if \(homeUi\.tab === v\) break;/, "стара перевірка вернулась");
  assert.match(src, /case 'newtask': newTaskDialog\(\); break;/);
  assert.match(src, /case 'spacenew': openSpaceNew\(\); break;/);
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
     (`hasPublish`), а лише `integrations` не відрізняє «публікує модуль» від «публікації нема». */
  assert.match(body, /space: st\.space \? \{ id: st\.space\.id, integrations: st\.space\.integrations, capabilities: st\.space\.capabilities \} : null,/);
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
  const guard = "if (document.querySelector('.cv-ask-scrim')) return;";
  assert.ok(body.includes(guard), "⌘K відкрив би палітру поверх форми, що чекає відповіді сервера");
  assert.ok(body.indexOf(guard) < body.indexOf("paletteOverlay = 'pal'"), "перевірка ДО будь-якої зміни стану");
  assert.ok(body.indexOf(guard) < body.indexOf("openDd = null"), "і до закриття дропдауна");
  /* І кнопка в смузі, і ⌘K йдуть тим самим openPalette (див. BAR_ACTIONS.palette): другого входу повз перевірку нема. */
  assert.match(src, /palette: \(\) => openPalette\(\),/);
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
   стоять опитування GitLab/Teams і командний канал, а публікація пішла на `hasPublish`. */

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
  assert.match(body, /pubLocal: /);
  assert.match(body, /pubWhen: /);
  assert.match(body, /previewTarget\(curTask, spaceNow\(\)\)/);
});

test("публікація: відповідь модуля (`local`) — плашка «Опубліковано локально» з «Відкрити», а не «деплой не вдався»", () => {
  const body = barAct("publish");
  assert.match(body, /if \(r\.url\) \{ render\(\); return; \}/, "шлях ЛІГА змінено");
  assert.match(body, /const local = safeLocalUrl\(r\.local\?\.url, location\.origin\);/, "адресу з відповіді звіряємо з оригіном канваса");
  assert.match(body, /if \(r\.local\) \{/);
  assert.match(body, /notice\('publish-local', t\('publishLocalDone'\)/);
  assert.match(body, /act: 'open'/);
  assert.match(body, /window\.open\(local, '_blank', 'noopener'\)/, "без noopener відкрита сторінка бачить `window.opener`");
  /* `publishDeployFailed` — лише для відповіді без `url` і без `local` (ЛІГА без деплою). */
  assert.ok(body.indexOf("r.local") < body.indexOf("publishDeployFailed"),
    "гілка `local` мусить стояти ДО «деплой не вдався» (інакше успішна публікація модулем читається як невдалий деплой)");
  assert.match(body, /const m = publishErr\(e\);\n\s+tell\(t\(m\.key, \.\.\.\(m\.reasonKey \? \[t\(m\.reasonKey\)\] : m\.args\)\)\);/, "відмова повз `publishErr`");
  assert.doesNotMatch(body, /catch \(e\) \{ tell\(t\('errFailed', e\.message\)\); \}/, "стара загальна відмова лишилась");
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
});

test("палітра й смуга: публікація — на hasPublish, GitLab і командний канал — на integrations", () => {
  assert.match(pal, /import \{ hasPublish \} from "\.\/spaces-model\.js";/);
  assert.match(pal, /if \(hasPublish\(s\.space\)\) \{\n    out\.push\(\{\n      id: "publish"/);
  assert.match(pal, /if \(!noOutward\) \{\n    \/\/ Той самий трьохгілковий розгляд/);
  assert.match(pal, /if \(noOutward && ch === "project"\) continue;/);
  const model = readFileSync(new URL("../app/bar-model.js", import.meta.url), "utf8");
  assert.match(model, /hasPublish\(s\.space\)/);
  assert.match(model, /isLegacyPublish\(s\.space\)/);
  assert.doesNotMatch(model, /const OUTWARD = /, "спільний набір «назовні» мав розщепитись на gl і publish");
});

test("`noOutward` у app.js лишається на інтеграціях (публікація його не питає)", () => {
  assert.match(src, /const noOutward = \(\) => spaceNow\(\)\?\.integrations === false \|\| needsWelcome\(spacesResp\);/);
  assert.doesNotMatch(src, /hasPublish\(spaceNow\(\)\)[^;]*noOutward|noOutward\(\)[^;]*hasPublish/);
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
